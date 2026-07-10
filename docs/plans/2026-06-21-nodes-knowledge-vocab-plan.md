# Knowledge Vocab Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `nodes.vocab` — a separately-importable profile of seven knowledge kinds on the domain-free kernel — and wire the kernel's `Registry` into the `Corpus` write path so the vocabulary is enforced fail-early.

**Architecture:** A new `src/nodes/vocab/` package (depends only on `nodes.kernel`, never the reverse) with three modules — `source.py` (the shared bibliographic facet), `kinds.py` (kind constants + `register_knowledge_vocab`), `predicates.py` (canonical predicate names + helpers) — plus one kernel change: `Corpus` gains an optional `registry` that validates on `add` and `rename`.

**Tech Stack:** Python ≥3.11, Pydantic v2, pytest, ruff (line-length 120), pyright (basic), `uv` runner, src/ layout.

## Current State Note

This plan has since been implemented and remains useful as the historical Plan-3 rollout for the Python `nodes.vocab` layer and registry-backed `Corpus` validation. The layering contract is still current: `nodes.vocab` imports from `nodes.kernel`, the kernel never imports `nodes.vocab`, and a caller opts into vocabulary enforcement by passing a registered `Registry` to `Corpus`.

The repo and kernel have grown since this checklist was written:

- Python now lives under `~/d/nodes/python/`. Historical paths like `src/nodes/vocab/...`, `src/nodes/kernel/...`, and `tests/...` mean `python/src/nodes/vocab/...`, `python/src/nodes/kernel/...`, and `python/tests/...` in the current checkout.
- Current `Corpus` is `Corpus(root, registry=None, embedder=None)`. Registry validation still runs before disk writes on `add` and before any rename writes, but the current rename path also prepares and commits full-text search, optional similarity vectors, and the live snapshot manifest.
- The `docs/STANDARD.md` appendix from Task 6 is already integrated and has since been extended with TypeScript parity, full-text search, similarity, and index-persistence sections. Do not append the historical snippet below again.
- Current shell commands should use the repository's `rtk` wrapper. From `~/d/nodes/python`, run Python gates with `rtk uv run --frozen pytest`, `rtk uv run --frozen ruff check .`, and `rtk uv run --frozen pyright src`.

Treat code snippets below as the original greenfield implementation sequence, not as replacement code for current `corpus.py`, `vocab/`, tests, or `docs/STANDARD.md`.

## Global Constraints

- Every module starts with `from __future__ import annotations`.
- `nodes.vocab` imports only from `nodes.kernel` (+ stdlib + pydantic). The kernel never imports `nodes.vocab`.
- All errors surface through the kernel hierarchy (`nodes.kernel.errors`): `FacetError`, `InvariantError`, `UnknownKindError`. No new error types. A raw Pydantic `ValidationError` must never escape `source_of`.
- `Source` uses `ConfigDict(extra="forbid")` — unknown keys fail, never silently dropped.
- The roster is exactly seven kinds: prose `note`, `idea`, `question`, `topic` (bare); source `paper`, `book`, `dataset` (require the `source` facet + `require_identifiable_source`).
- `Corpus(registry=None)` preserves today's behavior exactly — the existing 86-test suite stays green.
- Predicate constants and values: `ABOUT="about"`, `CITES="cites"`, `ANSWERS="answers"`, `ASKS="asks"`, `REFINES="refines"`.
- Historical gates below assume the old root Python package. Current gates should run from `python/` with `rtk uv run --frozen ...`.

---

### Task 1: `Source` facet

Historical path note: this checklist predates the repo split. In the current checkout, prefix Python implementation and test paths with `python/`.

**Files:**
- Create: `src/nodes/vocab/__init__.py` (empty package marker for now; populated in Task 6)
- Create: `src/nodes/vocab/source.py`
- Test: `tests/test_vocab_source.py`

**Interfaces:**
- Consumes: `nodes.kernel.errors.{FacetError, InvariantError}`, `nodes.kernel.node.Node`.
- Produces: `SOURCE: str = "source"`; `Source` (Pydantic model, fields `authors: list[str]`, `year: int | None`, `container: str | None`, `identifier: str | None`, `url: str | None`); `source_of(node) -> Source` (raises `FacetError` on missing/malformed); `require_identifiable_source(node) -> None` (raises `InvariantError` on empty source). Used by Task 2.

