# TypeScript Kernel Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the Plan-1 Python kernel to TypeScript at behavioral + on-disk-format parity, and restructure the repo into `python/` + `ts/` siblings.

**Architecture:** Eight TypeScript modules mirror the Plan-1 Python kernel (`errors`, `ids`, `relations`, `node`, `frontmatter`, `registry`, `shapes`, `store`) plus a barrel `index.ts`. Zod schemas play Pydantic's role (parse + fail-early validation); the `yaml` package plays PyYAML's. `Store` is the full CRUD surface (no `Corpus`, no `Index`). Cross-language parity is verified against a committed canonical-JSON oracle and committed cross-emitted fixtures, each kept current by a per-language regenerate-and-diff guard.

**Tech Stack:** TypeScript (ESM, strict), Zod, `yaml` (eemeli), Vitest, Biome, npm. Type gate is `tsc --noEmit`. Python side stays uv + pytest + ruff + pyright.

**Spec:** `docs/designs/2026-06-21-nodes-ts-kernel-design.md`

## Current State Note

This plan has since been implemented and remains useful as the historical Plan-4 rollout for the TypeScript kernel baseline and the `python/` + `ts/` repo split. The base parity contract is still current: TypeScript uses camelCase APIs, writes the shared snake_case on-disk format, and semantic parity is pinned by shared fixtures/oracles rather than byte-identical YAML.

The TypeScript kernel has grown substantially since this checklist:

- The current `ts/` package now includes `Corpus`, structural `Index` (`structural-index.ts`), knowledge vocab, full-text `SearchIndex`, optional similarity `VectorIndex`, and per-language snapshot persistence. Historical statements below like "no Corpus", "no Index", "no knowledge vocab", and "`Store` is the full CRUD surface" describe Plan-4 scope, not current package boundaries.
- Current `Store` is slim file mechanics (`writeFile`, `readFile`, `deleteFile`, `allNodes`, `pathFor`), matching the later Python boundary. Cross-corpus logic lives in `Corpus` and `Index`.
- `Store.allNodes()` now uses `iterCorpusFiles()` so TS scans share snapshot file-walk behavior, including ignoring `.nodes-index/`.
- `ts/src/index.ts` now exports later modules too: `Corpus`, snapshot helpers, `Index`, `SearchIndex`, `VectorIndex`, ranking, and similarity helpers.
- `ts/package.json` now exposes built `dist/` artifacts and includes a `build` script in addition to the original test/typecheck/check scripts.
- The shapes implementation in this plan was superseded by the structural-shapes redesign: current TS shapes split `membership`, `edges`, `order`, and `keys` into separate form facets, mirroring current Python.
- The `docs/STANDARD.md` and `ts/README.md` snippets in Task 10 have already been integrated and later extended with structural index, vocab, search, similarity, and snapshot persistence. Do not replace current docs with the historical snippets below.

Treat code snippets below as the original greenfield implementation sequence, not as replacement code for current `ts/src`, tests, package config, README, or `docs/STANDARD.md`.

## Global Constraints

- **Behavioral + format parity, NOT identifier parity.** TS API is idiomatic camelCase; on-disk YAML keys are identical to Python. The **only** field differing API-vs-disk is `deprecatedIds` (API) ↔ `deprecated_ids` (disk). All relation/metadata/facet payload keys (`source`, `predicate`, `target`, `directed`, `weight`, `attrs`, `created`, `updated`, `version`, `members`, `edges`, `shape`, …) stay exactly as on disk.
- **Mirror the historical Plan-1 `Store` (commit `f3e6ee4`, post-hardening).** `Store` is the complete CRUD surface with O(n) file-scan collision detection, resolution, and rename. Rename order is **write-new-file-FIRST, then unlink old** (crash-atomic). NO `Corpus`, NO `Index`, NO knowledge vocab in this plan.
- **Semantic parity, not byte-identical YAML.** Byte-identical cross-language emission is an explicit non-goal. Parity is proved via the canonical-JSON oracle + committed cross-emitted fixtures, each guarded by a regenerate-and-diff currency test.
- **Dates are `YYYY-MM-DD` strings or `null` — never a JS `Date`.** Validated by a Zod date-string schema.
- **Zod defaults MUST match Pydantic defaults:** `metadata` → `{created:null, updated:null, version:1}`; `relations` → `[]`; `facets` → `{}`; `deprecatedIds` → `[]`; `Membership.members` → `[]`; `Membership.edges` → `[]`.
- **Explicit YAML parse-error handling:** the frontmatter parser uses `parseDocument` and inspects `.errors`; it never assumes malformed YAML throws.
- **Boundary parsers wrap Zod errors into the kernel error hierarchy** (`ValidationError`/`FacetError`), never leaking raw. The boundary parsers are `makeNode`, `nodeFromMarkdown`, and `membershipOf` — the functions that ingest untrusted external input. Low-level schema helpers (`fromSerialized`, `relatesTo`, direct `RelationSchema.parse`) may surface raw Zod errors, mirroring Python where `Relation(...)`/`Relation.from_serialized` surface raw Pydantic errors. Callers reach disk through the boundary parsers, which catch and re-wrap.
- **Tooling:** ESM (`"type":"module"`), `strict:true`, target ES2022, `NodeNext` resolution; relative imports use the `.js` extension. `engines.node` `>=20`, `packageManager` `npm@11.11.0` (refines the spec's illustrative `npm@10` to the installed npm).
- **Command convention.** `rtk` is a token-optimizing proxy for *tool* commands whose output it can trim — `git`, `npm`, `npx`, `uv`, `node`, `grep` — so those are shown `rtk`-prefixed. Shell builtins (`cd`) and filesystem primitives (`mkdir`, `mv`, `rmdir`) have nothing for `rtk` to optimize and are shown bare. Every command — including `cd` — sits on **its own line**; no `&&` chaining. Python commands run from `python/`; TS commands run from `ts/`.
- **Docs use `~/d/` paths**, never `/home/keith/...` or `/mnt/ssd/...`.
- **Final gate:** TS — `vitest run` green, `tsc --noEmit` clean, `biome check` clean. Python — full suite green (≥112), `ruff check` clean, `pyright` clean, both run from `python/`.

---

## File Structure

Current-code note: this file map is the original target. Current `ts/src` also contains `corpus.ts`, `structural-index.ts`, `search.ts`, `similarity.ts`, `snapshot.ts`, `ranking.ts`, and `vocab/`.

```
~/d/nodes/
  docs/                              (unchanged; shared)
  fixtures/                          (NEW shared parity artifacts)
    gene_phf19.md                    (MOVED from python/tests/fixtures/)
    gene_phf19.canonical.json        (NEW oracle — Task 2)
    gene_phf19.py-emit.md            (NEW Python-emitted sample — Task 2)
    gene_phf19.ts-emit.md            (NEW TS-emitted sample — Task 6)
  python/                            (MOVED package: src/, tests/, pyproject.toml, uv.lock)
    tests/_canonical.py              (NEW canonical helper — Task 2)
    tests/test_parity.py             (NEW Python parity tests — Tasks 2 & 10)
  ts/                                (NEW)
    package.json  tsconfig.json  biome.json  package-lock.json
    src/{errors,ids,relations,node,frontmatter,registry,shapes,store,index}.ts
    tests/{_canonical.ts, *.test.ts}
  .gitignore                         (root; add node_modules/, ts/dist/, .venv/)
  .superpowers/                      (unchanged; ledger)
```

---

## Task 1: Repo restructure + TS scaffold

Current-code note: the repo split is complete. The current TS package config has since gained `main`/`types`/`exports` pointing at `dist/` and a `build` script, so the scaffold snippets below are only the initial bootstrap.

**Files:**
- Move (git): `src/` → `python/src/`, `tests/` → `python/tests/`, `pyproject.toml` → `python/pyproject.toml`
- Move (disk, gitignored): `uv.lock` → `python/uv.lock`; recreate `python/.venv` via `uv sync`
- Move (git): `python/tests/fixtures/gene_phf19.md` → `fixtures/gene_phf19.md`
- Modify: `python/tests/test_format_golden.py` (fixture path)
- Modify: `.gitignore`
- Create: `ts/package.json`, `ts/tsconfig.json`, `ts/biome.json`, `ts/src/index.ts`, `ts/tests/smoke.test.ts`

**Interfaces:**
- Produces: the `python/` + `ts/` layout; root `fixtures/gene_phf19.md`; a runnable (empty) TS toolchain.

- [ ] **Step 1: Move the Python package**

```bash
cd ~/d/nodes
mkdir -p python
rtk git mv src python/src
rtk git mv tests python/tests
rtk git mv pyproject.toml python/pyproject.toml
mv uv.lock python/uv.lock          # uv.lock is git-ignored — plain mv
```

- [ ] **Step 2: Move the shared fixture and fix its reference**

```bash
mkdir -p fixtures
rtk git mv python/tests/fixtures/gene_phf19.md fixtures/gene_phf19.md
rmdir python/tests/fixtures 2>/dev/null || true
```

In `python/tests/test_format_golden.py`, change the fixture path (the file moved one level deeper, the fixture moved to repo root):

```python
FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "gene_phf19.md"
```

(Confirm no other test references the fixture: `rtk grep -rln fixtures python/tests --include=*.py` should list only `test_format_golden.py`.)

- [ ] **Step 3: Recreate the Python venv and run the migration gate**

```bash
cd ~/d/nodes/python
rtk uv sync
rtk uv run pytest -q
rtk uv run ruff check src tests
rtk uv run pyright src
```

Expected: pytest **112 passed**; ruff + pyright clean. This is the migration gate — Python must be green from its new home before any TS work.

- [ ] **Step 4: Update root .gitignore**

Append to `~/d/nodes/.gitignore`:

```
.venv/
node_modules/
ts/dist/
```

- [ ] **Step 5: Scaffold the TS project**

`ts/package.json`:

```json
{
  "name": "@nodes/kernel",
  "version": "0.1.0",
  "description": "Problem-agnostic knowledge substrate kernel (TypeScript)",
  "type": "module",
  "engines": { "node": ">=20" },
  "packageManager": "npm@11.11.0",
  "main": "src/index.ts",
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "check": "biome check ."
  },
  "dependencies": {
    "yaml": "^2.5.0",
    "zod": "^3.23.0"
  },
  "devDependencies": {
    "@biomejs/biome": "^1.9.0",
    "@types/node": "^20.0.0",
    "typescript": "^5.5.0",
    "vitest": "^2.0.0"
  }
}
```

`ts/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "lib": ["ES2022"],
    "types": ["node"]
  },
  "include": ["src", "tests"]
}
```

`ts/biome.json`:

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.4/schema.json",
  "files": { "include": ["src/**/*.ts", "tests/**/*.ts"] },
  "formatter": { "enabled": true, "indentStyle": "space", "indentWidth": 2, "lineWidth": 120 },
  "linter": { "enabled": true, "rules": { "recommended": true } }
}
```

`ts/src/index.ts`:

```typescript
export const KERNEL_VERSION = "0.1.0";
```

`ts/tests/smoke.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { KERNEL_VERSION } from "../src/index.js";

