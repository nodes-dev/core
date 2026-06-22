# nodes — full-text search (derived index) design

- **Date:** 2026-06-22
- **Scope:** The full-text search piece of the substrate's derived index (spec
  §5). Python first; a TypeScript port follows in a later plan, at semantic
  parity.
- **Status:** Approved design, pending implementation plan.

## 1. Motivation & goals

Substrate spec §5 calls for a rebuildable derived index backing fast CRUD/search,
listing **full-text search (ripgrep-class)** as one of its faces alongside the
already-built structural index (resolution + relation graph). This design builds
that search face.

"ripgrep-class" is read here as the *performance/role* bar (fast, rebuildable,
files-stay-canonical), not literal regex scanning. The query model is **tokenized
ranked search** with **BM25F** relevance scoring — what an application's search
box needs ("most relevant thoughts/entities for these words"), the first concrete
consumer being Mindful v6.

### Goals

- Rank nodes by relevance to a free-text query over their `title` and `body`.
- Weight `title` matches above `body` matches, with weighting that stays an
  explicit, tunable contract (not baked into a synthetic term-frequency trick).
- Pure-Python, in-memory, rebuildable from the canonical files — the same shape
  as the structural `Index`. No external dependencies beyond pydantic.
- Semantic Python↔TS parity, pinned by shared fixtures (a tokenizer oracle and a
  ranking oracle).

### Non-goals (deferred — YAGNI)

- Stemming / lemmatization (morphological matching). Parity-fragile; can come
  later behind the same tokenizer seam.
- Highlighted snippets / excerpts. Results return refs + score + matched terms;
  the caller hydrates the `Node` via `Corpus.get` when it wants text.
- Indexing facet values or frontmatter fields. Only `title` + `body` for v1.
- Regex / boolean / phrase query operators. Bag-of-terms only.
- On-disk persistence of the index (a separate later plan); built in memory.

## 2. Architecture & placement

A new derived index, sibling to the structural `Index`, in the **kernel** (spec
§2: the kernel owns the derived index).

- **New module `python/src/nodes/kernel/search.py`**, containing:
  - `tokenize(text: str) -> list[str]` — the canonical tokenizer (§3).
  - `SearchIndex` — the inverted index + BM25F scorer (§4–5).
  - `SearchHit` — the result dataclass (§6).
- **`Corpus` owns a `SearchIndex`** alongside its structural `Index`: built in
  `__init__` from `store.all_nodes()`, kept current in `add`/`delete`/`rename`,
  and queried via a new `Corpus.search(query, limit=None)` (§7).
- Python exposes the surface by module path (`from nodes.kernel.search import
  SearchIndex, SearchHit, tokenize`); the package barrels are empty today, so no
  barrel changes are needed.

Files stay canonical; the index is disposable cache, fully reconstructable by
`SearchIndex.build(store.all_nodes())`.

## 3. Tokenizer — the canonical contract (highest parity risk)

`tokenize(text)` is deterministic and identical across languages. Steps, in
order:

1. **NFC-normalize**, then lowercase.
   - Python: `unicodedata.normalize("NFC", text).lower()`
   - TS: `text.normalize("NFC").toLowerCase()`
   - Without NFC, visually identical composed vs decomposed Unicode (e.g. `é` as
     U+00E9 vs `e`+U+0301) would tokenize differently.
2. **Split into tokens** = maximal runs of Unicode alphanumeric characters
   (`\p{L} ∪ \p{N}`). Everything else (whitespace, punctuation, underscore,
   apostrophe, hyphen) is a separator.
   - TS: `s.match(/[\p{L}\p{N}]+/gu) ?? []`
   - Python: `re.findall(r"[^\W_]+", s)` — under stdlib `re`'s Unicode `\w`,
     `[^\W_]` is "word char excluding underscore", i.e. Unicode alphanumerics.
   - Consequences pinned by the oracle: `well-known` → `["well", "known"]`;
     `don't` → `["don", "t"]`; `state_of_art` → `["state", "of"(stop→drop),
     "art"]`; `R2D2` → `["r2d2"]`.
3. **Drop stop-words** — membership test against a fixed frozenset (§3.1).
4. Return the surviving tokens **in document order** (duplicates kept — term
   frequency is meaningful for documents). Query-side dedup happens in
   `search`, not here (§5).

Empty / whitespace / all-separator / all-stop-word input → `[]`.

### 3.1 Stop-word list (fixed, pinned)

A small fixed English list, defined as a module-level frozenset and frozen by the
oracle:

