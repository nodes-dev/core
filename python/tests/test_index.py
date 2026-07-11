from __future__ import annotations

import pytest

from nodes.kernel.errors import CollisionError
from nodes.kernel.structural_index import Index
from nodes.kernel.node import Node
from nodes.kernel.node import Node as _Node
from nodes.kernel.relations import Relation, relates_to
from nodes.kernel.shapes import EDGES as _EDGES
from nodes.kernel.shapes import KEYS as _KEYS
from nodes.kernel.shapes import MEMBERSHIP as _MEMBERSHIP
from nodes.kernel.shapes import ORDER as _ORDER


def test_build_and_resolve_live_id():
    idx = Index.build([Node(id="topic:a", kind="topic", title="A")])
    uid = idx.id_to_uid["topic:a"]
    assert idx.resolve_uid("topic:a") == uid
    assert idx.resolve_uid("topic:missing") is None


def test_resolve_deprecated_id():
    a = Node(id="topic:new", kind="topic", title="A", deprecated_ids=["topic:old"])
    idx = Index.build([a])
    assert idx.resolve_uid("topic:old") == a.uid  # deprecated id resolves to A


def test_resolve_prefers_live_over_deprecated_map():
    # White-box: a live id always wins over a deprecated id. In a valid corpus a
    # ref appears in only one map; this asserts the lookup order directly.
    idx = Index()
    idx.id_to_uid["topic:x"] = "uid-live"
    idx.deprecated_to_uid["topic:x"] = "uid-dep"
    assert idx.resolve_uid("topic:x") == "uid-live"


def test_build_rejects_colliding_corpus():
    a = Node(id="topic:a", kind="topic", title="A")
    b = Node(id="topic:a", kind="topic", title="B")  # same id, different uid → corrupt corpus
    with pytest.raises(CollisionError):
        Index.build([a, b])


def test_build_rejects_duplicate_uid_same_id():
    a = Node(id="topic:a", kind="topic", title="A")
    duplicate = Node(id="topic:a", kind="topic", title="A copy", uid=a.uid)
    with pytest.raises(CollisionError):
        Index.build([a, duplicate])


def test_assert_addable_rejects_same_id_different_uid():
    idx = Index.build([Node(id="topic:a", kind="topic", title="A")])
    with pytest.raises(CollisionError):
        idx.assert_addable(Node(id="topic:a", kind="topic", title="Other"))


def test_assert_addable_rejects_same_uid_different_id():
    a = Node(id="topic:a", kind="topic", title="A")
    idx = Index.build([a])
    with pytest.raises(CollisionError):
        idx.assert_addable(Node(id="topic:b", kind="topic", title="B", uid=a.uid))


def test_assert_addable_rejects_deprecated_id_claim():
    idx = Index.build([Node(id="topic:a", kind="topic", title="A")])
    with pytest.raises(CollisionError):
        idx.assert_addable(Node(id="topic:b", kind="topic", title="B", deprecated_ids=["topic:a"]))


def test_assert_addable_allows_same_uid_same_id_overwrite():
    a = Node(id="topic:a", kind="topic", title="A")
    idx = Index.build([a])
    idx.assert_addable(Node(id="topic:a", kind="topic", title="A2", uid=a.uid))  # no raise


def test_upsert_replace_is_clean():
    a = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:x")])
    idx = Index.build([a])
    assert any(r.out_ref.ref == "topic:x" for r in idx.in_refs.get("topic:x", []))
    a2 = Node(id="topic:a", kind="topic", title="A", uid=a.uid,
              relations=[relates_to("topic:a", "topic:y")])
    idx.upsert(a2)
    # old outbound ref to topic:x is gone; new one to topic:y is present
    assert idx.in_refs.get("topic:x") in (None, [])
    assert any(r.out_ref.ref == "topic:y" for r in idx.in_refs.get("topic:y", []))


def test_remove_keeps_surviving_referrers_inbound():
    target = Node(id="topic:t", kind="topic", title="T")
    referrer = Node(id="topic:r", kind="topic", title="R",
                    relations=[relates_to("topic:r", "topic:t")])
    idx = Index.build([target, referrer])
    idx.remove(target.uid)
    # target's identity is gone...
    assert idx.resolve_uid("topic:t") is None
    assert target.uid not in idx.by_uid
    # ...but the referrer's inbound ref to topic:t persists (now dangling).
    rows = idx.in_refs.get("topic:t", [])
    assert any(r.source_uid == referrer.uid for r in rows)


