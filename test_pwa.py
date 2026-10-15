"""test_pwa.py - the dashboard installs on a phone like an app (Add to Home Screen): a valid manifest, real icons of the declared sizes, the page tags iOS and Android read, files served with the right
types by the real server, and no service worker (it needs https and could cache a control room's pages). Run: python test_pwa.py"""
import atexit
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="pwa_")
atexit.register(shutil.rmtree, TMP, True)
os.environ.update({"NEXXUS_ADMIN_TOKEN": "throwaway-admin", "NEXXUS_GOVERNANCE_SECRET": "throwaway-secret", "NEXXUS_UI_ROOT": os.path.join(TMP, "ui"), "NEXXUS_ENGINE_STAGING": os.path.join(TMP, "s", "e"),
                   "NEXXUS_ENGINE_LEDGER": os.path.join(TMP, "l.jsonl"), "NEXXUS_NOTIFICATIONS_FILE": os.path.join(TMP, "n.json"), "NEXXUS_PERIMETER_DIR": os.path.join(TMP, "p"),
                   "NEXXUS_DISABLE_AUTOSCHEDULER": "1"})
os.makedirs(os.environ["NEXXUS_UI_ROOT"])
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "nexxus"))
RENDER = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "render")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG: " + path
    return struct.unpack(">II", head[16:24])


class Pwa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(RENDER, "manifest.webmanifest"), encoding="utf-8") as f:
            cls.m = json.load(f)
        with open(os.path.join(RENDER, "babylon_preview.html"), encoding="utf-8") as f:
            cls.html = f.read()
        import python_server as srv
        cls.http = srv.app.test_client()

    def test_manifest_is_complete(self):
        m = self.m
        for k in ("name", "short_name", "start_url", "scope", "display", "background_color", "theme_color", "icons"):
            self.assertTrue(m.get(k), k)
        self.assertEqual((m["display"], m["start_url"]), ("standalone", "/"))
        purposes = {i["purpose"] for i in m["icons"]}
        self.assertEqual(purposes, {"any", "maskable"})

    def test_every_icon_exists_with_its_declared_size(self):
        for i in self.m["icons"]:
            w, h = png_size(os.path.join(RENDER, i["src"].lstrip("/").replace("/", os.sep)))
            self.assertEqual("%dx%d" % (w, h), i["sizes"], i["src"])
        self.assertEqual(png_size(os.path.join(RENDER, "pwa", "apple-touch-icon.png")), (180, 180))

    def test_page_carries_the_tags_phones_read(self):
        for needle in ('rel="manifest" href="/manifest.webmanifest"', 'name="theme-color"', 'name="apple-mobile-web-app-capable" content="yes"', 'name="apple-mobile-web-app-title" content="NEXXUS"',
                       'rel="apple-touch-icon" href="/pwa/apple-touch-icon.png"'):
            self.assertIn(needle, self.html)
        self.assertEqual(len(re.findall(r'rel="manifest"', self.html)), 1)

    def test_the_real_server_serves_them(self):
        r = self.http.get("/manifest.webmanifest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(force=True)["short_name"], "NEXXUS")
        for src in [i["src"] for i in self.m["icons"]] + ["/pwa/apple-touch-icon.png"]:
            r = self.http.get(src)
            self.assertEqual((r.status_code, r.mimetype), (200, "image/png"), src)

    def test_no_service_worker(self):
        self.assertNotIn("serviceWorker", self.html)                                           # needs https, and could cache pages of a security console
        self.assertFalse(any(f.lower().startswith(("sw.", "service-worker")) for f in os.listdir(RENDER)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
