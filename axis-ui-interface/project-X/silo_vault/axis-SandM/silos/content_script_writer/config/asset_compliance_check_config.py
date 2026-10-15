class AssetComplianceCheckConfig:
    def __init__(self):
        # Operational parameters for the Asset Compliance Check
        self.STRICT_MODE = True
        self.BLACKLISTED_TERMS = ["misleading_claim_a", "unverified_data_b"]
        
        # Governance alignment
        self.REQUIRE_GOVERNOR_APPROVAL = True
        self.LOG_AUDIT_TRAIL = True
