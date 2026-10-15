"""c_engine_check.py - static checks for the engines written in C, for a machine WITHOUT a C compiler. Nothing is compiled or run.

    python c_engine_check.py axis-drive [axis-phonetic ...]      (no arguments: every engine that contains .c files)

ERRORS (exit code 1): a quoted #include that resolves to no file, unbalanced braces or parentheses, a string literal broken across lines,
                      a function declared in a header that is defined nowhere in the engine.
WARNINGS: a .c file that is really C++ (iostream, std::, classes), a `while (1)` loop with nothing in it that waits or stops (it would burn a CPU core),
          the prebuilt .exe being older than the sources or not a Windows program.
A clean result means "consistent on paper", not "it compiles": only a compiler can say that.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SILO = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault")
SKIP = {"__pycache__", ".git", "node_modules"}
INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)
DECL = re.compile(r"^[ \t]*(?:[A-Za-z_][\w \t\*]*?)\b(\w+)\s*\([^;{}]*\)\s*;", re.M)
WAITS = re.compile(r"\b(sleep|Sleep|usleep|nanosleep|select|poll|recv|read|fgets|getchar|scanf|WaitFor\w*|break|return|exit)\b")


def strip(code):
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    return re.sub(r'"(?:\\.|[^"\\\n])*"', '""', code)


def files(folder, exts):
    for dp, dn, fn in os.walk(folder):
        dn[:] = [d for d in dn if d not in SKIP]
        for f in fn:
            if f.lower().endswith(exts):
                yield os.path.join(dp, f)


def loop_bodies(code):
    for m in re.finditer(r"\b(?:while\s*\(\s*(?:1|true)\s*\)|for\s*\(\s*;\s*;\s*\))\s*\{", code):
        depth, i = 1, m.end()
        while i < len(code) and depth:
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        yield code[m.end():i - 1]


def check_engine(name):
    folder = os.path.join(SILO, name)
    errors, warnings = [], []
    cfiles = sorted(files(folder, (".c",)))
    hfiles = sorted(files(folder, (".h",)))
    if not cfiles:
        return None
    all_defs = ""
    texts = {}
    for p in cfiles + hfiles:
        texts[p] = open(p, encoding="utf-8", errors="replace").read()
    for p in cfiles:
        all_defs += "\n" + strip(texts[p])
    rel = lambda p: os.path.relpath(p, folder)
    by_name = {}
    for p in cfiles + hfiles:
        by_name.setdefault(os.path.basename(p).lower(), []).append(p)
    for p in cfiles + hfiles:
        raw, code = texts[p], strip(texts[p])
        for inc in INCLUDE.findall(raw):
            target = os.path.normpath(os.path.join(os.path.dirname(p), inc))
            if not os.path.isfile(target):
                same = by_name.get(os.path.basename(inc).lower())
                hint = " (a file of that name exists at %s)" % rel(same[0]) if same else ""
                errors.append("%s: #include \"%s\" resolves to no file%s" % (rel(p), inc, hint))
        if code.count("{") != code.count("}") or code.count("(") != code.count(")"):
            errors.append("%s: unbalanced braces or parentheses" % rel(p))
        for i, l in enumerate(raw.splitlines(), 1):
            if l.count('"') % 2 == 1 and "//" not in l and "/*" not in l and "*/" not in l and "'\"'" not in l:
                errors.append("%s:%d: a string literal is broken across lines" % (rel(p), i))
                break
        if p.endswith(".c") and (re.search(r"#\s*include\s*<(iostream|string|vector)>", raw) or "std::" in raw or re.search(r"^\s*class\s+\w+", raw, re.M)):
            warnings.append("%s: this .c file contains C++ (it needs a C++ compiler, not a C one)" % rel(p))
        if p.endswith(".c"):
            for body in loop_bodies(code):
                if not WAITS.search(body):
                    warnings.append("%s: a `while (1)` loop with no sleep, wait, read or exit (it would use a whole CPU core)" % rel(p))
                    break
    for p in hfiles:
        for d in sorted(set(DECL.findall(strip(texts[p]))) - {"if", "while", "for", "switch", "return", "sizeof", "defined"}):
            if not re.search(r"\b%s\s*\([^;{}]*\)\s*\{" % re.escape(d), all_defs):
                errors.append("%s: %s() is declared but defined in no .c file" % (rel(p), d))
    for exe in files(folder, (".exe",)):
        parts = os.path.relpath(exe, folder).split(os.sep)
        if len(parts) > 1 and parts[0] not in ("build", "dist"):          # compiler toolchains and other tools kept in bin/ or libs/ are not this engine's build output
            continue
        data = open(exe, "rb").read(2)
        if data != b"MZ":
            errors.append("%s: not a Windows program" % rel(exe))
        elif max(os.path.getmtime(p) for p in cfiles + hfiles) > os.path.getmtime(exe):
            warnings.append("%s is older than the sources: rebuild it (no C compiler on this machine)" % rel(exe))
    return {"engine": name, "c_files": len(cfiles), "errors": errors, "warnings": warnings}


def main(argv):
    names = argv or sorted(d for d in os.listdir(SILO) if os.path.isdir(os.path.join(SILO, d)) and d.startswith("axis-"))
    bad = 0
    for n in names:
        r = check_engine(n)
        if r is None:
            continue
        bad += len(r["errors"])
        print("%-20s %2d .c file(s)   %d error(s)   %d warning(s)" % (n, r["c_files"], len(r["errors"]), len(r["warnings"])))
        for e in r["errors"]:
            print("    ERROR   " + e)
        for w in r["warnings"]:
            print("    warning " + w)
    print("\n%s" % ("CONSISTENT ON PAPER (not compiled)" if not bad else "%d error(s)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
