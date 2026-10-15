"""test_protocol.py - omni_protocol.py. Run: python test_protocol.py"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from omni_protocol import OmniProtocol, OmniProtocolError  # noqa: E402


class Protocol(unittest.TestCase):
    def setUp(self):
        self.o = OmniProtocol()

    def test_mirroring_says_back_what_was_understood(self):
        r = self.o.apply_active_mirroring("  make   a logo ")
        self.assertEqual(r, 'Received: "make a logo". Confirming alignment: Is this the correct interpretation?')

    def test_the_combined_output_has_the_three_lines_in_order(self):
        lines = self.o.process_communication("build a page").split("\n")
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("Received:"))
        self.assertIn("[Sandbox Workbench] Context: build a page.", lines[1])
        self.assertTrue(lines[2].startswith("[Intent Log]"))

    def test_input_is_held_unvalidated_until_a_person_confirms(self):
        r = self.o.process("delete nothing")
        self.assertEqual(self.o.pending(), {r["held_id"]: "delete nothing"})
        self.assertFalse(self.o.is_validated(r["held_id"]))
        self.assertEqual(self.o.validate(r["held_id"]), "delete nothing")
        self.assertTrue(self.o.is_validated(r["held_id"]))
        self.assertEqual(self.o.pending(), {})

    def test_rejecting_removes_the_held_input(self):
        r = self.o.process("something wrong")
        self.assertEqual(self.o.reject(r["held_id"]), "something wrong")
        self.assertFalse(self.o.is_validated(r["held_id"]))
        with self.assertRaises(KeyError):
            self.o.validate(r["held_id"])

    def test_unknown_ids_are_refused(self):
        with self.assertRaises(KeyError):
            self.o.validate(99)
        with self.assertRaises(KeyError):
            self.o.reject(99)

    def test_bad_input_is_refused_not_guessed_at(self):
        for bad in ("", "   ", None, 5, "x" * 2001):
            with self.assertRaises(OmniProtocolError):
                self.o.process_communication(bad)
        self.assertEqual(self.o.pending(), {})                   # a refused input is never held

    def test_each_input_gets_its_own_id(self):
        a, b = self.o.process("one"), self.o.process("two")
        self.assertNotEqual(a["held_id"], b["held_id"])
        self.assertEqual(len(self.o.pending()), 2)

    def test_the_old_cpp_names_still_work(self):
        self.assertEqual(self.o.applyActiveMirroring("x"), self.o.apply_active_mirroring("x"))
        self.assertTrue(self.o.processCommunication("x").startswith("Received:"))
        self.assertIn("Goal detected", self.o.separateIntentFromMechanics("x"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
