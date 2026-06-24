# Structural-Shape Redesign (TypeScript Port) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the just-merged Python structural-shape redesign to the TypeScript kernel so a structure's *membership* (scope) is cleanly separated from its shape-owned *form* (`edges`/`order`/`keys`), with shapes registered as a composable trait that kinds adopt — matching the Python oracle behaviour-for-behaviour.

**Architecture:** A `Structure` is a `Node` of a registered shape carrying a scope-only `membership` facet plus the form facet(s) its shape requires. Shapes register via `ShapeSpec`; a `KindSpec` adopts ≤1 shape via `KindSpec.shape`; the `Registry` composes the shape's required/optional facets and invariants into the kind's validation. The structural index extracts refs from `membership.members` plus the built-in form facets (registry-independently) and persists them as a generic `structuralRefs` list. Rename rewrites refs across all those facets. Clean breaking change — no compatibility layer, no migration.

**Tech Stack:** TypeScript 5.5+, zod v3, vitest, biome (width 120). Source under `~/d/nodes/ts/src/`, tests under `~/d/nodes/ts/tests/`. All commands run from `~/d/nodes/ts` via the `rtk` wrapper.

This is **Plan A-ts**, the second of three plans for mindful v6 SP1 (spec: `~/d/nodes/docs/specs/2026-06-23-mindful-v6-sp1-abstraction-design.md`, Part A). Plan A-py (Python) is **already merged** (`main` @ `a7dd55b`) and is the **oracle** for this port. Plan B (the mindful package) follows. The mindful package is not scaffolded until both kernels match.

## The Oracle

The Python kernel on `main` is the source of truth. For each task, the corresponding Python file is the behavioural reference — when this plan says "mirror the oracle," read it:

- Registry: `~/d/nodes/python/src/nodes/kernel/registry.py`
- Shapes: `~/d/nodes/python/src/nodes/kernel/shapes.py`
- Structural index: `~/d/nodes/python/src/nodes/kernel/index.py`
- Corpus rename: `~/d/nodes/python/src/nodes/kernel/corpus.py` (`_rewrite_refs`, lines 25–51)

This plan contains the full TypeScript for every changed function. The oracle is the cross-check for parity, not a substitute for the code below.

## Global Constraints

- **Structure contract:** `Structure = shape/kind + membership facet + shape-specific form facet(s)`. `Relation` is the universal **binary** primitive, but `Structure` is NOT defined in terms of it.
- **Membership = scope only:** `{ members: string[] }`, a unique unordered set. Order/edges/keys live in form facets — never leak through `membership.members` position.
- **Form is shape-owned:** each registered shape declares the form facet(s) it requires, its invariants, and any predicates it uses. Unknown shape or malformed form **fails early** (typed `FacetError`/`InvariantError`, never a raw `ZodError`).
- **Built-in shapes:** `set, list, dict, graph, dag, tree` — all six stay in scope.
- **Duplicate names fail early:** `registerShape` rejects a duplicate shape name (`ValidationError`); `register` rejects a duplicate kind name (`ValidationError`) and a kind adopting an unknown shape (`UnknownKindError`). Shape and kind namespaces are **separate** (a `graph` shape and a `graph` kind coexist).
- **Structure refs vs global graph:** structure refs (`members`/edges/`order`/`keys` values) are tracked for **rename + snapshot integrity** but are **never** exposed through `Corpus.outbound`/`inbound`/`neighbors`/`dangling`. Only top-level `relations:` feed the global relation graph.
- **No-registry recognition:** the built-in structural facets (`membership`/`edges`/`order`/`keys`) are recognized for ref rewriting + index extraction **with or without** a registry. Rename never skips a known structural ref for lack of a registry.
- **Clean breaking change:** no compat layer, no migration. No backward-compat reading of the old bundled `membership: { shape, members, edges }` facet.
- **Singular shape:** a kind adopts zero or one shape (`KindSpec.shape?: string`).
- **Snapshot key casing:** the TS snapshot uses **camelCase** keys on disk (`deprecatedIds`, etc.). The new structural-refs container key is therefore **`structuralRefs`** (NOT `structural_refs`). The **role string values** (`relation_source`, `membership_member`, `edges_source`, `edges_target`, `order_member`, `keys_value`) are snake-case literals identical to Python's — they are the shared role vocabulary.
- **Parity is behavioural, not byte-identical:** the TS and Python snapshots are separate files (`snapshot.ts.json` vs `snapshot.py.json`); key casing differs by language. The one cross-language fixture parity is `corpus_parity.test.ts` against the shared `fixtures/` oracle (see Baseline).
- **Gate (run from `~/d/nodes/ts`):** `rtk npm test` (vitest), `rtk npm run typecheck` (`tsc --noEmit`), `rtk npm run check` (biome) must all pass before a task is complete — subject to the per-task baseline below.

## Baseline — the suite is NOT fully green at the start

The A-py merge migrated the **shared** top-level `fixtures/corpus/graph/g.md` and `fixtures/corpus.rename.canonical.json` to the new split-facet model. `ts/tests/corpus_parity.test.ts` reads that shared `fixtures/` dir, so **on `main` (`a7dd55b`) the TS suite has exactly one pre-existing failure**:

```
FAIL tests/corpus_parity.test.ts > TS Corpus.rename over the fixture corpus matches the shared oracle
Tests  1 failed | 269 passed (270)
```

This is expected: the shared oracle requires split-facet rename rewriting that TS `corpus.ts` does not yet do. **Task 4 fixes it.** Per-task expected suite state:

| After task | Expected `rtk npm test` | Notes |
|---|---|---|
| (baseline) | 1 failed (`corpus_parity`), 269 passed | pre-existing |
| Task 1 (registry) | 1 failed (`corpus_parity`), rest passed | + new registry tests |
| Task 2 (shapes) | 1 failed (`corpus_parity`), rest passed | shapes + corpus validation tests migrated |
| Task 3 (index) | 1 failed (`corpus_parity`), rest passed | index tests migrated |
| Task 4 (corpus) | **0 failed, all passed** | `corpus_parity` goes green |
| Task 5 (finalize) | 0 failed, all passed | barrel/vocab/docs |

`tsc --noEmit` and `biome` must be **fully clean after every task** (a compile error or lint error is never an acceptable intermediate state — only the one named runtime test failure is). Each task that removes or renames an exported symbol MUST update the barrel `ts/src/index.ts` in the same task so `tsc` stays clean.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `ts/src/registry.ts` | `ShapeSpec`/`KindSpec.shape` + shape registration + composing `validate` | 1 |
| `ts/src/shapes.ts` | facet constants/schemas + accessors + invariants + `registerBuiltinShapes` | 2 |
| `ts/src/structural-index.ts` | `Role`, ref extraction, generic `structuralRefs` persistence | 3 |
| `ts/src/corpus.ts` | `rewriteRefs` across all form facets | 4 |
| `ts/src/index.ts` (barrel) | public export surface | 1, 2, 3, 5 |
| `ts/src/vocab/kinds.ts` | JSDoc comment (cosmetic) | 5 |
| `ts/tests/registry.test.ts` | registry tests | 1 |
| `ts/tests/shapes.test.ts` | shapes tests (full rewrite) | 2 |
| `ts/tests/corpus.test.ts` | shape-validation tests (T2) + rename tests (T4) | 2, 4 |
| `ts/tests/structural-index.test.ts` | the membership-not-graph-edge test | 3 |
| `ts/tests/index-snapshot.test.ts` | `seed()` fixture + round-trip | 3 |
| `ts/tests/index-rebuild-equivalence.test.ts` | add/rename/delete fixture | 3 |
| `ts/tests/corpus_parity.test.ts` | cross-language no-registry rename (goes green) | 4 (verify) |
| `ts/tests/smoke.test.ts` | barrel re-export smoke | 5 (verify) |

