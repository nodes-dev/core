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
