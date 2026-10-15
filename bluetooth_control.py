"""
bluetooth_control.py - find, add, connect, disconnect and remove Bluetooth devices from NEXXUS.

Runs on the PC that has the Bluetooth radio. Uses `bleak` (free; pip install bleak), which talks to the Windows
Bluetooth stack. Honest scope:
  * It finds Bluetooth LOW ENERGY devices (sensors, wearables, many speakers/keyboards advertise as BLE, phones
    often do when their Bluetooth screen is open). Classic-only devices (older headsets, some speakers) are paired
    in Windows Settings > Bluetooth; NEXXUS cannot see those through bleak.
  * "Add" = NEXXUS remembers the device (bluetooth_devices.json). "Connect" really opens a connection and keeps it
    open until "Disconnect". The radio is on the PC, so devices must be near the PC, not near you.
  * A device that is not advertising right now (asleep, off, out of range) will not be found.

States: discovered (seen in the last scan) / added (remembered) / connected / failed(reason). Nothing is reported
connected unless the library says the link is really up.

The radio work runs on one background event loop so a connection stays alive between requests. A fake backend is
used by the tests; the real one needs bleak and real hardware.
"""
import asyncio
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

ADDR = re.compile(r"^[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}$|^[0-9A-Fa-f-]{36}$")
MAX_DEVICES = 100


class BleakBackend:
    """The real thing. Imports bleak lazily so the rest of NEXXUS runs without it."""
    name = "bleak"

    def __init__(self):
        self._clients = {}

    @staticmethod
    def available():
        try:
            import bleak  # noqa: F401
            return True, None
        except ImportError:
            return False, "bleak is not installed: run  pip install bleak"

    async def scan(self, timeout):
        from bleak import BleakScanner
        found = await BleakScanner.discover(timeout=timeout, return_adv=True)
        out = []
        for addr, (dev, adv) in found.items():
            out.append({"address": str(addr), "name": dev.name or adv.local_name or "", "rssi": getattr(adv, "rssi", None)})
        return out

    async def connect(self, address, timeout):
        from bleak import BleakClient
        c = self._clients.get(address)
        if c is not None and c.is_connected:
            return True
        c = BleakClient(address, timeout=timeout)
        await c.connect()
        self._clients[address] = c
        return bool(c.is_connected)

    async def disconnect(self, address):
        c = self._clients.pop(address, None)
        if c is None:
            return True
        await c.disconnect()
        return not c.is_connected

    def is_connected(self, address):
        c = self._clients.get(address)
        return bool(c is not None and c.is_connected)


