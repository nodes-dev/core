# Nodes Base-Vocabulary Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the knowledge vocab from both kernels per the accepted base-vocabulary
boundary design (`docs/designs/2026-07-12-nodes-base-vocabulary-boundary-design.md`),
replacing it with per-kernel test-support fixtures profiles, and revise STANDARD to 1.2.

**Architecture:** Three commits on a branch `refactor/vocab-retirement`, merged to main
as one change (STANDARD §12 requires the normative revision and the code to land as the
same change; the merge is that change). Commit 1 retires the TypeScript vocab, commit 2
the Python vocab, commit 3 revises STANDARD and the living docs. Conformance fixtures
and oracles are never touched: the fixtures profile in each kernel's test support
re-registers the `KindSpec`s the fixtures need (`note`, `topic`, `paper` + a `source`
facet and identifiability invariant copied verbatim from the vocab), so every oracle
stays byte-identical.

**Tech Stack:** TypeScript (vitest, zod, biome), Python (pytest, pydantic, ruff,
pyright via uv), shared JSON conformance oracles.

## Global Constraints

- Work on branch `refactor/vocab-retirement` off `main` in `~/d/nodes`; merge to main
  only after all three tasks and final verification pass.
- All git commands through `rtk` (`rtk git …`); npm through `rtk npm …`; uv through
  `rtk uv …`.
- Stage explicitly by path. Never `git add -A` or `git add .`.
- Do NOT add any AI-attribution trailer or footer to commit messages ("Co-Authored-By",
  "Generated with Claude Code", etc.).
- ALL SIX gates before EVERY commit (AGENTS.md requires both language sets, even for
  a commit touching one language or only docs) — TypeScript, from `ts/`:
  `rtk npm test`, `rtk npm run typecheck`, `rtk npm run check`. Python, from
  `python/`: `rtk uv run --frozen pytest -q`, `rtk uv run --frozen ruff check .`,
  `rtk uv run --frozen pyright src`.
- Verification is fail-closed: run each line of a multi-line block as its own
  command and STOP on the first non-zero exit or missing expected output. Grep
  emptiness checks use `test $? -eq 1` so that no-match (exit 1) is distinguished
  from an operational failure (exit ≥ 2) — a bare `grep … || echo ok` would report
  success on both.
- `fixtures/` is untouchable: `rtk git status --porcelain fixtures/` must print nothing
  at every commit. Oracles stay byte-identical (design §3.2).
- If `rtk npm run check` flags import ordering after a rewire, apply the fixer:
  `cd ~/d/nodes/ts && rtk npx biome check --write .` — then re-run the gate.
- Kernel source is untouchable: nothing under `ts/src/` changes except deleting
  `ts/src/vocab/`; nothing under `python/src/nodes/` changes except deleting
  `python/src/nodes/vocab/` (design §8: no kernel semantics change).
- Historical docs (`docs/designs/`, `docs/plans/`) stay verbatim.
- Filepaths written into docs use `~/d/nodes/...` form.
- The spec (`docs/designs/2026-07-12-nodes-base-vocabulary-boundary-design.md`) governs
  on any conflict with this plan.

---

### Task 1: TypeScript — fixtures profile, test rewires, vocab deletion

**Files:**
- Create: `ts/tests/fixtures-profile.ts`
- Modify: `ts/tests/registry-check.test.ts`, `ts/tests/corpus-check.test.ts`,
  `ts/tests/check_parity.test.ts`
- Rename+modify: `ts/tests/vocab-corpus.test.ts` → `ts/tests/corpus-registry.test.ts`
- Delete: `ts/src/vocab/` (`index.ts`, `kinds.ts`, `predicates.ts`, `source.ts`),
  `ts/tests/vocab-exports.test.ts`, `ts/tests/vocab-kinds.test.ts`,
  `ts/tests/vocab-predicates.test.ts`, `ts/tests/vocab-source.test.ts`
