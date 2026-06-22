# nodes — TypeScript Kernel Port (Design)

- **Status:** Draft (design approved, pending spec review)
- **Date:** 2026-06-21
- **Plan number:** 4 (substrate roadmap §10 step 2: "Land Python + TS kernel libraries")
- **Scope:** Port the **Plan-1 Python kernel** to TypeScript at behavioral + on-disk-format
  parity. Restructure the repo into `python/` + `ts/` siblings. **No `Index`, no `Corpus`,
  no knowledge vocab** — those are later TS plans.

## 1. Motivation & goals

The substrate design (`2026-06-21-nodes-substrate-design.md` §6) requires Python and TypeScript
implementations that "share one API surface" so both applications — `science` (Python) and a
future Mindful v6 (likely TS) — operate on the **same on-disk corpus**. The Python kernel landed
across Plans 1–3. This plan brings TypeScript to parity with **Plan 1** (the foundational
kernel), the smallest reviewable unit, leaving the derived index and the knowledge vocab to
later TS plans.

### Goals

- A TypeScript kernel that reads and writes the **identical markdown + YAML on-disk format** the
  Python kernel uses, verified against a **shared, committed parity oracle**.
- **Behavioral parity and format parity** with idiomatic TypeScript naming — *not* identifier
  parity. The TS API uses camelCase; the on-disk format is byte-format-independent but
  semantically identical (see §5).
- A clean monorepo seam (`python/` + `ts/`) with shared, language-agnostic artifacts (`docs/`,
  `fixtures/`) at the root.

### Non-goals (this plan)

- **`Index` / `Corpus`** (Plan 2 equivalents) — a later TS plan.
- **Knowledge vocab** (Plan 3 equivalent: Source facet, kind roster, predicates) — a later TS plan.
- **Byte-identical cross-language YAML emission** — explicitly rejected (§5). PyYAML and the JS
  `yaml` package differ in quoting and indentation; forcing byte-parity wastes effort on emitter
  trivia and produces fragile tests. The substrate §3.2 contract is about the two *relation
  serialization shapes* round-tripping correctly, which semantic parity fully satisfies.

## 2. What "Plan-1 Store" means (precise)

The port mirrors the kernel **as it stood at the Plan-1 merge (commit `f3e6ee4`)**, *not* current
Python `main`. This distinction is load-bearing:

- At `f3e6ee4` there was **no `Corpus` and no `Index`**. `Store` itself was the complete CRUD
  surface, doing O(n) file-scan collision detection, resolution, and rename.
- **`f3e6ee4` is the *post-hardening* Plan-1 merge.** Plan 1's final hardening pass
  (`b56a055..f3e6ee4`) already fixed rename crash-atomicity to **write-new-then-delete-old**
  (earlier, mid-Plan-1 task code deleted the old file first). The pin is to `f3e6ee4`, so the TS
  rename ordering in §6.8 is *exact* mirroring of the pinned commit — not a divergence from it.
- On current `main`, Plan 2 introduced `Corpus` + `Index` and **moved** collision/resolution/
  rename out of `Store`; today's `Store` is slim file mechanics and `docs/format.md` calls
  `Corpus` the primary API.

**This port targets the historical Plan-1 `Store`.** The TS `Store` carries the full CRUD
behavior (write/collision, resolve/read, delete, rename + inbound rewrite). No `Corpus` class is
introduced in this plan.

The eight Plan-1 modules in scope: `errors`, `ids`, `relations`, `node`, `frontmatter`,
`registry`, `shapes`, `store` (plus a barrel `index.ts` for package exports).

## 3. Repo restructure

```
~/d/nodes/
  docs/            (unchanged — shared, language-agnostic specs & plans)
  fixtures/        (NEW — shared parity fixtures + canonical-JSON oracle; see §5)
  python/          (MOVED from root: src/, tests/, pyproject.toml, uv.lock)
  ts/              (NEW — package.json, tsconfig.json, biome.json, src/, tests/)
  .superpowers/    (unchanged — SDD ledger, git-ignored)
  .gitignore       (root — add node_modules/, ts/dist/)
```

