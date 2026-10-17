import base64
import json
import os
import sys
import tempfile
import time
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import Flask, jsonify

import entitlements as ent
import platform_mode as pm

KEY = Ed25519PrivateKey.generate()


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def token(plan="lifetime", exp=None, feature="platform", key=KEY, tamper=False):
    body = json.dumps({"feature": feature, "plan": plan, "iat": int(time.time()), "exp": exp, "id": "t1"}, separators=(",", ":")).encode()
    t = "NXP1." + b64(body) + "." + b64(key.sign(b"NXP1." + body))
    return t[:-3] + ("AAA" if tamper else t[-3:])


class FakeModes:
    DEFAULT_MODE = "conversation"
    MODES = {"conversation": {}}


class FakeState:
    def __init__(self):
        self.mode = "conversation"

    def set(self, m):
        if m not in FakeModes.MODES:
            raise ValueError("unknown mode")
        self.mode = m
        return {"mode": m}

    def snapshot(self):
        return {"mode": self.mode}


class Base(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        pub = os.path.join(d, "pub.pem")
        open(pub, "wb").write(KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        ent.PUBLIC_KEY_PATH, ent.LICENSE_PATH = pub, os.path.join(d, "license.json")
        ent.BETA_PATH = os.path.join(d, "beta.json")                      # no beta file here: the gate is ON unless a test opens the beta
        os.environ.pop("NEXXUS_PLATFORM_BETA", None)
        pm.DATA_DIR = os.path.join(d, "platform")
        pm.MEDIA_DIR = os.path.join(pm.DATA_DIR, "media")
        pm.VAULT_PATH = os.path.join(pm.DATA_DIR, "vault.json")
        import ranks as _ranks
        _ranks.LEDGER_PATH = os.path.join(pm.DATA_DIR, "ranks.jsonl")
        import academy as _academy
        import teams as _teams
        import marketplace as _market
        _market.DATA_DIR = os.path.join(pm.DATA_DIR, "market")
        _market.set_publish_gate(lambda: (True, ""))          # the $199 + Track A publishing gate has its own tests
        _market.SUBS_PATH, _market.BLOB_DIR = os.path.join(_market.DATA_DIR, "submissions.json"), os.path.join(_market.DATA_DIR, "quarantine")
        _market.AUDIT_PATH, _market.REPORTS_PATH = os.path.join(_market.DATA_DIR, "audit.jsonl"), os.path.join(_market.DATA_DIR, "reports.jsonl")
        import market_social as _social
        _social.DATA_DIR = _market.DATA_DIR
        _social.REVIEWS_PATH, _social.COMMENTS_PATH, _social.INTERACTIONS_PATH = os.path.join(_market.DATA_DIR, "reviews.json"), os.path.join(_market.DATA_DIR, "comments.json"), os.path.join(_market.DATA_DIR, "interactions.jsonl")
        _social._recent.clear()
        _teams.TEAMS_PATH = os.path.join(pm.DATA_DIR, "teams.json")
        import dashboard_hub as _hub
        _hub.STORE_PATH = os.path.join(pm.DATA_DIR, "hub.json")
        self.assertTrue(_hub.STORE_PATH.startswith(pm.DATA_DIR), "the workspace store is not redirected to the temp folder")
        _hub.set_engine_provider(lambda: ["axis-core", "axis-link"])
        import private_hub as _ph
        _ph.STORE_PATH = os.path.join(pm.DATA_DIR, "talk_sessions.json")
        self.assertTrue(_ph.STORE_PATH.startswith(pm.DATA_DIR), "the private conversation store is not redirected to the temp folder")
        _teams.set_company_gate(lambda: (True, ""))          # the Track A gate is tested in test_academy.py
        _academy.PROGRESS_PATH, _academy.BADGES_PATH = os.path.join(pm.DATA_DIR, "academy.json"), os.path.join(pm.DATA_DIR, "badges.jsonl")
        os.environ.pop("NEXXUS_GITHUB_TOKEN", None)
        pm.PROFILE_PATH, pm.POSTS_PATH = os.path.join(pm.DATA_DIR, "p.json"), os.path.join(pm.DATA_DIR, "posts.jsonl")
        for name in ("PROFILE_PATH", "POSTS_PATH", "MEDIA_DIR", "VAULT_PATH"):         # every store must live under the temp folder, never the real one
            self.assertTrue(getattr(pm, name).startswith(pm.DATA_DIR), name + " is not redirected to the temp folder")
        self.assertTrue(_ranks.LEDGER_PATH.startswith(pm.DATA_DIR), "the rank ledger is not redirected to the temp folder")
        self.assertTrue(all(p.startswith(pm.DATA_DIR) for p in (_market.SUBS_PATH, _market.BLOB_DIR, _market.AUDIT_PATH, _market.REPORTS_PATH, _social.REVIEWS_PATH, _social.COMMENTS_PATH, _social.INTERACTIONS_PATH)), "the marketplace files are not redirected to the temp folder")
        self.assertTrue(_teams.TEAMS_PATH.startswith(pm.DATA_DIR), "the team store is not redirected to the temp folder")
        self.assertTrue(_academy.PROGRESS_PATH.startswith(pm.DATA_DIR) and _academy.BADGES_PATH.startswith(pm.DATA_DIR), "the academy files are not redirected to the temp folder")
        FakeModes.MODES = {"conversation": {}}


class EntitlementTest(Base):
    def test_locked_by_default_and_prices(self):
        self.assertFalse(ent.is_unlocked())
        self.assertEqual(ent.PLANS["monthly"]["price_usd"], 9.99)
        self.assertEqual(ent.PLANS["lifetime"]["price_usd"], 199.00)

    def test_valid_keys_unlock(self):
        self.assertTrue(ent.activate(token("lifetime"))[0])
        ent.remove()
        self.assertTrue(ent.activate(token("monthly", exp=int(time.time()) + 3600))[0])
        self.assertEqual(ent.status()["plan"], "monthly")

    def test_forged_tampered_wrong_feature_expired_are_refused(self):
        other = Ed25519PrivateKey.generate()
        for t, why in ((token(key=other), "signature"), (token(tamper=True), "signature"), (token(feature="other"), "not for Platform"),
                       (token("monthly", exp=int(time.time()) - 5), "expired"), (token("monthly", exp=None), "expiry"), ("garbage", "not a NEXXUS"), ("", "no license")):
            ok, st = ent.activate(t)
            self.assertFalse(ok, t[:20])
            self.assertIn(why, st["reason"])
        self.assertFalse(ent.is_unlocked(), "a refused key is never saved")

    def test_saved_key_is_rechecked_so_expiry_relocks(self):
        ent.activate(token("monthly", exp=int(time.time()) + 100))
        self.assertTrue(ent.status()["unlocked"])
        self.assertFalse(ent.status(now=time.time() + 1000)["unlocked"])

    def test_offer_carries_no_hard_coded_checkout_links(self):
        offer = ent.offer()
        self.assertTrue(all("checkout_url" not in p for p in offer["plans"]), "buying goes through billing.py, never a static link")
        self.assertFalse(hasattr(ent, "checkout_links"))


class BetaTest(Base):
    def open_beta(self):
        open(ent.BETA_PATH, "w").write('{"beta_open": true}')

    def test_beta_unlocks_everyone_without_a_license(self):
        self.assertFalse(ent.is_unlocked())
        self.open_beta()
        st = ent.status()
        self.assertEqual((st["unlocked"], st["plan"], st["beta"]), (True, "beta", True))
        self.assertTrue(ent.offer()["beta"])

    def test_beta_off_switch_and_env_override(self):
        self.open_beta()
        os.environ["NEXXUS_PLATFORM_BETA"] = "0"
        try:
            self.assertFalse(ent.is_unlocked(), "the environment variable brings the gate back")
        finally:
            del os.environ["NEXXUS_PLATFORM_BETA"]
        open(ent.BETA_PATH, "w").write('{"beta_open": false}')
        self.assertFalse(ent.is_unlocked())
        open(ent.BETA_PATH, "w").write("not json")
        self.assertFalse(ent.is_unlocked(), "a broken beta file fails closed")

    def test_mode_and_routes_open_during_beta_and_close_after(self):
        st = FakeState(); pm.register_mode(st, FakeModes)
        self.open_beta()
        self.assertEqual(st.set("platform")["mode"], "platform")
        app = Flask(__name__); pm.register_routes(app, lambda: True, lambda p, s=200: (jsonify(p), s)); c = app.test_client()
        self.assertEqual(c.get("/api/platform/state").status_code, 200)
        open(ent.BETA_PATH, "w").write('{"beta_open": false}')
        self.assertEqual(c.get("/api/platform/state").status_code, 402, "the gate is back the moment the beta ends")
        self.assertEqual(st.snapshot()["mode"], "conversation", "and anyone in Platform drops back to the desktop view")

    def test_a_real_license_still_works_when_the_beta_is_off(self):
        self.assertTrue(ent.activate(token("lifetime"))[0])
        self.assertTrue(ent.status()["unlocked"])
        self.assertFalse(ent.status()["beta"])

    def test_the_shipped_default_is_open_beta(self):
        import json as _j
        shipped = _j.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "platform_beta.json")))
        self.assertTrue(shipped["beta_open"])


