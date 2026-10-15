#!/usr/bin/env python3
"""engine_checklist.py - the A+ gate: eight checks every engine (or module, or dashboard component) must pass before it counts as done.

    python engine_checklist.py axis-vision                 one engine, non-destructive (items 3 and 4 say NOT RUN)
    python engine_checklist.py axis-vision --stop-test     also closes its ENGINE window, times the dashboard flip, checks the others kept running, then relaunches it
    python engine_checklist.py --all                       every engine in the roster, non-destructive
    python engine_checklist.py --file path\\to\\new_engine.py --name my-engine     a NEW engine that is not on the roster yet (items 1, 2, 5, 6 on the file; 7 fails until it is on the roster)

The nine items (see QUALITY_CHECKLIST.md):
  1 real health check         it tests what the component depends on, not a hard-coded ok
  2 failure tested            hub down / secret missing / a dependency missing: it fails safely with a plain message
  3 isolation                 stop it and the rest keep running                       (needs --stop-test to be proven; otherwise NOT RUN)
  4 visible state             the dashboard shows it LIVE, then stale/down within a known time (needs --stop-test to be measured)
  5 handles messages          `message` is received and kept (inbox), `ping` answers, unknown instructions are refused, and a message relayed through the hub is acknowledged
  6 no leaks                  no paths, tracebacks, keys or exception text in anything it says; the secret comes from the environment only
  7 part of the cluster       it is on the roster, live, in the rolled-up engine cluster with no dead process or unreferenced folder, and the dashboard audit has no orphans (engines need no card of their own)
  8 evidence on file          a test, a dated raw log (this run writes it), and a commit (BLOCKED while commits are on hold)
  9 tests leave nothing       this run adds no files to the engine's folder, none to logs\\ except its own raw log, and no rows to the hub's message log (checked before and after)
Statuses: PASS | FAIL | NOT RUN (the run did not exercise it) | BLOCKED (cannot be satisfied right now, with the reason). Only nine PASS is an A+.
Every run writes the raw output to logs\\engine_checklist_<engine>_<date>.txt.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SILO = ROOT / "axis-ui-interface" / "project-X" / "silo_vault"
LOGS = ROOT / "logs"
HUB = os.environ.get("NEXXUS_MESH_URL", "http://127.0.0.1:8000").replace("//localhost", "//127.0.0.1").rstrip("/")
LEAKS = [(r"[A-Za-z]:[\\/]", "a file path"), (r"Traceback", "a traceback"), (r'File "', "a stack frame"), (r"NEXXUS_GOVERNANCE_SECRET", "the secret's variable name"),
         (r"AIza[0-9A-Za-z_\-]{20,}", "a Google key"), (r"\bsk-[A-Za-z0-9]{16,}", "an API key"), (r"\b[A-Fa-f0-9]{48,}\b", "a long hex token")]
LINES = []


def out(s=""):
    print(s, flush=True)
    LINES.append(s)


def hub_get(path, timeout=20):
    with urllib.request.urlopen(HUB + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ask(entry, req, env=None, timeout=60):
    """Run the engine's entry file the way the hub does: python file --mesh, JSON on stdin, JSON on stdout. -> (result dict, seconds, exit code)."""
    import tempfile
    e = dict(os.environ, PYTHONPATH=str(ROOT), NEXXUS_ENGINE_INBOX=os.path.join(tempfile.gettempdir(), "nexxus_checklist_inbox_%s.json" % entry.parent.name))     # test messages never land in the real engine folder
    e.update(env or {})
    t = time.time()
    r = subprocess.run([sys.executable, entry.name, "--mesh"], cwd=str(entry.parent), input=json.dumps(req).encode(), capture_output=True, env=e, timeout=timeout)
    txt = r.stdout.decode().strip().splitlines()
    try:
        res = json.loads(txt[-1])["result"]
    except (IndexError, ValueError, KeyError):
        res = {"__no_json__": (r.stderr.decode()[-200:] or "no output")}
    return res, time.time() - t, r.returncode


def pick_free_dead_url():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return "http://127.0.0.1:%d" % p


