"""
Core entry point for the extraction_parsing_pipeline module.
Binds configuration specs with underlying extraction pipeline tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.extraction_parsing_pipeline_config import EXTRACTION_PIPELINE_CONFIG
from lib.extraction_parsing_pipeline_tool import ExtractionParsingPipelineTool

class ExtractionParsingPipeline:
    def __init__(self):
        self.config = EXTRACTION_PIPELINE_CONFIG
        self.tool = ExtractionParsingPipelineTool(self.config)

    def extract(self, size_mb: float, syntax_ok: bool) -> bool:
        """Executes the extraction parsing pipeline verification check."""
        success, telemetry = self.tool.process_extraction_stream(size_mb, syntax_ok)
        print(f"[{self.config['module_name']}] Extraction Status -> Success: {success}")
        print(f"Telemetry Data: {telemetry}")
        return success

if __name__ == "__main__":
    pipeline = ExtractionParsingPipeline()
    # Sanity verification mock
    pipeline.extract(2.5, True)