class ModeGateTest(Base):
    def test_locked_until_licensed_and_relocks(self):
        st = FakeState()
        pm.register_mode(st, FakeModes)
        with self.assertRaises(pm.ModeLocked):
            st.set("platform")
        self.assertEqual(st.mode, "conversation")
        ent.activate(token("monthly", exp=int(time.time()) + 100))
        self.assertEqual(st.set("platform")["mode"], "platform")
        ent.remove()
        self.assertEqual(st.snapshot()["mode"], "conversation", "falls back to the desktop view when the license goes")


class RouteTest(Base):
    def setUp(self):
        super().setUp()
        self.local = True
        app = Flask(__name__)
        pm.register_routes(app, lambda: self.local, lambda p, s=200: (jsonify(p), s))
        self.c = app.test_client()

    def test_data_routes_locked_without_license(self):
        for method, url in (("get", "/api/platform/state"), ("post", "/api/platform/post"), ("post", "/api/platform/profile")):
            r = getattr(self.c, method)(url, json={"text": "x"})
            self.assertEqual(r.status_code, 402, url)
            self.assertEqual(r.get_json()["status"], "locked", "the status field must not be overwritten by the entitlement data")
            self.assertEqual(r.get_json()["plans"][1]["price_text"], "$199 one-time")
            self.assertFalse(r.get_json()["entitlement"]["unlocked"])

    def test_entitlement_route_reports_success_and_the_offer(self):
        d = self.c.get("/api/platform/entitlement").get_json()
        self.assertEqual(d["status"], "success")
        self.assertEqual([p["id"] for p in d["plans"]], ["monthly", "lifetime"])
        self.assertFalse(d["entitlement"]["unlocked"])

    def test_license_then_profile_posts_and_links(self):
        self.assertEqual(self.c.post("/api/platform/license", json={"token": "nope"}).status_code, 400)
        self.assertEqual(self.c.post("/api/platform/license", json={"token": token()}).status_code, 200)
        self.c.post("/api/platform/profile", json={"name": "Ada <b>L</b>", "headline": "Builder", "links": ["https://ex.am/p", "javascript:alert(1)", "ftp://x"]})
        p = self.c.post("/api/platform/post", json={"text": "hello floor"}).get_json()["post"]
        q = self.c.post("/api/platform/post", json={"text": "see https://example.com/a?b=1 now"}).get_json()["post"]
        self.assertEqual((p["kind"], q["kind"], q["url"]), ("post", "link", "https://example.com/a?b=1"))
        s = self.c.get("/api/platform/state").get_json()
        self.assertEqual(s["profile"]["links"], ["https://ex.am/p"], "only http(s) links are kept")
        self.assertEqual(len(s["floor"]), 2)
        self.assertEqual(len(s["shared_links"]), 1)
        self.assertEqual(s["network"], {"connections": 0, "feed": [], "note": s["network"]["note"]}, "the network side never shows invented content")
        self.assertEqual(self.c.delete("/api/platform/post/" + p["id"]).status_code, 200)
        self.assertEqual(self.c.delete("/api/platform/post/" + p["id"]).status_code, 404)
        self.assertEqual(self.c.post("/api/platform/post", json={"text": "   "}).status_code, 400)

    def test_not_available_from_other_machines(self):
        self.local = False
        self.assertEqual(self.c.get("/api/platform/entitlement").status_code, 403)
        self.assertEqual(self.c.post("/api/platform/license", json={"token": token()}).status_code, 403)

    def test_text_is_capped_and_cleaned(self):
        self.c.post("/api/platform/license", json={"token": token()})
        p = self.c.post("/api/platform/post", json={"text": "a\x00b" + "x" * 900}).get_json()["post"]
        self.assertEqual(len(p["text"]), 500)
        self.assertNotIn("\x00", p["text"])


