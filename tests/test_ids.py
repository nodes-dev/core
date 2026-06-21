from __future__ import annotations

import pytest

from nodes.kernel.errors import IdError
from nodes.kernel.ids import NodeId


def test_parse_simple():
    nid = NodeId.parse("topic:polycomb")
    assert nid.kind == "topic"
    assert nid.slug == "polycomb"
    assert str(nid) == "topic:polycomb"


def test_parse_curie_slug_keeps_inner_colons():
    nid = NodeId.parse("gene:HGNC:7296")
    assert nid.kind == "gene"
    assert nid.slug == "HGNC:7296"
    assert str(nid) == "gene:HGNC:7296"


def test_parse_rejects_missing_colon():
    with pytest.raises(IdError):
        NodeId.parse("nocolon")


def test_parse_rejects_bad_kind():
    with pytest.raises(IdError):
        NodeId.parse("Topic:polycomb")  # uppercase kind not allowed


def test_parse_rejects_empty_slug():
    with pytest.raises(IdError):
        NodeId.parse("topic:")
