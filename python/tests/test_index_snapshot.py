from __future__ import annotations

import pytest

from nodes.kernel.index import Index
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to

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
    assert restored.outbound_edges(a_uid) == idx.outbound_edges(a_uid)
    assert len(restored.dangling_edges()) == len(idx.dangling_edges()) == 1


def test_empty_index_round_trips():
    idx = Index.build([])
    restored = Index.from_dict(idx.to_dict())
    assert restored.by_uid == {}


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


def test_extract_out_refs_still_works_after_refactor():
    # Guards the _out_refs_from refactor: existing build path unchanged.
    idx = Index.build(_corpus())
    g_uid = idx.id_to_uid["graph:g"]
    assert {o.role for o in idx.by_uid[g_uid].out_refs} >= {
        "membership_member",
        "membership_edge_source",
        "membership_edge_target",
    }
