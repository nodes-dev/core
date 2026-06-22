import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { CollisionError, RefError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";

let root: string;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function n(id: string, kind: string, extra: Record<string, unknown> = {}) {
  return makeNode({ id, kind, title: id, ...extra });
}

describe("Corpus — CRUD", () => {
  it("add then get round-trips", () => {
    const c = new Corpus(root);
    const node = makeNode({ id: "topic:a", kind: "topic", title: "A", body: "hi" });
    c.add(node);
    const got = c.get("topic:a");
    expect(got.title).toBe("A");
    expect(got.body).toBe("hi");
    expect(got.uid).toBe(node.uid);
  });

  it("a fresh Corpus rebuilds its index from existing files", () => {
    new Corpus(root).add(n("topic:a", "topic"));
    const fresh = new Corpus(root);
    expect(fresh.get("topic:a").title).toBe("topic:a");
  });

  it("add rejects a colliding id (same id, different uid)", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic"));
    expect(() => c.add(makeNode({ id: "topic:a", kind: "topic", title: "Other" }))).toThrow(CollisionError);
  });

  it("add rejects a duplicate uid at a different id", () => {
    const c = new Corpus(root);
    const original = n("topic:a", "topic");
    c.add(original);
    expect(() => c.add(makeNode({ id: "topic:b", kind: "topic", title: "B", uid: original.uid }))).toThrow(
      CollisionError,
    );
  });

  it("add rejects a deprecated-id claim already in use", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic"));
    expect(() => c.add(n("topic:b", "topic", { deprecatedIds: ["topic:a"] }))).toThrow(CollisionError);
  });

  it("add overwrites a same-uid/same-id node", () => {
    const c = new Corpus(root);
    const node = n("topic:a", "topic");
    c.add(node);
    node.title = "A2";
    c.add(node);
    expect(c.get("topic:a").title).toBe("A2");
  });

  it("get on an unresolved ref throws RefError", () => {
    expect(() => new Corpus(root).get("topic:ghost")).toThrow(RefError);
  });

  it("delete removes a node and is live-id-only", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic", { deprecatedIds: ["topic:old"] }));
    expect(() => c.delete("topic:old")).toThrow(RefError); // deprecated id is not a live id
    c.delete("topic:a");
    expect(() => c.get("topic:a")).toThrow(RefError);
  });
});

describe("Corpus — graph queries", () => {
  it("delete leaves a dangling inbound ref", () => {
    const c = new Corpus(root);
    c.add(n("topic:t", "topic"));
    c.add(n("topic:r", "topic", { relations: [relatesTo("topic:r", "topic:t")] }));
    c.delete("topic:t");
    const out = c.outbound("topic:r");
    expect(out).toHaveLength(1);
    expect(out[0].targetUid).toBeNull();
    expect(c.dangling()).toHaveLength(1);
    expect(() => c.inbound("topic:t")).toThrow(RefError); // the target no longer resolves
  });

  it("neighbors returns distinct resolved neighbors (outbound + inbound)", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic", { relations: [relatesTo("topic:a", "topic:b")] }));
    c.add(n("topic:b", "topic"));
    c.add(n("topic:c", "topic", { relations: [relatesTo("topic:c", "topic:a")] }));
    expect(
      c
        .neighbors("topic:a")
        .map((x) => x.id)
        .sort(),
    ).toEqual(["topic:b", "topic:c"]);
  });
});
