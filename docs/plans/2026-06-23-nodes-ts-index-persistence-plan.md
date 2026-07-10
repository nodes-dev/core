# TypeScript Index-Persistence Port — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the Python on-disk index-persistence subsystem to the TypeScript kernel so that constructing a `Corpus` over an unchanged corpus loads a persisted snapshot and reconciles only what changed on disk, instead of re-parsing and re-indexing every `*.md` file.

**Architecture:** Mirror the *implemented* Python (`python/src/nodes/kernel/snapshot.py`, `index.py`, `search.py`, `similarity.py`, `corpus.py`) — not just the design spec, which the Python code hardened beyond (manifest-path↔structural-id cross-check, search/vector `idByUid` must equal structural-derived ids, JSON-constant rejection, broken-symlink handling). A new `ts/src/snapshot.ts` owns all on-disk concerns (file location, atomic write, version/lang gate, integrity validation, the manifest type, the byte-level file walk, and the reconcile inputs). The three index classes stay pure data and file-I/O-free, gaining `toDict()` plus validating `fromDict()` deserializers. Each `fromDict()` validates its own snapshot shape and local invariants; `loadSnapshot()` validates top-level and cross-index agreement. `Corpus` keeps an in-memory manifest synced across every write path and exposes `flushIndex()`. `Store.allNodes()` uses the same `iterCorpusFiles()` walker as `Corpus`, so `.nodes-index` is excluded consistently.

**Tech Stack:** TypeScript (ESM, `.js` import extensions), Node ≥20, vitest, biome (format + lint, line width 120), `tsc --noEmit` typecheck. No new runtime dependencies — `snapshot.ts` uses only Node built-ins (`node:crypto` `createHash`, `node:fs`, `node:path`) plus the existing kernel modules; `zod` (already a dependency) validates deserialized relations.

## Current State Note

This plan has since been implemented and remains useful as the historical TypeScript index-persistence port. Current `ts/src/snapshot.ts` owns the per-language snapshot cache, `Corpus.flushIndex()` is the explicit writer, and `Store.allNodes()` shares the same `iterCorpusFiles()` walker as reconcile/full rebuild.

There are three current-code details to keep in mind when reading the task snippets below:

- The plan intentionally follows the hardened Python implementation, not only the design spec. Current `fromDict()` methods validate per-index section shape and local invariants; `loadSnapshot()` validates top-level and cross-index agreement.
- Mutations do not auto-flush. If a process mutates files and exits without `flushIndex()`, the next startup reconciles the stale snapshot against file hashes and pays rebuild/reparse cost only for changed files.
- No-embedder corpus construction ignores any vectors section, while an embedder-configured corpus requires a matching vector namespace or falls back to a full rebuild.

## Global Constraints

- **Parity source is the implemented Python, not the spec.** Where the Python code is stricter than `docs/designs/2026-06-23-nodes-index-persistence-design.md`, follow the code. The two kernels must stay behaviorally equivalent (the `cross_parity.test.ts` discipline).
- **Snapshot is a disposable, private, per-language cache.** Filename `snapshot.ts.json`; `lang` is `"ts"`. Python writes `snapshot.py.json` / `lang "py"`; neither language reads the other's file. `SNAPSHOT_SCHEMA_VERSION = 1`.
- **Files are the single source of truth.** Every `Corpus` construction reconciles the snapshot against current file hashes, so a stale/absent/corrupt snapshot costs only time, never correctness.
- **Manifest is always a byte-level file-walk product** on both reconcile and full rebuild — hash the actual on-disk bytes, never `nodeToMarkdown(node)`, on the load path. The write path (`add`/`delete`/`rename`) may hash `nodeToMarkdown(node)` because those are exactly the bytes just written.
- **Error scoping (the single deliberate exception to "avoid silent fallbacks"):** silent fallback → full rebuild applies *only* to snapshot-cache unusability detected inside `loadSnapshot()` (missing file, invalid JSON, `version`/`lang` mismatch, integrity failure, embedder-configured vector mismatch). Any error from reading/parsing corpus files or from the index collision contract — during *either* `fullRebuild()` or `reconcile()` — propagates unchanged. `loadSnapshot()` never parses corpus files.
- **Construction never writes the snapshot.** (The raw `VectorCache` may still write under `.nodes-index/vectors/` during `VectorIndex.build`, as today — hence "never writes *the snapshot*".) Writing the snapshot happens only in the explicit `flushIndex()`.
- **No-embedder mode ignores the `vectors` section entirely** — not deserialized, not validated. A corrupt `vectors` section never forces a rebuild for a no-embedder corpus.
- **Shared-`Relation` identity invariant (structural):** a relation's source and target `OutRef`s must share ONE `Relation` object, because the graph queries dedup on object reference (the TS analog of Python's `id(relation)`). `fromDict` must replay extraction (`outRefsFrom`), never deserialize the two `OutRef`s independently.
- **TS conventions:** camelCase fields/methods (`toDict`, `fromDict`, `hashBytes`, `iterCorpusFiles`, `loadSnapshot`, `flushIndex`, `idByUid`, `hashByUid`), SCREAMING_CASE module constants, `.js` import extensions, `type`-only imports for types, biome line width 120. Maps serialize via `Object.fromEntries` and deserialize via `new Map(Object.entries(...))`. Deep-copy plain JSON values with `structuredClone`.

**Gate for every task:** from `~/d/nodes/ts`, `rtk npm test` (vitest) green, `rtk npm run typecheck` (`tsc --noEmit`) clean, `rtk npm run check` (biome) clean. All commands run from `~/d/nodes/ts`. This work was implemented on `main`.

---

### Task 1: Snapshot I/O foundations (`snapshot.ts`)

Create the new module with the version/lang constants, the byte-level file walk, the SHA-256 helper, the `CorpusFile` and `ManifestEntry` shapes, the atomic JSON writer (which rejects non-finite numbers), and the JSON reader (which returns `null` for a genuinely-absent file but throws for a directory / broken symlink / invalid JSON). Mirrors `snapshot.py` lines 1–75.

**Files:**
- Create: `ts/src/snapshot.ts`
- Test: `ts/tests/snapshot-io.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `SNAPSHOT_SCHEMA_VERSION: 1`, `SNAPSHOT_LANG: "ts"` (constants).
  - `snapshotPath(root: string): string` → `<root>/.nodes-index/snapshot.ts.json`.
  - `hashBytes(data: Buffer | Uint8Array): string` → 64-char lowercase sha256 hex.
  - `interface CorpusFile { readonly path: string; readonly data: Buffer; readonly sha256: string }`.
  - `iterCorpusFiles(root: string): CorpusFile[]` — sorted by root-relative POSIX path; reads each file's bytes once and hashes them; skips the `.nodes-index` tree, symlinks, and non-files; `.md` directories are ignored (only regular files).
  - `interface ManifestEntry { readonly path: string; readonly sha256: string; readonly uid: string }`.
  - `writeJsonAtomic(path: string, obj: unknown): void` — writes `<path>.tmp` then `renameSync`; throws `RangeError` on any non-finite number without leaving a snapshot or tmp file.
  - `readJson(path: string): unknown` — returns `null` when the path is genuinely absent; throws for a directory (`EISDIR`), a broken symlink, or invalid/non-finite-constant JSON.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/snapshot-io.test.ts`:

```ts
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, symlinkSync, writeFileSync } from "node:fs";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  type CorpusFile,
  type ManifestEntry,
  SNAPSHOT_LANG,
  SNAPSHOT_SCHEMA_VERSION,
  hashBytes,
  iterCorpusFiles,
  readJson,
  snapshotPath,
  writeJsonAtomic,
} from "../src/snapshot.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-snap-io-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("snapshot I/O foundations", () => {
  it("exposes the schema version and language", () => {
    expect(SNAPSHOT_SCHEMA_VERSION).toBe(1);
    expect(SNAPSHOT_LANG).toBe("ts");
  });

  it("snapshotPath points at the per-language cache file", () => {
    expect(snapshotPath(root)).toBe(join(root, ".nodes-index", "snapshot.ts.json"));
  });

  it("hashBytes is sha256 hex", () => {
    expect(hashBytes(Buffer.from("hello"))).toBe(createHash("sha256").update("hello").digest("hex"));
    expect(hashBytes(Buffer.from("")).length).toBe(64);
  });

  it("iterCorpusFiles is sorted, root-relative POSIX, with byte hashes", () => {
    mkdirSync(join(root, "topic"));
    mkdirSync(join(root, "gene"));
    writeFileSync(join(root, "topic", "b.md"), "BBB");
    writeFileSync(join(root, "gene", "a.md"), "AAA");
    writeFileSync(join(root, "ignore.txt"), "nope");
    const files = iterCorpusFiles(root);
    expect(files.map((f) => f.path)).toEqual(["gene/a.md", "topic/b.md"]);
    expect(files[0].data.equals(Buffer.from("AAA"))).toBe(true);
    expect(files[0].sha256).toBe(hashBytes(Buffer.from("AAA")));
  });

  it("iterCorpusFiles ignores .md directories", () => {
    mkdirSync(join(root, "notes.md"));
    writeFileSync(join(root, "real.md"), "real");
    const files = iterCorpusFiles(root);
    expect(files.map((f) => f.path)).toEqual(["real.md"]);
  });

  it("iterCorpusFiles ignores the private .nodes-index tree", () => {
    mkdirSync(join(root, ".nodes-index"));
    writeFileSync(join(root, ".nodes-index", "cache.md"), "not a node");
    writeFileSync(join(root, "real.md"), "real");
    expect(iterCorpusFiles(root).map((f) => f.path)).toEqual(["real.md"]);
  });

  it("iterCorpusFiles ignores .md symlinks", () => {
    writeFileSync(join(root, "target.txt"), "target");
    try {
      symlinkSync(join(root, "target.txt"), join(root, "linked.md"));
    } catch {
      return; // symlink unsupported on this platform
    }
    expect(iterCorpusFiles(root)).toEqual([]);
  });

  it("writeJsonAtomic round-trips and leaves no tmp file", () => {
    const p = snapshotPath(root);
    writeJsonAtomic(p, { version: 1, x: [1, 2] });
    expect(readJson(p)).toEqual({ version: 1, x: [1, 2] });
    expect(existsSync(`${p}.tmp`)).toBe(false);
  });

  it("writeJsonAtomic rejects non-finite numbers without writing a snapshot", () => {
    const p = snapshotPath(root);
    expect(() => writeJsonAtomic(p, { x: Number.NaN })).toThrow();
    expect(existsSync(p)).toBe(false);
    expect(existsSync(`${p}.tmp`)).toBe(false);
  });

  it("readJson returns null for a missing file", () => {
    expect(readJson(snapshotPath(root))).toBeNull();
  });

  it("readJson throws for a directory", () => {
    const p = snapshotPath(root);
    mkdirSync(p, { recursive: true });
    expect(() => readJson(p)).toThrow();
  });

  it("readJson throws for a broken symlink", () => {
    const p = snapshotPath(root);
    mkdirSync(join(root, ".nodes-index"), { recursive: true });
    try {
      symlinkSync(join(root, ".nodes-index", "missing-target.json"), p);
    } catch {
      return; // symlink unsupported
    }
    expect(() => readJson(p)).toThrow();
  });

  it("readJson throws on invalid JSON", () => {
    const p = snapshotPath(root);
    mkdirSync(join(root, ".nodes-index"), { recursive: true });
    writeFileSync(p, "{");
    expect(() => readJson(p)).toThrow();
  });

  it.each(["NaN", "Infinity", "-Infinity"])("readJson rejects the non-finite JSON constant %s", (constant) => {
    const p = snapshotPath(root);
    mkdirSync(join(root, ".nodes-index"), { recursive: true });
    writeFileSync(p, `{"x": ${constant}}`);
    expect(() => readJson(p)).toThrow();
  });

  it("CorpusFile and ManifestEntry are plain structural shapes", () => {
    const f: CorpusFile = { path: "a.md", data: Buffer.from("A"), sha256: hashBytes(Buffer.from("A")) };
    const m: ManifestEntry = { path: "a.md", sha256: "0".repeat(64), uid: "u1" };
    expect([f.path, f.sha256, m.uid]).toEqual(["a.md", hashBytes(Buffer.from("A")), "u1"]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npm test -- snapshot-io`
