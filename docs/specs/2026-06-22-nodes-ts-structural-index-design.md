# nodes — TypeScript Structural Index (Corpus + Index) Design

**Status:** approved 2026-06-22
**Builds on:** `docs/specs/2026-06-21-nodes-structural-index-design.md` (Plan 2, the Python
structural index) and `docs/specs/2026-06-21-nodes-ts-kernel-design.md` (Plan 4, the TypeScript
kernel port).
**Ports:** Plan 2 onto the TypeScript codebase, following the conventions established in Plan 4.

## 1. Purpose & scope

The Python kernel gained a structural index in Plan 2: O(1) ref resolution and a resolved
relations graph, with a `Corpus` coordinator over a slimmed `Store` + an in-memory `Index`. The
TypeScript kernel (Plan 4) deliberately mirrored only the *historical Plan-1* kernel — it shipped
the **fat** `Store` (collision detection, deprecated-id resolution, and `rename` all live inside
`Store`) and has **no** `Corpus` or `Index`.

This plan brings TypeScript to parity with the current Python kernel by porting Plan 2:

- **Resolution:** `id` / `deprecatedId` → `uid`, O(1), replacing the fat `Store`'s linear scans.
- **Resolved relations graph:** outbound / inbound / neighbors / dangling queries over the
  `Relation` primitive.
- **`Corpus`:** the new primary public API, coordinating a slimmed `Store` + an `Index`.

**Out of scope (matching Plan 2, deferred to later plans):** full-text search; embeddings /
similarity; on-disk persistence of the index; membership-graph *traversal* queries (tree
descendants, DAG reachability). The knowledge vocab is a separate TS plan.

The index remains a **disposable, fully rebuildable cache** over the canonical markdown files.

## 2. Architecture & layering

Three modules change, mirroring Plan 2's Python layout but adapted to TypeScript file
conventions:

- **`ts/src/structural-index.ts` — `Index`.** Pure in-memory maps + resolved relation graph.
  Knows nothing about files. Built from a list of `Node`s; supports incremental `upsert` /
  `remove`; answers resolution and graph queries.
- **`ts/src/corpus.ts` — `Corpus`.** The coordinator and primary public API. Owns a `Store` + an
  `Index`. Every mutation (`add` / `rename` / `delete`) goes through it.
- **`ts/src/store.ts` — slimmed.** Reduced to pure file mechanics. The cross-corpus logic
  migrates up into `Corpus` / `Index`. No compatibility shim is left behind (greenfield repo, no
  external consumers).

### TypeScript naming note

In Python the `Index` class lives in `nodes/kernel/index.py` and `__init__.py` is the package
entry. In TypeScript, `ts/src/index.ts` is the **package barrel** (the entry point), so the
`Index` class cannot live there. The file is therefore named `structural-index.ts`; the exported
class stays `Index` for cross-language parity with Python.

### Lifecycle

In-memory, incremental. `new Corpus(root)` builds the `Store`, scans the corpus once
(`store.allNodes()`), and builds the `Index`. Thereafter, `Corpus` mutations update the live index
incrementally — no full rebuild per mutation, no disk persistence. The index is always
reconstructable from the files (see §6 invariant).

## 3. `Store` after slimming

`Store` keeps only mechanical, single-file or whole-corpus-scan operations:

```typescript
class Store {
  constructor(root: string)
  pathFor(id: string): string
  writeFile(node: Node): string      // mechanical write; NO collision check
  readFile(id: string): Node         // by pathFor(id) only; RefError if no file. NO deprecated scan
  deleteFile(id: string): void       // unlink; RefError if absent
  allNodes(): Node[]                  // corpus scan, used to build/rebuild the Index
}
```

**Removed from `Store` (moved up to `Corpus` / `Index`):** `write` (collision check), `resolve`
(deprecated scan), `read`, `rename` and `rewriteInbound` / `rewriteRelations` /
`rewriteMembership`, `assertNoIdentityCollision`, `claimedIds`, `idOwnerUid`.

