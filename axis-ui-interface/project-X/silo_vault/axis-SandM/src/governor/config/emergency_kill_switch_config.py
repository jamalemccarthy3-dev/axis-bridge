class EmergencyKillSwitchConfig:
    def __init__(self):
        # Operational parameters for the Kill Switch
        self.SHUTDOWN_MODE = "HARD_STOP" # Options: SOFT_CLOSE, HARD_STOP
        self.LOG_TERMINATION_EVENTS = True
        
        # Trigger conditions
        self.ENABLE_AUTO_TRIGGER = True
        self.TRIGGER_SIGNAL_PATH = "data/state/kill_switch_signal"

