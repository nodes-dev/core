# TypeScript Structural Index (Corpus + Index) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the Python Plan-2 structural index to TypeScript — a slimmed `Store`, an in-memory `Index` (O(1) resolution + resolved relations graph), and a `Corpus` coordinator — reaching parity with the current Python kernel.

**Architecture:** `Corpus` owns a slimmed `Store` (pure file mechanics) plus an in-memory `Index`. Every mutation (`add`/`rename`/`delete`) goes through `Corpus`: index collision-check, `Store` file op, incremental index update. The index is a disposable cache, always rebuildable from the markdown files (a tested property). Faithful logic mirror of the current Python `corpus.py` / `index.py` / slimmed `store.py`.

**Tech Stack:** TypeScript (strict, ES2022, NodeNext ESM), Zod, eemeli `yaml`, Vitest, Biome.

**Reference (read before starting):** the design doc `~/d/nodes/docs/specs/2026-06-22-nodes-ts-structural-index-design.md`, and the Python sources this mirrors: `~/d/nodes/python/src/nodes/kernel/{index,corpus,store}.py` and their tests `~/d/nodes/python/tests/test_{index,corpus,store,index_rebuild_equivalence}.py`.

## Current State Note

This plan has since been implemented and remains useful as the historical TypeScript Plan-2 rollout for slim `Store`, structural `Index`, and `Corpus`. The core boundary is still current: `Store` is file mechanics, `Index` is pure in-memory structural data, and `Corpus` owns mutations, resolution, graph queries, and rename.

The TypeScript kernel has grown since this checklist was written:

- Current `Corpus` is `Corpus(root, registry?, embedder?)`. It still owns the structural index, and now also owns full-text `SearchIndex`, optional similarity `VectorIndex`, a live manifest, snapshot load/reconcile, and `flushIndex()`.
- Current construction attempts to load `.nodes-index/snapshot.ts.json` and reconcile it against current file hashes before falling back to a full rebuild. The plan's "always rebuildable from markdown files" remains true, but construction no longer always parses every file.
- `Store.allNodes()` now uses `iterCorpusFiles()` so scans share snapshot file-walk rules, including ignoring `.nodes-index/`.
- `Index` now also exposes `toDict()` / validating `fromDict()` for snapshot persistence. The class still does no file I/O.
- Later structural-shapes redesign split structural refs across `membership`, `edges`, `order`, and `keys` facets, so current ref roles include `edges_source`, `edges_target`, `order_member`, and `keys_value` instead of the historical one-facet membership edge roles shown below.
- The knowledge vocab has since been ported to TypeScript; the "knowledge vocab is NOT ported" constraint below is historical Plan-2 scope, not current package state.
- Current `Corpus` also exposes `idsByKind(kind)` and `allByKind(kind)`, which are later additions outside this plan.
- The `docs/format.md` and `ts/README.md` updates in Task 8 have already been integrated and extended with vocab, full-text search, similarity, and snapshot persistence. Do not replace current docs with the historical snippets below.

Treat code snippets below as the original greenfield implementation sequence, not as replacement code for current `ts/src`, tests, README, or `docs/format.md`.

## Global Constraints

Every task's requirements implicitly include this section.

- **Runtime/tooling (already in place; this plan adds NO dependencies):** ESM (`"type":"module"`); TypeScript `strict`, ES2022, **NodeNext** module resolution — all relative imports use a `.js` extension on `.ts` sources; Node `engines >=20`; npm; `packageManager npm@11.11.0`.
- **Dependencies:** Zod (validation), eemeli `yaml` (emit/parse — the relevant option is `sortMapEntries`, NOT js-yaml's `sortKeys`), Vitest (tests), Biome (lint/format).
- **API vs disk naming:** camelCase API, snake_case on disk. The only field that differs API-vs-disk is `deprecatedIds` (API) ↔ `deprecated_ids` (file + canonical JSON).
- **Error contract:** Reuse the existing `./errors.js` hierarchy — **no new error types**. `Corpus`/`Index` raise only `RefError` (unresolved ref) and `CollisionError` (identity collision). Dangling edges are a normal state, never an error. The boundary parsers (`makeNode`, `nodeFromMarkdown`, `membershipOf`) keep their existing ZodError-wrapping contract; this plan adds no new boundary parsers.
- **Parity is semantic, not byte-identical:** PyYAML vs JS `yaml` emitter formatting differences are an explicit non-goal.
- **Faithful port:** mirror the current Python `Corpus`/`Index`/slim `Store` semantics exactly. The knowledge vocab is NOT ported in this plan — registry-integration tests use `registerBuiltinShapes` (the only registry surface TS has), not the Python `register_knowledge_vocab`.
- **No compatibility layers / no "Unified" prefixes / no "legacy" shims.**
- **Commands:** `rtk` prefixes `git`/`npm`/`npx`/`uv`/`node`; shell builtins (`cd`) and filesystem primitives (`mkdir`/`mv`/`rmdir`) are shown bare; one command per line (no `&&` chains).
- **Docs/code paths** use `~/d/` (never `/home/keith/d/` or `/mnt/ssd/Dropbox/`). No `Co-Authored-By` trailers in commits.

---

### Task 1: Slim the `Store` to file mechanics

Current-code note: the slim `Store` surface from this task is implemented, with one later persistence-driven change: `Store.allNodes()` delegates to `iterCorpusFiles()` instead of a private recursive scanner.

**Files:**
- Modify: `ts/src/store.ts` (full rewrite — strip cross-corpus logic)
- Modify: `ts/tests/store.test.ts` (full rewrite — file-mechanics tests only)

**Interfaces:**
- Consumes: `RefError` (`./errors.js`); `nodeFromMarkdown`/`nodeToMarkdown` (`./frontmatter.js`); `NodeId` (`./ids.js`); `type Node` (`./node.js`).
- Produces: `class Store { constructor(root: string); pathFor(id): string; writeFile(node): string; readFile(id): Node; deleteFile(id): void; allNodes(): Node[] }`. **Removed** from the public surface: `write`, `resolve`, `read`, `delete`, `rename` (and all private rewrite/collision helpers).

- [ ] **Step 1: Rewrite the test to the slimmed surface (failing)**

Replace the entire contents of `ts/tests/store.test.ts`:

```typescript
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { RefError } from "../src/errors.js";
import { type Node, makeNode } from "../src/node.js";
import { Store } from "../src/store.js";

let root: string;
let store: Store;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-store-"));
  store = new Store(root);
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function n(id: string, kind: string, extra: Partial<Node> = {}): Node {
  return makeNode({ id, kind, title: id, ...extra });
}

describe("Store file mechanics", () => {
  it("writeFile then readFile round-trips", () => {
    store.writeFile(makeNode({ id: "topic:a", kind: "topic", title: "A", body: "hi" }));
    const got = store.readFile("topic:a");
    expect(got.title).toBe("A");
    expect(got.body).toBe("hi");
  });

  it("writeFile has no collision check — a different uid at the same id just overwrites", () => {
    store.writeFile(n("topic:a", "topic"));
    store.writeFile(makeNode({ id: "topic:a", kind: "topic", title: "Other" }));
    expect(store.readFile("topic:a").title).toBe("Other");
  });

  it("pathFor encodes a CURIE slug", () => {
    expect(store.pathFor("gene:HGNC:PHF19")).toBe(join(root, "gene", "HGNC__PHF19.md"));
  });

  it("readFile on a missing node throws RefError", () => {
    expect(() => store.readFile("topic:ghost")).toThrow(RefError);
  });

  it("deleteFile removes, then a second delete and a read both throw RefError", () => {
    store.writeFile(n("topic:a", "topic"));
    store.deleteFile("topic:a");
    expect(() => store.readFile("topic:a")).toThrow(RefError);
    expect(() => store.deleteFile("topic:a")).toThrow(RefError);
  });

  it("allNodes scans the corpus sorted by path", () => {
    store.writeFile(n("topic:b", "topic"));
    store.writeFile(n("topic:a", "topic"));
    expect(store.allNodes().map((x) => x.id)).toEqual(["topic:a", "topic:b"]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL — `store.writeFile`/`readFile`/`deleteFile` do not exist yet on the fat `Store`.

- [ ] **Step 3: Rewrite `Store` to file mechanics**

Replace the entire contents of `ts/src/store.ts`:

```typescript
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { RefError } from "./errors.js";
import { nodeFromMarkdown, nodeToMarkdown } from "./frontmatter.js";
import { NodeId } from "./ids.js";
import type { Node } from "./node.js";

/**
 * Pure file mechanics over a corpus directory. No cross-corpus logic.
 * Collision detection, ref resolution, and rename live in `Corpus`/`Index`.
 */
export class Store {
  readonly root: string;

  constructor(root: string) {
    this.root = root;
  }

  pathFor(nodeId: string): string {
    const nid = NodeId.parse(nodeId);
    return join(this.root, nid.kind, `${nid.slug.replace(/:/g, "__")}.md`);
  }

  private markdownPaths(): string[] {
    const out: string[] = [];
    const walk = (dir: string): void => {
      if (!existsSync(dir)) return;
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (entry.isFile() && entry.name.endsWith(".md")) out.push(full);
      }
    };
    walk(this.root);
    return out;
  }

  writeFile(node: Node): string {
    const path = this.pathFor(node.id);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, nodeToMarkdown(node), "utf-8");
    return path;
  }

  readFile(nodeId: string): Node {
    const path = this.pathFor(nodeId);
    if (!(existsSync(path) && statSync(path).isFile())) {
      throw new RefError(`no node at ${JSON.stringify(nodeId)}`);
    }
    return nodeFromMarkdown(readFileSync(path, "utf-8"));
  }

  deleteFile(nodeId: string): void {
    const path = this.pathFor(nodeId);
    if (!(existsSync(path) && statSync(path).isFile())) {
      throw new RefError(`no node at ${JSON.stringify(nodeId)}`);
    }
    rmSync(path);
  }

  allNodes(): Node[] {
    return this.markdownPaths()
      .sort()
      .map((p) => nodeFromMarkdown(readFileSync(p, "utf-8")));
  }
}
```

- [ ] **Step 4: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green. (The barrel `index.ts` still `export { Store }`s — that line is unchanged and valid.)

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/store.ts ts/tests/store.test.ts
rtk git commit -m "refactor(ts): slim Store to file mechanics (cross-corpus logic moves to Corpus/Index)"
```

