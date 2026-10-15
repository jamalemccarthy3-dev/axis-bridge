"""image_tools.py - the editing engine behind the 3D staging toolkit. Pure functions on RGBA images; each takes the working image and the user's own input (coordinates, a polygon, numbers) and
returns the changed image plus numbers that say what actually happened. Nothing is guessed or invented:
  crop        a box in image coordinates (0..1 of width/height), exactly as drawn
  trim        removes the uniform border: the background colour is measured from the image's own edge pixels (or its transparency), then the box around everything that differs is kept
  select      magic wand: from a clicked point, the region of similar colour (contiguous or not); REMOVE it (click the background) or KEEP it (click the subject)
  background  auto background removal: every region of border-like colour that touches the image edge is cleared (clean for a subject on a plain or smooth background; it is colour-based, not a
              learned model, so a busy background needs the wand or the lasso instead, and the result reports how much it cleared)
  lasso       a polygon the user drew: keep inside or remove inside, with a feathered edge
  alpha       edge feather, hard threshold, invert, or "clean" (keep only the largest connected piece, dropping specks)
  depth       a depth map made from the image: from its silhouette (a dome that rises from the edge; best after isolation) or from its luminance (relief); this is geometry for the viewer, not a
              learned monocular depth estimate, and the report says which one was used
Every function raises ToolError with a plain reason rather than returning a damaged image.
"""
import io
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

MAX_SIDE = 4096
MIN_SIDE = 8


class ToolError(Exception):
    pass


def load(data):
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:
        raise ToolError("the image cannot be read: %s" % str(e)[:100])
    if max(im.size) > MAX_SIDE:
        raise ToolError("the image is larger than %d px on a side" % MAX_SIDE)
    return np.array(im.convert("RGBA"), dtype=np.uint8)


def to_png(arr):
    b = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(b, "PNG", optimize=False)
    return b.getvalue()


def _num(v, name, lo, hi, default):
    if v is None:
        return default
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise ToolError("%s must be a number from %s to %s" % (name, lo, hi))
    return float(v)


def _pt(p, w, h, name="point"):
    if not (isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in p)):
        raise ToolError("%s must be [x, y] as fractions of the image" % name)
    if not (0 <= p[0] <= 1 and 0 <= p[1] <= 1):
        raise ToolError("%s is outside the image" % name)
    return min(w - 1, int(p[0] * w)), min(h - 1, int(p[1] * h))


def _dist(arr, color):
    d = arr[..., :3].astype(np.int32) - np.array(color[:3], dtype=np.int32)
    return np.sqrt((d * d).sum(axis=2))


def _tol(v):
    return _num(v, "tolerance", 0, 100, 18) * 4.42                       # 0..100 -> 0..~441 (the longest RGB distance)


def _label(mask):
    from scipy import ndimage
    return ndimage.label(mask)


def _feather(alpha, px):
    if px <= 0:
        return alpha
    return np.array(Image.fromarray(alpha, "L").filter(ImageFilter.GaussianBlur(px)), dtype=np.uint8)


def _cleared(before, after):
    a, b = before[..., 3] > 8, after[..., 3] > 8
    return {"visible_before_px": int(a.sum()), "visible_after_px": int(b.sum()), "cleared_pct": round(float(100.0 * (a.sum() - b.sum()) / max(1, a.sum())), 2)}


def crop(arr, p):
    h, w = arr.shape[:2]
    box = p.get("box")
    if not (isinstance(box, (list, tuple)) and len(box) == 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in box)):
        raise ToolError("a crop needs a box [x0, y0, x1, y1] as fractions of the image")
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ToolError("the crop box is outside the image or empty")
    X0, Y0, X1, Y1 = int(round(x0 * w)), int(round(y0 * h)), int(round(x1 * w)), int(round(y1 * h))
    if X1 - X0 < MIN_SIDE or Y1 - Y0 < MIN_SIDE:
        raise ToolError("the crop would be smaller than %d px" % MIN_SIDE)
    out = arr[Y0:Y1, X0:X1].copy()
    return out, {"from": [w, h], "to": [X1 - X0, Y1 - Y0], "box_px": [X0, Y0, X1, Y1]}


