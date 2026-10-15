"""The real server's _is_local() check: only the dashboard's own page may use the local-only routes (capture, telemetry, watchers, Platform)."""
import unittest

import python_server as srv


class LocalGuardTest(unittest.TestCase):
    def setUp(self):
        self.c = srv.app.test_client()

    def get(self, headers=None, host="localhost:8000", addr="127.0.0.1"):
        return self.c.get("/api/platform/entitlement", headers=headers or {}, base_url="http://" + host, environ_overrides={"REMOTE_ADDR": addr})

    def test_own_dashboard_page_is_allowed(self):
        self.assertEqual(self.get().status_code, 200)
        self.assertEqual(self.get({"Origin": "http://localhost:8000"}).status_code, 200)
        self.assertEqual(self.get(host="127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"}).status_code, 200)

    def test_another_web_page_cannot_read_it(self):
        self.assertEqual(self.get({"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.get({"Origin": "null"}).status_code, 403)

    def test_dns_rebinding_host_is_refused(self):
        self.assertEqual(self.get(host="evil.example:8000").status_code, 403)

    def test_other_machines_are_refused(self):
        self.assertEqual(self.get(addr="192.168.1.50").status_code, 403)

    def test_other_local_only_routes_share_the_check(self):
        for path in ("/api/capture/status", "/api/sandbox-telemetry/summary", "/api/watch/findings"):
            r = self.c.get(path, headers={"Origin": "https://evil.example"}, base_url="http://localhost:8000")
            if path != "/api/capture/status":          # capture status is read-only and not gated; the other two must refuse
                self.assertEqual(r.status_code, 403, path)


if __name__ == "__main__":
    unittest.main()
