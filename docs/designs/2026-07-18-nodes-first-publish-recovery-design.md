# Nodes first publish recovery: roll forward with uv

- **Date:** 2026-07-18
- **Status:** Accepted
- **Amends:** `~/d/nodes/docs/designs/2026-07-16-nodes-first-publish-design.md`

## 1. Context

The first tag-driven release, `core/v0.1.0`, passed its gates, build, and
artifact verification, then failed independently in both publish jobs. Neither
registry received version 0.1.0.

The failures have distinct confirmed causes:

- npm rejected the OIDC publish because the package's trusted-publisher entry
  named workflow `rebase.yml` and environment `rebase`, while the job presented
  `release.yml` and `release`. The owner corrected the saved entry to the
  intended values.
- PyPI's pinned `pypa/gh-action-pypi-publish` v1.14.0 image bundles Twine 6.1.0.
  Twine caps accepted core metadata at 2.4 and rejects this project's valid
  Metadata 2.5 `Import-Name` and `Import-Namespace` fields before upload. The
  compatibility fix is merged upstream but has not been released; Twine issue
  [#1327](https://github.com/pypa/twine/issues/1327) tracks the release gap.

The public tag and its workflow commit are immutable. A GitHub Actions re-run
would use the same pinned PyPI action and fail again. Repointing or deleting the
tag would erase useful release history and violate the original design's
never-reuse identity rule.

## 2. Decision

Roll forward to lockstep version 0.1.1 and tag `core/v0.1.1`. Preserve
`core/v0.1.0`, the npm 0.0.0 bootstrap, and the Metadata 2.5 import declarations.

The original design remains authoritative except where this recovery design
changes the first usable version and the PyPI publishing implementation.

### 2.1 Versions and identities

- Set `python/pyproject.toml`, `python/uv.lock`, `ts/package.json`, and
  `ts/package-lock.json` to 0.1.1.
- Do not publish, reuse, delete, or move version/tag 0.1.0.
- Continue using one shared tag and one pair of artifacts for the lockstep
  release.
- After successful verification, deprecate npm 0.0.0 with a message directing
  users to `>=0.1.1`.

### 2.2 Pre-publish compatibility gate

Add `uv publish --dry-run --trusted-publishing never` to `verify-artifacts` for
the exact downloaded Python distributions. This exercises the uploader's
metadata parser during rehearsals and tag runs while explicitly forbidding
credential discovery or upload. It closes the gap that allowed the
Twine/Metadata 2.5 incompatibility to survive the original rehearsal.

The existing Python artifact verifier and install smoke tests remain. The dry
run supplements them; it does not replace content, namespace-layout, or install
verification.

### 2.3 PyPI publication

Replace `pypa/gh-action-pypi-publish` with three explicit, fail-closed steps in the
existing `publish-pypi` job:

1. Install uv through the already SHA-pinned `astral-sh/setup-uv` action.
2. Generate adjacent PEP 740 publish attestations for the downloaded wheel and
   sdist with pinned `pypi-attestations==0.0.29`. In GitHub Actions, the signer
   uses the job's ambient OIDC identity.
3. Run `uv publish --trusted-publishing always --check-url
   https://pypi.org/simple/ dist/*`.

`--trusted-publishing always` forbids a silent fallback to workstation or token
credentials. `--check-url` makes a retry skip only byte-identical existing
files. uv discovers and uploads the adjacent attestations with their matching
distributions. The existing pre-upload and post-upload filename/SHA-256 checks
remain as independent fail-closed guards.

The job retains `environment: release`, `contents: read`, and `id-token: write`.
No registry token or repository secret is added.

### 2.4 npm publication

No workflow code change is needed for npm authentication. The package's saved
trusted-publisher identity now matches the existing job:

- organization/user: `nodes-dev`
- repository: `core`
- workflow: `release.yml`
- environment: `release`
- allowed action: `npm publish`

The next rehearsal still skips publishing. The `core/v0.1.1` tag run exercises
the corrected OIDC identity through the existing npm publish job.

## 3. Security and error handling

- **Tag integrity:** `core/v0.1.0` remains at its original commit. Only the new
  0.1.1 commit can receive `core/v0.1.1`.
- **Least privilege:** only the two tag-gated publish jobs receive
  `id-token: write`; dispatch remains an unconditional rehearsal.
- **Exact artifacts:** publish jobs download the artifacts built once by the
  successful build job. Neither job rebuilds.
- **Attestation failure:** signing completes before `uv publish`; a signing
  failure uploads nothing.
- **Partial PyPI upload:** the existing preflight rejects unexpected remote
  filenames or hashes. uv skips only identical files, and the postflight
  requires the complete expected set with exact hashes.
- **Partial registry release:** if one registry succeeds and the other fails,
  the successful version remains immutable. Recovery reruns only the failed job
  with the same stored artifacts.
- **Credential hygiene:** publication uses OIDC only. The short-lived npm login
  used to inspect configuration has already been revoked and `npm whoami`
  fails closed.

## 4. Verification

Before the recovery commit:

- Add focused workflow regression tests that fail against the current workflow
  and then prove:
  - Python artifact verification includes `uv publish --dry-run
    --trusted-publishing never`;
  - the PyPI job pins `pypi-attestations==0.0.29` and signs the distributions;
  - publication requires trusted publishing, uses the PyPI simple index for
    duplicate checks, and no longer invokes the incompatible PyPA action;
  - all four manifest/lockfile versions are 0.1.1.
- Run the six repository gates and confirm `fixtures/` is untouched.
- Run a production-only npm audit and scan the staged diff for secrets.

Before tagging:

- Push the reviewed commit to `main` and require its CI run to pass.
- Run an input-free `workflow_dispatch` rehearsal for the exact commit. Gates,
  build, both artifact verifiers, both install smokes, npm's dry run, and uv's
  dry run must pass; both publish jobs must be skipped.
- Confirm neither registry contains 0.1.1 and no local or remote
  `core/v0.1.1` tag exists.

After pushing `core/v0.1.1`:

- Select the release run by event and exact commit, and require every job to
  succeed.
- Install and import `nodes-core==0.1.1` and `@nodes-dev/core@0.1.1` from clean
  environments.
- Verify npm provenance and both PyPI file attestations identify
  `nodes-dev/core` and `release.yml`.
- Verify registry filenames and SHA-256 digests, then deprecate npm 0.0.0 in
  favor of `>=0.1.1` and revoke the temporary deprecation credential.

## 5. Alternatives considered

### 5.1 Remove Metadata 2.5 fields and keep the PyPA action

This would reduce the workflow change, but it discards intentional, valid
package import declarations solely to accommodate an unreleased Twine fix. The
package metadata should describe the package accurately.

### 5.2 Delete and recreate `core/v0.1.0`

No registry currently contains 0.1.0, so rewriting the tag could make 0.1.0 the
first usable release. Rejected: public tags and their workflow history are
release records even when publication fails. Rewriting one weakens the exact
invariant the release pipeline is meant to establish.

### 5.3 Remove the npm bootstrap package

Rejected: npm trusted publishing requires an existing package to hold the
publisher configuration. Keeping and later deprecating 0.0.0 is the intended
bootstrap lifecycle.

### 5.4 Wait for new Twine and PyPA action releases

Rejected: the upstream release date is outside this project's control, and the
immutable 0.1.0 workflow would still reference v1.14.0. A new commit and tag are
required either way.
