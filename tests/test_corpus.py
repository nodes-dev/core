from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import CollisionError, RefError
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to


def test_add_get_roundtrip(tmp_path):
    c = Corpus(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A", body="hi")
    c.add(n)
    got = c.get("topic:a")
    assert got.title == "A" and got.body == "hi" and got.uid == n.uid


def test_corpus_rebuilds_index_from_existing_files(tmp_path):
    Corpus(tmp_path).add(Node(id="topic:a", kind="topic", title="A"))
    fresh = Corpus(tmp_path)  # second corpus scans the same dir
    assert fresh.get("topic:a").title == "A"


def test_add_collision_same_id_different_uid(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A"))
    with pytest.raises(CollisionError):
        c.add(Node(id="topic:a", kind="topic", title="Other"))


def test_add_collision_duplicate_uid_at_different_id(tmp_path):
    c = Corpus(tmp_path)
    original = Node(id="topic:a", kind="topic", title="A")
    c.add(original)
    with pytest.raises(CollisionError):
        c.add(Node(id="topic:b", kind="topic", title="B", uid=original.uid))


def test_add_collision_deprecated_id_claim(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A"))
    with pytest.raises(CollisionError):
        c.add(Node(id="topic:b", kind="topic", title="B", deprecated_ids=["topic:a"]))


def test_add_overwrite_same_uid_same_id_ok(tmp_path):
    c = Corpus(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A")
    c.add(n)
    n.title = "A2"
    c.add(n)
    assert c.get("topic:a").title == "A2"


def test_get_unresolved_raises(tmp_path):
    with pytest.raises(RefError):
        Corpus(tmp_path).get("topic:ghost")


def test_delete_removes_and_is_live_id_only(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", deprecated_ids=["topic:old"]))
    with pytest.raises(RefError):
        c.delete("topic:old")  # deprecated id is not a live id
    c.delete("topic:a")
    with pytest.raises(RefError):
        c.get("topic:a")


def test_delete_leaves_dangling_inbound(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:t", kind="topic", title="T"))
    c.add(Node(id="topic:r", kind="topic", title="R", relations=[relates_to("topic:r", "topic:t")]))
    c.delete("topic:t")
    out = c.outbound("topic:r")
    assert len(out) == 1 and out[0].target_uid is None
    assert len(c.dangling()) == 1
    with pytest.raises(RefError):
        c.inbound("topic:t")  # target no longer resolves → input ref error


def test_neighbors_distinct_resolved(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")]))
    c.add(Node(id="topic:b", kind="topic", title="B"))
    c.add(Node(id="topic:c", kind="topic", title="C", relations=[relates_to("topic:c", "topic:a")]))
    names = sorted(n.id for n in c.neighbors("topic:a"))
    assert names == ["topic:b", "topic:c"]
