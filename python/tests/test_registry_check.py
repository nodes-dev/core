from __future__ import annotations

import pytest

from nodes.kernel.node import Node
from nodes.kernel.registry import KindSpec, Registry
from tests._fixtures_profile import SOURCE, register_fixtures_profile


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    register_fixtures_profile(r)
    return r


def _codes(violations) -> list[tuple[str, str]]:
    return [(v.code, v.detail) for v in violations]


def test_valid_node_yields_no_violations(reg):
    assert reg.check(Node(id="note:a", kind="note", title="A")) == []


def test_unknown_kind_single_violation(reg):
    vs = reg.check(Node(id="zzz:a", kind="zzz", title="A"))
    assert _codes(vs) == [("unknown-kind", "zzz")]
    assert "zzz:a" in vs[0].message


def test_missing_and_unexpected_collected_together():
    reg = Registry()
    reg.register(KindSpec(name="widget", required_facets={"a", "b"}))
    node = Node(id="widget:w", kind="widget", title="W", facets={"c": {}})
    assert _codes(reg.check(node)) == [
        ("facet-missing", "a"),
        ("facet-missing", "b"),
        ("facet-unexpected", "c"),
    ]


def test_invariants_skipped_when_presence_fails():
    def boom(node: Node) -> None:
        raise RuntimeError("must not run")

    reg = Registry()
    reg.register(KindSpec(name="widget", required_facets={"a"}, invariants=[boom]))
    node = Node(id="widget:w", kind="widget", title="W")
    assert _codes(reg.check(node)) == [("facet-missing", "a")]


def test_invariant_facet_error_becomes_facet_invalid(reg):
    node = Node(id="paper:p", kind="paper", title="P", facets={SOURCE: {"identifer": "10.1/x"}})
    assert _codes(reg.check(node)) == [("facet-invalid", "")]


def test_invariant_error_becomes_invariant_violated(reg):
    node = Node(id="paper:p", kind="paper", title="P", facets={SOURCE: {}})
    assert _codes(reg.check(node)) == [("invariant-violated", "")]


def test_non_kernel_invariant_exception_propagates():
    def buggy(node: Node) -> None:
        raise RuntimeError("programmer bug")

    reg = Registry()
    reg.register(KindSpec(name="widget", invariants=[buggy]))
    with pytest.raises(RuntimeError):
        reg.check(Node(id="widget:w", kind="widget", title="W"))


def test_validate_behavior_unchanged(reg):
    from nodes.kernel.errors import FacetError

    with pytest.raises(FacetError):
        reg.validate(Node(id="paper:p", kind="paper", title="P"))


def test_facet_names_sort_by_code_point(reg):
    # U+FF61 < U+1F600 by code point; UTF-16 code-unit order (as in a naive JS
    # sort) would reverse them. Pins the cross-language collation contract (§8.1).
    node = Node(id="note:n", kind="note", title="N", facets={"｡": {}, "\U0001f600": {}})
    assert _codes(reg.check(node)) == [
        ("facet-unexpected", "｡"),
        ("facet-unexpected", "\U0001f600"),
    ]
