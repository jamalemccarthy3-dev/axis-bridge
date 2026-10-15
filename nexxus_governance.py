"""
nexxus_governance.py - command authentication for the NEXXUS mesh.

The old check (origin == "NEXXUS_EXECUTOR") is just a string any caller can
type, so it authenticates nothing. This version requires an HMAC-SHA256
signature over the command, made with a local secret (NEXXUS_GOVERNANCE_SECRET),
plus a fresh timestamp to block replay. Free, local, stdlib only.
"""
import hashlib
import hmac
import json
import os
import time

MAX_AGE_SECONDS = 60
BOOT_TS = time.time()          # when this process started: the replay floor for packets that engines send to the hub (see validate_engine_packet)
ENGINE_ORIGIN = "ENGINE:"      # origin of a packet signed with an engine's own derived key: "ENGINE:<engine name>"


def _secret():
    s = os.environ.get("NEXXUS_GOVERNANCE_SECRET", "")
    return s.encode() if s else None


def _body(packet):
    return json.dumps({k: v for k, v in packet.items() if k != "signature"}, sort_keys=True).encode()


def sign_command(packet):
    sec = _secret()
    if not sec:
        raise RuntimeError("NEXXUS_GOVERNANCE_SECRET is not set")
    packet = dict(packet, origin="NEXXUS_EXECUTOR", ts=time.time())
    packet["signature"] = hmac.new(sec, _body(packet), hashlib.sha256).hexdigest()
    return packet


def engine_key(name):
    """The key one engine signs with: HMAC(shared secret, "engine:" + name). Derived, so there is still one secret to manage, but a packet signed by engine A cannot pass as engine B:
    the hub derives B's key from the engine name the packet CLAIMS, and A's signature will not verify under it. None if no secret is set."""
    sec = _secret()
    if not sec or not str(name or "").strip():
        return None
    return hmac.new(sec, b"nexxus-engine-key/1:" + str(name).encode("utf-8"), hashlib.sha256).digest()


def sign_as_engine(packet):
    """Sign a packet as the engine named in packet["engine"], with that engine's own derived key (origin "ENGINE:<name>")."""
    name = (packet or {}).get("engine")
    key = engine_key(name)
    if key is None:
        raise RuntimeError("NEXXUS_GOVERNANCE_SECRET is not set (or the packet names no engine)")
    packet = dict(packet, origin=ENGINE_ORIGIN + str(name), ts=time.time())
    packet["signature"] = hmac.new(key, _body(packet), hashlib.sha256).hexdigest()
    return packet


def _axis_gate():
    """The axis gate (axis-ui-interface/project-X/axis_gate). Every mesh packet is judged by it: signature, freshness, and single use."""
    try:
        import axis_gate
        return axis_gate
    except ImportError:
        import sys
        px = str(Path(__file__).resolve().parent / "axis-ui-interface" / "project-X")
        if px not in sys.path:
            sys.path.insert(0, px)
        import axis_gate
        return axis_gate


def validate_nexxus_command(data_packet):
    """True only for a packet signed with the governance secret, fresh, and never seen before. The axis gate makes the decision and logs it."""
    sec = _secret()
    if not sec or not isinstance(data_packet, dict):
        return False
    try:
        gate = _axis_gate()
    except Exception as e:                                       # fail closed: a guardian that cannot load lets nothing through
        print("SECURITY ALERT: the axis gate is unavailable (%s); command refused." % type(e).__name__)
        return False
    src = data_packet.get("engine") or data_packet.get("kind") or "mesh"
    v = gate.check_packet(data_packet, sec, {"NEXXUS_EXECUTOR"}, source=src, channel="MESH", max_age=MAX_AGE_SECONDS)
    if not v.allow and v.status in ("HANDSHAKE_FAILED", "BLOCKED"):
        print("SECURITY ALERT: Unauthorized command attempt rejected (%s)." % v.reason)
    return v.allow


