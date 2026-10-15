"""campaign_media.py - narrated, music-backed commercial videos from a campaign kit's scripts.

What is produced, honestly: a 1280x720 H.264 mp4 of brand-colour title cards (one per scene, the scene's line on screen), a REAL spoken narration made by the Windows text-to-speech voices installed on
this machine (the voice is named in the report), a synthesised background music bed (a soft chord progression, mixed well under the voice) with a small sound cue on the call to action, and an end
card with the call to action and a disclosure line. Assembly is script-driven: every scene's length comes from how long its narration really takes, and the whole file is checked (decodes, has video
and audio, length within 15% of the format).
What it is NOT: photoreal AI footage, AI presenters or studio-quality voices. Those need a text-to-video / voice service and a licence; none is built in, and nothing here pretends otherwise.
"""
import json
import os
import re
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100
W, H, FPS = 1280, 720, 12
PS_SPEAK = ("$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "if($env:NX_VOICE){$s.SelectVoice($env:NX_VOICE)}; $s.Rate=[int]$env:NX_RATE; $s.SetOutputToWaveFile($env:NX_OUT); "
            "$s.Speak([System.IO.File]::ReadAllText($env:NX_IN,[System.Text.Encoding]::UTF8)); $s.Dispose()")
PS_VOICES = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
             "$s.GetInstalledVoices() | Where-Object {$_.Enabled} | ForEach-Object { $v=$_.VoiceInfo; '{0}|{1}|{2}' -f $v.Name,$v.Gender,$v.Culture }")


class MediaError(Exception):
    pass


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise MediaError("ffmpeg is not available (pip install imageio-ffmpeg): %s" % e)


def _ps(script, env=None, timeout=90):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=timeout, env=e)
    if r.returncode:
        raise MediaError("speech synthesis failed: %s" % (r.stderr.strip().splitlines() or ["unknown"])[0][:200])
    return r.stdout


def list_voices():
    """-> [{"name", "gender", "culture"}] for the voices installed on THIS machine (empty if there is no speech engine)."""
    if os.name != "nt":
        return []
    try:
        out = _ps(PS_VOICES, timeout=40)
    except (MediaError, OSError, subprocess.SubprocessError):
        return []
    return [dict(zip(("name", "gender", "culture"), ln.strip().split("|"))) for ln in out.splitlines() if ln.count("|") == 2]


def speak(text, out_wav, voice=None, rate=0):
    text = str(text or "").strip()
    if not text or len(text) > 2000:
        raise MediaError("narration must be 1 to 2000 characters")
    voices = {v["name"] for v in list_voices()}
    if not voices:
        raise MediaError("no text-to-speech voice is installed on this machine")
    if voice and voice not in voices:
        raise MediaError("the voice %r is not installed (installed: %s)" % (voice, ", ".join(sorted(voices))))
    rate = max(-3, min(5, int(rate)))
    d = tempfile.mkdtemp(prefix="nxtts_")
    try:
        src = os.path.join(d, "in.txt")
        Path(src).write_text(text, encoding="utf-8")
        _ps(PS_SPEAK, {"NX_IN": src, "NX_OUT": str(out_wav), "NX_VOICE": voice or "", "NX_RATE": str(rate)})
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    return read_wav(out_wav)[1]


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        n, sr, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw != 2:
        raise MediaError("expected 16-bit audio")
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * SR / sr)), np.arange(len(a)), a).astype(np.float32)
    return a, len(a) / SR


