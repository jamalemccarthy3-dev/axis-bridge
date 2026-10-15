# src/curate_input_path_utility.py
import os
import logging

class CurateInputPathEngine:
    def __init__(self, config):
        self.base_path = os.path.abspath(config.base_path)
        self.restricted_paths = [os.path.abspath(p) for p in config.restricted_paths]
        self.logger = logging.getLogger("Factory.Curator.PathRouter")

    def resolve(self, data_id):
        """
        Resolves a data_id to an absolute path and validates it 
        against the authorized base directory.
        """
        try:
            # Construct absolute target
            target = os.path.normpath(os.path.join(self.base_path, data_id))
            
            # Security check: Ensure the path is within base_path and not restricted
            if not target.startswith(self.base_path):
                self.logger.warning(f"Unauthorized access attempt to: {target}")
                return {"status": "denied", "code": 403}
                
            if any(target.startswith(restricted) for restricted in self.restricted_paths):
                self.logger.critical(f"Access to restricted system path denied: {target}")
                return {"status": "restricted", "code": 403}

            return {"status": "resolved", "path": target, "code": 200}
            
        except Exception as e:
            self.logger.error(f"Path resolution error: {e}")
            return {"status": "error", "code": 500}