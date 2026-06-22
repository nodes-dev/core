import { cpSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { toCanonical } from "./_canonical.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures/", import.meta.url));

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-parity-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("cross-language rename parity", () => {
  it("TS Corpus.rename over the fixture corpus matches the shared oracle", () => {
    cpSync(join(FIXTURES, "corpus"), root, { recursive: true });
    const c = new Corpus(root);
    c.rename("topic:old", "topic:new");
    const actual = c
      .all()
      .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
      .map(toCanonical);
    const oracle = JSON.parse(readFileSync(join(FIXTURES, "corpus.rename.canonical.json"), "utf-8"));
    expect(actual).toEqual(oracle);
  });
});
