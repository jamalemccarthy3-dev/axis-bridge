import sys
from lib.asset_compliance_check_tool import ComplianceEngine
from config.asset_compliance_check_config import AssetComplianceCheckConfig

def run_compliance_check():
    """Main orchestrator for the Asset Compliance Check agent."""
    config = AssetComplianceCheckConfig()
    engine = ComplianceEngine(config)
    
    try:
        status = engine.validate_content("Final Asset Draft")
        if status['passed']:
            print("Compliance check passed: Asset cleared for distribution.")
        else:
            print(f"Compliance check failed: {status['violation_code']}")
    except Exception as e:
        print(f"Critical error in asset_compliance_check: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_compliance_check()