---

### Task 2: `Index` — data structures, resolution, collision gate, upsert/remove

Current-code note: `Index` now also has validating snapshot serialization (`toDict()` / `fromDict()`). Current structural refs reflect the redesigned shape facets (`membership`, `edges`, `order`, `keys`), so do not use this task's older one-facet membership role list as current code.

**Files:**
- Create: `ts/src/structural-index.ts`
- Create: `ts/tests/structural-index.test.ts`

**Interfaces:**
- Consumes: `CollisionError`, `RefError` (`./errors.js`); `type Node` (`./node.js`); `type Relation` (`./relations.js`); `MEMBERSHIP` (`./shapes.js`).
- Produces (this task): `type Role`; `interface OutRef`, `InRef`, `IndexEntry`, `ResolvedEdge`; `class Index` with public maps `byUid`, `idToUid`, `deprecatedToUid`, `inRefs`, and methods `static build(nodes): Index`, `resolveUid(ref): string|null`, `assertAddable(node): void`, `upsert(node): void`, `remove(uid): void`. Graph-query methods are added in Task 3 (the `ResolvedEdge` type and the private `extractOutRefs` membership handling are written here so the reverse-ref maps are complete).

- [ ] **Step 1: Write the failing tests**

Create `ts/tests/structural-index.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { CollisionError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { Index } from "../src/structural-index.js";

function node(id: string, kind: string, extra: Record<string, unknown> = {}) {
  return makeNode({ id, kind, title: id, ...extra });
}

describe("Index — resolution & collision", () => {
  it("builds and resolves a live id", () => {
    const idx = Index.build([node("topic:a", "topic")]);
    const uid = idx.idToUid.get("topic:a");
    expect(idx.resolveUid("topic:a")).toBe(uid);
    expect(idx.resolveUid("topic:missing")).toBeNull();
  });

  it("resolves a deprecated id to its live node", () => {
    const a = node("topic:new", "topic", { deprecatedIds: ["topic:old"] });
    const idx = Index.build([a]);
    expect(idx.resolveUid("topic:old")).toBe(a.uid);
  });

  it("prefers a live id over a deprecated id (lookup order)", () => {
    const idx = new Index();
    idx.idToUid.set("topic:x", "uid-live");
    idx.deprecatedToUid.set("topic:x", "uid-dep");
    expect(idx.resolveUid("topic:x")).toBe("uid-live");
  });

  it("build rejects a colliding corpus (same id, different uid)", () => {
    const a = node("topic:a", "topic");
    const b = node("topic:a", "topic");
    expect(() => Index.build([a, b])).toThrow(CollisionError);
  });

  it("build rejects a duplicate uid", () => {
    const a = node("topic:a", "topic");
    const dup = makeNode({ id: "topic:a", kind: "topic", title: "copy", uid: a.uid });
    expect(() => Index.build([a, dup])).toThrow(CollisionError);
  });

  it("assertAddable rejects same id / different uid", () => {
    const idx = Index.build([node("topic:a", "topic")]);
    expect(() => idx.assertAddable(node("topic:a", "topic"))).toThrow(CollisionError);
  });

  it("assertAddable rejects same uid / different id (rename misuse)", () => {
    const a = node("topic:a", "topic");
    const idx = Index.build([a]);
    expect(() => idx.assertAddable(makeNode({ id: "topic:b", kind: "topic", title: "B", uid: a.uid }))).toThrow(
      CollisionError,
    );
  });

  it("assertAddable rejects a deprecated-id claim already in use", () => {
    const idx = Index.build([node("topic:a", "topic")]);
    expect(() => idx.assertAddable(node("topic:b", "topic", { deprecatedIds: ["topic:a"] }))).toThrow(CollisionError);
  });

  it("assertAddable allows a same-uid/same-id overwrite", () => {
    const a = node("topic:a", "topic");
    const idx = Index.build([a]);
    expect(() => idx.assertAddable(makeNode({ id: "topic:a", kind: "topic", title: "A2", uid: a.uid }))).not.toThrow();
  });
});

describe("Index — upsert & remove", () => {
  it("upsert replace is clean (old outbound refs dropped, new ones present)", () => {
    const a = node("topic:a", "topic", { relations: [relatesTo("topic:a", "topic:x")] });
    const idx = Index.build([a]);
    expect((idx.inRefs.get("topic:x") ?? []).some((r) => r.outRef.ref === "topic:x")).toBe(true);
    const a2 = makeNode({
      id: "topic:a",
      kind: "topic",
      title: "A",
      uid: a.uid,
      relations: [relatesTo("topic:a", "topic:y")],
    });
    idx.upsert(a2);
    expect(idx.inRefs.get("topic:x") ?? []).toEqual([]);
    expect((idx.inRefs.get("topic:y") ?? []).some((r) => r.outRef.ref === "topic:y")).toBe(true);
  });

  it("remove keeps a surviving referrer's inbound ref (it becomes dangling)", () => {
    const target = node("topic:t", "topic");
    const referrer = node("topic:r", "topic", { relations: [relatesTo("topic:r", "topic:t")] });
    const idx = Index.build([target, referrer]);
    idx.remove(target.uid);
    expect(idx.resolveUid("topic:t")).toBeNull();
    expect(idx.byUid.has(target.uid)).toBe(false);
    expect((idx.inRefs.get("topic:t") ?? []).some((r) => r.sourceUid === referrer.uid)).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL — `../src/structural-index.js` does not exist.

- [ ] **Step 3: Implement the `Index` data layer**

Create `ts/src/structural-index.ts`:

```typescript
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
        throw new CollisionError(`identity claim ${JSON.stringify(claim)} already in use by uid ${JSON.stringify(owner)}`);
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
```

> The graph-query methods and their private helpers (`refsForUid`, `resolveEdge`) are added in Task 3 — they are omitted here so this task's commit passes the full gate with no unused private members. The exported `ResolvedEdge` interface is defined now (an exported type is not flagged as unused) so the public type surface is stable across tasks.

- [ ] **Step 4: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/structural-index.ts ts/tests/structural-index.test.ts
rtk git commit -m "feat(ts): Index data layer — resolution, collision gate, upsert/remove"
```

