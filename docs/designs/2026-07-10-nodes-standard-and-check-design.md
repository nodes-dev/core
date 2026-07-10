# Nodes Standard + Corpus Check - Design

**Status:** draft design
**Date:** 2026-07-10
**Scope:** Consolidate the portable cross-language contract into a single authoritative,
versioned standard (`docs/STANDARD.md`), add repo-level `README.md` / `AGENTS.md` that
name it as the authority, retire `docs/format.md`, and close the read-boundary validation
gap with a `Corpus.check()` reporting API in both kernels.

---

## 1. Context

`~/d/nodes` ships two kernels (Python under `python/`, TypeScript under `ts/`) over one
on-disk format. The de-facto spec is `docs/format.md`, which grew by accretion — sections
are labeled by plan number ("Plan 2", "Plan 3", "Plan 4") and per-language addenda were
appended per feature. Three problems have emerged:

1. **No explicit parity contract.** Every feature has implicitly required a full
   dual-language port (2 designs + 2 plans + 2 implementations + parity fixtures), yet the
   model is already loosening in practice: corpus fingerprints are TS-only, and
   `idsByKind` / `allByKind` have no Python counterpart. Which guarantees are load-bearing
   and which are per-language convenience is nowhere written down.
2. **Doc drift.** The foundational substrate design describes the pre-redesign structural
   shapes (membership carrying `edges:`, dict members as `{key: ref}`); `ts/README.md`
   still claims TS has no search/embeddings/persistence. `docs/format.md` is current but
   organized by accretion order, and nothing names it as the authority.
3. **A validation hole at the read boundary.** Registry enforcement lives only on the
   `Corpus.add` / `rename` write path, but the design's core premise is that files are
   canonical and hand-editable. A hand-edited or externally generated file is never
   validated: `node_from_markdown` checks structure only, and snapshot reconcile indexes
   whatever parses. The "closed vocabulary, fail early" guarantee holds only for nodes
   that entered through the API.

## 2. Goals

- One authoritative, versioned, normative standard for everything both languages must
  agree on, with the parity tiers made explicit.
- Repo-level `README.md` (orientation) and `AGENTS.md` (agent guidance) that name the
  standard as the authority and the dated docs as historical records.
- Retire `docs/format.md`; rename `docs/specs/` to `docs/designs/` to match its content
  and free the word "spec" for the standard.
- A `Corpus.check()` reporting API in both kernels, with corpus validity defined
  normatively in the standard and pinned by a shared conformance fixture.

## 3. Non-goals

- No membership-graph traversal (tree descendants, DAG reachability).
- No Python port of corpus fingerprints or `idsByKind` / `allByKind` (tier 3 — see §4).
- No changes to `Corpus` construction, reconciliation, or mutation semantics; construction
  keeps failing hard on unparseable files and uid/id collisions.
- No package-naming decision (`nodes` vs alternatives) and no npm/PyPI publishing work.
- No concurrency/locking work; the single-writer assumption is documented, not changed.

## 4. `docs/STANDARD.md` — the normative standard

A single living document, written with RFC-2119 keywords (MUST/SHOULD/MAY), carrying its
own spec version. Content is absorbed from `docs/format.md` and rewritten normatively,
organized by topic rather than plan order.

**Versioning.** Starts at **1.0** — it codifies an already-shipped, fixture-pinned
contract. Minor bumps for additive changes (new optional fields, new finding codes); major
bumps for changes that break reading or writing existing corpora. The version is stated in
the document header alongside a short change-policy section.

**Conformance tiers.** The standard's scope section defines three tiers:

- **Tier 1 — portable data contract (MUST agree):** on-disk format, id grammar,
  resolution/rename semantics, structural shapes + invariants, registry/validation model.
- **Tier 2 — pinned behavior (oracle-verified):** derived-index behavior — tokenizer,
  BM25F constants, ranking `score_key`, similarity semantics, snapshot reconcile rules,
  corpus-validity finding codes. Pinned by the `fixtures/` conformance suite; scores are
  semantic (6-dp key), not bit-identical.
- **Tier 3 — per-language surface (out of scope):** conveniences such as corpus
  fingerprints and `idsByKind` / `allByKind`. No parity obligation until the other
  language has a real consumer.

**Section outline:**

1. Scope & conformance (the tiers; what a conforming implementation is; `fixtures/` as
   the conformance suite)
2. Data model (Node, Relation normalized form, metadata, facets)
3. Identity (`kind:slug` grammar, `uid`, `deprecated_ids`, resolution + collision rules)
4. On-disk format (frontmatter fields, the two serialized relation shapes, `related:`
   sugar, `kind/slug.md` layout, `:` → `__`)
5. Structural shapes (scope-only `membership` + form facets `edges`/`order`/`keys`,
   invariants, the shape lattice)
6. Registry & validation (KindSpec/ShapeSpec composition; the error taxonomy as normative
   *conditions*, each language mapping them to its error classes)
