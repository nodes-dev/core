import { existsSync, mkdtempSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { CollisionError } from "../src/errors.js";
import { nodeToMarkdown } from "../src/frontmatter.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { snapshotPath } from "../src/snapshot.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-persist-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function seed(): Corpus {
  const c = new Corpus(root);
  c.add(
    makeNode({
      id: "topic:a",
      kind: "topic",
      title: "A",
      body: "alpha gamma",
      relations: [relatesTo("topic:a", "topic:b")],
    }),
  );
  c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", body: "beta gamma" }));
  return c;
}

function results(c: Corpus): unknown {
  return {
    searchGamma: c.search("gamma").map((h) => [h.id, h.uid]),
    outboundA: c.outbound("topic:a").map((e) => [e.relation.target, e.targetUid]),
    dangling: c.dangling().length,
  };
}

function freshRebuild(): Corpus {
  rmSync(snapshotPath(root));
  return new Corpus(root);
}

describe("Corpus persistence", () => {
  it("round-trip load matches a fresh rebuild", () => {
    const c = seed();
    c.flushIndex();
    expect(statSync(snapshotPath(root)).isFile()).toBe(true);
    const loaded = new Corpus(root);
    const fresh = freshRebuild();
    expect(results(loaded)).toEqual(results(c));
    expect(results(loaded)).toEqual(results(fresh));
  });

  it("construction never writes the snapshot", () => {
    seed(); // no flush
    expect(existsSync(snapshotPath(root))).toBe(false);
    new Corpus(root); // full rebuild, must not write
    expect(existsSync(snapshotPath(root))).toBe(false);
  });

  it("reconciles a direct on-disk edit (same uid/id, content change)", () => {
    const c = seed();
    c.flushIndex();
    const b = c.store.readFile("topic:b");
    b.body = "beta delta epsilon";
    writeFileSync(c.store.pathFor("topic:b"), nodeToMarkdown(b), "utf-8");
    const reconciled = new Corpus(root);
    expect(reconciled.search("delta").map((h) => [h.id, h.uid])).toEqual([["topic:b", b.uid]]);
  });

  it("reconciles added and deleted files", () => {
    const c = seed();
    c.flushIndex();
    rmSync(c.store.pathFor("topic:a"));
    c.store.writeFile(makeNode({ id: "topic:c", kind: "topic", title: "C", body: "gamma" }));
    const reconciled = new Corpus(root);
    expect(new Set(reconciled.search("gamma").map((h) => h.id))).toEqual(new Set(["topic:b", "topic:c"]));
  });

  it("silently rebuilds from a corrupt snapshot", () => {
    const c = seed();
    c.flushIndex();
    writeFileSync(snapshotPath(root), "{garbage", "utf-8");
    const rebuilt = new Corpus(root); // must not throw
    expect(results(rebuilt)).toEqual(results(c));
  });

  it("propagates a malformed corpus file on construction", () => {
    seed();
    const c2 = new Corpus(root);
    c2.flushIndex();
    writeFileSync(c2.store.pathFor("topic:a"), "---\nnot: valid node\n---\nbody", "utf-8");
    expect(() => new Corpus(root)).toThrow();
  });

  it("raises CollisionError when reconcile introduces a duplicate uid", () => {
    const c = seed();
    c.flushIndex();
    const a = c.store.readFile("topic:a");
    const b = c.store.readFile("topic:b");
    b.uid = a.uid;
    writeFileSync(c.store.pathFor("topic:b"), nodeToMarkdown(b), "utf-8");
    expect(() => new Corpus(root)).toThrow(CollisionError);
  });
});
