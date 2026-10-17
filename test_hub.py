"""The Academy workspace: 10 active slots per kind, the Work Safe vault, permanent purge, and the profile link."""
import os
import unittest

from flask import Flask, jsonify

import dashboard_hub as hub
import platform_mode as pm
from test_platform_mode import Base


class HubTest(Base):
    def fill(self, kind, n):
        return [hub.create(kind, "%s %d" % (kind, i)) for i in range(n)]

    def test_ten_active_slots_per_kind_and_a_clear_message_when_full(self):
        self.fill("dashboard", hub.MAX_ACTIVE)
        with self.assertRaisesRegex(hub.HubError, "Work Safe vault, or delete"):
            hub.create("dashboard", "one too many")
        hub.create("bot", "bots have their own ten")
        self.assertEqual(hub.slots()["dashboard"]["active"], 10)
        self.assertEqual(hub.slots()["bot"]["active"], 1)

    def test_work_safe_keeps_everything_intact_and_frees_the_slot(self):
        items = self.fill("dashboard", hub.MAX_ACTIVE)
        first = hub.update(items[0]["id"], note="my note", config={"widgets": ["telemetry", "tasks"]}, public=True)
        hub.shelve(first["id"])
        self.assertEqual(hub.slots()["dashboard"], {"active": 9, "max": 10, "safe": 1, "safe_max": hub.MAX_SAFE})
        kept = next(x for x in hub.snapshot()["items"] if x["id"] == first["id"])
        self.assertEqual((kept["state"], kept["note"], kept["config"]), ("safe", "my note", {"widgets": ["telemetry", "tasks"]}))
        self.assertEqual(hub.public_items(), [], "a resting item is never shown publicly")
        hub.create("dashboard", "takes the freed slot")
        with self.assertRaisesRegex(hub.HubError, "slots are in use"):
            hub.restore(first["id"])                                   # restoring needs a free slot
        hub.shelve(items[1]["id"])
        self.assertEqual(hub.restore(first["id"])["state"], "active")

    def test_purge_is_permanent_and_needs_the_exact_name(self):
        x = hub.create("bot", "Night Watcher", config={"k": 1})
        for wrong in ("", "night watcher", "Night"):
            with self.assertRaisesRegex(hub.HubError, "exact name"):
                hub.purge(x["id"], wrong)
        self.assertEqual(hub.purge(x["id"], "Night Watcher")["purged"], x["id"])
        self.assertEqual([i for i in hub.snapshot()["items"] if i["id"] == x["id"]], [])
        with self.assertRaises(hub.HubError):
            hub.restore(x["id"])
        with open(hub.STORE_PATH, encoding="utf-8") as f:
            self.assertNotIn("Night Watcher", f.read(), "nothing of it remains on disk")

    def test_validation(self):
        for bad in (("gizmo", "x"), ("dashboard", "  ")):
            with self.assertRaises(hub.HubError):
                hub.create(*bad)
        with self.assertRaisesRegex(hub.HubError, "not an engine"):
            hub.create("dashboard", "d", engine="made-up-engine")
        with self.assertRaises(hub.HubError):
            hub.create("dashboard", "d", config=["not", "an", "object"])
        with self.assertRaises(hub.HubError):
            hub.create("dashboard", "d", config={"big": "x" * 5000})
        self.assertEqual(hub.create("dashboard", "linked", engine="axis-core")["engine"], "axis-core")
        hub.set_engine_provider(lambda: None)                          # no telemetry: an engine cannot be verified, so it is refused
        with self.assertRaises(hub.HubError):
            hub.create("dashboard", "d2", engine="axis-core")

    def test_visitor_profile_shows_only_name_kind_and_engine_of_public_active_items(self):
        a = hub.create("dashboard", "Public One", note="secret note", engine="axis-link", config={"token": "x"}, public=True)
        hub.create("dashboard", "Private One")
        shown = pm.visitor_view()["dashboards"]
        self.assertEqual(shown, [{"name": "Public One", "kind": "dashboard", "engine": "axis-link"}])
        self.assertNotIn("secret note", str(pm.visitor_view()))
        self.assertIn("dashboards", pm.visitor_view()["sections"])
        hub.shelve(a["id"])
        self.assertNotIn("dashboards", pm.visitor_view())


class HubRoutesTest(Base):
    def setUp(self):
        super().setUp()
        app = Flask(__name__)
        pm.register_routes(app, lambda: True, lambda p, s=200: (jsonify(p), s))
        self.c = app.test_client()
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": true}')

    def test_roundtrip_through_the_routes(self):
        r = self.c.post("/api/platform/hub", json={"kind": "dashboard", "name": "Ops", "engine": "axis-core"}).get_json()
        hid = r["item"]["id"]
        self.assertEqual(r["slots"]["dashboard"]["active"], 1)
        self.assertEqual(self.c.post("/api/platform/hub/%s/shelve" % hid).get_json()["item"]["state"], "safe")
        self.assertEqual(self.c.post("/api/platform/hub/%s/restore" % hid).get_json()["item"]["state"], "active")
        self.assertEqual(self.c.post("/api/platform/hub/%s" % hid, json={"public": True}).get_json()["item"]["public"], True)
        self.assertEqual(self.c.post("/api/platform/hub/%s/explode" % hid).status_code, 404)
        self.assertEqual(self.c.delete("/api/platform/hub/%s" % hid, json={"confirm_name": "nope"}).status_code, 400)
        self.assertEqual(self.c.delete("/api/platform/hub/%s" % hid, json={"confirm_name": "Ops"}).status_code, 200)
        self.assertEqual(self.c.get("/api/platform/hub").get_json()["items"], [])

    def test_full_rotation_is_a_400_with_a_message_and_the_gate_still_applies(self):
        for i in range(hub.MAX_ACTIVE):
            self.assertEqual(self.c.post("/api/platform/hub", json={"kind": "bot", "name": "b%d" % i}).status_code, 200)
        r = self.c.post("/api/platform/hub", json={"kind": "bot", "name": "extra"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Work Safe", r.get_json()["message"])
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": false}')
        self.assertEqual(self.c.get("/api/platform/hub").status_code, 402)

    def test_the_slots_never_touch_the_local_node(self):
        import inspect
        src = inspect.getsource(hub)
        for word in ("subprocess", "os.system", "requests", "socket"):
            self.assertNotIn(word, src, "the hub only stores records; it must never act on your engines")


if __name__ == "__main__":
    unittest.main()
