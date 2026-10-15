"""test_silos.py - the 32 tools of the six working silos (analyst, content writer, distributer, strategist, technical, visual) do real work on real data,
in a temporary data folder. Run: python test_silos.py"""
import hashlib
import hmac
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import warnings

warnings.simplefilter("ignore", ResourceWarning)
DATA = tempfile.mkdtemp(prefix="sandm_silos_")
os.environ["SANDM_DATA"] = DATA
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import sandm_store as store  # noqa: E402


def eng(silo, tool, cls, cfg, cfg_cls, **over):
    c = store.load_class("silos/%s/config/%s_config.py" % (silo, cfg), cfg_cls)()
    for k, v in over.items():
        setattr(c, k, v)
    return store.load_engine("silos/%s/lib/%s_tool.py" % (silo, tool), cls, c)


def drop(name, records):
    d = os.path.join(DATA, "inbox", name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "r%d.json" % len(os.listdir(d))), "w") as f:
        json.dump(records, f)


class Base(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(DATA, ignore_errors=True)
        os.makedirs(DATA)


class Analyst(Base):
    def test_anomaly_detector_flags_a_metric_spike_and_the_failsafe_obeys_its_switch(self):
        e = eng("analyst", "anomaly_detector", "AnomalyEngine", "anomaly_detector", "AnomalyDetectorConfig")
        drop("metrics", [{"name": "errors", "value": v} for v in (10, 11, 10, 9, 10, 11, 10)] + [{"name": "errors", "value": 100}])
        r = e.scan_for_irregularities()
        self.assertTrue(any(f["source"] == "metrics:errors" for f in r["findings"]), r)
        self.assertFalse(r["is_secure"])
        e.config.AUTO_LOCKDOWN_ENABLED = False
        self.assertEqual(e.initiate_failsafe("CRITICAL"), ["audit_only"])
        self.assertIsNone(store.halted())
        e.config.AUTO_LOCKDOWN_ENABLED = True
        self.assertEqual(e.initiate_failsafe("CRITICAL")[-1], "kill_switch")
        self.assertIsNotNone(store.halted())

    def test_conversion_reporter_computes_from_records_and_never_invents(self):
        e = eng("analyst", "conversion_reporter", "ReporterEngine", "conversion_reporter", "ConversionReporterConfig")
        self.assertEqual(e.generate_financial_summary()["status"], "no_data")
        self.assertIsNone(e.generate_financial_summary()["roi_percentage"])
        drop("sales", [{"revenue": 1000, "cost": 400, "leads": 100, "conversions": 10}])
        s = e.generate_financial_summary()
        self.assertEqual((s["profit"], s["margin_pct"], s["conversion_rate"], s["roi_percentage"]), (600.0, 60.0, 0.1, 150.0))
        f = e.predict_future_yield([100, 110, 120, 130])
        self.assertEqual((f["forecast"], f["trend"]), ([140.0, 150.0, 160.0], "up"))
        self.assertEqual(e.predict_future_yield([1, 2])["status"], "insufficient_data")

    def test_data_aggregator_counts_streams_and_export_masks_personal_data(self):
        e = eng("analyst", "data_aggregator", "DataAggregatorEngine", "data_aggregator", "DataAggregatorConfig")
        drop("leads", [{"who": "anna@example.com", "ip": "10.1.2.3", "note": "token=abc12345"}, {"who": "nobody"}])
        snap = e.sync_all_data_streams()
        self.assertEqual(snap["streams"]["inbox:leads"], 2)
        out = os.path.join(DATA, "export", "x.json")
        res = e.generate_sanitized_export(out)
        text = open(out).read()
        self.assertGreaterEqual(res["redacted_records"], 1)
        for secret in ("anna@example.com", "10.1.2.3", "abc12345"):
            self.assertNotIn(secret, text)

    def test_feedback_looper_prefers_the_style_that_gets_clicks_and_feeds_the_strategist(self):
        e = eng("analyst", "feedback_looper", "FeedbackLooperEngine", "feedback_looper", "FeedbackLooperConfig")
        self.assertEqual(e.optimize_system_flow()["status"], "no_data")
        drop("engagement", [{"style": "A", "views": 1000, "clicks": 100}, {"style": "B", "views": 1000, "clicks": 10}])
        r = e.optimize_system_flow()
        self.assertEqual(r["best_style"], "A")
        w = store.read_json("state/style_weights.json")
        self.assertGreater(w["A"], w["B"])
        task = e.feed_forward_to_strategist(r)
        self.assertIn("favour style A", task["task"])
        self.assertEqual(len(store.read_jsonl("queue/tasks_strategist.jsonl")), 1)

    def test_triad_validator_audits_real_silos_and_proposes_repairs_for_a_typo(self):
        e = eng("analyst", "triad_validator", "TriadValidatorEngine", "triad_validator", "TriadValidatorConfig")
        self.assertEqual(e.audit_silo_structure("nope")["status"], "UNKNOWN_SILO")
        for silo in store.master_config().silos:
            if silo != "governor":
                r = e.audit_silo_structure(silo)
                self.assertEqual((silo, r["status"], r["problems"]), (silo, "INTEGRITY_VERIFIED", []))
        root = tempfile.mkdtemp()
        for d in ("lib", "config"):
            os.makedirs(os.path.join(root, "silos", "x", d))
        w = lambda rel, t: open(os.path.join(root, "silos", "x", *rel.split("/")), "w").write(t)
        w("a.py", "from lib.a_toool import AEngine\nfrom config.a_config import AConfig\n")
        w("lib/a_tool.py", "class AEngine:\n    pass\n")
        w("config/a_config.py", "class AConfig:\n    pass\n")

        class Fake:
            silos = {"x": {"utilities": ["a.py"]}}
            silo_folder = staticmethod(lambda n: os.path.join(root, "silos", n))
        saved, store.master_config = store.master_config, lambda: Fake
        try:
            self.assertEqual(e.audit_silo_structure("x")["status"], "BROKEN")
            fixes = e.repair_broken_references("x")
            self.assertEqual(fixes, {"applied": False, "fixes": [("a.py", "lib.a_toool", "lib.a_tool")]})
            self.assertIn("a_toool", open(os.path.join(root, "silos", "x", "a.py")).read())          # proposing changed nothing
            e.repair_broken_references("x", apply=True)
            self.assertEqual(e.audit_silo_structure("x")["status"], "INTEGRITY_VERIFIED")
        finally:
            store.master_config = saved


class Content(Base):
    def test_narrative_engine_budget_adds_up_and_themes_open_and_close_the_story(self):
        e = eng("content_script_writer", "narrative_engine", "NarrativeEngine", "narrative_engine", "NarrativeEngineConfig")
        arc = e.generate_structure("Why the future of logistics is local")
        self.assertEqual(arc["arc_type"], "THOUGHT_LEADERSHIP")
        self.assertEqual(sum(b["words"] for b in arc["beats"]), arc["target_words"])
        self.assertEqual(e.generate_structure("Growth rate is 40% higher")["arc_type"], "DATA_DRIVEN_STORY")
        themed = e.inject_thematic_elements(arc, ["trust", "speed"])
        self.assertEqual((themed["beats"][0]["theme"], themed["beats"][-1]["theme"]), ("trust", "trust"))
        self.assertNotIn("theme", arc["beats"][0])
        with self.assertRaises(ValueError):
            e.inject_thematic_elements(arc)

    def test_hook_generator_respects_length_and_scores_by_listed_features(self):
        e = eng("content_script_writer", "hook_generator", "HookGeneratorEngine", "hook_generator", "HookGeneratorConfig")
        hooks = e.generate_variations("slow customer onboarding")
        self.assertEqual(len(hooks), 9)
        self.assertTrue(all(len(h["text"]) <= e.config.MAX_HOOK_LENGTH_CHARS for h in hooks))
        good = e.test_hook_efficacy("Why are you still losing 3 hours to onboarding?")
        bad = e.test_hook_efficacy("In today's video we will be talking about onboarding processes and many other related things in general")
        self.assertGreater(good["score"], bad["score"])
        self.assertEqual(good["kind"], "heuristic")

    def test_tone_modifier_applies_its_rules_and_detects_mixed_sentiment(self):
        e = eng("content_script_writer", "tone_modifier", "ToneModifierEngine", "tone_modifier", "ToneModifierConfig")
        self.assertEqual(e.adjust_narrative_voice("We do not wait. It is easy.", "CASUAL")["text"], "We don't wait. It's easy.")
        self.assertEqual(e.adjust_narrative_voice("It's great, don't worry!", "ACADEMIC")["text"], "It is great, do not worry.")
        self.assertEqual(e.adjust_narrative_voice("Perhaps you might want to act", "URGENT")["text"], "you should act")
        with self.assertRaises(ValueError):
            e.adjust_narrative_voice("x", "SHOUTY")
        self.assertTrue(e.validate_sentiment_consistency("This is great. It is simple and easy.")["consistent"])
        self.assertFalse(e.validate_sentiment_consistency("This is great. It is a problem.")["consistent"])

    def test_converter_makes_each_format_and_validates_them(self):
        e = eng("content_script_writer", "multi_format_converter", "FormatConverterEngine", "multi_format_converter", "MultiFormatConverterConfig")
        text = "First point is here. " * 30 + "\n\nSecond paragraph, short."
        out = e.convert_asset(text)
        self.assertEqual(set(out), {"VIDEO_STORYBOARD", "SOCIAL_THREAD", "TECHNICAL_DOC"})
        self.assertEqual(len(out["VIDEO_STORYBOARD"]), 2)
        self.assertTrue(all(len(p) <= 280 for p in out["SOCIAL_THREAD"]) and out["SOCIAL_THREAD"][0].startswith("1/"))
        self.assertTrue(e.validate_format_compliance(out)["compliant"])
        out["SOCIAL_THREAD"][0] = "x" * 300
        self.assertFalse(e.validate_format_compliance(out)["compliant"])
        with self.assertRaises(ValueError):
            e.convert_asset(text, ["PODCAST"])

    def test_compliance_check_finds_blacklist_absolutes_and_queues_remediation(self):
        e = eng("content_script_writer", "asset_compliance_check", "ComplianceEngine", "asset_compliance_check", "AssetComplianceCheckConfig")
        self.assertTrue(e.validate_content("A calm, honest description.")["passed"])
        r = e.validate_content("Guaranteed results with misleading claim a. © 2026 all rights reserved")
        codes = {v["code"] for v in r["violations"]}
        self.assertEqual(codes, {"C-ABSOLUTE", "C-BLACKLIST", "C-COPYRIGHT"})
        self.assertFalse(r["passed"])
        t = e.trigger_remediation(r["violation_code"])
        self.assertEqual(t["priority"], "HIGH")
        with self.assertRaises(ValueError):
            e.trigger_remediation("C-NOPE")


class Distributer(Base):
    def test_affiliate_tracker_pays_capped_commission_and_flags_click_farms(self):
        e = eng("distributer_agent", "affiliate_tracker", "AffiliateEngine", "affiliate_tracker", "AffiliateTrackerConfig")
        self.assertEqual(e.audit_referral_performance()["status"], "no_data")
        t0 = time.time()
        drop("affiliates", [{"partner_id": "farm", "ip": "9.9.9.9", "ts": t0 + i * 0.1} for i in range(30)] +
             [{"partner_id": "good", "clicks": 100, "conversions": 8, "revenue": 200000.0}])
        r = e.audit_referral_performance()
        self.assertEqual(r["active_partners"], 2)
        self.assertEqual(r["partners"]["good"]["commission"], 5000.0)               # 5% of 200000 = 10000, capped at MAX_PAYOUT_LIMIT
        self.assertTrue(r["partners"]["farm"]["flagged"])
        self.assertFalse(r["partners"]["good"]["flagged"])
        self.assertEqual(len(e.detect_fraudulent_clicks("farm")["reasons"]), 2)       # one IP + a burst

    def test_segmenter_finds_groups_and_applies_one(self):
        e = eng("distributer_agent", "audience_segmenter", "SegmenterEngine", "audience_segmenter", "AudienceSegmenterConfig")
        self.assertEqual(e.analyze_audience_data()["status"], "insufficient_data")
        import random
        rng = random.Random(1)
        people = []
        for n, (s, sec, p) in enumerate([(2, 30, 0), (10, 200, 1), (30, 400, 8)]):
            for i in range(60):
                people.append({"user": "u%d_%d" % (n, i), "sessions": s + rng.random(), "avg_seconds": sec + rng.random() * 5, "purchases": p + rng.random() * 0.3})
        drop("audience", people)
        r = e.analyze_audience_data()
        self.assertEqual(r["status"], "ok")
        self.assertGreaterEqual(len(r["segments"]), 3)
        self.assertGreater(r["segments"][0]["profile"]["purchases"], r["segments"][-1]["profile"]["purchases"])      # 0 = the buyers
        self.assertTrue(all(s["size"] >= e.config.MIN_SEGMENT_SIZE for s in r["segments"]))
        self.assertEqual(e.apply_targeted_profile(0)["segment_id"], 0)
        with self.assertRaises(ValueError):
            e.apply_targeted_profile(99)

    def test_engagement_tracker_totals_and_flags_a_missed_kpi(self):
        e = eng("distributer_agent", "engagement_tracker", "EngagementEngine", "engagement_tracker", "EngagementTrackerConfig")
        self.assertEqual(e.collect_metrics()["status"], "no_data")
        self.assertIsNone(e.correlate_with_kpi(e.collect_metrics())["met"])
        drop("engagement", [{"views": 1000, "clicks": 20, "conversions": 2}, {"views": 1000, "clicks": 10, "conversions": 1, "ts": time.time() - 99999}])
        m = e.collect_metrics()
        self.assertEqual((m["views"], m["clicks"], m["ctr"]), (1000, 20, 0.02))             # the record from 99999 s ago is outside the 60-minute window
        k = e.correlate_with_kpi(m)
        self.assertEqual((k["met"], k["target"]), (False, 0.05))
        self.assertTrue(any("below target" in r["action"] for r in store.read_jsonl("logs/audit_trail.log")))

    def test_dispatcher_writes_outboxes_and_knows_delivered_from_sent(self):
        e = eng("distributer_agent", "multi_channels_dispatcher", "DispatcherEngine", "multi_channels_dispatcher", "MultiChannelsDispatcherConfig")
        self.assertFalse(e.dispatch_payloads())
        pid = e.queue_payload({"msg": "hello"}, ["email_relay"])
        with self.assertRaises(ValueError):
            e.queue_payload({}, ["carrier_pigeon"])
        self.assertTrue(e.dispatch_payloads())
        box = os.path.join(DATA, "outbox", "email_relay")
        self.assertEqual(json.load(open(os.path.join(box, pid + ".json")))["payload"], {"msg": "hello"})
        v = e.verify_delivery("email_relay")
        self.assertEqual((v["sent"], v["delivered"], v["waiting"]), (1, 0, [pid]))
        self.assertFalse(e.dispatch_payloads())                                       # backoff: not due yet, so nothing is re-sent
        os.makedirs(os.path.join(box, "acks"))
        json.dump({"ok": True}, open(os.path.join(box, "acks", pid + ".json"), "w"))
        self.assertEqual(e.verify_delivery("email_relay")["delivered"], 1)

    def test_query_manager_accepts_only_signed_requests_and_prioritises(self):
        from importlib import util
        e = eng("distributer_agent", "query_manager", "QueryManagerEngine", "query_manager", "QueryManagerConfig")
        qm = sys.modules.get("sandm_query_manager_tool")
        os.environ.pop("SANDM_REQUEST_SECRET", None)
        req = {"id": "r1", "text": "show the weekly report"}
        self.assertFalse(e.validate_request_integrity(dict(req, sig="x")))
        self.assertIn("cannot be authenticated", e.last_reasons[0])
        os.environ["SANDM_REQUEST_SECRET"] = "s3cret"
        try:
            sign = lambda r: hmac.new(b"s3cret", json.dumps({k: v for k, v in r.items() if k != "sig"}, sort_keys=True).encode(), hashlib.sha256).hexdigest()
            good_a = dict(req, sig=sign(req))
            r2 = {"id": "r2", "text": "publish the launch post"}
            good_b = dict(r2, sig=sign(r2))
            bad = {"id": "r3", "text": "hack", "sig": "00"}
            drop("requests", [good_a, good_b, bad, "junk"])
            self.assertTrue(e.validate_request_integrity(good_a))
            res = e.process_incoming_requests()
            self.assertEqual((res["accepted"], res["rejected"]), (2, 1))                # the bad signature; "junk" is not an object, so the inbox never yields it
            tasks = store.read_jsonl("queue/tasks_distributer_agent.jsonl")
            self.assertEqual([t["id"] for t in tasks], ["r2", "r1"])                  # publish (HIGH) before report (NORMAL)
            self.assertEqual(e.process_incoming_requests(), {"accepted": 0, "rejected": 0, "left_waiting": 0})      # nothing handled twice
        finally:
            os.environ.pop("SANDM_REQUEST_SECRET", None)

    def test_trend_harvester_scores_growth_and_boosts_only_good_viral_topics(self):
        e = eng("distributer_agent", "trend_harvester", "TrendHarvesterEngine", "trend_harvester", "TrendHarvesterConfig")
        self.assertEqual(e.sync_with_market_current()["status"], "no_data")
        drop("trends", [{"topic": "#rocket", "mentions": 5000, "prev_mentions": 100, "sentiment": 0.5}, {"topic": "#scandal", "mentions": 5000, "prev_mentions": 100, "sentiment": -0.7},
                        {"topic": "#flat", "mentions": 100, "prev_mentions": 100}])
        r = e.sync_with_market_current()
        self.assertEqual([t["topic"] for t in r["trending"]][-1], "#flat")
        self.assertEqual(r["trending"][-1]["score"], 0.0)
        self.assertEqual(set(store.read_json("state/priority_boost.json")), {"#rocket"})        # bad news is not ridden


class Strategist(Base):
    def test_blueprint_is_versioned_and_validation_catches_edits(self):
        e = eng("strategist", "blueprint_architect", "BlueprintArchitectEngine", "blueprint_architect", "BlueprintArchitectConfig")
        bp = e.generate_master_blueprint()
        self.assertEqual((bp["version"], len(bp["silos"])), (1, 7))
        self.assertEqual(e.generate_master_blueprint()["version"], 2)
        self.assertTrue(e.validate_architectural_integrity(e.last_path)["valid"])
        bad = json.load(open(e.last_path))
        bad["silos"]["ghost"] = {"utilities": ["x.py"]}
        bad["links"].append({"from": "analyst", "to": "distributer_agent", "channel": "direct"})
        p = os.path.join(DATA, "bad.json")
        json.dump(bad, open(p, "w"))
        problems = " | ".join(e.validate_architectural_integrity(p)["problems"])
        self.assertIn("ghost", problems)
        self.assertIn("not a governor queue", problems)
        self.assertFalse(e.validate_architectural_integrity(os.path.join(DATA, "missing.json"))["valid"])

    def test_competitor_scanner_filters_by_channel_and_relevance_and_rates_threat(self):
        e = eng("strategist", "competitor_insight_scanner", "CompetitorScannerEngine", "competitor_insight_scanner", "CompetitorInsightScannerConfig")
        store.write_json("state/milestones.json", {"keywords": ["routing", "warehouse", "tracking", "api"]})
        drop("competitors", [
            {"competitor": "Acme", "channel": "logistics_industry_feeds", "title": "Acme launches routing and warehouse tracking API", "summary": "price cut too"},
            {"competitor": "Acme", "channel": "logistics_industry_feeds", "title": "Acme picnic", "summary": "company outing"},
            {"competitor": "Beta", "channel": "random_blog", "title": "routing warehouse tracking api launch", "summary": ""}])
        sigs = e.perform_scan()
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0]["threat"]["level"], "HIGH")
        self.assertIn("launches", sigs[0]["threat"]["reasons"])

    def test_resource_allocation_rebalances_by_priority_and_protects_critical(self):
        e = eng("strategist", "resource_allocation_manager", "ResourceAllocationEngine", "resource_allocation_manager", "ResourceAllocationManagerConfig")
        self.assertEqual(e.optimize_distribution()["status"], "no_data")
        store.write_json("state/projects.json", [{"id": "core", "priority": "CRITICAL", "allocated": 500}, {"id": "growth", "priority": "HIGH", "allocated": 500}, {"id": "upkeep", "priority": "MAINTENANCE", "allocated": 4000}])
        r = e.optimize_distribution()
        self.assertEqual(r["status"], "rebalanced")
        self.assertLess(r["was"], r["efficiency_index"])
        alloc = {p["id"]: p["allocated"] for p in store.read_json("state/projects.json")}
        self.assertAlmostEqual(sum(alloc.values()), 5000, places=1)
        self.assertGreater(alloc["core"], alloc["growth"])
        self.assertEqual(e.optimize_distribution()["status"], "balanced")
        moved = e.request_emergency_reallocation("growth", 300)
        self.assertEqual(moved["taken_from"][0]["from"], "upkeep")                  # maintenance gives first
        self.assertEqual({p["id"]: p["allocated"] for p in store.read_json("state/projects.json")}["core"], alloc["core"])
        with self.assertRaises(ValueError):
            e.request_emergency_reallocation("growth", 10 ** 9)

    def test_roi_projection_is_arithmetic_on_given_numbers_with_a_spread_from_history(self):
        e = eng("strategist", "roi_projecter", "ROIProjecterEngine", "roi_projecter", "ROIProjecterConfig")
        self.assertIsNone(e.calculate_projected_roi()["yield_pct"])
        drop("investments", [{"name": "ads", "cost": 1000, "monthly_return": 150, "risk": "LOW", "history": [140, 160, 150, 145, 155]},
                             {"name": "gamble", "cost": 1000, "monthly_return": 900, "risk": "HIGH"}])
        r = e.calculate_projected_roi()
        self.assertEqual((r["investments"], r["cost"], r["expected_return"], r["yield_pct"]), (1, 1000.0, 1800.0, 80.0))     # HIGH risk excluded
        self.assertLess(r["spread_pct"]["p10"], r["spread_pct"]["p90"])
        self.assertTrue(e.validate_budget_alignment(5000)["aligned"])
        e.config.MIN_ACCEPTABLE_YIELD_PCT = 95.0
        self.assertFalse(e.validate_budget_alignment(5000)["aligned"])

    def test_trend_pulse_reads_direction_and_compares_with_the_strategy(self):
        e = eng("strategist", "trend_pulse_utility", "TrendPulseEngine", "trend_pulse_utility", "TrendPulseConfig")
        self.assertEqual(e.capture_current_pulse()["trend"], "unknown")
        now = time.time()
        drop("pulse", [{"value": v, "ts": now - (10 - i) * 3600, "sentiment": 0.2} for i, v in enumerate([10, 10, 11, 10, 14, 15, 16, 17])])
        p = e.capture_current_pulse()
        self.assertEqual(p["trend"], "rising")
        self.assertEqual(p["sentiment"], 0.2)
        self.assertIsNone(e.correlate_pulse_with_strategy(p)["aligned"])
        store.write_json("state/strategy.json", {"expects": "falling"})
        self.assertFalse(e.correlate_pulse_with_strategy(p)["aligned"])
        store.write_json("state/strategy.json", {"expects": "rising"})
        self.assertTrue(e.correlate_pulse_with_strategy(p)["aligned"])


