# @nodes/kernel (TypeScript)

TypeScript port of the `nodes` kernel — behavioral + on-disk-format parity with the Python kernel.

## Scope

Mirrors the **Plan-1 Python kernel**: `Node`/`Relation`, ids, errors, frontmatter parse/serialize,
registry, structural shapes, and a `Store` that is the full CRUD surface (O(n) collision detection,
resolution, and crash-atomic rename). There is **no `Corpus` and no derived `Index`** — those, and
the knowledge vocab, are later TypeScript plans.

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
