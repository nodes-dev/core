# Mindful v6 Package (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the headless `mindful` TypeScript package in `~/d/mindful/v6` over the `@nodes/kernel` substrate — a `Mindful` API that captures thoughts, builds mindmaps (graph) and journals (list), and encapsulates all structural form-facet maintenance so callers never hand-build `membership`/`edges`/`order`.

**Architecture:** `@nodes/kernel` gains a real build (`dist/`) so it is consumable as a package. `~/d/mindful/v6` is a new TS package depending on it via a one-way `file:` dependency. The package registers a *mindful profile* (`thought`/`mindmap`/`journal` kinds adopting the kernel's `graph`/`list` shapes) and exposes a `Mindful` class that wraps a `Corpus`, translating high-level intents into validated facet mutations.

**Tech Stack:** TypeScript 5.5+, zod v3 (transitively via the kernel), vitest, biome (width 120). `@nodes/kernel` at `~/d/nodes/ts` (already implements the structural-shape contract — Plan A merged). The mindful package at `~/d/mindful/v6`. All commands via the `rtk` wrapper.

This is **Plan B**, the third and final plan of mindful v6 SP1 (spec: `~/d/nodes/docs/specs/2026-06-23-mindful-v6-sp1-abstraction-design.md`, Part B / §3). It depends on Plan A (both kernels merged: Python `a7dd55b`, TS `f2f9749`). SP2 (the `visualIdentity` facet) and SP3 (renderer + CLI/TUI) are out of scope.

## Cross-Repo Structure

This plan spans **two repos**:
- **Task 1** modifies `~/d/nodes/ts` (adds the kernel build) — committed in the `nodes` git repo on a feature branch.
- **Tasks 2–6** create and build `~/d/mindful/v6` — a NEW repo (`git init` in Task 2), committed there.

The SDD progress ledger lives in `~/d/nodes/.superpowers/sdd/progress.md` (the controller's durable record across both repos).

## Global Constraints (from spec §3, copied verbatim where exact)

- **Dependency direction is one-way:** `mindful/v6 → @nodes/kernel`; the kernel never imports mindful. The dependency is `"@nodes/kernel": "file:../../nodes/ts"`.
- **Three kinds:** `thought` (no shape, no required facets in SP1 — ≈ `note`), `mindmap` (adopts `graph`), `journal` (adopts `list`). `registerMindfulProfile(reg)` assumes `registerBuiltinShapes(reg)` already ran.
- **Mindful's whole reason to exist** is to encapsulate form-facet maintenance so callers never hand-build `membership`/`edges`/`order`. All mutations go through `Corpus`, preserving its fail-before-write ordering and persistence.
- **Two distinct graphs, deliberately:** (1) the **global relation graph** (`relatesTo` links from tags) is what `Corpus.outbound`/`inbound`/`neighbors` traverse; surfaced as `related(thoughtId)`. (2) A **mindmap's internal edges** live in that mindmap's `edges` form facet, scoped to the structure and NOT part of the global graph; read via `mindmapEdges(mapId)`, NEVER via `related`.
- **Order never via array position:** a journal's order lives in the `order` form facet, maintained alongside `membership`; member array position carries no ordering.
- **Tags fail early:** `tag(thoughtId, name)` resolves by alias against the corpus; an unresolved tag throws `RefError`. SP1 does NOT auto-create nodes (deferred, with a `topic` kind).
- **Embedder is a seam:** `Mindful` accepts an optional `Embedder` (`cacheNamespace` + `embed(texts)`). `search` and graph traversal work with no embedder; `similar*` require one and otherwise raise `EmbedderRequiredError`. Tests use a deterministic stub embedder; the real model is deferred.
- **Fail early everywhere; no silent fallbacks.** `UnknownKindError` (unknown kind/shape), `FacetError` (missing/malformed facet), `InvariantError` (form-invariant violation), `RefError` (unresolved tag/ref), `EmbedderRequiredError` (semantic query without embedder). All validation precedes any disk write (the kernel enforces this).
- **Clean breaking change ethos:** no compat layers. Use `~/d/` form for filepaths in docs/comments. Conventional-commits messages, **no `Co-Authored-By` trailer**.
- **Gate — kernel (Task 1), from `~/d/nodes/ts`:** `rtk npm run build` (new) must emit `dist/`; `rtk npm test`, `rtk npm run typecheck`, `rtk npm run check` stay green.
- **Gate — mindful (Tasks 2–6), from `~/d/mindful/v6`:** `rtk npm test` (vitest), `rtk npm run typecheck` (`tsc --noEmit`), `rtk npm run check` (biome) must all pass.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `~/d/nodes/ts/tsconfig.build.json` | emit `dist/` (.js + .d.ts) from `src` only | 1 |
| `~/d/nodes/ts/package.json` | `build` script, `exports`/`types`/`files`, `main`→`dist` | 1 |
| `~/d/mindful/v6/package.json` | `file:` dep on `@nodes/kernel`, scripts | 2 |
| `~/d/mindful/v6/tsconfig.json`, `biome.json`, `vitest.config.ts` | toolchain (match nodes conventions) | 2 |
| `~/d/mindful/v6/src/index.ts` | package barrel | 2,3,4 |
| `~/d/mindful/v6/src/kinds.ts` | `THOUGHT`/`MINDMAP`/`JOURNAL` + `KindSpec`s | 3 |
| `~/d/mindful/v6/src/profile.ts` | `registerMindfulProfile(reg)` | 3 |
| `~/d/mindful/v6/src/api.ts` | `Mindful` class (thoughts/tags/queries, then mindmaps, then journals) | 4,5,6 |
| `~/d/mindful/v6/tests/*.test.ts` | per-area tests | 2–6 |

`api.ts` grows across Tasks 4–6 (thoughts/tags/queries → mindmaps → journals); each task adds a cohesive method group. If `api.ts` grows unwieldy, a split into `api/thoughts.ts`/`api/mindmaps.ts`/`api/journals.ts` is acceptable, but SP1's surface is small enough for one file — do not split preemptively.

---

### Task 1: Add a real build to `@nodes/kernel`

**Repo:** `~/d/nodes` (feature branch). **Files:**
- Create: `~/d/nodes/ts/tsconfig.build.json`
- Modify: `~/d/nodes/ts/package.json`

**Interfaces:**
- Produces: a built `~/d/nodes/ts/dist/` (`.js` + `.d.ts`), `package.json` `main`/`types`/`exports`/`files` pointing at `dist`, and an `npm run build` script. Consumed by the mindful `file:` dependency (Task 2+).

The existing `tsconfig.json` has `noEmit: true` and includes `src` + `tests`. The build config overrides `noEmit` and emits `src` only.

- [ ] **Step 1: Create `~/d/nodes/ts/tsconfig.build.json`**

```json
{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "noEmit": false,
    "outDir": "dist",
    "rootDir": "src",
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  },
  "include": ["src"]
}
```

- [ ] **Step 2: Update `~/d/nodes/ts/package.json`**

Change `"main"` and add `types`/`exports`/`files` + a `build` script. The resulting fields (merge into the existing file — keep `name`, `version`, `type: "module"`, `engines`, `packageManager`, deps, devDeps, and the existing `test`/`typecheck`/`check` scripts unchanged):

```jsonc
{
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "default": "./dist/index.js"
    }
  },
  "files": ["dist"],
  "scripts": {
    "build": "tsc -p tsconfig.build.json",
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "check": "biome check ."
  }
}
```

- [ ] **Step 3: Build and verify dist emits correctly**

Run: `cd ~/d/nodes/ts && rtk npm run build`
Expected: exits 0; `dist/index.js` and `dist/index.d.ts` exist. Verify:
```bash
cd ~/d/nodes/ts && rtk npm run build && ls dist/index.js dist/index.d.ts && node -e "import('./dist/index.js').then(m => console.log(typeof m.Corpus, typeof m.Registry, typeof m.registerBuiltinShapes))"
```
Expected: prints `function function function` (the built ESM barrel resolves and exports the kernel API).

- [ ] **Step 4: Confirm the existing gate is unaffected**

Run: `cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: vitest all passed (286), `tsc --noEmit` clean, biome clean. (Add `dist/` to `.gitignore` if biome/tests would otherwise scan it — verify biome does not lint `dist`; if `rtk npm run check` reports issues in `dist`, add `dist` to `~/d/nodes/ts/.gitignore` and confirm biome ignores git-ignored paths, or add a biome `files.ignore` for `dist`.)

- [ ] **Step 5: Ensure `dist/` is git-ignored**

The built output is a derived artifact, not source. Confirm/append `dist/` to `~/d/nodes/ts/.gitignore` (create the file if absent):
```
dist/
```

- [ ] **Step 6: Commit (in the nodes repo)**

```bash
cd ~/d/nodes && rtk git add ts/tsconfig.build.json ts/package.json ts/.gitignore
rtk git commit -m "build(kernel): emit dist with exports/types so @nodes/kernel is consumable as a package"
```

---

### Task 2: Scaffold the `mindful/v6` package

**Repo:** `~/d/mindful/v6` (NEW — `git init`). **Files:**
- Create: `~/d/mindful/v6/{package.json, tsconfig.json, biome.json, vitest.config.ts, .gitignore}`
- Create: `~/d/mindful/v6/src/index.ts`, `~/d/mindful/v6/tests/smoke.test.ts`

**Interfaces:**
- Produces: an installable, test/typecheck/lint-clean package that imports `@nodes/kernel` via `file:` and can construct a `Corpus`. Later tasks add `src/{kinds,profile,api}.ts`.

- [ ] **Step 1: Initialize the repo and ensure the kernel is built**

```bash
mkdir -p ~/d/mindful/v6 && cd ~/d/mindful/v6 && rtk git init
cd ~/d/nodes/ts && rtk npm run build   # mindful consumes dist/ — must exist before install
```

- [ ] **Step 2: Create `~/d/mindful/v6/package.json`**

```json
{
  "name": "@mindful/v6",
  "version": "0.1.0",
  "description": "Mindful: a headless thought/mindmap/journal app over @nodes/kernel",
  "type": "module",
  "engines": { "node": ">=20" },
  "main": "src/index.ts",
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "check": "biome check ."
  },
  "dependencies": {
    "@nodes/kernel": "file:../../nodes/ts"
  },
  "devDependencies": {
    "@biomejs/biome": "^1.9.0",
    "@types/node": "^20.0.0",
    "typescript": "^5.5.0",
    "vitest": "^2.0.0"
  }
}
```

- [ ] **Step 3: Create the toolchain configs**

`~/d/mindful/v6/tsconfig.json`:
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

`~/d/mindful/v6/biome.json`:
```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
  "formatter": { "enabled": true, "lineWidth": 120 },
  "linter": { "enabled": true, "rules": { "recommended": true } }
}
```

`~/d/mindful/v6/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";

