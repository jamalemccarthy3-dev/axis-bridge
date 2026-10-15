"""train_embeddings.py - builds real word vectors from text you already have, offline, with numpy and scipy.

    python train_embeddings.py                       corpus = the .md/.txt/.rst files and the docstrings/comments of the .py .js .mjs .c .h .cpp files under the project
    python train_embeddings.py DIR [DIR ...]         corpus = those folders instead
    python train_embeddings.py --max-words 80000 --min-count 2 --dim 192 --window 5      the limits (defaults below)

Method: count which words appear near each other (nearer counts more), turn the counts into positive pointwise mutual information (with the usual 0.75 smoothing of the context
counts), and compress with a truncated SVD. Words that appear in similar company get similar vectors. The counts are kept SPARSE, so the vocabulary can be tens of thousands of
words (the old dense version was capped at 6,000). Result: data/weights/embeddings.npy, one row per vocabulary id (rows of words too rare to learn are all zeros, and the engine
skips them), plus data/weights/embeddings.json describing how it was built. The same corpus and settings always give the same vectors.
The corpus is only as big as your own writing, so the vectors are domain-specific, not a general language model."""
import argparse
import ast
import io
import json
import os
import re
import sys
import tokenize
from collections import Counter

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import svds

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config.embedding_vectorizer_utility_config import EmbeddingVectorizerConfig  # noqa: E402
from config.tokenizer_utility_config import TokenizerUtilityConfig  # noqa: E402
from vocabulary_store import Vocabulary  # noqa: E402

WORD = re.compile(r"[a-z][a-z0-9]+")
SKIP = {"__pycache__", ".git", "node_modules", "site-packages", "logs", "dist", "build", "requirements", "workspace", "data", "_archive"}
TEXT_EXT = (".md", ".txt", ".rst")
CODE_EXT = (".py", ".js", ".mjs", ".c", ".h", ".cpp")
MAX_FILE_BYTES = 20_000_000
# the limits (override with the command-line flags, or pass them to train())
WINDOW, MIN_COUNT, MAX_WORDS, DIM = 5, 2, 60000, 128
VOCAB_SIZE = 65000                                    # ids the shared vocabulary may hold (config/tokenizer_utility_config.py says the same)
C_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


def python_prose(text):
    """The human text of a python file: docstrings and comments, not the code."""
    try:
        parts = [t.string.lstrip("# ") for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type == tokenize.COMMENT]
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                d = ast.get_docstring(node)
                if d:
                    parts.append(d)
        return "\n".join(parts)
    except (SyntaxError, tokenize.TokenError, ValueError):
        return ""


def c_like_prose(text):
    """The comments of a javascript / C / C++ file (// line comments and /* block comments */)."""
    return "\n".join(re.sub(r"^[\s/*]+", "", m).rstrip("*/ ") for m in C_COMMENT.findall(text))


def corpus(roots):
    docs = []
    for root in roots:
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in SKIP and not d.endswith("_env") and not d.startswith(".")]
            for f in fn:
                p = os.path.join(dp, f)
                low = f.lower()
                if not low.endswith(TEXT_EXT + CODE_EXT):
                    continue
                try:
                    if os.path.getsize(p) > MAX_FILE_BYTES:
                        continue
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                docs.append(text if low.endswith(TEXT_EXT) else python_prose(text) if low.endswith(".py") else c_like_prose(text))
    return [d for d in docs if d.strip()]


def words_of(text):
    return WORD.findall(text.lower().replace("_", " "))


def cooccurrence(seqs, n, window):
    """Sparse symmetric co-occurrence counts: a pair at distance k counts 1/k. -> scipy CSR matrix (n x n), duplicates summed."""
    rows, cols, vals = [], [], []
    for k in range(1, window + 1):
        for q in seqs:
            if len(q) > k:
                rows.append(q[:-k])
                cols.append(q[k:])
                vals.append(np.full(len(q) - k, 1.0 / k, dtype=np.float32))
    if not rows:
        return sparse.csr_matrix((n, n), dtype=np.float32)
    r, c, v = np.concatenate(rows), np.concatenate(cols), np.concatenate(vals)
    m = sparse.coo_matrix((v, (r, c)), shape=(n, n), dtype=np.float32).tocsr()
    return (m + m.T).tocsr()


