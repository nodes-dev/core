# Mindful v6 — SP1: Core Abstraction (Structural Shapes + Mindful Profile)

**Status:** Design (approved in brainstorming; pending written-spec review)
**Date:** 2026-06-23
**Repos:** `~/d/nodes` (kernel redesign), `~/d/mindful/v6` (new package)

**Goal:** Give mindful v6 its data foundation on the `nodes` kernel: redesign the kernel's
structural shapes so that *membership* (scope) is cleanly separated from *form* (shape-specific
structure), then build a small headless mindful package (`thought`/`mindmap`/`journal` + a
form-maintaining API) on top.

**Architecture:** Two coupled parts, implemented in order. **Part A** is a clean breaking redesign
of structural shapes in `nodes` (Python *and* TypeScript together): a `Structure` is a `Node` of a
registered *shape*, carrying a scope-only `membership` facet plus a shape-owned *form* facet. **Part
B** is a new TypeScript package at `~/d/mindful/v6` that registers the mindful kinds and exposes a
headless `Mindful` API over a `nodes` `Corpus`, consuming `@nodes/kernel` over a local `file:`
dependency.

**Tech stack:** TypeScript (Node ≥20, ESM, `.js` import extensions, zod, biome, vitest) for the
mindful package and the TS kernel; Python (kernel parity) for Part A. `@nodes/kernel` gains a real
`tsc` build so it is consumable as a package.

---

## Global Constraints

- **Structure contract (the spine):** `Structure Node = shape/kind + membership facet +
  shape-specific form facet(s)`. `Relation` remains the universal **binary** link primitive (tags,
  graph edges, future morphisms reuse its `source`/`target`), **but `Structure` is NOT defined in
  terms of `Relation`.** A graph is one possible shape over members, not the substrate model for all
  structures.
- **Membership = scope only:** `{ members: string[] }`, semantically an unordered unique set. Order,
  edges, keys, and every other form detail live in form facets — **never** leak through
  `membership.members` position.
- **Form is shape-owned:** each registered shape declares the form facet(s) it requires, its
  validation invariants, and any relation predicates it uses. Unknown shape or malformed form **fails
  early**.
- **Open shape family:** `set/list/dict/graph/dag/tree` are the built-ins; `quotient`, `complex`
  (simplices), `category` (morphisms + composition), `algebra` (operations) stay additive later
  without reworking the core. SP1 changes the *mechanism*, not the built-in roster.
- **Clean breaking change:** no compatibility layer, no corpus migration. `~/d/mindful/v6` is empty
  and `science` does not use shapes yet, so there is no real data to migrate. Existing built-ins are
  ported to the new model before mindful is scaffolded.
- **Parity:** Part A lands in Python and TS together (a membership-schema change must not fork the
  on-disk format across kernels).
- **Dependency direction:** `mindful/v6 → @nodes/kernel` only; the kernel never imports mindful.
- **Singular shape:** a kind adopts **zero or one** shape in SP1 (no multi-trait composition).

---

## 1. Context & Motivation

`nodes` already ships a structural-shape system (`shapes.py` / `shapes.ts`, tested, merged with the
structural-index work). Its `MEMBERSHIP` facet bundles three concerns into one payload:

```ts
// CURRENT (to be replaced)
MembershipSchema = z.object({
  shape: z.string(),                 // shape as a string field
  members: z.array | z.record,
  edges: z.array(RelationSchema),    // edges bundled into membership
});
// built-ins registered directly as kinds: set, list, dict, graph, dag, tree
```

This violates the structure contract in three concrete ways:

1. **Form leaks into scope** — `edges` rides inside `membership` (and on `set`/`list`/`dict`, where
   it is meaningless).
2. **`list` has no order** — order is implicit in `members` array position; `list` is not even given
   the uniqueness invariant. This is the order-leak the contract forbids.
3. **`shape` is a string field**, not a registered shape that *owns* its form facet and invariants.

SP1 corrects this at the kernel level (it is a format/kernel correction, not merely a mindful
dependency) and then builds the mindful layer on the corrected foundation.

---

## 2. Part A — Kernel Structural-Shape Redesign

### 2.1 Shape registry: `ShapeSpec`, `KindSpec.shape`, composition

A **shape** is a first-class registered trait that owns structural form. A **kind** optionally adopts
one shape; the registry composes the shape's requirements into the kind's validation.

