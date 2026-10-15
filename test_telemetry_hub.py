import json
import os
import re
import tempfile
import time
import unittest
from unittest import mock

import telemetry_hub as th

HERE = os.path.dirname(os.path.abspath(__file__))
ID = "a" * 32


def ev(**kw):
    d = {"e": "page_view", "t": int(time.time()), "i": ID}
    d.update(kw)
    return d


class HubTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        th.STORE_DIR = d
        th.STORE_PATH = os.path.join(d, "e.jsonl")

    def test_valid_event_and_optional_fields(self):
        self.assertIsNotNone(th.validate(ev()))
        self.assertEqual(th.validate(ev(v="1.0.1", s=1, w="m", x="sw-failed"))["x"], "sw-failed")

    def test_rejects_anything_outside_the_schema(self):
        bad = [ev(e="keylog"), ev(i="short"), ev(i="Z" * 32), ev(t=1), ev(t=time.time() + 99999), ev(t="now"), ev(t=True),
               ev(extra="x"), ev(text="hello"), ev(ua="Mozilla"), ev(ip="1.2.3.4"), ev(x="Has Space"), ev(x="a" * 33), ev(w="xl"), ev(s=2),
               ev(v="<script>"), "string", None, [], {}, {"e": "page_view"}]
        for b in bad:
            self.assertIsNone(th.validate(b), b)

    def test_pull_stores_valid_drops_invalid_and_acks_everything(self):
        calls = []

        def fake(path, body=None):
            calls.append((path, body))
            if path == "/pull":
                return {"events": [{"k": "ev:1", "ev": ev()}, {"k": "ev:2", "ev": ev(text="secret")}, {"k": "ev:3", "ev": None}]}
            return {"deleted": 3}
        with mock.patch.dict(os.environ, {"NEXXUS_RELAY_URL": "https://r.example", "NEXXUS_RELAY_KEY": "k"}), mock.patch.object(th, "_call", side_effect=fake):
            r = th.pull_once()
        self.assertEqual(r, {"received": 3, "stored": 1, "dropped": 2})
        self.assertEqual(calls[1], ("/ack", {"keys": ["ev:1", "ev:2", "ev:3"]}))
        self.assertEqual(sum(1 for _ in open(th.STORE_PATH)), 1)

    def test_transport_failure_acks_nothing(self):
        seen = []

        def fake(path, body=None):
            seen.append(path)
            raise OSError("down")
        with mock.patch.dict(os.environ, {"NEXXUS_RELAY_URL": "https://r.example", "NEXXUS_RELAY_KEY": "k"}), mock.patch.object(th, "_call", side_effect=fake):
            with self.assertRaises(OSError):
                th.pull_once()
        self.assertEqual(seen, ["/pull"])

    def test_requires_https_and_config(self):
        with mock.patch.dict(os.environ, {"NEXXUS_RELAY_URL": "", "NEXXUS_RELAY_KEY": ""}):
            self.assertFalse(th.configured())
            with self.assertRaises(RuntimeError):
                th.pull_once()
        with mock.patch.dict(os.environ, {"NEXXUS_RELAY_URL": "http://insecure.example", "NEXXUS_RELAY_KEY": "k"}):
            with self.assertRaises(RuntimeError):
                th._call("/pull")

    def test_summary_aggregates_only(self):
        th._append([th.validate(ev(v="1.0.1", s=1)), th.validate(ev(e="install_clicked")), th.validate(ev(i="b" * 32, e="page_view"))])
        s = th.summary()
        self.assertEqual((s["events"], s["distinct_installs"], s["installed_as_app"]), (3, 2, 1))
        self.assertEqual(s["by_event"], {"page_view": 2, "install_clicked": 1})
        self.assertNotIn(ID, json.dumps(s))     # install ids never appear in the summary


class SchemaAgreementTest(unittest.TestCase):
    """The desktop, the relay and the sandbox page must allow exactly the same events and fields."""

    def _js_list(self, text, name):
        m = re.search(r"const %s = \[(.*?)\];" % name, text, re.S)
        return tuple(re.findall(r'"([a-z_]+)"', m.group(1)))

    def test_relay_matches_hub(self):
        w = open(os.path.join(HERE, "relay", "worker.js"), encoding="utf-8").read()
        self.assertEqual(self._js_list(w, "EVENTS"), th.EVENTS)
        self.assertEqual(set(self._js_list(w, "FIELDS")), th.FIELDS)

    def test_sandbox_page_matches_hub(self):
        page = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
        m = re.search(r"var TEL_EVENTS = \[(.*?)\];", page, re.S)
        self.assertEqual(tuple(re.findall(r"'([a-z_]+)'", m.group(1))), th.EVENTS)


if __name__ == "__main__":
    unittest.main()
