from __future__ import annotations

import pytest

from nodes.kernel.errors import FacetError, InvariantError, UnknownKindError, ValidationError
from nodes.kernel.node import Node
from nodes.kernel.registry import KindSpec, Registry, ShapeSpec


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


def _flag(box: list[str], tag: str):
    def inv(node: Node) -> None:
        box.append(tag)
    return inv


def test_register_shape_rejects_duplicate():
    reg = Registry()
    reg.register_shape(ShapeSpec(name="graph", required_facets={"membership"}))
    with pytest.raises(ValidationError):
        reg.register_shape(ShapeSpec(name="graph"))


def test_register_rejects_duplicate_kind():
    reg = Registry()
    reg.register(KindSpec(name="topic"))
    with pytest.raises(ValidationError):
        reg.register(KindSpec(name="topic"))


def test_register_rejects_unknown_shape():
    reg = Registry()
    with pytest.raises(UnknownKindError):
        reg.register(KindSpec(name="mindmap", shape="graph"))


def test_shape_and_kind_may_share_a_name():
    reg = Registry()
    reg.register_shape(ShapeSpec(name="graph", required_facets={"membership"}))
    reg.register(KindSpec(name="graph", shape="graph"))  # separate namespaces: no raise
    assert reg.is_shape("graph") and reg.is_registered("graph")


def test_validate_composes_shape_and_kind_facets():
    reg = Registry()
    reg.register_shape(ShapeSpec(name="graph", required_facets={"membership"}))
    reg.register(KindSpec(name="mindmap", shape="graph", required_facets={"scene"}))
    node = Node(id="mindmap:m", kind="mindmap", title="M",
                facets={"membership": {"members": []}, "scene": {"x": 1}})
    reg.validate(node)  # both shape + kind required facets present: no raise
    missing_scene = Node(id="mindmap:n", kind="mindmap", title="N",
                         facets={"membership": {"members": []}})
    with pytest.raises(FacetError):
        reg.validate(missing_scene)


def test_validate_runs_shape_invariants_before_kind_invariants():
    order: list[str] = []
    reg = Registry()
    reg.register_shape(ShapeSpec(name="graph", required_facets={"membership"},
                                 invariants=[_flag(order, "shape")]))
    reg.register(KindSpec(name="mindmap", shape="graph", invariants=[_flag(order, "kind")]))
    reg.validate(Node(id="mindmap:m", kind="mindmap", title="M",
                      facets={"membership": {"members": []}}))
    assert order == ["shape", "kind"]
