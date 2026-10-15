"""feed_publish.py - run on the ORIGINAL NEXXUS only. Builds the signed, public "source feed" from real results and writes the files a free static host serves (GitHub Pages or a release).

    python feed_publish.py keygen                 once: create your signing key (private: .local_config/feed_signing_key.pem, git-ignored) and the public key (feed_public_key.pem, ships with the app)
    python feed_publish.py build [--hub URL]      collect real results from the running hub, sign them, write feed_out/latest.json (+ the public key and a small viewer page)
    python feed_publish.py license NUMBER HOLDER  issue a signed license token for a buyer (the number you put on the download page); prints it, sends nothing anywhere
    python feed_publish.py check                  re-verify feed_out/latest.json exactly as a copy would

What goes in (real data only, whitelisted, numbers and plain words): system health counts, the dashboard audit result, the latest full test run, the version, and any outputs YOU placed in feed_outputs/*.json
(each must name its source and method). No paths, addresses, keys or names ever go in: the bundle is checked and the build stops if anything looks like one. Nothing is sent anywhere by this script: you upload feed_out/ yourself."""
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

import feed_core

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY_PATH = os.environ.get("NEXXUS_FEED_KEY") or os.path.join(ROOT, ".local_config", "feed_signing_key.pem")
PUB_PATH = os.path.join(ROOT, "feed_public_key.pem")
OUT_DIR = os.environ.get("NEXXUS_FEED_OUT") or os.path.join(ROOT, "feed_out")
OUTPUTS_DIR = os.environ.get("NEXXUS_FEED_OUTPUTS") or os.path.join(ROOT, "feed_outputs")
NOTICE = ("Published by the original NEXXUS. These are results from one system, offered for information. They are not advice and not guarantees; outputs state their source and method, "
          "and no accuracy is claimed unless a measured record is included.")


def keygen():
    if os.path.exists(KEY_PATH):
        sys.exit("a signing key already exists at .local_config/feed_signing_key.pem: not overwriting it. Delete it yourself only if you mean to replace your published identity.")
    priv, pub = feed_core.generate_keypair()
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "wb") as f:
        f.write(priv)
    with open(PUB_PATH, "wb") as f:
        f.write(pub)
    print("created the signing key (private, stays on this PC, git-ignored) and feed_public_key.pem (public, ships with the app).")
    print("BACK UP .local_config/feed_signing_key.pem somewhere safe and private: if it is lost, every copy would need a new public key.")