describe("scaffold", () => {
  it("exposes a version string", () => {
    expect(KERNEL_VERSION).toBe("0.1.0");
  });
});
```

- [ ] **Step 6: Install and run the TS gates**

```bash
cd ~/d/nodes/ts
rtk npm install
rtk npm run typecheck
rtk npm test
rtk npm run check
```

Expected: typecheck clean; **1 test passed**; biome clean. (`biome check` may report formatting — run `rtk npx biome check --write .` once, then re-run `rtk npm run check` to confirm clean.)

- [ ] **Step 7: Commit**

```bash
cd ~/d/nodes
rtk git add -A
rtk git commit -m "chore: restructure into python/ + ts/; scaffold TS toolchain"
```

---

## Task 2: Python parity oracle + canonical helper

**Files:**
- Create: `python/tests/_canonical.py`
- Create: `fixtures/gene_phf19.canonical.json`
- Create: `fixtures/gene_phf19.py-emit.md`
- Create: `python/tests/test_parity.py`

**Interfaces:**
- Produces: `to_canonical(node) -> dict` (the canonical-JSON shape, §5.1 of spec); the committed oracle `gene_phf19.canonical.json`; the committed Python-emitted sample `gene_phf19.py-emit.md` (consumed by TS in Task 10).

- [ ] **Step 1: Write the canonical helper**

`python/tests/_canonical.py`:

```python
from __future__ import annotations

from nodes.kernel.node import Node


def to_canonical(node: Node) -> dict:
    """Language-neutral canonical JSON of a node (spec §5.1).

    Relations are normalized (source explicit) in document order. Dates render
    as YYYY-MM-DD strings or None. Uses on-disk field name `deprecated_ids`.
    """
    return {
        "id": node.id,
        "uid": node.uid,
        "kind": node.kind,
        "title": node.title,
        "body": node.body,
        "metadata": {
            "created": node.metadata.created.isoformat() if node.metadata.created else None,
            "updated": node.metadata.updated.isoformat() if node.metadata.updated else None,
            "version": node.metadata.version,
        },
        "relations": [
            {
                "source": r.source,
                "predicate": r.predicate,
                "target": r.target,
                "directed": r.directed,
                "weight": r.weight,
                "attrs": r.attrs,
            }
            for r in node.relations
        ],
        "facets": node.facets,
        "deprecated_ids": node.deprecated_ids,
    }
```

- [ ] **Step 2: Write the failing parity test**

`python/tests/test_parity.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown

from tests._canonical import to_canonical

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
SOURCE = FIXTURES / "gene_phf19.md"
ORACLE = FIXTURES / "gene_phf19.canonical.json"
PY_EMIT = FIXTURES / "gene_phf19.py-emit.md"


def _node():
    return node_from_markdown(SOURCE.read_text(encoding="utf-8"))


def test_python_parse_matches_oracle():
    assert to_canonical(_node()) == json.loads(ORACLE.read_text(encoding="utf-8"))


def test_py_emit_fixture_is_current():
    # Regenerate-and-diff currency guard: the committed py-emit fixture must equal
    # what the CURRENT emitter produces. On drift this fails — regenerate the file.
    assert PY_EMIT.read_text(encoding="utf-8") == node_to_markdown(_node())


def test_py_emit_round_trips_to_oracle():
    assert to_canonical(node_from_markdown(PY_EMIT.read_text(encoding="utf-8"))) == json.loads(
        ORACLE.read_text(encoding="utf-8")
    )
