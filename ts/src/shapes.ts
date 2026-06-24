import { z } from "zod";
import { FacetError, InvariantError } from "./errors.js";
import type { Node } from "./node.js";
import type { KindSpec, Registry, ShapeSpec } from "./registry.js";
import { RelationSchema } from "./relations.js";

export const MEMBERSHIP = "membership";
export const EDGES = "edges";
export const ORDER = "order";
export const KEYS = "keys";

export const MembershipSchema = z.object({ members: z.array(z.string()).default([]) });
export const EdgesSchema = z.object({ edges: z.array(RelationSchema).default([]) });
export const OrderSchema = z.object({ order: z.array(z.string()).default([]) });
export const KeysSchema = z.object({ keys: z.record(z.string()).default({}) });

export type Membership = z.infer<typeof MembershipSchema>;
export type Edges = z.infer<typeof EdgesSchema>;
export type Order = z.infer<typeof OrderSchema>;
export type Keys = z.infer<typeof KeysSchema>;

function load<S extends z.ZodTypeAny>(node: Node, name: string, schema: S): z.output<S> {
  const raw = node.facets[name];
  if (raw === undefined) throw new FacetError(`${node.id}: missing '${name}' facet`);
  const result = schema.safeParse(raw);
  if (!result.success) {
    throw new FacetError(
      `${node.id}: invalid '${name}' facet: ${result.error.issues.map((i) => i.message).join("; ")}`,
    );
  }
  return result.data as z.output<S>;
}

export function membershipOf(node: Node): Membership {
  return load(node, MEMBERSHIP, MembershipSchema);
}
export function edgesOf(node: Node): Edges {
  return load(node, EDGES, EdgesSchema);
}
export function orderOf(node: Node): Order {
  return load(node, ORDER, OrderSchema);
}
export function keysOf(node: Node): Keys {
  return load(node, KEYS, KeysSchema);
}

export function requireUniqueMembers(node: Node): void {
  const members = membershipOf(node).members;
  if (members.length !== new Set(members).size) {
    throw new InvariantError(`${node.id}: members must be unique`);
  }
}

export function requireEdgeEndpointsAreMembers(node: Node): void {
  const members = new Set(membershipOf(node).members);
  for (const e of edgesOf(node).edges) {
    if (!members.has(e.source) || !members.has(e.target)) {
      throw new InvariantError(`${node.id}: edge endpoints must be members`);
    }
  }
}

export function requireOrderIsPermutation(node: Node): void {
  const members = membershipOf(node).members;
  const order = orderOf(node).order;
  const memberSet = new Set(members);
  const orderSet = new Set(order);
  const sameSet = memberSet.size === orderSet.size && [...memberSet].every((m) => orderSet.has(m));
  if (order.length !== members.length || !sameSet) {
    throw new InvariantError(`${node.id}: order must be a permutation of members`);
  }
}

export function requireKeyValuesAreMembers(node: Node): void {
  const members = new Set(membershipOf(node).members);
  for (const value of Object.values(keysOf(node).keys)) {
    if (!members.has(value)) {
      throw new InvariantError(`${node.id}: key values must be members`);
    }
  }
}

export function requireAcyclic(node: Node): void {
  const adj = new Map<string, string[]>();
  for (const e of edgesOf(node).edges) {
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
  for (const e of edgesOf(node).edges) {
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
  const shapes: ShapeSpec[] = [
    { name: "set", requiredFacets: new Set([MEMBERSHIP]), invariants: [requireUniqueMembers] },
    {
      name: "list",
      requiredFacets: new Set([MEMBERSHIP, ORDER]),
      invariants: [requireUniqueMembers, requireOrderIsPermutation],
    },
    {
      name: "dict",
      requiredFacets: new Set([MEMBERSHIP, KEYS]),
      invariants: [requireUniqueMembers, requireKeyValuesAreMembers],
    },
    {
      name: "graph",
      requiredFacets: new Set([MEMBERSHIP, EDGES]),
      invariants: [requireUniqueMembers, requireEdgeEndpointsAreMembers],
    },
    {
      name: "dag",
      requiredFacets: new Set([MEMBERSHIP, EDGES]),
      invariants: [requireUniqueMembers, requireEdgeEndpointsAreMembers, requireAcyclic],
    },
    {
      name: "tree",
      requiredFacets: new Set([MEMBERSHIP, EDGES]),
      invariants: [requireUniqueMembers, requireEdgeEndpointsAreMembers, requireAcyclic, requireSingleParent],
    },
  ];
  for (const shape of shapes) reg.registerShape(shape);
  for (const name of ["set", "list", "dict", "graph", "dag", "tree"]) {
    const spec: KindSpec = { name, shape: name };
    reg.register(spec);
  }
}
