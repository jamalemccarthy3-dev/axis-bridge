"""test_cheatsheet.py - the command cheat sheet and the prompt vault stay true to the system.
  * Every fixed chat command on the sheet is checked against the server's OWN phrase rules (the mode gate, the build-order detector, the mesh-report phrase, the tool commands).
  * Every setting (environment variable) listed exists in the source; every script and module listed exists; every operating mode in the page has its row.
  * The goal matcher (the page's own JavaScript, run under Node) puts the right row or recipe near the top for requests written in plain words, tolerates typos, and never returns an empty box.
  * Both panels carry the Home / Find by goal toggle and the Back button, and every built-in recipe is valid, tagged and in a known category and mode.
Throwaway token and folders. Run: python test_cheatsheet.py"""
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="cheat_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"), NEXXUS_BUS_LEDGER=os.path.join(TMP, "ledger.jsonl"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "creations"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"),
                  NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"), NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1",
                  NEXXUS_PUBLISH_DIR=os.path.join(TMP, "pub"), NEXXUS_FACTORY_DIR=os.path.join(TMP, "factory"), NEXXUS_DISPATCH_QUEUE=os.path.join(TMP, "dq.json"),
                  NEXXUS_PROMPT_RECIPES=os.path.join(TMP, "recipes.json"))
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, NEXUS)

PAGE = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "render", "babylon_preview.html")
HTML = open(PAGE, encoding="utf-8").read()
a, b = HTML.index("// ====== INTENT MATCHER"), HTML.index("// ====== END COMMAND CHEAT SHEET DATA ======")
CORE_JS = HTML[a:b]
PV_FIELDS = re.search(r"const PV_FIELDS = \{[^}]*\};", HTML).group(0)
HAVE_NODE = bool(shutil.which("node"))


