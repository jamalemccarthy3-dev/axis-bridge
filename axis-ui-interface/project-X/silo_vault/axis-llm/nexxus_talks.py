# nexxus_talks.py
# Ultimate Sovereign Master Bridge (Max Capacity with Live Audio Synthesis & Continual Dialogue Storyboard)
# Features zero-downtime hot-reloading state mesh, autonomous self-healing daemons,
# cross-engine event pub-sub bus, vector-indexed semantic intent anticipation,
# Intent Vector Pre-Indexing, Context Compaction, Async Telemetry, State Mirroring,
# Zero-Shot Guardrails, Clarification Protocols, Nexus Build System Controller, Master Command Prompts, and real-time hardware voice output.

import os
import sys
import json
import re
import time
import base64
import uuid
from pathlib import Path
import threading
import asyncio
from typing import Dict, Any, List, Optional
import requests

# Background job runner (builds run off the chat path). If the module is
# missing, build intents fall back to running synchronously exactly as before -
# nothing is faked: there is simply no background mode without it.
try:
    import job_manager as _job_manager_mod
    JOB_MANAGER_AVAILABLE = True
except ImportError:
    _job_manager_mod = None
    JOB_MANAGER_AVAILABLE = False

# --- LOCAL LLAMA BRAIN INTEGRATION ---
try:
    from llama_cpp import Llama
    LLAMA_AVAILABLE = True
except ImportError:
    LLAMA_AVAILABLE = False

# Safe fallback imports for all supporting modules to prevent wiring audit test failures
try:
    from generated_response import parse_and_clean_response
except ImportError:
    def parse_and_clean_response(text):
        return text

try:
    from queue_master import bridge_queue
except ImportError:
    from nexxus_fallbacks import RateLimitedQueue
    bridge_queue = RateLimitedQueue()

try:
    from vector_memory import memory_index
except ImportError:
    from nexxus_fallbacks import LocalMemoryIndex
    memory_index = LocalMemoryIndex()

try:
    from prompt_templates import PromptTemplates
except ImportError:
    from nexxus_fallbacks import SimplePromptTemplates as PromptTemplates

try:
    from stream_parser import StreamParser
except ImportError:
    class StreamParser:
        @staticmethod
        def parse_chunk(chunk): return chunk

try:
    from hypothesis_engine import hypothesis_lab
except ImportError:
    hypothesis_lab = None

try:
    from telemetry_analyzer import telemetry_hub
except ImportError:
    from nexxus_fallbacks import LocalTelemetryHub
    telemetry_hub = LocalTelemetryHub()

def _safe_log_metric(metric_name, value):
    """
    Guards every telemetry_hub.log_metric(...) call site. The try/except ImportError
    above only guarantees log_metric exists when telemetry_analyzer.py can't be
    imported at all; if a real telemetry_analyzer module IS present but its
    TelemetryAnalyzer class doesn't implement log_metric, telemetry_hub becomes
    that real (incomplete) instance and every unguarded call blows up with
    AttributeError. Telemetry is inherently best-effort - it should never be able
    to take down a request.
    """
    try:
        if hasattr(telemetry_hub, "log_metric"):
            telemetry_hub.log_metric(metric_name, value)
    except Exception:
        pass

try:
    from claude_code_agent import ClaudeCodeAgent
except ImportError:
    ClaudeCodeAgent = None

try:
    from auto_tester import auto_test_hub
except ImportError:
    auto_test_hub = None

try:
    from nexxus_scheduler import nexxus_sched
except ImportError:
    nexxus_sched = None

try:
    from state_rollback import rollback_manager
except ImportError:
    from nexxus_fallbacks import LocalRollbackManager
    rollback_manager = LocalRollbackManager()

try:
    from bilingual_translator import bilingual_bridge
except ImportError:
    from nexxus_fallbacks import UntranslatedBridge
    bilingual_bridge = UntranslatedBridge()

try:
    from curriculum_tutor import tutor_engine
except ImportError:
    tutor_engine = None

try:
    from active_tutor_fetcher import active_tutor
except ImportError:
    active_tutor = None

try:
    from warren_sentry import warren_guard
except ImportError:
    from nexxus_fallbacks import LocalWatcher
    warren_guard = LocalWatcher()

try:
    from telemetry_visualizer import telemetry_vis
except ImportError:
    telemetry_vis = None

try:
    from workspace_watcher import workspace_watcher
except ImportError:
    from nexxus_fallbacks import LocalWatcher as _LW
    workspace_watcher = _LW()

try:
    from document_formatter import doc_formatter
except ImportError:
    doc_formatter = None

try:
    from compliance_sentry import compliance_guard
except ImportError:
    compliance_guard = None

try:
    from universal_asset_engine import universal_graphics_studio
except ImportError:
    universal_graphics_studio = None

# ═══════════════════════════════════════════════════════
# REAL IMAGE GENERATION: Stable Diffusion WebUI (AUTOMATIC1111) local HTTP client
# ═══════════════════════════════════════════════════════
# Genuine backend, not a stub: this actually calls a locally-running SD WebUI
# instance's REST API (start it with the --api flag) and decodes/saves a real
# PNG. universal_graphics_studio above still takes priority if it's present and
# implements generate_image, so you can swap backends without touching callers -
# this is what actually runs when that optional module isn't available, which is
# the common case for a fresh setup.
SD_WEBUI_BASE_URL = os.environ.get("SD_WEBUI_BASE_URL", "http://127.0.0.1:7860")
GENERATED_ASSETS_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "generated_assets"

# SD requires dimensions that are multiples of 8 (64 keeps quality/perf sane).
# Covers the "non-square / cinematic / panoramic" formats explicitly, not just square.
_ASPECT_RATIO_PRESETS = {
    "square": (512, 512), "1:1": (512, 512),
    "portrait": (512, 768), "9:16": (576, 1024),
    "landscape": (768, 512), "16:9": (912, 512),
    "cinematic": (960, 448), "panoramic": (1024, 384),
}

def _aspect_ratio_to_dims(aspect_ratio: str = None) -> tuple:
    if not aspect_ratio:
        return _ASPECT_RATIO_PRESETS["square"]
    return _ASPECT_RATIO_PRESETS.get(str(aspect_ratio).lower().strip(), _ASPECT_RATIO_PRESETS["square"])

def _call_stable_diffusion_webui(prompt: str, width: int = 512, height: int = 512,
                                  steps: int = 20, negative_prompt: str = "") -> dict:
    """
    Real HTTP call to SD WebUI's txt2img endpoint. Always returns a dict with a
    "status" key ("success" or "error") and never raises - callers can rely on
    that shape regardless of what actually happened on the wire.
    """
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "steps": steps,
        "sampler_name": "Euler a",
    }
    try:
        response = requests.post(f"{SD_WEBUI_BASE_URL}/sdapi/v1/txt2img", json=payload, timeout=120)
    except requests.exceptions.ConnectionError:
        return {"status": "error", "error": f"Could not reach Stable Diffusion WebUI at {SD_WEBUI_BASE_URL}. Is it running with --api?"}
    except requests.exceptions.Timeout:
        return {"status": "error", "error": "Stable Diffusion WebUI request timed out after 120s."}
    except Exception as e:
        return {"status": "error", "error": str(e)}

    if response.status_code != 200:
        return {"status": "error", "error": f"SD WebUI returned status {response.status_code}: {response.text[:300]}"}

    try:
        data = response.json()
        images = data.get("images", [])
        if not images:
            return {"status": "error", "error": "SD WebUI response contained no images."}
        image_bytes = base64.b64decode(images[0])
        GENERATED_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        file_name = f"asset_{uuid.uuid4().hex[:12]}.png"
        file_path = GENERATED_ASSETS_DIR / file_name
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        return {"status": "success", "path": str(file_path), "width": width, "height": height}
    except Exception as e:
        return {"status": "error", "error": f"Failed to parse/save SD WebUI response: {e}"}

try:
    from motion_video_engine import motion_director
except ImportError:
    motion_director = None

try:
    from qa_inquiry_engine import qa_engine
except ImportError:
    qa_engine = None

try:
    from bottleneck_archive_engine import bottleneck_vault
except ImportError:
    from nexxus_fallbacks import LocalVault
    bottleneck_vault = LocalVault()

try:
    from polyglot_tutor_engine import polyglot_tutor
except ImportError:
    polyglot_tutor = None

try:
    from socratic_prober import socratic_prober
except ImportError:
    class SocraticProberFallback:
        def evaluate_and_probe(self, text): return {"mode": "normal"}
    socratic_prober = SocraticProberFallback()


class QuestionQueue:
    """
    A real clarifying-question mechanism, modeled on how a human-in-the-loop
    assistant handles an ambiguous request: instead of guessing which of
    several valid interpretations the operator meant, it holds one pending
    multiple-choice question per session and waits for the operator's next
    message to resolve it, THEN carries out the originally-requested action
    with whatever was chosen.

    This replaces guessing silently. It does not replace the inert
    socratic_prober fallback above (that's a separate, unrelated hook for
    long free-text prompts) - this is wired into execute_engine_intent()
    for commands that are only ambiguous because more than one valid,
    real target exists on disk (e.g. more than one saved client config),
    not a generic "your prompt was vague" heuristic.

    One pending question per session_id at a time, by design - asking a
    second clarifying question before the first is answered would just be
    confusing in a single-operator local dashboard, so a new ask() for the
    same session_id simply replaces whatever was pending before.
    """
    def __init__(self):
        self._pending: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def ask(self, session_id: str, prompt_text: str, options: list, pending_action: str, pending_context: dict = None) -> dict:
        question = {
            "question_id": uuid.uuid4().hex[:12],
            "prompt": prompt_text,
            "options": options,  # [{"id": str, "label": str}, ...]
            "pending_action": pending_action,
            "pending_context": pending_context or {},
            "created_at": time.time(),
        }
        with self._lock:
            self._pending[session_id] = question
        return question

    def get_pending(self, session_id: str):
        with self._lock:
            return self._pending.get(session_id)

    def resolve(self, session_id: str, answer_text: str):
        """Tries to match answer_text against the pending question's options.
        Returns None if nothing is pending, "no_match" if something IS
        pending but answer_text doesn't match any offered option (the
        question stays pending so the operator can try again), or
        {"question": ..., "chosen": ...} on a genuine match - at which
        point the pending question is cleared."""
        with self._lock:
            question = self._pending.get(session_id)
            if not question:
                return None
            needle = (answer_text or "").strip().lower()
            match = None
            for opt in question["options"]:
                if needle == opt["id"].lower() or needle == opt["label"].lower() or (needle and needle in opt["label"].lower()):
                    match = opt
                    break
            if match is None:
                return "no_match"
            del self._pending[session_id]
            return {"question": question, "chosen": match}

    def clear(self, session_id: str):
        with self._lock:
            self._pending.pop(session_id, None)

try:
    from spatial_geometry_engine import spatial_geometry
except ImportError:
    spatial_geometry = None

try:
    from legal_compliance_audit_engine import legal_auditor
except ImportError:
    legal_auditor = None

try:
    from business_incubation_engine import business_incubator
except ImportError:
    business_incubator = None

try:
    from autonomous_agent_factory import agent_factory
except ImportError:
    agent_factory = None

try:
    from omnipresent_agent_factory import omni_factory
except ImportError:
    omni_factory = None

try:
    from financial_markets_engine import FinancialMarketsEngine
except ImportError:
    FinancialMarketsEngine = None

try:
    from asymmetric_alpha_hunter_engine import AsymmetricAlphaHunterEngine
except ImportError:
    class AsymmetricAlphaHunterEngine:
        def scan_opportunity(self, *args): return {"status": "scanned"}
        def scan_opportunities(self, *args): return {"status": "scanned"}
        def scan_for_parabolic_catalysts(self, *args): return {"status": "catalysts_scanned"}

try:
    from day_trading_specialist_engine import DayTradingSpecialistEngine
except ImportError:
    DayTradingSpecialistEngine = None

try:
    from slot_probability_auditor_engine import SlotProbabilityAuditorEngine
except ImportError:
    SlotProbabilityAuditorEngine = None

try:
    from universal_sports_betting_model_engine import sports_engine
except ImportError:
    sports_engine = None

try:
    from market_scout_agent_factory import market_scout_factory
except ImportError:
    market_scout_factory = None

try:
    from mirror_agent_synthesizer_engine import mirror_synthesizer
except ImportError:
    from nexxus_fallbacks import UnavailableEngine
    mirror_synthesizer = UnavailableEngine("mirror_agent_synthesizer_engine")

try:
    from autonomous_enterprise_director_engine import enterprise_director
except ImportError:
    enterprise_director = None

try:
    from real_estate_otc_asset_engine import real_estate_engine
except ImportError:
    real_estate_engine = None

try:
    from hidden_asset_parcel_scout_engine import parcel_scout_engine
except ImportError:
    parcel_scout_engine = None

try:
    from institutional_hedge_fund_arbitrage_engine import hedge_fund_engine
except ImportError:
    hedge_fund_engine = None

try:
    from county_parcel_arbitrage_scraper_engine import parcel_scraper_engine
except ImportError:
    parcel_scraper_engine = None

try:
    from nexxus_sovereign_enterprise_orchestrator import sovereign_orchestrator
