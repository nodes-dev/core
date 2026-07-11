import { describe, expect, it } from "vitest";
import { CollisionError, RefError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { MEMBERSHIP } from "../src/shapes.js";
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

describe("Index — graph queries", () => {
  it("outbound returns the node's source relations, resolved", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:b")] });
    const b = makeNode({ id: "topic:b", kind: "topic", title: "B" });
    const idx = Index.build([a, b]);
    const edges = idx.outboundEdges(a.uid);
    expect(edges).toHaveLength(1);
    expect(edges[0].relation.target).toBe("topic:b");
    expect(edges[0].sourceUid).toBe(a.uid);
    expect(edges[0].targetUid).toBe(b.uid);
  });

  it("inbound returns the node's target relations, resolved", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:b")] });
    const b = makeNode({ id: "topic:b", kind: "topic", title: "B" });
    const idx = Index.build([a, b]);
    const edges = idx.inboundEdges(b.uid);
    expect(edges).toHaveLength(1);
    expect(edges[0].sourceUid).toBe(a.uid);
    expect(edges[0].targetUid).toBe(b.uid);
  });

  it("inbound merges across a deprecated target ref", () => {
    const b = makeNode({ id: "topic:new", kind: "topic", title: "B", deprecatedIds: ["topic:old"] });
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:old")] });
    const idx = Index.build([a, b]);
    const edges = idx.inboundEdges(b.uid);
    expect(edges).toHaveLength(1);
    expect(edges[0].sourceUid).toBe(a.uid);
  });

  it("a relation with a non-container source attributes to the source node, not the file's node", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A" });
    const b = makeNode({
      id: "topic:b",
      kind: "topic",
      title: "B",
      relations: [{ source: "topic:a", predicate: "cites", target: "topic:c" }],
    });
    const c = makeNode({ id: "topic:c", kind: "topic", title: "C" });
    const idx = Index.build([a, b, c]);
    const outA = idx.outboundEdges(a.uid);
    expect(outA).toHaveLength(1);
    expect(outA[0].relation.target).toBe("topic:c");
    expect(idx.outboundEdges(b.uid)).toEqual([]); // B is not the source of any relation
  });

  it("structure-facet refs are tracked but are NOT public graph edges", () => {
    const g = makeNode({
      id: "graph:g",
      kind: "graph",
      title: "G",
      facets: {
        membership: { members: ["topic:x"] },
        edges: { edges: [{ source: "topic:x", predicate: "to", target: "topic:y" }] },
      },
    });
    const x = makeNode({ id: "topic:x", kind: "topic", title: "X" });
    const y = makeNode({ id: "topic:y", kind: "topic", title: "Y" });
    const idx = Index.build([g, x, y]);
    // structural refs register as inbound refs (for rename) ...
    expect((idx.inRefs.get("topic:x") ?? []).some((r) => r.sourceUid === g.uid)).toBe(true);
    expect((idx.inRefs.get("topic:y") ?? []).some((r) => r.sourceUid === g.uid)).toBe(true);
    // ... but never as graph edges.
    expect(idx.outboundEdges(g.uid)).toEqual([]);
    expect(idx.inboundEdges(y.uid)).toEqual([]);
    expect(idx.danglingEdges()).toEqual([]);
  });

  it("dangling lists relations whose target resolves to no uid", () => {
    const a = makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:gone")] });
    const idx = Index.build([a]);
    const dangling = idx.danglingEdges();
    expect(dangling).toHaveLength(1);
    expect(dangling[0].relation.target).toBe("topic:gone");
    expect(dangling[0].targetUid).toBeNull();
  });
});

function setNode(id: string, members: string[], extra: Record<string, unknown> = {}) {
  return node(id, "set", { facets: { [MEMBERSHIP]: { members } }, ...extra });
}