---

### Task 1: Registry — `ShapeSpec`, `KindSpec.shape`, composition, duplicate rejection

**Files:**
- Modify: `ts/src/registry.ts`
- Modify: `ts/src/index.ts` (barrel — export `ShapeSpec`)
- Test: `ts/tests/registry.test.ts`

**Interfaces:**
- Consumes: `Node` (`./node.js`); errors `FacetError`/`UnknownKindError`/`ValidationError` (`./errors.js` — all three already exist).
- Produces:
  - `interface ShapeSpec { name: string; requiredFacets?: Set<string>; optionalFacets?: Set<string>; invariants?: Invariant[]; }`
  - `KindSpec` gains `shape?: string`.
  - `Registry.registerShape(spec: ShapeSpec): void` — duplicate shape name → `ValidationError`.
  - `Registry.isShape(name: string): boolean`.
  - `Registry.register(spec: KindSpec): void` — now rejects a duplicate kind name (`ValidationError`) and an unknown adopted shape (`UnknownKindError`).
  - `Registry.validate(node)` composes shape + kind required/optional facets and runs shape invariants **then** kind invariants.

This mirrors `registry.py` (oracle) lines 13–83.

- [ ] **Step 1: Write the failing tests**

Append to `ts/tests/registry.test.ts` (the file already imports `FacetError`, `InvariantError`, `UnknownKindError`, `makeNode`, `Registry`, and defines `node(facets)`):

```ts
import { ValidationError } from "../src/errors.js";
import { Registry } from "../src/registry.js";

// The file's existing `node(facets)` helper hard-codes kind "k"; these tests register
// kinds named `mindmap`/`graph`/`topic`, so they need a builder whose kind matches.
function knode(kind: string, facets: Record<string, Record<string, unknown>>) {
  return makeNode({ id: `${kind}:1`, kind, title: "T", facets });
}

describe("Registry — shapes", () => {
  it("registerShape rejects a duplicate shape name", () => {
    const reg = new Registry();
    reg.registerShape({ name: "graph", requiredFacets: new Set(["membership"]) });
    expect(() => reg.registerShape({ name: "graph" })).toThrow(ValidationError);
  });

  it("register rejects a duplicate kind name", () => {
    const reg = new Registry();
    reg.register({ name: "topic" });
    expect(() => reg.register({ name: "topic" })).toThrow(ValidationError);
  });

  it("register rejects a kind adopting an unknown shape", () => {
    const reg = new Registry();
    expect(() => reg.register({ name: "mindmap", shape: "graph" })).toThrow(UnknownKindError);
  });

  it("a shape and a kind may share a name (separate namespaces)", () => {
    const reg = new Registry();
    reg.registerShape({ name: "graph", requiredFacets: new Set(["membership"]) });
    reg.register({ name: "graph", shape: "graph" });
    expect(reg.isShape("graph")).toBe(true);
    expect(reg.isRegistered("graph")).toBe(true);
  });

  it("validate composes shape + kind required facets", () => {
    const reg = new Registry();
    reg.registerShape({ name: "graph", requiredFacets: new Set(["membership"]) });
    reg.register({ name: "mindmap", shape: "graph", requiredFacets: new Set(["scene"]) });
    expect(() => reg.validate(knode("mindmap", { membership: { members: [] }, scene: { x: 1 } }))).not.toThrow();
    expect(() => reg.validate(knode("mindmap", { membership: { members: [] } }))).toThrow(FacetError);
  });

  it("validate runs shape invariants before kind invariants", () => {
    const order: string[] = [];
    const reg = new Registry();
    reg.registerShape({
      name: "graph",
      requiredFacets: new Set(["membership"]),
      invariants: [() => void order.push("shape")],
    });
    reg.register({ name: "mindmap", shape: "graph", invariants: [() => void order.push("kind")] });
    reg.validate(knode("mindmap", { membership: { members: [] } }));
    expect(order).toEqual(["shape", "kind"]);
  });
});
```

(`FacetError`, `UnknownKindError`, `makeNode` are already imported at the top of `registry.test.ts`; add only `ValidationError` and `knode`. `ShapeSpec` is not needed as a value import — the specs are object literals.)

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd ~/d/nodes/ts && rtk npx vitest run tests/registry.test.ts`
Expected: FAIL — `registerShape`/`isShape`/`shape`/dup-rejection do not exist yet (type errors / thrown-type mismatches).

- [ ] **Step 3: Implement the registry changes**

Replace the body of `ts/src/registry.ts` with (mirrors `registry.py`):

```ts
import { FacetError, UnknownKindError, ValidationError } from "./errors.js";
import type { Node } from "./node.js";

export type Invariant = (node: Node) => void;

export interface ShapeSpec {
  name: string;
  requiredFacets?: Set<string>;
  optionalFacets?: Set<string>;
  invariants?: Invariant[];
}

export interface KindSpec {
  name: string;
  shape?: string;
  requiredFacets?: Set<string>;
  optionalFacets?: Set<string>;
  invariants?: Invariant[];
}

export class Registry {
  private specs = new Map<string, KindSpec>();
  private shapes = new Map<string, ShapeSpec>();

  registerShape(spec: ShapeSpec): void {
    if (this.shapes.has(spec.name)) {
      throw new ValidationError(`shape ${JSON.stringify(spec.name)} is already registered`);
    }
    this.shapes.set(spec.name, spec);
  }

  isShape(name: string): boolean {
    return this.shapes.has(name);
  }

  register(spec: KindSpec): void {
    if (this.specs.has(spec.name)) {
      throw new ValidationError(`kind ${JSON.stringify(spec.name)} is already registered`);
    }
    if (spec.shape !== undefined && !this.shapes.has(spec.shape)) {
      throw new UnknownKindError(
        `kind ${JSON.stringify(spec.name)} adopts unknown shape ${JSON.stringify(spec.shape)}`,
      );
    }
    this.specs.set(spec.name, spec);
  }

  isRegistered(kind: string): boolean {
    return this.specs.has(kind);
  }

  get(kind: string): KindSpec {
    const spec = this.specs.get(kind);
    if (spec === undefined) {
      throw new UnknownKindError(`kind ${JSON.stringify(kind)} is not registered`);
    }
    return spec;
  }

