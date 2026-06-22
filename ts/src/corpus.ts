import { RefError } from "./errors.js";
import type { Node } from "./node.js";
import type { Registry } from "./registry.js";
import { Store } from "./store.js";
import { Index, type ResolvedEdge } from "./structural-index.js";

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
    void oldId;
    void newId;
    throw new Error("rename not yet implemented");
  }
}
