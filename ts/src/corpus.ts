import { CollisionError, RefError } from "./errors.js";
import { NodeId } from "./ids.js";
import type { Node } from "./node.js";
import type { Registry } from "./registry.js";
import { MEMBERSHIP } from "./shapes.js";
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
  readonly index: Index;

  constructor(root: string, registry?: Registry) {
    this.store = new Store(root);
    this.registry = registry;
    this.index = Index.build(this.store.allNodes());
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
    this.store.writeFile(node);
    this.index.upsert(node);
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

    // 6. Commit: renamed node first (crash-atomic), then referrers. Each written once.
    const newPath = this.store.writeFile(node);
    if (oldPath !== newPath) this.store.deleteFile(oldId);
    this.index.upsert(node);
    for (const referrer of referrers) {
      this.store.writeFile(referrer);
      this.index.upsert(referrer);
    }

    return node;
  }
}
