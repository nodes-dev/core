import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { RefError } from "../src/errors.js";
import { type Node, makeNode } from "../src/node.js";
import { Store } from "../src/store.js";

let root: string;
let store: Store;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-store-"));
  store = new Store(root);
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function n(id: string, kind: string, extra: Partial<Node> = {}): Node {
  return makeNode({ id, kind, title: id, ...extra });
}

describe("Store file mechanics", () => {
  it("writeFile then readFile round-trips", () => {
    store.writeFile(makeNode({ id: "topic:a", kind: "topic", title: "A", body: "hi" }));
    const got = store.readFile("topic:a");
    expect(got.title).toBe("A");
    expect(got.body).toBe("hi");
  });

  it("writeFile has no collision check — a different uid at the same id just overwrites", () => {
    store.writeFile(n("topic:a", "topic"));
    store.writeFile(makeNode({ id: "topic:a", kind: "topic", title: "Other" }));
    expect(store.readFile("topic:a").title).toBe("Other");
  });

  it("pathFor encodes a CURIE slug", () => {
    expect(store.pathFor("gene:HGNC:PHF19")).toBe(join(root, "gene", "HGNC__PHF19.md"));
  });

  it("readFile on a missing node throws RefError", () => {
    expect(() => store.readFile("topic:ghost")).toThrow(RefError);
  });

  it("deleteFile removes, then a second delete and a read both throw RefError", () => {
    store.writeFile(n("topic:a", "topic"));
    store.deleteFile("topic:a");
    expect(() => store.readFile("topic:a")).toThrow(RefError);
    expect(() => store.deleteFile("topic:a")).toThrow(RefError);
  });

  it("allNodes scans the corpus sorted by path", () => {
    store.writeFile(n("topic:b", "topic"));
    store.writeFile(n("topic:a", "topic"));
    expect(store.allNodes().map((x) => x.id)).toEqual(["topic:a", "topic:b"]);
  });
});
