from __future__ import annotations

from pydantic import BaseModel, Field

from nodes.kernel.errors import FacetError, InvariantError
from nodes.kernel.node import Node
from nodes.kernel.registry import KindSpec, Registry
from nodes.kernel.relations import Relation

MEMBERSHIP = "membership"


class Membership(BaseModel):
    shape: str
    members: list[str] | dict[str, str] = Field(default_factory=list)
    edges: list[Relation] = Field(default_factory=list)


def membership_of(node: Node) -> Membership:
    raw = node.facets.get(MEMBERSHIP)
    if raw is None:
        raise FacetError(f"{node.id}: missing '{MEMBERSHIP}' facet")
    return Membership.model_validate(raw)


def _member_ids(m: Membership) -> list[str]:
    return list(m.members.values()) if isinstance(m.members, dict) else list(m.members)


def require_unique_members(node: Node) -> None:
    ids = _member_ids(membership_of(node))
    if len(ids) != len(set(ids)):
        raise InvariantError(f"{node.id}: members must be unique")


def require_dict_keys(node: Node) -> None:
    if not isinstance(membership_of(node).members, dict):
        raise InvariantError(f"{node.id}: dict shape requires a key->ref mapping")


def require_acyclic(node: Node) -> None:
    m = membership_of(node)
    adj: dict[str, list[str]] = {}
    for e in m.edges:
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
    for e in membership_of(node).edges:
        parents[e.target] = parents.get(e.target, 0) + 1
    over = [t for t, c in parents.items() if c > 1]
    if over:
        raise InvariantError(f"{node.id}: nodes with multiple parents: {sorted(over)}")


def register_builtin_shapes(reg: Registry) -> None:
    reg.register(KindSpec(name="set", required_facets={MEMBERSHIP},
                          invariants=[require_unique_members]))
    reg.register(KindSpec(name="list", required_facets={MEMBERSHIP}))
    reg.register(KindSpec(name="dict", required_facets={MEMBERSHIP},
                          invariants=[require_dict_keys]))
    reg.register(KindSpec(name="graph", required_facets={MEMBERSHIP},
                          invariants=[require_unique_members]))
    reg.register(KindSpec(name="dag", required_facets={MEMBERSHIP},
                          invariants=[require_unique_members, require_acyclic]))
    reg.register(KindSpec(name="tree", required_facets={MEMBERSHIP},
                          invariants=[require_unique_members, require_acyclic, require_single_parent]))
