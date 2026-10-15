"""publish_queue.py - the publishing queue: generated videos wait here, and nothing goes out until the owner says so.

    staged  ->  approved  ->  uploaded          (or failed / cancelled)

  * STAGING is automatic (a generated video, a content trigger, a bot). It sends nothing anywhere.
  * APPROVING is the owner's act (admin token at the route). A "public" video needs a second, separate confirmation; the default and the fallback are "private".
  * DISPATCHING is a dry run unless live mode is switched on (NEXXUS_PUBLISH_LIVE=1): the dry run records exactly what would be sent (metadata, file, size, SHA-256) and changes nothing.
    Live dispatch is capped per day (NEXXUS_PUBLISH_DAILY_CAP, default 3) so an automatic trigger cannot flood a channel or burn the API quota.
  * Every step is written to an append-only, hash-chained ledger that never contains a token.
Only videos that are already in the Creations hub can be queued, so what is sent is exactly what was generated, checked and shown to the owner.
"""
import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

import youtube_adapter

STATES = ("staged", "approved", "uploaded", "failed", "cancelled")
VIDEO_EXT = (".mp4", ".webm")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


class QueueError(Exception):
    pass


def live_mode():
    return os.environ.get("NEXXUS_PUBLISH_LIVE", "0") == "1"


def daily_cap():
    try:
        return max(0, int(os.environ.get("NEXXUS_PUBLISH_DAILY_CAP", "3")))
    except ValueError:
        return 3


