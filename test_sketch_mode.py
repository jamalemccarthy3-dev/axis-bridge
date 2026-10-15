"""test_sketch_mode.py - Sketch Mode and the dashboard's core drive.

Engine: the arc Domain -> Working hypothesis -> Deep-dive -> Final thesis moves only when the user moves it; the model's closing questions ("are we finished?") are stripped before they are shown; pills change with
the stage; the board keeps the user's words apart from the model's unverified analysis; the thesis packages into a blueprint with hashes; Build is refused without a thesis; sketches survive a restart.
Core drive: the layout is created by the dashboard, syncs are atomic and hash-chained, names cannot leave the mount, and a missing D: is reported, not hidden.
Server: Sketch mode halts nothing, chat turns come back with the board view and the domain question, Build files the blueprint in the mount and returns the order for a build room, and the other modes still
gate build orders. Throwaway folders; the model is replaced by a fake. Run: python test_sketch_mode.py"""
import atexit
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="sketch_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"), NEXXUS_BUS_LEDGER=os.path.join(TMP, "ledger.jsonl"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "creations"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"), NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"),
                  NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1", NEXXUS_PUBLISH_DIR=os.path.join(TMP, "pub"), NEXXUS_FACTORY_DIR=os.path.join(TMP, "factory"),
                  NEXXUS_CAMPAIGN_DIR=os.path.join(TMP, "campaigns"), NEXXUS_HOME=os.path.join(TMP, "mount"), NEXXUS_DISABLE_SLAE_LOOP="1", NEXXUS_VAULT_DIR=os.path.join(TMP, "vault"),
                  NEXXUS_DAEMON_STATE_DIR=os.path.join(TMP, "dstate"), NEXXUS_DAEMON_LOG_DIR=os.path.join(TMP, "dlogs"), NEXXUS_DAEMON_ARCHIVE_DIR=os.path.join(TMP, "darch"))
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, NEXUS)
import core_drive  # noqa: E402
import mode_policy  # noqa: E402
import sketch_mode as sm  # noqa: E402

FAKE = lambda p: "Here is a sharp point about it. Are we finished? Another angle worth testing. Let me know if you need anything else."
HYP = "I think small clinics need simple online booking because no-shows cost them money every week"


def fresh(name, llm=FAKE):
    return sm.SketchEngine(Path(TMP) / name, llm=llm)


def walk_to_thesis(e):
    e.handle("Software & technology")
    e.handle(HYP)
    e.handle("The buyer is the practice manager at clinics with 2 to 5 doctors")
    e.handle("What would prove this wrong?")
    return e.handle("draft the thesis")


