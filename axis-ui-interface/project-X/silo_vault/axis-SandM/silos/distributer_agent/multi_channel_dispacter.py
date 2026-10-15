import sys
from lib.multi_channels_dispatcher_tool import DispatcherEngine
from config.multi_channels_dispatcher_config import MultiChannelsDispatcherConfig

def run_dispatcher():
    """Main orchestrator for the Multi-Channels Dispatcher agent."""
    config = MultiChannelsDispatcherConfig()
    engine = DispatcherEngine(config)
    
    try:
        if engine.dispatch_payloads():
            print("Dispatch: payloads written to the channel outboxes (delivery is confirmed by receipts, see verify_delivery).")
        else:
            print("Dispatch: nothing was sent (nothing queued or due), or a write failed.")
    except Exception as e:
        print(f"Critical error in multi_channels_dispatcher: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_dispatcher()