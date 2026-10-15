import sys
from lib.query_manager_tool import QueryManagerEngine
from config.query_manager_config import QueryManagerConfig

def run_query_manager():
    """Main orchestrator for the Query Manager agent."""
    config = QueryManagerConfig()
    engine = QueryManagerEngine(config)
    
    try:
        # Initializing the queue processor
        r = engine.process_incoming_requests()
        print(f"Query Manager: {r['accepted']} accepted, {r['rejected']} rejected, {r['left_waiting']} left waiting.")
    except Exception as e:
        print(f"Critical error in query_manager: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_query_manager()

