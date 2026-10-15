"""test_feed.py - the signed source feed and license tokens: signing, tamper and wrong-key refusal, replay, staleness, size, domain separation, the public-safety gate, the publisher against a fake hub,
and the client against a local web server (fetch, replay, offline, tampered cache, unset address). Everything uses temp folders and throwaway keys.
Run: python test_feed.py"""
import atexit
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

TMP = tempfile.mkdtemp(prefix="feed_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus"))
os.environ.update({"NEXXUS_ADMIN_TOKEN": "throwaway-admin", "NEXXUS_GOVERNANCE_SECRET": "throwaway-secret", "NEXXUS_UI_ROOT": os.path.join(TMP, "ui"), "NEXXUS_ENGINE_STAGING": os.path.join(TMP, "staging", "engines"),
                   "NEXXUS_ENGINE_LEDGER": os.path.join(TMP, "ledger.jsonl"), "NEXXUS_NOTIFICATIONS_FILE": os.path.join(TMP, "notifs.json"), "NEXXUS_PERIMETER_DIR": os.path.join(TMP, "perim"),
                   "NEXXUS_DISABLE_AUTOSCHEDULER": "1"})
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
os.environ["NEXXUS_FEED_KEY"] = os.path.join(TMP, "key", "feed_signing_key.pem")
os.environ["NEXXUS_FEED_OUT"] = os.path.join(TMP, "out")
os.environ["NEXXUS_FEED_OUTPUTS"] = os.path.join(TMP, "outputs")
os.environ["NEXXUS_FEED_CACHE"] = os.path.join(TMP, "cache")
os.environ["NEXXUS_FEED_PUBKEY"] = os.path.join(TMP, "pub.pem")

import feed_core  # noqa: E402
import feed_publish  # noqa: E402
import feed_client  # noqa: E402

feed_publish.PUB_PATH = os.path.join(TMP, "pub.pem")
PRIV, PUB = feed_core.generate_keypair()
OTHER_PRIV, OTHER_PUB = feed_core.generate_keypair()
NOW = 1_800_000_000


