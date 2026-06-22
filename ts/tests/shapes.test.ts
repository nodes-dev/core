import { describe, expect, it } from "vitest";
import { FacetError, InvariantError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import {
  MEMBERSHIP,
  membershipOf,
  registerBuiltinShapes,
  requireAcyclic,
  requireDictKeys,
  requireSingleParent,
  requireUniqueMembers,
} from "../src/shapes.js";

function shaped(kind: string, membership: Record<string, unknown>) {
  return makeNode({ id: `${kind}:1`, kind, title: "S", facets: { [MEMBERSHIP]: membership } });
}

describe("shapes", () => {
  it("membershipOf throws FacetError when the facet is absent", () => {
    expect(() => membershipOf(makeNode({ id: "set:1", kind: "set", title: "S" }))).toThrow(FacetError);
  });

  it("membershipOf defaults members and edges to empty", () => {
    const m = membershipOf(shaped("set", { shape: "set" }));
    expect(m.members).toEqual([]);
    expect(m.edges).toEqual([]);
  });

  it("requireUniqueMembers rejects duplicates", () => {
    expect(() => requireUniqueMembers(shaped("set", { shape: "set", members: ["a:1", "a:1"] }))).toThrow(
      InvariantError,
    );
  });

  it("requireDictKeys requires a mapping", () => {
    expect(() => requireDictKeys(shaped("dict", { shape: "dict", members: ["a:1"] }))).toThrow(InvariantError);
    expect(() => requireDictKeys(shaped("dict", { shape: "dict", members: { k: "a:1" } }))).not.toThrow();
  });

  it("requireAcyclic detects a cycle", () => {
    const m = {
      shape: "graph",
      members: ["a:1", "a:2"],
      edges: [
        { source: "a:1", predicate: "e", target: "a:2" },
        { source: "a:2", predicate: "e", target: "a:1" },
      ],
    };
    expect(() => requireAcyclic(shaped("dag", m))).toThrow(InvariantError);
  });

  it("requireSingleParent rejects two parents of one target", () => {
    const m = {
      shape: "tree",
      members: ["a:1", "a:2", "a:3"],
      edges: [
        { source: "a:1", predicate: "e", target: "a:3" },
        { source: "a:2", predicate: "e", target: "a:3" },
      ],
    };
    expect(() => requireSingleParent(shaped("tree", m))).toThrow(InvariantError);
  });

  it("registerBuiltinShapes wires all six shapes; a valid tree passes", () => {
    const reg = new Registry();
    registerBuiltinShapes(reg);
    for (const k of ["set", "list", "dict", "graph", "dag", "tree"]) expect(reg.isRegistered(k)).toBe(true);
    const tree = shaped("tree", {
      shape: "tree",
      members: ["a:1", "a:2"],
      edges: [{ source: "a:1", predicate: "child", target: "a:2" }],
    });
    expect(() => reg.validate(tree)).not.toThrow();
  });
});
