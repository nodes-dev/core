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
- No full-text search or embeddings/similarity index yet.
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
structural `Index` are ported (see below). The knowledge vocab is not yet ported.

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