def test_outbound_returns_source_relations_resolved():
    a = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")])
    b = Node(id="topic:b", kind="topic", title="B")
    idx = Index.build([a, b])
    edges = idx.outbound_edges(a.uid)
    assert len(edges) == 1
    assert edges[0].relation.target == "topic:b"
    assert edges[0].source_uid == a.uid and edges[0].target_uid == b.uid


def test_inbound_returns_target_relations_resolved():
    a = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")])
    b = Node(id="topic:b", kind="topic", title="B")
    idx = Index.build([a, b])
    edges = idx.inbound_edges(b.uid)
    assert len(edges) == 1
    assert edges[0].source_uid == a.uid and edges[0].target_uid == b.uid


def test_inbound_merges_across_deprecated_target_ref():
    # B is live as topic:new but still has deprecated topic:old;
    # A points at the stale ref topic:old.
    b = Node(id="topic:new", kind="topic", title="B", deprecated_ids=["topic:old"])
    a = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:old")])
    idx = Index.build([a, b])
    edges = idx.inbound_edges(b.uid)
    assert len(edges) == 1 and edges[0].source_uid == a.uid


def test_outbound_with_noncontainer_source_attributes_to_source_node():
    # The relation lives on B's file but its source is topic:a.
    rel = Relation(source="topic:a", predicate="cites", target="topic:c")
    a = Node(id="topic:a", kind="topic", title="A")
    b = Node(id="topic:b", kind="topic", title="B", relations=[rel])
    c = Node(id="topic:c", kind="topic", title="C")
    idx = Index.build([a, b, c])
    out_a = idx.outbound_edges(a.uid)
    assert len(out_a) == 1 and out_a[0].relation.target == "topic:c"
    assert idx.outbound_edges(b.uid) == []  # B is not the source of any relation


def test_membership_refs_not_in_graph_queries():
    g = Node(id="graph:g", kind="graph", title="G", facets={
        "membership": {"members": ["topic:x"]},
        "edges": {"edges": [{"source": "topic:x", "predicate": "to", "target": "topic:y"}]},
    })
    x = Node(id="topic:x", kind="topic", title="X")
    y = Node(id="topic:y", kind="topic", title="Y")
    idx = Index.build([g, x, y])
    # membership members/edges are tracked for rename but are not public graph edges
    assert idx.outbound_edges(g.uid) == []
    assert idx.inbound_edges(y.uid) == []
    assert idx.dangling_edges() == []


def test_dangling_lists_unresolved_targets():
    a = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:gone")])
    idx = Index.build([a])
    dangling = idx.dangling_edges()
    assert len(dangling) == 1
    assert dangling[0].relation.target == "topic:gone" and dangling[0].target_uid is None


