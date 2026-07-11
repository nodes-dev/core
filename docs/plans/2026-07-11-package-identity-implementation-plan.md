# Nodes Package Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repository's provisional Python and TypeScript distribution identities with the accepted public core-package names and align living documentation.

**Architecture:** Keep the runtime module boundaries unchanged: Python continues to import as `nodes.*`, and TypeScript continues to expose the same root barrel and internal `kernel`/`vocab` layers. Change only distribution metadata, its generated npm lockfile entry, and living package-orientation text; registry creation, publishing, repository transfer, domain packages, and downstream repositories remain separate work.

**Tech Stack:** Python 3.11+, Hatchling/PEP 621, TypeScript, npm package metadata/lockfile v3, Markdown.

## Global Constraints

- Public core identities are PyPI `nodes-core` and npm `@nodes-dev/core`.
- Python imports remain `nodes.*`; do not rename `python/src/nodes/`.
- The TypeScript source barrel and architectural `kernel` layer remain unchanged.
- Do not add legacy aliases, compatibility packages, or forwarding modules.
- Do not publish packages, create registry organizations, transfer the Git repository, create domain packages, or extract vocabulary in this slice.
- Do not edit dated historical designs or plans to rewrite their historical context.
- Before every commit, run all Python and TypeScript gates from `AGENTS.md`.
- Commit messages must not contain AI-attribution or `Co-Authored-By` trailers.

---

### Task 1: Rename the Python distribution

**Files:**
- Modify: `python/pyproject.toml`
- Refresh locally (gitignored, do not commit): `python/uv.lock`

**Interfaces:**
- Consumes: the existing Hatchling package mapping `packages = ["src/nodes"]`.
- Produces: distribution metadata named `nodes-core` and described as Nodes core while preserving the import package `nodes`.

- [ ] **Step 1: Assert the current metadata has the obsolete distribution name**

Run from the repository root:

```bash
rg -n '^name = "nodes"$' python/pyproject.toml
```

Expected: one match at `python/pyproject.toml:2`; this is the metadata that must change.

- [ ] **Step 2: Change the PEP 621 distribution identity**

Edit the opening project metadata to read:

```toml
[project]
name = "nodes-core"
version = "0.1.0"
description = "Nodes core: a problem-agnostic knowledge substrate"
```

