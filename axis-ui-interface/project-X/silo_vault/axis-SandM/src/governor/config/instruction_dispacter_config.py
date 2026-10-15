class InstructionDispatcherConfig:
    def __init__(self):
        # Operational parameters for the Instruction Dispatcher
        self.QUEUE_LIMIT = 50
        self.PRIORITY_LEVELS = ["CRITICAL", "HIGH", "NORMAL", "LOW"]
        
        # Dispatch configuration
        self.ENABLE_ASYNC = True
        self.TIMEOUT_MS = 5000