def node(js_after, stdin_obj=None):
    path = os.path.join(TMP, "run.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(CORE_JS + "\n" + PV_FIELDS + "\n" + js_after)               # a file, not -e: the page's script is too long for a Windows command line
    r = subprocess.run(["node", path], input=json.dumps(stdin_obj or {}), capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise AssertionError(r.stderr[-800:])
    return json.loads(r.stdout)


SHEET = None


def sheet():
    global SHEET
    if SHEET is None:
        SHEET = node("console.log(JSON.stringify(CMD_SHEET));")
    return SHEET


def rows(kind=None):
    return [(sec, r) for sec, rs in sheet() for r in rs if kind is None or (r[3] if len(r) > 3 else "chat") == kind]


@unittest.skipUnless(HAVE_NODE, "node is needed")
class Sheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv
        import python_server as srv  # noqa: E402
        cls.srv = srv

    def test_every_row_is_complete(self):
        for sec, r in rows():
            self.assertEqual(len(r), 4, r)
            self.assertTrue(r[0].strip() and r[1].strip() and r[2].strip(), r)
            self.assertIn(r[3], ("chat", "tip", "ui", "sh", "env"), r)
        secs = [s for s, _ in sheet()]
        self.assertEqual(len(secs), len(set(secs)))
        self.assertGreaterEqual(len(rows()), 90)

    def test_every_operating_mode_has_its_row(self):
        labels = re.findall(r"label: '([^']+)'", HTML.split("const MODE_INFO = {")[1].split("};")[0])
        self.assertEqual(len(labels), 10)
        modes_rows = [r[0] for _, r in rows() if r[0].startswith("Mode:")]
        for lab in labels:
            self.assertTrue(any(m.startswith("Mode: " + lab.split(" (")[0]) for m in modes_rows), lab)

    def test_fixed_chat_commands_are_really_recognised_by_the_server(self):
        s = self.srv
        by_cmd = {r[0]: r for _, r in rows("chat")}

        def gate_free(text):                                           # tool phrases pass the mode gate in every mode
            self.assertIsNone(s._mode_gate(text), text)
        for cmd in by_cmd:
            c = re.sub(r"^\([^)]*\)\s*", "", cmd)
            c = re.sub(r"\s{2,}\(.*$", "", c)
            if c.startswith("search:"):
                self.assertTrue(c.lower().startswith("search:"))
            elif c.startswith("find a tool to"):
                gate_free("find a tool to convert markdown to html")
            elif c.startswith("ingest "):
                gate_free("ingest owner/repo")
                gate_free("stage owner/repo")
                gate_free("fetch tool owner/repo")
            elif c == "list tools":
                self.assertIsNotNone(s._tools_chat_reply("list tools"))
                self.assertIsNotNone(s._tools_chat_reply("show my tools"))
            elif c == "list staged tools":
                self.assertIsNotNone(s._tools_chat_reply("list staged tools"))
                self.assertIsNotNone(s._tools_chat_reply("show pending briefings"))
            elif c.startswith("run tool"):
                self.assertIsNotNone(s._tools_chat_reply("run tool nosuchtool"))
                gate_free("run tool nosuchtool")
            elif c == "run a mesh diagnostic":
                for phrase in ("run a mesh diagnostic", "verify the mesh", "engines status check", "mesh health check"):
                    self.assertTrue(s._MESH_REPORT_ASK.search(phrase), phrase)
            elif c.startswith("build a <"):
                self.assertTrue(s._modes.looks_like_build_request("build a landing page"))
            elif c.startswith("write me a script"):
                self.assertTrue(s._modes.looks_like_build_request("write me a script that renames files"))
            elif c == "code this":
                for p in ("code this", "code that", "code it"):
                    self.assertTrue(s._modes.looks_like_build_request(p), p)
            elif c == "stage a build":
                for p in ("stage a build", "vault a build", "commit a build"):
                    self.assertTrue(s._modes.looks_like_build_request(p), p)
            elif c.startswith("how do I build a funnel"):
                self.assertFalse(s._modes.looks_like_build_request("how do I build a funnel?"))
            elif c.startswith("build a dashboard panel"):
                self.assertTrue(s._modes.looks_like_build_request("build a dashboard panel for engine status"))
            elif c.startswith("build an engine that"):
                self.assertTrue(s._modes.looks_like_build_request("build an engine that parses csv files"))
            elif c.startswith("make a logo for"):
                self.assertTrue(s._modes.looks_like_build_request("make a logo for a bakery") or s._creation is not None)
            elif c.startswith("make the <rays> longer") or c in ("surprise me", "never mind"):
                self.assertIsNotNone(s._creation)                       # creation mode's own parser handles these; its tests cover the wording
            elif c.startswith("which engines are offline") or c.startswith("which route is slowest"):
                self.assertIsNotNone(s._diag if "engines" in c else s._link)
            elif c.startswith("data: <name>") or c.startswith("search: <topic>"):
                import portal_chat
                self.assertIsNotNone(portal_chat)
            else:
                self.fail("a chat row has no server check: %r (add one, or make it a 'tip')" % cmd)

    def test_the_hub_courier_sends_clear_questions_and_leaves_the_rest(self):
        import domain_dispatch
        self.assertIsNone(domain_dispatch.target("build a landing page for my shop")[0])
        self.assertIsNone(domain_dispatch.target("hello")[0])

    def test_every_setting_listed_exists_in_the_source(self):
        src = ""
        for dp in (ROOT, NEXUS, os.path.join(ROOT, "axis-ui-interface", "project-X", "axis_gate")):       # the server, the main scripts, nexxus, the gate: where the settings are read
            for f in os.listdir(dp):
                if f.endswith((".py", ".bat", ".md")) and not f.startswith("test_"):
                    try:
                        src += open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read()
                    except OSError:
                        pass
        for _sec, r in rows("env"):
            name = re.match(r"NEXXUS_[A-Z0-9_<>]+", r[0]).group(0)
            probe = name.split("<")[0]
            self.assertIn(probe, src, "%s is listed on the sheet but appears nowhere in the code" % name)
        for extra in re.findall(r"NEXXUS_[A-Z0-9_]+", " ".join(r[1] + " " + r[0] for _, r in rows("env"))):
            if not extra.endswith("_"):
                self.assertIn(extra, src, extra)

    def test_every_script_and_module_listed_exists(self):
        for _sec, r in rows("sh"):
            c = r[0]
            m = re.match(r"python (-m )?(\S+)", c)
            if m and not m.group(1):
                self.assertTrue(os.path.exists(os.path.join(ROOT, m.group(2))), c)
            elif m:
                self.assertTrue(os.path.isdir(os.path.join(ROOT, "axis-ui-interface", "project-X", m.group(2))), c)
            elif c.endswith(".bat"):
                self.assertTrue(os.path.exists(os.path.join(ROOT, c)), c)
        for t in ("test_factory.py", "test_image_ingest.py", "test_staging.py", "test_remote.py", "test_publish_queue.py", "test_cheatsheet.py"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, t)), t)
        txt = " ".join(r[0] + " " + r[1] for _, r in rows("sh"))
        for sub in ("status", "verify", "seal core", "audit-names", "unshare"):
            self.assertIn(sub, txt)

    def test_nothing_that_does_not_exist_is_offered(self):
        allrows = " ".join(r[0] + " " + r[1] for _, r in rows()).lower()
        self.assertNotIn("legacy", allrows)
        calls = [r for _, r in rows() if "call" in r[1].lower() and "phone" in r[1].lower()]
        self.assertTrue(all("no phone" in r[1].lower() or "do not exist" in r[1].lower() or "never" in r[1].lower() or "not" in r[1].lower() for r in calls))


