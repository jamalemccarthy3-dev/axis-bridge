"""Does the public-facade leak guard actually catch leaks, and is the real output isolated? Plants leaks in a COPY and checks each is flagged.
Run: python test_facade_guard.py"""
import re, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_facade as B

n = ok = 0
def chk(label, cond, extra=""):
    global n, ok; n += 1; ok += bool(cond); print("[%s] %s %s" % ("PASS" if cond else "FAIL", label, extra))

tmp = Path(tempfile.mkdtemp(prefix="facade_test_"))
out = tmp / "out"
info = B.build(out)
chk("a build produces files for every engine folder", len(info["engines"]) >= 21 and info["files"] > 500, str(len(info["engines"])))
chk("the untouched build passes the guard", B.verify(out) == [])

eng = sorted((out / "engines").iterdir())[0]
def planted(label, mutate, expect):
    c = tmp / ("c_" + re.sub(r"\W+", "_", label)[:30]); shutil.copytree(out, c)
    mutate(c / "engines" / eng.name, c)
    bad = B.verify(c)
    chk("the guard catches: " + label, any(expect in b for b in bad), str(bad[:2]))

planted("a wiring-style file name inside an engine", lambda e, c: (e / "mesh.py").write_text("# Implementation withheld. This file exists in the private source.\n"), "wiring-style name")
planted("a master_config file inside an engine", lambda e, c: (e / "master_config.py").write_text("# x\n"), "wiring-style name")
planted("real code in a source file", lambda e, c: (e / "engine_core.py").write_text("def run():\n    return 42\n"), "not a placeholder")
planted("an engine file that mentions the bridge", lambda e, c: (e / "README.md").write_text("This engine connects to the bridge on localhost.\n"), "mentions the bridge")
planted("a secret-looking value", lambda e, c: (e / "notes.md").write_text("key sk-abcdefghijklmnopqrstuvwxyz123456\n"), "secret-shaped")
planted("a secrets file name", lambda e, c: (e / "nexxus.secret").write_text("x"), "hidden name")
planted("an .env file", lambda e, c: (c / "bridge" / ".env").parent.mkdir(parents=True, exist_ok=True) or (c / "bridge" / ".env").write_text("A=1\n"), "hidden name")
planted("a consultant-network file", lambda e, c: (c / "bridge" / "consult_tool.py").parent.mkdir(parents=True, exist_ok=True) or (c / "bridge" / "consult_tool.py").write_text("# Implementation withheld. This file exists in the private source.\n"), "hidden name")
planted("a byte copy of a real source file", lambda e, c: shutil.copy(B.WORK / "nexxus_governance.py", c / "bridge" / "copy.py") if (c / "bridge").is_dir() else None, "byte-identical")
def _readme_plus(text):
    return lambda e, c: (c / "README.md").write_text((c / "README.md").read_text(encoding="utf-8") + "\n" + text + "\n", encoding="utf-8")
planted("a README that reveals a local address", _readme_plus("running at localhost:8000"), "README leaks")
planted("a README that names a source file", _readme_plus("see mesh_bridge.py"), "README leaks")
planted("a README that names the consultant network", _readme_plus("the consult layer"), "README leaks")
def _spec_plus(text):
    return lambda e, c: (c / "docs" / "SPECIFICATION.md").write_text((c / "docs" / "SPECIFICATION.md").read_text(encoding="utf-8") + "\n" + text + "\n", encoding="utf-8")
planted("a specification that reveals a local address", _spec_plus("served at localhost:8000"), "SPECIFICATION.md leaks")
planted("a specification that names a source file", _spec_plus("wired in mesh_bridge.py"), "SPECIFICATION.md leaks")
planted("a specification that names a private subsystem", _spec_plus("the consult network"), "SPECIFICATION.md leaks")
def _assign_plus(text):
    return lambda e, c: (c / "docs" / "ASSIGNMENT.md").write_text((c / "docs" / "ASSIGNMENT.md").read_text(encoding="utf-8") + "\n" + text + "\n", encoding="utf-8")
planted("an assignment that names a source file", _assign_plus("edit mesh_bridge.py"), "ASSIGNMENT.md leaks")
planted("an assignment that reveals a key", _assign_plus("the token is abc"), "ASSIGNMENT.md leaks")
planted("a wiring file name on the bridge side", lambda e, c: (c / "bridge" / "mesh_bridge.py").parent.mkdir(parents=True, exist_ok=True) or (c / "bridge" / "mesh_bridge.py").write_text("# Implementation withheld. This file exists in the private source.\n"), "bridge side contains")
planted("a governance file name on the core side", lambda e, c: (c / "core" / "nexxus_governance.py").parent.mkdir(parents=True, exist_ok=True) or (c / "core" / "nexxus_governance.py").write_text("# Implementation withheld. This file exists in the private source.\n"), "bridge side contains")
planted("an engine folder without its README", lambda e, c: (e / "README.md").unlink(), "without its README")

# independent look at the real output (plain checks, not the guard's own code)
engine_files = [p for p in (out / "engines").rglob("*") if p.is_file()]
names = [p.relative_to(out / "engines").as_posix().lower() for p in engine_files]
bad_names = [x for x in names if "/" in x and re.search(r"(bridge|mesh|nexxus|govern|heartbeat|live_status|master_|snippet|handshake|roster|diagnostic_|orders)", x.split("/", 1)[1])]
chk("no engine path contains a wiring word (independent check)", not bad_names, str(bad_names[:3]))
contents = {p.read_text(encoding="utf-8") for p in engine_files if p.name != "README.md"}
chk("every engine file is just a placeholder line (%d distinct contents)" % len(contents), all(len(c) < 90 and "withheld" in c for c in contents), str(list(contents)[:2]))
chk("engine READMEs say nothing about the bridge", all(not re.search(r"(bridge|nexxus|mesh|govern)", p.read_text(encoding="utf-8"), re.I) for p in engine_files if p.name == "README.md"))
chk("each engine folder stands alone: no file refers to a sibling engine", all(not re.search(r"axis-[a-z_]+", p.read_text(encoding="utf-8")) for p in engine_files if p.name != "README.md"))
chk("the consultant network does not appear anywhere in the output", not [p for p in out.rglob("*") if re.search(r"consult", p.relative_to(out).as_posix(), re.I)])
allnames = " ".join(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
chk("no secret, env, key-box or private-vault file names anywhere in the output", not re.search(r"(secret|\.env|token|credential|keybox|(tools|staging|creations)_vault)", allnames, re.I))
print("\n%d/%d passed" % (ok, n))
sys.exit(0 if ok == n else 1)
