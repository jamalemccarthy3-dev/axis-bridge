"""test_orchestrator_bus.py - the bus rules, one by one. Run: python test_orchestrator_bus.py"""
import json
import os
import tempfile
import unittest

from orchestrator_bus import BusError, OrchestratorBus, sha256_file

SECRET = "unit-test-secret"


class Rules(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="bus_")
        self.now = [1_000_000.0]
        self.bus = OrchestratorBus(os.path.join(self.dir, "ledger.jsonl"), SECRET, clock=lambda: self.now[0])
        self.bus.register_orchestrator("axis-video_creator", "video_creator.governor")
        self.bus.register_orchestrator("axis-validator", "validator.governor", qc_reviewer=True)
        self.artifact = os.path.join(self.dir, "video.mp4")
        with open(self.artifact, "wb") as f:
            f.write(b"first cut")

    def env(self, sender, kind, **body):
        return self.bus.make_envelope(sender, "nexxus", kind, body)

    def order_built(self):
        o = self.bus.send_order("axis-video_creator", "video_creator.governor", {"make": "intro"})
        self.bus.receive(self.env("video_creator.governor", "ack", order_id=o["id"]))
        self.bus.receive(self.env("video_creator.governor", "built", order_id=o["id"], artifact=self.artifact))
        return o["id"]

    def qc(self, oid, verdict="pass", sha=None, findings=None, sender="validator.governor"):
        return self.bus.receive(self.env(sender, "qc", order_id=oid, verdict=verdict, findings=findings or [],
                                         artifact_sha256=sha or sha256_file(self.artifact)))

    # ---- who can be addressed
    def test_orders_to_a_silo_are_refused(self):
        with self.assertRaisesRegex(BusError, "never to a silo"):
            self.bus.send_order("axis-video_creator", "video_creator.silos.cgi", {})

    def test_engine_without_orchestrator_is_refused(self):
        with self.assertRaisesRegex(BusError, "no registered orchestrator"):
            self.bus.send_order("axis-unknown", "x", {})

    def test_a_silo_cannot_speak_to_nexxus(self):
        o = self.bus.send_order("axis-video_creator", "video_creator.governor", {})
        with self.assertRaisesRegex(BusError, "not a registered orchestrator"):
            self.bus.receive(self.env("video_creator.silos.cgi", "ack", order_id=o["id"]))

    # ---- signatures
    def test_forged_and_changed_messages_are_refused(self):
        o = self.bus.send_order("axis-video_creator", "video_creator.governor", {})
        e = self.env("video_creator.governor", "ack", order_id=o["id"])
        e["body"]["order_id"] = "ord_other"
        with self.assertRaisesRegex(BusError, "forged"):
            self.bus.receive(e)
        forged = self.env("video_creator.governor", "ack", order_id=o["id"])
        forged["sig"] = "0" * 64
        with self.assertRaisesRegex(BusError, "forged"):
            self.bus.receive(forged)

    def test_replay_and_stale_messages_are_refused(self):
        o = self.bus.send_order("axis-video_creator", "video_creator.governor", {})
        e = self.env("video_creator.governor", "ack", order_id=o["id"])
        self.bus.receive(e)
        with self.assertRaisesRegex(BusError, "replayed"):
            self.bus.receive(e)
        old = self.env("video_creator.governor", "ack", order_id=o["id"])
        self.now[0] += 120
        with self.assertRaisesRegex(BusError, "stale"):
            self.bus.receive(old)

    # ---- no skipping
    def test_states_cannot_be_skipped(self):
        o = self.bus.send_order("axis-video_creator", "video_creator.governor", {})
        with self.assertRaisesRegex(BusError, "no state can be skipped"):
            self.bus.receive(self.env("video_creator.governor", "built", order_id=o["id"], artifact=self.artifact))
        with self.assertRaisesRegex(BusError, "no state can be skipped"):
            self.bus.accept(o["id"])

    def test_a_build_must_name_a_real_file(self):
        o = self.bus.send_order("axis-video_creator", "video_creator.governor", {})
        self.bus.receive(self.env("video_creator.governor", "ack", order_id=o["id"]))
        with self.assertRaisesRegex(BusError, "artifact file that exists"):
            self.bus.receive(self.env("video_creator.governor", "built", order_id=o["id"], artifact=os.path.join(self.dir, "nope.mp4")))

    # ---- quality control cannot be cheated
    def test_a_builder_cannot_grade_its_own_work(self):
        oid = self.order_built()
        self.bus.qc_reviewers.add("axis-video_creator")           # even if someone registered it as a reviewer
        with self.assertRaisesRegex(BusError, "grade its own work"):
            self.qc(oid, sender="video_creator.governor")

    def test_only_registered_reviewers_can_issue_a_verdict(self):
        oid = self.order_built()
        self.bus.register_orchestrator("axis-other", "other.governor")
        with self.assertRaisesRegex(BusError, "not a registered quality-control reviewer"):
            self.qc(oid, sender="other.governor")

    def test_pass_must_name_the_exact_artifact(self):
        oid = self.order_built()
        with self.assertRaisesRegex(BusError, "exact artifact"):
            self.qc(oid, sha="f" * 64)

    def test_a_critical_finding_cannot_pass(self):
        oid = self.order_built()
        with self.assertRaisesRegex(BusError, "critical finding"):
            self.qc(oid, findings=[{"severity": "critical", "message": "audio clipped"}])

    def test_artifact_changed_after_the_build_is_refused_at_qc(self):
        oid = self.order_built()
        with open(self.artifact, "wb") as f:
            f.write(b"swapped after the build")
        with self.assertRaisesRegex(BusError, "changed"):
            self.qc(oid, sha=sha256_file(self.artifact))

    def test_artifact_changed_after_qc_is_refused_at_accept(self):
        oid = self.order_built()
        self.qc(oid)
        with open(self.artifact, "wb") as f:
            f.write(b"swapped after QC")
        with self.assertRaisesRegex(BusError, "no longer matches"):
            self.bus.accept(oid)

    def test_a_failed_qc_sends_it_back_and_it_cannot_be_accepted(self):
        oid = self.order_built()
        self.qc(oid, verdict="fail", findings=[{"severity": "warning", "message": "colour banding"}])
        self.assertEqual(self.bus.status(oid)["state"], "ACKED")
        with self.assertRaisesRegex(BusError, "no state can be skipped"):
            self.bus.accept(oid)

    def test_nexxus_runs_its_own_check_at_accept(self):
        oid = self.order_built()
        self.qc(oid)
        self.bus.nexxus_checks.append(lambda order, path: [{"severity": "critical", "message": "file too small"}])
        with self.assertRaisesRegex(BusError, "own checks refused"):
            self.bus.accept(oid)
        self.assertEqual(self.bus.status(oid)["state"], "REJECTED")

    def test_the_honest_path_ends_in_accepted(self):
        oid = self.order_built()
        self.qc(oid)
        self.assertEqual(self.bus.accept(oid)["state"], "ACCEPTED")

    # ---- the record
    def test_ledger_detects_tampering(self):
        oid = self.order_built()
        self.qc(oid)
        self.assertTrue(self.bus.verify_ledger()[0])
        lines = open(self.bus.ledger_path, encoding="utf-8").read().splitlines()
        e = json.loads(lines[3])
        e["data"]["state"] = "ACCEPTED"
        lines[3] = json.dumps(e, sort_keys=True)
        open(self.bus.ledger_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        self.assertFalse(self.bus.verify_ledger()[0])
        with self.assertRaisesRegex(BusError, "tampered"):
            OrchestratorBus(self.bus.ledger_path, SECRET)

    def test_ledger_detects_a_removed_entry(self):
        self.order_built()
        lines = open(self.bus.ledger_path, encoding="utf-8").read().splitlines()
        del lines[2]
        open(self.bus.ledger_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        self.assertFalse(self.bus.verify_ledger()[0])

    def test_state_survives_a_restart(self):
        oid = self.order_built()
        self.qc(oid)
        again = OrchestratorBus(self.bus.ledger_path, SECRET, clock=lambda: self.now[0])
        self.assertEqual(again.status(oid)["state"], "QC_PASSED")
        self.assertIn("axis-validator", again.qc_reviewers)
        self.assertEqual(again.accept(oid)["state"], "ACCEPTED")

    def test_no_secret_no_bus(self):
        os.environ.pop("NEXXUS_GOVERNANCE_SECRET", None)
        with self.assertRaisesRegex(BusError, "no signing secret"):
            OrchestratorBus(os.path.join(self.dir, "x.jsonl"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