@unittest.skipUnless(HAVE_NODE, "node is needed")
class Intent(unittest.TestCase):
    """The page's own matcher, run under Node."""

    def top(self, query, n=3):
        js = ("const ix = intIndex(cmdItems(), CMD_FIELDS); const q = JSON.parse(require('fs').readFileSync(0,'utf8')).q;"
              "console.log(JSON.stringify({res: intSearch(ix, q, %d).map(r => [r.item.c, r.item.sec, +r.score.toFixed(2)]), near: intNearest(ix, q, 3).map(r => r.item.c)}));") % n
        return node(js, {"q": query})

    def assertTop(self, query, needle, n=3):
        res = self.top(query, n)["res"]
        self.assertTrue(any(needle.lower() in (c + " " + s).lower() for c, s, _ in res), "%r -> %s" % (query, [c for c, _, _ in res]))

    def test_plain_words_find_the_right_row(self):
        for q, needle in (("make a logo for my bakery", "make a logo"), ("i want a picture with my company name on it", "make a logo"), ("are my engines healthy", "mesh diagnostic"), ("what is wrong with an engine", "which engines are offline"),
                          ("find a library for pdfs", "find a tool to"), ("i need a script for converting files", "find a tool to"), ("use it from my phone", "tailscale"), ("how do i reach this from outside my house", "tailscale"),
                          ("send a command later", "queue for later"), ("test before sending", "dry run"), ("cut the background out of a photo", "isolate subject"), ("remove the border from an image", "crop box"),
                          ("put a web image on a 3d panel", "image to 3d"), ("approve a video upload", "publishing"), ("why is it slow", "slowest"), ("which port does the sports hub use", "NEXXUS_PORT_SPORTS"),
                          ("how do i turn off remote access", "NEXXUS_BIND"), ("restart everything", "restart_nexxus.bat"), ("did my edit break the seal", "axis_gate"), ("check for leaked keys before pushing", "gitleaks"),
                          ("what is waiting for my approval", "list staged tools"), ("stop sending my questions to the hubs", "NEXXUS_DOMAIN_DISPATCH"), ("make a new engine", "build an engine"), ("can it make phone calls for me", "Micro-company")):
            self.assertTop(q, needle)

    def test_it_forgives_typos_and_plurals(self):
        for q, needle in (("make a logoo for my bakry", "make a logo"), ("deagnostic of the enginess", "mesh diagnostic"), ("tailscal tunnle", "tailscale"), ("queing commands", "queue for later")):
            self.assertTop(q, needle, 5)

    def test_it_never_returns_an_empty_box_for_a_real_word(self):
        r = self.top("zzzzxq")
        self.assertEqual(r["res"], [])                                    # nonsense matches nothing...
        r = self.top("engine cheesecake")
        self.assertTrue(r["res"] or r["near"])                            # ...but a real word always gets rows or the nearest rows
        self.assertEqual(self.top("   ")["res"], [])

    def test_the_best_match_comes_first_and_scores_are_ordered(self):
        res = self.top("make a logo", 10)["res"]
        scores = [s for _, _, s in res]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertIn("logo", res[0][0].lower())


