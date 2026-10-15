"""test_opportunity_desk.py - the opportunity desk: the entity vault (validated, atomic), eligibility checks against a funder's applicant types, the gap analysis and its questionnaire, sign-off that
goes stale when anything changes, the claims check that blocks any packet overstating the organisation, the packet itself, the one network door (official Grants.gov only, rate limited), the ledger,
and the server routes. No network is used (a fake stands in for the API, with the same shape the real one returns); one optional live check runs only if NEXXUS_LIVE_NET=1. Run: python test_opportunity_desk.py"""
import atexit
import json
import os
import shutil
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="opps_")
atexit.register(shutil.rmtree, TMP, True)
ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
os.environ.update(NEXXUS_ADMIN_TOKEN="throwaway-admin", NEXXUS_GOVERNANCE_SECRET="throwaway-secret", NEXXUS_UI_ROOT=os.path.join(TMP, "ui"), NEXXUS_BUS_LEDGER=os.path.join(TMP, "ledger.jsonl"),
                  NEXXUS_ENGINE_STAGING=os.path.join(TMP, "es", "engines"), NEXXUS_ENGINE_LEDGER=os.path.join(TMP, "el.jsonl"), NEXXUS_NOTIFICATIONS_FILE=os.path.join(TMP, "notifs.json"),
                  NEXXUS_PERIMETER_DIR=os.path.join(TMP, "perim"), NEXXUS_COMMERCIAL_WATCH=os.path.join(TMP, "none.json"), NEXXUS_CREATIONS_DIR=os.path.join(TMP, "creations"),
                  NEXXUS_GATE_DIR=os.path.join(TMP, "gate"), NEXXUS_STAGING_DIR=os.path.join(TMP, "stg"), NEXXUS_TOOLS_DIR=os.path.join(TMP, "tools"),
                  NEXXUS_TOOLS_MANIFEST=os.path.join(TMP, "man.json"), NEXXUS_TOOLS_LOG=os.path.join(TMP, "tools.jsonl"), NEXXUS_DISABLE_AUTOSCHEDULER="1",
                  NEXXUS_PUBLISH_DIR=os.path.join(TMP, "pub"), NEXXUS_FACTORY_DIR=os.path.join(TMP, "factory"), NEXXUS_OPPS_DIR=os.path.join(TMP, "opps"))
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, NEXUS)
import opportunity_desk as OD  # noqa: E402

ADMIN = {"X-Nexxus-Admin-Token": "throwaway-admin"}

# These people and facts exist only inside this test.
FACTS = {"org.legal_name": "Test Studio LLC", "org.entity_type": "llc", "org.state": "Oregon", "org.year_founded": 2021, "org.address": "1 Test Road, Testville", "org.mission": "We make accessible web tools for small libraries.",
         "org.services": ["web accessibility audits", "small library websites"], "org.small_business": True, "contact.name": "Pat Tester", "contact.email": "pat@example.org",
         "team.members": [{"name": "Pat Tester", "role": "Founder", "bio": "Builds the tools."}, {"name": "Sam Check", "role": "Designer", "bio": "Designs the interfaces."}],
         "past_performance": [{"client": "Testville Library", "year": "2023", "summary": "Rebuilt the catalogue search for screen readers.", "outcome": "Complaints fell."}]}


def real_shape_detail(types, ceiling=50000, floor=1000, elig="Open to small organisations.", desc="Applicants need demonstrated experience in accessibility."):
    return {"errorcode": 0, "msg": "Webservice Succeeds", "data": {"id": 1, "opportunityNumber": "TEST-001", "opportunityTitle": "Library Access Grant", "owningAgencyCode": "TST",
            "synopsis": {"agencyName": "Test Agency", "postingDate": "Jun 28, 2024 12:00:00 AM EDT", "responseDate": "Jan 01, 2099 12:00:00 AM EST", "awardFloor": str(floor), "awardCeiling": str(ceiling), "costSharing": "False",
                         "applicantTypes": [{"id": "x", "description": t} for t in types], "applicantEligibilityDesc": elig, "synopsisDesc": desc, "agencyContactName": "Grants Office", "agencyContactDesc": "grants@example.gov"}}}


