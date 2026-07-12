# Nodes base-vocabulary boundary

- **Date:** 2026-07-12
- **Status:** Accepted
- **Scope:** What belongs in the core packages' base vocabulary versus downstream
  domain profiles; the fate of the shipped knowledge vocab; the admission criteria
  for future named kinds, facets, and predicates in core. Follow-up recorded in the
  package identity and ownership design (2026-07-11).

## 1. Context

The substrate design (2026-06-21 §2) promised three layers with strict downward
dependencies — `domain → knowledge vocab → kernel` — and Plan 3 shipped the middle
layer: seven knowledge kinds (`note`, `idea`, `question`, `topic`, `paper`, `book`,
`dataset`), one `Source` facet with an identifiability invariant, and five canonical
predicates (`about`, `cites`, `answers`, `asks`, `refines`), implemented in parallel
in both kernels (`ts/src/vocab/`, `python/src/nodes/vocab/`).

Three facts gathered for this design decide the question:

- **The knowledge vocab has zero consumers.** Mindful v6, the only real downstream,
  imports kernel primitives plus `relatesTo` and defines its own kinds (`thought`,
  `mindmap`, `journal`) with its own facets directly on the kernel. Science — a
  planned adopter of the Python core as substrate — imports nothing from nodes today
  and maintains richer parallels of every bibliographic vocab kind (`article`,
  `book`, `dataset`, with its own source-reference and source-contract machinery).
  Neither consumer composes on the vocab kinds, and neither plans to; science's
  `article` is not vocab's `paper`, and adopting the substrate does not mean trading
  its model down.
- **The vocab is not reachable from the published TypeScript package.**
  `@nodes-dev/core`'s `exports` map exposes only the root barrel, and the barrel
  does not re-export vocab. Only in-repo tests import it via source paths. The de
  facto boundary is already: kernel public, vocab internal.