def write_wav(path, a):
    a = np.clip(a, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((a * 32767).astype("<i2").tobytes())


# ---- music: a soft chord progression, synthesised here ----
def music_bed(seconds, mood="warm", seed=1):
    """Mono float32 at 44.1 kHz, peak about 0.18 (it sits under the voice), with a fade in and out."""
    prog = {"warm": [(0, 4, 7), (7, 11, 2), (9, 0, 4), (5, 9, 0)], "bright": [(0, 4, 7), (5, 9, 0), (7, 11, 2), (0, 4, 7)], "calm": [(9, 0, 4), (5, 9, 0), (0, 4, 7), (7, 11, 2)]}.get(mood)
    if prog is None:
        raise MediaError("mood must be warm, bright or calm")
    rng = np.random.default_rng(seed)
    root = 220.0 * 2 ** (rng.integers(0, 5) / 12)                         # a different key per seed, all comfortable
    n = int(seconds * SR)
    out = np.zeros(n, dtype=np.float32)
    beat = SR * 2.0
    t = 0
    k = 0
    while t < n:
        seg = int(min(beat, n - t))
        x = np.arange(seg) / SR
        env = np.minimum(1, x / 0.15) * np.exp(-x * 0.45)
        chord = np.zeros(seg, dtype=np.float32)
        for semi in prog[k % len(prog)]:
            f = root * 2 ** (semi / 12)
            chord += (np.sin(2 * np.pi * f * x) + 0.35 * np.sin(2 * np.pi * 2 * f * x) + 0.12 * np.sin(2 * np.pi * 3 * f * x)).astype(np.float32)
        out[t:t + seg] += chord * env.astype(np.float32)
        t += seg
        k += 1
    peak = float(np.max(np.abs(out))) or 1.0
    out = out / peak * 0.18
    fade = min(int(1.0 * SR), n // 4)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out


def cue(kind="ding"):
    """A short sound cue (a soft two-note pluck) for the call to action."""
    x = np.arange(int(0.9 * SR)) / SR
    env = np.exp(-x * 5.5)
    a = np.sin(2 * np.pi * 880 * x) * env
    b = np.where(x > 0.12, np.sin(2 * np.pi * 1318.5 * (x - 0.12)) * np.exp(-(x - 0.12) * 5.5), 0)
    c = (a + b).astype(np.float32)
    return c / (np.max(np.abs(c)) or 1) * 0.35


# ---- cards ----
def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def card(text, brand, colors, index, total, end=None):
    from PIL import Image, ImageDraw, ImageFont
    import campaign_kit as CK
    bg, ac = _rgb(colors["primary"]), _rgb(colors["accent"])
    fg = CK.text_colour(bg)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - 14, W, H], fill=ac)
    d.text((70, 48), brand, font=ImageFont.load_default(size=30), fill=fg)
    size = 64 if len(text) < 70 else 50 if len(text) < 130 else 40
    f = ImageFont.load_default(size=size)
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= W - 160 or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    y = (H - len(lines) * int(size * 1.3)) // 2 - (40 if end else 0)
    for ln in lines:
        d.text((80, y), ln, font=f, fill=fg)
        y += int(size * 1.3)
    if end:
        cta = end["cta_text"]
        fb = ImageFont.load_default(size=44)
        bw = int(d.textlength(cta, font=fb)) + 70
        ctext = CK.text_colour(ac)
        d.rounded_rectangle([80, y + 20, 80 + bw, y + 100], radius=18, fill=ac)
        d.text((80 + 35, y + 36), cta, font=fb, fill=ctext)
        d.text((80, y + 125), end["url"], font=ImageFont.load_default(size=30), fill=fg)
        d.text((80, H - 60), end["disclosure"], font=ImageFont.load_default(size=22), fill=fg)
    return im


