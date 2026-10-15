import re

class CleanerSanitizerConfig:
    def __init__(self):
        self.max_length = 4096
        self.blacklist = [
            r"<script>",
            r"DROP TABLE",
            r"eval\(",
            r"system\("
        ]
        self.enforce_ascii = True