"""placeholder_scan.py - finds the places that LOOK like working code but are not, in every engine (Python, JavaScript, C/C++).

    python placeholder_scan.py                 print the summary
    python placeholder_scan.py --write         also write PLACEHOLDERS.md (readable) and logs/placeholders.json (everything)
    python placeholder_scan.py axis-logic      one engine

What it looks for, per file:
  EMPTY        a function or class whose body is only pass / ... / a docstring / comments
  PRINT_ONLY   a function that only prints (and maybe returns a constant): it announces work it does not do
  CONSTANT     a function that always returns the same True/False/None/status text, whatever it is given ("return True  # placeholder")
  NOT_IMPL     raise NotImplementedError: an honest, deliberate stub
  MARKER       the words placeholder / TODO / FIXME / stub / "not implemented" / "logic to ..." / "this is where ... will go" in code or comments
  CLAIM        a hard-coded READY / VERIFIED / OPERATIONAL status that nothing checked
  TINY_FILE    a code file with three lines of code or fewer (a skeleton)
Boilerplate copied into every engine (mesh.py, live_status.py, bridge_*.py, deployment_tool.py) is counted once, separately, not per engine.
Tests, __init__.py, vendored folders and the archive are skipped. Read-only.
"""
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SILO = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault")
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "logs", "dist", "build", "builds", "venv", "env", "bridge_env", "instantmesh_env", "tests", "test", "libs", "bin", "_archive", "backups", "backup"}
BOILERPLATE = {"engine_snippit_review.py", "engine_snippet_review.py", "mesh.py", "live_status.py", "bridge_diagnostic.py", "bridge_orders.py", "deployment_tool.py", "nexxus_governance.py"}
EXTS = (".py", ".js", ".mjs", ".c", ".h", ".cpp")
MARKER = re.compile(r"(?i:\bplaceholder\b|\bstubs?\b|not (?:yet )?(?:implemented|built|written)|\bImplementation (?:would|goes|here)\b|\bcoming soon\b)|\bTODO\b|\bFIXME\b|\bXXX\b")
COMMENT_MARKER = re.compile(r"(?i:\bLogic (?:to|for|goes|would)\b|this is where .{0,40}(?:will|would|goes)|\bgoes here\b|\bwould go here\b)")     # only when the line is a comment
MARKER_IGNORE = re.compile(r"placeholder\s*=|re\.compile|_PLACEHOLDER|scan:ok|not a (?:stub|placeholder)|stubs imported above")      # an HTML attribute, a pattern that looks FOR placeholders, or a line that carries its own reason
CLAIM = re.compile(r"READY_AND_OPERATIONAL|VERIFIED_LIVE|FULL_SUITE_VERIFIED|VERIFIED_ACTIVE|100% (?:Verified|Verification)|HARD LOCKDOWN INITIATED", re.I)
STATUS_CONSTANTS = {True, False, None}


def is_test(path):
    base = os.path.basename(path)
    return base.startswith("test_") or base.endswith(("_test.py", ".test.mjs", "_test.js")) or base in ("health_report.py", "master_test.py", "master_config_test.py", "master_link_test.py")


def code_lines(text, ext):
    if ext in (".c", ".h", ".cpp", ".js", ".mjs"):
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return [l for l in text.splitlines() if l.strip() and not l.strip().startswith("//")]
    return [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]