def _get(hub, path):
    with urllib.request.urlopen(hub.rstrip("/") + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def collect(hub):
    tel = _get(hub, "/api/mesh/telemetry")
    eng = tel.get("engines") or {}
    live = sum(1 for v in eng.values() if (v.get("live") or {}).get("fresh"))
    ready = sum(1 for v in eng.values() if v.get("mesh_ready"))
    aud = _get(hub, "/api/dashboards/audit")
    cl = aud.get("engine_cluster") or {}
    system = {"engines": len(eng), "engines_live": live, "engines_mesh_ready": ready, "hub_uptime_s": int((tel.get("hub") or {}).get("uptime_s") or 0)}
    audit = {"dashboard_audit_ok": bool(aud.get("ok")), "orphans": len(aud.get("orphans") or []), "engine_cluster_ok": bool(cl.get("ok")), "engine_cluster_live": int(cl.get("live") or 0),
             "engine_cluster_members": int(cl.get("members") or 0)}
    return system, audit


def read_text(path):
    """Decode a log however Windows wrote it (UTF-8, UTF-8 with a byte-order mark, or UTF-16): a hidden first character must never hide a line from the counts."""
    raw = open(path, "rb").read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def latest_tests():
    files = sorted(glob.glob(os.path.join(os.environ.get("NEXXUS_FEED_LOGS") or os.path.join(ROOT, "logs"), "verify_all_*.txt")))
    if not files:
        return {"available": False}
    text = read_text(files[-1]).replace("\r\n", "\n")
    passed = len(re.findall(r"(?m)^\s*PASS\b", text))
    failed = len(re.findall(r"(?m)^\s*FAIL\b", text))
    m = re.search(r"verify_all_(\d{4}-\d{2}-\d{2})", files[-1])
    return {"available": True, "run_date": m.group(1) if m else "", "suites_passed": passed, "suites_failed": failed, "all_green": "ALL GREEN" in text and failed == 0}


def version():
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def read_outputs():
    """Outputs YOU placed in feed_outputs/*.json. Each must be real and say where it came from; anything else is refused, not guessed."""
    out = []
    for p in sorted(glob.glob(os.path.join(OUTPUTS_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        for need in ("title", "summary", "source", "method", "generated_at"):
            if not str(d.get(need, "")).strip():
                raise feed_core.FeedError("%s is missing '%s': every published output must name its source and method" % (os.path.basename(p), need))
        out.append({k: d[k] for k in ("title", "summary", "source", "method", "generated_at") } | {"data": d.get("data", {}), "notice": "Output from one system. Not advice, not a guarantee."})
    return out


def next_sequence():
    try:
        with open(os.path.join(OUT_DIR, "latest.json"), encoding="utf-8") as f:
            return int(json.load(f)["bundle"]["sequence"]) + 1
    except (OSError, ValueError, KeyError, TypeError):
        return 1


def build(hub):
    if not os.path.exists(KEY_PATH):
        sys.exit("no signing key yet: run `python feed_publish.py keygen` first")
    system, audit = collect(hub)
    outputs = read_outputs()
    sections = {"notice": NOTICE, "version": version(), "system": system, "audit": audit, "tests": latest_tests(), "outputs": outputs,
                "outputs_note": "" if outputs else "No outputs have been published yet. This feed currently carries system results only."}
    feed_core.assert_public_safe(sections)
    bundle = feed_core.make_bundle(next_sequence(), sections)
    with open(KEY_PATH, "rb") as f:
        data = feed_core.pack(bundle, f.read())
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "latest.json"), "wb") as f:
        f.write(data)
    with open(PUB_PATH, "rb") as src, open(os.path.join(OUT_DIR, "feed_public_key.pem"), "wb") as f:
        f.write(src.read())
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(VIEWER)
    check()
    print("built feed number %d: %d engines live of %d, tests %s, %d output(s). Upload the folder feed_out/ to your static host." % (bundle["sequence"], system["engines_live"], system["engines"],
          "ALL GREEN" if sections["tests"].get("all_green") else "see tests section", len(outputs)))


def check():
    with open(os.path.join(OUT_DIR, "latest.json"), "rb") as f, open(PUB_PATH, "rb") as p:
        r = feed_core.verify_bundle(f.read(), p.read())
    print("verified like a copy would: sequence %d, stale=%s" % (r["bundle"]["sequence"], r["stale"]))


def license_cmd(number, holder):
    if not os.path.exists(KEY_PATH):
        sys.exit("no signing key yet: run `python feed_publish.py keygen` first")
    with open(KEY_PATH, "rb") as f:
        print(json.dumps(feed_core.issue_license(number, holder, "commercial", f.read()), indent=1))


VIEWER = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NEXXUS source feed</title>
<style>body{font:15px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem}pre{background:#f3f5f7;padding:1rem;overflow:auto;border-radius:8px}</style>
<h1>NEXXUS source feed</h1><p>Signed results published by the original NEXXUS. Copies of the app fetch and verify <code>latest.json</code>. This page only displays it; it does not verify the signature.</p><pre id="o">loading...</pre>
<script>fetch('latest.json').then(r=>r.json()).then(d=>{document.getElementById('o').textContent=JSON.stringify(d.bundle,null,2)}).catch(()=>{document.getElementById('o').textContent='Could not load latest.json'})</script>
"""


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "keygen":
        keygen()
    elif cmd == "build":
        hub = argv[argv.index("--hub") + 1] if "--hub" in argv else "http://127.0.0.1:8000"
        try:
            build(hub)
        except feed_core.FeedError as e:
            sys.exit("not published: %s" % e)
    elif cmd == "license" and len(argv) >= 4:
        license_cmd(argv[2], " ".join(argv[3:]))
    elif cmd == "check":
        check()
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