def trim(arr, p):
    h, w = arr.shape[:2]
    tol = _tol(p.get("tolerance"))
    pad = int(_num(p.get("padding"), "padding", 0, 200, 0))
    transparent = (arr[..., 3] < 250).any()
    if transparent and (arr[..., 3] <= 8).mean() > 0.001:
        keep, how = arr[..., 3] > 8, "its transparent border"
    else:
        edge = np.concatenate([arr[0, :, :3], arr[-1, :, :3], arr[:, 0, :3], arr[:, -1, :3]])
        bg = np.median(edge, axis=0)
        keep, how = _dist(arr, bg) > tol, "the border colour rgb(%d, %d, %d)" % tuple(int(x) for x in bg)
    ys, xs = np.where(keep)
    if len(xs) == 0:
        raise ToolError("everything matches the border, so there is nothing left to keep; lower the tolerance")
    x0, x1, y0, y1 = max(0, xs.min() - pad), min(w, xs.max() + 1 + pad), max(0, ys.min() - pad), min(h, ys.max() + 1 + pad)
    if (x0, y0, x1, y1) == (0, 0, w, h):
        raise ToolError("there is no uniform border to remove at this tolerance")
    if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
        raise ToolError("trimming would leave less than %d px" % MIN_SIDE)
    return arr[y0:y1, x0:x1].copy(), {"measured_from": how, "from": [w, h], "to": [int(x1 - x0), int(y1 - y0)], "removed_px": {"left": int(x0), "top": int(y0), "right": int(w - x1), "bottom": int(h - y1)}}


def select(arr, p):
    h, w = arr.shape[:2]
    x, y = _pt(p.get("point"), w, h)
    mode = p.get("mode", "remove")
    if mode not in ("remove", "keep"):
        raise ToolError("mode must be remove or keep")
    tol = _tol(p.get("tolerance"))
    feather = _num(p.get("feather"), "feather", 0, 20, 0)
    seed = arr[y, x]
    similar = _dist(arr, seed) <= tol
    if p.get("contiguous", True):
        lab, _ = _label(similar)
        region = lab == lab[y, x] if lab[y, x] else np.zeros_like(similar)
    else:
        region = similar
    if region.sum() < 4:
        raise ToolError("that click selected almost nothing: raise the tolerance")
    out = arr.copy()
    if mode == "remove":
        out[..., 3] = np.where(region, 0, out[..., 3])
    else:
        out[..., 3] = np.where(region, out[..., 3], 0)
    out[..., 3] = _feather(out[..., 3], feather)
    return out, dict({"selected_px": int(region.sum()), "selected_pct": round(float(100.0 * region.mean()), 2), "seed_colour": [int(v) for v in seed[:3]], "mode": mode}, **_cleared(arr, out))


def background(arr, p):
    h, w = arr.shape[:2]
    tol = _tol(p.get("tolerance"))
    feather = _num(p.get("feather"), "feather", 0, 20, 0)
    edge = np.concatenate([arr[0, :, :3], arr[-1, :, :3], arr[:, 0, :3], arr[:, -1, :3]])
    bg = np.median(edge, axis=0)
    similar = _dist(arr, bg) <= tol
    lab, n = _label(similar)
    touching = set(np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]]))) - {0}
    if not touching:
        raise ToolError("no region along the image edge matches the border colour at this tolerance; raise it, or use the wand on the background")
    region = np.isin(lab, list(touching))
    if region.mean() > 0.985:
        raise ToolError("that tolerance would clear nearly the whole image; lower it")
    out = arr.copy()
    out[..., 3] = np.where(region, 0, out[..., 3])
    out[..., 3] = _feather(out[..., 3], feather)
    return out, dict({"background_colour": [int(v) for v in bg], "regions_cleared": len(touching), "cleared_px": int(region.sum())}, **_cleared(arr, out))


