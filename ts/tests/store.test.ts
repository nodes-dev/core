import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CollisionError, RefError } from "../src/errors.js";
import { type Node, makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
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

describe("Store CRUD", () => {
  it("writes then reads a node back", () => {
    const a = n("topic:a", "topic");
    store.write(a);
    expect(store.read("topic:a").id).toBe("topic:a");
  });

  it("resolve() throws RefError for an unknown ref", () => {
    expect(() => store.resolve("topic:missing")).toThrow(RefError);
  });

  it("write() rejects a second node reusing a live uid under a different id", () => {
    const a = n("topic:a", "topic");
    store.write(a);
    const clash = makeNode({ id: "topic:b", kind: "topic", title: "b", uid: a.uid });
    expect(() => store.write(clash)).toThrow(CollisionError);
  });

  it("delete() removes a node and errors when absent", () => {
    store.write(n("topic:a", "topic"));
    store.delete("topic:a");
    expect(() => store.delete("topic:a")).toThrow(RefError);
  });

  it("rename() rewrites the node, records a deprecated id, and rewrites inbound refs", () => {
    store.write(n("topic:old", "topic"));
    store.write(n("note:r", "note", { relations: [relatesTo("note:r", "topic:old")] }));

    const renamed = store.rename("topic:old", "topic:new");
    expect(renamed.id).toBe("topic:new");
    expect(renamed.deprecatedIds).toContain("topic:old");

    // old ref still resolves through the deprecated alias
    expect(store.resolve("topic:old").id).toBe("topic:new");
    // inbound reference was rewritten
    expect(store.read("note:r").relations[0].target).toBe("topic:new");
  });

  it("rename() rejects a target id already in use", () => {
    store.write(n("topic:a", "topic"));
    store.write(n("topic:b", "topic"));
    expect(() => store.rename("topic:a", "topic:b")).toThrow(CollisionError);
  });

  it("rename() rewrites membership members and edges", () => {
    store.write(n("topic:old", "topic"));
    store.write(
      makeNode({
        id: "graph:g",
        kind: "graph",
        title: "g",
        facets: {
          membership: {
            shape: "graph",
            members: ["topic:old"],
            edges: [{ source: "topic:old", predicate: "e", target: "topic:old" }],
          },
        },
      }),
    );
    store.rename("topic:old", "topic:new");
    const g = store.read("graph:g");
    expect(g.facets.membership.members).toEqual(["topic:new"]);
    expect((g.facets.membership.edges as Array<Record<string, unknown>>)[0]).toMatchObject({
      source: "topic:new",
      target: "topic:new",
    });
  });
});
