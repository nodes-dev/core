from __future__ import annotations

import pytest

from nodes.core.errors import FacetError, InvariantError
from nodes.core.node import Node
from nodes.core.registry import Registry
from nodes.core.shapes import EDGES, KEYS, MEMBERSHIP, ORDER, register_builtin_shapes


def _struct(kind: str, **facets) -> Node:
    return Node(id=f"{kind}:s", kind=kind, title="S", facets=facets)


def _edge(source: str, target: str) -> dict:
    return {"source": source, "predicate": "to", "target": target}


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    register_builtin_shapes(r)
    return r


def test_set_requires_membership_only_and_rejects_duplicates(reg):
    reg.validate(_struct("set", **{MEMBERSHIP: {"members": ["a:1", "a:2"]}}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("set", **{MEMBERSHIP: {"members": ["a:1", "a:1"]}}))


def test_set_rejects_form_facets(reg):
    # edges is not allowed on a set (form bundling is gone)
    with pytest.raises(FacetError):
        reg.validate(_struct("set", **{MEMBERSHIP: {"members": ["a:1"]}, EDGES: {"edges": []}}))


def test_list_requires_order_permutation(reg):
    reg.validate(_struct("list", **{MEMBERSHIP: {"members": ["a:1", "a:2"]},
                                    ORDER: {"order": ["a:2", "a:1"]}}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("list", **{MEMBERSHIP: {"members": ["a:1", "a:2"]},
                                        ORDER: {"order": ["a:1"]}}))  # not a permutation


def test_list_rejects_duplicate_members(reg):
    with pytest.raises(InvariantError):
        reg.validate(_struct("list", **{MEMBERSHIP: {"members": ["a:1", "a:1"]},
                                        ORDER: {"order": ["a:1"]}}))


def test_list_missing_order_facet_raises(reg):
    with pytest.raises(FacetError):
        reg.validate(_struct("list", **{MEMBERSHIP: {"members": ["a:1"]}}))


def test_dict_requires_key_values_are_members(reg):
    reg.validate(_struct("dict", **{MEMBERSHIP: {"members": ["a:1"]},
                                    KEYS: {"keys": {"k": "a:1"}}}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("dict", **{MEMBERSHIP: {"members": ["a:1"]},
                                        KEYS: {"keys": {"k": "a:2"}}}))  # value not a member


def test_graph_requires_edge_endpoints_are_members(reg):
    reg.validate(_struct("graph", **{MEMBERSHIP: {"members": ["a:1", "a:2"]},
                                     EDGES: {"edges": [_edge("a:1", "a:2")]}}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("graph", **{MEMBERSHIP: {"members": ["a:1"]},
                                         EDGES: {"edges": [_edge("a:1", "a:2")]}}))


def test_dag_rejects_cycle_allows_diamond(reg):
    diamond = {MEMBERSHIP: {"members": ["a:1", "a:2", "a:3", "a:4"]},
               EDGES: {"edges": [_edge("a:1", "a:2"), _edge("a:1", "a:3"),
                                 _edge("a:2", "a:4"), _edge("a:3", "a:4")]}}
    reg.validate(_struct("dag", **diamond))  # no raise
    cyclic = {MEMBERSHIP: {"members": ["a:1", "a:2"]},
              EDGES: {"edges": [_edge("a:1", "a:2"), _edge("a:2", "a:1")]}}
    with pytest.raises(InvariantError):
        reg.validate(_struct("dag", **cyclic))


def test_tree_rejects_multiple_parents(reg):
    multi = {MEMBERSHIP: {"members": ["a:1", "a:2", "a:3"]},
             EDGES: {"edges": [_edge("a:1", "a:3"), _edge("a:2", "a:3")]}}
    with pytest.raises(InvariantError):
        reg.validate(_struct("tree", **multi))


def test_tree_rejects_cycle(reg):
    # Each node has in-degree 1 so require_single_parent passes;
    # the cycle trips require_acyclic (which runs before require_single_parent).
    cyclic = {MEMBERSHIP: {"members": ["a:1", "a:2"]},
              EDGES: {"edges": [_edge("a:1", "a:2"), _edge("a:2", "a:1")]}}
    with pytest.raises(InvariantError):
        reg.validate(_struct("tree", **cyclic))


def test_missing_membership_facet_raises(reg):
    with pytest.raises(FacetError):
        reg.validate(_struct("graph", **{EDGES: {"edges": []}}))


def test_malformed_membership_raises_facet_error(reg):
    with pytest.raises(FacetError):
        reg.validate(_struct("set", **{MEMBERSHIP: {"members": "not-a-list"}}))
