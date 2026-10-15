#!/usr/bin/env python3
"""axis_vault_container.py - the universal AXIS-CLOUD vault container: one Python file you drop into any folder (a cloud drive root, a local path, the dashboard's core mount) to govern it.

Run it (python axis_vault_container.py) and it
  1. discovers where it is: the folder the file sits in is the HOST. No hard-coded paths, no sync client.
  2. provisions   <host>/AXIS_SECURE_VAULT/  with  files/ (the verified copies), _versions/ (earlier versions of anything that changed), vault_manifest.json (what is in the vault and its SHA-256),
                  and <host>/vault_activity.log (hash-chained, one JSON line per event).
  3. mirrors      every file that appears or changes in the host folder into the vault with sync_file(): copy to a temp file inside the vault, fsync, require that the source did not change while it was being
                  copied (hash before = hash of the bytes written = hash after), read the copy back and compare, and only then os.replace it into place. A byte-accurate copy or nothing.
  4. reports      one clear line per state on the terminal ([AXIS-VAULT] ... SYNC_OK / SYNC_UNCHANGED / SYNC_SKIPPED / SYNC_FAILED / VERIFY_OK / HEALTH green|yellow|red) and the same facts, atomically, in
                  vault_status.json for a telemetry loop to read.

What it is and is not (said plainly, because a backup tool that oversells itself is dangerous):
  * It is a verified-copy mirror with isolation and tamper evidence: the vault is a separate folder the mirror never reads back from, source paths are confined to the host (symlinks and anything that resolves
    outside are refused), nothing in the vault is ever overwritten silently (a changed file moves its previous version to _versions/ first), and the activity log and manifest detect edits.
  * It is NOT encryption and NOT access control. Anyone who can read the folder (or the cloud account that syncs it) can read the vault. Put the host folder on an encrypted volume or use your provider's
    encryption if the contents are sensitive. "Impenetrable" is not a claim this module makes.
  * It never deletes anything from the vault. If a source file is removed, the vault keeps its copy and the manifest records that the source is gone.
  * Stdlib only. Settings come from AXIS_VAULT_CONFIG in a master_config.py next to this file (read as a constant, never imported); with no master_config.py the defaults below apply.

    python axis_vault_container.py              provision, mirror what is there, then keep watching        (Ctrl-C to stop)
    python axis_vault_container.py --once       provision, mirror what is there, exit (0 all good, 1 any failure)
    python axis_vault_container.py --sync PATH  mirror one file now
    python axis_vault_container.py --verify     re-hash every vault copy against the manifest
    python axis_vault_container.py --status     print vault_status.json
"""
import argparse
import ast
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

