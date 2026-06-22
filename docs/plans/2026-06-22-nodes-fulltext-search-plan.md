# Full-Text Search (Derived Index) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a BM25F full-text search derived index to the Python kernel — a sibling to the structural `Index` — queryable through `Corpus.search`, with cross-language parity fixtures so the later TypeScript port matches exactly.

**Architecture:** One new kernel module `src/nodes/kernel/search.py` holds a canonical `tokenize`, an in-memory inverted index `SearchIndex` (postings + per-field lengths + BM25F scorer), and a `SearchHit` result. `Corpus` builds a `SearchIndex` beside its `Index` from one disk scan, keeps it current on `add`/`delete`/`rename`, and exposes `Corpus.search`. Two committed fixtures pin parity: a tokenizer oracle and a ranking oracle.

**Tech Stack:** Python ≥3.11, stdlib only for the new code (`re`, `math`, `unicodedata`, `dataclasses`) plus existing Pydantic; pytest, ruff (line-length 120), pyright (basic), `uv` runner, src/ layout.

## Global Constraints

- Every module starts with `from __future__ import annotations`.
- New runtime code lives only in `src/nodes/kernel/search.py`; the sole edit to existing code is `src/nodes/kernel/corpus.py`. Search is a kernel-layer derived index (spec §2).
- **No new dependencies.** Use only stdlib (`re`, `math`, `unicodedata`, `dataclasses`) and what the kernel already imports. No external search/NLP libraries.
- **Tokenizer (canonical, identical across languages):** `unicodedata.normalize("NFC", text).lower()`, then tokens = maximal runs matching `re.compile(r"[^\W_]+")` (Unicode alphanumerics, underscore excluded), then drop the fixed 33-word `STOP_WORDS`. No stemming. Document tokenization keeps duplicates (term frequency); query-side dedup happens in `search`.
- **Stop-word list (exactly these 33):** `a an and are as at be but by for if in into is it no not of on or such that the their then there these they this to was will with`.
- **BM25F constants (module-level):** `K1 = 1.5`, `B = 0.75`, `TITLE_BOOST = 2.0`, `BODY_BOOST = 1.0`.
- **Scoring:** `idf(t) = ln(1 + (N − df + 0.5)/(df + 0.5))`; `tf'(t,d) = Σ_field boost_f · tf_f / (1 − B + B · len_f/avglen_f)` with the field skipped when `avglen_f == 0`; `score(t,d) = idf · (K1 + 1) · tf' / (K1 + tf')`; document score sums per-term scores over the **deduped** query terms present in the doc.
- **Determinism:** query terms reduced to `sorted(set(...))` (Python's default string sort is Unicode code-point order); fields combined in fixed order `title` then `body`; `score_key(s) = math.floor(s * 1_000_000 + 0.5) / 1_000_000`; ranking sort key is `(-score_key(score), id)`; `matched_terms` sorted by the same code-point order.
- **`limit` contract:** `None` = unbounded; otherwise a positive `int` (`bool` rejected as non-int, non-`int` rejected, `<= 0` rejected) → `ValueError`.
- **`SearchIndex.build` rejects a duplicate `uid`** with `CollisionError` (from `nodes.kernel.errors`), mirroring `Index.build`.
- **Mutation ordering:** `Corpus.__init__` builds both indexes from a single `all_nodes()` scan. `add`/`delete` do disk first, then `index` then `search_index`. `rename` adds exactly one step — `search_index.upsert(node)` for the renamed node, after the existing structural commit. This plan does NOT refactor rename's commit atomicity.
- `Corpus(registry=...)` and all existing behavior stay unchanged; the existing test suite stays green.
- **Per-task gates, all clean before commit:** `rtk uv run pytest -q`, `rtk uv run ruff check src tests`, `rtk uv run pyright src`.
- **Working directories:** run all `rtk uv run …` from `~/d/nodes/python/`; run all `rtk git …` from `~/d/nodes/`. Paths in `Files:` blocks are repo-root-relative.

---

### Task 1: Canonical tokenizer + tokenizer oracle

**Files:**
- Create: `python/src/nodes/kernel/search.py`
- Create: `python/tests/test_search_tokenizer.py`
- Create: `python/scripts/gen_tokenizer_oracle.py`
- Create: `fixtures/search.tokenizer.json` (generated)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `STOP_WORDS: frozenset[str]`; `tokenize(text: str) -> list[str]`. Consumed by every later task.

- [ ] **Step 1: Write the failing tokenizer unit test**

Create `python/tests/test_search_tokenizer.py` (all imports at the top so the
oracle test appended in Step 7 does not trip ruff's `E402`):

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nodes.kernel.search import STOP_WORDS, tokenize

ORACLE = Path(__file__).parent.parent.parent / "fixtures" / "search.tokenizer.json"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", []),
        ("   \t\n ", []),
        ("The Quick Brown Fox", ["quick", "brown", "fox"]),  # 'the' is a stop word; lowercased
        ("the THE The", []),                                  # all stop words
        ("well-known", ["well", "known"]),                    # hyphen separates
        ("state_of_art", ["state", "art"]),                   # underscore separates; 'of' is a stop word
        ("don't", ["don", "t"]),                              # apostrophe separates
        ("3.14 and 2", ["3", "14", "2"]),                     # '.' separates; 'and' is a stop word
        ("café", ["café"]),                                   # composed (U+00E9)
        ("café", ["café"]),                             # decomposed e + combining acute -> NFC -> café
        ("Hello МИР", ["hello", "мир"]),                      # Cyrillic, lowercased
        ("hello 世界", ["hello", "世界"]),                     # CJK run is one token
    ],
)
def test_tokenize_cases(text, expected):
    assert tokenize(text) == expected


