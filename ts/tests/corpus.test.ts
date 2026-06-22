import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { CollisionError, InvariantError, RefError, UnknownKindError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import { relatesTo } from "../src/relations.js";
import { registerBuiltinShapes } from "../src/shapes.js";

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

function shapeRegistry(): Registry {
  const r = new Registry();
  registerBuiltinShapes(r);
  return r;
}

describe("Corpus — rename", () => {
  it("rewrites inbound relations and records a deprecated id", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.add(n("topic:b", "topic", { relations: [relatesTo("topic:b", "topic:old")] }));
    const renamed = c.rename("topic:old", "topic:new");
    expect(renamed.id).toBe("topic:new");
    expect(renamed.deprecatedIds).toContain("topic:old");
    const b = c.get("topic:b");
    expect(b.relations.some((r) => r.target === "topic:new")).toBe(true);
    expect(b.relations.every((r) => r.target !== "topic:old")).toBe(true);
  });

  it("resolves the old id after rename, and the alias persists across a cold reload", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.rename("topic:old", "topic:new");
    expect(c.get("topic:old").id).toBe("topic:new");
    const fresh = new Corpus(root);
    expect(fresh.get("topic:old").id).toBe("topic:new");
  });

  it("rewrites membership members and edge sources", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.add(n("topic:x", "topic"));
    c.add(
      makeNode({
        id: "graph:g",
        kind: "graph",
        title: "G",
        facets: {
          membership: {
            shape: "graph",
            members: ["topic:old", "topic:x"],
            edges: [{ source: "topic:old", predicate: "to", target: "topic:x" }],
          },
        },
      }),
    );
    c.rename("topic:old", "topic:new");
    const mem = c.get("graph:g").facets.membership as Record<string, unknown>;
    expect(mem.members).toEqual(["topic:new", "topic:x"]);
    expect((mem.edges as Array<Record<string, unknown>>)[0].source).toBe("topic:new");
  });

  it("rewrites dict-membership values", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.add(n("topic:x", "topic"));
    c.add(
      makeNode({
        id: "dict:d",
        kind: "dict",
        title: "D",
        facets: { membership: { shape: "dict", members: { a: "topic:old", b: "topic:x" } } },
      }),
    );
    c.rename("topic:old", "topic:new");
    const mem = c.get("dict:d").facets.membership as Record<string, unknown>;
    expect(mem.members).toEqual({ a: "topic:new", b: "topic:x" });
  });

  it("rewrites the renamed node's OWN explicit relation source (no stale source: old)", () => {
    const c = new Corpus(root);
    c.add(n("topic:t", "topic"));
    c.add(
      makeNode({
        id: "topic:old",
        kind: "topic",
        title: "Old",
        relations: [{ source: "topic:old", predicate: "cites", target: "topic:t" }],
      }),
    );
    c.rename("topic:old", "topic:new");
    const renamed = c.get("topic:new");
    const cites = renamed.relations.find((r) => r.predicate === "cites");
    expect(cites?.source).toBe("topic:new");
    expect(renamed.relations.every((r) => r.source !== "topic:old")).toBe(true);
  });

  it("rewrites a multi-ref referrer exactly once (both refs land on the new id)", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.add(
      makeNode({
        id: "topic:r",
        kind: "topic",
        title: "R",
        relations: [relatesTo("topic:r", "topic:old"), { source: "topic:r", predicate: "cites", target: "topic:old" }],
      }),
    );
    c.rename("topic:old", "topic:new");
    const r = c.get("topic:r");
    expect(r.relations.every((rel) => rel.target !== "topic:old")).toBe(true);
    expect(r.relations.filter((rel) => rel.target === "topic:new")).toHaveLength(2);
  });

  it("inbound finds an edge across the deprecated id after rename", () => {
    const c = new Corpus(root);
    c.add(n("topic:old", "topic"));
    c.add(n("topic:b", "topic", { relations: [relatesTo("topic:b", "topic:old")] }));
    c.rename("topic:old", "topic:new");
    const inbound = c.inbound("topic:new");
    expect(inbound).toHaveLength(1);
    expect(inbound[0].sourceUid).toBe(c.index.idToUid.get("topic:b"));
  });

  it("rejects a deprecated or unknown oldId without writing or deleting", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic", { deprecatedIds: ["topic:stale"] }));
    expect(() => c.rename("topic:stale", "topic:z")).toThrow(RefError); // deprecated, not live
    expect(() => c.rename("topic:ghost", "topic:z")).toThrow(RefError); // unknown
    expect(c.get("topic:a").id).toBe("topic:a");
    expect(existsSync(join(root, "topic", "z.md"))).toBe(false);
  });

  it("rejects a target id already in use", () => {
    const c = new Corpus(root);
    c.add(n("topic:a", "topic"));
    c.add(n("topic:b", "topic"));
    expect(() => c.rename("topic:a", "topic:b")).toThrow(CollisionError);
  });
});

