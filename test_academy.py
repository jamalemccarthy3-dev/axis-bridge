"""The Academy: curriculum validity, honest progress rules, transparent badges and the leadership loop."""
import json
import os
import tempfile
import unittest

from flask import Flask, jsonify

import academy
import platform_mode as pm
from test_platform_mode import Base, token

HERE = os.path.dirname(os.path.abspath(__file__))


class CurriculumTest(unittest.TestCase):
    def test_every_track_is_valid_and_complete(self):
        tracks, problems = academy.load_curriculum()
        self.assertEqual(problems, [])
        self.assertEqual([t["id"] for t in tracks], ["operate-nexxus", "first-principles", "translation-matrix", "youtube-profile", "digital-storefront", "content-pipeline"])
        steps = [s for t in tracks for m in t["modules"] for s in m["steps"]]
        self.assertGreaterEqual(len(steps), 20)
        for s in steps:
            for k in ("title", "why", "check"):
                self.assertTrue(s[k].strip(), (s["id"], k))
            self.assertTrue(s["do"], s["id"] + " needs things to do")
            self.assertTrue(s["tips"], s["id"] + " needs tips")
            self.assertTrue(s["proof"] in ("note", "link") or s["proof"].split(":")[1] in academy.AUTO_CHECKS)

    def test_every_track_teaches_with_exact_prompts_or_commands(self):
        tracks, _ = academy.load_curriculum()
        for t in tracks:
            n = sum(len(s["prompts"]) + len(s["commands"]) for m in t["modules"] for s in m["steps"])
            self.assertGreaterEqual(n, 4, t["id"] + " must carry real prompts/commands")
            for m in t["modules"]:
                for s in m["steps"]:
                    for p in s["prompts"] + s["commands"]:
                        self.assertTrue(p["label"].strip() and p["text"].strip())

    def test_business_tracks_make_no_income_promises_and_carry_a_disclaimer(self):
        tracks, _ = academy.load_curriculum()
        banned = ("guaranteed", "get rich", "passive income", "make $", "earn $", "overnight", "100%")
        for t in tracks:
            blob = json.dumps(t).lower()
            for word in banned:
                self.assertNotIn(word, blob, "%s: %r" % (t["id"], word))
            if t["id"] != "operate-nexxus":
                self.assertIn("not", t["disclaimer"].lower() + " not")
                self.assertTrue(t["disclaimer"], t["id"] + " needs a disclaimer")

    def test_videos_come_only_from_allowed_hosts_and_no_unverified_urls_ship(self):
        ok = academy._valid_video({"title": "t", "url": "https://www.youtube-nocookie.com/embed/abc123"})
        self.assertEqual(ok["host"], "www.youtube-nocookie.com")
        for bad in ("http://www.youtube-nocookie.com/embed/x", "https://evil.example/embed/x", "https://www.youtube-nocookie.com/watch?v=x", "javascript:alert(1)", "https://player.vimeo.com/evil/1", ""):
            self.assertIsNone(academy._valid_video({"url": bad}), bad)
        tracks, _ = academy.load_curriculum()
        shipped = [s["video"] for t in tracks for m in t["modules"] for s in m["steps"] if s["video"]]
        self.assertEqual(shipped, [], "no video URL may ship until a real, rights-cleared one is added")


