"""The Marketplace: safe bundle reading, the four automatic stages, the strict order of the gauntlet, the buyer view's boundaries and the admin gates."""
import io
import json
import os
import unittest
import zipfile

from flask import Flask, jsonify

import marketplace as mk
import platform_mode as pm
import teams
from test_platform_mode import Base

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD_PY = "def main():\n    return 'hello from a clean product'\n\nif __name__ == '__main__':\n    print(main())\n"
GOOD_README = "# Clean Product\n\nThis product greets you politely. Install it by copying main.py; run it with python main.py. It reads nothing, writes nothing and uses no network. " * 2


def manifest(**over):
    m = {"name": "Clean Product", "version": "1.0.0", "description": "A tiny, honest product that greets the user and does nothing else at all.", "kind": "software",
         "license": "MIT", "entry": "main.py", "permissions": []}
    m.update(over)
    return m


def bundle(files=None, man=None, drop=()):
    f = {"marketplace.json": json.dumps(manifest() if man is None else man), "main.py": GOOD_PY, "README.md": GOOD_README}
    f.update(files or {})
    for d in drop:
        f.pop(d, None)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in f.items():
            z.writestr(n, b)
    return buf.getvalue()


def findings(stage_fn, *args):
    return [(a, b, d) for a, b, c, d in stage_fn(*args)]


def blocks(fs):
    return [x for x in fs if x[0] == "block"]


class BundleReaderTest(unittest.TestCase):
    def test_a_clean_bundle_reads(self):
        self.assertEqual(set(mk.read_bundle(bundle())), {"marketplace.json", "main.py", "README.md"})

    @staticmethod
    def flag_encrypted(data):
        """Set the 'encrypted' bit in both the local header and the central directory of a finished zip (the writer will not let a test do it directly)."""
        b = bytearray(data)
        for sig, off in ((b"PK", 6), (b"PK", 8)):
            i = b.find(sig)
            b[i + off] |= 1
        return bytes(b)

    def test_unsafe_zips_are_refused_outright(self):
        def raw(name, body=b"x", mutate=None):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                zi = zipfile.ZipInfo(name)
                zi.compress_type = zipfile.ZIP_DEFLATED
                if mutate:
                    mutate(zi)
                z.writestr(zi, body)
            return buf.getvalue()
        cases = {"traversal": raw("../evil.py"), "absolute": raw("/etc/passwd"), "drive": raw("C:/Windows/x.py"), "device": raw("CON.txt"), "backslash traversal": raw("a\\..\\..\\x.py"),
                 "symlink": raw("link", mutate=lambda zi: setattr(zi, "external_attr", 0o120777 << 16)), "encrypted": self.flag_encrypted(raw("secret.py")),
                 "not a zip": b"this is not a zip", "empty": b"", "bomb": raw("zeros.txt", b"\0" * (1500 * 1024))}
        for why, data in cases.items():
            with self.assertRaises(mk.MarketError, msg=why):
                mk.read_bundle(data)

    def test_size_and_count_limits(self):
        with self.assertRaises(mk.MarketError):
            mk.read_bundle(b"x" * (mk.MAX_ZIP + 1))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for i in range(mk.MAX_ENTRIES + 1):
                z.writestr("f%d.txt" % i, "x")
        with self.assertRaises(mk.MarketError):
            mk.read_bundle(buf.getvalue())
        big = io.BytesIO()
        with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("big.txt", os.urandom(mk.MAX_FILE + 10))
        with self.assertRaises(mk.MarketError):
            mk.read_bundle(big.getvalue())


class IntakeTest(unittest.TestCase):
    def run_intake(self, **kw):
        files = mk.read_bundle(bundle(**kw))
        return mk.stage_intake(files)[0]

    def test_clean_passes(self):
        self.assertEqual(self.run_intake(), [])

    def test_manifest_rules(self):
        for bad, man in (("no manifest", None), ("placeholder name", manifest(name="test")), ("bad version", manifest(version="1.0")), ("short description", manifest(description="too short")),
                         ("bad kind", manifest(kind="spaceship")), ("unknown permission", manifest(permissions=["root"])), ("missing entry", manifest(entry="nope.py"))):
            kw = {"drop": ("marketplace.json",)} if man is None else {"man": man}
            self.assertTrue(blocks([(a, b, d) for a, b, c, d in self.run_intake(**kw)]), bad)

    def test_files_must_parse(self):
        self.assertTrue(blocks([(a, b, d) for a, b, c, d in self.run_intake(files={"bad.py": "def (:\n"})]))
        self.assertTrue(blocks([(a, b, d) for a, b, c, d in self.run_intake(files={"data.json": "{not json"})]))


