# nodes — Structural Index (Plan 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-memory, incrementally-maintained structural index (O(1) id/deprecated-id→uid resolution + a resolved relations graph) to the `nodes` kernel, and route all corpus mutations through a new `Corpus` coordinator so the kernel's linear scans are retired.

**Architecture:** A new domain-free `Index` (pure in-memory maps, no file I/O) and a `Corpus` coordinator that owns a `Store` + an `Index`. The existing `Store` is slimmed to pure file mechanics; its cross-corpus logic (`resolve` deprecated-scan, collision detection, `rename` + ref-rewrites) migrates up into `Corpus`/`Index`. Resolution and graph queries become uid-based and O(degree); `rename` rewrites only the referrers the reverse index names.

**Tech Stack:** Python ≥3.11, Pydantic v2, PyYAML, `uv` (runner), pytest, ruff (line-length 120), pyright (basic), `src/` layout. Index/Corpus add **no** new third-party dependencies.

**Spec:** `docs/specs/2026-06-21-nodes-structural-index-design.md` (approved). Read it for rationale; this plan is self-contained for implementation.

## Global Constraints

- Every module starts with `from __future__ import annotations`.
- Python ≥3.11; Pydantic v2; PyYAML; no new third-party dependencies in this plan.
- Run everything through `uv`: `uv run pytest`, `uv run ruff check .`, `uv run pyright src`.
- ruff line-length is 120; code must pass `ruff check .` and `pyright src` clean.
- The index lives in `nodes.kernel` (it is domain-free). No `nodes.vocab` / `nodes.domains` code in this plan.
- **No compatibility/legacy shim.** When logic moves out of `Store`, delete it from `Store`; do not leave deprecated wrappers. This is a greenfield, local-only repo with no external consumers.
- **Public graph queries are relations-only.** `outbound`/`inbound`/`dangling`/`neighbors` expose `Relation`-primitive edges only. Membership members/edges are tracked internally for rename completeness but are NOT exposed as public graph edges.
- **`rename` is live-id-only** (raises `RefError` on an unknown or deprecated `old_id`), consistent with `delete`.
- **Resolution order:** a live id always wins over a deprecated id.
- Reuse the existing `nodes.kernel.errors` classes (`RefError`, `CollisionError`); add no new error types.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit.

---

## File Structure

- `src/nodes/kernel/store.py` — **modified** (slimmed to file mechanics).
- `src/nodes/kernel/index.py` — **created** (`Index` + value types).
- `src/nodes/kernel/corpus.py` — **created** (`Corpus` coordinator).
- `tests/test_store.py` — **modified** (shrunk to file mechanics).
- `tests/test_index.py` — **created**.
- `tests/test_corpus.py` — **created**.
- `tests/test_index_rebuild_equivalence.py` — **created** (the §6 property test).
- `docs/format.md` — **modified** (update the "known limitations" section).

Existing modules consumed as-is: `node.py` (`Node`), `relations.py` (`Relation`, `relates_to`, `RELATES_TO`), `ids.py` (`NodeId`), `shapes.py` (`MEMBERSHIP`), `frontmatter.py` (`node_from_markdown`, `node_to_markdown`).

---

## Task 1: Slim `Store` to file mechanics

**Files:**
- Modify: `src/nodes/kernel/store.py` (replace entire file)
- Modify: `tests/test_store.py` (replace entire file)

**Interfaces:**
- Consumes: `Node` (`nodes.kernel.node`), `node_from_markdown`/`node_to_markdown` (`nodes.kernel.frontmatter`), `NodeId` (`nodes.kernel.ids`), `RefError` (`nodes.kernel.errors`).
- Produces (used by Tasks 4–5):
  - `Store(root: Path)`
  - `Store.path_for(node_id: str) -> Path`
  - `Store.write_file(node: Node) -> Path` — mechanical write, NO collision check
  - `Store.read_file(node_id: str) -> Node` — by `path_for(node_id)` only; `RefError` if no file
  - `Store.delete_file(node_id: str) -> None` — unlink; `RefError` if absent
  - `Store.all_nodes() -> list[Node]` — corpus scan, sorted by path

- [ ] **Step 1: Replace `tests/test_store.py` with file-mechanics-only tests**

The collision/resolve/rename tests move up to `Corpus` (Tasks 4–5). `Store` now only knows files.

```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import RefError
from nodes.kernel.node import Node
from nodes.kernel.store import Store


def test_write_file_read_file_roundtrip(tmp_path):
    store = Store(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A", body="hi")
    store.write_file(n)
    got = store.read_file("topic:a")
    assert got.title == "A" and got.body == "hi" and got.uid == n.uid


def test_write_file_has_no_collision_check(tmp_path):
    # Store is a dumb primitive: writing a different uid at the same id just overwrites.
    store = Store(tmp_path)
    store.write_file(Node(id="topic:a", kind="topic", title="A"))
    store.write_file(Node(id="topic:a", kind="topic", title="Other"))  # no raise
    assert store.read_file("topic:a").title == "Other"


def test_path_for_encodes_curie_slug(tmp_path):
    store = Store(tmp_path)
    path = store.path_for("gene:HGNC:PHF19")
    assert path == tmp_path / "gene" / "HGNC__PHF19.md"


def test_read_file_missing_raises(tmp_path):
    with pytest.raises(RefError):
        Store(tmp_path).read_file("topic:ghost")


def test_delete_file_removes_then_missing_raises(tmp_path):
    store = Store(tmp_path)
    store.write_file(Node(id="topic:a", kind="topic", title="A"))
    store.delete_file("topic:a")
    with pytest.raises(RefError):
        store.read_file("topic:a")
    with pytest.raises(RefError):
        store.delete_file("topic:a")


def test_all_nodes_scans_corpus_sorted(tmp_path):
    store = Store(tmp_path)
    store.write_file(Node(id="topic:b", kind="topic", title="B"))
    store.write_file(Node(id="topic:a", kind="topic", title="A"))
    ids = [n.id for n in store.all_nodes()]
    assert ids == ["topic:a", "topic:b"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `AttributeError` (`write_file`/`read_file`/`delete_file` not defined on the old `Store`).

- [ ] **Step 3: Replace `src/nodes/kernel/store.py` with the slimmed version**

```python
from __future__ import annotations

