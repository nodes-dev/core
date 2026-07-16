# Nodes first publish: public home and lockstep 0.1.0 release

- **Date:** 2026-07-16
- **Status:** Accepted
- **Follows:** `~/d/nodes/docs/designs/2026-07-11-nodes-package-identity-and-ownership-design.md`
  (which fixed the names, ownership model, and lockstep release contract) and
  `~/d/nodes/docs/designs/2026-07-13-nodes-python-package-layout-design.md` (which
  closed the last pre-release layout blocker).

## 1. Context

Every design-level pre-release blocker is closed: the identity design fixed the
public names (`nodes-dev/core`, `@nodes-dev/core`, `nodes-core`), and the layout
design stabilized the Python import surface (`nodes` namespace, `nodes.core`).
What remains is operational: the project has no public home and no release
machinery.

Facts that bear on the design:

- **The repository has no git remote.** `nodes-dev/core` does not exist yet;
  creating the public home means pushing this local repository to GitHub, not
  transferring an existing one. The `nodes-dev` GitHub organization already exists
  (identity design §2.2). Both stored `gh` tokens are currently invalid;
  re-authentication is a prerequisite.
- **No CI exists.** There is no `.github/` directory; all six gates
  (Python pytest/ruff/pyright, TypeScript test/typecheck/biome) run locally via
  `rtk`. Trusted OIDC publishing requires GitHub Actions workflows.
- **Nothing is licensed.** There is no `LICENSE` file and neither manifest carries
  license metadata. Public registry releases need this decided and shipped.
- **Manifests are close but not publish-ready.** `ts/package.json` lacks
  `license`, `repository`, and `publishConfig.access` (scoped packages default to
  restricted). `python/pyproject.toml` lacks `license`, `readme`, `authors`, and
  `[project.urls]`, and `python/` has no README for the sdist/wheel to carry.
  Both versions already read 0.1.0.
- **`python/uv.lock` is gitignored.** The gates mandate `uv run --frozen`, but the
  lockfile they freeze against exists only on one machine. CI cannot run frozen
  gates against an untracked lockfile. (`ts/package-lock.json` is already tracked.)