class HygieneTest(unittest.TestCase):
    def scan(self, files):
        return mk.stage_hygiene(mk.read_bundle(bundle(files=files)))

    def test_executables_archives_and_odd_types_are_blocked(self):
        for name, body in (("app.exe", b"MZ\x90\x00x"), ("lib.dll", b"data"), ("note.txt", b"MZ\x90 disguised"), ("elf.txt", b"\x7fELF...."), ("inner.zip", b"PK\x03\x04"), ("tool.bin", b"x"), ("weird.xyz", b"x")):
            self.assertTrue(self.scan({name: body}), name)

    def test_credentials_files_and_secrets_are_blocked_without_echoing_them(self):
        secrets = {"k.py": 'KEY = "ghp_' + "a" * 36 + '"', "a.txt": "AKIA" + "A" * 16, "s.txt": "sk_live_" + "b" * 24, "p.txt": "-----BEGIN RSA PRIVATE KEY-----\nabc", "c.py": 'password = "hunter2hunter2hunter2"'}
        for name, body in secrets.items():
            found = self.scan({name: body})
            self.assertTrue(blocks([(a, b, d) for a, b, c, d in found]), name)
            for _, _, _, text in found:
                self.assertNotIn(body.strip('"'), text)
                self.assertNotIn("a" * 20, text)
        self.assertTrue(self.scan({".env": "X=1"}))

    def test_private_paths_and_long_lines_only_warn(self):
        found = self.scan({"p.txt": "see C:\\Users\\Ada\\secret", "m.js": "x=1;" + "a" * 6000})
        self.assertTrue(found and all(a == "warn" for a, *_ in found))

    def test_clean_files_pass(self):
        self.assertEqual(self.scan({"logo.png": b"\x89PNG\r\n\x1a\n" + b"0" * 20}), [])


class SecurityTest(unittest.TestCase):
    def scan(self, files, perms=()):
        man = manifest(permissions=list(perms))
        return mk.stage_security(mk.read_bundle(bundle(files=files, man=man)), man)

    def block_texts(self, found):
        return [d for a, b, c, d in found if a == "block"]

    def test_dangerous_constructs_are_always_blocked(self):
        for code in ("eval('1+1')", "exec('x=1')", "x = __import__('os')", "import os\nos.system('dir')", "import subprocess\nsubprocess.run('dir', shell=True)", "import pickle\npickle.loads(b'')",
                     "import ctypes", "compile('1', 'f', 'eval')", "import marshal"):
            self.assertTrue(self.block_texts(self.scan({"x.py": code}, perms=("network", "files", "subprocess", "env"))), code)

    def test_capabilities_must_be_declared(self):
        cases = {"network": "import urllib.request\nurllib.request.urlopen('https://x')", "files": "open('out.txt', 'w').write('x')", "subprocess": "import subprocess\nsubprocess.run(['ls'])",
                 "env": "import os\nx = os.environ.get('HOME')"}
        for perm, code in cases.items():
            self.assertTrue(any(perm in t for t in self.block_texts(self.scan({"x.py": code}))), "undeclared " + perm)
            self.assertFalse(self.block_texts(self.scan({"x.py": code}, perms=(perm,))), "declared " + perm + " must pass")

    def test_declared_but_unused_only_warns_and_clean_code_passes(self):
        found = self.scan({}, perms=("network",))
        self.assertFalse(self.block_texts(found))
        self.assertTrue(any(a == "warn" and "network" in d for a, b, c, d in found))
        self.assertFalse(self.block_texts(self.scan({})))

    def test_javascript_and_html(self):
        for code in ("eval('x')", "new Function('return 1')", "document.write('<b>')"):
            self.assertTrue(self.block_texts(self.scan({"a.js": code})), code)
        self.assertTrue(any("network" in t for t in self.block_texts(self.scan({"a.js": "fetch('/api')"}))))
        self.assertFalse(self.block_texts(self.scan({"a.js": "fetch('/api')"}, perms=("network",))))
        self.assertTrue(self.block_texts(self.scan({"p.html": '<a href="javascript:alert(1)">x</a>'})))

    def test_it_is_honest_that_static_analysis_proves_nothing(self):
        self.assertTrue(any(a == "info" and "cannot prove safety" in d for a, b, c, d in self.scan({})))


