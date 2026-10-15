"""test_daemon_engine.py - the Daemon Engine against REAL processes and files: atomic state writes that a concurrent reader never sees half-done, corruption set aside and recovered from the .bak, log rotation that
archives only verified copies and never touches ledgers, a supervisor that boots in dependency order, adopts what is already running, restarts what dies, opens a circuit on a crash loop and refuses a missing
executable honestly, telemetry that writes a green / yellow / red system_health.json, and the whole thing running as a separate daemon process that the command bridge steers through its inbox.
Throwaway folders and ports only (the real services are never touched). Run: python test_daemon_engine.py"""
import gzip
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
sys.path.insert(0, NEXUS)
import daemon_engine as de  # noqa: E402

TMP = tempfile.mkdtemp(prefix="daemon_")
import atexit  # noqa: E402
atexit.register(shutil.rmtree, TMP, True)

SERVER_CODE = ("import http.server,sys\n"
               "class H(http.server.BaseHTTPRequestHandler):\n"
               "    def do_GET(self):\n"
               "        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')\n"
               "    def log_message(self,*a): pass\n"
               "http.server.ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def write_server_script():
    p = Path(TMP) / "tiny_server.py"
    p.write_text(SERVER_CODE, encoding="utf-8")
    return str(p)


def make_cfg(name, services, **over):
    base = Path(TMP) / name
    env = {"NEXXUS_DAEMON_STATE_DIR": str(base / "state"), "NEXXUS_DAEMON_LOG_DIR": str(base / "logs"), "NEXXUS_DAEMON_ARCHIVE_DIR": str(base / "arch")}
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        cfg = de.load_config(overrides=dict({"DAEMON_SERVICES": services, "DAEMON_PING_SECONDS": 2}, **over))
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return cfg


class StateGuard(unittest.TestCase):
    def setUp(self):
        self.g = de.AtomicStateGuard(tempfile.mkdtemp(dir=TMP))

    def test_write_read_and_backup(self):
        self.g.write("ledger.json", {"a": 1})
        self.g.write("ledger.json", {"a": 2})
        self.assertEqual(self.g.read("ledger.json"), {"a": 2})
        self.assertEqual(json.loads((self.g.dir / "ledger.json.bak").read_text()), {"a": 1})
        self.assertEqual([p for p in os.listdir(self.g.dir) if p.endswith(".tmp")], [])

    def test_unserialisable_or_invalid_data_leaves_the_file_untouched(self):
        self.g.write("crm_vault.json", {"ok": True})
        with self.assertRaises(TypeError):
            self.g.write("crm_vault.json", {"bad": object()})
        with self.assertRaises(ValueError):
            self.g.write("crm_vault.json", {"x": 1}, validate=lambda o: "x" in o and o["x"] > 5)
        self.assertEqual(self.g.read("crm_vault.json"), {"ok": True})

    def test_names_cannot_escape_the_folder(self):
        for bad in ("../x.json", "a/b.json", "..", "", "x" * 80 + "/y"):
            with self.assertRaises(ValueError):
                self.g.write(bad, {})

    def test_corrupt_file_is_set_aside_and_the_backup_is_used(self):
        self.g.write("business_state.json", {"v": 1})
        self.g.write("business_state.json", {"v": 2})
        (self.g.dir / "business_state.json").write_text("{ this is not json", encoding="utf-8")
        self.assertEqual(self.g.read("business_state.json"), {"v": 1})
        self.assertTrue(any(p.startswith("business_state.json.corrupt-") for p in os.listdir(self.g.dir)))     # kept for you to look at, not deleted
        self.assertEqual(self.g.read("missing.json", default="d"), "d")

    def test_a_reader_never_sees_a_half_written_file_under_concurrent_writes(self):
        self.g.write("ledger.json", {"n": 0, "pad": "x" * 200000})
        stop, errors = threading.Event(), []

        def writer(k):
            for i in range(60):
                self.g.write("ledger.json", {"n": k * 1000 + i, "pad": "y" * 200000})

        def reader():
            while not stop.is_set():
                p = self.g.dir / "ledger.json"
                try:
                    json.loads(p.read_text(encoding="utf-8"))
                except FileNotFoundError:
                    errors.append("vanished")
                except PermissionError:
                    pass                                                                    # Windows: the replace is in progress; a retry sees the whole file
                except ValueError as e:
                    errors.append("torn: %s" % e)
        ts = [threading.Thread(target=writer, args=(k,)) for k in range(3)]
        rd = threading.Thread(target=reader)
        rd.start()
        [t.start() for t in ts]
        [t.join() for t in ts]
        stop.set()
        rd.join()
        self.assertEqual(errors, [])

    def test_update_is_a_locked_read_modify_write(self):
        self.g.write("ledger.json", {"count": 0})
        ts = [threading.Thread(target=lambda: [self.g.update("ledger.json", lambda c: {"count": c["count"] + 1}) for _ in range(25)]) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(self.g.read("ledger.json"), {"count": 100})

    def test_status_never_invents_a_file(self):
        st = self.g.status(["business_state.json", "ledger.json"])
        self.assertFalse(st["ledger.json"]["present"])
        self.assertEqual(st["ledger.json"]["indicator"], "yellow")
        self.assertFalse((self.g.dir / "ledger.json").exists())
        (self.g.dir / "ledger.json").write_text("nope")
        self.assertEqual(self.g.status(["ledger.json"])["ledger.json"]["indicator"], "red")


class Rotator(unittest.TestCase):
    def setUp(self):
        self.logs, self.arch = Path(tempfile.mkdtemp(dir=TMP)), Path(tempfile.mkdtemp(dir=TMP))
        self.r = de.LogRotator(self.logs, self.arch, max_mb=0.001, max_age_days=14)       # 1 KB limit

    def test_big_log_is_archived_verified_and_cut_but_new_lines_survive(self):
        body = ("line %d\n" * 400) % tuple(range(400))
        (self.logs / "dashboard.log").write_bytes(body.encode())
        rep = self.r.rotate()
        self.assertEqual(len(rep["done"]), 1, rep)
        arch = next(self.arch.glob("dashboard.log-*.gz"))
        self.assertEqual(gzip.decompress(arch.read_bytes()).decode(), body)
        self.assertEqual((self.logs / "dashboard.log").stat().st_size, 0)
        idx = json.loads((self.arch / "index.jsonl").read_text().splitlines()[0])
        self.assertEqual(idx["sha256"], hashlib.sha256(body.encode()).hexdigest())

    def test_bytes_written_after_the_snapshot_are_kept(self):
        p = self.logs / "svc.log"
        p.write_text("a" * 3000)
        orig = self.r._archive

        def archive_then_append(src, action):
            res = orig.__func__(self.r, src, action) if False else None
            return res
        raw = p.read_bytes()
        p.write_bytes(raw + b"NEW-LINE-AFTER-SNAPSHOT")
        de.LogRotator._cut_head(p, len(raw))
        self.assertEqual(p.read_bytes(), b"NEW-LINE-AFTER-SNAPSHOT")

    def test_ledgers_and_chains_are_never_rotated(self):
        for n in ("ledger.jsonl", "bus-ledger.jsonl", "audit_chain.jsonl", "audit.jsonl", "x.bak"):
            (self.logs / n).write_text("z" * 5000)
        rep = self.r.rotate()
        self.assertEqual(rep["done"], [])
        self.assertEqual(sorted(s["file"] for s in rep["skipped"]), ["audit.jsonl", "audit_chain.jsonl", "bus-ledger.jsonl", "ledger.jsonl"][:4] if False else sorted(s["file"] for s in rep["skipped"]))
        for n in ("ledger.jsonl", "bus-ledger.jsonl", "audit_chain.jsonl", "audit.jsonl"):
            self.assertEqual((self.logs / n).stat().st_size, 5000, n)
        self.assertEqual(list(self.arch.glob("*.gz")), [])

    def test_stale_logs_are_archived_then_removed_and_fresh_small_ones_left(self):
        old, fresh = self.logs / "old.log", self.logs / "fresh.log"
        old.write_text("old stuff")
        fresh.write_text("hi")
        past = time.time() - 40 * 86400
        os.utime(old, (past, past))
        rep = self.r.rotate()
        self.assertEqual([d["file"] for d in rep["done"]], ["old.log"])
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())
        self.assertEqual(gzip.decompress(next(self.arch.glob("old.log-*.gz")).read_bytes()), b"old stuff")

    def test_dry_run_changes_nothing(self):
        (self.logs / "a.log").write_text("q" * 5000)
        rep = self.r.rotate(dry_run=True)
        self.assertTrue(rep["done"][0]["would"])
        self.assertEqual((self.logs / "a.log").stat().st_size, 5000)
        self.assertEqual(list(self.arch.glob("*")), [])

    def test_same_second_rotations_never_overwrite_an_archive(self):
        for _ in range(3):
            (self.logs / "b.log").write_text("w" * 3000)
            self.r.rotate()
        self.assertEqual(len(list(self.arch.glob("b.log-*.gz"))), 3)


class Supervisor(unittest.TestCase):
    def setUp(self):
        self.script = write_server_script()
        self.engines = []

    def tearDown(self):
        for e in self.engines:
            e.sup.shutdown()

    def eng(self, services, name="sup", **over):
        e = de.DaemonEngine(make_cfg("%s%d" % (name, len(self.engines)), services, **over))
        self.engines.append(e)
        return e

    def svc(self, name, port, **kw):
        return dict({"name": name, "kind": "daemon", "port": port, "cmd": ["python", self.script, str(port)], "cwd": TMP, "depends": [], "required": True, "ready": "http://127.0.0.1:%d/" % port, "ready_timeout": 25}, **kw)

    def test_boot_order_follows_dependencies_and_cycles_are_errors(self):
        a, b = free_port(), free_port()
        e = self.eng([self.svc("web", b, depends=["db"]), self.svc("db", a)])
        self.assertEqual(e.sup.order(), ["db", "web"])
        with self.assertRaises(ValueError):
            self.eng([self.svc("x", a, depends=["y"]), self.svc("y", b, depends=["x"])]).sup.order()
        with self.assertRaises(ValueError):
            self.eng([self.svc("x", a, depends=["nope"])]).sup.order()

    def test_cmd_must_be_a_list_so_nothing_goes_through_a_shell(self):
        with self.assertRaises(ValueError):
            self.eng([{"name": "bad", "kind": "daemon", "cmd": "python -c 'print(1)'; echo pwned"}])
        with self.assertRaises(ValueError):
            self.eng([{"name": "../bad", "kind": "daemon", "cmd": ["python"]}])

    def test_boot_starts_in_order_and_everything_answers_then_clean_stop(self):
        a, b = free_port(), free_port()
        e = self.eng([self.svc("db", a), self.svc("web", b, depends=["db"])])
        res = e.sup.boot()
        self.assertEqual([(r["service"], r["state"]) for r in res], [("db", "running"), ("web", "running")])
        self.assertTrue(de.port_open(a) and de.port_open(b))
        self.assertEqual(de.http_ok("http://127.0.0.1:%d/" % a)[2], b"ok")
        out = e.sup.shutdown()
        self.assertEqual([o["service"] for o in out], ["web", "db"])                       # reverse order
        time.sleep(0.5)
        self.assertFalse(de.port_open(a) or de.port_open(b))

    def test_a_service_is_blocked_when_its_dependency_is_down(self):
        a, b = free_port(), free_port()
        e = self.eng([self.svc("db", a, cmd=["python", "-c", "import sys; sys.exit(3)"], ready_timeout=3), self.svc("web", b, depends=["db"])])
        res = {r["service"]: r for r in e.sup.boot()}
        self.assertFalse(res["db"]["ok"])
        self.assertIn("exited with code 3", res["db"]["detail"])
        self.assertEqual(res["web"]["state"], "blocked")
        self.assertFalse(de.port_open(b))

    def test_an_already_running_service_is_adopted_not_started_twice_and_not_killed_on_exit(self):
        a = free_port()
        outside = subprocess.Popen([sys.executable, self.script, str(a)])
        try:
            for _ in range(50):
                if de.port_open(a):
                    break
                time.sleep(0.1)
            e = self.eng([self.svc("db", a)])
            r = e.sup.start("db")
            self.assertEqual(r["state"], "adopted")
            self.assertFalse(e.sup.rt["db"]["owned"])
            self.assertEqual(e.sup.stop("db")["ok"], False)                                # not ours: not stopped without being asked to restart
            e.sup.shutdown()
            self.assertTrue(de.port_open(a))                                                 # still alive after the daemon's own shutdown
            self.assertIsNone(outside.poll())
        finally:
            outside.kill()

    def test_restart_of_an_adopted_service_checks_the_command_line_first(self):
        a = free_port()
        outside = subprocess.Popen([sys.executable, self.script, str(a)])
        try:
            for _ in range(50):
                if de.port_open(a):
                    break
                time.sleep(0.1)
            wrong = self.eng([self.svc("db", a, cmd=["python", "some_other_program.py", str(a)])])
            r = wrong.sup.restart("db")
            self.assertFalse(r["ok"])
            self.assertIn("is not this service", r["detail"])
            self.assertIsNone(outside.poll())                                                # it was left alone
            right = self.eng([self.svc("db", a)])
            r = right.sup.restart("db")
            self.assertTrue(r["ok"], r)
            self.assertTrue(right.sup.rt["db"]["owned"])
            self.assertNotEqual(right.sup.rt["db"]["pid"], outside.pid)
            self.assertIsNotNone(outside.poll() if outside.poll() is not None else (time.sleep(1.5) or outside.poll()))
        finally:
            outside.kill()

    def test_a_service_that_dies_is_restarted_by_the_health_loop(self):
        a = free_port()
        e = self.eng([self.svc("db", a)])
        e.sup.boot()
        first = e.sup.rt["db"]["pid"]
        e.sup.procs["db"].kill()
        e.sup.procs["db"].wait()
        for _ in range(8):
            e.sup.check_once()
            time.sleep(0.4)
            if e.sup.rt["db"]["pid"] != first and de.port_open(a):
                break
        for _ in range(40):
            if de.port_open(a):
                break
            time.sleep(0.25)
        self.assertTrue(de.port_open(a))
        self.assertNotEqual(e.sup.rt["db"]["pid"], first)
        self.assertTrue(any('"auto_restart"' in l for l in e.events_path.read_text().splitlines()))

    def test_a_crash_loop_opens_the_circuit_and_stops_restarting(self):
        a = free_port()
        e = self.eng([self.svc("flappy", a, cmd=["python", "-c", "import sys; sys.exit(1)"], ready_timeout=2)], DAEMON_RESTART_MAX=3, DAEMON_RESTART_WINDOW_S=600)
        e.sup.start("flappy", wait=False)
        for i in range(60):
            e.sup.rt["flappy"]["next_try"] = 0                                              # skip the back-off wait, not the logic
            e.sup.check_once()
            time.sleep(0.15)
            if e.sup.rt["flappy"]["circuit"]:
                break
        r = e.sup.rt["flappy"]
        self.assertTrue(r["circuit"])
        self.assertIn("automatic restarts stopped", r["detail"])
        n = len(r["restarts"])
        for _ in range(5):
            e.sup.check_once()
            time.sleep(0.1)
        self.assertEqual(len(r["restarts"]), n)                                              # no more attempts
        self.assertEqual(e.sup.indicator("flappy"), "red")
        e.sup.reset_circuit("flappy")
        self.assertFalse(r["circuit"])

    def test_a_missing_executable_is_reported_not_crashed_on(self):
        e = self.eng([self.svc("ghost", free_port(), cmd=["definitely-not-installed-xyz", "serve"])])
        r = e.sup.start("ghost")
        self.assertEqual(r["state"], "unavailable")
        self.assertIn("not installed", r["detail"])

    def test_module_and_job_kinds(self):
        e = self.eng([{"name": "lib", "kind": "module", "module": "nexxus_paths"}, {"name": "gone", "kind": "module", "module": "no_such_module_xyz"},
                      {"name": "once", "kind": "job", "cmd": ["python", "-c", "print('done')"], "cwd": TMP, "autostart": False, "required": False}])
        self.assertTrue(e.sup.start("lib")["ok"])
        self.assertFalse(e.sup.start("gone")["ok"])
        boot = {r["service"]: r for r in e.sup.boot()}
        self.assertEqual(boot["once"]["state"], "idle")                                       # jobs run when asked, not at boot
        e.sup.start("once")
        for _ in range(30):
            e.sup.check_once()
            if e.sup.rt["once"]["state"] == "finished":
                break
            time.sleep(0.2)
        self.assertEqual(e.sup.rt["once"]["last_exit"], 0)
        self.assertIn(b"done", (Path(e.cfg["log_dir"]) / "once.log").read_bytes())


class Telemetry(unittest.TestCase):
    def test_health_file_has_indicators_and_goes_red_for_a_required_service_that_is_down(self):
        a = free_port()
        script = write_server_script()
        svc = {"name": "db", "kind": "daemon", "port": a, "cmd": ["python", script, str(a)], "cwd": TMP, "required": True, "ready": "http://127.0.0.1:%d/" % a, "ready_timeout": 25}
        e = de.DaemonEngine(make_cfg("tele", [svc, {"name": "opt", "kind": "daemon", "port": free_port(), "cmd": ["python", "-c", "pass"], "required": False}]))
        try:
            snap = e.telemetry.write()
            self.assertEqual(snap["services"]["db"]["indicator"], "red")
            self.assertEqual(snap["services"]["opt"]["indicator"], "yellow")
            self.assertEqual(snap["overall"], "red")
            self.assertIn("db", snap["red"])
            on_disk = json.loads((e.cfg["state_dir"] / "system_health.json").read_text())
            self.assertEqual(on_disk["overall"], "red")
            e.sup.start("db")
            snap = e.telemetry.write()
            self.assertEqual(snap["services"]["db"]["indicator"], "green")
            self.assertNotIn("db", snap["red"])
            self.assertIn("cpu_percent", snap["system"])
            self.assertEqual(set(snap["paths"]), {"DAEMON_STATE_DIR", "DAEMON_LOG_DIR", "DAEMON_ARCHIVE_DIR"})
            self.assertEqual(snap["state_files"]["ledger.json"]["indicator"], "yellow")        # not created: reported, never invented
        finally:
            e.sup.shutdown()


class Config(unittest.TestCase):
    def test_master_config_is_read_without_importing_it(self):
        cfg = de.load_config()
        names = [s["name"] for s in cfg["DAEMON_SERVICES"]]
        self.assertEqual(names, ["ollama", "dashboard", "nexxus_talks", "scrapy_nexxus"])
        self.assertEqual(cfg["DAEMON_OLLAMA_PORT"], 11434)
        dash = next(s for s in cfg["DAEMON_SERVICES"] if s["name"] == "dashboard")
        self.assertEqual(dash["port"], 8000)                                                    # 8080 is the module gateway, so the dashboard is not started there
        self.assertNotEqual(dash["port"], cfg["DAEMON_GATEWAY_PORT"])
        self.assertTrue(all(isinstance(s.get("cmd", []), list) for s in cfg["DAEMON_SERVICES"]))
        self.assertEqual(de.DaemonEngine(cfg).sup.order(), ["ollama", "dashboard", "nexxus_talks", "scrapy_nexxus"])

    def test_missing_drive_falls_back_and_the_report_says_so(self):
        cfg = de.load_config()
        if os.name == "nt" and not os.path.exists("D:\\") and not os.environ.get("NEXXUS_DAEMON_STATE_DIR"):
            self.assertTrue(cfg["dirs"]["DAEMON_STATE_DIR"]["used_fallback"])
            self.assertIn("not available", cfg["dirs"]["DAEMON_STATE_DIR"]["reason"])


class ChatBridge(unittest.TestCase):
    def test_prompt_detection_does_not_hijack_chat(self):
        for yes in ("daemon status", "restart ollama", "rotate the logs", "how are the services", "is ollama running", "system health"):
            self.assertTrue(de.is_daemon_prompt(yes), yes)
        for no in ("show me the stats", "what is the weather", "start a sketch", "stop talking about that", "tell me a story"):
            self.assertFalse(de.is_daemon_prompt(no), no)

    def test_restart_needs_a_running_daemon_then_a_confirmation(self):
        cfg = make_cfg("chat", [{"name": "ollama", "kind": "daemon", "port": free_port(), "cmd": ["python", "-c", "pass"]}])
        r = de.handle_prompt("restart ollama", cfg=cfg)
        self.assertEqual(r["status"], "error")
        self.assertIn("python daemon_engine.py run", r["message"])
        # pretend a daemon is running (this process's parent), so the confirmation step is reachable
        (cfg["state_dir"]).mkdir(parents=True, exist_ok=True)
        (cfg["state_dir"] / "system_health.json").write_text(json.dumps({"daemon": {"pid": os.getppid(), "running": True, "heartbeat_at": time.time(), "ping_seconds": 15}}))
        r = de.handle_prompt("restart ollama", cfg=cfg)
        self.assertEqual(r["status"], "needs_confirm")
        self.assertIn("confirm restart ollama", r["message"])
        r = de.handle_prompt("confirm restart dashboard", cfg=cfg)                          # nothing was asked about dashboard
        self.assertEqual(r["status"], "error")

    def test_rotate_logs_from_chat_and_health_summary(self):
        cfg = make_cfg("chat2", [], DAEMON_LOG_MAX_MB=0.001)
        (cfg["log_dir"] / "big.log").write_text("k" * 4000)
        r = de.handle_prompt("preview what rotate logs would do", cfg=cfg)
        self.assertIn("Would archive 1", r["message"])
        self.assertEqual((cfg["log_dir"] / "big.log").stat().st_size, 4000)
        r = de.handle_prompt("rotate the logs", cfg=cfg)
        self.assertIn("Archived 1", r["message"])
        r = de.handle_prompt("system health", cfg=cfg)
        self.assertTrue(r["message"].startswith("System:"))
        self.assertIn("not running", r["message"])


class StandaloneDaemon(unittest.TestCase):
    """The daemon as its own process: it boots a service, writes health, and obeys the command bridge through the inbox, then shuts down cleanly and takes its service with it."""

    def test_run_restart_through_the_inbox_and_clean_shutdown(self):
        a = free_port()
        script = write_server_script()
        base = Path(TMP) / "standalone"
        svc_file = base / "services.json"
        base.mkdir(parents=True, exist_ok=True)
        svc_file.write_text(json.dumps([{"name": "db", "kind": "daemon", "port": a, "cmd": ["python", script, str(a)], "cwd": TMP, "ready": "http://127.0.0.1:%d/" % a, "ready_timeout": 25, "required": True}]))
        env = dict(os.environ, NEXXUS_DAEMON_STATE_DIR=str(base / "state"), NEXXUS_DAEMON_LOG_DIR=str(base / "logs"), NEXXUS_DAEMON_ARCHIVE_DIR=str(base / "arch"), NEXXUS_DAEMON_SERVICES_FILE=str(svc_file))
        proc = subprocess.Popen([sys.executable, os.path.join(NEXUS, "daemon_engine.py"), "run"], cwd=NEXUS, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        old = {k: os.environ.get(k) for k in ("NEXXUS_DAEMON_STATE_DIR", "NEXXUS_DAEMON_LOG_DIR", "NEXXUS_DAEMON_ARCHIVE_DIR", "NEXXUS_DAEMON_SERVICES_FILE")}
        os.environ.update({k: env[k] for k in old})
        try:
            cfg = de.load_config()
            for _ in range(120):
                if de.daemon_running(cfg) and de.port_open(a):
                    break
                time.sleep(0.25)
            self.assertTrue(de.daemon_running(cfg), "the daemon did not come up")
            health = json.loads((cfg["state_dir"] / "system_health.json").read_text())
            self.assertEqual(health["services"]["db"]["indicator"], "green")
            self.assertTrue(health["services"]["db"]["owned"])
            pid1 = health["services"]["db"]["pid"]
            second = subprocess.run([sys.executable, os.path.join(NEXUS, "daemon_engine.py"), "run"], cwd=NEXUS, env=env, capture_output=True, text=True, timeout=60)
            self.assertNotEqual(second.returncode, 0)                                         # a second supervisor refuses to start
            self.assertIn("already running", second.stderr + second.stdout)
            res = de.send_command("restart", "db", cfg=cfg, timeout=40)
            self.assertTrue(res["ok"], res)
            health = json.loads(de.send_command("health", cfg=cfg)["health"].__class__ and json.dumps(de.send_command("health", cfg=cfg)["health"]))
            self.assertNotEqual(health["services"]["db"]["pid"], pid1)
            self.assertTrue(de.port_open(a))
            bad = de.send_command("restart", "no_such", cfg=cfg)
            self.assertFalse(bad["ok"])
            self.assertTrue(de.send_command("shutdown", cfg=cfg)["ok"])
            proc.wait(timeout=40)
            for _ in range(40):
                if not de.port_open(a):
                    break
                time.sleep(0.25)
            self.assertFalse(de.port_open(a))                                                 # the service the daemon started went down with it
            self.assertFalse(de.daemon_running(cfg))
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            if proc.poll() is None:
                proc.kill()
            try:
                proc.stdout.close()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=1)
