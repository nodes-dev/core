import { existsSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
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

  it("ignores markdown symlinks and does not descend into symlinked directories", () => {
    write("real/inside.md", "inside");
    write("target.md", "target");
    try {
      symlinkSync(join(root, "target.md"), join(root, "linked.md"));
      symlinkSync(join(root, "real"), join(root, "linked-dir"));
    } catch {
      return;
    }

    expect(listCorpusFileStats(root).map((row) => row.path)).toEqual(["real/inside.md", "target.md"]);
  });

  it("changes the on-disk fingerprint when a corpus file's size changes", () => {
    write("a.md", "one");
    const before = readCorpusFingerprint(root);

    write("a.md", "a much longer body");
    const after = readCorpusFingerprint(root);

    expect(sameCorpusFingerprint(before, after)).toBe(false);
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
