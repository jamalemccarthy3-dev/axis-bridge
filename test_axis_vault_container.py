"""test_axis_vault_container.py - the AXIS-CLOUD vault container as a real drop-in: the single file is copied into a fresh folder and run there, it provisions its vault and log, mirrors files with a verified
byte-accurate copy (including files larger than its read chunk), keeps earlier versions instead of overwriting, refuses anything outside the folder / inside the vault / symlinked, never copies a file that changed
while it was being copied, waits for a file to stop changing in the live loop, never deletes from the vault when a source disappears, detects corruption and a tampered activity log, reports clear terminal states and
a status file, and mirrors to extra folders. Run: python test_axis_vault_container.py"""
import atexit
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = os.path.dirname(os.path.abspath(__file__))
CLOUD = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "axis-cloud")
SCRIPT = os.path.join(CLOUD, "axis_vault_container.py")
TMP = tempfile.mkdtemp(prefix="vault_")
atexit.register(shutil.rmtree, TMP, True)
sys.path.insert(0, CLOUD)
import axis_vault_container as avc  # noqa: E402

_n = [0]


def host(files=None):
    """A fresh governed folder with the container file dropped into it."""
    _n[0] += 1
    d = Path(TMP) / ("host%d" % _n[0])
    d.mkdir()
    shutil.copy(SCRIPT, d / "axis_vault_container.py")
    for rel, data in (files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode())
    return d


def box(d, **cfg):
    return avc.AxisVaultContainer(d, config=avc.load_config(d, dict(cfg)), quiet=True)


def sha(b):
    return hashlib.sha256(b).hexdigest()


