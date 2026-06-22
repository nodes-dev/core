import { describe, expect, it } from "vitest";
import { NOTE, PAPER, SOURCE, registerKnowledgeVocab, sourceOf } from "../src/vocab/index.js";
import * as vocab from "../src/vocab/index.js";

describe("vocab barrel", () => {
  it("re-exports the public surface", () => {
    expect(typeof registerKnowledgeVocab).toBe("function");
    expect(typeof sourceOf).toBe("function");
    expect(NOTE).toBe("note");
    expect(PAPER).toBe("paper");
    expect(SOURCE).toBe("source");
  });

  it("exposes the predicates namespace", () => {
    expect(vocab.predicates.CITES).toBe("cites");
    expect(typeof vocab.predicates.cites).toBe("function");
  });
});