class _Echo(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"echo": json.loads(body)}).encode())


class Technical(Base):
    def test_api_interrogator_probes_local_endpoints_and_refuses_remote_ones(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), _Echo)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = "http://127.0.0.1:%d/health" % srv.server_port
            e = eng("technical_agent", "api_interrogator", "APIInterrogatorEngine", "api_interrogator", "APIInterrogatorConfig", RETRY_ATTEMPTS=1, TIMEOUT_SEC=3)
            self.assertEqual(e.scan_endpoints()["summary"], "0/3 up, 3 not_configured")
            store.write_json("data/config/endpoints.json", {"internal_gateway": {"url": url, "required_keys": ["status"]}, "auth_service": {"url": url, "required_keys": ["token"]},
                                                           "data_vault": {"url": "http://example.com/x"}})
            r = e.scan_endpoints()["endpoints"]
            self.assertEqual((r["internal_gateway"]["status"], r["auth_service"]["status"], r["data_vault"]["status"]), ("up", "schema_mismatch", "blocked"))
            self.assertEqual(e.simulate_request("internal_gateway", {"a": 1})["response"], {"echo": {"a": 1}})
            with self.assertRaises(ValueError):
                e.simulate_request("data_vault", {})
        finally:
            srv.shutdown()

    def test_pipeline_runs_stages_in_order_stops_on_failure_and_needs_the_gatekeeper_to_deploy(self):
        py = sys.executable
        e = eng("technical_agent", "deployment_pipeline", "DeploymentPipelineEngine", "deployment_pipeline", "DeploymentPipelineConfig")
        self.assertFalse(e.execute_pipeline())
        self.assertIn("no pipeline", e.last_run["why"])
        store.write_json("data/config/pipeline.json", {"build": [[py, "-c", "print('built')"]], "test": [[py, "-c", "import sys; sys.exit(0)"]], "rollback": [[py, "-c", "print('{version}')"]]})
        self.assertTrue(e.execute_pipeline())
        good = e.last_run["version"]
        self.assertEqual([s["result"] for s in e.last_run["stages"]], ["passed", "passed", "skipped", "skipped"])
        store.write_json("data/config/pipeline.json", {"build": [[py, "-c", "print(1)"]], "test": [[py, "-c", "import sys; sys.exit(3)"]], "integration": [[py, "-c", "print('never')"]]})
        self.assertFalse(e.execute_pipeline())
        self.assertIn("test failed", e.last_run["why"])
        self.assertEqual(len(e.last_run["stages"]), 2)                               # integration never ran
        store.write_json("data/config/pipeline.json", {"build": [[py, "-c", "print(1)"]], "deploy": [[py, "-c", "print('shipped')"]]})
        time.sleep(1.1)
        self.assertFalse(e.execute_pipeline())
        self.assertEqual(e.last_run["why"], "deployment gatekeeper refused")
        self.assertFalse(e.rollback("20000101-000000")["rolled_back"])
        store.write_json("data/config/pipeline.json", {"rollback": [[py, "-c", "print('{version}')"]]})
        self.assertTrue(e.rollback(good)["rolled_back"])

    def test_repository_auditor_finds_real_problems_and_the_report_is_readable(self):
        src = tempfile.mkdtemp(prefix="audit_src_")
        open(os.path.join(src, "bad.py"), "w").write("import subprocess, hashlib, yaml, requests\nPASSWORD = 'hunter2hunter2'\nx = eval('1')\nsubprocess.run('ls', shell=True)\n"
                                                    "hashlib.md5(b'')\nyaml.load(open('f'))\nrequests.get('u', verify=False)\ntry:\n    pass\nexcept:\n    pass\n")
        open(os.path.join(src, "good.py"), "w").write("import os\nPASSWORD = os.environ.get('PASSWORD')\n")
        e = eng("technical_agent", "repository_auditor", "RepositoryAuditorEngine", "repository_auditor", "RepositoryAuditorConfig", SCAN_TARGET_DIR=src, CHECK_DEPENDENCIES=False)
        self.assertFalse(e.run_audit_cycle())
        rules = {f["rule"] for f in e.findings}
        for needle in ("eval() call", "hard-coded secret", "subprocess with shell=True", "weak hash hashlib.md5", "yaml.load without a Loader", "TLS verification turned off (verify=False)", "bare except that swallows everything"):
            self.assertIn(needle, rules)
        self.assertTrue(all(f["file"].endswith("bad.py") or "bad.py" in f["file"] for f in e.findings))
        rep = e.generate_audit_report()
        self.assertEqual(rep["counts"]["CRITICAL"], 2)
        self.assertIn("eval() call", rep["markdown"])
        open(os.path.join(src, "bad.py"), "w").write("x = 1\n")
        self.assertTrue(e.run_audit_cycle())
        e.config.SCAN_TARGET_DIR = os.path.join(src, "nowhere")
        self.assertFalse(e.run_audit_cycle())                                          # nothing scanned is not 'clean'

    def test_health_monitor_measures_and_alerts_on_a_breach(self):
        try:
            import psutil  # noqa: F401
        except ImportError:
            self.skipTest("psutil missing")
        e = eng("technical_agent", "system_health_monitor", "SystemHealthEngine", "system_health_monitor", "SystemHealthMonitorConfig", ENABLE_AUTO_NOTIFICATIONS=False)
        r = e.perform_diagnostic()
        self.assertTrue(0 <= r["cpu_pct"] <= 100 and 0 < r["memory_pct"] <= 100 and r["disk_latency_ms"] > 0)
        e.config.CPU_THRESHOLD = -1.0
        bad = e.perform_diagnostic()
        self.assertFalse(bad["is_stable"])
        a = e.alert_admin(bad["error_log"])
        self.assertIn("cpu_pct", a["issues"][0])
        self.assertIsNone(e.alert_admin([]))
        self.assertTrue(os.path.getsize(store.resolve(e.log_rel)) > 0)

    def test_version_controller_reads_status_and_commits_only_what_it_is_told_under_the_rules(self):
        if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
            self.skipTest("git missing")
        repo = tempfile.mkdtemp(prefix="vc_")
        run = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, check=True)
        run("init", "-b", "main")
        run("config", "user.email", "t@example.test")
        run("config", "user.name", "t")
        open(os.path.join(repo, "a.txt"), "w").write("1")
        run("add", "a.txt")
        run("commit", "-m", "init")
        e = eng("technical_agent", "version_controller", "VersionControlEngine", "version_controller", "VersionControlConfig")
        e.cwd = repo
        s = e.check_repo_status()
        self.assertEqual((s["status"], s["branch"], s["on_default_branch"], s["dirty_files"], s["ahead"]), ("ok", "main", True, 0, None))
        open(os.path.join(repo, "a.txt"), "w").write("2")
        open(os.path.join(repo, "other.txt"), "w").write("x")
        self.assertEqual(e.check_repo_status()["dirty_files"], 2)
        self.assertFalse(e.commit_changes("fix: a", None)["committed"])
        self.assertIn("message must look like", e.commit_changes("did stuff", ["a.txt"])["why"])
        c = e.commit_changes("fix: update a", ["a.txt"])
        self.assertTrue(c["committed"], c)
        self.assertEqual(c["files"], ["a.txt"])
        self.assertEqual(e.check_repo_status()["dirty_files"], 1)                     # other.txt was not touched
        self.assertIn("nothing changed", e.commit_changes("fix: again", ["a.txt"])["why"])
        e.cwd = tempfile.mkdtemp()
        self.assertEqual(e.check_repo_status()["status"], "no_repo")


