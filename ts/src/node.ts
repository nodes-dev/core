import { randomUUID } from "node:crypto";
import { z } from "zod";
import { IdError, ValidationError } from "./errors.js";
import { NodeId } from "./ids.js";
import { RelationSchema } from "./relations.js";

export function newUid(): string {
  return randomUUID().replace(/-/g, "");
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const dateStr = z
  .string()
  .regex(DATE_RE, "expected a YYYY-MM-DD date string")
  .refine((s) => {
    // Real-calendar validity via explicit arithmetic — full parity with Python's `date`
    // (MINYEAR=1, rejects 2026-99-99 / 2026-02-30 / non-leap 02-29, accepts 0001-0099).
    // Deliberately avoids JS `Date`, which maps years 0-99 onto 1900-1999.
    const [y, m, d] = s.split("-").map(Number);
    if (y < 1 || m < 1 || m > 12 || d < 1) return false;
    const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
    const maxDay = m === 2 && leap ? 29 : DAYS_IN_MONTH[m - 1];
    return d <= maxDay;
  }, "not a valid calendar date");

export const NodeMetadataSchema = z.object({
  created: dateStr.nullable().default(null),
  updated: dateStr.nullable().default(null),
  version: z.number().int().default(1),
});

export type NodeMetadata = z.infer<typeof NodeMetadataSchema>;

export const NodeSchema = z.object({
  id: z.string(),
  uid: z.string().default(() => newUid()),
  kind: z.string(),
  title: z.string(),
  body: z.string().default(""),
  metadata: z.preprocess((v) => v ?? {}, NodeMetadataSchema),
  relations: z.array(RelationSchema).default([]),
  facets: z.record(z.record(z.unknown())).default({}),
  deprecatedIds: z.array(z.string()).default([]),
});

export type Node = z.infer<typeof NodeSchema>;
export type NodeInput = z.input<typeof NodeSchema>;

export function makeNode(input: NodeInput): Node {
  let node: Node;
  try {
    node = NodeSchema.parse(input);
  } catch (e) {
    if (e instanceof z.ZodError) {
      throw new ValidationError(e.issues.map((i) => i.message).join("; "));
    }
    throw e;
  }
  let parsed: NodeId;
  try {
    parsed = NodeId.parse(node.id);
  } catch (e) {
    if (e instanceof IdError) throw new ValidationError(e.message);
    throw e;
  }
  if (parsed.kind !== node.kind) {
    throw new ValidationError(`id kind ${JSON.stringify(parsed.kind)} != kind field ${JSON.stringify(node.kind)}`);
  }
  return node;
}