from pathlib import Path

from nodes.kernel.errors import RefError
from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown
from nodes.kernel.ids import NodeId
from nodes.kernel.node import Node


class Store:
    """Pure file mechanics over a corpus directory. No cross-corpus logic.

    Collision detection, ref resolution, and rename live in `Corpus`/`Index`.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, node_id: str) -> Path:
        nid = NodeId.parse(node_id)
        return self.root / nid.kind / f"{nid.slug.replace(':', '__')}.md"

    def write_file(self, node: Node) -> Path:
        path = self.path_for(node.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(node_to_markdown(node), encoding="utf-8")
        return path

    def read_file(self, node_id: str) -> Node:
        path = self.path_for(node_id)
        if not path.is_file():
            raise RefError(f"no node at {node_id!r}")
        return node_from_markdown(path.read_text(encoding="utf-8"))

    def delete_file(self, node_id: str) -> None:
        path = self.path_for(node_id)
        if not path.is_file():
            raise RefError(f"no node at {node_id!r}")
        path.unlink()

    def all_nodes(self) -> list[Node]:
        return [node_from_markdown(p.read_text(encoding="utf-8")) for p in sorted(self.root.rglob("*.md"))]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Confirm nothing else imports the removed methods**

Run: `uv run pytest -q`
Expected: `test_store.py` passes. Other suites unaffected (only `test_store.py` imported `Store`). If any collection error mentions `Store.write`/`resolve`/`rename`, it is a stale reference — fix it before committing.

Run: `uv run ruff check . && uv run pyright src`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/nodes/kernel/store.py tests/test_store.py
git commit -m "refactor(store): slim Store to file mechanics; cross-corpus logic moves to Corpus"
```

---

## Task 2: `Index` core — entries, resolution, collision, maintenance

**Files:**
- Create: `src/nodes/kernel/index.py`
- Create: `tests/test_index.py`

**Interfaces:**
- Consumes: `Node` (`nodes.kernel.node`), `Relation` (`nodes.kernel.relations`), `MEMBERSHIP` (`nodes.kernel.shapes`), `CollisionError` (`nodes.kernel.errors`).
- Produces (used by Task 3 graph queries and Tasks 4–5):
  - Value types `OutRef`, `InRef`, `IndexEntry`, `ResolvedEdge` (dataclasses).
  - `Index()` with public maps: `by_uid: dict[str, IndexEntry]`, `id_to_uid: dict[str, str]`, `deprecated_to_uid: dict[str, str]`, `in_refs: dict[str, list[InRef]]`.
  - `Index.build(nodes) -> Index` (classmethod)
  - `Index.upsert(node: Node) -> None` — mechanical, replace-safe, non-raising
  - `Index.remove(uid: str) -> None` — drops the node's OWN contributions only
  - `Index.resolve_uid(ref: str) -> str | None` — id first, then deprecated id
  - `Index.assert_addable(node: Node) -> None` — raises `CollisionError` (the collision gate)

**Design notes for the implementer:**
- `upsert` is the mechanical maintenance op: it never raises on collision. The collision *gate* is the separate `assert_addable`, which `Corpus.add` calls **before** writing the file (so the index never gets ahead of disk). This split is deliberate: `rename` legitimately re-`upsert`s a node whose live id changed, which must not trip a collision.
- Relations are normalized (source always explicit), so a plain `related:` entry has `source == node.id`. Each `Relation` contributes two `OutRef`s (`relation_source`, `relation_target`); membership members and each edge endpoint contribute their own `OutRef`s. This completeness is what makes `rename` O(degree).
- `remove(uid)` drops only what this node contributed: its `by_uid` entry, its identity claims, and the `in_refs` rows whose `source_uid == uid`. It must NOT drop `in_refs` rows other nodes contributed pointing at this node — those persist as dangling.
- `build()` enforces the collision contract: it calls `assert_addable` before each `upsert`, so constructing a `Corpus` over a corrupt corpus (two files claiming the same id) fails early rather than letting the last file silently win.
- **Membership facet payloads are raw dicts** — the canonical on-disk form. `node.facets["membership"]["edges"]` are plain dicts with string `source`/`target` (this is what `node_to_markdown` yaml-dumps and `node_from_markdown` reads back; `Relation` objects could not serialize there). `_extract_out_refs` therefore reads edges as dicts, by design — do not add a `Relation`-object branch.

- [ ] **Step 1: Write `tests/test_index.py`**

```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import CollisionError
from nodes.kernel.index import Index
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to


def test_build_and_resolve_live_id():
    idx = Index.build([Node(id="topic:a", kind="topic", title="A")])
    uid = idx.id_to_uid["topic:a"]
    assert idx.resolve_uid("topic:a") == uid
    assert idx.resolve_uid("topic:missing") is None


def test_resolve_deprecated_id():
    a = Node(id="topic:new", kind="topic", title="A", deprecated_ids=["topic:old"])
    idx = Index.build([a])
    assert idx.resolve_uid("topic:old") == a.uid  # deprecated id resolves to A


def test_resolve_prefers_live_over_deprecated_map():
    # White-box: a live id always wins over a deprecated id. In a valid corpus a
    # ref appears in only one map; this asserts the lookup order directly.
    idx = Index()
    idx.id_to_uid["topic:x"] = "uid-live"
    idx.deprecated_to_uid["topic:x"] = "uid-dep"
    assert idx.resolve_uid("topic:x") == "uid-live"


def test_build_rejects_colliding_corpus():
    a = Node(id="topic:a", kind="topic", title="A")
    b = Node(id="topic:a", kind="topic", title="B")  # same id, different uid → corrupt corpus
    with pytest.raises(CollisionError):
        Index.build([a, b])


def test_assert_addable_rejects_same_id_different_uid():
    idx = Index.build([Node(id="topic:a", kind="topic", title="A")])
    with pytest.raises(CollisionError):
        idx.assert_addable(Node(id="topic:a", kind="topic", title="Other"))


def test_assert_addable_rejects_same_uid_different_id():
    a = Node(id="topic:a", kind="topic", title="A")
    idx = Index.build([a])
    with pytest.raises(CollisionError):
        idx.assert_addable(Node(id="topic:b", kind="topic", title="B", uid=a.uid))


def test_assert_addable_rejects_deprecated_id_claim():
    idx = Index.build([Node(id="topic:a", kind="topic", title="A")])
    with pytest.raises(CollisionError):
        idx.assert_addable(Node(id="topic:b", kind="topic", title="B", deprecated_ids=["topic:a"]))


def test_assert_addable_allows_same_uid_same_id_overwrite():
    a = Node(id="topic:a", kind="topic", title="A")
    idx = Index.build([a])
    idx.assert_addable(Node(id="topic:a", kind="topic", title="A2", uid=a.uid))  # no raise


def test_upsert_replace_is_clean():
    a = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:x")])
    idx = Index.build([a])
    assert any(r.out_ref.ref == "topic:x" for r in idx.in_refs.get("topic:x", []))
    a2 = Node(id="topic:a", kind="topic", title="A", uid=a.uid,
              relations=[relates_to("topic:a", "topic:y")])
    idx.upsert(a2)
    # old outbound ref to topic:x is gone; new one to topic:y is present
    assert idx.in_refs.get("topic:x") in (None, [])
    assert any(r.out_ref.ref == "topic:y" for r in idx.in_refs.get("topic:y", []))


def test_remove_keeps_surviving_referrers_inbound():
    target = Node(id="topic:t", kind="topic", title="T")
    referrer = Node(id="topic:r", kind="topic", title="R",
                    relations=[relates_to("topic:r", "topic:t")])
    idx = Index.build([target, referrer])
    idx.remove(target.uid)
    # target's identity is gone...
    assert idx.resolve_uid("topic:t") is None
    assert target.uid not in idx.by_uid
    # ...but the referrer's inbound ref to topic:t persists (now dangling).
    rows = idx.in_refs.get("topic:t", [])
    assert any(r.source_uid == referrer.uid for r in rows)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.index'`.

- [ ] **Step 3: Implement `src/nodes/kernel/index.py` (core)**

```python
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from nodes.kernel.errors import CollisionError
from nodes.kernel.node import Node
from nodes.kernel.relations import Relation
from nodes.kernel.shapes import MEMBERSHIP

Role = Literal[
    "relation_source",
    "relation_target",
    "membership_member",
    "membership_edge_source",
    "membership_edge_target",
]


@dataclass
class OutRef:
    ref: str
    role: Role
    relation: Relation | None = None  # present iff role startswith "relation_"


@dataclass
class InRef:
    source_uid: str
    out_ref: OutRef


@dataclass
class IndexEntry:
    uid: str
    id: str
    kind: str
    deprecated_ids: frozenset[str]
    out_refs: list[OutRef]


@dataclass
class ResolvedEdge:
    relation: Relation
    source_uid: str | None
    target_uid: str | None


def _extract_out_refs(node: Node) -> list[OutRef]:
    refs: list[OutRef] = []
    for rel in node.relations:
        refs.append(OutRef(ref=rel.source, role="relation_source", relation=rel))
        refs.append(OutRef(ref=rel.target, role="relation_target", relation=rel))
    mem = node.facets.get(MEMBERSHIP)
    if isinstance(mem, dict):
        members = mem.get("members")
        if isinstance(members, list):
            for m in members:
                refs.append(OutRef(ref=m, role="membership_member"))
        elif isinstance(members, dict):
            for v in members.values():
                refs.append(OutRef(ref=v, role="membership_member"))
        for edge in mem.get("edges", []) or []:
            if isinstance(edge, dict):
                if "source" in edge:
                    refs.append(OutRef(ref=edge["source"], role="membership_edge_source"))
                if "target" in edge:
                    refs.append(OutRef(ref=edge["target"], role="membership_edge_target"))
    return refs


class Index:
    """In-memory structural index. Pure data; no file I/O."""

    def __init__(self) -> None:
        self.by_uid: dict[str, IndexEntry] = {}
        self.id_to_uid: dict[str, str] = {}
        self.deprecated_to_uid: dict[str, str] = {}
        self.in_refs: dict[str, list[InRef]] = {}

    @classmethod
    def build(cls, nodes: Iterable[Node]) -> "Index":
        idx = cls()
        for node in nodes:
            idx.assert_addable(node)  # fail-early on a corrupt corpus (collision contract)
            idx.upsert(node)
        return idx

    def resolve_uid(self, ref: str) -> str | None:
        return self.id_to_uid.get(ref) or self.deprecated_to_uid.get(ref)

    def assert_addable(self, node: Node) -> None:
        existing = self.by_uid.get(node.uid)
        if existing is not None and existing.id != node.id:
            raise CollisionError(
                f"uid {node.uid!r} already belongs to live id {existing.id!r}; use rename()"
            )
        for claim in (node.id, *node.deprecated_ids):
            owner = self.resolve_uid(claim)
            if owner is not None and owner != node.uid:
                raise CollisionError(f"identity claim {claim!r} already in use by uid {owner!r}")

    def upsert(self, node: Node) -> None:
        if node.uid in self.by_uid:
            self._drop(node.uid)
        entry = IndexEntry(
            uid=node.uid,
            id=node.id,
            kind=node.kind,
            deprecated_ids=frozenset(node.deprecated_ids),
            out_refs=_extract_out_refs(node),
        )
        self.by_uid[node.uid] = entry
        self.id_to_uid[node.id] = node.uid
        for dep in node.deprecated_ids:
            self.deprecated_to_uid[dep] = node.uid
        for oref in entry.out_refs:
            self.in_refs.setdefault(oref.ref, []).append(InRef(source_uid=node.uid, out_ref=oref))

    def remove(self, uid: str) -> None:
        self._drop(uid)

    def _drop(self, uid: str) -> None:
        entry = self.by_uid.pop(uid, None)
        if entry is None:
            return
        if self.id_to_uid.get(entry.id) == uid:
            del self.id_to_uid[entry.id]
        for dep in entry.deprecated_ids:
            if self.deprecated_to_uid.get(dep) == uid:
                del self.deprecated_to_uid[dep]
        for ref, rows in list(self.in_refs.items()):
            kept = [r for r in rows if r.source_uid != uid]
            if kept:
                self.in_refs[ref] = kept
            else:
                del self.in_refs[ref]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_index.py -v`
Expected: PASS (10 tests).

Run: `uv run ruff check . && uv run pyright src`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/index.py tests/test_index.py
git commit -m "feat(index): structural index core — entries, resolution, collision gate, maintenance"
```

---

## Task 3: `Index` graph queries — outbound, inbound, dangling

**Files:**
- Modify: `src/nodes/kernel/index.py` (add query methods)
- Modify: `tests/test_index.py` (add query tests)

**Interfaces:**
- Consumes: the Task 2 maps and `ResolvedEdge`.
- Produces (used by Task 4):
  - `Index.outbound_edges(uid: str) -> list[ResolvedEdge]` — distinct relations whose `source` resolves to `uid`
  - `Index.inbound_edges(uid: str) -> list[ResolvedEdge]` — distinct relations whose `target` resolves to `uid`, merged across every ref (live + deprecated) resolving to that uid
  - `Index.dangling_edges() -> list[ResolvedEdge]` — relations whose `target` resolves to no uid

**Design notes:**
- Queries are defined over **distinct `Relation` objects** (dedup by object identity), not over `OutRef` rows — `OutRef.role` is just the indexing mechanism. This is why a relation whose `source` is a non-container node still attributes to the correct node.
- The refs resolving to a uid are exactly that node's `[id, *deprecated_ids]`. Look those up in `in_refs` to find the relation rows in O(degree).

- [ ] **Step 1: Add graph-query tests to `tests/test_index.py`**

```python
from nodes.kernel.relations import Relation


def _uid(idx, node):
    return idx.id_to_uid[node.id]


def test_outbound_returns_source_relations_resolved():
    a = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")])
    b = Node(id="topic:b", kind="topic", title="B")
    idx = Index.build([a, b])
    edges = idx.outbound_edges(a.uid)
    assert len(edges) == 1
    assert edges[0].relation.target == "topic:b"
    assert edges[0].source_uid == a.uid and edges[0].target_uid == b.uid


def test_inbound_returns_target_relations_resolved():
    a = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")])
    b = Node(id="topic:b", kind="topic", title="B")
    idx = Index.build([a, b])
    edges = idx.inbound_edges(b.uid)
    assert len(edges) == 1
    assert edges[0].source_uid == a.uid and edges[0].target_uid == b.uid


def test_inbound_merges_across_deprecated_target_ref():
    # B is live as topic:new but still has deprecated topic:old;
    # A points at the stale ref topic:old.
    b = Node(id="topic:new", kind="topic", title="B", deprecated_ids=["topic:old"])
    a = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:old")])
    idx = Index.build([a, b])
    edges = idx.inbound_edges(b.uid)
    assert len(edges) == 1 and edges[0].source_uid == a.uid


def test_outbound_with_noncontainer_source_attributes_to_source_node():
    # The relation lives on B's file but its source is topic:a.
    rel = Relation(source="topic:a", predicate="cites", target="topic:c")
    a = Node(id="topic:a", kind="topic", title="A")
    b = Node(id="topic:b", kind="topic", title="B", relations=[rel])
    c = Node(id="topic:c", kind="topic", title="C")
    idx = Index.build([a, b, c])
    out_a = idx.outbound_edges(a.uid)
    assert len(out_a) == 1 and out_a[0].relation.target == "topic:c"
    assert idx.outbound_edges(b.uid) == []  # B is not the source of any relation


def test_membership_refs_not_in_graph_queries():
    g = Node(id="graph:g", kind="graph", title="G", facets={"membership": {
        "shape": "graph",
        "members": ["topic:x"],
        "edges": [{"source": "topic:x", "predicate": "to", "target": "topic:y"}],
    }})
    x = Node(id="topic:x", kind="topic", title="X")
    y = Node(id="topic:y", kind="topic", title="Y")
    idx = Index.build([g, x, y])
    # membership members/edges are tracked for rename but are not public graph edges
    assert idx.outbound_edges(g.uid) == []
    assert idx.inbound_edges(y.uid) == []


def test_dangling_lists_unresolved_targets():
    a = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:gone")])
    idx = Index.build([a])
    dangling = idx.dangling_edges()
    assert len(dangling) == 1
    assert dangling[0].relation.target == "topic:gone" and dangling[0].target_uid is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_index.py -k "outbound or inbound or dangling or membership_refs_not" -v`
Expected: FAIL — `AttributeError: 'Index' object has no attribute 'outbound_edges'`.

- [ ] **Step 3: Add the query methods to `src/nodes/kernel/index.py`**

Add these methods to the `Index` class (and ensure `ResolvedEdge` is already defined from Task 2):

```python
    def _refs_for_uid(self, uid: str) -> list[str]:
        entry = self.by_uid[uid]
        return [entry.id, *sorted(entry.deprecated_ids)]

    def _resolve_edge(self, rel: Relation) -> ResolvedEdge:
        return ResolvedEdge(
            relation=rel,
            source_uid=self.resolve_uid(rel.source),
            target_uid=self.resolve_uid(rel.target),
        )

    def _relations_by_role(self, uid: str, role: Role) -> list[ResolvedEdge]:
        seen: set[int] = set()
        edges: list[ResolvedEdge] = []
        for ref in self._refs_for_uid(uid):
            for inref in self.in_refs.get(ref, []):
                oref = inref.out_ref
                if oref.role != role or oref.relation is None:
                    continue
                if id(oref.relation) in seen:
                    continue
                seen.add(id(oref.relation))
                edges.append(self._resolve_edge(oref.relation))
        return edges

    def outbound_edges(self, uid: str) -> list[ResolvedEdge]:
        return self._relations_by_role(uid, "relation_source")

    def inbound_edges(self, uid: str) -> list[ResolvedEdge]:
        return self._relations_by_role(uid, "relation_target")

    def dangling_edges(self) -> list[ResolvedEdge]:
        seen: set[int] = set()
        edges: list[ResolvedEdge] = []
        for entry in self.by_uid.values():
            for oref in entry.out_refs:
                if oref.role != "relation_target" or oref.relation is None:
                    continue
                if id(oref.relation) in seen:
                    continue
                if self.resolve_uid(oref.ref) is None:
                    seen.add(id(oref.relation))
                    edges.append(self._resolve_edge(oref.relation))
        return edges
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_index.py -v`
Expected: PASS (all Task 2 + Task 3 tests, 16 total).

Run: `uv run ruff check . && uv run pyright src`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/index.py tests/test_index.py
git commit -m "feat(index): relations-only graph queries — outbound, inbound, dangling"
```

---

## Task 4: `Corpus` coordinator — CRUD, resolution, graph delegation

**Files:**
- Create: `src/nodes/kernel/corpus.py`
- Create: `tests/test_corpus.py`

**Interfaces:**
- Consumes: `Store` (Task 1), `Index`/`ResolvedEdge` (Tasks 2–3), `Node`, `RefError`.
- Produces (rename added in Task 5):
  - `Corpus(root: Path)` — builds `Store`, scans corpus, builds `Index`
  - `Corpus.add(node) -> Node`
  - `Corpus.get(ref) -> Node` / `Corpus.resolve(ref) -> Node` (alias)
  - `Corpus.delete(node_id) -> None` — live-id-only
  - `Corpus.all() -> list[Node]`
  - `Corpus.outbound(ref)`, `Corpus.inbound(ref)`, `Corpus.dangling()`, `Corpus.neighbors(ref)`
  - module-level `_rewrite_refs(node, old, new)` helper (also used by Task 5)

**Design notes:**
- `add` collision-checks via `index.assert_addable` **before** `store.write_file`, so the index never gets ahead of disk.
- Graph queries resolve the input `ref` to a uid first; an unresolvable input raises `RefError` (distinct from a resolvable node with no edges). Dangling *targets* never raise.
- `_rewrite_refs` is the relocated kernel rewrite logic (relations source+target, membership members list/dict, edge source+target). Define it here; Task 5's `rename` reuses it. Membership edges are raw dicts (see Task 2's facet note) — the rewrite reads `edge["source"]`/`edge["target"]`, matching `_extract_out_refs`.

- [ ] **Step 1: Write `tests/test_corpus.py` (CRUD + queries; rename is Task 5)**

```python
from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import CollisionError, RefError
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to


def test_add_get_roundtrip(tmp_path):
    c = Corpus(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A", body="hi")
    c.add(n)
    got = c.get("topic:a")
    assert got.title == "A" and got.body == "hi" and got.uid == n.uid


def test_corpus_rebuilds_index_from_existing_files(tmp_path):
    Corpus(tmp_path).add(Node(id="topic:a", kind="topic", title="A"))
    fresh = Corpus(tmp_path)  # second corpus scans the same dir
    assert fresh.get("topic:a").title == "A"


def test_add_collision_same_id_different_uid(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A"))
    with pytest.raises(CollisionError):
        c.add(Node(id="topic:a", kind="topic", title="Other"))


def test_add_collision_duplicate_uid_at_different_id(tmp_path):
    c = Corpus(tmp_path)
    original = Node(id="topic:a", kind="topic", title="A")
    c.add(original)
    with pytest.raises(CollisionError):
        c.add(Node(id="topic:b", kind="topic", title="B", uid=original.uid))


def test_add_collision_deprecated_id_claim(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A"))
    with pytest.raises(CollisionError):
        c.add(Node(id="topic:b", kind="topic", title="B", deprecated_ids=["topic:a"]))


def test_add_overwrite_same_uid_same_id_ok(tmp_path):
    c = Corpus(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A")
    c.add(n)
    n.title = "A2"
    c.add(n)
    assert c.get("topic:a").title == "A2"


def test_get_unresolved_raises(tmp_path):
    with pytest.raises(RefError):
        Corpus(tmp_path).get("topic:ghost")


def test_delete_removes_and_is_live_id_only(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", deprecated_ids=["topic:old"]))
    with pytest.raises(RefError):
        c.delete("topic:old")  # deprecated id is not a live id
    c.delete("topic:a")
    with pytest.raises(RefError):
        c.get("topic:a")


def test_delete_leaves_dangling_inbound(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:t", kind="topic", title="T"))
    c.add(Node(id="topic:r", kind="topic", title="R", relations=[relates_to("topic:r", "topic:t")]))
    c.delete("topic:t")
    out = c.outbound("topic:r")
    assert len(out) == 1 and out[0].target_uid is None
    assert len(c.dangling()) == 1
    with pytest.raises(RefError):
        c.inbound("topic:t")  # target no longer resolves → input ref error


def test_neighbors_distinct_resolved(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")]))
    c.add(Node(id="topic:b", kind="topic", title="B"))
    c.add(Node(id="topic:c", kind="topic", title="C", relations=[relates_to("topic:c", "topic:a")]))
    names = sorted(n.id for n in c.neighbors("topic:a"))
    assert names == ["topic:b", "topic:c"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.corpus'`.

- [ ] **Step 3: Implement `src/nodes/kernel/corpus.py`**

```python
from __future__ import annotations

from pathlib import Path

from nodes.kernel.errors import RefError
from nodes.kernel.index import Index, ResolvedEdge
from nodes.kernel.node import Node
from nodes.kernel.shapes import MEMBERSHIP
from nodes.kernel.store import Store


def _rewrite_refs(node: Node, old: str, new: str) -> None:
    """Rewrite every position in `node` that holds `old` to `new` (in place)."""
    for rel in node.relations:
        if rel.source == old:
            rel.source = new
        if rel.target == old:
            rel.target = new
    mem = node.facets.get(MEMBERSHIP)
    if isinstance(mem, dict):
        members = mem.get("members")
        if isinstance(members, list):
            mem["members"] = [new if m == old else m for m in members]
        elif isinstance(members, dict):
            for key, val in list(members.items()):
                if val == old:
                    members[key] = new
        for edge in mem.get("edges", []) or []:
            if isinstance(edge, dict):
                if edge.get("source") == old:
                    edge["source"] = new
                if edge.get("target") == old:
                    edge["target"] = new


class Corpus:
    """Coordinator over a `Store` + an in-memory `Index`. The primary kernel API."""

    def __init__(self, root: Path) -> None:
        self.store = Store(root)
        self.index = Index.build(self.store.all_nodes())

    def add(self, node: Node) -> Node:
        self.index.assert_addable(node)
        self.store.write_file(node)
        self.index.upsert(node)
        return node

    def get(self, ref: str) -> Node:
        uid = self.index.resolve_uid(ref)
        if uid is None:
            raise RefError(f"no node resolves ref {ref!r}")
        return self.store.read_file(self.index.by_uid[uid].id)

    def resolve(self, ref: str) -> Node:
        return self.get(ref)

    def delete(self, node_id: str) -> None:
        uid = self.index.id_to_uid.get(node_id)
        if uid is None:
            raise RefError(f"no live node at {node_id!r}")
        self.store.delete_file(node_id)
        self.index.remove(uid)

    def all(self) -> list[Node]:
        return self.store.all_nodes()

    def _require_uid(self, ref: str) -> str:
        uid = self.index.resolve_uid(ref)
        if uid is None:
            raise RefError(f"no node resolves ref {ref!r}")
        return uid

    def outbound(self, ref: str) -> list[ResolvedEdge]:
        return self.index.outbound_edges(self._require_uid(ref))

    def inbound(self, ref: str) -> list[ResolvedEdge]:
        return self.index.inbound_edges(self._require_uid(ref))

    def dangling(self) -> list[ResolvedEdge]:
        return self.index.dangling_edges()

    def neighbors(self, ref: str) -> list[Node]:
        uid = self._require_uid(ref)
        neighbor_uids: set[str] = set()
        for edge in self.index.outbound_edges(uid):
            if edge.target_uid is not None:
                neighbor_uids.add(edge.target_uid)
        for edge in self.index.inbound_edges(uid):
            if edge.source_uid is not None:
                neighbor_uids.add(edge.source_uid)
        neighbor_uids.discard(uid)
        return [self.store.read_file(self.index.by_uid[u].id) for u in sorted(neighbor_uids)]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_corpus.py -v`
Expected: PASS (10 tests).

Run: `uv run ruff check . && uv run pyright src`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/corpus.py tests/test_corpus.py
git commit -m "feat(corpus): coordinator — CRUD, uid-based resolution, relations graph delegation"
```

---

## Task 5: `Corpus.rename` — O(degree) targeted rewrite

**Files:**
- Modify: `src/nodes/kernel/corpus.py` (add `rename`)
- Modify: `tests/test_corpus.py` (add rename tests)

**Interfaces:**
- Consumes: Task 4 `Corpus`, `_rewrite_refs`, `Store`, `Index`, plus `NodeId` (`nodes.kernel.ids`) and `CollisionError`.
- Produces: `Corpus.rename(old_id: str, new_id: str) -> Node`.

**Rename flow (implement exactly):**
1. If `old_id` not in `index.id_to_uid` → `RefError` (live-id-only). Then if `index.resolve_uid(new_id)` is not None → `CollisionError`.
2. Snapshot `referrer_uids = {ir.source_uid for ir in index.in_refs.get(old_id, [])}` **before** any mutation.
3. Read the node; set `id = new_id`, `kind = NodeId.parse(new_id).kind`, append `old_id` to `deprecated_ids`; `_rewrite_refs(node, old_id, new_id)` (its own relations/membership).
4. `store.write_file(node)` first; then `store.delete_file(old_id)` if `old_path != new_path`.
5. `index.upsert(node)`.
6. For each **other** `referrer_uid` in the snapshot (skip the renamed node's own uid): read it by `index.by_uid[uid].id`, `_rewrite_refs`, `store.write_file`, `index.upsert`.

Both the renamed node and every referrer are written exactly once.

- [ ] **Step 1: Add rename tests to `tests/test_corpus.py`**

```python
def test_rename_rewrites_inbound_relations(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:b", kind="topic", title="B", relations=[relates_to("topic:b", "topic:old")]))
    renamed = c.rename("topic:old", "topic:new")
    assert renamed.id == "topic:new" and "topic:old" in renamed.deprecated_ids
    b = c.get("topic:b")
    assert any(r.target == "topic:new" for r in b.relations)
    assert all(r.target != "topic:old" for r in b.relations)


def test_rename_resolves_old_id_after(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.rename("topic:old", "topic:new")
    assert c.get("topic:old").id == "topic:new"  # stale ref still resolves


def test_rename_rewrites_membership_members_and_edges(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:x", kind="topic", title="X"))
    c.add(Node(id="graph:g", kind="graph", title="G", facets={"membership": {
        "shape": "graph",
        "members": ["topic:old", "topic:x"],
        "edges": [{"source": "topic:old", "predicate": "to", "target": "topic:x"}],
    }}))
    c.rename("topic:old", "topic:new")
    mem = c.get("graph:g").facets["membership"]
    assert "topic:new" in mem["members"] and "topic:old" not in mem["members"]
    assert mem["edges"][0]["source"] == "topic:new"  # edge SOURCE rewritten


def test_rename_rewrites_dict_membership(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:x", kind="topic", title="X"))
    c.add(Node(id="dict:d", kind="dict", title="D", facets={"membership": {
        "shape": "dict",
        "members": {"a": "topic:old", "b": "topic:x"},
    }}))
    c.rename("topic:old", "topic:new")
    mem = c.get("dict:d").facets["membership"]
    assert mem["members"]["a"] == "topic:new" and mem["members"]["b"] == "topic:x"


def test_rename_rewrites_own_relation_source(tmp_path):
    # A node whose outgoing relation had explicit source == old_id must, after rename,
    # serialize that relation with the container source (no stale source: old_id).
    from nodes.kernel.relations import Relation
    c = Corpus(tmp_path)
    c.add(Node(id="topic:t", kind="topic", title="T"))
    c.add(Node(id="topic:old", kind="topic", title="Old",
               relations=[Relation(source="topic:old", predicate="cites", target="topic:t")]))
    c.rename("topic:old", "topic:new")
    new = c.get("topic:new")
    rel = next(r for r in new.relations if r.predicate == "cites")
    assert rel.source == "topic:new"
    # round-trips clean: re-reading from disk shows the container source, not a stale one
    assert all(r.source != "topic:old" for r in new.relations)


def test_rename_multi_ref_referrer_written_once(tmp_path):
    # A referrer that points at old_id from several positions is rewritten correctly.
    from nodes.kernel.relations import Relation
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:r", kind="topic", title="R", relations=[
        relates_to("topic:r", "topic:old"),
        Relation(source="topic:r", predicate="cites", target="topic:old"),
    ]))
    c.rename("topic:old", "topic:new")
    r = c.get("topic:r")
    assert all(rel.target != "topic:old" for rel in r.relations)
    assert sum(1 for rel in r.relations if rel.target == "topic:new") == 2


def test_rename_inbound_across_deprecated_id(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:b", kind="topic", title="B", relations=[relates_to("topic:b", "topic:old")]))
    c.rename("topic:old", "topic:new")
    # the referrer was rewritten to topic:new, so inbound finds it under the new id
    inbound = c.inbound("topic:new")
    assert len(inbound) == 1 and inbound[0].source_uid == c.index.id_to_uid["topic:b"]


def test_rename_rejects_deprecated_or_unknown_old_id(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", deprecated_ids=["topic:stale"]))
    with pytest.raises(RefError):
        c.rename("topic:stale", "topic:z")  # deprecated, not live
    with pytest.raises(RefError):
        c.rename("topic:ghost", "topic:z")  # unknown


def test_rename_rejects_taken_target(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A"))
    c.add(Node(id="topic:b", kind="topic", title="B"))
    with pytest.raises(CollisionError):
        c.rename("topic:a", "topic:b")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_corpus.py -k rename -v`
Expected: FAIL — `AttributeError: 'Corpus' object has no attribute 'rename'`.

- [ ] **Step 3: Add `rename` to `src/nodes/kernel/corpus.py`**

Add the import at the top (with the other kernel imports):

```python
from nodes.kernel.errors import CollisionError, RefError
from nodes.kernel.ids import NodeId
```

Add the method to `Corpus`:

```python
    def rename(self, old_id: str, new_id: str) -> Node:
        if old_id not in self.index.id_to_uid:
            raise RefError(f"rename source {old_id!r} is not a live id")
        if self.index.resolve_uid(new_id) is not None:
            raise CollisionError(f"target id {new_id!r} already in use")

        uid = self.index.id_to_uid[old_id]
        referrer_uids = {ir.source_uid for ir in self.index.in_refs.get(old_id, [])}

        node = self.store.read_file(old_id)
        old_path = self.store.path_for(old_id)
        node.id = new_id
        node.kind = NodeId.parse(new_id).kind
        if old_id not in node.deprecated_ids:
            node.deprecated_ids.append(old_id)
        _rewrite_refs(node, old_id, new_id)
        new_path = self.store.write_file(node)
        if old_path != new_path:
            self.store.delete_file(old_id)
        self.index.upsert(node)

        for referrer_uid in referrer_uids:
            if referrer_uid == uid:
                continue
            referrer = self.store.read_file(self.index.by_uid[referrer_uid].id)
            _rewrite_refs(referrer, old_id, new_id)
            self.store.write_file(referrer)
            self.index.upsert(referrer)

        return node
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_corpus.py -v`
Expected: PASS (all CRUD + 9 rename tests).

Run: `uv run ruff check . && uv run pyright src`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/corpus.py tests/test_corpus.py
git commit -m "feat(corpus): O(degree) rename — targeted referrer rewrite via reverse index"
```

---

## Task 6: Rebuild-equivalence property test + docs update

**Files:**
- Create: `tests/test_index_rebuild_equivalence.py`
- Modify: `docs/format.md`

**Interfaces:**
- Consumes: `Corpus` (Tasks 4–5), `Index` (Task 2).

**Design notes:**
- The invariant: after any sequence of `Corpus` mutations, the live index must equal a fresh `Index.build(store.all_nodes())`. Compare via a normalized form — scalar maps directly; list-valued `in_refs` as sorted multisets keyed by `(source_uid, ref, role)` — so insertion-order differences don't cause false failures.
- Drive a sequence that includes adds, a rename (creating deprecated ids and rewriting referrers), and a delete that strands an inbound ref (exercising the `remove`-keeps-dangling path).

- [ ] **Step 1: Write `tests/test_index_rebuild_equivalence.py`**

```python
from __future__ import annotations

from nodes.kernel.corpus import Corpus
from nodes.kernel.index import Index
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to


def _normalize(index: Index) -> dict:
    return {
        "by_uid": {
            uid: (
                e.id,
                e.kind,
                tuple(sorted(e.deprecated_ids)),
                tuple(sorted((o.ref, o.role) for o in e.out_refs)),  # dangling() depends on these
            )
            for uid, e in index.by_uid.items()
        },
        "id_to_uid": dict(index.id_to_uid),
        "deprecated_to_uid": dict(index.deprecated_to_uid),
        "in_refs": {
            ref: sorted((r.source_uid, r.out_ref.ref, r.out_ref.role) for r in rows)
            for ref, rows in index.in_refs.items()
        },
    }


def _assert_equivalent(corpus: Corpus) -> None:
    fresh = Index.build(corpus.store.all_nodes())
    assert _normalize(corpus.index) == _normalize(fresh)


def test_rebuild_equivalence_through_mutation_sequence(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")]))
    c.add(Node(id="topic:b", kind="topic", title="B"))
    c.add(Node(id="graph:g", kind="graph", title="G", facets={"membership": {
        "shape": "graph",
        "members": ["topic:a", "topic:b"],
        "edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}],
    }}))
    _assert_equivalent(c)

    c.rename("topic:b", "topic:b2")  # creates deprecated id, rewrites referrers (A's relation, graph members/edges)
    _assert_equivalent(c)

    c.add(Node(id="topic:c", kind="topic", title="C", relations=[relates_to("topic:c", "topic:a")]))
    _assert_equivalent(c)

    c.delete("topic:a")  # strands inbound refs from topic:c and graph:g → must stay as dangling
    _assert_equivalent(c)
    assert len(c.dangling()) >= 1  # topic:c still points at the deleted topic:a


def test_rebuild_equivalence_after_overwrite(tmp_path):
    c = Corpus(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:x")])
    c.add(n)
    n.relations = [relates_to("topic:a", "topic:y")]  # change outbound refs
    c.add(n)  # same uid+id overwrite
    _assert_equivalent(c)
```

- [ ] **Step 2: Run to verify it passes (this is a behavior assertion on finished code, not a red-first feature)**

Run: `uv run pytest tests/test_index_rebuild_equivalence.py -v`
Expected: PASS (2 tests). If either fails, an incremental-maintenance path diverges from a clean rebuild — fix the `upsert`/`remove`/`rename` path it points at before proceeding; do not weaken the normalization to make it pass.

- [ ] **Step 3: Update `docs/format.md` known-limitations section**

Replace the "Known kernel limitations" block (the derived-index bullet and the `delete()` note) with text reflecting Plan 2. Open `docs/format.md`, find:

```markdown
## Known kernel limitations (resolved in later plans)
- No derived search/graph index yet (Plan 2): full-text, resolved relation graph, embeddings.
  Kernel `resolve()` / collision checks do linear scans; the index makes lookups O(1).
- `delete()` operates on a node's current (live) id only; passing a stale/deprecated id raises
  `RefError`. This is intentional: a stale alias must not silently remove the renamed live node.
  Use `read()` / `resolve()` first if you need to look up the live id from a deprecated one.
```

Replace it with:

```markdown
## Index & API (Plan 2)
The kernel ships an in-memory **structural index** (`nodes.kernel.index.Index`) and a
**`Corpus`** coordinator (`nodes.kernel.corpus.Corpus`) that owns a `Store` + an `Index`.
`Corpus` is the primary API: `add`, `get`/`resolve`, `rename`, `delete`, `all`, and the
relations-graph queries `outbound`, `inbound`, `neighbors`, `dangling`.

- Resolution (`id` / deprecated `id` → `uid`) and collision checks are **O(1)** via the index;
  a live id always wins over a deprecated id.
- `rename` is **O(degree)**: it rewrites only the referrers the reverse index names (relations
  `source`/`target`, membership members, and edge `source`/`target`), plus the renamed node's
  own references.
- Graph queries are **relations-only** and uid-based. Dangling targets (a relation whose target
  no longer resolves) are a normal state — surfaced by `outbound(source)` and `dangling()`, never
  raised. `inbound`/`outbound` raise `RefError` only when the *input* ref does not resolve.
- `delete()` is **live-id-only**: passing a stale/deprecated id raises `RefError`, so a stale
  alias never silently removes the renamed live node. Inbound references to a deleted node remain
  on disk as dangling.

### Known kernel limitations (resolved in later plans)
- The index is in-memory and rebuilt on `Corpus(root)` construction; no on-disk persistence yet.
- No full-text search or embeddings/similarity index yet.
- No public membership-graph traversal (tree descendants, DAG reachability) yet — membership refs
  are tracked internally for rename but are not exposed as graph edges.
```

- [ ] **Step 4: Full gate — run the entire suite, lint, and type-check**

Run: `uv run pytest -q`
Expected: PASS. Whole suite green (the original kernel tests + the new `test_index.py`, `test_corpus.py`, `test_index_rebuild_equivalence.py`, and the slimmed `test_store.py`).

Run: `uv run ruff check . && uv run pyright src`
Expected: clean (0 errors).

- [ ] **Step 5: Commit**

```bash
git add tests/test_index_rebuild_equivalence.py docs/format.md
git commit -m "test(index): rebuild-equivalence property test; docs(format): Plan 2 index & API"
```

---

## Notes for the executor

- **Migration completeness:** Task 1 deletes `Store.write/resolve/read/rename` and helpers. Only `tests/test_store.py` referenced them; their behavior is re-tested at the `Corpus` level in Tasks 4–5. If you find any other importer, that is a real break — fix it, don't re-add the method.
- **No new dependencies.** Everything is stdlib + the existing Pydantic/PyYAML.
- **Collision gate vs. mechanical upsert** is intentional (Task 2 notes): `assert_addable` raises; `upsert` does not. `rename` relies on `upsert` not raising when a node's live id legitimately changes.
- **Dedup by object identity** (`id(relation)`) in the graph queries is correct because the index holds the same `Relation` objects parsed once per node; a fresh rebuild re-parses, but equivalence is asserted over the normalized `(source_uid, ref, role)` projection, not object identity.
```
