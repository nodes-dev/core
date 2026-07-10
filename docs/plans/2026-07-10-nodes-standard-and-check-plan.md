# Nodes Standard + Corpus Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the portable cross-language contract into a versioned normative standard (`docs/STANDARD.md`) with explicit parity tiers, add root `README.md` / `AGENTS.md` naming it the authority, retire `docs/format.md`, rename `docs/specs/` → `docs/designs/`, and close the read-boundary validation gap with `Registry.check` + `Corpus.check` in both kernels, pinned by a shared conformance fixture.

**Architecture:** Docs first (rename, standard, orientation files, stale-doc fixes), then code: a collecting `Registry.check(node) -> list[Violation]` beside the unchanged raising `validate`, consumed by a reporting `Corpus.check(registry=None) -> list[Finding]`; mirrored in TypeScript; both pinned by `fixtures/check-corpus/` + `fixtures/check.oracle.json`.

**Tech Stack:** Python ≥3.11 + Pydantic v2 + pytest/ruff/pyright via `uv` (run through `rtk`); TypeScript ESM + Zod + Vitest/Biome/tsc via npm.

**Design:** `docs/designs/2026-07-10-nodes-standard-and-check-design.md` (at `docs/specs/…` until Task 1 runs).

## Global Constraints

- Python gates run from `python/`: `rtk uv run --frozen pytest -q`, `rtk uv run --frozen ruff check .`, `rtk uv run --frozen pyright src`. TypeScript gates run from `ts/`: `npm test`, `npm run typecheck`, `npm run check`.
- Git commands go through `rtk` (e.g. `rtk git add …`). No AI-attribution trailers in commit messages.
- `Registry.validate` behavior (raise-at-first-violation, error classes, messages) MUST NOT change; the full existing suites stay green.
- `Corpus` construction semantics MUST NOT change (still fails hard on unparseable files and uid/id collisions; registry still not consulted at construction).
- Finding codes are exactly: `unknown-kind`, `facet-missing`, `facet-unexpected`, `facet-invalid`, `invariant-violated` (severity `error`) and `dangling-ref` (severity `warning`).
- Only kernel content errors convert to findings: `FacetError` → `facet-invalid`, `InvariantError` → `invariant-violated`. Any other exception from an invariant propagates.
- Finding order is `(ref, code, detail)` ascending; `message` is human-only, never sorted on, never in the oracle.
- Docs sweeps MUST NOT touch the two 2026-07-10 files (this plan and its design doc) — they intentionally reference the old paths they change.
- Filepaths written into docs use `~/d/nodes/...` (never `/home/keith/...` or `/mnt/ssd/Dropbox/...`).

---

### Task 1: Rename `docs/specs/` → `docs/designs/` + reference sweep

**Files:**
- Rename: `docs/specs/` → `docs/designs/` (all 11 files)
- Modify: every `docs/**/*.md` containing `docs/specs/` (except the two 2026-07-10 files)

**Interfaces:**
- Produces: the `docs/designs/` path used by Tasks 2–3 (STANDARD.md, README.md, AGENTS.md all reference it).

- [ ] **Step 1: Rename the directory**

From the repo root:

```bash
rtk git mv docs/specs docs/designs
```

- [ ] **Step 2: Sweep path references**

```bash
grep -rl 'docs/specs' docs --include='*.md' | grep -v '2026-07-10-nodes-standard-and-check' | xargs -r sed -i 's|docs/specs/|docs/designs/|g'
```

- [ ] **Step 3: Verify no stale references remain**

```bash
grep -rn 'docs/specs' docs | grep -v '2026-07-10-nodes-standard-and-check'
```

Expected: no output. (The 2026-07-10 design/plan mention `docs/specs` deliberately, describing this very change.)

- [ ] **Step 4: Commit**

```bash
rtk git add -A docs
rtk git commit -m "docs: rename specs/ to designs/ (dated design records)"
```

---

### Task 2: `docs/STANDARD.md` + retire `docs/format.md` + stale-doc notes

**Files:**
- Create: `docs/STANDARD.md`
- Delete: `docs/format.md`
- Modify: every `docs/**/*.md` referencing `format.md` (except the two 2026-07-10 files)
- Modify: `docs/designs/2026-06-21-nodes-substrate-design.md` (current-state note under §3.4)

**Interfaces:**
- Consumes: `docs/designs/` path from Task 1.
- Produces: `docs/STANDARD.md` — referenced by Tasks 3–4 and by the finding codes implemented in Tasks 5–9. Section numbers used later: §8 (corpus validity & checking), §11 (conformance fixtures).

- [ ] **Step 1: Create `docs/STANDARD.md`**

The content below absorbs all of `docs/format.md`, reorganized by topic and made normative. It is the complete file:

````markdown
# The nodes Standard

- **Spec version:** 1.0
- **Status:** Living standard — the authoritative definition of the portable `nodes` contract.
- **Implementations:** Python (`python/src/nodes/`), TypeScript (`ts/src/`).

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as
described in RFC 2119. Where a historical document in `docs/designs/` or `docs/plans/`
disagrees with this standard, this standard wins.

## 1. Scope & conformance

`nodes` is a problem-agnostic knowledge substrate: markdown files as canonical nodes,
typed relations, structural shapes, and rebuildable derived indexes. This document
defines everything a conforming implementation must agree on with the other language.

Guarantees fall into three conformance tiers:

- **Tier 1 — portable data contract.** The data model (§2), identity grammar and
  resolution (§3), on-disk format (§4), structural shapes (§5), validation model (§6),
  and corpus mutation semantics (§7). Implementations MUST agree exactly: a corpus
  written by one language MUST be readable and safely mutable by the other.
- **Tier 2 — pinned behavior.** Derived-index behavior and corpus checking (§8–§10):
  tokenizer, BM25F constants, ranking keys, similarity semantics, snapshot reconcile
  rules, and corpus-validity finding codes. Pinned by the conformance fixtures (§11).
  Parity is semantic — ranked ids, finding tuples, and 6-decimal score keys match; raw
  floats and serialized bytes need not.
- **Tier 3 — per-language surface.** Everything else (convenience APIs such as
  `idsByKind` / `allByKind`, corpus stat fingerprints). Out of scope for this standard;
  no parity obligation until the other language has a real consumer.

Byte-identical serialization is an explicit non-goal (PyYAML and the JS `yaml` emitter
format differently). Cross-language equivalence is defined over the canonical JSON
projection pinned by the fixtures (§11).

## 2. Data model

### 2.1 Node

The universal container. Fields:

| Field | Contract |
|-------|----------|
| `id` | Canonical `kind:slug` identifier (§3). Required. |
| `uid` | Immutable, corpus-unique opaque string; survives renames. Required. New nodes SHOULD mint 32-char lowercase hex (UUIDv4). |
| `kind` | Type name, resolved against a registry (§6). MUST equal the `id`'s kind segment. |
| `title` | Human-readable display title. Required. |
| `body` | Markdown content. May be empty. |
| `metadata` | `created` / `updated` (ISO `YYYY-MM-DD` dates, optional) and `version` (integer, default 1). |
| `relations` | Typed relations in normalized form (§2.2). |
| `facets` | Map of facet name → mapping payload (§2.3). |
| `deprecated_ids` | Previous ids retained after rename (§3). |

`related` is serialization sugar (§4.3), not a model field.

### 2.2 Relation

The single edge primitive:

```
Relation = { source, predicate, target, directed?, weight?, attrs? }
```

`source` and `target` are refs (§3). `predicate` is a free string — never enforced by
the kernel. `directed` defaults to `true`. The shape above is the **normalized**
(in-memory / indexed) form, where `source` is always explicit; serialized forms are
defined in §4.3. Untyped links use the reserved predicate `relatesTo`.

### 2.3 Facets

A facet is a named, typed payload attached to a node under `facets`. Payloads MUST be
mappings. Which facets a node may or must carry is decided by its kind's registry spec
(§6); facet payload schemas are enforced by invariants (e.g. the shape form facets §5,
the vocab `source` facet). Typed facet accessors MUST reject unknown payload keys
(fail-early on typos) and MUST surface malformed payloads as `FacetError` — a raw
Pydantic/Zod error never escapes a public API.

## 3. Identity, references & rename