export default defineConfig({ test: { include: ["tests/**/*.test.ts"] } });
```

`~/d/mindful/v6/.gitignore`:
```
node_modules/
```

- [ ] **Step 4: Create the package barrel `~/d/mindful/v6/src/index.ts`**

```ts
// Mindful v6 — headless thought/mindmap/journal app over @nodes/kernel.
// Public surface grows across the plan: kinds + profile (Task 3), Mindful (Tasks 4-6).
export {};
```

- [ ] **Step 5: Write the smoke test `~/d/mindful/v6/tests/smoke.test.ts`**

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus, Registry, registerBuiltinShapes } from "@nodes/kernel";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "mindful-smoke-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("toolchain + @nodes/kernel file: dependency", () => {
  it("imports the kernel and constructs a Corpus over a temp root", () => {
    const reg = new Registry();
    registerBuiltinShapes(reg);
    expect(reg.isShape("graph")).toBe(true);
    const corpus = new Corpus(root, reg);
    expect(corpus.all()).toEqual([]);
  });
});
```

- [ ] **Step 6: Install, then run the gate**

```bash
cd ~/d/mindful/v6 && rtk npm install
rtk npm test && rtk npm run typecheck && rtk npm run check
```
Expected: `npm install` links `@nodes/kernel` (from `file:`); vitest → 1 passed; `tsc --noEmit` clean; biome clean. If the import of `@nodes/kernel` fails to resolve, confirm Task 1's `dist/` was built and `package.json` `exports` point at `dist/index.js`.

