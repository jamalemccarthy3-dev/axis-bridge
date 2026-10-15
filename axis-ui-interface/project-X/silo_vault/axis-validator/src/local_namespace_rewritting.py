"""
Core entry point for the local_namespace_rewriting module.
Binds configuration specs with underlying namespace rewriting tool execution handlers.
"""

import sys
from pathlib import Path

# Ensure absolute local path integration
sys.path.append(str(Path(__file__).resolve().parent))

from config.local_namespace_rewritting_config import LOCAL_NAMESPACE_CONFIG
from lib.local_namespace_rewritting_tool import LocalNamespaceRewritingTool

class LocalNamespaceRewriting:
    def __init__(self):
        self.config = LOCAL_NAMESPACE_CONFIG
        self.tool = LocalNamespaceRewritingTool(self.config)

    def rewrite(self, namespace: str, global_scope: bool) -> bool:
        """Executes the local namespace rewriting and isolation check."""
        rewritten, telemetry = self.tool.rewrite_namespace(namespace, global_scope)
        print(f"[{self.config['module_name']}] Rewriting Status -> Success: {rewritten}")
        print(f"Telemetry Data: {telemetry}")
        return rewritten

if __name__ == "__main__":
    rewriter = LocalNamespaceRewriting()
    # Sanity verification mock
    rewriter.rewrite("axis.validator.local", False)