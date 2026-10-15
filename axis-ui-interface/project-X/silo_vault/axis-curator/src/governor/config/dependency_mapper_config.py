# src/dependency_mapper_config.py
import os

class DependencyMapperConfig:
    def __init__(self):
        # Defines the directory to be mapped
        self.src_dir = os.path.join(os.getcwd(), "src")
        self.ignore_list = ["__init__.py"]