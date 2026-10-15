#!/usr/bin/env python3
"""
axis_cert_mgr.py
Production-grade final implementation. Manages self-signed SSL/TLS certificates 
for local secure routing and HTTPS endpoints across the AXIS infrastructure.
"""

import subprocess
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
CERT_DIR = BASE_DIR / "config" / "certificates"

class AxisCertMgr:
    def __init__(self, cert_dir=CERT_DIR):
        self.cert_dir = cert_dir
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        self.cert_file = self.cert_dir / "axis-cert.pem"
        self.key_file = self.cert_dir / "axis-key.pem"

    def generate_self_signed(self, days=365):
        """Generates a self-signed SSL certificate and private key for local secure routing."""
        if self.cert_file.exists() and self.key_file.exists():
            print(f"[AXIS-CERT-MGR] Certificates already exist at {self.cert_dir}")
            return {"success": True, "message": "Certificates already exist", "cert": str(self.cert_file)}

        try:
            cmd = [
                "openssl", "req", "-x509", "-newkey", "rsa:4096",
                "-keyout", str(self.key_file),
                "-out", str(self.cert_file),
                "-days", str(days), "-nodes",
                "-subj", "/CN=axis-local-node"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"[AXIS-CERT-MGR] Self-signed certificate generated successfully at {self.cert_dir}")
            return {"success": True, "output": result.stdout.strip(), "cert": str(self.cert_file)}
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() or e.stdout.strip()
            print(f"[AXIS-CERT-MGR] ERROR: Failed to generate certificate: {error_msg}")
            return {"success": False, "error": error_msg}
        except FileNotFoundError:
            error_msg = "OpenSSL binary not found on system path."
            print(f"[AXIS-CERT-MGR] ERROR: {error_msg}")
            return {"success": False, "error": error_msg}

    def status(self):
        """Checks if local certificates exist and are accessible."""
        exists = self.cert_file.exists() and self.key_file.exists()
        return {
            "active": exists,
            "cert_path": str(self.cert_file),
            "key_path": str(self.key_file)
        }

if __name__ == "__main__":
    manager = AxisCertMgr()
    if len(sys.argv) > 1 and sys.argv[1].lower() == "generate":
        print(json.dumps(manager.generate_self_signed(), indent=2))
    else:
        print(json.dumps(manager.status(), indent=2))