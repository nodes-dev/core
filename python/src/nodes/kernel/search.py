from __future__ import annotations

import re
import unicodedata

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