class FakeHub(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/mesh/telemetry":
            body = {"engines": {"a": {"live": {"fresh": True}, "mesh_ready": True}, "b": {"live": {"fresh": False}, "mesh_ready": True}}, "hub": {"uptime_s": 4321.5}}
        elif self.path == "/api/dashboards/audit":
            body = {"ok": True, "orphans": [], "engine_cluster": {"ok": True, "live": 1, "members": 2, "dead_processes": ["b"]}}
        else:
            self.send_error(404)
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def serve(directory=None, handler=None):
    if handler is None:
        class H(http.server.SimpleHTTPRequestHandler):
            def __init__(s, *a, **k):
                super().__init__(*a, directory=directory, **k)

            def log_message(s, *a):
                pass
        handler = H
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Core(unittest.TestCase):
    def pack(self, seq=1, now=NOW, **kw):
        return feed_core.pack(feed_core.make_bundle(seq, {"x": 1}, now=now, **kw), PRIV)

    def test_roundtrip(self):
        r = feed_core.verify_bundle(self.pack(), PUB, now=NOW + 60)
        self.assertEqual((r["bundle"]["sequence"], r["stale"]), (1, False))

    def test_tampered_bundle_refused(self):
        doc = json.loads(self.pack())
        doc["bundle"]["sections"]["x"] = 2
        with self.assertRaisesRegex(feed_core.FeedError, "signature"):
            feed_core.verify_bundle(json.dumps(doc).encode(), PUB, now=NOW)

    def test_wrong_key_refused(self):
        with self.assertRaisesRegex(feed_core.FeedError, "signature"):
            feed_core.verify_bundle(self.pack(), OTHER_PUB, now=NOW)

    def test_replay_future_stale_size_garbage_schema(self):
        with self.assertRaisesRegex(feed_core.FeedError, "replay"):
            feed_core.verify_bundle(self.pack(seq=3), PUB, last_sequence=3, now=NOW)
        with self.assertRaisesRegex(feed_core.FeedError, "future"):
            feed_core.verify_bundle(self.pack(now=NOW + 10_000), PUB, now=NOW)
        self.assertTrue(feed_core.verify_bundle(self.pack(valid_hours=1), PUB, now=NOW + 7200)["stale"])          # shown, but flagged
        with self.assertRaisesRegex(feed_core.FeedError, "larger"):
            feed_core.verify_bundle(b"x" * (feed_core.MAX_BYTES + 1), PUB)
        with self.assertRaisesRegex(feed_core.FeedError, "format"):
            feed_core.verify_bundle(b"not json", PUB)
        bad = feed_core.make_bundle(1, {}, now=NOW)
        bad["schema"] = "other/9"
        with self.assertRaisesRegex(feed_core.FeedError, "schema"):
            feed_core.verify_bundle(json.dumps({"bundle": bad, "signature": feed_core.sign(bad, PRIV)}).encode(), PUB, now=NOW)

    def test_license_and_domain_separation(self):
        tok = feed_core.issue_license("4821", "Jane Doe", "commercial", PRIV, now=NOW)
        self.assertEqual(feed_core.check_license(tok, PUB)["number"], "4821")
        with self.assertRaises(feed_core.FeedError):
            feed_core.check_license(tok, OTHER_PUB)
        forged = json.loads(json.dumps(tok))
        forged["claims"]["holder"] = "Someone Else"
        with self.assertRaises(feed_core.FeedError):
            feed_core.check_license(forged, PUB)
        bundle = feed_core.make_bundle(1, {}, now=NOW)                                        # a feed signature is not a license, and a license signature is not a feed
        self.assertFalse(feed_core.verify_signature(tok["claims"], feed_core.sign(tok["claims"], PRIV), PUB, feed_core.DOMAIN_LICENSE))
        self.assertFalse(feed_core.verify_signature(bundle, feed_core.sign(bundle, PRIV, feed_core.DOMAIN_LICENSE), PUB, feed_core.DOMAIN_FEED))

    def test_public_safety_gate(self):
        feed_core.assert_public_safe({"a": 1, "b": "plain words", "c": [True, 2.5, None]})
        for bad in ("C:\\Users\\x\\file.py", "http://127.0.0.1:8000/x", "100.116.81.71", "192.168.1.5", "AIza" + "B" * 30, "AQ." + "c" * 30, "token = abc", "ghp_" + "a" * 25, "f" * 48):
            with self.assertRaises(feed_core.FeedError, msg=bad):
                feed_core.assert_public_safe({"field": bad})
        with self.assertRaises(feed_core.FeedError):
            feed_core.assert_public_safe({"C:\\secret\\key": 1})                                       # keys are checked too


class TestLogReading(unittest.TestCase):
    """The test counts in the feed must match the log however Windows encoded it (a byte-order mark once hid the first line and understated the result)."""
    BODY = "PASS  first suite  OK  (1 s)\nPASS  second suite  OK  (2 s)\nFAIL  third suite  broke  (3 s)\n\nALL GREEN\n"

    def counts(self, data):
        d = tempfile.mkdtemp(prefix="logs_", dir=TMP)
        open(os.path.join(d, "verify_all_2026-10-14.txt"), "wb").write(data)
        os.environ["NEXXUS_FEED_LOGS"] = d
        try:
            return feed_publish.latest_tests()
        finally:
            os.environ.pop("NEXXUS_FEED_LOGS", None)

    def test_every_encoding_gives_the_same_counts(self):
        for name, data in (("utf-8", self.BODY.encode("utf-8")), ("utf-8 with BOM", b"\xef\xbb\xbf" + self.BODY.encode("utf-8")), ("utf-16", self.BODY.encode("utf-16")),
                           ("crlf", self.BODY.replace("\n", "\r\n").encode("utf-8"))):
            t = self.counts(data)
            self.assertEqual((t["suites_passed"], t["suites_failed"], t["run_date"]), (2, 1, "2026-10-14"), name)
            self.assertFalse(t["all_green"], name)                                                  # a FAIL line means not green, whatever the text says

    def test_no_log_means_not_available(self):
        d = tempfile.mkdtemp(prefix="nolog_", dir=TMP)
        os.environ["NEXXUS_FEED_LOGS"] = d
        try:
            self.assertEqual(feed_publish.latest_tests(), {"available": False})
        finally:
            os.environ.pop("NEXXUS_FEED_LOGS", None)


class PublisherAndClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(os.path.dirname(feed_publish.KEY_PATH), exist_ok=True)
        open(feed_publish.KEY_PATH, "wb").write(PRIV)
        open(os.environ["NEXXUS_FEED_PUBKEY"], "wb").write(PUB)
        cls.hub = serve(handler=FakeHub)
        cls.hub_url = "http://127.0.0.1:%d" % cls.hub.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.hub.shutdown()

    def test_1_publish_real_results_and_refuse_incomplete_outputs(self):
        os.makedirs(feed_publish.OUTPUTS_DIR, exist_ok=True)
        bad = os.path.join(feed_publish.OUTPUTS_DIR, "x.json")
        json.dump({"title": "T", "summary": "S"}, open(bad, "w"))
        with self.assertRaisesRegex(feed_core.FeedError, "source and method"):
            feed_publish.build(self.hub_url)
        os.remove(bad)
        feed_publish.build(self.hub_url)
        doc = json.load(open(os.path.join(feed_publish.OUT_DIR, "latest.json")))
        sec = doc["bundle"]["sections"]
        self.assertEqual((sec["system"]["engines"], sec["system"]["engines_live"], sec["audit"]["engine_cluster_members"]), (2, 1, 2))
        self.assertEqual(sec["outputs"], [])
        self.assertIn("No outputs have been published", sec["outputs_note"])
        self.assertNotIn("127.0.0.1", json.dumps(doc))                                              # nothing internal leaks into the public file
        feed_publish.build(self.hub_url)
        self.assertEqual(json.load(open(os.path.join(feed_publish.OUT_DIR, "latest.json")))["bundle"]["sequence"], 2)

    def test_2_a_real_output_is_included_with_its_source(self):
        json.dump({"title": "Probability run", "summary": "Result of one run", "source": "axis-logic probability engine", "method": "Run on data entered by the owner",
                   "generated_at": "2026-10-14", "data": {"events": 12}}, open(os.path.join(feed_publish.OUTPUTS_DIR, "run1.json"), "w"))
        feed_publish.build(self.hub_url)
        out = json.load(open(os.path.join(feed_publish.OUT_DIR, "latest.json")))["bundle"]["sections"]["outputs"]
        self.assertEqual((len(out), out[0]["source"]), (1, "axis-logic probability engine"))
        self.assertIn("Not advice", out[0]["notice"])
        os.remove(os.path.join(feed_publish.OUTPUTS_DIR, "run1.json"))

    def test_3_client_fetch_replay_offline_tamper_unset(self):
        self.assertIn("not set", feed_client.fetch()["message"])                                    # unset address: plain message, nothing downloaded
        self.assertFalse(feed_client.status()["ok"])
        os.environ["NEXXUS_FEED_URL"] = "ftp://example/latest.json"
        self.assertIn("http", feed_client.fetch()["message"])
        host = serve(feed_publish.OUT_DIR)
        os.environ["NEXXUS_FEED_URL"] = "http://127.0.0.1:%d/latest.json" % host.server_address[1]
        r = feed_client.fetch()
        self.assertTrue(r["ok"], r["message"])
        seq = r["bundle"]["sequence"]
        self.assertEqual(feed_client.status()["bundle"]["sequence"], seq)
        again = feed_client.fetch()                                                                 # the same feed again is a replay: refused, saved copy untouched
        self.assertFalse(again["ok"])
        self.assertIn("replay", again["message"])
        self.assertEqual(feed_client.status()["bundle"]["sequence"], seq)
        feed_publish.build(self.hub_url)                                                            # a newer one is accepted
        self.assertTrue(feed_client.fetch()["ok"])
        host.shutdown()
        host.server_close()
        off = feed_client.fetch()                                                                   # host gone: plain offline message, last verified copy still shown
        self.assertFalse(off["ok"])
        self.assertIn("Could not reach", off["message"])
        self.assertIn("last verified", off["message"])
        p = os.path.join(feed_client.CACHE_DIR, "latest.json")                                      # someone edits the saved file: it is no longer shown
        doc = json.load(open(p))
        doc["bundle"]["sections"]["system"]["engines_live"] = 999
        json.dump(doc, open(p, "w"))
        s = feed_client.status()
        self.assertFalse(s["ok"])
        self.assertIn("no longer verifies", s["message"])
        os.environ.pop("NEXXUS_FEED_URL", None)

    def test_4_a_forged_feed_from_the_host_is_refused(self):
        forged_dir = os.path.join(TMP, "forged")
        os.makedirs(forged_dir)
        open(os.path.join(forged_dir, "latest.json"), "wb").write(feed_core.pack(feed_core.make_bundle(99, {"system": {"engines_live": 21}}), OTHER_PRIV))
        host = serve(forged_dir)
        os.environ["NEXXUS_FEED_URL"] = "http://127.0.0.1:%d/latest.json" % host.server_address[1]
        r = feed_client.fetch()
        host.shutdown()
        self.assertFalse(r["ok"])
        self.assertIn("signature", r["message"])
        os.environ.pop("NEXXUS_FEED_URL", None)


class Routes(unittest.TestCase):
    """The hub's two feed routes, through the real server with a Flask test client."""
    @classmethod
    def setUpClass(cls):
        import python_server as srv
        cls.http = srv.app.test_client()

    def setUp(self):
        self._cache = feed_client.CACHE_DIR
        feed_client.CACHE_DIR = tempfile.mkdtemp(prefix="routecache_", dir=TMP)          # a clean cache: earlier tests leave a deliberately tampered one
        os.environ.pop("NEXXUS_FEED_URL", None)

    def tearDown(self):
        feed_client.CACHE_DIR = self._cache

    def test_latest_is_readable_and_plain_when_nothing_is_downloaded(self):
        r = self.http.get("/api/feed/latest")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["status"], "success")
        self.assertFalse(d["ok"])
        self.assertIn("No feed has been downloaded", d["message"])

    def test_refresh_needs_the_admin_token_and_reports_an_unset_address_plainly(self):
        self.assertEqual(self.http.post("/api/feed/refresh").status_code, 401)
        r = self.http.post("/api/feed/refresh", headers={"X-Nexxus-Admin-Token": "throwaway-admin"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("not set", r.get_json()["message"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
