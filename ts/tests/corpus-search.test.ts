import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { makeNode } from "../src/node.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-search-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function seed(c: Corpus): void {
  c.add(makeNode({ id: "topic:a", kind: "topic", title: "alpha", body: "alpha beta" }));
  c.add(makeNode({ id: "topic:b", kind: "topic", title: "beta", body: "gamma" }));
}

describe("Corpus full-text search", () => {
  it("ranks title above body after add", () => {
    const c = new Corpus(root);
    seed(c);
    expect(c.search("beta").map((h) => h.id)).toEqual(["topic:b", "topic:a"]);
  });

  it("reflects delete", () => {
    const c = new Corpus(root);
    seed(c);
    c.delete("topic:b");
    expect(c.search("beta").map((h) => h.id)).toEqual(["topic:a"]); // only the body match remains
  });

  it("reflects rename and the hit carries the new id", () => {
    const c = new Corpus(root);
    seed(c);
    c.rename("topic:a", "topic:a2");
    expect(c.search("alpha").map((h) => h.id)).toEqual(["topic:a2"]);
  });

  it("rebuilds equivalently from disk on a fresh Corpus", () => {
    const c = new Corpus(root);
    seed(c);
    const fresh = new Corpus(root); // second corpus scans the same dir
    expect(fresh.search("beta").map((h) => h.id)).toEqual(c.search("beta").map((h) => h.id));
  });

  it("honors limit through the corpus", () => {
    const c = new Corpus(root);
    seed(c);
    expect(c.search("beta", 1).length).toBe(1);
  });
});
