# Nodes First Publish Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the first usable lockstep Nodes release as `nodes-core==0.1.1` and `@nodes-dev/core@0.1.1` without moving the failed `core/v0.1.0` tag.

**Architecture:** Pin uv 0.11.29 throughout CI and release automation, make the PyPI hash checker understand signed distribution directories, then replace the Metadata-2.5-incompatible PyPA action with explicit PEP 740 signing and `uv publish`. Build once, verify the exact stored artifacts, rehearse without publish permissions, and publish 0.1.1 from the immutable `core/v0.1.1` tag through OIDC.

**Tech Stack:** GitHub Actions (SHA-pinned actions), uv 0.11.29, Hatchling/Core Metadata 2.5, `pypi-attestations==0.0.29`, npm 11 trusted publishing, PyPI and npm OIDC.

## Global Constraints

- The governing design is `~/d/nodes/docs/designs/2026-07-18-nodes-first-publish-recovery-design.md`; `docs/STANDARD.md` remains the normative product contract.
- Preserve local and remote `core/v0.1.0` at commit `f4043dab94a5b78d8fe82f47ce129fe80d0aa193`. Never delete, move, or reuse it.
- Neither registry contains 0.1.0. Do not create registry version 0.1.0 during recovery.
- The recovery version is 0.1.1 in `python/pyproject.toml`, the editable root entry in `python/uv.lock`, `ts/package.json`, both root entries in `ts/package-lock.json`, and tag `core/v0.1.1`.
- Regenerate lockfile versions with `uv version 0.1.1 --no-sync` and `npm version 0.1.1 --no-git-tag-version`; do not hand-edit lockfiles.
- Every `astral-sh/setup-uv` step in `.github/workflows/ci.yml` and `.github/workflows/release.yml` installs `version: "0.11.29"`.
- Every workflow `uses:` remains pinned to a full 40-character commit SHA with a release-version comment; never add a mutable action tag or branch.
- Workflow permissions default to `contents: read`. Only `publish-npm` and `publish-pypi` receive `id-token: write`, and both stay gated on tag-push events.
- `workflow_dispatch` remains input-free and unconditionally skips both publish jobs.
- The PyPI path uses no registry token: sign with pinned `pypi-attestations==0.0.29`, dry-run the signed default `dist/` selection, then publish with `--trusted-publishing always`.
- The npm trusted-publisher entry is already corrected to `nodes-dev/core`, workflow `release.yml`, environment `release`, allowed action `npm publish`.
- Python gates, from `python/`: `uv run --frozen pytest -q`, `uv run --frozen ruff check .`, `uv run --frozen pyright src`.
- TypeScript gates, from `ts/`: `npm test`, `npm run typecheck`, `npm run check`.
- Run all six gates before every commit, including documentation-only or test-only commits.
- Before each commit, `git status --porcelain -- fixtures/` must print nothing. Stage only the explicit files named by that task; never stage `dist/`, tarballs, or fixtures.
- Run `npm audit --omit=dev` before the release-automation commit and before tagging; it must report zero production vulnerabilities.
- Do not add compatibility layers, AI attribution, or co-author trailers.
- Steps marked **[OWNER]** require the human owner. Stop, notify with `ohai`, and wait for confirmation.

## File Structure

- Modify `~/d/nodes/.github/workflows/ci.yml` — pin the uv binary used by Python CI gates.
- Modify `~/d/nodes/.github/workflows/release.yml` — pin uv for build/verification/publish, add the unsigned artifact dry run, and replace the PyPA publisher with sign/dry-run/publish steps.
- Modify `~/d/nodes/.github/scripts/pypi_upload_check.py` — distinguish distributions from matching PEP 740 sidecars and enforce pre/post mode requirements.
- Modify `~/d/nodes/python/tests/test_release_scripts.py` — pin workflow structure, versions, and publish command ordering.
- Create `~/d/nodes/python/tests/test_pypi_upload_check.py` — unit-test clean, signed, missing-sidecar, and stray-file directory states.
- Modify `~/d/nodes/python/pyproject.toml` and regenerate `~/d/nodes/python/uv.lock` — set Python release version 0.1.1.
- Modify `~/d/nodes/ts/package.json` and regenerate `~/d/nodes/ts/package-lock.json` — set npm release version 0.1.1.

---

### Task 0: Create the isolated recovery worktree

**Files:** None.

**Interfaces:**
- Consumes: clean primary checkout on `main`, including approved design commit `57be6df` and this plan commit.
- Produces: branch `fix/first-publish-recovery` in `~/d/nodes/.worktrees/first-publish-recovery`.

- [ ] **Step 1: Confirm the primary checkout and immutable failed tag**

