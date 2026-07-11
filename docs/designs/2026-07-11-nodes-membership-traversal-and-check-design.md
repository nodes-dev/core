# Membership Traversal + Dangling-Member Check - Design

**Status:** draft design
**Date:** 2026-07-11
**Scope:** Close the first bullet of STANDARD §13 in both kernels: report dangling
membership refs from `Corpus.check` as a new `dangling-member` finding, and expose
public membership-graph traversal (`members` / `containers` / `descendants` /
`ancestors`) on `Corpus`. STANDARD 1.0 → 1.1 (additive), shared conformance fixtures
extended in the same change.

---

## 1. Context

`~/d/nodes` ships two kernels (Python under `python/`, TypeScript under `ts/`) whose
structural index already tracks every membership/edges/order/keys ref (roles
`membership_member`, `edges_source`, `edges_target`, `order_member`, `keys_value`) in
`inRefs` / `in_refs`. Those refs participate in rename rewriting and stay indexed after
a referent is deleted — but two capabilities are missing, recorded verbatim in
STANDARD §13:

> No public membership-graph traversal (tree descendants, DAG reachability); membership
> refs are tracked for rename/dangling integrity but not exposed as graph edges, and
> dangling membership refs are not yet reported by `check`.

Concretely: `Corpus.delete` succeeds while other nodes still list the deleted node as a
member (§7 pins this — inbound refs remain on disk and become dangling), and nothing
surfaces the resulting hole. `Index.danglingEdges` inspects only `relation_target`
roles, so `Corpus.check` is blind to a mindmap whose member was deleted. Downstream,
mindful v6 now builds mindmap edges and views directly on membership graphs, so the gap
is no longer theoretical.

## 2. Goals

- `Corpus.check` reports every unresolved membership ref as a `dangling-member`
  finding, pinned by the shared check oracle.
- Public, cycle-safe membership traversal on `Corpus` in both kernels: direct
  (`members`, `containers`) and transitive (`descendants`, `ancestors`), pinned by a
  new shared traversal oracle.
- STANDARD updated in the same change: §7 gains the traversal contract, §8.2 gains the
  finding, §11.2 gains the fixture rows, §12 records **1.1**, §13 drops its first
  bullet.

## 3. Non-goals

- **No change to `delete` semantics.** §7 stands: inbound refs to a deleted node remain
  on disk and become dangling — a normal state, surfaced (now fully, via `check`) and
  never raised. Consumers that want stricter behavior compose it from `containers()`.
- **No reporting of non-membership structural roles.** On shape-valid nodes the
  edges/order/keys refs are invariant-forced subsets of `members`, so a dangling member
  subsumes them; payload validity remains a registry concern (§8.2's framing is
  unchanged).
- No relations-graph changes (`outbound` / `inbound` / `neighbors` / `dangling` are
  untouched).
- No mindful-side consumption (delete warnings, cascade UX) — that is a separate
  mindful slice on top of this API.
- No concurrency/locking or scale work (§13's other bullets).

## 4. API surface

TypeScript shown; Python is the snake_case mirror (`members`, `containers`,
`descendants`, `ancestors` — same names, `list[str]` returns).

```ts
// ts/src/corpus.ts
members(ref: string): string[];      // direct members of ref's node
containers(ref: string): string[];   // nodes whose membership lists ref
descendants(ref: string): string[];  // transitive members (BFS over membership)
ancestors(ref: string): string[];    // transitive containers (BFS over membership)
```

Shared semantics (normative, STANDARD §7):

- **Input resolution.** The input ref resolves via the index (live id, then deprecated
  id) — `RefError` when it resolves to no live node. This is the only raising path.
- **Output.** Sorted (Unicode code point) arrays of **live ids**, deduplicated by uid.
  Duplicate membership entries and multiple refs resolving to the same node (e.g. a
  live id and a deprecated id of the same node) yield one result.
- **Membership-ref resolution.** Member refs resolve like all refs (live then
  deprecated); a member listed under a deprecated id resolves to its live node and is
  reported under its live id. **Dangling member refs are silently skipped** — reporting
  them is `check`'s job, per the §7 rule that dangling is surfaced, never raised.
- **No-facet / no-container cases.** A node without a membership facet has no members;
  a node no container lists has no containers. Both return `[]`, never an error.
- **Direct vs transitive.** `members` / `containers` read exactly one hop (the literal
  facet content, resolved) — a container listing itself appears in its own `members`.
  `descendants` / `ancestors` are the transitive closures over one-or-more hops and
  **always exclude the start node**, even when a membership cycle makes it reachable
  from itself.
- **Cycle safety.** Membership traversal must be cycle-safe for **every** shape:
  `dag` / `tree` acyclicity constrains only the container's internal `edges` facet
  (`requireAcyclic` / `requireSingleParent` walk `edgesOf(node)`), so cross-node
  membership containment cycles are legal for all shapes. Traversal terminates via a
  visited-uid set seeded with the start uid.
- **Malformed facets.** Non-object `membership` payloads, non-array `members`, and
  non-string entries contribute no refs (exactly what `structuralOutRefs` /
  `_structural_out_refs` already extract); their diagnosis belongs to
  `Registry.check`, not traversal.

## 5. Index internals

Everything is a pure index computation (zero file I/O), following the existing layering
where `Index` owns graph primitives and `Corpus` adds ref resolution + uid→id mapping:

```ts
// ts/src/structural-index.ts — uid-level primitives
membersOf(uid: string): Set<string>;              // uids of resolvable direct members
containersOf(uid: string): Set<string>;           // uids of direct containers
membershipClosure(uid: string, direction: "members" | "containers"): Set<string>;
danglingMembers(): Array<{ sourceUid: string; ref: string }>;
```

- `membersOf`: walk the entry's `outRefs` with role `membership_member`, resolve each
  ref via `resolveUid`, collect non-null uids.
- `containersOf`: the mirror — for each of the node's identity claims (live id +
  deprecated ids, the `refsForUid` pattern used by `relationsByRole`), walk
  `inRefs[claim]` rows with role `membership_member` and collect source uids. This is
  what makes "member listed under my deprecated id" attribute correctly.
