class MultiChannelsDispatcherConfig:
    def __init__(self):
        # Operational parameters for the Multi-Channels Dispatcher
        self.ACTIVE_CHANNELS = ["api_gateway", "web_socket_hub", "email_relay"]
        self.RETRY_POLICY = "exponential_backoff"
        
        # Dispatch settings
        self.PARALLEL_THREADS = 5
        self.ENFORCE_DELIVERY_RECEIPT = True
