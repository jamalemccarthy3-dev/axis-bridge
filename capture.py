"""capture.py - NEXXUS media and capture module: screen snapshots, screen recording and camera snapshots, on command only.

Privacy rules, enforced here and not left to the caller:
  * OFF by default. Screen and camera are separate permissions, switched on by the operator (loopback only) and switched off the same way.
  * Never in the background. Nothing is captured unless a command arrives; a recording has a hard cap (MAX_RECORD_SECONDS) and can be stopped at any time.
  * Everything lands in nexxus_data/captures/ (newest MAX_FILES kept) and every attempt, allowed or refused, is appended to logs/capture_audit.jsonl.
  * Nothing leaves the machine. Analysis (`analyze`) talks only to the local Ollama server and only if NEXXUS_VISION_MODEL names an installed vision model.

Uses what is already installed: Pillow (screen snapshot) and the ffmpeg that ships with imageio-ffmpeg (screen recording through gdigrab, camera through dshow). Windows only for now.
"""
import base64
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURE_DIR = os.path.join(HERE, "nexxus_data", "captures")
STATE_PATH = os.path.join(HERE, "nexxus_data", "state", "capture_permissions.json")
AUDIT_PATH = os.path.join(HERE, "logs", "capture_audit.jsonl")
MAX_RECORD_SECONDS = 60
MAX_FILES = 100
KINDS = ("screen", "camera")
_LOCK = threading.RLock()
_REC = {"proc": None, "path": None, "started": None, "seconds": 0}


class CaptureError(Exception):
    pass


def _audit(action, allowed, detail=""):
    try:
        os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "action": action, "allowed": allowed, "detail": str(detail)[:300]}) + "\n")
    except OSError:
        pass


def permissions():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return {k: bool(d.get(k)) for k in KINDS}
    except (OSError, ValueError, AttributeError):
        return {k: False for k in KINDS}


def set_permission(kind, on):
    if kind not in KINDS:
        raise CaptureError("unknown capture kind: %s" % kind)
    with _LOCK:
        cur = permissions()
        cur[kind] = bool(on)
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE_PATH), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cur, f)
        os.replace(tmp, STATE_PATH)
    _audit("permission:%s" % kind, True, "on" if on else "off")
    if kind == "screen" and not on:
        stop_recording()
    return cur


def _need(kind, action):
    if not permissions().get(kind):
        _audit(action, False, "%s capture is switched off" % kind)
        raise CaptureError("%s capture is switched off. Switch it on first; NEXXUS never captures without it." % kind)


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise CaptureError("ffmpeg is not available (install imageio-ffmpeg)")


def _out(prefix, ext):
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    files = sorted((os.path.join(CAPTURE_DIR, f) for f in os.listdir(CAPTURE_DIR)), key=os.path.getmtime)
    for old in files[: max(0, len(files) - MAX_FILES + 1)]:
        try:
            os.remove(old)
        except OSError:
            pass
    return os.path.join(CAPTURE_DIR, "%s_%s.%s" % (prefix, time.strftime("%Y%m%d_%H%M%S"), ext))


def _entry(path, kind):
    return {"id": os.path.basename(path), "kind": kind, "path": path, "bytes": os.path.getsize(path) if os.path.exists(path) else 0}


def screen_snapshot():
    _need("screen", "screen_snapshot")
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=True)
    except Exception as e:
        _audit("screen_snapshot", False, type(e).__name__)
        raise CaptureError("could not capture the screen: %s" % type(e).__name__)
    path = _out("screen", "png")
    img.save(path)
    _audit("screen_snapshot", True, os.path.basename(path))
    return _entry(path, "screen")


