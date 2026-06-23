from __future__ import annotations

import pytest

from nodes.kernel.node import Node
from nodes.kernel.similarity import VectorCache, VectorIndex


class ListEmbedder:
    """Test embedder: looks up a frozen vector per embed_text(node) prefix."""

    cache_namespace = "test-ns"

    def __init__(self, table: dict[str, list[float]]) -> None:
        self.table = table

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.table[t.split("\n", 1)[0]] for t in texts]


def _index(tmp_path) -> VectorIndex:
    emb = ListEmbedder({"cat": [1.0, 0.1, 0.0], "dog": [0.9, 0.2, 0.0]})
    cache = VectorCache(tmp_path)
    nodes = [
        Node(id="topic:cat", kind="topic", title="cat"),
        Node(id="topic:dog", kind="topic", title="dog"),
    ]
    return VectorIndex.build(nodes, emb, cache)


def test_round_trip_preserves_query_results(tmp_path):
    idx = _index(tmp_path)
    restored = VectorIndex.from_dict(idx.to_dict())
    assert restored.dim == idx.dim
    assert restored.namespace == idx.namespace
    assert restored.query_vector((1.0, 0.0, 0.0)) == idx.query_vector((1.0, 0.0, 0.0))


def test_round_trip_preserves_internal_maps(tmp_path):
    idx = _index(tmp_path)
    restored = VectorIndex.from_dict(idx.to_dict())
    assert restored.vectors == idx.vectors
    assert restored.id_by_uid == idx.id_by_uid
    assert restored.hash_by_uid == idx.hash_by_uid


def test_empty_embedder_index_dim_null_round_trips():
    idx = VectorIndex.build([], ListEmbedder({}), VectorCache("/tmp/unused-cache"))
    d = idx.to_dict()
    assert d["dim"] is None
    assert d["namespace"] == "test-ns"
    restored = VectorIndex.from_dict(d)
    assert restored.dim is None
    assert restored.namespace == "test-ns"
    assert restored.vectors == {}


def test_to_dict_emits_dim_null_after_last_vector_removed(tmp_path):
    idx = _index(tmp_path)
    for uid in list(idx.vectors):
        idx.remove(uid)
    d = idx.to_dict()
    assert d["vectors"] == {}
    assert d["dim"] is None
    restored = VectorIndex.from_dict(d)
    assert restored.dim is None
    assert restored.namespace == "test-ns"


def test_from_dict_rejects_uid_map_mismatch():
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 2,
                "vectors": {"u1": [1.0, 0.0]},
                "id_by_uid": {},
                "hash_by_uid": {"u1": "h"},
            }
        )


def test_from_dict_rejects_non_dict_snapshot():
    with pytest.raises(ValueError, match="vector snapshot:"):
        VectorIndex.from_dict([])


@pytest.mark.parametrize("field", ("namespace", "dim", "vectors", "id_by_uid", "hash_by_uid"))
def test_from_dict_rejects_missing_top_level_keys(field):
    snapshot = {"namespace": "n", "dim": None, "vectors": {}, "id_by_uid": {}, "hash_by_uid": {}}
    del snapshot[field]
    with pytest.raises(ValueError, match="vector snapshot:"):
        VectorIndex.from_dict(snapshot)


@pytest.mark.parametrize("field", ("vectors", "id_by_uid", "hash_by_uid"))
def test_from_dict_rejects_malformed_map_containers(field):
    snapshot = {"namespace": "n", "dim": None, "vectors": {}, "id_by_uid": {}, "hash_by_uid": {}}
    snapshot[field] = []
    with pytest.raises(ValueError, match="vector snapshot:"):
        VectorIndex.from_dict(snapshot)


def test_from_dict_rejects_non_string_uid_keys():
    with pytest.raises(ValueError, match="vector snapshot:"):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 2,
                "vectors": {1: [1.0, 0.0]},
                "id_by_uid": {1: "topic:a"},
                "hash_by_uid": {1: "0" * 64},
            }
        )


