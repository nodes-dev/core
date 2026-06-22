# nodes — Embedding / Similarity Index (Design)

- **Status:** Draft (design approved, pending spec review)
- **Date:** 2026-06-22
- **Scope:** The fourth derived-index facet of the kernel (substrate §5): an
  **embedding + similarity store**. **Python first**; the TypeScript port is a
  separate later spec/plan, exactly as the full-text search subsystem was rolled
  out (Python → frozen fixtures → TS port).
- **Builds on:** the substrate design (§5 derived index) and the full-text
  search subsystem, whose `SearchIndex` / `Corpus` patterns this mirrors.

## 1. Motivation & goals

§5 of the substrate design lists four derived-index facets backing fast I/O:
full-text search, the resolved relation graph, alias/slug → id/uid resolution,
and **an embedding + similarity store**. The first three exist. This spec
designs the fourth: semantic "more like this" and free-text semantic search over
the corpus, computed from dense vector embeddings of each node.

### Goals

- A domain-free, parity-clean kernel facet that owns **vector storage + cosine
  ranking + the embedder seam**, and ships **no** concrete embedding model.
- Exact, deterministic ranking that is bit-stable across the Python and (later)
  TypeScript implementations.
- Files stay canonical; the index — including the on-disk vector cache — is a
  disposable, fully-rebuildable cache.
- Compose cleanly alongside the existing search/structural indexes without
  touching them.

### Non-goals (deferred — YAGNI)

- **Approximate nearest neighbor** (HNSW / IVF). We do exact brute-force cosine.
  At the current corpus scale it is fast enough, and — unlike ANN libraries,
  which differ across languages — brute-force is bit-stable, so it is the only
  thing that preserves the cross-language parity contract. ANN is a noted future
  axis.
- **The TypeScript port** — its own later spec/plan.
- **Body chunking** for long documents (one vector per node, from the whole
  title+body).
- **Multi-vector / per-field embeddings** (a single combined vector per node).
- **Automatic re-embedding on model change** beyond namespace isolation of the
  cache (§4).

## 2. Architecture

One new kernel module, `python/src/nodes/kernel/similarity.py`, domain-free and
parity-clean. It contributes three units plus one new error:

| Unit | Responsibility |
|------|----------------|
| `Embedder` (Protocol) | The seam: `embed(texts) -> list[Vector]` + a `cache_namespace`. Kernel defines the interface only; the concrete model is injected by the caller, one layer above the kernel. |
| `VectorCache` | Content-addressed on-disk cache of **raw** embedder output, namespaced per embedder. Disposable. |
| `VectorIndex` | In-memory, pure-data inverted-free store: `uid → normalized vector`, cosine ranking, the three query entry points. Owns all ranking math. |
| `EmbedderRequiredError` | Raised by `Corpus` similarity APIs when no embedder is configured. |

`Corpus` gains an optional `embedder` parameter; when supplied it owns the
embedder + a `VectorCache` and keeps the `VectorIndex` current on
`add`/`delete`/`rename`, mirroring how it maintains `SearchIndex`.

**Prerequisite refactor — shared ranking primitive.** `score_key` (the
parity-critical half-up-to-6-dp rounding) is extracted from `search.py` into a
new `python/src/nodes/kernel/ranking.py`, imported by **both** `search.py` and
`similarity.py`. This gives the two derived-index facets one source of truth for
the rounding without coupling the vector index to full-text search. The barrel
export and the existing search tests are updated to import from `ranking`; the
later TypeScript port mirrors the extraction (`ranking.ts`).

The dependency direction is unchanged: `similarity.py` depends only on
`node.py`, `errors.py`, and the shared `ranking.py`; nothing domain-specific
leaks in, and it does **not** depend on `search.py`.

## 3. Embedder seam & the Vector type

```python
Vector = tuple[float, ...]

class Embedder(Protocol):
    @property
    def cache_namespace(self) -> str: ...

    def embed(self, texts: list[str]) -> list[Vector]: ...
```

- `embed` is **order-preserving** and returns exactly one vector per input
  string.
- `cache_namespace` identifies the embedder (model + version + any config that
  changes its output) so that incompatible vectors never collide in the cache.
  It must be non-empty, match `^[A-Za-z0-9._-]+$`, and not equal `.` or `..`
  (it becomes a directory name; §4). Violations raise `ValueError`.
- **Vector validation (applied to every vector entering the system —
  embedder output, cache load, and query input):**
  - every element is a **finite** float (`NaN`, `Infinity`, `-Infinity` are
    rejected with `ValueError`);
  - length ≥ 1 (a zero-length vector is invalid);
  - length equals the index's established dimension (§5.3), else `ValueError`.

