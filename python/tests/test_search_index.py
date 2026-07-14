from __future__ import annotations

import pytest

from nodes.core.errors import CollisionError
from nodes.core.node import Node
from nodes.core.search import SearchIndex


def _norm(idx: SearchIndex) -> dict:
    return {
        "postings": {t: sorted(docs.items()) for t, docs in idx.postings.items()},
        "lengths": dict(idx.lengths),
        "id_by_uid": dict(idx.id_by_uid),
        "n": idx.n,
        "totals": (idx._total_title, idx._total_body),
    }


def test_upsert_records_per_field_term_frequencies():
    idx = SearchIndex()
    n = Node(id="topic:a", kind="topic", title="alpha", body="alpha alpha beta")
    idx.upsert(n)
    assert idx.postings["alpha"][n.uid] == (1, 2)  # 1 in title, 2 in body
    assert idx.postings["beta"][n.uid] == (0, 1)
    assert idx.lengths[n.uid] == (1, 3)
    assert idx.id_by_uid[n.uid] == "topic:a"
    assert idx.n == 1


def test_upsert_replaces_not_duplicates():
    idx = SearchIndex()
    n = Node(id="topic:a", kind="topic", title="", body="alpha alpha")
    idx.upsert(n)
    assert idx.postings["alpha"][n.uid] == (0, 2)
    n.body = "beta"
    idx.upsert(n)
    assert "alpha" not in idx.postings        # stale postings dropped
    assert idx.postings["beta"][n.uid] == (0, 1)
    assert idx.lengths[n.uid] == (0, 1)
    assert idx.n == 1


def test_remove_drops_everything_and_is_noop_when_absent():
    idx = SearchIndex()
    n = Node(id="topic:a", kind="topic", title="alpha", body="beta")
    idx.upsert(n)
    idx.remove(n.uid)
    assert idx.n == 0 and idx.postings == {} and idx.lengths == {} and idx.id_by_uid == {}
    assert (idx._total_title, idx._total_body) == (0, 0)
    idx.remove("not-present")  # no raise, no change
    assert idx.n == 0


def test_empty_text_still_counts_as_a_document():
    idx = SearchIndex()
    n = Node(id="topic:a", kind="topic", title="", body="")
    idx.upsert(n)
    assert idx.n == 1
    assert idx.lengths[n.uid] == (0, 0)
    assert idx.postings == {}


def test_build_rejects_duplicate_uid():
    a = Node(id="topic:a", kind="topic", title="A", uid="dup")
    b = Node(id="topic:b", kind="topic", title="B", uid="dup")
    with pytest.raises(CollisionError):
        SearchIndex.build([a, b])


def test_incremental_matches_fresh_rebuild():
    a = Node(id="topic:a", kind="topic", title="Alpha", body="alpha beta")
    b = Node(id="topic:b", kind="topic", title="Beta", body="gamma delta")
    c = Node(id="topic:c", kind="topic", title="C", body="alpha")
    idx = SearchIndex()
    idx.upsert(a)
    idx.upsert(b)
    a.body = "alpha gamma"
    idx.upsert(a)          # overwrite a
    idx.remove(b.uid)      # drop b
    idx.upsert(c)
    assert _norm(idx) == _norm(SearchIndex.build([a, c]))
