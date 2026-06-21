from __future__ import annotations

from pathlib import Path

from nodes.kernel.errors import RefError
from nodes.kernel.index import Index, ResolvedEdge
from nodes.kernel.node import Node
from nodes.kernel.shapes import MEMBERSHIP
from nodes.kernel.store import Store


def _rewrite_refs(node: Node, old: str, new: str) -> None:
    """Rewrite every position in `node` that holds `old` to `new` (in place)."""
    for rel in node.relations:
        if rel.source == old:
            rel.source = new
        if rel.target == old:
            rel.target = new
    mem = node.facets.get(MEMBERSHIP)
    if isinstance(mem, dict):
        members = mem.get("members")
        if isinstance(members, list):
            mem["members"] = [new if m == old else m for m in members]
        elif isinstance(members, dict):
            for key, val in list(members.items()):
                if val == old:
                    members[key] = new
        for edge in mem.get("edges", []) or []:
            if isinstance(edge, dict):
                if edge.get("source") == old:
                    edge["source"] = new
                if edge.get("target") == old:
                    edge["target"] = new


class Corpus:
    """Coordinator over a `Store` + an in-memory `Index`. The primary kernel API."""

    def __init__(self, root: Path) -> None:
        self.store = Store(root)
        self.index = Index.build(self.store.all_nodes())

    def add(self, node: Node) -> Node:
        self.index.assert_addable(node)
        self.store.write_file(node)
        self.index.upsert(node)
        return node

    def get(self, ref: str) -> Node:
        uid = self.index.resolve_uid(ref)
        if uid is None:
            raise RefError(f"no node resolves ref {ref!r}")
        return self.store.read_file(self.index.by_uid[uid].id)

    def resolve(self, ref: str) -> Node:
        return self.get(ref)

    def delete(self, node_id: str) -> None:
        uid = self.index.id_to_uid.get(node_id)
        if uid is None:
            raise RefError(f"no live node at {node_id!r}")
        self.store.delete_file(node_id)
        self.index.remove(uid)

    def all(self) -> list[Node]:
        return self.store.all_nodes()

    def _require_uid(self, ref: str) -> str:
        uid = self.index.resolve_uid(ref)
        if uid is None:
            raise RefError(f"no node resolves ref {ref!r}")
        return uid

    def outbound(self, ref: str) -> list[ResolvedEdge]:
        return self.index.outbound_edges(self._require_uid(ref))

    def inbound(self, ref: str) -> list[ResolvedEdge]:
        return self.index.inbound_edges(self._require_uid(ref))

    def dangling(self) -> list[ResolvedEdge]:
        return self.index.dangling_edges()

    def neighbors(self, ref: str) -> list[Node]:
        uid = self._require_uid(ref)
        neighbor_uids: set[str] = set()
        for edge in self.index.outbound_edges(uid):
            if edge.target_uid is not None:
                neighbor_uids.add(edge.target_uid)
        for edge in self.index.inbound_edges(uid):
            if edge.source_uid is not None:
                neighbor_uids.add(edge.source_uid)
        neighbor_uids.discard(uid)
        return [self.store.read_file(self.index.by_uid[u].id) for u in sorted(neighbor_uids)]