---

### Task 3: `Index` — graph queries (outbound / inbound / dangling)

**Files:**
- Modify: `ts/src/structural-index.ts` (append three public methods + one private helper)
- Modify: `ts/tests/structural-index.test.ts` (append a `describe` block)

**Interfaces:**
- Consumes: the Task 2 `Index` internals (`refsForUid`, `resolveEdge`, `byUid`, `inRefs`, `resolveUid`); `type Relation`.
- Produces: `Index.outboundEdges(uid): ResolvedEdge[]`, `Index.inboundEdges(uid): ResolvedEdge[]`, `Index.danglingEdges(): ResolvedEdge[]`. Public graph queries are **relations-only** (membership refs are tracked for rename but never surface here) and dedupe by `Relation` object reference.

- [ ] **Step 1: Append the failing tests**

Append to `ts/tests/structural-index.test.ts`:

```typescript
describe("Index — graph queries", () => {
  it("outbound returns the node's source relations, resolved", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:b")] });
    const b = makeNode({ id: "topic:b", kind: "topic", title: "B" });
    const idx = Index.build([a, b]);
    const edges = idx.outboundEdges(a.uid);
    expect(edges).toHaveLength(1);
    expect(edges[0].relation.target).toBe("topic:b");
    expect(edges[0].sourceUid).toBe(a.uid);
    expect(edges[0].targetUid).toBe(b.uid);
  });

  it("inbound returns the node's target relations, resolved", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:b")] });
    const b = makeNode({ id: "topic:b", kind: "topic", title: "B" });
    const idx = Index.build([a, b]);
    const edges = idx.inboundEdges(b.uid);
    expect(edges).toHaveLength(1);
    expect(edges[0].sourceUid).toBe(a.uid);
    expect(edges[0].targetUid).toBe(b.uid);
  });

  it("inbound merges across a deprecated target ref", () => {
    const b = makeNode({ id: "topic:new", kind: "topic", title: "B", deprecatedIds: ["topic:old"] });
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:old")] });
    const idx = Index.build([a, b]);
    const edges = idx.inboundEdges(b.uid);
    expect(edges).toHaveLength(1);
    expect(edges[0].sourceUid).toBe(a.uid);
  });

  it("a relation with a non-container source attributes to the source node, not the file's node", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A" });
    const b = makeNode({
      id: "topic:b",
      kind: "topic",
      title: "B",
      relations: [{ source: "topic:a", predicate: "cites", target: "topic:c" }],
    });
    const c = makeNode({ id: "topic:c", kind: "topic", title: "C" });
    const idx = Index.build([a, b, c]);
    const outA = idx.outboundEdges(a.uid);
    expect(outA).toHaveLength(1);
    expect(outA[0].relation.target).toBe("topic:c");
    expect(idx.outboundEdges(b.uid)).toEqual([]); // B is not the source of any relation
  });

  it("membership members/edges are tracked but are NOT public graph edges", () => {
    const g = makeNode({
      id: "graph:g",
      kind: "graph",
      title: "G",
      facets: {
        membership: { shape: "graph", members: ["topic:x"], edges: [{ source: "topic:x", predicate: "to", target: "topic:y" }] },
      },
    });
    const x = makeNode({ id: "topic:x", kind: "topic", title: "X" });
    const y = makeNode({ id: "topic:y", kind: "topic", title: "Y" });
    const idx = Index.build([g, x, y]);
    expect(idx.outboundEdges(g.uid)).toEqual([]);
    expect(idx.inboundEdges(y.uid)).toEqual([]);
    expect(idx.danglingEdges()).toEqual([]);
  });

  it("dangling lists relations whose target resolves to no uid", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:gone")] });
    const idx = Index.build([a]);
    const dangling = idx.danglingEdges();
    expect(dangling).toHaveLength(1);
    expect(dangling[0].relation.target).toBe("topic:gone");
    expect(dangling[0].targetUid).toBeNull();
  });
});
```