Expected: FAIL — `../src/snapshot.js` cannot be resolved (module does not exist yet).

- [ ] **Step 3: Write the implementation**

Create `ts/src/snapshot.ts`:

```ts
import { createHash } from "node:crypto";
import {
  type Dirent,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative } from "node:path";

export const SNAPSHOT_SCHEMA_VERSION = 1;
export const SNAPSHOT_LANG = "ts";

export function snapshotPath(root: string): string {
  return join(root, ".nodes-index", "snapshot.ts.json");
}

export function hashBytes(data: Buffer | Uint8Array): string {
  return createHash("sha256").update(data).digest("hex");
}

export interface CorpusFile {
  readonly path: string; // root-relative POSIX
  readonly data: Buffer;
  readonly sha256: string;
}

/** Root-relative POSIX path (forward slashes on every platform), the cross-language form. */
function relPosix(root: string, full: string): string {
  return relative(root, full).split(/[\\/]/).join("/");
}

/** Byte-level walk: read each .md file's bytes once and hash them. Skips the private
 * `.nodes-index` tree, symlinks, and non-files. Sorted by root-relative POSIX path so the
 * order matches Python's `sorted(root.rglob("*.md"))`. */
export function iterCorpusFiles(root: string): CorpusFile[] {
  const files: CorpusFile[] = [];
  const walk = (dir: string): void => {
    if (!existsSync(dir)) return;
    let entries: Dirent[];
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = join(dir, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) {
        if (relPosix(root, full) === ".nodes-index") continue;
        walk(full);
      } else if (entry.isFile() && entry.name.endsWith(".md")) {
        const data = readFileSync(full);
        files.push({ path: relPosix(root, full), data, sha256: hashBytes(data) });
      }
    }
  };
  walk(root);
  files.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  return files;
}

export interface ManifestEntry {
  readonly path: string;
  readonly sha256: string;
  readonly uid: string;
}

/** Write JSON atomically (tmp + rename). Rejects any non-finite number — JS `JSON.stringify`
 * silently emits `null` for NaN/Infinity, so a replacer enforces the rejection (parity with
 * Python's `json.dumps(..., allow_nan=False)`). Throws before any write, so no partial file. */
export function writeJsonAtomic(path: string, obj: unknown): void {
  const payload = JSON.stringify(obj, (_key, value) => {
    if (typeof value === "number" && !Number.isFinite(value)) {
      throw new RangeError("cannot serialize non-finite number to JSON");
    }
    return value;
  });
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, payload, "utf-8");
  renameSync(tmp, path);
}

/** Read + parse JSON. Returns `null` only for a genuinely-absent path. A directory, a broken
 * symlink, or invalid JSON throws (JS `JSON.parse` already rejects the `NaN`/`Infinity`
 * constants, so Python's explicit `parse_constant` guard is free here). */
export function readJson(path: string): unknown {
  let raw: string;
  try {
    raw = readFileSync(path, "utf-8");
  } catch (e) {
    const err = e as NodeJS.ErrnoException;
    if (err.code === "ENOENT") {
      try {
        lstatSync(path); // a broken symlink reads ENOENT but lstats fine
      } catch {
        return null; // genuinely absent
      }
      throw err; // path exists as a (broken) symlink
    }
    throw err; // EISDIR and anything else
  }
  return JSON.parse(raw);
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npm test -- snapshot-io`
Expected: PASS. Then `rtk npm test` (full), `rtk npm run typecheck`, `rtk npm run check` all clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/src/snapshot.ts ts/tests/snapshot-io.test.ts
rtk git commit -m "feat(ts-persistence): snapshot I/O foundations — file walk, byte hashing, atomic JSON"
```

---

### Task 2: `SearchIndex.toDict` / `fromDict`

Add pure serialization to `SearchIndex`. `toDict` emits `postings`/`lengths`/`idByUid` as plain objects (with `[number, number]` arrays preserved). `fromDict` is a validating deserializer: every `lengths` key equals every `idByUid` key; every posting uid is present in `lengths`; every tf/length pair is a non-negative int pair; posting buckets are non-empty; tf pairs are not `[0, 0]`; and each field tf is ≤ that uid's stored field length. It recomputes `totalTitle`/`totalBody` by summing `lengths` — the single source of truth, no stored-total drift.

**Files:**
- Modify: `ts/src/search.ts`
- Test: `ts/tests/search-snapshot.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure methods on the existing `SearchIndex`).
- Produces:
  - `SearchIndex.toDict(): { postings: Record<string, Record<string, [number, number]>>; lengths: Record<string, [number, number]>; idByUid: Record<string, string> }`.
  - `static SearchIndex.fromDict(d: unknown): SearchIndex` — throws `Error` on any structural/consistency violation.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/search-snapshot.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { SearchIndex } from "../src/search.js";

function seed(): SearchIndex {
  const idx = new SearchIndex();
  idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "alpha gamma", body: "gamma delta" }));
  idx.upsert(makeNode({ id: "topic:b", kind: "topic", title: "beta", body: "gamma epsilon" }));
  return idx;
}

describe("SearchIndex snapshot", () => {
  it("round-trips and preserves query results", () => {
    const idx = seed();
    const restored = SearchIndex.fromDict(idx.toDict());
    expect(restored.search("gamma").map((h) => [h.id, h.uid, h.score])).toEqual(
      idx.search("gamma").map((h) => [h.id, h.uid, h.score]),
    );
    expect(restored.search("delta").map((h) => h.id)).toEqual(idx.search("delta").map((h) => h.id));
  });

  it("recomputes the corpus totals from lengths (no stored drift)", () => {
    const idx = seed();
    const restored = SearchIndex.fromDict(idx.toDict());
    expect(restored.totalTitle).toBe(idx.totalTitle);
    expect(restored.totalBody).toBe(idx.totalBody);
    expect(restored.n).toBe(idx.n);
  });

  it("empty index round-trips", () => {
    const restored = SearchIndex.fromDict(new SearchIndex().toDict());
    expect(restored.n).toBe(0);
    expect(restored.search("anything")).toEqual([]);
  });

  it("rejects lengths/idByUid uid-set divergence", () => {
    const d = seed().toDict();
    delete d.idByUid[Object.keys(d.idByUid)[0]];
    expect(() => SearchIndex.fromDict(d)).toThrow();
  });

  it("rejects a posting uid absent from lengths", () => {
    const d = seed().toDict();
    const term = Object.keys(d.postings)[0];
    d.postings[term].ghost = [1, 0];
    expect(() => SearchIndex.fromDict(d)).toThrow();
  });

  it("rejects an empty posting bucket", () => {
    const d = seed().toDict();
    d.postings.ghost = {};
    expect(() => SearchIndex.fromDict(d)).toThrow();
  });

  it("rejects a zero posting tf pair", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.lengths)[0];
    d.postings.ghost = { [uid]: [0, 0] };
    expect(() => SearchIndex.fromDict(d)).toThrow();
  });

  it("rejects a posting tf greater than the field length", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.lengths)[0];
    const [titleLen] = d.lengths[uid];
    d.postings.ghost = { [uid]: [titleLen + 1, 0] };
    expect(() => SearchIndex.fromDict(d)).toThrow();
  });

  it("rejects a non-integer / negative length pair", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.lengths)[0];
    d.lengths[uid] = [-1, 0];
    expect(() => SearchIndex.fromDict(d)).toThrow();
    const d2 = seed().toDict();
    const uid2 = Object.keys(d2.lengths)[0];
    (d2.lengths[uid2] as unknown[]) = [1.5, 0];
    expect(() => SearchIndex.fromDict(d2)).toThrow();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npm test -- search-snapshot`
Expected: FAIL — `SearchIndex.toDict`/`fromDict` are not defined.

- [ ] **Step 3: Write the implementation**

In `ts/src/search.ts`, add a `SnapshotDict` shape and the two methods to the `SearchIndex` class (place `toDict`/`fromDict` just after `remove`). First, add this exported interface above the class:

```ts
export interface SearchSnapshot {
  postings: Record<string, Record<string, [number, number]>>;
  lengths: Record<string, [number, number]>;
  idByUid: Record<string, string>;
}
```

Then add the methods inside the class:

```ts
  toDict(): SearchSnapshot {
    const postings: Record<string, Record<string, [number, number]>> = {};
    for (const [term, docs] of this.postings) {
      const bucket: Record<string, [number, number]> = {};
      for (const [uid, tf] of docs) bucket[uid] = [tf[0], tf[1]];
      postings[term] = bucket;
    }
    return {
      postings,
      lengths: Object.fromEntries([...this.lengths].map(([uid, l]) => [uid, [l[0], l[1]]])),
      idByUid: Object.fromEntries(this.idByUid),
    };
  }

  static fromDict(d: unknown): SearchIndex {
    if (typeof d !== "object" || d === null) throw new Error("search snapshot: document must be an object");
    const raw = d as Record<string, unknown>;
    if (typeof raw.lengths !== "object" || raw.lengths === null) {
      throw new Error("search snapshot: lengths must be an object");
    }
    if (typeof raw.idByUid !== "object" || raw.idByUid === null) {
      throw new Error("search snapshot: idByUid must be an object");
    }
    if (typeof raw.postings !== "object" || raw.postings === null) {
      throw new Error("search snapshot: postings must be an object");
    }
    const lengths = new Map<string, [number, number]>();
    for (const [uid, v] of Object.entries(raw.lengths as Record<string, unknown>)) {
      lengths.set(uid, nonNegativeIntPair(v, `search snapshot: length for uid ${JSON.stringify(uid)}`));
    }
    const idByUid = new Map<string, string>();
    for (const [uid, id] of Object.entries(raw.idByUid as Record<string, unknown>)) {
      if (typeof id !== "string") throw new Error("search snapshot: idByUid must map uids to string ids");
      idByUid.set(uid, id);
    }
    if (lengths.size !== idByUid.size || [...lengths.keys()].some((uid) => !idByUid.has(uid))) {
      throw new Error("search snapshot: lengths/idByUid uid sets differ");
    }
    const postings = new Map<string, Map<string, [number, number]>>();
    for (const [term, docs] of Object.entries(raw.postings as Record<string, unknown>)) {
      if (typeof docs !== "object" || docs === null) throw new Error("search snapshot: postings bucket must be an object");
      if (Object.keys(docs).length === 0)
        throw new Error(`search snapshot: postings bucket for term ${JSON.stringify(term)} must not be empty`);
      const bucket = new Map<string, [number, number]>();
      for (const [uid, tf] of Object.entries(docs as Record<string, unknown>)) {
        if (!lengths.has(uid)) {
          throw new Error(`search snapshot: posting uid ${JSON.stringify(uid)} absent from lengths`);
        }
        const tfPair = nonNegativeIntPair(
          tf,
          `search snapshot: posting tf for term ${JSON.stringify(term)} uid ${JSON.stringify(uid)}`,
        );
        if (tfPair[0] === 0 && tfPair[1] === 0) {
          throw new Error(
            `search snapshot: posting tf for term ${JSON.stringify(term)} uid ${JSON.stringify(uid)} must not be all zero`,
          );
        }
        const [titleLen, bodyLen] = lengths.get(uid) as [number, number];
        if (tfPair[0] > titleLen || tfPair[1] > bodyLen) {
          throw new Error(
            `search snapshot: posting tf for term ${JSON.stringify(term)} uid ${JSON.stringify(uid)} exceeds field length`,
          );
        }
        bucket.set(uid, tfPair);
      }
      postings.set(term, bucket);
    }
    const idx = new SearchIndex();
    idx.postings = postings;
    idx.lengths = lengths;
    idx.idByUid = idByUid;
    idx.totalTitle = [...lengths.values()].reduce((s, l) => s + l[0], 0);
    idx.totalBody = [...lengths.values()].reduce((s, l) => s + l[1], 0);
    return idx;
  }
