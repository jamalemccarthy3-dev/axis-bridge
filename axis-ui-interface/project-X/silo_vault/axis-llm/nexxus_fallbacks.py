"""nexxus_fallbacks.py - what nexxus_talks uses when one of its optional modules is not installed.

Each fallback is a small REAL implementation of the same interface, working on local files (under NEXXUS_FALLBACK_DIR, default ./Nexus/fallback_data), so a missing module means
"simpler", not "pretending". Where only the real module can do the job (translation, mirror synthesis, flow shaping) the fallback answers {"status": "unavailable", "reason": ...}
instead of returning something that looks like a result. Standard library only."""
import hashlib
import json
import math
import os
import re
import shutil
import threading
import time

BASE = os.environ.get("NEXXUS_FALLBACK_DIR") or os.path.join(".", "Nexus", "fallback_data")
WORD = re.compile(r"[a-z0-9]{2,}")


def _path(*parts):
    p = os.path.join(BASE, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def _unavailable(what):
    return {"status": "unavailable", "reason": "%s is not installed here, so nothing was done" % what}


# --------------------------------------------------------------------------------------------------------------------------- memory
class LocalMemoryIndex:
    """store_context(text, meta) keeps text in a local file; query_similar(text, k) returns the stored items most like it (cosine similarity of word counts), best first, each
    {"score", "text", "meta"}; None when nothing similar (score 0) is stored."""

    def __init__(self, name="memory"):
        self.file = _path(name + ".jsonl")

    def store_context(self, text, meta=None, *args, **kwargs):
        with open(self.file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"text": str(text), "meta": meta, "at": time.time()}) + "\n")
        return True

    @staticmethod
    def _vec(text):
        v = {}
        for w in WORD.findall(str(text).lower()):
            v[w] = v.get(w, 0) + 1
        return v

    def query_similar(self, text, k=3, *args, **kwargs):
        q = self._vec(text)
        qn = math.sqrt(sum(x * x for x in q.values())) or 1.0
        rows = []
        try:
            with open(self.file, encoding="utf-8") as f:
                for line in f:
                    item = json.loads(line)
                    v = self._vec(item["text"])
                    dot = sum(q.get(w, 0) * c for w, c in v.items())
                    if dot:
                        rows.append({"score": round(dot / (qn * (math.sqrt(sum(x * x for x in v.values())) or 1.0)), 4), "text": item["text"], "meta": item.get("meta")})
        except (OSError, ValueError):
            return None
        rows.sort(key=lambda r: -r["score"])
        return rows[:k] or None