- Python package moves wholesale into `python/`. `.venv` is **recreated** in `python/` via
  `uv sync` (it is git-ignored and carries absolute paths; do not `git mv` it).
- The existing `python/tests/fixtures/gene_phf19.md` **moves to root `fixtures/gene_phf19.md`**
  (shared between suites); `test_format_golden.py`'s `FIXTURE` path updates to point at root
  `fixtures/`.
- `rtk` is a global hook-based proxy, not a repo script — unaffected by the move; Python commands
  simply run from `python/`.
- **Migration gate (required, before any TS code):** after the move + venv recreate, the full
  Python suite must still pass from its new home — `rtk uv run pytest -q` run in `python/`
  (equivalently `rtk uv run --project python pytest -q`), **112 passing, ruff + pyright clean**.
  This gate is the first task's deliverable.

## 4. TypeScript tooling

| Concern | Choice | Role / analog |
|---------|--------|---------------|
| Language | TypeScript, ESM (`"type": "module"`), `strict: true`, target ES2022, `NodeNext` resolution | — |
| Runtime validation | **Zod** | Pydantic analog: one schema yields runtime validation + inferred static types |
| YAML | **`yaml`** npm package | PyYAML analog; supports YAML 1.1/1.2, comments, `parse`/`stringify` |
| Tests | **Vitest** | pytest analog |
| Lint + format | **Biome** | ruff analog (single fast tool) |
| Type gate | **`tsc --noEmit`** | pyright analog — the *actual* type check; Biome does not type-check |
| Package manager | **npm** | A single `ts/` package needs no workspace/pnpm complexity yet |

`ts/package.json` pins environment expectations:

```jsonc
{
  "name": "@nodes/kernel",
  "type": "module",
  "engines": { "node": ">=20" },
  "packageManager": "npm@10",
  "dependencies": { "zod": "^3", "yaml": "^2" },
  "devDependencies": { "vitest": "^2", "@biomejs/biome": "^1", "typescript": "^5" },
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "check": "biome check ."
  }
}
```

Gates are written `rtk`-prefixed to match the Plan 3 convention (the hook rewrites transparently):
`rtk npm run typecheck`, `rtk npm test`, `rtk npm run check`, all from `ts/`.

## 5. Cross-language parity contract

The contract is **semantic**, anchored to a committed oracle — never byte comparison.

### 5.1 Canonical JSON

Define the **canonical JSON** of a node as its normalized in-memory form rendered to JSON:

```jsonc
{
  "id": "gene:PHF19",
  "uid": "7b2cdeadbeef7b2cdeadbeef7b2cdeef",
  "kind": "gene",
  "title": "PHF19",
  "body": "PHF19 is a PRC2-associated component.\n",
  "metadata": { "created": null, "updated": null, "version": 1 },
  "relations": [
    { "source": "gene:PHF19", "predicate": "relatesTo",     "target": "topic:polycomb",
      "directed": true, "weight": null, "attrs": {} },
    { "source": "gene:PHF19", "predicate": "interacts_with", "target": "gene:EZH2",
      "directed": true, "weight": null, "attrs": {} }
  ],
  "facets": { "bio-axes": { "primary_external_id": "HGNC:7296" } },
  "deprecated_ids": []
}
```

Normalization rules:

- **Relations are normalized**: `source` always explicit; `related:` sugar expands to
  `predicate: relatesTo` relations. Order = document order (`related:` entries first, then
  `relations:` entries) — matching `node_from_markdown`.
- **Dates are `YYYY-MM-DD` strings or `null`** — never a language-native date object. Python
  currently models `created`/`updated` as Pydantic `date`; for the oracle they serialize to the
  ISO string. **TS must not use JS `Date` as the public model** for these fields — it uses ISO
  date strings validated by a Zod date-string schema.
- Object **key order is irrelevant** to the comparison (deep structural equality); **array order
  is significant**.
- The canonical JSON uses the **on-disk field name** `deprecated_ids` (not the camelCase API
  name) so the oracle is language-neutral.

