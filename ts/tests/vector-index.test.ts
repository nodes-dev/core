import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CollisionError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { type Embedder, type Vector, VectorCache, VectorIndex } from "../src/similarity.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-vec-index-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

// A deterministic embedder: maps each node's embedText to a fixed vector via a table.
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

function node(id: string, title: string, body = "") {
  return makeNode({ id, kind: id.split(":")[0], title, body });
}

describe("VectorIndex lifecycle", () => {
  it("binds the namespace even for an empty corpus", () => {
    const cache = new VectorCache(root);
    const idx = VectorIndex.build([], new TableEmbedder(new Map()), cache);
    expect(idx.namespace).toBe("test-v1");
    expect(idx.dim).toBeNull();
    expect(idx.vectors.size).toBe(0);
  });

  it("rejects a build over a corpus with a duplicate uid", () => {
    const cache = new VectorCache(root);
    const a = makeNode({ id: "topic:a", uid: "u1", kind: "topic", title: "a" });
    const b = makeNode({ id: "topic:b", uid: "u1", kind: "topic", title: "b" });
    const emb = new TableEmbedder(
      new Map([
        ["a\n\n", [1, 0]],
        ["b\n\n", [0, 1]],
      ]),
    );
    expect(() => VectorIndex.build([a, b], emb, cache)).toThrow(CollisionError);
  });

  it("builds, binds dim from the first vector, and stores normalized vectors", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const emb = new TableEmbedder(new Map([["cat\n\n", [3, 4]]])); // norm 5
    const idx = VectorIndex.build([cat], emb, cache);
    expect(idx.dim).toBe(2);
    const v = idx.vectors.get(cat.uid) as Vector;
    expect(v[0]).toBeCloseTo(0.6, 12);
    expect(v[1]).toBeCloseTo(0.8, 12);
    expect(idx.idByUid.get(cat.uid)).toBe("topic:cat");
    // raw vector is cached (un-normalized)
    expect(cache.get("test-v1", [...idx.hashByUid.values()][0])).toEqual([3, 4]);
  });

  it("prepare does not mutate index state; commit applies it", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const emb = new TableEmbedder(new Map([["cat\n\n", [1, 0]]]));
    const idx = VectorIndex.build([], emb, cache);
    const prepared = idx.prepare(cat, emb, cache);
    expect(idx.vectors.size).toBe(0); // prepare left the index untouched
    idx.commit(cat, prepared);
    expect(idx.vectors.get(cat.uid)).toEqual([1, 0]);
  });

  it("rejects a vector of a different dimension", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const dog = node("topic:dog", "dog");
    const emb = new TableEmbedder(
      new Map([
        ["cat\n\n", [1, 0]],
        ["dog\n\n", [1, 0, 0]], // wrong dim
      ]),
    );
    const idx = VectorIndex.build([cat], emb, cache);
    expect(() => idx.upsert(dog, emb, cache)).toThrow(RangeError);
  });

  it("rejects an embedder bound to a different namespace", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const idx = VectorIndex.build([], new TableEmbedder(new Map(), "ns-a"), cache);
    const other = new TableEmbedder(new Map([["cat\n\n", [1, 0]]]), "ns-b");
    expect(() => idx.prepare(cat, other, cache)).toThrow(RangeError);
  });

  it("an unchanged-content re-upsert refreshes id without re-embedding (vector=null path)", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const emb = new TableEmbedder(new Map([["cat\n\n", [1, 0]]]));
    const idx = VectorIndex.build([cat], emb, cache);
    const renamed = makeNode({ id: "topic:feline", uid: cat.uid, kind: "topic", title: "cat" });
    const prepared = idx.prepare(renamed, emb, cache);
    expect(prepared.vector).toBeNull(); // same embedText => same hash => no new vector
    idx.commit(renamed, prepared);
    expect(idx.idByUid.get(cat.uid)).toBe("topic:feline");
    expect(idx.vectors.get(cat.uid)).toEqual([1, 0]); // vector unchanged
  });

  it("remove drops all per-uid state", () => {
    const cache = new VectorCache(root);
    const cat = node("topic:cat", "cat");
    const emb = new TableEmbedder(new Map([["cat\n\n", [1, 0]]]));
    const idx = VectorIndex.build([cat], emb, cache);
    idx.remove(cat.uid);
    expect(idx.vectors.has(cat.uid)).toBe(false);
    expect(idx.idByUid.has(cat.uid)).toBe(false);
    expect(idx.hashByUid.has(cat.uid)).toBe(false);
  });
});
