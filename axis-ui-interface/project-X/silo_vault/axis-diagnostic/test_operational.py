"""test_operational.py - is axis-diagnostic operational? Imports every module and creates every tool. Run: python test_operational.py"""
import importlib
import inspect
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("NEXXUS_MESH_URL", "http://127.0.0.1:9")
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def modules():
    for dp, dn, fn in os.walk(os.path.join(ROOT, "src")):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in fn:
            if f.endswith(".py") and f != "__init__.py":
                yield os.path.relpath(os.path.join(dp, f), ROOT)[:-3].replace(os.sep, ".")


class Operational(unittest.TestCase):
    def test_every_module_imports(self):
        bad = {}
        for m in modules():
            try:
                importlib.import_module(m)
            except Exception as e:
                bad[m] = "%s: %s" % (type(e).__name__, str(e)[:100])
        self.assertEqual(bad, {})

    def test_every_tool_can_be_created(self):
        bad = {}
        for m in modules():
            if not m.endswith("_tool"):
                continue
            mod = importlib.import_module(m)
            for name, cls in inspect.getmembers(mod, inspect.isclass):
                if cls.__module__ == m and name.endswith("tool"):
                    try:
                        cls()
                    except Exception as e:
                        bad["%s.%s" % (m, name)] = "%s: %s" % (type(e).__name__, str(e)[:100])
        self.assertEqual(bad, {})


if __name__ == "__main__":
    unittest.main(verbosity=1)
