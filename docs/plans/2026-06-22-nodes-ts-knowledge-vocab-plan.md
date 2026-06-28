# TypeScript Knowledge Vocab Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the Python `nodes.vocab` knowledge-vocab layer to TypeScript — a separately-importable profile of seven knowledge kinds (`source`/`kinds`/`predicates`) layered on the domain-free kernel — reaching parity with the current Python vocab.

**Architecture:** A new `ts/src/vocab/` directory (depends only on the kernel modules; the kernel never imports it) with three modules — `source.ts` (the shared bibliographic facet), `kinds.ts` (kind constants + `registerKnowledgeVocab`), `predicates.ts` (canonical predicate names + helper constructors) — plus a vocab-only barrel `ts/src/vocab/index.ts`. No kernel change is needed: the TS `Corpus` already accepts an optional `registry` and validates on `add`/`rename`. Faithful logic mirror of the current Python `nodes/vocab/{source,kinds,predicates}.py`.

**Tech Stack:** TypeScript (strict, ES2022, NodeNext ESM), Zod, Vitest, Biome.

**Reference (read before starting):** the spec is `docs/format.md` §"Knowledge vocab (Plan 3)" (the roster, the `Source` facet, the predicates, the enforcement contract). The oracle this mirrors is the Python source `~/d/nodes/python/src/nodes/vocab/{source,kinds,predicates,__init__}.py` and its tests `~/d/nodes/python/tests/test_vocab_{source,kinds,predicates,exports}.py`. The kernel surface the port consumes lives in `~/d/nodes/ts/src/{errors,node,registry,relations,corpus}.ts`.

## Current State Note

This plan has since been implemented and remains useful as the historical TypeScript knowledge-vocab rollout. The current TS vocab layer lives under `ts/src/vocab/`, remains separately importable from the kernel, and mirrors the Python `nodes.vocab` roster, `Source` facet, predicate constants, and registry-backed validation contract.

There are three current-code details to keep in mind when reading the task snippets below:

- Later plans added structural shapes, full-text search, similarity, and snapshot persistence to the TypeScript kernel. Current `Corpus(root, registry?, embedder?)` has a larger construction and mutation path than this vocab-only plan needed.
- The "no kernel code" constraint was correct for this plan's scope. Do not infer from it that the current kernel has not changed since; it now includes search, similarity, ranking, and snapshot modules.
- The `docs/format.md` and `ts/README.md` edits in Task 5 have already been applied and later extended by subsequent plans.

## Global Constraints

Every task's requirements implicitly include this section.

- **Runtime/tooling (already in place; this plan adds NO dependencies):** ESM (`"type":"module"`); TypeScript `strict`, ES2022, **NodeNext** module resolution — all relative imports use a `.js` extension on `.ts` sources; Node `engines >=20`; npm; `packageManager npm@11.11.0`.
- **Dependencies:** Zod (validation), Vitest (tests), Biome (lint/format). No new dependencies.
- **Layering:** `ts/src/vocab/*` imports only from the kernel modules (`../errors.js`, `../node.js`, `../registry.js`, `../relations.js`, `../corpus.js`) + Zod. **The kernel never imports vocab** — do NOT add any vocab export to the kernel barrel `ts/src/index.ts`. The vocab layer has its own barrel `ts/src/vocab/index.ts`.
- **Error contract:** Reuse the existing `./errors.js` hierarchy — **no new error types**. `sourceOf` raises `FacetError` on a missing or malformed `source` facet; `requireIdentifiableSource` raises `InvariantError` on an empty source. A raw `ZodError` must never escape `sourceOf` (catch-and-rewrap, exactly as `membershipOf` does in `shapes.ts`).
- **`Source` strictness:** the `Source` Zod schema is `.strict()` — unknown keys (typos like `identifer`) fail, never silently dropped. This is the parity analog of Pydantic's `ConfigDict(extra="forbid")`.
- **`Source.year` coercion parity:** follow Pydantic's current `int | None` behavior for normal JSON/YAML inputs: quoted numeric years like `"2026"` and integral floats like `2026.0` normalize to `2026`; non-numeric strings and non-integral numbers fail. Do not use broad `z.coerce.number()` because it would accept values Python rejects, such as `""`.
- **Roster (exactly seven kinds):** prose `note`, `idea`, `question`, `topic` (bare — no required facets); source `paper`, `book`, `dataset` (require the `source` facet + the `requireIdentifiableSource` invariant).
- **Predicate constants and values:** `ABOUT="about"`, `CITES="cites"`, `ANSWERS="answers"`, `ASKS="asks"`, `REFINES="refines"`. Predicates are a shared vocabulary only — free-string, never enforced by the kernel.
- **Naming:** Python `snake_case` becomes TS `camelCase` at the API: `source_of`→`sourceOf`, `require_identifiable_source`→`requireIdentifiableSource`, `register_knowledge_vocab`→`registerKnowledgeVocab`. Kind/predicate string *values* are unchanged (`"note"`, `"about"`, …). Constant identifiers stay `SCREAMING_SNAKE` (`SOURCE`, `PROSE_KINDS`, `ABOUT`).
- **`Corpus` is unchanged:** it already takes `registry?` and validates on `add`/`rename` (`ts/src/corpus.ts:46,65,146`). This plan adds NO kernel code — only the `vocab/` module, its tests, and docs.
- **Faithful port:** mirror the current Python `nodes.vocab` semantics exactly, including the truthiness of `requireIdentifiableSource`'s "at least one of" check.
- **No compatibility layers / no "Unified" prefixes / no "legacy" shims.**
- **Commands:** `rtk` prefixes `git`/`npm`/`npx`/`uv`/`node`; shell builtins (`cd`) and filesystem primitives (`mkdir`) are shown bare; one command per line (no `&&` chains).
- **Docs/code paths** use `~/d/` (never `/home/keith/d/` or `/mnt/ssd/Dropbox/`). No `Co-Authored-By` trailers in commits.

