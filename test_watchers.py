import json
import os
import re
import tempfile
import time
import unittest

import watchers as w

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = 1_800_000_000


def put(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


class WatcherTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        w.EVENTS_PATH = os.path.join(d, "events.jsonl")
        w.PULL_STATS_PATH = os.path.join(d, "pulls.jsonl")
        w.OPERATOR_AUDIT = os.path.join(d, "op.jsonl")
        w.CAPTURE_AUDIT = os.path.join(d, "cap.jsonl")
        w.FINDINGS_PATH = os.path.join(d, "findings.jsonl")

    def test_quiet_when_normal(self):
        put(w.EVENTS_PATH, [{"e": "page_view", "t": NOW - 5, "i": "a" * 32}] * 5)
        put(w.OPERATOR_AUDIT, [{"ts": NOW - 5, "allowed": False, "action": "access"}] * 3)
        self.assertEqual(w.scan(NOW), [])

    def test_flood_churn_reject_probing_all_fire(self):
        put(w.EVENTS_PATH, [{"e": "page_view", "t": NOW - 30, "i": "f" * 32}] * 150 + [{"e": "page_view", "t": NOW - 20, "i": "%032x" % n} for n in range(250)])
        put(w.PULL_STATS_PATH, [{"t": NOW - 60, "received": 100, "dropped": 60}])
        put(w.OPERATOR_AUDIT, [{"ts": NOW - 30, "allowed": False, "action": "access"}] * 12)
        put(w.CAPTURE_AUDIT, [{"ts": NOW - 30, "allowed": False, "action": "screen_snapshot"}] * 6)
        rules = sorted(f["rule"] for f in w.scan(NOW))
        self.assertEqual(rules, ["capture_probing", "id_churn", "operator_probing", "reject_rate", "relay_flood"])

    def test_cooldown_and_notifier(self):
        put(w.CAPTURE_AUDIT, [{"ts": NOW - 30, "allowed": False}] * 6)
        got = []
        self.assertEqual(len(w.scan(NOW, got.append)), 1)
        self.assertEqual(len(w.scan(NOW + 60, got.append)), 0, "same finding is not repeated inside the cooldown")
        self.assertEqual(len(w.scan(NOW + 4000, got.append)), 0, "events aged out of the window by then")
        put(w.CAPTURE_AUDIT, [{"ts": NOW + 3700, "allowed": False}] * 6)
        self.assertEqual(len(w.scan(NOW + 3800, got.append)), 1, "fires again after the cooldown")
        self.assertEqual(len(got), 2)

    def test_findings_hold_no_identity_and_say_nothing_was_blocked(self):
        put(w.EVENTS_PATH, [{"e": "page_view", "t": NOW - 30, "i": "abcdef12" + "0" * 24}] * 150)
        f = w.scan(NOW)[0]
        self.assertEqual(f["subject"], "abcdef12")
        self.assertNotIn("0" * 24, json.dumps(f))
        self.assertIn("Nothing was blocked", f["suggestion"])

    def test_a_broken_bot_does_not_stop_the_others(self):
        put(w.CAPTURE_AUDIT, [{"ts": NOW - 30, "allowed": False}] * 6)
        orig = w.BOTS
        w.BOTS = (lambda now: 1 / 0,) + orig
        try:
            self.assertEqual(len(w.scan(NOW)), 1)
        finally:
            w.BOTS = orig

    def test_watchers_cannot_kill_or_block(self):
        src = open(os.path.join(HERE, "watchers.py"), encoding="utf-8").read()
        code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith(("#", '"""')))
        imports = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z_][\w]*)", code, re.M))
        self.assertFalse(imports & {"subprocess", "signal", "shutil", "socket", "ctypes", "multiprocessing", "psutil"}, imports)
        self.assertNotRegex(code, r"os\.(kill|killpg|system|remove|unlink|rmdir|popen|spawn)")


if __name__ == "__main__":
    unittest.main()