class ProgressTest(Base):
    def setUp(self):
        super().setUp()
        pm._recent_posts.clear()

    def test_note_steps_need_a_real_sentence_and_say_they_are_self_reported(self):
        with self.assertRaises(academy.AcademyError):
            academy.complete_step("operate-nexxus", "modes", "ok")
        r = academy.complete_step("operate-nexxus", "modes", "I opened Diagnostic and read the engine lights.")
        self.assertEqual(r["step"]["proof"], "note")

    def test_auto_steps_cannot_be_ticked_by_hand_until_it_is_true(self):
        with self.assertRaises(academy.AcademyError) as cm:
            academy.complete_step("operate-nexxus", "complete-profile", "I did it, trust me")
        self.assertIn("checks this itself", str(cm.exception))
        pm.save_profile({"name": "Ada", "headline": "Builder", "about": "I build things."})
        r = academy.complete_step("operate-nexxus", "complete-profile")
        self.assertEqual(r["step"]["proof"], "auto")

    def test_the_substantial_public_post_check_is_real(self):
        short = pm.add_post("hi"); pm.set_public(short["id"], True)
        with self.assertRaises(academy.AcademyError):
            academy.complete_step("operate-nexxus", "first-public-post")
        priv = pm.add_post("A long and detailed private note about everything I learned today.")
        with self.assertRaises(academy.AcademyError):
            academy.complete_step("operate-nexxus", "first-public-post")
        pm.set_public(priv["id"], True)
        self.assertEqual(academy.complete_step("operate-nexxus", "first-public-post")["step"]["proof"], "auto")

    def test_completing_twice_is_harmless_and_unknown_steps_are_refused(self):
        a = academy.complete_step("operate-nexxus", "modes", "I opened the menu and read every entry.")
        b = academy.complete_step("operate-nexxus", "modes", "something else entirely")
        self.assertEqual(a["step"]["t"], b["step"]["t"])
        for bad in (("nope", "modes"), ("operate-nexxus", "nope"), ("", "")):
            with self.assertRaises(academy.AcademyError):
                academy.complete_step(*bad)

    def test_module_and_track_badges_leadership_and_evidence_levels(self):
        note = "I did this step and here is what I saw."
        for sid in ("modes", "cheatsheet"):
            r = academy.complete_step("operate-nexxus", sid, note)
        self.assertEqual([b["badge"] for b in r["new_badges"]], ["operate-nexxus:orient"])
        self.assertEqual(r["new_badges"][0]["evidence"], "self-reported")
        for sid in ("build-halt", "creation", "sketch"):
            academy.complete_step("operate-nexxus", sid, note)
        academy.complete_step("operate-nexxus", "guardrails", note)
        pm.save_profile({"name": "Ada", "headline": "Builder", "about": "About"})
        academy.complete_step("operate-nexxus", "complete-profile")
        post = pm.add_post("I learned how the modes and the guardrails fit together today."); pm.set_public(post["id"], True)
        r = academy.complete_step("operate-nexxus", "first-public-post")
        ids = [b["badge"] for b in r["new_badges"]]
        self.assertEqual(ids, ["operate-nexxus:safe-and-share", "operate-nexxus", "mentor-ready"])
        self.assertEqual(r["new_badges"][0]["evidence"], "mixed")
        ov = academy.overview()
        self.assertTrue(ov["leadership"]["mentor_ready"])
        self.assertIn("not built yet", ov["leadership"]["text"])
        self.assertEqual(sum(1 for b in ov["badges"] if b["earned"]), 5, "three module badges, the track badge and Mentor-ready")
        self.assertEqual(academy.complete_step("operate-nexxus", "modes", "again")["new_badges"], [], "badges are never awarded twice")

    def test_every_badge_lists_how_to_earn_it(self):
        ov = academy.overview()
        self.assertGreaterEqual(len(ov["badges"]), 12)
        for b in ov["badges"]:
            self.assertTrue(b["criteria"].strip(), b["id"])
            self.assertFalse(b["earned"])

    def test_open_beta_every_track_is_open_with_no_prerequisites(self):
        ov = academy.overview()
        self.assertIn("Open Beta", ov["beta"])
        academy.complete_step("content-pipeline", "idea-bank", "I wrote ten ideas into one note today.")      # a different track, first thing, no gate
        self.assertEqual(academy.track_detail("content-pipeline")["modules"][0]["steps"][0]["done"], True)

    def test_path_choice_and_the_group_trust_protocol_are_honest(self):
        with self.assertRaises(academy.AcademyError):
            academy.set_path("both")
        with self.assertRaises(academy.AcademyError):
            academy.set_path("solo", "no-such-track")
        self.assertEqual(academy.set_path("group", "youtube-profile")["path"], "group")
        g = academy.group_checklist()
        self.assertEqual(g["pod_entry"], "locked")
        self.assertEqual([i["available"] for i in g["items"]], [True, False, False, False], "steps that need other people stay open, never faked")
        q = {x["id"]: x for x in academy.quests()}
        self.assertFalse(q["peers"]["available"] or q["review"]["available"])
        self.assertTrue(q["path"]["done"])
        self.assertFalse(q["conduct"]["done"])
        academy.acknowledge_conduct()
        self.assertTrue({x["id"]: x for x in academy.quests()}["conduct"]["done"])


    def test_company_gate_needs_all_of_track_a(self):
        ok, why = academy.company_gate()
        self.assertFalse(ok)
        self.assertIn("Track A", why)
        st = academy.track_a_status()
        self.assertEqual((st["done"], st["total"]), (0, 20))
        tracks, _ = academy.load_curriculum()
        a = [t for t in tracks if academy.track_path(t) == "A"]
        self.assertEqual([t["id"] for t in a], ["operate-nexxus", "first-principles", "translation-matrix"])
        self.assertTrue(all(academy.track_path(t) == "B" for t in tracks if t not in a))

    def test_weekly_release_holds_future_lessons_back(self):
        import time as _t
        tracks, _ = academy.load_curriculum()
        late = {"id": "x", "week": 3, "steps": []}
        self.assertTrue(academy.module_released({"id": "y"}), "week 0 is open from day one")
        self.assertFalse(academy.module_released(late))
        self.assertTrue(academy.module_released(late, now=_t.time() + 3 * academy.WEEK_SECONDS + 5))

    def test_task_focus_scopes_nexxus_until_done_or_left(self):
        self.assertEqual(academy.focus_preamble(), "")
        academy.set_focus("operate-nexxus", "modes")
        pre = academy.focus_preamble()
        self.assertIn("Meet the Modes menu", pre)
        self.assertIn("Do not start or switch to unrelated topics", pre)
        academy.clear_focus()
        self.assertEqual(academy.focus_preamble(), "")
        academy.set_focus("operate-nexxus", "modes")
        academy.complete_step("operate-nexxus", "modes", "I opened Diagnostic and read the engine lights.")
        self.assertIsNone(academy.focus_info(), "finishing the task releases the lock")
        with self.assertRaises(academy.AcademyError):
            academy.set_focus("operate-nexxus", "nope")

    def test_greeting_is_warm_optional_and_pressure_free(self):
        g = academy.greeting().lower()
        for word in ("welcome", "deep end", "academy", "optional", "no rush"):
            self.assertIn(word, g)
        self.assertEqual(academy.welcome()["greeting"], academy.greeting())


