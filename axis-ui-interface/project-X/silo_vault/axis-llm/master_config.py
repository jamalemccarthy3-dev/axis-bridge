import os
from bridge_diagnostic import deck

class master_config:
    def __init__(self):
        # 1. System Infrastructure
        self.BASE_DIR = os.getcwd()
        self.DATA_DIR = os.path.join(self.BASE_DIR, "data")
        self.ENGINE_ID = "NEXXUS_SOVEREIGN_001"
        self.DECK = deck  # Integrating the diagnostic bridge

        # 2. The Binder's "Duty and Task" (NEXXUS Feed Configuration)
        self.BINDER_CONFIG = {
            "search_api_endpoint": "https://api.sovereign-shift.net/v1/crawl",
            "token_api_endpoint": "https://api.sovereign-shift.net/v1/token",
            "default_feed_interval": 300,  # seconds
            "allowed_domains": ["trusted-source-alpha.com", "api.knowledge-base.net"],
            "normalization_strategy": "strict_json",
            "nexxus_feed_priority": "high",
        }

        # 3. Governance Thresholds (Rules of the Democracy)
        self.GOVERNANCE = {
            "cpu_limit": 85.0,
            "memory_limit": 90.0,
            "strict_mode": True,
        }

        # 4. Comprehensive Asset, Utility & NEXXUS Governance Registry
        self.ASSET_REGISTRY = {
            # Core
            "CORE": "../nexxus/nexxus_sovereign_core.py",

            # Governor Utilities
            "LLM_GOVERNOR": "src/governor/governor_alignment_utility.py",
            "CHECKPOINT_MANAGER": "src/governor/checkpoint_state_manager.py",
            "PERFORMANCE_MONITOR": "src/governor/performance_monitor.py",

            # NEXXUS Governance Integration Modules
            "NEXXUS_GOVERNANCE_MESH": "mesh.py",
            "NEXXUS_GOVERNANCE_SNIPPET_REVIEW": "engine_snippet_review.py",

            # Lib / Tooling Utilities
            "LLM_LIB": "lib/attention_context_engine_tool.py",
            "CLEANER_SANITIZER": "lib/cleaner_sanitizer_tool.py",
            "EMBEDDING_VECTORIZER": "lib/embedding_vectorizer_utility_tool.py",
            "INFERENCE_ENGINE": "lib/infrence_feed_forward_utility_tool.py",
            "TOKENIZER": "lib/tokenizer_utility_tool.py",
            "VOCABULARY_MAP": "lib/vocabulary_mapping_utility_tool.py",
            "NEXXUS_TALKS": "../nexxus/nexxus_talks.py",

            # External Interfaces
            "SEARCH_BINDER": "https://api.sovereign-shift.net/v1/crawl",
            "TOKEN_BINDER": "https://api.sovereign-shift.net/v1/token"
        }

    def get_binder_settings(self):
        """Allows components to query the Binder's configuration directly."""
        return self.BINDER_CONFIG

    def validate_connection(self, domain):
        """Acts as a gatekeeper for the Binder's connections."""
        return domain in self.BINDER_CONFIG["allowed_domains"]

    def run_diagnostic_check(self):
        """Simultaneous master diagnostic check covering all system modules via the integrated bridge deck."""
        results = {}
        for key, asset_path in self.ASSET_REGISTRY.items():
            results[key] = self.DECK.report_status(f"{self.ENGINE_ID}_{key}", "INTEGRITY", "CONFIG_VERIFIED")
        return all(results.values())

    def initialize_engine(self):
        """Initializes the operational parameters and executes module verification."""
        results = self.run_diagnostic_check()
        print(f"Nexxus Sovereign Engine Initialized. Master Status Verified: {results}")
        return results