# @nodes/kernel (TypeScript)

TypeScript port of the `nodes` kernel — behavioral + on-disk-format parity with the Python kernel.

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
