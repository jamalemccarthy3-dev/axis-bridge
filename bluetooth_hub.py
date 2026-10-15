import asyncio
from bleak import BleakScanner, BleakClient

class BluetoothHub:
    def __init__(self):
        self.discovered_devices = {}
        self.active_connections = {}

    async def scan_airspace(self, timeout=5.0):
        """Scans for nearby Bluetooth devices and populates the feed."""
        print("[BluetoothHub] Scanning for active hardware...")
        try:
            devices = await BleakScanner.discover(timeout=timeout)
            self.discovered_devices = {d.address: d for d in devices}
            return [
                {
                    "name": d.name or "Unknown Device", 
                    "address": d.address,
                    "rssi": getattr(d, 'rssi', None)
                } 
                for d in devices
            ]
        except Exception as e:
            print(f"[BluetoothHub] Scan error: {e}")
            return []

    async def pair_and_connect(self, address):
        """Pairs and connects to a selected device on the fly."""
        if address not in self.discovered_devices:
            print(f"[BluetoothHub] Device {address} not found. Run a scan first.")
            return False
        
        device = self.discovered_devices[address]
        client = BleakClient(device)
        
        try:
            print(f"[BluetoothHub] Connecting to {device.name or address}...")
            await client.connect()
            
            if client.is_connected:
                # Attempt pairing protocol if supported by the OS/hardware stack
                try:
                    await client.pair()
                    print(f"[BluetoothHub] Successfully paired and bound to {device.name}")
                except Exception as pair_err:
                    print(f"[BluetoothHub] Note: Direct pairing skipped or unsupported by OS wrapper: {pair_err}")
                
                self.active_connections[address] = client
                return True
        except Exception as e:
            print(f"[BluetoothHub] Connection failed for {address}: {e}")
            return False

    async def disconnect_device(self, address):
        """Gracefully drops connection to an active device."""
        if address in self.active_connections:
            client = self.active_connections[address]
            await client.disconnect()
            del self.active_connections[address]
            print(f"[BluetoothHub] Disconnected from {address}")
            return True
        return False

# Global instance for easy importing across your settings wedge backend routes
bt_hub = BluetoothHub()