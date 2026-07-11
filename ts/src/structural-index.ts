import { CollisionError, IdError, RefError } from "./errors.js";
import { NodeId } from "./ids.js";
import type { Node } from "./node.js";
import { type Relation, RelationSchema } from "./relations.js";
import { EDGES, KEYS, MEMBERSHIP, ORDER } from "./shapes.js";

export type Role =
  | "relation_source"
  | "relation_target"
  | "membership_member"
  | "edges_source"
  | "edges_target"
  | "order_member"
  | "keys_value";

const STRUCTURAL_ENTRY_KEYS = ["uid", "id", "kind", "deprecatedIds", "relations", "structuralRefs"] as const;
const STRUCTURAL_REF_ROLES = new Set<Role>([
  "membership_member",
  "edges_source",
  "edges_target",
  "order_member",
  "keys_value",
]);

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

function relationOutRefs(relations: Relation[]): OutRef[] {
  const refs: OutRef[] = [];
  for (const rel of relations) {
    refs.push({ ref: rel.source, role: "relation_source", relation: rel });
    refs.push({ ref: rel.target, role: "relation_target", relation: rel });
  }
  return refs;
}

// Refs from the built-in structural facets. Read directly from `node.facets`
// (registry-independent); they populate `inRefs` for rename + dangling integrity but
// are never relation-graph edges (their `relation` stays undefined).
function structuralOutRefs(node: Node): OutRef[] {
  const refs: OutRef[] = [];
  const mem = node.facets[MEMBERSHIP];
  if (mem !== null && typeof mem === "object") {
    const members = (mem as Record<string, unknown>).members;
    if (Array.isArray(members)) {
      for (const m of members) if (typeof m === "string") refs.push({ ref: m, role: "membership_member" });
    }
  }
  const eg = node.facets[EDGES];
  if (eg !== null && typeof eg === "object") {
    const edges = (eg as Record<string, unknown>).edges;
    if (Array.isArray(edges)) {
      for (const edge of edges) {
        if (edge !== null && typeof edge === "object") {
          const e = edge as Record<string, unknown>;
          if (typeof e.source === "string") refs.push({ ref: e.source, role: "edges_source" });
          if (typeof e.target === "string") refs.push({ ref: e.target, role: "edges_target" });
        }
      }
    }
  }
  const od = node.facets[ORDER];
  if (od !== null && typeof od === "object") {
    const order = (od as Record<string, unknown>).order;
    if (Array.isArray(order)) {
      for (const m of order) if (typeof m === "string") refs.push({ ref: m, role: "order_member" });
    }
  }
  const ky = node.facets[KEYS];
  if (ky !== null && typeof ky === "object") {
    const keys = (ky as Record<string, unknown>).keys;
    if (keys !== null && typeof keys === "object") {
      for (const v of Object.values(keys as Record<string, unknown>)) {
        if (typeof v === "string") refs.push({ ref: v, role: "keys_value" });
      }
    }
  }
  return refs;
}

function extractOutRefs(node: Node): OutRef[] {
  return [...relationOutRefs(node.relations), ...structuralOutRefs(node)];
}

function validatedDeprecatedIds(raw: unknown, entryId: string): string[] {
  if (!Array.isArray(raw)) throw new Error("structural snapshot: deprecatedIds must be an array of strings");
  const out: string[] = [];
  const seen = new Set<string>();
  for (const dep of raw) {
    if (typeof dep !== "string") throw new Error("structural snapshot: deprecatedIds must be an array of strings");
    if (dep === entryId)
      throw new Error(
        `structural snapshot: identity claim ${JSON.stringify(dep)} is both live and deprecated in one entry`,
      );
    if (seen.has(dep))
      throw new Error(`structural snapshot: duplicate deprecated identity claim ${JSON.stringify(dep)} in one entry`);
    seen.add(dep);
    out.push(dep);
  }
  return out;
}

function validateSnapshotWeight(raw: Record<string, unknown>, label: string): void {
  if (!("weight" in raw)) return;
  const weight = raw.weight;
  if (typeof weight !== "number" || !Number.isFinite(weight)) {
    throw new Error(`structural snapshot: ${label} weight must be a finite number`);
  }
}

function validateSnapshotDirected(raw: Record<string, unknown>, label: string): void {
  if ("directed" in raw && typeof raw.directed !== "boolean") {
    throw new Error(`structural snapshot: ${label} directed must be a boolean`);
  }
}

