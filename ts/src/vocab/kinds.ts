import type { Registry } from "../registry.js";
import { SOURCE, requireIdentifiableSource } from "./source.js";

export const NOTE = "note";
export const IDEA = "idea";
export const QUESTION = "question";
export const TOPIC = "topic";
export const PAPER = "paper";
export const BOOK = "book";
export const DATASET = "dataset";

export const PROSE_KINDS = [NOTE, IDEA, QUESTION, TOPIC] as const;
export const SOURCE_KINDS = [PAPER, BOOK, DATASET] as const;

/** Register the standard knowledge-vocab kinds onto `reg`.
 *  Mirrors `registerBuiltinShapes` in `shapes.ts`. */
export function registerKnowledgeVocab(reg: Registry): void {
  for (const name of PROSE_KINDS) {
    reg.register({ name });
  }
  for (const name of SOURCE_KINDS) {
    reg.register({ name, requiredFacets: new Set([SOURCE]), invariants: [requireIdentifiableSource] });
  }
}