def image_bytes(fmt="JPEG", size=(40, 30), exif=False, mode="RGB"):
    import io
    from PIL import Image
    im = Image.new(mode, size, (200, 30, 30) if mode == "RGB" else (200, 30, 30, 128))
    buf = io.BytesIO()
    kw = {}
    if exif:
        e = Image.Exif()
        e[0x010F] = "SecretCameraMaker"                     # Make
        e[0x8825] = {1: "N", 2: (51.0, 30.0, 0.0), 3: "W", 4: (0.0, 7.0, 0.0)}      # GPS position
        kw["exif"] = e
    im.save(buf, fmt, **kw)
    return buf.getvalue()


class MediaTest(Base):
    def test_photo_is_reencoded_and_metadata_is_stripped(self):
        raw = image_bytes(exif=True)
        self.assertIn(b"SecretCameraMaker", raw)
        mid = pm.save_media(raw)
        path, ctype = pm.media_path(mid)
        data = open(path, "rb").read()
        self.assertEqual(ctype, "image/jpeg")
        self.assertNotIn(b"SecretCameraMaker", data)
        from PIL import Image
        self.assertFalse(Image.open(path).getexif(), "no EXIF survives")

    def test_big_photo_is_shrunk_and_transparent_png_stays_png(self):
        from PIL import Image
        mid = pm.save_media(image_bytes("PNG", size=(3200, 1000)))
        self.assertEqual(max(Image.open(pm.media_path(mid)[0]).size), pm.MAX_SIDE)
        mid2 = pm.save_media(image_bytes("PNG", mode="RGBA"))
        self.assertEqual(pm.media_path(mid2)[1], "image/png")
        self.assertIsNotNone(pm.save_media(image_bytes("GIF")))

    def test_non_photos_are_refused(self):
        for bad in (b"", b"just some text pretending to be a png", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                    b"<html><script>alert(1)</script></html>", b"MZ\x90\x00 an exe", b"x" * (pm.MAX_UPLOAD + 1)):
            with self.assertRaises(pm.MediaError, msg=bad[:20]):
                pm.save_media(bad)

    def test_media_ids_cannot_escape_the_folder(self):
        for bad in ("../license", "..\\x", "a" * 16 + "/../x", "0123456789abcdeg", "", None):
            self.assertIsNone(pm.media_path(bad))


