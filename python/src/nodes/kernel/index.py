from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
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
    membership: dict | None = None


@dataclass
class ResolvedEdge:
    relation: Relation
    source_uid: str | None
    target_uid: str | None


def _out_refs_from(relations: list[Relation], membership: object) -> list[OutRef]:
    refs: list[OutRef] = []
    for rel in relations:
        refs.append(OutRef(ref=rel.source, role="relation_source", relation=rel))
        refs.append(OutRef(ref=rel.target, role="relation_target", relation=rel))
    if isinstance(membership, dict):
        members = membership.get("members")
        if isinstance(members, list):
            for m in members:
                refs.append(OutRef(ref=m, role="membership_member"))
        elif isinstance(members, dict):
            for v in members.values():
                refs.append(OutRef(ref=v, role="membership_member"))
        for edge in membership.get("edges", []) or []:
            if isinstance(edge, dict):
                if "source" in edge:
                    refs.append(OutRef(ref=edge["source"], role="membership_edge_source"))
                if "target" in edge:
                    refs.append(OutRef(ref=edge["target"], role="membership_edge_target"))
    return refs


def _extract_out_refs(node: Node) -> list[OutRef]:
    return _out_refs_from(node.relations, node.facets.get(MEMBERSHIP))


def _validated_deprecated_ids(raw: object, entry_id: str) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError("structural snapshot: deprecated_ids must be a list of strings")

    deprecated_ids: list[str] = []
    seen: set[str] = set()
    for dep in raw:
        if not isinstance(dep, str):
            raise ValueError("structural snapshot: deprecated_ids must be a list of strings")
        if dep == entry_id:
            raise ValueError(
                f"structural snapshot: identity claim {dep!r} is both live and deprecated in one entry"
            )
        if dep in seen:
            raise ValueError(
                f"structural snapshot: duplicate deprecated identity claim {dep!r} in one entry"
            )
        seen.add(dep)
        deprecated_ids.append(dep)
    return deprecated_ids


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
        membership = node.facets.get(MEMBERSHIP)
        entry = IndexEntry(
            uid=node.uid,
            id=node.id,
            kind=node.kind,
            deprecated_ids=frozenset(node.deprecated_ids),
            out_refs=_extract_out_refs(node),
            membership=membership,
        )
        self.by_uid[node.uid] = entry
        self.id_to_uid[node.id] = node.uid
        for dep in node.deprecated_ids:
            self.deprecated_to_uid[dep] = node.uid
        for oref in entry.out_refs:
            self.in_refs.setdefault(oref.ref, []).append(InRef(source_uid=node.uid, out_ref=oref))

    def to_dict(self) -> dict:
        entries = []
        for entry in self.by_uid.values():
            relations = [
                {
                    "source": o.relation.source,
                    "predicate": o.relation.predicate,
                    "target": o.relation.target,
                    "directed": o.relation.directed,
                    "weight": o.relation.weight,
                    "attrs": deepcopy(o.relation.attrs),
                }
                for o in entry.out_refs
                if o.role == "relation_source" and o.relation is not None
            ]
            entries.append(
                {
                    "uid": entry.uid,
                    "id": entry.id,
                    "kind": entry.kind,
                    "deprecated_ids": sorted(entry.deprecated_ids),
                    "relations": relations,
                    "membership": deepcopy(entry.membership),
                }
            )
        return {"entries": entries}

    @classmethod
    def from_dict(cls, d: dict) -> "Index":
        idx = cls()
        for raw in d["entries"]:
            uid = raw["uid"]
            if uid in idx.by_uid:
                raise ValueError(f"structural snapshot: duplicate uid {uid!r}")
            deprecated_ids = _validated_deprecated_ids(raw["deprecated_ids"], raw["id"])
            relations = []
            for raw_relation in raw["relations"]:
                relation_data = dict(raw_relation)
                relation_data["attrs"] = deepcopy(relation_data.get("attrs", {}))
                relations.append(Relation(**relation_data))
            membership = deepcopy(raw["membership"])
            out_refs = _out_refs_from(relations, membership)
            entry = IndexEntry(
                uid=uid,
                id=raw["id"],
                kind=raw["kind"],
                deprecated_ids=frozenset(deprecated_ids),
                out_refs=out_refs,
                membership=membership,
            )
            for claim in (entry.id, *entry.deprecated_ids):
                owner = idx.resolve_uid(claim)
                if owner is not None:
                    raise ValueError(
                        f"structural snapshot: identity claim {claim!r} already in use by uid {owner!r}"
                    )
            idx.by_uid[uid] = entry
            idx.id_to_uid[entry.id] = uid
            for dep in entry.deprecated_ids:
                idx.deprecated_to_uid[dep] = uid
            for oref in out_refs:
                idx.in_refs.setdefault(oref.ref, []).append(InRef(source_uid=uid, out_ref=oref))
        return idx

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

    def _refs_for_uid(self, uid: str) -> list[str]:
        entry = self.by_uid[uid]
        return [entry.id, *sorted(entry.deprecated_ids)]

    def _resolve_edge(self, rel: Relation) -> ResolvedEdge:
        return ResolvedEdge(
            relation=rel,
            source_uid=self.resolve_uid(rel.source),
            target_uid=self.resolve_uid(rel.target),
        )

    def _relations_by_role(self, uid: str, role: Role) -> list[ResolvedEdge]:
        seen: set[int] = set()
        edges: list[ResolvedEdge] = []
        for ref in self._refs_for_uid(uid):
            for inref in self.in_refs.get(ref, []):
                oref = inref.out_ref
                if oref.role != role or oref.relation is None:
                    continue
                if id(oref.relation) in seen:
                    continue
                seen.add(id(oref.relation))
                edges.append(self._resolve_edge(oref.relation))
        return edges

    def outbound_edges(self, uid: str) -> list[ResolvedEdge]:
        return self._relations_by_role(uid, "relation_source")

    def inbound_edges(self, uid: str) -> list[ResolvedEdge]:
        return self._relations_by_role(uid, "relation_target")

    def dangling_edges(self) -> list[ResolvedEdge]:
        seen: set[int] = set()
        edges: list[ResolvedEdge] = []
        for entry in self.by_uid.values():
            for oref in entry.out_refs:
                if oref.role != "relation_target" or oref.relation is None:
                    continue
                if id(oref.relation) in seen:
                    continue
                if self.resolve_uid(oref.ref) is None:
                    seen.add(id(oref.relation))
                    edges.append(self._resolve_edge(oref.relation))
        return edges
