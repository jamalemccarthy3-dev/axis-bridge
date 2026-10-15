"""requirements_scan.py - which pip packages does each engine really need, and are they installed?

    python requirements_scan.py                 print the summary
    python requirements_scan.py --write         also write requirements/<engine>.txt, requirements-all.txt and PIP_REPORT.md

For every .py file of an engine it reads the imports (never runs the code), drops the standard library and the project's own modules, maps the rest from
the import name to the pip name (PIL -> Pillow, yaml -> PyYAML, cv2 -> opencv-python ...), and checks the packages against THIS Python.
  required   imported at the top level of a file: the engine fails to import without it
  optional   imported inside try/except ImportError or inside a function: the engine degrades without it
  dev        only imported by test files
Nothing is installed. The install command for what is missing is printed at the end.
"""
import ast
import importlib.metadata as md
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SILO = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault")
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "logs", "dist", "build", "builds", "venv", "env", "_archive", "site-packages", "backups", "InstantMesh", "nvdiffrast"}
STDLIB = set(sys.stdlib_module_names)
KNOWN = {  # import name -> pip name, for names that differ (used when the package is not installed, so metadata cannot say)
    "yaml": "PyYAML", "cv2": "opencv-python", "PIL": "Pillow", "bs4": "beautifulsoup4", "sklearn": "scikit-learn", "dotenv": "python-dotenv", "serial": "pyserial",
    "dateutil": "python-dateutil", "OpenGL": "PyOpenGL", "Crypto": "pycryptodome", "jwt": "PyJWT", "magic": "python-magic", "win32com": "pywin32", "win32api": "pywin32",
    "pythoncom": "pywin32", "pyttsx3": "pyttsx3", "speech_recognition": "SpeechRecognition", "attr": "attrs", "git": "GitPython", "docx": "python-docx",
    "fitz": "PyMuPDF", "skimage": "scikit-image", "google": "google-api-python-client", "zmq": "pyzmq", "llama_cpp": "llama-cpp-python", "usb": "pyusb", "bluetooth": "pybluez", "lxml": "lxml",
}
PIP_NAME_FIX = {"pywin32": "pywin32", "comtypes": "comtypes"}


def local_names():
    """Every module/package name the project itself provides, anywhere: a flat import of one of these is not a pip package."""
    names = set()
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.endswith("_env") and not d.startswith(".")]
        for d in dn:
            names.add(d.replace("-", "_"))
        for f in fn:
            if f.endswith((".py", ".pyd")):
                names.add(f.split(".")[0])
            if f == "bootstrap.py":      # an engine's bootstrap registers flat import names ("x_utility") at runtime; those are the project's own
                names.update(re.findall(r'^\s*"([A-Za-z_][\w]*)"\s*:', open(os.path.join(dp, f), encoding="utf-8", errors="replace").read(), re.M))
    return names


def py_files(folder):
    for dp, dn, fn in os.walk(folder):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.endswith("_env") and not d.startswith("_backup")]
        for f in fn:
            if f.endswith(".py"):
                yield os.path.join(dp, f)


def imports_of(path):
    """-> [(top-level module name, kind)] with kind required / optional."""
    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
    except SyntaxError:
        return []
    out = []

    def visit(node, optional):
        for child in ast.iter_child_nodes(node):
            opt = optional
            if isinstance(child, ast.Try) and any(isinstance(h.type, (ast.Name, ast.Tuple, ast.Attribute)) and re.search(r"ImportError|ModuleNotFoundError|Exception", ast.dump(h.type)) or h.type is None for h in child.handlers):
                opt = True
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                opt = True
            if isinstance(child, ast.Import):
                for a in child.names:
                    out.append((a.name.split(".")[0], "optional" if opt else "required"))
            elif isinstance(child, ast.ImportFrom) and child.level == 0 and child.module:
                out.append((child.module.split(".")[0], "optional" if opt else "required"))
            visit(child, opt)
    visit(tree, False)
    return out


def is_test(path):
    b = os.path.basename(path)
    return b.startswith("test_") or b.endswith("_test.py") or b in ("master_test.py", "health_report.py", "conftest.py")


DIST_MAP = None


def dist_for(name):
    global DIST_MAP
    if DIST_MAP is None:
        try:
            DIST_MAP = md.packages_distributions()
        except Exception:
            DIST_MAP = {}
    if name in DIST_MAP:
        return DIST_MAP[name][0]
    return KNOWN.get(name, name)