class FakeNet:
    def __init__(self, detail=None):
        self.calls, self.detail = [], detail

    def __call__(self, url, body):
        self.calls.append((url, body))
        if url.endswith("search2"):
            return {"errorcode": 0, "data": {"hitCount": 2, "oppHits": [{"id": "1", "number": "TEST-001", "title": "Library Access Grant", "agency": "Test Agency", "openDate": "01/01/2026", "closeDate": "", "oppStatus": "posted"},
                                                                         {"id": "2", "number": "TEST-002", "title": "Other", "agency": "Test Agency", "openDate": "01/01/2026", "closeDate": "", "oppStatus": "forecasted"}]}}
        return self.detail


def desk(detail=None, clock=None):
    t = [1000.0]
    d = OD.Desk(tempfile.mkdtemp(dir=TMP), now=(clock or (lambda: t[0])), http=FakeNet(detail))
    d.vault.update(FACTS)
    return d


BUDGET = [{"item": "Part-time developer", "amount": 20000}, {"item": "Testing with readers", "amount": 5000}]
NARR = "We will rebuild the search of three small libraries so that it works with screen readers, and we will test it with real readers. Pat and Sam do the work."


class Vault(unittest.TestCase):
    def test_facts_are_validated_and_nothing_is_stored_unless_all_are_valid(self):
        d = desk()
        before = d.vault.snapshot()
        for bad in ({"org.entity_type": "spaceship"}, {"org.year_founded": -3}, {"nope.field": "x"}, {"org.legal_name": "ok", "team.members": [{"role": "no name"}]}, {"org.small_business": "yes"}, {}):
            with self.assertRaises(OD.DeskError, msg=bad):
                d.vault.update(bad)
        self.assertEqual(d.vault.snapshot(), before)

    def test_missing_required_and_headcount_come_from_what_is_stored(self):
        d = OD.Desk(tempfile.mkdtemp(dir=TMP))
        self.assertIn("org.legal_name", d.vault.missing_required())
        d.vault.update(FACTS)
        self.assertEqual(d.vault.missing_required(), [])
        self.assertEqual(d.vault.headcount(), (2, 0))

    def test_a_corrupt_vault_is_set_aside_not_overwritten(self):
        root = tempfile.mkdtemp(dir=TMP)
        open(os.path.join(root, "entity_vault.json"), "w").write("{broken")
        d = OD.Desk(root)
        self.assertEqual(d.vault.snapshot(), {})
        self.assertTrue(any(f.startswith("entity_vault.corrupt") for f in os.listdir(root)))

    def test_no_field_stores_an_identifier_the_desk_must_never_hold(self):
        paths = " ".join(OD.FIELD_BY_PATH)
        for forbidden in ("ein", "ssn", "bank", "card", "password", "routing"):
            self.assertNotRegex(paths.lower(), r"\b%s\b" % forbidden)


class Eligibility(unittest.TestCase):
    def verdict(self, types, vault_facts=None, elig=""):
        d = desk()
        if vault_facts:
            d.vault.update(vault_facts)
        opp = d.add_manual({"title": "T", "agency": "A", "applicant_types": types, "eligibility_text": elig})
        return OD.check_eligibility(opp, d.vault)["verdict"]

    def test_applicant_types_are_matched_against_the_entity_type(self):
        self.assertEqual(self.verdict(["Small businesses"]), "eligible")
        self.assertEqual(self.verdict(["Small businesses"], {"org.small_business": False}), "not_eligible")
        self.assertEqual(self.verdict(["Nonprofits having a 501(c)(3) status with the IRS, other than institutions of higher education"]), "not_eligible")
        self.assertEqual(self.verdict(["Nonprofits having a 501(c)(3) status with the IRS, other than institutions of higher education"], {"org.entity_type": "nonprofit_501c3"}), "eligible")
        self.assertEqual(self.verdict(["For profit organizations other than small businesses", "Individuals"], {"org.small_business": False}), "eligible")
        self.assertEqual(self.verdict(["Unrestricted (i.e., open to any type of entity above)"]), "eligible")

    def test_what_it_cannot_decide_is_review_with_the_reason(self):
        self.assertEqual(self.verdict(['Others (see text field entitled "Additional Information on Eligibility")']), "review")
        self.assertEqual(self.verdict([]), "review")
        self.assertEqual(self.verdict(["Small businesses"], elig="Applicants must hold 501(c)(3) status."), "review")
        d = OD.Desk(tempfile.mkdtemp(dir=TMP))
        opp = d.add_manual({"title": "T", "agency": "A", "applicant_types": ["Small businesses"]})
        self.assertEqual(OD.check_eligibility(opp, d.vault)["verdict"], "review")                 # no entity type in the vault: it does not guess


