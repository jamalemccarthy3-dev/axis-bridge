#!/usr/bin/env python3
"""
axis_cloud_server.py
Production-grade final implementation. Binds port 5000, hosts the local 
dashboard hub, and provides secure REST endpoints for system telemetry, 
the axis-tunnel-bridge WireGuard toggle, and local workspace file saves.
"""

import http.server
import json
import subprocess
import os
from pathlib import Path

PORT = 5000
BASE_DIR = Path(__file__).parent
FILES_DIR = BASE_DIR / "files"
FILES_DIR.mkdir(exist_ok=True)

class AxisServerHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            status = {
                "status": "online",
                "infrastructure": "AXIS",
                "orchestrator": "NEXXUS",
                "port": PORT,
                "storage_sink": str(FILES_DIR)
            }
            self.wfile.write(json.dumps(status).encode("utf-8"))
        else:
            # Serve local static dashboard assets from base directory
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/toggle-tunnel":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode('utf-8'))
                action = data.get("action")
            except json.JSONDecodeError:
                self._send_json_response(400, {"success": False, "error": "Invalid JSON payload"})
                return

            if action in ["up", "down"]:
                try:
                    cmd = ["wg-quick", action, "wg0"]
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    self._send_json_response(200, {"success": True, "output": result.stdout})
                except subprocess.CalledProcessError as e:
                    self._send_json_response(500, {"success": False, "error": e.stderr.strip()})
            else:
                self._send_json_response(400, {"success": False, "error": "Invalid action parameter; expected 'up' or 'down'"})

        elif self.path == "/api/save-file":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            try:
                data = json.loads(body.decode('utf-8'))
                filename = data.get("filename", "workspace_export.txt")
                content = data.get("content", "")

                # Sanitize filename to prevent directory traversal
                safe_filename = Path(filename).name
                file_path = FILES_DIR / safe_filename
                file_path.write_text(content, encoding="utf-8")

                self._send_json_response(200, {"success": True, "saved_to": str(file_path)})
            except Exception as e:
                self._send_json_response(500, {"success": False, "error": str(e)})
        else:
            self._send_json_response(404, {"success": False, "error": "Endpoint not found"})

    def _send_json_response(self, status_code, payload):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

def run():
    server_address = ("", PORT)
    httpd = http.server.HTTPServer(server_address, AxisServerHandler)
    print(f"[AXIS-CLOUD-SERVER] Locked and bound to port {PORT}. Ready for production execution.")
    httpd.serve_forever()

if __name__ == "__main__":
    run()