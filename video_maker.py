"""video_maker.py - renders a real mp4 explainer from text: a title card, then one card per line of the brief, with a short fade between cards.

This is a text-card video, nothing more: the words on screen are exactly the words given (the brief is never summarised or cut), set in a 1280x720 frame, encoded as H.264 by the ffmpeg
that ships with imageio-ffmpeg. It does not generate footage, voice or music; those need a different tool. verify() decodes the file back and proves its size, duration and frame count.
"""
import re
from pathlib import Path

W, H, FPS = 1280, 720, 12
MAX_CARDS, MAX_LINE, MAX_SECONDS = 24, 400, 180
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
BG, FG, ACCENT = (11, 16, 32), (232, 236, 245), (110, 168, 255)


class VideoError(Exception):
    pass


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        raise VideoError("Pillow 10.1 or newer is needed to set the card text size")


def _wrap(draw, text, font, width):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=font) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def _card(title, text, index, total):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 12, H], fill=ACCENT)
    big, small = _font(64), _font(26)
    d.text((80, 50), title, font=small, fill=ACCENT)
    size = 64 if len(text) < 90 else 48 if len(text) < 220 else 36
    font = big if size == 64 else _font(size)
    rows = _wrap(d, text, font, W - 200)
    lh = int(size * 1.35)
    if len(rows) * lh > H - 220:
        raise VideoError("card %d does not fit the frame at the smallest size; split it into shorter lines" % (index + 1))
    y = (H - len(rows) * lh) // 2
    for r in rows:
        d.text((100, y), r, font=font, fill=FG)
        y += lh
    d.text((80, H - 60), "%d / %d" % (index + 1, total), font=small, fill=(140, 150, 175))
    return img


def make(path, title, lines, seconds_per_card=3.0):
    """Write the mp4 to `path`. -> {"path","bytes","cards","seconds","width","height","fps"}. Raises VideoError rather than cutting anything."""
    import numpy as np
    import imageio_ffmpeg
    title = str(title or "").strip()
    cards = [str(x).strip() for x in (lines or []) if str(x).strip()]
    if not title or len(title) > 100:
        raise VideoError("the video needs a title of up to 100 characters")
    if not cards or len(cards) > MAX_CARDS:
        raise VideoError("give 1 to %d lines of text, one per card" % MAX_CARDS)
    for c in cards + [title]:
        if _CTRL.search(c) or len(c) > MAX_LINE:
            raise VideoError("each line must be plain text of up to %d characters" % MAX_LINE)
    if isinstance(seconds_per_card, bool) or not isinstance(seconds_per_card, (int, float)) or not 1 <= seconds_per_card <= 15:
        raise VideoError("seconds per card must be between 1 and 15")
    total = (len(cards) + 1) * seconds_per_card
    if total > MAX_SECONDS:
        raise VideoError("that would run %.0f seconds; the limit is %d" % (total, MAX_SECONDS))
    imgs = [_card("", title, 0, len(cards) + 1)] + [_card(title, c, i + 1, len(cards) + 1) for i, c in enumerate(cards)]
    arrs = [np.asarray(i, dtype=np.uint8) for i in imgs]
    hold, fade = max(1, int(seconds_per_card * FPS) - 4), 4
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    w = imageio_ffmpeg.write_frames(str(out), (W, H), fps=FPS, codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p", macro_block_size=16, quality=6)
    w.send(None)
    frames = 0
    try:
        for k, a in enumerate(arrs):
            for _ in range(hold):
                w.send(a.tobytes()); frames += 1
            nxt = arrs[k + 1] if k + 1 < len(arrs) else a
            for f in range(1, fade + 1):
                mix = (a.astype(np.float32) * (1 - f / (fade + 1)) + nxt.astype(np.float32) * (f / (fade + 1))).astype(np.uint8)
                w.send(mix.tobytes()); frames += 1
    finally:
        w.close()
    return {"path": str(out), "bytes": out.stat().st_size, "cards": len(arrs), "frames": frames, "seconds": round(frames / FPS, 2), "width": W, "height": H, "fps": FPS}


def verify(path, expect_frames=None):
    """Decode the file back. -> {"ok", "frames", "width", "height", "problems"}."""
    import imageio_ffmpeg
    problems, n, size = [], 0, None
    r = None
    try:
        r = imageio_ffmpeg.read_frames(str(path))
        meta = next(r)
        size = tuple(meta["size"])
        for _ in r:
            n += 1
    except Exception as e:
        if r is not None:
            r.close()
        return {"ok": False, "frames": n, "width": None, "height": None, "problems": ["the file does not decode: %s" % str(e)[:200]]}
    if size != (W, H):
        problems.append("size is %s, expected %s" % (size, (W, H)))
    if n < 1 or (expect_frames and abs(n - expect_frames) > 2):
        problems.append("frame count is %d, expected %s" % (n, expect_frames))
    return {"ok": not problems, "frames": n, "width": size[0] if size else None, "height": size[1] if size else None, "problems": problems}