- Rebuild (gitignored, no commit impact): `ts/dist/` — cleaned and rebuilt in
  Step 10 so the published/`file:`-consumed artifact drops `dist/vocab/*`

**Interfaces:**
- Consumes: kernel API unchanged — `Registry`, `registerBuiltinShapes`, `FacetError`,
  `InvariantError`, `makeNode`, `Corpus` from `../src/*`.
- Produces: `ts/tests/fixtures-profile.ts` exporting
  `SOURCE: string`, `SourceSchema`, `type Source`, `sourceOf(node: Node): Source`,
  `requireIdentifiableSource(node: Node): void`,
  `registerFixturesProfile(reg: Registry): void`. Later tasks don't consume these;
  Task 2 mirrors the same shape in Python.

There is no new failing test to write: the existing conformance suite (check oracle,
registry-check, corpus-check, write-boundary tests) is the net. The cycle is: rewire,
run the suite, delete, run the suite again.

- [ ] **Step 1: Create the branch (baseline must be green first)**

```bash
cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check
cd ~/d/nodes/python && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
cd ~/d/nodes && rtk git checkout -b refactor/vocab-retirement
```

Expected: all gates pass on main before branching. If any fail, STOP and report.

- [ ] **Step 2: Create `ts/tests/fixtures-profile.ts`**

Test support only — never imported from `ts/src/`. The `source` facet schema and
invariant are copied verbatim from the vocab so the check oracle's finding tuples
(`facet-missing`/`facet-invalid`/`facet-unexpected` on `source`, `invariant-violated`
on an empty source) reproduce exactly:

```typescript
import { z } from "zod";
import { FacetError, InvariantError } from "../src/errors.js";
import type { Node } from "../src/node.js";
import type { Registry } from "../src/registry.js";

/** Test-support profile for the shared conformance fixtures (design §3.2).
 *  Registers the kinds the fixture corpora use; not shipped API. */

export const SOURCE = "source";

const SourceYearSchema = z.preprocess((value) => {
  if (typeof value === "string" && value.trim() !== "") return Number(value);
  return value;
}, z.number().int().nullable().default(null));

/** `.strict()` mirrors Pydantic's `extra="forbid"`: unknown keys (typos) fail,
 *  never silently dropped. */
export const SourceSchema = z
  .object({
    authors: z.array(z.string()).default([]),
    year: SourceYearSchema,
    container: z.string().nullable().default(null),
    identifier: z.string().nullable().default(null),
    url: z.string().nullable().default(null),
  })
  .strict();

export type Source = z.infer<typeof SourceSchema>;

export function sourceOf(node: Node): Source {
  const raw = node.facets[SOURCE];
  if (raw === undefined) {
    throw new FacetError(`${node.id}: missing '${SOURCE}' facet`);
  }
  try {
    return SourceSchema.parse(raw);
  } catch (e) {
    if (e instanceof z.ZodError) {
      throw new FacetError(`${node.id}: invalid '${SOURCE}' facet: ${e.issues.map((i) => i.message).join("; ")}`);
    }
    throw e;
  }
}

export function requireIdentifiableSource(node: Node): void {
  const s = sourceOf(node);
  // Truthiness on purpose: an empty author list / year 0 / "" identifier counts as absent.
  if (!(s.authors.length || s.year || s.identifier || s.url)) {
    throw new InvariantError(`${node.id}: source facet needs at least one of authors/year/identifier/url`);
  }
}

export const NOTE = "note";
export const TOPIC = "topic";
export const PAPER = "paper";

/** Register the kinds the shared fixtures need. `zzz` stays unregistered on
 *  purpose — the check oracle pins `unknown-kind` for it. */
export function registerFixturesProfile(reg: Registry): void {
  reg.register({ name: NOTE });
  reg.register({ name: TOPIC });
  reg.register({
    name: PAPER,
    requiredFacets: new Set([SOURCE]),
    invariants: [requireIdentifiableSource],
  });
}
```

