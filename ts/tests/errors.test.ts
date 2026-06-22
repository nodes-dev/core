import { describe, expect, it } from "vitest";
import { IdError, NodesError, ValidationError } from "../src/errors.js";

describe("errors", () => {
  it("all kernel errors extend NodesError", () => {
    expect(new IdError("x")).toBeInstanceOf(NodesError);
    expect(new ValidationError("x")).toBeInstanceOf(Error);
  });
  it("sets name to the subclass name", () => {
    expect(new IdError("x").name).toBe("IdError");
  });
});
