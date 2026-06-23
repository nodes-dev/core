import { cpSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { scoreKey } from "../src/ranking.js";

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
