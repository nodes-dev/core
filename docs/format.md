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
