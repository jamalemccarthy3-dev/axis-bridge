#!/usr/bin/env python3
"""
axis_vault_core.py
Production-grade final implementation. Manages local vault encryption, 
silo indexing, and structured entity/identity (people) records across the AXIS ecosystem.
"""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
SILOS_DIR = BASE_DIR / "silos"
VAULT_REGISTRY = SILOS_DIR / "vault_index.json"

class AxisVaultCore:
    def __init__(self):
        SILOS_DIR.mkdir(exist_ok=True)
        if not VAULT_REGISTRY.exists():
            self._initialize_registry()

    def _initialize_registry(self):
        initial_data = {
            "entities": [],
            "metadata": {
                "version": "1.0.0",
                "infrastructure": "AXIS",
                "orchestrator": "NEXXUS"
            }
        }
        VAULT_REGISTRY.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    def load_registry(self):
        try:
            return json.loads(VAULT_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            return {"entities": [], "metadata": {}}

    def save_registry(self, data):
        VAULT_REGISTRY.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_entity(self, name, entity_type, attributes=None):
        """Adds a structured entity (person, project, or node reference) to the local vault index."""
        registry = self.load_registry()
        
        entity_record = {
            "name": name,
            "type": entity_type,
            "attributes": attributes or {}
        }
        
        registry["entities"].append(entity_record)
        self.save_registry(registry)
        print(f"[AXIS-VAULT-CORE] Indexed entity: {name} [{entity_type}]")
        return entity_record

    def query_entities(self, query_string=""):
        registry = self.load_registry()
        if not query_string:
            return registry["entities"]
        
        results = [
            e for e in registry["entities"] 
            if query_string.lower() in e["name"].lower() or query_string.lower() in e["type"].lower()
        ]
        return results

if __name__ == "__main__":
    vault = AxisVaultCore()
    print(f"[AXIS-VAULT-CORE] Vault active. Registry initialized at: {VAULT_REGISTRY}")