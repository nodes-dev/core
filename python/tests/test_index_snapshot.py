from __future__ import annotations

import pytest

from nodes.kernel.index import Index
from nodes.kernel.node import Node
from nodes.kernel.relations import Relation, relates_to

# Reuse the equivalence normalizer that already pins structural state.
from tests.test_index_rebuild_equivalence import _normalize


def _corpus() -> list[Node]:
    return [
        Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")]),
        Node(id="topic:b", kind="topic", title="B"),
        Node(
            id="graph:g",
            kind="graph",
            title="G",
            facets={
                "membership": {
                    "shape": "graph",
                    "members": ["topic:a", "topic:b"],
                    "edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}],
                }
            },
        ),
    ]


def test_round_trip_equals_fresh_build():
    idx = Index.build(_corpus())
    restored = Index.from_dict(idx.to_dict())
    assert _normalize(restored) == _normalize(idx)


def test_round_trip_preserves_inbound_and_dangling_dedup():
    # One relation yields a source+target OutRef sharing a single Relation instance;
    # ensure outbound/dangling queries match a fresh build after a round trip (the
    # shared-Relation identity that in_refs dedup relies on must survive from_dict).
    nodes = [
        Node(
            id="topic:a",
            kind="topic",
            title="A",
            relations=[relates_to("topic:a", "topic:missing")],
        ),
    ]
    idx = Index.build(nodes)
    restored = Index.from_dict(idx.to_dict())
    a_uid = restored.id_to_uid["topic:a"]
    source_ref = next(o for o in restored.by_uid[a_uid].out_refs if o.role == "relation_source")
    target_ref = next(o for o in restored.by_uid[a_uid].out_refs if o.role == "relation_target")
    assert source_ref.relation is target_ref.relation
    assert restored.outbound_edges(a_uid) == idx.outbound_edges(a_uid)
    assert len(restored.dangling_edges()) == len(idx.dangling_edges()) == 1


def test_empty_index_round_trips():
    idx = Index.build([])
    restored = Index.from_dict(idx.to_dict())
    assert restored.by_uid == {}


def _single_entry_snapshot() -> dict:
    return Index.build([Node(id="topic:a", kind="topic", title="A")]).to_dict()


def test_from_dict_rejects_non_dict_snapshot():
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict([])


def test_from_dict_rejects_entries_not_list():
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict({"entries": {}})


def test_from_dict_rejects_entry_not_dict():
    d = {"entries": ["not an entry"]}
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


@pytest.mark.parametrize("field", ("uid", "id", "kind", "deprecated_ids", "relations", "membership"))
def test_from_dict_rejects_missing_entry_keys(field):
    d = _single_entry_snapshot()
    del d["entries"][0][field]
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


@pytest.mark.parametrize("field", ("uid", "id", "kind"))
def test_from_dict_rejects_non_string_entry_fields(field):
    d = _single_entry_snapshot()
    d["entries"][0][field] = 123
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


def test_from_dict_rejects_relations_not_list():
    d = _single_entry_snapshot()
    d["entries"][0]["relations"] = {}
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


def test_from_dict_rejects_relation_row_not_dict():
    d = _single_entry_snapshot()
    d["entries"][0]["relations"] = ["not a relation"]
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


def test_from_dict_rejects_invalid_relation_schema():
    d = _single_entry_snapshot()
    d["entries"][0]["relations"] = [{"source": "topic:a", "predicate": "relatesTo"}]
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


def test_from_dict_rejects_invalid_membership_container():
    d = _single_entry_snapshot()
    d["entries"][0]["membership"] = []
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


@pytest.mark.parametrize(
    "members",
    [
        "topic:a",
        ["topic:a", 123],
        {"a": "topic:a", "b": 123},
    ],
)
def test_from_dict_rejects_invalid_membership_members(members):
    d = _single_entry_snapshot()
    d["entries"][0]["membership"] = {"shape": "graph", "members": members}
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


@pytest.mark.parametrize(
    "edges",
    [
        {"source": "topic:a", "target": "topic:b"},
        ["not an edge"],
        [{"source": 123, "predicate": "to", "target": "topic:b"}],
        [{"source": "topic:a", "predicate": "to", "target": 123}],
    ],
)
def test_from_dict_rejects_invalid_membership_edges(edges):
    d = _single_entry_snapshot()
    d["entries"][0]["membership"] = {"shape": "graph", "edges": edges}
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


def test_from_dict_rejects_membership_missing_shape():
    d = _single_entry_snapshot()
    d["entries"][0]["membership"] = {"members": []}
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


@pytest.mark.parametrize(
    "edge",
    [
        {"predicate": "to", "target": "topic:b"},
        {"source": "topic:a", "target": "topic:b"},
        {"source": None, "predicate": "to", "target": "topic:b"},
        {"source": "topic:a", "predicate": 123, "target": "topic:b"},
        {"source": "topic:a", "predicate": "to", "target": "topic:b", "directed": "yes"},
        {"source": "topic:a", "predicate": "to", "target": "topic:b", "weight": True},
        {"source": "topic:a", "predicate": "to", "target": "topic:b", "attrs": []},
    ],
)
def test_from_dict_rejects_invalid_membership_edge_schema(edge):
    d = _single_entry_snapshot()
    d["entries"][0]["membership"] = {"shape": "graph", "edges": [edge]}
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


