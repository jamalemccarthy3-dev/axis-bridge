"""demo_sandbox.py - an isolated, throwaway copy of NEXXUS for recording demos, so nothing you show touches your real hub, quarantine, logs or secrets.

    python demo_sandbox.py build        copy the system into the sandbox, create demo-only settings, seed demo quarantine items
    python demo_sandbox.py start        start the sandbox hub (port 8100) and its 21 engines, publish the roster, wait until 21 are live
    python demo_sandbox.py start --mobile   same, and also listen on this PC's Tailscale address, so your phone (on your tailnet) can open it
    python demo_sandbox.py status       what is running, and proof that your real hub on port 8000 is not the one being used
    python demo_sandbox.py reseed       put the demo quarantine items back (use before each take of "Release All")
    python demo_sandbox.py checklist [engine]   run the nine-point checklist against the SANDBOX hub (default engine: axis-core)
    python demo_sandbox.py stop         stop only the sandbox processes
    python demo_sandbox.py clean        stop, then delete the sandbox folder

What is safe about it: it lives in its own folder (default: Desktop\\nexxus_demo_sandbox, override with NEXXUS_DEMO_DIR) on its own port 8100, with its own random governance secret, its own message
log and liveness file, and a perimeter folder holding only obviously fake demo items. The admin token in the sandbox is the throwaway word `demo-token`, safe to type on camera. It refuses to run
on port 8000 and never reads or writes your real quarantine. Windows only. Standard library only."""
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
SANDBOX = os.environ.get("NEXXUS_DEMO_DIR") or os.path.join(os.path.expanduser("~"), "Desktop", "nexxus_demo_sandbox")
PORT = 8100
TOKEN = "demo-token"
NESTED = ["", r"axis-ui-interface\project-X\axis_gate", r"axis-ui-interface\project-X\silo_vault\nexxus", r"axis-ui-interface\project-X\silo_vault\axis-core",
          r"axis-ui-interface\project-X\silo_vault\axis-phonetic", r"axis-ui-interface\project-X\silo_vault\axis-vantage_point",
          r"axis-ui-interface\project-X\silo_vault\S.A.M.U.E.L.-", r"axis-ui-interface\project-X\silo_vault\triad-protocol-module-"]
DEMO_ITEMS = [("demo-node-%02d" % i, "bad-signature: demo packet %d (fake data for the demo)" % i,
               {"engine": "demo-node-%02d" % i, "kind": "demo", "body": "This is a demo-only packet number %d. It is not real traffic." % i}) for i in range(1, 13)]


def sb(*p):
    return os.path.join(SANDBOX, *p)


def get(path, token=False):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), headers={"X-Nexxus-Admin-Token": TOKEN} if token else {})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def up():
    try:
        get("/api/mesh/telemetry")
        return True
    except Exception:
        return False


def ps(script):
    return subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=120).stdout


def sandbox_pids():
    out = ps("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like '*%s*' -and $_.ProcessId -ne $PID } | Select-Object -ExpandProperty ProcessId" % SANDBOX.replace("'", "''"))
    return [int(x) for x in out.split() if x.strip().isdigit()]


def guard():
    if PORT == 8000:
        sys.exit("refusing to use port 8000: that is the real hub")
    if os.path.abspath(SANDBOX) == os.path.abspath(ROOT) or os.path.abspath(ROOT).startswith(os.path.abspath(SANDBOX) + os.sep):
        sys.exit("the sandbox folder must be separate from the real repository")


