"""c_compile_check.py - really compiles every .c file of the C engines (to a temporary folder, nothing is kept or run) and reports the compiler's errors.

    python c_compile_check.py [engine ...]

It needs a C compiler. It uses, in this order: the command in the environment variable C_COMPILER (for example "gcc"), a gcc/cc/clang on PATH,
or Zig's bundled clang (`python -m ziglang cc`, from `pip install ziglang`; point PYTHONPATH at the folder you installed it in).
Each file is compiled on its own (`-c`), so one broken file never hides the others. Exit code 0 only when every file compiles.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SILO = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault")
SKIP = {"__pycache__", ".git", "node_modules", "bin", "libs", "build", "dist"}


def find_compiler():
    env = os.environ.get("C_COMPILER")
    if env:
        return env.split()
    for name in ("gcc", "cc", "clang"):
        path = shutil.which(name)
        if path:
            probe = subprocess.run([path, "-fsyntax-only", "-x", "c", "-"], input="int main(void){return 0;}", capture_output=True, text=True)
            if probe.returncode == 0:                                   # a driver without its compiler proper (cc1) does not count
                return [path]
    probe = subprocess.run([sys.executable, "-m", "ziglang", "version"], capture_output=True, text=True)
    return [sys.executable, "-m", "ziglang", "cc"] if probe.returncode == 0 else None


def c_files(folder):
    for dp, dn, fn in os.walk(folder):
        dn[:] = [d for d in dn if d not in SKIP]
        for f in fn:
            if f.endswith((".c", ".cpp")):
                yield os.path.join(dp, f)


def compile_engine(cc, name):
    folder = os.path.join(SILO, name)
    files = sorted(c_files(folder))
    if not files:
        return None
    incs = sorted({os.path.dirname(f) for f in files} | {folder, os.path.join(folder, "src"), os.path.join(folder, "lib")})
    flags = ["-c", "-Wall", "-Wno-unused-function"] + ["-I" + d for d in incs if os.path.isdir(d)]
    out = tempfile.mkdtemp(prefix="cc_")
    results = {}
    for f in files:
        # a .c file that is really C++ is compiled as C++ (and said to be so): the file name is the problem, not the code
        text = open(f, encoding="utf-8", errors="replace").read()
        is_cpp = f.endswith(".cpp") or "<iostream>" in text or "std::" in text
        base = list(cc)
        if is_cpp and base[-1] == "cc" and "ziglang" in base:
            base[-1] = "c++"                       # Zig ships its C++ library only behind `zig c++`
        cmd = base + (["-x", "c++"] if is_cpp else []) + flags + ["-o", os.path.join(out, "x.o"), f]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        msgs = [l for l in r.stderr.splitlines() if "error:" in l or "fatal error:" in l]
        warns = [l for l in r.stderr.splitlines() if "warning:" in l]
        results[os.path.relpath(f, folder)] = {"ok": r.returncode == 0, "cpp": is_cpp, "errors": msgs[:4], "warnings": len(warns)}
    shutil.rmtree(out, ignore_errors=True)
    return results


def main(argv):
    cc = find_compiler()
    if not cc:
        print("No working C compiler found (set C_COMPILER, or pip install ziglang and put it on PYTHONPATH).")
        return 2
    names = argv or sorted(d for d in os.listdir(SILO) if os.path.isdir(os.path.join(SILO, d)) and not d.startswith(("_", ".")))
    bad = 0
    for n in names:
        res = compile_engine(cc, n)
        if res is None:
            continue
        broken = {k: v for k, v in res.items() if not v["ok"]}
        bad += len(broken)
        print("%-20s %2d file(s)  %d compile error file(s)  %d warning(s)" % (n, len(res), len(broken), sum(v["warnings"] for v in res.values())))
        for k, v in broken.items():
            print("    FAIL %s%s" % (k, "  (C++)" if v["cpp"] else ""))
            for e in v["errors"]:
                print("         " + e[-170:])
        cpp = [k for k, v in res.items() if v["cpp"] and v["ok"] and k.endswith(".c")]
        if cpp:
            print("    note: compiles only as C++: %s (rename to .cpp)" % ", ".join(cpp))
    print("\n%s" % ("EVERYTHING COMPILES" if not bad else "%d file(s) do not compile" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
