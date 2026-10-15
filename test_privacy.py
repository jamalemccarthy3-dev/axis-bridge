"""The wall between private conversations and everything public. If one of these fails, a private path has been wired into a public one."""
import os
import re
import unittest

import privacy
import telemetry_hub

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_MODULES = ("github_sync.py", "ranks.py", "platform_mode.py", "telemetry_hub.py", "watchers.py", "site_server.py", "teams.py", "academy.py")
PRIVATE_WORDS = ("direct_message", "group_chat", "room_session", "room_signal", "nexxus_talk", "nexxus_data/private", "nexxus_data\\private", "PRIVATE_DIR", "PRIVATE_KINDS")


def source(name):
    return open(os.path.join(HERE, name), encoding="utf-8").read()


class GateTest(unittest.TestCase):
    def test_private_kinds_can_never_enter_a_public_path(self):
        for kind in privacy.PRIVATE_KINDS:
            item = {"kind": kind, "visibility": "private", "text": "hello"}
            with self.assertRaises(privacy.PrivacyViolation):
                privacy.require_public(item, "test")
            with self.assertRaises(privacy.PrivacyViolation):
                privacy.public_only([{"kind": "public_post", "visibility": "public"}, item], "test")

    def test_a_private_item_cannot_pretend_to_be_public(self):
        for liar in ({"kind": "direct_message", "visibility": "public"}, {"kind": "group_chat", "visibility": "public"}, {"kind": "room_session", "visibility": "public"}):
            with self.assertRaises(privacy.PrivacyViolation):
                privacy.require_public(liar, "test")

    def test_unmarked_items_are_not_public(self):
        for bad in ({}, {"kind": "public_post"}, {"kind": "public_post", "visibility": "private"}, {"visibility": "public"}, "text", None):
            with self.assertRaises(privacy.PrivacyViolation):
                privacy.require_public(bad, "test")

    def test_public_items_pass(self):
        self.assertTrue(privacy.is_public(privacy.as_public_post({"id": "a", "text": "hi"})))
        self.assertTrue(privacy.is_public(privacy.as_public_comment("a", {"id": "c", "text": "yo"})))

    def test_public_shapes_carry_no_ratings_or_private_fields(self):
        post = privacy.as_public_post({"id": "a", "t": 1, "text": "hi", "rating": 5, "comments": [{"text": "x"}], "vault": "secret", "public": True})
        self.assertEqual(set(post), {"kind", "visibility", "id", "t", "text", "url", "media", "gh"})


class BoundaryTest(unittest.TestCase):
    def test_no_public_module_mentions_a_private_store_or_kind(self):
        for name in PUBLIC_MODULES:
            src = source(name)
            for word in PRIVATE_WORDS:
                self.assertNotIn(word, src, "%s references the private world (%r)" % (name, word))

    def test_the_private_folder_is_not_inside_any_public_data_folder(self):
        self.assertFalse(privacy.PRIVATE_DIR.startswith(os.path.join(HERE, "nexxus_data", "platform")))
        self.assertFalse(privacy.PRIVATE_DIR.startswith(os.path.join(HERE, "nexxus_data", "telemetry")))

    def test_the_private_folder_is_gitignored(self):
        self.assertRegex(source(".gitignore"), r"(?m)^nexxus_data/private/\s*$")

    def test_telemetry_can_never_carry_content(self):
        self.assertEqual(telemetry_hub.FIELDS, {"e", "t", "v", "i", "s", "w", "x"})
        for name in telemetry_hub.EVENTS:
            self.assertFalse(re.search(r"message|chat|dm|room|call|post|comment|text", name), "telemetry event %s hints at content" % name)

    def test_the_public_code_paths_use_the_gate(self):
        wall = source("platform_mode.py")
        self.assertIn('privacy.require_public(privacy.as_public_post(p), "the public wall")', wall)
        self.assertIn("privacy.require_public(privacy.as_public_comment", wall)
        sync = source("github_sync.py")
        self.assertIn("privacy.require_public", sync)
        self.assertNotIn("import ranks", sync)

    def test_rank_points_come_only_from_the_ledger_rules(self):
        src = source("ranks.py")
        self.assertIn("RULES", src)
        for forbidden in ("platform_mode", "github_sync", "privacy.PRIVATE", "requests", "urllib"):
            self.assertNotIn(forbidden, src, "ranks.py must stay a closed, auditable ledger (%s)" % forbidden)


if __name__ == "__main__":
    unittest.main()
