import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { type Embedder, type Vector, VectorCache, VectorIndex } from "../src/similarity.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-vec-query-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

class TableEmbedder implements Embedder {
  readonly cacheNamespace: string;
  private table: Map<string, Vector>;
  constructor(table: Map<string, Vector>, namespace = "test-v1") {
    this.table = table;
    this.cacheNamespace = namespace;
  }
  embed(texts: string[]): Vector[] {
    return texts.map((t) => {
      const v = this.table.get(t);
      if (v === undefined) throw new Error(`no vector for ${JSON.stringify(t)}`);
      return v;
    });
  }
}

function build(root: string) {
  const cache = new VectorCache(root);
  const cat = makeNode({ id: "topic:cat", uid: "ucat", kind: "topic", title: "cat" });
  const dog = makeNode({ id: "topic:dog", uid: "udog", kind: "topic", title: "dog" });
  const car = makeNode({ id: "topic:car", uid: "ucar", kind: "topic", title: "car" });
  const emb = new TableEmbedder(
    new Map([
      ["cat\n\n", [1, 0.1, 0, 0]],
      ["dog\n\n", [0.9, 0.2, 0, 0]],
      ["car\n\n", [0, 0, 1, 0.1]],
    ]),
  );
  return { idx: VectorIndex.build([cat, dog, car], emb, cache), emb };
}

describe("VectorIndex queries", () => {
  it("similar(uid) excludes the node itself and ranks by cosine then id", () => {
    const { idx } = build(root);
    const hits = idx.similar("ucat");
    expect(hits.map((h) => h.id)).toEqual(["topic:dog", "topic:car"]); // dog closest, car orthogonal
    expect(hits.every((h) => h.uid !== "ucat")).toBe(true);
    expect(hits[0].score).toBeGreaterThan(hits[1].score);
  });

  it("similar respects k", () => {
    const { idx } = build(root);
    expect(idx.similar("ucat", 1).map((h) => h.id)).toEqual(["topic:dog"]);
  });

  it("similar throws an internal uid lookup error on an unknown uid", () => {
    const { idx } = build(root);
    expect(() => idx.similar("nope")).toThrow(Error);
  });

  it("queryVector ranks all nodes (no exclusion) and validates k", () => {
    const { idx } = build(root);
    const hits = idx.queryVector([0.95, 0.15, 0, 0]);
    expect(hits.map((h) => h.id)).toEqual(["topic:cat", "topic:dog", "topic:car"]);
    expect(() => idx.queryVector([1, 0, 0, 0], 0)).toThrow(RangeError);
    expect(() => idx.queryVector([1, 0, 0, 0], 1.5)).toThrow(RangeError);
  });

  it("queryVector rejects a wrong-dimension or zero-norm query", () => {
    const { idx } = build(root);
    expect(() => idx.queryVector([1, 0])).toThrow(RangeError); // dim mismatch
    expect(() => idx.queryVector([0, 0, 0, 0])).toThrow(RangeError); // zero norm
  });

  it("similarText embeds via the live embedder and enforces the namespace", () => {
    const { idx, emb } = build(root);
    expect(idx.similarText("cat\n\n", emb).map((h) => h.id)).toEqual(["topic:cat", "topic:dog", "topic:car"]);
    const wrongNs = new TableEmbedder(new Map([["x", [1, 0, 0, 0]]]), "other");
    expect(() => idx.similarText("x", wrongNs)).toThrow(RangeError);
  });

  it("an empty index still validates the query vector", () => {
    const idx = VectorIndex.build([], new TableEmbedder(new Map()), new VectorCache(root));
    expect(idx.queryVector([1, 2, 3])).toEqual([]); // valid query, no candidates
    expect(() => idx.queryVector([0, 0])).toThrow(RangeError); // zero norm still rejected
  });
});
