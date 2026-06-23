from __future__ import annotations

import pytest

from nodes.kernel.node import Node
from nodes.kernel.search import SearchIndex


def _corpus() -> list[Node]:
    return [
        Node(id="topic:alpha", kind="topic", title="Alpha Beta", body="alpha gamma gamma"),
        Node(id="topic:delta", kind="topic", title="Delta", body="beta delta"),
        Node(id="topic:empty", kind="topic", title="", body=""),
    ]


def test_round_trip_preserves_search_results():
    idx = SearchIndex.build(_corpus())
    restored = SearchIndex.from_dict(idx.to_dict())
    for query in ("alpha", "beta", "gamma", "delta", "nothing"):
        assert idx.search(query) == restored.search(query)


def test_round_trip_preserves_internal_state():
    idx = SearchIndex.build(_corpus())
    restored = SearchIndex.from_dict(idx.to_dict())
    assert restored.postings == idx.postings
    assert restored.lengths == idx.lengths
    assert restored.id_by_uid == idx.id_by_uid
    assert restored._total_title == idx._total_title
    assert restored._total_body == idx._total_body


def test_empty_index_round_trips():
    idx = SearchIndex.build([])
    restored = SearchIndex.from_dict(idx.to_dict())
    assert restored.n == 0
    assert restored.search("anything") == []


def test_from_dict_rejects_length_id_mismatch():
    with pytest.raises(ValueError):
        SearchIndex.from_dict({"postings": {}, "lengths": {"u1": [1, 0]}, "id_by_uid": {}})


def test_from_dict_rejects_stale_posting_uid():
    with pytest.raises(ValueError):
        SearchIndex.from_dict(
            {"postings": {"x": {"ghost": [1, 0]}}, "lengths": {"u1": [1, 0]}, "id_by_uid": {"u1": "topic:a"}}
        )