```ts
interface ShapeSpec {
  name: string;
  requiredFacets: Set<string>;       // form facets the shape requires (plus membership)
  optionalFacets?: Set<string>;
  invariants: Invariant[];           // shape-owned, run before kind invariants
}

interface KindSpec {
  name: string;
  shape?: string;                    // names a registered shape; ≤1 in SP1
  requiredFacets?: Set<string>;      // domain facets the kind adds
  optionalFacets?: Set<string>;
  invariants?: Invariant[];
}
```

**Registry behavior:**

- `registerShape(spec: ShapeSpec)` registers reusable structural form.
- `register(spec: KindSpec)` **fails early** (`UnknownKindError`/`ValidationError`) if `spec.shape`
  names a shape that is not registered.
- `validate(node)` composes, for a node whose kind adopts shape `S`:
  - required facets = `S.requiredFacets ∪ kind.requiredFacets`
  - optional facets = `S.optionalFacets ∪ kind.optionalFacets`
  - invariants = `S.invariants` then `kind.invariants` (shape first)
  - the existing "unexpected facet" check uses the composed allowed-set.
- **On disk there is no `shape` field.** A structure's shape is inferred from its registered kind.

Built-ins are registered as **both** shape-specs and convenience shape-kinds:

```text
registerShape({ name: "graph", requiredFacets: {membership, edges}, invariants: [...] })
register({ name: "graph", shape: "graph" })     // node kind:"graph" → id graph:foo
```

`registerBuiltinShapes(reg)` registers all six shape-specs and their convenience kinds.

### 2.2 Facets

`membership` becomes scope-only; each form facet is owned by the shapes that require it.

| Facet key    | Payload                              | Required by         | Purpose                                  |
|--------------|--------------------------------------|---------------------|------------------------------------------|
| `membership` | `{ members: string[] }`              | all shapes          | scope — unique, **unordered**            |
| `edges`      | `{ edges: Relation[] }`              | `graph`,`dag`,`tree`| binary edge form (endpoints ∈ members)   |
| `order`      | `{ order: string[] }`                | `list`              | explicit total order (permutation)       |
| `keys`       | `{ keys: Record<string,string> }`    | `dict`              | key → member-ref map                     |
| *(none)*     | —                                    | `set`               | membership-only                          |

Notes:
- Edges live in the `edges` **form facet**, not in the node's top-level `relations:` and not in the
  global relation graph — structure edges are scoped to the structure.
- `edges` is shared by `graph`/`dag`/`tree`; the shapes differ only by invariants.

### 2.3 Built-in shapes (migrated)

| Shape  | Required facets        | Invariants                                                        |
|--------|------------------------|------------------------------------------------------------------|
| `set`  | `membership`           | `uniqueMembers`                                                   |
| `list` | `membership`,`order`   | `uniqueMembers`, `orderIsPermutationOfMembers`                   |
| `dict` | `membership`,`keys`    | `uniqueMembers`, `keyValuesAreMembers`                            |
| `graph`| `membership`,`edges`   | `uniqueMembers`, `edgeEndpointsAreMembers`                        |
| `dag`  | `membership`,`edges`   | `uniqueMembers`, `edgeEndpointsAreMembers`, `acyclic`            |
| `tree` | `membership`,`edges`   | `uniqueMembers`, `edgeEndpointsAreMembers`, `acyclic`, `singleParent` |

### 2.4 Invariants (fail-early)

- `uniqueMembers` — `members` has no duplicates.
- `edgeEndpointsAreMembers` — every `edge.source` and `edge.target` ∈ `members`.
- `orderIsPermutationOfMembers` — `order` and `members` are the same set and same length. **This is
  what closes the order-leak.**
- `keyValuesAreMembers` — every value of `keys` ∈ `members`.
- `acyclic` — the `edges` digraph has no cycle.
- `singleParent` — no member is the `target` of more than one edge.

Malformed form facets surface as `FacetError`; invariant violations as `InvariantError`; unknown kind
as `UnknownKindError` — all before any mutation.

### 2.5 Ripple (in-kernel consumers)

Changing the membership schema requires updating everything that assumed `{shape, members, edges}`:

- **`shapes.{py,ts}`** — new scope-only `membership` schema + the form facets, invariants, shape
  registry, and `registerBuiltinShapes`.
