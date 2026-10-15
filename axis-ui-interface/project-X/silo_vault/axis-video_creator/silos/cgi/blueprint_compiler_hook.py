# operations/cgi_silo/com_lib/blueprint_compiler_hook.py
from lib.blueprint_compiler_hook_tool import blueprint_compiler_hook_tool
from config.blueprint_compiler_hook_config import blueprint_compiler_hook_config

class blueprint_compiler_hook:
    def __init__(self):
        self.tool = blueprint_compiler_hook_tool(blueprint_compiler_hook_config)

    def execute_compilation(self, blueprint_data):
        """Triggers the compilation process for the provided blueprint."""
        return self.tool.compile_blueprint(blueprint_data)

    def verify_syntax(self, blueprint_id):
        """Checks the integrity and syntax of the compiled output."""
        return self.tool.validate_syntax(blueprint_id)

if __name__ == "__main__":
    # Test block to verify initialization
    try:
        hook = blueprint_compiler_hook()
        print("Blueprint compiler hook initialized successfully.")
    except Exception as e:
        print(f"Test failed with error: {e}")