def test_from_dict_rejects_duplicate_uid():
    idx = Index.build([Node(id="topic:a", kind="topic", title="A")])
    d = idx.to_dict()
    d["entries"].append(dict(d["entries"][0]))  # duplicate uid
    with pytest.raises(ValueError):
        Index.from_dict(d)


def test_from_dict_rejects_duplicate_live_id():
    idx = Index.build(
        [
            Node(id="topic:a", kind="topic", title="A"),
            Node(id="topic:b", kind="topic", title="B"),
        ]
    )
    d = idx.to_dict()
    d["entries"][1]["id"] = d["entries"][0]["id"]
    with pytest.raises(ValueError):
        Index.from_dict(d)


def test_from_dict_rejects_deprecated_id_collision():
    idx = Index.build(
        [
            Node(id="topic:a", kind="topic", title="A"),
            Node(id="topic:b", kind="topic", title="B"),
        ]
    )
    d = idx.to_dict()
    d["entries"][1]["deprecated_ids"] = [d["entries"][0]["id"]]
    with pytest.raises(ValueError):
        Index.from_dict(d)


@pytest.mark.parametrize("deprecated_ids", ["topic:old", ["topic:old", 1]])
def test_from_dict_rejects_invalid_deprecated_ids(deprecated_ids):
    idx = Index.build([Node(id="topic:a", kind="topic", title="A")])
    d = idx.to_dict()
    d["entries"][0]["deprecated_ids"] = deprecated_ids
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


@pytest.mark.parametrize("deprecated_ids", [["topic:a"], ["topic:old", "topic:old"]])
def test_from_dict_rejects_same_entry_identity_collisions(deprecated_ids):
    idx = Index.build([Node(id="topic:a", kind="topic", title="A")])
    d = idx.to_dict()
    d["entries"][0]["deprecated_ids"] = deprecated_ids
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


def test_to_dict_deep_copies_relation_attrs_and_membership():
    idx = Index.build(
        [
            Node(
                id="topic:a",
                kind="topic",
                title="A",
                relations=[
                    Relation(
                        source="topic:a",
                        predicate="relatesTo",
                        target="topic:b",
                        attrs={"meta": {"score": 1}},
                    )
                ],
                facets={
                    "membership": {
                        "shape": "graph",
                        "members": ["topic:b"],
                        "edges": [
                            {
                                "source": "topic:a",
                                "predicate": "to",
                                "target": "topic:b",
                                "attrs": {"label": "old"},
                            }
                        ],
                    }
                },
            )
        ]
    )

    d = idx.to_dict()
    d["entries"][0]["relations"][0]["attrs"]["meta"]["score"] = 2
    d["entries"][0]["membership"]["edges"][0]["attrs"]["label"] = "new"

    entry = next(iter(idx.by_uid.values()))
    relation = next(o.relation for o in entry.out_refs if o.role == "relation_source")
    assert relation is not None
    assert relation.attrs["meta"]["score"] == 1
    assert entry.membership is not None
    assert entry.membership["edges"][0]["attrs"]["label"] == "old"


def test_from_dict_deep_copies_relation_attrs_and_membership():
    d = Index.build(
        [
            Node(
                id="topic:a",
                kind="topic",
                title="A",
                relations=[
                    Relation(
                        source="topic:a",
                        predicate="relatesTo",
                        target="topic:b",
                        attrs={"meta": {"score": 1}},
                    )
                ],
                facets={
                    "membership": {
                        "shape": "graph",
                        "members": ["topic:b"],
                        "edges": [
                            {
                                "source": "topic:a",
                                "predicate": "to",
                                "target": "topic:b",
                                "attrs": {"label": "old"},
                            }
                        ],
                    }
                },
            )
        ]
    ).to_dict()

    restored = Index.from_dict(d)
    d["entries"][0]["relations"][0]["attrs"]["meta"]["score"] = 2
    d["entries"][0]["membership"]["edges"][0]["attrs"]["label"] = "new"

    entry = next(iter(restored.by_uid.values()))
    relation = next(o.relation for o in entry.out_refs if o.role == "relation_source")
    assert relation is not None
    assert relation.attrs["meta"]["score"] == 1
    assert entry.membership is not None
    assert entry.membership["edges"][0]["attrs"]["label"] == "old"


def test_extract_out_refs_still_works_after_refactor():
    # Guards the _out_refs_from refactor: existing build path unchanged.
    idx = Index.build(_corpus())
    g_uid = idx.id_to_uid["graph:g"]
    assert {o.role for o in idx.by_uid[g_uid].out_refs} >= {
        "membership_member",
        "membership_edge_source",
        "membership_edge_target",
    }
