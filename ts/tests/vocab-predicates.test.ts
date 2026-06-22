import { describe, expect, it } from "vitest";
import type { Relation } from "../src/relations.js";
import { ABOUT, ANSWERS, ASKS, CITES, REFINES, about, answers, asks, cites, refines } from "../src/vocab/predicates.js";

describe("vocab predicates", () => {
  it("exposes the canonical constant values", () => {
    expect(ABOUT).toBe("about");
    expect(CITES).toBe("cites");
    expect(ANSWERS).toBe("answers");
    expect(ASKS).toBe("asks");
    expect(REFINES).toBe("refines");
  });

  it("helper constructors build directed relations with the right predicate", () => {
    const cases: [(s: string, t: string) => Relation, string][] = [
      [about, ABOUT],
      [cites, CITES],
      [answers, ANSWERS],
      [asks, ASKS],
      [refines, REFINES],
    ];
    for (const [fn, predicate] of cases) {
      const rel = fn("note:a", "topic:b");
      expect(rel.source).toBe("note:a");
      expect(rel.target).toBe("topic:b");
      expect(rel.predicate).toBe(predicate);
      expect(rel.directed).toBe(true);
    }
  });
});
