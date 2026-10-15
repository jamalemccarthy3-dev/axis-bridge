"""test_voice.py - checks for voice.py. Writes .wav files to a temp folder, so no speaker is needed. Run: python test_voice.py"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import voice  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("[PASS] %s" % name)
    else:
        failed += 1
        print("[FAIL] %s %s" % (name, detail))


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


modes = voice.list_modes()
check("all 12 modes in the bank are found", len(modes) == 12, modes)
check("every mode loads with a legal rate and volume", all(-10 <= voice.load_mode(m)["rate"] <= 10 and 0 <= voice.load_mode(m)["volume"] <= 100 for m in modes))
check("both JSON layouts work (bpm style and pacing style)", voice.load_mode("rap")["bpm"] == 95 and voice.load_mode("corporate")["bpm"] == 80)
check("rap is faster than poetry", voice.load_mode("rap")["rate"] > voice.load_mode("poetry")["rate"])
check("theatrical pauses longer than rap", voice.load_mode("theatrical")["pause_ms"] > voice.load_mode("rap")["pause_ms"])
check("unknown mode is refused with the list", raises(lambda: voice.load_mode("nope")))
check("path tricks in a mode name are neutralised", raises(lambda: voice.load_mode("../../master_config")))
check("sentences split on . ! ? and newlines", voice.split_sentences("One. Two! Three?\nFour") == ["One.", "Two!", "Three?", "Four"])

sp, notes = voice.render_template("commercial", "Fresh ideas. Free forever.")
check("template: the filled line is spoken, the direction lines are only notes", sp == ["Fresh ideas.", "Free forever."] and len(notes) == 2, (sp, notes))
sp, _ = voice.render_template("quotes", "Build it yourself.")
check("template: [PAUSE] becomes a long beat", "<<PAUSE>>" in sp and sp[0] == "Build it yourself.")
check("conversation template is refused (it is a protocol, not a script)", raises(lambda: voice.render_template("conversation", "x")))
check("empty text is refused", raises(lambda: voice.plan("   ", "rap")))
check("dry run speaks nothing and returns the plan", voice.speak("Hello there.", "rap", dry_run=True)["plan"]["mode"]["name"] == "rap")

if os.name == "nt":
    d = tempfile.mkdtemp(prefix="omni_voice_")
    text = "This is a test of the Omni voice. It should take a few seconds to say."
    sizes = {}
    for m in ("rap", "poetry"):
        out = os.path.join(d, m + ".wav")
        r = voice.speak(text, m, wav=out)
        check("%s: a real .wav file is written" % m, r["ok"] and os.path.getsize(out) > 5000 and open(out, "rb").read(4) == b"RIFF", r["error"])
        sizes[m] = os.path.getsize(out) if os.path.isfile(out) else 0
    check("poetry (slow, long pauses) lasts longer than rap on the same text", sizes["poetry"] > sizes["rap"] * 1.15, sizes)
    nasty = 'Say "this"; $(Remove-Item -Recurse C:\\nope) `whoami` & echo hi | more'
    out = os.path.join(d, "nasty.wav")
    r = voice.speak(nasty, "standard_neutral", wav=out)
    check("quotes, $( ), backticks and pipes in the text are only words", r["ok"] and os.path.getsize(out) > 5000, r["error"])
    out = os.path.join(d, "tpl.wav")
    r = voice.speak("Free for everyone.", "theatrical", template="psa", wav=out)
    check("a template can be spoken to a file", r["ok"] and os.path.getsize(out) > 5000, r["error"])
else:
    print("[SKIP] audio checks need Windows")

print("\n%d/%d passed" % (passed, passed + failed))
sys.exit(0 if not failed else 1)
