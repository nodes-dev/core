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
