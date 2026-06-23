# Nodes Index Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the three derived indexes (`Index`, `SearchIndex`, `VectorIndex`) to a disposable on-disk snapshot so constructing a `Corpus` over an unchanged corpus skips the full parse + re-index pass, reconciling only what changed on disk.

**Architecture:** A new `snapshot.py` module owns all snapshot I/O — the file location, atomic write, the version/lang gate, integrity validation, a byte-level file walk, and the `path → (sha256, uid)` manifest. The three index classes stay pure data and gain only `to_dict()`/`from_dict()`. `Corpus.__init__` loads + reconciles (or full-rebuilds); `Corpus.flush_index()` writes; `Corpus` maintains an in-memory manifest across every write path. The snapshot is never authoritative — every load reconciles against current file hashes, so a stale/absent snapshot costs only time.

**Tech Stack:** Python ≥3.11, pydantic v2, pyyaml, stdlib `hashlib`/`json`/`os`. Tests: pytest. Lint: ruff (line-length 120). Types: pyright (basic). All commands run through the `rtk` wrapper from `~/d/nodes/python`.

## Global Constraints

- The snapshot is a **disposable, private, per-language cache**; files are the single source of truth. Every load reconciles the snapshot against the current files by content hash, so a stale or absent snapshot never affects correctness, only speed.
- Snapshot file: `<root>/.nodes-index/snapshot.py.json` (the `.nodes-index/` directory is already git-ignored). `SNAPSHOT_SCHEMA_VERSION = 1`; `lang` field is `"py"`. The TS port (later) uses `snapshot.ts.json`; Python never reads a non-`py` snapshot.
- The manifest is **always a byte-level file-walk product** — hash the *actual on-disk bytes*, in **both** reconcile and full rebuild. The load path never hashes `node_to_markdown(node)`.
- The in-memory manifest is maintained on every write path: `add`/`rename` set the entry from `sha256(node_to_markdown(node))` (those bytes are exactly what `write_file` wrote); `delete` removes it; `rename` also re-hashes every rewritten referrer at its unchanged path and removes the old path entry when the renamed node moves.
- **Construction never writes the snapshot.** (The raw `VectorCache` may still write under `.nodes-index/vectors/` during `VectorIndex.build`.)
- **Silent fallback → full rebuild** is scoped strictly to snapshot-cache unusability detected inside `load_snapshot()`: missing file, invalid JSON, `version`/`lang` mismatch, integrity failure, or (embedder configured) a missing/mismatched `vectors` section. Any error from reading/parsing corpus files or from the collision contract — during either rebuild or reconcile — **propagates**. `flush_index()` I/O errors propagate.
- **Reconcile enforces the full `build()` collision contract**, not just `assert_addable`: after planned drops, every changed/added uid must be absent before insertion, and duplicate uids among upserts raise `CollisionError`.
- **Integrity (bijection) rules:** manifest has no duplicate uids/paths; structural `entries` uid-set == manifest uid-set; search `lengths` keys == `id_by_uid` keys == manifest uid-set, and every postings-bucket uid ∈ that set; vectors (only when an embedder is configured) `vectors` == `id_by_uid` == `hash_by_uid` keys == manifest uid-set, `namespace` == embedder's `cache_namespace`, `dim` is `int | null` (`null` only with zero stored vectors; otherwise every vector has length `dim`).
- **No-embedder mode** ignores the `vectors` section entirely — it is not deserialized or validated.
- Atomic writes: write to `<path>.tmp`, then `os.replace`. Manifest paths are **root-relative POSIX** strings.
- **Shared-`Relation` identity invariant (structural):** the source and target `OutRef`s of one relation must share a single `Relation` instance (`in_refs` dedup keys on `id(relation)`). Serialize each relation once per entry and replay extraction (`_out_refs_from`) on load.
- Gate (run from `~/d/nodes/python`): `rtk uv run pytest -q`, `rtk uv run ruff check src tests`, `rtk uv run pyright src`.

---

## File Structure

- **Create** `python/src/nodes/kernel/snapshot.py` — `SNAPSHOT_SCHEMA_VERSION`, `SNAPSHOT_LANG`, `snapshot_path`, `hash_bytes`, `CorpusFile`, `iter_corpus_files`, `ManifestEntry`, atomic JSON write, `Snapshot`, `write_snapshot`, `load_snapshot`.
- **Modify** `python/src/nodes/kernel/index.py` — refactor extraction into `_out_refs_from`; add `IndexEntry.membership`; add `Index.to_dict`/`Index.from_dict`.
- **Modify** `python/src/nodes/kernel/search.py` — add `SearchIndex.to_dict`/`from_dict`.
- **Modify** `python/src/nodes/kernel/similarity.py` — add `VectorIndex.to_dict`/`from_dict`.
- **Modify** `python/src/nodes/kernel/corpus.py` — load/reconcile/full-rebuild in `__init__`; `flush_index()`; manifest maintenance in `add`/`delete`/`rename`.
- **Modify** `docs/format.md` — index-persistence subsection.
- **Tests:** `test_snapshot_io.py`, `test_search_snapshot.py`, `test_vector_snapshot.py`, `test_index_snapshot.py`, `test_snapshot_load.py`, `test_corpus_persistence.py`, `test_corpus_persistence_rename.py`.

---

### Task 1: Snapshot I/O foundations

**Files:**
- Create: `python/src/nodes/kernel/snapshot.py`
- Test: `python/tests/test_snapshot_io.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `SNAPSHOT_SCHEMA_VERSION: int = 1`, `SNAPSHOT_LANG: str = "py"`
  - `snapshot_path(root: Path | str) -> Path` → `<root>/.nodes-index/snapshot.py.json`
  - `hash_bytes(data: bytes) -> str` → 64-char lowercase sha256 hexdigest
  - `@dataclass(frozen=True) CorpusFile{ path: str, data: bytes, sha256: str }`
  - `iter_corpus_files(root: Path | str) -> list[CorpusFile]` (sorted by path; `path` is root-relative POSIX)
  - `@dataclass(frozen=True) ManifestEntry{ path: str, sha256: str, uid: str }`
  - `write_json_atomic(path: Path, obj: dict) -> None`
  - `read_json(path: Path) -> dict | None` (returns `None` if file missing; raises on invalid JSON)

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_snapshot_io.py`:

```python
from __future__ import annotations

import hashlib

from nodes.kernel.snapshot import (
    SNAPSHOT_LANG,
    SNAPSHOT_SCHEMA_VERSION,
    CorpusFile,
    ManifestEntry,
    hash_bytes,
    iter_corpus_files,
    read_json,
    snapshot_path,
    write_json_atomic,
)


def test_constants():
    assert SNAPSHOT_SCHEMA_VERSION == 1
    assert SNAPSHOT_LANG == "py"


def test_snapshot_path(tmp_path):
    assert snapshot_path(tmp_path) == tmp_path / ".nodes-index" / "snapshot.py.json"


def test_hash_bytes_is_sha256_hex():
    assert hash_bytes(b"hello") == hashlib.sha256(b"hello").hexdigest()
    assert len(hash_bytes(b"")) == 64


def test_iter_corpus_files_sorted_relative_posix_with_hash(tmp_path):
    (tmp_path / "topic").mkdir()
    (tmp_path / "gene").mkdir()
    (tmp_path / "topic" / "b.md").write_bytes(b"BBB")
    (tmp_path / "gene" / "a.md").write_bytes(b"AAA")
    (tmp_path / "ignore.txt").write_bytes(b"nope")
    files = iter_corpus_files(tmp_path)
    assert [f.path for f in files] == ["gene/a.md", "topic/b.md"]
    assert files[0] == CorpusFile(path="gene/a.md", data=b"AAA", sha256=hash_bytes(b"AAA"))


def test_write_json_atomic_round_trip_and_no_tmp_left(tmp_path):
    p = snapshot_path(tmp_path)
    write_json_atomic(p, {"version": 1, "x": [1, 2]})
    assert read_json(p) == {"version": 1, "x": [1, 2]}
    assert not (p.parent / (p.name + ".tmp")).exists()


def test_read_json_missing_returns_none(tmp_path):
    assert read_json(snapshot_path(tmp_path)) is None


def test_manifest_entry_is_frozen():
    e = ManifestEntry(path="a.md", sha256="0" * 64, uid="u1")
    assert (e.path, e.sha256, e.uid) == ("a.md", "0" * 64, "u1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_snapshot_io.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.snapshot'`.

- [ ] **Step 3: Write the implementation**

Create `python/src/nodes/kernel/snapshot.py`:

```python
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_LANG = "py"


def snapshot_path(root: Path | str) -> Path:
    return Path(root) / ".nodes-index" / "snapshot.py.json"


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class CorpusFile:
    path: str  # root-relative POSIX
    data: bytes
    sha256: str


def iter_corpus_files(root: Path | str) -> list[CorpusFile]:
    root = Path(root)
    files: list[CorpusFile] = []
    for p in sorted(root.rglob("*.md")):
        data = p.read_bytes()
        files.append(CorpusFile(path=p.relative_to(root).as_posix(), data=data, sha256=hash_bytes(data)))
    return files


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    sha256: str
    uid: str


def write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, allow_nan=False)
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk uv run pytest tests/test_snapshot_io.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Run gate and commit**

Run: `rtk uv run ruff check src tests` (clean), `rtk uv run pyright src` (clean).

```bash
cd python && rtk git add src/nodes/kernel/snapshot.py tests/test_snapshot_io.py
rtk git commit -m "feat(persistence): snapshot I/O foundations — file walk, hashing, atomic JSON"
```

---

### Task 2: SearchIndex serialization

**Files:**
- Modify: `python/src/nodes/kernel/search.py`
- Test: `python/tests/test_search_snapshot.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `SearchIndex.to_dict(self) -> dict` → `{"postings": {term: {uid: [title_tf, body_tf]}}, "lengths": {uid: [title_len, body_len]}, "id_by_uid": {uid: id}}`
  - `SearchIndex.from_dict(cls, d: dict) -> SearchIndex` — rebuilds, recomputing `_total_title`/`_total_body`; raises `ValueError` on internal inconsistency (`lengths` keys ≠ `id_by_uid` keys, or a postings uid absent from `lengths`).

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_search_snapshot.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.node import Node
from nodes.kernel.search import SearchIndex


def _corpus() -> list[Node]:
    return [
        Node(id="topic:alpha", kind="topic", title="Alpha Beta", body="alpha gamma gamma"),
        Node(id="topic:delta", kind="topic", title="Delta", body="beta delta"),
        Node(id="topic:empty", kind="topic", title="", body=""),
    ]


def test_round_trip_preserves_search_results():
    idx = SearchIndex.build(_corpus())
    restored = SearchIndex.from_dict(idx.to_dict())
    for query in ("alpha", "beta", "gamma", "delta", "nothing"):
        assert idx.search(query) == restored.search(query)


def test_round_trip_preserves_internal_state():
    idx = SearchIndex.build(_corpus())
    restored = SearchIndex.from_dict(idx.to_dict())
    assert restored.postings == idx.postings
    assert restored.lengths == idx.lengths
    assert restored.id_by_uid == idx.id_by_uid
    assert restored._total_title == idx._total_title
    assert restored._total_body == idx._total_body


def test_empty_index_round_trips():
    idx = SearchIndex.build([])
    restored = SearchIndex.from_dict(idx.to_dict())
    assert restored.n == 0
    assert restored.search("anything") == []


def test_from_dict_rejects_length_id_mismatch():
    with pytest.raises(ValueError):
        SearchIndex.from_dict({"postings": {}, "lengths": {"u1": [1, 0]}, "id_by_uid": {}})