class Gap(unittest.TestCase):
    def test_a_complete_vault_still_asks_for_the_documents_only_you_can_write(self):
        d = desk()
        o = d.add_manual({"title": "T", "agency": "A", "applicant_types": ["Small businesses"], "award_floor": 1000, "award_ceiling": 50000})
        g = d.analyze(o["id"])["gap"]
        self.assertEqual({q["key"] for q in g["questions"] if q["kind"] == "document"}, {"narrative", "budget"})
        self.assertFalse([q for q in g["questions"] if q["kind"] == "fact"])
        self.assertFalse(g["complete"])

    def test_missing_facts_become_questions_and_answers_close_the_gap(self):
        d = OD.Desk(tempfile.mkdtemp(dir=TMP))
        o = d.add_manual({"title": "T", "agency": "A", "applicant_types": ["Small businesses"]})
        g = d.analyze(o["id"])["gap"]
        paths = {q["path"] for q in g["questions"] if q["kind"] == "fact"}
        self.assertIn("org.legal_name", paths)
        self.assertIn("team.members", paths)
        d.answer(o["id"], facts=FACTS, documents={"narrative": NARR, "budget": BUDGET})
        self.assertTrue(d.analyze(o["id"])["gap"]["complete"])

    def test_a_federal_notice_asks_for_the_uei_and_past_performance_when_the_text_does(self):
        d = desk(real_shape_detail(["Small businesses"]))
        o = d.fetch("1")
        ids = {r["id"] for r in OD.standard_requirements(o)}
        self.assertIn("r-uei", ids)
        self.assertIn("r-past", ids)

    def test_budget_must_fit_the_award_range(self):
        d = desk()
        o = d.add_manual({"title": "T", "agency": "A", "award_floor": 10000, "award_ceiling": 30000})
        for bad in ([{"item": "x", "amount": 40000}], [{"item": "x", "amount": 5}], [], [{"item": "", "amount": 1}], [{"item": "x", "amount": "lots"}]):
            with self.assertRaises(OD.DeskError, msg=bad):
                d.answer(o["id"], documents={"budget": bad})
        d.answer(o["id"], documents={"budget": BUDGET})


class Claims(unittest.TestCase):
    def check(self, text, **facts):
        d = desk()
        if facts:
            d.vault.update(facts)
        return OD.claims_check([text], d.vault)

    def test_overstating_the_team_is_caught(self):
        for text in ("Our team of 25 experts delivers.", "We have 40 employees.", "a staff of 12 professionals", "Over 100+ consultants worldwide", "our team of 5"):
            self.assertTrue(self.check(text), text)

    def test_the_truth_passes(self):
        for text in ("Our team of 2 builds accessible tools.", "Two people do the work: Pat and Sam.", "We tested with 12 readers over 3 months.", "We will rebuild the search of 3 libraries."):
            self.assertEqual(self.check(text), [], text)

    def test_more_years_than_the_organisation_has_existed_is_caught(self):
        self.assertTrue(self.check("With 20 years of experience we deliver."))
        self.assertEqual(self.check("In our 3 years we have rebuilt one catalogue."), [])

    def test_phrases_that_imply_a_scale_the_vault_does_not_record_are_caught(self):
        for text in ("We run a global network of partners.", "offices in four countries", "Our Fortune 500 clients trust us.", "a worldwide presence"):
            self.assertTrue(self.check(text), text)

    def test_a_solo_operator_is_described_as_one(self):
        d = desk()
        d.vault.update({"team.members": [{"name": "Pat Tester", "role": "Founder", "bio": "Does everything."}]})
        o = d.add_manual({"title": "T", "agency": "A", "applicant_types": ["Small businesses"], "award_floor": 1000, "award_ceiling": 50000})
        d.answer(o["id"], documents={"narrative": NARR, "budget": BUDGET})
        d.sign_off(o["id"], "Pat Tester", True)
        out = d.compile(o["id"])
        cover = open(os.path.join(d.root, "packets", out["packet"], "cover_letter.md"), encoding="utf-8").read()
        self.assertIn("one-person practice", cover)
        pers = open(os.path.join(d.root, "packets", out["packet"], "key_personnel.md"), encoding="utf-8").read()
        self.assertIn("One person does the work.", pers)


