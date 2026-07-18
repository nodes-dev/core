from __future__ import annotations

import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile

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
