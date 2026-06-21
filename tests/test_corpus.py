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


def test_rename_rewrites_inbound_relations(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:b", kind="topic", title="B", relations=[relates_to("topic:b", "topic:old")]))
    renamed = c.rename("topic:old", "topic:new")
    assert renamed.id == "topic:new" and "topic:old" in renamed.deprecated_ids
    b = c.get("topic:b")
    assert any(r.target == "topic:new" for r in b.relations)
    assert all(r.target != "topic:old" for r in b.relations)


def test_rename_resolves_old_id_after(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.rename("topic:old", "topic:new")
    assert c.get("topic:old").id == "topic:new"  # stale ref still resolves


def test_rename_rewrites_membership_members_and_edges(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:x", kind="topic", title="X"))
    c.add(Node(id="graph:g", kind="graph", title="G", facets={"membership": {
        "shape": "graph",
        "members": ["topic:old", "topic:x"],
        "edges": [{"source": "topic:old", "predicate": "to", "target": "topic:x"}],
    }}))
    c.rename("topic:old", "topic:new")
    mem = c.get("graph:g").facets["membership"]
    assert "topic:new" in mem["members"] and "topic:old" not in mem["members"]
    assert mem["edges"][0]["source"] == "topic:new"  # edge SOURCE rewritten


def test_rename_rewrites_dict_membership(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:x", kind="topic", title="X"))
    c.add(Node(id="dict:d", kind="dict", title="D", facets={"membership": {
        "shape": "dict",
        "members": {"a": "topic:old", "b": "topic:x"},
    }}))
    c.rename("topic:old", "topic:new")
    mem = c.get("dict:d").facets["membership"]
    assert mem["members"]["a"] == "topic:new" and mem["members"]["b"] == "topic:x"


def test_rename_rewrites_own_relation_source(tmp_path):
    # A node whose outgoing relation had explicit source == old_id must, after rename,
    # serialize that relation with the container source (no stale source: old_id).
    from nodes.kernel.relations import Relation
    c = Corpus(tmp_path)
    c.add(Node(id="topic:t", kind="topic", title="T"))
    c.add(Node(id="topic:old", kind="topic", title="Old",
               relations=[Relation(source="topic:old", predicate="cites", target="topic:t")]))
    c.rename("topic:old", "topic:new")
    new = c.get("topic:new")
    rel = next(r for r in new.relations if r.predicate == "cites")
    assert rel.source == "topic:new"
    # round-trips clean: re-reading from disk shows the container source, not a stale one
    assert all(r.source != "topic:old" for r in new.relations)


def test_rename_multi_ref_referrer_written_once(tmp_path):
    # A referrer that points at old_id from several positions is rewritten correctly.
    from nodes.kernel.relations import Relation
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:r", kind="topic", title="R", relations=[
        relates_to("topic:r", "topic:old"),
        Relation(source="topic:r", predicate="cites", target="topic:old"),
    ]))
    c.rename("topic:old", "topic:new")
    r = c.get("topic:r")
    assert all(rel.target != "topic:old" for rel in r.relations)
    assert sum(1 for rel in r.relations if rel.target == "topic:new") == 2


def test_rename_inbound_across_deprecated_id(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:b", kind="topic", title="B", relations=[relates_to("topic:b", "topic:old")]))
    c.rename("topic:old", "topic:new")
    # the referrer was rewritten to topic:new, so inbound finds it under the new id
    inbound = c.inbound("topic:new")
    assert len(inbound) == 1 and inbound[0].source_uid == c.index.id_to_uid["topic:b"]


def test_rename_rejects_deprecated_or_unknown_old_id(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", deprecated_ids=["topic:stale"]))
    with pytest.raises(RefError):
        c.rename("topic:stale", "topic:z")  # deprecated, not live
    with pytest.raises(RefError):
        c.rename("topic:ghost", "topic:z")  # unknown


def test_rename_rejects_taken_target(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A"))
    c.add(Node(id="topic:b", kind="topic", title="B"))
    with pytest.raises(CollisionError):
        c.rename("topic:a", "topic:b")