class Arc(unittest.TestCase):
    def test_entry_asks_the_domain_with_options_and_nothing_else(self):
        e = fresh("a1")
        r = e.handle("")
        self.assertEqual(r["view"]["stage"], "domain")
        self.assertEqual(r["question"]["prompt"], "What domain are we sketching in?")
        self.assertEqual([o["label"] for o in r["question"]["options"]], sm.DOMAINS)
        self.assertNotIn("?", r["reply"].replace("What domain do you want to think in?", ""))     # one question only, the domain
        self.assertIn("nothing to finish", r["reply"])

    def test_the_four_stages_move_only_when_the_user_moves_them(self):
        e = fresh("a2")
        e.handle("")
        self.assertEqual(e.handle("Marketing & growth")["view"]["stage"], "hypothesis")
        self.assertEqual(e.handle("hmm")["view"]["stage"], "hypothesis")                              # too thin to be a hypothesis: stays, asks for more
        self.assertEqual(e.handle(HYP)["view"]["stage"], "deep_dive")
        for i in range(6):
            self.assertEqual(e.handle("angle %d: what if the clinics are chains?" % i)["view"]["stage"], "deep_dive")   # never drifts to the thesis by itself
        self.assertEqual(e.handle("draft the thesis")["view"]["stage"], "thesis")
        self.assertEqual(e.handle("go deeper")["view"]["stage"], "deep_dive")
        self.assertEqual(e.handle("Back to the hypothesis: I want to change it.")["view"]["stage"], "hypothesis")
        self.assertEqual(e.handle("change the domain")["view"]["stage"], "domain")

    def test_a_greeting_is_not_taken_as_the_domain(self):
        e = fresh("a3")
        r = e.handle("hello")
        self.assertEqual(r["view"]["stage"], "domain")
        self.assertIn("question", r)
        self.assertIsNone(e.current()["domain"])

    def test_closing_questions_are_stripped_from_every_model_reply(self):
        e = fresh("a4")
        replies = [e.handle("Software & technology")["reply"], e.handle(HYP)["reply"], e.handle("who pays?")["reply"], e.handle("draft the thesis")["reply"]]
        blob = " ".join(replies).lower()
        for banned in ("are we finished", "let me know if", "anything else", "are we done", "wrap"):
            self.assertNotIn(banned, blob)
        self.assertIn("another angle worth testing", blob)                                                # the useful part survives
        t = strip = sm.strip_closers("Good point.\nIs there anything else? Think about pricing.\nShall we wrap up?")
        self.assertEqual(t, "Good point.\nThink about pricing.")
        self.assertEqual(sm.strip_closers("Are we finished?"), "")

    def test_pills_follow_the_stage_and_never_offer_to_finish(self):
        e = fresh("a5")
        e.handle("")
        ids = lambda: [p["id"] for p in e.view(e.current())["pills"]]
        self.assertTrue(all(i.startswith("d") for i in ids()))
        e.handle("Finance & operations")
        self.assertIn("h_suggest", ids())
        e.handle(HYP)
        self.assertIn("a_stress", ids())
        self.assertIn("x_unit", ids())                                                                     # the domain adds its own pill
        self.assertNotIn("m_thesis", ids())                                                               # offered only after two of YOUR findings
        e.handle("finding one"); e.handle("finding two")
        self.assertIn("m_thesis", ids())
        every = " ".join(p["label"] + " " + p["text"] for p in e.view(e.current())["pills"]).lower()
        for banned in ("finish", "done", "wrap", "conclude", "build it"):
            self.assertNotIn(banned, every)
        e.handle("draft the thesis")
        self.assertIn("t_tight", ids())
        self.assertTrue(all(p["kind"] in ("ask", "move", "domain") and p["text"] for p in e.view(e.current())["pills"]))

    def test_a_clicked_pill_is_just_a_message_and_gets_real_analysis(self):
        seen = []
        e = fresh("a6", llm=lambda p: seen.append(p) or "Analysis of the point.")
        e.handle("Business & products"); e.handle(HYP)
        pill = next(p for p in e.view(e.current())["pills"] if p["id"] == "a_wrong")
        r = e.handle(pill["text"])
        self.assertEqual(r["reply"], "Analysis of the point.")
        self.assertIn("small clinics need simple online booking", seen[-1])                                # the board is in front of the model
        self.assertIn("Never invent statistics", seen[-1])

    def test_without_a_model_it_says_so_instead_of_pretending(self):
        e = fresh("a7", llm=None)
        e.handle("Creative & media"); e.handle(HYP)
        r = e.handle("who is the audience?")
        self.assertIn("not reachable", r["reply"])
        self.assertEqual(len([n for n in e.current()["notes"] if n["by"] == "you"]), 3)                  # everything the user wrote is still kept
        self.assertEqual([n for n in e.current()["notes"] if n["by"] == "nexxus"], [])

    def test_a_failing_model_does_not_break_the_workshop(self):
        def boom(p):
            raise RuntimeError("down")
        e = fresh("a8", llm=boom)
        e.handle("Business & products"); e.handle(HYP)
        self.assertEqual(e.handle("next thought")["view"]["stage"], "deep_dive")


class Thesis(unittest.TestCase):
    def test_the_thesis_keeps_your_words_apart_from_the_models(self):
        e = fresh("t1")
        r = walk_to_thesis(e)
        t = e.current()["thesis"]
        self.assertEqual(r["view"]["stage"], "thesis")
        self.assertIn("The buyer is the practice manager", t["your_findings"][0])
        self.assertIn("What would prove this wrong?", t["open_questions"])
        self.assertTrue(t["model_analysis_unverified"])
        self.assertTrue(all("practice manager" not in a for a in t["model_analysis_unverified"]))
        self.assertIn("edit before building", t["source"])
        self.assertTrue(r["view"]["can_build"])

    def test_without_a_model_the_thesis_is_your_hypothesis_as_stated(self):
        e = fresh("t2", llm=None)
        e.handle("Software & technology"); e.handle(HYP)
        e.handle("draft the thesis")
        t = e.current()["thesis"]
        self.assertEqual(t["source"], "your hypothesis, as stated")
        self.assertIn(HYP, t["statement"])

    def test_no_thesis_without_a_hypothesis_and_new_input_after_the_thesis_invalidates_it(self):
        e = fresh("t3")
        e.handle("Software & technology")
        self.assertIn("no working hypothesis", e.draft_thesis()["reply"])
        e.handle(HYP)
        e.handle("draft the thesis")
        self.assertTrue(e.current()["thesis"])
        e.handle("one more thing I just thought of")
        self.assertIsNone(e.current()["thesis"])                                                           # the board moved: redraft when you ask
        self.assertFalse(e.view(e.current())["can_build"])


