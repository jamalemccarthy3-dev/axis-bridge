# MAIN MASTER DIRECTOR: worker.py
import sys
# Link to the SRC (The Master Statistical Core)
sys.path.append("./SRC")

class MasterDirector:
    def __init__(self):
        self.stats_log = {}

    def ingest(self, silo_name, data_packet):
        """
        The Master does not touch money or logic.
        It only calculates the statistical health of the data flow.
        """
        # Calculate volume/throughput stats
        self.stats_log[silo_name] = len(str(data_packet))
        print(f"[STATISTICS MASTER] Ingested data from {silo_name}. Current throughput: {self.stats_log[silo_name]}")
        return self.stats_log[silo_name]

# Global instance for the system
director = MasterDirector()