- [ ] **Step 1: Create the empty package marker**

Create `src/nodes/vocab/__init__.py` with exactly:

```python
from __future__ import annotations
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_vocab_source.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import FacetError, InvariantError
from nodes.kernel.node import Node
from nodes.vocab.source import SOURCE, Source, require_identifiable_source, source_of


def _paper(source: dict | None) -> Node:
    facets = {} if source is None else {SOURCE: source}
    return Node(id="paper:x", kind="paper", title="X", facets=facets)


def test_source_defaults():
    s = Source()
    assert s.authors == []
    assert s.year is None and s.container is None and s.identifier is None and s.url is None


def test_source_of_missing_facet_raises():
    with pytest.raises(FacetError):
        source_of(_paper(None))


def test_source_of_unknown_key_raises_facet_error():
    with pytest.raises(FacetError):
        source_of(_paper({"identifer": "10.1/x"}))  # typo: identifer


def test_source_of_wrong_type_raises_facet_error():
    with pytest.raises(FacetError):
        source_of(_paper({"year": "soon"}))


def test_require_identifiable_source_rejects_empty():
    with pytest.raises(InvariantError):
        require_identifiable_source(_paper({}))


def test_require_identifiable_source_accepts_one_field():
    require_identifiable_source(_paper({"year": 2026}))  # no raise


def test_source_roundtrips_through_facets():
    node = _paper({"authors": ["A. Author"], "year": 2026, "identifier": "10.1/x"})
    s = source_of(node)
    assert s.authors == ["A. Author"] and s.year == 2026 and s.identifier == "10.1/x"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_vocab_source.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.vocab.source'`.

- [ ] **Step 4: Write the implementation**

Create `src/nodes/vocab/source.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from nodes.kernel.errors import FacetError, InvariantError
from nodes.kernel.node import Node

SOURCE = "source"


class Source(BaseModel):
    """Shared bibliographic facet for paper / book / dataset kinds."""

    model_config = ConfigDict(extra="forbid")  # unknown keys (typos) fail, never silently dropped

    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    container: str | None = None   # journal / publisher / repository
    identifier: str | None = None  # DOI / ISBN / accession id
    url: str | None = None


def source_of(node: Node) -> Source:
    raw = node.facets.get(SOURCE)
    if raw is None:
        raise FacetError(f"{node.id}: missing '{SOURCE}' facet")
    try:
        return Source.model_validate(raw)
    except PydanticValidationError as exc:  # malformed payload / unknown key / wrong type
        raise FacetError(f"{node.id}: invalid '{SOURCE}' facet: {exc}") from exc


def require_identifiable_source(node: Node) -> None:
    s = source_of(node)
    if not (s.authors or s.year or s.identifier or s.url):
        raise InvariantError(
            f"{node.id}: source facet needs at least one of authors/year/identifier/url"
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_vocab_source.py -q`
Expected: PASS (7 tests).

- [ ] **Step 6: Run gates and commit**

```bash
rtk uv run ruff check src tests
rtk uv run pyright src
rtk git add src/nodes/vocab/__init__.py src/nodes/vocab/source.py tests/test_vocab_source.py
rtk git commit -m "feat(vocab): Source bibliographic facet with fail-early validation"
```

---

### Task 2: Kinds + `register_knowledge_vocab`

**Files:**
- Create: `src/nodes/vocab/kinds.py`
- Test: `tests/test_vocab_kinds.py`

**Interfaces:**
- Consumes: `nodes.kernel.registry.{KindSpec, Registry}`; `nodes.vocab.source.{SOURCE, require_identifiable_source}` (Task 1).
- Produces: kind constants `NOTE, IDEA, QUESTION, TOPIC, PAPER, BOOK, DATASET`; groups `PROSE_KINDS`, `SOURCE_KINDS`; `register_knowledge_vocab(reg: Registry) -> None`. Used by Tasks 4–6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_vocab_kinds.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import FacetError, InvariantError, UnknownKindError
from nodes.kernel.node import Node
from nodes.kernel.registry import Registry
from nodes.vocab.kinds import PROSE_KINDS, SOURCE_KINDS, register_knowledge_vocab
from nodes.vocab.source import SOURCE


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    register_knowledge_vocab(r)
    return r


