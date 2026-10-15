"""test_factory.py - the dashboard factory: type registry and isolation, custom types, the platform generator, the environment compiler and its physics (run under Node), the micro-company engine
(routing, caps, ledger, kill switch, no calls/SMS), the real mp4 maker, the lab's stress runs, and the server routes (admin gate, build, preview, inbox, custom types).
Throwaway folders and token; nothing here calls a model or the network. Run: python test_factory.py"""
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

TMP = tempfile.mkdtemp(prefix="factory_")
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
import factory_hub  # noqa: E402
import factory_lab  # noqa: E402
import factory_platform  # noqa: E402
import factory_types as FT  # noqa: E402
import micro_company as MC  # noqa: E402
import video_maker  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}


def scene(n=20, extra=None):
    cfg = {"title": "Test yard", "ground": 40, "objects": [{"shape": "box", "size": [4, 2, 4], "position": [0, 1, 0]}] +
           [{"shape": "sphere", "size": [0.6], "position": [(i % 9) - 4, 4 + i * 0.3, (i % 7) - 3], "dynamic": True, "mass": 1} for i in range(n)]}
    cfg.update(extra or {})
    return cfg


class Types(unittest.TestCase):
    def setUp(self):
        self.f = FT.Factory(tempfile.mkdtemp(dir=TMP))

    def test_builtin_types_cannot_be_changed_through_a_read(self):
        t = self.f.types()
        t["micro_company"]["fields"].clear()
        t["platform_factory"]["title"] = "x"
        self.assertTrue(self.f.types()["micro_company"]["fields"])
        self.assertEqual(self.f.type("platform_factory")["title"], "Platform factory")

    def test_a_type_rejects_another_types_fields(self):
        with self.assertRaises(FT.FactoryError) as c:
            self.f.create("platform_factory", "x", {"brand": "A", "kind": "site", "bots": []})
        self.assertIn("not fields of", str(c.exception))

    def test_instances_live_in_their_own_folders(self):
        a = self.f.create("platform_factory", "A", {"brand": "A", "kind": "site"})
        b = self.f.create("platform_factory", "B", {"brand": "B", "kind": "site"})
        c = self.f.create("spatial_environment", "C", {"title": "C", "objects": [{"shape": "box", "size": [1, 1, 1]}]})
        dirs = {self.f.workdir(r["type"], r["id"]) for r in (a, b, c)}
        self.assertEqual(len(dirs), 3)
        self.assertEqual(self.f.workdir("platform_factory", a["id"]).parent.name, "platform_factory")
        with self.assertRaises(FT.FactoryError):
            self.f.workdir("platform_factory", "../../etc")
        with self.assertRaises(FT.FactoryError):
            self.f.get("spatial_environment", a["id"])                      # an id from one type is not found under another

    def test_custom_types_extend_and_cannot_touch_built_ins(self):
        t = self.f.define_custom("Studio brief", "Studio brief", "bespoke", [{"name": "client", "kind": "text", "required": True}, {"name": "tier", "kind": "choice", "choices": ["a", "b"]}])
        self.assertEqual(t["key"], "custom_studio_brief")
        self.assertFalse(t["builtin"])
        r = self.f.create("custom_studio_brief", "One", {"client": "Acme", "tier": "a"})
        self.assertEqual(r["config"], {"client": "Acme", "tier": "a"})
        with self.assertRaises(FT.FactoryError):
            self.f.create("custom_studio_brief", "Bad", {"client": "A", "tier": "zzz"})
        shadow = self.f.define_custom("micro_company", "Mine", "", [{"name": "note", "kind": "text"}])      # a new type, custom_micro_company: it never replaces the built-in
        self.assertEqual(shadow["key"], "custom_micro_company")
        self.assertEqual(self.f.type("micro_company")["engine"], "micro_company")
        self.assertTrue(self.f.type("micro_company")["builtin"])
        self.f.delete_custom("custom_micro_company")
        with self.assertRaises(FT.FactoryError):
            self.f.define_custom("needs", "Needs", "", [{"name": "note", "kind": "text"}], engine="platform_factory")   # must carry the engine's required fields
        with self.assertRaises(FT.FactoryError):
            self.f.delete_custom("custom_studio_brief")                    # still has an instance
        self.f.delete("custom_studio_brief", r["id"])
        self.f.delete_custom("custom_studio_brief")
        self.assertNotIn("custom_studio_brief", self.f.types())

    def test_custom_types_survive_a_restart(self):
        self.f.define_custom("keeper", "Keeper", "", [{"name": "note", "kind": "text"}])
        self.assertIn("custom_keeper", FT.Factory(self.f.root).types())


