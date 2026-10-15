# knowledge_graph/knowledge_graph_config.py

class KnowledgeGraphConfig:
    """
    Configuration for knowledge_graph.
    Points to the distributed graph database endpoint.
    """
    def __init__(self):
        self.graph_db_uri = "bolt+s://graph.sovereign-shift.net:7687"
        self.auth_token = "SOVEREIGN_GRAPH_TOKEN"
        self.connection_pool_size = 20