class ListingTest(unittest.TestCase):
    def check(self, readme=GOOD_README, man=None, listing=None):
        m = man or manifest()
        files = mk.read_bundle(bundle(files={"README.md": readme}, man=m))
        return [(a, d) for a, b, c, d in mk.stage_listing(files, m, listing or {"title": "Clean Product", "summary": "A tiny honest product that greets you."})]

    def test_good_and_bad_listings(self):
        self.assertFalse([x for x in self.check() if x[0] == "block"])
        self.assertTrue([x for x in self.check(readme="too short") if x[0] == "block"])
        self.assertTrue([x for x in self.check(man=manifest(license="WTFPL")) if x[0] == "block"])
        self.assertTrue([x for x in self.check(listing={"title": "Guaranteed passive income machine", "summary": "x" * 30}) if x[0] == "block"])


class ListingValidationTest(unittest.TestCase):
    def test_listing_fields(self):
        ok = mk._listing({"title": "T", "summary": "x" * 25, "category": "Software", "price": 9.99})
        self.assertEqual((ok["price_cents"], ok["currency"]), (999, "USD"))
        for bad in ({}, {"title": "T", "summary": "short", "category": "Software", "price": 1}, {"title": "T", "summary": "x" * 25, "category": "Weapons", "price": 1},
                    {"title": "T", "summary": "x" * 25, "category": "Software", "price": -1}, {"title": "T", "summary": "x" * 25, "category": "Software", "price": "free"}):
            with self.assertRaises(mk.MarketError):
                mk._listing(bad)


class GauntletBase(Base):
    LISTING = {"title": "Clean Product", "summary": "A tiny honest product that greets you politely.", "category": "Software", "price": 12}

    def setUp(self):
        super().setUp()
        teams.set_providers(tracks=lambda: [], system=lambda: None)
        self.co = teams.create_team("Founders Co", "ship it", "company")
        self.sub = mk.create_submission(self.co["id"], self.LISTING)
        self.sid = self.sub["id"]

    def status(self):
        return mk.get_submission(self.sid)["status"]

    def stage(self, name):
        return next(s for s in mk.get_submission(self.sid)["stages"] if s["id"] == name)

    def clean_through_tests(self):
        mk.upload_version(self.sid, bundle())
        mk.attest_tests(self.sid, "Rae Reviewer", "Ran the product in a throwaway VM: clean install, ran twice, fed empty and huge inputs, checked memory. Everything behaved.", "Disposable Windows VM, no network", 5, 0)

    def clean_through_review(self):
        self.clean_through_tests()
        mk.review_signoff(self.sid, "Rae Reviewer", {k: True for k in mk.REVIEW_CHECKLIST}, "Looks honest.", True)