`writeFile` / `readFile` / `deleteFile` are the renamed mechanical cores of the old `write` /
`read` / `delete`. The crash-atomic write ordering that lived in the fat `rename` moves up to
`Corpus.rename` (§5).

## 4. `Index` (`ts/src/structural-index.ts`)

### What it holds

A lightweight entry per node — **not** the prose body (the body stays sourced from disk via
`Store`, keeping a single source of truth):

```typescript
type Role =
  | "relation_source"
  | "relation_target"
  | "membership_member"
  | "membership_edge_source"
  | "membership_edge_target";

interface OutRef {
  ref: string;                 // the referenced id string as written (the inRefs key)
  role: Role;
  relation?: Relation;         // present iff role starts with "relation_"
}

interface InRef {
  sourceUid: string;           // the node that holds this reference
  outRef: OutRef;              // the specific outbound reference
}

interface IndexEntry {
  uid: string;
  id: string;
  kind: string;
  deprecatedIds: ReadonlySet<string>;
  outRefs: OutRef[];
}

interface ResolvedEdge {
  relation: Relation;
  sourceUid: string | null;
  targetUid: string | null;    // null when the endpoint ref is dangling
}
```

Maps (all plain `Map<string, …>`):

- `byUid: Map<string, IndexEntry>`
- `idToUid: Map<string, string>`            — live ids
- `deprecatedToUid: Map<string, string>`    — stale-ref resolution; a live id ALWAYS wins
- `inRefs: Map<string, InRef[]>`            — reverse map keyed by *referenced id string* (any
                                              position that holds an id — see `OutRef.role`)

### Outbound refs — what is indexed vs what is queried

Two distinct concerns, exactly as in Plan 2:

1. **Maintenance / reverse-ref tracking (must be complete).** `rename` must rewrite every
   position that holds the old id: `node.relations` (both `target` **and** `source`), membership
   `members` (list values and dict values), and membership `edges` (both `source` **and**
   `target`). So `outRefs` / `inRefs` track an `OutRef` for **each such position**, enabling
   O(degree) rename instead of an O(corpus) scan.
2. **Public graph queries (relations-only).** `outbound()` / `inbound()` expose **`Relation`-primitive
   edges only**, resolved to uids. Membership members/edges are tracked for rename but are **not**
   exposed as public graph edges in this plan. Membership traversal is deferred.

A single `Relation` with an explicit non-container `source` contributes two `OutRef`s (one
`relation_source`, one `relation_target`); a membership edge likewise contributes two.

`OutRef.role` is purely an indexing/rename detail. The public queries are defined semantically
over **distinct `Relation` objects**, not over `OutRef` rows (§5), so a relation never appears
twice and a relation whose `source` is a non-container node still attributes correctly.

### TypeScript-specific: relation dedup

Python dedupes relations in the graph queries via `id(relation)` (object identity). In TypeScript
the equivalent is a `Set<Relation>` keyed by reference: each `OutRef.relation` holds the **same
object reference** as the owning node's relation, so reference-based set membership is the exact
analog of Python's `id()` dedup. The index never clones `Relation` objects.

### Resolution

```typescript
resolveUid(ref: string): string | null
  // idToUid first; then deprecatedToUid; else null
```

`Corpus` raises `RefError` when this returns `null`.

### Collision

`assertAddable` is the **collision gate** — `upsert` is mechanical and never raises. Every claimed
id (the live `id` plus each `deprecatedId`) of an *added* node must belong to exactly one uid;
`assertAddable` enforces this via O(1) map lookups:

- a claimed id already mapped to a *different* uid → `CollisionError`;
- a uid already mapped to a *different* live id (the rename-misuse case) → `CollisionError`.

