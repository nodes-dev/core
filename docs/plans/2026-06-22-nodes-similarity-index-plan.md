# Embedding / Similarity Index (Derived Index) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an embedding + cosine-similarity derived index to the Python kernel — a sibling to the structural `Index` and the BM25F `SearchIndex` — exposed through `Corpus.similar` / `Corpus.query_vector` / `Corpus.similar_text`, with a content-addressed vector cache and frozen fixtures so the later TypeScript port matches exactly.

**Architecture:** One new kernel module `src/nodes/kernel/similarity.py` holds the `Embedder` protocol, an `embed_text` contract, a content-addressed `VectorCache` (raw embedder output, namespaced per model), and an in-memory `VectorIndex` (uid → L2-normalized vector + exact brute-force cosine ranking). A small prerequisite refactor extracts the shared `score_key` rounding into `src/nodes/kernel/ranking.py`, imported by both `search.py` and `similarity.py`. `Corpus` gains an optional `embedder`; when supplied it builds and maintains the `VectorIndex`, validating vectors before any disk mutation. Three committed fixtures pin parity.

**Tech Stack:** Python ≥3.11, stdlib only for the new code (`hashlib`, `json`, `math`, `os`, `re`, `dataclasses`, `typing.Protocol`, `pathlib`) plus existing Pydantic; pytest, ruff (line-length 120), pyright (basic), `uv` runner, src/ layout.

## Global Constraints

- Every module starts with `from __future__ import annotations`.
- New runtime code lives in `src/nodes/kernel/similarity.py` and the new `src/nodes/kernel/ranking.py`; the only edits to existing runtime code are `src/nodes/kernel/search.py` (import `score_key` from `ranking`), `src/nodes/kernel/errors.py` (one new error), and `src/nodes/kernel/corpus.py` (integration). Similarity is a kernel-layer derived index (spec §2).
- **No new dependencies.** Use only stdlib and what the kernel already imports. No external embedding/ML/vector libraries; **no ANN** — exact brute-force cosine only.
- **`similarity.py` depends only on `node.py`, `errors.py`, and `ranking.py`. It MUST NOT import `search.py`.**
- **`embed_text(node)` (frozen contract):** `f"{node.title}\n\n{node.body}"` — one vector per node from title and body joined by exactly one blank line.
- **Cache key:** `text_hash(text) = sha256(text.encode("utf-8")).hexdigest()`. Cache path: `<root>/.nodes-index/vectors/<namespace>/<text_hash>.json`. The cache stores **raw** (un-normalized) embedder output as `{"dim": N, "vector": [...]}`, written with `allow_nan=False`, via temp-file-then-`os.replace`.
- **`cache_namespace` validation:** non-empty, matches `^[A-Za-z0-9._-]+$`, and not `.` or `..`; else `ValueError`.
- **Vector validation (every vector entering the system — embedder output, cache load, query input):** length ≥ 1; every element finite (`NaN`/`±Infinity` → `ValueError`); length equals the index's established `dim` once set (else `ValueError`). Stored vectors are L2-normalized on the way into memory (zero-norm → `ValueError`); the cache keeps raw vectors.
- **Dimension & namespace lifecycle:** empty `VectorIndex` has `dim = None`, `namespace = None`; the first committed vector establishes `dim`; the first `build`/`upsert` binds `namespace`; a later `build`/`upsert` whose embedder reports a different `cache_namespace` raises `ValueError`. Query paths never re-check the namespace except `similar_text`, which enforces `embedder.cache_namespace == self.namespace` when bound.
- **Ranking key (shared with search):** `score_key(s) = math.floor(s * 1_000_000 + 0.5) / 1_000_000`, from `ranking.py`. Cosine similarity `cos = Σ_i a_i·b_i` over the two L2-normalized vectors, summed in **index order**. Ranking sort key is `(-score_key(score), id)`.
- **`k` contract (identical to search's `limit`):** `None` = unbounded; otherwise a positive `int` (`bool` rejected as non-int, non-`int` rejected, `<= 0` rejected) → `ValueError`.
- **Query surface:** `query_vector(vec, k=None)`, `similar(uid, k=None)` (excludes `uid` itself; unknown uid → `KeyError`), `similar_text(text, embedder, k=None)`. On an **empty index** queries still validate the query vector (finite/length/non-zero) but skip the dimension match and return `[]`.
- **`VectorIndex.build` rejects a duplicate `uid`** with `CollisionError` (from `nodes.kernel.errors`), mirroring `Index.build` / `SearchIndex.build`.
- **`Corpus` integration:** `Corpus(root, registry=None, embedder=None)`. The vector index is built only when `embedder` is supplied. With `embedder=None`, `similar` / `query_vector` / `similar_text` raise `EmbedderRequiredError` **before** any ref resolution. `add` and `rename` resolve+validate the renamed/added node's vector (`prepare`) **before** any disk/structural-index write and commit it **last** (`commit`) — `rename`'s prepare runs after the in-memory ref rewrite + registry validation and before `store.write_file`; `delete` calls `remove`. (A normal rename leaves title/body unchanged ⇒ id-only refresh, no re-embed; the ordering still guarantees no partial corpus state if the vector step fails.) All existing `Corpus` behavior and the existing test suite stay unchanged/green.
- **Per-task gates, all clean before commit:** `rtk uv run pytest -q`, `rtk uv run ruff check src tests`, `rtk uv run pyright src`.
- **Working directories:** run all `rtk uv run …` from `~/d/nodes/python/`; run all `rtk git …` from `~/d/nodes/`. Paths in `Files:` blocks are repo-root-relative.

---

### Task 1: Extract `score_key` into a shared `ranking.py`

Prerequisite refactor so `search` and `similarity` share one source of truth for the parity-critical rounding without coupling the two facets.

**Files:**
- Create: `python/src/nodes/kernel/ranking.py`
- Modify: `python/src/nodes/kernel/search.py` (remove local `score_key` def; import from `ranking`)
- Modify: `python/tests/test_search_query.py` (move `score_key` import + test out)
- Modify: `python/tests/test_search_parity.py:8` (import `score_key` from `ranking`)
- Modify: `python/scripts/gen_search_oracle.py:7` (import `score_key` from `ranking`)
- Create: `python/tests/test_ranking.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `score_key(score: float) -> float` in `nodes.kernel.ranking`. Consumed by `search.py`, `similarity.py` (Task 5), and oracle scripts/tests.

- [ ] **Step 1: Create `python/tests/test_ranking.py` (failing — module does not exist yet)**

```python
from __future__ import annotations

from nodes.kernel.ranking import score_key


def test_score_key_rounds_to_6dp():
    assert score_key(1.2345674) == 1.234567   # rounds down
    assert score_key(1.2345678) == 1.234568   # rounds up
    assert score_key(0.0) == 0.0


def test_score_key_handles_negative():
    # cosine can be negative; floor-based half-up must still round correctly
    assert score_key(-0.3408105) == -0.340810
    assert score_key(-1.0) == -1.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk uv run pytest tests/test_ranking.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'nodes.kernel.ranking'`.

- [ ] **Step 3: Create `python/src/nodes/kernel/ranking.py`**

```python
from __future__ import annotations

import math


def score_key(score: float) -> float:
    """Half-up rounding to 6 decimal places — the shared ranking/parity key.

    Used by both the full-text search index and the similarity index. Floor-based
    half-up is identical in Python and TypeScript (``math.floor`` / ``Math.floor``
    agree on negative operands), so it is correct over BM25 (non-negative) and
    cosine (``[-1, 1]``) scores alike.
    """
    return math.floor(score * 1_000_000 + 0.5) / 1_000_000
```

- [ ] **Step 4: Point `search.py` at `ranking.score_key`**

In `python/src/nodes/kernel/search.py`, delete the local `score_key` definition (the `def score_key(score: float) -> float:` block through its `return` line, lines ~29-35) and add the import beside the existing kernel imports (after `from nodes.kernel.node import Node`):

```python
from nodes.kernel.ranking import score_key
```

Leave `import math` in place — `search.py` still uses `math.log`. The two call sites (`hits.sort(key=lambda h: (-score_key(h.score), h.id))`) are unchanged.

- [ ] **Step 5: Update the remaining `score_key` importers**

In `python/tests/test_search_query.py`, change line 8 from
`from nodes.kernel.search import SearchHit, SearchIndex, score_key` to:

```python
from nodes.kernel.search import SearchHit, SearchIndex
```

and **delete** its `test_score_key_rounds_to_6dp` function (now owned by `test_ranking.py`).

In `python/tests/test_search_parity.py`, change line 8 from
`from nodes.kernel.search import score_key` to:

```python
from nodes.kernel.ranking import score_key
```

In `python/scripts/gen_search_oracle.py`, change line 7 from
`from nodes.kernel.search import score_key` to:

```python
from nodes.kernel.ranking import score_key
```

- [ ] **Step 6: Run the full suite + gates**

Run: `rtk uv run pytest -q`
Expected: PASS (all pre-existing search tests still green; `test_ranking.py` green).
Run: `rtk uv run ruff check src tests`
Expected: clean (no unused `score_key` import left behind).
Run: `rtk uv run pyright src`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
rtk git add python/src/nodes/kernel/ranking.py python/src/nodes/kernel/search.py \
  python/tests/test_ranking.py python/tests/test_search_query.py \
  python/tests/test_search_parity.py python/scripts/gen_search_oracle.py
rtk git commit -m "refactor(kernel): extract shared score_key into ranking.py"
```

---

### Task 2: Similarity foundations — `Embedder`, `embed_text`, validators

The pure, I/O-free primitives every later task consumes.

**Files:**
- Create: `python/src/nodes/kernel/similarity.py`
- Create: `python/tests/test_similarity_foundations.py`

**Interfaces:**
- Consumes: `Node` (`nodes.kernel.node`).
- Produces: `Vector = tuple[float, ...]`; `class Embedder(Protocol)` with `cache_namespace: str` and `embed(texts: list[str]) -> list[Vector]`; `embed_text(node: Node) -> str`; `text_hash(text: str) -> str`; `validate_namespace(namespace: str) -> None`; `validate_text_hash(text_hash: str) -> None`; `_validate_finite(vec: Vector) -> None`; `_normalize(vec: Vector) -> Vector`.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_similarity_foundations.py`:

```python
from __future__ import annotations

import math

import pytest

from nodes.kernel.node import Node
from nodes.kernel.similarity import (
    _normalize,
    _validate_finite,
    embed_text,
    text_hash,
    validate_namespace,
    validate_text_hash,
)


def test_embed_text_joins_title_and_body_with_blank_line():
    node = Node(id="topic:x", kind="topic", title="Title", body="line one\nline two")
    assert embed_text(node) == "Title\n\nline one\nline two"


def test_text_hash_is_sha256_of_utf8():
    import hashlib

    assert text_hash("café") == hashlib.sha256("café".encode("utf-8")).hexdigest()


@pytest.mark.parametrize("ns", ["model-v1", "openai.text-3", "A_b.C-1"])
def test_validate_namespace_accepts_safe(ns):
    validate_namespace(ns)  # no raise


@pytest.mark.parametrize("ns", ["", ".", "..", "a/b", "a b", "a\0b", "naïve"])
def test_validate_namespace_rejects_unsafe(ns):
    with pytest.raises(ValueError):
        validate_namespace(ns)


@pytest.mark.parametrize("h", ["a" * 64, "0123456789abcdef" * 4])
def test_validate_text_hash_accepts_64_lower_hex(h):
    validate_text_hash(h)  # no raise


@pytest.mark.parametrize(
    "h", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65, "../" + "a" * 61]
)
def test_validate_text_hash_rejects_bad(h):
    with pytest.raises(ValueError):
        validate_text_hash(h)