class GauntletOrderTest(GauntletBase):
    def test_only_a_company_can_submit(self):
        solo = teams.create_team("Just a team", kind="team")
        with self.assertRaises(mk.MarketError):
            mk.create_submission(solo["id"], self.LISTING)
        with self.assertRaises(mk.MarketError):
            mk.create_submission("nope", self.LISTING)

    def test_the_whole_path_in_order(self):
        self.assertEqual(self.status(), "draft")
        mk.upload_version(self.sid, bundle())
        self.assertEqual([self.stage(s)["state"] for s in ("intake", "hygiene", "security", "listing")], ["pass"] * 4)
        self.assertEqual(self.status(), "awaiting_tests")
        with self.assertRaises(mk.MarketError):
            mk.review_signoff(self.sid, "Rae", {k: True for k in mk.REVIEW_CHECKLIST}, "", True)
        with self.assertRaises(mk.MarketError):
            mk.sign_agreement(self.sid, "Ada Lovelace", {k: True for k in mk.AGREEMENT_ACKS})
        with self.assertRaises(mk.MarketError):
            mk.greenlight(self.sid, "admin")
        mk.attest_tests(self.sid, "Rae Reviewer", "Ran it in a disposable VM with no network: clean install, repeated runs, bad inputs and a memory check all behaved.", "Disposable VM", 6, 0)
        self.assertEqual(self.status(), "awaiting_review")
        with self.assertRaises(mk.MarketError):
            mk.sign_agreement(self.sid, "Ada Lovelace", {k: True for k in mk.AGREEMENT_ACKS})
        mk.review_signoff(self.sid, "Rae Reviewer", {k: True for k in mk.REVIEW_CHECKLIST}, "Fine.", True)
        self.assertEqual(self.status(), "awaiting_agreement")
        with self.assertRaises(mk.MarketError):
            mk.greenlight(self.sid, "admin")
        mk.sign_agreement(self.sid, "Ada Lovelace", {k: True for k in mk.AGREEMENT_ACKS})
        self.assertEqual(self.status(), "awaiting_greenlight")
        self.assertEqual(mk.public_catalog()["total"], 0, "not visible until the administrator greenlights it")
        mk.greenlight(self.sid, "admin", "https://pay.example/checkout/clean")
        self.assertEqual(self.status(), "published")
        card = mk.public_catalog()["products"][0]
        self.assertEqual((card["title"], card["buy_url"], card["final_cents"]), ("Clean Product", "https://pay.example/checkout/clean", 1200))

    def test_an_automatic_failure_stops_everything(self):
        mk.upload_version(self.sid, bundle(files={"evil.py": "import os\nos.system('rm -rf /')"}))
        self.assertEqual((self.status(), self.stage("security")["state"]), ("changes_requested", "fail"))
        self.assertEqual([self.stage(k)["state"] for k in ("functional", "review", "agreement", "greenlight")], ["locked"] * 4, "nothing after a failed stage can start")
        self.assertTrue(any("os.system" in f["text"] for f in self.stage("security")["findings"]))
        with self.assertRaises(mk.MarketError):
            mk.attest_tests(self.sid, "Rae Reviewer", "x" * 150, "A VM here", 3, 0)

    def test_intake_failure_locks_the_later_automatic_stages(self):
        mk.upload_version(self.sid, bundle(drop=("marketplace.json",)))
        self.assertEqual([self.stage(s)["state"] for s in ("intake", "security", "listing")], ["fail", "locked", "locked"])

    def test_a_thin_or_failing_test_report_cannot_pass(self):
        mk.upload_version(self.sid, bundle())
        for args in (("Rae", "short", "VM here", 3, 0), ("Rae", "x" * 150, "", 3, 0), ("Rae", "x" * 150, "VM here", 0, 0), ("", "x" * 150, "VM here", 3, 0), ("Rae", "x" * 150, "VM here", "many", 0)):
            with self.assertRaises(mk.MarketError):
                mk.attest_tests(self.sid, *args)
        mk.attest_tests(self.sid, "Rae Reviewer", "Ran it in a disposable VM; two tests failed on empty input, which the creator must fix before it can pass.", "Disposable VM", 4, 2)
        self.assertEqual(self.status(), "changes_requested")

    def test_review_needs_every_checklist_item_to_approve(self):
        self.clean_through_tests()
        partial = {k: True for k in mk.REVIEW_CHECKLIST}
        partial["tested_in_isolation"] = False
        with self.assertRaises(mk.MarketError):
            mk.review_signoff(self.sid, "Rae", partial, "", True)
        mk.review_signoff(self.sid, "Rae", partial, "Not tested properly.", False)
        self.assertEqual(self.status(), "changes_requested")

    def test_the_agreement_needs_the_full_name_and_every_acknowledgement(self):
        self.clean_through_review()
        for name, acks in (("Ada", {k: True for k in mk.AGREEMENT_ACKS}), ("Ada Lovelace", {"read": True}), ("Ada Lovelace", {k: "yes" for k in mk.AGREEMENT_ACKS}), ("", {})):
            with self.assertRaises(mk.MarketError):
                mk.sign_agreement(self.sid, name, acks)
        sub = mk.sign_agreement(self.sid, "Ada Lovelace", {k: True for k in mk.AGREEMENT_ACKS})
        self.assertEqual((sub["agreement"]["revenue_share_percent"], sub["agreement"]["sha256"]), (5, mk.AGREEMENT_SHA))
        self.assertIn("5%", mk.AGREEMENT_TEXT)
        self.assertIn("DRAFT TEMPLATE", mk.AGREEMENT_TEXT)
        self.assertIn("lawyer", mk.AGREEMENT_TEXT)

    def test_a_changed_agreement_must_be_signed_again(self):
        self.clean_through_review()
        mk.sign_agreement(self.sid, "Ada Lovelace", {k: True for k in mk.AGREEMENT_ACKS})
        old = mk.AGREEMENT_VERSION
        mk.AGREEMENT_VERSION = "2027-new"
        try:
            with self.assertRaises(mk.MarketError):
                mk.greenlight(self.sid, "admin")
        finally:
            mk.AGREEMENT_VERSION = old

    def test_a_new_version_reruns_everything_but_the_vetted_one_stays_on_sale(self):
        self.clean_through_review()
        mk.sign_agreement(self.sid, "Ada Lovelace", {k: True for k in mk.AGREEMENT_ACKS})
        mk.greenlight(self.sid, "admin", "https://pay.example/c")
        mk.upload_version(self.sid, bundle(man=manifest(version="1.1.0")))
        self.assertEqual(self.status(), "awaiting_tests", "the update must pass the gauntlet again")
        self.assertEqual(self.stage("functional")["state"], "waiting")
        self.assertEqual(mk.public_catalog()["products"][0]["version"], "1.0.0", "buyers keep the vetted version while the update is vetted")

    def test_nothing_in_the_bundle_is_ever_executed(self):
        marker = os.path.join(os.path.dirname(mk.DATA_DIR), "pwned.txt")
        code = "open(%r, 'w').write('executed')\n" % marker
        mk.upload_version(self.sid, bundle(files={"main.py": code}))
        self.assertFalse(os.path.exists(marker), "the submitted code must never run")
        self.assertTrue(os.path.exists(os.path.join(mk.BLOB_DIR, "%s-v1.zip" % self.sid)), "the bundle is kept as an inert zip")

    def test_every_step_is_in_the_audit_trail(self):
        self.clean_through_review()
        actions = [a["action"] for a in mk.audit()]
        for expected in ("created", "uploaded", "tests attested", "review approved"):
            self.assertIn(expected, actions)


