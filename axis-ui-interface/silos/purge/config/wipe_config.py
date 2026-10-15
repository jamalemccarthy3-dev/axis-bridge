# Final Copy: The Purge Configuration
class WipeConfig:
    def get_wipe_parameters(self):
        """Returns the intensity of the wipe/purge."""
        return {
            "recursive_cleanup": True,
            "force_memory_release": True
        }