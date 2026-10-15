class AuditTrailLoggerConfig:
    def __init__(self):
        # Operational parameters for the Audit Trail Logger
        self.LOG_FILE_PATH = "data/logs/audit_trail.log"
        self.TAMPER_EVIDENT = True   # hash-chained lines: editing one is detected. It is not encrypted.
        
        # Logging settings
        self.LOG_LEVEL = "INFO" # Options: DEBUG, INFO, WARNING, CRITICAL
        self.AUTO_ROTATE_SIZE_MB = 10
