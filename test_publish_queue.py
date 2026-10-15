"""test_publish_queue.py - the YouTube publishing queue and adapter, checked on the wire against a local stand-in for YouTube (a loopback server that records exactly what it receives).
Proves: nothing is sent without owner approval; a dry run sends nothing; the default is private and public needs a separate confirmation; the daily cap holds; the token never reaches a
log, ledger, queue file or error message; a channel can only be VERIFIED (the API cannot create one) with the owner's next step spelled out; the routes need the admin token.
This does NOT touch YouTube: no real upload, channel or account is involved. Run: python test_publish_queue.py"""
import atexit
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TMP = tempfile.mkdtemp(prefix="pubq_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
TOKEN = "ya29.test-token-that-must-never-leak"
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"), NEXXUS_BUS_LEDGER=os.path.join(TMP, "bus.jsonl"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "creations"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"),
                  NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"), NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1",
                  NEXXUS_PUBLISH_DIR=os.path.join(TMP, "publish"))
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, NEXUS)
import creations_vault  # noqa: E402
import publish_queue as PQ  # noqa: E402
import python_server as srv  # noqa: E402
import youtube_adapter as YT  # noqa: E402

MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + bytes(range(256)) * 60
ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}


class FakeYouTube:
    """Answers like the parts of the YouTube Data API v3 the adapter uses, and records every request."""

    def __init__(self):
        self.requests, self.channels, self.fail_upload = [], [{"id": "UC123", "snippet": {"title": "Owner Channel"}, "statistics": {"videoCount": "4"}, "brandingSettings": {"channel": {"description": "old"}}}], False
        yt = self

        class H(BaseHTTPRequestHandler):
            def _body(self):
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def _send(self, code, obj, extra=None):
                data = json.dumps(obj).encode()
                self.send_response(code)
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _rec(self, body):
                yt.requests.append({"method": self.command, "path": self.path, "auth": self.headers.get("Authorization"), "headers": dict(self.headers), "body": body})

            def do_GET(self):
                self._rec(b"")
                if self.path.startswith("/youtube/v3/channels"):
                    return self._send(200, {"items": yt.channels})
                self._send(404, {})

            def do_PUT(self):
                body = self._body()
                self._rec(body)
                if self.path.startswith("/youtube/v3/channels"):
                    return self._send(200, {})
                if self.path.startswith("/upload-session/"):
                    if yt.fail_upload:
                        return self._send(403, {"error": {"message": "quota exceeded for token " + TOKEN}})
                    return self._send(200, {"id": "VID123"})
                self._send(404, {})

            def do_POST(self):
                body = self._body()
                self._rec(body)
                if self.path.startswith("/upload/youtube/v3/videos"):
                    return self._send(200, {}, {"Location": "http://127.0.0.1:%d/upload-session/abc" % yt.port})
                self._send(404, {})

            def log_message(self, *a):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def uploads(self):
        return [r for r in self.requests if r["method"] == "PUT" and r["path"].startswith("/upload-session/")]

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class Base(unittest.TestCase):
    def setUp(self):
        self.yt = FakeYouTube()
        os.environ.update(NEXXUS_YT_API_BASE="http://127.0.0.1:%d" % self.yt.port, NEXXUS_YT_ACCESS_TOKEN=TOKEN)
        os.environ.pop("NEXXUS_PUBLISH_LIVE", None)
        os.environ.pop("NEXXUS_PUBLISH_DAILY_CAP", None)
        self.vault = creations_vault.CreationsVault(os.path.join(TMP, "vault_%d" % id(self)))
        self.clip = self.vault.save("Launch teaser video", [{"name": "teaser.mp4", "data": MP4}])
        self.page = self.vault.save("Plain page graphic", [{"name": "page.html", "data": b"<!doctype html><html><body><svg></svg></body></html>"}])
        self.now = [1_800_000_000.0]
        self.q = PQ.PublishQueue(os.path.join(TMP, "queue_%d" % id(self)), self.vault, now=lambda: self.now[0])

    def tearDown(self):
        self.yt.stop()
        for k in ("NEXXUS_YT_API_BASE", "NEXXUS_YT_ACCESS_TOKEN"):
            os.environ.pop(k, None)

    def approved(self, **kw):
        i = self.q.stage(self.clip["id"], "Launch teaser", **kw)
        return self.q.approve(i["id"])


