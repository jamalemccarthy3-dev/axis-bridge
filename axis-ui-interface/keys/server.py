"""Keys: one page to enter every module's API keys, without anything holding them in the middle.

    http://keys.localhost:8080/        (through the module gateway; this computer only)

Each module declares the settings it needs in its own module.json ("keys": [...]). This tool reads those declarations, shows
which ones are set (never the value of a secret), and when you paste a key it writes it straight into THAT module's own .env
file and forgets it. It keeps no copy, logs no value, and holds nothing afterwards: delete this folder and every module still
works, remove a module and its keys vanish from the page.

Key declaration (in the module's module.json):
  "keys": [{"name": "BG_ANTHROPIC_KEY", "label": "Anthropic API key", "help": "https://...", "prefix": ["sk-ant-"],
            "secret": true, "restart": true, "group": "AI writer"}]
  name must be an UPPER_CASE variable; the value is written to <module folder>/.env only.
"""
import hmac
import http.client
import json
import os
import re
import secrets
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.dirname(HERE)                       # axis-ui-interface/
GATEWAY = ("127.0.0.1", int(os.environ.get("KEYS_GATEWAY_PORT", "8080")))
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
TOKEN = secrets.token_urlsafe(24)                    # per run; the page embeds it, saves must send it back (blocks cross-site posts)
_write_lock = threading.Lock()
MAX_VALUE = 400


def port():
    return int(os.environ.get("KEYS_PORT", "8730"))


def allowed_hosts():
    p = port()
    extra = [h.strip().lower() for h in os.environ.get("KEYS_ALLOWED_HOSTS", "keys.localhost:8080,keys.localhost").split(",") if h.strip()]
    return {f"127.0.0.1:{p}", f"localhost:{p}", *extra}


# ------------------------------------------------------------------ what modules declare
def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _clean_key(k):
    if not isinstance(k, dict) or not NAME_RE.match(str(k.get("name", ""))):
        return None
    prefix = k.get("prefix") or []
    prefix = [str(p) for p in (prefix if isinstance(prefix, list) else [prefix])][:6]
    return {"name": k["name"], "label": str(k.get("label") or k["name"])[:80], "help": str(k.get("help") or "")[:300],
            "group": str(k.get("group") or "")[:60], "secret": bool(k.get("secret", True)), "restart": bool(k.get("restart", False)), "prefix": prefix}


def modules():
    """Every module under the UI folder (a folder with module.json, or a <name>.module.json pointer) that declares keys."""
    found, self_dir = [], os.path.realpath(HERE)
    try:
        entries = sorted(os.listdir(UI_DIR))
    except OSError:
        return []
    for entry in entries:
        full = os.path.join(UI_DIR, entry)
        folder = None
        if os.path.isdir(full) and not entry.startswith(("_", ".")):
            folder = full
        elif entry.endswith(".module.json") and os.path.isfile(full):
            ptr = _read_json(full) or {}
            folder = os.path.normpath(str(ptr.get("folder", ""))) if ptr.get("folder") else None
        if not folder or os.path.realpath(folder) == self_dir or not os.path.isdir(folder):
            continue
        manifest = _read_json(os.path.join(folder, "module.json"))
        if not manifest or not isinstance(manifest.get("keys"), list):
            continue
        keys = [c for c in (_clean_key(k) for k in manifest["keys"]) if c]
        if keys and re.match(r"^[a-z0-9][a-z0-9-]{0,40}$", str(manifest.get("name", ""))):
            found.append({"name": manifest["name"], "folder": folder, "title": str(manifest.get("title") or manifest["name"])[:60], "keys": keys})
    return found


def find_module(name):
    return next((m for m in modules() if m["name"] == name), None)


# ------------------------------------------------------------------ the .env file (the only thing this tool ever writes)
def _env_path(module):
    return os.path.join(module["folder"], ".env")


