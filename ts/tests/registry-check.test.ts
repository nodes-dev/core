import { describe, expect, it } from "vitest";
import { FacetError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import { SOURCE, registerFixturesProfile } from "./fixtures-profile.js";

function fixturesRegistry(): Registry {
  const reg = new Registry();
  registerFixturesProfile(reg);
  return reg;
}

function codes(violations: { code: string; detail: string }[]): [string, string][] {
  return violations.map((v) => [v.code, v.detail]);
}

describe("Registry.check", () => {
  it("returns no violations for a valid node", () => {
    const reg = fixturesRegistry();
    expect(reg.check(makeNode({ id: "note:a", kind: "note", title: "A" }))).toEqual([]);
  });

  it("reports unknown kind as a single violation", () => {
    const reg = fixturesRegistry();
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
    const reg = fixturesRegistry();
    const node = makeNode({
      id: "paper:p",
      kind: "paper",
      title: "P",
      facets: { [SOURCE]: { identifer: "10.1/x" } },
    });
    expect(codes(reg.check(node))).toEqual([["facet-invalid", ""]]);
  });

  it("maps InvariantError to invariant-violated", () => {
    const reg = fixturesRegistry();
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
    const reg = fixturesRegistry();
    expect(() => reg.validate(makeNode({ id: "paper:p", kind: "paper", title: "P" }))).toThrow(FacetError);
  });

  it("sorts facet names by Unicode code point, not UTF-16 code units", () => {
    const reg = fixturesRegistry();
    // U+FF61 is a single code unit (0xFF61); U+1F600 is a surrogate pair whose lead
    // unit (0xD83D) sorts BEFORE 0xFF61 — code-point order is the reverse.
    const node = makeNode({ id: "note:n", kind: "note", title: "N", facets: { "｡": {}, "\u{1f600}": {} } });
    expect(reg.check(node).map((v) => v.detail)).toEqual(["｡", "\u{1f600}"]);
  });
});
