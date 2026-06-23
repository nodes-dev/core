import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { iterCorpusFiles, loadSnapshot, snapshotPath } from "../src/snapshot.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-persist-rename-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function manifestMatchesDisk(c: Corpus): boolean {
  const onDisk = new Map(iterCorpusFiles(c.store.root).map((f) => [f.path, f.sha256]));
  if (onDisk.size !== c.manifest.size) return false;
  for (const [path, e] of c.manifest) if (onDisk.get(path) !== e.sha256) return false;
  return true;
}

function results(c: Corpus): unknown {
  return [
    c
      .search("gamma")
      .map((h) => [h.id, h.uid])
      .sort(),
    c
      .dangling()
      .map((e) => [e.relation.source, e.relation.target])
      .sort(),
    [...c.index.idToUid.keys()].sort(),
  ];
}

describe("Corpus manifest maintenance", () => {
  it("add keeps the manifest in sync with disk", () => {
    const c = new Corpus(root);
    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A", body: "gamma" }));
    c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", body: "gamma" }));
    expect(manifestMatchesDisk(c)).toBe(true);
  });

  it("delete removes the manifest entry", () => {
    const c = new Corpus(root);
    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A", body: "gamma" }));
    c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", body: "gamma" }));
    c.delete("topic:a");
    expect(c.manifest.has("topic/a.md")).toBe(false);
    expect(manifestMatchesDisk(c)).toBe(true);
  });

  it("rename updates referrers and removes the old path", () => {
    const c = new Corpus(root);
    c.add(
      makeNode({
        id: "topic:a",
        kind: "topic",
        title: "A",
        body: "gamma",
        relations: [relatesTo("topic:a", "topic:b")],
      }),
    );
    c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", body: "gamma" }));
    c.rename("topic:b", "topic:b2"); // rewrites a.md (referrer) and moves b.md -> b2.md
    expect(c.manifest.has("topic/b.md")).toBe(false);
    expect(c.manifest.has("topic/b2.md")).toBe(true);
    expect(manifestMatchesDisk(c)).toBe(true); // referrer a.md re-hashed too
  });

  it("flush after a mutation sequence reloads equivalently and matches a fresh rebuild", () => {
    const c = new Corpus(root);
    c.add(
      makeNode({
        id: "topic:a",
        kind: "topic",
        title: "A",
        body: "gamma",
        relations: [relatesTo("topic:a", "topic:b")],
      }),
    );
    c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", body: "gamma" }));
    c.rename("topic:b", "topic:b2");
    c.add(makeNode({ id: "topic:c", kind: "topic", title: "C", body: "gamma" }));
    c.delete("topic:a");
    c.flushIndex();
    const reloaded = new Corpus(root);
    expect(loadSnapshot(root, null)).not.toBeNull();
    expect(results(reloaded)).toEqual(results(c));
    rmSync(snapshotPath(root));
    expect(results(new Corpus(root))).toEqual(results(c));
  });
});