  validate(node: Node): void {
    const spec = this.get(node.kind);
    const required = new Set(spec.requiredFacets ?? []);
    const optional = new Set(spec.optionalFacets ?? []);
    const invariants: Invariant[] = [];
    if (spec.shape !== undefined) {
      const shape = this.shapes.get(spec.shape) as ShapeSpec;
      for (const f of shape.requiredFacets ?? []) required.add(f);
      for (const f of shape.optionalFacets ?? []) optional.add(f);
      for (const inv of shape.invariants ?? []) invariants.push(inv);
    }
    for (const inv of spec.invariants ?? []) invariants.push(inv);

    const present = new Set(Object.keys(node.facets));
    const missing = [...required].filter((f) => !present.has(f)).sort();
    if (missing.length > 0) {
      throw new FacetError(`${node.id}: missing required facets ${JSON.stringify(missing)}`);
    }
    const allowed = new Set([...required, ...optional]);
    const unexpected = [...present].filter((f) => !allowed.has(f)).sort();
    if (unexpected.length > 0) {
      throw new FacetError(`${node.id}: unexpected facets ${JSON.stringify(unexpected)}`);
    }
    for (const invariant of invariants) invariant(node);
  }
}
```

- [ ] **Step 4: Export `ShapeSpec` from the barrel**

In `ts/src/index.ts`, find the `export { ... } from "./registry.js"` / `export type { ... } from "./registry.js"` line(s) and add `ShapeSpec` to the exported types (alongside `KindSpec`, `Invariant`, `Registry`). Do not remove anything.

- [ ] **Step 5: Run the registry tests, then the full gate**

Run: `cd ~/d/nodes/ts && rtk npx vitest run tests/registry.test.ts`
Expected: PASS (all registry tests).

Run: `rtk npm run typecheck && rtk npm run check && rtk npm test`
Expected: `tsc` clean, biome clean. `rtk npm test` → **1 failed (`corpus_parity`), rest passed** (the documented baseline; no new failures).

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes && rtk git add ts/src/registry.ts ts/src/index.ts ts/tests/registry.test.ts
rtk git commit -m "feat(shapes-ts): ShapeSpec + KindSpec.shape composition with dup-name rejection"
```

---

### Task 2: Shapes — scope-only membership, form facets, invariants, built-ins

**Files:**
- Rewrite: `ts/src/shapes.ts`
- Modify: `ts/src/index.ts` (barrel — replace shape exports)
- Rewrite: `ts/tests/shapes.test.ts`
- Modify: `ts/tests/corpus.test.ts` (migrate the shape-VALIDATION tests only)
- Test: `ts/tests/shapes.test.ts`

**Interfaces:**
- Consumes: `ShapeSpec`/`KindSpec`/`Registry` (Task 1); `RelationSchema`/`Relation` (`./relations.js`); `FacetError`/`InvariantError` (`./errors.js`).
- Produces (mirrors `shapes.py`):
  - Constants `MEMBERSHIP = "membership"`, `EDGES = "edges"`, `ORDER = "order"`, `KEYS = "keys"`.
  - Schemas `MembershipSchema` (`{ members: string[] }`), `EdgesSchema` (`{ edges: Relation[] }`), `OrderSchema` (`{ order: string[] }`), `KeysSchema` (`{ keys: Record<string,string> }`); types `Membership`/`Edges`/`Order`/`Keys`.
  - Accessors `membershipOf`/`edgesOf`/`orderOf`/`keysOf`, each wrapping a `ZodError` as `FacetError`.
  - Invariants `requireUniqueMembers`, `requireEdgeEndpointsAreMembers`, `requireOrderIsPermutation`, `requireKeyValuesAreMembers`, `requireAcyclic`, `requireSingleParent`.
  - `registerBuiltinShapes(reg: Registry): void` — registers 6 `ShapeSpec`s + 6 convenience shape-kinds.
- **Removed** (no compat): old bundled `MembershipSchema` (`{ shape, members, edges }`), `memberIds`, `requireDictKeys`.

- [ ] **Step 1: Write the failing tests (full rewrite of `shapes.test.ts`)**

Replace the entire contents of `ts/tests/shapes.test.ts` with (mirrors `python/tests/test_shapes.py`, including the two fix-wave tests `test_tree_rejects_cycle` and the isolated list duplicate-members test):

