import sys
from lib.version_controller_tool import VersionControlEngine
from config.version_controller_config import VersionControlConfig

def run_version_control():
    """Main orchestrator for the Version Controller agent."""
    config = VersionControlConfig()
    engine = VersionControlEngine(config)
    
    try:
        r = engine.check_repo_status()
        print("Version Control: %s, branch %s, %s file(s) changed, ahead %s / behind %s." % (r["status"], r.get("branch"), r.get("dirty_files"), r.get("ahead"), r.get("behind")))
    except Exception as e:
        print(f"Critical error in version_controller: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_version_control()