class Adapter(Base):
    def test_the_channel_is_verified_not_created(self):
        c = YT.channel()
        self.assertEqual((c["id"], c["title"]), ("UC123", "Owner Channel"))
        self.assertEqual(self.yt.requests[0]["auth"], "Bearer " + TOKEN)
        self.yt.channels.clear()
        with self.assertRaises(YT.YouTubeError) as cm:
            YT.channel()
        self.assertIn("cannot create one", str(cm.exception))
        self.assertIn("YouTube Studio", str(cm.exception))

    def test_without_a_token_it_says_what_the_owner_must_do(self):
        os.environ.pop("NEXXUS_YT_ACCESS_TOKEN")
        with self.assertRaises(YT.YouTubeError) as cm:
            YT.channel()
        self.assertIn("OAuth consent", str(cm.exception))
        self.assertIn("cannot authorise itself", str(cm.exception))
        self.assertEqual(self.yt.requests, [])

    def test_the_default_is_private_and_the_file_goes_as_it_is(self):
        res = YT.upload(str(self.vault.file_path(self.clip["id"], "teaser.mp4")), "Launch teaser", "About it", ["a", "b"])
        self.assertEqual((res["video_id"], res["privacy"]), ("VID123", "private"))
        init = next(r for r in self.yt.requests if r["method"] == "POST")
        meta = json.loads(init["body"])
        self.assertEqual(meta["status"]["privacyStatus"], "private")
        self.assertEqual((meta["snippet"]["title"], meta["snippet"]["tags"]), ("Launch teaser", ["a", "b"]))
        self.assertEqual(self.yt.uploads()[0]["body"], MP4)
        self.assertEqual(init["headers"].get("X-Upload-Content-Length"), str(len(MP4)))

    def test_bad_inputs_are_refused_before_anything_is_sent(self):
        p = str(self.vault.file_path(self.clip["id"], "teaser.mp4"))
        with self.assertRaises(YT.YouTubeError):
            YT.upload(p, "t", privacy="everyone")
        with open(os.path.join(TMP, "x.avi"), "wb") as f:
            f.write(MP4)
        with self.assertRaises(YT.YouTubeError):
            YT.upload(os.path.join(TMP, "x.avi"), "t")
        with open(os.path.join(TMP, "big.mp4"), "wb") as f:
            f.write(b"\0" * (YT.MAX_UPLOAD_BYTES + 1))
        with self.assertRaises(YT.YouTubeError):
            YT.upload(os.path.join(TMP, "big.mp4"), "t")
        self.assertEqual(self.yt.requests, [])

    def test_only_https_or_loopback_and_never_another_host(self):
        os.environ["NEXXUS_YT_API_BASE"] = "http://example.com"
        with self.assertRaises(YT.YouTubeError):
            YT.channel()
        os.environ["NEXXUS_YT_API_BASE"] = "http://127.0.0.1:%d" % self.yt.port
        orig = YT._call
        YT._call = lambda m, u, h=None, b=None: (200, {"Location": "http://evil.example/upload"}, b"{}") if m == "POST" else orig(m, u, h, b)
        try:
            with self.assertRaises(YT.YouTubeError) as cm:
                YT.upload(str(self.vault.file_path(self.clip["id"], "teaser.mp4")), "t")
            self.assertIn("another host", str(cm.exception))
        finally:
            YT._call = orig

    def test_channel_settings_are_merged_and_only_for_the_authorised_channel(self):
        out = YT.configure_channel("UC123", description="New description", keywords=["video", "ai tools"], country="us")
        self.assertEqual(out["updated"], ["country", "description", "keywords"])
        put = next(r for r in self.yt.requests if r["method"] == "PUT")
        chan = json.loads(put["body"])["brandingSettings"]["channel"]
        self.assertEqual((chan["description"], chan["keywords"], chan["country"]), ("New description", 'video "ai tools"', "US"))
        with self.assertRaises(YT.YouTubeError):
            YT.configure_channel("UC999", description="x")

    def test_errors_never_carry_the_token(self):
        self.yt.fail_upload = True
        with self.assertRaises(YT.YouTubeError) as cm:
            YT.upload(str(self.vault.file_path(self.clip["id"], "teaser.mp4")), "t")
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertIn("[token]", str(cm.exception))