class Flow(unittest.TestCase):
    def ready(self, types=("Small businesses",)):
        d = desk()
        o = d.add_manual({"title": "Library Access Grant", "agency": "Test Agency", "number": "TEST-001", "applicant_types": list(types), "award_floor": 1000, "award_ceiling": 50000, "url": "https://example.gov/x"})
        d.answer(o["id"], documents={"narrative": NARR, "budget": BUDGET})
        return d, o

    def test_compile_needs_a_sign_off_and_the_sign_off_goes_stale_when_anything_changes(self):
        d, o = self.ready()
        with self.assertRaises(OD.DeskError) as c:
            d.compile(o["id"])
        self.assertIn("sign-off", str(c.exception))
        for name, confirm in (("", True), ("Pat", False), ("Pat", "yes")):
            with self.assertRaises(OD.DeskError):
                d.sign_off(o["id"], name, confirm)
        d.sign_off(o["id"], "Pat Tester", True)
        d.vault.update({"org.mission": "A changed mission statement for the test."})                 # the vault changed after signing
        with self.assertRaises(OD.DeskError) as c:
            d.compile(o["id"])
        self.assertIn("sign off again", str(c.exception))
        d.sign_off(o["id"], "Pat Tester", True)
        self.assertEqual(d.compile(o["id"])["manifest"]["claims_check"], "passed")
        d.answer(o["id"], documents={"narrative": NARR + " More."})                                    # answering resets the sign-off outright
        self.assertFalse(d.analyze(o["id"])["signed_off"])

    def test_sign_off_is_refused_while_questions_are_open(self):
        d = desk()
        o = d.add_manual({"title": "T", "agency": "A", "applicant_types": ["Small businesses"]})
        with self.assertRaises(OD.DeskError) as c:
            d.sign_off(o["id"], "Pat", True)
        self.assertIn("open questions", str(c.exception))

    def test_a_blocked_claim_stops_the_packet_and_is_logged(self):
        d, o = self.ready()
        d.answer(o["id"], documents={"narrative": "Our team of 30 experts will deliver worldwide."})
        d.sign_off(o["id"], "Pat Tester", True)
        with self.assertRaises(OD.DeskError) as c:
            d.compile(o["id"])
        self.assertIn("claims check blocked", str(c.exception))
        self.assertFalse(os.path.exists(os.path.join(d.root, "packets")) and os.listdir(os.path.join(d.root, "packets")))
        self.assertIn("compile_blocked", open(d._ledger, encoding="utf-8").read())

    def test_an_ineligible_organisation_gets_no_packet(self):
        d, o = self.ready(types=("Nonprofits having a 501(c)(3) status with the IRS, other than institutions of higher education",))
        d.sign_off(o["id"], "Pat Tester", True)
        with self.assertRaises(OD.DeskError) as c:
            d.compile(o["id"])
        self.assertIn("not appear eligible", str(c.exception))

    def test_the_packet_is_complete_escaped_hashed_and_says_who_submits(self):
        d, o = self.ready()
        d.vault.update({"org.mission": "We make <b>accessible</b> web tools & more."})
        d.answer(o["id"], documents={"narrative": NARR})
        d.sign_off(o["id"], "Pat Tester", True)
        out = d.compile(o["id"])
        names = set(out["files"])
        for f in ("cover_letter.md", "organization_profile.md", "key_personnel.md", "past_performance.md", "budget.md", "project_narrative.md", "attestations_checklist.md", "submission_notes.md", "application_packet.html", "manifest.json"):
            self.assertIn(f, names)
        pdir = os.path.join(d.root, "packets", out["packet"])
        import hashlib
        for f, h in out["manifest"]["files"].items():
            self.assertEqual(hashlib.sha256(open(os.path.join(pdir, f), "rb").read()).hexdigest(), h)
        page = open(os.path.join(pdir, "application_packet.html"), encoding="utf-8").read()
        self.assertNotIn("<b>accessible</b>", page)
        self.assertIn("&lt;b&gt;accessible&lt;/b&gt;", page)
        notes = open(os.path.join(pdir, "submission_notes.md"), encoding="utf-8").read()
        self.assertIn("Nothing has been sent anywhere", notes)
        self.assertIn("submit through the funder's official portal", notes.lower().replace("3. submit", "submit"))
        self.assertIn("25000.00", open(os.path.join(pdir, "budget.md"), encoding="utf-8").read())
        everything = "".join(open(os.path.join(pdir, f), encoding="utf-8").read() for f in names)
        self.assertNotRegex(everything, r"\b\d{2}-\d{7}\b")                                                  # no EIN-shaped number anywhere
        self.assertIn("EIN, SSN, bank or card details", " ".join(out["manifest"]["not_included"]))

    def test_packet_files_cannot_be_reached_by_path_tricks(self):
        d, o = self.ready()
        d.sign_off(o["id"], "Pat Tester", True)
        out = d.compile(o["id"])
        self.assertTrue(d.packet_file(out["packet"], "budget.md").is_file())
        for packet, name in ((out["packet"], "../../entity_vault.json"), ("../x", "budget.md"), (out["packet"], "budget.md/../../x.json"), ("gg-1-20260101-000000", "budget.md"), (out["packet"], "entity_vault.json.txt")):
            with self.assertRaises(OD.DeskError, msg=(packet, name)):
                d.packet_file(packet, name)