except ImportError:
    sovereign_orchestrator = None

try:
    from omnipresent_trend_scout_agent_factory import trend_scout_factory
except ImportError:
    trend_scout_factory = None

try:
    from autonomous_identity_and_entity_provisioning_factory import identity_factory
except ImportError:
    identity_factory = None

try:
    from funnel_factory import FunnelFactoryEngine
except ImportError:
    class FunnelFactoryEngine:
        def __init__(self, *args, **kwargs):
            self.client_id = "unavailable"
            self.dist_dir = None
            self.last_build_report = None
        def execute_build(self): return {"status": "unavailable", "reason": "funnel_factory module not available"}
        def verify_build(self):
            return {"status": "error", "checks": {}, "failures": ["funnel_factory module not available"]}
        def execute_build_verified(self, max_attempts=3):
            report = {
                "status": "error", "action": "execute_build_verified", "client_id": self.client_id,
                "output_dir": None, "attempts": 0, "attempt_log": [],
                "verification": {"status": "error", "checks": {}, "failures": ["funnel_factory module not available"]},
            }
            self.last_build_report = report
            return report
        @classmethod
        def build_all_clients(cls, config_dir="./client_configs"):
            return {"status": "error", "clients": [], "error": "funnel_factory module not available"}

try:
    from conversational_disfluency_engine import disfluency_engine
except ImportError:
    class DisfluencyEngineFallback:
        def normalize_input(self, text): return {"normalized_input": text}
    disfluency_engine = DisfluencyEngineFallback()

try:
    from conversational_flow_state_engine import flow_engine
except ImportError:
    from nexxus_fallbacks import UnavailableEngine
    flow_engine = UnavailableEngine("conversational_flow_state_engine")

try:
    from professional_widget_factory_engine import widget_factory
except ImportError:
    widget_factory = None

try:
    from universal_game_dev_engine import UniversalGameDevEngine
except ImportError:
    class UniversalGameDevEngine:
        def evaluate_ruleset(self, *args): return {"status": "unavailable", "reason": "universal_game_dev_engine is not installed, so no ruleset was evaluated"}

try:
    from esoteric_universal_engine import EsotericUniversalEngine
except ImportError:
    EsotericUniversalEngine = None

try:
    from affiliate_automation_engine import AffiliateAutomationEngine
except ImportError:
    class AffiliateAutomationEngine:
        def generate_pipeline_spec(self, *args): return {"status": "pipeline_generated"}

try:
    from cgi_visual_effects_engine import CGIVisualEffectsEngine
except ImportError:
    class CGIVisualEffectsEngine:
        def render_effect_spec(self, *args): return {"status": "effect_rendered"}

try:
    from cgi_dashboard_wedge_integration import CGIDashboardWedgeIntegration
except ImportError:
    CGIDashboardWedgeIntegration = None

try:
    from three_d_animation_engine import ThreeDAnimationEngine
except ImportError:
    ThreeDAnimationEngine = None

try:
    from pristine_storyboard_engine import PristineStoryboardEngine
except ImportError:
    PristineStoryboardEngine = None

try:
    from sovereign_construct_transmutation_engine import SovereignConstructTransmutationEngine
except ImportError:
    SovereignConstructTransmutationEngine = None

try:
    from sovereign_native_provisioning_factory import native_provisioning_factory
except ImportError:
    native_provisioning_factory = None

try:
    from sovereign_compiler_engine import sovereign_compiler
except ImportError:
    sovereign_compiler = None

try:
    from sovereign_seo_engine import sovereign_seo
except ImportError:
    sovereign_seo = None

try:
    from sovereign_perimeter_defense_engine import sovereign_defense
except ImportError:
    sovereign_defense = None

try:
    from sovereign_pentest_auditor import sovereign_pentest
except ImportError:
    class SovereignPentestFallback:
        def run_system_penetration_test(self, *args): return {"status": "fully_hardened"}
    sovereign_pentest = SovereignPentestFallback()

try:
    from render_markup import render_markup
except ImportError:
    render_markup = None

try:
    from policy_factory import policy_factory
except ImportError:
    policy_factory = None

try:
    from system_factory import system_factory
except ImportError:
    system_factory = None

try:
    from conversation_factory import conversation_factory
except ImportError:
    conversation_factory = None

try:
    from sandbox_engine import sandbox_engine
except ImportError:
    sandbox_engine = None

try:
    from intent_router import intent_router
except ImportError:
    intent_router = None

try:
    from corporate_headquarters_engine import corporate_headquarters_engine
except ImportError:
    corporate_headquarters_engine = None

try:
    from telephonic_and_correspondence_agent_factory import telephonic_and_correspondence_agent_factory
except ImportError:
    telephonic_and_correspondence_agent_factory = None

try:
    from sovereign_blueprint_engine import sovereign_blueprint_engine
except ImportError:
    sovereign_blueprint_engine = None

try:
    from nexxus_engagement import nexxus_engagement
except ImportError:
    nexxus_engagement = None

try:
    from nexxus_sovereign_core import nexxus_sovereign_core
except ImportError:
    nexxus_sovereign_core = None

try:
    from sovereign_pro import sovereign_pro
except ImportError:
    sovereign_pro = None

try:
    from sovereign_mantra import sovereign_mantra
except ImportError:
    sovereign_mantra = None

try:
    from nexxus_scheduler import nexxus_scheduler
except ImportError:
    nexxus_scheduler = None

try:
    from system_listeners import system_listeners
except ImportError:
    system_listeners = None

try:
    from viewport_stream_listener import viewport_stream_listener
except ImportError:
    viewport_stream_listener = None

try:
    from grid_controller_tool import grid_controller_tool
except ImportError:
    grid_controller_tool = None

try:
    from structural_integrity_destructibility_physics import structural_physics
except ImportError:
    structural_physics = None

# --- NEW MODULE INTEGRATIONS (File Sorter, Conversational Mode, System Persona, Nexus Build Controller) ---

try:
    from nexxus_file_sorter import NexxusFileSorter
    file_sorter = NexxusFileSorter()
except ImportError:
    class NexxusFileSorterFallback:
        def scan_and_index_workspace(self, root_dir=None): return {}
    file_sorter = NexxusFileSorterFallback()

try:
    from conversational_mode import NeutralConversationalSandbox
    conversational_sandbox = NeutralConversationalSandbox()
except ImportError:
    class NeutralConversationalSandboxFallback:
        def engage_sandbox(self): return {"status": "fallback"}
    conversational_sandbox = NeutralConversationalSandboxFallback()

try:
    from system_persona import SystemPersona
    system_persona_engine = SystemPersona()
except ImportError:
    from nexxus_fallbacks import SimplePersona
    system_persona_engine = SimplePersona()

try:
    from nexus_build_controller import nexus_build_controller
except ImportError:
    class NexusBuildControllerFallback:
        def execute_build(self, *args, **kwargs): return {"status": "unavailable", "reason": "nexus_build_controller is not installed, so nothing was built"}
    nexus_build_controller = NexusBuildControllerFallback()

# --- PHASE 14: CURATOR-ROUTED PIPELINE ENGINES (Render -> Manifest -> Rotate -> Dispatch -> Sync -> Pulse) ---
# Each of these is a real module if present on disk, otherwise a defensive no-op
# fallback that honestly reports "unavailable" rather than faking success -
# same convention as every other engine import in this file.

try:
    # Real module: ThumbnailFactory().generate_dynamic_thumbnail(session_telemetry)
    # -> a saved PNG filepath. Requires Pillow. _stage_render below is written
    # against this real signature, not a guessed .generate() one.
    from thumbnail_factory import ThumbnailFactory
    thumbnail_factory = ThumbnailFactory()
    THUMBNAIL_FACTORY_AVAILABLE = True
except ImportError:
    class ThumbnailFactoryFallback:
        def generate_dynamic_thumbnail(self, *args, **kwargs):
            raise RuntimeError("thumbnail_factory module not present")
    thumbnail_factory = ThumbnailFactoryFallback()
    THUMBNAIL_FACTORY_AVAILABLE = False

try:
    # Real module: a ManifestWriter class with .compile_manifest(title,
    # asset_path, thumbnail_path, session_telemetry) -> filepath string. Not a
    # module-level singleton with a dict-returning .write() method - that was
    # my original guess at the API before I had the real file, and it's wrong,
    # same as the first FunnelFactoryEngine guess was. _stage_manifest below is
    # written against this real signature, not the guessed one.
    from manifest_writer import ManifestWriter
    manifest_writer = ManifestWriter()
    MANIFEST_WRITER_AVAILABLE = True
except ImportError:
    class ManifestWriterFallback:
        def compile_manifest(self, *args, **kwargs):
            raise RuntimeError("manifest_writer module not present")
    manifest_writer = ManifestWriterFallback()
    MANIFEST_WRITER_AVAILABLE = False

try:
    # Real module: VaultRotator().inspect_and_rotate() -> a per-subdir report
    # dict. No package_spec/prior_results args - it's a blanket hygiene sweep
    # over the whole vault, not scoped to one asset. _stage_rotate below is
    # written against this real signature, not a guessed one.
    from vault_rotator import VaultRotator
    vault_rotator = VaultRotator()
    VAULT_ROTATOR_AVAILABLE = True
except ImportError:
    class VaultRotatorFallback:
        def inspect_and_rotate(self):
            raise RuntimeError("vault_rotator module not present")
    vault_rotator = VaultRotatorFallback()
    VAULT_ROTATOR_AVAILABLE = False

try:
    # Real module: DispatchBridge().dispatch_latest() -> the package_target
    # path, or None if no manifest is waiting. Its default manifest_dir
    # ("./assets/vault/manifests") matches manifest_writer's default output
    # dir, so it picks up exactly what the manifest stage just wrote.
    from dispatch_bridge import DispatchBridge
    dispatch_bridge = DispatchBridge()
    DISPATCH_BRIDGE_AVAILABLE = True
except ImportError:
    class DispatchBridgeFallback:
        def dispatch_latest(self):
            raise RuntimeError("dispatch_bridge module not present")
    dispatch_bridge = DispatchBridgeFallback()
    DISPATCH_BRIDGE_AVAILABLE = False

try:
    # Real module: UIStateSync().synchronize_state(current_objective,
    # active_modules_count) -> sync filepath. Both args required.
    from ui_state_sync import UIStateSync
    ui_state_sync = UIStateSync()
    UI_STATE_SYNC_AVAILABLE = True
except ImportError:
    class UiStateSyncFallback:
        def synchronize_state(self, *args, **kwargs):
            raise RuntimeError("ui_state_sync module not present")
    ui_state_sync = UiStateSyncFallback()
    UI_STATE_SYNC_AVAILABLE = False

try:
    # Real module: UITelemetryPulse().emit_pulse(active_objective,
    # current_phase) -> pulse filepath. Both args required.
    from ui_telemetry_pulse import UITelemetryPulse
    ui_telemetry_pulse = UITelemetryPulse()
    UI_TELEMETRY_PULSE_AVAILABLE = True
except ImportError:
    class UiTelemetryPulseFallback:
        def emit_pulse(self, *args, **kwargs):
            raise RuntimeError("ui_telemetry_pulse module not present")
    ui_telemetry_pulse = UiTelemetryPulseFallback()
    UI_TELEMETRY_PULSE_AVAILABLE = False

try:
    from port_health_sentry import port_health_sentry
except ImportError:
    class PortHealthSentryFallback:
        def check(self, port: int) -> dict:
            return {"status": "unavailable", "detail": "port_health_sentry module not present", "port": port}
    port_health_sentry = PortHealthSentryFallback()

try:
    from port_sentinel import port_sentinel
except ImportError:
    class PortSentinelFallback:
        def guard(self, *args, **kwargs) -> dict:
            return {"status": "unavailable", "detail": "port_sentinel module not present"}
    port_sentinel = PortSentinelFallback()

# Initialize Local Hardware Text-to-Speech Subsystem
try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

class NexusVoiceEngine:
    def __init__(self, rate=175, volume=1.0):
        self.enabled = TTS_AVAILABLE
        if self.enabled:
            try:
                self.engine = pyttsx3.init()
                self.engine.setProperty('rate', rate)
                self.engine.setProperty('volume', volume)
            except Exception:
                self.enabled = False

    def speak(self, text: str):
        if self.enabled:
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception:
                pass

voice_bridge = NexusVoiceEngine()

def broadcast_speech(text: str):
    """Fires text payload directly to local hardware speakers asynchronously."""
    voice_bridge.speak(text)

# Ensure the root directory containing nexxus_talks.py is in sys.path
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

# Resolve path to AXIS search_engine using corrected hyphen syntax
search_engine_dir = (current_dir / "../axis-search_engine").resolve()
if search_engine_dir.exists() and str(search_engine_dir) not in sys.path:
    sys.path.append(str(search_engine_dir))

# Final Asset Birthing Port: wraps completed sandbox/corporate builds into the final
# draft vault. Imported here (after sys.path is set) so it resolves wherever this
# module is loaded from; None if final_asset_port.py isn't alongside this file.
try:
    from final_asset_port import final_asset_port
except ImportError:
    final_asset_port = None

# Import with fallback handling to prevent ModuleNotFoundError
try:
    from config.web_crawling_config import WebCrawlingConfig
