"""orchestrator.py - axis-video_creator's orchestrator: takes build orders from NEXXUS over the orchestrator bus.

Order spec it understands (anything else is refused, the order stays unbuilt and the error is reported):
    {"kind": "storyboard", "script": "<narration text>", "title": "<optional>", "wpm": 150}
It turns the narration into a timed storyboard (one scene per sentence, duration from the word count at `wpm`, at least 1.5 s) and writes
builds/<order id>/storyboard.json. NEXXUS hashes that file itself; an independent QC engine re-derives the scene count from the script.

Run:  python orchestrator.py --once      (one round: acknowledge, build)
      python orchestrator.py --serve     (keep listening)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from nexxus_link import client  # noqa: E402
from root_tools.lib import crypto  # noqa: E402

MIN_SCENE_SECONDS = 1.5


def split_sentences(text):
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", str(text or "").strip()) if p.strip()]


def make_storyboard(script, title="", wpm=150):
    if int(wpm) <= 0:
        raise ValueError("wpm must be positive")
    scenes, t = [], 0.0
    for i, sentence in enumerate(split_sentences(script), 1):
        words = len(sentence.split())
        dur = round(max(MIN_SCENE_SECONDS, words / float(wpm) * 60.0), 2)
        scenes.append({"n": i, "text": sentence, "words": words, "start_s": round(t, 2), "duration_s": dur})
        t += dur
    if not scenes:
        raise ValueError("the script has no sentences")
    return {"title": title, "wpm": int(wpm), "scenes": scenes, "total_s": round(t, 2), "script_hash": crypto.generate_hash(script)}


def build(order):
    """-> path of the artifact. Raises (and so reports nothing as built) for an order it cannot do."""
    spec = order.get("spec") or {}
    if spec.get("kind") != "storyboard":
        raise ValueError("axis-video_creator can only build kind 'storyboard' right now (got %r)" % spec.get("kind"))
    board = make_storyboard(spec.get("script"), spec.get("title", ""), spec.get("wpm", 150))
    out = os.path.join(HERE, "builds", order["id"])
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "storyboard.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(board, f, indent=2)
    return path


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
    import orchestrator_worker
    link = client()
    if "--serve" in sys.argv:
        orchestrator_worker.serve(link, build=build)
    else:
        for d in orchestrator_worker.run_once(link, build=build):
            print(d["action"], d["order"], d["result"].get("status"), d["result"].get("message", ""))