```ts
import { describe, expect, it } from "vitest";
import { FacetError, InvariantError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { Registry } from "../src/registry.js";
import {
  EDGES,
  KEYS,
  MEMBERSHIP,
  ORDER,
  edgesOf,
  keysOf,
  membershipOf,
  orderOf,
  registerBuiltinShapes,
  requireUniqueMembers,
} from "../src/shapes.js";

function reg(): Registry {
  const r = new Registry();
  registerBuiltinShapes(r);
  return r;
}

function struct(kind: string, facets: Record<string, Record<string, unknown>>) {
  return makeNode({ id: `${kind}:1`, kind, title: "S", facets });
}

function edge(source: string, target: string) {
  return { source, predicate: "to", target };
}

describe("shapes — facet accessors", () => {
  it("membershipOf throws FacetError when the facet is absent", () => {
    expect(() => membershipOf(makeNode({ id: "set:1", kind: "set", title: "S" }))).toThrow(FacetError);
  });

  it("membershipOf defaults members to empty", () => {
    expect(membershipOf(struct("set", { [MEMBERSHIP]: {} })).members).toEqual([]);
  });

  it("each accessor wraps a malformed facet as FacetError", () => {
    expect(() => membershipOf(struct("set", { [MEMBERSHIP]: { members: [1] } }))).toThrow(FacetError);
    expect(() => orderOf(struct("list", { [ORDER]: { order: [1] } }))).toThrow(FacetError);
    expect(() => keysOf(struct("dict", { [KEYS]: { keys: { a: 1 } } }))).toThrow(FacetError);
    expect(() => edgesOf(struct("graph", { [EDGES]: { edges: [{ source: 1 }] } }))).toThrow(FacetError);
  });
});

describe("shapes — built-in validation", () => {
  it("set requires membership only and rejects duplicates", () => {
    expect(() => reg().validate(struct("set", { [MEMBERSHIP]: { members: ["a:1"] } }))).not.toThrow();
    expect(() =>
      reg().validate(struct("set", { [MEMBERSHIP]: { members: ["a:1", "a:1"] } })),
    ).toThrow(InvariantError);
  });

  it("set rejects form facets it does not own", () => {
    expect(() =>
      reg().validate(struct("set", { [MEMBERSHIP]: { members: ["a:1"] }, [ORDER]: { order: ["a:1"] } })),
    ).toThrow(FacetError);
  });

  it("list requires order to be a permutation of members", () => {
    expect(() =>
      reg().validate(struct("list", { [MEMBERSHIP]: { members: ["a:1", "a:2"] }, [ORDER]: { order: ["a:2", "a:1"] } })),
    ).not.toThrow();
    expect(() =>
      reg().validate(struct("list", { [MEMBERSHIP]: { members: ["a:1", "a:2"] }, [ORDER]: { order: ["a:1"] } })),
    ).toThrow(InvariantError);
  });

  it("list rejects duplicate members (isolated from the permutation check)", () => {
    // duplicate members, but order is NOT itself duplicated: requireUniqueMembers fires first.
    expect(() =>
      reg().validate(struct("list", { [MEMBERSHIP]: { members: ["a:1", "a:1"] }, [ORDER]: { order: ["a:1"] } })),
    ).toThrow(InvariantError);
  });

  it("list missing the order facet is rejected", () => {
    expect(() => reg().validate(struct("list", { [MEMBERSHIP]: { members: ["a:1"] } }))).toThrow(FacetError);
  });

  it("dict requires key values to be members", () => {
    expect(() =>
      reg().validate(struct("dict", { [MEMBERSHIP]: { members: ["a:1"] }, [KEYS]: { keys: { label: "a:1" } } })),
    ).not.toThrow();
    expect(() =>
      reg().validate(struct("dict", { [MEMBERSHIP]: { members: ["a:1"] }, [KEYS]: { keys: { label: "a:2" } } })),
    ).toThrow(InvariantError);
  });

  it("graph requires edge endpoints to be members", () => {
    expect(() =>
      reg().validate(struct("graph", { [MEMBERSHIP]: { members: ["a:1", "a:2"] }, [EDGES]: { edges: [edge("a:1", "a:2")] } })),
    ).not.toThrow();
    expect(() =>
      reg().validate(struct("graph", { [MEMBERSHIP]: { members: ["a:1"] }, [EDGES]: { edges: [edge("a:1", "a:2")] } })),
    ).toThrow(InvariantError);
  });

  it("dag rejects a cycle", () => {
    expect(() =>
      reg().validate(
        struct("dag", { [MEMBERSHIP]: { members: ["a:1", "a:2"] }, [EDGES]: { edges: [edge("a:1", "a:2"), edge("a:2", "a:1")] } }),
      ),
    ).toThrow(InvariantError);
  });

  it("dag accepts a diamond (shared sink reached by two paths)", () => {
    expect(() =>
      reg().validate(
        struct("dag", {
          [MEMBERSHIP]: { members: ["a:1", "a:2", "a:3", "a:4"] },
          [EDGES]: { edges: [edge("a:1", "a:2"), edge("a:1", "a:3"), edge("a:2", "a:4"), edge("a:3", "a:4")] },
        }),
      ),
    ).not.toThrow();
  });

  it("tree rejects multiple parents of one target", () => {
    expect(() =>
      reg().validate(
        struct("tree", { [MEMBERSHIP]: { members: ["a:1", "a:2", "a:3"] }, [EDGES]: { edges: [edge("a:1", "a:3"), edge("a:2", "a:3")] } }),
      ),
    ).toThrow(InvariantError);
  });

  it("tree rejects a cycle (acyclic failure path on the full tree stack)", () => {
    // each node has in-degree 1 so requireSingleParent passes; the cycle trips requireAcyclic
    // (which runs before requireSingleParent).
    expect(() =>
      reg().validate(
        struct("tree", { [MEMBERSHIP]: { members: ["a:1", "a:2"] }, [EDGES]: { edges: [edge("a:1", "a:2"), edge("a:2", "a:1")] } }),
      ),
    ).toThrow(InvariantError);
  });

  it("registerBuiltinShapes wires all six shapes and kinds", () => {
    const r = reg();
    for (const k of ["set", "list", "dict", "graph", "dag", "tree"]) {
      expect(r.isShape(k)).toBe(true);
      expect(r.isRegistered(k)).toBe(true);
    }
  });

  it("a standalone invariant is callable on a node", () => {
    expect(() => requireUniqueMembers(struct("set", { [MEMBERSHIP]: { members: ["a:1", "a:1"] } }))).toThrow(
      InvariantError,
    );
  });
});
```

- [ ] **Step 2: Run the shapes tests to verify they fail**

Run: `cd ~/d/nodes/ts && rtk npx vitest run tests/shapes.test.ts`
Expected: FAIL — `EDGES`/`ORDER`/`KEYS`/`edgesOf`/`orderOf`/`keysOf` and the new schemas do not exist; `registerBuiltinShapes` does not register shapes yet.

- [ ] **Step 3: Rewrite `ts/src/shapes.ts`**

Replace the entire contents with (mirrors `shapes.py`):

```ts
import { z } from "zod";
import { FacetError, InvariantError } from "./errors.js";
import type { Node } from "./node.js";
import { type KindSpec, type Registry, type ShapeSpec } from "./registry.js";
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

function load<T>(node: Node, name: string, schema: z.ZodType<T>): T {
  const raw = node.facets[name];
  if (raw === undefined) throw new FacetError(`${node.id}: missing '${name}' facet`);
  const result = schema.safeParse(raw);
  if (!result.success) {
    throw new FacetError(`${node.id}: invalid '${name}' facet: ${result.error.issues.map((i) => i.message).join("; ")}`);
  }
  return result.data;
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
```

Note: `z.record(z.string())` types as `Record<string, string>`, the `keys` map. `RelationSchema` is imported as a value (used by `EdgesSchema`); the `Relation` type is NOT imported here (it would be an unused import — biome would flag it). Confirm the gate is clean.

- [ ] **Step 4: Update the barrel `ts/src/index.ts`**

In `ts/src/index.ts`, the `export { ... } from "./shapes.js"` block currently re-exports `MEMBERSHIP`, `MembershipSchema`, `type Membership`, `membershipOf`, `registerBuiltinShapes`, `requireAcyclic`, `requireDictKeys`, `requireSingleParent`, `requireUniqueMembers`. Replace that block so it exports the new surface:

```ts
export {
  EDGES,
  EdgesSchema,
  KEYS,
  KeysSchema,
  MEMBERSHIP,
  MembershipSchema,
  ORDER,
  OrderSchema,
  edgesOf,
  keysOf,
  membershipOf,
  orderOf,
  registerBuiltinShapes,
  requireAcyclic,
  requireEdgeEndpointsAreMembers,
  requireKeyValuesAreMembers,
  requireOrderIsPermutation,
  requireSingleParent,
  requireUniqueMembers,
} from "./shapes.js";
export type { Edges, Keys, Membership, Order } from "./shapes.js";
```

