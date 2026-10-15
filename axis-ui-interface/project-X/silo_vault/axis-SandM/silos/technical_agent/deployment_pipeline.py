import sys
from lib.deployment_pipeline_tool import DeploymentPipelineEngine
from config.deployment_pipeline_config import DeploymentPipelineConfig

def run_pipeline():
    """Main orchestrator for the Deployment Pipeline agent."""
    config = DeploymentPipelineConfig()
    engine = DeploymentPipelineEngine(config)
    
    try:
        if engine.execute_pipeline():
            print("Deployment pipeline completed successfully.")
        else:
            print("Deployment pipeline halted: %s" % engine.last_run.get("why"))
    except Exception as e:
        print(f"Critical error in deployment_pipeline: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_pipeline()