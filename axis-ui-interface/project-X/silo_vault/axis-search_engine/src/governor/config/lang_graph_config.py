# src/lang_graph/lang_graph_config.py

class LangGraphConfig:
    """
    Configuration for lang_graph.
    Defines orchestration flow endpoints and state management.
    """
    def __init__(self):
        self.orchestrator_url = "https://orchestrator.sovereign-shift.net/v1/flow"
        self.max_steps = 25
        self.persistence_mode = "remote_redis"