```
a an and are as at be but by for if in into is it no not of on or
such that the their then there these they this to was will with
```

(33 words.) Intentionally minimal; expansion is a later, oracle-gated change.

### 3.2 Tokenizer oracle (built first — see §9)

A committed `fixtures/search.tokenizer.json`: a list of `{input, tokens}` cases
that **both** languages must reproduce exactly. Required coverage: stop-words;
mixed case; punctuation; underscores; numbers; apostrophes; hyphens; composed
(NFC) vs decomposed (NFD) accents normalizing to the same tokens; empty string;
whitespace-only; and mixed scripts (e.g. Latin + CJK + Cyrillic).

## 4. Scoring — BM25F (field-weighted)

Two fields, `title` and `body`, combined the proper BM25F way: per-field
term-frequency contributions are length-normalized and summed into a single
weighted term frequency **before** saturation, with one IDF per term (not two
independent BM25 scores summed).

For query term `t` and document `d`:

- **IDF (non-negative, Lucene form):**
  `idf(t) = ln(1 + (N − df(t) + 0.5) / (df(t) + 0.5))`
  where `N` = number of documents and `df(t)` = number of documents containing
  `t` in `title` **or** `body`.
- **Weighted term frequency** over fields `f ∈ {title, body}`:
  `tf'(t,d) = Σ_f  boost_f · tf_f(t,d) / (1 − B + B · len_f(d) / avglen_f)`
  where `tf_f` is the count of `t` in field `f` of `d`, `len_f(d)` is `d`'s token
  count in field `f`, and `avglen_f` is the mean field length across all docs.
  If `avglen_f == 0` (no document has any token in that field), the field
  contributes 0 (its `tf_f` is necessarily 0) — guard the division.
- **Per-term score (standard BM25 numerator, with `(K1 + 1)`):**
  `score(t,d) = idf(t) · (K1 + 1) · tf'(t,d) / (K1 + tf'(t,d))`
- **Document score:** `Σ_t score(t,d)` over the **deduped** query terms that
  occur in `d`.

### 4.1 Constants (module-level, the tuning contract)

```
K1          = 1.5
B           = 0.75
TITLE_BOOST = 2.0
BODY_BOOST  = 1.0
```

### 4.2 Determinism (parity-critical)

Float accumulation order is fixed so results are bit-identical across languages:

- Query terms are reduced to a **sorted, deduplicated** list before scoring.
- Per term, fields are combined in the fixed order `title` then `body`.
- The document score sums per-term scores in sorted-term order.

Both languages run IEEE-754 doubles through the same operation sequence, so
scores match. The ranking oracle (§8) additionally compares scores rounded to 6
decimal places as a belt-and-braces check.

## 5. `SearchIndex` — state & operations

State (all in memory):

- `postings: dict[str, dict[str, tuple[int, int]]]` — term → uid →
  `(title_tf, body_tf)`. `df(term) == len(postings[term])`.
- `lengths: dict[str, tuple[int, int]]` — uid → `(title_len, body_len)`.
- `id_by_uid: dict[str, str]` — uid → current `id`, so hits carry a ref without
  touching disk.
- Running totals for `N` and summed title/body lengths → `avglen_title`,
  `avglen_body` (recomputed from totals, O(1) per query).

Operations mirror the structural `Index`:

- `build(nodes) -> SearchIndex` (classmethod) — full construction.
- `upsert(node)` — if `node.uid` is already present, remove its old postings and
  lengths first; then tokenize `title` and `body`, add per-field postings, record
  lengths, and set `id_by_uid[uid] = node.id`. Idempotent and update-safe.
- `remove(uid)` — drop the uid from `postings`, `lengths`, `id_by_uid`; decrement
  totals. Removing an absent uid is a no-op.
- `search(query, limit) -> list[SearchHit]` (§6).

A node whose `title` and `body` produce no tokens still occupies a document slot
(`lengths[uid] = (0, 0)`, no postings) so `N` and the averages stay correct.

## 6. Query API & result shape

```python
@dataclass
class SearchHit:
    id: str
    uid: str
    score: float
    matched_terms: list[str]   # sorted, deduped query terms present in this doc
```

`Corpus.search(query: str, limit: int | None = None) -> list[SearchHit]`:

1. `terms = sorted(set(tokenize(query)))`. If empty → return `[]`.
2. Candidate docs = union of `postings[t]` over `t ∈ terms`. Score each (§4).
3. Sort by **(score descending, id ascending)** — id breaks ties for full
   determinism.
