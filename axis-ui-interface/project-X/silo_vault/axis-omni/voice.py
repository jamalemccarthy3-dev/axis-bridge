"""voice.py - Omni's voice: speaks text in one of the performance modes in bank/performance_modes, offline and free.

It uses the speech engine that ships with Windows (System.Speech, the same voices as Narrator-era apps). Nothing is downloaded and
nothing leaves the computer. Honest limits:
  * Windows only. On this PC the installed voices are Microsoft David and Zira (US English).
  * A mode changes SPEED, PAUSES, VOLUME and EMPHASIS. It cannot change the accent: 'british', 'spanish' and 'country' sound like
    the installed US voice at that mode's pace. A real accent needs another installed voice (Windows Settings > Speech > Add voices;
    pass its name with voice=...).
  * The five text templates in bank/templates are writing structures. Only the filled-in line (and a [PAUSE] beat) is spoken; the
    direction lines are notes for the writer and are returned in `writer_notes`, never spoken.

Use:  python voice.py --list
      python voice.py --mode rap --text "Fresh ideas, free forever." --wav out.wav
      python voice.py --mode theatrical --template quotes --text "Build it yourself." (speaks aloud)
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODES_DIR = os.path.join(HERE, "bank", "performance_modes")
TEMPLATES_DIR = os.path.join(HERE, "bank", "templates")

_PACING_BPM = {"precise": 80, "moderate": 85, "varied": 80}
_BASE_BPM = 85                                  # the pace at which the voice's default rate (0) sounds natural
_PAUSE_BY_CADENCE = [("dramatic", 700), ("melodic", 400), ("measured", 300), ("drawl", 350), ("fluid", 220),
                     ("syncopated", 120), ("staccato", 110), ("bouncy", 150)]
_LOUD_STRESS = ("aggressive", "enthusiastic", "emotive", "punchline")
_NOT_SPOKEN_TEMPLATES = {"conversation"}        # a protocol description, not something to say aloud


def list_modes():
    return sorted(f[:-5] for f in os.listdir(MODES_DIR) if f.endswith(".json"))


def list_templates():
    return sorted(f[:-4] for f in os.listdir(TEMPLATES_DIR) if f.endswith(".txt") and f[:-4] not in _NOT_SPOKEN_TEMPLATES)


def load_mode(name):
    """-> {name, bpm, rate, volume, pause_ms, emphasize_last, cadence, stress}. Handles both JSON layouts in the bank."""
    path = os.path.join(MODES_DIR, os.path.basename(name) + ".json")
    if not os.path.isfile(path):
        raise ValueError("unknown mode %r. Modes: %s" % (name, ", ".join(list_modes())))
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    bpm = d.get("bpm") or _PACING_BPM.get(str(d.get("pacing", "")).lower(), _BASE_BPM)
    cadence = str(d.get("cadence") or d.get("pacing") or "")
    stress = str(d.get("stress") or d.get("tone") or "")
    rate = max(-10, min(10, int(round((float(bpm) - _BASE_BPM) / 6.0))))
    pause = next((ms for key, ms in _PAUSE_BY_CADENCE if key in cadence.lower()), 200)
    loud = any(k in stress.lower() or k in str(d.get("style", "")).lower() for k in _LOUD_STRESS)
    return {"name": os.path.basename(name), "bpm": float(bpm), "rate": rate, "volume": 100 if loud else 90, "pause_ms": pause,
            "emphasize_last": loud, "cadence": cadence, "stress": stress}


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", str(text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def render_template(template, text):
    """-> (spoken_lines, writer_notes). Fills the template's %s with `text`; speaks that line; [PAUSE] becomes a long beat."""
    if template in _NOT_SPOKEN_TEMPLATES or template not in list_templates():
        raise ValueError("%r is not a speakable template. Templates: %s" % (template, ", ".join(list_templates())))
    with open(os.path.join(TEMPLATES_DIR, template + ".txt"), encoding="utf-8") as f:
        lines = [l.rstrip() for l in f.read().splitlines() if l.strip()]
    spoken, notes = [], []
    for line in lines:
        if "%s" in line:
            spoken += split_sentences(line.split(":", 1)[1].replace("%s", str(text)) if ":" in line else str(text))
        elif line.upper().startswith("[PAUSE]"):
            spoken.append("<<PAUSE>>")
        else:
            notes.append(line)
    return spoken, notes


