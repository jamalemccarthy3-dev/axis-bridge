import importlib
import os
import sys

# The engine's own folder goes first, so `config`, `src` and the flat module names mean THIS engine's files.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# component -> (module, attribute). A class is created; a module is registered as it is.
# Components of OTHER engines (the triage gate, the bridge) are not imported from here: an engine does not reach into another engine's folder.
COMPONENT_MAP = {
    "web_crawling": ("config.web_crawling_config", "WebCrawlingConfig"),
    "ui_dashboard": ("config.ui_dashboard_config", "UiDashboardConfig"),
    "search_routing": ("config.search_routing_config", "SearchRoutingConfig"),
    "memory_store": ("config.memory_store_config", "MemoryStoreConfig"),
    "knowledge_graph": ("config.knowledge_graph_config", "KnowledgeGraphConfig"),
    "archival_access": ("config.archival_access_config", "ArchivalAccessConfig"),
    "governor": ("src.governor.config.governor_utility", "GovernorConfig"),
    "pydantic": ("src.governor.config.pydantic_utility_config", "PydanticConfig"),
    "lang_graph": ("src.governor.config.lang_graph_config", "LangGraphConfig"),
    "hypothesis_engine": ("src.governor.config.hypothesis_engine_config", "HypothesisEngineConfig"),
    "audit_log": ("src.governor.config.audit_log_utility_config", "AuditLogUtilityConfig"),
    "search_engine": ("search_engine", None),
    "nexus_talk": ("nexxus_talks", None),
}
EXTERNAL = {"axis_triage": "axis-triage", "axis_system": "axis-bridge"}
NEXXUS_GOVERNANCE = {"mesh": "mesh.py", "engine_snippet_review": "engine_snippet_review.py"}


class MasterConfig:
    """Central registry for all Sovereign Shift component configurations. Each component loads on its own: one broken component never hides the others."""

    def __init__(self):
        self.components = {}
        self.status = {}
        for name, (module, attr) in COMPONENT_MAP.items():
            try:
                mod = importlib.import_module(module)
                self.components[name] = getattr(mod, attr)() if attr else mod
                self.status[name] = "LOADED"
            except Exception as e:
                self.status[name] = "UNAVAILABLE (%s: %s)" % (type(e).__name__, str(e)[:80])
        for name, owner in EXTERNAL.items():
            self.status[name] = "EXTERNAL (belongs to %s; not imported)" % owner
        for key, fname in NEXXUS_GOVERNANCE.items():
            present = os.path.isfile(os.path.join(ROOT, fname))
            self.status["nexxus_governance_" + key] = "PRESENT" if present else ("NOT_INSTALLED (optional)" if key == "engine_snippet_review" else "MISSING")

    def get_config(self, component_name):
        """Dynamic retrieval of component configurations."""
        return self.components.get(component_name)

    def run_diagnostic_handshake(self):
        """Prints the real state of every component. -> the number of components that are UNAVAILABLE or MISSING."""
        problems = 0
        for name, st in self.status.items():
            problems += 1 if st.startswith(("UNAVAILABLE", "MISSING")) else 0
            print(f"Component: {name} | Status: {st}")
        return problems


masterconfig = MasterConfig          # the lower-case name older files import