The kernel ships **no** concrete `Embedder`. Tests supply a deterministic
double; real deployments inject a model client.

### `embed_text` — the frozen text contract

```python
def embed_text(node: Node) -> str:
    return f"{node.title}\n\n{node.body}"
```

A single vector per node, from the title and body joined by exactly one blank
line. This join is a frozen contract: it determines both the cache key (§4) and
the parity fixtures (§7), and must be identical in the TypeScript port.

## 4. VectorCache — content-addressed disk cache

Embeddings are expensive to recompute and require the model to be present.
A content-addressed cache reconciles that with §5's "files canonical, index
disposable" rule: a rebuild re-embeds only new/changed text; unchanged text is a
cache hit, so a warm cache needs no model call (no remote embedding request) for
already-seen content.

- **Location:** `<corpus_root>/.nodes-index/vectors/<namespace>/<text_hash>.json`
  - `<namespace>` = the embedder's validated `cache_namespace` — incompatible
    models are physically isolated, so a text-only key can never reuse another
    model's vector.
  - `<text_hash>` = `sha256(embed_text.encode("utf-8"))` hex. Identical bytes →
    identical key in both languages; two nodes with identical `embed_text`
    dedupe to one entry.
  - The whole `.nodes-index/` tree is git-ignored and disposable; deleting it
    just forces re-embedding.
- **File format** — one JSON object per key, storing the **raw** (un-normalized)
  embedder output, so the cache is purely a model-output cache and all ranking
  math stays owned by `VectorIndex`:

  ```json
  {"dim": 1536, "vector": [0.1, -0.2]}
  ```

  Written with `allow_nan=False` (non-finite floats are never serialized).
- **Reads validate, fail-early:** a cache file that is unparseable, whose
  `vector` length ≠ `dim`, or that contains a non-finite element raises
  `ValueError`. The repair path is deletion (the entry is disposable);
  there is no silent fallback.
- **Writes are atomic:** write to a temporary file in the same directory, then
  `os.replace` into place, so a crash mid-write never leaves a corrupt final
  file that would later require manual repair.

## 5. VectorIndex — in-memory store + ranking

Pure data; the only I/O it performs is delegated to the injected `VectorCache`.

### 5.1 State

| Field | Meaning |
|-------|---------|
| `vectors: dict[str, Vector]` | uid → **L2-normalized** vector (so cosine = dot product). |
| `id_by_uid: dict[str, str]` | uid → current canonical id (for hit construction). |
| `hash_by_uid: dict[str, str]` | uid → `text_hash` last embedded (to detect content change on upsert). |
| `dim: int \| None` | Established dimension (§5.3). |
| `namespace: str \| None` | The embedder `cache_namespace` this index is bound to (§5.3). |

### 5.2 Mutators

- `build(nodes, embedder, cache) -> VectorIndex` — binds the index to
  `embedder.cache_namespace` (§5.3), then for each node:
  `embed_text → text_hash → cache hit loads raw vector, miss calls
  embedder.embed([text]) and writes the cache`; validate; normalize; store.
  A duplicate uid raises `CollisionError` (mirrors `SearchIndex.build`).
- `upsert(node, embedder, cache)` — first enforce the namespace binding (§5.3).
  Then, if the node's current `text_hash` equals the stored `hash_by_uid[uid]`
  **and** the index is already bound to this embedder's namespace,
  **no re-embedding**: only `id_by_uid` is refreshed (this is the rename case —
  title/body unchanged, id changed). Otherwise resolve the vector
  (cache-or-embed), validate, normalize, and replace. Because the index is bound
  to a single namespace, the skip decision is effectively keyed on the full
  `(namespace, text_hash)` — a different namespace can never silently reuse a
  stale vector.
- `remove(uid)` — drop all state for the uid.

`build`/`upsert` resolve-and-validate the vector **before** mutating index state,
so a failure leaves the index unchanged (and composes with the corpus-level
ordering guarantee in §6).

### 5.3 Dimension & namespace lifecycle

Both are established on first use and immutable thereafter, because an index
mixes neither dimensions nor models (cosine across vectors from two different
embedders is meaningless):

- **Dimension:** empty index has `dim = None`; the first stored vector
  establishes `dim` (its length, ≥ 1); every later stored vector, and every
  query vector, must have length `dim`, else `ValueError`.
- **Namespace:** empty index has `namespace = None`; the first `build`/`upsert`
  binds it to that embedder's `cache_namespace`; any later `build`/`upsert` whose
  embedder reports a different `cache_namespace` raises `ValueError`. Query paths
  take no embedder and so never re-check the namespace.

