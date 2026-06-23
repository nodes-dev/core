import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { EmbedderRequiredError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import type { Embedder, Vector } from "../src/similarity.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-sim-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

class TableEmbedder implements Embedder {
  readonly cacheNamespace = "test-v1";
  private table: Map<string, Vector>;
  constructor(table: Map<string, Vector>) {
    this.table = table;
  }
  embed(texts: string[]): Vector[] {
    return texts.map((t) => {
      const v = this.table.get(t);
      if (v === undefined) throw new Error(`no vector for ${JSON.stringify(t)}`);
      return v;
    });
  }
}

const TABLE = new Map<string, Vector>([
  ["cat\n\n", [1, 0.1, 0, 0]],
  ["dog\n\n", [0.9, 0.2, 0, 0]],
  ["car\n\n", [0, 0, 1, 0.1]],
  ["kitten\n\n", [1, 0.1, 0, 0]], // same vector as cat (content-addressed cache shares it)
]);

describe("Corpus similarity (opt-in)", () => {
  it("raises EmbedderRequiredError when no embedder was supplied (before ref resolution)", () => {
    const c = new Corpus(root);
    expect(() => c.similar("topic:anything")).toThrow(EmbedderRequiredError);
    expect(() => c.queryVector([1, 0, 0, 0])).toThrow(EmbedderRequiredError);
    expect(() => c.similarText("cat")).toThrow(EmbedderRequiredError);
  });

  it("similar over an embedder-backed corpus ranks by cosine and excludes self", () => {
    const c = new Corpus(root, undefined, new TableEmbedder(TABLE));
    c.add(makeNode({ id: "topic:cat", kind: "topic", title: "cat" }));
    c.add(makeNode({ id: "topic:dog", kind: "topic", title: "dog" }));
    c.add(makeNode({ id: "topic:car", kind: "topic", title: "car" }));
    expect(c.similar("topic:cat").map((h) => h.id)).toEqual(["topic:dog", "topic:car"]);
    expect(c.queryVector([0.95, 0.15, 0, 0]).map((h) => h.id)).toEqual(["topic:cat", "topic:dog", "topic:car"]);
    expect(c.similarText("cat\n\n").map((h) => h.id)).toEqual(["topic:cat", "topic:dog", "topic:car"]);
  });

  it("delete removes a node from the vector index", () => {
    const c = new Corpus(root, undefined, new TableEmbedder(TABLE));
    c.add(makeNode({ id: "topic:cat", kind: "topic", title: "cat" }));
    c.add(makeNode({ id: "topic:dog", kind: "topic", title: "dog" }));
    c.delete("topic:dog");
    expect(c.similar("topic:cat")).toEqual([]); // dog was the only other vector
  });

  it("a failing embed leaves the corpus completely unmutated (fail before disk write)", () => {
    const c = new Corpus(root, undefined, new TableEmbedder(TABLE));
    // "ghost\n\n" is absent from the table -> embed throws inside add's prepare, before writeFile
    expect(() => c.add(makeNode({ id: "topic:ghost", kind: "topic", title: "ghost" }))).toThrow();
    expect(c.all()).toEqual([]); // no file written
    expect(() => c.get("topic:ghost")).toThrow(); // not in the structural index either
  });

  it("rename carries the new id into the vector index (no re-embed; same content)", () => {
    const c = new Corpus(root, undefined, new TableEmbedder(TABLE));
    c.add(makeNode({ id: "topic:cat", kind: "topic", title: "cat" }));
    c.add(makeNode({ id: "topic:dog", kind: "topic", title: "dog" }));
    c.rename("topic:cat", "topic:feline");
    // dog's nearest neighbor (cat) is now reported under the new id, and the old id is gone
    const hits = c.similar("topic:dog");
    expect(hits[0].id).toBe("topic:feline");
    expect(hits.map((h) => h.id)).toContain("topic:feline");
    expect(hits.map((h) => h.id)).not.toContain("topic:cat");
  });
});
