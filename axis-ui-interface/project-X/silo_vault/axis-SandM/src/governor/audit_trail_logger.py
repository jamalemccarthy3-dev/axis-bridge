import sys
from lib.audit_trail_logger_tool import AuditTrailLoggerEngine
from config.audit_trail_logger_config import AuditTrailLoggerConfig

def run_logger():
    """Main orchestrator for the Audit Trail Logger agent."""
    config = AuditTrailLoggerConfig()
    engine = AuditTrailLoggerEngine(config)
    
    try:
        engine.initialize_session_log()
        print("Audit Trail Logger initialized. Monitoring active.")
    except Exception as e:
        print(f"Critical error in audit_trail_logger: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_logger()