---

### Task 1: `Source` facet (`vocab/source.ts`)

**Files:**
- Create: `ts/src/vocab/source.ts`
- Create: `ts/tests/vocab-source.test.ts`

**Interfaces:**
- Consumes: `FacetError`, `InvariantError` (`../errors.js`); `type Node` (`../node.js`); `z` (`zod`).
- Produces: `SOURCE = "source"`; `SourceSchema` (Zod, `.strict()`); `type Source`; `sourceOf(node: Node): Source` (raises `FacetError` on missing/malformed); `requireIdentifiableSource(node: Node): void` (raises `InvariantError` on empty source). Consumed by Task 2.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/vocab-source.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { FacetError, InvariantError } from "../src/errors.js";
import { type Node, makeNode } from "../src/node.js";
import { SOURCE, type Source, requireIdentifiableSource, sourceOf } from "../src/vocab/source.js";

function paper(source: Record<string, unknown> | null): Node {
  const facets = source === null ? {} : { [SOURCE]: source };
  return makeNode({ id: "paper:x", kind: "paper", title: "X", facets });
}

describe("Source facet", () => {
  it("parses defaults from an empty payload", () => {
    const s: Source = sourceOf(paper({}));
    expect(s.authors).toEqual([]);
    expect(s.year).toBeNull();
    expect(s.container).toBeNull();
    expect(s.identifier).toBeNull();
    expect(s.url).toBeNull();
  });

  it("raises FacetError when the source facet is missing", () => {
    expect(() => sourceOf(paper(null))).toThrow(FacetError);
  });

  it("raises FacetError on an unknown key (typo)", () => {
    expect(() => sourceOf(paper({ identifer: "10.1/x" }))).toThrow(FacetError);
  });

  it("raises FacetError on a wrong-typed field", () => {
    expect(() => sourceOf(paper({ year: "soon" }))).toThrow(FacetError);
  });

  it("never leaks a raw ZodError", () => {
    try {
      sourceOf(paper({ year: "soon" }));
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(FacetError);
      expect((e as Error).constructor.name).toBe("FacetError");
    }
  });

  it("rejects an empty source via requireIdentifiableSource", () => {
    expect(() => requireIdentifiableSource(paper({}))).toThrow(InvariantError);
  });

  it("accepts a source with one identifying field", () => {
    requireIdentifiableSource(paper({ year: 2026 })); // no throw
  });

  it("normalizes quoted numeric years like Python/Pydantic", () => {
    expect(sourceOf(paper({ year: "2026" })).year).toBe(2026);
    expect(sourceOf(paper({ year: 2026.0 })).year).toBe(2026);
  });

  it("roundtrips a populated source through the facet", () => {
    const s = sourceOf(paper({ authors: ["A. Author"], year: 2026, identifier: "10.1/x" }));
    expect(s.authors).toEqual(["A. Author"]);
    expect(s.year).toBe(2026);
    expect(s.identifier).toBe("10.1/x");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd ~/d/nodes/ts
rtk npm test -- vocab-source
```

Expected: FAIL — cannot resolve `../src/vocab/source.js`.

- [ ] **Step 3: Write the implementation**

Create `ts/src/vocab/source.ts`:

```typescript
import { z } from "zod";
import { FacetError, InvariantError } from "../errors.js";
import type { Node } from "../node.js";

export const SOURCE = "source";

const SourceYearSchema = z.preprocess((value) => {
  if (typeof value === "string" && value.trim() !== "") return Number(value);
  return value;
}, z.number().int().nullable().default(null));

/** Shared bibliographic facet for paper / book / dataset kinds. `.strict()` mirrors
 *  Pydantic's `extra="forbid"`: unknown keys (typos) fail, never silently dropped. */
export const SourceSchema = z
  .object({
    authors: z.array(z.string()).default([]),
    year: SourceYearSchema,
    container: z.string().nullable().default(null), // journal / publisher / repository
    identifier: z.string().nullable().default(null), // DOI / ISBN / accession id
    url: z.string().nullable().default(null),
  })
  .strict();

export type Source = z.infer<typeof SourceSchema>;

export function sourceOf(node: Node): Source {
  const raw = node.facets[SOURCE];
  if (raw === undefined) {
    throw new FacetError(`${node.id}: missing '${SOURCE}' facet`);
  }
  try {
    return SourceSchema.parse(raw);
  } catch (e) {
    if (e instanceof z.ZodError) {
      throw new FacetError(`${node.id}: invalid '${SOURCE}' facet: ${e.issues.map((i) => i.message).join("; ")}`);
    }
    throw e;
  }
}

export function requireIdentifiableSource(node: Node): void {
  const s = sourceOf(node);
  // Faithful to Python's `if not (s.authors or s.year or s.identifier or s.url)`:
  // truthiness, so an empty author list / year 0 / "" identifier counts as absent.
  if (!(s.authors.length || s.year || s.identifier || s.url)) {
    throw new InvariantError(`${node.id}: source facet needs at least one of authors/year/identifier/url`);
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd ~/d/nodes/ts
rtk npm test -- vocab-source
```

Expected: PASS.

- [ ] **Step 5: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/vocab/source.ts ts/tests/vocab-source.test.ts
rtk git commit -m "feat(ts): vocab Source facet (sourceOf + requireIdentifiableSource)"
```

---

### Task 2: Knowledge kinds (`vocab/kinds.ts`)

**Files:**
- Create: `ts/src/vocab/kinds.ts`
- Create: `ts/tests/vocab-kinds.test.ts`

**Interfaces:**
- Consumes: `type Registry` (`../registry.js`); `SOURCE`, `requireIdentifiableSource` (`./source.js`).
- Produces: kind-name constants `NOTE`/`IDEA`/`QUESTION`/`TOPIC`/`PAPER`/`BOOK`/`DATASET`; `PROSE_KINDS` (`[note,idea,question,topic]`); `SOURCE_KINDS` (`[paper,book,dataset]`); `registerKnowledgeVocab(reg: Registry): void`. Consumed by Task 4.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/vocab-kinds.test.ts`:

```typescript
import { beforeEach, describe, expect, it } from "vitest";
import { FacetError, InvariantError, UnknownKindError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import { PROSE_KINDS, SOURCE_KINDS, registerKnowledgeVocab } from "../src/vocab/kinds.js";
import { SOURCE } from "../src/vocab/source.js";

let reg: Registry;
beforeEach(() => {
  reg = new Registry();
  registerKnowledgeVocab(reg);
});

describe("knowledge vocab kinds", () => {
  it("registers all seven kinds", () => {
    for (const name of [...PROSE_KINDS, ...SOURCE_KINDS]) {
      expect(reg.isRegistered(name)).toBe(true);
    }
  });

  it("validates a bare note", () => {
    reg.validate(makeNode({ id: "note:a", kind: "note", title: "A" })); // no throw
  });

  it("rejects a note carrying a stray facet", () => {
    expect(() => reg.validate(makeNode({ id: "note:a", kind: "note", title: "A", facets: { [SOURCE]: { year: 2026 } } }))).toThrow(FacetError);
  });

  it("rejects a paper missing the source facet", () => {
    expect(() => reg.validate(makeNode({ id: "paper:a", kind: "paper", title: "A" }))).toThrow(FacetError);
  });

  it("rejects a paper with an empty source facet", () => {
    expect(() => reg.validate(makeNode({ id: "paper:a", kind: "paper", title: "A", facets: { [SOURCE]: {} } }))).toThrow(InvariantError);
  });

  it("accepts a paper with a valid source facet", () => {
    reg.validate(makeNode({ id: "paper:a", kind: "paper", title: "A", facets: { [SOURCE]: { year: 2026 } } })); // no throw
  });

  it("book and dataset share the source invariant", () => {
    for (const kind of ["book", "dataset"]) {
      expect(() => reg.validate(makeNode({ id: `${kind}:a`, kind, title: "A", facets: { [SOURCE]: {} } }))).toThrow(InvariantError);
      reg.validate(makeNode({ id: `${kind}:b`, kind, title: "B", facets: { [SOURCE]: { identifier: "x" } } })); // no throw
    }
  });

  it("an empty registry rejects an unregistered kind", () => {
    const empty = new Registry();
    expect(() => empty.validate(makeNode({ id: "note:a", kind: "note", title: "A" }))).toThrow(UnknownKindError);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd ~/d/nodes/ts
rtk npm test -- vocab-kinds
```

Expected: FAIL — cannot resolve `../src/vocab/kinds.js`.

- [ ] **Step 3: Write the implementation**

Create `ts/src/vocab/kinds.ts`:

```typescript
import type { Registry } from "../registry.js";
import { SOURCE, requireIdentifiableSource } from "./source.js";

export const NOTE = "note";
export const IDEA = "idea";
export const QUESTION = "question";
export const TOPIC = "topic";
export const PAPER = "paper";
export const BOOK = "book";
export const DATASET = "dataset";

export const PROSE_KINDS = [NOTE, IDEA, QUESTION, TOPIC] as const;
export const SOURCE_KINDS = [PAPER, BOOK, DATASET] as const;

/** Register the standard knowledge-vocab kinds onto `reg`.
 *  Mirrors `registerBuiltinShapes` in `shapes.ts`. */
export function registerKnowledgeVocab(reg: Registry): void {
  for (const name of PROSE_KINDS) {
    reg.register({ name });
  }
  for (const name of SOURCE_KINDS) {
    reg.register({ name, requiredFacets: new Set([SOURCE]), invariants: [requireIdentifiableSource] });
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd ~/d/nodes/ts
rtk npm test -- vocab-kinds
```

Expected: PASS.

- [ ] **Step 5: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/vocab/kinds.ts ts/tests/vocab-kinds.test.ts
rtk git commit -m "feat(ts): vocab knowledge kinds + registerKnowledgeVocab"
```

---

### Task 3: Predicates (`vocab/predicates.ts`)

**Files:**
- Create: `ts/src/vocab/predicates.ts`
- Create: `ts/tests/vocab-predicates.test.ts`

**Interfaces:**
- Consumes: `type Relation`, `RelationSchema` (`../relations.js`).
- Produces: predicate constants `ABOUT`/`CITES`/`ANSWERS`/`ASKS`/`REFINES`; helper constructors `about`/`cites`/`answers`/`asks`/`refines`, each `(source: string, target: string) => Relation`. Consumed (as a namespace) by Task 4.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/vocab-predicates.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import type { Relation } from "../src/relations.js";
import { ABOUT, ANSWERS, ASKS, CITES, REFINES, about, answers, asks, cites, refines } from "../src/vocab/predicates.js";

describe("vocab predicates", () => {
  it("exposes the canonical constant values", () => {
    expect(ABOUT).toBe("about");
    expect(CITES).toBe("cites");
    expect(ANSWERS).toBe("answers");
    expect(ASKS).toBe("asks");
    expect(REFINES).toBe("refines");
  });

  it("helper constructors build directed relations with the right predicate", () => {
    const cases: [(s: string, t: string) => Relation, string][] = [
      [about, ABOUT],
      [cites, CITES],
      [answers, ANSWERS],
      [asks, ASKS],
      [refines, REFINES],
    ];
    for (const [fn, predicate] of cases) {
      const rel = fn("note:a", "topic:b");
      expect(rel.source).toBe("note:a");
      expect(rel.target).toBe("topic:b");
      expect(rel.predicate).toBe(predicate);
      expect(rel.directed).toBe(true);
    }
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd ~/d/nodes/ts
rtk npm test -- vocab-predicates
```

Expected: FAIL — cannot resolve `../src/vocab/predicates.js`.

- [ ] **Step 3: Write the implementation**

Create `ts/src/vocab/predicates.ts`:

```typescript
import { type Relation, RelationSchema } from "../relations.js";

export const ABOUT = "about"; // any node -> topic
export const CITES = "cites"; // any node -> paper/book/dataset
export const ANSWERS = "answers"; // note/idea -> question
export const ASKS = "asks"; // any node -> question (raises one)
export const REFINES = "refines"; // any node -> node (builds on / supersedes)

/** `source` is about `target` (a topic). */
export function about(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: ABOUT, target });
}

/** `source` cites `target` (a paper/book/dataset). */
export function cites(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: CITES, target });
}

/** `source` (a note/idea) answers `target` (a question). */
export function answers(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: ANSWERS, target });
}

/** `source` raises `target` (a question). */
export function asks(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: ASKS, target });
}

/** `source` refines / supersedes `target`. */
export function refines(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: REFINES, target });
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd ~/d/nodes/ts
rtk npm test -- vocab-predicates
```

Expected: PASS.

- [ ] **Step 5: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/vocab/predicates.ts ts/tests/vocab-predicates.test.ts
rtk git commit -m "feat(ts): vocab predicates (constants + relation constructors)"
```

---

### Task 4: Vocab barrel + exports test + Corpus integration test

Current-code note: `Corpus(root, registry?)` in this task is the historical surface at the time of the vocab port. Current construction is `Corpus(root, registry?, embedder?)` and may load/reconcile snapshots while still honoring the same registry-validation behavior.

**Files:**
- Create: `ts/src/vocab/index.ts`
- Create: `ts/tests/vocab-exports.test.ts`
- Create: `ts/tests/vocab-corpus.test.ts`

**Interfaces:**
- Consumes: every `vocab/*` module's public surface (Tasks 1–3); `Corpus` (`../src/corpus.js`); `Registry` (`../src/registry.js`).
- Produces: the vocab barrel `ts/src/vocab/index.ts` re-exporting the `source`/`kinds` surface and the `predicates` namespace. Confirms the layer is reachable as one import, and that a vocab-registered `Corpus` enforces the roster on `add`/`rename` (semantic parity with Python's `test_corpus_registry.py`, exercised through the knowledge vocab).

- [ ] **Step 1: Write the barrel**

Create `ts/src/vocab/index.ts`:

```typescript
export {
  SOURCE,
  SourceSchema,
  type Source,
  requireIdentifiableSource,
  sourceOf,
} from "./source.js";
export {
  BOOK,
  DATASET,
  IDEA,
  NOTE,
  PAPER,
  PROSE_KINDS,
  QUESTION,
  SOURCE_KINDS,
  TOPIC,
  registerKnowledgeVocab,
} from "./kinds.js";
export * as predicates from "./predicates.js";
```

- [ ] **Step 2: Write the exports test**

Create `ts/tests/vocab-exports.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { NOTE, PAPER, SOURCE, registerKnowledgeVocab, sourceOf } from "../src/vocab/index.js";
import * as vocab from "../src/vocab/index.js";

describe("vocab barrel", () => {
  it("re-exports the public surface", () => {
    expect(typeof registerKnowledgeVocab).toBe("function");
    expect(typeof sourceOf).toBe("function");
    expect(NOTE).toBe("note");
    expect(PAPER).toBe("paper");
    expect(SOURCE).toBe("source");
  });

  it("exposes the predicates namespace", () => {
    expect(vocab.predicates.CITES).toBe("cites");
    expect(typeof vocab.predicates.cites).toBe("function");
  });
});
```

- [ ] **Step 3: Write the Corpus integration test**

Create `ts/tests/vocab-corpus.test.ts`:

```typescript
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { FacetError, InvariantError, RefError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import { SOURCE, registerKnowledgeVocab } from "../src/vocab/index.js";

function knowledgeRegistry(): Registry {
  const reg = new Registry();
  registerKnowledgeVocab(reg);
  return reg;
}

let root: string;
let corpus: Corpus;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-vocab-corpus-"));
  corpus = new Corpus(root, knowledgeRegistry());
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("Corpus with the knowledge vocab registry", () => {
  it("adds a bare note", () => {
    corpus.add(makeNode({ id: "note:a", kind: "note", title: "A" })); // no throw
    expect(corpus.get("note:a").title).toBe("A");
  });

  it("rejects a paper with an empty source before any disk write", () => {
    expect(() => corpus.add(makeNode({ id: "paper:a", kind: "paper", title: "A", facets: { [SOURCE]: {} } }))).toThrow(InvariantError);
    expect(() => corpus.get("paper:a")).toThrow(); // never written
  });

  it("rejects a paper with a stray-keyed source", () => {
    expect(() => corpus.add(makeNode({ id: "paper:b", kind: "paper", title: "B", facets: { [SOURCE]: { identifer: "x" } } }))).toThrow(FacetError);
  });

  it("adds a valid paper and keeps it valid across a rename", () => {
    corpus.add(makeNode({ id: "paper:c", kind: "paper", title: "C", facets: { [SOURCE]: { year: 2026 } } }));
    corpus.rename("paper:c", "paper:c2");
    expect(corpus.get("paper:c2").title).toBe("C");
    expect(corpus.get("paper:c").id).toBe("paper:c2"); // deprecated id still resolves
  });

  it("rejects a rename that would make the renamed node invalid before any disk write", () => {
    corpus.add(makeNode({ id: "paper:a", kind: "paper", title: "A", facets: { [SOURCE]: { year: 2026 } } }));
    expect(() => corpus.rename("paper:a", "note:a")).toThrow(FacetError);
    expect(corpus.get("paper:a").title).toBe("A");
    expect(() => corpus.get("note:a")).toThrow(RefError);
  });

  it("rejects a rename blocked by an invalid referrer before writing anything", () => {
    const seed = new Corpus(root); // no registry: permits seeding an invalid referrer
    seed.add(makeNode({ id: "topic:t", kind: "topic", title: "T" }));
    seed.add(
      makeNode({
        id: "paper:bad",
        kind: "paper",
        title: "Bad",
        facets: { [SOURCE]: {} },
        relations: [{ source: "paper:bad", predicate: "about", target: "topic:t" }],
      }),
    );

    const c = new Corpus(root, knowledgeRegistry());
    expect(() => c.rename("topic:t", "topic:t2")).toThrow(InvariantError);

    const fresh = new Corpus(root);
    expect(fresh.get("topic:t").title).toBe("T");
    expect(() => fresh.get("topic:t2")).toThrow(RefError);
    expect(fresh.get("paper:bad").relations[0]?.target).toBe("topic:t");
  });
});
```

- [ ] **Step 4: Run the new tests**

```bash
cd ~/d/nodes/ts
rtk npm test -- vocab-exports vocab-corpus
```

Expected: PASS.

- [ ] **Step 5: Run the full gate**

```bash
cd ~/d/nodes/ts
rtk npm test
rtk npm run typecheck
rtk npx biome check --write .
rtk npm run check
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/vocab/index.ts ts/tests/vocab-exports.test.ts ts/tests/vocab-corpus.test.ts
rtk git commit -m "feat(ts): vocab barrel + exports + Corpus-vocab integration test"
```

---

### Task 5: Docs

**Files:**
- Modify: `ts/README.md` (scope: knowledge vocab now ported)
- Modify: `docs/format.md` (note the TS vocab layer; fix the stale "not yet ported" sentence)

**Interfaces:**
- Consumes: nothing (docs only).
- Produces: docs reflecting that the TypeScript knowledge vocab is ported as a separate `ts/src/vocab/` layer.

- [ ] **Step 1: Update `ts/README.md`**

In `ts/README.md`, find the `## Scope` section's closing sentence (it currently lists the knowledge vocab among "later TypeScript plans") and replace the trailing clause so it reads:

```markdown
There is **no full-text search, no embeddings, no on-disk index persistence, and no
membership-graph traversal** — those are later TypeScript plans. The knowledge vocab
(`ts/src/vocab/` — `note`/`idea`/`question`/`topic`/`paper`/`book`/`dataset`, the `Source`
facet, and the predicate vocabulary) is ported as a separate layer that imports only from the
kernel; register it onto a `Registry` with `registerKnowledgeVocab(reg)`.
```

(If the existing wording differs, preserve the surrounding scope text and only swap the "knowledge vocab … later plans" clause for the text above.)

- [ ] **Step 2: Update `docs/format.md`**

In `docs/format.md`, in the "## TypeScript kernel (Plan 4)" section, change the final sentence that reads "The knowledge vocab is not yet ported." to:

```markdown
The knowledge vocab is ported too — see "TypeScript knowledge vocab" below.
```

Then append a new section at the end of the file:

```markdown
## TypeScript knowledge vocab

`ts/src/vocab/` mirrors the Python `nodes.vocab` layer (see "Knowledge vocab (Plan 3)" above):
the same seven kinds, the same `Source` facet, and the same predicate vocabulary. It imports only
from the kernel modules; the kernel never imports it, and it is **not** part of the kernel barrel
(`ts/src/index.ts`) — import it from `ts/src/vocab/index.ts`.

- **Source facet.** `SourceSchema` is a Zod `.strict()` object (`authors`, `year`, `container`,
  `identifier`, `url`); `.strict()` is the parity analog of Pydantic's `extra="forbid"` — unknown
  keys fail. `sourceOf(node)` raises `FacetError` on a missing or malformed facet (never a raw
  `ZodError`); `requireIdentifiableSource(node)` raises `InvariantError` on an empty source.
- **Kinds.** `registerKnowledgeVocab(reg)` registers prose kinds (`note`/`idea`/`question`/`topic`)
  bare and source kinds (`paper`/`book`/`dataset`) with the `source` facet + identifiability
  invariant — mirroring `registerBuiltinShapes`.
- **Predicates.** `ABOUT`/`CITES`/`ANSWERS`/`ASKS`/`REFINES` constants plus helper constructors,
  exposed as the `predicates` namespace. Free-string only; never enforced by the kernel.
- **Enforcement.** `new Corpus(root, reg)` with a vocab-registered `Registry` validates on `add`
  and `rename` before any disk write — same fail-early contract as the Python `Corpus`.
```

- [ ] **Step 3: Verify the docs build/read cleanly (no code gate needed)**

Re-read both edited sections to confirm there is no remaining "not yet ported" / contradictory wording.

- [ ] **Step 4: Commit**

```bash
cd ~/d/nodes
rtk git add ts/README.md docs/format.md
rtk git commit -m "docs: TypeScript knowledge vocab ported"
```

---

## Self-Review

**1. Spec coverage** (`docs/format.md` §"Knowledge vocab (Plan 3)" + Python oracle):
- Roster of 7 kinds; prose bare; source kinds require `source` facet + identifiability invariant → Task 2 ✅
- `Source` facet fields + `extra="forbid"` (→ `.strict()`) + at-least-one invariant → Task 1 ✅
- `Source.year` Pydantic-compatible normalization for quoted numeric years / integral floats, without broad JS coercion → Task 1 ✅
- Predicates (`about`/`cites`/`answers`/`asks`/`refines`) as a shared free-string vocab → Task 3 ✅
- Separately-importable, kernel-never-imports-vocab layering; own barrel → Tasks 1–4 + Global Constraints ✅
- Enforcement via `Corpus(root, registry)` on `add`/`rename`, including rename-invalid-node and invalid-referrer no-write cases → Task 4 integration test (kernel already wired) ✅
- Error contract: `FacetError`/`InvariantError`/`UnknownKindError` only; no raw ZodError escapes → Tasks 1–2 ✅
- Docs reflect the new layer → Task 5 ✅

**2. Placeholder scan:** No "TBD"/"handle errors"/"similar to Task N". Every code step contains the full file or test contents. Task 5's doc edits give exact replacement prose and the locating sentence.

**3. Type consistency:** `SOURCE`/`Source`/`sourceOf`/`requireIdentifiableSource` consistent across Tasks 1, 2, 4. `registerKnowledgeVocab(reg: Registry)` consistent across Tasks 2, 4, and the docs. `PROSE_KINDS`/`SOURCE_KINDS` are `as const` tuples — iterating them in tests and in `registerKnowledgeVocab` is type-safe; `reg.register({ name })` matches the existing `KindSpec` shape in `registry.ts`. Predicate constructors are `(string, string) => Relation`, matching `relatesTo` in `relations.ts`. The Corpus integration test uses the real `Corpus(root, registry)` constructor (`corpus.ts:46`) and `registerKnowledgeVocab` (TS has it) — no reference to the unported anything.
