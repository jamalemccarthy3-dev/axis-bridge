# build_governor.py
import ast
import os

MAX_DATA_BYTES = 100_000
FORBIDDEN_KEYS = ("password", "passwd", "secret", "api_key", "apikey", "token", "private_key")


class BuildGovernor:
    """Decides whether a build command may run. The rules come from the config file (a Python dict literal): `allowed_operations` (the only commands that may run),
    `restricted_commands` (refused even if someone adds them to the allowed list), and `governance_settings.enforce_strict_mode` (data must be a dict with no secret-looking keys
    and no path tricks; without strict mode only the command lists apply). A missing or unreadable config means NOTHING is allowed (a governor with no rules does not allow everything).
    The reason for the last decision is in self.last_reason."""

    def __init__(self, config_path):
        self.config_path = config_path
        self.config = None
        self.last_reason = None
        try:
            with open(config_path, encoding="utf-8") as f:
                self.config = ast.literal_eval(f.read().strip())
        except (OSError, ValueError, SyntaxError):
            self.config = None

    def validate_command(self, command, data=None):
        """True to allow, False to block (reason in self.last_reason)."""
        def deny(why):
            self.last_reason = why
            return False
        if self.config is None:
            return deny("no readable governance config at %s: nothing is allowed without rules" % self.config_path)
        if not isinstance(command, str) or not command.strip():
            return deny("a command is a non-empty string")
        if command in self.config.get("restricted_commands", []):
            return deny("%r is a restricted command" % command)
        if command not in self.config.get("allowed_operations", []):
            return deny("%r is not an allowed operation (%s)" % (command, ", ".join(self.config.get("allowed_operations", []))))
        if self.config.get("governance_settings", {}).get("enforce_strict_mode", True):
            if not isinstance(data, dict):
                return deny("strict mode: data must be a dict, got %s" % type(data).__name__)
            if len(repr(data)) > MAX_DATA_BYTES:
                return deny("strict mode: data is over %d characters" % MAX_DATA_BYTES)
            bad = self._scan(data)
            if bad:
                return deny("strict mode: %s" % bad)
        self.last_reason = "allowed"
        return True

    def _scan(self, obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in FORBIDDEN_KEYS:
                    return "secret-looking key %s%s" % (path, k)
                r = self._scan(v, "%s%s." % (path, k))
                if r:
                    return r
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                r = self._scan(v, "%s[%d]." % (path, i))
                if r:
                    return r
        elif isinstance(obj, str) and (".." + os.sep in obj or "../" in obj or "..\\" in obj):
            return "path traversal in a value (%s)" % path.rstrip(".")
        return None
