# Membership Traversal + Dangling-Member Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close STANDARD §13's first bullet in both kernels: `Corpus.check` reports dangling membership refs (`dangling-member`), and `Corpus` gains cycle-safe membership traversal (`members` / `containers` / `descendants` / `ancestors`), pinned by shared conformance fixtures; STANDARD 1.0 → 1.1.

**Architecture:** Uid-level primitives on the structural `Index` (which already tracks every `membership_member` ref in `outRefs` / `inRefs`), wrapped by thin ref-resolving methods on `Corpus` — the same layering as the existing relations-graph queries. TypeScript and Python change in mirror-image; shared fixtures land after both kernels so every commit stays green.

**Tech Stack:** TypeScript (Node ≥20, vitest, biome) under `ts/`; Python 3.11 (pytest, ruff, pyright, uv) under `python/`; shared JSON oracles under `fixtures/`.

**Spec:** `docs/designs/2026-07-11-nodes-membership-traversal-and-check-design.md` (committed). The spec governs on any conflict.

## Global Constraints

- Work on `main` (standing consent). Run all `git` and `npm` commands through `rtk` (e.g. `rtk git add …`, `rtk npm test`); run Python tooling directly via `uv`.
- Do NOT add any AI-attribution trailer or footer to commit messages ("Co-Authored-By: …", "Generated with Claude Code", etc.).
- Stage files explicitly by path — never `git add -A` or `git add .`.
- Gates before every commit — TypeScript (from `ts/`): `rtk npm test`, `rtk npm run typecheck`, `rtk npm run check`; Python (from `python/`): `uv run --frozen pytest -q`, `uv run --frozen ruff check .`, `uv run --frozen pyright src`.
- Exact normative values (copy verbatim, do not improvise): finding code `dangling-member`, severity `warning`, `ref` = container's live id, `detail` = the unresolved member ref, deduplicated per `(container, member ref)`; traversal returns **sorted (Unicode code point), uid-deduplicated live ids**; transitive results always exclude the start node, even when a cycle reaches it; dangling member refs are silently skipped by traversal; `RefError` only for an unresolvable *input* ref.
- Fixture uids are 32-char strings; the new ones are pinned in Task 5 — do not regenerate them.
- Use `~/d/` (never `/home/keith/…` or `/mnt/ssd/Dropbox/…`) for any path written into docs.

---

### Task 1: TypeScript Index membership primitives

**Files:**
- Modify: `ts/src/structural-index.ts` (append methods to `class Index`, after `danglingEdges()`)
- Test: `ts/tests/structural-index.test.ts` (append a describe block)

**Interfaces:**
- Consumes: existing `Index` internals — `byUid: Map<string, IndexEntry>`, `inRefs: Map<string, InRef[]>`, `resolveUid(ref): string | null`, private `refsForUid(uid): string[]` (throws `RefError` on unknown uid), `OutRef.role`.
- Produces (Task 2 relies on these exact signatures):
  - `membersOf(uid: string): Set<string>`
  - `containersOf(uid: string): Set<string>`
  - `membershipClosure(uid: string, direction: "members" | "containers"): Set<string>`
  - `danglingMembers(): Array<{ sourceUid: string; ref: string }>`

- [ ] **Step 1: Write the failing tests**

Append to `ts/tests/structural-index.test.ts`. Extend the existing import lines at the top of the file (it already imports `CollisionError`, `makeNode`, `relatesTo`, `Index`) with:

```ts
import { RefError } from "../src/errors.js";
import { MEMBERSHIP } from "../src/shapes.js";
```

Then append at the end of the file (the `node(...)` helper already exists at the top):

