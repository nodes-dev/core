# nodes — Knowledge Vocab Layer (Design)

- **Status:** Draft (design approved, pending spec review)
- **Date:** 2026-06-21
- **Scope:** Plan 3 of the `nodes` roadmap. Builds the *knowledge vocab* layer (substrate
  design §2) one layer above the domain-free kernel, and wires the kernel's registry into the
  write path so the vocabulary is actually enforced.
- **Depends on:** Plan 1 (Python kernel) and Plan 2 (structural index / `Corpus`), both merged.

## 1. Motivation & goals

The substrate architecture (§2) defines three layers with a strict downward dependency:
`domain → knowledge vocab → kernel`. Plans 1–2 delivered the kernel (`Node`, `Relation`,
`Registry`/`KindSpec`, structural shapes, `Store`, `Index`, `Corpus`). The kernel is ruthlessly
domain-free: it ships **zero named knowledge kinds**.

This plan adds the **knowledge vocab**: a standard, separately-importable profile of
generally-useful knowledge-representation kinds. It mirrors the kernel's own
`register_builtin_shapes(reg)` pattern — a profile module that registers `KindSpec`s (plus the
facet models and invariants they need) onto a `Registry`.

It also closes a gap exposed during design: the `Registry` is currently **orphaned from the
write path**. `Corpus.add` performs collision-checking, file write, and index upsert, but never
calls `reg.validate(node)`; registry validation exists only as a standalone function exercised
in tests. A vocabulary nothing validates against is inert, so this plan wires an **optional
registry** into `Corpus`.

### Goals

- Ship `nodes.vocab`: a profile of seven knowledge kinds, depending only on `nodes.kernel`.
- Define one shared, typed `Source` facet for the bibliographic kinds, with a fail-early
  invariant — reusing the kernel's facet/invariant pattern (`Membership` in `shapes.py`).
- Ship a small set of canonical relation predicates as a shared vocabulary.
- Make the registry enforceable through the primary API by giving `Corpus` an optional
  registry, validating on `add` and `rename`.

### Non-goals (deferred — YAGNI)

- **Domain kinds** (science: hypothesis/evidence-line/…; mindful: thought/mindmap/…). Those
  are downstream profiles that compose on this layer.
- **A distinct `Dataset` facet** (format / location / schema). `dataset` uses the shared
  `Source` facet for now; a richer dataset facet waits for a real consumer.
- **Predicate enforcement.** Predicates remain free-string at the kernel level; the vocab ships
  canonical *names*, not target-kind constraints.
- **Parse-time validation.** Wiring the registry into frontmatter deserialization is a separate
  concern; this plan enforces at the `Corpus` write boundary only.
- **Embeddings / full-text / similarity** — separate plans (substrate §5 deferrals).

## 2. Architecture & layering

```
src/nodes/vocab/
  __init__.py     re-exports: register_knowledge_vocab, kind constants, Source, source_of, predicates
  source.py       Source facet model + source_of() accessor + require_identifiable_source invariant
  kinds.py        kind-name constants + KindSpec registrations + register_knowledge_vocab(reg)
  predicates.py   canonical predicate constants + thin helper constructors
```

`nodes.vocab` imports from `nodes.kernel` only. The kernel never imports `nodes.vocab` (the
dependency direction the substrate mandates). The layer is purely additive except for the one
`Corpus` change in §6.

## 3. The roster — seven kinds

| Kind | Required facets | Invariants | Notes |
|------|-----------------|------------|-------|
| `note` | — | — | Neutral prose container. Mindful's `thought` = note + VisualIdentity (downstream) builds on this concept. |
| `idea` | — | — | A proposed / speculative concept (a hypothesis precursor). Distinct from `note`. |
| `question` | — | — | An open inquiry. |
| `topic` | — | — | An organizing subject node. |
| `paper` | `source` | `require_identifiable_source` | Bibliographic. |
| `book` | `source` | `require_identifiable_source` | Bibliographic. |
| `dataset` | `source` | `require_identifiable_source` | Bibliographic (shares `Source` for now). |