- **Id grammar.** `id = kind ":" slug` with `kind` matching `^[a-z][a-z0-9-]*$` and
  `slug` matching `^[A-Za-z0-9][A-Za-z0-9:_.-]*$`. Malformed ids MUST raise `IdError`.
- **Refs.** Every stored reference (relations, membership, form facets) is a node id in
  this grammar. `uid` is the join key and identity anchor — never the stored ref form.
- **Resolution.** A ref resolves to a `uid` via the live-id map first, then the
  deprecated-id map. A live id always wins over another node's deprecated id.
  Resolution MUST be O(1) via the structural index.
- **Collisions.** The corpus MUST reject a node claiming a live id or another node's
  still-active deprecated id (`CollisionError`), and MUST reject a duplicate `uid`.
- **Rename** is a library operation. Given `old_id` → `new_id`: `old_id` MUST be live
  (`RefError` otherwise); `new_id` MUST NOT resolve (`CollisionError` otherwise). The
  operation updates `id`, sets `kind` from the new id, appends `old_id` to
  `deprecated_ids` (once), and rewrites every position holding `old_id` — in the renamed
  node and in every referrer the reverse index names (relation `source`/`target`,
  membership members, `edges`/`order`/`keys` form-facet refs). Cost MUST be O(degree).
  `uid` never changes; a stale ref still resolves through `deprecated_ids`.
- **Rename atomicity.** All rewrites are prepared in memory; with a registry (§6) every
  node that will be written is validated before anything is written (no partial rename).
  Commit writes the renamed node first (write-new-then-delete-old), then referrers.

## 4. On-disk format

### 4.1 Corpus layout & membership

- One file per node: `<root>/<kind>/<slug>.md`, with any `:` in the slug mapped to `__`.
- Files are canonical and git-versioned; everything else is rebuildable from them.
- Corpus membership (the files a corpus walk considers): regular `*.md` files under the
  root, recursively; `.nodes-index/` is a reserved private cache directory and MUST be
  skipped; symlinks and non-regular files MUST be skipped; walk order is sorted by
  root-relative POSIX path.

### 4.2 Frontmatter

YAML frontmatter followed by the markdown body (everything below the closing `---`,
preserved verbatim). Top-level fields:

- `id`, `uid`, `kind`, `title` — required; parsing MUST fail (`ValidationError`) when
  any is missing or when `kind` ≠ the id's kind segment.
- `created`, `updated` — optional ISO dates, top-level.
- `version` — optional integer; default 1; MUST be omitted when 1.
- `related` — optional list of target ids (sugar, §4.3).
- `relations` — optional list of typed relations in node-relation form (§4.3).
- `facets` — optional nested map keyed by facet name.
- `deprecated_ids` — optional list of previous ids.

### 4.3 Serialized relation forms

- **Node-relation** (in `related` / `relations`): `{ predicate, target, … }` — `source`
  is implied to be the containing node and MUST be omitted on disk.
