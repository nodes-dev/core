from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import EmbedderRequiredError
from nodes.kernel.node import Node


class DictEmbedder:
    def __init__(self, table, namespace="stub-v1"):
        self._table = table
        self.cache_namespace = namespace

    def embed(self, texts):
        return [self._table[t] for t in texts]


# Keys are embed_text == f"{title}\n\n{body}" for the in-memory and round-tripped nodes.
PET = (1.0, 0.0)
PET2 = (0.9, 0.1)
CAR = (0.0, 1.0)


def _embedder():
    # keyed by embed_text == "<title>\n\n<body>"
    return DictEmbedder(
        {
            "cat\n\nfeline": PET,
            "dog\n\ncanine": PET2,
            "car\n\nvehicle": CAR,
            "find pet": PET,
        }
    )


def _seed(c: Corpus) -> None:
    c.add(Node(id="topic:cat", kind="topic", title="cat", body="feline"))
    c.add(Node(id="topic:dog", kind="topic", title="dog", body="canine"))
    c.add(Node(id="topic:car", kind="topic", title="car", body="vehicle"))


def test_disabled_without_embedder_raises_before_resolution(tmp_path):
    c = Corpus(tmp_path)  # no embedder
    with pytest.raises(EmbedderRequiredError):
        c.similar("topic:does-not-exist")  # raises BEFORE ref resolution
    with pytest.raises(EmbedderRequiredError):
        c.query_vector((1.0, 0.0))
    with pytest.raises(EmbedderRequiredError):
        c.similar_text("anything")


def test_similar_ranks_by_cosine(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    assert [h.id for h in c.similar("topic:cat")] == ["topic:dog", "topic:car"]


def test_query_vector_and_similar_text(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    assert [h.id for h in c.query_vector((1.0, 0.0), k=2)] == ["topic:cat", "topic:dog"]
    assert [h.id for h in c.similar_text("find pet", k=1)] == ["topic:cat"]


def test_similar_unknown_ref_raises_referror(tmp_path):
    from nodes.kernel.errors import RefError

    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    with pytest.raises(RefError):
        c.similar("topic:missing")


def test_index_current_after_delete_and_rebuild_from_disk(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    c.delete("topic:dog")
    assert [h.id for h in c.similar("topic:cat")] == ["topic:car"]
    fresh = Corpus(tmp_path, embedder=_embedder())  # rebuild from disk (warm cache)
    assert [h.id for h in fresh.similar("topic:cat")] == ["topic:car"]


def test_rename_refreshes_id_without_reembedding(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    c.rename("topic:cat", "topic:kitten")
    assert [h.id for h in c.query_vector((1.0, 0.0), k=1)] == ["topic:kitten"]


def test_failed_embedding_leaves_corpus_unmutated(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    bad = Node(id="topic:bad", kind="topic", title="bad", body="missing")  # not in table
    with pytest.raises(KeyError):
        c.add(bad)
    # no file written (re-scan disk), structural + search indexes unchanged
    assert c.index.resolve_uid("topic:bad") is None
    assert c.search("bad") == []
    assert "topic:bad" not in [n.id for n in c.all()]


def test_failed_rename_vector_leaves_corpus_unmutated(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    # Force a namespace inconsistency so the vector prepare fails during rename —
    # after the in-memory rewrite + registry validation, before any disk write.
    c.embedder = DictEmbedder({}, namespace="other-model")
    with pytest.raises(ValueError):
        c.rename("topic:cat", "topic:kitten")
    assert c.index.resolve_uid("topic:cat") is not None
    assert c.index.resolve_uid("topic:kitten") is None
    assert [n.id for n in c.all()].count("topic:cat") == 1
