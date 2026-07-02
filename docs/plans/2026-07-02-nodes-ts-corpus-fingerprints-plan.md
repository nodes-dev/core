# Nodes TypeScript Corpus Fingerprints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add domain-free stat-only corpus file listing and fingerprint primitives to `@nodes/kernel`, sharing the same corpus membership rules as `iterCorpusFiles(root)`.

**Architecture:** `ts/src/snapshot.ts` keeps ownership of corpus file traversal. A new private path-listing helper becomes the single source of truth for both existing byte reads and new stat-only fingerprints. `ts/src/index.ts` re-exports the new public API from the package barrel.

**Tech Stack:** TypeScript ESM, Node >=20, Vitest, Biome, `tsc`, `npm`, `rtk`.

---

## File Structure

- Modify `ts/src/snapshot.ts`
  - Add `CorpusFileStat` and `CorpusFingerprint` interfaces.
  - Add private `WalkedCorpusPath` and `listCorpusMarkdownPaths(root)` helper.
  - Refactor `iterCorpusFiles(root)` to use the shared path helper.
  - Add `listCorpusFileStats(root)`, `readCorpusFingerprint(root)`, and `sameCorpusFingerprint(a, b)`.
- Modify `ts/src/index.ts`
  - Re-export the new types and functions from `./snapshot.js`.
- Create `ts/tests/corpus-fingerprint.test.ts`
  - Cover missing/empty roots, sorting, nested markdown files, ignored non-corpus files, symlink skip, stat metadata, fingerprint equality/difference, and path agreement with `iterCorpusFiles(root)`.
- No Mindful files change in this plan.
- No Python files change in this plan.

## Global Constraints

- Run all commands from `~/d/nodes/ts` unless a step says otherwise.
- Use `rtk` for shell commands.
- Do not change `Corpus`, snapshot schema, snapshot file layout, or mutation semantics.
- Preserve current `iterCorpusFiles(root)` observable behavior: same rows, same sorting, same hashes, and file-level errors still propagate.
- Directory traversal remains permissive: missing root and unreadable directories produce no rows for that subtree.
- File-level `statSync`/`readFileSync` errors propagate.
- Do not add Mindful-specific scopes such as `thought/`.

---

### Task 1: Public Behavior Tests

**Files:**
- Create: `ts/tests/corpus-fingerprint.test.ts`
- Read: `ts/tests/snapshot-io.test.ts`
- Read: `ts/src/snapshot.ts`

- [ ] **Step 1: Create failing tests for the new API**

Create `ts/tests/corpus-fingerprint.test.ts`:

