"""test_operational.py - axis-search_engine, offline: every component loads, the parser works on a sample page, the query is URL-encoded,
and a network failure gives an empty result instead of an exception. Run: python test_operational.py"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("NEXXUS_MESH_URL", "http://127.0.0.1:9")
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import search_engine  # noqa: E402

SAMPLE = """<html><body>
<a class="result__snippet" href="x">NEXXUS is a <b>local-first</b> orchestrator &amp; more</a>
<a class="result__snippet" href="y">Second result about engines</a>
</body></html>"""


class Operational(unittest.TestCase):
    def test_every_component_loads(self):
        from config.master_config import MasterConfig
        m = MasterConfig()
        self.assertEqual({k: v for k, v in m.status.items() if v.startswith(("UNAVAILABLE", "MISSING"))}, {})
        self.assertIsNotNone(m.get_config("hypothesis_engine"))

    def test_master_test_runs(self):
        r = subprocess.run([sys.executable, "master_test.py"], cwd=ROOT, capture_output=True, text=True, timeout=120, env=dict(os.environ, NEXXUS_MESH_URL="http://127.0.0.1:9"))
        self.assertEqual(r.returncode, 0, r.stdout[-300:])

    def test_html_is_stripped_and_decoded(self):
        self.assertEqual(search_engine.clean_html_tags("a <b>b</b> &amp; c"), "a b & c")
        self.assertEqual(search_engine.clean_html_tags(""), "")

    def test_the_parser_finds_snippets(self):
        r = search_engine.parse_duckduckgo_html(SAMPLE)
        self.assertEqual([x["snippet"] for x in r], ["NEXXUS is a local-first orchestrator & more", "Second result about engines"])
        self.assertEqual(search_engine.parse_duckduckgo_html(""), [])

    def test_the_query_is_url_encoded(self):
        seen = []

        class Resp:
            status_code = 200
            text = SAMPLE

        original = search_engine.requests.get
        search_engine.requests.get = lambda url, headers=None, timeout=None: seen.append(url) or Resp()
        try:
            out = search_engine.search_web("cats & dogs?x=1#top")
        finally:
            search_engine.requests.get = original
        self.assertEqual(len(seen), 2)
        for url in seen:
            self.assertIn("q=cats+%26+dogs%3Fx%3D1%23top", url)          # nothing in the query can add a parameter or end the URL
        self.assertEqual(len(out["aggregated_snippets"]), 2)             # the same two snippets from both sources are not duplicated

    def test_a_network_failure_is_an_empty_result_not_a_crash(self):
        original = search_engine.requests.get

        def boom(*a, **k):
            raise ConnectionError("offline")
        search_engine.requests.get = boom
        try:
            out = search_engine.search_web("anything")
        finally:
            search_engine.requests.get = original
        self.assertEqual(out["aggregated_snippets"], [])
        self.assertTrue(all(s["status"] == "failed" for s in out["raw_sources"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