class FloorTest(Base):
    def setUp(self):
        super().setUp()
        pm._recent_posts.clear()
        self.local = True
        app = Flask(__name__)
        pm.register_routes(app, lambda: self.local, lambda p, s=200: (jsonify(p), s))
        self.c = app.test_client()
        self.c.post("/api/platform/license", json={"token": token()})

    def test_photo_post_comment_rating_delete_roundtrip(self):
        import io
        r = self.c.post("/api/platform/post", data={"text": "look at this", "image": (io.BytesIO(image_bytes(exif=True)), "x.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_json())
        post = r.get_json()["post"]
        self.assertEqual(post["kind"], "photo")
        m = self.c.get("/api/platform/media/" + post["media"])
        self.assertEqual((m.status_code, m.headers["Content-Type"], m.headers["X-Content-Type-Options"]), (200, "image/jpeg", "nosniff"))
        self.assertIn("sandbox", m.headers["Content-Security-Policy"])
        m.close()                                          # a finished download releases the file (Windows cannot delete an open one)
        self.assertEqual(self.c.post("/api/platform/post/%s/rating" % post["id"], json={"rating": 4}).get_json()["rating"], 4)
        self.assertEqual(self.c.post("/api/platform/post/%s/rating" % post["id"], json={"rating": 9}).status_code, 400)
        c = self.c.post("/api/platform/post/%s/comment" % post["id"], json={"text": "nice <b>one</b>"}).get_json()["comment"]
        self.assertEqual(self.c.post("/api/platform/post/nope/comment", json={"text": "x"}).status_code, 400)
        s = self.c.get("/api/platform/state").get_json()["floor"][0]
        self.assertEqual((s["rating"], len(s["comments"]), s["media"] == post["media"]), (4, 1, True))
        self.assertEqual(self.c.delete("/api/platform/post/%s/comment/%s" % (post["id"], c["id"])).status_code, 200)
        self.assertEqual(self.c.delete("/api/platform/post/" + post["id"]).status_code, 200)
        self.assertEqual(self.c.get("/api/platform/media/" + post["media"]).status_code, 200, "the photo stays in the image vault after its post is deleted")
        self.assertEqual(self.c.delete("/api/platform/vault/" + post["media"]).status_code, 200)
        self.assertEqual(self.c.get("/api/platform/media/" + post["media"]).status_code, 404, "deleted from the vault with no post using it: the file is gone")

    def test_sweep_removes_orphans_even_if_a_delete_could_not(self):
        keep = pm.add_post("kept", pm.save_media(image_bytes()))
        orphan = pm.save_media(image_bytes())
        self.assertEqual(pm.sweep_media(), 1)
        self.assertIsNone(pm.media_path(orphan))
        self.assertIsNotNone(pm.media_path(keep["media"]), "a photo that a post uses is never swept")

    def test_photo_only_post_and_bad_upload(self):
        import io
        ok = self.c.post("/api/platform/post", data={"text": "", "image": (io.BytesIO(image_bytes()), "x.jpg")}, content_type="multipart/form-data")
        self.assertEqual(ok.status_code, 200)
        bad = self.c.post("/api/platform/post", data={"text": "hi", "image": (io.BytesIO(b"<svg onload=alert(1)>"), "x.svg")}, content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(len(self.c.get("/api/platform/state").get_json()["floor"]), 1, "a refused photo posts nothing")

    def test_posting_is_rate_limited(self):
        codes = [self.c.post("/api/platform/post", json={"text": "spam %d" % i}).status_code for i in range(pm.POSTS_PER_MINUTE + 3)]
        self.assertEqual(codes.count(200), pm.POSTS_PER_MINUTE)
        self.assertEqual(codes[-1], 429)

    def test_media_and_stream_are_locked_without_a_license(self):
        self.c.delete("/api/platform/license")
        self.assertEqual(self.c.get("/api/platform/media/" + "0" * 16).status_code, 402)
        self.assertEqual(self.c.get("/api/platform/stream").status_code, 402)


class ProfileWallTest(Base):
    def test_sections_are_cleaned_capped_and_unsafe_links_dropped(self):
        p = pm.save_profile({"name": "Ada", "headline": "Builder", "skills": ["Python", "python", " Flask ", "x" * 99] + ["s%d" % i for i in range(40)],
                             "experience": [{"title": "Founder", "org": "Acme", "period": "2024-now", "desc": "d" * 900}, {"nonsense": 1}, "junk"] + [{"title": "t%d" % i} for i in range(20)],
                             "projects": [{"name": "NEXXUS", "url": "https://example.com/x", "desc": "local-first"}, {"name": "bad", "url": "javascript:alert(1)"}],
                             "links": ["https://a.example", "ftp://no", "javascript:x"], "visible": {"links": True, "bogus": True}})
        self.assertEqual(p["skills"][:3], ["Python", "Flask", "x" * 30], "duplicates (any case) collapse and long skills are cut")
        self.assertEqual(len(p["skills"]), 20)
        self.assertEqual((len(p["experience"]), len(p["experience"][0]["desc"])), (10, 300))
        self.assertEqual([x["url"] for x in p["projects"]], ["https://example.com/x", ""])
        self.assertEqual(p["links"], ["https://a.example"])
        self.assertNotIn("bogus", p["visible"])
        self.assertTrue(p["visible"]["links"])

    def test_visitor_view_shows_only_what_is_marked_visible(self):
        post = pm.add_post("my launch day")
        pm.add_post("a private note")
        pm.add_comment(post["id"], "secret comment")
        pm.set_rating(post["id"], 5)
        pm.save_profile({"name": "Ada", "headline": "Builder", "location": "London", "about": "About me", "links": ["https://a.example"], "skills": ["Python"],
                         "experience": [{"title": "Founder"}], "featured": [post["id"], "nonexistent"], "visible": {"experience": False}})
        v = pm.visitor_view()
        self.assertEqual((v["name"], v["headline"], v["about"], v["skills"]), ("Ada", "Builder", "About me", ["Python"]))
        for hidden in ("location", "links", "experience"):
            self.assertNotIn(hidden, v, hidden + " is private by default / by choice")
        self.assertEqual([f["text"] for f in v["featured"]], ["my launch day"])
        blob = json.dumps(v)
        for secret in ("secret comment", "a private note", "rating", "comments"):
            self.assertNotIn(secret, blob)

    def test_featured_is_limited_and_follows_deletes(self):
        ids = [pm.add_post("p%d" % i)["id"] for i in range(5)]
        self.assertEqual(len(pm.save_profile({"featured": ids})["featured"]), pm.MAX_FEATURED)
        pm.delete_post(ids[0])
        self.assertNotIn(ids[0], pm.get_profile()["featured"])

    def test_a_partial_save_keeps_everything_else(self):
        pm.save_profile({"name": "Ada", "skills": ["Python"], "experience": [{"title": "Founder"}], "visible": {"links": True}})
        p = pm.save_profile({"headline": "Builder"})                      # what the small edit form sends
        self.assertEqual((p["name"], p["headline"], p["skills"], p["experience"][0]["title"]), ("Ada", "Builder", ["Python"], "Founder"))
        self.assertTrue(p["visible"]["links"], "visibility choices survive a partial save too")
        p = pm.save_profile({"skills": []})
        self.assertEqual(p["skills"], [], "an explicit empty list does clear it")
        self.assertEqual(pm.save_profile({"visible": {"about": False}})["visible"]["about"], False)
        self.assertEqual(pm.save_profile({"unknown": 1, "visible": "nonsense"})["name"], "Ada")

    def test_default_visibility_hides_contact_like_details(self):
        v = pm.get_profile()["visible"]
        self.assertFalse(v["links"] or v["location"])
        self.assertTrue(v["about"] and v["experience"] and v["skills"])


class VaultTest(Base):
    def setUp(self):
        super().setUp()
        pm._recent_posts.clear()

    def test_posted_photos_land_in_the_vault_and_survive_the_post(self):
        mid = pm.save_media(image_bytes())
        post = pm.add_post("pic", mid)
        self.assertEqual([v["id"] for v in pm.vault_list()], [mid])
        self.assertEqual(pm.vault_list()[0]["posts"], [post["id"]])
        pm.delete_post(post["id"])
        self.assertIsNotNone(pm.media_path(mid), "deleting the post keeps the photo in the vault")
        self.assertEqual(pm.vault_list()[0]["posts"], [])

    def test_direct_upload_post_from_vault_and_delete(self):
        mid = pm.save_media(image_bytes())
        self.assertEqual(pm.vault_add(mid, "C:\fake\path\holiday.jpg", "upload")["name"], "holiday.jpg", "only the file name is kept")
        self.assertEqual(pm.sweep_media(), 0, "a vault photo is never swept")
        post = pm.add_post("from the vault", mid)
        self.assertEqual(len(pm.vault_list()), 1, "posting a vault photo does not duplicate it")
        self.assertTrue(pm.vault_delete(mid))
        self.assertIsNotNone(pm.media_path(mid), "a post still uses it, so the file stays")
        pm.delete_post(post["id"])
        self.assertEqual(pm.sweep_media(), 0)
        self.assertIsNone(pm.media_path(mid), "no post, no vault entry, no profile photo: gone")

    def test_profile_photo_protects_the_file_and_must_be_real(self):
        mid = pm.save_media(image_bytes())
        pm.vault_add(mid, "me.jpg")
        self.assertEqual(pm.save_profile({"avatar": mid})["avatar"], mid)
        pm.vault_delete(mid)
        self.assertIsNotNone(pm.media_path(mid), "the profile photo keeps its file")
        self.assertEqual(pm.save_profile({"avatar": "0123456789abcdef"})["avatar"], "", "an avatar that does not exist is dropped")
        self.assertEqual(pm.save_profile({"avatar": "../../x"})["avatar"], "")

    def test_vault_routes(self):
        import io
        app = Flask(__name__); pm.register_routes(app, lambda: True, lambda p, s=200: (jsonify(p), s)); c = app.test_client()
        c.post("/api/platform/license", json={"token": token()})
        up = c.post("/api/platform/vault", data={"image": (io.BytesIO(image_bytes(exif=True)), "me.jpg")}, content_type="multipart/form-data").get_json()["item"]
        self.assertEqual(c.post("/api/platform/vault", data={"image": (io.BytesIO(b"<svg onload=1>"), "x.svg")}, content_type="multipart/form-data").status_code, 400)
        self.assertEqual([i["id"] for i in c.get("/api/platform/vault").get_json()["items"]], [up["id"]])
        p = c.post("/api/platform/vault/%s/post" % up["id"], json={"text": "from vault"}).get_json()["post"]
        self.assertEqual(p["media"], up["id"])
        self.assertEqual(c.post("/api/platform/vault/%s/post" % ("f" * 16), json={}).status_code, 404)
        self.assertEqual(c.delete("/api/platform/vault/" + up["id"]).status_code, 200)
        self.assertEqual(c.delete("/api/platform/vault/" + up["id"]).status_code, 404)
        pub = c.get("/api/platform/profile/public").get_json()["profile"]
        self.assertNotIn("vault", json.dumps(pub), "the vault is private: visitors never see it")

    def test_vault_changes_reach_every_viewport(self):
        del pm._subs[:]
        q = pm.subscribe()
        mid = pm.save_media(image_bytes())
        pm.vault_add(mid, "a.jpg")
        pm.vault_delete(mid)
        self.assertEqual([e["type"] for e in [q.get_nowait() for _ in range(q.qsize())]], ["vault_added", "vault_deleted"])


class LiveSyncTest(Base):
    """Two viewports (two subscribers): everything one does reaches the other at once, in order, without a reload."""

    def setUp(self):
        super().setUp()
        pm._recent_posts.clear()
        del pm._subs[:]

    def drain(self, q):
        out = []
        while not q.empty():
            out.append(q.get_nowait())
        return out

    def test_every_change_reaches_every_viewport(self):
        a, b = pm.subscribe(), pm.subscribe()
        post = pm.add_post("hello")
        pm.set_rating(post["id"], 5)
        c = pm.add_comment(post["id"], "first")
        pm.delete_comment(post["id"], c["id"])
        pm.save_profile({"name": "Ada"})
        pm.delete_post(post["id"])
        for q in (a, b):
            self.assertEqual([e["type"] for e in self.drain(q)], ["post", "rating", "comment", "comment_deleted", "profile", "post_deleted"])

    def test_unsubscribed_and_stuck_viewports_do_not_block_others(self):
        a, b = pm.subscribe(), pm.subscribe()
        pm.unsubscribe(a)
        for i in range(250):
            pm.publish({"type": "x", "i": i})              # b is never read: its queue fills and drops the oldest
        self.assertEqual(self.drain(a), [])
        self.assertEqual(len(self.drain(b)), 200)
        self.assertEqual(pm.viewers(), 1)

    def test_viewport_cap(self):
        qs = [pm.subscribe() for _ in range(pm.MAX_STREAMS)]
        self.assertTrue(all(qs))
        self.assertIsNone(pm.subscribe())

    def test_the_stream_route_sends_events_as_they_happen(self):
        self.local = True
        app = Flask(__name__)
        pm.register_routes(app, lambda: True, lambda p, s=200: (jsonify(p), s))
        c = app.test_client()
        c.post("/api/platform/license", json={"token": token()})
        r = c.get("/api/platform/stream", buffered=False)
        self.assertEqual(r.mimetype, "text/event-stream")
        it = iter(r.response)
        self.assertIn(b"event: hello", next(it))
        pm.add_post("live one")
        seen = b""
        for _ in range(3):
            seen += next(it)
            if b"live one" in seen:
                break
        self.assertIn(b'"type": "post"', seen)
        self.assertIn(b"live one", seen)
        r.close()


if __name__ == "__main__":
    unittest.main()
