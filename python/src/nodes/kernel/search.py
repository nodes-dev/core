from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from nodes.kernel.errors import CollisionError
from nodes.kernel.node import Node

STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if",
        "in", "into", "is", "it", "no", "not", "of", "on", "or", "such", "that",
        "the", "their", "then", "there", "these", "they", "this", "to", "was",
        "will", "with",
    }
)

_TOKEN_RE = re.compile(r"[^\W_]+")


def tokenize(text: str) -> list[str]:
    """NFC-normalize, lowercase, split into Unicode-alphanumeric runs, drop stop words.

    Document tokenization keeps duplicates (term frequency is meaningful); query-side
    dedup happens in SearchIndex.search.
    """
    normalized = unicodedata.normalize("NFC", text).lower()
    return [tok for tok in _TOKEN_RE.findall(normalized) if tok not in STOP_WORDS]


class SearchIndex:
    """In-memory inverted index over node title+body. Pure data; no file I/O."""

    def __init__(self) -> None:
        self.postings: dict[str, dict[str, tuple[int, int]]] = {}  # term -> uid -> (title_tf, body_tf)
        self.lengths: dict[str, tuple[int, int]] = {}              # uid -> (title_len, body_len)
        self.id_by_uid: dict[str, str] = {}
        self._total_title = 0
        self._total_body = 0

    @property
    def n(self) -> int:
        return len(self.lengths)

    @classmethod
    def build(cls, nodes: Iterable[Node]) -> "SearchIndex":
        idx = cls()
        for node in nodes:
            if node.uid in idx.lengths:
                raise CollisionError(f"duplicate uid {node.uid!r} in corpus")
            idx.upsert(node)
        return idx

    @staticmethod
    def _counts(tokens: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for tok in tokens:
            counts[tok] = counts.get(tok, 0) + 1
        return counts

    def upsert(self, node: Node) -> None:
        if node.uid in self.lengths:
            self._drop(node.uid)
        title_tokens = tokenize(node.title)
        body_tokens = tokenize(node.body)
        title_counts = self._counts(title_tokens)
        body_counts = self._counts(body_tokens)
        for term in title_counts.keys() | body_counts.keys():
            self.postings.setdefault(term, {})[node.uid] = (
                title_counts.get(term, 0),
                body_counts.get(term, 0),
            )
        self.lengths[node.uid] = (len(title_tokens), len(body_tokens))
        self.id_by_uid[node.uid] = node.id
        self._total_title += len(title_tokens)
        self._total_body += len(body_tokens)

    def remove(self, uid: str) -> None:
        self._drop(uid)

    def _drop(self, uid: str) -> None:
        lengths = self.lengths.pop(uid, None)
        if lengths is None:
            return
        self._total_title -= lengths[0]
        self._total_body -= lengths[1]
        del self.id_by_uid[uid]
        for term, docs in list(self.postings.items()):
            if uid in docs:
                del docs[uid]
                if not docs:
                    del self.postings[term]
