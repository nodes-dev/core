# nodes — on-disk format (kernel)

One file per node: YAML frontmatter + markdown body. Files are canonical (git-versioned).

## Top-level frontmatter fields
- `id` (required): canonical `kind:slug`. Stored + display ref form.
- `uid` (required): immutable UUID (hex). Identity anchor; survives renames.
- `kind` (required): must equal the `id`'s kind segment.
- `title` (required).
- `created`, `updated` (optional): ISO dates, top-level.
- `version` (optional): integer, top-level, default 1 (omitted when default).
- `related` (optional): list of target ids — sugar for `relatesTo` relations sourced at this node.
- `relations` (optional): typed relations; `source` omitted (implied = this node).
- `facets` (optional): nested map, keyed by facet name.
- `deprecated_ids` (optional): previous ids retained after rename for ref resolution.

## Relations
Normalized form: `{source, predicate, target, directed?, weight?, attrs?}`.
- Node-relation (in `related`/`relations`): `source` implied = containing node.
- Graph edge (in a structure's `membership.edges`): both `source` and `target` explicit.

## Structures
A structure node carries a `membership` facet: `{shape, members, edges?}`.
Shapes: `set`, `list`, `dict`, `graph`, `dag`, `tree` (invariants per spec §3.4).

## Index & API (Plan 2)
The kernel ships an in-memory **structural index** (`nodes.kernel.index.Index`) and a
**`Corpus`** coordinator (`nodes.kernel.corpus.Corpus`) that owns a `Store` + an `Index`.
`Corpus` is the primary API: `add`, `get`/`resolve`, `rename`, `delete`, `all`, and the
relations-graph queries `outbound`, `inbound`, `neighbors`, `dangling`.

- Resolution (`id` / deprecated `id` → `uid`) and collision checks are **O(1)** via the index;
  a live id always wins over a deprecated id.
- `rename` is **O(degree)**: it rewrites only the referrers the reverse index names (relations
  `source`/`target`, membership members, and edge `source`/`target`), plus the renamed node's
  own references.
- Graph queries are **relations-only** and uid-based. Dangling targets (a relation whose target
  no longer resolves) are a normal state — surfaced by `outbound(source)` and `dangling()`, never
  raised. `inbound`/`outbound` raise `RefError` only when the *input* ref does not resolve.
- `delete()` is **live-id-only**: passing a stale/deprecated id raises `RefError`, so a stale
  alias never silently removes the renamed live node. Inbound references to a deleted node remain
  as dangling — retained in the live index and on disk — and are surfaced by `dangling()`.

### Known kernel limitations (resolved in later plans)
- The index is in-memory and rebuilt on `Corpus(root)` construction; no on-disk persistence yet.
- No embeddings/similarity index yet. (Full-text search is implemented in both the
  Python and TypeScript kernels — see "Full-text search (derived index)" below.)
- No public membership-graph traversal (tree descendants, DAG reachability) yet — membership refs
  are tracked internally for rename but are not exposed as graph edges.

## Knowledge vocab (Plan 3)
`nodes.vocab` is a separately-importable profile of generally-useful knowledge kinds, one layer
above the domain-free kernel. It imports only from `nodes.kernel`; the kernel never imports it.
Register it onto a `Registry` with `register_knowledge_vocab(reg)` (mirrors
`register_builtin_shapes`).

- **Roster (7 kinds).** Prose (bare, no facets): `note`, `idea`, `question`, `topic`. Source
  (require the `source` facet + the identifiability invariant): `paper`, `book`, `dataset`.
- **`Source` facet** (`facets.source`): `{authors?, year?, container?, identifier?, url?}`, with
  `extra="forbid"` (unknown keys fail) and an invariant requiring at least one of
  `authors`/`year`/`identifier`/`url`. The node's `kind` discriminates paper/book/dataset and
  `title` holds the work title, so `Source` carries neither.
- **Predicates** (`nodes.vocab.predicates`): canonical names `about` (→ topic), `cites`
  (→ source), `answers`/`asks` (→ question), `refines` (→ node), plus helper constructors. A
  shared vocabulary only — predicates remain free-string and are not enforced by the kernel.
- **Enforcement.** `Corpus(root, registry=...)` validates on `add` and `rename`; with
  `registry=None` (default) behavior is unchanged. A registry-backed corpus rejects unregistered
  kinds and facet/invariant violations **before any disk write**, and `rename`
  validates the renamed node and every rewritten referrer before writing anything (no partial
  rename).

## TypeScript kernel (Plan 4)

The TypeScript kernel (`ts/`) reads and writes the **same on-disk format** as the Python kernel.
Parity is **semantic, not byte-identical** — PyYAML and the JS `yaml` emitter differ in formatting,
which is an explicit non-goal to reconcile.

Parity is pinned to a shared oracle under root `fixtures/`:

- `gene_phf19.md` — shared source node.
- `gene_phf19.canonical.json` — the canonical-JSON oracle (normalized relations; dates as
  `YYYY-MM-DD` strings; on-disk field name `deprecated_ids`).
- `gene_phf19.py-emit.md`, `gene_phf19.ts-emit.md` — committed cross-emitted samples. Each is kept
  current by a **regenerate-and-diff** test in its emitting language, then parsed by the other
  language and checked against the oracle.

The TypeScript `Store` is slimmed to pure file mechanics; the `Corpus` coordinator and its in-memory
structural `Index` are ported (see below). The knowledge vocab is ported too — see "TypeScript
knowledge vocab" below.

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

## TypeScript knowledge vocab

`ts/src/vocab/` mirrors the Python `nodes.vocab` layer (see "Knowledge vocab (Plan 3)" above):
the same seven kinds, the same `Source` facet, and the same predicate vocabulary. It imports only
from the kernel modules; the kernel never imports it, and it is **not** part of the kernel barrel
(`ts/src/index.ts`) — import it from `ts/src/vocab/index.ts`.

- **Source facet.** `SourceSchema` is a Zod `.strict()` object (`authors`, `year`, `container`,
  `identifier`, `url`); `.strict()` is the parity analog of Pydantic's `extra="forbid"` — unknown
  keys fail. `sourceOf(node)` raises `FacetError` on a missing or malformed facet (never a raw
  `ZodError`); `requireIdentifiableSource(node)` raises `InvariantError` on a source with no
  identifying fields (none of `authors`/`year`/`identifier`/`url` set).
- **Kinds.** `registerKnowledgeVocab(reg)` registers prose kinds (`note`/`idea`/`question`/`topic`)
  bare and source kinds (`paper`/`book`/`dataset`) with the `source` facet + identifiability
  invariant — mirroring `registerBuiltinShapes`.
- **Predicates.** `ABOUT`/`CITES`/`ANSWERS`/`ASKS`/`REFINES` constants plus helper constructors,
  exposed as the `predicates` namespace. Free-string only; never enforced by the kernel.
- **Enforcement.** `new Corpus(root, reg)` with a vocab-registered `Registry` validates on `add`
  and `rename` before any disk write — same fail-early contract as the Python `Corpus`.

## Full-text search (derived index)

The Python kernel ships a second derived index beside the structural `Index`: an
in-memory BM25F full-text search index (`nodes.kernel.search`). `Corpus` builds it
from the same `all_nodes()` scan, keeps it current on `add`/`delete`/`rename`, and
exposes `Corpus.search(query, limit=None) -> list[SearchHit]`.

- **Tokenizer.** NFC-normalize → lowercase → split into Unicode-alphanumeric runs
  → drop a fixed 33-word stop list; no stemming. Pinned across languages by
  `fixtures/search.tokenizer.json`.
- **Scoring.** BM25F over two fields (`title` boosted above `body`) with the
  standard `(K1 + 1)` numerator and a non-negative Lucene IDF. Constants `K1=1.5`,
  `B=0.75`, `TITLE_BOOST=2.0`, `BODY_BOOST=1.0`.
- **Results.** Ranked `SearchHit`s (`id`, `uid`, `score`, `matched_terms`), sorted
  by a 6-decimal half-up `score_key` then `id`. The caller hydrates the `Node` via
  `Corpus.get` when it needs the text.
- **Parity.** A fixture corpus (`fixtures/search-corpus/`) plus a ranking oracle
  (`fixtures/search.oracle.json`) pin ranked ids and 6-dp scores; both languages
  build the index and assert equality. Scores are not claimed bit-identical.

This is in-memory and rebuilt on `Corpus` construction; on-disk persistence is a
later plan.

### TypeScript full-text search

The TypeScript kernel (`ts/src/search.ts`) is a semantic port of `nodes.kernel.search`:
the same tokenizer, BM25F scoring, constants, and `SearchIndex` operations, exposed as
`Corpus.search(query, limit?) -> SearchHit[]` (`SearchHit` carries `id`, `uid`, `score`,
`matchedTerms`). Query-term ordering uses an explicit Unicode code-point comparator — not
JavaScript's default UTF-16 code-unit sort — so non-BMP tokens order identically to Python.

Parity is pinned by the same two fixtures Python generated: `fixtures/search.tokenizer.json`
(the tokenizer freeze) and `fixtures/search-corpus/` + `fixtures/search.oracle.json` (the
ranking freeze). Both languages assert ranked ids and 6-decimal scores against them. Scores
are not claimed bit-identical; the 6-dp `scoreKey` is the cross-language contract, and oracle
scores are compared numerically (not string-compared) to absorb JSON trailing-zero formatting.