def test_validate_finite_rejects_empty_and_nonfinite():
    _validate_finite((1.0, 2.0))  # ok
    with pytest.raises(ValueError):
        _validate_finite(())
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError):
            _validate_finite((1.0, bad))


def test_normalize_unit_length_and_rejects_zero():
    nv = _normalize((3.0, 4.0))
    assert nv == pytest.approx((0.6, 0.8))
    assert math.isclose(math.sqrt(sum(x * x for x in nv)), 1.0)
    with pytest.raises(ValueError):
        _normalize((0.0, 0.0))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk uv run pytest tests/test_similarity_foundations.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'nodes.kernel.similarity'`.

- [ ] **Step 3: Create `python/src/nodes/kernel/similarity.py` with the foundations**

```python
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from nodes.kernel.node import Node

Vector = tuple[float, ...]

_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class Embedder(Protocol):
    """The seam: turns text into vectors. The kernel ships no concrete embedder."""

    @property
    def cache_namespace(self) -> str: ...

    def embed(self, texts: list[str]) -> list[Vector]: ...


def embed_text(node: Node) -> str:
    """The frozen per-node embedding input: title and body joined by one blank line."""
    return f"{node.title}\n\n{node.body}"


def text_hash(text: str) -> str:
    """Content-address key for the vector cache."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_namespace(namespace: str) -> None:
    """A cache_namespace must be a safe single path segment."""
    if not namespace or namespace in (".", "..") or _NAMESPACE_RE.match(namespace) is None:
        raise ValueError(f"invalid cache_namespace {namespace!r}")


_TEXT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_text_hash(text_hash: str) -> None:
    """A cache key must be exactly 64 lowercase hex chars (a SHA-256 hexdigest)."""
    if _TEXT_HASH_RE.match(text_hash) is None:
        raise ValueError(f"invalid text_hash {text_hash!r}")


def _validate_finite(vec: Vector) -> None:
    if len(vec) < 1:
        raise ValueError("vector must have length >= 1")
    for x in vec:
        if not math.isfinite(x):
            raise ValueError(f"vector contains non-finite value {x!r}")


def _normalize(vec: Vector) -> Vector:
    """Return the L2-normalized vector; reject zero-norm and non-finite input."""
    _validate_finite(vec)
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        raise ValueError("cannot normalize a zero-norm vector")
    return tuple(x / norm for x in vec)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk uv run pytest tests/test_similarity_foundations.py -q`
Expected: PASS.

- [ ] **Step 5: Gates**

Run: `rtk uv run ruff check src tests` — Expected: clean.
Run: `rtk uv run pyright src` — Expected: clean.

- [ ] **Step 6: Commit**

```bash
rtk git add python/src/nodes/kernel/similarity.py python/tests/test_similarity_foundations.py
rtk git commit -m "feat(similarity): embedder protocol, embed_text, vector validators"
```

---

### Task 3: `VectorCache` — content-addressed disk cache

**Files:**
- Modify: `python/src/nodes/kernel/similarity.py` (append `VectorCache`)
- Modify: `.gitignore` (ignore `.nodes-index/`)
- Create: `python/tests/test_vector_cache.py`

**Interfaces:**
- Consumes: `Vector`, `validate_namespace`, `_validate_finite` (Task 2).
- Produces: `class VectorCache` with `__init__(root: Path | str)`, `get(namespace: str, text_hash: str) -> Vector | None`, `put(namespace: str, text_hash: str, vector: Vector) -> None`.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_vector_cache.py`:

```python
from __future__ import annotations

import json

import pytest

from nodes.kernel.similarity import VectorCache

H = "a" * 64   # a valid 64-char lowercase-hex cache key
H2 = "b" * 64


def test_put_then_get_roundtrips_raw_vector(tmp_path):
    cache = VectorCache(tmp_path)
    cache.put("model-v1", H, (0.5, -0.25, 2.0))
    assert cache.get("model-v1", H) == (0.5, -0.25, 2.0)


def test_get_miss_returns_none(tmp_path):
    assert VectorCache(tmp_path).get("model-v1", H2) is None


def test_namespaces_are_isolated(tmp_path):
    cache = VectorCache(tmp_path)
    cache.put("model-a", H, (1.0,))
    assert cache.get("model-b", H) is None


def test_put_writes_expected_json_with_dim(tmp_path):
    cache = VectorCache(tmp_path)
    cache.put("model-v1", H, (1.0, 2.0))
    path = tmp_path / ".nodes-index" / "vectors" / "model-v1" / f"{H}.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"dim": 2, "vector": [1.0, 2.0]}


def test_invalid_namespace_rejected(tmp_path):
    with pytest.raises(ValueError):
        VectorCache(tmp_path).get("../escape", H)


def test_path_traversal_key_rejected(tmp_path):
    cache = VectorCache(tmp_path)
    with pytest.raises(ValueError):
        cache.get("model-v1", "../../etc/passwd")
    with pytest.raises(ValueError):
        cache.put("model-v1", "..", (1.0,))


def test_non_hex_or_wrong_length_key_rejected(tmp_path):
    with pytest.raises(ValueError):
        VectorCache(tmp_path).get("model-v1", "not-a-hash")
    with pytest.raises(ValueError):
        VectorCache(tmp_path).get("model-v1", "A" * 64)  # uppercase not allowed


def test_corrupt_file_fails_early(tmp_path):
    cache = VectorCache(tmp_path)
    path = tmp_path / ".nodes-index" / "vectors" / "model-v1" / f"{H}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        cache.get("model-v1", H)


def test_dim_length_mismatch_fails_early(tmp_path):
    cache = VectorCache(tmp_path)
    path = tmp_path / ".nodes-index" / "vectors" / "model-v1" / f"{H}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"dim": 3, "vector": [1.0, 2.0]}), encoding="utf-8")
    with pytest.raises(ValueError):
        cache.get("model-v1", H)


def test_put_rejects_nonfinite(tmp_path):
    with pytest.raises(ValueError):
        VectorCache(tmp_path).put("model-v1", H, (float("nan"),))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk uv run pytest tests/test_vector_cache.py -q`
Expected: FAIL with `ImportError: cannot import name 'VectorCache'`.

- [ ] **Step 3: Append `VectorCache` to `similarity.py`**

Add these imports to the top of `python/src/nodes/kernel/similarity.py` (with the existing stdlib imports):

```python
import json
import os
from pathlib import Path
```

Append the class:

```python
class VectorCache:
    """Content-addressed on-disk cache of RAW embedder output, namespaced per embedder.

    Disposable: deleting the directory just forces re-embedding. All ranking math
    lives in VectorIndex; this is purely a model-output cache.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, namespace: str, text_hash: str) -> Path:
        validate_namespace(namespace)
        validate_text_hash(text_hash)
        return self.root / ".nodes-index" / "vectors" / namespace / f"{text_hash}.json"

    def get(self, namespace: str, text_hash: str) -> Vector | None:
        path = self._path(namespace, text_hash)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"corrupt cache file {path}: {exc}") from exc
        if not isinstance(data, dict) or "dim" not in data or "vector" not in data:
            raise ValueError(f"corrupt cache file {path}: missing dim/vector")
        raw = data["vector"]
        if not isinstance(raw, list) or len(raw) != data["dim"]:
            raise ValueError(f"corrupt cache file {path}: dim/vector length mismatch")
        try:
            vec: Vector = tuple(float(x) for x in raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"corrupt cache file {path}: non-numeric vector") from exc
        _validate_finite(vec)
        return vec

    def put(self, namespace: str, text_hash: str, vector: Vector) -> None:
        _validate_finite(vector)
        path = self._path(namespace, text_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"dim": len(vector), "vector": list(vector)}, allow_nan=False)
        tmp = path.parent / f"{text_hash}.json.tmp"
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk uv run pytest tests/test_vector_cache.py -q`
Expected: PASS.

- [ ] **Step 5: Ignore the cache directory**

Append to `.gitignore` (it is created under any corpus root that uses an embedder):

```
.nodes-index/
```

- [ ] **Step 6: Gates**

Run: `rtk uv run ruff check src tests` — Expected: clean.
Run: `rtk uv run pyright src` — Expected: clean.

- [ ] **Step 7: Commit**

```bash
rtk git add python/src/nodes/kernel/similarity.py python/tests/test_vector_cache.py .gitignore
rtk git commit -m "feat(similarity): content-addressed vector cache (raw output, atomic writes)"
```

---

### Task 4: `VectorIndex` — state, build/upsert/remove, lifecycle

The in-memory store plus its fail-before-mutation `prepare`/`commit` split. Query/ranking is Task 5.

**Files:**
- Modify: `python/src/nodes/kernel/similarity.py` (append `_PreparedVector`, `VectorIndex`)
- Create: `python/tests/test_vector_index.py`

**Interfaces:**
- Consumes: `Embedder`, `Vector`, `embed_text`, `text_hash`, `validate_namespace`, `_validate_finite`, `_normalize`, `VectorCache` (Tasks 2-3); `CollisionError` (`nodes.kernel.errors`); `Node`.
- Produces: `class VectorIndex` with attrs `vectors: dict[str, Vector]`, `id_by_uid: dict[str, str]`, `hash_by_uid: dict[str, str]`, `dim: int | None`, `namespace: str | None`; classmethod `build(nodes, embedder, cache) -> VectorIndex`; `prepare(node, embedder, cache) -> _PreparedVector`; `commit(node, prepared) -> None`; `upsert(node, embedder, cache) -> None`; `remove(uid) -> None`. Consumed by Task 5 (query methods) and Task 6 (`Corpus`).

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_vector_index.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import CollisionError
from nodes.kernel.node import Node
from nodes.kernel.similarity import VectorCache, VectorIndex, embed_text


class DictEmbedder:
    """Deterministic test embedder: maps exact embed_text -> raw vector."""

    def __init__(self, table: dict[str, tuple[float, ...]], namespace: str = "stub-v1") -> None:
        self._table = table
        self.cache_namespace = namespace

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self._table[t] for t in texts]


def _node(node_id: str, title: str, body: str = "", uid: str | None = None) -> Node:
    return Node(id=node_id, uid=uid or node_id.replace(":", "_"), kind="topic", title=title, body=body)


def _embedder(nodes: list[Node], vectors: list[tuple[float, ...]], **kw) -> DictEmbedder:
    return DictEmbedder({embed_text(n): v for n, v in zip(nodes, vectors)}, **kw)


def test_build_normalizes_and_sets_dim_and_namespace(tmp_path):
    nodes = [_node("topic:a", "a"), _node("topic:b", "b")]
    emb = _embedder(nodes, [(3.0, 4.0), (0.0, 1.0)])
    idx = VectorIndex.build(nodes, emb, VectorCache(tmp_path))
    assert idx.dim == 2
    assert idx.namespace == "stub-v1"
    assert idx.vectors["topic_a"] == pytest.approx((0.6, 0.8))
    assert idx.id_by_uid == {"topic_a": "topic:a", "topic_b": "topic:b"}


def test_build_rejects_duplicate_uid(tmp_path):
    nodes = [_node("topic:a", "a", uid="dup"), _node("topic:b", "b", uid="dup")]
    emb = _embedder(nodes, [(1.0, 0.0), (0.0, 1.0)])
    with pytest.raises(CollisionError):
        VectorIndex.build(nodes, emb, VectorCache(tmp_path))


def test_upsert_replaces_on_content_change(tmp_path):
    n1 = _node("topic:a", "a", body="one", uid="u")
    n2 = _node("topic:a", "a", body="two", uid="u")
    emb = DictEmbedder({embed_text(n1): (1.0, 0.0), embed_text(n2): (0.0, 1.0)})
    idx = VectorIndex.build([n1], emb, VectorCache(tmp_path))
    idx.upsert(n2, emb, VectorCache(tmp_path))
    assert idx.vectors["u"] == pytest.approx((0.0, 1.0))
    assert idx.dim == 2


def test_upsert_same_content_new_id_refreshes_id_only(tmp_path):
    # the rename case: title/body unchanged, id changed -> no re-embed
    n1 = _node("topic:a", "a", body="x", uid="u")
    renamed = _node("topic:a2", "a", body="x", uid="u")
    table = {embed_text(n1): (1.0, 0.0)}  # only the original text is embeddable

    class OneShot(DictEmbedder):
        def embed(self, texts):  # fail loudly if a re-embed is attempted
            return [self._table[t] for t in texts]

    emb = OneShot(table)
    idx = VectorIndex.build([n1], emb, VectorCache(tmp_path))
    before = idx.vectors["u"]
    idx.upsert(renamed, emb, VectorCache(tmp_path))  # must not call embed(missing text)
    assert idx.vectors["u"] == before
    assert idx.id_by_uid["u"] == "topic:a2"


def test_remove_drops_all_state(tmp_path):
    nodes = [_node("topic:a", "a"), _node("topic:b", "b")]
    emb = _embedder(nodes, [(1.0, 0.0), (0.0, 1.0)])
    idx = VectorIndex.build(nodes, emb, VectorCache(tmp_path))
    idx.remove("topic_a")
    assert "topic_a" not in idx.vectors and "topic_a" not in idx.id_by_uid


def test_dimension_mismatch_rejected(tmp_path):
    nodes = [_node("topic:a", "a"), _node("topic:b", "b")]
    emb = _embedder(nodes, [(1.0, 0.0), (1.0, 0.0, 0.0)])
    with pytest.raises(ValueError):
        VectorIndex.build(nodes, emb, VectorCache(tmp_path))


def test_namespace_mismatch_rejected(tmp_path):
    n1 = [_node("topic:a", "a")]
    idx = VectorIndex.build(n1, _embedder(n1, [(1.0, 0.0)], namespace="model-a"), VectorCache(tmp_path))
    n2 = _node("topic:b", "b")
    other = DictEmbedder({embed_text(n2): (0.0, 1.0)}, namespace="model-b")
    with pytest.raises(ValueError):
        idx.upsert(n2, other, VectorCache(tmp_path))


def test_zero_norm_vector_rejected(tmp_path):
    nodes = [_node("topic:a", "a")]
    emb = _embedder(nodes, [(0.0, 0.0)])
    with pytest.raises(ValueError):
        VectorIndex.build(nodes, emb, VectorCache(tmp_path))


def test_empty_build_binds_namespace(tmp_path):
    idx = VectorIndex.build([], DictEmbedder({}, namespace="model-x"), VectorCache(tmp_path))
    assert idx.namespace == "model-x"
    assert idx.dim is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk uv run pytest tests/test_vector_index.py -q`
