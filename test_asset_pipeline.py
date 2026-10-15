"""test_asset_pipeline.py - the asset pipeline, end to end: Creation mode's prompt-fidelity checks (does the page do what was ASKED, not just parse), the explicit length limits (a request is refused
out loud, never silently cut), and delivery of accepted bus builds (images, pages, video) into the Creations hub so the finished product reaches the page. Real server routes through the Flask
test client, throwaway token and folders. Nothing here calls a model. Run: python test_asset_pipeline.py"""
import atexit
import json
import os
import shutil
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="assetpipe_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"), NEXXUS_BUS_LEDGER=os.path.join(TMP, "ledger.jsonl"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "creations"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"),
                  NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"), NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1")
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, NEXUS)
import creation_mode as CM  # noqa: E402
import python_server as srv  # noqa: E402
from orchestrator_bus import sha256_file  # noqa: E402
from orchestrator_client import OrchestratorClient  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + bytes(range(256)) * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class Fidelity(unittest.TestCase):
    def test_text_the_request_asks_for_must_be_on_the_page(self):
        page = '<svg viewBox="0 0 10 10"><circle r="4"/><text>NEXXUS</text></svg>'
        self.assertEqual(CM.fidelity('a round badge saying "NEXXUS"', page), [])
        self.assertEqual(CM.fidelity("a badge reading NEXXUS", page), [])
        miss = CM.fidelity('a round badge saying "NEXXUS"', '<svg viewBox="0 0 10 10"><circle r="4"/></svg>')
        self.assertEqual(len(miss), 1)
        self.assertIn("NEXXUS", miss[0])
        self.assertEqual(CM.fidelity('a badge saying "NEXXUS"', "<svg><text>NEX<tspan>XUS</tspan></text></svg>"), [])      # split across tspans is still the text
        self.assertEqual(CM.fidelity('a badge saying "nexxus core"', "<svg><text>NEXXUS   CORE</text></svg>"), [])          # case and spacing do not matter
        self.assertEqual(CM.fidelity("a sign for Bob's cafe", "<svg><circle r='3'/></svg>"), [])                              # an apostrophe is not a quote
        self.assertEqual(CM.fidelity("draw a 'sunset' over hills", "<svg><circle r='3'/></svg>"), [])                        # a quoted SUBJECT is not lettering

    def test_named_colours_must_be_used(self):
        blue = '<svg><circle fill="#1e90ff"/></svg>'
        red = '<svg><circle fill="#ff0000"/></svg>'
        self.assertEqual(CM.fidelity("a blue circle", blue), [])
        self.assertTrue(CM.fidelity("a blue circle", red))
        self.assertIn("blue", CM.fidelity("a blue circle", red)[0])
        self.assertEqual(CM.fidelity("a red circle", '<svg><circle fill="crimson"/></svg>'), [])                             # CSS names count
        self.assertEqual(CM.fidelity("a red circle", '<svg><circle style="fill:rgb(220,20,30)"/></svg>'), [])
        self.assertEqual(CM.fidelity("a green star", '<svg><path fill="hsl(120, 60%, 40%)"/></svg>'), [])
        self.assertEqual(CM.fidelity("a gold crest", '<svg><path fill="#f4c20d"/></svg>'), [])
        self.assertEqual(CM.fidelity("a white ring on black", '<svg><rect fill="#000"/><circle stroke="#fff"/></svg>'), [])
        self.assertTrue(CM.fidelity("a purple badge", blue))
        self.assertEqual(CM.fidelity("a badge with no red in it", blue), [])                                                  # a negated colour is not demanded
        self.assertEqual(CM.fidelity("a plain badge", blue), [])                                                              # nothing checkable asked: nothing to fail

    def test_motion_and_glow_must_exist(self):
        still = '<svg><circle r="4"/></svg>'
        anim = "<svg><style>@keyframes s { to { transform: rotate(360deg) } } circle { animation: s 2s infinite }</style><circle r='4'/></svg>"
        self.assertTrue(CM.fidelity("an animated badge", still))
        self.assertEqual(CM.fidelity("an animated badge", anim), [])
        self.assertEqual(CM.fidelity("a still badge", still), [])
        pulse_only = "<svg><style>@keyframes p { to { opacity: .5 } } circle { animation: p 1s infinite }</style><circle r='4'/></svg>"
        self.assertTrue(CM.fidelity("a spinning badge", pulse_only))                                                          # it moves, but nothing rotates
        self.assertEqual(CM.fidelity("a spinning badge", anim), [])
        self.assertTrue(CM.fidelity("a glowing orb", still))
        self.assertEqual(CM.fidelity("a glowing orb", '<svg><filter id="g"><feGaussianBlur stdDeviation="3"/></filter><circle r="4" filter="url(#g)"/></svg>'), [])

    def test_check_page_reports_both_kinds_of_problem(self):
        problems, _ = CM.check_page('a blue badge saying "NEXXUS"', "<html><body><svg><circle fill='#f00'/></svg>")      # not closed, wrong colour, no text
        text = " | ".join(problems)
        self.assertIn("cut off", text)
        self.assertIn("blue", text)
        self.assertIn("NEXXUS", text)
        good = '<!doctype html><html><body><svg viewBox="0 0 10 10"><circle r="4" fill="#1e90ff"/><text>NEXXUS</text></svg></body></html>'
        self.assertEqual(CM.check_page('a blue badge saying "NEXXUS"', good)[0], [])

    def test_empty_and_odd_input_never_crash(self):
        for prompt, code in (("", ""), (None, None), ("a red thing", ""), ("a red thing", None), ("x" * 10000, "<svg></svg>")):
            self.assertIsInstance(CM.fidelity(prompt, code), list)


