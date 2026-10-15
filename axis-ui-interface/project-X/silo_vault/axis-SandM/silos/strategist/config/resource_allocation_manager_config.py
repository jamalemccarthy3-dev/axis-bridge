class ResourceAllocationManagerConfig:
    def __init__(self):
        # Operational parameters for the Resource Allocation Manager
        self.PRIORITY_LEVELS = ["CRITICAL", "HIGH", "MAINTENANCE"]
        self.AUTO_BALANCE = True
        
        # Thresholds for resource shifts
        self.REALLOCATION_THRESHOLD = 0.20 # 20% variance triggers re-balance
        self.MAX_BURN_RATE = 5000 # Units per cycle
