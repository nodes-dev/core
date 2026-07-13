# Nodes Python package layout: `nodes` namespace, `nodes.core` module

- **Date:** 2026-07-13
- **Status:** Accepted
- **Follows:** `~/d/nodes/docs/designs/2026-07-11-nodes-package-identity-and-ownership-design.md`
  (which recorded this decision as a pre-release blocker: "The Python package layout
  cannot be treated as stable until the native-namespace versus top-level-domain-import
  decision is made before the first public release") and
  `~/d/nodes/docs/designs/2026-07-12-nodes-base-vocabulary-boundary-design.md` (which
  reduced the shipped Python surface to the kernel alone).

## 1. Context

The `nodes-core` distribution currently ships a regular top-level package `nodes`
whose `__init__.py` contains only `from __future__ import annotations` — no
re-exports. The entire public surface is deep imports through `nodes.kernel.*`
(`~/d/nodes/python/src/nodes/kernel/`, 15 modules). Since the base-vocabulary
retirement, `kernel` is the only subpackage; the path segment no longer contrasts
with anything.

Facts that bear on the decision:

- **Zero Python consumers exist.** Science imports nothing from nodes yet
  (its packages are `science_model`/`science_tool` under their own top-level names);
  mindful is TypeScript-only. Any layout change is free exactly now, and stops being
  free at first publish — that is why the identity design flagged it.
- **The identity design contemplates first-party domain distributions** under the
  nodes brand (the npm scope `@nodes-dev/*` was reserved for the same reason).
- **`docs/STANDARD.md` names no import paths** — the spec is language-neutral, so no
  layout choice has normative impact.
- **The conventional PEP 420 family mapping** is dist `foo-bar` → module `foo.bar`
  (`google-cloud-storage` → `google.cloud.storage`, `opentelemetry-sdk` →
  `opentelemetry.sdk`). Our dist is `nodes-core`; the module is `nodes.kernel`.
- **The package ships no `py.typed`** despite being fully typed — a PEP 561 gap.
- **Irreversibility is one-directional.** Deleting `nodes/__init__.py` (namespace)
  is reversible for as long as only `nodes-core` ships into the namespace: adding the
  file back later breaks nobody. The reverse — publishing with a regular
  `nodes/__init__.py` and later switching to a namespace so `nodes-science` can
  provide `nodes.science` — is a breaking repackaging of an already-published
  artifact.

## 2. Decision

`nodes-core` ships `nodes` as a **PEP 420 native namespace package** containing one
regular subpackage, **`nodes.core`** (renamed from `nodes.kernel`). This is the
stable pre-release layout: dist `nodes-<x>` ↔ module `nodes.<x>`, mirroring
`@nodes-dev/<x>` on npm.

"Kernel" remains the architectural term in prose (README, AGENTS, STANDARD
discussion); it stops being a path segment — as in TypeScript, where
`@nodes-dev/core` has no `kernel` directory and the term appears only in
documentation.

### 2.1 Namespace contract

Recorded for future first-party distributions:

- Each `nodes-<x>` distribution ships exactly one regular package `nodes/<x>/` and
  MUST NOT install a `nodes/__init__.py` — a single stray init converts the
  namespace back to a regular package and breaks every co-installed member.
- The `nodes` namespace is for substrate-family packages only. Downstream
  applications (mindful-style consumers) are not namespace members; they depend on
  `nodes-core` and register their own kinds, under their own package names.
- PyPI cannot reserve `nodes-*` distribution names (the identity design's accepted
  asymmetry with the npm scope; unchanged by this decision; re-evaluate if PEP
  752/755 namespace grants ship).

## 3. Mechanics

- Delete `python/src/nodes/__init__.py` (its only statement,
  `from __future__ import annotations`, is dead in an `__init__.py` with no
  annotations).
- `git mv python/src/nodes/kernel python/src/nodes/core`; rewrite every
  `nodes.kernel` import to `nodes.core` (12 kernel modules import siblings
  absolutely; ~41 test files including `python/tests/_fixtures_profile.py`).
- `nodes/core/__init__.py` stays — `nodes.core` is a regular package inside the
  namespace.
- Add `python/src/nodes/core/py.typed` (empty marker file, PEP 561). Hatchling's
  `packages = ["src/nodes"]` includes it in the wheel; the config and the
  distribution name `nodes-core` are unchanged.

## 4. Normative and documentation impact

- **STANDARD: no change, no version bump.** The spec names no import paths;
  packaging is per-language (Tier 3).
- **README.md**: repo-layout row for `python/` changes from "imports are
  `nodes.kernel`" to "imports are `nodes.core`".
- **AGENTS.md**: the layering bullet is reworded to name the path —
  "`nodes.core` (the kernel) imports nothing above it and names zero knowledge
  kinds." The gates and conventions sections are unaffected.
- Historical designs and plans stay verbatim (dated records keep their vocabulary;
  the retirement-plan precedent).

## 5. Error handling and guards

- **Layout regression guard**: a new `python/tests/test_namespace_layout.py` pins
  the shape — `import nodes.core` succeeds;
  `getattr(nodes, "__file__", None) is None` (the PEP 420 signature — verified
  empirically on the project's Python; `__file__` is `None` for namespace packages
  and the check fails the moment anyone reintroduces `nodes/__init__.py`); and
  `import nodes.kernel` raises `ModuleNotFoundError` with `exc.name ==
  "nodes.kernel"` (name-checked so a broken internal dependency cannot masquerade
  as absence).
- **Stale-bytecode hazard**: the rename leaves ignored
  `src/nodes/kernel/__pycache__/` residue behind `git mv`, and a leftover
  `src/nodes/kernel/` directory would resurrect `nodes.kernel` as a namespace
  package with stale bytecode — the exact failure mode hit after the vocab
  retirement. The implementation plan must remove the residual directory and assert
  it is gone before running import checks.
- Tooling: pytest, ruff, pyright, and hatchling all support PEP 420 with the src
  layout; the gates verify rather than assume.

## 6. Testing strategy

- Both kernels' full suites green after the rename (all six gates; the TS suite
  guards against accidental cross-tree damage even though no TS file changes).
