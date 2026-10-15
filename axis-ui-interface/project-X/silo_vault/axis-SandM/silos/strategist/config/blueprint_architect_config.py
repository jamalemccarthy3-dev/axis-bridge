class BlueprintArchitectConfig:
    def __init__(self):
        # Operational parameters for the Blueprint Architect
        self.OUTPUT_SCHEMA_FORMAT = "json"
        self.TEMPLATE_DIR = "assets/blueprints/templates/"
        
        # Architecture constraints
        self.ENFORCE_MODULARITY = True
        self.STRICT_INTER_SILO_COMMUNICATION = True