def test_all_kinds_registered(reg):
    for name in PROSE_KINDS + SOURCE_KINDS:
        assert reg.is_registered(name)


def test_bare_note_validates(reg):
    reg.validate(Node(id="note:a", kind="note", title="A"))  # no raise


def test_note_with_stray_facet_raises(reg):
    with pytest.raises(FacetError):
        reg.validate(Node(id="note:a", kind="note", title="A", facets={SOURCE: {"year": 2026}}))


def test_paper_missing_source_raises(reg):
    with pytest.raises(FacetError):
        reg.validate(Node(id="paper:a", kind="paper", title="A"))


def test_paper_empty_source_raises(reg):
    with pytest.raises(InvariantError):
        reg.validate(Node(id="paper:a", kind="paper", title="A", facets={SOURCE: {}}))


def test_paper_valid_source_passes(reg):
    reg.validate(Node(id="paper:a", kind="paper", title="A", facets={SOURCE: {"year": 2026}}))


def test_book_and_dataset_share_source_invariant(reg):
    for kind in ("book", "dataset"):
        with pytest.raises(InvariantError):
            reg.validate(Node(id=f"{kind}:a", kind=kind, title="A", facets={SOURCE: {}}))
        reg.validate(Node(id=f"{kind}:b", kind=kind, title="B", facets={SOURCE: {"identifier": "x"}}))