The appended tests need no new imports beyond `makeNode`, `relatesTo`, `Index`, and the vitest helpers already imported at the top of the file.

- [ ] **Step 2: Run to verify it fails**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL — `outboundEdges`/`inboundEdges`/`danglingEdges` are not defined.

- [ ] **Step 3: Implement the graph queries**

First, add `RefError` to the errors import at the top of `ts/src/structural-index.ts` — change:

```typescript
import { CollisionError } from "./errors.js";
```

to:

```typescript
import { CollisionError, RefError } from "./errors.js";
```

Then append the helpers and query methods inside the `Index` class, immediately before its closing `}` (i.e. right after the `drop` method):

```typescript
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
}
```

- [ ] **Step 4: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green; Biome clean (the Task 2 private helpers are now used).

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/structural-index.ts ts/tests/structural-index.test.ts
rtk git commit -m "feat(ts): Index graph queries (outbound/inbound/dangling, relations-only)"
```

---

### Task 4: `Corpus` — CRUD, resolution, neighbors (`rename` stub)

Current-code note: current `Corpus` construction is no longer just `Index.build(this.store.allNodes())`; it loads/reconciles snapshots, builds `SearchIndex`, optionally builds `VectorIndex`, and maintains a manifest. The CRUD and graph-query APIs from this task are still present.

**Files:**
- Create: `ts/src/corpus.ts`
- Create: `ts/tests/corpus.test.ts`

**Interfaces:**
- Consumes: `RefError` (`./errors.js`); `type Node` (`./node.js`); `Store` (`./store.js`); `Index`, `type ResolvedEdge` (`./structural-index.js`).
- Produces: `class Corpus { constructor(root: string, registry?: Registry); readonly store: Store; readonly index: Index; add(node): Node; get(ref): Node; resolve(ref): Node; delete(id): void; all(): Node[]; outbound(ref): ResolvedEdge[]; inbound(ref): ResolvedEdge[]; dangling(): ResolvedEdge[]; neighbors(ref): Node[]; rename(oldId, newId): Node }`. `rename` is a deliberate stub in this task so Task 5's failing tests fail at runtime with the expected message, not at compile/type-analysis time. Task 5 replaces the stub with the real implementation and adds its extra imports + the `rewriteRefs` helper. `add` already calls `registry?.validate`.

- [ ] **Step 1: Write the failing tests**

Create `ts/tests/corpus.test.ts`:

```typescript
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { CollisionError, RefError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";

let root: string;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function n(id: string, kind: string, extra: Record<string, unknown> = {}) {
  return makeNode({ id, kind, title: id, ...extra });
}

describe("Corpus — CRUD", () => {
  it("add then get round-trips", () => {
    const c = new Corpus(root);
    const node = makeNode({ id: "topic:a", kind: "topic", title: "A", body: "hi" });
    c.add(node);
    const got = c.get("topic:a");
    expect(got.title).toBe("A");
    expect(got.body).toBe("hi");
    expect(got.uid).toBe(node.uid);
  });

  it("a fresh Corpus rebuilds its index from existing files", () => {
    new Corpus(root).add(n("topic:a", "topic"));
    const fresh = new Corpus(root);
    expect(fresh.get("topic:a").title).toBe("topic:a");
  });

  it("add rejects a colliding id (same id, different uid)", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic"));
    expect(() => c.add(makeNode({ id: "topic:a", kind: "topic", title: "Other" }))).toThrow(CollisionError);
  });

  it("add rejects a duplicate uid at a different id", () => {
    const c = new Corpus(root);
    const original = n("topic:a", "topic");
    c.add(original);
    expect(() => c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", uid: original.uid }))).toThrow(
      CollisionError,
    );
  });

  it("add rejects a deprecated-id claim already in use", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic"));
    expect(() => c.add(n("topic:b", "topic", { deprecatedIds: ["topic:a"] }))).toThrow(CollisionError);
  });

  it("add overwrites a same-uid/same-id node", () => {
    const c = new Corpus(root);
    const node = n("topic:a", "topic");
    c.add(node);
    node.title = "A2";
    c.add(node);
    expect(c.get("topic:a").title).toBe("A2");
  });

  it("get on an unresolved ref throws RefError", () => {
    expect(() => new Corpus(root).get("topic:ghost")).toThrow(RefError);
  });

  it("delete removes a node and is live-id-only", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic", { deprecatedIds: ["topic:old"] }));
    expect(() => c.delete("topic:old")).toThrow(RefError); // deprecated id is not a live id
    c.delete("topic:a");
    expect(() => c.get("topic:a")).toThrow(RefError);
  });
});

