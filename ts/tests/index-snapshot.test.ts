import { describe, expect, it } from "vitest";
import { makeNode } from "../src/node.js";
import { relatesTo } from "../src/relations.js";
import { Index, type OutRef } from "../src/structural-index.js";

function canonicalAttrs(attrs: Record<string, unknown>): string {
  const sorted: Record<string, unknown> = {};
  for (const k of Object.keys(attrs).sort()) sorted[k] = attrs[k];
  return JSON.stringify(sorted);
}
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

function seed(): Index {
  return Index.build([
    makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:b")] }),
    makeNode({ id: "topic:b", kind: "topic", title: "B", deprecatedIds: ["topic:bb"] }),
    makeNode({
      id: "graph:g",
      kind: "graph",
      title: "G",
      facets: {
        membership: {
          shape: "graph",
          members: ["topic:a", "topic:missing"],
          edges: [{ source: "topic:a", predicate: "to", target: "topic:b" }],
        },
      },
    }),
  ]);
}

describe("structural Index snapshot", () => {
  it("round-trips to a structurally-equivalent index", () => {
    const idx = seed();
    expect(normalize(Index.fromDict(idx.toDict()))).toEqual(normalize(idx));
  });

  it("preserves shared-Relation identity so inbound/dangling dedup correctly", () => {
    const idx = seed();
    const restored = Index.fromDict(idx.toDict());
    // topic:a -> topic:b relation: one Relation object backs both source and target outRefs.
    const aUid = restored.idToUid.get("topic:a") as string;
    const out = restored.outboundEdges(aUid);
    expect(out.length).toBe(1);
    // topic:missing is dangling (membership_member role does not produce a relation edge,
    // but the graph edge a->b resolves; the relatesTo a->b resolves too). Confirm no spurious dup.
    const bUid = restored.idToUid.get("topic:b") as string;
    expect(restored.inboundEdges(bUid).length).toBe(idx.inboundEdges(idx.idToUid.get("topic:b") as string).length);
  });

  it("round-trips an empty index", () => {
    expect(normalize(Index.fromDict(new Index().toDict()))).toEqual(normalize(new Index()));
  });

  it("rejects a duplicate uid across entries", () => {
    const d = seed().toDict();
    d.entries.push({ ...d.entries[0] });
    expect(() => Index.fromDict(d)).toThrow();
  });

  it("rejects an entry whose id kind disagrees with kind", () => {
    const d = seed().toDict();
    d.entries[0].kind = "gene";
    expect(() => Index.fromDict(d)).toThrow();
  });

  it("rejects a deprecated id equal to the live id", () => {
    const d = seed().toDict();
    d.entries[0].deprecatedIds = [d.entries[0].id];
    expect(() => Index.fromDict(d)).toThrow();
  });

  it("rejects an identity claim already in use by another entry", () => {
    const d = seed().toDict();
    d.entries[1].deprecatedIds = ["topic:a"]; // topic:a is entry 0's live id
    expect(() => Index.fromDict(d)).toThrow();
  });
});
