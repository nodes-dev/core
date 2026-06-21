# nodes Python Kernel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python reference implementation of the `nodes` kernel — the domain-free data model, on-disk format, registry/validation, and file CRUD — in the new `~/d/nodes/` repo.

**Architecture:** A single `nodes` package with a `nodes.kernel` subpackage (reserving `nodes.vocab` / `nodes.domains` for later plans). Markdown + YAML frontmatter is the canonical store; the kernel parses/serializes it into Pydantic models, validates kinds against a registry, and performs file CRUD + rename over a corpus directory. No derived index, no TypeScript, no knowledge-vocab kinds in this plan.

**Tech Stack:** Python ≥3.11, Pydantic ≥2, PyYAML, `uv` (deps + runner), pytest, ruff (line-length 120), pyright (basic), hatchling build, `src/` layout.

## Global Constraints

- Python `requires-python = ">=3.11"`; type-check mode `basic`.
- Every module starts with `from __future__ import annotations`.
- Pydantic v2 `BaseModel`; snake_case field names (no camelCase aliases).
- ruff `line-length = 120`.
- Import package is `nodes`; kernel code lives under `src/nodes/kernel/`; tests under `tests/`.
- All commands run through `uv` (e.g. `uv run pytest …`).
- Canonical id form `kind:slug` is the stored **and** display ref form; `uid` is an immutable UUID anchor on every node (spec §3.1, §3.5).
- One `Relation` primitive; on disk `source` is implied by location (spec §3.2): node-relations omit `source`, graph edges keep both endpoints.
- Facets serialize as a nested `facets:` map (spec §4).
- Reference spec: `~/d/nodes/docs/specs/2026-06-21-nodes-substrate-design.md`.

---

### Task 1: Repo scaffold + error hierarchy

**Files:**
- Create: `~/d/nodes/pyproject.toml`
- Create: `~/d/nodes/src/nodes/__init__.py`
- Create: `~/d/nodes/src/nodes/kernel/__init__.py`
- Create: `~/d/nodes/src/nodes/kernel/errors.py`
- Test: `~/d/nodes/tests/test_errors.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: exception hierarchy importable as `from nodes.kernel.errors import NodesError, IdError, RefError, CollisionError, UnknownKindError, FacetError, InvariantError, ValidationError`. All inherit `NodesError(Exception)`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "nodes"
version = "0.1.0"
description = "Problem-agnostic knowledge substrate kernel"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2.0",
  "pyyaml>=6.0.3",
]

[build-system]
requires = ["hatchling>=1.24"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/nodes"]

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]

[tool.ruff]
line-length = 120

[tool.pyright]
pythonVersion = "3.11"
typeCheckingMode = "basic"

[dependency-groups]
dev = [
    "pytest>=9.0",
    "ruff>=0.15.7",
    "pyright>=1.1.390",
]
```

- [ ] **Step 2: Create empty package markers**

`src/nodes/__init__.py`:
```python
from __future__ import annotations
```

`src/nodes/kernel/__init__.py`:
```python
from __future__ import annotations
```

- [ ] **Step 3: Write the failing test**

`tests/test_errors.py`:
```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import (
    CollisionError,
    FacetError,
    IdError,
    InvariantError,
    NodesError,
    RefError,
    UnknownKindError,
    ValidationError,
)


@pytest.mark.parametrize(
    "exc",
    [IdError, RefError, CollisionError, UnknownKindError, FacetError, InvariantError, ValidationError],
)
def test_all_errors_subclass_base(exc):
    assert issubclass(exc, NodesError)
    assert issubclass(NodesError, Exception)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.errors'`.

- [ ] **Step 5: Write minimal implementation**

`src/nodes/kernel/errors.py`:
```python
from __future__ import annotations


class NodesError(Exception):
    """Base class for all nodes kernel errors."""


class IdError(NodesError):
    """Raised on a malformed canonical id (`kind:slug`)."""


class RefError(NodesError):
    """Raised when a reference cannot be resolved or is malformed."""


class CollisionError(NodesError):
    """Raised when an id collides with a live id or an active deprecated id."""


class UnknownKindError(NodesError):
    """Raised when a node's kind is not registered."""


class FacetError(NodesError):
    """Raised when a facet payload is malformed or a required facet is missing."""


class InvariantError(NodesError):
    """Raised when a structural-shape invariant is violated."""


class ValidationError(NodesError):
    """Raised when a node fails validation against its kind."""
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_errors.py -v`
Expected: PASS (7 parametrized cases).

- [ ] **Step 7: Commit**

```bash
cd ~/d/nodes
git add pyproject.toml src/nodes tests/test_errors.py
git commit -m "feat(kernel): scaffold nodes package + error hierarchy"
```

---

### Task 2: Canonical identity (`NodeId`)

**Files:**
- Create: `src/nodes/kernel/ids.py`
- Test: `tests/test_ids.py`

**Interfaces:**
- Consumes: `IdError` from `nodes.kernel.errors`.
- Produces:
  - `Ref = str` (type alias for a `kind:slug` reference string).
  - `KIND_RE`, `SLUG_RE` (compiled `re.Pattern`).
  - `class NodeId(BaseModel)` with fields `kind: str`, `slug: str`; classmethod `parse(raw: str) -> NodeId` (raises `IdError`); `__str__() -> str` returns `"{kind}:{slug}"`; staticmethods `is_valid_kind(kind: str) -> bool`, `is_valid_slug(slug: str) -> bool`.

- [ ] **Step 1: Write the failing test**