def scan_leaks(label, obj, secret):
    text = json.dumps(obj)
    found = []
    for rx, what in LEAKS:
        if re.search(rx, text):
            found.append(what)
    if secret and len(secret) >= 8 and secret in text:
        found.append("the signing secret itself")
    return ["%s contains %s" % (label, w) for w in found]


class Checklist:
    def __init__(self, name, entry, on_roster=True):
        self.name, self.entry, self.on_roster = name, entry, on_roster
        self.results = {}
        self.responses = {}
        self.before = None
        self.cleaned_rows = 0
        self.secret = os.environ.get("NEXXUS_GOVERNANCE_SECRET", "")

    # ---- snapshots for item 9
    MSG_LOG = ROOT / "mesh_messages.json"

    def msg_rows(self):
        try:
            return json.loads(self.MSG_LOG.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def snapshot(self):
        eng = {}
        for f in self.entry.parent.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                st = f.stat()
                eng[f.relative_to(ROOT).as_posix()] = (st.st_size, st.st_mtime_ns)
        logs = {f.name for f in LOGS.glob("*") if f.is_file()} if LOGS.exists() else set()
        rows = self.msg_rows()
        return {"engine_files": eng, "logs": logs, "msg_ids": {r.get("id") for r in rows}, "msg_max": max([r.get("id", 0) for r in rows] or [0])}

    def cleanup_message_log(self, before_max, sender, t0):
        """The relay check is real traffic through the hub, so it adds relay / instruction / ack rows to the hub's message log. Remove exactly the rows this check created (by id, kind, pair and time)."""
        pair = {(sender, self.name), ("nexxus", self.name), (self.name, sender)}
        rows = self.msg_rows()
        keep = [r for r in rows if not (r.get("id", 0) > before_max and r.get("kind") in ("relay", "instruction", "ack") and (r.get("from"), r.get("to")) in pair and r.get("ts", 0) >= t0 - 1)]
        if len(keep) != len(rows):
            tmp = self.MSG_LOG.with_name(self.MSG_LOG.name + ".tmp")
            tmp.write_text(json.dumps(keep), encoding="utf-8")
            os.replace(tmp, self.MSG_LOG)
        self.cleaned_rows += len(rows) - len(keep)

    def record(self, n, status, evidence):
        self.results[n] = (status, evidence)
        out("  [%-7s] %d. %s" % (status, n, evidence))

    # ---- 1 and 2
    def items_1_2(self):
        src = self.entry.read_text(encoding="utf-8", errors="ignore")
        bare = re.search(r'if op == "health":\s*\n\s*return \{"ok": True\}', src)
        healthy, secs, rc = ask(self.entry, {"op": "health"})
        self.responses["health"] = healthy
        down, dsecs, drc = ask(self.entry, {"op": "health"}, {"NEXXUS_MESH_URL": pick_free_dead_url()})
        nosecret, _, nrc = ask(self.entry, {"op": "health"}, {"NEXXUS_GOVERNANCE_SECRET": ""})
        self.responses["health_hub_down"], self.responses["health_no_secret"] = down, nosecret
        has_own_gov = (self.entry.parent / "nexxus_governance.py").exists()
        dep = None
        if not has_own_gov:
            dep, _, _ = ask(self.entry, {"op": "health"}, {"PYTHONPATH": str(ROOT / "logs")})        # the governance module cannot be imported
            self.responses["health_dependency_missing"] = dep
        real = not bare and healthy == {"ok": True} and down.get("ok") is False and down.get("checks", {}).get("hub_reachable") is False and nosecret.get("ok") is False and nosecret.get("checks", {}).get("can_sign_packets") is False
        if real:
            self.record(1, "PASS", "health is measured: healthy -> {'ok': True} (%.0f ms); hub unreachable -> ok False (hub_reachable False); secret missing -> ok False (can_sign_packets False); not a bare return {'ok': True}" % (secs * 1000))
        else:
            self.record(1, "FAIL", "health is not a real check (bare stub: %s, healthy: %s, hub-down: %s, no-secret: %s)" % (bool(bare), healthy, down, nosecret))
        plain = [x for x in (down, nosecret, dep) if x is not None]
        msgs = [x.get("error", "") for x in plain]
        safe = all(rc_ == 0 for rc_ in (drc, nrc)) and all(m and not re.search(r"Traceback|Error\b|[A-Za-z]:[\\/]", m) for m in msgs) and dsecs < 8
        cases = "hub down (%.1f s)" % dsecs + ", secret missing" + (", dependency missing" if dep is not None else " (dependency-missing case skipped: this engine ships its own governance copy)")
        if safe:
            self.record(2, "PASS", "failures shown and safe: %s -> exit code 0, plain message: %r" % (cases, msgs[0]))
        else:
            self.record(2, "FAIL", "a failure was not safe or not plain: %s | messages %s" % (cases, msgs))

    # ---- 3 and 4
    def items_3_4(self, stop_test):
        if not self.on_roster:
            self.record(3, "NOT RUN", "not on the roster, so there is nothing to stop yet")
            self.record(4, "NOT RUN", "not on the roster, so the dashboard cannot show it yet")
            return
        tel = hub_get("/api/mesh/telemetry")
        live = tel["engines"].get(self.name, {}).get("live")
        interval = (live or {}).get("interval", 10.0)
        limit = 3 * interval + 5
        if not stop_test:
            self.record(3, "NOT RUN", "isolation is proven only by stopping it: run with --stop-test")
            if live and live["fresh"]:
                self.record(4, "NOT RUN", "currently LIVE (heartbeat %.1f s old) but the stale/down flip time was not measured: run with --stop-test" % live["age_s"])
            else:
                self.record(4, "FAIL", "the dashboard does not show it LIVE right now: %s" % live)
            return
        others_before = {n for n, e in tel["engines"].items() if n != self.name and (e.get("live") or {}).get("fresh")}
        title = "ENGINE %s*" % self.name
        t0 = time.time()
        subprocess.run('taskkill /F /T /FI "WINDOWTITLE eq %s"' % title, shell=True, capture_output=True, timeout=30)
        flip = None
        while time.time() - t0 < 90:
            time.sleep(1)
            lv = hub_get("/api/mesh/telemetry")["engines"].get(self.name, {}).get("live")
            if not lv or not lv["fresh"]:
                flip = time.time() - t0
                break
        tel2 = hub_get("/api/mesh/telemetry")
        others_after = {n for n, e in tel2["engines"].items() if n != self.name and (e.get("live") or {}).get("fresh")}
        lost = sorted(others_before - others_after)
        if flip is not None and not lost:
            self.record(3, "PASS", "stopped its window: the other %d engines all kept reporting (0 lost), the hub kept answering" % len(others_before))
        else:
            self.record(3, "FAIL", "after stopping it: flip=%s, engines that stopped too: %s" % (flip, lost))
        if flip is not None and flip <= limit:
            self.record(4, "PASS", "dashboard flipped it from LIVE to stale %.1f s after the window closed (known bound: 3 x %.0f s heartbeat + 5 s = %.0f s)" % (flip, interval, limit))
        else:
            self.record(4, "FAIL", "flip time %s s exceeds the bound %.0f s (or it never flipped)" % (flip, limit))
        # relaunch it exactly the way start_all_engines.bat does, and confirm it comes back
        bat = LOGS / ("relaunch_%s.bat" % self.name)
        bat.write_text('@echo off\nset "ROOT=%s"\nstart "ENGINE %s" /min cmd /c "call "%%ROOT%%\\start_engine.bat" %s >> "%%ROOT%%\\logs\\engine_%s.log" 2>&1"\n' % (ROOT, self.name, self.name, self.name), encoding="ascii")
        # detached, with no pipes: the relaunched engine must not inherit our stdout/stderr, or this call would wait for it to exit (it never does)
        subprocess.Popen(["cmd", "/c", str(bat)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x00000008 | 0x08000000)
        t1 = time.time()
        back = None
        while time.time() - t1 < 60:
            time.sleep(1.5)
            lv = hub_get("/api/mesh/telemetry")["engines"].get(self.name, {}).get("live")
            if lv and lv["fresh"]:
                back = time.time() - t1
                break
        try:
            bat.unlink()
        except OSError:
            pass
        out("      (relaunched: %s)" % ("LIVE again after %.1f s" % back if back is not None else "DID NOT COME BACK - start it with start_engine.bat %s" % self.name))

    # ---- 5
    def item_5(self):
        token = "checklist-%d" % int(time.time())
        msg, _, _ = ask(self.entry, {"op": "instruct", "instruction": "message", "payload": {"from": "engine_checklist", "text": token}})
        inbox, _, _ = ask(self.entry, {"op": "instruct", "instruction": "inbox"})
        ping, _, _ = ask(self.entry, {"op": "instruct", "instruction": "ping"})
        unk, _, _ = ask(self.entry, {"op": "instruct", "instruction": "zzz_not_an_instruction"})
        util, _, _ = ask(self.entry, {"op": "utilities"})
        self.responses.update(message=msg, inbox=inbox, ping=ping, unknown=unk, utilities=util)
        got = any(m.get("payload", {}).get("text") == token for m in (inbox.get("messages") or []))
        ok_local = msg.get("ok") is True and msg.get("received") is True and "error" not in msg and got and ping.get("ok") is True and "unknown instruction" in unk.get("error", "")
        relay = "relay not tried (not on the roster or hub down)"
        relay_ok = True
        if self.on_roster:
            try:
                sys.path.insert(0, str(ROOT))
                import nexxus_governance as g
                peers = sorted(hub_get("/api/mesh/telemetry")["engines"])
                sender = next(p for p in peers if p != self.name)
                before_max, t_relay = self.snapshot()["msg_max"], time.time()
                pkt = g.sign_as_engine({"engine": sender, "kind": "note", "to": self.name, "body": {"instruction": "message", "payload": {"text": token + "-relay"}}})
                rq = urllib.request.Request(HUB + "/api/mesh/message", json.dumps(pkt).encode(), {"Content-Type": "application/json"})
                with urllib.request.urlopen(rq, timeout=30) as r:
                    rr = json.loads(r.read().decode())
                hs = rr.get("handshake") or {}
                relay_ok = rr.get("status") == "success" and hs.get("acknowledged") is True
                self.cleanup_relay_residue(token)
                self.cleanup_message_log(before_max, sender, t_relay)
                relay = "relayed %s -> %s through the hub: delivered=%s acknowledged=%s" % (sender, self.name, hs.get("delivered"), hs.get("acknowledged"))
            except Exception as e:
                relay_ok, relay = False, "relay through the hub failed: %s" % type(e).__name__
        if ok_local and relay_ok:
            self.record(5, "PASS", "message received and kept (found in the inbox), ping ok, unknown instruction refused with a reason; %s" % relay)
        else:
            self.record(5, "FAIL", "message=%s | in inbox=%s | ping=%s | unknown=%s | %s" % (msg, got, ping, unk, relay))

    def cleanup_relay_residue(self, token):
        """The relay runs in the engine's own folder (the hub starts it), so its test message lands in the engine's real inbox. Remove exactly that message again."""
        path = Path(str(self.entry) + ".inbox.json")
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
            keep = [i for i in items if not str((i.get("payload") or {}).get("text", "")).startswith(token)]
            if len(keep) != len(items):
                if not keep:
                    path.unlink()                       # nothing else in it: remove the file the test created
                else:
                    tmp = path.with_name(path.name + ".tmp")
                    tmp.write_text(json.dumps(keep), encoding="utf-8")
                    os.replace(tmp, path)
        except (OSError, ValueError):
            pass

    # ---- 6
    def item_6(self):
        problems = []
        for label, obj in self.responses.items():
            problems += scan_leaks(label, obj, self.secret)
        src = self.entry.read_text(encoding="utf-8", errors="ignore")
        if self.secret and len(self.secret) >= 8 and self.secret in src:
            problems.append("the engine's source contains the signing secret")
        if re.search(r"""(?i)secret\s*=\s*["'][A-Za-z0-9+/_\-]{16,}["']""", src):
            problems.append("the engine's source assigns a hard-coded secret")
        env_ok = "os.environ" in src
        if problems or not env_ok:
            self.record(6, "FAIL", "; ".join(problems) or "the engine does not read its settings from the environment")
        else:
            self.record(6, "PASS", "scanned %d responses (health, hub-down, no-secret, message, inbox, ping, unknown, utilities) for paths, tracebacks, keys and the secret: none; no hard-coded secret in the source; settings come from the environment" % len(self.responses))

    # ---- 7
    def item_7(self):
        if not self.on_roster:
            self.record(7, "FAIL", "it is not on the hub's roster, so no dashboard shows it. Register it, then re-run")
            return
        tel = hub_get("/api/mesh/telemetry")
        ov = hub_get("/api/diagnostics/overview")
        e = tel["engines"].get(self.name)
        row = next((x for x in ov["engines"] if x.get("name") == self.name), None)
        aud = hub_get("/api/dashboards/audit")
        clean = aud.get("ok") is True and not aud.get("orphans") and not aud.get("dangling")
        cl = aud.get("engine_cluster") or {}
        mine_ok = self.name not in (cl.get("dead_processes") or []) + (cl.get("unreferenced_folders") or []) + (cl.get("roster_without_folder") or []) + (cl.get("not_mesh_ready") or [])
        if e and e.get("found") and e.get("mesh_ready") and row and clean and cl and mine_ok:
            self.record(7, "PASS", "on the roster (found, mesh-ready), counted in the headless engine cluster (GET /api/dashboards/audit engine_cluster: %s of %s live, dead %s, unreferenced %s) and shown in the Boiler Room overview as '%s'; dashboard audit ok, 0 orphans, 0 dangling. No card of its own is required." % (cl.get("live"), cl.get("members"), cl.get("dead_processes"), cl.get("unreferenced_folders"), row.get("status")))
        elif cl and not mine_ok:
            self.record(7, "FAIL", "this engine is flagged by the cluster rollup: %s" % {k: cl.get(k) for k in ("dead_processes", "unreferenced_folders", "roster_without_folder", "not_mesh_ready")})
        elif not clean:
            self.record(7, "FAIL", "the dashboard audit is not clean: orphans %s, dangling %s, problems %s" % ([o.get("ref") for o in aud.get("orphans") or []], aud.get("dangling"), aud.get("problems")))
        else:
            self.record(7, "FAIL", "roster entry %s, overview row %s" % (e, row))

    # ---- 9
    def item_9(self, logpath):
        a, b = self.before, self.snapshot()
        new_files = sorted(set(b["engine_files"]) - set(a["engine_files"]))
        changed = sorted(f for f in a["engine_files"] if f in b["engine_files"] and a["engine_files"][f] != b["engine_files"][f])
        gone = sorted(set(a["engine_files"]) - set(b["engine_files"]))
        new_logs = sorted(x for x in (b["logs"] - a["logs"]) if not x.startswith("engine_checklist_") and x != "engine_%s.log" % self.name and not x.startswith("relaunch_"))
        new_rows = sorted(b["msg_ids"] - a["msg_ids"])
        if not (new_files or changed or gone or new_logs or new_rows):
            self.record(9, "PASS", "before and after this run: engine folder unchanged (%d files, 0 new, 0 modified), logs\\ has no new files besides the raw log, the hub's message log has 0 new rows (%d relay row(s) written by the check were removed again)" % (len(b["engine_files"]), self.cleaned_rows))
        else:
            self.record(9, "FAIL", "left behind: new files %s, modified %s, removed %s, new logs %s, new message-log rows %s" % (new_files, changed, gone, new_logs, new_rows))

    # ---- 8
    def item_8(self, logpath):
        tests = [t for t in ("axis-ui-interface/project-X/silo_vault/nexxus/test_engine_messages.py", "test_engine_health_bt.py", "test_mesh_hardening.py") if (ROOT / t).exists()]
        try:
            rel = self.entry.relative_to(ROOT).as_posix()
            tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=str(ROOT), capture_output=True).returncode == 0
            dirty = subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
            last = subprocess.run(["git", "log", "-1", "--format=%h %ad", "--date=short", "--", rel], cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
        except Exception:
            tracked, dirty, last = False, "?", ""
        committed = tracked and not dirty
        if len(tests) >= 2 and committed:
            self.record(8, "PASS", "tests on file %s; raw log %s; committed (%s)" % (tests, logpath.name, last))
        else:
            why = "tests on file: %s; raw log: %s (written when this run ends)" % (tests, logpath.name)
            why += "; commit: " + ("clean and committed (%s)" % last if committed else "NOT COMMITTED (%s) - commits are on hold until the leaked API key is rotated" % ("tracked, changed since last commit" if tracked else "not tracked"))
            self.record(8, "BLOCKED" if not committed and len(tests) >= 2 else "FAIL", why)


def run_one(name, entry, args, on_roster=True):
    out("=" * 100)
    out("ENGINE CHECKLIST  %s   %s   (entry file: %s)" % (name, time.strftime("%Y-%m-%d %H:%M:%S"), entry.relative_to(ROOT) if entry.is_relative_to(ROOT) else entry))
    out("=" * 100)
    c = Checklist(name, entry, on_roster)
    c.before = c.snapshot()
    c.items_1_2()
    c.items_3_4(args.stop_test)
    c.item_5()
    c.item_6()
    c.item_7()
    LOGS.mkdir(exist_ok=True)
    logpath = LOGS / ("engine_checklist_%s_%s.txt" % (name, time.strftime("%Y-%m-%d")))
    c.item_9(logpath)
    c.item_8(logpath)
    counts = {}
    for st, _ in c.results.values():
        counts[st] = counts.get(st, 0) + 1
    verdict = "A+ (all nine PASS)" if counts.get("PASS") == 9 else "NOT A+ yet: " + ", ".join("%s %s" % (v, k) for k, v in sorted(counts.items()))
    out("  RESULT for %s: %s" % (name, verdict))
    return c.results, logpath


def main():
    ap = argparse.ArgumentParser(description="the A+ checklist for an engine")
    ap.add_argument("engine", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--stop-test", action="store_true", help="also stop the engine's window to prove isolation and time the dashboard flip, then relaunch it")
    ap.add_argument("--file")
    ap.add_argument("--name")
    args = ap.parse_args()
    summary = {}
    if args.file:
        entry = Path(args.file).resolve()
        name = args.name or entry.stem
        roster = hub_get("/api/mesh/telemetry")["engines"]
        res, logpath = run_one(name, entry, args, on_roster=name in roster)
        summary[name] = res
        logs = {name: logpath}
    elif args.all:
        names = sorted(hub_get("/api/mesh/telemetry")["engines"])
        logs = {}
        for n in names:
            res, lp = run_one(n, SILO / n / "mesh.py", args)
            summary[n] = res
            logs[n] = lp
    elif args.engine:
        res, lp = run_one(args.engine, SILO / args.engine / "mesh.py", args)
        summary[args.engine] = res
        logs = {args.engine: lp}
    else:
        ap.error("give an engine name, --all, or --file")
    out("")
    out("SUMMARY  (%d engine%s)" % (len(summary), "s" if len(summary) != 1 else ""))
    for item in range(1, 10):
        c = {}
        for r in summary.values():
            st = r.get(item, ("-", ""))[0]
            c[st] = c.get(st, 0) + 1
        out("  item %d: %s" % (item, ", ".join("%d %s" % (v, k) for k, v in sorted(c.items()))))
    perfect = [n for n, r in summary.items() if all(r.get(i, ("", ""))[0] == "PASS" for i in range(1, 10))]
    out("  engines at A+ (all nine PASS): %d of %d" % (len(perfect), len(summary)))
    text = "\n".join(LINES) + "\n"
    if args.all:
        (LOGS / ("engine_checklist_ALL_%s.txt" % time.strftime("%Y-%m-%d"))).write_text(text, encoding="utf-8")
        print("raw log: logs\\engine_checklist_ALL_%s.txt" % time.strftime("%Y-%m-%d"))
    else:
        for lp in logs.values():
            lp.write_text(text, encoding="utf-8")
            print("raw log: %s" % lp.relative_to(ROOT))
    return 0 if len(perfect) == len(summary) else 1


if __name__ == "__main__":
    sys.exit(main())
