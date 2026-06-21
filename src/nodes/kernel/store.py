from __future__ import annotations

from pathlib import Path

from nodes.kernel.errors import CollisionError, RefError
from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown
from nodes.kernel.ids import NodeId
from nodes.kernel.node import Node
from nodes.kernel.shapes import MEMBERSHIP


class Store:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, node_id: str) -> Path:
        nid = NodeId.parse(node_id)
        return self.root / nid.kind / f"{nid.slug.replace(':', '__')}.md"

    def all_nodes(self) -> list[Node]:
        return [node_from_markdown(p.read_text(encoding="utf-8")) for p in sorted(self.root.rglob("*.md"))]

    def _id_owner_uid(self, node_id: str) -> str | None:
        for n in self.all_nodes():
            if n.id == node_id or node_id in n.deprecated_ids:
                return n.uid
        return None

    @staticmethod
    def _claimed_ids(node: Node) -> set[str]:
        return {node.id, *node.deprecated_ids}

    def _assert_no_identity_collision(self, node: Node) -> None:
        claimed = self._claimed_ids(node)
        for existing in self.all_nodes():
            same_live_identity = existing.id == node.id and existing.uid == node.uid
            if existing.uid == node.uid and existing.id != node.id:
                raise CollisionError(
                    f"uid {node.uid!r} already belongs to live id {existing.id!r}; use rename()"
                )
            if same_live_identity:
                continue
            overlap = claimed & self._claimed_ids(existing)
            if overlap:
                raise CollisionError(f"identity claims already in use: {sorted(overlap)}")

    def write(self, node: Node) -> Path:
        self._assert_no_identity_collision(node)
        path = self.path_for(node.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(node_to_markdown(node), encoding="utf-8")
        return path

    def resolve(self, ref: str) -> Node:
        """Resolve a ref by live id (file path) or active deprecated id (spec §3.5)."""
        path = self.path_for(ref)
        if path.is_file():
            return node_from_markdown(path.read_text(encoding="utf-8"))
        for n in self.all_nodes():
            if ref in n.deprecated_ids:
                return n
        raise RefError(f"no node resolves ref {ref!r}")

    def read(self, node_id: str) -> Node:
        return self.resolve(node_id)

    def delete(self, node_id: str) -> None:
        path = self.path_for(node_id)
        if not path.is_file():
            raise RefError(f"no node at {node_id!r}")
        path.unlink()

    def rename(self, old_id: str, new_id: str) -> Node:
        if self._id_owner_uid(new_id) is not None:
            raise CollisionError(f"target id {new_id!r} already in use")
        node = self.read(old_id)
        self.delete(old_id)
        node.id = new_id
        node.kind = NodeId.parse(new_id).kind
        if old_id not in node.deprecated_ids:
            node.deprecated_ids.append(old_id)
        self.write(node)
        self._rewrite_inbound(old_id, new_id)
        return node

    def _rewrite_inbound(self, old_id: str, new_id: str) -> None:
        for other in self.all_nodes():
            if other.id == new_id:
                continue
            changed = self._rewrite_relations(other, old_id, new_id)
            changed = self._rewrite_membership(other, old_id, new_id) or changed
            if changed:
                self.write(other)

    @staticmethod
    def _rewrite_relations(node: Node, old_id: str, new_id: str) -> bool:
        changed = False
        for rel in node.relations:
            if rel.target == old_id:
                rel.target = new_id
                changed = True
            if rel.source == old_id:
                rel.source = new_id
                changed = True
        return changed

    @staticmethod
    def _rewrite_membership(node: Node, old_id: str, new_id: str) -> bool:
        mem = node.facets.get(MEMBERSHIP)
        if not isinstance(mem, dict):
            return False
        changed = False
        members = mem.get("members")
        if isinstance(members, list):
            updated = [new_id if m == old_id else m for m in members]
            if updated != members:
                mem["members"] = updated
                changed = True
        elif isinstance(members, dict):
            for key, val in list(members.items()):
                if val == old_id:
                    members[key] = new_id
                    changed = True
        for edge in mem.get("edges", []) or []:
            if edge.get("source") == old_id:
                edge["source"] = new_id
                changed = True
            if edge.get("target") == old_id:
                edge["target"] = new_id
                changed = True
        return changed
