# Nodes Python Package Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `nodes` to a PEP 420 native namespace package with `nodes.core`
(renamed from `nodes.kernel`), ship `py.typed` and PEP 794 import metadata, and point
the living docs at the new path — per the accepted layout design
(`docs/designs/2026-07-13-nodes-python-package-layout-design.md`).

**Architecture:** Three commits on a branch `refactor/python-package-layout`, merged to
main as one change. Commit 1 converts the package layout (init deletion, directory
move, mechanical import rewrite, layout-regression test). Commit 2 adds the packaging
artifacts (PEP 794 metadata, hatchling floor, `py.typed`) with a wheel-content check.
Commit 3 updates the two living-doc mentions. No TypeScript file, fixture, or
STANDARD change anywhere.

**Tech Stack:** Python (pytest, pydantic, ruff, pyright via uv; hatchling build
backend), TypeScript gates run as cross-tree guards only.

## Global Constraints

- Work on branch `refactor/python-package-layout` off `main` in `~/d/nodes`; merge to
  main only after all three tasks and final verification pass.
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
  from an operational failure (exit ≥ 2).
- `fixtures/` is untouchable: at every commit,
  `FIXSTAT="$(rtk git status --porcelain fixtures/)" && test -z "$FIXSTAT" && echo "fixtures clean"`
  must print `fixtures clean`.
- `python/dist/` is NOT gitignored: remove it after every `uv build` and never stage
  it.
- Kernel behavior is untouchable: the only source changes are the dotted-path
  rewrite `nodes.kernel` → `nodes.core` and the directory move. No signature,
  logic, or re-export changes.
- Historical docs (`docs/designs/`, `docs/plans/`) stay verbatim.
- Filepaths written into docs use `~/d/nodes/...` form.
- If `ruff check .` flags import ordering after the rewrite, apply
  `rtk uv run --frozen ruff check . --fix` from `python/`, then re-run the gate.
- The spec (`docs/designs/2026-07-13-nodes-python-package-layout-design.md`) governs
  on any conflict with this plan.

---

### Task 1: Namespace conversion and `nodes.kernel` → `nodes.core` rename

**Files:**
- Delete: `python/src/nodes/__init__.py`
- Rename: `python/src/nodes/kernel/` → `python/src/nodes/core/` (15 modules)
- Modify: every file matching `nodes\.kernel` — 12 files under `python/src/nodes/core/`,
  41 under `python/tests/`, 3 under `python/scripts/` (verified: all 56 files'
  occurrences are import statements only; no strings or monkeypatch targets exist,
  so a global textual replace is safe)
- Create: `python/tests/test_namespace_layout.py`
- Remove (gitignored residue, no commit impact): `python/src/nodes/kernel/` leftovers,
  `python/src/nodes/core/__pycache__/`, `python/scripts/__pycache__/`

**Interfaces:**
- Consumes: the existing kernel API, unchanged.
- Produces: import path `nodes.core.*` (e.g. `from nodes.core.corpus import Corpus`);
  `nodes` importable only as a namespace package. Tasks 2–3 rely on the path and on
  `python/tests/test_namespace_layout.py` existing.

- [ ] **Step 1: Baseline gates on main, then branch**

```bash
cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check
cd ~/d/nodes/python && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
cd ~/d/nodes && rtk git checkout -b refactor/python-package-layout
```

Expected: all gates pass on main before branching. If any fail, STOP and report.

- [ ] **Step 2: Delete the top-level init and move the package directory**

```bash
cd ~/d/nodes && rtk git rm python/src/nodes/__init__.py
rtk git mv python/src/nodes/kernel python/src/nodes/core
```

The deleted `__init__.py` contains only `from __future__ import annotations` (dead
in an init with no annotations); removing it is what makes `nodes` a PEP 420
namespace.

- [ ] **Step 3: Clear bytecode residue from the move**

`git mv` relocates the ignored `__pycache__` along with the directory (or leaves it
behind — both are hazards): stale bytecode under a surviving
`python/src/nodes/kernel/` would resurrect `nodes.kernel` as a namespace package —
the exact failure mode hit after the vocab retirement.

```bash
cd ~/d/nodes && rm -rf python/src/nodes/kernel python/src/nodes/core/__pycache__ python/scripts/__pycache__
test ! -e python/src/nodes/kernel && echo "kernel dir gone"
```

Expected: `kernel dir gone`.

- [ ] **Step 4: Rewrite every `nodes.kernel` import to `nodes.core`**

```bash
cd ~/d/nodes && grep -rl "nodes\.kernel" python/src python/tests python/scripts | xargs sed -i 's/nodes\.kernel/nodes.core/g'
```

This covers the 12 core modules (absolute sibling imports), all 41 test files
(including `python/tests/_fixtures_profile.py` and `_canonical.py`), and the three
oracle generators (`gen_search_oracle.py`, `gen_similarity_oracle.py`,
`gen_tokenizer_oracle.py`) that no gate executes.