def lasso(arr, p):
    h, w = arr.shape[:2]
    pts = p.get("points")
    if not isinstance(pts, list) or not 3 <= len(pts) <= 500:
        raise ToolError("a lasso needs 3 to 500 points")
    poly = [_pt(q, w, h, "a lasso point") for q in pts]
    area = abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))) / 2
    if area < 16:
        raise ToolError("the shape is too small or flat to enclose anything: spread the points out")
    mode = p.get("mode", "keep")
    if mode not in ("keep", "remove"):
        raise ToolError("mode must be keep or remove")
    feather = _num(p.get("feather"), "feather", 0, 20, 2)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).polygon(poly, fill=255)
    inside = np.array(m, dtype=np.uint8)
    if inside.sum() == 0:
        raise ToolError("the shape encloses no pixels")
    inside = _feather(inside, feather)
    out = arr.copy()
    a = out[..., 3].astype(np.float32)
    out[..., 3] = (a * (inside / 255.0 if mode == "keep" else 1 - inside / 255.0)).astype(np.uint8)
    return out, dict({"points": len(poly), "mode": mode, "feather_px": feather}, **_cleared(arr, out))


def alpha(arr, p):
    act = p.get("action")
    out = arr.copy()
    a = out[..., 3]
    if act == "feather":
        out[..., 3] = _feather(a, _num(p.get("amount"), "amount", 0.5, 20, 2))
    elif act == "threshold":
        t = int(_num(p.get("level"), "level", 1, 254, 128))
        out[..., 3] = np.where(a >= t, 255, 0).astype(np.uint8)
    elif act == "invert":
        out[..., 3] = 255 - a
    elif act == "clean":
        lab, n = _label(a > 8)
        if n < 2:
            raise ToolError("there is only one piece: nothing to clean")
        sizes = np.bincount(lab.ravel())[1:]
        keep = int(np.argmax(sizes)) + 1
        out[..., 3] = np.where(lab == keep, a, 0)
    else:
        raise ToolError("alpha action must be feather, threshold, invert or clean")
    return out, dict({"action": act}, **_cleared(arr, out))


def depth(arr, p):
    """-> (depth map as a uint8 'L' array, report). Does not change the image."""
    method = p.get("method", "silhouette")
    strength = _num(p.get("strength"), "strength", 0.1, 3, 1.0)
    h, w = arr.shape[:2]
    a = arr[..., 3] > 128
    if method == "silhouette":
        if a.sum() < 16:
            raise ToolError("there is no visible subject to build depth from")
        from scipy import ndimage
        d = ndimage.distance_transform_edt(a)
        d = d / max(1e-6, d.max())
        z = np.sqrt(np.clip(1 - (1 - d) ** 2, 0, 1)) ** (1.0 / strength)           # a dome: steep at the rim, flat on top
        z = np.where(a, z, 0)
        note = "dome from the visible silhouette" + (" (the image has no transparent area, so the whole rectangle is the subject: isolate the subject first for a real shape)" if a.mean() > 0.99 else "")
    elif method == "luminance":
        g = np.array(Image.fromarray(arr, "RGBA").convert("L").filter(ImageFilter.GaussianBlur(max(1, min(w, h) / 200))), dtype=np.float32)
        lo, hi = np.percentile(g[a] if a.any() else g, [2, 98])
        z = np.clip((g - lo) / max(1e-6, hi - lo), 0, 1) ** (1.0 / strength)
        z = np.where(a, z, 0)
        note = "relief from brightness (bright reads as near): a stylised relief, not measured depth"
    else:
        raise ToolError("depth method must be silhouette or luminance")
    return (z * 255).astype(np.uint8), {"method": method, "strength": strength, "note": note, "min": int(z.min() * 255), "max": int(z.max() * 255), "covered_pct": round(float(100.0 * a.mean()), 2)}


TOOLS = {"crop": crop, "trim": trim, "select": select, "background": background, "lasso": lasso, "alpha": alpha}
