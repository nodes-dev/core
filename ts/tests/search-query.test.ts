import { describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { SearchIndex } from "../src/search.js";

function twoDocIndex(): SearchIndex {
  const idx = new SearchIndex();
  idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "alpha beta" }));
  idx.upsert(makeNode({ id: "topic:b", kind: "topic", title: "beta", body: "gamma" }));
  return idx;
}

describe("SearchIndex.search (BM25F)", () => {
  it("matches a hand-computed BM25F score", () => {
    // N=2, avgTitle=1.0, avgBody=1.5. Query "alpha" hits only topic:a (titleTf=1, bodyTf=1, bodyLen=2).
    // idf = ln(2); tf' = 2.0*1/1.0 + 1.0*1/1.25 = 2.8; score = ln(2)*2.5*2.8/(1.5+2.8).
    const expected = (Math.log(2.0) * 2.5 * 2.8) / 4.3;
    const hits = twoDocIndex().search("alpha");
    expect(hits.map((h) => h.id)).toEqual(["topic:a"]);
    expect(hits[0].score).toBeCloseTo(expected, 12);
    expect(hits[0].uid).not.toBe("");
    expect(hits[0].matchedTerms).toEqual(["alpha"]);
  });

  it("ranks a title match above a body match (title boost)", () => {
    // "beta" is in topic:b's TITLE and topic:a's BODY -> title boost ranks b first.
    expect(
      twoDocIndex()
        .search("beta")
        .map((h) => h.id),
    ).toEqual(["topic:b", "topic:a"]);
  });

  it("breaks rounded-score ties by id ascending", () => {
    const idx = new SearchIndex();
    idx.upsert(makeNode({ id: "topic:b", kind: "topic", title: "x", body: "z" }));
    idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "x", body: "z" }));
    expect(idx.search("x").map((h) => h.id)).toEqual(["topic:a", "topic:b"]);
  });

  it("matchedTerms is the sorted deduped subset present in the doc", () => {
    const idx = new SearchIndex();
    idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "gamma" }));
    const hits = idx.search("gamma alpha zeta"); // zeta absent; alpha repeated below
    expect(hits[0].matchedTerms).toEqual(["alpha", "gamma"]);
  });

  it("orders query terms by Unicode code point, not UTF-16 code unit", () => {
    // Title 'ａ' U+FF41 (65345), body '𝟙' U+1D7D9 (120793). Both NFC- and lowercase-stable.
    // Code-point order -> ["ａ","𝟙"]. Default UTF-16 sort would compare 0xFF41 (65345) vs the
    // surrogate lead 0xD835 (55349) and WRONGLY yield ["𝟙","ａ"]. This pins the comparator.
    const idx = new SearchIndex();
    idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "ａ", body: "\u{1D7D9}" }));
    const hits = idx.search("\u{1D7D9} ａ");
    expect(hits[0].matchedTerms).toEqual(["ａ", "\u{1D7D9}"]);
  });

  it("returns [] for empty, stop-word-only, and all-absent queries", () => {
    const idx = new SearchIndex();
    idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "the cat" }));
    expect(idx.search("")).toEqual([]);
    expect(idx.search("   ")).toEqual([]);
    expect(idx.search("the")).toEqual([]); // stop word only
    expect(idx.search("zeta")).toEqual([]); // term absent
  });

  it("honors limit and treats undefined as unbounded", () => {
    const idx = new SearchIndex();
    for (const slug of ["a", "b", "c"]) {
      idx.upsert(makeNode({ id: `topic:${slug}`, kind: "topic", title: "alpha", body: "alpha" }));
    }
    expect(idx.search("alpha").length).toBe(3);
    expect(idx.search("alpha", 2).length).toBe(2);
    expect(idx.search("alpha", undefined).length).toBe(3);
  });

  it("rejects a non-positive or non-integer limit with RangeError", () => {
    const idx = new SearchIndex();
    idx.upsert(makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "" }));
    for (const bad of [0, -1, 1.5]) {
      expect(() => idx.search("alpha", bad)).toThrow(RangeError);
    }
  });
});
