from __future__ import annotations

import pytest

from nodes.kernel.errors import ValidationError
from nodes.kernel.node import Node, new_uid


def test_node_minimal_defaults():
    n = Node(id="topic:polycomb", kind="topic", title="Polycomb")
    assert n.body == ""
    assert n.metadata.version == 1
    assert n.relations == [] and n.facets == {}
    assert len(n.uid) == 32  # uuid4 hex


def test_uid_is_unique_per_node():
    a = Node(id="topic:a", kind="topic", title="A")
    b = Node(id="topic:b", kind="topic", title="B")
    assert a.uid != b.uid


def test_explicit_uid_preserved():
    fixed = new_uid()
    n = Node(id="topic:a", kind="topic", title="A", uid=fixed)
    assert n.uid == fixed


def test_id_kind_mismatch_rejected():
    with pytest.raises(ValidationError):
        Node(id="topic:a", kind="note", title="Mismatch")


def test_id_must_be_wellformed():
    with pytest.raises(ValidationError):
        Node(id="nocolon", kind="nocolon", title="Bad")
