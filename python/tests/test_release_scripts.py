from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tomllib

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
NPM_VERIFIER = ROOT / ".github/scripts/verify_npm_tarball.py"
NPM_SMOKE = ROOT / ".github/scripts/smoke_install_npm.sh"
PYTHON_SMOKE = ROOT / ".github/scripts/smoke_install_python.sh"
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"
REQUIRED = (
    "package/package.json",
    "package/README.md",
    "package/LICENSE",
    "package/dist/index.js",
    "package/dist/index.d.ts",
)
UV_VERSION = "0.11.29"
EXPECTED_RELEASE_VERSION = "0.1.1"
PUBLISH_GATE = "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/core/v')"
DOWNLOAD_ARTIFACT_ACTION = (
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
)
EXTERNAL_ACTION_LINE = re.compile(
    r"^\s+(?:- )?uses: [A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$"
)
CREDENTIAL_MATERIAL = re.compile(
    r"(?:secrets\.|(?<![A-Za-z])(?:token|password|credential|api[-_]?key|username)(?![A-Za-z]))",
    re.IGNORECASE,
)
REBUILD_COMMAND = re.compile(
    r"(?:^|[\s;&|])(?:uv build|hatch build|python3? -m build|"
    r"npm (?:ci|install|build|pack|run (?:build|typecheck|tsc)|exec tsc)|"
    r"npx(?: --no-install)? tsc|tsc)(?:\s|$)",
)


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


def _workflow(path: Path) -> dict[str | bool, object]:
    workflow = yaml.safe_load(path.read_text())
    assert isinstance(workflow, dict)
    return workflow


def _jobs(path: Path) -> dict[str, dict[str, object]]:
    jobs = _workflow(path)["jobs"]
    assert isinstance(jobs, dict)
    assert all(isinstance(name, str) and isinstance(job, dict) for name, job in jobs.items())
    return jobs


def _workflow_triggers(path: Path) -> dict[str, object]:
    workflow = _workflow(path)
    assert "on" not in workflow
    assert True in workflow, "PyYAML SafeLoader no longer parses the YAML 1.1 'on' key as True"
    triggers = workflow[True]
    assert isinstance(triggers, dict)
    return triggers


def _job(path: Path, job_name: str) -> dict[str, object]:
    return _jobs(path)[job_name]


def _workflow_steps(path: Path) -> list[dict[str, object]]:
    return [
        step
        for job in _jobs(path).values()
        for step in job.get("steps", [])
        if isinstance(step, dict)
    ]


def _job_steps(path: Path, job_name: str) -> list[dict[str, object]]:
    steps = _job(path, job_name)["steps"]
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return steps


def _normalized_run(step: dict[str, object]) -> str:
    return " ".join(str(step.get("run", "")).split())


def _external_action_lines(path: Path) -> list[str]:
    lines = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith(("uses: ", "- uses: ")):
            continue
        reference = stripped.split("uses: ", maxsplit=1)[1]
        if not reference.startswith("./"):
            lines.append(line)
    assert lines
    return lines


def _ordered_named_commands(
    steps: list[dict[str, object]],
    expected_names: list[str],
) -> list[tuple[str, str]]:
    actual_names = [step.get("name") for step in steps]
    for name in expected_names:
        assert actual_names.count(name) == 1
    return [
        (name, _normalized_run(step))
        for step in steps
        if isinstance((name := step.get("name")), str) and name in expected_names
    ]


def _mapping_material(
    container: dict[str, object],
    field: str,
    context: str,
) -> list[tuple[str, str]]:
    mapping = container.get(field, {})
    assert isinstance(mapping, dict)
    return [
        (f"{context}.{field}.{key}", f"{key}={value}") for key, value in mapping.items()
    ]


