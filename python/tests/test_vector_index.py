from __future__ import annotations

import pytest

from nodes.core.errors import CollisionError
from nodes.core.node import Node
from nodes.core.similarity import VectorCache, VectorIndex, embed_text


class DictEmbedder:
    """Deterministic test embedder: maps exact embed_text -> raw vector."""

    def __init__(self, table: dict[str, tuple[float, ...]], namespace: str = "stub-v1") -> None:
        self._table = table
        self.cache_namespace = namespace

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self._table[t] for t in texts]


def _node(node_id: str, title: str, body: str = "", uid: str | None = None) -> Node:
    return Node(id=node_id, uid=uid or node_id.replace(":", "_"), kind="topic", title=title, body=body)


def _embedder(nodes: list[Node], vectors: list[tuple[float, ...]], **kw) -> DictEmbedder:
    return DictEmbedder({embed_text(n): v for n, v in zip(nodes, vectors)}, **kw)


def test_build_normalizes_and_sets_dim_and_namespace(tmp_path):
    nodes = [_node("topic:a", "a"), _node("topic:b", "b")]
    emb = _embedder(nodes, [(3.0, 4.0), (0.0, 1.0)])
    idx = VectorIndex.build(nodes, emb, VectorCache(tmp_path))
    assert idx.dim == 2
    assert idx.namespace == "stub-v1"
    assert idx.vectors["topic_a"] == pytest.approx((0.6, 0.8))
    assert idx.id_by_uid == {"topic_a": "topic:a", "topic_b": "topic:b"}


def test_build_rejects_duplicate_uid(tmp_path):
    nodes = [_node("topic:a", "a", uid="dup"), _node("topic:b", "b", uid="dup")]
    emb = _embedder(nodes, [(1.0, 0.0), (0.0, 1.0)])
    with pytest.raises(CollisionError):
        VectorIndex.build(nodes, emb, VectorCache(tmp_path))


def test_upsert_replaces_on_content_change(tmp_path):
    n1 = _node("topic:a", "a", body="one", uid="u")
    n2 = _node("topic:a", "a", body="two", uid="u")
    emb = DictEmbedder({embed_text(n1): (1.0, 0.0), embed_text(n2): (0.0, 1.0)})
    idx = VectorIndex.build([n1], emb, VectorCache(tmp_path))
    idx.upsert(n2, emb, VectorCache(tmp_path))
    assert idx.vectors["u"] == pytest.approx((0.0, 1.0))
    assert idx.dim == 2


def test_upsert_same_content_new_id_refreshes_id_only(tmp_path):
    # the rename case: title/body unchanged, id changed -> no re-embed
    n1 = _node("topic:a", "a", body="x", uid="u")
    renamed = _node("topic:a2", "a", body="x", uid="u")
    table = {embed_text(n1): (1.0, 0.0)}  # only the original text is embeddable

    class OneShot(DictEmbedder):
        def embed(self, texts):  # fail loudly if a re-embed is attempted
            return [self._table[t] for t in texts]

    emb = OneShot(table)
    idx = VectorIndex.build([n1], emb, VectorCache(tmp_path))
    before = idx.vectors["u"]
    idx.upsert(renamed, emb, VectorCache(tmp_path))  # must not call embed(missing text)
    assert idx.vectors["u"] == before
    assert idx.id_by_uid["u"] == "topic:a2"


def test_remove_drops_all_state(tmp_path):
    nodes = [_node("topic:a", "a"), _node("topic:b", "b")]
    emb = _embedder(nodes, [(1.0, 0.0), (0.0, 1.0)])
    idx = VectorIndex.build(nodes, emb, VectorCache(tmp_path))
    idx.remove("topic_a")
    assert "topic_a" not in idx.vectors and "topic_a" not in idx.id_by_uid


def test_dimension_mismatch_rejected(tmp_path):
    nodes = [_node("topic:a", "a"), _node("topic:b", "b")]
    emb = _embedder(nodes, [(1.0, 0.0), (1.0, 0.0, 0.0)])
    with pytest.raises(ValueError):
        VectorIndex.build(nodes, emb, VectorCache(tmp_path))


def test_namespace_mismatch_rejected(tmp_path):
    n1 = [_node("topic:a", "a")]
    idx = VectorIndex.build(n1, _embedder(n1, [(1.0, 0.0)], namespace="model-a"), VectorCache(tmp_path))
    n2 = _node("topic:b", "b")
    other = DictEmbedder({embed_text(n2): (0.0, 1.0)}, namespace="model-b")
    with pytest.raises(ValueError):
        idx.upsert(n2, other, VectorCache(tmp_path))


def test_zero_norm_vector_rejected(tmp_path):
    nodes = [_node("topic:a", "a")]
    emb = _embedder(nodes, [(0.0, 0.0)])
    with pytest.raises(ValueError):
        VectorIndex.build(nodes, emb, VectorCache(tmp_path))


def test_bool_embedder_vector_rejected(tmp_path):
    nodes = [_node("topic:a", "a")]
    emb = _embedder(nodes, [(True,)])
    with pytest.raises(ValueError):
        VectorIndex.build(nodes, emb, VectorCache(tmp_path))


def test_empty_build_binds_namespace(tmp_path):
    idx = VectorIndex.build([], DictEmbedder({}, namespace="model-x"), VectorCache(tmp_path))
    assert idx.namespace == "model-x"
    assert idx.dim is None
