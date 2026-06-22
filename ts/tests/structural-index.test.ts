import { describe, expect, it } from "vitest";
import { CollisionError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { Index } from "../src/structural-index.js";

function node(id: string, kind: string, extra: Record<string, unknown> = {}) {
  return makeNode({ id, kind, title: id, ...extra });
}

describe("Index — resolution & collision", () => {
  it("builds and resolves a live id", () => {
    const idx = Index.build([node("topic:a", "topic")]);
    const uid = idx.idToUid.get("topic:a");
    expect(idx.resolveUid("topic:a")).toBe(uid);
    expect(idx.resolveUid("topic:missing")).toBeNull();
  });

  it("resolves a deprecated id to its live node", () => {
    const a = node("topic:new", "topic", { deprecatedIds: ["topic:old"] });
    const idx = Index.build([a]);
    expect(idx.resolveUid("topic:old")).toBe(a.uid);
  });

  it("prefers a live id over a deprecated id (lookup order)", () => {
    const idx = new Index();
    idx.idToUid.set("topic:x", "uid-live");
    idx.deprecatedToUid.set("topic:x", "uid-dep");
    expect(idx.resolveUid("topic:x")).toBe("uid-live");
  });

  it("build rejects a colliding corpus (same id, different uid)", () => {
    const a = node("topic:a", "topic");
    const b = node("topic:a", "topic");
    expect(() => Index.build([a, b])).toThrow(CollisionError);
  });

  it("build rejects a duplicate uid", () => {
    const a = node("topic:a", "topic");
    const dup = makeNode({ id: "topic:a", kind: "topic", title: "copy", uid: a.uid });
    expect(() => Index.build([a, dup])).toThrow(CollisionError);
  });

  it("assertAddable rejects same id / different uid", () => {
    const idx = Index.build([node("topic:a", "topic")]);
    expect(() => idx.assertAddable(node("topic:a", "topic"))).toThrow(CollisionError);
  });

  it("assertAddable rejects same uid / different id (rename misuse)", () => {
    const a = node("topic:a", "topic");
    const idx = Index.build([a]);
    expect(() => idx.assertAddable(makeNode({ id: "topic:b", kind: "topic", title: "B", uid: a.uid }))).toThrow(
      CollisionError,
    );
  });

  it("assertAddable rejects a deprecated-id claim already in use", () => {
    const idx = Index.build([node("topic:a", "topic")]);
    expect(() => idx.assertAddable(node("topic:b", "topic", { deprecatedIds: ["topic:a"] }))).toThrow(CollisionError);
  });

  it("assertAddable allows a same-uid/same-id overwrite", () => {
    const a = node("topic:a", "topic");
    const idx = Index.build([a]);
    expect(() => idx.assertAddable(makeNode({ id: "topic:a", kind: "topic", title: "A2", uid: a.uid }))).not.toThrow();
  });
});

describe("Index — upsert & remove", () => {
  it("upsert replace is clean (old outbound refs dropped, new ones present)", () => {
    const a = node("topic:a", "topic", { relations: [relatesTo("topic:a", "topic:x")] });
    const idx = Index.build([a]);
    expect((idx.inRefs.get("topic:x") ?? []).some((r) => r.outRef.ref === "topic:x")).toBe(true);
    const a2 = makeNode({
      id: "topic:a",
      kind: "topic",
      title: "A",
      uid: a.uid,
      relations: [relatesTo("topic:a", "topic:y")],
    });
    idx.upsert(a2);
    expect(idx.inRefs.get("topic:x") ?? []).toEqual([]);
    expect((idx.inRefs.get("topic:y") ?? []).some((r) => r.outRef.ref === "topic:y")).toBe(true);
  });

  it("remove keeps a surviving referrer's inbound ref (it becomes dangling)", () => {
    const target = node("topic:t", "topic");
    const referrer = node("topic:r", "topic", { relations: [relatesTo("topic:r", "topic:t")] });
    const idx = Index.build([target, referrer]);
    idx.remove(target.uid);
    expect(idx.resolveUid("topic:t")).toBeNull();
    expect(idx.byUid.has(target.uid)).toBe(false);
    expect((idx.inRefs.get("topic:t") ?? []).some((r) => r.sourceUid === referrer.uid)).toBe(true);
  });
});