def read_env(module):
    """{NAME: value} of active lines. Used only to say whether a key is set (and to show non-secret settings)."""
    out = {}
    try:
        with open(_env_path(module), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def validate(key, value):
    """Return an error string, or None. Values go to a one-line-per-setting file, so they must be a single clean line."""
    if len(value) > MAX_VALUE:
        return "that value is too long"
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        return "a key must be a single line with no hidden characters (re-copy it without trailing line breaks)"
    if value and (value[0] in "\"'" or value[-1] in "\"'"):
        return "remove the quote marks around the value"
    if value and key["prefix"] and not any(value.startswith(p) for p in key["prefix"]):
        return "that doesn't look like the right kind of key (expected it to start with " + " or ".join(key["prefix"]) + ")"
    return None


def write_env(module, name, value):
    """Set NAME=value in the module's .env: replace the existing active line or append. Atomic; other lines and line endings untouched."""
    path = _env_path(module)
    with _write_lock:
        try:
            with open(path, encoding="utf-8", newline="") as f:
                raw = f.read()
        except FileNotFoundError:
            raw = ""
        nl = "\r\n" if "\r\n" in raw else "\n"
        lines = raw.replace("\r\n", "\n").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        done = False
        for i, line in enumerate(lines):
            s = line.strip()
            if s and not s.startswith("#") and "=" in s and s.split("=", 1)[0].strip() == name:
                lines[i], done = f"{name}={value}", True
                break
        if not done:
            lines.append(f"{name}={value}")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(nl.join(lines) + nl)
        os.replace(tmp, path)


def describe():
    out = []
    for m in modules():
        env = read_env(m)
        out.append({"name": m["name"], "title": m["title"], "keys": [
            {"name": k["name"], "label": k["label"], "help": k["help"], "group": k["group"], "secret": k["secret"], "restart": k["restart"],
             "set": bool(env.get(k["name"])), "value": None if k["secret"] else env.get(k["name"], "")} for k in m["keys"]]})
    return out


def restart_module(name):
    """Ask the gateway to stop and start a module it manages, so it picks up its new .env."""
    for action in ("_stop", "_start"):
        conn = http.client.HTTPConnection(*GATEWAY, timeout=15)
        try:
            conn.request("POST", f"/{action}/{name}", "", {"Host": f"{GATEWAY[0]}:{GATEWAY[1]}", "Content-Length": "0"})
            if conn.getresponse().status >= 400:
                return False
        except (OSError, http.client.HTTPException):
            return False
        finally:
            conn.close()
    return True


# ------------------------------------------------------------------ HTTP
def page():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys.html"), encoding="utf-8") as f:
        return f.read().replace("__TOKEN__", TOKEN)


class Handler(BaseHTTPRequestHandler):
    server_version = "KeysTool/1.0"

    def log_message(self, *a):
        pass                                       # never log requests: they carry the values being saved

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _local(self):
        """This computer only: a loopback connection that did not come through a proxy or tunnel, to a known host name."""
        fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return (self.client_address[0] in ("127.0.0.1", "::1") and fwd in ("", "127.0.0.1", "::1")
                and (self.headers.get("Host") or "").lower() in allowed_hosts())

    def _dispatch(self):
        try:
            if not self._local():
                return self._send(404, {"error": "not found"})
            path = urllib.parse.urlparse(self.path).path
            if self.command in ("GET", "HEAD"):
                if path == "/":
                    return self._send(200, page(), "text/html; charset=utf-8")
                if path == "/api/health":
                    return self._send(200, {"ok": True, "service": "keys"})
                if path == "/api/keys":
                    return self._send(200, {"modules": describe()})
                return self._send(404, {"error": "not found"})
            if self.command == "POST":
                origin = self.headers.get("Origin")
                if origin and urllib.parse.urlparse(origin).netloc.lower() not in allowed_hosts():
                    return self._send(403, {"error": "cross-site request refused"})
                if not hmac.compare_digest(self.headers.get("X-Keys-Token", ""), TOKEN):
                    return self._send(403, {"error": "reload the page and try again"})
                n = int(self.headers.get("Content-Length") or 0)
                if n > 8192:
                    return self._send(413, {"error": "too large"})
                data = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError
                m = find_module(str(data.get("module", "")))
                if not m:
                    return self._send(404, {"error": "unknown module"})
                if path == "/api/keys/save":
                    key = next((k for k in m["keys"] if k["name"] == data.get("name")), None)
                    if not key:
                        return self._send(404, {"error": "that setting is not declared by the module"})
                    value = str(data.get("value", "")).strip()
                    err = validate(key, value)
                    if err:
                        return self._send(400, {"error": err})
                    write_env(m, key["name"], value)
                    return self._send(200, {"ok": True, "set": bool(value), "restart": key["restart"]})
                if path == "/api/keys/restart":
                    ok = restart_module(m["name"])
                    return self._send(200 if ok else 502, {"ok": ok})
            self._send(404, {"error": "not found"})
        except (ValueError, TypeError):
            self._send(400, {"error": "bad request"})
        except OSError:
            self._send(500, {"error": "could not write the settings file"})       # no detail: it must never echo a value
        except Exception as exc:
            print(f"[keys] {self.command} {self.path}: {type(exc).__name__}", flush=True)
            self._send(500, {"error": "server error"})

    do_GET = do_POST = do_HEAD = _dispatch


def make_server(host="127.0.0.1", p=None):
    return ThreadingHTTPServer((host, p if p is not None else port()), Handler)


if __name__ == "__main__":
    srv = make_server()
    print(f"[keys] ready on http://127.0.0.1:{srv.server_address[1]} (this computer only)", flush=True)
    srv.serve_forever()