class Limits(unittest.TestCase):
    def test_a_long_request_is_refused_out_loud_not_cut(self):
        r = CM.handle("draw a logo " + "with many details " * 400)
        self.assertEqual(r["kind"], "say")
        self.assertIn("limit is %d" % CM.MAX_PROMPT, r["reply"])
        self.assertIn("will not cut it silently", r["reply"])
        res = CM.runner(None, {"prompt": "draw a logo " + "x" * (CM.MAX_PROMPT + 1)})
        self.assertEqual(res["status"], "error")
        self.assertIn("never silently cut", res["error"])

    def test_a_long_refine_request_is_refused_not_cut(self):
        long = "make it bigger " + "and bolder " * 300
        r = CM.handle(long, active_id="abc")
        self.assertEqual(r["kind"], "say")
        self.assertIn("limit is %d" % CM.MAX_INSTRUCTION, r["reply"])
        res = CM.refine_runner(None, {"instruction": long, "parent_id": "abc"})
        self.assertEqual(res["status"], "error")
        self.assertIn("never silently cut", res["error"])

    def test_a_request_inside_the_limit_is_passed_on_whole(self):
        text = "make the rays longer " + "and warmer " * 100            # about 1.2k characters: the old route cut at 600
        self.assertLess(len(text), CM.MAX_INSTRUCTION)
        self.assertEqual(CM.handle(text, active_id="abc")["instruction"], text.strip())

    def test_the_refine_route_refuses_instead_of_cutting(self):
        http = srv.app.test_client()
        orig = srv._mode_state.mode
        srv._mode_state._mode = "creation"                              # set() would fire the model-swap listener
        try:
            r = http.post("/api/creation/refine", json={"instruction": "make it bigger " * 200, "parent_id": "x" * 3})
            self.assertEqual(r.status_code, 413)
            self.assertIn("limit is %d" % CM.MAX_INSTRUCTION, r.get_json()["message"])
        finally:
            srv._mode_state._mode = orig


