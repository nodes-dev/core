# nodes — Structural Index (Plan 2) Design

**Status:** approved 2026-06-21
**Builds on:** `docs/specs/2026-06-21-nodes-substrate-design.md` §5 (Derived index & fast I/O)
**Supersedes for §5:** scopes the spec's four-capability "derived index" down to its structural core.

## 1. Purpose & scope

The substrate spec's §5 bundles four independent capabilities under "derived index":
full-text search, the resolved relation graph, alias/slug→id/uid resolution, and an
embedding/similarity store. They have very different dependencies and risk profiles, so they
are split across plans.

**Plan 2 delivers the structural index only** — pure-Python, no external dependencies:

- **Resolution:** `id` / `deprecated_id` → `uid`, O(1), replacing the kernel `Store`'s linear scans.
- **Resolved relations graph:** outbound / inbound queries over the `Relation` primitive.

**Out of scope (later plans):** full-text search (needs a search backend); embeddings/similarity
(needs an embedding model); on-disk persistence of the index; membership-graph *traversal*
queries (tree descendants, DAG reachability); the TypeScript port.

The index remains what the spec promises: a **disposable, fully rebuildable cache** over the
canonical markdown files.

## 2. Architecture & layering

The index is domain-free, so it lives in `nodes.kernel` (the substrate spec lists the derived
index as kernel scope). Two new modules, plus a slimming of the existing `store.py`:

- **`src/nodes/kernel/index.py` — `Index`.** Pure in-memory maps + resolved relation graph.
  Knows nothing about files. Built from a list of `Node`s; supports incremental `upsert` /
  `remove`; answers resolution and graph queries.
- **`src/nodes/kernel/corpus.py` — `Corpus`.** The coordinator and primary public API. Owns a
  `Store` + an `Index`. Every mutation (`add` / `rename` / `delete`) goes through it: collision
  check against the index, the `Store` file op, then the index update.
- **`src/nodes/kernel/store.py` — slimmed.** Reduced to pure file mechanics. The cross-corpus
  logic (`resolve()`'s deprecated scan, `_assert_no_identity_collision`, `rename` +
  `_rewrite_*`, `_id_owner_uid`) **migrates up** into `Corpus` / `Index`. No compatibility shim
  is left behind (greenfield repo, no external consumers).

### Lifecycle

In-memory, incremental. `Corpus(root)` builds the `Store`, scans the corpus once
(`store.all_nodes()`), and builds the `Index`. Thereafter, `Corpus` mutations update the live
index incrementally — no full rebuild per mutation, no disk persistence. The index is always
reconstructable from the files (see §6 invariant).

## 3. `Store` after slimming

`Store` keeps only mechanical, single-file or whole-corpus-scan operations:

```
Store(root: Path)
  .path_for(id) -> Path
  .write_file(node) -> Path          # mechanical write; NO collision check (was _write_file)
  .read_file(id) -> Node             # by path_for(id) only; RefError if no file. NO deprecated scan
  .delete_file(id) -> None           # unlink; RefError if absent
  .all_nodes() -> list[Node]         # corpus scan, used to build/rebuild the Index
```

Removed from `Store` (moved up): `write` (collision), `resolve` (deprecated scan), `read`,
`rename` and `_rewrite_relations` / `_rewrite_membership` / `_rewrite_inbound`,
`_assert_no_identity_collision`, `_claimed_ids`, `_id_owner_uid`.

## 4. `Index`

### What it holds

A lightweight entry per node — **not** the prose body (the body stays sourced from disk via
`Store`, keeping a single source of truth):

```
IndexEntry:
  uid: str
  id: str
  kind: str
  deprecated_ids: frozenset[str]
  out_refs: list[OutRef]             # outbound refs this node points at (see below)
```

Maps:

- `by_uid: dict[str, IndexEntry]`
- `id_to_uid: dict[str, str]`            # live ids
- `deprecated_to_uid: dict[str, str]`    # stale-ref resolution; a live id ALWAYS wins
- `in_refs: dict[str, list[InRef]]`      # reverse map keyed by *target ref string*

```
InRef:
  source_uid: str          # the node that points at this target ref
  out_ref: OutRef          # the specific outbound ref (relation or membership)
```

### Outbound refs — what is indexed vs what is queried

There are two distinct concerns:

1. **Maintenance / reverse-ref tracking (must be complete).** `rename` must rewrite every place
   that points at the old id. The kernel rewrites three kinds of outbound ref: `node.relations`,
   membership `members` (set/list/dict), and membership `edges`. So `out_refs` /
   `in_refs` track **all three**, enabling O(degree) rename instead of an O(corpus) scan.
2. **Public graph queries (relations-only).** `outbound()` / `inbound()` expose **`Relation`-primitive
   edges only**, resolved to uids. Membership members/edges are tracked for rename but are **not**
   exposed as public graph edges in Plan 2. Membership traversal is deferred to the layer that
   consumes it.

`OutRef` records enough to distinguish a relation edge from a membership ref and to resolve its
target:

```
OutRef:
  ref: str                 # the target id string as written
  origin: "relation" | "membership"
  relation: Relation | None    # present when origin == "relation"
```