function validatedStructuralRefs(raw: unknown): OutRef[] {
  if (!Array.isArray(raw)) throw new Error("structural snapshot: structuralRefs must be an array");
  const out: OutRef[] = [];
  for (const item of raw) {
    if (item === null || typeof item !== "object")
      throw new Error("structural snapshot: structuralRef must be an object");
    const { ref, role } = item as Record<string, unknown>;
    if (typeof ref !== "string") throw new Error("structural snapshot: structuralRef ref must be a string");
    if (typeof role !== "string" || !STRUCTURAL_REF_ROLES.has(role as Role))
      throw new Error("structural snapshot: structuralRef role is invalid");
    out.push({ ref, role: role as Role });
  }
  return out;
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

  toDict(): {
    entries: Array<{
      uid: string;
      id: string;
      kind: string;
      deprecatedIds: string[];
      relations: Array<Record<string, unknown>>;
      structuralRefs: Array<{ ref: string; role: Role }>;
    }>;
  } {
    const entries = [];
    for (const entry of this.byUid.values()) {
      const relations: Array<Record<string, unknown>> = [];
      for (const o of entry.outRefs) {
        if (o.role !== "relation_source" || o.relation === undefined) continue;
        const rel = o.relation;
        const row: Record<string, unknown> = {
          source: rel.source,
          predicate: rel.predicate,
          target: rel.target,
          directed: rel.directed,
          attrs: structuredClone(rel.attrs),
        };
        if (rel.weight !== null) row.weight = rel.weight;
        relations.push(row);
      }
      entries.push({
        uid: entry.uid,
        id: entry.id,
        kind: entry.kind,
        deprecatedIds: [...entry.deprecatedIds].sort(),
        relations,
        structuralRefs: entry.outRefs
          .filter((o) => !o.role.startsWith("relation_"))
          .map((o) => ({ ref: o.ref, role: o.role })),
      });
    }
    return { entries };
  }

  static fromDict(d: unknown): Index {
    if (typeof d !== "object" || d === null) throw new Error("structural snapshot: document must be an object");
    const raw = d as Record<string, unknown>;
    if (!("entries" in raw)) throw new Error("structural snapshot: missing entries");
    if (!Array.isArray(raw.entries)) throw new Error("structural snapshot: entries must be an array");
    const idx = new Index();
    for (const rawEntry of raw.entries) {
      if (typeof rawEntry !== "object" || rawEntry === null)
        throw new Error("structural snapshot: entry must be an object");
      const e = rawEntry as Record<string, unknown>;
      for (const key of STRUCTURAL_ENTRY_KEYS) {
        if (!(key in e)) throw new Error(`structural snapshot: entry missing ${key}`);
      }
      const { uid, id: entryId, kind } = e;
      if (typeof uid !== "string") throw new Error("structural snapshot: entry uid must be a string");
      if (typeof entryId !== "string") throw new Error("structural snapshot: entry id must be a string");
      if (typeof kind !== "string") throw new Error("structural snapshot: entry kind must be a string");
      let parsed: NodeId;
      try {
        parsed = NodeId.parse(entryId);
      } catch (err) {
        if (err instanceof IdError) throw new Error("structural snapshot: entry id must be a valid node id");
        throw err;
      }
      if (parsed.kind !== kind) throw new Error("structural snapshot: entry id kind must match entry kind");
      if (!Array.isArray(e.relations)) throw new Error("structural snapshot: entry relations must be an array");
      if (idx.byUid.has(uid)) throw new Error(`structural snapshot: duplicate uid ${JSON.stringify(uid)}`);
      const deprecatedIds = validatedDeprecatedIds(e.deprecatedIds, entryId);
      const relations: Relation[] = [];
      for (const rawRel of e.relations) {
        if (typeof rawRel !== "object" || rawRel === null)
          throw new Error("structural snapshot: relation row must be an object");
        const rr = rawRel as Record<string, unknown>;
        validateSnapshotDirected(rr, "relation row");
        validateSnapshotWeight(rr, "relation row");
        const relData = { ...rr, attrs: structuredClone(rr.attrs ?? {}) };
        const result = RelationSchema.safeParse(relData);
        if (!result.success) throw new Error("structural snapshot: invalid relation row");
        relations.push(result.data);
      }
      const structuralRefs = validatedStructuralRefs(e.structuralRefs);
      const outRefs = [...relationOutRefs(relations), ...structuralRefs];
      const entry: IndexEntry = {
        uid,
        id: entryId,
        kind,
        deprecatedIds: new Set(deprecatedIds),
        outRefs,
      };
      for (const claim of [entry.id, ...entry.deprecatedIds]) {
        const owner = idx.resolveUid(claim);
        if (owner !== null) {
          throw new Error(
            `structural snapshot: identity claim ${JSON.stringify(claim)} already in use by uid ${JSON.stringify(owner)}`,
          );
        }
      }
      idx.byUid.set(uid, entry);
      idx.idToUid.set(entry.id, uid);
      for (const dep of entry.deprecatedIds) idx.deprecatedToUid.set(dep, uid);
      for (const oref of outRefs) {
        const rows = idx.inRefs.get(oref.ref) ?? [];
        rows.push({ sourceUid: uid, outRef: oref });
        idx.inRefs.set(oref.ref, rows);
      }
    }
    return idx;
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

  private refsForUid(uid: string): string[] {
    const entry = this.byUid.get(uid);
    if (entry === undefined) throw new RefError(`uid ${JSON.stringify(uid)} not in index`);
    return [entry.id, ...[...entry.deprecatedIds].sort()];
  }

  private resolveEdge(rel: Relation): ResolvedEdge {
    return { relation: rel, sourceUid: this.resolveUid(rel.source), targetUid: this.resolveUid(rel.target) };
  }

  // Public graph queries are defined over distinct `Relation` OBJECTS (reference identity —
  // the TS analog of Python's `id(relation)` dedup), relations-only. A relation never
  // appears twice, and a relation whose source is a non-container node still attributes
  // correctly because we key on `relation_source` / `relation_target` roles.
  private relationsByRole(uid: string, role: Role): ResolvedEdge[] {
    const seen = new Set<Relation>();
    const edges: ResolvedEdge[] = [];
    for (const ref of this.refsForUid(uid)) {
      for (const inref of this.inRefs.get(ref) ?? []) {
        const oref = inref.outRef;
        if (oref.role !== role || oref.relation === undefined) continue;
        if (seen.has(oref.relation)) continue;
        seen.add(oref.relation);
        edges.push(this.resolveEdge(oref.relation));
      }
    }
    return edges;
  }

  outboundEdges(uid: string): ResolvedEdge[] {
    return this.relationsByRole(uid, "relation_source");
  }

  inboundEdges(uid: string): ResolvedEdge[] {
    return this.relationsByRole(uid, "relation_target");
  }

  danglingEdges(): ResolvedEdge[] {
    const seen = new Set<Relation>();
    const edges: ResolvedEdge[] = [];
    for (const entry of this.byUid.values()) {
      for (const oref of entry.outRefs) {
        // Only the target side can dangle: a relation is dangling when its TARGET ref resolves
        // to no live uid. (Source-side refs are the node's own outbound edges, always resolvable.)
        if (oref.role !== "relation_target" || oref.relation === undefined) continue;
        if (seen.has(oref.relation)) continue;
        if (this.resolveUid(oref.ref) === null) {
          seen.add(oref.relation);
          edges.push(this.resolveEdge(oref.relation));
        }
      }
    }
    return edges;
  }

  /** Uids of this node's resolvable direct members. Dangling member refs are skipped
   * (check reports them); duplicate entries and live+deprecated refs dedupe by uid. */
  membersOf(uid: string): Set<string> {
    const entry = this.byUid.get(uid);
    if (entry === undefined) throw new RefError(`uid ${JSON.stringify(uid)} not in index`);
    const members = new Set<string>();
    for (const oref of entry.outRefs) {
      if (oref.role !== "membership_member") continue;
      const memberUid = this.resolveUid(oref.ref);
      if (memberUid !== null) members.add(memberUid);
    }
    return members;
  }

  /** Uids of the nodes whose membership facet lists any of this node's identity claims
   * (live id or deprecated ids — the same attribution rule as relationsByRole). */
  containersOf(uid: string): Set<string> {
    const containers = new Set<string>();
    for (const ref of this.refsForUid(uid)) {
      for (const inref of this.inRefs.get(ref) ?? []) {
        if (inref.outRef.role !== "membership_member") continue;
        containers.add(inref.sourceUid);
      }
    }
    return containers;
  }

  /** Transitive membership closure (BFS). The visited set is seeded with the start uid,
   * which is excluded from the result even when a membership cycle reaches it. */
  membershipClosure(uid: string, direction: "members" | "containers"): Set<string> {
    const step = direction === "members" ? this.membersOf.bind(this) : this.containersOf.bind(this);
    const visited = new Set<string>([uid]);
    const queue: string[] = [uid];
    let head = 0;
    while (head < queue.length) {
      const current = queue[head++];
      for (const next of step(current)) {
        if (visited.has(next)) continue;
        visited.add(next);
        queue.push(next);
      }
    }
    visited.delete(uid);
    return visited;
  }

  /** Every unresolved membership ref, deduped by (container uid, ref). */
  danglingMembers(): Array<{ sourceUid: string; ref: string }> {
    const out: Array<{ sourceUid: string; ref: string }> = [];
    const seen = new Set<string>();
    for (const entry of this.byUid.values()) {
      for (const oref of entry.outRefs) {
        if (oref.role !== "membership_member") continue;
        if (this.resolveUid(oref.ref) !== null) continue;
        const key = `${entry.uid}\u0000${oref.ref}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({ sourceUid: entry.uid, ref: oref.ref });
      }
    }
    return out;
  }
}
