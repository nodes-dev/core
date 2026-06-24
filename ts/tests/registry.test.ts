import { describe, expect, it } from "vitest";
import { FacetError, InvariantError, UnknownKindError, ValidationError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";

function node(facets: Record<string, Record<string, unknown>>) {
  return makeNode({ id: "k:1", kind: "k", title: "T", facets });
}

function knode(kind: string, facets: Record<string, Record<string, unknown>>) {
  return makeNode({ id: `${kind}:1`, kind, title: "T", facets });
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

describe("Registry — shapes", () => {
  it("registerShape rejects a duplicate shape name", () => {
    const reg = new Registry();
    reg.registerShape({ name: "graph", requiredFacets: new Set(["membership"]) });
    expect(() => reg.registerShape({ name: "graph" })).toThrow(ValidationError);
  });

  it("register rejects a duplicate kind name", () => {
    const reg = new Registry();
    reg.register({ name: "topic" });
    expect(() => reg.register({ name: "topic" })).toThrow(ValidationError);
  });

  it("register rejects a kind adopting an unknown shape", () => {
    const reg = new Registry();
    expect(() => reg.register({ name: "mindmap", shape: "graph" })).toThrow(UnknownKindError);
  });

  it("a shape and a kind may share a name (separate namespaces)", () => {
    const reg = new Registry();
    reg.registerShape({ name: "graph", requiredFacets: new Set(["membership"]) });
    reg.register({ name: "graph", shape: "graph" });
    expect(reg.isShape("graph")).toBe(true);
    expect(reg.isRegistered("graph")).toBe(true);
  });

  it("validate composes shape + kind required facets", () => {
    const reg = new Registry();
    reg.registerShape({ name: "graph", requiredFacets: new Set(["membership"]) });
    reg.register({ name: "mindmap", shape: "graph", requiredFacets: new Set(["scene"]) });
    expect(() => reg.validate(knode("mindmap", { membership: { members: [] }, scene: { x: 1 } }))).not.toThrow();
    expect(() => reg.validate(knode("mindmap", { membership: { members: [] } }))).toThrow(FacetError);
  });

  it("validate runs shape invariants before kind invariants", () => {
    const order: string[] = [];
    const reg = new Registry();
    reg.registerShape({
      name: "graph",
      requiredFacets: new Set(["membership"]),
      invariants: [() => void order.push("shape")],
    });
    reg.register({ name: "mindmap", shape: "graph", invariants: [() => void order.push("kind")] });
    reg.validate(knode("mindmap", { membership: { members: [] } }));
    expect(order).toEqual(["shape", "kind"]);
  });

  it("validate permits a shape's optional facets", () => {
    const reg = new Registry();
    reg.registerShape({
      name: "graph",
      requiredFacets: new Set(["membership"]),
      optionalFacets: new Set(["style"]),
    });
    reg.register({ name: "mindmap", shape: "graph" });
    expect(() =>
      reg.validate(knode("mindmap", { membership: { members: [] }, style: { color: "red" } })),
    ).not.toThrow();
  });
});
