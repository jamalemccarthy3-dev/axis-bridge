"""test_chat_failsafe.py - when the local model (Ollama) is not running, the chat says so in plain words, fast, with no exception text, and the rest of the server keeps answering.
It points NEXXUS at a port nothing listens on (the real Ollama is never touched). Run: python test_chat_failsafe.py"""
import os
import socket
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
NEXUS = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus")
sys.path.insert(0, NEXUS)
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class ModelDown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["NEXXUS_OLLAMA_URL"] = "http://127.0.0.1:%d" % closed_port()
        import nexxus_talks
        cls.nt = nexxus_talks

    def test_the_reachability_check_is_fast_and_honest(self):
        t = time.time()
        self.assertFalse(self.nt.NexxusTalks._ollama_reachable())
        self.assertLess(time.time() - t, 2)
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        os.environ["NEXXUS_OLLAMA_URL"] = "http://127.0.0.1:%d" % srv.getsockname()[1]
        try:
            self.assertTrue(self.nt.NexxusTalks._ollama_reachable())
        finally:
            srv.close()
            os.environ["NEXXUS_OLLAMA_URL"] = "http://127.0.0.1:%d" % closed_port()

    def test_the_chat_message_is_plain_fast_and_leaks_no_exception_text(self):
        talks = self.nt.NexxusTalks.__new__(self.nt.NexxusTalks)
        t = time.time()
        msg = talks.query_local_llama("hello", model_name="phi4-mini")
        self.assertLess(time.time() - t, 3)
        self.assertEqual(msg, self.nt.OLLAMA_DOWN_MESSAGE)
        for leak in ("HTTPConnectionPool", "Max retries", "NewConnectionError", "WinError", "Traceback", "Errno"):
            self.assertNotIn(leak, msg)
        self.assertIn("ollama serve", msg)
        self.assertIn("still running", msg)

    def test_the_default_chat_context_is_small_for_an_8gb_machine(self):
        import llm_router
        self.assertEqual(llm_router.CHAT_CTX, int(os.environ.get("NEXXUS_CHAT_CTX", "2048")))
        self.assertLessEqual(llm_router.CHAT_CTX, 4096)


if __name__ == "__main__":
    unittest.main(verbosity=1)