- **`registry.{py,ts}`** — `ShapeSpec`, `KindSpec.shape`, `registerShape`, composed `validate`.
- **Corpus rename ref-rewriting** — stop treating `membership.edges` as the universal edge source.
  Rewrite refs from `membership.members` **plus the registered/known form facets** (`edges` endpoints,
  `order` entries, `keys` values) when a referenced id is renamed.
- **Structural index / snapshot** — update membership-ref extraction and snapshot validation away
  from hard-coded `{shape,members,edges}`; read edges from the `edges` form facet.
- **Tests, fixtures, `docs/format.md`** — update all graph/list/dict fixtures and parity
  expectations to the new model.

Implemented in Python and TS together.

---

## 3. Part B — Mindful Profile & Headless Package

### 3.1 Repo layout & dependency

`@nodes/kernel` gains a real build so it is consumable as a package:

- `tsc` emits `dist/` (`.js` + `.d.ts`); `package.json` gets `exports`/`types`/`files`, `main` →
  `dist`. (Today `main` is `src/index.ts` with no build.)
- A `build` script; mindful installs the built package.

```text
~/d/nodes/ts/                      # @nodes/kernel (domain-free)
  src/{registry,shapes,...}.ts     # Part A lives here
  dist/                            # built output (new)

~/d/mindful/v6/                    # new TypeScript package
  src/
    kinds.ts                       # THOUGHT/MINDMAP/JOURNAL constants + KindSpecs
    profile.ts                     # registerMindfulProfile(reg)
    api.ts                         # Mindful class over Corpus
    index.ts
  tests/
  package.json                     # "@nodes/kernel": "file:../../nodes/ts"
```

Dependency direction is one-way: `mindful/v6 → @nodes/kernel`; the kernel never imports mindful.

### 3.2 Kinds & profile

```ts
export const THOUGHT = "thought";
export const MINDMAP = "mindmap";
export const JOURNAL = "journal";

// kinds.ts (KindSpecs)
{ name: THOUGHT }                       // no shape, no required facets in SP1
{ name: MINDMAP, shape: "graph" }       // first-class kind adopting the graph shape → mindmap:garden
{ name: JOURNAL, shape: "list" }        // → journal:2026

export function registerMindfulProfile(reg: Registry): void {
  // assumes registerBuiltinShapes(reg) already ran
  reg.register(thoughtSpec);
  reg.register(mindmapSpec);
  reg.register(journalSpec);
}
```

`thought` is its own kind now (≈ `note`); SP2 will add `visualIdentity` as its required facet
(`thought = note + VisualIdentity`). `mindmap`/`journal` can later add domain facets (`scene`,
`layout`, …) without touching `graph`/`list`.

### 3.3 Headless `Mindful` API

`Mindful` wraps a `Corpus` (built with the mindful registry and an optional embedder). **Its whole
reason to exist is to encapsulate form-facet maintenance** so callers never hand-build
`membership`/`edges`/`order`.

| Group              | Methods                                                                                          |
|--------------------|--------------------------------------------------------------------------------------------------|
| Thoughts           | `capture({title, body, tags?}) → thought`, `get(id)`, `edit(id, patch)`, `delete(id)`            |
| Mindmaps (`graph`) | `createMindmap({title})`, `addThought(mapId, thoughtId)`, `link(mapId, fromId, toId, predicate?)`, `unlink(...)`, `removeThought(...)`, `mindmapEdges(mapId)` — maintains `membership` + `edges`, validates endpoints |
| Journals (`list`)  | `createJournal({title})`, `append(journalId, thoughtId)`, `reorder(journalId, order)`, `remove(...)` — maintains `membership` + `order` together |
| Tags               | `tag(thoughtId, name)` and `tags` at capture                                                     |
| Queries            | `search(q)`, `similar(thoughtId)` / `similarText(t)`, `related(thoughtId)`, `allThoughts()`      |

**Two distinct graphs, deliberately:** (1) the **global relation graph** — `relatesTo` links from
tags/relations between thoughts — is what the kernel's `outbound`/`inbound`/`neighbors` traverse;
the mindful API surfaces it as `related(thoughtId)`. (2) A **mindmap's internal edges** live in that
mindmap's `edges` form facet, scoped to the structure and *not* part of the global graph; they are
read via `mindmapEdges(mapId)` (or the returned mindmap node), never via `related`. This is the
direct consequence of "structure edges are shape-owned, not the node's own relations."

