class APIInterrogatorConfig:
    def __init__(self):
        # Operational parameters for the API Interrogator
        self.TIMEOUT_SEC = 30
        self.VERIFY_SSL = True
        
        # Endpoint monitoring settings
        self.REGISTERED_ENDPOINTS = ["internal_gateway", "auth_service", "data_vault"]
        self.RETRY_ATTEMPTS = 3
        self.ALLOW_REMOTE = False   # only loopback addresses are probed until you turn this on
