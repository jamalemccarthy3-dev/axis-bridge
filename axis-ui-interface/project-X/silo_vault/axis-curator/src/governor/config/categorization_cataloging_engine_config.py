# src/categorization_cataloging_config.py
class CategorizationCatalogingConfig:
    def __init__(self):
        # Classification mapping rules
        self.core_extensions = [".py", ".sh", ".bat"]
        self.doc_extensions = [".txt", ".md", ".pdf"]
        self.default_category = "GENERAL_ASSET"