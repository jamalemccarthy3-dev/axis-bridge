"""test_operational.py - is axis-triage operational? Run: python test_operational.py
Tests the gate, the sanitiser, the sync check, the packet delivery and the controller pipeline, using temporary folders for anything written."""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("NEXXUS_MESH_URL", "http://127.0.0.1:9")
os.chdir(ROOT)
sys.path.insert(0, ROOT)


class Operational(unittest.TestCase):
    def test_every_module_imports(self):
        bad = {}
        for m in ("sanatizer", "triage_gate", "sync_manager", "task_runner", "grid_controller", "master_config", "lib.grid_controller_tool", "lib.sanatizer_tool",
                  "lib.sync_manager_tool", "lib.task_runner_tool", "lib.triage_gate_tool"):
            try:
                importlib.import_module(m)
            except Exception as e:
                bad[m] = "%s: %s" % (type(e).__name__, e)
        self.assertEqual(bad, {})

    def test_sanitizer_removes_forbidden_characters(self):
        from sanatizer import Sanitizer
        self.assertEqual(Sanitizer().process("  <b>hi</b>; $x  "), "bhi/b x")        # < > ; $ { } are removed, the ends trimmed

    def test_gate_redacts_blocked_patterns_in_any_case_and_checks_the_route(self):
        from triage_gate import TriageGate
        g = TriageGate()
        out = g.run("select 1; DROP TABLE users", "axis-llm")
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("DROP TABLE", out)
        self.assertIsNone(g.run("hello", "axis-does-not-exist"))

    def test_sync_detects_both_directions(self):
        from sync_manager import SyncManager
        root = tempfile.mkdtemp(prefix="grid_")
        for name in ("axis-llm", "axis-brand-new"):
            os.makedirs(os.path.join(root, name))
        d = SyncManager(root).run_sync()
        self.assertIn("axis-brand-new", d)                                  # on disk, not in the map
        self.assertTrue(any(x.startswith("MISSING_ON_DISK:") for x in d))   # in the map, not on disk
        self.assertEqual(SyncManager().run_sync(), [])                      # the real grid is in sync

    def test_packets_are_really_delivered_and_paths_cannot_escape(self):
        from task_runner import TaskRunner
        root = tempfile.mkdtemp(prefix="grid_")
        os.makedirs(os.path.join(root, "axis-llm"))
        r = TaskRunner(root)
        self.assertTrue(r.run_task("axis-llm", {"hello": "world"}))
        files = os.listdir(os.path.join(root, "axis-llm", "triage_inbox"))
        self.assertEqual(len(files), 1)
        self.assertEqual(json.load(open(os.path.join(root, "axis-llm", "triage_inbox", files[0]), encoding="utf-8"))["packet"], {"hello": "world"})
        self.assertFalse(r.run_task("..", {"x": 1}))                         # outside the grid
        self.assertFalse(r.run_task(os.path.dirname(root), {"x": 1}))        # an absolute path outside the grid
        self.assertFalse(r.run_task("no-such-node", {"x": 1}))               # does not exist
        self.assertFalse(r.run_task(".", {"x": 1}))                          # the root itself

    def test_the_pipeline_only_forwards_what_passes_the_gate(self):
        from grid_controller import GridController
        seen = []
        c = GridController(search=lambda q: "result for %s; DROP TABLE x" % q, llm=lambda s: seen.append(s) or "ok")
        self.assertTrue(c.execute_cycle("cats", "axis-llm"))
        self.assertIn("[REDACTED]", seen[0])
        self.assertFalse(c.execute_cycle("cats", "axis-nowhere"))
        self.assertEqual(len(seen), 1)                                       # the refused route never reached the LLM
        with self.assertRaises(RuntimeError):
            GridController().execute_cycle("x", "axis-llm")

    def test_the_controller_health_pass(self):
        from grid_controller import GridController
        s = GridController().main_loop()
        self.assertEqual(s["discrepancies"], [])
        self.assertTrue(s["llm_registered"] and s["search_registered"])

    def test_master_test_and_master_config_run(self):
        for script in ("master_test.py", "master_config.py"):
            r = subprocess.run([sys.executable, script], cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, script + ": " + r.stdout[-300:])


if __name__ == "__main__":
    unittest.main(verbosity=1)
