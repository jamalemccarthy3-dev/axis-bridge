import sys
from lib.instruction_dispacter_tool import InstructionDispatcherEngine
from config.instruction_dispacter_config import InstructionDispatcherConfig

def run_dispatcher():
    """Main orchestrator for the Instruction Dispatcher agent."""
    config = InstructionDispatcherConfig()
    engine = InstructionDispatcherEngine(config)
    
    try:
        if engine.process_queue():
            print("Instruction queue processed successfully.")
        else:
            print("Dispatch failure: Queue empty or corrupted.")
    except Exception as e:
        print(f"Critical error in instruction_dispatcher: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_dispatcher()