### 5.4 Query entry points & ranking contract

- `query_vector(vec, k) -> list[SimilarHit]` — validate + normalize `vec`
  (zero-norm or non-finite or dim-mismatch → `ValueError`), dot-product against
  every stored vector, rank, return top `k`.
- `similar(uid, k) -> list[SimilarHit]` — rank the stored vector for `uid`,
  **excluding `uid` itself**. It is a pure lookup over uids and raises a concrete
  `KeyError` if the uid is unknown; ref resolution and the `RefError` translation
  are the caller's job (`Corpus.similar`, §6). Implemented via a private
  `_rank(query_vec, k, *, exclude_uid=None)`; `query_vector` passes
  `exclude_uid=None`, `similar` passes the node's own uid.
- `similar_text(text, embedder, k) -> list[SimilarHit]` — the only query path
  that needs a live embedder. When `self.namespace is not None` it first enforces
  `embedder.cache_namespace == self.namespace`, raising `ValueError` on mismatch,
  so a direct caller cannot rank a model-B query vector against model-A stored
  vectors. It then calls `embedder.embed([text])` and `query_vector`, using the
  embedder directly and **not** writing the query vector to the cache (the cache
  is for node content, not arbitrary queries).

**Ranking key — identical to full-text search:** sort by
`(-score_key(score), id)` ascending on id, where `score` is cosine similarity and
`score_key` is the shared half-up-to-6-dp function
(`math.floor(score * 1_000_000 + 0.5) / 1_000_000`) from the new `ranking.py`
(§2). It is correct over cosine's `[-1, 1]` range because `math.floor` /
`Math.floor` agree on negative operands across both languages.

**`k` contract — identical to search's `limit`:** a positive int, or `None` for
unbounded; anything else (including `bool`, non-int, or `<= 0`) raises
`ValueError`.

**Empty index:** `query_vector` / `similar_text` on an index with no vectors
still validate the query vector — finite elements, length ≥ 1, non-zero norm all
apply and raise `ValueError` on violation. Only the **dimension match** is
skipped (there is no established `dim` yet). A valid query then returns `[]` (no
candidates).

### 5.5 Hit type

```python
@dataclass
class SimilarHit:
    id: str
    uid: str
    score: float   # raw cosine similarity (not the rounded score_key)
```

## 6. Corpus integration

`Corpus.__init__(root, registry=None, embedder=None)`. The similarity index is
**opt-in**:

- **`embedder=None`** — no `VectorIndex` is built. All three similarity APIs
  (`similar`, `query_vector`, `similar_text`) raise `EmbedderRequiredError`
  **before** any ref resolution or other work. Callers who only need
  CRUD/search/graph pay nothing.
- **`embedder` supplied** — `Corpus` owns the embedder and a `VectorCache(root)`,
  builds the `VectorIndex` at construction (cache-accelerated), and keeps it
  current:
  - `add` → `vector_index.upsert(node, embedder, cache)`
  - `delete` → `vector_index.remove(uid)`
  - `rename` → `vector_index.upsert(node, embedder, cache)` (same `text_hash` ⇒
    cache hit, no re-embed; `id_by_uid` refreshed for the new id)
  - `similar(ref, k)` resolves `ref → uid` via `self.index` (honoring
    `deprecated_ids`); a ref that resolves to nothing raises `RefError`. It then
    calls `vector_index.similar(uid, k)` — which would raise `KeyError` on an
    unknown uid, but `Corpus` only ever passes a uid it just resolved, so that
    `KeyError` is not reachable through `Corpus`. `Corpus` is the sole layer that
    translates unresolved refs into `RefError`.
  - `query_vector` / `similar_text` delegate directly to the `VectorIndex`.

### Mutation ordering (fail-early, no partial corpus state)

Unlike the structural/search indexes, similarity maintenance can fail (embedding
errors, invalid/non-finite vectors, dimension mismatch). `Corpus.add` and
`Corpus.rename` therefore **resolve and validate the vector before committing any
disk or structural-index mutation**:

1. existing pre-checks (registry validation, addability / rename collision);
2. resolve-and-validate the vector (cache-or-embed → finite/dim/nonzero checks →
   normalize). Cache *writes* here are acceptable (disposable);
3. only then write the node file, update the structural index, and commit the
   vector into the `VectorIndex`.

An embedding or validation failure raises before step 3, leaving the corpus
completely unmutated.

## 7. Cross-language parity strategy