class StorefrontTest(GauntletBase):
    def publish(self, title, price, category="Software", checkout="https://pay.example/x", discount=None, summary="A product that is honest and useful for makers."):
        sub = mk.create_submission(self.co["id"], {"title": title, "summary": summary, "category": category, "price": price})
        sid = sub["id"]
        mk.upload_version(sid, bundle(man=manifest(name=title)))
        mk.attest_tests(sid, "Rae Reviewer", "Ran it in a disposable VM: clean install, repeated runs, bad inputs and resource checks all fine for this one.", "Disposable VM", 5, 0)
        mk.review_signoff(sid, "Rae Reviewer", {k: True for k in mk.REVIEW_CHECKLIST}, "ok", True)
        mk.sign_agreement(sid, "Ada Lovelace", {k: True for k in mk.AGREEMENT_ACKS})
        mk.greenlight(sid, "admin", checkout, discount)
        return sid

    def test_the_storefront_is_empty_not_faked(self):
        c = mk.public_catalog()
        self.assertEqual((c["products"], c["total"], c["on_sale"]), ([], 0, 0))
        self.assertEqual(c["categories"], list(mk.CATEGORIES))

    def test_buyers_see_only_published_products_and_nothing_private(self):
        draft = mk.create_submission(self.co["id"], self.LISTING)                         # a draft that must stay invisible
        sid = self.publish("Alpha Kit", 20)
        cat = mk.public_catalog()
        self.assertEqual([p["id"] for p in cat["products"]], [sid])
        blob = json.dumps(cat)
        for private in ("agreement_text", "Ada Lovelace", "stages", "versions", "sha256", "Rae Reviewer", "quarantine", draft["id"], "creator", "5%", "revenue", "findings", "legal_name"):
            self.assertNotIn(private, blob, private)

    def test_vetting_is_shown_to_buyers_honestly(self):
        sid = self.publish("Alpha Kit", 20)
        v = mk.public_catalog()["products"][0]["vetting"]
        self.assertEqual(v["automatic"], ["intake", "hygiene", "security", "listing"])
        self.assertTrue(v["tests_attested_by_person"] and v["human_reviewed"] and v["agreement_signed"])
        self.assertEqual(v["permissions"], [])

    def test_filters_search_and_sorting(self):
        self.publish("Alpha Kit", 30, "Software")
        self.publish("Beta Guide", 10, "Guides", summary="A guide to pricing your first digital product well.")
        self.publish("Gamma Pack", 20, "Assets")
        names = lambda **kw: [p["title"] for p in mk.public_catalog(**kw)["products"]]
        self.assertEqual(names(category="Guides"), ["Beta Guide"])
        self.assertEqual(names(q="gamma"), ["Gamma Pack"])
        self.assertEqual(names(q="pricing"), ["Beta Guide"])
        self.assertEqual(names(sort="price_low"), ["Beta Guide", "Gamma Pack", "Alpha Kit"])
        self.assertEqual(names(sort="price_high"), ["Alpha Kit", "Gamma Pack", "Beta Guide"])
        self.assertEqual(names(sort="name"), ["Alpha Kit", "Beta Guide", "Gamma Pack"])
        self.assertEqual(names(category="Nonsense"), ["Alpha Kit", "Beta Guide", "Gamma Pack"] if False else names(), "an unknown category is ignored, not an error")

    def test_discounts_are_real_and_expire(self):
        self.publish("Sale Item", 100, discount={"percent": 25, "label": "Launch week", "until": "2999-01-01"})
        self.publish("Old Sale", 100, discount={"percent": 50, "until": "2000-01-01"})
        cards = {p["title"]: p for p in mk.public_catalog(today="2026-10-15")["products"]}
        self.assertEqual((cards["Sale Item"]["final_cents"], cards["Sale Item"]["discount"]["label"]), (7500, "Launch week"))
        self.assertEqual((cards["Old Sale"]["final_cents"], cards["Old Sale"]["discount"]), (10000, None), "an expired discount does nothing")
        self.assertEqual(mk.public_catalog(today="2026-10-15")["on_sale"], 1)
        for bad in ({"percent": 95}, {"percent": 0}, {"percent": "x"}, {"percent": 10, "until": "soon"}):
            with self.assertRaises(mk.MarketError):
                mk._discount(bad)

    def test_a_product_without_a_checkout_link_cannot_be_bought_yet(self):
        self.publish("No Link Yet", 10, checkout="")
        self.assertEqual(mk.public_catalog()["products"][0]["buy_url"], "")
        sid = mk.public_catalog()["products"][0]["id"]
        with self.assertRaises(mk.MarketError):
            mk.set_checkout(sid, "admin", "http://insecure.example")
        mk.set_checkout(sid, "admin", "https://pay.example/ok")
        self.assertEqual(mk.public_catalog()["products"][0]["buy_url"], "https://pay.example/ok")

    def test_takedowns_reports_and_withdrawals(self):
        sid = self.publish("Risky Kit", 10)
        with self.assertRaises(mk.MarketError):
            mk.report_listing(sid, "bad")
        mk.report_listing(sid, "This product copies another seller's work.", "a buyer")
        self.assertEqual(mk.reports()[0]["id"], sid)
        mk.unpublish(sid, "admin", "Rights complaint upheld")
        self.assertEqual(mk.public_catalog()["total"], 0)
        with self.assertRaises(mk.MarketError):
            mk.public_product(sid)
        sid2 = self.publish("Mine To Withdraw", 5)
        mk.withdraw(sid2, "creator")
        self.assertEqual(mk.public_catalog()["total"], 0)


