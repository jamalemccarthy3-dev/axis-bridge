import sys
from lib.data_aggregator_tool import DataAggregatorEngine
from config.data_aggregator_config import DataAggregatorConfig

def run_data_aggregator():
    """Main orchestrator for the Data Aggregator agent."""
    config = DataAggregatorConfig()
    engine = DataAggregatorEngine(config)
    
    try:
        # Centralizing telemetry from across all silos
        report = engine.sync_all_data_streams()
        print(f"Data aggregation successful. Records processed: {report['record_count']}")
    except Exception as e:
        print(f"Critical error in data_aggregator: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_data_aggregator()