describe("Corpus — registry validation (built-in shapes)", () => {
  it("with no registry, an unregistered kind is allowed", () => {
    const c = new Corpus(root); // no registry
    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A" })); // topic is not a built-in shape
    expect(c.get("topic:a").title).toBe("A");
  });

  it("a registry rejects an unknown kind on add, writing no file", () => {
    const c = new Corpus(root, shapeRegistry());
    expect(() => c.add(makeNode({ id: "topic:a", kind: "topic", title: "A" }))).toThrow(UnknownKindError);
    expect(existsSync(join(root, "topic"))).toBe(false);
  });

  it("a registry rejects an invalid node on add, writing no file", () => {
    const c = new Corpus(root, shapeRegistry());
    // a `dag` whose membership has a cycle fails requireAcyclic
    const bad = makeNode({
      id: "dag:d",
      kind: "dag",
      title: "D",
      facets: {
        membership: {
          shape: "dag",
          members: ["a:1", "a:2"],
          edges: [
            { source: "a:1", predicate: "e", target: "a:2" },
            { source: "a:2", predicate: "e", target: "a:1" },
          ],
        },
      },
    });
    expect(() => c.add(bad)).toThrow(InvariantError);
    expect(existsSync(join(root, "dag"))).toBe(false);
  });

  it("a registry accepts a valid node on add", () => {
    const c = new Corpus(root, shapeRegistry());
    c.add(
      makeNode({ id: "set:s", kind: "set", title: "S", facets: { membership: { shape: "set", members: ["a:1"] } } }),
    );
    expect(c.get("set:s").title).toBe("S");
  });

  it("rename validates the renamed node before any write (no partial rename)", () => {
    // Seed without a registry so we can place a node whose RENAMED kind would be invalid.
    const seed = new Corpus(root);
    seed.add(
      makeNode({
        id: "set:s",
        kind: "set",
        title: "S",
        facets: { membership: { shape: "set", members: ["a:1", "a:1"] } }, // duplicate members
      }),
    );
    const c = new Corpus(root, shapeRegistry());
    // set:s is invalid (duplicate members) under requireUniqueMembers; renaming it re-validates.
    expect(() => c.rename("set:s", "set:s2")).toThrow(InvariantError);
    const fresh = new Corpus(root);
    expect(fresh.get("set:s").title).toBe("S"); // old id still live
    expect(() => fresh.get("set:s2")).toThrow(RefError); // new id absent
  });

  it("rename blocked by an invalid referrer writes nothing", () => {
    const seed = new Corpus(root); // no registry — lets us write an invalid referrer
    seed.add(
      makeNode({
        id: "set:t",
        kind: "set",
        title: "set:t",
        facets: { membership: { shape: "set", members: ["a:1"] } },
      }),
    );
    seed.add(
      makeNode({
        id: "dag:bad",
        kind: "dag",
        title: "Bad",
        facets: {
          membership: {
            shape: "dag",
            members: ["a:1"],
            edges: [{ source: "a:1", predicate: "e", target: "a:1" }], // self-cycle → requireAcyclic fails
          },
        },
        relations: [{ source: "dag:bad", predicate: "about", target: "set:t" }],
      }),
    );
    const c = new Corpus(root, shapeRegistry());
    expect(() => c.rename("set:t", "set:t2")).toThrow(InvariantError);
    const fresh = new Corpus(root);
    expect(fresh.get("set:t").title).toBe("set:t"); // unchanged
    expect(() => fresh.get("set:t2")).toThrow(RefError);
    expect(fresh.get("dag:bad").relations[0].target).toBe("set:t"); // referrer untouched
  });
});