def plan(text, mode="standard_neutral", template=None, voice=None):
    m = load_mode(mode)
    notes = []
    sentences = split_sentences(text)
    if template:
        sentences, notes = render_template(template, text)
    if not [s for s in sentences if s != "<<PAUSE>>"]:
        raise ValueError("nothing to say")
    return {"mode": m, "sentences": sentences, "writer_notes": notes, "voice": voice, "long_pause_ms": 900}


_PS = r"""
Add-Type -AssemblyName System.Speech
$p = $env:OMNI_PLAN | ConvertFrom-Json
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($p.voice) { try { $s.SelectVoice([string]$p.voice) } catch { } }
$s.Rate = [int]$p.rate
$s.Volume = [int]$p.volume
if ($p.wav) { $s.SetOutputToWaveFile([string]$p.wav) } else { $s.SetOutputToDefaultAudioDevice() }
$b = New-Object System.Speech.Synthesis.PromptBuilder
$items = @($p.sentences)
for ($i = 0; $i -lt $items.Count; $i++) {
    $t = [string]$items[$i]
    if ($t -eq '<<PAUSE>>') { $b.AppendBreak([TimeSpan]::FromMilliseconds([int]$p.long_pause_ms)); continue }
    if ($p.emphasize_last -and $i -eq ($items.Count - 1)) { $b.AppendText($t, [System.Speech.Synthesis.PromptEmphasis]::Strong) } else { $b.AppendText($t) }
    $b.AppendBreak([TimeSpan]::FromMilliseconds([int]$p.pause_ms))
}
$s.Speak($b)
$s.Dispose()
"""


def speak(text, mode="standard_neutral", template=None, voice=None, wav=None, dry_run=False, timeout=120):
    """Speak (or save to a .wav file). The text travels in an environment variable as JSON, never inside the command line,
    so quotes, `$( )` or semicolons in the text are only ever words. -> {ok, plan, wav, error}"""
    p = plan(text, mode, template, voice)
    if dry_run:
        return {"ok": True, "plan": p, "wav": None, "error": None}
    if os.name != "nt":
        return {"ok": False, "plan": p, "wav": None, "error": "the offline voice needs Windows (System.Speech)"}
    payload = {"rate": p["mode"]["rate"], "volume": p["mode"]["volume"], "pause_ms": p["mode"]["pause_ms"], "long_pause_ms": p["long_pause_ms"],
               "emphasize_last": p["mode"]["emphasize_last"], "sentences": p["sentences"], "voice": voice, "wav": os.path.abspath(wav) if wav else None}
    env = dict(os.environ, OMNI_PLAN=json.dumps(payload))
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _PS],
                           env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "plan": p, "wav": None, "error": "%s: %s" % (type(e).__name__, e)}
    ok = r.returncode == 0 and (not wav or (os.path.isfile(wav) and os.path.getsize(wav) > 1000))
    return {"ok": ok, "plan": p, "wav": wav if ok else None, "error": None if ok else (r.stderr.strip()[:300] or "the speech engine produced no audio")}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Omni voice")
    ap.add_argument("--list", action="store_true", help="list modes and templates")
    ap.add_argument("--mode", default="standard_neutral")
    ap.add_argument("--template")
    ap.add_argument("--text")
    ap.add_argument("--voice")
    ap.add_argument("--wav", help="save to this .wav file instead of speaking aloud")
    ap.add_argument("--dry-run", action="store_true", help="show the plan only")
    a = ap.parse_args(argv)
    if a.list:
        print("modes:    " + ", ".join(list_modes()))
        print("templates: " + ", ".join(list_templates()))
        return 0
    if not a.text:
        ap.error("--text is required")
    try:
        res = speak(a.text, a.mode, a.template, a.voice, a.wav, a.dry_run)
    except ValueError as e:
        print("Not spoken: %s" % e)
        return 2
    m = res["plan"]["mode"]
    print("mode %s: rate %+d, volume %d, pause %d ms%s" % (m["name"], m["rate"], m["volume"], m["pause_ms"], ", emphasis on the last line" if m["emphasize_last"] else ""))
    for n in res["plan"]["writer_notes"]:
        print("  (writer note, not spoken) %s" % n)
    if res["error"]:
        print("Failed: %s" % res["error"])
    elif res["wav"]:
        print("Saved %s (%d KB)" % (res["wav"], os.path.getsize(res["wav"]) // 1024))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