def build():
    guard()
    if up():
        sys.exit("something already answers on port %d: run `stop` first" % PORT)
    if os.path.isdir(SANDBOX):
        shutil.rmtree(SANDBOX)
    n = 0
    for rel in NESTED:
        base = os.path.join(ROOT, rel)
        out = subprocess.run(["git", "-C", base, "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True).stdout.decode("utf-8", "replace")
        for f in filter(None, out.split("\0")):
            s = os.path.join(base, f)
            if os.path.isfile(s):
                d = os.path.join(SANDBOX, rel, f)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
                n += 1
    for f in os.listdir(ROOT):                                   # the root modules git keeps private (bridges) are needed to run
        if f.endswith(".py") and not os.path.exists(sb(f)):
            shutil.copy2(os.path.join(ROOT, f), sb(f))
            n += 1
    os.makedirs(sb("logs"), exist_ok=True)
    with open(sb("nexxus_env.bat"), "w", newline="\r\n") as f:
        f.write('@echo off\nset "NEXXUS_GOVERNANCE_SECRET=%s"\nset "NEXXUS_MESH_URL=http://127.0.0.1:%d"\nset "NEXXUS_REQUIRE_ENGINE_KEYS=1"\nset "NEXXUS_PORT=%d"\n'
                'set "NEXXUS_ADMIN_TOKEN=%s"\nset "NEXXUS_PERIMETER_DIR=%s"\nfor %%%%I in ("%%~dp0.") do set "NEXXUS_HOME=%%%%~fI"\nset "PYTHONPATH=%%NEXXUS_HOME%%;%%PYTHONPATH%%"\n'
                % (secrets.token_hex(32), PORT, PORT, TOKEN, sb("perimeter_demo")))
    with open(sb("nexxus_admin.bat"), "w", newline="\r\n") as f:
        f.write("@echo off\nREM demo sandbox only\n")
    reseed()
    print("built the sandbox: %d files in %s" % (n, SANDBOX))
    print("admin token for the demo (throwaway, safe on camera): %s" % TOKEN)


def reseed():
    guard()
    sys.path.insert(0, sb())
    import importlib
    perim_dir = sb("perimeter_demo")
    shutil.rmtree(perim_dir, ignore_errors=True)
    os.makedirs(perim_dir)
    import perimeter
    importlib.reload(perimeter)
    p = perimeter.Perimeter(perim_dir)
    for node, reason, packet in DEMO_ITEMS:
        p.quarantine(node, reason, packet)
    print("seeded %d demo-only quarantine items in %s" % (len(p.quarantined()), perim_dir))


def tailscale_ip():
    for exe in ("tailscale", r"C:\Program Files\Tailscale\tailscale.exe"):
        try:
            out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=15).stdout.split()
            if out:
                return out[0]
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def start(mobile=False):
    guard()
    if not os.path.isdir(SANDBOX):
        sys.exit("run `build` first")
    if mobile and not tailscale_ip():
        sys.exit("--mobile needs Tailscale running on this PC (no Tailscale address found)")
    if up():
        print("the sandbox hub is already running")
    else:
        pyexe = sys.executable
        hub = '"%s" python_server.py > logs\\hub_demo.log 2>&1' % pyexe
        bat = sb("_run_hub.bat")
        bind = 'set "NEXXUS_BIND=loopback,tailscale"\n' if mobile else ""        # mobile: also listen on this PC's Tailscale address (your own devices only, never the open internet)
        with open(bat, "w", newline="\r\n") as f:
            f.write('@echo off\ncd /d "%s"\ncall "%s\\nexxus_env.bat"\ncall "%s\\nexxus_admin.bat"\n%sif not "%%NEXXUS_PORT%%"=="%d" exit /b 9\n%s\n' % (SANDBOX, SANDBOX, SANDBOX, bind, PORT, hub))
        subprocess.Popen(["cmd", "/c", bat], cwd=SANDBOX, creationflags=0x08000000 | 0x00000008, close_fds=True)
        for _ in range(40):
            time.sleep(2)
            if up():
                break
        else:
            sys.exit("the sandbox hub did not come up; see %s" % sb("logs", "hub_demo.log"))
        eng = sb("_run_engines.bat")
        with open(eng, "w", newline="\r\n") as f:
            f.write('@echo off\ncd /d "%s"\ncall "%s\\start_all_engines.bat"\n' % (SANDBOX, SANDBOX))
        subprocess.Popen(["cmd", "/c", eng], cwd=SANDBOX, creationflags=0x08000000 | 0x00000008, close_fds=True)
    time.sleep(25)
    silo = os.path.join(SANDBOX, "axis-ui-interface", "project-X", "silo_vault")             # absolute, as the real bridge passes it (a relative path doubles the engine paths)
    subprocess.run([sys.executable, "-c", "import mesh_roster, pathlib, sys; mesh_roster.publish_roster(pathlib.Path(sys.argv[1]))", silo], cwd=SANDBOX, capture_output=True)
    for _ in range(10):
        time.sleep(3)
        t = get("/api/mesh/telemetry")
        fresh = sum(1 for v in t["engines"].values() if (v.get("live") or {}).get("fresh"))
        if fresh >= 21:
            break
    print("sandbox hub: http://localhost:%d/  | engines live: %d of %d | perimeter: %s" % (PORT, fresh, len(t["engines"]), get("/api/perimeter/status")["perimeter"]["quarantined"]) + " quarantined (demo items)")
    print("admin token for the demo: %s" % TOKEN)
    if mobile:
        print("phone link (on your Tailscale network only): http://%s:%d/" % (tailscale_ip(), PORT))


def status():
    print("sandbox folder:", SANDBOX, "(exists)" if os.path.isdir(SANDBOX) else "(not built)")
    print("sandbox hub on %d: %s" % (PORT, "UP" if up() else "down"))
    try:
        real = get("/api/mesh/telemetry")
    except Exception:
        real = None
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8000/api/mesh/telemetry", timeout=8)
        t = json.loads(r.read().decode("utf-8"))
        print("real hub on 8000: UP, serving", t["server"]["file"])
    except Exception:
        print("real hub on 8000: not answering")
    if real:
        print("sandbox hub serves:", real["server"]["file"])
    print("sandbox processes:", len(sandbox_pids()))


def checklist(engine="axis-core"):
    guard()
    if not up():
        sys.exit("start the sandbox first")
    bat = sb("_run_checklist.bat")
    with open(bat, "w", newline="\r\n") as f:
        f.write('@echo off\ncd /d "%s"\ncall "%s\\nexxus_env.bat"\n"%s" engine_checklist.py %s\n' % (SANDBOX, SANDBOX, sys.executable, engine))
    subprocess.run(["cmd", "/c", bat], cwd=SANDBOX)


def stop():
    guard()
    pids = sandbox_pids()
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    time.sleep(2)
    print("stopped %d sandbox process(es); sandbox hub is %s" % (len(pids), "UP (something else?)" if up() else "down"))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "build":
        build()
    elif cmd == "start":
        start(mobile="--mobile" in argv)
    elif cmd == "status":
        status()
    elif cmd == "reseed":
        reseed()
    elif cmd == "checklist":
        checklist(*(argv[2:3]))
    elif cmd == "stop":
        stop()
    elif cmd == "clean":
        stop()
        guard()
        shutil.rmtree(SANDBOX, ignore_errors=True)
        print("deleted", SANDBOX)
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