class BluetoothManager:
    def __init__(self, backend=None, path=None):
        self.backend = backend or BleakBackend()
        self._path = path
        self._lock = threading.RLock()
        self._loop = None
        self._thread = None
        self._seen = {}          # address -> {name, rssi, seen_at}   (last scan only)
        self._last_scan = None
        self._errors = {}        # address -> last failure text
        self._radio_problem = None   # set when the last scan found no usable Bluetooth radio (shown in the panel until a scan works)

    # ---- storage of added devices
    @property
    def path(self):
        return Path(self._path or os.environ.get("NEXXUS_BT_PATH") or (Path(__file__).resolve().parent / "bluetooth_devices.json"))

    def _load(self):
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return d if isinstance(d, list) else []
        except FileNotFoundError:
            return []
        except Exception:
            return []

    def _save(self, items):
        p = self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=1)
        os.replace(tmp, p)

    # ---- the radio loop
    def _ensure_loop(self):
        with self._lock:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="nexxus-bluetooth")
                self._thread.start()
            return self._loop

    def _call(self, coro, timeout):
        fut = asyncio.run_coroutine_threadsafe(coro, self._ensure_loop())
        try:
            return fut.result(timeout=timeout)
        except Exception:
            fut.cancel()
            raise

    @staticmethod
    def _clean(address):
        a = str(address or "").strip()
        if not ADDR.match(a):
            raise ValueError("not a Bluetooth address (expected AA:BB:CC:DD:EE:FF)")
        return a.upper().replace("-", ":") if ":" in a or len(a) == 17 else a

    def _usable(self):
        if hasattr(self.backend, "available"):
            ok, why = self.backend.available()
            if not ok:
                raise RuntimeError(why)

    # ---- actions
    def scan(self, seconds=6):
        """Look for advertising devices right now. Returns what was really heard."""
        self._usable()
        seconds = max(2, min(float(seconds), 20))
        try:
            found = self._call(self.backend.scan(seconds), seconds + 15)
        except Exception as e:
            text = "%s %s" % (type(e).__name__, e)
            if "NO_BLUETOOTH" in text or "No Bluetooth adapter" in text or "NotAvailable" in text:
                self._radio_problem = ("This PC has no usable Bluetooth radio: Windows reports no Bluetooth adapter, or Bluetooth is switched off. "
                                       "Plug in a Bluetooth adapter (or turn Bluetooth on in Windows Settings), then scan again. Nothing else in NEXXUS depends on it.")
                raise RuntimeError(self._radio_problem)
            raise RuntimeError("scan failed: %s: %s (is Bluetooth switched on in Windows?)" % (type(e).__name__, e))
        now = time.time()
        self._radio_problem = None
        with self._lock:
            self._seen = {d["address"]: {"name": d.get("name") or "", "rssi": d.get("rssi"), "seen_at": now} for d in found}
            self._last_scan = now
        return self.devices()

    def add(self, address, name=None):
        addr = self._clean(address)
        with self._lock:
            items = self._load()
            if any(i["address"] == addr for i in items):
                return next(i for i in items if i["address"] == addr)
            if len(items) >= MAX_DEVICES:
                raise ValueError("too many devices (%d)" % MAX_DEVICES)
            nm = (name or self._seen.get(addr, {}).get("name") or addr)[:60]
            item = {"address": addr, "name": nm, "added_at": time.time()}
            items.append(item)
            self._save(items)
            return item

    def remove(self, address):
        """Forget the device (and disconnect it first if it is connected)."""
        addr = self._clean(address)
        if self._is_connected(addr):
            self.disconnect(addr)
        with self._lock:
            items = self._load()
            kept = [i for i in items if i["address"] != addr]
            if len(kept) == len(items):
                raise KeyError(addr)
            self._save(kept)
            self._errors.pop(addr, None)
        return {"removed": addr}

    def connect(self, address, timeout=20):
        self._usable()
        addr = self._clean(address)
        with self._lock:
            if not any(i["address"] == addr for i in self._load()):
                raise KeyError(addr)        # only devices you added can be connected
        try:
            ok = self._call(self.backend.connect(addr, timeout), timeout + 10)
        except Exception as e:
            self._errors[addr] = "%s: %s" % (type(e).__name__, str(e)[:160] or "could not connect (asleep, out of range or already in use?)")
            raise RuntimeError(self._errors[addr])
        if not ok:
            self._errors[addr] = "the device refused the connection"
            raise RuntimeError(self._errors[addr])
        self._errors.pop(addr, None)
        return self._view(addr)

    def disconnect(self, address):
        self._usable()
        addr = self._clean(address)
        try:
            ok = self._call(self.backend.disconnect(addr), 20)
        except Exception as e:
            raise RuntimeError("disconnect failed: %s: %s" % (type(e).__name__, e))
        if not ok:
            raise RuntimeError("the device is still connected")
        return self._view(addr)

    def disconnect_all(self):
        done = []
        for i in self._load():
            if self._is_connected(i["address"]):
                try:
                    self.disconnect(i["address"]); done.append(i["address"])
                except Exception:
                    pass
        return done

    # ---- views
    def _is_connected(self, addr):
        try:
            return bool(self.backend.is_connected(addr))
        except Exception:
            return False

    def _view(self, addr):
        added = {i["address"]: i for i in self._load()}.get(addr)
        seen = self._seen.get(addr)
        state = "connected" if self._is_connected(addr) else ("added" if added else "discovered")
        return {"address": addr, "name": (added or {}).get("name") or (seen or {}).get("name") or addr, "state": state,
                "added": bool(added), "in_range": bool(seen), "rssi": (seen or {}).get("rssi"), "error": self._errors.get(addr)}

    def devices(self):
        with self._lock:
            addrs = list(dict.fromkeys([i["address"] for i in self._load()] + list(self._seen)))
            items = [self._view(a) for a in addrs]
        order = {"connected": 0, "added": 1, "discovered": 2}
        items.sort(key=lambda d: (order[d["state"]], d["name"].lower()))
        ok, why = (self.backend.available() if hasattr(self.backend, "available") else (True, None))
        if ok and self._radio_problem:
            ok, why = False, self._radio_problem
        return {"backend": getattr(self.backend, "name", "custom"), "available": ok, "unavailable_reason": why,
                "last_scan": self._last_scan, "devices": items}