# Full-Text Search (TypeScript port) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the Python full-text search subsystem (BM25F derived index) to the TypeScript kernel at semantic parity, pinned by the already-committed cross-language fixtures.

**Architecture:** A new `ts/src/search.ts` module mirroring `python/src/nodes/kernel/search.py`: the canonical `tokenize`, an in-memory inverted `SearchIndex` with BM25F scoring, and a `SearchHit` result shape. `Corpus` owns a `searchIndex` beside its structural `Index`, built from one `allNodes()` scan and kept current on `add`/`delete`/`rename`. Parity is asserted against the two fixtures Python already generated and committed (`fixtures/search.tokenizer.json`, `fixtures/search-corpus/` + `fixtures/search.oracle.json`) — this port consumes them, it does not regenerate them.

**Tech Stack:** TypeScript (ESM, `.js` import extensions), Node ≥20, vitest, biome (format + lint, line width 120), `tsc --noEmit` typecheck. No new runtime dependencies — `search.ts` is pure language built-ins (`String.prototype.normalize`, Unicode-property regex, `Math`).

## Current State Note

This plan has since been implemented and remains useful as the historical TypeScript full-text search port. Current `ts/src/search.ts` still owns canonical tokenization, BM25F scoring, `SearchIndex`, and `SearchHit`, and `Corpus.search(query, limit?)` remains the public query surface.

There are three current-code details to keep in mind when reading the task snippets below:

- Later similarity work extracted `scoreKey` to `ts/src/ranking.ts`; import it from `../src/ranking.js` or `./ranking.js`, not from `search.ts`.
- Later snapshot persistence added `SearchIndex.toDict()` / `fromDict()` and changed `Corpus` construction so it may load/reconcile snapshots instead of always building from `Store.allNodes()`.
- The `docs/format.md` update in Task 5 has already been applied and later extended with similarity and snapshot persistence sections.

## Global Constraints

These bind every task. Values are copied verbatim from the spec (`docs/designs/2026-06-22-nodes-fulltext-search-design.md`) and the committed Python implementation (`python/src/nodes/kernel/search.py`).

- **Tokenizer (the parity contract):** `text.normalize("NFC").toLowerCase()`, then split into maximal Unicode-alphanumeric runs via `/[\p{L}\p{N}]+/gu` (`s.match(re) ?? []`), then drop stop-words. No stemming. Document tokenization keeps duplicates; query-side dedup happens in `search`. Empty / whitespace / all-separator / all-stop-word input → `[]`.
- **Stop-word list — exactly these 33 words** (a module-level `Set`): `a an and are as at be but by for if in into is it no not of on or such that the their then there these they this to was will with`.
- **Constants (exact):** `K1 = 1.5`, `B = 0.75`, `TITLE_BOOST = 2.0`, `BODY_BOOST = 1.0`.
- **BM25F scoring (exact formulas):**
  - `idf(t) = ln(1 + (N − df + 0.5) / (df + 0.5))` — non-negative Lucene form; `df` counts a document once if `t` is in its title **or** body.
  - `tf'(t,d) = Σ_field boost_f · tf_f / (1 − B + B · len_f / avglen_f)`, fields combined in fixed order **title then body**; when `avglen_f == 0` the field's denominator is `1` (its `tf_f` is necessarily 0, so it contributes 0) — guard the division.
  - per-term `score = idf · (K1 + 1) · tf' / (K1 + tf')`.
  - document score = sum of per-term scores over the **deduped** query terms present in the doc.
