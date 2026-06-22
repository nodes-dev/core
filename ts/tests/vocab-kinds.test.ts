import { beforeEach, describe, expect, it } from "vitest";
import { FacetError, InvariantError, UnknownKindError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import { PROSE_KINDS, SOURCE_KINDS, registerKnowledgeVocab } from "../src/vocab/kinds.js";
import { SOURCE } from "../src/vocab/source.js";

let reg: Registry;
beforeEach(() => {
  reg = new Registry();
  registerKnowledgeVocab(reg);
});

describe("knowledge vocab kinds", () => {
  it("registers all seven kinds", () => {
    for (const name of [...PROSE_KINDS, ...SOURCE_KINDS]) {
      expect(reg.isRegistered(name)).toBe(true);
    }
  });

  it("validates a bare note", () => {
    reg.validate(makeNode({ id: "note:a", kind: "note", title: "A" })); // no throw
  });

  it("rejects a note carrying a stray facet", () => {
    expect(() =>
      reg.validate(makeNode({ id: "note:a", kind: "note", title: "A", facets: { [SOURCE]: { year: 2026 } } })),
    ).toThrow(FacetError);
  });

  it("rejects a paper missing the source facet", () => {
    expect(() => reg.validate(makeNode({ id: "paper:a", kind: "paper", title: "A" }))).toThrow(FacetError);
  });

  it("rejects a paper with an empty source facet", () => {
    expect(() =>
      reg.validate(makeNode({ id: "paper:a", kind: "paper", title: "A", facets: { [SOURCE]: {} } })),
    ).toThrow(InvariantError);
  });

  it("accepts a paper with a valid source facet", () => {
    reg.validate(makeNode({ id: "paper:a", kind: "paper", title: "A", facets: { [SOURCE]: { year: 2026 } } })); // no throw
  });

  it("book and dataset share the source invariant", () => {
    for (const kind of ["book", "dataset"]) {
      expect(() => reg.validate(makeNode({ id: `${kind}:a`, kind, title: "A", facets: { [SOURCE]: {} } }))).toThrow(
        InvariantError,
      );
      reg.validate(makeNode({ id: `${kind}:b`, kind, title: "B", facets: { [SOURCE]: { identifier: "x" } } })); // no throw
    }
  });

  it("an empty registry rejects an unregistered kind", () => {
    const empty = new Registry();
    expect(() => empty.validate(makeNode({ id: "note:a", kind: "note", title: "A" }))).toThrow(UnknownKindError);
  });
});
