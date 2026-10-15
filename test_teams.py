"""Team workspaces, the welcome manifest, shared posts and the Talk-to-NEXXUS privacy rule."""
import json
import os
import re
import time
import unittest

from flask import Flask, jsonify

import academy
import platform_mode as pm
import privacy
import ranks
import teams
from test_platform_mode import Base

HERE = os.path.dirname(os.path.abspath(__file__))
TELEMETRY = {"hub": {"uptime_s": 12.5, "cpu_percent": 3.0, "rss_mb": 120.0, "threads": 9},
             "engines": {"axis-core": {"found": True, "mesh_ready": True}, "axis-link": {"found": True, "mesh_ready": False}, "axis-gone": {"found": False, "mesh_ready": False}}}


class TeamBase(Base):
    def setUp(self):
        super().setUp()
        teams.set_providers(tracks=lambda: [{"id": "operate-nexxus", "title": "Operate NEXXUS", "badge": "NEXXUS Operator", "steps": 8, "done": 2}], system=lambda: TELEMETRY)


class TeamTest(TeamBase):
    def test_create_validates_and_limits(self):
        for bad in (("", "m", "team"), ("  ", "", "team"), ("ok", "", "empire")):
            with self.assertRaises(teams.TeamError):
                teams.create_team(*bad)
        for i in range(teams.MAX_TEAMS):
            teams.create_team("t%d" % i)
        with self.assertRaises(teams.TeamError):
            teams.create_team("one too many")

    def test_a_new_workspace_has_one_leader_and_nothing_invented(self):
        t = teams.create_team("Founders", "Ship the first product", "company", "Ada")
        self.assertEqual(t["members"], [{"id": "you", "name": "Ada", "role": "leader"}])
        d = teams.get_team(t["id"])["dashboard"]
        self.assertEqual((d["health"], d["total"], d["percent"]), ("empty", 0, 0))
        self.assertEqual(teams.list_teams()[0]["members"], 1)

    def test_board_flow_activity_and_workflow_health(self):
        t = teams.create_team("Pod")
        a = teams.add_task(t["id"], "Write the product page", "headline and price", "2999-01-01")
        b = teams.add_task(t["id"], "Pick a payment provider", due="not a date")
        self.assertEqual(b["due"], "", "a malformed date is dropped")
        self.assertEqual(teams.get_team(t["id"])["dashboard"]["health"], "not started")
        teams.move_task(t["id"], a["id"], "doing")
        self.assertEqual(teams.get_team(t["id"])["dashboard"]["health"], "moving")
        teams.move_task(t["id"], a["id"], "done")
        d = teams.get_team(t["id"])["dashboard"]
        self.assertEqual((d["counts"], d["percent"], d["done_this_week"]), ({"todo": 1, "doing": 0, "done": 1}, 50, 1))
        self.assertIn("Task done: Write the product page", [x["text"] for x in d["activity"]])
        late = teams.add_task(t["id"], "Late thing", due="2000-01-01")
        self.assertEqual(teams.get_team(t["id"])["dashboard"]["health"], "behind")
        self.assertEqual(teams.get_team(t["id"])["dashboard"]["overdue"][0]["id"], late["id"])
        teams.move_task(t["id"], late["id"], "done")
        self.assertEqual(teams.get_team(t["id"])["dashboard"]["overdue"], [])
        teams.delete_task(t["id"], b["id"])
        with self.assertRaises(teams.TeamError):
            teams.move_task(t["id"], "nope", "done")
        with self.assertRaises(teams.TeamError):
            teams.move_task(t["id"], a["id"], "someday")
        with self.assertRaises(teams.TeamError):
            teams.add_task(t["id"], "   ")

    def test_board_is_capped(self):
        t = teams.create_team("Big")
        for i in range(teams.MAX_TASKS):
            teams.add_task(t["id"], "t%d" % i)
        with self.assertRaises(teams.TeamError):
            teams.add_task(t["id"], "one more")

    def test_blueprints_come_from_the_academy_and_only_real_tracks_attach(self):
        t = teams.create_team("Learners")
        self.assertEqual(teams.attach_track(t["id"], "operate-nexxus"), ["operate-nexxus"])
        with self.assertRaises(teams.TeamError):
            teams.attach_track(t["id"], "no-such-track")
        bp = teams.get_team(t["id"])["dashboard"]["blueprints"][0]
        self.assertEqual((bp["steps"], bp["done"], bp["percent"]), (8, 2, 25))
        self.assertEqual(teams.attach_track(t["id"], "operate-nexxus", False), [])

    def test_system_telemetry_is_real_or_absent(self):
        t = teams.create_team("Ops")
        s = teams.get_team(t["id"])["dashboard"]["system"]
        self.assertEqual((s["engines_total"], s["engines_found"], s["engines_mesh_ready"]), (3, 2, 1))
        self.assertEqual(s["hub"]["threads"], 9)
        teams.set_providers(system=lambda: 1 / 0)
        self.assertIsNone(teams.get_team(t["id"])["dashboard"]["system"], "a broken reader shows nothing rather than a made-up number")
        teams.set_providers(system=lambda: "garbage")
        self.assertIsNone(teams.get_team(t["id"])["dashboard"]["system"])

    def test_the_company_stack_never_claims_what_does_not_exist(self):
        t = teams.create_team("Co", kind="company")
        stack = {x["id"]: x for x in teams.get_team(t["id"])["dashboard"]["stack"]}
        for unavailable in ("phone", "rooms", "invites"):
            self.assertEqual(stack[unavailable]["status"], "unavailable")
            self.assertIn("Not available", stack[unavailable]["text"])
        self.assertTrue(all(x["status"] in ("learn", "system", "unavailable") for x in stack.values()), "no item may carry a connected or live status")
        self.assertFalse(teams.get_team(t["id"])["dashboard"]["channels"]["available"])

    def test_delete_team(self):
        t = teams.create_team("Gone")
        teams.delete_team(t["id"])
        with self.assertRaises(teams.TeamError):
            teams.get_team(t["id"])