- The layout test of §5 passes.
- Packaging check with teeth: `rtk uv build` from `python/`, then assert the built
  wheel lists `nodes/core/py.typed` and does **not** list `nodes/__init__.py`.
- Conformance fixtures and oracles untouched: `rtk git status --porcelain fixtures/`
  is empty (kind names and finding tuples never mention import paths).

## 7. Alternatives considered

### 7.1 Regular package, domain packages under their own top levels

Keep `nodes/__init__.py`; declare the current layout stable; future domain
distributions use their own top-level names (`science_model`, `nodes_science`).
Rejected: it closes `nodes.<domain>` forever at first publish — reopening it later
is a breaking repackaging — while the namespace costs nothing today and remains
reversible until a second distribution joins it.

### 7.2 Regular package with a barrel API

Keep `nodes/__init__.py` and grow it into a convenience re-export surface
(`from nodes import Corpus, …`), mirroring the TS root barrel. Rejected: it commits
the top level to an API surface that contradicts the established deep-import idiom
(stdlib-style module imports throughout src and tests); the TS barrel is npm idiom,
not a parity obligation.

### 7.3 Rename the distribution instead of the module

Keep `nodes.kernel` and rename the distribution to `nodes-kernel`. Rejected: the
identity design already fixed `nodes-core` for lockstep parity with
`@nodes-dev/core`, and the family convention should follow the distribution, not
the other way around.

## 8. Consequences

- The Python layout is stable for first release: `pip install nodes-core` →
  `import nodes.core`, and every future family member follows the same mapping.
- A top-level `from nodes import …` API is foreclosed while the namespace is
  active. Nothing is lost today (the init was empty), and the door reopens
  (non-breaking) any time before a second distribution ships into the namespace.
- The `nodes.kernel` import path dies pre-release with no deprecation shim
  (fail-early; no consumers exist; consistent with the identity-migration and
  vocab-retirement precedents).

## 9. Implementation boundary

One implementation slice: the init deletion, the `kernel` → `core` move and import
rewrite, `py.typed`, the layout test, the wheel check, and the two living-doc
edits. It does not publish packages, change the TypeScript package, touch
`fixtures/` or `docs/STANDARD.md`, or modify mindful or science.