class Delivery(unittest.TestCase):
    """An ACCEPTED build is delivered to the Creations hub, where the page has viewers for video, images and pages."""

    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()
        post = lambda path, body, headers=None: cls.http.post(path, json=body, headers=headers or {})  # noqa: E731
        cls.post = staticmethod(post)
        transport = lambda path, payload: cls.http.post(path, json=payload).get_json()  # noqa: E731
        cls.builder = OrchestratorClient("axis-video_creator", "video_creator.governor", transport=transport)
        cls.reviewer = OrchestratorClient("axis-validator", "validator.governor", transport=transport)
        assert post("/api/bus/register", {"engine": "axis-video_creator", "orchestrator": "video_creator.governor"}, ADMIN).status_code == 200
        assert post("/api/bus/register", {"engine": "axis-validator", "orchestrator": "validator.governor", "qc_reviewer": True}, ADMIN).status_code == 200

    def accepted(self, spec, filename, data):
        path = os.path.join(TMP, filename)
        with open(path, "wb") as f:
            f.write(data)
        oid = self.post("/api/bus/order", {"engine": "axis-video_creator", "to": "video_creator.governor", "spec": spec}, ADMIN).get_json()["order"]["id"]
        self.assertEqual(self.builder.ack(oid)["order"]["state"], "ACKED")
        self.assertEqual(self.builder.built(oid, path)["order"]["state"], "BUILT")
        self.assertEqual(self.reviewer.qc(oid, "pass", [], sha256_file(path))["order"]["state"], "QC_PASSED")
        r = self.post("/api/bus/accept", {"order_id": oid}, ADMIN)
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()

    def test_an_accepted_video_reaches_the_page_byte_for_byte(self):
        got = self.accepted({"title": "Launch teaser video"}, "teaser.mp4", MP4)
        d = got["delivered"]
        self.assertEqual((d["kind"], d["title"]), ("video", "Launch teaser video"))
        listed = self.http.get("/api/creations").get_json()["creations"]
        self.assertTrue(any(c["id"] == d["creation_id"] and c["kind"] == "video" for c in listed))
        item = self.http.get("/api/creations/%s" % d["creation_id"]).get_json()
        name = item["creation"]["files"][0]["name"] if "creation" in item else item["files"][0]["name"]
        f = self.http.get("/api/creations/%s/file/%s" % (d["creation_id"], name))
        self.assertEqual(f.status_code, 200)
        self.assertEqual(f.mimetype, "video/mp4")
        self.assertEqual(f.data, MP4)                                                         # exactly what was built, QC'd and re-hashed
        notes = self.http.get("/api/notifications").get_json()
        self.assertIn("Delivered to Creations: Launch teaser video", json.dumps(notes))

    def test_images_and_pages_are_delivered_too(self):
        png = self.accepted({"make": "Product thumbnail image"}, "thumb.png", PNG)["delivered"]
        page = self.accepted({"prompt": "A glowing blue badge saying NEXXUS"}, "badge.html", b"<!doctype html><html><body><svg></svg></body></html>")["delivered"]
        self.assertEqual((png["kind"], page["kind"]), ("image", "html"))

    def test_an_unnamed_order_is_not_given_a_stand_in_name(self):
        got = self.accepted({"x": 1}, "mystery.mp4", MP4)
        self.assertIn("skipped", got["delivered"])
        self.assertIn("does not say what it is", got["delivered"]["skipped"])
        self.assertEqual(got["order"]["state"], "ACCEPTED")                                   # the acceptance itself is unaffected

    def test_files_the_hub_cannot_hold_are_reported_not_hidden(self):
        wrong = self.accepted({"title": "Broken clip"}, "broken.mp4", b"this is not a video at all, only text bytes")["delivered"]
        self.assertIn("skipped", wrong)
        odd = self.accepted({"title": "Raw data dump"}, "dump.bin", b"\x00" * 100)["delivered"]
        self.assertIn("not allowed", odd["skipped"])
        big = self.accepted({"title": "Huge render"}, "huge.mp4", MP4 + b"\x00" * (26 * 1024 * 1024))["delivered"]
        self.assertIn("too large", big["skipped"])
        self.assertIn("25 MB", big["skipped"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
