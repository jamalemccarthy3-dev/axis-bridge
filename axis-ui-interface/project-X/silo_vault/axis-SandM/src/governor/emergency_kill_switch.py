import sys
from lib.emergency_kill_switch_tool import KillSwitchEngine
from config.emergency_kill_switch_config import EmergencyKillSwitchConfig

def run_kill_switch():
    """Main orchestrator for the Emergency Kill Switch agent."""
    config = EmergencyKillSwitchConfig()
    engine = KillSwitchEngine(config)
    
    try:
        # Emergency monitoring loop or instant trigger check
        if engine.is_triggered():
            engine.execute_shutdown()
        else:
            print("System state nominal. No shutdown initiated.")
    except Exception as e:
        print(f"Critical error in emergency_kill_switch: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_kill_switch()
