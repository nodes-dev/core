import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { VectorCache } from "../src/similarity.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-vec-cache-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

const NS = "fixture-v1";
const HEX64 = "a".repeat(64);

describe("VectorCache", () => {
  it("returns null on a miss", () => {
    expect(new VectorCache(root).get(NS, HEX64)).toBeNull();
  });

  it("round-trips a raw vector through an atomic write", () => {
    const cache = new VectorCache(root);
    cache.put(NS, HEX64, [1, 2, 3.5, -4]);
    expect(cache.get(NS, HEX64)).toEqual([1, 2, 3.5, -4]);
    // the file lives under the namespaced cache dir and contains {dim, vector}
    const path = join(root, ".nodes-index", "vectors", NS, `${HEX64}.json`);
    expect(existsSync(path)).toBe(true);
    expect(JSON.parse(readFileSync(path, "utf-8"))).toEqual({ dim: 4, vector: [1, 2, 3.5, -4] });
  });

  it("leaves no .tmp file behind", () => {
    const cache = new VectorCache(root);
    cache.put(NS, HEX64, [1, 0]);
    expect(existsSync(join(root, ".nodes-index", "vectors", NS, `${HEX64}.json.tmp`))).toBe(false);
  });

  it("rejects an unsafe namespace or hash before touching disk", () => {
    const cache = new VectorCache(root);
    expect(() => cache.get("..", HEX64)).toThrow(TypeError);
    expect(() => cache.put("ok", "nothex", [1])).toThrow(TypeError);
  });

  it("rejects a non-finite vector on put (never serialized)", () => {
    const cache = new VectorCache(root);
    expect(() => cache.put(NS, HEX64, [1, Number.NaN])).toThrow(TypeError);
    expect(() => cache.put(NS, HEX64, [1, Number.POSITIVE_INFINITY])).toThrow(TypeError);
    expect(() => cache.put(NS, HEX64, [])).toThrow(RangeError); // length < 1
  });

  it("throws on a corrupt cache file", () => {
    const cache = new VectorCache(root);
    const dir = join(root, ".nodes-index", "vectors", NS);
    const path = join(dir, `${HEX64}.json`);
    cache.put(NS, HEX64, [1, 2]); // create the dir + a valid file first
    writeFileSync(path, "{ not json", "utf-8");
    expect(() => cache.get(NS, HEX64)).toThrow(TypeError);
    writeFileSync(path, JSON.stringify({ dim: 3, vector: [1, 2] }), "utf-8"); // length mismatch
    expect(() => cache.get(NS, HEX64)).toThrow(TypeError);
    writeFileSync(path, JSON.stringify({ vector: [1, 2] }), "utf-8"); // missing dim
    expect(() => cache.get(NS, HEX64)).toThrow(TypeError);
  });
});
