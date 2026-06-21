from __future__ import annotations

import pytest

from nodes.kernel.errors import CollisionError, RefError
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to
from nodes.kernel.store import Store


def test_write_read_roundtrip(tmp_path):
    store = Store(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A", body="hi")
    store.write(n)
    got = store.read("topic:a")
    assert got.title == "A" and got.body == "hi" and got.uid == n.uid


def test_collision_on_new_id(tmp_path):
    store = Store(tmp_path)
    store.write(Node(id="topic:a", kind="topic", title="A"))
    with pytest.raises(CollisionError):
        store.write(Node(id="topic:a", kind="topic", title="Other"))  # different uid, same id


def test_collision_on_duplicate_uid_at_different_id(tmp_path):
    store = Store(tmp_path)
    original = Node(id="topic:a", kind="topic", title="A")
    store.write(original)
    with pytest.raises(CollisionError):
        store.write(Node(id="topic:b", kind="topic", title="B", uid=original.uid))


def test_collision_on_deprecated_id_claim(tmp_path):
    store = Store(tmp_path)
    store.write(Node(id="topic:a", kind="topic", title="A"))
    with pytest.raises(CollisionError):
        store.write(Node(id="topic:b", kind="topic", title="B", deprecated_ids=["topic:a"]))


def test_overwrite_same_uid_ok(tmp_path):
    store = Store(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A")
    store.write(n)
    n.title = "A2"
    store.write(n)  # same uid → allowed
    assert store.read("topic:a").title == "A2"


def test_read_missing_raises(tmp_path):
    with pytest.raises(RefError):
        Store(tmp_path).read("topic:ghost")


def test_rename_rewrites_inbound_refs(tmp_path):
    store = Store(tmp_path)
    store.write(Node(id="topic:old", kind="topic", title="Old"))
    store.write(Node(id="topic:b", kind="topic", title="B",
                     relations=[relates_to("topic:b", "topic:old")]))
    renamed = store.rename("topic:old", "topic:new")
    assert renamed.id == "topic:new"
    assert "topic:old" in renamed.deprecated_ids
    b = store.read("topic:b")
    assert relates_to("topic:b", "topic:new") in b.relations
    assert all(r.target != "topic:old" for r in b.relations)


def test_resolve_old_id_after_rename(tmp_path):
    store = Store(tmp_path)
    store.write(Node(id="topic:old", kind="topic", title="Old"))
    store.rename("topic:old", "topic:new")
    assert store.resolve("topic:old").id == "topic:new"
    assert store.read("topic:old").id == "topic:new"  # stale ref survives


def test_rename_rewrites_membership_refs(tmp_path):
    store = Store(tmp_path)
    store.write(Node(id="topic:old", kind="topic", title="Old"))
    store.write(Node(id="topic:x", kind="topic", title="X"))
    store.write(Node(id="graph:g", kind="graph", title="G", facets={"membership": {
        "shape": "graph",
        "members": ["topic:old", "topic:x"],
        "edges": [{"source": "topic:old", "predicate": "to", "target": "topic:x"}],
    }}))
    store.rename("topic:old", "topic:new")
    mem = store.read("graph:g").facets["membership"]
    assert "topic:new" in mem["members"] and "topic:old" not in mem["members"]
    assert mem["edges"][0]["source"] == "topic:new"