class AcademyRouteTest(Base):
    def setUp(self):
        super().setUp()
        pm._recent_posts.clear()
        app = Flask(__name__)
        pm.register_routes(app, lambda: True, lambda p, s=200: (jsonify(p), s))
        self.c = app.test_client()
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": true}')

    def test_routes_roundtrip(self):
        ov = self.c.get("/api/platform/academy").get_json()
        self.assertEqual((ov["status"], len(ov["tracks"])), ("success", 6))
        self.assertEqual(self.c.get("/api/platform/academy/track/youtube-profile").get_json()["track"]["badge"], "Channel Builder")
        self.assertEqual(self.c.get("/api/platform/academy/track/nope").status_code, 404)
        self.assertEqual(self.c.post("/api/platform/academy/path", json={"path": "solo", "track": "operate-nexxus"}).status_code, 200)
        self.assertEqual(self.c.post("/api/platform/academy/path", json={"path": "x"}).status_code, 400)
        self.assertEqual(self.c.post("/api/platform/academy/conduct").status_code, 200)
        r = self.c.post("/api/platform/academy/step", json={"track": "operate-nexxus", "step": "complete-profile", "evidence": "trust me"})
        self.assertEqual(r.status_code, 400)
        r = self.c.post("/api/platform/academy/step", json={"track": "operate-nexxus", "step": "modes", "evidence": "I opened the Modes menu and read each entry."})
        self.assertEqual(r.status_code, 200)

    def test_terms_acceptance_is_versioned_and_recorded(self):
        w = self.c.get("/api/platform/academy").get_json()["welcome"]
        self.assertFalse(w["terms_accepted"])
        self.assertEqual([x["title"][:2] for x in w["terms"]["sections"]], ["1.", "2."])
        self.assertTrue(all(x["today"] for x in w["terms"]["sections"]), "every promise says what is true today")
        self.assertEqual(self.c.post("/api/platform/academy/terms", json={"version": "old"}).status_code, 409, "an old screen cannot accept new words")
        r = self.c.post("/api/platform/academy/terms", json={"version": w["terms"]["version"]}).get_json()
        self.assertEqual(r["accepted"]["sha256"], w["terms"]["sha256"])
        self.assertTrue(self.c.get("/api/platform/academy").get_json()["welcome"]["terms_accepted"])

    def test_terms_workspace_limit_matches_the_code(self):
        import teams
        self.assertIn("limited to %d" % teams.MAX_TEAMS, academy.TERMS[0]["today"])
        self.assertIn("one per person", academy.TERMS[0]["today"])
        self.assertEqual(teams.MAX_COMPANIES, 1)

    def test_focus_and_company_gate_through_the_routes(self):
        import teams
        r = self.c.post("/api/platform/academy/focus", json={"track": "operate-nexxus", "step": "modes"}).get_json()
        self.assertEqual(r["focus"]["step"], "modes")
        self.assertIn("[Task focus]", r["preamble"])
        self.assertEqual(self.c.post("/api/platform/academy/focus", json={"track": "x", "step": "y"}).status_code, 400)
        self.assertEqual(self.c.delete("/api/platform/academy/focus").get_json()["preamble"], "")
        teams.set_company_gate(academy.company_gate)                       # the real gate, not the test default
        r = self.c.post("/api/platform/teams", json={"name": "Co", "kind": "company"})
        self.assertGreaterEqual(r.status_code, 400)
        self.assertIn("Track A", json.dumps(r.get_json()))
        self.assertEqual(self.c.post("/api/platform/teams", json={"name": "Solo", "kind": "team"}).status_code, 200)

    def test_closed_when_the_beta_ends_without_a_license(self):
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": false}')
        self.assertEqual(self.c.get("/api/platform/academy").status_code, 402)


class PrivacyOfProgressTest(unittest.TestCase):
    def test_academy_never_touches_the_private_world(self):
        src = open(os.path.join(HERE, "academy.py"), encoding="utf-8").read()
        for word in ("direct_message", "group_chat", "room_session", "nexxus_data/private", "PRIVATE_DIR"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
