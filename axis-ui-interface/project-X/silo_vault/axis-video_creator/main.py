"""axis-video_creator: makes a short video from a script, entirely on this machine.

    python main.py                                    builds the built-in sample
    python main.py --script "Your narration here."    one sentence = one scene
    python main.py --file script.txt --resolution 720p --environment production --codec auto
    python main.py --inspect <project id>             audits a finished project
    python main.py --order order.json                 a full order: footage, audio, AI script/images, transition ... (see below)
    python main.py --ai-status                        what AI models this machine can run right now

An order file is JSON, e.g.
    {"script": "...", "resolution": "720p", "environment": "production", "codec": "auto", "transition": "crossfade",
     "footage": [{"path": "C:/clips/shop.mp4", "scene": 2, "trim_start_s": 1.5}], "audio": "footage",
     "ai": {"script": true, "images": true, "sentences": 5, "required": false}}
(leave out "script" and give "topic" with ai.script to have a local Ollama model write the narration; environments: draft, staging, production, cinema)

The pipeline: interview -> narrative -> timing -> style -> assets -> blueprint -> CGI render -> sync check -> encode + export (see src/integration_office/master_builder).
Everything it makes goes to the workspace/ folder. h264 .mp4 needs ffmpeg; without it the video is an animated .gif and the result says so."""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import vc_store as store  # noqa: E402

SAMPLE = ("Here is what matters about steel. It resists rust far longer than iron. It can be recycled forever without losing strength. "
          "Choose steel for what you build next.")


def build(script, **opts):
    builder = store.load_module("src/integration_office/master_builder/lib/builder_tool.py")
    return builder.orchestrate_silos(dict(opts, script=script))


def inspect(project_id):
    tool = store.load_module("src/quality_control/inspector/lib/inspector_tool.py")
    audit = tool.run_audit(project_id, True, "verbose")
    audit["validation"] = store.load_module("src/quality_control/inspector/lib/validator_tool.py").evaluate_against_protocol(audit, "standard")
    audit["report"] = store.load_module("src/quality_control/inspector/lib/reporter_tool.py").format_and_dispatch(audit, "markdown")
    return audit


def main(argv=None):
    ap = argparse.ArgumentParser(description="Make a video from a script.")
    ap.add_argument("--script")
    ap.add_argument("--file")
    ap.add_argument("--title")
    ap.add_argument("--resolution", default="360p")
    ap.add_argument("--environment", default="draft", choices=["draft", "staging", "production", "cinema"])
    ap.add_argument("--codec", default="auto", choices=["auto", "h264", "gif"])
    ap.add_argument("--style", default=None)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--project")
    ap.add_argument("--inspect")
    ap.add_argument("--order")
    ap.add_argument("--ai-status", action="store_true")
    a = ap.parse_args(argv)
    if a.ai_status:
        print(json.dumps(store.load_module("silos/asset_generation_library/lib/ai_backends.py").status(), indent=1))
        return 0
    if a.order:
        with open(a.order, encoding="utf-8") as fh:
            res = store.load_module("src/integration_office/master_builder/lib/builder_tool.py").orchestrate_silos(json.load(fh))
        print(json.dumps(res, indent=1))
        return 0 if res["status"] == "build_complete" else 1
    if a.inspect:
        audit = inspect(a.inspect)
        print(json.dumps({"issues": audit["issues"], "validation": audit["validation"], "report": audit["report"]["path"]}, indent=1))
        return 0 if audit["validation"]["status"] == "validated" else 1
    script = open(a.file, encoding="utf-8").read() if a.file else (a.script or SAMPLE)
    res = build(script, title=a.title, resolution=a.resolution, environment=a.environment, codec=a.codec, style=a.style, fps=a.fps, project_id=a.project)
    print(json.dumps(res, indent=1))
    return 0 if res["status"] == "build_complete" else 1


if __name__ == "__main__":
    sys.exit(main())
