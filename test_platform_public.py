"""The public wall, the transparent ranks and the GitHub sync (against a FAKE GitHub: nothing here talks to the network)."""
import json
import os
import unittest
from unittest import mock

from flask import Flask, jsonify

import github_sync as gs
import platform_mode as pm
import privacy
import ranks
from test_platform_mode import Base, token

REPO_INFO = {"repository": {"id": "R_1", "hasDiscussionsEnabled": True, "discussionCategories": {"nodes": [{"id": "C_1", "name": "Show and tell"}]}}}


class FakeGitHub:
    def __init__(self):
        self.calls, self.comments, self.discussions = [], [], 0
        self.me = "owner"

    def __call__(self, query, variables):
        self.calls.append((query, variables))
        if "viewer{login}" in query:
            return {"data": {"viewer": {"login": self.me}}}
        if "hasDiscussionsEnabled" in query:
            return {"data": REPO_INFO}
        if "createDiscussion" in query:
            self.discussions += 1
            return {"data": {"createDiscussion": {"discussion": {"id": "D_%d" % self.discussions, "number": self.discussions, "url": "https://github.com/o/r/discussions/%d" % self.discussions}}}}
        if "node(id" in query:
            return {"data": {"node": {"comments": {"nodes": self.comments}}}}
        if "addDiscussionComment" in query:
            return {"data": {"addDiscussionComment": {"comment": {"id": "DC_new", "url": "https://github.com/o/r/discussions/1#c1"}}}}
        return {"errors": [{"message": "unexpected query"}]}

    def sent(self, word):
        return [v for q, v in self.calls if word in q]


def gh_comment(i, author, text="nice work"):
    return {"id": "DC_%d" % i, "body": text, "url": "https://github.com/o/r/discussions/1#c%d" % i, "createdAt": "2026-10-15T00:00:00Z", "author": {"login": author}}


class PublicBase(Base):
    def setUp(self):
        super().setUp()
        pm._recent_posts.clear()
        pm._gh_last_pull[0] = 0
        self.gh = FakeGitHub()
        pm._gh_transport = self.gh

    def tearDown(self):
        pm._gh_transport = None


class PublicWallTest(PublicBase):
    def test_posts_are_private_until_marked_public(self):
        p = pm.add_post("only for me")
        self.assertFalse(p["public"])
        self.assertEqual(pm.public_wall()["posts"], [])
        self.assertEqual(pm.set_public(p["id"], True), "ok")
        wall = pm.public_wall()
        self.assertEqual([x["text"] for x in wall["posts"]], ["only for me"])
        self.assertEqual(wall["statement"], privacy.PRIVATE_STATEMENT)

    def test_the_wall_never_carries_ratings_or_private_posts(self):
        a, b = pm.add_post("public one"), pm.add_post("private one")
        pm.set_rating(a["id"], 5)
        pm.set_public(a["id"], True)
        blob = json.dumps(pm.public_wall())
        self.assertNotIn("private one", blob)
        self.assertNotIn('"rating"', blob)

    def test_making_it_private_again_removes_it_and_its_points(self):
        p = pm.add_post("changing my mind")
        pm.set_public(p["id"], True)
        self.assertEqual(ranks.status()["points"], 2)
        pm.set_public(p["id"], False)
        self.assertEqual((pm.public_wall()["posts"], ranks.status()["points"]), ([], 0))


