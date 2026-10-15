"""vocabulary_store.py - the one vocabulary the tokenizer and the vocabulary mapper share. Local, deterministic, saved to data/vocab.json.
Ids 0..3 are reserved (pad, unknown, start, end); a new word gets the next free id, so the same text always gives the same ids on the same vocabulary."""
import json
import os
import threading

RESERVED = ["<pad>", "<unk>", "<s>", "</s>"]


class Vocabulary:
    def __init__(self, path, max_size=10000):
        self.path, self.max_size = path, max_size
        self._lock = threading.Lock()
        self.words = list(RESERVED)
        self.ids = {w: i for i, w in enumerate(self.words)}
        try:
            with open(path, encoding="utf-8") as f:
                words = json.load(f)
            if isinstance(words, list) and words[:len(RESERVED)] == RESERVED:
                self.words = words
                self.ids = {w: i for i, w in enumerate(words)}
        except (OSError, ValueError):
            pass

    def add(self, word):
        """-> id of the word; <unk> (1) once the vocabulary is full."""
        with self._lock:
            if word in self.ids:
                return self.ids[word]
            if len(self.words) >= self.max_size:
                return 1
            self.ids[word] = len(self.words)
            self.words.append(word)
            return self.ids[word]

    def word(self, i):
        return self.words[i] if 0 <= i < len(self.words) else "<unk>"

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.words, f)
        os.replace(tmp, self.path)