class PublishQueue:
    def __init__(self, directory, creations, now=time.time):
        self.dir, self.creations, self.now = Path(directory), creations, now
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._file, self._ledger = self.dir / "queue.json", self.dir / "ledger.jsonl"
        self.items = {}
        if self._file.is_file():
            try:
                self.items = json.loads(self._file.read_text(encoding="utf-8")).get("items", {})
            except (OSError, ValueError):
                aside = self._file.with_suffix(".corrupt-%d" % int(now()))
                self._file.replace(aside)                      # never overwrite what could not be read
        self._last = self._tail()

    # ---- storage ----
    def _tail(self):
        try:
            lines = self._ledger.read_text(encoding="utf-8").strip().splitlines()
            return json.loads(lines[-1])["hash"] if lines else "0" * 64
        except (OSError, ValueError, KeyError, IndexError):
            return "0" * 64

    def _log(self, item_id, event, detail=None):
        rec = {"t": round(self.now(), 3), "id": item_id, "event": event, "detail": detail or {}, "prev": self._last}
        rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True).encode("utf-8")).hexdigest()
        with open(self._ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        self._last = rec["hash"]

    def _save(self):
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"items": self.items}, indent=1), encoding="utf-8")
        os.replace(tmp, self._file)

    def verify_ledger(self):
        """-> (ok, entries or the first bad line number). Detects any edited, removed or reordered entry."""
        prev, n = "0" * 64, 0
        try:
            lines = self._ledger.read_text(encoding="utf-8").splitlines() if self._ledger.is_file() else []
        except OSError:
            return False, 0
        for n, line in enumerate(lines, 1):
            try:
                rec = json.loads(line)
                h = rec.pop("hash")
            except (ValueError, KeyError):
                return False, n
            if rec.get("prev") != prev or hashlib.sha256(json.dumps(rec, sort_keys=True).encode("utf-8")).hexdigest() != h:
                return False, n
            prev = h
        return True, n

    # ---- the queue ----
    def stage(self, creation_id, title, description="", tags=(), topic="", privacy="private", source="manual"):
        title, description = str(title or "").strip(), str(description or "").strip()
        if not title or len(title) > 100 or _CTRL.search(title):
            raise QueueError("the title must be 1 to 100 characters of plain text")
        if len(description.encode("utf-8")) > 5000:
            raise QueueError("the description is over 5000 bytes")
        tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
        if len(tags) > 30 or any(len(t) > 30 or _CTRL.search(t) for t in tags):
            raise QueueError("at most 30 tags of up to 30 characters")
        if privacy not in youtube_adapter.PRIVACY:
            raise QueueError("privacy must be one of %s" % ", ".join(youtube_adapter.PRIVACY))
        meta = self.creations.get(str(creation_id))
        if not meta:
            raise QueueError("that creation is not in the Creations hub")
        vid = next((f for f in meta["files"] if f["name"].lower().endswith(VIDEO_EXT)), None)
        if meta.get("kind") != "video" or vid is None:
            raise QueueError("only videos (.mp4 or .webm) can be queued; that creation is %s" % meta.get("kind"))
        with self._lock:
            if any(i["creation_id"] == meta["id"] and i["state"] in ("staged", "approved") for i in self.items.values()):
                raise QueueError("that video is already waiting in the queue")
            iid = "pq-" + uuid.uuid4().hex[:12]                  # random: ids built from names and times collide when two items are staged together
            self.items[iid] = {"id": iid, "creation_id": meta["id"], "file": vid["name"], "title": title, "description": description, "tags": tags, "topic": str(topic)[:120], "privacy": privacy,
                               "state": "staged", "source": str(source)[:60], "staged_at": round(self.now(), 3)}
            self._save()
            self._log(iid, "staged", {"creation_id": meta["id"], "privacy": privacy, "source": source})
            return dict(self.items[iid])

    def get(self, item_id):
        with self._lock:
            i = self.items.get(item_id)
            if i is None:
                raise QueueError("no such queue item")
            return i

    def list(self):
        with self._lock:
            return sorted((dict(i) for i in self.items.values()), key=lambda i: i["staged_at"])

    def approve(self, item_id, privacy=None, confirm_public=False):
        with self._lock:
            i = self.get(item_id)
            if i["state"] not in ("staged", "failed"):
                raise QueueError("only a staged (or failed) item can be approved; this one is %s" % i["state"])
            p = privacy or i["privacy"]
            if p not in youtube_adapter.PRIVACY:
                raise QueueError("privacy must be one of %s" % ", ".join(youtube_adapter.PRIVACY))
            if p == "public" and confirm_public is not True:
                raise QueueError("a public video needs a separate explicit confirmation (confirm_public: true)")
            i.update(state="approved", privacy=p, approved_at=round(self.now(), 3))
            i.pop("error", None)
            self._save()
            self._log(item_id, "approved", {"privacy": p})
            return dict(i)

    def cancel(self, item_id):
        with self._lock:
            i = self.get(item_id)
            if i["state"] == "uploaded":
                raise QueueError("it has already been uploaded; remove it on YouTube")
            i["state"] = "cancelled"
            self._save()
            self._log(item_id, "cancelled")
            return dict(i)

    def _uploaded_today(self):
        day = time.strftime("%Y-%m-%d", time.localtime(self.now()))
        return sum(1 for i in self.items.values() if i["state"] == "uploaded" and time.strftime("%Y-%m-%d", time.localtime(i.get("uploaded_at", 0))) == day)

    def _path(self, i):
        p = self.creations.file_path(i["creation_id"], i["file"])
        if p is None or not Path(p).is_file():
            raise QueueError("the video file is no longer in the Creations hub")
        return Path(p)

    def dispatch(self, item_id, live=None):
        """Send an APPROVED item. Dry run unless live mode is on. -> {"dry_run": True, "would_send": {...}} or {"uploaded": {...}}."""
        live = live_mode() if live is None else bool(live)
        with self._lock:
            i = self.get(item_id)
            if i["state"] != "approved":
                raise QueueError("only an approved item can be dispatched; this one is %s" % i["state"])
            path = self._path(i)
            data = path.read_bytes()
            sent = {"title": i["title"], "privacy": i["privacy"], "tags": i["tags"], "file": i["file"], "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if not live:
                self._log(item_id, "dry_run", sent)
                return {"dry_run": True, "would_send": sent, "note": "nothing was sent: live mode is off (NEXXUS_PUBLISH_LIVE=1 turns it on)"}
            if self._uploaded_today() >= daily_cap():
                self._log(item_id, "refused_cap", {"cap": daily_cap()})
                raise QueueError("the daily upload cap (%d) has been reached; it resets tomorrow" % daily_cap())
            try:
                res = youtube_adapter.upload(str(path), i["title"], i["description"], i["tags"], i["privacy"])
            except youtube_adapter.YouTubeError as e:
                i.update(state="failed", error=str(e)[:300])
                self._save()
                self._log(item_id, "failed", {"error": str(e)[:300]})
                raise QueueError("the upload failed: %s" % e)
            i.update(state="uploaded", uploaded_at=round(self.now(), 3), result=res)
            self._save()
            self._log(item_id, "uploaded", {"video_id": res["video_id"], "privacy": res["privacy"], "sha256": sent["sha256"]})
            return {"uploaded": res, "sent": sent}