def installed(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def version_of(dist):
    try:
        return md.version(dist)
    except md.PackageNotFoundError:
        return None


def scan_engine(name, local):
    folder = os.path.join(SILO, name)
    own = {os.path.splitext(f)[0] for _, _, fs in os.walk(folder) for f in fs if f.endswith(".py")}
    found = {}      # import name -> {"kinds": set, "files": set}
    for p in py_files(folder):
        t = is_test(p)
        for mod, kind in imports_of(p):
            if mod in STDLIB or mod in local or mod in own or mod == "__future__":
                continue
            e = found.setdefault(mod, {"kinds": set(), "files": set()})
            e["kinds"].add("dev" if t else kind)
            e["files"].add(os.path.relpath(p, folder).replace("\\", "/"))
    rows = []
    for mod, e in sorted(found.items()):
        kind = "required" if "required" in e["kinds"] else ("optional" if "optional" in e["kinds"] else "dev")
        dist = dist_for(mod)
        ok = installed(mod)
        if not ok and mod not in KNOWN and dist == mod and re.search(r"_(utility|tool|config|orchestrator|controller|engine)$|^myproject$|^nexus_|^universal_", mod):
            kind = "unresolved"      # looks like one of the project's own modules, but no such file exists: a broken import, not a pip package
        rows.append({"import": mod, "pip": dist, "kind": kind, "installed": ok, "version": version_of(dist) if ok else None, "files": sorted(e["files"])[:4]})
    js = os.path.join(folder, "package.json")
    node = None
    if os.path.isfile(js):
        try:
            pj = json.load(open(js, encoding="utf-8"))
            node = {"dependencies": pj.get("dependencies", {}), "devDependencies": pj.get("devDependencies", {})}
        except ValueError:
            node = {"error": "package.json does not parse"}
    has_c = any(f.endswith((".c", ".cpp")) for _, _, fs in os.walk(folder) for f in fs)
    return {"engine": name, "packages": rows, "node": node, "needs_c_compiler": has_c}


def main(argv):
    write = "--write" in argv
    names = [a for a in argv if not a.startswith("--")] or sorted(d for d in os.listdir(SILO) if os.path.isdir(os.path.join(SILO, d)) and not d.startswith(("_", ".")) and d != "render")
    local = local_names()
    results = [scan_engine(n, local) for n in names]
    missing_all = {}
    unresolved = {}
    print("%-24s %9s %9s %9s %s" % ("engine", "required", "optional", "dev", "missing (required / optional)"))
    for r in results:
        by = lambda k: [p for p in r["packages"] if p["kind"] == k]
        for p in by("unresolved"):
            unresolved.setdefault(p["import"], []).append(r["engine"] + ":" + p["files"][0])
        miss_req = [p["pip"] for p in by("required") if not p["installed"]]
        miss_opt = [p["pip"] for p in by("optional") if not p["installed"]]
        for p in by("required") + by("optional"):
            if not p["installed"]:
                missing_all.setdefault(p["pip"], set()).add(r["engine"])
        print("%-24s %9d %9d %9d %s / %s%s" % (r["engine"], len(by("required")), len(by("optional")), len(by("dev")), ", ".join(miss_req) or "-", ", ".join(miss_opt) or "-", ("   broken imports: %d" % len(by("unresolved"))) if by("unresolved") else ""))
    if missing_all:
        print("\nNOT INSTALLED but imported (required or optional): " + ", ".join(sorted(missing_all)))
        print("install them with:   python -m pip install " + " ".join(sorted(missing_all)))
    if write:
        os.makedirs(os.path.join(ROOT, "requirements"), exist_ok=True)
        union = {}
        for r in results:
            lines = ["# %s: generated by requirements_scan.py. required first, then optional; '# not installed' marks what this machine lacks." % r["engine"]]
            for kind in ("required", "optional"):
                for p in (q for q in r["packages"] if q["kind"] == kind):
                    spec = "%s==%s" % (p["pip"], p["version"]) if p["version"] else p["pip"]
                    lines.append(("# optional: " if kind == "optional" else "") + spec + ("" if p["installed"] else "   # not installed"))
                    union.setdefault(p["pip"], p["version"])
            if r["needs_c_compiler"]:
                lines.append("# also needs a C compiler to build its C code (gcc/clang, or: pip install ziglang)")
            if r["node"] is not None:
                lines.append("# also a Node.js engine (npm: %s)" % (r["node"].get("dependencies") or "no dependencies"))
            open(os.path.join(ROOT, "requirements", r["engine"] + ".txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
        open(os.path.join(ROOT, "requirements-all.txt"), "w", encoding="utf-8").write("# every third-party package any engine imports\n" + "\n".join(("%s==%s" % (k, v)) if v else k for k, v in sorted(union.items())) + "\n")
        rep = ["# Pip packages per engine", "", "Generated by `python requirements_scan.py --write` from the engines' imports, checked against %s." % sys.version.split()[0], "",
               "`requirements/<engine>.txt` is one engine's list; `requirements-all.txt` is the union. A `==version` is what is installed here.", "",
               "| Engine | Required | Optional | Missing here |", "|---|---|---|---|"]
        for r in results:
            req = ", ".join(p["pip"] for p in r["packages"] if p["kind"] == "required") or "-"
            opt = ", ".join(p["pip"] for p in r["packages"] if p["kind"] == "optional") or "-"
            miss = ", ".join(p["pip"] for p in r["packages"] if p["kind"] != "dev" and not p["installed"]) or "-"
            rep.append("| %s | %s | %s | %s |" % (r["engine"], req, opt, miss))
        if unresolved:
            rep += ["", "## Broken imports (not pip packages)", "", "These look like the project's own modules but no such file exists, so the importing file fails or silently skips them.", ""]
            rep += ["- `%s`: %s" % (m, "; ".join(sorted(set(w)))) for m, w in sorted(unresolved.items())]
        if missing_all:
            rep += ["", "## Install what is missing", "", "```", "python -m pip install " + " ".join(sorted(missing_all)), "```"]
        open(os.path.join(ROOT, "PIP_REPORT.md"), "w", encoding="utf-8").write("\n".join(rep) + "\n")
        json.dump(results, open(os.path.join(ROOT, "logs", "requirements.json"), "w", encoding="utf-8"), indent=1)
        print("\nwrote requirements/<engine>.txt, requirements-all.txt, PIP_REPORT.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
