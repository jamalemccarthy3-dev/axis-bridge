import os
import tempfile
import unittest

import operator_scope as sc


class ScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        sc.GRANTS_PATH = os.path.join(self.tmp, "state", "g.json")
        sc.AUDIT_PATH = os.path.join(self.tmp, "logs", "a.jsonl")
        self.ok = os.path.join(self.tmp, "ok")
        self.other = os.path.join(self.tmp, "ok_sibling")
        os.makedirs(self.ok)
        os.makedirs(self.other)

    def test_deny_by_default(self):
        self.assertFalse(sc.check(self.ok)[0])
        with self.assertRaises(PermissionError):
            sc.require(self.ok)

    def test_inside_allowed_outside_refused(self):
        self.assertTrue(sc.grant(self.ok)[0])
        self.assertTrue(sc.check(os.path.join(self.ok, "a", "b.txt"))[0])
        self.assertFalse(sc.check(self.other)[0])              # prefix-lookalike sibling
        self.assertFalse(sc.check(self.tmp)[0])                # parent
        self.assertFalse(sc.check(os.path.join(self.ok, "..", "ok_sibling"))[0])   # dot-dot escape

    def test_revoke_is_immediate(self):
        sc.grant(self.ok)
        sc.revoke(self.ok)
        self.assertFalse(sc.check(self.ok)[0])

    def test_cannot_grant_root_home_or_missing(self):
        self.assertFalse(sc.grant(os.path.abspath(os.sep))[0])
        self.assertFalse(sc.grant("~")[0])
        self.assertFalse(sc.grant(os.path.join(self.tmp, "nope"))[0])

    def test_symlink_escape(self):
        link = os.path.join(self.ok, "link")
        sc.grant(self.ok)
        try:
            os.symlink(self.other, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not permitted here")
        self.assertFalse(sc.check(link)[0])

    def test_audit_written(self):
        sc.check(self.ok)
        self.assertTrue(os.path.getsize(sc.AUDIT_PATH) > 0)


if __name__ == "__main__":
    unittest.main()