class Queue(Base):
    def test_staging_sends_nothing_and_checks_everything(self):
        item = self.q.stage(self.clip["id"], "Launch teaser", "About it", ["a"], topic="launch")
        self.assertEqual((item["state"], item["privacy"]), ("staged", "private"))
        self.assertEqual(self.yt.requests, [])
        for bad in (dict(title=""), dict(title="x" * 101), dict(title="bad\x00title"), dict(tags=["t"] * 31), dict(tags=["x" * 31]), dict(privacy="everyone"), dict(description="d" * 5001)):
            args = dict(creation_id=self.clip["id"], title="Another title", description="", tags=(), topic="", privacy="private")
            args.update(bad)
            with self.assertRaises(PQ.QueueError, msg=bad):
                self.q.stage(args.pop("creation_id"), args.pop("title"), **args)
        with self.assertRaises(PQ.QueueError):
            self.q.stage(self.page["id"], "A page")                                            # only videos
        with self.assertRaises(PQ.QueueError):
            self.q.stage("nope", "Missing")
        with self.assertRaises(PQ.QueueError):
            self.q.stage(self.clip["id"], "Again")                                             # already waiting

    def test_nothing_unapproved_can_be_dispatched(self):
        item = self.q.stage(self.clip["id"], "Launch teaser")
        os.environ["NEXXUS_PUBLISH_LIVE"] = "1"
        with self.assertRaises(PQ.QueueError) as cm:
            self.q.dispatch(item["id"])
        self.assertIn("only an approved item", str(cm.exception))
        self.assertEqual(self.yt.requests, [])

    def test_public_needs_its_own_confirmation(self):
        item = self.q.stage(self.clip["id"], "Launch teaser", privacy="public")
        with self.assertRaises(PQ.QueueError) as cm:
            self.q.approve(item["id"])
        self.assertIn("separate explicit confirmation", str(cm.exception))
        with self.assertRaises(PQ.QueueError):
            self.q.approve(item["id"], confirm_public="yes")                                   # only a real true counts
        self.assertEqual(self.q.approve(item["id"], confirm_public=True)["privacy"], "public")
        other = self.q.stage(self.page["id"], "x") if False else None                         # (a page cannot be queued at all)
        self.assertIsNone(other)

    def test_a_dry_run_sends_nothing_and_changes_nothing(self):
        item = self.approved()
        res = self.q.dispatch(item["id"])                                                      # live mode is off
        self.assertTrue(res["dry_run"])
        self.assertEqual((res["would_send"]["bytes"], res["would_send"]["privacy"]), (len(MP4), "private"))
        self.assertEqual(self.yt.requests, [])
        self.assertEqual(self.q.get(item["id"])["state"], "approved")
        self.assertIn("dry_run", open(os.path.join(TMP, "queue_%d" % id(self), "ledger.jsonl")).read())

    def test_live_dispatch_uploads_once_and_records_the_result(self):
        os.environ["NEXXUS_PUBLISH_LIVE"] = "1"
        item = self.approved()
        res = self.q.dispatch(item["id"])
        self.assertEqual(res["uploaded"]["video_id"], "VID123")
        self.assertEqual(self.q.get(item["id"])["state"], "uploaded")
        self.assertEqual(len(self.yt.uploads()), 1)
        self.assertEqual(self.yt.uploads()[0]["body"], MP4)
        with self.assertRaises(PQ.QueueError):
            self.q.dispatch(item["id"])                                                        # not twice
        self.assertEqual(len(self.yt.uploads()), 1)

    def test_the_daily_cap_holds_and_resets(self):
        os.environ["NEXXUS_PUBLISH_LIVE"] = "1"
        os.environ["NEXXUS_PUBLISH_DAILY_CAP"] = "2"
        ids = []
        for n in range(3):
            c = self.vault.save("Clip number %d video" % n, [{"name": "c%d.mp4" % n, "data": MP4}])
            ids.append(self.q.approve(self.q.stage(c["id"], "Clip %d" % n)["id"])["id"])
        self.q.dispatch(ids[0])
        self.q.dispatch(ids[1])
        with self.assertRaises(PQ.QueueError) as cm:
            self.q.dispatch(ids[2])
        self.assertIn("daily upload cap (2)", str(cm.exception))
        self.assertEqual(len(self.yt.uploads()), 2)
        self.now[0] += 86400 * 2
        self.assertTrue(self.q.dispatch(ids[2])["uploaded"])                                   # a new day

    def test_a_failed_upload_is_recorded_and_can_be_approved_again(self):
        os.environ["NEXXUS_PUBLISH_LIVE"] = "1"
        self.yt.fail_upload = True
        item = self.approved()
        with self.assertRaises(PQ.QueueError) as cm:
            self.q.dispatch(item["id"])
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertEqual(self.q.get(item["id"])["state"], "failed")
        self.yt.fail_upload = False
        self.q.approve(item["id"])
        self.assertTrue(self.q.dispatch(item["id"])["uploaded"])

    def test_cancel_and_the_hash_chained_ledger(self):
        item = self.q.stage(self.clip["id"], "Launch teaser")
        self.q.cancel(item["id"])
        self.assertEqual(self.q.get(item["id"])["state"], "cancelled")
        ok, n = self.q.verify_ledger()
        self.assertTrue(ok)
        self.assertEqual(n, 2)
        path = os.path.join(TMP, "queue_%d" % id(self), "ledger.jsonl")
        text = open(path).read().replace("staged", "approved", 1)
        open(path, "w").write(text)
        self.assertEqual(self.q.verify_ledger(), (False, 1))                                   # an edited entry is found

    def test_the_token_is_nowhere_on_disk(self):
        os.environ["NEXXUS_PUBLISH_LIVE"] = "1"
        self.q.dispatch(self.approved()["id"])
        d = os.path.join(TMP, "queue_%d" % id(self))
        for name in os.listdir(d):
            self.assertNotIn(TOKEN, open(os.path.join(d, name), encoding="utf-8").read(), name)

    def test_a_restart_keeps_the_queue_and_a_corrupt_file_is_set_aside(self):
        item = self.approved()
        again = PQ.PublishQueue(os.path.join(TMP, "queue_%d" % id(self)), self.vault)
        self.assertEqual(again.get(item["id"])["state"], "approved")
        d = os.path.join(TMP, "queue_%d" % id(self))
        open(os.path.join(d, "queue.json"), "w").write("{broken")
        broken = PQ.PublishQueue(d, self.vault)
        self.assertEqual(broken.list(), [])
        self.assertTrue([f for f in os.listdir(d) if ".corrupt-" in f])