class Build(unittest.TestCase):
    def test_build_is_refused_without_a_thesis_and_for_unknown_rooms(self):
        e = fresh("b1")
        e.handle("Software & technology"); e.handle(HYP)
        with self.assertRaises(ValueError):
            e.package(e.current()["id"], "engine_build", sync=False)
        walk_to_thesis(fresh("b1x"))
        e2 = fresh("b1y")
        walk_to_thesis(e2)
        with self.assertRaises(ValueError):
            e2.package(e2.current()["id"], "demolition", sync=False)
        with self.assertRaises(KeyError):
            e2.package("sk-0123456789", "sandbox", sync=False)
        with self.assertRaises((KeyError, ValueError)):
            e2.package("../../etc/passwd", "sandbox", sync=False)

    def test_the_blueprint_is_packaged_hashed_and_filed_in_the_core_drive(self):
        e = fresh("b2")
        walk_to_thesis(e)
        sid = e.current()["id"]
        res = e.package(sid, "engine_build")
        self.assertEqual(res["room"], "engine_build")
        self.assertTrue(res["order"].startswith("Build an engine from this approved sketch blueprint"))
        self.assertTrue(mode_policy.looks_like_build_request(res["order"]))                                 # a build room reads it as the order it is
        folder = Path(res["path"])
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["MANIFEST.json", "blueprint.json", "blueprint.md", "build_order.txt"])
        man = json.loads((folder / "MANIFEST.json").read_text())
        import hashlib
        for name, sha in man["files"].items():
            self.assertEqual(hashlib.sha256((folder / name).read_bytes()).hexdigest(), sha)
        bp = json.loads((folder / "blueprint.json").read_text())
        self.assertEqual(bp["hypothesis"], HYP)
        self.assertEqual(bp["thesis"]["statement"], e.current()["thesis"]["statement"])
        self.assertIn("unverified", (folder / "blueprint.md").read_text())
        self.assertIn(os.environ["NEXXUS_HOME"], res["path"])                                              # inside the dashboard's mount, not somewhere else
        self.assertEqual(core_drive.verify_index()["ok"], True)
        self.assertEqual(core_drive.index()[-1]["kind"], "builds")
        self.assertEqual(e.current()["built"]["room"], "engine_build")
        self.assertEqual(os.listdir(tempfile.gettempdir()).count("sketchpkg_leftover"), 0)

    def test_sketches_survive_a_restart_and_resume(self):
        a = fresh("b3")
        a.handle("Software & technology"); a.handle(HYP)
        b = sm.SketchEngine(Path(TMP) / "b3", llm=FAKE)
        s = b.current()
        self.assertEqual((s["stage"], s["hypothesis"]), ("deep_dive", HYP))
        self.assertEqual(len(b.list()), 1)
        b.handle("new sketch")
        self.assertEqual(len(b.list()), 2)
        self.assertEqual(b.resume(a.current()["id"])["hypothesis"], HYP)


