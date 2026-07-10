# Structural-Shape Redesign (Python) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Python kernel's structural shapes so a structure's *membership* (scope) is cleanly separated from its shape-owned *form* (`edges`/`order`/`keys`), with shapes registered as a composable trait that kinds adopt.

**Architecture:** A `Structure` is a `Node` of a registered shape, carrying a scope-only `membership` facet plus the form facet(s) its shape requires. Shapes are registered via `ShapeSpec`; a `KindSpec` adopts ≤1 shape via `KindSpec.shape`; the `Registry` composes the shape's required/optional facets and invariants into the kind's validation. The structural index and rename rewrite refs from `membership.members` plus the built-in form facets, independent of any registry. This is a clean breaking change — no compatibility layer, no corpus migration.

**Tech Stack:** Python 3.11+, pydantic v2, pytest. Source under `~/d/nodes/python/src/nodes/`, tests under `~/d/nodes/python/tests/`. All commands run from `~/d/nodes/python` via the `rtk` wrapper.

This is **Plan A-py**, the first of three plans for mindful v6 SP1 (spec: `~/d/nodes/docs/designs/2026-06-23-mindful-v6-sp1-abstraction-design.md`). It is followed by **Plan A-ts** (the TypeScript port, using this finished Python as its oracle) and then **Plan B** (the mindful package). Both kernels land before mindful is scaffolded.

## Current State Note

This plan has since been implemented and remains useful as the historical Plan A-py rollout for the structural-shape redesign. Current Python and TypeScript kernels both use the split model described here: scope-only `membership.members`, shape-owned form facets (`edges`, `order`, `keys`), shape registration through `ShapeSpec`, and registry-independent structural-ref extraction for rename and snapshot integrity.

There are three current-code details to keep in mind when reading the task snippets below:

- Later plans added full-text search, similarity, and snapshot persistence. Current `Corpus(root, registry=None, embedder=None)` therefore does more during construction and mutation than the snippets in this plan show.
- Current structural `Index.to_dict()` / `from_dict()` serializes generic `structural_refs` rather than the old bundled membership snapshot shape, and `from_dict()` is a validating deserializer used by snapshot persistence.
- The `docs/STANDARD.md` update in Task 5 has already been applied and later extended with TypeScript parity, full-text search, similarity, and snapshot persistence sections.

## Global Constraints

- **Structure contract:** `Structure = shape/kind + membership facet + shape-specific form facet(s)`. `Relation` is the universal **binary** primitive, but `Structure` is NOT defined in terms of it.
- **Membership = scope only:** `{ members: list[str] }`, a unique unordered set. Order/edges/keys live in form facets — never leak through `membership.members` position.
- **Form is shape-owned:** each registered shape declares the form facet(s) it requires, its invariants, and any predicates it uses. Unknown shape or malformed form **fails early**.
- **Built-in shapes:** `set, list, dict, graph, dag, tree` — all six stay in scope (this is a built-in shape redesign, not the minimum mindful subset).
- **Duplicate names fail early:** `register_shape` rejects a duplicate shape name; `register` rejects a duplicate kind name. Shape and kind namespaces are **separate** (a `graph` shape and a `graph` kind coexist).
- **Structure refs vs global graph:** structure refs (`members`/edges/`order`/`keys` values) are tracked for **rename + snapshot integrity** but are **never** exposed through `Corpus.outbound`/`inbound`/`neighbors`/`dangling`. Only top-level `relations:` feed the global relation graph.
- **No-registry recognition:** the built-in structural facets (`membership`/`edges`/`order`/`keys`) are recognized for ref rewriting + index extraction **with or without** a registry. Rename never skips known structural refs for lack of a registry.
- **Clean breaking change:** no compat layer, no migration. `~/d/mindful/v6` is empty and `science` does not use shapes yet.
- **Singular shape:** a kind adopts zero or one shape.
- **Gate (run from `~/d/nodes/python`):** `rtk uv run pytest tests -q`, `rtk uv run ruff check src tests`, `rtk uv run pyright src` must all pass before a task is complete.

---

### Task 1: Registry — `ShapeSpec`, `KindSpec.shape`, composition, duplicate rejection

**Files:**
- Modify: `python/src/nodes/kernel/registry.py`
- Test: `python/tests/test_registry.py`

**Interfaces:**
- Consumes: `Node` (`nodes.kernel.node`), errors `FacetError`/`UnknownKindError`/`ValidationError` (`nodes.kernel.errors`).
- Produces:
  - `ShapeSpec(BaseModel)` with fields `name: str`, `required_facets: set[str]`, `optional_facets: set[str]`, `invariants: list[Invariant]`.
  - `KindSpec(BaseModel)` gains `shape: str | None = None` (other fields unchanged).
  - `Registry.register_shape(spec: ShapeSpec) -> None` — rejects duplicate shape name (`ValidationError`).
  - `Registry.is_shape(name: str) -> bool`.
  - `Registry.register(spec: KindSpec) -> None` — rejects duplicate kind name (`ValidationError`) and an unknown adopted shape (`UnknownKindError`).
  - `Registry.validate(node)` composes shape + kind required/optional facets and runs shape invariants then kind invariants.

- [ ] **Step 1: Write the failing tests**

Append to `python/tests/test_registry.py`:

