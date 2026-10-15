class DeploymentGatekeeperConfig:
    def __init__(self):
        # Operational parameters for the Deployment Gatekeeper
        self.REQUIRE_SIGNATURE = True
        self.STAGING_ENV_ONLY = True
        
        # Validation checks
        self.CHECK_SECURITY_VULNERABILITIES = True
        self.CHECK_TEST_COVERAGE = 80.0 # Percentage