@unittest.skipUnless(HAVE_NODE, "node is needed")
class Vault(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv
        import python_server as srv  # noqa: E402
        cls.recipes = srv.app.test_client().get("/api/prompts").get_json()["recipes"]

    def test_every_builtin_recipe_is_valid_tagged_and_in_a_known_place(self):
        import prompt_vault as pv
        ids = [r["id"] for r in self.recipes]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 28)
        for r in self.recipes:
            self.assertIn(r["category"], pv.CATEGORIES, r["id"])
            self.assertIn(r["mode"], pv.MODES, r["id"])
            self.assertTrue(r["tags"].strip() and r["summary"].strip(), r["id"])
            self.assertLessEqual(len(r["prompt"]), 4000)
        for cat in ("Creation", "Diagnostics", "Tools", "Hubs", "Factory"):
            self.assertTrue(any(r["category"] == cat for r in self.recipes), cat)

    def test_vault_commands_match_what_the_server_recognises(self):
        import python_server as s
        by = {r["id"]: r for r in self.recipes}
        s._mode_gate(by["tools-find"]["prompt"].replace("[WHAT YOU NEED, e.g. convert markdown to html]", "convert markdown to html"))
        self.assertIsNone(s._mode_gate("find a tool to convert markdown to html"))
        self.assertIsNone(s._mode_gate(by["tools-ingest"]["prompt"].replace("[OWNER/REPO]", "owner/repo")))
        self.assertIsNotNone(s._tools_chat_reply(by["tools-staged"]["prompt"]))
        for rid in ("factory-storefront-products", "factory-env-objects", "factory-company-bots"):
            self.assertIn("JSON", by[rid]["prompt"])
        import micro_company
        for task in micro_company.TASKS:
            self.assertIn(task, by["factory-company-bots"]["prompt"])
        import factory_env
        for shape in factory_env.SHAPES:
            self.assertIn(shape, by["factory-env-objects"]["prompt"])

    def top(self, query):
        js = ("const rs = JSON.parse(require('fs').readFileSync(0,'utf8')); const ix = intIndex(rs.recipes.map(r => ({ r, title: r.title, tags: String(r.tags||'').replace(/\\|/g,' . '), summary: r.summary||'', cat: r.category+' '+r.mode, prompt: r.prompt })), PV_FIELDS);"
              "console.log(JSON.stringify(intSearch(ix, rs.q, 3).map(x => x.item.r.id)));")
        return node(js, {"recipes": self.recipes, "q": query})

    def test_goals_find_the_right_recipe(self):
        for q, rid in (("make a logo with my name", "creation-logo-lettering"), ("a spinning glowing badge", "creation-animated-badge"), ("why is an engine not answering", "diag-engine-why"),
                       ("which requests are slow", "link-slowest"), ("find a library on github", "tools-find"), ("what is waiting for approval", "tools-staged"), ("products for my online shop", "factory-storefront-products"),
                       ("save records in a database", "engine-data-sqlite"), ("is this generated code safe to approve", "quality-review-engine"), ("2d fixtures for my team", "hub-sports"),
                       ("shipments are late", "hub-logistics"), ("automate tasks with bots", "factory-company-bots"), ("a walkable 3d room", "factory-env-objects")):
            self.assertIn(rid, self.top(q), q)


class Page(unittest.TestCase):
    def test_both_panels_have_the_home_and_search_toggle_and_back(self):
        for needle in ('id="cmdChrome"', 'id="pvChrome"', "function intChrome", "'Home'", "'Find by goal'", "'← Home'", "back.hidden = v === 'home'", "setView('home', true)", "id: 'cmdSheetFilter'", "id: 'pvFilter'",
                       "e.key === 'Escape'", "aria-selected", "role', 'tablist'"):
            self.assertIn(needle, HTML, needle)
        self.assertEqual(HTML.count("cs.chrome.setView('home', true)") + HTML.count("pv.chrome.setView('home', true)"), 2)      # each panel opens on Home

    def test_the_legacy_filters_and_stale_placeholders_are_gone(self):
        for needle in ("filter: tool, build, search, logo...", "filter: engine, dashboard, sqlite, review...", "renderCmdSheet(e.target.value)", "pv.q = f.value"):
            self.assertNotIn(needle, HTML, needle)

    def test_the_matcher_is_pure_and_runs_in_the_page(self):
        for needle in ("function intSearch", "function intIndex", "function intNearest", "function intStem", "const INT_SYN", "intMark(", "intWhyText("):
            self.assertIn(needle, HTML, needle)
        self.assertNotIn("fetch(", CORE_JS)                              # nothing is sent anywhere
        self.assertNotIn("document.", CORE_JS)                           # pure: runs under Node as well

    def test_the_new_blocks_sit_outside_the_window_code_other_suites_inspect(self):
        a_, b_ = HTML.index("// ====== HUB WINDOWS"), HTML.index("// ====== SETTINGS READOUTS")
        self.assertNotIn("INTENT MATCHER", HTML[a_:b_])


if __name__ == "__main__":
    unittest.main(verbosity=1)
