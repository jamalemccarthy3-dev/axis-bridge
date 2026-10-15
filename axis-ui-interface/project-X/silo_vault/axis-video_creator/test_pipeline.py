"""test_pipeline.py - axis-video_creator really makes a video, and every silo behind it does real work. Run: python test_pipeline.py
Uses a temporary workspace (VC_WORKSPACE), so nothing in your real workspace/ is touched."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings

warnings.simplefilter("ignore", ResourceWarning)
WS = tempfile.mkdtemp(prefix="vc_ws_")
os.environ["VC_WORKSPACE"] = WS
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import vc_store as store  # noqa: E402

M = store.load_module
SCRIPT = "Here is what matters about steel. Narrator: It resists rust. Choose steel."
ORDER = {"script": SCRIPT, "resolution": "240p", "environment": "draft", "fps": 12, "codec": "gif"}


def builder():
    return M("src/integration_office/master_builder/lib/builder_tool.py")


class Base(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(WS, ignore_errors=True)
        os.makedirs(WS)


class Interview(Base):
    def test_input_is_cleaned_bounded_and_typed(self):
        t = M("silos/active_interview/lib/input_tool.py")
        r = t.process_raw_input("  hello\x00   world  ", 8)
        self.assertEqual((r["text"], r["truncated"], r["length"]), ("hello wo", True, 8))
        with self.assertRaises(TypeError):
            t.process_raw_input(5, 10)

    def test_the_session_persists_and_the_interview_asks_for_what_is_missing(self):
        ctx, syn = M("silos/active_interview/lib/context_tool.py"), M("silos/active_interview/lib/synthesizer_tool.py")
        s = ctx.update_session_state({"topic": "Why steel lasts"}, "s1")
        self.assertEqual(s["turns"], 1)
        r = syn.generate_response(s, "professional_hardened")
        self.assertEqual((r["status"], r["missing"], r["next_question"]["fact"]), ("needs_more_input", ["key_points"], "audience"))
        s = ctx.update_session_state({"key_points": ["it resists rust"]}, "s1")
        s = ctx.update_session_state({"key_points": ["it resists rust", "it recycles"], "call_to_action": "Choose steel"}, "s1")
        self.assertEqual(s["facts"]["key_points"], ["it resists rust", "it recycles"])          # lists merge without duplicates
        r = syn.generate_response(s, "professional_hardened")
        self.assertEqual(r["status"], "response_generated")
        self.assertIn("Choose steel.", r["brief"]["script"])
        self.assertNotIn("audience", r["brief"]["script"])                                       # nothing is invented
        with self.assertRaises(ValueError):
            ctx.update_session_state({}, "../escape")


class Narrative(Base):
    def test_schema_finds_characters_and_validator_names_problems(self):
        sb, v = M("silos/vision_narrative_architect/lib/schema_builder.py"), M("silos/vision_narrative_architect/lib/validator.py")
        s = sb.build_narrative_schema(SCRIPT)
        self.assertEqual((s["status"], s["characters"], [b["kind"] for b in s["beats"]]), ("pristine", ["Narrator"], ["hook", "body", "close"]))
        self.assertTrue(v.validate_blueprint(s))
        bad = json.loads(json.dumps(s))
        bad["beats"][1]["n"] = 7
        bad["beats"][2]["speaker"] = "Ghost"
        del bad["title"]
        p = " | ".join(v.problems(bad))
        for needle in ("missing key 'title'", "numbered 7", "Ghost"):
            self.assertIn(needle, p)
        self.assertFalse(v.validate_blueprint(bad))


class Timing(Base):
    def test_frames_never_drift_and_bad_beats_are_reported(self):
        rc = M("silos/storyboard_timing_precision_engine/lib/rhythm_calc.py")
        beats = [{"n": i, "duration_s": 1.51} for i in range(1, 41)]
        r = rc.calculate_beat_alignment(beats, 24)
        self.assertTrue(r["is_synced"])
        self.assertEqual(r["total_duration"], round(40 * 1.51 * 24))                  # rounded from the cumulative time: no build-up of error
        self.assertLessEqual(r["max_boundary_error_frames"], 0.5)
        self.assertEqual([b["start_frame"] for b in r["beats"][1:3]], [r["beats"][0]["end_frame"], r["beats"][1]["end_frame"]])
        bad = rc.calculate_beat_alignment([{"n": 1, "duration_s": 0.01}, {"n": 2, "duration_s": 0}], 24)
        self.assertFalse(bad["is_synced"])
        self.assertEqual(bad["alignment_status"], "mismatch")
        self.assertFalse(rc.calculate_beat_alignment([], 24)["is_synced"])


class Vault(Base):
    def test_vault_stores_once_searches_and_has_a_capacity(self):
        t = M("silos/concept_vault/lib/vault_tool.py")
        f = "data/v.json"
        a = t.add_concept({"title": "Steel resists rust", "text": "Stainless steel forms a passive chromium layer", "tags": ["metal"]}, f)
        self.assertEqual(t.add_concept({"title": "Steel resists rust", "text": "Stainless steel forms a passive chromium layer"}, f)["status"], "already_stored")
        t.add_concept({"title": "Wood grain", "text": "Growth rings"}, f)
        self.assertEqual(t.search_concepts("rust chromium", f)[0]["id"], a["id"])
        self.assertEqual(t.search_concepts("zzzz", f), [])
        with self.assertRaises(ValueError):
            t.add_concept({"title": "Third", "text": "x"}, f, max_concepts=2)
        with self.assertRaises(ValueError):
            t.add_concept({"title": "", "text": "x"}, f)
        with self.assertRaises(KeyError):
            t.get_concept("nope", f)


class StyleAndAssets(Base):
    def test_style_and_traits_are_deterministic_and_checked(self):
        st, at = M("silos/character_style_forge/lib/style_tool.py"), M("silos/character_style_forge/lib/attribute_tool.py")
        self.assertTrue(all(st.apply_aesthetic(p)["readable"] for p in st.PRESETS))
        self.assertAlmostEqual(st.contrast_ratio("#000000", "#ffffff"), 21.0)
        self.assertEqual(at.generate_traits("rival_01", 3, "x"), at.generate_traits("rival_01", 3, "x"))
        self.assertNotEqual(at.generate_traits("rival_01", 3, "x")["traits"], at.generate_traits("rival_01", 3, "y")["traits"])
        for bad in (lambda: st.apply_aesthetic("nope"), lambda: at.generate_traits("nope"), lambda: at.generate_traits("rival_01", 99)):
            with self.assertRaises(ValueError):
                bad()

    def test_assets_are_real_files_registered_once_and_tampering_is_caught(self):
        g, r = M("silos/asset_generation_library/lib/generator_tool.py"), M("silos/asset_generation_library/lib/registry_tool.py")
        a = g.create_asset("gradient_background", "240p", colors=("#102030", "#405060"))
        self.assertEqual(a["res"], [426, 240])
        self.assertEqual(g.create_asset("gradient_background", "240p", colors=("#102030", "#405060"))["sha256"], a["sha256"])
        self.assertEqual(r.register_asset(a, "data/m.json")["status"], "registered")
        self.assertEqual(r.register_asset(a, "data/m.json")["status"], "already_registered")
        self.assertTrue(r.verify_manifest("data/m.json")["ok"])
        with open(a["path"], "ab") as f:
            f.write(b"x")
        self.assertFalse(r.verify_manifest("data/m.json")["ok"])
        for bad in (lambda: g.create_asset("video", "240p"), lambda: g.create_asset("solid_color", "9000x9000"), lambda: g.create_asset("solid_color", "240p", color="red")):
            with self.assertRaises(ValueError):
                bad()


class Compiler(Base):
    def _inputs(self):
        nar = M("silos/vision_narrative_architect/lib/schema_builder.py").build_narrative_schema(SCRIPT)
        tim = M("silos/storyboard_timing_precision_engine/lib/rhythm_calc.py").calculate_beat_alignment(nar["beats"], 12)
        return {"narrative": nar, "timing": tim, "style": M("silos/character_style_forge/lib/style_tool.py").apply_aesthetic("rugged_steel")["style"], "resolution": "240p"}

    def test_parser_checks_the_inputs_against_each_other_and_assembler_builds_a_plan(self):
        p, a = M("silos/blueprint_compiler/lib/parser_tool.py"), M("silos/blueprint_compiler/lib/assembler_tool.py")
        d = self._inputs()
        self.assertEqual(p.validate_raw_data(d, "2.0.0")["status"], "parsed")
        plan = a.build_final_blueprint(d, "draft")
        self.assertEqual((plan["total_frames"], len(plan["scenes"]), plan["quality"]), (d["timing"]["total_duration"], 3, "draft"))
        self.assertEqual([s["start_frame"] for s in plan["scenes"][1:]], [s["end_frame"] for s in plan["scenes"][:-1]])
        self.assertEqual(a.build_final_blueprint(d, "draft")["blueprint_sha256"], plan["blueprint_sha256"])
        short = dict(d, timing=dict(d["timing"], beats=d["timing"]["beats"][:2]))
        self.assertIn("does not cover", " ".join(p.validate_raw_data(short, "2.0.0")["problems"]))
        self.assertIn("not supported", " ".join(p.validate_raw_data(d, "1.0.0")["problems"]))
        with self.assertRaises(ValueError):
            a.build_final_blueprint(d, "nowhere")

    def test_the_cgi_hook_saves_a_plan_and_notices_when_it_is_edited(self):
        cfg = M("silos/cgi/config/blueprint_compiler_hook_config.py").blueprint_compiler_hook_config
        hook = M("silos/cgi/lib/blueprint_compiler_hook_tool.py").blueprint_compiler_hook_tool(dict(cfg))
        out = hook.compile_blueprint(self._inputs(), "draft")
        self.assertTrue(hook.validate_syntax(out["id"])["valid"])
        plan = json.load(open(out["path"]))
        plan["scenes"][0]["nodes"][0]["type"] = "hologram"
        json.dump(plan, open(out["path"], "w"))
        v = hook.validate_syntax(out["id"])
        self.assertFalse(v["valid"])
        self.assertTrue(any("hash" in p for p in v["problems"]) and any("hologram" in p for p in v["problems"]))
        bad = self._inputs()
        bad["narrative"]["status"] = "invalid"
        with self.assertRaises(ValueError):
            hook.compile_blueprint(bad, "draft")


def cgi_tool(name, **over):
    cfg = dict(getattr(M("silos/cgi/config/%s_config.py" % name), name + "_config"), **over)
    return getattr(M("silos/cgi/lib/%s_tool.py" % name), name + "_tool")(cfg)


class Cgi(Base):
    def test_scene_graph_is_built_from_a_plan_and_edited_safely(self):
        t = cgi_tool("scene_orchestrator")
        d = Compiler()._inputs()
        plan = M("silos/blueprint_compiler/lib/assembler_tool.py").build_final_blueprint(d, "draft")
        with self.assertRaises(ValueError):
            t.construct_scene({"status": "draft", "scenes": []})
        info = t.construct_scene(plan)
        self.assertEqual(info["scenes"], 3)
        self.assertEqual(t.modify_node("caption", {"color": "#ff0000"}), 3)
        self.assertEqual(t.modify_node("caption", {"text": "changed"}, scene=2), 1)
        self.assertEqual(t.find_node("caption", 2)[1]["text"], "changed")
        for bad in ({"colour": "x"}, {"x": "left"}):
            with self.assertRaises(ValueError):
                t.modify_node("caption", bad)
        with self.assertRaises(KeyError):
            t.modify_node("ghost", {"x": 0.1})
        self.assertEqual(t.scene_for_frame(0)[0], 1)
        self.assertIsNone(t.scene_for_frame(10 ** 6))

    def test_camera_lighting_and_quality_really_change_the_picture(self):
        r = M("silos/cgi/lib/renderer.py")
        scene = {"background": ["#202020", "#404040"], "nodes": [{"id": "t", "type": "text", "text": "Hello", "x": 0.5, "y": 0.5, "size": 0.2, "color": "#ffffff"}]}
        base = r.render_frame(scene, 0, (160, 90))
        self.assertEqual(r.render_frame(scene, 0, (160, 90)).tobytes(), base.tobytes())
        self.assertNotEqual(r.render_frame(scene, 0, (160, 90), camera={"zoom": 2.0}).tobytes(), base.tobytes())
        bright = r.render_frame(scene, 0, (160, 90), lighting={"ambient": [0.2] * 3, "lights": {"k": {"intensity": 1.5, "color": "#ffffff"}}})
        self.assertGreater(sum(bright.convert("L").getdata()), sum(base.convert("L").getdata()))
        node = {"keys": [{"f": 0, "opacity": 0.0}, {"f": 10, "opacity": 1.0}]}
        self.assertEqual((r.prop_at(node, "opacity", 5), r.prop_at(node, "opacity", -3), r.prop_at(node, "opacity", 99)), (0.5, 0.0, 1.0))
        pipe = cgi_tool("render_pipeline_utility")
        self.assertEqual(pipe.update_quality_settings("draft")["scale"], 0.5)
        self.assertEqual(pipe.render_frame(scene, 0, (160, 90)).size, (80, 44))
        with self.assertRaises(ValueError):
            pipe.update_quality_settings("ultra")
        with self.assertRaises(ValueError):
            r.render_frame({"background": ["#000000", "#111111"], "nodes": [{"type": "hologram"}]}, 0, (16, 16))

    def test_cameras_are_validated_and_ease(self):
        c = cgi_tool("camera_logic_utility")
        c.activate_camera("wide")
        c.modify_transform("wide", (0.25, 0.75, 2.0), 10)
        self.assertEqual(c.cameras["wide"], {"x": 0.25, "y": 0.75, "zoom": 2.0, "roll": 10.0})
        mid = c.transform_at(0.5)
        self.assertAlmostEqual(mid["zoom"], 1.5)
        self.assertLess(c.transform_at(0.1)["zoom"], 1.0 + 0.1)                      # eased: slower than linear at the start
        for bad in (((1.5, 0.5), 0), ((0.5, 0.5, 9), 0), ((0.5, 0.5), 80)):
            with self.assertRaises(ValueError):
                c.modify_transform("wide", *bad)
        with self.assertRaises(KeyError):
            c.modify_transform("ghost", (0.5, 0.5), 0)

    def test_lighting_presets_and_limits(self):
        l = cgi_tool("lighting_present_utility")
        setup = l.apply_lighting_setup("sc", "night")
        self.assertEqual(set(setup["lights"]), {"key", "fill"})
        self.assertEqual(l.update_light_intensity("key", 1.2), 1)
        self.assertEqual(store.read_json("data/lighting/sc.json")["lights"]["key"]["intensity"], 1.2)
        for bad in (lambda: l.update_light_intensity("key", 9), lambda: l.update_light_intensity("ghost", 1), lambda: l.apply_lighting_setup("x", "disco")):
            with self.assertRaises((ValueError, KeyError)):
                bad()

    def test_rigs_are_checked_weighted_and_saved(self):
        t = cgi_tool("rigging_automator")
        joints = [{"name": "hip", "parent": None, "pos": [0, 0]}, {"name": "knee", "parent": "hip", "pos": [0, 1]}, {"name": "foot", "parent": "knee", "pos": [0, 2]}]
        out = t.bind_skeleton({"id": "leg", "vertices": [[0, 0.2], [0, 1.6], [0.1, 2.4]], "skeleton": {"joints": joints}})
        self.assertEqual((out["joints"], out["weighted"]), (3, True))
        self.assertTrue(t.validate_rig("leg")["valid"])
        rig = store.read_json("data/rigs/leg.json")
        self.assertAlmostEqual(sum(rig["weights"][0].values()), 1.0, places=4)
        self.assertGreater(rig["weights"][0]["hip"], rig["weights"][0].get("foot", 0))
        rig["weights"][1] = {"knee": 0.3}
        store.write_json("data/rigs/leg.json", rig)
        self.assertIn("sum to", " ".join(t.validate_rig("leg")["problems"]))
        cyc = [{"name": "a", "parent": "b", "pos": [0, 0]}, {"name": "b", "parent": "a", "pos": [0, 1]}]
        for bad in (cyc, joints + [{"name": "second_root", "parent": None, "pos": [1, 1]}], [], [{"name": "a", "parent": "zz", "pos": [0, 0]}]):
            with self.assertRaises(ValueError):
                t.bind_skeleton({"id": "bad", "vertices": [], "skeleton": {"joints": bad}})
        self.assertFalse(t.validate_rig("missing")["valid"])

    def test_recorder_registry_and_buffer(self):
        rec = cgi_tool("frame_sequence_recorder", buffer_size_limit=3)
        from PIL import Image
        with self.assertRaises(RuntimeError):
            rec.write_frame(Image.new("RGB", (4, 4)))
        d = rec.begin_capture("s1")
        for _ in range(3):
            rec.write_frame(Image.new("RGB", (8, 8), (9, 9, 9)))
        with self.assertRaises(RuntimeError):
            rec.write_frame(Image.new("RGB", (8, 8)))
        with self.assertRaises(TypeError):
            rec2 = cgi_tool("frame_sequence_recorder")
            rec2.begin_capture("s2")
            rec2.write_frame("not an image")
        self.assertEqual((rec.finish()["frames"], sorted(os.listdir(d))[0]), (3, "frame_00000.png"))
        buf = cgi_tool("buffer_governor_bridge")
        self.assertIsNone(buf.check_throughput()["ok"])
        self.assertEqual(buf.sync_state("s1")["frames"], 3)
        with self.assertRaises(KeyError):
            buf.sync_state("ghost")
        reg = cgi_tool("asset_registry_loader")
        f = os.path.join(WS, "a.bin")
        open(f, "wb").write(b"abc")
        reg.add_to_registry("a1", f)
        self.assertTrue(reg.fetch_asset("a1")["verified"])
        open(f, "wb").write(b"changed")
        self.assertFalse(reg.fetch_asset("a1")["verified"])
        with self.assertRaises(ValueError):
            reg.add_to_registry("a1", f)                                              # same id, different content
        with self.assertRaises(KeyError):
            reg.fetch_asset("zz")

    def test_the_governor_bridge_demands_telemetry_and_reaches_the_governor(self):
        b = cgi_tool("src_governor_bridge")
        self.assertEqual(b.execute_report("ok", {"frame_time": 1})["missing"], ["memory_usage", "asset_load_status", "render_error_count"])
        full = {k: 0 for k in ("frame_time", "memory_usage", "asset_load_status", "render_error_count")}
        self.assertEqual(b.execute_report("ok", full)["status"], "SUCCESS")
        st = b.interrogate_state()
        self.assertEqual((st["status"], st["bridge"]), ("operational", "active"))


class Compositing(Base):
    def test_blend_modes_and_timeline_alignment(self):
        from PIL import Image
        lt, tt = M("silos/composition_sync_engine/lib/layer_tool.py"), M("silos/composition_sync_engine/lib/temporal_tool.py")
        a, b = Image.new("RGB", (4, 4), (100, 100, 100)), Image.new("RGB", (4, 4), (100, 100, 100))
        self.assertEqual(lt.stack_visuals("add", [a, b])["image"].getpixel((0, 0)), (200, 200, 200))
        self.assertEqual(lt.stack_visuals("multiply", [a, b])["image"].getpixel((0, 0))[0], 39)
        half = Image.new("RGBA", (4, 4), (255, 0, 0, 128))
        self.assertGreater(lt.stack_visuals("alpha", [a, half])["image"].getpixel((0, 0))[0], 150)
        for bad in (lambda: lt.stack_visuals("xor"), lambda: lt.stack_visuals("add", [a, Image.new("RGB", (5, 5))]), lambda: lt.stack_visuals("add", [a] * 11)):
            with self.assertRaises(ValueError):
                bad()
        beats = [{"n": 1, "duration_s": 2.0}, {"n": 2, "duration_s": 3.0}]
        ok = tt.align_timeline(24, beats, 5.0)
        self.assertEqual((ok["status"], ok["total_frames"], ok["drift_frames"]), ("aligned", 120, 0.0))
        self.assertEqual(tt.align_timeline(24, beats, 5.2)["status"], "drift")
        with self.assertRaises(ValueError):
            tt.align_timeline(23, beats)


class FinalRender(Base):
    def _frames(self, n=6, gap=False):
        from PIL import Image
        d = tempfile.mkdtemp(dir=WS)
        for i in range(n):
            if gap and i == 3:
                continue
            Image.new("RGB", (32, 18), (i * 30, 0, 0)).save(os.path.join(d, "frame_%05d.png" % i))
        return d

    def test_encoder_makes_a_real_gif_and_refuses_what_it_cannot_do(self):
        enc, exp = M("silos/composition_final_render/lib/encoder_tool.py"), M("silos/composition_final_render/lib/exporter_tool.py")
        d = self._frames()
        out = enc.compress_stream("gif", d, os.path.join(WS, "o", "v.gif"), 12)
        self.assertEqual((out["codec"], out["frames"]), ("gif", 6))
        from PIL import Image
        with Image.open(out["path"]) as im:
            self.assertEqual(im.n_frames, 6)
        with self.assertRaises(ValueError):
            enc.compress_stream("gif", self._frames(gap=True))
        with self.assertRaises(ValueError):
            enc.compress_stream("gif", None)
        if not enc.find_ffmpeg():
            with self.assertRaises(RuntimeError):
                enc.compress_stream("h264", d, os.path.join(WS, "o", "v.mp4"), 12)                # never swapped silently
            self.assertEqual(enc.compress_stream("auto", d, os.path.join(WS, "o", "a.gif"), 12)["codec"], "gif")
        ex = exp.write_to_disk("/exports/final/", out["path"], "x.gif")
        self.assertEqual(ex["sha256"], out["sha256"])
        self.assertTrue(ex["destination"].startswith(WS))
        with self.assertRaises(ValueError):
            exp.write_to_disk("/exports/final/", None)
        with self.assertRaises(FileNotFoundError):
            exp.write_to_disk("/exports/final/", os.path.join(WS, "none.gif"))


class Governor(Base):
    def test_day_reports_are_accepted_or_rejected_and_logged_tamper_evidently(self):
        g = M("src/governor/governor.py").Govenor()
        self.assertEqual(g.handle_day_report("cgi", {"status": "fine"})["status"], "SUCCESS")
        self.assertEqual(g.handle_day_report("stranger", {"status": "fine"})["status"], "REJECTED")
        self.assertEqual(g.handle_day_report("cgi", {"status": "x", "api_key": "k"})["status"], "REJECTED")
        self.assertEqual(g.handle_day_report("cgi", {"status": "x", "url": "https://evil.example/x"})["status"], "REJECTED")
        self.assertEqual(g.handle_day_report("cgi", "not a dict")["status"], "REJECTED")
        t = M("src/governor/lib/tracker_tool.py")
        self.assertTrue(t.verify_log("logs/governance_audit.log")["ok"])
        p = store.resolve("logs/governance_audit.log")
        lines = open(p).read().splitlines()
        rec = json.loads(lines[1])
        rec["status"] = "edited"
        lines[1] = json.dumps(rec, sort_keys=True)
        open(p, "w").write("\n".join(lines) + "\n")
        self.assertEqual(t.verify_log("logs/governance_audit.log")["first_bad_line"], 2)

    def test_regulator_and_policy_enforcer(self):
        reg, pol = M("src/governor/lib/regulator_tool.py"), M("src/governor/lib/policy_tool.py")
        self.assertEqual(reg.verify_regulatory_alignment({"a": [{"password": "x"}]}, "sovereign_stronghold_v1")["status"], "violation")
        self.assertEqual(reg.verify_regulatory_alignment({"a": "http://localhost:8000/x"}, "sovereign_stronghold_v1")["status"], "compliant")
        self.assertEqual(reg.verify_regulatory_alignment({"a": "https://example.com"}, "open_v1")["status"], "compliant")
        with self.assertRaises(ValueError):
            reg.verify_regulatory_alignment({}, "made_up_rules")
        tmp = os.path.join(ROOT, "_policy_probe")
        os.makedirs(tmp, exist_ok=True)
        try:
            open(os.path.join(tmp, "bad.py"), "w").write("import socket\nPASSWORD = 'abcdefgh1234'\nx = eval('1')\n")
            open(os.path.join(tmp, "good.py"), "w").write("import os\nPASSWORD = os.environ.get('P')\n")
            bad = pol.validate_compliance("_policy_probe/bad.py", "maximum_hardened", "sovereign_v1_sync")
            self.assertEqual({r for _, r in bad["violations"]}, {"network module socket", "hard-coded secret", "eval() call"})
            self.assertEqual(pol.validate_compliance("_policy_probe/bad.py", "standard", "p")["violations"][0][1], "eval() call")
            self.assertEqual(pol.validate_compliance("_policy_probe/good.py", "maximum_hardened", "p")["status"], "compliant")
            with self.assertRaises(ValueError):
                pol.validate_compliance("../outside.py", "standard", "p")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_access_control_needs_the_right_token_and_locks_after_repeated_failures(self):
        a = M("src/governor/lib/access_controler_tool.py")
        a.register_actor("ann", "level_beta", "a-long-secret-token")
        self.assertNotIn("a-long-secret-token", open(store.resolve("data/actors.json")).read())      # only a salted hash is kept
        self.assertEqual(a.verify_permission("ann", "vault", "level_beta", "a-long-secret-token")["status"], "granted")
        self.assertIn("below", a.verify_permission("ann", "vault", "level_alpha", "a-long-secret-token")["reason"])
        self.assertEqual(a.verify_permission("ann", "vault", "level_gamma")["reason"], "no token")
        self.assertEqual(a.verify_permission("nobody", "vault", "level_gamma", "x")["reason"], "unknown actor")
        for _ in range(3):
            self.assertEqual(a.verify_permission("ann", "vault", "level_beta", "wrong")["status"], "denied")
        self.assertIn("locked", a.verify_permission("ann", "vault", "level_beta", "a-long-secret-token")["reason"])
        with self.assertRaises(ValueError):
            a.register_actor("bob", "level_alpha", "short")

    def test_source_loader_stays_inside_its_root_and_honours_hash_pins(self):
        sm = M("src/governor/lib/source_manager.py")
        root = "src/governor"
        r = sm.load_module("lib/regulator_tool.py", root, True)
        self.assertEqual((r["kind"], r["cached"]), ("python", False))
        self.assertTrue(sm.load_module("lib/regulator_tool.py", root, True)["cached"])
        self.assertEqual(sm.load_module("config/governor_config.py", root, False)["module"].CONFIG["strictness_level"], "maximum_hardened")
        with self.assertRaises(ValueError):
            sm.load_module("../../vc_store.py", root, False)
        with self.assertRaises(ValueError):
            sm.load_module("lib/regulator_tool.py", root, False, pinned_hashes={"lib/regulator_tool.py": "0" * 64})
        with self.assertRaises(ValueError):
            sm.load_module("lib/regulator_tool.py", root, False, allowed_extensions=(".json",))
        with self.assertRaises(FileNotFoundError):
            sm.load_module("lib/none.py", root, False)

    def test_crypto_engine_needs_a_key_and_detects_tampering(self):
        mod = M("lib/cryptography_engine.py")
        ce = mod.CryptographyEngine
        os.environ.pop("VC_CRYPTO_KEY", None)
        real_key_file, mod.KEY_FILE = mod.KEY_FILE, os.path.join(WS, "no_such.key")          # pretend there is no key file, whatever this machine has
        with self.assertRaises(RuntimeError):
            ce.encrypt("secret")
        made = ce.init_key(os.path.join(WS, "t.key"))
        self.assertTrue(os.path.isfile(made))
        with self.assertRaises(FileExistsError):
            ce.init_key(made)                                                                  # a key is never overwritten
        mod.KEY_FILE = made
        self.assertEqual(ce.decrypt(ce.encrypt("from the key file")), b"from the key file")
        mod.KEY_FILE = os.path.join(WS, "no_such.key")
        os.environ["VC_CRYPTO_KEY"] = ce.generate_key()
        try:
            tok = ce.encrypt("secret")
            self.assertNotIn("secret", tok)
            self.assertEqual(ce.decrypt(tok), b"secret")
            from cryptography.fernet import InvalidToken
            with self.assertRaises(InvalidToken):
                ce.decrypt(tok[:-4] + "AAAA")
        finally:
            os.environ.pop("VC_CRYPTO_KEY", None)
            mod.KEY_FILE = real_key_file
        pv = M("lib/protocol_validator.py").ProtocolValidator
        self.assertTrue(pv.validate({"a": 1}))
        self.assertFalse(pv.validate(""))
        self.assertFalse(pv.validate("bad\x00text"))
        self.assertFalse(pv.validate({"x": object()}))


class EndToEnd(Base):
    def test_a_script_becomes_a_verified_video_and_a_second_run_reuses_everything(self):
        b = builder()
        r = b.orchestrate_silos(dict(ORDER, project_id="e2e"))
        self.assertEqual(r["status"], "build_complete", r)
        self.assertEqual(set(r["stages"].values()), {"done"})
        self.assertEqual(r["governor"], "SUCCESS")
        from PIL import Image
        with Image.open(r["video"]) as im:
            plan = store.read_json(json.load(open(os.path.join(WS, "projects", "e2e", "state.json")))["stages"]["blueprint_compiler"]["artifacts"]["blueprint"]["path"])
            self.assertEqual(im.n_frames, plan["total_frames"])
        self.assertEqual(store.sha256_file(r["video"]), store.sha256_file(r["export"]))
        again = b.orchestrate_silos(dict(ORDER, project_id="e2e"))
        self.assertEqual(set(again["stages"].values()), {"skipped"})
        audit = M("src/quality_control/inspector/lib/inspector_tool.py").run_audit("e2e", True, "verbose")
        self.assertEqual(audit["issues"], [])
        self.assertGreater(audit["checked"], 25)
        v = M("src/quality_control/inspector/lib/validator_tool.py").evaluate_against_protocol(audit, "hardened")
        self.assertEqual(v["status"], "validated")
        mon = M("src/integration_office/master_builder/lib/monitor_tool.py").check_silo_status(["cgi", "final_render", "ghost"], 5000)
        self.assertEqual((mon["status"], mon["active_count"], mon["silos"]["ghost"]["state"]), ("degraded", 2, "NEVER_SEEN"))

    def test_changed_files_are_noticed_and_only_the_stale_stages_run_again(self):
        b = builder()
        b.orchestrate_silos(dict(ORDER, project_id="stale"))
        frame = os.path.join(WS, "projects", "stale", "render", "frames", "frame_00000.png")
        open(frame, "ab").write(b"tamper")
        r = b.orchestrate_silos(dict(ORDER, project_id="stale"))
        self.assertEqual(r["status"], "build_complete")
        self.assertEqual({k: v for k, v in r["stages"].items() if v == "skipped"}.keys(), {"interview", "narrative", "timing", "style", "footage", "ai_assets", "asset_generation", "blueprint_compiler"})
        self.assertEqual(r["stages"]["cgi_render"], "done")
        self.assertEqual(r["stages"]["final_render"], "done")

    def test_the_inspector_catches_a_swapped_video_and_the_validator_fails_it(self):
        b = builder()
        r = b.orchestrate_silos(dict(ORDER, project_id="swap"))
        open(r["export"], "ab").write(b"x")
        audit = M("src/quality_control/inspector/lib/inspector_tool.py").run_audit("swap", True, "verbose")
        checks = {i["check"] for i in audit["issues"]}
        self.assertIn("file_hash", checks)
        self.assertIn("export_identical", checks)
        val = M("src/quality_control/inspector/lib/validator_tool.py").evaluate_against_protocol(audit, "standard")
        self.assertEqual(val["status"], "failed")
        rep = M("src/quality_control/inspector/lib/reporter_tool.py").format_and_dispatch(dict(audit, validation=val), "markdown")
        self.assertIn("FAILED", open(rep["path"]).read())
        self.assertTrue(M("src/quality_control/inspector/lib/reporter_tool.py").format_and_dispatch(audit, "json_log")["path"].endswith(".json"))
        with self.assertRaises(ValueError):
            M("src/quality_control/inspector/lib/reporter_tool.py").format_and_dispatch(audit, "pdf")
        self.assertEqual(M("src/quality_control/inspector/lib/validator_tool.py").evaluate_against_protocol({"checked": 0}, "relaxed")["status"], "failed")
        self.assertEqual(M("src/quality_control/inspector/lib/inspector_tool.py").run_audit("no-such-project", True, "v")["issues"][0]["check"], "state_file")

    def test_a_failing_stage_stops_the_build_names_itself_and_can_be_rolled_back(self):
        b = builder()
        r = b.orchestrate_silos(dict(ORDER, project_id="bad", style="not_a_style"))
        self.assertEqual(r["status"], "build_failed")
        self.assertIn("style failed", r["error"])
        self.assertEqual(r["stages"], {"interview": "done", "narrative": "done", "timing": "done", "style": "failed"})
        self.assertNotIn("video", r)
        good = b.orchestrate_silos(dict(ORDER, project_id="rb"))
        self.assertEqual(good["status"], "build_complete")
        rec = M("src/integration_office/master_builder/lib/recovery_tool.py")
        out = rec.trigger_rollback("E_TEST", "immediate_snapshot", "rb")
        self.assertEqual((out["restored_to"], out["rolled_back"]), ("final_render", []))        # everything is stable: nothing to undo
        open(os.path.join(WS, "projects", "rb", "render", "frames", "frame_00001.png"), "ab").write(b"x")
        out = rec.trigger_rollback("E_TEST", "immediate_snapshot", "rb")
        self.assertEqual(out["restored_to"], "blueprint_compiler")                               # the damaged render is not a restore point
        self.assertEqual(out["rolled_back"], ["cgi_render", "composition_sync", "final_render"])
        self.assertFalse(os.path.exists(os.path.join(WS, "projects", "rb", "render", "frames")))
        self.assertTrue(os.path.exists(good["export"]))                                          # the exported copy is outside the project and stays
        with self.assertRaises(ValueError):
            rec.trigger_rollback("x", "immediate_snapshot")
        with self.assertRaises(ValueError):
            rec.trigger_rollback("x", 99, "rb")
        redo = b.orchestrate_silos(dict(ORDER, project_id="rb"))
        self.assertEqual(redo["status"], "build_complete")

    def test_the_interview_path_asks_questions_then_builds(self):
        b = builder()
        first = b.orchestrate_silos({"project_id": "iv", "answers": {"topic": "Why steel lasts"}, "resolution": "240p", "environment": "draft", "fps": 12, "codec": "gif"})
        self.assertEqual(first["status"], "needs_input")
        self.assertEqual(first["missing"], ["key_points"])
        done = b.orchestrate_silos({"project_id": "iv", "answers": {"key_points": ["it resists rust", "it recycles"], "call_to_action": "Choose steel"}, "resolution": "240p",
                                    "environment": "draft", "fps": 12, "codec": "gif"})
        self.assertEqual(done["status"], "build_complete", done)

    def test_orders_with_secrets_or_unknown_stages_are_refused(self):
        b = builder()
        with self.assertRaises(ValueError):
            b.orchestrate_silos(dict(ORDER, api_key="abc"))
        with self.assertRaises(ValueError):
            b.orchestrate_silos(ORDER, ["interview", "teleport"])
        bad_res = b.orchestrate_silos(dict(ORDER, project_id="res", resolution="12x"))
        self.assertEqual(bad_res["status"], "build_failed")

    def test_main_cli_builds_and_inspects(self):
        env = dict(os.environ, VC_WORKSPACE=WS)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "main.py"), "--script", "One short line. Another short line.", "--resolution", "240p", "--fps", "12",
                            "--codec", "gif", "--project", "cli"], capture_output=True, text=True, env=env, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-300:] + r.stderr[-300:])
        self.assertIn('"status": "build_complete"', r.stdout)
        i = subprocess.run([sys.executable, os.path.join(ROOT, "main.py"), "--inspect", "cli"], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(i.returncode, 0, i.stdout[-300:])
        self.assertIn('"status": "validated"', i.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1, warnings="ignore")
