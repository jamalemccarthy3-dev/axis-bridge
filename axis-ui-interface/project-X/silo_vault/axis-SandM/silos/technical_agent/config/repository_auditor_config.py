class RepositoryAuditorConfig:
    def __init__(self):
        # Operational parameters for the Repository Auditor
        self.SCAN_TARGET_DIR = "src/"
        self.CHECK_DEPENDENCIES = True
        
        # Auditing settings
        self.SEVERITY_THRESHOLD = "MEDIUM" # Options: LOW, MEDIUM, HIGH, CRITICAL
        self.AUTO_FIX_MINOR_ISSUES = False
