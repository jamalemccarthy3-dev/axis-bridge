class ResourceBalancerConfig:
    def __init__(self):
        # Operational parameters for the Resource Balancer
        self.MAX_THRESHOLD = 0.85
        self.BALANCING_INTERVAL = 60 # seconds
        
        # Priority mapping for system agents
        self.AGENT_PRIORITIES = {
            "strategist": 0.4,
            "technical_agent": 0.3,
            "analyst": 0.2,
            "others": 0.1
        }
        
        self.DEBUG_MODE = False
