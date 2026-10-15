"""test_image_ingest.py - live image ingestion and the image-to-3D pipeline, against a LOCAL image server (no internet needed): the fetch refuses everything unsafe, accepts real images by their own
bytes, scales oversize ones, follows and re-checks redirects; the textured-panel scene compiles with the image's own proportions; the whole route (fetch, file in the Creations hub, bind as texture,
build and self-check) works end to end; and the page carries the Image-to-3D control and the send menu (queue, dry run) wired to real handlers. Run: python test_image_ingest.py"""
import atexit
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TMP = tempfile.mkdtemp(prefix="imgingest_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"), NEXXUS_BUS_LEDGER=os.path.join(TMP, "ledger.jsonl"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "creations"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"),
                  NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"), NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1",
                  NEXXUS_PUBLISH_DIR=os.path.join(TMP, "pub"), NEXXUS_FACTORY_DIR=os.path.join(TMP, "factory"))
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, NEXUS)
import factory_env  # noqa: E402
import image_ingest as II  # noqa: E402
from PIL import Image  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
PAGE = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "render", "babylon_preview.html")


def img(fmt, size=(64, 32), color=(200, 40, 40)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, fmt)
    return b.getvalue()


PNG, JPG, GIF, WEBP = img("PNG"), img("JPEG"), img("GIF"), img("WEBP")
BIG = img("PNG", (3000, 1500))
SERVE = {"/a.png": (200, "image/png", PNG), "/b.jpg": (200, "image/jpeg", JPG), "/c.gif": (200, "image/gif", GIF), "/d.webp": (200, "image/webp", WEBP), "/big.png": (200, "image/png", BIG),
         "/liar.png": (200, "image/png", b"<html>not an image</html>"), "/svg.png": (200, "image/png", b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>'),
         "/broken.png": (200, "image/png", PNG[:40]), "/missing": (404, "text/plain", b"nope"), "/huge": (200, "image/png", PNG + b"\0" * (9 * 1024 * 1024))}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/r1":
            return self._redir("/r2")
        if self.path == "/r2":
            return self._redir("/a.png")
        if self.path in ("/loop",):
            return self._redir("/loop")
        if self.path == "/to-private":
            return self._redir("http://10.0.0.1/a.png")
        code, ctype, body = SERVE.get(self.path, (404, "text/plain", b"nope"))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redir(self, to):
        self.send_response(302)
        self.send_header("Location", to)
        self.send_header("Content-Length", "0")
        self.end_headers()


SERVER = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
atexit.register(SERVER.shutdown)
BASE = "http://127.0.0.1:%d" % SERVER.server_address[1]


class Fetch(unittest.TestCase):
    def get(self, path, **kw):
        return II.fetch(BASE + path, allow_loopback=True, **kw)

    def test_real_images_are_accepted_by_their_own_bytes(self):
        for path, ext in (("/a.png", "png"), ("/b.jpg", "jpg"), ("/c.gif", "gif"), ("/d.webp", "webp")):
            r = self.get(path)
            self.assertEqual((r["ext"], r["width"], r["height"], r["scaled"]), (ext, 64, 32, False), path)
            self.assertEqual([s["step"] for s in r["steps"]], ["resolve", "connect", "download", "verify"])
            self.assertTrue(all(s["ok"] for s in r["steps"]))
        self.assertEqual(self.get("/a.png")["data"], PNG)                                    # the exact bytes, nothing substituted

    def test_what_the_server_claims_does_not_matter(self):
        for path in ("/liar.png", "/svg.png", "/broken.png"):
            with self.assertRaises(II.IngestError, msg=path):
                self.get(path)

    def test_oversize_pixels_are_scaled_and_oversize_files_refused(self):
        r = self.get("/big.png")
        self.assertEqual((r["width"], r["height"], r["scaled"]), (2048, 1024, True))
        with self.assertRaises(II.IngestError) as c:
            self.get("/huge")
        self.assertIn("larger than", str(c.exception))

    def test_redirects_are_followed_rechecked_and_bounded(self):
        r = self.get("/r1")
        self.assertEqual(r["data"], PNG)
        self.assertEqual([s["step"] for s in r["steps"]].count("redirect"), 2)
        with self.assertRaises(II.IngestError) as c:
            self.get("/loop")
        self.assertIn("redirect", str(c.exception))
        with self.assertRaises(II.IngestError) as c:
            self.get("/to-private")                                                         # a redirect into the private network is refused before any connection
        self.assertIn("not a public address", str(c.exception))

    def test_errors_say_why(self):
        with self.assertRaises(II.IngestError) as c:
            self.get("/missing")
        self.assertIn("404", str(c.exception))

    def test_unsafe_addresses_are_refused_without_the_test_switch(self):
        for url in ("http://example.com/a.png", "ftp://example.com/a.png", "file:///etc/passwd", "https://127.0.0.1/a.png", "https://localhost/a.png", "https://[::1]/a.png", "https://10.0.0.5/a.png",
                    "https://192.168.1.1/a.png", "https://169.254.169.254/latest/meta-data", "https://user:pw@example.com/a.png", "", "not a url", BASE + "/a.png"):
            with self.assertRaises(II.IngestError, msg=url):
                II.fetch(url)

    def test_the_loopback_switch_is_off_by_default(self):
        self.assertFalse(II.fetch.__defaults__[0])


class Scene(unittest.TestCase):
    def resolver(self, w=400, h=200):
        data = img("PNG", (w, h))
        return lambda cid: [("image.png", data)] if cid == "cr_x" else None

    def test_a_panel_takes_the_proportions_of_its_image(self):
        s = factory_env.compile_scene({"title": "T", "ground": 20, "objects": [{"shape": "panel", "size": [6], "position": [0, 2, 4], "texture": "cr_x"}]}, self.resolver(400, 200))
        o = s["objects"][0]
        self.assertEqual(o["size"][:2], [6.0, 3.0])
        self.assertTrue(o["texture"].startswith("tex/"))

    def test_textures_must_exist_and_panels_are_fixed(self):
        base = {"title": "T", "ground": 20}
        for obj in ({"shape": "panel", "size": [6], "position": [0, 2, 4], "texture": "cr_missing"}, {"shape": "panel", "size": [6], "position": [0, 2, 4]},
                    {"shape": "panel", "size": [6, 2], "position": [0, 2, 4], "dynamic": True}, {"shape": "panel", "size": [1, 2, 3], "position": [0, 2, 4]}):
            with self.assertRaises(factory_env.EnvError, msg=obj):
                factory_env.compile_scene(dict(base, objects=[obj]), self.resolver())

    def test_build_copies_the_texture_and_check_catches_a_swapped_file(self):
        d, res = tempfile.mkdtemp(dir=TMP), self.resolver()
        cfg = {"title": "T", "ground": 20, "objects": [{"shape": "panel", "size": [4], "position": [0, 1.2, 4], "texture": "cr_x"}]}
        info = factory_env.build(d, cfg, res)
        self.assertEqual(len(info["textures"]), 1)
        self.assertEqual(factory_env.check(d, cfg, res), {"ok": True, "problems": []})
        open(os.path.join(d, "env", info["textures"][0]), "wb").write(b"swapped")
        self.assertFalse(factory_env.check(d, cfg, res)["ok"])
        self.assertIn("texture", " ".join(factory_env.check(d, cfg, res)["problems"]))


class Route(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv
        import python_server as srv  # noqa: E402
        os.environ["NEXXUS_INGEST_ALLOW_LOOPBACK"] = "1"                                  # lets the route reach the local test server; unset in normal use
        cls.http = srv.app.test_client()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("NEXXUS_INGEST_ALLOW_LOOPBACK", None)

    def post(self, body, admin=True):
        return self.http.post("/api/factory/image-to-3d", json=body, headers=ADMIN if admin else {})

    def test_it_needs_the_admin_token(self):
        self.assertEqual(self.post({"url": BASE + "/a.png", "title": "x"}, admin=False).status_code, 401)

    def test_a_real_image_goes_all_the_way_to_a_built_scene(self):
        r = self.post({"url": BASE + "/b.jpg", "title": "Red test card"})
        self.assertEqual(r.status_code, 201, r.get_json())
        d = r.get_json()
        self.assertEqual([s["step"] for s in d["steps"]], ["resolve", "connect", "download", "verify", "save", "texture_bind", "viewport_inject"])
        self.assertTrue(all(s["ok"] for s in d["steps"]))
        self.assertEqual((d["image"]["width"], d["image"]["height"]), (64, 32))
        cr = self.http.get("/api/creations").get_json()["creations"]
        mine = next(c for c in cr if c["id"] == d["creation_id"])
        self.assertEqual(mine["kind"], "image")
        self.assertEqual(mine["title"], "Red test card")
        page = self.http.get(d["preview"])
        self.assertEqual(page.status_code, 200)
        page.close()
        html = self.http.get(d["preview"]).get_data(as_text=True)
        self.assertIn('"shape":"panel"', html)
        tex = self.http.get(d["preview"] + "tex/" + html.split("tex/")[1].split('"')[0])
        self.assertEqual(tex.status_code, 200)
        self.assertEqual(tex.data, JPG)                                                 # the texture is byte-for-byte the fetched image
        tex.close()
        inst = next(i for i in self.http.get("/api/factory/instances?type=spatial_environment").get_json()["instances"] if i["id"] == d["instance"])
        self.assertEqual(inst["state"], "built")
        tel = self.http.get("/api/factory/telemetry").get_json()["telemetry"]
        self.assertEqual(tel[-1]["kind"], "image_to_3d")

    def test_failures_are_reported_and_leave_nothing_behind(self):
        before = len(self.http.get("/api/factory/instances").get_json()["instances"])
        n_cr = len(self.http.get("/api/creations").get_json()["creations"])
        for body in ({"url": BASE + "/liar.png", "title": "x"}, {"url": BASE + "/a.png", "title": ""}, {"url": "", "title": "x"}, {"url": BASE + "/missing", "title": "x"}):
            r = self.post(body)
            self.assertEqual(r.status_code, 400, body)
            self.assertIn("message", r.get_json())
        self.assertEqual(len(self.http.get("/api/factory/instances").get_json()["instances"]), before)
        self.assertEqual(len(self.http.get("/api/creations").get_json()["creations"]), n_cr)

    def test_without_the_test_switch_the_route_refuses_local_addresses(self):
        os.environ.pop("NEXXUS_INGEST_ALLOW_LOOPBACK")
        try:
            r = self.post({"url": BASE + "/a.png", "title": "x"})
            self.assertEqual(r.status_code, 400)
            self.assertIn("https", r.get_json()["message"])
        finally:
            os.environ["NEXXUS_INGEST_ALLOW_LOOPBACK"] = "1"


class PageSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = open(PAGE, encoding="utf-8").read()

    def test_the_send_button_has_three_wired_ways_to_send(self):
        h = self.html
        for needle in ('id="send"', 'id="dspCaret"', 'aria-haspopup="menu"', 'id="dspNow"', 'id="dspLater"', 'id="dspDry"', 'id="dspRun"', 'id="dspClear"', 'role="menu"'):
            self.assertIn(needle, h, needle)
        for needle in ("function dspQueueAdd", "function dspDryRun", "function dspSendQueue", "dispatchCommandAndRenderCard(it.text)", "api/input/queue", "e.altKey", "e.ctrlKey", "stopImmediatePropagation",
                       "localStorage.setItem(DSP_KEY"):
            self.assertIn(needle, h, needle)
        self.assertIn("if (sendBtn) sendBtn.addEventListener('click', handleUserDispatch);", h)      # the plain Send click is untouched

    def test_the_dry_run_never_posts_to_the_dispatch_route(self):
        block = self.html.split("async function dspDryRun()")[1].split("async function dspSendQueue()")[0]
        self.assertNotIn("command-dispatch'", block.replace("/command-dispatch as JSON", ""))
        self.assertNotIn("dispatchCommandAndRenderCard", block)

    def test_the_image_to_3d_control_is_wired_to_the_route_and_the_grid(self):
        h = self.html
        for needle in ("function fxImageTo3d", "api/factory/image-to-3d", "fx.preview = { type: 'spatial_environment'", "if (t.engine === 'spatial_environment') main.appendChild(fxImageTo3d())", "function fxPaintSteps"):
            self.assertIn(needle, h, needle)
        self.assertNotRegex(h.split("function fxImageTo3d")[1].split("function fxPaintSteps")[0], r"https?://[a-z]")        # no pre-filled address

    def test_the_new_blocks_sit_outside_the_window_code_other_suites_inspect(self):
        a, b = self.html.index("// ====== HUB WINDOWS"), self.html.index("// ====== SETTINGS READOUTS")
        self.assertNotIn("DISPATCH CONTROL", self.html[a:b])
        self.assertNotIn("FACTORY (dashboard types)", self.html[a:b])


if __name__ == "__main__":
    unittest.main(verbosity=1)
