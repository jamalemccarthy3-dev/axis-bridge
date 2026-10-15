class VersionControlConfig:
    def __init__(self):
        # Operational parameters for the Version Controller
        self.REPO_URL = None   # the repository is whatever git repo this engine sits in
        self.DEFAULT_BRANCH = "main"
        
        # VCS settings
        self.AUTO_FETCH_ENABLED = False   # a fetch uses the network; turn on if you want it
        self.STRICT_COMMIT_RULES = True
