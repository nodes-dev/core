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


def test_to_dict_uses_json_pair_schema():
    snapshot = SearchIndex.build(_corpus()).to_dict()
    assert set(snapshot) == {"postings", "lengths", "id_by_uid"}
    for length_pair in snapshot["lengths"].values():
        assert isinstance(length_pair, list)
        assert len(length_pair) == 2
        assert all(isinstance(value, int) for value in length_pair)
    for docs in snapshot["postings"].values():
        for tf_pair in docs.values():
            assert isinstance(tf_pair, list)
            assert len(tf_pair) == 2
            assert all(isinstance(value, int) for value in tf_pair)


def test_empty_index_round_trips():
    idx = SearchIndex.build([])
    restored = SearchIndex.from_dict(idx.to_dict())
    assert restored.n == 0
    assert restored.search("anything") == []


def test_from_dict_rejects_length_id_mismatch():
    with pytest.raises(ValueError):
        SearchIndex.from_dict({"postings": {}, "lengths": {"u1": [1, 0]}, "id_by_uid": {}})


def test_from_dict_rejects_non_dict_snapshot():
    with pytest.raises(ValueError, match="search snapshot:"):
        SearchIndex.from_dict([])


@pytest.mark.parametrize("field", ("postings", "lengths", "id_by_uid"))
def test_from_dict_rejects_missing_top_level_keys(field):
    snapshot = {"postings": {}, "lengths": {}, "id_by_uid": {}}
    del snapshot[field]
    with pytest.raises(ValueError, match="search snapshot:"):
        SearchIndex.from_dict(snapshot)


@pytest.mark.parametrize("field", ("postings", "lengths", "id_by_uid"))
def test_from_dict_rejects_malformed_map_containers(field):
    snapshot = {"postings": {}, "lengths": {}, "id_by_uid": {}}
    snapshot[field] = []
    with pytest.raises(ValueError, match="search snapshot:"):
        SearchIndex.from_dict(snapshot)


def test_from_dict_rejects_stale_posting_uid():
    with pytest.raises(ValueError):
        SearchIndex.from_dict(
            {"postings": {"x": {"ghost": [1, 0]}}, "lengths": {"u1": [1, 0]}, "id_by_uid": {"u1": "topic:a"}}
        )


@pytest.mark.parametrize("value", ([1.9, 0], ["1", 0], [True, 0], [-1, 0], [1], (1, 0)))
def test_from_dict_rejects_malformed_length_values(value):
    with pytest.raises(ValueError):
        SearchIndex.from_dict({"postings": {}, "lengths": {"u1": value}, "id_by_uid": {"u1": "topic:a"}})


@pytest.mark.parametrize("value", ([1.9, 0], ["1", 0], [True, 0], [-1, 0], [1], (1, 0)))
def test_from_dict_rejects_malformed_posting_tf_values(value):
    with pytest.raises(ValueError):
        SearchIndex.from_dict(
            {"postings": {"x": {"u1": value}}, "lengths": {"u1": [1, 0]}, "id_by_uid": {"u1": "topic:a"}}
        )
