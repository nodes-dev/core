import { type Relation, RelationSchema } from "../relations.js";

export const ABOUT = "about"; // any node -> topic
export const CITES = "cites"; // any node -> paper/book/dataset
export const ANSWERS = "answers"; // note/idea -> question
export const ASKS = "asks"; // any node -> question (raises one)
export const REFINES = "refines"; // any node -> node (builds on / supersedes)

/** `source` is about `target` (a topic). */
export function about(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: ABOUT, target });
}

/** `source` cites `target` (a paper/book/dataset). */
export function cites(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: CITES, target });
}

/** `source` (a note/idea) answers `target` (a question). */
export function answers(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: ANSWERS, target });
}

/** `source` raises `target` (a question). */
export function asks(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: ASKS, target });
}

/** `source` refines / supersedes `target`. */
export function refines(source: string, target: string): Relation {
  return RelationSchema.parse({ source, predicate: REFINES, target });
}