Leave this Hatchling mapping unchanged so imports remain `nodes.*`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/nodes"]
```

- [ ] **Step 3: Refresh the ignored local lockfile**

Run from `python/`:

```bash
uv lock
```

Expected: uv updates the root workspace member from `nodes` to `nodes-core` (typically reported as `Removed nodes v0.1.0` and `Added nodes-core v0.1.0`). `python/uv.lock` is ignored by the repository, so this refresh supports local frozen commands but is not part of the commit.

- [ ] **Step 4: Verify the new distribution/import boundary**

Run from the repository root:

```bash
rg -n '^name = "nodes-core"$|^description = "Nodes core: a problem-agnostic knowledge substrate"$|packages = \["src/nodes"\]' python/pyproject.toml
rg -n '^name = "nodes-core"$' python/uv.lock
```

Expected: the project metadata contains the new name and description plus `packages = ["src/nodes"]`, and the refreshed lockfile contains the `nodes-core` root workspace member.

Run from `python/`:

```bash
uv run --frozen python -c 'import nodes; print(nodes.__name__)'
```

Expected output:

```text
nodes
```

- [ ] **Step 5: Run every repository gate**

Run from `python/`:

```bash
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen pyright src
```

Expected: the test suite passes, Ruff reports `All checks passed!`, and Pyright reports zero errors.

Run from `ts/`:

```bash
npm test
npm run typecheck
npm run check
```

Expected: Vitest passes, TypeScript exits successfully with no diagnostics, and Biome reports no errors.

- [ ] **Step 6: Commit the Python distribution rename**

```bash
git add python/pyproject.toml
git commit -m "chore(python): rename distribution to nodes-core"
```

Expected: one commit containing only `python/pyproject.toml`.

---

### Task 2: Rename the TypeScript package

**Files:**
- Modify: `ts/package.json`
- Modify: `ts/package-lock.json`

**Interfaces:**
- Consumes: the existing npm package at version `0.1.0` and lockfile version 3.
- Produces: npm metadata named and described as `@nodes-dev/core`, with identical version, exports, files, scripts, dependencies, and runtime API.

- [ ] **Step 1: Assert both npm metadata files have the obsolete name**

Run from the repository root:

```bash
rg -n '"name": "@nodes/kernel"' ts/package.json ts/package-lock.json
```

Expected: three matches—one in `package.json`, plus the lockfile's root and root-package entries.

- [ ] **Step 2: Update the npm manifest identity**

Change the top-level name and description in `ts/package.json`:

```json
{
  "name": "@nodes-dev/core",
  "version": "0.1.0",
  "description": "Nodes core: a problem-agnostic knowledge substrate (TypeScript)",
```

- [ ] **Step 3: Regenerate the lockfile metadata**

Run from `ts/`:

```bash
npm install --package-lock-only --ignore-scripts
```

Expected: npm exits successfully and updates both `name` entries associated with the root package without changing dependency versions.

- [ ] **Step 4: Verify the manifest and lockfile are synchronized**

Run from `ts/`:

```bash
npm pkg get name description
rg -n '"name": "@nodes-dev/core"' package.json package-lock.json
git diff -- package.json package-lock.json
```

Expected: `npm pkg get name description` prints the accepted name and `Nodes core: a problem-agnostic knowledge substrate (TypeScript)`; `rg` reports three matches; the diff changes the three package-name values and the manifest description, without changing versions, exports, scripts, or dependencies.

- [ ] **Step 5: Run every repository gate**

Run from `python/`:

```bash
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen pyright src
```

Expected: the test suite passes, Ruff reports `All checks passed!`, and Pyright reports zero errors.

Run from `ts/`:

```bash
npm test
npm run typecheck
npm run check
```

Expected: Vitest passes, TypeScript exits successfully with no diagnostics, and Biome reports no errors.

- [ ] **Step 6: Commit the TypeScript package rename**

```bash
git add ts/package.json ts/package-lock.json
git commit -m "chore(ts): rename package to @nodes-dev/core"
```

Expected: one commit containing only the npm manifest and lockfile.

---

### Task 3: Align living repository documentation

**Files:**
- Modify: `README.md`
- Modify: `ts/README.md`

**Interfaces:**
- Consumes: the accepted distinction between the Nodes family, the public core distributions, and the internal kernel layer.
- Produces: current orientation docs that identify `nodes-core` and `@nodes-dev/core` without changing architectural terminology where `kernel` is correct.

- [ ] **Step 1: Confirm the remaining obsolete public-name references are confined to living docs**

Run from the repository root:

```bash
rg -n '@nodes/kernel|Python kernel \+ vocab|TypeScript kernel \+ vocab' README.md ts/README.md
```

Expected: the TypeScript README heading and root repo-layout rows are the only matches.

- [ ] **Step 2: Update the root repository orientation**

Replace the two package rows in `README.md` with:

```markdown
| `python/` | Python core distribution (`nodes-core`); imports are `nodes.kernel` and `nodes.vocab`. |
| `ts/` | TypeScript core package (`@nodes-dev/core`), containing kernel and vocab layers. |
```

Keep the architecture diagram and its use of `kernel` unchanged because it names the lowest internal layer, not the distribution.

- [ ] **Step 3: Update the TypeScript package heading and description**

Replace the opening of `ts/README.md` with:

```markdown
# @nodes-dev/core (TypeScript)

TypeScript implementation of Nodes core — behavioral and on-disk-format parity with
the Python distribution. Core contains the domain-free kernel and the general-purpose
knowledge vocabulary.
```

Keep later references to the kernel when they specifically describe kernel APIs or the kernel/vocab dependency boundary.

- [ ] **Step 4: Verify living files contain only the accepted identities**

Run from the repository root:

```bash
rg -n '@nodes/kernel|^name = "nodes"$' README.md ts/README.md python/pyproject.toml ts/package.json ts/package-lock.json
rg -n 'nodes-core|@nodes-dev/core' README.md ts/README.md python/pyproject.toml ts/package.json ts/package-lock.json
```

Expected: the first command exits with status 1 and no matches; the second reports the new Python and npm identities in metadata and living docs.

- [ ] **Step 5: Run every repository gate**

Run from `python/`:

```bash
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen pyright src
```

Expected: the test suite passes, Ruff reports `All checks passed!`, and Pyright reports zero errors.

Run from `ts/`:

```bash
npm test
npm run typecheck
npm run check
```

Expected: Vitest passes, TypeScript exits successfully with no diagnostics, and Biome reports no errors.

- [ ] **Step 6: Commit the living documentation update**

```bash
git add README.md ts/README.md
git commit -m "docs: align core package identities"
```

Expected: one commit containing only the two living README files.

---

### Task 4: Audit the completed identity slice

**Files:**
- Verify: `python/pyproject.toml`
- Verify: `ts/package.json`
- Verify: `ts/package-lock.json`
- Verify: `README.md`
- Verify: `ts/README.md`
- Verify (no edits): `~/d/mindful/v6/package.json`
- Verify (no edits): `~/d/mindful/v6/node_modules/@nodes/kernel`

**Interfaces:**
- Consumes: the three committed deliverables above.
- Produces: evidence that the mechanical slice is complete and clean, plus an explicit record of mindful's temporarily inconsistent local dependency, without performing downstream, registry, or repository mutations.

- [ ] **Step 1: Scan all non-historical tracked files for the obsolete identities**

Run from the repository root:

```bash
rg -n '@nodes/kernel|^name = "nodes"$' --glob '!docs/designs/**' --glob '!docs/plans/**' .
```

Expected: no matches. Historical records are intentionally excluded because they preserve prior context.

- [ ] **Step 2: Audit mindful's quiet dependency-name mismatch without changing it**

Run from the package-identity worktree root:

```bash
node -e 'const fs = require("node:fs"); const mindful = JSON.parse(fs.readFileSync(process.argv[1], "utf8")); const core = JSON.parse(fs.readFileSync(process.argv[2], "utf8")); console.log(JSON.stringify({ requested: mindful.dependencies["@nodes/kernel"], bundled: mindful.bundledDependencies.includes("@nodes/kernel"), declared: core.name }, null, 2))' ~/d/mindful/v6/package.json ts/package.json
```

Expected: `requested` is `file:../../nodes/ts`, `bundled` is `true`, and the worktree package declares `@nodes-dev/core`. This directly records the dependency-name mismatch that a future mindful `npm install` would reconcile.

As a no-commit downstream baseline, run from `~/d/mindful/v6`:

```bash
realpath node_modules/@nodes/kernel
npm run build
```

Expected: `realpath` identifies the main Nodes checkout, and the mindful build can still pass because its existing `node_modules/@nodes/kernel` symlink resolves there. Record that this is only a current-consumer API baseline: the symlink does not target the isolated package-identity worktree, so this passing build is not evidence of package-name compatibility. The build may refresh ignored `dist/` output but must not change tracked mindful files.

- [ ] **Step 3: Record mindful migration as the top follow-up**

Record this follow-up in the implementation handoff:

```text
Before running npm install in ~/d/mindful/v6, migrate its file dependency,
bundledDependencies entry, source imports, freshness script, lockfile, and installed
link from @nodes/kernel to @nodes-dev/core; then run mindful's full build/test/typecheck/check gates.
```

This downstream migration needs its own reviewed commit in the mindful repository. Do not edit mindful in this package-identity slice and do not add a compatibility package or alias in Nodes.

- [ ] **Step 4: Inspect the branch commits and worktree state**

```bash
git log --oneline --decorate -5
git status --short
```

Expected: the Python metadata, TypeScript metadata, and documentation commits are present; `git status --short` prints nothing.

- [ ] **Step 5: Stop at the implementation boundary**

Do not create npm/PyPI organizations, publish either package, transfer the GitHub repository, edit `~/d/mindful/` or `~/d/science/`, introduce domain package layouts, or decide the Python domain import namespace. Carry the explicit mindful migration from Step 3 as the first downstream follow-up; record the other items as follow-up work governed by the accepted design rather than expanding this branch.