- [ ] **Step 3: Rewire `ts/tests/registry-check.test.ts`**

Replace the vocab import and helper (top of file):

```typescript
// OLD
import { SOURCE, registerKnowledgeVocab } from "../src/vocab/index.js";

function vocabRegistry(): Registry {
  const reg = new Registry();
  registerKnowledgeVocab(reg);
  return reg;
}

// NEW
import { SOURCE, registerFixturesProfile } from "./fixtures-profile.js";

function fixturesRegistry(): Registry {
  const reg = new Registry();
  registerFixturesProfile(reg);
  return reg;
}
```

Then replace every call site: `vocabRegistry()` → `fixturesRegistry()` (6 call sites
in this file). All node kinds used (`note`, `paper`, `widget` ad hoc) are covered.

- [ ] **Step 4: Rewire `ts/tests/corpus-check.test.ts`**

```typescript
// OLD
import { SOURCE, registerKnowledgeVocab } from "../src/vocab/index.js";

function vocabRegistry(): Registry {
  const reg = new Registry();
  registerBuiltinShapes(reg);
  registerKnowledgeVocab(reg);
  return reg;
}

// NEW
import { SOURCE, registerFixturesProfile } from "./fixtures-profile.js";

function fixturesRegistry(): Registry {
  const reg = new Registry();
  registerBuiltinShapes(reg);
  registerFixturesProfile(reg);
  return reg;
}
```

Replace every `vocabRegistry()` call site (5 occurrences). Kinds used: `topic`,
`note`, `paper`, `zzz` (unregistered), `set` (builtin shape) — all covered.

- [ ] **Step 5: Rewire `ts/tests/check_parity.test.ts`**

```typescript
// OLD
import { registerKnowledgeVocab } from "../src/vocab/index.js";
// NEW
import { registerFixturesProfile } from "./fixtures-profile.js";
```

and in the first test body:

```typescript
// OLD
registerKnowledgeVocab(reg);
// NEW
registerFixturesProfile(reg);
```

- [ ] **Step 6: Rename and rewire the write-boundary test**

```bash
cd ~/d/nodes && rtk git mv ts/tests/vocab-corpus.test.ts ts/tests/corpus-registry.test.ts
```

Then in `ts/tests/corpus-registry.test.ts`:

```typescript
// OLD
import { SOURCE, registerKnowledgeVocab } from "../src/vocab/index.js";

function knowledgeRegistry(): Registry {
  const reg = new Registry();
  registerKnowledgeVocab(reg);
  return reg;
}

// NEW
import { SOURCE, registerFixturesProfile } from "./fixtures-profile.js";

function fixturesRegistry(): Registry {
  const reg = new Registry();
  registerFixturesProfile(reg);
  return reg;
}
```

Replace both `knowledgeRegistry()` call sites with `fixturesRegistry()`, and update the
two strings:

```typescript
// OLD
  root = mkdtempSync(join(tmpdir(), "nodes-vocab-corpus-"));
// NEW
  root = mkdtempSync(join(tmpdir(), "nodes-corpus-registry-"));

// OLD
describe("Corpus with the knowledge vocab registry", () => {
// NEW
describe("Corpus write-boundary enforcement with a registry", () => {
```

The file's relation predicates (`about`, `cites`) are free strings to the kernel —
they need no registration and stay as-is.

- [ ] **Step 7: Run the suite with the vocab still present**

```bash
cd ~/d/nodes/ts && rtk npm test
```

Expected: PASS. The rewired tests now exercise the fixtures profile; nothing imports
vocab except the four dedicated vocab test files.

- [ ] **Step 8: Delete the vocab and its dedicated tests**

```bash
cd ~/d/nodes && rtk git rm -r ts/src/vocab
rtk git rm ts/tests/vocab-exports.test.ts ts/tests/vocab-kinds.test.ts ts/tests/vocab-predicates.test.ts ts/tests/vocab-source.test.ts
```

