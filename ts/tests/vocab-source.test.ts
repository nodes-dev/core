import { describe, expect, it } from "vitest";
import { FacetError, InvariantError } from "../src/errors.js";
import { type Node, makeNode } from "../src/node.js";
import { SOURCE, type Source, requireIdentifiableSource, sourceOf } from "../src/vocab/source.js";

function paper(source: Record<string, unknown> | null): Node {
  if (source === null) {
    return makeNode({ id: "paper:x", kind: "paper", title: "X" });
  }
  return makeNode({ id: "paper:x", kind: "paper", title: "X", facets: { [SOURCE]: source } });
}

describe("Source facet", () => {
  it("parses defaults from an empty payload", () => {
    const s: Source = sourceOf(paper({}));
    expect(s.authors).toEqual([]);
    expect(s.year).toBeNull();
    expect(s.container).toBeNull();
    expect(s.identifier).toBeNull();
    expect(s.url).toBeNull();
  });

  it("raises FacetError when the source facet is missing", () => {
    expect(() => sourceOf(paper(null))).toThrow(FacetError);
  });

  it("raises FacetError on an unknown key (typo)", () => {
    expect(() => sourceOf(paper({ identifer: "10.1/x" }))).toThrow(FacetError);
  });

  it("raises FacetError on a wrong-typed field", () => {
    expect(() => sourceOf(paper({ year: "soon" }))).toThrow(FacetError);
  });

  it("never leaks a raw ZodError", () => {
    try {
      sourceOf(paper({ year: "soon" }));
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(FacetError);
      expect((e as Error).constructor.name).toBe("FacetError");
    }
  });

  it("rejects an empty source via requireIdentifiableSource", () => {
    expect(() => requireIdentifiableSource(paper({}))).toThrow(InvariantError);
  });

  it("accepts a source with one identifying field", () => {
    requireIdentifiableSource(paper({ year: 2026 })); // no throw
  });

  it("normalizes quoted numeric years like Python/Pydantic", () => {
    expect(sourceOf(paper({ year: "2026" })).year).toBe(2026);
    expect(sourceOf(paper({ year: 2026.0 })).year).toBe(2026);
  });

  it("rejects the year coercion boundary cases z.coerce.number() would wrongly accept", () => {
    // Pins the reason the schema avoids z.coerce.number(): "" must NOT become 0, and a
    // non-integral float must fail — matching Pydantic's int|None rejects.
    expect(() => sourceOf(paper({ year: "" }))).toThrow(FacetError);
    expect(() => sourceOf(paper({ year: 2026.5 }))).toThrow(FacetError);
  });

  it("roundtrips a populated source through the facet", () => {
    const s = sourceOf(paper({ authors: ["A. Author"], year: 2026, identifier: "10.1/x" }));
    expect(s.authors).toEqual(["A. Author"]);
    expect(s.year).toBe(2026);
    expect(s.identifier).toBe("10.1/x");
  });
});