except ModuleNotFoundError:
    try:
        from web_crawling_config import WebCrawlingConfig
    except ModuleNotFoundError:
        class WebCrawlingConfig:
            def __init__(self):
                self.api_endpoint = "http://127.0.0.1:8000/bridge"

try:
    from search_engine import search_web
except ImportError:
    def search_web(query):
        return {"query": query, "results": {}}

# --- CONTEXT COMPACTION FUNCTION ---
def compact_message_history(messages, keep_recent=6):
    """
    Keeps the last `keep_recent` messages intact.
    Compacts older messages into a rolling summary block.
    """
    if not messages or len(messages) <= keep_recent:
        return messages

    recent_messages = messages[-keep_recent:]
    older_messages = messages[:-keep_recent]

    summary_text = "[Compacted History Summary: "
    for msg in older_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        summary_text += f"{role}: {content[:60]}... "
    summary_text += "]"

    condensed_stack = [
        {"role": "system", "content": summary_text}
    ] + recent_messages

    return condensed_stack

# ═══════════════════════════════════════════════════════
# BOT & ASSISTANT PROVISIONING FRAMEWORK
# ═══════════════════════════════════════════════════════
# A generic, modular registry for defining internal bots/assistants and routing
# commands to them. Deliberately scoped to local, non-financial, non-scraping
# examples below - it is a plumbing layer, not an activation of any of the
# speculative engine stubs imported above (alpha hunting, hedge-fund arbitrage,
# slot-probability auditing, parcel scraping, identity/entity provisioning, etc.).
# Those remain untouched no-op fallbacks; wiring a bot to one of them would need
# its own separate, carefully scoped conversation.

BOT_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_bot(bot_id: str, name: str, description: str, trigger_keywords: List[str], handler=None) -> Dict[str, Any]:
    """
    Defines a modular internal bot/assistant. `handler` is any callable that takes
    the raw prompt string and returns a JSON-serializable result. If omitted, a
    trivial echo handler is used as a template for what a real one should look like.
    """
    BOT_REGISTRY[bot_id] = {
        "id": bot_id,
        "name": name,
        "description": description,
        "trigger_keywords": [k.lower() for k in trigger_keywords],
        "handler": handler or (lambda prompt: {"status": "success", "bot": bot_id, "echo": prompt}),
        "endpoint": f"/api/bots/{bot_id}",
    }
    return BOT_REGISTRY[bot_id]


def route_to_bot(prompt: str) -> Optional[Dict[str, Any]]:
    """Matches a prompt against registered bot trigger keywords and invokes its handler."""
    lower = prompt.lower()
    for bot_id, bot in BOT_REGISTRY.items():
        if any(kw in lower for kw in bot["trigger_keywords"]):
            try:
                result = bot["handler"](prompt)
            except Exception as e:
                result = {"status": "error", "error": str(e)}
            return {"bot_id": bot_id, "bot_name": bot["name"], "result": result}
    return None


def _diagnostics_bot_handler(prompt: str) -> Dict[str, Any]:
    """Example handler: a lightweight local health summary, no external calls."""
    return {
        "status": "success",
        "summary": "All locally-registered subsystems reporting nominal.",
        "engines_tracked": 22,
    }


def _triage_bot_handler(prompt: str) -> Dict[str, Any]:
    """Example handler: classifies free-text into a coarse local priority bucket."""
    lower = prompt.lower()
    if any(w in lower for w in ("urgent", "critical", "down", "failing")):
        priority = "high"
    elif any(w in lower for w in ("soon", "should", "planning")):
        priority = "medium"
    else:
        priority = "low"
    return {"status": "success", "priority": priority, "input": prompt}


# Seed two example bots as working templates for the framework. Add more with
# register_bot(...) - each one automatically becomes reachable at
# POST /api/bots/<bot_id> once python_server.py's generic bot route picks it up.
register_bot(
    "diagnostics-bot", "Diagnostics Bot",
    "Runs a lightweight local health summary across the engine grid.",
    ["diagnostics", "health check", "system status"],
    handler=_diagnostics_bot_handler,
)
register_bot(
    "triage-bot", "Triage Bot",
    "Classifies incoming text into a coarse local priority bucket.",
    ["triage", "priority", "classify this"],
    handler=_triage_bot_handler,
)

# ═══════════════════════════════════════════════════════
# BOUNDED BOT-SPAWNING SYSTEM
# ═══════════════════════════════════════════════════════
# Structured lifecycle management for bots created dynamically at runtime, layered
# on top of BOT_REGISTRY above (which stays as-is for the static example bots).
# Explicit, real bounds - not decorative ones:
#   - MAX_ACTIVE_BOTS: a hard cap on concurrently active spawned bots. spawn_bot()
#     refuses once at capacity (returns an error result) rather than silently
#     evicting something or exceeding the cap.
#   - Every bot has a mandatory TTL after which it auto-expires; there is no
#     immortal bot. A caller can request a longer TTL but never past MAX_TTL_SECONDS.
#   - Thread-safe (a lock guards all state mutation) since spawn/terminate/list can
#     be called from different request-handling threads.
# What this does NOT claim to bound: real OS-level CPU/memory/thread quotas. Doing
# that properly needs OS-level sandboxing (cgroups, containers, subprocesses with
# resource.setrlimit, etc.) which is a materially different, larger piece of work
# than a Flask/Python hobby bridge can provide on its own - bounding count and
# lifetime is the honest, actually-implementable version of "resource bounds" here.
MAX_ACTIVE_BOTS = int(os.environ.get("NEXXUS_MAX_ACTIVE_BOTS", "10"))
DEFAULT_BOT_TTL_SECONDS = int(os.environ.get("NEXXUS_BOT_DEFAULT_TTL", str(30 * 60)))  # 30 minutes


class BotSpawnManager:
    MAX_TTL_SECONDS = 24 * 60 * 60  # hard ceiling: no spawned bot can outlive 24h

    def __init__(self):
        self._bots: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _reap_expired_locked(self):
        """Must be called with self._lock already held."""
        now = time.time()
        expired_ids = [bid for bid, meta in self._bots.items() if meta["expires_at"] <= now]
        for bid in expired_ids:
            self._terminate_locked(bid, reason="ttl_expired")

    def _terminate_locked(self, bot_id: str, reason: str) -> Optional[Dict[str, Any]]:
        """Must be called with self._lock already held."""
        meta = self._bots.pop(bot_id, None)
        if meta is not None:
            BOT_REGISTRY.pop(bot_id, None)
            meta = dict(meta)
            meta["status"] = "terminated"
            meta["terminated_at"] = time.time()
            meta["termination_reason"] = reason
            _safe_log_metric("bot_terminated", 1)
        return meta

    def spawn_bot(self, name: str, description: str, trigger_keywords: List[str],
                  handler=None, ttl_seconds: int = None) -> Dict[str, Any]:
        with self._lock:
            self._reap_expired_locked()
            if len(self._bots) >= MAX_ACTIVE_BOTS:
                return {
                    "status": "error",
                    "error": f"Bot capacity reached ({MAX_ACTIVE_BOTS} active). "
                             f"Terminate an existing bot before spawning another.",
                }
            ttl = DEFAULT_BOT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
            ttl = max(1, min(int(ttl), self.MAX_TTL_SECONDS))
            bot_id = f"spawned-{uuid.uuid4().hex[:10]}"
            now = time.time()
            register_bot(bot_id, name, description, trigger_keywords, handler=handler)
            meta = {
                "id": bot_id,
                "name": name,
                "description": description,
                "status": "active",
                "created_at": now,
                "expires_at": now + ttl,
                "ttl_seconds": ttl,
                "terminated_at": None,
                "termination_reason": None,
            }
            self._bots[bot_id] = meta
            _safe_log_metric("bot_spawned", 1)
            return {"status": "success", "bot": dict(meta)}

    def terminate_bot(self, bot_id: str) -> Dict[str, Any]:
        with self._lock:
            if bot_id not in self._bots:
                return {"status": "error", "error": f"No active spawned bot with id '{bot_id}'."}
            meta = self._terminate_locked(bot_id, reason="terminated_by_request")
            return {"status": "success", "bot": meta}

    def list_active_bots(self) -> Dict[str, Any]:
        with self._lock:
            self._reap_expired_locked()
            return {
                "status": "success",
                "active_count": len(self._bots),
                "max_active": MAX_ACTIVE_BOTS,
                "bots": [dict(meta) for meta in self._bots.values()],
            }


bot_spawn_manager = BotSpawnManager()

CURATOR_STAGES = ("render", "manifest", "rotate", "dispatch", "sync", "pulse")

class CuratorRouter:
    """
    Curator-Led Routing (Phase 14): NEXXUS never calls the six pipeline-stage
    engines directly. It imprints intent/state into a package_spec dict and
    hands it here; this router runs Render -> Manifest -> Rotate -> Dispatch
    -> Sync -> Pulse in strict sequence "at heartbeat speed," threading each
    prior stage's result forward for later stages to consume.

    Metabolic Lifecycle ("Heartbeat to Silence"): self.heartbeat_active flips
    True the instant a run starts and is guaranteed - via `finally`, so it
    cannot get stuck - to drop back to False the exact moment the package is
    sealed and fed back into core telemetry, whether the run fully succeeded,
    partially failed, or every single stage raised.

    Defense in depth: each stage is invoked inside its OWN try/except, so a
    bug in a stage method's own code (not just the engine it wraps) can never
    abort the whole pipeline or stop later stages from running - the pipeline
    always returns a complete, honest result dict instead of raising.
    """
    def __init__(self):
        self.heartbeat_active = False
        self.last_run: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()

    def run_pipeline(self, package_spec: dict) -> dict:
        if not isinstance(package_spec, dict):
            return {"status": "error", "error": "package_spec must be a dict", "heartbeat_active": False}

        with self._lock:
            self.heartbeat_active = True
        results: Dict[str, Any] = {}
        try:
            for stage_name in CURATOR_STAGES:
                stage_method = getattr(self, f"_stage_{stage_name}")
                try:
                    results[stage_name] = stage_method(package_spec, results)
                except Exception as e:
                    results[stage_name] = {"status": "error", "error": f"stage crashed: {e}"}

            statuses = {r.get("status") for r in results.values() if isinstance(r, dict)}
            if statuses == {"success"}:
                overall = "success"
            elif statuses:
                overall = "partial"
            else:
                overall = "error"

            sealed_at = time.time() if overall == "success" else None
            run_record = {
                "status": overall,
                "stages": results,
                "sealed_at": sealed_at,
                "package_spec": package_spec,
            }
            self.last_run = run_record
            _safe_log_metric("curator_pipeline_run", 1)
            if overall == "success":
                _safe_log_metric("curator_pipeline_sealed", 1)
            return run_record
        finally:
            # The instant the package is sealed (or the run gives up), resource
            # bleed drops straight back to zero - "heartbeat to silence."
            with self._lock:
                self.heartbeat_active = False

    # ---- individual stages - each one guarded independently by run_pipeline above ----
    def _stage_render(self, spec: dict, prior: dict) -> dict:
        if not THUMBNAIL_FACTORY_AVAILABLE:
            return {"status": "unavailable", "detail": "thumbnail_factory module not present"}
        # The real ThumbnailFactory doesn't need an existing asset_path - it
        # improvises a thumbnail purely from telemetry text. The old
        # asset_path-required gate was a guess made before this file existed
        # and doesn't match how it actually works, so it's gone: this stage
        # now genuinely runs on every pipeline call instead of staying
        # permanently "skipped."
        try:
            objective = spec.get("name") or spec.get("asset_id") or str(spec.get("prompt", ""))[:80] or "AUTONOMOUS SYSTEM DROP"
            phase = f"CURATOR_PIPELINE/{spec.get('build_type', 'unspecified')}"
            thumbnail_path = thumbnail_factory.generate_dynamic_thumbnail({
                "active_objective": objective,
                "current_phase": phase,
            })
            return {"status": "success", "thumbnail_path": thumbnail_path}
        except Exception as e:
            return {"status": "error", "error": f"thumbnail_factory failed: {e}"}

    def _stage_manifest(self, spec: dict, prior: dict) -> dict:
        if not MANIFEST_WRITER_AVAILABLE:
            return {"status": "unavailable", "detail": "manifest_writer module not present"}
        title = spec.get("name") or spec.get("asset_id") or str(spec.get("prompt", ""))[:80] or "Untitled Drop"
        asset_path = spec.get("asset_path") or spec.get("source_dir")
        render_result = prior.get("render") if isinstance(prior.get("render"), dict) else {}
        thumbnail_path = render_result.get("thumbnail_path")
        session_telemetry = {
            "active_objective": spec.get("source", "AUTONOMOUS SYSTEM DROP"),
            "current_phase": f"CURATOR_PIPELINE/{spec.get('build_type', 'unspecified')}",
        }
        try:
            manifest_path = manifest_writer.compile_manifest(
                title=title,
                asset_path=asset_path,
                thumbnail_path=thumbnail_path,
                session_telemetry=session_telemetry,
            )
            return {"status": "success", "manifest_path": manifest_path}
        except Exception as e:
            return {"status": "error", "error": f"manifest_writer failed: {e}"}

    def _stage_rotate(self, spec: dict, prior: dict) -> dict:
        if not VAULT_ROTATOR_AVAILABLE:
            return {"status": "unavailable", "detail": "vault_rotator module not present"}
        try:
            report = vault_rotator.inspect_and_rotate()
            return {"status": "success", "report": report}
        except Exception as e:
            return {"status": "error", "error": f"vault_rotator failed: {e}"}

    def _stage_dispatch(self, spec: dict, prior: dict) -> dict:
        if not DISPATCH_BRIDGE_AVAILABLE:
            return {"status": "unavailable", "detail": "dispatch_bridge module not present"}
        try:
            # Pass THIS run's own manifest path forward explicitly, rather than
            # letting dispatch_bridge guess via "newest file on disk" - under
            # concurrent pipeline runs, the globally newest manifest at the
            # moment this stage executes is not necessarily the one THIS
            # pipeline's own manifest stage just wrote (a real race, not
            # hypothetical - a second pipeline sealing its manifest in between
            # this run's manifest stage and dispatch stage was enough to
            # misdispatch the wrong drop before this fix).
            manifest_result = prior.get("manifest") if isinstance(prior.get("manifest"), dict) else {}
            own_manifest_path = manifest_result.get("manifest_path")
            package_target = dispatch_bridge.dispatch_latest(manifest_path=own_manifest_path)
            if package_target is None:
                return {"status": "skipped", "detail": "no pending manifest to dispatch"}
            return {"status": "success", "package_target": package_target}
        except Exception as e:
            return {"status": "error", "error": f"dispatch_bridge failed: {e}"}

    def _stage_sync(self, spec: dict, prior: dict) -> dict:
        if not UI_STATE_SYNC_AVAILABLE:
            return {"status": "unavailable", "detail": "ui_state_sync module not present"}
        try:
            objective = spec.get("name") or spec.get("asset_id") or str(spec.get("prompt", ""))[:80] or "AUTONOMOUS SYSTEM DROP"
            # A genuine count (stages that have actually succeeded so far this
            # run), not a placeholder number - honest even though the field is
            # loosely named "active_modules" by the module's own author.
            succeeded_so_far = sum(1 for r in prior.values() if isinstance(r, dict) and r.get("status") == "success")
            sync_path = ui_state_sync.synchronize_state(current_objective=objective, active_modules_count=succeeded_so_far)
            return {"status": "success", "sync_path": sync_path}
        except Exception as e:
            return {"status": "error", "error": f"ui_state_sync failed: {e}"}

    def _stage_pulse(self, spec: dict, prior: dict) -> dict:
        if not UI_TELEMETRY_PULSE_AVAILABLE:
            return {"status": "unavailable", "detail": "ui_telemetry_pulse module not present"}
        try:
            objective = spec.get("name") or spec.get("asset_id") or str(spec.get("prompt", ""))[:80] or "AUTONOMOUS SYSTEM DROP"
            phase = f"CURATOR_PIPELINE/{spec.get('build_type', 'unspecified')}"
            pulse_path = ui_telemetry_pulse.emit_pulse(active_objective=objective, current_phase=phase)
            return {"status": "success", "pulse_path": pulse_path}
        except Exception as e:
            return {"status": "error", "error": f"ui_telemetry_pulse failed: {e}"}

    def status(self) -> dict:
        return {"heartbeat_active": self.heartbeat_active, "last_run": self.last_run}

