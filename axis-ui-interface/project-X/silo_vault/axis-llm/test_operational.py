"""test_operational.py - axis-llm's pipeline really runs, offline: sanitise -> vocabulary -> tokens -> vectors -> governor -> checkpoint.
Run: python test_operational.py. Uses a temporary vocabulary, so it leaves data/vocab.json alone."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [ROOT, os.path.join(ROOT, "lib")]

from config.tokenizer_utility_config import TokenizerUtilityConfig  # noqa: E402
from config.vocabulary_mapping_utility_config import VocabularyMappingConfig  # noqa: E402
from tokenizer_utility import tokenizerutilityengine  # noqa: E402
from vocabulary_mapping_utility import VocabularyMapper  # noqa: E402
from embedding_vectorizer_utility import EmbeddingVectorizerEngine  # noqa: E402


class Llm(unittest.TestCase):
    def setUp(self):
        self.vocab = os.path.join(tempfile.mkdtemp(prefix="llm_"), "vocab.json")
        self.tc = TokenizerUtilityConfig()
        self.tc.vocab_path = self.vocab
        self.mc = VocabularyMappingConfig()
        self.mc.vocab_path = self.vocab

    def test_no_engine_points_at_a_placeholder_service(self):
        for c in (TokenizerUtilityConfig(), VocabularyMappingConfig()):
            self.assertFalse(getattr(c, "tokenizer_service_url", None) or getattr(c, "search_service_url", None), "a service URL is set by default")

    def test_encode_decode_round_trip_and_stable_ids(self):
        t = tokenizerutilityengine(self.tc)
        ids = t.encode("The cat sat. The cat!")
        self.assertEqual(t.decode(ids), "the cat sat . the cat !")
        self.assertEqual(ids[0], ids[4])                       # same word, same id
        self.assertEqual(tokenizerutilityengine(self.tc).encode("the cat sat. the cat!"), ids)   # a fresh engine reads the saved vocabulary

    def test_mapper_and_tokenizer_agree_on_ids(self):
        mapped = VocabularyMapper(self.mc).map_and_sanitize("Hello, world")
        self.assertEqual(tokenizerutilityengine(self.tc).encode("hello world"), mapped)

    def test_a_full_vocabulary_gives_unknown_not_a_crash(self):
        self.tc.vocab_size = 5
        ids = tokenizerutilityengine(self.tc).encode("a b c")
        self.assertEqual(ids[-1], 1)

    def test_derived_vectors_are_deterministic_and_say_so(self):
        from config.embedding_vectorizer_utility_config import EmbeddingVectorizerConfig
        c = EmbeddingVectorizerConfig()
        c.embedding_path = os.path.join(tempfile.mkdtemp(), "none.npy")
        v = EmbeddingVectorizerEngine(c)
        a, b = v.vectorize([4, 5, 6]), v.vectorize([4, 5, 6])
        self.assertTrue((a == b).all())
        self.assertEqual((v.source, len(a)), ("derived", 768))
        self.assertFalse((v.vectorize([4]) == v.vectorize([5])).all())

    def test_training_learns_that_words_in_similar_company_are_close(self):
        import numpy as np
        import train_embeddings as te
        corpus_dir = tempfile.mkdtemp(prefix="corpus_")
        lines = []
        for i in range(60):
            lines.append("the cat drinks milk and the kitten drinks milk")
            lines.append("the dog chases ball and the puppy chases ball")
            lines.append("alpha%d beta%d gamma%d delta%d epsilon%d zeta%d" % ((i % 9,) * 6))
        with open(os.path.join(corpus_dir, "a.txt"), "w") as f:
            f.write(chr(10).join(lines))
        out = tempfile.mkdtemp(prefix="weights_")
        info, M, vocab = te.train([corpus_dir], out, self.vocab)
        self.assertTrue(os.path.exists(os.path.join(out, "embeddings.npy")))
        i = vocab.ids

        def sim(x, y):
            return float(M[i[x]] @ M[i[y]])
        self.assertGreater(sim("cat", "kitten"), sim("cat", "puppy"))
        self.assertGreater(sim("dog", "puppy"), sim("dog", "kitten"))
        from config.embedding_vectorizer_utility_config import EmbeddingVectorizerConfig
        c = EmbeddingVectorizerConfig()
        c.embedding_path = os.path.join(out, "embeddings.npy")
        e = EmbeddingVectorizerEngine(c)
        self.assertEqual((e.source, len(e.vectorize([i["cat"]]))), ("trained", info["dim"]))
        self.assertTrue(np.allclose(e.vectorize([i["cat"]]), M[i["cat"]]))
        self.assertFalse(e.vectorize([99999]).any())            # an id the matrix does not have gives zeros, not a crash

    def test_training_scales_past_the_old_limit_is_repeatable_and_respects_its_caps(self):
        import numpy as np
        import train_embeddings as te
        d = tempfile.mkdtemp(prefix="bigcorpus_")
        rng = np.random.default_rng(5)
        def word(t, i):                                                                    # letters only: the trainer's tokenizer drops digits and underscores
            enc = lambda n: chr(97 + n // 26 % 26) + chr(97 + n % 26)
            return "tp" + enc(t) + enc(i)
        topics = [[word(t, i) for i in range(400)] for t in range(25)]                   # 25 topics x 400 words = 10,000 words, more than the old 6,000 cap
        lines = [" ".join(rng.choice(topics[t], 12)) for t in rng.integers(0, 25, 4000)]
        with open(os.path.join(d, "a.txt"), "w") as f:
            f.write(chr(10).join(lines))
        out1, out2 = tempfile.mkdtemp(), tempfile.mkdtemp()
        info, M1, vocab = te.train([d], out1, os.path.join(out1, "v1.json"), dim=32, max_words=20000)
        self.assertGreater(info["words_learned"], 6000)
        info2, M2, _ = te.train([d], out2, os.path.join(out2, "v2.json"), dim=32, max_words=20000)
        self.assertTrue(np.array_equal(M1, M2))                                              # same corpus and settings, same vectors
        capped, Mc, _ = te.train([d], tempfile.mkdtemp(), os.path.join(tempfile.mkdtemp(), "v3.json"), dim=16, max_words=500)
        self.assertEqual(capped["words_learned"], 500)
        self.assertGreater(capped["words_dropped_for_rarity_or_cap"], 5000)                  # what the cap dropped is reported, not hidden
        a, b = vocab.ids[word(3, 1)], vocab.ids[word(3, 2)]
        other = vocab.ids[word(17, 1)]
        self.assertGreater(float(M1[a] @ M1[b]), float(M1[a] @ M1[other]))                     # words of one topic sit closer than words of different topics

    def test_the_corpus_reads_javascript_and_c_comments_and_skips_generated_folders(self):
        import train_embeddings as te
        d = tempfile.mkdtemp(prefix="srcs_")
        open(os.path.join(d, "a.js"), "w").write("// the pelican swallows fish" + chr(10) + "var x = 1; /* a block about herons */")
        open(os.path.join(d, "b.c"), "w").write("/* ospreys dive for trout */ int main(void) { return 0; }")
        os.makedirs(os.path.join(d, "workspace"))
        open(os.path.join(d, "workspace", "skip.md"), "w").write("generated words that must not be read")
        text = " ".join(te.corpus([d]))
        for needle in ("pelican", "herons", "ospreys"):
            self.assertIn(needle, text)
        self.assertNotIn("generated words", text)
        self.assertNotIn("var x", text)                                                       # comments only, not the code

    def test_the_feed_forward_layer_is_deterministic_checked_and_honest_about_its_weights(self):
        import numpy as np
        from config.infrence_feed_forward_utility_config import InfrenceFeedForwardConfig
        from infrence_feed_forward_utility import InfrenceFeedForwardEngine, gelu
        c = InfrenceFeedForwardConfig()
        self.assertEqual(c.weight_source, "initialised")                                    # no trained file here: it says so
        e = InfrenceFeedForwardEngine(c)
        x = np.linspace(-1, 1, 768)
        a, b = e.process_forward_pass(x), e.process_forward_pass(x)
        self.assertEqual(a, b)
        self.assertEqual(InfrenceFeedForwardEngine(InfrenceFeedForwardConfig()).process_forward_pass(x), a)       # the same every run
        self.assertEqual(np.asarray(e.process_forward_pass([x, x])).shape, (2, 768))
        self.assertAlmostEqual(float(gelu(np.array(0.0))), 0.0)
        self.assertGreater(float(gelu(np.array(3.0))), 2.9)
        self.assertLess(float(gelu(np.array(-3.0))), 0.0)
        for bad in (np.zeros(10), np.full(768, np.nan), np.zeros((2, 2, 768))):
            with self.assertRaises(ValueError):
                e.process_forward_pass(bad)

    def test_main_runs_end_to_end_and_exits_zero(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "main.py")], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-400:] + r.stderr[-400:])
        self.assertIn("'ok': True", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
