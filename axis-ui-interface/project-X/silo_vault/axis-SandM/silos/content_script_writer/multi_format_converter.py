import sys
from lib.multi_format_converter_tool import FormatConverterEngine
from config.multi_format_converter_config import MultiFormatConverterConfig

def run_format_converter():
    """Main orchestrator for the Multi-Format Converter agent."""
    config = MultiFormatConverterConfig()
    engine = FormatConverterEngine(config)
    
    try:
        # Transforming content into target delivery formats
        engine.convert_asset("MASTER_NARRATIVE_V1")
        print("Content conversion sequence complete.")
    except Exception as e:
        print(f"Critical error in multi_format_converter: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_format_converter()