```

- [ ] **Step 3: Run to verify it fails**

```bash
cd ~/d/nodes/python
rtk uv run pytest tests/test_parity.py -q
```

Expected: FAIL (oracle and py-emit fixtures do not exist yet).

- [ ] **Step 4: Generate the committed oracle + py-emit fixtures**

Run this one-off generator from `python/` (it writes the two fixtures from the *current* parser/emitter):

```bash
cd ~/d/nodes/python
rtk uv run python -c '
import json
from pathlib import Path
from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown
from tests._canonical import to_canonical
fx = Path("..") / "fixtures"
node = node_from_markdown((fx / "gene_phf19.md").read_text(encoding="utf-8"))
(fx / "gene_phf19.canonical.json").write_text(
    json.dumps(to_canonical(node), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
(fx / "gene_phf19.py-emit.md").write_text(node_to_markdown(node), encoding="utf-8")
'
```

Verify `fixtures/gene_phf19.canonical.json` reads (modulo whitespace):

```json
{
  "id": "gene:PHF19",
  "uid": "7b2cdeadbeef7b2cdeadbeef7b2cdeef",
  "kind": "gene",
  "title": "PHF19",
  "body": "PHF19 is a PRC2-associated component.\n",
  "metadata": { "created": null, "updated": null, "version": 1 },
  "relations": [
    { "source": "gene:PHF19", "predicate": "relatesTo", "target": "topic:polycomb", "directed": true, "weight": null, "attrs": {} },
    { "source": "gene:PHF19", "predicate": "interacts_with", "target": "gene:EZH2", "directed": true, "weight": null, "attrs": {} }
  ],
  "facets": { "bio-axes": { "primary_external_id": "HGNC:7296" } },
  "deprecated_ids": []
}
```

If `body` lacks the trailing `\n`, the source fixture is missing its final newline — add exactly one and regenerate.

- [ ] **Step 5: Run to verify it passes**

```bash
cd ~/d/nodes/python
rtk uv run pytest tests/test_parity.py -q
```

Expected: **3 passed**.

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add fixtures/ python/tests/_canonical.py python/tests/test_parity.py
rtk git commit -m "test(parity): canonical-JSON oracle + Python-emitted fixture with currency guard"
```

---

## Task 3: errors.ts + ids.ts

**Files:**
- Create: `ts/src/errors.ts`, `ts/src/ids.ts`
- Create: `ts/tests/errors.test.ts`, `ts/tests/ids.test.ts`

**Interfaces:**
- Produces: error classes `NodesError`, `IdError`, `RefError`, `CollisionError`, `UnknownKindError`, `FacetError`, `InvariantError`, `ValidationError`; `class NodeId { kind; slug; static parse(raw): NodeId; static isValidKind(k): boolean; static isValidSlug(s): boolean; toString(): string }`.

- [ ] **Step 1: Write failing tests**

`ts/tests/errors.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { IdError, NodesError, ValidationError } from "../src/errors.js";

describe("errors", () => {
  it("all kernel errors extend NodesError", () => {
    expect(new IdError("x")).toBeInstanceOf(NodesError);
    expect(new ValidationError("x")).toBeInstanceOf(Error);
  });
  it("sets name to the subclass name", () => {
    expect(new IdError("x").name).toBe("IdError");
  });
});
```

`ts/tests/ids.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { IdError } from "../src/errors.js";
import { NodeId } from "../src/ids.js";

describe("NodeId.parse", () => {
  it("parses kind:slug", () => {
    const id = NodeId.parse("topic:polycomb");
    expect(id.kind).toBe("topic");
    expect(id.slug).toBe("polycomb");
    expect(id.toString()).toBe("topic:polycomb");
  });
  it("keeps colons in the slug (split on first only)", () => {
    expect(NodeId.parse("gene:HGNC:7296").slug).toBe("HGNC:7296");
  });
  it("throws IdError without a colon", () => {
    expect(() => NodeId.parse("nope")).toThrow(IdError);
  });
  it("throws IdError on a bad kind", () => {
    expect(() => NodeId.parse("Topic:x")).toThrow(IdError);
  });
  it("throws IdError on a bad slug", () => {
    expect(() => NodeId.parse("topic:-bad")).toThrow(IdError);
  });
  it("validates kind and slug independently", () => {
    expect(NodeId.isValidKind("bio-axes")).toBe(true);
    expect(NodeId.isValidKind("Bad")).toBe(false);
    expect(NodeId.isValidSlug("A1:_.-")).toBe(true);
    expect(NodeId.isValidSlug("-bad")).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL (modules not found).

- [ ] **Step 3: Implement**

`ts/src/errors.ts`:

```typescript
export class NodesError extends Error {
  constructor(message?: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class IdError extends NodesError {}
export class RefError extends NodesError {}
export class CollisionError extends NodesError {}
export class UnknownKindError extends NodesError {}
export class FacetError extends NodesError {}
export class InvariantError extends NodesError {}
export class ValidationError extends NodesError {}
```

`ts/src/ids.ts`:

```typescript
import { IdError } from "./errors.js";

export type Ref = string;

const KIND_RE = /^[a-z][a-z0-9-]*$/;
const SLUG_RE = /^[A-Za-z0-9][A-Za-z0-9:_.-]*$/;

export class NodeId {
  constructor(
    readonly kind: string,
    readonly slug: string,
  ) {}

  static isValidKind(kind: string): boolean {
    return KIND_RE.test(kind);
  }

  static isValidSlug(slug: string): boolean {
    return SLUG_RE.test(slug);
  }

  static parse(raw: string): NodeId {
    const idx = raw.indexOf(":");
    if (idx === -1) {
      throw new IdError(`id must be 'kind:slug', got ${JSON.stringify(raw)}`);
    }
    const kind = raw.slice(0, idx);
    const slug = raw.slice(idx + 1);
    if (!NodeId.isValidKind(kind)) {
      throw new IdError(`invalid kind ${JSON.stringify(kind)} in id ${JSON.stringify(raw)}`);
    }
    if (!NodeId.isValidSlug(slug)) {
      throw new IdError(`invalid slug ${JSON.stringify(slug)} in id ${JSON.stringify(raw)}`);
    }
    return new NodeId(kind, slug);
  }

  toString(): string {
    return `${this.kind}:${this.slug}`;
  }
}
```

- [ ] **Step 4: Run to verify they pass**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all tests pass; typecheck + biome clean.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/errors.ts ts/src/ids.ts ts/tests/errors.test.ts ts/tests/ids.test.ts
rtk git commit -m "feat(ts): port errors hierarchy + NodeId"
```

---

## Task 4: relations.ts

**Files:**
- Create: `ts/src/relations.ts`
- Create: `ts/tests/relations.test.ts`

**Interfaces:**
- Consumes: `RefError` from `errors.ts`.
- Produces: `RELATES_TO = "relatesTo"`; `RelationSchema` (Zod); `type Relation = z.infer<typeof RelationSchema>` with fields `{ source, predicate, target, directed, weight, attrs }`; `fromSerialized(data, containerId): Relation`; `toSerialized(rel, containerId): Record<string, unknown>`; `relatesTo(source, target): Relation`; `tagToRelation(source, tag, aliasMap): Relation`.

- [ ] **Step 1: Write failing tests**

`ts/tests/relations.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { RefError } from "../src/errors.js";
import { RELATES_TO, fromSerialized, relatesTo, tagToRelation, toSerialized } from "../src/relations.js";

describe("relations", () => {
  it("relatesTo builds a normalized relatesTo edge", () => {
    expect(relatesTo("a:1", "b:2")).toEqual({
      source: "a:1",
      predicate: RELATES_TO,
      target: "b:2",
      directed: true,
      weight: null,
      attrs: {},
    });
  });

  it("fromSerialized fills source from the container when absent", () => {
    const r = fromSerialized({ predicate: "cites", target: "p:2" }, "p:1");
    expect(r.source).toBe("p:1");
    expect(r.directed).toBe(true);
  });

  it("fromSerialized keeps an explicit source", () => {
    expect(fromSerialized({ source: "x:9", predicate: "cites", target: "p:2" }, "p:1").source).toBe("x:9");
  });

  it("toSerialized omits source==container, directed=true, null weight, empty attrs", () => {
    expect(toSerialized(relatesTo("p:1", "p:2"), "p:1")).toEqual({ predicate: RELATES_TO, target: "p:2" });
  });

  it("toSerialized keeps non-default fields", () => {
    const r = fromSerialized(
      { source: "x:1", predicate: "cites", target: "p:2", directed: false, weight: 0.5, attrs: { k: 1 } },
      "p:1",
    );
    expect(toSerialized(r, "p:1")).toEqual({
      source: "x:1",
      predicate: "cites",
      target: "p:2",
      directed: false,
      weight: 0.5,
      attrs: { k: 1 },
    });
  });

  it("tagToRelation resolves #alias case-insensitively", () => {
    const r = tagToRelation("a:1", "#Polycomb", { polycomb: "topic:polycomb" });
    expect(r.target).toBe("topic:polycomb");
  });

  it("tagToRelation throws RefError on an unknown tag", () => {
    expect(() => tagToRelation("a:1", "#nope", {})).toThrow(RefError);
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

`ts/src/relations.ts`:

```typescript
import { z } from "zod";
import { RefError } from "./errors.js";

export const RELATES_TO = "relatesTo";

export const RelationSchema = z.object({
  source: z.string(),
  predicate: z.string(),
  target: z.string(),
  directed: z.boolean().default(true),
  weight: z.number().nullable().default(null),
  attrs: z.record(z.unknown()).default({}),
});

export type Relation = z.infer<typeof RelationSchema>;

// Low-level schema helpers. Like Python's `Relation(...)` / `Relation.from_serialized`, these may
// surface a raw ZodError on malformed input. The "never leak raw" contract lives in the boundary
// parsers (`makeNode`, `nodeFromMarkdown`, `membershipOf`), which catch and re-wrap as kernel errors.
export function fromSerialized(data: Record<string, unknown>, containerId: string): Relation {
  const { source, ...rest } = data;
  return RelationSchema.parse({ source: source !== undefined ? source : containerId, ...rest });
}

export function toSerialized(rel: Relation, containerId: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (rel.source !== containerId) out.source = rel.source;
  out.predicate = rel.predicate;
  out.target = rel.target;
  if (rel.directed !== true) out.directed = rel.directed;
  if (rel.weight !== null) out.weight = rel.weight;
  if (Object.keys(rel.attrs).length > 0) out.attrs = rel.attrs;
  return out;
}

export function relatesTo(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: RELATES_TO, target });
}

export function tagToRelation(source: string, tag: string, aliasMap: Record<string, string>): Relation {
  const name = tag.replace(/^#+/, "");
  const target = aliasMap[name] ?? aliasMap[name.toLowerCase()];
  if (target === undefined) {
    throw new RefError(`tag ${JSON.stringify(tag)} does not resolve to a known node`);
  }
  return relatesTo(source, target);
}
```

- [ ] **Step 4: Run to verify they pass**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/relations.ts ts/tests/relations.test.ts
rtk git commit -m "feat(ts): port Relation primitive + serialization sugar"
```

---

## Task 5: node.ts

**Files:**
- Create: `ts/src/node.ts`
- Create: `ts/tests/node.test.ts`

**Interfaces:**
- Consumes: `IdError`, `ValidationError` from `errors.ts`; `NodeId` from `ids.ts`; `RelationSchema` from `relations.ts`.
- Produces: `newUid(): string`; `NodeMetadataSchema`, `type NodeMetadata`; `NodeSchema`, `type Node = z.infer<typeof NodeSchema>`, `type NodeInput = z.input<typeof NodeSchema>`; `makeNode(input: NodeInput): Node`. `Node` fields: `{ id, uid, kind, title, body, metadata:{created,updated,version}, relations, facets, deprecatedIds }`.

- [ ] **Step 1: Write failing tests**

`ts/tests/node.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { ValidationError } from "../src/errors.js";
import { makeNode, newUid } from "../src/node.js";

describe("node", () => {
  it("newUid is 32 lowercase hex chars (uuid4().hex parity)", () => {
    expect(newUid()).toMatch(/^[0-9a-f]{32}$/);
  });

  it("applies Pydantic-parity defaults from minimal input", () => {
    const n = makeNode({ id: "topic:x", kind: "topic", title: "X" });
    expect(n.body).toBe("");
    expect(n.metadata).toEqual({ created: null, updated: null, version: 1 });
    expect(n.relations).toEqual([]);
    expect(n.facets).toEqual({});
    expect(n.deprecatedIds).toEqual([]);
    expect(n.uid).toMatch(/^[0-9a-f]{32}$/);
  });

  it("accepts YYYY-MM-DD metadata dates as strings", () => {
    const n = makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: "2026-06-21" } });
    expect(n.metadata.created).toBe("2026-06-21");
    expect(n.metadata.updated).toBeNull();
  });

  it("rejects a malformed id with ValidationError", () => {
    expect(() => makeNode({ id: "nope", kind: "topic", title: "X" })).toThrow(ValidationError);
  });

  it("rejects an id whose kind disagrees with the kind field", () => {
    expect(() => makeNode({ id: "topic:x", kind: "gene", title: "X" })).toThrow(ValidationError);
  });

  it("rejects a non-date metadata string with ValidationError", () => {
    expect(() => makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: "yesterday" } })).toThrow(
      ValidationError,
    );
  });

  it("rejects impossible calendar dates (bad month/day, non-leap Feb 29)", () => {
    for (const bad of ["2026-99-99", "2026-13-01", "2026-02-30", "2026-00-10", "2025-02-29"]) {
      expect(() => makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: bad } })).toThrow(
        ValidationError,
      );
    }
  });

  it("accepts a valid leap day", () => {
    expect(
      makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: "2024-02-29" } }).metadata.created,
    ).toBe("2024-02-29");
  });

  it("accepts low years 0001-0099 (Python date MINYEAR parity, not JS Date 1900 offset)", () => {
    for (const ok of ["0001-01-01", "0099-12-31", "0004-02-29"]) {
      expect(
        makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: ok } }).metadata.created,
      ).toBe(ok);
    }
    expect(() => makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: "0000-01-01" } })).toThrow(
      ValidationError,
    );
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL.

- [ ] **Step 3: Implement**

`ts/src/node.ts`:

```typescript
import { randomUUID } from "node:crypto";
import { z } from "zod";
import { IdError, ValidationError } from "./errors.js";
import { NodeId } from "./ids.js";
import { RelationSchema } from "./relations.js";

export function newUid(): string {
  return randomUUID().replace(/-/g, "");
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const dateStr = z
  .string()
  .regex(DATE_RE, "expected a YYYY-MM-DD date string")
  .refine((s) => {
    // Real-calendar validity via explicit arithmetic — full parity with Python's `date`
    // (MINYEAR=1, rejects 2026-99-99 / 2026-02-30 / non-leap 02-29, accepts 0001-0099).
    // Deliberately avoids JS `Date`, which maps years 0-99 onto 1900-1999.
    const [y, m, d] = s.split("-").map(Number);
    if (y < 1 || m < 1 || m > 12 || d < 1) return false;
    const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
    const maxDay = m === 2 && leap ? 29 : DAYS_IN_MONTH[m - 1];
    return d <= maxDay;
  }, "not a valid calendar date");

export const NodeMetadataSchema = z.object({
  created: dateStr.nullable().default(null),
  updated: dateStr.nullable().default(null),
  version: z.number().int().default(1),
});

export type NodeMetadata = z.infer<typeof NodeMetadataSchema>;

export const NodeSchema = z.object({
  id: z.string(),
  uid: z.string().default(() => newUid()),
  kind: z.string(),
  title: z.string(),
  body: z.string().default(""),
  metadata: z.preprocess((v) => v ?? {}, NodeMetadataSchema),
  relations: z.array(RelationSchema).default([]),
  facets: z.record(z.record(z.unknown())).default({}),
  deprecatedIds: z.array(z.string()).default([]),
});

export type Node = z.infer<typeof NodeSchema>;
export type NodeInput = z.input<typeof NodeSchema>;

export function makeNode(input: NodeInput): Node {
  let node: Node;
  try {
    node = NodeSchema.parse(input);
  } catch (e) {
    if (e instanceof z.ZodError) {
      throw new ValidationError(e.issues.map((i) => i.message).join("; "));
    }
    throw e;
  }
  let parsed: NodeId;
  try {
    parsed = NodeId.parse(node.id);
  } catch (e) {
    if (e instanceof IdError) throw new ValidationError(e.message);
    throw e;
  }
  if (parsed.kind !== node.kind) {
    throw new ValidationError(`id kind ${JSON.stringify(parsed.kind)} != kind field ${JSON.stringify(node.kind)}`);
  }
  return node;
}
```

- [ ] **Step 4: Run to verify they pass**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/node.ts ts/tests/node.test.ts
rtk git commit -m "feat(ts): port Node + NodeMetadata with Pydantic-parity defaults"
```

---

## Task 6: frontmatter.ts + TS parity (oracle + idempotency + ts-emit currency)

**Files:**
- Create: `ts/src/frontmatter.ts`
- Create: `ts/tests/_canonical.ts`
- Create: `ts/tests/frontmatter.test.ts`
- Create: `ts/tests/parity.test.ts`
- Create: `fixtures/gene_phf19.ts-emit.md`

**Interfaces:**
- Consumes: `ValidationError`; `makeNode`, `type Node`; `RELATES_TO`, `fromSerialized`, `relatesTo`, `toSerialized`, `type Relation`.
- Produces: `splitFrontmatter(text): [Record<string, unknown>, string]`; `nodeFromMarkdown(text): Node`; `nodeToMarkdown(node): string`. Test helper `toCanonical(node): unknown`.

- [ ] **Step 1: Write the canonical test helper**

`ts/tests/_canonical.ts`:

```typescript
import type { Node } from "../src/node.js";

// Language-neutral canonical JSON of a node (spec §5.1). Mirrors python/tests/_canonical.py.
export function toCanonical(node: Node): unknown {
  return {
    id: node.id,
    uid: node.uid,
    kind: node.kind,
    title: node.title,
    body: node.body,
    metadata: {
      created: node.metadata.created,
      updated: node.metadata.updated,
      version: node.metadata.version,
    },
    relations: node.relations.map((r) => ({
      source: r.source,
      predicate: r.predicate,
      target: r.target,
      directed: r.directed,
      weight: r.weight,
      attrs: r.attrs,
    })),
    facets: node.facets,
    deprecated_ids: node.deprecatedIds,
  };
}
```

- [ ] **Step 2: Write failing tests**

`ts/tests/frontmatter.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { ValidationError } from "../src/errors.js";
import { nodeFromMarkdown, nodeToMarkdown, splitFrontmatter } from "../src/frontmatter.js";
import { makeNode } from "../src/node.js";

const DOC = "---\nid: topic:x\nuid: abc\nkind: topic\ntitle: X\n---\nhello body\n";

describe("frontmatter", () => {
  it("splits the frontmatter block from the body", () => {
    const [fm, body] = splitFrontmatter(DOC);
    expect(fm.id).toBe("topic:x");
    expect(body).toBe("hello body\n");
  });

  it("returns empty frontmatter when no block is present", () => {
    expect(splitFrontmatter("no frontmatter here")).toEqual([{}, "no frontmatter here"]);
  });

  it("throws ValidationError on malformed YAML in the block", () => {
    expect(() => splitFrontmatter("---\nid: : :\n  bad\n---\nb\n")).toThrow(ValidationError);
  });

  it("throws ValidationError when a required field is missing", () => {
    expect(() => nodeFromMarkdown("---\nid: topic:x\nkind: topic\ntitle: X\n---\nb\n")).toThrow(ValidationError);
  });

  it("expands related: sugar and typed relations: in document order", () => {
    const n = nodeFromMarkdown(
      "---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelated:\n- b:2\nrelations:\n- predicate: cites\n  target: c:3\n---\nx\n",
    );
    expect(n.relations.map((r) => [r.predicate, r.target])).toEqual([
      ["relatesTo", "b:2"],
      ["cites", "c:3"],
    ]);
  });

  it("round-trips date metadata semantically", () => {
    const n = makeNode({ id: "a:1", kind: "a", title: "A", metadata: { created: "2026-06-21", updated: null, version: 3 } });
    const back = nodeFromMarkdown(nodeToMarkdown(n));
    expect(back.metadata).toEqual({ created: "2026-06-21", updated: null, version: 3 });
  });

  it("wraps a malformed typed relation as ValidationError (no raw ZodError)", () => {
    // relations: entry missing the required target
    expect(() =>
      nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelations:\n- predicate: cites\n---\nx\n"),
    ).toThrow(ValidationError);
  });

  it("wraps a non-string related entry as ValidationError", () => {
    expect(() => nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelated:\n- 123\n---\nx\n")).toThrow(
      ValidationError,
    );
  });

  it("rejects a non-list 'related' (scalar or mapping) as ValidationError, never a raw TypeError", () => {
    // scalar
    expect(() => nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelated: 123\n---\nx\n")).toThrow(
      ValidationError,
    );
    // mapping
    expect(() => nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelated:\n  b: c\n---\nx\n")).toThrow(
      ValidationError,
    );
  });

  it("rejects a non-list 'relations' (scalar or mapping) as ValidationError, never a raw TypeError", () => {
    // scalar
    expect(() => nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelations: 7\n---\nx\n")).toThrow(
      ValidationError,
    );
    // a single mapping where a list was expected
    expect(() =>
      nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelations:\n  predicate: cites\n  target: c:3\n---\nx\n"),
    ).toThrow(ValidationError);
  });
});
```

`ts/tests/parity.test.ts`:

```typescript
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { nodeFromMarkdown, nodeToMarkdown } from "../src/frontmatter.js";
import { toCanonical } from "./_canonical.js";

// new URL(..., import.meta.url) resolves on all supported Node (no import.meta.dirname dependency).
const FIXTURES = fileURLToPath(new URL("../../fixtures/", import.meta.url));
const SOURCE = join(FIXTURES, "gene_phf19.md");
const ORACLE = join(FIXTURES, "gene_phf19.canonical.json");
const TS_EMIT = join(FIXTURES, "gene_phf19.ts-emit.md");

const oracle = () => JSON.parse(readFileSync(ORACLE, "utf-8"));
const sourceNode = () => nodeFromMarkdown(readFileSync(SOURCE, "utf-8"));

describe("cross-language parity (TS side)", () => {
  it("TS parse of the shared fixture matches the oracle (check 2)", () => {
    expect(toCanonical(sourceNode())).toEqual(oracle());
  });

  it("TS serialize is semantically idempotent (check 5)", () => {
    const once = nodeToMarkdown(sourceNode());
    const twice = nodeToMarkdown(nodeFromMarkdown(once));
    expect(toCanonical(nodeFromMarkdown(twice))).toEqual(oracle());
  });

  it("the committed ts-emit fixture is current (regenerate-and-diff guard)", () => {
    expect(readFileSync(TS_EMIT, "utf-8")).toBe(nodeToMarkdown(sourceNode()));
  });
});
```

- [ ] **Step 3: Run to verify they fail**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL (module + ts-emit fixture missing).

- [ ] **Step 4: Implement**

`ts/src/frontmatter.ts`:

```typescript
import { parseDocument, stringify } from "yaml";
import { z } from "zod";
import { ValidationError } from "./errors.js";
import { type Node, makeNode } from "./node.js";
import { RELATES_TO, fromSerialized, relatesTo, type Relation, toSerialized } from "./relations.js";

export function splitFrontmatter(text: string): [Record<string, unknown>, string] {
  let nl: string;
  if (text.startsWith("---\r\n")) nl = "\r\n";
  else if (text.startsWith("---\n")) nl = "\n";
  else return [{}, text];

  const rest = text.slice(3 + nl.length);
  const sep = `${nl}---${nl}`;
  const idx = rest.indexOf(sep);
  if (idx === -1) return [{}, text];

  const doc = parseDocument(rest.slice(0, idx));
  if (doc.errors.length > 0) {
    throw new ValidationError(`invalid frontmatter YAML: ${doc.errors[0].message}`);
  }
  const fm = (doc.toJS() ?? {}) as Record<string, unknown>;
  return [fm, rest.slice(idx + sep.length)];
}

export function nodeFromMarkdown(text: string): Node {
  const [fm, body] = splitFrontmatter(text);
  const missing = (["id", "uid", "kind", "title"] as const).filter((k) => !(k in fm));
  if (missing.length > 0) {
    throw new ValidationError(`frontmatter missing required field(s): ${JSON.stringify(missing)}`);
  }
  const nodeId = fm.id as string;

  // `nodeFromMarkdown` is a boundary parser: every malformed-input path leaves as a typed
  // kernel error (spec §7), never a raw ZodError or a raw TypeError. Collection fields must be
  // lists — a scalar or mapping is a ValidationError, not a "not iterable" TypeError. (Python's
  // node_from_markdown leaks a raw TypeError here; the TS boundary deliberately tightens that.)
  if (fm.related !== undefined && !Array.isArray(fm.related)) {
    throw new ValidationError(`'related' must be a list in ${JSON.stringify(nodeId)}`);
  }
  if (fm.relations !== undefined && !Array.isArray(fm.relations)) {
    throw new ValidationError(`'relations' must be a list in ${JSON.stringify(nodeId)}`);
  }
  const relations: Relation[] = [];
  try {
    for (const ref of (fm.related as unknown[] | undefined) ?? []) {
      relations.push(relatesTo(nodeId, ref as string));
    }
    for (const raw of (fm.relations as Record<string, unknown>[] | undefined) ?? []) {
      relations.push(fromSerialized(raw, nodeId));
    }
  } catch (e) {
    if (e instanceof z.ZodError) {
      throw new ValidationError(`invalid relation in ${JSON.stringify(nodeId)}: ${e.issues.map((i) => i.message).join("; ")}`);
    }
    throw e;
  }

  const metadata: Record<string, unknown> = {};
  for (const k of ["created", "updated", "version"] as const) {
    if (k in fm) metadata[k] = fm[k];
  }

  return makeNode({
    id: nodeId,
    uid: fm.uid as string,
    kind: fm.kind as string,
    title: fm.title as string,
    body,
    metadata,
    relations,
    facets: (fm.facets as Record<string, Record<string, unknown>>) ?? {},
    deprecatedIds: (fm.deprecated_ids as string[]) ?? [],
  });
}

function isPlainRelatesTo(rel: Relation, nodeId: string): boolean {
  return (
    rel.predicate === RELATES_TO &&
    rel.source === nodeId &&
    rel.directed === true &&
    rel.weight === null &&
    Object.keys(rel.attrs).length === 0
  );
}

export function nodeToMarkdown(node: Node): string {
  const fm: Record<string, unknown> = { id: node.id, uid: node.uid, kind: node.kind, title: node.title };
  if (node.metadata.created !== null) fm.created = node.metadata.created;
  if (node.metadata.updated !== null) fm.updated = node.metadata.updated;
  if (node.metadata.version !== 1) fm.version = node.metadata.version;

  const related = node.relations.filter((r) => isPlainRelatesTo(r, node.id)).map((r) => r.target);
  const typed = node.relations.filter((r) => !isPlainRelatesTo(r, node.id)).map((r) => toSerialized(r, node.id));
  if (related.length > 0) fm.related = related;
  if (typed.length > 0) fm.relations = typed;
  if (Object.keys(node.facets).length > 0) fm.facets = node.facets;
  if (node.deprecatedIds.length > 0) fm.deprecated_ids = node.deprecatedIds;

  const yamlText = stringify(fm, { sortMapEntries: false }).trimEnd();
  return `---\n${yamlText}\n---\n${node.body}`;
}
```

- [ ] **Step 5: Generate the committed ts-emit fixture**

```bash
cd ~/d/nodes/ts
rtk node --experimental-strip-types -e '
import { readFileSync, writeFileSync } from "node:fs";
import { nodeFromMarkdown, nodeToMarkdown } from "./src/frontmatter.ts";
const fx = "../fixtures/";
const node = nodeFromMarkdown(readFileSync(fx + "gene_phf19.md", "utf-8"));
writeFileSync(fx + "gene_phf19.ts-emit.md", nodeToMarkdown(node));
'
```

(If `--experimental-strip-types` is unavailable on the local Node, write the same three lines to a temp `.ts` and run via `rtk npx vitest run` in a throwaway test, or `rtk npx tsx gen.ts`. The committed fixture must equal current `nodeToMarkdown` output — Step 6's currency test enforces this.)

- [ ] **Step 6: Run to verify they pass**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green (parse parity, idempotency, currency).

- [ ] **Step 7: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/frontmatter.ts ts/tests/_canonical.ts ts/tests/frontmatter.test.ts ts/tests/parity.test.ts fixtures/gene_phf19.ts-emit.md
rtk git commit -m "feat(ts): port frontmatter parse/serialize + TS parity oracle & currency guard"
```

---

## Task 7: registry.ts

**Files:**
- Create: `ts/src/registry.ts`
- Create: `ts/tests/registry.test.ts`

**Interfaces:**
- Consumes: `FacetError`, `UnknownKindError`; `type Node`.
- Produces: `type Invariant = (node: Node) => void`; `interface KindSpec { name; requiredFacets?: Set<string>; optionalFacets?: Set<string>; invariants?: Invariant[] }`; `class Registry { register(spec); isRegistered(kind): boolean; get(kind): KindSpec; validate(node): void }`.

- [ ] **Step 1: Write failing tests**

`ts/tests/registry.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { FacetError, InvariantError, UnknownKindError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";

function node(facets: Record<string, Record<string, unknown>>) {
  return makeNode({ id: "k:1", kind: "k", title: "T", facets });
}

describe("Registry", () => {
  it("get() throws UnknownKindError for an unregistered kind", () => {
    expect(() => new Registry().get("nope")).toThrow(UnknownKindError);
    expect(new Registry().isRegistered("nope")).toBe(false);
  });

  it("validate() accepts required + optional facets", () => {
    const reg = new Registry();
    reg.register({ name: "k", requiredFacets: new Set(["a"]), optionalFacets: new Set(["b"]) });
    expect(() => reg.validate(node({ a: {}, b: {} }))).not.toThrow();
  });

  it("validate() rejects a missing required facet", () => {
    const reg = new Registry();
    reg.register({ name: "k", requiredFacets: new Set(["a"]) });
    expect(() => reg.validate(node({}))).toThrow(FacetError);
  });

  it("validate() rejects an unexpected facet", () => {
    const reg = new Registry();
    reg.register({ name: "k" });
    expect(() => reg.validate(node({ x: {} }))).toThrow(FacetError);
  });

  it("validate() runs invariants", () => {
    const reg = new Registry();
    reg.register({
      name: "k",
      invariants: [
        () => {
          throw new InvariantError("boom");
        },
      ],
    });
    expect(() => reg.validate(node({}))).toThrow(InvariantError);
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL.

- [ ] **Step 3: Implement**

`ts/src/registry.ts`:

```typescript
import { FacetError, UnknownKindError } from "./errors.js";
import type { Node } from "./node.js";

export type Invariant = (node: Node) => void;

export interface KindSpec {
  name: string;
  requiredFacets?: Set<string>;
  optionalFacets?: Set<string>;
  invariants?: Invariant[];
}

export class Registry {
  private specs = new Map<string, KindSpec>();

  register(spec: KindSpec): void {
    this.specs.set(spec.name, spec);
  }

  isRegistered(kind: string): boolean {
    return this.specs.has(kind);
  }

  get(kind: string): KindSpec {
    const spec = this.specs.get(kind);
    if (spec === undefined) {
      throw new UnknownKindError(`kind ${JSON.stringify(kind)} is not registered`);
    }
    return spec;
  }

  validate(node: Node): void {
    const spec = this.get(node.kind);
    const required = spec.requiredFacets ?? new Set<string>();
    const optional = spec.optionalFacets ?? new Set<string>();
    const present = new Set(Object.keys(node.facets));

    const missing = [...required].filter((f) => !present.has(f)).sort();
    if (missing.length > 0) {
      throw new FacetError(`${node.id}: missing required facets ${JSON.stringify(missing)}`);
    }
    const allowed = new Set([...required, ...optional]);
    const unexpected = [...present].filter((f) => !allowed.has(f)).sort();
    if (unexpected.length > 0) {
      throw new FacetError(`${node.id}: unexpected facets ${JSON.stringify(unexpected)}`);
    }
    for (const invariant of spec.invariants ?? []) {
      invariant(node);
    }
  }
}
```

- [ ] **Step 4: Run to verify they pass**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/registry.ts ts/tests/registry.test.ts
rtk git commit -m "feat(ts): port KindSpec + Registry validation"
```

---

## Task 8: shapes.ts

Current-code note: this task's one-facet `Membership` shape is historical. Current TS shapes mirror the redesigned Python structural-shapes model: scope membership lives in `facets.membership`, while shape-owned form data lives in `facets.edges`, `facets.order`, and `facets.keys`.

**Files:**
- Create: `ts/src/shapes.ts`
- Create: `ts/tests/shapes.test.ts`

**Interfaces:**
- Consumes: `FacetError`, `InvariantError`; `type Node`; `KindSpec`, `Registry`; `RelationSchema`, `type Relation`.
- Produces: `MEMBERSHIP = "membership"`; `MembershipSchema`, `type Membership = { shape; members: string[] | Record<string,string>; edges: Relation[] }`; `membershipOf(node): Membership`; `requireUniqueMembers`, `requireDictKeys`, `requireAcyclic`, `requireSingleParent` (each `(node) => void`); `registerBuiltinShapes(reg: Registry): void`.

- [ ] **Step 1: Write failing tests**

`ts/tests/shapes.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { FacetError, InvariantError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import {
  MEMBERSHIP,
  membershipOf,
  registerBuiltinShapes,
  requireAcyclic,
  requireDictKeys,
  requireSingleParent,
  requireUniqueMembers,
} from "../src/shapes.js";

function shaped(kind: string, membership: Record<string, unknown>) {
  return makeNode({ id: `${kind}:1`, kind, title: "S", facets: { [MEMBERSHIP]: membership } });
}

describe("shapes", () => {
  it("membershipOf throws FacetError when the facet is absent", () => {
    expect(() => membershipOf(makeNode({ id: "set:1", kind: "set", title: "S" }))).toThrow(FacetError);
  });

  it("membershipOf defaults members and edges to empty", () => {
    const m = membershipOf(shaped("set", { shape: "set" }));
    expect(m.members).toEqual([]);
    expect(m.edges).toEqual([]);
  });

  it("requireUniqueMembers rejects duplicates", () => {
    expect(() => requireUniqueMembers(shaped("set", { shape: "set", members: ["a:1", "a:1"] }))).toThrow(InvariantError);
  });

  it("requireDictKeys requires a mapping", () => {
    expect(() => requireDictKeys(shaped("dict", { shape: "dict", members: ["a:1"] }))).toThrow(InvariantError);
    expect(() => requireDictKeys(shaped("dict", { shape: "dict", members: { k: "a:1" } }))).not.toThrow();
  });

  it("requireAcyclic detects a cycle", () => {
    const m = {
      shape: "graph",
      members: ["a:1", "a:2"],
      edges: [
        { source: "a:1", predicate: "e", target: "a:2" },
        { source: "a:2", predicate: "e", target: "a:1" },
      ],
    };
    expect(() => requireAcyclic(shaped("dag", m))).toThrow(InvariantError);
  });

  it("requireSingleParent rejects two parents of one target", () => {
    const m = {
      shape: "tree",
      members: ["a:1", "a:2", "a:3"],
      edges: [
        { source: "a:1", predicate: "e", target: "a:3" },
        { source: "a:2", predicate: "e", target: "a:3" },
      ],
    };
    expect(() => requireSingleParent(shaped("tree", m))).toThrow(InvariantError);
  });

  it("registerBuiltinShapes wires all six shapes; a valid tree passes", () => {
    const reg = new Registry();
    registerBuiltinShapes(reg);
    for (const k of ["set", "list", "dict", "graph", "dag", "tree"]) expect(reg.isRegistered(k)).toBe(true);
    const tree = shaped("tree", {
      shape: "tree",
      members: ["a:1", "a:2"],
      edges: [{ source: "a:1", predicate: "child", target: "a:2" }],
    });
    expect(() => reg.validate(tree)).not.toThrow();
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL.

- [ ] **Step 3: Implement**

`ts/src/shapes.ts`:

```typescript
import { z } from "zod";
import { FacetError, InvariantError } from "./errors.js";
import type { Node } from "./node.js";
import { type KindSpec, Registry } from "./registry.js";
import { RelationSchema } from "./relations.js";

export const MEMBERSHIP = "membership";

export const MembershipSchema = z.object({
  shape: z.string(),
  members: z.union([z.array(z.string()), z.record(z.string())]).default([]),
  edges: z.array(RelationSchema).default([]),
});

export type Membership = z.infer<typeof MembershipSchema>;

export function membershipOf(node: Node): Membership {
  const raw = node.facets[MEMBERSHIP];
  if (raw === undefined) {
    throw new FacetError(`${node.id}: missing '${MEMBERSHIP}' facet`);
  }
  try {
    return MembershipSchema.parse(raw);
  } catch (e) {
    if (e instanceof z.ZodError) {
      throw new FacetError(`${node.id}: invalid '${MEMBERSHIP}' facet: ${e.issues.map((i) => i.message).join("; ")}`);
    }
    throw e;
  }
}

function memberIds(m: Membership): string[] {
  return Array.isArray(m.members) ? [...m.members] : Object.values(m.members);
}

export function requireUniqueMembers(node: Node): void {
  const ids = memberIds(membershipOf(node));
  if (ids.length !== new Set(ids).size) {
    throw new InvariantError(`${node.id}: members must be unique`);
  }
}

export function requireDictKeys(node: Node): void {
  if (Array.isArray(membershipOf(node).members)) {
    throw new InvariantError(`${node.id}: dict shape requires a key->ref mapping`);
  }
}

export function requireAcyclic(node: Node): void {
  const m = membershipOf(node);
  const adj = new Map<string, string[]>();
  for (const e of m.edges) {
    const list = adj.get(e.source) ?? [];
    list.push(e.target);
    adj.set(e.source, list);
  }
  const visiting = new Set<string>();
  const done = new Set<string>();
  const walk = (n: string): void => {
    if (visiting.has(n)) throw new InvariantError(`${node.id}: cycle detected at ${n}`);
    if (done.has(n)) return;
    visiting.add(n);
    for (const nxt of adj.get(n) ?? []) walk(nxt);
    visiting.delete(n);
    done.add(n);
  };
  for (const start of [...adj.keys()]) walk(start);
}

export function requireSingleParent(node: Node): void {
  const parents = new Map<string, number>();
  for (const e of membershipOf(node).edges) {
    parents.set(e.target, (parents.get(e.target) ?? 0) + 1);
  }
  const over = [...parents.entries()].filter(([, c]) => c > 1).map(([t]) => t).sort();
  if (over.length > 0) {
    throw new InvariantError(`${node.id}: nodes with multiple parents: ${JSON.stringify(over)}`);
  }
}

export function registerBuiltinShapes(reg: Registry): void {
  const m = () => new Set([MEMBERSHIP]);
  const specs: KindSpec[] = [
    { name: "set", requiredFacets: m(), invariants: [requireUniqueMembers] },
    { name: "list", requiredFacets: m() },
    { name: "dict", requiredFacets: m(), invariants: [requireDictKeys] },
    { name: "graph", requiredFacets: m(), invariants: [requireUniqueMembers] },
    { name: "dag", requiredFacets: m(), invariants: [requireUniqueMembers, requireAcyclic] },
    { name: "tree", requiredFacets: m(), invariants: [requireUniqueMembers, requireAcyclic, requireSingleParent] },
  ];
  for (const spec of specs) reg.register(spec);
}
```

- [ ] **Step 4: Run to verify they pass**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/shapes.ts ts/tests/shapes.test.ts
rtk git commit -m "feat(ts): port structural shapes (membership facet + invariants)"
```

---

## Task 9: store.ts (historical Plan-1 CRUD surface)

Current-code note: this task's full-CRUD `Store` was intentionally superseded by later structural-index work. Current `Store` is file mechanics only; `Corpus` owns resolution, collision checks, rename, search/vector updates, and manifest maintenance.

**Files:**
- Create: `ts/src/store.ts`
- Create: `ts/tests/store.test.ts`

**Interfaces:**
- Consumes: `CollisionError`, `RefError`; `nodeFromMarkdown`, `nodeToMarkdown`; `NodeId`; `type Node`; `MEMBERSHIP`.
- Produces: `class Store { constructor(root: string); pathFor(id): string; allNodes(): Node[]; write(node): string; resolve(ref): Node; read(id): Node; delete(id): void; rename(oldId, newId): Node }`.

- [ ] **Step 1: Write failing tests**

`ts/tests/store.test.ts`:

```typescript
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CollisionError, RefError } from "../src/errors.js";
import { makeNode, type Node } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { Store } from "../src/store.js";

let root: string;
let store: Store;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-store-"));
  store = new Store(root);
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function n(id: string, kind: string, extra: Partial<Node> = {}): Node {
  return makeNode({ id, kind, title: id, ...extra });
}

describe("Store CRUD", () => {
  it("writes then reads a node back", () => {
    const a = n("topic:a", "topic");
    store.write(a);
    expect(store.read("topic:a").id).toBe("topic:a");
  });

  it("resolve() throws RefError for an unknown ref", () => {
    expect(() => store.resolve("topic:missing")).toThrow(RefError);
  });

  it("write() rejects a second node reusing a live uid under a different id", () => {
    const a = n("topic:a", "topic");
    store.write(a);
    const clash = makeNode({ id: "topic:b", kind: "topic", title: "b", uid: a.uid });
    expect(() => store.write(clash)).toThrow(CollisionError);
  });

  it("delete() removes a node and errors when absent", () => {
    store.write(n("topic:a", "topic"));
    store.delete("topic:a");
    expect(() => store.delete("topic:a")).toThrow(RefError);
  });

  it("rename() rewrites the node, records a deprecated id, and rewrites inbound refs", () => {
    store.write(n("topic:old", "topic"));
    store.write(n("note:r", "note", { relations: [relatesTo("note:r", "topic:old")] }));

    const renamed = store.rename("topic:old", "topic:new");
    expect(renamed.id).toBe("topic:new");
    expect(renamed.deprecatedIds).toContain("topic:old");

    // old ref still resolves through the deprecated alias
    expect(store.resolve("topic:old").id).toBe("topic:new");
    // inbound reference was rewritten
    expect(store.read("note:r").relations[0].target).toBe("topic:new");
  });

  it("rename() rejects a target id already in use", () => {
    store.write(n("topic:a", "topic"));
    store.write(n("topic:b", "topic"));
    expect(() => store.rename("topic:a", "topic:b")).toThrow(CollisionError);
  });

  it("rename() rewrites membership members and edges", () => {
    store.write(n("topic:old", "topic"));
    store.write(
      makeNode({
        id: "graph:g",
        kind: "graph",
        title: "g",
        facets: {
          membership: {
            shape: "graph",
            members: ["topic:old"],
            edges: [{ source: "topic:old", predicate: "e", target: "topic:old" }],
          },
        },
      }),
    );
    store.rename("topic:old", "topic:new");
    const g = store.read("graph:g");
    expect(g.facets.membership.members).toEqual(["topic:new"]);
    expect((g.facets.membership.edges as Array<Record<string, unknown>>)[0]).toMatchObject({
      source: "topic:new",
      target: "topic:new",
    });
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd ~/d/nodes/ts
rtk npm test
```

Expected: FAIL.

- [ ] **Step 3: Implement**

`ts/src/store.ts`:

```typescript
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { CollisionError, RefError } from "./errors.js";
import { nodeFromMarkdown, nodeToMarkdown } from "./frontmatter.js";
import { NodeId } from "./ids.js";
import type { Node } from "./node.js";
import { MEMBERSHIP } from "./shapes.js";

export class Store {
  readonly root: string;

  constructor(root: string) {
    this.root = root;
  }

  pathFor(nodeId: string): string {
    const nid = NodeId.parse(nodeId);
    return join(this.root, nid.kind, `${nid.slug.replace(/:/g, "__")}.md`);
  }

  private markdownPaths(): string[] {
    const out: string[] = [];
    const walk = (dir: string): void => {
      if (!existsSync(dir)) return;
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (entry.isFile() && entry.name.endsWith(".md")) out.push(full);
      }
    };
    walk(this.root);
    return out;
  }

  allNodes(): Node[] {
    return this.markdownPaths()
      .sort()
      .map((p) => nodeFromMarkdown(readFileSync(p, "utf-8")));
  }

  private claimedIds(node: Node): Set<string> {
    return new Set([node.id, ...node.deprecatedIds]);
  }

  private assertNoIdentityCollision(node: Node): void {
    const claimed = this.claimedIds(node);
    for (const existing of this.allNodes()) {
      const sameLiveIdentity = existing.id === node.id && existing.uid === node.uid;
      if (existing.uid === node.uid && existing.id !== node.id) {
        throw new CollisionError(
          `uid ${JSON.stringify(node.uid)} already belongs to live id ${JSON.stringify(existing.id)}; use rename()`,
        );
      }
      if (sameLiveIdentity) continue;
      const existingClaims = this.claimedIds(existing);
      const overlap = [...claimed].filter((c) => existingClaims.has(c)).sort();
      if (overlap.length > 0) {
        throw new CollisionError(`identity claims already in use: ${JSON.stringify(overlap)}`);
      }
    }
  }

  private writeFileRaw(node: Node): string {
    const path = this.pathFor(node.id);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, nodeToMarkdown(node), "utf-8");
    return path;
  }

  write(node: Node): string {
    this.assertNoIdentityCollision(node);
    return this.writeFileRaw(node);
  }

  resolve(ref: string): Node {
    const path = this.pathFor(ref);
    if (existsSync(path) && statSync(path).isFile()) {
      return nodeFromMarkdown(readFileSync(path, "utf-8"));
    }
    for (const n of this.allNodes()) {
      if (n.deprecatedIds.includes(ref)) return n;
    }
    throw new RefError(`no node resolves ref ${JSON.stringify(ref)}`);
  }

  read(nodeId: string): Node {
    return this.resolve(nodeId);
  }

  delete(nodeId: string): void {
    const path = this.pathFor(nodeId);
    if (!(existsSync(path) && statSync(path).isFile())) {
      throw new RefError(`no node at ${JSON.stringify(nodeId)}`);
    }
    rmSync(path);
  }

  private idOwnerUid(nodeId: string): string | null {
    for (const n of this.allNodes()) {
      if (n.id === nodeId || n.deprecatedIds.includes(nodeId)) return n.uid;
    }
    return null;
  }

  rename(oldId: string, newId: string): Node {
    if (this.idOwnerUid(newId) !== null) {
      throw new CollisionError(`target id ${JSON.stringify(newId)} already in use`);
    }
    const node = this.read(oldId);
    const oldPath = this.pathFor(oldId);
    node.id = newId;
    node.kind = NodeId.parse(newId).kind;
    if (!node.deprecatedIds.includes(oldId)) node.deprecatedIds.push(oldId);

    const newPath = this.writeFileRaw(node); // write new FIRST — no data-loss window
    if (oldPath !== newPath && existsSync(oldPath) && statSync(oldPath).isFile()) {
      rmSync(oldPath); // then remove old
    }
    this.rewriteInbound(oldId, newId);
    return node;
  }

  private rewriteInbound(oldId: string, newId: string): void {
    for (const other of this.allNodes()) {
      if (other.id === newId) continue;
      let changed = this.rewriteRelations(other, oldId, newId);
      changed = this.rewriteMembership(other, oldId, newId) || changed;
      if (changed) this.write(other);
    }
  }

  private rewriteRelations(node: Node, oldId: string, newId: string): boolean {
    let changed = false;
    for (const rel of node.relations) {
      if (rel.target === oldId) {
        rel.target = newId;
        changed = true;
      }
      if (rel.source === oldId) {
        rel.source = newId;
        changed = true;
      }
    }
    return changed;
  }

  private rewriteMembership(node: Node, oldId: string, newId: string): boolean {
    const mem = node.facets[MEMBERSHIP];
    if (mem === undefined || mem === null || typeof mem !== "object") return false;
    const m = mem as Record<string, unknown>;
    let changed = false;

    const members = m.members;
    if (Array.isArray(members)) {
      let mchanged = false;
      const updated = members.map((x) => {
        if (x === oldId) {
          mchanged = true;
          return newId;
        }
        return x;
      });
      if (mchanged) {
        m.members = updated;
        changed = true;
      }
    } else if (members !== null && typeof members === "object") {
      const obj = members as Record<string, unknown>;
      for (const key of Object.keys(obj)) {
        if (obj[key] === oldId) {
          obj[key] = newId;
          changed = true;
        }
      }
    }

    const edges = m.edges;
    if (Array.isArray(edges)) {
      for (const edge of edges) {
        if (edge !== null && typeof edge === "object") {
          const e = edge as Record<string, unknown>;
          if (e.source === oldId) {
            e.source = newId;
            changed = true;
          }
          if (e.target === oldId) {
            e.target = newId;
            changed = true;
          }
        }
      }
    }
    return changed;
  }
}
```

- [ ] **Step 4: Run to verify they pass**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/store.ts ts/tests/store.test.ts
rtk git commit -m "feat(ts): port historical Plan-1 Store CRUD surface"
```

---

## Task 10: Barrel exports + cross-language parity + docs

Current-code note: the barrel and parity fixtures remain, but current `ts/src/index.ts` exports the later Corpus, structural-index, search, similarity, snapshot, ranking, and vocab surfaces too. The `docs/STANDARD.md` and README sections below are historical Plan-4 snapshots and have been extended in current docs.

**Files:**
- Modify: `ts/src/index.ts`
- Modify: `python/tests/test_parity.py` (append check 3)
- Create: `ts/tests/cross_parity.test.ts` (check 4)
- Create: `ts/README.md`
- Modify: `docs/STANDARD.md`

**Interfaces:**
- Consumes: every module's public surface.
- Produces: the package barrel; cross-language checks 3 (Python parses TS emit) and 4 (TS parses Python emit).

- [ ] **Step 1: Write the barrel and its smoke test**

Replace `ts/src/index.ts`:

```typescript
export {
  CollisionError,
  FacetError,
  IdError,
  InvariantError,
  NodesError,
  RefError,
  UnknownKindError,
  ValidationError,
} from "./errors.js";
export { NodeId, type Ref } from "./ids.js";
export {
  RELATES_TO,
  RelationSchema,
  type Relation,
  fromSerialized,
  relatesTo,
  tagToRelation,
  toSerialized,
} from "./relations.js";
export { NodeMetadataSchema, NodeSchema, type Node, type NodeInput, type NodeMetadata, makeNode, newUid } from "./node.js";
export { nodeFromMarkdown, nodeToMarkdown, splitFrontmatter } from "./frontmatter.js";
export { type Invariant, type KindSpec, Registry } from "./registry.js";
export {
  MEMBERSHIP,
  MembershipSchema,
  type Membership,
  membershipOf,
  registerBuiltinShapes,
  requireAcyclic,
  requireDictKeys,
  requireSingleParent,
  requireUniqueMembers,
} from "./shapes.js";
export { Store } from "./store.js";
```

Replace `ts/tests/smoke.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { makeNode, nodeFromMarkdown, nodeToMarkdown, Registry, registerBuiltinShapes, Store } from "../src/index.js";

describe("barrel", () => {
  it("re-exports the public surface", () => {
    expect(typeof makeNode).toBe("function");
    expect(typeof nodeFromMarkdown).toBe("function");
    expect(typeof nodeToMarkdown).toBe("function");
    expect(typeof registerBuiltinShapes).toBe("function");
    expect(typeof Registry).toBe("function");
    expect(typeof Store).toBe("function");
  });
});
```

- [ ] **Step 2: Write the cross-language tests (failing)**

Append check 3 to `python/tests/test_parity.py`:

```python
TS_EMIT = FIXTURES / "gene_phf19.ts-emit.md"


def test_python_parses_ts_emit_to_oracle():
    # Check 3: TS-emitted markdown, parsed by Python, equals the oracle.
    assert to_canonical(node_from_markdown(TS_EMIT.read_text(encoding="utf-8"))) == json.loads(
        ORACLE.read_text(encoding="utf-8")
    )
```

Create `ts/tests/cross_parity.test.ts`:

```typescript
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { nodeFromMarkdown } from "../src/frontmatter.js";
import { toCanonical } from "./_canonical.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures/", import.meta.url));

describe("cross-language parity (check 4)", () => {
  it("TS parses the Python-emitted markdown to the oracle", () => {
    const md = readFileSync(join(FIXTURES, "gene_phf19.py-emit.md"), "utf-8");
    const oracle = JSON.parse(readFileSync(join(FIXTURES, "gene_phf19.canonical.json"), "utf-8"));
    expect(toCanonical(nodeFromMarkdown(md))).toEqual(oracle);
  });
});
```

- [ ] **Step 3: Run both to verify they pass**

```bash
cd ~/d/nodes/ts
rtk npm test
cd ~/d/nodes/python
rtk uv run pytest tests/test_parity.py -q
```

Expected: TS green; Python parity tests green (now 4). (Both committed cross-emitted fixtures already exist from Tasks 2 and 6; their currency guards live in their emitting language.)

- [ ] **Step 4: Write the docs**

Create `ts/README.md`:

```markdown
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
```

Append to `docs/STANDARD.md`:

```markdown
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

The TypeScript `Store` is the Plan-1 CRUD surface; `Corpus`, the derived index, and the knowledge
vocab are not yet ported.
```

- [ ] **Step 5: Final full-gate run**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
cd ~/d/nodes/python
rtk uv run pytest -q
rtk uv run ruff check src tests
rtk uv run pyright src
```

Expected: TS — full Vitest suite green, typecheck + biome clean. Python — full suite green (≥112 + 4 parity), ruff + pyright clean.

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/index.ts ts/tests/smoke.test.ts ts/tests/cross_parity.test.ts ts/README.md python/tests/test_parity.py docs/STANDARD.md
rtk git commit -m "feat(ts): barrel exports + cross-language parity checks + docs"
```

---

## Self-Review

**1. Spec coverage:**
- §1 goals / §2 historical-Store pin → Tasks 9, 3–10 (camelCase API, no Corpus/Index/vocab) ✅
- §3 restructure (`python/`+`ts/`, root `fixtures/`, migration gate) → Task 1 ✅
- §4 tooling (Zod, yaml, Vitest, Biome, npm, `tsc --noEmit`, engines/packageManager) → Task 1 + Global Constraints ✅
- §5 parity (canonical JSON oracle; checks 1–5; regenerate-and-diff currency guard) → Tasks 2 (1, py-emit currency, py round-trip), 6 (2, 5, ts-emit currency), 10 (3, 4) ✅
- §6.1–6.9 module ports → Tasks 3 (errors, ids), 4 (relations), 5 (node), 6 (frontmatter), 7 (registry), 8 (shapes), 9 (store), 10 (barrel) ✅
- §6.5 explicit YAML parse-error handling → Task 6 `splitFrontmatter` `doc.errors` ✅
- §7 errors wrapped, never raw → Tasks 5 (`makeNode`), 8 (`membershipOf`) ✅
- §9 docs (`ts/README.md`, `docs/STANDARD.md` section) → Task 10 ✅

**2. Placeholder scan:** No TBD/"handle errors"/"similar to"/uncoded steps. The fixture-generation steps (Task 2 Step 4, Task 6 Step 5) contain runnable commands; their committed outputs are enforced by currency tests.

**3. Type consistency:** `makeNode`/`NodeInput`/`Node`, `nodeFromMarkdown`/`nodeToMarkdown`/`splitFrontmatter`, `relatesTo`/`fromSerialized`/`toSerialized`/`RELATES_TO`, `Registry`/`KindSpec`/`Invariant`, `membershipOf`/`MEMBERSHIP`/`registerBuiltinShapes`/the four `require*`, `Store` method names are identical across the Interfaces blocks, the barrel (Task 10), and every consumer. `deprecatedIds` (API) ↔ `deprecated_ids` (disk + canonical JSON) used consistently. TS test fixture paths use `fileURLToPath(new URL("../../fixtures/", import.meta.url))` (portable across all supported Node; no `import.meta.dirname` version dependency).

**Note for executor:** If a fixture-generation one-liner (Task 2 Step 4 / Task 6 Step 5) can't run via the suggested invocation on the local Node, any method that writes the committed fixture from the *current* emitter is acceptable — the regenerate-and-diff currency tests are the real gate.
