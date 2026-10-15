#!/usr/bin/env python3
"""
python_server.py - NEXXUS Infrastructure & Routing Bridge
Optimized: Removed self-referential HTTP loopback deadlocks,
cleaned non-breaking spaces, and structured Flask globally.
"""

import os
import json
import urllib.request
import re
import sys
import time
import uuid
import threading
import sqlite3
import requests
import socket
from pathlib import Path

def _mesh_manifest(deep=False):
    reg = _gov.discover_and_register()  # auto-connect any engine file that has appeared
    m = _axis_bridge.manifest(deep)
    for n in m["nodes"]:
        n["registered"] = n["engine"] in reg
    m["engines_registered"] = sum(1 for n in m["nodes"] if n["registered"])
    return m
from flask import Flask, request, jsonify, make_response, send_from_directory, send_file
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

BRIDGE_PORT = int(os.environ.get("NEXXUS_PORT") or 8000)

# ═══════════════════════════════════════════════════════
# AUTO-FIND NEXXUS BRAIN
# ═══════════════════════════════════════════════════════

_POSSIBLE_NEXUS_PATHS = [
    os.path.join("axis-ui-interface", "project-X", "silo_vault", "nexus"),
    os.path.join("axis-ui-interface", "project-X", "silo_vault", "nexxus"),
    os.path.join("axis-ui-interface", "project-X", "silo_vault", "Nexus"),
    os.path.join("..", "axis-ui-interface", "project-X", "silo_vault", "nexus"),
]

NEXUS_DIR = None
for p in _POSSIBLE_NEXUS_PATHS:
    full = os.path.abspath(os.path.join(os.path.dirname(__file__), p))
    if os.path.exists(full):
        NEXUS_DIR = full
        break

NEXUS_AVAILABLE = False
if NEXUS_DIR and NEXUS_DIR not in sys.path:
    sys.path.insert(0, NEXUS_DIR)

# These helper modules may sit next to this file OR in the nexxus folder (which is only added to the
# import path just above), so they must be imported AFTER that line, never before it.
from safe_submit import safe_submit
import mesh_bridge as _axis_bridge
import nexxus_governance as _gov
try:
    import category_probation as _probation
    import recon_engine as _recon
    import peer_review as _peer_review
    import context_cache as _context_cache_mod
except ImportError as _e:   # optional: the rest of the server runs without them
    _probation = _recon = _peer_review = _context_cache_mod = None
    print(f"[BRIDGE WARNING] recon/probation modules not found: {_e}")
try:
    import mode_policy as _modes
    _mode_state = _modes.ModeState()          # always boots in Conversation (Neutral)
    try:                                      # swap the local model when the mode changes (see llm_router.py)
        import llm_router as _llm_router
        _llm_router.set_mode(_mode_state.mode)
        _mode_state.add_listener(_llm_router.on_mode_change)
    except ImportError as _e:
        _llm_router = None
        print(f"[BRIDGE WARNING] llm_router.py not found - no model switching on mode change: {_e}")
except ImportError as _e:
    _modes = _mode_state = None
    print(f"[BRIDGE WARNING] mode_policy.py not found - operating modes are NOT enforced: {_e}")
try:
    import creation_mode as _creation          # Creation mode: visuals made on the fly (see creation_mode.py)
except ImportError as _e:
    _creation = None
    print(f"[BRIDGE WARNING] creation_mode.py not found - Creation mode will not make anything: {_e}")
try:
    import tunnel_control as _tunnel_mod
    _tunnel = _tunnel_mod.TunnelController(port=int(os.environ.get("NEXXUS_PORT") or 8000))
except ImportError as _e:
    _tunnel = None
    print(f"[BRIDGE WARNING] tunnel_control.py not found - tunnel controls are unavailable: {_e}")
try:
    import bluetooth_control as _bt_mod
    _bt = _bt_mod.BluetoothManager()
except ImportError as _e:
    _bt = None
    print(f"[BRIDGE WARNING] bluetooth_control.py not found - Bluetooth controls are unavailable: {_e}")
try:
    import dashboard_cycle as _dc
    _dash = _dc.DashboardStore()
except ImportError as _e:
    _dc = _dash = None
    print(f"[BRIDGE WARNING] dashboard_cycle.py not found - the dashboard build cycle is unavailable: {_e}")
try:
    import mesh_diagnostic as _mesh_diag
except ImportError as _e:
    _mesh_diag = None
    print(f"[BRIDGE WARNING] mesh_diagnostic.py not found - the mesh verification report is unavailable: {_e}")

try:
    import nexxus_talks as nexus_module
    NEXUS_AVAILABLE = True
    print("[BRIDGE] NEXXUS brain imported successfully.")
except Exception as e:
    print(f"[BRIDGE WARNING] Could not import nexxus_talks: {e}")
    print("[BRIDGE] Will fallback to direct Ollama.")

# Thread pool for AI calls — prevents Flask from hanging
_AI_EXECUTOR = ThreadPoolExecutor(max_workers=4)

latest_chat_message = {"sender": "NEXXUS", "text": "Infrastructure bridge online."}

# ═══════════════════════════════════════════════════════
# FIXED: Use absolute path based on server file location
# ═══════════════════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Your exact path structure
HTML_FOLDER = os.path.join(BASE_DIR, "axis-ui-interface", "project-X", "silo_vault", "render")

# Check if the folder exists, if not try alternatives
if not os.path.exists(HTML_FOLDER):
    # Try to find the render folder anywhere in the project
    for root, dirs, files in os.walk(BASE_DIR):
        if "render" in dirs:
            HTML_FOLDER = os.path.join(root, "render")
            break

# Find the HTML file (case-insensitive)
HTML_FILE = None
if os.path.exists(HTML_FOLDER):
    for filename in os.listdir(HTML_FOLDER):
        if filename.lower().endswith('.html'):
            HTML_FILE = filename
            break

if HTML_FILE is None:
    HTML_FILE = "babylon_preview.html"  # Default fallback

print(f"[BRIDGE] Serving HTML from: {os.path.join(HTML_FOLDER, HTML_FILE)}")

app = Flask(__name__)


# Every JSON reply is made strictly valid before it leaves: Python writes NaN / Infinity for a float that came out that way (a latency, a score, a render time), and the browser's
# response.json() rejects those words, which broke whatever the page was drawing (images and models included). They become null instead.
def _json_finite(o, _depth=0):
    if _depth > 60:
        return None
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if isinstance(o, dict):
        return {k: _json_finite(v, _depth + 1) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_finite(v, _depth + 1) for v in o]
    return o


try:
    from flask.json.provider import DefaultJSONProvider as _DefaultJSONProvider

    class _StrictJSONProvider(_DefaultJSONProvider):
        def dumps(self, obj, **kwargs):
            return super().dumps(_json_finite(obj), **kwargs)

    app.json = _StrictJSONProvider(app)
except Exception as _e_json:                         # an older Flask without the provider API keeps its default behavior
    print("[BRIDGE WARNING] strict JSON provider not installed: %s" % _e_json)

print("=" * 50)
print("NEXXUS INFRASTRUCTURE BRIDGE INITIALIZING...")
print("=" * 50)