```ts
import { existsSync, mkdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  type CorpusFileStat,
  type CorpusFingerprint,
  iterCorpusFiles,
  listCorpusFileStats,
  readCorpusFingerprint,
  sameCorpusFingerprint,
} from "../src/snapshot.js";

let root: string;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-fp-"));
});

afterEach(() => rmSync(root, { recursive: true, force: true }));

function write(path: string, body: string): void {
  const full = join(root, path);
  mkdirSync(dirname(full), { recursive: true });
  writeFileSync(full, body, "utf-8");
}

describe("corpus stat fingerprints", () => {
  it("returns an empty stat list for an empty root", () => {
    expect(listCorpusFileStats(root)).toEqual([]);
    expect(readCorpusFingerprint(root)).toEqual({ files: [] });
  });

  it("returns an empty stat list for a missing root", () => {
    const missing = join(root, "missing");
    expect(existsSync(missing)).toBe(false);
    expect(listCorpusFileStats(missing)).toEqual([]);
    expect(readCorpusFingerprint(missing)).toEqual({ files: [] });
  });

  it("lists regular markdown files as sorted root-relative POSIX paths with stat metadata", () => {
    write("topic/b.md", "BBB");
    write("gene/a.md", "A");
    write("ignore.txt", "nope");
    mkdirSync(join(root, "notes.md"));

    const rows = listCorpusFileStats(root);

    expect(rows.map((row) => row.path)).toEqual(["gene/a.md", "topic/b.md"]);
    expect(rows.map((row) => row.size)).toEqual([1, 3]);
    for (const row of rows) {
      expect(Number.isFinite(row.mtimeMs)).toBe(true);
      expect(row.mtimeMs).toBeGreaterThan(0);
    }
  });

  it("ignores the private root .nodes-index tree", () => {
    mkdirSync(join(root, ".nodes-index"), { recursive: true });
    writeFileSync(join(root, ".nodes-index", "cache.md"), "not a node", "utf-8");
    write("real.md", "real");

    expect(listCorpusFileStats(root).map((row) => row.path)).toEqual(["real.md"]);
  });

  it("ignores markdown symlinks", () => {
    write("target.txt", "target");
    try {
      symlinkSync(join(root, "target.txt"), join(root, "linked.md"));
    } catch {
      return; // symlink unsupported on this platform
    }

    expect(listCorpusFileStats(root)).toEqual([]);
  });

  it("matches iterCorpusFiles path set and order", () => {
    write("zeta/last.md", "Z");
    write("alpha/first.md", "A");

    expect(listCorpusFileStats(root).map((row) => row.path)).toEqual(iterCorpusFiles(root).map((row) => row.path));
  });

  it("compares equal fingerprints exactly", () => {
    const a: CorpusFingerprint = {
      files: [
        { path: "a.md", mtimeMs: 1000.5, size: 10 },
        { path: "b.md", mtimeMs: 1001.5, size: 20 },
      ],
    };
    const b: CorpusFingerprint = {
      files: [
        { path: "a.md", mtimeMs: 1000.5, size: 10 },
        { path: "b.md", mtimeMs: 1001.5, size: 20 },
      ],
    };

    expect(sameCorpusFingerprint(a, b)).toBe(true);
  });

  it("detects path, order, mtime, size, and count differences", () => {
    const base: CorpusFingerprint = {
      files: [
        { path: "a.md", mtimeMs: 1000, size: 10 },
        { path: "b.md", mtimeMs: 1001, size: 20 },
      ],
    };
    const reordered: CorpusFingerprint = {
      files: [
        { path: "b.md", mtimeMs: 1001, size: 20 },
        { path: "a.md", mtimeMs: 1000, size: 10 },
      ],
    };
    const changedPath: CorpusFingerprint = {
      files: [
        { path: "a.md", mtimeMs: 1000, size: 10 },
        { path: "c.md", mtimeMs: 1001, size: 20 },
      ],
    };
    const changedMtime: CorpusFingerprint = {
      files: [
        { path: "a.md", mtimeMs: 1000, size: 10 },
        { path: "b.md", mtimeMs: 1002, size: 20 },
      ],
    };
    const changedSize: CorpusFingerprint = {
      files: [
        { path: "a.md", mtimeMs: 1000, size: 10 },
        { path: "b.md", mtimeMs: 1001, size: 21 },
      ],
    };
    const changedCount: CorpusFingerprint = {
      files: [{ path: "a.md", mtimeMs: 1000, size: 10 }],
    };

    expect(sameCorpusFingerprint(base, reordered)).toBe(false);
    expect(sameCorpusFingerprint(base, changedPath)).toBe(false);
    expect(sameCorpusFingerprint(base, changedMtime)).toBe(false);
    expect(sameCorpusFingerprint(base, changedSize)).toBe(false);
    expect(sameCorpusFingerprint(base, changedCount)).toBe(false);
  });

  it("CorpusFileStat is a plain structural shape", () => {
    const row: CorpusFileStat = { path: "a.md", mtimeMs: 1000, size: 10 };
    expect(row).toEqual({ path: "a.md", mtimeMs: 1000, size: 10 });
  });
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
rtk npm test -- tests/corpus-fingerprint.test.ts
```

Expected: FAIL with TypeScript/Vitest import errors because `CorpusFileStat`, `CorpusFingerprint`, `listCorpusFileStats`, `readCorpusFingerprint`, and `sameCorpusFingerprint` are not exported from `../src/snapshot.js`.

- [ ] **Step 3: Leave the failing tests uncommitted for Task 2**

Run:

```bash
rtk git status --short
```

Expected: `?? tests/corpus-fingerprint.test.ts`. Do not commit a red test-only state; Task 2 commits the green test and implementation together.

---

### Task 2: Snapshot Walker Refactor And Fingerprint Implementation

**Files:**
- Modify: `ts/src/snapshot.ts`
- Test: `ts/tests/corpus-fingerprint.test.ts`
- Test: `ts/tests/snapshot-io.test.ts`

- [ ] **Step 1: Update imports and add public interfaces**

In `ts/src/snapshot.ts`, update the `node:fs` import to include `statSync`:

```ts
import {
  type Dirent,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  statSync,
  writeFileSync,
} from "node:fs";
```

Below `export interface CorpusFile`, add:

```ts
export interface CorpusFileStat {
  readonly path: string;
  readonly mtimeMs: number;
  readonly size: number;
}

export interface CorpusFingerprint {
  readonly files: readonly CorpusFileStat[];
}

interface WalkedCorpusPath {
  readonly path: string;
  readonly fullPath: string;
}
```