describe("Index — membership traversal", () => {
  it("membersOf returns resolvable member uids and skips dangling refs", () => {
    const leaf = node("note:leaf", "note");
    const box = setNode("set:box", ["note:leaf", "note:ghost"]);
    const idx = Index.build([leaf, box]);
    expect(idx.membersOf(box.uid)).toEqual(new Set([leaf.uid]));
  });

  it("membersOf resolves members listed under a deprecated id", () => {
    const renamed = node("note:renamed", "note", { deprecatedIds: ["note:old"] });
    const box = setNode("set:box", ["note:old"]);
    const idx = Index.build([renamed, box]);
    expect(idx.membersOf(box.uid)).toEqual(new Set([renamed.uid]));
  });

  it("membersOf dedupes duplicate entries and live+deprecated refs to one uid", () => {
    const renamed = node("note:renamed", "note", { deprecatedIds: ["note:old"] });
    const box = setNode("set:box", ["note:renamed", "note:old", "note:renamed"]);
    const idx = Index.build([renamed, box]);
    expect(idx.membersOf(box.uid)).toEqual(new Set([renamed.uid]));
  });

  it("membersOf on a node without a membership facet is empty", () => {
    const plain = node("note:plain", "note");
    const idx = Index.build([plain]);
    expect(idx.membersOf(plain.uid)).toEqual(new Set());
  });

  it("membersOf and containersOf reject an unknown uid", () => {
    expect(() => new Index().membersOf("nope")).toThrow(RefError);
    expect(() => new Index().containersOf("nope")).toThrow(RefError);
  });

  it("containersOf finds containers listing the node's live or deprecated id", () => {
    const renamed = node("note:renamed", "note", { deprecatedIds: ["note:old"] });
    const byLive = setNode("set:live", ["note:renamed"]);
    const byDep = setNode("set:dep", ["note:old"]);
    const idx = Index.build([renamed, byLive, byDep]);
    expect(idx.containersOf(renamed.uid)).toEqual(new Set([byLive.uid, byDep.uid]));
  });

  it("containersOf on an uncontained node is empty", () => {
    const plain = node("note:plain", "note");
    const idx = Index.build([plain]);
    expect(idx.containersOf(plain.uid)).toEqual(new Set());
  });

  it("membershipClosure walks nesting transitively in both directions", () => {
    const leaf = node("note:leaf", "note");
    const box = setNode("set:box", ["note:leaf"]);
    const crate = setNode("set:crate", ["set:box"]);
    const idx = Index.build([leaf, box, crate]);
    expect(idx.membershipClosure(crate.uid, "members")).toEqual(new Set([box.uid, leaf.uid]));
    expect(idx.membershipClosure(leaf.uid, "containers")).toEqual(new Set([box.uid, crate.uid]));
  });

  it("membershipClosure terminates on cycles and always excludes the start node", () => {
    const a = setNode("set:a", ["set:b"]);
    const b = setNode("set:b", ["set:a"]);
    const selfie = setNode("set:selfie", ["set:selfie"]);
    const idx = Index.build([a, b, selfie]);
    expect(idx.membershipClosure(a.uid, "members")).toEqual(new Set([b.uid]));
    expect(idx.membershipClosure(selfie.uid, "members")).toEqual(new Set());
    expect(idx.membershipClosure(selfie.uid, "containers")).toEqual(new Set());
  });

  it("danglingMembers reports unresolved membership refs deduped per container", () => {
    const box = setNode("set:box", ["note:ghost", "note:ghost"]);
    const other = setNode("set:other", ["note:ghost"]);
    const idx = Index.build([box, other]);
    const rows = idx.danglingMembers();
    expect(rows).toHaveLength(2);
    expect(new Set(rows.map((r) => `${r.sourceUid} ${r.ref}`))).toEqual(
      new Set([`${box.uid} note:ghost`, `${other.uid} note:ghost`]),
    );
  });

  it("danglingMembers is empty when every member resolves (incl. via deprecated ids)", () => {
    const renamed = node("note:renamed", "note", { deprecatedIds: ["note:old"] });
    const box = setNode("set:box", ["note:old"]);
    expect(Index.build([renamed, box]).danglingMembers()).toEqual([]);
  });

  it("a malformed membership facet contributes no member refs and no danglers", () => {
    const weird = node("note:weird", "note", { facets: { [MEMBERSHIP]: { members: "not-a-list" } } });
    const idx = Index.build([weird]);
    expect(idx.membersOf(weird.uid)).toEqual(new Set());
    expect(idx.danglingMembers()).toEqual([]);
  });
});
