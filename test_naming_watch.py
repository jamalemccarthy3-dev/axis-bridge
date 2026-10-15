"""test_naming_watch.py - explicit naming + adoption, and the read-only commercial watch (unit level, then through the real server routes).
Run: python test_naming_watch.py"""
import atexit
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest

TMP = tempfile.mkdtemp(prefix="naming_watch_")
atexit.register(shutil.rmtree, TMP, True)
WATCHED = os.path.join(TMP, "sellable_storefront")                         # stands in for a commercial-grade folder
os.makedirs(os.path.join(WATCHED, "assets"))
open(os.path.join(WATCHED, "app.py"), "w").write("print('sellable core')\n")
open(os.path.join(WATCHED, "assets", "logo.svg"), "w").write("<svg/>")
WATCH_FILE = os.path.join(TMP, "commercial_watch.json")
json.dump({"watch": [{"name": "storefront-core", "path": WATCHED}]}, open(WATCH_FILE, "w"))
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "staging", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "ledger.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=WATCH_FILE, NEXXUS_CREATIONS_DIR=os.path.join(TMP, "creations"), NEXXUS_DISABLE_AUTOSCHEDULER="1")
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
ROOT = os.path.dirname(os.path.abspath(__file__))
NX = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, NX)

import creations_vault  # noqa: E402
import engine_build  # noqa: E402
import naming  # noqa: E402
import vital_watch  # noqa: E402
import python_server as srv  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>'


def snapshot(folder):
    out = {}
    for dp, _d, fs in os.walk(folder):
        for f in fs:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, folder)] = (os.path.getsize(p), os.stat(p).st_mtime_ns, hashlib.sha256(open(p, "rb").read()).hexdigest())
    return out


class Naming(unittest.TestCase):
    def test_stand_ins_are_refused_and_real_names_pass(self):
        for bad in ("Untitled", "Untitled_Build", "output", "new file", "tmp123", "a3f9c2d1", "20261011-145012", "file1.png", "default", "asset 42", "my project", "something", ""):
            self.assertFalse(naming.check_name(bad)[0], bad)
        for good in ("red-fox-bakery-logo", "counts_words", "Neon coffee cup", "dragon-flying-castle-video", "storefront-core"):
            self.assertTrue(naming.check_name(good)[0], good)

    def test_names_come_from_the_request_never_from_a_default(self):
        self.assertEqual(naming.derive("a red fox logo for Bakery Co"), "red-fox-bakery-co-logo")
        self.assertIsNone(naming.derive("make a new thing"))
        self.assertEqual(naming.explicit("Untitled", hint="a neon coffee cup animation", sep=" "), "neon coffee cup animation")
        with self.assertRaises(naming.NamingError):
            naming.explicit("Untitled", hint="make something")
        self.assertEqual(naming.file_name("graphic.svg", "red-fox-logo"), "red-fox-logo.svg")
        self.assertEqual(naming.file_name("index.html", "neon-cup"), "neon-cup.html")
        self.assertEqual(naming.file_name("fox-front.png", "x-logo"), "fox-front.png")

    def test_adoption_tags_a_folder_and_the_audit_finds_orphans(self):
        root = os.path.join(TMP, "outputs")
        for n in ("tagged-thing-one", "orphan-thing-two", "temp"):
            os.makedirs(os.path.join(root, n))
            open(os.path.join(root, n, "a.txt"), "w").write(n)
        with self.assertRaises(naming.NamingError):
            naming.adopt(os.path.join(root, "temp"), "temp", "x", "me")
        tag = naming.adopt(os.path.join(root, "tagged-thing-one"), "tagged-thing-one", "demo", "test", request="a demo")
        self.assertEqual(tag["files"][0]["sha256"], hashlib.sha256(b"tagged-thing-one").hexdigest())
        a = naming.audit(root)
        self.assertEqual((a["tagged"], sorted(a["orphans"])), (1, ["orphan-thing-two", "temp"]))
        self.assertEqual([s["name"] for s in a["stand_in_names"]], ["temp"])

    def test_creations_are_named_for_what_they_are_and_tagged(self):
        v = creations_vault.CreationsVault(os.path.join(TMP, "cr_unit"))
        m = v.save(None, [{"name": "graphic.svg", "data": SVG}], prompt="a red fox logo for Bakery Co")
        self.assertTrue(m["id"].startswith("cr_red-fox-bakery-co-logo_"), m["id"])
        self.assertEqual(m["title"], "red fox bakery co logo")
        self.assertEqual([f["name"] for f in m["files"]], ["red-fox-bakery-co-logo.svg"])
        folder = v.root / m["id"]
        self.assertIsNotNone(naming.read_tag(folder))
        self.assertEqual(naming.read_tag(folder)["owner"], "creation mode")
        self.assertIsNotNone(v.get(m["id"]))                                    # the new id form is accepted everywhere the old one was
        m2 = v.save("Untitled", [{"name": "x.svg", "data": SVG}], prompt="a red fox logo for Bakery Co")
        self.assertNotEqual(m["id"], m2["id"])                                  # made twice: a counter, not a random token
        self.assertRegex(m2["id"], r"-\d+$|_\d{6}$")
        with self.assertRaises(creations_vault.CreationError):
            v.save("Untitled", [{"name": "x.svg", "data": SVG}], prompt="make a new thing")
        with self.assertRaises(creations_vault.CreationError):
            creations_vault.clean_name(".png")

    def test_engine_names_are_derived_not_defaulted(self):
        self.assertEqual(engine_build.derive_name("an engine that counts words and keeps a counter of lines"), "counts_words")
        with self.assertRaises(engine_build.EngineBuildError):
            engine_build.derive_name("make me a new thing please")
        with self.assertRaises(engine_build.EngineBuildError):
            engine_build.make_spec("an engine that counts words in text", name="engine_1")

    def test_no_stand_in_label_is_left_in_the_generating_code(self):
        banned = [r'"Untitled', r"AUTONOMOUS SYSTEM DROP", r'or "engine"', r'"graphic\.svg" if', r'or "file"', r'or "Creation"', r'"Untitled_Build"']
        for rel in ("creations_vault.py", "creation_mode.py", "engine_build.py", "nexxus_talks.py"):
            text = open(os.path.join(NX, rel), encoding="utf-8").read()
            for pat in banned:
                self.assertIsNone(re.search(pat, text), "%s still has %s" % (rel, pat))


