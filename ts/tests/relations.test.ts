import { describe, expect, it } from "vitest";
import { RefError } from "../src/errors.js";
import { RELATES_TO, fromSerialized, relatesTo, tagToRelation, toSerialized } from "../src/relations.js";

describe("relations", () => {
  it("relatesTo builds a normalized relatesTo edge", () => {
    expect(relatesTo("a:1", "b:2")).toEqual({
      source: "a:1",
      predicate: RELATES_TO,
      target: "b:2",
      directed: true,
      weight: null,
      attrs: {},
    });
  });

  it("fromSerialized fills source from the container when absent", () => {
    const r = fromSerialized({ predicate: "cites", target: "p:2" }, "p:1");
    expect(r.source).toBe("p:1");
    expect(r.directed).toBe(true);
  });

  it("fromSerialized keeps an explicit source", () => {
    expect(fromSerialized({ source: "x:9", predicate: "cites", target: "p:2" }, "p:1").source).toBe("x:9");
  });

  it("toSerialized omits source==container, directed=true, null weight, empty attrs", () => {
    expect(toSerialized(relatesTo("p:1", "p:2"), "p:1")).toEqual({ predicate: RELATES_TO, target: "p:2" });
  });

  it("toSerialized keeps non-default fields", () => {
    const r = fromSerialized(
      { source: "x:1", predicate: "cites", target: "p:2", directed: false, weight: 0.5, attrs: { k: 1 } },
      "p:1",
    );
    expect(toSerialized(r, "p:1")).toEqual({
      source: "x:1",
      predicate: "cites",
      target: "p:2",
      directed: false,
      weight: 0.5,
      attrs: { k: 1 },
    });
  });

  it("tagToRelation resolves #alias case-insensitively", () => {
    const r = tagToRelation("a:1", "#Polycomb", { polycomb: "topic:polycomb" });
    expect(r.target).toBe("topic:polycomb");
  });

  it("tagToRelation throws RefError on an unknown tag", () => {
    expect(() => tagToRelation("a:1", "#nope", {})).toThrow(RefError);
  });
});