- `membershipClosure`: one BFS used in both directions, visited-set seeded with the
  start uid; returns the visited set minus the start.
- `danglingMembers`: for every entry, every `membership_member` out-ref whose ref
  resolves to no uid, deduplicated by `(sourceUid, ref)`.

`Corpus.members/containers/descendants/ancestors` each do: `requireUid(ref)` → index
primitive → map uids to live ids via `idFor` → sort with `compareCodepoints`. Python
mirrors with `members_of` / `containers_of` / `membership_closure` /
`dangling_members` on `Index`.

## 6. `dangling-member` finding

`Corpus.check` gains a third scan alongside registry violations and dangling relations:

| Code | Severity | `ref` | `detail` | Condition |
|------|----------|-------|----------|-----------|
| `dangling-member` | warning | container's live id | the unresolved member ref | a `membership.members` entry resolves to no live node |

- One finding per `(container, member ref)` pair — `danglingMembers`' dedupe means a
  hand-edited duplicate entry reports once.
- A member listed under a *deprecated but resolvable* id is **not** dangling
  (resolution includes deprecated ids, same as relations).
- Severity mirrors `dangling-ref`: dangling is a normal, hand-editable-files state —
  a warning, not an error.
- Findings merge into the existing `(ref, code, detail)` code-point ordering.
  `message` is human-only and non-normative, e.g.
  `set:crate: member "note:ghost" resolves to no live node`.

## 7. STANDARD changes (1.0 → 1.1)

Additive throughout — a **minor** bump per §12 (new methods, one new finding code, new
fixtures; no change to reading/writing corpora or to pinned behavior):

- **§7 Corpus semantics.** After the relations-only graph-queries bullet, a new bullet
  pins membership traversal: the four methods, sorted-live-ids returns, resolution
  rules, dangling-skip, transitive self-exclusion, cycle safety, `RefError` on input
  only.
- **§8.2 `Corpus.check`.** The findings table gains the `dangling-member` row. The
  sentence "Malformed structural facet payloads are a registry concern (shape
  invariants); dangling *membership* refs are deferred (§13)." is replaced by the new
  rule: structural findings are exactly one `dangling-ref` per unresolved relation
  target plus one `dangling-member` per unresolved `(container, member ref)` pair;
  malformed payloads remain a registry concern.
- **§11.2 Fixture inventory.** The `check-corpus/`, `check.oracle.json` row's
  description extends to cover the membership cluster; a new row pins
  `traversal.oracle.json` (membership traversal over `check-corpus/`).
- **§12 Versioning.** History gains: **1.1** (2026-07-11) — membership traversal +
  `dangling-member` finding.
- **§13 Known limitations.** The first bullet is deleted; single-writer and scale
  bullets stay.
- Header spec version: 1.0 → 1.1.

## 8. Conformance fixtures

### 8.1 `fixtures/check-corpus/` — membership cluster

Six new nodes join the existing seven. Containers use the built-in `set` convenience
kind (the conformance registry already loads `registerBuiltinShapes` /
`register_builtin_shapes`; `set` requires only the `membership` facet):

| Node | `membership.members` | Purpose |
|------|----------------------|---------|
| `set:crate` | `["set:box", "note:ghost"]` | nesting root; `note:ghost` is the dangling member |
| `set:box` | `["note:tidy", "note:old-name"]` | mid container; one member via a deprecated id |
| `set:loop-a` | `["set:loop-b"]` | two-node membership cycle |
| `set:loop-b` | `["set:loop-a"]` | two-node membership cycle |
| `set:selfie` | `["set:selfie"]` | direct self-membership (one-node cycle) |
| `note:renamed` | — (plain note, `deprecated_ids: ["note:old-name"]`) | deprecated-id resolution target |

