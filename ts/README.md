# @nodes/kernel (TypeScript)

TypeScript port of the `nodes` kernel — behavioral + on-disk-format parity with the Python kernel.

## Scope

Mirrors the current Python kernel: `Node`/`Relation`, ids, errors, frontmatter parse/serialize,
registry, structural shapes, a slimmed `Store` (pure file mechanics), an in-memory `Index`
(O(1) resolution + resolved relations graph), and a `Corpus` coordinator — the primary API for
all mutations (`add`/`get`/`rename`/`delete`) and graph queries (`outbound`/`inbound`/`neighbors`/
`dangling`). There is **no full-text search, no embeddings, no on-disk index persistence, and no
membership-graph traversal** — those, and the knowledge vocab, are later TypeScript plans.

## Conventions

- **camelCase API, snake_case on disk.** The on-disk YAML format is identical to Python's; the only
  field that differs API-vs-disk is `deprecatedIds` (API) ↔ `deprecated_ids` (file).
- Dates are `YYYY-MM-DD` strings (never JS `Date`), validated by Zod.
- Validation failures surface as the kernel error hierarchy (`ValidationError`, `FacetError`, …),
  never raw Zod errors.

## Scripts

- `npm test` — Vitest suite (includes the cross-language parity checks)
- `npm run typecheck` — `tsc --noEmit` (the type gate)
- `npm run check` — Biome lint + format