```python
from nodes.kernel.errors import ValidationError
from nodes.kernel.registry import ShapeSpec


def _flag(box: list[str], tag: str):
    def inv(node: Node) -> None:
        box.append(tag)
    return inv


def test_register_shape_rejects_duplicate():
    reg = Registry()
    reg.register_shape(ShapeSpec(name="graph", required_facets={"membership"}))
    with pytest.raises(ValidationError):
        reg.register_shape(ShapeSpec(name="graph"))


def test_register_rejects_duplicate_kind():
    reg = Registry()
    reg.register(KindSpec(name="topic"))
    with pytest.raises(ValidationError):
        reg.register(KindSpec(name="topic"))


def test_register_rejects_unknown_shape():
    reg = Registry()
    with pytest.raises(UnknownKindError):
        reg.register(KindSpec(name="mindmap", shape="graph"))


def test_shape_and_kind_may_share_a_name():
    reg = Registry()
    reg.register_shape(ShapeSpec(name="graph", required_facets={"membership"}))
    reg.register(KindSpec(name="graph", shape="graph"))  # separate namespaces: no raise
    assert reg.is_shape("graph") and reg.is_registered("graph")


def test_validate_composes_shape_and_kind_facets():
    reg = Registry()
    reg.register_shape(ShapeSpec(name="graph", required_facets={"membership"}))
    reg.register(KindSpec(name="mindmap", shape="graph", required_facets={"scene"}))
    node = Node(id="mindmap:m", kind="mindmap", title="M",
                facets={"membership": {"members": []}, "scene": {"x": 1}})
    reg.validate(node)  # both shape + kind required facets present: no raise
    missing_scene = Node(id="mindmap:n", kind="mindmap", title="N",
                         facets={"membership": {"members": []}})
    with pytest.raises(FacetError):
        reg.validate(missing_scene)


def test_validate_runs_shape_invariants_before_kind_invariants():
    order: list[str] = []
    reg = Registry()
    reg.register_shape(ShapeSpec(name="graph", required_facets={"membership"},
                                 invariants=[_flag(order, "shape")]))
    reg.register(KindSpec(name="mindmap", shape="graph", invariants=[_flag(order, "kind")]))
    reg.validate(Node(id="mindmap:m", kind="mindmap", title="M",
                      facets={"membership": {"members": []}}))
    assert order == ["shape", "kind"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk uv run pytest tests/test_registry.py -q`
Expected: FAIL — `ImportError: cannot import name 'ShapeSpec'` (and `register_shape`/`shape` missing).

- [ ] **Step 3: Implement the registry changes**

Replace the body of `python/src/nodes/kernel/registry.py` with:

```python
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from nodes.kernel.errors import FacetError, UnknownKindError, ValidationError
from nodes.kernel.node import Node

Invariant = Callable[[Node], None]


class ShapeSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    required_facets: set[str] = Field(default_factory=set)
    optional_facets: set[str] = Field(default_factory=set)
    invariants: list[Invariant] = Field(default_factory=list)


class KindSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    shape: str | None = None
    required_facets: set[str] = Field(default_factory=set)
    optional_facets: set[str] = Field(default_factory=set)
    invariants: list[Invariant] = Field(default_factory=list)


class Registry:
    def __init__(self) -> None:
        self._specs: dict[str, KindSpec] = {}
        self._shapes: dict[str, ShapeSpec] = {}

    def register_shape(self, spec: ShapeSpec) -> None:
        if spec.name in self._shapes:
            raise ValidationError(f"shape {spec.name!r} is already registered")
        self._shapes[spec.name] = spec

    def is_shape(self, name: str) -> bool:
        return name in self._shapes

    def register(self, spec: KindSpec) -> None:
        if spec.name in self._specs:
            raise ValidationError(f"kind {spec.name!r} is already registered")
        if spec.shape is not None and spec.shape not in self._shapes:
            raise UnknownKindError(f"kind {spec.name!r} adopts unknown shape {spec.shape!r}")
        self._specs[spec.name] = spec

    def is_registered(self, kind: str) -> bool:
        return kind in self._specs

    def get(self, kind: str) -> KindSpec:
        try:
            return self._specs[kind]
        except KeyError as exc:
            raise UnknownKindError(f"kind {kind!r} is not registered") from exc

    def validate(self, node: Node) -> None:
        spec = self.get(node.kind)
        required = set(spec.required_facets)
        optional = set(spec.optional_facets)
        invariants: list[Invariant] = []
        if spec.shape is not None:
            shape = self._shapes[spec.shape]
            required |= shape.required_facets
            optional |= shape.optional_facets
            invariants.extend(shape.invariants)
        invariants.extend(spec.invariants)

        present = set(node.facets)
        missing = required - present
        if missing:
            raise FacetError(f"{node.id}: missing required facets {sorted(missing)}")
        allowed = required | optional
        unexpected = present - allowed
        if unexpected:
            raise FacetError(f"{node.id}: unexpected facets {sorted(unexpected)}")
        for invariant in invariants:
            invariant(node)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_registry.py -q`
Expected: PASS (all registry tests, old and new).

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes && rtk git add python/src/nodes/kernel/registry.py python/tests/test_registry.py
rtk git commit -m "feat(shapes-py): ShapeSpec + KindSpec.shape composition with dup-name rejection"
```

---

### Task 2: Shapes — scope-only membership, form facets, invariants, built-ins

**Files:**
- Modify (full rewrite): `python/src/nodes/kernel/shapes.py`
- Test (full rewrite): `python/tests/test_shapes.py`

**Interfaces:**
- Consumes: `ShapeSpec`, `KindSpec`, `Registry` (Task 1); `Node`, `Relation`, `FacetError`, `InvariantError`.
- Produces:
  - Facet-name constants: `MEMBERSHIP = "membership"`, `EDGES = "edges"`, `ORDER = "order"`, `KEYS = "keys"`.
  - Facet models: `Membership(members: list[str])`, `Edges(edges: list[Relation])`, `Order(order: list[str])`, `Keys(keys: dict[str, str])`.
  - Accessors `membership_of/edges_of/order_of/keys_of(node) -> <Model>` (raise `FacetError` on missing/malformed facet).
  - Invariants: `require_unique_members`, `require_edge_endpoints_are_members`, `require_order_is_permutation`, `require_key_values_are_members`, `require_acyclic`, `require_single_parent`.
  - `register_builtin_shapes(reg: Registry) -> None` — registers six shape-specs and six convenience shape-kinds.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `python/tests/test_shapes.py` with:

```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import FacetError, InvariantError
from nodes.kernel.node import Node
from nodes.kernel.registry import Registry
from nodes.kernel.shapes import EDGES, KEYS, MEMBERSHIP, ORDER, register_builtin_shapes


def _struct(kind: str, **facets) -> Node:
    return Node(id=f"{kind}:s", kind=kind, title="S", facets=facets)


def _edge(source: str, target: str) -> dict:
    return {"source": source, "predicate": "to", "target": target}


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    register_builtin_shapes(r)
    return r


