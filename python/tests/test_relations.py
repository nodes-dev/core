from __future__ import annotations

import pytest

from nodes.core.errors import RefError
from nodes.core.relations import RELATES_TO, Relation, relates_to, tag_to_relation


def test_node_relation_roundtrip_drops_source():
    rel = Relation(source="gene:PHF19", predicate="interacts_with", target="gene:EZH2")
    ser = rel.to_serialized("gene:PHF19")
    assert ser == {"predicate": "interacts_with", "target": "gene:EZH2"}
    back = Relation.from_serialized(ser, container_id="gene:PHF19")
    assert back == rel


def test_graph_edge_keeps_both_endpoints():
    edge = Relation(source="thought:a", predicate="relatesTo", target="thought:b")
    ser = edge.to_serialized("graph:mymap")  # container is the structure, not an endpoint
    assert ser == {"source": "thought:a", "predicate": "relatesTo", "target": "thought:b"}


def test_serialized_includes_non_default_attrs():
    rel = Relation(source="a:x", predicate="cites", target="b:y", weight=0.5, attrs={"note": "n"})
    ser = rel.to_serialized("a:x")
    assert ser == {"predicate": "cites", "target": "b:y", "weight": 0.5, "attrs": {"note": "n"}}


def test_relates_to_sugar():
    rel = relates_to("topic:a", "topic:b")
    assert rel.predicate == RELATES_TO
    assert rel.source == "topic:a" and rel.target == "topic:b"


def test_tag_resolves_via_alias_map():
    rel = tag_to_relation("thought:a", "#biology", {"biology": "topic:biology"})
    assert rel == relates_to("thought:a", "topic:biology")


def test_tag_unresolved_raises():
    with pytest.raises(RefError):
        tag_to_relation("thought:a", "#missing", {})