def test_from_dict_rejects_stale_posting_uid():
    with pytest.raises(ValueError):
        SearchIndex.from_dict(
            {"postings": {"x": {"ghost": [1, 0]}}, "lengths": {"u1": [1, 0]}, "id_by_uid": {"u1": "topic:a"}}
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_search_snapshot.py -q`
Expected: FAIL — `AttributeError: type object 'SearchIndex' has no attribute 'from_dict'`.

- [ ] **Step 3: Write the implementation**

In `python/src/nodes/kernel/search.py`, add these two methods to `class SearchIndex` (e.g. after `remove`):

```python
    def to_dict(self) -> dict:
        return {
            "postings": {
                term: {uid: [tf[0], tf[1]] for uid, tf in docs.items()}
                for term, docs in self.postings.items()
            },
            "lengths": {uid: [lens[0], lens[1]] for uid, lens in self.lengths.items()},
            "id_by_uid": dict(self.id_by_uid),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SearchIndex":
        idx = cls()
        lengths = {uid: (int(v[0]), int(v[1])) for uid, v in d["lengths"].items()}
        id_by_uid = dict(d["id_by_uid"])
        if set(lengths) != set(id_by_uid):
            raise ValueError("search snapshot: lengths/id_by_uid uid sets differ")
        postings: dict[str, dict[str, tuple[int, int]]] = {}
        for term, docs in d["postings"].items():
            bucket: dict[str, tuple[int, int]] = {}
            for uid, tf in docs.items():
                if uid not in lengths:
                    raise ValueError(f"search snapshot: posting uid {uid!r} absent from lengths")
                bucket[uid] = (int(tf[0]), int(tf[1]))
            postings[term] = bucket
        idx.postings = postings
        idx.lengths = lengths
        idx.id_by_uid = id_by_uid
        idx._total_title = sum(lens[0] for lens in lengths.values())
        idx._total_body = sum(lens[1] for lens in lengths.values())
        return idx
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk uv run pytest tests/test_search_snapshot.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Run gate and commit**

Run: `rtk uv run ruff check src tests`, `rtk uv run pyright src`.

```bash
cd python && rtk git add src/nodes/kernel/search.py tests/test_search_snapshot.py
rtk git commit -m "feat(persistence): SearchIndex to_dict/from_dict with self-consistency checks"
```

---

### Task 3: VectorIndex serialization

**Files:**
- Modify: `python/src/nodes/kernel/similarity.py`
- Test: `python/tests/test_vector_snapshot.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `VectorIndex.to_dict(self) -> dict` → `{"namespace": str | None, "dim": int | None, "vectors": {uid: [float,...]}, "id_by_uid": {uid: id}, "hash_by_uid": {uid: hash}}`
  - `VectorIndex.from_dict(cls, d: dict) -> VectorIndex` — rebuilds verbatim (stored vectors are already L2-normalized; no re-normalization). Raises `ValueError` if the three uid maps differ, if `dim` is non-int while vectors are present, if a vector's length ≠ `dim`, or if `dim` is non-null while there are zero vectors.

**Reference (current `VectorIndex` attributes, from `similarity.py`):** `vectors: dict[str, Vector]`, `id_by_uid: dict[str, str]`, `hash_by_uid: dict[str, str]`, `dim: int | None`, `namespace: str | None`. `Vector = tuple[float, ...]`.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_vector_snapshot.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.node import Node
from nodes.kernel.similarity import VectorCache, VectorIndex


class ListEmbedder:
    """Test embedder: looks up a frozen vector per embed_text(node) prefix."""

    cache_namespace = "test-ns"

    def __init__(self, table: dict[str, list[float]]) -> None:
        self.table = table

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.table[t.split("\n", 1)[0]] for t in texts]


def _index(tmp_path) -> VectorIndex:
    emb = ListEmbedder({"cat": [1.0, 0.1, 0.0], "dog": [0.9, 0.2, 0.0]})
    cache = VectorCache(tmp_path)
    nodes = [Node(id="topic:cat", kind="topic", title="cat"), Node(id="topic:dog", kind="topic", title="dog")]
    return VectorIndex.build(nodes, emb, cache)


def test_round_trip_preserves_query_results(tmp_path):
    idx = _index(tmp_path)
    restored = VectorIndex.from_dict(idx.to_dict())
    assert restored.dim == idx.dim
    assert restored.namespace == idx.namespace
    assert restored.query_vector((1.0, 0.0, 0.0)) == idx.query_vector((1.0, 0.0, 0.0))


def test_round_trip_preserves_internal_maps(tmp_path):
    idx = _index(tmp_path)
    restored = VectorIndex.from_dict(idx.to_dict())
    assert restored.vectors == idx.vectors
    assert restored.id_by_uid == idx.id_by_uid
    assert restored.hash_by_uid == idx.hash_by_uid


def test_empty_embedder_index_dim_null_round_trips():
    idx = VectorIndex.build([], ListEmbedder({}), VectorCache("/tmp/unused-cache"))
    d = idx.to_dict()
    assert d["dim"] is None
    assert d["namespace"] == "test-ns"
    restored = VectorIndex.from_dict(d)
    assert restored.dim is None
    assert restored.namespace == "test-ns"
    assert restored.vectors == {}


def test_from_dict_rejects_uid_map_mismatch():
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {"namespace": "n", "dim": 2, "vectors": {"u1": [1.0, 0.0]}, "id_by_uid": {}, "hash_by_uid": {"u1": "h"}}
        )


def test_from_dict_rejects_dim_length_mismatch():
    with pytest.raises(ValueError):
        VectorIndex.from_dict(
            {"namespace": "n", "dim": 3, "vectors": {"u1": [1.0, 0.0]},
             "id_by_uid": {"u1": "topic:a"}, "hash_by_uid": {"u1": "h"}}
        )


def test_from_dict_rejects_non_null_dim_when_empty():
    with pytest.raises(ValueError):
        VectorIndex.from_dict({"namespace": "n", "dim": 2, "vectors": {}, "id_by_uid": {}, "hash_by_uid": {}})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_vector_snapshot.py -q`
Expected: FAIL — `AttributeError: type object 'VectorIndex' has no attribute 'from_dict'`.

- [ ] **Step 3: Write the implementation**

In `python/src/nodes/kernel/similarity.py`, add these two methods to `class VectorIndex` (e.g. after `remove`):

```python
    def to_dict(self) -> dict:
        return {
            "namespace": self.namespace,
            "dim": self.dim,
            "vectors": {uid: list(vec) for uid, vec in self.vectors.items()},
            "id_by_uid": dict(self.id_by_uid),
            "hash_by_uid": dict(self.hash_by_uid),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VectorIndex":
        idx = cls()
        idx.namespace = d["namespace"]
        vectors = {uid: tuple(float(x) for x in vec) for uid, vec in d["vectors"].items()}
        id_by_uid = dict(d["id_by_uid"])
        hash_by_uid = dict(d["hash_by_uid"])
        if not (set(vectors) == set(id_by_uid) == set(hash_by_uid)):
            raise ValueError("vector snapshot: vectors/id_by_uid/hash_by_uid uid sets differ")
        dim = d["dim"]
        if vectors:
            if not isinstance(dim, int) or isinstance(dim, bool):
                raise ValueError("vector snapshot: dim must be an int when vectors are present")
            for vec in vectors.values():
                if len(vec) != dim:
                    raise ValueError("vector snapshot: vector length != dim")
        elif dim is not None:
            raise ValueError("vector snapshot: dim must be null when there are no vectors")
        idx.vectors = vectors
        idx.id_by_uid = id_by_uid
        idx.hash_by_uid = hash_by_uid
        idx.dim = dim
        return idx
```

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk uv run pytest tests/test_vector_snapshot.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Run gate and commit**

Run: `rtk uv run ruff check src tests`, `rtk uv run pyright src`.

```bash
cd python && rtk git add src/nodes/kernel/similarity.py tests/test_vector_snapshot.py
rtk git commit -m "feat(persistence): VectorIndex to_dict/from_dict (dim int|null, uid-map checks)"
```

---

### Task 4: Structural Index serialization

**Files:**
- Modify: `python/src/nodes/kernel/index.py`
- Test: `python/tests/test_index_snapshot.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - Refactor: `_out_refs_from(relations: list[Relation], membership: object) -> list[OutRef]` (extraction body); `_extract_out_refs(node)` delegates to it.
  - `IndexEntry` gains field `membership: dict | None = None`.
  - `Index.to_dict(self) -> dict` → `{"entries": [{"uid","id","kind","deprecated_ids":[...],"relations":[{source,predicate,target,directed,weight,attrs}],"membership": dict | None}]}`
  - `Index.from_dict(cls, d: dict) -> Index` — replays extraction via `_out_refs_from`, rebuilding `by_uid`/`id_to_uid`/`deprecated_to_uid`/`in_refs`; raises `ValueError` on a duplicate uid within `entries`.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_index_snapshot.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.index import Index
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to

# Reuse the equivalence normalizer that already pins structural state.
from tests.test_index_rebuild_equivalence import _normalize


def _corpus() -> list[Node]:
    return [
        Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")]),
        Node(id="topic:b", kind="topic", title="B"),
        Node(id="graph:g", kind="graph", title="G", facets={"membership": {
            "shape": "graph",
            "members": ["topic:a", "topic:b"],
            "edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}],
        }}),
    ]


def test_round_trip_equals_fresh_build():
    idx = Index.build(_corpus())
    restored = Index.from_dict(idx.to_dict())
    assert _normalize(restored) == _normalize(idx)


def test_round_trip_preserves_inbound_and_dangling_dedup():
    # One relation yields a source+target OutRef sharing a single Relation instance;
    # ensure outbound/dangling queries match a fresh build after a round trip (the
    # shared-Relation identity that in_refs dedup relies on must survive from_dict).
    nodes = [
        Node(id="topic:a", kind="topic", title="A",
             relations=[relates_to("topic:a", "topic:missing")]),
    ]
    idx = Index.build(nodes)
    restored = Index.from_dict(idx.to_dict())
    a_uid = restored.id_to_uid["topic:a"]
    assert restored.outbound_edges(a_uid) == idx.outbound_edges(a_uid)
    assert len(restored.dangling_edges()) == len(idx.dangling_edges()) == 1


def test_empty_index_round_trips():
    idx = Index.build([])
    restored = Index.from_dict(idx.to_dict())
    assert restored.by_uid == {}


def test_from_dict_rejects_duplicate_uid():
    idx = Index.build([Node(id="topic:a", kind="topic", title="A")])
    d = idx.to_dict()
    d["entries"].append(dict(d["entries"][0]))  # duplicate uid
    with pytest.raises(ValueError):
        Index.from_dict(d)


def test_extract_out_refs_still_works_after_refactor():
    # Guards the _out_refs_from refactor: existing build path unchanged.
    idx = Index.build(_corpus())
    g_uid = idx.id_to_uid["graph:g"]
    assert {o.role for o in idx.by_uid[g_uid].out_refs} >= {
        "membership_member", "membership_edge_source", "membership_edge_target",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_index_snapshot.py -q`
Expected: FAIL — `AttributeError: type object 'Index' has no attribute 'to_dict'`.

- [ ] **Step 3a: Refactor extraction (pure, no behavior change)**

In `python/src/nodes/kernel/index.py`, replace the body of `_extract_out_refs` with a delegating call and a new `_out_refs_from` helper. Replace:

```python
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
```

with:

```python
def _out_refs_from(relations: list[Relation], membership: object) -> list[OutRef]:
    refs: list[OutRef] = []
    for rel in relations:
        refs.append(OutRef(ref=rel.source, role="relation_source", relation=rel))
        refs.append(OutRef(ref=rel.target, role="relation_target", relation=rel))
    if isinstance(membership, dict):
        members = membership.get("members")
        if isinstance(members, list):
            for m in members:
                refs.append(OutRef(ref=m, role="membership_member"))
        elif isinstance(members, dict):
            for v in members.values():
                refs.append(OutRef(ref=v, role="membership_member"))
        for edge in membership.get("edges", []) or []:
            if isinstance(edge, dict):
                if "source" in edge:
                    refs.append(OutRef(ref=edge["source"], role="membership_edge_source"))
                if "target" in edge:
                    refs.append(OutRef(ref=edge["target"], role="membership_edge_target"))
    return refs


def _extract_out_refs(node: Node) -> list[OutRef]:
    return _out_refs_from(node.relations, node.facets.get(MEMBERSHIP))
```

`_out_refs_from` references `Relation`; add it to the existing import: `from nodes.kernel.relations import Relation`.

- [ ] **Step 3b: Add the `membership` field and store it in `upsert`**

Change `IndexEntry` to add a `membership` field:

```python
@dataclass
class IndexEntry:
    uid: str
    id: str
    kind: str
    deprecated_ids: frozenset[str]
    out_refs: list[OutRef]
    membership: dict | None = None
```

In `Index.upsert`, set it when constructing the entry:

```python
        entry = IndexEntry(
            uid=node.uid,
            id=node.id,
            kind=node.kind,
            deprecated_ids=frozenset(node.deprecated_ids),
            out_refs=_extract_out_refs(node),
            membership=node.facets.get(MEMBERSHIP),
        )
```

- [ ] **Step 3c: Add `to_dict`/`from_dict`**

Add these methods to `class Index` (e.g. after `remove`):

```python
    def to_dict(self) -> dict:
        entries = []
        for entry in self.by_uid.values():
            relations = [
                {
                    "source": o.relation.source,
                    "predicate": o.relation.predicate,
                    "target": o.relation.target,
                    "directed": o.relation.directed,
                    "weight": o.relation.weight,
                    "attrs": o.relation.attrs,
                }
                for o in entry.out_refs
                if o.role == "relation_source" and o.relation is not None
            ]
            entries.append({
                "uid": entry.uid,
                "id": entry.id,
                "kind": entry.kind,
                "deprecated_ids": sorted(entry.deprecated_ids),
                "relations": relations,
                "membership": entry.membership,
            })
        return {"entries": entries}

    @classmethod
    def from_dict(cls, d: dict) -> "Index":
        idx = cls()
        for raw in d["entries"]:
            uid = raw["uid"]
            if uid in idx.by_uid:
                raise ValueError(f"structural snapshot: duplicate uid {uid!r}")
            relations = [Relation(**r) for r in raw["relations"]]
            membership = raw["membership"]
            out_refs = _out_refs_from(relations, membership)
            entry = IndexEntry(
                uid=uid,
                id=raw["id"],
                kind=raw["kind"],
                deprecated_ids=frozenset(raw["deprecated_ids"]),
                out_refs=out_refs,
                membership=membership,
            )
            idx.by_uid[uid] = entry
            idx.id_to_uid[entry.id] = uid
            for dep in entry.deprecated_ids:
                idx.deprecated_to_uid[dep] = uid
            for oref in out_refs:
                idx.in_refs.setdefault(oref.ref, []).append(InRef(source_uid=uid, out_ref=oref))
        return idx
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_index_snapshot.py tests/test_index_rebuild_equivalence.py tests/test_index.py -q`
Expected: PASS (new file 5 tests; the existing index suites still green — guards the refactor).

- [ ] **Step 5: Run gate and commit**

Run: `rtk uv run ruff check src tests`, `rtk uv run pyright src`.

```bash
cd python && rtk git add src/nodes/kernel/index.py tests/test_index_snapshot.py
rtk git commit -m "feat(persistence): structural Index to_dict/from_dict via shared extraction replay"
```

---

### Task 5: Snapshot document — write + load with integrity gate

**Files:**
- Modify: `python/src/nodes/kernel/snapshot.py`
- Test: `python/tests/test_snapshot_load.py`

**Interfaces:**
- Consumes: Task 1 (`snapshot_path`, `ManifestEntry`, `write_json_atomic`, `read_json`, `SNAPSHOT_SCHEMA_VERSION`, `SNAPSHOT_LANG`); Task 2 (`SearchIndex.to_dict/from_dict`); Task 3 (`VectorIndex.to_dict/from_dict`); Task 4 (`Index.to_dict/from_dict`).
- Produces:
  - `@dataclass Snapshot{ manifest: list[ManifestEntry], index: Index, search_index: SearchIndex, vector_index: VectorIndex | None }`
  - `write_snapshot(root, manifest: list[ManifestEntry], index: Index, search_index: SearchIndex, vector_index: VectorIndex | None) -> None`
  - `load_snapshot(root, embedder_namespace: str | None) -> Snapshot | None` — returns `None` on any cache-unusability (missing/invalid JSON, `version`/`lang` mismatch, manifest dup uid/path, malformed sections, cross-section bijection failure, or — when `embedder_namespace is not None` — a missing/namespace-mismatched/uid-mismatched `vectors` section). Never parses corpus files.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_snapshot_load.py`:

```python
from __future__ import annotations

from nodes.kernel.index import Index
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to
from nodes.kernel.search import SearchIndex
from nodes.kernel.snapshot import (
    ManifestEntry,
    Snapshot,
    load_snapshot,
    read_json,
    snapshot_path,
    write_json_atomic,
    write_snapshot,
)


def _nodes() -> list[Node]:
    return [
        Node(id="topic:a", kind="topic", title="A", body="alpha", relations=[relates_to("topic:a", "topic:b")]),
        Node(id="topic:b", kind="topic", title="B", body="beta"),
    ]


def _manifest(nodes) -> list[ManifestEntry]:
    return [ManifestEntry(path=f"topic/{n.id.split(':')[1]}.md", sha256=f"{i:064d}", uid=n.uid)
            for i, n in enumerate(nodes)]


def _write(tmp_path, *, embedder=False):
    nodes = _nodes()
    manifest = _manifest(nodes)
    index = Index.build(nodes)
    search = SearchIndex.build(nodes)
    write_snapshot(tmp_path, manifest, index, search, None)
    return nodes, manifest


def test_write_then_load_round_trips_structural_and_search(tmp_path):
    nodes, manifest = _write(tmp_path)
    snap = load_snapshot(tmp_path, None)
    assert isinstance(snap, Snapshot)
    assert {m.uid for m in snap.manifest} == {n.uid for n in nodes}
    assert set(snap.index.by_uid) == {n.uid for n in nodes}
    assert snap.vector_index is None


def test_missing_file_returns_none(tmp_path):
    assert load_snapshot(tmp_path, None) is None


def test_bad_version_returns_none(tmp_path):
    _write(tmp_path)
    doc = read_json(snapshot_path(tmp_path))
    doc["version"] = 999
    write_json_atomic(snapshot_path(tmp_path), doc)
    assert load_snapshot(tmp_path, None) is None


def test_bad_lang_returns_none(tmp_path):
    _write(tmp_path)
    doc = read_json(snapshot_path(tmp_path))
    doc["lang"] = "ts"
    write_json_atomic(snapshot_path(tmp_path), doc)
    assert load_snapshot(tmp_path, None) is None


def test_corrupt_json_returns_none(tmp_path):
    p = snapshot_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    assert load_snapshot(tmp_path, None) is None


def test_duplicate_manifest_uid_returns_none(tmp_path):
    _write(tmp_path)
    doc = read_json(snapshot_path(tmp_path))
    doc["manifest"].append(dict(doc["manifest"][0]))  # same uid + path twice
    write_json_atomic(snapshot_path(tmp_path), doc)
    assert load_snapshot(tmp_path, None) is None


def test_manifest_section_bijection_violation_returns_none(tmp_path):
    _write(tmp_path)
    doc = read_json(snapshot_path(tmp_path))
    doc["manifest"].append({"path": "topic/ghost.md", "sha256": "f" * 64, "uid": "ghost"})
    write_json_atomic(snapshot_path(tmp_path), doc)
    assert load_snapshot(tmp_path, None) is None  # manifest uid not in structural/search


def test_no_embedder_ignores_corrupt_vectors_section(tmp_path):
    _write(tmp_path)
    doc = read_json(snapshot_path(tmp_path))
    doc["vectors"] = {"garbage": True}
    write_json_atomic(snapshot_path(tmp_path), doc)
    assert load_snapshot(tmp_path, None) is not None  # vectors irrelevant without an embedder


def test_embedder_required_but_vectors_missing_returns_none(tmp_path):
    _write(tmp_path)  # wrote vectors=None
    assert load_snapshot(tmp_path, "some-ns") is None


def test_embedder_namespace_mismatch_returns_none(tmp_path):
    nodes = _nodes()
    manifest = _manifest(nodes)
    index = Index.build(nodes)
    search = SearchIndex.build(nodes)
    # Hand-craft a vectors section with the wrong namespace.
    write_snapshot(tmp_path, manifest, index, search, None)
    doc = read_json(snapshot_path(tmp_path))
    doc["vectors"] = {"namespace": "other-ns", "dim": None, "vectors": {}, "id_by_uid": {}, "hash_by_uid": {}}
    write_json_atomic(snapshot_path(tmp_path), doc)
    assert load_snapshot(tmp_path, "expected-ns") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_snapshot_load.py -q`
Expected: FAIL — `ImportError: cannot import name 'Snapshot' from 'nodes.kernel.snapshot'`.

- [ ] **Step 3: Write the implementation**

In `python/src/nodes/kernel/snapshot.py`, add imports at the top (after the stdlib imports):

```python
from nodes.kernel.index import Index
from nodes.kernel.search import SearchIndex
from nodes.kernel.similarity import VectorIndex
```

Append:

```python
@dataclass
class Snapshot:
    manifest: list[ManifestEntry]
    index: Index
    search_index: SearchIndex
    vector_index: VectorIndex | None


def write_snapshot(
    root: Path | str,
    manifest: list[ManifestEntry],
    index: Index,
    search_index: SearchIndex,
    vector_index: VectorIndex | None,
) -> None:
    doc = {
        "version": SNAPSHOT_SCHEMA_VERSION,
        "lang": SNAPSHOT_LANG,
        "manifest": [{"path": m.path, "sha256": m.sha256, "uid": m.uid} for m in manifest],
        "structural": index.to_dict(),
        "search": search_index.to_dict(),
        "vectors": vector_index.to_dict() if vector_index is not None else None,
    }
    write_json_atomic(snapshot_path(root), doc)


def _parse_manifest(raw: object) -> list[ManifestEntry]:
    if not isinstance(raw, list):
        raise ValueError("snapshot manifest is not a list")
    entries = [ManifestEntry(path=e["path"], sha256=e["sha256"], uid=e["uid"]) for e in raw]
    uids = [e.uid for e in entries]
    paths = [e.path for e in entries]
    if len(set(uids)) != len(uids):
        raise ValueError("snapshot manifest: duplicate uid")
    if len(set(paths)) != len(paths):
        raise ValueError("snapshot manifest: duplicate path")
    return entries


def load_snapshot(root: Path | str, embedder_namespace: str | None) -> Snapshot | None:
    try:
        doc = read_json(snapshot_path(root))
        if doc is None:
            return None
        if not isinstance(doc, dict):
            return None
        if doc.get("version") != SNAPSHOT_SCHEMA_VERSION or doc.get("lang") != SNAPSHOT_LANG:
            return None

        manifest = _parse_manifest(doc["manifest"])
        manifest_uids = {m.uid for m in manifest}

        index = Index.from_dict(doc["structural"])
        if set(index.by_uid) != manifest_uids:
            return None

        search_index = SearchIndex.from_dict(doc["search"])
        if set(search_index.lengths) != manifest_uids:
            return None

        vector_index: VectorIndex | None = None
        if embedder_namespace is not None:
            vec = doc.get("vectors")
            if not isinstance(vec, dict):
                return None
            if vec.get("namespace") != embedder_namespace:
                return None
            vector_index = VectorIndex.from_dict(vec)
            if set(vector_index.vectors) != manifest_uids:
                return None

        return Snapshot(manifest=manifest, index=index, search_index=search_index, vector_index=vector_index)
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None
```

Note: `json.JSONDecodeError` is a subclass of `ValueError`, so the `except` clause already covers corrupt JSON from `read_json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `rtk uv run pytest tests/test_snapshot_load.py -q`
Expected: PASS (10 tests).

- [ ] **Step 5: Run gate and commit**

Run: `rtk uv run ruff check src tests`, `rtk uv run pyright src`.

```bash
cd python && rtk git add src/nodes/kernel/snapshot.py tests/test_snapshot_load.py
rtk git commit -m "feat(persistence): snapshot write + load with version/lang/integrity gate"
```

---

### Task 6: Corpus load / reconcile / full-rebuild + flush_index

**Files:**
- Modify: `python/src/nodes/kernel/corpus.py`
- Test: `python/tests/test_corpus_persistence.py`

**Interfaces:**
- Consumes: Task 1 (`iter_corpus_files`, `ManifestEntry`, `hash_bytes`); Task 5 (`load_snapshot`, `write_snapshot`, `Snapshot`); existing `node_from_markdown`, `node_to_markdown`, the three index classes, `VectorCache`.
- Produces:
  - `Corpus.flush_index(self) -> None` — atomically writes the snapshot from current in-memory state (manifest sorted by path).
  - `Corpus.__init__` reconciles from a usable snapshot or full-rebuilds; populates `self.manifest: dict[str, ManifestEntry]` (keyed by root-relative POSIX path); never writes the snapshot.
  - Private helpers `_full_rebuild`, `_reconcile`.

**Current `corpus.py` `__init__` (for reference — being replaced):** builds `self.index`/`self.search_index`/`self.vector_index` unconditionally from `self.store.all_nodes()`.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_corpus_persistence.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import CollisionError
from nodes.kernel.frontmatter import node_to_markdown
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to
from nodes.kernel.snapshot import snapshot_path


def _seed(root) -> Corpus:
    c = Corpus(root)
    c.add(Node(id="topic:a", kind="topic", title="A", body="alpha gamma",
               relations=[relates_to("topic:a", "topic:b")]))
    c.add(Node(id="topic:b", kind="topic", title="B", body="beta gamma"))
    return c


def _results(c: Corpus) -> dict:
    return {
        "search_gamma": [(h.id, h.uid) for h in c.search("gamma")],
        "outbound_a": [(e.relation.target, e.target_uid) for e in c.outbound("topic:a")],
        "dangling": len(c.dangling()),
    }


def test_round_trip_matches_fresh_rebuild(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    assert snapshot_path(tmp_path).is_file()
    loaded = Corpus(tmp_path)          # loads + reconciles (no on-disk changes)
    fresh = Corpus(tmp_path)           # also loads, identical
    assert _results(loaded) == _results(c)
    assert _results(loaded) == _results(fresh)


def test_construction_never_writes_snapshot(tmp_path):
    _seed(tmp_path)                    # no flush
    assert not snapshot_path(tmp_path).is_file()
    Corpus(tmp_path)                   # full rebuild, must not write
    assert not snapshot_path(tmp_path).is_file()


def test_reconcile_after_direct_disk_edit(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    # Edit topic/b.md directly on disk (content change, same uid/id).
    b_node = c.store.read_file("topic:b")
    b_node.body = "beta delta epsilon"
    c.store.path_for("topic:b").write_text(node_to_markdown(b_node), encoding="utf-8")
    reconciled = Corpus(tmp_path)
    assert [(h.id, h.uid) for h in reconciled.search("delta")] == [("topic:b", b_node.uid)]


def test_reconcile_added_and_deleted_files(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    # Delete a's file, add a new file, both directly on disk.
    c.store.path_for("topic:a").unlink()
    c.store.write_file(Node(id="topic:c", kind="topic", title="C", body="gamma"))
    reconciled = Corpus(tmp_path)
    ids = {h.id for h in reconciled.search("gamma")}
    assert ids == {"topic:b", "topic:c"}     # a gone, c present, b retained


def test_corrupt_snapshot_silently_rebuilds(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    snapshot_path(tmp_path).write_text("{garbage", encoding="utf-8")
    rebuilt = Corpus(tmp_path)                # must not raise
    assert _results(rebuilt) == _results(c)


def test_malformed_corpus_file_propagates(tmp_path):
    _seed(tmp_path)
    c2 = Corpus(tmp_path)
    c2.flush_index()
    # Corrupt an actual corpus file (not the cache): construction must raise.
    c2.store.path_for("topic:a").write_text("---\nnot: valid node\n---\nbody", encoding="utf-8")
    with pytest.raises(Exception):
        Corpus(tmp_path)


def test_reconcile_uid_collision_raises(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    # Rewrite b.md so it claims a's uid → duplicate uid on reconcile.
    a = c.store.read_file("topic:a")
    b = c.store.read_file("topic:b")
    b.uid = a.uid
    c.store.path_for("topic:b").write_text(node_to_markdown(b), encoding="utf-8")
    with pytest.raises(CollisionError):
        Corpus(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_corpus_persistence.py -q`
Expected: FAIL — `AttributeError: 'Corpus' object has no attribute 'flush_index'`.

- [ ] **Step 3: Rewrite `Corpus.__init__` and add the helpers**

In `python/src/nodes/kernel/corpus.py`, update the imports block:

```python
from nodes.kernel.errors import CollisionError, EmbedderRequiredError, RefError
from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown
from nodes.kernel.similarity import Embedder, SimilarHit, Vector, VectorCache, VectorIndex
from nodes.kernel.snapshot import (
    ManifestEntry,
    Snapshot,
    hash_bytes,
    iter_corpus_files,
    load_snapshot,
    write_snapshot,
)
```

(Keep the existing `NodeId`, `Index`, `ResolvedEdge`, `Node`, `Registry`, `SearchHit`, `SearchIndex`, `MEMBERSHIP`, `Store` imports.)

Replace `__init__` with:

```python
    def __init__(self, root: Path, registry: Registry | None = None, embedder: Embedder | None = None) -> None:
        self.store = Store(root)
        self.registry = registry
        self.embedder = embedder
        self.vector_cache: VectorCache | None = VectorCache(root) if embedder is not None else None
        self.manifest: dict[str, ManifestEntry] = {}
        namespace = embedder.cache_namespace if embedder is not None else None
        snap = load_snapshot(self.store.root, namespace)
        if snap is None:
            self._full_rebuild()
        else:
            self._reconcile(snap)

    def _rel_path(self, node_id: str) -> str:
        return self.store.path_for(node_id).relative_to(self.store.root).as_posix()

    def _full_rebuild(self) -> None:
        nodes: list[Node] = []
        manifest: dict[str, ManifestEntry] = {}
        for f in iter_corpus_files(self.store.root):
            node = node_from_markdown(f.data.decode("utf-8"))
            nodes.append(node)
            manifest[f.path] = ManifestEntry(path=f.path, sha256=f.sha256, uid=node.uid)
        self.index = Index.build(nodes)
        self.search_index = SearchIndex.build(nodes)
        if self.embedder is not None:
            assert self.vector_cache is not None
            self.vector_index: VectorIndex | None = VectorIndex.build(nodes, self.embedder, self.vector_cache)
        else:
            self.vector_index = None
        self.manifest = manifest

    def _reconcile(self, snap: Snapshot) -> None:
        self.index = snap.index
        self.search_index = snap.search_index
        self.vector_index = snap.vector_index
        old = {m.path: m for m in snap.manifest}
        new_manifest: dict[str, ManifestEntry] = {}
        changed: list[tuple[str, str, Node]] = []  # (path, sha256, node)
        drops: list[str] = []
        current: set[str] = set()
        for f in iter_corpus_files(self.store.root):
            current.add(f.path)
            prev = old.get(f.path)
            if prev is not None and prev.sha256 == f.sha256:
                new_manifest[f.path] = prev
                continue
            if prev is not None:
                drops.append(prev.uid)  # changed: drop old uid
            changed.append((f.path, f.sha256, node_from_markdown(f.data.decode("utf-8"))))
        for path, m in old.items():
            if path not in current:
                drops.append(m.uid)  # deleted
        for uid in drops:
            self.index.remove(uid)
            self.search_index.remove(uid)
            if self.vector_index is not None:
                self.vector_index.remove(uid)
        for path, sha, node in changed:
            if node.uid in self.index.by_uid:  # full build() collision contract, not just assert_addable
                raise CollisionError(f"duplicate uid {node.uid!r} in corpus")
            self.index.assert_addable(node)
            prepared = None
            if self.vector_index is not None:
                assert self.embedder is not None and self.vector_cache is not None
                prepared = self.vector_index.prepare(node, self.embedder, self.vector_cache)
            self.index.upsert(node)
            self.search_index.upsert(node)
            if self.vector_index is not None and prepared is not None:
                self.vector_index.commit(node, prepared)
            new_manifest[path] = ManifestEntry(path=path, sha256=sha, uid=node.uid)
        self.manifest = new_manifest

    def flush_index(self) -> None:
        manifest = sorted(self.manifest.values(), key=lambda m: m.path)
        write_snapshot(self.store.root, manifest, self.index, self.search_index, self.vector_index)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_corpus_persistence.py -q`
Expected: PASS (7 tests).

Run the full suite to confirm nothing regressed (the `__init__` rewrite touches every `Corpus` construction):
Run: `rtk uv run pytest -q`
Expected: PASS (all existing tests still green).

- [ ] **Step 5: Run gate and commit**

Run: `rtk uv run ruff check src tests`, `rtk uv run pyright src`.

```bash
cd python && rtk git add src/nodes/kernel/corpus.py tests/test_corpus_persistence.py
rtk git commit -m "feat(persistence): Corpus load/reconcile/full-rebuild + flush_index"
```

---

### Task 7: Manifest maintenance across mutations + docs

**Files:**
- Modify: `python/src/nodes/kernel/corpus.py`
- Modify: `docs/format.md`
- Test: `python/tests/test_corpus_persistence_rename.py`

**Interfaces:**
- Consumes: Task 6 (`self.manifest`, `_rel_path`, `flush_index`); `node_to_markdown`, `hash_bytes`, `ManifestEntry`.
- Produces: `add`, `delete`, `rename` keep `self.manifest` in sync (a renamed node's referrers are re-hashed; the old path entry is removed when the node moves), so `flush_index()` after API mutations writes a manifest that matches the on-disk bytes.

- [ ] **Step 1: Write the failing test**

Create `python/tests/test_corpus_persistence_rename.py`:

```python
from __future__ import annotations

from nodes.kernel.corpus import Corpus
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to
from nodes.kernel.snapshot import hash_bytes, iter_corpus_files


def _manifest_matches_disk(c: Corpus) -> bool:
    """Every in-memory manifest entry equals the actual on-disk file bytes + walk."""
    on_disk = {f.path: f.sha256 for f in iter_corpus_files(c.store.root)}
    mem = {p: e.sha256 for p, e in c.manifest.items()}
    return on_disk == mem


def _results(c: Corpus):
    return (
        sorted((h.id, h.uid) for h in c.search("gamma")),
        sorted((e.relation.source, e.relation.target) for e in c.dangling()),
        sorted(c.index.id_to_uid),
    )


def test_add_keeps_manifest_in_sync(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", body="gamma"))
    c.add(Node(id="topic:b", kind="topic", title="B", body="gamma"))
    assert _manifest_matches_disk(c)


def test_delete_removes_manifest_entry(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", body="gamma"))
    c.add(Node(id="topic:b", kind="topic", title="B", body="gamma"))
    c.delete("topic:a")
    assert "topic/a.md" not in c.manifest
    assert _manifest_matches_disk(c)


def test_rename_updates_referrers_and_old_path(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", body="gamma",
               relations=[relates_to("topic:a", "topic:b")]))
    c.add(Node(id="topic:b", kind="topic", title="B", body="gamma"))
    c.rename("topic:b", "topic:b2")  # rewrites a.md (referrer) and moves b.md -> b2.md
    assert "topic/b.md" not in c.manifest          # old path removed
    assert "topic/b2.md" in c.manifest
    assert _manifest_matches_disk(c)               # referrer a.md re-hashed too


def test_flush_after_mutations_reloads_equivalently(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", body="gamma",
               relations=[relates_to("topic:a", "topic:b")]))
    c.add(Node(id="topic:b", kind="topic", title="B", body="gamma"))
    c.rename("topic:b", "topic:b2")
    c.add(Node(id="topic:c", kind="topic", title="C", body="gamma"))
    c.delete("topic:a")
    c.flush_index()
    reloaded = Corpus(tmp_path)
    fresh = Corpus(tmp_path)  # snapshot already consumed; both load the same snapshot
    assert _results(reloaded) == _results(c)
    # And a from-scratch rebuild (no snapshot) agrees:
    from nodes.kernel.snapshot import snapshot_path
    snapshot_path(tmp_path).unlink()
    assert _results(Corpus(tmp_path)) == _results(c)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk uv run pytest tests/test_corpus_persistence_rename.py -q`
Expected: FAIL — `test_rename_updates_referrers_and_old_path` (and the add/delete sync tests) fail because mutations don't yet touch `self.manifest`.

- [ ] **Step 3: Add manifest maintenance to the mutation methods**

In `python/src/nodes/kernel/corpus.py`, add a helper and wire it into `add`/`delete`/`rename`.

Add the helper (near `_rel_path`):

```python
    def _record_manifest(self, node: Node) -> None:
        rel = self._rel_path(node.id)
        sha = hash_bytes(node_to_markdown(node).encode("utf-8"))
        self.manifest[rel] = ManifestEntry(path=rel, sha256=sha, uid=node.uid)
```

In `add`, after the existing `self.search_index.upsert(node)` / vector commit, before `return node`:

```python
        self._record_manifest(node)
        return node
```

In `delete`, capture the path before deleting the file and drop the manifest entry after removal:

```python
    def delete(self, node_id: str) -> None:
        uid = self.index.id_to_uid.get(node_id)
        if uid is None:
            raise RefError(f"no live node at {node_id!r}")
        rel = self._rel_path(node_id)
        self.store.delete_file(node_id)
        self.index.remove(uid)
        self.search_index.remove(uid)
        if self.vector_index is not None:
            self.vector_index.remove(uid)
        self.manifest.pop(rel, None)
```

In `rename`, after the existing final `self.search_index.upsert(node)` and vector commit (i.e. at the very end, before `return node`), add:

```python
        old_rel = old_path.relative_to(self.store.root).as_posix()
        new_rel = new_path.relative_to(self.store.root).as_posix()
        if old_rel != new_rel:
            self.manifest.pop(old_rel, None)
        self._record_manifest(node)
        for referrer in referrers:
            self._record_manifest(referrer)
        return node
```

(`old_path` and `new_path` already exist in `rename`: `old_path = self.store.path_for(old_id)` and `new_path = self.store.write_file(node)`. `referrers` is the existing list of rewritten referrer nodes.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk uv run pytest tests/test_corpus_persistence_rename.py -q`
Expected: PASS (4 tests).

Run the full suite:
Run: `rtk uv run pytest -q`
Expected: PASS (entire suite green).

- [ ] **Step 5: Update `docs/format.md`**

Append a subsection after the similarity-index section (the file's current tail describes the similarity index). Add:

```markdown
### Index persistence (Python)

The three derived indexes are persisted to a **disposable, private, per-language
snapshot** at `<root>/.nodes-index/snapshot.py.json` (git-ignored). Constructing a
`Corpus` loads the snapshot and **reconciles it against the current files by content
hash** — unchanged files (sha256 of on-disk bytes matches the snapshot manifest) skip
parsing; changed/added files are re-parsed and re-indexed; deleted files are dropped.
Files remain the single source of truth: an absent, corrupt, wrong-`version`/`lang`, or
(embedder-configured) namespace-mismatched snapshot silently triggers a full rebuild, and
every load reconciles against current hashes, so the cache can never serve stale results.

Writing is explicit: `Corpus.flush_index()` serializes the three indexes plus the
manifest and writes atomically. Construction never writes the snapshot. Reconcile
enforces the same collision contract as a from-scratch build. The TypeScript port writes
`snapshot.ts.json`; neither language reads the other's snapshot.
```

- [ ] **Step 6: Run gate and commit**

Run: `rtk uv run ruff check src tests`, `rtk uv run pyright src`.

```bash
cd python && rtk git add src/nodes/kernel/corpus.py tests/test_corpus_persistence_rename.py ../docs/format.md
rtk git commit -m "feat(persistence): manifest maintenance across add/delete/rename; docs"
```

---

## Self-Review

**Spec coverage:**

- §2 architecture (pure indexes + `snapshot.py` owns I/O) → Tasks 1–5 add `to_dict/from_dict` to the pure classes; all file I/O lives in `snapshot.py`. ✓
- §2.1/§2.2 file layout + document shape → Task 1 (`snapshot_path`, `.nodes-index/snapshot.py.json`), Task 5 (`write_snapshot` document with `version`/`lang`/`manifest`/`structural`/`search`/`vectors`). ✓
- §3 manifest as byte-level walk product (both paths) → Task 6 `_full_rebuild` + `_reconcile` hash on-disk bytes via `iter_corpus_files`; Task 7 write-path entries hash `node_to_markdown(node)` (== on-disk bytes). ✓
- §3 rename referrers + old-path removal → Task 7 `rename` updates referrers and pops old path on move. ✓
- §4 load/reconcile algorithm, drops-before-upserts, error scoping → Task 6 `_reconcile`; `load_snapshot` (Task 5) never parses corpus files so corpus errors propagate. ✓
- §4.1 full `build()` collision contract → Task 6 `node.uid in self.index.by_uid` check before `assert_addable`; covered by `test_reconcile_uid_collision_raises`. ✓
- §5 integrity/bijection → Task 5 `load_snapshot` cross-section checks + Tasks 2/3/4 per-section self-consistency. ✓
- §6 embedder/vector rules + no-embedder tolerance → Task 5 (`embedder_namespace` gate; vectors ignored when `None`); `test_no_embedder_ignores_corrupt_vectors_section`. ✓
- §7 per-index serialization + shared-`Relation` invariant → Tasks 2/3/4; Task 4 replays `_out_refs_from`; `test_round_trip_preserves_inbound_and_dangling_dedup`. ✓
- §8 `flush_index` explicit + atomic; construction never writes → Task 6; `test_construction_never_writes_snapshot`. ✓
- §9 error handling table → Task 5 silent-`None` cases + Task 6 propagation tests. ✓
- §10 testing (round-trip, on-disk reconcile, rename, invalidation, no-embedder, error propagation, relation identity, integrity guards, dim=null) → distributed across Tasks 1–7. ✓
- §11 module/file map → matches the File Structure section. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every test has assertions; no "similar to Task N" references. ✓

**Type consistency:** `ManifestEntry(path, sha256, uid)`, `CorpusFile(path, data, sha256)`, `Snapshot(manifest, index, search_index, vector_index)`, `load_snapshot(root, embedder_namespace)`, `write_snapshot(root, manifest, index, search_index, vector_index)`, `_out_refs_from(relations, membership)`, `IndexEntry.membership`, `self.manifest: dict[str, ManifestEntry]` — names/signatures are identical across the tasks that define and consume them. ✓
