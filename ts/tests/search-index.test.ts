import { describe, expect, it } from "vitest";
import { CollisionError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { SearchIndex } from "../src/search.js";

function norm(idx: SearchIndex): unknown {
  const postings: Record<string, [string, [number, number]][]> = {};
  for (const [term, docs] of idx.postings) {
    postings[term] = [...docs.entries()].sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  }
  return {
    postings,
    lengths: [...idx.lengths.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)),
    idByUid: [...idx.idByUid.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)),
    n: idx.n,
    totals: [idx.totalTitle, idx.totalBody],
  };
}

describe("SearchIndex state", () => {
  it("upsert records per-field term frequencies and lengths", () => {
    const idx = new SearchIndex();
    const n = makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "alpha alpha beta" });
    idx.upsert(n);
    expect(idx.postings.get("alpha")?.get(n.uid)).toEqual([1, 2]); // 1 in title, 2 in body
    expect(idx.postings.get("beta")?.get(n.uid)).toEqual([0, 1]);
    expect(idx.lengths.get(n.uid)).toEqual([1, 3]);
    expect(idx.idByUid.get(n.uid)).toBe("topic:a");
    expect(idx.n).toBe(1);
  });

  it("upsert replaces stale postings, it does not duplicate", () => {
    const idx = new SearchIndex();
    const n = makeNode({ id: "topic:a", kind: "topic", title: "", body: "alpha alpha" });
    idx.upsert(n);
    expect(idx.postings.get("alpha")?.get(n.uid)).toEqual([0, 2]);
    n.body = "beta";
    idx.upsert(n);
    expect(idx.postings.has("alpha")).toBe(false); // stale postings dropped
    expect(idx.postings.get("beta")?.get(n.uid)).toEqual([0, 1]);
    expect(idx.lengths.get(n.uid)).toEqual([0, 1]);
    expect(idx.n).toBe(1);
  });

  it("remove drops everything and totals, and is a no-op when absent", () => {
    const idx = new SearchIndex();
    const n = makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "beta" });
    idx.upsert(n);
    idx.remove(n.uid);
    expect(idx.n).toBe(0);
    expect(idx.postings.size).toBe(0);
    expect(idx.lengths.size).toBe(0);
    expect(idx.idByUid.size).toBe(0);
    expect([idx.totalTitle, idx.totalBody]).toEqual([0, 0]);
    idx.remove("not-present"); // no throw, no change
    expect(idx.n).toBe(0);
  });

  it("empty text still counts as a document slot", () => {
    const idx = new SearchIndex();
    const n = makeNode({ id: "topic:a", kind: "topic", title: "", body: "" });
    idx.upsert(n);
    expect(idx.n).toBe(1);
    expect(idx.lengths.get(n.uid)).toEqual([0, 0]);
    expect(idx.postings.size).toBe(0);
  });

  it("build rejects a duplicate uid with CollisionError", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A", uid: "dup" });
    const b = makeNode({ id: "topic:b", kind: "topic", title: "B", uid: "dup" });
    expect(() => SearchIndex.build([a, b])).toThrow(CollisionError);
  });

  it("incremental mutation matches a fresh rebuild", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "Alpha", body: "alpha beta" });
    const b = makeNode({ id: "topic:b", kind: "topic", title: "Beta", body: "gamma delta" });
    const c = makeNode({ id: "topic:c", kind: "topic", title: "C", body: "alpha" });
    const idx = new SearchIndex();
    idx.upsert(a);
    idx.upsert(b);
    a.body = "alpha gamma";
    idx.upsert(a); // overwrite a
    idx.remove(b.uid); // drop b
    idx.upsert(c);
    expect(norm(idx)).toEqual(norm(SearchIndex.build([a, c])));
  });
});
