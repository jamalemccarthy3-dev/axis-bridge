# src/dependency_mapper_utility.py
import os
import re
import logging

class DependencyMapperEngine:
    def __init__(self, config):
        self.src_dir = config.src_dir
        self.logger = logging.getLogger("Factory.Governance.Mapper")

    def map_directory(self):
        """Scans the source directory and maps module dependencies."""
        dependency_map = {}
        try:
            for filename in os.listdir(self.src_dir):
                if filename.endswith(".py"):
                    path = os.path.join(self.src_dir, filename)
                    with open(path, "r") as f:
                        content = f.read()
                        # Extract 'from x import y' or 'import x' patterns
                        imports = re.findall(r'from\s+(\S+)|import\s+(\S+)', content)
                        # Flatten results and clean
                        deps = [imp[0] or imp[1] for imp in imports]
                        dependency_map[filename] = list(set(deps))
            
            return {"status": "success", "map": dependency_map, "code": 200}
        except Exception as e:
            self.logger.error(f"Mapping failure: {e}")
            return {"status": "error", "message": str(e), "code": 500}