All mutations go through `Corpus`, preserving its fail-before-write ordering and persistence.

### 3.4 Tags

A tag links one thought to an existing node, resolved by alias. `tag(thoughtId, name)` builds an
alias map from the corpus and calls the kernel's `tagToRelation`, producing a `relatesTo` relation.
**Unresolved tags fail early (`RefError`)** — SP1 does not auto-create nodes (that, and a `topic`
kind, are deferred).

### 3.5 Embedder seam

`Mindful` accepts an optional `Embedder` (the kernel seam: `cacheNamespace` + `embed(texts)`). SP1
defines the seam only and tests with a **deterministic stub embedder**; the real model is an
SP2/runtime choice. `search` and graph traversal work with no embedder; `similar*` require one and
otherwise raise the kernel's `EmbedderRequiredError`.

---

## 4. Error Handling

Fail early everywhere; no silent fallbacks (the existing cache-rebuild fallback in `loadSnapshot` is
unaffected). Specifically: `UnknownKindError` on unknown kind or unknown adopted shape; `FacetError`
on missing/malformed facet; `InvariantError` on form-invariant violation; `RefError` on unresolved
tag; `EmbedderRequiredError` on semantic queries without an embedder. All validation precedes any
disk write.

---

## 5. Testing Strategy

**Part A (kernel, Python + TS):**
- Shape registry: `registerShape`/`register` composition; `register` with unknown `shape` fails.
- Each built-in shape: valid construction; each invariant rejects its violation (duplicate members;
  edge endpoint not a member; `order` not a permutation; `keys` value not a member; cycle in `dag`;
  multi-parent in `tree`).
- Round-trip: build → `nodeToMarkdown` → parse → validate, with the new facets.
- Ripple: rename rewrites refs inside `edges`/`order`/`keys`; structural index/snapshot read the new
  form facets; cross-language parity fixtures updated.

**Part B (mindful, TS):**
- `registerMindfulProfile` registers the three kinds; `mindmap`/`journal` validate as graph/list.
- `Mindful` over a temp `Corpus`: capture/edit/delete; mindmap add/link/unlink maintains a valid
  `edges` facet; journal append/reorder maintains a valid `order` facet (order never via array
  position); `search` returns captured thoughts; `similar*` works with the stub embedder and raises
  without one; `tag` resolves an existing thought and throws `RefError` when unresolved.
- On-disk round-trip through the package API.

---

## 6. Implementation Sequencing

SP1 is naturally two plans, executed in order:

1. **Plan A — kernel structural-shape redesign** (`~/d/nodes`, Python + TS): §2. Independently
   testable; `science` benefits too. Must land before Part B.
2. **Plan B — mindful package** (`~/d/mindful/v6`, TS): §3, depends on Plan A and the `@nodes/kernel`
   build.

---

## 7. Out of Scope / Deferred

- **SP2:** the `visualIdentity` facet and identity-derivation model (`thought = note +
  VisualIdentity`).
- **SP3:** the renderer (2D "8-bit/chiptune" art, animation) and the CLI/TUI shell; natural-systems
  formula-viz integration.
- Additional shapes (`quotient`, `complex`, `category`, `algebra`) — the mechanism supports them;
  none are built here.
- The real embedder model; tag auto-creation and a `topic` kind; publishing `@nodes/kernel` to a
  registry; multi-shape kinds.

---

## 8. Decisions Log

1. Mindful profile + app target **TypeScript**; kernel shapes redesigned in **both** languages.
2. **Structure = shape + membership + form**; `Relation` is the universal binary primitive but
   structure is not defined via it.
3. `membership` = scope only (unique, unordered); form facets (`edges`/`order`/`keys`) are
   shape-owned; `set` is membership-only.
4. Shape adoption via **composable trait**: `ShapeSpec` + `KindSpec.shape` + registry composition;
   no on-disk `shape` field; `mindmap`/`journal` are first-class kinds adopting `graph`/`list`.
5. **Clean breaking change**, no compat layer, no migration; Python + TS in lockstep.
6. `thought` is its own kind now (≈ `note`); `visualIdentity` becomes its required facet in SP2.
7. Layout: domain-free `@nodes/kernel` (with a real build) + a new `~/d/mindful/v6` package over a
   `file:` dependency; one-way dependency.
8. Tags resolve by alias and **fail early** on miss; embedder is a seam (stub in tests), real model
   deferred.