def _write_video(path, frames_spec):
    import imageio_ffmpeg
    w = imageio_ffmpeg.write_frames(str(path), (W, H), fps=FPS, codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p", macro_block_size=16, quality=6)
    w.send(None)
    n = 0
    try:
        for arr, secs in frames_spec:
            for _ in range(max(1, int(round(secs * FPS)))):
                w.send(arr.tobytes())
                n += 1
    finally:
        w.close()
    return n


def probe(path):
    """-> {"seconds", "has_video", "has_audio", "frames"} by actually decoding the file."""
    r = subprocess.run([_ffmpeg(), "-i", str(path), "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    err = r.stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    frames = re.findall(r"frame=\s*(\d+)", err)
    return {"seconds": round(secs, 2), "has_video": "Video:" in err, "has_audio": "Audio:" in err, "frames": int(frames[-1]) if frames else 0, "decoded_ok": r.returncode == 0}


def make_commercial(profile, script, out_path, voice=None, mood="warm", seed=1, disclosure="Narration: synthetic voice. Made with automated tools."):
    """script: one entry of kit["video_scripts"]. -> report dict. Raises MediaError rather than producing a file that fails its own checks."""
    import numpy as _np
    scenes = script["scenes"]
    nominal = script["seconds"]
    tmp = Path(tempfile.mkdtemp(prefix="nxmedia_"))
    try:
        voice_tracks, durations, used_rate = [], [], 0
        for rate in (0, 1, 2, 3):                                         # speak a little faster only if the narration would overrun the format
            voice_tracks, durations = [], []
            for i, s in enumerate(scenes):
                wav = tmp / ("v%d_%d.wav" % (rate, i))
                speak(s["narration"], wav, voice, rate)
                a, secs = read_wav(wav)
                voice_tracks.append(a)
                durations.append(secs)
            used_rate = rate
            if sum(durations) + 0.5 * len(scenes) <= nominal * 1.15:
                break
        gap = 0.35
        starts, t = [], 0.4
        for secs in durations:
            starts.append(t)
            t += secs + gap
        total = t + 1.2                                                    # a beat after the last word for the cue and the end card
        if not nominal * 0.55 <= total <= nominal * 1.15:
            raise MediaError("the narration runs %.1f s for a %d s format even at the fastest pace: shorten the script" % (total, nominal))
        n = int(total * SR)
        audio = music_bed(total, mood, seed)
        voice_bus = _np.zeros(n, dtype=_np.float32)
        for a, s in zip(voice_tracks, starts):
            i = int(s * SR)
            voice_bus[i:i + len(a)] += a[:max(0, n - i)] * 0.95
        c = cue()
        ci = int(starts[-1] * SR + durations[-1] * SR * 0.6)
        audio[ci:ci + len(c)] += c[:max(0, n - ci)]
        # duck the music under the voice (smoothed envelope of the narration)
        env = _np.convolve(_np.abs(voice_bus), _np.ones(int(0.12 * SR)) / int(0.12 * SR), mode="same")
        duck = 1 - 0.6 * _np.clip(env / 0.05, 0, 1)
        mix = _np.clip(audio * duck + voice_bus, -0.98, 0.98).astype(_np.float32)
        wav_mix = tmp / "mix.wav"
        write_wav(wav_mix, mix)
        specs, endinfo = [], {"cta_text": profile["cta_text"], "url": re.sub(r"^https?://", "", profile["cta_url"]), "disclosure": disclosure}
        for i, s in enumerate(scenes):
            last = i == len(scenes) - 1
            im = card(s["on_screen_text"], profile["name"], profile["colors"], i, len(scenes), endinfo if last else None)
            span = (starts[i + 1] - starts[i]) if not last else (total - starts[i])
            if i == 0:
                span += starts[0]
            specs.append((_np.asarray(im, dtype=_np.uint8), span))
        silent = tmp / "silent.mp4"
        frames = _write_video(silent, specs)
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([_ffmpeg(), "-y", "-i", str(silent), "-i", str(wav_mix), "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)], capture_output=True, text=True, timeout=180)
        if r.returncode or not out.is_file():
            raise MediaError("assembly failed: %s" % (r.stderr.strip().splitlines() or ["unknown"])[-1][:200])
        pr = probe(out)
        problems = []
        if not (pr["has_video"] and pr["has_audio"] and pr["decoded_ok"]):
            problems.append("the file is missing a stream or does not decode")
        if not nominal * 0.55 <= pr["seconds"] <= nominal * 1.15:
            problems.append("length %.1f s is outside the format (%d s)" % (pr["seconds"], nominal))
        if problems:
            out.unlink(missing_ok=True)
            raise MediaError("the finished video failed its own checks: " + "; ".join(problems))
        peak = float(_np.max(_np.abs(mix)))
        return {"path": str(out), "bytes": out.stat().st_size, "seconds": pr["seconds"], "format_seconds": nominal, "frames": frames, "has_audio": True, "voice": voice or "(system default voice)",
                "speech_rate": used_rate, "music": "synthesised %s chord bed, ducked under the voice" % mood, "audio_peak": round(peak, 3), "disclosure": disclosure,
                "not_included": "photoreal AI footage, AI presenters and studio voices are not produced here"}
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
