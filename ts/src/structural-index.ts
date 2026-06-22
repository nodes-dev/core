import { CollisionError } from "./errors.js";
import type { Node } from "./node.js";
import type { Relation } from "./relations.js";
import { MEMBERSHIP } from "./shapes.js";

export type Role =
  | "relation_source"
  | "relation_target"
  | "membership_member"
  | "membership_edge_source"
  | "membership_edge_target";

export interface OutRef {
  ref: string;
  role: Role;
  relation?: Relation; // present iff role starts with "relation_"
}

export interface InRef {
  sourceUid: string;
  outRef: OutRef;
}

export interface IndexEntry {
  uid: string;
  id: string;
  kind: string;
  deprecatedIds: ReadonlySet<string>;
  outRefs: OutRef[];
}

export interface ResolvedEdge {
  relation: Relation;
  sourceUid: string | null;
  targetUid: string | null; // null when the endpoint ref is dangling
}

// Every position that holds an id: relation source+target, membership members
// (list values and dict values), and membership edge source+target. Valid corpora
// hold only string refs in these positions; the string guards are a typed safety net.
function extractOutRefs(node: Node): OutRef[] {
  const refs: OutRef[] = [];
  for (const rel of node.relations) {
    refs.push({ ref: rel.source, role: "relation_source", relation: rel });
    refs.push({ ref: rel.target, role: "relation_target", relation: rel });
  }
  const mem = node.facets[MEMBERSHIP];
  if (mem !== undefined && mem !== null && typeof mem === "object") {
    const m = mem as Record<string, unknown>;
    const members = m.members;
    if (Array.isArray(members)) {
      for (const x of members) {
        if (typeof x === "string") refs.push({ ref: x, role: "membership_member" });
      }
    } else if (members !== null && typeof members === "object") {
      for (const v of Object.values(members as Record<string, unknown>)) {
        if (typeof v === "string") refs.push({ ref: v, role: "membership_member" });
      }
    }
    const edges = m.edges;
    if (Array.isArray(edges)) {
      for (const edge of edges) {
        if (edge !== null && typeof edge === "object") {
          const e = edge as Record<string, unknown>;
          if (typeof e.source === "string") refs.push({ ref: e.source, role: "membership_edge_source" });
          if (typeof e.target === "string") refs.push({ ref: e.target, role: "membership_edge_target" });
        }
      }
    }
  }
  return refs;
}

/** In-memory structural index. Pure data; no file I/O. */
export class Index {
  byUid = new Map<string, IndexEntry>();
  idToUid = new Map<string, string>();
  deprecatedToUid = new Map<string, string>();
  inRefs = new Map<string, InRef[]>();

  static build(nodes: Iterable<Node>): Index {
    const idx = new Index();
    for (const node of nodes) {
      if (idx.byUid.has(node.uid)) {
        throw new CollisionError(`duplicate uid ${JSON.stringify(node.uid)} in corpus`);
      }
      idx.assertAddable(node); // fail-early on a corrupt corpus (collision contract)
      idx.upsert(node);
    }
    return idx;
  }

  resolveUid(ref: string): string | null {
    return this.idToUid.get(ref) ?? this.deprecatedToUid.get(ref) ?? null;
  }

  // The collision gate. `upsert` is mechanical and never raises; this is what `build`
  // and `Corpus.add` call before `upsert`. `Corpus.rename` does NOT call it (rename
  // changes a uid's live id, which the second clause would reject mid-commit).
  assertAddable(node: Node): void {
    const existing = this.byUid.get(node.uid);
    if (existing !== undefined && existing.id !== node.id) {
      throw new CollisionError(
        `uid ${JSON.stringify(node.uid)} already belongs to live id ${JSON.stringify(existing.id)}; use rename()`,
      );
    }
    for (const claim of [node.id, ...node.deprecatedIds]) {
      const owner = this.resolveUid(claim);
      if (owner !== null && owner !== node.uid) {
        throw new CollisionError(
          `identity claim ${JSON.stringify(claim)} already in use by uid ${JSON.stringify(owner)}`,
        );
      }
    }
  }

  upsert(node: Node): void {
    if (this.byUid.has(node.uid)) this.drop(node.uid);
    const entry: IndexEntry = {
      uid: node.uid,
      id: node.id,
      kind: node.kind,
      deprecatedIds: new Set(node.deprecatedIds),
      outRefs: extractOutRefs(node),
    };
    this.byUid.set(node.uid, entry);
    this.idToUid.set(node.id, node.uid);
    for (const dep of node.deprecatedIds) this.deprecatedToUid.set(dep, node.uid);
    for (const oref of entry.outRefs) {
      const rows = this.inRefs.get(oref.ref) ?? [];
      rows.push({ sourceUid: node.uid, outRef: oref });
      this.inRefs.set(oref.ref, rows);
    }
  }

  remove(uid: string): void {
    this.drop(uid);
  }

  private drop(uid: string): void {
    const entry = this.byUid.get(uid);
    if (entry === undefined) return;
    this.byUid.delete(uid);
    if (this.idToUid.get(entry.id) === uid) this.idToUid.delete(entry.id);
    for (const dep of entry.deprecatedIds) {
      if (this.deprecatedToUid.get(dep) === uid) this.deprecatedToUid.delete(dep);
    }
    // Drop only the refs THIS node contributed as a source. Inbound refs that other
    // (surviving) nodes contributed pointing at this node's ids must persist — they
    // are still on disk and become dangling.
    for (const [ref, rows] of [...this.inRefs.entries()]) {
      const kept = rows.filter((r) => r.sourceUid !== uid);
      if (kept.length > 0) this.inRefs.set(ref, kept);
      else this.inRefs.delete(ref);
    }
  }
}
