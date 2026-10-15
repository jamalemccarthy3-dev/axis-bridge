import sys
from lib.repository_auditor_tool import RepositoryAuditorEngine
from config.repository_auditor_config import RepositoryAuditorConfig

def run_auditor():
    """Main orchestrator for the Repository Auditor agent."""
    config = RepositoryAuditorConfig()
    engine = RepositoryAuditorEngine(config)
    
    try:
        if engine.run_audit_cycle():
            print("Repository audit completed: nothing at or above the severity threshold.")
        else:
            print("Audit failed: %d finding(s) (see data/state/repo_audit.json), or the scan folder was not found." % len(engine.findings))
    except Exception as e:
        print(f"Critical error in repository_auditor: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_auditor()