#src/orchestrator.py

class orchestrator:
    def __init__(self):
        self.state = "IDLE"
        self.staging_area = []
        self.awaiting_authorization = False
        self.current_manifest = None

    def start_mission(self, manifest):
        """Intake Phase: Set the mission and hold at the Drive."""
        self.current_manifest = manifest
        self.state = "AT_DRIVE_HOLDING"
        print(f"[ORCHESTRATOR] Holding at Drive. Mission {manifest['id']} ready.")

    def authorize_next_step(self):
        """The Security Gatekeeper: Grants permission to move between isolated systems."""
        self.awaiting_authorization = True
        print("[ORCHESTRATOR] Authorization received.")

    def proceed_to_port(self):
        """Transit Phase: Controlled move from Drive to Port."""
        if self.awaiting_authorization:
            self.state = "AT_PORT_HOLDING"
            self.awaiting_authorization = False 
            print("[ORCHESTRATOR] Secure transition to Port authorized.")
        else:
            print("[SECURITY ALERT] Unauthorized lateral movement blocked.")

    def finalize_delivery(self):
        """Completion Phase: Confirm build and trigger Amnesia."""
        print("[ORCHESTRATOR] Delivery confirmed by Nexus. Executing Purge.")
        self.purge_amnesia()

    def purge_amnesia(self):
        """Security Purge: Wipe mission data to maintain system state."""
        self.staging_area = []
        self.current_manifest = None
        self.state = "CLEAN_AND_IDLE"
        print("[ORCHESTRATOR] Amnesia triggered. Link is clean.")



Orchestrator = orchestrator      # alias: the importers use this spelling
