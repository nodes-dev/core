# Nodes TypeScript Corpus Fingerprints - Design

**Status:** draft design
**Date:** 2026-07-02
**Scope:** Add domain-free corpus file-listing and stat-fingerprint primitives to the
TypeScript kernel, so downstream apps can validate resident caches without copying the
kernel's private corpus-walk semantics.

---

## 1. Context

`~/d/nodes/ts` is the problem-agnostic knowledge substrate. `~/d/mindful/v6` builds a
thought/journal/mindmap application on top of that substrate. Recent Mindful resident-shell
work needed a cheap "has the corpus changed?" check before reusing a cached `Mindful`
instance. Mindful implemented its own recursive markdown walk and stat fingerprint, then
had to keep that logic aligned with the kernel's `iterCorpusFiles(root)` behavior.

That duplication is the wrong boundary. The kernel already defines which files are part of
a corpus:

- recurse under the corpus root,
- include regular `*.md` files,
- skip `.nodes-index`,
- skip symlinks and non-files,
- sort by root-relative POSIX path.

Downstream apps should not reimplement those rules. They should ask the kernel for a
domain-free view of the corpus file set.

## 2. Goals

- Export a stat-only corpus file walk from the TypeScript kernel.
- Export a deterministic corpus fingerprint based on the same file set.
- Keep the new API domain-free: no thoughts, journals, mindmaps, read models, sidecars, or
  application cache policy.
- Preserve current `iterCorpusFiles(root)` behavior and use the same underlying walk rules.
- Make the API cheap enough for resident-command freshness checks: no file body reads, no
  markdown parsing, no hash computation.
- Give downstream code a single kernel-owned contract for "the files a `Corpus` would
  reconcile."

## 3. Non-goals

- No Mindful-specific scopes such as `thought/` or "catalog dependency" walks. Those remain
  downstream application concerns.
- No resident-session cache implementation in `nodes/ts`.
- No file watcher, daemon, debounce window, trusted marker, or bounded-staleness policy.
- No DuckDB/SQLite storage layer.
- No changes to `Corpus` construction, reconciliation, mutation semantics, or snapshot
  format in this slice.
- No cross-language API guarantee for Python yet. The TypeScript API should be shaped so a
  Python parity slice can add the same concept later, but this design covers TS only.

## 4. API

Add the following exports from `ts/src/snapshot.ts` and `ts/src/index.ts`.

```ts
export interface CorpusFileStat {
  readonly path: string; // root-relative POSIX path
  readonly mtimeMs: number;
  readonly size: number;
}

export interface CorpusFingerprint {
  readonly files: readonly CorpusFileStat[];
}

export function listCorpusFileStats(root: string): CorpusFileStat[];

export function readCorpusFingerprint(root: string): CorpusFingerprint;

export function sameCorpusFingerprint(a: CorpusFingerprint, b: CorpusFingerprint): boolean;
```

`listCorpusFileStats(root)` returns one row per regular corpus markdown file. It never reads
file contents. It reports `mtimeMs` and `size` from `statSync`, because those are the cheap
filesystem signals resident applications can compare on every command. This still costs one
`statSync` syscall per corpus file; the intended win is avoiding full-body reads, hashing,
and markdown parsing. Symlinks are filtered during traversal, so `statSync` is taken only on
paths the shared walker identified as regular markdown files.

`readCorpusFingerprint(root)` is a small wrapper around `listCorpusFileStats(root)`. The
separate name is intentional: downstream code that stores a reusable baseline should depend
on the semantic concept, not on the current representation.

`sameCorpusFingerprint(a, b)` compares order-sensitively after both fingerprints have been
produced by the kernel. Because the file list is sorted by path, order-sensitive comparison
is deterministic and catches path, count, mtime, and size changes without building maps.
`mtimeMs` is compared exactly, not with an epsilon; both values come from the same kernel
stat path, so an unchanged file should produce identical metadata.

## 5. Walk Contract

The new stat walk must match the kernel's corpus membership rules:

- paths are root-relative POSIX strings,
- rows are sorted lexicographically by path,
- only regular files ending in `.md` are included,
- `.nodes-index` is skipped as a private cache directory,
- symlinks are skipped,
- unreadable directories are skipped, matching `iterCorpusFiles(root)`,
- missing roots produce an empty list.

The implementation should avoid a second independently-maintained walker. Prefer a private
helper that both `iterCorpusFiles(root)` and `listCorpusFileStats(root)` use for traversal:

```ts
interface WalkedCorpusPath {
  readonly path: string;
  readonly fullPath: string;
}

function listCorpusMarkdownPaths(root: string): WalkedCorpusPath[];
```

