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


def test_local_files_requires_both_postcheck_attestations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dist = tmp_path / "dist"
    _write_distributions(dist)
    (dist / f"{WHEEL}.publish.attestation").write_text("wheel attestation")

    with pytest.raises(SystemExit, match="1"):
        CHECK.local_files(str(dist), require_attestations=True)

    assert capsys.readouterr().out == (
        f"FAIL: missing distribution attestations: "
        f"['{SDIST}.publish.attestation']\n"
    )


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

    assert capsys.readouterr().out == (
        f"FAIL: unexpected files in distribution directory: ['{extra_name}']\n"
    )
