"""test_media.py - the graphics effects, live-action footage, audio, and AI generation of axis-video_creator. Run: python test_media.py
Footage is made with ffmpeg itself (a test pattern with a tone); the AI backends are exercised against small fake servers on this machine, so no model is needed."""
import base64
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

WS = tempfile.mkdtemp(prefix="vc_media_")
os.environ["VC_WORKSPACE"] = WS
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import vc_store as store  # noqa: E402

M = store.load_module
R = M("silos/cgi/lib/renderer.py")
ENC = M("silos/composition_final_render/lib/encoder_tool.py")
FFMPEG = ENC.find_ffmpeg()


def px(img):
    return img.tobytes()


class Base(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(WS, ignore_errors=True)
        os.makedirs(WS)


class Effects(Base):
    SCENE = {"background": ["#202830", "#10151a"], "nodes": [
        {"id": "t", "type": "text", "text": "Hello world", "x": 0.5, "y": 0.5, "size": 0.2, "font": "bold", "color": "#ffffff", "depth": 0.0},
        {"id": "b", "type": "rect", "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2, "color": "#e8a33d", "radius": 0.3, "shadow": {"dy": 0.03, "blur": 0.03, "opacity": 0.9}, "depth": 1.0}]}

    def test_each_effect_changes_the_picture_and_only_when_switched_on(self):
        size = (240, 135)
        plain = R.render_frame(self.SCENE, 0, size)
        self.assertEqual(px(R.render_frame(self.SCENE, 0, size)), px(plain))                     # repeatable
        for fx in ({"shadows": True}, {"dof": 0.1}, {"vignette": 0.6}, {"grain": 0.05}, {"bloom": 0.8}):
            self.assertNotEqual(px(R.render_frame(self.SCENE, 0, size, fx=fx)), px(plain), fx)
        glow = dict(self.SCENE, nodes=[dict(self.SCENE["nodes"][0], glow={"color": "#ff0000", "radius": 0.05, "strength": 1.0})])
        self.assertNotEqual(px(R.render_frame(glow, 0, size, fx={"glow": True})), px(R.render_frame(glow, 0, size)))
        self.assertEqual(px(R.render_frame(glow, 0, size)), px(R.render_frame(dict(glow, nodes=[self.SCENE["nodes"][0]]), 0, size)))       # glow ignored without fx
        g1, g2 = R.render_frame(self.SCENE, 3, size, fx={"grain": 0.05}), R.render_frame(self.SCENE, 4, size, fx={"grain": 0.05})
        self.assertNotEqual(px(g1), px(g2))                                                        # fresh grain every frame

    def test_depth_of_field_blurs_only_what_is_away_from_the_focus(self):
        size = (240, 135)
        sharp = R.render_frame(self.SCENE, 0, size)
        dof = R.render_frame(self.SCENE, 0, size, fx={"dof": 0.1})
        box = (24, 13, 96, 40)                                                                     # the far rectangle (depth 1.0, focus 0.5)
        self.assertNotEqual(px(sharp.crop(box)), px(dof.crop(box)))
        text_only = dict(self.SCENE, nodes=[self.SCENE["nodes"][0]])                               # depth 0.0 text
        flat = R.render_frame(text_only, 0, size)
        self.assertNotEqual(px(R.render_frame(text_only, 0, size, fx={"dof": 0.1})), px(flat))     # focus 0.5: the text is 0.5 away from it, so it blurs
        self.assertEqual(px(R.render_frame(dict(text_only, focus=0.0), 0, size, fx={"dof": 0.1})), px(flat))     # focus moved onto the text: it stays sharp

    def test_easing_keyframes_and_typewriter_reveal(self):
        node = {"keys": [{"f": 0, "x": 0.0, "ease": "in"}, {"f": 10, "x": 1.0}]}
        self.assertLess(R.prop_at(node, "x", 5), 0.5)                                              # ease-in starts slow
        self.assertAlmostEqual(R.prop_at({"keys": [{"f": 0, "x": 0, "ease": "in_out"}, {"f": 10, "x": 1}]}, "x", 5), 0.5)
        self.assertGreater(R.prop_at({"keys": [{"f": 0, "x": 0, "ease": "back"}, {"f": 10, "x": 1}]}, "x", 8), 1.0)       # overshoots, then settles
        txt = {"background": ["#000000", "#000000"], "nodes": [{"type": "text", "text": "ABCDEFGH", "x": 0.5, "y": 0.5, "size": 0.2, "color": "#ffffff", "keys": [{"f": 0, "reveal": 0.0}, {"f": 10, "reveal": 1.0}]}]}
        a, b, c = (sum(R.render_frame(txt, f, (200, 100)).convert("L").getdata()) for f in (0, 5, 10))
        self.assertTrue(a < b < c)

    def test_solids_are_shaded_3d_and_rotate(self):
        s = {"background": ["#000000", "#000000"], "nodes": [{"type": "solid3d", "shape": "cube", "x": 0.5, "y": 0.5, "size": 0.2, "rx": 20, "ry": 30, "color": "#ff8800", "keys": [{"f": 0, "ry": 30}, {"f": 10, "ry": 120}]}]}
        a, b = R.render_frame(s, 0, (160, 160)), R.render_frame(s, 10, (160, 160))
        self.assertNotEqual(px(a), px(b))
        shades = {p for p in a.getdata() if p != (0, 0, 0)}
        self.assertGreater(len({p[0] for p in shades}), 2)                                         # several face shades, not one flat colour
        for shape in R.SHAPES:
            R.render_frame(dict(s, nodes=[dict(s["nodes"][0], shape=shape)]), 0, (64, 64))

    def test_transitions_and_motion_blur(self):
        a, b = R.render_frame(self.SCENE, 0, (96, 54)), R.render_frame(dict(self.SCENE, background=["#aa0000", "#aa0000"], nodes=[]), 0, (96, 54))
        for kind in ("crossfade", "dip", "slide", "wipe"):
            self.assertEqual(px(R.transition(a, b, 0.0, kind)), px(a.convert("RGB")), kind)
            self.assertEqual(px(R.transition(a, b, 1.0, kind)), px(b.convert("RGB")), kind)
            self.assertNotEqual(px(R.transition(a, b, 0.5, kind)), px(a.convert("RGB")), kind)
        with self.assertRaises(ValueError):
            R.transition(a, b, 0.5, "spin")
        pipe = M("silos/cgi/lib/render_pipeline_utility_tool.py").render_pipeline_utility_tool(dict(M("silos/cgi/config/render_pipeline_utility_config.py").render_pipeline_utility_config))
        moving = {"background": ["#000000", "#000000"], "nodes": [{"type": "rect", "x": 0.1, "y": 0.4, "w": 0.1, "h": 0.2, "color": "#ffffff", "keys": [{"f": 0, "x": 0.1}, {"f": 1, "x": 0.8}]}]}
        pipe.update_quality_settings("high")
        sharp = pipe.render_frame(moving, 0.5, (160, 90))
        pipe.update_quality_settings("production")
        self.assertEqual(pipe.pipeline["samples"], 4)
        blur = pipe.render_frame(moving, 0.5, (160, 90))
        self.assertNotEqual(px(sharp), px(blur))
        self.assertGreater(len({p for p in blur.convert("L").crop((20, 36, 140, 54)).getdata()}), len({p for p in sharp.convert("L").crop((20, 36, 140, 54)).getdata()}) - 40)
        off = M("silos/cgi/lib/render_pipeline_utility_tool.py").render_pipeline_utility_tool(dict(M("silos/cgi/config/render_pipeline_utility_config.py").render_pipeline_utility_config, motion_blur=False, depth_of_field=False))
        self.assertEqual(off.update_quality_settings("production")["samples"], 1)                    # the config switches really switch it off
        self.assertNotIn("dof", off.pipeline["fx"])

    def test_fonts_are_real_and_a_missing_family_falls_back(self):
        f = R.get_font("bold", 40)
        self.assertGreater(f.getlength("Wide text"), R.get_font("sans", 20).getlength("Wide text"))
        self.assertTrue(R.get_font("no-such-family", 20).getlength("x") > 0)
        self.assertEqual(R._wrap("one two three four", R.get_font("sans", 30), 1000), "one two three four")
        self.assertIn("\n", R._wrap("one two three four five six seven", R.get_font("sans", 30), 150))

    def test_the_assembler_makes_rich_scenes_without_repeating_the_title(self):
        nar = M("silos/vision_narrative_architect/lib/schema_builder.py").build_narrative_schema("Steel matters. It resists rust. Choose steel.")
        tim = M("silos/storyboard_timing_precision_engine/lib/rhythm_calc.py").calculate_beat_alignment(nar["beats"], 24)
        style = M("silos/character_style_forge/lib/style_tool.py").apply_aesthetic("rugged_steel")["style"]
        plan = M("silos/blueprint_compiler/lib/assembler_tool.py").build_final_blueprint({"narrative": nar, "timing": tim, "style": style, "resolution": "360p", "transition": "slide"}, "cinema")
        self.assertEqual(plan["quality"], "production")
        ids = [[n["id"] for n in s["nodes"]] for s in plan["scenes"]]
        self.assertIn("cube", ids[0])
        self.assertNotIn("title", ids[0])                                                          # the title is the first sentence: shown once
        self.assertEqual(plan["scenes"][1]["transition"]["type"], "slide")
        self.assertNotIn("transition", plan["scenes"][0])
        nar2 = dict(nar, title="Why steel lasts")
        plan2 = M("silos/blueprint_compiler/lib/assembler_tool.py").build_final_blueprint({"narrative": nar2, "timing": tim, "style": style}, "draft")
        self.assertIn("title", [n["id"] for n in plan2["scenes"][0]["nodes"]])
        with self.assertRaises(ValueError):
            M("silos/blueprint_compiler/lib/assembler_tool.py").build_final_blueprint({"narrative": nar, "timing": tim, "style": style, "transition": "spin"}, "draft")


@unittest.skipUnless(FFMPEG, "ffmpeg is not available")
class Footage(Base):
    def _clip(self, name="clip.mp4", seconds=3, audio=True):
        path = os.path.join(WS, name)
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=%d" % seconds]
        if audio:
            cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=%d" % seconds, "-c:a", "aac"]
        subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True, capture_output=True)
        return path

    def test_probe_reads_a_real_clip_and_refuses_bad_files(self):
        t = M("silos/asset_generation_library/lib/footage_tool.py")
        info = t.probe(self._clip())
        self.assertEqual((info["width"], info["height"], info["has_audio"]), (320, 240, True))
        self.assertAlmostEqual(info["duration_s"], 3.0, delta=0.2)
        self.assertFalse(t.probe(self._clip("mute.mp4", audio=False))["has_audio"])
        bad = os.path.join(WS, "notvideo.mp4")
        open(bad, "wb").write(b"this is not a video")
        for p in (bad, os.path.join(WS, "missing.mp4"), os.path.join(WS, "x.txt")):
            open(p, "ab").close() if p.endswith(".txt") else None
            with self.assertRaises(t.FootageError):
                t.probe(p)

    def test_ingest_cuts_frames_at_the_project_rate_and_size(self):
        t = M("silos/asset_generation_library/lib/footage_tool.py")
        out = t.ingest(self._clip(), os.path.join(WS, "f"), 12, (160, 90), 0.5, 2.0)
        self.assertEqual((out["count"], out["size"], out["has_audio"]), (24, [160, 90], True))
        from PIL import Image
        with Image.open(os.path.join(out["dir"], "f_00000.jpg")) as im:
            self.assertEqual(im.size, (160, 90))
        self.assertEqual(len(out["source_sha256"]), 64)
        again = t.ingest(self._clip(), os.path.join(WS, "f"), 12, (160, 90), 0.5, 1.0)             # re-running replaces, never mixes
        self.assertEqual(again["count"], 12)
        self.assertEqual(len(os.listdir(out["dir"])), 12)
        with self.assertRaises(t.FootageError):
            t.ingest(self._clip(), os.path.join(WS, "g"), 12, (160, 90), 99.0)
        self.assertGreater(t.extract_audio(self._clip(), os.path.join(WS, "a.m4a"), 0, 2)["bytes"], 0)
        with self.assertRaises(t.FootageError):
            t.extract_audio(self._clip("mute.mp4", audio=False), os.path.join(WS, "b.m4a"))

    def test_a_full_build_with_footage_under_a_beat_and_its_sound_in_the_mp4(self):
        clip = self._clip(seconds=4)
        b = M("src/integration_office/master_builder/lib/builder_tool.py")
        r = b.orchestrate_silos({"project_id": "live", "script": "Opening line here. This part is real footage. Closing line now.", "resolution": "240p", "environment": "staging",
                                 "fps": 12, "codec": "h264", "footage": [{"path": clip, "scene": 2}], "audio": "footage"})
        self.assertEqual(r["status"], "build_complete", r)
        self.assertTrue(r["video"].endswith(".mp4"))
        info = subprocess.run([FFMPEG, "-hide_banner", "-i", r["video"]], capture_output=True, text=True).stderr
        self.assertIn("Video: h264", info)
        self.assertIn("Audio: aac", info)
        st = store.read_json(os.path.join(WS, "projects", "live", "state.json"))
        self.assertTrue(st["stages"]["final_render"]["encoding"]["audio"])
        plan = store.read_json(st["stages"]["blueprint_compiler"]["artifacts"]["blueprint"]["path"])
        self.assertIn("footage", [n["id"] for n in plan["scenes"][1]["nodes"]])
        self.assertNotIn("footage", [n["id"] for n in plan["scenes"][0]["nodes"]])
        audit = M("src/quality_control/inspector/lib/inspector_tool.py").run_audit("live", True, "v")
        self.assertEqual(audit["issues"], [])
        bad = b.orchestrate_silos({"project_id": "live2", "script": "One. Two.", "resolution": "240p", "environment": "draft", "fps": 12, "codec": "gif", "footage": [{"path": clip, "scene": 9}]})
        self.assertEqual(bad["status"], "build_failed")
        self.assertIn("footage failed", bad["error"])

    def test_gif_output_says_it_cannot_carry_sound(self):
        from PIL import Image
        d = os.path.join(WS, "fr")
        os.makedirs(d)
        for i in range(3):
            Image.new("RGB", (32, 18), (i * 50, 0, 0)).save(os.path.join(d, "frame_%05d.png" % i))
        audio = os.path.join(WS, "t.m4a")
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", "-c:a", "aac", audio], check=True)
        out = ENC.compress_stream("gif", d, os.path.join(WS, "o.gif"), 12, audio=audio)
        self.assertFalse(out["audio"])
        self.assertIn("cannot carry sound", out["note"])
        mp4 = ENC.compress_stream("h264", d, os.path.join(WS, "o.mp4"), 12, audio=audio)
        self.assertTrue(mp4["audio"])
        self.assertEqual(mp4["codec"], "h264")
        with self.assertRaises(FileNotFoundError):
            ENC.compress_stream("h264", d, os.path.join(WS, "p.mp4"), 12, audio=os.path.join(WS, "none.m4a"))


class _FakeServices(http.server.BaseHTTPRequestHandler):
    """Stands in for Ollama (/api/tags, /api/generate) and a Stable Diffusion web UI (/sdapi/v1/*) on this machine."""
    calls = []
    script = "Steel resists rust. It recycles forever. Choose steel."

    def log_message(self, *a):
        pass

    def _send(self, obj):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_GET(self):
        if self.path == "/api/tags":
            return self._send({"models": [{"name": "fakemodel:latest"}]})
        if self.path == "/sdapi/v1/options":
            return self._send({})
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        _FakeServices.calls.append((self.path, body))
        if self.path == "/api/generate":
            return self._send({"response": _FakeServices.script})
        if self.path == "/sdapi/v1/txt2img":
            from PIL import Image
            buf = io.BytesIO()
            Image.new("RGB", (body["width"], body["height"]), (body["seed"] * 40 % 255, 90, 160)).save(buf, "PNG")
            return self._send({"images": [base64.b64encode(buf.getvalue()).decode()]})
        self.send_response(404)
        self.end_headers()


class AI(Base):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), _FakeServices)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d" % cls.srv.server_port

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        super().setUp()
        _FakeServices.calls.clear()
        _FakeServices.script = "Steel resists rust. It recycles forever. Choose steel."
        self._env = {k: os.environ.get(k) for k in ("VC_OLLAMA_URL", "VC_A1111_URL", "VC_OLLAMA_MODEL")}

    def tearDown(self):
        for k, v in self._env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def _up(self):
        os.environ["VC_OLLAMA_URL"] = os.environ["VC_A1111_URL"] = self.url

    def _down(self):
        os.environ["VC_OLLAMA_URL"] = os.environ["VC_A1111_URL"] = "http://127.0.0.1:9"

    def test_status_reports_what_is_and_is_not_there(self):
        b = M("silos/asset_generation_library/lib/ai_backends.py")
        self._down()
        st = b.status()
        self.assertEqual((st["text"], st["images"] or st["diffusers"]["available"]), (False, False))
        self.assertIn("no Ollama server", st["ollama"]["why"])
        self._up()
        st = b.status()
        self.assertEqual((st["text"], st["automatic1111"]["available"], st["ollama"]["models"]), (True, True, ["fakemodel:latest"]))

    def test_images_come_from_the_local_server_with_provenance_and_sizes_rounded(self):
        b = M("silos/asset_generation_library/lib/ai_backends.py")
        self._up()
        out = b.generate_image("a steel bridge at dawn", 515, 291, seed=2, backend="automatic1111")
        self.assertEqual((out["width"], out["height"], out["backend"], out["ai_generated"]), (512, 288, "automatic1111", True))
        prov = json.load(open(out["path"] + ".provenance.json"))
        self.assertEqual((prov["prompt"], prov["seed"], prov["sha256"]), ("a steel bridge at dawn", 2, out["sha256"]))
        self.assertEqual(store.sha256_file(out["path"]), out["sha256"])
        self.assertEqual(_FakeServices.calls[0][1]["width"], 512)
        with self.assertRaises(ValueError):
            b.generate_image("  ")
        with self.assertRaises(ValueError):
            b.generate_image("x", backend="midjourney")

    def test_no_backend_means_a_clear_refusal_never_a_fake_image(self):
        b = M("silos/asset_generation_library/lib/ai_backends.py")
        self._down()
        for call in (lambda: b.generate_image("a bridge", backend="automatic1111"), lambda: b.generate_text("hi")):
            with self.assertRaises(b.AIUnavailable):
                call()
        self.assertFalse(os.path.isdir(store.resolve("assets/ai")) and os.listdir(store.resolve("assets/ai")))
        os.environ["VC_A1111_URL"] = "http://example.com:7860"
        with self.assertRaises(b.AIUnavailable) as cm:
            b.generate_image("x", backend="automatic1111")
        self.assertIn("not this machine", str(cm.exception))

    def test_script_writing_is_checked_and_retried(self):
        b = M("silos/asset_generation_library/lib/ai_backends.py")
        self._up()
        r = b.write_script("why steel lasts", ["rust"], None, 3)
        self.assertEqual((r["script"], r["attempts"], r["ai_generated"], r["model"]), ("Steel resists rust. It recycles forever. Choose steel.", 1, True, "fakemodel:latest"))
        self.assertIn("exactly 3 short sentences", _FakeServices.calls[0][1]["prompt"])
        _FakeServices.script = "# Title\n- one\n- two"
        with self.assertRaises(b.AIUnavailable):
            b.write_script("x", None, None, 3)
        self.assertEqual(len([c for c in _FakeServices.calls if c[0] == "/api/generate"]), 4)       # 1 earlier + 3 failed tries
        os.environ["VC_OLLAMA_MODEL"] = "ghost"
        with self.assertRaises(b.AIUnavailable):
            b.write_script("x", None, None, 3)

    def test_a_build_with_an_ai_written_script_and_ai_stills(self):
        self._up()
        b = M("src/integration_office/master_builder/lib/builder_tool.py")
        r = b.orchestrate_silos({"project_id": "ai1", "topic": "why steel lasts", "ai": {"script": True, "images": True, "sentences": 3}, "resolution": "240p", "environment": "draft",
                                 "fps": 12, "codec": "gif"})
        self.assertEqual(r["status"], "build_complete", r)
        st = store.read_json(os.path.join(WS, "projects", "ai1", "state.json"))
        brief = store.read_json(st["stages"]["interview"]["artifacts"]["brief"]["path"])
        self.assertEqual((brief["script_source"], brief["ai_generated"]), ("ai:fakemodel:latest", True))
        imgs = store.read_json(st["stages"]["ai_assets"]["artifacts"]["ai_images"]["path"])["images"]
        self.assertEqual(sorted(imgs), ["1", "2", "3"])
        plan = store.read_json(st["stages"]["blueprint_compiler"]["artifacts"]["blueprint"]["path"])
        self.assertTrue(all("ai_image" in [n["id"] for n in s["nodes"]] for s in plan["scenes"]))
        self.assertEqual(M("src/quality_control/inspector/lib/inspector_tool.py").run_audit("ai1", True, "v")["issues"], [])

    def test_missing_image_models_skip_honestly_unless_the_order_requires_them(self):
        self._down()
        b = M("src/integration_office/master_builder/lib/builder_tool.py")
        order = {"project_id": "noai", "script": "One short line. Another short line.", "ai": {"images": True}, "resolution": "240p", "environment": "draft", "fps": 12, "codec": "gif"}
        r = b.orchestrate_silos(order)
        self.assertEqual(r["status"], "build_complete", r)
        st = store.read_json(os.path.join(WS, "projects", "noai", "state.json"))
        self.assertIn("not available", st["stages"]["ai_assets"]["skipped_because"])
        plan = store.read_json(st["stages"]["blueprint_compiler"]["artifacts"]["blueprint"]["path"])
        self.assertFalse(any("ai_image" in [n["id"] for n in s["nodes"]] for s in plan["scenes"]))          # no image was invented
        hard = b.orchestrate_silos(dict(order, project_id="noai2", ai={"images": True, "required": True}))
        self.assertEqual(hard["status"], "build_failed")
        self.assertIn("ai_assets failed", hard["error"])


if __name__ == "__main__":
    unittest.main(verbosity=1, warnings="ignore")
