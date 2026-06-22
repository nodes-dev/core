import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { FacetError, InvariantError, RefError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import { SOURCE, registerKnowledgeVocab } from "../src/vocab/index.js";

function knowledgeRegistry(): Registry {
  const reg = new Registry();
  registerKnowledgeVocab(reg);
  return reg;
}

let root: string;
let corpus: Corpus;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-vocab-corpus-"));
  corpus = new Corpus(root, knowledgeRegistry());
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("Corpus with the knowledge vocab registry", () => {
  it("adds a bare note", () => {
    corpus.add(makeNode({ id: "note:a", kind: "note", title: "A" })); // no throw
    expect(corpus.get("note:a").title).toBe("A");
  });

  it("rejects a paper with an empty source before any disk write", () => {
    expect(() => corpus.add(makeNode({ id: "paper:a", kind: "paper", title: "A", facets: { [SOURCE]: {} } }))).toThrow(
      InvariantError,
    );
    expect(() => corpus.get("paper:a")).toThrow(); // never written
  });

  it("rejects a paper with a stray-keyed source", () => {
    expect(() =>
      corpus.add(makeNode({ id: "paper:b", kind: "paper", title: "B", facets: { [SOURCE]: { identifer: "x" } } })),
    ).toThrow(FacetError);
  });

  it("adds a valid paper and keeps it valid across a rename", () => {
    corpus.add(makeNode({ id: "paper:c", kind: "paper", title: "C", facets: { [SOURCE]: { year: 2026 } } }));
    corpus.rename("paper:c", "paper:c2");
    expect(corpus.get("paper:c2").title).toBe("C");
    expect(corpus.get("paper:c").id).toBe("paper:c2"); // deprecated id still resolves
  });

  it("rejects a rename that would make the renamed node invalid before any disk write", () => {
    corpus.add(makeNode({ id: "paper:a", kind: "paper", title: "A", facets: { [SOURCE]: { year: 2026 } } }));
    expect(() => corpus.rename("paper:a", "note:a")).toThrow(FacetError);
    expect(corpus.get("paper:a").title).toBe("A");
    expect(() => corpus.get("note:a")).toThrow(RefError);
  });

  it("rejects a rename blocked by an invalid referrer before writing anything", () => {
    const seed = new Corpus(root); // no registry: permits seeding an invalid referrer
    seed.add(makeNode({ id: "topic:t", kind: "topic", title: "T" }));
    seed.add(
      makeNode({
        id: "paper:bad",
        kind: "paper",
        title: "Bad",
        facets: { [SOURCE]: {} },
        relations: [{ source: "paper:bad", predicate: "about", target: "topic:t" }],
      }),
    );

    const c = new Corpus(root, knowledgeRegistry());
    expect(() => c.rename("topic:t", "topic:t2")).toThrow(InvariantError);

    const fresh = new Corpus(root);
    expect(fresh.get("topic:t").title).toBe("T");
    expect(() => fresh.get("topic:t2")).toThrow(RefError);
    expect(fresh.get("paper:bad").relations[0]?.target).toBe("topic:t");
  });
});