- [ ] **Step 9: Verify no vocab reference survives in TS**

```bash
cd ~/d/nodes && rtk grep -rn "vocab" ts/src ts/tests; test $? -eq 1 && echo "ts vocab retired"
```

Expected: `ts vocab retired` on its own (no match lines above it). Any match lines,
or no `ts vocab retired` (grep exit 0 = matches survive; exit ≥ 2 = grep itself
failed), is a STOP.

- [ ] **Step 10: Clean-rebuild `ts/dist` and verify the packed surface**

`ts/dist` is gitignored but it is the published artifact (`package.json`
`"files": ["dist"]`) and mindful's `file:../../nodes/ts` dependency consumes it.
`tsc` does not remove outputs for deleted sources, so the stale `dist/vocab/*`
artifacts must be cleaned explicitly:

```bash
cd ~/d/nodes/ts && rm -rf dist && rtk npm run build
cd ~/d/nodes/ts && if rtk npm pack --dry-run 2>&1 | grep -q "dist/vocab"; then echo "FAIL: dist/vocab still packed"; false; else echo "pack clean"; fi
```

Expected: build succeeds; `pack clean`. `FAIL: dist/vocab still packed` is a STOP.

- [ ] **Step 11: Gates (all six — both languages, per Global Constraints)**

```bash
cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check
cd ~/d/nodes/python && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
cd ~/d/nodes && test -z "$(rtk git status --porcelain fixtures/)" && echo "fixtures clean"
```

Expected: all six gates PASS (check-oracle parity test included); `fixtures clean`.

- [ ] **Step 12: Commit**

```bash
cd ~/d/nodes && rtk git add ts/src ts/tests && rtk git commit -m "refactor(ts): retire knowledge vocab behind fixtures profile"
```

---

### Task 2: Python — fixtures profile, test rewires, vocab deletion

**Files:**
- Create: `python/tests/_fixtures_profile.py` (underscore prefix matches the existing
  `python/tests/_canonical.py` helper convention)
- Modify: `python/tests/test_registry_check.py`, `python/tests/test_corpus_check.py`,
  `python/tests/test_check_parity.py`, `python/tests/test_corpus_registry.py`
- Delete: `python/src/nodes/vocab/` (`__init__.py`, `kinds.py`, `predicates.py`,
  `source.py`), `python/tests/test_vocab_exports.py`, `python/tests/test_vocab_kinds.py`,
  `python/tests/test_vocab_predicates.py`, `python/tests/test_vocab_source.py`

**Interfaces:**
- Consumes: kernel API unchanged — `KindSpec`, `Registry` from
  `nodes.kernel.registry`; `FacetError`, `InvariantError` from `nodes.kernel.errors`;
  `Node` from `nodes.kernel.node`.
- Produces: `python/tests/_fixtures_profile.py` exporting `SOURCE: str`,
  `Source` (pydantic model), `source_of(node: Node) -> Source`,
  `require_identifiable_source(node: Node) -> None`,
  `register_fixtures_profile(reg: Registry) -> None` — the Python mirror of Task 1's
  `ts/tests/fixtures-profile.ts`.

- [ ] **Step 1: Create `python/tests/_fixtures_profile.py`**

Copied verbatim from the vocab's `source.py`/`kinds.py`, trimmed to what the fixtures
need:

```python
"""Test-support profile for the shared conformance fixtures (design §3.2).

Registers the kinds the fixture corpora use; not shipped API. `zzz` stays
unregistered on purpose — the check oracle pins `unknown-kind` for it.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from nodes.kernel.errors import FacetError, InvariantError
from nodes.kernel.node import Node
from nodes.kernel.registry import KindSpec, Registry

SOURCE = "source"
NOTE = "note"
TOPIC = "topic"
PAPER = "paper"


class Source(BaseModel):
    """Bibliographic facet the fixture `paper` nodes carry."""

    model_config = ConfigDict(extra="forbid")  # unknown keys (typos) fail, never silently dropped

    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    container: str | None = None
    identifier: str | None = None
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


def register_fixtures_profile(reg: Registry) -> None:
    reg.register(KindSpec(name=NOTE))
    reg.register(KindSpec(name=TOPIC))
    reg.register(
        KindSpec(
            name=PAPER,
            required_facets={SOURCE},
            invariants=[require_identifiable_source],
        )
    )
```

