import { CollisionError, EmbedderRequiredError, RefError } from "./errors.js";
import { nodeFromMarkdown, nodeToMarkdown } from "./frontmatter.js";
import { NodeId } from "./ids.js";
import type { Node } from "./node.js";
import type { Registry } from "./registry.js";
import { type SearchHit, SearchIndex } from "./search.js";
import { MEMBERSHIP } from "./shapes.js";
import { type Embedder, type SimilarHit, type Vector, VectorCache, VectorIndex } from "./similarity.js";
import {
  type ManifestEntry,
  type Snapshot,
  hashBytes,
  iterCorpusFiles,
  loadSnapshot,
  pathForNodeId,
  writeSnapshot,
} from "./snapshot.js";
import { Store } from "./store.js";
import { Index, type ResolvedEdge } from "./structural-index.js";

/** Rewrite every position in `node` that holds `oldId` to `newId` (in place). */
function rewriteRefs(node: Node, oldId: string, newId: string): void {
  for (const rel of node.relations) {
    if (rel.source === oldId) rel.source = newId;
    if (rel.target === oldId) rel.target = newId;
  }
  const mem = node.facets[MEMBERSHIP];
  if (mem !== undefined && mem !== null && typeof mem === "object") {
    const m = mem as Record<string, unknown>;
    const members = m.members;
    if (Array.isArray(members)) {
      m.members = members.map((x) => (x === oldId ? newId : x));
    } else if (members !== null && typeof members === "object") {
      const obj = members as Record<string, unknown>;
      for (const key of Object.keys(obj)) {
        if (obj[key] === oldId) obj[key] = newId;
      }
    }
    const edges = m.edges;
    if (Array.isArray(edges)) {
      for (const edge of edges) {
        if (edge !== null && typeof edge === "object") {
          const e = edge as Record<string, unknown>;
          if (e.source === oldId) e.source = newId;
          if (e.target === oldId) e.target = newId;
        }
      }
    }
  }
}

/** Coordinator over a `Store` + an in-memory `Index`. The primary kernel API. */
export class Corpus {
  readonly store: Store;
  readonly registry?: Registry;
  index!: Index;
  searchIndex!: SearchIndex;
  readonly embedder?: Embedder;
  readonly vectorCache?: VectorCache;
  vectorIndex?: VectorIndex;
  manifest: Map<string, ManifestEntry>;

  constructor(root: string, registry?: Registry, embedder?: Embedder) {
    this.store = new Store(root);
    this.registry = registry;
    this.embedder = embedder;
    this.vectorCache = embedder !== undefined ? new VectorCache(root) : undefined;
    this.manifest = new Map();
    const namespace = embedder !== undefined ? embedder.cacheNamespace : null;
    const snap = loadSnapshot(this.store.root, namespace);
    if (snap === null) this.fullRebuild();
    else this.reconcile(snap);
  }

  private relPath(nodeId: string): string {
    return pathForNodeId(nodeId);
  }

  private recordManifest(node: Node): void {
    const path = this.relPath(node.id);
    const data = Buffer.from(nodeToMarkdown(node), "utf-8");
    this.manifest.set(path, { path, sha256: hashBytes(data), uid: node.uid });
  }

  private fullRebuild(): void {
    const nodes: Node[] = [];
    const manifest = new Map<string, ManifestEntry>();
    for (const f of iterCorpusFiles(this.store.root)) {
      const node = nodeFromMarkdown(f.data.toString("utf-8"));
      nodes.push(node);
      manifest.set(f.path, { path: f.path, sha256: f.sha256, uid: node.uid });
    }
    this.index = Index.build(nodes);
    this.searchIndex = SearchIndex.build(nodes);
    if (this.embedder !== undefined) {
      this.vectorIndex = VectorIndex.build(nodes, this.embedder, this.vectorCache as VectorCache);
    } else {
      this.vectorIndex = undefined;
    }
    this.manifest = manifest;
  }