def test_stop_words_count_is_33():
    assert len(STOP_WORDS) == 33
    assert "the" in STOP_WORDS and "with" in STOP_WORDS
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk uv run pytest tests/test_search_tokenizer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nodes.kernel.search'`.

- [ ] **Step 3: Implement the tokenizer**

Create `python/src/nodes/kernel/search.py`:

```python
from __future__ import annotations

import re
import unicodedata

STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if",
        "in", "into", "is", "it", "no", "not", "of", "on", "or", "such", "that",
        "the", "their", "then", "there", "these", "they", "this", "to", "was",
        "will", "with",
    }
)

_TOKEN_RE = re.compile(r"[^\W_]+")


def tokenize(text: str) -> list[str]:
    """NFC-normalize, lowercase, split into Unicode-alphanumeric runs, drop stop words.

    Document tokenization keeps duplicates (term frequency is meaningful); query-side
    dedup happens in SearchIndex.search.
    """
    normalized = unicodedata.normalize("NFC", text).lower()
    return [tok for tok in _TOKEN_RE.findall(normalized) if tok not in STOP_WORDS]
```

- [ ] **Step 4: Run the unit test to verify it passes**

Run: `rtk uv run pytest tests/test_search_tokenizer.py -q`
Expected: PASS.

- [ ] **Step 5: Write the tokenizer-oracle generator**

Create `python/scripts/gen_tokenizer_oracle.py`. It writes `{input, tokens}` for a fixed input list. The inputs include the cases above plus mixed scripts and a non-BMP alphanumeric token so the later TS code-point comparator is exercised:

```python
from __future__ import annotations

import json
from pathlib import Path

from nodes.kernel.search import tokenize

ORACLE = Path(__file__).parent.parent.parent / "fixtures" / "search.tokenizer.json"

INPUTS = [
    "",
    "   \t\n ",
    "The Quick Brown Fox",
    "the THE The",
    "well-known",
    "state_of_art",
    "don't",
    "3.14 and 2",
    "café",            # composed U+00E9
    "café",      # decomposed e + combining acute
    "Hello МИР",       # Cyrillic
    "hello 世界",       # CJK
    "data\U0001D7D9point",  # non-BMP MATHEMATICAL DOUBLE-STRUCK DIGIT ONE inside a token
]


def main() -> None:
    cases = [{"input": text, "tokens": tokenize(text)} for text in INPUTS]
    ORACLE.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Generate the oracle fixture**

Run: `rtk uv run python scripts/gen_tokenizer_oracle.py`
Expected: writes `fixtures/search.tokenizer.json`. Sanity-check it: the `café` and `café` entries must both have `["café"]`; the non-BMP entry should be a single token `["data𝟙point"]` (one run, not split). If the non-BMP case splits, that is a real finding — stop and report it rather than editing the expectation away.

- [ ] **Step 7: Add the oracle-driven test**

Append this function to `python/tests/test_search_tokenizer.py` (imports and `ORACLE`
are already at the top from Step 1):

```python
def test_tokenizer_matches_committed_oracle():
    # Currency + cross-language freeze: the tokenizer must reproduce every committed
    # oracle case exactly. The later TypeScript port asserts the same file.
    cases = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert cases, "oracle must not be empty"
    for case in cases:
        assert tokenize(case["input"]) == case["tokens"], repr(case["input"])
```

- [ ] **Step 8: Run the full gate**

Run: `rtk uv run pytest tests/test_search_tokenizer.py -q`
Run: `rtk uv run ruff check src tests`
Run: `rtk uv run pyright src`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
cd ~/d/nodes
rtk git add python/src/nodes/kernel/search.py python/tests/test_search_tokenizer.py python/scripts/gen_tokenizer_oracle.py fixtures/search.tokenizer.json
rtk git commit -m "feat(search): canonical tokenizer + cross-language tokenizer oracle"
```