`tests/test_ids.py`:
```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import IdError
from nodes.kernel.ids import NodeId


def test_parse_simple():
    nid = NodeId.parse("topic:polycomb")
    assert nid.kind == "topic"
    assert nid.slug == "polycomb"
    assert str(nid) == "topic:polycomb"


def test_parse_curie_slug_keeps_inner_colons():
    nid = NodeId.parse("gene:HGNC:7296")
    assert nid.kind == "gene"
    assert nid.slug == "HGNC:7296"
    assert str(nid) == "gene:HGNC:7296"


def test_parse_rejects_missing_colon():
    with pytest.raises(IdError):
        NodeId.parse("nocolon")


def test_parse_rejects_bad_kind():
    with pytest.raises(IdError):
        NodeId.parse("Topic:polycomb")  # uppercase kind not allowed


def test_parse_rejects_empty_slug():
    with pytest.raises(IdError):
        NodeId.parse("topic:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ids.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.ids'`.

- [ ] **Step 3: Write minimal implementation**

`src/nodes/kernel/ids.py`:
```python
from __future__ import annotations

import re

from pydantic import BaseModel

from nodes.kernel.errors import IdError

Ref = str

KIND_RE = re.compile(r"^[a-z][a-z0-9-]*$")
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_.-]*$")


class NodeId(BaseModel):
    """Canonical typed identifier: `kind:slug`."""

    kind: str
    slug: str

    @staticmethod
    def is_valid_kind(kind: str) -> bool:
        return bool(KIND_RE.match(kind))

    @staticmethod
    def is_valid_slug(slug: str) -> bool:
        return bool(SLUG_RE.match(slug))

    @classmethod
    def parse(cls, raw: str) -> "NodeId":
        if ":" not in raw:
            raise IdError(f"id must be 'kind:slug', got {raw!r}")
        kind, slug = raw.split(":", 1)
        if not cls.is_valid_kind(kind):
            raise IdError(f"invalid kind {kind!r} in id {raw!r}")
        if not cls.is_valid_slug(slug):
            raise IdError(f"invalid slug {slug!r} in id {raw!r}")
        return cls(kind=kind, slug=slug)

    def __str__(self) -> str:
        return f"{self.kind}:{self.slug}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ids.py -v`
Expected: PASS (5 cases).

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/ids.py tests/test_ids.py
git commit -m "feat(kernel): NodeId canonical id parse/validate"
```

---

### Task 3: Relation primitive + serialized forms + sugar

**Files:**
- Create: `src/nodes/kernel/relations.py`
- Test: `tests/test_relations.py`

**Interfaces:**
- Consumes: `Ref` from `nodes.kernel.ids`.
- Produces:
  - `RELATES_TO = "relatesTo"`.
  - `class Relation(BaseModel)`: `source: str`, `predicate: str`, `target: str`, `directed: bool = True`, `weight: float | None = None`, `attrs: dict[str, Any] = {}`.
    - classmethod `from_serialized(data: dict, container_id: str) -> Relation` — fills `source` from `data["source"]` if present else `container_id`.
    - method `to_serialized(container_id: str) -> dict` — emits `predicate`/`target`, includes `source` only when `source != container_id`, includes `directed`/`weight`/`attrs` only when non-default.
  - `relates_to(source: str, target: str) -> Relation`.
  - `tag_to_relation(source: str, tag: str, alias_map: dict[str, str]) -> Relation` — strips leading `#`, resolves alias→id via `alias_map`, raises `RefError` if unresolved.

- [ ] **Step 1: Write the failing test**

`tests/test_relations.py`:
```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import RefError
from nodes.kernel.relations import RELATES_TO, Relation, relates_to, tag_to_relation


def test_node_relation_roundtrip_drops_source():
    rel = Relation(source="gene:PHF19", predicate="interacts_with", target="gene:EZH2")
    ser = rel.to_serialized("gene:PHF19")
    assert ser == {"predicate": "interacts_with", "target": "gene:EZH2"}
    back = Relation.from_serialized(ser, container_id="gene:PHF19")
    assert back == rel


def test_graph_edge_keeps_both_endpoints():
    edge = Relation(source="thought:a", predicate="relatesTo", target="thought:b")
    ser = edge.to_serialized("graph:mymap")  # container is the structure, not an endpoint
    assert ser == {"source": "thought:a", "predicate": "relatesTo", "target": "thought:b"}


def test_serialized_includes_non_default_attrs():
    rel = Relation(source="a:x", predicate="cites", target="b:y", weight=0.5, attrs={"note": "n"})
    ser = rel.to_serialized("a:x")
    assert ser == {"predicate": "cites", "target": "b:y", "weight": 0.5, "attrs": {"note": "n"}}


def test_relates_to_sugar():
    rel = relates_to("topic:a", "topic:b")
    assert rel.predicate == RELATES_TO
    assert rel.source == "topic:a" and rel.target == "topic:b"


def test_tag_resolves_via_alias_map():
    rel = tag_to_relation("thought:a", "#biology", {"biology": "topic:biology"})
    assert rel == relates_to("thought:a", "topic:biology")


def test_tag_unresolved_raises():
    with pytest.raises(RefError):
        tag_to_relation("thought:a", "#missing", {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_relations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.relations'`.

- [ ] **Step 3: Write minimal implementation**

`src/nodes/kernel/relations.py`:
```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nodes.kernel.errors import RefError

RELATES_TO = "relatesTo"


class Relation(BaseModel):
    """The single edge primitive (normalized form: source always explicit)."""

    source: str
    predicate: str
    target: str
    directed: bool = True
    weight: float | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_serialized(cls, data: dict, container_id: str) -> "Relation":
        return cls(
            source=data.get("source", container_id),
            predicate=data["predicate"],
            target=data["target"],
            directed=data.get("directed", True),
            weight=data.get("weight"),
            attrs=data.get("attrs", {}),
        )

    def to_serialized(self, container_id: str) -> dict:
        out: dict[str, Any] = {}
        if self.source != container_id:
            out["source"] = self.source
        out["predicate"] = self.predicate
        out["target"] = self.target
        if self.directed is not True:
            out["directed"] = self.directed
        if self.weight is not None:
            out["weight"] = self.weight
        if self.attrs:
            out["attrs"] = self.attrs
        return out


def relates_to(source: str, target: str) -> Relation:
    return Relation(source=source, predicate=RELATES_TO, target=target)


def tag_to_relation(source: str, tag: str, alias_map: dict[str, str]) -> Relation:
    name = tag.lstrip("#")
    target = alias_map.get(name) or alias_map.get(name.lower())
    if target is None:
        raise RefError(f"tag {tag!r} does not resolve to a known node")
    return relates_to(source, target)
```