The four **prose kinds** are *bare*: they register a name with no required facets. The kernel
registry's existing check (`unexpected = present - allowed`) means a stray facet on a prose kind
is rejected (fail-early) — a `note` carrying a `source` facet is an error.

The three **source kinds** require the `source` facet and carry the identifiability invariant.

Kind names are exported as module constants (`NOTE`, `IDEA`, `QUESTION`, `TOPIC`, `PAPER`,
`BOOK`, `DATASET`) and grouped (`PROSE_KINDS`, `SOURCE_KINDS`) so the registration loop and tests
share one source of truth.

## 4. The `Source` facet

A shared bibliographic payload for `paper` / `book` / `dataset`. Mirrors the `Membership` facet
pattern in `shapes.py`: a Pydantic model + an `_of(node)` accessor + invariant functions.

```python
SOURCE = "source"

class Source(BaseModel):
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    container: str | None = None   # journal / publisher / repository
    identifier: str | None = None  # DOI / ISBN / accession id
    url: str | None = None

def source_of(node: Node) -> Source:
    raw = node.facets.get(SOURCE)
    if raw is None:
        raise FacetError(f"{node.id}: missing '{SOURCE}' facet")
    return Source.model_validate(raw)

def require_identifiable_source(node: Node) -> None:
    s = source_of(node)
    if not (s.authors or s.year or s.identifier or s.url):
        raise InvariantError(
            f"{node.id}: source facet needs at least one of authors/year/identifier/url"
        )
```

Design notes:

- **No `type`/discriminator field.** The node's `kind` already says paper vs book vs dataset.
- **No `title` field.** `Node.title` already holds the work's display title; `Source` is *only*
  bibliographic metadata, avoiding a second source of truth.
- The invariant rejects an empty `Source` facet — a bibliographic node with no authors, year,
  identifier, or url carries no bibliographic information and is an error (explicit > defensive).
- `source_of` raising `FacetError` on a missing facet is belt-and-suspenders: the registry's
  `required_facets` check already guarantees presence for the source kinds, but `source_of` is a
  public accessor usable independently, so it fails early on misuse.

## 5. Predicates

`nodes.vocab.predicates` ships canonical predicate **names** as constants, plus thin
`relates_to`-style helper constructors. This is a *shared vocabulary*, not enforced by the
kernel — `Relation.predicate` remains a free string. Intended source → target kinds are
documented in each helper's docstring but not validated.

| Constant | Value | Intended use |
|----------|-------|--------------|
| `ABOUT` | `"about"` | any node → `topic` |
| `CITES` | `"cites"` | any node → `paper`/`book`/`dataset` |
| `ANSWERS` | `"answers"` | `note`/`idea` → `question` |
| `ASKS` | `"asks"` | any node → `question` (raises one) |
| `REFINES` | `"refines"` | any node → node (builds on / supersedes) |

Each constant has a paired helper that mirrors the kernel's `relates_to(source, target)`:

```python
def about(source: str, target: str) -> Relation:
    return Relation(source=source, predicate=ABOUT, target=target)
# ...likewise cites / answers / asks / refines
```

The kernel's `RELATES_TO` already covers untyped links; the vocab does not re-export it.

## 6. Registry → Corpus wiring (the one kernel change)

`Corpus` gains an **optional** `registry` parameter. This is the only change to a Plan-1/Plan-2
file.

```python
class Corpus:
    def __init__(self, root: Path, registry: Registry | None = None) -> None:
        self.store = Store(root)
        self.registry = registry
        self.index = Index.build(self.store.all_nodes())

    def add(self, node: Node) -> Node:
        if self.registry is not None:
            self.registry.validate(node)   # fail-early, before collision-check/write
        self.index.assert_addable(node)
        self.store.write_file(node)
        self.index.upsert(node)
        return node
```