def _graph_node() -> _Node:
    return _Node(
        id="graph:g", kind="graph", title="G",
        facets={
            _MEMBERSHIP: {"members": ["topic:a", "topic:b"]},
            _EDGES: {"edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}]},
        },
    )


def test_structure_refs_register_referrers_but_not_graph_edges():
    g = _graph_node()
    idx = Index.build([g])
    # membership members + edge endpoints are tracked as referrers (for rename):
    assert g.uid in {ir.source_uid for ir in idx.in_refs.get("topic:a", [])}
    assert g.uid in {ir.source_uid for ir in idx.in_refs.get("topic:b", [])}
    # ...but they are NOT relation-graph edges:
    assert idx.outbound_edges(g.uid) == []
    assert idx.dangling_edges() == []  # unresolved members are not dangling relation edges


def test_order_member_refs_are_tracked():
    lst = _Node(id="list:l", kind="list", title="L",
                facets={_MEMBERSHIP: {"members": ["topic:a"]}, _ORDER: {"order": ["topic:a"]}})
    idx = Index.build([lst])
    assert lst.uid in {ir.source_uid for ir in idx.in_refs.get("topic:a", [])}


def test_keys_value_refs_are_tracked():
    dct = _Node(id="dict:d", kind="dict", title="D",
                facets={_MEMBERSHIP: {"members": ["topic:a"]},
                        _KEYS: {"keys": {"k": "topic:a"}}})
    idx = Index.build([dct])
    roles = {ir.out_ref.role for ir in idx.in_refs.get("topic:a", []) if ir.source_uid == dct.uid}
    assert "keys_value" in roles


def _set_node(node_id: str, members: list[str], **extra) -> Node:
    return Node(id=node_id, kind="set", title=node_id, facets={_MEMBERSHIP: {"members": members}}, **extra)


def test_members_of_skips_dangling_and_resolves_deprecated():
    renamed = Node(id="note:renamed", kind="note", title="R", deprecated_ids=["note:old"])
    box = _set_node("set:box", ["note:old", "note:ghost"])
    idx = Index.build([renamed, box])
    assert idx.members_of(box.uid) == {renamed.uid}


def test_members_of_dedupes_duplicate_and_aliased_refs():
    renamed = Node(id="note:renamed", kind="note", title="R", deprecated_ids=["note:old"])
    box = _set_node("set:box", ["note:renamed", "note:old", "note:renamed"])
    idx = Index.build([renamed, box])
    assert idx.members_of(box.uid) == {renamed.uid}


def test_members_of_without_membership_facet_is_empty():
    plain = Node(id="note:plain", kind="note", title="P")
    idx = Index.build([plain])
    assert idx.members_of(plain.uid) == set()


def test_members_of_unknown_uid_raises_key_error():
    with pytest.raises(KeyError):
        Index().members_of("nope")


def test_containers_of_finds_live_and_deprecated_listings():
    renamed = Node(id="note:renamed", kind="note", title="R", deprecated_ids=["note:old"])
    by_live = _set_node("set:live", ["note:renamed"])
    by_dep = _set_node("set:dep", ["note:old"])
    idx = Index.build([renamed, by_live, by_dep])
    assert idx.containers_of(renamed.uid) == {by_live.uid, by_dep.uid}


def test_containers_of_uncontained_node_is_empty():
    plain = Node(id="note:plain", kind="note", title="P")
    idx = Index.build([plain])
    assert idx.containers_of(plain.uid) == set()


def test_membership_closure_walks_nesting_both_directions():
    leaf = Node(id="note:leaf", kind="note", title="L")
    box = _set_node("set:box", ["note:leaf"])
    crate = _set_node("set:crate", ["set:box"])
    idx = Index.build([leaf, box, crate])
    assert idx.membership_closure(crate.uid, "members") == {box.uid, leaf.uid}
    assert idx.membership_closure(leaf.uid, "containers") == {box.uid, crate.uid}


def test_membership_closure_cycles_terminate_and_exclude_start():
    a = _set_node("set:a", ["set:b"])
    b = _set_node("set:b", ["set:a"])
    selfie = _set_node("set:selfie", ["set:selfie"])
    idx = Index.build([a, b, selfie])
    assert idx.membership_closure(a.uid, "members") == {b.uid}
    assert idx.membership_closure(selfie.uid, "members") == set()
    assert idx.membership_closure(selfie.uid, "containers") == set()


def test_dangling_members_dedupes_per_container():
    box = _set_node("set:box", ["note:ghost", "note:ghost"])
    other = _set_node("set:other", ["note:ghost"])
    idx = Index.build([box, other])
    assert sorted(idx.dangling_members()) == sorted([(box.uid, "note:ghost"), (other.uid, "note:ghost")])


def test_dangling_members_empty_when_all_resolve():
    renamed = Node(id="note:renamed", kind="note", title="R", deprecated_ids=["note:old"])
    box = _set_node("set:box", ["note:old"])
    assert Index.build([renamed, box]).dangling_members() == []


def test_malformed_membership_facet_contributes_no_member_refs():
    # Parity fix pinned here: a string `members` value must NOT be iterated
    # character-by-character (TS guards with Array.isArray; Python must guard too,
    # or dangling_members() reports phantom single-character refs).
    weird = Node(id="note:weird", kind="note", title="W", facets={_MEMBERSHIP: {"members": "not-a-list"}})
    idx = Index.build([weird])
    assert idx.members_of(weird.uid) == set()
    assert idx.dangling_members() == []