def ppmi(co, alpha=0.75):
    """Positive PMI on the stored (non-zero) entries only. Context counts are raised to `alpha` (0.75) so rare contexts are not over-rewarded."""
    csr = co.tocsr()
    coo = csr.tocoo()
    total = float(coo.data.sum())
    row = np.asarray(csr.sum(axis=1)).ravel()
    col = np.asarray(csr.sum(axis=0)).ravel() ** alpha
    col_total = col.sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log((coo.data / total) / ((row[coo.row] / total) * (col[coo.col] / col_total)))
    pmi = np.where(np.isfinite(pmi) & (pmi > 0), pmi, 0.0).astype(np.float32)
    out = sparse.coo_matrix((pmi, (coo.row, coo.col)), shape=coo.shape)
    out.eliminate_zeros()
    return out.tocsr()


def embed(m, dim):
    """Truncated SVD of the PPMI matrix -> rows of U * sqrt(S), each scaled to unit length. A fixed start vector makes the result repeatable."""
    n = m.shape[0]
    k = min(dim, n - 2)
    if k < 1:
        raise ValueError("too few words to learn from")
    u, s, _ = svds(m.astype(np.float64), k=k, v0=np.ones(n) / np.sqrt(n), random_state=0)
    order = np.argsort(-s)
    vecs = u[:, order] * np.sqrt(s[order])
    for j in range(vecs.shape[1]):                       # an SVD's sign is arbitrary: make each axis point the same way every run
        i = int(np.argmax(np.abs(vecs[:, j])))
        if vecs[i, j] < 0:
            vecs[:, j] = -vecs[:, j]
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return np.where(norms > 0, vecs / np.maximum(norms, 1e-12), 0).astype(np.float32)


def train(roots, out_dir, vocab_path, vocab_size=VOCAB_SIZE, max_words=MAX_WORDS, min_count=MIN_COUNT, dim=DIM, window=WINDOW):
    docs = [words_of(d) for d in corpus(roots)]
    counts = Counter(w for d in docs for w in d)
    kept = [w for w, c in counts.most_common(max_words) if c >= min_count]
    if len(kept) < 50:
        raise SystemExit("only %d usable words in the corpus; not enough to learn from" % len(kept))
    vocab = Vocabulary(vocab_path, vocab_size)
    ids = {w: vocab.add(w) for w in kept}
    local = {i: n for n, i in enumerate(sorted(set(ids.values())))}
    index = {w: local[i] for w, i in ids.items()}
    n = len(local)
    seqs = [np.array([index[w] for w in d if w in index], dtype=np.int64) for d in docs]
    vecs = embed(ppmi(cooccurrence(seqs, n, window)), dim)
    matrix = np.zeros((len(vocab.words), vecs.shape[1]), dtype=np.float32)
    for w, i in ids.items():
        matrix[i] = vecs[index[w]]
    vocab.save()
    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "embeddings.npy"), matrix)
    info = {"words_learned": n, "vocabulary_rows": len(vocab.words), "dim": int(vecs.shape[1]), "documents": len(docs), "tokens": int(sum(len(d) for d in docs)), "window": window,
            "min_count": min_count, "max_words": max_words, "distinct_words_seen": len(counts), "words_dropped_for_rarity_or_cap": len(counts) - n,
            "method": "sparse PPMI (context smoothing 0.75) + truncated SVD"}
    with open(os.path.join(out_dir, "embeddings.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)
    return info, matrix, vocab


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dirs", nargs="*")
    ap.add_argument("--max-words", type=int, default=MAX_WORDS)
    ap.add_argument("--min-count", type=int, default=MIN_COUNT)
    ap.add_argument("--dim", type=int, default=DIM)
    ap.add_argument("--window", type=int, default=WINDOW)
    a = ap.parse_args()
    roots = a.dirs or [os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))]
    cfg = EmbeddingVectorizerConfig()
    info, _, _ = train(roots, os.path.dirname(cfg.embedding_path), TokenizerUtilityConfig().vocab_path, max_words=a.max_words, min_count=a.min_count, dim=a.dim, window=a.window)
    print(json.dumps(info, indent=1))
