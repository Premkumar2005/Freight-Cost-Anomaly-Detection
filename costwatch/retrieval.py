"""Small, dependency-free TF-IDF retriever over the notes (deterministic, no LLM, no randomness).

Retrieval only *ranks* notes. Whether a note actually justifies a rise is decided
separately by the verdict gate (route, time window, direction), so a wrong retrieval
can never produce a fabricated 'justified'.
"""
import math
import re
from collections import Counter

STOP = {"a", "an", "the", "of", "on", "in", "to", "and", "or", "for", "by", "was", "were", "is", "are",
        "this", "that", "with", "as", "at", "from", "be", "has", "have", "had", "not", "no", "it", "its"}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def tokenize(text: str):
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]


class NoteRetriever:
    def __init__(self, notes):
        """notes: DataFrame with note_id, applies_to, note."""
        self.ids = list(notes["note_id"])
        docs = [tokenize(f"{r.applies_to} {r.note}") for r in notes.itertuples()]
        n = len(docs)
        df = Counter(t for d in docs for t in set(d))
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.vecs = [self._vec(d) for d in docs]

    def _vec(self, tokens):
        tf = Counter(tokens)
        v = {t: c * self.idf.get(t, 0.0) for t, c in tf.items() if t in self.idf}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def search(self, query: str, k: int):
        q = self._vec(tokenize(query))
        scored = [(sum(w * v.get(t, 0.0) for t, w in q.items()), nid) for nid, v in zip(self.ids, self.vecs)]
        scored.sort(key=lambda x: (-round(x[0], 10), x[1]))  # stable tie-break on note_id
        return [(nid, s) for s, nid in scored[:k]]


def build_query(route: str) -> str:
    """Query describing what could explain a cost rise on this route."""
    return (f"{route.replace('-', ' ')} {route} cost rise increase surcharge diesel fuel price toll "
            f"flood weather festival disruption all routes")