- [ ] **Step 2: Rewire `python/tests/test_registry_check.py`**

```python
# OLD
from nodes.vocab.kinds import register_knowledge_vocab
from nodes.vocab.source import SOURCE


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    register_knowledge_vocab(r)
    return r

# NEW
from tests._fixtures_profile import SOURCE, register_fixtures_profile


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    register_fixtures_profile(r)
    return r
```

No other changes: the tests use kinds `note`, `paper`, `zzz` (unregistered), and ad hoc
`widget` specs — all covered.

- [ ] **Step 3: Rewire `python/tests/test_corpus_check.py`**

```python
# OLD
from nodes.vocab.kinds import register_knowledge_vocab
from nodes.vocab.source import SOURCE


def _registry() -> Registry:
    r = Registry()
    register_builtin_shapes(r)
    register_knowledge_vocab(r)
    return r

# NEW
from tests._fixtures_profile import SOURCE, register_fixtures_profile


def _registry() -> Registry:
    r = Registry()
    register_builtin_shapes(r)
    register_fixtures_profile(r)
    return r
```

- [ ] **Step 4: Rewire `python/tests/test_check_parity.py`**

```python
# OLD
from nodes.vocab.kinds import register_knowledge_vocab
# NEW
from tests._fixtures_profile import register_fixtures_profile
```

and in `test_check_findings_match_committed_oracle`:

```python
# OLD
    register_knowledge_vocab(reg)
# NEW
    register_fixtures_profile(reg)
```

- [ ] **Step 5: Rewire `python/tests/test_corpus_registry.py`**

```python
# OLD
from nodes.vocab.kinds import register_knowledge_vocab
from nodes.vocab.source import SOURCE


def _registry() -> Registry:
    r = Registry()
    register_knowledge_vocab(r)
    return r

# NEW
from tests._fixtures_profile import SOURCE, register_fixtures_profile


def _registry() -> Registry:
    r = Registry()
    register_fixtures_profile(r)
    return r
```

- [ ] **Step 6: Run the suite with the vocab still present**

```bash
cd ~/d/nodes/python && rtk uv run --frozen pytest -q
```

Expected: PASS. Only the four `test_vocab_*.py` files still import `nodes.vocab`.

- [ ] **Step 7: Delete the vocab and its dedicated tests**

```bash
cd ~/d/nodes && rtk git rm -r python/src/nodes/vocab
rtk git rm python/tests/test_vocab_exports.py python/tests/test_vocab_kinds.py python/tests/test_vocab_predicates.py python/tests/test_vocab_source.py
```

- [ ] **Step 8: Verify no vocab reference survives in Python, and the shipped surface**

```bash
cd ~/d/nodes && rtk grep -rn "vocab" python/src python/tests; test $? -eq 1 && echo "python vocab retired"
cd ~/d/nodes/python && rtk uv run --frozen python -c "import nodes; print('nodes ok')"
cd ~/d/nodes/python && rtk uv run --frozen python -c "
try:
    import nodes.vocab
except ModuleNotFoundError:
    print('nodes.vocab absent')
else:
    raise SystemExit('FAIL: nodes.vocab importable')
"
```

Expected: `python vocab retired` (no match lines; missing message or match lines is
a STOP); then `nodes ok` (the environment resolves the package — this is what makes
the next check non-vacuous); then `nodes.vocab absent` with exit 0. The check itself
fails (non-zero exit, `FAIL: nodes.vocab importable`) if the module still imports
(design §5).