```

Add this module-level helper (near the bottom of the file, before the class or after it — keep it module-private, not exported):

```ts
function nonNegativeIntPair(value: unknown, label: string): [number, number] {
  if (!Array.isArray(value) || value.length !== 2) throw new Error(`${label} must be a 2-item array`);
  const [first, second] = value;
  if (
    typeof first !== "number" ||
    typeof second !== "number" ||
    !Number.isInteger(first) ||
    !Number.isInteger(second) ||
    first < 0 ||
    second < 0
  ) {
    throw new Error(`${label} must contain non-negative integers`);
  }
  return [first, second];
}
```

Export the new interface from `ts/src/index.ts` by adding `type SearchSnapshot` to the existing `./search.js` export block:

```ts
export { SearchIndex, type SearchHit, type SearchSnapshot, tokenize } from "./search.js";
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npm test -- search-snapshot`
Expected: PASS. Then `rtk npm test` (full), `rtk npm run typecheck`, `rtk npm run check` clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/src/search.ts ts/src/index.ts ts/tests/search-snapshot.test.ts
rtk git commit -m "feat(ts-persistence): SearchIndex toDict/fromDict with self-consistency checks"
```

---

### Task 3: `VectorIndex.toDict` / `fromDict`

Add pure serialization to `VectorIndex`. `toDict` emits `namespace`, `dim` (`null` when there are no stored vectors, mirroring the empty-corpus state), `vectors` (uid → normalized vector array), `idByUid`, `hashByUid`. `fromDict` validates: the three uid maps are equal; every `hashByUid` value is a valid 64-hex text hash; `idByUid` maps strings to strings; when vectors are present, `namespace` is a valid string and `dim` a positive int and every vector has length `dim` and is L2-normalized; when empty, `dim` is `null` and `namespace` is `null` or a valid string. Loads vectors verbatim (no re-normalization beyond the unit-length check). Mirrors `similarity.py` `to_dict`/`from_dict` (lines 155–230).

**Files:**
- Modify: `ts/src/similarity.ts`
- Test: `ts/tests/vector-snapshot.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `VectorIndex.toDict(): { namespace: string | null; dim: number | null; vectors: Record<string, number[]>; idByUid: Record<string, string>; hashByUid: Record<string, string> }`.
  - `static VectorIndex.fromDict(d: unknown): VectorIndex` — throws `Error` on any violation.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/vector-snapshot.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach } from "vitest";
import { makeNode } from "../src/node.js";
import { type Embedder, type Vector, VectorCache, VectorIndex } from "../src/similarity.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-vec-snap-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

class TableEmbedder implements Embedder {
  readonly cacheNamespace = "vec-v1";
  embed(texts: string[]): Vector[] {
    return texts.map((t) => (t.includes("cat") ? [3, 4] : [0, 5]));
  }
}

function seed(): VectorIndex {
  const idx = VectorIndex.build(
    [makeNode({ id: "topic:cat", kind: "topic", title: "cat" }), makeNode({ id: "topic:dog", kind: "topic", title: "dog" })],
    new TableEmbedder(),
    new VectorCache(root),
  );
  return idx;
}

describe("VectorIndex snapshot", () => {
  it("round-trips vectors, ids, hashes, dim and namespace", () => {
    const idx = seed();
    const restored = VectorIndex.fromDict(idx.toDict());
    expect(restored.namespace).toBe("vec-v1");
    expect(restored.dim).toBe(2);
    expect(restored.queryVector([3, 4]).map((h) => h.id)).toEqual(idx.queryVector([3, 4]).map((h) => h.id));
    expect([...restored.hashByUid]).toEqual([...idx.hashByUid]);
  });

  it("empty embedder index round-trips with dim null", () => {
    const idx = new VectorIndex();
    idx.namespace = "vec-v1";
    const d = idx.toDict();
    expect(d.dim).toBeNull();
    const restored = VectorIndex.fromDict(d);
    expect(restored.dim).toBeNull();
    expect(restored.namespace).toBe("vec-v1");
    expect(restored.vectors.size).toBe(0);
  });

  it("rejects mismatched uid maps", () => {
    const d = seed().toDict();
    delete d.hashByUid[Object.keys(d.hashByUid)[0]];
    expect(() => VectorIndex.fromDict(d)).toThrow();
  });

  it("rejects a vector whose length != dim", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.vectors)[0];
    d.vectors[uid] = [1];
    expect(() => VectorIndex.fromDict(d)).toThrow();
  });

  it("rejects a non-normalized stored vector", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.vectors)[0];
    d.vectors[uid] = [3, 4]; // norm 5, not 1
    expect(() => VectorIndex.fromDict(d)).toThrow();
  });

  it("rejects non-null dim when there are no vectors", () => {
    const d = new VectorIndex().toDict();
    (d as { dim: number | null }).dim = 4;
    expect(() => VectorIndex.fromDict(d)).toThrow();
  });

  it("rejects an invalid hashByUid value", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.hashByUid)[0];
    d.hashByUid[uid] = "not-a-hash";
    expect(() => VectorIndex.fromDict(d)).toThrow();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npm test -- vector-snapshot`
Expected: FAIL — `VectorIndex.toDict`/`fromDict` are not defined.

- [ ] **Step 3: Write the implementation**

In `ts/src/similarity.ts`, add an exported interface above the `VectorIndex` class:

```ts
export interface VectorSnapshot {
  namespace: string | null;
  dim: number | null;
  vectors: Record<string, number[]>;
  idByUid: Record<string, string>;
  hashByUid: Record<string, string>;
}
```

Add these two methods to `VectorIndex` (place them right after the field declarations, before `static build`):

```ts
  toDict(): VectorSnapshot {
    return {
      namespace: this.namespace,
      dim: this.vectors.size > 0 ? this.dim : null,
      vectors: Object.fromEntries([...this.vectors].map(([uid, vec]) => [uid, [...vec]])),
      idByUid: Object.fromEntries(this.idByUid),
      hashByUid: Object.fromEntries(this.hashByUid),
    };
  }

  static fromDict(d: unknown): VectorIndex {
    if (typeof d !== "object" || d === null) throw new Error("vector snapshot: document must be an object");
    const raw = d as Record<string, unknown>;
    for (const key of ["namespace", "dim", "vectors", "idByUid", "hashByUid"]) {
      if (!(key in raw)) throw new Error(`vector snapshot: missing ${key}`);
    }
    const { namespace, dim } = raw;
    if (typeof raw.vectors !== "object" || raw.vectors === null) throw new Error("vector snapshot: vectors must be an object");
    if (typeof raw.idByUid !== "object" || raw.idByUid === null) throw new Error("vector snapshot: idByUid must be an object");
    if (typeof raw.hashByUid !== "object" || raw.hashByUid === null) throw new Error("vector snapshot: hashByUid must be an object");
    const vectorsRaw = raw.vectors as Record<string, unknown>;
    const idByUid = new Map<string, string>();
    for (const [uid, id] of Object.entries(raw.idByUid as Record<string, unknown>)) {
      if (typeof id !== "string") throw new Error("vector snapshot: idByUid must map string uids to string ids");
      idByUid.set(uid, id);
    }
    const hashByUid = new Map<string, string>();
    for (const [uid, h] of Object.entries(raw.hashByUid as Record<string, unknown>)) {
      if (typeof h !== "string") throw new Error("vector snapshot: hashByUid values must be strings");
      validateTextHash(h);
      hashByUid.set(uid, h);
    }
    const vectorUids = Object.keys(vectorsRaw);
    const sameSet =
      vectorUids.length === idByUid.size &&
      vectorUids.length === hashByUid.size &&
      vectorUids.every((uid) => idByUid.has(uid) && hashByUid.has(uid));
    if (!sameSet) throw new Error("vector snapshot: vectors/idByUid/hashByUid uid sets differ");

    const hasVectors = vectorUids.length > 0;
    if (hasVectors) {
      if (typeof namespace !== "string") throw new Error("vector snapshot: namespace must be a string when vectors are present");
      validateNamespace(namespace);
      if (typeof dim !== "number" || !Number.isInteger(dim) || dim <= 0) {
        throw new Error("vector snapshot: dim must be a positive integer when vectors are present");
      }
    } else if (dim !== null) {
      throw new Error("vector snapshot: dim must be null when there are no vectors");
    } else if (namespace !== null) {
      if (typeof namespace !== "string") throw new Error("vector snapshot: namespace must be a string when non-null");
      validateNamespace(namespace);
    }

    const vectors = new Map<string, Vector>();
    for (const [uid, rawVec] of Object.entries(vectorsRaw)) {
      if (!Array.isArray(rawVec)) throw new Error("vector snapshot: vector must be an array");
      for (const x of rawVec) {
        if (typeof x !== "number" || !Number.isFinite(x)) throw new Error("vector snapshot: vector contains a non-finite value");
      }
      const vec = rawVec as number[];
      if (vec.length !== dim) throw new Error("vector snapshot: vector length != dim");
      const norm = Math.sqrt(vec.reduce((s, x) => s + x * x, 0));
      if (Math.abs(norm - 1) > 1e-9) throw new Error("vector snapshot: stored vector must be L2-normalized");
      vectors.set(uid, [...vec]);
    }

    const idx = new VectorIndex();
    idx.namespace = (namespace as string | null) ?? null;
    idx.vectors = vectors;
    idx.idByUid = idByUid;
    idx.hashByUid = hashByUid;
    idx.dim = (dim as number | null) ?? null;
    return idx;
  }
```