class MarketplaceRoutesTest(GauntletBase):
    def setUp(self):
        super().setUp()
        self.admin = False
        app = Flask(__name__)
        pm.register_routes(app, lambda: True, lambda p, s=200: (jsonify(p), s), lambda: self.admin)
        self.c = app.test_client()
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": true}')

    def upload(self, sid, data):
        return self.c.post("/api/platform/marketplace/submission/%s/upload" % sid, data={"bundle": (io.BytesIO(data), "p.zip")}, content_type="multipart/form-data")

    def test_buyer_view_works_with_no_company_at_all(self):
        teams.delete_team(self.co["id"])
        r = self.c.get("/api/platform/marketplace/catalog").get_json()
        self.assertEqual((r["status"], r["total"]), ("success", 0))
        me = self.c.get("/api/platform/marketplace/me").get_json()
        self.assertEqual((me["companies"], me["admin"], me["revenue_share_percent"]), ([], False, 5))

    def test_creator_flow_and_admin_gates(self):
        s = self.c.post("/api/platform/marketplace/submission", json={"team_id": self.co["id"], "listing": self.LISTING}).get_json()["submission"]
        sid = s["id"]
        self.assertEqual(self.upload(sid, bundle()).status_code, 200)
        self.assertEqual(self.upload(sid, b"not a zip").status_code, 400)
        attest = {"reviewer": "Rae Reviewer", "report": "Ran it in a disposable VM with no network: clean install, repeated runs, bad inputs and a memory check all behaved.", "environment": "Disposable VM", "passed": 5, "failed": 0}
        for path in ("attest", "review", "greenlight", "checkout", "reject", "unpublish"):
            self.assertEqual(self.c.post("/api/platform/marketplace/submission/%s/%s" % (sid, path), json=attest).status_code, 403, "%s must need the administrator" % path)
        self.assertEqual(self.c.get("/api/platform/marketplace/admin/queue").status_code, 403)
        self.admin = True
        self.assertEqual(self.c.post("/api/platform/marketplace/submission/%s/attest" % sid, json=attest).status_code, 200)
        self.assertEqual(self.c.post("/api/platform/marketplace/submission/%s/review" % sid, json={"reviewer": "Rae", "checklist": {}, "approve": True}).status_code, 400)
        self.assertEqual(self.c.post("/api/platform/marketplace/submission/%s/review" % sid, json={"reviewer": "Rae", "checklist": {k: True for k in mk.REVIEW_CHECKLIST}, "approve": True}).status_code, 200)
        self.admin = False
        sign = {"legal_name": "Ada Lovelace", "acks": {k: True for k in mk.AGREEMENT_ACKS}}
        self.assertEqual(self.c.post("/api/platform/marketplace/submission/%s/agreement" % sid, json=sign).status_code, 200)
        self.admin = True
        self.assertEqual(self.c.post("/api/platform/marketplace/submission/%s/greenlight" % sid, json={"checkout_url": "https://pay.example/z", "discount": {"percent": 10}}).status_code, 200)
        q = self.c.get("/api/platform/marketplace/admin/queue").get_json()
        self.assertEqual((len(q["submissions"]), q["audit"][0]["action"]), (2, "published"), "the setup's own draft plus this one")
        self.admin = False
        cat = self.c.get("/api/platform/marketplace/catalog?category=Software").get_json()
        self.assertEqual((cat["total"], cat["products"][0]["final_cents"]), (1, 1080))
        self.assertEqual(self.c.get("/api/platform/marketplace/product/" + sid).status_code, 200)

    def test_a_visitor_cannot_see_other_creators_submissions(self):
        s = self.c.post("/api/platform/marketplace/submission", json={"team_id": self.co["id"], "listing": self.LISTING}).get_json()["submission"]
        teams.delete_team(self.co["id"])
        self.assertEqual(self.c.get("/api/platform/marketplace/submission/" + s["id"]).status_code, 404)
        self.assertEqual(self.upload(s["id"], bundle()).status_code, 404)
        self.assertEqual(self.c.get("/api/platform/marketplace/mine").get_json()["submissions"], [])

    def test_the_catalog_route_only_ever_returns_public_data(self):
        self.upload(self.c.post("/api/platform/marketplace/submission", json={"team_id": self.co["id"], "listing": self.LISTING}).get_json()["submission"]["id"], bundle())
        self.assertEqual(self.c.get("/api/platform/marketplace/catalog").get_json()["products"], [])

    def test_closed_when_the_platform_beta_ends_without_a_license(self):
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": false}')
        self.assertEqual(self.c.get("/api/platform/marketplace/catalog").status_code, 402)


class MarketplaceBoundaryTest(unittest.TestCase):
    def test_it_never_executes_or_imports_submitted_code(self):
        import ast
        tree = ast.parse(open(os.path.join(HERE, "marketplace.py"), encoding="utf-8").read())
        imported = set()
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
            elif isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    called.add(f.id)
                elif isinstance(f, ast.Attribute) and f.attr in ("system", "popen", "Popen", "extract", "extractall", "import_module", "run_module", "run_path"):
                    called.add(f.attr)
        self.assertFalse(imported & {"subprocess", "importlib", "runpy", "multiprocessing", "ctypes", "socket", "urllib", "requests", "http", "shutil", "pickle", "marshal"}, imported)
        self.assertFalse(called & {"exec", "eval", "compile", "__import__", "system", "popen", "extract", "extractall", "Popen", "import_module", "run_module", "run_path"}, called)

    def test_it_never_touches_the_private_world(self):
        src = open(os.path.join(HERE, "marketplace.py"), encoding="utf-8").read()
        for word in ("direct_message", "group_chat", "room_session", "nexxus_talk", "nexxus_data/private", "PRIVATE_DIR"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