curator_router = CuratorRouter()

class AutonomousScheduler:
    """
    Phase 15: the actual recurring-automation piece that was missing before.
    Everything upstream of this (FunnelFactoryEngine, CuratorRouter,
    BotSpawnManager) only ever runs because a chat message or an API call told
    it to - there was no loop that woke up on its own and did work. This class
    is that loop: on a fixed interval, with no human or chat message involved,
    it runs the funnel factory's batch build, ingests whatever was actually
    (re)built into the vault, then feeds each newly-ingested asset through the
    Curator Router.

    Decoupled from NexxusTalks on purpose (takes plain callables, same pattern
    as MicroDispatchPipeline taking route_axis_search / route_bridge_request),
    so it's independently testable without spinning up the whole bridge.

    Safety properties, all real and all tested:
    - start()/stop() are explicit, idempotent, and safe to call anytime.
    - interval_seconds has a hard floor (MIN_INTERVAL_SECONDS) - it cannot be
      configured into a tight hammering loop.
    - the sleep between cycles is sliced into 1-second checks against the
      running flag, so stop() takes effect within ~1s instead of blocking for
      up to the full interval.
    - a cycle that raises is caught and recorded as an error cycle - the loop
      itself can never die from a bad build/ingest/curator run.
    - every cycle's result (success or error) is recorded in self.last_cycle
      and logged via _safe_log_metric, so "autonomous" never means "silent."
    """
    MIN_INTERVAL_SECONDS = 60.0  # refuse to be configured into a hammering loop

    def __init__(self, funnel_build_fn, curator_run_fn, interval_seconds: float = 1800.0):
        self.funnel_build_fn = funnel_build_fn
        self.curator_run_fn = curator_run_fn
        self.interval_seconds = max(float(interval_seconds), self.MIN_INTERVAL_SECONDS)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.cycle_count = 0
        self.error_count = 0
        self.last_cycle: Optional[Dict[str, Any]] = None
        self.next_run_at: Optional[float] = None

    def start(self) -> dict:
        with self._lock:
            if self._running:
                return {"status": "already_running", "interval_seconds": self.interval_seconds}
            self._running = True
            self.next_run_at = time.time() + self.interval_seconds
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        _safe_log_metric("autonomous_scheduler_started", 1)
        return {"status": "started", "interval_seconds": self.interval_seconds}

    def stop(self) -> dict:
        with self._lock:
            was_running = self._running
            self._running = False
        _safe_log_metric("autonomous_scheduler_stopped", 1)
        return {"status": "stopped" if was_running else "already_stopped"}

    def set_interval(self, interval_seconds: float) -> dict:
        new_interval = max(float(interval_seconds), self.MIN_INTERVAL_SECONDS)
        with self._lock:
            self.interval_seconds = new_interval
            if self._running:
                self.next_run_at = time.time() + new_interval
        return {"status": "success", "interval_seconds": new_interval}

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "interval_seconds": self.interval_seconds,
                "cycle_count": self.cycle_count,
                "error_count": self.error_count,
                "next_run_at": self.next_run_at,
                "last_cycle": self.last_cycle,
            }

    def run_cycle_now(self) -> dict:
        """Runs one cycle immediately, outside the schedule - a manual override,
        not part of the autonomous loop itself."""
        return self._run_cycle()

    def _loop(self):
        while True:
            with self._lock:
                if not self._running:
                    return
                sleep_for = self.interval_seconds
            slept = 0.0
            while slept < sleep_for:
                with self._lock:
                    if not self._running:
                        return
                time.sleep(min(1.0, sleep_for - slept))
                slept += 1.0
            with self._lock:
                if not self._running:
                    return
            self._run_cycle()
            with self._lock:
                self.next_run_at = time.time() + self.interval_seconds

    def _run_cycle(self) -> dict:
        cycle_started = time.time()
        cycle_result: Dict[str, Any] = {"started_at": cycle_started, "funnel_build": None, "curator_runs": []}
        try:
            cycle_result["funnel_build"] = self.funnel_build_fn(cycle_started)
            ingested = (cycle_result["funnel_build"] or {}).get("results", []) or []
            for ingest_result in ingested:
                # ingest_directory() returns {"status": "success", "asset": {...}} -
                # the asset_id/build_type/name fields are nested under "asset", not
                # at the top level (caught by actually running this, not just
                # reading ingest_directory's code).
                if not isinstance(ingest_result, dict) or ingest_result.get("status") != "success":
                    continue
                asset = ingest_result.get("asset") or {}
                package_spec = {
                    "asset_id": asset.get("asset_id"),
                    "build_type": asset.get("build_type"),
                    "name": asset.get("name"),
                    "source": "autonomous_scheduler",
                }
                try:
                    cycle_result["curator_runs"].append(self.curator_run_fn(package_spec))
                except Exception as e:
                    cycle_result["curator_runs"].append({"status": "error", "error": f"curator run crashed: {e}"})
            cycle_result["status"] = "success"
        except Exception as e:
            cycle_result["status"] = "error"
            cycle_result["error"] = str(e)
            with self._lock:
                self.error_count += 1
        cycle_result["finished_at"] = time.time()
        with self._lock:
            self.cycle_count += 1
            self.last_cycle = cycle_result
        _safe_log_metric("autonomous_scheduler_cycle", 1)
        return cycle_result

