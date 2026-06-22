import { describe, expect, it } from "vitest";
import { FacetError, InvariantError, UnknownKindError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";

function node(facets: Record<string, Record<string, unknown>>) {
  return makeNode({ id: "k:1", kind: "k", title: "T", facets });
}

describe("Registry", () => {
  it("get() throws UnknownKindError for an unregistered kind", () => {
    expect(() => new Registry().get("nope")).toThrow(UnknownKindError);
    expect(new Registry().isRegistered("nope")).toBe(false);
  });

  it("validate() accepts required + optional facets", () => {
    const reg = new Registry();
    reg.register({ name: "k", requiredFacets: new Set(["a"]), optionalFacets: new Set(["b"]) });
    expect(() => reg.validate(node({ a: {}, b: {} }))).not.toThrow();
  });

  it("validate() rejects a missing required facet", () => {
    const reg = new Registry();
    reg.register({ name: "k", requiredFacets: new Set(["a"]) });
    expect(() => reg.validate(node({}))).toThrow(FacetError);
  });

  it("validate() rejects an unexpected facet", () => {
    const reg = new Registry();
    reg.register({ name: "k" });
    expect(() => reg.validate(node({ x: {} }))).toThrow(FacetError);
  });

  it("validate() runs invariants", () => {
    const reg = new Registry();
    reg.register({
      name: "k",
      invariants: [
        () => {
          throw new InvariantError("boom");
        },
      ],
    });
    expect(() => reg.validate(node({}))).toThrow(InvariantError);
  });
});