class Platform(unittest.TestCase):
    PNG = None

    def resolver(self):
        from PIL import Image
        import io
        b = io.BytesIO()
        Image.new("RGB", (8, 8), (200, 30, 30)).save(b, "PNG")
        data = b.getvalue()
        return lambda cid: [("a.png", data)] if cid == "asset-1" else None

    def test_a_storefront_is_built_and_proves_itself(self):
        d = tempfile.mkdtemp(dir=TMP)
        cfg = {"brand": "Harbor & Co", "kind": "storefront", "tagline": "<b>Fresh</b>", "products": [{"name": "Print <1>", "price": 12.5, "currency": "usd", "asset": "asset-1"}, {"name": "Card", "price": 0}]}
        m = factory_platform.build(d, cfg, self.resolver(), "fi-abcdef012345")
        self.assertEqual(m["products"], 2)
        self.assertEqual(m["assets"], 1)
        home = open(os.path.join(d, "site", "index.html"), encoding="utf-8").read()
        self.assertIn("Harbor &amp; Co", home)
        self.assertNotIn("<b>Fresh</b>", home)                                   # escaped, not injected
        self.assertNotRegex(home, r"https?://")
        contact = open(os.path.join(d, "site", "contact.html"), encoding="utf-8").read()
        self.assertIn("/api/factory/fi-abcdef012345/inbox", contact)

    def test_a_missing_asset_fails_the_build(self):
        with self.assertRaises(factory_platform.PlatformError):
            factory_platform.build(tempfile.mkdtemp(dir=TMP), {"brand": "A", "kind": "storefront", "products": [{"name": "P", "price": 1, "asset": "nope"}]}, self.resolver())

    def test_bad_products_are_refused(self):
        for cfg in ({"brand": "A", "kind": "storefront"}, {"brand": "A", "kind": "site", "products": [{"name": "P", "price": 1}]},
                    {"brand": "A", "kind": "storefront", "products": [{"name": "P", "price": -1}]}, {"brand": "A", "kind": "storefront", "products": [{"name": "P", "price": True}]}):
            with self.assertRaises(factory_platform.PlatformError, msg=cfg):
                factory_platform.build(tempfile.mkdtemp(dir=TMP), cfg)


@unittest.skipUnless(shutil.which("node"), "node is needed")
class Environment(unittest.TestCase):
    def test_bad_scenes_are_refused_not_repaired(self):
        for bad in ({"objects": []}, {"objects": [{"shape": "cone", "size": [1]}]}, {"objects": [{"shape": "box", "size": [1, 1, 1], "position": [0, 0, 0]}]},
                    {"objects": [{"shape": "box", "size": [1, 1, 1], "position": [99, 1, 0]}]}, {"objects": [{"shape": "box", "size": [1, 1, float("nan")], "position": [0, 1, 0]}]},
                    {"objects": [{"shape": "sphere", "size": [1], "position": [0, 1, 0], "color": "red"}]}, {"objects": [{"shape": "sphere", "size": [1], "position": [0, 1, 0], "dynamic": "yes"}]}):
            with self.assertRaises(factory_env.EnvError, msg=bad):
                factory_env.compile_scene(bad)

    def test_build_check_and_the_checks_catch_tampering(self):
        d, cfg = tempfile.mkdtemp(dir=TMP), scene()
        factory_env.build(d, cfg)
        self.assertEqual(factory_env.check(d, cfg), {"ok": True, "problems": []})
        p = os.path.join(d, "env", "env.js")
        open(p, "a").write("\nfunction (")                                   # break the runtime
        r = factory_env.check(d, cfg)
        self.assertFalse(r["ok"])
        self.assertTrue(any("env.js" in x for x in r["problems"]))
        self.assertNotRegex(open(os.path.join(d, "env", "index.html"), encoding="utf-8").read(), r"(src|href)=\"https?:")

    def test_a_script_in_a_title_cannot_break_out_of_the_page(self):
        d, cfg = tempfile.mkdtemp(dir=TMP), scene(2, {"title": "</script><script>alert(1)</script>"})
        factory_env.build(d, cfg)
        page = open(os.path.join(d, "env", "index.html"), encoding="utf-8").read()
        self.assertEqual(page.count("<script"), 4)                             # data + babylon + physics + env: nothing extra
        self.assertTrue(factory_env.check(d, cfg)["ok"])

    def test_physics_a_sphere_rests_on_a_box_and_nothing_leaves_the_world(self):
        r = factory_env.simulate({"title": "t", "ground": 40, "objects": [{"shape": "box", "size": [4, 2, 4], "position": [0, 1, 0]}, {"shape": "sphere", "size": [1], "position": [0, 6, 0], "dynamic": True}]}, 400)
        self.assertEqual((r["faults"], r["out_of_bounds"]), (0, 0))
        self.assertAlmostEqual(r["min_height"], 0.0 + 2.0, delta=0.05)       # the lowest dynamic body is on top of the 2 m box
        big = factory_env.simulate(scene(1500, {"ground": 60}) | {"objects": scene(1500)["objects"]}, 300)
        self.assertEqual((big["faults"], big["out_of_bounds"]), (0, 0))

    def test_physics_survives_bad_numbers_by_freezing_the_body(self):
        js = ("const {World}=require(%r);const w=new World({});w.addBody({shape:'sphere',pos:[0,5,0],r:.5,dynamic:true});"
              "w.addBody({shape:'sphere',pos:[NaN,1,0],r:.5,dynamic:true});for(let i=0;i<50;i++)w.step(1/60);console.log(JSON.stringify(w.stats()))") % os.path.join(ROOT, "factory_env_physics.js")
        out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(out["faults"], 1)


