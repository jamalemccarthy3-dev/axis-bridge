"""test_links_access.py - the omni <-> axis-llm link and the path guard work. Run: python test_links_access.py"""
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("NEXXUS_MESH_URL", "http://127.0.0.1:9")


def load(rel, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Access(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.base, "bank"))
        os.makedirs(os.path.join(self.base, "out"))
        self.A = load("access/access_omni_path.py", "oa").OmniPathAccess({"bank": (os.path.join(self.base, "bank"), False), "out": (os.path.join(self.base, "out"), True)})

    def test_only_allowed_folders_and_only_writable_ones_for_writing(self):
        a, b = self.A, self.base
        self.assertTrue(a.resolve(os.path.join(b, "bank", "v.json")).endswith("v.json"))
        self.assertTrue(a.allowed(os.path.join(b, "out", "r.wav"), write=True))
        self.assertFalse(a.allowed(os.path.join(b, "bank", "v.json"), write=True))               # read-only
        for bad in (os.path.join(b, "elsewhere.txt"), os.path.join(b, "out", "..", "..", "etc"), os.path.join(b, "bank", "..", "out2", "x"), "C:/Windows/system32/x"):
            self.assertFalse(a.allowed(bad), bad)
        for bad in ("", None, "a\x00b"):
            self.assertFalse(a.allowed(bad), repr(bad))
        with self.assertRaises(PermissionError):
            a.resolve(os.path.join(b, "outsider"))

    def test_open_creates_output_folders_and_refuses_the_rest(self):
        with self.A.open(os.path.join(self.base, "out", "sub", "r.txt"), "w") as f:
            f.write("hi")
        self.assertEqual(open(os.path.join(self.base, "out", "sub", "r.txt")).read(), "hi")
        with self.assertRaises(PermissionError):
            self.A.open(os.path.join(self.base, "bank", "x.txt"), "w")
        with self.assertRaises(PermissionError):
            self.A.open(os.path.join(self.base, "x.txt"), "r")

    def test_a_link_pointing_out_of_an_allowed_folder_does_not_escape(self):
        secret = os.path.join(self.base, "secret.txt")
        open(secret, "w").write("s")
        link = os.path.join(self.base, "out", "link.txt")
        try:
            os.symlink(secret, link)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are not available here")
        self.assertFalse(self.A.allowed(link))


class Link(unittest.TestCase):
    def setUp(self):
        self.llm = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.llm, "data", "weights"))
        json.dump(["<pad>", "<unk>", "<s>", "</s>", "steel", "rust", "wood"], open(os.path.join(self.llm, "data", "vocab.json"), "w"))
        import numpy as np
        m = np.zeros((7, 4), dtype=np.float32)
        m[4], m[5] = [1, 0, 0, 0], [0, 1, 0, 0]
        np.save(os.path.join(self.llm, "data", "weights", "embeddings.npy"), m)                  # "wood" (6) is untrained: an all-zero row
        self.L = load("links/AXIS_LLM_link.py", "ol").AxisLlmLink

    def test_tokens_and_embeddings_come_from_axis_llm_and_nothing_is_invented(self):
        link = self.L(self.llm)
        self.assertEqual(link.available(), {"vocabulary": 7, "embeddings": True, "reason": "ok"})
        self.assertEqual(link.tokens("Steel and RUST, wood!"), [4, 1, 5, 6])                        # "and" is unknown: id 1
        self.assertEqual(link.embed("steel rust"), [0.5, 0.5, 0.0, 0.0])
        self.assertEqual(link.embed("steel wood"), [1.0, 0.0, 0.0, 0.0])                            # the untrained word is skipped, not averaged in as zeros
        self.assertIsNone(link.embed("wood"))
        self.assertIsNone(link.embed("zebra"))
        before = open(os.path.join(self.llm, "data", "vocab.json")).read()
        link.tokens("a brand new word")
        self.assertEqual(open(os.path.join(self.llm, "data", "vocab.json")).read(), before)         # read only

    def test_without_axis_llm_data_it_says_so(self):
        link = self.L(tempfile.mkdtemp())
        self.assertEqual(link.available()["vocabulary"], 0)
        with self.assertRaises(RuntimeError):
            link.tokens("hello")
        os.makedirs(os.path.join(link.llm_dir, "data"))
        json.dump(["<pad>", "<unk>", "<s>", "</s>", "hello"], open(os.path.join(link.llm_dir, "data", "vocab.json"), "w"))
        self.assertIsNone(link.embed("hello"))                                                      # a vocabulary without trained vectors gives none

    def test_ask_uses_a_local_ollama_and_is_honest_when_there_is_none(self):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, o):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(o).encode())

            def do_GET(self):
                self._send({"models": [{"name": "tiny:latest"}]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self._send({"response": "echo: " + body["prompt"]})
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            link = self.L(self.llm, "http://127.0.0.1:%d" % srv.server_port)
            self.assertEqual(link.ask("hi"), {"status": "ok", "text": "echo: hi", "model": "tiny:latest"})
            self.assertEqual(link.ask("hi", model="tiny")["model"], "tiny:latest")
            self.assertEqual(link.ask("hi", model="ghost")["status"], "unavailable")
        finally:
            srv.shutdown()
        self.assertEqual(self.L(self.llm, "http://127.0.0.1:9").ask("hi")["status"], "unavailable")
        self.assertIn("on this machine", self.L(self.llm, "http://example.com:11434").ask("hi")["reason"])


class Registry(unittest.TestCase):
    def test_the_components_are_registered_and_ready_not_planned(self):
        cfg = load("master_config.py", "omc")
        self.assertEqual(cfg.PLANNED, {})
        for comp in ("links", "access"):
            self.assertEqual(cfg.perform_health_assessment(comp)["status"], "READY", comp)


if __name__ == "__main__":
    unittest.main(verbosity=1, warnings="ignore")