class RanksTest(PublicBase):
    def test_points_come_only_from_the_visible_ledger(self):
        for i in range(3):
            pm.set_public(pm.add_post("post %d" % i)["id"], True)
        st = ranks.status()
        self.assertEqual((st["points"], st["tier"], st["next_tier"], st["to_next"]), (6, "Newcomer", "Apprentice", 4))
        self.assertEqual(len(st["ledger"]), 3)
        self.assertTrue(all(e["rule"] == "public_post" and e["points"] == 2 for e in st["ledger"]))
        self.assertEqual(sum(e["points"] for e in st["ledger"]), st["points"], "the ledger adds up to the points shown: nothing hidden")
        self.assertIn("never count", st["note"])

    def test_one_award_per_item_and_a_daily_cap(self):
        ids = [pm.add_post("p%d" % i)["id"] for i in range(7)]
        for i in ids:
            pm.set_public(i, True)
        self.assertEqual(ranks.status()["points"], 5 * 2, "at most 5 public posts a day count")
        self.assertIsNone(ranks.award("public_post", ids[0]), "the same item never pays twice")

    def test_unavailable_rules_earn_nothing_and_are_listed(self):
        self.assertIsNone(ranks.award("pod_task_completed", "t1"))
        self.assertIsNone(ranks.award("peer_support_given", "c1"))
        self.assertIsNone(ranks.award("made_up_rule", "x"))
        rules = ranks.status()["rules"]
        self.assertFalse(rules["pod_task_completed"]["available"])
        self.assertIn("not built yet", rules["pod_task_completed"]["text"])

    def test_tiers(self):
        self.assertEqual([ranks.tier_for(n) for n in (0, 9, 10, 29, 30, 80, 200, 999)], ["Newcomer", "Newcomer", "Apprentice", "Apprentice", "Builder", "Craftsman", "Master", "Master"])


class GitHubSyncTest(PublicBase):
    def public_post(self, text="Shipped the vault"):
        p = pm.add_post(text)
        pm.set_public(p["id"], True)
        return p

    def test_nothing_is_planned_or_sent_for_private_posts(self):
        pm.add_post("private")
        self.assertEqual(pm.github_plan()["items"], [])
        with self.assertRaises(privacy.PrivacyViolation):
            gs.preview({"id": "x", "text": "private", "kind": "post"})
        self.assertEqual(self.gh.calls, [])

    def test_plan_shows_exactly_what_will_be_posted(self):
        p = self.public_post("Shipped the vault\nit keeps photos private")
        item = pm.github_plan()["items"][0]
        self.assertEqual((item["id"], item["title"]), (p["id"], "Shipped the vault"))
        self.assertIn("it keeps photos private", item["body"])
        self.assertIn("PG-13", item["body"])
        self.assertEqual(self.gh.calls, [], "planning sends nothing")

    def test_publish_creates_one_discussion_and_remembers_it(self):
        p = self.public_post()
        gh = pm.github_publish(p["id"])
        self.assertEqual(gh["url"], "https://github.com/o/r/discussions/1")
        self.assertEqual(self.gh.sent("createDiscussion")[0]["i"]["categoryId"], "C_1")
        self.assertEqual(pm.github_plan()["items"], [], "a mirrored post is no longer on the to-do list")
        with self.assertRaises(gs.GitHubError):
            pm.github_publish(p["id"])
        self.assertEqual(self.gh.discussions, 1)

    def test_a_mirrored_post_cannot_be_made_private_from_here(self):
        p = self.public_post()
        pm.github_publish(p["id"])
        self.assertEqual(pm.set_public(p["id"], False), "mirrored")
        self.assertTrue(pm.public_wall()["posts"])

    def test_publishing_a_private_post_is_refused(self):
        p = pm.add_post("nope")
        with self.assertRaises(privacy.PrivacyViolation):
            pm.github_publish(p["id"])
        self.assertEqual(self.gh.sent("createDiscussion"), [])

    def test_pulled_comments_appear_award_points_to_others_only_and_never_duplicate(self):
        p = self.public_post()
        pm.github_publish(p["id"])
        self.gh.comments = [gh_comment(1, "ada"), gh_comment(2, "OWNER", "my own reply"), gh_comment(3, "grace")]
        self.assertEqual(pm.github_pull(), {"new": 3})
        wall = pm.public_wall()["posts"][0]["comments"]
        self.assertEqual([(c["author"], c["source"]) for c in wall], [("ada", "github"), ("OWNER", "github"), ("grace", "github")])
        self.assertTrue(all(c["url"].startswith("https://github.com/") for c in wall))
        st = ranks.status()
        self.assertEqual(st["by_rule"]["peer_comment_received"]["points"], 2, "ada and grace count; your own login does not")
        pm._gh_last_pull[0] = 0
        self.assertEqual(pm.github_pull(), {"new": 0}, "a second pull adds nothing")
        self.assertEqual(ranks.status()["points"], st["points"])

    def test_pull_is_rate_limited(self):
        self.public_post()
        pm.github_pull()
        with self.assertRaises(gs.GitHubError):
            pm.github_pull()

    def test_only_your_own_comments_can_be_pushed_and_only_once(self):
        p = self.public_post()
        pm.github_publish(p["id"])
        mine = pm.add_comment(p["id"], "thanks all")
        self.gh.comments = [gh_comment(1, "ada")]
        pm.github_pull()
        theirs = [c for c in pm._read_posts()[0]["comments"] if c.get("source") == "github"][0]
        self.assertEqual(pm.github_push_comment(p["id"], mine["id"])["url"], "https://github.com/o/r/discussions/1#c1")
        self.assertEqual(self.gh.sent("addDiscussionComment")[0]["i"], {"discussionId": "D_1", "body": "thanks all"})
        with self.assertRaises(gs.GitHubError):
            pm.github_push_comment(p["id"], mine["id"])
        with self.assertRaises(gs.GitHubError):
            pm.github_push_comment(p["id"], theirs["id"])

    def test_the_token_is_never_returned_or_put_in_errors(self):
        os.environ["NEXXUS_GITHUB_TOKEN"] = "ghp_SUPERSECRETTOKEN123"
        pm._gh_transport = None
        try:
            with mock.patch("urllib.request.urlopen", side_effect=OSError("boom ghp_SUPERSECRETTOKEN123")):
                with self.assertRaises(gs.GitHubError) as cm:
                    gs.viewer_login()
            self.assertNotIn("SUPERSECRET", str(cm.exception))
            self.assertNotIn("SUPERSECRET", json.dumps(pm.github_status()))
        finally:
            del os.environ["NEXXUS_GITHUB_TOKEN"]


