import { describe, expect, it } from "vitest";
import {
  Corpus,
  Index,
  Registry,
  Store,
  makeNode,
  nodeFromMarkdown,
  nodeToMarkdown,
  registerBuiltinShapes,
} from "../src/index.js";

describe("barrel", () => {
  it("re-exports the public surface", () => {
    expect(typeof makeNode).toBe("function");
    expect(typeof nodeFromMarkdown).toBe("function");
    expect(typeof nodeToMarkdown).toBe("function");
    expect(typeof registerBuiltinShapes).toBe("function");
    expect(typeof Registry).toBe("function");
    expect(typeof Store).toBe("function");
    expect(typeof Corpus).toBe("function");
    expect(typeof Index).toBe("function");
  });
});
