import { cpSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Corpus, Registry, registerBuiltinShapes } from "../src/index.js";
import { registerFixturesProfile } from "./fixtures-profile.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures", import.meta.url));

function copiedCorpus(): string {
  const root = join(mkdtempSync(join(tmpdir(), "nodes-check-parity-")), "check-corpus");
  cpSync(join(FIXTURES, "check-corpus"), root, { recursive: true });
  return root;
}

describe("check parity", () => {
  it("Corpus.check matches the committed oracle", () => {
    // Cross-language freeze: same fixture + oracle as the Python kernel.
    const reg = new Registry();
    registerBuiltinShapes(reg);
    registerFixturesProfile(reg);
    const corpus = new Corpus(copiedCorpus(), reg);
    const oracle = JSON.parse(readFileSync(join(FIXTURES, "check.oracle.json"), "utf-8"));
    expect(oracle.length).toBeGreaterThan(0);
    const actual = corpus.check().map((f) => ({
      severity: f.severity,
      code: f.code,
      ref: f.ref,
      detail: f.detail,
    }));
    expect(actual).toEqual(oracle);
  });

  it("fixture corpus has thirteen nodes", () => {
    expect(new Corpus(copiedCorpus()).all()).toHaveLength(13);
  });
});