```bash
cd ~/d/nodes
git status --short --branch
test "$(git rev-parse core/v0.1.0^{commit})" = "f4043dab94a5b78d8fe82f47ce129fe80d0aa193"
test "$(git ls-remote origin refs/tags/core/v0.1.0 | cut -f1)" = "f4043dab94a5b78d8fe82f47ce129fe80d0aa193"
```

Expected: clean `main`; both tag assertions exit 0.

- [ ] **Step 2: Create an isolated worktree**

Use `superpowers:using-git-worktrees`. Its resulting commands must be equivalent to:

```bash
cd ~/d/nodes
git check-ignore -q .worktrees
git worktree add .worktrees/first-publish-recovery -b fix/first-publish-recovery main
cd ~/d/nodes/.worktrees/first-publish-recovery
test "$(git branch --show-current)" = "fix/first-publish-recovery"
```

Expected: `.worktrees` is ignored; the final assertion exits 0.

- [ ] **Step 3: Establish a green baseline**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen pyright src
cd ~/d/nodes/.worktrees/first-publish-recovery/ts
npm test
npm run typecheck
npm run check
```

Expected: 480 Python tests pass; Ruff and Pyright report no findings; 41 TypeScript files and 326 tests pass; typecheck and Biome pass.

---

### Task 1: Pin the uv binary in every workflow

**Files:**
- Modify: `~/d/nodes/.github/workflows/ci.yml`
- Modify: `~/d/nodes/.github/workflows/release.yml`
- Test: `~/d/nodes/python/tests/test_release_scripts.py`

**Interfaces:**
- Consumes: existing SHA-pinned `astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990` steps.
- Produces: every existing setup-uv step installs exactly uv 0.11.29; Task 4 raises the release-workflow expected count when it adds the publish step.

- [ ] **Step 1: Add YAML inspection helpers and the failing pin test**

Add `import yaml`, the CI constant, and these helpers/tests to `python/tests/test_release_scripts.py`:

```python
import yaml

CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
UV_VERSION = "0.11.29"


def _workflow_steps(path: Path) -> list[dict[str, object]]:
    workflow = yaml.safe_load(path.read_text())
    return [
        step
        for job in workflow["jobs"].values()
        if isinstance(job, dict)
        for step in job.get("steps", [])
        if isinstance(step, dict)
    ]


@pytest.mark.parametrize(
    ("workflow", "expected_count"),
    [(CI_WORKFLOW, 1), (RELEASE_WORKFLOW, 2)],
)
def test_workflows_pin_every_setup_uv_binary(workflow: Path, expected_count: int) -> None:
    steps = [
        step
        for step in _workflow_steps(workflow)
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    ]

    assert len(steps) == expected_count
    assert {step.get("with", {}).get("version") for step in steps} == {UV_VERSION}
```

Keep imports grouped and alphabetized for Ruff.

- [ ] **Step 2: Run the pin test and verify RED**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q tests/test_release_scripts.py::test_workflows_pin_every_setup_uv_binary
```

Expected: FAIL because each setup-uv step currently lacks `with.version`.

- [ ] **Step 3: Pin uv 0.11.29 on the three existing setup steps**

In `.github/workflows/ci.yml`, make the Python setup block:

```yaml
      - uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990 # v8.3.2
        with:
          version: "0.11.29"
          python-version: ${{ matrix.python-version }}
```

In `.github/workflows/release.yml`, make the build setup block:

```yaml
      - uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990 # v8.3.2
        with:
          version: "0.11.29"
```

Make the verify-artifacts setup block identical to that release build block.

- [ ] **Step 4: Run the focused test and verify GREEN**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q tests/test_release_scripts.py::test_workflows_pin_every_setup_uv_binary
```

Expected: PASS.

- [ ] **Step 5: Run all six gates and fixture check**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen pyright src
cd ~/d/nodes/.worktrees/first-publish-recovery/ts
npm test
npm run typecheck
npm run check
cd ~/d/nodes/.worktrees/first-publish-recovery
test -z "$(git status --porcelain -- fixtures/)"
git diff --check
```

Expected: all gates pass, fixture assertion and diff check exit 0.

- [ ] **Step 6: Commit the uv pin**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery
git add .github/workflows/ci.yml .github/workflows/release.yml python/tests/test_release_scripts.py
git commit -m "ci: pin uv release toolchain"
```

Expected: one commit containing only the three named files.

---

### Task 2: Make the PyPI hash checker sidecar-aware

**Files:**
- Modify: `~/d/nodes/.github/scripts/pypi_upload_check.py`
- Create: `~/d/nodes/python/tests/test_pypi_upload_check.py`

**Interfaces:**
- Consumes: a directory containing exactly one `.whl`, one `.tar.gz`, and optionally their adjacent `.publish.attestation` files.
- Produces: `local_files(dist: str, *, require_attestations: bool) -> dict[str, str]`; hashes only distributions, permits no unmatched sidecars, and requires both sidecars in post mode.

- [ ] **Step 1: Write the failing sidecar tests**

Create `python/tests/test_pypi_upload_check.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/pypi_upload_check.py"
WHEEL = "nodes_core-0.1.1-py3-none-any.whl"
SDIST = "nodes_core-0.1.1.tar.gz"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pypi_upload_check", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = _load_script()