4. Truncate to `limit` (`None` = unbounded).
5. Each `SearchHit.matched_terms` = the subset of `terms` present in that doc,
   sorted lexicographically.

The caller fetches the `Node` via `Corpus.get(hit.id)` when it needs the text.

## 7. Corpus integration

`Corpus.__init__` builds the search index after the structural index:
`self.search_index = SearchIndex.build(self.store.all_nodes())`.

Mutation ordering mirrors the structural index — **the disk write/delete succeeds
first, then both derived indexes update together** (no derived-index change is
observable if the disk operation raises):

- **`add`**: `validate → index.assert_addable → store.write_file →
  index.upsert(node) → search_index.upsert(node)`.
- **`delete`**: `store.delete_file → index.remove(uid) →
  search_index.remove(uid)`.
- **`rename`**: unchanged through the commit (write new file, delete old,
  `index.upsert` the renamed node and referrers). Then `search_index.upsert(node)`
  for the renamed node — its `uid` is unchanged and its `title`/`body` are
  untouched by rename, so only `id_by_uid` changes. Referrers' searchable text and
  ids are unchanged by rename, so they need no search-index update.

`Corpus.search` delegates to `self.search_index.search`.

## 8. Cross-language ranking oracle

A committed fixture corpus with prose-rich bodies plus a ranking oracle:

- `fixtures/search-corpus/` — a small multi-node corpus in the on-disk
  `kind/slug.md` layout, with varied natural-language bodies (so term frequency
  and field length actually differ across docs).
- `fixtures/search.oracle.json` — a list of `{query, hits}` cases, where each hit
  is `{id, score}` with `score` rounded to 6 decimal places, in ranked order.

Both languages: build a `SearchIndex` over the fixture corpus, run each query, and
assert the ranked `id` order and 6-dp scores equal the oracle. Mirrors the
existing `fixtures/corpus.rename.canonical.json` cross-language parity check.

## 9. Testing strategy

- **Tokenizer (Task 1, built first):** unit tests + the `search.tokenizer.json`
  oracle (§3.2). This is the highest parity-risk surface and every later oracle
  depends on it, so it lands before any scoring code.
- **BM25F scorer:** unit tests on small hand-computed corpora where IDF, field
  length norms, and the title boost are checked against worked-out numbers;
  include the `avglen_f == 0` guard and a single-term/single-doc baseline.
- **`SearchIndex` build/upsert/remove:** unit tests, including re-`upsert` of an
  existing uid (postings replaced, not duplicated) and `remove` of an absent uid.
- **Rebuild-equivalence property:** an index mutated incrementally
  (`upsert`/`remove`) equals a fresh `build()` of the same final node set —
  mirrors `test_index_rebuild_equivalence.py`.
- **`Corpus.search` integration:** ranking correct after `add`/`delete`/`rename`;
  title boost observable; `limit` honored.
- **Cross-language ranking oracle:** §8.

## 10. Error handling

- Zero matches → `[]` (never raises).
- `limit`: `None` = unbounded; otherwise must be an `int` with `limit > 0`. `0`,
  negative, or non-`int` → `ValueError`. (`bool` is rejected as non-int.)
- Empty / stop-word-only / non-tokenizing query → `[]`.
- No new error types; the search layer raises only `ValueError` for the `limit`
  contract. It never raises on corpus content.

## 11. Resolved decisions

1. **Query model:** tokenized ranked search, not literal/regex scanning.
2. **Backend:** hand-rolled in-memory inverted index + BM25F; no external deps;
   rebuilt on `Corpus` construction (structural-index precedent).
3. **Fields:** `title` + `body`, title weighted via `TITLE_BOOST`; explicit BM25F
   field weighting, not a boosted-token-stream approximation.
4. **Tokenizer:** NFC → lowercase → Unicode-alphanumeric runs → drop fixed
   stop-words; no stemming. Pinned by an oracle built first.
5. **Scoring:** standard BM25 numerator `(K1 + 1)·tf'/(K1 + tf')`; non-negative
   Lucene IDF; deterministic accumulation order.
6. **Results:** ranked refs + score + matched terms; sort `(score desc, id asc)`;
   caller hydrates nodes lazily.
7. **Mutation ordering:** disk first, then `index` and `search_index` together.
8. **Parity:** two shared fixtures — tokenizer oracle and ranking oracle.

## 12. Deferred / open

- Stemming, snippets, facet/frontmatter indexing, phrase/boolean/regex operators,
  on-disk persistence — all later, behind the seams above.
- Stop-word list expansion and any constant retuning are oracle-gated changes
  (they move the fixtures, so parity stays enforced).