def start_recording(seconds=10):
    _need("screen", "screen_record")
    seconds = max(1, min(int(seconds), MAX_RECORD_SECONDS))
    with _LOCK:
        if _REC["proc"] and _REC["proc"].poll() is None:
            raise CaptureError("a recording is already running; stop it first")
        path = _out("recording", "mp4")
        cmd = [_ffmpeg(), "-y", "-f", "gdigrab", "-framerate", "10", "-t", str(seconds), "-i", "desktop",
               "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            _audit("screen_record", False, type(e).__name__)
            raise CaptureError("could not start recording: %s" % type(e).__name__)
        _REC.update(proc=proc, path=path, started=time.time(), seconds=seconds)
    _audit("screen_record", True, "%ss -> %s" % (seconds, os.path.basename(path)))
    return {"id": os.path.basename(path), "kind": "recording", "path": path, "seconds": seconds, "recording": True}


def recording_status():
    with _LOCK:
        p = _REC["proc"]
        running = bool(p and p.poll() is None)
        return {"recording": running, "path": _REC["path"], "seconds": _REC["seconds"],
                "elapsed": round(time.time() - _REC["started"], 1) if running else 0}


def stop_recording():
    with _LOCK:
        p = _REC["proc"]
        if not p or p.poll() is not None:
            return {"recording": False}
        try:
            p.stdin.write(b"q")          # ffmpeg finishes the file cleanly on 'q'
            p.stdin.flush()
            p.wait(timeout=10)
        except Exception:
            p.kill()
        _audit("screen_record_stop", True, os.path.basename(_REC["path"] or ""))
        return {"recording": False, "saved": _entry(_REC["path"], "recording")}


def camera_devices():
    """Names of the video devices Windows reports (no capture happens)."""
    proc = subprocess.run([_ffmpeg(), "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                          capture_output=True, text=True, timeout=20)
    names = []
    for line in (proc.stderr or "").splitlines():
        m = re.search(r'"([^"]+)"\s+\(video\)', line)
        if m:
            names.append(m.group(1))
    return names


def camera_snapshot(device=None):
    _need("camera", "camera_snapshot")
    devices = camera_devices()
    if not devices:
        _audit("camera_snapshot", False, "no camera found")
        raise CaptureError("no camera found")
    device = device or devices[0]
    if device not in devices:
        _audit("camera_snapshot", False, "unknown device")
        raise CaptureError("unknown camera; choose one of: %s" % ", ".join(devices))
    path = _out("camera", "jpg")
    proc = subprocess.run([_ffmpeg(), "-y", "-f", "dshow", "-i", "video=" + device, "-frames:v", "1", path], capture_output=True, timeout=30)
    if proc.returncode != 0 or not os.path.exists(path):
        _audit("camera_snapshot", False, "ffmpeg failed")
        raise CaptureError("the camera did not return an image (is another app using it?)")
    _audit("camera_snapshot", True, os.path.basename(path))
    return _entry(path, "camera")


def list_captures():
    if not os.path.isdir(CAPTURE_DIR):
        return []
    return [_entry(os.path.join(CAPTURE_DIR, f), "file") for f in sorted(os.listdir(CAPTURE_DIR))]


def analyze(capture_id, prompt="Describe what you see in this image."):
    """Ask a LOCAL Ollama vision model about a saved image. Needs NEXXUS_VISION_MODEL; sends nothing off the machine."""
    model = os.environ.get("NEXXUS_VISION_MODEL", "").strip()
    if not model:
        raise CaptureError("no vision model configured (set NEXXUS_VISION_MODEL to an installed Ollama vision model)")
    if os.path.basename(capture_id) != capture_id or not capture_id.lower().endswith((".png", ".jpg")):
        raise CaptureError("analysis works on saved .png or .jpg captures only")
    path = os.path.join(CAPTURE_DIR, capture_id)
    if not os.path.isfile(path):
        raise CaptureError("no such capture")
    with open(path, "rb") as f:
        img = base64.b64encode(f.read()).decode()
    url = os.environ.get("NEXXUS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
    body = json.dumps({"model": model, "prompt": str(prompt)[:500], "images": [img], "stream": False}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}), timeout=300) as r:
            text = json.load(r).get("response", "")
    except Exception as e:
        _audit("analyze", False, type(e).__name__)
        raise CaptureError("the local vision model did not answer: %s" % type(e).__name__)
    _audit("analyze", True, capture_id)
    return {"id": capture_id, "model": model, "analysis": text}


def status():
    return {"permissions": permissions(), "recording": recording_status(), "max_record_seconds": MAX_RECORD_SECONDS,
            "vision_model": os.environ.get("NEXXUS_VISION_MODEL", "") or None, "captures": len(list_captures())}