def _write_distributions(dist: Path) -> None:
    dist.mkdir()
    (dist / WHEEL).write_bytes(b"wheel")
    (dist / SDIST).write_bytes(b"sdist")


def test_local_files_accepts_unsigned_precheck_directory(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_distributions(dist)

    files = CHECK.local_files(str(dist), require_attestations=False)

    assert set(files) == {WHEEL, SDIST}


def test_local_files_accepts_matching_signed_postcheck_directory(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_distributions(dist)
    (dist / f"{WHEEL}.publish.attestation").write_text("wheel attestation")
    (dist / f"{SDIST}.publish.attestation").write_text("sdist attestation")

    files = CHECK.local_files(str(dist), require_attestations=True)

    assert set(files) == {WHEEL, SDIST}


def test_local_files_requires_both_postcheck_attestations(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dist = tmp_path / "dist"
    _write_distributions(dist)
    (dist / f"{WHEEL}.publish.attestation").write_text("wheel attestation")

    with pytest.raises(SystemExit, match="1"):
        CHECK.local_files(str(dist), require_attestations=True)

    assert capsys.readouterr().out == f"FAIL: missing distribution attestations: ['{SDIST}.publish.attestation']\n"


@pytest.mark.parametrize(
    "extra_name",
    ["notes.txt", "other.whl.publish.attestation"],
)
def test_local_files_rejects_unrelated_entries(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra_name: str,
) -> None:
    dist = tmp_path / "dist"
    _write_distributions(dist)
    (dist / extra_name).write_text("unexpected")

    with pytest.raises(SystemExit, match="1"):
        CHECK.local_files(str(dist), require_attestations=False)

    assert capsys.readouterr().out == f"FAIL: unexpected files in distribution directory: ['{extra_name}']\n"
```

- [ ] **Step 2: Run the new tests and verify RED**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q tests/test_pypi_upload_check.py
```

Expected: five failures because `local_files` does not accept `require_attestations`.

- [ ] **Step 3: Implement strict distribution and sidecar classification**

Replace `local_files` in `.github/scripts/pypi_upload_check.py` with:

```python
def local_files(dist: str, *, require_attestations: bool) -> dict[str, str]:
    names = sorted(os.listdir(dist))
    wheels = [name for name in names if name.endswith(".whl")]
    sdists = [name for name in names if name.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1:
        fail(f"expected exactly 1 wheel and 1 sdist, found wheels={wheels}, sdists={sdists}")

    distributions = wheels + sdists
    expected_attestations = {f"{name}.publish.attestation" for name in distributions}
    present_attestations = {name for name in names if name.endswith(".publish.attestation")}
    unexpected = sorted(set(names) - set(distributions) - expected_attestations)
    if unexpected:
        fail(f"unexpected files in distribution directory: {unexpected}")
    if require_attestations:
        missing = sorted(expected_attestations - present_attestations)
        if missing:
            fail(f"missing distribution attestations: {missing}")

    out: dict[str, str] = {}
    for name in distributions:
        with open(os.path.join(dist, name), "rb") as fh:
            out[name] = hashlib.sha256(fh.read()).hexdigest()
    return out
```

Change the call in `main()` to:

```python
    local = local_files(args.dist, require_attestations=args.mode == "post")
```

- [ ] **Step 4: Run the checker tests and verify GREEN**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q tests/test_pypi_upload_check.py
```

Expected: five tests pass.

- [ ] **Step 5: Run the existing live-index pre-check**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
rm -rf dist
uv build --no-create-gitignore
python3 ../.github/scripts/pypi_upload_check.py pre --project nodes-core --version 0.1.0 --dist dist
rm -rf dist
```

Expected: `pypi pre-check ok: 0/2 files present and matching`; `dist/` is removed afterward. If PyPI unexpectedly contains 0.1.1, stop before any release work.

- [ ] **Step 6: Run all six gates and fixture check**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen pyright src
cd ~/d/nodes/.worktrees/first-publish-recovery/ts
npm test
npm run typecheck
npm run check
cd ~/d/nodes/.worktrees/first-publish-recovery
test -z "$(git status --porcelain -- fixtures/)"
git diff --check
```

Expected: all gates pass; fixtures remain clean.

- [ ] **Step 7: Commit the checker change**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery
git add .github/scripts/pypi_upload_check.py python/tests/test_pypi_upload_check.py
git commit -m "ci: validate signed PyPI artifact sets"
```

Expected: one commit containing only the checker and its new test file.

---

### Task 3: Roll both package identities to 0.1.1

**Files:**
- Modify: `~/d/nodes/python/pyproject.toml`
- Regenerate: `~/d/nodes/python/uv.lock`
- Modify: `~/d/nodes/ts/package.json`
- Regenerate: `~/d/nodes/ts/package-lock.json`
- Test: `~/d/nodes/python/tests/test_release_scripts.py`

**Interfaces:**
- Consumes: current lockstep 0.1.0 manifests and lockfiles.
- Produces: exact lockstep version 0.1.1 across both package ecosystems.

- [ ] **Step 1: Add the failing four-file version test**

Add `import json` and `import tomllib` to `python/tests/test_release_scripts.py`, then add:

```python
EXPECTED_RELEASE_VERSION = "0.1.1"


def test_release_manifests_and_lockfiles_are_lockstep_0_1_1() -> None:
    pyproject = tomllib.loads((ROOT / "python/pyproject.toml").read_text())
    uv_lock = tomllib.loads((ROOT / "python/uv.lock").read_text())
    package_json = json.loads((ROOT / "ts/package.json").read_text())
    package_lock = json.loads((ROOT / "ts/package-lock.json").read_text())
    editable = [
        package
        for package in uv_lock["package"]
        if package["name"] == "nodes-core" and package.get("source") == {"editable": "."}
    ]
    assert len(editable) == 1

    versions = {
        "python/pyproject.toml": pyproject["project"]["version"],
        "python/uv.lock": editable[0]["version"],
        "ts/package.json": package_json["version"],
        "ts/package-lock.json root": package_lock["version"],
        "ts/package-lock.json package": package_lock["packages"][""]["version"],
    }
    assert versions == {name: EXPECTED_RELEASE_VERSION for name in versions}
```

- [ ] **Step 2: Run the version test and verify RED**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q tests/test_release_scripts.py::test_release_manifests_and_lockfiles_are_lockstep_0_1_1
```

Expected: FAIL showing all five recorded values are 0.1.0.

- [ ] **Step 3: Regenerate the Python version and lockfile**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv version 0.1.1 --no-sync
```

Expected: `nodes-core 0.1.0 => 0.1.1`; only `pyproject.toml` and `uv.lock` change on the Python side.

- [ ] **Step 4: Regenerate the npm version and lockfile**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/ts
npm version 0.1.1 --no-git-tag-version
```

Expected: `v0.1.1`; `package.json` and both root version entries in `package-lock.json` change.

- [ ] **Step 5: Run the version test and verify GREEN**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q tests/test_release_scripts.py::test_release_manifests_and_lockfiles_are_lockstep_0_1_1
```

Expected: PASS.

- [ ] **Step 6: Audit the generated diff and run all gates**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery
git diff -- python/pyproject.toml python/uv.lock ts/package.json ts/package-lock.json
git diff --check
test -z "$(git status --porcelain -- fixtures/)"
cd python
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen pyright src
cd ../ts
npm test
npm run typecheck
npm run check
```

Expected: the diff contains only version changes; all gates pass.

- [ ] **Step 7: Commit the lockstep version**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery
git add python/pyproject.toml python/uv.lock ts/package.json ts/package-lock.json python/tests/test_release_scripts.py
git commit -m "chore: roll first release to 0.1.1"
```

Expected: one commit containing only the five named files.

---

### Task 4: Replace the PyPA upload action with signed uv publication

**Files:**
- Modify: `~/d/nodes/.github/workflows/release.yml`
- Test: `~/d/nodes/python/tests/test_release_scripts.py`

**Interfaces:**
- Consumes: uv 0.11.29 pin, sidecar-aware pre/post checker, and version 0.1.1 artifacts.
- Produces: unsigned-distribution rehearsal dry run plus tag-gated pre-check → sign → signed-directory dry-run → OIDC publish → post-check sequence.

- [ ] **Step 1: Raise the expected release setup count and add failing publish-pipeline tests**

Change the `RELEASE_WORKFLOW` setup-uv expectation in `test_workflows_pin_every_setup_uv_binary` from 2 to 3. Add:

```python
def _job_steps(path: Path, job_name: str) -> list[dict[str, object]]:
    workflow = yaml.safe_load(path.read_text())
    return workflow["jobs"][job_name]["steps"]


def _normalized_run(step: dict[str, object]) -> str:
    return " ".join(str(step.get("run", "")).split())


def test_release_rehearses_uv_against_only_python_distributions() -> None:
    commands = [_normalized_run(step) for step in _job_steps(RELEASE_WORKFLOW, "verify-artifacts")]

    assert (
        "uv publish --dry-run --trusted-publishing never "
        "dist-python/*.whl dist-python/*.tar.gz"
    ) in commands


def test_release_pypi_job_signs_validates_and_publishes_default_dist() -> None:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text())
    job = workflow["jobs"]["publish-pypi"]
    steps = _job_steps(RELEASE_WORKFLOW, "publish-pypi")
    names = [step.get("name") for step in steps]
    commands = [_normalized_run(step) for step in steps]
    uses = [str(step.get("uses", "")) for step in steps]

    assert job["if"] == "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/core/v')"
    assert job["environment"] == "release"
    assert job["permissions"] == {"contents": "read", "id-token": "write"}
    assert not any(value.startswith("pypa/gh-action-pypi-publish@") for value in uses)
    assert (
        "uvx --from pypi-attestations==0.0.29 python -m pypi_attestations sign "
        "dist/*.whl dist/*.tar.gz"
    ) in commands
    assert "uv publish --dry-run --trusted-publishing never" in commands
    assert (
        "uv publish --trusted-publishing always --check-url https://pypi.org/simple/"
    ) in commands
    assert names.index("PyPI pre-upload check") < names.index("Generate PyPI attestations")
    assert names.index("Generate PyPI attestations") < names.index("Validate signed PyPI upload set")
    assert names.index("Validate signed PyPI upload set") < names.index("Publish to PyPI")
    assert names.index("Publish to PyPI") < names.index("PyPI post-upload check")
```

- [ ] **Step 2: Run the three workflow tests and verify RED**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q \
  tests/test_release_scripts.py::test_workflows_pin_every_setup_uv_binary \
  tests/test_release_scripts.py::test_release_rehearses_uv_against_only_python_distributions \
  tests/test_release_scripts.py::test_release_pypi_job_signs_validates_and_publishes_default_dist
```

Expected: all three fail: release has only two setup-uv steps, no Python publish dry run, and still uses the PyPA action.

- [ ] **Step 3: Add the unsigned-distribution uv dry run**

In `verify-artifacts`, after both install smoke steps and before npm's dry run, add:

```yaml
      - name: PyPI publish dry-run
        run: |
          uv publish --dry-run --trusted-publishing never \
            dist-python/*.whl dist-python/*.tar.gz
```

- [ ] **Step 4: Replace the PyPI action with the exact signed publication sequence**

Keep checkout and artifact download. Replace the current pre-check/action/post-check tail with:

```yaml
      - uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990 # v8.3.2
        with:
          version: "0.11.29"
      - name: PyPI pre-upload check
        run: python3 .github/scripts/pypi_upload_check.py pre --project nodes-core --version "${GITHUB_REF#refs/tags/core/v}" --dist dist
      - name: Generate PyPI attestations
        run: uvx --from pypi-attestations==0.0.29 python -m pypi_attestations sign dist/*.whl dist/*.tar.gz
      - name: Validate signed PyPI upload set
        run: uv publish --dry-run --trusted-publishing never
      - name: Publish to PyPI
        run: uv publish --trusted-publishing always --check-url https://pypi.org/simple/
      - name: PyPI post-upload check
        run: python3 .github/scripts/pypi_upload_check.py post --project nodes-core --version "${GITHUB_REF#refs/tags/core/v}" --dist dist
```

Do not change the job condition, environment, permissions, dependencies, artifact name, or artifact path.

- [ ] **Step 5: Run the focused workflow tests and verify GREEN**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q \
  tests/test_release_scripts.py::test_workflows_pin_every_setup_uv_binary \
  tests/test_release_scripts.py::test_release_rehearses_uv_against_only_python_distributions \
  tests/test_release_scripts.py::test_release_pypi_job_signs_validates_and_publishes_default_dist
```

Expected: three tests pass.

- [ ] **Step 6: Exercise uv 0.11.29 dry-run forms locally**

Use the exact binary version in an isolated uvx cache so the workstation's uv 0.11.28 does not substitute:

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
rm -rf dist
uv build --no-create-gitignore
uvx --from uv==0.11.29 uv publish --dry-run --trusted-publishing never dist/*.whl dist/*.tar.gz
uvx --from uv==0.11.29 uv publish --dry-run --trusted-publishing never
rm -rf dist
```

Expected: both dry runs succeed without credentials or upload; `dist/` is removed afterward.

- [ ] **Step 7: Run release hygiene and all six gates**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/ts
npm audit --omit=dev
npm test
npm run typecheck
npm run check
cd ../python
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen pyright src
cd ..
test -z "$(git status --porcelain -- fixtures/)"
git diff --check
git diff | rg -ni "password|secret|api[_-]?key|token" || test $? -eq 1
```

Expected: zero production vulnerabilities; all six gates pass; fixtures and diff are clean. Any secret-scan matches must be inspected and be explanatory workflow/documentation text, never credential material.

- [ ] **Step 8: Commit the release pipeline**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery
git add .github/workflows/release.yml python/tests/test_release_scripts.py
git commit -m "ci: publish signed Python artifacts with uv"
```

Expected: one commit containing only the workflow and its regression tests.

---

### Task 5: Review, merge, push, and rehearse 0.1.1

**Files:** No planned source edits; review fixes must be committed separately with all six gates.

**Interfaces:**
- Consumes: four implementation commits on `fix/first-publish-recovery`.
- Produces: reviewed `main` on GitHub and a fully green input-free rehearsal for its exact commit.

- [ ] **Step 1: Run final local verification in the worktree**

```bash
cd ~/d/nodes/.worktrees/first-publish-recovery/python
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen pyright src
cd ../ts
npm test
npm run typecheck
npm run check
npm audit --omit=dev
cd ..
test -z "$(git status --porcelain -- fixtures/)"
git diff --check
test -z "$(git status --porcelain)"
```

Expected: all gates and audit pass; fixtures and worktree are clean.

- [ ] **Step 2: Request a fresh branch review**

Use `superpowers:requesting-code-review`. Give the reviewer:

- base: the implementation branch's parent commit on `main` (the committed plan);
- head: `fix/first-publish-recovery`;
- governing design: `~/d/nodes/docs/designs/2026-07-18-nodes-first-publish-recovery-design.md`;
- required checks: uv pin coverage, checker fail-closed classification, version lockstep, publish ordering/permissions, dispatch skip invariant, exact artifact reuse, no mutable action references.

Expected: no Critical, Important, or Minor findings. If findings exist, fix them test-first, run all six gates, commit explicitly, and request re-review.

- [ ] **Step 3: Fast-forward the primary checkout**

Use `superpowers:finishing-a-development-branch`, option "Merge back to main locally". The result must be equivalent to:

```bash
cd ~/d/nodes
git status --short --branch
git merge --ff-only fix/first-publish-recovery
```

Expected: fast-forward succeeds; no merge commit.

- [ ] **Step 4: Re-run all gates on merged main**

```bash
cd ~/d/nodes/python
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen pyright src
cd ../ts
npm test
npm run typecheck
npm run check
npm audit --omit=dev
cd ..
test -z "$(git status --porcelain -- fixtures/)"
test -z "$(git status --porcelain)"
```

Expected: all gates and audit pass; primary checkout is clean.

- [ ] **Step 5: Push main and wait for exact-commit CI**

```bash
cd ~/d/nodes
git push origin main
SHA="$(git rev-parse HEAD)"
RUN_ID=""
for _ in $(seq 1 24); do
  RUN_ID="$(gh run list --repo nodes-dev/core --workflow ci.yml --event push --commit "$SHA" --limit 1 --json databaseId --jq '.[0].databaseId // empty')"
  test -n "$RUN_ID" && break
  sleep 5
done
test -n "$RUN_ID"
gh run watch --repo nodes-dev/core --exit-status "$RUN_ID"
```

Expected: the exact pushed commit's Python 3.11/3.13 and Node 20/24 jobs all succeed.

- [ ] **Step 6: Dispatch and watch the exact-commit rehearsal**

```bash
cd ~/d/nodes
SHA="$(git rev-parse HEAD)"
PREV="$(gh run list --repo nodes-dev/core --workflow release.yml --event workflow_dispatch --commit "$SHA" --limit 1 --json databaseId --jq '.[0].databaseId // empty')"
gh workflow run release.yml --repo nodes-dev/core --ref main
RUN_ID=""
for _ in $(seq 1 24); do
  RUN_ID="$(gh run list --repo nodes-dev/core --workflow release.yml --event workflow_dispatch --commit "$SHA" --limit 1 --json databaseId --jq '.[0].databaseId // empty')"
  if test -n "$RUN_ID" && test "$RUN_ID" != "$PREV"; then
    break
  fi
  RUN_ID=""
  sleep 5
done
test -n "$RUN_ID"
gh run watch --repo nodes-dev/core --exit-status "$RUN_ID"
gh run view --repo nodes-dev/core "$RUN_ID" --json jobs | python3 -c '
import json, sys
jobs = json.load(sys.stdin)["jobs"]
publish = {j["name"]: j["conclusion"] for j in jobs if j["name"] in {"publish-npm", "publish-pypi"}}
assert publish == {"publish-npm": "skipped", "publish-pypi": "skipped"}, publish
failed = {j["name"]: j["conclusion"] for j in jobs if j["conclusion"] not in {"success", "skipped"}}
assert not failed, failed
print("rehearsal publish jobs skipped; all executable jobs green")
'
```

Expected: gates, build, artifact checks, install smokes, npm dry run, and uv unsigned-distribution dry run succeed; both publish jobs are skipped.

- [ ] **Step 7: Remove the worktree and branch**

```bash
cd ~/d/nodes
git worktree remove .worktrees/first-publish-recovery
git worktree prune
git branch -d fix/first-publish-recovery
```

Expected: worktree removed and merged branch deleted; `main` remains clean.

---

### Task 6: Tag, publish, verify, and retire the bootstrap

**Files:** No repository edits. Registry mutations are the `core/v0.1.1` tag, two version publications, and npm 0.0.0 deprecation.

**Interfaces:**
- Consumes: green pushed `main`, green exact-commit rehearsal, corrected npm publisher, and pending PyPI publisher.
- Produces: immutable `core/v0.1.1`, `nodes-core==0.1.1`, `@nodes-dev/core@0.1.1`, verified provenance/attestations, and deprecated npm 0.0.0.

- [ ] **Step 1: Prove release targets are absent and main is exact**

```bash
cd ~/d/nodes
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git tag --list core/v0.1.1)"
REMOTE_TAG="$(git ls-remote --tags origin refs/tags/core/v0.1.1)"
test -z "$REMOTE_TAG"
NPM_OUT="$(npm view @nodes-dev/core@0.1.1 version --prefer-online 2>&1)"
NPM_STATUS=$?
test "$NPM_STATUS" -ne 0
printf '%s' "$NPM_OUT" | rg 'E404|404 Not Found'
PYPI_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' https://pypi.org/pypi/nodes-core/0.1.1/json)"
test "$PYPI_STATUS" = "404"
npm --prefix ts audit --omit=dev
```

Expected: clean exact `main`; tag and both registry versions absent; production audit finds zero vulnerabilities.

- [ ] **Step 2: Create and push the immutable release tag**

```bash
cd ~/d/nodes
git tag core/v0.1.1
git push origin core/v0.1.1
```

Expected: remote accepts the new tag. Never delete or move it after this point.

- [ ] **Step 3: Watch the exact tag-push release run**

```bash
cd ~/d/nodes
SHA="$(git rev-parse core/v0.1.1^{commit})"
RUN_ID=""
for _ in $(seq 1 24); do
  RUN_ID="$(gh run list --repo nodes-dev/core --workflow release.yml --event push --commit "$SHA" --limit 1 --json databaseId --jq '.[0].databaseId // empty')"
  test -n "$RUN_ID" && break
  sleep 5
done
test -n "$RUN_ID"
gh run watch --repo nodes-dev/core --exit-status "$RUN_ID"
```

Expected: gates, build, verify-artifacts, `publish-npm`, and `publish-pypi` all succeed.

If a publish job fails, do not move the tag or create another version immediately. Inspect the exact job log first. For a transient OIDC/registry/configuration failure that requires no code change, run `gh run rerun --repo nodes-dev/core "$RUN_ID" --failed`; the same run reuses the stored distributions and registry duplicate checks. If workflow or artifact code must change, stop: 0.1.1 remains an immutable failed tag and recovery must roll forward again.

- [ ] **Step 4: Verify PyPI installation, file set, and attestations**

```bash
S="$(mktemp -d)"
uv venv "$S/venv"
uv pip install --python "$S/venv/bin/python" nodes-core==0.1.1
"$S/venv/bin/python" - <<'EOF'
import importlib

import nodes.core

assert nodes.core.__name__ == "nodes.core"
assert getattr(nodes, "__file__", None) is None
legacy = ".".join(["nodes", "kernel"])
try:
    importlib.import_module(legacy)
except ModuleNotFoundError as exc:
    assert exc.name == legacy
else:
    raise SystemExit("legacy import path importable")
print("pypi install smoke ok")
EOF
rm -rf "$S"

python3 - <<'EOF'
import json
import urllib.parse
import urllib.request

project = "nodes-core"
version = "0.1.1"
expected = {
    "nodes_core-0.1.1-py3-none-any.whl",
    "nodes_core-0.1.1.tar.gz",
}
with urllib.request.urlopen(f"https://pypi.org/pypi/{project}/{version}/json", timeout=30) as response:
    release = json.load(response)
filenames = {item["filename"] for item in release["urls"]}
assert filenames == expected, f"unexpected PyPI file set: {sorted(filenames)}"

for filename in sorted(expected):
    quoted = urllib.parse.quote(filename, safe="")
    request = urllib.request.Request(
        f"https://pypi.org/integrity/{project}/{version}/{quoted}/provenance",
        headers={"Accept": "application/vnd.pypi.integrity.v1+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        provenance = json.load(response)
    bundles = provenance.get("attestation_bundles", [])
    matching = [
        bundle
        for bundle in bundles
        if bundle.get("attestations")
        and bundle.get("publisher", {}).get("kind") == "GitHub"
        and bundle["publisher"].get("repository") == "nodes-dev/core"
        and bundle["publisher"].get("workflow") == "release.yml"
        and bundle["publisher"].get("environment") == "release"
    ]
    assert matching, f"expected release publisher provenance missing for {filename}"
print("pypi attestations ok: 2 files")
EOF
```

Expected: `pypi install smoke ok` and `pypi attestations ok: 2 files`. A temporary index propagation 404 may be retried after two minutes; missing Integrity data is never treated as propagation success.

- [ ] **Step 5: Verify npm installation and provenance**

```bash
npm view @nodes-dev/core@0.1.1 --json | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert d["version"] == "0.1.1", d["version"]
att = d.get("dist", {}).get("attestations")
assert att and att.get("url"), f"attestations missing: {att!r}"
print("npm 0.1.1 present with attestations")
'
S="$(mktemp -d)"
cd "$S"
npm init -y >/dev/null
npm install --no-audit --no-fund @nodes-dev/core@0.1.1 >/dev/null
node --input-type=module -e "const core = await import('@nodes-dev/core'); if (Object.keys(core).length === 0) throw new Error('no exports'); console.log('npm registry smoke ok');"
cd ~/d/nodes
rm -rf "$S"
```

Expected: `npm 0.1.1 present with attestations` and `npm registry smoke ok`.

- [ ] **Step 6 [OWNER]: Deprecate npm 0.0.0 with a short-lived login**

Notify the owner and wait. The owner runs `npm login` from `~/d/nodes/ts` and replies `Done`. Then run this mutation/readback/revocation block:

```bash
cd ~/d/nodes/ts
DEPRECATE_STATUS=0
npm whoami || DEPRECATE_STATUS=$?
if test "$DEPRECATE_STATUS" -eq 0; then
  npm deprecate @nodes-dev/core@0.0.0 "Bootstrap release for trusted-publishing setup; use >=0.1.1." || DEPRECATE_STATUS=$?
fi
if test "$DEPRECATE_STATUS" -eq 0; then
  npm view @nodes-dev/core@0.0.0 --json | python3 -c '
import json, sys
d = json.load(sys.stdin)
expected = "Bootstrap release for trusted-publishing setup; use >=0.1.1."
assert d.get("deprecated") == expected, d.get("deprecated")
print("0.0.0 deprecated")
' || DEPRECATE_STATUS=$?
fi
LOGOUT_OUT="$(npm logout 2>&1)"
LOGOUT_STATUS=$?
WHOAMI_OUT="$(npm whoami 2>&1)"
WHOAMI_STATUS=$?
if test "$LOGOUT_STATUS" -ne 0; then
  echo "FAIL: npm logout failed: $LOGOUT_OUT"
  CREDENTIAL_STATUS=1
elif test "$WHOAMI_STATUS" -eq 0; then
  echo "FAIL: npm still authenticated as $WHOAMI_OUT"
  CREDENTIAL_STATUS=1
elif printf '%s' "$WHOAMI_OUT" | rg -q 'ENEEDAUTH|E401'; then
  echo "npm deprecation credential revoked"
  CREDENTIAL_STATUS=0
else
  echo "FAIL: whoami failed for another reason: $WHOAMI_OUT"
  CREDENTIAL_STATUS=1
fi
test "$CREDENTIAL_STATUS" -eq 0
test "$DEPRECATE_STATUS" -eq 0
```

Expected: owner username, `0.0.0 deprecated`, `npm deprecation credential revoked`, overall exit 0. Logout and fail-closed authentication proof run even if deprecation fails.

- [ ] **Step 7: Final repository and tag hygiene**

```bash
cd ~/d/nodes
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test "$(git rev-parse core/v0.1.0^{commit})" = "f4043dab94a5b78d8fe82f47ce129fe80d0aa193"
test "$(git rev-parse core/v0.1.1^{commit})" = "$(git rev-parse HEAD)"
test "$(git ls-remote origin refs/tags/core/v0.1.1 | cut -f1)" = "$(git rev-parse HEAD)"
test ! -e python/dist
rm -rf ts/dist
test ! -e ts/dist
```

Expected: clean synchronized main; immutable 0.1.0 tag unchanged; local/remote 0.1.1 tag at HEAD; no local build residue.

---

## Final Verification

- All six gates pass on the implementation branch and merged `main`; fixtures remain untouched.
- All setup-uv steps in CI and release install uv 0.11.29; all action references remain full-SHA pinned.
- Exact-commit CI and the input-free release rehearsal are green; dispatch skips both publish jobs.
- `core/v0.1.0` remains at `f4043dab94a5b78d8fe82f47ce129fe80d0aa193`; `core/v0.1.1` exists locally and remotely at the released `main` commit.
- Clean installs and imports succeed for `nodes-core==0.1.1` and `@nodes-dev/core@0.1.1`.
- PyPI exposes exactly the 0.1.1 wheel and sdist, each with Integrity API provenance from `nodes-dev/core`, `release.yml`, environment `release`.
- npm 0.1.1 metadata includes attestations; npm 0.0.0 is deprecated in favor of `>=0.1.1`.
- The temporary npm deprecation credential is revoked and `npm whoami` fails specifically for absent authentication.
- Production npm audit reports zero vulnerabilities; primary checkout is clean and synchronized with `origin/main`.