def body_without_doc(node):
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def classify_function(node):
    body = body_without_doc(node)
    if not body or all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis) for s in body):
        return "EMPTY"
    if any(isinstance(s, ast.Raise) and isinstance(s.exc, (ast.Call, ast.Name)) and "NotImplementedError" in ast.dump(s.exc) for s in body) and len(body) <= 2:
        return "NOT_IMPL"
    def is_print(s):
        return isinstance(s, ast.Expr) and isinstance(s.value, ast.Call) and getattr(s.value.func, "id", "") == "print"
    non_print = [s for s in body if not is_print(s)]
    if any(is_print(s) for s in body) and all(isinstance(s, ast.Return) and (s.value is None or isinstance(s.value, (ast.Constant, ast.Dict, ast.List, ast.JoinedStr))) for s in non_print):
        return "PRINT_ONLY"
    if len(body) == 1 and isinstance(body[0], ast.Return):
        v = body[0].value
        if v is None or (isinstance(v, ast.Constant) and (v.value in STATUS_CONSTANTS or isinstance(v.value, str))):
            if not node.args.args or True:
                return "CONSTANT" if (v is None or v.value in STATUS_CONSTANTS or (isinstance(v.value, str) and len(v.value) < 40 and re.search(r"READY|OK|SUCCESS|ACTIVE|VERIFIED|DONE|COMPLETE|OPERATIONAL", v.value, re.I))) else None
    return None


def is_data_only(path, text, ext):
    """A Python file that only assigns values (a config or a parameter file) is data, not a skeleton."""
    if ext != ".py":
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    def config_class(n):                       # class X: def __init__(self): self.a = ...   (a settings holder)
        return isinstance(n, ast.ClassDef) and all(isinstance(m, ast.FunctionDef) and m.name == "__init__" and all(isinstance(t, (ast.Assign, ast.AnnAssign, ast.Expr)) for t in m.body) for m in n.body if not isinstance(m, ast.Expr))
    return bool(tree.body) and all(isinstance(n, (ast.Assign, ast.AnnAssign, ast.Import, ast.ImportFrom)) or config_class(n) or (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant)) for n in tree.body)


def is_delegating(text, ext):
    """A small file whose function just hands the work to another module (return tool.x(...)) or gives an honest structured answer is a real wrapper, not a skeleton."""
    if ext != ".py":
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    return any(isinstance(n, ast.Return) and isinstance(n.value, (ast.Call, ast.Dict)) for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) for n in f.body)


def scan_python(path, text):
    findings = []
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return [{"kind": "SYNTAX_ERROR", "line": e.lineno or 0, "what": str(e.msg)}]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            k = classify_function(node) if "scan:ok" not in lines[node.lineno - 1] else None
            if k and not (node.name.startswith("__") and node.name.endswith("__")) and not (k == "EMPTY" and node.name.startswith("handle_")):
                findings.append({"kind": k, "line": node.lineno, "what": node.name + "()"})
        elif isinstance(node, ast.ClassDef):
            body = body_without_doc(node)
            is_exception = any(getattr(b, "id", getattr(b, "attr", "")).endswith(("Error", "Exception", "Full", "Warning")) for b in node.bases)
            if (not body or all(isinstance(s, ast.Pass) for s in body)) and not is_exception:
                findings.append({"kind": "EMPTY", "line": node.lineno, "what": "class " + node.name})
    return findings


def scan_text(path, text):
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        is_comment = line.lstrip().startswith(("#", "//", "/*", "*"))
        if (MARKER.search(line) or (is_comment and COMMENT_MARKER.search(line))) and not MARKER_IGNORE.search(line) and "stubs" not in os.path.basename(path):
            out.append({"kind": "MARKER", "line": i, "what": line.strip()[:110]})
        if CLAIM.search(line) and not re.search(r"\bnot\b|refus|never|instead of|removed|used to|old|honest", line, re.I):
            out.append({"kind": "CLAIM", "line": i, "what": line.strip()[:110]})
    return out


def scan_c_like(path, text):
    out = []
    for m in re.finditer(r"\b(?:void|int|float|double|char\s*\*?|bool|size_t|\w+_t)\s+(\w+)\s*\([^)]*\)\s*\{\s*(?:/\*.*?\*/|//[^\n]*|\s)*\}", text, flags=re.S):
        out.append({"kind": "EMPTY", "line": text.count("\n", 0, m.start()) + 1, "what": m.group(1) + "()"})
    for m in re.finditer(r"\b(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{\s*(?:/\*.*?\*/|//[^\n]*|\s)*\}", text, flags=re.S) if path.endswith((".js", ".mjs")) else []:
        if m.group(1) not in ("if", "for", "while", "switch", "catch", "function"):
            out.append({"kind": "EMPTY", "line": text.count("\n", 0, m.start()) + 1, "what": m.group(1) + "()"})
    return out


