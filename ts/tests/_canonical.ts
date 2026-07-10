import type { Node } from "../src/node.js";

// Language-neutral canonical JSON of a node (docs/STANDARD.md §11.1). Mirrors python/tests/_canonical.py.
export function toCanonical(node: Node): unknown {
  return {
    id: node.id,
    uid: node.uid,
    kind: node.kind,
    title: node.title,
    body: node.body,
    metadata: {
      created: node.metadata.created,
      updated: node.metadata.updated,
      version: node.metadata.version,
    },
    relations: node.relations.map((r) => ({
      source: r.source,
      predicate: r.predicate,
      target: r.target,
      directed: r.directed,
      weight: r.weight,
      attrs: r.attrs,
    })),
    facets: node.facets,
    deprecated_ids: node.deprecatedIds,
  };
}
