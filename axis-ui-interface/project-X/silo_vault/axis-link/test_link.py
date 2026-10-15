"""test_link.py - axis-link really encrypts, checks ports, and throttles. Run: python test_link.py"""
import os
import socket
import sys
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
from lib.bridge import UtilityBridge  # noqa: E402
from src import security  # noqa: E402
from src.relay import UniversalRelay  # noqa: E402


class Crypto(unittest.TestCase):
    def tearDown(self):
        security.purge_buffer()

    def test_no_session_no_sending_and_the_text_is_really_hidden(self):
        with self.assertRaises(security.SecurityError):
            security.encrypt_packet("x")
        security.new_session()
        tok = security.encrypt_packet("launch the build")
        self.assertNotIn("launch", tok)
        self.assertNotIn("ENCRYPTED_", tok)
        self.assertEqual(security.decrypt_packet(tok), "launch the build")
        self.assertNotEqual(security.encrypt_packet("same"), security.encrypt_packet("same"))          # fresh randomness each time

    def test_tampering_and_old_sessions_are_detected(self):
        security.new_session()
        tok = security.encrypt_packet("data")
        with self.assertRaises(security.SecurityError):
            security.decrypt_packet(tok[:-3] + "AAA")
        security.new_session()                                                                      # a new session: a new key
        with self.assertRaises(security.SecurityError):
            security.decrypt_packet(tok)
        security.purge_buffer()
        with self.assertRaises(security.SecurityError):
            security.decrypt_packet(tok)

    def test_the_session_gatekeeper_signs_and_verifies(self):
        g = security.SecureGatekeeper()
        sig = g.sign("m")
        self.assertTrue(g.verify("m", sig))
        self.assertFalse(g.verify("m2", sig))
        g.close()
        self.assertFalse(g.verify("m", sig))


class Relay(unittest.TestCase):
    def setUp(self):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        def accept_loop():
            try:
                for _ in range(20):
                    self.srv.accept()
            except OSError:
                pass                                                                      # the server socket was closed by tearDown
        threading.Thread(target=accept_loop, daemon=True).start()

    def tearDown(self):
        security.purge_buffer()
        self.srv.close()

    def test_a_handshake_needs_a_live_port_and_a_signature(self):
        r = UniversalRelay()
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        dead_port = free.getsockname()[1]
        free.close()
        self.assertFalse(r.establish_handshake(dead_port, "sig"))
        self.assertFalse(r.establish_handshake(self.port, ""))
        for bad in (0, -1, 70000, "80", None, True):
            self.assertFalse(r._is_port_live(bad), bad)
        self.assertTrue(r.establish_handshake(self.port, "sig"))
        self.assertEqual(r.active_session["port"], self.port)

    def test_a_command_travels_encrypted_and_the_session_ends_after_it(self):
        seen = {}

        class Engine:
            def execute(self, payload):
                seen["payload"] = payload
                return security.encrypt_packet("done: " + security.decrypt_packet(payload).upper())
        r = UniversalRelay()
        self.assertIsNone(r.relay_to_engine("x", Engine()))                              # no session yet
        self.assertTrue(r.establish_handshake(self.port, "sig"))
        self.assertEqual(r.relay_to_engine("build it", Engine()), "done: BUILD IT")
        self.assertNotIn("build", seen["payload"])
        self.assertIsNone(r.active_session)
        self.assertFalse(security.has_session())
        self.assertIsNone(r.relay_to_engine("again", Engine()))                          # stateless: nothing remembered

    def test_an_engine_that_answers_in_plain_text_is_caught_and_the_session_still_ends(self):
        class Bad:
            def execute(self, payload):
                return "plain text answer"
        r = UniversalRelay()
        r.establish_handshake(self.port, "sig")
        with self.assertRaises(security.SecurityError):
            r.relay_to_engine("x", Bad())
        self.assertIsNone(r.active_session)
        self.assertFalse(security.has_session())


class Bridge(unittest.TestCase):
    def test_only_registered_hooks_run_and_the_engine_is_throttled(self):
        t = [0.0]
        b = UtilityBridge(capacity=5, rate=1.0, clock=lambda: t[0])
        b.register_hook("add", lambda x, y: x + y)
        b.register_hook("boom", lambda: 1 / 0)
        self.assertEqual(b.process_task({"hook": "add", "args": [2, 3]}), {"status": "done", "result": 5})
        self.assertEqual(b.process_task({"hook": "format_disk"})["status"], "unknown_hook")
        self.assertEqual(b.process_task("add")["status"], "invalid")
        self.assertEqual(b.process_task({"hook": "boom"})["status"], "failed")
        statuses = [b.process_task({"hook": "add", "args": [1, 1]})["status"] for _ in range(6)]
        self.assertEqual(statuses[:2], ["done", "done"])                                  # a burst of 0.8 x 5 = 4 tokens, 2 already used
        self.assertIn("throttled", statuses)
        t[0] += 3.0                                                                       # three seconds later three tokens are back
        self.assertEqual(b.process_task({"hook": "add", "args": [1, 1]})["status"], "done")
        with self.assertRaises(ValueError):
            b.register_hook("", len)

    def test_main_builds_its_parts(self):
        import main
        relay, orch, sec, bridge = main.initialize_ai_environment()
        self.assertEqual((type(relay).__name__, orch.state, type(bridge).__name__), ("UniversalRelay", "IDLE", "UtilityBridge"))


if __name__ == "__main__":
    unittest.main(verbosity=1, warnings="ignore")