Expected: FAIL with `ImportError: cannot import name 'VectorIndex'`.

- [ ] **Step 3: Append `_PreparedVector` + `VectorIndex` to `similarity.py`**

Add to the imports at the top of `similarity.py`:

```python
from collections.abc import Iterable
from dataclasses import dataclass

from nodes.kernel.errors import CollisionError
```

Append:

```python
@dataclass(frozen=True)
class _PreparedVector:
    text_hash: str
    namespace: str
    vector: Vector | None  # None => content unchanged (id-only refresh)


class VectorIndex:
    """In-memory uid -> L2-normalized vector store with exact cosine ranking.

    Bound to exactly one embedder namespace and one dimension (cosine across
    vectors from different models or dimensions is meaningless).
    """

    def __init__(self) -> None:
        self.vectors: dict[str, Vector] = {}
        self.id_by_uid: dict[str, str] = {}
        self.hash_by_uid: dict[str, str] = {}
        self.dim: int | None = None
        self.namespace: str | None = None

    @classmethod
    def build(cls, nodes: Iterable[Node], embedder: Embedder, cache: VectorCache) -> "VectorIndex":
        idx = cls()
        validate_namespace(embedder.cache_namespace)
        idx.namespace = embedder.cache_namespace  # bind even for an empty corpus
        for node in nodes:
            if node.uid in idx.hash_by_uid:
                raise CollisionError(f"duplicate uid {node.uid!r} in corpus")
            idx.upsert(node, embedder, cache)
        return idx

    def prepare(self, node: Node, embedder: Embedder, cache: VectorCache) -> _PreparedVector:
        """Resolve + validate the vector WITHOUT mutating index state (cache writes ok)."""
        namespace = embedder.cache_namespace
        validate_namespace(namespace)
        if self.namespace is not None and namespace != self.namespace:
            raise ValueError(f"embedder namespace {namespace!r} != index namespace {self.namespace!r}")
        text = embed_text(node)
        h = text_hash(text)
        if self.hash_by_uid.get(node.uid) == h:
            return _PreparedVector(text_hash=h, namespace=namespace, vector=None)
        cached = cache.get(namespace, h)
        if cached is None:
            embedded = embedder.embed([text])
            if len(embedded) != 1:
                raise ValueError(f"embedder returned {len(embedded)} vectors for 1 input")
            raw: Vector = tuple(float(x) for x in embedded[0])
            _validate_finite(raw)
            cache.put(namespace, h, raw)
        else:
            raw = cached
        if self.dim is not None and len(raw) != self.dim:
            raise ValueError(f"vector dim {len(raw)} != index dim {self.dim}")
        return _PreparedVector(text_hash=h, namespace=namespace, vector=_normalize(raw))

    def commit(self, node: Node, prepared: _PreparedVector) -> None:
        """Apply a prepared vector. Infallible: never raises on valid prepared input."""
        if self.namespace is None:
            self.namespace = prepared.namespace
        if prepared.vector is None:
            self.id_by_uid[node.uid] = node.id  # rename / id-only refresh
            return
        if self.dim is None:
            self.dim = len(prepared.vector)
        self.vectors[node.uid] = prepared.vector
        self.id_by_uid[node.uid] = node.id
        self.hash_by_uid[node.uid] = prepared.text_hash

    def upsert(self, node: Node, embedder: Embedder, cache: VectorCache) -> None:
        self.commit(node, self.prepare(node, embedder, cache))

    def remove(self, uid: str) -> None:
        self.vectors.pop(uid, None)
        self.id_by_uid.pop(uid, None)
        self.hash_by_uid.pop(uid, None)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk uv run pytest tests/test_vector_index.py -q`
