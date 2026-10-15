"""setup_nexxus.py - first-run setup for a fresh copy of NEXXUS. Safe to run any time: it only creates what is missing and NEVER overwrites a file that exists.

    python setup_nexxus.py

It creates, next to this file:
  nexxus_env.bat     the governance secret shared by the hub and every engine (random, 64 hex characters), the hub URL, strict engine keys, PYTHONPATH
  nexxus_admin.bat   the admin token you type into the dashboard's padlock for overrides (random)
and the logs folder. Both .bat files are in .gitignore: they are yours and must never be committed or shared. The values are never printed; only the file names are.
Standard library only."""
import os
import secrets
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

ENV = """@echo off
REM nexxus_env.bat - shared settings for the NEXXUS server AND every engine. Created by setup_nexxus.py. Do not share or commit this file.
REM The secret must be IDENTICAL for the server and all engines.
set "NEXXUS_GOVERNANCE_SECRET={secret}"
set "NEXXUS_MESH_URL=http://127.0.0.1:{port}"
set "NEXXUS_REQUIRE_ENGINE_KEYS=1"
set "NEXXUS_PORT={port}"
for %%I in ("%~dp0.") do set "NEXXUS_HOME=%%~fI"
set "PYTHONPATH=%NEXXUS_HOME%;%PYTHONPATH%"
"""

ADMIN = """@echo off
REM nexxus_admin.bat - the admin token for overrides (Hard Lock, Release, Promote). Created by setup_nexxus.py. Type it into the padlock on the dashboard. Do not share or commit it.
set "NEXXUS_ADMIN_TOKEN={token}"
"""


def write_new(name, text):
    path = os.path.join(ROOT, name)
    if os.path.exists(path):
        print("  %-18s already exists, left untouched" % name)
        return False
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)
    print("  %-18s created (values are not shown)" % name)
    return True


def main():
    port = int(os.environ.get("NEXXUS_PORT") or 8000)
    print("NEXXUS setup in", ROOT)
    write_new("nexxus_env.bat", ENV.format(secret=secrets.token_hex(32), port=port))
    made = write_new("nexxus_admin.bat", ADMIN.format(token=secrets.token_urlsafe(24)))
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    if made:
        print("\nYour admin token is stored in nexxus_admin.bat (open that file to copy it into the dashboard's padlock). Keep it private.")
    print("Done. Next: START_NEXXUS.bat, then open http://localhost:%d/" % port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
