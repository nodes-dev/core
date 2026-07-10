# Similarity / Embedding Index (TypeScript port) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the Python embedding/similarity subsystem (cosine-similarity derived index) to the TypeScript kernel at semantic parity, pinned by the already-committed cross-language fixtures.

**Architecture:** A new `ts/src/similarity.ts` module mirroring `python/src/nodes/kernel/similarity.py`: an `Embedder` seam (the kernel ships no model), `embedText`, a content-addressed on-disk `VectorCache` of raw embedder output, and an in-memory `VectorIndex` holding L2-normalized vectors with exact brute-force cosine ranking. `Corpus` gains an **opt-in** `vectorIndex` (built only when an embedder is supplied) beside its structural `Index` and `SearchIndex`, kept current on `add`/`delete`/`rename` with the same fail-before-mutation ordering as Python. The shared `scoreKey` ranking key is first extracted out of `search.ts` into a new `ranking.ts` (so neither derived-index facet imports the other), mirroring the Python `ranking.py` extraction.

**Tech Stack:** TypeScript (ESM, `.js` import extensions), Node ≥20, vitest, biome (format + lint, line width 120), `tsc --noEmit` typecheck. No new runtime dependencies — `similarity.ts` uses only Node built-ins (`node:crypto` `createHash`, `node:fs`, `node:path`, `Math`).

## Current State Note

This plan has since been implemented and remains useful as the historical TypeScript similarity-index port. Current `ts/src/similarity.ts` owns the embedder seam, raw vector cache, normalized in-memory `VectorIndex`, exact cosine ranking, and `SimilarHit`; current `ts/src/ranking.ts` owns the shared `scoreKey`.

There are three current-code details to keep in mind when reading the task snippets below:

- Later snapshot persistence added `VectorIndex.toDict()` / `fromDict()` and snapshot namespace/dimension validation. Current `Corpus` construction may load/reconcile persisted normalized vectors.
- The `scoreKey` extraction described in Task 1 is already complete, so older search-plan snippets that import it from `search.ts` are historical.
- The `docs/STANDARD.md` update in Task 7 has already been applied and later extended with snapshot persistence sections.

## Global Constraints

These bind every task. Values are copied verbatim from the spec (`docs/designs/2026-06-22-nodes-similarity-index-design.md`) and the committed Python implementation (`python/src/nodes/kernel/similarity.py`, `ranking.py`, `corpus.py`).