Note: `to_serialized` emits `predicate` before `target` by insertion order; the test compares dict equality (order-insensitive), so this is safe.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_relations.py -v`
Expected: PASS (6 cases).

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/relations.py tests/test_relations.py
git commit -m "feat(kernel): Relation primitive with serialized forms + tag/relatesTo sugar"
```

---

### Task 4: Node model

**Files:**
- Create: `src/nodes/kernel/node.py`
- Test: `tests/test_node.py`

**Interfaces:**
- Consumes: `Relation` from `nodes.kernel.relations`; `NodeId` from `nodes.kernel.ids`; `ValidationError` from `nodes.kernel.errors`.
- Produces:
  - `class NodeMetadata(BaseModel)`: `created: date | None = None`, `updated: date | None = None`, `version: int = 1`.
  - `def new_uid() -> str` — returns `uuid4().hex`.
  - `class Node(BaseModel)`: `id: str`, `uid: str = Field(default_factory=new_uid)`, `kind: str`, `title: str`, `body: str = ""`, `metadata: NodeMetadata = NodeMetadata()`, `relations: list[Relation] = []`, `facets: dict[str, dict] = {}`, `deprecated_ids: list[str] = []`. A model validator asserts `id` parses and its kind segment equals `kind` (raises `ValidationError`). There is **no** `related` model field: `related:` is an on-disk serialization sugar over `relatesTo` relations (handled in Task 7), not stored separately.

- [ ] **Step 1: Write the failing test**

`tests/test_node.py`:
```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import ValidationError
from nodes.kernel.node import Node, new_uid


def test_node_minimal_defaults():
    n = Node(id="topic:polycomb", kind="topic", title="Polycomb")
    assert n.body == ""
    assert n.metadata.version == 1
    assert n.relations == [] and n.facets == {}
    assert len(n.uid) == 32  # uuid4 hex


def test_uid_is_unique_per_node():
    a = Node(id="topic:a", kind="topic", title="A")
    b = Node(id="topic:b", kind="topic", title="B")
    assert a.uid != b.uid


def test_explicit_uid_preserved():
    fixed = new_uid()
    n = Node(id="topic:a", kind="topic", title="A", uid=fixed)
    assert n.uid == fixed


def test_id_kind_mismatch_rejected():
    with pytest.raises(ValidationError):
        Node(id="topic:a", kind="note", title="Mismatch")


def test_id_must_be_wellformed():
    with pytest.raises(ValidationError):
        Node(id="nocolon", kind="nocolon", title="Bad")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_node.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.node'`.

- [ ] **Step 3: Write minimal implementation**

`src/nodes/kernel/node.py`:
```python
from __future__ import annotations

from datetime import date
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from nodes.kernel.errors import IdError, ValidationError
from nodes.kernel.ids import NodeId
from nodes.kernel.relations import Relation


def new_uid() -> str:
    return uuid4().hex


class NodeMetadata(BaseModel):
    created: date | None = None
    updated: date | None = None
    version: int = 1


class Node(BaseModel):
    id: str
    uid: str = Field(default_factory=new_uid)
    kind: str
    title: str
    body: str = ""
    metadata: NodeMetadata = Field(default_factory=NodeMetadata)
    relations: list[Relation] = Field(default_factory=list)
    facets: dict[str, dict] = Field(default_factory=dict)
    deprecated_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_id_kind(self) -> "Node":
        try:
            parsed = NodeId.parse(self.id)
        except IdError as exc:
            raise ValidationError(str(exc)) from exc
        if parsed.kind != self.kind:
            raise ValidationError(f"id kind {parsed.kind!r} != kind field {self.kind!r}")
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_node.py -v`
Expected: PASS (5 cases).

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/node.py tests/test_node.py
git commit -m "feat(kernel): Node model with uid anchor + id/kind consistency"
```

---

### Task 5: Kind registry + validation

**Files:**
- Create: `src/nodes/kernel/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: `Node` from `nodes.kernel.node`; `UnknownKindError`, `FacetError` from `nodes.kernel.errors`.
- Produces:
  - `Invariant = Callable[[Node], None]` (raises on violation).
  - `class KindSpec(BaseModel)`: `name: str`, `required_facets: set[str] = set()`, `optional_facets: set[str] = set()`, `invariants: list[Invariant] = []` (config `arbitrary_types_allowed=True`).
  - `class Registry`: `register(spec: KindSpec) -> None`; `get(kind: str) -> KindSpec` (raises `UnknownKindError`); `is_registered(kind: str) -> bool`; `validate(node: Node) -> None` — checks kind registered, every `required_facets` present in `node.facets`, no facet outside `required ∪ optional`, then runs each invariant.

- [ ] **Step 1: Write the failing test**

