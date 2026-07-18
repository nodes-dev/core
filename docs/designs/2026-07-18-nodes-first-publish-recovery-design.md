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

- Set `~/d/nodes/python/pyproject.toml` and its regenerated
  `~/d/nodes/python/uv.lock` to 0.1.1 with
  `uv version 0.1.1 --no-sync`. Set `~/d/nodes/ts/package.json` and both
  version entries in its regenerated `~/d/nodes/ts/package-lock.json` with
  `npm version 0.1.1 --no-git-tag-version`. Do not hand-edit either lockfile.
- Do not publish, reuse, delete, or move version/tag 0.1.0.
- Continue using one shared tag and one pair of artifacts for the lockstep
  release.
- After successful verification, deprecate npm 0.0.0 with a message directing
  users to `>=0.1.1`.

### 2.2 Pre-publish compatibility gate

Pin every `astral-sh/setup-uv` invocation in
`~/d/nodes/.github/workflows/ci.yml` and
`~/d/nodes/.github/workflows/release.yml` to uv 0.11.29 through the action's
`version:` input. Pinning the action implementation does not pin the uv binary
it downloads; the explicit binary version makes the gates, build, rehearsal,
signing, and publication use one reviewed toolchain.

Add this command to `verify-artifacts` for the exact downloaded Python
distributions:

```bash
uv publish --dry-run --trusted-publishing never \
  dist-python/*.whl dist-python/*.tar.gz
```

The distribution-only globs exercise the uploader's metadata parser during
rehearsals and tag runs while explicitly forbidding credential discovery or
upload. This closes the gap that allowed the Twine/Metadata 2.5 incompatibility
to survive the original rehearsal.

The existing Python artifact verifier and install smoke tests remain. The dry
run supplements them; it does not replace content, namespace-layout, or install
verification.

### 2.3 PyPI publication

Replace `pypa/gh-action-pypi-publish` with an explicit, fail-closed sequence in
the existing `publish-pypi` job. Including the existing guards, the full order
is:

1. Install uv 0.11.29 through the SHA-pinned `astral-sh/setup-uv` action.
2. Run the existing remote filename/SHA-256 pre-check.
3. Generate adjacent PEP 740 publish attestations for `dist/*.whl` and
   `dist/*.tar.gz` with pinned `pypi-attestations==0.0.29`. In GitHub Actions,
   the signer uses the job's ambient OIDC identity.
4. From the repository root, run
   `uv publish --dry-run --trusted-publishing never` with no positional files.
   This exercises uv's documented default
   `dist/` discovery after the attestations exist, before any upload.
5. Run
   `uv publish --trusted-publishing always --check-url https://pypi.org/simple/`,
   again with no positional files.
6. Run the existing remote filename/SHA-256 post-check.

`--trusted-publishing always` forbids a silent fallback to workstation or token
credentials. `--check-url` makes a retry skip only byte-identical existing
files. With no positionals, uv selects the distributions and their adjacent
attestations from `dist/` and ignores unrelated files instead of receiving an
expanded shell glob as an explicit upload set. The existing pre-upload and
post-upload filename/SHA-256 checks remain as independent fail-closed guards.

The current `~/d/nodes/.github/scripts/pypi_upload_check.py` treats every entry
in its distribution directory as a release file and requires exactly two. Once
signing adds two `.publish.attestation` sidecars, that behavior would make the
post-check fail locally. Update the checker to hash only the one wheel and one
sdist, allow only the corresponding adjacent attestation filename for each,
and reject every unrelated directory entry. Pre-check mode permits the clean
unsigned pair; post-check mode additionally requires both matching sidecars to
exist. The remote comparison remains strictly between PyPI's release files and
the two local distributions; the Integrity API verifies the uploaded sidecars
after publication.

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
- **Attestation first-use risk:** the signer requires ambient OIDC, so the
  input-free rehearsal cannot execute it without granting a non-publish job
  `id-token: write`. Least privilege wins: signing first runs in the real
  tag-gated publish job. A signing failure uploads nothing; after signing, the
  no-positionals dry run validates the complete `dist/` directory before the
  upload; and a corrected rerun reuses the same stored distributions.
- **Partial PyPI upload:** the existing preflight rejects unexpected remote
  filenames or hashes. The local checker rejects sidecars that do not match a
  distribution and all other stray files. uv skips only identical files, and
  the postflight requires the complete expected distribution set with exact
  hashes.
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
  - every setup-uv use pins the uv binary to 0.11.29;
  - Python artifact verification includes distribution-only globs with
    `uv publish --dry-run --trusted-publishing never`;
  - the PyPI job pins `pypi-attestations==0.0.29` and signs the distributions;
  - the PyPI job dry-runs and publishes through uv's default `dist/` discovery
    with no positional upload set;
  - publication requires trusted publishing, uses the PyPI simple index for
    duplicate checks, and no longer invokes the incompatible PyPA action;
  - the PyPI hash checker permits only matching attestation sidecars, requires
    both in post mode, and rejects unmatched sidecars or unrelated files;
  - all four manifest/lockfile versions are 0.1.1.
- Run the six repository gates and confirm `fixtures/` is untouched.
- Run a production-only npm audit and scan the staged diff for secrets.

Before tagging:

- Push the reviewed commit to `main` and require its CI run to pass.
- Run an input-free `workflow_dispatch` rehearsal for the exact commit. Gates,
  build, both artifact verifiers, both install smokes, npm's dry run, and uv's
  unsigned-artifact dry run must pass; both publish jobs must be skipped. The
  OIDC signing step is deliberately not rehearsed under dispatch.
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
