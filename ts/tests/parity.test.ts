import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { nodeFromMarkdown, nodeToMarkdown } from "../src/frontmatter.js";
import { toCanonical } from "./_canonical.js";

// new URL(..., import.meta.url) resolves on all supported Node (no import.meta.dirname dependency).
const FIXTURES = fileURLToPath(new URL("../../fixtures/", import.meta.url));
const SOURCE = join(FIXTURES, "gene_phf19.md");
const ORACLE = join(FIXTURES, "gene_phf19.canonical.json");
const TS_EMIT = join(FIXTURES, "gene_phf19.ts-emit.md");

const oracle = () => JSON.parse(readFileSync(ORACLE, "utf-8"));
const sourceNode = () => nodeFromMarkdown(readFileSync(SOURCE, "utf-8"));

describe("cross-language parity (TS side)", () => {
  it("TS parse of the shared fixture matches the oracle (check 2)", () => {
    expect(toCanonical(sourceNode())).toEqual(oracle());
  });

  it("TS serialize is semantically idempotent (check 5)", () => {
    const once = nodeToMarkdown(sourceNode());
    const twice = nodeToMarkdown(nodeFromMarkdown(once));
    expect(toCanonical(nodeFromMarkdown(twice))).toEqual(oracle());
  });

  it("the committed ts-emit fixture is current (regenerate-and-diff guard)", () => {
    expect(readFileSync(TS_EMIT, "utf-8")).toBe(nodeToMarkdown(sourceNode()));
  });
});
