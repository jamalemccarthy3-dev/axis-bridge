"""campaign_queue.py - what happens AFTER a campaign kit exists: items wait here, and nothing leaves until the owner approves each one.

    staged  ->  approved  ->  exported            (or cancelled)

  * Staging is automatic and harmless: it only lists what could go out (a video, an ad, an email sequence, the landing page), with its copy checked again.
  * Approving is the owner's act, one item at a time, with an optional schedule time. There is no "approve all".
  * Exporting writes a ready-to-post package for that channel (the copy, the files with their hashes, the schedule, and the exact steps in that platform's own upload tool) into exports/<channel>/<id>/.
    It does not post. The platforms' publishing APIs need an app registration and the account owner's own authorisation; until you have that, you post the package yourself. YouTube is the one exception:
    a finished video can be handed to the publishing queue (publish_queue.py), which uploads only after a second approval there and is a dry run unless live mode is switched on.
  * Every AI-assisted item carries a disclosure line in its package (platforms ask for it, and viewers are entitled to it).
Everything is written to a hash-chained ledger.
"""
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

import campaign_kit as CK

CHANNELS = {"youtube": "video", "tiktok": "video", "linkedin": "ad", "meta": "ad", "google_ads": "ad", "native": "ad", "email": "email_sequence", "landing": "page"}
STEPS = {
    "youtube": "Open YouTube Studio > Create > Upload videos, choose the video file, paste the title and description from post.json, set Audience, and under 'Altered content' declare that it contains synthetic narration. Schedule from the Visibility step.",
    "tiktok": "In TikTok Studio upload the video, paste the caption from post.json, switch on the AI-generated content label, and schedule it from the upload page.",
    "linkedin": "In LinkedIn Campaign Manager create a Single image ad, upload the image from this folder, paste the intro text and headline from post.json, and set the schedule on the campaign.",
    "meta": "In Meta Ads Manager create an ad, upload the image(s) from this folder, paste the primary text, headline and description from post.json, and set the schedule at the ad set level.",
    "google_ads": "In Google Ads create a Responsive search ad, paste the headlines and descriptions from post.json (each is within Google's limits), and set the schedule on the campaign.",
    "native": "In your native ad platform create a campaign, upload the images, and paste the headline and description from post.json.",
    "email": "Load the sequence into your email service. Send only to people who asked to hear from you. Replace {{unsubscribe_url}} with the service's own unsubscribe link: it must work.",
    "landing": "Upload the landing folder to your web host (or open it in your site builder). It is one self-contained file.",
}
MAX_ITEMS = 40
DISCLOSURE = "Contains AI-assisted content: synthetic narration and automated copy. Reviewed and approved by the account owner before posting."


class QueueError(Exception):
    pass