Expected: PASS.

- [ ] **Step 5: Gates**

Run: `rtk uv run ruff check src tests` — Expected: clean.
Run: `rtk uv run pyright src` — Expected: clean.

- [ ] **Step 6: Commit**

```bash
rtk git add python/src/nodes/kernel/similarity.py python/tests/test_vector_index.py
rtk git commit -m "feat(similarity): VectorIndex build/upsert/remove with prepare/commit + lifecycle"
```

---

### Task 5: `VectorIndex` query + ranking

**Files:**
- Modify: `python/src/nodes/kernel/similarity.py` (append `SimilarHit`, `_validate_k`, query methods)
- Create: `python/tests/test_vector_query.py`

**Interfaces:**
- Consumes: `VectorIndex` state + `_normalize`, `_validate_finite`, `score_key` (`nodes.kernel.ranking`), `Embedder`.
- Produces: `@dataclass SimilarHit { id: str; uid: str; score: float }`; methods `VectorIndex.query_vector(vec, k=None) -> list[SimilarHit]`, `VectorIndex.similar(uid, k=None) -> list[SimilarHit]`, `VectorIndex.similar_text(text, embedder, k=None) -> list[SimilarHit]`.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_vector_query.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.node import Node
from nodes.kernel.ranking import score_key
from nodes.kernel.similarity import VectorCache, VectorIndex, embed_text


