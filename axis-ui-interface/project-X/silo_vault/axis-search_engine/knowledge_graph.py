from neo4j import GraphDatabase
# Point directly to the 'config' folder
from config.knowledge_graph_config import KnowledgeGraphConfig

class KnowledgeGraph:
    """Engine for interacting with the remote graph database."""
    def __init__(self):
        self.config = KnowledgeGraphConfig()
        self.driver = GraphDatabase.driver(
            self.config.graph_db_uri,
            auth=("neo4j", self.config.auth_token)
        )

    def query(self, cypher_query):
        """Executes graph queries on the remote node."""
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query)
                return [record.data() for record in result]
        except Exception as e:
            return {"error": str(e)}