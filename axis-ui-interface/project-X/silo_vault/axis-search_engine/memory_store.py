import redis
# Point directly to the 'config' folder
from config.memory_store_config import MemoryStoreConfig

class MemoryStore:
    """Engine for managing distributed state across the cloud."""
    def __init__(self):
        self.config = MemoryStoreConfig()
        self.client = redis.Redis(
            host=self.config.db_host,
            port=self.config.db_port,
            ssl=self.config.use_ssl
        )

    def write(self, key, value):
        """Persists data to the remote memory cluster."""
        try:
            return self.client.set(key, value)
        except Exception as e:
            return {"error": str(e)}

    def read(self, key):
        """Retrieves data from the remote memory cluster."""
        try:
            return self.client.get(key)
        except Exception as e:
            return {"error": str(e)}