class DictEmbedder:
    def __init__(self, table, namespace="stub-v1"):
        self._table = table
        self.cache_namespace = namespace

    def embed(self, texts):
        return [self._table[t] for t in texts]


def _node(node_id, title, body=""):
    return Node(id=node_id, uid=node_id.replace(":", "_"), kind="topic", title=title, body=body)


def _index(tmp_path, nodes, vectors, **kw):
    emb = DictEmbedder({embed_text(n): v for n, v in zip(nodes, vectors)}, **kw)
    return VectorIndex.build(nodes, emb, VectorCache(tmp_path)), emb


def test_query_vector_exact_cosine(tmp_path):
    nodes = [_node("topic:x", "x"), _node("topic:y", "y")]
    idx, _ = _index(tmp_path, nodes, [(3.0, 4.0), (1.0, 0.0)])
    hits = idx.query_vector((4.0, 3.0))
    by_id = {h.id: h.score for h in hits}
    assert by_id["topic:x"] == pytest.approx(0.96)   # (0.6,0.8)·(0.8,0.6)
    assert by_id["topic:y"] == pytest.approx(0.8)     # (0.6,0.8)·(1,0)


def test_query_vector_ranks_desc_then_id(tmp_path):
    # two docs identical to the query vector tie on score -> id ascending
    nodes = [_node("topic:b", "b"), _node("topic:a", "a")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0), (1.0, 0.0)])
    assert [h.id for h in idx.query_vector((1.0, 0.0))] == ["topic:a", "topic:b"]


def test_similar_excludes_self(tmp_path):
    nodes = [_node("topic:x", "x"), _node("topic:y", "y")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0), (0.0, 1.0)])
    hits = idx.similar("topic_x")
    assert [h.id for h in hits] == ["topic:y"]  # self ('topic:x') excluded


def test_similar_unknown_uid_raises_keyerror(tmp_path):
    nodes = [_node("topic:x", "x")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0)])
    with pytest.raises(KeyError):
        idx.similar("nope")


def test_similar_text_embeds_then_ranks(tmp_path):
    nodes = [_node("topic:x", "x"), _node("topic:y", "y")]
    idx, emb = _index(tmp_path, nodes, [(1.0, 0.0), (0.0, 1.0)])
    emb._table["find x"] = (1.0, 0.0)
    assert [h.id for h in idx.similar_text("find x", emb)] == ["topic:x", "topic:y"]


def test_similar_text_namespace_mismatch_raises(tmp_path):
    nodes = [_node("topic:x", "x")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0)], namespace="model-a")
    other = DictEmbedder({"q": (1.0, 0.0)}, namespace="model-b")
    with pytest.raises(ValueError):
        idx.similar_text("q", other)


def test_similar_text_namespace_checked_on_empty_built_index(tmp_path):
    # build([]) binds the namespace, so even an empty index rejects a foreign embedder
    idx = VectorIndex.build([], DictEmbedder({}, namespace="model-a"), VectorCache(tmp_path))
    other = DictEmbedder({"q": (1.0, 0.0)}, namespace="model-b")
    with pytest.raises(ValueError):
        idx.similar_text("q", other)


def test_limit_k_honored_and_validated(tmp_path):
    nodes = [_node("topic:x", "x"), _node("topic:y", "y")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0), (0.0, 1.0)])
    assert len(idx.query_vector((1.0, 1.0), k=1)) == 1
    for bad in (0, -1, 1.5, True, "1"):
        with pytest.raises(ValueError):
            idx.query_vector((1.0, 1.0), k=bad)


def test_query_validates_vector_even_when_empty(tmp_path):
    idx = VectorIndex()  # empty: dim is None
    assert idx.query_vector((1.0, 2.0)) == []        # valid query, no candidates
    with pytest.raises(ValueError):
        idx.query_vector((0.0, 0.0))                  # zero-norm still rejected
    with pytest.raises(ValueError):
        idx.query_vector(())                          # empty vector still rejected


def test_query_dim_mismatch_rejected(tmp_path):
    nodes = [_node("topic:x", "x")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0)])
    with pytest.raises(ValueError):
        idx.query_vector((1.0, 0.0, 0.0))