- [ ] **Step 5: Zero-match rewrite guard**

```bash
cd ~/d/nodes && rtk grep -rn "nodes\.kernel" python/src python/tests python/scripts; test $? -eq 1 && echo "kernel path retired"
```

Expected: `kernel path retired` on its own (no match lines above it). Match lines,
or a missing message (grep exit 0 = matches survive; exit ≥ 2 = grep itself failed),
is a STOP.

- [ ] **Step 6: Write the layout-regression test**

Create `python/tests/test_namespace_layout.py`:

```python
"""Pins the PEP 420 layout (layout design §5).

`nodes` is a native namespace package shared by family distributions;
`nodes.core` is the regular package this distribution owns. A regular
`nodes/__init__.py` reappearing anywhere breaks co-installed family members.
"""
from __future__ import annotations

import pytest


def test_core_is_importable() -> None:
    import nodes.core

    assert nodes.core.__name__ == "nodes.core"


def test_nodes_is_a_namespace_package() -> None:
    import nodes

    # PEP 420 signature: namespace packages have no __file__ (None or unset).
    assert getattr(nodes, "__file__", None) is None


def test_kernel_import_path_is_gone() -> None:
    with pytest.raises(ModuleNotFoundError) as excinfo:
        import nodes.kernel  # noqa: F401

    # Name-checked so a broken internal dependency cannot masquerade as absence.
    assert excinfo.value.name == "nodes.kernel"
```

- [ ] **Step 7: Run the new test, then the full Python suite**

```bash
cd ~/d/nodes/python && rtk uv run --frozen pytest tests/test_namespace_layout.py -v
cd ~/d/nodes/python && rtk uv run --frozen pytest -q
```

Expected: 3/3 PASS, then full suite PASS (uv rebuilds the project on the changed
layout automatically).

- [ ] **Step 8: Gates (all six — both languages, per Global Constraints)**

```bash
cd ~/d/nodes/python && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check
cd ~/d/nodes && FIXSTAT="$(rtk git status --porcelain fixtures/)" && test -z "$FIXSTAT" && echo "fixtures clean"
```

Expected: all six gates PASS; `fixtures clean`.

- [ ] **Step 9: Commit**

```bash
cd ~/d/nodes && rtk git add python/src python/tests python/scripts && rtk git commit -m "refactor(python): convert nodes to a namespace package with nodes.core"
```

---

### Task 2: PEP 794 metadata, hatchling floor, `py.typed`, wheel check

**Files:**
- Modify: `python/pyproject.toml` (two edits)
- Create: `python/src/nodes/core/py.typed` (empty PEP 561 marker)
- Build artifact (NOT gitignored — remove after checking, never stage):
  `python/dist/`

**Interfaces:**
- Consumes: Task 1's layout (`nodes/core/` exists, no `nodes/__init__.py`).
- Produces: wheel METADATA carrying `Import-Name: nodes.core` /
  `Import-Namespace: nodes`; typed-package marker consumers' type checkers read.

- [ ] **Step 1: Declare import metadata in `python/pyproject.toml`**

```toml
# OLD
[project]
name = "nodes-core"
# NEW
[project]
name = "nodes-core"
import-names = ["nodes.core"]
import-namespaces = ["nodes"]
```

- [ ] **Step 2: Raise the hatchling floor (first version emitting PEP 794 fields)**

```toml
# OLD
requires = ["hatchling>=1.24"]
# NEW
requires = ["hatchling>=1.30"]
```

(Both edits were probed during design review: the project's uv 0.11.28 parses the
keys and builds with the raised floor; `uv run --frozen` is unaffected because
neither edit touches locked dependencies.)

- [ ] **Step 3: Add the PEP 561 marker**

```bash
cd ~/d/nodes && touch python/src/nodes/core/py.typed
```

- [ ] **Step 4: Wheel-content check (design §6 teeth)**

```bash
cd ~/d/nodes/python && rm -rf dist && rtk uv build
cd ~/d/nodes/python && python3 - <<'EOF'
import glob
import zipfile

paths = glob.glob("dist/nodes_core-*.whl")
assert len(paths) == 1, f"expected exactly one wheel, got {paths}"
with zipfile.ZipFile(paths[0]) as whl:
    names = whl.namelist()
    assert "nodes/core/py.typed" in names, "py.typed missing from wheel"
    assert "nodes/__init__.py" not in names, "namespace broken: nodes/__init__.py shipped"
    meta_name = next(n for n in names if n.endswith(".dist-info/METADATA"))
    metadata = whl.read(meta_name).decode()
assert "Import-Name: nodes.core" in metadata, "Import-Name missing from METADATA"
assert "Import-Namespace: nodes" in metadata, "Import-Namespace missing from METADATA"
print("wheel layout ok")
EOF
cd ~/d/nodes/python && rm -rf dist && test ! -e dist && echo "dist not left behind"
```

