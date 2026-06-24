import { describe, expect, it } from "vitest";
import { FacetError, InvariantError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import {
  EDGES,
  KEYS,
  MEMBERSHIP,
  ORDER,
  edgesOf,
  keysOf,
  membershipOf,
  orderOf,
  registerBuiltinShapes,
  requireUniqueMembers,
} from "../src/shapes.js";

function reg(): Registry {
  const r = new Registry();
  registerBuiltinShapes(r);
  return r;
}

function struct(kind: string, facets: Record<string, Record<string, unknown>>) {
  return makeNode({ id: `${kind}:1`, kind, title: "S", facets });
}

function edge(source: string, target: string) {
  return { source, predicate: "to", target };
}

describe("shapes — facet accessors", () => {
  it("membershipOf throws FacetError when the facet is absent", () => {
    expect(() => membershipOf(makeNode({ id: "set:1", kind: "set", title: "S" }))).toThrow(FacetError);
  });

  it("membershipOf defaults members to empty", () => {
    expect(membershipOf(struct("set", { [MEMBERSHIP]: {} })).members).toEqual([]);
  });

  it("each accessor wraps a malformed facet as FacetError", () => {
    expect(() => membershipOf(struct("set", { [MEMBERSHIP]: { members: [1] } }))).toThrow(FacetError);
    expect(() => orderOf(struct("list", { [ORDER]: { order: [1] } }))).toThrow(FacetError);
    expect(() => keysOf(struct("dict", { [KEYS]: { keys: { a: 1 } } }))).toThrow(FacetError);
    expect(() => edgesOf(struct("graph", { [EDGES]: { edges: [{ source: 1 }] } }))).toThrow(FacetError);
  });
});

describe("shapes — built-in validation", () => {
  it("set requires membership only and rejects duplicates", () => {
    expect(() => reg().validate(struct("set", { [MEMBERSHIP]: { members: ["a:1"] } }))).not.toThrow();
    expect(() => reg().validate(struct("set", { [MEMBERSHIP]: { members: ["a:1", "a:1"] } }))).toThrow(InvariantError);
  });

  it("set rejects form facets it does not own", () => {
    expect(() =>
      reg().validate(struct("set", { [MEMBERSHIP]: { members: ["a:1"] }, [ORDER]: { order: ["a:1"] } })),
    ).toThrow(FacetError);
  });

  it("list requires order to be a permutation of members", () => {
    expect(() =>
      reg().validate(struct("list", { [MEMBERSHIP]: { members: ["a:1", "a:2"] }, [ORDER]: { order: ["a:2", "a:1"] } })),
    ).not.toThrow();
    expect(() =>
      reg().validate(struct("list", { [MEMBERSHIP]: { members: ["a:1", "a:2"] }, [ORDER]: { order: ["a:1"] } })),
    ).toThrow(InvariantError);
  });

  it("list rejects duplicate members (isolated from the permutation check)", () => {
    // duplicate members, but order is NOT itself duplicated: requireUniqueMembers fires first.
    expect(() =>
      reg().validate(struct("list", { [MEMBERSHIP]: { members: ["a:1", "a:1"] }, [ORDER]: { order: ["a:1"] } })),
    ).toThrow(InvariantError);
  });

  it("list missing the order facet is rejected", () => {
    expect(() => reg().validate(struct("list", { [MEMBERSHIP]: { members: ["a:1"] } }))).toThrow(FacetError);
  });

  it("dict requires key values to be members", () => {
    expect(() =>
      reg().validate(struct("dict", { [MEMBERSHIP]: { members: ["a:1"] }, [KEYS]: { keys: { label: "a:1" } } })),
    ).not.toThrow();
    expect(() =>
      reg().validate(struct("dict", { [MEMBERSHIP]: { members: ["a:1"] }, [KEYS]: { keys: { label: "a:2" } } })),
    ).toThrow(InvariantError);
  });

  it("graph requires edge endpoints to be members", () => {
    expect(() =>
      reg().validate(
        struct("graph", { [MEMBERSHIP]: { members: ["a:1", "a:2"] }, [EDGES]: { edges: [edge("a:1", "a:2")] } }),
      ),
    ).not.toThrow();
    expect(() =>
      reg().validate(struct("graph", { [MEMBERSHIP]: { members: ["a:1"] }, [EDGES]: { edges: [edge("a:1", "a:2")] } })),
    ).toThrow(InvariantError);
  });

  it("dag rejects a cycle", () => {
    expect(() =>
      reg().validate(
        struct("dag", {
          [MEMBERSHIP]: { members: ["a:1", "a:2"] },
          [EDGES]: { edges: [edge("a:1", "a:2"), edge("a:2", "a:1")] },
        }),
      ),
    ).toThrow(InvariantError);
  });

  it("dag accepts a diamond (shared sink reached by two paths)", () => {
    expect(() =>
      reg().validate(
        struct("dag", {
          [MEMBERSHIP]: { members: ["a:1", "a:2", "a:3", "a:4"] },
          [EDGES]: { edges: [edge("a:1", "a:2"), edge("a:1", "a:3"), edge("a:2", "a:4"), edge("a:3", "a:4")] },
        }),
      ),
    ).not.toThrow();
  });

  it("tree rejects multiple parents of one target", () => {
    expect(() =>
      reg().validate(
        struct("tree", {
          [MEMBERSHIP]: { members: ["a:1", "a:2", "a:3"] },
          [EDGES]: { edges: [edge("a:1", "a:3"), edge("a:2", "a:3")] },
        }),
      ),
    ).toThrow(InvariantError);
  });

  it("tree rejects a cycle (acyclic failure path on the full tree stack)", () => {
    // each node has in-degree 1 so requireSingleParent passes; the cycle trips requireAcyclic
    // (which runs before requireSingleParent).
    expect(() =>
      reg().validate(
        struct("tree", {
          [MEMBERSHIP]: { members: ["a:1", "a:2"] },
          [EDGES]: { edges: [edge("a:1", "a:2"), edge("a:2", "a:1")] },
        }),
      ),
    ).toThrow(InvariantError);
  });

  it("registerBuiltinShapes wires all six shapes and kinds", () => {
    const r = reg();
    for (const k of ["set", "list", "dict", "graph", "dag", "tree"]) {
      expect(r.isShape(k)).toBe(true);
      expect(r.isRegistered(k)).toBe(true);
    }
  });

  it("a standalone invariant is callable on a node", () => {
    expect(() => requireUniqueMembers(struct("set", { [MEMBERSHIP]: { members: ["a:1", "a:1"] } }))).toThrow(
      InvariantError,
    );
  });
});