DEFAULT_CONFIG = {
    "enabled": True,
    "vault_folder_name": "AXIS_SECURE_VAULT",
    "log_file": "vault_activity.log",
    "status_file": "vault_status.json",
    "poll_interval_seconds": 5,           # how often the host folder is looked at
    "heartbeat_seconds": 60,              # how often a HEALTH line is printed and the status file refreshed
    "max_file_mb": 2048,                  # larger files are skipped and reported, not half-copied
    "verify_after_copy": True,            # read the copy back and compare hashes before it is put in place
    "keep_versions": 0,                   # 0 = keep every earlier version; N = keep the newest N per file (older ones are then deleted)
    "mirror_to": [],                      # extra existing folders (another drive, a cloud folder): each gets its own verified copy in <folder>/<vault_folder_name>/files
    "exclude_patterns": ["*.tmp", "*.part", "*.crdownload", "~$*", ".~lock*", "desktop.ini", ".DS_Store", "Thumbs.db", "*.pyc", "*.swp", "*.log.lock"],
    "exclude_dirs": [".git", "__pycache__", "node_modules", ".venv"],
}
LOCK = threading.RLock()
CHUNK = 1024 * 1024
OFFLINE_ATTRS = 0x1000 | 0x400000 | 0x40000      # FILE_ATTRIBUTE_OFFLINE | RECALL_ON_DATA_ACCESS | RECALL_ON_OPEN: a cloud placeholder; reading it would download it


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(host_dir, overrides=None):
    """Defaults, then AXIS_VAULT_CONFIG from master_config.py beside this file (ast, not import), then overrides. Anything of the wrong type is rejected loudly."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    mc = Path(__file__).resolve().parent / "master_config.py"
    if mc.is_file():
        try:
            tree = ast.parse(mc.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "AXIS_VAULT_CONFIG" for t in node.targets):
                    cfg.update(ast.literal_eval(node.value))
        except (OSError, SyntaxError, ValueError) as e:
            raise ValueError("AXIS_VAULT_CONFIG in %s could not be read: %s" % (mc, e))
    cfg.update(overrides or {})
    for key, typ in (("vault_folder_name", str), ("log_file", str), ("status_file", str), ("poll_interval_seconds", (int, float)), ("heartbeat_seconds", (int, float)), ("max_file_mb", (int, float)),
                     ("verify_after_copy", bool), ("keep_versions", int), ("mirror_to", list), ("exclude_patterns", list), ("exclude_dirs", list), ("enabled", bool)):
        if not isinstance(cfg[key], typ):
            raise ValueError("AXIS_VAULT_CONFIG[%r] must be %s" % (key, typ))
    for key in ("vault_folder_name", "log_file", "status_file"):
        if not cfg[key] or os.sep in cfg[key] or "/" in cfg[key] or cfg[key] in (".", ".."):
            raise ValueError("AXIS_VAULT_CONFIG[%r] must be a plain name" % key)
    return cfg


class VaultError(RuntimeError):
    pass


class AxisVaultContainer:
    def __init__(self, host_dir=None, config=None, quiet=False):
        self.host = Path(host_dir).resolve() if host_dir else Path(__file__).resolve().parent
        if not self.host.is_dir():
            raise VaultError("host folder does not exist: %s" % self.host)
        self.cfg = config or load_config(self.host)
        self.quiet = quiet
        self.vault = self.host / self.cfg["vault_folder_name"]
        self.files = self.vault / "files"
        self.versions = self.vault / "_versions"
        self.manifest_path = self.vault / "vault_manifest.json"
        self.log_path = self.host / self.cfg["log_file"]
        self.status_path = self.host / self.cfg["status_file"]
        self.script = Path(__file__).resolve()
        self.own = {self.script, self.host / self.script.name, self.log_path, self.status_path}          # the container never mirrors itself or its own bookkeeping
        self.failing = {}                                                                                  # rel path -> last error: health is yellow while any file is failing and clears when a retry succeeds
        self.counters = {"synced": 0, "unchanged": 0, "skipped": 0, "failed": 0, "bytes": 0, "versions_kept": 0}
        self.started_at = now()
        self.last_event, self.last_error, self.last_verify = None, None, None
        self.manifest = {"schema": "axis.vault.manifest/1", "host": str(self.host), "created": now(), "entries": {}}
        self._last_hash = None
        self._pending, self._known = {}, {}       # path -> signature last seen / path -> signature already mirrored: a file is copied once it has stopped changing
        self._stop = threading.Event()
        self.provisioned = False

    # -- terminal + activity log
    def emit(self, state, detail="", **fields):
        """One line on the terminal, one hash-chained line in vault_activity.log. `state` is what a telemetry loop greps for."""
        line = "[AXIS-VAULT] %s %-15s %s" % (now(), state, detail)
        if not self.quiet:
            print(line, flush=True)
        self.last_event = {"at": now(), "state": state, "detail": detail}
        with LOCK:
            try:
                if self._last_hash is None:
                    self._last_hash = self._tail_hash()
                entry = {"at": now(), "state": state, "detail": detail, **fields, "prev": self._last_hash}
                entry["entry_hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True).encode("utf-8")).hexdigest()
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self._last_hash = entry["entry_hash"]
            except OSError as e:
                self.last_error = "activity log not writable: %s" % e
        return line

    def _tail_hash(self):
        try:
            size = self.log_path.stat().st_size
            if not size:
                return "0" * 64
            buf, pos = b"", size
            with open(self.log_path, "rb") as f:
                while pos > 0:
                    step = min(65536, pos)
                    pos -= step
                    f.seek(pos)
                    buf = f.read(step) + buf
                    lines = buf.rstrip(b"\r\n").split(b"\n")
                    if len(lines) > 1 or pos == 0:
                        return json.loads(lines[-1].decode("utf-8"))["entry_hash"]
        except (OSError, ValueError, KeyError):
            pass
        return "0" * 64

    def verify_log(self):
        """-> {"ok", "entries", "broken_at"}: recomputes the activity log's chain."""
        prev, n = "0" * 64, 0
        try:
            for line in self.log_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                n += 1
                e = json.loads(line)
                body = {k: v for k, v in e.items() if k != "entry_hash"}
                if e.get("prev") != prev or hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest() != e.get("entry_hash"):
                    return {"ok": False, "entries": n, "broken_at": n}
                prev = e["entry_hash"]
        except (OSError, ValueError):
            return {"ok": False, "entries": n, "broken_at": n}
        return {"ok": True, "entries": n, "broken_at": None}

    # -- atomic json
    @staticmethod
    def _atomic_json(path, obj):
        data = json.dumps(obj, indent=1, ensure_ascii=False).encode("utf-8")
        tmp = path.with_name("%s.%d.tmp" % (path.name, os.getpid()))
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for _ in range(8):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                time.sleep(0.05)
        os.replace(tmp, path)

    # -- provisioning
    def provision(self):
        """Claim the space: create the vault folders, load (or start) the manifest, open the log. Safe to run again; it never touches what is already in the vault."""
        if not self.cfg.get("enabled", True):
            raise VaultError("the container is switched off in AXIS_VAULT_CONFIG (enabled = False)")
        self.emit("BOOT", "host=%s" % self.host)
        for d in (self.vault, self.files, self.versions):
            d.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                os.chmod(self.vault, 0o700)
            except OSError:
                pass
        if self.manifest_path.exists():
            try:
                loaded = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                if loaded.get("schema") != "axis.vault.manifest/1":
                    raise ValueError("unknown schema")
                self.manifest = loaded
            except (OSError, ValueError) as e:
                aside = self.manifest_path.with_name("vault_manifest.json.corrupt-%s" % time.strftime("%Y%m%d-%H%M%S"))
                os.replace(self.manifest_path, aside)         # never overwritten silently: kept for you to look at, then rebuilt from what is actually in the vault
                self.emit("MANIFEST_RESET", "manifest unreadable (%s); set aside as %s and rebuilt from the files" % (e, aside.name))
                self._rebuild_manifest()
        else:
            self._rebuild_manifest()
        self._save_manifest()
        self.provisioned = True
        self.emit("PROVISIONED", "vault=%s entries=%d" % (self.vault, len(self.manifest["entries"])))
        self.write_status()
        return {"host": str(self.host), "vault": str(self.vault), "entries": len(self.manifest["entries"])}

    def _rebuild_manifest(self):
        self.manifest["entries"] = {}
        for p in sorted(self.files.rglob("*")):
            if p.is_file():
                rel = p.relative_to(self.files).as_posix()
                self.manifest["entries"][rel] = {"sha256": sha256_file(p), "size": p.stat().st_size, "synced_at": now(), "versions": 0, "source_present": None}

    def _save_manifest(self):
        with LOCK:
            self._atomic_json(self.manifest_path, self.manifest)

    # -- what may be mirrored
    def _excluded(self, rel_parts, name):
        if any(fnmatch.fnmatch(name, pat) for pat in self.cfg["exclude_patterns"]):
            return True
        return any(part in self.cfg["exclude_dirs"] for part in rel_parts[:-1])

    def _confine(self, path):
        """-> (resolved path, relative posix path) or raises VaultError. The path must be a regular file inside the host, not in the vault, not a symlink, and not this script or its own log / status."""
        p = Path(path)
        if not p.is_absolute():
            p = self.host / p
        if p.is_symlink():
            raise VaultError("symlinks are not followed: %s" % p)
        r = p.resolve()
        if self.host not in r.parents:
            raise VaultError("outside the host folder: %s" % r)
        if self.vault == r or self.vault in r.parents:
            raise VaultError("that is inside the vault itself")
        if r in self.own or (r.parent == self.host and r.name in (self.cfg["log_file"], self.cfg["status_file"], self.script.name)):
            raise VaultError("that is the container's own bookkeeping")
        if not r.is_file():
            raise VaultError("not a regular file: %s" % r)
        return r, r.relative_to(self.host).as_posix()

    # -- the ingestion method
    def sync_file(self, path):
        """Drive a verified, byte-accurate copy of `path` into the vault (and each mirror_to folder). -> {"ok", "state", "path", "sha256", "bytes", ...}. Never raises for a file problem; reports it."""
        rel = str(path)
        try:
            src, rel = self._confine(path)
            if self._excluded(Path(rel).parts, src.name):
                return self._skip(rel, "excluded by pattern")
            st = src.stat()
            if getattr(st, "st_file_attributes", 0) & OFFLINE_ATTRS:
                return self._skip(rel, "cloud placeholder (online-only): reading it would download it; make it available offline first")
            if st.st_size > self.cfg["max_file_mb"] * 1024 * 1024:
                return self._skip(rel, "larger than max_file_mb (%s MB)" % self.cfg["max_file_mb"])
            if not self.provisioned:
                self.provision()
            with LOCK:
                res = self._store(src, rel)
            self.write_status()
            return res
        except VaultError as e:
            return self._skip(rel, str(e))
        except Exception as e:                                           # a file that vanishes, is locked, or a disk that fills must be reported, never crash the loop
            self.counters["failed"] += 1
            self.failing[rel] = str(e)
            self.last_error = "%s: %s" % (rel, e)
            self.emit("SYNC_FAILED", "%s: %s" % (rel, e), path=rel)
            self.write_status()
            return {"ok": False, "state": "failed", "path": rel, "error": str(e)}

    def _skip(self, rel, why):
        self.counters["skipped"] += 1
        self.emit("SYNC_SKIPPED", "%s (%s)" % (rel, why), path=rel)
        return {"ok": False, "state": "skipped", "path": rel, "reason": why}

    def _copy_verified(self, src, dest, expect_hash=None):
        """Copy src -> dest atomically with the whole verification chain. -> (sha256, bytes). Raises on any mismatch, leaving dest as it was."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".%d.part" % os.getpid())
        h_before = expect_hash or sha256_file(src)
        h_copy, n = hashlib.sha256(), 0
        try:
            with open(src, "rb") as fin, open(tmp, "wb") as fout:
                for chunk in iter(lambda: fin.read(CHUNK), b""):
                    h_copy.update(chunk)
                    fout.write(chunk)
                    n += len(chunk)
                fout.flush()
                os.fsync(fout.fileno())
            h_after = sha256_file(src)
            if not (h_before == h_copy.hexdigest() == h_after):
                raise IOError("the source changed while it was being copied (hash before %s, copied %s, after %s); nothing was stored, it will be retried" % (h_before[:8], h_copy.hexdigest()[:8], h_after[:8]))
            if self.cfg["verify_after_copy"] and sha256_file(tmp) != h_before:
                raise IOError("the copy did not read back identical; nothing was stored")
            try:
                shutil.copystat(src, tmp)
            except OSError:
                pass
            for _ in range(8):
                try:
                    os.replace(tmp, dest)
                    break
                except PermissionError:
                    time.sleep(0.05)
            else:
                os.replace(tmp, dest)
            return h_before, n
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _store(self, src, rel):
        dest = self.files / rel
        h = sha256_file(src)
        entry = self.manifest["entries"].get(rel)
        if dest.exists() and entry and entry.get("sha256") == h and sha256_file(dest) == h:
            entry["source_present"] = True
            self.counters["unchanged"] += 1
            self.emit("SYNC_UNCHANGED", "%s sha256=%s" % (rel, h[:12]), path=rel, sha256=h)
            return {"ok": True, "state": "unchanged", "path": rel, "sha256": h, "bytes": dest.stat().st_size}
        versions = entry.get("versions", 0) if entry else 0
        if dest.exists():                                                    # a changed file: the earlier version is kept, not overwritten
            old = sha256_file(dest)
            vdir = self.versions / rel
            vdir.parent.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            vpath = vdir.with_name("%s.%s.%s" % (vdir.name, stamp, old[:8]))
            n = 1
            while vpath.exists():
                n += 1
                vpath = vdir.with_name("%s.%s.%s-%d" % (vdir.name, stamp, old[:8], n))
            os.replace(dest, vpath)
            versions += 1
            self.counters["versions_kept"] += 1
            self._prune_versions(vdir)
        digest, size = self._copy_verified(src, dest, h)
        mirrors = {}
        for target in self.cfg["mirror_to"]:
            mirrors[str(target)] = self._mirror(Path(target), rel, dest, digest)
        self.failing.pop(rel, None)
        self.manifest["entries"][rel] = {"sha256": digest, "size": size, "synced_at": now(), "versions": versions, "source_present": True, "mirrors": mirrors}
        self._save_manifest()
        self.counters["synced"] += 1
        self.counters["bytes"] += size
        bad = [t for t, m in mirrors.items() if m != "ok"]
        self.emit("SYNC_OK", "%s %dB sha256=%s%s" % (rel, size, digest[:12], (" mirror problems: " + "; ".join("%s -> %s" % (t, mirrors[t]) for t in bad)) if bad else ""), path=rel, sha256=digest, bytes=size)
        if bad:
            self.last_error = "mirror problem for %s" % rel
        return {"ok": True, "state": "synced", "path": rel, "sha256": digest, "bytes": size, "versions": versions, "mirrors": mirrors}

    def _prune_versions(self, vdir):
        keep = self.cfg["keep_versions"]
        if keep <= 0:
            return
        found = sorted(vdir.parent.glob(vdir.name + ".*"), key=lambda p: p.stat().st_mtime)
        for old in found[:-keep]:
            try:
                old.unlink()
            except OSError:
                pass

    def _mirror(self, target, rel, primary_copy, digest):
        """A further verified copy (from the already-verified vault copy) into another existing folder's own vault. -> "ok" or the reason it failed."""
        try:
            if not target.is_dir():
                return "folder does not exist"
            troot = (target / self.cfg["vault_folder_name"] / "files").resolve()
            if self.vault.resolve() in troot.parents or troot == self.files.resolve():
                return "refused: a mirror cannot be inside this vault"
            dest = troot / rel
            if dest.exists() and sha256_file(dest) == digest:
                return "ok"
            self._copy_verified(primary_copy, dest, digest)
            return "ok"
        except Exception as e:
            return "failed: %s" % e

    # -- scanning and the live loop
    def iter_candidates(self):
        for dirpath, dirnames, filenames in os.walk(self.host, followlinks=False):
            dp = Path(dirpath)
            dirnames[:] = [d for d in dirnames if d not in self.cfg["exclude_dirs"] and (dp / d) != self.vault and not (dp / d).is_symlink()]
            for fn in filenames:
                p = dp / fn
                try:
                    rel = p.relative_to(self.host).as_posix()
                except ValueError:
                    continue
                if p.is_symlink() or p.resolve() in self.own or self._excluded(Path(rel).parts, fn):
                    continue
                yield p

    def _sig(self, p):
        st = p.stat()
        return (st.st_size, st.st_mtime_ns)

    def _remember(self, p, res):
        """Note which exact version of a file has been dealt with, so the loop does not redo it (or repeat a 'skipped' line) every poll. A failure is not remembered: it is retried."""
        if res["state"] in ("synced", "unchanged", "skipped"):
            try:
                self._known[str(p)] = self._sig(p)
            except OSError:
                pass

    def scan_once(self):
        """Mirror everything in the host that is not yet in the vault or has changed. -> [result, ...]."""
        if not self.provisioned:
            self.provision()
        results = []
        for p in list(self.iter_candidates()):
            res = self.sync_file(p)
            self._remember(p, res)
            results.append(res)
        self._note_removed()
        return results

    def _note_removed(self):
        present = {p.relative_to(self.host).as_posix() for p in self.iter_candidates()}
        changed = False
        for rel, e in self.manifest["entries"].items():
            if rel not in present and e.get("source_present") is not False:
                e["source_present"] = False
                changed = True
                self.emit("SOURCE_REMOVED", "%s is gone from the host; the vault keeps its copy" % rel, path=rel)
        if changed:
            self._save_manifest()

    def poll_once(self):
        """One pass of the live loop. A new or changed file is mirrored only after it has had the same size and time on two polls in a row, so a file still being written or downloaded is never copied half-done."""
        done, seen = [], set()
        for p in list(self.iter_candidates()):
            key = str(p)
            try:
                sig = self._sig(p)
            except OSError:
                continue
            seen.add(key)
            if self._known.get(key) == sig:
                self._pending.pop(key, None)
                continue
            if self._pending.get(key) == sig:
                res = self.sync_file(p)
                self._remember(p, res)
                self._pending.pop(key, None)
                done.append(res)
            else:
                self._pending[key] = sig
        for key in list(self._pending):
            if key not in seen:
                self._pending.pop(key, None)
        return done

    def watch(self, stop_event=None):
        """The live mirroring loop. Runs until stop_event is set (or Ctrl-C from the command line)."""
        stop = stop_event or self._stop
        if not self.provisioned:
            self.provision()
        self.emit("WATCHING", "every %ss; a file is copied once it has stopped changing" % self.cfg["poll_interval_seconds"])
        last_beat = 0.0
        while not stop.is_set():
            try:
                self.poll_once()
                if time.time() - last_beat >= self.cfg["heartbeat_seconds"]:
                    last_beat = time.time()
                    self._note_removed()
                    h = self.health()
                    self.emit("HEALTH", "%s synced=%d unchanged=%d skipped=%d failed=%d%s" % (h["state"], self.counters["synced"], self.counters["unchanged"], self.counters["skipped"], self.counters["failed"], (" last_error=" + self.last_error) if self.last_error else ""))
                    self.write_status()
            except Exception as e:
                self.last_error = "loop: %s" % e
                self.emit("LOOP_ERROR", str(e))
            stop.wait(self.cfg["poll_interval_seconds"])
        self.emit("SHUTDOWN", "watch loop stopped")
        self.write_status()

    def start_background(self):
        """Run the watch loop in a thread (for embedding in another process). -> the thread; call .stop() on the container to end it."""
        t = threading.Thread(target=self.watch, name="axis-vault-watch", daemon=True)
        t.start()
        return t

    def stop(self):
        self._stop.set()

    # -- integrity and health
    def verify(self):
        """Re-hash every vault copy against the manifest. -> {"ok", "checked", "missing": [...], "corrupt": [...]}. Corrupt copies are reported, never 'repaired' from a source that may itself have changed."""
        if not self.provisioned:
            self.provision()
        missing, corrupt, checked = [], [], 0
        for rel, e in self.manifest["entries"].items():
            p = self.files / rel
            checked += 1
            if not p.is_file():
                missing.append(rel)
            elif sha256_file(p) != e.get("sha256"):
                corrupt.append(rel)
        res = {"ok": not missing and not corrupt, "checked": checked, "missing": missing, "corrupt": corrupt, "log": self.verify_log()}
        res["ok"] = res["ok"] and res["log"]["ok"]
        self.last_verify = dict(res, at=now())
        self.emit("VERIFY_OK" if res["ok"] else "VERIFY_FAILED", "checked=%d missing=%d corrupt=%d log_chain=%s" % (checked, len(missing), len(corrupt), "ok" if res["log"]["ok"] else "BROKEN"))
        self.write_status()
        return res

    def health(self):
        """-> {"state": green|yellow|red, "reasons": [...]}. Red: the vault cannot be written or a verify failed. Yellow: something failed or was skipped lately, or a mirror folder has a problem."""
        reasons, state = [], "green"
        try:
            probe = self.vault / (".probe.%d" % os.getpid())
            probe.write_bytes(b"x")
            probe.unlink()
        except OSError as e:
            return {"state": "red", "reasons": ["the vault is not writable: %s" % e]}
        if self.last_verify and not self.last_verify["ok"]:
            state, reasons = "red", reasons + ["the last verify found problems"]
        if self.failing:
            state = "red" if state == "red" else "yellow"
            reasons.append("%d file(s) failing to sync: %s" % (len(self.failing), "; ".join("%s (%s)" % (k, v[:80]) for k, v in list(self.failing.items())[:3])))
        if self.counters["skipped"] and state == "green":
            state = "yellow"
            reasons.append("%d file(s) skipped (see the log)" % self.counters["skipped"])
        if self.last_error and "mirror" in self.last_error and state == "green":
            state = "yellow"
            reasons.append(self.last_error)
        return {"state": state, "reasons": reasons}

    def status(self):
        h = self.health()
        return {"container": "axis_vault_container", "host": str(self.host), "vault": str(self.vault), "provisioned": self.provisioned, "started_at": self.started_at, "updated_at": now(), "pid": os.getpid(),
                "health": h["state"], "health_reasons": h["reasons"], "counters": dict(self.counters), "entries": len(self.manifest["entries"]), "last_event": self.last_event, "last_error": self.last_error,
                "last_verify": self.last_verify, "mirror_to": [str(t) for t in self.cfg["mirror_to"]], "poll_interval_seconds": self.cfg["poll_interval_seconds"],
                "encryption": "none: this is isolation + verified copies + tamper evidence, not encryption or access control"}

    def write_status(self):
        try:
            self._atomic_json(self.status_path, self.status())
        except OSError as e:
            self.last_error = "status file not writable: %s" % e