```ts
function setNode(id: string, members: string[], extra: Record<string, unknown> = {}) {
  return node(id, "set", { facets: { [MEMBERSHIP]: { members } }, ...extra });
}

describe("Index — membership traversal", () => {
  it("membersOf returns resolvable member uids and skips dangling refs", () => {
    const leaf = node("note:leaf", "note");
    const box = setNode("set:box", ["note:leaf", "note:ghost"]);
    const idx = Index.build([leaf, box]);
    expect(idx.membersOf(box.uid)).toEqual(new Set([leaf.uid]));
  });

  it("membersOf resolves members listed under a deprecated id", () => {
    const renamed = node("note:renamed", "note", { deprecatedIds: ["note:old"] });
    const box = setNode("set:box", ["note:old"]);
    const idx = Index.build([renamed, box]);
    expect(idx.membersOf(box.uid)).toEqual(new Set([renamed.uid]));
  });

  it("membersOf dedupes duplicate entries and live+deprecated refs to one uid", () => {
    const renamed = node("note:renamed", "note", { deprecatedIds: ["note:old"] });
    const box = setNode("set:box", ["note:renamed", "note:old", "note:renamed"]);
    const idx = Index.build([renamed, box]);
    expect(idx.membersOf(box.uid)).toEqual(new Set([renamed.uid]));
  });

  it("membersOf on a node without a membership facet is empty", () => {
    const plain = node("note:plain", "note");
    const idx = Index.build([plain]);
    expect(idx.membersOf(plain.uid)).toEqual(new Set());
  });

  it("membersOf and containersOf reject an unknown uid", () => {
    expect(() => new Index().membersOf("nope")).toThrow(RefError);
    expect(() => new Index().containersOf("nope")).toThrow(RefError);
  });

  it("containersOf finds containers listing the node's live or deprecated id", () => {
    const renamed = node("note:renamed", "note", { deprecatedIds: ["note:old"] });
    const byLive = setNode("set:live", ["note:renamed"]);
    const byDep = setNode("set:dep", ["note:old"]);
    const idx = Index.build([renamed, byLive, byDep]);
    expect(idx.containersOf(renamed.uid)).toEqual(new Set([byLive.uid, byDep.uid]));
  });

  it("containersOf on an uncontained node is empty", () => {
    const plain = node("note:plain", "note");
    const idx = Index.build([plain]);
    expect(idx.containersOf(plain.uid)).toEqual(new Set());
  });

  it("membershipClosure walks nesting transitively in both directions", () => {
    const leaf = node("note:leaf", "note");
    const box = setNode("set:box", ["note:leaf"]);
    const crate = setNode("set:crate", ["set:box"]);
    const idx = Index.build([leaf, box, crate]);
    expect(idx.membershipClosure(crate.uid, "members")).toEqual(new Set([box.uid, leaf.uid]));
    expect(idx.membershipClosure(leaf.uid, "containers")).toEqual(new Set([box.uid, crate.uid]));
  });

  it("membershipClosure terminates on cycles and always excludes the start node", () => {
    const a = setNode("set:a", ["set:b"]);
    const b = setNode("set:b", ["set:a"]);
    const selfie = setNode("set:selfie", ["set:selfie"]);
    const idx = Index.build([a, b, selfie]);
    expect(idx.membershipClosure(a.uid, "members")).toEqual(new Set([b.uid]));
    expect(idx.membershipClosure(selfie.uid, "members")).toEqual(new Set());
    expect(idx.membershipClosure(selfie.uid, "containers")).toEqual(new Set());
  });

  it("danglingMembers reports unresolved membership refs deduped per container", () => {
    const box = setNode("set:box", ["note:ghost", "note:ghost"]);
    const other = setNode("set:other", ["note:ghost"]);
    const idx = Index.build([box, other]);
    const rows = idx.danglingMembers();
    expect(rows).toHaveLength(2);
    expect(new Set(rows.map((r) => `${r.sourceUid} ${r.ref}`))).toEqual(
      new Set([`${box.uid} note:ghost`, `${other.uid} note:ghost`]),
    );
  });

  it("danglingMembers is empty when every member resolves (incl. via deprecated ids)", () => {
    const renamed = node("note:renamed", "note", { deprecatedIds: ["note:old"] });
    const box = setNode("set:box", ["note:old"]);
    expect(Index.build([renamed, box]).danglingMembers()).toEqual([]);
  });

  it("a malformed membership facet contributes no member refs and no danglers", () => {
    const weird = node("note:weird", "note", { facets: { [MEMBERSHIP]: { members: "not-a-list" } } });
    const idx = Index.build([weird]);
    expect(idx.membersOf(weird.uid)).toEqual(new Set());
    expect(idx.danglingMembers()).toEqual([]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `ts/`): `rtk npm test -- tests/structural-index.test.ts`
Expected: FAIL — `idx.membersOf is not a function` (and siblings).

- [ ] **Step 3: Implement the four Index methods**

In `ts/src/structural-index.ts`, append inside `class Index`, directly after the closing brace of `danglingEdges()` (`RefError` is already imported at the top of the file):

```ts
  /** Uids of this node's resolvable direct members. Dangling member refs are skipped
   * (check reports them); duplicate entries and live+deprecated refs dedupe by uid. */
  membersOf(uid: string): Set<string> {
    const entry = this.byUid.get(uid);
    if (entry === undefined) throw new RefError(`uid ${JSON.stringify(uid)} not in index`);
    const members = new Set<string>();
    for (const oref of entry.outRefs) {
      if (oref.role !== "membership_member") continue;
      const memberUid = this.resolveUid(oref.ref);
      if (memberUid !== null) members.add(memberUid);
    }
    return members;
  }

  /** Uids of the nodes whose membership facet lists any of this node's identity claims
   * (live id or deprecated ids — the same attribution rule as relationsByRole). */
  containersOf(uid: string): Set<string> {
    const containers = new Set<string>();
    for (const ref of this.refsForUid(uid)) {
      for (const inref of this.inRefs.get(ref) ?? []) {
        if (inref.outRef.role !== "membership_member") continue;
        containers.add(inref.sourceUid);
      }
    }
    return containers;
  }

  /** Transitive membership closure (BFS). The visited set is seeded with the start uid,
   * which is excluded from the result even when a membership cycle reaches it. */
  membershipClosure(uid: string, direction: "members" | "containers"): Set<string> {
    const step = direction === "members" ? this.membersOf.bind(this) : this.containersOf.bind(this);
    const visited = new Set<string>([uid]);
    const queue: string[] = [uid];
    while (queue.length > 0) {
      const current = queue.shift() as string;
      for (const next of step(current)) {
        if (visited.has(next)) continue;
        visited.add(next);
        queue.push(next);
      }
    }
    visited.delete(uid);
    return visited;
  }

  /** Every unresolved membership ref, deduped by (container uid, ref). */
  danglingMembers(): Array<{ sourceUid: string; ref: string }> {
    const out: Array<{ sourceUid: string; ref: string }> = [];
    const seen = new Set<string>();
    for (const entry of this.byUid.values()) {
      for (const oref of entry.outRefs) {
        if (oref.role !== "membership_member") continue;
        if (this.resolveUid(oref.ref) !== null) continue;
        const key = `${entry.uid}\u0000${oref.ref}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({ sourceUid: entry.uid, ref: oref.ref });
      }
    }
    return out;
  }
```

Note: `refsForUid` is currently `private`; `containersOf` calls it from inside the class, so no visibility change is needed.

- [ ] **Step 4: Run the gates**

Run (from `ts/`): `rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/structural-index.ts ts/tests/structural-index.test.ts
rtk git commit -m "feat(ts/index): membership traversal primitives and dangling-member scan"
```

---

### Task 2: TypeScript Corpus traversal + dangling-member findings

**Files:**
- Modify: `ts/src/corpus.ts` (four methods + private helper after `neighbors()`; one block inside `check()`)
- Create: `ts/tests/corpus-traversal.test.ts`
- Modify: `ts/tests/corpus-check.test.ts` (append two tests)

**Interfaces:**
- Consumes (from Task 1): `Index.membersOf(uid): Set<string>`, `Index.containersOf(uid): Set<string>`, `Index.membershipClosure(uid, "members" | "containers"): Set<string>`, `Index.danglingMembers(): Array<{ sourceUid: string; ref: string }>`. Also existing `Corpus` privates `requireUid(ref): string` and `idFor(uid): string`, and `compareCodepoints` (already imported in `corpus.ts`).
- Produces (STANDARD-pinned public API; Task 5's parity test calls these):
  - `Corpus.members(ref: string): string[]`
  - `Corpus.containers(ref: string): string[]`
  - `Corpus.descendants(ref: string): string[]`
  - `Corpus.ancestors(ref: string): string[]`
  - `Corpus.check()` emits `{ severity: "warning", code: "dangling-member", ref: <container live id>, detail: <unresolved member ref>, message: … }`

- [ ] **Step 1: Write the failing traversal tests**

Create `ts/tests/corpus-traversal.test.ts`:

```ts
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Corpus } from "../src/corpus.js";
import { RefError } from "../src/errors.js";
import { makeNode } from "../src/node.js";
import { MEMBERSHIP } from "../src/shapes.js";

function tmpRoot(): string {
  return mkdtempSync(join(tmpdir(), "nodes-traversal-"));
}

function setNode(id: string, members: string[]) {
  return makeNode({ id, kind: "set", title: id, facets: { [MEMBERSHIP]: { members } } });
}

/** Registry-free corpus mirroring the fixture cluster: crate ⊃ box ⊃ {tidy, renamed};
 * box lists renamed under its deprecated id; crate lists a dangling note:ghost. */
function seeded(): Corpus {
  const c = new Corpus(tmpRoot());
  c.add(makeNode({ id: "note:renamed", kind: "note", title: "R", deprecatedIds: ["note:old-name"] }));
  c.add(makeNode({ id: "note:tidy", kind: "note", title: "T" }));
  c.add(setNode("set:box", ["note:tidy", "note:old-name"]));
  c.add(setNode("set:crate", ["set:box", "note:ghost"]));
  return c;
}

describe("Corpus — membership traversal", () => {
  it("members skips dangling refs", () => {
    expect(seeded().members("set:crate")).toEqual(["set:box"]);
  });

  it("members resolves deprecated member refs to sorted live ids", () => {
    expect(seeded().members("set:box")).toEqual(["note:renamed", "note:tidy"]);
  });

  it("members of a facet-less node is empty", () => {
    expect(seeded().members("note:tidy")).toEqual([]);
  });

  it("containers resolves a deprecated input ref", () => {
    expect(seeded().containers("note:old-name")).toEqual(["set:box"]);
  });

  it("containers reports direct containers only", () => {
    expect(seeded().containers("set:box")).toEqual(["set:crate"]);
  });

  it("descendants walks nesting transitively and skips dangling", () => {
    expect(seeded().descendants("set:crate")).toEqual(["note:renamed", "note:tidy", "set:box"]);
  });

  it("ancestors walks containers transitively", () => {
    expect(seeded().ancestors("note:renamed")).toEqual(["set:box", "set:crate"]);
  });

  it("cycles terminate and transitive results exclude the start node", () => {
    const c = new Corpus(tmpRoot());
    c.add(setNode("set:loop-a", ["set:loop-b"]));
    c.add(setNode("set:loop-b", ["set:loop-a"]));
    c.add(setNode("set:selfie", ["set:selfie"]));
    expect(c.descendants("set:loop-a")).toEqual(["set:loop-b"]);
    expect(c.ancestors("set:loop-b")).toEqual(["set:loop-a"]);
    expect(c.members("set:selfie")).toEqual(["set:selfie"]);
    expect(c.descendants("set:selfie")).toEqual([]);
    expect(c.ancestors("set:selfie")).toEqual([]);
  });

  it("all four methods reject an unresolvable input ref", () => {
    const c = seeded();
    for (const fn of ["members", "containers", "descendants", "ancestors"] as const) {
      expect(() => c[fn]("note:ghost")).toThrow(RefError);
    }
  });
});
```

- [ ] **Step 2: Write the failing check tests**

Append inside the existing `describe("Corpus.check", …)` block of `ts/tests/corpus-check.test.ts`, and add to its imports:

```ts
import { MEMBERSHIP } from "../src/shapes.js";
```

```ts
  it("reports a dangling member after a delete, deduped per (container, ref)", () => {
    const root = tmpRoot();
    const seed = new Corpus(root); // registry-free: dangling-member is registry-independent
    seed.add(makeNode({ id: "note:gone", kind: "note", title: "G" }));
    seed.add(
      makeNode({
        id: "set:box",
        kind: "set",
        title: "Box",
        facets: { [MEMBERSHIP]: { members: ["note:gone", "note:gone"] } },
      }),
    );
    seed.delete("note:gone");
    expect(tuples(seed.check())).toEqual([["warning", "dangling-member", "set:box", "note:gone"]]);
  });

  it("orders dangling-member with other findings by (ref, code, detail)", () => {
    const root = tmpRoot();
    const seed = new Corpus(root);
    seed.add(
      makeNode({
        id: "set:box",
        kind: "set",
        title: "Box",
        relations: [{ source: "set:box", predicate: "about", target: "topic:gone", directed: true }],
        facets: { [MEMBERSHIP]: { members: ["note:ghost"] } },
      }),
    );
    expect(tuples(seed.check())).toEqual([
      ["warning", "dangling-member", "set:box", "note:ghost"],
      ["warning", "dangling-ref", "set:box", "topic:gone"],
    ]);
  });
```

- [ ] **Step 3: Run tests to verify they fail**

Run (from `ts/`): `rtk npm test -- tests/corpus-traversal.test.ts tests/corpus-check.test.ts`
Expected: FAIL — `c.members is not a function`; check tests report missing `dangling-member` findings.

- [ ] **Step 4: Implement the Corpus methods and the check block**

In `ts/src/corpus.ts`, insert directly after the closing brace of `neighbors(...)`:

```ts
  private sortedLiveIds(uids: Iterable<string>): string[] {
    return [...uids].map((u) => this.idFor(u)).sort(compareCodepoints);
  }

  members(ref: string): string[] {
    return this.sortedLiveIds(this.index.membersOf(this.requireUid(ref)));
  }

  containers(ref: string): string[] {
    return this.sortedLiveIds(this.index.containersOf(this.requireUid(ref)));
  }

  descendants(ref: string): string[] {
    return this.sortedLiveIds(this.index.membershipClosure(this.requireUid(ref), "members"));
  }

  ancestors(ref: string): string[] {
    return this.sortedLiveIds(this.index.membershipClosure(this.requireUid(ref), "containers"));
  }
```

In `check(registry?)`, insert after the `for (const edge of this.index.danglingEdges()) { … }` loop and before `findings.sort(…)`:

```ts
    for (const { sourceUid, ref } of this.index.danglingMembers()) {
      const containerId = this.idFor(sourceUid);
      findings.push({
        severity: "warning",
        code: "dangling-member",
        ref: containerId,
        detail: ref,
        message: `${containerId}: member ${JSON.stringify(ref)} resolves to no live node`,
      });
    }
```

Also update the doc comment above `check` — replace the sentence fragment `unresolved top-level relation targets are warnings` with `unresolved top-level relation targets and unresolved membership member refs are warnings`.

- [ ] **Step 5: Run the gates**

Run (from `ts/`): `rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all PASS (existing suites unaffected — new code paths only).

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add ts/src/corpus.ts ts/tests/corpus-traversal.test.ts ts/tests/corpus-check.test.ts
rtk git commit -m "feat(ts/corpus): membership traversal API and dangling-member findings"
```

---

### Task 3: Python Index membership primitives

**Files:**
- Modify: `python/src/nodes/kernel/structural_index.py` (imports + methods on `class Index`, after `dangling_edges()`)
- Test: `python/tests/test_index.py` (append tests)

**Interfaces:**
- Consumes: existing `Index` internals — `by_uid: dict[str, IndexEntry]`, `in_refs: dict[str, list[InRef]]`, `resolve_uid(ref) -> str | None`, `_refs_for_uid(uid) -> list[str]` (raises `KeyError` on unknown uid — the module's existing dict convention), `OutRef.role`, `Literal` (already imported).
- Produces (Task 4 relies on these exact signatures):
  - `members_of(self, uid: str) -> set[str]`
  - `containers_of(self, uid: str) -> set[str]`
  - `membership_closure(self, uid: str, direction: Literal["members", "containers"]) -> set[str]`
  - `dangling_members(self) -> list[tuple[str, str]]` (rows are `(container uid, unresolved ref)`)

- [ ] **Step 1: Write the failing tests**

Append to `python/tests/test_index.py` (it already imports `pytest`, `Index`, `Node`, and `MEMBERSHIP as _MEMBERSHIP`):

```python
def _set_node(node_id: str, members: list[str], **extra) -> Node:
    return Node(id=node_id, kind="set", title=node_id, facets={_MEMBERSHIP: {"members": members}}, **extra)


def test_members_of_skips_dangling_and_resolves_deprecated():
    renamed = Node(id="note:renamed", kind="note", title="R", deprecated_ids=["note:old"])
    box = _set_node("set:box", ["note:old", "note:ghost"])
    idx = Index.build([renamed, box])
    assert idx.members_of(box.uid) == {renamed.uid}


def test_members_of_dedupes_duplicate_and_aliased_refs():
    renamed = Node(id="note:renamed", kind="note", title="R", deprecated_ids=["note:old"])
    box = _set_node("set:box", ["note:renamed", "note:old", "note:renamed"])
    idx = Index.build([renamed, box])
    assert idx.members_of(box.uid) == {renamed.uid}


def test_members_of_without_membership_facet_is_empty():
    plain = Node(id="note:plain", kind="note", title="P")
    idx = Index.build([plain])
    assert idx.members_of(plain.uid) == set()


def test_members_of_unknown_uid_raises_key_error():
    with pytest.raises(KeyError):
        Index().members_of("nope")


def test_containers_of_finds_live_and_deprecated_listings():
    renamed = Node(id="note:renamed", kind="note", title="R", deprecated_ids=["note:old"])
    by_live = _set_node("set:live", ["note:renamed"])
    by_dep = _set_node("set:dep", ["note:old"])
    idx = Index.build([renamed, by_live, by_dep])
    assert idx.containers_of(renamed.uid) == {by_live.uid, by_dep.uid}


def test_containers_of_uncontained_node_is_empty():
    plain = Node(id="note:plain", kind="note", title="P")
    idx = Index.build([plain])
    assert idx.containers_of(plain.uid) == set()


def test_membership_closure_walks_nesting_both_directions():
    leaf = Node(id="note:leaf", kind="note", title="L")
    box = _set_node("set:box", ["note:leaf"])
    crate = _set_node("set:crate", ["set:box"])
    idx = Index.build([leaf, box, crate])
    assert idx.membership_closure(crate.uid, "members") == {box.uid, leaf.uid}
    assert idx.membership_closure(leaf.uid, "containers") == {box.uid, crate.uid}


def test_membership_closure_cycles_terminate_and_exclude_start():
    a = _set_node("set:a", ["set:b"])
    b = _set_node("set:b", ["set:a"])
    selfie = _set_node("set:selfie", ["set:selfie"])
    idx = Index.build([a, b, selfie])
    assert idx.membership_closure(a.uid, "members") == {b.uid}
    assert idx.membership_closure(selfie.uid, "members") == set()
    assert idx.membership_closure(selfie.uid, "containers") == set()


def test_dangling_members_dedupes_per_container():
    box = _set_node("set:box", ["note:ghost", "note:ghost"])
    other = _set_node("set:other", ["note:ghost"])
    idx = Index.build([box, other])
    assert sorted(idx.dangling_members()) == sorted([(box.uid, "note:ghost"), (other.uid, "note:ghost")])


def test_dangling_members_empty_when_all_resolve():
    renamed = Node(id="note:renamed", kind="note", title="R", deprecated_ids=["note:old"])
    box = _set_node("set:box", ["note:old"])
    assert Index.build([renamed, box]).dangling_members() == []


def test_malformed_membership_facet_contributes_no_member_refs():
    # Parity fix pinned here: a string `members` value must NOT be iterated
    # character-by-character (TS guards with Array.isArray; Python must guard too,
    # or dangling_members() reports phantom single-character refs).
    weird = Node(id="note:weird", kind="note", title="W", facets={_MEMBERSHIP: {"members": "not-a-list"}})
    idx = Index.build([weird])
    assert idx.members_of(weird.uid) == set()
    assert idx.dangling_members() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `python/`): `uv run --frozen pytest tests/test_index.py -q`
Expected: FAIL — `AttributeError: 'Index' object has no attribute 'members_of'` (and siblings).

- [ ] **Step 3: Implement the four Index methods (and the malformed-members guard)**

In `python/src/nodes/kernel/structural_index.py`, add to the imports near the top (after `import math`):

```python
from collections import deque
```

In `_structural_out_refs`, guard the membership branch the way TypeScript's
`structuralOutRefs` already does (`Array.isArray`) — without this, a malformed string
`members` value is iterated character-by-character and `dangling_members()` reports
phantom refs. Replace:

```python
    mem = node.facets.get(MEMBERSHIP)
    if isinstance(mem, dict):
        for m in mem.get("members", []) or []:
            if isinstance(m, str):
                refs.append(OutRef(ref=m, role="membership_member"))
```

with:

```python
    mem = node.facets.get(MEMBERSHIP)
    if isinstance(mem, dict) and isinstance(mem.get("members"), list):
        for m in mem["members"]:
            if isinstance(m, str):
                refs.append(OutRef(ref=m, role="membership_member"))
```

Then append inside `class Index`, directly after `dangling_edges()`:

```python
    def members_of(self, uid: str) -> set[str]:
        """Uids of this node's resolvable direct members. Dangling member refs are skipped
        (check reports them); duplicate entries and live+deprecated refs dedupe by uid."""
        entry = self.by_uid[uid]
        members: set[str] = set()
        for oref in entry.out_refs:
            if oref.role != "membership_member":
                continue
            member_uid = self.resolve_uid(oref.ref)
            if member_uid is not None:
                members.add(member_uid)
        return members

    def containers_of(self, uid: str) -> set[str]:
        """Uids of the nodes whose membership facet lists any of this node's identity claims
        (live id or deprecated ids — the same attribution rule as _relations_by_role)."""
        containers: set[str] = set()
        for ref in self._refs_for_uid(uid):
            for inref in self.in_refs.get(ref, []):
                if inref.out_ref.role != "membership_member":
                    continue
                containers.add(inref.source_uid)
        return containers

    def membership_closure(self, uid: str, direction: Literal["members", "containers"]) -> set[str]:
        """Transitive membership closure (BFS). The visited set is seeded with the start uid,
        which is excluded from the result even when a membership cycle reaches it."""
        step = self.members_of if direction == "members" else self.containers_of
        visited: set[str] = {uid}
        queue: deque[str] = deque([uid])
        while queue:
            current = queue.popleft()
            for nxt in step(current):
                if nxt in visited:
                    continue
                visited.add(nxt)
                queue.append(nxt)
        visited.discard(uid)
        return visited

    def dangling_members(self) -> list[tuple[str, str]]:
        """Every unresolved membership ref, deduped by (container uid, ref)."""
        out: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for entry in self.by_uid.values():
            for oref in entry.out_refs:
                if oref.role != "membership_member":
                    continue
                if self.resolve_uid(oref.ref) is not None:
                    continue
                key = (entry.uid, oref.ref)
                if key in seen:
                    continue
                seen.add(key)
                out.append(key)
        return out
```

- [ ] **Step 4: Run the gates**

Run (from `python/`): `uv run --frozen pytest -q && uv run --frozen ruff check . && uv run --frozen pyright src`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes
rtk git add python/src/nodes/kernel/structural_index.py python/tests/test_index.py
rtk git commit -m "feat(py/index): membership traversal primitives and dangling-member scan"
```

---

### Task 4: Python Corpus traversal + dangling-member findings

**Files:**
- Modify: `python/src/nodes/kernel/corpus.py` (imports; four methods + private helper after `neighbors()`; one block inside `check()`)
- Create: `python/tests/test_corpus_traversal.py`
- Modify: `python/tests/test_corpus_check.py` (append two tests)

**Interfaces:**
- Consumes (from Task 3): `Index.members_of(uid) -> set[str]`, `Index.containers_of(uid) -> set[str]`, `Index.membership_closure(uid, direction) -> set[str]`, `Index.dangling_members() -> list[tuple[str, str]]`. Also existing `Corpus._require_uid(ref) -> str` and `self.index.by_uid[uid].id`.
- Produces (STANDARD-pinned public API; Task 5's parity test calls these):
  - `Corpus.members(ref: str) -> list[str]`
  - `Corpus.containers(ref: str) -> list[str]`
  - `Corpus.descendants(ref: str) -> list[str]`
  - `Corpus.ancestors(ref: str) -> list[str]`
  - `Corpus.check()` emits `Finding(severity="warning", code="dangling-member", ref=<container live id>, detail=<unresolved member ref>, message=…)`

- [ ] **Step 1: Write the failing traversal tests**

Create `python/tests/test_corpus_traversal.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import RefError
from nodes.kernel.node import Node
from nodes.kernel.shapes import MEMBERSHIP


def _set_node(node_id: str, members: list[str]) -> Node:
    return Node(id=node_id, kind="set", title=node_id, facets={MEMBERSHIP: {"members": members}})


def _seeded(tmp_path) -> Corpus:
    """Registry-free corpus mirroring the fixture cluster: crate ⊃ box ⊃ {tidy, renamed};
    box lists renamed under its deprecated id; crate lists a dangling note:ghost."""
    c = Corpus(tmp_path)
    c.add(Node(id="note:renamed", kind="note", title="R", deprecated_ids=["note:old-name"]))
    c.add(Node(id="note:tidy", kind="note", title="T"))
    c.add(_set_node("set:box", ["note:tidy", "note:old-name"]))
    c.add(_set_node("set:crate", ["set:box", "note:ghost"]))
    return c


def test_members_skips_dangling(tmp_path):
    assert _seeded(tmp_path).members("set:crate") == ["set:box"]


def test_members_resolves_deprecated_refs_to_sorted_live_ids(tmp_path):
    assert _seeded(tmp_path).members("set:box") == ["note:renamed", "note:tidy"]


def test_members_of_facetless_node_is_empty(tmp_path):
    assert _seeded(tmp_path).members("note:tidy") == []


def test_containers_resolves_deprecated_input_ref(tmp_path):
    assert _seeded(tmp_path).containers("note:old-name") == ["set:box"]


def test_containers_reports_direct_containers_only(tmp_path):
    assert _seeded(tmp_path).containers("set:box") == ["set:crate"]


def test_descendants_walks_nesting_and_skips_dangling(tmp_path):
    assert _seeded(tmp_path).descendants("set:crate") == ["note:renamed", "note:tidy", "set:box"]


def test_ancestors_walks_containers_transitively(tmp_path):
    assert _seeded(tmp_path).ancestors("note:renamed") == ["set:box", "set:crate"]


def test_cycles_terminate_and_exclude_start(tmp_path):
    c = Corpus(tmp_path)
    c.add(_set_node("set:loop-a", ["set:loop-b"]))
    c.add(_set_node("set:loop-b", ["set:loop-a"]))
    c.add(_set_node("set:selfie", ["set:selfie"]))
    assert c.descendants("set:loop-a") == ["set:loop-b"]
    assert c.ancestors("set:loop-b") == ["set:loop-a"]
    assert c.members("set:selfie") == ["set:selfie"]
    assert c.descendants("set:selfie") == []
    assert c.ancestors("set:selfie") == []


def test_all_four_reject_unresolvable_input_ref(tmp_path):
    c = _seeded(tmp_path)
    for fn in (c.members, c.containers, c.descendants, c.ancestors):
        with pytest.raises(RefError):
            fn("note:ghost")
```

- [ ] **Step 2: Write the failing check tests**

Append to `python/tests/test_corpus_check.py`, and add to its imports:

```python
from nodes.kernel.shapes import MEMBERSHIP
```

```python
def test_dangling_member_reported_after_delete_and_deduped(tmp_path):
    seed = Corpus(tmp_path)  # registry-free: dangling-member is registry-independent
    seed.add(Node(id="note:gone", kind="note", title="G"))
    seed.add(Node(id="set:box", kind="set", title="Box",
                  facets={MEMBERSHIP: {"members": ["note:gone", "note:gone"]}}))
    seed.delete("note:gone")
    assert _tuples(seed.check()) == [("warning", "dangling-member", "set:box", "note:gone")]


def test_dangling_member_orders_with_other_findings(tmp_path):
    seed = Corpus(tmp_path)
    seed.add(Node(id="set:box", kind="set", title="Box",
                  relations=[Relation(source="set:box", predicate="about", target="topic:gone")],
                  facets={MEMBERSHIP: {"members": ["note:ghost"]}}))
    assert _tuples(seed.check()) == [
        ("warning", "dangling-member", "set:box", "note:ghost"),
        ("warning", "dangling-ref", "set:box", "topic:gone"),
    ]
```

- [ ] **Step 3: Run tests to verify they fail**

Run (from `python/`): `uv run --frozen pytest tests/test_corpus_traversal.py tests/test_corpus_check.py -q`
Expected: FAIL — `AttributeError: 'Corpus' object has no attribute 'members'`; the check tests miss the `dangling-member` rows.

- [ ] **Step 4: Implement the Corpus methods and the check block**

In `python/src/nodes/kernel/corpus.py`, add to the imports (after `from pathlib import Path`):

```python
from collections.abc import Iterable
```

Insert directly after `neighbors(...)`:

```python
    def _sorted_live_ids(self, uids: Iterable[str]) -> list[str]:
        return sorted(self.index.by_uid[u].id for u in uids)

    def members(self, ref: str) -> list[str]:
        return self._sorted_live_ids(self.index.members_of(self._require_uid(ref)))

    def containers(self, ref: str) -> list[str]:
        return self._sorted_live_ids(self.index.containers_of(self._require_uid(ref)))

    def descendants(self, ref: str) -> list[str]:
        return self._sorted_live_ids(self.index.membership_closure(self._require_uid(ref), "members"))

    def ancestors(self, ref: str) -> list[str]:
        return self._sorted_live_ids(self.index.membership_closure(self._require_uid(ref), "containers"))
```

(Python `sorted()` on `str` compares by code point — no custom comparator needed, matching TS `compareCodepoints`.)

In `check(...)`, insert after the `for edge in self.index.dangling_edges(): …` loop and before `findings.sort(...)`:

```python
        for source_uid, ref in self.index.dangling_members():
            container_id = self.index.by_uid[source_uid].id
            findings.append(
                Finding(
                    severity="warning",
                    code="dangling-member",
                    ref=container_id,
                    detail=ref,
                    message=f"{container_id}: member {ref!r} resolves to no live node",
                )
            )
```

Also update the `check` docstring — replace `unresolved top-level relation targets are warnings` with `unresolved top-level relation targets and unresolved membership member refs are warnings`.

- [ ] **Step 5: Run the gates**

Run (from `python/`): `uv run --frozen pytest -q && uv run --frozen ruff check . && uv run --frozen pyright src`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add python/src/nodes/kernel/corpus.py python/tests/test_corpus_traversal.py python/tests/test_corpus_check.py
rtk git commit -m "feat(py/corpus): membership traversal API and dangling-member findings"
```

---

### Task 5: Shared fixtures, oracles, and parity tests

**Files:**
- Create: `fixtures/check-corpus/set/crate.md`, `fixtures/check-corpus/set/box.md`, `fixtures/check-corpus/set/loop-a.md`, `fixtures/check-corpus/set/loop-b.md`, `fixtures/check-corpus/set/selfie.md`, `fixtures/check-corpus/note/renamed.md`
- Modify: `fixtures/check.oracle.json`
- Create: `fixtures/traversal.oracle.json`
- Create: `ts/tests/traversal_parity.test.ts`
- Create: `python/tests/test_traversal_parity.py`
- Modify: `ts/tests/check_parity.test.ts` (node count 7 → 13)
- Modify: `python/tests/test_check_parity.py` (node count 7 → 13)

**Interfaces:**
- Consumes: `Corpus.members/containers/descendants/ancestors(ref) -> sorted live ids` (Tasks 2 & 4) and the `dangling-member` finding (Tasks 2 & 4). The conformance registry (`registerBuiltinShapes` / `register_builtin_shapes`) already registers the `set` convenience kind (required facet: `membership`), so the new fixture nodes are registry-valid.
- Produces: the frozen cross-language contract — `fixtures/check.oracle.json` (7 rows) and `fixtures/traversal.oracle.json` (12 rows). Task 6's STANDARD text references both.

- [ ] **Step 1: Add the six fixture nodes**

Create `fixtures/check-corpus/set/crate.md`:

```markdown
---
id: set:crate
uid: "11111111111111111111111111111111"
kind: set
title: Crate
facets:
  membership:
    members:
    - set:box
    - note:ghost
---
Nesting root; its second member resolves to no node (dangling-member).
```

Create `fixtures/check-corpus/set/box.md`:

```markdown
---
id: set:box
uid: "22222222222222222222222222222222"
kind: set
title: Box
facets:
  membership:
    members:
    - note:tidy
    - note:old-name
---
Mid container; its second member is listed under a deprecated id.
```

Create `fixtures/check-corpus/set/loop-a.md`:

```markdown
---
id: set:loop-a
uid: "33333333333333333333333333333333"
kind: set
title: Loop A
facets:
  membership:
    members:
    - set:loop-b
---
Half of a two-node membership cycle.
```

Create `fixtures/check-corpus/set/loop-b.md`:

```markdown
---
id: set:loop-b
uid: "44444444444444444444444444444444"
kind: set
title: Loop B
facets:
  membership:
    members:
    - set:loop-a
---
Half of a two-node membership cycle.
```

Create `fixtures/check-corpus/set/selfie.md`:

```markdown
---
id: set:selfie
uid: "55555555555555555555555555555555"
kind: set
title: Selfie
facets:
  membership:
    members:
    - set:selfie
---
Directly self-membered: in its own members, excluded from its own descendants.
```

Create `fixtures/check-corpus/note/renamed.md`:

```markdown
---
id: note:renamed
uid: "66666666666666666666666666666666"
kind: note
title: Renamed
deprecated_ids:
- note:old-name
---
A valid note reachable via its deprecated id.
```

(`note:ghost` deliberately does not exist. The pinned uids avoid the seven existing fixture uids — `aaaa…`, `bbbb…`, `cccc…`, `dddd…`, `eeee…`, `ffff…`, `1212…`.)

- [ ] **Step 2: Update the check oracle**

Replace the full contents of `fixtures/check.oracle.json` (one new `set:crate` row, in `(ref, code, detail)` code-point order between `paper:typo` and `zzz:mystery`):

```json
[
  { "severity": "error", "code": "facet-unexpected", "ref": "note:stray", "detail": "source" },
  { "severity": "warning", "code": "dangling-ref", "ref": "paper:broken", "detail": "paper:ghost" },
  { "severity": "error", "code": "facet-missing", "ref": "paper:broken", "detail": "source" },
  { "severity": "error", "code": "invariant-violated", "ref": "paper:empty", "detail": "" },
  { "severity": "error", "code": "facet-invalid", "ref": "paper:typo", "detail": "" },
  { "severity": "warning", "code": "dangling-member", "ref": "set:crate", "detail": "note:ghost" },
  { "severity": "error", "code": "unknown-kind", "ref": "zzz:mystery", "detail": "zzz" }
]
```

- [ ] **Step 3: Create the traversal oracle**

Create `fixtures/traversal.oracle.json`:

```json
[
  { "op": "members", "ref": "set:crate", "expect": ["set:box"] },
  { "op": "members", "ref": "set:box", "expect": ["note:renamed", "note:tidy"] },
  { "op": "members", "ref": "note:tidy", "expect": [] },
  { "op": "containers", "ref": "note:tidy", "expect": ["set:box"] },
  { "op": "containers", "ref": "note:old-name", "expect": ["set:box"] },
  { "op": "containers", "ref": "set:box", "expect": ["set:crate"] },
  { "op": "descendants", "ref": "set:crate", "expect": ["note:renamed", "note:tidy", "set:box"] },
  { "op": "ancestors", "ref": "note:renamed", "expect": ["set:box", "set:crate"] },
  { "op": "descendants", "ref": "set:loop-a", "expect": ["set:loop-b"] },
  { "op": "ancestors", "ref": "set:loop-b", "expect": ["set:loop-a"] },
  { "op": "members", "ref": "set:selfie", "expect": ["set:selfie"] },
  { "op": "descendants", "ref": "set:selfie", "expect": [] }
]
```

- [ ] **Step 4: Write the TypeScript parity test and update the count**

Create `ts/tests/traversal_parity.test.ts`:

```ts
import { cpSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { Corpus } from "../src/index.js";

const FIXTURES = fileURLToPath(new URL("../../fixtures", import.meta.url));

interface OracleRow {
  op: "members" | "containers" | "descendants" | "ancestors";
  ref: string;
  expect: string[];
}

function copiedCorpus(): string {
  const root = join(mkdtempSync(join(tmpdir(), "nodes-traversal-parity-")), "check-corpus");
  cpSync(join(FIXTURES, "check-corpus"), root, { recursive: true });
  return root;
}

describe("traversal parity", () => {
  it("membership traversal matches the committed oracle", () => {
    // Cross-language freeze: same fixture + oracle as the Python kernel. Traversal is
    // registry-independent, so the corpus is constructed without a registry.
    const corpus = new Corpus(copiedCorpus());
    const oracle: OracleRow[] = JSON.parse(readFileSync(join(FIXTURES, "traversal.oracle.json"), "utf-8"));
    expect(oracle.length).toBeGreaterThan(0);
    for (const row of oracle) {
      expect(corpus[row.op](row.ref), `${row.op}(${row.ref})`).toEqual(row.expect);
    }
  });
});
```

In `ts/tests/check_parity.test.ts`, replace:

```ts
  it("fixture corpus has seven nodes", () => {
    expect(new Corpus(copiedCorpus()).all()).toHaveLength(7);
  });
```

with:

```ts
  it("fixture corpus has thirteen nodes", () => {
    expect(new Corpus(copiedCorpus()).all()).toHaveLength(13);
  });
```

- [ ] **Step 5: Write the Python parity test and update the count**

Create `python/tests/test_traversal_parity.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

from nodes.kernel.corpus import Corpus

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "check-corpus"
ORACLE = FIXTURES / "traversal.oracle.json"


def test_membership_traversal_matches_committed_oracle(tmp_path):
    # Cross-language freeze: same fixture + oracle as the TypeScript kernel. Traversal
    # is registry-independent, so the corpus is constructed without a registry.
    corpus_dir = tmp_path / "check-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    corpus = Corpus(corpus_dir)
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle, "oracle must not be empty"
    for row in oracle:
        assert getattr(corpus, row["op"])(row["ref"]) == row["expect"], f"{row['op']}({row['ref']})"
```

In `python/tests/test_check_parity.py`, replace:

```python
def test_check_corpus_has_seven_nodes(tmp_path):
    corpus_dir = tmp_path / "check-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    assert len(Corpus(corpus_dir).all()) == 7
```

with:

```python
def test_check_corpus_has_thirteen_nodes(tmp_path):
    corpus_dir = tmp_path / "check-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    assert len(Corpus(corpus_dir).all()) == 13
```

- [ ] **Step 6: Run both languages' full gates**

Run (from `ts/`): `rtk npm test && rtk npm run typecheck && rtk npm run check`
Run (from `python/`): `uv run --frozen pytest -q && uv run --frozen ruff check . && uv run --frozen pyright src`
Expected: all PASS — in particular `check_parity` / `test_check_parity` now see the `dangling-member` oracle row produced by both kernels, and both traversal parity tests pass against the same oracle.

- [ ] **Step 7: Commit**

```bash
cd ~/d/nodes
rtk git add fixtures/check-corpus/set fixtures/check-corpus/note/renamed.md fixtures/check.oracle.json fixtures/traversal.oracle.json ts/tests/traversal_parity.test.ts python/tests/test_traversal_parity.py ts/tests/check_parity.test.ts python/tests/test_check_parity.py
rtk git commit -m "test: membership cluster fixture + traversal and check oracles"
```

---

### Task 6: STANDARD 1.1 + downstream build

**Files:**
- Modify: `docs/STANDARD.md` (header, §7, §8.2, §11.2, §12, §13)
- Verify (no commit): `ts/` build output consumed by `~/d/mindful/v6` via its `@nodes/kernel` symlink

**Interfaces:**
- Consumes: the shipped behavior of Tasks 1–5 (this task documents it; no code changes).
- Produces: STANDARD spec version 1.1 — the normative text future work cites.

- [ ] **Step 1: Update the header version**

In `docs/STANDARD.md`, replace:

```markdown
- **Spec version:** 1.0
```

with:

```markdown
- **Spec version:** 1.1
```

- [ ] **Step 2: Add the §7 membership-traversal bullet**

In §7 (Corpus semantics), directly after the bullet beginning `- Graph queries (`outbound`, `inbound`, `neighbors`, `dangling`) are relations-only…`, insert:

```markdown
- Membership traversal (`members`, `containers`, `descendants`, `ancestors`) exposes
  the containment graph over `membership.members` refs. Each method MUST resolve its
  input ref (live then deprecated; `RefError` when it resolves to no live node — the
  only raising path) and return a sorted (Unicode code point), uid-deduplicated list
  of **live ids**. `members` / `containers` read one hop — the literal facet content,
  resolved, so a container listing itself appears in its own `members`;
  `descendants` / `ancestors` are the transitive closures over one-or-more hops and
  MUST exclude the start node, even when a membership cycle makes it reachable from
  itself. Member refs listed under deprecated ids resolve normally; dangling member
  refs are silently skipped (`check` reports them, §8.2). Traversal MUST be
  cycle-safe for every shape: `dag` / `tree` acyclicity constrains only a container's
  internal `edges` facet, so cross-node membership containment cycles are legal. A
  node without a membership facet has no members; a node no container lists has no
  containers — both are empty results, never errors.
```

- [ ] **Step 3: Add the finding to §8.2**

In the §8.2 findings table, after the `dangling-ref` row, add:

```markdown
| `dangling-member` | warning | member ref | a `membership.members` entry resolves to no live node (`ref` = the container node) |
```

Then replace the bullet:

```markdown
- Always (registry or not), the exhaustive list of structural findings: one
  `dangling-ref` per unresolved top-level relation target — exactly the edges
  `dangling()` reports. Malformed structural facet payloads are a registry concern
  (shape invariants); dangling *membership* refs are deferred (§13).
```

with:

```markdown
- Always (registry or not), the exhaustive list of structural findings: one
  `dangling-ref` per unresolved top-level relation target — exactly the edges
  `dangling()` reports — and one `dangling-member` per unresolved
  `(container, member ref)` pair, deduplicated (a duplicated dangling entry reports
  once). A member listed under a deprecated-but-resolvable id is not dangling.
  Malformed structural facet payloads remain a registry concern (shape invariants).
```

- [ ] **Step 4: Update the §11.2 fixture inventory**

Replace the table row:

```markdown
| `check-corpus/`, `check.oracle.json` | corpus-validity findings (severity, code, ref, detail) |
```

with:

```markdown
| `check-corpus/`, `check.oracle.json` | corpus-validity findings (severity, code, ref, detail); includes a membership cluster (nesting, a cycle, self-membership, one dangling member) |
| `traversal.oracle.json` | membership traversal (`members` / `containers` / `descendants` / `ancestors`) over `check-corpus/` |
```

- [ ] **Step 5: Update §12 history and §13**

In §12, replace:

```markdown
- History: **1.0** (2026-07-10) — initial consolidation; adds §8 corpus validity.
```

with:

```markdown
- History: **1.0** (2026-07-10) — initial consolidation; adds §8 corpus validity.
  **1.1** (2026-07-11) — membership traversal (§7); `dangling-member` finding (§8.2).
```

In §13, delete the first bullet (the three lines):

```markdown
- No public membership-graph traversal (tree descendants, DAG reachability); membership
  refs are tracked for rename/dangling integrity but not exposed as graph edges, and
  dangling membership refs are not yet reported by `check`.
```

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add docs/STANDARD.md
rtk git commit -m "docs: STANDARD 1.1 — membership traversal + dangling-member finding"
```

- [ ] **Step 7: Rebuild the TS dist and smoke-check mindful**

`~/d/mindful/v6` consumes the TS kernel's built `dist/` through its `@nodes/kernel` symlink, so rebuild and run its suite (no commits — verification only):

```bash
cd ~/d/nodes/ts && rtk npm run build
cd ~/d/mindful/v6 && rtk npm test
```

Expected: build succeeds; mindful's full vitest suite passes (the kernel change is additive, so no mindful code changes are needed).