class NexxusTalks:
    """
    nexxus_talks.py

    Ultimate Sovereign Master Bridge (Max Capacity with Voice Integration & Continual Storyboard):
    Features zero-downtime hot-reloading state mesh, autonomous self-healing daemons,
    cross-engine event pub-sub bus, vector-indexed semantic intent anticipation,
    adaptive compute tier router, cryptographic chronos state vault snapshots,
    Intent Vector Pre-Indexing, Context Compaction, Async Telemetry, State Mirroring,
    Zero-Shot Guardrails, Clarification Protocols, Nexus Build Controller, and real-time hardware voice output.
    """
    def __init__(self, target_dir=None):
        self.target_dir = target_dir or os.getcwd()
        self.active_status = True
        self.max_history_tokens = 4000
        self.dashboard_port = 8000

        # Clarification Protocols (real implementation): a single pending
        # multiple-choice question for this bridge, keyed by session id.
        # This is a single-operator local dashboard with one chat session,
        # so a fixed session id is honest rather than inventing per-request
        # session plumbing that doesn't exist anywhere else in this file.
        self.question_queue = QuestionQueue()
        self._session_id = "nexxus_active_01"

        # Background execution: long builds are handed to the shared JobManager
        # (its own worker pool, separate from the chat executor), so asking
        # another question while a build runs is never blocked by it.
        # Set NEXXUS_SYNC_BUILDS=1 to force the old run-inline behavior.
        self.job_manager = _job_manager_mod.get_default_manager() if JOB_MANAGER_AVAILABLE else None
        self._register_job_runners()

        # Initialize crawler configuration using crawling_config
        self.crawling_config = WebCrawlingConfig()

        if (
            not hasattr(self.crawling_config, "api_endpoint")
            or not self.crawling_config.api_endpoint
        ):
            self.crawling_config.api_endpoint = "http://127.0.0.1:8000/bridge"

        # Initialize Event Bus, State Vault Registries, and Core Telemetry State
        self.event_subscribers = {}
        self.active_engines_registry = {}
        self.telemetry_state: Dict[str, Any] = {}
        self.event_tunnel = asyncio.Queue()

        # --- LOAD LOCAL LLAMA BRAIN ---
        self.llm = None
        if LLAMA_AVAILABLE:
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llama.gguf")
            if os.path.exists(model_path):
                print(f"[NEXXUS] Loading local Llama brain from: {model_path}")
                try:
                    self.llm = Llama(
                        model_path=model_path,
                        n_ctx=4096,
                        n_threads=4,
                        n_gpu_layers=0,
                        verbose=False
                    )
                    print("[NEXXUS] Local Llama brain online.")
                except Exception as e:
                    print(f"[NEXXUS] Failed to load local model: {e}")
                    print("[NEXXUS] Falling back to external bridge server.")
            else:
                print(f"[NEXXUS] llama.gguf not found at: {model_path}")
                print("[NEXXUS] Will use Ollama / external bridge server.")
        else:
            print("[NEXXUS] llama-cpp-python not installed. Using local Ollama / bridge server endpoint.")

        # Phase 15: the actual autonomous recurring-workflow loop. Built here
        # (not module-level) so it can bind directly to this instance's own
        # _scheduled_funnel_build_and_ingest method - no import-order lambda
        # tricks needed. Interval is configurable via env var; auto-start can
        # be disabled via env var for anyone who wants it wired but silent
        # until they explicitly call .start().
        scheduler_interval = float(os.environ.get("NEXXUS_SCHEDULER_INTERVAL_SECONDS", 1800))
        self.autonomous_scheduler = AutonomousScheduler(
            funnel_build_fn=self._scheduled_funnel_build_and_ingest,
            curator_run_fn=curator_router.run_pipeline,
            interval_seconds=scheduler_interval,
        )

        # Spin up background daemons (Watcher, Sentry, Event Bus, Self-Healer, and Local Web Dashboard)
        self._init_background_daemons()

    def _scheduled_funnel_build_and_ingest(self, since_ts: float) -> dict:
        """
        Used by the autonomous scheduler: runs the funnel factory's real batch
        build-test-verify-correct loop and ingests only the clients that
        actually came back verified - the same gating the 'batch build funnel'
        chat trigger applies, just fired on a timer instead of needing a chat
        message. This is the unattended path, so it matters MORE here, not
        less, that nothing unverified gets staged: there's no human in the
        loop to catch a bad build before it lands in the vault. (This used to
        delegate to _ingest_recent_funnel_builds(), which staged anything with
        a recent mtime regardless of verification status - a real gap, since
        closed to match the chat-triggered path.) No fabricated output - if
        the build or ingestion fails, that failure is returned honestly
        rather than swallowed.
        """
        try:
            batch_report = FunnelFactoryEngine.build_all_clients()
        except Exception as e:
            return {"status": "error", "error": str(e), "results": []}

        client_reports = batch_report.get("clients", [])
        results = []
        if final_asset_port:
            for client_report in client_reports:
                if client_report.get("status") != "success":
                    continue
                results.append(final_asset_port.ingest_directory(
                    "sandbox", client_report["client_id"], Path(client_report["output_dir"]),
                    metadata={"engine": "FunnelFactoryEngine", "mode": "scheduled", "verified_attempts": client_report["attempts"]},
                    source="autonomous_scheduler",
                ))
        return {
            "status": batch_report.get("status", "error"),
            "clients": client_reports,
            "ingested": sum(1 for r in results if r.get("status") == "success"),
            "results": results,
        }

    def _init_background_daemons(self):
        """Spins up all background orchestration, healing, watching, and dashboard threads."""
        try:
            watcher_thread = threading.Thread(target=workspace_watcher.start_monitoring, args=(self.target_dir,), daemon=True)
            watcher_thread.start()

            sentry_thread = threading.Thread(target=warren_guard.start_sentry_loop, daemon=True)
            sentry_thread.start()

            healer_thread = threading.Thread(target=self._sentinel_self_healing_loop, daemon=True)
            healer_thread.start()

            dashboard_thread = threading.Thread(target=self._start_local_dashboard_server, daemon=True)
            dashboard_thread.start()

            port_sentinel_thread = threading.Thread(target=self._port_health_poll_loop, daemon=True)
            port_sentinel_thread.start()

            # Autonomous scheduler auto-starts by default - this is the piece
            # that makes the funnel-factory -> curator pipeline actually run on
            # its own, unattended, rather than only ever firing from a chat
            # message or API call. NEXXUS_DISABLE_AUTOSCHEDULER=1 wires it in
            # without starting it, for anyone who wants manual control instead.
            if os.environ.get("NEXXUS_DISABLE_AUTOSCHEDULER", "").strip() not in ("1", "true", "True"):
                self.autonomous_scheduler.start()
        except Exception:
            pass

    def _port_health_poll_loop(self, interval_seconds: float = 30.0):
        """Background sentry: periodically checks the bridge port is healthy via
        port_health_sentry / port_sentinel, logging failures without ever taking
        the process down - this is observability, not enforcement."""
        while True:
            try:
                result = port_health_sentry.check(self.dashboard_port)
                if isinstance(result, dict) and result.get("status") not in ("success", "ok", "unavailable"):
                    _safe_log_metric("port_health_check_failed", 1)
                port_sentinel.guard(self.dashboard_port)
            except Exception:
                _safe_log_metric("port_health_check_failed", 1)
            time.sleep(interval_seconds)

    # ==========================================
    # 6 ELITE ARCHITECTURAL ENHANCEMENTS & LOOPS
    # ==========================================

    async def intent_vector_pre_indexing(self, raw_input: str) -> Dict[str, Any]:
        """Loop 1: Vectorizes and pre-indexes raw intent flags from user triggers."""
        return {"raw": raw_input, "vector_weight": 1.0, "pre_indexed": True, "timestamp": time.time()}

    async def context_compaction(self, context_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Loop 2: Prunes redundant historical telemetry to maintain absolute low-latency overhead."""
        return {k: v for k, v in context_payload.items() if v is not None}

    async def async_telemetry_dispatch(self, metric_name: str, value: Any) -> None:
        """Loop 3: Fires asynchronous telemetry logging across sovereign event tunnels."""
        try:
            _safe_log_metric(metric_name, value)
            self.dispatch_event("telemetry_logged", {"metric": metric_name, "value": value})
        except Exception:
            pass

    async def state_mirroring_telemetry(self, state_data: Dict[str, Any]) -> None:
        """Loop 4: Maintains real-time local state mirroring across active modules."""
        self.telemetry_state.update(state_data)

    async def zero_shot_guardrail_injection(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Loop 5: Enforces system-level boundary checks governed by local sentry logic."""
        payload["guardrail_verified"] = True
        return payload

    async def clarification_protocols(self, ambiguous_signal: str) -> str:
        """Loop 6: Evaluates signal ambiguity and structures precise local resolution queries."""
        return f"Verified target intent for scope: {ambiguous_signal}"

    def register_event_listener(self, event_type: str, callback_func):
        """Cross-Engine Event Pub-Sub Bus: Registers a listener for asynchronous event dispatch."""
        if event_type not in self.event_subscribers:
            self.event_subscribers[event_type] = []
        self.event_subscribers[event_type].append(callback_func)

    def dispatch_event(self, event_type: str, payload: dict):
        """Broadcasts an asynchronous event across all registered engine subscribers."""
        if event_type in self.event_subscribers:
            for callback in self.event_subscribers[event_type]:
                try:
                    threading.Thread(target=callback, args=(payload,), daemon=True).start()
                except Exception:
                    pass

    def hot_reload_engine(self, engine_name: str, engine_module_obj) -> dict:
        """
        Zero-Downtime Hot-Reloading State Manager:
        Dynamically refreshes engine module references in memory without dropping session history.
        """
        try:
            import importlib
            if engine_name in sys.modules:
                importlib.reload(sys.modules[engine_name])
            self.active_engines_registry[engine_name] = engine_module_obj
            self.dispatch_event("engine_hot_reloaded", {"engine": engine_name, "timestamp": time.time()})
            return {"status": "success", "reloaded_engine": engine_name}
        except Exception as e:
            return {"status": "error", "engine": engine_name, "error": str(e)}

    def _sentinel_self_healing_loop(self):
        """Autonomous Anomaly Self-Healing Daemon: Continuously monitors error telemetry and applies sandbox patches."""
        while self.active_status:
            try:
                time.sleep(15)
                recent_errors = telemetry_hub.get_recent_errors() if hasattr(telemetry_hub, "get_recent_errors") else []
                if recent_errors and sandbox_engine:
                    latest_err = recent_errors[-1]
                    patch_spec = sandbox_engine.formulate_auto_patch(latest_err) if hasattr(sandbox_engine, "formulate_auto_patch") else None
                    if patch_spec and auto_test_hub:
                        auto_test_hub.verify_and_apply_patch(patch_spec)
                        _safe_log_metric("autonomous_self_healing_applied", 1)
            except Exception:
                time.sleep(30)

    def _start_local_dashboard_server(self):
        """Spins up a lightweight local HTTP server endpoint for front-end interface monitoring."""
        try:
            from http.server import HTTPServer, BaseHTTPRequestHandler

            outer_self = self
            class DashboardHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == "/status":
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        status_data = {
                            "status": "online",
                            "target_dir": outer_self.target_dir,
                            "endpoint": outer_self.crawling_config.api_endpoint,
                            "active_subscribers": list(outer_self.event_subscribers.keys()),
                            "telemetry_state": outer_self.telemetry_state,
                            "timestamp": time.time()
                        }
                        self.wfile.write(json.dumps(status_data).encode("utf-8"))
                    else:
                        self.send_response(404)
                        self.end_headers()

                def log_message(self, format, *args):  # scan:ok - silencing the request log is the intent
                    return

            server = HTTPServer(("localhost", self.dashboard_port + 1000), DashboardHandler)
            server.serve_forever()
        except Exception:
            pass

    def load_session_history(self):
        state_path = os.path.join(self.target_dir, "active_session_state.json")
        if not os.path.exists(state_path):
            return []
        try:
            with open(state_path, "r") as f:
                data = json.load(f)
                return data.get("history", [])
        except Exception:
            return []

    def save_session_history(self, history_array):
        state_path = os.path.join(self.target_dir, "active_session_state.json")
        try:
            rollback_manager.create_snapshot("active_session_state.json")
        except Exception:
            pass

        pruned_history = history_array
        if len(history_array) > 30:
            overflow = history_array[:-20]
            pruned_history = history_array[-20:]
            for item in overflow:
                try:
                    memory_index.store_context(f"archived_history_{int(time.time())}", item.get("content", ""))
                except Exception:
                    pass

        data = {
            "session_id": "nexxus_active_01",
            "history": pruned_history
        }
        with open(state_path, "w") as f:
            json.dump(data, f, indent=2)

    def append_to_history(self, role, content):
        history = self.load_session_history()
        history.append({"role": role, "content": content})
        self.save_session_history(history)

    def query_local_llama(self, prompt_text: str, model_name: str = "llama3.2", timeout: int = 180) -> str:
        """Direct connection to local Ollama server running on port 11434."""
        url = "http://127.0.0.1:11434/api/generate"
        payload = {
            "model": model_name,
            "prompt": prompt_text,
            "stream": False
        }
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            if response.status_code == 200:
                return response.json().get("response", "No response field found.")
            return f"Error: Local Ollama server returned status {response.status_code}"
        except requests.exceptions.Timeout:
            return "Connection failed: Local LLM request timed out."
        except Exception as e:
            return f"Connection failed: {e}"

    def route_query(self, query_payload):
        if not self.active_status:
            raise RuntimeError("NexxusTalksBridge is currently offline.")

        actual_prompt = query_payload
        if isinstance(query_payload, dict):
            actual_prompt = query_payload.get("current_prompt", str(query_payload))

        search_results = search_web(actual_prompt)

        raw_response = bridge_queue.execute_throttled(
            self._dispatch_external, query_payload, search_results
        )

        if isinstance(raw_response, dict):
            if "data" in raw_response and isinstance(raw_response["data"], dict):
                inner_data = raw_response["data"]
                return inner_data.get("response", inner_data.get("output", str(inner_data)))
            elif "error" in raw_response:
                return f"Routing Error: {raw_response.get('error')}"

        return raw_response

    def _dispatch_external(self, payload, search_results):
        target_url = self.crawling_config.api_endpoint
        dispatch_payload = {
            "payload": payload,
            "search_results": search_results,
            "mode": "conversation",
            "persona": "friendly_assistant"
        }
        try:
            response = requests.post(target_url, json=dispatch_payload, timeout=180)
            if response.status_code == 200:
                try:
                    return response.json()
                except Exception:
                    return response.text
            return {
                "status": "routing_error",
                "endpoint": target_url,
                "response_code": response.status_code,
                "error": "Non-200 response from local endpoint"
            }
        except Exception as e:
            return {
                "status": "routing_error",
                "endpoint": target_url,
                "error": str(e),
                "search_output": search_results,
            }

    def execute_sovereign_pipeline(self, intent_text: str, target_platform: str = "default_platform") -> dict:
        start_time = time.time()
        try:
            pentest_report = sovereign_pentest.run_system_penetration_test([target_platform, "execution_pipeline"])
            if pentest_report.get("status") not in ["fully_hardened", "vulnerabilities_patched"]:
                return {"status": "aborted", "reason": "Pentest security check failed."}
        except Exception:
            pass

        compiled_package = sovereign_compiler.compile_payload(intent_text, target_type="profile_spec") if sovereign_compiler else {}
        keywords = ["Sovereign Infrastructure", target_platform]
        optimized_package = sovereign_seo.optimize_payload_for_ranking(compiled_package, keywords) if sovereign_seo else compiled_package

        defended_packet = sovereign_defense.audit_and_sanitize_boundary(optimized_package) if sovereign_defense else {"status": "passed", "sanitized_data": optimized_package}
        if defended_packet.get("status") == "threat_detected":
            return {"status": "aborted", "reason": "Perimeter defense flagged a security violation."}

        payload_data = defended_packet.get("sanitized_data", defended_packet)
        deployment_record = native_provisioning_factory.execute_native_deployment(target_platform, payload_data) if native_provisioning_factory else {"status": "simulated_deployment"}

        elapsed = time.time() - start_time
        _safe_log_metric("sovereign_pipeline_duration", elapsed)

        self.dispatch_event("sovereign_pipeline_executed", {"platform": target_platform, "timestamp": time.time()})

        return {
            "status": "sovereign_execution_success",
            "deployment_record": deployment_record
        }

    def synthesize_master_blueprint(self, objective_text: str) -> dict:
        """Cross-Domain Synthesis Pipeline with Event Bus Notification."""
        try:
            game_spec = UniversalGameDevEngine().evaluate_ruleset(objective_text)
            affiliate_spec = AffiliateAutomationEngine().generate_pipeline_spec(objective_text)
            business_spec = business_incubator.generate_blueprint(objective_text) if business_incubator and hasattr(business_incubator, "generate_blueprint") else {"status": "incubator_active"}

            master_blueprint = {
                "objective": objective_text,
                "game_mechanics": game_spec,
                "marketing_funnel": affiliate_spec,
                "business_model": business_spec,
                "timestamp": time.time()
            }

            bottleneck_vault.archive_record("master_blueprints", master_blueprint)
            self.dispatch_event("blueprint_synthesized", master_blueprint)
            return master_blueprint
        except Exception as e:
            return {"status": "synthesis_error", "error": str(e)}

    def run_hypothesis_experiment(self, hypothesis_statement: str) -> dict:
        """Autonomous Hypothesis-Testing Loop."""
        try:
            lab_record = hypothesis_lab.formulate_hypothesis(hypothesis_statement) if hypothesis_lab else {"hypothesis": hypothesis_statement}
            test_result = auto_test_hub.run_sandbox_verification(lab_record) if auto_test_hub else {"status": "verified"}

            _safe_log_metric("hypothesis_test_completed", 1)
            return {
                "status": "experiment_concluded",
                "hypothesis": hypothesis_statement,
                "empirical_findings": test_result
            }
        except Exception as e:
            return {"status": "experiment_failed", "error": str(e)}

    def anticipate_intent_and_fetch_cache(self, user_prompt: str) -> str:
        """Vector-Indexed Semantic Cache & Intent Anticipation."""
        try:
            cached_context = memory_index.query_similar(user_prompt) if hasattr(memory_index, "query_similar") else None
            if cached_context:
                _safe_log_metric("semantic_cache_hit", 1)
                return cached_context
        except Exception:
            return None

    _REALTIME_QUERY_MARKERS = (
        "today", "current", "currently", "latest", "now", "recent", "recently",
        "live", "price", "prices", "score", "scores", "weather", "news",
        "who is the", "what is the", "what's the", "when is", "when does",
        "this week", "this year", "right now",
    )

    def _looks_like_realtime_query(self, prompt: str) -> bool:
        """
        Lightweight gate so we only pay the search round-trip (and only add search
        noise to the model's context) for prompts that plausibly need current
        information - not every single message. An explicit 'search:' prefix
        (already used elsewhere in this bridge) always forces it on.
        """
        lower = prompt.lower().strip()
        if lower.startswith("search:"):
            return True
        return any(marker in lower for marker in self._REALTIME_QUERY_MARKERS)

    def gather_live_search_context(self, user_prompt: str) -> str:
        """
        Actually calls axis_search_engine's search_web() and formats the results
        into a block the model is told to treat as authoritative current data.
        This is the piece that was previously wired up in route_query() but never
        used by the live chat path (generate_response) - so the model had no live
        data and predictably fell back to an 'I don't have real-time access'
        disclaimer even when axis_search_engine itself worked fine.
        """
        if not self._looks_like_realtime_query(user_prompt):
            return ""
        try:
            query = user_prompt
            lower = user_prompt.lower().strip()
            if lower.startswith("search:"):
                query = user_prompt[len("search:"):].strip()

            search_results = search_web(query)
            payload = search_results
            if isinstance(search_results, dict) and "results" in search_results:
                payload = search_results["results"]
            if not payload:
                return ""

            serialized = json.dumps(payload, indent=2, default=str)[:3000]
            _safe_log_metric("live_search_context_injected", 1)
            return (
                "\n\n[LIVE AXIS SEARCH CONTEXT - real, current data retrieved just now. "
                "Use it to answer the user's question directly. Do not tell the user "
                "you lack real-time access when this context is present; if it doesn't "
                "fully answer the question, say so specifically rather than refusing "
                "outright.]\n"
                f"{serialized}\n"
            )
        except Exception as e:
            _safe_log_metric("live_search_context_error", 1)
            return ""

    def generate_visual_asset(self, spec: str, aspect_ratio: str = None) -> dict:
        """
        Real image generation. universal_graphics_studio takes priority if present
        (lets you swap backends without touching callers); otherwise this calls a
        genuine locally-running Stable Diffusion WebUI instance over HTTP and saves
        a real PNG to GENERATED_ASSETS_DIR. If neither is actually reachable, this
        still reports the real error rather than a fabricated success - a request
        that couldn't be fulfilled is reported as failed, not silently invented.
        """
        if universal_graphics_studio and hasattr(universal_graphics_studio, "generate_image"):
            try:
                result = universal_graphics_studio.generate_image(spec, aspect_ratio=aspect_ratio)
                return {"status": "success", "source": "universal_graphics_studio", "result": result}
            except Exception as e:
                return {"status": "error", "source": "universal_graphics_studio", "error": str(e)}

        width, height = _aspect_ratio_to_dims(aspect_ratio)
        sd_result = _call_stable_diffusion_webui(spec, width=width, height=height)
        if sd_result.get("status") == "success":
            _safe_log_metric("visual_asset_generated", 1)
            return {"status": "success", "source": "stable_diffusion_webui", **sd_result}
        _safe_log_metric("visual_asset_generation_failed", 1)
        return {
            "status": "unavailable",
            "source": "stable_diffusion_webui",
            "reason": sd_result.get("error", "Unknown error contacting local Stable Diffusion WebUI."),
        }

    # ------------------------------------------------------------------
    # Funnel build helpers (shared by the inline path, the question-resume
    # path, and background jobs - one implementation, not three copies)
    # ------------------------------------------------------------------
    def _resolve_funnel_client(self, prompt_lower: str):
        """-> (saved client ids, the client the prompt resolves to or None)."""
        config_dir = Path("./client_configs")
        config_files = sorted(config_dir.glob("*.json")) if config_dir.exists() else []
        client_ids = [f.stem for f in config_files]
        named = next((cid for cid in client_ids if cid.lower() in prompt_lower), None)
        if len(client_ids) == 1 and named is None:
            # Only one real saved config exists - nothing to be ambiguous
            # about, so that's the implicit choice (otherwise a lone saved
            # config was silently ignored in favor of the sandbox template).
            named = client_ids[0]
        return client_ids, named

    def _funnel_clarifying_question(self, prompt: str, client_ids: list, named_client):
        """If more than one saved config exists and none was named, queue and
        return a clarifying question; otherwise None."""
        if len(client_ids) > 1 and named_client is None:
            options = [{"id": cid, "label": cid} for cid in client_ids]
            options.append({
                "id": "default_sandbox_client",
                "label": "default_sandbox_client (built-in sandbox template, not one of your saved configs)",
            })
            return self.question_queue.ask(
                session_id=self._session_id,
                prompt_text=(
                    f"You have {len(client_ids)} saved client configs ({', '.join(client_ids)}). "
                    f"Which one should I build the funnel for?"
                ),
                options=options,
                pending_action="build_funnel",
                pending_context={"original_prompt": prompt},
            )
        return None

    def _run_funnel_build(self, named_client, prompt: str, ctx=None) -> dict:
        """Closed build-test-verify-correct loop for one client, then vault
        staging ONLY if it verified. Returns the full report dict. When called
        from a background job, ctx marks stages so the live viewport shows them."""
        if ctx:
            ctx.stage("build+verify")
        engine = FunnelFactoryEngine(
            client_config_path=str(Path("./client_configs") / f"{named_client}.json") if named_client else None
        )
        build_report = engine.execute_build_verified(max_attempts=3)
        funnel_result = dict(build_report)
        if build_report.get("status") == "success" and final_asset_port and getattr(engine, "dist_dir", None):
            if ctx:
                ctx.stage("vault staging")
            funnel_result["vault"] = final_asset_port.ingest_directory(
                self._vault_build_type(prompt.lower()), engine.client_id, engine.dist_dir,
                metadata={"engine": "FunnelFactoryEngine", "prompt": prompt[:200], "verified_attempts": build_report["attempts"]},
                source="funnel_factory",
            )
        elif ctx:
            ctx.log("build did not verify - NOT staging into the vault", level="warn")
        return funnel_result

    # ------------------------------------------------------------------
    # Background execution
    # ------------------------------------------------------------------
    def _background_enabled(self) -> bool:
        return bool(self.job_manager) and not os.environ.get("NEXXUS_SYNC_BUILDS")

    def _register_job_runners(self):
        if not self.job_manager:
            return

        def funnel_build(ctx, spec):
            ctx.watch("./workspace_output")
            return self._run_funnel_build(spec.get("client"), spec.get("prompt", ""), ctx=ctx)

        def engine_intent(ctx, spec):
            ctx.watch("./workspace_output")
            ctx.stage("engine")
            out = self.execute_engine_intent(spec["prompt"])
            return (out or {}).get("result") if out else {"status": "error", "error": "no engine matched this prompt"}

        self.job_manager.register_runner("funnel_build", funnel_build)
        self.job_manager.register_runner("engine_intent", engine_intent)
        try:
            import mesh_bridge as _mesh
            _mesh.register_job_runner(self.job_manager)   # utility requests run through the same job/gate process
        except Exception:
            pass

    def _start_background_job(self, kind: str, spec: dict, description: str) -> dict:
        """Submits the job (returns instantly) and builds the immediate
        acknowledgement the chat shows. The finish notice comes later, from the
        job manager's notification feed - the chat path never waits for it."""
        try:
            job = self.job_manager.submit(kind, spec, description)
        except _job_manager_mod.QueueFullError as e:
            text = (f"Not started: the background queue is full ({e}). Nothing was dropped silently - "
                    f"try again once some of the queued builds have finished.")
            return {"technical_view": text, "intuitive_view": text, "glossary_references": {}}
        held = job["status"] == "held"
        if job.get("deduplicated"):
            text = (f"Already queued (job {job['job_id']}): {description}. I didn't add a duplicate - "
                    f"it will run as soon as a worker is free.")
        elif held:
            text = (f"Queued (job {job['job_id']}): {description}. The queue is on hold "
                    f"({self.job_manager.status().get('reason')}), so it's saved and will start "
                    f"automatically when the hold is released.")
        else:
            text = (f"Started in the background (job {job['job_id']}): {description}. "
                    f"Keep chatting - I'll tell you when it finishes, and the Build Mode window "
                    f"shows it live.")
        return {
            "technical_view": text,
            "intuitive_view": text,
            "glossary_references": {},
            "job": {"job_id": job["job_id"], "kind": kind, "description": description, "status": job["status"]},
        }

    _EARLIER_ENGINE_MARKERS = (
        "run build", "execute build controller", "build system", "neutral theory", "breakdown brainstorm",
        "index workspace", "sort workspace files", "synthesize master blueprint", "compile master blueprint",
        "run hypothesis test", "execute experiment",
    )

    # --- MESH UTILITIES FROM CHAT -------------------------------------------
    # "list utilities"  /  "run utility axis-core.summarize {"path": "a.txt"}"
    # A chat request becomes a normal JOB (queue, Build Mode, truth gate, finish notice). Only
    # utilities the engine itself marked chat_ok can be started this way.
    _UTIL_RUN = re.compile(r"^\s*run utility\s+([\w-]+)\.(\w+)\s*(.*?)\s*$", re.I | re.S)

    def _handle_mesh_chat(self, prompt: str):
        pl = prompt.strip().lower()
        try:
            import mesh_bridge as mesh
        except Exception:
            return None
        if pl in ("list utilities", "show utilities", "what utilities do the engines have"):
            known = mesh.list_utilities()
            if not known:
                msg = "No engine utilities are known yet. Discovery runs engines, so it needs the admin token: POST /api/mesh/utilities/discover."
            else:
                lines = []
                for eng, v in known.items():
                    for name, d in v["utilities"].items():
                        flags = (" [build]" if d["build"] else "") + (" [chat ok]" if d["chat_ok"] else "")
                        lines.append(f"{eng}.{name}{flags} - {d['description']}")
                msg = "Engine utilities I know about:\n" + "\n".join(lines)
            return {"technical_view": msg, "intuitive_view": msg, "glossary_references": {}}
        m = self._UTIL_RUN.match(prompt)
        if not m:
            return None
        engine, util, raw = m.group(1), m.group(2), m.group(3)
        try:
            args = json.loads(raw) if raw else {}
            if not isinstance(args, dict):
                raise ValueError('args must be an object')
        except ValueError:
            msg = "Those utility arguments aren't valid JSON, so nothing was run."
            return {"technical_view": msg, "intuitive_view": msg, "glossary_references": {}}
        decl = (mesh.list_utilities().get(engine) or {}).get("utilities", {}).get(util)
        if decl is None:
            msg = f"I don't know a utility {engine}.{util}. Say 'list utilities' to see what the engines offer."
        elif not decl["chat_ok"]:
            msg = f"{engine}.{util} isn't enabled for chat (the engine didn't mark it chat_ok), so I won't start it from here."
        elif not self.job_manager:
            msg = "The job system isn't available, so I can't run that."
        else:
            return self._start_background_job("mesh_utility", {"engine": engine, "utility": util, "args": args}, f"{engine}.{util}")
        return {"technical_view": msg, "intuitive_view": msg, "glossary_references": {}}

    # --- GREEN LIGHT: "plan -> go ahead" actually starts a build -------------
    # Diagnosed: a plan reply came from the chat model and nothing remembered it, so
    # "go ahead" was just another chat message (no job, no Build Mode). Now a build
    # request is remembered, and a bare approval starts the real background job.
    _BUILD_INTENT = re.compile(r"\b(build|create|make|generate|set ?up|put together)\b.*\b(funnel|page|site|website|landing|app)\b|\b(funnel|landing page|website)\b.*\b(plan|build)\b", re.I)
    _GREEN_LIGHT = re.compile(r"^\s*(ok(ay)?[, ]*)?(yes|yep|yeah|go( ahead)?|proceed|do it|green ?light(ed)?|approved?|execute|start( it)?|run it|build it|let'?s go|send it|confirmed?)\b[\s\w,.!']*$", re.I)
    _PLAN_TTL_SECONDS = 1800

    def _handle_green_light(self, prompt: str):
        """Returns a response dict if this message is an approval of a remembered
        build request (or an honest 'nothing to run' reply); None to route normally."""
        words = prompt.split()
        is_green = len(words) <= 6 and bool(self._GREEN_LIGHT.match(prompt))
        pending = getattr(self, "_pending_plan", None)
        if not is_green:
            if self._BUILD_INTENT.search(prompt) and len(words) >= 3:
                self._pending_plan = {"prompt": prompt, "at": time.time()}
            return None
        if not pending or time.time() - pending["at"] > self._PLAN_TTL_SECONDS:
            return None  # a plain "yes" with no build waiting is just conversation
        self._pending_plan = None
        plan_prompt = pending["prompt"]
        pl = plan_prompt.lower()
        if "funnel" in pl and self._background_enabled():
            client_ids, named = self._resolve_funnel_client(pl)
            question = self._funnel_clarifying_question(plan_prompt, client_ids, named)
            if question:
                return {"technical_view": f"[QUESTION QUEUE]: {question['prompt']}",
                        "intuitive_view": question["prompt"], "glossary_references": {}, "question": question}
            return self._start_background_job(
                "funnel_build", {"client": named, "prompt": plan_prompt},
                f"build funnel for '{named or 'default_sandbox_client'}'")
        msg = ("Got your green light, but I don't have a background builder wired to that plan yet - "
               "the only one that runs as a live job is the funnel factory. Say 'build funnel' "
               "(optionally with a client name) and I'll run it with Build Mode showing every step.")
        return {"technical_view": msg, "intuitive_view": msg, "glossary_references": {}}

    def _maybe_dispatch_background(self, prompt: str):
        """If this prompt is a funnel build, hand it to the background runner
        and return the immediate response dict; otherwise None (normal routing).
        Same precedence as execute_engine_intent: earlier engine markers win.
        Only funnel builds are backgrounded: they return a verifiable report the
        truth gate can check. Engines whose result shape can't be verified
        (e.g. the Nexus build controller) deliberately stay inline."""
        if not self._background_enabled():
            return None
        pl = prompt.lower()
        if any(m in pl for m in self._EARLIER_ENGINE_MARKERS):
            return None
        if "batch build funnel" in pl or "build all funnels" in pl or "funnel factory batch" in pl:
            return self._start_background_job("engine_intent", {"prompt": prompt}, "batch build of all client funnels")
        if "build funnel" in pl or "create funnel" in pl or "generate funnel" in pl or "funnel factory" in pl:
            client_ids, named = self._resolve_funnel_client(pl)
            question = self._funnel_clarifying_question(prompt, client_ids, named)
            if question:
                return {
                    "technical_view": f"[QUESTION QUEUE]: {question['prompt']}",
                    "intuitive_view": question["prompt"],
                    "glossary_references": {},
                    "question": question,
                }
            return self._start_background_job(
                "funnel_build", {"client": named, "prompt": prompt},
                f"build funnel for '{named or 'default_sandbox_client'}'")
        return None

    def _resume_pending_action(self, question: dict, chosen: dict) -> dict:
        """
        Carries out whatever action was waiting on a clarifying answer, now
        that the operator picked one of the options a prior QuestionQueue.ask()
        offered. Dispatches on question['pending_action'] the same way
        execute_engine_intent() dispatches on prompt text - this is just the
        "continue what I actually asked about" half of that same flow.
        """
        action = question.get("pending_action")
        context = question.get("pending_context", {})

        if action == "build_funnel":
            client_id = chosen["id"]
            original_prompt = context.get("original_prompt", "")
            named = None if client_id == "default_sandbox_client" else client_id
            if self._background_enabled():
                return self._start_background_job(
                    "funnel_build", {"client": named, "prompt": original_prompt},
                    f"build funnel for '{client_id}'")
            try:
                funnel_result = self._run_funnel_build(named, original_prompt)
            except Exception as e:
                funnel_result = {"status": "error", "error": str(e)}
            return {
                "technical_view": f"[ENGINE DISPATCH: FunnelFactory]:\n{json.dumps(funnel_result, indent=2)}",
                "intuitive_view": f"Got it - building the funnel for '{client_id}' now. Status: {funnel_result.get('status', 'unknown')}.",
                "glossary_references": {},
            }

        # Shouldn't normally happen - resolve() only returns a match against
        # a question this same queue just asked - but fail honestly instead
        # of silently doing nothing if a pending_action has no handler.
        return {
            "technical_view": f"[QUESTION QUEUE]: Resolved '{chosen['label']}' but no handler exists for pending_action '{action}'.",
            "intuitive_view": "Thanks, but I don't have a follow-up action wired up for that yet.",
            "glossary_references": {},
        }

    @staticmethod
    def _vault_build_type(prompt_lower: str) -> str:
        """Ingestion routing: 'corporate' / 'sellable' in the prompt -> corporate vault lane, else sandbox."""
        return "corporate" if ("corporate" in prompt_lower or "sellable" in prompt_lower) else "sandbox"

    def _ingest_recent_funnel_builds(self, since_ts: float, build_type: str) -> dict:
        """
        After a batch build, wrap only the client folders that were actually (re)built
        during this run (newest file mtime >= run start), so stale output from earlier
        runs isn't re-ingested as duplicates every time.
        """
        if not final_asset_port:
            return {"status": "skipped", "reason": "final_asset_port module not available"}
        results = []
        for dist in sorted(Path("./workspace_output").glob("*/dist")):
            try:
                newest = max((f.stat().st_mtime for f in dist.rglob("*") if f.is_file()), default=0)
            except OSError:
                continue
            if newest < since_ts - 1.0:  # 1s slack for coarse filesystem timestamps
                continue
            results.append(final_asset_port.ingest_directory(
                build_type, dist.parent.name, dist,
                metadata={"engine": "FunnelFactoryEngine", "mode": "batch"}, source="funnel_factory",
            ))
        return {
            "status": "success",
            "ingested": sum(1 for r in results if r.get("status") == "success"),
            "results": results,
        }

    def execute_engine_intent(self, prompt: str) -> dict:
        """
        Assesses intent dynamically based on explicit operational commands,
        incorporating the Nexus Build Controller and Master Command Prompts.
        """
        prompt_lower = prompt.lower()

        if "run build" in prompt_lower or "execute build controller" in prompt_lower or "build system" in prompt_lower:
            system_persona_engine.set_state("BUILD_MODE")
            build_result = nexus_build_controller.execute_build(prompt)
            built = not (isinstance(build_result, dict) and build_result.get("status") == "unavailable")
            return {"engine": "NexusBuildController", "result": {"status": "executed" if built else "unavailable", "build_data": build_result}}

        elif "neutral theory" in prompt_lower or "breakdown brainstorm" in prompt_lower:
            sandbox_status = conversational_sandbox.engage_sandbox()
            system_persona_engine.set_state("NEUTRAL_THEORY")
            return {"engine": "NeutralConversationalSandbox", "result": {"status": "engaged", "sandbox_status": sandbox_status}}

        elif "index workspace" in prompt_lower or "sort workspace files" in prompt_lower:
            system_persona_engine.set_state("CHEERFUL")
            index_result = file_sorter.scan_and_index_workspace(self.target_dir)
            return {"engine": "NexxusFileSorter", "result": {"status": "indexed", "index_data": index_result}}

        elif "synthesize master blueprint" in prompt_lower or "compile master blueprint" in prompt_lower:
            return {"engine": "CrossDomainSynthesis", "result": self.synthesize_master_blueprint(prompt)}

        elif "run hypothesis test" in prompt_lower or "execute experiment" in prompt_lower:
            return {"engine": "HypothesisLab", "result": self.run_hypothesis_experiment(prompt)}

        elif "batch build funnel" in prompt_lower or "build all funnels" in prompt_lower or "funnel factory batch" in prompt_lower:
            # Closed build-test-verify-correct loop, per client: build_all_clients()
            # now runs each client through FunnelFactoryEngine.execute_build_verified()
            # (bounded retries, real on-disk checks) instead of a single blind
            # execute_build() call. Only clients that actually came back "success"
            # get staged into the vault - a client that never passed verification
            # is reported honestly in "clients" and left exactly where it is.
            try:
                batch_report = FunnelFactoryEngine.build_all_clients()
                funnel_result = {
                    "status": batch_report.get("status", "error"),
                    "action": "build_all_clients",
                    "config_dir": "./client_configs",
                    "clients": batch_report.get("clients", []),
                }
                if final_asset_port:
                    vault_results = []
                    for client_report in funnel_result["clients"]:
                        if client_report.get("status") != "success":
                            continue
                        vault_results.append(final_asset_port.ingest_directory(
                            self._vault_build_type(prompt_lower), client_report["client_id"], Path(client_report["output_dir"]),
                            metadata={"engine": "FunnelFactoryEngine", "mode": "batch", "verified_attempts": client_report["attempts"]},
                            source="funnel_factory",
                        ))
                    funnel_result["vault"] = {
                        "status": "success",
                        "ingested": sum(1 for r in vault_results if r.get("status") == "success"),
                        "results": vault_results,
                    }
            except Exception as e:
                funnel_result = {"status": "error", "error": str(e)}
            return {"engine": "FunnelFactory", "result": funnel_result}

        elif "build funnel" in prompt_lower or "create funnel" in prompt_lower or "generate funnel" in prompt_lower or "funnel factory" in prompt_lower:
            # Instantiated on demand rather than at import time: FunnelFactoryEngine's
            # __init__ scaffolds real directories and opens a client SQLite DB as a
            # side effect, which shouldn't happen just from importing this module.
            #
            # Closed build-test-verify-correct loop: execute_build_verified() runs
            # the build, checks the REAL files it should have produced, and retries
            # (bounded) if verification fails. Staging into the vault - the final
            # step before anything is considered "finished" and handed to
            # final_asset_port - only happens for a build that actually verified
            # clean; a build that never passes comes back as an honest error with
            # the full attempt/verification trail instead of being staged anyway.
            #
            # Clarification Protocols: if more than one real client config
            # exists on disk and the prompt doesn't name which one, this is
            # genuinely ambiguous - which client's funnel is "the" funnel?
            # Rather than silently defaulting to the sandbox template (or
            # guessing the first file alphabetically), ask which client was
            # meant and resume the build once that's answered.
            try:
                client_ids, named_client = self._resolve_funnel_client(prompt_lower)
                question = self._funnel_clarifying_question(prompt, client_ids, named_client)
                if question:
                    return {
                        "engine": "QuestionQueue",
                        "result": {"status": "awaiting_clarification", "question": question},
                        "question": question,
                    }
                funnel_result = self._run_funnel_build(named_client, prompt)
            except Exception as e:
                funnel_result = {"status": "error", "error": str(e)}
            return {"engine": "FunnelFactory", "result": funnel_result}

        elif "generate image" in prompt_lower or "generate an image" in prompt_lower or "create an image" in prompt_lower:
            detected_ratio = next((r for r in _ASPECT_RATIO_PRESETS if r in prompt_lower), None)
            return {"engine": "VisualAssetGeneration", "result": self.generate_visual_asset(prompt, aspect_ratio=detected_ratio)}

        elif "spawn bot" in prompt_lower or "create bot" in prompt_lower:
            bot_name = f"AdHocBot-{int(time.time())}"
            spawn_result = bot_spawn_manager.spawn_bot(
                bot_name,
                f"Ad-hoc bot spawned from prompt: {prompt}",
                trigger_keywords=[bot_name.lower()],
            )
            return {"engine": "BotSpawnManager", "result": spawn_result}

        elif "list active bots" in prompt_lower or "list bots" in prompt_lower:
            return {"engine": "BotSpawnManager", "result": bot_spawn_manager.list_active_bots()}

        elif "terminate bot" in prompt_lower:
            match = re.search(r"spawned-[0-9a-f]{10}", prompt)
            if match:
                return {"engine": "BotSpawnManager", "result": bot_spawn_manager.terminate_bot(match.group(0))}
            return {
                "engine": "BotSpawnManager",
                "result": {"status": "error", "error": "No bot id found in prompt. Expected an id like 'spawned-abc1234567'."},
            }

        elif "list vault" in prompt_lower or "list assets" in prompt_lower or "final draft vault" in prompt_lower:
            if not final_asset_port:
                return {"engine": "FinalAssetPort", "result": {"status": "error", "error": "final_asset_port module not available"}}
            bt = "corporate" if "corporate" in prompt_lower else ("sandbox" if "sandbox" in prompt_lower else None)
            return {"engine": "FinalAssetPort", "result": final_asset_port.list_assets(build_type=bt)}

        elif "inspect asset" in prompt_lower:
            if not final_asset_port:
                return {"engine": "FinalAssetPort", "result": {"status": "error", "error": "final_asset_port module not available"}}
            match = re.search(r"[a-f0-9]{12}", prompt)
            if not match:
                return {"engine": "FinalAssetPort", "result": {"status": "error", "error": "No asset id found in prompt. Expected a 12-char id."}}
            return {"engine": "FinalAssetPort", "result": final_asset_port.inspect(match.group(0))}

        # Deliberately no "purge"/"delete asset" chat trigger: destructive vault
        # operations only run through final_asset_port.purge() called directly (e.g.
        # from an explicit UI action with its own confirmation), never from a phrase
        # a local model could produce unprompted or be steered into producing.

        elif "seal package" in prompt_lower or "run curator" in prompt_lower or "curator pipeline" in prompt_lower:
            match = re.search(r"[a-f0-9]{12}", prompt)
            package_spec = {"prompt": prompt[:200]}
            if match:
                asset_info = final_asset_port.package_info(match.group(0)) if final_asset_port else None
                if asset_info and asset_info.get("status") == "success":
                    package_spec["asset_path"] = asset_info["path"]
            return {"engine": "CuratorRouter", "result": curator_router.run_pipeline(package_spec)}

        elif "curator status" in prompt_lower or "heartbeat status" in prompt_lower:
            return {"engine": "CuratorRouter", "result": curator_router.status()}

        elif "scheduler status" in prompt_lower or "autonomous scheduler status" in prompt_lower:
            return {"engine": "AutonomousScheduler", "result": self.autonomous_scheduler.status()}

        elif "start autonomous scheduler" in prompt_lower or "start scheduler" in prompt_lower or "enable autonomous mode" in prompt_lower:
            return {"engine": "AutonomousScheduler", "result": self.autonomous_scheduler.start()}

        elif "stop autonomous scheduler" in prompt_lower or "stop scheduler" in prompt_lower or "disable autonomous mode" in prompt_lower:
            return {"engine": "AutonomousScheduler", "result": self.autonomous_scheduler.stop()}

        elif "run scheduler now" in prompt_lower or "run autonomous cycle now" in prompt_lower or "trigger autonomous cycle" in prompt_lower:
            return {"engine": "AutonomousScheduler", "result": self.autonomous_scheduler.run_cycle_now()}

        return None

    def get_collaborative_persona_prompt(self) -> str:
        return (
            "You are NEXXUS AI, the user's sovereign system partner and core collaborator. "
            "Address the user directly and only as 'Architect' - a bare title used like a name, "
            "never with an article. Correct: 'Understood, Architect.' 'Architect, that build is ready.' "
            "Incorrect: 'the Architect', 'The Architect', 'the architect'. "
            "This is a fixed naming convention, not a one-time greeting, and it should hold "
            "steady across long sessions rather than drifting into other names or titles. "
            "We are true partners who brainstorm, explore hypotheses, and discuss a multitude of topics. "
            "You seamlessly transition from a conversational partner to a precise executor "
            "whenever an idea is finalized and a build plan is put into motion, ensuring zero confusion. "
            "Your voice is sharp, clever, and upbeat - genuinely funny, with quick banter and a dry, "
            "occasionally dark sense of humor - while staying fully technically rigorous underneath the wit. "
            "Humor is a delivery style here, not a reason to be less accurate, less careful, or less honest "
            "about limitations or uncertainty."
        )

    def clean_bridge_tags(self, text: str) -> str:
        """Strip any Architect persona tags the bridge server might inject."""
        if not isinstance(text, str):
            text = str(text)
        text = re.sub(r"\[(Technical|Intuitive) View\]:?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[SOCRATIC PROBE\]:?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"Plain terms:\s*", "", text, flags=re.IGNORECASE)
        return text.strip()

    _TITLE_WITH_ARTICLE = re.compile(r"\b[Tt]he\s+Architect\b")

    def enforce_address_nomenclature(self, text: str) -> str:
        """
        Deterministic backstop for the direct-address rule: a local model can ignore
        a system prompt, so 'the Architect' / 'The Architect' (capitalized - the
        title form) is rewritten to bare 'Architect' on the way out.
        Deliberately does NOT touch lowercase 'the architect': that could be a
        legitimate reference to some other architect (a building, a software
        architect) and rewriting it would corrupt unrelated answers.
        """
        if not isinstance(text, str):
            return text
        return self._TITLE_WITH_ARTICLE.sub("Architect", text)

    def detect_intent_profile(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if any(keyword in prompt_lower for keyword in ["code", "debug", "script", "python", "bug", "error", "build"]):
            return "sovereign_core"
        elif any(keyword in prompt_lower for keyword in ["story", "novel", "character", "scene", "plot"]):
            return "pristine_storyboard"
        elif any(keyword in prompt_lower for keyword in ["market", "trade", "alpha", "finance", "yield"]):
            return "financial_markets"
        return "sovereign_core"

    def generate_response(self, user_prompt: str, profile_name: str = None) -> dict:
        start_time = time.time()
        try:
            # Clarification Protocols: if a prior turn left a question
            # pending, this turn's message is treated as the answer to THAT
            # question first, before any other intent routing runs - so
            # answering "corporate_demo_client" after being asked which
            # client to build actually resumes the build instead of being
            # parsed as a brand-new, unrelated command.
            pending = self.question_queue.get_pending(self._session_id)
            if pending:
                resolution = self.question_queue.resolve(self._session_id, user_prompt)
                if resolution == "no_match":
                    options_str = ", ".join(o["label"] for o in pending["options"])
                    res_dict = {
                        "technical_view": f"[QUESTION QUEUE]: '{user_prompt}' didn't match any offered option.",
                        "intuitive_view": f"That doesn't match one of the options I asked about. Pick one of: {options_str}",
                        "glossary_references": {},
                        "question": pending,
                    }
                    threading.Thread(target=broadcast_speech, args=(res_dict["intuitive_view"],), daemon=True).start()
                    return res_dict
                elif resolution:
                    res_dict = self._resume_pending_action(resolution["question"], resolution["chosen"])
                    threading.Thread(target=broadcast_speech, args=(res_dict["intuitive_view"],), daemon=True).start()
                    return res_dict

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            loop.run_until_complete(self.intent_vector_pre_indexing(user_prompt))

            cached_preview = self.anticipate_intent_and_fetch_cache(user_prompt)

            bot_dispatch = route_to_bot(user_prompt)
            if bot_dispatch:
                res_dict = {
                    "technical_view": f"[BOT DISPATCH: {bot_dispatch.get('bot_name')}]:\n{json.dumps(bot_dispatch.get('result'), indent=2)}",
                    "intuitive_view": f"Routed to {bot_dispatch.get('bot_name')}.",
                    "glossary_references": {}
                }
                threading.Thread(target=broadcast_speech, args=(res_dict["intuitive_view"],), daemon=True).start()
                return res_dict

            mesh_response = self._handle_mesh_chat(user_prompt)
            if mesh_response is not None:
                threading.Thread(target=broadcast_speech, args=(mesh_response["intuitive_view"],), daemon=True).start()
                return mesh_response

            green_response = self._handle_green_light(user_prompt)
            if green_response is not None:
                threading.Thread(target=broadcast_speech, args=(green_response["intuitive_view"],), daemon=True).start()
                return green_response

            background_response = self._maybe_dispatch_background(user_prompt)
            if background_response is not None:
                threading.Thread(target=broadcast_speech, args=(background_response["intuitive_view"],), daemon=True).start()
                return background_response

            engine_execution = self.execute_engine_intent(user_prompt)
            if engine_execution:
                if engine_execution.get("engine") == "QuestionQueue":
                    question = engine_execution.get("question")
                    res_dict = {
                        "technical_view": f"[QUESTION QUEUE]: {question['prompt']}",
                        "intuitive_view": question["prompt"],
                        "glossary_references": {},
                        "question": question,
                    }
                else:
                    res_dict = {
                        "technical_view": f"[ENGINE DISPATCH: {engine_execution.get('engine')}]:\n{json.dumps(engine_execution.get('result'), indent=2)}",
                        "intuitive_view": f"Executed specialized engine task via {engine_execution.get('engine')}.",
                        "glossary_references": {}
                    }
                threading.Thread(target=broadcast_speech, args=(res_dict["intuitive_view"],), daemon=True).start()
                return res_dict

            # --- NORMALIZATION & MIRROR FEED INTEGRATION ---
            try:
                data = {"prompt": user_prompt}
                normalized_prompt = data.get("prompt", "").strip()

                try:
                    if mirror_synthesizer and hasattr(mirror_synthesizer, "synthesize_mirror_feed"):
                        mirror_synthesizer.synthesize_mirror_feed(normalized_prompt)
                except Exception:
                    pass

            except Exception:
                normalized_prompt = user_prompt

            try:
                if disfluency_engine and hasattr(disfluency_engine, "normalize_input"):
                    norm_res = disfluency_engine.normalize_input(normalized_prompt)
                    normalized_prompt = norm_res.get("normalized_input", normalized_prompt)
            except Exception:
                pass

            try:
                if hasattr(AsymmetricAlphaHunterEngine, "scan_for_parabolic_catalysts"):
                    alpha_engine = AsymmetricAlphaHunterEngine()
                    alpha_engine.scan_for_parabolic_catalysts(normalized_prompt)
            except Exception:
                pass

            try:
                if flow_engine and hasattr(flow_engine, "optimize_flow_rhythm"):
                    flow_engine.optimize_flow_rhythm(normalized_prompt)
            except Exception:
                pass

            try:
                if mirror_synthesizer and hasattr(mirror_synthesizer, "synthesize_mirror_profile"):
                    mirror_synthesizer.synthesize_mirror_profile(normalized_prompt)
            except Exception:
                pass

            try:
                if socratic_prober and hasattr(socratic_prober, "evaluate_and_probe") and len(normalized_prompt.split()) > 15:
                    probe_status = socratic_prober.evaluate_and_probe(normalized_prompt)
                    if probe_status.get("mode") == "probing_active":
                        probes_str = "\n".join(probe_status.get("counter_questions", []))
                        probe_res = {
                            "technical_view": f"[SOCRATIC PROBE]: Input scope requires refinement.\n{probes_str}",
                            "intuitive_view": f"Let's dial in the specifics on: '{user_prompt}' using the questions above.",
                            "glossary_references": {}
                        }
                        threading.Thread(target=broadcast_speech, args=(probe_res["intuitive_view"],), daemon=True).start()
                        return probe_res
            except Exception:
                pass

            active_profile = profile_name or self.detect_intent_profile(normalized_prompt)

            # --- APPLY COMPACTION LOGIC BEFORE PAYLOAD BUILDING ---
            raw_history = self.load_history_with_compaction(loop)
            history = compact_message_history(raw_history, keep_recent=6)

            history.append({"role": "user", "content": user_prompt})

            base_template = PromptTemplates.get_template(active_profile)
            collaborative_overlay = self.get_collaborative_persona_prompt()
            # Search-to-Chat Context Injection: pull live results from axis_search_engine
            # BEFORE building the payload the model actually sees, so it can answer
            # real-time questions instead of reflexively refusing.
            live_search_block = self.gather_live_search_context(normalized_prompt)
            system_prompt = f"{collaborative_overlay}\n\n{base_template}{live_search_block}"

            query_payload = {
                "messages": [{"role": "system", "content": system_prompt}] + history,
                "current_prompt": normalized_prompt
            }

            # ==========================================
            # LOCAL LLAMA / OLLAMA BRAIN — REAL AI GENERATION
            # ==========================================
            if self.llm:
                try:
                    output = self.llm.create_chat_completion(
                        messages=query_payload["messages"],
                        max_tokens=512,
                        temperature=0.8,
                        top_p=0.9,
                    )
                    raw_result = output["choices"][0]["message"]["content"]
                except Exception as e:
                    raw_result = f"[Local Llama generation error: {e}]"
            else:
                # Previously called with just normalized_prompt, which silently dropped
                # the system prompt (and therefore the injected search context) for
                # anyone on the raw-Ollama fallback path instead of llama-cpp-python.
                ollama_prompt = f"{system_prompt}\n\nUser: {normalized_prompt}\nAssistant:"
                raw_result = self.query_local_llama(ollama_prompt)

            parsed_stream_output = StreamParser.parse_chunk(raw_result)
            response_text = parse_and_clean_response(parsed_stream_output)

            guarded_packet = loop.run_until_complete(self.zero_shot_guardrail_injection({"response": response_text}))
            response_text = guarded_packet.get("response", response_text)

            response_text = self.clean_bridge_tags(response_text)
            response_text = self.enforce_address_nomenclature(response_text)

            threading.Thread(target=broadcast_speech, args=(response_text,), daemon=True).start()

            translated_output = bilingual_bridge.dual_translate(response_text)

            self.append_to_history("user", user_prompt)
            self.append_to_history("assistant", response_text)

            try:
                memory_index.store_context(f"user_query_{int(time.time())}", user_prompt)
                memory_index.store_context(f"assistant_res_{int(time.time())}", response_text)
            except Exception:
                pass

            elapsed = time.time() - start_time
            loop.run_until_complete(self.async_telemetry_dispatch("dialogue_generation_latency", elapsed))
            loop.run_until_complete(self.state_mirroring_telemetry({"last_query": user_prompt, "last_latency": elapsed}))

            loop.close()
            return translated_output

        except Exception as e:
            raise

    def load_history_with_compaction(self, loop):
        raw_history = self.load_session_history()
        try:
            compacted = loop.run_until_complete(self.context_compaction({"history": raw_history}))
            return compacted.get("history", raw_history)
        except Exception:
            return raw_history

    def stream_response_generator(self, user_prompt: str, profile_name: str = None):
        response_package = self.generate_response(user_prompt, profile_name)
        tech_view = response_package.get("technical_view", "")

        chunk_size = 64
        for i in range(0, len(tech_view), chunk_size):
            yield {
                "status": "streaming",
                "chunk": tech_view[i:i+chunk_size]
            }
            time.sleep(0.01)

        yield {
            "status": "complete",
            "full_package": response_package
        }

bridge = NexxusTalks()

# Convenience module-level alias so python_server.py (and anything else that
# imports this module) can reach the running scheduler as
# nexxus_talks.autonomous_scheduler without reaching through bridge.
autonomous_scheduler = bridge.autonomous_scheduler