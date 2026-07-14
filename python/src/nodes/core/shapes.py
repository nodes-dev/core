from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from nodes.core.errors import FacetError, InvariantError
from nodes.core.node import Node
from nodes.core.registry import KindSpec, Registry, ShapeSpec
from nodes.core.relations import Relation

_M = TypeVar("_M", bound=BaseModel)

MEMBERSHIP = "membership"
EDGES = "edges"
ORDER = "order"
KEYS = "keys"


class Membership(BaseModel):
    members: list[str] = Field(default_factory=list)


class Edges(BaseModel):
    edges: list[Relation] = Field(default_factory=list)


class Order(BaseModel):
    order: list[str] = Field(default_factory=list)


class Keys(BaseModel):
    keys: dict[str, str] = Field(default_factory=dict)


def _load(node: Node, name: str, model: type[_M]) -> _M:
    raw = node.facets.get(name)
    if raw is None:
        raise FacetError(f"{node.id}: missing {name!r} facet")
    try:
        return model.model_validate(raw)
    except PydanticValidationError as exc:
        raise FacetError(f"{node.id}: invalid {name!r} facet: {exc}") from exc


def membership_of(node: Node) -> Membership:
    return _load(node, MEMBERSHIP, Membership)


def edges_of(node: Node) -> Edges:
    return _load(node, EDGES, Edges)


def order_of(node: Node) -> Order:
    return _load(node, ORDER, Order)


def keys_of(node: Node) -> Keys:
    return _load(node, KEYS, Keys)


def require_unique_members(node: Node) -> None:
    members = membership_of(node).members
    if len(members) != len(set(members)):
        raise InvariantError(f"{node.id}: members must be unique")


def require_edge_endpoints_are_members(node: Node) -> None:
    members = set(membership_of(node).members)
    for e in edges_of(node).edges:
        if e.source not in members or e.target not in members:
            raise InvariantError(f"{node.id}: edge endpoints must be members")


def require_order_is_permutation(node: Node) -> None:
    members = membership_of(node).members
    order = order_of(node).order
    if len(order) != len(members) or set(order) != set(members):
        raise InvariantError(f"{node.id}: order must be a permutation of members")


def require_key_values_are_members(node: Node) -> None:
    members = set(membership_of(node).members)
    for value in keys_of(node).keys.values():
        if value not in members:
            raise InvariantError(f"{node.id}: key values must be members")


def require_acyclic(node: Node) -> None:
    adj: dict[str, list[str]] = {}
    for e in edges_of(node).edges:
        adj.setdefault(e.source, []).append(e.target)
    visiting, done = set(), set()

    def walk(n: str) -> None:
        if n in visiting:
            raise InvariantError(f"{node.id}: cycle detected at {n}")
        if n in done:
            return
        visiting.add(n)
        for nxt in adj.get(n, []):
            walk(nxt)
        visiting.discard(n)
        done.add(n)

    for start in list(adj):
        walk(start)


def require_single_parent(node: Node) -> None:
    parents: dict[str, int] = {}
    for e in edges_of(node).edges:
        parents[e.target] = parents.get(e.target, 0) + 1
    over = sorted(t for t, c in parents.items() if c > 1)
    if over:
        raise InvariantError(f"{node.id}: nodes with multiple parents: {over}")


def register_builtin_shapes(reg: Registry) -> None:
    reg.register_shape(ShapeSpec(name="set", required_facets={MEMBERSHIP},
                                 invariants=[require_unique_members]))
    reg.register_shape(ShapeSpec(name="list", required_facets={MEMBERSHIP, ORDER},
                                 invariants=[require_unique_members, require_order_is_permutation]))
    reg.register_shape(ShapeSpec(name="dict", required_facets={MEMBERSHIP, KEYS},
                                 invariants=[require_unique_members, require_key_values_are_members]))
    reg.register_shape(ShapeSpec(name="graph", required_facets={MEMBERSHIP, EDGES},
                                 invariants=[require_unique_members, require_edge_endpoints_are_members]))
    reg.register_shape(ShapeSpec(name="dag", required_facets={MEMBERSHIP, EDGES},
                                 invariants=[require_unique_members, require_edge_endpoints_are_members,
                                             require_acyclic]))
    reg.register_shape(ShapeSpec(name="tree", required_facets={MEMBERSHIP, EDGES},
                                 invariants=[require_unique_members, require_edge_endpoints_are_members,
                                             require_acyclic, require_single_parent]))
    for name in ("set", "list", "dict", "graph", "dag", "tree"):
        reg.register(KindSpec(name=name, shape=name))
