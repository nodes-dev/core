from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from nodes.kernel.errors import CollisionError
from nodes.kernel.node import Node
from nodes.kernel.ranking import score_key

STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if",
        "in", "into", "is", "it", "no", "not", "of", "on", "or", "such", "that",
        "the", "their", "then", "there", "these", "they", "this", "to", "was",
        "will", "with",
    }
)

_TOKEN_RE = re.compile(r"[^\W_]+")

K1 = 1.5
B = 0.75
TITLE_BOOST = 2.0
BODY_BOOST = 1.0
_SEARCH_SNAPSHOT_KEYS = frozenset({"postings", "lengths", "id_by_uid"})


def _codepoint_sorted(values: set[str] | list[str]) -> list[str]:
    """Sort by Unicode code point order.

    Python's default string sort already uses code-point order; this named helper
    keeps the parity contract visible and gives the TS port a function to mirror
    with an explicit comparator instead of default UTF-16 sorting.
    """
    return sorted(values)


def tokenize(text: str) -> list[str]:
    """NFC-normalize, lowercase, split into Unicode-alphanumeric runs, drop stop words.

    Document tokenization keeps duplicates (term frequency is meaningful); query-side
    dedup happens in SearchIndex.search.
    """
    normalized = unicodedata.normalize("NFC", text).lower()
    return [tok for tok in _TOKEN_RE.findall(normalized) if tok not in STOP_WORDS]


@dataclass
class SearchHit:
    id: str
    uid: str
    score: float
    matched_terms: list[str]


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

    def to_dict(self) -> dict:
        return {
            "postings": {
                term: {uid: [tf[0], tf[1]] for uid, tf in docs.items()}
                for term, docs in self.postings.items()
            },
            "lengths": {uid: [lens[0], lens[1]] for uid, lens in self.lengths.items()},
            "id_by_uid": dict(self.id_by_uid),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SearchIndex":
        idx = cls()
        if not isinstance(d, dict):
            raise ValueError("search snapshot: document must be a dict")
        missing = _SEARCH_SNAPSHOT_KEYS - d.keys()
        if missing:
            raise ValueError(f"search snapshot: missing {sorted(missing)[0]}")
        postings_raw = d["postings"]
        lengths_raw = d["lengths"]
        id_by_uid_raw = d["id_by_uid"]
        if not isinstance(postings_raw, dict):
            raise ValueError("search snapshot: postings must be a dict")
        if not isinstance(lengths_raw, dict):
            raise ValueError("search snapshot: lengths must be a dict")
        if not isinstance(id_by_uid_raw, dict):
            raise ValueError("search snapshot: id_by_uid must be a dict")
        lengths = {
            uid: cls._non_negative_int_pair(v, f"search snapshot: length for uid {uid!r}")
            for uid, v in lengths_raw.items()
        }
        id_by_uid = dict(id_by_uid_raw)
        if set(lengths) != set(id_by_uid):
            raise ValueError("search snapshot: lengths/id_by_uid uid sets differ")
        postings: dict[str, dict[str, tuple[int, int]]] = {}
        for term, docs in postings_raw.items():
            if not isinstance(docs, dict):
                raise ValueError(f"search snapshot: postings bucket for term {term!r} must be a dict")
            bucket: dict[str, tuple[int, int]] = {}
            for uid, tf in docs.items():
                if uid not in lengths:
                    raise ValueError(f"search snapshot: posting uid {uid!r} absent from lengths")
                bucket[uid] = cls._non_negative_int_pair(
                    tf,
                    f"search snapshot: posting tf for term {term!r} uid {uid!r}",
                )
            postings[term] = bucket
        idx.postings = postings
        idx.lengths = lengths
        idx.id_by_uid = id_by_uid
        idx._total_title = sum(lens[0] for lens in lengths.values())
        idx._total_body = sum(lens[1] for lens in lengths.values())
        return idx

    @staticmethod
    def _non_negative_int_pair(value: object, label: str) -> tuple[int, int]:
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError(f"{label} must be a 2-item list")
        first, second = value
        if (
            isinstance(first, bool)
            or isinstance(second, bool)
            or not isinstance(first, int)
            or not isinstance(second, int)
            or first < 0
            or second < 0
        ):
            raise ValueError(f"{label} must contain non-negative ints")
        return first, second

    def search(self, query: str, limit: int | None = None) -> list[SearchHit]:
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
        ):
            raise ValueError(f"limit must be a positive int or None, got {limit!r}")
        terms = _codepoint_sorted(set(tokenize(query)))  # dedup; Python str sort is code-point order
        if not terms:
            return []

        n = self.n
        avg_title = self._total_title / n if n else 0.0
        avg_body = self._total_body / n if n else 0.0

        scores: dict[str, float] = {}
        matched: dict[str, list[str]] = {}
        for term in terms:
            docs = self.postings.get(term)
            if not docs:
                continue
            df = len(docs)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for uid, (title_tf, body_tf) in docs.items():
                title_len, body_len = self.lengths[uid]
                tf_prime = 0.0
                if title_tf:
                    denom = (1 - B + B * (title_len / avg_title)) if avg_title else 1.0
                    tf_prime += TITLE_BOOST * title_tf / denom
                if body_tf:
                    denom = (1 - B + B * (body_len / avg_body)) if avg_body else 1.0
                    tf_prime += BODY_BOOST * body_tf / denom
                scores[uid] = scores.get(uid, 0.0) + idf * (K1 + 1) * tf_prime / (K1 + tf_prime)
                matched.setdefault(uid, []).append(term)

        hits = [
            SearchHit(
                id=self.id_by_uid[uid],
                uid=uid,
                score=scores[uid],
                matched_terms=_codepoint_sorted(matched[uid]),
            )
            for uid in scores
        ]
        hits.sort(key=lambda h: (-score_key(h.score), h.id))
        return hits if limit is None else hits[:limit]

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
