from __future__ import annotations

import math

import pytest

from nodes.kernel.node import Node
from nodes.kernel.search import SearchHit, SearchIndex, score_key


def _two_doc_index() -> SearchIndex:
    idx = SearchIndex()
    idx.upsert(Node(id="topic:a", kind="topic", title="alpha", body="alpha beta"))
    idx.upsert(Node(id="topic:b", kind="topic", title="beta", body="gamma"))
    return idx


def test_bm25f_score_matches_hand_computation():
    # N=2, avg_title=1.0, avg_body=1.5. Query "alpha" hits only topic:a (title_tf=1, body_tf=1).
    # idf = ln(2); tf' = 2.0*1/1.0 + 1.0*1/1.25 = 2.8; score = ln(2)*2.5*2.8/(1.5+2.8).
    expected = math.log(2.0) * 2.5 * 2.8 / 4.3
    hits = _two_doc_index().search("alpha")
    assert [h.id for h in hits] == ["topic:a"]
    assert isinstance(hits[0], SearchHit)
    assert hits[0].score == pytest.approx(expected, abs=1e-12)
    assert hits[0].uid != "" and hits[0].matched_terms == ["alpha"]


def test_title_match_outranks_body_match():
    # "beta" is in topic:b's TITLE and topic:a's BODY -> title boost ranks b first.
    hits = _two_doc_index().search("beta")
    assert [h.id for h in hits] == ["topic:b", "topic:a"]


def test_rounded_score_ties_break_by_id():
    idx = SearchIndex()
    idx.upsert(Node(id="topic:b", kind="topic", title="x", body="z"))
    idx.upsert(Node(id="topic:a", kind="topic", title="x", body="z"))
    assert [h.id for h in idx.search("x")] == ["topic:a", "topic:b"]


def test_matched_terms_is_sorted_subset_present_in_doc():
    idx = SearchIndex()
    idx.upsert(Node(id="topic:a", kind="topic", title="alpha", body="gamma"))
    hits = idx.search("gamma alpha zeta")  # zeta is absent from the corpus
    assert hits[0].matched_terms == ["alpha", "gamma"]


def test_query_terms_use_unicode_codepoint_order_not_utf16_order():
    # U+F900 sorts before U+1D7D9 by Unicode code point, but JS default UTF-16
    # sort would put the surrogate-pair token first. This pins the TS parity contract.
    # Note: After NFC normalization, U+F900 becomes U+8C48, so matched_terms contains the normalized form.
    import unicodedata
    bmp = "\uf900"       # CJK COMPATIBILITY IDEOGRAPH-F900, category Lo
    non_bmp = "\U0001D7D9"  # MATHEMATICAL DOUBLE-STRUCK DIGIT ONE, category Nd
    idx = SearchIndex()
    idx.upsert(Node(id="topic:a", kind="topic", title=bmp, body=non_bmp))
    hits = idx.search(f"{non_bmp} {bmp}")
    bmp_normalized = unicodedata.normalize("NFC", bmp)
    assert hits[0].matched_terms == [bmp_normalized, non_bmp]


def test_empty_stopword_and_absent_queries_return_empty():
    idx = SearchIndex()
    idx.upsert(Node(id="topic:a", kind="topic", title="alpha", body="the cat"))
    assert idx.search("") == []
    assert idx.search("   ") == []
    assert idx.search("the") == []     # stop word only
    assert idx.search("zeta") == []    # term absent


def test_limit_truncates_and_none_is_unbounded():
    idx = SearchIndex()
    for slug in ("a", "b", "c"):
        idx.upsert(Node(id=f"topic:{slug}", kind="topic", title="alpha", body="alpha"))
    assert len(idx.search("alpha")) == 3
    assert len(idx.search("alpha", limit=2)) == 2
    assert len(idx.search("alpha", limit=None)) == 3


@pytest.mark.parametrize("bad", [0, -1, 1.0, True, "1"])
def test_search_rejects_bad_limit(bad):
    idx = SearchIndex()
    idx.upsert(Node(id="topic:a", kind="topic", title="alpha", body=""))
    with pytest.raises(ValueError):
        idx.search("alpha", limit=bad)


def test_score_key_rounds_to_6dp():
    # Inputs kept clear of the exact .5 boundary so float representation can't flip them.
    assert score_key(1.2345674) == 1.234567   # rounds down
    assert score_key(1.2345678) == 1.234568   # rounds up
    assert score_key(0.0) == 0.0
