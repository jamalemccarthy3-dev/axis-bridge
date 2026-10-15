"""test_campaign_routes.py - the campaign endpoints: every one needs the admin token, a kit is created from a profile (bad profiles are refused with a reason), kit files are served only from inside the
kit folder, the queue goes stage -> approve -> export through HTTP and exports a package without posting anything, and (where a voice and ffmpeg exist) a narrated video is rendered and served.
Throwaway token and folders. Run: python test_campaign_routes.py"""
import atexit
import json
import os
import shutil
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="camproutes_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"), NEXXUS_BUS_LEDGER=os.path.join(TMP, "ledger.jsonl"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "creations"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"),
                  NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"), NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1",
                  NEXXUS_PUBLISH_DIR=os.path.join(TMP, "pub"), NEXXUS_FACTORY_DIR=os.path.join(TMP, "factory"), NEXXUS_CAMPAIGN_DIR=os.path.join(TMP, "campaigns"))
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, NEXUS)
import campaign_media  # noqa: E402
from test_campaign_kit import PROFILE  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
HAVE_VOICE = bool(campaign_media.list_voices())


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv
        import python_server as srv  # noqa: E402
        cls.http = srv.app.test_client()

    def req(self, method, path, body=None, admin=True):
        return self.http.open(path, method=method, json=body, headers=ADMIN if admin else {})

    def kit(self, **over):
        r = self.req("POST", "/api/campaigns", {"profile": dict(PROFILE, **over)})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def test_everything_needs_the_admin_token(self):
        for m, p in (("GET", "/api/campaigns"), ("POST", "/api/campaigns"), ("GET", "/api/campaigns/kit-0123456789"), ("POST", "/api/campaigns/kit-0123456789/video"), ("GET", "/api/campaigns/kit-0123456789/file/manifest.json"),
                     ("GET", "/api/campaigns/queue"), ("POST", "/api/campaigns/queue"), ("POST", "/api/campaigns/queue/cq-x/approve"), ("POST", "/api/campaigns/queue/cq-x/export")):
            self.assertEqual(self.req(m, p, {} if m == "POST" else None, admin=False).status_code, 401, (m, p))

    def test_a_kit_is_made_listed_and_opened_and_bad_profiles_say_why(self):
        k = self.kit()
        self.assertTrue(k["id"].startswith("kit-"))
        self.assertEqual(k["kit"]["source"], "template")
        self.assertEqual(len(k["manifest"]["graphics"]), 7)
        listed = self.req("GET", "/api/campaigns").get_json()
        self.assertIn(k["id"], [x["id"] for x in listed["kits"]])
        self.assertIn("voices", listed)
        one = self.req("GET", "/api/campaigns/" + k["id"]).get_json()
        self.assertEqual(one["kit"]["profile"]["name"], "Harbor Bakery")
        for bad in ({"postal_address": ""}, {"cta_url": "javascript:alert(1)"}, {"differentiators": []}):
            r = self.req("POST", "/api/campaigns", {"profile": dict(PROFILE, **bad)})
            self.assertEqual(r.status_code, 400, bad)
            self.assertTrue(r.get_json()["message"])
        self.assertEqual(self.req("GET", "/api/campaigns/..%2f..%2fx").status_code, 404)
        self.assertEqual(self.req("GET", "/api/campaigns/kit-ffffffffff").status_code, 400)

    def test_files_are_served_only_from_inside_the_kit(self):
        k = self.kit()
        png = self.req("GET", "/api/campaigns/%s/file/graphics/social_1200x628.png" % k["id"])
        self.assertEqual((png.status_code, png.mimetype), (200, "image/png"))
        self.assertEqual(png.data[:8], b"\x89PNG\r\n\x1a\n")
        page = self.req("GET", "/api/campaigns/%s/file/landing/index.html" % k["id"])
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.mimetype, "text/plain")                                                   # shown as text, never run as a page on this origin
        for evil in ("../../python_server.py", "..%2f..%2fpython_server.py", "graphics/../../../python_server.py", "/etc/passwd", "kit.json.exe", "..\\..\\python_server.py"):
            r = self.req("GET", "/api/campaigns/%s/file/%s" % (k["id"], evil))
            self.assertNotIn(b"def command_dispatch", r.data, evil)
            self.assertIn(r.status_code, (400, 404), evil)

    def test_stage_approve_export_through_http_posts_nothing(self):
        k = self.kit()
        s = self.req("POST", "/api/campaigns/queue", {"kit": k["id"], "channel": "meta"})
        self.assertEqual(s.status_code, 201, s.get_json())
        iid = s.get_json()["item"]["id"]
        self.assertEqual(self.req("POST", "/api/campaigns/queue/%s/export" % iid, {}).status_code, 400)       # not approved yet
        self.assertEqual(self.req("POST", "/api/campaigns/queue/%s/approve" % iid, {"scheduled_at": "yesterday"}).status_code, 400)
        self.assertEqual(self.req("POST", "/api/campaigns/queue/%s/approve" % iid, {"scheduled_at": "2099-03-03 08:00"}).status_code, 200)
        e = self.req("POST", "/api/campaigns/queue/%s/export" % iid, {})
        self.assertEqual(e.status_code, 200, e.get_json())
        post = json.load(open(os.path.join(e.get_json()["item"]["export_dir"], "post.json"), encoding="utf-8"))
        self.assertEqual((post["posted"], post["scheduled_at"]), (False, "2099-03-03 08:00"))
        self.assertIn("AI-assisted", post["disclosure"])
        self.assertEqual(self.req("POST", "/api/campaigns/queue/%s/explode" % iid, {}).status_code, 404)
        self.assertEqual(self.req("POST", "/api/campaigns/queue", {"kit": k["id"], "channel": "myspace"}).status_code, 400)
        self.assertEqual(self.req("POST", "/api/campaigns/queue", {"kit": "../x", "channel": "meta"}).status_code, 400)
        self.assertEqual(self.req("POST", "/api/campaigns/queue", {"kit": k["id"], "channel": "youtube"}).status_code, 400)   # a video channel needs a rendered video

    @unittest.skipUnless(HAVE_VOICE, "no speech voice installed")
    def test_a_narrated_video_is_rendered_served_and_stageable(self):
        k = self.kit()
        r = self.req("POST", "/api/campaigns/%s/video" % k["id"], {"format": "social_15s", "mood": "calm", "seed": 3})
        self.assertEqual(r.status_code, 200, r.get_json())
        v = r.get_json()["video"]
        self.assertTrue(v["has_audio"] and 8 <= v["seconds"] <= 17.3)
        dl = self.req("GET", "/api/campaigns/%s/file/%s" % (k["id"], v["path"]))
        self.assertEqual((dl.status_code, dl.mimetype), (200, "video/mp4"))
        self.assertEqual(dl.data[4:8], b"ftyp")
        st = self.req("POST", "/api/campaigns/queue", {"kit": k["id"], "channel": "tiktok", "video": v["path"]})
        self.assertEqual(st.status_code, 201, st.get_json())
        self.assertEqual(self.req("POST", "/api/campaigns/%s/video" % k["id"], {"format": "no_such"}).status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=1)
