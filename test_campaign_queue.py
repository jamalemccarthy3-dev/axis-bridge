"""test_campaign_queue.py - nothing leaves the campaign queue without the owner's approval: staging is checked and harmless, approving is one item at a time and goes stale if a file changes, exporting
writes a package (copy, hashed files, schedule, exact steps, disclosure) and posts nothing, and the ledger is tamper-evident. Run: python test_campaign_queue.py"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import campaign_kit as CK  # noqa: E402
import campaign_queue as CQ  # noqa: E402
from test_campaign_kit import PROFILE  # noqa: E402


def setup():
    d = tempfile.mkdtemp()
    kit = CK.generate(PROFILE)
    CK.write_kit(os.path.join(d, "kit"), kit)
    open(os.path.join(d, "kit", "spot.mp4"), "wb").write(b"\x00\x00\x00\x18ftypisom" + b"\x01" * 400)
    return d, os.path.join(d, "kit"), kit, CQ.CampaignQueue(os.path.join(d, "q"))


class Staging(unittest.TestCase):
    def test_each_channel_stages_with_its_own_payload(self):
        d, kd, kit, q = setup()
        for ch in ("linkedin", "meta", "native", "google_ads", "email", "landing"):
            i = q.stage(kd, kit, ch)
            self.assertEqual((i["state"], i["channel"]), ("staged", ch))
        v = q.stage(kd, kit, "youtube", video="spot.mp4")
        self.assertIn("AI-assisted", v["payload"]["description"])
        self.assertEqual(q.stage(kd, kit, "tiktok", video="spot.mp4")["payload"]["caption"], kit["ads"]["tiktok"]["text"])

    def test_bad_requests_are_refused(self):
        d, kd, kit, q = setup()
        for kwargs in ({"channel": "myspace"}, {"channel": "youtube"}, {"channel": "youtube", "video": "../../etc/passwd"}, {"channel": "meta", "files": ["../kit/../../x.png"]}, {"channel": "tiktok", "video": "missing.mp4"}):
            with self.assertRaises(CQ.QueueError, msg=kwargs):
                q.stage(kd, kit, **kwargs)

    def test_copy_that_fails_its_checks_is_not_staged(self):
        d, kd, kit, q = setup()
        kit["ads"]["meta"]["headline"] = "Guaranteed best bread, 50,000 customers"
        with self.assertRaises(CQ.QueueError) as c:
            q.stage(kd, kit, "meta")
        self.assertIn("failed its checks", str(c.exception))

    def test_the_queue_is_bounded(self):
        d, kd, kit, q = setup()
        for _ in range(CQ.MAX_ITEMS):
            q.stage(kd, kit, "landing")
        with self.assertRaises(CQ.QueueError):
            q.stage(kd, kit, "landing")


class Approval(unittest.TestCase):
    def test_nothing_can_be_exported_before_it_is_approved(self):
        d, kd, kit, q = setup()
        i = q.stage(kd, kit, "meta")
        with self.assertRaises(CQ.QueueError) as c:
            q.export(i["id"])
        self.assertIn("approved", str(c.exception))
        q.approve(i["id"], "2099-01-01 09:30")
        self.assertEqual(q.export(i["id"])["state"], "exported")

    def test_schedule_format_and_past_dates(self):
        d, kd, kit, q = setup()
        i = q.stage(kd, kit, "meta")
        for bad in ("tomorrow", "2020-01-01", "2099-13", "2099-01-01 25:00:00"):
            with self.assertRaises(CQ.QueueError, msg=bad):
                q.approve(i["id"], bad)
        self.assertEqual(q.approve(i["id"], "2099-06-01")["scheduled_at"], "2099-06-01")

    def test_a_file_that_changes_after_staging_or_approval_stops_everything(self):
        d, kd, kit, q = setup()
        i = q.stage(kd, kit, "meta")
        open(os.path.join(kd, "graphics", "social_1200x628.png"), "ab").write(b"tampered")
        with self.assertRaises(CQ.QueueError) as c:
            q.approve(i["id"])
        self.assertIn("changed after it was staged", str(c.exception))
        d2, kd2, kit2, q2 = setup()
        j = q2.stage(kd2, kit2, "landing")
        q2.approve(j["id"])
        open(os.path.join(kd2, "landing", "index.html"), "ab").write(b"<!-- edited -->")
        with self.assertRaises(CQ.QueueError) as c:
            q2.export(j["id"])
        self.assertIn("changed after approval", str(c.exception))

    def test_states_only_move_forward(self):
        d, kd, kit, q = setup()
        i = q.stage(kd, kit, "landing")
        q.approve(i["id"])
        with self.assertRaises(CQ.QueueError):
            q.approve(i["id"])
        q.export(i["id"])
        with self.assertRaises(CQ.QueueError):
            q.cancel(i["id"])
        j = q.stage(kd, kit, "landing")
        q.cancel(j["id"])
        with self.assertRaises(CQ.QueueError):
            q.approve(j["id"])


class Export(unittest.TestCase):
    def test_the_package_has_the_copy_the_hashed_files_the_steps_and_the_disclosure_and_posts_nothing(self):
        d, kd, kit, q = setup()
        i = q.stage(kd, kit, "youtube", video="spot.mp4")
        q.approve(i["id"], "2099-02-02 10:00")
        out = q.export(i["id"])["export_dir"]
        post = json.load(open(os.path.join(out, "post.json"), encoding="utf-8"))
        self.assertEqual((post["posted"], post["approved_by_owner"], post["scheduled_at"]), (False, True, "2099-02-02 10:00"))
        self.assertIn("AI-assisted", post["disclosure"])
        self.assertEqual(hashlib.sha256(open(os.path.join(out, "spot.mp4"), "rb").read()).hexdigest(), post["files"]["spot.mp4"])
        readme = open(os.path.join(out, "README.txt"), encoding="utf-8").read()
        self.assertIn("YouTube Studio", readme)
        self.assertIn("Nothing has been posted", readme)
        self.assertIn("synthetic", readme.lower() + post["disclosure"].lower())

    def test_every_channel_has_steps_and_email_tells_you_to_send_only_to_people_who_asked(self):
        self.assertEqual(set(CQ.STEPS), set(CQ.CHANNELS))
        self.assertIn("asked to hear from you", CQ.STEPS["email"])
        self.assertIn("unsubscribe", CQ.STEPS["email"].lower())


class Ledger(unittest.TestCase):
    def test_tamper_evident(self):
        d, kd, kit, q = setup()
        i = q.stage(kd, kit, "landing")
        q.approve(i["id"])
        q.export(i["id"])
        self.assertEqual(q.verify_ledger(), (True, 3))
        lines = open(q._ledger, encoding="utf-8").read().splitlines()
        r = json.loads(lines[1])
        r["detail"] = {"x": 1}
        lines[1] = json.dumps(r, sort_keys=True)
        open(q._ledger, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        self.assertEqual(q.verify_ledger(), (False, 2))

    def test_a_corrupt_queue_file_is_set_aside(self):
        d = tempfile.mkdtemp()
        open(os.path.join(d, "queue.json"), "w").write("{broken")
        q = CQ.CampaignQueue(d)
        self.assertEqual(q.items, {})
        self.assertTrue(any(f.startswith("queue.corrupt") for f in os.listdir(d)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