def test_set_requires_membership_only_and_rejects_duplicates(reg):
    reg.validate(_struct("set", **{MEMBERSHIP: {"members": ["a:1", "a:2"]}}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("set", **{MEMBERSHIP: {"members": ["a:1", "a:1"]}}))


def test_set_rejects_form_facets(reg):
    # edges is not allowed on a set (form bundling is gone)
    with pytest.raises(FacetError):
        reg.validate(_struct("set", **{MEMBERSHIP: {"members": ["a:1"]}, EDGES: {"edges": []}}))


def test_list_requires_order_permutation(reg):
    reg.validate(_struct("list", **{MEMBERSHIP: {"members": ["a:1", "a:2"]},
                                    ORDER: {"order": ["a:2", "a:1"]}}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("list", **{MEMBERSHIP: {"members": ["a:1", "a:2"]},
                                        ORDER: {"order": ["a:1"]}}))  # not a permutation


def test_list_rejects_duplicate_members(reg):
    with pytest.raises(InvariantError):
        reg.validate(_struct("list", **{MEMBERSHIP: {"members": ["a:1", "a:1"]},
                                        ORDER: {"order": ["a:1", "a:1"]}}))


def test_list_missing_order_facet_raises(reg):
    with pytest.raises(FacetError):
        reg.validate(_struct("list", **{MEMBERSHIP: {"members": ["a:1"]}}))


def test_dict_requires_key_values_are_members(reg):
    reg.validate(_struct("dict", **{MEMBERSHIP: {"members": ["a:1"]},
                                    KEYS: {"keys": {"k": "a:1"}}}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("dict", **{MEMBERSHIP: {"members": ["a:1"]},
                                        KEYS: {"keys": {"k": "a:2"}}}))  # value not a member


def test_graph_requires_edge_endpoints_are_members(reg):
    reg.validate(_struct("graph", **{MEMBERSHIP: {"members": ["a:1", "a:2"]},
                                     EDGES: {"edges": [_edge("a:1", "a:2")]}}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("graph", **{MEMBERSHIP: {"members": ["a:1"]},
                                         EDGES: {"edges": [_edge("a:1", "a:2")]}}))


def test_dag_rejects_cycle_allows_diamond(reg):
    diamond = {MEMBERSHIP: {"members": ["a:1", "a:2", "a:3", "a:4"]},
               EDGES: {"edges": [_edge("a:1", "a:2"), _edge("a:1", "a:3"),
                                 _edge("a:2", "a:4"), _edge("a:3", "a:4")]}}
    reg.validate(_struct("dag", **diamond))  # no raise
    cyclic = {MEMBERSHIP: {"members": ["a:1", "a:2"]},
              EDGES: {"edges": [_edge("a:1", "a:2"), _edge("a:2", "a:1")]}}
    with pytest.raises(InvariantError):
        reg.validate(_struct("dag", **cyclic))


def test_tree_rejects_multiple_parents(reg):
    multi = {MEMBERSHIP: {"members": ["a:1", "a:2", "a:3"]},
             EDGES: {"edges": [_edge("a:1", "a:3"), _edge("a:2", "a:3")]}}
    with pytest.raises(InvariantError):
        reg.validate(_struct("tree", **multi))


def test_missing_membership_facet_raises(reg):
    with pytest.raises(FacetError):
        reg.validate(_struct("graph", **{EDGES: {"edges": []}}))


def test_malformed_membership_raises_facet_error(reg):
    with pytest.raises(FacetError):
        reg.validate(_struct("set", **{MEMBERSHIP: {"members": "not-a-list"}}))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk uv run pytest tests/test_shapes.py -q`
Expected: FAIL — `ImportError: cannot import name 'EDGES'` (the new facet constants/model do not exist yet).

- [ ] **Step 3: Implement the shapes redesign**

Replace the entire contents of `python/src/nodes/kernel/shapes.py` with:

```python
from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from nodes.kernel.errors import FacetError, InvariantError
from nodes.kernel.node import Node
from nodes.kernel.registry import KindSpec, Registry, ShapeSpec
from nodes.kernel.relations import Relation

MEMBERSHIP = "membership"
EDGES = "edges"
ORDER = "order"
KEYS = "keys"


class Membership(BaseModel):
    members: list[str] = Field(default_factory=list)


class Edges(BaseModel):
    edges: list[Relation] = Field(default_factory=list)


class Order(BaseModel):
    order: list[str] = Field(default_factory=list)


class Keys(BaseModel):
    keys: dict[str, str] = Field(default_factory=dict)


def _load(node: Node, name: str, model: type[BaseModel]):
    raw = node.facets.get(name)
    if raw is None:
        raise FacetError(f"{node.id}: missing {name!r} facet")
    try:
        return model.model_validate(raw)
    except PydanticValidationError as exc:
        raise FacetError(f"{node.id}: invalid {name!r} facet: {exc}") from exc


def membership_of(node: Node) -> Membership:
    return _load(node, MEMBERSHIP, Membership)


def edges_of(node: Node) -> Edges:
    return _load(node, EDGES, Edges)


def order_of(node: Node) -> Order:
    return _load(node, ORDER, Order)


def keys_of(node: Node) -> Keys:
    return _load(node, KEYS, Keys)


def require_unique_members(node: Node) -> None:
    members = membership_of(node).members
    if len(members) != len(set(members)):
        raise InvariantError(f"{node.id}: members must be unique")


def require_edge_endpoints_are_members(node: Node) -> None:
    members = set(membership_of(node).members)
    for e in edges_of(node).edges:
        if e.source not in members or e.target not in members:
            raise InvariantError(f"{node.id}: edge endpoints must be members")


def require_order_is_permutation(node: Node) -> None:
    members = membership_of(node).members
    order = order_of(node).order
    if len(order) != len(members) or set(order) != set(members):
        raise InvariantError(f"{node.id}: order must be a permutation of members")


def require_key_values_are_members(node: Node) -> None:
    members = set(membership_of(node).members)
    for value in keys_of(node).keys.values():
        if value not in members:
            raise InvariantError(f"{node.id}: key values must be members")


def require_acyclic(node: Node) -> None:
    adj: dict[str, list[str]] = {}
    for e in edges_of(node).edges:
        adj.setdefault(e.source, []).append(e.target)
    visiting, done = set(), set()

    def walk(n: str) -> None:
        if n in visiting:
            raise InvariantError(f"{node.id}: cycle detected at {n}")
        if n in done:
            return
        visiting.add(n)
        for nxt in adj.get(n, []):
            walk(nxt)
        visiting.discard(n)
        done.add(n)

    for start in list(adj):
        walk(start)


def require_single_parent(node: Node) -> None:
    parents: dict[str, int] = {}
    for e in edges_of(node).edges:
        parents[e.target] = parents.get(e.target, 0) + 1
    over = sorted(t for t, c in parents.items() if c > 1)
    if over:
        raise InvariantError(f"{node.id}: nodes with multiple parents: {over}")


def register_builtin_shapes(reg: Registry) -> None:
    reg.register_shape(ShapeSpec(name="set", required_facets={MEMBERSHIP},
                                 invariants=[require_unique_members]))
    reg.register_shape(ShapeSpec(name="list", required_facets={MEMBERSHIP, ORDER},
                                 invariants=[require_unique_members, require_order_is_permutation]))
    reg.register_shape(ShapeSpec(name="dict", required_facets={MEMBERSHIP, KEYS},
                                 invariants=[require_unique_members, require_key_values_are_members]))
    reg.register_shape(ShapeSpec(name="graph", required_facets={MEMBERSHIP, EDGES},
                                 invariants=[require_unique_members, require_edge_endpoints_are_members]))
    reg.register_shape(ShapeSpec(name="dag", required_facets={MEMBERSHIP, EDGES},
                                 invariants=[require_unique_members, require_edge_endpoints_are_members,
                                             require_acyclic]))
    reg.register_shape(ShapeSpec(name="tree", required_facets={MEMBERSHIP, EDGES},
                                 invariants=[require_unique_members, require_edge_endpoints_are_members,
                                             require_acyclic, require_single_parent]))
    for name in ("set", "list", "dict", "graph", "dag", "tree"):
        reg.register(KindSpec(name=name, shape=name))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_shapes.py -q`
Expected: PASS (all shape tests).

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes && rtk git add python/src/nodes/kernel/shapes.py python/tests/test_shapes.py
rtk git commit -m "feat(shapes-py): scope-only membership + edges/order/keys form facets + built-in shapes"
```

---

### Task 3: Structural index — form-facet ref extraction + generic `structural_refs` persistence

Current-code note: the generic `structural_refs` shape from this task is the current Python snapshot representation for structural refs. Later persistence work added broader snapshot integrity checks around it, so treat the snippets here as the original migration steps, not the full current `Index.from_dict()` contract.

**Files:**
- Modify: `python/src/nodes/kernel/index.py`
- Test: `python/tests/test_index.py`, `python/tests/test_index_snapshot.py`, `python/tests/test_index_rebuild_equivalence.py` (fixture migration), `python/tests/test_snapshot_load.py` (cache-malformation migration)

**Interfaces:**
- Consumes: facet constants `MEMBERSHIP`/`EDGES`/`ORDER`/`KEYS` (Task 2); `Node`, `Relation`.
- Produces (unchanged public API; internal shape changes):
  - `Role` Literal adds `edges_source`, `edges_target`, `order_member`, `keys_value`; keeps `relation_source/target`, `membership_member`; drops `membership_edge_source/target`.
  - `IndexEntry` drops its `membership` field (structure refs live in `out_refs`).
  - Snapshot entries persist `structural_refs: list[{"ref": str, "role": str}]` instead of `membership`.
  - `outbound_edges`/`inbound_edges`/`dangling_edges` continue to expose only `relation_*` roles (structure refs stay out of the graph).

- [ ] **Step 1a: Migrate the broken `test_index.py` fixture to the new model**

The existing `test_membership_refs_not_in_graph_queries` (in `python/tests/test_index.py`, ~lines 139-151) builds `graph:g` with the OLD bundled `membership` facet (`{shape, members, edges}`). That bundle no longer exists. Replace that whole test (keep the same assertions: outbound/inbound/dangling all `== []`) with the new split-facet fixture:

```python
def test_membership_refs_not_in_graph_queries():
    g = Node(id="graph:g", kind="graph", title="G", facets={
        "membership": {"members": ["topic:x"]},
        "edges": {"edges": [{"source": "topic:x", "predicate": "to", "target": "topic:y"}]},
    })
    x = Node(id="topic:x", kind="topic", title="X")
    y = Node(id="topic:y", kind="topic", title="Y")
    idx = Index.build([g, x, y])
    # membership members/edges are tracked for rename but are not public graph edges
    assert idx.outbound_edges(g.uid) == []
    assert idx.inbound_edges(y.uid) == []
    assert idx.dangling_edges() == []
```

- [ ] **Step 1b: Write the failing tests**

Append to `python/tests/test_index.py`:

```python
from nodes.kernel.node import Node as _Node
from nodes.kernel.shapes import EDGES as _EDGES
from nodes.kernel.shapes import MEMBERSHIP as _MEMBERSHIP
from nodes.kernel.shapes import ORDER as _ORDER


def _graph_node() -> _Node:
    return _Node(
        id="graph:g", kind="graph", title="G",
        facets={
            _MEMBERSHIP: {"members": ["topic:a", "topic:b"]},
            _EDGES: {"edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}]},
        },
    )


def test_structure_refs_register_referrers_but_not_graph_edges():
    from nodes.kernel.index import Index

    g = _graph_node()
    idx = Index.build([g])
    # membership members + edge endpoints are tracked as referrers (for rename):
    assert g.uid in {ir.source_uid for ir in idx.in_refs.get("topic:a", [])}
    assert g.uid in {ir.source_uid for ir in idx.in_refs.get("topic:b", [])}
    # ...but they are NOT relation-graph edges:
    assert idx.outbound_edges(g.uid) == []
    assert idx.dangling_edges() == []  # unresolved members are not dangling relation edges


def test_order_member_refs_are_tracked():
    from nodes.kernel.index import Index

    lst = _Node(id="list:l", kind="list", title="L",
                facets={_MEMBERSHIP: {"members": ["topic:a"]}, _ORDER: {"order": ["topic:a"]}})
    idx = Index.build([lst])
    assert lst.uid in {ir.source_uid for ir in idx.in_refs.get("topic:a", [])}
```

Migrate `python/tests/test_index_snapshot.py` (this file's `_corpus()` helper and several tests are keyed on the OLD bundled `membership`; they must be migrated before/with the new tests).

**(i) Migrate the `_corpus()` helper** (~lines 13-29) to the new split model:

```python
def _corpus() -> list[Node]:
    return [
        Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")]),
        Node(id="topic:b", kind="topic", title="B"),
        Node(
            id="graph:g",
            kind="graph",
            title="G",
            facets={
                "membership": {"members": ["topic:a", "topic:b"]},
                "edges": {"edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}]},
            },
        ),
    ]
```

**(ii) Update the missing-entry-keys parametrize** (~line 86) — `"membership"` is no longer a required entry key; `"structural_refs"` is:

```python
@pytest.mark.parametrize("field", ("uid", "id", "kind", "deprecated_ids", "relations", "structural_refs"))
def test_from_dict_rejects_missing_entry_keys(field):
    d = _single_entry_snapshot()
    del d["entries"][0][field]
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)
```

**(iii) DELETE these now-obsolete tests entirely** (they validate the membership sub-schema the snapshot no longer stores): `test_from_dict_rejects_invalid_membership_container`, `test_from_dict_rejects_invalid_membership_members`, `test_from_dict_rejects_invalid_membership_edges`, `test_from_dict_rejects_membership_missing_shape`, `test_from_dict_rejects_invalid_membership_edge_schema`, `test_from_dict_rejects_non_finite_membership_edge_weight`.

**(iv) DELETE the two `entry["membership"]` deep-copy tests** (the snapshot no longer carries a `membership` sub-document and `IndexEntry` no longer has a `membership` field): `test_to_dict_deep_copies_relation_attrs_and_membership` and `test_from_dict_deep_copies_relation_attrs_and_membership`. Replace them with a single relation-only deep-copy test that pins the same property the surviving half of those tests cared about (`to_dict`/`from_dict` deep-copy relation attrs):

```python
def test_to_dict_deep_copies_relation_attrs():
    idx = Index.build(
        [
            Node(
                id="topic:a",
                kind="topic",
                title="A",
                relations=[
                    Relation(
                        source="topic:a",
                        predicate="relatesTo",
                        target="topic:b",
                        attrs={"meta": {"score": 1}},
                    )
                ],
            )
        ]
    )

    d = idx.to_dict()
    d["entries"][0]["relations"][0]["attrs"]["meta"]["score"] = 2

    entry = next(iter(idx.by_uid.values()))
    relation = next(o.relation for o in entry.out_refs if o.role == "relation_source")
    assert relation is not None
    assert relation.attrs["meta"]["score"] == 1


def test_from_dict_deep_copies_relation_attrs():
    d = Index.build(
        [
            Node(
                id="topic:a",
                kind="topic",
                title="A",
                relations=[
                    Relation(
                        source="topic:a",
                        predicate="relatesTo",
                        target="topic:b",
                        attrs={"meta": {"score": 1}},
                    )
                ],
            )
        ]
    ).to_dict()

    restored = Index.from_dict(d)
    d["entries"][0]["relations"][0]["attrs"]["meta"]["score"] = 2

    entry = next(iter(restored.by_uid.values()))
    relation = next(o.relation for o in entry.out_refs if o.role == "relation_source")
    assert relation is not None
    assert relation.attrs["meta"]["score"] == 1
```

**(v) Replace `test_extract_out_refs_still_works_after_refactor`** (~lines 376-385) — the old role names `membership_edge_source`/`membership_edge_target` are gone; the migrated `_corpus()` graph now yields `membership_member`, `edges_source`, `edges_target`:

```python
def test_extract_out_refs_still_works_after_refactor():
    # Guards the _extract_out_refs refactor: existing build path unchanged.
    idx = Index.build(_corpus())
    g_uid = idx.id_to_uid["graph:g"]
    assert {o.role for o in idx.by_uid[g_uid].out_refs} >= {
        "membership_member",
        "edges_source",
        "edges_target",
    }
```

**(vi) Append the new structural-refs tests** to `python/tests/test_index_snapshot.py`:

```python
def test_structural_refs_round_trip():
    from nodes.kernel.index import Index
    from nodes.kernel.node import Node
    from nodes.kernel.shapes import EDGES, MEMBERSHIP

    g = Node(id="graph:g", kind="graph", title="G",
             facets={MEMBERSHIP: {"members": ["topic:a", "topic:b"]},
                     EDGES: {"edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}]}})
    idx = Index.build([g])

    doc = idx.to_dict()
    entry = next(e for e in doc["entries"] if e["id"] == "graph:g")
    assert "membership" not in entry
    roles = sorted(r["role"] for r in entry["structural_refs"])
    assert roles == ["edges_source", "edges_target", "membership_member", "membership_member"]

    restored = Index.from_dict(doc)
    assert g.uid in {ir.source_uid for ir in restored.in_refs.get("topic:a", [])}
    assert restored.outbound_edges(g.uid) == []


def test_from_dict_rejects_bad_structural_ref_role():
    from nodes.kernel.index import Index

    bad = {"entries": [{
        "uid": "u" * 32, "id": "graph:g", "kind": "graph", "deprecated_ids": [],
        "relations": [], "structural_refs": [{"ref": "topic:a", "role": "bogus"}],
    }]}
    with pytest.raises(ValueError):
        Index.from_dict(bad)


def test_from_dict_rejects_structural_refs_not_a_list():
    d = _single_entry_snapshot()
    d["entries"][0]["structural_refs"] = {}
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)


def test_from_dict_rejects_structural_ref_non_string_ref():
    d = _single_entry_snapshot()
    d["entries"][0]["structural_refs"] = [{"ref": 123, "role": "membership_member"}]
    with pytest.raises(ValueError, match="structural snapshot:"):
        Index.from_dict(d)
```

(`pytest`, `Index`, `Node`, `Relation`, and `relates_to` are already imported at the top of `test_index_snapshot.py`; the new tests reuse those module-level imports rather than the function-local ones shown in the round-trip example.)

- [ ] **Step 1c: Migrate the `test_index_rebuild_equivalence.py` fixture**

The `_normalize`/`_relation_signature`/`_out_ref_signature` helpers in `python/tests/test_index_rebuild_equivalence.py` read `e.out_refs` (NOT `entry.membership`), so they need NO change. Only the corpus fixture (~lines 58-62) builds `graph:g` with the OLD bundled `membership`. Replace that `c.add(...)` call with the split-facet form (the surrounding mutation-sequence assertions stay exactly as they are):

```python
    c.add(Node(id="graph:g", kind="graph", title="G", facets={
        "membership": {"members": ["topic:a", "topic:b"]},
        "edges": {"edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}]},
    }))
```

- [ ] **Step 1d: Migrate the `test_snapshot_load.py` membership-malformation tests**

In `python/tests/test_snapshot_load.py`, five tests craft an OLD bundled `membership` sub-document on a structural entry and assert `load_snapshot(...)` returns `None` (silent rebuild on a malformed cache). After the source change, setting an EXTRA `"membership"` key would be IGNORED by `from_dict` (it only rejects *missing* required keys, not extra ones), so those tests would no longer trigger a rebuild — they must target `structural_refs` instead. DELETE these five tests:

`test_malformed_structural_membership_members_string_returns_none`, `test_malformed_structural_membership_edges_dict_returns_none`, `test_malformed_structural_membership_edge_source_returns_none`, `test_malformed_structural_membership_missing_shape_returns_none`, `test_malformed_structural_membership_edge_schema_returns_none`.

Replace them with three structural_refs-malformation equivalents (a non-list `structural_refs`; a structural_ref missing `ref`; a structural_ref with an invalid `role`), preserving the exact surrounding assertion style (`_write` → mutate `doc` → `write_json_atomic` → assert `load_snapshot(tmp_path, None) is None`):

```python
def test_malformed_structural_refs_not_a_list_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"][0]["structural_refs"] = {}
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_structural_ref_missing_ref_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"][0]["structural_refs"] = [{"role": "membership_member"}]
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_structural_ref_invalid_role_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"][0]["structural_refs"] = [{"ref": "topic:a", "role": "bogus"}]
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None
```

(The `_nodes()` corpus in `test_snapshot_load.py` is relation-only, so each structural entry already serializes an empty `structural_refs: []` after the source change — these tests mutate that key to a malformed value. No other test in this file references `membership`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk uv run pytest tests/test_index.py tests/test_index_snapshot.py -q`
Expected: FAIL — `outbound_edges`/snapshot still derive from `membership`; `structural_refs` key absent; `membership` key still present.

- [ ] **Step 3: Implement the index changes**

In `python/src/nodes/kernel/index.py`:

(a) Replace the `Role` definition and the `from ... shapes import MEMBERSHIP` line:

```python
from nodes.kernel.shapes import EDGES, KEYS, MEMBERSHIP, ORDER

Role = Literal[
    "relation_source",
    "relation_target",
    "membership_member",
    "edges_source",
    "edges_target",
    "order_member",
    "keys_value",
]

_STRUCTURAL_ENTRY_KEYS = frozenset({"uid", "id", "kind", "deprecated_ids", "relations", "structural_refs"})
_STRUCTURAL_REF_ROLES = frozenset({"membership_member", "edges_source", "edges_target", "order_member", "keys_value"})
```

(b) Remove the `membership` field from `IndexEntry`:

```python
@dataclass
class IndexEntry:
    uid: str
    id: str
    kind: str
    deprecated_ids: frozenset[str]
    out_refs: list[OutRef]
```

(c) Replace `_out_refs_from`/`_extract_out_refs` (lines 58–81) with:

```python
def _relation_out_refs(relations: list[Relation]) -> list[OutRef]:
    refs: list[OutRef] = []
    for rel in relations:
        refs.append(OutRef(ref=rel.source, role="relation_source", relation=rel))
        refs.append(OutRef(ref=rel.target, role="relation_target", relation=rel))
    return refs


def _structural_out_refs(node: Node) -> list[OutRef]:
    """Refs from the built-in structural facets. Read directly from `node.facets`
    (registry-independent); they populate `in_refs` for rename + dangling integrity but
    are never relation-graph edges (their `relation` is None)."""
    refs: list[OutRef] = []
    mem = node.facets.get(MEMBERSHIP)
    if isinstance(mem, dict):
        for m in mem.get("members", []) or []:
            if isinstance(m, str):
                refs.append(OutRef(ref=m, role="membership_member"))
    eg = node.facets.get(EDGES)
    if isinstance(eg, dict):
        for edge in eg.get("edges", []) or []:
            if isinstance(edge, dict):
                if isinstance(edge.get("source"), str):
                    refs.append(OutRef(ref=edge["source"], role="edges_source"))
                if isinstance(edge.get("target"), str):
                    refs.append(OutRef(ref=edge["target"], role="edges_target"))
    od = node.facets.get(ORDER)
    if isinstance(od, dict):
        for m in od.get("order", []) or []:
            if isinstance(m, str):
                refs.append(OutRef(ref=m, role="order_member"))
    ky = node.facets.get(KEYS)
    if isinstance(ky, dict):
        keys = ky.get("keys", {})
        if isinstance(keys, dict):
            for v in keys.values():
                if isinstance(v, str):
                    refs.append(OutRef(ref=v, role="keys_value"))
    return refs


def _extract_out_refs(node: Node) -> list[OutRef]:
    return _relation_out_refs(node.relations) + _structural_out_refs(node)
```

(d) Replace `_validated_membership` (lines 106–152) with:

```python
def _validated_structural_refs(raw: object) -> list[OutRef]:
    if not isinstance(raw, list):
        raise ValueError("structural snapshot: structural_refs must be a list")
    out: list[OutRef] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("structural snapshot: structural_ref must be a dict")
        ref = item.get("ref")
        role = item.get("role")
        if not isinstance(ref, str):
            raise ValueError("structural snapshot: structural_ref ref must be a string")
        if role not in _STRUCTURAL_REF_ROLES:
            raise ValueError("structural snapshot: structural_ref role is invalid")
        out.append(OutRef(ref=ref, role=role))  # type: ignore[arg-type]
    return out
```

(e) In `upsert` (lines 205–222), drop the `membership` local and the `membership=` arg:

```python
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
```

(f) In `to_dict` (lines 224–251), emit `structural_refs` instead of `membership`:

```python
            entries.append(
                {
                    "uid": entry.uid,
                    "id": entry.id,
                    "kind": entry.kind,
                    "deprecated_ids": sorted(entry.deprecated_ids),
                    "relations": relations,
                    "structural_refs": [
                        {"ref": o.ref, "role": o.role}
                        for o in entry.out_refs
                        if not o.role.startswith("relation_")
                    ],
                }
            )
```

(g) In `from_dict` (lines 272–312), replace the `membership_raw`/`_validated_membership`/`_out_refs_from` lines:

```python
            relations_raw = raw["relations"]
            structural_refs_raw = raw["structural_refs"]
```

and, after the `relations` list is built (replacing the `membership = _validated_membership(...)` and `out_refs = _out_refs_from(...)` lines):

```python
            structural_refs = _validated_structural_refs(structural_refs_raw)
            out_refs = _relation_out_refs(relations) + structural_refs
            entry = IndexEntry(
                uid=uid,
                id=entry_id,
                kind=kind,
                deprecated_ids=frozenset(deprecated_ids),
                out_refs=out_refs,
            )
```

Leave `outbound_edges`, `inbound_edges`, `dangling_edges`, `_relations_by_role`, `_drop`, `_resolve_edge`, `_refs_for_uid` unchanged — they already filter to `relation_*` roles, so structure refs stay out of the graph automatically.

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_index.py tests/test_index_snapshot.py tests/test_index_rebuild_equivalence.py tests/test_snapshot_load.py -q`
Expected: PASS (all four files). (`test_index_rebuild_equivalence.py` re-checks that a rebuilt index equals a snapshot-loaded one — confirms the new `structural_refs` round-trip is faithful; `test_snapshot_load.py` confirms a malformed `structural_refs` cache triggers a silent rebuild.)

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes && rtk git add python/src/nodes/kernel/index.py python/tests/test_index.py python/tests/test_index_snapshot.py python/tests/test_index_rebuild_equivalence.py python/tests/test_snapshot_load.py
rtk git commit -m "feat(shapes-py): index extracts structural refs from form facets; persists generic structural_refs"
```

---

### Task 4: Corpus rename — rewrite refs across the form facets

Current-code note: the no-registry rewrite contract is still current. Current `Corpus.rename` also maintains `SearchIndex`, optional `VectorIndex`, and the snapshot manifest after the structural rewrite succeeds.

**Files:**
- Modify: `python/src/nodes/kernel/corpus.py:12,25-46`
- Test: `python/tests/test_corpus_persistence_rename.py`, `python/tests/test_corpus.py` (fixture + behavior migration)

**Interfaces:**
- Consumes: facet constants `MEMBERSHIP`/`EDGES`/`ORDER`/`KEYS` (Task 2); the `in_refs` referrer index (Task 3) already lists nodes that reference a renamed id via any structural facet.
- Produces: `_rewrite_refs(node, old, new)` rewrites `old → new` in `relations`, `membership.members`, `edges` endpoints, `order` entries, and `keys` values.

- [ ] **Step 1a: Migrate the broken `test_corpus.py` rename tests to the new model**

Two tests in `python/tests/test_corpus.py` build OLD bundled `membership` facets and assert OLD rewrite behavior. Migrate both (do NOT delete coverage — convert it) and add a third covering the `order` facet. `Corpus(tmp_path)` is used with NO registry — keep it that way (this also exercises no-registry ref rewriting).

Replace `test_rename_rewrites_membership_members_and_edges` (~lines 112-124) and `test_rename_rewrites_dict_membership` (~lines 127-137) with the following three tests:

```python
def test_rename_rewrites_membership_members_and_edges(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:x", kind="topic", title="X"))
    c.add(Node(id="graph:g", kind="graph", title="G", facets={
        "membership": {"members": ["topic:old", "topic:x"]},
        "edges": {"edges": [{"source": "topic:old", "predicate": "to", "target": "topic:x"}]},
    }))
    c.rename("topic:old", "topic:new")
    g = c.get("graph:g")
    members = g.facets["membership"]["members"]
    assert "topic:new" in members and "topic:old" not in members
    assert g.facets["edges"]["edges"][0]["source"] == "topic:new"  # edge SOURCE rewritten


def test_rename_rewrites_dict_membership(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="topic:x", kind="topic", title="X"))
    c.add(Node(id="dict:d", kind="dict", title="D", facets={
        "membership": {"members": ["topic:old", "topic:x"]},
        "keys": {"keys": {"a": "topic:old", "b": "topic:x"}},
    }))
    c.rename("topic:old", "topic:new")
    keys = c.get("dict:d").facets["keys"]["keys"]
    assert keys["a"] == "topic:new" and keys["b"] == "topic:x"


def test_rename_rewrites_list_order(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:old", kind="topic", title="Old"))
    c.add(Node(id="list:l", kind="list", title="L", facets={
        "membership": {"members": ["topic:old"]},
        "order": {"order": ["topic:old"]},
    }))
    c.rename("topic:old", "topic:new")
    lst = c.get("list:l")
    assert lst.facets["membership"]["members"] == ["topic:new"]
    assert lst.facets["order"]["order"] == ["topic:new"]
```

- [ ] **Step 1b: Write the failing test**

Append to `python/tests/test_corpus_persistence_rename.py`. Opening the `Corpus` with **no registry** is deliberate: it proves the no-registry recognition guarantee — structural refs are rewritten on rename even when nothing is registered to validate them. (This single comprehensive graph+list+dict no-registry test is the canonical no-registry case; the `test_corpus.py` tests above migrate the pre-existing per-facet coverage and use the `Corpus.add` path.)

```python
def test_rename_rewrites_structure_form_facet_refs_without_registry(tmp_path):
    from nodes.kernel.corpus import Corpus
    from nodes.kernel.node import Node
    from nodes.kernel.shapes import EDGES, KEYS, MEMBERSHIP, ORDER

    c = Corpus(tmp_path)  # no registry attached
    c.store.write_file(Node(id="topic:a", kind="topic", title="A"))
    c.store.write_file(Node(id="topic:b", kind="topic", title="B"))
    c.store.write_file(Node(
        id="graph:g", kind="graph", title="G",
        facets={MEMBERSHIP: {"members": ["topic:a", "topic:b"]},
                EDGES: {"edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}]}},
    ))
    c.store.write_file(Node(
        id="list:l", kind="list", title="L",
        facets={MEMBERSHIP: {"members": ["topic:a"]}, ORDER: {"order": ["topic:a"]}},
    ))
    c.store.write_file(Node(
        id="dict:d", kind="dict", title="D",
        facets={MEMBERSHIP: {"members": ["topic:a"]}, KEYS: {"keys": {"k": "topic:a"}}},
    ))
    c = Corpus(tmp_path)  # reload: index sees every structural ref, with no registry

    c.rename("topic:a", "topic:c")

    g = c.store.read_file("graph:g")
    assert g.facets[MEMBERSHIP]["members"] == ["topic:c", "topic:b"]
    assert g.facets[EDGES]["edges"][0]["source"] == "topic:c"
    assert c.store.read_file("list:l").facets[ORDER]["order"] == ["topic:c"]
    assert c.store.read_file("dict:d").facets[KEYS]["keys"] == {"k": "topic:c"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk uv run pytest tests/test_corpus_persistence_rename.py::test_rename_rewrites_structure_form_facet_refs_without_registry tests/test_corpus.py -q`
Expected: FAIL — the new/migrated tests fail because `edges`/`order`/`keys` are not rewritten (only `membership.members` and the old bundled `membership.edges` were handled).

- [ ] **Step 3: Implement the rename rewrite**

In `python/src/nodes/kernel/corpus.py`, change the import on line 12:

```python
from nodes.kernel.shapes import EDGES, KEYS, MEMBERSHIP, ORDER
```

and replace `_rewrite_refs` (lines 25–46) with:

```python
def _rewrite_refs(node: Node, old: str, new: str) -> None:
    """Rewrite every position in `node` that holds `old` to `new` (in place):
    top-level relations plus the built-in structural form facets."""
    for rel in node.relations:
        if rel.source == old:
            rel.source = new
        if rel.target == old:
            rel.target = new
    mem = node.facets.get(MEMBERSHIP)
    if isinstance(mem, dict) and isinstance(mem.get("members"), list):
        mem["members"] = [new if m == old else m for m in mem["members"]]
    eg = node.facets.get(EDGES)
    if isinstance(eg, dict):
        for edge in eg.get("edges", []) or []:
            if isinstance(edge, dict):
                if edge.get("source") == old:
                    edge["source"] = new
                if edge.get("target") == old:
                    edge["target"] = new
    od = node.facets.get(ORDER)
    if isinstance(od, dict) and isinstance(od.get("order"), list):
        od["order"] = [new if m == old else m for m in od["order"]]
    ky = node.facets.get(KEYS)
    if isinstance(ky, dict) and isinstance(ky.get("keys"), dict):
        for key, val in list(ky["keys"].items()):
            if val == old:
                ky["keys"][key] = new
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_corpus_persistence_rename.py tests/test_corpus.py -q`
Expected: PASS (the new structural-rename test plus the existing rename/corpus tests).

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes && rtk git add python/src/nodes/kernel/corpus.py python/tests/test_corpus_persistence_rename.py python/tests/test_corpus.py
rtk git commit -m "feat(shapes-py): rename rewrites refs across membership/edges/order/keys form facets"
```

---

### Task 5: Docs — update the structural-shapes section of `STANDARD.md`

**Files:**
- Modify: `python/src/nodes/vocab/kinds.py:20` (comment only), `docs/STANDARD.md`

**Interfaces:**
- Consumes: nothing new. Documents the Task 1–4 model.
- Produces: corrected prose; no code behavior change.

- [ ] **Step 1: Update `STANDARD.md`**

In `docs/STANDARD.md`, find the structural-shapes paragraph that currently reads `{shape, members, edges?}` and the shape list, and replace that paragraph (around line 23–24) with:

```markdown
A **structure** is a node of a registered *shape* carrying a scope-only `membership` facet
(`{members}`) plus the shape-owned form facet(s) it requires: `edges` (`{edges}`) for
`graph`/`dag`/`tree`, `order` (`{order}`) for `list`, `keys` (`{keys}`) for `dict`; `set` is
membership-only. Shapes are registered via `ShapeSpec`; a kind adopts ≤1 shape through
`KindSpec.shape`, and the registry composes the shape's required facets + invariants into the kind
(`register_builtin_shapes` registers `set`, `list`, `dict`, `graph`, `dag`, `tree` and their
convenience kinds). Membership is a unique unordered set; order/edges/keys never leak through member
position.
```

In the structural-index paragraph (around line 35), update the parenthetical describing tracked refs to:

```markdown
(relation `source`/`target`, membership members, and `edges`/`order`/`keys` form-facet refs)
```

Leave the existing note (around line 49–50) that membership/form refs "are tracked internally for
rename but are not exposed as graph edges" — it remains correct.

- [ ] **Step 2: Update the `vocab/kinds.py` doc comment**

In `python/src/nodes/vocab/kinds.py`, the docstring of `register_knowledge_vocab` says
"Mirrors `nodes.kernel.shapes.register_builtin_shapes`." Leave the reference (still valid), but it
is informational only — no code change required. (This step exists so the reviewer confirms the
comment is not stale; the function still mirrors the builtin-shape registration pattern.)

- [ ] **Step 3: Verify the golden-format test still passes**

Run: `rtk uv run pytest tests/test_format_golden.py -q`
Expected: PASS (this test guards `STANDARD.md` round-trip examples, not the prose; confirm no example block was broken).

- [ ] **Step 4: Run the full gate**

Run:
```
rtk uv run pytest tests -q
rtk uv run ruff check src tests
rtk uv run pyright src
```
Expected: all PASS / no errors.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes && rtk git add docs/STANDARD.md python/src/nodes/vocab/kinds.py
rtk git commit -m "docs(shapes-py): document membership/form-facet shape model in docs/STANDARD.md"
```

---

## Final Verification (whole-plan)

From `~/d/nodes/python`, the full gate must be green:

```
rtk uv run pytest tests -q          # all tests pass
rtk uv run ruff check src tests     # clean
rtk uv run pyright src              # no type errors
```

Key invariants to confirm by inspection after the gate is green:
- `membership` facet is scope-only (`{members}`); `edges`/`order`/`keys` are separate form facets.
- `Registry.validate` composes shape + kind facets/invariants; duplicate shape and kind names fail; unknown adopted shape fails; a shape and kind may share a name.
- Structure refs populate `in_refs` (so rename finds referrers) but never appear in `outbound`/`inbound`/`dangling` (those are `relation_*` only).
- Rename rewrites refs across `relations` + all four structural facets, with or without a registry.
- The structural snapshot persists `structural_refs` (generic `{ref, role}`) — adding a future shape needs no snapshot-schema change.