- [ ] **Step 9: Gates (all six — both languages, per Global Constraints)**

```bash
cd ~/d/nodes/python && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check
cd ~/d/nodes && test -z "$(rtk git status --porcelain fixtures/)" && echo "fixtures clean"
```

Expected: all six gates PASS (check-oracle parity test included); `fixtures clean`.

- [ ] **Step 10: Commit**

```bash
cd ~/d/nodes && rtk git add python/src python/tests && rtk git commit -m "refactor(python): retire knowledge vocab behind fixtures profile"
```

---

### Task 3: STANDARD 1.2 and living-doc scrub

**Files:**
- Modify: `docs/STANDARD.md` (header version; §2.3; §6 error table; §6 write-boundary
  note; §12 policy + history), `README.md`, `AGENTS.md`, `ts/README.md`

**Interfaces:**
- Consumes: nothing from Tasks 1–2 besides their commits existing (the §12 same-change
  rule is satisfied by all three commits merging together).
- Produces: STANDARD spec version `1.2`; no `vocab` mention in living docs except
  STANDARD's §12 history entry.

- [ ] **Step 1: Bump the STANDARD header**

In `docs/STANDARD.md` line 3:

```markdown
<!-- OLD -->
- **Spec version:** 1.1
<!-- NEW -->
- **Spec version:** 1.2
```

- [ ] **Step 2: Rewrite §2.3 (drop the vocab source-facet example and its MUST)**

```markdown
<!-- OLD -->
mappings. Which facets a node may or must carry is decided by its kind's registry spec
(§6); facet payload schemas are enforced by invariants (e.g. the shape form facets §5,
the vocab `source` facet). Typed facet accessors MUST surface a missing or malformed
payload as `FacetError` — a raw Pydantic/Zod error never escapes a public API. Whether
unknown payload keys are rejected is a property of each facet's schema: the vocab
`source` facet MUST reject them (fail-early on typos); the built-in shape form facets
(§5) currently tolerate them. New facet schemas SHOULD reject unknown keys.

<!-- NEW -->
mappings. Which facets a node may or must carry is decided by its kind's registry spec
(§6); facet payload schemas are enforced by invariants (e.g. the shape form facets §5).
Typed facet accessors MUST surface a missing or malformed payload as `FacetError` — a
raw Pydantic/Zod error never escapes a public API. Whether unknown payload keys are
rejected is a property of each facet's schema: the built-in shape form facets (§5)
currently tolerate them. New facet schemas SHOULD reject unknown keys.
```

- [ ] **Step 3: Rewrite the two §6 mentions**

Error table row:

```markdown
<!-- OLD -->
| Shape or vocabulary invariant violation | `InvariantError` |
<!-- NEW -->
| Shape or registry invariant violation | `InvariantError` |
```

Write-boundary note:

```markdown
<!-- OLD -->
  no vocabulary validation occurs (a deliberate composition default, not a fallback).
<!-- NEW -->
  no registry validation occurs (a deliberate composition default, not a fallback).
```

- [ ] **Step 4: Amend §12 (minor covers backward-compatible removals) and add history**

```markdown
<!-- OLD -->
- This standard carries a spec version (header). **Minor** bumps are additive (new
  optional fields, new finding codes, new fixtures). **Major** bumps break reading or
  writing existing corpora, or change pinned tier-2 behavior.

<!-- NEW -->
- This standard carries a spec version (header). **Minor** bumps are
  backward-compatible: additive changes (new optional fields, new finding codes, new
  fixtures), or removals and relaxations that break neither reading/writing existing
  corpora nor pinned tier-2 behavior. **Major** bumps break reading or writing
  existing corpora, or change pinned tier-2 behavior.
```

History line (append to the `History:` entry so it reads):