def test_score_uses_score_key_for_ranking(tmp_path):
    # scores within 1e-6 collapse under score_key, so id breaks the tie
    nodes = [_node("topic:a", "a"), _node("topic:b", "b")]
    idx, _ = _index(tmp_path, nodes, [(1.0, 0.0), (1.0, 1e-7)])
    hits = idx.query_vector((1.0, 0.0))
    assert score_key(hits[0].score) == score_key(hits[1].score)
    assert [h.id for h in hits] == ["topic:a", "topic:b"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk uv run pytest tests/test_vector_query.py -q`
Expected: FAIL with `ImportError: cannot import name 'SimilarHit'`.

- [ ] **Step 3: Append query support to `similarity.py`**

Add to the imports at the top:

```python
from nodes.kernel.ranking import score_key
```

Append:

```python
@dataclass
class SimilarHit:
    id: str
    uid: str
    score: float


def _validate_k(k: int | None) -> None:
    if k is not None and (isinstance(k, bool) or not isinstance(k, int) or k <= 0):
        raise ValueError(f"k must be a positive int or None, got {k!r}")
```

and add these methods to `VectorIndex` (after `remove`):

```python
    def query_vector(self, vec: Vector, k: int | None = None) -> list[SimilarHit]:
        _validate_k(k)
        return self._rank(self._prepare_query(vec), k, exclude_uid=None)

    def similar(self, uid: str, k: int | None = None) -> list[SimilarHit]:
        _validate_k(k)
        if uid not in self.vectors:
            raise KeyError(uid)
        return self._rank(self.vectors[uid], k, exclude_uid=uid)

    def similar_text(self, text: str, embedder: Embedder, k: int | None = None) -> list[SimilarHit]:
        _validate_k(k)
        if self.namespace is not None and embedder.cache_namespace != self.namespace:
            raise ValueError(
                f"embedder namespace {embedder.cache_namespace!r} != index namespace {self.namespace!r}"
            )
        embedded = embedder.embed([text])
        if len(embedded) != 1:
            raise ValueError(f"embedder returned {len(embedded)} vectors for 1 input")
        return self.query_vector(tuple(float(x) for x in embedded[0]), k)

    def _prepare_query(self, vec: Vector) -> Vector:
        vec = tuple(float(x) for x in vec)
        _validate_finite(vec)
        if self.dim is not None and len(vec) != self.dim:
            raise ValueError(f"query dim {len(vec)} != index dim {self.dim}")
        return _normalize(vec)

    def _rank(self, query_vec: Vector, k: int | None, *, exclude_uid: str | None) -> list[SimilarHit]:
        hits = [
            SimilarHit(
                id=self.id_by_uid[uid],
                uid=uid,
                score=sum(a * b for a, b in zip(query_vec, vec)),
            )
            for uid, vec in self.vectors.items()
            if uid != exclude_uid
        ]
        hits.sort(key=lambda h: (-score_key(h.score), h.id))
        return hits if k is None else hits[:k]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk uv run pytest tests/test_vector_query.py -q`
Expected: PASS.

- [ ] **Step 5: Gates**

Run: `rtk uv run ruff check src tests` — Expected: clean.
Run: `rtk uv run pyright src` — Expected: clean.

- [ ] **Step 6: Commit**

```bash
rtk git add python/src/nodes/kernel/similarity.py python/tests/test_vector_query.py
rtk git commit -m "feat(similarity): cosine query/ranking — query_vector, similar, similar_text"
```

---

### Task 6: `Corpus` integration + `EmbedderRequiredError`

**Files:**
- Modify: `python/src/nodes/kernel/errors.py` (add `EmbedderRequiredError`)
- Modify: `python/src/nodes/kernel/corpus.py` (optional `embedder`; maintain `VectorIndex`; query methods)
- Create: `python/tests/test_corpus_similarity.py`

**Interfaces:**
- Consumes: `VectorIndex`, `VectorCache`, `SimilarHit`, `Embedder` (Tasks 2-5); existing `Corpus`, `Index`, `SearchIndex`, `Store`, `RefError`.
- Produces: `Corpus.__init__(root, registry=None, embedder=None)`; attrs `embedder`, `vector_cache: VectorCache | None`, `vector_index: VectorIndex | None`; methods `Corpus.similar(ref, k=None) -> list[SimilarHit]`, `Corpus.query_vector(vec, k=None) -> list[SimilarHit]`, `Corpus.similar_text(text, k=None) -> list[SimilarHit]`.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_corpus_similarity.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import EmbedderRequiredError
from nodes.kernel.node import Node


class DictEmbedder:
    def __init__(self, table, namespace="stub-v1"):
        self._table = table
        self.cache_namespace = namespace

    def embed(self, texts):
        return [self._table[t] for t in texts]


# Keys are embed_text == f"{title}\n\n{body}" for the in-memory and round-tripped nodes.
PET = (1.0, 0.0)
PET2 = (0.9, 0.1)
CAR = (0.0, 1.0)


def _embedder():
    # keyed by embed_text == "<title>\n\n<body>"
    return DictEmbedder(
        {
            "cat\n\nfeline": PET,
            "dog\n\ncanine": PET2,
            "car\n\nvehicle": CAR,
            "find pet": PET,
        }
    )


def _seed(c: Corpus) -> None:
    c.add(Node(id="topic:cat", kind="topic", title="cat", body="feline"))
    c.add(Node(id="topic:dog", kind="topic", title="dog", body="canine"))
    c.add(Node(id="topic:car", kind="topic", title="car", body="vehicle"))


def test_disabled_without_embedder_raises_before_resolution(tmp_path):
    c = Corpus(tmp_path)  # no embedder
    with pytest.raises(EmbedderRequiredError):
        c.similar("topic:does-not-exist")  # raises BEFORE ref resolution
    with pytest.raises(EmbedderRequiredError):
        c.query_vector((1.0, 0.0))
    with pytest.raises(EmbedderRequiredError):
        c.similar_text("anything")


def test_similar_ranks_by_cosine(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    assert [h.id for h in c.similar("topic:cat")] == ["topic:dog", "topic:car"]


def test_query_vector_and_similar_text(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    assert [h.id for h in c.query_vector((1.0, 0.0), k=2)] == ["topic:cat", "topic:dog"]
    assert [h.id for h in c.similar_text("find pet", k=1)] == ["topic:cat"]


def test_similar_unknown_ref_raises_referror(tmp_path):
    from nodes.kernel.errors import RefError

    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    with pytest.raises(RefError):
        c.similar("topic:missing")


def test_index_current_after_delete_and_rebuild_from_disk(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    c.delete("topic:dog")
    assert [h.id for h in c.similar("topic:cat")] == ["topic:car"]
    fresh = Corpus(tmp_path, embedder=_embedder())  # rebuild from disk (warm cache)
    assert [h.id for h in fresh.similar("topic:cat")] == ["topic:car"]


def test_rename_refreshes_id_without_reembedding(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    c.rename("topic:cat", "topic:kitten")
    assert [h.id for h in c.query_vector((1.0, 0.0), k=1)] == ["topic:kitten"]


def test_failed_embedding_leaves_corpus_unmutated(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    bad = Node(id="topic:bad", kind="topic", title="bad", body="missing")  # not in table
    with pytest.raises(KeyError):
        c.add(bad)
    # no file written (re-scan disk), structural + search indexes unchanged
    assert c.index.resolve_uid("topic:bad") is None
    assert c.search("bad") == []
    assert "topic:bad" not in [n.id for n in c.all()]


def test_failed_rename_vector_leaves_corpus_unmutated(tmp_path):
    c = Corpus(tmp_path, embedder=_embedder())
    _seed(c)
    # Force a namespace inconsistency so the vector prepare fails during rename —
    # after the in-memory rewrite + registry validation, before any disk write.
    c.embedder = DictEmbedder({}, namespace="other-model")
    with pytest.raises(ValueError):
        c.rename("topic:cat", "topic:kitten")
    assert c.index.resolve_uid("topic:cat") is not None
    assert c.index.resolve_uid("topic:kitten") is None
    assert [n.id for n in c.all()].count("topic:cat") == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk uv run pytest tests/test_corpus_similarity.py -q`
Expected: FAIL with `ImportError: cannot import name 'EmbedderRequiredError'`.

- [ ] **Step 3: Add `EmbedderRequiredError` to `errors.py`**

Append to `python/src/nodes/kernel/errors.py`:

```python
class EmbedderRequiredError(NodesError):
    """Raised when a similarity API is used on a Corpus built without an embedder."""
```

- [ ] **Step 4: Wire `Corpus`**

In `python/src/nodes/kernel/corpus.py`, update the imports:

```python
from nodes.kernel.errors import CollisionError, EmbedderRequiredError, RefError
from nodes.kernel.similarity import Embedder, SimilarHit, Vector, VectorCache, VectorIndex
```

(keep the existing `SearchHit, SearchIndex` import). Replace `Corpus.__init__` with:

```python
    def __init__(self, root: Path, registry: Registry | None = None, embedder: Embedder | None = None) -> None:
        self.store = Store(root)
        self.registry = registry
        self.embedder = embedder
        nodes = self.store.all_nodes()
        self.index = Index.build(nodes)
        self.search_index = SearchIndex.build(nodes)
        if embedder is not None:
            self.vector_cache: VectorCache | None = VectorCache(root)
            self.vector_index: VectorIndex | None = VectorIndex.build(nodes, embedder, self.vector_cache)
        else:
            self.vector_cache = None
            self.vector_index = None
```

Replace `add` with the fail-before-mutation ordering:

```python
    def add(self, node: Node) -> Node:
        if self.registry is not None:
            self.registry.validate(node)
        self.index.assert_addable(node)
        prepared = None
        if self.vector_index is not None:
            assert self.embedder is not None and self.vector_cache is not None
            prepared = self.vector_index.prepare(node, self.embedder, self.vector_cache)
        self.store.write_file(node)
        self.index.upsert(node)
        self.search_index.upsert(node)
        if self.vector_index is not None and prepared is not None:
            self.vector_index.commit(node, prepared)
        return node
```

In `delete`, after `self.search_index.remove(uid)` add:

```python
        if self.vector_index is not None:
            self.vector_index.remove(uid)
```

In `rename`, honor the fail-before-mutation guarantee. Insert the vector **prepare** after the `# --- validate ---` block (registry validation of `node` + referrers) and immediately **before** `new_path = self.store.write_file(node)`:

```python
        # --- prepare similarity vector (fail before any disk write) ---
        prepared = None
        if self.vector_index is not None:
            assert self.embedder is not None and self.vector_cache is not None
            prepared = self.vector_index.prepare(node, self.embedder, self.vector_cache)
```

Then, after the existing final `self.search_index.upsert(node)` (and before `return node`), **commit** it last:

```python
        if self.vector_index is not None and prepared is not None:
            self.vector_index.commit(node, prepared)
```

(Referrer nodes only have their refs rewritten — title/body unchanged — so their vectors never change and need no update.)

Add the three query methods (e.g. just after the existing `search` method):

```python
    def similar(self, ref: str, k: int | None = None) -> list[SimilarHit]:
        if self.vector_index is None:
            raise EmbedderRequiredError("similarity requires Corpus(embedder=...)")
        return self.vector_index.similar(self._require_uid(ref), k)

    def query_vector(self, vec: Vector, k: int | None = None) -> list[SimilarHit]:
        if self.vector_index is None:
            raise EmbedderRequiredError("similarity requires Corpus(embedder=...)")
        return self.vector_index.query_vector(vec, k)

    def similar_text(self, text: str, k: int | None = None) -> list[SimilarHit]:
        if self.vector_index is None:
            raise EmbedderRequiredError("similarity requires Corpus(embedder=...)")
        assert self.embedder is not None
        return self.vector_index.similar_text(text, self.embedder, k)
```

- [ ] **Step 5: Run the test + full suite + gates**

Run: `rtk uv run pytest tests/test_corpus_similarity.py -q` — Expected: PASS.
Run: `rtk uv run pytest -q` — Expected: PASS (existing suite unchanged).
Run: `rtk uv run ruff check src tests` — Expected: clean.
Run: `rtk uv run pyright src` — Expected: clean.

- [ ] **Step 6: Commit**

```bash
rtk git add python/src/nodes/kernel/errors.py python/src/nodes/kernel/corpus.py \
  python/tests/test_corpus_similarity.py
rtk git commit -m "feat(similarity): opt-in Corpus integration with fail-before-mutation ordering"
```

---

### Task 7: Parity fixtures, oracle generator, docs

Freeze a fixture corpus + hand-authored low-dim vectors + a generated oracle so the later TypeScript port asserts identical rankings.

**Files:**
- Create: `fixtures/similarity-corpus/topic/cat.md`, `dog.md`, `car.md`, `truck.md`
- Create: `fixtures/similarity.vectors.json` (hand-authored, frozen)
- Create: `python/scripts/gen_similarity_oracle.py`
- Create: `fixtures/similarity.oracle.json` (generated by the script)
- Create: `python/tests/test_similarity_parity.py`
- Modify: `docs/format.md` (document the similarity index + known-limitation update)

**Interfaces:**
- Consumes: `Corpus`, `embed_text` (`nodes.kernel.similarity`), `score_key` (`nodes.kernel.ranking`).
- Produces: committed fixtures consumed read-only by this parity test and by the future TS port.

> **Fixture-format note (refinement of spec §7):** the spec's illustrative
> `documents` schema listed `{id, embed_text, vector}`. To eliminate any
> frontmatter/trailing-newline mismatch between the fixture file and the parser,
> document vectors here are keyed by **id** only, and the `LookupEmbedder` table is
> built from each corpus node's *actual* parsed `embed_text(node)`. Behavior is
> unchanged; this only makes the fixture robust to body whitespace.

- [ ] **Step 1: Create the fixture corpus (4 topic nodes)**

`fixtures/similarity-corpus/topic/cat.md`:

```markdown
---
id: topic:cat
uid: "a0000000000000000000000000000001"
kind: topic
title: cat
---
feline pet animal
```

`fixtures/similarity-corpus/topic/dog.md`:

```markdown
---
id: topic:dog
uid: "a0000000000000000000000000000002"
kind: topic
title: dog
---
canine pet animal
```

`fixtures/similarity-corpus/topic/car.md`:

```markdown
---
id: topic:car
uid: "a0000000000000000000000000000003"
kind: topic
title: car
---
automobile road vehicle
```

`fixtures/similarity-corpus/topic/truck.md`:

```markdown
---
id: topic:truck
uid: "a0000000000000000000000000000004"
kind: topic
title: truck
---
automobile road vehicle
```

- [ ] **Step 2: Create `fixtures/similarity.vectors.json` (hand-authored, 4-d)**

```json
{
  "documents": [
    {"id": "topic:cat",   "vector": [1.0, 0.1, 0.0, 0.0]},
    {"id": "topic:dog",   "vector": [0.9, 0.2, 0.0, 0.0]},
    {"id": "topic:car",   "vector": [0.0, 0.0, 1.0, 0.1]},
    {"id": "topic:truck", "vector": [0.0, 0.0, 0.9, 0.2]}
  ],
  "queries": [
    {"text": "pet",     "vector": [0.95, 0.15, 0.0, 0.0]},
    {"text": "vehicle", "vector": [0.0, 0.0, 0.95, 0.15]}
  ]
}
```

- [ ] **Step 3: Create the oracle generator `python/scripts/gen_similarity_oracle.py`**

```python
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from nodes.kernel.corpus import Corpus
from nodes.kernel.ranking import score_key
from nodes.kernel.similarity import Vector, embed_text

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "similarity-corpus"
VECTORS = FIXTURES / "similarity.vectors.json"
ORACLE = FIXTURES / "similarity.oracle.json"


class LookupEmbedder:
    cache_namespace = "fixture-v1"

    def __init__(self, table: dict[str, Vector]) -> None:
        self._table = table

    def embed(self, texts: list[str]) -> list[Vector]:
        return [self._table[t] for t in texts]


def build_table(data: dict, nodes: list) -> dict[str, Vector]:
    by_id = {d["id"]: tuple(d["vector"]) for d in data["documents"]}
    table: dict[str, Vector] = {embed_text(n): by_id[n.id] for n in nodes}
    for q in data["queries"]:
        table[q["text"]] = tuple(q["vector"])
    return table


def _hits(hits) -> list[dict]:
    return [{"id": h.id, "score": score_key(h.score)} for h in hits]


def main() -> None:
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "similarity-corpus"
        shutil.copytree(CORPUS, dst)
        nodes = Corpus(dst).all()  # plain read, no embedder
        emb = LookupEmbedder(build_table(data, nodes))
        corpus = Corpus(dst, embedder=emb)
        cases = {
            "similar": [{"ref": d["id"], "hits": _hits(corpus.similar(d["id"]))} for d in data["documents"]],
            "query_vector": [
                {"text": q["text"], "hits": _hits(corpus.query_vector(tuple(q["vector"])))}
                for q in data["queries"]
            ],
            "similar_text": [
                {"text": q["text"], "hits": _hits(corpus.similar_text(q["text"]))} for q in data["queries"]
            ],
        }
    ORACLE.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Generate the oracle**

Run: `rtk uv run python scripts/gen_similarity_oracle.py`
Expected: writes `fixtures/similarity.oracle.json`. Open it and sanity-check: `similar` for `topic:cat` ranks `topic:dog` first; `query_vector` for `"vehicle"` ranks `topic:car`/`topic:truck` above `topic:cat`/`topic:dog`.

- [ ] **Step 5: Write the parity test**

Create `python/tests/test_similarity_parity.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

from nodes.kernel.corpus import Corpus
from nodes.kernel.ranking import score_key
from nodes.kernel.similarity import Vector, embed_text

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "similarity-corpus"
VECTORS = FIXTURES / "similarity.vectors.json"
ORACLE = FIXTURES / "similarity.oracle.json"


class LookupEmbedder:
    cache_namespace = "fixture-v1"

    def __init__(self, table: dict[str, Vector]) -> None:
        self._table = table

    def embed(self, texts: list[str]) -> list[Vector]:
        return [self._table[t] for t in texts]


def _table(data: dict, nodes: list) -> dict[str, Vector]:
    by_id = {d["id"]: tuple(d["vector"]) for d in data["documents"]}
    table: dict[str, Vector] = {embed_text(n): by_id[n.id] for n in nodes}
    for q in data["queries"]:
        table[q["text"]] = tuple(q["vector"])
    return table


def _hits(hits) -> list[dict]:
    return [{"id": h.id, "score": score_key(h.score)} for h in hits]


def test_similarity_corpus_has_four_topics(tmp_path):
    dst = tmp_path / "similarity-corpus"
    shutil.copytree(CORPUS, dst)
    assert len(Corpus(dst).all()) == 4


def test_similarity_ranking_matches_committed_oracle(tmp_path):
    # Currency + cross-language freeze: Corpus similarity over the committed fixture
    # corpus + frozen vectors must reproduce the committed oracle exactly (ranked ids
    # + 6-dp scores). The later TypeScript port asserts the same fixtures + oracle.
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle["similar"] and oracle["query_vector"] and oracle["similar_text"]

    dst = tmp_path / "similarity-corpus"
    shutil.copytree(CORPUS, dst)
    nodes = Corpus(dst).all()
    # guard: every corpus node has a frozen document vector
    by_id = {d["id"]: d for d in data["documents"]}
    assert {n.id for n in nodes} == set(by_id)

    emb = LookupEmbedder(_table(data, nodes))
    corpus = Corpus(dst, embedder=emb)

    for case in oracle["similar"]:
        assert _hits(corpus.similar(case["ref"])) == case["hits"], case["ref"]
    for case in oracle["query_vector"]:
        vec = tuple(next(q for q in data["queries"] if q["text"] == case["text"])["vector"])
        assert _hits(corpus.query_vector(vec)) == case["hits"], case["text"]
    for case in oracle["similar_text"]:
        assert _hits(corpus.similar_text(case["text"])) == case["hits"], case["text"]
```

- [ ] **Step 6: Run the parity test + full suite + gates**

Run: `rtk uv run pytest tests/test_similarity_parity.py -q` — Expected: PASS.
Run: `rtk uv run pytest -q` — Expected: PASS (whole suite).
Run: `rtk uv run ruff check src tests` — Expected: clean.
Run: `rtk uv run pyright src` — Expected: clean.

- [ ] **Step 7: Document in `docs/format.md`**

Update the existing "Known kernel limitations"/persistence note if present, and append a new section after the full-text search section:

```markdown
## Similarity / embedding index (derived index)

The Python kernel ships a third derived index beside the structural `Index` and
the BM25F `SearchIndex`: an in-memory cosine-similarity index over dense
embeddings (`nodes.kernel.similarity`). It is **opt-in** — pass an embedder:
`Corpus(root, embedder=...)`. Without one, the vector index is not built and the
similarity APIs raise `EmbedderRequiredError`.

- **Seam.** The kernel ships no model. An `Embedder` protocol
  (`cache_namespace: str`, `embed(texts) -> list[Vector]`) is injected by the
  caller. One vector per node from `embed_text(node) = f"{title}\n\n{body}"`.
- **Vectors.** Stored L2-normalized in memory (cosine = dot product); raw
  embedder output is persisted in a content-addressed, per-namespace cache under
  `<root>/.nodes-index/vectors/<namespace>/<sha256>.json` (git-ignored,
  disposable, atomic writes). A warm cache needs no model call for already-seen
  content.
- **Queries.** `Corpus.similar(ref, k=None)` (excludes the node itself),
  `Corpus.query_vector(vec, k=None)`, `Corpus.similar_text(text, k=None)`.
  Results are `SimilarHit`s (`id`, `uid`, `score`), sorted by a 6-decimal half-up
  `score_key` (shared with search, in `nodes.kernel.ranking`) then `id`. Exact
  brute-force cosine — no ANN.
- **Determinism & failure.** The index is bound to one embedder namespace and one
  dimension; mismatches, zero-norm, and non-finite vectors fail early. `add`
  validates the vector before any disk write (no partial corpus state).
- **Parity.** A fixture corpus (`fixtures/similarity-corpus/`), frozen low-dim
  vectors (`fixtures/similarity.vectors.json`), and a ranking oracle
  (`fixtures/similarity.oracle.json`) pin ranked ids and 6-dp scores. Because
  model embeddings are not portable across languages, the *vectors* are frozen
  (not computed); both languages inject a lookup embedder over the frozen vectors
  and assert identical rankings. On-disk index persistence and the TypeScript
  port are later plans.
```

- [ ] **Step 8: Commit**

```bash
rtk git add fixtures/similarity-corpus fixtures/similarity.vectors.json \
  fixtures/similarity.oracle.json python/scripts/gen_similarity_oracle.py \
  python/tests/test_similarity_parity.py docs/format.md
rtk git commit -m "test(similarity): frozen parity fixtures + oracle; docs"
```

---

## Notes for the executor

- **Test embedders are doubles, not fixtures to freeze.** The `DictEmbedder` /
  `LookupEmbedder` classes defined inside test files and the oracle script are
  deterministic stand-ins for a real model; only the committed vector fixtures are
  the frozen artifact.
- **Never edit the committed fixtures** (`fixtures/similarity-corpus/`,
  `fixtures/similarity.vectors.json`, `fixtures/similarity.oracle.json`) after Task
  7 except by regenerating the oracle via the script. They are the cross-language
  contract for the future TS port.
- **`similarity.py` must not import `search.py`** — both share only `ranking.py`.
