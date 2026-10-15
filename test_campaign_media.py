"""test_campaign_media.py - real narration (the Windows voices installed here), a synthesised music bed, and a script-driven assembly into a narrated mp4 that is decoded back and checked. Skipped
where there is no speech engine or ffmpeg. The file is judged by what is in it (video and audio streams, a length inside the format), not by the code that wrote it.
Run: python test_campaign_media.py"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import numpy as np  # noqa: E402
import campaign_kit as CK  # noqa: E402
import campaign_media as CM  # noqa: E402
from test_campaign_kit import PROFILE  # noqa: E402

VOICES = CM.list_voices()
try:
    CM._ffmpeg()
    HAVE_FF = True
except CM.MediaError:
    HAVE_FF = False


class Music(unittest.TestCase):
    def test_the_bed_is_the_right_length_quiet_and_fades(self):
        a = CM.music_bed(6.0, "warm", 3)
        self.assertEqual(len(a), 6 * CM.SR)
        self.assertLessEqual(float(np.max(np.abs(a))), 0.19)
        self.assertGreater(float(np.max(np.abs(a))), 0.05)
        self.assertLess(abs(float(a[0])), 0.01)
        self.assertLess(abs(float(a[-1])), 0.01)
        for mood in ("bright", "calm"):
            self.assertEqual(len(CM.music_bed(2.0, mood)), 2 * CM.SR)
        with self.assertRaises(CM.MediaError):
            CM.music_bed(2.0, "angry")

    def test_the_same_seed_is_the_same_music_and_a_different_seed_is_not(self):
        self.assertTrue(np.array_equal(CM.music_bed(3, "warm", 5), CM.music_bed(3, "warm", 5)))
        self.assertFalse(np.array_equal(CM.music_bed(3, "warm", 5), CM.music_bed(3, "warm", 6)))

    def test_the_cue_is_short_and_bounded(self):
        c = CM.cue()
        self.assertLess(len(c) / CM.SR, 1.0)
        self.assertLessEqual(float(np.max(np.abs(c))), 0.36)


@unittest.skipUnless(VOICES, "no text-to-speech voice is installed")
class Speech(unittest.TestCase):
    def test_a_real_voice_speaks_for_a_plausible_time(self):
        d = tempfile.mkdtemp()
        text = "Fresh bread delivered before eight o'clock every morning."
        for v in VOICES:
            secs = CM.speak(text, os.path.join(d, v["name"].replace(" ", "_") + ".wav"), v["name"])
            self.assertTrue(2.0 < secs < 7.0, (v["name"], secs))
        a, s = CM.read_wav(os.path.join(d, VOICES[0]["name"].replace(" ", "_") + ".wav"))
        self.assertGreater(float(np.max(np.abs(a))), 0.1)                         # there is real sound in it

    def test_bad_input_is_refused(self):
        d = tempfile.mkdtemp()
        for text, voice in (("", None), ("x" * 2001, None), ("hello", "Not A Real Voice"), ("hello'; Remove-Item *", "Not A Real Voice")):
            with self.assertRaises(CM.MediaError):
                CM.speak(text, os.path.join(d, "x.wav"), voice)

    def test_text_with_shell_characters_is_just_text(self):
        d = tempfile.mkdtemp()
        secs = CM.speak("Say \"hello\" & goodbye; $env:USERNAME `whoami`", os.path.join(d, "t.wav"), VOICES[0]["name"])
        self.assertGreater(secs, 1.0)


@unittest.skipUnless(VOICES and HAVE_FF, "needs a speech voice and ffmpeg")
class Commercial(unittest.TestCase):
    def test_a_15_second_commercial_is_assembled_and_decodes_with_video_and_audio(self):
        kit = CK.generate(PROFILE)
        d = tempfile.mkdtemp()
        rep = CM.make_commercial(kit["profile"], kit["video_scripts"]["social_15s"], os.path.join(d, "spot.mp4"), VOICES[0]["name"], "warm", 2)
        self.assertTrue(rep["has_audio"])
        self.assertTrue(8.0 <= rep["seconds"] <= 17.3, rep["seconds"])
        self.assertIn("synthetic voice", rep["disclosure"])
        self.assertIn("not produced here", rep["not_included"])
        pr = CM.probe(rep["path"])
        self.assertTrue(pr["has_video"] and pr["has_audio"] and pr["decoded_ok"])
        self.assertGreater(pr["frames"], 80)
        self.assertGreater(rep["bytes"], 20000)
        self.assertLessEqual(rep["audio_peak"], 0.98)

    def test_a_script_too_long_for_its_format_is_refused_not_squeezed(self):
        kit = CK.generate(PROFILE)
        s = dict(kit["video_scripts"]["social_15s"])
        s["scenes"] = [dict(x, narration="This is a deliberately long sentence that goes on and on and on for far too many words to fit. " * 3) for x in s["scenes"]]
        with self.assertRaises(CM.MediaError) as c:
            CM.make_commercial(kit["profile"], s, os.path.join(tempfile.mkdtemp(), "x.mp4"), VOICES[0]["name"])
        self.assertIn("shorten the script", str(c.exception))


if __name__ == "__main__":
    unittest.main(verbosity=1)
