import { cpSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Corpus } from "../src/index.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures", import.meta.url));

interface OracleRow {
  op: "members" | "containers" | "descendants" | "ancestors";
  ref: string;
  expect: string[];
}

function copiedCorpus(): string {
  const root = join(mkdtempSync(join(tmpdir(), "nodes-traversal-parity-")), "check-corpus");
  cpSync(join(FIXTURES, "check-corpus"), root, { recursive: true });
  return root;
}

describe("traversal parity", () => {
  it("membership traversal matches the committed oracle", () => {
    // Cross-language freeze: same fixture + oracle as the Python kernel. Traversal is
    // registry-independent, so the corpus is constructed without a registry.
    const corpus = new Corpus(copiedCorpus());
    const oracle: OracleRow[] = JSON.parse(readFileSync(join(FIXTURES, "traversal.oracle.json"), "utf-8"));
    expect(oracle.length).toBeGreaterThan(0);
    for (const row of oracle) {
      expect(corpus[row.op](row.ref), `${row.op}(${row.ref})`).toEqual(row.expect);
    }
  });
});
