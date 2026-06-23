from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import RefError
from nodes.kernel.node import Node
from nodes.kernel.store import Store


def test_write_file_read_file_roundtrip(tmp_path):
    store = Store(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A", body="hi")
    store.write_file(n)
    got = store.read_file("topic:a")
    assert got.title == "A" and got.body == "hi" and got.uid == n.uid


def test_write_file_has_no_collision_check(tmp_path):
    # Store is a dumb primitive: writing a different uid at the same id just overwrites.
    store = Store(tmp_path)
    store.write_file(Node(id="topic:a", kind="topic", title="A"))
    store.write_file(Node(id="topic:a", kind="topic", title="Other"))  # no raise
    assert store.read_file("topic:a").title == "Other"


def test_path_for_encodes_curie_slug(tmp_path):
    store = Store(tmp_path)
    path = store.path_for("gene:HGNC:PHF19")
    assert path == tmp_path / "gene" / "HGNC__PHF19.md"


def test_read_file_missing_raises(tmp_path):
    with pytest.raises(RefError):
        Store(tmp_path).read_file("topic:ghost")


def test_delete_file_removes_then_missing_raises(tmp_path):
    store = Store(tmp_path)
    store.write_file(Node(id="topic:a", kind="topic", title="A"))
    store.delete_file("topic:a")
    with pytest.raises(RefError):
        store.read_file("topic:a")
    with pytest.raises(RefError):
        store.delete_file("topic:a")


def test_all_nodes_scans_corpus_sorted(tmp_path):
    store = Store(tmp_path)
    store.write_file(Node(id="topic:b", kind="topic", title="B"))
    store.write_file(Node(id="topic:a", kind="topic", title="A"))
    ids = [n.id for n in store.all_nodes()]
    assert ids == ["topic:a", "topic:b"]


def test_all_nodes_ignores_private_nodes_index_tree(tmp_path):
    store = Store(tmp_path)
    store.write_file(Node(id="topic:a", kind="topic", title="A"))
    (tmp_path / ".nodes-index").mkdir()
    (tmp_path / ".nodes-index" / "cache.md").write_text("not a node", encoding="utf-8")

    ids = [n.id for n in store.all_nodes()]

    assert ids == ["topic:a"]


def test_corpus_construction_ignores_private_nodes_index_tree(tmp_path):
    store = Store(tmp_path)
    store.write_file(Node(id="topic:a", kind="topic", title="A"))
    (tmp_path / ".nodes-index").mkdir()
    (tmp_path / ".nodes-index" / "cache.md").write_text("not a node", encoding="utf-8")

    corpus = Corpus(tmp_path)

    assert [n.id for n in corpus.all()] == ["topic:a"]
