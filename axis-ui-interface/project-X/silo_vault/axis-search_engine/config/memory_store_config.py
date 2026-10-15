# memory_store/memory_store_config.py

class MemoryStoreConfig:
    """
    Stretched configuration for memory_store.
    Connects to a remote, high-performance data store.
    """
    def __init__(self):
        self.db_host = "cluster.sovereign-shift.net"
        self.db_port = 6379
        self.db_timeout = 5.0
        self.use_ssl = True