describe("Corpus — graph queries", () => {
  it("delete leaves a dangling inbound ref", () => {
    const c = new Corpus(root);
    c.add(n("topic:t", "topic"));
    c.add(n("topic:r", "topic", { relations: [relatesTo("topic:r", "topic:t")] }));
    c.delete("topic:t");
    const out = c.outbound("topic:r");
    expect(out).toHaveLength(1);
    expect(out[0].targetUid).toBeNull();
    expect(c.dangling()).toHaveLength(1);
    expect(() => c.inbound("topic:t")).toThrow(RefError); // the target no longer resolves
  });

  it("neighbors returns distinct resolved neighbors (outbound + inbound)", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic", { relations: [relatesTo("topic:a", "topic:b")] }));
    c.add(n("topic:b", "topic"));
    c.add(n("topic:c", "topic", { relations: [relatesTo("topic:c", "topic:a")] }));
    expect(c.neighbors("topic:a").map((x) => x.id).sort()).toEqual(["topic:b", "topic:c"]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL — `../src/corpus.js` does not exist.

- [ ] **Step 3: Implement `Corpus` (CRUD + queries; `rename` stubbed for Task 5)**

Create `ts/src/corpus.ts` (the `rewriteRefs` helper and the real `rename` method are added in Task 5; this task imports only what CRUD + queries need):

```typescript
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
```

(`rename` is intentionally stubbed. The Task 4 tests do not call `rename`, so the suite is green; Task 5's first test run exercises the stub and fails before the implementation is added.)

- [ ] **Step 4: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/corpus.ts ts/tests/corpus.test.ts
rtk git commit -m "feat(ts): Corpus CRUD + resolution + graph queries (rename stubbed)"
```

---

### Task 5: `Corpus.rename` — O(degree) referrer rewrite + registry validation

Current-code note: the O(degree), validate-all-before-write rename contract is still current. Later plans extended the commit path to refresh `SearchIndex`, optional `VectorIndex`, and manifest entries for the renamed node and every rewritten referrer.

**Files:**
- Modify: `ts/src/corpus.ts` (replace the `rename` stub with the real implementation)
- Modify: `ts/tests/corpus.test.ts` (append rename + registry `describe` blocks)

**Interfaces:**
- Consumes: the Task 4 `Corpus` (`store`, `index`, `idFor`); `NodeId.parse`; `CollisionError`/`RefError`; `MEMBERSHIP`; `Registry`, `registerBuiltinShapes` (`./registry.js`, `./shapes.js`) for the registry tests. Adds the module-level `rewriteRefs` helper.
- Produces: `Corpus.rename(oldId, newId): Node` — live-id-only; collision-checks `newId`; snapshots referrers before mutation; rewrites the renamed node's own refs + each referrer's refs; validates all writes before any write; writes new-then-deletes-old (crash-atomic); reindexes. Each node written exactly once.

- [ ] **Step 1: Append the failing tests**

Append to `ts/tests/corpus.test.ts`:

```typescript
import { existsSync } from "node:fs";
import { InvariantError, UnknownKindError } from "../src/errors.js";
import { Registry } from "../src/registry.js";
import { registerBuiltinShapes } from "../src/shapes.js";

function shapeRegistry(): Registry {
  const r = new Registry();
  registerBuiltinShapes(r);
  return r;
}

describe("Corpus — rename", () => {
  it("rewrites inbound relations and records a deprecated id", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.add(n("topic:b", "topic", { relations: [relatesTo("topic:b", "topic:old")] }));
    const renamed = c.rename("topic:old", "topic:new");
    expect(renamed.id).toBe("topic:new");
    expect(renamed.deprecatedIds).toContain("topic:old");
    const b = c.get("topic:b");
    expect(b.relations.some((r) => r.target === "topic:new")).toBe(true);
    expect(b.relations.every((r) => r.target !== "topic:old")).toBe(true);
  });

  it("resolves the old id after rename, and the alias persists across a cold reload", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.rename("topic:old", "topic:new");
    expect(c.get("topic:old").id).toBe("topic:new");
    const fresh = new Corpus(root);
    expect(fresh.get("topic:old").id).toBe("topic:new");
  });

  it("rewrites membership members and edge sources", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.add(n("topic:x", "topic"));
    c.add(
      makeNode({
        id: "graph:g",
        kind: "graph",
        title: "G",
        facets: {
          membership: {
            shape: "graph",
            members: ["topic:old", "topic:x"],
            edges: [{ source: "topic:old", predicate: "to", target: "topic:x" }],
          },
        },
      }),
    );
    c.rename("topic:old", "topic:new");
    const mem = c.get("graph:g").facets.membership as Record<string, unknown>;
    expect(mem.members).toEqual(["topic:new", "topic:x"]);
    expect((mem.edges as Array<Record<string, unknown>>)[0].source).toBe("topic:new");
  });

  it("rewrites dict-membership values", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.add(n("topic:x", "topic"));
    c.add(
      makeNode({
        id: "dict:d",
        kind: "dict",
        title: "D",
        facets: { membership: { shape: "dict", members: { a: "topic:old", b: "topic:x" } } },
      }),
    );
    c.rename("topic:old", "topic:new");
    const mem = c.get("dict:d").facets.membership as Record<string, unknown>;
    expect(mem.members).toEqual({ a: "topic:new", b: "topic:x" });
  });

  it("rewrites the renamed node's OWN explicit relation source (no stale source: old)", () => {
    const c = new Corpus(root);
    c.add(n("topic:t", "topic"));
    c.add(
      makeNode({
        id: "topic:old",
        kind: "topic",
        title: "Old",
        relations: [{ source: "topic:old", predicate: "cites", target: "topic:t" }],
      }),
    );
    c.rename("topic:old", "topic:new");
    const renamed = c.get("topic:new");
    const cites = renamed.relations.find((r) => r.predicate === "cites");
    expect(cites?.source).toBe("topic:new");
    expect(renamed.relations.every((r) => r.source !== "topic:old")).toBe(true);
  });

  it("rewrites a multi-ref referrer exactly once (both refs land on the new id)", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.add(
      makeNode({
        id: "topic:r",
        kind: "topic",
        title: "R",
        relations: [
          relatesTo("topic:r", "topic:old"),
          { source: "topic:r", predicate: "cites", target: "topic:old" },
        ],
      }),
    );
    c.rename("topic:old", "topic:new");
    const r = c.get("topic:r");
    expect(r.relations.every((rel) => rel.target !== "topic:old")).toBe(true);
    expect(r.relations.filter((rel) => rel.target === "topic:new")).toHaveLength(2);
  });

  it("inbound finds an edge across the deprecated id after rename", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.add(n("topic:b", "topic", { relations: [relatesTo("topic:b", "topic:old")] }));
    c.rename("topic:old", "topic:new");
    const inbound = c.inbound("topic:new");
    expect(inbound).toHaveLength(1);
    expect(inbound[0].sourceUid).toBe(c.index.idToUid.get("topic:b"));
  });

  it("rejects a deprecated or unknown oldId without writing or deleting", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic", { deprecatedIds: ["topic:stale"] }));
    expect(() => c.rename("topic:stale", "topic:z")).toThrow(RefError); // deprecated, not live
    expect(() => c.rename("topic:ghost", "topic:z")).toThrow(RefError); // unknown
    expect(c.get("topic:a").id).toBe("topic:a");
    expect(existsSync(join(root, "topic", "z.md"))).toBe(false);
  });

  it("rejects a target id already in use", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic"));
    c.add(n("topic:b", "topic"));
    expect(() => c.rename("topic:a", "topic:b")).toThrow(CollisionError);
  });
});