  private reconcile(snap: Snapshot): void {
    this.index = snap.index;
    this.searchIndex = snap.searchIndex;
    this.vectorIndex = snap.vectorIndex ?? undefined;
    const old = new Map<string, ManifestEntry>(snap.manifest.map((m) => [m.path, m]));
    const newManifest = new Map<string, ManifestEntry>();
    const changed: Array<{ path: string; sha256: string; node: Node }> = [];
    const drops: string[] = [];
    const current = new Set<string>();
    for (const f of iterCorpusFiles(this.store.root)) {
      current.add(f.path);
      const prev = old.get(f.path);
      if (prev !== undefined && prev.sha256 === f.sha256) {
        newManifest.set(f.path, prev); // unchanged: keep deserialized state, no parse
        continue;
      }
      if (prev !== undefined) drops.push(prev.uid);
      changed.push({ path: f.path, sha256: f.sha256, node: nodeFromMarkdown(f.data.toString("utf-8")) });
    }
    for (const [path, m] of old) {
      if (!current.has(path)) drops.push(m.uid); // deleted on disk
    }
    for (const uid of drops) {
      this.index.remove(uid);
      this.searchIndex.remove(uid);
      this.vectorIndex?.remove(uid);
    }
    for (const { path, sha256, node } of changed) {
      // Full build() collision contract: duplicate uid is rejected outright, then assertAddable.
      if (this.index.byUid.has(node.uid))
        throw new CollisionError(`duplicate uid ${JSON.stringify(node.uid)} in corpus`);
      this.index.assertAddable(node);
      const prepared =
        this.vectorIndex !== undefined
          ? this.vectorIndex.prepare(node, this.embedder as Embedder, this.vectorCache as VectorCache)
          : undefined;
      this.index.upsert(node);
      this.searchIndex.upsert(node);
      if (this.vectorIndex !== undefined && prepared !== undefined) this.vectorIndex.commit(node, prepared);
      newManifest.set(path, { path, sha256, uid: node.uid });
    }
    this.manifest = newManifest;
  }

  flushIndex(): void {
    const manifest = [...this.manifest.values()].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
    writeSnapshot(this.store.root, manifest, this.index, this.searchIndex, this.vectorIndex);
  }

  private idFor(uid: string): string {
    const entry = this.index.byUid.get(uid);
    if (entry === undefined) throw new RefError(`uid ${JSON.stringify(uid)} not in index`);
    return entry.id;
  }

  private requireUid(ref: string): string {
    const uid = this.index.resolveUid(ref);
    if (uid === null) throw new RefError(`no node resolves ref ${JSON.stringify(ref)}`);
    return uid;
  }

  add(node: Node): Node {
    if (this.registry !== undefined) this.registry.validate(node);
    this.index.assertAddable(node);
    const prepared =
      this.vectorIndex !== undefined
        ? this.vectorIndex.prepare(node, this.embedder as Embedder, this.vectorCache as VectorCache)
        : undefined;
    this.store.writeFile(node);
    this.index.upsert(node);
    this.searchIndex.upsert(node);
    if (this.vectorIndex !== undefined && prepared !== undefined) {
      this.vectorIndex.commit(node, prepared);
    }
    return node;
  }

  get(ref: string): Node {
    return this.store.readFile(this.idFor(this.requireUid(ref)));
  }

  resolve(ref: string): Node {
    return this.get(ref);
  }

  delete(nodeId: string): void {
    const uid = this.index.idToUid.get(nodeId);
    if (uid === undefined) throw new RefError(`no live node at ${JSON.stringify(nodeId)}`);
    this.store.deleteFile(nodeId);
    this.index.remove(uid);
    this.searchIndex.remove(uid);
    this.vectorIndex?.remove(uid);
  }

  all(): Node[] {
    return this.store.allNodes();
  }

  outbound(ref: string): ResolvedEdge[] {
    return this.index.outboundEdges(this.requireUid(ref));
  }

  inbound(ref: string): ResolvedEdge[] {
    return this.index.inboundEdges(this.requireUid(ref));
  }