### 5.2 The committed oracle

Two shared files at root `fixtures/`:

- `fixtures/gene_phf19.md` — the shared source-of-truth markdown node.
- `fixtures/gene_phf19.canonical.json` — its expected canonical JSON (per §5.1).

### 5.3 Required checks

1. **Python parse parity:** Python `node_from_markdown(gene_phf19.md)` → canonical JSON equals
   `gene_phf19.canonical.json`.
2. **TS parse parity:** TS `nodeFromMarkdown(gene_phf19.md)` → canonical JSON equals the same file.
3. **TS→Python:** TS emits markdown → Python parses it → canonical JSON equals the oracle.
4. **Python→TS:** Python emits markdown → TS parses it → canonical JSON equals the oracle.
5. **Per-language semantic idempotency:** within each language,
   `parse(serialize(parse(md)))` equals `parse(md)` in canonical JSON (not byte-for-byte).

Checks 3 and 4 are the cross-emitter guarantee; they pass even though the two emitters produce
different bytes. Operationally, the per-language suites assert 1/2/5 directly; 3/4 are covered by
**committed cross-emitted fixtures** — a Python-emitted sample (`fixtures/gene_phf19.py-emit.md`)
that TS parses, and a TS-emitted sample (`fixtures/gene_phf19.ts-emit.md`) that Python parses — so
neither suite needs the other language's runtime at test time.

**Stale-fixture guard (required).** A committed cross-emitted fixture can silently rot: if an
emitter later regresses, the *other* language still parses the stale committed file and passes.
To prevent this, each emitted fixture is **regenerated-and-diffed by its own language's gate**:
the emitting language re-emits from its *current* emitter and asserts the result equals the
committed fixture (canonical-JSON equality; on emitter drift the test **fails** and the fixture
must be regenerated and re-reviewed). Thus check 3 = (TS gate proves `ts-emit.md` is current) +
(Python parses it → oracle); check 4 is symmetric. A live dual-runtime CI harness that re-emits in
both languages on every run is an acceptable stronger alternative if CI later runs both toolchains,
but is not required given the in-suite regenerate-and-diff guard.

## 6. Module-by-module port

camelCase applies to the **programmatic surface and Node field names**. On-disk YAML keys —
including relation payload keys (`source`, `predicate`, `target`, `directed`, `weight`, `attrs`),
metadata keys (`created`, `updated`, `version`), and facet payload keys (`members`, `edges`,
`shape`, `primary_external_id`, …) — stay exactly as authored. **The only field that differs
between API and disk is `deprecatedIds` (API) ↔ `deprecated_ids` (disk).**

### 6.1 `errors.ts`
The 8-class hierarchy, all extending a base `NodesError extends Error`:
`IdError`, `RefError`, `CollisionError`, `UnknownKindError`, `FacetError`, `InvariantError`,
`ValidationError`. Each sets `this.name` for legible stacks.

### 6.2 `ids.ts`
`NodeId { kind, slug }`. Same two regexes verbatim:
`KIND_RE = /^[a-z][a-z0-9-]*$/`, `SLUG_RE = /^[A-Za-z0-9][A-Za-z0-9:_.-]*$/`.
`parse(raw)` (split on first `:`, validate both halves, throw `IdError`),
`isValidKind`, `isValidSlug`, `toString()` → `kind:slug`.

### 6.3 `relations.ts`
`RELATES_TO = "relatesTo"`. `Relation` Zod schema:
`{ source, predicate, target, directed=true, weight=null, attrs={} }`.
`fromSerialized(data, containerId)` (fills `source` from container when absent),
`toSerialized(containerId)` (drops `source` when it equals container; omits `directed` when
`true`, `weight` when `null`, `attrs` when empty), `relatesTo(source, target)`,
`tagToRelation(source, tag, aliasMap)` (strips leading `#`, resolves via alias map, exact then
lowercased, throws `RefError` on miss).

