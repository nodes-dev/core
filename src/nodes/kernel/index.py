from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from nodes.kernel.errors import CollisionError
from nodes.kernel.node import Node
from nodes.kernel.relations import Relation
from nodes.kernel.shapes import MEMBERSHIP

Role = Literal[
    "relation_source",
    "relation_target",
    "membership_member",
    "membership_edge_source",
    "membership_edge_target",
]


@dataclass
class OutRef:
    ref: str
    role: Role
    relation: Relation | None = None  # present iff role startswith "relation_"


@dataclass
class InRef:
    source_uid: str
    out_ref: OutRef


@dataclass
class IndexEntry:
    uid: str
    id: str
    kind: str
    deprecated_ids: frozenset[str]
    out_refs: list[OutRef]


@dataclass
class ResolvedEdge:
    relation: Relation
    source_uid: str | None
    target_uid: str | None


def _extract_out_refs(node: Node) -> list[OutRef]:
    refs: list[OutRef] = []
    for rel in node.relations:
        refs.append(OutRef(ref=rel.source, role="relation_source", relation=rel))
        refs.append(OutRef(ref=rel.target, role="relation_target", relation=rel))
    mem = node.facets.get(MEMBERSHIP)
    if isinstance(mem, dict):
        members = mem.get("members")
        if isinstance(members, list):
            for m in members:
                refs.append(OutRef(ref=m, role="membership_member"))
        elif isinstance(members, dict):
            for v in members.values():
                refs.append(OutRef(ref=v, role="membership_member"))
        for edge in mem.get("edges", []) or []:
            if isinstance(edge, dict):
                if "source" in edge:
                    refs.append(OutRef(ref=edge["source"], role="membership_edge_source"))
                if "target" in edge:
                    refs.append(OutRef(ref=edge["target"], role="membership_edge_target"))
    return refs


class Index:
    """In-memory structural index. Pure data; no file I/O."""

    def __init__(self) -> None:
        self.by_uid: dict[str, IndexEntry] = {}
        self.id_to_uid: dict[str, str] = {}
        self.deprecated_to_uid: dict[str, str] = {}
        self.in_refs: dict[str, list[InRef]] = {}

    @classmethod
    def build(cls, nodes: Iterable[Node]) -> "Index":
        idx = cls()
        for node in nodes:
            if node.uid in idx.by_uid:
                raise CollisionError(f"duplicate uid {node.uid!r} in corpus")
            idx.assert_addable(node)  # fail-early on a corrupt corpus (collision contract)
            idx.upsert(node)
        return idx

    def resolve_uid(self, ref: str) -> str | None:
        return self.id_to_uid.get(ref) or self.deprecated_to_uid.get(ref)

    def assert_addable(self, node: Node) -> None:
        existing = self.by_uid.get(node.uid)
        if existing is not None and existing.id != node.id:
            raise CollisionError(
                f"uid {node.uid!r} already belongs to live id {existing.id!r}; use rename()"
            )
        for claim in (node.id, *node.deprecated_ids):
            owner = self.resolve_uid(claim)
            if owner is not None and owner != node.uid:
                raise CollisionError(f"identity claim {claim!r} already in use by uid {owner!r}")

    def upsert(self, node: Node) -> None:
        if node.uid in self.by_uid:
            self._drop(node.uid)
        entry = IndexEntry(
            uid=node.uid,
            id=node.id,
            kind=node.kind,
            deprecated_ids=frozenset(node.deprecated_ids),
            out_refs=_extract_out_refs(node),
        )
        self.by_uid[node.uid] = entry
        self.id_to_uid[node.id] = node.uid
        for dep in node.deprecated_ids:
            self.deprecated_to_uid[dep] = node.uid
        for oref in entry.out_refs:
            self.in_refs.setdefault(oref.ref, []).append(InRef(source_uid=node.uid, out_ref=oref))

    def remove(self, uid: str) -> None:
        self._drop(uid)

    def _drop(self, uid: str) -> None:
        entry = self.by_uid.pop(uid, None)
        if entry is None:
            return
        if self.id_to_uid.get(entry.id) == uid:
            del self.id_to_uid[entry.id]
        for dep in entry.deprecated_ids:
            if self.deprecated_to_uid.get(dep) == uid:
                del self.deprecated_to_uid[dep]
        for ref, rows in list(self.in_refs.items()):
            kept = [r for r in rows if r.source_uid != uid]
            if kept:
                self.in_refs[ref] = kept
            else:
                del self.in_refs[ref]