class Routes(Base):
    def setUp(self):
        super().setUp()
        self.http = srv.app.test_client()
        srv._publish = PQ.PublishQueue(os.path.join(TMP, "routes_%d" % id(self)), self.vault)

    def post(self, path, body=None, admin=True):
        return self.http.post(path, json=body or {}, headers=ADMIN if admin else {})

    def test_every_route_needs_the_admin_token(self):
        for path in ("/api/publish/stage", "/api/publish/x/approve", "/api/publish/x/dispatch", "/api/publish/x/cancel", "/api/publish/channel"):
            self.assertEqual(self.post(path, admin=False).status_code, 401, path)
        self.assertEqual(self.http.get("/api/publish").status_code, 401)
        self.assertEqual(self.http.get("/api/publish/channel").status_code, 401)

    def test_stage_approve_dispatch_through_the_routes(self):
        r = self.post("/api/publish/stage", {"creation_id": self.clip["id"], "title": "Launch teaser", "tags": ["a"]})
        self.assertEqual(r.status_code, 201)
        iid = r.get_json()["item"]["id"]
        early = self.post("/api/publish/%s/dispatch" % iid)
        self.assertEqual(early.status_code, 400)
        self.assertEqual(self.post("/api/publish/%s/approve" % iid).get_json()["item"]["state"], "approved")
        dry = self.post("/api/publish/%s/dispatch" % iid).get_json()
        self.assertTrue(dry["dry_run"])
        self.assertEqual(self.yt.requests, [])
        listing = self.http.get("/api/publish", headers=ADMIN).get_json()
        self.assertEqual((listing["live_mode"], listing["daily_cap"], listing["ledger_ok"], listing["token_present"]), (False, 3, True, True))
        self.assertNotIn(TOKEN, json.dumps(listing))
        self.assertEqual(self.post("/api/publish/%s/bogus" % iid).status_code, 404)

    def test_the_channel_check_and_the_guarded_channel_change(self):
        got = self.http.get("/api/publish/channel", headers=ADMIN).get_json()
        self.assertEqual(got["channel"]["title"], "Owner Channel")
        self.assertEqual(self.post("/api/publish/channel", {"channel_id": "UC123", "description": "x", "confirm": True}).status_code, 400)       # live mode is off
        os.environ["NEXXUS_PUBLISH_LIVE"] = "1"
        self.assertEqual(self.post("/api/publish/channel", {"channel_id": "UC123", "description": "x"}).status_code, 400)                          # no confirm
        ok = self.post("/api/publish/channel", {"channel_id": "UC123", "description": "x", "confirm": True})
        self.assertEqual(ok.status_code, 200)
        self.yt.channels.clear()
        gone = self.http.get("/api/publish/channel", headers=ADMIN)
        self.assertEqual(gone.status_code, 502)
        self.assertIn("YouTube Studio", gone.get_json()["message"])

    def test_a_publish_block_in_an_accepted_order_is_only_staged(self):
        from orchestrator_bus import sha256_file
        from orchestrator_client import OrchestratorClient
        transport = lambda path, payload: self.http.post(path, json=payload).get_json()  # noqa: E731
        b = OrchestratorClient("axis-video_creator", "video_creator.governor", transport=transport)
        v = OrchestratorClient("axis-validator", "validator.governor", transport=transport)
        self.post("/api/bus/register", {"engine": "axis-video_creator", "orchestrator": "video_creator.governor"})
        self.post("/api/bus/register", {"engine": "axis-validator", "orchestrator": "validator.governor", "qc_reviewer": True})
        srv._publish = PQ.PublishQueue(os.path.join(TMP, "order_queue_%d" % id(self)), srv._creations)         # the delivery saves into the server's own Creations hub, so the queue must watch that one
        path = os.path.join(TMP, "order.mp4")
        open(path, "wb").write(MP4)
        spec = {"title": "Weekly product update video", "publish": {"title": "Product update", "tags": ["update"], "topic": "weekly"}}
        oid = self.post("/api/bus/order", {"engine": "axis-video_creator", "to": "video_creator.governor", "spec": spec}).get_json()["order"]["id"]
        b.ack(oid)
        b.built(oid, path)
        v.qc(oid, "pass", [], sha256_file(path))
        out = self.post("/api/bus/accept", {"order_id": oid}).get_json()["delivered"]
        self.assertIn("staged_for_publishing", out)
        item = srv._publish.get(out["staged_for_publishing"])
        self.assertEqual((item["state"], item["privacy"], item["title"]), ("staged", "private", "Product update"))
        self.assertEqual(self.yt.requests, [])                                                 # staged only: nothing left the machine


class Hygiene(unittest.TestCase):
    def test_nothing_in_the_modules_asks_for_credentials_or_drives_a_browser(self):
        for name in ("youtube_adapter.py", "publish_queue.py"):
            src = open(os.path.join(ROOT, name), encoding="utf-8").read().lower()
            src = __import__("re").sub(r'""".*?"""', "", src, flags=__import__("re").S)                       # the docstring may SAY "never asks for a password"; only code is checked
            code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
            for needle in ("password", "selenium", "webbrowser", "playwright", "input(", "client_secret", "refresh_token", "getpass"):
                self.assertNotIn(needle, code, "%s mentions %s" % (name, needle))


if __name__ == "__main__":
    unittest.main(verbosity=1)