Export the new interface from `ts/src/index.ts` by adding `type VectorSnapshot` to the existing `./similarity.js` export block:

```ts
export {
  type Embedder,
  type SimilarHit,
  type Vector,
  type VectorSnapshot,
  VectorCache,
  VectorIndex,
  embedText,
  textHash,
  validateNamespace,
  validateTextHash,
} from "./similarity.js";
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npm test -- vector-snapshot`
Expected: PASS. Then `rtk npm test` (full), `rtk npm run typecheck`, `rtk npm run check` clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/src/similarity.ts ts/src/index.ts ts/tests/vector-snapshot.test.ts
rtk git commit -m "feat(ts-persistence): VectorIndex toDict/fromDict (dim null|int, uid-map + normalization checks)"
```

---

### Task 4: structural `Index.toDict` / `fromDict`

Add pure serialization to `Index` using the post-structural-shapes snapshot shape. The snapshot stores relations once per entry and stores built-in structure refs in a generic `structuralRefs` array, not as a copied `membership` facet. This preserves the structural-shapes redesign: `members`, graph `edges`, list `order`, and dict `keys` refs are tracked for rename + snapshot integrity, but they are not relation-graph edges and they do not require snapshot-schema changes for every shape facet.

`fromDict` is a validating deserializer. It validates every entry, parses each relation through `RelationSchema`, validates structural-ref roles, rebuilds `idToUid` / `deprecatedToUid` / `inRefs`, enforces identity-claim uniqueness across entries, and replays relation extraction so each relation's source and target `OutRef`s share one `Relation` object.

**Files:**
- Modify: `ts/src/structural-index.ts`
- Test: `ts/tests/index-snapshot.test.ts`

**Interfaces:**
- Consumes: `Relation`, `RelationSchema` from `./relations.js`; `MEMBERSHIP`, `EDGES`, `ORDER`, `KEYS` from `./shapes.js`; `NodeId` / `IdError`.
- Produces:
  - Structural roles: `"membership_member"`, `"edges_source"`, `"edges_target"`, `"order_member"`, `"keys_value"` in addition to relation roles.
  - `Index.toDict(): { entries: Array<{ uid: string; id: string; kind: string; deprecatedIds: string[]; relations: Array<Record<string, unknown>>; structuralRefs: Array<{ ref: string; role: Role }> }> }`.
  - `static Index.fromDict(d: unknown): Index` — throws `Error` on any structural/integrity violation.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/index-snapshot.test.ts`. It reuses the `normalize` equivalence helper pattern from `index-rebuild-equivalence.test.ts` and covers every structural-ref role:

```ts
import { describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { Index, type OutRef } from "../src/structural-index.js";

function canonicalAttrs(attrs: Record<string, unknown>): string {
  const sorted: Record<string, unknown> = {};
  for (const k of Object.keys(attrs).sort()) sorted[k] = attrs[k];
  return JSON.stringify(sorted);
}
function relationSignature(o: OutRef): string | null {
  const rel = o.relation;
  if (rel === undefined) return null;
  return JSON.stringify([rel.source, rel.predicate, rel.target, rel.directed, rel.weight, canonicalAttrs(rel.attrs)]);
}
function outRefKey(o: OutRef): string {
  return JSON.stringify([o.ref, o.role, relationSignature(o)]);
}
function normalize(index: Index): unknown {
  const byUid: Record<string, unknown> = {};
  for (const [uid, e] of index.byUid) {
    byUid[uid] = [e.id, e.kind, [...e.deprecatedIds].sort(), e.outRefs.map(outRefKey).sort()];
  }
  const inRefs: Record<string, string[]> = {};
  for (const [ref, rows] of index.inRefs) {
    inRefs[ref] = rows
      .map((r) => JSON.stringify([r.sourceUid, r.outRef.ref, r.outRef.role, relationSignature(r.outRef)]))
      .sort();
  }
  return {
    byUid,
    idToUid: Object.fromEntries(index.idToUid),
    deprecatedToUid: Object.fromEntries(index.deprecatedToUid),
    inRefs,
  };
}

function seed(): Index {
  return Index.build([
    makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:b")] }),
    makeNode({ id: "topic:b", kind: "topic", title: "B", deprecatedIds: ["topic:bb"] }),
    makeNode({
      id: "graph:g",
      kind: "graph",
      title: "G",
      facets: {
        membership: { members: ["topic:a", "topic:missing"] },
        edges: { edges: [{ source: "topic:a", predicate: "to", target: "topic:b" }] },
      },
    }),
    makeNode({
      id: "list:l",
      kind: "list",
      title: "L",
      facets: { membership: { members: ["topic:a"] }, order: { order: ["topic:a"] } },
    }),
    makeNode({
      id: "dict:d",
      kind: "dict",
      title: "D",
      facets: { membership: { members: ["topic:a"] }, keys: { keys: { label: "topic:a" } } },
    }),
  ]);
}

describe("structural Index snapshot", () => {
  it("round-trips to a structurally-equivalent index", () => {
    const idx = seed();
    expect(normalize(Index.fromDict(idx.toDict()))).toEqual(normalize(idx));
  });

  it("preserves shared-Relation identity so inbound/dangling dedup correctly", () => {
    const idx = seed();
    const restored = Index.fromDict(idx.toDict());
    const aUid = restored.idToUid.get("topic:a") as string;
    expect(restored.outboundEdges(aUid).length).toBe(1);
    const bUid = restored.idToUid.get("topic:b") as string;
    expect(restored.inboundEdges(bUid).length).toBe(idx.inboundEdges(idx.idToUid.get("topic:b") as string).length);
  });

  it("round-trips an empty index", () => {
    expect(normalize(Index.fromDict(new Index().toDict()))).toEqual(normalize(new Index()));
  });

  it("rejects a duplicate uid across entries", () => {
    const d = seed().toDict();
    d.entries.push({ ...d.entries[0] });
    expect(() => Index.fromDict(d)).toThrow();
  });

  it("rejects an entry whose id kind disagrees with kind", () => {
    const d = seed().toDict();
    d.entries[0].kind = "gene";
    expect(() => Index.fromDict(d)).toThrow();
  });

  it("rejects a deprecated id equal to the live id", () => {
    const d = seed().toDict();
    d.entries[0].deprecatedIds = [d.entries[0].id];
    expect(() => Index.fromDict(d)).toThrow();
  });

  it("rejects an identity claim already in use by another entry", () => {
    const d = seed().toDict();
    d.entries[1].deprecatedIds = ["topic:a"];
    expect(() => Index.fromDict(d)).toThrow();
  });

  it("persists structural refs under structuralRefs (not membership) for every role", () => {
    const d = seed().toDict();
    for (const entry of d.entries) {
      expect("membership" in entry).toBe(false);
      expect(Array.isArray(entry.structuralRefs)).toBe(true);
    }
    const allRoles = new Set(d.entries.flatMap((e) => e.structuralRefs.map((r) => r.role)));
    expect(allRoles).toContain("membership_member");
    expect(allRoles).toContain("edges_source");
    expect(allRoles).toContain("edges_target");
    expect(allRoles).toContain("order_member");
    expect(allRoles).toContain("keys_value");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npm test -- index-snapshot`
Expected: FAIL — `Index.toDict`/`fromDict` are not defined.

- [ ] **Step 3: Write the implementation**

In `ts/src/structural-index.ts`:

1. Define the structural roles and accepted snapshot roles:

```ts
export type Role =
  | "relation_source"
  | "relation_target"
  | "membership_member"
  | "edges_source"
  | "edges_target"
  | "order_member"
  | "keys_value";

const STRUCTURAL_ENTRY_KEYS = ["uid", "id", "kind", "deprecatedIds", "relations", "structuralRefs"] as const;
const STRUCTURAL_REF_ROLES = new Set<Role>([
  "membership_member",
  "edges_source",
  "edges_target",
  "order_member",
  "keys_value",
]);
```

2. Extract relation refs separately from structure refs. Relation refs keep the shared `Relation` object; structure refs are raw `{ref, role}` rows with no `relation`.

```ts
function relationOutRefs(relations: Relation[]): OutRef[] {
  const refs: OutRef[] = [];
  for (const rel of relations) {
    refs.push({ ref: rel.source, role: "relation_source", relation: rel });
    refs.push({ ref: rel.target, role: "relation_target", relation: rel });
  }
  return refs;
}

function structuralOutRefs(node: Node): OutRef[] {
  const refs: OutRef[] = [];
  const mem = node.facets[MEMBERSHIP];
  if (mem !== null && typeof mem === "object") {
    const members = (mem as Record<string, unknown>).members;
    if (Array.isArray(members)) {
      for (const m of members) if (typeof m === "string") refs.push({ ref: m, role: "membership_member" });
    }
  }
  const eg = node.facets[EDGES];
  if (eg !== null && typeof eg === "object") {
    const edges = (eg as Record<string, unknown>).edges;
    if (Array.isArray(edges)) {
      for (const edge of edges) {
        if (edge !== null && typeof edge === "object") {
          const e = edge as Record<string, unknown>;
          if (typeof e.source === "string") refs.push({ ref: e.source, role: "edges_source" });
          if (typeof e.target === "string") refs.push({ ref: e.target, role: "edges_target" });
        }
      }
    }
  }
  const od = node.facets[ORDER];
  if (od !== null && typeof od === "object") {
    const order = (od as Record<string, unknown>).order;
    if (Array.isArray(order)) {
      for (const m of order) if (typeof m === "string") refs.push({ ref: m, role: "order_member" });
    }
  }
  const ky = node.facets[KEYS];
  if (ky !== null && typeof ky === "object") {
    const keys = (ky as Record<string, unknown>).keys;
    if (keys !== null && typeof keys === "object") {
      for (const v of Object.values(keys as Record<string, unknown>)) {
        if (typeof v === "string") refs.push({ ref: v, role: "keys_value" });
      }
    }
  }
  return refs;
}

function extractOutRefs(node: Node): OutRef[] {
  return [...relationOutRefs(node.relations), ...structuralOutRefs(node)];
}
```