class TeamRoutesTest(TeamBase):
    def setUp(self):
        super().setUp()
        app = Flask(__name__)
        pm.register_routes(app, lambda: True, lambda p, s=200: (jsonify(p), s))
        self.c = app.test_client()
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": true}')

    def test_full_roundtrip(self):
        r = self.c.post("/api/platform/teams", json={"name": "Alpha", "mission": "Launch", "kind": "pod"})
        self.assertEqual(r.status_code, 200)
        tid = r.get_json()["team"]["id"]
        self.assertEqual(self.c.post("/api/platform/teams", json={"name": ""}).status_code, 400)
        task = self.c.post("/api/platform/teams/%s/task" % tid, json={"title": "First"}).get_json()["task"]
        self.assertEqual(self.c.post("/api/platform/teams/%s/task/%s" % (tid, task["id"]), json={"status": "doing"}).get_json()["task"]["status"], "doing")
        self.assertEqual(self.c.post("/api/platform/teams/%s/blueprint" % tid, json={"track": "operate-nexxus"}).get_json()["tracks"], ["operate-nexxus"])
        got = self.c.get("/api/platform/teams/" + tid).get_json()["team"]
        self.assertEqual((got["dashboard"]["counts"]["doing"], len(got["dashboard"]["blueprints"])), (1, 1))
        self.assertEqual(self.c.get("/api/platform/teams").get_json()["teams"][0]["name"], "Alpha")
        self.assertEqual(self.c.delete("/api/platform/teams/%s/task/%s" % (tid, task["id"])).status_code, 200)
        self.assertEqual(self.c.get("/api/platform/teams/nope").status_code, 404)
        self.assertEqual(self.c.delete("/api/platform/teams/" + tid).status_code, 200)

    def test_closed_when_the_beta_ends(self):
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": false}')
        self.assertEqual(self.c.get("/api/platform/teams").status_code, 402)

    def test_team_data_never_reaches_the_public_wall_or_visitors(self):
        tid = self.c.post("/api/platform/teams", json={"name": "SecretCo", "mission": "stealth mission"}).get_json()["team"]["id"]
        self.c.post("/api/platform/teams/%s/task" % tid, json={"title": "confidential launch task"})
        blob = json.dumps(pm.public_wall()) + json.dumps(pm.visitor_view())
        self.assertNotIn("SecretCo", blob)
        self.assertNotIn("confidential", blob)


