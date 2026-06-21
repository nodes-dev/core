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

## Known kernel limitations (resolved in later plans)
- No derived search/graph index yet (Plan 2): full-text, resolved relation graph, embeddings.
  Kernel `resolve()` / collision checks do linear scans; the index makes lookups O(1).
- `delete()` operates on a node's current (live) id only; passing a stale/deprecated id raises
  `RefError`. This is intentional: a stale alias must not silently remove the renamed live node.
  Use `read()` / `resolve()` first if you need to look up the live id from a deprecated one.
