import { z } from "zod";
import { FacetError, InvariantError } from "../src/errors.js";
import type { Node } from "../src/node.js";
import type { Registry } from "../src/registry.js";

/** Test-support profile for the shared conformance fixtures (design §3.2).
 *  Registers the kinds the fixture corpora use; not shipped API. */

export const SOURCE = "source";

const SourceYearSchema = z.preprocess((value) => {
  if (typeof value === "string" && value.trim() !== "") return Number(value);
  return value;
}, z.number().int().nullable().default(null));

/** `.strict()` mirrors Pydantic's `extra="forbid"`: unknown keys (typos) fail,
 *  never silently dropped. */
export const SourceSchema = z
  .object({
    authors: z.array(z.string()).default([]),
    year: SourceYearSchema,
    container: z.string().nullable().default(null),
    identifier: z.string().nullable().default(null),
    url: z.string().nullable().default(null),
  })
  .strict();

export type Source = z.infer<typeof SourceSchema>;

export function sourceOf(node: Node): Source {
  const raw = node.facets[SOURCE];
  if (raw === undefined) {
    throw new FacetError(`${node.id}: missing '${SOURCE}' facet`);
  }
  try {
    return SourceSchema.parse(raw);
  } catch (e) {
    if (e instanceof z.ZodError) {
      throw new FacetError(`${node.id}: invalid '${SOURCE}' facet: ${e.issues.map((i) => i.message).join("; ")}`);
    }
    throw e;
  }
}

export function requireIdentifiableSource(node: Node): void {
  const s = sourceOf(node);
  // Truthiness on purpose: an empty author list / year 0 / "" identifier counts as absent.
  if (!(s.authors.length || s.year || s.identifier || s.url)) {
    throw new InvariantError(`${node.id}: source facet needs at least one of authors/year/identifier/url`);
  }
}

export const NOTE = "note";
export const TOPIC = "topic";
export const PAPER = "paper";

/** Register the kinds the shared fixtures need. `zzz` stays unregistered on
 *  purpose — the check oracle pins `unknown-kind` for it. */
export function registerFixturesProfile(reg: Registry): void {
  reg.register({ name: NOTE });
  reg.register({ name: TOPIC });
  reg.register({
    name: PAPER,
    requiredFacets: new Set([SOURCE]),
    invariants: [requireIdentifiableSource],
  });
}