- **Determinism (parity-critical):** query terms are deduped and **sorted by Unicode code-point order** using an explicit comparator over code points — NOT the default `Array.sort()` (which is UTF-16 code-unit order and differs for non-BMP characters). Per-term scores are summed in that sorted-term order.
- **Ranking key:** `scoreKey(score) = Math.floor(score * 1_000_000 + 0.5) / 1_000_000`; sort by `(scoreKey desc, id asc)`.
- **`matchedTerms`:** the deduped query terms present in the doc, sorted by the same code-point comparator.
- **`limit` contract:** `undefined` = unbounded; otherwise must be an integer `> 0`. `0`, negative, or non-integer (e.g. `1.5`) → throw `RangeError` (the idiomatic JS equivalent of Python's `ValueError`; the parity oracle does not cover error type). Note: TypeScript's type system already rejects `boolean`/`string`/float-typed `limit` at compile time, so the runtime guard's observable cases are `0`, negatives, and non-integers.
- **Mutation ordering (mirror the structural index):** `add` and `delete` are disk-first, then both in-memory indexes update together. `rename` stays best-effort and is **not** refactored — it adds exactly one `searchIndex.upsert(node)` for the renamed node before returning.
- **Parity, not bit-identity:** scores are not asserted bit-identical across languages. The contract is the two committed fixtures: identical ranked `id` order and scores equal at 6 decimal places. When comparing oracle scores, parse them as numbers and compare the `scoreKey`-rounded value — do **not** string-compare (the oracle prints `0.34081`, a JSON trailing-zero truncation of `0.340810`).
- **TS conventions:** camelCase fields/methods (`idByUid`, `matchedTerms`, `scoreKey`, `codepointSorted`), SCREAMING_CASE module constants, `.js` import extensions, `type`-only imports for types, biome line width 120. No `cd &&` chains needed in the plan — commands below assume the implementer runs from `~/d/nodes/ts`.

**Gate for every task:** from `~/d/nodes/ts`, `rtk npm test` (vitest) green, `rtk npm run typecheck` (`tsc --noEmit`) clean, `rtk npm run check` (biome) clean.

---

### Task 1: Tokenizer + parity helpers + tokenizer oracle

Current-code note: this task originally placed `scoreKey` in `search.ts`. Current code exports `scoreKey` from `ts/src/ranking.ts`; the tokenizer helpers still live in `search.ts`.

**Files:**
- Create: `ts/src/search.ts`
- Test: `ts/tests/search-tokenizer.test.ts`

**Interfaces:**
- Consumes: nothing (pure built-ins). Reads the committed `fixtures/search.tokenizer.json` in the test.
- Produces: `tokenize(text: string): string[]`, `STOP_WORDS: ReadonlySet<string>`, `scoreKey(score: number): number`, `codepointSorted(values: Iterable<string>): string[]`. Later tasks add `SearchHit`, the constants, and `SearchIndex` to this same module.

- [ ] **Step 1: Write the failing tokenizer + helper tests**

Create `ts/tests/search-tokenizer.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { STOP_WORDS, codepointSorted, scoreKey, tokenize } from "../src/search.js";

const ORACLE = fileURLToPath(new URL("../../fixtures/search.tokenizer.json", import.meta.url));

describe("tokenize", () => {
  it.each([
    ["", []],
    ["   \t\n ", []],
    ["The Quick Brown Fox", ["quick", "brown", "fox"]], // 'the' is a stop word; lowercased
    ["the THE The", []], // all stop words
    ["well-known", ["well", "known"]], // hyphen separates
    ["state_of_art", ["state", "art"]], // underscore separates; 'of' is a stop word
    ["don't", ["don", "t"]], // apostrophe separates
    ["3.14 and 2", ["3", "14", "2"]], // '.' separates; 'and' is a stop word
    ["café", ["café"]], // composed (U+00E9)
    ["café", ["café"]], // decomposed e + U+0301 combining acute -> NFC -> café
    ["Hello МИР", ["hello", "мир"]], // Cyrillic, lowercased
    ["hello 世界", ["hello", "世界"]], // CJK run is one token
    ["data\u{1D7D9}point", ["data\u{1D7D9}point"]], // non-BMP digit stays inside one token
  ])("tokenizes %j", (text, expected) => {
    expect(tokenize(text as string)).toEqual(expected);
  });

  it("keeps duplicate tokens in document order (term frequency is meaningful)", () => {
    expect(tokenize("alpha beta alpha")).toEqual(["alpha", "beta", "alpha"]);
  });
});

describe("STOP_WORDS", () => {
  it("has exactly 33 words including the and with", () => {
    expect(STOP_WORDS.size).toBe(33);
    expect(STOP_WORDS.has("the")).toBe(true);
    expect(STOP_WORDS.has("with")).toBe(true);
  });
});

describe("scoreKey", () => {
  it("rounds half-up to 6 decimal places", () => {
    // Inputs kept clear of the exact .5 boundary so float representation can't flip them.
    expect(scoreKey(1.2345674)).toBe(1.234567); // rounds down
    expect(scoreKey(1.2345678)).toBe(1.234568); // rounds up
    expect(scoreKey(0)).toBe(0);
  });
});

describe("codepointSorted", () => {
  it("sorts by Unicode code point, not UTF-16 code unit", () => {
    // 'ａ' U+FF41 (65345) < '𝟙' U+1D7D9 (120793) by code point, so 'ａ' must sort first.
    // Default Array.sort() compares UTF-16 units: 0xFF41 (65345) > 0xD835 (55349, '𝟙' lead
    // surrogate) would WRONGLY place '𝟙' first. Both tokens are NFC- and lowercase-stable.
    expect(codepointSorted(["\u{1D7D9}", "ａ"])).toEqual(["ａ", "\u{1D7D9}"]);
  });

  it("dedup is the caller's job — it sorts whatever it is given", () => {
    expect(codepointSorted(new Set(["b", "a", "b"]))).toEqual(["a", "b"]);
  });
});

describe("tokenizer oracle (cross-language freeze)", () => {
  it("reproduces every committed case exactly", () => {
    const cases = JSON.parse(readFileSync(ORACLE, "utf-8")) as { input: string; tokens: string[] }[];
    expect(cases.length).toBeGreaterThan(0);
    for (const c of cases) {
      expect(tokenize(c.input)).toEqual(c.tokens);
    }
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npm test -- tests/search-tokenizer.test.ts`
Expected: FAIL — cannot resolve `../src/search.js` (module does not exist yet).

- [ ] **Step 3: Create `ts/src/search.ts` with the tokenizer and helpers**

```ts
/** Fixed English stop-word list (33 words), frozen by the tokenizer oracle. */
export const STOP_WORDS: ReadonlySet<string> = new Set([
  "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if",
  "in", "into", "is", "it", "no", "not", "of", "on", "or", "such", "that",
  "the", "their", "then", "there", "these", "they", "this", "to", "was",
  "will", "with",
]);

// Maximal runs of Unicode alphanumerics (\p{L} ∪ \p{N}); everything else separates.
// This is the parity twin of Python's re.findall(r"[^\W_]+", s).
const TOKEN_RE = /[\p{L}\p{N}]+/gu;

/** Half-up rounding to 6 decimal places — the shared ranking/parity key. Scores are
 * non-negative, so this floor-based half-up is correct and identical to Python's. */
export function scoreKey(score: number): number {
  return Math.floor(score * 1_000_000 + 0.5) / 1_000_000;
}

// Compare by Unicode code point. Array.from iterates by code point (surrogate-pair aware),
// so this is the explicit comparator the spec requires instead of default UTF-16 sort.
function compareCodepoints(a: string, b: string): number {
  const ca = Array.from(a);
  const cb = Array.from(b);
  const len = Math.min(ca.length, cb.length);
  for (let i = 0; i < len; i++) {
    const x = ca[i].codePointAt(0) as number;
    const y = cb[i].codePointAt(0) as number;
    if (x !== y) return x - y;
  }
  return ca.length - cb.length;
}

/** Sort by Unicode code-point order — mirrors Python's default string sort (which is
 * already code-point order) and is the cross-language ordering contract. */
export function codepointSorted(values: Iterable<string>): string[] {
  return [...values].sort(compareCodepoints);
}

/** NFC-normalize, lowercase, split into Unicode-alphanumeric runs, drop stop words.
 * Document tokenization keeps duplicates; query-side dedup happens in SearchIndex.search. */
export function tokenize(text: string): string[] {
  const normalized = text.normalize("NFC").toLowerCase();
  const matches = normalized.match(TOKEN_RE) ?? [];
  return matches.filter((tok) => !STOP_WORDS.has(tok));
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk npm test -- tests/search-tokenizer.test.ts`
Expected: PASS (all cases, including the oracle).

- [ ] **Step 5: Run the full gate**

Run: `rtk npm test` then `rtk npm run typecheck` then `rtk npm run check`
Expected: all green/clean.

- [ ] **Step 6: Commit**

```bash
rtk git add ts/src/search.ts ts/tests/search-tokenizer.test.ts
rtk git commit -m "feat(ts/search): canonical tokenizer + code-point sort + scoreKey; tokenizer oracle parity"
```

---

### Task 2: `SearchIndex` state — build / upsert / remove

**Files:**
- Modify: `ts/src/search.ts`
- Test: `ts/tests/search-index.test.ts`

**Interfaces:**
- Consumes: `tokenize` (Task 1); `CollisionError` from `./errors.js`; `Node` from `./node.js`; `makeNode` from `./node.js` (tests).
- Produces: the constants `K1`, `B`, `TITLE_BOOST`, `BODY_BOOST`; `interface SearchHit { id: string; uid: string; score: number; matchedTerms: string[] }`; `class SearchIndex` with public fields `postings: Map<string, Map<string, [number, number]>>`, `lengths: Map<string, [number, number]>`, `idByUid: Map<string, string>`, `totalTitle: number`, `totalBody: number`; getter `n`; `static build(nodes): SearchIndex`; `upsert(node)`; `remove(uid)`. (`search` is added in Task 3.)

- [ ] **Step 1: Write the failing state tests**

Create `ts/tests/search-index.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { CollisionError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { SearchIndex } from "../src/search.js";

function norm(idx: SearchIndex): unknown {
  const postings: Record<string, [string, [number, number]][]> = {};
  for (const [term, docs] of idx.postings) {
    postings[term] = [...docs.entries()].sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  }
  return {
    postings,
    lengths: [...idx.lengths.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)),
    idByUid: [...idx.idByUid.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)),
    n: idx.n,
    totals: [idx.totalTitle, idx.totalBody],
  };
}

describe("SearchIndex state", () => {
  it("upsert records per-field term frequencies and lengths", () => {
    const idx = new SearchIndex();
    const n = makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "alpha alpha beta" });
    idx.upsert(n);
    expect(idx.postings.get("alpha")?.get(n.uid)).toEqual([1, 2]); // 1 in title, 2 in body
    expect(idx.postings.get("beta")?.get(n.uid)).toEqual([0, 1]);
    expect(idx.lengths.get(n.uid)).toEqual([1, 3]);
    expect(idx.idByUid.get(n.uid)).toBe("topic:a");
    expect(idx.n).toBe(1);
  });

  it("upsert replaces stale postings, it does not duplicate", () => {
    const idx = new SearchIndex();
    const n = makeNode({ id: "topic:a", kind: "topic", title: "", body: "alpha alpha" });
    idx.upsert(n);
    expect(idx.postings.get("alpha")?.get(n.uid)).toEqual([0, 2]);
    n.body = "beta";
    idx.upsert(n);
    expect(idx.postings.has("alpha")).toBe(false); // stale postings dropped
    expect(idx.postings.get("beta")?.get(n.uid)).toEqual([0, 1]);
    expect(idx.lengths.get(n.uid)).toEqual([0, 1]);
    expect(idx.n).toBe(1);
  });

  it("remove drops everything and totals, and is a no-op when absent", () => {
    const idx = new SearchIndex();
    const n = makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "beta" });
    idx.upsert(n);
    idx.remove(n.uid);
    expect(idx.n).toBe(0);
    expect(idx.postings.size).toBe(0);
    expect(idx.lengths.size).toBe(0);
    expect(idx.idByUid.size).toBe(0);
    expect([idx.totalTitle, idx.totalBody]).toEqual([0, 0]);
    idx.remove("not-present"); // no throw, no change
    expect(idx.n).toBe(0);
  });

  it("empty text still counts as a document slot", () => {
    const idx = new SearchIndex();
    const n = makeNode({ id: "topic:a", kind: "topic", title: "", body: "" });
    idx.upsert(n);
    expect(idx.n).toBe(1);
    expect(idx.lengths.get(n.uid)).toEqual([0, 0]);
    expect(idx.postings.size).toBe(0);
  });

  it("build rejects a duplicate uid with CollisionError", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A", uid: "dup" });
    const b = makeNode({ id: "topic:b", kind: "topic", title: "B", uid: "dup" });
    expect(() => SearchIndex.build([a, b])).toThrow(CollisionError);
  });

  it("incremental mutation matches a fresh rebuild", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "Alpha", body: "alpha beta" });
    const b = makeNode({ id: "topic:b", kind: "topic", title: "Beta", body: "gamma delta" });
    const c = makeNode({ id: "topic:c", kind: "topic", title: "C", body: "alpha" });
    const idx = new SearchIndex();
    idx.upsert(a);
    idx.upsert(b);
    a.body = "alpha gamma";
    idx.upsert(a); // overwrite a
    idx.remove(b.uid); // drop b
    idx.upsert(c);
    expect(norm(idx)).toEqual(norm(SearchIndex.build([a, c])));
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npm test -- tests/search-index.test.ts`
Expected: FAIL — `SearchIndex` is not exported from `../src/search.js`.

- [ ] **Step 3: Add the constants, `SearchHit`, and `SearchIndex` to `ts/src/search.ts`**

Ensure the import block at the top of `search.ts` is:

```ts
import { CollisionError } from "./errors.js";
import type { Node } from "./node.js";
```

Append after `tokenize` (constants may go near the top beside `scoreKey` if preferred — keep them module-level and exported):

```ts
export const K1 = 1.5;
export const B = 0.75;
export const TITLE_BOOST = 2.0;
export const BODY_BOOST = 1.0;

export interface SearchHit {
  id: string;
  uid: string;
  score: number;
  matchedTerms: string[];
}

/** In-memory inverted index over node title+body. Pure data; no file I/O. */
export class SearchIndex {
  postings = new Map<string, Map<string, [number, number]>>(); // term -> uid -> [titleTf, bodyTf]
  lengths = new Map<string, [number, number]>(); // uid -> [titleLen, bodyLen]
  idByUid = new Map<string, string>();
  totalTitle = 0;
  totalBody = 0;

  get n(): number {
    return this.lengths.size;
  }

  static build(nodes: Iterable<Node>): SearchIndex {
    const idx = new SearchIndex();
    for (const node of nodes) {
      if (idx.lengths.has(node.uid)) {
        throw new CollisionError(`duplicate uid ${JSON.stringify(node.uid)} in corpus`);
      }
      idx.upsert(node);
    }
    return idx;
  }

  private static counts(tokens: string[]): Map<string, number> {
    const counts = new Map<string, number>();
    for (const tok of tokens) counts.set(tok, (counts.get(tok) ?? 0) + 1);
    return counts;
  }

  upsert(node: Node): void {
    if (this.lengths.has(node.uid)) this.drop(node.uid);
    const titleTokens = tokenize(node.title);
    const bodyTokens = tokenize(node.body);
    const titleCounts = SearchIndex.counts(titleTokens);
    const bodyCounts = SearchIndex.counts(bodyTokens);
    const terms = new Set<string>([...titleCounts.keys(), ...bodyCounts.keys()]);
    for (const term of terms) {
      let docs = this.postings.get(term);
      if (docs === undefined) {
        docs = new Map<string, [number, number]>();
        this.postings.set(term, docs);
      }
      docs.set(node.uid, [titleCounts.get(term) ?? 0, bodyCounts.get(term) ?? 0]);
    }
    this.lengths.set(node.uid, [titleTokens.length, bodyTokens.length]);
    this.idByUid.set(node.uid, node.id);
    this.totalTitle += titleTokens.length;
    this.totalBody += bodyTokens.length;
  }

  remove(uid: string): void {
    this.drop(uid);
  }

  private drop(uid: string): void {
    const lengths = this.lengths.get(uid);
    if (lengths === undefined) return;
    this.totalTitle -= lengths[0];
    this.totalBody -= lengths[1];
    this.lengths.delete(uid);
    this.idByUid.delete(uid);
    for (const [term, docs] of [...this.postings]) {
      if (docs.has(uid)) {
        docs.delete(uid);
        if (docs.size === 0) this.postings.delete(term);
      }
    }
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk npm test -- tests/search-index.test.ts`
Expected: PASS.

- [ ] **Step 5: Run the full gate**

Run: `rtk npm test` then `rtk npm run typecheck` then `rtk npm run check`
Expected: all green/clean.

- [ ] **Step 6: Commit**

```bash
rtk git add ts/src/search.ts ts/tests/search-index.test.ts
rtk git commit -m "feat(ts/search): SearchIndex build/upsert/remove + rebuild equivalence"
```

---

### Task 3: BM25F scoring + `search` query API

**Files:**
- Modify: `ts/src/search.ts`
- Test: `ts/tests/search-query.test.ts`

**Interfaces:**
- Consumes: `SearchIndex` state + `tokenize`, `codepointSorted`, `scoreKey`, the constants (Tasks 1–2); `makeNode` (tests).
- Produces: `SearchIndex.search(query: string, limit?: number): SearchHit[]`.

- [ ] **Step 1: Write the failing query tests**

Create `ts/tests/search-query.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { SearchIndex } from "../src/search.js";

function twoDocIndex(): SearchIndex {
  const idx = new SearchIndex();
  idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "alpha beta" }));
  idx.upsert(makeNode({ id: "topic:b", kind: "topic", title: "beta", body: "gamma" }));
  return idx;
}

describe("SearchIndex.search (BM25F)", () => {
  it("matches a hand-computed BM25F score", () => {
    // N=2, avgTitle=1.0, avgBody=1.5. Query "alpha" hits only topic:a (titleTf=1, bodyTf=1, bodyLen=2).
    // idf = ln(2); tf' = 2.0*1/1.0 + 1.0*1/1.25 = 2.8; score = ln(2)*2.5*2.8/(1.5+2.8).
    const expected = (Math.log(2.0) * 2.5 * 2.8) / 4.3;
    const hits = twoDocIndex().search("alpha");
    expect(hits.map((h) => h.id)).toEqual(["topic:a"]);
    expect(hits[0].score).toBeCloseTo(expected, 12);
    expect(hits[0].uid).not.toBe("");
    expect(hits[0].matchedTerms).toEqual(["alpha"]);
  });

  it("ranks a title match above a body match (title boost)", () => {
    // "beta" is in topic:b's TITLE and topic:a's BODY -> title boost ranks b first.
    expect(twoDocIndex().search("beta").map((h) => h.id)).toEqual(["topic:b", "topic:a"]);
  });

  it("breaks rounded-score ties by id ascending", () => {
    const idx = new SearchIndex();
    idx.upsert(makeNode({ id: "topic:b", kind: "topic", title: "x", body: "z" }));
    idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "x", body: "z" }));
    expect(idx.search("x").map((h) => h.id)).toEqual(["topic:a", "topic:b"]);
  });

  it("matchedTerms is the sorted deduped subset present in the doc", () => {
    const idx = new SearchIndex();
    idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "gamma" }));
    const hits = idx.search("gamma alpha zeta"); // zeta absent; alpha repeated below
    expect(hits[0].matchedTerms).toEqual(["alpha", "gamma"]);
  });

  it("orders query terms by Unicode code point, not UTF-16 code unit", () => {
    // Title 'ａ' U+FF41 (65345), body '𝟙' U+1D7D9 (120793). Both NFC- and lowercase-stable.
    // Code-point order -> ["ａ","𝟙"]. Default UTF-16 sort would compare 0xFF41 (65345) vs the
    // surrogate lead 0xD835 (55349) and WRONGLY yield ["𝟙","ａ"]. This pins the comparator.
    const idx = new SearchIndex();
    idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "ａ", body: "\u{1D7D9}" }));
    const hits = idx.search("\u{1D7D9} ａ");
    expect(hits[0].matchedTerms).toEqual(["ａ", "\u{1D7D9}"]);
  });

  it("returns [] for empty, stop-word-only, and all-absent queries", () => {
    const idx = new SearchIndex();
    idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "the cat" }));
    expect(idx.search("")).toEqual([]);
    expect(idx.search("   ")).toEqual([]);
    expect(idx.search("the")).toEqual([]); // stop word only
    expect(idx.search("zeta")).toEqual([]); // term absent
  });

  it("honors limit and treats undefined as unbounded", () => {
    const idx = new SearchIndex();
    for (const slug of ["a", "b", "c"]) {
      idx.upsert(makeNode({ id: `topic:${slug}`, kind: "topic", title: "alpha", body: "alpha" }));
    }
    expect(idx.search("alpha").length).toBe(3);
    expect(idx.search("alpha", 2).length).toBe(2);
    expect(idx.search("alpha", undefined).length).toBe(3);
  });

  it("rejects a non-positive or non-integer limit with RangeError", () => {
    const idx = new SearchIndex();
    idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "" }));
    for (const bad of [0, -1, 1.5]) {
      expect(() => idx.search("alpha", bad)).toThrow(RangeError);
    }
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npm test -- tests/search-query.test.ts`
Expected: FAIL — `idx.search is not a function` / type error (method not defined yet).

- [ ] **Step 3: Add `search` to `SearchIndex` in `ts/src/search.ts`**

Insert this method into the `SearchIndex` class, after `remove` and before the private `drop`:

```ts
  search(query: string, limit?: number): SearchHit[] {
    if (limit !== undefined && (!Number.isInteger(limit) || limit <= 0)) {
      throw new RangeError(`limit must be a positive integer or undefined, got ${JSON.stringify(limit)}`);
    }
    const terms = codepointSorted(new Set(tokenize(query))); // dedup + code-point order
    if (terms.length === 0) return [];

    const n = this.n;
    const avgTitle = n > 0 ? this.totalTitle / n : 0;
    const avgBody = n > 0 ? this.totalBody / n : 0;

    const scores = new Map<string, number>();
    const matched = new Map<string, string[]>();
    for (const term of terms) {
      const docs = this.postings.get(term);
      if (docs === undefined) continue;
      const df = docs.size;
      const idf = Math.log(1 + (n - df + 0.5) / (df + 0.5));
      for (const [uid, [titleTf, bodyTf]] of docs) {
        const [titleLen, bodyLen] = this.lengths.get(uid) as [number, number];
        let tfPrime = 0;
        if (titleTf > 0) {
          const denom = avgTitle > 0 ? 1 - B + B * (titleLen / avgTitle) : 1;
          tfPrime += (TITLE_BOOST * titleTf) / denom;
        }
        if (bodyTf > 0) {
          const denom = avgBody > 0 ? 1 - B + B * (bodyLen / avgBody) : 1;
          tfPrime += (BODY_BOOST * bodyTf) / denom;
        }
        scores.set(uid, (scores.get(uid) ?? 0) + (idf * (K1 + 1) * tfPrime) / (K1 + tfPrime));
        const m = matched.get(uid);
        if (m === undefined) matched.set(uid, [term]);
        else m.push(term);
      }
    }

    const hits: SearchHit[] = [];
    for (const [uid, score] of scores) {
      hits.push({
        id: this.idByUid.get(uid) as string,
        uid,
        score,
        matchedTerms: codepointSorted(matched.get(uid) as string[]),
      });
    }
    hits.sort((a, b) => {
      const ka = scoreKey(a.score);
      const kb = scoreKey(b.score);
      if (ka !== kb) return kb - ka; // scoreKey descending
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; // id ascending
    });
    return limit === undefined ? hits : hits.slice(0, limit);
  }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk npm test -- tests/search-query.test.ts`
Expected: PASS.

- [ ] **Step 5: Run the full gate**

Run: `rtk npm test` then `rtk npm run typecheck` then `rtk npm run check`
Expected: all green/clean.

- [ ] **Step 6: Commit**

```bash
rtk git add ts/src/search.ts ts/tests/search-query.test.ts
rtk git commit -m "feat(ts/search): BM25F scoring + ranked search query API"
```

---

### Task 4: `Corpus` integration + barrel exports

Current-code note: current `Corpus` construction is no longer just `const nodes = this.store.allNodes(); this.index = Index.build(nodes); this.searchIndex = SearchIndex.build(nodes)`. Snapshot load/reconcile and optional vector-index construction now participate in initialization.

**Files:**
- Modify: `ts/src/corpus.ts`
- Modify: `ts/src/index.ts`
- Test: `ts/tests/corpus-search.test.ts`

**Interfaces:**
- Consumes: `SearchIndex`, `SearchHit` (Tasks 2–3); existing `Corpus`, `Index`, `Store` (`ts/src/corpus.ts`).
- Produces: `Corpus.searchIndex: SearchIndex`; `Corpus.search(query: string, limit?: number): SearchHit[]`. Barrel re-exports `SearchIndex`, `SearchHit`, `tokenize`, `scoreKey`.

- [ ] **Step 1: Write the failing integration tests**

Create `ts/tests/corpus-search.test.ts`:

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { makeNode } from "../src/node.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-search-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function seed(c: Corpus): void {
  c.add(makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "alpha beta" }));
  c.add(makeNode({ id: "topic:b", kind: "topic", title: "beta", body: "gamma" }));
}