- **The seam.** The kernel ships **no** concrete embedder. `Embedder` is an interface with a `readonly cacheNamespace: string` and `embed(texts: string[]): Vector[]`. `Vector = number[]`. Vectors are treated as immutable by convention.
- **`embedText` (frozen contract):** one vector per node from ``embedText(node) = `${node.title}\n\n${node.body}` `` — title and body joined by exactly one blank line. This is the cache-key text and the parity contract; do not alter it.
- **Cache key:** `textHash(text) = sha256(text)` as a 64-char lowercase hex digest (`createHash("sha256").update(text, "utf-8").digest("hex")`).
- **Content-addressed cache layout:** `<root>/.nodes-index/vectors/<namespace>/<textHash>.json`, git-ignored (the `.nodes-index/` ignore already exists), disposable. Stores **raw** (un-normalized) embedder output as `{"dim": N, "vector": [...]}`. Writes are atomic: write `<path>.tmp` then `renameSync` over `<path>`. `validateFinite` runs before `JSON.stringify` so no `NaN`/`Infinity` is ever serialized (the parity twin of Python's `allow_nan=False`).
- **Path safety (security-relevant):** `VectorCache` derives the file path only after `validateNamespace(namespace)` **and** `validateTextHash(textHash)` — both run in `pathFor` before any filesystem use, so `get`/`put` cannot escape the cache directory.
  - `validateNamespace`: reject `""`, `"."`, `".."`, and anything not matching `/^[A-Za-z0-9._-]+$/`.
  - `validateTextHash`: require exactly `/^[0-9a-f]{64}$/`.
  - Use **anchored** regexes with `.test()`. JavaScript's `$` (no `m` flag) matches only end-of-input — it does **not** match before a trailing `\n` the way Python's `$` does — so a trailing-newline bypass is not possible here. Tests still assert `"abc\n"` and `("a"*64)+"\n"` are rejected, to lock the contract.
- **L2 normalization:** vectors are stored **normalized** in memory (so cosine = dot product). `normalize` rejects a zero-norm vector. Raw vectors persist in the cache; normalized vectors live only in `VectorIndex.vectors`.
- **Cosine + ranking (parity-critical):** similarity score is the dot product of two L2-normalized vectors, summed in index order: `Σ queryVec[i] * vec[i]`. Sort by `(scoreKey(score) desc, id asc)`. `scoreKey(s) = Math.floor(s * 1_000_000 + 0.5) / 1_000_000` — the **same** key search uses, valid over cosine's `[-1, 1]` because `Math.floor`/`math.floor` agree on negatives. `SimilarHit.score` carries the **raw** cosine (not the rounded key).
- **Namespace + dimension binding.** A `VectorIndex` is bound to exactly one embedder namespace and one dimension. `build` binds `cacheNamespace` eagerly (even for an empty corpus). The first committed vector establishes `dim`. Any later vector or query of a different namespace or dimension fails (see error table). `similarText` re-checks the namespace before embedding.
- **prepare / commit split (fail-before-mutation).** `prepare(node, embedder, cache)` resolves and validates the vector **without mutating index state** (cache writes are allowed and it may throw). `commit(node, prepared)` applies the prepared result and never throws on valid input. `Corpus.add` and `Corpus.rename` call `prepare` **before** any disk or structural write and `commit` **last**, so a failed embed/validate leaves the corpus completely unmutated.
- **`similar` excludes the query node itself.** `VectorIndex.similar(uid, k)` ranks all vectors except `uid`.
- **`k` contract (identical to search's `limit`):** `undefined` = unbounded; otherwise must be an integer `> 0`. `0`, negative, or non-integer → `RangeError`. (TypeScript's types already reject `boolean`/`string`/float-typed `k` at compile time; the observable runtime cases are `0`, negatives, and non-integers.)
- **Error mapping (types are NOT part of the parity contract — the oracle asserts ranking only).** Apply this table consistently:
  - `RangeError`: invalid `k`; vector length `< 1`; zero-norm vector; dimension mismatch (build / query / prepare); namespace mismatch; embedder returning a number of vectors `!= 1` (or `!=` the requested count).
  - `TypeError`: a vector element that is not a finite `number`; invalid `cacheNamespace` format; invalid `textHash` format; corrupt cache-file structure (unparseable, missing `dim`/`vector`, length mismatch).
  - `Error`: unknown `uid` in `VectorIndex.similar` (internal uid lookup; mirrors Python's `KeyError(uid)`). `Corpus.similar(ref)` remains the layer that translates unresolved refs into `RefError`.
  - `CollisionError` (kernel): duplicate `uid` during `build`.
  - `EmbedderRequiredError` (new kernel error): any `Corpus` similarity API called on an embedder-less corpus — raised **before** ref resolution.
  - Note: TS `typeof true === "boolean"`, so `typeof x !== "number"` already rejects booleans (no special bool case needed). `Number.isFinite` rejects `NaN`/`±Infinity`; JS has no `OverflowError`, so the Python out-of-range-int guard has no TS analogue.
- **Opt-in `Corpus` integration.** `new Corpus(root, registry?, embedder?)`. With no embedder, no `VectorCache`/`VectorIndex` is built and `similar`/`queryVector`/`similarText` throw `EmbedderRequiredError`. The structural and search indexes are unchanged whether or not an embedder is present.
- **Mutation ordering (mirror Python `corpus.py`):** `add` = registry-validate → `assertAddable` → `prepare` (if embedder) → `writeFile` → `index.upsert` → `searchIndex.upsert` → `vectorIndex.commit`. `delete` = `deleteFile` → `index.remove` → `searchIndex.remove` → `vectorIndex?.remove`. `rename` is **not** otherwise refactored — it inserts exactly one `prepare` after registry validation / before the first `writeFile`, and one `commit` after the final `searchIndex.upsert`.
- **Parity, not bit-identity.** Embeddings are not portable across languages, so the *vectors* are frozen, not computed. The contract is the three committed fixtures (`fixtures/similarity-corpus/`, `fixtures/similarity.vectors.json`, `fixtures/similarity.oracle.json`): identical ranked `id` order and scores equal at 6 decimal places. **This port consumes those fixtures read-only — it does not regenerate them.** Compare oracle scores numerically via `scoreKey` (do not string-compare — `0.99838` is a JSON trailing-zero truncation of `0.998380`).
- **TS conventions:** camelCase fields/methods (`cacheNamespace`, `embedText`, `textHash`, `idByUid`, `hashByUid`, `vectorIndex`), SCREAMING_CASE module constants, `.js` import extensions, `type`-only imports for types, biome line width 120. Commands below assume the implementer runs from `~/d/nodes/ts`.

**Gate for every task:** from `~/d/nodes/ts`, `rtk npm test` (vitest) green, `rtk npm run typecheck` (`tsc --noEmit`) clean, `rtk npm run check` (biome) clean.

---

### Task 1: Extract `scoreKey` into `ranking.ts`

Mirror of Python commit `3b8806a`. `scoreKey` currently lives in `search.ts`; the similarity index needs it too, and neither derived-index facet should import the other. Move the single source of truth into a new `ranking.ts` and rewire every importer.

**Files:**
- Create: `ts/src/ranking.ts`
- Modify: `ts/src/search.ts` (remove the local `scoreKey`, import it from `./ranking.js`)
- Modify: `ts/src/index.ts` (barrel — export `scoreKey` from `./ranking.js`, not `./search.js`)
- Modify: `ts/tests/search-tokenizer.test.ts:4` (import `scoreKey` from `../src/ranking.js`; keep `STOP_WORDS`, `codepointSorted`, `tokenize` from `../src/search.js`)
- Modify: `ts/tests/search-parity.test.ts:7` (import `scoreKey` from `../src/ranking.js`)
- Test: `ts/tests/ranking.test.ts`

**Interfaces:**
- Consumes: nothing (pure built-ins).
- Produces: `scoreKey(score: number): number` from `ts/src/ranking.ts`. `search.ts` and `similarity.ts` both import it from there.

- [ ] **Step 1: Write the failing ranking test**

Create `ts/tests/ranking.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { scoreKey } from "../src/ranking.js";

describe("scoreKey", () => {
  it("rounds half-up to 6 decimal places", () => {
    expect(scoreKey(0.1234565)).toBe(0.123457); // .5 at 7th place rounds up
    expect(scoreKey(0.1234564)).toBe(0.123456);
    expect(scoreKey(1)).toBe(1);
    expect(scoreKey(0)).toBe(0);
  });

  it("is correct on negative scores (Math.floor half-up, parity with Python)", () => {
    // cosine is in [-1, 1]; floor-based half-up must behave like Python's on negatives
    expect(scoreKey(-0.9999995)).toBe(-0.999999); // floor(-999999.5+0.5)=floor(-999999)= -999999
    expect(scoreKey(-0.5)).toBe(-0.5);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk npm test -- ranking`
Expected: FAIL — `Cannot find module '../src/ranking.js'`.

- [ ] **Step 3: Create `ranking.ts` and rewire `search.ts`**

Create `ts/src/ranking.ts`:

```ts
/** Half-up rounding to 6 decimal places — the shared ranking/parity key. Used by both the
 * full-text search index and the similarity index, so it lives here rather than in either
 * (neither derived-index facet imports the other). Floor-based half-up is identical in
 * TypeScript and Python (`Math.floor` / `math.floor` agree on negative operands), so it is
 * correct over BM25 (non-negative) and cosine (`[-1, 1]`) scores alike. */
export function scoreKey(score: number): number {
  return Math.floor(score * 1_000_000 + 0.5) / 1_000_000;
}
```

In `ts/src/search.ts`, delete the local `scoreKey` definition (the `export function scoreKey...` block) and add an import at the top of the import group:

```ts
import { scoreKey } from "./ranking.js";
```

(`search.ts` keeps using `scoreKey` internally in `SearchIndex.search`; it no longer defines or exports it.)

- [ ] **Step 4: Rewire the barrel and the two existing tests**

In `ts/src/index.ts`, change the final search export line and add a ranking export. Replace:

```ts
export { SearchIndex, type SearchHit, scoreKey, tokenize } from "./search.js";
```

with:

```ts
export { scoreKey } from "./ranking.js";
export { SearchIndex, type SearchHit, tokenize } from "./search.js";
```

In `ts/tests/search-tokenizer.test.ts`, change line 4 from:

```ts
import { STOP_WORDS, codepointSorted, scoreKey, tokenize } from "../src/search.js";
```

to:

```ts
import { STOP_WORDS, codepointSorted, tokenize } from "../src/search.js";
import { scoreKey } from "../src/ranking.js";
```

In `ts/tests/search-parity.test.ts`, change line 7 from `import { scoreKey } from "../src/search.js";` to `import { scoreKey } from "../src/ranking.js";`.

- [ ] **Step 5: Run the full suite to verify green**

Run: `rtk npm test`
Expected: PASS — the new `ranking.test.ts` plus every pre-existing test (tokenizer, parity, search-query, corpus, etc.) green; no test lost. Then `rtk npm run typecheck` and `rtk npm run check` clean.

- [ ] **Step 6: Commit**

```bash
rtk git add ts/src/ranking.ts ts/src/search.ts ts/src/index.ts ts/tests/ranking.test.ts ts/tests/search-tokenizer.test.ts ts/tests/search-parity.test.ts
rtk git commit -m "refactor(ts-kernel): extract shared scoreKey into ranking.ts"
```

---

### Task 2: Similarity foundations — `Embedder`, `embedText`, `textHash`, validators

Mirror of Python commit `fe8d4d2`. Create `ts/src/similarity.ts` with the pure (no-I/O) primitives and add `EmbedderRequiredError` to `errors.ts`.

**Files:**
- Create: `ts/src/similarity.ts`
- Modify: `ts/src/errors.ts` (add `EmbedderRequiredError`)
- Test: `ts/tests/similarity-foundations.test.ts`

**Interfaces:**
- Consumes: `Node` (type) from `./node.js`; `node:crypto` `createHash`.
- Produces (from `similarity.ts`): `type Vector = number[]`; `interface Embedder { readonly cacheNamespace: string; embed(texts: string[]): Vector[] }`; `embedText(node: Node): string`; `textHash(text: string): string`; `validateNamespace(namespace: string): void`; `validateTextHash(hash: string): void`; `interface SimilarHit { id: string; uid: string; score: number }`. Produces (from `errors.ts`): `class EmbedderRequiredError extends NodesError`.

- [ ] **Step 1: Write the failing foundations test**

Create `ts/tests/similarity-foundations.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { embedText, textHash, validateNamespace, validateTextHash } from "../src/similarity.js";

const HEX64 = "a".repeat(64);

describe("embedText", () => {
  it("joins title and body with one blank line", () => {
    const node = makeNode({ id: "topic:x", kind: "topic", title: "Cats", body: "feline pets" });
    expect(embedText(node)).toBe("Cats\n\nfeline pets");
  });

  it("handles an empty body (title, blank line, empty string)", () => {
    const node = makeNode({ id: "topic:x", kind: "topic", title: "Cats" });
    expect(embedText(node)).toBe("Cats\n\n");
  });
});

describe("textHash", () => {
  it("is the lowercase sha256 hex digest of the utf-8 text", () => {
    // sha256("") is well-known
    expect(textHash("")).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    expect(textHash("abc")).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe("validateNamespace", () => {
  it("accepts safe single segments", () => {
    expect(() => validateNamespace("fixture-v1")).not.toThrow();
    expect(() => validateNamespace("model.v2_0")).not.toThrow();
  });

  it("rejects empty, dot, dot-dot, separators, and trailing newline", () => {
    for (const bad of ["", ".", "..", "a/b", "a\\b", "a b", "fixture-v1\n"]) {
      expect(() => validateNamespace(bad)).toThrow(TypeError);
    }
  });
});

describe("validateTextHash", () => {
  it("accepts exactly 64 lowercase hex chars", () => {
    expect(() => validateTextHash(HEX64)).not.toThrow();
  });

  it("rejects wrong length, uppercase, non-hex, and trailing newline", () => {
    for (const bad of ["a".repeat(63), "a".repeat(65), "A".repeat(64), `${"a".repeat(63)}g`, `${HEX64}\n`]) {
      expect(() => validateTextHash(bad)).toThrow(TypeError);
    }
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk npm test -- similarity-foundations`
Expected: FAIL — `Cannot find module '../src/similarity.js'`.

- [ ] **Step 3: Add `EmbedderRequiredError`**

In `ts/src/errors.ts`, add one line to the error list (after `ValidationError`):

```ts
export class EmbedderRequiredError extends NodesError {}
```

- [ ] **Step 4: Create `similarity.ts` with the foundations**

Create `ts/src/similarity.ts`:

```ts
import { createHash } from "node:crypto";
import type { Node } from "./node.js";

export type Vector = number[];

/** The seam: turns text into vectors. The kernel ships no concrete embedder. */
export interface Embedder {
  readonly cacheNamespace: string;
  embed(texts: string[]): Vector[];
}

/** The frozen per-node embedding input: title and body joined by one blank line. */
export function embedText(node: Node): string {
  return `${node.title}\n\n${node.body}`;
}

/** Content-address key for the vector cache. */
export function textHash(text: string): string {
  return createHash("sha256").update(text, "utf-8").digest("hex");
}

const NAMESPACE_RE = /^[A-Za-z0-9._-]+$/;

/** A cacheNamespace must be a safe single path segment. */
export function validateNamespace(namespace: string): void {
  if (namespace === "." || namespace === ".." || !NAMESPACE_RE.test(namespace)) {
    throw new TypeError(`invalid cacheNamespace ${JSON.stringify(namespace)}`);
  }
}

const TEXT_HASH_RE = /^[0-9a-f]{64}$/;

/** A cache key must be exactly 64 lowercase hex chars (a SHA-256 hexdigest). */
export function validateTextHash(hash: string): void {
  if (!TEXT_HASH_RE.test(hash)) {
    throw new TypeError(`invalid textHash ${JSON.stringify(hash)}`);
  }
}

export interface SimilarHit {
  id: string;
  uid: string;
  score: number;
}
```

> Note: `NAMESPACE_RE` already excludes `""` (one-or-more required) and `/`, `\`, spaces; the explicit `"."`/`".."` checks reject the two path-traversal segments that otherwise match the character class. `validateFinite`, `normalize`, and `validateK` are introduced in the later tasks that first use them, so this task stays clean under biome's no-unused-vars rule.

- [ ] **Step 5: Make the suite green**

Run: `rtk npm test -- similarity-foundations`
Expected: PASS. Then `rtk npm test` (full), `rtk npm run typecheck`, `rtk npm run check` all clean.

- [ ] **Step 6: Commit**

```bash
rtk git add ts/src/similarity.ts ts/src/errors.ts ts/tests/similarity-foundations.test.ts
rtk git commit -m "feat(ts-similarity): embedder seam, embedText, textHash, path validators"
```

---

### Task 3: `VectorCache` — content-addressed raw-vector store

Mirror of Python commit `c919524`. Add `validateFinite` (first user) and the `VectorCache` class to `similarity.ts`.

**Files:**
- Modify: `ts/src/similarity.ts` (add `validateFinite` + `VectorCache`)
- Test: `ts/tests/vector-cache.test.ts`

**Interfaces:**
- Consumes: `validateNamespace`, `validateTextHash` (Task 2); `node:fs`, `node:path`.
- Produces: `class VectorCache { constructor(root: string); get(namespace: string, textHash: string): Vector | null; put(namespace: string, textHash: string, vector: Vector): void }`. Internal: `validateFinite(vec: ReadonlyArray<unknown>): void`.

- [ ] **Step 1: Write the failing cache test**

Create `ts/tests/vector-cache.test.ts`:

```ts
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { VectorCache } from "../src/similarity.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-vec-cache-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

const NS = "fixture-v1";
const HEX64 = "a".repeat(64);

describe("VectorCache", () => {
  it("returns null on a miss", () => {
    expect(new VectorCache(root).get(NS, HEX64)).toBeNull();
  });

  it("round-trips a raw vector through an atomic write", () => {
    const cache = new VectorCache(root);
    cache.put(NS, HEX64, [1, 2, 3.5, -4]);
    expect(cache.get(NS, HEX64)).toEqual([1, 2, 3.5, -4]);
    // the file lives under the namespaced cache dir and contains {dim, vector}
    const path = join(root, ".nodes-index", "vectors", NS, `${HEX64}.json`);
    expect(existsSync(path)).toBe(true);
    expect(JSON.parse(readFileSync(path, "utf-8"))).toEqual({ dim: 4, vector: [1, 2, 3.5, -4] });
  });

  it("leaves no .tmp file behind", () => {
    const cache = new VectorCache(root);
    cache.put(NS, HEX64, [1, 0]);
    expect(existsSync(join(root, ".nodes-index", "vectors", NS, `${HEX64}.json.tmp`))).toBe(false);
  });

  it("rejects an unsafe namespace or hash before touching disk", () => {
    const cache = new VectorCache(root);
    expect(() => cache.get("..", HEX64)).toThrow(TypeError);
    expect(() => cache.put("ok", "nothex", [1])).toThrow(TypeError);
  });

  it("rejects a non-finite vector on put (never serialized)", () => {
    const cache = new VectorCache(root);
    expect(() => cache.put(NS, HEX64, [1, Number.NaN])).toThrow(TypeError);
    expect(() => cache.put(NS, HEX64, [1, Number.POSITIVE_INFINITY])).toThrow(TypeError);
    expect(() => cache.put(NS, HEX64, [])).toThrow(RangeError); // length < 1
  });

  it("throws on a corrupt cache file", () => {
    const cache = new VectorCache(root);
    const dir = join(root, ".nodes-index", "vectors", NS);
    const path = join(dir, `${HEX64}.json`);
    cache.put(NS, HEX64, [1, 2]); // create the dir + a valid file first
    writeFileSync(path, "{ not json", "utf-8");
    expect(() => cache.get(NS, HEX64)).toThrow(TypeError);
    writeFileSync(path, JSON.stringify({ dim: 3, vector: [1, 2] }), "utf-8"); // length mismatch
    expect(() => cache.get(NS, HEX64)).toThrow(TypeError);
    writeFileSync(path, JSON.stringify({ vector: [1, 2] }), "utf-8"); // missing dim
    expect(() => cache.get(NS, HEX64)).toThrow(TypeError);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk npm test -- vector-cache`
Expected: FAIL — `VectorCache` is not exported.

- [ ] **Step 3: Add `validateFinite` and `VectorCache`**

In `ts/src/similarity.ts`, update the imports at the top to add the fs/path built-ins (keep the existing `createHash` and `Node` imports):

```ts
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { Node } from "./node.js";
```

Add `validateFinite` immediately after `validateTextHash` (before `SimilarHit`):

```ts
/** Reject empty / non-numeric / non-finite vectors. Booleans are non-`number` typed,
 * so `typeof x !== "number"` already rejects them. */
function validateFinite(vec: ReadonlyArray<unknown>): void {
  if (vec.length < 1) {
    throw new RangeError("vector must have length >= 1");
  }
  for (const x of vec) {
    if (typeof x !== "number" || !Number.isFinite(x)) {
      throw new TypeError(`vector contains non-finite or non-numeric value ${String(x)}`);
    }
  }
}
```

Add the `VectorCache` class at the end of the module:

```ts
/** Content-addressed on-disk cache of RAW embedder output, namespaced per embedder.
 * Disposable: deleting the directory just forces re-embedding. All ranking math lives in
 * VectorIndex; this is purely a model-output cache. */
export class VectorCache {
  readonly root: string;

  constructor(root: string) {
    this.root = root;
  }

  private pathFor(namespace: string, hash: string): string {
    validateNamespace(namespace);
    validateTextHash(hash);
    return join(this.root, ".nodes-index", "vectors", namespace, `${hash}.json`);
  }

  get(namespace: string, hash: string): Vector | null {
    const path = this.pathFor(namespace, hash);
    if (!existsSync(path)) return null;
    let data: unknown;
    try {
      data = JSON.parse(readFileSync(path, "utf-8"));
    } catch (e) {
      throw new TypeError(`corrupt cache file ${path}: ${(e as Error).message}`);
    }
    if (typeof data !== "object" || data === null || !("dim" in data) || !("vector" in data)) {
      throw new TypeError(`corrupt cache file ${path}: missing dim/vector`);
    }
    const { dim, vector } = data as { dim: unknown; vector: unknown };
    if (!Array.isArray(vector) || vector.length !== dim) {
      throw new TypeError(`corrupt cache file ${path}: dim/vector length mismatch`);
    }
    validateFinite(vector);
    return [...(vector as number[])];
  }

  put(namespace: string, hash: string, vector: Vector): void {
    validateFinite(vector);
    const path = this.pathFor(namespace, hash);
    mkdirSync(dirname(path), { recursive: true });
    const payload = JSON.stringify({ dim: vector.length, vector });
    const tmp = `${path}.tmp`;
    writeFileSync(tmp, payload, "utf-8");
    renameSync(tmp, path);
  }
}
```

- [ ] **Step 4: Run to verify green**

Run: `rtk npm test -- vector-cache`
Expected: PASS. Then `rtk npm test` (full), `rtk npm run typecheck`, `rtk npm run check` clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/src/similarity.ts ts/tests/vector-cache.test.ts
rtk git commit -m "feat(ts-similarity): content-addressed vector cache (raw output, atomic writes)"
```

---

### Task 4: `VectorIndex` core — build / prepare / commit / upsert / remove

Mirror of Python commit `815e772`. Add `normalize`, the `PreparedVector` shape, and the `VectorIndex` class with its lifecycle (no query methods yet).

**Files:**
- Modify: `ts/src/similarity.ts` (add `normalize`, `PreparedVector`, `VectorIndex` build/prepare/commit/upsert/remove)
- Test: `ts/tests/vector-index.test.ts`

**Interfaces:**
- Consumes: `validateFinite` (Task 3), `validateNamespace`, `embedText`, `textHash`, `VectorCache`, `Embedder`, `Vector`; `CollisionError` from `./errors.js`; `Node` from `./node.js`.
- Produces: `class VectorIndex` with public fields `vectors: Map<string, Vector>`, `idByUid: Map<string, string>`, `hashByUid: Map<string, string>`, `dim: number | null`, `namespace: string | null`; static `build(nodes: Iterable<Node>, embedder: Embedder, cache: VectorCache): VectorIndex`; `prepare(node, embedder, cache): PreparedVector`; `commit(node, prepared): void`; `upsert(node, embedder, cache): void`; `remove(uid: string): void`. Internal: `normalize`; non-exported `interface PreparedVector { readonly textHash: string; readonly namespace: string; readonly vector: Vector | null }`. (Query methods `queryVector`/`similar`/`similarText` arrive in Task 5.)

- [ ] **Step 1: Write the failing index-lifecycle test**

Create `ts/tests/vector-index.test.ts`:

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CollisionError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { type Embedder, type Vector, VectorCache, VectorIndex } from "../src/similarity.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-vec-index-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

// A deterministic embedder: maps each node's embedText to a fixed vector via a table.
class TableEmbedder implements Embedder {
  readonly cacheNamespace: string;
  private table: Map<string, Vector>;
  constructor(table: Map<string, Vector>, namespace = "test-v1") {
    this.table = table;
    this.cacheNamespace = namespace;
  }
  embed(texts: string[]): Vector[] {
    return texts.map((t) => {
      const v = this.table.get(t);
      if (v === undefined) throw new Error(`no vector for ${JSON.stringify(t)}`);
      return v;
    });
  }
}

function node(id: string, title: string, body = "") {
  return makeNode({ id, kind: id.split(":")[0], title, body });
}

describe("VectorIndex lifecycle", () => {
  it("binds the namespace even for an empty corpus", () => {
    const cache = new VectorCache(root);
    const idx = VectorIndex.build([], new TableEmbedder(new Map()), cache);
    expect(idx.namespace).toBe("test-v1");
    expect(idx.dim).toBeNull();
    expect(idx.vectors.size).toBe(0);
  });

  it("rejects a build over a corpus with a duplicate uid", () => {
    const cache = new VectorCache(root);
    const a = makeNode({ id: "topic:a", uid: "u1", kind: "topic", title: "a" });
    const b = makeNode({ id: "topic:b", uid: "u1", kind: "topic", title: "b" });
    const emb = new TableEmbedder(
      new Map([
        ["a\n\n", [1, 0]],
        ["b\n\n", [0, 1]],
      ]),
    );
    expect(() => VectorIndex.build([a, b], emb, cache)).toThrow(CollisionError);
  });

  it("builds, binds dim from the first vector, and stores normalized vectors", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const emb = new TableEmbedder(new Map([["cat\n\n", [3, 4]]])); // norm 5
    const idx = VectorIndex.build([cat], emb, cache);
    expect(idx.dim).toBe(2);
    const v = idx.vectors.get(cat.uid) as Vector;
    expect(v[0]).toBeCloseTo(0.6, 12);
    expect(v[1]).toBeCloseTo(0.8, 12);
    expect(idx.idByUid.get(cat.uid)).toBe("topic:cat");
    // raw vector is cached (un-normalized)
    expect(cache.get("test-v1", [...idx.hashByUid.values()][0])).toEqual([3, 4]);
  });

  it("prepare does not mutate index state; commit applies it", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const emb = new TableEmbedder(new Map([["cat\n\n", [1, 0]]]));
    const idx = VectorIndex.build([], emb, cache);
    const prepared = idx.prepare(cat, emb, cache);
    expect(idx.vectors.size).toBe(0); // prepare left the index untouched
    idx.commit(cat, prepared);
    expect(idx.vectors.get(cat.uid)).toEqual([1, 0]);
  });

  it("rejects a vector of a different dimension", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const dog = node("topic:dog", "dog");
    const emb = new TableEmbedder(
      new Map([
        ["cat\n\n", [1, 0]],
        ["dog\n\n", [1, 0, 0]], // wrong dim
      ]),
    );
    const idx = VectorIndex.build([cat], emb, cache);
    expect(() => idx.upsert(dog, emb, cache)).toThrow(RangeError);
  });

  it("rejects an embedder bound to a different namespace", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const idx = VectorIndex.build([], new TableEmbedder(new Map(), "ns-a"), cache);
    const other = new TableEmbedder(new Map([["cat\n\n", [1, 0]]]), "ns-b");
    expect(() => idx.prepare(cat, other, cache)).toThrow(RangeError);
  });

  it("an unchanged-content re-upsert refreshes id without re-embedding (vector=null path)", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const emb = new TableEmbedder(new Map([["cat\n\n", [1, 0]]]));
    const idx = VectorIndex.build([cat], emb, cache);
    const renamed = makeNode({ id: "topic:feline", uid: cat.uid, kind: "topic", title: "cat" });
    const prepared = idx.prepare(renamed, emb, cache);
    expect(prepared.vector).toBeNull(); // same embedText => same hash => no new vector
    idx.commit(renamed, prepared);
    expect(idx.idByUid.get(cat.uid)).toBe("topic:feline");
    expect(idx.vectors.get(cat.uid)).toEqual([1, 0]); // vector unchanged
  });

  it("remove drops all per-uid state", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const emb = new TableEmbedder(new Map([["cat\n\n", [1, 0]]]));
    const idx = VectorIndex.build([cat], emb, cache);
    idx.remove(cat.uid);
    expect(idx.vectors.has(cat.uid)).toBe(false);
    expect(idx.idByUid.has(cat.uid)).toBe(false);
    expect(idx.hashByUid.has(cat.uid)).toBe(false);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk npm test -- vector-index`
Expected: FAIL — `VectorIndex` is not exported.

- [ ] **Step 3: Add `normalize`, `PreparedVector`, and `VectorIndex`**

In `ts/src/similarity.ts`, add the `CollisionError` import (errors are otherwise not yet imported here):

```ts
import { CollisionError } from "./errors.js";
```

Add `normalize` immediately after `validateFinite`:

```ts
/** Return the L2-normalized vector; reject zero-norm and invalid numeric input. */
function normalize(vec: Vector): Vector {
  validateFinite(vec);
  let sumSq = 0;
  for (const x of vec) sumSq += x * x;
  const norm = Math.sqrt(sumSq);
  if (norm === 0) {
    throw new RangeError("cannot normalize a zero-norm vector");
  }
  return vec.map((x) => x / norm);
}
```

Add the prepared-vector shape and the class (after `VectorCache`):

```ts
interface PreparedVector {
  readonly textHash: string;
  readonly namespace: string;
  readonly vector: Vector | null; // null => content unchanged (id-only refresh)
}

/** In-memory uid -> L2-normalized vector store with exact cosine ranking. Bound to exactly
 * one embedder namespace and one dimension (cosine across vectors from different models or
 * dimensions is meaningless). */
export class VectorIndex {
  vectors = new Map<string, Vector>();
  idByUid = new Map<string, string>();
  hashByUid = new Map<string, string>();
  dim: number | null = null;
  namespace: string | null = null;

  static build(nodes: Iterable<Node>, embedder: Embedder, cache: VectorCache): VectorIndex {
    const idx = new VectorIndex();
    validateNamespace(embedder.cacheNamespace);
    idx.namespace = embedder.cacheNamespace; // bind even for an empty corpus
    for (const node of nodes) {
      if (idx.hashByUid.has(node.uid)) {
        throw new CollisionError(`duplicate uid ${JSON.stringify(node.uid)} in corpus`);
      }
      idx.upsert(node, embedder, cache);
    }
    return idx;
  }

  /** Resolve + validate the vector WITHOUT mutating index state (cache writes ok). */
  prepare(node: Node, embedder: Embedder, cache: VectorCache): PreparedVector {
    const namespace = embedder.cacheNamespace;
    validateNamespace(namespace);
    if (this.namespace !== null && namespace !== this.namespace) {
      throw new RangeError(
        `embedder namespace ${JSON.stringify(namespace)} != index namespace ${JSON.stringify(this.namespace)}`,
      );
    }
    const text = embedText(node);
    const h = textHash(text);
    if (this.hashByUid.get(node.uid) === h) {
      return { textHash: h, namespace, vector: null };
    }
    let raw = cache.get(namespace, h);
    if (raw === null) {
      const embedded = embedder.embed([text]);
      if (embedded.length !== 1) {
        throw new RangeError(`embedder returned ${embedded.length} vectors for 1 input`);
      }
      raw = embedded[0];
      validateFinite(raw);
      cache.put(namespace, h, raw);
    }
    if (this.dim !== null && raw.length !== this.dim) {
      throw new RangeError(`vector dim ${raw.length} != index dim ${this.dim}`);
    }
    return { textHash: h, namespace, vector: normalize(raw) };
  }

  /** Apply a prepared vector. Infallible: never throws on valid prepared input. */
  commit(node: Node, prepared: PreparedVector): void {
    if (this.namespace === null) this.namespace = prepared.namespace;
    if (prepared.vector === null) {
      this.idByUid.set(node.uid, node.id); // rename / id-only refresh
      return;
    }
    if (this.dim === null) this.dim = prepared.vector.length;
    this.vectors.set(node.uid, prepared.vector);
    this.idByUid.set(node.uid, node.id);
    this.hashByUid.set(node.uid, prepared.textHash);
  }

  upsert(node: Node, embedder: Embedder, cache: VectorCache): void {
    this.commit(node, this.prepare(node, embedder, cache));
  }

  remove(uid: string): void {
    this.vectors.delete(uid);
    this.idByUid.delete(uid);
    this.hashByUid.delete(uid);
  }
}
```

> Note: `build` detects a duplicate uid via `hashByUid.has(node.uid)` (faithful mirror of Python's `if node.uid in idx.hash_by_uid`). On a fresh build every node is new and gets a non-null vector, so `hashByUid` is populated on each `commit` and the check is correct.

- [ ] **Step 4: Run to verify green**

Run: `rtk npm test -- vector-index`
Expected: PASS. Then `rtk npm test` (full), `rtk npm run typecheck`, `rtk npm run check` clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/src/similarity.ts ts/tests/vector-index.test.ts
rtk git commit -m "feat(ts-similarity): VectorIndex build/upsert/remove with prepare/commit + lifecycle"
```

---

### Task 5: Cosine query + ranking — `queryVector`, `similar`, `similarText`

Mirror of Python commit `597f240`. Add `validateK` (first user) and the three query methods plus their helpers.

**Files:**
- Modify: `ts/src/similarity.ts` (add `validateK`, `queryVector`, `similar`, `similarText`, `prepareQuery`, `rank`)
- Test: `ts/tests/vector-query.test.ts`

**Interfaces:**
- Consumes: `normalize`, `validateFinite`, `scoreKey` (from `./ranking.js`), `SimilarHit`, `Embedder`, `Vector`.
- Produces (methods on `VectorIndex`): `queryVector(vec: Vector, k?: number): SimilarHit[]`; `similar(uid: string, k?: number): SimilarHit[]`; `similarText(text: string, embedder: Embedder, k?: number): SimilarHit[]`. Internal: `validateK`; private `prepareQuery(vec): Vector`; private `rank(queryVec, k, excludeUid): SimilarHit[]`.

- [ ] **Step 1: Write the failing query test**

Create `ts/tests/vector-query.test.ts`:

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { type Embedder, type Vector, VectorCache, VectorIndex } from "../src/similarity.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-vec-query-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

class TableEmbedder implements Embedder {
  readonly cacheNamespace: string;
  private table: Map<string, Vector>;
  constructor(table: Map<string, Vector>, namespace = "test-v1") {
    this.table = table;
    this.cacheNamespace = namespace;
  }
  embed(texts: string[]): Vector[] {
    return texts.map((t) => {
      const v = this.table.get(t);
      if (v === undefined) throw new Error(`no vector for ${JSON.stringify(t)}`);
      return v;
    });
  }
}

function build(root: string) {
  const cache = new VectorCache(root);
  const cat = makeNode({ id: "topic:cat", uid: "ucat", kind: "topic", title: "cat" });
  const dog = makeNode({ id: "topic:dog", uid: "udog", kind: "topic", title: "dog" });
  const car = makeNode({ id: "topic:car", uid: "ucar", kind: "topic", title: "car" });
  const emb = new TableEmbedder(
    new Map([
      ["cat\n\n", [1, 0.1, 0, 0]],
      ["dog\n\n", [0.9, 0.2, 0, 0]],
      ["car\n\n", [0, 0, 1, 0.1]],
    ]),
  );
  return { idx: VectorIndex.build([cat, dog, car], emb, cache), emb };
}

describe("VectorIndex queries", () => {
  it("similar(uid) excludes the node itself and ranks by cosine then id", () => {
    const { idx } = build(root);
    const hits = idx.similar("ucat");
    expect(hits.map((h) => h.id)).toEqual(["topic:dog", "topic:car"]); // dog closest, car orthogonal
    expect(hits.every((h) => h.uid !== "ucat")).toBe(true);
    expect(hits[0].score).toBeGreaterThan(hits[1].score);
  });

  it("similar respects k", () => {
    const { idx } = build(root);
    expect(idx.similar("ucat", 1).map((h) => h.id)).toEqual(["topic:dog"]);
  });

  it("similar throws an internal uid lookup error on an unknown uid", () => {
    const { idx } = build(root);
    expect(() => idx.similar("nope")).toThrow(Error);
  });

  it("queryVector ranks all nodes (no exclusion) and validates k", () => {
    const { idx } = build(root);
    const hits = idx.queryVector([0.95, 0.15, 0, 0]);
    expect(hits.map((h) => h.id)).toEqual(["topic:cat", "topic:dog", "topic:car"]);
    expect(() => idx.queryVector([1, 0, 0, 0], 0)).toThrow(RangeError);
    expect(() => idx.queryVector([1, 0, 0, 0], 1.5)).toThrow(RangeError);
  });

  it("queryVector rejects a wrong-dimension or zero-norm query", () => {
    const { idx } = build(root);
    expect(() => idx.queryVector([1, 0])).toThrow(RangeError); // dim mismatch
    expect(() => idx.queryVector([0, 0, 0, 0])).toThrow(RangeError); // zero norm
  });

  it("similarText embeds via the live embedder and enforces the namespace", () => {
    const { idx, emb } = build(root);
    expect(idx.similarText("cat\n\n", emb).map((h) => h.id)).toEqual([
      "topic:cat",
      "topic:dog",
      "topic:car",
    ]);
    const wrongNs = new TableEmbedder(new Map([["x", [1, 0, 0, 0]]]), "other");
    expect(() => idx.similarText("x", wrongNs)).toThrow(RangeError);
  });

  it("an empty index still validates the query vector", () => {
    const idx = VectorIndex.build([], new TableEmbedder(new Map()), new VectorCache(root));
    expect(idx.queryVector([1, 2, 3])).toEqual([]); // valid query, no candidates
    expect(() => idx.queryVector([0, 0])).toThrow(RangeError); // zero norm still rejected
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk npm test -- vector-query`
Expected: FAIL — `queryVector`/`similar`/`similarText` are not methods on `VectorIndex`.

- [ ] **Step 3: Add `validateK`, the query methods, and helpers**

`VectorIndex.similar(uid)` receives an internal uid, not an external ref. Keep `RefError` at the `Corpus.similar(ref)` boundary; direct unknown-uid lookup mirrors Python's `KeyError` with a plain `Error`.

In `ts/src/similarity.ts`, keep the existing `CollisionError` import unchanged:

```ts
import { CollisionError } from "./errors.js";
```

and add the ranking-key import:

```ts
import { scoreKey } from "./ranking.js";
```

Add `validateK` immediately after `SimilarHit`:

```ts
function validateK(k?: number): void {
  if (k !== undefined && (!Number.isInteger(k) || k <= 0)) {
    throw new RangeError(`k must be a positive integer or undefined, got ${JSON.stringify(k)}`);
  }
}
```

Add these methods to the `VectorIndex` class (after `remove`):

```ts
  queryVector(vec: Vector, k?: number): SimilarHit[] {
    validateK(k);
    return this.rank(this.prepareQuery(vec), k, null);
  }

  similar(uid: string, k?: number): SimilarHit[] {
    validateK(k);
    const vec = this.vectors.get(uid);
    if (vec === undefined) throw new Error(`uid ${JSON.stringify(uid)} not in vector index`);
    return this.rank(vec, k, uid);
  }

  similarText(text: string, embedder: Embedder, k?: number): SimilarHit[] {
    validateK(k);
    if (this.namespace !== null && embedder.cacheNamespace !== this.namespace) {
      throw new RangeError(
        `embedder namespace ${JSON.stringify(embedder.cacheNamespace)} != index namespace ${JSON.stringify(this.namespace)}`,
      );
    }
    const embedded = embedder.embed([text]);
    if (embedded.length !== 1) {
      throw new RangeError(`embedder returned ${embedded.length} vectors for 1 input`);
    }
    return this.queryVector(embedded[0], k);
  }

  private prepareQuery(vec: Vector): Vector {
    validateFinite(vec);
    if (this.dim !== null && vec.length !== this.dim) {
      throw new RangeError(`query dim ${vec.length} != index dim ${this.dim}`);
    }
    return normalize(vec);
  }

  private rank(queryVec: Vector, k: number | undefined, excludeUid: string | null): SimilarHit[] {
    const hits: SimilarHit[] = [];
    for (const [uid, vec] of this.vectors) {
      if (uid === excludeUid) continue;
      let dot = 0;
      for (let i = 0; i < queryVec.length; i++) dot += queryVec[i] * vec[i];
      hits.push({ id: this.idByUid.get(uid) as string, uid, score: dot });
    }
    hits.sort((a, b) => {
      const ka = scoreKey(a.score);
      const kb = scoreKey(b.score);
      if (ka !== kb) return kb - ka; // scoreKey descending
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; // id ascending
    });
    return k === undefined ? hits : hits.slice(0, k);
  }
```

> Note: `rank` sums in `this.vectors` insertion order (JS `Map` preserves it) and breaks ties on ascending `id` — identical to Python's `(-score_key(h.score), h.id)` sort. `SimilarHit.score` is the raw cosine; `scoreKey` is applied only for ordering.

- [ ] **Step 4: Run to verify green**

Run: `rtk npm test -- vector-query`
Expected: PASS. Then `rtk npm test` (full), `rtk npm run typecheck`, `rtk npm run check` clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/src/similarity.ts ts/tests/vector-query.test.ts
rtk git commit -m "feat(ts-similarity): cosine query/ranking — queryVector, similar, similarText"
```

---

### Task 6: Opt-in `Corpus` integration

Current-code note: the embedder gating and prepare/commit ordering remain current. Current `Corpus` also maintains a snapshot manifest and may reconcile indexes from `snapshot.ts.json`, so the snippets here are the similarity-specific additions, not the full present-day constructor or mutation methods.

Mirror of Python commit `45157cc`. Wire the vector index into `Corpus` with the fail-before-mutation ordering and export the new public surface from the barrel.

**Files:**
- Modify: `ts/src/corpus.ts` (constructor, `add`, `delete`, `rename`, three query methods)
- Modify: `ts/src/index.ts` (barrel — export similarity surface + `EmbedderRequiredError`)
- Test: `ts/tests/corpus-similarity.test.ts`

**Interfaces:**
- Consumes: `VectorCache`, `VectorIndex`, `Embedder`, `Vector`, `SimilarHit` from `./similarity.js`; `EmbedderRequiredError` from `./errors.js`.
- Produces: `new Corpus(root, registry?, embedder?)`; `Corpus.similar(ref, k?): SimilarHit[]`; `Corpus.queryVector(vec, k?): SimilarHit[]`; `Corpus.similarText(text, k?): SimilarHit[]`. Barrel re-exports `Embedder`, `SimilarHit`, `Vector`, `VectorCache`, `VectorIndex`, `embedText`, `textHash`, `validateNamespace`, `validateTextHash`, and `EmbedderRequiredError`.

- [ ] **Step 1: Write the failing integration test**

Create `ts/tests/corpus-similarity.test.ts`:

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { EmbedderRequiredError } from "../src/errors.js";
import { Corpus } from "../src/corpus.js";
import { makeNode } from "../src/node.js";
import { type Embedder, type Vector } from "../src/similarity.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-sim-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

class TableEmbedder implements Embedder {
  readonly cacheNamespace = "test-v1";
  private table: Map<string, Vector>;
  constructor(table: Map<string, Vector>) {
    this.table = table;
  }
  embed(texts: string[]): Vector[] {
    return texts.map((t) => {
      const v = this.table.get(t);
      if (v === undefined) throw new Error(`no vector for ${JSON.stringify(t)}`);
      return v;
    });
  }
}

const TABLE = new Map<string, Vector>([
  ["cat\n\n", [1, 0.1, 0, 0]],
  ["dog\n\n", [0.9, 0.2, 0, 0]],
  ["car\n\n", [0, 0, 1, 0.1]],
  ["kitten\n\n", [1, 0.1, 0, 0]], // same vector as cat (content-addressed cache shares it)
]);

describe("Corpus similarity (opt-in)", () => {
  it("raises EmbedderRequiredError when no embedder was supplied (before ref resolution)", () => {
    const c = new Corpus(root);
    expect(() => c.similar("topic:anything")).toThrow(EmbedderRequiredError);
    expect(() => c.queryVector([1, 0, 0, 0])).toThrow(EmbedderRequiredError);
    expect(() => c.similarText("cat")).toThrow(EmbedderRequiredError);
  });

  it("similar over an embedder-backed corpus ranks by cosine and excludes self", () => {
    const c = new Corpus(root, undefined, new TableEmbedder(TABLE));
    c.add(makeNode({ id: "topic:cat", kind: "topic", title: "cat" }));
    c.add(makeNode({ id: "topic:dog", kind: "topic", title: "dog" }));
    c.add(makeNode({ id: "topic:car", kind: "topic", title: "car" }));
    expect(c.similar("topic:cat").map((h) => h.id)).toEqual(["topic:dog", "topic:car"]);
    expect(c.queryVector([0.95, 0.15, 0, 0]).map((h) => h.id)).toEqual([
      "topic:cat",
      "topic:dog",
      "topic:car",
    ]);
    expect(c.similarText("cat\n\n").map((h) => h.id)).toEqual(["topic:cat", "topic:dog", "topic:car"]);
  });

  it("delete removes a node from the vector index", () => {
    const c = new Corpus(root, undefined, new TableEmbedder(TABLE));
    c.add(makeNode({ id: "topic:cat", kind: "topic", title: "cat" }));
    c.add(makeNode({ id: "topic:dog", kind: "topic", title: "dog" }));
    c.delete("topic:dog");
    expect(c.similar("topic:cat")).toEqual([]); // dog was the only other vector
  });

  it("a failing embed leaves the corpus completely unmutated (fail before disk write)", () => {
    const c = new Corpus(root, undefined, new TableEmbedder(TABLE));
    // "ghost\n\n" is absent from the table -> embed throws inside add's prepare, before writeFile
    expect(() => c.add(makeNode({ id: "topic:ghost", kind: "topic", title: "ghost" }))).toThrow();
    expect(c.all()).toEqual([]); // no file written
    expect(() => c.get("topic:ghost")).toThrow(); // not in the structural index either
  });

  it("rename carries the new id into the vector index (no re-embed; same content)", () => {
    const c = new Corpus(root, undefined, new TableEmbedder(TABLE));
    c.add(makeNode({ id: "topic:cat", kind: "topic", title: "cat" }));
    c.add(makeNode({ id: "topic:dog", kind: "topic", title: "dog" }));
    c.rename("topic:cat", "topic:feline");
    // dog's nearest neighbor (cat) is now reported under the new id, and the old id is gone
    const hits = c.similar("topic:dog");
    expect(hits[0].id).toBe("topic:feline");
    expect(hits.map((h) => h.id)).toContain("topic:feline");
    expect(hits.map((h) => h.id)).not.toContain("topic:cat");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk npm test -- corpus-similarity`
Expected: FAIL — `Corpus` has no third constructor arg / no `similar` method.

- [ ] **Step 3: Wire the vector index into `Corpus`**

In `ts/src/corpus.ts`, extend the imports:

```ts
import { CollisionError, EmbedderRequiredError, RefError } from "./errors.js";
import { type Embedder, type SimilarHit, type Vector, VectorCache, VectorIndex } from "./similarity.js";
```

Add the new fields and constructor argument (replace the existing field block + constructor):

```ts
  readonly store: Store;
  readonly registry?: Registry;
  readonly index: Index;
  readonly searchIndex: SearchIndex;
  readonly embedder?: Embedder;
  readonly vectorCache?: VectorCache;
  readonly vectorIndex?: VectorIndex;

  constructor(root: string, registry?: Registry, embedder?: Embedder) {
    this.store = new Store(root);
    this.registry = registry;
    this.embedder = embedder;
    const nodes = this.store.allNodes();
    this.index = Index.build(nodes);
    this.searchIndex = SearchIndex.build(nodes);
    if (embedder !== undefined) {
      this.vectorCache = new VectorCache(root);
      this.vectorIndex = VectorIndex.build(nodes, embedder, this.vectorCache);
    }
  }
```

Update `add` (prepare before disk, commit last):

```ts
  add(node: Node): Node {
    if (this.registry !== undefined) this.registry.validate(node);
    this.index.assertAddable(node);
    const prepared =
      this.vectorIndex !== undefined
        ? this.vectorIndex.prepare(node, this.embedder as Embedder, this.vectorCache as VectorCache)
        : undefined;
    this.store.writeFile(node);
    this.index.upsert(node);
    this.searchIndex.upsert(node);
    if (this.vectorIndex !== undefined && prepared !== undefined) {
      this.vectorIndex.commit(node, prepared);
    }
    return node;
  }
```

Update `delete` (append the vector removal):

```ts
  delete(nodeId: string): void {
    const uid = this.index.idToUid.get(nodeId);
    if (uid === undefined) throw new RefError(`no live node at ${JSON.stringify(nodeId)}`);
    this.store.deleteFile(nodeId);
    this.index.remove(uid);
    this.searchIndex.remove(uid);
    this.vectorIndex?.remove(uid);
  }
```

Add the three similarity query methods (place them right after `search`):

```ts
  similar(ref: string, k?: number): SimilarHit[] {
    if (this.vectorIndex === undefined) {
      throw new EmbedderRequiredError("similarity requires Corpus(root, registry?, embedder)");
    }
    return this.vectorIndex.similar(this.requireUid(ref), k);
  }

  queryVector(vec: Vector, k?: number): SimilarHit[] {
    if (this.vectorIndex === undefined) {
      throw new EmbedderRequiredError("similarity requires Corpus(root, registry?, embedder)");
    }
    return this.vectorIndex.queryVector(vec, k);
  }

  similarText(text: string, k?: number): SimilarHit[] {
    if (this.vectorIndex === undefined) {
      throw new EmbedderRequiredError("similarity requires Corpus(root, registry?, embedder)");
    }
    return this.vectorIndex.similarText(text, this.embedder as Embedder, k);
  }
```

In `rename`, insert the `prepare` call after the registry-validation block (step 5) and before `const newPath = this.store.writeFile(node);` (step 6), and the `commit` after the final `this.searchIndex.upsert(node);`:

```ts
    // 5. Validate ALL writes before ANY write (fail-early, no partial rename).
    if (this.registry !== undefined) {
      this.registry.validate(node);
      for (const referrer of referrers) this.registry.validate(referrer);
    }

    // 5b. Prepare the renamed node's vector (fail before any disk write).
    const prepared =
      this.vectorIndex !== undefined
        ? this.vectorIndex.prepare(node, this.embedder as Embedder, this.vectorCache as VectorCache)
        : undefined;

    // 6. Commit: renamed node first (crash-atomic), then referrers. Each written once.
    const newPath = this.store.writeFile(node);
    if (oldPath !== newPath) this.store.deleteFile(oldId);
    this.index.upsert(node);
    for (const referrer of referrers) {
      this.store.writeFile(referrer);
      this.index.upsert(referrer);
    }

    this.searchIndex.upsert(node);
    if (this.vectorIndex !== undefined && prepared !== undefined) {
      this.vectorIndex.commit(node, prepared);
    }
    return node;
```

- [ ] **Step 4: Export the new surface from the barrel**

In `ts/src/index.ts`, add `EmbedderRequiredError` to the errors export block (alphabetical), and append a similarity export after the search line:

```ts
export {
  type Embedder,
  type SimilarHit,
  type Vector,
  VectorCache,
  VectorIndex,
  embedText,
  textHash,
  validateNamespace,
  validateTextHash,
} from "./similarity.js";
```

- [ ] **Step 5: Run to verify green**

Run: `rtk npm test -- corpus-similarity`
Expected: PASS. Then `rtk npm test` (full — the existing `corpus.test.ts`, `corpus_parity.test.ts`, `corpus-search.test.ts`, `index-rebuild-equivalence.test.ts` must all stay green, confirming the structural/search seams are untouched), `rtk npm run typecheck`, `rtk npm run check` clean.

- [ ] **Step 6: Commit**

```bash
rtk git add ts/src/corpus.ts ts/src/index.ts ts/tests/corpus-similarity.test.ts
rtk git commit -m "feat(ts-similarity): opt-in Corpus integration with fail-before-mutation ordering"
```

---

### Task 7: Cross-language parity test + docs

Mirror of Python commit `cf5cb43`, but **consume** the frozen fixtures rather than generate them. Assert TS `Corpus` similarity reproduces the committed oracle, and document the TS port in `docs/STANDARD.md`.

**Files:**
- Test: `ts/tests/similarity-parity.test.ts`
- Modify: `docs/STANDARD.md` (append a "TypeScript similarity index" subsection under the existing similarity section)

**Interfaces:**
- Consumes: the committed `fixtures/similarity-corpus/`, `fixtures/similarity.vectors.json`, `fixtures/similarity.oracle.json` (read-only); `Corpus`, `scoreKey`, `embedText`, `Embedder`, `Vector`.
- Produces: nothing new — this is the parity gate. **Do not modify any file under `fixtures/`.**

- [ ] **Step 1: Write the parity test**

Create `ts/tests/similarity-parity.test.ts`. It mirrors `python/tests/test_similarity_parity.py`: a `LookupEmbedder` whose table is built from each parsed node's actual `embedText` (documents keyed by id) plus the queries keyed by text, then asserts `similar`/`queryVector`/`similarText` against the oracle with `scoreKey`-rounded scores.

```ts
import { cpSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import type { Node } from "../src/node.js";
import { scoreKey } from "../src/ranking.js";
import { type Embedder, type SimilarHit, type Vector, embedText } from "../src/similarity.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures/", import.meta.url));
const CORPUS = join(FIXTURES, "similarity-corpus");
const VECTORS = join(FIXTURES, "similarity.vectors.json");
const ORACLE = join(FIXTURES, "similarity.oracle.json");

interface VectorsFile {
  documents: { id: string; vector: number[] }[];
  queries: { text: string; vector: number[] }[];
}
interface OracleCase {
  ref?: string;
  text?: string;
  hits: { id: string; score: number }[];
}
interface OracleFile {
  similar: OracleCase[];
  query_vector: OracleCase[];
  similar_text: OracleCase[];
}

class LookupEmbedder implements Embedder {
  readonly cacheNamespace = "fixture-v1";
  private table: Map<string, Vector>;
  constructor(table: Map<string, Vector>) {
    this.table = table;
  }
  embed(texts: string[]): Vector[] {
    return texts.map((t) => {
      const v = this.table.get(t);
      if (v === undefined) throw new Error(`no vector for ${JSON.stringify(t)}`);
      return v;
    });
  }
}

function buildTable(data: VectorsFile, nodes: Node[]): Map<string, Vector> {
  const byId = new Map(data.documents.map((d) => [d.id, d.vector]));
  const table = new Map<string, Vector>();
  for (const n of nodes) {
    const vec = byId.get(n.id);
    if (vec === undefined) throw new Error(`no frozen vector for ${n.id}`);
    table.set(embedText(n), vec);
  }
  for (const q of data.queries) table.set(q.text, q.vector);
  return table;
}

function rounded(hits: SimilarHit[]): { id: string; score: number }[] {
  return hits.map((h) => ({ id: h.id, score: scoreKey(h.score) }));
}

function expected(hits: { id: string; score: number }[]): { id: string; score: number }[] {
  return hits.map((h) => ({ id: h.id, score: scoreKey(h.score) }));
}

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-sim-parity-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("cross-language similarity oracle", () => {
  it("the fixture corpus has four topics", () => {
    cpSync(CORPUS, root, { recursive: true });
    expect(new Corpus(root).all().length).toBe(4);
  });

  it("TS Corpus similarity over the frozen fixtures matches the shared oracle", () => {
    cpSync(CORPUS, root, { recursive: true });
    const data = JSON.parse(readFileSync(VECTORS, "utf-8")) as VectorsFile;
    const oracle = JSON.parse(readFileSync(ORACLE, "utf-8")) as OracleFile;
    expect(oracle.similar.length).toBeGreaterThan(0);
    expect(oracle.query_vector.length).toBeGreaterThan(0);
    expect(oracle.similar_text.length).toBeGreaterThan(0);

    const nodes = new Corpus(root).all();
    // guard: every corpus node has a frozen document vector
    const ids = new Set(nodes.map((n) => n.id));
    expect(ids).toEqual(new Set(data.documents.map((d) => d.id)));

    const emb = new LookupEmbedder(buildTable(data, nodes));
    const corpus = new Corpus(root, undefined, emb);
    const queryVecByText = new Map(data.queries.map((q) => [q.text, q.vector]));

    for (const c of oracle.similar) {
      expect(rounded(corpus.similar(c.ref as string))).toEqual(expected(c.hits));
    }
    for (const c of oracle.query_vector) {
      const vec = queryVecByText.get(c.text as string) as Vector;
      expect(rounded(corpus.queryVector(vec))).toEqual(expected(c.hits));
    }
    for (const c of oracle.similar_text) {
      expect(rounded(corpus.similarText(c.text as string))).toEqual(expected(c.hits));
    }
  });
});
```

- [ ] **Step 2: Run it to verify green**

Run: `rtk npm test -- similarity-parity`
Expected: PASS — all three oracle sections (`similar`, `query_vector`, `similar_text`) reproduce the committed ranked ids and 6-dp scores. Confirm `fixtures/` is unmodified: `rtk git status --porcelain -- fixtures/` prints nothing.

- [ ] **Step 3: Document the TS port**

In `docs/STANDARD.md`, append a subsection at the end of the "Similarity / embedding index (derived index)" section (after the Parity bullet at the bottom of the file):

```markdown
### TypeScript similarity index

The TypeScript kernel (`ts/src/similarity.ts`) is a semantic port of `nodes.kernel.similarity`:
the same `Embedder` seam (`cacheNamespace`, `embed`), `embedText` contract, content-addressed
raw-vector cache (`<root>/.nodes-index/vectors/<namespace>/<sha256>.json`, atomic writes), and an
in-memory `VectorIndex` of L2-normalized vectors with exact brute-force cosine. It is opt-in via
`new Corpus(root, registry?, embedder?)`; without an embedder the similarity APIs throw
`EmbedderRequiredError`. Queries are `Corpus.similar(ref, k?)` (excludes the node itself),
`Corpus.queryVector(vec, k?)`, and `Corpus.similarText(text, k?)`, returning `SimilarHit[]`
sorted by the shared 6-decimal `scoreKey` (in `ts/src/ranking.ts`) then `id`.

Because model embeddings are not portable across languages, parity is pinned by the same frozen
fixtures Python committed: `fixtures/similarity-corpus/`, `fixtures/similarity.vectors.json`, and
`fixtures/similarity.oracle.json`. Both languages inject a lookup embedder over the frozen vectors
and assert identical ranked ids and 6-dp scores; scores are compared numerically (not
string-compared). On-disk index persistence remains a later plan.
```

Also update the final sentence of the preceding Parity bullet — change "On-disk index persistence and the TypeScript port are later plans." to "On-disk index persistence is a later plan." (the TS port now exists).

- [ ] **Step 4: Commit**

```bash
rtk git add ts/tests/similarity-parity.test.ts docs/STANDARD.md
rtk git commit -m "test(ts-similarity): cross-language parity against frozen oracle; docs"
```

---

## Self-Review (completed by plan author)

**Spec coverage** (against `docs/designs/2026-06-22-nodes-similarity-index-design.md`, realized in `similarity.py`):
- Embedder seam + `embedText` → Task 2. `textHash` + cache layout + atomic writes + raw vectors → Task 3. Path-safety validators → Task 2 (defined) / Task 3 (enforced in `pathFor`). L2 normalize + cosine + shared `scoreKey` → Tasks 4–5 + Task 1. Namespace/dim binding + prepare/commit + `similar` self-exclusion + `k` contract → Tasks 4–5. Opt-in `Corpus` + `EmbedderRequiredError` + mutation ordering → Task 6. Frozen-fixture parity → Task 7. No gaps.

**Placeholder scan:** no TBD/TODO; every code step shows complete code. The one deliberately-simplified test line in Task 6 Step 1 is called out with explicit fallback instructions.

**Type consistency:** `cacheNamespace`, `embedText`, `textHash`, `validateNamespace`, `validateTextHash`, `validateFinite`, `normalize`, `validateK`, `PreparedVector{textHash,namespace,vector}`, `VectorIndex` fields (`vectors`, `idByUid`, `hashByUid`, `dim`, `namespace`), and method signatures (`build`, `prepare`, `commit`, `upsert`, `remove`, `queryVector`, `similar`, `similarText`) are used identically across Tasks 2→7. `Corpus(root, registry?, embedder?)` matches the Python signature order. Barrel exports in Task 6 reference only symbols defined in Tasks 2–5.

**Ordering note for the executor:** Task 2 defines only the exported foundation surface. `validateFinite`, `normalize`, and `validateK` are introduced in the tasks that first *use* them (3/4/5), which keeps biome's no-unused-vars rule satisfied at every commit.
