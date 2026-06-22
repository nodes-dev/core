import { z } from "zod";
import { FacetError, InvariantError } from "./errors.js";
import type { Node } from "./node.js";
import type { KindSpec, Registry } from "./registry.js";
import { RelationSchema } from "./relations.js";

export const MEMBERSHIP = "membership";

export const MembershipSchema = z.object({
  shape: z.string(),
  members: z.union([z.array(z.string()), z.record(z.string())]).default([]),
  edges: z.array(RelationSchema).default([]),
});

export type Membership = z.infer<typeof MembershipSchema>;

export function membershipOf(node: Node): Membership {
  const raw = node.facets[MEMBERSHIP];
  if (raw === undefined) {
    throw new FacetError(`${node.id}: missing '${MEMBERSHIP}' facet`);
  }
  try {
    return MembershipSchema.parse(raw);
  } catch (e) {
    if (e instanceof z.ZodError) {
      throw new FacetError(`${node.id}: invalid '${MEMBERSHIP}' facet: ${e.issues.map((i) => i.message).join("; ")}`);
    }
    throw e;
  }
}

function memberIds(m: Membership): string[] {
  return Array.isArray(m.members) ? [...m.members] : Object.values(m.members);
}

export function requireUniqueMembers(node: Node): void {
  const ids = memberIds(membershipOf(node));
  if (ids.length !== new Set(ids).size) {
    throw new InvariantError(`${node.id}: members must be unique`);
  }
}

export function requireDictKeys(node: Node): void {
  if (Array.isArray(membershipOf(node).members)) {
    throw new InvariantError(`${node.id}: dict shape requires a key->ref mapping`);
  }
}

export function requireAcyclic(node: Node): void {
  const m = membershipOf(node);
  const adj = new Map<string, string[]>();
  for (const e of m.edges) {
    const list = adj.get(e.source) ?? [];
    list.push(e.target);
    adj.set(e.source, list);
  }
  const visiting = new Set<string>();
  const done = new Set<string>();
  const walk = (n: string): void => {
    if (visiting.has(n)) throw new InvariantError(`${node.id}: cycle detected at ${n}`);
    if (done.has(n)) return;
    visiting.add(n);
    for (const nxt of adj.get(n) ?? []) walk(nxt);
    visiting.delete(n);
    done.add(n);
  };
  for (const start of [...adj.keys()]) walk(start);
}

export function requireSingleParent(node: Node): void {
  const parents = new Map<string, number>();
  for (const e of membershipOf(node).edges) {
    parents.set(e.target, (parents.get(e.target) ?? 0) + 1);
  }
  const over = [...parents.entries()]
    .filter(([, c]) => c > 1)
    .map(([t]) => t)
    .sort();
  if (over.length > 0) {
    throw new InvariantError(`${node.id}: nodes with multiple parents: ${JSON.stringify(over)}`);
  }
}

export function registerBuiltinShapes(reg: Registry): void {
  const m = () => new Set([MEMBERSHIP]);
  const specs: KindSpec[] = [
    { name: "set", requiredFacets: m(), invariants: [requireUniqueMembers] },
    { name: "list", requiredFacets: m() },
    { name: "dict", requiredFacets: m(), invariants: [requireDictKeys] },
    { name: "graph", requiredFacets: m(), invariants: [requireUniqueMembers] },
    { name: "dag", requiredFacets: m(), invariants: [requireUniqueMembers, requireAcyclic] },
    { name: "tree", requiredFacets: m(), invariants: [requireUniqueMembers, requireAcyclic, requireSingleParent] },
  ];
  for (const spec of specs) reg.register(spec);
}
