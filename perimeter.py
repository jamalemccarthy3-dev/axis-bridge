"""perimeter.py - the operator's overrides at the perimeter: Hard Lock, Quarantine, and the breach log that drives the dashboard's alert flash and notification.

HARD LOCK freezes a node (an engine or module, by its mesh / gateway name): while it is locked NEXXUS refuses everything that comes from it or is addressed to it (signed mesh
posts, instructions, utility calls, jobs) and refuses to call it as a module. It is enforced here, in NEXXUS's own server and bridge. It changes no engine's files and kills no
process, and it is lifted only with the admin token. (The Triad module's own lockdown.flag needs its master secret and is not touched from here.)

QUARANTINE keeps a copy of a packet that failed verification (or any recorded transaction you choose) in a folder, as inert text with secrets blanked, so you can read it later.
Nothing in quarantine is ever executed, imported or replayed; releasing one simply deletes the copy. Releasing many at once (release_all) first writes a hash-chained record of what is
being released (released.jsonl: metadata only, never the packet) and never releases an item the operator was not shown.

BREACH EVENTS are the things that should make the dashboard flash: a signature that did not verify, a wrong admin token, a locked node trying to talk, a node being locked.
Repeats of the same thing from the same node within a few seconds count once (with a counter) so a flood cannot bury the log.

State lives in one folder (locks.json, events.json, quarantine/*.json). Standard library only."""
import hashlib
import json
import os
import re
import threading
import time
import uuid

NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,60}$")
MAX_EVENTS = 200
MAX_PACKET_CHARS = 4000
DEDUPE_S = 5.0


class PerimeterError(Exception):
    pass


def _scrub(obj):
    try:
        import link_hub
        return link_hub.scrub(obj)
    except Exception:                     # redaction is the point: without it, store nothing
        return "[unavailable: redaction module missing]"


