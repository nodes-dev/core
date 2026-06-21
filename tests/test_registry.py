from __future__ import annotations

import pytest

from nodes.kernel.errors import FacetError, InvariantError, UnknownKindError
from nodes.kernel.node import Node
from nodes.kernel.registry import KindSpec, Registry


def _node(**facets) -> Node:
    return Node(id="topic:a", kind="topic", title="A", facets=facets)


def test_unknown_kind_raises():
    reg = Registry()
    with pytest.raises(UnknownKindError):
        reg.validate(_node())


def test_missing_required_facet_raises():
    reg = Registry()
    reg.register(KindSpec(name="topic", required_facets={"summary"}))
    with pytest.raises(FacetError):
        reg.validate(_node())


def test_unexpected_facet_raises():
    reg = Registry()
    reg.register(KindSpec(name="topic"))
    with pytest.raises(FacetError):
        reg.validate(_node(extra={"x": 1}))


def test_optional_facet_allowed():
    reg = Registry()
    reg.register(KindSpec(name="topic", optional_facets={"summary"}))
    reg.validate(_node(summary={"text": "hi"}))  # no raise


def test_invariant_runs():
    def must_have_title_a(node: Node) -> None:
        if node.title != "A":
            raise InvariantError("title must be A")

    reg = Registry()
    reg.register(KindSpec(name="topic", invariants=[must_have_title_a]))
    reg.validate(_node())  # passes
    with pytest.raises(InvariantError):
        reg.validate(Node(id="topic:b", kind="topic", title="B"))
