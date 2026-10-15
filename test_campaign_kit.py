"""test_campaign_kit.py - the campaign kit writes only from the profile, respects every channel's limits, refuses invented numbers, quotes and unsubstantiated claims, produces compliant emails,
branded graphics with checked contrast, an escaped landing page, and a hashed manifest. A model may rewrite copy but its output goes through the same checks. No network, no server.
Run: python test_campaign_kit.py"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import campaign_kit as CK  # noqa: E402

PROFILE = {"name": "Harbor Bakery", "what": "A neighbourhood bakery that bakes sourdough and pastries every morning", "audience": "families and offices in the harbour district",
           "offer": "Fresh bread delivered before 8am", "cta_text": "Order today", "cta_url": "https://harborbakery.example/order", "sender_name": "Ana at Harbor Bakery",
           "postal_address": "12 Dock Street, Harbour City", "differentiators": ["Baked each morning from a 48 hour sourdough starter", "Delivered by bicycle within the district"],
           "proof_points": ["Open since 2019"], "colors": {"primary": "#7c2d12", "accent": "#fbbf24"}}


def prof(**kw):
    return dict(PROFILE, **kw)


class Profile(unittest.TestCase):
    def test_required_facts_and_formats(self):
        for bad in ({"name": ""}, {"cta_url": "javascript:alert(1)"}, {"cta_url": "harborbakery.example"}, {"postal_address": ""}, {"differentiators": []}, {"colors": {"primary": "red"}},
                    {"proof_points": ["x"] * 9}, {"what": "a" * 400}, {"name": "x\x00y"}):
            with self.assertRaises(CK.CampaignError, msg=bad):
                CK.validate_profile(prof(**bad))
        p = CK.validate_profile(prof(proof_points="one\ntwo"))
        self.assertEqual(p["proof_points"], ["one", "two"])


class Copy(unittest.TestCase):
    def test_every_channel_limit_holds_and_nothing_is_invented(self):
        kit = CK.generate(PROFILE)
        a = kit["ads"]
        self.assertTrue(all(len(h) <= 30 for h in a["google_search"]["headlines"]))
        self.assertTrue(all(len(d) <= 90 for d in a["google_search"]["descriptions"]))
        self.assertGreaterEqual(len(a["google_search"]["headlines"]), 3)
        self.assertLessEqual(len(a["meta"]["headline"]), 40)
        self.assertLessEqual(len(a["meta"]["primary_text"]), 125)
        self.assertLessEqual(len(a["linkedin"]["headline"]), 70)
        self.assertLessEqual(len(a["tiktok"]["text"]), 100)
        self.assertEqual(CK.check_kit(kit, kit["profile"]), [])
        blob = json.dumps(kit["ads"]) + json.dumps(kit["emails"])
        self.assertNotIn("guarantee", blob.lower())

    def test_long_facts_are_cut_at_a_word_never_mid_word(self):
        kit = CK.generate(prof(offer="Fresh bread delivered before eight every single morning of the year to your door"))
        for h in kit["ads"]["google_search"]["headlines"]:
            self.assertLessEqual(len(h), 30)
            self.assertTrue(h == h.strip() and not h.endswith((",", ";", ":", "-")))

    def test_scripts_fit_their_running_time(self):
        kit = CK.generate(PROFILE)
        for key, s in kit["video_scripts"].items():
            self.assertLessEqual(s["word_count"], s["word_budget"], key)
            self.assertEqual(round(s["scenes"][-1]["t_end"]), s["seconds"])
            self.assertIn("Order today", s["scenes"][-1]["narration"])
            ts = [(x["t_start"], x["t_end"]) for x in s["scenes"]]
            self.assertTrue(all(a < b for a, b in ts) and all(ts[i][1] <= ts[i + 1][0] + 0.01 for i in range(len(ts) - 1)))
        self.assertEqual(set(kit["video_scripts"]), {"social_15s", "broadcast_30s", "brand_story"})

    def test_emails_always_carry_sender_address_and_unsubscribe(self):
        kit = CK.generate(PROFILE)
        self.assertEqual(len(kit["emails"]), 5)
        for e in kit["emails"]:
            for need in ("{{unsubscribe_url}}", "12 Dock Street, Harbour City", "Ana at Harbor Bakery", "you asked to hear from"):
                self.assertIn(need, e["body"])
            self.assertLessEqual(len(e["subject"]), 60)
        kit["emails"][2]["body"] = kit["emails"][2]["body"].replace("{{unsubscribe_url}}", "")
        self.assertTrue([p for p in CK.check_kit(kit, kit["profile"]) if "unsubscribe" in p])


class Lint(unittest.TestCase):
    def setUp(self):
        self.p = CK.validate_profile(PROFILE)

    def test_numbers_must_come_from_the_profile(self):
        self.assertEqual(CK.lint_copy("Open since 2019 and baked with a 48 hour starter", self.p), [])
        for text in ("Over 10,000 happy customers", "Rated 4.9 stars", "Save 40% today", "Since 1999"):
            self.assertTrue(CK.lint_copy(text, self.p), text)

    def test_quotes_are_never_invented(self):
        self.assertTrue(CK.lint_copy('"This is the best bread I have ever eaten," says Maria.', self.p))
        self.assertEqual(CK.lint_copy("Fresh bread delivered before 8am", self.p), [])

    def test_unsubstantiated_claims_are_refused_unless_the_owner_supplied_them(self):
        for text in ("Guaranteed fresh", "Risk-free trial", "The #1 bakery", "Best in the world", "Clinically proven to satisfy", "A miracle loaf"):
            self.assertTrue(CK.lint_copy(text, self.p), text)
        p2 = CK.validate_profile(prof(proof_points=["Our bread is guaranteed fresh or we replace it"]))
        self.assertEqual(CK.lint_copy("guaranteed fresh", p2), [])


class Model(unittest.TestCase):
    def test_a_model_may_rewrite_but_only_through_the_same_checks(self):
        good = {"ads": CK.build_copy(CK.validate_profile(PROFILE))["ads"], "emails": CK.build_copy(CK.validate_profile(PROFILE))["emails"]}
        good["ads"]["meta"]["headline"] = "Warm bread, at your door by 8am"
        kit = CK.generate(PROFILE, llm=lambda prompt: "Sure! " + json.dumps(good))
        self.assertEqual(kit["ads"]["meta"]["headline"], "Warm bread, at your door by 8am")
        self.assertIn("model", kit["source"])

    def test_invented_or_oversized_model_output_falls_back_to_the_template_and_says_so(self):
        base = CK.build_copy(CK.validate_profile(PROFILE))
        for mutate in (lambda a: a["meta"].update(headline="x" * 80), lambda a: a["tiktok"].update(text="Join 50,000 happy customers"), lambda a: a["linkedin"].update(intro="Guaranteed results")):
            bad = json.loads(json.dumps({"ads": base["ads"], "emails": base["emails"]}))
            mutate(bad["ads"])
            kit = CK.generate(PROFILE, llm=lambda prompt, b=bad: json.dumps(b))
            self.assertEqual(kit["source"], "template")
            self.assertIn("failed the checks", kit["source_note"])
        kit = CK.generate(PROFILE, llm=lambda prompt: "not json at all")
        self.assertEqual(kit["source"], "template")


class Graphics(unittest.TestCase):
    def test_contrast_is_computed_and_the_text_colour_is_chosen_to_read(self):
        self.assertAlmostEqual(CK.contrast((255, 255, 255), (0, 0, 0)), 21.0, delta=0.01)
        for hexc in ("#7c2d12", "#fbbf24", "#ffffff", "#000000", "#1d4ed8", "#facc15"):
            rgb = CK._rgb(hexc)
            self.assertGreaterEqual(CK.contrast(rgb, CK.text_colour(rgb)), 4.5, hexc)

    def test_every_size_is_drawn_at_its_exact_size(self):
        from PIL import Image
        d = tempfile.mkdtemp()
        kit = CK.generate(PROFILE)
        man = CK.write_kit(d, kit)
        self.assertEqual(len(man["graphics"]), len(CK.AD_SIZES))
        for key, size in CK.AD_SIZES.items():
            self.assertEqual(Image.open(os.path.join(d, "graphics", key + ".png")).size, size)
        for g in man["graphics"]:
            self.assertGreaterEqual(g["contrast_text_on_background"], 4.5)
            self.assertGreaterEqual(g["contrast_label_on_button"], 4.5)

    def overlaps(self, a, b):
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    def test_no_block_runs_into_another_in_any_size_even_with_long_text(self):
        long_cases = [PROFILE, prof(offer="Fresh sourdough and pastries delivered to your door before eight every single morning of the week", what="A neighbourhood bakery that bakes sourdough, rye, pastries and seasonal specials every morning from scratch",
                                    name="The Very Long Named Harbour District Artisan Bakery", cta_text="Order your bread today")]
        for prof_ in long_cases:
            kit = CK.generate(prof_)
            d = tempfile.mkdtemp()
            man = CK.write_kit(d, kit)
            for g in man["graphics"]:
                W, H = g["size"]
                L = g["layout"]
                blocks = list(L.items())
                for name, r in blocks:
                    self.assertTrue(0 <= r[0] < r[2] <= W and 0 <= r[1] < r[3] <= g["footer_bar_top"], (g["path"], name, r))
                for i in range(len(blocks)):
                    for j in range(i + 1, len(blocks)):
                        self.assertFalse(self.overlaps(blocks[i][1], blocks[j][1]), (os.path.basename(g["path"]), blocks[i][0], blocks[j][0], blocks[i][1], blocks[j][1]))
                self.assertIn("headline", L)
                self.assertTrue(g["headline_drawn"].strip())


class Landing(unittest.TestCase):
    def test_the_landing_page_is_escaped_self_contained_and_complete(self):
        kit = CK.generate(prof(name="Harbor <Bakery> & Co", what="We bake <b>bread</b> daily"))
        page = CK.landing_page(kit["profile"], kit)
        self.assertNotIn("<b>bread</b>", page)
        self.assertIn("&lt;b&gt;bread&lt;/b&gt;", page)
        self.assertNotRegex(page, r"(src|href)=\"//")
        self.assertNotRegex(page, r"<script")
        for must in ("Order today", "https://harborbakery.example/order", "12 Dock Street", "viewport", "<title>"):
            self.assertIn(must, page)


class Manifest(unittest.TestCase):
    def test_files_match_their_hashes_and_the_disclosure_and_gaps_are_stated(self):
        d = tempfile.mkdtemp()
        man = CK.write_kit(d, CK.generate(PROFILE))
        for rel, h in man["files"].items():
            if rel != "manifest.json":
                self.assertEqual(hashlib.sha256(open(os.path.join(d, rel), "rb").read()).hexdigest(), h, rel)
        self.assertIn("automated tools", man["disclosure"])
        self.assertIn("photoreal AI footage", " ".join(man["not_included"]))
        for rel in ("video_scripts.json", "ad_copy.json", "emails.md", "landing/index.html", "manifest.json"):
            self.assertTrue(os.path.exists(os.path.join(d, rel)), rel)


if __name__ == "__main__":
    unittest.main(verbosity=1)
