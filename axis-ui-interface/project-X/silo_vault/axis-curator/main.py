# main.py - starts axis-curator: creates every tool and checks that all of them really loaded.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bootstrap  # noqa: E402,F401  (flat import names, see bootstrap.py)

from verify_integrity_tool import VerifyIntegrityTool  # noqa: E402
from optimize_storage_tool import OptimizeStorageTool  # noqa: E402
from denoising_sanitization_tool import DenoisingSanitizationTool  # noqa: E402
from curate_input_path_tool import CurateInputPathTool  # noqa: E402
from checksum_verification_tool import ChecksumVerificationTool  # noqa: E402
from automated_metadata_tagging_tool import AutomatedMetadataTaggingTool  # noqa: E402
from life_cycle_policy_tool import LifeCyclePolicyTool  # noqa: E402
from dependency_mapper_tool import DependencyMapperTool  # noqa: E402
from categorization_cataloging_engine_tool import CategorizationCatalogingTool  # noqa: E402


class triad_starter:
    def __init__(self):
        self.verifier = VerifyIntegrityTool()
        self.storage = OptimizeStorageTool()
        self.sanitizer = DenoisingSanitizationTool()
        self.router = CurateInputPathTool()
        self.checksum = ChecksumVerificationTool()
        self.tagger = AutomatedMetadataTaggingTool()
        self.governor = LifeCyclePolicyTool()
        self.mapper = DependencyMapperTool()
        self.catalog = CategorizationCatalogingTool()
        self.status = "standby"

    def boot(self):
        print("--- Triad Build: Initializing System ---")
        import health_report
        issues = health_report.problems()
        self.status = "online" if not issues else "degraded"
        return {"status": "system_ready" if not issues else "degraded", "core": "active", "issues": [i[1] for i in issues]}


if __name__ == "__main__":
    result = triad_starter().boot()
    print(result)
    sys.exit(0 if result["status"] == "system_ready" else 1)