class DropIn(unittest.TestCase):
    def test_running_the_dropped_file_provisions_everything(self):
        d = host({"report.txt": "quarterly numbers", "deep/er/notes.md": "# notes"})
        r = subprocess.run([sys.executable, str(d / "axis_vault_container.py"), "--once"], cwd=str(d), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((d / "AXIS_SECURE_VAULT" / "files" / "report.txt").is_file())
        self.assertEqual((d / "AXIS_SECURE_VAULT" / "files" / "deep" / "er" / "notes.md").read_text(), "# notes")
        for f in ("vault_activity.log", "vault_status.json", "AXIS_SECURE_VAULT/vault_manifest.json"):
            self.assertTrue((d / f).is_file(), f)
        self.assertFalse((d / "AXIS_SECURE_VAULT" / "files" / "axis_vault_container.py").exists())     # it never mirrors itself, its log, its status or its vault
        self.assertFalse((d / "AXIS_SECURE_VAULT" / "files" / "vault_activity.log").exists())
        out = r.stdout
        for state in ("BOOT", "PROVISIONED", "SYNC_OK", "DONE"):
            self.assertIn("[AXIS-VAULT]", out)
            self.assertIn(state, out)

    def test_it_governs_whatever_folder_it_is_in_without_configuration(self):
        a, b = host({"x.txt": "1"}), host({"y.txt": "2"})
        for d in (a, b):
            subprocess.run([sys.executable, str(d / "axis_vault_container.py"), "--once", "--quiet"], cwd=str(d), check=True, timeout=60)
        self.assertTrue((a / "AXIS_SECURE_VAULT" / "files" / "x.txt").is_file())
        self.assertFalse((a / "AXIS_SECURE_VAULT" / "files" / "y.txt").exists())
        self.assertTrue((b / "AXIS_SECURE_VAULT" / "files" / "y.txt").is_file())

    def test_provisioning_twice_changes_nothing_in_the_vault(self):
        d = host({"a.txt": "keep me"})
        c = box(d)
        c.scan_once()
        before = sha((d / "AXIS_SECURE_VAULT" / "files" / "a.txt").read_bytes())
        c2 = box(d)
        c2.provision()
        self.assertEqual(len(c2.manifest["entries"]), 1)
        res = c2.scan_once()
        self.assertEqual([r["state"] for r in res], ["unchanged"])
        self.assertEqual(sha((d / "AXIS_SECURE_VAULT" / "files" / "a.txt").read_bytes()), before)

    def test_status_command_and_failure_exit_codes(self):
        d = host({"a.txt": "1"})
        st = lambda *a: subprocess.run([sys.executable, str(d / "axis_vault_container.py"), *a], cwd=str(d), capture_output=True, text=True, timeout=60)
        self.assertEqual(st("--status").returncode, 1)                                                  # nothing has run yet: says so, does not invent a status
        self.assertEqual(st("--once", "--quiet").returncode, 0)
        s = json.loads(st("--status").stdout)
        self.assertEqual((s["health"], s["entries"]), ("green", 1))
        self.assertIn("not encryption", s["encryption"])
        outside = Path(TMP) / "outside.txt"
        outside.write_text("nope")
        self.assertEqual(st("--sync", str(outside)).returncode, 1)
        self.assertEqual(st("--sync", "a.txt").returncode, 0)
        self.assertEqual(st("--verify").returncode, 0)
        self.assertEqual(subprocess.run([sys.executable, str(d / "axis_vault_container.py"), "--host", str(d / "nope")], capture_output=True, text=True, timeout=60).returncode, 2)


class Mirroring(unittest.TestCase):
    def test_copies_are_byte_accurate_including_binary_and_large_files(self):
        big = os.urandom(avc.CHUNK * 2 + 12345)
        d = host({"blob.bin": big, "empty.dat": b"", "unicode éè.txt": "café"})
        c = box(d)
        res = {r["path"]: r for r in c.scan_once()}
        self.assertTrue(all(r["ok"] for r in res.values()), res)
        self.assertEqual((d / "AXIS_SECURE_VAULT" / "files" / "blob.bin").read_bytes(), big)
        self.assertEqual(res["blob.bin"]["sha256"], sha(big))
        self.assertEqual((d / "AXIS_SECURE_VAULT" / "files" / "empty.dat").read_bytes(), b"")
        self.assertEqual((d / "AXIS_SECURE_VAULT" / "files" / "unicode éè.txt").read_text(encoding="utf-8"), "café")
        self.assertEqual(c.manifest["entries"]["blob.bin"]["sha256"], sha(big))
        self.assertEqual([p.name for p in (d / "AXIS_SECURE_VAULT" / "files").iterdir() if p.name.endswith(".part")], [])

    def test_a_changed_file_keeps_its_earlier_version_instead_of_overwriting(self):
        d = host({"doc.txt": "version one"})
        c = box(d)
        c.sync_file("doc.txt")
        (d / "doc.txt").write_text("version two")
        r = c.sync_file("doc.txt")
        self.assertEqual((r["state"], r["versions"]), ("synced", 1))
        self.assertEqual((d / "AXIS_SECURE_VAULT" / "files" / "doc.txt").read_text(), "version two")
        old = list((d / "AXIS_SECURE_VAULT" / "_versions").glob("doc.txt.*"))
        self.assertEqual(len(old), 1)
        self.assertEqual(old[0].read_text(), "version one")
        (d / "doc.txt").write_text("version three")
        c.sync_file("doc.txt")
        self.assertEqual(len(list((d / "AXIS_SECURE_VAULT" / "_versions").glob("doc.txt.*"))), 2)
        self.assertEqual(c.manifest["entries"]["doc.txt"]["versions"], 2)

    def test_keep_versions_prunes_only_when_asked(self):
        d = host({"d.txt": "0"})
        c = box(d, keep_versions=2)
        for i in range(1, 6):
            c.sync_file("d.txt")
            (d / "d.txt").write_text("v%d" % i)
        c.sync_file("d.txt")
        self.assertEqual(len(list((d / "AXIS_SECURE_VAULT" / "_versions").glob("d.txt.*"))), 2)
        d2 = host({"d.txt": "0"})
        c2 = box(d2)
        for i in range(1, 6):
            c2.sync_file("d.txt")
            (d2 / "d.txt").write_text("v%d" % i)
        c2.sync_file("d.txt")
        self.assertEqual(len(list((d2 / "AXIS_SECURE_VAULT" / "_versions").glob("d.txt.*"))), 5)         # default: nothing is ever thrown away

    def test_a_file_that_changes_mid_copy_is_not_stored_and_leaves_no_debris(self):
        d = host({"live.log": "x" * 5000})
        c = box(d)
        real, calls = avc.sha256_file, []

        def shifting(path):
            calls.append(path)
            h = real(path)
            return h if len(calls) < 2 else "0" * 64                                                       # the source "changes" between the first hash and the check after copying
        avc.sha256_file = shifting
        try:
            r = c.sync_file("live.log")
        finally:
            avc.sha256_file = real
        self.assertFalse(r["ok"])
        self.assertEqual(r["state"], "failed")
        self.assertIn("changed while it was being copied", r["error"])
        self.assertFalse((d / "AXIS_SECURE_VAULT" / "files" / "live.log").exists())
        self.assertEqual([p.name for p in (d / "AXIS_SECURE_VAULT" / "files").iterdir()], [])
        self.assertEqual(c.counters["failed"], 1)
        self.assertEqual(c.health()["state"], "yellow")                                                      # failing right now: reported
        self.assertTrue(c.sync_file("live.log")["ok"])                                                      # retried when it settles
        self.assertEqual(c.health()["state"], "green")                                                      # and the warning clears once the retry succeeds

    def test_read_back_verification_catches_a_bad_write(self):
        d = host({"f.txt": "payload"})
        c = box(d)
        c.provision()
        real_verify, seen = avc.sha256_file, []

        def bad_readback(path):
            seen.append(str(path))
            return "f" * 64 if str(path).endswith(".part") else real_verify(path)
        avc.sha256_file = bad_readback
        try:
            r = c.sync_file("f.txt")
        finally:
            avc.sha256_file = real_verify
        self.assertEqual(r["state"], "failed")
        self.assertIn("read back", r["error"])
        self.assertFalse((d / "AXIS_SECURE_VAULT" / "files" / "f.txt").exists())


class Confinement(unittest.TestCase):
    def test_nothing_outside_the_host_or_inside_the_vault_or_its_own_bookkeeping(self):
        d = host({"ok.txt": "fine"})
        c = box(d)
        c.provision()
        outside = Path(TMP) / "secret_outside.txt"
        outside.write_text("do not copy")
        for bad in (str(outside), str(d / ".." / "secret_outside.txt"), str(d / "AXIS_SECURE_VAULT" / "vault_manifest.json"), str(d / "vault_activity.log"), str(d / "vault_status.json"),
                    str(d / "axis_vault_container.py"), str(d / "nope.txt"), str(d)):
            r = c.sync_file(bad)
            self.assertFalse(r["ok"], bad)
            self.assertEqual(r["state"], "skipped", bad)
        self.assertEqual(list((d / "AXIS_SECURE_VAULT" / "files").iterdir()), [])
        self.assertTrue(c.sync_file("ok.txt")["ok"])

    def test_symlinks_are_not_followed(self):
        d = host({"real.txt": "real"})
        target = Path(TMP) / "linked_target.txt"
        target.write_text("outside")
        link = d / "link.txt"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks need privileges on this machine")
        c = box(d)
        r = c.sync_file("link.txt")
        self.assertEqual(r["state"], "skipped")
        self.assertIn("symlink", r["reason"])
        self.assertEqual([x["path"] for x in c.scan_once() if x["state"] == "synced"], ["real.txt"])

    def test_excluded_patterns_dirs_and_oversize_are_skipped_and_reported(self):
        d = host({"a.tmp": "t", "~$lock.docx": "t", "keep.txt": "k", ".git/config": "g", "node_modules/x.js": "j", "big.bin": b"z" * 3000})
        c = box(d, max_file_mb=0.001)
        results = c.scan_once()
        stored = sorted(p.relative_to(d / "AXIS_SECURE_VAULT" / "files").as_posix() for p in (d / "AXIS_SECURE_VAULT" / "files").rglob("*") if p.is_file())
        self.assertEqual(stored, ["keep.txt"])
        big = [r for r in results if r["path"] == "big.bin"][0]
        self.assertEqual(big["state"], "skipped")
        self.assertIn("max_file_mb", big["reason"])
        self.assertEqual(c.health()["state"], "yellow")                                                      # skipped files are reported, not hidden


class LiveLoop(unittest.TestCase):
    def test_a_file_is_copied_only_after_it_stops_changing(self):
        d = host()
        c = box(d)
        c.provision()
        p = d / "download.bin"
        p.write_bytes(b"part1")
        self.assertEqual(c.poll_once(), [])                                                                   # first sight: pending
        p.write_bytes(b"part1part2")                                                                          # still being written
        self.assertEqual(c.poll_once(), [])
        done = c.poll_once()                                                                                   # unchanged for a full poll: now it is mirrored
        self.assertEqual([r["state"] for r in done], ["synced"])
        self.assertEqual((d / "AXIS_SECURE_VAULT" / "files" / "download.bin").read_bytes(), b"part1part2")
        self.assertEqual(c.poll_once(), [])                                                                   # nothing further to do
        time.sleep(0.02)
        p.write_bytes(b"part1part2part3")
        c.poll_once()
        self.assertEqual([r["state"] for r in c.poll_once()], ["synced"])
        self.assertEqual(c.manifest["entries"]["download.bin"]["versions"], 1)

    def test_a_removed_source_never_removes_the_vault_copy(self):
        d = host({"gone.txt": "precious"})
        c = box(d)
        c.scan_once()
        (d / "gone.txt").unlink()
        c.scan_once()
        self.assertEqual((d / "AXIS_SECURE_VAULT" / "files" / "gone.txt").read_text(), "precious")
        self.assertIs(c.manifest["entries"]["gone.txt"]["source_present"], False)
        self.assertIn("SOURCE_REMOVED", (d / "vault_activity.log").read_text())

    def test_the_watch_loop_runs_in_a_thread_mirrors_and_stops_cleanly(self):
        d = host({"first.txt": "1"})
        c = box(d, poll_interval_seconds=0.2, heartbeat_seconds=1)
        t = c.start_background()
        try:
            for _ in range(60):
                if (d / "AXIS_SECURE_VAULT" / "files" / "first.txt").exists():
                    break
                time.sleep(0.1)
            (d / "later.txt").write_text("2")
            for _ in range(80):
                if (d / "AXIS_SECURE_VAULT" / "files" / "later.txt").exists():
                    break
                time.sleep(0.1)
            self.assertEqual((d / "AXIS_SECURE_VAULT" / "files" / "later.txt").read_text(), "2")
            time.sleep(1.3)
            s = json.loads((d / "vault_status.json").read_text())
            self.assertEqual(s["health"], "green")
            self.assertGreaterEqual(s["counters"]["synced"], 2)
            self.assertIn("HEALTH", (d / "vault_activity.log").read_text())
        finally:
            c.stop()
            t.join(5)
        self.assertFalse(t.is_alive())
        self.assertIn("SHUTDOWN", (d / "vault_activity.log").read_text())


class Integrity(unittest.TestCase):
    def test_verify_finds_corruption_and_missing_copies_and_never_repairs_silently(self):
        d = host({"a.txt": "alpha", "b.txt": "beta", "c.txt": "gamma"})
        c = box(d)
        c.scan_once()
        self.assertTrue(c.verify()["ok"])
        (d / "AXIS_SECURE_VAULT" / "files" / "a.txt").write_text("tampered")
        (d / "AXIS_SECURE_VAULT" / "files" / "b.txt").unlink()
        v = c.verify()
        self.assertFalse(v["ok"])
        self.assertEqual((v["corrupt"], v["missing"]), (["a.txt"], ["b.txt"]))
        self.assertEqual((d / "AXIS_SECURE_VAULT" / "files" / "a.txt").read_text(), "tampered")              # reported, not 'fixed' from a source that might itself have changed
        self.assertEqual(c.health()["state"], "red")

    def test_the_activity_log_is_hash_chained_and_an_edit_is_found(self):
        d = host({"a.txt": "1", "b.txt": "2"})
        c = box(d)
        c.scan_once()
        n = c.verify_log()
        self.assertTrue(n["ok"])
        self.assertGreaterEqual(n["entries"], 4)
        lines = (d / "vault_activity.log").read_text().splitlines()
        lines[2] = lines[2].replace("SYNC_OK", "SYNC_FAILED") if "SYNC_OK" in lines[2] else lines[2].replace("PROVISIONED", "BOOT")
        (d / "vault_activity.log").write_text("\n".join(lines) + "\n")
        self.assertFalse(c.verify_log()["ok"])
        self.assertFalse(c.verify()["ok"])                                                                      # verify includes the log chain

    def test_the_chain_continues_after_a_restart(self):
        d = host({"a.txt": "1"})
        box(d).scan_once()
        c2 = box(d)
        c2.provision()
        (d / "b.txt").write_text("2")
        c2.sync_file("b.txt")
        self.assertTrue(c2.verify_log()["ok"])

    def test_a_corrupt_manifest_is_set_aside_and_rebuilt_from_the_files(self):
        d = host({"a.txt": "alpha"})
        box(d).scan_once()
        (d / "AXIS_SECURE_VAULT" / "vault_manifest.json").write_text("{ broken")
        c = box(d)
        c.provision()
        self.assertTrue(any(p.name.startswith("vault_manifest.json.corrupt-") for p in (d / "AXIS_SECURE_VAULT").iterdir()))
        self.assertEqual(c.manifest["entries"]["a.txt"]["sha256"], sha(b"alpha"))
        self.assertTrue(c.verify()["ok"])


class Mirrors(unittest.TestCase):
    def test_extra_folders_get_their_own_verified_copy(self):
        d = host({"a.txt": "alpha", "sub/b.txt": "beta"})
        other = Path(TMP) / ("mirror%d" % _n[0])
        other.mkdir()
        c = box(d, mirror_to=[str(other)])
        res = c.scan_once()
        self.assertTrue(all(r["mirrors"][str(other)] == "ok" for r in res if r["state"] == "synced"))
        self.assertEqual((other / "AXIS_SECURE_VAULT" / "files" / "sub" / "b.txt").read_text(), "beta")
        self.assertEqual(c.health()["state"], "green")

    def test_a_missing_mirror_folder_is_reported_and_the_primary_still_succeeds(self):
        d = host({"a.txt": "alpha"})
        c = box(d, mirror_to=[str(Path(TMP) / "does_not_exist")])
        r = c.scan_once()[0]
        self.assertTrue(r["ok"])
        self.assertIn("does not exist", list(r["mirrors"].values())[0])
        self.assertEqual(c.health()["state"], "yellow")
        self.assertFalse((Path(TMP) / "does_not_exist").exists())                                              # it never creates a drive or an arbitrary folder

    def test_a_mirror_cannot_point_inside_the_vault(self):
        d = host({"a.txt": "alpha"})
        c = box(d, mirror_to=[str(d / "AXIS_SECURE_VAULT" / "files")])
        r = c.scan_once()[0]
        self.assertIn("refused", list(r["mirrors"].values())[0])


class Config(unittest.TestCase):
    def test_axis_vault_config_is_registered_in_master_config_and_read_without_importing_it(self):
        import ast
        tree = ast.parse(Path(CLOUD, "master_config.py").read_text(encoding="utf-8"))
        lit = [ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "AXIS_VAULT_CONFIG" for t in n.targets)][0]
        cfg = avc.load_config(Path(TMP))
        for k, v in lit.items():
            self.assertEqual(cfg[k], v, k)
        self.assertEqual(cfg["vault_folder_name"], "AXIS_SECURE_VAULT")
        self.assertEqual(cfg["log_file"], "vault_activity.log")
        self.assertNotIn("master_config", sys.modules)
        self.assertIn("vault_container", Path(CLOUD, "master_config.py").read_text(encoding="utf-8"))

    def test_bad_settings_are_rejected_loudly(self):
        for bad in ({"poll_interval_seconds": "fast"}, {"mirror_to": "x"}, {"vault_folder_name": "../escape"}, {"vault_folder_name": ""}, {"log_file": "a/b.log"}, {"verify_after_copy": 1}):
            with self.assertRaises(ValueError, msg=str(bad)):
                avc.load_config(Path(TMP), bad)

    def test_disabled_container_refuses_to_run(self):
        d = host({"a.txt": "1"})
        c = avc.AxisVaultContainer(d, config=avc.load_config(d, {"enabled": False}), quiet=True)
        with self.assertRaises(avc.VaultError):
            c.provision()
        self.assertFalse((d / "AXIS_SECURE_VAULT").exists())


class Telemetry(unittest.TestCase):
    def test_terminal_states_are_clear_and_greppable(self):
        d = host({"a.txt": "1", "x.tmp": "t"})
        c = avc.AxisVaultContainer(d, config=avc.load_config(d), quiet=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            c.scan_once()
            c.scan_once()
            c.verify()
        lines = [l for l in buf.getvalue().splitlines() if l.startswith("[AXIS-VAULT]")]
        states = [l.split()[3] for l in lines]
        self.assertEqual(states[:3], ["BOOT", "PROVISIONED", "SYNC_OK"])
        self.assertIn("SYNC_UNCHANGED", states)
        self.assertIn("VERIFY_OK", states)
        self.assertTrue(all(len(l.split()) >= 4 for l in lines))

    def test_status_file_tracks_health_and_counters_atomically(self):
        d = host({"a.txt": "1", "b.txt": "22"})
        c = box(d)
        c.scan_once()
        s = json.loads((d / "vault_status.json").read_text())
        self.assertEqual((s["health"], s["counters"]["synced"], s["counters"]["bytes"], s["entries"]), ("green", 2, 3, 2))
        self.assertEqual(s["last_event"]["state"], "SYNC_OK")
        self.assertEqual([p.name for p in d.iterdir() if p.name.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
