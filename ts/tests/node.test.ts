import { describe, expect, it } from "vitest";
import { ValidationError } from "../src/errors.js";
import { makeNode, newUid } from "../src/node.js";

describe("node", () => {
  it("newUid is 32 lowercase hex chars (uuid4().hex parity)", () => {
    expect(newUid()).toMatch(/^[0-9a-f]{32}$/);
  });

  it("applies Pydantic-parity defaults from minimal input", () => {
    const n = makeNode({ id: "topic:x", kind: "topic", title: "X" });
    expect(n.body).toBe("");
    expect(n.metadata).toEqual({ created: null, updated: null, version: 1 });
    expect(n.relations).toEqual([]);
    expect(n.facets).toEqual({});
    expect(n.deprecatedIds).toEqual([]);
    expect(n.uid).toMatch(/^[0-9a-f]{32}$/);
  });

  it("accepts YYYY-MM-DD metadata dates as strings", () => {
    const n = makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: "2026-06-21" } });
    expect(n.metadata.created).toBe("2026-06-21");
    expect(n.metadata.updated).toBeNull();
  });

  it("rejects a malformed id with ValidationError", () => {
    expect(() => makeNode({ id: "nope", kind: "topic", title: "X" })).toThrow(ValidationError);
  });

  it("rejects an id whose kind disagrees with the kind field", () => {
    expect(() => makeNode({ id: "topic:x", kind: "gene", title: "X" })).toThrow(ValidationError);
  });

  it("rejects a non-date metadata string with ValidationError", () => {
    expect(() => makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: "yesterday" } })).toThrow(
      ValidationError,
    );
  });

  it("rejects impossible calendar dates (bad month/day, non-leap Feb 29)", () => {
    for (const bad of ["2026-99-99", "2026-13-01", "2026-02-30", "2026-00-10", "2025-02-29"]) {
      expect(() => makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: bad } })).toThrow(
        ValidationError,
      );
    }
  });

  it("accepts a valid leap day", () => {
    expect(
      makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: "2024-02-29" } }).metadata.created,
    ).toBe("2024-02-29");
  });

  it("accepts low years 0001-0099 (Python date MINYEAR parity, not JS Date 1900 offset)", () => {
    for (const ok of ["0001-01-01", "0099-12-31", "0004-02-29"]) {
      expect(makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: ok } }).metadata.created).toBe(
        ok,
      );
    }
    expect(() => makeNode({ id: "topic:x", kind: "topic", title: "X", metadata: { created: "0000-01-01" } })).toThrow(
      ValidationError,
    );
  });
});
