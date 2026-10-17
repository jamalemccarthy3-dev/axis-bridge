"""The private side: Talk to NEXXUS auto-save and archive, the messaging hub's honesty, and the wall to the public side."""
import os
import time
import unittest

from flask import Flask, jsonify

import platform_mode as pm
import private_hub as ph
import privacy
from test_platform_mode import Base

HERE = os.path.dirname(os.path.abspath(__file__))


class StoreTest(Base):
    def test_every_message_is_saved_the_moment_it_is_sent_and_names_the_conversation(self):
        s = ph.new_session()
        ph.add_message(s["id"], "me", "How do I read an error message?")
        ph.add_message(s["id"], "ai", "Start with the first line.")
        got = ph.get(s["id"])
        self.assertEqual([m["who"] for m in got["messages"]], ["me", "ai"])
        self.assertEqual(got["title"], "How do I read an error message?")

    def test_validation_and_caps(self):
        s = ph.new_session()
        for bad in (("robot", "x"), ("me", "   ")):
            with self.assertRaises(ph.TalkError):
                ph.add_message(s["id"], *bad)
        with self.assertRaises(ph.TalkError):
            ph.add_message("nope", "me", "x")
        self.assertEqual(len(ph.get(ph.add_message(s["id"], "me", "x" * 9000)["id"])["messages"][0]["text"]), ph.MAX_TEXT)

    def test_archive_groups_by_day(self):
        now = time.time()
        for label, age in (("Today", 60), ("Yesterday", 86400 + 60), ("Earlier this week", 3 * 86400), ("Older", 20 * 86400)):
            s = ph.new_session()
            ph.add_message(s["id"], "me", "msg " + label)
            sessions = ph._read()
            for x in sessions:
                if x["id"] == s["id"]:
                    x["updated"] = int(now - age)
            ph._write(sessions)
        a = ph.archive(now)
        self.assertEqual([g["label"] for g in a["groups"]], ["Today", "Yesterday", "Earlier this week", "Older"])
        self.assertEqual(ph.archive(now)["groups"][0]["items"][0]["title"], "msg Today")

    def test_empty_sessions_are_not_listed_and_delete_is_permanent(self):
        blank = ph.new_session()
        s = ph.new_session()
        ph.add_message(s["id"], "me", "secret plan for tomorrow")
        self.assertEqual([i["id"] for g in ph.archive()["groups"] for i in g["items"]], [s["id"]])
        ph.delete(s["id"])
        with self.assertRaises(ph.TalkError):
            ph.get(s["id"])
        with open(ph.STORE_PATH, encoding="utf-8") as f:
            self.assertNotIn("secret plan", f.read())
        self.assertTrue(blank["id"])


class RoutesTest(Base):
    def setUp(self):
        super().setUp()
        self.local = True
        app = Flask(__name__)
        pm.register_routes(app, lambda: self.local, lambda p, s=200: (jsonify(p), s))
        self.c = app.test_client()
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": true}')

    def test_roundtrip(self):
        sid = self.c.post("/api/platform/private/talk").get_json()["session"]["id"]
        self.assertEqual(self.c.post("/api/platform/private/talk/%s/message" % sid, json={"who": "me", "text": "hello"}).get_json()["saved"], 1)
        self.assertEqual(self.c.post("/api/platform/private/talk/%s/message" % sid, json={"who": "ai", "text": "hi", "cls": "err"}).get_json()["saved"], 2)
        a = self.c.get("/api/platform/private/talk").get_json()
        self.assertEqual(a["current"]["id"], sid)
        self.assertIn("never posted", a["statement"])
        self.assertEqual(self.c.get("/api/platform/private/talk/" + sid).get_json()["session"]["messages"][1]["cls"], "err")
        self.assertEqual(self.c.delete("/api/platform/private/talk/" + sid).status_code, 200)
        self.assertEqual(self.c.get("/api/platform/private/talk/" + sid).status_code, 404)

    def test_other_devices_and_a_locked_account_get_nothing(self):
        self.local = False
        for method, url in (("get", "/api/platform/private/talk"), ("post", "/api/platform/private/talk"), ("get", "/api/platform/private/hub")):
            self.assertEqual(getattr(self.c, method)(url).status_code, 403, url)
        self.local = True
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": false}')
        self.assertEqual(self.c.get("/api/platform/private/talk").status_code, 402)

    def test_the_hub_is_honest_that_nothing_between_people_exists_yet(self):
        h = self.c.get("/api/platform/private/hub").get_json()
        self.assertIn("100% private", h["statement"])
        self.assertIn("Post & Publish", h["statement"])
        self.assertEqual([s["id"] for s in h["sections"]], ["friends", "messages", "groups", "calls"])
        self.assertTrue(all(s["available"] is False for s in h["sections"]), "no fake friends, chats or calls")

    def test_a_private_conversation_never_reaches_a_public_surface(self):
        sid = self.c.post("/api/platform/private/talk").get_json()["session"]["id"]
        self.c.post("/api/platform/private/talk/%s/message" % sid, json={"who": "me", "text": "my-private-marker-123"})
        everything = ""
        for url in ("/api/platform/state", "/api/platform/public", "/api/platform/profile/public", "/api/platform/ranks", "/api/platform/vault"):
            r = self.c.get(url)
            everything += r.get_data(as_text=True)
        self.assertNotIn("my-private-marker-123", everything)


class WallTest(unittest.TestCase):
    def test_the_store_lives_in_the_private_folder_and_public_modules_do_not_read_it(self):
        src = open(os.path.join(HERE, "private_hub.py"), encoding="utf-8").read()
        self.assertIn("STORE_PATH = os.path.join(privacy.PRIVATE_DIR", src)
        for name in ("github_sync.py", "ranks.py", "marketplace_export.py", "seo.py"):
            self.assertNotIn("private_hub", open(os.path.join(HERE, name), encoding="utf-8").read(), name)


if __name__ == "__main__":
    unittest.main()
