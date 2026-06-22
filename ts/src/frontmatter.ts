import { parseDocument, stringify } from "yaml";
import { z } from "zod";
import { ValidationError } from "./errors.js";
import { type Node, makeNode } from "./node.js";
import { RELATES_TO, type Relation, fromSerialized, relatesTo, toSerialized } from "./relations.js";

export function splitFrontmatter(text: string): [Record<string, unknown>, string] {
  let nl: string;
  if (text.startsWith("---\r\n")) nl = "\r\n";
  else if (text.startsWith("---\n")) nl = "\n";
  else return [{}, text];

  const rest = text.slice(3 + nl.length);
  const sep = `${nl}---${nl}`;
  const idx = rest.indexOf(sep);
  if (idx === -1) return [{}, text];

  const doc = parseDocument(rest.slice(0, idx));
  if (doc.errors.length > 0) {
    throw new ValidationError(`invalid frontmatter YAML: ${doc.errors[0].message}`);
  }
  const fm = (doc.toJS() ?? {}) as Record<string, unknown>;
  return [fm, rest.slice(idx + sep.length)];
}

export function nodeFromMarkdown(text: string): Node {
  const [fm, body] = splitFrontmatter(text);
  const missing = (["id", "uid", "kind", "title"] as const).filter((k) => !(k in fm));
  if (missing.length > 0) {
    throw new ValidationError(`frontmatter missing required field(s): ${JSON.stringify(missing)}`);
  }
  const nodeId = fm.id as string;

  // `nodeFromMarkdown` is a boundary parser: every malformed-input path leaves as a typed
  // kernel error (spec §7), never a raw ZodError or a raw TypeError. Collection fields must be
  // lists — a scalar or mapping is a ValidationError, not a "not iterable" TypeError. (Python's
  // node_from_markdown leaks a raw TypeError here; the TS boundary deliberately tightens that.)
  if (fm.related !== undefined && !Array.isArray(fm.related)) {
    throw new ValidationError(`'related' must be a list in ${JSON.stringify(nodeId)}`);
  }
  if (fm.relations !== undefined && !Array.isArray(fm.relations)) {
    throw new ValidationError(`'relations' must be a list in ${JSON.stringify(nodeId)}`);
  }
  const relations: Relation[] = [];
  try {
    for (const ref of (fm.related as unknown[] | undefined) ?? []) {
      relations.push(relatesTo(nodeId, ref as string));
    }
    for (const raw of (fm.relations as Record<string, unknown>[] | undefined) ?? []) {
      relations.push(fromSerialized(raw, nodeId));
    }
  } catch (e) {
    if (e instanceof z.ZodError) {
      throw new ValidationError(
        `invalid relation in ${JSON.stringify(nodeId)}: ${e.issues.map((i) => i.message).join("; ")}`,
      );
    }
    throw e;
  }

  const metadata: Record<string, unknown> = {};
  for (const k of ["created", "updated", "version"] as const) {
    if (k in fm) metadata[k] = fm[k];
  }

  return makeNode({
    id: nodeId,
    uid: fm.uid as string,
    kind: fm.kind as string,
    title: fm.title as string,
    body,
    metadata,
    relations,
    facets: (fm.facets as Record<string, Record<string, unknown>>) ?? {},
    deprecatedIds: (fm.deprecated_ids as string[]) ?? [],
  });
}

function isPlainRelatesTo(rel: Relation, nodeId: string): boolean {
  return (
    rel.predicate === RELATES_TO &&
    rel.source === nodeId &&
    rel.directed === true &&
    rel.weight === null &&
    Object.keys(rel.attrs).length === 0
  );
}

export function nodeToMarkdown(node: Node): string {
  const fm: Record<string, unknown> = { id: node.id, uid: node.uid, kind: node.kind, title: node.title };
  if (node.metadata.created !== null) fm.created = node.metadata.created;
  if (node.metadata.updated !== null) fm.updated = node.metadata.updated;
  if (node.metadata.version !== 1) fm.version = node.metadata.version;

  const related = node.relations.filter((r) => isPlainRelatesTo(r, node.id)).map((r) => r.target);
  const typed = node.relations.filter((r) => !isPlainRelatesTo(r, node.id)).map((r) => toSerialized(r, node.id));
  if (related.length > 0) fm.related = related;
  if (typed.length > 0) fm.relations = typed;
  if (Object.keys(node.facets).length > 0) fm.facets = node.facets;
  if (node.deprecatedIds.length > 0) fm.deprecated_ids = node.deprecatedIds;

  const yamlText = stringify(fm, { sortMapEntries: false }).trimEnd();
  return `---\n${yamlText}\n---\n${node.body}`;
}