3. Implement `toDict()` so structural refs are serialized as `structuralRefs` and `membership` is never emitted:

```ts
  toDict(): {
    entries: Array<{
      uid: string;
      id: string;
      kind: string;
      deprecatedIds: string[];
      relations: Array<Record<string, unknown>>;
      structuralRefs: Array<{ ref: string; role: Role }>;
    }>;
  } {
    const entries = [];
    for (const entry of this.byUid.values()) {
      const relations: Array<Record<string, unknown>> = [];
      for (const o of entry.outRefs) {
        if (o.role !== "relation_source" || o.relation === undefined) continue;
        const rel = o.relation;
        const row: Record<string, unknown> = {
          source: rel.source,
          predicate: rel.predicate,
          target: rel.target,
          directed: rel.directed,
          attrs: structuredClone(rel.attrs),
        };
        if (rel.weight !== null) row.weight = rel.weight;
        relations.push(row);
      }
      entries.push({
        uid: entry.uid,
        id: entry.id,
        kind: entry.kind,
        deprecatedIds: [...entry.deprecatedIds].sort(),
        relations,
        structuralRefs: entry.outRefs
          .filter((o) => !o.role.startsWith("relation_"))
          .map((o) => ({ ref: o.ref, role: o.role })),
      });
    }
    return { entries };
  }
```

4. Implement `fromDict()` by validating `STRUCTURAL_ENTRY_KEYS`, parsing relations through `RelationSchema`, validating `structuralRefs` with `STRUCTURAL_REF_ROLES`, then rebuilding the maps. Use `relationOutRefs(relations)` plus the validated structural refs to preserve the shared-`Relation` invariant.

5. Add module-private helpers:
   - `validatedDeprecatedIds(raw, entryId)` — array of unique strings, no live-id duplicate.
   - `validateSnapshotWeight(raw, label)` — optional finite number.
   - `validateSnapshotDirected(raw, label)` — optional boolean.
   - `validatedStructuralRefs(raw)` — array of `{ref: string, role: one of STRUCTURAL_REF_ROLES}`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npm test -- index-snapshot`
Expected: PASS. Then `rtk npm test` (full — `index-rebuild-equivalence.test.ts`, `structural-index.test.ts`, `corpus*.test.ts`, `cross_parity.test.ts` must all stay green, confirming the extraction refactor and `structuralRefs` snapshot shape changed no behavior), `rtk npm run typecheck`, `rtk npm run check` clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/src/structural-index.ts ts/tests/index-snapshot.test.ts
rtk git commit -m "feat(ts-persistence): structural Index toDict/fromDict with structural refs"
```

---

### Task 5: `Snapshot` document, `writeSnapshot`, `loadSnapshot`

Add the document shape, the manifest parser, the id→path reconstructor, the atomic snapshot writer, and the validated loader to `snapshot.ts`. `loadSnapshot` reads and validates *only* the cache file (it never parses corpus files), returning `null` for any cache problem (missing/invalid JSON, version/lang mismatch, integrity failure, embedder-configured vector mismatch). It enforces the full cross-section bijection plus the manifest-path↔structural-id and `idByUid`↔structural-id cross-checks the Python code added. Mirrors `snapshot.py` lines 77–203.

**Files:**
- Modify: `ts/src/snapshot.ts`
- Test: `ts/tests/snapshot-load.test.ts`

**Interfaces:**
- Consumes: `Index`/`SearchIndex`/`VectorIndex` `.toDict`/`.fromDict` (Tasks 2–4); `ManifestEntry`, `snapshotPath`, `readJson`, `writeJsonAtomic`, `SNAPSHOT_SCHEMA_VERSION`, `SNAPSHOT_LANG` (Task 1).
- Produces:
  - `interface Snapshot { manifest: ManifestEntry[]; index: Index; searchIndex: SearchIndex; vectorIndex: VectorIndex | null }`.
  - `pathForNodeId(nodeId: string): string` → `${kind}/${slug.replace(/:/g,"__")}.md` (root-relative POSIX).
  - `writeSnapshot(root, manifest: ManifestEntry[], index: Index, searchIndex: SearchIndex, vectorIndex: VectorIndex | undefined): void`.
  - `loadSnapshot(root: string, embedderNamespace: string | null): Snapshot | null`.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/snapshot-load.test.ts`:

```ts
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { SearchIndex } from "../src/search.js";
import { type Embedder, type Vector, VectorCache, VectorIndex } from "../src/similarity.js";
import {
  type ManifestEntry,
  hashBytes,
  loadSnapshot,
  pathForNodeId,
  snapshotPath,
  writeSnapshot,
} from "../src/snapshot.js";
import { Index } from "../src/structural-index.js";
import { nodeToMarkdown } from "../src/frontmatter.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-snap-load-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

class FixedEmbedder implements Embedder {
  readonly cacheNamespace = "load-v1";
  embed(texts: string[]): Vector[] {
    return texts.map(() => [1, 0]);
  }
}

function nodes() {
  return [
    makeNode({ id: "topic:a", kind: "topic", title: "A", body: "alpha", relations: [relatesTo("topic:a", "topic:b")] }),
    makeNode({ id: "topic:b", kind: "topic", title: "B", body: "beta" }),
  ];
}

function manifestFor(ns: ReturnType<typeof nodes>): ManifestEntry[] {
  return ns.map((n) => ({
    path: pathForNodeId(n.id),
    sha256: hashBytes(Buffer.from(nodeToMarkdown(n), "utf-8")),
    uid: n.uid,
  }));
}

