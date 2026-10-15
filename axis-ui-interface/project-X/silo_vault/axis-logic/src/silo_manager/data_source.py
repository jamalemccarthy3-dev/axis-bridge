# MASTER DATA SOURCE: SRC/data_source.py
import csv
import json
import os


class DataSource:
    """The gatekeeper every silo reads its data through. connect() only succeeds for a file that exists; fetch() returns the real records
    (a .json file as parsed, a .csv file as a list of rows). Anything else is refused with a reason."""

    def __init__(self, silo_name):
        self.silo_name = silo_name
        self.connection_status = "DISCONNECTED"
        self.source_path = None

    def connect(self, source_path):
        self.source_path = source_path
        if source_path and os.path.isfile(source_path):
            self.connection_status = "ACTIVE"
            print(f"[{self.silo_name}] Gatekeeper: Connection established to {source_path}")
            return True
        self.connection_status = "DISCONNECTED"
        return False

    def fetch(self):
        if self.connection_status != "ACTIVE":
            return {"status": "ERROR", "data": "UNAUTHORIZED_ACCESS"}
        ext = os.path.splitext(self.source_path)[1].lower()
        try:
            with open(self.source_path, encoding="utf-8", newline="") as f:
                if ext == ".json":
                    return {"status": "SUCCESS", "data": json.load(f)}
                if ext == ".csv":
                    return {"status": "SUCCESS", "data": list(csv.DictReader(f))}
        except (OSError, ValueError) as e:
            return {"status": "ERROR", "data": "UNREADABLE: %s" % e}
        return {"status": "ERROR", "data": "UNSUPPORTED_TYPE %s (use .json or .csv)" % ext}