This split matches Python (`assert_addable` is the gate; `upsert` is mechanical/non-raising) and
is **load-bearing for `rename`**: `Corpus.rename` changes a uid's live id and then calls
`index.upsert(node)` *after* disk writes have begun. If `upsert` itself enforced "uid already
mapped to a different live id", rename would raise mid-commit. So the gate lives only in
`assertAddable`, which `build` and `Corpus.add` call *before* `upsert`; rename never calls it
(it has already collision-checked `newId` against the index in step 1).

### Maintenance ops

```typescript
static build(nodes: Iterable<Node>): Index   // assertAddable then upsert per node; raises CollisionError on a duplicate uid
assertAddable(node: Node): void               // collision gate (see above); raises CollisionError. Does NOT mutate
upsert(node: Node): void                      // mechanical add-or-replace; updates all maps + reverse refs; never raises
remove(uid: string): void                     // drop the node's OWN contributions only
```

`build` calls `assertAddable(node)` before `upsert(node)` for each node (a duplicate uid is caught
by `assertAddable`'s second clause). `Corpus.add` does the same. `upsert` is replace-safe:
re-indexing an existing uid first removes its old ref contributions, then adds the new ones, so the
maps never leak stale entries.

`remove(uid)` deletes only what the removed node itself contributed: its `byUid` entry, its
`idToUid` / `deprecatedToUid` identity claims, and the `inRefs` entries it contributed as a
*source* (its outbound refs). It must **not** drop `inRefs` entries that surviving referrers
contributed pointing *at* the removed node's ids — those references still exist on disk, so they
become **dangling** and must remain visible to `dangling()` and consistent with a fresh rebuild.

### Graph queries

```typescript
outboundEdges(uid: string): ResolvedEdge[]    // distinct relations whose source resolves to uid
inboundEdges(uid: string): ResolvedEdge[]     // distinct relations whose target resolves to uid
danglingEdges(): ResolvedEdge[]               // corpus-wide: relations whose target resolves to no uid
```

`inboundEdges` is merged across every written ref that resolves to that uid, so an edge still
written as a deprecated id is included in the inbound set of the live uid.

## 5. `Corpus` — public API (`ts/src/corpus.ts`)

```typescript
class Corpus {
  constructor(root: string, registry?: Registry)   // build Store, scan corpus, build Index

  add(node: Node): Node             // registry?.validate; index.assertAddable; store.writeFile; index.upsert
  get(ref: string): Node            // resolveUid → live id → store.readFile
  resolve(ref: string): Node        // alias of get; RefError if unresolved
  delete(id: string): void          // store.deleteFile + index.remove; live-id-only
  all(): Node[]                     // passthrough to store.allNodes

  // graph queries — input ref must resolve (live or via deprecatedIds); else RefError:
  outbound(ref: string): ResolvedEdge[]
  inbound(ref: string): ResolvedEdge[]
  neighbors(ref: string): Node[]    // distinct resolved neighbors (outbound + inbound), sorted
  dangling(): ResolvedEdge[]        // corpus-wide: relations whose target resolves to no uid

  rename(oldId: string, newId: string): Node
}
```

**Graph queries are uid-based and defined over distinct `Relation` objects.** `outbound(ref)` and
`inbound(ref)` first resolve `ref` to a uid; a ref that resolves to no uid raises `RefError`
(distinct from a resolvable node that simply has no edges). Each `ResolvedEdge` re-resolves its
endpoints to uids.

**Dangling-target semantics:** because `inbound` is keyed on the *target's* uid, it can only
return edges to a node that still resolves; it cannot surface edges to a fully-deleted id. Edges
whose target no longer resolves are surfaced by `outbound(existingSource)` (with
`targetUid = null`) and enumerated corpus-wide by `dangling()`. A dangling target is never an
error.

### Shared rewrite helper

A module-level `rewriteRefs(node, oldId, newId)` consolidates the two rewrite passes that lived
separately in the fat `Store` (`rewriteRelations` + `rewriteMembership`) into the single helper
Python's `_rewrite_refs` uses. It rewrites, in place: `relations` `source`/`target`, membership
`members` (list values and dict values), and membership `edges` `source`/`target`.

### `rename` flow (the O(degree) payoff)

Mirrors Plan 2 exactly:

1. **`oldId` must be a live id.** If `oldId` is not in `index.idToUid`, raise `RefError` and do
   nothing — rename is live-id-only, consistent with `delete`. Then collision-check `newId`
   (`index.resolveUid(newId)` must be `null`, else `CollisionError`).
2. **Snapshot the referrer set first.** Collect `{inref.sourceUid}` from `index.inRefs.get(oldId)`
   into a deduplicated set *before* any index mutation — the rename loop calls `index.upsert`,
   which rewrites `inRefs`, so iterating the live structure would skip or double-process entries.
   The renamed node's own uid is included if it self-references.
3. Read the node, set `id = newId`, `kind = NodeId.parse(newId).kind`, append `oldId` to
   `deprecatedIds` (if absent). **Rewrite the renamed node's own `oldId` references too** via
   `rewriteRefs`, so a relation whose normalized `source` was `oldId` does not serialize a stale
   explicit `source: oldId`.
4. For each *other* referrer uid in the snapshot, load that referrer (`store.readFile` by its live
   id from `index.byUid`) and `rewriteRefs` it.
5. **Validate all writes before any write** (fail-early, no partial rename): if a `Registry` is
   present, `validate` the renamed node and every referrer first.
6. **Commit:** `store.writeFile(node)` first, then `store.deleteFile(oldId)` if the path changed
   (crash-atomic ordering, matching the kernel's hardened rename); `index.upsert(node)`; then for
   each referrer `store.writeFile` + `index.upsert`. Both the renamed node and every referrer are
   written exactly once.

This replaces the fat `Store`'s `rewriteInbound` whole-corpus scan with a targeted walk of the
known referrers.

## 6. Core correctness invariant

The spec's promise is "incremental updates == fully rebuildable from the files." This is a
**tested property**:

> After any sequence of `Corpus` mutations, the live in-memory index must equal a fresh
> `Index.build(store.allNodes())`.

Equality is defined over all four maps (`byUid`, `idToUid`, `deprecatedToUid`, `inRefs`). The
scalar maps compare directly; the **list-valued** structures (`outRefs`, `inRefs`) compare as
**normalized multisets** — incremental insertion order differs from rebuild scan order even when
the index is semantically identical, so the property test normalizes each ref list to a sorted
multiset of stable keys before comparing.

The key **must include the relation payload**, not just `(ref, role, sourceUid)`. The bare triple
omits the `Relation` fields, so a stale `predicate` / `directed` / `weight` / `attrs` left behind
by a buggy incremental rewrite would pass undetected; and comparing the `Relation` *objects*
directly gives false negatives, because live vs freshly-rebuilt indexes hold distinct object
references. So, mirroring the Python plan, the key embeds a **`relationSignature`** — a
canonicalized tuple of `(source, predicate, target, directed, weight, canonicalized attrs)` (the
same shape the Plan-4 canonical oracle uses for a relation, with `attrs` key-sorted) — or `null`
for non-relation roles. The full key is therefore `(ref, role, sourceUid, relationSignature)`.
This directly catches incremental-maintenance bugs — the main risk of the in-memory+incremental
choice.

## 7. Cross-language rename parity

In-memory derived structures have no new on-disk format, so the single-node format oracle from
Plan 4 already locks the disk format. The one *behavioral* surface worth cross-language pinning is
`rename`, which rewrites files. This plan adds a corpus-level parity check, consistent with Plan
4's **semantic (not byte-identical)** parity discipline.

Shared artifacts under root `fixtures/corpus/`:

- A committed **multi-node source corpus** — a rename target plus referrers that exercise every
  rewrite position: a `Relation` target, a `Relation` with explicit `source`, a membership
  `member`, and a membership `edge` (both `source` and `target`). One markdown file per node, in
  the on-disk `kind/slug.md` layout.
- A committed **post-rename canonical-JSON oracle** — the whole corpus after one fixed rename
  (`topic:old` → `topic:new`), expressed as a list of canonical node forms **sorted by id**,
  reusing Plan 4's canonical-node oracle extended corpus-wide.

Both languages run the same check: copy the fixture corpus into a temp dir, construct a `Corpus`,
run the fixed `rename`, canonicalize every node, sort by id, and assert equality with the shared
oracle. Because both languages compare against **one** oracle, agreement with the oracle
guarantees cross-language agreement — no direct A-emit / B-parse cross-diff is needed.

The source corpus and the oracle are both committed. A drift in either language's `rename`
(structural or on-disk) fails that language's parity check; no separate currency guard is needed
beyond the two checks.

## 8. Error handling

Reuses the existing `nodes.kernel` error classes only — **no new error types**:

- Unresolved ref (`get` / `resolve`, or a graph query whose *input* ref does not resolve) →
  `RefError`.
- Identity collision (`add` / `rename`) → `CollisionError`.
- **Dangling edges are a normal state**, not an error: a relation whose target ref does not
  resolve is returned by `outbound(existingSource)` and `dangling()` with `targetUid = null`.
  Graph queries never raise on a dangling *target*.

## 9. Testing strategy

- **`structural-index.test.ts` (unit):** resolution order (live id beats deprecated id); collision
  detection (both forms); `outboundEdges` / `inboundEdges` relations-only; dangling-target
  handling; `upsert` replace-safety; `remove` leaves no stale map entries (and leaves surviving
  inbound refs as dangling).
- **`corpus.test.ts` (integration):** `add` / `get` / `rename` / `delete` round-trips;
  deprecated-id resolution after rename; collision-on-add; `delete` live-id-only; rename rewrites
  every referrer (relations + membership members + membership edges). Plus the tightened cases:
  - **renamed node's own relations** — explicit `source == oldId` serializes with the container
    source after rename (no stale `source: oldId`).
  - **edge-source rename** — renaming an id used as a membership *edge source* finds and rewrites
    the containing structure node.
  - **multi-ref referrer** — a referrer pointing at `oldId` from several positions is rewritten and
    written exactly once (snapshot/dedup).
  - **inbound across a deprecated id** — `inbound(newId)` includes an edge still written as `oldId`.
  - **rename rejects a deprecated/unknown `oldId`** — `RefError`, no file written or deleted.
  - **delete leaves dangling inbound** — after deleting a target, `outbound(source)` reports the
    edge with `targetUid = null`, `dangling()` lists it, `inbound` on the deleted id raises
    `RefError`, and a fresh rebuild matches the live index.
- **Rebuild-equivalence property test (§6):** drive a sequence of mutations (add/rename/delete,
  including deletes that strand inbound refs), assert the live index equals a fresh rebuild from
  disk.
- **Cross-language rename parity (§7):** the TS half of the shared-oracle check; the Python half is
  added to the Python parity suite.
- **`store.test.ts` migration:** the fat-`Store` cases (collision via `write`, `resolve`, `rename`)
  relocate up to `corpus.test.ts`; `store.test.ts` shrinks to file mechanics (`pathFor`,
  `writeFile`/`readFile`/`deleteFile`, `allNodes`).

## 10. Barrel & deferrals

`ts/src/index.ts` barrel adds: `Corpus`; `Index` and its types (`ResolvedEdge`, `Role`, `OutRef`,
`InRef`, `IndexEntry`). `Store` stays exported (now slimmed). The fat-`Store` methods removed in §3
disappear from the public surface.

**Deferred (intentional, matching Plan 2):** on-disk index persistence; full-text search;
embeddings / similarity; public membership-graph traversal queries; the knowledge vocab (its own
TS plan).