- [ ] **Step 7: Commit (in the mindful repo)**

```bash
cd ~/d/mindful/v6 && rtk git add -A
rtk git commit -m "chore: scaffold mindful v6 package over @nodes/kernel (file: dep, toolchain, smoke test)"
```
(Note: `package-lock.json` may be created by `npm install` — add it; do NOT add `node_modules/`.)

---

### Task 3: Kinds & mindful profile

**Repo:** `~/d/mindful/v6`. **Files:**
- Create: `src/kinds.ts`, `src/profile.ts`
- Modify: `src/index.ts` (export the new surface)
- Test: `tests/profile.test.ts`

**Interfaces:**
- Consumes: `KindSpec`, `Registry`, `registerBuiltinShapes` (`@nodes/kernel`).
- Produces:
  - `kinds.ts`: `THOUGHT = "thought"`, `MINDMAP = "mindmap"`, `JOURNAL = "journal"`; `thoughtSpec`/`mindmapSpec`/`journalSpec: KindSpec`.
  - `profile.ts`: `registerMindfulProfile(reg: Registry): void` (assumes `registerBuiltinShapes(reg)` already ran).

- [ ] **Step 1: Write the failing test `tests/profile.test.ts`**

```ts
import { describe, expect, it } from "vitest";
import { Registry, makeNode, registerBuiltinShapes } from "@nodes/kernel";
import { JOURNAL, MINDMAP, THOUGHT } from "../src/kinds.js";
import { registerMindfulProfile } from "../src/profile.js";

function reg(): Registry {
  const r = new Registry();
  registerBuiltinShapes(r);
  registerMindfulProfile(r);
  return r;
}

describe("mindful profile", () => {
  it("registers the three mindful kinds", () => {
    const r = reg();
    for (const k of [THOUGHT, MINDMAP, JOURNAL]) expect(r.isRegistered(k)).toBe(true);
  });

  it("a thought validates with no facets", () => {
    expect(() => reg().validate(makeNode({ id: `${THOUGHT}:t1`, kind: THOUGHT, title: "T" }))).not.toThrow();
  });

  it("a mindmap validates as a graph (membership + edges)", () => {
    const m = makeNode({
      id: `${MINDMAP}:garden`,
      kind: MINDMAP,
      title: "Garden",
      facets: { membership: { members: [] }, edges: { edges: [] } },
    });
    expect(() => reg().validate(m)).not.toThrow();
  });

  it("a journal validates as a list (membership + order)", () => {
    const j = makeNode({
      id: `${JOURNAL}:2026`,
      kind: JOURNAL,
      title: "2026",
      facets: { membership: { members: [] }, order: { order: [] } },
    });
    expect(() => reg().validate(j)).not.toThrow();
  });

  it("registerMindfulProfile requires the builtin shapes (unknown shape fails early)", () => {
    const bare = new Registry(); // no registerBuiltinShapes
    expect(() => registerMindfulProfile(bare)).toThrow(); // mindmap adopts unknown shape "graph"
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/profile.test.ts`
Expected: FAIL — `../src/kinds.js` / `../src/profile.js` do not exist.

- [ ] **Step 3: Write `src/kinds.ts`**

```ts
import type { KindSpec } from "@nodes/kernel";

export const THOUGHT = "thought";
export const MINDMAP = "mindmap";
export const JOURNAL = "journal";

// thought: its own kind (≈ note); SP2 adds `visualIdentity` as a required facet.
export const thoughtSpec: KindSpec = { name: THOUGHT };
// mindmap/journal: first-class kinds adopting the kernel's graph/list shapes.
export const mindmapSpec: KindSpec = { name: MINDMAP, shape: "graph" };
export const journalSpec: KindSpec = { name: JOURNAL, shape: "list" };
```

- [ ] **Step 4: Write `src/profile.ts`**

```ts
import type { Registry } from "@nodes/kernel";
import { journalSpec, mindmapSpec, thoughtSpec } from "./kinds.js";

/** Register the three mindful kinds. Assumes `registerBuiltinShapes(reg)` already ran
 * (mindmap/journal adopt the `graph`/`list` shapes; an unregistered shape fails early). */
export function registerMindfulProfile(reg: Registry): void {
  reg.register(thoughtSpec);
  reg.register(mindmapSpec);
  reg.register(journalSpec);
}
```

- [ ] **Step 5: Export from the barrel `src/index.ts`**

```ts
export { JOURNAL, MINDMAP, THOUGHT, journalSpec, mindmapSpec, thoughtSpec } from "./kinds.js";
export { registerMindfulProfile } from "./profile.js";
```

