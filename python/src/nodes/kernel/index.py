from __future__ import annotations

import math
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError as PydanticValidationError

from nodes.kernel.errors import CollisionError, IdError
from nodes.kernel.ids import NodeId
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

_STRUCTURAL_ENTRY_KEYS = frozenset({"uid", "id", "kind", "deprecated_ids", "relations", "membership"})


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


def _validated_membership(raw: object) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("structural snapshot: entry membership must be a dict or null")

    shape = raw.get("shape")
    if not isinstance(shape, str):
        raise ValueError("structural snapshot: membership shape must be a string")

    members = raw.get("members")
    if members is not None:
        if isinstance(members, list):
            if any(not isinstance(member, str) for member in members):
                raise ValueError("structural snapshot: membership members must be strings")
        elif isinstance(members, dict):
            if any(not isinstance(member, str) for member in members.values()):
                raise ValueError("structural snapshot: membership member values must be strings")
        else:
            raise ValueError("structural snapshot: membership members must be a list or dict")

    edges = raw.get("edges")
    if edges is not None:
        if not isinstance(edges, list):
            raise ValueError("structural snapshot: membership edges must be a list")
        for edge in edges:
            if not isinstance(edge, dict):
                raise ValueError("structural snapshot: membership edge must be a dict")
            if not isinstance(edge.get("source"), str):
                raise ValueError("structural snapshot: membership edge source must be a string")
            if not isinstance(edge.get("predicate"), str):
                raise ValueError("structural snapshot: membership edge predicate must be a string")
            if not isinstance(edge.get("target"), str):
                raise ValueError("structural snapshot: membership edge target must be a string")
            directed = edge.get("directed")
            if "directed" in edge and not isinstance(directed, bool):
                raise ValueError("structural snapshot: membership edge directed must be a bool")
            weight = edge.get("weight")
            if "weight" in edge and (
                isinstance(weight, bool) or not isinstance(weight, (int, float))
            ):
                raise ValueError("structural snapshot: membership edge weight must be numeric")
            attrs = edge.get("attrs")
            if "attrs" in edge and not isinstance(attrs, dict):
                raise ValueError("structural snapshot: membership edge attrs must be a dict")
            try:
                Relation(**edge)
            except (PydanticValidationError, TypeError) as exc:
                raise ValueError("structural snapshot: invalid membership edge") from exc

    return deepcopy(raw)


def _validate_snapshot_weight(raw: dict, label: str) -> None:
    if "weight" not in raw:
        return
    weight = raw["weight"]
    if (
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not math.isfinite(weight)
    ):
        raise ValueError(f"structural snapshot: {label} weight must be a finite number")


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
            relations = []
            for o in entry.out_refs:
                if o.role != "relation_source" or o.relation is None:
                    continue
                relation = {
                    "source": o.relation.source,
                    "predicate": o.relation.predicate,
                    "target": o.relation.target,
                    "directed": o.relation.directed,
                    "attrs": deepcopy(o.relation.attrs),
                }
                if o.relation.weight is not None:
                    relation["weight"] = o.relation.weight
                relations.append(relation)
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
        if not isinstance(d, dict):
            raise ValueError("structural snapshot: document must be a dict")
        if "entries" not in d:
            raise ValueError("structural snapshot: missing entries")
        entries_raw = d["entries"]
        if not isinstance(entries_raw, list):
            raise ValueError("structural snapshot: entries must be a list")
        idx = cls()
        for raw in entries_raw:
            if not isinstance(raw, dict):
                raise ValueError("structural snapshot: entry must be a dict")
            missing = _STRUCTURAL_ENTRY_KEYS - raw.keys()
            if missing:
                raise ValueError(f"structural snapshot: entry missing {sorted(missing)[0]}")
            uid = raw["uid"]
            entry_id = raw["id"]
            kind = raw["kind"]
            relations_raw = raw["relations"]
            membership_raw = raw["membership"]
            if not isinstance(uid, str):
                raise ValueError("structural snapshot: entry uid must be a string")
            if not isinstance(entry_id, str):
                raise ValueError("structural snapshot: entry id must be a string")
            if not isinstance(kind, str):
                raise ValueError("structural snapshot: entry kind must be a string")
            try:
                parsed_id = NodeId.parse(entry_id)
            except IdError as exc:
                raise ValueError("structural snapshot: entry id must be a valid node id") from exc
            if parsed_id.kind != kind:
                raise ValueError("structural snapshot: entry id kind must match entry kind")
            if not isinstance(relations_raw, list):
                raise ValueError("structural snapshot: entry relations must be a list")
            if uid in idx.by_uid:
                raise ValueError(f"structural snapshot: duplicate uid {uid!r}")
            deprecated_ids = _validated_deprecated_ids(raw["deprecated_ids"], entry_id)
            relations = []
            for raw_relation in relations_raw:
                if not isinstance(raw_relation, dict):
                    raise ValueError("structural snapshot: relation row must be a dict")
                _validate_snapshot_weight(raw_relation, "relation row")
                relation_data = dict(raw_relation)
                relation_data["attrs"] = deepcopy(relation_data.get("attrs", {}))
                try:
                    relations.append(Relation(**relation_data))
                except (PydanticValidationError, TypeError) as exc:
                    raise ValueError("structural snapshot: invalid relation row") from exc
            membership = _validated_membership(membership_raw)
            out_refs = _out_refs_from(relations, membership)
            entry = IndexEntry(
                uid=uid,
                id=entry_id,
                kind=kind,
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