class CoreDrive(unittest.TestCase):
    def test_layout_sync_chain_and_safety(self):
        root = Path(TMP) / "cd"
        lay = core_drive.ensure_layout(root)
        self.assertEqual(set(lay), set(core_drive.KINDS))
        self.assertTrue(all(Path(p).is_dir() for p in lay.values()))
        src = Path(TMP) / "src.txt"
        src.write_text("hello")
        a = core_drive.sync("documents", "doc1.txt", src, root)
        self.assertEqual(Path(a["path"]).read_text(), "hello")
        src.write_text("changed")
        core_drive.sync("documents", "doc1.txt", src, root)                                                   # same name: replaced atomically
        self.assertEqual((root / "data" / "documents" / "doc1.txt").read_text(), "changed")
        self.assertEqual(core_drive.verify_index(root), {"ok": True, "entries": 2, "broken_at": None})
        for bad in ("../x", "a/b", "..", ".hidden", ""):
            with self.assertRaises(ValueError):
                core_drive.sync("documents", bad, src, root)
        with self.assertRaises(ValueError):
            core_drive.sync("nowhere", "x", src, root)
        with self.assertRaises(FileNotFoundError):
            core_drive.sync("documents", "x", Path(TMP) / "nope", root)
        idx = root / "data" / "mount_index.jsonl"
        lines = idx.read_text().splitlines()
        lines[0] = lines[0].replace('"documents"', '"state"')
        idx.write_text("\n".join(lines) + "\n")
        self.assertFalse(core_drive.verify_index(root)["ok"])                                                 # an edited history is found

    def test_folders_sync_whole_and_replace_cleanly(self):
        root = Path(TMP) / "cd2"
        d = Path(TMP) / "srcdir"
        (d / "sub").mkdir(parents=True, exist_ok=True)
        (d / "a.txt").write_text("a")
        (d / "sub" / "b.txt").write_text("b")
        r = core_drive.sync("modules", "mod1", d, root)
        self.assertEqual(sorted(r["files"]), ["a.txt", "sub/b.txt"])
        (d / "a.txt").unlink()
        r = core_drive.sync("modules", "mod1", d, root)
        self.assertEqual(sorted(r["files"]), ["sub/b.txt"])                                                    # no stale file left from the old version
        self.assertEqual([p.name for p in (root / "data" / "modules").iterdir() if p.name.startswith(".")], [])

    def test_a_missing_drive_is_reported_in_plain_words(self):
        h = core_drive.home()
        self.assertEqual(str(h["path"]), os.environ["NEXXUS_HOME"])                                            # the env override wins
        st = core_drive.status()
        self.assertIn("builds", st["areas"])
        os.environ.pop("NEXXUS_HOME")
        try:
            h = core_drive.home()
            if os.name == "nt" and not os.path.exists("D:\\"):
                self.assertTrue(h["used_fallback"])
                self.assertIn("nexxus_data", str(h["path"]))
                self.assertIn("is not on this machine", core_drive.status(root=Path(TMP) / "cd3")["note"])
        finally:
            os.environ["NEXXUS_HOME"] = os.path.join(TMP, "mount")