class Network(unittest.TestCase):
    def test_only_the_official_api_is_ever_called_and_calls_are_spaced(self):
        slept = []
        t = [0.0]
        import time as _t
        real = _t.sleep
        _t.sleep = lambda s: (slept.append(s), t.__setitem__(0, t[0] + s))
        try:
            d = desk(real_shape_detail(["Small businesses"]), clock=lambda: t[0])
            d.search("library accessibility")
            d.search("library accessibility")
        finally:
            _t.sleep = real
        self.assertTrue(slept and max(slept) >= OD.MIN_GAP_S - 0.01)
        self.assertTrue(all(u.startswith("https://api.grants.gov/") for u, _ in d._http.calls))
        with self.assertRaises(OD.DeskError):
            d._call("https://evil.example/api", {})
        with self.assertRaises(OD.DeskError):
            d._call("http://api.grants.gov/v1/api/search2", {})

    def test_search_and_fetch_parse_the_real_shapes(self):
        d = desk(real_shape_detail(["Small businesses", "Individuals"], ceiling=50000, floor=1000))
        r = d.search("library", rows=500)
        self.assertEqual(d._http.calls[0][1]["rows"], 25)                                             # the page size is capped
        self.assertEqual([h["id"] for h in r["hits"]], ["1", "2"])
        o = d.fetch("1")
        self.assertEqual((o["id"], o["award_ceiling"], o["award_floor"], o["cost_sharing"]), ("gg-1", 50000.0, 1000.0, False))
        self.assertEqual(o["applicant_types"], ["Small businesses", "Individuals"])
        self.assertEqual(d.get("gg-1")["title"], "Library Access Grant")
        self.assertEqual([x["id"] for x in d.list()], ["gg-1"])

    def test_errors_from_the_funder_or_the_network_are_reported_not_hidden(self):
        d = OD.Desk(tempfile.mkdtemp(dir=TMP), http=lambda u, b: {"errorcode": 7, "msg": "bad request"})
        with self.assertRaises(OD.DeskError) as c:
            d.search("x")
        self.assertIn("bad request", str(c.exception))
        import urllib.error

        def boom(u, b):
            raise urllib.error.URLError("no route")
        d2 = OD.Desk(tempfile.mkdtemp(dir=TMP), http=boom)
        with self.assertRaises(OD.DeskError) as c:
            d2.fetch("5")
        self.assertIn("did not answer", str(c.exception))
        for bad in ("", "x" * 200):
            with self.assertRaises(OD.DeskError):
                d.search(bad)

    @unittest.skipUnless(os.environ.get("NEXXUS_LIVE_NET") == "1", "set NEXXUS_LIVE_NET=1 to check the real Grants.gov API")
    def test_live_grants_gov(self):
        d = OD.Desk(tempfile.mkdtemp(dir=TMP))
        r = d.search("arts", rows=2)
        self.assertTrue(r["hits"])
        o = d.fetch(r["hits"][0]["id"])
        self.assertTrue(o["title"])


