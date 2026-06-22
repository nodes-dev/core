import { z } from "zod";
import { RefError } from "./errors.js";

export const RELATES_TO = "relatesTo";

export const RelationSchema = z.object({
  source: z.string(),
  predicate: z.string(),
  target: z.string(),
  directed: z.boolean().default(true),
  weight: z.number().nullable().default(null),
  attrs: z.record(z.unknown()).default({}),
});

export type Relation = z.infer<typeof RelationSchema>;

// Low-level schema helpers. Like Python's `Relation(...)` / `Relation.from_serialized`, these may
// surface a raw ZodError on malformed input. The "never leak raw" contract lives in the boundary
// parsers (`makeNode`, `nodeFromMarkdown`, `membershipOf`), which catch and re-wrap as kernel errors.
export function fromSerialized(data: Record<string, unknown>, containerId: string): Relation {
  const { source, ...rest } = data;
  return RelationSchema.parse({ source: source !== undefined ? source : containerId, ...rest });
}

export function toSerialized(rel: Relation, containerId: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (rel.source !== containerId) out.source = rel.source;
  out.predicate = rel.predicate;
  out.target = rel.target;
  if (rel.directed !== true) out.directed = rel.directed;
  if (rel.weight !== null) out.weight = rel.weight;
  if (Object.keys(rel.attrs).length > 0) out.attrs = rel.attrs;
  return out;
}

export function relatesTo(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: RELATES_TO, target });
}

export function tagToRelation(source: string, tag: string, aliasMap: Record<string, string>): Relation {
  const name = tag.replace(/^#+/, "");
  const target = aliasMap[name] ?? aliasMap[name.toLowerCase()];
  if (target === undefined) {
    throw new RefError(`tag ${JSON.stringify(tag)} does not resolve to a known node`);
  }
  return relatesTo(source, target);
}