`note:ghost` deliberately does not exist. All six new nodes are registry-valid, so the
only new check finding is the dangling member.

### 8.2 `fixtures/check.oracle.json`

One new row, landing between `paper:typo` and `zzz:mystery` in the `(ref, code,
detail)` order:

```json
{ "severity": "warning", "code": "dangling-member", "ref": "set:crate", "detail": "note:ghost" }
```

### 8.3 `fixtures/traversal.oracle.json` (new)

An array of `{op, ref, expect}` rows evaluated against `check-corpus/`; both kernels
run every row and compare exactly:

```json
[
  { "op": "members",     "ref": "set:crate",     "expect": ["set:box"] },
  { "op": "members",     "ref": "set:box",       "expect": ["note:renamed", "note:tidy"] },
  { "op": "members",     "ref": "note:tidy",     "expect": [] },
  { "op": "containers",  "ref": "note:tidy",     "expect": ["set:box"] },
  { "op": "containers",  "ref": "note:old-name", "expect": ["set:box"] },
  { "op": "containers",  "ref": "set:box",       "expect": ["set:crate"] },
  { "op": "descendants", "ref": "set:crate",     "expect": ["note:renamed", "note:tidy", "set:box"] },
  { "op": "ancestors",   "ref": "note:renamed",  "expect": ["set:box", "set:crate"] },
  { "op": "descendants", "ref": "set:loop-a",    "expect": ["set:loop-b"] },
  { "op": "ancestors",   "ref": "set:loop-b",    "expect": ["set:loop-a"] },
  { "op": "members",     "ref": "set:selfie",    "expect": ["set:selfie"] },
  { "op": "descendants", "ref": "set:selfie",    "expect": [] }
]
```

Coverage by row: dangling-skip (1), deprecated-member resolution + sorted live-id
output (2), facet-less node (3), direct containers (4), deprecated *input* ref (5),
nesting (6–8), cycle termination + transitive self-exclusion (9–10), direct
self-membership vs transitive start-exclusion (11–12). Error behavior
(`RefError` on an unresolvable input ref) is deliberately not oracle material — the
oracle pins successful results; errors are pinned by each language's unit tests.

## 9. Testing

Per language, three layers:

- **Index unit tests** — `membersOf` / `containersOf` / `membershipClosure` /
  `danglingMembers` (and snake_case mirrors): cycles, self-membership, duplicate member
  entries, members via deprecated ids, missing/malformed membership facets, dedupe of
  dangling pairs.
- **Corpus unit tests** — `RefError` on unresolvable input refs for all four methods;
  sorted live-id output; `check` emits `dangling-member` after a real `delete`;
  finding dedupe; combined ordering with existing codes.
- **Oracle parity tests** — `traversal_parity` mirroring the existing `check_parity`
  harness (copy `check-corpus/` to a temp root, run every oracle row). Traversal is
  registry-independent, so the harness constructs `Corpus(root)` with no registry —
  itself a useful pin. The existing
  check-parity test picks up the new oracle row automatically. The "fixture corpus has
  seven nodes" assertions in both languages become thirteen.

Gates: `npm run check && npm run typecheck && npm test` under `ts/`, `uv run pytest`
under `python/`. Because mindful v6 consumes the TS kernel via its `@nodes/kernel`
symlink to `ts/` built output, finish with a TS `npm run build` and run mindful's suite
as a downstream smoke check.

## 10. Decisions log

1. **`delete` unchanged.** Dangling stays a surfaced-never-raised normal state (§7);
   strict deletion composes from `containers()` at the consumer layer. Keeps the bump
   minor.
2. **Membership-only reporting.** One `dangling-member` code; edges/order/keys roles
   unreported (invariant-forced subsets of `members` on shape-valid nodes; payload
   validity is a registry concern).
3. **Symmetric four traversal methods** (`members` / `containers` / `descendants` /
   `ancestors`) over a minimal pair or an options-bag `traverse()`.
4. **Sorted live ids** (code-point order, uid-deduped) as the return type — index-only,
   no file I/O, trivially oracle-pinnable; callers `get()` what they need.
5. **Logic on `Index`, `Corpus` wraps** — matches the existing graph-query layering in
   both languages.
6. **Transitive results always exclude the start node**, even when a cycle makes it
   reachable from itself; direct `members` does not self-exclude (it reports the
   literal, resolved facet).
7. **`dangling-member` is a warning**, deduped by `(ref, detail)` — mirrors
   `dangling-ref`.
8. **Fixtures: extend `check-corpus/`, add `traversal.oracle.json`** — one corpus, two
   oracles; the check corpus needed a dangling-member case regardless.
