from __future__ import annotations

from pathlib import Path

from nodes.kernel.errors import CollisionError, EmbedderRequiredError, RefError
from nodes.kernel.frontmatter import node_from_markdown
from nodes.kernel.ids import NodeId
from nodes.kernel.index import Index, ResolvedEdge
from nodes.kernel.node import Node
from nodes.kernel.registry import Registry
from nodes.kernel.search import SearchHit, SearchIndex
from nodes.kernel.shapes import MEMBERSHIP
from nodes.kernel.similarity import Embedder, SimilarHit, Vector, VectorCache, VectorIndex
from nodes.kernel.snapshot import (
    ManifestEntry,
    Snapshot,
    hash_bytes,
    iter_corpus_files,
    load_snapshot,
    write_snapshot,
)
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

    def __init__(self, root: Path, registry: Registry | None = None, embedder: Embedder | None = None) -> None:
        self.store = Store(root)
        self.registry = registry
        self.embedder = embedder
        self.vector_cache: VectorCache | None = VectorCache(root) if embedder is not None else None
        self.manifest: dict[str, ManifestEntry] = {}
        namespace = embedder.cache_namespace if embedder is not None else None
        snap = load_snapshot(self.store.root, namespace)
        if snap is None:
            self._full_rebuild()
        else:
            self._reconcile(snap)

    def _rel_path(self, node_id: str) -> str:
        return self.store.path_for(node_id).relative_to(self.store.root).as_posix()

    def _full_rebuild(self) -> None:
        nodes: list[Node] = []
        manifest: dict[str, ManifestEntry] = {}
        for f in iter_corpus_files(self.store.root):
            node = node_from_markdown(f.data.decode("utf-8"))
            nodes.append(node)
            manifest[f.path] = ManifestEntry(path=f.path, sha256=f.sha256, uid=node.uid)
        self.index = Index.build(nodes)
        self.search_index = SearchIndex.build(nodes)
        if self.embedder is not None:
            assert self.vector_cache is not None
            self.vector_index: VectorIndex | None = VectorIndex.build(nodes, self.embedder, self.vector_cache)
        else:
            self.vector_index = None
        self.manifest = manifest

    def _reconcile(self, snap: Snapshot) -> None:
        self.index = snap.index
        self.search_index = snap.search_index
        self.vector_index = snap.vector_index
        old = {m.path: m for m in snap.manifest}
        new_manifest: dict[str, ManifestEntry] = {}
        changed: list[tuple[str, str, Node]] = []
        drops: list[str] = []
        current: set[str] = set()
        for f in iter_corpus_files(self.store.root):
            current.add(f.path)
            prev = old.get(f.path)
            if prev is not None and prev.sha256 == f.sha256:
                new_manifest[f.path] = prev
                continue
            if prev is not None:
                drops.append(prev.uid)
            changed.append((f.path, f.sha256, node_from_markdown(f.data.decode("utf-8"))))
        for path, m in old.items():
            if path not in current:
                drops.append(m.uid)
        for uid in drops:
            self.index.remove(uid)
            self.search_index.remove(uid)
            if self.vector_index is not None:
                self.vector_index.remove(uid)
        for path, sha, node in changed:
            if node.uid in self.index.by_uid:
                raise CollisionError(f"duplicate uid {node.uid!r} in corpus")
            self.index.assert_addable(node)
            prepared = None
            if self.vector_index is not None:
                assert self.embedder is not None and self.vector_cache is not None
                prepared = self.vector_index.prepare(node, self.embedder, self.vector_cache)
            self.index.upsert(node)
            self.search_index.upsert(node)
            if self.vector_index is not None and prepared is not None:
                self.vector_index.commit(node, prepared)
            new_manifest[path] = ManifestEntry(path=path, sha256=sha, uid=node.uid)
        self.manifest = new_manifest

    def flush_index(self) -> None:
        manifest = sorted(self.manifest.values(), key=lambda m: m.path)
        write_snapshot(self.store.root, manifest, self.index, self.search_index, self.vector_index)

    def add(self, node: Node) -> Node:
        if self.registry is not None:
            self.registry.validate(node)
        self.index.assert_addable(node)
        prepared = None
        if self.vector_index is not None:
            assert self.embedder is not None and self.vector_cache is not None
            prepared = self.vector_index.prepare(node, self.embedder, self.vector_cache)
        path = self.store.write_file(node)
        self.index.upsert(node)
        self.search_index.upsert(node)
        if self.vector_index is not None and prepared is not None:
            self.vector_index.commit(node, prepared)
        rel_path = path.relative_to(self.store.root).as_posix()
        self.manifest[rel_path] = ManifestEntry(path=rel_path, sha256=hash_bytes(path.read_bytes()), uid=node.uid)
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
        self.search_index.remove(uid)
        if self.vector_index is not None:
            self.vector_index.remove(uid)

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

    def search(self, query: str, limit: int | None = None) -> list[SearchHit]:
        return self.search_index.search(query, limit)

    def similar(self, ref: str, k: int | None = None) -> list[SimilarHit]:
        if self.vector_index is None:
            raise EmbedderRequiredError("similarity requires Corpus(embedder=...)")
        return self.vector_index.similar(self._require_uid(ref), k)

    def query_vector(self, vec: Vector, k: int | None = None) -> list[SimilarHit]:
        if self.vector_index is None:
            raise EmbedderRequiredError("similarity requires Corpus(embedder=...)")
        return self.vector_index.query_vector(vec, k)

    def similar_text(self, text: str, k: int | None = None) -> list[SimilarHit]:
        if self.vector_index is None:
            raise EmbedderRequiredError("similarity requires Corpus(embedder=...)")
        assert self.embedder is not None
        return self.vector_index.similar_text(text, self.embedder, k)

    def rename(self, old_id: str, new_id: str) -> Node:
        if old_id not in self.index.id_to_uid:
            raise RefError(f"rename source {old_id!r} is not a live id")
        if self.index.resolve_uid(new_id) is not None:
            raise CollisionError(f"target id {new_id!r} already in use")

        uid = self.index.id_to_uid[old_id]
        referrer_uids = {ir.source_uid for ir in self.index.in_refs.get(old_id, [])}

        # --- prepare: rewrite every node that will change, in memory ---
        node = self.store.read_file(old_id)
        old_path = self.store.path_for(old_id)
        node.id = new_id
        node.kind = NodeId.parse(new_id).kind
        if old_id not in node.deprecated_ids:
            node.deprecated_ids.append(old_id)
        _rewrite_refs(node, old_id, new_id)

        referrers: list[Node] = []
        for referrer_uid in referrer_uids:
            if referrer_uid == uid:
                continue
            referrer = self.store.read_file(self.index.by_uid[referrer_uid].id)
            _rewrite_refs(referrer, old_id, new_id)
            referrers.append(referrer)

        # --- validate: ALL writes, before ANY write (fail-early, no partial rename) ---
        if self.registry is not None:
            self.registry.validate(node)
            for referrer in referrers:
                self.registry.validate(referrer)

        # --- prepare similarity vector (fail before any disk write) ---
        prepared = None
        if self.vector_index is not None:
            assert self.embedder is not None and self.vector_cache is not None
            prepared = self.vector_index.prepare(node, self.embedder, self.vector_cache)

        # --- commit: renamed node first (crash-atomic), then referrers ---
        new_path = self.store.write_file(node)
        if old_path != new_path:
            self.store.delete_file(old_id)
        self.index.upsert(node)
        for referrer in referrers:
            self.store.write_file(referrer)
            self.index.upsert(referrer)

        self.search_index.upsert(node)
        if self.vector_index is not None and prepared is not None:
            self.vector_index.commit(node, prepared)
        return node
