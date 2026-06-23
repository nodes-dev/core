import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { type Embedder, type Vector, VectorCache, VectorIndex } from "../src/similarity.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-vec-snap-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

class TableEmbedder implements Embedder {
  readonly cacheNamespace = "vec-v1";
  embed(texts: string[]): Vector[] {
    return texts.map((t) => (t.includes("cat") ? [3, 4] : [0, 5]));
  }
}

function seed(): VectorIndex {
  const idx = VectorIndex.build(
    [
      makeNode({ id: "topic:cat", kind: "topic", title: "cat" }),
      makeNode({ id: "topic:dog", kind: "topic", title: "dog" }),
    ],
    new TableEmbedder(),
    new VectorCache(root),
  );
  return idx;
}

describe("VectorIndex snapshot", () => {
  it("round-trips vectors, ids, hashes, dim and namespace", () => {
    const idx = seed();
    const restored = VectorIndex.fromDict(idx.toDict());
    expect(restored.namespace).toBe("vec-v1");
    expect(restored.dim).toBe(2);
    expect(restored.queryVector([3, 4]).map((h) => h.id)).toEqual(idx.queryVector([3, 4]).map((h) => h.id));
    expect([...restored.hashByUid]).toEqual([...idx.hashByUid]);
  });

  it("empty embedder index round-trips with dim null", () => {
    const idx = new VectorIndex();
    idx.namespace = "vec-v1";
    const d = idx.toDict();
    expect(d.dim).toBeNull();
    const restored = VectorIndex.fromDict(d);
    expect(restored.dim).toBeNull();
    expect(restored.namespace).toBe("vec-v1");
    expect(restored.vectors.size).toBe(0);
  });

  it("rejects mismatched uid maps", () => {
    const d = seed().toDict();
    delete d.hashByUid[Object.keys(d.hashByUid)[0]];
    expect(() => VectorIndex.fromDict(d)).toThrow();
  });

  it("rejects a vector whose length != dim", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.vectors)[0];
    d.vectors[uid] = [1];
    expect(() => VectorIndex.fromDict(d)).toThrow();
  });

  it("rejects a non-normalized stored vector", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.vectors)[0];
    d.vectors[uid] = [3, 4]; // norm 5, not 1
    expect(() => VectorIndex.fromDict(d)).toThrow();
  });

  it("rejects non-null dim when there are no vectors", () => {
    const d = new VectorIndex().toDict();
    (d as { dim: number | null }).dim = 4;
    expect(() => VectorIndex.fromDict(d)).toThrow();
  });

  it("rejects an invalid hashByUid value", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.hashByUid)[0];
    d.hashByUid[uid] = "not-a-hash";
    expect(() => VectorIndex.fromDict(d)).toThrow();
  });
});