class SharedPostTest(Base):
    def setUp(self):
        super().setUp()
        pm._recent_posts.clear()
        app = Flask(__name__)
        pm.register_routes(app, lambda: True, lambda p, s=200: (jsonify(p), s))
        self.c = app.test_client()
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": true}')

    def test_private_notes_stay_private_and_shared_posts_go_public(self):
        a = self.c.post("/api/platform/post", json={"text": "my private scratchpad"}).get_json()["post"]
        b = self.c.post("/api/platform/post", json={"text": "shared with the community", "public": True}).get_json()["post"]
        self.assertEqual((a["public"], b["public"]), (False, True))
        self.assertEqual([p["text"] for p in pm.public_wall()["posts"]], ["shared with the community"])
        self.assertEqual(ranks.status()["points"], 2, "only the shared post earned points")

    def test_multipart_share_flag(self):
        import io
        from test_platform_mode import image_bytes
        r = self.c.post("/api/platform/post", data={"text": "photo for everyone", "public": "true", "image": (io.BytesIO(image_bytes()), "x.jpg")}, content_type="multipart/form-data")
        self.assertTrue(r.get_json()["post"]["public"])
        r2 = self.c.post("/api/platform/post", data={"text": "photo for me", "image": (io.BytesIO(image_bytes()), "y.jpg")}, content_type="multipart/form-data")
        self.assertFalse(r2.get_json()["post"]["public"])

    def test_sharing_never_publishes_to_github_by_itself(self):
        class Spy:
            calls = []

            def __call__(self, q, v):
                Spy.calls.append(q)
                return {"data": {}}
        pm._gh_transport = Spy()
        try:
            self.c.post("/api/platform/post", json={"text": "shared but not on GitHub", "public": True})
            self.assertEqual(Spy.calls, [], "a shared post waits for an explicit, confirmed publish to GitHub")
        finally:
            pm._gh_transport = None


class WelcomeTest(Base):
    def test_every_planned_feature_is_marked_not_available_and_says_what_it_needs(self):
        w = academy.welcome()
        self.assertEqual(w["planned_label"], "Not available yet")
        self.assertGreaterEqual(len(w["planned"]), 5)
        for item in w["planned"]:
            self.assertTrue(item["needs"].strip(), item["title"] + " must say what it needs")
        planned_titles = " ".join(i["title"] for i in w["planned"]).lower()
        for must in ("teams", "rooms", "pods", "telephony"):
            self.assertIn(must, planned_titles)

    def test_nothing_unbuilt_appears_in_the_available_list(self):
        w = academy.welcome()
        today = " ".join(i["title"] + " " + i["text"] for i in w["today"]).lower()
        for unbuilt in ("video room", "phone line", "across the country", "invite other", "telephony", "live clustered"):
            self.assertNotIn(unbuilt, today)

    def test_the_beta_notice_is_wide_open_and_honest_about_money(self):
        b = academy.welcome()["beta"]
        self.assertIn("BETA", b["headline"])
        self.assertIn("free", b["text"])
        self.assertIn("Nobody is charged", b["text"])
        self.assertIn("before you pay", b["text"])
        self.assertNotRegex(json.dumps(academy.welcome()), r"\$\s?\d", "no price is attached to anything that does not exist")

    def test_marking_it_seen_is_remembered(self):
        self.assertNotIn("welcomed", academy.overview()["state"])
        academy.mark_welcomed()
        self.assertIn("welcomed", academy.overview()["state"])
        self.assertEqual(academy.overview()["welcome"]["title"], "Welcome to NEXXUS Platform")


class TalkPrivacyTest(unittest.TestCase):
    def test_talking_to_nexxus_is_a_private_kind(self):
        self.assertIn("nexxus_talk", privacy.PRIVATE_KINDS)
        with self.assertRaises(privacy.PrivacyViolation):
            privacy.require_public({"kind": "nexxus_talk", "visibility": "public", "text": "debug my code"}, "test")

    def test_public_modules_never_handle_the_talk_channel(self):
        for name in ("github_sync.py", "ranks.py", "teams.py", "academy.py", "telemetry_hub.py"):
            self.assertNotIn("nexxus_talk", open(os.path.join(HERE, name), encoding="utf-8").read(), name)


if __name__ == "__main__":
    unittest.main()