def test_unregistered_kind_raises():
    reg = Registry()  # empty
    with pytest.raises(UnknownKindError):
        reg.validate(Node(id="note:a", kind="note", title="A"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_vocab_kinds.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.vocab.kinds'`.

- [ ] **Step 3: Write the implementation**

Create `src/nodes/vocab/kinds.py`:

```python
from __future__ import annotations

from nodes.kernel.registry import KindSpec, Registry
from nodes.vocab.source import SOURCE, require_identifiable_source

NOTE = "note"
IDEA = "idea"
QUESTION = "question"
TOPIC = "topic"
PAPER = "paper"
BOOK = "book"
DATASET = "dataset"

PROSE_KINDS = (NOTE, IDEA, QUESTION, TOPIC)
SOURCE_KINDS = (PAPER, BOOK, DATASET)


def register_knowledge_vocab(reg: Registry) -> None:
    """Register the standard knowledge-vocab kinds onto `reg`.

    Mirrors `nodes.kernel.shapes.register_builtin_shapes`.
    """
    for name in PROSE_KINDS:
        reg.register(KindSpec(name=name))
    for name in SOURCE_KINDS:
        reg.register(
            KindSpec(
                name=name,
                required_facets={SOURCE},
                invariants=[require_identifiable_source],
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_vocab_kinds.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Run gates and commit**

```bash
rtk uv run ruff check src tests
rtk uv run pyright src
rtk git add src/nodes/vocab/kinds.py tests/test_vocab_kinds.py
rtk git commit -m "feat(vocab): seven-kind knowledge roster + register_knowledge_vocab"
```

---

### Task 3: Predicates

**Files:**
- Create: `src/nodes/vocab/predicates.py`
- Test: `tests/test_vocab_predicates.py`

**Interfaces:**
- Consumes: `nodes.kernel.relations.Relation`.
- Produces: constants `ABOUT, CITES, ANSWERS, ASKS, REFINES`; helpers `about, cites, answers, asks, refines` each `(source: str, target: str) -> Relation`. Re-exported in Task 6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_vocab_predicates.py`:

```python
from __future__ import annotations

from nodes.vocab import predicates as p


def test_constant_values():
    assert p.ABOUT == "about"
    assert p.CITES == "cites"
    assert p.ANSWERS == "answers"
    assert p.ASKS == "asks"
    assert p.REFINES == "refines"


def test_helpers_build_relations():
    cases = [
        (p.about, p.ABOUT),
        (p.cites, p.CITES),
        (p.answers, p.ANSWERS),
        (p.asks, p.ASKS),
        (p.refines, p.REFINES),
    ]
    for fn, predicate in cases:
        rel = fn("note:a", "topic:b")
        assert rel.source == "note:a"
        assert rel.target == "topic:b"
        assert rel.predicate == predicate
        assert rel.directed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_vocab_predicates.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.vocab.predicates'`.

- [ ] **Step 3: Write the implementation**

Create `src/nodes/vocab/predicates.py`:

```python
from __future__ import annotations

from nodes.kernel.relations import Relation

ABOUT = "about"      # any node -> topic
CITES = "cites"      # any node -> paper/book/dataset
ANSWERS = "answers"  # note/idea -> question
ASKS = "asks"        # any node -> question (raises one)
REFINES = "refines"  # any node -> node (builds on / supersedes)


def about(source: str, target: str) -> Relation:
    """`source` is about `target` (a topic)."""
    return Relation(source=source, predicate=ABOUT, target=target)


def cites(source: str, target: str) -> Relation:
    """`source` cites `target` (a paper/book/dataset)."""
    return Relation(source=source, predicate=CITES, target=target)


def answers(source: str, target: str) -> Relation:
    """`source` (a note/idea) answers `target` (a question)."""
    return Relation(source=source, predicate=ANSWERS, target=target)


def asks(source: str, target: str) -> Relation:
    """`source` raises `target` (a question)."""
    return Relation(source=source, predicate=ASKS, target=target)


def refines(source: str, target: str) -> Relation:
    """`source` refines / supersedes `target`."""
    return Relation(source=source, predicate=REFINES, target=target)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_vocab_predicates.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Run gates and commit**

```bash
rtk uv run ruff check src tests
rtk uv run pyright src
rtk git add src/nodes/vocab/predicates.py tests/test_vocab_predicates.py
rtk git commit -m "feat(vocab): canonical relation predicates + helper constructors"
```

---

### Task 4: Wire optional registry into `Corpus.add`

Current-code note: `Corpus.add` still validates a registry-backed node before collision checks and before disk writes. Current code then also prepares similarity vectors when configured, writes the node, updates structural/search/vector indexes, and records the live manifest.

**Files:**
- Modify: `src/nodes/kernel/corpus.py` (imports; `__init__`; `add`)
- Test: `tests/test_corpus_registry.py`

**Interfaces:**
- Consumes: `nodes.kernel.registry.Registry`; `nodes.vocab.kinds.register_knowledge_vocab` (test only).
- Produces: `Corpus(root, registry: Registry | None = None)` with `self.registry`; `add` validates when a registry is present. Relied on by Task 5.

**Context:** `corpus.py` currently builds `Store` + `Index` and `add` does `assert_addable` → `write_file` → `upsert` (see corpus.py:40-48). Registry validation must run **before** `assert_addable` (fail-early, no disk write).

- [ ] **Step 1: Write the failing test**

Create `tests/test_corpus_registry.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import InvariantError, UnknownKindError
from nodes.kernel.node import Node
from nodes.kernel.registry import Registry
from nodes.vocab.kinds import register_knowledge_vocab
from nodes.vocab.source import SOURCE


def _registry() -> Registry:
    r = Registry()
    register_knowledge_vocab(r)
    return r


def test_no_registry_skips_validation(tmp_path):
    c = Corpus(tmp_path)  # no registry — today's behavior
    c.add(Node(id="zzz:a", kind="zzz", title="A"))  # unregistered kind, still allowed
    assert c.get("zzz:a").title == "A"


def test_registry_rejects_unknown_kind_no_file(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    with pytest.raises(UnknownKindError):
        c.add(Node(id="zzz:a", kind="zzz", title="A"))
    assert not (tmp_path / "zzz").exists()


def test_registry_rejects_invalid_paper_no_file(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    with pytest.raises(InvariantError):  # empty source facet
        c.add(Node(id="paper:a", kind="paper", title="A", facets={SOURCE: {}}))
    assert not (tmp_path / "paper").exists()


def test_registry_accepts_valid_node(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    c.add(Node(id="paper:a", kind="paper", title="A", facets={SOURCE: {"year": 2026}}))
    assert c.get("paper:a").title == "A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_corpus_registry.py -q`
Expected: FAIL — `TypeError: Corpus.__init__() got an unexpected keyword argument 'registry'`.

- [ ] **Step 3: Add the `Registry` import**

In `src/nodes/kernel/corpus.py`, add to the imports (after the `from nodes.kernel.node import Node` line):

```python
from nodes.kernel.registry import Registry
```

- [ ] **Step 4: Update the constructor**

Replace the existing `__init__`:

```python
    def __init__(self, root: Path) -> None:
        self.store = Store(root)
        self.index = Index.build(self.store.all_nodes())
```

with:

```python
    def __init__(self, root: Path, registry: Registry | None = None) -> None:
        self.store = Store(root)
        self.registry = registry
        self.index = Index.build(self.store.all_nodes())
```

- [ ] **Step 5: Update `add`**

Replace the existing `add`:

```python
    def add(self, node: Node) -> Node:
        self.index.assert_addable(node)
        self.store.write_file(node)
        self.index.upsert(node)
        return node
```

with:

```python
    def add(self, node: Node) -> Node:
        if self.registry is not None:
            self.registry.validate(node)
        self.index.assert_addable(node)
        self.store.write_file(node)
        self.index.upsert(node)
        return node
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_corpus_registry.py tests/test_corpus.py -q`
Expected: PASS (4 new + existing corpus tests; the no-registry default keeps the old suite green).

- [ ] **Step 7: Run gates and commit**

```bash
rtk uv run pytest -q
rtk uv run ruff check src tests
rtk uv run pyright src
rtk git add src/nodes/kernel/corpus.py tests/test_corpus_registry.py
rtk git commit -m "feat(corpus): optional registry validates on add (fail-early, default None)"
```

---

### Task 5: Validate on `rename` (prepare-all → validate-all → commit-all)

Current-code note: the validate-all-before-write contract from this task is still current. Later plans extended the commit phase so renamed nodes and referrers also refresh `SearchIndex`, optional `VectorIndex`, and manifest entries; the historical replacement method below is incomplete for current `corpus.py`.

**Files:**
- Modify: `src/nodes/kernel/corpus.py` (`rename`)
- Test: `tests/test_corpus_registry.py` (append rename tests)

**Interfaces:**
- Consumes: `self.registry` (Task 4); existing `rename` machinery (`in_refs`, `_rewrite_refs`, `NodeId`, write-new-then-delete-old).
- Produces: a `rename` that validates the renamed node **and every referrer it rewrites** before any write; raises before writing anything on failure (no partial rename).

**Context:** The current `rename` (corpus.py:96-125) reads/rewrites referrers and writes them *after* writing the renamed node, with no validation. Restructure so all rewrites happen in memory, all validations run, and only then do writes occur. Preserve the Plan-2 atomicity (renamed node via write-new-then-delete-old) and O(degree) referrer cost.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_corpus_registry.py`:

```python
from nodes.kernel.errors import FacetError, RefError  # noqa: E402
from nodes.kernel.relations import Relation  # noqa: E402


def test_rename_validates_renamed_node_no_write(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    c.add(Node(id="paper:a", kind="paper", title="A", facets={SOURCE: {"year": 2026}}))
    # paper -> note keeps the source facet, which a bare note may not carry
    with pytest.raises(FacetError):
        c.rename("paper:a", "note:a")
    assert (tmp_path / "paper" / "a.md").exists()
    assert not (tmp_path / "note").exists()
    assert c.get("paper:a").title == "A"


def test_rename_valid_rewrites_referrer(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    c.add(Node(id="paper:b", kind="paper", title="B", facets={SOURCE: {"year": 2020}}))
    c.add(Node(id="note:a", kind="note", title="A",
               relations=[Relation(source="note:a", predicate="cites", target="paper:b")]))
    c.rename("paper:b", "paper:c")
    assert c.get("paper:c").title == "B"
    assert c.get("note:a").relations[0].target == "paper:c"
    assert c.resolve("paper:b").id == "paper:c"  # deprecated alias still resolves


def test_rename_blocked_by_invalid_referrer_no_writes(tmp_path):
    seed = Corpus(tmp_path)  # no registry — lets us write an invalid referrer
    seed.add(Node(id="topic:t", kind="topic", title="T"))
    seed.add(Node(id="paper:bad", kind="paper", title="Bad", facets={SOURCE: {}},
                  relations=[Relation(source="paper:bad", predicate="about", target="topic:t")]))
    c = Corpus(tmp_path, registry=_registry())
    with pytest.raises(InvariantError):  # the invalid referrer fails validation
        c.rename("topic:t", "topic:t2")
    # nothing was written: old id still live, new id absent, referrer untouched
    fresh = Corpus(tmp_path)
    assert fresh.get("topic:t").title == "T"
    with pytest.raises(RefError):
        fresh.get("topic:t2")
    assert fresh.get("paper:bad").relations[0].target == "topic:t"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk uv run pytest tests/test_corpus_registry.py -q`
Expected: FAIL — current `rename` doesn't validate, so `test_rename_validates_renamed_node_no_write` writes `note:a` (no `FacetError`) and `test_rename_blocked_by_invalid_referrer_no_writes` completes the rename.

- [ ] **Step 3: Replace `rename`**

In `src/nodes/kernel/corpus.py`, replace the entire existing `rename` method:

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

with the prepare-all → validate-all → commit-all version:

```python
    def rename(self, old_id: str, new_id: str) -> Node:
        if old_id not in self.index.id_to_uid:
            raise RefError(f"rename source {old_id!r} is not a live id")
        if self.index.resolve_uid(new_id) is not None:
            raise CollisionError(f"target id {new_id!r} already in use")

        uid = self.index.id_to_uid[old_id]
        referrer_uids = {ir.source_uid for ir in self.index.in_refs.get(old_id, [])}

        # --- prepare: rewrite every node that will change, in memory ---
        node = self.store.read_file(old_id)
        old_path = self.store.path_for(old_id)
        node.id = new_id
        node.kind = NodeId.parse(new_id).kind
        if old_id not in node.deprecated_ids:
            node.deprecated_ids.append(old_id)
        _rewrite_refs(node, old_id, new_id)

        referrers: list[Node] = []
        for referrer_uid in referrer_uids:
            if referrer_uid == uid:
                continue
            referrer = self.store.read_file(self.index.by_uid[referrer_uid].id)
            _rewrite_refs(referrer, old_id, new_id)
            referrers.append(referrer)

        # --- validate: ALL writes, before ANY write (fail-early, no partial rename) ---
        if self.registry is not None:
            self.registry.validate(node)
            for referrer in referrers:
                self.registry.validate(referrer)

        # --- commit: renamed node first (crash-atomic), then referrers ---
        new_path = self.store.write_file(node)
        if old_path != new_path:
            self.store.delete_file(old_id)
        self.index.upsert(node)
        for referrer in referrers:
            self.store.write_file(referrer)
            self.index.upsert(referrer)

        return node
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_corpus_registry.py tests/test_corpus.py -q`
Expected: PASS (3 new rename tests + the existing corpus tests, including the no-registry rename cases).

- [ ] **Step 5: Run gates and commit**

```bash
rtk uv run pytest -q
rtk uv run ruff check src tests
rtk uv run pyright src
rtk git add src/nodes/kernel/corpus.py tests/test_corpus_registry.py
rtk git commit -m "feat(corpus): validate-all-before-write rename (no partial rename under a registry)"
```

---

### Task 6: Package exports + docs

Current-code note: package exports are implemented, and the `docs/STANDARD.md` section below is already present in current docs with later additions around TypeScript, search, similarity, and snapshot persistence.

**Files:**
- Modify: `src/nodes/vocab/__init__.py` (populate re-exports)
- Modify: `docs/STANDARD.md` (append the vocab section)
- Test: `tests/test_vocab_exports.py`

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces: a populated `nodes.vocab` namespace (`register_knowledge_vocab`, kind constants, `Source`/`source_of`/`require_identifiable_source`, `SOURCE`, and the `predicates` module).

- [ ] **Step 1: Write the failing test**

Create `tests/test_vocab_exports.py`:

```python
from __future__ import annotations

import nodes.vocab as vocab


def test_top_level_exports_present():
    assert vocab.register_knowledge_vocab is not None
    assert vocab.NOTE == "note" and vocab.PAPER == "paper" and vocab.DATASET == "dataset"
    assert vocab.SOURCE == "source"
    assert vocab.Source is not None
    assert vocab.source_of is not None and vocab.require_identifiable_source is not None


def test_predicates_module_reachable():
    assert vocab.predicates.CITES == "cites"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_vocab_exports.py -q`
Expected: FAIL — `AttributeError: module 'nodes.vocab' has no attribute 'register_knowledge_vocab'`.

- [ ] **Step 3: Populate `src/nodes/vocab/__init__.py`**

Replace the file contents with:

```python
from __future__ import annotations

from nodes.vocab import predicates
from nodes.vocab.kinds import (
    BOOK,
    DATASET,
    IDEA,
    NOTE,
    PAPER,
    PROSE_KINDS,
    QUESTION,
    SOURCE_KINDS,
    TOPIC,
    register_knowledge_vocab,
)
from nodes.vocab.source import SOURCE, Source, require_identifiable_source, source_of

__all__ = [
    "register_knowledge_vocab",
    "NOTE",
    "IDEA",
    "QUESTION",
    "TOPIC",
    "PAPER",
    "BOOK",
    "DATASET",
    "PROSE_KINDS",
    "SOURCE_KINDS",
    "SOURCE",
    "Source",
    "source_of",
    "require_identifiable_source",
    "predicates",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_vocab_exports.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Append the docs section**

Append to the end of `docs/STANDARD.md`:

```markdown

## Knowledge vocab (Plan 3)
`nodes.vocab` is a separately-importable profile of generally-useful knowledge kinds, one layer
above the domain-free kernel. It imports only from `nodes.kernel`; the kernel never imports it.
Register it onto a `Registry` with `register_knowledge_vocab(reg)` (mirrors
`register_builtin_shapes`).

- **Roster (7 kinds).** Prose (bare, no facets): `note`, `idea`, `question`, `topic`. Source
  (require the `source` facet + the identifiability invariant): `paper`, `book`, `dataset`.
- **`Source` facet** (`facets.source`): `{authors?, year?, container?, identifier?, url?}`, with
  `extra="forbid"` (unknown keys fail) and an invariant requiring at least one of
  `authors`/`year`/`identifier`/`url`. The node's `kind` discriminates paper/book/dataset and
  `title` holds the work title, so `Source` carries neither.
- **Predicates** (`nodes.vocab.predicates`): canonical names `about` (→ topic), `cites`
  (→ source), `answers`/`asks` (→ question), `refines` (→ node), plus helper constructors. A
  shared vocabulary only — predicates remain free-string and are not enforced by the kernel.
- **Enforcement.** `Corpus(root, registry=...)` validates on `add` and `rename`; with
  `registry=None` (default) behavior is unchanged. A registry-backed corpus rejects unregistered
  kinds and facet/invariant violations **before any disk write**, and `rename`
  validates the renamed node and every rewritten referrer before writing anything (no partial
  rename).
```

- [ ] **Step 6: Run full gates and commit**

```bash
rtk uv run pytest -q
rtk uv run ruff check src tests
rtk uv run pyright src
rtk git add src/nodes/vocab/__init__.py tests/test_vocab_exports.py docs/STANDARD.md
rtk git commit -m "feat(vocab): package exports + docs(format): Knowledge vocab (Plan 3)"
```

---

## Self-review notes (for the controller)

- **Spec coverage:** Source facet (Task 1) ↔ spec §4; roster + register (Task 2) ↔ §3; predicates (Task 3) ↔ §5; Corpus add-validation (Task 4) ↔ §6; rename validate-all-before-write (Task 5) ↔ §6; exports + docs (Task 6) ↔ §2/§9. Error handling (§7) is exercised across Tasks 1–2/4–5; testing matrix (§8) is split across the per-task tests.
- **Type consistency:** `SOURCE`/`Source`/`source_of`/`require_identifiable_source` names are stable from Task 1 onward; kind constants and `PROSE_KINDS`/`SOURCE_KINDS` from Task 2; predicate constants/helpers from Task 3; `Corpus(root, registry=None)` from Task 4 used unchanged in Task 5.
- **Layering:** no `nodes.vocab` symbol is imported by any `nodes.kernel` module; the only kernel edit (corpus.py) imports `Registry` from the kernel itself, not the vocab.
```