`rename` validates the **renamed node** after its own refs are rewritten and *before* any file
is written:

```python
def rename(self, old_id: str, new_id: str) -> Node:
    # ... existing guards (old_id live, new_id free) ...
    node = self.store.read_file(old_id)
    # ... set node.id/kind, append deprecated_id, _rewrite_refs(node, old_id, new_id) ...
    if self.registry is not None:
        self.registry.validate(node)       # rename can change kind; reject before any write
    new_path = self.store.write_file(node)
    # ... delete-old-if-path-changed, upsert, rewrite referrers ...
```

Semantics:

- **`registry=None`** preserves today's behavior exactly — a deliberate, documented composition
  default (not a silent fallback). All existing `Corpus` tests pass unchanged.
- **`registry` present** rejects any node whose kind is unregistered (`UnknownKindError`) or
  whose facets/invariants fail (`FacetError` / `InvariantError`) — enforcing the closed
  vocabulary fail-early, before any disk write.
- **`rename` validates only the renamed node**, not referrers. A rename can change a node's
  `kind` (e.g. `topic:x` → `note:y`); if the resulting facets don't fit the new kind, the rename
  is rejected before any write. Referrers are *not* re-validated: their kind/facets are
  unchanged, only ref strings are rewritten, and re-validating them could surface pre-existing
  invalidity unrelated to the rename.

## 7. Error handling

All errors reuse the kernel's existing hierarchy (`nodes.kernel.errors`):

- Missing required facet → `FacetError` (from `Registry.validate` and from `source_of`).
- Unexpected facet on a bare kind → `FacetError` (from `Registry.validate`).
- Empty `Source` facet → `InvariantError` (from `require_identifiable_source`).
- Unregistered kind on a registry-backed `Corpus` → `UnknownKindError` (from `Registry.get`).

No new error types are introduced.

## 8. Testing

- **`test_vocab_source.py`** — `Source` defaults; `source_of` on a node missing the facet →
  `FacetError`; `require_identifiable_source` on an empty source → `InvariantError`; a populated
  source passes; the facet round-trips through `node.facets` (dict in, `Source` out).
- **`test_vocab_kinds.py`** — `register_knowledge_vocab` registers all seven; a bare `note`
  validates; `note` + a stray facet → `FacetError`; each source kind missing `source` →
  `FacetError`, with an empty `source` → `InvariantError`, with a valid `source` passes; an
  unregistered kind → `UnknownKindError`.
- **`test_vocab_predicates.py`** — each constant has the documented string value; each helper
  builds a `Relation` with the correct `predicate`, `source`, and `target`.
- **`test_corpus_registry.py`** — a `Corpus` built without a registry behaves exactly as before
  (add any kind, no validation); a `Corpus` built with a vocab+shapes registry rejects an
  invalid node on `add` **with no file written**; a valid node is added; `rename` validates the
  renamed node (a rename into a kind whose facets don't fit is rejected, **no file written**);
  a valid rename passes. The existing 86-test suite stays green (registry defaults to `None`).

## 9. Docs

Add a **"Knowledge vocab (Plan 3)"** section to `docs/format.md`: the seven-kind roster, the
`Source` facet shape, the predicate vocabulary, and the `Corpus` optional-registry wiring, plus a
one-line statement of the `vocab → kernel` layering direction.

## 10. Why this shape

- **Composition over inheritance:** kinds are name + facets + invariants, registered on a
  `Registry` — no subclass chains. `idea` and `note` are sibling bare kinds; the three
  bibliographic kinds compose the same `Source` facet.
- **Explicit over defensive / fail early:** the identifiability invariant rejects an empty
  source; a registry-backed `Corpus` rejects unregistered kinds and facet violations *before*
  writing to disk.
- **Plumbing/domain separation stays structural:** `nodes.vocab` depends only on the kernel and
  introduces no domain semantics; the kernel remains free of named knowledge kinds.