### 6.4 `node.ts`
`newUid()` = `crypto.randomUUID()` with dashes stripped → 32 lowercase hex chars, matching
Python's `uuid4().hex`. `NodeMetadata` Zod schema `{ created: dateStr|null = null, updated:
dateStr|null = null, version: number = 1 }` where `dateStr` is a `YYYY-MM-DD`-validated string —
**every field carries a Zod default** so an absent or `{}` metadata parses to `{created:null,
updated:null, version:1}`, matching Python's Pydantic defaults
([`node.py:25`](../../python/src/nodes/kernel/node.py)). `Node` Zod schema `{ id, uid =
newUid(), kind, title, body = "", metadata = {created:null,updated:null,version:1}, relations =
[], facets = {}, deprecatedIds = [] }` — **all of `metadata`, `relations`, `facets`,
`deprecatedIds` default via Zod** so minimal TS construction (`{id, kind, title}`) produces a
node byte-for-byte equal in canonical JSON to minimal Python construction. The schema carries
an after-validator: `NodeId.parse(id)` (wrap `IdError` → `ValidationError`) and assert
`parsed.kind === kind` (else `ValidationError`). `facets` is loosely typed
(`Record<string, Record<string, unknown>>`), validated on demand by registry/shapes — mirroring
Python's `dict[str, dict]`.

### 6.5 `frontmatter.ts`
- `splitFrontmatter(text)` → `[frontmatter, body]`. Handle both `---\n` and `---\r\n` openings;
  line-anchored closing `---` (Plan 1's Task-7 fix). Return `[{}, text]` when no valid
  frontmatter block is present.
- **YAML parse-error handling (explicit):** the `yaml` package is lenient — `parse` accepts many
  inputs and parses what it can rather than throwing on malformed YAML. The parser MUST use
  `parseDocument` (or equivalent) and **explicitly inspect `.errors`**, raising `ValidationError`
  when the frontmatter block does not parse cleanly. Do not assume malformed YAML throws.
- `nodeFromMarkdown(text)`: require `id`, `uid`, `kind`, `title` (missing → `ValidationError`);
  expand `related:` → `relatesTo` relations, then `relations:` via `fromSerialized`; build
  `metadata` from present `created`/`updated`/`version`; pass `facets`, `deprecated_ids` through.
- `nodeToMarkdown(node)`: emit top-level `id`/`uid`/`kind`/`title`; include `created`/`updated`
  only when set, `version` only when ≠ 1; split relations into plain-`relatesTo` → `related:` and
  the rest → `relations:` (`toSerialized`); include `facets` and `deprecated_ids` only when
  non-empty. Dates emit as unquoted `YYYY-MM-DD`. Body appended after the closing `---`.

### 6.6 `registry.ts`
`KindSpec { name, requiredFacets=Set, optionalFacets=Set, invariants=[] }`
(`Invariant = (node: Node) => void`). `Registry`: `register`, `isRegistered`, `get` (throw
`UnknownKindError` on miss), `validate(node)` — missing required facets → `FacetError`;
unexpected facets (present − (required ∪ optional)) → `FacetError`; then run each invariant.

### 6.7 `shapes.ts`
`MEMBERSHIP = "membership"`. `Membership` Zod schema `{ shape, members: string[] | Record<string,
string> = [], edges: Relation[] = [] }` — `members` and `edges` **carry Zod defaults** (`[]`),
matching Python's `default_factory` ([`shapes.py:15`](../../python/src/nodes/kernel/shapes.py)),
so a membership facet with only `shape` validates. `membershipOf(node)` (missing facet →
`FacetError`; validate via schema). Invariants: `requireUniqueMembers`, `requireDictKeys`, `requireAcyclic` (DFS with
visiting/done sets, `InvariantError` on back-edge), `requireSingleParent`. `registerBuiltinShapes`
registers set/list/dict/graph/dag/tree with the same required-facet + invariant wiring as Python.

### 6.8 `store.ts` (historical Plan-1 CRUD surface)
Constructed with a root path. Methods mirror `f3e6ee4` behavior:
- `pathFor(id)` → `root/<kind>/<slug-with-':'→'__'>.md`.
- `allNodes()` → parse every `*.md` under root, sorted by path.
- `write(node)` → O(n) identity-collision check (`uid` already owned by a different live `id` →
  `CollisionError` "use rename()"; overlapping claimed ids — `id` ∪ `deprecatedIds` — →
  `CollisionError`), then write file.
- `resolve(ref)` / `read(ref)` → live id (file path) first, else scan `deprecatedIds`, else
  `RefError`.
- `delete(id)` → unlink (missing → `RefError`).
- `rename(oldId, newId)` → reject taken target (`CollisionError`); read node; set `id`/`kind`,
  append old id to `deprecatedIds`; **write new file FIRST, then unlink old** (crash-atomic,
  no data-loss window — this is the pinned `f3e6ee4` post-hardening order; see §2); O(n) inbound
  rewrite of `relations` + `membership` (`members` list/dict
  and `edges`) across the corpus, re-writing each changed referrer.

### 6.9 `index.ts` (barrel)
Re-export the public surface: errors, `NodeId`, `Relation`/`relatesTo`/`tagToRelation`/
`RELATES_TO`, `Node`/`NodeMetadata`/`newUid`, `nodeFromMarkdown`/`nodeToMarkdown`/
`splitFrontmatter`, `KindSpec`/`Registry`, `Membership`/`membershipOf`/the invariants/
`registerBuiltinShapes`/`MEMBERSHIP`, `Store`.

## 7. Errors

The TS hierarchy mirrors §6.1 one-for-one. Validation failures map to the same typed errors as
Python: malformed id → `IdError` (wrapped to `ValidationError` inside `Node`); missing
frontmatter field → `ValidationError`; bad/missing facet → `FacetError`; invariant breach →
`InvariantError`; id collision → `CollisionError`; unresolvable ref → `RefError`; unknown kind →
`UnknownKindError`. Zod validation errors are caught at the schema boundary and re-thrown as the
appropriate kernel error (never leaked raw), matching Plan 3's Pydantic-wrapping discipline.

## 8. Testing

Per-module Vitest suites mirroring the Python tests (`test_ids`, `test_relations`, `test_node`,
`test_frontmatter`, `test_registry`, `test_shapes`, `test_store`, `test_errors`), plus the
cross-language parity suite of §5.3. Each task is TDD: failing test → minimal port → green.
Final gate: full Vitest suite green, `tsc --noEmit` clean, `biome check` clean, **and** the Python
suite still 112 / ruff + pyright clean from `python/`.

## 9. Docs

- `ts/README.md`: install, scripts, the camelCase-API / snake_case-on-disk note, the
  Plan-1-`Store`-is-the-CRUD-surface note.
- Append a short "TypeScript kernel (Plan 4)" section to `docs/format.md`: the semantic parity
  contract, the shared `fixtures/` oracle, and the explicit non-goal of byte-identical YAML.

## 10. Why this shape

- **Behavioral + format parity over identifier parity:** the corpus is the contract; idiomatic TS
  naming costs nothing because the on-disk format and the canonical-JSON oracle are language-neutral.
- **Semantic parity over byte parity:** avoids brittle coupling to two YAML emitters' formatting
  while still guaranteeing every node round-trips identically in meaning across languages.
- **Mirror Plan 1 exactly (historical `Store`):** smallest reviewable unit; `Index`/`Corpus`/vocab
  land as later TS plans, keeping each plan independently shippable.
- **Fail early / explicit:** Zod at the schema boundary, explicit YAML parse-error inspection,
  typed kernel errors throughout — no silent fallbacks.

## 11. Open / deferred

- **Deferred to later TS plans:** `Index` + `Corpus` (Plan 2 equivalent); knowledge vocab
  (Plan 3 equivalent); the language-agnostic spec document (§6 of the substrate design).
- **To settle during planning:** exact `tsconfig` lib/target details. (Cross-language checks 3/4
  are resolved: committed cross-emitted fixtures kept current by a per-language regenerate-and-diff
  gate — §5.3.)