- [ ] **Step 6: Run the test, then the gate**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/profile.test.ts`
Expected: PASS.
Run: `rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
cd ~/d/mindful/v6 && rtk git add src/kinds.ts src/profile.ts src/index.ts tests/profile.test.ts
rtk git commit -m "feat: mindful kinds (thought/mindmap/journal) + registerMindfulProfile"
```

---

### Task 4: `Mindful` — thoughts, tags, queries

**Repo:** `~/d/mindful/v6`. **Files:**
- Create: `src/api.ts`
- Modify: `src/index.ts`
- Test: `tests/mindful-thoughts.test.ts`

**Interfaces:**
- Consumes: `Corpus`, `Registry`, `Node`, `Embedder`, `Relation`, `SearchHit`, `SimilarHit`, `makeNode`, `newUid`, `registerBuiltinShapes`, `tagToRelation`, `ValidationError`, `RefError` (`@nodes/kernel`); the mindful profile (Task 3).
- Produces (this task's slice of `Mindful`):
  - `new Mindful(root: string, opts?: { embedder?: Embedder })`
  - `capture(input: { title: string; body?: string; tags?: string[] }): Node`
  - `get(id: string): Node`, `edit(id: string, patch: { title?: string; body?: string }): Node`, `delete(id: string): void`
  - `tag(thoughtId: string, name: string): Node`
  - `search(q: string, limit?: number): SearchHit[]`, `similar(thoughtId: string, k?: number): SimilarHit[]`, `similarText(text: string, k?: number): SimilarHit[]`, `related(thoughtId: string): Node[]`, `allThoughts(): Node[]`
  - Helper (module-private): `slugify(title: string): string`.

- [ ] **Step 1: Write the failing test `tests/mindful-thoughts.test.ts`**

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { type Embedder, EmbedderRequiredError, RefError, ValidationError, type Vector } from "@nodes/kernel";
import { Mindful } from "../src/api.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "mindful-thoughts-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

// Deterministic stub: "cat" → [1,0], anything else → [0,1].
class StubEmbedder implements Embedder {
  readonly cacheNamespace = "stub-v1";
  embed(texts: string[]): Vector[] {
    return texts.map((t) => (t.toLowerCase().includes("cat") ? [1, 0] : [0, 1]));
  }
}

describe("Mindful — thoughts", () => {
  it("captures a thought and reads it back", () => {
    const m = new Mindful(root);
    const t = m.capture({ title: "First", body: "hello" });
    expect(t.kind).toBe("thought");
    expect(t.id.startsWith("thought:")).toBe(true);
    expect(m.get(t.id).body).toBe("hello");
  });

  it("edits a thought (title/body) preserving identity", () => {
    const m = new Mindful(root);
    const t = m.capture({ title: "Draft" });
    const edited = m.edit(t.id, { body: "now with a body" });
    expect(edited.uid).toBe(t.uid);
    expect(m.get(t.id).body).toBe("now with a body");
  });

  it("deletes a thought", () => {
    const m = new Mindful(root);
    const t = m.capture({ title: "Temp" });
    m.delete(t.id);
    expect(() => m.get(t.id)).toThrow(RefError);
  });

  it("tag resolves an existing thought by title and links via the global graph", () => {
    const m = new Mindful(root);
    const target = m.capture({ title: "Recipes" });
    const note = m.capture({ title: "Carbonara" });
    m.tag(note.id, "Recipes");
    const related = m.related(note.id);
    expect(related.map((n) => n.id)).toContain(target.id);
  });

  it("an unresolved tag fails early with RefError", () => {
    const m = new Mindful(root);
    const note = m.capture({ title: "Orphan" });
    expect(() => m.tag(note.id, "does-not-exist")).toThrow(RefError);
  });

  it("captures with tags in one call", () => {
    const m = new Mindful(root);
    m.capture({ title: "Recipes" });
    const note = m.capture({ title: "Carbonara", tags: ["Recipes"] });
    expect(m.related(note.id).some((n) => n.title === "Recipes")).toBe(true);
  });

  it("capture with an unresolved tag throws and persists nothing (atomic)", () => {
    const m = new Mindful(root);
    expect(() => m.capture({ title: "Carbonara", tags: ["does-not-exist"] })).toThrow(RefError);
    expect(m.allThoughts()).toEqual([]); // the half-created thought was never written
  });

  it("tagging by a title shared by multiple thoughts fails early instead of guessing", () => {
    const m = new Mindful(root);
    m.capture({ title: "Recipes" });
    m.capture({ title: "Recipes" }); // duplicate title — allowed in SP1
    const note = m.capture({ title: "Carbonara" });
    expect(() => m.tag(note.id, "Recipes")).toThrow(ValidationError);
  });

  it("search finds a captured thought", () => {
    const m = new Mindful(root);
    m.capture({ title: "Quantum", body: "entanglement is spooky" });
    expect(m.search("entanglement").length).toBeGreaterThan(0);
  });

  it("similar requires an embedder and otherwise raises", () => {
    const m = new Mindful(root); // no embedder
    const t = m.capture({ title: "x" });
    expect(() => m.similar(t.id)).toThrow(EmbedderRequiredError);
  });

  it("similar works with a stub embedder", () => {
    const m = new Mindful(root, { embedder: new StubEmbedder() });
    const cat = m.capture({ title: "cat", body: "a cat" });
    m.capture({ title: "dog", body: "a dog" });
    const hits = m.similar(cat.id);
    expect(hits.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/mindful-thoughts.test.ts`
Expected: FAIL — `../src/api.js` does not exist.

