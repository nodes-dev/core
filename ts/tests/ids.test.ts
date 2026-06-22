import { describe, expect, it } from "vitest";
import { IdError } from "../src/errors.js";
import { NodeId } from "../src/ids.js";

describe("NodeId.parse", () => {
  it("parses kind:slug", () => {
    const id = NodeId.parse("topic:polycomb");
    expect(id.kind).toBe("topic");
    expect(id.slug).toBe("polycomb");
    expect(id.toString()).toBe("topic:polycomb");
  });
  it("keeps colons in the slug (split on first only)", () => {
    expect(NodeId.parse("gene:HGNC:7296").slug).toBe("HGNC:7296");
  });
  it("throws IdError without a colon", () => {
    expect(() => NodeId.parse("nope")).toThrow(IdError);
  });
  it("throws IdError on a bad kind", () => {
    expect(() => NodeId.parse("Topic:x")).toThrow(IdError);
  });
  it("throws IdError on a bad slug", () => {
    expect(() => NodeId.parse("topic:-bad")).toThrow(IdError);
  });
  it("validates kind and slug independently", () => {
    expect(NodeId.isValidKind("bio-axes")).toBe(true);
    expect(NodeId.isValidKind("Bad")).toBe(false);
    expect(NodeId.isValidSlug("A1:_.-")).toBe(true);
    expect(NodeId.isValidSlug("-bad")).toBe(false);
  });
});
