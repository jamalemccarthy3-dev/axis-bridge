# Final Copy: The Consultant Network Config
# Policy + the list of consultants. EVERYTHING ships disabled: nothing leaves this PC until the owner switches a
# consultant on in consult_config.json. A bad or missing file means "no consultants" (it fails closed).
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "consult_config.json"
STATE_FILE = ROOT / "consult_state.json"       # today's call / token counters + circuit breakers (no content)
LOG_FILE = ROOT / "consult_private.jsonl"      # the owner's private record of every consult (never shown in the UI)

KINDS = ("ollama", "openai_compat")            # both are free, self-hosted servers on YOUR network (Ollama / LM Studio / llama.cpp server / vLLM)
TASKS = ("fix", "repair", "plan")
KEY_ENV_PREFIX = "NEXXUS_CONSULT_"             # an optional LAN-server key can only come from a variable with this prefix (never the governance secret / admin token)
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
_ENV = re.compile(r"^NEXXUS_CONSULT_[A-Z0-9_]{1,50}$")

DEFAULT_POLICY = {"max_calls_per_day": 10, "max_output_tokens": 4000, "max_input_chars": 24000,
                  "timeout_s": 120, "breaker_failures": 3, "breaker_cooldown_s": 900}
_LIMITS = {"max_calls_per_day": (0, 200), "max_output_tokens": (100, 8000), "max_input_chars": (2000, 60000),
           "timeout_s": (10, 600), "breaker_failures": (1, 20), "breaker_cooldown_s": (60, 86400)}


class ConsultConfig:
    def __init__(self, path=None):
        self.path = Path(path) if path else CONFIG_FILE
        self.problems = []
        self._raw = self._read()

    def _read(self):
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            self.problems.append("config unreadable (%s) - consultants are OFF" % type(e).__name__)
            return {}

    def master_enabled(self):
        return self._raw.get("enabled") is True

    def get_policy(self):
        p = dict(DEFAULT_POLICY)
        for k, (lo, hi) in _LIMITS.items():
            v = (self._raw.get("policy") or {}).get(k)
            if isinstance(v, int) and not isinstance(v, bool):
                p[k] = max(lo, min(hi, v))
        return p

    def get_consultants(self):
        """Validated consultants. Anything malformed is dropped (and noted in .problems), never guessed at."""
        out, seen = [], set()
        for c in (self._raw.get("consultants") or []):
            if not isinstance(c, dict):
                continue
            cid, kind = str(c.get("id") or ""), c.get("kind")
            if not _ID.match(cid) or cid in seen:
                self.problems.append("consultant %r dropped: bad or duplicate id" % cid); continue
            if kind not in KINDS:
                self.problems.append("consultant %r dropped: unknown kind %r" % (cid, kind)); continue
            key_env = c.get("api_key_env")
            if key_env is not None and not _ENV.match(str(key_env)):
                self.problems.append("consultant %r dropped: api_key_env must look like %sSOMETHING" % (cid, KEY_ENV_PREFIX)); continue
            seen.add(cid)
            out.append({
                "id": cid, "kind": kind, "enabled": c.get("enabled") is True,
                "host": str(c.get("host") or ""), "base_url": str(c.get("base_url") or ""), "model": str(c.get("model") or ""),
                "api_key_env": key_env, "for": [t for t in (c.get("for") or list(TASKS)) if t in TASKS],
            })
        return out