class RouteTest(PublicBase):
    def setUp(self):
        super().setUp()
        app = Flask(__name__)
        pm.register_routes(app, lambda: True, lambda p, s=200: (jsonify(p), s))
        self.c = app.test_client()
        self.c.post("/api/platform/license", json={"token": token()})
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": true}')

    def test_publish_needs_an_explicit_confirmation(self):
        p = pm.add_post("hello public")
        self.assertEqual(self.c.post("/api/platform/post/%s/public" % p["id"], json={"public": True}).status_code, 200)
        self.assertEqual(self.c.post("/api/platform/github/publish", json={"id": p["id"]}).status_code, 400)
        self.assertEqual(self.gh.calls, [], "no confirmation, nothing sent")
        r = self.c.post("/api/platform/github/publish", json={"id": p["id"], "confirm": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["gh"]["number"], 1)
        self.assertEqual(self.c.post("/api/platform/post/%s/public" % p["id"], json={"public": False}).status_code, 409)

    def test_comment_push_needs_confirmation_too(self):
        p = pm.add_post("x"); pm.set_public(p["id"], True); pm.github_publish(p["id"]); c = pm.add_comment(p["id"], "mine")
        self.assertEqual(self.c.post("/api/platform/post/%s/comment/%s/github" % (p["id"], c["id"]), json={}).status_code, 400)
        self.assertEqual(self.c.post("/api/platform/post/%s/comment/%s/github" % (p["id"], c["id"]), json={"confirm": True}).status_code, 200)

    def test_ranks_and_public_routes(self):
        p = pm.add_post("shared"); self.c.post("/api/platform/post/%s/public" % p["id"], json={"public": True})
        r = self.c.get("/api/platform/ranks").get_json()
        self.assertEqual((r["points"], r["tier"]), (2, "Newcomer"))
        self.assertIn("rules", r)
        w = self.c.get("/api/platform/public").get_json()
        self.assertEqual(len(w["posts"]), 1)
        self.assertIn("never shown on the public wall", w["statement"])

    def test_without_a_token_the_sync_says_so_and_sends_nothing(self):
        pm._gh_transport = None
        p = pm.add_post("x"); pm.set_public(p["id"], True)
        r = self.c.post("/api/platform/github/publish", json={"id": p["id"], "confirm": True})
        self.assertEqual(r.status_code, 400)
        self.assertIn("NEXXUS_GITHUB_TOKEN", r.get_json()["message"])
        self.assertFalse(self.c.get("/api/platform/github/plan").get_json()["configured"])


if __name__ == "__main__":
    unittest.main()
