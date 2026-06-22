from __future__ import annotations

import pytest

from nodes.kernel.node import Node
from nodes.kernel.ranking import score_key
from nodes.kernel.similarity import VectorCache, VectorIndex, embed_text


class DictEmbedder:
    def __init__(self, table, namespace="stub-v1"):
        self._table = table
        self.cache_namespace = namespace

    def embed(self, texts):
        return [self._table[t] for t in texts]


def _node(node_id, title, body=""):
    return Node(id=node_id, uid=node_id.replace(":", "_"), kind="topic", title=title, body=body)


def _index(tmp_path, nodes, vectors, **kw):
    emb = DictEmbedder({embed_text(n): v for n, v in zip(nodes, vectors)}, **kw)
    return VectorIndex.build(nodes, emb, VectorCache(tmp_path)), emb


def test_query_vector_exact_cosine(tmp_path):
    nodes = [_node("topic:x", "x"), _node("topic:y", "y")]
    idx, _ = _index(tmp_path, nodes, [(3.0, 4.0), (1.0, 0.0)])
    hits = idx.query_vector((4.0, 3.0))
    by_id = {h.id: h.score for h in hits}
    assert by_id["topic:x"] == pytest.approx(0.96)   # (0.6,0.8)·(0.8,0.6)
    assert by_id["topic:y"] == pytest.approx(0.8)     # (0.6,0.8)·(1,0)


def test_query_vector_ranks_desc_then_id(tmp_path):
    # two docs identical to the query vector tie on score -> id ascending
    nodes = [_node("topic:b", "b"), _node("topic:a", "a")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0), (1.0, 0.0)])
    assert [h.id for h in idx.query_vector((1.0, 0.0))] == ["topic:a", "topic:b"]


def test_similar_excludes_self(tmp_path):
    nodes = [_node("topic:x", "x"), _node("topic:y", "y")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0), (0.0, 1.0)])
    hits = idx.similar("topic_x")
    assert [h.id for h in hits] == ["topic:y"]  # self ('topic:x') excluded


def test_similar_unknown_uid_raises_keyerror(tmp_path):
    nodes = [_node("topic:x", "x")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0)])
    with pytest.raises(KeyError):
        idx.similar("nope")


def test_similar_text_embeds_then_ranks(tmp_path):
    nodes = [_node("topic:x", "x"), _node("topic:y", "y")]
    idx, emb = _index(tmp_path, nodes, [(1.0, 0.0), (0.0, 1.0)])
    emb._table["find x"] = (1.0, 0.0)
    assert [h.id for h in idx.similar_text("find x", emb)] == ["topic:x", "topic:y"]


def test_similar_text_namespace_mismatch_raises(tmp_path):
    nodes = [_node("topic:x", "x")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0)], namespace="model-a")
    other = DictEmbedder({"q": (1.0, 0.0)}, namespace="model-b")
    with pytest.raises(ValueError):
        idx.similar_text("q", other)


def test_similar_text_namespace_checked_on_empty_built_index(tmp_path):
    # build([]) binds the namespace, so even an empty index rejects a foreign embedder
    idx = VectorIndex.build([], DictEmbedder({}, namespace="model-a"), VectorCache(tmp_path))
    other = DictEmbedder({"q": (1.0, 0.0)}, namespace="model-b")
    with pytest.raises(ValueError):
        idx.similar_text("q", other)


def test_limit_k_honored_and_validated(tmp_path):
    nodes = [_node("topic:x", "x"), _node("topic:y", "y")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0), (0.0, 1.0)])
    assert len(idx.query_vector((1.0, 1.0), k=1)) == 1
    for bad in (0, -1, 1.5, True, "1"):
        with pytest.raises(ValueError):
            idx.query_vector((1.0, 1.0), k=bad)


def test_query_validates_vector_even_when_empty(tmp_path):
    idx = VectorIndex()  # empty: dim is None
    assert idx.query_vector((1.0, 2.0)) == []        # valid query, no candidates
    with pytest.raises(ValueError):
        idx.query_vector((0.0, 0.0))                  # zero-norm still rejected
    with pytest.raises(ValueError):
        idx.query_vector(())                          # empty vector still rejected
    with pytest.raises(ValueError):
        idx.query_vector((True,))                      # bool is not accepted as numeric


def test_query_dim_mismatch_rejected(tmp_path):
    nodes = [_node("topic:x", "x")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0)])
    with pytest.raises(ValueError):
        idx.query_vector((1.0, 0.0, 0.0))


def test_score_uses_score_key_for_ranking(tmp_path):
    # scores within 1e-6 collapse under score_key, so id breaks the tie
    nodes = [_node("topic:a", "a"), _node("topic:b", "b")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0), (1.0, 1e-7)])
    hits = idx.query_vector((1.0, 0.0))
    assert score_key(hits[0].score) == score_key(hits[1].score)
    assert [h.id for h in hits] == ["topic:a", "topic:b"]


def test_similar_text_rejects_bool_embedder_vector(tmp_path):
    nodes = [_node("topic:x", "x")]
    idx, emb = _index(tmp_path, nodes, [(1.0, 0.0)])
    emb._table["bad"] = (True,)
    with pytest.raises(ValueError):
        idx.similar_text("bad", emb)
