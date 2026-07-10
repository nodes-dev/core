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
the vocab `source` facet). Typed facet accessors MUST surface a missing or malformed
payload as `FacetError` — a raw Pydantic/Zod error never escapes a public API. Whether
unknown payload keys are rejected is a property of each facet's schema: the vocab
`source` facet MUST reject them (fail-early on typos); the built-in shape form facets
(§5) currently tolerate them. New facet schemas SHOULD reject unknown keys.

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
  defaults to the containing node. Serializers MUST omit `source` when it equals the
  container; a relation sourced elsewhere carries an explicit `source`.
- **Graph edge** (in a structure's `edges` facet): `{ source, predicate, target, … }` —
  both endpoints explicit (the structure node is the container, not an endpoint).
- `related: [ref, …]` is sugar for `relatesTo` relations sourced at the node. On
  serialization, a plain `relatesTo` relation (directed, no weight, no attrs, sourced at
  the node) MUST emit into `related`; all other relations emit into `relations`.
- Parsers MUST fill an omitted `source` from the container into the normalized form.
  Serializers MUST omit optional relation fields at their defaults (`directed: true`,
  no `weight`, empty `attrs`). Round-trip MUST be lossless.

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

### 11.1 Canonical JSON projection

Cross-language node equality is defined over this projection (implemented by the
`to_canonical` / `toCanonical` test helpers):

```json
{
  "id": "...", "uid": "...", "kind": "...", "title": "...", "body": "...",
  "metadata": { "created": "YYYY-MM-DD or null", "updated": "YYYY-MM-DD or null", "version": 1 },
  "relations": [ { "source": "...", "predicate": "...", "target": "...",
                   "directed": true, "weight": null, "attrs": {} } ],
  "facets": { },
  "deprecated_ids": [ ]
}
```

Relations are normalized (`source` explicit, every field present) in document order;
dates render as `YYYY-MM-DD` strings or `null`; field names use the on-disk forms
(`deprecated_ids`).

### 11.2 Fixture inventory

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
