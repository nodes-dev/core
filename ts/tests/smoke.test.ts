import { describe, expect, it } from "vitest";
import { KERNEL_VERSION } from "../src/index.js";

describe("scaffold", () => {
  it("exposes a version string", () => {
    expect(KERNEL_VERSION).toBe("0.1.0");
  });
});