```markdown
<!-- OLD -->
- History: **1.0** (2026-07-10) — initial consolidation; adds §8 corpus validity.
  **1.1** (2026-07-11) — membership traversal (§7); `dangling-member` finding (§8.2).

<!-- NEW -->
- History: **1.0** (2026-07-10) — initial consolidation; adds §8 corpus validity.
  **1.1** (2026-07-11) — membership traversal (§7); `dangling-member` finding (§8.2).
  **1.2** (2026-07-12) — knowledge vocab retired from the shipped surface
  (base-vocabulary boundary design); §2.3 source-facet rule removed; minor bumps
  redefined to cover backward-compatible removals.
```

- [ ] **Step 5: Update `README.md`**

Layer diagram and paragraph (the "## Architecture" section):

````markdown
<!-- OLD -->
Three layers, strict downward dependency:

```
domain profiles   science (Python), mindful v6 (TypeScript), …
knowledge vocab   note / idea / question / topic / paper / book / dataset
kernel            Node, Relation, shapes, identity, format, Corpus, indexes
```

The kernel is domain-free (zero named knowledge kinds); the vocab imports only the
kernel; domain profiles live in downstream repos.

<!-- NEW -->
Two layers, strict downward dependency:

```
domain profiles   science (Python), mindful v6 (TypeScript), …
kernel            Node, Relation, shapes, identity, format, Corpus, indexes
```

The kernel is domain-free (zero named knowledge kinds); domain profiles register
their own kinds onto the kernel's registry and live in downstream repos.
````

Repo layout table rows:

```markdown
<!-- OLD -->
| `python/` | Python core distribution (`nodes-core`); imports are `nodes.kernel` and `nodes.vocab`. |
| `ts/` | TypeScript core package (`@nodes-dev/core`), containing kernel and vocab layers. |
<!-- NEW -->
| `python/` | Python core distribution (`nodes-core`); imports are `nodes.kernel`. |
| `ts/` | TypeScript core package (`@nodes-dev/core`), the domain-free kernel. |
```

- [ ] **Step 6: Update `AGENTS.md`**

The "## Layering" section:

```markdown
<!-- OLD -->
- `kernel` imports nothing above it and names zero knowledge kinds.
- `vocab` imports only the kernel. Domain kinds live in downstream repos.
<!-- NEW -->
- `kernel` imports nothing above it and names zero knowledge kinds.
- Domain kinds live in downstream repos, registered onto the kernel's `Registry`.
```

- [ ] **Step 7: Update `ts/README.md`**

Intro paragraph:

```markdown
<!-- OLD -->
TypeScript implementation of Nodes core — behavioral and on-disk-format parity with
the Python distribution. Core contains the domain-free kernel and the general-purpose
knowledge vocabulary.
<!-- NEW -->
TypeScript implementation of Nodes core — behavioral and on-disk-format parity with
the Python distribution. Core contains the domain-free kernel.
```

Delete the vocab paragraph entirely:

```markdown
<!-- DELETE -->
The knowledge vocab (`ts/src/vocab/` — `note`/`idea`/`question`/`topic`/`paper`/`book`/
`dataset`, the `Source` facet, and the predicate vocabulary) is a separate layer that
imports only from the kernel; register it with `registerKnowledgeVocab(reg)`.
```

Correct the stale traversal claim in the Scope paragraph — traversal shipped in
STANDARD 1.1 (`ts/src/corpus.ts`: `members`/`containers`/`descendants`/`ancestors`),
so the "no membership-graph traversal" sentence is false; list traversal among the
queries and drop the sentence:

```markdown
<!-- OLD -->
(`outbound`/`inbound`/`neighbors`/`dangling`), BM25F full-text `search`, opt-in
embedding `similar`/`queryVector`/`similarText`, snapshot persistence (`flushIndex`),
and corpus checking (`check`). TS-only conveniences (tier 3): `idsByKind`/`allByKind`
and corpus stat fingerprints. There is **no membership-graph traversal** yet.
<!-- NEW -->
(`outbound`/`inbound`/`neighbors`/`dangling`), membership traversal
(`members`/`containers`/`descendants`/`ancestors`), BM25F full-text `search`, opt-in
embedding `similar`/`queryVector`/`similarText`, snapshot persistence (`flushIndex`),
and corpus checking (`check`). TS-only conveniences (tier 3): `idsByKind`/`allByKind`
and corpus stat fingerprints.
```

Fix the stale spec-version citation:

```markdown
<!-- OLD -->
The portable contract this kernel implements is specified in `../docs/STANDARD.md`
(spec version 1.0); parity with Python is pinned by the shared `../fixtures/` oracles.
<!-- NEW -->
The portable contract this kernel implements is specified in `../docs/STANDARD.md`
(spec version 1.2); parity with Python is pinned by the shared `../fixtures/` oracles.
```

- [ ] **Step 8: Verify the living-doc exit criteria**

```bash
cd ~/d/nodes && rtk grep -rln "vocab" README.md AGENTS.md ts/README.md; test $? -eq 1 && echo "living docs clean"
cd ~/d/nodes && rtk grep -n "vocab" docs/STANDARD.md
```

Expected: `living docs clean` (no filenames above it; a listed filename or a missing
message is a STOP); the STANDARD grep matches ONLY the lines of the §12 1.2 history
entry (design §5 exempts it as a dated record) — any other match is a STOP.

- [ ] **Step 9: Gates (all six — both languages, per Global Constraints)**

```bash
cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check
cd ~/d/nodes/python && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
cd ~/d/nodes && test -z "$(rtk git status --porcelain fixtures/)" && echo "fixtures clean"
```

Expected: all six gates PASS; `fixtures clean`.

- [ ] **Step 10: Commit**

```bash
cd ~/d/nodes && rtk git add docs/STANDARD.md README.md AGENTS.md ts/README.md && rtk git commit -m "docs: revise STANDARD to 1.2 and scrub vocab from living docs"
```

---

### Final Verification (before merge)

- [ ] **Step 1: Full gates at branch HEAD**

```bash
cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check
cd ~/d/nodes/python && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
```

Expected: all PASS.

- [ ] **Step 2: Design §5 exit criteria**

```bash
cd ~/d/nodes && rtk grep -rn "vocab" ts/src python/src; test $? -eq 1 && echo "shipped surface clean"
cd ~/d/nodes/python && rtk uv run --frozen python -c "import nodes; print('nodes ok')"
cd ~/d/nodes/python && rtk uv run --frozen python -c "
try:
    import nodes.vocab
except ModuleNotFoundError:
    print('nodes.vocab absent')
else:
    raise SystemExit('FAIL: nodes.vocab importable')
"
cd ~/d/nodes/ts && if rtk npm pack --dry-run 2>&1 | grep -q "dist/vocab"; then echo "FAIL: dist/vocab still packed"; false; else echo "pack clean"; fi
cd ~/d/nodes && test -z "$(rtk git status --porcelain fixtures/)" && echo "fixtures clean"
cd ~/d/nodes && rtk git log --oneline main..HEAD
```

Expected: `shipped surface clean` (no match lines); `nodes ok`; `nodes.vocab absent`
(exit 0 — `FAIL: nodes.vocab importable` means the module still ships);
`pack clean`; `fixtures clean`; exactly three commits —
`docs: revise STANDARD to 1.2 and scrub vocab from living docs`,
`refactor(python): retire knowledge vocab behind fixtures profile`,
`refactor(ts): retire knowledge vocab behind fixtures profile`. Any missing
expected message or extra output is a STOP.

- [ ] **Step 3: Merge (the §12 "same change")**

Use superpowers:finishing-a-development-branch — merge `refactor/vocab-retirement`
into `main` locally (repo precedent: the identity migration merged
`docs/package-identity` the same way), verify gates on the merged result, delete the
branch.
