import os
import tempfile
import unittest

import context_guard as cg


class ContextGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        cg.STATE_DIR = self.tmp
        cg.STATE_PATH = os.path.join(self.tmp, "s.json")
        cg.TRANSCRIPT_PATH = os.path.join(self.tmp, "t.jsonl")
        cg.HANDOFF_DIR = os.path.join(self.tmp, "handoffs")
        os.environ["NEXXUS_CONTEXT_BUDGET_TOKENS"] = "1000"

    def test_quiet_below_threshold(self):
        self.assertIsNone(cg.record_turn("hi", "hello"))
        self.assertEqual(cg.status()["level"], "ok")

    def test_fires_once_saves_then_notice(self):
        hit = None
        for i in range(40):
            r = cg.record_turn("question %d " % i + "x" * 200, "answer " + "y" * 200)
            if r:
                self.assertIsNone(hit, "must fire only once")
                hit = r
        self.assertIsNotNone(hit)
        self.assertEqual(hit["notice"], cg.NOTICE)
        self.assertTrue(os.path.isfile(hit["handoff"]))
        self.assertIn("Operator:", hit["continuation_prompt"])
        self.assertIn(cg.status()["level"], ("warn", "full"))

    def test_save_failure_is_reported_honestly(self):
        cg.HANDOFF_DIR = os.path.join(self.tmp, "t.jsonl", "nope")  # a file in the way
        open(cg.TRANSCRIPT_PATH, "a").close()
        r = None
        for i in range(10):
            r = cg.record_turn("q" * 400, "a" * 400) or r
        self.assertFalse(r["saved"])
        self.assertEqual(r["notice"], cg.NOTICE_SAVE_FAILED)

    def test_new_window_resets(self):
        for i in range(10):
            cg.record_turn("q" * 400, "a" * 400)
        s = cg.start_new_window()
        self.assertEqual((s["turns"], s["level"]), (0, "ok"))
        self.assertIn("no earlier", cg.continuation_prompt())


if __name__ == "__main__":
    unittest.main()
