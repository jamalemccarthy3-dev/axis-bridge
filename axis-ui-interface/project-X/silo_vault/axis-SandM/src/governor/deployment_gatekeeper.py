import sys
from lib.deployment_gatekeeper_tool import DeploymentGatekeeperEngine
from config.deployment_gatekeeper_config import DeploymentGatekeeperConfig

def run_gatekeeper():
    """Main orchestrator for the Deployment Gatekeeper agent."""
    config = DeploymentGatekeeperConfig()
    engine = DeploymentGatekeeperEngine(config)
    
    try:
        if engine.verify_deployment_readiness():
            print("Deployment gate passed. Initiating release.")
        else:
            print("Deployment gate blocked: Security or QA failure.")
    except Exception as e:
        print(f"Critical error in deployment_gatekeeper: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_gatekeeper()