  dangling(): ResolvedEdge[] {
    return this.index.danglingEdges();
  }

  neighbors(ref: string): Node[] {
    const uid = this.requireUid(ref);
    const neighborUids = new Set<string>();
    for (const edge of this.index.outboundEdges(uid)) {
      if (edge.targetUid !== null) neighborUids.add(edge.targetUid);
    }
    for (const edge of this.index.inboundEdges(uid)) {
      if (edge.sourceUid !== null) neighborUids.add(edge.sourceUid);
    }
    neighborUids.delete(uid);
    return [...neighborUids].sort().map((u) => this.store.readFile(this.idFor(u)));
  }

  rename(oldId: string, newId: string): Node {
    // 1. oldId must be a LIVE id (not unknown, not merely deprecated); then collision-check newId.
    const uid = this.index.idToUid.get(oldId);
    if (uid === undefined) throw new RefError(`rename source ${JSON.stringify(oldId)} is not a live id`);
    if (this.index.resolveUid(newId) !== null) {
      throw new CollisionError(`target id ${JSON.stringify(newId)} already in use`);
    }

    // 2. Snapshot the referrer set BEFORE any index mutation (upsert rewrites inRefs).
    const referrerUids = new Set<string>();
    for (const inref of this.index.inRefs.get(oldId) ?? []) referrerUids.add(inref.sourceUid);

    // 3. Rewrite the renamed node itself (incl. its own oldId refs).
    const node = this.store.readFile(oldId);
    const oldPath = this.store.pathFor(oldId);
    node.id = newId;
    node.kind = NodeId.parse(newId).kind;
    if (!node.deprecatedIds.includes(oldId)) node.deprecatedIds.push(oldId);
    rewriteRefs(node, oldId, newId);

    // 4. Rewrite every OTHER referrer in memory.
    const referrers: Node[] = [];
    for (const referrerUid of referrerUids) {
      if (referrerUid === uid) continue;
      const referrer = this.store.readFile(this.idFor(referrerUid));
      rewriteRefs(referrer, oldId, newId);
      referrers.push(referrer);
    }

    // 5. Validate ALL writes before ANY write (fail-early, no partial rename).
    if (this.registry !== undefined) {
      this.registry.validate(node);
      for (const referrer of referrers) this.registry.validate(referrer);
    }

    // 5b. Prepare the renamed node's vector (fail before any disk write).
    const prepared =
      this.vectorIndex !== undefined
        ? this.vectorIndex.prepare(node, this.embedder as Embedder, this.vectorCache as VectorCache)
        : undefined;

    // 6. Commit: renamed node first (crash-atomic), then referrers. Each written once.
    const newPath = this.store.writeFile(node);
    if (oldPath !== newPath) this.store.deleteFile(oldId);
    this.index.upsert(node);
    for (const referrer of referrers) {
      this.store.writeFile(referrer);
      this.index.upsert(referrer);
    }

    this.searchIndex.upsert(node);
    if (this.vectorIndex !== undefined && prepared !== undefined) {
      this.vectorIndex.commit(node, prepared);
    }
    return node;
  }

  search(query: string, limit?: number): SearchHit[] {
    return this.searchIndex.search(query, limit);
  }

  similar(ref: string, k?: number): SimilarHit[] {
    if (this.vectorIndex === undefined) {
      throw new EmbedderRequiredError("similarity requires Corpus(root, registry?, embedder)");
    }
    return this.vectorIndex.similar(this.requireUid(ref), k);
  }

  queryVector(vec: Vector, k?: number): SimilarHit[] {
    if (this.vectorIndex === undefined) {
      throw new EmbedderRequiredError("similarity requires Corpus(root, registry?, embedder)");
    }
    return this.vectorIndex.queryVector(vec, k);
  }

  similarText(text: string, k?: number): SimilarHit[] {
    if (this.vectorIndex === undefined) {
      throw new EmbedderRequiredError("similarity requires Corpus(root, registry?, embedder)");
    }
    return this.vectorIndex.similarText(text, this.embedder as Embedder, k);
  }
}