- **npm trusted publishing cannot create a package.** A trusted publisher is
  configured on an existing package's settings page, which does not exist before
  the first publish (npm/cli#8544, open as of 2026-07). A one-time manual
  bootstrap publish is unavoidable on the npm side.
- **PyPI has no such gap.** A *pending trusted publisher* binds a not-yet-existing
  project name to a repository, workflow file, and environment; the first
  pipeline upload creates the project. The PyPI organization request (identity
  design §2.2) is approval-gated but does not block first publish: projects can
  be moved into an organization later.

## 2. Decision

Create the public home and publish the first lockstep release — `nodes-core`
0.1.0 on PyPI and `@nodes-dev/core` 0.1.0 on npm — from one tag, `core/v0.1.0`,
through a tag-driven GitHub Actions pipeline using trusted OIDC publishing on
both registries. No long-lived registry tokens are created for the pipeline; the
only manual publish ever performed is the npm bootstrap (§2.5).

### 2.1 Repository home

`nodes-dev/core` is created public and `main` is pushed with full history — the
dated designs and plans are part of the project's public record. This checkout
(`~/d/nodes`) remains the primary working copy and gains `origin`. Interactive
prerequisite: `gh auth refresh` for the account that controls the `nodes-dev`
organization.

### 2.2 License

MIT, copyright Keith Hughitt. The canonical text lives at the repository root
(`LICENSE`); identical copies live at `python/LICENSE` and `ts/LICENSE` because
each packaging tool collects license files from its own package directory and
neither reaches above it (hatchling's `license-files` resolves inside the
project directory; npm auto-includes `LICENSE` from the package root it
publishes, which is `ts/`). Manifests carry the SPDX expression: PEP 639
`license = "MIT"` plus `license-files` in `python/pyproject.toml`, and
`"license": "MIT"` in `ts/package.json`.

### 2.3 Manifest completion

- `ts/package.json` adds `license`, `repository` (git URL with
  `"directory": "ts"`), `homepage`, `bugs`, and
  `publishConfig: { "access": "public" }`. Provenance is generated automatically
  by OIDC publishing and is not configured in the manifest.
- `python/pyproject.toml` adds `license`, `license-files`, `readme`, `authors`,
  `[project.urls]` (Homepage, Repository, Issues), and the `Typing :: Typed`
  classifier. A short `python/README.md` is created as the PyPI landing page
  (`ts/README.md` already serves npm).
- `uv.lock` leaves `.gitignore` and `python/uv.lock` is committed. This makes the
  frozen gates mean the same thing locally and in CI, and makes local runs
  reproducible across machines.

### 2.4 Workflows

Two workflows, sharing the six gates. Both pin every external action to a
verified full-length commit SHA (with its release version in a comment), never
a mutable branch or tag. All non-publishing jobs grant only `contents: read`;
each publishing job explicitly grants `contents: read` plus `id-token: write`.

- **`.github/workflows/ci.yml`** — on pushes to `main` and pull requests. Two
  matrix jobs mirroring the gates exactly, each run at the declared floor and a
  current version: Python on **3.11 (the `requires-python` floor) and 3.13** via
  `astral-sh/setup-uv` (`uv sync --frozen`, then `uv run --frozen pytest -q`,
  `ruff check .`, `pyright src`) and TypeScript on **Node 20 (the `engines`
  floor) and 24** via `actions/setup-node` (`npm ci`, then `npm test`,
  `npm run typecheck`, `npm run check`). The commands are the AGENTS.md gates
  without the local `rtk` wrapper.
- **`.github/workflows/release.yml`** — on `push` of tags matching `core/v*`,
  plus a plain `workflow_dispatch` (no inputs) that is unconditionally a
  rehearsal: dispatch runs everything except the publish jobs, which are gated
  on `github.event_name == 'push' && startsWith(github.ref,
  'refs/tags/core/v')`. Dispatch inputs are caller-supplied values and cannot
  carry a release invariant, and a dispatch has no tag to check versions
  against — so publishing is conditioned on the tag ref alone. Every run first
  requires the two manifest versions to agree; tag pushes additionally require
  `core/vX.Y.Z` to equal that shared version. Runs are serialized by tag ref
  (`cancel-in-progress: false`) so two attempts cannot race one another at the
  registries. Jobs, in dependency order:
  - **gates** — the six gates, reusing the CI matrix (floors and current
    versions).
  - **build** — each artifact is built exactly once and uploaded as a workflow
    artifact. It checks manifest equality on every run and tag↔manifest
    consistency on tag pushes before building. Python: `uv build` creates the
    sdist and then builds the wheel from that sdist, so the sdist is the source
    of truth for both published files. TypeScript: `npm ci`, `rm -rf dist`,
    `npm run build`, then `npm pack` — the compile step is explicit because
    nothing in `package.json` attaches it to packing (`files: ["dist"]`, no
    `prepare`/`prepack`), and `tsc` never deletes stale outputs, so packing
    without a clean build ships either nothing or stale files.
  - **verify-artifacts** — downloads the built artifacts and verifies those
    exact files. Both Python distributions pass metadata checks; the sdist
    contains `pyproject.toml`, `README.md`, `LICENSE`, and
    `src/nodes/core/py.typed`, and excludes `src/nodes/__init__.py`; and the
    wheel passes the layout design §6 assertions (`nodes/core/py.typed`
    present, `nodes/__init__.py` absent, `Import-Name: nodes.core` and
    `Import-Namespace: nodes` in METADATA). Each Python file is installed
    independently into a scratch environment and passes the namespace-layout
    smoke checks — installing the sdist necessarily rebuilds it and proves it
    is a usable source artifact. The npm tarball contains `dist/index.js` and
    `dist/index.d.ts` and no paths outside `dist/`, `README.md`, `LICENSE`, and
    `package.json`; it installs into a scratch project and `@nodes-dev/core`
    imports.
  - **publish-npm** and **publish-pypi** — tag pushes only; each depends on
    gates, build, and verify-artifacts, and **downloads and publishes the same
    verified artifacts** (`npm publish <tarball>`; `pypa/gh-action-pypi-publish`
    pointed at the downloaded dist directory) — never a rebuild. All three
    distribution files exist and are verified before either registry upload
    starts (all-or-nothing up to the upload boundary, which is as far as two
    registries allow). Each runs in the protected `release` GitHub environment
    with its job-scoped OIDC permission. npm publishes with OIDC and automatic
    provenance on Node 24 (meets npm trusted-publishing requirements); PyPI
    publishes with OIDC and PEP 740 attestations.

### 2.5 Registry setup and the npm bootstrap

Interactive administrative steps, driven by the project owner with exact
instructions in the implementation plan:

- **npm:** create the `nodes-dev` organization on the free public-packages plan
  (this reserves the `@nodes-dev` scope), then perform the one-time bootstrap:
  manually publish `@nodes-dev/core` **0.0.0** from a workstation to create the
  package, configure the trusted publisher (repository `nodes-dev/core`,
  workflow `release.yml`, environment `release`, allowed action
  `npm publish` — configurations created after 2026-05-20 must select allowed
  actions), and after the real release `npm deprecate` 0.0.0 pointing at
  `>=0.1.0`. The bootstrap publish MUST be made from a clean build
  (`rm -rf dist && npm ci && npm run build`), never from an existing
  workstation `dist/` — at the time of writing this workstation's ignored
  `dist/` still contains retired `dist/vocab/` outputs, which is exactly the
  stale-output hazard — and its tarball is checked with the same content
  assertions as §2.4's verify-artifacts before upload. The bootstrap does not
  conflict with the identity design's "no empty placeholders" rule: that rule
  forbids reserving *domain* names on PyPI with nothing behind them; this is a
  registry-imposed bootstrap for a package shipping the same day, on the same
  version line.
- **PyPI:** add a pending trusted publisher for `nodes-core` (same
  repository/workflow/environment binding) on the owner's account. No
  placeholder, no token. The PyPI organization request remains a separate,
  approval-gated follow-up outside this design.
- **GitHub:** create the `release` environment on `nodes-dev/core` with its
  deployment policy restricted to **selected tags matching `core/v*`** (no
  branches), so a publish job can only ever run against a release tag even if a
  workflow bug loosened its own conditions. No required reviewers: the project
  has a single maintainer and the pipeline is designed to run unattended once a
  tag is pushed; the tag push itself is the human approval. Both trusted
  publishers name this environment, so the registry bindings and the
  environment policy enforce the same invariant from both sides.

### 2.6 First release

Versions already read 0.1.0 on both sides; no bump. Push tag `core/v0.1.0`; the
pipeline publishes both artifacts. Post-release verification (§4) then closes
the slice.

## 3. Error handling

- **Version skew fails closed:** the build job rejects manifest disagreement on
  every run and, on a tag push, rejects a tag version that does not equal the
  shared manifest version — all before either artifact builds.
- **Gate or verification failure publishes nothing:** publish jobs are
  unreachable unless the gates, both builds, and the artifact verification all
  succeed.
- **Partial publish is loud, and recovery rolls forward:** if one registry
  upload fails after the other succeeded, the workflow run fails visibly.
  Recovery re-runs the failed publish job at the same version; the successful
  artifact is never retracted (identity design §2.4). Registry versions are
  never reused.
- **Partial upload within PyPI recovers file-by-file:** PyPI filenames are
  immutable — if the sdist uploaded and the wheel did not, the sdist's filename
  can never be uploaded again, so a blind re-run would fail forever. Before
  every upload, the publish job queries PyPI's project JSON for the target
  version and compares the remote file set with the two local artifacts (an
  absent project or version is the expected empty set on first publish). An
  unexpected filename or any SHA-256 mismatch fails closed; matching existing
  files are the byte-identical artifacts from an earlier partial attempt. Only
  after that check does the action run with `skip-existing: true`, allowing it
  to skip matching files and upload only missing ones. A post-upload query must
  find exactly the expected two filenames with matching SHA-256 digests. The
  per-tag workflow concurrency guard prevents two attempts from racing between
  the preflight and upload. npm has no within-registry partial state (one
  tarball); a failed `npm publish` uploaded nothing and re-runs cleanly.
- **Rehearsal before reality:** a plain `workflow_dispatch` run exercises
  gates, build, and artifact verification (including `npm publish --dry-run`
  against the tarball) with the publish jobs skipped by their tag-ref
  condition, so the first tag push is not the pipeline's first execution.

## 4. Testing and verification

- CI green on `main` after the push (both gate matrices, including the Node 20
  and Python 3.11 floor legs — the first time the declared floors are actually
  tested).
- Release rehearsal (plain `workflow_dispatch`) green before tagging,
  including the artifact verification job against real built artifacts.
- After `core/v0.1.0`: install `nodes-core` from PyPI into a scratch
  environment and run the namespace-layout smoke checks (`import nodes.core`;
  `getattr(nodes, "__file__", None) is None`; `nodes.kernel` raises name-checked
  `ModuleNotFoundError`); `npm view @nodes-dev/core` shows 0.1.0 with
  provenance; install `@nodes-dev/core@0.1.0` from npm into a fresh scratch
  project and import it; the npm 0.0.0 bootstrap is deprecated.
- All six gates before every commit, as always; fixtures untouched.

## 5. Alternatives considered

### 5.1 Manual first publish, automation later

Publish 0.1.0 by hand with short-lived tokens and build the pipeline in a later
slice. Rejected: the permanent pipeline stays unbuilt and untested, and the
first — most scrutinized — artifacts ship without provenance or attestations.

### 5.2 CI verify, manual upload

Let CI build and verify on the tag, download artifacts, upload by hand.
Rejected: keeps a human token path alive indefinitely and gives up provenance
for no operational gain over the dry-run rehearsal.

### 5.3 Fresh public history

Start `nodes-dev/core` from a squashed initial commit. Rejected: the dated
design and plan record is part of the project's value, and the history is
clean.

### 5.4 npm bootstrap with the real 0.1.0

Publish 0.1.0 manually as the bootstrap instead of 0.0.0. Rejected: the first
real version would lack provenance and would not validate the pipeline; a
deprecated 0.0.0 placeholder is the established community pattern for npm's
first-publish gap.

## 6. Consequences

- `pip install nodes-core` and `npm install @nodes-dev/core` work; science can
  adopt `nodes.core` / `@nodes-dev/core` as real dependencies (next design, in
  the science repo).
- The release path is tag-driven and tokenless from the first real version;
  npm 0.0.0 remains visible but deprecated.
- `python/uv.lock` becomes tracked; dependency updates now appear in diffs.
- The repository, its designs, and its history are public.
- Follow-ups explicitly out of scope: PyPI organization request, PEP 541
  transfer of the legacy `nodes` name, branch protection, domain packages.

## 7. Implementation boundary

One implementation slice in this repository: license files, manifest and
README additions, lockfile tracking, the two workflows, the interactive
registry/bootstrap steps (owner-driven, plan-guided), the repository push, and
the `core/v0.1.0` release with its post-release verification. It does not touch
kernel code, fixtures, `docs/STANDARD.md`, science, or mindful, and it does not
file the PyPI organization or PEP 541 requests.
