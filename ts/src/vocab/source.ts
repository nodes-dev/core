import { z } from "zod";
import { FacetError, InvariantError } from "../errors.js";
import type { Node } from "../node.js";

export const SOURCE = "source";

const SourceYearSchema = z.preprocess((value) => {
  if (typeof value === "string" && value.trim() !== "") return Number(value);
  return value;
}, z.number().int().nullable().default(null));

/** Shared bibliographic facet for paper / book / dataset kinds. `.strict()` mirrors
 *  Pydantic's `extra="forbid"`: unknown keys (typos) fail, never silently dropped. */
export const SourceSchema = z
  .object({
    authors: z.array(z.string()).default([]),
    year: SourceYearSchema,
    container: z.string().nullable().default(null), // journal / publisher / repository
    identifier: z.string().nullable().default(null), // DOI / ISBN / accession id
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
  // Faithful to Python's `if not (s.authors or s.year or s.identifier or s.url)`:
  // truthiness, so an empty author list / year 0 / "" identifier counts as absent.
  if (!(s.authors.length || s.year || s.identifier || s.url)) {
    throw new InvariantError(`${node.id}: source facet needs at least one of authors/year/identifier/url`);
  }
}
