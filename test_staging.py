"""test_staging.py - the 3D staging toolkit: the image tools on pictures built here (so the right answer is known), the working-copy sessions (undo, reset, depth, history), the server routes (admin
token, errors, the original never touched), vault sync (the result is a NEW linked version with its edits recorded and its depth map), and the page wiring (thumbnail click, toolkit, touch-safe
marking). Throwaway token and folders; nothing calls a model. Run: python test_staging.py"""
import atexit
import io
import os
import shutil
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="staging_")
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
import image_tools as T  # noqa: E402
import stage_sessions as SS  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
PAGE = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "render", "babylon_preview.html")


def planet_png(w=300, h=200, border=8):
    """A blue disc on black, inside a white border: the correct answer to every tool is known."""
    im = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([border, border, w - border - 1, h - border - 1], fill=(0, 0, 0))
    d.ellipse([90, 40, 210, 160], fill=(40, 120, 220))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def alpha_of(png):
    return Image.open(io.BytesIO(png)).convert("RGBA").getchannel("A")


class Tools(unittest.TestCase):
    def setUp(self):
        self.a = T.load(planet_png())

    def test_trim_removes_exactly_the_measured_border(self):
        out, r = T.trim(self.a, {})
        self.assertEqual(out.shape[:2], (184, 284))
        self.assertEqual(r["removed_px"], {"left": 8, "top": 8, "right": 8, "bottom": 8})
        tight, r2 = T.trim(out, {"tolerance": 5})                                         # the black frame is now the border, and goes too
        self.assertEqual(r2["measured_from"], "the border colour rgb(0, 0, 0)")
        self.assertLess(tight.shape[0], out.shape[0])
        with self.assertRaises(T.ToolError):
            T.trim(tight, {"tolerance": 5})                                              # nothing uniform left to trim

    def test_background_removal_clears_the_edge_connected_background_and_keeps_the_subject(self):
        t, _ = T.trim(self.a, {})
        out, r = T.background(t, {"tolerance": 10})
        h, w = out.shape[:2]
        self.assertEqual((out[0, 0, 3], out[h // 2, w // 2, 3]), (0, 255))
        self.assertEqual(r["background_colour"], [0, 0, 0])
        self.assertAlmostEqual(r["cleared_pct"], 78.0, delta=0.5)
        self.assertEqual(out[h // 2, w // 2, :3].tolist(), [40, 120, 220])                # the subject's pixels are unchanged

    def test_the_wand_keeps_or_removes_what_was_clicked(self):
        t, _ = T.trim(self.a, {})
        keep, rk = T.select(t, {"point": [0.5, 0.5], "mode": "keep", "tolerance": 10})
        rem, rr = T.select(t, {"point": [0.02, 0.02], "mode": "remove", "tolerance": 10})
        self.assertEqual(int((keep[..., 3] > 8).sum()), int((rem[..., 3] > 8).sum()))      # the same subject either way
        self.assertEqual(rk["seed_colour"], [40, 120, 220])
        with self.assertRaises(T.ToolError):
            T.select(t, {"point": [0.5, 0.5], "mode": "bogus"})

    def test_crop_lasso_and_alpha(self):
        t, _ = T.trim(self.a, {})
        c, r = T.crop(t, {"box": [0.25, 0.25, 0.75, 0.75]})
        self.assertEqual((r["from"], r["to"]), ([284, 184], [142, 92]))
        l, rl = T.lasso(t, {"points": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]], "mode": "keep", "feather": 0})
        self.assertAlmostEqual(rl["visible_after_px"] / (284 * 184), 0.36, delta=0.02)    # a 60% x 60% box
        b, _ = T.background(t, {"tolerance": 10})
        hard, _ = T.alpha(b, {"action": "threshold", "level": 128})
        self.assertTrue(set(hard[..., 3].flatten().tolist()) <= {0, 255})
        inv, _ = T.alpha(b, {"action": "invert"})
        self.assertEqual(int(inv[0, 0, 3]), 255)

    def test_clean_keeps_only_the_biggest_piece(self):
        b, _ = T.background(T.trim(self.a, {})[0], {"tolerance": 10})
        b[5:9, 5:9, 3] = 255                                                               # a speck
        out, _ = T.alpha(b, {"action": "clean"})
        self.assertEqual(int(out[6, 6, 3]), 0)
        self.assertEqual(int(out[out.shape[0] // 2, out.shape[1] // 2, 3]), 255)

    def test_depth_is_a_dome_inside_the_silhouette_and_says_what_it_is(self):
        b, _ = T.background(T.trim(self.a, {})[0], {"tolerance": 10})
        z, r = T.depth(b, {"method": "silhouette"})
        h, w = z.shape
        self.assertEqual(int(z[0, 0]), 0)
        self.assertGreater(int(z[h // 2, w // 2]), 240)                                    # highest at the centre
        self.assertGreater(int(z[h // 2, w // 2]), int(z[h // 2, w // 2 - 40]))
        self.assertIn("silhouette", r["note"])
        _, r2 = T.depth(self.a, {"method": "luminance"})
        self.assertIn("not measured depth", r2["note"])
        _, r3 = T.depth(self.a, {"method": "silhouette"})
        self.assertIn("isolate the subject first", r3["note"])                             # an opaque picture is called out, not dressed up

    def test_bad_input_is_refused_with_a_reason(self):
        for fn, p in ((T.crop, {"box": [0, 0, 0, 1]}), (T.crop, {"box": [0.1, 0.1, 0.12, 0.12]}), (T.crop, {}), (T.select, {"point": [2, 2]}), (T.select, {"point": "x"}), (T.lasso, {"points": [[0, 0]]}),
                      (T.lasso, {"points": [[0, 0], [0, 0], [0, 0]]}), (T.alpha, {"action": "x"}), (T.trim, {"tolerance": "a"}), (T.trim, {"tolerance": 500}), (T.depth, {"method": "ai"}),
                      (T.background, {"tolerance": 100})):
            with self.assertRaises(T.ToolError, msg=(fn.__name__, p)):
                fn(self.a, p)
        with self.assertRaises(T.ToolError):
            T.load(b"not an image")


class Sessions(unittest.TestCase):
    def setUp(self):
        self.st = SS.Stager()
        self.meta = {"id": "cr_x_20260101_000000", "title": "Planet test", "prompt": None, "version": 1}

    def test_apply_undo_reset_and_the_picture_changes_each_time(self):
        s = self.st.open(self.meta, planet_png())
        v0 = s.version
        self.st.apply(s.id, "trim", {})
        self.st.apply(s.id, "background", {"tolerance": 10})
        self.assertEqual(s.state()["edits"], 2)
        self.assertGreater(s.version, v0)
        self.st.undo(s.id)
        self.assertEqual(s.state()["edits"], 1)
        self.st.reset(s.id)
        self.assertEqual((s.state()["edits"], s.history[-1]), (0, planet_png()))
        with self.assertRaises(SS.StageError):
            self.st.undo(s.id)

    def test_a_depth_map_is_dropped_when_the_picture_changes_under_it(self):
        s = self.st.open(self.meta, planet_png())
        self.st.apply(s.id, "background", {"tolerance": 10})
        self.st.apply(s.id, "depth", {"method": "silhouette"})
        self.assertTrue(s.state()["has_depth"])
        self.st.apply(s.id, "crop", {"box": [0, 0, 0.5, 0.5]})
        self.assertFalse(s.state()["has_depth"])

    def test_errors_do_not_change_the_working_copy(self):
        s = self.st.open(self.meta, planet_png())
        before = s.history[-1]
        for tool, p in (("crop", {"box": [0, 0, 0, 0]}), ("nope", {}), ("select", {"point": [9, 9]})):
            with self.assertRaises(SS.StageError):
                self.st.apply(s.id, tool, p)
        self.assertEqual((s.history[-1], s.state()["edits"]), (before, 0))

    def test_history_and_session_counts_are_bounded(self):
        s = self.st.open(self.meta, planet_png())
        for _ in range(SS.MAX_HISTORY + 5):
            self.st.apply(s.id, "alpha", {"action": "invert"})
        self.assertLessEqual(len(s.history), SS.MAX_HISTORY + 1)
        self.assertLessEqual(len(s.ops), SS.MAX_HISTORY)
        for _ in range(SS.MAX_SESSIONS + 3):
            self.st.open(self.meta, planet_png())
        self.assertLessEqual(len(self.st._s), SS.MAX_SESSIONS)

    def test_sessions_expire(self):
        clock = [1000.0]
        st = SS.Stager(now=lambda: clock[0])
        s = st.open(self.meta, planet_png())
        clock[0] += SS.TTL + 5
        st.open(self.meta, planet_png())                                                  # opening sweeps the expired one
        with self.assertRaises(SS.StageError):
            st.image(s.id)


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv
        import python_server as srv  # noqa: E402
        cls.http = srv.app.test_client()
        r = cls.http.post("/api/creations", json={"title": "Planet test picture", "files": [{"name": "planet.png", "data_b64": __import__("base64").b64encode(planet_png()).decode()}], "source": "upload"}, headers=ADMIN)
        assert r.status_code in (200, 201), r.get_json()
        cls.cid = r.get_json()["creation"]["id"] if "creation" in r.get_json() else r.get_json()["id"]

    def post(self, path, body=None, admin=True):
        return self.http.post(path, json=body or {}, headers=ADMIN if admin else {})

    def open(self):
        r = self.post("/api/stage/open", {"creation_id": self.cid})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()

    def test_everything_that_changes_needs_the_admin_token(self):
        self.assertEqual(self.post("/api/stage/open", {"creation_id": self.cid}, admin=False).status_code, 401)
        s = self.open()
        for act in ("apply", "undo", "reset", "finalize", "close"):
            self.assertEqual(self.post("/api/stage/%s/%s" % (s["session"], act), {}, admin=False).status_code, 401, act)

    def test_open_apply_and_the_picture_is_served_back(self):
        s = self.open()
        self.assertEqual((s["width"], s["height"], s["edits"]), (300, 200, 0))
        r = self.post("/api/stage/%s/apply" % s["session"], {"tool": "trim", "params": {}})
        self.assertEqual(r.status_code, 200, r.get_json())
        d = r.get_json()
        self.assertEqual((d["width"], d["height"], d["edits"]), (284, 184, 1))
        pic = self.http.get(d["image_url"])
        self.assertEqual((pic.status_code, pic.mimetype), (200, "image/png"))
        self.assertEqual(Image.open(io.BytesIO(pic.data)).size, (284, 184))
        self.assertIn("no-store", pic.headers["Cache-Control"])
        self.assertEqual(self.http.get("/api/stage/%s/depth" % s["session"]).status_code, 404)           # none made yet

    def test_errors_are_400_with_a_reason_and_unknown_things_404(self):
        s = self.open()
        r = self.post("/api/stage/%s/apply" % s["session"], {"tool": "crop", "params": {"box": [0, 0, 0, 0]}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("crop", r.get_json()["message"])
        self.assertEqual(self.post("/api/stage/st-000000000000/apply", {"tool": "trim"}).status_code, 400)
        self.assertEqual(self.post("/api/stage/open", {"creation_id": "nope"}).status_code, 400)
        self.assertEqual(self.post("/api/stage/%s/explode" % s["session"]).status_code, 404)
        self.assertEqual(self.http.get("/api/stage/../etc/image").status_code, 404)

    def test_only_pictures_can_be_staged(self):
        r = self.http.post("/api/creations", json={"title": "A page about planets", "files": [{"name": "index.html", "data_b64": __import__("base64").b64encode(b"<!doctype html><title>p</title><p>planets</p>").decode()}], "source": "upload"}, headers=ADMIN)
        page_id = r.get_json().get("creation", r.get_json())["id"]
        self.assertEqual(self.post("/api/stage/open", {"creation_id": page_id}).status_code, 400)

    def test_finalize_files_a_new_linked_version_and_leaves_the_original(self):
        orig = self.http.get("/api/creations/%s" % self.cid).get_json()
        s = self.open()
        self.assertEqual(self.post("/api/stage/%s/finalize" % s["session"]).status_code, 400)           # nothing changed: nothing to sync
        for tool, p in (("trim", {}), ("background", {"tolerance": 10}), ("depth", {"method": "silhouette"})):
            r = self.post("/api/stage/%s/apply" % s["session"], {"tool": tool, "params": p})
            self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIsNotNone(r.get_json()["depth_url"])
        depth = self.http.get(r.get_json()["depth_url"])
        self.assertEqual(depth.status_code, 200)
        self.assertEqual(Image.open(io.BytesIO(depth.data)).mode, "L")
        f = self.post("/api/stage/%s/finalize" % s["session"])
        self.assertEqual(f.status_code, 200, f.get_json())
        new = f.get_json()["creation"]
        self.assertEqual((new["parent_id"], new["version"], new["source"]), (self.cid, 2, "staging"))
        self.assertIn("trim", new["instruction"])
        self.assertIn("background", new["instruction"])
        names = [x["name"] for x in new["files"]]
        self.assertEqual(len(names), 2, names)
        png = next(x for x in new["files"] if "depth" not in x["name"])
        self.http.get("/api/creations/%s/file/%s" % (new["id"], png["name"]))
        saved = self.http.get("/api/creations/%s/file/%s" % (new["id"], png["name"])).data
        a = alpha_of(saved)
        self.assertEqual((a.getpixel((0, 0)), a.getpixel((a.width // 2, a.height // 2))), (0, 255))      # transparent background, opaque subject
        self.assertEqual(self.http.get("/api/creations/%s" % self.cid).get_json(), orig)                  # the original is untouched
        self.assertEqual(self.post("/api/stage/%s/apply" % s["session"], {"tool": "trim"}).status_code, 400)   # the session is closed after syncing
        listed = {c["id"] for c in self.http.get("/api/creations").get_json()["creations"]}
        self.assertIn(new["id"], listed)                                                                  # it is in the vault for the rest of the pipeline


class PageSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = open(PAGE, encoding="utf-8").read()

    def test_a_picture_thumbnail_opens_the_staging_view(self):
        h = self.html
        self.assertIn("box.addEventListener('click', e => { e.stopPropagation(); stageOpen(m.id); })", h)
        self.assertIn("view.addEventListener('click', () => stageOpen(m.id))", h)
        self.assertIn("p.type !== 'image/svg+xml'", h)                                                   # svg pictures are not raster-edited

    def test_the_toolkit_is_wired_to_the_server_and_marks_use_pointer_events(self):
        h = self.html
        for tool in ("'trim'", "'background'", "'select'", "'lasso'", "'crop'", "'alpha'", "'depth'"):
            self.assertIn("stgApply(" + tool, h, tool)
        for needle in ("api/stage/open", "api/stage/${stg.s.session}/${action}", "api/stage/${stg.s.session}/finalize", "ArcRotateCamera", "getTextureCoordinates", "pointerdown", "setPointerCapture",
                       "touch-action: none", "multiTouchPanAndZoom", "Finalize and sync to vault", "Discard edits?", "refreshCreations(); openCreationsDrawer(id)"):
            self.assertIn(needle, h, needle)
        self.assertNotIn("mousedown", h.split("function stgBuild")[1].split("// ====== END 3D STAGING VIEW")[0])    # touch works because nothing here depends on mouse-only events

    def test_it_sits_outside_the_window_code_other_suites_inspect(self):
        a, b = self.html.index("// ====== HUB WINDOWS"), self.html.index("// ====== SETTINGS READOUTS")
        self.assertNotIn("3D STAGING VIEW", self.html[a:b])


if __name__ == "__main__":
    unittest.main(verbosity=1)
