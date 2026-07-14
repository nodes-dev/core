from __future__ import annotations

from nodes.core.corpus import Corpus
from nodes.core.node import Node


def _seed(c: Corpus) -> None:
    c.add(Node(id="topic:a", kind="topic", title="alpha", body="alpha beta"))
    c.add(Node(id="topic:b", kind="topic", title="beta", body="gamma"))


def test_search_ranks_title_above_body_after_add(tmp_path):
    c = Corpus(tmp_path)
    _seed(c)
    assert [h.id for h in c.search("beta")] == ["topic:b", "topic:a"]


def test_search_reflects_delete(tmp_path):
    c = Corpus(tmp_path)
    _seed(c)
    c.delete("topic:b")
    assert [h.id for h in c.search("beta")] == ["topic:a"]  # only the body match remains


def test_search_reflects_rename(tmp_path):
    c = Corpus(tmp_path)
    _seed(c)
    c.rename("topic:a", "topic:a2")
    hits = c.search("alpha")
    assert [h.id for h in hits] == ["topic:a2"]  # hit carries the new id


def test_search_index_rebuilds_from_disk(tmp_path):
    c = Corpus(tmp_path)
    _seed(c)
    fresh = Corpus(tmp_path)  # second corpus scans the same dir
    assert [h.id for h in fresh.search("beta")] == [h.id for h in c.search("beta")]


def test_limit_is_honored_through_corpus(tmp_path):
    c = Corpus(tmp_path)
    _seed(c)
    assert len(c.search("beta", limit=1)) == 1
