import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { Index, type OutRef } from "../src/structural-index.js";

let root: string;
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "nodes-rebuild-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

function canonicalAttrs(attrs: Record<string, unknown>): string {
  const sorted: Record<string, unknown> = {};
  for (const k of Object.keys(attrs).sort()) sorted[k] = attrs[k];
  return JSON.stringify(sorted);
}

// The key MUST embed the relation payload, not just (ref, role, sourceUid): a stale
// predicate/directed/weight/attrs would otherwise pass undetected, and comparing Relation
// OBJECTS directly gives false negatives (live vs rebuild hold distinct references).
function relationSignature(o: OutRef): string | null {
  const rel = o.relation;
  if (rel === undefined) return null;
  return JSON.stringify([rel.source, rel.predicate, rel.target, rel.directed, rel.weight, canonicalAttrs(rel.attrs)]);
}

function outRefKey(o: OutRef): string {
  return JSON.stringify([o.ref, o.role, relationSignature(o)]);
}

function normalize(index: Index): unknown {
  const byUid: Record<string, unknown> = {};
  for (const [uid, e] of index.byUid) {
    byUid[uid] = [e.id, e.kind, [...e.deprecatedIds].sort(), e.outRefs.map(outRefKey).sort()];
  }
  const inRefs: Record<string, string[]> = {};
  for (const [ref, rows] of index.inRefs) {
    inRefs[ref] = rows
      .map((r) => JSON.stringify([r.sourceUid, r.outRef.ref, r.outRef.role, relationSignature(r.outRef)]))
      .sort();
  }
  return {
    byUid,
    idToUid: Object.fromEntries(index.idToUid),
    deprecatedToUid: Object.fromEntries(index.deprecatedToUid),
    inRefs,
  };
}

function assertEquivalent(c: Corpus): void {
  const fresh = Index.build(c.store.allNodes());
  expect(normalize(c.index)).toEqual(normalize(fresh));
}

describe("Index rebuild equivalence", () => {
  it("holds through an add/rename/delete/re-add sequence", () => {
    const c = new Corpus(root);
    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:b")] }));
    c.add(makeNode({ id: "topic:b", kind: "topic", title: "B" }));
    c.add(
      makeNode({
        id: "graph:g",
        kind: "graph",
        title: "G",
        facets: {
          membership: { members: ["topic:a", "topic:b"] },
          edges: { edges: [{ source: "topic:a", predicate: "to", target: "topic:b" }] },
        },
      }),
    );
    assertEquivalent(c);

    c.rename("topic:b", "topic:b2"); // deprecated id + rewrites A's relation and graph members/edges
    assertEquivalent(c);

    c.add(makeNode({ id: "topic:c", kind: "topic", title: "C", relations: [relatesTo("topic:c", "topic:a")] }));
    assertEquivalent(c);

    c.delete("topic:a"); // strands inbound refs from topic:c and graph:g → must stay dangling
    assertEquivalent(c);
    expect(c.dangling().length).toBeGreaterThanOrEqual(1);

    c.add(makeNode({ id: "topic:a", kind: "topic", title: "A again" })); // reconverges dangling refs
    assertEquivalent(c);
    expect(c.dangling()).toEqual([]);
    expect(c.outbound("topic:c").every((e) => e.targetUid !== null)).toBe(true);
  });

  it("holds after a same-uid/same-id overwrite that changes outbound refs", () => {
    const c = new Corpus(root);
    const node = makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:x")] });
    c.add(node);
    node.relations = [relatesTo("topic:a", "topic:y")];
    c.add(node); // same uid + id overwrite
    assertEquivalent(c);
  });
});