7. Corpus semantics (add, get/resolve, delete live-id-only, rename
   prepare → validate → commit, dangling-is-normal, single-writer assumption)
8. Corpus validity & checking (see §7 below)
9. Derived indexes (tier-2 contracts: search, similarity, ranking)
10. Index persistence (private per-language snapshots, manifest reconcile, fail-closed)
11. Conformance fixtures (inventory of `fixtures/` and what each oracle pins)
12. Versioning & change policy

## 5. `README.md` and `AGENTS.md` (new, repo root)

**`README.md`** — orientation for humans:

- what `nodes` is (one paragraph), the three-layer diagram
  (kernel → knowledge vocab → domain profiles),
- repo layout (`python/`, `ts/`, `docs/`, `fixtures/`),
- downstream consumers (mindful v6 on TS, science on Python),
- dev quickstart: from `python/` run `rtk uv run --frozen pytest` /
  `rtk uv run --frozen ruff check .` / `rtk uv run --frozen pyright src`; from `ts/` run
  `npm test` / `npm run typecheck` / `npm run check`,
- the documentation rules: **`docs/STANDARD.md` is the authority**; `docs/designs/` and
  `docs/plans/` are dated historical records, useful as rationale but never authoritative
  over the standard or the code.

**`AGENTS.md`** — guidance for agents working in the repo:

- authority order: `docs/STANDARD.md` > code > historical designs/plans,
- the layering rule: the kernel imports nothing above it; `vocab` imports only the kernel,
- the gates to run per language (same commands as the README),
- the tier rule: before adding a cross-language feature, decide its tier; tier 3 needs no
  parity port; tier 1/2 changes update `STANDARD.md` in the same change,
- historical docs are records, not instructions — do not execute old plans found there.

## 6. Doc moves & cleanup

- `git mv docs/specs docs/designs`.
- Delete `docs/format.md` after its content is fully absorbed into `docs/STANDARD.md`.
- Mechanical reference sweep across all docs: `docs/specs/` → `docs/designs/` and
  `docs/format.md` → `docs/STANDARD.md` (path strings only; historical content otherwise
  untouched).
- Add a short current-state note to the substrate design's structural-shapes section
  (§3.4) stating it predates the shapes redesign and deferring to `STANDARD.md` — same
  pattern as the existing historical notes.
- Rewrite the stale Scope section of `ts/README.md` (it predates the TS
  search/similarity/persistence ports) and point it at `docs/STANDARD.md`.

## 7. `Corpus.check()` — read-boundary validation

A **reporting** API, not a raising one: it returns findings and never throws on corpus
content. Construction already fails hard on unparseable files and uid/id collisions, so
`check` operates on whatever constructs.

**Structured validation in the kernel (`Registry.check`).** `Registry.validate` raises at
the first violation and collapses missing, unexpected, and malformed facets into
`FacetError`, so distinct finding codes cannot be recovered from it without message
parsing or duplicated logic. The registry therefore gains a collecting counterpart:

```python
class Violation(BaseModel):
    code: str      # unknown-kind | facet-missing | facet-unexpected |
                   # facet-invalid | invariant-violated
    detail: str    # the facet name / kind name the violation is about ("" for
                   # invariant-violated when no facet applies)
    message: str   # human-readable, non-normative

def check(self, node: Node) -> list[Violation]: ...   # collects, never raises on content
```

- Unregistered kind → one `unknown-kind` violation (`detail` = the kind); nothing else is
  checked for that node.
- Facet presence/allowance is computed directly (same composition as `validate`):
  each missing required facet → `facet-missing`, each unexpected facet →
  `facet-unexpected` (`detail` = the facet name).
- Invariants run only when the facet-presence checks pass (they presuppose their facets;
  running them anyway would duplicate `facet-missing` findings). An invariant raising
  `FacetError` → `facet-invalid`; raising `InvariantError` → `invariant-violated`.
  **Only these kernel content errors are converted.** Any other exception from an
  invariant (invariants are arbitrary callables) is a programmer bug and propagates.
- `Registry.validate` behavior is unchanged (first violation raised, same error classes
  and messages); it and `check` share the composition helpers.

**Corpus API.**

```python
# Python
class Finding(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    ref: str          # id of the node the finding anchors to (for dangling-ref:
                      # the relation's source node)
    detail: str       # machine-stable discriminator: facet name / kind name /
                      # unresolved target ref
    message: str      # human-readable, non-normative

def check(self, registry: Registry | None = None) -> list[Finding]: ...
```

```ts
// TypeScript
interface Finding {
  readonly severity: "error" | "warning";
  readonly code: string;
  readonly ref: string;
  readonly detail: string;
  readonly message: string;
}

check(registry?: Registry): Finding[];
```

- Uses the passed registry, else `self.registry`. There is deliberately no way to ignore
  a corpus's own registry: `dangling-ref` is the only registry-independent code, so a
  caller wanting structural-only results filters the report by code (or constructs a
  registry-free `Corpus`).