- **STANDARD never mandates the knowledge kinds, but does state one vocab rule
  normatively.** `vocab`/`vocabulary` appears at four spots: twice in §2.3 —
  including "the vocab `source` facet MUST reject [unknown payload keys]", a
  normative MUST — and twice in §6 (the error table's "vocabulary invariant
  violation" and the write-boundary note's "no vocabulary validation occurs"). The
  conformance suite exercises registry mechanics — `facet-missing`, `facet-invalid`,
  `invariant-violated`, `unknown-kind` — *through* vocab specs, and the shared
  fixtures use vocab kind strings (`note`, `topic`, `paper`), but kind names are
  free strings to the kernel; only the tests need the `KindSpec`s.

The package identity design pinned one constraint: this decision does not pull
science's domain model into core.

## 2. Decision

### 2.1 The boundary

Core's base vocabulary is its **structural vocabulary** — the names the substrate
needs to be a substrate, enumerated exhaustively:

- the six built-in shapes and their convenience kinds (`set`, `list`, `dict`,
  `graph`, `dag`, `tree`; STANDARD §5),
- the four structural facets those shapes compose (`membership`, `order`, `edges`,
  `keys`; STANDARD §5),
- the `relatesTo` predicate — part of the serialization contract (the shorthand
  relation form, STANDARD §4.3), not knowledge vocabulary,
- the facet/invariant machinery and the registry (STANDARD §2.3, §6).

Structural vocabulary is Tier-1 mechanism: it is admitted and changed through
STANDARD's own design and change policy (§12), not by consumer count. Named
knowledge kinds, facets, and knowledge predicates — names that carry
knowledge-representation semantics beyond structure — are domain property,
registered by each downstream profile (as mindful already does and science will).

This supersedes the substrate design's shipped-knowledge-vocab promise: the middle
layer of `domain → knowledge vocab → kernel` becomes "whatever a domain registers,"
not a profile core ships.

### 2.2 Admission criteria (knowledge vocabulary)

These criteria govern **knowledge vocabulary only**; structural vocabulary (§2.1) is
governed by STANDARD §12 instead. A named knowledge kind, facet, or predicate enters
core only by **promotion from proven use**:

- at least two independent consumers using it with matching semantics in real
  corpora, or
- a concrete interchange/federation requirement pinned by its own design.

Core never ships speculative kinds. Promotion harvests a definition from
demonstrated consumer usage; it never designs vocabulary ahead of consumers.

### 2.3 Audit of the shipped vocab

Applying §2.2 to every item the vocab ships:

| Item | Verdict | Evidence |
| --- | --- | --- |
| `note`, `idea`, `question`, `topic` kinds | Retire | Zero consumers; mindful chose `thought` over `note`; science mints its own `question` entities |
| `paper`, `book`, `dataset` kinds | Retire | Zero consumers; science's `article`/`book`/`dataset` are semantically richer parallels |
| `Source` facet + identifiability invariant | Retire from shipped API | Zero consumers; science has its own source machinery. Survives only as conformance test support (§3.2) |
| `about`, `cites`, `answers`, `asks`, `refines` predicates | Retire | Zero consumers; science has its own relation-kind registry (`addresses`, `grounds`, `disputes`, …); mindful uses `relatesTo` only |
| `relatesTo` | Stays (kernel) | Structural vocabulary per §2.1 (serialization contract, STANDARD §4.3) — not subject to §2.2; its one real consumer (mindful tags) is corroboration, not the admission basis |

Retired means deleted from both kernels. Nothing is demoted to an incubating limbo;
git history and the knowledge-vocab design (2026-06-21) are the archive, and §2.2
governs any future return.

## 3. Mechanical consequences

The implementation slice, in both kernels plus docs:

### 3.1 Delete the vocab modules

- `ts/src/vocab/` (`index.ts`, `kinds.ts`, `predicates.ts`, `source.ts`)
- `python/src/nodes/vocab/` (`__init__.py`, `kinds.py`, `predicates.py`, `source.py`)
- Dedicated vocab tests: `ts/tests/vocab-corpus.test.ts`, `vocab-exports.test.ts`,
  `vocab-kinds.test.ts`, `vocab-predicates.test.ts`, `vocab-source.test.ts`;
  `python/tests/test_vocab_exports.py`, `test_vocab_kinds.py`,
  `test_vocab_predicates.py`, `test_vocab_source.py`

### 3.2 Fixtures profile (test support)

The shared conformance fixtures keep their kind strings and oracles **byte-identical**.
Each kernel gains a test-support fixtures profile — not shipped API — registering the
`KindSpec`s the fixtures need: `note`, `topic`, and `paper` with a test-local `source`
facet schema and identifiability invariant reproducing the behavior the check oracle
pins (`facet-unexpected`/`facet-missing`/`facet-invalid` on `source`,
`invariant-violated` on an empty source, `unknown-kind` on `zzz`).

Tests that today register the knowledge vocab rewire to this profile:
`ts/tests/check_parity.test.ts`, `corpus-check.test.ts`, `registry-check.test.ts`;
`python/tests/test_check_parity.py`, `test_corpus_check.py`,
`test_registry_check.py`, `test_corpus_registry.py`.

The registry semantics these tests conformance-check are kernel mechanics; the vocab
was only the vehicle. No oracle regenerates.

### 3.3 STANDARD revision (normative; 1.1 → 1.2)

Retiring the vocab removes a normative rule: §2.3 currently says "the vocab `source`
facet MUST reject [unknown payload keys]." Deleting a MUST is a contract change, not
wording, so STANDARD bumps to **1.2** with a §12 history entry, in the same change as
the code (per §12's same-change rule). It is recorded as a **minor** bump with
explicit rationale: §12 defines minor as additive and major as breaking, and this
removal breaks nothing — corpora containing vocab kind names remain readable and
writable (kind names are free strings, validation is opt-in), and no pinned Tier-2
behavior changes (fixtures and oracles are byte-identical; the same finding tuples
are produced via the fixtures profile).

`vocab`/`vocabulary` appears at exactly four spots; all four are rewritten:

- §2.3 (two occurrences): drop the "vocab `source` facet" example and its MUST; the
  paragraph keeps its remaining normative facet rules (`FacetError` surfacing,
  unknown-key policy is a property of each facet's schema, new facet schemas SHOULD
  reject unknown keys) in generic language, with the built-in shape form facets as
  the remaining concrete example.
- §6 error table: "Shape or vocabulary invariant violation" becomes "Shape or
  registry invariant violation."
- §6 write-boundary note: "no vocabulary validation occurs" becomes "no registry
  validation occurs."

After this revision the only `vocab` match remaining in STANDARD is the 1.2 history
entry itself, which names the retirement (a dated record, exempt like the SP49
self-references).

### 3.4 Living docs

- `README.md`: layer diagram drops the knowledge-vocab row; package descriptions
  drop `nodes.vocab` / "kernel and vocab layers."
- `AGENTS.md`: layering note drops the vocab bullet; the rule "domain kinds live in
  downstream repos" is now the whole story.

Historical designs and plans stay verbatim (the SP49 precedent: dated records keep
their vocabulary).

### 3.5 Downstream

Mindful is untouched — it never imported vocab. Science is untouched — it imports
nothing from nodes yet; when it adopts the substrate it registers its own profile,
exactly as §2.1 prescribes.

## 4. Error handling

No kernel semantics change. Registry validation, facet errors, invariant errors, and
the optional-registry composition default (STANDARD §6) are untouched and remain
conformance-tested through the fixtures profile. Deleting `nodes.vocab` makes
`import nodes.vocab` fail with `ModuleNotFoundError` — fail-early, no deprecation
shim, consistent with the no-compatibility-alias precedent from the identity
migration.

## 5. Testing strategy

- Both kernels' full suites green after the deletion and rewire.
- Conformance fixtures and oracles byte-identical (`rtk git status` clean under
  `fixtures/` at the end of the implementation).
- Shipped-surface checks, run against the Python project environment (from
  `python/`): `rtk uv run --frozen python -c "import nodes"` exits 0 (proving the
  environment resolves the package — a bare failure to find `nodes` would make the
  next check vacuous), and `rtk uv run --frozen python -c "import nodes.vocab"`
  fails with `ModuleNotFoundError: No module named 'nodes.vocab'`. On the TS side,
  `rtk grep -rn "vocab" ts/src python/src` returns nothing.
- Living-docs check: `rtk grep -rln "vocab" README.md AGENTS.md` returns nothing;
  in `docs/STANDARD.md` the only match is the §12 1.2 history entry; remaining repo
  mentions are dated designs/plans plus this design.

## 6. Alternatives considered

### 6.1 Promote the vocab to core's public profile

Expose `@nodes-dev/core/vocab` as a subpath export and keep `nodes.vocab` public;
encourage science to compose on it. Rejected: the audit evidence says science will
not — its parallels are semantically richer, and mindful already demonstrated the
kernel-direct pattern. Promotion without consumers entrenches speculation as public
API on the eve of first release.

### 6.2 Formalized incubation

Keep the vocab in-repo, explicitly non-public and non-normative, deferring
keep-or-prune until science's migration. Rejected: it is the status quo wearing a
label — unconsumed code parked indefinitely, against the explicit-over-defensive
rule. §2.2 already defines the return path if evidence materializes.

### 6.3 Neutralize the fixtures too

Rewrite the conformance fixtures with overtly test-named kinds and regenerate every
oracle in both kernels. Rejected: pure churn. Kind names are free strings; keeping
`note`/`topic`/`paper` as fixture vocabulary costs nothing and avoids touching
oracles that exist to pin cross-kernel parity.

## 7. Consequences

- The published core packages ship mechanism only; every named knowledge kind in
  existence lives in a downstream profile.
- The substrate design's three-layer diagram is superseded as recorded in §2.1;
  the substrate document itself stays verbatim as a dated record.
- STANDARD advances to 1.2, its history recording the retirement (§3.3).
- Future knowledge-vocabulary proposals carry an evidence burden (§2.2) instead of
  a design argument.
- The monorepo package layout follow-up inherits a simpler world: no vocab
  packaging question remains.
- If federation later wants an interchange vocabulary, it is built from observed
  consumer overlap under §2.2, not resurrected wholesale.

## 8. Implementation boundary

The mechanical slice implements §3 exactly: delete the vocab modules and their
dedicated tests, add the per-kernel fixtures profiles, rewire the listed tests,
revise STANDARD to 1.2 (§3.3), and update the living docs. It does not create
packages, alter kernel semantics, regenerate fixtures or oracles, or touch mindful,
science, or historical documents.
