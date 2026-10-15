"""AXIS_LLM_link.py - the link between axis-omni (voice) and axis-llm (language), entirely on this machine.

    link = AxisLlmLink()
    link.tokens("hello world")        word ids from axis-llm's vocabulary (read only: it never adds words to axis-llm's vocabulary file)
    link.embed("hello world")         one vector for the text from axis-llm's TRAINED embeddings (None when axis-llm has none: nothing is invented)
    link.ask("say hi in one line")    a reply from a local Ollama model, or {"status": "unavailable", "reason": ...}

axis-llm is found next to this engine (../axis-llm) or at AXIS_LLM_DIR. Nothing is sent to the internet; Ollama is only used on loopback."""
import importlib.util
import json
import os
import re
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WORD = re.compile(r"[a-z][a-z0-9]+")


class AxisLlmLink:
    def __init__(self, llm_dir=None, ollama_url=None):
        self.llm_dir = llm_dir or os.environ.get("AXIS_LLM_DIR") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "axis-llm")
        self.ollama_url = (ollama_url or os.environ.get("VC_OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
        self._vocab = None
        self._matrix = None

    # ---- axis-llm's data, read without importing its packages (its folder names collide with omni's) ----------------------------------
    def _load_vocab(self):
        if self._vocab is None:
            path = os.path.join(self.llm_dir, "data", "vocab.json")
            try:
                with open(path, encoding="utf-8") as f:
                    words = json.load(f)
            except (OSError, ValueError):
                self._vocab = {}
                return self._vocab
            self._vocab = {w: i for i, w in enumerate(words)}
        return self._vocab

    def available(self):
        """-> {"vocabulary": n words or 0, "embeddings": True/False, "reason"}: what axis-llm has ready."""
        vocab = self._load_vocab()
        emb = os.path.isfile(os.path.join(self.llm_dir, "data", "weights", "embeddings.npy"))
        return {"vocabulary": len(vocab), "embeddings": emb, "reason": "ok" if vocab else "no vocabulary at %s (run axis-llm/train_embeddings.py)" % self.llm_dir}

    def tokens(self, text):
        """-> [id per word]; a word axis-llm has not seen is id 1 (<unk>). Raises RuntimeError if axis-llm has no vocabulary (an empty vocabulary would make every word <unk>)."""
        vocab = self._load_vocab()
        if not vocab:
            raise RuntimeError(self.available()["reason"])
        return [vocab.get(w, 1) for w in WORD.findall(str(text).lower().replace("_", " "))]

    def embed(self, text):
        """-> the mean of the trained vectors of the words axis-llm knows (a list of floats), or None when there are no trained embeddings or no known word."""
        import numpy as np
        if self._matrix is None:
            path = os.path.join(self.llm_dir, "data", "weights", "embeddings.npy")
            self._matrix = np.load(path) if os.path.isfile(path) else False
        if self._matrix is False:
            return None
        rows = [self._matrix[i] for i in self.tokens(text) if 0 < i < len(self._matrix) and self._matrix[i].any()]
        return np.mean(rows, axis=0).tolist() if rows else None

    # ---- a local model ------------------------------------------------------------------------------------------------------------------
    def ask(self, prompt, model=None, timeout=300):
        """Asks a local Ollama model. -> {"status": "ok", "text", "model"} or {"status": "unavailable", "reason"} (no server, no model, or a non-loopback URL)."""
        host = re.match(r"^https?://([^/:]+)", self.ollama_url)
        if not host or host.group(1) not in ("127.0.0.1", "localhost"):
            return {"status": "unavailable", "reason": "the Ollama address must be on this machine"}
        try:
            with urllib.request.urlopen(self.ollama_url + "/api/tags", timeout=5) as r:
                models = [m["name"] for m in json.loads(r.read()).get("models", [])]
        except (OSError, ValueError) as e:
            return {"status": "unavailable", "reason": "no Ollama server: %s" % getattr(e, "reason", e)}
        if not models:
            return {"status": "unavailable", "reason": "Ollama has no models installed"}
        model = model or os.environ.get("VC_OLLAMA_MODEL") or models[0]
        if model not in models and (model + ":latest") in models:
            model += ":latest"
        if model not in models:
            return {"status": "unavailable", "reason": "Ollama has no model %r (it has %s)" % (model, models)}
        body = json.dumps({"model": model, "prompt": str(prompt), "stream": False}).encode()
        try:
            req = urllib.request.Request(self.ollama_url + "/api/generate", data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return {"status": "ok", "text": (json.loads(r.read()).get("response") or "").strip(), "model": model}
        except (OSError, ValueError) as e:
            return {"status": "unavailable", "reason": "the model did not answer: %s" % getattr(e, "reason", e)}
