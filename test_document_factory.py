"""test_document_factory.py - the Document Factory: every document type builds from facts only, money is exact, contracts refuse to invent a jurisdiction and say they are templates, invoices never invent
payment details, HTML is escaped, files are written atomically inside the output folder, missing facts become questions, nexxus_paths falls back when the drive is absent, and nexxus_talks routes natural
language to the factory (without hijacking ordinary chat). Run: python test_document_factory.py"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
sys.path.insert(0, NEXUS)
sys.path.insert(0, ROOT)
import document_factory as df  # noqa: E402
import nexxus_paths  # noqa: E402

A = {"name": "Acme Studio LLC", "address": "1 Main St, Portland, OR 97201", "signatory": "Pat Rivera"}
B = {"name": "Beta Clinic", "address": "2 Oak Ave, Salem, OR 97301"}


def proposal(**over):
    p = {"title": "Booking site", "provider": A, "client": B, "summary": "We will build a booking site so patients can book online.",
         "scope": [{"name": "Booking pages", "description": "Five pages", "acceptance": "All five pages live and linked"}], "timeline": [{"milestone": "Design", "due": "2099-01-10"}, {"milestone": "Launch", "due": "2099-02-01"}],
         "pricing": [{"description": "Design", "quantity": 1, "unit_price": "1200.10"}, {"description": "Build (hours)", "quantity": "10.5", "unit_price": "95"}], "date": "2098-12-01"}
    p.update(over)
    return p


def contract(**over):
    p = {"parties": [dict(B, role="Client"), dict(A, role="Provider")], "effective_date": "2099-01-01", "services": "Build and host a booking site.", "fee_total": "1000.00",
         "payment_schedule": [{"due": "On signing", "percent": 33}, {"due": "On launch", "percent": 67}], "governing_law": "the laws of the State of Oregon, USA", "term": {"months": 6}}
    p.update(over)
    return p


def invoice(**over):
    p = {"invoice_number": "INV-0007", "issue_date": "2099-03-01", "seller": A, "buyer": B, "items": [{"description": "Design", "quantity": 3, "unit_price": "19.99"}, {"description": "Hosting", "quantity": 1, "unit_price": "10"}],
         "terms_days": 30}
    p.update(over)
    return p


class Types(unittest.TestCase):
    def test_every_alias_builds_the_right_class(self):
        self.assertEqual(df.DocumentFactory.known_types(), ["billing", "contract", "invoice", "legal", "proposal", "sow"])
        self.assertEqual(df.DocumentFactory.create_doc("proposal", proposal())["kind"], "proposal")
        self.assertEqual(df.DocumentFactory.create_doc("SOW", proposal())["doc_type"], "sow")
        self.assertEqual(df.DocumentFactory.create_doc("legal", contract())["kind"], "contract")
        self.assertEqual(df.DocumentFactory.create_doc("billing", invoice())["kind"], "invoice")
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.create_doc("novel", {})
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.create_doc("invoice", "not a dict")

    def test_base_is_abstract_and_extensible(self):
        with self.assertRaises(TypeError):
            df.BaseDocument()

        class Memo(df.BaseDocument):
            kind = "memo"
            def _read(self, p): return {"t": p.get("t")}, ([] if p.get("t") else ["t is required"])
            def _compose(self, c): return "Memo", "m", [("h1", c["t"])], [], {}
        df.DocumentFactory.register("memo", Memo)
        try:
            self.assertIn("# Hello", df.DocumentFactory.create_doc("memo", {"t": "Hello"})["markdown"])
            with self.assertRaises(df.DocumentError):
                df.DocumentFactory.create_doc("memo", {})
        finally:
            df.DocumentFactory._REGISTRY.pop("memo", None)
            df.DocumentFactory._CANON.pop("memo", None)
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.register("x", dict)


class Money(unittest.TestCase):
    def test_proposal_totals_are_exact_decimals(self):
        d = df.DocumentFactory.create_doc("proposal", proposal(tax_rate="8.5"))
        t = d["data"]["totals"]
        self.assertEqual((t["subtotal"], t["tax"], t["total"]), ("2197.60", "186.80", "2384.40"))     # 1200.10 + 997.50 ; 8.5% of 2197.60 = 186.796 -> 186.80
        self.assertIn("$2,384.40", d["markdown"])

    def test_invoice_recomputes_and_never_trusts_a_supplied_total(self):
        d = df.DocumentFactory.create_doc("invoice", invoice(total="1.00", tax_rate="10", discount_percent="10"))
        t = d["data"]["totals"]
        self.assertEqual((t["subtotal"], t["discount"], t["tax"], t["total"]), ("69.97", "7.00", "6.30", "69.27"))
        self.assertEqual(d["data"]["due_date"], "2099-03-31")

    def test_invoice_rules(self):
        for bad, why in ((dict(items=[]), "at least one"), (dict(items=[{"description": "x", "quantity": 0, "unit_price": 1}]), "more than 0"), (dict(items=[{"description": "x", "quantity": 1, "unit_price": "abc"}]), "amount"),
                         (dict(tax_rate="5", items=[{"description": "x", "quantity": 1, "unit_price": 1, "tax_rate": 5}]), "not both"), (dict(discount_percent=5, discount_amount=1), "not both"),
                         (dict(due_date="2099-02-01"), "before the issue date"), (dict(discount_amount="9999"), "larger than the subtotal")):
            with self.assertRaises(df.DocumentError, msg=why) as cm:
                df.DocumentFactory.create_doc("invoice", invoice(**bad))
            self.assertIn(why, "; ".join(cm.exception.problems), bad)

    def test_payment_details_are_never_invented(self):
        d = df.DocumentFactory.create_doc("invoice", invoice())
        self.assertNotIn("IBAN", d["markdown"] + "routing" )
        self.assertTrue(any("no payment instructions" in w for w in d["warnings"]))
        d2 = df.DocumentFactory.create_doc("invoice", invoice(payment_instructions="Pay by cheque to Acme Studio LLC."))
        self.assertIn("Pay by cheque", d2["markdown"])
        self.assertEqual(d2["warnings"], [])


class Contracts(unittest.TestCase):
    def test_governing_law_is_never_assumed(self):
        p = contract()
        del p["governing_law"]
        with self.assertRaises(df.DocumentError) as cm:
            df.DocumentFactory.create_doc("contract", p)
        self.assertIn("governing_law", "; ".join(cm.exception.problems))

    def test_template_banner_and_review_flag_and_defaults_listed(self):
        d = df.DocumentFactory.create_doc("contract", contract())
        self.assertTrue(d["requires_review"] and d["data"]["requires_legal_review"])
        self.assertIn("NOT", d["markdown"].upper())
        self.assertIn("not legal advice", d["markdown"])
        self.assertTrue(any("limitation of liability" in w for w in d["warnings"]))
        self.assertIn("the laws of the State of Oregon", d["markdown"])

    def test_schedule_must_add_up_and_percent_rounding_lands_exactly(self):
        with self.assertRaises(df.DocumentError) as cm:
            df.DocumentFactory.create_doc("contract", contract(payment_schedule=[{"due": "a", "amount": "400"}, {"due": "b", "amount": "500"}]))
        self.assertIn("adds up to 900.00 but the total fee is 1000.00", "; ".join(cm.exception.problems))
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.create_doc("contract", contract(payment_schedule=[{"due": "a", "percent": 50}, {"due": "b", "percent": 40}]))
        d = df.DocumentFactory.create_doc("contract", contract(fee_total="100.00", payment_schedule=[{"due": "a", "percent": "33.33"}, {"due": "b", "percent": "33.33"}, {"due": "c", "percent": "33.34"}]))
        self.assertIn("$33.33", d["markdown"])
        self.assertIn("$33.34", d["markdown"])
        d = df.DocumentFactory.create_doc("contract", contract(fee_total="0.10", payment_schedule=[{"due": "a", "percent": 33}, {"due": "b", "percent": 33}, {"due": "c", "percent": 34}]))
        amounts = [Decimal(x) for x in __import__("re").findall(r"\$(\d+\.\d\d)", d["markdown"].split("Fees and payment")[1].split("Term and")[0])]
        self.assertEqual(sum(amounts[1:]), Decimal("0.10"))                                  # the instalments always equal the fee exactly

    def test_roles_and_term_and_clause_options(self):
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.create_doc("contract", contract(parties=[dict(A, role="Client"), dict(B, role="Client")]))
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.create_doc("contract", contract(term={"end_date": "2098-01-01"}))
        d = df.DocumentFactory.create_doc("contract", contract(clauses=["confidentiality"], ip_ownership="provider", liability_cap="the fees paid in the previous 3 months", late_payment_interest="1.5"))
        self.assertNotIn("Confidentiality", d["markdown"])
        self.assertIn("The Provider owns the deliverables", d["markdown"])
        self.assertIn("previous 3 months", d["markdown"])
        self.assertIn("1.50% per month", d["markdown"])
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.create_doc("contract", contract(clauses=["made_up"]))


class Proposals(unittest.TestCase):
    def test_sow_demands_acceptance_criteria_and_has_change_control(self):
        p = proposal(scope=[{"name": "Pages"}])
        df.DocumentFactory.create_doc("proposal", p)                                          # a proposal does not need them
        with self.assertRaises(df.DocumentError) as cm:
            df.DocumentFactory.create_doc("sow", p)
        self.assertIn("acceptance criteria", "; ".join(cm.exception.problems))
        d = df.DocumentFactory.create_doc("sow", proposal())
        self.assertIn("Change control", d["markdown"])
        self.assertIn("Valid until", d["markdown"])

    def test_timeline_order_and_dates(self):
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.create_doc("proposal", proposal(timeline=[{"milestone": "b", "due": "2099-03-01"}, {"milestone": "a", "due": "2099-02-01"}]))
        d = df.DocumentFactory.create_doc("proposal", proposal(timeline=[{"milestone": "Kickoff", "due": "week 1"}]))
        self.assertIn("week 1", d["markdown"])

    def test_all_problems_are_reported_together(self):
        with self.assertRaises(df.DocumentError) as cm:
            df.DocumentFactory.create_doc("proposal", {})
        self.assertGreaterEqual(len(cm.exception.problems), 6)


class Safety(unittest.TestCase):
    def test_html_is_escaped_and_self_contained(self):
        evil = "<script>alert(1)</script>"
        d = df.DocumentFactory.create_doc("invoice", invoice(buyer=dict(B, name=evil), notes=evil))
        self.assertNotIn("<script>alert", d["html"])
        self.assertIn("&lt;script&gt;", d["html"])
        self.assertNotIn("http://", d["html"].replace("http://www.w3.org", ""))
        self.assertNotIn("<link", d["html"])

    def test_bad_text_is_refused(self):
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.create_doc("invoice", invoice(notes="x\x00y"))
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.create_doc("invoice", invoice(notes="x" * 5000))
        with self.assertRaises(df.DocumentError):
            df.DocumentFactory.create_doc("invoice", invoice(items=[{"description": "d", "quantity": 1, "unit_price": "1"}] * 201))

    def test_save_is_atomic_inside_the_folder_and_hashed(self):
        tmp = tempfile.mkdtemp()
        try:
            d = df.DocumentFactory.create_doc("invoice", invoice())
            s = df.save_document(d, tmp)
            self.assertEqual(len(s["files"]), 3)
            for name, sha in s["files"].items():
                import hashlib
                self.assertEqual(hashlib.sha256((Path(tmp) / name).read_bytes()).hexdigest(), sha)
            self.assertEqual([p for p in os.listdir(tmp) if p.endswith(".tmp")], [])
            self.assertEqual(json.load(open(next(Path(tmp).glob("*.json")), encoding="utf-8"))["kind"], "invoice")
            bad = dict(d, number="../../escape")
            s2 = df.save_document(bad, tmp)                                                   # a hostile number becomes a plain slug, still inside the folder
            self.assertTrue(all(Path(tmp) in (Path(tmp) / n).resolve().parents for n in s2["files"]))
        finally:
            shutil.rmtree(tmp, True)


class Prompts(unittest.TestCase):
    def test_detect_type(self):
        D = df.DocumentFactory.detect_type
        self.assertEqual(D("write me a proposal for a website"), "proposal")
        self.assertEqual(D("draft a statement of work"), "sow")
        self.assertEqual(D("I need a contract for a freelancer"), "contract")
        self.assertEqual(D("create an invoice for Beta"), "invoice")
        for chatty in ("show me the stats", "what is a contract?", "tell me about the invoice from last week", "hello there", "I signed the contract yesterday"):
            self.assertIsNone(D(chatty), chatty)

    def test_missing_facts_become_questions_never_filler(self):
        r = df.DocumentFactory.handle_prompt("write me an invoice for Beta Clinic")
        self.assertEqual(r["status"], "needs")
        self.assertIn("Invoice number", r["message"])
        self.assertIn("never fill facts in", r["message"])
        r = df.DocumentFactory.handle_prompt("create a contract\ngoverning_law: the laws of Oregon")
        self.assertEqual(r["status"], "needs")
        self.assertEqual(r["have"], ["governing_law"])
        self.assertNotIn("Governing law", r["message"])

    def test_payload_parsing_and_build_from_a_message(self):
        tmp = tempfile.mkdtemp()
        try:
            msg = "create an invoice " + json.dumps(invoice())
            r = df.DocumentFactory.handle_prompt(msg, out_dir=tmp)
            self.assertEqual(r["status"], "built", r)
            self.assertEqual(len(r["files"]), 3)
            self.assertIn("Saved to", r["message"])
            r = df.DocumentFactory.handle_prompt("create an invoice\ninvoice_number: 12\nissue_date: today\nseller: " + json.dumps(A) + "\nbuyer: " + json.dumps(B) + "\nitems: " + json.dumps([{"description": "Work", "quantity": 2, "unit_price": 50}]) + "\nterms_days: 14", out_dir=tmp)
            self.assertEqual(r["status"], "built", r)
            r = df.DocumentFactory.handle_prompt("create an invoice " + json.dumps(invoice(items=[{"description": "x", "quantity": 1, "unit_price": "-5"}])), out_dir=tmp)
            self.assertEqual(r["status"], "needs")                                           # the bad amount is asked about, not repaired
            r = df.DocumentFactory.handle_prompt("create a contract " + json.dumps(contract()), out_dir=tmp)
            self.assertEqual(r["status"], "built")
            self.assertTrue(r["requires_review"])
            self.assertIn("lawyer", r["message"])
        finally:
            shutil.rmtree(tmp, True)

    def test_a_model_draft_is_validated_like_typed_facts(self):
        r = df.DocumentFactory.handle_prompt("write a proposal for a website", llm=lambda p: '{"title": "Site", "summary": "x"}')
        self.assertEqual(r["status"], "needs")
        self.assertIn("provider", " ".join(n["field"] or "" for n in r["needs"]))


class Paths(unittest.TestCase):
    def test_config_is_read_without_importing_master_config(self):
        cfg = nexxus_paths.read_config(["DOCUMENT_FACTORY_ENABLED", "DOC_FACTORY_OUTPUT_DIR", "NEXXUS_HOME", "NOPE"])
        self.assertIs(cfg["DOCUMENT_FACTORY_ENABLED"], True)
        self.assertEqual(cfg["DOC_FACTORY_OUTPUT_DIR"], r"D:\NEXXUS\data\documents")
        self.assertNotIn("NOPE", cfg)
        self.assertNotIn("master_config", sys.modules)

    def test_missing_drive_falls_back_and_says_so(self):
        tmp = tempfile.mkdtemp()
        try:
            r = nexxus_paths.resolve_dir(r"Q:\nowhere\docs", "documents", None, create=False)
            if os.name == "nt" and not os.path.exists("Q:\\"):
                self.assertTrue(r["used_fallback"])
                self.assertIn("not available", r["reason"])
            os.environ["NEXXUS_TEST_DIR"] = os.path.join(tmp, "x")
            r = nexxus_paths.resolve_dir(r"Q:\nowhere", "documents", "NEXXUS_TEST_DIR")
            self.assertFalse(r["used_fallback"])
            self.assertTrue(os.path.isdir(r["path"]))
            r = nexxus_paths.resolve_dir(tmp, "documents", None)
            self.assertEqual(str(r["path"]), tmp)
        finally:
            os.environ.pop("NEXXUS_TEST_DIR", None)
            shutil.rmtree(tmp, True)


class Routing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(ROOT)
        import nexxus_talks
        cls.nt = nexxus_talks

    def test_bot_is_registered_and_registry_has_a_match_hook(self):
        self.assertIn("document-factory", self.nt.BOT_REGISTRY)
        self.assertTrue(callable(self.nt.BOT_REGISTRY["document-factory"]["match"]))

    def test_natural_language_is_routed_and_chat_is_not_hijacked(self):
        r = self.nt.route_to_bot("write me a statement of work for a rebrand")
        self.assertEqual(r["bot_id"], "document-factory")
        self.assertEqual(r["result"]["status"], "needs")
        self.assertIn("message", r["result"])
        for chat in ("show me what you can do", "what is a contract?", "how is my health check", "tell me a story about an invoice"):
            hit = self.nt.route_to_bot(chat)
            self.assertNotEqual((hit or {}).get("bot_id"), "document-factory", chat)

    def test_a_bot_with_a_broken_match_does_not_break_routing(self):
        self.nt.register_bot("boom-bot", "Boom", "x", ["zzzunlikelyzzz"], match=lambda p: 1 / 0)
        try:
            self.assertIsNone(self.nt.route_to_bot("zzzunlikelyzzz please"))
        finally:
            self.nt.BOT_REGISTRY.pop("boom-bot", None)


if __name__ == "__main__":
    unittest.main(verbosity=1)