Expected: `Building…` then `wheel layout ok` then `dist not left behind`. Any
assertion message is a STOP. (`python3` directly is fine here: the check needs only
the stdlib `zipfile` against the built artifact, not the project environment.)

- [ ] **Step 5: Gates (all six — both languages, per Global Constraints)**

```bash
cd ~/d/nodes/python && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check
cd ~/d/nodes && FIXSTAT="$(rtk git status --porcelain fixtures/)" && test -z "$FIXSTAT" && echo "fixtures clean"
```

Expected: all six gates PASS; `fixtures clean`.

- [ ] **Step 6: Commit**

```bash
cd ~/d/nodes && rtk git add python/pyproject.toml python/src/nodes/core/py.typed && rtk git commit -m "chore(python): ship py.typed and declare PEP 794 import metadata"
```

---

### Task 3: Living-doc updates

**Files:**
- Modify: `README.md` (one row), `AGENTS.md` (one bullet)

**Interfaces:**
- Consumes: nothing from Tasks 1–2 besides their commits existing.
- Produces: no living doc mentions `nodes.kernel`.

- [ ] **Step 1: Update the `README.md` repo-layout row**

```markdown
<!-- OLD -->
| `python/` | Python core distribution (`nodes-core`); imports are `nodes.kernel`. |
<!-- NEW -->
| `python/` | Python core distribution (`nodes-core`); imports are `nodes.core`. |
```

(The prose uses of "kernel" as the architectural term — the layer diagram and
surrounding paragraphs — stay; only the import path changes, per design §2.)

- [ ] **Step 2: Update the `AGENTS.md` layering bullet**

```markdown
<!-- OLD -->
- `kernel` imports nothing above it and names zero knowledge kinds.
<!-- NEW -->
- `nodes.core` (the kernel) imports nothing above it and names zero knowledge kinds.
```

The following bullet ("Domain kinds live in downstream repos…") is unchanged.

- [ ] **Step 3: Verify no living doc references the old path**

```bash
cd ~/d/nodes && rtk grep -rn "nodes\.kernel" README.md AGENTS.md ts/README.md docs/STANDARD.md; test $? -eq 1 && echo "living docs clean"
```

Expected: `living docs clean` on its own. A match line or missing message is a STOP.

- [ ] **Step 4: Gates (all six — both languages, per Global Constraints)**

```bash
cd ~/d/nodes/python && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check
cd ~/d/nodes && FIXSTAT="$(rtk git status --porcelain fixtures/)" && test -z "$FIXSTAT" && echo "fixtures clean"
```

Expected: all six gates PASS; `fixtures clean`.

- [ ] **Step 5: Commit**

```bash
cd ~/d/nodes && rtk git add README.md AGENTS.md && rtk git commit -m "docs: point living docs at nodes.core"
```

---

### Final Verification (before merge)

- [ ] **Step 1: Full gates at branch HEAD**

```bash
cd ~/d/nodes/ts && rtk npm test && rtk npm run typecheck && rtk npm run check
cd ~/d/nodes/python && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
```

Expected: all PASS.

- [ ] **Step 2: Design §6 exit criteria**

```bash
cd ~/d/nodes && rtk grep -rn "nodes\.kernel" python/src python/tests python/scripts; test $? -eq 1 && echo "kernel path retired"
cd ~/d/nodes/python && rtk uv run --frozen pytest tests/test_namespace_layout.py -q
cd ~/d/nodes/python && rm -rf dist && rtk uv build && python3 -c "
import glob, zipfile
whl = glob.glob('dist/nodes_core-*.whl')[0]
with zipfile.ZipFile(whl) as z:
    names = z.namelist()
    assert 'nodes/core/py.typed' in names
    assert 'nodes/__init__.py' not in names
    metadata = z.read(next(n for n in names if n.endswith('.dist-info/METADATA'))).decode()
assert 'Import-Name: nodes.core' in metadata and 'Import-Namespace: nodes' in metadata
print('wheel layout ok')
" && rm -rf dist
cd ~/d/nodes && FIXSTAT="$(rtk git status --porcelain fixtures/)" && test -z "$FIXSTAT" && echo "fixtures clean"
cd ~/d/nodes && rtk git log --oneline main..HEAD
```

Expected: `kernel path retired`; layout test passes; `wheel layout ok`;
`fixtures clean`; exactly three commits —
`docs: point living docs at nodes.core`,
`chore(python): ship py.typed and declare PEP 794 import metadata`,
`refactor(python): convert nodes to a namespace package with nodes.core`.
Any missing expected message or extra output is a STOP.

- [ ] **Step 3: Merge**

Use superpowers:finishing-a-development-branch — merge
`refactor/python-package-layout` into `main` locally (repo precedent: the vocab
retirement merged `refactor/vocab-retirement` the same way), verify gates on the
merged result, delete the branch.
