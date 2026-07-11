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

- Python, from `python/`: `uv run --frozen pytest -q`,
  `uv run --frozen ruff check .`, `uv run --frozen pyright src`.
- TypeScript, from `ts/`: `npm test`, `npm run typecheck`, `npm run check`.

## Conventions

- Fail early; no silent fallbacks. Wrap Pydantic/Zod errors into the kernel error
  hierarchy — they never escape public APIs.
- Composition over inheritance: kinds are name + facets + invariants, never subclasses.
- Filepaths in docs use `~/d/nodes/...`.
- No AI-attribution trailers in commit messages.