`tests/test_registry.py`:
```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import FacetError, InvariantError, UnknownKindError
from nodes.kernel.node import Node
from nodes.kernel.registry import KindSpec, Registry


def _node(**facets) -> Node:
    return Node(id="topic:a", kind="topic", title="A", facets=facets)


def test_unknown_kind_raises():
    reg = Registry()
    with pytest.raises(UnknownKindError):
        reg.validate(_node())


def test_missing_required_facet_raises():
    reg = Registry()
    reg.register(KindSpec(name="topic", required_facets={"summary"}))
    with pytest.raises(FacetError):
        reg.validate(_node())


def test_unexpected_facet_raises():
    reg = Registry()
    reg.register(KindSpec(name="topic"))
    with pytest.raises(FacetError):
        reg.validate(_node(extra={"x": 1}))


def test_optional_facet_allowed():
    reg = Registry()
    reg.register(KindSpec(name="topic", optional_facets={"summary"}))
    reg.validate(_node(summary={"text": "hi"}))  # no raise


def test_invariant_runs():
    def must_have_title_a(node: Node) -> None:
        if node.title != "A":
            raise InvariantError("title must be A")

    reg = Registry()
    reg.register(KindSpec(name="topic", invariants=[must_have_title_a]))
    reg.validate(_node())  # passes
    with pytest.raises(InvariantError):
        reg.validate(Node(id="topic:b", kind="topic", title="B"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.registry'`.

- [ ] **Step 3: Write minimal implementation**

`src/nodes/kernel/registry.py`:
```python
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from nodes.kernel.errors import FacetError, UnknownKindError
from nodes.kernel.node import Node

Invariant = Callable[[Node], None]


class KindSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    required_facets: set[str] = Field(default_factory=set)
    optional_facets: set[str] = Field(default_factory=set)
    invariants: list[Invariant] = Field(default_factory=list)


class Registry:
    def __init__(self) -> None:
        self._specs: dict[str, KindSpec] = {}

    def register(self, spec: KindSpec) -> None:
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
        present = set(node.facets)
        missing = spec.required_facets - present
        if missing:
            raise FacetError(f"{node.id}: missing required facets {sorted(missing)}")
        allowed = spec.required_facets | spec.optional_facets
        unexpected = present - allowed
        if unexpected:
            raise FacetError(f"{node.id}: unexpected facets {sorted(unexpected)}")
        for invariant in spec.invariants:
            invariant(node)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_registry.py -v`
Expected: PASS (5 cases).

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/registry.py tests/test_registry.py
git commit -m "feat(kernel): kind registry + facet/invariant validation"
```

---

### Task 6: Structural shapes (Membership facet + built-in shape kinds)

**Files:**
- Create: `src/nodes/kernel/shapes.py`
- Test: `tests/test_shapes.py`

**Interfaces:**
- Consumes: `Node` from `nodes.kernel.node`; `Relation` from `nodes.kernel.relations`; `Registry`, `KindSpec` from `nodes.kernel.registry`; `InvariantError`, `FacetError` from `nodes.kernel.errors`.
- Produces:
  - `MEMBERSHIP = "membership"` (the facet key).
  - `class Membership(BaseModel)`: `shape: str`, `members: list[str] | dict[str, str] = []`, `edges: list[Relation] = []`.
  - `def membership_of(node: Node) -> Membership` — builds a `Membership` from `node.facets[MEMBERSHIP]` (raises `FacetError` if absent).
  - Invariant functions `require_unique_members(node)`, `require_dict_keys(node)`, `require_acyclic(node)`, `require_single_parent(node)` (each raises `InvariantError`).
  - `def register_builtin_shapes(reg: Registry) -> None` — registers kinds `set`, `list`, `dict`, `graph`, `dag`, `tree`, each requiring the `membership` facet with the appropriate invariants.

- [ ] **Step 1: Write the failing test**

`tests/test_shapes.py`:
```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import InvariantError
from nodes.kernel.node import Node
from nodes.kernel.registry import Registry
from nodes.kernel.shapes import MEMBERSHIP, register_builtin_shapes


def _struct(kind: str, membership: dict) -> Node:
    return Node(id=f"{kind}:s", kind=kind, title="S", facets={MEMBERSHIP: membership})


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    register_builtin_shapes(r)
    return r