(Match the existing barrel's `export { ... }` vs `export type { ... }` split conventions. `requireDictKeys` and the old bundled `Membership` are removed.)

- [ ] **Step 5: Migrate the shape-VALIDATION tests in `ts/tests/corpus.test.ts`**

These tests construct shape nodes with the OLD bundled membership and exercise `registerBuiltinShapes` validation. They break under the new validation. Migrate ONLY these (leave the rename-rewrite tests at L138–179 for Task 4):

- The `shapeRegistry()` helper (≈L110–114) calls `registerBuiltinShapes(r)` — unchanged, still valid.
- `"a registry rejects an invalid node on add, writing no file"` (≈L256–276): change the `dag:d` node's facets from
  `{ membership: { shape: "dag", members: [...], edges: [cycle] } }` to
  `{ membership: { members: ["a:1", "a:2"] }, edges: { edges: [edge("a:1","a:2"), edge("a:2","a:1")] } }`
  (a real cycle, so `requireAcyclic` rejects). Use a local `edge(s,t)` helper or inline `{ source, predicate: "e", target }`.
- `"a registry accepts a valid node on add"` (≈L278–284): change `{ membership: { shape: "set", members: ["a:1"] } }` to `{ membership: { members: ["a:1"] } }`.
- `"rename validates the renamed node before any write (no partial rename)"` (≈L286–303): change the `set:s` node `{ membership: { shape: "set", members: ["a:1","a:1"] } }` to `{ membership: { members: ["a:1","a:1"] } }` (duplicate members → `requireUniqueMembers` rejects).
- `"rename blocked by an invalid referrer writes nothing"` (≈L305–336): change the `dag:bad` node `{ membership: { shape: "dag", members: ["a:1"], edges: [self-cycle] } }` to `{ membership: { members: ["a:1"] }, edges: { edges: [{ source: "a:1", predicate: "e", target: "a:1" }] } }` (self-cycle → `requireAcyclic` rejects; note `a:1` is its own endpoint so it is a member).

Read each test before editing and preserve its surrounding assertions (file-not-written checks etc.) verbatim — change only the facet literals.

- [ ] **Step 6: Run the affected tests, then the full gate**

Run: `cd ~/d/nodes/ts && rtk npx vitest run tests/shapes.test.ts tests/corpus.test.ts`
Expected: PASS (shapes fully; corpus.test.ts — the migrated validation tests pass, the not-yet-migrated rename tests at L138–179 still pass because `rewriteRefs` is unchanged and they still use bundled membership).

Run: `rtk npm run typecheck && rtk npm run check && rtk npm test`
Expected: `tsc` clean, biome clean. `rtk npm test` → 1 failed (`corpus_parity`), rest passed (baseline unchanged).

- [ ] **Step 7: Commit**

```bash
cd ~/d/nodes && rtk git add ts/src/shapes.ts ts/src/index.ts ts/tests/shapes.test.ts ts/tests/corpus.test.ts
rtk git commit -m "feat(shapes-ts): scope-only membership + edges/order/keys form facets + built-in shapes"
```

---

### Task 3: Structural index — form-facet ref extraction + generic `structuralRefs` persistence

**Files:**
- Modify: `ts/src/structural-index.ts`
- Test: `ts/tests/structural-index.test.ts`, `ts/tests/index-snapshot.test.ts`, `ts/tests/index-rebuild-equivalence.test.ts`

**Interfaces:**
- Consumes: `MEMBERSHIP`/`EDGES`/`ORDER`/`KEYS` (Task 2); `Relation`/`RelationSchema` (`./relations.js`); errors.
- Produces (mirrors `index.py`):
  - `Role` = `"relation_source" | "relation_target" | "membership_member" | "edges_source" | "edges_target" | "order_member" | "keys_value"`.
  - `OutRef { ref: string; role: Role; relation?: Relation }` (unchanged shape; `relation` present iff role starts with `relation_`).
  - `IndexEntry` **drops** the `membership?` field (carries `outRefs` only, as before).
  - `relationOutRefs(relations)`, `structuralOutRefs(node)` (reads `node.facets` directly, registry-independent), `extractOutRefs(node)`.
  - `validatedStructuralRefs(raw)` — replaces `validatedMembership`.
  - `toDict` emits `structuralRefs: [{ ref, role }]` per entry (no `membership`); `fromDict` rebuilds out-refs from `relations` + `structuralRefs`; the required-key list becomes `["uid","id","kind","deprecatedIds","relations","structuralRefs"]`.

This mirrors `index.py` lines 17–141, 211–315. The class methods `build`/`resolveUid`/`assertAddable`/`upsert`/`remove`/`drop`/`refsForUid`/`resolveEdge`/`relationsByRole`/`outboundEdges`/`inboundEdges`/`danglingEdges` are **unchanged** except where they reference `membership` or the old roles — see below.

- [ ] **Step 1: Migrate the index tests (write the new expectations first)**

**`ts/tests/structural-index.test.ts`** — replace the test `"membership members/edges are tracked but are NOT public graph edges"` (L144–163) with a split-facet version that also exercises `order`/`keys` roles:

```ts
  it("structure-facet refs are tracked but are NOT public graph edges", () => {
    const g = makeNode({
      id: "graph:g",
      kind: "graph",
      title: "G",
      facets: {
        membership: { members: ["topic:x"] },
        edges: { edges: [{ source: "topic:x", predicate: "to", target: "topic:y" }] },
      },
    });
    const x = makeNode({ id: "topic:x", kind: "topic", title: "X" });
    const y = makeNode({ id: "topic:y", kind: "topic", title: "Y" });
    const idx = Index.build([g, x, y]);
    // structural refs register as inbound refs (for rename) ...
    expect((idx.inRefs.get("topic:x") ?? []).some((r) => r.sourceUid === g.uid)).toBe(true);
    expect((idx.inRefs.get("topic:y") ?? []).some((r) => r.sourceUid === g.uid)).toBe(true);
    // ... but never as graph edges.
    expect(idx.outboundEdges(g.uid)).toEqual([]);
    expect(idx.inboundEdges(y.uid)).toEqual([]);
    expect(idx.danglingEdges()).toEqual([]);
  });
```

**`ts/tests/index-snapshot.test.ts`** — replace the `seed()` helper's bundled `graph:g` facet with split facets, and add `list`/`dict` nodes so the round-trip witnesses every structural role. Replace `seed()` (L38–55) with:

```ts
function seed(): Index {
  return Index.build([
    makeNode({ id: "topic:a", kind: "topic", title: "A", relations: [relatesTo("topic:a", "topic:b")] }),
    makeNode({ id: "topic:b", kind: "topic", title: "B", deprecatedIds: ["topic:bb"] }),
    makeNode({
      id: "graph:g",
      kind: "graph",
      title: "G",
      facets: {
        membership: { members: ["topic:a", "topic:missing"] },
        edges: { edges: [{ source: "topic:a", predicate: "to", target: "topic:b" }] },
      },
    }),
    makeNode({
      id: "list:l",
      kind: "list",
      title: "L",
      facets: { membership: { members: ["topic:a"] }, order: { order: ["topic:a"] } },
    }),
    makeNode({
      id: "dict:d",
      kind: "dict",
      title: "D",
      facets: { membership: { members: ["topic:a"] }, keys: { keys: { label: "topic:a" } } },
    }),
  ]);
}
```

Update the comment at L70 (mentions `membership_member role`) to reference the structural roles generically. The 7 existing snapshot tests (`round-trips`, `preserves shared-Relation identity`, `rejects a duplicate uid`, `rejects an entry whose id kind disagrees`, `rejects a deprecated id equal to the live id`, `rejects an identity claim already in use`, `round-trips an empty index`) all keep working through `normalize()` (which is role-agnostic) — do not change their bodies. Add one new test pinning the new persisted key:

```ts
  it("persists structural refs under structuralRefs (not membership) for every role", () => {
    const d = seed().toDict();
    for (const entry of d.entries) {
      expect("membership" in entry).toBe(false);
      expect(Array.isArray(entry.structuralRefs)).toBe(true);
    }
    const allRoles = new Set(d.entries.flatMap((e) => e.structuralRefs.map((r) => r.role)));
    expect(allRoles).toContain("membership_member");
    expect(allRoles).toContain("edges_source");
    expect(allRoles).toContain("edges_target");
    expect(allRoles).toContain("order_member");
    expect(allRoles).toContain("keys_value");
  });
```

**`ts/tests/index-rebuild-equivalence.test.ts`** — the `graph:g` fixture (≈L62–77) uses bundled membership. Change its facets to split form:

```ts
      facets: {
        membership: { members: ["topic:a", "topic:b"] },
        edges: { edges: [{ source: "topic:a", predicate: "to", target: "topic:b" }] },
      },
```

(Keep the rest of the add/rename/delete/re-add sequence and the equivalence assertion unchanged. Equivalence holds because both the add-built and snapshot-rebuilt indices derive deterministically from the same on-disk state.)

- [ ] **Step 2: Run the index tests to verify they fail**

Run: `cd ~/d/nodes/ts && rtk npx vitest run tests/structural-index.test.ts tests/index-snapshot.test.ts tests/index-rebuild-equivalence.test.ts`
Expected: FAIL — the new structural-roles test and the `structuralRefs` persistence test fail (old code emits `membership`, lacks `edges_source`/`order_member`/`keys_value` roles).

- [ ] **Step 3: Update `ts/src/structural-index.ts`**

3a. **Role type** (replace lines 7–12):

```ts
export type Role =
  | "relation_source"
  | "relation_target"
  | "membership_member"
  | "edges_source"
  | "edges_target"
  | "order_member"
  | "keys_value";

const STRUCTURAL_ENTRY_KEYS = ["uid", "id", "kind", "deprecatedIds", "relations", "structuralRefs"] as const;
const STRUCTURAL_REF_ROLES = new Set<Role>([
  "membership_member",
  "edges_source",
  "edges_target",
  "order_member",
  "keys_value",
]);
```

3b. **Imports** (line 5): change `import { MEMBERSHIP } from "./shapes.js";` to `import { EDGES, KEYS, MEMBERSHIP, ORDER } from "./shapes.js";`

3c. **`IndexEntry`** (lines 25–32): remove the `membership?: Record<string, unknown>;` field. The interface becomes `{ uid; id; kind; deprecatedIds; outRefs }`.

3d. **Replace `outRefsFrom` + `extractOutRefs`** (lines 43–75) with `relationOutRefs` + `structuralOutRefs` + `extractOutRefs` (mirrors `index.py` 60–102):

```ts
function relationOutRefs(relations: Relation[]): OutRef[] {
  const refs: OutRef[] = [];
  for (const rel of relations) {
    refs.push({ ref: rel.source, role: "relation_source", relation: rel });
    refs.push({ ref: rel.target, role: "relation_target", relation: rel });
  }
  return refs;
}

// Refs from the built-in structural facets. Read directly from `node.facets`
// (registry-independent); they populate `inRefs` for rename + dangling integrity but
// are never relation-graph edges (their `relation` stays undefined).
function structuralOutRefs(node: Node): OutRef[] {
  const refs: OutRef[] = [];
  const mem = node.facets[MEMBERSHIP];
  if (mem !== null && typeof mem === "object") {
    const members = (mem as Record<string, unknown>).members;
    if (Array.isArray(members)) {
      for (const m of members) if (typeof m === "string") refs.push({ ref: m, role: "membership_member" });
    }
  }
  const eg = node.facets[EDGES];
  if (eg !== null && typeof eg === "object") {
    const edges = (eg as Record<string, unknown>).edges;
    if (Array.isArray(edges)) {
      for (const edge of edges) {
        if (edge !== null && typeof edge === "object") {
          const e = edge as Record<string, unknown>;
          if (typeof e.source === "string") refs.push({ ref: e.source, role: "edges_source" });
          if (typeof e.target === "string") refs.push({ ref: e.target, role: "edges_target" });
        }
      }
    }
  }
  const od = node.facets[ORDER];
  if (od !== null && typeof od === "object") {
    const order = (od as Record<string, unknown>).order;
    if (Array.isArray(order)) {
      for (const m of order) if (typeof m === "string") refs.push({ ref: m, role: "order_member" });
    }
  }
  const ky = node.facets[KEYS];
  if (ky !== null && typeof ky === "object") {
    const keys = (ky as Record<string, unknown>).keys;
    if (keys !== null && typeof keys === "object") {
      for (const v of Object.values(keys as Record<string, unknown>)) {
        if (typeof v === "string") refs.push({ ref: v, role: "keys_value" });
      }
    }
  }
  return refs;
}

function extractOutRefs(node: Node): OutRef[] {
  return [...relationOutRefs(node.relations), ...structuralOutRefs(node)];
}
```

3e. **Replace `validatedMembership`** (lines 109–147) with `validatedStructuralRefs` (mirrors `index.py` 127–141):

```ts
function validatedStructuralRefs(raw: unknown): OutRef[] {
  if (!Array.isArray(raw)) throw new Error("structural snapshot: structuralRefs must be an array");
  const out: OutRef[] = [];
  for (const item of raw) {
    if (item === null || typeof item !== "object")
      throw new Error("structural snapshot: structuralRef must be an object");
    const { ref, role } = item as Record<string, unknown>;
    if (typeof ref !== "string") throw new Error("structural snapshot: structuralRef ref must be a string");
    if (typeof role !== "string" || !STRUCTURAL_REF_ROLES.has(role as Role))
      throw new Error("structural snapshot: structuralRef role is invalid");
    out.push({ ref, role: role as Role });
  }
  return out;
}
```

3f. **`upsert`** (lines 192–214): remove the `membership` computation and the `membership` field from the `entry` literal. The entry becomes:

```ts
    const entry: IndexEntry = {
      uid: node.uid,
      id: node.id,
      kind: node.kind,
      deprecatedIds: new Set(node.deprecatedIds),
      outRefs: extractOutRefs(node),
    };
```

(keep the `byUid.set` / `idToUid.set` / `deprecatedToUid` / inRefs-population lines that follow.)

3g. **`toDict`** (lines 216–252): change the return type's per-entry `membership` field to `structuralRefs`, and emit it. Replace the entries `.push({...})` so each entry is:

```ts
      entries.push({
        uid: entry.uid,
        id: entry.id,
        kind: entry.kind,
        deprecatedIds: [...entry.deprecatedIds].sort(),
        relations,
        structuralRefs: entry.outRefs
          .filter((o) => !o.role.startsWith("relation_"))
          .map((o) => ({ ref: o.ref, role: o.role })),
      });
```

and update the method's declared return type accordingly:

```ts
  toDict(): {
    entries: Array<{
      uid: string;
      id: string;
      kind: string;
      deprecatedIds: string[];
      relations: Array<Record<string, unknown>>;
      structuralRefs: Array<{ ref: string; role: Role }>;
    }>;
  } {
```

3h. **`fromDict`** (lines 254–322): change the required-key check from the `["uid","id","kind","deprecatedIds","relations","membership"]` literal to `STRUCTURAL_ENTRY_KEYS`; replace the `validatedMembership` call + `outRefsFrom` with `validatedStructuralRefs` + the relation/structural composition; drop the `membership` field from the rebuilt `entry`. The changed lines:

```ts
      for (const key of STRUCTURAL_ENTRY_KEYS) {
        if (!(key in e)) throw new Error(`structural snapshot: entry missing ${key}`);
      }
```

```ts
      // ... after relations[] is built from e.relations (unchanged) ...
      const structuralRefs = validatedStructuralRefs(e.structuralRefs);
      const outRefs = [...relationOutRefs(relations), ...structuralRefs];
      const entry: IndexEntry = {
        uid,
        id: entryId,
        kind,
        deprecatedIds: new Set(deprecatedIds),
        outRefs,
      };
```

(the identity-claim collision loop and the `byUid.set`/`idToUid.set`/`inRefs` population that follow are unchanged.)

3i. **`drop`, `relationsByRole`, `outboundEdges`, `inboundEdges`, `danglingEdges`** are unchanged — they already filter on `relation_source`/`relation_target` roles and `relation !== undefined`, which the new structural roles never satisfy. Confirm no remaining reference to `membership_edge_*` or `entry.membership` exists anywhere in the file (search for `membership` — after this task the only occurrence should be the imported `MEMBERSHIP` constant and the `membership_member` role string).

- [ ] **Step 4: Run the index tests, then the full gate**

Run: `cd ~/d/nodes/ts && rtk npx vitest run tests/structural-index.test.ts tests/index-snapshot.test.ts tests/index-rebuild-equivalence.test.ts`
Expected: PASS.

Run: `rtk npm run typecheck && rtk npm run check && rtk npm test`
Expected: `tsc` clean, biome clean. `rtk npm test` → 1 failed (`corpus_parity`), rest passed (baseline unchanged — corpus still uses old `rewriteRefs`).

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes && rtk git add ts/src/structural-index.ts ts/tests/structural-index.test.ts ts/tests/index-snapshot.test.ts ts/tests/index-rebuild-equivalence.test.ts
rtk git commit -m "feat(shapes-ts): index extracts structural refs from form facets; persists generic structuralRefs"
```

---

### Task 4: Corpus rename — rewrite refs across the form facets

**Files:**
- Modify: `ts/src/corpus.ts` (`rewriteRefs`)
- Test: `ts/tests/corpus.test.ts` (rename-rewrite tests), `ts/tests/corpus_parity.test.ts` (goes green)

**No-registry coverage:** the new rename tests below build `new Corpus(root)` with **no registry argument**, so they prove rename rewrites structural facets WITHOUT a registry (the no-registry-recognition constraint). `corpus_parity.test.ts` also renames the shared fixture corpus with no registry — it is the cross-language form of the same guarantee. (`corpus-persistence-rename.test.ts` is a manifest/persistence test using only plain relations — NOT a structure test — and needs no changes.)

**Interfaces:**
- Consumes: `MEMBERSHIP`/`EDGES`/`ORDER`/`KEYS` (Task 2 — already imported? `corpus.ts` currently imports only `MEMBERSHIP`; add the others).
- Produces: `rewriteRefs(node, oldId, newId)` rewrites `oldId → newId` across top-level `relations` + `membership.members` + `edges` (each Relation source/target) + `order` entries + `keys` **values** (mirrors `corpus.py` `_rewrite_refs`, lines 25–51). The `keys` VALUE side is rewritten (matching the `keys_value` role the index extracts); map keys (labels) are untouched.

- [ ] **Step 1: Write/adjust the failing tests**

**`ts/tests/corpus.test.ts`** — migrate the two rename-rewrite tests (L138–179) to split facets and assert the new facet values are rewritten:

Replace `"rewrites membership members and edge sources"` (L138–162) with a graph node using split facets, asserting both `membership.members` and the `edges` facet are rewritten:

```ts
  it("rename rewrites membership members and edges-facet endpoints", () => {
    const c = new Corpus(root); // `root` is the module-level temp dir from beforeEach
    c.add(makeNode({ id: "topic:old", kind: "topic", title: "Old" }));
    c.add(makeNode({ id: "topic:x", kind: "topic", title: "X" }));
    c.add(
      makeNode({
        id: "graph:g",
        kind: "graph",
        title: "G",
        facets: {
          membership: { members: ["topic:old", "topic:x"] },
          edges: { edges: [{ source: "topic:old", predicate: "to", target: "topic:old" }] },
        },
      }),
    );
    c.rename("topic:old", "topic:new");
    const g = c.get("graph:g");
    expect((g.facets.membership as { members: string[] }).members).toEqual(["topic:new", "topic:x"]);
    const edges = (g.facets.edges as { edges: Array<{ source: string; target: string }> }).edges;
    expect(edges[0].source).toBe("topic:new");
    expect(edges[0].target).toBe("topic:new");
  });
```

Replace `"rewrites dict-membership values"` (L164–179) with a dict node using split facets, asserting the `keys` VALUE is rewritten and add an `order`-facet (list) rename assertion:

```ts
  it("rename rewrites dict keys-facet values and list order entries", () => {
    const c = new Corpus(root);
    c.add(makeNode({ id: "topic:old", kind: "topic", title: "Old" }));
    c.add(
      makeNode({
        id: "dict:d",
        kind: "dict",
        title: "D",
        facets: { membership: { members: ["topic:old"] }, keys: { keys: { label: "topic:old" } } },
      }),
    );
    c.add(
      makeNode({
        id: "list:l",
        kind: "list",
        title: "L",
        facets: { membership: { members: ["topic:old"] }, order: { order: ["topic:old"] } },
      }),
    );
    c.rename("topic:old", "topic:new");
    expect((c.get("dict:d").facets.keys as { keys: Record<string, string> }).keys.label).toBe("topic:new");
    expect((c.get("list:l").facets.order as { order: string[] }).order).toEqual(["topic:new"]);
  });
```

`corpus.test.ts` already provides the scaffolding these tests use: a module-level `let root` set in `beforeEach` via `mkdtempSync(join(tmpdir(), "nodes-corpus-"))` (cleaned in `afterEach`), the `makeNode` import, and a `n(id, kind, extra)` helper. Use `new Corpus(root)` and `makeNode(...)` as shown; do not introduce a new temp-dir helper.

(The two tests above already exercise the no-registry guarantee because `new Corpus(root)` is built without a registry. No other corpus test file needs changes for this task.)

- [ ] **Step 2: Run the corpus tests to verify they fail**

Run: `cd ~/d/nodes/ts && rtk npx vitest run tests/corpus.test.ts tests/corpus_parity.test.ts`
Expected: FAIL — the new edges/order/keys assertions fail (old `rewriteRefs` only touches `membership.members` and the now-absent bundled `membership.edges`); `corpus_parity` still fails.

- [ ] **Step 3: Update `rewriteRefs` in `ts/src/corpus.ts`**

3a. Change the import (line 7) from `import { MEMBERSHIP } from "./shapes.js";` to `import { EDGES, KEYS, MEMBERSHIP, ORDER } from "./shapes.js";`

3b. Replace `rewriteRefs` (lines 21–50) with (mirrors `corpus.py` `_rewrite_refs`):

```ts
/** Rewrite every position in `node` that holds `oldId` to `newId` (in place):
 * top-level relations plus the built-in structural form facets. */
function rewriteRefs(node: Node, oldId: string, newId: string): void {
  for (const rel of node.relations) {
    if (rel.source === oldId) rel.source = newId;
    if (rel.target === oldId) rel.target = newId;
  }
  const mem = node.facets[MEMBERSHIP];
  if (mem !== null && typeof mem === "object") {
    const members = (mem as Record<string, unknown>).members;
    if (Array.isArray(members)) {
      (mem as Record<string, unknown>).members = members.map((m) => (m === oldId ? newId : m));
    }
  }
  const eg = node.facets[EDGES];
  if (eg !== null && typeof eg === "object") {
    const edges = (eg as Record<string, unknown>).edges;
    if (Array.isArray(edges)) {
      for (const edge of edges) {
        if (edge !== null && typeof edge === "object") {
          const e = edge as Record<string, unknown>;
          if (e.source === oldId) e.source = newId;
          if (e.target === oldId) e.target = newId;
        }
      }
    }
  }
  const od = node.facets[ORDER];
  if (od !== null && typeof od === "object") {
    const order = (od as Record<string, unknown>).order;
    if (Array.isArray(order)) {
      (od as Record<string, unknown>).order = order.map((m) => (m === oldId ? newId : m));
    }
  }
  const ky = node.facets[KEYS];
  if (ky !== null && typeof ky === "object") {
    const keys = (ky as Record<string, unknown>).keys;
    if (keys !== null && typeof keys === "object") {
      const km = keys as Record<string, unknown>;
      for (const k of Object.keys(km)) {
        if (km[k] === oldId) km[k] = newId;
      }
    }
  }
}
```

Do NOT change the `rename` method body — `rewriteRefs` is called in its prepare phase (before any write), preserving the fail-before-mutate ordering.

- [ ] **Step 4: Run the corpus tests, then the full gate**

Run: `cd ~/d/nodes/ts && rtk npx vitest run tests/corpus.test.ts tests/corpus_parity.test.ts`
Expected: PASS — including `corpus_parity` (the TS rename now matches the shared oracle).

Run: `rtk npm run typecheck && rtk npm run check && rtk npm test`
Expected: `tsc` clean, biome clean. `rtk npm test` → **0 failed, all passed**. (The baseline failure is now resolved.)

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes && rtk git add ts/src/corpus.ts ts/tests/corpus.test.ts
rtk git commit -m "feat(shapes-ts): rename rewrites refs across membership/edges/order/keys form facets"
```

---

### Task 5: Finalize — barrel verification, vocab comment, full-suite green

**Files:**
- Modify: `ts/src/vocab/kinds.ts` (JSDoc comment)
- Verify: `ts/src/index.ts` (barrel), `ts/tests/smoke.test.ts`, `ts/tests/vocab-exports.test.ts`
- Note: `docs/format.md` is the SHARED, language-agnostic doc and was already updated by Plan A-py — do NOT edit it here; only confirm it still matches.

**Interfaces:** none new — this task closes the surface and proves the whole suite green.

- [ ] **Step 1: Update the `vocab/kinds.ts` comment**

In `ts/src/vocab/kinds.ts`, the JSDoc on `registerKnowledgeVocab` (≈line 16) says `Mirrors registerBuiltinShapes in shapes.ts.`. `registerBuiltinShapes` still exists (its signature changed but the name is stable), and knowledge-vocab kinds still adopt no shape. The reference remains valid — leave it, but if the comment describes the OLD bundled membership model anywhere, correct it to the membership/form-facet split. (Read the file; if the only reference is the name `registerBuiltinShapes`, no change is needed — this step then just confirms the comment is not stale.)

- [ ] **Step 2: Verify the barrel and smoke test**

Read `ts/tests/smoke.test.ts` (it asserts `typeof registerBuiltinShapes === "function"` from the barrel) and `ts/tests/vocab-exports.test.ts`. Confirm:
- `registerBuiltinShapes` is still exported from `ts/src/index.ts` (it is — kept through Tasks 2).
- No removed symbol (`requireDictKeys`, the old bundled `Membership` type, `membership_edge_*` roles) is referenced anywhere in `ts/src/index.ts` or any test. Search the repo: `grep -rn "requireDictKeys\|membership_edge" ts/` should return nothing (remember the repo's grep can misreport — cross-check by reading `ts/src/index.ts` directly).

If smoke/vocab-exports reference a removed symbol, fix the test to the new surface. If everything is already consistent (expected), this step changes nothing.

- [ ] **Step 3: Run the full gate**

Run: `cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all vitest tests pass (0 failed), `tsc` clean, biome clean.

- [ ] **Step 4: Confirm Python parity by inspection**

Confirm, by reading both, that the TS behaviour matches the Python oracle on the five locked invariants:
- `membership` is scope-only (`{ members }`); `edges`/`order`/`keys` are separate form facets.
- `Registry.validate` composes shape + kind facets/invariants; duplicate shape and kind names fail; unknown adopted shape fails; a shape and kind may share a name.
- Structure refs populate `inRefs` (so rename finds referrers) but never appear in `outboundEdges`/`inboundEdges`/`danglingEdges` (those are `relation_*` only).
- Rename rewrites refs across `relations` + all four structural facets, with or without a registry.
- The structural snapshot persists `structuralRefs` (generic `{ ref, role }`) — adding a future shape needs no snapshot-schema change.

- [ ] **Step 5: Commit (only if Step 1/2 changed anything)**

```bash
cd ~/d/nodes && rtk git add ts/src/vocab/kinds.ts ts/src/index.ts ts/tests/smoke.test.ts
rtk git commit -m "docs(shapes-ts): finalize structural-shape surface; confirm parity with Python oracle"
```

If Steps 1–2 found nothing to change (the likely case), skip the commit and note in the report that the surface was already consistent and the full suite is green.

---

## Final Verification (whole-plan)

From `~/d/nodes/ts`, the full gate must be green:

```
rtk npm test            # all tests pass, 0 failed (corpus_parity now green)
rtk npm run typecheck   # tsc --noEmit clean
rtk npm run check       # biome clean
```

Cross-language parity: `corpus_parity.test.ts` (TS rename over the shared `fixtures/` corpus) passes against the same `fixtures/corpus.rename.canonical.json` oracle the Python suite uses — proving the two kernels agree on the new model.
