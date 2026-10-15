"""Serves the NEXXUS PWA page and its community/feedback API.

Loopback-only by default. Serves a fixed whitelist of files; everything else 404s.
  GET  /api/community        -> {"comments": [...]}
  POST /api/comment          {name, text, rating}
  POST /api/upvote           {id}
  POST /api/feedback         {message, context}   -> logs/feedback.jsonl
Usage: python site_server.py [--port 8787] [--host 127.0.0.1]
"""
import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "logs"
COMMUNITY = ROOT / "nexxus_data" / "community.json"
FEEDBACK = LOGS / "feedback.jsonl"

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/manifest.json": ("manifest.json", "application/manifest+json"),
    "/sw.js": ("sw.js", "text/javascript"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/config.js": ("config.js", "text/javascript"),
    "/icon-512.png": ("icon-512.png", "image/png"),
    "/docs/images/dashboard.png": ("docs/images/dashboard.png", "image/png"),
}
MAX_BODY = 8 * 1024
LOCK = threading.Lock()


def _load():
    try:
        return json.loads(COMMUNITY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"comments": []}


def _save(data):
    COMMUNITY.parent.mkdir(parents=True, exist_ok=True)
    tmp = COMMUNITY.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(COMMUNITY)


def _clip(v, n):
    return str(v or "").strip()[:n]


class Handler(BaseHTTPRequestHandler):
    server_version = "NexxusSite"

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return None
        if n <= 0 or n > MAX_BODY:
            return None
        try:
            d = json.loads(self.rfile.read(n))
        except ValueError:
            return None
        return d if isinstance(d, dict) else None

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/community":
            with LOCK:
                return self._send(200, _load())
        entry = STATIC.get(path)
        if not entry:
            return self._send(404, {"error": "not found"})
        f = ROOT / entry[0]
        if not f.is_file():
            return self._send(404, {"error": "not found"})
        self._send(200, f.read_bytes(), entry[1])

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        d = self._json()
        if d is None:
            return self._send(400, {"error": "bad request"})

        if path == "/api/comment":
            text = _clip(d.get("text"), 1000)
            if not text:
                return self._send(400, {"error": "empty"})
            try:
                rating = max(0, min(5, int(d.get("rating") or 0)))
            except (TypeError, ValueError):
                rating = 0
            c = {"id": uuid.uuid4().hex[:12], "name": _clip(d.get("name"), 40),
                 "text": text, "rating": rating, "up": 0, "ts": int(time.time())}
            with LOCK:
                data = _load()
                data["comments"].append(c)
                _save(data)
            return self._send(200, {"comment": c})

        if path == "/api/upvote":
            cid = _clip(d.get("id"), 32)
            with LOCK:
                data = _load()
                for c in data["comments"]:
                    if c["id"] == cid:
                        c["up"] += 1
                        _save(data)
                        return self._send(200, {"up": c["up"]})
            return self._send(404, {"error": "no such comment"})

        if path == "/api/feedback":
            msg = _clip(d.get("message"), 1000)
            if not msg:
                return self._send(400, {"error": "empty"})
            ctx = d.get("context") if isinstance(d.get("context"), dict) else {}
            rec = {"ts": int(time.time()), "message": msg,
                   "context": {_clip(k, 40): _clip(v, 300) for k, v in list(ctx.items())[:10]}}
            with LOCK:
                LOGS.mkdir(exist_ok=True)
                with FEEDBACK.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
            return self._send(200, {"ok": True})

        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    a = ap.parse_args()
    print(f"NEXXUS site on http://{a.host}:{a.port}  (feedback -> {FEEDBACK})")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