- [ ] **Step 2: Extract the shared private path walker**

Replace the current `iterCorpusFiles(root)` implementation with a private path helper plus a refactored byte walk.

Use this exact code in `ts/src/snapshot.ts`, replacing the current `iterCorpusFiles(root)` function:

```ts
function listCorpusMarkdownPaths(root: string): WalkedCorpusPath[] {
  const files: WalkedCorpusPath[] = [];
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
        files.push({ path: relPosix(root, full), fullPath: full });
      }
    }
  };
  walk(root);
  files.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  return files;
}

/** Byte-level walk: read each .md file's bytes once and hash them. Skips the private
 * `.nodes-index` tree, symlinks, and non-files. Sorted by root-relative POSIX path so the
 * order matches Python's `sorted(root.rglob("*.md"))`. */
export function iterCorpusFiles(root: string): CorpusFile[] {
  return listCorpusMarkdownPaths(root).map(({ path, fullPath }) => {
    const data = readFileSync(fullPath);
    return { path, data, sha256: hashBytes(data) };
  });
}
```

- [ ] **Step 3: Add stat-only listing and fingerprint helpers**

Immediately after `iterCorpusFiles(root)` in `ts/src/snapshot.ts`, add:

```ts
/** Stat-level walk over the same corpus file set as `iterCorpusFiles`. Does not read file bodies. */
export function listCorpusFileStats(root: string): CorpusFileStat[] {
  return listCorpusMarkdownPaths(root).map(({ path, fullPath }) => {
    const stat = statSync(fullPath);
    return { path, mtimeMs: stat.mtimeMs, size: stat.size };
  });
}

/** Cheap external-change fingerprint for resident consumers. Not a content-identity hash. */
export function readCorpusFingerprint(root: string): CorpusFingerprint {
  return { files: listCorpusFileStats(root) };
}

export function sameCorpusFingerprint(a: CorpusFingerprint, b: CorpusFingerprint): boolean {
  if (a.files.length !== b.files.length) return false;
  for (let i = 0; i < a.files.length; i++) {
    const left = a.files[i];
    const right = b.files[i];
    if (left.path !== right.path || left.mtimeMs !== right.mtimeMs || left.size !== right.size) return false;
  }
  return true;
}
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
rtk npm test -- tests/corpus-fingerprint.test.ts tests/snapshot-io.test.ts
```

Expected: PASS. `snapshot-io.test.ts` proves the `iterCorpusFiles(root)` refactor preserved existing behavior.

- [ ] **Step 5: Run typecheck**

Run:

```bash
rtk npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit implementation**

```bash
rtk git add src/snapshot.ts tests/corpus-fingerprint.test.ts
rtk git commit -m "feat: add corpus stat fingerprints"
```

---

### Task 3: Package Barrel Exports

**Files:**
- Modify: `ts/src/index.ts`
- Test: `ts/tests/smoke.test.ts`
- Test: `ts/tests/corpus-fingerprint.test.ts`

- [ ] **Step 1: Extend the public-barrel smoke test**

Modify `ts/tests/smoke.test.ts`.

Replace its contents with:

```ts
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  Corpus,
  Index,
  Registry,
  Store,
  listCorpusFileStats,
  makeNode,
  nodeFromMarkdown,
  nodeToMarkdown,
  readCorpusFingerprint,
  registerBuiltinShapes,
  sameCorpusFingerprint,
} from "../src/index.js";

let root: string;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-smoke-"));
});

afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("barrel", () => {
  it("re-exports the public surface", () => {
    expect(typeof makeNode).toBe("function");
    expect(typeof nodeFromMarkdown).toBe("function");
    expect(typeof nodeToMarkdown).toBe("function");
    expect(typeof registerBuiltinShapes).toBe("function");
    expect(typeof Registry).toBe("function");
    expect(typeof Store).toBe("function");
    expect(typeof Corpus).toBe("function");
    expect(typeof Index).toBe("function");
  });

  it("exports corpus fingerprint helpers from the package barrel", () => {
    writeFileSync(join(root, "a.md"), "not parsed by stat helpers", "utf-8");

    expect(listCorpusFileStats(root).map((row) => row.path)).toEqual(["a.md"]);
    expect(sameCorpusFingerprint(readCorpusFingerprint(root), readCorpusFingerprint(root))).toBe(true);
  });
});
```

- [ ] **Step 2: Run the smoke test and verify it fails**

Run:

```bash
rtk npm test -- tests/smoke.test.ts
```

Expected: FAIL with export errors for `listCorpusFileStats`, `readCorpusFingerprint`, and `sameCorpusFingerprint`.

- [ ] **Step 3: Export the new API from `src/index.ts`**

In `ts/src/index.ts`, update the `./snapshot.js` export block to include the new types and functions:

```ts
export {
  type CorpusFile,
  type CorpusFileStat,
  type CorpusFingerprint,
  type ManifestEntry,
  type Snapshot,
  SNAPSHOT_LANG,
  SNAPSHOT_SCHEMA_VERSION,
  hashBytes,
  iterCorpusFiles,
  listCorpusFileStats,
  loadSnapshot,
  pathForNodeId,
  readCorpusFingerprint,
  readJson,
  sameCorpusFingerprint,
  snapshotPath,
  writeJsonAtomic,
  writeSnapshot,
} from "./snapshot.js";
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
rtk npm test -- tests/smoke.test.ts tests/corpus-fingerprint.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run typecheck**

