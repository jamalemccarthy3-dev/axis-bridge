import sys
from lib.prototype_renderer_tool import PrototypeRendererEngine
from config.prototype_renderer_config import PrototypeRendererConfig

def run_renderer():
    """Main orchestrator for the Prototype Renderer agent."""
    config = PrototypeRendererConfig()
    engine = PrototypeRendererEngine(config)
    
    try:
        if engine.render_active_prototype():
            print("Prototype written to %s" % engine.output)
        else:
            print("Rendering failed: %s" % engine.last_error)
    except Exception as e:
        print(f"Critical error in prototype_renderer: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_renderer()