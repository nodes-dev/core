import { describe, expect, it } from "vitest";
import { scoreKey } from "../src/ranking.js";

describe("scoreKey", () => {
  it("rounds half-up to 6 decimal places", () => {
    expect(scoreKey(0.1234565)).toBe(0.123457); // .5 at 7th place rounds up
    expect(scoreKey(0.1234564)).toBe(0.123456);
    expect(scoreKey(1)).toBe(1);
    expect(scoreKey(0)).toBe(0);
  });

  it("is correct on negative scores (Math.floor half-up, parity with Python)", () => {
    // cosine is in [-1, 1]; floor-based half-up must behave like Python's on negatives
    expect(scoreKey(-0.9999995)).toBe(-0.999999); // floor(-999999.5+0.5)=floor(-999999)= -999999
    expect(scoreKey(-0.5)).toBe(-0.5);
  });
});