def test_set_rejects_duplicates(reg):
    reg.validate(_struct("set", {"shape": "set", "members": ["a:1", "a:2"]}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("set", {"shape": "set", "members": ["a:1", "a:1"]}))


def test_list_allows_duplicates(reg):
    reg.validate(_struct("list", {"shape": "list", "members": ["a:1", "a:1"]}))  # no raise


def test_dict_requires_mapping(reg):
    reg.validate(_struct("dict", {"shape": "dict", "members": {"k": "a:1"}}))
    with pytest.raises(InvariantError):
        reg.validate(_struct("dict", {"shape": "dict", "members": ["a:1"]}))


def test_dag_rejects_cycle(reg):
    acyclic = {"shape": "dag", "members": ["a:1", "a:2"],
               "edges": [{"source": "a:1", "predicate": "to", "target": "a:2"}]}
    reg.validate(_struct("dag", acyclic))
    cyclic = {"shape": "dag", "members": ["a:1", "a:2"],
              "edges": [{"source": "a:1", "predicate": "to", "target": "a:2"},
                        {"source": "a:2", "predicate": "to", "target": "a:1"}]}
    with pytest.raises(InvariantError):
        reg.validate(_struct("dag", cyclic))


def test_tree_rejects_multiple_parents(reg):
    multi = {"shape": "tree", "members": ["a:1", "a:2", "a:3"],
             "edges": [{"source": "a:1", "predicate": "to", "target": "a:3"},
                       {"source": "a:2", "predicate": "to", "target": "a:3"}]}
    with pytest.raises(InvariantError):
        reg.validate(_struct("tree", multi))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_shapes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.shapes'`.

- [ ] **Step 3: Write minimal implementation**

`src/nodes/kernel/shapes.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, Field

from nodes.kernel.errors import FacetError, InvariantError
from nodes.kernel.node import Node
from nodes.kernel.registry import KindSpec, Registry
from nodes.kernel.relations import Relation

MEMBERSHIP = "membership"


class Membership(BaseModel):
    shape: str
    members: list[str] | dict[str, str] = Field(default_factory=list)
    edges: list[Relation] = Field(default_factory=list)


def membership_of(node: Node) -> Membership:
    raw = node.facets.get(MEMBERSHIP)
    if raw is None:
        raise FacetError(f"{node.id}: missing '{MEMBERSHIP}' facet")
    return Membership.model_validate(raw)


def _member_ids(m: Membership) -> list[str]:
    return list(m.members.values()) if isinstance(m.members, dict) else list(m.members)


def require_unique_members(node: Node) -> None:
    ids = _member_ids(membership_of(node))
    if len(ids) != len(set(ids)):
        raise InvariantError(f"{node.id}: members must be unique")


def require_dict_keys(node: Node) -> None:
    if not isinstance(membership_of(node).members, dict):
        raise InvariantError(f"{node.id}: dict shape requires a key->ref mapping")


def require_acyclic(node: Node) -> None:
    m = membership_of(node)
    adj: dict[str, list[str]] = {}
    for e in m.edges:
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
    for e in membership_of(node).edges:
        parents[e.target] = parents.get(e.target, 0) + 1
    over = [t for t, c in parents.items() if c > 1]
    if over:
        raise InvariantError(f"{node.id}: nodes with multiple parents: {sorted(over)}")


def register_builtin_shapes(reg: Registry) -> None:
    reg.register(KindSpec(name="set", required_facets={MEMBERSHIP},
                          invariants=[require_unique_members]))
    reg.register(KindSpec(name="list", required_facets={MEMBERSHIP}))
    reg.register(KindSpec(name="dict", required_facets={MEMBERSHIP},
                          invariants=[require_dict_keys]))
    reg.register(KindSpec(name="graph", required_facets={MEMBERSHIP},
                          invariants=[require_unique_members]))
    reg.register(KindSpec(name="dag", required_facets={MEMBERSHIP},
                          invariants=[require_unique_members, require_acyclic]))
    reg.register(KindSpec(name="tree", required_facets={MEMBERSHIP},
                          invariants=[require_unique_members, require_acyclic, require_single_parent]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_shapes.py -v`
Expected: PASS (5 cases).

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/shapes.py tests/test_shapes.py
git commit -m "feat(kernel): structural shapes + membership facet + invariants"
```

---

### Task 7: Frontmatter parse/serialize

**Files:**
- Create: `src/nodes/kernel/frontmatter.py`
- Test: `tests/test_frontmatter.py`

**Interfaces:**
- Consumes: `Node`, `NodeMetadata` from `nodes.kernel.node`; `Relation`, `RELATES_TO`, `relates_to` from `nodes.kernel.relations`.
- Produces:
  - `def split_frontmatter(text: str) -> tuple[dict, str]` — returns `(frontmatter_dict, body)`; `({}, text)` when no frontmatter.
  - `def node_from_markdown(text: str) -> Node` — builds a `Node`; top-level `created`/`updated`/`version` populate `NodeMetadata`; `related:` entries become `relatesTo` relations sourced at the node id; `relations:` entries are deserialized via `Relation.from_serialized(..., container_id=node_id)`.
  - `def node_to_markdown(node: Node) -> str` — emits top-level fields, splits relations into `related:` (bare `relatesTo` with no extras) vs `relations:` (everything else, via `to_serialized`), then `facets:`, then the body. Plain-`relatesTo` relations are NOT duplicated into `relations:`.

- [ ] **Step 1: Write the failing test**

`tests/test_frontmatter.py`:
```python
from __future__ import annotations

from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown, split_frontmatter
from nodes.kernel.node import Node
from nodes.kernel.relations import Relation, relates_to


def test_split_no_frontmatter():
    fm, body = split_frontmatter("just text")
    assert fm == {} and body == "just text"


def test_parse_related_and_relations():
    text = (
        "---\n"
        "id: gene:PHF19\n"
        "uid: deadbeefdeadbeefdeadbeefdeadbeef\n"
        "kind: gene\n"
        "title: PHF19\n"
        "related: [topic:polycomb]\n"
        "relations:\n"
        "  - { predicate: interacts_with, target: gene:EZH2 }\n"
        "---\n"
        "PHF19 body.\n"
    )
    n = node_from_markdown(text)
    assert n.id == "gene:PHF19" and n.uid == "deadbeefdeadbeefdeadbeefdeadbeef"
    assert relates_to("gene:PHF19", "topic:polycomb") in n.relations
    assert Relation(source="gene:PHF19", predicate="interacts_with", target="gene:EZH2") in n.relations
    assert n.body == "PHF19 body.\n"


def test_body_preserves_whitespace_below_frontmatter():
    text = (
        "---\n"
        "id: topic:a\n"
        "uid: deadbeefdeadbeefdeadbeefdeadbeef\n"
        "kind: topic\n"
        "title: A\n"
        "---\n"
        "\n"
        "First paragraph.\n"
        "\n"
    )
    n = node_from_markdown(text)
    assert n.body == "\nFirst paragraph.\n\n"
    assert node_from_markdown(node_to_markdown(n)).body == n.body


def test_roundtrip_preserves_relations_and_facets():
    n = Node(
        id="gene:PHF19", kind="gene", title="PHF19",
        uid="deadbeefdeadbeefdeadbeefdeadbeef",
        relations=[
            relates_to("gene:PHF19", "topic:polycomb"),
            Relation(source="gene:PHF19", predicate="interacts_with", target="gene:EZH2"),
        ],
        facets={"bio-axes": {"primary_external_id": "HGNC:7296"}},
        body="PHF19 body.",
    )
    reparsed = node_from_markdown(node_to_markdown(n))
    assert reparsed.id == n.id
    assert reparsed.facets == n.facets
    assert set((r.predicate, r.target) for r in reparsed.relations) == \
        set((r.predicate, r.target) for r in n.relations)


def test_plain_relatesto_serializes_into_related_only():
    n = Node(id="topic:a", kind="topic", title="A",
             relations=[relates_to("topic:a", "topic:b")])
    md = node_to_markdown(n)
    assert "related:" in md
    assert "relations:" not in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_frontmatter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.frontmatter'`.

- [ ] **Step 3: Write minimal implementation**

`src/nodes/kernel/frontmatter.py`:
```python
from __future__ import annotations

from typing import Any

import yaml

from nodes.kernel.node import Node, NodeMetadata
from nodes.kernel.relations import RELATES_TO, Relation, relates_to


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2]
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    return fm, body


def node_from_markdown(text: str) -> Node:
    fm, body = split_frontmatter(text)
    node_id = fm["id"]
    relations: list[Relation] = []
    for ref in fm.get("related", []) or []:
        relations.append(relates_to(node_id, ref))
    for raw in fm.get("relations", []) or []:
        relations.append(Relation.from_serialized(raw, container_id=node_id))
    meta = NodeMetadata.model_validate({k: fm[k] for k in ("created", "updated", "version") if k in fm})
    return Node(
        id=node_id,
        uid=fm["uid"],
        kind=fm["kind"],
        title=fm["title"],
        body=body,
        metadata=meta,
        relations=relations,
        facets=fm.get("facets", {}) or {},
        deprecated_ids=fm.get("deprecated_ids", []) or [],
    )


def _is_plain_relatesto(rel: Relation, node_id: str) -> bool:
    return (
        rel.predicate == RELATES_TO
        and rel.source == node_id
        and rel.directed is True
        and rel.weight is None
        and not rel.attrs
    )


def node_to_markdown(node: Node) -> str:
    fm: dict[str, Any] = {"id": node.id, "uid": node.uid, "kind": node.kind, "title": node.title}
    if node.metadata.created is not None:
        fm["created"] = node.metadata.created
    if node.metadata.updated is not None:
        fm["updated"] = node.metadata.updated
    if node.metadata.version != 1:
        fm["version"] = node.metadata.version
    related = [r.target for r in node.relations if _is_plain_relatesto(r, node.id)]
    typed = [r.to_serialized(node.id) for r in node.relations if not _is_plain_relatesto(r, node.id)]
    if related:
        fm["related"] = related
    if typed:
        fm["relations"] = typed
    if node.facets:
        fm["facets"] = node.facets
    if node.deprecated_ids:
        fm["deprecated_ids"] = node.deprecated_ids
    yaml_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{yaml_text}\n---\n{node.body}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_frontmatter.py -v`
Expected: PASS (5 cases).

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/frontmatter.py tests/test_frontmatter.py
git commit -m "feat(kernel): markdown frontmatter parse/serialize with source-implied relations"
```

---

### Task 8: File store — CRUD, collision, rename

**Files:**
- Create: `src/nodes/kernel/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Node` from `nodes.kernel.node`; `node_from_markdown`, `node_to_markdown` from `nodes.kernel.frontmatter`; `NodeId` from `nodes.kernel.ids`; `MEMBERSHIP` from `nodes.kernel.shapes`; `CollisionError`, `RefError` from `nodes.kernel.errors`.
- Produces:
  - `class Store`: constructed with `Store(root: Path)`.
    - `path_for(node_id: str) -> Path` → `root/<kind>/<slug>.md` (slug colons → `__`).
    - `write(node: Node) -> Path` — refuses to create a file whose identity claims collide with another node: duplicate live id, duplicate active `deprecated_id`, live-vs-deprecated overlap, or duplicate `uid` under a different live id (`CollisionError`); overwriting the same live id + uid is allowed.
    - `resolve(ref: str) -> Node` — resolves a ref by live id (direct file path) or active `deprecated_id` (linear scan); raises `RefError` if nothing resolves (spec §3.5).
    - `read(node_id: str) -> Node` — delegates to `resolve`, so stale ids still resolve after a rename.
    - `delete(node_id: str) -> None`.
    - `all_nodes() -> list[Node]`.
    - `rename(old_id: str, new_id: str) -> Node` — moves the file, sets new `id`, appends `old_id` to `deprecated_ids`, rewrites every inbound ref across the corpus from `old_id` to `new_id` — covering both `related`/`relations` AND the `membership` facet (members + edges) of structure nodes, since those are canonical file refs; `uid` unchanged.

- [ ] **Step 1: Write the failing test**

`tests/test_store.py`:
```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import CollisionError, RefError
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to
from nodes.kernel.store import Store


def test_write_read_roundtrip(tmp_path):
    store = Store(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A", body="hi")
    store.write(n)
    got = store.read("topic:a")
    assert got.title == "A" and got.body == "hi" and got.uid == n.uid


def test_collision_on_new_id(tmp_path):
    store = Store(tmp_path)
    store.write(Node(id="topic:a", kind="topic", title="A"))
    with pytest.raises(CollisionError):
        store.write(Node(id="topic:a", kind="topic", title="Other"))  # different uid, same id


def test_collision_on_duplicate_uid_at_different_id(tmp_path):
    store = Store(tmp_path)
    original = Node(id="topic:a", kind="topic", title="A")
    store.write(original)
    with pytest.raises(CollisionError):
        store.write(Node(id="topic:b", kind="topic", title="B", uid=original.uid))


def test_collision_on_deprecated_id_claim(tmp_path):
    store = Store(tmp_path)
    store.write(Node(id="topic:a", kind="topic", title="A"))
    with pytest.raises(CollisionError):
        store.write(Node(id="topic:b", kind="topic", title="B", deprecated_ids=["topic:a"]))


def test_overwrite_same_uid_ok(tmp_path):
    store = Store(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A")
    store.write(n)
    n.title = "A2"
    store.write(n)  # same uid → allowed
    assert store.read("topic:a").title == "A2"


def test_read_missing_raises(tmp_path):
    with pytest.raises(RefError):
        Store(tmp_path).read("topic:ghost")


def test_rename_rewrites_inbound_refs(tmp_path):
    store = Store(tmp_path)
    store.write(Node(id="topic:old", kind="topic", title="Old"))
    store.write(Node(id="topic:b", kind="topic", title="B",
                     relations=[relates_to("topic:b", "topic:old")]))
    renamed = store.rename("topic:old", "topic:new")
    assert renamed.id == "topic:new"
    assert "topic:old" in renamed.deprecated_ids
    b = store.read("topic:b")
    assert relates_to("topic:b", "topic:new") in b.relations
    assert all(r.target != "topic:old" for r in b.relations)


def test_resolve_old_id_after_rename(tmp_path):
    store = Store(tmp_path)
    store.write(Node(id="topic:old", kind="topic", title="Old"))
    store.rename("topic:old", "topic:new")
    assert store.resolve("topic:old").id == "topic:new"
    assert store.read("topic:old").id == "topic:new"  # stale ref survives


def test_rename_rewrites_membership_refs(tmp_path):
    store = Store(tmp_path)
    store.write(Node(id="topic:old", kind="topic", title="Old"))
    store.write(Node(id="topic:x", kind="topic", title="X"))
    store.write(Node(id="graph:g", kind="graph", title="G", facets={"membership": {
        "shape": "graph",
        "members": ["topic:old", "topic:x"],
        "edges": [{"source": "topic:old", "predicate": "to", "target": "topic:x"}],
    }}))
    store.rename("topic:old", "topic:new")
    mem = store.read("graph:g").facets["membership"]
    assert "topic:new" in mem["members"] and "topic:old" not in mem["members"]
    assert mem["edges"][0]["source"] == "topic:new"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.store'`.

- [ ] **Step 3: Write minimal implementation**

`src/nodes/kernel/store.py`:
```python
from __future__ import annotations

from pathlib import Path

from nodes.kernel.errors import CollisionError, RefError
from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown
from nodes.kernel.ids import NodeId
from nodes.kernel.node import Node
from nodes.kernel.shapes import MEMBERSHIP


class Store:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, node_id: str) -> Path:
        nid = NodeId.parse(node_id)
        return self.root / nid.kind / f"{nid.slug.replace(':', '__')}.md"

    def all_nodes(self) -> list[Node]:
        return [node_from_markdown(p.read_text(encoding="utf-8")) for p in sorted(self.root.rglob("*.md"))]

    def _id_owner_uid(self, node_id: str) -> str | None:
        for n in self.all_nodes():
            if n.id == node_id or node_id in n.deprecated_ids:
                return n.uid
        return None

    @staticmethod
    def _claimed_ids(node: Node) -> set[str]:
        return {node.id, *node.deprecated_ids}

    def _assert_no_identity_collision(self, node: Node) -> None:
        claimed = self._claimed_ids(node)
        for existing in self.all_nodes():
            same_live_identity = existing.id == node.id and existing.uid == node.uid
            if existing.uid == node.uid and existing.id != node.id:
                raise CollisionError(
                    f"uid {node.uid!r} already belongs to live id {existing.id!r}; use rename()"
                )
            if same_live_identity:
                continue
            overlap = claimed & self._claimed_ids(existing)
            if overlap:
                raise CollisionError(f"identity claims already in use: {sorted(overlap)}")

    def write(self, node: Node) -> Path:
        self._assert_no_identity_collision(node)
        path = self.path_for(node.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(node_to_markdown(node), encoding="utf-8")
        return path

    def resolve(self, ref: str) -> Node:
        """Resolve a ref by live id (file path) or active deprecated id (spec §3.5)."""
        path = self.path_for(ref)
        if path.is_file():
            return node_from_markdown(path.read_text(encoding="utf-8"))
        for n in self.all_nodes():
            if ref in n.deprecated_ids:
                return n
        raise RefError(f"no node resolves ref {ref!r}")

    def read(self, node_id: str) -> Node:
        return self.resolve(node_id)

    def delete(self, node_id: str) -> None:
        path = self.path_for(node_id)
        if not path.is_file():
            raise RefError(f"no node at {node_id!r}")
        path.unlink()

    def rename(self, old_id: str, new_id: str) -> Node:
        if self._id_owner_uid(new_id) is not None:
            raise CollisionError(f"target id {new_id!r} already in use")
        node = self.read(old_id)
        self.delete(old_id)
        node.id = new_id
        node.kind = NodeId.parse(new_id).kind
        if old_id not in node.deprecated_ids:
            node.deprecated_ids.append(old_id)
        self.write(node)
        self._rewrite_inbound(old_id, new_id)
        return node

    def _rewrite_inbound(self, old_id: str, new_id: str) -> None:
        for other in self.all_nodes():
            if other.id == new_id:
                continue
            changed = self._rewrite_relations(other, old_id, new_id)
            changed = self._rewrite_membership(other, old_id, new_id) or changed
            if changed:
                self.write(other)

    @staticmethod
    def _rewrite_relations(node: Node, old_id: str, new_id: str) -> bool:
        changed = False
        for rel in node.relations:
            if rel.target == old_id:
                rel.target = new_id
                changed = True
            if rel.source == old_id:
                rel.source = new_id
                changed = True
        return changed

    @staticmethod
    def _rewrite_membership(node: Node, old_id: str, new_id: str) -> bool:
        mem = node.facets.get(MEMBERSHIP)
        if not isinstance(mem, dict):
            return False
        changed = False
        members = mem.get("members")
        if isinstance(members, list):
            updated = [new_id if m == old_id else m for m in members]
            if updated != members:
                mem["members"] = updated
                changed = True
        elif isinstance(members, dict):
            for key, val in list(members.items()):
                if val == old_id:
                    members[key] = new_id
                    changed = True
        for edge in mem.get("edges", []) or []:
            if edge.get("source") == old_id:
                edge["source"] = new_id
                changed = True
            if edge.get("target") == old_id:
                edge["target"] = new_id
                changed = True
        return changed
```

Note: `_rewrite_inbound` rewrites both `related`/`relations` (which live in `node.relations` after parsing) AND the `membership` facet's `members` + `edges` of structure nodes — all are canonical file refs. `resolve()` is a linear scan here; Plan 2's derived index makes it O(1).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS (9 cases).

- [ ] **Step 5: Commit**

```bash
git add src/nodes/kernel/store.py tests/test_store.py
git commit -m "feat(kernel): file store with CRUD, collision detection, rename"
```

---

### Task 9: On-disk format reference + full-suite gate

**Files:**
- Create: `~/d/nodes/docs/format.md`
- Create: `tests/test_format_golden.py`
- Create: `tests/fixtures/gene_phf19.md`

**Interfaces:**
- Consumes: `node_from_markdown`, `node_to_markdown` from `nodes.kernel.frontmatter`.
- Produces: the canonical format reference doc + a golden round-trip test asserting the documented example parses and re-serializes stably.

- [ ] **Step 1: Write the fixture**

`tests/fixtures/gene_phf19.md`:
```markdown
---
id: gene:PHF19
uid: 7b2cdeadbeef7b2cdeadbeef7b2cdeef
kind: gene
title: PHF19
related:
- topic:polycomb
relations:
- predicate: interacts_with
  target: gene:EZH2
facets:
  bio-axes:
    primary_external_id: HGNC:7296
---
PHF19 is a PRC2-associated component.
```

- [ ] **Step 2: Write the failing test**

`tests/test_format_golden.py`:
```python
from __future__ import annotations

from pathlib import Path

from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown

FIXTURE = Path(__file__).parent / "fixtures" / "gene_phf19.md"


def test_golden_fixture_parses():
    n = node_from_markdown(FIXTURE.read_text(encoding="utf-8"))
    assert n.id == "gene:PHF19"
    assert n.kind == "gene"
    assert n.facets["bio-axes"]["primary_external_id"] == "HGNC:7296"
    targets = {r.target for r in n.relations}
    assert {"topic:polycomb", "gene:EZH2"} <= targets


def test_serialize_is_idempotent():
    n = node_from_markdown(FIXTURE.read_text(encoding="utf-8"))
    once = node_to_markdown(n)
    twice = node_to_markdown(node_from_markdown(once))
    assert once == twice
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_format_golden.py -v`
Expected: FAIL — fixture missing or assertion error until the fixture + parser align.

- [ ] **Step 4: Write the format reference doc**

`~/d/nodes/docs/format.md`:
```markdown
# nodes — on-disk format (kernel)

One file per node: YAML frontmatter + markdown body. Files are canonical (git-versioned).

## Top-level frontmatter fields
- `id` (required): canonical `kind:slug`. Stored + display ref form.
- `uid` (required): immutable UUID (hex). Identity anchor; survives renames.
- `kind` (required): must equal the `id`'s kind segment.
- `title` (required).
- `created`, `updated` (optional): ISO dates, top-level.
- `version` (optional): integer, top-level, default 1 (omitted when default).
- `related` (optional): list of target ids — sugar for `relatesTo` relations sourced at this node.
- `relations` (optional): typed relations; `source` omitted (implied = this node).
- `facets` (optional): nested map, keyed by facet name.
- `deprecated_ids` (optional): previous ids retained after rename for ref resolution.

## Relations
Normalized form: `{source, predicate, target, directed?, weight?, attrs?}`.
- Node-relation (in `related`/`relations`): `source` implied = containing node.
- Graph edge (in a structure's `membership.edges`): both `source` and `target` explicit.

## Structures
A structure node carries a `membership` facet: `{shape, members, edges?}`.
Shapes: `set`, `list`, `dict`, `graph`, `dag`, `tree` (invariants per spec §3.4).

## Known kernel limitations (resolved in later plans)
- No derived search/graph index yet (Plan 2): full-text, resolved relation graph, embeddings.
  Kernel `resolve()` / collision checks do linear scans; the index makes lookups O(1).
```

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS — all tests across tasks 1–9 green.

- [ ] **Step 6: Lint + type-check**

Run: `uv run ruff check src tests` then `uv run pyright src` (if pyright available; otherwise skip).
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add docs/format.md tests/test_format_golden.py tests/fixtures/gene_phf19.md
git commit -m "docs(kernel): on-disk format reference + golden round-trip test"
```

---

## Self-Review

**Spec coverage:**
- §2 layering (`nodes.kernel` subpackage, reserved vocab/domain) → Task 1.
- §3.1 Node (id/uid/kind/title/body/metadata/relations/facets; `related` is on-disk sugar, not a stored field) → Task 4.
- §3.2 Relation primitive + normalized/serialized forms + tag/related sugar → Task 3; serialize split → Task 7.
- §3.3 facets + registry + invariants → Task 5.
- §3.4 structural shapes + membership facet + invariants → Task 6.
- §3.5 identity/rename contract (stored=id, uid anchor, `resolve()` via deprecated_ids, ref rewrite incl. membership, collisions) → Tasks 2, 4, 8.
- §4 on-disk format (nested facets, top-level created/updated/version, source-implied) → Tasks 7, 9.
- §5 derived index → **out of scope (Plan 2)**, flagged in `format.md`.
- §6 Python lib (CRUD) → Tasks 4–8; TS port out of scope.
- §10 `uid` backfill → **out of scope (science-migration plan)**; kernel mints uuid4 for new nodes (Task 4).

**Placeholder scan:** none — every code/test step shows complete content.

**Type consistency:** `Node`, `Relation`, `Membership`, `Registry`, `KindSpec`, `Store` signatures match across Interfaces blocks and usage. `node.relations` holds the merged related+typed relations everywhere (Tasks 4, 7, 8). `MEMBERSHIP` facet key consistent (Tasks 6, 9).

**Known deferrals (intentional, flagged in `docs/format.md`):** derived index (incl. O(1) ref resolution); TS port; `uid` backfill migration. Membership-edge rewrite on rename is **in scope** and implemented in Task 8.
