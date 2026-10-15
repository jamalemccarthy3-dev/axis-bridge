"""test_operational.py - is axis-SandM really operational? Run: python test_operational.py
Starts the seven agents and imports every utility of every silo (each silo in its own process)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import health_report  # noqa: E402
import main  # noqa: E402
from config.master_config import MasterConfig  # noqa: E402


class Operational(unittest.TestCase):
    def test_all_seven_agents_start(self):
        res = main.run_system()
        self.assertEqual(len(res), 7)
        self.assertEqual({k: v for k, v in res.items() if v is not True}, {})

    def test_every_utility_exists_and_imports(self):
        cfg = MasterConfig()
        broken = {}
        for name in cfg.silos:
            for util, (status, why) in health_report.check_silo(cfg, name).items():
                if status in ("MISSING", "IMPORT_ERROR", "PROBE_FAILED"):
                    broken["%s/%s" % (name, util)] = why
        self.assertEqual(broken, {})

    def test_registry_matches_the_disk(self):
        cfg = MasterConfig()
        for name, spec in cfg.silos.items():
            for u in spec["utilities"]:
                self.assertTrue(os.path.isfile(os.path.join(cfg.silo_folder(name), u)), "%s/%s" % (name, u))

    def test_governor_has_no_missing_utilities(self):
        import silos.governor.tool_request as g
        self.assertEqual(g.GovernorAgent().missing_utilities(), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