`iterCorpusFiles(root)` then reads and hashes each `fullPath`; `listCorpusFileStats(root)`
stats each `fullPath`. That keeps membership and sorting rules in one place while preserving
the existing public `iterCorpusFiles(root)` behavior. This changes the implementation shape
of `iterCorpusFiles(root)` from "read during traversal" to "list paths, then read paths,"
but it must not change the returned rows, sorting, or error behavior.

## 6. Fingerprint Semantics

The fingerprint is an external-change detector, not a content identity hash.

It answers: "Has the visible corpus file set probably changed since this baseline was
captured?" It deliberately uses `(path, mtimeMs, size)` rather than SHA-256 because resident
freshness checks must not read every file body.

Consequences:

- A content-preserving mtime touch invalidates the fingerprint. This is acceptable; it
  causes a safe reload.
- A filesystem that fails to update mtime/size could hide a content change. This is the same
  mtime-granularity limit any stat-based freshness check carries.
- Applications that require content identity must use existing byte-hashing paths such as
  `iterCorpusFiles(root)` / snapshot reconciliation, not this fingerprint.

The API should document this explicitly. It must not be presented as a cryptographic digest
or as a replacement for snapshot manifest hashes.

## 7. Error Handling

Follow the existing `iterCorpusFiles(root)` traversal posture:

- missing root: empty fingerprint,
- unreadable directory during traversal: skip that subtree,
- symlink: skip,
- stat/read race on an individual file: propagate the file-level filesystem error, including
  `ENOENT`, matching the current bare `readFileSync(full)` behavior in `iterCorpusFiles(root)`.

This mirrors the current split contract: directory traversal is permissive, but once a
regular markdown file has been selected, file-level races and unexpected file errors fail
rather than silently shrinking the corpus.

## 8. Downstream Usage

Mindful's resident runtime should eventually replace its local broad corpus fingerprint
implementation with:

```ts
import { readCorpusFingerprint, sameCorpusFingerprint } from "@nodes/kernel";
```

`@nodes/kernel` is the package name exported by `~/d/nodes/ts/package.json`; the barrel is
`ts/src/index.ts`.

Mindful should still own all application-specific policy:

- when to check the fingerprint,
- whether to invalidate or adopt caches after a command,
- which caches depend on the whole corpus versus Mindful-specific sidecars,
- whether to introduce narrower `thought/`-only checks for catalog caches.

This slice does not move Mindful's catalog, read-model, semantic-index, or shell-session
logic upstream.

## 9. Testing Strategy

TypeScript kernel tests should cover:

- empty and missing roots return `[]`,
- regular nested markdown files are included and sorted by root-relative POSIX path,
- non-markdown files are ignored,
- `.nodes-index` markdown files are ignored,
- symlinked files/directories are ignored,
- `mtimeMs` and `size` changes make `sameCorpusFingerprint` return `false`,
- equal fingerprints compare `true`,
- order-sensitive comparison rejects reordered or path-mismatched rows,
- `iterCorpusFiles(root)` and `listCorpusFileStats(root)` agree on the set and order of
  corpus paths for the same fixture.

Mindful integration tests should wait for a later Mindful slice. That slice can replace the
local resident fingerprint reader with the kernel export and assert behavior remains
unchanged.

## 10. Alternatives Considered

### Keep the fingerprint in Mindful

Rejected. Mindful already copied the kernel's corpus-walk semantics and almost drifted from
them. The kernel owns corpus membership; downstream apps should not mirror it.

### Export `iterCorpusFiles(root)` only

Rejected. `iterCorpusFiles(root)` reads and hashes every file body. Resident freshness checks
need a cheap stat-only path.

### Add Mindful-specific scopes upstream

Rejected. A `thought/`-only walk is useful for Mindful catalog caches but not a kernel
concept. The kernel should expose the broad corpus primitive; Mindful can derive narrower
application scopes locally.

### Use a digest string instead of file rows

Rejected for this slice. A digest is compact, but it hides useful diagnostics and requires
choosing serialization details now. Rows are straightforward, testable, and let downstream
tools report changed path/count/mtime/size if they need to.

## 11. Decisions

1. **Upstream the broad corpus fingerprint primitive, not Mindful cache policy.** Kernel owns
   corpus membership; Mindful owns product behavior.
2. **Use stat metadata, not content hashes.** This keeps resident checks cheap and makes the
   mtime-granularity trade-off explicit.
3. **Share traversal rules with `iterCorpusFiles(root)`.** One private path-listing helper
   prevents future drift.
4. **Keep the API row-shaped.** Rows are easier to inspect and compare; digesting can be
   added later if measurement shows the row comparison itself matters.
5. **Do not add app-specific scopes to `nodes/ts`.** Narrow dependencies belong in
   downstream applications.
