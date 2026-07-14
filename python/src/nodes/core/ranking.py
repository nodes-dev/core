from __future__ import annotations

import math


def score_key(score: float) -> float:
    """Half-up rounding to 6 decimal places — the shared ranking/parity key.

    Used by both the full-text search index and the similarity index. Floor-based
    half-up is identical in Python and TypeScript (``math.floor`` / ``Math.floor``
    agree on negative operands), so it is correct over BM25 (non-negative) and
    cosine (``[-1, 1]``) scores alike.
    """
    return math.floor(score * 1_000_000 + 0.5) / 1_000_000
