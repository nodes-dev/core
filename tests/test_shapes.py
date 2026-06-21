from __future__ import annotations

import pytest

from nodes.kernel.errors import InvariantError
from nodes.kernel.node import Node
from nodes.kernel.registry import Registry
from nodes.kernel.shapes import MEMBERSHIP, register_builtin_shapes


def _struct(kind: str, membership: dict) -> Node:
    return Node(id=f"{kind}:s", kind=kind, title="S", facets={MEMBERSHIP: membership})


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    register_builtin_shapes(r)
    return r


def test_set_rejects_duplicates(reg):
    reg.validate(_struct("set", {"shape": "set", "members": ["a:1", "a:2"]}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("set", {"shape": "set", "members": ["a:1", "a:1"]}))


def test_list_allows_duplicates(reg):
    reg.validate(_struct("list", {"shape": "list", "members": ["a:1", "a:1"]}))  # no raise


def test_dict_requires_mapping(reg):
    reg.validate(_struct("dict", {"shape": "dict", "members": {"k": "a:1"}}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("dict", {"shape": "dict", "members": ["a:1"]}))


def test_dag_rejects_cycle(reg):
    acyclic = {"shape": "dag", "members": ["a:1", "a:2"],
               "edges": [{"source": "a:1", "predicate": "to", "target": "a:2"}]}
    reg.validate(_struct("dag", acyclic))
    cyclic = {"shape": "dag", "members": ["a:1", "a:2"],
              "edges": [{"source": "a:1", "predicate": "to", "target": "a:2"},
                        {"source": "a:2", "predicate": "to", "target": "a:1"}]}
    with pytest.raises(InvariantError):
        reg.validate(_struct("dag", cyclic))


def test_tree_rejects_multiple_parents(reg):
    multi = {"shape": "tree", "members": ["a:1", "a:2", "a:3"],
             "edges": [{"source": "a:1", "predicate": "to", "target": "a:3"},
                       {"source": "a:2", "predicate": "to", "target": "a:3"}]}
    with pytest.raises(InvariantError):
        reg.validate(_struct("tree", multi))
