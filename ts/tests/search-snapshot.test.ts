import { describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { SearchIndex } from "../src/search.js";

function seed(): SearchIndex {
  const idx = new SearchIndex();
  idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "alpha gamma", body: "gamma delta" }));
  idx.upsert(makeNode({ id: "topic:b", kind: "topic", title: "beta", body: "gamma epsilon" }));
  return idx;
}

describe("SearchIndex snapshot", () => {
  it("round-trips and preserves query results", () => {
    const idx = seed();
    const restored = SearchIndex.fromDict(idx.toDict());
    expect(restored.search("gamma").map((h) => [h.id, h.uid, h.score])).toEqual(
      idx.search("gamma").map((h) => [h.id, h.uid, h.score]),
    );
    expect(restored.search("delta").map((h) => h.id)).toEqual(idx.search("delta").map((h) => h.id));
  });

  it("recomputes the corpus totals from lengths (no stored drift)", () => {
    const idx = seed();
    const restored = SearchIndex.fromDict(idx.toDict());
    expect(restored.totalTitle).toBe(idx.totalTitle);
    expect(restored.totalBody).toBe(idx.totalBody);
    expect(restored.n).toBe(idx.n);
  });

  it("empty index round-trips", () => {
    const restored = SearchIndex.fromDict(new SearchIndex().toDict());
    expect(restored.n).toBe(0);
    expect(restored.search("anything")).toEqual([]);
  });

  it("rejects lengths/idByUid uid-set divergence", () => {
    const d = seed().toDict();
    delete d.idByUid[Object.keys(d.idByUid)[0]];
    expect(() => SearchIndex.fromDict(d)).toThrow();
  });

  it("rejects a posting uid absent from lengths", () => {
    const d = seed().toDict();
    const term = Object.keys(d.postings)[0];
    d.postings[term].ghost = [1, 0];
    expect(() => SearchIndex.fromDict(d)).toThrow();
  });

  it("rejects an empty posting bucket", () => {
    const d = seed().toDict();
    d.postings.ghost = {};
    expect(() => SearchIndex.fromDict(d)).toThrow();
  });

  it("rejects a zero posting tf pair", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.lengths)[0];
    d.postings.ghost = { [uid]: [0, 0] };
    expect(() => SearchIndex.fromDict(d)).toThrow();
  });

  it("rejects a posting tf greater than the field length", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.lengths)[0];
    const [titleLen] = d.lengths[uid];
    d.postings.ghost = { [uid]: [titleLen + 1, 0] };
    expect(() => SearchIndex.fromDict(d)).toThrow();
  });

  it("rejects a non-integer / negative length pair", () => {
    const d = seed().toDict();
    const uid = Object.keys(d.lengths)[0];
    d.lengths[uid] = [-1, 0];
    expect(() => SearchIndex.fromDict(d)).toThrow();
    const d2 = seed().toDict();
    const uid2 = Object.keys(d2.lengths)[0];
    (d2.lengths[uid2] as unknown[]) = [1.5, 0];
    expect(() => SearchIndex.fromDict(d2)).toThrow();
  });
});
