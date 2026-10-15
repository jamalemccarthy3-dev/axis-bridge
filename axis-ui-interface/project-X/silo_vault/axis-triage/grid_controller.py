"""The grid controller: search -> triage gate -> LLM. The search engine and the LLM belong to other engines, so they are handed in (search=..., llm=...)
instead of being imported from them: an engine must not reach into another engine's folder."""
from triage_gate import TriageGate
from lib.grid_controller_tool import discover_nodes, read_diagnostic, validate_pipeline_connection
from lib import _cfg
from sync_manager import SyncManager


class GridController:
    def __init__(self, search=None, llm=None):
        self.search = search      # callable(query) -> raw data (e.g. the search engine's search route)
        self.llm = llm            # callable(safe_data) -> response (e.g. the LLM engine)

    def execute_cycle(self, query, target_node):
        """Orchestrates the pipeline: 1. raw data from the search, 2. sanitised and routed by the TriageGate, 3. delivered to the LLM.
        -> True when the data passed the gate and reached the LLM."""
        if self.search is None or self.llm is None:
            raise RuntimeError("GridController needs search= and llm= callables (they belong to the search-engine and LLM engines)")
        raw_data = self.search(query)
        safe_data = TriageGate().run(raw_data, target_node)
        if safe_data:
            response = self.llm(safe_data)
            print(f"[GridController] Data successfully routed to LLM: {response}")
            return True
        print("[GridController] Error: Data failed sanitization or validation.")
        return False

    def main_loop(self):
        """One health pass over the grid (what main.py runs at start-up). -> a summary dict."""
        discrepancies = SyncManager().run_sync()
        summary = {"nodes": len(discover_nodes(["__pycache__", ".git", "render", "nexxus"])), "discrepancies": discrepancies,
                   "diagnostic": read_diagnostic(_cfg.load_config("grid_controller").get("log", "axis_audit_log.txt")),
                   "llm_registered": validate_pipeline_connection("axis-llm"), "search_registered": validate_pipeline_connection("axis-search_engine")}
        print(f"[GridController] {summary}")
        return summary


if __name__ == "__main__":
    GridController().main_loop()