def diagnose_port(host, port):
    print(f"[*] Diagnosing endpoint {host}:{port}...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        try:
            result = s.connect_ex((host, port))
            if result == 0:
                print(f"[X] Port {port} is ALREADY IN USE!")
            else:
                print(f"[OK] Port {port} is free.")
        except socket.error as e:
            print(f"[?] Could not diagnose: {e}")

def execute_axis_primary(query):
    return {
        "status": "success",
        "pipeline": "primary",
        "data": f"AXIS Deep Index: {query}"
    }

def execute_axis_secondary(query):
    return {
        "status": "success",
        "pipeline": "secondary",
        "data": f"AXIS Quick Index: {query}"
    }

def route_axis_search(query):
    """
    Fixed: Direct function invocation instead of self-referential HTTP loopbacks
    which cause thread pool deadlocks in Flask.
    """
    try:
        results = {
            "primary": execute_axis_primary(query),
            "secondary": execute_axis_secondary(query)
        }
        return results
    except Exception as e:
        return {"error": str(e)}

def _invoke_nexxus_pipeline(user_input):
    """
    Runs the full NEXXUS pipeline exactly once and returns (reply_text, question)
    where question is the structured clarifying-question dict (question_id,
    prompt, options, pending_action, pending_context) whenever
    nexxus_talks.generate_response() came back with one pending, else None.

    This is the single place that actually calls the pipeline. route_bridge_request()
    below wraps it to keep its existing string-only return contract (micro_dispatch's
    plain_speak stage calls it expecting plain text), while the /bridge route calls
    this directly so it can also forward "question" to the dashboard for rendering
    as clickable clarifying-question options - without that, a question dict would
    just get flattened into "technical_view" string text and the frontend would have
    no structured field to build option buttons from.
    """
    if NEXUS_AVAILABLE:
        try:
            if hasattr(nexus_module, "bridge") and hasattr(nexus_module.bridge, "generate_response"):
                gen_func = nexus_module.bridge.generate_response
            elif hasattr(nexus_module, "generate_response"):
                gen_func = nexus_module.generate_response
            else:
                gen_func = lambda q: {"technical_view": f"NEXXUS module loaded, but no generate_response found. Input: {q}"}

            # Previously 60s here while query_local_llama()'s own HTTP timeout is
            # 180s (nexxus_talks.py's own error message even says "first inference
            # is always slow" and to wait 30s+) - the outer future was killing the
            # request before the inner Ollama call ever got a chance to finish or
            # legitimately time out on its own. Give it real headroom above 180s.
            future = safe_submit(_AI_EXECUTOR, gen_func, str(user_input).strip())
            response_package = future.result(timeout=185)

            extras = {}
            if isinstance(response_package, dict):
                # Structured side-channels the dashboard renders specially:
                # "question" (clarifying options) and "job" (a build that was
                # started in the background and is being tracked live).
                extras = {k: response_package[k] for k in ("question", "job") if response_package.get(k)}
                reply = (
                    response_package.get("technical_view") or
                    response_package.get("intuitive_view") or
                    response_package.get("message") or
                    str(response_package)
                )
            else:
                reply = str(response_package)
            return reply.strip(), extras

        except FutureTimeoutError:
            return (
                "NEXXUS pipeline timed out after 185 seconds.\n\n"
                "This usually means Ollama is still loading the model into RAM, or the "
                "model itself is slow on this hardware.\n"
                "Wait a bit and try again - first inference after a cold start is always slow."
            ), {}
        except Exception as e:
            print("[NEXXUS] pipeline error (%s): %s" % (type(e).__name__, e))          # the detail stays in the server window, not in the chat
            return "NEXXUS hit an error while answering. The details are in the server window; everything else is still running.", {}

    # Fallback to direct Ollama (used when nexus_module itself fails to import).
    # Was 30s - too short for anything but the smallest completions and prone to
    # exactly the "Read timed out" drops described; raised to 120s. Still safely
    # under the 185s outer executor timeout above.
    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={"model": "llama3.2", "prompt": user_input, "stream": False},
            timeout=120
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip(), {}
        return f"Ollama error: {response.status_code}", {}
    except requests.exceptions.ConnectionError:
        return ("NEXXUS can't reach its local language model right now (Ollama is not answering on port 11434). The server, the dashboard and the engines are still running; "
                "only chat replies need the model. Start Ollama (the tray app, or run: ollama serve) and ask again."), {}
    except Exception as e:
        print("[NEXXUS] direct Ollama call failed (%s): %s" % (type(e).__name__, e))
        return "The local model call failed unexpectedly. The details are in the server window; everything else is still running.", {}


def route_bridge_request(user_input):
    """
    Calls the FULL NEXXUS pipeline and returns just the reply text - kept as
    its own function (rather than inlining _invoke_nexxus_pipeline everywhere)
    because micro_dispatch's plain_speak stage already depends on this
    returning a plain string, not a tuple.
    """
    reply, _extras = _invoke_nexxus_pipeline(user_input)
    return reply

# ═══════════════════════════════════════════════════════
# FLASK ROUTES
# ═══════════════════════════════════════════════════════

@app.route("/")
def serve_dashboard():
    return send_from_directory(HTML_FOLDER, HTML_FILE)

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(HTML_FOLDER, filename)

@app.route("/status", methods=["GET", "POST", "OPTIONS"])
def status():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST")
        return response
    response = make_response(jsonify({
        "status": "success",
        "message": "NEXXUS bridge online. All engines active.",
        "brain_loaded": NEXUS_AVAILABLE,
        "audio_muted": False
    }))
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response

# ═══════════════════════════════════════════════════════
# OPERATING MODES + MESH REPORT HOOKS (chat paths)
# The server owns the current mode (mode_policy.ModeState). Both chat routes ask it before doing anything:
# in Conversation mode a build/code order is halted with a prompt to switch; in Corporate mode the build is
# routed to the corporate vault lane; a "corporate/sellable" order made in a non-corporate mode is halted.
# ═══════════════════════════════════════════════════════
_MESH_REPORT_ASK = re.compile(r"\b(mesh|engines?)\b.*\b(diagnostic|verification|verify|report|status check|health check|test)\b|"
                              r"\b(diagnostic|verify|verification|test)\b.*\b(mesh|engines)\b", re.I)

def _mode_gate(text):
    """None to carry on, else the halt payload (already includes message + options)."""
    if _mode_state is None:
        return None
    if re.match(r"^\s*(?:please\s+)?(?:(?:find|search for|look for|scout|get me|(?:i|we)\s+need)\s+.*\b(?:tool|skill|script|library|package|repo|repository)s?\b|ingest\s+\S+|stage\s+\S+|fetch tool\s+\S+|(?:list|show)\s+.*tools?\b|run tool\s+\w+)", text or "", re.I):
        return None                          # tool scouting only reads from GitHub and stages; nothing is built or run, so it works in every mode
    return _mode_state.gate(text)

def _mode_pipeline_text(text):
    """Corporate mode: steer the existing vault-lane rule (it reads 'corporate'/'sellable' in the prompt)."""
    if _mode_state is not None and _mode_state.mode == "corporate" and _modes.looks_like_build_request(text) \
            and not re.search(r"\b(corporate|sellable)\b", text, re.I):
        return text + " (corporate sellable build)"
    return text

def _mesh_report_reply(text):
    """A chat request for the mesh report gets the real static report (never runs an engine from chat)."""
    if _mesh_diag is None or not _MESH_REPORT_ASK.search(text or ""):
        return None
    if str(text or "").lstrip().startswith("Build an engine from this approved sketch blueprint"):
        return None                          # a Sketch Mode hand-off order: its thesis may say "engine" and "test", but it is a build order, not a request for the mesh report
    try:
        rep = _mesh_diag.run_diagnostic(probe=False)
    except Exception as e:
        return "The mesh report could not be built: %s: %s" % (type(e).__name__, e)
    return _mesh_diag.render_text(rep) + "\n\nThis chat report does not start any engine. Use the Mesh Verification panel on the Engine Diagnostic face for the full probe."


_creation_last = {"id": None, "at": 0.0}      # the most recent creation (a bare "make the rays longer" refines this one)
_CREATION_LAST_TTL = 2 * 3600

def _start_refine_job(parent_id=None, code=None, instruction="", title=None, prompt=None):
    """Start a background 'creation_refine' job. Returns the job dict, or raises (caller reports it)."""
    mgr = _job_manager.get_default_manager() if _job_manager is not None else None
    if mgr is None:
        raise RuntimeError("the job system is not available")
    if "creation_refine" not in getattr(mgr, "_runners", {}):
        mgr.register_runner("creation_refine", _creation.refine_runner)
    return mgr.submit("creation_refine", {"parent_id": parent_id, "code": code, "instruction": instruction, "title": title, "prompt": prompt},
                      "refine: " + instruction.splitlines()[0][:70])

def _creation_chat_reply(text, active_id=None):
    """Creation mode only. A visual request is either answered with clarifying questions (too vague), started
    as a background 'creation_render' job, or - if it is a change request about something already made - started as a
    'creation_refine' job on that creation. The result appears in the artifact panel.
    -> (reply, extras) or None to fall through to ordinary chat."""
    if _creation is None or _mode_state is None or _mode_state.mode != "creation":
        return None
    last = _creation_last["id"] if (_creation_last["id"] and time.time() - _creation_last["at"] < _CREATION_LAST_TTL) else None
    if last and _creations is not None and _creations.get(last) is None:
        last = None                                  # it was deleted
    if active_id and (_creations is None or _creations.get(active_id) is None):
        active_id = None
    d = _creation.handle(text, active_id=active_id, last_id=last)
    if d is None:
        return None
    if d["kind"] == "say":
        return d["reply"], {}
    if d["kind"] == "ask":
        return d["reply"], {"question": d["question"]}
    if d["kind"] == "refine":
        try:
            job = _start_refine_job(parent_id=d["parent_id"], instruction=d["instruction"])
        except Exception as e:
            return "Not started: %s: %s" % (type(e).__name__, e), {}
        pm = _creations.get(d["parent_id"]) if _creations is not None else None
        try:
            _next = _creation._next_title((pm or {}).get("title"), int((pm or {}).get("version", 1)))
        except Exception:                                   # an older creation whose stored title is a stand-in: the job names it from its own request, nothing is invented here
            _next = None
        return (d["reply"].replace("{job}", job["job_id"]),
                {"creation_job": {"job_id": job["job_id"], "title": _next,
                                  "prompt": d["instruction"], "parent_id": d["parent_id"]}})
    mgr = _job_manager.get_default_manager() if _job_manager is not None else None
    if mgr is None:
        return "The job system is not available, so I cannot make that right now.", {}
    try:
        if "creation_render" not in getattr(mgr, "_runners", {}):
            mgr.register_runner("creation_render", _creation.runner)
        job = mgr.submit("creation_render", {"prompt": d["prompt"]}, "create: " + d["prompt"].splitlines()[0][:70])
    except Exception as e:
        return "Not started: %s: %s" % (type(e).__name__, e), {}
    return (d["reply"].replace("{job}", job["job_id"]),
            {"creation_job": {"job_id": job["job_id"], "title": _creation._title(d["prompt"]), "prompt": d["prompt"]}})


_DASH_CHAT_ASK = re.compile(r"\b(dashboard|panel|calculator|viewport|3d|game|environment|front.?face|silo|wedge|hub|app|application|tool|widget)\b", re.I)

def _dashboard_chat_reply(text):
    """Dashboard Hub mode only: a build order for a dashboard / component is handled by the dashboard cycle
    (isolated hub, default static face, both creators, nested silo, wiring) and answered with the code blocks.
    -> (reply, extras) or None to fall through to the normal pipeline."""
    if _dash is None or _mode_state is None or _mode_state.mode != "dashboard_hub":
        return None
    if not (_modes.looks_like_build_request(text) and _DASH_CHAT_ASK.search(text or "")):
        return None
    try:
        res = _dc.build_dashboard(_dash, text, engine_states=_dash_engine_states(), utilities=_dash_utilities(), base=_dash_base())
    except Exception as e:
        return ("The dashboard could not be built: %s: %s" % (type(e).__name__, e), {})
    hub, pkg = res["hub"], res["package"]
    lines = [res["result"]["message"], "Dashboard: %s (id %s). Nested silos: %d." % (hub["title"], hub["id"], len(hub["silos"]))]
    w = hub.get("wired_engines") or []
    if w:
        lines.append("Backend engines wired: " + ", ".join("%s (%s)" % (e["engine"], e["state"]) for e in w) + ".")
    if hub.get("to_wire"):
        lines.append("Still to plug in: " + "; ".join("%s - %s" % (x["engine"], x["fix"]) for x in hub["to_wire"]) + ".")
    elif not w:
        lines.append("This build is self-contained, so no backend engine was needed.")
    lines.append("Code blocks (the full set is in the Hub panel):")
    for b in pkg["blocks"]:
        code = b["code"] if len(b["code"]) <= 9000 else b["code"][:9000] + "\n... (cut here; copy the full block from the Hub panel)"
        lines.append("\n%s [%s]\n```%s\n%s\n```" % (b["label"], b["filename"], b["language"], code))
    return "\n".join(lines), {"dashboard": {"hub_id": hub["id"], "created_hub": res["created_hub"]}}

@app.route("/bridge", methods=["POST", "OPTIONS"])
def bridge():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response

    global latest_chat_message
    data = request.get_json(silent=True) or {}
    msg = (
        data.get("message") or
        data.get("prompt") or
        data.get("text") or
        next((v for v in data.values() if isinstance(v, str)), None) or
        request.data.decode('utf-8', errors='ignore')
    )
    if not msg or not str(msg).strip():
        res = jsonify({"error": "No message provided"})
        response = make_response(res, 400)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    try:
        clean_msg = str(msg).strip()
        extras = {}
        halt = _mode_gate(clean_msg)
        if halt:
            latest_chat_message = {"sender": "NEXXUS", "text": halt["message"]}
            return handle_action_response({"status": "success", "message": halt["message"], "audio_muted": False,
                                           "halted": True, "mode": halt["mode"], "mode_required": halt})
        mesh_text = _mesh_report_reply(clean_msg)
        if clean_msg.lower().startswith("search:"):
            search_query = clean_msg[7:].strip()
            search_results = route_axis_search(search_query)
            reply = f"AXIS search complete for: '{search_query}'."
        elif mesh_text:
            reply = mesh_text
        else:
            cap_out = _capture_chat_reply(clean_msg)
            tool_out = cap_out or _tools_chat_reply(clean_msg)
            eng_out = None if tool_out else (_sketch_chat_reply(clean_msg) or _engine_chat_reply(clean_msg) or _diagnostic_chat_reply(clean_msg) or _link_chat_reply(clean_msg))
            dash_out = None if (tool_out or eng_out) else _dashboard_chat_reply(clean_msg)
            if tool_out:
                reply, extras = tool_out
            elif eng_out:
                reply, extras = eng_out
            elif dash_out:
                reply, extras = dash_out
            else:
                reply, extras = _invoke_nexxus_pipeline(_mode_pipeline_text(clean_msg))

        latest_chat_message = {"sender": "NEXXUS", "text": reply}
        payload = {"status": "success", "message": reply, "audio_muted": False}
        # Context self-awareness: when the chat gets too heavy, save a handoff and tell the operator (see context_guard.py).
        try:
            _ctx = _context_guard.record_turn(clean_msg, reply)
            if _ctx:
                payload["message"] = reply + "\n\n" + _ctx["notice"]
                payload["context_notice"] = _ctx
        except Exception:
            pass
        # "question" is only present when NEXXUS's QuestionQueue has a pending
        # clarifying question (e.g. "build funnel" was ambiguous between
        # several saved client configs) - the dashboard renders this as
        # clickable option buttons instead of plain chat text when present.
        payload.update(extras)
        res = jsonify(payload)
        response = make_response(res)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    except Exception as e:
        res = jsonify({"error": str(e)})
        response = make_response(res, 500)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

import context_guard as _context_guard

@app.route("/api/context/status", methods=["GET", "OPTIONS"])
def context_status():
    return handle_action_response({"status": "success", **_context_guard.status()})

@app.route("/api/context/handoff", methods=["GET", "OPTIONS"])
def context_handoff():
    return handle_action_response({"status": "success", "continuation_prompt": _context_guard.continuation_prompt(), **_context_guard.status()})

@app.route("/api/context/new-window", methods=["POST", "OPTIONS"])
def context_new_window():
    if request.method == "OPTIONS":
        return handle_action_response()
    return handle_action_response({"status": "success", **_context_guard.start_new_window()})

import capture as _capture

def _is_local():
    """True only for a request from this machine's own dashboard page. Three checks: the connection is loopback; the Host header names loopback (stops DNS rebinding); and, if the browser sent an
    Origin, it is this very server (stops another web page from reading these routes, which answer with CORS open for the dashboard's sake)."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return False
    if (request.host or "").rsplit(":", 1)[0].strip("[]").lower() not in ("localhost", "127.0.0.1", "::1"):
        return False
    origin = request.headers.get("Origin")
    if origin and (urllib.parse.urlsplit(origin).netloc or "").lower() != (request.host or "").lower():
        return False
    return True

def _capture_chat_reply(text):
    """Chat commands for screen and camera capture. Local machine only, and each kind must have been switched on first (see capture.py)."""
    t = (text or "").strip().lower().rstrip(".!?")
    m = re.match(r"^(?:please\s+)?(?:take (?:a |the )?screenshot|screenshot|capture (?:the |my )?screen|screen snapshot)$", t)
    r = re.match(r"^(?:please\s+)?(?:record|capture)\s+(?:the |my )?screen(?:\s+for\s+(\d{1,3})\s*(?:s|sec|secs|seconds)?)?$", t)
    c = re.match(r"^(?:please\s+)?(?:take (?:a |the )?(?:camera |webcam )?(?:photo|picture|snapshot)|camera snapshot|webcam snapshot)$", t)
    stop = t in ("stop recording", "stop the recording")
    if not (m or r or c or stop):
        return None
    if not _is_local():
        return "Capture commands only work from the computer NEXXUS runs on.", {}
    try:
        if stop:
            out = _capture.stop_recording()
            return ("Recording stopped and saved: %s" % out["saved"]["id"]) if out.get("saved") else "No recording is running.", {}
        if m:
            return "Screenshot saved: %s" % _capture.screen_snapshot()["id"], {}
        if r:
            out = _capture.start_recording(int(r.group(1) or 10))
            return "Recording the screen for %ss. Say 'stop recording' to end it early. File: %s" % (out["seconds"], out["id"]), {}
        return "Camera snapshot saved: %s" % _capture.camera_snapshot()["id"], {}
    except _capture.CaptureError as e:
        return str(e), {}

@app.route("/api/capture/status", methods=["GET", "OPTIONS"])
def capture_status():
    return handle_action_response({"status": "success", **_capture.status()})

@app.route("/api/capture/<action>", methods=["POST", "OPTIONS"])
def capture_action(action):
    """permissions, screen-snapshot, record, stop, camera-snapshot, analyze. Local machine only; capturing also needs {"confirm": true}."""
    if request.method == "OPTIONS":
        return handle_action_response()
    if not _is_local():
        return make_response(jsonify({"status": "error", "message": "capture can only be driven from the local machine"}), 403)
    d = request.get_json(silent=True) or {}
    if action not in ("permissions", "stop") and d.get("confirm") is not True:
        return make_response(jsonify({"status": "error", "message": 'send {"confirm": true} to confirm this capture'}), 400)
    try:
        if action == "permissions":
            out = _capture.set_permission(d.get("kind", ""), bool(d.get("on")))
        elif action == "screen-snapshot":
            out = _capture.screen_snapshot()
        elif action == "record":
            out = _capture.start_recording(d.get("seconds", 10))
        elif action == "stop":
            out = _capture.stop_recording()
        elif action == "camera-snapshot":
            out = _capture.camera_snapshot(d.get("device"))
        elif action == "analyze":
            out = _capture.analyze(str(d.get("id", "")), d.get("prompt") or "Describe what you see in this image.")
        else:
            return make_response(jsonify({"status": "error", "message": "unknown capture action"}), 404)
    except (_capture.CaptureError, ValueError) as e:
        return make_response(jsonify({"status": "error", "message": str(e)}), 400)
    return handle_action_response({"status": "success", "result": out})

import platform_mode as _platform

if _mode_state is not None:
    _platform.register_mode(_mode_state, _modes)          # adds the locked Platform mode (needs a valid license, see entitlements.py)
_platform.register_routes(app, _is_local, lambda payload, status=200: _json_cors(payload, status))

import telemetry_hub as _tele

@app.route("/api/sandbox-telemetry/summary", methods=["GET", "OPTIONS"])
def sandbox_telemetry_summary():
    """Aggregate numbers from opt-in sandbox sessions (counts only; install ids and raw events are never returned). Local machine only."""
    if request.method == "OPTIONS":
        return handle_action_response()
    if not _is_local():
        return make_response(jsonify({"status": "error", "message": "local machine only"}), 403)
    try:
        days = max(1, min(int(request.args.get("days", 7)), 90))
    except ValueError:
        days = 7
    return handle_action_response({"status": "success", **_tele.summary(days)})

@app.route("/api/sandbox-telemetry/pull", methods=["POST", "OPTIONS"])
def sandbox_telemetry_pull():
    """Collect queued events from the relay now (the desktop calls out; nothing connects in). Local machine only."""
    if request.method == "OPTIONS":
        return handle_action_response()
    if not _is_local():
        return make_response(jsonify({"status": "error", "message": "local machine only"}), 403)
    try:
        return handle_action_response({"status": "success", **_tele.pull_once()})
    except RuntimeError as e:
        return make_response(jsonify({"status": "error", "message": str(e)}), 400)
    except Exception as e:
        return make_response(jsonify({"status": "error", "message": "relay not reachable: " + type(e).__name__}), 502)

try:
    _tele.start_poller()          # only starts when NEXXUS_RELAY_URL and NEXXUS_RELAY_KEY are set
except Exception:
    pass

import watchers as _watchers

def _watch_notify(f):
    """Watcher findings become notifications. Observe and flag only: nothing is blocked or stopped (see watchers.py)."""
    if _notes is not None:
        _notes.add("watch", "Watcher: " + f["rule"].replace("_", " "), f["summary"] + " " + f["suggestion"], level="fail" if f["severity"] == "alert" else "warn",
                   ref={"rule": f["rule"], "dedupe": "watch:%s:%s:%d" % (f["rule"], f["subject"], f["t"] // 3600)}, dedupe_key="watch:%s:%s:%d" % (f["rule"], f["subject"], f["t"] // 3600))

@app.route("/api/watch/findings", methods=["GET", "OPTIONS"])
def watch_findings():
    """What the watcher bots flagged in the last 24 hours (counts and short random ids only). Local machine only."""
    if request.method == "OPTIONS":
        return handle_action_response()
    if not _is_local():
        return make_response(jsonify({"status": "error", "message": "local machine only"}), 403)
    return handle_action_response({"status": "success", "findings": _watchers.recent()})

@app.route("/api/watch/scan", methods=["POST", "OPTIONS"])
def watch_scan():
    """Run every watcher once now. Local machine only."""
    if request.method == "OPTIONS":
        return handle_action_response()
    if not _is_local():
        return make_response(jsonify({"status": "error", "message": "local machine only"}), 403)
    return handle_action_response({"status": "success", "new": _watchers.scan(notifier=_watch_notify)})

try:
    _watchers.start(60, _watch_notify)
except Exception:
    pass

import operator_scope as _op_scope

@app.route("/api/operator/grants", methods=["GET", "POST", "DELETE", "OPTIONS"])
def operator_grants():
    """Operator mode v1 works only inside folders granted here. Changing grants is allowed from this machine only."""
    if request.method == "OPTIONS":
        return handle_action_response()
    if request.method == "GET":
        return handle_action_response({"status": "success", "folders": _op_scope.grants()})
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return make_response(jsonify({"status": "error", "message": "grants can only be changed from the local machine"}), 403)
    folder = (request.get_json(silent=True) or {}).get("folder", "")
    if request.method == "POST":
        ok, why = _op_scope.grant(folder)
        return make_response(jsonify({"status": "success" if ok else "error", "message": why, "folders": _op_scope.grants()}), 200 if ok else 400)
    _op_scope.revoke(folder)
    return handle_action_response({"status": "success", "folders": _op_scope.grants()})

@app.route("/api/operator/check", methods=["POST", "OPTIONS"])
def operator_check():
    if request.method == "OPTIONS":
        return handle_action_response()
    ok, why = _op_scope.check((request.get_json(silent=True) or {}).get("path", ""), "check")
    return handle_action_response({"status": "success", "allowed": ok, "reason": why})

def handle_action_response(data_payload=None):
    res = jsonify(data_payload or {"status": "success"})
    response = make_response(res)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response

# final_asset_port's own result dicts carry a "code" on error (not_found |
# invalid | capacity | internal - see its module docstring), but
# handle_action_response() always answers 200 regardless of that code, so a
# caller checking only the HTTP status (rather than parsing the body) would
# see 200 for a purged/nonexistent asset and wrongly conclude it still
# exists. This was caught for real: inspecting an asset immediately after a
# successful purge of that same asset returned 200 with an error body
# instead of 404. vault_asset_download already hand-rolled the correct
# mapping for its one case; this generalizes that so every vault_asset_detail
# verb (GET/PATCH/DELETE) answers with real, checkable HTTP status codes.
_VAULT_ERROR_CODE_TO_HTTP = {"not_found": 404, "invalid": 400, "capacity": 409, "internal": 500}

def handle_vault_result(result):
    status_code = 200
    if isinstance(result, dict) and result.get("status") == "error":
        status_code = _VAULT_ERROR_CODE_TO_HTTP.get(result.get("code"), 400)
    res = jsonify(result)
    response = make_response(res, status_code)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response

# Staging Area + Micro-Dispatch Pipeline: wired to the REAL scrape/LLM functions
# already defined above, so a staged job's "scrape" stage runs the same
# route_axis_search this server always used, and "plain_speak" runs through the
# same Llama.cpp/Ollama pipeline as every chat message - no separate/fake backend.
try:
    from micro_dispatch import staging_area, MicroDispatchPipeline
    dispatch_pipeline = MicroDispatchPipeline(staging_area, route_axis_search, route_bridge_request)
except ImportError:
    staging_area = None
    dispatch_pipeline = None

@app.route("/sandbox-toggle", methods=["POST", "OPTIONS"])
def sandbox_toggle():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    return handle_action_response({"status": "success", "action": "sandbox-toggle"})

@app.route("/status-recheck", methods=["POST", "OPTIONS"])
def status_recheck():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    return handle_action_response({"status": "success", "action": "status-recheck"})

@app.route("/poll-subsystem", methods=["POST", "OPTIONS"])
def poll_subsystem():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    return handle_action_response({"status": "success", "action": "poll-subsystem"})

@app.route("/flush-buffer", methods=["POST", "OPTIONS"])
def flush_buffer():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    return handle_action_response({"status": "success", "action": "flush-buffer"})

@app.route("/search", methods=["POST", "OPTIONS"])
def search_action():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    results = route_axis_search(query) if query else {"status": "ready"}
    return handle_action_response({"status": "success", "results": results})

@app.route("/speech-toggle", methods=["POST", "OPTIONS"])
def speech_toggle():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    return handle_action_response({"status": "success", "action": "speech-toggle"})

@app.route("/command-dispatch", methods=["POST", "OPTIONS"])
def command_dispatch():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    data = request.get_json(silent=True) or {}
    command = (
        data.get("command") or
        data.get("message") or
        data.get("text") or
        next((v for v in data.values() if isinstance(v, str)), None) or
        ""
    )
    clean_cmd = str(command).strip()
    if not clean_cmd:
        res = jsonify({"status": "error", "message": "No command provided"})
        response = make_response(res, 400)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    extras = {}
    global latest_chat_message
    halt = _mode_gate(clean_cmd)
    if halt:
        latest_chat_message = {"sender": "NEXXUS", "text": halt["message"]}
        return handle_action_response({"status": "success", "dispatched": clean_cmd, "response": halt["message"],
                                       "halted": True, "mode": halt["mode"], "mode_required": halt})
    # Domain courier: in Conversation mode a prompt that clearly targets ONE hub (Sports, Markets, Logistics, Economics) is not answered here. It is packaged and sent to that hub's own local
    # port, and the hub's reply comes back unaltered. If the hub is down the courier says so; it never answers in the hub's place. Everything else takes the regular route below.
    if _domain_dispatch is not None and _mode_state is not None and _mode_state.mode == "conversation":
        courier = _domain_dispatch.route(clean_cmd)
        if courier is not None:
            if courier["ok"]:
                c_reply, c_extras = courier["reply"], {"domain_hub": {"domain": courier["domain"], "port": courier["port"], "kind": courier["hub"].get("kind")}, "hub_payload": courier["hub"]}
            else:
                c_reply, c_extras = _domain_dispatch.courier_error_text(courier), {"domain_hub": {"domain": courier.get("domain"), "port": courier.get("port"), "error": True}}
            latest_chat_message = {"sender": "NEXXUS", "text": c_reply}
            return handle_action_response(dict({"status": "success", "dispatched": clean_cmd, "response": c_reply}, **c_extras))
    mesh_text = _mesh_report_reply(clean_cmd)
    if clean_cmd.lower().startswith("search:"):
        search_query = clean_cmd[7:].strip()
        reply = f"AXIS search complete for: '{search_query}'."
    elif mesh_text:
        reply = mesh_text
    else:
        tool_out = _tools_chat_reply(clean_cmd)
        eng_out = None if tool_out else (_sketch_chat_reply(clean_cmd) or _engine_chat_reply(clean_cmd) or _diagnostic_chat_reply(clean_cmd) or _link_chat_reply(clean_cmd))
        creation_out = None if (tool_out or eng_out) else _creation_chat_reply(clean_cmd, active_id=str(data.get("active_creation_id") or "") or None)
        dash_out = None if (tool_out or eng_out or creation_out) else _dashboard_chat_reply(clean_cmd)
        if tool_out:
            reply, extras = tool_out
        elif eng_out:
            reply, extras = eng_out
        elif creation_out:
            reply, extras = creation_out
        elif dash_out:
            reply, extras = dash_out
        else:
            reply, extras = _invoke_nexxus_pipeline(_mode_pipeline_text(clean_cmd))

    latest_chat_message = {"sender": "NEXXUS", "text": reply}
    payload = {
        "status": "success",
        "dispatched": clean_cmd,
        "response": reply
    }
    # See /bridge's handling of this same field - command-dispatch is the
    # frontend's primary chat path (it only falls back to /bridge if this
    # fails), so the clarifying-question payload has to be forwarded from
    # here too, not just from /bridge, or it would never reach the dashboard.
    payload.update(extras)
    return handle_action_response(payload)

@app.route("/save-session", methods=["POST", "OPTIONS"])
def save_session():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    return handle_action_response({"status": "success", "action": "save-session"})

@app.route("/axis/primary", methods=["POST", "OPTIONS"])
def axis_primary():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    data = request.get_json(silent=True) or {}
    return handle_action_response(execute_axis_primary(data.get("query", "")))

@app.route("/axis/secondary", methods=["POST", "OPTIONS"])
def axis_secondary():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    data = request.get_json(silent=True) or {}
    return handle_action_response(execute_axis_secondary(data.get("query", "")))

@app.route("/api/get-chat", methods=["GET", "POST", "OPTIONS"])
def chat_sync():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST")
        return response
    global latest_chat_message
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        if "text" in data and "sender" in data:
            latest_chat_message = data
        res = jsonify({"status": "success"})
        response = make_response(res)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    res = jsonify(latest_chat_message)
    response = make_response(res)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response

# ═══════════════════════════════════════════════════════
# PREVIOUSLY-MISSING BINDINGS
# The frontend's dispatchPythonServerRequest() already calls these endpoints and
# has always degraded gracefully (its own catch-all falls back to local client-side
# behavior on any error, including a 404), so nothing was crashing - these routes
# just weren't backed by real server logic yet. Adding them here does not change
# any frontend code or its appearance; it only makes what was already being called
# actually reach real logic instead of silently 404'ing.
# ═══════════════════════════════════════════════════════

@app.route("/create-hub", methods=["POST", "OPTIONS"])
def create_hub():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    data = request.get_json(silent=True) or {}
    return handle_action_response({"status": "success", "action": "create-hub", "hub": data})

@app.route("/api/hub/<hub_id>/telemetry", methods=["GET", "OPTIONS"])
def hub_telemetry(hub_id):
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "GET")
        return response
    # Pre-computed so a hub silo has real numbers to show the instant it opens.
    return handle_action_response({
        "status": "success",
        "hub": hub_id,
        "engines_online": _mesh_manifest()["engines_verified"],
        "engines_expected": 21,
        "brain_loaded": NEXUS_AVAILABLE,
        "server_time": time.time(),
    })

@app.route("/api/diagnostic/deep-test", methods=["POST", "OPTIONS"])
def diagnostic_deep_test():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    data = request.get_json(silent=True) or {}
    name = data.get("name") or ""
    if name not in _axis_bridge.ENGINES and name != _axis_bridge.HUB:
        return handle_action_response({"status": "error", "error": f"unknown engine {name!r}"})
    probe = _axis_bridge.probe_engine(name, deep=True)
    return handle_action_response({
        "status": "success",
        "engine_id": data.get("engine_id"),
        "name": name,
        "result": "PASS" if probe["status"] == "found" else "FAIL",
        "probe": probe,
    })

@app.route("/api/diagnostic/full-silo", methods=["POST", "OPTIONS"])
def diagnostic_full_silo():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    m = _mesh_manifest(deep=True)
    return handle_action_response({
        "status": "success",
        "result": "ALL VERIFIED" if m["engines_verified"] == m["expected_engines"] else
                  f"{m['engines_verified']}/{m['expected_engines']} engines verified",
        "manifest": m,
    })

def _admin_ok():
    tok = os.environ.get("NEXXUS_ADMIN_TOKEN", "")
    return bool(tok) and request.headers.get("X-Nexxus-Admin-Token") == tok

@app.route("/api/mesh/instruct", methods=["POST"], strict_slashes=False)
def mesh_instruct():
    # Runs engine code, so it needs the admin token (same gate as the vault).
    if not os.environ.get("NEXXUS_ADMIN_TOKEN"):
        return handle_action_response({"status": "error", "error": "NEXXUS_ADMIN_TOKEN not configured"}), 503
    if not _admin_ok():
        return handle_action_response({"status": "error", "error": "unauthorized"}), 401
    d = request.get_json(silent=True) or {}
    if _telemetry is not None and d.get("engine"):
        _telemetry.record(str(d.get("engine")), "instruct", str(d.get("instruction", ""))[:60])
    return handle_action_response(_axis_bridge.instruct(d.get("engine"), d.get("instruction", ""), d.get("payload")))

@app.route("/api/mesh/message", methods=["POST"], strict_slashes=False)
def mesh_message():
    # Engine -> hub (or engine -> engine via hub). Must carry a signed packet (the engine's own derived key, or the legacy shared key unless NEXXUS_REQUIRE_ENGINE_KEYS=1).
    d = request.get_json(silent=True) or {}
    if not _gov.validate_engine_packet(d):
        return handle_action_response({"status": "error", "error": "bad or missing signature"}), 401
    if d.get("engine") not in _axis_bridge.ENGINES:
        return handle_action_response({"status": "error", "error": "unknown engine"}), 400
    to = d.get("to", "nexxus")
    if to == "nexxus":
        e = _axis_bridge.post_message(d["engine"], "nexxus", d.get("kind", "message"), d.get("body"))
        if _telemetry is not None:
            _telemetry.record(d["engine"], "message", str(d.get("kind", "message")))
        return handle_action_response({"status": "success", "message": e})
    if to in _axis_bridge.ENGINES:
        return handle_action_response(_axis_bridge.relay(d["engine"], to, d.get("body") or {}))
    return handle_action_response({"status": "error", "error": "unknown recipient"}), 400

@app.route("/api/mesh/messages", methods=["GET"], strict_slashes=False)
def mesh_messages():
    since = int(request.args.get("since", 0) or 0)
    return handle_action_response({"status": "success", "messages": _axis_bridge.messages(since, request.args.get("to"))})

@app.route("/api/mesh/status", methods=["POST"], strict_slashes=False)
def mesh_status_push():
    # Engine -> hub heartbeat. Signed (same HMAC as messages) so nothing can fake an engine's status.
    d = request.get_json(silent=True) or {}
    if not _gov.validate_engine_packet(d):
        return handle_action_response({"status": "error", "error": "bad or missing signature"}), 401
    if d.get("engine") not in _axis_bridge.ENGINES:
        return handle_action_response({"status": "error", "error": "unknown engine"}), 400
    try:
        hb = _axis_bridge.record_heartbeat(d["engine"], d.get("state"), d.get("metrics"), d.get("interval"))
    except _axis_bridge.HeartbeatError as e:
        return handle_action_response({"status": "error", "error": "invalid heartbeat: %s" % e}), 400
    if _telemetry is not None:
        _telemetry.record(d["engine"], "heartbeat", str(d.get("state") or ""))
    return handle_action_response({"status": "success", "received_at": hb["received_at"],
                                   "mesh_version": _axis_bridge.mesh_map()["version"]})

@app.route("/api/mesh/peers", methods=["POST"], strict_slashes=False)
def mesh_peers():
    # Engine -> hub: "who else is in the mesh and what can they do?" Signed. Also records which
    # map version this engine now knows, which is what the awareness count is built from.
    d = request.get_json(silent=True) or {}
    if not _gov.validate_engine_packet(d):
        return handle_action_response({"status": "error", "error": "bad or missing signature"}), 401
    if d.get("engine") not in _axis_bridge.ENGINES:
        return handle_action_response({"status": "error", "error": "unknown engine"}), 400
    m = _axis_bridge.mesh_map()
    _axis_bridge.ack_map(d["engine"], m["version"])
    return handle_action_response({"status": "success", **m})

@app.route("/api/mesh/utilities", methods=["GET"], strict_slashes=False)
def mesh_utilities():
    # Cached view; never runs an engine.
    name = request.args.get("name")
    data = _axis_bridge.find_utility(name) if name else _axis_bridge.list_utilities()
    return handle_action_response({"status": "success", "utilities": data})

@app.route("/api/mesh/utilities/discover", methods=["POST"], strict_slashes=False)
def mesh_utilities_discover():
    if not os.environ.get("NEXXUS_ADMIN_TOKEN"):
        return handle_action_response({"status": "error", "error": "NEXXUS_ADMIN_TOKEN not configured"}), 503
    if not _admin_ok():
        return handle_action_response({"status": "error", "error": "unauthorized"}), 401
    return handle_action_response({"status": "success", "results": _axis_bridge.discover_all()})

@app.route("/api/mesh/call", methods=["POST"], strict_slashes=False)
def mesh_call():
    # Direct utility call (non-build utilities only). Build utilities go through /api/mesh/job.
    if not os.environ.get("NEXXUS_ADMIN_TOKEN"):
        return handle_action_response({"status": "error", "error": "NEXXUS_ADMIN_TOKEN not configured"}), 503
    if not _admin_ok():
        return handle_action_response({"status": "error", "error": "unauthorized"}), 401
    d = request.get_json(silent=True) or {}
    r = _axis_bridge.call_utility(d.get("engine"), d.get("utility"), d.get("args"))
    return handle_action_response(r), (200 if r["status"] == "success" else 409)

@app.route("/api/mesh/job", methods=["POST"], strict_slashes=False)
def mesh_job():
    # Runs a utility as a JOB: same queue, Build Mode events, truth gate and completion notice
    # as every other build. This is the only path for utilities flagged build=True.
    if not os.environ.get("NEXXUS_ADMIN_TOKEN"):
        return handle_action_response({"status": "error", "error": "NEXXUS_ADMIN_TOKEN not configured"}), 503
    if not _admin_ok():
        return handle_action_response({"status": "error", "error": "unauthorized"}), 401
    mgr, err = _jobs_or_503()
    if err:
        return err
    _axis_bridge.register_job_runner(mgr)
    d = request.get_json(silent=True) or {}
    job = mgr.submit("mesh_utility", {"engine": d.get("engine"), "utility": d.get("utility"), "args": d.get("args") or {}},
                     f"{d.get('engine')}.{d.get('utility')}")
    return handle_action_response({"status": "success", "job": job})

def _server_identity():
    """Which python_server.py answered, and which mesh routes it really has. Lets the dashboard and the
    install checker tell 'route missing because this is an old server copy' apart from 'server offline'."""
    return {"file": os.path.abspath(__file__),
            "mesh_routes": sorted(r.rule for r in app.url_map.iter_rules() if r.rule.startswith("/api/mesh/")),
            "started": _SERVER_STARTED}

_SERVER_STARTED = time.time()

@app.route("/api/mesh/telemetry", methods=["GET"], strict_slashes=False)
def mesh_telemetry():
    # Read-only and cheap: never runs an engine, so the dashboard can poll it.
    _gov.discover_and_register()
    return handle_action_response({"status": "success", **_axis_bridge.telemetry(), "server": _server_identity()})

@app.route("/api/mesh/manifest", methods=["GET"], strict_slashes=False)
def mesh_manifest():
    return handle_action_response({"status": "success", **_mesh_manifest(deep=request.args.get("deep") == "1")})

# ═══════════════════════════════════════════════════════
# MESH VERIFICATION (all 21 engines): what is wired, what is not, what to plug in next.
# GET is cheap and runs nothing. POST .../run also probes every opted-in engine (separate processes), so it
# needs the admin token like every other route that runs engine code.
# ═══════════════════════════════════════════════════════
@app.route("/api/mesh/diagnostic", methods=["GET", "OPTIONS"], strict_slashes=False)
def mesh_diagnostic_report():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if _mesh_diag is None:
        return _json_cors({"status": "error", "error": "mesh_diagnostic.py is not installed next to python_server.py"}, 503)
    _gov.discover_and_register()
    return _json_cors(_mesh_diag.run_diagnostic(probe=False))

@app.route("/api/mesh/diagnostic/run", methods=["POST", "OPTIONS"], strict_slashes=False)
def mesh_diagnostic_run():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    if _mesh_diag is None:
        return _json_cors({"status": "error", "error": "mesh_diagnostic.py is not installed next to python_server.py"}, 503)
    if not os.environ.get("NEXXUS_ADMIN_TOKEN"):
        return _json_cors({"status": "error", "error": "NEXXUS_ADMIN_TOKEN not configured: the probe starts engine processes, so it needs the admin token"}, 503)
    if not _admin_ok():
        return _json_cors({"status": "error", "error": "unauthorized"}, 401)
    _gov.discover_and_register()
    return _json_cors(_mesh_diag.run_diagnostic(probe=True))

# ═══════════════════════════════════════════════════════
# DASHBOARD HUB MAPPING: which staging-vault profiles and bots are mapped into which hub.
# Allowed only in Dashboard Hub Build mode. The mapping is kept here (not just in the page) so it survives
# a reload, and "verify" checks each mapped item still exists on the backend.
# ═══════════════════════════════════════════════════════
import json as _json_hm, tempfile as _tempfile_hm
_HUBMAP_LOCK = threading.RLock()
_HUBMAP_MAX = 100

def _hubmap_path():
    return Path(os.environ.get("NEXXUS_HUBMAP_PATH") or (Path(__file__).resolve().parent / "hub_mapping.json"))

def _hubmap_load():
    try:
        d = _json_hm.loads(_hubmap_path().read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except FileNotFoundError:
        return []
    except Exception:
        try:
            _hubmap_path().rename(_hubmap_path().with_suffix(".corrupt-%d" % int(time.time())))
        except OSError:
            pass
        return []

def _hubmap_save(items):
    try:
        p = _hubmap_path(); p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = _tempfile_hm.mkstemp(dir=str(p.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            _json_hm.dump(items, f, indent=1)
        os.replace(tmp, p)
    except OSError:
        pass

def _hubmap_mode_block():
    if _mode_state is not None and _mode_state.mode != "dashboard_hub":
        return _json_cors({"status": "halted", "reason": "hub_mapping_needs_dashboard_hub_mode", "mode": _mode_state.mode,
                           "message": "Mapping vault profiles and bots into the interface is part of Dashboard Hub Build mode. Switch to it first."}, 409)
    return None

@app.route("/api/hubs/mapping", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def hub_mapping():
    if request.method == "OPTIONS":
        return _cors_options("GET, POST")
    with _HUBMAP_LOCK:
        items = _hubmap_load()
        if request.method == "GET":
            return _json_cors({"status": "success", "mappings": items})
        blocked = _hubmap_mode_block()
        if blocked:
            return blocked
        d = request.get_json(silent=True) or {}
        source, ref = str(d.get("source", "")), str(d.get("ref", "")).strip()
        hub_id = re.sub(r"[^a-z0-9_-]+", "-", str(d.get("hub_id", "")).strip().lower()).strip("-")[:40]
        if source not in ("vault", "bot") or not ref or len(ref) > 120 or not hub_id:
            return _json_cors({"status": "error", "error": "source ('vault' or 'bot'), ref and hub_id are required"}, 400)
        if any(m["hub_id"] == hub_id and m["source"] == source and m["ref"] == ref for m in items):
            return _json_cors({"status": "error", "error": "already mapped to this hub"}, 409)
        if len(items) >= _HUBMAP_MAX:
            return _json_cors({"status": "error", "error": "too many mappings (%d)" % _HUBMAP_MAX}, 409)
        item = {"id": uuid.uuid4().hex[:8], "hub_id": hub_id, "hub_title": str(d.get("hub_title") or hub_id)[:80],
                "source": source, "ref": ref, "title": str(d.get("title") or ref)[:80], "mapped_at": time.time()}
        items.append(item)
        _hubmap_save(items)
        if _dash is not None:            # the mapped item also lives on a real dashboard (zero leftovers)
            try:
                _dash.ensure_hub(hub_id, item["hub_title"], _dash_base())
                _dash.nest(hub_id, source, ref, item["title"])
            except Exception:
                pass
        return _json_cors({"status": "success", "mapping": item, "mappings": items})

@app.route("/api/hubs/mapping/remove", methods=["POST", "OPTIONS"], strict_slashes=False)
def hub_mapping_remove():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    blocked = _hubmap_mode_block()
    if blocked:
        return blocked
    mid = str((request.get_json(silent=True) or {}).get("id", ""))
    with _HUBMAP_LOCK:
        items = _hubmap_load()
        kept = [m for m in items if m["id"] != mid]
        if len(kept) == len(items):
            return _json_cors({"status": "error", "error": "no such mapping"}, 404)
        _hubmap_save(kept)
        if _dash is not None:            # taking it off one hub must not leave it in "invisible land"
            try:
                gone = next(m for m in items if m["id"] == mid)
                _dash.unnest(gone["hub_id"], gone["source"], gone["ref"])
                _dash.adopt_orphans({gone["source"]: [gone["ref"]]}, _dash_base())
            except Exception:
                pass
        return _json_cors({"status": "success", "mappings": kept})

@app.route("/api/hubs/mapping/verify", methods=["GET", "OPTIONS"], strict_slashes=False)
def hub_mapping_verify():
    """Frontend-backend check: does each mapped profile / bot still exist where the backend keeps it?"""
    if request.method == "OPTIONS":
        return _cors_options("GET")
    staged = set()
    if staging_area is not None:
        try:
            staged = {c["category"] for c in staging_area.list_categories().get("categories", [])}
        except Exception:
            staged = set()
    committed = set()
    try:
        port = getattr(nexus_module, "final_asset_port", None) if NEXUS_AVAILABLE else None
        if port is not None:
            committed = {a.get("name") for a in (port.list_assets().get("assets") or [])}
    except Exception:
        committed = set()
    bots = set(getattr(nexus_module, "BOT_REGISTRY", {}).keys()) if NEXUS_AVAILABLE else set()
    out = []
    with _HUBMAP_LOCK:
        for m in _hubmap_load():
            if m["source"] == "vault":
                where = "staging" if m["ref"] in staged else "permanent vault" if m["ref"] in committed else None
            else:
                where = "bot registry" if m["ref"] in bots else None
            out.append({"id": m["id"], "ok": where is not None, "where": where,
                        "reason": None if where else ("not in staging or the permanent vault" if m["source"] == "vault" else "not in the bot registry")})
    return _json_cors({"status": "success", "checked_at": time.time(), "results": out,
                       "ok": sum(1 for r in out if r["ok"]), "missing": sum(1 for r in out if not r["ok"])})



# ═══════════════════════════════════════════════════════
# CONNECTIVITY: the Tailscale tunnel and Bluetooth devices.
# Reading state is open; anything that changes it (connect, disconnect, share, scan, add, remove) needs the admin token.
# ═══════════════════════════════════════════════════════
def _admin_gate():
    if not os.environ.get("NEXXUS_ADMIN_TOKEN"):
        return _json_cors({"status": "error", "error": "NEXXUS_ADMIN_TOKEN is not set, so this action is switched off"}, 503)
    if not _admin_ok():
        return _json_cors({"status": "error", "error": "unauthorized"}, 401)
    return None

def _conn_missing(obj, name):
    return _json_cors({"status": "error", "error": "%s is not installed next to python_server.py" % name}, 503) if obj is None else None

@app.route("/api/tunnel/status", methods=["GET", "OPTIONS"], strict_slashes=False)
def tunnel_status():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    m = _conn_missing(_tunnel, "tunnel_control.py")
    return m or _json_cors({"status": "success", "tunnel": _tunnel.status()})

@app.route("/api/tunnel/<action>", methods=["POST", "OPTIONS"], strict_slashes=False)
def tunnel_action(action):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    m = _conn_missing(_tunnel, "tunnel_control.py")
    if m:
        return m
    fn = {"connect": "connect", "disconnect": "disconnect", "share": "share", "unshare": "unshare"}.get(action)
    if not fn:
        return _json_cors({"status": "error", "error": "unknown tunnel action"}, 404)
    g = _admin_gate()
    if g:
        return g
    res = getattr(_tunnel, fn)()
    return _json_cors({"status": "success" if res["ok"] else "error", "result": res, "error": res.get("error")}, 200 if res["ok"] else 409)

@app.route("/api/bluetooth/devices", methods=["GET", "OPTIONS"], strict_slashes=False)
def bluetooth_devices():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    m = _conn_missing(_bt, "bluetooth_control.py")
    return m or _json_cors({"status": "success", **_bt.devices()})

@app.route("/api/bluetooth/<action>", methods=["POST", "OPTIONS"], strict_slashes=False)
def bluetooth_action(action):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    m = _conn_missing(_bt, "bluetooth_control.py")
    if m:
        return m
    if action not in ("scan", "add", "remove", "connect", "disconnect"):
        return _json_cors({"status": "error", "error": "unknown bluetooth action"}, 404)
    g = _admin_gate()
    if g:
        return g
    d = request.get_json(silent=True) or {}
    try:
        if action == "scan":
            out = _bt.scan(d.get("seconds", 6))
        elif action == "add":
            _bt.add(d.get("address"), d.get("name")); out = _bt.devices()
        elif action == "remove":
            _bt.remove(d.get("address")); out = _bt.devices()
        elif action == "connect":
            _bt.connect(d.get("address")); out = _bt.devices()
        else:
            _bt.disconnect(d.get("address")); out = _bt.devices()
    except KeyError as e:
        return _json_cors({"status": "error", "error": "that device is not in your added list: %s" % (e.args[0] if e.args else "")}, 404)
    except ValueError as e:
        return _json_cors({"status": "error", "error": str(e)}, 400)
    except RuntimeError as e:
        return _json_cors({"status": "error", "error": str(e), **_bt.devices()}, 409)
    return _json_cors({"status": "success", **out})

# ═══════════════════════════════════════════════════════
# DASHBOARD & COMPONENT BUILD CYCLE
# Every dashboard is its own isolated sandbox folder: a static front face (default safe UI unless custom UI is
# given), both creators, nested silos for anything major, every profile / bot nested on a dashboard, backend engines
# wired through scoped hub routes, and the code handed back as paste-ready blocks. Building and changing are
# Dashboard Hub mode only; reading, previewing and the leftover audit work in any mode.
# ═══════════════════════════════════════════════════════
_DASH_CACHE = {"t": 0.0, "states": {}}

def _dash_or_503():
    if _dash is None:
        return _json_cors({"status": "error", "error": "dashboard_cycle.py is not installed next to python_server.py"}, 503)
    return None

def _dash_mode_block():
    if _mode_state is not None and _mode_state.mode != "dashboard_hub":
        halt = _modes.halt_payload(_mode_state.mode) if not _modes.MODES[_mode_state.mode]["can_build"] else None
        return _json_cors({"status": "halted", "reason": "dashboards_need_dashboard_hub_mode", "mode": _mode_state.mode,
                           "message": "Building or changing dashboards is part of Dashboard Hub Build mode. Switch to it first.",
                           **({"mode_required": halt} if halt else {})}, 409)
    return None

def _dash_base():
    env = os.environ.get("NEXXUS_PUBLIC_BASE")
    if env:
        return env
    try:
        host = request.host
        proto = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower()
        if proto not in ("http", "https"):
            proto = "https" if host.split(":")[0].endswith(".ts.net") else request.scheme   # reached through `tailscale serve`
        return "%s://%s" % (proto, host)
    except RuntimeError:
        return _dc.DEFAULT_BASE

def _dash_engine_states():
    """Engine -> mesh state from the static diagnostic (reads files, never runs an engine). Cached for 5 s."""
    now = time.time()
    if now - _DASH_CACHE["t"] < 5 and _DASH_CACHE["states"]:
        return _DASH_CACHE["states"]
    states = {}
    if _mesh_diag is not None:
        try:
            states = {e["name"]: e["status"] for e in _mesh_diag.run_diagnostic(probe=False)["engines"]}
        except Exception:
            states = {}
    _DASH_CACHE.update({"t": now, "states": states})
    return states

def _dash_utilities():
    try:
        return {e: (v or {}).get("utilities", {}) for e, v in _axis_bridge.list_utilities().items()}
    except Exception:
        return {}

def _dash_known():
    """Everything that exists on the backend and so must be nested on a dashboard."""
    vault = set()
    if staging_area is not None:
        try:
            vault |= {c["category"] for c in staging_area.list_categories().get("categories", [])}
        except Exception:
            pass
    try:
        port = getattr(nexus_module, "final_asset_port", None) if NEXUS_AVAILABLE else None
        if port is not None:
            vault |= {a.get("name") for a in (port.list_assets().get("assets") or []) if a.get("name")}
    except Exception:
        pass
    bots = set(getattr(nexus_module, "BOT_REGISTRY", {}).keys()) if NEXUS_AVAILABLE else set()
    return {"vault": sorted(vault), "bot": sorted(bots)}

def _bootstrap_default_dashboard():
    """First run: a fresh install has no dashboard, so the built-in bots would be reported as orphans and the audit would fail on day one. When NO dashboard exists yet, create the default one and nest
    what already exists on the backend. Idempotent: it does nothing once any dashboard exists, and anything added later still has to be nested by the owner (the audit keeps flagging it)."""
    if _dash is None:
        return {"created": False, "reason": "dashboard store unavailable"}
    try:
        if _dash.list():
            return {"created": False, "reason": "a dashboard already exists"}
        _dash.ensure_hub("nexxus-operations", title="NEXXUS Operations")
        known, nested = _dash_known(), 0
        for source in ("bot", "vault"):
            for ref in known.get(source, []):
                _dash.nest("nexxus-operations", source, ref)
                nested += 1
        print("[DASHBOARDS] first run: created the default dashboard and nested %d existing item(s)" % nested)
        return {"created": True, "nested": nested}
    except Exception as e:
        print("[DASHBOARDS] first-run setup skipped: %s" % type(e).__name__)
        return {"created": False, "reason": type(e).__name__}


def _dash_item_state(source, ref):
    """Read-only state of one nested item, for the dashboard's live view."""
    if source == "bot":
        bots = getattr(nexus_module, "BOT_REGISTRY", {}) if NEXUS_AVAILABLE else {}
        b = bots.get(ref)
        if not b:
            return {"state": "missing on backend", "detail": "not in the bot registry", "active": False}
        desc = b.get("description") if isinstance(b, dict) else getattr(b, "description", "")
        return {"state": "registered", "detail": str(desc or "")[:80], "active": False}
    if source == "vault":
        working = False
        try:
            mgr = _job_manager.get_default_manager() if _job_manager is not None else None
            for j in (mgr.list(50) if mgr else []):
                if j.get("status") in ("queued", "running") and ref in json.dumps(j.get("spec") or {}, default=str):
                    working = True
                    break
        except Exception:
            pass
        try:
            for c in (staging_area.list_categories().get("categories", []) if staging_area is not None else []):
                if c["category"] == ref:
                    return {"state": "building" if working else "staged", "detail": "%d file(s), %d bytes" % (c["file_count"], c["total_bytes"]), "active": working}
        except Exception:
            pass
        return {"state": "building" if working else "committed or unknown", "detail": "", "active": working}
    return {"state": "nested", "detail": "", "active": False}

_VENDOR_TAG = '<script src="/vendor/babylon.js"></script>'
_vendor_cache = {"text": None}

def _inline_vendor(html_text):
    """Generated dashboards are served in an isolated frame (opaque origin) that cannot fetch from this server, so the local Babylon.js is embedded
    in the page itself. Nothing is loaded from the internet, and the stored dashboard stays small."""
    if not html_text or _VENDOR_TAG not in html_text:
        return html_text
    if _vendor_cache["text"] is None:
        _vendor_cache["text"] = Path(HTML_FOLDER, "vendor", "babylon.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    return html_text.replace(_VENDOR_TAG, "<script>" + _vendor_cache["text"] + "</script>")

def _dash_html(html_text):
    resp = make_response(_inline_vendor(html_text) or "")
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store"
    # opaque origin: the dashboard cannot read the NEXXUS page's storage or call its authenticated routes
    resp.headers["Content-Security-Policy"] = "sandbox allow-scripts"
    return resp

def _dash_err(e):
    if isinstance(e, KeyError):
        return _json_cors({"status": "error", "error": "not found: %s" % (e.args[0] if e.args else "")}, 404)
    return _json_cors({"status": "error", "error": str(e)}, 400)

@app.route("/api/dashboards", methods=["GET", "OPTIONS"], strict_slashes=False)
def dashboards_list():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    un = _dash_or_503()
    if un:
        return un
    return _json_cors({"status": "success", "dashboards": _dash.list(), "mode": _mode_state.mode if _mode_state else None})

@app.route("/api/dashboards/build", methods=["POST", "OPTIONS"], strict_slashes=False)
def dashboards_build():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    un = _dash_or_503()
    if un:
        return un
    blocked = _dash_mode_block()
    if blocked:
        return blocked
    d = request.get_json(silent=True) or {}
    prompt = str(d.get("prompt") or "").strip()
    if not prompt and not d.get("ui"):
        return _json_cors({"status": "error", "error": "prompt is required"}, 400)
    try:
        res = _dc.build_dashboard(_dash, prompt, title=d.get("title"), kind=d.get("kind"), ui=d.get("ui"), hub_id=d.get("hub_id"),
                                  standalone=bool(d.get("standalone")), base=_dash_base(),
                                  engine_states=_dash_engine_states(), utilities=_dash_utilities())
    except Exception as e:
        return _dash_err(e)
    return _json_cors({"status": "success", **res})

@app.route("/api/dashboards/audit", methods=["GET", "OPTIONS"], strict_slashes=False)
def dashboards_audit():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    un = _dash_or_503()
    if un:
        return un
    out = _dash.audit(_dash_known())
    out["engine_cluster"] = _engine_cluster_rollup()
    return _json_cors(out)

def _engine_cluster_rollup():
    """The mesh engines judged as ONE headless background cluster, not as dashboard widgets. The standard (set by the owner): the engines run without a UI card of their own, the dashboard
    is the command / aggregation layer (telemetry, perimeter, quarantine). An orphan here is a DEAD process (on the roster, heartbeat gone stale), an UNREFERENCED engine folder (has a mesh.py
    but is not on the roster). Loose scripts inside engine folders are not scanned here. A healthy engine with no card is never an orphan. Read-only: runs nothing."""
    try:
        eng = _axis_bridge.telemetry().get("engines") or {}
    except Exception as e:
        return {"ok": False, "problem": "telemetry unavailable (%s)" % type(e).__name__}
    silo = Path(__file__).resolve().parent / "axis-ui-interface" / "project-X" / "silo_vault"
    on_disk = sorted(p.parent.name for p in silo.glob("*/mesh.py") if p.parent.name.startswith("axis-") or p.parent.name == "render")
    dead = sorted(n for n, v in eng.items() if not ((v.get("live") or {}).get("fresh")))
    unreferenced = sorted(n for n in on_disk if n not in eng)
    missing = sorted(n for n in eng if n not in on_disk)
    unready = sorted(n for n, v in eng.items() if not v.get("mesh_ready"))
    members = len(eng)
    return {"ok": not (dead or unreferenced or missing or unready), "members": members, "live": members - len(dead), "mesh_ready": members - len(unready),
            "dead_processes": dead, "unreferenced_folders": unreferenced, "roster_without_folder": missing, "not_mesh_ready": unready,
            "standard": "headless background cluster: engines need no dashboard card; an orphan is a dead process or an unreferenced file/folder"}

@app.route("/api/dashboards/adopt", methods=["POST", "OPTIONS"], strict_slashes=False)
def dashboards_adopt():
    """Zero leftovers: every profile / bot on the backend that is on no dashboard gets its own default static dashboard."""
    if request.method == "OPTIONS":
        return _cors_options("POST")
    un = _dash_or_503()
    if un:
        return un
    blocked = _dash_mode_block()
    if blocked:
        return blocked
    try:
        moved = _dash.adopt_orphans(_dash_known(), _dash_base())
    except Exception as e:
        return _dash_err(e)
    return _json_cors({"status": "success", "moved": moved, "audit": _dash.audit(_dash_known())})

@app.route("/api/dashboards/<hub_id>", methods=["GET", "OPTIONS"], strict_slashes=False)
def dashboards_get(hub_id):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    un = _dash_or_503()
    if un:
        return un
    h = _dash.get(hub_id)
    return _json_cors({"status": "success", "dashboard": h}) if h else _dash_err(KeyError(hub_id))

@app.route("/api/dashboards/<hub_id>/face", methods=["GET"], strict_slashes=False)
def dashboards_face(hub_id):
    un = _dash_or_503()
    if un:
        return un
    t = _dash.face_html(hub_id)
    return _dash_html(t) if t is not None else _dash_err(KeyError(hub_id))

@app.route("/api/dashboards/<hub_id>/silos/<silo_id>", methods=["GET"], strict_slashes=False)
def dashboards_silo_page(hub_id, silo_id):
    un = _dash_or_503()
    if un:
        return un
    t = _dash.silo_html(hub_id, silo_id)
    return _dash_html(t) if t is not None else _dash_err(KeyError(silo_id))

@app.route("/api/dashboards/<hub_id>/package", methods=["GET", "OPTIONS"], strict_slashes=False)
def dashboards_package(hub_id):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    un = _dash_or_503()
    if un:
        return un
    p = _dash.package(hub_id, _dash_base())
    return _json_cors({"status": "success", **p}) if p else _dash_err(KeyError(hub_id))

@app.route("/api/dashboards/<hub_id>/live", methods=["GET", "OPTIONS"], strict_slashes=False)
def dashboards_live(hub_id):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    un = _dash_or_503()
    if un:
        return un
    snap = _dash.live_snapshot(hub_id, _dash_item_state, _axis_bridge.live_status)
    return _json_cors(snap) if snap else _dash_err(KeyError(hub_id))

@app.route("/api/dashboards/<hub_id>/outputs", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def dashboards_outputs(hub_id):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    un = _dash_or_503()
    if un:
        return un
    if request.method == "POST":
        # A bot or engine delivering its work (server side, with the admin token) may write in any mode;
        # anyone else only while building in Dashboard Hub mode.
        if not (os.environ.get("NEXXUS_ADMIN_TOKEN") and _admin_ok()):
            blocked = _dash_mode_block()
            if blocked:
                return blocked
        d = request.get_json(silent=True) or {}
        try:
            return _json_cors({"status": "success", "output": _dash.add_output(hub_id, d.get("name"), d.get("text"))})
        except Exception as e:
            return _dash_err(e)
    if not _dash.get(hub_id):
        return _dash_err(KeyError(hub_id))
    return _json_cors({"status": "success", "outputs": _dash.outputs(hub_id)})

@app.route("/api/dashboards/<hub_id>/outputs/<name>", methods=["GET", "OPTIONS"], strict_slashes=False)
def dashboards_output_read(hub_id, name):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    un = _dash_or_503()
    if un:
        return un
    t = _dash.read_output(hub_id, name)
    return _json_cors({"status": "success", "name": name, "text": t}) if t is not None else _json_cors({"status": "error", "error": "no such output"}, 404)

def _dash_write_route(hub_id, fn):
    un = _dash_or_503()
    if un:
        return un
    blocked = _dash_mode_block()
    if blocked:
        return blocked
    try:
        return _json_cors({"status": "success", **fn(request.get_json(silent=True) or {})})
    except Exception as e:
        return _dash_err(e)

@app.route("/api/dashboards/<hub_id>/silos", methods=["POST", "OPTIONS"], strict_slashes=False)
def dashboards_add_silo(hub_id):
    if request.method == "OPTIONS":
        return _cors_options("POST")
    def go(d):
        if not str(d.get("title") or d.get("prompt") or "").strip():
            raise ValueError("title or prompt is required")
        silo = _dash.add_silo(hub_id, d.get("title") or _dc.nice_title(d.get("prompt")), d.get("kind"), d.get("prompt") or "",
                              bool(d.get("standalone")), _dash_base(), _dash_engine_states(), _dash_utilities())
        return {"silo": silo, "dashboard": _dash.get(hub_id)}
    return _dash_write_route(hub_id, go)

@app.route("/api/dashboards/<hub_id>/change", methods=["POST", "OPTIONS"], strict_slashes=False)
def dashboards_change(hub_id):
    if request.method == "OPTIONS":
        return _cors_options("POST")
    def go(d):
        text = str(d.get("text") or "").strip()
        if not text:
            raise ValueError("text is required")
        return {"result": _dash.request_change(hub_id, text, d.get("kind"), bool(d.get("standalone")), _dash_base(),
                                              _dash_engine_states(), _dash_utilities()), "dashboard": _dash.get(hub_id)}
    return _dash_write_route(hub_id, go)

@app.route("/api/dashboards/<hub_id>/identity", methods=["POST", "OPTIONS"], strict_slashes=False)
def dashboards_identity(hub_id):
    if request.method == "OPTIONS":
        return _cors_options("POST")
    return _dash_write_route(hub_id, lambda d: {"dashboard": _dash.edit_identity(hub_id, _dash_base(), **{k: v for k, v in d.items() if k != "hub_id"})})

@app.route("/api/dashboards/<hub_id>/nest", methods=["POST", "OPTIONS"], strict_slashes=False)
def dashboards_nest(hub_id):
    if request.method == "OPTIONS":
        return _cors_options("POST")
    return _dash_write_route(hub_id, lambda d: {"item": _dash.nest(hub_id, d.get("source"), d.get("ref"), d.get("title"), d.get("silo_id")),
                                                "dashboard": _dash.get(hub_id)})

@app.route("/api/dashboards/<hub_id>/repair", methods=["POST", "OPTIONS"], strict_slashes=False)
def dashboards_repair(hub_id):
    if request.method == "OPTIONS":
        return _cors_options("POST")
    return _dash_write_route(hub_id, lambda d: {"dashboard": _dash.repair(hub_id, _dash_base())})

# Scoped engine gateway: a dashboard can reach ONLY the engines wired to it, and only through the hub.
@app.route("/api/dashboards/<hub_id>/engines/<engine>/status", methods=["GET", "OPTIONS"], strict_slashes=False)
def dashboards_engine_status(hub_id, engine):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    un = _dash_or_503()
    if un:
        return un
    allowed = _dash.hub_engines(hub_id)
    if allowed is None:
        return _dash_err(KeyError(hub_id))
    if engine not in allowed:
        return _json_cors({"status": "error", "error": "engine %s is not wired to this dashboard" % engine}, 403)
    return _json_cors({"status": "success", "engine": engine, "live": _axis_bridge.live_status(engine),
                       "mesh_state": _dash_engine_states().get(engine, "UNKNOWN")})

@app.route("/api/dashboards/<hub_id>/engines/<engine>/call", methods=["POST", "OPTIONS"], strict_slashes=False)
def dashboards_engine_call(hub_id, engine):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    un = _dash_or_503()
    if un:
        return un
    if not os.environ.get("NEXXUS_ADMIN_TOKEN"):
        return _json_cors({"status": "error", "error": "NEXXUS_ADMIN_TOKEN not configured"}, 503)
    if not _admin_ok():
        return _json_cors({"status": "error", "error": "unauthorized"}, 401)
    allowed = _dash.hub_engines(hub_id)
    if allowed is None:
        return _dash_err(KeyError(hub_id))
    if engine not in allowed:
        return _json_cors({"status": "error", "error": "engine %s is not wired to this dashboard" % engine}, 403)
    d = request.get_json(silent=True) or {}
    r = _axis_bridge.call_utility(engine, d.get("utility"), d.get("args"))     # build utilities are refused here
    return _json_cors(r, 200 if r.get("status") == "success" else 409)

# ═══════════════════════════════════════════════════════
# OPERATING MODE (server-held). The dashboard asks; the server decides what each mode allows.
# ═══════════════════════════════════════════════════════
@app.route("/api/mode", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def operating_mode():
    if request.method == "OPTIONS":
        return _cors_options("GET, POST")
    if _mode_state is None:
        return _json_cors({"status": "error", "error": "mode_policy.py is not installed next to python_server.py"}, 503)
    if request.method == "POST":
        d = request.get_json(silent=True) or {}
        try:
            _mode_state.set(str(d.get("mode", "")))
        except ValueError as e:
            return _json_cors({"status": "error", "error": str(e)}, 400)
    return _json_cors({"status": "success", **_mode_state.snapshot()})

# ═══════════════════════════════════════════════════════
# BOT & ASSISTANT PROVISIONING - UI HOOK DISTRIBUTION
# Reads nexxus_talks.py's BOT_REGISTRY directly, so any bot registered there via
# register_bot(...) is reachable here automatically with no server restart-time
# route wiring needed per bot. /api/bots/manifest is the "export hook" a frontend
# could poll to auto-populate a bot list; note the current dashboard HTML does not
# yet poll it (left untouched per your instruction not to alter the frontend).
# ═══════════════════════════════════════════════════════

@app.route("/api/bots/manifest", methods=["GET", "OPTIONS"])
def bots_manifest():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "GET")
        return response
    bots = []
    if NEXUS_AVAILABLE and hasattr(nexus_module, "BOT_REGISTRY"):
        for bot_id, bot in nexus_module.BOT_REGISTRY.items():
            bots.append({
                "id": bot_id,
                "name": bot.get("name"),
                "description": bot.get("description"),
                "endpoint": bot.get("endpoint"),
            })
    return handle_action_response({"status": "success", "bots": bots})

@app.route("/api/bots/<bot_id>", methods=["POST", "OPTIONS"])
def bot_invoke(bot_id):
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response
    if not NEXUS_AVAILABLE or not hasattr(nexus_module, "BOT_REGISTRY"):
        res = jsonify({"status": "error", "message": "Bot registry unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    bot = nexus_module.BOT_REGISTRY.get(bot_id)
    if not bot:
        res = jsonify({"status": "error", "message": f"Unknown bot '{bot_id}'"})
        response = make_response(res, 404)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt") or data.get("message") or data.get("text") or ""
    try:
        result = bot["handler"](prompt)
    except Exception as e:
        result = {"status": "error", "error": str(e)}
    return handle_action_response({"status": "success", "bot_id": bot_id, "result": result})

# ═══════════════════════════════════════════════════════
# FINAL ASSET BIRTHING PORT
# Command endpoints for the final draft vault: ingest, inspect, manage, purge.
# Mirrors the bot endpoints' pattern - reads nexus_module.final_asset_port directly,
# so this stays a thin HTTP wrapper around final_asset_port.py rather than a second
# copy of its logic.
# ═══════════════════════════════════════════════════════

def _vault_or_503():
    if not NEXUS_AVAILABLE or not getattr(nexus_module, "final_asset_port", None):
        res = jsonify({"status": "error", "message": "final_asset_port unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return None

# Local shared-secret gate for vault MUTATIONS (ingest/patch/delete) over
# HTTP - not a full auth system, just a check so an arbitrary network caller
# can't rewrite or purge vault assets. No external auth provider, no cost:
# it's one env var compared against one request header. Read-only listing
# and inspection (GET) stay open - this only gates writes. Internal callers
# (the "build funnel" chat dispatch, which calls final_asset_port.ingest_
# directory() directly in-process, not through this HTTP route) are
# unaffected either way, since they never go through this endpoint.
#
# No token configured -> mutations are refused by default. That's a
# deliberate choice: silently defaulting to "open to anyone" would make this
# gate a no-op for exactly the deployments that forgot to set it.
VAULT_ADMIN_TOKEN = os.environ.get("NEXXUS_ADMIN_TOKEN")

def _require_vault_admin():
    if not VAULT_ADMIN_TOKEN:
        res = jsonify({"status": "error",
                        "message": "Vault mutations are disabled: set the NEXXUS_ADMIN_TOKEN environment variable to enable them."})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    if request.headers.get("X-Nexxus-Admin-Token") != VAULT_ADMIN_TOKEN:
        res = jsonify({"status": "error", "message": "Missing or invalid X-Nexxus-Admin-Token header."})
        response = make_response(res, 401)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return None

def _cors_options(methods):
    response = make_response()
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", methods)
    return response

# ═══════════════════════════════════════════════════════
# BACKGROUND JOBS (live Build Mode viewport + completion notices)
# ═══════════════════════════════════════════════════════
# Read-only endpoints the dashboard polls with a cursor. They only READ the
# shared JobManager - a poll never touches a running build, so watching a build
# can't slow it down or interfere with chat. hold/release change what the queue
# does, so they sit behind the same admin-token gate as vault mutations.
try:
    import job_manager as _job_manager
except ImportError:
    _job_manager = None

def _jobs_or_503():
    if _job_manager is None:
        res = jsonify({"status": "error", "message": "job_manager module not available"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return None, response
    return _job_manager.get_default_manager(), None

def _json_cors(payload, code=200):
    response = make_response(jsonify(payload), code)
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers["Cache-Control"] = "no-store"
    return response

# ═══════════════════════════════════════════════════════
# CATEGORY PROBATION + RECON (Phase 1 of the adaptive-intelligence rule)
# ═══════════════════════════════════════════════════════
# A category starts in observation: you confirm every run and each confirmation
# is recorded. Only after enough approvals AND your explicit promote click may a
# category re-run actions you already approved, and only read-only ones.
# Recon is read-only by construction (GET only, robots.txt, public hosts only).
_RECON_EXECUTOR = ThreadPoolExecutor(max_workers=2)   # separate from chat's pool so a slow crawl can't stall replies
_RECON_RUNS = {}
_RECON_LOCK = threading.Lock()
_RECON_MAX_RUNS = 40
_probation_store = _probation.ProbationStore() if _probation else None

def _admin_cors_options(methods):
    response = _cors_options(methods)
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Nexxus-Admin-Token"
    return response

def _probation_or_503():
    if _probation_store is None or _recon is None:
        return _json_cors({"status": "error", "message": "recon/probation modules not installed"}, 503)
    return None

@app.route("/api/categories", methods=["GET", "OPTIONS"], strict_slashes=False)
def categories_list():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    unavailable = _probation_or_503()
    if unavailable:
        return unavailable
    return _json_cors({"status": "success", "categories": _probation_store.list_all()})

@app.route("/api/categories/<category>/<action>", methods=["POST", "OPTIONS"], strict_slashes=False)
def categories_action(category, action):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    unavailable = _probation_or_503()
    if unavailable:
        return unavailable
    data = request.get_json(silent=True) or {}
    try:
        if action == "feedback":
            # Rejecting is always allowed (it only makes the system MORE cautious).
            # Approvals are recorded by confirmed runs, never by this endpoint.
            if data.get("outcome") != "rejected":
                return _json_cors({"status": "error", "message": "only outcome 'rejected' is accepted here"}, 400)
            view = _probation_store.observe(category, data.get("command", ""), "rejected")
            return _json_cors({"status": "success", **view})
        if action in ("promote", "demote"):
            if not os.environ.get("NEXXUS_ADMIN_TOKEN"):
                return _json_cors({"status": "error", "message": "NEXXUS_ADMIN_TOKEN not configured"}, 503)
            if not _admin_ok():
                return _json_cors({"status": "error", "message": "unauthorized"}, 401)
            result = _probation_store.promote(category) if action == "promote" else _probation_store.demote(category)
            return _json_cors(result, 200 if result.get("status") == "success" else 409)
    except ValueError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    return _json_cors({"status": "error", "message": "unknown action"}, 404)

@app.route("/api/recon/run", methods=["POST", "OPTIONS"], strict_slashes=False)
def recon_run():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    unavailable = _probation_or_503()
    if unavailable:
        return unavailable
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    try:
        category = _probation.slugify(data.get("category", ""))
        _recon.check_target(url)           # reject bad / private targets before anything is recorded
    except (ValueError, _recon.ReconError) as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    command = f"recon {url}"
    decision = _probation_store.decide(category, command, "read_only")
    if decision["action"] == "confirm" and data.get("confirm") is not True:
        return _json_cors({"status": "needs_confirmation", "decision": decision,
                           "message": f"Category '{category}' is {decision['phase']} "
                                      f"({decision['approved']}/{decision['needed']} approvals). Confirm to run it and teach NEXXUS."})
    with _RECON_LOCK:
        if sum(1 for r in _RECON_RUNS.values() if r["status"] == "running") >= 3:
            return _json_cors({"status": "error", "message": "too many recon runs in progress"}, 429)
        run_id = "recon-" + uuid.uuid4().hex[:10]
        run = {"id": run_id, "category": category, "url": url, "status": "running", "events": [], "stop": False,
               "result": None, "started": time.time()}
        _RECON_RUNS[run_id] = run
        for old in sorted(_RECON_RUNS, key=lambda k: _RECON_RUNS[k]["started"])[:-_RECON_MAX_RUNS]:
            if _RECON_RUNS[old]["status"] != "running":
                del _RECON_RUNS[old]
    if decision["action"] == "confirm":
        decision = {**decision, **_probation_store.observe(category, command, "approved"), "action": "confirm"}

    def _work():
        try:
            def emit(e):
                with _RECON_LOCK:
                    e["seq"] = len(run["events"]) + 1
                    run["events"].append(e)
            res = _recon.recon(url, max_pages=int(data.get("max_pages", 10) or 10),
                               max_depth=int(data.get("max_depth", 1) or 1),
                               on_event=emit, should_stop=lambda: run["stop"])
            run["result"] = res
            run["status"] = "stopped" if run["stop"] else "completed"
        except Exception as ex:   # noqa: BLE001 - report, never crash the worker
            with _RECON_LOCK:
                run["events"].append({"seq": len(run["events"]) + 1, "type": "error", "error": str(ex)})
            run["status"] = "failed"
    safe_submit(_RECON_EXECUTOR, _work)
    return _json_cors({"status": "started", "run_id": run_id, "decision": decision, "category": category})

@app.route("/api/recon/<run_id>", methods=["GET", "OPTIONS"], strict_slashes=False)
def recon_events(run_id):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    run = _RECON_RUNS.get(run_id)
    if not run:
        return _json_cors({"status": "error", "message": "unknown run"}, 404)
    try:
        since = int(request.args.get("since", 0))
    except ValueError:
        since = 0
    with _RECON_LOCK:
        evs = [e for e in run["events"] if e["seq"] > since]
    return _json_cors({"status": "success", "run_status": run["status"], "category": run["category"], "url": run["url"],
                       "events": evs, "summary": (run["result"] or {}).get("summary")})

@app.route("/api/recon/<run_id>/stop", methods=["POST", "OPTIONS"], strict_slashes=False)
def recon_stop(run_id):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    run = _RECON_RUNS.get(run_id)
    if not run:
        return _json_cors({"status": "error", "message": "unknown run"}, 404)
    run["stop"] = True
    return _json_cors({"status": "success"})

# ═══════════════════════════════════════════════════════
# PEER REVIEW + PREDICTIVE CONTEXT CACHE (Phase 2)
# ═══════════════════════════════════════════════════════
# Review: static checks plus any mesh engine that declares a `review` utility.
# Findings are advisory; a CRITICAL finding holds the commit to the permanent vault
# until you release it (the hold is always on - it does not depend on probation).
# What probation controls is the BACKGROUND reviewer: it only reviews a category on
# its own after you promoted that category and approved "peer_review" in it.
# Cache: read-only local data only; see context_cache.py.
_review_store = _peer_review.ReviewStore() if _peer_review else None
_REVIEW_FILE_CAP = 60
_REVIEW_BYTES_CAP = 400_000

def _review_inputs(category):
    """-> (files {name: text}, signature) for what is staged right now, or (None, None) if unreadable."""
    if staging_area is None:
        return None, None
    ins = staging_area.inspect_category(category)
    if not isinstance(ins, dict) or ins.get("status") != "success":
        return None, None
    listing = (ins.get("files") or [])[:_REVIEW_FILE_CAP]
    sig = _peer_review.signature_of({f["filename"]: f.get("sha256", "") for f in listing})
    files, used = {}, 0
    for f in listing:
        if used >= _REVIEW_BYTES_CAP:
            break
        r = staging_area.read_staged_file(category, f["filename"], max_bytes=min(MAX_REVIEW_FILE, _REVIEW_BYTES_CAP - used))
        if r.get("status") == "success" and r.get("encoding") == "utf-8":
            files[f["filename"]] = r["content"]
            used += len(r["content"])
    return files, sig

MAX_REVIEW_FILE = 256 * 1024

def _engine_reviewers(files):
    return _peer_review.run_engine_reviewers(files, _axis_bridge.find_utility, _axis_bridge.call_utility)

def _run_review(category):
    files, sig = _review_inputs(category)
    if files is None:
        return None
    return _review_store.save(_peer_review.build_report(category, files, sig, engine_reviewers=_engine_reviewers))

def _review_view(category, report, sig):
    return {"report": report, "current_signature": sig,
            "stale": bool(report and sig and report["signature"] != sig),
            "blocking": bool(report and sig and _review_store.is_blocking(category, sig))}

def _review_or_503():
    if _review_store is None or _probation_store is None:
        return _json_cors({"status": "error", "message": "peer_review module not installed"}, 503)
    if staging_area is None:
        return _json_cors({"status": "error", "message": "staging area unavailable"}, 503)
    return None

@app.route("/api/review/<category>", methods=["GET", "OPTIONS"], strict_slashes=False)
def review_get(category):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    unavailable = _review_or_503()
    if unavailable:
        return unavailable
    _, sig = _review_inputs(category)
    if sig is None:
        return _json_cors({"status": "error", "message": "unknown or unreadable category"}, 404)
    rep = _review_store.get(category)
    return _json_cors({"status": "success", **_review_view(category, rep, sig),
                       "decision": _probation_store.decide(category, "peer_review", "read_only")})

@app.route("/api/review/<category>/run", methods=["POST", "OPTIONS"], strict_slashes=False)
def review_run(category):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    unavailable = _review_or_503()
    if unavailable:
        return unavailable
    data = request.get_json(silent=True) or {}
    decision = _probation_store.decide(category, "peer_review", "read_only")
    if decision["action"] == "confirm" and data.get("confirm") is not True:
        return _json_cors({"status": "needs_confirmation", "decision": decision,
                           "message": f"Category '{category}' is {decision['phase']} "
                                      f"({decision['approved']}/{decision['needed']} approvals). Confirm to run the review and teach NEXXUS."})
    rep = _run_review(category)
    if rep is None:
        return _json_cors({"status": "error", "message": "unknown or unreadable category"}, 404)
    if decision["action"] == "confirm":
        _probation_store.observe(category, "peer_review", "approved")
    _, sig = _review_inputs(category)
    return _json_cors({"status": "success", **_review_view(category, rep, sig)})

@app.route("/api/review/<category>/release", methods=["POST", "OPTIONS"], strict_slashes=False)
def review_release(category):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    unavailable = _review_or_503()
    if unavailable:
        return unavailable
    if not os.environ.get("NEXXUS_ADMIN_TOKEN"):
        return _json_cors({"status": "error", "message": "NEXXUS_ADMIN_TOKEN not configured"}, 503)
    if not _admin_ok():
        return _json_cors({"status": "error", "message": "unauthorized"}, 401)
    _, sig = _review_inputs(category)
    result = _review_store.release(category, sig)
    return _json_cors(result, 200 if result.get("status") == "success" else 409)

def _review_daemon_loop(interval):
    """Background reviewer: only for categories YOU promoted and where you approved 'peer_review'."""
    while True:
        time.sleep(interval)
        try:
            cats = (staging_area.list_categories() or {}).get("categories", []) if staging_area else []
            for c in cats:
                name = c.get("category")
                if not name or _probation_store.decide(name, "peer_review", "read_only")["action"] != "auto":
                    continue
                _, sig = _review_inputs(name)
                rep = _review_store.get(name)
                if sig and (not rep or rep["signature"] != sig):
                    _run_review(name)
        except Exception as ex:   # noqa: BLE001 - a bad cycle must never kill the daemon
            print(f"[review-daemon] cycle error: {ex}")

if _review_store is not None and os.environ.get("NEXXUS_DISABLE_REVIEW_DAEMON") != "1":
    threading.Thread(target=_review_daemon_loop, args=(float(os.environ.get("NEXXUS_REVIEW_INTERVAL", "30")),),
                     daemon=True, name="peer-review-daemon").start()

# ---- predictive context cache (read-only local data) ----
def _cache_loader(scope, key):
    if staging_area is None:
        return None
    r = staging_area.read_staged_file(scope, key, max_bytes=256 * 1024)
    if r.get("status") != "success":
        return None
    return {"content": r["content"], "encoding": r.get("encoding"), "truncated": r.get("truncated", False)}

_context_cache = _context_cache_mod.ContextCache(_probation_store, _cache_loader) if (_context_cache_mod and _probation_store) else None

@app.route("/api/context/file", methods=["GET", "OPTIONS"], strict_slashes=False)
def context_file():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    if _context_cache is None:
        return _json_cors({"status": "error", "message": "context cache not installed"}, 503)
    category, name = request.args.get("category", ""), request.args.get("file", "")
    try:
        r = _context_cache.get(category, name)
    except Exception as ex:   # noqa: BLE001
        return _json_cors({"status": "error", "message": str(ex)}, 400)
    if r["value"] is None:
        return _json_cors({"status": "error", "message": "no such staged file", "cache": r["cache"]}, 404)
    return _json_cors({"status": "success", **r["value"], "cache": r["cache"], "predictions": r["predictions"]})

@app.route("/api/context/approve", methods=["POST", "OPTIONS"], strict_slashes=False)
def context_approve():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    if _context_cache is None:
        return _json_cors({"status": "error", "message": "context cache not installed"}, 503)
    d = request.get_json(silent=True) or {}
    if not d.get("category") or not d.get("file"):
        return _json_cors({"status": "error", "message": "category and file are required"}, 400)
    try:
        view = _context_cache.approve(d["category"], d["file"])
    except ValueError as ex:
        return _json_cors({"status": "error", "message": str(ex)}, 400)
    return _json_cors({"status": "success", **view})

@app.route("/api/context/stats", methods=["GET", "OPTIONS"], strict_slashes=False)
def context_stats():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    if _context_cache is None:
        return _json_cors({"status": "error", "message": "context cache not installed"}, 503)
    return _json_cors({"status": "success", **_context_cache.summary()})

@app.route("/api/jobs", methods=["GET", "OPTIONS"])
def jobs_list():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    mgr, err = _jobs_or_503()
    if err:
        return err
    slim = []
    for j in mgr.list(limit=int(request.args.get("limit", 30))):
        slim.append({k: j[k] for k in ("job_id", "kind", "description", "status", "stage", "submitted_at",
                                       "started_at", "finished_at", "elapsed", "event_count", "gate")})
    return _json_cors({"status": "success", "jobs": slim, "queue": mgr.status()})

@app.route("/api/jobs/notifications", methods=["GET", "OPTIONS"])
def jobs_notifications():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    mgr, err = _jobs_or_503()
    if err:
        return err
    since = request.args.get("since")
    try:
        since = int(since) if since is not None else None
    except ValueError:
        since = None
    return _json_cors({"status": "success", **mgr.notifications(since)})

@app.route("/api/jobs/hold", methods=["POST", "OPTIONS"])
def jobs_hold():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    denied = _require_vault_admin()
    if denied:
        return denied
    mgr, err = _jobs_or_503()
    if err:
        return err
    reason = (request.get_json(silent=True) or {}).get("reason", "queue on hold")
    return _json_cors({"status": "success", "queue": mgr.hold(str(reason)[:200])})

@app.route("/api/jobs/release", methods=["POST", "OPTIONS"])
def jobs_release():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    denied = _require_vault_admin()
    if denied:
        return denied
    mgr, err = _jobs_or_503()
    if err:
        return err
    return _json_cors({"status": "success", "queue": mgr.release()})

@app.route("/api/jobs/<job_id>", methods=["GET", "OPTIONS"])
def jobs_detail(job_id):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    mgr, err = _jobs_or_503()
    if err:
        return err
    job = mgr.get(job_id)
    if not job:
        return _json_cors({"status": "error", "message": "unknown job"}, 404)
    return _json_cors({"status": "success", "job": job})

@app.route("/api/jobs/<job_id>/events", methods=["GET", "OPTIONS"])
def jobs_events(job_id):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    mgr, err = _jobs_or_503()
    if err:
        return err
    try:
        since = int(request.args.get("since", 0))
    except ValueError:
        since = 0
    ev = mgr.events(job_id, since)
    if ev is None:
        return _json_cors({"status": "error", "message": "unknown job"}, 404)
    return _json_cors({"status": "success", **ev})

@app.route("/api/vault/ingest", methods=["POST", "OPTIONS"])
def vault_ingest():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    unavailable = _vault_or_503()
    if unavailable:
        return unavailable
    denied = _require_vault_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    result = nexus_module.final_asset_port.route(data)
    return handle_vault_result(result)

@app.route("/api/vault/assets", methods=["GET", "OPTIONS"])
def vault_list():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    unavailable = _vault_or_503()
    if unavailable:
        return unavailable
    build_type = request.args.get("build_type") or None
    return handle_vault_result(nexus_module.final_asset_port.list_assets(build_type=build_type))

@app.route("/api/vault/assets/<asset_id>", methods=["GET", "PATCH", "DELETE", "OPTIONS"])
def vault_asset_detail(asset_id):
    if request.method == "OPTIONS":
        return _cors_options("GET, PATCH, DELETE")
    unavailable = _vault_or_503()
    if unavailable:
        return unavailable

    if request.method == "GET":
        return handle_vault_result(nexus_module.final_asset_port.inspect(asset_id))

    # PATCH and DELETE both mutate the vault - gated behind the shared admin token.
    denied = _require_vault_admin()
    if denied:
        return denied

    if request.method == "PATCH":
        data = request.get_json(silent=True) or {}
        result = nexus_module.final_asset_port.update_metadata(
            asset_id, name=data.get("name"), tags=data.get("tags"), notes=data.get("notes"))
        return handle_vault_result(result)

    # DELETE: destructive, so it requires the caller to echo the asset id back as
    # 'confirm' - a client can't purge something by simply hitting an endpoint it
    # already had a link to; it has to state which id it means to destroy.
    data = request.get_json(silent=True) or {}
    if data.get("confirm") != asset_id:
        res = jsonify({"status": "error", "message": "Purge requires {\"confirm\": \"<asset_id>\"} matching the URL's asset id."})
        response = make_response(res, 400)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return handle_vault_result(nexus_module.final_asset_port.purge(asset_id))

@app.route("/api/vault/assets/<asset_id>/file", methods=["GET", "OPTIONS"])
def vault_asset_file_preview(asset_id):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    unavailable = _vault_or_503()
    if unavailable:
        return unavailable
    member = request.args.get("path")
    if not member:
        res = jsonify({"status": "error", "message": "Query param 'path' (member file path inside the package) is required."})
        response = make_response(res, 400)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    max_bytes = request.args.get("max_bytes", 65536)
    try:
        max_bytes = int(max_bytes)
    except (TypeError, ValueError):
        max_bytes = 65536
    return handle_action_response(nexus_module.final_asset_port.read_member(asset_id, member, max_bytes=max_bytes))

@app.route("/api/vault/assets/<asset_id>/download", methods=["GET", "OPTIONS"])
def vault_asset_download(asset_id):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    unavailable = _vault_or_503()
    if unavailable:
        return unavailable
    info = nexus_module.final_asset_port.package_info(asset_id)
    if info.get("status") != "success":
        res = jsonify(info)
        response = make_response(res, 404 if info.get("code") == "not_found" else 400)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    pkg_path = Path(info["path"])
    response = make_response(send_from_directory(str(pkg_path.parent), pkg_path.name, as_attachment=True,
                                                   download_name=f"{asset_id}.zip"))
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


# ═══════════════════════════════════════════════════════
# CREATIONS HUB + NOTIFICATION HUB
# Creations: the final repository for visuals made in Creation Mode (and files you add by hand), kept completely
# apart from the Final Assets vault and from build output. Notifications: the bell in the top bar - stored on disk,
# never auto-purged, deleted only by the architect. Writes/deletes of Creations need the admin token (same one as
# the vault); reading is open like the vault's listing.
# ═══════════════════════════════════════════════════════
import base64 as _b64
try:
    import creations_vault as _cv_mod
    import notification_store as _ns_mod
    _creations = _cv_mod.CreationsVault(os.environ.get("NEXXUS_CREATIONS_DIR") or (Path(__file__).resolve().parent / "creations_vault"))
    _notes = _ns_mod.NotificationStore(os.environ.get("NEXXUS_NOTIFICATIONS_FILE") or (Path(__file__).resolve().parent / "notifications.json"))
except ImportError as _e:
    _cv_mod = _ns_mod = _creations = _notes = None
    print(f"[BRIDGE WARNING] creations_vault.py / notification_store.py not found - Creations and notifications are off: {_e}")

def _creations_save_artifact(art, prompt, job_id, parent_id=None, instruction=None):
    """Hook for Creation Mode: file a finished, checked page in the Creations hub. Returns the creation id.
    parent_id/instruction are set when this is a refined version of an earlier creation."""
    files = [{"name": f["name"], "data": f["content"].encode("utf-8")} for f in (art.get("files") or [])]
    cid = _creations.save(art.get("title"), files, source="creation", prompt=prompt, job_id=job_id,
                          parent_id=parent_id, instruction=instruction)["id"]
    _creation_last.update(id=cid, at=time.time())
    return cid

def _creations_load(cid):
    """Hook for refine: the page of a stored creation (its html, else its svg), or None."""
    meta = _creations.get(cid)
    if not meta:
        return None
    f = next((x for x in meta["files"] if x["name"].lower().endswith((".html", ".htm"))), None) or \
        next((x for x in meta["files"] if x["name"].lower().endswith(".svg")), None)
    p = _creations.file_path(cid, f["name"]) if f else None
    if p is None:
        return None
    return {"title": meta["title"], "code": p.read_text(encoding="utf-8", errors="replace"), "prompt": meta.get("prompt"),
            "version": meta.get("version", 1), "name": f["name"]}

if _creation is not None and _creations is not None:
    _creation.saver = _creations_save_artifact
    _creation.loader = _creations_load

def _hubs_or_503():
    if _creations is None or _notes is None:
        return _json_cors({"status": "error", "message": "creations_vault.py / notification_store.py are not installed"}, 503)
    return None

@app.route("/api/creations", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def creations_collection():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    unavailable = _hubs_or_503()
    if unavailable:
        return unavailable
    if request.method == "GET":
        return _json_cors({"status": "success", "creations": _creations.list(request.args.get("q") or None)})
    denied = _require_vault_admin()                     # adding a file writes to disk: admin token
    if denied:
        return denied
    if (request.content_length or 0) > 40 * 1024 * 1024:
        return _json_cors({"status": "error", "message": "upload too large (limit about 25 MB per file)"}, 413)
    d = request.get_json(silent=True) or {}
    files = []
    for f in (d.get("files") or []):
        try:
            files.append({"name": f.get("name"), "data": _b64.b64decode(f.get("data_b64") or "", validate=True)})
        except Exception:
            return _json_cors({"status": "error", "message": "a file's data_b64 is not valid base64"}, 400)
    try:
        meta = _creations.save(d.get("title"), files, source=str(d.get("source") or "upload"), prompt=d.get("prompt"), job_id=d.get("job_id"))
    except _cv_mod.CreationError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    _notes.add("creation", "Saved to Creations: " + meta["title"], "%s - %d file(s), %d KB." % (meta["kind"], len(meta["files"]), max(1, meta["total_bytes"] // 1024)),
               "ok", [{"type": "view_creation", "label": "View in Creations", "ref": meta["id"]},
                      {"type": "download", "label": "Download", "ref": "/api/creations/%s/download" % meta["id"]}],
               {"creation_id": meta["id"]}, dedupe_key="creation:" + meta["id"])
    return _json_cors({"status": "success", "creation": meta}, 201)

@app.route("/api/creations/<cid>", methods=["GET", "DELETE", "OPTIONS"], strict_slashes=False)
def creations_item(cid):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, DELETE")
    unavailable = _hubs_or_503()
    if unavailable:
        return unavailable
    if request.method == "GET":
        meta = _creations.get(cid)
        return _json_cors({"status": "success", "creation": meta}) if meta else _json_cors({"status": "error", "message": "unknown creation"}, 404)
    denied = _require_vault_admin()                     # deleting is permanent: admin token + the id echoed back
    if denied:
        return denied
    if (request.get_json(silent=True) or {}).get("confirm") != cid:
        return _json_cors({"status": "error", "message": "Delete requires {\"confirm\": \"<creation id>\"} matching the URL."}, 400)
    try:
        gone = _creations.delete(cid)
    except _cv_mod.CreationError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    return _json_cors({"status": "success", "deleted": cid}) if gone else _json_cors({"status": "error", "message": "unknown creation"}, 404)

@app.route("/api/creations/<cid>/file/<path:name>", methods=["GET", "OPTIONS"])
def creations_file(cid, name):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    unavailable = _hubs_or_503()
    if unavailable:
        return unavailable
    p = _creations.file_path(cid, name)
    if p is None:
        return _json_cors({"status": "error", "message": "unknown file"}, 404)
    ext = p.suffix.lower()
    resp = send_file(str(p), mimetype=_cv_mod.MIME.get(ext, "application/octet-stream"), conditional=True)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "no-store"
    # A saved page/SVG is untrusted (a model wrote it): serve it sandboxed so opening it directly can never act on the dashboard.
    if ext in (".html", ".htm"):
        resp.headers["Content-Security-Policy"] = "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; media-src data:"
    elif ext == ".svg":
        resp.headers["Content-Security-Policy"] = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    return resp

@app.route("/api/creations/<cid>/download", methods=["GET", "OPTIONS"])
def creations_download(cid):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    unavailable = _hubs_or_503()
    if unavailable:
        return unavailable
    meta = _creations.get(cid)
    if not meta:
        return _json_cors({"status": "error", "message": "unknown creation"}, 404)
    name = request.args.get("name") or (meta["files"][0]["name"] if len(meta["files"]) == 1 else None)
    if name:
        p = _creations.file_path(cid, name)
        if p is None:
            return _json_cors({"status": "error", "message": "unknown file"}, 404)
        resp = send_file(str(p), mimetype=_cv_mod.MIME.get(p.suffix.lower(), "application/octet-stream"), as_attachment=True, download_name=p.name)
    else:
        import io as _io
        resp = send_file(_io.BytesIO(_creations.zip_bytes(cid)), mimetype="application/zip", as_attachment=True, download_name=cid + ".zip")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

# ═══════════════════════════════════════════════════════
# MODULE GATEWAY WINDOW (Settings > Modules). The gateway (port 8080) is the shared front door for PICTHIS, the Blog Guy and any
# module dropped into axis-ui-interface. NEXXUS only LOOKS at it (read-only list) and, with the admin token, asks it to wake or
# rest a module. It never runs a module's code. The gateway's problem list contains file paths, so only the owner (admin token) sees it.
# ═══════════════════════════════════════════════════════
_GATEWAY_ADDR = ("127.0.0.1", int(os.environ.get("NEXXUS_GATEWAY_PORT") or 8080))
_MODULE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")

def _gateway_call(method, path, timeout=4):
    import http.client as _hc
    c = _hc.HTTPConnection(_GATEWAY_ADDR[0], _GATEWAY_ADDR[1], timeout=timeout)
    try:
        c.request(method, path, headers={"Host": "localhost"})
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()

@app.route("/api/modules", methods=["GET", "OPTIONS"], strict_slashes=False)
def modules_list():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    try:
        st, raw = _gateway_call("GET", "/_status")
        data = json.loads(raw.decode("utf-8")) if st == 200 else None
    except Exception:
        data = None
    if data is None:
        return _json_cors({"status": "success", "gateway_up": False, "gateway_port": _GATEWAY_ADDR[1], "modules": [], "bridge": None, "problem_count": 0})
    mods = [{k: m.get(k) for k in ("name", "type", "hostnames", "state", "keep_running", "idle_minutes", "started_by_gateway", "error", "nexxus")} for m in data.get("modules", [])]
    out = {"status": "success", "gateway_up": True, "gateway_port": _GATEWAY_ADDR[1], "modules": mods, "bridge": data.get("bridge"),
           "problem_count": len(data.get("problems") or [])}
    if _admin_ok():
        out["problems"] = data.get("problems") or []
    return _json_cors(out)

@app.route("/api/modules/<name>/<action>", methods=["POST", "OPTIONS"])
def modules_action(name, action):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin()
    if denied:
        return denied
    if action not in ("start", "stop") or not _MODULE_NAME.match(name):
        return _json_cors({"status": "error", "message": "unknown module action"}, 400)
    try:
        st, raw = _gateway_call("GET", "/_status")
        known = {m.get("name") for m in json.loads(raw.decode("utf-8")).get("modules", [])} if st == 200 else set()
        if name not in known:
            return _json_cors({"status": "error", "message": "unknown module"}, 404)
        st, raw = _gateway_call("POST", "/_%s/%s" % (action, name))
    except Exception as e:
        return _json_cors({"status": "error", "message": "the gateway is not reachable (%s)" % type(e).__name__}, 502)
    return _json_cors({"status": "success" if st in (200, 202) else "error", "gateway_status": st})

@app.route("/api/consult/status", methods=["GET"])
def consult_status():
    """Owner-only view of the consultant network (what is on, today's usage, the private log's tail). Anyone without the
    admin token gets the same plain 404 as a route that does not exist - the layer is invisible from outside."""
    if not _admin_ok():
        from flask import abort as _abort
        _abort(404)
    try:
        import consult_client as _cc
        st = _cc.status()
    except Exception:
        st = None
    return _json_cors({"status": "success", "consult": st})

@app.route("/api/creation/refine", methods=["POST", "OPTIONS"])
def creation_refine():
    """The panel's Refine bar: start a background refine job on a saved creation (parent_id) or on page code (code)."""
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if _creation is None or _mode_state is None or _job_manager is None:
        return _json_cors({"status": "error", "message": "Creation mode is not available"}, 503)
    if _mode_state.mode != "creation":
        return _json_cors({"status": "error", "message": "Refining uses the code model: switch to Creation mode first."}, 409)
    d = request.get_json(silent=True) or {}
    instruction = str(d.get("instruction") or "").strip()
    if not instruction:
        return _json_cors({"status": "error", "message": "Describe the change you want."}, 400)
    if len(instruction) > _creation.MAX_INSTRUCTION:                  # refused out loud: a request is never silently cut short
        return _json_cors({"status": "error", "message": "That change request is %d characters and the limit is %d. Shorten it, or make the changes one at a time." % (len(instruction), _creation.MAX_INSTRUCTION)}, 413)
    parent_id, code = d.get("parent_id") or None, d.get("code") or None
    if parent_id and not (_cv_mod is not None and _cv_mod.ID_RE.match(str(parent_id))):
        return _json_cors({"status": "error", "message": "not a valid creation id"}, 400)
    if not parent_id and not code:
        return _json_cors({"status": "error", "message": "Nothing to refine: give a creation id or the page code."}, 400)
    if code and len(str(code).encode("utf-8")) > _creation.MAX_REFINE_BYTES:
        return _json_cors({"status": "error", "message": "That page is too large to refine on this machine."}, 413)
    if parent_id and _creations is not None and _creations.get(parent_id) is None and not code:
        return _json_cors({"status": "error", "message": "That creation is no longer in the Creations hub."}, 404)
    try:
        job = _start_refine_job(parent_id=parent_id, code=(str(code) if code else None), instruction=instruction,
                                title=(str(d.get("title"))[:120] if d.get("title") else None), prompt=(str(d.get("prompt"))[:2000] if d.get("prompt") else None))
    except Exception as e:
        return _json_cors({"status": "error", "message": "%s: %s" % (type(e).__name__, e)}, 500)
    pm = _creations.get(parent_id) if (parent_id and _creations is not None) else None
    try:
        title = _creation._next_title((pm or {}).get("title") or d.get("title"), int((pm or {}).get("version", 1)))
    except Exception as e:                            # naming.NamingError: nothing says what this creation is
        return _json_cors({"status": "error", "message": str(e)}, 400)
    return _json_cors({"status": "success", "creation_job": {"job_id": job["job_id"], "title": title, "prompt": instruction, "parent_id": parent_id}})

@app.route("/api/notifications", methods=["GET", "OPTIONS"], strict_slashes=False)
def notifications_list():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    unavailable = _hubs_or_503()
    if unavailable:
        return unavailable
    return _json_cors({"status": "success", **_notes.list()})

@app.route("/api/notifications/read", methods=["POST", "OPTIONS"])
def notifications_read():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    unavailable = _hubs_or_503()
    if unavailable:
        return unavailable
    d = request.get_json(silent=True) or {}
    ids = None if d.get("all") else set(d.get("ids") or [])
    return _json_cors({"status": "success", "marked": _notes.mark_read(ids), **{k: v for k, v in _notes.list().items() if k == "unread"}})

@app.route("/api/notifications/clear", methods=["POST", "OPTIONS"])
def notifications_clear():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    unavailable = _hubs_or_503()
    if unavailable:
        return unavailable
    if (request.get_json(silent=True) or {}).get("confirm") != "clear all":
        return _json_cors({"status": "error", "message": "Clearing needs {\"confirm\": \"clear all\"}."}, 400)
    return _json_cors({"status": "success", "cleared": _notes.clear()})

@app.route("/api/notifications/<nid>", methods=["DELETE", "OPTIONS"])
def notifications_delete(nid):
    if request.method == "OPTIONS":
        return _cors_options("DELETE")
    unavailable = _hubs_or_503()
    if unavailable:
        return unavailable
    return _json_cors({"status": "success", "deleted": nid}) if _notes.delete(nid) else _json_cors({"status": "error", "message": "unknown notification"}, 404)

# ═══════════════════════════════════════════════════════
# HUMAN-IN-THE-LOOP CODE INGESTION  (scout -> staging_vault -> briefing -> owner approval -> tools_vault -> callable)
# Nothing downloaded is ever imported, installed or run here. Fetching is GitHub-only and pinned to a commit; the briefing is computed
# by reading the code; only the owner (admin token) can approve; an approved tool runs only in a locked-down child process.
# See tool_scout.py / tool_analyzer.py / tool_vault.py / tool_sandbox.py.
# ═══════════════════════════════════════════════════════
try:
    import tool_scout as _scout
    import tool_vault as _tools
except Exception as _e_tools:                       # the rest of NEXXUS must still run without it
    _scout = _tools = None
    print("[TOOLS] ingestion unavailable: %s: %s" % (type(_e_tools).__name__, _e_tools))
try:
    import nexxus_external as _ext
except Exception:
    _ext = None
try:                                                 # the axis gate: signed manifests, packet checks, drift watch (project-X/axis_gate)
    _px = str(Path(__file__).resolve().parent / "axis-ui-interface" / "project-X")
    if _px not in sys.path:
        sys.path.insert(0, _px)
    import axis_gate as _gate
except Exception as _e_gate:
    _gate = None
    print("[axis gate] unavailable: %s: %s" % (type(_e_gate).__name__, _e_gate))

_ingest = {"busy": False, "last": 0.0, "lock": threading.Lock(), "done": {}}     # one fetch at a time, spaced out
_TOOL_NAME_RX = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

def _tools_or_503():
    if _tools is None or _scout is None:
        return _json_cors({"status": "error", "message": "tool ingestion is not available"}, 503)
    return None

def _briefing_text(b):
    f = b["facts"]
    lines = ["Briefing for %s (commit %s). Risk: %s%s." % (f["name"], f["commit"][:7], f["risk_level"].upper(), " - it cannot be ingested" if f["blocked"] else ""),
             f["plain_summary"], "Licence: %s." % f["license"]["spdx"]]
    for r in f["risks"]:
        if r["level"] != "info":
            lines.append("  [%s] %s" % (r["level"].upper(), r["text"]))
    expo = [x for x in f["functions"] if x["exposable"]]
    if expo:
        lines.append("Functions it could offer: " + "; ".join("%s(%s)" % (x["name"], ", ".join(p["name"] for p in x["params"])) for x in expo[:8]))
    prov = f.get("provisioning") or {}
    pip = prov.get("pip") or {}
    if pip.get("command"):
        lines.append("To install what it needs, run this yourself (NEXXUS never installs anything), then press Re-check in the briefing:")
        lines.append("    " + pip["command"])
        for pk in pip.get("packages", []):
            lines.append("    - %s: %s  [%s]" % (pk["pip"], pk["check_url"], pk["source"]))
    for k in prov.get("keys", []):
        lines.append("It needs an API key%s%s. %s: %s" % (" (%s)" % k["service"] if k.get("service") else "", " read as %s" % k["env"] if k.get("env") else "", k["link_kind"].capitalize(), k["link"]))
    if prov.get("keys"):
        lines.append("Then put the key in the left panel (API Key Ingestion) and grant it to the tool after you approve it. The briefing has a button that fills the name for you.")
    pl = b.get("pipeline")
    if pl:
        lines.append("Intake pipeline (Inspect, Heal, Gate, Contribute): axis gate %s. %s" % (pl["verdict"].upper(), (
            "%d small correction(s) were needed to make it parse; the upstream files are kept untouched beside the working copy, and what you are briefed on is the corrected copy." % pl["fixes"]) if pl["fixes"]
            else "It parsed cleanly as published; nothing was changed."))
        for fx in pl.get("fix_list", [])[:6]:
            lines.append("    - %s%s: %s (%s)" % (fx["file"], (" line %s" % fx["line"]) if fx.get("line") else "", fx["stopped_at"], fx["fix"]))
        if pl.get("has_letter"):
            lines.append("A private note for the original author is ready for you to review in the briefing. NEXXUS has not sent it and never will; you decide whether to.")
    lines.append("Nothing has been installed or run. It is parked in the staging vault.")
    if f["blocked"]:
        lines.append("I will not ingest this one. You can reject it in the Tools panel.")
    else:
        lines.append("Do you want me to ingest and integrate this tool? Open the briefing, tick what to allow and approve (it needs your admin token).")
    return "\n".join(lines)

def _ingest_worker(owner, repo, ref, out):
    try:
        b = _tools.stage(owner, repo, ref)
        out["brief"] = b
        f = b["facts"]
        _notes.add("tool", "Briefing ready: " + f["name"], "Risk %s. %d function(s) could be offered. Nothing has been installed or run." % (f["risk_level"].upper(), len([x for x in f["functions"] if x["exposable"]])),
                   "fail" if f["blocked"] else "info", [{"type": "review_briefing", "label": "Review briefing", "ref": b["id"]}], {"staging_id": b["id"]},
                   dedupe_key="stage:%s:%s" % (b["id"], f["commit"]))
    except Exception as e:
        out["error"] = str(e) if isinstance(e, (_scout.ScoutError, _tools.VaultError)) else "%s: %s" % (type(e).__name__, str(e)[:200])
        if "axis gate blocked" in out["error"]:                    # the pipeline stopped it before staging: say so where you will see it
            _notes.add("tool", "Blocked at the axis gate: %s/%s" % (owner, repo), out["error"], "fail", [{"type": "open_tools", "label": "Open Tools", "ref": ""}],
                       {"blocked": "%s/%s" % (owner, repo)}, dedupe_key="blocked:%s/%s:%s" % (owner, repo, ref or ""))
    finally:
        out["done"] = True
        _ingest["busy"] = False

def _ingest_start(target):
    """-> (state dict, error text). Starts a background fetch+analyse; the dict gains 'brief'/'error'/'done'."""
    with _ingest["lock"]:
        if _ingest["busy"]:
            return None, "A tool is already being fetched. Give it a moment."
        if time.time() - _ingest["last"] < 8:
            return None, "Please wait a few seconds between fetches."
        try:
            owner, repo, ref = _scout.parse_target(target)
        except _scout.ScoutError as e:
            return None, str(e)
        _ingest.update(busy=True, last=time.time())
    out = {"done": False, "target": "%s/%s" % (owner, repo)}
    t = threading.Thread(target=_ingest_worker, args=(owner, repo, ref, out), daemon=True, name="nexxus-ingest")
    out["thread"] = t
    t.start()
    return out, None

def _tools_chat_reply(text):
    """Chat commands for the ingestion pipeline. -> (reply, extras) or None."""
    if _tools is None or _scout is None:
        return None
    t = (text or "").strip()
    m = re.match(r"^(?:please\s+)?(?:find|search for|look for|scout|get me|(?:i|we)\s+need)\s+(?:me\s+)?(?:an?\s+|some\s+)?(?:open[- ]source\s+|free\s+)?(?:tool|skill|script|library|package|repo|repository)s?\s+(?:to|that|for|which|who)\s+(.{3,200})$", t, re.I)
    if m:
        try:
            found = _scout.search(m.group(1))
        except Exception as e:
            return "I could not search GitHub: %s" % (e if isinstance(e, _scout.ScoutError) else type(e).__name__), {}
        if not found:
            return "I found nothing suitable on GitHub for that. Try different words.", {}
        lines = ["Here is what I found (public Python projects, permissive licences first). Nothing has been downloaded yet:"]
        for r in found:
            lines.append("- %s  [%s, %s stars] %s" % (r["full_name"], r["license"] or "no licence", r["stars"], (r["description"] or "")[:110]))
        lines.append("Pick one to fetch into the staging vault. I will read it, brief you, and ask before anything is integrated.")
        return "\n".join(lines), {"question": {"question_id": "ingest-" + uuid.uuid4().hex[:8], "prompt": "Fetch which one?", "pending_action": "ingest",
                                               "options": [{"id": "r%d" % i, "label": "ingest " + r["full_name"]} for i, r in enumerate(found)]}}
    m = re.match(r"^(?:ingest|stage|fetch tool)\s+(\S+)\s*$", t, re.I)
    if m:
        out, err = _ingest_start(m.group(1))
        if err:
            return err, {}
        out["thread"].join(timeout=40)
        if not out.get("done"):
            return "I am still fetching and reading %s. The briefing will appear in your notification bell when it is ready. Nothing runs meanwhile." % out["target"], {}
        if out.get("error"):
            return "I could not stage %s: %s" % (out["target"], out["error"]), {}
        return _briefing_text(out["brief"]), {"tool_briefing": {"id": out["brief"]["id"]}}
    if re.match(r"^(?:list|show)\s+(?:my\s+|the\s+|all\s+)?(?:ingested\s+)?tools\s*$", t, re.I):
        tl = _tools.list_tools()
        if not tl:
            return "No tools have been ingested yet. Say \"find a tool to <what you need>\" to start.", {}
        return "Ingested tools:\n" + "\n".join("- %s%s: %s (from %s)" % (x["name"], "" if x["enabled"] else " [off]", x["description"][:90], x["source"]) for x in tl), {}
    if re.match(r"^(?:list|show)\s+(?:staged|pending)\s+(?:tools|briefings|downloads)\s*$", t, re.I):
        st = _tools.list_staged()
        if not st:
            return "Nothing is waiting in the staging vault.", {}
        return "Waiting for your decision:\n" + "\n".join("- %s: risk %s, %d function(s)" % (s["name"], s["risk_level"].upper(), s["functions"]) for s in st), {"tool_briefing": {"id": st[0]["id"]}}
    m = re.match(r"^run tool\s+([a-z][a-z0-9_]{2,63})\s*(\{.*\})?\s*$", t, re.I | re.S)
    if m:
        rec = next((x for x in _tools.list_tools() if x["name"] == m.group(1).lower()), None)
        if rec is None:
            return "There is no tool called %s. Say \"list tools\" to see them." % m.group(1)[:40], {}
        if rec["permissions"].get("network") or rec["permissions"].get("subprocess"):
            return "%s was given network/program access, so it can only be run from the Tools panel with your admin token." % rec["name"], {}
        try:
            args = json.loads(m.group(2)) if m.group(2) else {}
        except ValueError:
            return "The arguments must be JSON, for example: run tool %s {\"text\": \"hello\"}" % rec["name"], {}
        r = _tools.call(rec["name"], args, caller="owner-chat")
        return ("Result of %s (%d ms): %s" % (rec["name"], r["ms"], json.dumps(r.get("value"), default=str)[:1500])) if r["ok"] else ("%s failed: %s" % (rec["name"], r.get("error"))), {}
    return None

# ---- ORCHESTRATOR BUS: NEXXUS <-> engine orchestrators (see ORCHESTRATOR_BUS.md) ----
# Orders and accepting need the admin token. Messages FROM an engine's orchestrator need no token: they are authenticated by their signature
# (HMAC with NEXXUS_GOVERNANCE_SECRET), single use, and only a registered orchestrator can speak. Silos can never use this door.
try:
    import orchestrator_bus as _obus
except Exception as _e:
    _obus = None
    print(f"[BRIDGE WARNING] orchestrator_bus.py not available - the orchestrator bus is off: {_e}")
_bus_holder = {"bus": None}
_bus_lock = threading.Lock()

def _bus():
    with _bus_lock:
        if _bus_holder["bus"] is None:
            ledger = os.environ.get("NEXXUS_BUS_LEDGER") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "orchestrator_ledger.jsonl")
            b = _obus.OrchestratorBus(ledger)
            def _not_empty(order, path):          # NEXXUS's own minimum check at accept time
                return [] if os.path.getsize(path) > 0 else [{"severity": "critical", "message": "the artifact is empty"}]
            b.nexxus_checks.append(_not_empty)
            _bus_holder["bus"] = b
        return _bus_holder["bus"]

def _bus_do(fn, ok_code=200):
    if _obus is None:
        return _json_cors({"status": "error", "message": "the orchestrator bus is not installed"}, 503)
    try:
        return _json_cors({"status": "success", **fn(_bus())}, ok_code)
    except _obus.BusError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)

@app.route("/api/bus/register", methods=["POST", "OPTIONS"])
def bus_register():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin()
    if denied:
        return denied
    d = request.get_json(silent=True) or {}
    def run(b):
        if not d.get("engine") or not d.get("orchestrator"):
            raise _obus.BusError("engine and orchestrator are required")
        b.register_orchestrator(str(d["engine"]), str(d["orchestrator"]), bool(d.get("qc_reviewer")), bool(d.get("auditor")))
        return {"registered": {"engine": d["engine"], "orchestrator": d["orchestrator"], "qc_reviewer": bool(d.get("qc_reviewer")), "auditor": bool(d.get("auditor"))}}
    return _bus_do(run)

@app.route("/api/bus/order", methods=["POST", "OPTIONS"])
def bus_order():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin()
    if denied:
        return denied
    d = request.get_json(silent=True) or {}
    return _bus_do(lambda b: {"order": b.send_order(str(d.get("engine") or ""), str(d.get("to") or ""), d.get("spec") or {})}, 201)

@app.route("/api/bus/message", methods=["POST", "OPTIONS"])
def bus_message():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    env = request.get_json(silent=True) or {}
    def run(b):
        order = b.receive(env)
        if "audit_n" in order or "audit_cursor" in order:
            return order                                  # an audit report or an auditor's confirmation: there is no order to describe
        if _notes is not None and order.get("state") in ("BUILT", "QC_PASSED"):
            _notes.add("info", "Order %s is %s" % (order["id"], order["state"]), "%s reported through its orchestrator. NEXXUS accepts only after quality control passes and its own checks agree." % order["engine"],
                       "info", [], {"order_id": order["id"]}, dedupe_key="bus:%s:%s" % (order["id"], order["state"]))
        return {"order": b.status(order["id"])}
    return _bus_do(run)

@app.route("/api/bus/poll", methods=["POST", "OPTIONS"])
def bus_poll():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    env = request.get_json(silent=True) or {}
    return _bus_do(lambda b: {"orders": b.poll(env)})

@app.route("/api/bus/accept", methods=["POST", "OPTIONS"])
def bus_accept():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin()
    if denied:
        return denied
    d = request.get_json(silent=True) or {}
    def run(b):
        order = b.accept(str(d.get("order_id") or ""))
        if _notes is not None:
            _notes.add("info", "Order %s accepted" % order["id"], "Quality control passed and NEXXUS's own checks agreed.", "ok", [], {"order_id": order["id"]}, dedupe_key="bus:%s:ACCEPTED" % order["id"])
        return {"order": b.status(order["id"]), "delivered": _deliver_order(b, order["id"])}
    return _bus_do(run)


def _deliver_order(bus, order_id):
    """An ACCEPTED build is delivered to where the page can show it: images, pages and video go into the Creations hub (which has the viewers), so the finished product is in front of the owner
    without a manual step. Nothing is invented on the way: the title must come from the order itself (the naming rule), and a file the hub cannot hold (type, size) is reported as not delivered,
    with the reason, and left where it is. -> {"creation_id": ...} or {"skipped": reason}."""
    if _creations is None or _cv_mod is None:
        return {"skipped": "the Creations hub is not available"}
    o = bus.orders.get(order_id) or {}
    path = o.get("artifact")
    if not path or not os.path.isfile(path):
        return {"skipped": "the order has no artifact file"}
    spec = o.get("spec") if isinstance(o.get("spec"), dict) else {}
    title = next((str(spec[k]).strip() for k in ("title", "make", "prompt", "topic") if spec.get(k)), "")
    if _creation is None or not title or not _creation.naming.check_name(title)[0]:
        return {"skipped": "the order does not say what it is (give it a title, make, prompt or topic): NEXXUS does not invent stand-in names"}
    try:
        with open(path, "rb") as f:
            data = f.read(_cv_mod.MAX_FILE_BYTES + 1)
        meta = _creations.save(title[:120], [{"name": os.path.basename(path), "data": data}], source="order from %s" % o.get("engine"), prompt=json.dumps(spec, sort_keys=True)[:2000], job_id=order_id)
    except _cv_mod.CreationError as e:
        return {"skipped": str(e)}
    except OSError as e:
        return {"skipped": "the artifact could not be read: %s" % e}
    if _notes is not None:
        _notes.add("creation", "Delivered to Creations: " + meta["title"], "%s from order %s - %d KB." % (meta["kind"], order_id, max(1, meta["total_bytes"] // 1024)), "ok",
                   [{"type": "view_creation", "label": "View in Creations", "ref": meta["id"]}], {"creation_id": meta["id"]}, dedupe_key="creation:" + meta["id"])
    out = {"creation_id": meta["id"], "title": meta["title"], "kind": meta["kind"]}
    pub = spec.get("publish")
    if isinstance(pub, dict) and meta["kind"] == "video":          # a content trigger: the order asked for publishing. It is only STAGED: the owner approves, and nothing is sent without that.
        try:
            out["staged_for_publishing"] = _publish.stage(meta["id"], pub.get("title") or title, pub.get("description", ""), pub.get("tags") or [], pub.get("topic", ""), "private", source="order %s" % order_id)["id"]
        except Exception as e:
            out["publish_skipped"] = str(e)
    return out

@app.route("/api/bus/orders", methods=["GET", "OPTIONS"])
def bus_orders():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _require_vault_admin()
    if denied:
        return denied
    return _bus_do(lambda b: {"orders": [b.status(i) for i in b.orders], "orchestrators": b.orchestrators, "qc_reviewers": sorted(b.qc_reviewers)})

@app.route("/api/bus/verify", methods=["GET", "OPTIONS"])
def bus_verify():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _require_vault_admin()
    if denied:
        return denied
    def run(b):
        ok, info = b.verify_ledger()
        return {"ledger_ok": ok, "entries" if ok else "first_bad_entry": info}
    return _bus_do(run)

# ---- NEEDS: NEXXUS asks before it fetches anything ----
# A "need" is a request that NEXXUS (or you, from the left panel) wants something it does not have. The search is read-only; nothing is downloaded
# until you say yes. Critical needs (a build is blocked) wait in the notification bell; the rest pop up as a yes/no question.
_NEEDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "needs.json")
_needs_lock = threading.Lock()

def _needs_load():
    try:
        with open(_NEEDS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []

def _needs_save(items):
    tmp = _NEEDS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        pending = [n for n in items if n.get("status") == "pending"]            # a waiting request is never dropped
        rest = [n for n in items if n.get("status") != "pending"][-200:]
        json.dump(sorted(pending + rest, key=lambda n: n.get("ts", 0)), f, indent=1)
    os.replace(tmp, _NEEDS_FILE)

def request_need(query, why="", critical=False, source="nexxus"):
    """-> the need record (existing one if the same ask is pending or was answered in the last 24 h, so NEXXUS never nags), or None."""
    q = " ".join(str(query or "").split())[:200]
    if len(q) < 3 or _tools is None or _scout is None:
        return None
    key = q.lower()
    with _needs_lock:
        for n in _needs_load():
            if n.get("key") == key and (n.get("status") == "pending" or time.time() - n.get("ts", 0) < 86400):
                return n
    try:
        found = _scout.search(q)
        search_note = ""
    except Exception as e:
        found, search_note = [], "GitHub search failed (%s)." % type(e).__name__
    if not found and not critical:
        return None
    if not found:
        search_note = search_note or "Nothing suitable was found automatically."
    best = next((r for r in found if r.get("permissive")), found[0]) if found else None
    need = {"id": "need_" + uuid.uuid4().hex[:8], "key": key, "ts": time.time(), "query": q, "why": str(why or "")[:300], "critical": bool(critical), "source": source,
            "candidate": ({k: best.get(k) for k in ("full_name", "license", "permissive", "stars", "description")} if best else None), "note": search_note, "status": "pending",
            "candidates": [{k: r.get(k) for k in ("full_name", "license", "permissive", "stars", "description")} for r in ([best] + [x for x in found if x is not best])[:3]] if best else []}
    with _needs_lock:
        items = _needs_load(); items.append(need); _needs_save(items)
    if need["critical"] and _notes is not None:
        c = need["candidate"]
        detail = ("Best match: %s (%s, %s stars). Nothing is downloaded until you accept." % (c["full_name"], c["license"] or "no licence", c["stars"])) if c else (search_note + " Use Look it up in the left panel, or tell me where to get it.")
        _notes.add("need", "NEXXUS needs: " + q[:80], "%s %s" % (need["why"] or "A task is blocked without it.", detail),
                   "info", [{"type": "review_need", "label": "Review", "ref": need["id"]}], {"need_id": need["id"]}, dedupe_key="need:" + need["id"])
    return need

@app.route("/api/needs", methods=["GET", "POST", "OPTIONS"])
def needs_collection():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    if request.method == "GET":
        with _needs_lock:
            return _json_cors({"status": "success", "needs": [n for n in _needs_load() if n.get("status") == "pending"]})
    d = request.get_json(silent=True) or {}
    need = request_need(d.get("query"), d.get("why", ""), bool(d.get("critical")), source="owner")
    if not need:
        return _json_cors({"status": "error", "message": "Nothing suitable found for that (or GitHub did not answer). Try different words."}, 404)
    return _json_cors({"status": "success", "need": need})

@app.route("/api/needs/<nid>/decide", methods=["POST", "OPTIONS"])
def needs_decide(nid):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    accept = bool(body.get("accept"))
    with _needs_lock:
        items = _needs_load()
        need = next((n for n in items if n.get("id") == nid and n.get("status") == "pending"), None)
        if need is None:
            return _json_cors({"status": "error", "message": "That request is not waiting any more."}, 404)
        if not accept:
            need["status"] = "rejected"; _needs_save(items)
            return _json_cors({"status": "success", "decision": "rejected"})
        if not need.get("candidate"):
            return _json_cors({"status": "error", "message": "No match was found for this one. Use Look it up in the left panel with a link or other words; this request stays on the list."}, 409)
    allowed = [c["full_name"] for c in (need.get("candidates") or [need["candidate"]])]
    chosen = str(body.get("repo") or allowed[0])
    if chosen not in allowed:
        return _json_cors({"status": "error", "message": "That is not one of the matches I offered."}, 400)
    out, err = _ingest_start(chosen)
    if err:
        return _json_cors({"status": "error", "message": err}, 409)
    with _needs_lock:
        items = _needs_load()
        for n in items:
            if n.get("id") == nid:
                n["status"] = "accepted"
        _needs_save(items)
    return _json_cors({"status": "success", "decision": "accepted", "started": out["target"], "note": "Fetching into the staging vault; a briefing notification follows. Nothing is run."}, 202)

@app.route("/api/ingest/scout", methods=["POST", "OPTIONS"])
def ingest_scout():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    obj = str((request.get_json(silent=True) or {}).get("objective") or "").strip()[:200]
    if len(obj) < 3:
        return _json_cors({"status": "error", "message": "Describe what the tool should do."}, 400)
    try:
        return _json_cors({"status": "success", "results": _scout.search(obj)})
    except _scout.ScoutError as e:
        return _json_cors({"status": "error", "message": str(e)}, 502)

@app.route("/api/ingest/fetch", methods=["POST", "OPTIONS"])
def ingest_fetch():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    out, err = _ingest_start(str((request.get_json(silent=True) or {}).get("target") or ""))
    if err:
        return _json_cors({"status": "error", "message": err}, 409 if "already" in err or "wait" in err else 400)
    return _json_cors({"status": "success", "started": out["target"], "note": "A notification appears when the briefing is ready."}, 202)

@app.route("/api/ingest/staged", methods=["GET", "OPTIONS"])
def ingest_staged():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    return _json_cors({"status": "success", "staged": _tools.list_staged(), "fetching": _ingest["busy"]})

@app.route("/api/ingest/<sid>", methods=["GET", "OPTIONS"])
def ingest_briefing(sid):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    try:
        return _json_cors({"status": "success", "briefing": _tools.briefing(sid)})
    except _tools.VaultError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)

@app.route("/api/ingest/<sid>/approve", methods=["POST", "OPTIONS"])
def ingest_approve(sid):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    d = request.get_json(silent=True) or {}
    if d.get("confirm") != sid:
        return _json_cors({"status": "error", "message": "Approving needs {\"confirm\": \"%s\"}." % sid}, 400)
    try:
        res = _tools.approve(sid, str(d.get("briefing_sha256") or ""), d.get("functions") or [], d.get("grants") or {}, approver="owner")
    except _tools.VaultError as e:
        return _json_cors({"status": "error", "message": str(e)}, 409)
    _notes.add("tool", "Tool integrated: " + ", ".join(res["tools"][:3]), "Callable right now by NEXXUS, PICTHIS and the other engines. No restart was needed.", "ok",
               [{"type": "open_tools", "label": "Open Tools", "ref": res["id"]}], {"tools_id": res["id"]}, dedupe_key="approved:" + res["id"])
    return _json_cors({"status": "success", **res})

@app.route("/api/ingest/<sid>/contribution", methods=["GET", "OPTIONS"])
def ingest_contribution(sid):
    """The private note to the original author for this staged asset (admin token). Read-only: NEXXUS never sends it; the confirmations are what YOU must be able to say before you do."""
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    try:
        return _json_cors({"status": "success", **_tools.contribution(sid)})
    except _tools.VaultError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)

@app.route("/api/ingest/<sid>/reject", methods=["POST", "OPTIONS"])
def ingest_reject(sid):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    if (request.get_json(silent=True) or {}).get("confirm") != sid:
        return _json_cors({"status": "error", "message": "Rejecting needs {\"confirm\": \"%s\"}." % sid}, 400)
    try:
        _tools.reject(sid)
    except _tools.VaultError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)
    return _json_cors({"status": "success", "rejected": sid})

@app.route("/api/ingest/<sid>/explain", methods=["POST", "OPTIONS"])
def ingest_explain(sid):
    """Optional: ask the local model for a plain-English paragraph. It sees only the computed facts (never the code or the README) and its text is labelled."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    try:
        b = _tools.briefing(sid)
    except _tools.VaultError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)
    f = b["facts"]
    facts = "Permissions found: %s. Concerns: %s. Functions: %s." % (
        ", ".join(k for k, v in f["permissions"].items() if v) or "none",
        "; ".join(r["text"] for r in f["risks"] if r["level"] != "info") or "none",
        ", ".join("%s - %s" % (x["name"], x["doc"] or "no description") for x in f["functions"][:10]) or "none")
    prompt = ("You explain software to a non-programmer. Using ONLY these facts, write 3 short plain sentences: what the tool seems to do, and what to be careful about. "
              "Do not invent anything. Facts: " + facts)
    try:
        import llm_router as _llm
        text = _llm.generate(prompt, timeout=120, max_tokens=220, temperature=0.2)
    except Exception as e:
        return _json_cors({"status": "error", "message": "The local model could not be reached (%s)." % type(e).__name__}, 503)
    _tools.attach_summary(sid, text)
    return _json_cors({"status": "success", "ai_summary": _tools.briefing(sid)["ai_summary"], "label": "Written by the local AI from the facts above. It may be wrong; approve based on the facts."})

@app.route("/api/ingest/<sid>/recheck", methods=["POST", "OPTIONS"])
def ingest_recheck(sid):
    """After you ran the pip command from the briefing: read the same staged files again and refresh the briefing (no new download)."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    try:
        b = _tools.recheck(sid)
    except _tools.VaultError as e:
        return _json_cors({"status": "error", "message": str(e)}, 409)
    return _json_cors({"status": "success", "briefing": b})

@app.route("/api/tools", methods=["GET", "OPTIONS"], strict_slashes=False)
def tools_list():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    unavailable = _tools_or_503()
    if unavailable:
        return unavailable
    return _json_cors({"status": "success", "tools": _tools.list_tools()})

@app.route("/api/tools/<name>/<action>", methods=["POST", "OPTIONS"])
def tools_toggle(name, action):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    if action not in ("enable", "disable") or not _TOOL_NAME_RX.match(name):
        return _json_cors({"status": "error", "message": "unknown tool action"}, 400)
    try:
        _tools.set_enabled(name, action == "enable")
    except _tools.VaultError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)
    return _json_cors({"status": "success", "tool": name, "enabled": action == "enable"})

@app.route("/api/tools/package/<pid>", methods=["DELETE", "OPTIONS"])
def tools_remove(pid):
    if request.method == "OPTIONS":
        return _admin_cors_options("DELETE")
    denied = _require_vault_admin() or _tools_or_503()
    if denied:
        return denied
    if (request.get_json(silent=True) or {}).get("confirm") != pid:
        return _json_cors({"status": "error", "message": "Removing needs {\"confirm\": \"%s\"}." % pid}, 400)
    try:
        _tools.remove_package(pid)
    except _tools.VaultError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)
    return _json_cors({"status": "success", "removed": pid})

def _module_caller(d):
    """Who is calling a tool? The owner (admin token), or a connected module that signed the packet with its own nexxus.secret.
    -> (caller, error text). The signature covers the tool name and arguments, is valid for 60 s and only once."""
    if _admin_ok():
        return "owner", None
    sig, origin, ts = d.get("signature"), str(d.get("origin") or ""), d.get("ts")
    if _ext is None or not origin.startswith("MODULE:") or not isinstance(sig, str) or not isinstance(ts, (int, float)) or isinstance(ts, bool):
        return None, "unauthorised"
    name = origin[7:]
    if not re.match(r"^[a-z0-9_-]{1,40}$", name) or not _ext.is_external(name):
        return None, "unauthorised"
    key = _ext._secret(name)
    if not key or _gate is None:
        return None, "unauthorised"
    v = _gate.check_packet(d, key, {origin}, source=origin, channel="BUS", max_age=60)     # signature + freshness + single use, logged by the axis gate
    if not v.allow:
        return None, "unauthorised"
    return "MODULE:" + name, None

@app.route("/api/tools/call", methods=["POST", "OPTIONS"])
def tools_call():
    """Call an approved tool. Owner: admin token. A module: a signed packet {origin:'MODULE:<name>', ts, tool, args, signature}."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    unavailable = _tools_or_503()
    if unavailable:
        return unavailable
    d = request.get_json(silent=True) or {}
    caller, err = _module_caller(d)
    if err:
        from flask import abort as _abort
        _abort(404)                                    # an unauthenticated caller learns nothing, not even that this exists
    tool = str(d.get("tool") or "")
    if not _TOOL_NAME_RX.match(tool):
        return _json_cors({"status": "error", "message": "unknown tool"}, 400)
    r = _tools.call(tool, d.get("args") or {}, caller=caller)
    return _json_cors({"status": "success" if r["ok"] else "error", "tool": tool, "result": r.get("value"), "message": r.get("error"), "output": r.get("output"), "ms": r["ms"]},
                      200 if r["ok"] else 422)

# ═══════════════════════════════════════════════════════
# axis gate telemetry + controls (the guardian itself is the axis_gate package)
# Counts and "is anything tripped" are public like the modules list; which subject, why, and the event feed need the admin token.
# ═══════════════════════════════════════════════════════
@app.route("/api/gate/status", methods=["GET", "OPTIONS"], strict_slashes=False)
def gate_status():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    if _gate is None:
        return _json_cors({"status": "error", "message": "the axis gate is not available"}, 503)
    if _admin_ok():
        g = _gate.status()
        if _keybox is not None:
            try:
                g["keybox"] = _keybox.status()                 # count + time of the last key only; never a name's value
            except Exception:
                pass
        return _json_cors({"status": "success", "detail": True, "gate": g})
    return _json_cors({"status": "success", "detail": False, "gate": _gate.summary()})

@app.route("/api/gate/verify", methods=["POST", "OPTIONS"])
def gate_verify():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin()
    if denied:
        return denied
    if _gate is None:
        return _json_cors({"status": "error", "message": "the axis gate is not available"}, 503)
    res = _gate.verify_all(fast=False)
    _gate_notify(res)
    return _json_cors({"status": "success", "result": res, "gate": _gate.status()})

@app.route("/api/gate/reseal", methods=["POST", "OPTIONS"])
def gate_reseal():
    """After YOU changed a core file on purpose: make the current files the trusted baseline again."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin()
    if denied:
        return denied
    if _gate is None:
        return _json_cors({"status": "error", "message": "the axis gate is not available"}, 503)
    what = (request.get_json(silent=True) or {}).get("confirm")
    if what not in ("core", "consult"):
        return _json_cors({"status": "error", "message": "Re-sealing needs {\"confirm\": \"core\"} or {\"confirm\": \"consult\"}."}, 400)
    r = _gate.seal_core() if what == "core" else _gate.seal_consult()
    return _json_cors({"status": "success", "sealed": r, "gate": _gate.status()})

# ── API key ingestion: left-panel form -> single-use axis gate ticket -> payload structure check -> key box in the tool vault ──
# The key travels: browser form -> this route (admin token) -> axis gate (ticket spent once + structure checked) -> keybox.ingest (locked).
# It is never logged, never echoed back, and never part of an error message. Nothing here (or anywhere) returns a stored key.
try:
    import keybox as _keybox
except Exception as _e_kb:
    _keybox = None
    print("[KEYBOX] unavailable: %s" % type(_e_kb).__name__)

_KEY_RULES = {"name": {"min": 2, "max": 64, "pattern": r"[A-Za-z0-9][A-Za-z0-9_.-]*"},
              "purpose": {"min": 1, "max": 300},
              "key": {"min": 8, "max": 4096, "printable": True},
              "ticket": {"min": 16, "max": 80}}
_KEY_BODY_MAX = 12_000

def _keybox_or_503():
    if _keybox is None or _gate is None:
        return _json_cors({"status": "error", "message": "the key box needs the axis gate and keybox modules, and one is not available"}, 503)
    return None

@app.route("/api/keys/ticket", methods=["POST", "OPTIONS"])
def keys_ticket():
    """Step 1: the form asks the axis gate for ONE single-use ticket (valid 2 minutes) for ONE key submission."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _keybox_or_503()
    if denied:
        return denied
    purpose = str((request.get_json(silent=True) or {}).get("purpose") or "keybox")
    if purpose not in ("keybox", "keygrant"):
        return _json_cors({"status": "error", "message": "unknown ticket purpose"}, 400)
    t = _gate.issue_ticket(purpose, ttl=120)
    if t is None:
        return _json_cors({"status": "error", "message": "too many pending requests; wait a moment"}, 429)
    return _json_cors({"status": "success", "ticket": t, "expires_in": 120})

@app.route("/api/keys/ingest", methods=["POST", "OPTIONS"])
def keys_ingest():
    """Step 2: {ticket, name, purpose, key, overwrite?}. The ticket is spent first (replay protection), then the structure is checked,
    only then is the key locked in the key box. Success returns metadata and a green flag; the key itself is never returned."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _keybox_or_503()
    if denied:
        return denied
    if request.content_length is not None and request.content_length > _KEY_BODY_MAX:
        return _json_cors({"status": "error", "indicator": "red", "message": "that request is too large to be a key"}, 413)
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return _json_cors({"status": "error", "indicator": "red", "message": "send JSON: {ticket, name, purpose, key}"}, 400)
    overwrite = d.pop("overwrite", False) is True
    v = _gate.redeem_ticket(d.get("ticket"), "keybox", source="keybox-ui")
    if not v.allow:
        return _json_cors({"status": "error", "indicator": "red", "message": "the axis gate refused it (%s). Press Ingest & Lock again to get a fresh ticket." % v.reason}, 409)
    v = _gate.check_fields("KEYBOX", "key-ingest", d, _KEY_RULES)                      # the verdict names a field, never a value
    if not v.allow:
        return _json_cors({"status": "error", "indicator": "red", "message": "the axis gate refused the form (%s)" % v.reason}, 422)
    try:
        meta = _keybox.ingest(d["name"], d["purpose"], d["key"], overwrite=overwrite)
    except _keybox.KeyBoxError as e:
        _gate.record("KEYBOX", d.get("name", "?"), "KEY_INGEST", "BLOCKED", "refused by the key box", "HIGH")
        return _json_cors({"status": "error", "indicator": "red", "message": str(e), "exists": "already locked" in str(e)}, 409)
    except Exception as e:
        _gate.record("KEYBOX", d.get("name", "?"), "KEY_INGEST", "SYSTEM_FAULT", type(e).__name__, "HIGH")
        return _json_cors({"status": "error", "indicator": "red", "message": "the key could not be locked (%s)" % type(e).__name__}, 500)
    d.clear()
    _gate.record("KEYBOX", meta["name"], "KEY_INGEST", "SUCCESS", "locked in the key box (%s)" % meta["protection"], "HIGH")
    return _json_cors({"status": "success", "indicator": "green", "message": "Locked in the key box.", "key": meta})

@app.route("/api/keys", methods=["GET", "OPTIONS"], strict_slashes=False)
def keys_list():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _require_vault_admin() or _keybox_or_503()
    if denied:
        return denied
    return _json_cors({"status": "success", "keys": _keybox.list_keys(), "box": _keybox.status()})

@app.route("/api/keys/<name>", methods=["DELETE", "OPTIONS"])
def keys_remove(name):
    if request.method == "OPTIONS":
        return _admin_cors_options("DELETE")
    denied = _require_vault_admin() or _keybox_or_503()
    if denied:
        return denied
    if (request.get_json(silent=True) or {}).get("confirm") != name:
        return _json_cors({"status": "error", "message": "Removing needs {\"confirm\": \"%s\"}." % name}, 400)
    try:
        _keybox.remove(name)
    except _keybox.KeyBoxError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)
    _gate.record("KEYBOX", name, "KEY_REMOVE", "SUCCESS", "removed from the key box", "HIGH")
    return _json_cors({"status": "success", "removed": name})

# ── Granting a stored key to ONE approved tool ──
# Rules: owner only (admin token) + a single-use gate ticket; the tool must exist and must have been approved WITH internet access (a key is for calling
# an API); the key must be in the key box. The grant record is sealed by the axis gate. At call time the key reaches the tool only as an environment
# variable inside its sandbox, and the tool vault scrubs it from whatever the tool returns.
_GRANT_RULES = {"ticket": {"min": 16, "max": 80}, "key": {"min": 2, "max": 64, "pattern": r"[A-Za-z0-9][A-Za-z0-9_.-]*"},
                "env": {"min": 3, "max": 64, "required": False, "pattern": r"[A-Z][A-Z0-9_]*"}}

@app.route("/api/keys/grants", methods=["GET", "OPTIONS"])
def keys_grants():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _require_vault_admin() or _keybox_or_503()
    if denied:
        return denied
    return _json_cors({"status": "success", "grants": _keybox.all_grants(), "detail": _keybox.all_grants_detail(), "env_prefix": "NEXXUS_KEY_"})

@app.route("/api/tools/<name>/keys", methods=["POST", "OPTIONS"])
def tools_grant_key(name):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _keybox_or_503() or _tools_or_503()
    if denied:
        return denied
    d = request.get_json(silent=True)
    if not isinstance(d, dict) or not _TOOL_NAME_RX.match(name):
        return _json_cors({"status": "error", "indicator": "red", "message": "send JSON: {ticket, key}"}, 400)
    v = _gate.redeem_ticket(d.get("ticket"), "keygrant", source="keygrant-ui")
    if not v.allow:
        return _json_cors({"status": "error", "indicator": "red", "message": "the axis gate refused it (%s). Press Grant again for a fresh ticket." % v.reason}, 409)
    v = _gate.check_fields("KEYGRANT", name, d, _GRANT_RULES)
    if not v.allow:
        return _json_cors({"status": "error", "indicator": "red", "message": "the axis gate refused the request (%s)" % v.reason}, 422)
    tool = next((t for t in _tools.list_tools() if t["name"] == name), None)
    if tool is None:
        return _json_cors({"status": "error", "indicator": "red", "message": "no such tool"}, 404)
    if not tool["permissions"].get("network"):
        _gate.record("KEYGRANT", name, "KEY_GRANT", "BLOCKED", "tool has no internet permission", "HIGH")
        return _json_cors({"status": "error", "indicator": "red", "message": "That tool was approved without internet access, so it has no use for an API key. Re-fetch it and grant internet when you approve it."}, 409)
    try:
        held = _keybox.grant(name, d["key"], env=d.get("env"))
    except _keybox.KeyBoxError as e:
        _gate.record("KEYGRANT", name, "KEY_GRANT", "BLOCKED", "refused by the key box", "HIGH")
        return _json_cors({"status": "error", "indicator": "red", "message": str(e)}, 409)
    _gate.record("KEYGRANT", name, "KEY_GRANT", "SUCCESS", "a key was granted to the tool", "HIGH")
    names = [_keybox.env_name(d["key"])] + ([d["env"]] if d.get("env") else [])
    return _json_cors({"status": "success", "indicator": "green", "message": "Granted. The tool reads it from %s." % " and ".join(names),
                       "tool": name, "keys": held, "env": names[0], "alias": d.get("env")})

@app.route("/api/tools/<name>/keys/<key>", methods=["DELETE", "OPTIONS"])
def tools_revoke_key(name, key):
    if request.method == "OPTIONS":
        return _admin_cors_options("DELETE")
    denied = _require_vault_admin() or _keybox_or_503()
    if denied:
        return denied
    if (request.get_json(silent=True) or {}).get("confirm") != key:
        return _json_cors({"status": "error", "message": "Revoking needs {\"confirm\": \"%s\"}." % key}, 400)
    try:
        held = _keybox.revoke(name, key)
    except _keybox.KeyBoxError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)
    _gate.record("KEYGRANT", name, "KEY_REVOKE", "SUCCESS", "a key was taken back from the tool", "HIGH")
    return _json_cors({"status": "success", "tool": name, "keys": held})

def _gate_notify(res):
    """A drift seen for the first time becomes one persistent notification in the bell."""
    for t in (res or {}).get("new", []):
        try:
            _notes.add("gate", "axis gate: %s %s changed" % (t["kind"], t["id"]), "%s. %s" % (t["reason"], "It is refused until fixed." if t["enforced"] else "Report only: re-seal in Settings > axis gate if you changed it on purpose."),
                       "fail", [], {"gate": "%s:%s" % (t["kind"], t["id"])}, dedupe_key="gate:%s:%s:%s" % (t["kind"], t["id"], __import__("zlib").crc32(t["reason"].encode())))
        except Exception:
            pass

def _gate_watcher():
    """Background: re-check every sealed item every 30 s (cheap: report-only files are checked by size+mtime first)."""
    time.sleep(8)
    while True:
        try:
            _gate_notify(_gate.verify_all(fast=True))
        except Exception as e:
            print(f"[axis gate] watcher error (continuing): {type(e).__name__}: {e}")
        time.sleep(30)

def _note_from_job(mgr, n):
    """A finished job (success or failure) becomes one persistent notification, with the actions that make sense for it."""
    job = mgr.get(n.get("job_id")) or {}
    res = job.get("result") or {}
    actions, ref = [], {"job_id": n.get("job_id")}
    cid = res.get("creation_id")
    if cid:
        ref["creation_id"] = cid
        actions += [{"type": "view_creation", "label": "View in Creations", "ref": cid},
                    {"type": "download", "label": "Download", "ref": "/api/creations/%s/download" % cid}]
    if isinstance(res, dict) and res.get("artifact"):
        actions.append({"type": "open_artifact", "label": "Open in panel", "ref": n.get("job_id")})
    _notes.add("creation" if cid else "job", job.get("description") or "Job finished", n.get("message", ""),
               "ok" if n.get("status") == "completed" else "fail", actions, ref, dedupe_key="job:%s" % n.get("job_id"))
    if n.get("status") != "completed":
        mm = re.search(r"No module named '([A-Za-z0-9_]+)", "%s %s" % (n.get("message", ""), json.dumps(res, default=str)[:4000]))
        if mm:
            threading.Thread(target=lambda: request_need("python package " + mm.group(1), "A build failed: it needs the Python module '%s' and it is not installed." % mm.group(1), True, "build-failure"),
                             daemon=True, name="nexxus-need").start()

def _notes_check_vault():
    """New Final Assets vault commits become notifications. The first ever run only records what is already there."""
    port = getattr(nexus_module, "final_asset_port", None) if NEXUS_AVAILABLE else None
    if port is None:
        return
    res = port.list_assets()
    assets = res.get("assets") if isinstance(res, dict) else None
    if not isinstance(assets, list):
        return
    ids = {a.get("asset_id") for a in assets if isinstance(a, dict) and a.get("asset_id")}
    seen = _notes.seen_vault_ids()
    if seen is None:
        _notes.set_seen_vault_ids(ids)
        return
    new = ids - seen
    for a in assets:
        if isinstance(a, dict) and a.get("asset_id") in new:
            aid = a["asset_id"]
            _notes.add("vault", a.get("name") or aid, "%s - %s files ready in the Final Assets vault." % (a.get("build_type") or "build", a.get("file_count", "?")), "ok",
                       [{"type": "download", "label": "Download", "ref": "/api/vault/assets/%s/download" % aid},
                        {"type": "view_vault", "label": "View in vault", "ref": aid}], {"vault_id": aid}, dedupe_key="vault:" + aid)
    if new:
        _notes.set_seen_vault_ids(seen | ids)

def _notify_watcher():
    """Background thread: turns job completions and new vault assets into stored notifications (works with the page closed)."""
    mgr = _job_manager.get_default_manager() if _job_manager is not None else None
    cursor = mgr.notifications()["latest"] if mgr else 0
    tick = 0
    while True:
        time.sleep(4)
        try:
            if mgr:
                got = mgr.notifications(since=cursor)
                for n in got["items"]:
                    _note_from_job(mgr, n)
                cursor = got["latest"]
            tick += 1
            if tick % 3 == 0:
                _notes_check_vault()
        except Exception as e:
            print(f"[NOTIFY] watcher error (continuing): {type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════
# LEAD CAPTURE
# Receives the "Black Book" mailing-list form every funnel_factory.py landing
# page renders (<form action="/api/collect_lead" method="POST">). Writes into
# the SAME per-client SQLite DB FunnelFactoryEngine already created at
# ./lead_storage/{client_id}_leads.db (schema: id, email, source_page,
# timestamp) - this is a thin HTTP wrapper around that existing storage, not a
# second lead store. The table is also created here defensively (CREATE TABLE
# IF NOT EXISTS) in case a lead comes in for a client DB that, for whatever
# reason, wasn't pre-built.
# ═══════════════════════════════════════════════════════

LEAD_DB_DIR = Path("./lead_storage")
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Plain in-memory sliding-window rate limit - no Redis, no external service,
# just a dict guarded by a lock. Good enough for a single-process deployment
# (which this is - the Werkzeug dev server / a single gunicorn worker); it
# would NOT coordinate across multiple separate worker processes, since each
# process gets its own dict. Keyed on remote_addr, which is the real client
# IP only when nothing sits in front of this process rewriting it (no
# X-Forwarded-For handling here - this is a local/single-host deployment,
# not behind a load balancer).
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_MAX_REQUESTS = 20  # per IP per window, for the public lead-capture form
_rate_limit_lock = threading.Lock()
_rate_limit_buckets = {}  # ip -> [timestamps within the current window]

def _rate_limited(ip: str) -> bool:
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    with _rate_limit_lock:
        bucket = _rate_limit_buckets.setdefault(ip, [])
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= _RATE_LIMIT_MAX_REQUESTS:
            return True
        bucket.append(now)
        # Opportunistic sweep (not on every call) so IPs that stop sending
        # requests don't sit in the dict forever - bounds memory without a
        # dedicated background thread.
        if len(_rate_limit_buckets) > 200 and int(now) % 50 == 0:
            for key in [k for k, v in _rate_limit_buckets.items() if not v or v[-1] < cutoff]:
                del _rate_limit_buckets[key]
        return False

def _lead_error(message, code=400):
    res = jsonify({"status": "error", "message": message})
    response = make_response(res, code)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response

def _lead_db_path(client_id):
    """Resolves client_id to its lead DB path, refusing anything that would
    escape lead_storage/ (path traversal via a crafted client_id)."""
    LEAD_DB_DIR.mkdir(parents=True, exist_ok=True)
    root = LEAD_DB_DIR.resolve()
    candidate = (LEAD_DB_DIR / f"{client_id}_leads.db").resolve()
    if candidate.parent != root:
        return None
    return candidate

@app.route("/api/collect_lead", methods=["POST", "OPTIONS"])
def collect_lead():
    if request.method == "OPTIONS":
        return _cors_options("POST")

    if _rate_limited(request.remote_addr or "unknown"):
        response = make_response(
            jsonify({"status": "error", "message": "Too many submissions - please wait a minute and try again."}), 429)
        response.headers["Retry-After"] = str(int(_RATE_LIMIT_WINDOW_SECONDS))
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    # The landing pages submit a plain HTML form (not JSON/fetch), so this is
    # standard form-encoded data - request.form, not request.get_json().
    form = request.form or {}
    client_id = (form.get("client_id") or "").strip()
    email = (form.get("email") or "").strip()

    if not client_id or not CLIENT_ID_RE.match(client_id):
        return _lead_error("Missing or invalid 'client_id'.")
    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        return _lead_error("Missing or invalid 'email'.")

    db_path = _lead_db_path(client_id)
    if db_path is None:
        return _lead_error("Invalid 'client_id'.")

    source_page = (request.form.get("source_page") or request.referrer or "")[:500]
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        # busy_timeout makes a concurrent writer WAIT (up to 5s) for the lock
        # instead of immediately raising "database is locked"; WAL mode lets
        # readers and writers proceed concurrently instead of serializing on
        # a single rollback-journal lock. Neither eliminates contention under
        # extreme concurrency, but both substantially raise the concurrent-
        # writer ceiling for this exact endpoint over the sqlite3 defaults.
        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute('''
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    source_page TEXT,
                    timestamp TEXT
                )
            ''')
            conn.execute(
                "INSERT INTO leads (email, source_page, timestamp) VALUES (?, ?, ?)",
                (email, source_page, timestamp),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return _lead_error(f"Could not store lead: {e}", 500)

    # Plain HTML-form submissions expect a page back, not a bare JSON blob -
    # a lightweight confirmation page rather than the JSON responses the rest
    # of this file's JS-driven endpoints return.
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>You're in</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #f9f9fb; color: #333; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; margin: 0; }
  .card { background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);
          text-align: center; max-width: 420px; }
  h1 { margin-top: 0; color: #111; }
  a { color: #3b82f6; text-decoration: none; }
</style>
</head>
<body>
  <div class="card">
    <h1>You&#39;re on the list.</h1>
    <p>Thanks for signing up - check your inbox soon.</p>
    <p><a href="javascript:history.back()">&larr; Back</a></p>
  </div>
</body>
</html>"""
    response = make_response(html, 200)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


# ═══════════════════════════════════════════════════════
# STAGING AREA + MICRO-DISPATCH PIPELINE
# The Sidecar Vault Inspector's backend: categories staged here are visible and
# inspectable but NOT yet in the permanent vault. Nothing here auto-promotes -
# /commit is the Manual Commit Gate, and /discard is its explicit reject.
# The job endpoints implement the micro-dispatch protocol: run_stage advances a
# job by exactly one bounded stage per call, so a slow LLM summarization can never
# block or time out the scrape/stage/validate work already done.
# ═══════════════════════════════════════════════════════

def _staging_or_503():
    if not staging_area:
        res = jsonify({"status": "error", "message": "staging_area unavailable (micro_dispatch.py not found)"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return None

@app.route("/api/staging/categories", methods=["GET", "OPTIONS"])
def staging_list():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    unavailable = _staging_or_503()
    if unavailable:
        return unavailable
    return handle_action_response(staging_area.list_categories())

@app.route("/api/staging/categories/<category>", methods=["GET", "OPTIONS"])
def staging_inspect(category):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    unavailable = _staging_or_503()
    if unavailable:
        return unavailable
    return handle_action_response(staging_area.inspect_category(category))

@app.route("/api/staging/categories/<category>/file", methods=["GET", "OPTIONS"])
def staging_read_file(category):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    unavailable = _staging_or_503()
    if unavailable:
        return unavailable
    filename = request.args.get("path")
    if not filename:
        res = jsonify({"status": "error", "message": "Query param 'path' (staged file name) is required."})
        response = make_response(res, 400)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return handle_action_response(staging_area.read_staged_file(category, filename))

@app.route("/api/staging/categories/<category>/commit", methods=["POST", "OPTIONS"])
def staging_commit(category):
    if request.method == "OPTIONS":
        return _cors_options("POST")
    unavailable = _staging_or_503()
    if unavailable:
        return unavailable
    if not NEXUS_AVAILABLE or not getattr(nexus_module, "final_asset_port", None):
        res = jsonify({"status": "error", "message": "final_asset_port unavailable - cannot commit to permanent storage"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    data = request.get_json(silent=True) or {}
    build_type = data.get("build_type", "sandbox")
    mode_info = _modes.describe(_mode_state.mode) if _mode_state is not None else None
    if mode_info is not None:
        if not mode_info["can_build"]:
            return _json_cors({"status": "halted", "reason": "commit_in_conversation_mode", "mode": mode_info["mode"],
                               "message": "Save halted: Conversation (Neutral) mode never writes to the permanent vault. Switch to a build mode first.",
                               "mode_required": _modes.halt_payload(mode_info["mode"])}, 409)
        build_type = mode_info["vault_lane"]
    # Peer-review hold: always on. Re-review the exact files being committed; a critical finding
    # you have not released stops the commit (nothing is written to the permanent vault).
    if _review_store is not None:
        rep = _run_review(category)
        if rep is not None:
            _, sig = _review_inputs(category)
            if _review_store.is_blocking(category, sig):
                crit = [f for f in rep["findings"] if f["severity"] == "critical"][:10]
                return _json_cors({"status": "held_by_review", "category": category, "summary": rep["summary"],
                                   "critical": crit,
                                   "message": f"{rep['summary']['critical']} critical finding(s) hold this commit. Fix the files, or release the hold (admin token) if you accept them."}, 409)
    # Mode rule: Corporate Sellable holds the commit on ANY warning-or-worse review finding, and unlike a
    # critical hold there is no release button - fix the files (or deliberately leave Corporate mode).
    if mode_info is not None and "warning" in mode_info["commit_blocks_on"]:
        rep2 = _run_review(category) if _review_store is not None else None
        if rep2 is None:
            return _json_cors({"status": "held_by_mode", "mode": mode_info["mode"], "category": category, "findings": [],
                               "message": "Corporate Sellable mode needs a completed peer review before saving, and the review could not run (module missing or category unreadable)."}, 409)
        reason = _modes.corporate_commit_check(rep2["summary"], mode_info["commit_blocks_on"])
        if reason:
            held = [f for f in rep2["findings"] if f["severity"] in mode_info["commit_blocks_on"]][:10]
            return _json_cors({"status": "held_by_mode", "mode": mode_info["mode"], "category": category, "summary": rep2["summary"],
                               "findings": held, "message": f"Corporate Sellable mode holds this commit: {reason}. Fix the files and save again."}, 409)
    result = staging_area.commit(category, build_type, nexus_module.final_asset_port, name=data.get("name"))
    return handle_action_response(result)

@app.route("/api/staging/categories/<category>/discard", methods=["POST", "OPTIONS"])
def staging_discard(category):
    if request.method == "OPTIONS":
        return _cors_options("POST")
    unavailable = _staging_or_503()
    if unavailable:
        return unavailable
    return handle_action_response(staging_area.discard(category))

@app.route("/api/staging/jobs", methods=["POST", "OPTIONS"])
def staging_create_job():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if not dispatch_pipeline:
        res = jsonify({"status": "error", "message": "dispatch_pipeline unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    data = request.get_json(silent=True) or {}
    category, target = data.get("category"), data.get("target")
    if not category or not target:
        res = jsonify({"status": "error", "message": "'category' and 'target' are both required"})
        response = make_response(res, 400)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    build_type = data.get("build_type", "sandbox")
    if _mode_state is not None:
        info = _modes.describe(_mode_state.mode)
        if not info["can_build"]:
            return _json_cors({"status": "halted", "reason": "build_in_conversation_mode", "mode": info["mode"],
                               "message": "Build halted: you are in Conversation (Neutral) mode. Switch to Sandbox, Corporate or Dashboard Hub Build mode first.",
                               "mode_required": _modes.halt_payload(info["mode"])}, 409)
        build_type = info["vault_lane"]      # the mode decides the lane, not the request body
    result = dispatch_pipeline.create_job(category, target, build_type)
    if _dash is not None and _mode_state is not None and _mode_state.mode == "dashboard_hub" \
            and isinstance(result, dict) and result.get("status") != "error":
        try:                              # every profile built here gets a dashboard of its own, nested from the start
            hub = _dash.ensure_hub(_dc.slug("vault-" + str(category)), str(category), _dash_base())
            _dash.nest(hub["id"], "vault", str(category), str(category))
        except Exception:
            pass
    return handle_action_response(result)

@app.route("/api/staging/jobs/<job_id>", methods=["GET", "OPTIONS"])
def staging_job_status(job_id):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if not dispatch_pipeline:
        res = jsonify({"status": "error", "message": "dispatch_pipeline unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return handle_action_response(dispatch_pipeline.get_job(job_id))

@app.route("/api/staging/jobs/<job_id>/run/<stage>", methods=["POST", "OPTIONS"])
def staging_run_stage(job_id, stage):
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if not dispatch_pipeline:
        res = jsonify({"status": "error", "message": "dispatch_pipeline unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return handle_action_response(dispatch_pipeline.run_stage(job_id, stage))


# ═══════════════════════════════════════════════════════
# CURATOR ROUTER (Phase 14): Render -> Manifest -> Rotate -> Dispatch -> Sync -> Pulse
# Curator-led routing - these two endpoints never run the six pipeline-stage
# engines themselves; they hand a package_spec to nexxus_talks.curator_router,
# which is the only thing allowed to invoke those engines, in strict sequence.
# ═══════════════════════════════════════════════════════

@app.route("/api/curator/run", methods=["POST", "OPTIONS"])
def curator_run():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if not NEXUS_AVAILABLE:
        res = jsonify({"status": "error", "message": "nexxus_talks (curator_router) unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    payload = request.get_json(silent=True) or {}
    package_spec = payload.get("package_spec", payload) if isinstance(payload, dict) else {}
    return handle_action_response(nexus_module.curator_router.run_pipeline(package_spec))

@app.route("/api/curator/status", methods=["GET", "OPTIONS"])
def curator_status():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if not NEXUS_AVAILABLE:
        res = jsonify({"status": "error", "message": "nexxus_talks (curator_router) unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return handle_action_response(nexus_module.curator_router.status())


# ═══════════════════════════════════════════════════════
# AUTONOMOUS SCHEDULER (Phase 15): the actual recurring-automation loop.
# On its own interval it runs the real funnel factory batch build, ingests
# whatever was actually (re)built into the vault, and feeds each new asset
# through the Curator Router - with no chat message or API call needed once
# it's started. Auto-starts when nexxus_talks loads (unless
# NEXXUS_DISABLE_AUTOSCHEDULER=1 is set); these endpoints only ever
# inspect/start/stop/reconfigure it - never a substitute trigger path.
# ═══════════════════════════════════════════════════════

@app.route("/api/scheduler/status", methods=["GET", "OPTIONS"])
def scheduler_status():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if not NEXUS_AVAILABLE:
        res = jsonify({"status": "error", "message": "nexxus_talks (autonomous_scheduler) unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return handle_action_response(nexus_module.autonomous_scheduler.status())

@app.route("/api/scheduler/start", methods=["POST", "OPTIONS"])
def scheduler_start():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if not NEXUS_AVAILABLE:
        res = jsonify({"status": "error", "message": "nexxus_talks (autonomous_scheduler) unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return handle_action_response(nexus_module.autonomous_scheduler.start())

@app.route("/api/scheduler/stop", methods=["POST", "OPTIONS"])
def scheduler_stop():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if not NEXUS_AVAILABLE:
        res = jsonify({"status": "error", "message": "nexxus_talks (autonomous_scheduler) unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return handle_action_response(nexus_module.autonomous_scheduler.stop())

@app.route("/api/scheduler/run-now", methods=["POST", "OPTIONS"])
def scheduler_run_now():
    """Manual override: runs one cycle immediately, outside the schedule."""
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if not NEXUS_AVAILABLE:
        res = jsonify({"status": "error", "message": "nexxus_talks (autonomous_scheduler) unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return handle_action_response(nexus_module.autonomous_scheduler.run_cycle_now())

@app.route("/api/scheduler/configure", methods=["POST", "OPTIONS"])
def scheduler_configure():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if not NEXUS_AVAILABLE:
        res = jsonify({"status": "error", "message": "nexxus_talks (autonomous_scheduler) unavailable"})
        response = make_response(res, 503)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    payload = request.get_json(silent=True) or {}
    interval = payload.get("interval_seconds")
    if interval is None:
        res = jsonify({"status": "error", "message": "interval_seconds is required"})
        response = make_response(res, 400)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    try:
        interval = float(interval)
    except (TypeError, ValueError):
        res = jsonify({"status": "error", "message": "interval_seconds must be a number"})
        response = make_response(res, 400)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    return handle_action_response(nexus_module.autonomous_scheduler.set_interval(interval))


# ═══════════════════════════════════════════════════════
# FULL-STACK WEDGE GENERATION
# Genuinely backed by your local model (via route_bridge_request - the same
# Llama.cpp/Ollama pipeline everything else uses), not a canned response. Asks
# the model to emit frontend/backend code between explicit markers; if it doesn't
# follow that format reliably, returns the same offline_fallback_success shape
# dispatchPythonServerRequest() already produces on the frontend so the client's
# local template scaffold kicks in exactly as if the server were unreachable -
# never returns malformed/partial code as if it were a real result.
# ═══════════════════════════════════════════════════════

@app.route("/api/generate-fullstack", methods=["POST", "OPTIONS"])
def generate_fullstack():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response

    data = request.get_json(silent=True) or {}
    spec = str(data.get("spec", "")).strip()
    hub_id = data.get("hub")
    if not spec:
        res = jsonify({"status": "error", "message": "No spec provided"})
        response = make_response(res, 400)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    gen_prompt = (
        "You are generating a small, self-contained UI component and a matching Flask "
        "backend route stub for a local dashboard. Respond in EXACTLY this format, with "
        "no extra commentary outside the markers:\n"
        "---FRONTEND---\n"
        "<a small, self-contained HTML/CSS/JS snippet implementing the UI>\n"
        "---BACKEND---\n"
        "<a matching Flask route (Python) the frontend snippet calls via fetch>\n"
        "---LABEL---\n"
        "<a short one-line title for this component>\n"
        f"\nComponent to build: {spec}"
    )

    raw = route_bridge_request(gen_prompt)

    frontend, backend, label = None, None, None
    try:
        if isinstance(raw, str) and "---FRONTEND---" in raw and "---BACKEND---" in raw:
            after_fe = raw.split("---FRONTEND---", 1)[1]
            frontend_part, rest = after_fe.split("---BACKEND---", 1)
            frontend = frontend_part.strip()
            if "---LABEL---" in rest:
                backend_part, label_part = rest.split("---LABEL---", 1)
                backend = backend_part.strip()
                label = (label_part.strip().splitlines() or [spec])[0]
            else:
                backend = rest.strip()
                label = spec
    except Exception:
        frontend, backend, label = None, None, None

    if not frontend or not backend:
        # Model didn't follow the format reliably - signal the same shape as an
        # unreachable server so the client's local scaffold fallback takes over,
        # rather than handing back unparseable text as if it were real code.
        return handle_action_response({"status": "offline_fallback_success", "reason": "generation_unparseable"})

    return handle_action_response({
        "status": "success",
        "frontend": frontend,
        "backend": backend,
        "label": label,
        "hub": hub_id,
    })

# ═══════════════════════════════════════════════════════
# EXECUTION LOOPS
# ═══════════════════════════════════════════════════════

def run_terminal():
    """Terminal chat. Returns 'exit' when the user chose to shut down, or 'headless' when there is
    no usable console (stdin closed / no console) - in that case the server just keeps serving."""
    print("NEXXUS Bridge & Terminal Chat Active.")
    print("Type 'exit' to shut down.\n")
    consecutive_errors = 0
    while True:
        try:
            user_input = input("You: ").strip()
            consecutive_errors = 0
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit"]:
                print("\nBridge offline.")
                return "exit"
            reply = route_bridge_request(user_input)
            print(f"NEXXUS: {reply}\n")
        except KeyboardInterrupt:
            print("\nBridge offline.")
            return "exit"
        except (EOFError, RuntimeError) as e:
            # No console to read from (launched without one / stdin closed). Keep serving instead of spinning.
            print(f"\nNo terminal input available ({type(e).__name__}); continuing in server-only mode.")
            return "headless"
        except Exception as e:
            print(f"\nError: {e}\n")
            consecutive_errors += 1
            if consecutive_errors >= 20:
                print("Terminal input keeps failing; continuing in server-only mode.")
                return "headless"

# ═══════════════════════════════════════════════════════
# ENGINE BUILD MODE  +  CROSS-ENGINE TELEMETRY  +  PROMPT RECIPE VAULT
# Engine Build writes a new modular engine into staging_vault/engines/ and deploys it to the UI directory ONLY when the owner approves (admin token, bound to the
# briefing hash). Telemetry registers every external engine, pings it, and keeps a numbered activity feed the dashboard lights LEDs from. The prompt vault holds
# reusable build prompts. See engine_build.py / engine_telemetry.py / prompt_vault.py.
# ═══════════════════════════════════════════════════════
try:
    import engine_build as _eb
    import engine_telemetry as _etel
    import prompt_vault as _pvault
except Exception as _e_eb:                           # the rest of NEXXUS must still run without it
    _eb = _etel = _pvault = None
    print("[ENGINE BUILD] unavailable: %s: %s" % (type(_e_eb).__name__, _e_eb))

_engine_cfg = {"standalone": True}                   # the bottom-left switch: True = no NEXXUS link, False = linked across the external bridge
_telemetry = None
if _etel is not None:
    try:
        _telemetry = _etel.EngineTelemetry(_eb.UI_ROOT, roster_names=(lambda: list(_ext.names()) if _ext is not None else []),
                                           rpc=(_ext._rpc if _ext is not None else None), builds=(lambda: _eb.list_builds(20)), interval=10.0)
        if _ext is not None:
            def _ext_activity(name, op, ok):         # a signed call to a module just crossed the bridge (its own health pings are not "activity")
                if op != "health":
                    _telemetry.record(name, "rpc" if ok else "rpc-failed", str(op))
            _ext.ACTIVITY_HOOK = _ext_activity
    except Exception as _e_tel:
        _telemetry = None
        print("[TELEMETRY] unavailable: %s: %s" % (type(_e_tel).__name__, _e_tel))


def _eb_or_503():
    if _eb is None:
        return _json_cors({"status": "error", "message": "engine_build.py is not installed next to the NEXXUS modules"}, 503)
    return None


def _engine_notify(build_id, name):
    if _notes is not None:
        _notes.add("engine", "Engine staged for review: " + name, "Its tests passed and the audit is clean. Nothing is deployed until you approve it.", "ok",
                   [{"type": "open_engine_tracker", "label": "Review", "ref": build_id}], {"engine_build": build_id}, dedupe_key="engine-staged:" + build_id)


def _engine_start(request_text, name=None):
    """Start a build in the current Standalone/Linked setting. -> (result dict, error text)."""
    try:
        res = _eb.start_build(request_text, standalone=_engine_cfg["standalone"], name=name, notify=_engine_notify)
    except _eb.EngineBuildError as e:
        return None, str(e)
    if _telemetry is not None:
        _telemetry.record(res["name"], "build", "queued (%s)" % res["mode"])
    return res, None


def _engine_chat_reply(text):
    """In Engine Build mode a build order starts an engine build. -> (reply, extras) or None."""
    if _eb is None or _mode_state is None or _mode_state.mode != "engine_build" or not _modes.looks_like_build_request(text):
        return None
    res, err = _engine_start(text)
    if err:
        return "I could not start that engine build: %s." % err, {}
    return ("Engine build started: %s (%s). Watch the file tracker on the side; it will wait there for your review. Nothing is deployed until you approve it."
            % (res["name"], res["mode"]), {"engine_build": res})


# ═══════════════════════════════════════════════════════
# PORTALS  (Sports, Markets, Logistics, Economics: the dock's four visual controllers)
# The page only draws and asks. Every calculation runs in axis-logic's portal_worker (a throwaway subprocess with a time limit); the data comes from the owner's own
# files in portal_data/, and shipped sample rows say so. Nothing is ever staked, traded, ordered or shipped. See portals.py.
# ═══════════════════════════════════════════════════════
try:
    import portals as _portals
except Exception as _e_portals:
    _portals = None
    print("[PORTALS] unavailable: %s: %s" % (type(_e_portals).__name__, _e_portals))


def _portals_or_503():
    if _portals is None:
        return _json_cors({"status": "error", "message": "the portals are not available (portals.py is missing)"}, 503)
    return None


@app.route("/api/portals", methods=["GET", "OPTIONS"], strict_slashes=False)
def portals_catalog():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    return _portals_or_503() or _json_cors(_portals.catalog())


@app.route("/api/portals/data/<name>", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def portals_data(name):
    """GET: the data set as it really is (loaded, missing, or rejected with its reasons). POST (admin token): validate the owner's data set against its schema and store it; nothing is stored
    unless the whole file is valid, and a file that calls itself sample or placeholder data is refused."""
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    denied = _portals_or_503()
    if denied:
        return denied
    if request.method == "POST":
        denied = _require_vault_admin()
        if denied:
            return denied
        body = request.get_json(silent=True)
        doc = body.get("doc") if isinstance(body, dict) else None
        try:
            return _json_cors({"status": "success", "saved": _portals.save_data(name, doc)})
        except _portals.PortalError as e:
            return _json_cors({"status": "error", "message": str(e)}, 400)
    try:
        return _json_cors({"status": "success", "name": name, "data": _portals.data(name)})
    except _portals.PortalError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)


@app.route("/api/portals/hub/<portal>", methods=["GET", "OPTIONS"], strict_slashes=False)
def portals_hub(portal):
    """What the owner has added to this portal's hub (full catalog entries, in the order added)."""
    if request.method == "OPTIONS":
        return _cors_options("GET")
    denied = _portals_or_503()
    if denied:
        return denied
    try:
        return _json_cors({"status": "success", "portal": portal, "mounted": _portals.hub_mounted(portal)})
    except _portals.PortalError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)


@app.route("/api/portals/hub/mount", methods=["POST", "OPTIONS"], strict_slashes=False)
def portals_hub_mount():
    """Add to Hub / Remove. Only an id that exists in that portal's own catalog can be mounted."""
    if request.method == "OPTIONS":
        return _cors_options("POST")
    denied = _portals_or_503()
    if denied:
        return denied
    d = request.get_json(silent=True)
    if not isinstance(d, dict) or not isinstance(d.get("portal"), str) or not isinstance(d.get("id"), str) or d.get("action") not in ("add", "remove"):
        return _json_cors({"status": "error", "message": "send {\"portal\", \"id\", \"action\": \"add\" or \"remove\"}"}, 400)
    try:
        return _json_cors({"status": "success", "portal": d["portal"], "mounted": _portals.hub_set(d["portal"], d["id"], d["action"] == "add")})
    except _portals.PortalError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)


try:
    import portal_chat as _pchat
except Exception as _e_pchat:
    _pchat = None
    print("[PORTAL CHAT] unavailable: %s: %s" % (type(_e_pchat).__name__, _e_pchat))


# ═══════════════════════════════════════════════════════
# PUBLISHING QUEUE (YouTube): generated videos wait here and nothing goes out until the owner approves. See publish_queue.py and youtube_adapter.py. Every route needs the admin token.
# The API cannot create a channel and NEXXUS cannot authorise itself: the owner creates the channel once in YouTube Studio and supplies the OAuth access token (NEXXUS_YT_ACCESS_TOKEN).
# ═══════════════════════════════════════════════════════
try:
    import publish_queue as _pq
    import youtube_adapter as _yt
    _publish = _pq.PublishQueue(os.environ.get("NEXXUS_PUBLISH_DIR") or (Path(__file__).resolve().parent / "publish_queue"), _creations) if _creations is not None else None
except Exception as _e_pub:
    _pq = _yt = _publish = None
    print("[PUBLISH] unavailable: %s: %s" % (type(_e_pub).__name__, _e_pub))


def _publish_guard():
    denied = _require_vault_admin()
    if denied:
        return denied
    if _publish is None:
        return _json_cors({"status": "error", "message": "the publishing queue is not available (it needs the Creations hub)"}, 503)
    return None


def _publish_do(fn, ok=200):
    try:
        return _json_cors(dict({"status": "success"}, **fn()), ok)
    except _pq.QueueError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    except _yt.YouTubeError as e:
        return _json_cors({"status": "error", "message": str(e)}, 502)


@app.route("/api/publish", methods=["GET", "OPTIONS"], strict_slashes=False)
def publish_list():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _publish_guard()
    if denied:
        return denied
    return _json_cors({"status": "success", "items": _publish.list(), "live_mode": _pq.live_mode(), "daily_cap": _pq.daily_cap(), "token_present": bool(os.environ.get("NEXXUS_YT_ACCESS_TOKEN")),
                       "ledger_ok": _publish.verify_ledger()[0]})


@app.route("/api/publish/stage", methods=["POST", "OPTIONS"], strict_slashes=False)
def publish_stage():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _publish_guard()
    if denied:
        return denied
    d = request.get_json(silent=True) or {}
    return _publish_do(lambda: {"item": _publish.stage(d.get("creation_id"), d.get("title"), d.get("description", ""), d.get("tags") or [], d.get("topic", ""), d.get("privacy", "private"), source="owner")}, 201)


@app.route("/api/publish/<item_id>/<action>", methods=["POST", "OPTIONS"], strict_slashes=False)
def publish_action(item_id, action):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _publish_guard()
    if denied:
        return denied
    d = request.get_json(silent=True) or {}
    if action == "approve":
        return _publish_do(lambda: {"item": _publish.approve(item_id, d.get("privacy"), d.get("confirm_public") is True)})
    if action == "dispatch":
        return _publish_do(lambda: dict(_publish.dispatch(item_id), item=_publish.get(item_id)))
    if action == "cancel":
        return _publish_do(lambda: {"item": _publish.cancel(item_id)})
    return _json_cors({"status": "error", "message": "unknown action"}, 404)


@app.route("/api/publish/channel", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def publish_channel():
    """GET: is there an authorised channel? (a read-only call to YouTube with the owner's token). POST: set its description/keywords/country; needs live mode and confirm: true."""
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    denied = _publish_guard()
    if denied:
        return denied
    if request.method == "GET":
        return _publish_do(lambda: {"channel": _yt.channel()})
    d = request.get_json(silent=True) or {}
    if d.get("confirm") is not True or not _pq.live_mode():
        return _json_cors({"status": "error", "message": "changing the channel needs live mode (NEXXUS_PUBLISH_LIVE=1) and confirm: true"}, 400)
    return _publish_do(lambda: {"updated": _yt.configure_channel(d.get("channel_id"), d.get("description"), d.get("keywords"), d.get("country"))})


# ═══════════════════════════════════════════════════════
# FACTORY: dashboard types (micro-company, platform factory, spatial environment, publishing pipeline, custom). See factory_hub.py / factory_lab.py.
# Reading is open on this machine like the other hubs; every change needs the admin token. A generated site posts its orders to /api/factory/<id>/inbox (below), so no generated form is a dead end.
# ═══════════════════════════════════════════════════════
try:
    import factory_hub as _fh
    import factory_lab as _fl
    import factory_types as _ft
    import factory_platform as _fp
    import factory_env as _fe
    import micro_company as _mc
    import video_maker as _vm
    _fdir = Path(os.environ.get("NEXXUS_FACTORY_DIR") or (Path(__file__).resolve().parent / "factory_data"))

    def _fac_resolver(cid):
        meta = _creations.get(str(cid)) if _creations is not None else None
        if not meta:
            return None
        out = []
        for f in meta["files"]:
            p = _creations.file_path(meta["id"], f["name"])
            if p is not None:
                out.append((f["name"], Path(p).read_bytes()))
        return out

    def _fac_health():
        return {"ok": True, "creations": len(_creations.list()) if _creations is not None else None, "publish_items": len(_publish.list()) if _publish is not None else None,
                "mode": getattr(_mode_state, "mode", None), "at": round(time.time(), 1)}

    def _fac_creation(prompt):
        if _creation is None or _mode_state is None or _job_manager is None:
            raise _mc.CompanyError("Creation mode is not available")
        if _mode_state.mode != "creation":
            raise _mc.CompanyError("creation jobs need Creation mode (the code model); switch to it first")
        mgr = _job_manager.get_default_manager()
        if "creation_render" not in getattr(mgr, "_runners", {}):
            mgr.register_runner("creation_render", _creation.runner)
        return {"job": mgr.submit("creation_render", {"prompt": prompt}, "create: " + prompt.splitlines()[0][:70])["job_id"]}

    def _fac_video(title, lines, spc):
        if _creations is None:
            raise _mc.CompanyError("the Creations hub is not available")
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            r = _vm.make(Path(td) / "video.mp4", title, lines, spc)
            v = _vm.verify(r["path"], r["frames"])
            if not v["ok"]:
                raise _mc.CompanyError("the rendered video failed its decode check: %s" % "; ".join(v["problems"]))
            meta = _creations.save(title, [{"name": "video.mp4", "data": Path(r["path"]).read_bytes()}], source="factory", prompt="; ".join(lines)[:1000], job_id=None)
        return {"creation_id": meta["id"], "title": title, "bytes": r["bytes"], "seconds": r["seconds"]}

    def _fac_stage(cid, title, description="", tags=(), topic=""):
        if _publish is None:
            raise _mc.CompanyError("the publishing queue is not available")
        return _publish.stage(cid, title, description, tags, topic, "private", source="factory")["id"]

    _factory = _fh.Hub(_fdir, {"health": _fac_health, "creation": _fac_creation, "video": _fac_video, "stage": _fac_stage,
                               "channel": lambda: _yt.channel()}, _fac_resolver)
    _factory_lab = _fl.Lab(_fdir / "lab", dict(_factory.services))
except Exception as _e_fac:
    _factory = _factory_lab = None
    print("[FACTORY] unavailable: %s: %s" % (type(_e_fac).__name__, _e_fac))


def _fac_do(fn, ok=200, admin=True):
    if _factory is None:
        return _json_cors({"status": "error", "message": "the factory is not available"}, 503)
    if admin:
        denied = _require_vault_admin()
        if denied:
            return denied
    try:
        return _json_cors(dict({"status": "success"}, **fn()), ok)
    except (_ft.FactoryError, _mc.CompanyError, _fl.LabError, _fp.PlatformError, _fe.EnvError) as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)


def _fac_find(iid):
    for r in _factory.factory.list():
        if r["id"] == iid:
            return r
    return None


@app.route("/api/factory/types", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def factory_types_route():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    if request.method == "GET":
        return _fac_do(lambda: {"types": list(_factory.factory.types().values())}, admin=False)
    d = request.get_json(silent=True) or {}
    return _fac_do(lambda: {"type": _factory.factory.define_custom(d.get("key"), d.get("title"), d.get("summary", ""), d.get("fields") or [], d.get("engine") or "none")}, 201)


@app.route("/api/factory/types/<key>", methods=["DELETE", "OPTIONS"], strict_slashes=False)
def factory_type_delete(key):
    if request.method == "OPTIONS":
        return _admin_cors_options("DELETE")
    return _fac_do(lambda: (_factory.factory.delete_custom(key), {"deleted": key})[1])


@app.route("/api/factory/instances", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def factory_instances():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    if request.method == "GET":
        return _fac_do(lambda: {"instances": [dict(r, company=_factory.company_status(r["id"])) for r in _factory.factory.list(request.args.get("type") or None)]}, admin=False)
    d = request.get_json(silent=True) or {}
    return _fac_do(lambda: {"instance": _factory.create(d.get("type"), d.get("name"), d.get("config") or {})}, 201)


@app.route("/api/factory/instances/<type_key>/<iid>", methods=["GET", "DELETE", "OPTIONS"], strict_slashes=False)
def factory_instance(type_key, iid):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, DELETE")
    if request.method == "DELETE":
        return _fac_do(lambda: (_factory.delete(type_key, iid), {"deleted": iid})[1])
    return _fac_do(lambda: {"instance": _factory.factory.get(type_key, iid), "company": _factory.company_status(iid)}, admin=False)


@app.route("/api/factory/instances/<type_key>/<iid>/<action>", methods=["POST", "OPTIONS"], strict_slashes=False)
def factory_action(type_key, iid, action):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    d = request.get_json(silent=True) or {}
    acts = {"build": lambda: {"build": _factory.build(type_key, iid)}, "deploy": lambda: _factory.deploy(type_key, iid), "stop": lambda: _factory.stop(type_key, iid),
            "run": lambda: {"runs": _factory.run_once(type_key, iid, str(d.get("bot") or ""))}}
    if action not in acts:
        return _json_cors({"status": "error", "message": "unknown action"}, 404)
    return _fac_do(acts[action])


@app.route("/api/factory/<iid>/preview/", defaults={"sub": ""}, methods=["GET"])
@app.route("/api/factory/<iid>/preview/<path:sub>", methods=["GET"])
def factory_preview(iid, sub):
    """The built site or environment, served from the instance's own folder (nothing outside it can be reached)."""
    if _factory is None or not re.fullmatch(r"fi-[0-9a-f]{12}", iid):
        return _json_cors({"status": "error", "message": "not found"}, 404)
    rec = _fac_find(iid)
    root = _factory.preview_root(rec["type"], iid) if rec else None
    if root is None:
        return _json_cors({"status": "error", "message": "nothing is built for that instance yet"}, 404)
    return send_from_directory(str(root), sub or "index.html")


@app.route("/api/factory/<iid>/inbox", methods=["POST", "OPTIONS"], strict_slashes=False)
def factory_inbox_post(iid):
    """Where a generated site sends its contact messages and order requests. Stored in the instance's folder; nothing is forwarded anywhere."""
    if request.method == "OPTIONS":
        return _cors_options("POST")
    rec = _fac_find(iid) if (_factory is not None and re.fullmatch(r"fi-[0-9a-f]{12}", iid)) else None
    if rec is None or rec["type"] != "platform_factory" or rec.get("state") != "built":
        return _json_cors({"status": "error", "message": "this site is not accepting messages"}, 404)
    if (request.content_length or 0) > 6000:
        return _json_cors({"status": "error", "message": "too large"}, 413)
    d = request.get_json(silent=True) or {}
    entry = {k: str(d.get(k) or "").strip()[:1000] for k in ("name", "email", "message", "item", "quantity")}
    if not entry["name"] or not entry["message"] or "@" not in entry["email"]:
        return _json_cors({"status": "error", "message": "name, a valid email and a message are required"}, 400)
    f = _factory.factory.workdir(rec["type"], iid) / "inbox.jsonl"
    with _factory._lock:
        n = len(f.read_text(encoding="utf-8").splitlines()) if f.is_file() else 0
        if n >= 1000:
            return _json_cors({"status": "error", "message": "the inbox is full"}, 429)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(entry, at=round(time.time(), 1))) + "\n")
    return _json_cors({"status": "success"}, 201)


@app.route("/api/factory/instances/<type_key>/<iid>/inbox", methods=["GET", "OPTIONS"], strict_slashes=False)
def factory_inbox_read(type_key, iid):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    def read():
        f = _factory.factory.workdir(type_key, iid) / "inbox.jsonl"
        return {"entries": [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()][-200:] if f.is_file() else []}
    return _fac_do(read)


@app.route("/api/factory/lab/<what>", methods=["POST", "OPTIONS"], strict_slashes=False)
def factory_lab_run(what):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    d = request.get_json(silent=True) or {}
    runs = {"demo": lambda: {"result": _factory_lab.demo(_factory, d.get("type"))}, "stress": lambda: {"result": _factory_lab.stress(d.get("type"), d.get("level", "heavy"))},
            "isolation": lambda: {"result": _factory_lab.isolation(_factory)}}
    if what not in runs:
        return _json_cors({"status": "error", "message": "unknown lab run"}, 404)
    return _fac_do(runs[what])


def _fac_image_to_3d(url, title, allow_loopback=False):
    """Fetch a real image from a web address, file it in the Creations hub, stage it as a textured panel in a spatial environment, build and check that environment.
    -> {"instance", "creation_id", "preview", "steps": [...]}: every step with its own result and timing, so nothing is claimed that did not happen."""
    import image_ingest as _ii
    title = str(title or "").strip()
    if not title:
        raise _ft.FactoryError("name the image (what it shows): the name is needed so it can be filed and shown")
    steps, t0 = [], time.perf_counter()
    got = _ii.fetch(url, allow_loopback=allow_loopback)
    steps += got["steps"]
    t = time.perf_counter()
    meta = _creations.save(title[:120], [{"name": "image." + got["ext"], "data": got["data"]}], source="web image", prompt=got["url"], job_id=None)
    steps.append({"step": "save", "ok": True, "creation_id": meta["id"], "bytes": len(got["data"]), "ms": round((time.perf_counter() - t) * 1000, 1)})
    aspect = got["height"] / got["width"]
    width = 6.0
    cfg = {"title": title[:80], "ground": 24, "objects": [{"shape": "panel", "size": [width], "position": [0, round(width * aspect / 2 + 0.4, 3), 6], "texture": meta["id"]}],
           "lights": [{"type": "hemispheric", "intensity": 0.9}], "player": {"start": [0, 1.7, -6], "speed": 5, "height": 1.7}}
    t = time.perf_counter()
    rec = _factory.create("spatial_environment", ("Image to 3D: " + title)[:80], cfg)
    steps.append({"step": "texture_bind", "ok": True, "detail": "the saved image is the texture of a %.1f x %.2f m panel (proportions taken from the image: %dx%d)" % (width, width * aspect, got["width"], got["height"]),
                  "ms": round((time.perf_counter() - t) * 1000, 1)})
    t = time.perf_counter()
    build = _factory.build("spatial_environment", rec["id"])
    steps.append({"step": "viewport_inject", "ok": build["ok"], "detail": "built into the spatial-environment viewport and self-checked (page parses, scene reads back identical, texture file matches its source)",
                  "problems": build["problems"], "ms": round((time.perf_counter() - t) * 1000, 1)})
    out = {"instance": rec["id"], "creation_id": meta["id"], "preview": "/api/factory/%s/preview/" % rec["id"], "source_url": got["url"], "image": {"width": got["width"], "height": got["height"], "bytes": len(got["data"]), "sha256": got["sha256"], "scaled": got["scaled"]},
           "steps": steps, "total_ms": round((time.perf_counter() - t0) * 1000, 1)}
    if _factory_lab is not None:
        _factory_lab._record({"kind": "image_to_3d", "type": "spatial_environment", "ok": build["ok"], "source": got["url"], "bytes": len(got["data"]), "width": got["width"], "height": got["height"], "total_ms": out["total_ms"],
                              "measured": "a real fetch, a real file in the Creations hub, a built and self-checked scene; not measured here: how it looks on your screen (open the preview)"})
    return out


@app.route("/api/factory/image-to-3d", methods=["POST", "OPTIONS"], strict_slashes=False)
def factory_image_to_3d():
    """Owner gives a web address and a name; the image is fetched from it and staged as an interactive textured panel. Needs the admin token."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    import image_ingest as _ii
    d = request.get_json(silent=True) or {}
    loop = bool(os.environ.get("NEXXUS_INGEST_ALLOW_LOOPBACK") == "1")      # only ever set by the tests
    def run():
        try:
            return _fac_image_to_3d(d.get("url"), d.get("title"), allow_loopback=loop)
        except _ii.IngestError as e:
            raise _ft.FactoryError(str(e))
    return _fac_do(run, 201)


@app.route("/api/factory/telemetry", methods=["GET", "OPTIONS"], strict_slashes=False)
def factory_telemetry():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    return _fac_do(lambda: {"telemetry": _factory_lab.telemetry(int(request.args.get("limit", 50)))}, admin=False)


# ═══════════════════════════════════════════════════════
# 3D STAGING: open an image from the Creations hub in the staging view, edit a private working copy with the toolkit (crop, trim, subject isolation, alpha mask, depth), and sync the result back
# to the hub as a new linked version. See stage_sessions.py / image_tools.py. Changes need the admin token; the picture of an open session is served to the viewer by its unguessable session id.
# ═══════════════════════════════════════════════════════
try:
    import stage_sessions as _ss
    import image_tools as _it
    _stager = _ss.Stager()
except Exception as _e_stage:
    _ss = _it = _stager = None
    print("[STAGING] unavailable: %s: %s" % (type(_e_stage).__name__, _e_stage))

_STAGE_RASTER = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def _stage_guard():
    if _stager is None or _creations is None:
        return _json_cors({"status": "error", "message": "staging is not available (it needs the Creations hub, Pillow, numpy and scipy)"}, 503)
    return None


def _stage_do(fn, ok=200, admin=True):
    bad = _stage_guard()
    if bad:
        return bad
    if admin:
        denied = _require_vault_admin()
        if denied:
            return denied
    try:
        return _json_cors(dict({"status": "success"}, **fn()), ok)
    except (_ss.StageError, _it.ToolError) as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)


def _stage_title(parent):
    if _creation is not None:
        try:
            return _creation._next_title(parent.get("title"), int(parent.get("version", 1)))
        except Exception as e:
            raise _ss.StageError(str(e))
    return parent.get("title")


@app.route("/api/stage/open", methods=["POST", "OPTIONS"], strict_slashes=False)
def stage_open():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    d = request.get_json(silent=True) or {}

    def run():
        cid = str(d.get("creation_id") or "")
        meta = _creations.get(cid) if (_cv_mod is not None and _cv_mod.ID_RE.match(cid)) else None
        if not meta:
            raise _ss.StageError("that creation is not in the Creations hub")
        f = next((x for x in meta["files"] if x["name"].lower().endswith(_STAGE_RASTER)), None)
        p = _creations.file_path(meta["id"], f["name"]) if f else None
        if p is None:
            raise _ss.StageError("only picture creations (png, jpg, gif, webp) can be staged; this one is %s" % meta.get("kind"))
        s = _stager.open(meta, _it.to_png(_it.load(Path(p).read_bytes())))
        return dict(s.state(), image_url="/api/stage/%s/image" % s.id)
    return _stage_do(run)


@app.route("/api/stage/<sid>/<action>", methods=["POST", "OPTIONS"], strict_slashes=False)
def stage_action(sid, action):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    d = request.get_json(silent=True) or {}

    def with_state(s, **extra):
        return dict(s.state(), image_url="/api/stage/%s/image?v=%d" % (s.id, s.version), depth_url=("/api/stage/%s/depth?v=%d" % (s.id, s.version)) if s.depth is not None else None, **extra)

    def finalize():
        meta = _stager.finalize(sid, _creations, _stage_title, "depth-map.png")
        try:
            if _notes is not None:
                _notes.add("creation", "Staged asset saved: " + meta["title"], "Saved to the Creations hub as a new version; the original is unchanged.")
        except Exception:
            pass
        return {"creation": meta}
    acts = {"apply": lambda: with_state(_stager.apply(sid, d.get("tool"), d.get("params"))), "undo": lambda: with_state(_stager.undo(sid)), "reset": lambda: with_state(_stager.reset(sid)),
            "finalize": finalize, "close": lambda: (_stager.close(sid), {"closed": True})[1]}
    if action not in acts:
        return _json_cors({"status": "error", "message": "unknown action"}, 404)
    return _stage_do(acts[action])


@app.route("/api/stage/<sid>/<what>", methods=["GET"])
def stage_picture(sid, what):
    if what not in ("image", "depth") or not re.fullmatch(r"st-[0-9a-f]{12}", sid):
        return _json_cors({"status": "error", "message": "not found"}, 404)
    bad = _stage_guard()
    if bad:
        return bad
    try:
        data = _stager.image(sid) if what == "image" else _stager.depth(sid)
    except _ss.StageError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)
    resp = make_response(data)
    resp.headers["Content-Type"] = "image/png"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


# ═══════════════════════════════════════════════════════
# REMOTE ACCESS (Tailscale, phones): who may connect, a heartbeat, a live "something changed" stream, and a command queue that lives on the host so every device sees the same one.
# See net_bind.py. The stream carries counters and ids only, never content: a device that hears "creations changed" asks the normal (token-protected) routes for the details.
# ═══════════════════════════════════════════════════════
try:
    import net_bind as _net
except Exception as _e_net:
    _net = None
    print("[NET] unavailable: %s: %s" % (type(_e_net).__name__, _e_net))
_listeners = None
import hmac
import urllib.parse
import secrets
_BOOT_ID = "b" + secrets.token_hex(4)


@app.before_request
def _peer_guard():
    """Three locks, in order. 1) Only this machine and its Tailscale peers (and the private LAN if NEXXUS_ALLOW_LAN=1) are served at all.
    2) A request that CHANGES something and comes from another web page (a browser sends an Origin that is not this server) is refused: no site you visit can drive the dashboard.
    3) A request that changes something and comes over the network (a Tailscale device, or a request the tunnel proxy forwarded) needs the admin token, except the chat and screen plumbing listed in
       _REMOTE_OPEN. From this machine's own page nothing changes: those routes work as before."""
    if _net is not None and not _net.peer_allowed(request.remote_addr):
        return _json_cors({"status": "error", "message": "this address is not allowed to use the dashboard (only this machine and its Tailscale devices are)"}, 403)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("Origin")
        if origin and not _re_inbox.match(request.path):
            host = (urllib.parse.urlsplit(origin).netloc or "").lower()
            if host != (request.host or "").lower():
                return _json_cors({"status": "error", "message": "refused: this request came from another web page, not from the dashboard"}, 403)
        remote = not _net.is_loopback(request.remote_addr) or "X-Forwarded-For" in request.headers or "Tailscale-User-Login" in request.headers if _net is not None else False
        if remote and not any(rx.match(request.path) for rx in _REMOTE_OPEN):
            tok = request.headers.get("X-Nexxus-Admin-Token") or ""
            if not VAULT_ADMIN_TOKEN or not hmac.compare_digest(tok.encode("utf-8"), VAULT_ADMIN_TOKEN.encode("utf-8")):
                return _json_cors({"status": "error", "message": "from another device this needs the admin token (unlock it with the lock button in the header)"}, 401)
    return None


# Changes a device may make over the network WITHOUT the token: the chat and the screens' own plumbing, plus calls that authenticate themselves (engines sign their messages; a published site's visitors
# post to its inbox). Everything else that changes anything needs the admin token when it does not come from this machine's own page.
_REMOTE_OPEN = [re.compile(x) for x in (r"^/command-dispatch$", r"^/bridge$", r"^/api/get-chat$", r"^/search$", r"^/status$", r"^/status-recheck$", r"^/save-session$", r"^/speech-toggle$", r"^/flush-buffer$",
                                      r"^/api/telemetry/ping$", r"^/api/notifications/read$", r"^/api/desk/(chat|search|reset|nexxus|link|widget)$", r"^/api/portals/chat(/reset)?$", r"^/api/portals/dispatch/preview$",
                                      r"^/api/factory/fi-[0-9a-f]{12}/inbox$", r"^/api/bus/message$", r"^/api/bus/poll$", r"^/api/mesh/(message|status|peers)$", r"^/api/dispatch-queue.*$")]
_re_inbox = re.compile(r"^/api/factory/fi-[0-9a-f]{12}/inbox$")


@app.route("/api/ping", methods=["GET", "OPTIONS"], strict_slashes=False)
def net_ping():
    """The heartbeat a device uses to know the tunnel is alive. The boot id changes only when the server restarts, so a device can tell 'slow network' from 'the host restarted'."""
    if request.method == "OPTIONS":
        return _cors_options("GET")
    r = _json_cors({"status": "success", "t": round(time.time(), 3), "boot": _BOOT_ID})
    r.headers["Cache-Control"] = "no-store"
    return r


@app.route("/api/net/status", methods=["GET", "OPTIONS"], strict_slashes=False)
def net_status():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    st = _listeners.status() if _listeners is not None else {"spec": "loopback", "port": BRIDGE_PORT, "listeners": {"127.0.0.1": {"ok": True}}, "problems": [], "tailscale_addresses": _net.tailscale_addresses() if _net else []}
    return _json_cors(dict(st, status="success", you=request.remote_addr, boot=_BOOT_ID, stream_clients=_sse["clients"]))


# ---- the host-side command queue ----
_dq_lock = threading.RLock()
_DQ_FILE = Path(os.environ.get("NEXXUS_DISPATCH_QUEUE") or (Path(__file__).resolve().parent / "dispatch_queue.json"))
_DQ_MAX, _DQ_TEXT = 50, 4000


def _dq_load():
    try:
        d = json.loads(_DQ_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and isinstance(d.get("items"), list) else {"version": 0, "items": []}
    except (OSError, ValueError):
        return {"version": 0, "items": []}


def _dq_save(d):
    d["version"] = int(d.get("version", 0)) + 1
    tmp = _DQ_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    os.replace(tmp, _DQ_FILE)


def _dq_do(fn, ok=200):
    denied = _require_vault_admin()
    if denied:
        return denied
    with _dq_lock:
        try:
            return _json_cors(dict({"status": "success"}, **fn()), ok)
        except ValueError as e:
            return _json_cors({"status": "error", "message": str(e)}, 400)


@app.route("/api/dispatch-queue", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def dispatch_queue_collection():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    d = request.get_json(silent=True) or {}

    def get():
        q = _dq_load()
        return {"items": q["items"], "version": q["version"]}

    def add():
        text = str(d.get("text") or "").strip()
        if not text:
            raise ValueError("there is nothing to queue")
        if len(text) > _DQ_TEXT:
            raise ValueError("a queued command is limited to %d characters" % _DQ_TEXT)
        q = _dq_load()
        iid = re.sub(r"[^a-z0-9]", "", str(d.get("id") or "").lower())[:20] or secrets.token_hex(6)
        if any(i["id"] == iid for i in q["items"]):
            return {"items": q["items"], "version": q["version"], "duplicate": True}      # a device re-sending after a dropped connection does not queue twice
        if len(q["items"]) >= _DQ_MAX:
            raise ValueError("the queue is full (%d)" % _DQ_MAX)
        q["items"].append({"id": iid, "text": text, "at": round(time.time(), 3), "device": str(d.get("device") or "")[:40]})
        _dq_save(q)
        return {"items": q["items"], "version": q["version"]}
    return _dq_do(get if request.method == "GET" else add, 200 if request.method == "GET" else 201)


@app.route("/api/dispatch-queue/<what>", methods=["POST", "DELETE", "OPTIONS"], strict_slashes=False)
def dispatch_queue_item(what):
    """POST /next: take the first item off the queue and hand it to the caller (exactly one device gets it). POST /clear: empty it. DELETE /<id>: remove one."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST, DELETE")

    def run():
        q = _dq_load()
        if request.method == "DELETE":
            q["items"] = [i for i in q["items"] if i["id"] != what]
            _dq_save(q)
            return {"items": q["items"], "version": q["version"]}
        if what == "clear":
            q["items"] = []
            _dq_save(q)
            return {"items": [], "version": q["version"]}
        if what == "next":
            if not q["items"]:
                return {"item": None, "items": [], "version": q["version"]}
            item = q["items"].pop(0)
            _dq_save(q)
            return {"item": item, "items": q["items"], "version": q["version"]}
        raise ValueError("unknown queue action")
    return _dq_do(run)


# ---- the live stream (Server-Sent Events: plain HTTP, so it passes through the tunnel and the browser reconnects it by itself) ----
_sse = {"clients": 0, "lock": threading.Lock(), "conns": []}
_SSE_MAX_CLIENTS, _SSE_MAX_SECONDS, _SSE_TICK, _SSE_HEARTBEAT, _SSE_PER_ADDR = 24, 1800, 1.0, 10, 3


def _sse_signals():
    """name -> a small value that changes when that thing changes. Counters and ids only."""
    sig = {}
    try:
        if _notes is not None:
            n = _notes.list()
            sig["notifications"] = {"unread": n["unread"], "total": n["total"]}
        if _creations is not None:
            c = _creations.list()
            sig["creations"] = {"count": len(c), "newest": (c[0]["id"] if c else None)}
        if _input_queue is not None:
            s = _input_queue.snapshot()
            sig["input_queue"] = {k: s.get(k) for k in ("state", "used", "served", "turned_away")}
        sig["dispatch_queue"] = {"version": _dq_load()["version"]}
        if _publish is not None:
            sig["publish"] = {"items": len(_publish.list())}
        if _factory_lab is not None:
            sig["factory"] = {"telemetry_bytes": _factory_lab.log.stat().st_size if _factory_lab.log.is_file() else 0}
        _tl = globals().get("_tools")
        if _tl is not None and getattr(_tl, "LOG", None) is not None:
            sig["tools_log"] = {"bytes": _tl.LOG.stat().st_size if _tl.LOG.is_file() else 0}
    except Exception as e:                                                       # one broken source must not silence the others
        sig["probe_error"] = type(e).__name__
    return sig


@app.route("/api/events", methods=["GET"])
def net_events():
    conn = {"addr": request.remote_addr, "evict": threading.Event()}
    with _sse["lock"]:
        mine = [c for c in _sse["conns"] if c["addr"] == conn["addr"]]
        while len(mine) >= _SSE_PER_ADDR:                       # a device that reconnects (Wi-Fi to cellular) replaces its own stale connection instead of being locked out by it
            old = mine.pop(0)
            old["evict"].set()
            _sse["conns"].remove(old)
            _sse["clients"] -= 1
        if _sse["clients"] >= _SSE_MAX_CLIENTS:
            return _json_cors({"status": "error", "message": "too many live connections (%d); close another device's page" % _SSE_MAX_CLIENTS}, 429)
        _sse["conns"].append(conn)
        _sse["clients"] += 1

    def gen():
        seq, t0 = 1, time.time()
        try:
            yield "retry: 3000\n\n"
            last = _sse_signals()
            hb = time.time()
            yield "id: 1\nevent: hello\ndata: %s\n\n" % json.dumps({"signals": last, "boot": _BOOT_ID})
            while time.time() - t0 < _SSE_MAX_SECONDS and not conn["evict"].is_set():
                time.sleep(_SSE_TICK)
                cur, now = _sse_signals(), time.time()
                for name, val in cur.items():
                    if last.get(name) != val:
                        seq += 1
                        hb = now
                        yield "id: %d\nevent: %s\ndata: %s\n\n" % (seq, name, json.dumps(val))
                last = cur
                if now - hb >= _SSE_HEARTBEAT:
                    hb = now
                    yield ": hb %d\n\n" % int(now)
        finally:
            with _sse["lock"]:
                if conn in _sse["conns"]:                       # (an evicted connection was already counted out)
                    _sse["conns"].remove(conn)
                    _sse["clients"] -= 1
    from flask import Response as _Response
    r = _Response(gen(), mimetype="text/event-stream")
    r.headers["Cache-Control"] = "no-cache, no-transform"
    r.headers["X-Accel-Buffering"] = "no"
    r.headers["Access-Control-Allow-Origin"] = "*"
    return r


# ═══════════════════════════════════════════════════════
# OPPORTUNITY DESK: real funding opportunities (official Grants.gov API or added by hand), checked against your entity vault, a questionnaire for what is missing, and, after your sign-off, an accurate
# application packet that you submit yourself. See opportunity_desk.py. Every route needs the admin token (it is your organisation's business data). Nothing here submits, registers or files anything.
# ═══════════════════════════════════════════════════════
try:
    import opportunity_desk as _od
    _opps = _od.Desk(os.environ.get("NEXXUS_OPPS_DIR") or (Path(__file__).resolve().parent / "opportunity_data"))
except Exception as _e_opps:
    _od = _opps = None
    print("[OPPORTUNITIES] unavailable: %s: %s" % (type(_e_opps).__name__, _e_opps))


def _opp_do(fn, ok=200):
    denied = _require_vault_admin()
    if denied:
        return denied
    if _opps is None:
        return _json_cors({"status": "error", "message": "the opportunity desk is not available"}, 503)
    try:
        return _json_cors(dict({"status": "success"}, **fn()), ok)
    except _od.DeskError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)


@app.route("/api/opps", methods=["GET", "OPTIONS"], strict_slashes=False)
def opps_list():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    return _opp_do(lambda: {"opportunities": _opps.list(), "ledger_ok": _opps.verify_ledger()[0]})


@app.route("/api/opps/vault", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def opps_vault():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    d = request.get_json(silent=True) or {}
    if request.method == "GET":
        return _opp_do(lambda: {"fields": _od.FIELDS, "data": _opps.vault.snapshot(), "missing_required": _opps.vault.missing_required()})
    return _opp_do(lambda: {"data": _opps.vault.update(d.get("facts")), "missing_required": _opps.vault.missing_required()})


@app.route("/api/opps/search", methods=["POST", "OPTIONS"], strict_slashes=False)
def opps_search():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    d = request.get_json(silent=True) or {}
    return _opp_do(lambda: _opps.search(d.get("keyword"), d.get("rows", 10)))


@app.route("/api/opps/fetch", methods=["POST", "OPTIONS"], strict_slashes=False)
def opps_fetch():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    d = request.get_json(silent=True) or {}
    return _opp_do(lambda: {"opportunity": _opps.fetch(d.get("id"))}, 201)


@app.route("/api/opps/add", methods=["POST", "OPTIONS"], strict_slashes=False)
def opps_add():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    d = request.get_json(silent=True) or {}
    return _opp_do(lambda: {"opportunity": _opps.add_manual(d)}, 201)


@app.route("/api/opps/<oid>", methods=["GET", "OPTIONS"], strict_slashes=False)
def opps_one(oid):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    return _opp_do(lambda: _opps.analyze(oid))


@app.route("/api/opps/<oid>/<action>", methods=["POST", "OPTIONS"], strict_slashes=False)
def opps_action(oid, action):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    d = request.get_json(silent=True) or {}
    acts = {"answer": lambda: _opps.answer(oid, d.get("facts"), d.get("documents")), "signoff": lambda: {"signoff": _opps.sign_off(oid, d.get("name"), d.get("confirm"))},
            "compile": lambda: _opps.compile(oid)}
    if action not in acts:
        return _json_cors({"status": "error", "message": "unknown action"}, 404)
    return _opp_do(acts[action])


@app.route("/api/opps/packet/<packet>/<name>", methods=["GET", "OPTIONS"], strict_slashes=False)
def opps_packet_file(packet, name):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _require_vault_admin()
    if denied:
        return denied
    if _opps is None:
        return _json_cors({"status": "error", "message": "the opportunity desk is not available"}, 503)
    try:
        p = _opps.packet_file(packet, name)
    except _od.DeskError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    r = make_response(p.read_bytes())
    r.headers["Content-Type"] = "text/html; charset=utf-8" if name.endswith(".html") else "text/plain; charset=utf-8"
    r.headers["Content-Disposition"] = 'attachment; filename="%s"' % name
    r.headers["X-Content-Type-Options"] = "nosniff"
    return r


# ═══════════════════════════════════════════════════════
# CAMPAIGN KIT: a go-to-market kit for one real business (scripts, channel-checked ad copy, a compliant email sequence, branded graphics, a landing page, a narrated video) and an approval-gated
# queue. See campaign_kit.py, campaign_media.py, campaign_queue.py. Every route needs the admin token. Nothing here posts anywhere: approved items are EXPORTED as ready-to-post packages.
# ═══════════════════════════════════════════════════════
try:
    import campaign_kit as _ck
    import campaign_media as _cm
    import campaign_queue as _cq
    _camp_dir = Path(os.environ.get("NEXXUS_CAMPAIGN_DIR") or (Path(__file__).resolve().parent / "campaign_data"))
    _camp_dir.mkdir(parents=True, exist_ok=True)
    _camp_queue = _cq.CampaignQueue(_camp_dir / "queue")
except Exception as _e_camp:
    _ck = _cm = _cq = _camp_queue = None
    print("[CAMPAIGNS] unavailable: %s: %s" % (type(_e_camp).__name__, _e_camp))


def _camp_do(fn, ok=200):
    denied = _require_vault_admin()
    if denied:
        return denied
    if _ck is None:
        return _json_cors({"status": "error", "message": "the campaign kit is not available"}, 503)
    try:
        return _json_cors(dict({"status": "success"}, **fn()), ok)
    except (_ck.CampaignError, _cm.MediaError, _cq.QueueError) as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)


def _camp_kit_dir(kid):
    if not re.fullmatch(r"kit-[0-9a-f]{10}", str(kid)):
        raise _ck.CampaignError("not a valid kit id")
    d = _camp_dir / kid
    if not (d / "kit.json").is_file():
        raise _ck.CampaignError("no such kit")
    return d


def _camp_local_model():
    """A local-model rewrite function when Ollama answers; None otherwise (the template copy is used, and the kit says so)."""
    try:
        import urllib.request as _ur
        url = (os.environ.get("NEXXUS_OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
        model = os.environ.get("NEXXUS_CHAT_MODEL") or "phi4-mini"
        def ask(prompt):
            req = _ur.Request(url + "/api/generate", data=json.dumps({"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.4}}).encode(), headers={"Content-Type": "application/json"})
            with _ur.urlopen(req, timeout=120) as r:
                return json.loads(r.read()).get("response", "")
        return ask
    except Exception:
        return None


@app.route("/api/campaigns", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def campaigns_collection():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    d = request.get_json(silent=True) or {}

    def lst():
        out = []
        for k in sorted(_camp_dir.glob("kit-*")):
            try:
                m = json.loads((k / "kit.json").read_text(encoding="utf-8"))
                out.append({"id": k.name, "business": m["profile"]["name"], "source": m.get("source"), "videos": sorted(p.name for p in (k / "video").glob("*.mp4")) if (k / "video").is_dir() else []})
            except (OSError, ValueError, KeyError):
                continue
        return {"kits": out, "voices": _cm.list_voices(), "queue_ledger_ok": _camp_queue.verify_ledger()[0]}

    def make():
        kit = _ck.generate(d.get("profile"), llm=_camp_local_model() if d.get("use_model") else None)
        kid = "kit-" + uuid.uuid4().hex[:10]
        folder = _camp_dir / kid
        man = _ck.write_kit(folder, kit)
        (folder / "kit.json").write_bytes(json.dumps(kit, indent=1).encode("utf-8"))
        return {"id": kid, "kit": kit, "manifest": man}
    return _camp_do(lst if request.method == "GET" else make, 200 if request.method == "GET" else 201)


@app.route("/api/campaigns/<kid>", methods=["GET", "OPTIONS"], strict_slashes=False)
def campaign_one(kid):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    return _camp_do(lambda: {"kit": json.loads((_camp_kit_dir(kid) / "kit.json").read_text(encoding="utf-8")), "manifest": json.loads((_camp_kit_dir(kid) / "manifest.json").read_text(encoding="utf-8"))})


@app.route("/api/campaigns/<kid>/video", methods=["POST", "OPTIONS"], strict_slashes=False)
def campaign_video(kid):
    """Render a narrated commercial for one of the kit's scripts. Takes 20 to 60 seconds."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    d = request.get_json(silent=True) or {}

    def make():
        folder = _camp_kit_dir(kid)
        kit = json.loads((folder / "kit.json").read_text(encoding="utf-8"))
        fmt = str(d.get("format") or "social_15s")
        if fmt not in kit["video_scripts"]:
            raise _ck.CampaignError("format must be one of: %s" % ", ".join(kit["video_scripts"]))
        rep = _cm.make_commercial(kit["profile"], kit["video_scripts"][fmt], folder / "video" / (fmt + ".mp4"), d.get("voice") or None, d.get("mood") or "warm", int(d.get("seed") or 1))
        rep["path"] = "video/%s.mp4" % fmt
        return {"video": rep}
    return _camp_do(make)


@app.route("/api/campaigns/<kid>/file/<path:rel>", methods=["GET", "OPTIONS"], strict_slashes=False)
def campaign_file(kid, rel):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _require_vault_admin()
    if denied:
        return denied
    if _ck is None:
        return _json_cors({"status": "error", "message": "the campaign kit is not available"}, 503)
    try:
        folder = _camp_kit_dir(kid).resolve()
    except _ck.CampaignError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    p = (folder / rel).resolve()
    if folder not in p.parents or not p.is_file() or p.suffix.lower() not in (".png", ".mp4", ".html", ".json", ".md"):
        return _json_cors({"status": "error", "message": "not a kit file"}, 404)
    r = make_response(p.read_bytes())
    r.headers["Content-Type"] = {".png": "image/png", ".mp4": "video/mp4", ".html": "text/plain; charset=utf-8", ".json": "application/json", ".md": "text/plain; charset=utf-8"}[p.suffix.lower()]
    r.headers["X-Content-Type-Options"] = "nosniff"
    return r


@app.route("/api/campaigns/queue", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def campaign_queue_collection():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    d = request.get_json(silent=True) or {}

    def stage():
        folder = _camp_kit_dir(d.get("kit"))
        kit = json.loads((folder / "kit.json").read_text(encoding="utf-8"))
        return {"item": _camp_queue.stage(folder, kit, d.get("channel"), d.get("files"), d.get("title"), d.get("video"))}
    return _camp_do(lambda: {"items": _camp_queue.list()} if request.method == "GET" else stage(), 200 if request.method == "GET" else 201)


@app.route("/api/campaigns/queue/<iid>/<action>", methods=["POST", "OPTIONS"], strict_slashes=False)
def campaign_queue_action(iid, action):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    d = request.get_json(silent=True) or {}
    acts = {"approve": lambda: {"item": _camp_queue.approve(iid, d.get("scheduled_at") or None)}, "export": lambda: {"item": _camp_queue.export(iid)}, "cancel": lambda: {"item": _camp_queue.cancel(iid)}}
    if action not in acts:
        return _json_cors({"status": "error", "message": "unknown action"}, 404)
    return _camp_do(acts[action])


try:
    import domain_dispatch as _domain_dispatch
except Exception as _e_dd:
    _domain_dispatch = None
    print("[DOMAIN COURIER] unavailable: %s: %s" % (type(_e_dd).__name__, _e_dd))


@app.route("/api/portals/dispatch", methods=["GET", "OPTIONS"], strict_slashes=False)
def portals_dispatch_status():
    """The courier's settings and whether each hub's own port is answering right now."""
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if _domain_dispatch is None:
        return _json_cors({"status": "error", "message": "the domain courier is not available (domain_dispatch.py is missing)"}, 503)
    cfg = _domain_dispatch.config()
    for dom, h in cfg["hubs"].items():
        try:
            with urllib.request.urlopen(h["url"].replace("/chat", "/health"), timeout=1.5) as r:
                h["up"] = r.status == 200
        except Exception:
            h["up"] = False
    return _json_cors(dict(cfg, status="success"))


@app.route("/api/portals/dispatch/preview", methods=["POST", "OPTIONS"], strict_slashes=False)
def portals_dispatch_preview():
    """Where WOULD this prompt go? Nothing is sent."""
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if _domain_dispatch is None:
        return _json_cors({"status": "error", "message": "the domain courier is not available"}, 503)
    d = request.get_json(silent=True)
    if not isinstance(d, dict) or not isinstance(d.get("message"), str):
        return _json_cors({"status": "error", "message": "send {\"message\": \"...\"}"}, 400)
    dom, why = _domain_dispatch.target(d["message"])
    return _json_cors({"status": "success", "route": dom or "standard", "why": why, "enabled": _domain_dispatch.enabled()})


@app.route("/api/portals/chat", methods=["POST", "OPTIONS"], strict_slashes=False)
def portals_chat():
    """One turn in ONE hub's own domain-locked chat. The hub is named by the page; the server gates, prompts and filters it (see portal_chat.py). Nothing here touches the main chat's session."""
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if _pchat is None:
        return _json_cors({"status": "error", "message": "the hub chats are not available (portal_chat.py is missing)"}, 503)
    d = request.get_json(silent=True)
    if not isinstance(d, dict) or not isinstance(d.get("portal"), str) or not isinstance(d.get("message"), str):
        return _json_cors({"status": "error", "message": "send {\"portal\": \"sports|markets|logistics|economics\", \"message\": \"...\"}"}, 400)
    try:
        res = _pchat.chat(d["portal"], d["message"])
    except _portals.PortalError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    return _json_cors(dict(res, status="busy" if res["kind"] == "busy" else "success"), 429 if res["kind"] == "busy" else 200)


@app.route("/api/portals/chat/reset", methods=["POST", "OPTIONS"], strict_slashes=False)
def portals_chat_reset():
    """Forget one hub's conversation (and only that hub's)."""
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if _pchat is None:
        return _json_cors({"status": "error", "message": "the hub chats are not available"}, 503)
    d = request.get_json(silent=True)
    if not isinstance(d, dict) or d.get("portal") not in _portals.ORDER:
        return _json_cors({"status": "error", "message": "name the hub to clear"}, 400)
    _pchat.reset(d["portal"])
    return _json_cors({"status": "success", "portal": d["portal"]})


# ---- Engine desks (every engine that is not one of the four portals): local chat, search pipeline, NEXXUS two-step bridge, widget generation. See desk_bridge.py ----
try:
    import desk_bridge as _desk
except Exception as _e_desk:
    _desk = None
    print("[ENGINE DESKS] unavailable: %s: %s" % (type(_e_desk).__name__, _e_desk))


def _desk_call(fn_name, keys):
    """Shared shell for the desk routes: CORS, JSON body check, DeskError -> 400."""
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if _desk is None:
        return _json_cors({"status": "error", "message": "the engine desks are not available (desk_bridge.py is missing)"}, 503)
    d = request.get_json(silent=True)
    if not isinstance(d, dict) or not all(isinstance(d.get(k), str) for k in keys):
        return _json_cors({"status": "error", "message": "send {%s}" % ", ".join('"%s": "..."' % k for k in keys)}, 400)
    try:
        res = getattr(_desk, fn_name)(*[d[k] for k in keys])
    except _desk.DeskError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    return _json_cors(dict(res or {}, status="busy" if (res or {}).get("kind") == "busy" else "success"), 429 if (res or {}).get("kind") == "busy" else 200)


@app.route("/api/desk/engines", methods=["GET", "OPTIONS"], strict_slashes=False)
def desk_engines():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if _desk is None:
        return _json_cors({"status": "error", "message": "the engine desks are not available"}, 503)
    return _json_cors({"status": "success", "engines": _desk.catalog(), "web_search": _desk.portal_chat.web_enabled()})


@app.route("/api/desk/chat", methods=["POST", "OPTIONS"], strict_slashes=False)
def desk_chat():
    return _desk_call("chat_local", ["engine", "message"])


@app.route("/api/desk/nexxus", methods=["POST", "OPTIONS"], strict_slashes=False)
def desk_nexxus():
    return _desk_call("nexxus_answer", ["engine", "message"])


@app.route("/api/desk/search", methods=["POST", "OPTIONS"], strict_slashes=False)
def desk_search_route():
    return _desk_call("desk_search", ["engine", "query"])


@app.route("/api/desk/widget", methods=["POST", "OPTIONS"], strict_slashes=False)
def desk_widget():
    return _desk_call("make_widget", ["engine", "prompt"])


@app.route("/api/desk/link", methods=["POST", "OPTIONS"], strict_slashes=False)
def desk_link():
    """The Linked Room: the engine talks about its own status through the LLM. The live picture (telemetry, mesh heartbeat, declared utilities) comes from the diagnostics hub, never from the page."""
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if _desk is None:
        return _json_cors({"status": "error", "message": "the engine desks are not available (desk_bridge.py is missing)"}, 503)
    d = request.get_json(silent=True)
    if not isinstance(d, dict) or not isinstance(d.get("engine"), str) or not isinstance(d.get("message"), str):
        return _json_cors({"status": "error", "message": "send {\"engine\": \"...\", \"message\": \"...\"}"}, 400)
    facts = ""
    if _diag is not None:
        for name in (d["engine"], d["engine"].rstrip("-"), d["engine"].rstrip("-").replace("_", "-")):
            try:
                detail = _diag.engine_detail(name)
            except Exception:
                detail = None
            if detail:
                detail.pop("history", None)
                facts = json.dumps(detail, default=str)[:2500]
                break
    try:
        res = _desk.link_chat(d["engine"], d["message"], facts)
    except _desk.DeskError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    return _json_cors(dict(res, status="busy" if res.get("kind") == "busy" else "success"), 429 if res.get("kind") == "busy" else 200)


@app.route("/api/desk/reset", methods=["POST", "OPTIONS"], strict_slashes=False)
def desk_reset():
    return _desk_call("reset", ["engine"])


@app.route("/api/portals/run", methods=["POST", "OPTIONS"], strict_slashes=False)
def portals_run():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    denied = _portals_or_503()
    if denied:
        return denied
    d = request.get_json(silent=True)
    if not isinstance(d, dict) or not isinstance(d.get("op"), str):
        return _json_cors({"status": "error", "message": "send {\"op\": \"portal.operation\", \"args\": {...}}"}, 400)
    try:
        return _json_cors(_portals.run(d["op"], d.get("args") or {}))
    except _portals.PortalBusy as e:
        return _json_cors({"status": "busy", "message": str(e)}, 429)
    except _portals.PortalError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)


@app.route("/api/engine/config", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def engine_config():
    if request.method == "OPTIONS":
        return _cors_options("GET, POST")
    if request.method == "POST":
        d = request.get_json(silent=True) or {}
        if not isinstance(d.get("standalone"), bool):
            return _json_cors({"status": "error", "message": "standalone must be true or false"}, 400)
        _engine_cfg["standalone"] = d["standalone"]
    return _json_cors({"status": "success", **_engine_cfg, "available": _eb is not None, "mode": _mode_state.mode if _mode_state else None})


@app.route("/api/engine/builds", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def engine_builds():
    if request.method == "OPTIONS":
        return _cors_options("GET, POST")
    denied = _eb_or_503()
    if denied:
        return denied
    if request.method == "POST":
        if _mode_state is None or _mode_state.mode != "engine_build":
            return _json_cors({"status": "halted", "reason": "engine_builds_need_engine_build_mode", "message": "Switch the mode selector to Engine Build first."}, 409)
        d = request.get_json(silent=True) or {}
        res, err = _engine_start(str(d.get("request") or ""), (str(d["name"]) if d.get("name") else None))
        if err:
            return _json_cors({"status": "error", "message": err}, 400)
        return _json_cors({"status": "success", **res}, 202)
    return _json_cors({"status": "success", "builds": _eb.list_builds(int(request.args.get("limit", 30) or 30)), **_engine_cfg})


def _eb_call(fn):
    try:
        return _json_cors({"status": "success", **fn()})
    except _eb.EngineBuildError as e:
        return _json_cors({"status": "error", "message": str(e)}, 404)


@app.route("/api/engine/builds/<bid>", methods=["GET", "OPTIONS"], strict_slashes=False)
def engine_build_get(bid):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    return _eb_or_503() or _eb_call(lambda: {"build": _eb.get(bid), "tree": _eb.tree(bid)})


@app.route("/api/engine/builds/<bid>/events", methods=["GET", "OPTIONS"], strict_slashes=False)
def engine_build_events(bid):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    return _eb_or_503() or _eb_call(lambda: {"events": _eb.events(bid, int(request.args.get("since", 0) or 0)), "tree": _eb.tree(bid), "build": _eb.get(bid)})


@app.route("/api/engine/builds/<bid>/file", methods=["GET", "OPTIONS"], strict_slashes=False)
def engine_build_file(bid):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    return _eb_or_503() or _eb_call(lambda: _eb.read_file(bid, request.args.get("path", "")))


@app.route("/api/engine/builds/<bid>/briefing", methods=["GET", "OPTIONS"], strict_slashes=False)
def engine_build_briefing(bid):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    return _eb_or_503() or _eb_call(lambda: {"briefing": _eb.briefing(bid)})


@app.route("/api/engine/builds/<bid>/approve", methods=["POST", "OPTIONS"], strict_slashes=False)
def engine_build_approve(bid):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _eb_or_503()
    if denied:
        return denied
    d = request.get_json(silent=True) or {}
    if d.get("confirm") != bid:
        return _json_cors({"status": "error", "message": "Approving needs {\"confirm\": \"%s\"}." % bid}, 400)
    try:
        res = _eb.approve(bid, str(d.get("briefing_sha256") or ""), approver="owner")
    except _eb.EngineBuildError as e:
        return _json_cors({"status": "error", "message": str(e)}, 409)
    if _telemetry is not None:
        _telemetry.record(res["name"], "deployed", "approved by the owner")
    if _notes is not None:
        _notes.add("engine", "Engine deployed: " + res["name"], res["note"], "ok", [], {"engine_build": bid}, dedupe_key="engine-deployed:" + bid)
    return _json_cors({"status": "success", **res})


@app.route("/api/engine/builds/<bid>/reject", methods=["POST", "OPTIONS"], strict_slashes=False)
def engine_build_reject(bid):
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin() or _eb_or_503()
    if denied:
        return denied
    if (request.get_json(silent=True) or {}).get("confirm") != bid:
        return _json_cors({"status": "error", "message": "Rejecting needs {\"confirm\": \"%s\"}." % bid}, 400)
    try:
        _eb.reject(bid)
        return _json_cors({"status": "success", "rejected": bid})
    except _eb.EngineBuildError as e:
        return _json_cors({"status": "error", "message": str(e)}, 409)


@app.route("/api/engine/map", methods=["GET", "OPTIONS"], strict_slashes=False)
def engine_workspace_map():
    """The local workspace map NEXXUS reads when it builds: counts, the modules that exist, and the largest folders. Names and signatures only."""
    if request.method == "OPTIONS":
        return _cors_options("GET")
    denied = _eb_or_503()
    if denied:
        return denied
    m = _eb.get_map(refresh=request.args.get("refresh") == "1")
    by_dir = {}
    for f in m["files"]:
        k = os.path.dirname(f["path"]).replace("\\", "/").split("/")[-1] or "."
        by_dir[k] = by_dir.get(k, 0) + 1
    return _json_cors({"status": "success", "generated_at": m["generated_at"], "counts": m["counts"], "truncated": m["truncated"],
                       "modules": [{k: x[k] for k in ("name", "type", "port", "hostnames", "linked_to_nexxus")} for x in m["modules"]],
                       "top_folders": sorted(by_dir.items(), key=lambda kv: -kv[1])[:12]})


@app.route("/api/telemetry", methods=["GET", "OPTIONS"], strict_slashes=False)
def telemetry_snapshot():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if _telemetry is None:
        return _json_cors({"status": "error", "message": "engine telemetry is not installed"}, 503)
    return _json_cors({"status": "success", **_telemetry.snapshot(int(request.args.get("since", 0) or 0))})


_last_manual_ping = [0.0]


@app.route("/api/telemetry/ping", methods=["POST", "OPTIONS"], strict_slashes=False)
def telemetry_ping():
    if request.method == "OPTIONS":
        return _cors_options("POST")
    if _telemetry is None:
        return _json_cors({"status": "error", "message": "engine telemetry is not installed"}, 503)
    if time.time() - _last_manual_ping[0] < 2:
        return _json_cors({"status": "success", **_telemetry.snapshot(0), "note": "pinged a moment ago"})
    _last_manual_ping[0] = time.time()
    return _json_cors({"status": "success", **_telemetry.ping_all()})


@app.route("/api/prompts", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def prompt_recipes():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    if _pvault is None:
        return _json_cors({"status": "error", "message": "prompt_vault.py is not installed"}, 503)
    if request.method == "POST":
        denied = _require_vault_admin()
        if denied:
            return denied
        d = request.get_json(silent=True) or {}
        try:
            rec = _pvault.add(d.get("title"), d.get("prompt"), d.get("category") or "Custom", d.get("mode") or "sandbox", d.get("summary") or "", d.get("tags") or "")
        except ValueError as e:
            return _json_cors({"status": "error", "message": str(e)}, 400)
        return _json_cors({"status": "success", "recipe": rec}, 201)
    return _json_cors({"status": "success", "recipes": _pvault.list_recipes(), "categories": _pvault.categories()})


@app.route("/api/prompts/<rid>", methods=["DELETE", "OPTIONS"], strict_slashes=False)
def prompt_recipe_delete(rid):
    if request.method == "OPTIONS":
        return _admin_cors_options("DELETE")
    if _pvault is None:
        return _json_cors({"status": "error", "message": "prompt_vault.py is not installed"}, 503)
    denied = _require_vault_admin()
    if denied:
        return denied
    try:
        _pvault.delete(rid)
    except ValueError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)
    except KeyError:
        return _json_cors({"status": "error", "message": "no such recipe"}, 404)
    return _json_cors({"status": "success", "deleted": rid})


# ═══════════════════════════════════════════════════════
# DIAGNOSTIC MODE ("Boiler Room"): live overview + drill-down for the left panel, and the system-locked conversation.
# Everything is read from the live system (diagnostics_hub.py); nothing is invented. In Diagnostic mode the mode gate turns away anything that is not about the system.
# ═══════════════════════════════════════════════════════
try:
    import diagnostics_hub as _dhub
except Exception as _e_dh:
    _dhub = None
    print("[DIAGNOSTICS] unavailable: %s: %s" % (type(_e_dh).__name__, _e_dh))

_ollama_cache = {"t": 0.0, "v": None, "busy": False}


def _ollama_refresh():
    base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if not base.startswith("http"):
        base = "http://" + base
    out = {"up": False, "models": [], "loaded": []}
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=2) as r:
            out["models"] = [m.get("name") for m in json.loads(r.read()).get("models", [])]
            out["up"] = True
        with urllib.request.urlopen(base + "/api/ps", timeout=2) as r:
            out["loaded"] = [m.get("name") for m in json.loads(r.read()).get("models", [])]
    except Exception:
        pass
    _ollama_cache.update(t=time.time(), v=out, busy=False)


def _ollama_status():
    """The local model server: reachable? which models are installed and which are loaded in memory. Read in the background (a busy model server can take seconds to
    answer) and cached for 5 s, so the live panel never waits on it. The very first call says up=None ("still reading")."""
    if time.time() - _ollama_cache["t"] > 5 and not _ollama_cache["busy"]:
        _ollama_cache["busy"] = True
        threading.Thread(target=_ollama_refresh, daemon=True, name="ollama-status").start()
    return _ollama_cache["v"] or {"up": None, "models": [], "loaded": []}


def _diag_ledgers():
    out = {}
    if _eb is not None:
        ok, why = _eb.verify_ledger()
        out["engine_builds"] = "chain intact" if ok else "BROKEN: " + str(why)
    return out


def _diag_jobs():
    import job_manager
    return job_manager.get_default_manager().list(50)


_diag = None
if _dhub is not None and _telemetry is not None:
    try:
        _diag = _dhub.DiagnosticsHub(
            _telemetry, mesh=_axis_bridge.telemetry, mesh_utils=_axis_bridge.list_utilities, mesh_messages=lambda since: _axis_bridge.messages(since, None),
            gate=(lambda: {"gate": _gate.summary()}) if _gate is not None else None, jobs=_diag_jobs, ollama=_ollama_status, ledgers=_diag_ledgers,
            ports=[(BRIDGE_PORT, "NEXXUS server"), (8080, "gateway"), (11434, "Ollama")], gateway=("127.0.0.1", 8080))
    except Exception as _e_diag:
        _diag = None
        print("[DIAGNOSTICS] could not start: %s: %s" % (type(_e_diag).__name__, _e_diag))


def _diag_names():
    names = list(_axis_bridge.ENGINES) + [e["name"] for e in (_telemetry.snapshot(0)["engines"] if _telemetry else [])]
    _dhub.set_names(names)                      # so "why is picthis slow" counts as a system question


@app.route("/api/diagnostics/overview", methods=["GET", "OPTIONS"], strict_slashes=False)
def diagnostics_overview():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if _diag is None:
        return _json_cors({"status": "error", "message": "diagnostics are not available (diagnostics_hub.py or engine telemetry is missing)"}, 503)
    _diag_names()
    return _json_cors({"status": "success", **_diag.overview(), "mode": _mode_state.mode if _mode_state else None})


@app.route("/api/diagnostics/engine/<name>", methods=["GET", "OPTIONS"], strict_slashes=False)
def diagnostics_engine(name):
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if _diag is None:
        return _json_cors({"status": "error", "message": "diagnostics are not available"}, 503)
    if not re.match(r"^[A-Za-z0-9_.-]{1,60}$", name):
        return _json_cors({"status": "error", "message": "that is not an engine name"}, 400)
    d = _diag.engine_detail(name)
    if d is None:
        return _json_cors({"status": "error", "message": "no engine called %r is known" % name}, 404)
    body = dict(d, engine_status=d["status"])       # the engine's own state must not overwrite the response's status
    body["status"] = "success"
    return _json_cors(body)


def _diagnostic_chat_reply(text):
    """In Diagnostic mode a system question is answered from the live data; if that cannot answer it exactly, the model answers with those facts in front of it and a
    rule to stay on the machinery. (Off-topic messages never get here: the mode gate turned them away.) -> (reply, extras) or None."""
    if _diag is None or _mode_state is None or _mode_state.mode != "diagnostic":
        return None
    _diag_names()
    grounded = _diag.answer(text)
    if grounded:
        return grounded, {"diagnostic": {"source": "live data"}}
    prompt = ("[DIAGNOSTIC MODE. You are NEXXUS auditing its own machinery. Answer ONLY about the system, the engines, the bridge and the infrastructure, using the live facts below. "
              "No small talk, no unrelated topics, no filler. If the facts do not cover the question, say exactly what is unknown and how to find out.]\n\n"
              + _diag.facts_for_model() + "\n\nQUESTION: " + str(text))
    reply, extras = _invoke_nexxus_pipeline(prompt)
    return reply, dict(extras or {}, diagnostic={"source": "model, with live facts"})


# ═══════════════════════════════════════════════════════
# AXIS LINK  (Link mode: the backend settings space, the transaction ledger, the two-slot input queue, the analyst and the hypothesis desk)
# Everything that crosses the machine is written to an in-memory ledger (link_hub.TransactionLog, 600 newest, cleared on restart): the signed calls to modules (timed hop by hop
# from nexxus_external), the mesh and bus routes, and every chat. The routes that show the CONTENTS are admin-token gated (payloads are redacted, but they are still the owner's
# traffic); the queue lights are open. The input queue (input_queue.TwoSlotQueue) sits in front of /bridge and /command-dispatch: two slots, first in first out, a third is refused.
# Read-only: nothing here changes an engine. See AXIS_LINK.md.
# ═══════════════════════════════════════════════════════
try:
    import link_hub as _lhub
    import link_translate as _ltr
    import link_analyst as _lan
    import input_queue as _iq
except Exception as _e_link:
    _lhub = _ltr = _lan = _iq = None
    print("[AXIS LINK] unavailable: %s: %s" % (type(_e_link).__name__, _e_link))

_link = _lhub.TransactionLog() if _lhub is not None else None
_input_queue = _iq.TwoSlotQueue(slots=2) if _iq is not None else None
_QUEUE_PATHS = ("/bridge", "/command-dispatch")
_QUEUE_WAIT_S = 180.0

# route -> (kind, how to name source / destination from the request body, what is verified)
_LINK_ROUTES = {
    "/api/mesh/message": ("mesh_message", lambda d: (d.get("engine"), d.get("to") or "nexxus"), "signature", False),
    "/api/mesh/status": ("mesh_heartbeat", lambda d: (d.get("engine"), "nexxus"), "signature", True),
    "/api/mesh/peers": ("mesh_message", lambda d: (d.get("engine"), "nexxus"), "signature", True),
    "/api/mesh/instruct": ("mesh_instruct", lambda d: ("owner", d.get("engine")), "token", False),
    "/api/mesh/call": ("mesh_call", lambda d: ("owner", d.get("engine")), "token", False),
    "/api/mesh/job": ("mesh_job", lambda d: ("owner", d.get("engine")), "token", False),
}


def _module_txn(info):
    """nexxus_external reports each signed call: record it hop by hop with the real times it measured. Health pings are recorded as quiet (hidden unless asked for)."""
    if _link is None:
        return
    pk = info["packet"] or {}
    op = pk.get("op", "call")
    t = _link.start("module_rpc", "nexxus", info["name"], "signed '%s' request" % op, payload=pk, meta={"op": op, "module": info["name"]}, quiet=(op == "health"))
    t.started = info["t_start"]
    t.hop("nexxus", "signed_request", "ok", "op=%s" % op, at=info["t_start"])
    sent = info.get("t_sent")
    if sent:
        t.hop("gateway", "sent_to_gateway", "ok", "", at=sent)
    http = info.get("http")
    t.hop(info["name"], "gateway_module", "ok" if info["ok"] else "failed", ("HTTP %s" % http) if http else (info.get("error") or ""),
          check="signature" if info["ok"] else None, at=info["t_end"])
    t.finish("ok" if info["ok"] else "failed", "" if info["ok"] else (info.get("error") or "no answer"), at=info["t_end"])
    if not info["ok"] and op != "health" and info.get("http") in (401, 403) and globals().get("_perim") is not None:
        _perim.breach("module-refused-packet", info["name"], "The %s module refused a signed request (HTTP %s)." % (info["name"], info["http"]), severity="alert", packet={"module": info["name"], "packet": pk}, txn_id=t.id)


if _link is not None and _ext is not None:
    _ext.TXN_HOOK = _module_txn


@app.before_request
def _link_before():
    from flask import g
    g.link_t0 = time.time()
    g.link_ticket = None
    if request.method != "POST" or request.path not in _QUEUE_PATHS or _input_queue is None:
        return None
    g.link_ticket = _input_queue.enter()
    if g.link_ticket is None:                                            # both slots are taken: turned away at once, nothing queued
        snap = _input_queue.snapshot()
        if _link is not None:
            body = request.get_json(silent=True) or {}
            tx = _link.start("chat", "owner", "nexxus", "input turned away (both slots busy)", payload=body, meta={"preview": str(body.get("message") or body.get("command") or "")[:80]})
            tx.hop("input queue", "refused", "blocked", "both slots in use", check=None)
            tx.finish("blocked", "queue full: two inputs already in line")
        return _json_cors({"status": "busy", "busy": True, "error": "maxed out", "message": "Both input slots are in use. Wait for the light to clear, then send it again. Nothing was queued.",
                           "queue": snap}, 429)
    q0 = time.time()
    if not _input_queue.wait(g.link_ticket, timeout=_QUEUE_WAIT_S):    # waited too long for the one ahead: the slot is released
        g.link_ticket = None
        return _json_cors({"status": "busy", "busy": True, "error": "timed out waiting for its turn", "message": "The earlier request took too long. Send it again.",
                           "queue": _input_queue.snapshot()}, 429)
    g.link_wait = time.time() - q0
    if _link is not None:                                                # the flight takes off now: it is in the ledger as "in flight" until the reply is sent
        body = request.get_json(silent=True) or {}
        body = body if isinstance(body, dict) else {"body": body}
        text = str(body.get("message") or body.get("command") or body.get("text") or "")
        tx = _link.start("chat", "owner", "nexxus", "chat: " + text[:80], payload=body, meta={"preview": text[:80], "mode": _mode_state.mode if _mode_state else None, "route": request.path})
        tx.started = g.link_t0
        tx.hop("dashboard", "received", "ok", "via %s" % request.path, at=g.link_t0)
        tx.hop("input queue", "queue_wait", "ok", "waited %.0f ms for its turn" % (g.link_wait * 1000.0), at=g.link_t0 + g.link_wait)
        g.link_txn = tx
    return None


@app.after_request
def _link_after(resp):
    from flask import g
    try:
        t0 = getattr(g, "link_t0", None)
        if _link is not None and t0 is not None and request.method == "POST" and resp.status_code != 429:
            _link_record(resp, t0)
    except Exception:
        pass                                                             # the ledger never changes what the caller gets
    return resp


@app.teardown_request
def _link_teardown(exc):
    from flask import g
    tk = getattr(g, "link_ticket", None)
    if tk is not None and _input_queue is not None:
        _input_queue.leave(tk)
        g.link_ticket = None


def _link_record(resp, t0):
    from flask import g
    p, end = request.path, time.time()
    body = request.get_json(silent=True) or {}
    body = body if isinstance(body, dict) else {"body": body}
    out = resp.get_json(silent=True) if resp.is_json else None
    out = out if isinstance(out, dict) else {}
    ok = resp.status_code < 400
    if p in _QUEUE_PATHS:
        text = str(body.get("message") or body.get("command") or body.get("text") or "")
        halted = bool(out.get("halted"))
        tx = getattr(g, "link_txn", None)                                   # opened when the input was taken in, so a stalled chat is visible while it is still stuck
        wait = getattr(g, "link_wait", 0.0) or 0.0
        if tx is None:
            tx = _link.start("chat", "owner", "nexxus", "chat: " + text[:80], payload=body, meta={"preview": text[:80], "mode": _mode_state.mode if _mode_state else None, "route": p})
            tx.started = t0
            tx.hop("dashboard", "received", "ok", "via %s" % p, at=t0)
            tx.hop("input queue", "queue_wait", "ok", "waited %.0f ms for its turn" % (wait * 1000.0), at=t0 + wait)
        tx.hop("mode gate", "mode_gate", "blocked" if halted else "ok", ("held by mode %s" % out.get("mode")) if halted else "allowed", check="mode", at=t0 + wait)
        if not halted:
            tx.hop("nexxus", "model" if not out.get("diagnostic") else "handled", "ok" if ok else "failed", "", at=end)
        tx.hop("dashboard", "replied", "ok" if ok else "failed", "HTTP %s" % resp.status_code, at=end)
        tx.finish("blocked" if halted else ("ok" if ok else "failed"), "held by the mode gate" if halted else ("" if ok else "HTTP %s" % resp.status_code), at=end)
        return
    spec = _LINK_ROUTES.get(p)
    if spec is None and not p.startswith("/api/bus/"):
        return
    if spec is None:
        kind, quiet, verify = "bus_order", False, "token"
        src, dst = "owner", "orchestrator bus"
        meta = {"op": p.rsplit("/", 1)[-1]}
    else:
        kind, namer, verify, quiet = spec
        src, dst = namer(body)
        meta = {"msg_kind": body.get("kind"), "state": body.get("state"), "instruction": str(body.get("instruction") or "")[:80], "utility": body.get("utility")}
    tx = _link.start(kind, src or "unknown", dst or "unknown", p, payload=body, meta={k: v for k, v in meta.items() if v}, quiet=quiet)
    tx.started = t0
    tx.hop(src or "unknown", "received", "ok", p, at=t0)
    locked = resp.status_code == 423
    refused = resp.status_code in (401, 403, 423)
    if locked:
        tx.hop("perimeter", "lock_check", "blocked", "Hard Locked: " + str(out.get("message", "")), check="lock", at=t0)
    else:
        tx.hop("nexxus", "signature_check" if verify == "signature" else "token_check", "failed" if refused else "ok",
               "bad or missing %s" % ("signature" if verify == "signature" else "admin token") if refused else "", check=verify, at=t0)
    if not refused:
        tx.hop("nexxus", "handled", "ok" if ok else "failed", "HTTP %s" % resp.status_code, at=end)
    tx.finish("blocked" if refused else ("ok" if ok else "failed"), "HTTP %s" % resp.status_code, at=end)


# --- read routes (admin-gated) ---------------------------------------------------------------
def _intake_flight(report, meta):
    """Every run of the intake pipeline is a Flight Record: one checkpoint per stage, with the stage's real time."""
    if _link is None:
        return
    st = report["stages"]
    t = _link.start("intake", "github:%s/%s" % (meta.get("owner"), meta.get("repo")), "tool vault", "intake: " + report["asset"],
                    payload={"asset": report["asset"], "commit": report.get("commit"), "files": report["plan_before"]["files"], "fixes": len(report["fixes"]), "gate": report["gate"]["verdict"]},
                    meta={"asset": report["asset"], "fixes": len(report["fixes"]), "gate": report["gate"]["verdict"]})
    t.started = st[0]["at"] - st[0]["ms"] / 1000.0
    for s in st:
        status = "ok" if s["ok"] else ("blocked" if s["name"] == "gate" else "failed")
        t.hop("intake: " + s["name"], "intake_" + s["name"], status, s["detail"], check=s["check"], at=s["at"])
    t.finish("ok" if report["gate"]["verdict"] == "pass" else "blocked", "" if report["gate"]["verdict"] == "pass" else "; ".join(report["gate"]["blockers"])[:180], at=st[-1]["at"])


try:
    import intake_pipeline as _ipl
    _ipl.FLIGHT_HOOK = _intake_flight
except Exception as _e_ipl:
    print("[INTAKE] flight hook not installed: %s" % _e_ipl)


def _link_or_503():
    if _link is None:
        return _json_cors({"status": "error", "message": "AXIS LINK is not available (link_hub.py is missing)"}, 503)
    return None


@app.route("/api/input/queue", methods=["GET", "OPTIONS"], strict_slashes=False)
def input_queue_state():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if _input_queue is None:
        return _json_cors({"status": "error", "message": "input queue not installed"}, 503)
    return _json_cors({"status": "success", **_input_queue.snapshot()})


@app.route("/api/link/log", methods=["GET", "OPTIONS"], strict_slashes=False)
def link_log():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _link_or_503() or _require_vault_admin()
    if denied:
        return denied
    kinds = [k for k in (request.args.get("kinds") or "").split(",") if k] or None
    rows = _link.list(since=int(request.args.get("since", 0) or 0), kinds=kinds, include_quiet=request.args.get("quiet") == "1", limit=min(300, int(request.args.get("limit", 200) or 200)))
    for r in rows:
        r["plain"] = _ltr.summary_plain(_link.get(r["id"]))
    return _json_cors({"status": "success", "rows": rows, "latest": _link.latest_seq(), "queue": _input_queue.snapshot() if _input_queue else None,
                       "stats": _link.stats(), "mode": _mode_state.mode if _mode_state else None})


@app.route("/api/link/txn/<txn_id>", methods=["GET", "OPTIONS"], strict_slashes=False)
def link_txn(txn_id):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _link_or_503() or _require_vault_admin()
    if denied:
        return denied
    t = _link.get(txn_id) if re.match(r"^(t\d{1,9}|FL-[0-9A-Z]{1,8}-\d{4})$", txn_id) else None
    if t is None:
        return _json_cors({"status": "error", "message": "no such transaction (the ledger keeps the newest 600 and is cleared on restart)"}, 404)
    stats = _link.stats()
    return _json_cors({"status": "success", "txn": t, "terminal": _ltr.terminal_view(t), "layman": _ltr.layman_view(t, stats), "plain": _ltr.summary_plain(t),
                       "touchpoints": _ltr.touchpoints(t, stats), "unusual": _ltr.unusual(t, stats), "diagnosis": _ltr.diagnose(t, stats)})


# --- the analyst + the hypothesis desk: the exact part answers at once, the model's own words arrive in the background --------------
_link_jobs, _link_jobs_lock = {}, threading.Lock()


def _link_job(prompt):
    jid = uuid.uuid4().hex[:12]
    with _link_jobs_lock:
        for k in list(_link_jobs)[:-40]:
            _link_jobs.pop(k, None)
        _link_jobs[jid] = {"state": "running", "text": "", "started": time.time()}

    def run():
        try:
            reply, _x = _invoke_nexxus_pipeline(prompt)
            res = {"state": "done", "text": str(reply)}
        except Exception as e:
            res = {"state": "failed", "text": "the model could not answer: %s" % e}
        with _link_jobs_lock:
            _link_jobs[jid].update(res)
    threading.Thread(target=run, daemon=True, name="link-analyst").start()
    return jid


@app.route("/api/link/analyze", methods=["POST", "OPTIONS"], strict_slashes=False)
def link_analyze():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _link_or_503() or _require_vault_admin()
    if denied:
        return denied
    d = request.get_json(silent=True) or {}
    t = _link.get(str(d.get("txn", "")))
    if t is None:
        return _json_cors({"status": "error", "message": "no such transaction"}, 404)
    stats = _link.stats()
    try:
        rules = _ltr.rules_breakdown(t, str(d.get("element", "")), stats)
    except KeyError:
        return _json_cors({"status": "error", "message": "that element does not exist on this transaction"}, 400)
    jid = _link_job(_ltr.analyst_prompt(t, str(d.get("element")), stats)) if d.get("model", True) else None
    return _json_cors({"status": "success", "rules": rules, "job": jid})


@app.route("/api/link/hypothesis", methods=["POST", "OPTIONS"], strict_slashes=False)
def link_hypothesis():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _link_or_503() or _require_vault_admin()
    if denied:
        return denied
    d = request.get_json(silent=True) or {}
    text = str(d.get("text", "")).strip()
    if not text:
        return _json_cors({"status": "error", "message": "write the hypothesis first"}, 400)
    names = list(_axis_bridge.ENGINES) + ([e["name"] for e in _telemetry.snapshot(0)["engines"]] if _telemetry else [])
    ev = _lan.evidence(_link, text, names)
    hist = [(str(h.get("who", "owner")), str(h.get("text", ""))) for h in (d.get("history") or []) if isinstance(h, dict)]
    jid = _link_job(_lan.copilot_prompt(text, ev, hist)) if d.get("model", True) else None
    return _json_cors({"status": "success", "evidence": ev, "job": jid})


@app.route("/api/link/job/<jid>", methods=["GET", "OPTIONS"], strict_slashes=False)
def link_job_state(jid):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _link_or_503() or _require_vault_admin()
    if denied:
        return denied
    with _link_jobs_lock:
        j = dict(_link_jobs.get(jid) or {})
    if not j:
        return _json_cors({"status": "error", "message": "no such analysis"}, 404)
    return _json_cors({"status": "success", **j})


def _link_chat_reply(text):
    """Link mode: questions about the traffic are answered by the model with the ledger's numbers in front of it. -> (reply, extras) or None."""
    if _link is None or _mode_state is None or _mode_state.mode != "link":
        return None
    s = _link.stats()
    facts = "LEDGER: %d finished transaction(s). Fleet median %s ms, 95th %s ms, %s not completed.\n" % (s["sample"], s["fleet"]["p50"], s["fleet"]["p95"], s["fleet"]["failed"])
    facts += "\n".join("- %s: %d, %d failed, median %s ms, 95th %s ms" % (k, v["count"], v["failed"], v["p50"], v["p95"]) for k, v in list(s["routes"].items())[:12]) or "- nothing recorded yet"
    prompt = ("[AXIS LINK MODE. You are NEXXUS helping the owner understand the traffic through the machine. Answer from the recorded numbers below; never invent numbers; if the "
              "ledger does not cover the question, say what is unknown. Offer to open the Transaction Log or the hypothesis desk when that would help.]\n\n" + facts + "\n\nQUESTION: " + str(text))
    reply, extras = _invoke_nexxus_pipeline(prompt)
    return reply, dict(extras or {}, link={"source": "model, with ledger numbers"})


# ═══════════════════════════════════════════════════════
# CORE DRIVE, SKETCH MODE, DAEMON ENGINE
# core_drive.py is the dashboard's own core memory (NEXXUS_HOME, D:\NEXXUS; a local folder when that drive is not on this machine): its layout is created when this server starts and everything
# built through the dashboard is filed into it. Sketch Mode (sketch_mode.py) is the ideation workshop: its chat turns come through _sketch_chat_reply, Build packages the thesis into the core
# drive and returns the order for the build room (which still stages and asks for approval). daemon_engine.py supervises the services; the routes here only READ its health, and its commands need the
# admin token and a running daemon. See FACTORY.md.
# ═══════════════════════════════════════════════════════
try:
    import core_drive as _core
    _core_layout = _core.ensure_layout()
except Exception as _e_core:
    _core = None
    _core_layout = {}
    print("[CORE DRIVE] unavailable: %s: %s" % (type(_e_core).__name__, _e_core))
try:
    import sketch_mode as _sk
except Exception as _e_sk:
    _sk = None
    print("[SKETCH] unavailable: %s: %s" % (type(_e_sk).__name__, _e_sk))
try:
    import daemon_engine as _daemon
except Exception as _e_dm:
    _daemon = None
    print("[DAEMON] unavailable: %s: %s" % (type(_e_dm).__name__, _e_dm))


def _sketch_llm(prompt):
    reply, _extras = _invoke_nexxus_pipeline(prompt)
    return reply


_sketch = None
if _sk is not None and _core is not None:
    try:
        _sketch = _sk.SketchEngine(os.environ.get("NEXXUS_SKETCH_DIR") or _core.kind_dir("sketches"), llm=_sketch_llm)
    except Exception as _e_ske:
        print("[SKETCH] engine unavailable: %s: %s" % (type(_e_ske).__name__, _e_ske))


def _sketch_chat_reply(text):
    """Sketch mode: every message is a turn in the workshop (board, stage, pills); nothing is built. -> (reply, extras) or None."""
    if _sketch is None or _mode_state is None or _mode_state.mode != "sketch":
        return None
    res = _sketch.handle(text)
    extras = {"sketch": res["view"]}
    if res.get("question"):
        extras["question"] = res["question"]
    return res["reply"], extras


def _sketch_do(fn, ok=200):
    if _sketch is None:
        return _json_cors({"status": "error", "error": "Sketch Mode is not installed"}, 503)
    try:
        return _json_cors(dict(fn(), status="success"), ok)
    except (ValueError, KeyError) as e:
        return _json_cors({"status": "error", "error": str(e.args[0] if e.args else e)}, 400)


@app.route("/api/sketch", methods=["GET", "OPTIONS"], strict_slashes=False)
def sketch_state():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    return _sketch_do(lambda: {"view": _sketch.view(_sketch.current()), "sketches": _sketch.list()})


@app.route("/api/sketch/<action>", methods=["POST", "OPTIONS"], strict_slashes=False)
def sketch_action(action):
    if request.method == "OPTIONS":
        return _cors_options("POST")
    d = request.get_json(silent=True) or {}

    def run():
        if action == "new":
            s = _sketch.new()
            return {"view": _sketch.view(s), "reply": _sketch.handle("")["reply"]}
        if action == "resume":
            return {"view": _sketch.view(_sketch.resume(str(d.get("id"))))}
        if action == "thesis":
            return _sketch.draft_thesis(d.get("id"))
        if action == "build":
            s = _sketch.current()
            if not s:
                raise ValueError("there is no sketch to build")
            r = _sketch.package(s["id"], str(d.get("room") or "engine_build"))
            return {"build": r, "view": _sketch.view(_sketch.load(s["id"]))}
        raise KeyError("no such sketch action")
    return _sketch_do(run)


@app.route("/api/core/drive", methods=["GET", "OPTIONS"], strict_slashes=False)
def core_drive_status():
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if _core is None:
        return _json_cors({"status": "error", "error": "core_drive.py is not installed"}, 503)
    return _json_cors(dict(_core.status(), status="success", recent=_core.index(limit=12)))


@app.route("/api/slae/stats", methods=["GET", "OPTIONS"], strict_slashes=False)
def slae_stats():
    """Immunity telemetry for the dashboard: total resolved, active rules (and which are enforceable), recurrences after a rule existed, vault location."""
    if request.method == "OPTIONS":
        return _cors_options("GET")
    try:
        import sl_adaptive_core as _slae_mod
        eng = _slae_mod.get_engine()
    except Exception as e:
        return _json_cors({"status": "error", "error": "adaptation engine unavailable: %s" % e}, 503)
    if eng is None:
        return _json_cors({"status": "error", "error": "the adaptation engine is switched off in SLAE_CONFIG"}, 503)
    return _json_cors(dict(eng.get_system_immunity_stats(), status="success", engine=eng.status()))


@app.route("/api/daemon/health", methods=["GET", "OPTIONS"], strict_slashes=False)
def daemon_health():
    """The green / yellow / red picture. The running daemon's system_health.json when there is one; otherwise a one-off read-only look (nothing is started)."""
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if _daemon is None:
        return _json_cors({"status": "error", "error": "daemon_engine.py is not installed"}, 503)
    cfg = _daemon.load_config()
    try:
        if _daemon.daemon_running(cfg):
            return _json_cors({"status": "success", "source": "daemon", "health": json.loads((cfg["state_dir"] / "system_health.json").read_text(encoding="utf-8"))})
    except (OSError, ValueError):
        pass
    return _json_cors({"status": "success", "source": "one-off look (the daemon is not running)", "health": _daemon.DaemonEngine(cfg).telemetry.snapshot()})


@app.route("/api/daemon/command", methods=["POST", "OPTIONS"], strict_slashes=False)
def daemon_command():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    if _daemon is None:
        return _json_cors({"status": "error", "error": "daemon_engine.py is not installed"}, 503)
    if not os.environ.get("NEXXUS_ADMIN_TOKEN"):
        return _json_cors({"status": "error", "error": "NEXXUS_ADMIN_TOKEN not configured"}, 503)
    if not _admin_ok():
        return _json_cors({"status": "error", "error": "unauthorized"}, 401)
    d = request.get_json(silent=True) or {}
    action, service = str(d.get("action") or ""), d.get("service")
    if action not in ("health", "status", "start", "stop", "restart", "reset", "rotate", "boot"):
        return _json_cors({"status": "error", "error": "action must be one of health, status, start, stop, restart, reset, rotate, boot"}, 400)
    cfg = _daemon.load_config()
    if action in ("rotate", "health"):
        out = _daemon.DaemonEngine(cfg).execute(action, dry_run=bool(d.get("dry_run")))
    else:
        out = _daemon.send_command(action, service, cfg=cfg)
    return _json_cors(dict(out, status="success" if out.get("ok", True) else "error"), 200 if out.get("ok", True) else 409)



# ═══════════════════════════════════════════════════════
# PERIMETER  (upper-right dock: Perimeter Gate on top, Triad Protocol node board beneath it, with the operator's Hard Lock and Quarantine overrides)
# The gate half is the existing axis gate (sealed manifests, single-use tickets, owner sign-off); the Triad half is the live node board built from the AXIS LINK ledger and the
# engine telemetry. Hard Lock refuses a node in this server and bridge; Quarantine keeps an inert, redacted copy of a bad packet. Breaches flash the dashboard and raise one
# notification each. Overrides need the admin token. See perimeter.py and PERIMETER.md.
# ═══════════════════════════════════════════════════════
try:
    import perimeter as _perimeter
except Exception as _e_perim:
    _perimeter = None
    print("[PERIMETER] unavailable: %s: %s" % (type(_e_perim).__name__, _e_perim))


def _perim_notify(ev):
    if _notes is None:
        return
    _notes.add("security", "Perimeter: %s (%s)" % (ev["kind"], ev["node"]), ev["detail"], "info" if ev["severity"] == "info" else "fail",
               [{"type": "open_perimeter", "label": "Open command center", "ref": str(ev["seq"])}], {"perimeter": ev["seq"]}, dedupe_key="perimeter:%s" % ev["seq"])


_perim = None
if _perimeter is not None:
    try:
        _perim = _perimeter.Perimeter(os.environ.get("NEXXUS_PERIMETER_DIR") or (Path(__file__).resolve().parent / "perimeter_state"), on_breach=_perim_notify)
        if _ext is not None:
            _ext.BLOCK_CHECK = _perim.blocked_reason
    except Exception as _e_perim2:
        _perim = None
        print("[PERIMETER] could not start: %s: %s" % (type(_e_perim2).__name__, _e_perim2))

_PERIM_MESH_POSTS = ("/api/mesh/message", "/api/mesh/status", "/api/mesh/peers", "/api/mesh/instruct", "/api/mesh/call", "/api/mesh/job")


def _perim_nodes(body):
    """Every node a mesh post names: who it is from and who it is for."""
    body = body if isinstance(body, dict) else {}
    return [str(n) for n in (body.get("engine"), body.get("to")) if n and str(n) != "nexxus"]


@app.before_request
def _perim_before():
    if _perim is None or request.method != "POST" or request.path not in _PERIM_MESH_POSTS:
        return None
    for n in _perim_nodes(request.get_json(silent=True)):
        why = _perim.blocked_reason(n)
        if why:
            _perim.breach("locked-node-contact", n, "%s tried to use %s while %s." % (n, request.path, why), severity="warn")
            return _json_cors({"status": "locked", "error": "node is Hard Locked", "node": n, "message": why}, 423)
    return None


@app.after_request
def _perim_after(resp):
    """Turn a refused signature or admin token on the mesh/bus routes into a breach event (and keep a redacted copy of the packet)."""
    try:
        if _perim is None or request.method != "POST" or resp.status_code not in (401, 403):
            return resp
        p = request.path
        if p not in _PERIM_MESH_POSTS and not p.startswith("/api/bus/"):
            return resp
        body = request.get_json(silent=True)
        node = (_perim_nodes(body) or ["unknown"])[0]
        signed = p in ("/api/mesh/message", "/api/mesh/status", "/api/mesh/peers")
        _perim.breach("bad-signature" if signed else "bad-admin-token", node, "%s was refused (%s)." % (p, "signature did not verify" if signed else "admin token missing or wrong"),
                      severity="alert", packet={"route": p, "body": body})
    except Exception:
        pass
    return resp


def _perim_or_503():
    if _perim is None:
        return _json_cors({"status": "error", "message": "the perimeter overrides are not available (perimeter.py is missing)"}, 503)
    return None


@app.route("/api/auth/check", methods=["GET", "OPTIONS"], strict_slashes=False)
def auth_check():
    """Does this admin token work? The dashboard's unlock dialog asks before it keeps a token."""
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _require_vault_admin()
    return denied or _json_cors({"status": "success", "admin": True})


@app.route("/api/perimeter/status", methods=["GET", "OPTIONS"], strict_slashes=False)
def perimeter_status():
    """Cheap and public like the gate counts: the numbers that make the dashboard flash. No node names, no packets."""
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _perim_or_503()
    if denied:
        return denied
    out = {"status": "success", "perimeter": _perim.summary(), "gate": _gate.summary() if _gate is not None else None}
    if _admin_ok():
        out["events"] = _perim.events(int(request.args.get("since", 0) or 0))[-30:]
    return _json_cors(out)


def _perim_nodes_board():
    names = list(_axis_bridge.ENGINES) if _axis_bridge is not None else []
    health = {}
    if _diag is not None:
        _diag_names()
        for e in _diag.overview().get("engines", []):
            health[e["name"]] = e
            if e["name"] not in names:
                names.append(e["name"])
    traffic = _link.by_node() if _link is not None else {}
    for n in traffic:
        if n not in ("nexxus", "owner", "unknown") and n not in names:           # a node that only shows up in traffic is still on the board
            names.append(n)
    locks = _perim.locks()
    rows = []
    for n in sorted(set(names) | set(locks)):
        h, t = health.get(n, {}), traffic.get(n, {})
        rows.append({"name": n, "group": h.get("group"), "status": h.get("status", "unknown"), "latency_ms": h.get("latency_ms"), "sent": t.get("sent", 0), "received": t.get("received", 0),
                     "failed": t.get("failed", 0), "last": t.get("last"), "locked": locks.get(n)})
    return rows


@app.route("/api/perimeter/triad", methods=["GET", "OPTIONS"], strict_slashes=False)
def perimeter_triad():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _perim_or_503() or _require_vault_admin()
    if denied:
        return denied
    journeys = []
    if _link is not None:
        for r in reversed(_link.list(include_quiet=False, limit=300)):
            if r["source"] in ("nexxus", "owner") and r["dest"] not in ("nexxus",):
                journeys.append({k: r[k] for k in ("id", "kind", "source", "dest", "status", "duration_ms", "hops", "started")})
            if len(journeys) >= 8:
                break
    return _json_cors({"status": "success", "nodes": _perim_nodes_board(), "journeys": journeys, "quarantine": _perim.quarantined()[-20:], "perimeter": _perim.summary()})


def _perim_body(*keys):
    d = request.get_json(silent=True) or {}
    return d, [str(d.get(k, "")).strip() for k in keys]


@app.route("/api/perimeter/lock", methods=["POST", "OPTIONS"], strict_slashes=False)
def perimeter_lock():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _perim_or_503() or _require_vault_admin()
    if denied:
        return denied
    _d, (node, reason) = _perim_body("node", "reason")
    try:
        return _json_cors({"status": "success", "lock": _perim.lock(node, reason or "operator override"), "node": node})
    except _perimeter.PerimeterError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)


@app.route("/api/perimeter/unlock", methods=["POST", "OPTIONS"], strict_slashes=False)
def perimeter_unlock():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _perim_or_503() or _require_vault_admin()
    if denied:
        return denied
    _d, (node,) = _perim_body("node")
    try:
        _perim.unlock(node)
        return _json_cors({"status": "success", "node": node})
    except _perimeter.PerimeterError as e:
        return _json_cors({"status": "error", "message": str(e)}, 400)


@app.route("/api/perimeter/quarantine", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def perimeter_quarantine():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    denied = _perim_or_503() or _require_vault_admin()
    if denied:
        return denied
    if request.method == "GET":
        return _json_cors({"status": "success", "items": _perim.quarantined()})
    d, (txn, reason) = _perim_body("txn", "reason")
    t = _link.get(txn) if (_link is not None and txn) else None
    if t is None:
        return _json_cors({"status": "error", "message": "name a recorded transaction (txn) to quarantine; it must still be in the ledger"}, 404)
    qid = _perim.quarantine(t["source"], reason or "operator quarantine", {"summary": t["summary"], "kind": t["kind"], "status": t["status"], "payload": t["payload"]["text"], "meta": t["meta"]}, txn_id=txn)
    return _json_cors({"status": "success", "id": qid})


@app.route("/api/perimeter/quarantine/release-all", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def perimeter_quarantine_release_all():
    """POST {"confirm": true, "ids": [...optional...], "expected": N optional}: release (delete the inert copy of) everything in quarantine in one action. Admin token required.
    Refused without confirm:true. With `ids` only those still-held items go (items that arrived after the operator's view stay held and are reported as still_held); with `expected`
    a different count of held items answers 409 and nothing is released. The record of what went (metadata only) is kept hash-chained; GET returns that record."""
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, POST")
    denied = _perim_or_503() or _require_vault_admin()
    if denied:
        return denied
    if request.method == "GET":
        return _json_cors({"status": "success", "log": _perim.release_log(int(request.args.get("limit", 50) or 50)), "perimeter": _perim.summary()})
    d = request.get_json(silent=True) or {}
    if d.get("confirm") is not True:
        return _json_cors({"status": "error", "message": "release-all deletes every held copy; send confirm:true to proceed"}, 400)
    ids = d.get("ids")
    if ids is not None and not (isinstance(ids, list) and len(ids) <= 5000):
        return _json_cors({"status": "error", "message": "ids must be a list of quarantine ids"}, 400)
    exp = d.get("expected")
    if exp is not None and (not isinstance(exp, int) or isinstance(exp, bool) or exp < 0):
        return _json_cors({"status": "error", "message": "expected must be a count"}, 400)
    if exp is not None:
        held = len(_perim.quarantined())
        if held != exp and ids is None:
            return _json_cors({"status": "error", "message": "quarantine now holds %d item(s), not the %d you were shown; refresh and review first" % (held, exp), "held": held}, 409)
    try:
        res = _perim.release_all(ids=ids, by="operator")
    except OSError as e:
        return _json_cors({"status": "error", "message": "could not write the release record, nothing was released (%s)" % type(e).__name__}, 500)
    return _json_cors({"status": "success", **res, "perimeter": _perim.summary()})


@app.route("/api/perimeter/quarantine/<qid>", methods=["GET", "DELETE", "OPTIONS"], strict_slashes=False)
def perimeter_quarantine_item(qid):
    if request.method == "OPTIONS":
        return _admin_cors_options("GET, DELETE")
    denied = _perim_or_503() or _require_vault_admin()
    if denied:
        return denied
    if request.method == "DELETE":
        try:
            _perim.release(qid)
            return _json_cors({"status": "success", "released": qid})
        except _perimeter.PerimeterError as e:
            return _json_cors({"status": "error", "message": str(e)}, 404)
    r = _perim.quarantine_get(qid)
    return _json_cors({"status": "success", "item": r}) if r else _json_cors({"status": "error", "message": "nothing quarantined under that id"}, 404)


try:
    import feed_client as _feed
except Exception:                                                            # the feed is optional: a copy without it still runs
    _feed = None


@app.route("/api/feed/latest", methods=["GET", "OPTIONS"], strict_slashes=False)
def feed_latest():
    """The last verified source feed from the original NEXXUS (re-verified from disk on every read). Read-only; nothing is downloaded here."""
    if request.method == "OPTIONS":
        return _cors_options("GET")
    if _feed is None:
        return _json_cors({"status": "error", "message": "the source feed module is not installed"}, 503)
    return _json_cors({"status": "success", **_feed.status()})


@app.route("/api/feed/refresh", methods=["POST", "OPTIONS"], strict_slashes=False)
def feed_refresh():
    """Download and verify the newest feed. One-way: asks the published address for a file and sends nothing about you. Needs the admin token."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _require_vault_admin()
    if denied:
        return denied
    if _feed is None:
        return _json_cors({"status": "error", "message": "the source feed module is not installed"}, 503)
    r = _feed.fetch()
    return _json_cors({"status": "success" if r.get("ok") else "error", **r}, 200 if r.get("ok") else 502)


@app.route("/api/perimeter/ack", methods=["POST", "OPTIONS"], strict_slashes=False)
def perimeter_ack():
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _perim_or_503() or _require_vault_admin()
    if denied:
        return denied
    _perim.ack()
    return _json_cors({"status": "success", "perimeter": _perim.summary()})



# ═══════════════════════════════════════════════════════
# EXPLICIT NAMING + READ-ONLY COMMERCIAL WATCH
# naming.py: everything generated is named for what it is and adopted with a tag (no 'Untitled', no random-token drops). vital_watch.py: NEXXUS may check the pulse of the
# commercial-grade paths the OWNER listed in commercial_watch.json (present, readable, unchanged, optionally answering on loopback) and may never write to, import or run them.
# There is no route that adds or edits a watched path. Reading needs the admin token except the bare counts. See NAMING_AND_WATCH.md.
# ═══════════════════════════════════════════════════════
try:
    import naming as _naming
    import vital_watch as _vital
except Exception as _e_vital:
    _naming = _vital = None
    print("[WATCH] unavailable: %s: %s" % (type(_e_vital).__name__, _e_vital))

_vital_cache = {"at": 0.0, "data": None}
_vital_lock = threading.Lock()


def _vital_transition(name, prev, now, note):
    """A watched path stopped breathing (or changed): a perimeter event that flashes the dashboard. Read-only: nothing is repaired or touched."""
    if _perim is None or prev is None:
        return
    bad = now in ("missing", "unreadable", "not-answering")
    _perim.breach("commercial-" + now, name, "Commercial watch: %s is %s. %s" % (name, now, note or "NEXXUS only observes; nothing was changed."), severity="alert" if bad else "warn")


def _vital_pulse(max_age=15.0):
    with _vital_lock:
        if _vital_cache["data"] is None or time.time() - _vital_cache["at"] > max_age:
            _vital_cache.update(at=time.time(), data=_vital.pulse_all(_vital_transition))
        return _vital_cache["data"]


def _vital_loop():
    while True:
        try:
            _vital_pulse(max_age=0)
        except Exception as e:
            print("[WATCH] pulse failed: %s: %s" % (type(e).__name__, e))
        time.sleep(30)


def _vital_or_503():
    if _vital is None:
        return _json_cors({"status": "error", "message": "the commercial watch is not available (vital_watch.py is missing)"}, 503)
    return None


@app.route("/api/vital/status", methods=["GET", "OPTIONS"], strict_slashes=False)
def vital_status():
    """Bare counts only (no names, no paths): how many watched, how many breathing."""
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _vital_or_503()
    if denied:
        return denied
    d = _vital_pulse()
    return _json_cors({"status": "success", "summary": d["summary"], "read_only": True, "problem": bool(d["problem"])})


@app.route("/api/vital/pulse", methods=["GET", "OPTIONS"], strict_slashes=False)
def vital_pulse_route():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    denied = _vital_or_503() or _require_vault_admin()
    if denied:
        return denied
    return _json_cors({"status": "success", **_vital_pulse(max_age=float(request.args.get("max_age", 15) or 15))})


@app.route("/api/vital/accept", methods=["POST", "OPTIONS"], strict_slashes=False)
def vital_accept_route():
    """The owner accepts a changed commercial path's current contents as the new baseline. Writes NEXXUS's own state file only; the watched path is only read."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    denied = _vital_or_503() or _require_vault_admin()
    if denied:
        return denied
    name = str((request.get_json(silent=True) or {}).get("name", ""))
    try:
        _vital.accept(name)
    except KeyError:
        return _json_cors({"status": "error", "message": "no watched path is called %r (the list is edited by the owner in commercial_watch.json)" % name}, 404)
    except OSError as e:
        return _json_cors({"status": "error", "message": str(e)}, 409)
    with _vital_lock:
        _vital_cache["data"] = None
    return _json_cors({"status": "success", "accepted": name})


def _naming_roots():
    roots = {}
    if _creations is not None:
        roots["creations"] = str(_creations.root)
    if _eb is not None:
        roots["engine builds (staging)"] = str(_eb.STAGING)
    return roots


@app.route("/api/naming/audit", methods=["GET", "OPTIONS"], strict_slashes=False)
def naming_audit():
    if request.method == "OPTIONS":
        return _admin_cors_options("GET")
    if _naming is None:
        return _json_cors({"status": "error", "message": "naming.py is missing"}, 503)
    denied = _require_vault_admin()
    if denied:
        return denied
    out = {k: _naming.audit(v) for k, v in _naming_roots().items()}
    if _eb is not None:                                   # deployed engines live in the UI directory next to many things that are not engines: only the ones a build deployed are checked
        deployed = []
        for b in _eb.list_builds(200):
            if b["status"] == "deployed":
                folder = _eb.UI_ROOT / b["name"]
                deployed.append({"name": b["name"], "tagged": bool(_naming.read_tag(folder)) if folder.is_dir() else None, "present": folder.is_dir()})
        out["deployed engines"] = {"root": str(_eb.UI_ROOT), "items": deployed, "orphans": [d["name"] for d in deployed if d["present"] and not d["tagged"]]}
    return _json_cors({"status": "success", "roots": out})


@app.route("/api/naming/adopt", methods=["POST", "OPTIONS"], strict_slashes=False)
def naming_adopt():
    """Tag the creations and deployed engines that have no tag yet. Non-destructive: nothing is renamed or moved, a tag file is added; anything whose name says nothing is reported, not renamed."""
    if request.method == "OPTIONS":
        return _admin_cors_options("POST")
    if _naming is None:
        return _json_cors({"status": "error", "message": "naming.py is missing"}, 503)
    denied = _require_vault_admin()
    if denied:
        return denied
    done, needs_name = [], []
    if _creations is not None:
        for m in _creations.list():
            folder = _creations.root / m["id"]
            if _naming.read_tag(folder) or not folder.is_dir() or _vital.protected(folder):
                continue
            nm = m.get("title") if _naming.check_name(m.get("title"))[0] else _naming.derive(m.get("prompt"))
            if not nm:
                needs_name.append({"id": m["id"], "why": "its title and request say nothing about what it is"})
                continue
            _naming.adopt(folder, name=nm, kind=m.get("kind", "creation"), owner="creation mode", request=m.get("prompt"), source=m.get("job_id"), extra={"adopted_later": True})
            done.append(m["id"])
    if _eb is not None:
        for b in _eb.list_builds(200):
            folder = _eb.UI_ROOT / b["name"]
            if b["status"] == "deployed" and folder.is_dir() and not _naming.read_tag(folder) and not _vital.protected(folder):
                _naming.adopt(folder, name=b["name"], kind="engine", owner="engine build", request=b.get("request"), source=b["id"], extra={"adopted_later": True})
                done.append(b["name"])
    return _json_cors({"status": "success", "adopted": done, "need_a_name": needs_name})



if __name__ == "__main__":
    _bootstrap_default_dashboard()
    diagnose_port("localhost", BRIDGE_PORT)

    print(f"\n{'='*50}")
    print(f"DASHBOARD:  http://localhost:{BRIDGE_PORT}/")
    print(f"NEXXUS:     {'DIRECT IMPORT (Active)' if NEXUS_AVAILABLE else 'FALLBACK TO OLLAMA'}")
    print(f"HTML FILE:  {HTML_FILE}")
    print(f"HTML PATH:  {HTML_FOLDER}")
    print(f"{'='*50}\n")

    web_thread = threading.Thread(target=lambda: app.run(host="127.0.0.1", port=BRIDGE_PORT, threaded=True, debug=False, use_reloader=False), daemon=False)
    web_thread.start()
    if _net is not None:                                          # Tailscale / other addresses from NEXXUS_BIND (loopback is always served above); see net_bind.py
        _listeners = _net.Listeners(app, BRIDGE_PORT, os.environ.get("NEXXUS_BIND", "loopback")).start()
        for _p in _listeners.problems:
            print("[NET] " + _p)
    if _telemetry is not None and not os.environ.get("NEXXUS_DISABLE_AUTOSCHEDULER"):
        _telemetry.start()
    if _vital is not None and not os.environ.get("NEXXUS_DISABLE_AUTOSCHEDULER"):
        threading.Thread(target=_vital_loop, daemon=True, name="commercial-watch").start()
    if _notes is not None and not os.environ.get("NEXXUS_DISABLE_AUTOSCHEDULER"):
        threading.Thread(target=_notify_watcher, daemon=True, name="nexxus-notify-watch").start()
    if _notes is not None and _gate is not None and not os.environ.get("NEXXUS_DISABLE_AUTOSCHEDULER"):
        threading.Thread(target=_gate_watcher, daemon=True, name="axis_gate_watch").start()

    # The terminal chat must never be what quietly ends the process while the web server is still
    # up: once the main thread finishes, Python refuses all new background work ("cannot schedule new
    # futures after interpreter shutdown") and every chat/build then fails. So: "exit" / Ctrl+C really
    # shuts the whole server down, and with no usable console the main thread stays alive serving.
    outcome = "headless"
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            outcome = run_terminal()
    except Exception as e:
        print(f"Terminal chat unavailable: {e}")
    if outcome == "exit":
        print("Shutting down the NEXXUS server.")
        sys.stdout.flush()
        os._exit(0)
    web_thread.join()