# --------------------------------------------------------------------------------------------------------------------------- telemetry
class LocalTelemetryHub:
    """log_metric(name, value) appends to a local file; get_recent_errors() returns the latest metrics whose name contains 'error' or 'fail'."""

    def __init__(self):
        self.file = _path("telemetry.jsonl")

    def log_metric(self, name, value=1, *args, **kwargs):
        with open(self.file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"name": str(name), "value": value, "at": time.time()}, default=str) + "\n")
        return True

    def get_recent_errors(self, limit=20):
        out = []
        try:
            with open(self.file, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    if re.search(r"error|fail", r["name"], re.I):
                        out.append(r)
        except (OSError, ValueError):
            pass
        return out[-limit:]


# --------------------------------------------------------------------------------------------------------------------------- snapshots
class LocalRollbackManager:
    """create_snapshot(label, paths) copies the given files into a numbered snapshot folder with a manifest of their hashes; restore(snapshot_id) puts them back.
    With no paths it records an empty snapshot (and says so). -> the snapshot id."""

    def create_snapshot(self, label="snapshot", paths=(), *args, **kwargs):
        sid = "%s_%d" % (re.sub(r"\W+", "_", str(label))[:40], int(time.time() * 1000))
        files = {}
        for p in paths or ():
            if os.path.isfile(p):
                dest = _path("snapshots", sid, hashlib.sha256(os.path.abspath(p).encode()).hexdigest()[:16])
                shutil.copy2(p, dest)
                files[os.path.abspath(p)] = {"copy": dest, "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()}
        with open(_path("snapshots", sid, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"label": label, "files": files, "empty": not files}, f, indent=1)
        return sid

    def restore(self, snapshot_id):
        with open(_path("snapshots", snapshot_id, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        for orig, info in m["files"].items():
            shutil.copy2(info["copy"], orig)
        return sorted(m["files"])


# --------------------------------------------------------------------------------------------------------------------------- watching
class LocalWatcher:
    """start_sentry_loop() / start_monitoring(path) watch a folder tree on a background thread: every `interval` seconds the file list (name, size, mtime) is compared with the
    last look, and each file added, removed or changed is appended to the events file. stop() ends it. Not a security product: it notices changes, it does not judge them."""

    def __init__(self, interval=2.0):
        self.interval = interval
        self.events_file = _path("watch_events.jsonl")
        self._stop = threading.Event()
        self._thread = None
        self.last_error = None

    @staticmethod
    def _scan(root):
        out = {}
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in (".git", "__pycache__", "node_modules")]
            for f in fn:
                p = os.path.join(dp, f)
                try:
                    st = os.stat(p)
                    out[p] = (st.st_size, int(st.st_mtime))
                except OSError:
                    continue
        return out

    def _run(self, root):
        before = self._scan(root)
        while not self._stop.wait(self.interval):
            try:
                now = self._scan(root)
                with open(self.events_file, "a", encoding="utf-8") as f:
                    for p in now.keys() - before.keys():
                        f.write(json.dumps({"event": "added", "path": p, "at": time.time()}) + "\n")
                    for p in before.keys() - now.keys():
                        f.write(json.dumps({"event": "removed", "path": p, "at": time.time()}) + "\n")
                    for p in now.keys() & before.keys():
                        if now[p] != before[p]:
                            f.write(json.dumps({"event": "changed", "path": p, "at": time.time()}) + "\n")
                before = now
            except Exception as e:                           # noqa: BLE001 - a watcher must survive a bad scan
                self.last_error = "%s: %s" % (type(e).__name__, e)

    def start_monitoring(self, path=".", *args, **kwargs):
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(path,), daemon=True)
        self._thread.start()
        return True

    def start_sentry_loop(self, path=".", *args, **kwargs):
        return self.start_monitoring(path)

    def stop(self):
        self._stop.set()


# --------------------------------------------------------------------------------------------------------------------------- vault, persona, templates, queue
class LocalVault:
    """archive_record(collection, record) appends the record (with a hash and time) to a local collection file."""

    def archive_record(self, collection="records", record=None, *args, **kwargs):
        entry = {"at": time.time(), "record": record, "sha256": hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()}
        with open(_path("vault", re.sub(r"\W+", "_", str(collection)) + ".jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry["sha256"]


class SimplePersona:
    """set_state(state) remembers the persona state the engine switched to; get_state() reads it back."""

    def __init__(self):
        self.state = "DEFAULT"

    def set_state(self, state):
        self.state = str(state)
        return self.state

    def get_state(self):
        return self.state


class RateLimitedQueue:
    """execute_throttled(func, ...) runs func after waiting, if needed, so calls are at least `min_gap` seconds apart (one at a time)."""

    def __init__(self, min_gap=0.0):
        self.min_gap = min_gap
        self._last = 0.0
        self._lock = threading.Lock()

    def execute_throttled(self, func, *args, **kwargs):
        with self._lock:
            wait = self.min_gap - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                return func(*args, **kwargs)
            finally:
                self._last = time.monotonic()


PROMPTS = {"default": "You are a careful assistant. Answer plainly and say when you are unsure.",
           "technical": "You are a precise engineer. Give exact steps, name the files and commands, and state any assumption.",
           "intuitive": "Explain simply, with an everyday example, then give the technical term in brackets."}


class SimplePromptTemplates:
    @staticmethod
    def get_template(profile="default"):
        return PROMPTS.get(str(profile).lower(), PROMPTS["default"])


class UnavailableEngine:
    """Stands in for an engine that is not installed: every method returns {"status": "unavailable", ...}."""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, item):
        if item.startswith("__"):
            raise AttributeError(item)
        return lambda *a, **k: _unavailable(self._name)


class UntranslatedBridge:
    """Without the real translator both 'views' are the original text, and the answer says so (it is not a translation)."""

    def dual_translate(self, text):
        return {"technical_view": text, "intuitive_view": text, "glossary_references": {}, "translated": False, "note": "bilingual_translator is not installed: both views are the original text"}