def scan_file(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    findings = scan_python(path, text) if ext == ".py" else scan_c_like(path, text)
    findings += scan_text(path, text)
    if len(code_lines(text, ext)) <= 3 and os.path.basename(path) != "__init__.py" and not is_data_only(path, text, ext) and not is_delegating(text, ext):
        findings.append({"kind": "TINY_FILE", "line": 1, "what": "%d line(s) of code" % len(code_lines(text, ext))})
    seen, uniq = set(), []
    for f in findings:
        key = (f["kind"], f["line"], f["what"])
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return sorted(uniq, key=lambda f: f["line"])


def engines():
    return sorted(d for d in os.listdir(SILO) if os.path.isdir(os.path.join(SILO, d)) and not d.startswith(("_", ".")) and d not in ("render",))


def scan_engine(name):
    folder = os.path.join(SILO, name)
    files, boiler = {}, 0
    for dp, dn, fn in os.walk(folder):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith("_backup")]
        for f in fn:
            if not f.lower().endswith(EXTS) or f == "__init__.py":
                continue
            p = os.path.join(dp, f)
            if is_test(p):
                continue
            if f in BOILERPLATE:
                boiler += 1
                continue
            fs = scan_file(p)
            if fs:
                files[os.path.relpath(p, folder).replace("\\", "/")] = fs
    counts = {}
    for fs in files.values():
        for f in fs:
            counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    return {"engine": name, "files_with_findings": len(files), "counts": counts, "files": files, "boilerplate_files": boiler}


def main(argv):
    write = "--write" in argv
    names = [a for a in argv if not a.startswith("--")] or engines()
    results = [scan_engine(n) for n in names]
    kinds = ["EMPTY", "PRINT_ONLY", "CONSTANT", "NOT_IMPL", "MARKER", "CLAIM", "TINY_FILE", "SYNTAX_ERROR"]
    print("%-24s %5s " % ("engine", "files") + " ".join("%8s" % k[:8] for k in kinds))
    for r in results:
        print("%-24s %5d " % (r["engine"], r["files_with_findings"]) + " ".join("%8d" % r["counts"].get(k, 0) for k in kinds))
    tot = {k: sum(r["counts"].get(k, 0) for r in results) for k in kinds}
    print("%-24s %5d " % ("TOTAL", sum(r["files_with_findings"] for r in results)) + " ".join("%8d" % tot[k] for k in kinds))
    if write:
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        with open(os.path.join(ROOT, "logs", "placeholders.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1)
        lines = ["# Placeholders and fakes, engine by engine", "",
                 "Generated by `python placeholder_scan.py --write`. A finding is a place that looks like working code but is empty, only prints, always returns the same answer, or says it is a placeholder.",
                 "`NOT_IMPL` entries are honest stubs (they raise when called). Everything else needs real code or a decision to remove it.", "",
                 "| Engine | Files | " + " | ".join(kinds[:7]) + " |", "|---|---:|" + "---:|" * 7]
        for r in results:
            lines.append("| %s | %d | " % (r["engine"], r["files_with_findings"]) + " | ".join(str(r["counts"].get(k, 0)) for k in kinds[:7]) + " |")
        for r in results:
            if not r["files"]:
                continue
            lines += ["", "## " + r["engine"], ""]
            for rel, fs in sorted(r["files"].items(), key=lambda kv: -len(kv[1])):
                lines.append("- `%s`: %s" % (rel, "; ".join("%s %s (line %d)" % (f["kind"], f["what"][:70], f["line"]) for f in fs[:6]) + (" ..." if len(fs) > 6 else "")))
        open(os.path.join(ROOT, "PLACEHOLDERS.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print("\nwrote PLACEHOLDERS.md and logs/placeholders.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