class Company(unittest.TestCase):
    def services(self, log=None):
        log = log if log is not None else []
        return {"health": lambda: {"ok": True}, "creation": lambda p: log.append(("creation", p)) or {"job": "j1"}, "video": lambda t, l, s: log.append(("video", t)) or {"creation_id": "c1", "title": t},
                "stage": lambda *a: log.append(("stage", a)) or "pq-1", "channel": lambda: {"title": "chan"}}

    def test_phone_sms_and_telemarketing_tasks_are_refused_with_a_reason(self):
        for task in ("telemarketing_call", "dial_leads", "send_sms", "phone_outreach", "robocall"):
            with self.assertRaises(MC.CompanyError) as c:
                MC.validate({"company": "A", "bots": [{"name": "Dialer", "task": task}]})
            self.assertIn("does not place calls", str(c.exception))

    def test_validation(self):
        bad = [{"company": "", "bots": [{"name": "A", "task": "report"}]}, {"company": "A", "bots": []}, {"company": "A", "bots": [{"name": "A", "task": "nope"}]},
               {"company": "A", "bots": [{"name": "A", "task": "report"}, {"name": "A", "task": "report"}]}, {"company": "A", "bots": [{"name": "A", "task": "report", "then": "Z"}]},
               {"company": "A", "bots": [{"name": "A", "task": "report", "then": "B"}, {"name": "B", "task": "report", "then": "A"}]},
               {"company": "A", "bots": [{"name": "W", "task": "webhook"}]}, {"company": "A", "bots": [{"name": "A", "task": "report", "every_s": 1}]},
               {"company": "A", "bots": [{"name": "A", "task": "report"}], "webhook_allow": ["http://x"]}]
        for cfg in bad:
            with self.assertRaises(MC.CompanyError, msg=cfg):
                MC.validate(cfg)

    def test_work_is_routed_along_the_chain_and_the_ledger_is_tamper_evident(self):
        log = []
        cfg = {"company": "Chain", "bots": [{"name": "Make", "task": "video_make", "params": {"title": "T", "lines": ["a"]}, "then": "Queue"}, {"name": "Queue", "task": "publish_stage", "params": {"title": "T"}, "then": "Rep"},
                                             {"name": "Rep", "task": "report"}]}
        co = MC.MicroCompany(tempfile.mkdtemp(dir=TMP), cfg, self.services(log))
        runs = co.run_bot("Make")
        self.assertEqual([r["bot"] for r in runs], ["Make", "Queue", "Rep"])
        self.assertTrue(all(r["ok"] for r in runs))
        self.assertEqual(log[1][1][0], "c1")                                   # the stager got the creation id from the maker, not from config
        self.assertEqual(co.verify_ledger(), (True, 3))
        lines = open(co._ledger, encoding="utf-8").read().splitlines()
        rec = json.loads(lines[1]); rec["ok"] = False
        lines[1] = json.dumps(rec, sort_keys=True)
        open(co._ledger, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        self.assertEqual(co.verify_ledger(), (False, 2))

    def test_a_failing_bot_is_recorded_and_stops_its_chain_only(self):
        sv = self.services()
        sv["health"] = lambda: (_ for _ in ()).throw(RuntimeError("down"))
        co = MC.MicroCompany(tempfile.mkdtemp(dir=TMP), {"company": "F", "bots": [{"name": "A", "task": "health_check", "then": "B"}, {"name": "B", "task": "report"}, {"name": "C", "task": "report"}]}, sv)
        runs = co.run_bot("A")
        self.assertEqual([(r["bot"], r["ok"]) for r in runs], [("A", False)])
        self.assertIn("down", runs[0]["error"])
        self.assertTrue(co.run_bot("C")[0]["ok"])

    def test_webhooks_go_only_to_the_owners_allow_list(self):
        sent = []
        cfg = {"company": "W", "webhook_allow": ["hooks.example.org"], "bots": [{"name": "Ok", "task": "webhook", "params": {"url": "https://hooks.example.org/a"}},
                                                                                {"name": "Evil", "task": "webhook", "params": {"url": "https://evil.example.net/a"}}, {"name": "Plain", "task": "webhook", "params": {"url": "http://hooks.example.org/a"}}]}
        co = MC.MicroCompany(tempfile.mkdtemp(dir=TMP), cfg, self.services(), post=lambda u, b: sent.append((u, b)) or 204)
        self.assertTrue(co.run_bot("Ok")[0]["ok"])
        self.assertFalse(co.run_bot("Evil")[0]["ok"])
        self.assertFalse(co.run_bot("Plain")[0]["ok"])
        self.assertEqual([u for u, _ in sent], ["https://hooks.example.org/a"])

    def test_caps_and_the_kill_switch(self):
        co = MC.MicroCompany(tempfile.mkdtemp(dir=TMP), {"company": "Cap", "bots": [{"name": "A", "task": "health_check", "every_s": 5}]}, self.services())
        res = [co.run_bot("A")[0] for _ in range(MC.HOURLY_BOT_CAP + 5)]
        self.assertEqual(sum(1 for r in res if r["ok"]), MC.HOURLY_BOT_CAP)
        self.assertTrue(all(r["error"] == "hourly run cap reached" for r in res if not r["ok"]))
        co2 = MC.MicroCompany(tempfile.mkdtemp(dir=TMP), {"company": "Run", "bots": [{"name": "A", "task": "health_check", "every_s": 5}]}, self.services())
        self.assertTrue(co2.start())
        self.assertFalse(co2.start())
        time.sleep(0.5)
        self.assertTrue(co2.running())
        self.assertGreaterEqual(co2.status()["runs"], 1)
        self.assertTrue(co2.stop())
        n = co2.status()["runs"]
        time.sleep(0.5)
        self.assertEqual(co2.status()["runs"], n)
        self.assertFalse(co2.running())

    def test_concurrent_runs_keep_an_intact_ledger(self):
        co = MC.MicroCompany(tempfile.mkdtemp(dir=TMP), {"company": "Par", "bots": [{"name": "A", "task": "health_check", "then": "B"}, {"name": "B", "task": "health_check"}]}, self.services())
        ts = [threading.Thread(target=lambda: [co.run_bot("A") for _ in range(10)]) for _ in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(co.verify_ledger(), (True, 120))


class Video(unittest.TestCase):
    def test_a_real_mp4_that_decodes(self):
        d = tempfile.mkdtemp(dir=TMP)
        r = video_maker.make(os.path.join(d, "v.mp4"), "Why bridges stand", ["Arches turn weight into compression.", "Cables carry tension."], 1)
        with open(r["path"], "rb") as f:
            self.assertEqual(f.read(12)[4:8], b"ftyp")
        v = video_maker.verify(r["path"], r["frames"])
        self.assertEqual((v["ok"], v["width"], v["height"]), (True, 1280, 720))
        self.assertGreater(r["seconds"], 2.5)

    def test_nothing_is_silently_cut(self):
        d = os.path.join(tempfile.mkdtemp(dir=TMP), "v.mp4")
        for title, lines, spc in (("T", [], 2), ("T", ["x" * 401], 2), ("", ["a"], 2), ("T", ["a"] * 25, 2), ("T", ["a"], 99), ("T", ["a"] * 24, 15)):
            with self.assertRaises(video_maker.VideoError, msg=(title, len(lines), spc)):
                video_maker.make(d, title, lines, spc)
        self.assertFalse(os.path.exists(d))

    def test_a_corrupt_file_does_not_verify(self):
        p = os.path.join(tempfile.mkdtemp(dir=TMP), "bad.mp4")
        open(p, "wb").write(b"not a video" * 50)
        self.assertFalse(video_maker.verify(p)["ok"])


class Hub(unittest.TestCase):
    def test_every_builtin_type_builds_and_a_recordonly_custom_type_says_so(self):
        hub = factory_hub.Hub(tempfile.mkdtemp(dir=TMP), {"health": lambda: {"ok": True}}, Platform().resolver())
        cfgs = {"platform_factory": {"brand": "B", "kind": "site"}, "spatial_environment": scene(5),
                "micro_company": {"company": "C", "bots": [{"name": "A", "task": "health_check"}]},
                "publishing_pipeline": {"topic": "t", "brief": "One. Two. Three.", "title": "T"}}
        for k, c in cfgs.items():
            r = hub.create(k, "x " + k, c)
            self.assertTrue(hub.build(k, r["id"])["ok"], k)
            self.assertEqual(hub.factory.get(k, r["id"])["state"], "built")
        hub.factory.define_custom("notes", "Notes", "", [{"name": "text", "kind": "text"}])
        r = hub.create("custom_notes", "n", {"text": "hello"})
        with self.assertRaises(FT.FactoryError) as c:
            hub.build("custom_notes", r["id"])
        self.assertIn("no generator", str(c.exception))

    def test_a_custom_type_built_with_an_engine_uses_it(self):
        hub = factory_hub.Hub(tempfile.mkdtemp(dir=TMP))
        hub.factory.define_custom("shop", "Shop", "", [{"name": "brand", "kind": "text", "required": True}, {"name": "kind", "kind": "choice", "choices": ["site", "storefront"], "required": True}, {"name": "owner", "kind": "text"}],
                                  engine="platform_factory")
        r = hub.create("custom_shop", "mine", {"brand": "Mine", "kind": "site", "owner": "me"})
        self.assertTrue(hub.build("custom_shop", r["id"])["ok"])
        self.assertTrue(hub.preview_root("custom_shop", r["id"]).is_dir())

    def test_a_failed_build_is_recorded_not_hidden(self):
        hub = factory_hub.Hub(tempfile.mkdtemp(dir=TMP))
        r = hub.create("platform_factory", "x", {"brand": "A", "kind": "storefront", "products": [{"name": "P", "price": 1, "asset": "gone"}]})
        with self.assertRaises(FT.FactoryError):
            hub.build("platform_factory", r["id"])
        self.assertEqual(hub.factory.get("platform_factory", r["id"])["state"], "build_failed")

    def test_the_pipeline_makes_a_video_and_stages_it(self):
        log = []
        sv = {"video": lambda t, l, s: log.append(("video", t, l)) or {"creation_id": "c9"}, "stage": lambda cid, title, desc="", tags=(), topic="": log.append(("stage", cid, title, topic)) or "pq-9"}
        hub = factory_hub.Hub(tempfile.mkdtemp(dir=TMP), sv)
        r = hub.create("publishing_pipeline", "p", {"topic": "bridges", "brief": "Arches work. Cables help.", "title": "Bridges", "tags": ["eng"]})
        hub.build("publishing_pipeline", r["id"])
        runs = hub.run_once("publishing_pipeline", r["id"], "Maker")
        self.assertEqual([(x["bot"], x["ok"]) for x in runs], [("Maker", True), ("Stager", True)])
        self.assertEqual(log[0][2], ["Arches work.", "Cables help."])
        self.assertEqual(log[1][1:], ("c9", "Bridges", "bridges"))


@unittest.skipUnless(shutil.which("node"), "node is needed")
class Lab(unittest.TestCase):
    def test_stress_runs_report_real_measurements_and_pass(self):
        lab = factory_lab.Lab(tempfile.mkdtemp(dir=TMP), {"health": lambda: {"ok": True}})
        for k in ("platform_factory", "spatial_environment", "micro_company"):
            r = lab.stress(k, "light")
            self.assertTrue(r["ok"], r)
            self.assertIn("measured", r)
            self.assertIn("rss_peak_mb", r)
        self.assertEqual(len(lab.telemetry()), 3)

    def test_two_runs_of_one_type_are_refused_and_unknown_types_too(self):
        lab = factory_lab.Lab(tempfile.mkdtemp(dir=TMP))
        lab._claim("stress:micro_company")
        with self.assertRaises(factory_lab.LabError):
            lab.stress("micro_company", "light")
        with self.assertRaises(factory_lab.LabError):
            lab.stress("custom_x", "light")
        with self.assertRaises(factory_lab.LabError):
            lab.stress("micro_company", "extreme")

    def test_demos_are_labelled_and_isolation_holds(self):
        lab = factory_lab.Lab(tempfile.mkdtemp(dir=TMP), {"health": lambda: {"ok": True}})
        hub = factory_hub.Hub(tempfile.mkdtemp(dir=TMP), {"health": lambda: {"ok": True}})
        for k in FT.BUILTIN:
            self.assertTrue(lab.demo(hub, k)["ok"], k)
        self.assertTrue(all(r.get("demo") for r in hub.factory.list()))
        self.assertTrue(lab.isolation(hub)["ok"])


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv
        import python_server as srv  # noqa: E402
        cls.http = srv.app.test_client()

    def post(self, path, body, admin=True):
        return self.http.post(path, json=body, headers=ADMIN if admin else {})

    def test_changes_need_the_admin_token_but_reading_does_not(self):
        self.assertEqual(self.http.get("/api/factory/types").status_code, 200)
        self.assertEqual(self.http.get("/api/factory/instances").status_code, 200)
        for path in ("/api/factory/instances", "/api/factory/types", "/api/factory/lab/stress"):
            self.assertEqual(self.post(path, {}, admin=False).status_code, 401, path)
        self.assertEqual(self.post("/api/factory/instances/platform_factory/fi-000000000000/build", {}, admin=False).status_code, 401)
        self.assertEqual(self.http.delete("/api/factory/instances/platform_factory/fi-000000000000").status_code, 401)

    def test_a_site_is_built_previewed_and_its_contact_form_actually_works(self):
        r = self.post("/api/factory/instances", {"type": "platform_factory", "name": "Route site", "config": {"brand": "Route Brand", "kind": "site", "about": "hi"}})
        self.assertEqual(r.status_code, 201, r.get_json())
        iid = r.get_json()["instance"]["id"]
        self.assertEqual(self.http.post("/api/factory/%s/inbox" % iid, json={"name": "a", "email": "a@b.c", "message": "hello"}).status_code, 404)      # not built yet: not accepting
        self.assertEqual(self.http.get("/api/factory/%s/preview/" % iid).status_code, 404)
        b = self.post("/api/factory/instances/platform_factory/%s/build" % iid, {})
        self.assertEqual(b.status_code, 200, b.get_json())
        page = self.http.get("/api/factory/%s/preview/contact.html" % iid)
        self.assertEqual(page.status_code, 200)
        self.assertIn(("/api/factory/%s/inbox" % iid).encode(), page.data)
        page.close()
        for sub in ("", "style.css"):
            g = self.http.get("/api/factory/%s/preview/%s" % (iid, sub))
            self.assertEqual(g.status_code, 200)
            g.close()
        self.assertEqual(self.http.get("/api/factory/%s/preview/../instance.json" % iid).status_code, 404)
        ok = self.http.post("/api/factory/%s/inbox" % iid, json={"name": "Ann", "email": "ann@example.org", "message": "hello"})
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(self.http.post("/api/factory/%s/inbox" % iid, json={"name": "", "email": "x", "message": ""}).status_code, 400)
        self.assertEqual(self.http.post("/api/factory/%s/inbox" % iid, data="x" * 7000, content_type="application/json").status_code, 413)
        entries = self.http.get("/api/factory/instances/platform_factory/%s/inbox" % iid, headers=ADMIN).get_json()["entries"]
        self.assertEqual([e["name"] for e in entries], ["Ann"])
        self.assertEqual(self.http.get("/api/factory/instances/platform_factory/%s/inbox" % iid).status_code, 401)        # the inbox is the owner's
        self.assertEqual(self.http.delete("/api/factory/instances/platform_factory/%s" % iid, headers=ADMIN).status_code, 200)

    def test_every_endpoint_a_generated_page_calls_exists(self):
        r = self.post("/api/factory/instances", {"type": "platform_factory", "name": "Endpoint scan", "config": {"brand": "Scan", "kind": "site"}})
        iid = r.get_json()["instance"]["id"]
        self.post("/api/factory/instances/platform_factory/%s/build" % iid, {})
        rules = {str(x) for x in srv.app.url_map.iter_rules()}
        for name in ("index.html", "about.html", "contact.html"):
            html = self.http.get("/api/factory/%s/preview/%s" % (iid, name)).get_data(as_text=True)
            for ref in re.findall(r"""["'](/api/[^"']+)["']""", html):
                self.assertTrue(any(re.fullmatch(re.sub(r"<[^>]+>", "[^/]+", rule), ref) for rule in rules), "%s calls %s, which has no route" % (name, ref))

    def test_environment_company_and_custom_type_through_the_routes(self):
        r = self.post("/api/factory/instances", {"type": "spatial_environment", "name": "Route env", "config": scene(10)})
        iid = r.get_json()["instance"]["id"]
        self.assertTrue(self.post("/api/factory/instances/spatial_environment/%s/build" % iid, {}).get_json()["build"]["ok"])
        page = self.http.get("/api/factory/%s/preview/" % iid)
        self.assertIn(b"physics.js", page.data)
        self.assertEqual(self.http.get("/api/factory/%s/preview/physics.js" % iid).status_code, 200)
        self.assertEqual(self.http.get("/vendor/babylon.js").status_code, 200)                      # the page's engine is served locally
        bad = self.post("/api/factory/instances", {"type": "spatial_environment", "name": "bad", "config": {"title": "x", "objects": [{"shape": "cone"}]}})
        self.assertEqual(bad.status_code, 201)                                                       # stored as configured...
        self.assertEqual(self.post("/api/factory/instances/spatial_environment/%s/build" % bad.get_json()["instance"]["id"], {}).status_code, 400)   # ...and refused loudly at build
        c = self.post("/api/factory/instances", {"type": "micro_company", "name": "Route co", "config": {"company": "Route Co", "bots": [{"name": "A", "task": "health_check", "every_s": 5}]}}).get_json()["instance"]["id"]
        self.assertEqual(self.post("/api/factory/instances/micro_company/%s/deploy" % c, {}).status_code, 400)          # build first
        self.post("/api/factory/instances/micro_company/%s/build" % c, {})
        self.assertEqual(self.post("/api/factory/instances/micro_company/%s/run" % c, {"bot": "A"}).get_json()["runs"][0]["ok"], True)
        self.assertTrue(self.post("/api/factory/instances/micro_company/%s/deploy" % c, {}).get_json()["started"])
        self.assertTrue(self.http.get("/api/factory/instances?type=micro_company").get_json()["instances"][0]["company"]["running"])
        self.assertTrue(self.post("/api/factory/instances/micro_company/%s/stop" % c, {}).get_json()["stopped"])
        t = self.post("/api/factory/types", {"key": "route kind", "title": "Route kind", "fields": [{"name": "who", "kind": "text", "required": True}]})
        self.assertEqual(t.status_code, 201, t.get_json())
        keys = [x["key"] for x in self.http.get("/api/factory/types").get_json()["types"]]
        self.assertEqual(keys[:4], ["micro_company", "platform_factory", "spatial_environment", "publishing_pipeline"])
        self.assertIn("custom_route_kind", keys)
        self.assertEqual(self.http.delete("/api/factory/types/custom_route_kind", headers=ADMIN).status_code, 200)

    def test_the_lab_through_the_routes_and_its_telemetry(self):
        r = self.post("/api/factory/lab/stress", {"type": "spatial_environment", "level": "light"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertTrue(r.get_json()["result"]["ok"])
        tel = self.http.get("/api/factory/telemetry").get_json()["telemetry"]
        self.assertEqual(tel[-1]["type"], "spatial_environment")
        self.assertEqual(self.post("/api/factory/lab/stress", {"type": "nope"}).status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=1)