---

### Task 2: `SearchIndex` state — build / upsert / remove

**Files:**
- Modify: `python/src/nodes/kernel/search.py` (add the `SearchIndex` class)
- Create: `python/tests/test_search_index.py`

**Interfaces:**
- Consumes: `tokenize` (Task 1); `nodes.kernel.node.Node`; `nodes.kernel.errors.CollisionError`.
- Produces: `class SearchIndex` with attributes `postings: dict[str, dict[str, tuple[int, int]]]`, `lengths: dict[str, tuple[int, int]]`, `id_by_uid: dict[str, str]`, `_total_title: int`, `_total_body: int`; property `n: int`; methods `build(nodes) -> SearchIndex` (classmethod), `upsert(node) -> None`, `remove(uid) -> None`. `search` is added in Task 3.

- [ ] **Step 1: Write the failing tests**

Create `python/tests/test_search_index.py`:

```python
from __future__ import annotations

import pytest

from nodes.kernel.errors import CollisionError
from nodes.kernel.node import Node
from nodes.kernel.search import SearchIndex


def _norm(idx: SearchIndex) -> dict:
    return {
        "postings": {t: sorted(docs.items()) for t, docs in idx.postings.items()},
        "lengths": dict(idx.lengths),
        "id_by_uid": dict(idx.id_by_uid),
        "n": idx.n,
        "totals": (idx._total_title, idx._total_body),
    }


def test_upsert_records_per_field_term_frequencies():
    idx = SearchIndex()
    n = Node(id="topic:a", kind="topic", title="alpha", body="alpha alpha beta")
    idx.upsert(n)
    assert idx.postings["alpha"][n.uid] == (1, 2)  # 1 in title, 2 in body
    assert idx.postings["beta"][n.uid] == (0, 1)
    assert idx.lengths[n.uid] == (1, 3)
    assert idx.id_by_uid[n.uid] == "topic:a"
    assert idx.n == 1


def test_upsert_replaces_not_duplicates():
    idx = SearchIndex()
    n = Node(id="topic:a", kind="topic", title="", body="alpha alpha")
    idx.upsert(n)
    assert idx.postings["alpha"][n.uid] == (0, 2)
    n.body = "beta"
    idx.upsert(n)
    assert "alpha" not in idx.postings        # stale postings dropped
    assert idx.postings["beta"][n.uid] == (0, 1)
    assert idx.lengths[n.uid] == (0, 1)
    assert idx.n == 1


def test_remove_drops_everything_and_is_noop_when_absent():
    idx = SearchIndex()
    n = Node(id="topic:a", kind="topic", title="alpha", body="beta")
    idx.upsert(n)
    idx.remove(n.uid)
    assert idx.n == 0 and idx.postings == {} and idx.lengths == {} and idx.id_by_uid == {}
    assert (idx._total_title, idx._total_body) == (0, 0)
    idx.remove("not-present")  # no raise, no change
    assert idx.n == 0


def test_empty_text_still_counts_as_a_document():
    idx = SearchIndex()
    n = Node(id="topic:a", kind="topic", title="", body="")
    idx.upsert(n)
    assert idx.n == 1
    assert idx.lengths[n.uid] == (0, 0)
    assert idx.postings == {}


def test_build_rejects_duplicate_uid():
    a = Node(id="topic:a", kind="topic", title="A", uid="dup")
    b = Node(id="topic:b", kind="topic", title="B", uid="dup")
    with pytest.raises(CollisionError):
        SearchIndex.build([a, b])


def test_incremental_matches_fresh_rebuild():
    a = Node(id="topic:a", kind="topic", title="Alpha", body="alpha beta")
    b = Node(id="topic:b", kind="topic", title="Beta", body="gamma delta")
    c = Node(id="topic:c", kind="topic", title="C", body="alpha")
    idx = SearchIndex()
    idx.upsert(a)
    idx.upsert(b)
    a.body = "alpha gamma"
    idx.upsert(a)          # overwrite a
    idx.remove(b.uid)      # drop b
    idx.upsert(c)
    assert _norm(idx) == _norm(SearchIndex.build([a, c]))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `rtk uv run pytest tests/test_search_index.py -q`
Expected: FAIL — `ImportError: cannot import name 'SearchIndex'`.

- [ ] **Step 3: Implement `SearchIndex` (state + build/upsert/remove)**

Append to `python/src/nodes/kernel/search.py` (after `tokenize`). Add the imports `from collections.abc import Iterable`, `from nodes.kernel.errors import CollisionError`, `from nodes.kernel.node import Node` near the top with the existing imports:

```python
class SearchIndex:
    """In-memory inverted index over node title+body. Pure data; no file I/O."""

    def __init__(self) -> None:
        self.postings: dict[str, dict[str, tuple[int, int]]] = {}  # term -> uid -> (title_tf, body_tf)
        self.lengths: dict[str, tuple[int, int]] = {}              # uid -> (title_len, body_len)
        self.id_by_uid: dict[str, str] = {}
        self._total_title = 0
        self._total_body = 0

    @property
    def n(self) -> int:
        return len(self.lengths)

    @classmethod
    def build(cls, nodes: Iterable[Node]) -> "SearchIndex":
        idx = cls()
        for node in nodes:
            if node.uid in idx.lengths:
                raise CollisionError(f"duplicate uid {node.uid!r} in corpus")
            idx.upsert(node)
        return idx

    @staticmethod
    def _counts(tokens: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for tok in tokens:
            counts[tok] = counts.get(tok, 0) + 1
        return counts

    def upsert(self, node: Node) -> None:
        if node.uid in self.lengths:
            self._drop(node.uid)
        title_tokens = tokenize(node.title)
        body_tokens = tokenize(node.body)
        title_counts = self._counts(title_tokens)
        body_counts = self._counts(body_tokens)
        for term in title_counts.keys() | body_counts.keys():
            self.postings.setdefault(term, {})[node.uid] = (
                title_counts.get(term, 0),
                body_counts.get(term, 0),
            )
        self.lengths[node.uid] = (len(title_tokens), len(body_tokens))
        self.id_by_uid[node.uid] = node.id
        self._total_title += len(title_tokens)
        self._total_body += len(body_tokens)

    def remove(self, uid: str) -> None:
        self._drop(uid)

    def _drop(self, uid: str) -> None:
        lengths = self.lengths.pop(uid, None)
        if lengths is None:
            return
        self._total_title -= lengths[0]
        self._total_body -= lengths[1]
        del self.id_by_uid[uid]
        for term, docs in list(self.postings.items()):
            if uid in docs:
                del docs[uid]
                if not docs:
                    del self.postings[term]
```

- [ ] **Step 4: Run them to verify they pass**

Run: `rtk uv run pytest tests/test_search_index.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full gate**

Run: `rtk uv run pytest -q`
Run: `rtk uv run ruff check src tests`
Run: `rtk uv run pyright src`
Expected: all green (existing suite still passes).

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add python/src/nodes/kernel/search.py python/tests/test_search_index.py
rtk git commit -m "feat(search): SearchIndex build/upsert/remove with rebuild-equivalence"
```

---

### Task 3: BM25F scoring + `search` query API

**Files:**
- Modify: `python/src/nodes/kernel/search.py` (add constants, `score_key`, `SearchHit`, `SearchIndex.search`)
- Create: `python/tests/test_search_query.py`

**Interfaces:**
- Consumes: `SearchIndex` state from Task 2.
- Produces: constants `K1=1.5`, `B=0.75`, `TITLE_BOOST=2.0`, `BODY_BOOST=1.0`; `score_key(score: float) -> float`; `@dataclass SearchHit` with fields `id: str`, `uid: str`, `score: float`, `matched_terms: list[str]`; `SearchIndex.search(query: str, limit: int | None = None) -> list[SearchHit]`. Consumed by Tasks 4–5.

- [ ] **Step 1: Write the failing tests**

Create `python/tests/test_search_query.py`:

```python
from __future__ import annotations

import math

import pytest

from nodes.kernel.node import Node
from nodes.kernel.search import SearchHit, SearchIndex, score_key


def _two_doc_index() -> SearchIndex:
    idx = SearchIndex()
    idx.upsert(Node(id="topic:a", kind="topic", title="alpha", body="alpha beta"))
    idx.upsert(Node(id="topic:b", kind="topic", title="beta", body="gamma"))
    return idx


def test_bm25f_score_matches_hand_computation():
    # N=2, avg_title=1.0, avg_body=1.5. Query "alpha" hits only topic:a (title_tf=1, body_tf=1).
    # idf = ln(2); tf' = 2.0*1/1.0 + 1.0*1/1.25 = 2.8; score = ln(2)*2.5*2.8/(1.5+2.8).
    expected = math.log(2.0) * 2.5 * 2.8 / 4.3
    hits = _two_doc_index().search("alpha")
    assert [h.id for h in hits] == ["topic:a"]
    assert isinstance(hits[0], SearchHit)
    assert hits[0].score == pytest.approx(expected, abs=1e-12)
    assert hits[0].uid != "" and hits[0].matched_terms == ["alpha"]


def test_title_match_outranks_body_match():
    # "beta" is in topic:b's TITLE and topic:a's BODY -> title boost ranks b first.
    hits = _two_doc_index().search("beta")
    assert [h.id for h in hits] == ["topic:b", "topic:a"]


def test_rounded_score_ties_break_by_id():
    idx = SearchIndex()
    idx.upsert(Node(id="topic:b", kind="topic", title="x", body="z"))
    idx.upsert(Node(id="topic:a", kind="topic", title="x", body="z"))
    assert [h.id for h in idx.search("x")] == ["topic:a", "topic:b"]


def test_matched_terms_is_sorted_subset_present_in_doc():
    idx = SearchIndex()
    idx.upsert(Node(id="topic:a", kind="topic", title="alpha", body="gamma"))
    hits = idx.search("gamma alpha zeta")  # zeta is absent from the corpus
    assert hits[0].matched_terms == ["alpha", "gamma"]


def test_empty_stopword_and_absent_queries_return_empty():
    idx = SearchIndex()
    idx.upsert(Node(id="topic:a", kind="topic", title="alpha", body="the cat"))
    assert idx.search("") == []
    assert idx.search("   ") == []
    assert idx.search("the") == []     # stop word only
    assert idx.search("zeta") == []    # term absent


def test_limit_truncates_and_none_is_unbounded():
    idx = SearchIndex()
    for slug in ("a", "b", "c"):
        idx.upsert(Node(id=f"topic:{slug}", kind="topic", title="alpha", body="alpha"))
    assert len(idx.search("alpha")) == 3
    assert len(idx.search("alpha", limit=2)) == 2
    assert len(idx.search("alpha", limit=None)) == 3


@pytest.mark.parametrize("bad", [0, -1, 1.0, True, "1"])
def test_search_rejects_bad_limit(bad):
    idx = SearchIndex()
    idx.upsert(Node(id="topic:a", kind="topic", title="alpha", body=""))
    with pytest.raises(ValueError):
        idx.search("alpha", limit=bad)


def test_score_key_rounds_to_6dp():
    # Inputs kept clear of the exact .5 boundary so float representation can't flip them.
    assert score_key(1.2345674) == 1.234567   # rounds down
    assert score_key(1.2345678) == 1.234568   # rounds up
    assert score_key(0.0) == 0.0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `rtk uv run pytest tests/test_search_query.py -q`
Expected: FAIL — `ImportError: cannot import name 'SearchHit'` (and `score_key`, `search`).

- [ ] **Step 3: Implement scoring + `search`**

In `python/src/nodes/kernel/search.py`, add `import math` and `from dataclasses import dataclass` to the imports. Add the constants and `score_key` near the top (after `_TOKEN_RE`):

```python
K1 = 1.5
B = 0.75
TITLE_BOOST = 2.0
BODY_BOOST = 1.0


def score_key(score: float) -> float:
    """Half-up rounding to 6 decimal places — the shared ranking/parity key.

    Scores are non-negative, so this floor-based half-up is correct and identical
    in both languages.
    """
    return math.floor(score * 1_000_000 + 0.5) / 1_000_000
```

Add the `SearchHit` dataclass just above the `SearchIndex` class:

```python
@dataclass
class SearchHit:
    id: str
    uid: str
    score: float
    matched_terms: list[str]
```

Add the `search` method to `SearchIndex` (after `remove`):

```python
    def search(self, query: str, limit: int | None = None) -> list[SearchHit]:
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
            raise ValueError(f"limit must be a positive int or None, got {limit!r}")
        terms = sorted(set(tokenize(query)))  # dedup; Python str sort is code-point order
        if not terms:
            return []

        n = self.n
        avg_title = self._total_title / n if n else 0.0
        avg_body = self._total_body / n if n else 0.0

        scores: dict[str, float] = {}
        matched: dict[str, list[str]] = {}
        for term in terms:
            docs = self.postings.get(term)
            if not docs:
                continue
            df = len(docs)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for uid, (title_tf, body_tf) in docs.items():
                title_len, body_len = self.lengths[uid]
                tf_prime = 0.0
                if title_tf:
                    denom = (1 - B + B * (title_len / avg_title)) if avg_title else 1.0
                    tf_prime += TITLE_BOOST * title_tf / denom
                if body_tf:
                    denom = (1 - B + B * (body_len / avg_body)) if avg_body else 1.0
                    tf_prime += BODY_BOOST * body_tf / denom
                scores[uid] = scores.get(uid, 0.0) + idf * (K1 + 1) * tf_prime / (K1 + tf_prime)
                matched.setdefault(uid, []).append(term)

        hits = [
            SearchHit(id=self.id_by_uid[uid], uid=uid, score=scores[uid], matched_terms=sorted(matched[uid]))
            for uid in scores
        ]
        hits.sort(key=lambda h: (-score_key(h.score), h.id))
        return hits if limit is None else hits[:limit]
```

- [ ] **Step 4: Run them to verify they pass**

Run: `rtk uv run pytest tests/test_search_query.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full gate**

Run: `rtk uv run pytest -q`
Run: `rtk uv run ruff check src tests`
Run: `rtk uv run pyright src`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add python/src/nodes/kernel/search.py python/tests/test_search_query.py
rtk git commit -m "feat(search): BM25F scoring + ranked search query API"
```

---

### Task 4: Corpus integration

**Files:**
- Modify: `python/src/nodes/kernel/corpus.py` (`__init__`, `add`, `delete`, `rename`, new `search`)
- Create: `python/tests/test_corpus_search.py`

**Interfaces:**
- Consumes: `SearchIndex`, `SearchHit` (Task 3); existing `Corpus`/`Index`/`Store`.
- Produces: `Corpus.search_index: SearchIndex`; `Corpus.search(query: str, limit: int | None = None) -> list[SearchHit]`.

- [ ] **Step 1: Write the failing tests**

Create `python/tests/test_corpus_search.py`:

```python
from __future__ import annotations

from nodes.kernel.corpus import Corpus
from nodes.kernel.node import Node


def _seed(c: Corpus) -> None:
    c.add(Node(id="topic:a", kind="topic", title="alpha", body="alpha beta"))
    c.add(Node(id="topic:b", kind="topic", title="beta", body="gamma"))


def test_search_ranks_title_above_body_after_add(tmp_path):
    c = Corpus(tmp_path)
    _seed(c)
    assert [h.id for h in c.search("beta")] == ["topic:b", "topic:a"]


def test_search_reflects_delete(tmp_path):
    c = Corpus(tmp_path)
    _seed(c)
    c.delete("topic:b")
    assert [h.id for h in c.search("beta")] == ["topic:a"]  # only the body match remains


def test_search_reflects_rename(tmp_path):
    c = Corpus(tmp_path)
    _seed(c)
    c.rename("topic:a", "topic:a2")
    hits = c.search("alpha")
    assert [h.id for h in hits] == ["topic:a2"]  # hit carries the new id


def test_search_index_rebuilds_from_disk(tmp_path):
    c = Corpus(tmp_path)
    _seed(c)
    fresh = Corpus(tmp_path)  # second corpus scans the same dir
    assert [h.id for h in fresh.search("beta")] == [h.id for h in c.search("beta")]


def test_limit_is_honored_through_corpus(tmp_path):
    c = Corpus(tmp_path)
    _seed(c)
    assert len(c.search("beta", limit=1)) == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `rtk uv run pytest tests/test_corpus_search.py -q`
Expected: FAIL — `AttributeError: 'Corpus' object has no attribute 'search'`.

- [ ] **Step 3: Wire the search index into `Corpus`**

In `python/src/nodes/kernel/corpus.py`, add the import alongside the others:

```python
from nodes.kernel.search import SearchHit, SearchIndex
```

Replace `Corpus.__init__` body so both indexes build from one scan:

```python
    def __init__(self, root: Path, registry: Registry | None = None) -> None:
        self.store = Store(root)
        self.registry = registry
        nodes = self.store.all_nodes()
        self.index = Index.build(nodes)
        self.search_index = SearchIndex.build(nodes)
```

In `add`, append the search upsert after the structural upsert:

```python
    def add(self, node: Node) -> Node:
        if self.registry is not None:
            self.registry.validate(node)
        self.index.assert_addable(node)
        self.store.write_file(node)
        self.index.upsert(node)
        self.search_index.upsert(node)
        return node
```

In `delete`, append the search remove after the structural remove:

```python
    def delete(self, node_id: str) -> None:
        uid = self.index.id_to_uid.get(node_id)
        if uid is None:
            raise RefError(f"no live node at {node_id!r}")
        self.store.delete_file(node_id)
        self.index.remove(uid)
        self.search_index.remove(uid)
```

In `rename`, add the single search upsert immediately before `return node` (after the existing referrer-write loop):

```python
        self.search_index.upsert(node)
        return node
```

Add the `search` method (e.g. after `neighbors`):

```python
    def search(self, query: str, limit: int | None = None) -> list[SearchHit]:
        return self.search_index.search(query, limit)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `rtk uv run pytest tests/test_corpus_search.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full gate**

Run: `rtk uv run pytest -q`
Run: `rtk uv run ruff check src tests`
Run: `rtk uv run pyright src`
Expected: all green — including the existing corpus/index/rebuild-equivalence suites (Corpus behavior is otherwise unchanged).

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes
rtk git add python/src/nodes/kernel/corpus.py python/tests/test_corpus_search.py
rtk git commit -m "feat(search): Corpus.search + keep search index current on add/delete/rename"
```

---

### Task 5: Cross-language ranking oracle + docs

**Files:**
- Create: `fixtures/search-corpus/topic/search.md`, `fixtures/search-corpus/topic/graph.md`, `fixtures/search-corpus/topic/index.md`, `fixtures/search-corpus/topic/relevance.md`
- Create: `python/scripts/gen_search_oracle.py`
- Create: `fixtures/search.oracle.json` (generated)
- Create: `python/tests/test_search_parity.py`
- Modify: `docs/format.md`

**Interfaces:**
- Consumes: `Corpus.search` (Task 4); `score_key` (Task 3).
- Produces: the committed fixture corpus + ranking oracle + a parity test asserting `Corpus.search` reproduces it. The later TS port runs the same fixture/oracle.

- [ ] **Step 1: Author the fixture corpus (exact bytes)**

Create the four files below. uids are quoted 32-char hex strings (containing letters) so both YAML parsers read them as strings, matching the existing `fixtures/corpus/` convention. Each file is frontmatter then a one-line body.

`fixtures/search-corpus/topic/search.md`:

```markdown
---
id: topic:search
uid: "0a1b2c3d4e5f60718293a4b5c6d7e8f9"
kind: topic
title: Search
---
full text search ranks documents by relevance using term frequency
```

`fixtures/search-corpus/topic/graph.md`:

```markdown
---
id: topic:graph
uid: "1a2b3c4d5e6f70819203a4b5c6d7e8fa"
kind: topic
title: Graph
---
the relation graph resolves references between documents
```

`fixtures/search-corpus/topic/index.md`:

```markdown
---
id: topic:index
uid: "2a3b4c5d6e7f80910213a4b5c6d7e8fb"
kind: topic
title: Index
---
a derived index makes search fast over many documents
```

`fixtures/search-corpus/topic/relevance.md`:

```markdown
---
id: topic:relevance
uid: "3a4b5c6d7e8f90112233a4b5c6d7e8fc"
kind: topic
title: Relevance and ranking
---
ranking documents by relevance is what search returns
```

- [ ] **Step 2: Write the ranking-oracle generator**

Create `python/scripts/gen_search_oracle.py`. It builds a `Corpus` over the committed fixture corpus (read-only) and writes ranked `{id, score}` (score via `score_key`) per query:

```python
from __future__ import annotations

import json
from pathlib import Path

from nodes.kernel.corpus import Corpus
from nodes.kernel.search import score_key

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "search-corpus"
ORACLE = FIXTURES / "search.oracle.json"

QUERIES = ["search", "documents ranking", "relevance"]


def main() -> None:
    corpus = Corpus(CORPUS)
    cases = []
    for query in QUERIES:
        hits = corpus.search(query)
        cases.append(
            {"query": query, "hits": [{"id": h.id, "score": score_key(h.score)} for h in hits]}
        )
    ORACLE.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Generate the oracle**

Run: `rtk uv run python scripts/gen_search_oracle.py`
Expected: writes `fixtures/search.oracle.json`. Sanity-check it: for query `"search"`, `topic:search` must rank first (it is the only doc with the term in its title, so the title boost wins); every listed `score` must be a positive number with at most 6 decimal places; each query's hits are in non-increasing score order.

- [ ] **Step 4: Write the parity test**

Create `python/tests/test_search_parity.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

from nodes.kernel.corpus import Corpus
from nodes.kernel.search import score_key

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CORPUS = FIXTURES / "search-corpus"
ORACLE = FIXTURES / "search.oracle.json"


def test_search_ranking_matches_committed_oracle(tmp_path):
    # Currency + cross-language freeze: Corpus.search over the committed fixture corpus
    # must reproduce the committed ranking oracle exactly (ranked ids + 6-dp scores).
    # The later TypeScript port asserts the same fixture + oracle.
    corpus_dir = tmp_path / "search-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    corpus = Corpus(corpus_dir)
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle, "oracle must not be empty"
    for case in oracle:
        hits = corpus.search(case["query"])
        actual = [{"id": h.id, "score": score_key(h.score)} for h in hits]
        assert actual == case["hits"], case["query"]


def test_search_corpus_has_four_topics(tmp_path):
    corpus_dir = tmp_path / "search-corpus"
    shutil.copytree(CORPUS, corpus_dir)
    assert len(Corpus(corpus_dir).all()) == 4
```

- [ ] **Step 5: Run the parity test**

Run: `rtk uv run pytest tests/test_search_parity.py -q`
Expected: PASS.

- [ ] **Step 6: Update `docs/format.md`**

In the "### Known kernel limitations (resolved in later plans)" list, replace this line:

```markdown
- No full-text search or embeddings/similarity index yet.
```

with:

```markdown
- No embeddings/similarity index yet. (Full-text search is now implemented in the
  Python kernel — see "Full-text search (derived index)" below; the TypeScript port
  is a later plan.)
```

Then append this section to the end of `docs/format.md`:

```markdown
## Full-text search (derived index)

The Python kernel ships a second derived index beside the structural `Index`: an
in-memory BM25F full-text search index (`nodes.kernel.search`). `Corpus` builds it
from the same `all_nodes()` scan, keeps it current on `add`/`delete`/`rename`, and
exposes `Corpus.search(query, limit=None) -> list[SearchHit]`.

- **Tokenizer.** NFC-normalize → lowercase → split into Unicode-alphanumeric runs
  → drop a fixed 33-word stop list; no stemming. Pinned across languages by
  `fixtures/search.tokenizer.json`.
- **Scoring.** BM25F over two fields (`title` boosted above `body`) with the
  standard `(K1 + 1)` numerator and a non-negative Lucene IDF. Constants `K1=1.5`,
  `B=0.75`, `TITLE_BOOST=2.0`, `BODY_BOOST=1.0`.
- **Results.** Ranked `SearchHit`s (`id`, `uid`, `score`, `matched_terms`), sorted
  by a 6-decimal half-up `score_key` then `id`. The caller hydrates the `Node` via
  `Corpus.get` when it needs the text.
- **Parity.** A fixture corpus (`fixtures/search-corpus/`) plus a ranking oracle
  (`fixtures/search.oracle.json`) pin ranked ids and 6-dp scores; both languages
  build the index and assert equality. Scores are not claimed bit-identical.

This is in-memory and rebuilt on `Corpus` construction; on-disk persistence is a
later plan.
```

- [ ] **Step 7: Run the full gate**

Run: `rtk uv run pytest -q`
Run: `rtk uv run ruff check src tests`
Run: `rtk uv run pyright src`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
cd ~/d/nodes
rtk git add fixtures/search-corpus python/scripts/gen_search_oracle.py fixtures/search.oracle.json python/tests/test_search_parity.py docs/format.md
rtk git commit -m "test(search): cross-language ranking oracle + fixture corpus; docs"
```

---

## Self-Review

**1. Spec coverage** (design doc §-by-§):
- §2 placement (`kernel/search.py`, `tokenize`/`SearchIndex`/`SearchHit`; Corpus owns + queries) → Tasks 1–4 ✅
- §3 tokenizer (NFC→lower→`[^\W_]+`→stop words; consequences; empty input) → Task 1 ✅
- §3.1 33-word stop list (exact) → Task 1 (`STOP_WORDS`, length-33 test) ✅
- §3.2 tokenizer oracle built first (all listed cases incl. NFD↔NFC, mixed scripts, non-BMP) → Task 1 ✅
- §4 BM25F (IDF, per-field tf' with `avglen_f==0` guard, `(K1+1)` numerator, deduped doc score) → Task 3 ✅
- §4.1 constants → Task 3 ✅
- §4.2 determinism (sorted-set code-point terms, fixed field order, `score_key`, sort key) → Task 3 ✅
- §5 SearchIndex state + build(dup-uid→CollisionError)/upsert(replace)/remove(no-op)/empty-doc slot → Task 2 ✅
- §6 `SearchHit`, `Corpus.search` flow, sort, `matched_terms`, lazy hydration → Tasks 3–4 ✅
- §7 single-scan `__init__`; add/delete disk-then-both; rename single search upsert → Task 4 ✅
- §8 ranking oracle (fixture corpus + `search.oracle.json`; both languages assert) → Task 5 ✅
- §9 testing (tokenizer, scorer hand-computed, build/upsert/remove, rebuild-equivalence, Corpus integration incl. rename tie→id, parity) → Tasks 1–5 ✅
- §10 error handling (`limit` ValueError incl. bool/non-int/≤0; zero matches → []; build CollisionError; no new error types) → Tasks 2–3 ✅
- §11/§12 resolved decisions / deferrals → respected; deferrals (stemming, snippets, facet indexing, persistence) not built ✅

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N". Every code/test step carries full code. The two generated fixtures (`search.tokenizer.json`, `search.oracle.json`) are produced by committed generator scripts with exact inputs, each followed by an explicit sanity-check and a test that re-asserts reproduction — the same regenerate-and-diff pattern as the existing emit/parity fixtures, not a placeholder.

**3. Type consistency:** `tokenize(str)->list[str]`, `SearchIndex` attrs (`postings`/`lengths`/`id_by_uid`/`_total_title`/`_total_body`/`n`) and methods (`build`/`upsert`/`remove`/`search`), `SearchHit(id,uid,score,matched_terms)`, `score_key(float)->float`, and `Corpus.search(query,limit=None)->list[SearchHit]` are used identically across Tasks 1–5 and match the spec names. Postings shape `term->uid->(title_tf, body_tf)` is consistent in Tasks 2–3. `CollisionError`/`ValueError` are the only raised types, per §10.