class Ledger(unittest.TestCase):
    def test_the_ledger_is_hash_chained_and_tamper_evident(self):
        d, o = Flow().ready()
        d.sign_off(o["id"], "Pat Tester", True)
        d.compile(o["id"])
        ok, n = d.verify_ledger()
        self.assertTrue(ok)
        self.assertGreaterEqual(n, 4)
        lines = open(d._ledger, encoding="utf-8").read().splitlines()
        r = json.loads(lines[1])
        r["detail"] = {"edited": True}
        lines[1] = json.dumps(r, sort_keys=True)
        open(d._ledger, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        self.assertEqual(d.verify_ledger(), (False, 2))


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global srv
        import python_server as srv  # noqa: E402
        cls.http = srv.app.test_client()

    def req(self, method, path, body=None, admin=True):
        return self.http.open(path, method=method, json=body, headers=ADMIN if admin else {})

    def test_everything_needs_the_admin_token(self):
        for method, path in (("GET", "/api/opps"), ("GET", "/api/opps/vault"), ("POST", "/api/opps/vault"), ("POST", "/api/opps/search"), ("POST", "/api/opps/fetch"), ("POST", "/api/opps/add"),
                             ("GET", "/api/opps/m-abc"), ("POST", "/api/opps/m-abc/answer"), ("POST", "/api/opps/m-abc/signoff"), ("POST", "/api/opps/m-abc/compile"), ("GET", "/api/opps/packet/m-abc-20260101-000000/budget.md")):
            self.assertEqual(self.req(method, path, {} if method == "POST" else None, admin=False).status_code, 401, (method, path))

    def test_the_whole_flow_through_the_routes_and_the_download(self):
        r = self.req("GET", "/api/opps/vault")
        self.assertEqual(r.status_code, 200)
        self.assertIn("org.legal_name", [f["path"] for f in r.get_json()["fields"]])
        self.assertEqual(self.req("POST", "/api/opps/vault", {"facts": {"org.entity_type": "spaceship"}}).status_code, 400)
        self.assertEqual(self.req("POST", "/api/opps/vault", {"facts": FACTS}).status_code, 200)
        o = self.req("POST", "/api/opps/add", {"title": "Library Access Grant", "agency": "Test Agency", "applicant_types": ["Small businesses"], "award_floor": 1000, "award_ceiling": 50000}).get_json()["opportunity"]
        a = self.req("GET", "/api/opps/" + o["id"]).get_json()
        self.assertEqual((a["eligibility"]["verdict"], a["gap"]["complete"]), ("eligible", False))
        self.assertEqual(self.req("POST", "/api/opps/%s/compile" % o["id"], {}).status_code, 400)
        self.assertEqual(self.req("POST", "/api/opps/%s/answer" % o["id"], {"documents": {"narrative": NARR, "budget": BUDGET}}).status_code, 200)
        self.assertEqual(self.req("POST", "/api/opps/%s/signoff" % o["id"], {"name": "Pat Tester", "confirm": True}).status_code, 200)
        c = self.req("POST", "/api/opps/%s/compile" % o["id"], {})
        self.assertEqual(c.status_code, 200, c.get_json())
        dl = self.req("GET", "/api/opps/packet/%s/budget.md" % c.get_json()["packet"])
        self.assertEqual(dl.status_code, 200)
        self.assertIn(b"Total", dl.data)
        self.assertIn(self.req("GET", "/api/opps/packet/%s/..%%2Fentity_vault.json" % c.get_json()["packet"]).status_code, (400, 404))
        self.assertEqual(self.req("POST", "/api/opps/fetch", {"id": "abc"}).status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=1)