class CampaignQueue:
    def __init__(self, root, now=time.time):
        self.root, self.now = Path(root), now
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._file, self._ledger = self.root / "queue.json", self.root / "ledger.jsonl"
        self.items = {}
        if self._file.is_file():
            try:
                self.items = json.loads(self._file.read_text(encoding="utf-8")).get("items", {})
            except (OSError, ValueError):
                self._file.replace(self._file.with_suffix(".corrupt-%d" % int(now())))
        self._last = "0" * 64
        try:
            lines = self._ledger.read_text(encoding="utf-8").strip().splitlines()
            self._last = json.loads(lines[-1])["hash"] if lines else self._last
        except (OSError, ValueError, KeyError, IndexError):
            pass

    def _log(self, event, detail=None):
        rec = {"t": round(self.now(), 3), "event": event, "detail": detail or {}, "prev": self._last}
        rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True).encode("utf-8")).hexdigest()
        with open(self._ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        self._last = rec["hash"]

    def verify_ledger(self):
        prev, n = "0" * 64, 0
        try:
            lines = self._ledger.read_text(encoding="utf-8").splitlines() if self._ledger.is_file() else []
        except OSError:
            return False, 0
        for n, line in enumerate(lines, 1):
            try:
                r = json.loads(line)
                h = r.pop("hash")
            except (ValueError, KeyError):
                return False, n
            if r.get("prev") != prev or hashlib.sha256(json.dumps(r, sort_keys=True).encode("utf-8")).hexdigest() != h:
                return False, n
            prev = h
        return True, n

    def _save(self):
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"items": self.items}, indent=1), encoding="utf-8")
        os.replace(tmp, self._file)

    # ---- staging ----
    def stage(self, kit_dir, kit, channel, files=None, title=None, video=None):
        """Stage one item for a channel from a finished kit folder. Copy is linted again against the profile; files must exist inside the kit folder."""
        if channel not in CHANNELS:
            raise QueueError("channel must be one of: %s" % ", ".join(CHANNELS))
        profile, kit_dir = kit["profile"], Path(kit_dir).resolve()
        payload, rels = {}, []
        if channel in ("tiktok", "youtube"):
            if not video:
                raise QueueError("a %s item needs a finished video file from this kit" % channel)
            rels = [video]
            fmt = "social_15s" if channel == "tiktok" else "broadcast_30s"
            sc = kit["video_scripts"].get(fmt) or next(iter(kit["video_scripts"].values()))
            payload = {"title": CK._cut("%s - %s" % (profile["name"], profile["offer"]), 100), "caption": CK._cut(kit["ads"]["tiktok"]["text"], 100) if channel == "tiktok" else None,
                       "description": "%s\n\n%s: %s\n\n%s" % (profile["what"], profile["cta_text"], profile["cta_url"], DISCLOSURE), "script": fmt}
        elif channel in ("linkedin", "meta", "native"):
            payload = dict(kit["ads"][channel])
            rels = files or ["graphics/social_1200x628.png"]
        elif channel == "google_ads":
            payload = dict(kit["ads"]["google_search"])
        elif channel == "email":
            payload = {"emails": kit["emails"]}
        elif channel == "landing":
            rels = ["landing/index.html"]
        hashes = {}
        for r in rels:
            p = (kit_dir / r).resolve()
            if kit_dir not in p.parents or not p.is_file():
                raise QueueError("the file %r is not in the kit folder" % r)
            hashes[r] = hashlib.sha256(p.read_bytes()).hexdigest()
        problems = []
        for k, v in payload.items():
            for s in (v if isinstance(v, list) else [v]):
                if isinstance(s, str) and k not in ("script",):
                    problems += CK.lint_copy(re.sub(re.escape(profile["cta_url"]), "", s), profile, "%s.%s" % (channel, k))
        if channel == "email":
            problems = [x for x in CK.check_kit(kit, profile) if "email" in x]
        if problems:
            raise QueueError("the copy failed its checks: " + " | ".join(problems[:4]))
        with self._lock:
            if len([i for i in self.items.values() if i["state"] in ("staged", "approved")]) >= MAX_ITEMS:
                raise QueueError("%d items are already waiting: approve, export or cancel some first" % MAX_ITEMS)
            iid = "cq-" + uuid.uuid4().hex[:12]
            self.items[iid] = {"id": iid, "channel": channel, "kind": CHANNELS[channel], "title": title or "%s - %s" % (profile["name"], channel), "payload": payload, "files": rels, "hashes": hashes,
                               "kit_dir": str(kit_dir), "business": profile["name"], "state": "staged", "scheduled_at": None, "created": round(self.now(), 3)}
            self._save()
            self._log("staged", {"id": iid, "channel": channel})
            return dict(self.items[iid])

    def get(self, iid):
        with self._lock:
            if iid not in self.items:
                raise QueueError("no such queue item")
            return self.items[iid]

    def list(self):
        with self._lock:
            return sorted((dict(i) for i in self.items.values()), key=lambda i: i["created"])

    def approve(self, iid, scheduled_at=None):
        with self._lock:
            i = self.get(iid)
            if i["state"] != "staged":
                raise QueueError("only a staged item can be approved; this one is %s" % i["state"])
            if scheduled_at:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?", str(scheduled_at)):
                    raise QueueError("schedule as YYYY-MM-DD or YYYY-MM-DD HH:MM (your local time)")
                if str(scheduled_at)[:10] < time.strftime("%Y-%m-%d", time.localtime(self.now())):
                    raise QueueError("that date is in the past")
            for r, h in i["hashes"].items():                                   # the files are exactly what was staged
                p = Path(i["kit_dir"]) / r
                if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
                    raise QueueError("%s changed after it was staged: stage it again" % r)
            i.update(state="approved", scheduled_at=scheduled_at, approved_at=round(self.now(), 3))
            self._save()
            self._log("approved", {"id": iid, "scheduled_at": scheduled_at})
            return dict(i)

    def cancel(self, iid):
        with self._lock:
            i = self.get(iid)
            if i["state"] == "exported":
                raise QueueError("it has already been exported")
            i["state"] = "cancelled"
            self._save()
            self._log("cancelled", {"id": iid})
            return dict(i)

    def export(self, iid):
        """Write the ready-to-post package. Only an APPROVED item can be exported. -> the item with its export folder. Nothing is posted."""
        with self._lock:
            i = self.get(iid)
            if i["state"] != "approved":
                raise QueueError("only an approved item can be exported; this one is %s" % i["state"])
            out = self.root / "exports" / i["channel"] / iid
            out.mkdir(parents=True, exist_ok=True)
            files = {}
            for r in i["files"]:
                src = Path(i["kit_dir"]) / r
                if hashlib.sha256(src.read_bytes()).hexdigest() != i["hashes"][r]:
                    raise QueueError("%s changed after approval" % r)
                shutil.copyfile(src, out / Path(r).name)
                files[Path(r).name] = i["hashes"][r]
            post = {"business": i["business"], "channel": i["channel"], "scheduled_at": i["scheduled_at"], "disclosure": DISCLOSURE, "copy": i["payload"], "files": files,
                    "approved_by_owner": True, "posted": False}
            (out / "post.json").write_bytes(json.dumps(post, indent=1).encode("utf-8"))
            (out / "README.txt").write_bytes(("%s\n\nChannel: %s\nScheduled for: %s\n\nSTEPS\n%s\n\nNothing has been posted. You post this yourself, from your own account.\n%s\n" % (
                i["title"], i["channel"], i["scheduled_at"] or "(not scheduled)", STEPS[i["channel"]], DISCLOSURE)).encode("utf-8"))
            i.update(state="exported", exported_at=round(self.now(), 3), export_dir=str(out))
            self._save()
            self._log("exported", {"id": iid, "dir": out.name})
            return dict(i)
