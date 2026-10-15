CONFIG = {
  "grid_version": "1.1",
  "system_settings": {
    "auto_discover": True,
    "ignore_list": ["__pycache__", ".git", "venv", "tools"],
    "diagnostic_link": "./axis_audit_log.txt"
  },
  "pipeline_nodes": {
    "search_engine": "axis_search_engine",
    "triage_gate": "triage_gate",
    "llm_sink": "axis_llm"
  }
}