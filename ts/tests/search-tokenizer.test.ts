import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { scoreKey } from "../src/ranking.js";
import { STOP_WORDS, codepointSorted, tokenize } from "../src/search.js";

const ORACLE = fileURLToPath(new URL("../../fixtures/search.tokenizer.json", import.meta.url));

describe("tokenize", () => {
  it.each([
    ["", []],
    ["   \t\n ", []],
    ["The Quick Brown Fox", ["quick", "brown", "fox"]], // 'the' is a stop word; lowercased
    ["the THE The", []], // all stop words
    ["well-known", ["well", "known"]], // hyphen separates
    ["state_of_art", ["state", "art"]], // underscore separates; 'of' is a stop word
    ["don't", ["don", "t"]], // apostrophe separates
    ["3.14 and 2", ["3", "14", "2"]], // '.' separates; 'and' is a stop word
    ["café", ["café"]], // composed (U+00E9)
    ["café", ["café"]], // decomposed e + U+0301 combining acute -> NFC -> café
    ["Hello МИР", ["hello", "мир"]], // Cyrillic, lowercased
    ["hello 世界", ["hello", "世界"]], // CJK run is one token
    ["data\u{1D7D9}point", ["data\u{1D7D9}point"]], // non-BMP digit stays inside one token
  ])("tokenizes %j", (text, expected) => {
    expect(tokenize(text as string)).toEqual(expected);
  });

  it("keeps duplicate tokens in document order (term frequency is meaningful)", () => {
    expect(tokenize("alpha beta alpha")).toEqual(["alpha", "beta", "alpha"]);
  });
});

describe("STOP_WORDS", () => {
  it("has exactly 33 words including the and with", () => {
    expect(STOP_WORDS.size).toBe(33);
    expect(STOP_WORDS.has("the")).toBe(true);
    expect(STOP_WORDS.has("with")).toBe(true);
  });
});

describe("scoreKey", () => {
  it("rounds half-up to 6 decimal places", () => {
    // Inputs kept clear of the exact .5 boundary so float representation can't flip them.
    expect(scoreKey(1.2345674)).toBe(1.234567); // rounds down
    expect(scoreKey(1.2345678)).toBe(1.234568); // rounds up
    expect(scoreKey(0)).toBe(0);
  });
});

describe("codepointSorted", () => {
  it("sorts by Unicode code point, not UTF-16 code unit", () => {
    // 'ａ' U+FF41 (65345) < '𝟙' U+1D7D9 (120793) by code point, so 'ａ' must sort first.
    // Default Array.sort() compares UTF-16 units: 0xFF41 (65345) > 0xD835 (55349, '𝟙' lead
    // surrogate) would WRONGLY place '𝟙' first. Both tokens are NFC- and lowercase-stable.
    expect(codepointSorted(["\u{1D7D9}", "ａ"])).toEqual(["ａ", "\u{1D7D9}"]);
  });

  it("dedup is the caller's job — it sorts whatever it is given", () => {
    expect(codepointSorted(new Set(["b", "a", "b"]))).toEqual(["a", "b"]);
  });
});

describe("tokenizer oracle (cross-language freeze)", () => {
  it("reproduces every committed case exactly", () => {
    const cases = JSON.parse(readFileSync(ORACLE, "utf-8")) as { input: string; tokens: string[] }[];
    expect(cases.length).toBeGreaterThan(0);
    for (const c of cases) {
      expect(tokenize(c.input)).toEqual(c.tokens);
    }
  });
});
