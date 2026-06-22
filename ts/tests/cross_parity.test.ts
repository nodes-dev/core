import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { nodeFromMarkdown } from "../src/frontmatter.js";
import { toCanonical } from "./_canonical.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures/", import.meta.url));

describe("cross-language parity (check 4)", () => {
  it("TS parses the Python-emitted markdown to the oracle", () => {
    const md = readFileSync(join(FIXTURES, "gene_phf19.py-emit.md"), "utf-8");
    const oracle = JSON.parse(readFileSync(join(FIXTURES, "gene_phf19.canonical.json"), "utf-8"));
    expect(toCanonical(nodeFromMarkdown(md))).toEqual(oracle);
  });
});