The decisive difference from full-text search: vectors come from a model, so
Python and TS cannot be expected to compute identical vectors. We therefore
**freeze the vectors**, not merely the text, and assert that identical input
vectors produce identical rankings. Three committed fixtures (authored from
Python, consumed read-only by the later TS port — the same discipline search
used):

- **`fixtures/similarity-corpus/`** — a handful of `topic` nodes (markdown +
  frontmatter), the document set.
- **`fixtures/similarity.vectors.json`** — frozen **low-dimension** (4-d)
  hand-authored vectors, split so both query paths are covered:

  ```json
  {
    "documents": [{"id": "topic:...", "embed_text": "...", "vector": [..]}],
    "queries":   [{"text": "...", "vector": [..]}]
  }
  ```

  Low dimensionality keeps the rankings hand-checkable.
- **`fixtures/similarity.oracle.json`** — expected results for `similar(ref)`,
  `query_vector`, and `similar_text` cases: ranked `id`s with `score_key` scores.

Tests inject a `LookupEmbedder` with a fixed `cache_namespace` (e.g.
`"fixture-v1"`) that maps `embed_text → document vector` and
`query text → query vector` by exact table lookup — there is no embedding
*algorithm* to keep in parity, only shared frozen data. Both languages assert
identical ranked ids and 6-dp scores against the oracle.

## 8. Errors & edge cases (summary)

| Situation | Result |
|-----------|--------|
| `embedder=None` + any similarity API | `EmbedderRequiredError` (before ref resolution) |
| Unknown ref in `Corpus.similar` | `RefError` |
| Unknown uid in `VectorIndex.similar` | `KeyError` (not reachable via `Corpus`) |
| Zero-norm vector (insert or query) | `ValueError` |
| Non-finite element (embedder / cache / query) | `ValueError` |
| Dimension mismatch (insert or query) | `ValueError` |
| `build`/`upsert` embedder namespace ≠ index's bound namespace | `ValueError` |
| Invalid `cache_namespace` | `ValueError` |
| Duplicate uid in `build` | `CollisionError` |
| `k` not a positive int and not `None` | `ValueError` |
| Corrupt / dim-mismatched cache file | `ValueError` (delete to repair) |
| Query against empty index | `[]` |

## 9. Testing

- **Ranking extraction:** `score_key` lives in `ranking.py`; the existing search
  tests still pass importing it from there.
- **VectorIndex unit:** normalization (unit norm), cosine ranking with
  `(-score_key, id)` tiebreak, self-exclusion in `similar`, unknown-uid `KeyError`
  in `similar`, `k` validation, dimension lifecycle + mismatch, namespace binding
  (first use binds; mismatched `cache_namespace` on later build/upsert →
  `ValueError`), zero-norm and non-finite rejection, duplicate uid in `build`.
- **VectorCache unit:** hit/miss, namespace isolation, `cache_namespace`
  validation, raw-vector round-trip, atomic write, corrupt/dim-mismatch
  fail-early.
- **Corpus integration:** the three queries over a temp corpus with a
  deterministic test embedder; embedder-gating (`None` → `EmbedderRequiredError`
  before resolution); `add`/`delete`/`rename` keep the index current (rename
  refreshes id without re-embedding); failed-embedding leaves the corpus
  unmutated.
- **Parity:** frozen corpus + vectors + oracle (`similar`, `query_vector`,
  `similar_text`).

## 10. Resolved decisions

1. **Kernel scope:** vector storage + cosine ranking + embedder *protocol*; no
   bundled model.
2. **Persistence:** content-addressed on-disk cache of raw embedder output,
   namespaced per embedder; disposable; atomic writes.
3. **Embedded text:** one vector per node from `title + "\n\n" + body`.
4. **Metric:** exact brute-force cosine over L2-normalized vectors; no ANN.
5. **Ranking key:** shared `score_key` (half-up 6-dp) + `id` tiebreak, extracted
   into a new `ranking.py` and imported by both `search.py` and `similarity.py`
   (so neither facet depends on the other).
6. **Query surface:** `similar(ref, k)` (self-excluded), `query_vector(vec, k)`,
   `similar_text(text, embedder, k)`.
7. **Integration:** opt-in via `Corpus(embedder=...)`; `EmbedderRequiredError`
   when absent; add/rename validate the vector before mutating the corpus.
8. **Parity:** frozen low-dim fixture vectors (documents + queries) + oracle;
   `LookupEmbedder` table lookup; TS port consumes read-only.

## 11. Out of scope / future axes

ANN indexing; the TypeScript port (its own spec/plan); body chunking; multi-vector
/ per-field embeddings; automatic re-embedding on model change beyond cache
namespace isolation.
