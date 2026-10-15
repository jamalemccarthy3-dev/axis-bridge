"""tool_request.py - the governor's front door. An agent that needs a governor tool (the audit trail, the kill switch, the gatekeeper ...) asks here:

    from tool_request import run_tool            # (put the engine root on sys.path first)
    run_tool("audit_trail_logger", "log_event", "analyst", "report sent", "ok")

Only the ten governor tools can be asked for, and only their public methods. Every request is written to the audit trail, and while the kill switch is on
every request is refused except the kill switch's own (so it can be inspected and cleared)."""
import ast
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if _ROOT not in sys.path:
    sys.path.append(_ROOT)
import sandm_store as store  # noqa: E402

TOOLS = ["audit_trail_logger", "deployment_gatekeeper", "emergency_kill_switch", "fusion_linker", "heartbeat_monitor", "instruction_dispacter",
         "policy_validator", "protocol_enforcer", "registry_manager", "resource_balancer"]
_HERE = os.path.dirname(os.path.abspath(__file__))


def _first_class(path):
    with open(path, encoding="utf-8") as f:
        return next(n.name for n in ast.parse(f.read()).body if isinstance(n, ast.ClassDef))


def _public_methods(path, cls):
    with open(path, encoding="utf-8") as f:
        node = next(n for n in ast.parse(f.read()).body if isinstance(n, ast.ClassDef) and n.name == cls)
    return {m.name for m in node.body if isinstance(m, ast.FunctionDef) and not m.name.startswith("_")}


def run_tool(tool, method, *args, **kwargs):
    """Runs tool.method(*args, **kwargs) on a fresh engine built with the tool's own config. -> whatever the method returns.
    Raises ValueError for an unknown tool or method, PermissionError while the kill switch is on."""
    if tool not in TOOLS:
        raise ValueError("unknown governor tool %r (choose from %s)" % (tool, TOOLS))
    lib = os.path.join("src", "governor", "lib", tool + "_tool.py")
    cfg = os.path.join("src", "governor", "config", tool + "_config.py")
    cls = _first_class(os.path.join(_ROOT, lib))
    if method not in _public_methods(os.path.join(_ROOT, lib), cls):
        raise ValueError("%s has no public method %r" % (tool, method))
    if store.halted() and tool != "emergency_kill_switch":
        raise PermissionError("kill switch is on: governor tools are refused until it is cleared")
    config = store.load_class(cfg.replace("\\", "/"), _first_class(os.path.join(_ROOT, cfg)))()
    engine = store.load_engine(lib.replace("\\", "/"), cls, config)
    result = getattr(engine, method)(*args, **kwargs)
    if tool != "audit_trail_logger":
        store.audit("tool_request", "%s.%s" % (tool, method), "ran")
    return result