- [ ] **Step 3: Write `src/api.ts` (this task's slice)**

```ts
import {
  Corpus,
  type Embedder,
  type Node,
  Registry,
  type Relation,
  type SearchHit,
  type SimilarHit,
  ValidationError,
  makeNode,
  newUid,
  registerBuiltinShapes,
  tagToRelation,
} from "@nodes/kernel";
import { THOUGHT } from "./kinds.js";
import { registerMindfulProfile } from "./profile.js";

/** Lowercase, hyphenate, trim to a valid NodeId slug. Throws if the title yields nothing usable. */
export function slugify(title: string): string {
  const slug = title
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (slug === "") throw new ValidationError(`title ${JSON.stringify(title)} does not yield a usable slug`);
  return slug;
}

export interface MindfulOptions {
  embedder?: Embedder;
}

/** Title/lowercase-title → thought id, with titles that resolve to multiple thoughts held out as ambiguous. */
interface AliasIndex {
  map: Record<string, string>;
  ambiguous: Set<string>;
}

export class Mindful {
  readonly corpus: Corpus;

  constructor(root: string, opts: MindfulOptions = {}) {
    const reg = new Registry();
    registerBuiltinShapes(reg);
    registerMindfulProfile(reg);
    this.corpus = new Corpus(root, reg, opts.embedder);
  }

  // --- thoughts ---

  capture(input: { title: string; body?: string; tags?: string[] }): Node {
    const node = makeNode({ id: `${THOUGHT}:${newUid()}`, kind: THOUGHT, title: input.title, body: input.body ?? "" });
    // Resolve every tag BEFORE the single write: a miss (RefError) or an ambiguous title
    // (ValidationError) throws here, so an unresolved tag never leaves a half-created thought on disk.
    const idx = this.aliasIndex();
    for (const name of input.tags ?? []) node.relations.push(this.resolveTag(node.id, name, idx));
    this.corpus.add(node); // one write; nothing persists if a tag above threw
    return this.corpus.get(node.id);
  }

  get(id: string): Node {
    return this.corpus.get(id);
  }

  edit(id: string, patch: { title?: string; body?: string }): Node {
    const node = this.corpus.get(id);
    if (patch.title !== undefined) node.title = patch.title;
    if (patch.body !== undefined) node.body = patch.body;
    this.corpus.add(node); // same uid + id → overwrite (Corpus.assertAddable permits it), re-validates
    return this.corpus.get(id);
  }

  delete(id: string): void {
    this.corpus.delete(id);
  }

  // --- tags (global relation graph) ---

  // SP1 allows duplicate thought titles, so a title can map to more than one id. An alias key that
  // resolves to >1 distinct thought is ambiguous: we record it separately and refuse to guess.
  private aliasIndex(): AliasIndex {
    const byKey: Record<string, Set<string>> = {};
    for (const n of this.corpus.all()) {
      for (const key of [n.title, n.title.toLowerCase()]) (byKey[key] ??= new Set<string>()).add(n.id);
    }
    const map: Record<string, string> = {};
    const ambiguous = new Set<string>();
    for (const [key, ids] of Object.entries(byKey)) {
      if (ids.size === 1) map[key] = [...ids][0];
      else ambiguous.add(key);
    }
    return { map, ambiguous };
  }

  // Mirrors tagToRelation's lookup order (map[name] ?? map[name.toLowerCase()]) but fails early on the
  // key it would land on if that key is ambiguous — instead of silently linking to an arbitrary match.
  private resolveTag(source: string, name: string, idx: AliasIndex): Relation {
    if (idx.map[name] === undefined) {
      const lower = name.toLowerCase();
      if (idx.ambiguous.has(name) || (idx.map[lower] === undefined && idx.ambiguous.has(lower))) {
        throw new ValidationError(`ambiguous tag ${JSON.stringify(name)}: multiple thoughts share that title`);
      }
    }
    return tagToRelation(source, name, idx.map); // RefError on a genuine miss
  }

  tag(thoughtId: string, name: string): Node {
    const node = this.corpus.get(thoughtId);
    node.relations.push(this.resolveTag(node.id, name, this.aliasIndex())); // RefError/ValidationError before any write
    this.corpus.add(node); // overwrite + re-validate; relation now in the global graph
    return this.corpus.get(thoughtId);
  }

  // --- queries ---

  search(q: string, limit?: number): SearchHit[] {
    return this.corpus.search(q, limit);
  }

  similar(thoughtId: string, k?: number): SimilarHit[] {
    return this.corpus.similar(thoughtId, k); // raises EmbedderRequiredError without an embedder
  }

  similarText(text: string, k?: number): SimilarHit[] {
    return this.corpus.similarText(text, k);
  }

  /** The GLOBAL relation graph (tags/relatesTo) — never a mindmap's internal edges. */
  related(thoughtId: string): Node[] {
    return this.corpus.neighbors(thoughtId);
  }

  allThoughts(): Node[] {
    return this.corpus.all().filter((n) => n.kind === THOUGHT);
  }
}
```

Note: `tagToRelation(source, name, map)` resolves `map[name] ?? map[name.toLowerCase()]` and throws `RefError` on a miss — so `aliasIndex()` registers both the title and its lowercase form. Because SP1 permits duplicate thought titles, `aliasIndex()` holds any key that resolves to more than one thought in a separate `ambiguous` set, and `resolveTag` throws `ValidationError` rather than linking to an arbitrary match (fail early, no silent fallback). `capture` builds ONE index up front and resolves every tag against it before its single `corpus.add`, so an unresolved or ambiguous tag never persists a half-created thought. To keep Task 4 lint-clean, import ONLY `THOUGHT` from `./kinds.js` here and add `MINDMAP`/`JOURNAL` in Task 5/6 (their first use); likewise `requireThought` (Task 5) is defined where it is first used, since biome's `noUnusedPrivateClassMembers` would flag a method defined a task before its first call.

- [ ] **Step 4: Export `Mindful` from the barrel `src/index.ts`**

Append:
```ts
export { Mindful, type MindfulOptions, slugify } from "./api.js";
```

- [ ] **Step 5: Run the test, then the gate**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/mindful-thoughts.test.ts`
Expected: PASS.
Run: `rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd ~/d/mindful/v6 && rtk git add src/api.ts src/index.ts tests/mindful-thoughts.test.ts
rtk git commit -m "feat: Mindful — capture/edit/delete thoughts, tags, search/similar/related"
```

---

### Task 5: `Mindful` — mindmaps (graph form facet)

**Repo:** `~/d/mindful/v6`. **Files:**
- Modify: `src/api.ts`
- Test: `tests/mindful-mindmaps.test.ts`

**Interfaces:**
- Consumes (add to `api.ts` imports): `MEMBERSHIP`, `EDGES`, `membershipOf`, `edgesOf`, `RELATES_TO` (`@nodes/kernel`); `MINDMAP` (`./kinds.js`). (`Relation` and `ValidationError` are already imported by Task 4; `RefError` is needed only in this task's test file.)
- Produces (added to `Mindful`):
  - `createMindmap(input: { title: string }): Node`
  - `addThought(mapId: string, thoughtId: string): Node`
  - `removeThought(mapId: string, thoughtId: string): Node`
  - `link(mapId: string, fromId: string, toId: string, predicate?: string): Node`
  - `unlink(mapId: string, fromId: string, toId: string, predicate?: string): Node`
  - `mindmapEdges(mapId: string): Relation[]`

A mindmap is a `graph`-shaped node: `membership.members` is its node set; `edges.edges` are its internal binary edges (NOT global relations). Endpoints must be members — enforced by the kernel's `requireEdgeEndpointsAreMembers` on `corpus.add`.

- [ ] **Step 1: Write the failing test `tests/mindful-mindmaps.test.ts`**

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { InvariantError, RefError } from "@nodes/kernel";
import { Mindful } from "../src/api.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "mindful-mindmaps-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("Mindful — mindmaps", () => {
  it("creates an empty mindmap that validates as a graph", () => {
    const m = new Mindful(root);
    const map = m.createMindmap({ title: "Garden" });
    expect(map.kind).toBe("mindmap");
    expect(map.id).toBe("mindmap:garden");
    expect(m.mindmapEdges(map.id)).toEqual([]);
  });

  it("adds thoughts and links them; edges live in the structure, not the global graph", () => {
    const m = new Mindful(root);
    const a = m.capture({ title: "A" });
    const b = m.capture({ title: "B" });
    const map = m.createMindmap({ title: "Map" });
    m.addThought(map.id, a.id);
    m.addThought(map.id, b.id);
    m.link(map.id, a.id, b.id, "leads-to");
    const edges = m.mindmapEdges(map.id);
    expect(edges).toHaveLength(1);
    expect([edges[0].source, edges[0].target, edges[0].predicate]).toEqual([a.id, b.id, "leads-to"]);
    // mindmap edges are NOT global relations: related() (global graph) sees nothing
    expect(m.related(a.id)).toEqual([]);
  });

  it("linking a non-member endpoint fails early (kernel invariant)", () => {
    const m = new Mindful(root);
    const a = m.capture({ title: "A" });
    const b = m.capture({ title: "B" });
    const map = m.createMindmap({ title: "Map" });
    m.addThought(map.id, a.id); // b is NOT a member
    expect(() => m.link(map.id, a.id, b.id)).toThrow(InvariantError);
  });

  it("unlink removes a specific edge", () => {
    const m = new Mindful(root);
    const a = m.capture({ title: "A" });
    const b = m.capture({ title: "B" });
    const map = m.createMindmap({ title: "Map" });
    m.addThought(map.id, a.id);
    m.addThought(map.id, b.id);
    m.link(map.id, a.id, b.id, "x");
    m.unlink(map.id, a.id, b.id, "x");
    expect(m.mindmapEdges(map.id)).toEqual([]);
  });

  it("removeThought drops the member and any edges touching it", () => {
    const m = new Mindful(root);
    const a = m.capture({ title: "A" });
    const b = m.capture({ title: "B" });
    const map = m.createMindmap({ title: "Map" });
    m.addThought(map.id, a.id);
    m.addThought(map.id, b.id);
    m.link(map.id, a.id, b.id, "x");
    const updated = m.removeThought(map.id, a.id);
    expect(updated.facets.membership).toEqual({ members: [b.id] });
    expect(m.mindmapEdges(map.id)).toEqual([]); // edge a->b removed with a
  });

  it("addThought rejects a missing thought id (fail early, no dangling member)", () => {
    const m = new Mindful(root);
    const map = m.createMindmap({ title: "Map" });
    expect(() => m.addThought(map.id, "thought:does-not-exist")).toThrow(RefError);
    expect((m.get(map.id).facets.membership as { members: string[] }).members).toEqual([]);
  });

  it("addThought is idempotent on the member set (unique members)", () => {
    const m = new Mindful(root);
    const a = m.capture({ title: "A" });
    const map = m.createMindmap({ title: "Map" });
    m.addThought(map.id, a.id);
    const again = m.addThought(map.id, a.id);
    expect((again.facets.membership as { members: string[] }).members).toEqual([a.id]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/mindful-mindmaps.test.ts`
Expected: FAIL — `createMindmap`/`addThought`/etc. are not methods of `Mindful`.

- [ ] **Step 3: Extend `src/api.ts`**

Add to the `@nodes/kernel` import: `EDGES`, `MEMBERSHIP`, `RELATES_TO`, `edgesOf`, `membershipOf` (`Relation` is already imported by Task 4). Add `MINDMAP` to the `./kinds.js` import. Add these methods to the `Mindful` class — `requireThought` is defined here (its first use) so biome's `noUnusedPrivateClassMembers` does not flag it in Task 4:

```ts
  // --- mindmaps (graph form facet) ---

  // Members are live thoughts, not arbitrary ids: the kernel checks structural consistency, not
  // existence, so the API resolves the id here (RefError if absent) and rejects non-thoughts.
  private requireThought(thoughtId: string): void {
    const node = this.corpus.get(thoughtId); // throws RefError if no such node
    if (node.kind !== THOUGHT) {
      throw new ValidationError(`${thoughtId} is a ${node.kind}, not a thought`);
    }
  }

  createMindmap(input: { title: string }): Node {
    const node = makeNode({
      id: `${MINDMAP}:${slugify(input.title)}`,
      kind: MINDMAP,
      title: input.title,
      facets: { [MEMBERSHIP]: { members: [] }, [EDGES]: { edges: [] } },
    });
    this.corpus.add(node);
    return this.corpus.get(node.id);
  }

  addThought(mapId: string, thoughtId: string): Node {
    const map = this.corpus.get(mapId);
    this.requireThought(thoughtId); // fail early: no dangling members
    const members = membershipOf(map).members;
    if (!members.includes(thoughtId)) {
      map.facets[MEMBERSHIP] = { members: [...members, thoughtId] };
      this.corpus.add(map);
    }
    return this.corpus.get(mapId);
  }

  removeThought(mapId: string, thoughtId: string): Node {
    const map = this.corpus.get(mapId);
    const members = membershipOf(map).members.filter((m) => m !== thoughtId);
    const edges = edgesOf(map).edges.filter((e) => e.source !== thoughtId && e.target !== thoughtId);
    map.facets[MEMBERSHIP] = { members };
    map.facets[EDGES] = { edges };
    this.corpus.add(map);
    return this.corpus.get(mapId);
  }

  link(mapId: string, fromId: string, toId: string, predicate: string = RELATES_TO): Node {
    const map = this.corpus.get(mapId);
    const edges = edgesOf(map).edges;
    map.facets[EDGES] = { edges: [...edges, { source: fromId, predicate, target: toId }] };
    this.corpus.add(map); // requireEdgeEndpointsAreMembers fails early if fromId/toId not members
    return this.corpus.get(mapId);
  }

  unlink(mapId: string, fromId: string, toId: string, predicate: string = RELATES_TO): Node {
    const map = this.corpus.get(mapId);
    const edges = edgesOf(map).edges.filter(
      (e) => !(e.source === fromId && e.target === toId && e.predicate === predicate),
    );
    map.facets[EDGES] = { edges };
    this.corpus.add(map);
    return this.corpus.get(mapId);
  }

  mindmapEdges(mapId: string): Relation[] {
    return edgesOf(this.corpus.get(mapId)).edges;
  }
```

Note on writing facets: `edgesOf(map).edges` returns parsed `Relation[]` (full objects with `directed`/`weight`/`attrs` defaults); writing `{ source, predicate, target }` for a new edge is sufficient — the kernel re-parses the facet (applying `RelationSchema` defaults) on validate and on extraction. Re-assigning the whole facet object (rather than mutating in place) keeps the stored shape explicit.

- [ ] **Step 4: Run the test, then the gate**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/mindful-mindmaps.test.ts`
Expected: PASS.
Run: `rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd ~/d/mindful/v6 && rtk git add src/api.ts tests/mindful-mindmaps.test.ts
rtk git commit -m "feat: Mindful mindmaps — addThought/link/unlink/removeThought over the graph edges facet"
```

---

### Task 6: `Mindful` — journals (list form facet)

**Repo:** `~/d/mindful/v6`. **Files:**
- Modify: `src/api.ts`
- Test: `tests/mindful-journals.test.ts`

**Interfaces:**
- Consumes (already imported in api.ts after Task 5): `MEMBERSHIP`, `membershipOf`, `makeNode`; add `ORDER`, `orderOf`, and `JOURNAL` (from `./kinds.js`).
- Produces (added to `Mindful`):
  - `createJournal(input: { title: string }): Node`
  - `append(journalId: string, thoughtId: string): Node`
  - `reorder(journalId: string, order: string[]): Node`
  - `remove(journalId: string, thoughtId: string): Node`

A journal is a `list`-shaped node: `membership.members` is its set; `order.order` is the explicit ordering (a permutation of members). The kernel's `requireOrderIsPermutation` enforces that `order` and `members` are the same set with the same length — order is maintained alongside membership, never via array position.

- [ ] **Step 1: Write the failing test `tests/mindful-journals.test.ts`**

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { InvariantError, RefError } from "@nodes/kernel";
import { Mindful } from "../src/api.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "mindful-journals-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function ids(facetOrder: unknown): string[] {
  return (facetOrder as { order: string[] }).order;
}

describe("Mindful — journals", () => {
  it("creates an empty journal that validates as a list", () => {
    const m = new Mindful(root);
    const j = m.createJournal({ title: "2026" });
    expect(j.kind).toBe("journal");
    expect(j.id).toBe("journal:2026");
    expect(ids(j.facets.order)).toEqual([]);
  });

  it("append adds to members AND order together", () => {
    const m = new Mindful(root);
    const a = m.capture({ title: "A" });
    const b = m.capture({ title: "B" });
    const j = m.createJournal({ title: "log" });
    m.append(j.id, a.id);
    const after = m.append(j.id, b.id);
    expect((after.facets.membership as { members: string[] }).members.sort()).toEqual([a.id, b.id].sort());
    expect(ids(after.facets.order)).toEqual([a.id, b.id]); // insertion order
  });

  it("reorder accepts a permutation of members", () => {
    const m = new Mindful(root);
    const a = m.capture({ title: "A" });
    const b = m.capture({ title: "B" });
    const j = m.createJournal({ title: "log" });
    m.append(j.id, a.id);
    m.append(j.id, b.id);
    const reordered = m.reorder(j.id, [b.id, a.id]);
    expect(ids(reordered.facets.order)).toEqual([b.id, a.id]);
  });

  it("reorder rejects a non-permutation (kernel invariant)", () => {
    const m = new Mindful(root);
    const a = m.capture({ title: "A" });
    const b = m.capture({ title: "B" });
    const j = m.createJournal({ title: "log" });
    m.append(j.id, a.id);
    m.append(j.id, b.id);
    expect(() => m.reorder(j.id, [a.id])).toThrow(InvariantError); // missing b
  });

  it("append rejects a missing thought id (fail early, no dangling order entry)", () => {
    const m = new Mindful(root);
    const j = m.createJournal({ title: "log" });
    expect(() => m.append(j.id, "thought:does-not-exist")).toThrow(RefError);
    expect(ids(m.get(j.id).facets.order)).toEqual([]);
  });

  it("remove drops the entry from members AND order", () => {
    const m = new Mindful(root);
    const a = m.capture({ title: "A" });
    const b = m.capture({ title: "B" });
    const j = m.createJournal({ title: "log" });
    m.append(j.id, a.id);
    m.append(j.id, b.id);
    const after = m.remove(j.id, a.id);
    expect((after.facets.membership as { members: string[] }).members).toEqual([b.id]);
    expect(ids(after.facets.order)).toEqual([b.id]);
  });

  it("on-disk round-trip: a fresh Mindful over the same root sees the journal", () => {
    const m = new Mindful(root);
    const a = m.capture({ title: "A" });
    const j = m.createJournal({ title: "log" });
    m.append(j.id, a.id);
    const reopened = new Mindful(root);
    expect(ids(reopened.get(j.id).facets.order)).toEqual([a.id]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/mindful-journals.test.ts`
Expected: FAIL — journal methods are not defined.

- [ ] **Step 3: Extend `src/api.ts`**

Add to the `@nodes/kernel` import: `ORDER`, `orderOf`. Add `JOURNAL` to the `./kinds.js` import. Add these methods to the `Mindful` class (`append` reuses the `requireThought` helper added in Task 5):

```ts
  // --- journals (list form facet) ---

  createJournal(input: { title: string }): Node {
    const node = makeNode({
      id: `${JOURNAL}:${slugify(input.title)}`,
      kind: JOURNAL,
      title: input.title,
      facets: { [MEMBERSHIP]: { members: [] }, [ORDER]: { order: [] } },
    });
    this.corpus.add(node);
    return this.corpus.get(node.id);
  }

  append(journalId: string, thoughtId: string): Node {
    const j = this.corpus.get(journalId);
    this.requireThought(thoughtId); // fail early: no dangling order/member entry (helper from Task 5)
    const members = membershipOf(j).members;
    if (!members.includes(thoughtId)) {
      j.facets[MEMBERSHIP] = { members: [...members, thoughtId] };
      j.facets[ORDER] = { order: [...orderOf(j).order, thoughtId] };
      this.corpus.add(j);
    }
    return this.corpus.get(journalId);
  }

  reorder(journalId: string, order: string[]): Node {
    const j = this.corpus.get(journalId);
    j.facets[ORDER] = { order };
    this.corpus.add(j); // requireOrderIsPermutation fails early if `order` is not a permutation of members
    return this.corpus.get(journalId);
  }

  remove(journalId: string, thoughtId: string): Node {
    const j = this.corpus.get(journalId);
    j.facets[MEMBERSHIP] = { members: membershipOf(j).members.filter((m) => m !== thoughtId) };
    j.facets[ORDER] = { order: orderOf(j).order.filter((m) => m !== thoughtId) };
    this.corpus.add(j);
    return this.corpus.get(journalId);
  }
```

- [ ] **Step 4: Run the test, then the gate**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/mindful-journals.test.ts`
Expected: PASS.
Run: `rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green (all mindful test files).

- [ ] **Step 5: Commit**

```bash
cd ~/d/mindful/v6 && rtk git add src/api.ts tests/mindful-journals.test.ts
rtk git commit -m "feat: Mindful journals — append/reorder/remove over the list order facet"
```

---

## Final Verification (whole-plan)

- **Kernel (`~/d/nodes/ts`):** `rtk npm run build` emits `dist/`; `rtk npm test` (286) + `rtk npm run typecheck` + `rtk npm run check` green.
- **Mindful (`~/d/mindful/v6`):** `rtk npm test` (all 5 test files) + `rtk npm run typecheck` + `rtk npm run check` green.

Key invariants to confirm by inspection after the gates are green:
- `Mindful` never hands callers a raw `membership`/`edges`/`order` to build — every structural mutation goes through a method that maintains the facet and is validated by `Corpus.add`.
- A mindmap's edges are read via `mindmapEdges`/the node, NEVER surfaced by `related` (which is the global relation graph from tags). The mindmaps test asserts `related(a.id) === []` after an internal `link`.
- A journal's order lives in the `order` facet and is a permutation of members; `reorder` with a non-permutation fails early (`InvariantError`).
- Tags fail early (`RefError`) on an unresolved name and (`ValidationError`) on a title shared by multiple thoughts — never a silent arbitrary match; `similar*` fail early (`EmbedderRequiredError`) without an embedder.
- `capture` is atomic: tags resolve before the single `corpus.add`, so an unresolved/ambiguous tag persists nothing (`allThoughts()` stays empty).
- `addThought`/`append` reject a missing or non-thought id (`RefError`/`ValidationError`) before mutating membership — no dangling structural members.
- On-disk round-trip works through the package API (a fresh `Mindful` over the same root sees prior state).

## Deferred (per spec §7)

- **SP2:** the `visualIdentity` facet and identity-derivation (`thought = note + VisualIdentity`).
- **SP3:** renderer (2D art/animation) + CLI/TUI shell; natural-systems formula-viz.
- Tag auto-creation + a `topic` kind; thought-id slugs derived from titles (SP1 mints `thought:<uid>` — unique, collision-free); publishing `@nodes/kernel` to a registry; multi-shape kinds; additional shapes.