class Visual(Base):
    def _lib(self):
        d = store.resolve("assets/ui_components")
        os.makedirs(d, exist_ok=True)
        json.dump({"name": "Header", "version": "1.0.0", "html": "<header>Hi</header>", "css": "header{color:#0a84ff}", "themes": {"light_mode": {"html": "<header class=l>Hi</header>"}}}, open(os.path.join(d, "header.json"), "w"))
        json.dump({"name": "Hero", "version": "1.2.0", "html": "<section>Hero</section>"}, open(os.path.join(d, "hero.json"), "w"))

    def test_component_library_checks_and_serves_components_with_theme_overrides(self):
        e = eng("visual_comercial_maker", "ui_components_library", "UIComponentsEngine", "ui_components_library", "UIComponentsConfig")
        self.assertEqual(e.sync_component_library()["status"], "no_library")
        self._lib()
        d = store.resolve("assets/ui_components")
        json.dump({"name": "Header", "version": "2.0.0", "html": "dupe"}, open(os.path.join(d, "zdupe.json"), "w"))
        json.dump({"name": "Badver", "version": "one", "html": "x"}, open(os.path.join(d, "bad.json"), "w"))
        open(os.path.join(d, "broken.json"), "w").write("{nope")
        r = e.sync_component_library()
        self.assertEqual(r["components"], 2)
        self.assertEqual(len(r["problems"]), 3)
        self.assertEqual(e.get_component("Header", "light_mode")["html"], "<header class=l>Hi</header>")
        self.assertEqual(e.get_component("Header")["html"], "<header>Hi</header>")
        with self.assertRaises(KeyError):
            e.get_component("Nope")

    def test_style_sheets_compile_from_tokens_and_brand_consistency_is_checked(self):
        e = eng("visual_comercial_maker", "style_sheet_synchronizer", "StyleSheetEngine", "style_sheet_synchronizer", "StyleSheetSynchronizerConfig")
        self.assertFalse(e.sync_global_styles())
        store.write_json("assets/design_tokens.json", {"color": {"primary": "#0a84ff", "ink": "#111"}, "space": {"1": "4px"}, "font": {"body": "Inter, sans-serif"}})
        out = store.resolve("assets/compiled_styles")
        os.makedirs(out)
        open(os.path.join(out, "site.css"), "w").write("a{x:1}\n/* tokens:start */\nold\n/* tokens:end */\nb{y:2}\n")
        self.assertTrue(e.sync_global_styles())
        css = open(os.path.join(out, "tokens.css")).read()
        self.assertIn("--color-primary: #0a84ff;", css)
        site = open(os.path.join(out, "site.css")).read()
        self.assertIn("--space-1: 4px;", site)
        self.assertNotIn("old", site)
        self.assertIn("b{y:2}", site)
        page = os.path.join(DATA, "page.css")
        open(page, "w").write("a{color:#0A84FF;background:#111}b{color:#ff0000}")
        r = e.validate_brand_consistency(page)
        self.assertEqual((r["consistent"], r["off_brand_colors"]), (False, ["#ff0000"]))
        store.write_json("assets/design_tokens.json", {"color": {"primary": "red"}})
        self.assertFalse(e.sync_global_styles())
        self.assertIn("bad value", e.last_problems[0])

    def test_aesthetics_enforcer_checks_palette_fonts_and_image_size(self):
        e = eng("visual_comercial_maker", "aesthetics_enforcer", "AestheticsEnforcerEngine", "aesthetics_enforcer", "AestheticsEnforcerConfig")
        self.assertFalse(e.verify_visual_integrity())
        self.assertEqual(e.violations[0][1], "no_style_guide")
        store.write_json("assets/style_guides/master_aesthetic.json", {"palette": ["#0a84ff", "#111111"], "allowed_fonts": ["Inter"], "max_image_size": [400, 300]})
        rend = store.resolve("assets/rendered")
        os.makedirs(rend)
        open(os.path.join(rend, "ok.css"), "w").write("a{color:#0a84ff;font-family:Inter, sans-serif}")
        self.assertTrue(e.verify_visual_integrity())
        open(os.path.join(rend, "bad.css"), "w").write("a{color:#ff2200;font-family:'Comic Sans MS'}")
        try:
            from PIL import Image
            Image.new("RGB", (800, 600), (10, 132, 255)).save(os.path.join(rend, "big.png"))
        except ImportError:
            pass
        self.assertFalse(e.verify_visual_integrity())
        kinds = {(a, k) for a, k, _ in e.violations}
        self.assertIn(("bad.css", "off_palette_color"), kinds)
        self.assertIn(("bad.css", "font_not_allowed"), kinds)
        self.assertNotIn(("ok.css", "off_palette_color"), kinds)
        if os.path.exists(os.path.join(rend, "big.png")):
            self.assertIn(("big.png", "image_too_large"), kinds)
        self.assertGreaterEqual(len(store.read_jsonl("breaches.jsonl")), 3)
        self.assertTrue(store.read_jsonl("queue/tasks_visual_comercial_maker.jsonl"))

    def test_asset_optimizer_never_makes_a_file_bigger_and_says_what_it_skipped(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow missing")
        e = eng("visual_comercial_maker", "asset_optimizer", "AssetOptimizerEngine", "asset_optimizer", "AssetOptimizerConfig")
        self.assertFalse(e.optimize_directory())                                       # no input folder
        src = store.resolve("assets/raw")
        os.makedirs(src)
        import random
        rng = random.Random(3)
        photo = Image.new("RGB", (160, 120))
        photo.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(160 * 120)])
        photo.save(os.path.join(src, "noise.jpg"), quality=100)
        Image.new("RGB", (200, 200), (255, 255, 255)).save(os.path.join(src, "flat.png"))
        open(os.path.join(src, "notes.txt"), "w").write("not an asset")
        self.assertTrue(e.optimize_directory(), e.report)
        out = store.resolve("assets/optimized")
        by = {r["file"]: r for r in e.report}
        self.assertLess(by["noise.jpg"]["new_bytes"], by["noise.jpg"]["original_bytes"])
        self.assertTrue(all(r["new_bytes"] <= r["original_bytes"] for r in e.report))
        self.assertNotIn("notes.txt", os.listdir(out))
        v = e.validate_compression_ratio(1000, 1500)
        self.assertEqual((v["ok"], v["why"]), (False, "the file grew"))
        self.assertFalse(e.validate_compression_ratio(1000, 50)["ok"])
        self.assertTrue(e.validate_compression_ratio(1000, 600)["ok"])

    def test_prototype_renderer_assembles_a_page_and_is_honest_about_formats(self):
        e = eng("visual_comercial_maker", "prototype_renderer", "PrototypeRendererEngine", "prototype_renderer", "PrototypeRendererConfig")
        self.assertFalse(e.render_active_prototype())
        self.assertIn("no prototype spec", e.last_error)
        self._lib()
        store.write_json("state/prototype.json", {"title": "Landing <test>", "theme": "dark_mode", "components": ["Header", "Missing"]})
        self.assertFalse(e.render_active_prototype())
        self.assertIn("Missing", e.last_error)
        out = store.resolve("assets/compiled_styles")
        os.makedirs(out)
        open(os.path.join(out, "tokens.css"), "w").write(":root{--c:1}")
        store.write_json("state/prototype.json", {"title": "Landing <test>", "theme": "dark_mode", "components": ["Header", "Hero"]})
        self.assertTrue(e.render_active_prototype())
        page = open(e.output, encoding="utf-8").read()
        for needle in ("<header>Hi</header>", "<section>Hero</section>", "--c:1", "Landing &lt;test&gt;", "header{color:#0a84ff}"):
            self.assertIn(needle, page)
        self.assertTrue(e.export_preview("html")["exported"])
        self.assertTrue(e.export_preview("json")["exported"])
        for fmt in ("png", "mp4"):
            r = e.export_preview(fmt)
            self.assertFalse(r["exported"])
            self.assertIn("no renderer", r["why"])
        self.assertFalse(e.export_preview("gif")["exported"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