- **Graph edge** (in a structure's `edges` facet): `{ source, predicate, target, … }` —
  both endpoints explicit (the structure node is the container, not an endpoint).
- `related: [ref, …]` is sugar for `relatesTo` relations sourced at the node. On
  serialization, a plain `relatesTo` relation (directed, no weight, no attrs, sourced at
  the node) MUST emit into `related`; all other relations emit into `relations`.
- Parsers MUST fill `source` from context into the normalized form; serializers MUST
  drop `source` only when it equals the container. Round-trip MUST be lossless.

Example:

```yaml
---
id: gene:PHF19
uid: 7b2c9d1e4f5a48b3a6c7d8e9f0a1b2c3
kind: gene
title: PHF19
created: 2026-06-21
related: [pathway:PRC2, topic:polycomb]
relations:
  - { predicate: interacts_with, target: gene:EZH2 }
facets:
  bio-axes: { primary_external_id: HGNC:7296 }
---
PHF19 is a PRC2-associated component …
```

## 5. Structural shapes

A **structure** is a node of a kind that adopts a registered *shape*. Shapes compose
required facets + invariants into the kind (§6). The built-in shapes and their
convenience kinds (a kind named after each shape) are registered by
`register_builtin_shapes` / `registerBuiltinShapes`:

| Shape | Required facets | Invariants |
|-------|-----------------|------------|
| `set` | `membership` | unique members |
| `list` | `membership`, `order` | unique members; `order` is a permutation of members |
| `dict` | `membership`, `keys` | unique members; every key value is a member |
| `graph` | `membership`, `edges` | unique members; every edge endpoint is a member |
| `dag` | `membership`, `edges` | graph invariants + acyclic |
| `tree` | `membership`, `edges` | dag invariants + single parent |

Facet payloads: `membership = {members: [ref]}` (scope-only — a unique, unordered set);
`edges = {edges: [Relation]}` (graph-edge form, §4.3); `order = {order: [ref]}`;
`keys = {keys: {key: ref}}`. Order/edges/keys never leak through member position. A kind
adopts at most one shape. Membership and form-facet refs participate in rename rewriting
and dangling tracking but are not relation-graph edges.

## 6. Registry & validation

- A **kind** is a name + a set of required/optional facets + invariants
  (`KindSpec`), optionally adopting one shape (`ShapeSpec`) whose facets and invariants
  compose into it. Registration MUST reject duplicate names and unknown shapes.
- `validate(node)` MUST: resolve the kind (`UnknownKindError` if unregistered); fail on
  missing required facets and on unexpected facets (`FacetError`); then run invariants
  (shape invariants before kind invariants, in registration order).
- **Error taxonomy.** Conforming implementations map these conditions to these error
  names (each language's error classes):

| Condition | Error |
|-----------|-------|
| Malformed canonical id | `IdError` |
| Unresolvable input ref; delete/rename of a non-live id | `RefError` |
| Live-id / deprecated-id / uid collision | `CollisionError` |
| Unregistered kind | `UnknownKindError` |
| Missing, unexpected, or malformed facet payload | `FacetError` |
| Shape or vocabulary invariant violation | `InvariantError` |
| Structural node/frontmatter failure (missing required field, id/kind mismatch) | `ValidationError` |
| Similarity API on a corpus without an embedder | `EmbedderRequiredError` |

- **Write-boundary enforcement.** A corpus MAY be constructed with a registry. When
  present, `add` MUST validate before any disk write, and `rename` MUST validate the
  renamed node and every rewritten referrer before any disk write. Without a registry,
  no vocabulary validation occurs (a deliberate composition default, not a fallback).
- **Structured checking.** The registry MUST also provide a collecting counterpart to
  `validate` (`Registry.check`, §8) that reports all violations of a node with
  machine-stable codes, without raising on content.

## 7. Corpus semantics

`Corpus` is the primary API — a coordinator over the file store and the derived indexes.

- `add(node)`: registry validation (when configured) → collision check → similarity
  vector preparation (when configured) → file write → index upserts. Any failure MUST
  precede the disk write.
- `get(ref)` / `resolve(ref)`: resolve via the index (live then deprecated), read the
  file; `RefError` when the ref does not resolve.
- `delete(id)`: **live-id-only** — a stale/deprecated id MUST raise `RefError` so a
  stale alias never deletes the renamed live node. Inbound refs to a deleted node remain
  on disk and become dangling.
- `rename(old, new)`: as specified in §3.
- Graph queries (`outbound`, `inbound`, `neighbors`, `dangling`) are relations-only and
  uid-based. A **dangling** target (a relation whose target no longer resolves) is a
  normal state — surfaced, never raised. `inbound`/`outbound` raise `RefError` only when
  the *input* ref does not resolve.
- **Single-writer assumption.** Nothing coordinates concurrent mutation of one corpus
  (by two processes or two languages). Deployments MUST ensure a single writer at a
  time; readers may run concurrently at the cost of possibly-stale derived indexes.

## 8. Corpus validity & checking

A corpus is **valid** with respect to a registry when every node passes that registry's
validation. Because files are canonical and hand-editable, nodes can bypass the write
boundary; conforming implementations MUST therefore provide a *reporting* check.

### 8.1 `Registry.check(node)`

Returns a list of violations; MUST NOT raise on content. Each violation carries
`{code, detail, message}`:

- Unregistered kind → a single `unknown-kind` violation (`detail` = the kind); nothing
  else is checked for that node.
- Otherwise, facet presence is computed directly (same composition as `validate`): each
  missing required facet → `facet-missing`; each unexpected facet → `facet-unexpected`
  (`detail` = the facet name, sorted within each code).
- Invariants run only when the facet-presence checks pass (they presuppose their
  facets). An invariant raising `FacetError` → `facet-invalid`; `InvariantError` →
  `invariant-violated` (`detail` = `""` — invariants are opaque callables and cannot be
  attributed to a facet). **Only these kernel content errors are converted**; any other
  exception from an invariant is a programmer bug and MUST propagate.

### 8.2 `Corpus.check(registry?)`

Returns a list of findings; MUST NOT raise on content. Uses the passed registry, else
the corpus's own; there is deliberately no way to ignore a corpus's registry
(`dangling-ref` is the only registry-independent code — filter by code instead).

Finding fields: `{severity, code, ref, detail, message}` where `ref` is the id of the
node the finding anchors to.

| Code | Severity | `detail` | Condition |
|------|----------|----------|-----------|
| `unknown-kind` | error | kind name | node's kind not registered |
| `facet-missing` | error | facet name | required facet absent |
| `facet-unexpected` | error | facet name | facet present but not allowed |
| `facet-invalid` | error | `""` | invariant raised `FacetError` (malformed payload) |
| `invariant-violated` | error | `""` | invariant raised `InvariantError` |
| `dangling-ref` | warning | target ref | top-level relation target resolves to no live node (`ref` = the relation's source node) |

- With a registry: every node runs through `Registry.check`; each violation becomes an
  `error` finding.
- Always (registry or not), the exhaustive list of structural findings: one
  `dangling-ref` per unresolved top-level relation target — exactly the edges
  `dangling()` reports. Malformed structural facet payloads are a registry concern
  (shape invariants); dangling *membership* refs are deferred (§13).
- Ordering MUST be `(ref, code, detail)` ascending — all normative, oracle-pinned
  fields. `message` is human-readable, non-normative, and never used for ordering or
  parity.

## 9. Derived indexes: search & similarity

Derived indexes are disposable caches, always rebuildable from files.

### 9.1 Full-text search (BM25F)

- **Tokenizer:** NFC-normalize → lowercase → split into Unicode-alphanumeric runs →
  drop a fixed 33-word stop list; no stemming. Pinned by `fixtures/search.tokenizer.json`.
- **Scoring:** BM25F over two fields (`title`, `body`) with the standard `(K1 + 1)`
  numerator and a non-negative Lucene IDF. Constants: `K1 = 1.5`, `B = 0.75`,
  `TITLE_BOOST = 2.0`, `BODY_BOOST = 1.0`.
- **Results:** hits carry `id`, `uid`, `score`, matched terms; ordered by descending
  6-decimal half-up score key (§9.3), then ascending `id`. Query-term iteration MUST use
  Unicode code-point order (not UTF-16 code-unit order).
- The index MUST stay current through `add` / `delete` / `rename`.

### 9.2 Similarity (embeddings)

- **Opt-in seam:** the kernel ships no model. An `Embedder` (`cache_namespace`,
  `embed(texts) -> vectors`) is injected at corpus construction; without one the
  similarity APIs MUST raise `EmbedderRequiredError`.
- **Text contract:** one vector per node over `embed_text(node) = title + "\n\n" + body`.
- **Vectors:** L2-normalized in memory (cosine = dot product); exact brute-force — no
  ANN. Raw embedder output is cached content-addressed at
  `<root>/.nodes-index/vectors/<namespace>/<sha256>.json` (git-ignored, atomic writes).
- **Determinism & failure:** one namespace and one dimension per index; namespace/dim
  mismatches, zero-norm, boolean/non-numeric, and non-finite vectors MUST fail early —
  on `add`, before any disk write.
- **Results:** hits carry `id`, `uid`, `score`; ordered like search results.
  `similar(ref)` excludes the node itself.

### 9.3 Ranking key

The cross-language ranking contract is the 6-decimal, round-half-up score key
(`score_key` / `scoreKey`). Oracle scores are compared numerically, never as strings.

## 10. Index persistence

- The derived indexes persist to a **private, disposable, per-language** snapshot:
  `<root>/.nodes-index/snapshot.py.json` (Python) / `snapshot.ts.json` (TypeScript).
  A language MUST NOT read the other's snapshot.
- **Writing is explicit** (`flush_index` / `flushIndex`); construction never writes.
- **Loading reconciles by content hash:** construction hashes current file bytes
  (sha256) against the snapshot manifest — unchanged files skip parsing; changed/added
  files re-parse and re-index; deleted files drop. Reconcile enforces the same collision
  contract as a from-scratch build.
- **Fail-closed:** an absent, corrupt, wrong-version/lang, namespace-mismatched, or
  internally inconsistent snapshot MUST be discarded silently and trigger a full
  rebuild. Files remain the single source of truth; deleting a snapshot only costs
  startup speed.

## 11. Conformance fixtures

The shared oracles under `fixtures/` are the conformance suite. Both languages MUST
assert against them.

| Fixture | Pins |
|---------|------|
| `gene_phf19.md`, `gene_phf19.canonical.json` | frontmatter parse → canonical JSON projection |
| `gene_phf19.py-emit.md`, `gene_phf19.ts-emit.md` | cross-emitted samples: each language re-emits (regenerate-and-diff) and parses the other's |
| `corpus/`, `corpus.rename.canonical.json` | rename semantics across referrers (whole-corpus post-rename oracle) |
| `search.tokenizer.json` | tokenizer freeze |
| `search-corpus/`, `search.oracle.json` | BM25F ranked ids + 6-dp scores |
| `similarity-corpus/`, `similarity.vectors.json`, `similarity.oracle.json` | similarity ranking over frozen vectors (model embeddings are not portable) |
| `check-corpus/`, `check.oracle.json` | corpus-validity findings (severity, code, ref, detail) |

## 12. Versioning & change policy

- This standard carries a spec version (header). **Minor** bumps are additive (new
  optional fields, new finding codes, new fixtures). **Major** bumps break reading or
  writing existing corpora, or change pinned tier-2 behavior.
- Any tier-1/tier-2 change MUST update this document and the affected fixtures in the
  same change. Tier-3 additions do not touch this document.
- History: **1.0** (2026-07-10) — initial consolidation; adds §8 corpus validity.

## 13. Known limitations

- No public membership-graph traversal (tree descendants, DAG reachability); membership
  refs are tracked for rename/dangling integrity but not exposed as graph edges, and
  dangling membership refs are not yet reported by `check`.
- Single-writer only (§7); no locking.
- In-memory indexes and brute-force cosine target personal-corpus scale (order of
  10⁴–10⁵ nodes), not bulk graph workloads.
````

- [ ] **Step 2: Delete `docs/format.md` and sweep references**

```bash
rtk git rm docs/format.md
grep -rl 'format\.md' docs --include='*.md' | grep -v '2026-07-10-nodes-standard-and-check' | xargs -r sed -i 's|docs/format\.md|docs/STANDARD.md|g; s|`format\.md`|`STANDARD.md`|g'
grep -rn 'format\.md' docs | grep -v '2026-07-10-nodes-standard-and-check'
```

Expected final grep: no output. If stragglers appear (bare `format.md` in prose), rewrite each by hand to `docs/STANDARD.md`.

- [ ] **Step 3: Add the current-state note to the substrate design**

In `docs/designs/2026-06-21-nodes-substrate-design.md`, insert directly under the `### 3.4 Structural shapes — the refinement lattice` heading:

```markdown
> **Current-state note (2026-07-10):** this section predates the structural-shapes
> redesign. The current contract is a scope-only `membership` facet (`{members}`) plus
> shape-owned form facets (`edges` / `order` / `keys`), specified normatively in
> `docs/STANDARD.md` §5. The table below is the original design record.
```

- [ ] **Step 4: Verify suites still pass (no code references docs)**

From `python/`: `rtk uv run --frozen pytest -q` — expected: PASS.
From `ts/`: `npm test` — expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add -A docs
rtk git commit -m "docs: add versioned normative STANDARD.md, retire format.md"
```

---

### Task 3: Root `README.md` + `AGENTS.md`

**Files:**
- Create: `README.md`
- Create: `AGENTS.md`

**Interfaces:**
- Consumes: `docs/STANDARD.md` (Task 2), `docs/designs/` (Task 1).

- [ ] **Step 1: Create `README.md`**

```markdown
# nodes

A problem-agnostic knowledge substrate: entities as markdown files ("nodes"), typed
relations, structural shapes (set/list/dict/graph/DAG/tree), and rebuildable derived
indexes (structural, full-text, similarity) — implemented in Python and TypeScript over
one shared on-disk format.

## Architecture

Three layers, strict downward dependency:

```
domain profiles   science (Python), mindful v6 (TypeScript), …
knowledge vocab   note / idea / question / topic / paper / book / dataset
kernel            Node, Relation, shapes, identity, format, Corpus, indexes
```

The kernel is domain-free (zero named knowledge kinds); the vocab imports only the
kernel; domain profiles live in downstream repos.

## Repo layout

| Path | Contents |
|------|----------|
| `docs/STANDARD.md` | **The authority** — the versioned, normative portable contract. |
| `docs/designs/`, `docs/plans/` | Dated historical records (rationale, not authority). |
| `python/` | Python kernel + vocab (`nodes.kernel`, `nodes.vocab`). |
| `ts/` | TypeScript kernel + vocab (`@nodes/kernel`). |
| `fixtures/` | Shared cross-language conformance oracles. |

## The standard

`docs/STANDARD.md` defines what both languages must agree on, in three tiers: the
portable data contract (tier 1), oracle-pinned behavior (tier 2), and per-language
surface with no parity obligation (tier 3). When any document here disagrees with the
standard, the standard wins.

## Development

Python (from `python/`):

```sh
rtk uv run --frozen pytest -q
rtk uv run --frozen ruff check .
rtk uv run --frozen pyright src
```

TypeScript (from `ts/`):

```sh
npm test
npm run typecheck
npm run check
```

## Consumers

- **mindful v6** (`~/d/mindful/`) — tool-for-thought, builds on the TypeScript kernel.
- **science** (`~/d/science/`) — research knowledge graphs, builds on the Python kernel.
```

- [ ] **Step 2: Create `AGENTS.md`**

```markdown
# Agent guide — nodes

## Authority order

1. `docs/STANDARD.md` — the versioned normative contract. When anything disagrees with
   it, it wins (or it has a bug: fix it in the same change).
2. The code and its tests.
3. `docs/designs/` and `docs/plans/` — dated historical records. Rationale only; do not
   execute old plans or treat their code snippets as current.

## Layering (enforced, not conventional)

- `kernel` imports nothing above it and names zero knowledge kinds.
- `vocab` imports only the kernel. Domain kinds live in downstream repos.

## Parity tiers (before adding any feature)

Decide the tier first — see `docs/STANDARD.md` §1:

- **Tier 1** (format, identity, mutation semantics): implement in both languages, update
  `docs/STANDARD.md` and the `fixtures/` oracles in the same change.
- **Tier 2** (derived-index behavior, finding codes): same, pinned by oracles.
- **Tier 3** (per-language convenience): one language is fine; no standard change.

## Gates (run before every commit)

- Python, from `python/`: `rtk uv run --frozen pytest -q`,
  `rtk uv run --frozen ruff check .`, `rtk uv run --frozen pyright src`.
- TypeScript, from `ts/`: `npm test`, `npm run typecheck`, `npm run check`.

## Conventions

- Fail early; no silent fallbacks. Wrap Pydantic/Zod errors into the kernel error
  hierarchy — they never escape public APIs.
- Composition over inheritance: kinds are name + facets + invariants, never subclasses.
- Filepaths in docs use `~/d/nodes/...`.
- No AI-attribution trailers in commit messages.
```

- [ ] **Step 3: Commit**

```bash
rtk git add README.md AGENTS.md
rtk git commit -m "docs: add root README and AGENTS guide naming STANDARD.md the authority"
```

---

### Task 4: Fix stale `ts/README.md`

**Files:**
- Modify: `ts/README.md` (the `## Scope` section, lines 5–15)

**Interfaces:**
- Consumes: `docs/STANDARD.md` (Task 2).

- [ ] **Step 1: Replace the stale Scope section**

Replace the entire `## Scope` section body (currently claiming "no full-text search, no embeddings, no on-disk index persistence") with:

```markdown
## Scope

Mirrors the current Python kernel: `Node`/`Relation`, ids, errors, frontmatter
parse/serialize, registry, structural shapes, a slimmed `Store` (pure file mechanics),
the in-memory structural `Index`, and the `Corpus` coordinator — the primary API for
mutations (`add`/`get`/`rename`/`delete`), graph queries
(`outbound`/`inbound`/`neighbors`/`dangling`), BM25F full-text `search`, opt-in
embedding `similar`/`queryVector`/`similarText`, snapshot persistence (`flushIndex`),
and corpus checking (`check`). TS-only conveniences (tier 3): `idsByKind`/`allByKind`
and corpus stat fingerprints. There is **no membership-graph traversal** yet.

The knowledge vocab (`ts/src/vocab/` — `note`/`idea`/`question`/`topic`/`paper`/`book`/
`dataset`, the `Source` facet, and the predicate vocabulary) is a separate layer that
imports only from the kernel; register it with `registerKnowledgeVocab(reg)`.

The portable contract this kernel implements is specified in `../docs/STANDARD.md`
(spec version 1.0); parity with Python is pinned by the shared `../fixtures/` oracles.
```

- [ ] **Step 2: Commit**

```bash
rtk git add ts/README.md
rtk git commit -m "docs(ts): fix stale README scope, point at STANDARD.md"
```

---

### Task 5: Python `Registry.check` + `Violation`

**Files:**
- Modify: `python/src/nodes/kernel/registry.py`
- Test: `python/tests/test_registry_check.py`

**Interfaces:**
- Consumes: `nodes.kernel.errors.{FacetError, InvariantError}`, existing `Registry`/`KindSpec`/`ShapeSpec`.
- Produces: `Violation` (Pydantic model: `code: str`, `detail: str`, `message: str`); `Registry.check(node: Node) -> list[Violation]`. Used by Task 6. `Registry.validate` unchanged.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_registry_check.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.node import Node
from nodes.kernel.registry import KindSpec, Registry
from nodes.vocab.kinds import register_knowledge_vocab
from nodes.vocab.source import SOURCE


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    register_knowledge_vocab(r)
    return r


def _codes(violations) -> list[tuple[str, str]]:
    return [(v.code, v.detail) for v in violations]


def test_valid_node_yields_no_violations(reg):
    assert reg.check(Node(id="note:a", kind="note", title="A")) == []


def test_unknown_kind_single_violation(reg):
    vs = reg.check(Node(id="zzz:a", kind="zzz", title="A"))
    assert _codes(vs) == [("unknown-kind", "zzz")]
    assert "zzz:a" in vs[0].message


def test_missing_and_unexpected_collected_together():
    reg = Registry()
    reg.register(KindSpec(name="widget", required_facets={"a", "b"}))
    node = Node(id="widget:w", kind="widget", title="W", facets={"c": {}})
    assert _codes(reg.check(node)) == [
        ("facet-missing", "a"),
        ("facet-missing", "b"),
        ("facet-unexpected", "c"),
    ]


def test_invariants_skipped_when_presence_fails():
    def boom(node: Node) -> None:
        raise RuntimeError("must not run")

    reg = Registry()
    reg.register(KindSpec(name="widget", required_facets={"a"}, invariants=[boom]))
    node = Node(id="widget:w", kind="widget", title="W")
    assert _codes(reg.check(node)) == [("facet-missing", "a")]


def test_invariant_facet_error_becomes_facet_invalid(reg):
    node = Node(id="paper:p", kind="paper", title="P", facets={SOURCE: {"identifer": "10.1/x"}})
    assert _codes(reg.check(node)) == [("facet-invalid", "")]


def test_invariant_error_becomes_invariant_violated(reg):
    node = Node(id="paper:p", kind="paper", title="P", facets={SOURCE: {}})
    assert _codes(reg.check(node)) == [("invariant-violated", "")]


def test_non_kernel_invariant_exception_propagates():
    def buggy(node: Node) -> None:
        raise RuntimeError("programmer bug")

    reg = Registry()
    reg.register(KindSpec(name="widget", invariants=[buggy]))
    with pytest.raises(RuntimeError):
        reg.check(Node(id="widget:w", kind="widget", title="W"))


def test_validate_behavior_unchanged(reg):
    from nodes.kernel.errors import FacetError

    with pytest.raises(FacetError):
        reg.validate(Node(id="paper:p", kind="paper", title="P"))
```

- [ ] **Step 2: Run test to verify it fails**

From `python/`: `rtk uv run --frozen pytest tests/test_registry_check.py -q`
Expected: FAIL — `AttributeError: 'Registry' object has no attribute 'check'`.

- [ ] **Step 3: Implement**

In `python/src/nodes/kernel/registry.py`, add `Violation` after the `KindSpec` class, extract the composition helper, and add `check`. The full replacement for everything from `class Registry:` down (plus the new model; imports stay as they are, with `FacetError`, `InvariantError`, `UnknownKindError`, `ValidationError` already imported):

```python
class Violation(BaseModel):
    """One structured validation finding from `Registry.check` (never raised)."""

    code: str
    detail: str
    message: str


class Registry:
    def __init__(self) -> None:
        self._specs: dict[str, KindSpec] = {}
        self._shapes: dict[str, ShapeSpec] = {}

    def register_shape(self, spec: ShapeSpec) -> None:
        if spec.name in self._shapes:
            raise ValidationError(f"shape {spec.name!r} is already registered")
        self._shapes[spec.name] = spec

    def is_shape(self, name: str) -> bool:
        return name in self._shapes

    def register(self, spec: KindSpec) -> None:
        if spec.name in self._specs:
            raise ValidationError(f"kind {spec.name!r} is already registered")
        if spec.shape is not None and spec.shape not in self._shapes:
            raise UnknownKindError(f"kind {spec.name!r} adopts unknown shape {spec.shape!r}")
        self._specs[spec.name] = spec

    def is_registered(self, kind: str) -> bool:
        return kind in self._specs

    def get(self, kind: str) -> KindSpec:
        try:
            return self._specs[kind]
        except KeyError as exc:
            raise UnknownKindError(f"kind {kind!r} is not registered") from exc

    def _compose(self, spec: KindSpec) -> tuple[set[str], set[str], list[Invariant]]:
        required = set(spec.required_facets)
        optional = set(spec.optional_facets)
        invariants: list[Invariant] = []
        if spec.shape is not None:
            shape = self._shapes[spec.shape]
            required |= shape.required_facets
            optional |= shape.optional_facets
            invariants.extend(shape.invariants)
        invariants.extend(spec.invariants)
        return required, optional, invariants

    def validate(self, node: Node) -> None:
        required, optional, invariants = self._compose(self.get(node.kind))
        present = set(node.facets)
        missing = required - present
        if missing:
            raise FacetError(f"{node.id}: missing required facets {sorted(missing)}")
        allowed = required | optional
        unexpected = present - allowed
        if unexpected:
            raise FacetError(f"{node.id}: unexpected facets {sorted(unexpected)}")
        for invariant in invariants:
            invariant(node)

    def check(self, node: Node) -> list[Violation]:
        """Collect ALL violations of `node` with machine-stable codes; never raises on
        content. Non-kernel exceptions from invariants are programmer bugs and propagate."""
        spec = self._specs.get(node.kind)
        if spec is None:
            return [
                Violation(
                    code="unknown-kind",
                    detail=node.kind,
                    message=f"{node.id}: kind {node.kind!r} is not registered",
                )
            ]
        required, optional, invariants = self._compose(spec)
        present = set(node.facets)
        violations: list[Violation] = []
        for name in sorted(required - present):
            violations.append(
                Violation(code="facet-missing", detail=name, message=f"{node.id}: missing required facet {name!r}")
            )
        for name in sorted(present - (required | optional)):
            violations.append(
                Violation(code="facet-unexpected", detail=name, message=f"{node.id}: unexpected facet {name!r}")
            )
        if violations:
            return violations  # invariants presuppose their facets; running them would duplicate reports
        for invariant in invariants:
            try:
                invariant(node)
            except FacetError as exc:
                violations.append(Violation(code="facet-invalid", detail="", message=str(exc)))
            except InvariantError as exc:
                violations.append(Violation(code="invariant-violated", detail="", message=str(exc)))
        return violations
```

- [ ] **Step 4: Run tests to verify they pass**

From `python/`: `rtk uv run --frozen pytest tests/test_registry_check.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Run gates and commit**

```bash
rtk uv run --frozen pytest -q
rtk uv run --frozen ruff check .
rtk uv run --frozen pyright src
rtk git add src/nodes/kernel/registry.py tests/test_registry_check.py
rtk git commit -m "feat(registry): structured collecting Registry.check beside unchanged validate"
```

---

### Task 6: Python `Corpus.check` + `Finding`

**Files:**
- Modify: `python/src/nodes/kernel/corpus.py`
- Test: `python/tests/test_corpus_check.py`

**Interfaces:**
- Consumes: `Registry.check` / `Violation` (Task 5); existing `Corpus`, `Index.dangling_edges`, `Store.all_nodes`.
- Produces: `Finding` (Pydantic model: `severity: Literal["error","warning"]`, `code: str`, `ref: str`, `detail: str`, `message: str`); `Corpus.check(registry: Registry | None = None) -> list[Finding]`. Used by Task 9.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_corpus_check.py`:

```python
from __future__ import annotations

from nodes.kernel.corpus import Corpus
from nodes.kernel.node import Node
from nodes.kernel.registry import Registry
from nodes.kernel.relations import Relation
from nodes.kernel.shapes import register_builtin_shapes
from nodes.vocab.kinds import register_knowledge_vocab
from nodes.vocab.source import SOURCE


def _registry() -> Registry:
    r = Registry()
    register_builtin_shapes(r)
    register_knowledge_vocab(r)
    return r


def _tuples(findings) -> list[tuple[str, str, str, str]]:
    return [(f.severity, f.code, f.ref, f.detail) for f in findings]


def test_clean_corpus_no_findings(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    c.add(Node(id="topic:t", kind="topic", title="T"))
    c.add(Node(id="note:n", kind="note", title="N",
               relations=[Relation(source="note:n", predicate="about", target="topic:t")]))
    assert c.check() == []


def test_hand_edited_violations_reported(tmp_path):
    seed = Corpus(tmp_path)  # registry-free: simulates hand-edited files
    seed.add(Node(id="zzz:m", kind="zzz", title="M"))
    seed.add(Node(id="note:s", kind="note", title="S", facets={SOURCE: {"year": 2026}}))
    seed.add(Node(id="paper:b", kind="paper", title="B",
                  relations=[Relation(source="paper:b", predicate="cites", target="paper:ghost")]))
    c = Corpus(tmp_path, registry=_registry())
    assert _tuples(c.check()) == [
        ("error", "facet-unexpected", "note:s", "source"),
        ("warning", "dangling-ref", "paper:b", "paper:ghost"),
        ("error", "facet-missing", "paper:b", "source"),
        ("error", "unknown-kind", "zzz:m", "zzz"),
    ]


def test_no_registry_reports_only_dangling(tmp_path):
    seed = Corpus(tmp_path)
    seed.add(Node(id="zzz:m", kind="zzz", title="M",
                  relations=[Relation(source="zzz:m", predicate="cites", target="note:gone")]))
    c = Corpus(tmp_path)
    assert _tuples(c.check()) == [("warning", "dangling-ref", "zzz:m", "note:gone")]


def test_passed_registry_overrides_corpus_registry(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    c.add(Node(id="note:n", kind="note", title="N"))
    empty = Registry()
    assert _tuples(c.check(registry=empty)) == [("error", "unknown-kind", "note:n", "note")]


def test_check_does_not_mutate_corpus(tmp_path):
    seed = Corpus(tmp_path)
    seed.add(Node(id="zzz:m", kind="zzz", title="M"))
    c = Corpus(tmp_path, registry=_registry())
    c.check()
    assert c.get("zzz:m").title == "M"  # still readable, file untouched
```

- [ ] **Step 2: Run test to verify it fails**

From `python/`: `rtk uv run --frozen pytest tests/test_corpus_check.py -q`
Expected: FAIL — `AttributeError: 'Corpus' object has no attribute 'check'`.

- [ ] **Step 3: Implement**

In `python/src/nodes/kernel/corpus.py`:

Add to the imports:

```python
from typing import Literal

from pydantic import BaseModel
```

Add after the `_rewrite_refs` function (module level, before `class Corpus`):

```python
class Finding(BaseModel):
    """One corpus-check finding (reported, never raised)."""

    severity: Literal["error", "warning"]
    code: str
    ref: str
    detail: str
    message: str
```

Add this method to `Corpus` (after `rename`):

```python
    def check(self, registry: Registry | None = None) -> list[Finding]:
        """Report corpus-validity findings; never raises on content.

        Registry violations (when a registry is configured or passed) are errors;
        unresolved top-level relation targets are warnings. Sorted by (ref, code,
        detail) — `message` is human-only.
        """
        reg = registry if registry is not None else self.registry
        findings: list[Finding] = []
        if reg is not None:
            for node in self.store.all_nodes():
                for v in reg.check(node):
                    findings.append(
                        Finding(severity="error", code=v.code, ref=node.id, detail=v.detail, message=v.message)
                    )
        for edge in self.index.dangling_edges():
            rel = edge.relation
            findings.append(
                Finding(
                    severity="warning",
                    code="dangling-ref",
                    ref=rel.source,
                    detail=rel.target,
                    message=f"{rel.source}: relation {rel.predicate!r} targets unresolved {rel.target!r}",
                )
            )
        findings.sort(key=lambda f: (f.ref, f.code, f.detail))
        return findings
```

- [ ] **Step 4: Run tests to verify they pass**

From `python/`: `rtk uv run --frozen pytest tests/test_corpus_check.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Run gates and commit**

```bash
rtk uv run --frozen pytest -q
rtk uv run --frozen ruff check .
rtk uv run --frozen pyright src
rtk git add src/nodes/kernel/corpus.py tests/test_corpus_check.py
rtk git commit -m "feat(corpus): Corpus.check reporting API (registry violations + dangling refs)"
```

---

### Task 7: TypeScript `Registry.check` + `Violation`

**Files:**
- Modify: `ts/src/registry.ts`
- Test: `ts/tests/registry-check.test.ts`

**Interfaces:**
- Consumes: `ts/src/errors.ts` (`FacetError`, `InvariantError`), existing `Registry`.
- Produces: `export interface Violation { code; detail; message }` (all `string`); `Registry.check(node: Node): Violation[]`. Used by Task 8. `Registry.validate` unchanged.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/registry-check.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { FacetError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import { SOURCE, registerKnowledgeVocab } from "../src/vocab/index.js";

function vocabRegistry(): Registry {
  const reg = new Registry();
  registerKnowledgeVocab(reg);
  return reg;
}

function codes(violations: { code: string; detail: string }[]): [string, string][] {
  return violations.map((v) => [v.code, v.detail]);
}

describe("Registry.check", () => {
  it("returns no violations for a valid node", () => {
    const reg = vocabRegistry();
    expect(reg.check(makeNode({ id: "note:a", kind: "note", title: "A" }))).toEqual([]);
  });

  it("reports unknown kind as a single violation", () => {
    const reg = vocabRegistry();
    const vs = reg.check(makeNode({ id: "zzz:a", kind: "zzz", title: "A" }));
    expect(codes(vs)).toEqual([["unknown-kind", "zzz"]]);
    expect(vs[0].message).toContain("zzz:a");
  });

  it("collects missing and unexpected facets together", () => {
    const reg = new Registry();
    reg.register({ name: "widget", requiredFacets: new Set(["a", "b"]) });
    const node = makeNode({ id: "widget:w", kind: "widget", title: "W", facets: { c: {} } });
    expect(codes(reg.check(node))).toEqual([
      ["facet-missing", "a"],
      ["facet-missing", "b"],
      ["facet-unexpected", "c"],
    ]);
  });

  it("skips invariants when facet presence fails", () => {
    const reg = new Registry();
    reg.register({
      name: "widget",
      requiredFacets: new Set(["a"]),
      invariants: [
        () => {
          throw new Error("must not run");
        },
      ],
    });
    const node = makeNode({ id: "widget:w", kind: "widget", title: "W" });
    expect(codes(reg.check(node))).toEqual([["facet-missing", "a"]]);
  });

  it("maps invariant FacetError to facet-invalid", () => {
    const reg = vocabRegistry();
    const node = makeNode({
      id: "paper:p",
      kind: "paper",
      title: "P",
      facets: { [SOURCE]: { identifer: "10.1/x" } },
    });
    expect(codes(reg.check(node))).toEqual([["facet-invalid", ""]]);
  });

  it("maps InvariantError to invariant-violated", () => {
    const reg = vocabRegistry();
    const node = makeNode({ id: "paper:p", kind: "paper", title: "P", facets: { [SOURCE]: {} } });
    expect(codes(reg.check(node))).toEqual([["invariant-violated", ""]]);
  });

  it("propagates non-kernel invariant exceptions", () => {
    const reg = new Registry();
    reg.register({
      name: "widget",
      invariants: [
        () => {
          throw new RangeError("programmer bug");
        },
      ],
    });
    expect(() => reg.check(makeNode({ id: "widget:w", kind: "widget", title: "W" }))).toThrow(RangeError);
  });

  it("leaves validate behavior unchanged", () => {
    const reg = vocabRegistry();
    expect(() => reg.validate(makeNode({ id: "paper:p", kind: "paper", title: "P" }))).toThrow(FacetError);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

From `ts/`: `npm test -- registry-check`
Expected: FAIL — `reg.check is not a function`.

- [ ] **Step 3: Implement**

In `ts/src/registry.ts`:

Change the errors import to include `InvariantError`:

```ts
import { FacetError, InvariantError, UnknownKindError, ValidationError } from "./errors.js";
```

Add the `Violation` interface after the `KindSpec` interface:

```ts
/** One structured validation finding from `Registry.check` (never thrown). */
export interface Violation {
  readonly code: string;
  readonly detail: string;
  readonly message: string;
}
```

Inside `Registry`, extract the composition into a private helper, rewrite `validate` on top of it (identical behavior and messages), and add `check`. Replace the existing `validate` method with:

```ts
  private compose(
    spec: KindSpec,
    kind: string,
  ): { required: Set<string>; optional: Set<string>; invariants: Invariant[] } {
    const required = new Set(spec.requiredFacets ?? []);
    const optional = new Set(spec.optionalFacets ?? []);
    const invariants: Invariant[] = [];
    if (spec.shape !== undefined) {
      const shape = this.shapes.get(spec.shape);
      if (shape === undefined) {
        throw new UnknownKindError(
          `kind ${JSON.stringify(kind)} adopts unknown shape ${JSON.stringify(spec.shape)}`,
        );
      }
      for (const f of shape.requiredFacets ?? []) required.add(f);
      for (const f of shape.optionalFacets ?? []) optional.add(f);
      for (const inv of shape.invariants ?? []) invariants.push(inv);
    }
    for (const inv of spec.invariants ?? []) invariants.push(inv);
    return { required, optional, invariants };
  }

  validate(node: Node): void {
    const spec = this.get(node.kind);
    const { required, optional, invariants } = this.compose(spec, node.kind);
    const present = new Set(Object.keys(node.facets));
    const missing = [...required].filter((f) => !present.has(f)).sort();
    if (missing.length > 0) {
      throw new FacetError(`${node.id}: missing required facets ${JSON.stringify(missing)}`);
    }
    const allowed = new Set([...required, ...optional]);
    const unexpected = [...present].filter((f) => !allowed.has(f)).sort();
    if (unexpected.length > 0) {
      throw new FacetError(`${node.id}: unexpected facets ${JSON.stringify(unexpected)}`);
    }
    for (const invariant of invariants) invariant(node);
  }

  /** Collect ALL violations of `node` with machine-stable codes; never throws on
   * content. Non-kernel exceptions from invariants are programmer bugs and propagate. */
  check(node: Node): Violation[] {
    const spec = this.specs.get(node.kind);
    if (spec === undefined) {
      return [
        {
          code: "unknown-kind",
          detail: node.kind,
          message: `${node.id}: kind ${JSON.stringify(node.kind)} is not registered`,
        },
      ];
    }
    const { required, optional, invariants } = this.compose(spec, node.kind);
    const present = new Set(Object.keys(node.facets));
    const violations: Violation[] = [];
    for (const name of [...required].filter((f) => !present.has(f)).sort()) {
      violations.push({
        code: "facet-missing",
        detail: name,
        message: `${node.id}: missing required facet ${JSON.stringify(name)}`,
      });
    }
    const allowed = new Set([...required, ...optional]);
    for (const name of [...present].filter((f) => !allowed.has(f)).sort()) {
      violations.push({
        code: "facet-unexpected",
        detail: name,
        message: `${node.id}: unexpected facet ${JSON.stringify(name)}`,
      });
    }
    // Invariants presuppose their facets; running them anyway would duplicate reports.
    if (violations.length > 0) return violations;
    for (const invariant of invariants) {
      try {
        invariant(node);
      } catch (exc) {
        if (exc instanceof FacetError) {
          violations.push({ code: "facet-invalid", detail: "", message: exc.message });
        } else if (exc instanceof InvariantError) {
          violations.push({ code: "invariant-violated", detail: "", message: exc.message });
        } else {
          throw exc;
        }
      }
    }
    return violations;
  }
```

- [ ] **Step 4: Run tests to verify they pass**

From `ts/`: `npm test -- registry-check`
Expected: PASS (8 tests).

- [ ] **Step 5: Run gates and commit**

```bash
npm test
npm run typecheck
npm run check
rtk git add src/registry.ts tests/registry-check.test.ts
rtk git commit -m "feat(ts/registry): structured collecting Registry.check beside unchanged validate"
```

---

### Task 8: TypeScript `Corpus.check` + `Finding` + barrel exports

**Files:**
- Modify: `ts/src/corpus.ts`
- Modify: `ts/src/index.ts` (barrel exports)
- Test: `ts/tests/corpus-check.test.ts`

**Interfaces:**
- Consumes: `Registry.check` / `Violation` (Task 7); existing `Corpus`, `Index.danglingEdges`, `Store.allNodes`.
- Produces: `export interface Finding { severity: "error" | "warning"; code; ref; detail; message }` (rest `string`); `Corpus.check(registry?: Registry): Finding[]`; barrel exports `type Violation` (from `registry.js`) and `type Finding` (from `corpus.js`). Used by Task 9.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/corpus-check.test.ts`:

```ts
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import { registerBuiltinShapes } from "../src/shapes.js";
import { SOURCE, registerKnowledgeVocab } from "../src/vocab/index.js";

function vocabRegistry(): Registry {
  const reg = new Registry();
  registerBuiltinShapes(reg);
  registerKnowledgeVocab(reg);
  return reg;
}

function tuples(findings: { severity: string; code: string; ref: string; detail: string }[]) {
  return findings.map((f) => [f.severity, f.code, f.ref, f.detail]);
}

function tmpRoot(): string {
  return mkdtempSync(join(tmpdir(), "nodes-check-"));
}

describe("Corpus.check", () => {
  it("returns no findings for a clean corpus", () => {
    const root = tmpRoot();
    const c = new Corpus(root, vocabRegistry());
    c.add(makeNode({ id: "topic:t", kind: "topic", title: "T" }));
    c.add(
      makeNode({
        id: "note:n",
        kind: "note",
        title: "N",
        relations: [{ source: "note:n", predicate: "about", target: "topic:t", directed: true }],
      }),
    );
    expect(c.check()).toEqual([]);
  });

  it("reports hand-edited violations sorted by (ref, code, detail)", () => {
    const root = tmpRoot();
    const seed = new Corpus(root); // registry-free: simulates hand-edited files
    seed.add(makeNode({ id: "zzz:m", kind: "zzz", title: "M" }));
    seed.add(makeNode({ id: "note:s", kind: "note", title: "S", facets: { [SOURCE]: { year: 2026 } } }));
    seed.add(
      makeNode({
        id: "paper:b",
        kind: "paper",
        title: "B",
        relations: [{ source: "paper:b", predicate: "cites", target: "paper:ghost", directed: true }],
      }),
    );
    const c = new Corpus(root, vocabRegistry());
    expect(tuples(c.check())).toEqual([
      ["error", "facet-unexpected", "note:s", "source"],
      ["warning", "dangling-ref", "paper:b", "paper:ghost"],
      ["error", "facet-missing", "paper:b", "source"],
      ["error", "unknown-kind", "zzz:m", "zzz"],
    ]);
  });

  it("reports only dangling refs without any registry", () => {
    const root = tmpRoot();
    const seed = new Corpus(root);
    seed.add(
      makeNode({
        id: "zzz:m",
        kind: "zzz",
        title: "M",
        relations: [{ source: "zzz:m", predicate: "cites", target: "note:gone", directed: true }],
      }),
    );
    const c = new Corpus(root);
    expect(tuples(c.check())).toEqual([["warning", "dangling-ref", "zzz:m", "note:gone"]]);
  });

  it("passed registry overrides the corpus registry", () => {
    const root = tmpRoot();
    const c = new Corpus(root, vocabRegistry());
    c.add(makeNode({ id: "note:n", kind: "note", title: "N" }));
    expect(tuples(c.check(new Registry()))).toEqual([["error", "unknown-kind", "note:n", "note"]]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

From `ts/`: `npm test -- corpus-check`
Expected: FAIL — `c.check is not a function`.

- [ ] **Step 3: Implement**

In `ts/src/corpus.ts`:

Change the registry import to also bring in `Violation` usage (type-only stays fine):

```ts
import type { Registry } from "./registry.js";
```

(unchanged — `Violation` is consumed structurally). Add the `Finding` interface after the `rewriteRefs` function, before `export class Corpus`:

```ts
/** One corpus-check finding (reported, never thrown). */
export interface Finding {
  readonly severity: "error" | "warning";
  readonly code: string;
  readonly ref: string;
  readonly detail: string;
  readonly message: string;
}

function cmpStr(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}
```

Add this method to `Corpus` (after `rename`):

```ts
  /** Report corpus-validity findings; never throws on content. Registry violations
   * (configured or passed) are errors; unresolved top-level relation targets are
   * warnings. Sorted by (ref, code, detail) — `message` is human-only. */
  check(registry?: Registry): Finding[] {
    const reg = registry ?? this.registry;
    const findings: Finding[] = [];
    if (reg !== undefined) {
      for (const node of this.store.allNodes()) {
        for (const v of reg.check(node)) {
          findings.push({ severity: "error", code: v.code, ref: node.id, detail: v.detail, message: v.message });
        }
      }
    }
    for (const edge of this.index.danglingEdges()) {
      const rel = edge.relation;
      findings.push({
        severity: "warning",
        code: "dangling-ref",
        ref: rel.source,
        detail: rel.target,
        message: `${rel.source}: relation ${JSON.stringify(rel.predicate)} targets unresolved ${JSON.stringify(rel.target)}`,
      });
    }
    findings.sort((a, b) => cmpStr(a.ref, b.ref) || cmpStr(a.code, b.code) || cmpStr(a.detail, b.detail));
    return findings;
  }
```

In `ts/src/index.ts`, update the two export lines:

```ts
export { type Invariant, type KindSpec, type ShapeSpec, type Violation, Registry } from "./registry.js";
```

```ts
export { Corpus, type Finding } from "./corpus.js";
```

- [ ] **Step 4: Run tests to verify they pass**

From `ts/`: `npm test -- corpus-check`
Expected: PASS (4 tests).

- [ ] **Step 5: Run gates and commit**

```bash
npm test
npm run typecheck
npm run check
rtk git add src/corpus.ts src/index.ts tests/corpus-check.test.ts
rtk git commit -m "feat(ts/corpus): Corpus.check reporting API (registry violations + dangling refs)"
```

---

### Task 9: Shared conformance fixture + parity tests

**Files:**
- Create: `fixtures/check-corpus/topic/clean.md`, `fixtures/check-corpus/note/tidy.md`, `fixtures/check-corpus/note/stray.md`, `fixtures/check-corpus/paper/empty.md`, `fixtures/check-corpus/paper/typo.md`, `fixtures/check-corpus/paper/broken.md`, `fixtures/check-corpus/zzz/mystery.md`
- Create: `fixtures/check.oracle.json`
- Test: `python/tests/test_check_parity.py`, `ts/tests/check_parity.test.ts`

**Interfaces:**
- Consumes: `Corpus.check` in both languages (Tasks 6, 8); `register_builtin_shapes` / `registerBuiltinShapes`; `register_knowledge_vocab` / `registerKnowledgeVocab`.
- Produces: the tier-2 conformance oracle listed in `docs/STANDARD.md` §11.

- [ ] **Step 1: Create the fixture corpus**

`fixtures/check-corpus/topic/clean.md`:

```markdown
---
id: topic:clean
uid: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
kind: topic
title: Clean
---
A valid topic node.
```

`fixtures/check-corpus/note/tidy.md`:

```markdown
---
id: note:tidy
uid: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
kind: note
title: Tidy
relations:
- predicate: about
  target: topic:clean
---
A valid note whose relation resolves.
```

`fixtures/check-corpus/note/stray.md`:

```markdown
---
id: note:stray
uid: "cccccccccccccccccccccccccccccccc"
kind: note
title: Stray
facets:
  source:
    year: 2026
---
A prose kind carrying a facet it may not have.
```

`fixtures/check-corpus/paper/empty.md`:

```markdown
---
id: paper:empty
uid: "dddddddddddddddddddddddddddddddd"
kind: paper
title: Empty
facets:
  source: {}
---
A source kind whose source facet is empty (invariant violation).
```

`fixtures/check-corpus/paper/typo.md`:

```markdown
---
id: paper:typo
uid: "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
kind: paper
title: Typo
facets:
  source:
    identifer: 10.1/x
---
A source kind whose source facet has a typoed key (malformed payload).
```

`fixtures/check-corpus/paper/broken.md`:

```markdown
---
id: paper:broken
uid: "ffffffffffffffffffffffffffffffff"
kind: paper
title: Broken
relations:
- predicate: cites
  target: paper:ghost
---
Missing its source facet AND citing a node that does not exist.
```

`fixtures/check-corpus/zzz/mystery.md`:

```markdown
---
id: zzz:mystery
uid: "12121212121212121212121212121212"
kind: zzz
title: Mystery
---
A kind no registry knows.
```

- [ ] **Step 2: Create the oracle**

`fixtures/check.oracle.json` (sorted by `(ref, code, detail)`; `message` deliberately unpinned):

```json
[
  { "severity": "error", "code": "facet-unexpected", "ref": "note:stray", "detail": "source" },
  { "severity": "warning", "code": "dangling-ref", "ref": "paper:broken", "detail": "paper:ghost" },
  { "severity": "error", "code": "facet-missing", "ref": "paper:broken", "detail": "source" },
  { "severity": "error", "code": "invariant-violated", "ref": "paper:empty", "detail": "" },
  { "severity": "error", "code": "facet-invalid", "ref": "paper:typo", "detail": "" },
  { "severity": "error", "code": "unknown-kind", "ref": "zzz:mystery", "detail": "zzz" }
]
```

- [ ] **Step 3: Write the Python parity test**

Create `python/tests/test_check_parity.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

from nodes.kernel.corpus import Corpus
from nodes.kernel.registry import Registry
from nodes.kernel.shapes import register_builtin_shapes
from nodes.vocab.kinds import register_knowledge_vocab

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "check-corpus"
ORACLE = FIXTURES / "check.oracle.json"


def test_check_findings_match_committed_oracle(tmp_path):
    # Cross-language freeze: Corpus.check over the committed fixture corpus must
    # reproduce the committed findings oracle exactly (severity, code, ref, detail).
    # The TypeScript kernel asserts the same fixture + oracle.
    corpus_dir = tmp_path / "check-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    reg = Registry()
    register_builtin_shapes(reg)
    register_knowledge_vocab(reg)
    corpus = Corpus(corpus_dir, registry=reg)
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle, "oracle must not be empty"
    actual = [{"severity": f.severity, "code": f.code, "ref": f.ref, "detail": f.detail} for f in corpus.check()]
    assert actual == oracle


def test_check_corpus_has_seven_nodes(tmp_path):
    corpus_dir = tmp_path / "check-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    assert len(Corpus(corpus_dir).all()) == 7
```

- [ ] **Step 4: Run the Python parity test**

From `python/`: `rtk uv run --frozen pytest tests/test_check_parity.py -q`
Expected: PASS (2 tests). If the findings differ from the oracle, fix the fixture/oracle (not the sort contract) — the oracle above was derived by hand from §8 of the standard.

- [ ] **Step 5: Write the TypeScript parity test**

Create `ts/tests/check_parity.test.ts`:

```ts
import { cpSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Corpus, Registry, registerBuiltinShapes } from "../src/index.js";
import { registerKnowledgeVocab } from "../src/vocab/index.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures", import.meta.url));

function copiedCorpus(): string {
  const root = join(mkdtempSync(join(tmpdir(), "nodes-check-parity-")), "check-corpus");
  cpSync(join(FIXTURES, "check-corpus"), root, { recursive: true });
  return root;
}

describe("check parity", () => {
  it("Corpus.check matches the committed oracle", () => {
    // Cross-language freeze: same fixture + oracle as the Python kernel.
    const reg = new Registry();
    registerBuiltinShapes(reg);
    registerKnowledgeVocab(reg);
    const corpus = new Corpus(copiedCorpus(), reg);
    const oracle = JSON.parse(readFileSync(join(FIXTURES, "check.oracle.json"), "utf-8"));
    expect(oracle.length).toBeGreaterThan(0);
    const actual = corpus.check().map((f) => ({
      severity: f.severity,
      code: f.code,
      ref: f.ref,
      detail: f.detail,
    }));
    expect(actual).toEqual(oracle);
  });

  it("fixture corpus has seven nodes", () => {
    expect(new Corpus(copiedCorpus()).all()).toHaveLength(7);
  });
});
```

- [ ] **Step 6: Run the TypeScript parity test**

From `ts/`: `npm test -- check_parity`
Expected: PASS (2 tests).

- [ ] **Step 7: Run all gates in both languages and commit**

From `python/`:

```bash
rtk uv run --frozen pytest -q
rtk uv run --frozen ruff check .
rtk uv run --frozen pyright src
```

From `ts/`:

```bash
npm test
npm run typecheck
npm run check
```

Expected: all green. Then from the repo root:

```bash
rtk git add fixtures/check-corpus fixtures/check.oracle.json python/tests/test_check_parity.py ts/tests/check_parity.test.ts
rtk git commit -m "test: shared check-corpus conformance fixture + cross-language findings oracle"
```

---

## Self-review notes (for the controller)

- **Spec coverage:** design §4 (standard + tiers) ↔ Task 2; §5 (README/AGENTS) ↔ Task 3; §6 (doc moves: rename ↔ Task 1, format.md deletion + sweep + substrate note ↔ Task 2, ts/README ↔ Task 4); §7 (`Registry.check` ↔ Tasks 5/7, `Corpus.check` ↔ Tasks 6/8); §8 (testing: unit ↔ Tasks 5–8, shared fixture + oracle ↔ Task 9). Design non-goals (no membership traversal, no Python fingerprints, no construction changes) are reflected in STANDARD.md §13 and the Global Constraints.
- **Type consistency:** `Violation {code, detail, message}` (Tasks 5/7) is consumed field-for-field by `Finding` construction in Tasks 6/8; finding codes and the `(ref, code, detail)` sort are identical in STANDARD.md §8, both implementations, and the oracle. `register_builtin_shapes` + `register_knowledge_vocab` (and camelCase twins) are the registry recipe in Tasks 6, 8, and 9.
- **Oracle derivation check:** note:stray → `facet-unexpected/source`; paper:broken → `facet-missing/source` (error) + `dangling-ref/paper:ghost` (warning; `dangling-ref` < `facet-missing` lexicographically, hence the warning row first); paper:empty → `invariant-violated/""` (empty source passes presence, fails the identifiability invariant); paper:typo → `facet-invalid/""` (unknown key under extra-forbid raises `FacetError` inside the invariant); zzz:mystery → `unknown-kind/zzz`; topic:clean and note:tidy contribute nothing. Refs sort `note:stray < paper:broken < paper:empty < paper:typo < zzz:mystery`.
- **Sweep safety:** both sweeps exclude the two 2026-07-10 files, which intentionally contain the old path strings they describe changing.