Run:

```bash
rtk npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit barrel exports**

```bash
rtk git add src/index.ts tests/smoke.test.ts
rtk git commit -m "feat: export corpus fingerprint helpers"
```

---

### Task 4: Verification And Documentation Check

**Files:**
- Read: `docs/specs/2026-07-02-nodes-ts-corpus-fingerprints-design.md`
- Read: `ts/src/snapshot.ts`
- Read: `ts/src/index.ts`
- Read: `ts/tests/corpus-fingerprint.test.ts`

- [ ] **Step 1: Run full TypeScript test suite**

Run from `~/d/nodes/ts`:

```bash
rtk npm test
```

Expected: PASS.

- [ ] **Step 2: Run typecheck**

Run:

```bash
rtk npm run typecheck
```

Expected: PASS.

- [ ] **Step 3: Run Biome check**

Run:

```bash
rtk npm run check
```

Expected: PASS.

- [ ] **Step 4: Run build**

Run:

```bash
rtk npm run build
```

Expected: PASS and `dist/` updates locally. Do not commit `dist/` unless it is already tracked and changed by the build.

- [ ] **Step 5: Verify the design contract against the implementation**

Run:

```bash
rtk rg -n "listCorpusMarkdownPaths|listCorpusFileStats|readCorpusFingerprint|sameCorpusFingerprint|statSync" src tests
```

Expected:

- `src/snapshot.ts` contains one private `listCorpusMarkdownPaths` helper.
- `src/snapshot.ts` contains the three exported runtime functions.
- `src/index.ts` re-exports the three exported runtime functions and two exported types.
- `tests/corpus-fingerprint.test.ts` covers behavior.
- No Mindful-specific names such as `thought`, `journal`, `mindmap`, `readModel`, or `semantic` were introduced in `ts/src/snapshot.ts`.

- [ ] **Step 6: Check final git status**

Run from `~/d/nodes`:

```bash
rtk git status --short
```

Expected: clean, or only intentional untracked build artifacts that are not part of this plan.

- [ ] **Step 7: Commit verification-only fixes if needed**

If Step 1-5 required formatting or small test corrections, commit them:

```bash
rtk git add ts/src/snapshot.ts ts/src/index.ts ts/tests/corpus-fingerprint.test.ts ts/tests/smoke.test.ts
rtk git commit -m "test: verify corpus fingerprint contract"
```

If no files changed after verification, skip this step.

---

## Self-Review Checklist

- [ ] Spec §2 Goals: stat-only file walk and deterministic fingerprint are implemented in `ts/src/snapshot.ts`.
- [ ] Spec §3 Non-goals: no Mindful-specific scopes, no resident runtime, no watcher, no storage layer, no Python changes.
- [ ] Spec §4 API: `CorpusFileStat`, `CorpusFingerprint`, `listCorpusFileStats`, `readCorpusFingerprint`, and `sameCorpusFingerprint` exist and are exported from `ts/src/index.ts`.
- [ ] Spec §5 Walk Contract: `iterCorpusFiles` and `listCorpusFileStats` share `listCorpusMarkdownPaths`.
- [ ] Spec §6 Fingerprint Semantics: comparison is exact over `(path, mtimeMs, size)`.
- [ ] Spec §7 Error Handling: directory failures are skipped; file-level stat/read errors propagate.
- [ ] Spec §9 Testing Strategy: tests cover missing roots, sorting, `.nodes-index`, symlinks, exact comparison differences, and agreement with `iterCorpusFiles`.
- [ ] No placeholders remain in this plan.
- [ ] All command snippets use `rtk`.
