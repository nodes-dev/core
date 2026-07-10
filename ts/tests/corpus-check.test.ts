import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import { registerBuiltinShapes } from "../src/shapes.js";
import { SOURCE, registerKnowledgeVocab } from "../src/vocab/index.js";

function vocabRegistry(): Registry {
  const reg = new Registry();
  registerBuiltinShapes(reg);
  registerKnowledgeVocab(reg);
  return reg;
}

function tuples(findings: { severity: string; code: string; ref: string; detail: string }[]) {
  return findings.map((f) => [f.severity, f.code, f.ref, f.detail]);
}

function tmpRoot(): string {
  return mkdtempSync(join(tmpdir(), "nodes-check-"));
}

describe("Corpus.check", () => {
  it("returns no findings for a clean corpus", () => {
    const root = tmpRoot();
    const c = new Corpus(root, vocabRegistry());
    c.add(makeNode({ id: "topic:t", kind: "topic", title: "T" }));
    c.add(
      makeNode({
        id: "note:n",
        kind: "note",
        title: "N",
        relations: [{ source: "note:n", predicate: "about", target: "topic:t", directed: true }],
      }),
    );
    expect(c.check()).toEqual([]);
  });

  it("reports hand-edited violations sorted by (ref, code, detail)", () => {
    const root = tmpRoot();
    const seed = new Corpus(root); // registry-free: simulates hand-edited files
    seed.add(makeNode({ id: "zzz:m", kind: "zzz", title: "M" }));
    seed.add(makeNode({ id: "note:s", kind: "note", title: "S", facets: { [SOURCE]: { year: 2026 } } }));
    seed.add(
      makeNode({
        id: "paper:b",
        kind: "paper",
        title: "B",
        relations: [{ source: "paper:b", predicate: "cites", target: "paper:ghost", directed: true }],
      }),
    );
    const c = new Corpus(root, vocabRegistry());
    expect(tuples(c.check())).toEqual([
      ["error", "facet-unexpected", "note:s", "source"],
      ["warning", "dangling-ref", "paper:b", "paper:ghost"],
      ["error", "facet-missing", "paper:b", "source"],
      ["error", "unknown-kind", "zzz:m", "zzz"],
    ]);
  });

  it("reports only dangling refs without any registry", () => {
    const root = tmpRoot();
    const seed = new Corpus(root);
    seed.add(
      makeNode({
        id: "zzz:m",
        kind: "zzz",
        title: "M",
        relations: [{ source: "zzz:m", predicate: "cites", target: "note:gone", directed: true }],
      }),
    );
    const c = new Corpus(root);
    expect(tuples(c.check())).toEqual([["warning", "dangling-ref", "zzz:m", "note:gone"]]);
  });

  it("passed registry overrides the corpus registry", () => {
    const root = tmpRoot();
    const c = new Corpus(root, vocabRegistry());
    c.add(makeNode({ id: "note:n", kind: "note", title: "N" }));
    expect(tuples(c.check(new Registry()))).toEqual([["error", "unknown-kind", "note:n", "note"]]);
  });

  it("orders details by Unicode code point, not UTF-16 code units", () => {
    const root = tmpRoot();
    const seed = new Corpus(root); // registry-free: simulates hand-edited files
    // U+FF61 (one code unit, 0xFF61) vs U+1F600 (surrogate pair, lead unit 0xD83D):
    // code-unit order puts the emoji first; code-point order puts it last.
    seed.add(makeNode({ id: "note:x", kind: "note", title: "X", facets: { "｡": {}, "\u{1f600}": {} } }));
    const c = new Corpus(root, vocabRegistry());
    expect(c.check().map((f) => f.detail)).toEqual(["｡", "\u{1f600}"]);
  });

  it("does not mutate the corpus", () => {
    const root = tmpRoot();
    const seed = new Corpus(root);
    seed.add(makeNode({ id: "zzz:m", kind: "zzz", title: "M" }));
    const c = new Corpus(root, vocabRegistry());
    c.check();
    expect(c.get("zzz:m").title).toBe("M"); // still readable, file untouched
  });
});