def validate_engine_packet(data_packet):
    """For packets an ENGINE sends to the hub (heartbeat, message, peers). Accepts
      * a packet signed with the engine's own derived key (origin "ENGINE:<name>"): the name inside must match the origin, and the key is derived from that name, so engine A cannot speak as B;
      * a legacy packet signed with the shared key (origin NEXXUS_EXECUTOR), unless NEXXUS_REQUIRE_ENGINE_KEYS=1, which refuses it (switch that on once every engine has been restarted).
    Both are fresh, single-use, and must not predate this process (BOOT_TS): the single-use cache is in memory, so after a restart a captured packet could otherwise be replayed once more."""
    if not _secret() or not isinstance(data_packet, dict):
        return False
    try:
        gate = _axis_gate()
    except Exception as e:                                       # fail closed
        print("SECURITY ALERT: the axis gate is unavailable (%s); command refused." % type(e).__name__)
        return False
    origin, engine = data_packet.get("origin"), data_packet.get("engine")
    floor = BOOT_TS - 2.0
    if isinstance(origin, str) and origin.startswith(ENGINE_ORIGIN):
        key = engine_key(engine)
        if key is None or origin != ENGINE_ORIGIN + str(engine):
            print("SECURITY ALERT: Unauthorized command attempt rejected (origin_does_not_match_engine).")
            return False
        v = gate.check_packet(data_packet, key, {origin}, source=engine, channel="MESH", max_age=MAX_AGE_SECONDS, min_ts=floor)
    else:
        if os.environ.get("NEXXUS_REQUIRE_ENGINE_KEYS") == "1":
            print("SECURITY ALERT: Unauthorized command attempt rejected (shared_key_not_accepted_here).")
            return False
        v = gate.check_packet(data_packet, _secret(), {"NEXXUS_EXECUTOR"}, source=data_packet.get("engine") or data_packet.get("kind") or "mesh",
                              channel="MESH", max_age=MAX_AGE_SECONDS, min_ts=floor)
    if not v.allow and v.status in ("HANDSHAKE_FAILED", "BLOCKED"):
        print("SECURITY ALERT: Unauthorized command attempt rejected (%s)." % v.reason)
    return v.allow


# ---------------------------------------------------------------------------
# Engine auto-registration (the "connector")
# ---------------------------------------------------------------------------
# Two ways an engine joins the mesh (the SERVER never scans silo folders;
# the bridge publishes mesh_roster.json via mesh_roster.publish_roster), both recorded in mesh_registry.json:
#   1. Drop-in discovery: put the engine's .py file in the project folder or in
#      a folder listed in NEXXUS_ENGINE_PATH. discover_and_register() finds any
#      file matching one of the 21 known engine names and registers it - no
#      signature needed because the file is on YOUR disk in a folder YOU chose.
#   2. Self-registration: a running engine calls register_engine(packet) with a
#      packet made by sign_command(); unsigned or tampered packets are refused.
import threading
from pathlib import Path

REGISTRY_FILE = Path(__file__).resolve().parent / "mesh_registry.json"
_reg_lock = threading.Lock()


def _load():
    try:
        return json.loads(REGISTRY_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save(reg):
    tmp = REGISTRY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, indent=2))
    os.replace(tmp, REGISTRY_FILE)


def registered_engines():
    with _reg_lock:
        return _load()


def register_engine(packet):
    """Signed self-registration. Returns (ok, message)."""
    import mesh_bridge as axis_bridge
    if not validate_nexxus_command(packet):
        return False, "rejected: bad or missing signature"
    name = packet.get("engine")
    if name not in axis_bridge.ENGINES:
        return False, f"rejected: {name!r} is not one of the 21 known engines"
    with _reg_lock:
        reg = _load()
        reg[name] = {"via": "signed", "module": packet.get("module"), "registered_at": time.time()}
        _save(reg)
    return True, f"{name} registered"


def discover_and_register():
    """Sync the registry with the bridge-published roster (no silo scanning here)."""
    import mesh_bridge as axis_bridge
    roster = axis_bridge.load_roster()
    with _reg_lock:
        reg = _load()
        for name in axis_bridge.ENGINES:
            path = roster.get(name)
            if path and Path(path).is_file():
                if name not in reg or reg[name].get("module") != path:
                    reg[name] = {"via": "bridge_roster", "module": path, "registered_at": time.time()}
            elif reg.get(name, {}).get("via") == "bridge_roster":
                del reg[name]
        _save(reg)
        return reg