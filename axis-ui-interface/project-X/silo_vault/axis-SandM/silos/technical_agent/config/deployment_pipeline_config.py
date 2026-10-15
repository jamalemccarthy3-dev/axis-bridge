class DeploymentPipelineConfig:
    def __init__(self):
        # Operational parameters for the Deployment Pipeline
        self.DEPLOY_TARGET = "production"
        self.ENABLE_ROLLBACK = True
        
        # Pipeline steps
        self.RUN_UNIT_TESTS = True
        self.RUN_INTEGRATION_TESTS = True
        self.TIMEOUT_LIMIT = 600 # seconds