class Perimeter:
    def __init__(self, directory, clock=time.time, on_breach=None):
        self.dir = str(directory)
        self.qdir = os.path.join(self.dir, "quarantine")
        os.makedirs(self.qdir, exist_ok=True)
        self.clock, self.on_breach = clock, on_breach
        self._lock = threading.RLock()
        self._locks = self._load("locks.json", {})
        self._events = self._load("events.json", [])
        self._seq = max([e.get("seq", 0) for e in self._events] or [0])
        self._acked = self._seq               # breaches from before this start were already seen

    # -- persistence --
    def _load(self, name, default):
        try:
            with open(os.path.join(self.dir, name), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save(self, name, value):
        tmp = os.path.join(self.dir, name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f)
        os.replace(tmp, os.path.join(self.dir, name))

    @staticmethod
    def _node(name):
        name = str(name or "").strip()
        if not NAME_RE.match(name):
            raise PerimeterError("that is not a node name")
        return name

    # -- hard lock --
    def lock(self, node, reason="", by="operator"):
        node = self._node(node)
        with self._lock:
            self._locks[node] = {"since": self.clock(), "reason": str(reason)[:200], "by": str(by)[:40]}
            self._save("locks.json", self._locks)
        self.breach("hard-lock", node, "Hard Lock applied: %s" % (str(reason)[:120] or "no reason given"), severity="info")
        return dict(self._locks[node])

    def unlock(self, node):
        node = self._node(node)
        with self._lock:
            if node not in self._locks:
                raise PerimeterError("%s is not locked" % node)
            del self._locks[node]
            self._save("locks.json", self._locks)
        return True

    def locked(self, node):
        with self._lock:
            v = self._locks.get(str(node))
            return dict(v) if v else None

    def locks(self):
        with self._lock:
            return {k: dict(v) for k, v in self._locks.items()}

    def blocked_reason(self, node):
        v = self.locked(node)
        return ("Hard Lock since %s%s" % (time.strftime("%H:%M:%S", time.localtime(v["since"])), (": " + v["reason"]) if v["reason"] else "")) if v else None

    # -- quarantine --
    def quarantine(self, source, reason, packet, txn_id=None):
        qid = "q" + uuid.uuid4().hex[:10]
        text = json.dumps(_scrub(packet), default=str)[:MAX_PACKET_CHARS]
        rec = {"id": qid, "at": self.clock(), "source": str(source)[:60], "reason": str(reason)[:200], "txn": txn_id, "packet": text, "bytes": len(text)}
        with self._lock:
            with open(os.path.join(self.qdir, qid + ".json"), "w", encoding="utf-8") as f:
                json.dump(rec, f)
        return qid

    def quarantined(self):
        out = []
        with self._lock:
            for fn in sorted(os.listdir(self.qdir)):
                if fn.endswith(".json"):
                    try:
                        with open(os.path.join(self.qdir, fn), encoding="utf-8") as f:
                            r = json.load(f)
                        out.append({k: r[k] for k in ("id", "at", "source", "reason", "txn", "bytes")})
                    except Exception:
                        continue
        return sorted(out, key=lambda r: r["at"])

    def quarantine_get(self, qid):
        if not re.match(r"^q[0-9a-f]{10}$", str(qid)):
            return None
        try:
            with open(os.path.join(self.qdir, qid + ".json"), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def release(self, qid):
        if not re.match(r"^q[0-9a-f]{10}$", str(qid)):
            raise PerimeterError("not a quarantine id")
        try:
            os.remove(os.path.join(self.qdir, qid + ".json"))
        except FileNotFoundError:
            raise PerimeterError("nothing quarantined under that id")
        return True

    def release_all(self, ids=None, by="operator"):
        """Release (delete) quarantined copies in one action. `ids` None = everything held right now; a list = exactly those that are still held (anything quarantined after the operator
        looked stays held and is counted in still_held, so a packet that arrives during an active run is never released unseen). Nothing is executed or replayed: a release only deletes the inert copy.
        Before any copy is deleted, one line per item is appended to released.jsonl (id, source, reason, txn, size and when: never the packet text), hash-chained to the line before it, so
        what was released stays on record after the copies are gone. -> {"released": n, "ids": [...], "still_held": m, "failed": k, "batch": id}."""
        with self._lock:
            held = {r["id"]: r for r in self.quarantined()}
            if ids is None:
                target = list(held)
            else:
                seen, target = set(), []
                for i in ids:
                    if isinstance(i, str) and re.match(r"^q[0-9a-f]{10}$", i) and i in held and i not in seen:
                        seen.add(i)
                        target.append(i)
            batch = "b" + uuid.uuid4().hex[:8]
            if target:
                prev = self._last_release_hash()
                lines = []
                for i in target:
                    r = held[i]
                    entry = {"batch": batch, "at": self.clock(), "by": str(by)[:40], "id": i, "source": r["source"], "reason": r["reason"], "txn": r["txn"], "bytes": r["bytes"], "prev": prev}
                    entry["hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True).encode("utf-8")).hexdigest()
                    prev = entry["hash"]
                    lines.append(json.dumps(entry))
                with open(os.path.join(self.dir, "released.jsonl"), "a", encoding="utf-8") as f:       # the record first: if this fails nothing is deleted
                    f.write("\n".join(lines) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            released, failed = [], 0
            for i in target:
                try:
                    os.remove(os.path.join(self.qdir, i + ".json"))
                    released.append(i)
                except FileNotFoundError:
                    released.append(i)                                    # someone else released it between the listing and now: it is gone, which is the goal
                except OSError:
                    failed += 1
            still_held = len([f for f in os.listdir(self.qdir) if f.endswith(".json")])
        if released:
            self.breach("quarantine-release-all", "operator", "Released %d quarantined item(s)%s" % (len(released), (", %d newer item(s) kept" % still_held) if still_held else ""), severity="info")
        return {"released": len(released), "ids": released, "still_held": still_held, "failed": failed, "batch": batch}

    def _last_release_hash(self):
        try:
            with open(os.path.join(self.dir, "released.jsonl"), "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                back = min(size, 65536)
                f.seek(size - back)
                last = f.read().rstrip(b"\r\n").split(b"\n")[-1]
            return json.loads(last.decode("utf-8"))["hash"]
        except (OSError, ValueError, KeyError, IndexError):
            return "0" * 64

    def release_log(self, limit=200):
        """What has been released, newest last (metadata only). verify: the chain is recomputed, a removed or edited line shows as ok False."""
        rows, ok, prev = [], True, "0" * 64
        try:
            with open(os.path.join(self.dir, "released.jsonl"), encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    e = json.loads(line)
                    body = {k: v for k, v in e.items() if k != "hash"}
                    if e.get("prev") != prev or hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest() != e.get("hash"):
                        ok = False
                    prev = e.get("hash", prev)
                    rows.append(e)
        except (OSError, ValueError):
            pass
        return {"ok": ok, "total": len(rows), "items": rows[-int(limit):]}

    # -- breach log --
    def breach(self, kind, node, detail, severity="warn", packet=None, txn_id=None):
        """Record a perimeter event. With `packet`, a scrubbed copy is quarantined too. -> the event (a repeat within a few seconds returns the same event with count+1)."""
        now = self.clock()
        quarantine_id = self.quarantine(node, "%s: %s" % (kind, str(detail)[:120]), packet, txn_id) if packet is not None else None
        with self._lock:
            last = next((e for e in reversed(self._events) if e["kind"] == kind and e["node"] == str(node)), None)
            if last and now - last["at"] < DEDUPE_S:
                last["count"] += 1
                last["at"] = now
                if quarantine_id:
                    last.setdefault("quarantine", []).append(quarantine_id)
                self._save("events.json", self._events)
                return dict(last)
            self._seq += 1
            ev = {"seq": self._seq, "at": now, "kind": str(kind)[:40], "node": str(node)[:60], "detail": str(detail)[:200], "severity": severity, "count": 1,
                  "quarantine": [quarantine_id] if quarantine_id else []}
            self._events.append(ev)
            del self._events[:-MAX_EVENTS]
            self._save("events.json", self._events)
        if self.on_breach:
            try:
                self.on_breach(dict(ev))
            except Exception:
                pass                              # a notification problem never changes the perimeter's decision
        return dict(ev)

    def events(self, since=0):
        with self._lock:
            return [dict(e) for e in self._events if e["seq"] > int(since)]

    def ack(self):
        with self._lock:
            self._acked = self._seq
            return self._acked

    def summary(self):
        """Public numbers: no node names, no packets."""
        with self._lock:
            last = self._events[-1] if self._events else None
            unacked = [e for e in self._events if e["seq"] > self._acked and e["severity"] != "info"]    # your own Hard Lock is logged but does not flash
            return {"locked": len(self._locks), "quarantined": len([f for f in os.listdir(self.qdir) if f.endswith(".json")]), "breach_seq": self._seq,
                    "unacked": len(unacked), "alert": bool(unacked),
                    "last": {"kind": last["kind"], "at": last["at"], "severity": last["severity"]} if last else None}