### Resolution

```
Index.resolve_uid(ref) -> str | None
  # id_to_uid first; then deprecated_to_uid; else None
```

`Corpus` raises `RefError` when this returns `None`.

### Collision

On `upsert`, every claimed id (the live `id` plus each `deprecated_id`) must belong to exactly
one uid. Violations raise `CollisionError` — same semantics as the kernel's
`_assert_no_identity_collision`, enforced via O(1) map lookups:

- a claimed id already mapped to a *different* uid → `CollisionError`;
- a uid already mapped to a *different* live id (the rename-misuse case) → `CollisionError`.

### Maintenance ops

```
Index.build(nodes: Iterable[Node]) -> Index   # classmethod / constructor
Index.upsert(node: Node) -> None              # add or replace; updates all maps + reverse refs
Index.remove(uid: str) -> None                # drop entry; updates all maps + reverse refs
```

`upsert` is replace-safe: re-indexing an existing uid first removes its old ref contributions,
then adds the new ones, so the maps never leak stale entries.

## 5. `Corpus` — public API

```
Corpus(root: Path)                       # build Store, scan corpus, build Index

  .add(node) -> Node                      # index collision-check; store.write_file; index.upsert
  .get(ref) -> Node                       # index.resolve_uid → live id → store.read_file
  .resolve(ref) -> Node                   # alias of get; RefError if unresolved
  .rename(old_id, new_id) -> Node         # collision-check; write new + delete old file;
                                          #   rewrite ONLY the referrers in_refs names (O(degree));
                                          #   reindex affected nodes
  .delete(id) -> None                     # store.delete_file + index.remove; live-id-only (documented)
  .all() -> list[Node]                    # passthrough to store.all_nodes

  # graph queries (resolved to uids; dangling targets returned, not raised):
  .outbound(ref) -> list[ResolvedEdge]
  .inbound(ref) -> list[ResolvedEdge]
  .neighbors(ref) -> list[Node]           # distinct resolved neighbors (outbound + inbound)
  .dangling() -> list[ResolvedEdge]       # edges whose target ref resolves to nothing
```

```
ResolvedEdge:
  relation: Relation
  source_uid: str
  target_uid: str | None        # None when the target ref is dangling
```

### `rename` flow (the O(degree) payoff)

1. Collision-check `new_id` against the index.
2. Read the node, set `id = new_id`, `kind = parse(new_id).kind`, append `old_id` to
   `deprecated_ids`.
3. `store.write_file(new)` first, then `store.delete_file(old)` if the path changed
   (crash-atomic ordering, matching the kernel's hardened rename).
4. For each `(referrer_uid, ref)` in `index.in_refs[old_id]`, load that referrer, rewrite its
   `relations` + membership `members` + membership `edges` from `old_id`→`new_id`,
   `store.write_file` it, and `index.upsert` it.
5. `index.upsert` the renamed node.

This replaces the kernel's `_rewrite_inbound` whole-corpus scan with a targeted walk of the
known referrers.

## 6. Core correctness invariant

The spec's promise is "incremental updates == fully rebuildable from the files." This is a
**tested property**:

> After any sequence of `Corpus` mutations, the live in-memory index must equal a fresh
> `Index.build(store.all_nodes())`.

Equality is defined over all four maps (`by_uid`, `id_to_uid`, `deprecated_to_uid`, `in_refs`).
This directly catches incremental-maintenance bugs — the main risk of the in-memory+incremental
choice.

## 7. Error handling

- Unresolved ref (`get` / `resolve`) → `RefError`.
- Identity collision (`add` / `rename`) → `CollisionError`.
- **Dangling edges are a normal state**, not an error: a relation whose target ref does not
  resolve (target not yet created, or deleted) is returned by `outbound` / `inbound` /
  `dangling` with `target_uid = None`. Resolution and graph queries never raise on dangling refs.

All error types are the existing `nodes.kernel.errors` classes — no new error types.

## 8. Testing strategy

- **`Index` unit tests:** resolution order (live id beats deprecated id); collision detection
  (both forms); `outbound` / `inbound` relations-only edges; dangling-target handling;
  `upsert` replace-safety and `remove` leave no stale map entries.
- **`Corpus` integration tests:** `add` / `get` / `rename` / `delete` round-trips; deprecated-id
  resolution after rename; collision-on-add; `delete` live-id-only behavior; rename rewrites
  every referrer (relations + membership members + membership edges) — these port up from the
  kernel's existing `Store` rename tests.
- **Rebuild-equivalence property test (§6):** drive a sequence of mutations, assert live index
  equals a fresh rebuild from disk.
- **Migration:** Plan 1's `Store` tests for `resolve` / collision / `rename` move up to target
  `Corpus`; `Store`'s own tests shrink to file mechanics. The existing suite stays green
  (adjusted for the relocated API), plus the new `Index` / `Corpus` / property tests.

## 9. Known deferrals (intentional)

Disk persistence of the index; full-text search; embeddings / similarity; public
membership-graph traversal queries; the TypeScript port. Each becomes its own later plan if a
consumer needs it.
