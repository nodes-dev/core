import { describe, expect, it } from "vitest";
import { FacetError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import { SOURCE, registerKnowledgeVocab } from "../src/vocab/index.js";

function vocabRegistry(): Registry {
  const reg = new Registry();
  registerKnowledgeVocab(reg);
  return reg;
}

function codes(violations: { code: string; detail: string }[]): [string, string][] {
  return violations.map((v) => [v.code, v.detail]);
}

describe("Registry.check", () => {
  it("returns no violations for a valid node", () => {
    const reg = vocabRegistry();
    expect(reg.check(makeNode({ id: "note:a", kind: "note", title: "A" }))).toEqual([]);
  });

  it("reports unknown kind as a single violation", () => {
    const reg = vocabRegistry();
    const vs = reg.check(makeNode({ id: "zzz:a", kind: "zzz", title: "A" }));
    expect(codes(vs)).toEqual([["unknown-kind", "zzz"]]);
    expect(vs[0].message).toContain("zzz:a");
  });

  it("collects missing and unexpected facets together", () => {
    const reg = new Registry();
    reg.register({ name: "widget", requiredFacets: new Set(["a", "b"]) });
    const node = makeNode({ id: "widget:w", kind: "widget", title: "W", facets: { c: {} } });
    expect(codes(reg.check(node))).toEqual([
      ["facet-missing", "a"],
      ["facet-missing", "b"],
      ["facet-unexpected", "c"],
    ]);
  });

  it("skips invariants when facet presence fails", () => {
    const reg = new Registry();
    reg.register({
      name: "widget",
      requiredFacets: new Set(["a"]),
      invariants: [
        () => {
          throw new Error("must not run");
        },
      ],
    });
    const node = makeNode({ id: "widget:w", kind: "widget", title: "W" });
    expect(codes(reg.check(node))).toEqual([["facet-missing", "a"]]);
  });

  it("maps invariant FacetError to facet-invalid", () => {
    const reg = vocabRegistry();
    const node = makeNode({
      id: "paper:p",
      kind: "paper",
      title: "P",
      facets: { [SOURCE]: { identifer: "10.1/x" } },
    });
    expect(codes(reg.check(node))).toEqual([["facet-invalid", ""]]);
  });

  it("maps InvariantError to invariant-violated", () => {
    const reg = vocabRegistry();
    const node = makeNode({ id: "paper:p", kind: "paper", title: "P", facets: { [SOURCE]: {} } });
    expect(codes(reg.check(node))).toEqual([["invariant-violated", ""]]);
  });

  it("propagates non-kernel invariant exceptions", () => {
    const reg = new Registry();
    reg.register({
      name: "widget",
      invariants: [
        () => {
          throw new RangeError("programmer bug");
        },
      ],
    });
    expect(() => reg.check(makeNode({ id: "widget:w", kind: "widget", title: "W" }))).toThrow(RangeError);
  });

  it("leaves validate behavior unchanged", () => {
    const reg = vocabRegistry();
    expect(() => reg.validate(makeNode({ id: "paper:p", kind: "paper", title: "P" }))).toThrow(FacetError);
  });
});
