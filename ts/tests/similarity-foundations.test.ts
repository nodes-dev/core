import { describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { embedText, textHash, validateNamespace, validateTextHash } from "../src/similarity.js";

const HEX64 = "a".repeat(64);

describe("embedText", () => {
  it("joins title and body with one blank line", () => {
    const node = makeNode({ id: "topic:x", kind: "topic", title: "Cats", body: "feline pets" });
    expect(embedText(node)).toBe("Cats\n\nfeline pets");
  });

  it("handles an empty body (title, blank line, empty string)", () => {
    const node = makeNode({ id: "topic:x", kind: "topic", title: "Cats" });
    expect(embedText(node)).toBe("Cats\n\n");
  });
});

describe("textHash", () => {
  it("is the lowercase sha256 hex digest of the utf-8 text", () => {
    // sha256("") is well-known
    expect(textHash("")).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    expect(textHash("abc")).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe("validateNamespace", () => {
  it("accepts safe single segments", () => {
    expect(() => validateNamespace("fixture-v1")).not.toThrow();
    expect(() => validateNamespace("model.v2_0")).not.toThrow();
  });

  it("rejects empty, dot, dot-dot, separators, and trailing newline", () => {
    for (const bad of ["", ".", "..", "a/b", "a\\b", "a b", "fixture-v1\n"]) {
      expect(() => validateNamespace(bad)).toThrow(TypeError);
    }
  });
});

describe("validateTextHash", () => {
  it("accepts exactly 64 lowercase hex chars", () => {
    expect(() => validateTextHash(HEX64)).not.toThrow();
  });

  it("rejects wrong length, uppercase, non-hex, and trailing newline", () => {
    for (const bad of ["a".repeat(63), "a".repeat(65), "A".repeat(64), `${"a".repeat(63)}g`, `${HEX64}\n`]) {
      expect(() => validateTextHash(bad)).toThrow(TypeError);
    }
  });
});