class Watch(unittest.TestCase):
    def test_pulse_reports_breathing_changed_missing_and_never_touches_the_files(self):
        if os.path.exists(vital_watch._state_path()):                           # a fresh start: no baseline yet
            os.remove(vital_watch._state_path())
        before = snapshot(WATCHED)
        listing = sorted(os.listdir(WATCHED))
        first = vital_watch.pulse_all()["entries"][0]
        self.assertEqual(first["status"], "new")
        again = vital_watch.pulse_all()
        self.assertEqual(again["entries"][0]["status"], "breathing")
        self.assertEqual(again["summary"], {"watching": 1, "breathing": 1, "changed": 0, "missing": 0})
        self.assertEqual(snapshot(WATCHED), before)                           # same bytes, same sizes, same modification times
        self.assertEqual(sorted(os.listdir(WATCHED)), listing)                # nothing created next to them
        open(os.path.join(WATCHED, "app.py"), "a").write("# the owner edited this\n")           # the OWNER changes it
        events = []
        res = vital_watch.pulse_all(lambda *a: events.append(a))
        self.assertEqual(res["entries"][0]["status"], "changed")
        self.assertEqual(events[0][:3], ("storefront-core", "breathing", "changed"))
        vital_watch.accept("storefront-core")
        self.assertEqual(vital_watch.pulse_all()["entries"][0]["status"], "breathing")
        with self.assertRaises(KeyError):
            vital_watch.accept("not-on-the-list")

    def test_guards_refuse_writes_and_integration_inside_the_watched_path_only(self):
        with self.assertRaises(vital_watch.ReadOnlyBoundary):
            vital_watch.guard_write(os.path.join(WATCHED, "assets", "new.txt"))
        with self.assertRaises(vital_watch.ReadOnlyBoundary):
            vital_watch.guard_integrate(WATCHED)
        with self.assertRaises(vital_watch.ReadOnlyBoundary):
            vital_watch.guard_integrate(TMP)                                  # a parent that contains a watched path would pull it in
        vital_watch.guard_write(os.path.join(TMP, "somewhere_else", "x.txt"))
        v = creations_vault.CreationsVault(os.path.join(WATCHED, "creations"))   # a vault whose root is inside the watched folder
        with self.assertRaises(vital_watch.ReadOnlyBoundary):
            v.save("red fox logo", [{"name": "red-fox.svg", "data": SVG}], prompt="red fox logo")
        self.assertFalse(os.path.exists(os.path.join(WATCHED, "creations")))
        import nexxus_external
        json.dump({"blog": {"secret_file": os.path.join(TMP, "x", "nexxus.secret")}, "storefront": {"secret_file": os.path.join(WATCHED, "nexxus.secret")}}, open(os.path.join(TMP, "ext.json"), "w"))
        old = nexxus_external.CONFIG
        nexxus_external.CONFIG = type(old)(os.path.join(TMP, "ext.json"))
        try:
            self.assertEqual(sorted(nexxus_external.names()), ["blog"])      # a module living in a watched folder is never callable
        finally:
            nexxus_external.CONFIG = old


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = srv.app.test_client()

    def test_1_public_status_is_counts_only_and_detail_needs_the_token(self):
        d = self.http.get("/api/vital/status").get_json()
        self.assertEqual(d["summary"]["watching"], 1)
        self.assertNotIn("storefront", str(d))
        self.assertEqual(self.http.get("/api/vital/pulse").status_code, 401)
        p = self.http.get("/api/vital/pulse?max_age=0", headers=ADMIN).get_json()
        self.assertEqual(p["entries"][0]["name"], "storefront-core")
        self.assertTrue(p["read_only"])
        self.assertNotIn(WATCHED, json.dumps(p))                              # the path itself is not echoed

    def test_2_nothing_can_add_or_edit_a_watched_path_through_the_server(self):
        for method, path in (("post", "/api/vital/add"), ("post", "/api/vital/watch"), ("put", "/api/vital/pulse"), ("delete", "/api/vital/pulse"), ("post", "/api/vital/pulse")):
            self.assertIn(getattr(self.http, method)(path, json={"name": "x", "path": TMP}, headers=ADMIN).status_code, (404, 405), path)
        before = json.load(open(WATCH_FILE))
        self.http.post("/api/vital/accept", json={"name": "../../etc", "path": TMP}, headers=ADMIN)
        self.assertEqual(json.load(open(WATCH_FILE)), before)

    def test_3_a_watched_path_that_goes_missing_is_a_perimeter_event_and_nothing_is_repaired(self):
        gone = os.path.join(WATCHED, "assets")
        moved = gone + "_moved_by_owner"
        os.rename(gone, moved)
        try:
            srv._vital_cache["data"] = None
            self.http.get("/api/vital/pulse?max_age=0", headers=ADMIN)           # first look after the change
            srv._vital_cache["data"] = None
            r = self.http.get("/api/vital/pulse?max_age=0", headers=ADMIN).get_json()
            self.assertEqual(r["entries"][0]["status"], "changed")                # a missing sub-folder changes the tree; the tree itself is still there
            self.assertFalse(os.path.exists(gone))                                # and NEXXUS did not recreate it
        finally:
            os.rename(moved, gone)
        events = self.http.get("/api/perimeter/status", headers=ADMIN).get_json()["events"]
        self.assertTrue(any(e["kind"] == "commercial-changed" for e in events))

    def test_4_accept_and_naming_routes(self):
        self.assertEqual(self.http.post("/api/vital/accept", json={"name": "storefront-core"}).status_code, 401)
        self.assertEqual(self.http.post("/api/vital/accept", json={"name": "storefront-core"}, headers=ADMIN).status_code, 200)
        self.assertEqual(self.http.post("/api/vital/accept", json={"name": "nope"}, headers=ADMIN).status_code, 404)
        self.assertEqual(self.http.get("/api/naming/audit").status_code, 401)
        a = self.http.get("/api/naming/audit", headers=ADMIN).get_json()["roots"]
        self.assertIn("creations", a)
        # an older, untagged creation is found as an orphan and adopted without being renamed
        old = os.path.join(os.environ["NEXXUS_CREATIONS_DIR"], "cr_20260101_120000_ab12")
        os.makedirs(old)
        open(os.path.join(old, "meta.json"), "w").write(json.dumps({"id": "cr_20260101_120000_ab12", "title": "Untitled", "kind": "svg", "prompt": "a green frog badge", "files": [], "version": 1, "created_at": 1}))
        open(os.path.join(old, "graphic.svg"), "wb").write(SVG)
        self.assertIn("cr_20260101_120000_ab12", self.http.get("/api/naming/audit", headers=ADMIN).get_json()["roots"]["creations"]["orphans"])
        r = self.http.post("/api/naming/adopt", headers=ADMIN).get_json()
        self.assertIn("cr_20260101_120000_ab12", r["adopted"])
        self.assertEqual(naming.read_tag(old)["name"], "green-frog-badge")
        self.assertTrue(os.path.exists(os.path.join(old, "graphic.svg")))        # nothing was renamed or moved


if __name__ == "__main__":
    unittest.main(verbosity=1)