describe("Corpus full-text search", () => {
  it("ranks title above body after add", () => {
    const c = new Corpus(root);
    seed(c);
    expect(c.search("beta").map((h) => h.id)).toEqual(["topic:b", "topic:a"]);
  });

  it("reflects delete", () => {
    const c = new Corpus(root);
    seed(c);
    c.delete("topic:b");
    expect(c.search("beta").map((h) => h.id)).toEqual(["topic:a"]); // only the body match remains
  });

  it("reflects rename and the hit carries the new id", () => {
    const c = new Corpus(root);
    seed(c);
    c.rename("topic:a", "topic:a2");
    expect(c.search("alpha").map((h) => h.id)).toEqual(["topic:a2"]);
  });

  it("rebuilds equivalently from disk on a fresh Corpus", () => {
    const c = new Corpus(root);
    seed(c);
    const fresh = new Corpus(root); // second corpus scans the same dir
    expect(fresh.search("beta").map((h) => h.id)).toEqual(c.search("beta").map((h) => h.id));
  });

  it("honors limit through the corpus", () => {
    const c = new Corpus(root);
    seed(c);
    expect(c.search("beta", 1).length).toBe(1);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npm test -- tests/corpus-search.test.ts`
Expected: FAIL — `c.search is not a function`.

- [ ] **Step 3: Wire `SearchIndex` into `Corpus`**

In `ts/src/corpus.ts`, add the import (with the other imports):

```ts
import { SearchIndex, type SearchHit } from "./search.js";
```

Add the field beside `index`:

```ts
  readonly index: Index;
  readonly searchIndex: SearchIndex;
```

Replace the constructor body so both indexes build from one scan:

```ts
  constructor(root: string, registry?: Registry) {
    this.store = new Store(root);
    this.registry = registry;
    const nodes = this.store.allNodes();
    this.index = Index.build(nodes);
    this.searchIndex = SearchIndex.build(nodes);
  }
```

In `add`, after `this.index.upsert(node);` add:

```ts
    this.searchIndex.upsert(node);
```

In `delete`, after `this.index.remove(uid);` add:

```ts
    this.searchIndex.remove(uid);
```

In `rename`, immediately before `return node;` add exactly one line (the renamed node's uid is unchanged and its title/body are untouched by rename — only `idByUid` changes; referrers' searchable text is unchanged so they need no search-index update):

```ts
    this.searchIndex.upsert(node);
```

Add the query method (e.g. after `neighbors`, mirroring the Python placement near the other read APIs):

```ts
  search(query: string, limit?: number): SearchHit[] {
    return this.searchIndex.search(query, limit);
  }
```

- [ ] **Step 4: Add barrel exports**

In `ts/src/index.ts`, append:

```ts
export { SearchIndex, type SearchHit, scoreKey, tokenize } from "./search.js";
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `rtk npm test -- tests/corpus-search.test.ts`
Expected: PASS.

- [ ] **Step 6: Run the full gate**

Run: `rtk npm test` then `rtk npm run typecheck` then `rtk npm run check`
Expected: all green/clean — including the existing `index-rebuild-equivalence` and `corpus_parity` suites (the single-scan constructor change must not regress them).

- [ ] **Step 7: Commit**

```bash
rtk git add ts/src/corpus.ts ts/src/index.ts ts/tests/corpus-search.test.ts
rtk git commit -m "feat(ts/search): Corpus.search + keep search index current on add/delete/rename; barrel exports"
```

---

### Task 5: Cross-language ranking oracle parity + docs

**Files:**
- Test: `ts/tests/search-parity.test.ts`
- Modify: `docs/format.md`

**Interfaces:**
- Consumes: `Corpus` (Task 4); the committed `fixtures/search-corpus/` and `fixtures/search.oracle.json` (generated by Python in Plan 7; this task only reads them).
- Produces: nothing — this is the crowning parity gate plus documentation.

- [ ] **Step 1: Write the failing parity test**

Create `ts/tests/search-parity.test.ts` (mirrors `corpus_parity.test.ts`):

```ts
import { cpSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { scoreKey } from "../src/search.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures/", import.meta.url));

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-search-parity-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("cross-language ranking oracle", () => {
  it("TS Corpus.search over the fixture corpus matches the shared oracle", () => {
    cpSync(join(FIXTURES, "search-corpus"), root, { recursive: true });
    const c = new Corpus(root);
    const oracle = JSON.parse(readFileSync(join(FIXTURES, "search.oracle.json"), "utf-8")) as {
      query: string;
      hits: { id: string; score: number }[];
    }[];
    expect(oracle.length).toBeGreaterThan(0);
    for (const c0 of oracle) {
      const actual = c.search(c0.query).map((h) => ({ id: h.id, score: scoreKey(h.score) }));
      // Compare the rounded score numerically (the oracle prints 0.34081, a JSON trailing-zero
      // truncation of 0.340810) — scoreKey(parsed) round-trips both to the same number.
      const expected = c0.hits.map((h) => ({ id: h.id, score: scoreKey(h.score) }));
      expect(actual).toEqual(expected);
    }
  });

  it("the fixture corpus has four topics", () => {
    cpSync(join(FIXTURES, "search-corpus"), root, { recursive: true });
    expect(new Corpus(root).all().length).toBe(4);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails, then passes**

Run: `rtk npm test -- tests/search-parity.test.ts`
Expected: PASS immediately (all production code already exists; this test only consumes committed fixtures). If it FAILS, the failure is a real Python↔TS ranking divergence — stop and report it; do not edit the fixtures (they are the Python-frozen oracle).

- [ ] **Step 3: Update `docs/format.md`**

(a) Update the "Known kernel limitations" bullet at `docs/format.md:46-48`. Replace:

```
- No embeddings/similarity index yet. (Full-text search is now implemented in the
  Python kernel — see "Full-text search (derived index)" below; the TypeScript port
  is a later plan.)
```

with:

```
- No embeddings/similarity index yet. (Full-text search is implemented in both the
  Python and TypeScript kernels — see "Full-text search (derived index)" below.)
```

(b) Append a TypeScript subsection at the end of the "Full-text search (derived index)" section (after the line `later plan.` at `docs/format.md:147`):

```markdown

### TypeScript full-text search

The TypeScript kernel (`ts/src/search.ts`) is a semantic port of `nodes.kernel.search`:
the same tokenizer, BM25F scoring, constants, and `SearchIndex` operations, exposed as
`Corpus.search(query, limit?) -> SearchHit[]` (`SearchHit` carries `id`, `uid`, `score`,
`matchedTerms`). Query-term ordering uses an explicit Unicode code-point comparator — not
JavaScript's default UTF-16 code-unit sort — so non-BMP tokens order identically to Python.

Parity is pinned by the same two fixtures Python generated: `fixtures/search.tokenizer.json`
(the tokenizer freeze) and `fixtures/search-corpus/` + `fixtures/search.oracle.json` (the
ranking freeze). Both languages assert ranked ids and 6-decimal scores against them. Scores
are not claimed bit-identical; the 6-dp `scoreKey` is the cross-language contract, and oracle
scores are compared numerically (not string-compared) to absorb JSON trailing-zero formatting.
```

- [ ] **Step 4: Run the full gate**

Run: `rtk npm test` then `rtk npm run typecheck` then `rtk npm run check`
Expected: all green/clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/tests/search-parity.test.ts docs/format.md
rtk git commit -m "test(ts/search): cross-language ranking oracle parity; docs"
```

---

## Self-Review

**Spec coverage** (`docs/designs/2026-06-22-nodes-fulltext-search-design.md`):
- §3 tokenizer (NFC → lowercase → `\p{L}\p{N}` runs → 33 stop-words; dups kept) → Task 1. §3.2 oracle (incl. NFD↔NFC, mixed scripts, non-BMP) → Task 1 oracle test.
- §4 BM25F (idf, tf' title-then-body with avglen guard, `(K1+1)` numerator, deduped sum) + §4.1 constants + §4.2 determinism (code-point comparator, `scoreKey`, sort key) → Tasks 1 (helpers) + 3 (scoring).
- §5 `SearchIndex` state + build/upsert/remove (dup-uid → `CollisionError`, empty-text doc slot) → Task 2. Rebuild-equivalence (§9) → Task 2.
- §6 query API + `SearchHit` (matchedTerms sorted/deduped) → Task 3.
- §7 Corpus integration (single scan; add/delete disk-first then both indexes; rename one extra upsert, not refactored) → Task 4.
- §8 ranking oracle parity → Task 5. §9 testing strategy → Tasks 1–5. §10 errors (`limit` → `RangeError`; zero-match → `[]`; `build` `CollisionError`) → Tasks 2–3.

**Placeholder scan:** none — every code step shows complete code; every run step shows the command and expected result.

**Type consistency:** `tokenize`, `codepointSorted`, `scoreKey`, `SearchHit{id,uid,score,matchedTerms}`, `SearchIndex.{postings,lengths,idByUid,totalTitle,totalBody,n,build,upsert,remove,search}`, `Corpus.{searchIndex,search}` are named identically across Tasks 1→5 and match the existing TS kernel naming (`idByUid` mirrors the structural index's public-field style; `Map`/tuple state mirrors Python's dict/tuple state). `limit` is `number | undefined` everywhere; `RangeError` is the single throw type for the limit contract.

**Parity note for the executor:** the oracle fixtures were frozen from the Python implementation in Plan 7. A green Task 5 means the TS port reproduces Python's ranking exactly; a red Task 5 is a genuine divergence to investigate in `search.ts` (most likely the tokenizer regex, NFC/lowercase order, or the code-point comparator), never a reason to edit the fixtures.
