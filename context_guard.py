"""context_guard.py - NEXXUS watches how heavy the main chat has become and hands the operator a clean way into a fresh window.

Every turn of the main chat is recorded here (user text + NEXXUS reply). Weight is estimated as characters / 4 (a stdlib-only approximation of tokens, good enough to trip a threshold, not
a billing figure). When the estimate crosses WARN_RATIO of the budget the guard, once:
  1. saves a handoff to nexxus_data/archives/handoffs/ (full transcript as JSON + the continuation prompt as Markdown), and only then
  2. returns the operator notice. If the save fails, the notice says so instead of claiming everything is locked down.
The continuation prompt is built deterministically from the recorded transcript (no model call), so it still works when the model is the thing that is overloaded.

Tunables (environment): NEXXUS_CONTEXT_BUDGET_TOKENS (default 6000, sized for the small local model), NEXXUS_CONTEXT_WARN_RATIO (default 0.8), NEXXUS_CONTEXT_MAX_TURNS (default 40).
"""
import json
import os
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "nexxus_data", "state")
STATE_PATH = os.path.join(STATE_DIR, "context_guard.json")
TRANSCRIPT_PATH = os.path.join(STATE_DIR, "context_transcript.jsonl")
HANDOFF_DIR = os.path.join(HERE, "nexxus_data", "archives", "handoffs")

NOTICE = ("This chat is getting too full and overloaded. Time to spin up a new window—auto-save has already locked everything down. "
          "Let's move forward cleanly.")
NOTICE_SAVE_FAILED = ("This chat is getting too full and overloaded. Time to spin up a new window. WARNING: auto-save could not write the handoff file, "
                      "so copy the continuation prompt below before you leave. Let's move forward cleanly.")

KEEP_TURNS = 6          # recent turns quoted verbatim in the continuation prompt
EARLIER_ASKS = 12       # earlier operator requests listed as bullets
CLIP = 400              # characters kept per quoted message
_LOCK = threading.RLock()


def _env_num(name, default, cast):
    try:
        return cast(os.environ.get(name, default))
    except (TypeError, ValueError):
        return cast(default)


def budget():
    return max(500, _env_num("NEXXUS_CONTEXT_BUDGET_TOKENS", 6000, int))


def warn_ratio():
    return min(1.0, max(0.2, _env_num("NEXXUS_CONTEXT_WARN_RATIO", 0.8, float)))


def max_turns():
    return max(4, _env_num("NEXXUS_CONTEXT_MAX_TURNS", 40, int))


def estimate_tokens(text):
    return (len(str(text)) + 3) // 4


def _clip(text, n=CLIP):
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _read_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            s = json.load(f)
        if isinstance(s, dict):
            return s
    except (OSError, ValueError):
        pass
    return {"session_started": time.time(), "turns": 0, "tokens": 0, "notified": False, "handoff": None}


def _write_state(s):
    os.makedirs(STATE_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(s, f)
    os.replace(tmp, STATE_PATH)


def _read_transcript():
    out = []
    try:
        with open(TRANSCRIPT_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def continuation_prompt(turns=None):
    """A paste-ready prompt that lets a fresh window pick up where this one stopped."""
    turns = _read_transcript() if turns is None else turns
    if not turns:
        return "Starting fresh: no earlier conversation was recorded."
    recent = turns[-KEEP_TURNS:]
    earlier = turns[:-KEEP_TURNS]
    asks = [t["user"] for t in earlier if t.get("user")][-EARLIER_ASKS:]
    lines = ["Continuing a previous NEXXUS session that outgrew its window. Treat the notes below as established context, do not re-ask what is already answered, "
             "and pick up from the last exchange.", ""]
    if asks:
        lines.append("Earlier in the session the operator asked about:")
        lines += ["- " + _clip(a, 160) for a in asks]
        lines.append("")
    lines.append("Most recent exchanges (oldest first):")
    for t in recent:
        lines.append("Operator: " + _clip(t.get("user", "")))
        lines.append("NEXXUS: " + _clip(t.get("reply", "")))
    lines += ["", "Where we left off: " + _clip(recent[-1].get("user", ""), 200) + "  (answered above)", "Carry on from here; ask me what is next."]
    return "\n".join(lines)


def _save_handoff(turns, tokens):
    """-> path of the saved handoff, or None if it could not be written."""
    try:
        os.makedirs(HANDOFF_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = os.path.join(HANDOFF_DIR, "handoff_" + stamp)
        prompt = continuation_prompt(turns)
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump({"saved": time.time(), "est_tokens": tokens, "turns": turns}, f, indent=2)
        with open(base + ".md", "w", encoding="utf-8") as f:
            f.write("# NEXXUS continuation prompt\n\nPaste everything below the line into the new window.\n\n---\n\n" + prompt + "\n")
        return base + ".md"
    except OSError:
        return None


def status():
    with _LOCK:
        s = _read_state()
    b = budget()
    return {"turns": s["turns"], "est_tokens": s["tokens"], "budget_tokens": b, "ratio": round(s["tokens"] / b, 3),
            "level": "full" if (s["tokens"] >= b or s["turns"] >= max_turns()) else ("warn" if s["notified"] else "ok"),
            "notified": s["notified"], "handoff": s.get("handoff")}


def record_turn(user_text, reply_text):
    """Record one exchange. -> None normally; a dict {"notice", "continuation_prompt", "handoff", "saved"} on the turn that crosses the threshold."""
    with _LOCK:
        s = _read_state()
        turn = {"ts": time.time(), "user": str(user_text), "reply": str(reply_text)}
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(TRANSCRIPT_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(turn) + "\n")
        except OSError:
            pass
        s["turns"] += 1
        s["tokens"] += estimate_tokens(user_text) + estimate_tokens(reply_text)
        crossed = (not s["notified"]) and (s["tokens"] >= budget() * warn_ratio() or s["turns"] >= max_turns())
        result = None
        if crossed:
            turns = _read_transcript()
            path = _save_handoff(turns, s["tokens"])
            s["notified"], s["handoff"] = True, path
            result = {"notice": NOTICE if path else NOTICE_SAVE_FAILED, "continuation_prompt": continuation_prompt(turns), "handoff": path, "saved": bool(path)}
        try:
            _write_state(s)
        except OSError:
            pass
        return result


def start_new_window():
    """The operator opened a fresh window: archive the old transcript and zero the counters."""
    with _LOCK:
        try:
            if os.path.exists(TRANSCRIPT_PATH):
                os.makedirs(HANDOFF_DIR, exist_ok=True)
                os.replace(TRANSCRIPT_PATH, os.path.join(HANDOFF_DIR, "transcript_" + time.strftime("%Y%m%d_%H%M%S") + ".jsonl"))
        except OSError:
            pass
        try:
            _write_state({"session_started": time.time(), "turns": 0, "tokens": 0, "notified": False, "handoff": None})
        except OSError:
            pass
        return status()