class Policy(unittest.TestCase):
    def test_sketch_halts_nothing_and_other_modes_still_gate(self):
        st = mode_policy.ModeState()
        st.set("sketch")
        for text in ("build me a landing page for a bakery", "write the code for a booking app", "create a dashboard"):
            self.assertIsNone(st.gate(text), text)
        self.assertFalse(mode_policy.MODES["sketch"]["can_build"])
        st.set("conversation")
        self.assertIsNotNone(st.gate("build me a landing page for a bakery"))
        self.assertIn("sketch", [m["mode"] for m in st.snapshot()["available"]])


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv
        import python_server as srv  # noqa: E402
        cls.srv = srv
        cls.http = srv.app.test_client()
        cls._orig_llm = srv._sketch.llm
        srv._sketch.llm = FAKE

    @classmethod
    def tearDownClass(cls):
        srv._sketch.llm = cls._orig_llm
        srv._mode_state.set("conversation")

    def say(self, t):
        return self.http.post("/command-dispatch", json={"command": t}).get_json()

    def test_chat_turns_in_sketch_mode(self):
        self.http.post("/api/mode", json={"mode": "sketch"})
        srv._sketch.new()
        r = self.say("build me a landing page")                      # even a build-sounding line is just ideation here
        self.assertNotIn("halted", r)
        self.assertEqual(r["sketch"]["stage"], "domain")
        r = self.say("")  if False else self.say("start")            # "start" is a greeting, not a domain
        self.assertIn("question", r)
        r = self.say("Software & technology")
        self.assertEqual(r["sketch"]["stage"], "hypothesis")
        self.assertEqual(r["sketch"]["domain"], "Software & technology")
        self.assertTrue(r["sketch"]["pills"])
        r = self.say(HYP)
        self.assertEqual(r["sketch"]["stage"], "deep_dive")
        self.assertNotIn("are we finished", r["response"].lower())

    def test_state_thesis_build_and_resume_routes(self):
        self.http.post("/api/mode", json={"mode": "sketch"})
        srv._sketch.new()
        self.say("Business & products"); self.say(HYP); self.say("a finding"); self.say("another finding")
        st = self.http.get("/api/sketch").get_json()
        self.assertEqual(st["view"]["stage"], "deep_dive")
        r = self.http.post("/api/sketch/build", json={"room": "engine_build"})
        self.assertEqual(r.status_code, 400)                                                                    # no thesis yet
        self.assertIn("thesis", r.get_json()["error"])
        t = self.http.post("/api/sketch/thesis", json={}).get_json()
        self.assertEqual(t["view"]["stage"], "thesis")
        b = self.http.post("/api/sketch/build", json={"room": "sandbox"})
        self.assertEqual(b.status_code, 200, b.get_json())
        j = b.get_json()["build"]
        self.assertEqual(j["room"], "sandbox")
        self.assertTrue(Path(j["path"], "blueprint.json").is_file())
        self.assertIn(os.environ["NEXXUS_HOME"], j["path"])
        self.assertEqual(self.http.post("/api/sketch/build", json={"room": "nonsense"}).status_code, 400)
        self.assertEqual(self.http.post("/api/sketch/explode", json={}).status_code, 400)
        n = self.http.post("/api/sketch/new", json={}).get_json()
        self.assertEqual(n["view"]["stage"], "domain")
        rs = self.http.post("/api/sketch/resume", json={"id": st["view"]["id"]}).get_json()
        self.assertEqual(rs["view"]["hypothesis"], HYP)
        self.assertEqual(self.http.post("/api/sketch/resume", json={"id": "nope"}).status_code, 400)

    def test_mutating_sketch_routes_are_locked_from_other_devices(self):
        r = self.http.post("/api/sketch/build", json={"room": "sandbox"}, environ_overrides={"REMOTE_ADDR": "100.99.99.99"})
        self.assertIn(r.status_code, (401, 403))
        r = self.http.post("/api/sketch/new", json={}, headers={"Origin": "https://evil.example"})
        self.assertIn(r.status_code, (401, 403))

    def test_core_drive_and_daemon_and_slae_routes(self):
        d = self.http.get("/api/core/drive").get_json()
        self.assertEqual(d["status"], "success")
        self.assertIn("builds", d["areas"])
        self.assertTrue(d["index"]["ok"])
        h = self.http.get("/api/daemon/health").get_json()
        self.assertEqual(h["status"], "success")
        self.assertIn(h["health"]["overall"], ("green", "yellow", "red"))
        self.assertEqual(self.http.post("/api/daemon/command", json={"action": "restart", "service": "ollama"}).status_code, 401)
        admin = {"X-Nexxus-Admin-Token": "throwaway-admin"}
        self.assertEqual(self.http.post("/api/daemon/command", json={"action": "format_c"}, headers=admin).status_code, 400)
        r = self.http.post("/api/daemon/command", json={"action": "restart", "service": "ollama"}, headers=admin)
        self.assertEqual(r.status_code, 409)                                                                    # no daemon running in this test: it says so, it does not start one
        self.assertIn("not running", r.get_json()["detail"])
        s = self.http.get("/api/slae/stats").get_json()
        self.assertEqual(s["status"], "success")
        for k in ("total_resolved", "active_rules_count", "active_rules"):
            self.assertIn(k, s)

    def test_a_hand_off_order_is_not_hijacked_by_the_mesh_report_matcher(self):
        e = fresh("hand")
        e.handle("Software & technology"); e.handle(HYP)
        e.llm = lambda p: "A booking engine for clinics; the first test is five real practices this week; the biggest risk is adoption."
        e.handle("draft the thesis")
        order = e.package(e.current()["id"], "engine_build", sync=False)["order"]
        self.assertRegex(order.lower(), r"engine.*test")                                                   # exactly the words that used to trip the matcher
        self.assertIsNone(srv._mesh_report_reply(order))
        self.assertIsNotNone(srv._MESH_REPORT_ASK.search(order))                                            # the regex alone WOULD have matched: only the hand-off prefix exempts it
        self.assertIsNotNone(srv._MESH_REPORT_ASK.search("run the engine verification report"))            # and it is unchanged for real requests (not executed here: it runs the diagnostic)

    def test_other_modes_are_unchanged(self):
        self.http.post("/api/mode", json={"mode": "conversation"})
        r = self.say("build me a landing page for a bakery")
        self.assertTrue(r.get("halted"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
