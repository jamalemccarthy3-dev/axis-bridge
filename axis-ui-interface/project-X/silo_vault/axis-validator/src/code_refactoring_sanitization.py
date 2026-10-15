"""
Core entry point for the code_refactoring_sanitization module.
Binds configuration specs with underlying code refactoring and sanitization tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.code_refactoring_sanitization_config import CODE_SANITIZATION_CONFIG
from lib.code_refactoring_sanitization_tool import CodeRefactoringSanitizationTool

class CodeRefactoringSanitization:
    def __init__(self):
        self.config = CODE_SANITIZATION_CONFIG
        self.tool = CodeRefactoringSanitizationTool(self.config)

    def sanitize(self, patterns: list, depth: int) -> bool:
        """Executes the code refactoring and sanitization check."""
        success, telemetry = self.tool.sanitize_codebase(patterns, depth)
        print(f"[{self.config['module_name']}] Sanitization Status -> Success: {success}")
        print(f"Telemetry Data: {telemetry}")
        return success

if __name__ == "__main__":
    sanitizer = CodeRefactoringSanitization()
    # Sanity verification mock
    sanitizer.sanitize([], 4)