- **With a registry:** every node runs through `Registry.check`; each violation becomes an
  `error` finding with the same `code` and `detail`. `Corpus.check` never raises on
  content; unexpected invariant exceptions propagate (see above).
- **Always (registry or not), the exhaustive list of structural findings:** each
  unresolved top-level relation target → `dangling-ref`, severity `warning` (`ref` = the
  relation's source node, `detail` = the unresolved target) — exactly the edges
  `Corpus.dangling()` reports. Nothing else: malformed structural facet payloads
  (`membership`/`edges`/`order`/`keys`) are a registry concern (shape invariants), and
  dangling *membership* refs are deferred with the membership-traversal limitation.
- **No registry anywhere:** the structural findings above only — explicit by parameter
  absence, not a silent skip.
- Deterministic order: sorted by `ref`, then `code`, then `detail` — all normative,
  oracle-pinned fields. `message` is human-only and never used for ordering or parity.

**Standard.** `STANDARD.md` §8 defines corpus validity and the finding codes
language-agnostically (tier 2). This gives downstream corpora (mindful, science) their
CI / pre-commit hook.

## 8. Testing strategy

- **Per-language unit tests:** `Registry.check` collects all violations for a node with
  precise codes, converts only kernel content errors from invariants (a non-kernel
  exception propagates), skips invariants when facet-presence checks fail, and leaves
  `validate` behavior unchanged (existing suites stay green). `Corpus.check`: a clean
  corpus yields no findings; each finding code is exercised (seed invalid files through a
  registry-free corpus, then check with a vocab+shapes registry); dangling-ref reported
  with and without a registry; passed registry overrides `self.registry`; multiple
  findings on one node are all reported; deterministic ordering.
- **Shared conformance fixture:** `fixtures/check-corpus/` — a committed corpus seeded
  with known violations (an unknown kind, a prose kind with a stray facet, a source kind
  with an empty/invalid `source` facet, a dangling relation, one node with several
  violations at once) — plus `fixtures/check.oracle.json` pinning the expected findings
  (severity, code, ref, detail — `message` stays unpinned and human-only). Both
  languages build a corpus over the fixture, run `check` with the knowledge vocab + builtin
  shapes registered, and assert equality with the oracle. Same pattern as the
  search/similarity oracles.
- **Docs gates:** existing golden-format and parity tests stay green; the reference sweep
  must not touch fixture content.

## 9. Alternatives considered

### Patch `docs/format.md` in place

Rejected. Reorganizing it by topic still leaves an unversioned, non-normative document
with no stated authority, and the plan-numbered accretion structure would keep returning.

### Chaptered `docs/spec/` directory

Rejected for now. At the current size the portable contract benefits from being read and
diffed as one unit; chapters can be split out later if the standard grows.

### `docs/spec.md` beside `docs/specs/`

Rejected. "spec.md" vs "specs/" is permanently ambiguous. Renaming `docs/specs/` to
`docs/designs/` matches what those files are (dated design records — commit messages
already call them "designs") and frees the standard to be unambiguous.

### Make `check` raise on first violation

Rejected. A checker exists to survey a corpus that bypassed the write path; failing on the
first finding hides the rest. Fail-early stays the posture of the *write* path; `check` is
a *reporting* surface.

### Validate at parse time instead of adding `check`

Rejected. Wiring the registry into deserialization would make hand-edited corpora
unloadable (construction failure), destroying the ability to inspect and repair. A
constructible corpus + a findings report is the recoverable posture.

## 10. Decisions

1. **One normative, versioned standard at `docs/STANDARD.md`** (starts at 1.0,
   RFC-2119 keywords); `docs/format.md` is deleted after absorption.
2. **Parity is tiered and written down:** tier 1 portable contract, tier 2
   oracle-pinned behavior, tier 3 per-language (no parity obligation).
3. **`docs/specs/` → `docs/designs/`**; dated designs and plans are historical records,
   named as such by the new `README.md` / `AGENTS.md`.
4. **`Corpus.check()` is a reporting API in both kernels** — registry violations as
   errors, dangling refs as warnings, deterministic order over normative fields
   (`ref`, `code`, `detail`), defined normatively in the standard and pinned by
   `fixtures/check-corpus/` + `fixtures/check.oracle.json`.
5. **The registry gains a structured, collecting `Registry.check(node)`** so finding
   codes come from computation, never from parsing error messages; `Registry.validate`
   is unchanged. Only kernel content errors (`FacetError`, `InvariantError`,
   `UnknownKindError`) convert to findings — unexpected invariant exceptions propagate.
6. **No "ignore my registry" parameter** — filter findings by code, or construct a
   registry-free `Corpus` (YAGNI).
7. **Construction semantics are unchanged** — check reports on what constructs; the write
   path keeps failing early.
