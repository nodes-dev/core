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
