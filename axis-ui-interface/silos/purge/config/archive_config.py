# Final Copy: The Archive Configuration
class ArchiveConfig:
    def get_storage_policy(self):
        """Sets the vault location and access protocols."""
        return {
            "vault_path": "/secure/vault/projects",
            "access_control": "RESTRICTED"
        }
