import sys
from lib.api_interrogator_tool import APIInterrogatorEngine
from config.api_interrogator_config import APIInterrogatorConfig

def run_api_interrogator():
    """Main orchestrator for the API Interrogator agent."""
    config = APIInterrogatorConfig()
    engine = APIInterrogatorEngine(config)
    
    try:
        # Run diagnostic check on defined endpoints
        results = engine.scan_endpoints()
        print(f"API Scan completed. Status: {results['summary']}")
    except Exception as e:
        print(f"Critical error in api_interrogator: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_api_interrogator()

