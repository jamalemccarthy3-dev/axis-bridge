"""verify_all.py - one command to check that NEXXUS is healthy: python verify_all.py

Runs the axis gate check and the main test suites one after another and prints one green/red line each.
Nothing is changed. Exit code 0 only when everything passed. Each suite has a time limit, so a stuck one shows as a failure.
"""
import re
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PX = ROOT / "axis-ui-interface" / "project-X"
NX = PX / "silo_vault" / "nexxus"
SUITES = [
    ("axis gate (sealed items)", [sys.executable, "-m", "axis_gate", "verify"], PX, 120),
    ("axis gate tests", [sys.executable, "test_axis_gate.py"], PX / "axis_gate", 600),
    ("tool ingestion", [sys.executable, "test_tool_ingest.py"], NX, 300),
    ("tool analyzer", [sys.executable, "test_tool_analyzer.py"], NX, 300),
    ("tool provisioning", [sys.executable, "test_tool_provision.py"], NX, 300),
    ("tool scout", [sys.executable, "test_tool_scout.py"], NX, 300),
    ("tool vault", [sys.executable, "test_tool_vault.py"], NX, 300),
    ("tool sandbox", [sys.executable, "test_tool_sandbox.py"], NX, 300),
    ("offline dashboard", [sys.executable, "test_dashboard_offline.py"], NX, 300),
    ("axis-SandM operational", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-SandM", 300),
    ("axis-video_creator operational", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-video_creator", 300),
    ("axis-video_creator pipeline", [sys.executable, "test_pipeline.py"], PX / "silo_vault" / "axis-video_creator", 900),
    ("axis-video_creator media", [sys.executable, "test_media.py"], PX / "silo_vault" / "axis-video_creator", 900),
    ("axis-diagnostic utilities", [sys.executable, "test_utilities.py"], PX / "silo_vault" / "axis-diagnostic", 200),
    ("axis-link", [sys.executable, "test_link.py"], PX / "silo_vault" / "axis-link", 200),
    ("triad gatekeeper", [sys.executable, "test_gatekeeper.py"], PX / "silo_vault" / "triad-protocol-module-", 200),
    ("axis-integrity layers", [sys.executable, "test_layers.py"], PX / "silo_vault" / "axis-integrity", 300),
    ("axis-logic operations", [sys.executable, "test_operations.py"], PX / "silo_vault" / "axis-logic", 300),
    ("nexxus fallbacks", [sys.executable, "test_fallbacks.py"], PX / "silo_vault" / "nexxus", 200),
    ("nexxus sovereign bits", [sys.executable, "test_sovereign_bits.py"], PX / "silo_vault" / "nexxus", 400),
    ("nexxus build controller", [sys.executable, "test_build_controller.py"], PX / "silo_vault" / "nexxus", 300),
    ("nexxus game dev engine", [sys.executable, "test_game_dev_engine.py"], PX / "silo_vault" / "nexxus", 300),
    ("nexxus scrapy spiders", [sys.executable, "test_spiders.py"], PX / "silo_vault" / "nexxus" / "Nexxus", 400),
    ("axis-curator operational", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-curator", 300),
    ("axis-llm operational", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-llm", 300),
    ("axis-SandM governor", [sys.executable, "test_governor.py"], PX / "silo_vault" / "axis-SandM", 600),
    ("axis-SandM silos", [sys.executable, "test_silos.py"], PX / "silo_vault" / "axis-SandM", 600),
    ("axis-vantage_point sources", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-vantage_point", 120),
    ("build-and-QC loop", [sys.executable, "test_bus_flow.py"], ROOT, 240),
    ("bus through the server", [sys.executable, "test_bus_server.py"], ROOT, 240),
    ("orchestrator bus", [sys.executable, "test_orchestrator_bus.py"], ROOT, 120),
    ("axis-integrity operational", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-integrity", 300),
    ("integrity sentinel", [sys.executable, "test_sentinel.py"], PX / "silo_vault" / "axis-integrity", 300),
    ("integrity witness", [sys.executable, "test_witness.py"], PX / "silo_vault" / "axis-integrity", 300),
    ("core reports to integrity", [sys.executable, "test_bus_audit.py"], ROOT, 600),
    ("axis-validator operational", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-validator", 300),
    ("axis-diagnostic operational", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-diagnostic", 300),
    ("omni protocol", [sys.executable, "test_protocol.py"], PX / "silo_vault" / "axis-omni", 120),
    ("omni voice", [sys.executable, "test_voice.py"], PX / "silo_vault" / "axis-omni", 300),
    ("omni links and access", [sys.executable, "test_links_access.py"], PX / "silo_vault" / "axis-omni", 120),
    ("axis-triage operational", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-triage", 300),
    ("axis-search_engine offline", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-search_engine", 300),
    ("axis-sweep (JavaScript)", [sys.executable, "test_operational.py"], PX / "silo_vault" / "axis-sweep", 300),
    ("engine build mode (pipeline, audit, approval)", [sys.executable, "test_engine_build.py"], PX / "silo_vault" / "nexxus", 600),
    ("engine telemetry and prompt vault", [sys.executable, "test_engine_telemetry.py"], PX / "silo_vault" / "nexxus", 300),
    ("boiler room data and the diagnostic lock", [sys.executable, "test_diagnostics_hub.py"], PX / "silo_vault" / "nexxus", 120),
    ("boiler room through the server", [sys.executable, "test_diagnostics_routes.py"], ROOT, 300),
    ("engine build, telemetry, prompts through the server", [sys.executable, "test_engine_routes.py"], ROOT, 600),
    ("axis link: ledger, translation, queue, hypothesis", [sys.executable, "test_link_hub.py"], PX / "silo_vault" / "nexxus", 120),
    ("axis link through the server (ledger, gate, queue)", [sys.executable, "test_link_routes.py"], ROOT, 300),
    ("perimeter: hard lock, quarantine, breach loop, unlock check", [sys.executable, "test_perimeter.py"], ROOT, 300),
    ("source feed: signing, replay, tamper, license tokens, publisher, client, routes", [sys.executable, "test_feed.py"], ROOT, 300),
    ("phone install: manifest, icons, page tags, served files, no service worker", [sys.executable, "test_pwa.py"], ROOT, 300),
    ("first run: a fresh install passes its own dashboard audit", [sys.executable, "test_first_run.py"], ROOT, 300),
    ("explicit naming, adoption and the read-only commercial watch", [sys.executable, "test_naming_watch.py"], ROOT, 300),
    ("python 2 -> 3 corrections (py2fix)", [sys.executable, "test_py2fix.py"], PX / "silo_vault" / "nexxus", 120),
    ("intake pipeline: inspect, heal, gate, contribute", [sys.executable, "test_intake_pipeline.py"], PX / "silo_vault" / "nexxus", 120),
    ("intake pipeline inside tool staging", [sys.executable, "test_intake_staging.py"], PX / "silo_vault" / "nexxus", 120),
    ("intake pipeline through the server", [sys.executable, "test_intake_routes.py"], ROOT, 300),
    ("dashboard page: drawers and screen restore", [sys.executable, "test_ui_state.py"], ROOT, 120),
    ("portals: Sports, Markets, Logistics, Economics, field search, Add to Hub", [sys.executable, "test_portals.py"], ROOT, 300),
    ("asset pipeline: prompt fidelity, explicit limits, delivery of accepted builds", [sys.executable, "test_asset_pipeline.py"], ROOT, 300),
    ("publishing queue: staging, approval, dry run, daily cap, ledger, token hygiene", [sys.executable, "test_publish_queue.py"], ROOT, 300),
    ("factory: dashboard types, platform generator, environment compiler and physics, micro-company, video maker, lab, routes", [sys.executable, "test_factory.py"], ROOT, 600),
    ("image ingestion, image-to-3D pipeline, send menu (queue, dry run)", [sys.executable, "test_image_ingest.py"], ROOT, 300),
    ("3D staging: image tools, working copies, routes, vault sync, page wiring", [sys.executable, "test_staging.py"], ROOT, 300),
    ("remote access: Tailscale binding, peer lock, heartbeat, live stream, shared command queue, phone layout", [sys.executable, "test_remote.py"], ROOT, 300),
    ("cheat sheet and prompt vault: true to the code, goal matcher, Home / Find toggle", [sys.executable, "test_cheatsheet.py"], ROOT, 300),
    ("opportunity desk: vault, eligibility, gap analysis, sign-off, claims check, packet, routes", [sys.executable, "test_opportunity_desk.py"], ROOT, 300),
    ("gauntlet: concurrency, resilience, red team, fuzz, cascade, flooding, runaway, control paths", [sys.executable, "test_gauntlet.py"], ROOT, 900),
    ("campaign kit: facts-only copy, channel limits, compliant emails, graphics, landing page", [sys.executable, "test_campaign_kit.py"], ROOT, 300),
    ("campaign media: real narration, synthesised music, assembled and decoded mp4", [sys.executable, "test_campaign_media.py"], ROOT, 600),
    ("campaign queue: approval-gated export, nothing posted", [sys.executable, "test_campaign_queue.py"], ROOT, 300),
    ("campaign routes: token, kit, safe files, stage / approve / export, narrated video", [sys.executable, "test_campaign_routes.py"], ROOT, 600),
    ("document factory: proposals, SOW, contracts, invoices, exact money, prompts, routing in nexxus_talks", [sys.executable, "test_document_factory.py"], ROOT, 300),
    ("daemon engine: atomic state, log rotation, supervisor on real processes, health file, standalone daemon", [sys.executable, "test_daemon_engine.py"], ROOT, 600),
    ("adaptation engine (SLAE): real failures to rules, preflight, hash-chained vault, loop, nexxus_talks wiring", [sys.executable, "test_slae.py"], ROOT, 300),
    ("sketch mode, core drive, and the daemon / slae / sketch routes", [sys.executable, "test_sketch_mode.py"], ROOT, 300),
    ("mesh hardening: derived engine keys, honest results, handshakes, strict heartbeats, durable liveness, no localhost", [sys.executable, "test_mesh_hardening.py"], ROOT, 600),
    ("engine entry template: identical to the three snippets, and a copy passes health / message / inbox / signing", [sys.executable, "test_entry_template.py"], PX / "silo_vault" / "nexxus", 300),
    ("engine messages: message / inbox / on_message hook / crashing hook, health from the templates (the A+ item 5 test)", [sys.executable, "test_engine_messages.py"], PX / "silo_vault" / "nexxus", 300),
    ("chat fail-safe: model down gives a plain message, fast, no exception text", [sys.executable, "test_chat_failsafe.py"], ROOT, 300),
    ("engine health is measured; bluetooth explains a missing radio", [sys.executable, "test_engine_health_bt.py"], ROOT, 600),
    ("axis-cloud vault container: drop-in provisioning, verified copies, versions, confinement, integrity", [sys.executable, "test_axis_vault_container.py"], ROOT, 300),
    ("hub chats: domain gate, prompts, output filter, search and data bridge", [sys.executable, "test_portal_chat.py"], ROOT, 300),
    ("home screen courier and the one-domain hub server", [sys.executable, "test_domain_dispatch.py"], ROOT, 300),
    ("axis-core learning and retention (knowledge.py)", [sys.executable, "test_knowledge.py"], PX / "silo_vault" / "axis-core", 120),
    ("axis-core direct bridging for builds (fuse.py)", [sys.executable, "test_fuse.py"], PX / "silo_vault" / "axis-core", 120),
    ("C engines compile and pass", [sys.executable, "test_c_all.py"], ROOT, 900),
    ("axis-logic engines", [sys.executable, "test_logic_engine.py"], PX / "silo_vault" / "axis-logic", 300),
    ("axis-logic health", [sys.executable, "health_report.py"], PX / "silo_vault" / "axis-logic", 300),
    ("axis-logic probability", [sys.executable, "test_probability.py"], PX / "silo_vault" / "axis-logic", 120),
]


def run(name, cmd, cwd, limit):
    t0 = time.time()
    try:
        # the repo root is on PYTHONPATH for every suite, the same way nexxus_env.bat puts it there for the engines (they import nexxus_governance from it)
        env = dict(os.environ, PYTHONPATH=str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=limit, env=env)
    except subprocess.TimeoutExpired:
        return False, "timed out after %d s" % limit, time.time() - t0
    except OSError as e:
        return False, "could not start: %s" % e, time.time() - t0
    out = (r.stdout + "\n" + r.stderr).strip().splitlines()
    m = None
    for line in reversed(out):
        m = re.search(r"(\d+)\s*/\s*(\d+)\s+passed", line) or re.search(r"OK: .*", line)
        if m:
            break
    detail = m.group(0) if m else (out[-1][:90] if out else "no output")
    ok = r.returncode == 0 and (not m or not re.match(r"(\d+)\s*/\s*(\d+)", m.group(0)) or m.group(1) == m.group(2))
    return ok, detail, time.time() - t0


def main():
    bad = 0
    for name, cmd, cwd, limit in SUITES:
        if cmd[1] != "-m" and not (cwd / cmd[1]).exists():
            ok, detail, dt = False, "test file not found", 0.0
        else:
            ok, detail, dt = run(name, cmd, cwd, limit)
        bad += 0 if ok else 1
        print("%s  %-26s %s  (%.0f s)" % ("PASS" if ok else "FAIL", name, detail, dt))
    print("\nALL GREEN" if not bad else "\n%d suite(s) FAILED" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
