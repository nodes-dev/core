import { describe, expect, it } from "vitest";
import { ValidationError } from "../src/errors.js";
import { nodeFromMarkdown, nodeToMarkdown, splitFrontmatter } from "../src/frontmatter.js";
import { makeNode } from "../src/node.js";

const DOC = "---\nid: topic:x\nuid: abc\nkind: topic\ntitle: X\n---\nhello body\n";

describe("frontmatter", () => {
  it("splits the frontmatter block from the body", () => {
    const [fm, body] = splitFrontmatter(DOC);
    expect(fm.id).toBe("topic:x");
    expect(body).toBe("hello body\n");
  });

  it("returns empty frontmatter when no block is present", () => {
    expect(splitFrontmatter("no frontmatter here")).toEqual([{}, "no frontmatter here"]);
  });

  it("throws ValidationError on malformed YAML in the block", () => {
    expect(() => splitFrontmatter("---\nid: : :\n  bad\n---\nb\n")).toThrow(ValidationError);
  });

  it("throws ValidationError when a required field is missing", () => {
    expect(() => nodeFromMarkdown("---\nid: topic:x\nkind: topic\ntitle: X\n---\nb\n")).toThrow(ValidationError);
  });

  it("expands related: sugar and typed relations: in document order", () => {
    const n = nodeFromMarkdown(
      "---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelated:\n- b:2\nrelations:\n- predicate: cites\n  target: c:3\n---\nx\n",
    );
    expect(n.relations.map((r) => [r.predicate, r.target])).toEqual([
      ["relatesTo", "b:2"],
      ["cites", "c:3"],
    ]);
  });

  it("round-trips date metadata semantically", () => {
    const n = makeNode({
      id: "a:1",
      kind: "a",
      title: "A",
      metadata: { created: "2026-06-21", updated: null, version: 3 },
    });
    const back = nodeFromMarkdown(nodeToMarkdown(n));
    expect(back.metadata).toEqual({ created: "2026-06-21", updated: null, version: 3 });
  });

  it("wraps a malformed typed relation as ValidationError (no raw ZodError)", () => {
    // relations: entry missing the required target
    expect(() =>
      nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelations:\n- predicate: cites\n---\nx\n"),
    ).toThrow(ValidationError);
  });

  it("wraps a non-string related entry as ValidationError", () => {
    expect(() => nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelated:\n- 123\n---\nx\n")).toThrow(
      ValidationError,
    );
  });

  it("rejects a non-list 'related' (scalar or mapping) as ValidationError, never a raw TypeError", () => {
    // scalar
    expect(() => nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelated: 123\n---\nx\n")).toThrow(
      ValidationError,
    );
    // mapping
    expect(() => nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelated:\n  b: c\n---\nx\n")).toThrow(
      ValidationError,
    );
  });

  it("rejects a non-list 'relations' (scalar or mapping) as ValidationError, never a raw TypeError", () => {
    // scalar
    expect(() => nodeFromMarkdown("---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelations: 7\n---\nx\n")).toThrow(
      ValidationError,
    );
    // a single mapping where a list was expected
    expect(() =>
      nodeFromMarkdown(
        "---\nid: a:1\nuid: u\nkind: a\ntitle: A\nrelations:\n  predicate: cites\n  target: c:3\n---\nx\n",
      ),
    ).toThrow(ValidationError);
  });
});