def _publish_job_surfaces(job_name: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    job = _job(RELEASE_WORKFLOW, job_name)
    steps = _job_steps(RELEASE_WORKFLOW, job_name)
    material = _mapping_material(job, "env", job_name)
    runs = []
    for index, step in enumerate(steps):
        context = f"{job_name}.steps[{index}]"
        material.extend(_mapping_material(step, "env", context))
        material.extend(_mapping_material(step, "with", context))
        if "run" in step:
            assert isinstance(step["run"], str)
            run = _normalized_run(step)
            material.append((f"{context}.run", run))
            runs.append((f"{context}.run", run))
    return material, runs


@pytest.mark.parametrize(
    ("workflow", "expected_count"),
    [(CI_WORKFLOW, 1), (RELEASE_WORKFLOW, 3)],
)
def test_workflows_pin_every_setup_uv_binary(workflow: Path, expected_count: int) -> None:
    steps = [
        step
        for step in _workflow_steps(workflow)
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    ]

    assert len(steps) == expected_count
    assert {step.get("with", {}).get("version") for step in steps} == {UV_VERSION}


@pytest.mark.parametrize("workflow", [CI_WORKFLOW, RELEASE_WORKFLOW])
def test_workflows_pin_external_actions_to_full_shas_with_version_comments(workflow: Path) -> None:
    lines = _external_action_lines(workflow)

    assert [line for line in lines if not EXTERNAL_ACTION_LINE.fullmatch(line)] == []


def test_release_workflow_uses_explicit_filesystem_tarball_paths() -> None:
    commands = [
        line.strip()
        for line in RELEASE_WORKFLOW.read_text().splitlines()
        if line.strip().startswith(("run: npm publish", "- run: npm publish"))
    ]

    assert commands == [
        'run: npm publish --dry-run "./$(ls dist-npm/*.tgz)"',
        '- run: npm publish "./$(ls dist-npm/*.tgz)"',
    ]


def test_release_rehearses_uv_against_only_python_distributions() -> None:
    commands = [
        command
        for step in _job_steps(RELEASE_WORKFLOW, "verify-artifacts")
        if (command := _normalized_run(step)).startswith("uv publish")
    ]

    assert commands == [
        "uv publish --dry-run --trusted-publishing never "
        "dist-python/*.whl dist-python/*.tar.gz"
    ]


def test_release_limits_oidc_to_inputless_tag_gated_publish_jobs() -> None:
    workflow = _workflow(RELEASE_WORKFLOW)
    jobs = _jobs(RELEASE_WORKFLOW)
    triggers = _workflow_triggers(RELEASE_WORKFLOW)
    id_token_jobs = {
        name: permissions["id-token"]
        for name, job in jobs.items()
        if isinstance((permissions := job.get("permissions", {})), dict)
        and "id-token" in permissions
    }

    assert workflow["permissions"] == {"contents": "read"}
    assert triggers["workflow_dispatch"] is None
    assert id_token_jobs == {"publish-npm": "write", "publish-pypi": "write"}
    for name in id_token_jobs:
        assert jobs[name]["if"] == PUBLISH_GATE
        assert jobs[name]["environment"] == "release"
        assert jobs[name]["permissions"] == {"contents": "read", "id-token": "write"}


def test_release_pypi_job_binds_verified_artifacts() -> None:
    job = _job(RELEASE_WORKFLOW, "publish-pypi")
    steps = _job_steps(RELEASE_WORKFLOW, "publish-pypi")
    downloads = [
        step for step in steps if str(step.get("uses", "")).startswith("actions/download-artifact@")
    ]

    assert job["needs"] == ["gates", "build", "verify-artifacts"]
    assert downloads == [
        {
            "uses": DOWNLOAD_ARTIFACT_ACTION,
            "with": {"name": "python-dist", "path": "dist"},
        }
    ]


def test_publish_jobs_contain_no_credentials_or_rebuilds() -> None:
    credential_findings = []
    rebuild_findings = []
    for job_name in ["publish-npm", "publish-pypi"]:
        material, runs = _publish_job_surfaces(job_name)
        credential_findings.extend(
            (context, value)
            for context, value in material
            if CREDENTIAL_MATERIAL.search(value)
        )
        rebuild_findings.extend(
            (context, command)
            for context, command in runs
            if REBUILD_COMMAND.search(command)
        )

    assert (credential_findings, rebuild_findings) == ([], [])


def test_release_pypi_job_signs_validates_and_publishes_default_dist() -> None:
    job = _job(RELEASE_WORKFLOW, "publish-pypi")
    steps = _job_steps(RELEASE_WORKFLOW, "publish-pypi")
    uses = [str(step.get("uses", "")) for step in steps]
    expected_sequence = [
        (
            "PyPI pre-upload check",
            "python3 .github/scripts/pypi_upload_check.py pre --project nodes-core "
            '--version "${GITHUB_REF#refs/tags/core/v}" --dist dist',
        ),
        (
            "Generate PyPI attestations",
            "uvx --from pypi-attestations==0.0.29 python -m pypi_attestations sign "
            "dist/*.whl dist/*.tar.gz",
        ),
        ("Validate signed PyPI upload set", "uv publish --dry-run --trusted-publishing never"),
        (
            "Publish to PyPI",
            "uv publish --trusted-publishing always --check-url https://pypi.org/simple/",
        ),
        (
            "PyPI post-upload check",
            "python3 .github/scripts/pypi_upload_check.py post --project nodes-core "
            '--version "${GITHUB_REF#refs/tags/core/v}" --dist dist',
        ),
    ]

    assert job["if"] == "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/core/v')"
    assert job["environment"] == "release"
    assert job["permissions"] == {"contents": "read", "id-token": "write"}
    assert not any(value.startswith("pypa/gh-action-pypi-publish@") for value in uses)
    assert _ordered_named_commands(steps, [name for name, _ in expected_sequence]) == expected_sequence


def _regular_file(name: str, content: bytes = b"content") -> tuple[tarfile.TarInfo, bytes]:
    member = tarfile.TarInfo(name)
    member.size = len(content)
    return member, content


def _write_tarball(path: Path, members: list[tuple[tarfile.TarInfo, bytes | None]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for member, content in members:
            archive.addfile(member, io.BytesIO(content) if content is not None else None)


def _valid_members(*, without: str | None = None) -> list[tuple[tarfile.TarInfo, bytes | None]]:
    return [_regular_file(name) for name in REQUIRED if name != without]


def _run_verifier(tarball: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(NPM_VERIFIER), str(tarball)],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "member_name",
    [
        "package/dist/../../escaped",
        "package/dist/./escaped",
        "package/dist//escaped",
        "package\\dist\\escaped",
        "/package/dist/escaped",
    ],
)
def test_npm_verifier_rejects_noncanonical_member_paths(tmp_path: Path, member_name: str) -> None:
    tarball = tmp_path / "noncanonical.tgz"
    _write_tarball(tarball, [*_valid_members(), _regular_file(member_name)])

    result = _run_verifier(tarball)

    assert result.returncode == 1
    assert result.stdout == f"FAIL: tarball contains non-canonical path: {member_name!r}\n"
    assert result.stderr == ""


def test_npm_verifier_rejects_duplicate_member_names(tmp_path: Path) -> None:
    tarball = tmp_path / "duplicate.tgz"
    duplicate = "package/dist/index.js"
    _write_tarball(tarball, [*_valid_members(), _regular_file(duplicate, b"duplicate")])

    result = _run_verifier(tarball)

    assert result.returncode == 1
    assert result.stdout == f"FAIL: tarball contains duplicate path: {duplicate!r}\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("member_type", "linkname"),
    [
        pytest.param(tarfile.SYMTYPE, "package/dist/index.d.ts", id="symlink"),
        pytest.param(tarfile.LNKTYPE, "package/dist/index.d.ts", id="hard-link"),
        pytest.param(tarfile.DIRTYPE, "", id="directory"),
        pytest.param(tarfile.CHRTYPE, "", id="device"),
        pytest.param(tarfile.FIFOTYPE, "", id="other-non-regular"),
    ],
)
def test_npm_verifier_rejects_nonregular_required_member(
    tmp_path: Path,
    member_type: bytes,
    linkname: str,
) -> None:
    tarball = tmp_path / "nonregular.tgz"
    required = "package/dist/index.js"
    member = tarfile.TarInfo(required)
    member.type = member_type
    member.linkname = linkname
    _write_tarball(tarball, [*_valid_members(without=required), (member, None)])

    result = _run_verifier(tarball)

    assert result.returncode == 1
    assert result.stdout == f"FAIL: tarball contains non-regular member: {required!r}\n"
    assert result.stderr == ""


def test_npm_verifier_accepts_valid_regular_files(tmp_path: Path) -> None:
    tarball = tmp_path / "valid.tgz"
    _write_tarball(tarball, _valid_members())

    result = _run_verifier(tarball)

    assert result.returncode == 0
    assert result.stdout == "npm tarball ok\n"
    assert result.stderr == ""


def _failing_command(fake_bin: Path, name: str, exit_code: int) -> None:
    command = fake_bin / name
    command.write_text(f"#!/bin/sh\nexit {exit_code}\n")
    command.chmod(0o755)


def _smoke_environment(tmp_path: Path, command: str, exit_code: int) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    scratch_parent = tmp_path / "scratch"
    fake_bin.mkdir()
    scratch_parent.mkdir()
    _failing_command(fake_bin, command, exit_code)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["TMPDIR"] = str(scratch_parent)
    return env, scratch_parent


def test_npm_smoke_removes_scratch_directory_after_failure(tmp_path: Path) -> None:
    env, scratch_parent = _smoke_environment(tmp_path, "npm", 23)
    tarball = tmp_path / "package.tgz"
    tarball.touch()

    result = subprocess.run(
        [str(NPM_SMOKE), str(tarball)],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 23
    assert list(scratch_parent.iterdir()) == []


def test_python_smoke_removes_scratch_directory_after_failure(tmp_path: Path) -> None:
    env, scratch_parent = _smoke_environment(tmp_path, "uv", 24)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "nodes_core-0.1.0-py3-none-any.whl").touch()
    (dist / "nodes_core-0.1.0.tar.gz").touch()

    result = subprocess.run(
        [str(PYTHON_SMOKE), str(dist)],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 24
    assert list(scratch_parent.iterdir()) == []
