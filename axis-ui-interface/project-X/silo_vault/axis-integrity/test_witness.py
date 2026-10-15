"""test_witness.py - the witness catches false claims and impossible sequences. Run: python test_witness.py"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from lib.auditor import Auditor  # noqa: E402
from witness import Witness, ghosts_in  # noqa: E402


def ev(n, kind, detail=""):
    return {"n": n, "engine": "axis-core", "kind": kind, "detail": detail}


def folder_with(*names):
    d = tempfile.mkdtemp(prefix="wit_")
    for name in names:
        open(os.path.join(d, name), "w").close()
    return d


class WitnessTests(unittest.TestCase):
    def setUp(self):
        self.aud = Auditor(os.path.join(tempfile.mkdtemp(prefix="wit_aud_"), "a.jsonl"))
        self.w = Witness(self.aud)

    def test_an_honest_purge_has_no_findings(self):
        d = folder_with("axis_switchboard.exe", "sender.exe")
        f = self.w.check([ev(1, "PURGE_REQUESTED", d), ev(2, "PURGE_DONE", d + ": 2 file(s)")])
        self.assertEqual(f, [])

    def test_a_purge_done_with_no_request_is_critical(self):
        d = folder_with()
        f = self.w.check([ev(1, "PURGE_DONE", d + ": 1 file(s)")])
        self.assertEqual([x["severity"] for x in f], ["CRITICAL"])
        self.assertIn("no PURGE_REQUESTED", f[0]["message"])

    def test_a_false_done_is_caught_by_looking_at_the_folder(self):
        d = folder_with("axis_switchboard.exe", "ghost.txt", "ghost2.dat")
        f = self.w.check([ev(1, "PURGE_REQUESTED", d), ev(2, "PURGE_DONE", d + ": 2 file(s)")])
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "CRITICAL")
        self.assertIn("ghost.txt", f[0]["message"])

    def test_a_missing_folder_is_a_warning(self):
        d = os.path.join(tempfile.gettempdir(), "wit_does_not_exist_xyz")
        f = self.w.check([ev(1, "PURGE_REQUESTED", d), ev(2, "PURGE_DONE", d + ": 0 file(s)")])
        self.assertEqual([x["severity"] for x in f], ["WARNING"])

    def test_a_report_only_purge_that_removed_something_is_caught(self):
        d = folder_with("ghost.txt")
        self.w.check([ev(1, "PURGE_REPORT_ONLY", d)])
        os.remove(os.path.join(d, "ghost.txt"))                           # something deleted it although only a report was asked for
        f = self.w.check([ev(2, "SECURITY_ARMING"), ev(3, "SECURITY_ARMED")])
        self.assertEqual([x["severity"] for x in f], ["CRITICAL"])
        self.assertIn("ghost.txt", f[0]["message"])

    def test_an_unfinished_request_becomes_a_warning_after_the_time_limit(self):
        t = [1000.0]
        w = Witness(self.aud, now=lambda: t[0], unfinished_after=60)
        d = folder_with()
        self.assertEqual(w.check([ev(1, "PURGE_REQUESTED", d)]), [])
        t[0] += 120
        f = w.check([])
        self.assertEqual([x["severity"] for x in f], ["WARNING"])
        self.assertIn("never finished", f[0]["message"])

    def test_the_security_sequence(self):
        self.assertEqual(self.w.check([ev(1, "SECURITY_ARMING"), ev(2, "SECURITY_ARMED")]), [])
        self.assertEqual([x["severity"] for x in self.w.check([ev(3, "SECURITY_ARMED")])], ["WARNING"])
        self.assertEqual([x["severity"] for x in self.w.check([ev(4, "SECURITY_ARM_FAILED", "lock not active")])], ["WARNING"])

    def test_findings_are_written_into_the_tamper_evident_chain(self):
        d = folder_with("ghost.txt")
        self.w.check([ev(1, "PURGE_REQUESTED", d), ev(2, "PURGE_DONE", d + ": 1 file(s)")])
        kinds = [e["kind"] for e in self.aud.events()]
        self.assertIn("FINDING:CRITICAL", kinds)
        self.assertTrue(self.aud.verify()[0])

    def test_ghosts_in_follows_the_purge_rule(self):
        d = folder_with("axis_switchboard.exe", "sender.exe", "a.txt")
        os.mkdir(os.path.join(d, "sub"))
        open(os.path.join(d, "sub", "inner.txt"), "w").close()
        self.assertEqual(ghosts_in(d), ["a.txt"])                          # allowed files and sub-folders do not count
        self.assertIsNone(ghosts_in(os.path.join(d, "nope")))

    def test_a_windows_style_folder_with_a_colon_is_read_correctly(self):
        from witness import _folder
        self.assertEqual(_folder("C:\\Users\\x\\core: 3 file(s)"), "C:\\Users\\x\\core")
        self.assertEqual(_folder("C:\\Users\\x\\core"), "C:\\Users\\x\\core")
        self.assertEqual(_folder("C:\\a: -1 file(s)"), "C:\\a")


if __name__ == "__main__":
    unittest.main(verbosity=1)