def test_from_dict_rejects_non_string_id_by_uid_key():
    with pytest.raises(ValueError, match="vector snapshot:"):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 2,
                "vectors": {"u1": [1.0, 0.0]},
                "id_by_uid": {1: "topic:a"},
                "hash_by_uid": {"u1": "0" * 64},
            }
        )


def test_from_dict_rejects_non_string_id_by_uid_value():
    with pytest.raises(ValueError, match="vector snapshot:"):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 2,
                "vectors": {"u1": [1.0, 0.0]},
                "id_by_uid": {"u1": 123},
                "hash_by_uid": {"u1": "0" * 64},
            }
        )


def test_from_dict_rejects_non_string_hash_by_uid_key():
    with pytest.raises(ValueError, match="vector snapshot:"):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 2,
                "vectors": {"u1": [1.0, 0.0]},
                "id_by_uid": {"u1": "topic:a"},
                "hash_by_uid": {1: "0" * 64},
            }
        )


@pytest.mark.parametrize("hash_value", (123, "not-a-sha"))
def test_from_dict_rejects_malformed_hash_by_uid_values(hash_value):
    with pytest.raises(ValueError, match="vector snapshot:"):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 2,
                "vectors": {"u1": [1.0, 0.0]},
                "id_by_uid": {"u1": "topic:a"},
                "hash_by_uid": {"u1": hash_value},
            }
        )


def test_from_dict_rejects_dim_length_mismatch():
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 3,
                "vectors": {"u1": [1.0, 0.0]},
                "id_by_uid": {"u1": "topic:a"},
                "hash_by_uid": {"u1": "h"},
            }
        )


@pytest.mark.parametrize("vector", ([2.0, 0.0], [0.0, 0.0]))
def test_from_dict_rejects_non_unit_stored_vectors(vector):
    with pytest.raises(ValueError, match="vector snapshot:"):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 2,
                "vectors": {"u1": vector},
                "id_by_uid": {"u1": "topic:a"},
                "hash_by_uid": {"u1": "0" * 64},
            }
        )


def test_from_dict_rejects_non_null_dim_when_empty():
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {"namespace": "n", "dim": 2, "vectors": {}, "id_by_uid": {}, "hash_by_uid": {}}
        )


def test_from_dict_rejects_zero_dim_with_vector():
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 0,
                "vectors": {"u1": []},
                "id_by_uid": {"u1": "topic:a"},
                "hash_by_uid": {"u1": "h"},
            }
        )


def test_from_dict_rejects_bool_vector_entry():
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 2,
                "vectors": {"u1": [True, 0.0]},
                "id_by_uid": {"u1": "topic:a"},
                "hash_by_uid": {"u1": "h"},
            }
        )


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
def test_from_dict_rejects_non_finite_vector_entry(bad_value: float):
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 2,
                "vectors": {"u1": [bad_value, 0.0]},
                "id_by_uid": {"u1": "topic:a"},
                "hash_by_uid": {"u1": "h"},
            }
        )


def test_from_dict_rejects_non_list_vector_container():
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {
                "namespace": "n",
                "dim": 2,
                "vectors": {"u1": (1.0, 0.0)},
                "id_by_uid": {"u1": "topic:a"},
                "hash_by_uid": {"u1": "h"},
            }
        )


def test_from_dict_rejects_null_namespace_when_vectors_present():
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {
                "namespace": None,
                "dim": 2,
                "vectors": {"u1": [1.0, 0.0]},
                "id_by_uid": {"u1": "topic:a"},
                "hash_by_uid": {"u1": "h"},
            }
        )


def test_from_dict_rejects_invalid_non_null_namespace():
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {
                "namespace": "../bad",
                "dim": 2,
                "vectors": {"u1": [1.0, 0.0]},
                "id_by_uid": {"u1": "topic:a"},
                "hash_by_uid": {"u1": "h"},
            }
        )


def test_from_dict_rejects_non_string_empty_namespace_with_value_error():
    with pytest.raises(ValueError, match="vector snapshot:"):
        VectorIndex.from_dict(
            {"namespace": 123, "dim": None, "vectors": {}, "id_by_uid": {}, "hash_by_uid": {}}
        )
