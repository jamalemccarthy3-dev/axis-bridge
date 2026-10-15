"""stage_sessions.py - the working copies behind the 3D staging view.

Opening an image from the Creations hub starts a SESSION: a private working copy (the original in the hub is never touched). Each tool call changes the working copy and is recorded
(tool, the user's own parameters, what it measurably did); undo steps back; reset returns to the original. FINALIZE writes the result back to the Creations hub as a NEW linked version
(the original stays; the new one records the edits it came from), including the depth map when one was made, then closes the session. Sessions are memory-only, capped, and expire.
"""
import threading
import time
import uuid

import image_tools as T

MAX_SESSIONS = 6
MAX_HISTORY = 12
TTL = 2 * 3600


class StageError(Exception):
    pass


class Session:
    def __init__(self, sid, creation, original_png, now):
        self.id, self.creation, self.original = sid, creation, original_png
        self.history = [original_png]               # PNG bytes; the last one is the working copy
        self.ops = []                               # one entry per applied tool, aligned with history[1:]
        self.depth, self.depth_report = None, None
        self.version = 0                            # bumps on every change so the viewer can tell the picture changed
        self.touched = now

    def arr(self):
        return T.load(self.history[-1])

    def state(self):
        import io
        from PIL import Image
        w, h = Image.open(io.BytesIO(self.history[-1])).size
        return {"session": self.id, "creation_id": self.creation["id"], "title": self.creation["title"], "width": w, "height": h, "version": self.version, "edits": len(self.ops), "can_undo": len(self.ops) > 0,
                "ops": [{"tool": o["tool"], "params": o["params"], "result": o["result"]} for o in self.ops], "has_depth": self.depth is not None, "depth": self.depth_report}


class Stager:
    def __init__(self, now=time.time):
        self.now, self._s, self._lock = now, {}, threading.Lock()

    def _get(self, sid):
        with self._lock:
            s = self._s.get(sid)
        if s is None:
            raise StageError("that staging session is not open (it may have expired): open the asset again")
        s.touched = self.now()
        return s

    def _sweep(self):
        cut = self.now() - TTL
        for k in [k for k, s in self._s.items() if s.touched < cut]:
            del self._s[k]

    def open(self, creation, png_bytes):
        T.load(png_bytes)                                           # must be a readable image
        with self._lock:
            self._sweep()
            if len(self._s) >= MAX_SESSIONS:
                oldest = min(self._s.values(), key=lambda s: s.touched)
                del self._s[oldest.id]                              # the least recently used session makes room
            s = Session("st-" + uuid.uuid4().hex[:12], creation, png_bytes, self.now())
            self._s[s.id] = s
        return s

    def apply(self, sid, tool, params):
        s = self._get(sid)
        params = params if isinstance(params, dict) else {}
        try:
            if tool == "depth":
                z, rep = T.depth(s.arr(), params)
                s.depth, s.depth_report = _gray_png(z), rep
                s.version += 1
                s.ops.append({"tool": tool, "params": params, "result": rep, "depth_only": True})
                s.history.append(s.history[-1])
                del s.history[:-MAX_HISTORY - 1]
                del s.ops[:-MAX_HISTORY]
                return s
            fn = T.TOOLS.get(tool)
            if fn is None:
                raise StageError("unknown tool %r" % tool)
            out, rep = fn(s.arr(), params)
        except T.ToolError as e:
            raise StageError(str(e))
        s.history.append(T.to_png(out))
        del s.history[:-MAX_HISTORY - 1]
        s.ops.append({"tool": tool, "params": params, "result": rep})
        del s.ops[:-MAX_HISTORY]
        if s.depth is not None and tool != "depth":
            s.depth, s.depth_report = None, None                    # the picture changed, so the old depth map no longer matches it
        s.version += 1
        return s

    def undo(self, sid):
        s = self._get(sid)
        if len(s.history) < 2:
            raise StageError("nothing to undo")
        s.history.pop()
        last = s.ops.pop()
        if last.get("depth_only"):
            s.depth, s.depth_report = None, None
        s.version += 1
        return s

    def reset(self, sid):
        s = self._get(sid)
        s.history, s.ops, s.depth, s.depth_report = [s.original], [], None, None
        s.version += 1
        return s

    def image(self, sid):
        return self._get(sid).history[-1]

    def depth(self, sid):
        s = self._get(sid)
        if s.depth is None:
            raise StageError("no depth map has been made for this picture")
        return s.depth

    def close(self, sid):
        with self._lock:
            self._s.pop(sid, None)

    def finalize(self, sid, vault, title_for, depth_name):
        """Write the working copy back to the vault as a new version of the original. -> the new creation's meta. Closes the session."""
        s = self._get(sid)
        if not s.ops:
            raise StageError("nothing was changed, so there is nothing to sync back")
        parent = s.creation
        title = title_for(parent)
        files = [{"name": "image.png", "data": s.history[-1]}]
        if s.depth is not None:
            files.append({"name": depth_name, "data": s.depth})
        summary = "; ".join("%s%s" % (o["tool"], _short(o["params"])) for o in s.ops if not o.get("depth_only")) + ("; depth map (%s)" % s.depth_report["method"] if s.depth_report else "")
        meta = vault.save(title, files, source="staging", prompt=parent.get("prompt"), job_id=None, parent_id=parent["id"], instruction="staging edits: " + summary[:900])
        self.close(sid)
        return meta


def _short(p):
    keys = [k for k in ("mode", "action", "method", "tolerance") if k in p]
    return " (" + ", ".join("%s=%s" % (k, p[k]) for k in keys) + ")" if keys else ""


def _gray_png(z):
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(z, "L").save(b, "PNG")
    return b.getvalue()