describe("snapshot writeSnapshot/loadSnapshot", () => {
  it("pathForNodeId mirrors the on-disk layout", () => {
    expect(pathForNodeId("topic:a")).toBe("topic/a.md");
    expect(pathForNodeId("gene:BRCA1:v2")).toBe("gene/BRCA1__v2.md");
  });

  it("round-trips a no-embedder snapshot", () => {
    const ns = nodes();
    writeSnapshot(root, manifestFor(ns), Index.build(ns), SearchIndex.build(ns), undefined);
    const snap = loadSnapshot(root, null);
    expect(snap).not.toBeNull();
    expect(snap?.vectorIndex).toBeNull();
    expect([...(snap as { index: Index }).index.byUid.keys()].sort()).toEqual(ns.map((n) => n.uid).sort());
  });

  it("round-trips an embedder snapshot when the namespace matches", () => {
    const ns = nodes();
    const vi = VectorIndex.build(ns, new FixedEmbedder(), new VectorCache(root));
    writeSnapshot(root, manifestFor(ns), Index.build(ns), SearchIndex.build(ns), vi);
    expect(loadSnapshot(root, "load-v1")).not.toBeNull();
  });

  it("returns null when no snapshot exists", () => {
    expect(loadSnapshot(root, null)).toBeNull();
  });

  it("returns null on a version mismatch", () => {
    const ns = nodes();
    writeSnapshot(root, manifestFor(ns), Index.build(ns), SearchIndex.build(ns), undefined);
    const doc = JSON.parse(require("node:fs").readFileSync(snapshotPath(root), "utf-8"));
    doc.version = 999;
    writeFileSync(snapshotPath(root), JSON.stringify(doc));
    expect(loadSnapshot(root, null)).toBeNull();
  });

  it("returns null on a lang mismatch", () => {
    const ns = nodes();
    writeSnapshot(root, manifestFor(ns), Index.build(ns), SearchIndex.build(ns), undefined);
    const doc = JSON.parse(require("node:fs").readFileSync(snapshotPath(root), "utf-8"));
    doc.lang = "py";
    writeFileSync(snapshotPath(root), JSON.stringify(doc));
    expect(loadSnapshot(root, null)).toBeNull();
  });

  it("returns null on corrupt JSON", () => {
    const ns = nodes();
    writeSnapshot(root, manifestFor(ns), Index.build(ns), SearchIndex.build(ns), undefined);
    writeFileSync(snapshotPath(root), "{garbage");
    expect(loadSnapshot(root, null)).toBeNull();
  });

  it("returns null when an embedder is configured but the snapshot has no vectors", () => {
    const ns = nodes();
    writeSnapshot(root, manifestFor(ns), Index.build(ns), SearchIndex.build(ns), undefined);
    expect(loadSnapshot(root, "load-v1")).toBeNull();
  });

  it("returns null when the vector namespace differs from the embedder", () => {
    const ns = nodes();
    const vi = VectorIndex.build(ns, new FixedEmbedder(), new VectorCache(root));
    writeSnapshot(root, manifestFor(ns), Index.build(ns), SearchIndex.build(ns), vi);
    expect(loadSnapshot(root, "other-namespace")).toBeNull();
  });

  it("ignores a corrupt vectors section for a no-embedder load", () => {
    const ns = nodes();
    const vi = VectorIndex.build(ns, new FixedEmbedder(), new VectorCache(root));
    writeSnapshot(root, manifestFor(ns), Index.build(ns), SearchIndex.build(ns), vi);
    const doc = JSON.parse(require("node:fs").readFileSync(snapshotPath(root), "utf-8"));
    doc.vectors.vectors = { ghost: [1, 0] }; // garbage, but no embedder => ignored
    writeFileSync(snapshotPath(root), JSON.stringify(doc));
    expect(loadSnapshot(root, null)).not.toBeNull();
  });

  it("returns null when a manifest uid is missing from the structural section", () => {
    const ns = nodes();
    const manifest = manifestFor(ns);
    manifest[0] = { ...manifest[0], uid: "ghostuid" };
    writeSnapshot(root, manifest, Index.build(ns), SearchIndex.build(ns), undefined);
    expect(loadSnapshot(root, null)).toBeNull();
  });

  it("returns null on a duplicate manifest uid", () => {
    const ns = nodes();
    const manifest = manifestFor(ns);
    manifest[1] = { ...manifest[1], uid: manifest[0].uid };
    writeSnapshot(root, manifest, Index.build(ns), SearchIndex.build(ns), undefined);
    expect(loadSnapshot(root, null)).toBeNull();
  });

  it("returns null when a manifest path disagrees with the structural id", () => {
    const ns = nodes();
    const manifest = manifestFor(ns);
    manifest[0] = { ...manifest[0], path: "topic/wrong.md" };
    writeSnapshot(root, manifest, Index.build(ns), SearchIndex.build(ns), undefined);
    expect(loadSnapshot(root, null)).toBeNull();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npm test -- snapshot-load`
Expected: FAIL — `writeSnapshot`/`loadSnapshot`/`pathForNodeId` are not defined.

- [ ] **Step 3: Write the implementation**

In `ts/src/snapshot.ts`, add the imports for the index classes and `NodeId`:

```ts
import { NodeId } from "./ids.js";
import { SearchIndex } from "./search.js";
import { Index } from "./structural-index.js";
import { VectorIndex } from "./similarity.js";
```

Add the SHA-256 manifest regex constant near the top (after the `SNAPSHOT_LANG` line):

```ts
const SHA256_RE = /^[0-9a-f]{64}$/;
const SNAPSHOT_KEYS = ["version", "lang", "manifest", "structural", "search", "vectors"];
const MANIFEST_ROW_KEYS = ["path", "sha256", "uid"];
```

Append the document logic to the end of `snapshot.ts`:

```ts
export interface Snapshot {
  manifest: ManifestEntry[];
  index: Index;
  searchIndex: SearchIndex;
  vectorIndex: VectorIndex | null;
}

export function pathForNodeId(nodeId: string): string {
  const nid = NodeId.parse(nodeId);
  return `${nid.kind}/${nid.slug.replace(/:/g, "__")}.md`;
}

export function writeSnapshot(
  root: string,
  manifest: ManifestEntry[],
  index: Index,
  searchIndex: SearchIndex,
  vectorIndex: VectorIndex | undefined,
): void {
  const doc = {
    version: SNAPSHOT_SCHEMA_VERSION,
    lang: SNAPSHOT_LANG,
    manifest: manifest.map((m) => ({ path: m.path, sha256: m.sha256, uid: m.uid })),
    structural: index.toDict(),
    search: searchIndex.toDict(),
    vectors: vectorIndex !== undefined ? vectorIndex.toDict() : null,
  };
  writeJsonAtomic(snapshotPath(root), doc);
}

function validateManifestPath(path: string): void {
  const parts = path.split("/");
  if (
    !path ||
    path.startsWith("/") ||
    path.includes("\\") ||
    path.endsWith("/") ||
    !path.endsWith(".md") ||
    parts[0] === ".nodes-index" ||
    parts.some((part) => part === "" || part === "." || part === "..")
  ) {
    throw new Error("snapshot manifest row path must be a root-relative POSIX .md path");
  }
}

function parseManifest(raw: unknown): ManifestEntry[] {
  if (!Array.isArray(raw)) throw new Error("snapshot manifest is not an array");
  const entries: ManifestEntry[] = [];
  for (const e of raw) {
    if (typeof e !== "object" || e === null) throw new Error("snapshot manifest row is not an object");
    const row = e as Record<string, unknown>;
    for (const key of MANIFEST_ROW_KEYS) {
      if (!(key in row)) throw new Error(`snapshot manifest row missing ${key}`);
    }
    const { path, sha256, uid } = row;
    if (typeof path !== "string") throw new Error("snapshot manifest row path must be a string");
    validateManifestPath(path);
    if (typeof sha256 !== "string") throw new Error("snapshot manifest row sha256 must be a string");
    if (!SHA256_RE.test(sha256)) throw new Error("snapshot manifest row sha256 must be 64 lowercase hex chars");
    if (typeof uid !== "string") throw new Error("snapshot manifest row uid must be a string");
    entries.push({ path, sha256, uid });
  }
  if (new Set(entries.map((m) => m.uid)).size !== entries.length) throw new Error("snapshot manifest: duplicate uid");
  if (new Set(entries.map((m) => m.path)).size !== entries.length) throw new Error("snapshot manifest: duplicate path");
  return entries;
}

function setsEqual(a: Set<string>, b: Set<string>): boolean {
  return a.size === b.size && [...a].every((x) => b.has(x));
}

function mapsEqual(a: Map<string, string>, b: Map<string, string>): boolean {
  if (a.size !== b.size) return false;
  for (const [k, v] of a) if (b.get(k) !== v) return false;
  return true;
}

/** Reads and validates ONLY the cache file. Returns null for any cache problem (missing file,
 * invalid JSON, version/lang mismatch, integrity failure, embedder-configured vector mismatch).
 * Never parses corpus files, so it can never raise a corpus error — any throw here is a cache
 * problem and resolves to a silent full rebuild upstream. */
export function loadSnapshot(root: string, embedderNamespace: string | null): Snapshot | null {
  try {
    const doc = readJson(snapshotPath(root));
    if (doc === null) return null;
    if (typeof doc !== "object") return null;
    const d = doc as Record<string, unknown>;
    for (const key of SNAPSHOT_KEYS) {
      if (!(key in d)) throw new Error(`snapshot document missing ${key}`);
    }
    if (d.version !== SNAPSHOT_SCHEMA_VERSION || d.lang !== SNAPSHOT_LANG) return null;

    const manifest = parseManifest(d.manifest);
    const manifestUids = new Set(manifest.map((m) => m.uid));

    const index = Index.fromDict(d.structural);
    if (!setsEqual(new Set(index.byUid.keys()), manifestUids)) return null;
    const expectedIds = new Map<string, string>();
    for (const [uid, entry] of index.byUid) expectedIds.set(uid, entry.id);
    for (const m of manifest) {
      if (m.path !== pathForNodeId(expectedIds.get(m.uid) as string)) {
        throw new Error("snapshot manifest path does not match structural id");
      }
    }

    const searchIndex = SearchIndex.fromDict(d.search);
    if (!setsEqual(new Set(searchIndex.lengths.keys()), manifestUids)) return null;
    if (!mapsEqual(searchIndex.idByUid, expectedIds)) return null;

    let vectorIndex: VectorIndex | null = null;
    if (embedderNamespace !== null) {
      const vec = d.vectors;
      if (typeof vec !== "object" || vec === null) return null;
      if ((vec as Record<string, unknown>).namespace !== embedderNamespace) return null;
      vectorIndex = VectorIndex.fromDict(vec);
      if (!setsEqual(new Set(vectorIndex.vectors.keys()), manifestUids)) return null;
      if (!mapsEqual(vectorIndex.idByUid, expectedIds)) return null;
    }

    return { manifest, index, searchIndex, vectorIndex };
  } catch {
    // loadSnapshot only ever reads the cache file, so any failure is a cache problem -> rebuild.
    return null;
  }
}
```

Export the new symbols from `ts/src/index.ts` by adding to the `./snapshot.js` block (create the block — `snapshot.ts` is not yet exported). Add after the `Corpus` export line:

```ts
export {
  type CorpusFile,
  type ManifestEntry,
  type Snapshot,
  SNAPSHOT_LANG,
  SNAPSHOT_SCHEMA_VERSION,
  hashBytes,
  iterCorpusFiles,
  loadSnapshot,
  pathForNodeId,
  readJson,
  snapshotPath,
  writeJsonAtomic,
  writeSnapshot,
} from "./snapshot.js";
```

> Note on the `require` in the test: the test uses `require("node:fs")` only to re-read the written file for tampering. If biome flags `require` in an ESM test, replace those two reads with a top-level `import { readFileSync } from "node:fs"` and use `readFileSync` directly. Prefer the import form to keep biome clean.

Replace the two `require("node:fs").readFileSync(...)` occurrences in the test with a top-level `import { readFileSync, writeFileSync } from "node:fs"` and `readFileSync(...)` calls before running.

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npm test -- snapshot-load`
Expected: PASS. Then `rtk npm test` (full), `rtk npm run typecheck`, `rtk npm run check` clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/src/snapshot.ts ts/src/index.ts ts/tests/snapshot-load.test.ts
rtk git commit -m "feat(ts-persistence): Snapshot document, writeSnapshot, validated loadSnapshot"
```

---

### Task 6: `Corpus` load / reconcile / full-rebuild + `flushIndex`

Rewrite `Corpus` construction to load the snapshot and either reconcile (only changed/added/deleted files are parsed) or full-rebuild, maintain an in-memory `manifest`, and add `flushIndex()`. Drops the `readonly` on `index`/`searchIndex`/`vectorIndex` (they are now set by one of two code paths) and adds the manifest field. Mirrors `corpus.py` `__init__`, `_full_rebuild`, `_reconcile`, `flushIndex`, `_relPath`, `_recordManifest` (lines 52–132).

**Files:**
- Modify: `ts/src/corpus.ts`
- Test: `ts/tests/corpus-persistence.test.ts`

**Interfaces:**
- Consumes: `loadSnapshot`, `writeSnapshot`, `iterCorpusFiles`, `hashBytes`, `pathForNodeId`, `type ManifestEntry`, `type Snapshot` (Task 5); `nodeFromMarkdown`, `nodeToMarkdown` (`./frontmatter.js`).
- Produces:
  - `Corpus.flushIndex(): void`.
  - `Corpus.manifest: Map<string, ManifestEntry>` (public, read by tests).
  - private `relPath`, `recordManifest`, `fullRebuild`, `reconcile`.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/corpus-persistence.test.ts`:

```ts
import { existsSync, mkdtempSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { CollisionError } from "../src/errors.js";
import { nodeToMarkdown } from "../src/frontmatter.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { snapshotPath } from "../src/snapshot.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-persist-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function seed(): Corpus {
  const c = new Corpus(root);
  c.add(makeNode({ id: "topic:a", kind: "topic", title: "A", body: "alpha gamma", relations: [relatesTo("topic:a", "topic:b")] }));
  c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", body: "beta gamma" }));
  return c;
}

function results(c: Corpus): unknown {
  return {
    searchGamma: c.search("gamma").map((h) => [h.id, h.uid]),
    outboundA: c.outbound("topic:a").map((e) => [e.relation.target, e.targetUid]),
    dangling: c.dangling().length,
  };
}

function freshRebuild(): Corpus {
  rmSync(snapshotPath(root));
  return new Corpus(root);
}

describe("Corpus persistence", () => {
  it("round-trip load matches a fresh rebuild", () => {
    const c = seed();
    c.flushIndex();
    expect(statSync(snapshotPath(root)).isFile()).toBe(true);
    const loaded = new Corpus(root);
    const fresh = freshRebuild();
    expect(results(loaded)).toEqual(results(c));
    expect(results(loaded)).toEqual(results(fresh));
  });

  it("construction never writes the snapshot", () => {
    seed(); // no flush
    expect(existsSync(snapshotPath(root))).toBe(false);
    new Corpus(root); // full rebuild, must not write
    expect(existsSync(snapshotPath(root))).toBe(false);
  });

  it("reconciles a direct on-disk edit (same uid/id, content change)", () => {
    const c = seed();
    c.flushIndex();
    const b = c.store.readFile("topic:b");
    b.body = "beta delta epsilon";
    writeFileSync(c.store.pathFor("topic:b"), nodeToMarkdown(b), "utf-8");
    const reconciled = new Corpus(root);
    expect(reconciled.search("delta").map((h) => [h.id, h.uid])).toEqual([["topic:b", b.uid]]);
  });

  it("reconciles added and deleted files", () => {
    const c = seed();
    c.flushIndex();
    rmSync(c.store.pathFor("topic:a"));
    c.store.writeFile(makeNode({ id: "topic:c", kind: "topic", title: "C", body: "gamma" }));
    const reconciled = new Corpus(root);
    expect(new Set(reconciled.search("gamma").map((h) => h.id))).toEqual(new Set(["topic:b", "topic:c"]));
  });

  it("silently rebuilds from a corrupt snapshot", () => {
    const c = seed();
    c.flushIndex();
    writeFileSync(snapshotPath(root), "{garbage", "utf-8");
    const rebuilt = new Corpus(root); // must not throw
    expect(results(rebuilt)).toEqual(results(c));
  });

  it("propagates a malformed corpus file on construction", () => {
    seed();
    const c2 = new Corpus(root);
    c2.flushIndex();
    writeFileSync(c2.store.pathFor("topic:a"), "---\nnot: valid node\n---\nbody", "utf-8");
    expect(() => new Corpus(root)).toThrow();
  });

  it("raises CollisionError when reconcile introduces a duplicate uid", () => {
    const c = seed();
    c.flushIndex();
    const a = c.store.readFile("topic:a");
    const b = c.store.readFile("topic:b");
    b.uid = a.uid;
    writeFileSync(c.store.pathFor("topic:b"), nodeToMarkdown(b), "utf-8");
    expect(() => new Corpus(root)).toThrow(CollisionError);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npm test -- corpus-persistence`
Expected: FAIL — `Corpus.flushIndex`/`manifest` are not defined; the round-trip test fails because construction does not yet load a snapshot.

- [ ] **Step 3: Write the implementation**

In `ts/src/corpus.ts`:

1. Extend imports:

```ts
import { nodeFromMarkdown, nodeToMarkdown } from "./frontmatter.js";
import {
  type ManifestEntry,
  type Snapshot,
  hashBytes,
  iterCorpusFiles,
  loadSnapshot,
  pathForNodeId,
  writeSnapshot,
} from "./snapshot.js";
```

2. Replace the class field declarations and constructor. Change the three index fields off `readonly` and add `manifest`:

```ts
  readonly store: Store;
  readonly registry?: Registry;
  index!: Index;
  searchIndex!: SearchIndex;
  readonly embedder?: Embedder;
  readonly vectorCache?: VectorCache;
  vectorIndex?: VectorIndex;
  manifest: Map<string, ManifestEntry>;

  constructor(root: string, registry?: Registry, embedder?: Embedder) {
    this.store = new Store(root);
    this.registry = registry;
    this.embedder = embedder;
    this.vectorCache = embedder !== undefined ? new VectorCache(root) : undefined;
    this.manifest = new Map();
    const namespace = embedder !== undefined ? embedder.cacheNamespace : null;
    const snap = loadSnapshot(this.store.root, namespace);
    if (snap === null) this.fullRebuild();
    else this.reconcile(snap);
  }
```

3. Add the private helpers and `flushIndex` (place right after the constructor, before `idFor`):

```ts
  private relPath(nodeId: string): string {
    return pathForNodeId(nodeId);
  }

  private recordManifest(node: Node): void {
    const path = this.relPath(node.id);
    const data = Buffer.from(nodeToMarkdown(node), "utf-8");
    this.manifest.set(path, { path, sha256: hashBytes(data), uid: node.uid });
  }

  private fullRebuild(): void {
    const nodes: Node[] = [];
    const manifest = new Map<string, ManifestEntry>();
    for (const f of iterCorpusFiles(this.store.root)) {
      const node = nodeFromMarkdown(f.data.toString("utf-8"));
      nodes.push(node);
      manifest.set(f.path, { path: f.path, sha256: f.sha256, uid: node.uid });
    }
    this.index = Index.build(nodes);
    this.searchIndex = SearchIndex.build(nodes);
    if (this.embedder !== undefined) {
      this.vectorIndex = VectorIndex.build(nodes, this.embedder, this.vectorCache as VectorCache);
    } else {
      this.vectorIndex = undefined;
    }
    this.manifest = manifest;
  }

  private reconcile(snap: Snapshot): void {
    this.index = snap.index;
    this.searchIndex = snap.searchIndex;
    this.vectorIndex = snap.vectorIndex ?? undefined;
    const old = new Map<string, ManifestEntry>(snap.manifest.map((m) => [m.path, m]));
    const newManifest = new Map<string, ManifestEntry>();
    const changed: Array<{ path: string; sha256: string; node: Node }> = [];
    const drops: string[] = [];
    const current = new Set<string>();
    for (const f of iterCorpusFiles(this.store.root)) {
      current.add(f.path);
      const prev = old.get(f.path);
      if (prev !== undefined && prev.sha256 === f.sha256) {
        newManifest.set(f.path, prev); // unchanged: keep deserialized state, no parse
        continue;
      }
      if (prev !== undefined) drops.push(prev.uid);
      changed.push({ path: f.path, sha256: f.sha256, node: nodeFromMarkdown(f.data.toString("utf-8")) });
    }
    for (const [path, m] of old) {
      if (!current.has(path)) drops.push(m.uid); // deleted on disk
    }
    for (const uid of drops) {
      this.index.remove(uid);
      this.searchIndex.remove(uid);
      this.vectorIndex?.remove(uid);
    }
    for (const { path, sha256, node } of changed) {
      // Full build() collision contract: duplicate uid is rejected outright, then assertAddable.
      if (this.index.byUid.has(node.uid)) throw new CollisionError(`duplicate uid ${JSON.stringify(node.uid)} in corpus`);
      this.index.assertAddable(node);
      const prepared =
        this.vectorIndex !== undefined
          ? this.vectorIndex.prepare(node, this.embedder as Embedder, this.vectorCache as VectorCache)
          : undefined;
      this.index.upsert(node);
      this.searchIndex.upsert(node);
      if (this.vectorIndex !== undefined && prepared !== undefined) this.vectorIndex.commit(node, prepared);
      newManifest.set(path, { path, sha256, uid: node.uid });
    }
    this.manifest = newManifest;
  }

  flushIndex(): void {
    const manifest = [...this.manifest.values()].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
    writeSnapshot(this.store.root, manifest, this.index, this.searchIndex, this.vectorIndex);
  }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npm test -- corpus-persistence`
Expected: PASS. Then `rtk npm test` (full — `corpus.test.ts`, `corpus_parity.test.ts`, `corpus-search.test.ts`, `corpus-similarity.test.ts`, `index-rebuild-equivalence.test.ts` must all stay green: the rewritten constructor preserves the from-scratch build path), `rtk npm run typecheck`, `rtk npm run check` clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/src/corpus.ts ts/tests/corpus-persistence.test.ts
rtk git commit -m "feat(ts-persistence): Corpus load/reconcile/full-rebuild + flushIndex with in-memory manifest"
```

---

### Task 7: Manifest maintenance across `add`/`delete`/`rename`, Store walker parity + docs

Wire the in-memory manifest into every write path so `flushIndex()` needs no re-reads, route `Store.allNodes()` through the same `iterCorpusFiles()` walker as `Corpus`, and document the TS index-persistence subsection. `add` records the node after its upserts; `delete` removes the path entry; `rename` removes the old path when the node moves and re-records the renamed node plus every rewritten referrer (their bytes changed). The shared walker keeps `.nodes-index` private for both corpus construction and the lower-level store listing API.

**Files:**
- Modify: `ts/src/corpus.ts`
- Modify: `ts/src/store.ts`
- Modify: `docs/format.md`
- Test: `ts/tests/corpus-persistence-rename.test.ts`
- Test: `ts/tests/store.test.ts`

**Interfaces:**
- Consumes: `recordManifest`, `relPath`, `manifest` (Task 6); `iterCorpusFiles` (for the test's disk-vs-memory check and `Store.allNodes()`).
- Produces: no new public surface — `add`/`delete`/`rename` keep `manifest` consistent with disk, and `Store.allNodes()` ignores `.nodes-index`.

- [ ] **Step 1: Write the failing test**

Create `ts/tests/corpus-persistence-rename.test.ts`:

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { iterCorpusFiles, loadSnapshot, snapshotPath } from "../src/snapshot.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-persist-rename-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function manifestMatchesDisk(c: Corpus): boolean {
  const onDisk = new Map(iterCorpusFiles(c.store.root).map((f) => [f.path, f.sha256]));
  if (onDisk.size !== c.manifest.size) return false;
  for (const [path, e] of c.manifest) if (onDisk.get(path) !== e.sha256) return false;
  return true;
}

function results(c: Corpus): unknown {
  return [
    c.search("gamma").map((h) => [h.id, h.uid]).sort(),
    c.dangling().map((e) => [e.relation.source, e.relation.target]).sort(),
    [...c.index.idToUid.keys()].sort(),
  ];
}

describe("Corpus manifest maintenance", () => {
  it("add keeps the manifest in sync with disk", () => {
    const c = new Corpus(root);
    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A", body: "gamma" }));
    c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", body: "gamma" }));
    expect(manifestMatchesDisk(c)).toBe(true);
  });

  it("delete removes the manifest entry", () => {
    const c = new Corpus(root);
    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A", body: "gamma" }));
    c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", body: "gamma" }));
    c.delete("topic:a");
    expect(c.manifest.has("topic/a.md")).toBe(false);
    expect(manifestMatchesDisk(c)).toBe(true);
  });

  it("rename updates referrers and removes the old path", () => {
    const c = new Corpus(root);
    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A", body: "gamma", relations: [relatesTo("topic:a", "topic:b")] }));
    c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", body: "gamma" }));
    c.rename("topic:b", "topic:b2"); // rewrites a.md (referrer) and moves b.md -> b2.md
    expect(c.manifest.has("topic/b.md")).toBe(false);
    expect(c.manifest.has("topic/b2.md")).toBe(true);
    expect(manifestMatchesDisk(c)).toBe(true); // referrer a.md re-hashed too
  });

  it("flush after a mutation sequence reloads equivalently and matches a fresh rebuild", () => {
    const c = new Corpus(root);
    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A", body: "gamma", relations: [relatesTo("topic:a", "topic:b")] }));
    c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", body: "gamma" }));
    c.rename("topic:b", "topic:b2");
    c.add(makeNode({ id: "topic:c", kind: "topic", title: "C", body: "gamma" }));
    c.delete("topic:a");
    c.flushIndex();
    const reloaded = new Corpus(root);
    expect(loadSnapshot(root, null)).not.toBeNull();
    expect(results(reloaded)).toEqual(results(c));
    rmSync(snapshotPath(root));
    expect(results(new Corpus(root))).toEqual(results(c));
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npm test -- corpus-persistence-rename`
Expected: FAIL — `add`/`delete`/`rename` do not yet maintain `manifest`, so `manifestMatchesDisk` returns `false` (the manifest is empty after `add`).

- [ ] **Step 3: Write the implementation**

In `ts/src/corpus.ts`:

1. In `add`, record the manifest entry after the upserts. Replace the tail of `add` (the `return node;`) so it reads:

```ts
    if (this.vectorIndex !== undefined && prepared !== undefined) {
      this.vectorIndex.commit(node, prepared);
    }
    this.recordManifest(node);
    return node;
```

2. In `delete`, capture the relative path before deleting and drop it from the manifest. Replace the body of `delete`:

```ts
  delete(nodeId: string): void {
    const uid = this.index.idToUid.get(nodeId);
    if (uid === undefined) throw new RefError(`no live node at ${JSON.stringify(nodeId)}`);
    const path = this.relPath(nodeId);
    this.store.deleteFile(nodeId);
    this.index.remove(uid);
    this.searchIndex.remove(uid);
    this.vectorIndex?.remove(uid);
    this.manifest.delete(path);
  }
```

3. In `rename`, capture the old relative path, then after the commits remove the old path (when moved) and re-record the renamed node and every referrer. The renamed node's `oldPath`/`newPath` comparison already exists; add `oldRelPath` next to it and the manifest updates at the end. Replace the rename body from the `const oldPath` line through the final `return node;`:

```ts
    // 3. Rewrite the renamed node itself (incl. its own oldId refs).
    const node = this.store.readFile(oldId);
    const oldPath = this.store.pathFor(oldId);
    const oldRelPath = this.relPath(oldId);
    node.id = newId;
    node.kind = NodeId.parse(newId).kind;
    if (!node.deprecatedIds.includes(oldId)) node.deprecatedIds.push(oldId);
    rewriteRefs(node, oldId, newId);

    // 4. Rewrite every OTHER referrer in memory.
    const referrers: Node[] = [];
    for (const referrerUid of referrerUids) {
      if (referrerUid === uid) continue;
      const referrer = this.store.readFile(this.idFor(referrerUid));
      rewriteRefs(referrer, oldId, newId);
      referrers.push(referrer);
    }

    // 5. Validate ALL writes before ANY write (fail-early, no partial rename).
    if (this.registry !== undefined) {
      this.registry.validate(node);
      for (const referrer of referrers) this.registry.validate(referrer);
    }

    // 5b. Prepare the renamed node's + referrers' vectors (fail before any disk write).
    const prepared =
      this.vectorIndex !== undefined
        ? this.vectorIndex.prepare(node, this.embedder as Embedder, this.vectorCache as VectorCache)
        : undefined;
    const preparedReferrers =
      this.vectorIndex !== undefined
        ? referrers.map((r) => (this.vectorIndex as VectorIndex).prepare(r, this.embedder as Embedder, this.vectorCache as VectorCache))
        : [];

    // 6. Commit: renamed node first (crash-atomic), then referrers. Each written once.
    const newPath = this.store.writeFile(node);
    if (oldPath !== newPath) this.store.deleteFile(oldId);
    this.index.upsert(node);
    for (let i = 0; i < referrers.length; i++) {
      const referrer = referrers[i];
      this.store.writeFile(referrer);
      this.index.upsert(referrer);
      this.searchIndex.upsert(referrer);
      if (this.vectorIndex !== undefined) this.vectorIndex.commit(referrer, preparedReferrers[i]);
    }

    this.searchIndex.upsert(node);
    if (this.vectorIndex !== undefined && prepared !== undefined) {
      this.vectorIndex.commit(node, prepared);
    }

    // 7. Manifest: remove old path on move; re-record the renamed node and every rewritten referrer.
    if (oldPath !== newPath) this.manifest.delete(oldRelPath);
    this.recordManifest(node);
    for (const referrer of referrers) this.recordManifest(referrer);
    return node;
```

> Note: the existing TS `rename` upserts referrers into the structural index but did NOT previously call `searchIndex.upsert(referrer)` or commit referrer vectors — the Python `rename` does (a referrer's body is unchanged by a rename, so its search/vector state is unchanged, but Python refreshes it for the externally-edited-referrer case). This step brings TS `rename` to parity with Python by upserting referrers into search and committing their vectors, and preparing referrer vectors before any disk write. Confirm `corpus-similarity.test.ts`'s rename test stays green after this change.

4. Route `Store.allNodes()` through `iterCorpusFiles()` and add a store-level regression test. In `ts/src/store.ts`, import `iterCorpusFiles` and replace the recursive scan with:

```ts
  allNodes(): Node[] {
    return iterCorpusFiles(this.root).map((f) => nodeFromMarkdown(f.data.toString("utf-8")));
  }
```

Append this test to `ts/tests/store.test.ts`:

```ts
  it("allNodes ignores the private .nodes-index tree", () => {
    store.writeFile(n("topic:a", "topic"));
    mkdirSync(join(root, ".nodes-index"));
    writeFileSync(join(root, ".nodes-index", "cache.md"), "not a node");
    expect(store.allNodes().map((x) => x.id)).toEqual(["topic:a"]);
  });
```

5. Append the index-persistence subsection to `docs/format.md`. Add this section at the end of the file (match the file's existing heading style — read the file first to confirm the heading level and tone, then append):

```markdown
### Index persistence (TypeScript)

The TypeScript kernel persists its three derived indexes (structural `Index`, `SearchIndex`,
`VectorIndex`) to a private, disposable, per-language cache so that constructing a `Corpus` over
an unchanged corpus skips the full parse + re-index pass.

- **Location:** `<root>/.nodes-index/snapshot.ts.json` (git-ignored). The Python kernel writes
  `snapshot.py.json`; neither language reads the other's file.
- **Writing is explicit:** call `corpus.flushIndex()`. Construction never writes the snapshot.
- **Loading reconciles by content hash:** every `new Corpus(root)` walks the `*.md` files, hashes
  their bytes, and diffs against the snapshot manifest — unchanged files are reused without parsing,
  changed/added files are parsed and upserted, deleted files are dropped. A missing, stale, or
  corrupt snapshot triggers a silent full rebuild (it is a cache, never the source of truth).
- **Files remain authoritative.** The snapshot can be deleted at any time with no loss of
  correctness — only the startup-speed benefit.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk npm test -- corpus-persistence-rename store`
Expected: PASS. Then `rtk npm test` (full — every existing test, especially `corpus-similarity.test.ts`'s rename test and `corpus.test.ts`, must stay green), `rtk npm run typecheck`, `rtk npm run check` clean.

- [ ] **Step 5: Commit**

```bash
rtk git add ts/src/corpus.ts ts/src/store.ts docs/format.md ts/tests/corpus-persistence-rename.test.ts ts/tests/store.test.ts
rtk git commit -m "feat(ts-persistence): manifest maintenance across add/delete/rename + docs"
```

---

## Self-Review

**1. Spec coverage** (against `docs/designs/2026-06-23-nodes-index-persistence-design.md` and the implemented Python):

- §2 architecture (pure indexes + `snapshot.ts` owns I/O + `Corpus` owns manifest): Tasks 1–6.
- §2.1 file layout (`snapshot.ts.json`, `lang "ts"`): Tasks 1, 5.
- §2.2 document shape (version/lang/manifest/structural/search/vectors|null): Task 5 `writeSnapshot`.
- §3 manifest byte-level invariant on both rebuild and reconcile; write-path hashing of `nodeToMarkdown`; rename referrer re-hash + old-path removal: Tasks 6, 7.
- §4 load/reconcile; §4.1 full `build()` collision contract (duplicate-uid reject before `assertAddable`): Task 6 `reconcile`.
- §4 error scoping (silent only for cache; corpus/collision errors propagate): Task 5 `loadSnapshot` catch is cache-only; Task 6 reconcile/fullRebuild let parse + `CollisionError` propagate — covered by the malformed-file and uid-collision tests.
- §5 integrity validation (dup manifest uids, structural bijection, search bijection incl. posting uid presence and field-length bounds, vector uid-map + dim + namespace, manifest-path↔id, idByUid↔structural): Tasks 2, 3, 5.
- §6 embedder rules (no-embedder ignores vectors; embedder requires matching namespace section): Task 5 `loadSnapshot` (vectors only read when `embedderNamespace !== null`), covered by the corrupt-vectors-ignored and namespace-mismatch tests.
- §7 per-index serialization incl. shared-`Relation` invariant: Tasks 2 (search totals recompute), 3 (vectors verbatim + normalization check), 4 (structural replay).
- §8 `flushIndex` (atomic write, vectors null without embedder); construction never writes: Tasks 5, 6.
- §9 error-handling summary: Tasks 5, 6 (and the propagation tests in Task 6).
- §10 testing matrix: every listed scenario maps to a test in Tasks 1–7 (round-trip, on-disk mutation, rename manifest, invalidation → silent rebuild, no-embedder tolerance, error propagation, full collision contract, empty-embedder corpus via Task 3's empty round-trip + Task 5's no-vectors-with-embedder, relation identity, integrity guards).
- §11 module/file map: `snapshot.ts` created (Tasks 1, 5); `search.ts`/`similarity.ts`/`structural-index.ts` modified (Tasks 2–4); `corpus.ts` modified (Tasks 6, 7); `store.ts` modified (Task 7); `docs/format.md` extended (Task 7).

**2. Placeholder scan:** No unresolved placeholders or hand-wavy "similar to Task N" steps — every step carries its full code. The `docs/format.md` step instructs reading the file first to match heading level, with the exact content to append provided.

**3. Type consistency:** Method names are stable across tasks — `toDict`/`fromDict` (camelCase, matching TS convention; Python uses `to_dict`/`from_dict`), `flushIndex`, `loadSnapshot`, `writeSnapshot`, `iterCorpusFiles`, `hashBytes`, `pathForNodeId`, `recordManifest`, `relPath`, `fullRebuild`, `reconcile`. `ManifestEntry`/`CorpusFile`/`Snapshot` shapes are defined in Task 1/5 and consumed unchanged in Task 6. The `Corpus.manifest` field (Task 6) is the type read by Task 7's tests. Structural snapshot entries use `structuralRefs`, never a copied `membership` object.

One parity adjustment is called out explicitly (Task 7, step 3 note): the existing TS `rename` did not refresh referrers' search/vector state; this plan brings it to parity with Python. This is intentional and verified by keeping `corpus-similarity.test.ts` green.