def main(argv=None):
    ap = argparse.ArgumentParser(description="AXIS-CLOUD universal vault container")
    ap.add_argument("--once", action="store_true", help="provision, mirror what is there, exit")
    ap.add_argument("--sync", metavar="PATH", help="mirror one file now")
    ap.add_argument("--verify", action="store_true", help="re-hash every vault copy against the manifest")
    ap.add_argument("--status", action="store_true", help="print the current status file")
    ap.add_argument("--host", metavar="DIR", help="govern this folder instead of the one this file sits in")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    try:
        c = AxisVaultContainer(a.host, quiet=a.quiet)
    except (VaultError, ValueError) as e:
        print("[AXIS-VAULT] %s FATAL           %s" % (now(), e), file=sys.stderr)
        return 2
    if a.status:
        if c.status_path.exists():
            print(c.status_path.read_text(encoding="utf-8"))
            return 0
        print("[AXIS-VAULT] no status yet: run the container once", file=sys.stderr)
        return 1
    try:
        c.provision()
        if a.verify:
            return 0 if c.verify()["ok"] else 1
        if a.sync:
            return 0 if c.sync_file(a.sync)["ok"] else 1
        results = c.scan_once()
        bad = [r for r in results if r["state"] == "failed"]
        if a.once:
            c.emit("DONE", "scanned=%d synced=%d unchanged=%d skipped=%d failed=%d" % (len(results), c.counters["synced"], c.counters["unchanged"], c.counters["skipped"], c.counters["failed"]))
            c.write_status()
            return 1 if bad else 0
        try:
            c.watch()
        except KeyboardInterrupt:
            c.stop()
            c.emit("SHUTDOWN", "stopped by Ctrl-C")
            c.write_status()
        return 0
    except VaultError as e:
        print("[AXIS-VAULT] %s FATAL           %s" % (now(), e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