describe("Corpus — registry validation (built-in shapes)", () => {
  it("with no registry, an unregistered kind is allowed", () => {
    const c = new Corpus(root); // no registry
    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A" })); // topic is not a built-in shape
    expect(c.get("topic:a").title).toBe("A");
  });

  it("a registry rejects an unknown kind on add, writing no file", () => {
    const c = new Corpus(root, shapeRegistry());
    expect(() => c.add(makeNode({ id: "topic:a", kind: "topic", title: "A" }))).toThrow(UnknownKindError);
    expect(existsSync(join(root, "topic"))).toBe(false);
  });

  it("a registry rejects an invalid node on add, writing no file", () => {
    const c = new Corpus(root, shapeRegistry());
    // a `dag` whose membership has a cycle fails requireAcyclic
    const bad = makeNode({
      id: "dag:d",
      kind: "dag",
      title: "D",
      facets: {
        membership: {
          shape: "dag",
          members: ["a:1", "a:2"],
          edges: [
            { source: "a:1", predicate: "e", target: "a:2" },
            { source: "a:2", predicate: "e", target: "a:1" },
          ],
        },
      },
    });
    expect(() => c.add(bad)).toThrow(InvariantError);
    expect(existsSync(join(root, "dag"))).toBe(false);
  });

  it("a registry accepts a valid node on add", () => {
    const c = new Corpus(root, shapeRegistry());
    c.add(makeNode({ id: "set:s", kind: "set", title: "S", facets: { membership: { shape: "set", members: ["a:1"] } } }));
    expect(c.get("set:s").title).toBe("S");
  });

  it("rename validates the renamed node before any write (no partial rename)", () => {
    // Seed without a registry so we can place a node whose RENAMED kind would be invalid.
    const seed = new Corpus(root);
    seed.add(
      makeNode({
        id: "set:s",
        kind: "set",
        title: "S",
        facets: { membership: { shape: "set", members: ["a:1", "a:1"] } }, // duplicate members
      }),
    );
    const c = new Corpus(root, shapeRegistry());
    // set:s is invalid (duplicate members) under requireUniqueMembers; renaming it re-validates.
    expect(() => c.rename("set:s", "set:s2")).toThrow(InvariantError);
    const fresh = new Corpus(root);
    expect(fresh.get("set:s").title).toBe("S"); // old id still live
    expect(() => fresh.get("set:s2")).toThrow(RefError); // new id absent
  });

  it("rename blocked by an invalid referrer writes nothing", () => {
    const seed = new Corpus(root); // no registry — lets us write an invalid referrer
    seed.add(
      makeNode({
        id: "set:t",
        kind: "set",
        title: "set:t",
        facets: { membership: { shape: "set", members: ["a:1"] } },
      }),
    );
    seed.add(
      makeNode({
        id: "dag:bad",
        kind: "dag",
        title: "Bad",
        facets: {
          membership: {
            shape: "dag",
            members: ["a:1"],
            edges: [{ source: "a:1", predicate: "e", target: "a:1" }], // self-cycle → requireAcyclic fails
          },
        },
        relations: [{ source: "dag:bad", predicate: "about", target: "set:t" }],
      }),
    );
    const c = new Corpus(root, shapeRegistry());
    expect(() => c.rename("set:t", "set:t2")).toThrow(InvariantError);
    const fresh = new Corpus(root);
    expect(fresh.get("set:t").title).toBe("set:t"); // unchanged
    expect(() => fresh.get("set:t2")).toThrow(RefError);
    expect(fresh.get("dag:bad").relations[0].target).toBe("set:t"); // referrer untouched
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL — `rename` is the stub that throws "rename not yet implemented".

- [ ] **Step 3: Add the imports, the `rewriteRefs` helper, and the `rename` method**

First, extend the imports at the top of `ts/src/corpus.ts`. Change:

```typescript
import { RefError } from "./errors.js";
import type { Node } from "./node.js";
import type { Registry } from "./registry.js";
import { Store } from "./store.js";
import { Index, type ResolvedEdge } from "./structural-index.js";
```

to:

```typescript
import { CollisionError, RefError } from "./errors.js";
import { NodeId } from "./ids.js";
import type { Node } from "./node.js";
import type { Registry } from "./registry.js";
import { MEMBERSHIP } from "./shapes.js";
import { Store } from "./store.js";
import { Index, type ResolvedEdge } from "./structural-index.js";
```

Then add this module-level helper immediately above the `/** Coordinator ... */` doc comment:

```typescript
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
```

Finally, add the `rename` method inside the `Corpus` class, immediately after the `neighbors` method (before the class's closing `}`):

```typescript
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
```

- [ ] **Step 4: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/corpus.ts ts/tests/corpus.test.ts
rtk git commit -m "feat(ts): Corpus.rename — O(degree) referrer rewrite + fail-early validation"
```

---

### Task 6: Rebuild-equivalence property test

**Files:**
- Create: `ts/tests/index-rebuild-equivalence.test.ts`

**Interfaces:**
- Consumes: `Corpus` (`../src/corpus.js`); `Index`, `type OutRef` (`../src/structural-index.js`); `makeNode` (`../src/node.js`); `relatesTo` (`../src/relations.js`).
- Produces: a property test asserting the live index equals `Index.build(store.allNodes())` after a mutation sequence. No production code.

- [ ] **Step 1: Write the test**

Create `ts/tests/index-rebuild-equivalence.test.ts`:

```typescript
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { Index, type OutRef } from "../src/structural-index.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-rebuild-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function canonicalAttrs(attrs: Record<string, unknown>): string {
  const sorted: Record<string, unknown> = {};
  for (const k of Object.keys(attrs).sort()) sorted[k] = attrs[k];
  return JSON.stringify(sorted);
}

// The key MUST embed the relation payload, not just (ref, role, sourceUid): a stale
// predicate/directed/weight/attrs would otherwise pass undetected, and comparing Relation
// OBJECTS directly gives false negatives (live vs rebuild hold distinct references).
function relationSignature(o: OutRef): string | null {
  const rel = o.relation;
  if (rel === undefined) return null;
  return JSON.stringify([rel.source, rel.predicate, rel.target, rel.directed, rel.weight, canonicalAttrs(rel.attrs)]);
}

function outRefKey(o: OutRef): string {
  return JSON.stringify([o.ref, o.role, relationSignature(o)]);
}

function normalize(index: Index): unknown {
  const byUid: Record<string, unknown> = {};
  for (const [uid, e] of index.byUid) {
    byUid[uid] = [e.id, e.kind, [...e.deprecatedIds].sort(), e.outRefs.map(outRefKey).sort()];
  }
  const inRefs: Record<string, string[]> = {};
  for (const [ref, rows] of index.inRefs) {
    inRefs[ref] = rows
      .map((r) => JSON.stringify([r.sourceUid, r.outRef.ref, r.outRef.role, relationSignature(r.outRef)]))
      .sort();
  }
  return {
    byUid,
    idToUid: Object.fromEntries(index.idToUid),
    deprecatedToUid: Object.fromEntries(index.deprecatedToUid),
    inRefs,
  };
}

function assertEquivalent(c: Corpus): void {
  const fresh = Index.build(c.store.allNodes());
  expect(normalize(c.index)).toEqual(normalize(fresh));
}

describe("Index rebuild equivalence", () => {
  it("holds through an add/rename/delete/re-add sequence", () => {
    const c = new Corpus(root);
    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:b")] }));
    c.add(makeNode({ id: "topic:b", kind: "topic", title: "B" }));
    c.add(
      makeNode({
        id: "graph:g",
        kind: "graph",
        title: "G",
        facets: {
          membership: {
            shape: "graph",
            members: ["topic:a", "topic:b"],
            edges: [{ source: "topic:a", predicate: "to", target: "topic:b" }],
          },
        },
      }),
    );
    assertEquivalent(c);

    c.rename("topic:b", "topic:b2"); // deprecated id + rewrites A's relation and graph members/edges
    assertEquivalent(c);

    c.add(makeNode({ id: "topic:c", kind: "topic", title: "C", relations: [relatesTo("topic:c", "topic:a")] }));
    assertEquivalent(c);

    c.delete("topic:a"); // strands inbound refs from topic:c and graph:g → must stay dangling
    assertEquivalent(c);
    expect(c.dangling().length).toBeGreaterThanOrEqual(1);

    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A again" })); // reconverges dangling refs
    assertEquivalent(c);
    expect(c.dangling()).toEqual([]);
    expect(c.outbound("topic:c").every((e) => e.targetUid !== null)).toBe(true);
  });

  it("holds after a same-uid/same-id overwrite that changes outbound refs", () => {
    const c = new Corpus(root);
    const node = makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:x")] });
    c.add(node);
    node.relations = [relatesTo("topic:a", "topic:y")];
    c.add(node); // same uid + id overwrite
    assertEquivalent(c);
  });
});
```

- [ ] **Step 2: Run the test**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: PASS (the index is already correct from Tasks 2–5; this test guards it).

- [ ] **Step 3: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
cd ~/d/nodes
rtk git add ts/tests/index-rebuild-equivalence.test.ts
rtk git commit -m "test(ts): rebuild-equivalence property (live index == fresh rebuild)"
```

---

### Task 7: Cross-language rename parity (shared fixture corpus + oracle)

**Files:**
- Create: `fixtures/corpus/topic/old.md`, `fixtures/corpus/note/r.md`, `fixtures/corpus/graph/g.md`
- Create: `fixtures/corpus.rename.canonical.json`
- Create: `ts/tests/corpus_parity.test.ts`
- Create: `python/tests/test_corpus_parity.py`

**Interfaces:**
- Consumes: `Corpus`; the canonical-JSON helpers `toCanonical` (`ts/tests/_canonical.ts`) and `to_canonical` (`python/tests/_canonical.py`).
- Produces: a committed multi-node fixture corpus + a post-rename canonical-JSON oracle, and one parity check in each language asserting that `Corpus.rename("topic:old","topic:new")` over the fixture canonicalizes (all nodes, sorted by id) to the shared oracle. Semantic parity; both languages comparing to one oracle guarantees cross-language agreement.

- [ ] **Step 1: Author the fixture corpus**

The on-disk layout is `kind/slug.md`; frontmatter requires `id`, `uid`, `kind`, `title`. Each file ends at the closing `---\n` with an empty body (body == ""). Use these exact uids so the oracle is fully determined.

Create `fixtures/corpus/topic/old.md` (exact contents — file ends after `---` + newline, no body):

```markdown
---
id: topic:old
uid: 11111111111111111111111111111111
kind: topic
title: Old
---
```

Create `fixtures/corpus/note/r.md`:

```markdown
---
id: note:r
uid: 22222222222222222222222222222222
kind: note
title: R
related:
- topic:old
relations:
- predicate: cites
  target: topic:old
---
```

Create `fixtures/corpus/graph/g.md`:

```markdown
---
id: graph:g
uid: 33333333333333333333333333333333
kind: graph
title: G
facets:
  membership:
    shape: graph
    members:
    - topic:old
    edges:
    - source: topic:old
      predicate: to
      target: topic:old
---
```

- [ ] **Step 2: Author the post-rename oracle**

The fixed rename is `topic:old` → `topic:new`. After it: `topic:old` becomes `topic:new` with `deprecated_ids: ["topic:old"]`; `note:r`'s two relations (the `related` `relatesTo` and the typed `cites`) both retarget to `topic:new`; `graph:g`'s membership member and edge source+target all become `topic:new`. Canonical forms are sorted by id (`graph:g` < `note:r` < `topic:new`).

Create `fixtures/corpus.rename.canonical.json`:

```json
[
  {
    "id": "graph:g",
    "uid": "33333333333333333333333333333333",
    "kind": "graph",
    "title": "G",
    "body": "",
    "metadata": { "created": null, "updated": null, "version": 1 },
    "relations": [],
    "facets": {
      "membership": {
        "shape": "graph",
        "members": ["topic:new"],
        "edges": [{ "source": "topic:new", "predicate": "to", "target": "topic:new" }]
      }
    },
    "deprecated_ids": []
  },
  {
    "id": "note:r",
    "uid": "22222222222222222222222222222222",
    "kind": "note",
    "title": "R",
    "body": "",
    "metadata": { "created": null, "updated": null, "version": 1 },
    "relations": [
      { "source": "note:r", "predicate": "relatesTo", "target": "topic:new", "directed": true, "weight": null, "attrs": {} },
      { "source": "note:r", "predicate": "cites", "target": "topic:new", "directed": true, "weight": null, "attrs": {} }
    ],
    "facets": {},
    "deprecated_ids": []
  },
  {
    "id": "topic:new",
    "uid": "11111111111111111111111111111111",
    "kind": "topic",
    "title": "Old",
    "body": "",
    "metadata": { "created": null, "updated": null, "version": 1 },
    "relations": [],
    "facets": {},
    "deprecated_ids": ["topic:old"]
  }
]
```

- [ ] **Step 3: Write the TS parity check (failing until fixtures/oracle exist + match)**

Create `ts/tests/corpus_parity.test.ts`:

```typescript
import { cpSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { toCanonical } from "./_canonical.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures/", import.meta.url));

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-parity-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("cross-language rename parity", () => {
  it("TS Corpus.rename over the fixture corpus matches the shared oracle", () => {
    cpSync(join(FIXTURES, "corpus"), root, { recursive: true });
    const c = new Corpus(root);
    c.rename("topic:old", "topic:new");
    const actual = c
      .all()
      .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
      .map(toCanonical);
    const oracle = JSON.parse(readFileSync(join(FIXTURES, "corpus.rename.canonical.json"), "utf-8"));
    expect(actual).toEqual(oracle);
  });
});
```

- [ ] **Step 4: Write the Python parity check**

Create `python/tests/test_corpus_parity.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

from nodes.kernel.corpus import Corpus

from tests._canonical import to_canonical

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
ORACLE = FIXTURES / "corpus.rename.canonical.json"


def test_corpus_rename_parity(tmp_path):
    corpus_dir = tmp_path / "corpus"
    shutil.copytree(FIXTURES / "corpus", corpus_dir)
    c = Corpus(corpus_dir)
    c.rename("topic:old", "topic:new")
    actual = [to_canonical(n) for n in sorted(c.all(), key=lambda n: n.id)]
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert actual == oracle
```

- [ ] **Step 5: Run both checks**

```bash
cd ~/d/nodes/ts
rtk npm test
cd ~/d/nodes/python
rtk uv run pytest tests/test_corpus_parity.py -q
```

Expected: TS parity green; Python parity green. If both fail with the *same* actual value differing from the oracle, the oracle is mis-authored — correct `fixtures/corpus.rename.canonical.json` to the shared actual (the rename behavior itself is already proven by Task 5) and re-run. If only one language fails, that language's `rename`/emit has drifted — fix the code, not the oracle.

- [ ] **Step 6: Run both full gates**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
cd ~/d/nodes/python
rtk uv run pytest -q
rtk uv run ruff check src tests
rtk uv run pyright src
```

Expected: TS — full Vitest suite green, typecheck + Biome clean. Python — full suite green (existing + the new parity test), ruff + pyright clean.

- [ ] **Step 7: Commit**

```bash
cd ~/d/nodes
rtk git add fixtures/corpus fixtures/corpus.rename.canonical.json ts/tests/corpus_parity.test.ts python/tests/test_corpus_parity.py
rtk git commit -m "test: cross-language Corpus.rename parity (shared fixture corpus + oracle)"
```

---

### Task 8: Barrel exports + smoke test + docs

Current-code note: current `ts/src/index.ts` exports additional surfaces added later (`SearchIndex`, `VectorIndex`, snapshot helpers, ranking, similarity, and vocab). The docs snippets below are historical and have been superseded by current `docs/format.md` and `ts/README.md`.

**Files:**
- Modify: `ts/src/index.ts` (barrel — add `Corpus`, `Index` + its types)
- Modify: `ts/tests/smoke.test.ts` (assert the new surface)
- Modify: `ts/README.md` (scope: now includes Corpus + structural index; Store slimmed)
- Modify: `docs/format.md` (note the corpus rename-parity fixtures)

**Interfaces:**
- Consumes: every module's public surface.
- Produces: the package barrel re-exporting `Corpus`, `Index`, `ResolvedEdge`, `Role`, `OutRef`, `InRef`, `IndexEntry` (and the still-exported slimmed `Store`).

- [ ] **Step 1: Update the barrel**

Append to `ts/src/index.ts` (after the existing `export { Store } from "./store.js";` line):

```typescript
export { Corpus } from "./corpus.js";
export {
  Index,
  type InRef,
  type IndexEntry,
  type OutRef,
  type ResolvedEdge,
  type Role,
} from "./structural-index.js";
```

- [ ] **Step 2: Update the smoke test**

Replace the entire contents of `ts/tests/smoke.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { Corpus, Index, makeNode, nodeFromMarkdown, nodeToMarkdown, Registry, registerBuiltinShapes, Store } from "../src/index.js";

describe("barrel", () => {
  it("re-exports the public surface", () => {
    expect(typeof makeNode).toBe("function");
    expect(typeof nodeFromMarkdown).toBe("function");
    expect(typeof nodeToMarkdown).toBe("function");
    expect(typeof registerBuiltinShapes).toBe("function");
    expect(typeof Registry).toBe("function");
    expect(typeof Store).toBe("function");
    expect(typeof Corpus).toBe("function");
    expect(typeof Index).toBe("function");
  });
});
```

- [ ] **Step 3: Run to verify it passes**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: PASS.

- [ ] **Step 4: Update `ts/README.md`**

Replace the `## Scope` section of `ts/README.md` with:

```markdown
## Scope

Mirrors the current Python kernel: `Node`/`Relation`, ids, errors, frontmatter parse/serialize,
registry, structural shapes, a slimmed `Store` (pure file mechanics), an in-memory `Index`
(O(1) resolution + resolved relations graph), and a `Corpus` coordinator — the primary API for
all mutations (`add`/`get`/`rename`/`delete`) and graph queries (`outbound`/`inbound`/`neighbors`/
`dangling`). There is **no full-text search, no embeddings, no on-disk index persistence, and no
membership-graph traversal** — those, and the knowledge vocab, are later TypeScript plans.
```

- [ ] **Step 5: Update `docs/format.md`**

Append to `docs/format.md`:

```markdown
## Corpus rename parity (TypeScript structural index)

`Corpus.rename` rewrites files on disk. A corpus-level parity fixture pins this behavior across
languages under root `fixtures/`:

- `fixtures/corpus/` — a committed multi-node source corpus (a rename target plus referrers via
  relations and membership members/edges), in the on-disk `kind/slug.md` layout.
- `fixtures/corpus.rename.canonical.json` — the post-rename canonical-JSON oracle (the whole
  corpus after `topic:old` → `topic:new`, as canonical node forms sorted by id).

Both languages run the same check: copy the fixture corpus into a temp dir, run the fixed
`Corpus.rename`, canonicalize every node, and assert equality with the shared oracle. Parity is
semantic, not byte-identical.
```

- [ ] **Step 6: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/index.ts ts/tests/smoke.test.ts ts/README.md docs/format.md
rtk git commit -m "feat(ts): barrel exports for Corpus + Index; docs"
```

---

## Self-Review

**1. Spec coverage** (design doc §-by-§):
- §2 layering / TS naming (`structural-index.ts`, class `Index`) → Tasks 2–4 ✅
- §3 slimmed `Store` (exact surface; removals) → Task 1 ✅
- §4 `Index`: types, maps, `extractOutRefs` (relations + membership), resolution, collision (`assertAddable` gate; `upsert` mechanical), `build`/`upsert`/`remove`, graph queries, relation-reference dedup → Tasks 2–3 ✅
- §5 `Corpus`: `add`/`get`/`resolve`/`delete`/`all`/`outbound`/`inbound`/`dangling`/`neighbors`/`rename`; `rewriteRefs`; the O(degree) rename flow (live-id-only, snapshot-before-mutate, own-refs rewrite, validate-all-before-write, write-new-then-delete-old, reindex) → Tasks 4–5 ✅
- §6 rebuild-equivalence property w/ `relationSignature` in the multiset key → Task 6 ✅
- §7 cross-language rename parity (fixture corpus + oracle + both checks) → Task 7 ✅
- §8 error handling (RefError/CollisionError only; dangling never raises) → enforced in Tasks 4–5 ✅
- §9 testing strategy (Index unit, Corpus integration incl. all tightened cases, property, parity, Store migration) → Tasks 1–7 ✅
- §10 barrel + docs; deferrals → Task 8 ✅

**2. Placeholder scan:** No "TBD"/"handle errors"/"similar to Task N". The two intentional stubs (Task 4's `rename` throw + the `void` symbol-references; Task 3's marker import line) are each called out with explicit removal instructions in the very next task/step. Fixture-authoring steps contain exact byte contents and an exact oracle.

**3. Type consistency:** `Store` surface (`writeFile`/`readFile`/`deleteFile`/`pathFor`/`allNodes`) is identical across Task 1 (def) and Tasks 4–5 (consumers). `Index` method names (`build`/`resolveUid`/`assertAddable`/`upsert`/`remove`/`outboundEdges`/`inboundEdges`/`danglingEdges`) and public maps (`byUid`/`idToUid`/`deprecatedToUid`/`inRefs`) match across Tasks 2–6. `Corpus` surface matches across Tasks 4–8 and the barrel. `ResolvedEdge.{sourceUid,targetUid}` nullable, `OutRef.{ref,role,relation?}`, `Role` union — consistent. `deprecatedIds` (API) ↔ `deprecated_ids` (oracle JSON) used correctly. The registry tests use `registerBuiltinShapes` (TS has it), not the unported `register_knowledge_vocab` — consistent with the Global Constraints.
