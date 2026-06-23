from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

from nodes.kernel.snapshot import (
    SNAPSHOT_LANG,
    SNAPSHOT_SCHEMA_VERSION,
    CorpusFile,
    ManifestEntry,
    hash_bytes,
    iter_corpus_files,
    read_json,
    snapshot_path,
    write_json_atomic,
)


def test_constants():
    assert SNAPSHOT_SCHEMA_VERSION == 1
    assert SNAPSHOT_LANG == "py"


def test_snapshot_path(tmp_path):
    assert snapshot_path(tmp_path) == tmp_path / ".nodes-index" / "snapshot.py.json"


def test_hash_bytes_is_sha256_hex():
    assert hash_bytes(b"hello") == hashlib.sha256(b"hello").hexdigest()
    assert len(hash_bytes(b"")) == 64


def test_iter_corpus_files_sorted_relative_posix_with_hash(tmp_path):
    (tmp_path / "topic").mkdir()
    (tmp_path / "gene").mkdir()
    (tmp_path / "topic" / "b.md").write_bytes(b"BBB")
    (tmp_path / "gene" / "a.md").write_bytes(b"AAA")
    (tmp_path / "ignore.txt").write_bytes(b"nope")
    files = iter_corpus_files(tmp_path)
    assert [f.path for f in files] == ["gene/a.md", "topic/b.md"]
    assert files[0] == CorpusFile(path="gene/a.md", data=b"AAA", sha256=hash_bytes(b"AAA"))


def test_iter_corpus_files_ignores_md_directories(tmp_path):
    (tmp_path / "notes.md").mkdir()
    (tmp_path / "real.md").write_bytes(b"real")
    files = iter_corpus_files(tmp_path)
    assert files == [CorpusFile(path="real.md", data=b"real", sha256=hash_bytes(b"real"))]


def test_iter_corpus_files_ignores_md_symlinks(tmp_path):
    target = tmp_path / "target.txt"
    target.write_bytes(b"target")
    link = tmp_path / "linked.md"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unsupported: {exc}")

    assert iter_corpus_files(tmp_path) == []


def test_write_json_atomic_round_trip_and_no_tmp_left(tmp_path):
    p = snapshot_path(tmp_path)
    write_json_atomic(p, {"version": 1, "x": [1, 2]})
    assert read_json(p) == {"version": 1, "x": [1, 2]}
    assert not (p.parent / (p.name + ".tmp")).exists()


def test_write_json_atomic_rejects_non_finite_values_without_snapshot(tmp_path):
    p = snapshot_path(tmp_path)
    with pytest.raises(ValueError):
        write_json_atomic(p, {"x": float("nan")})
    assert not p.exists()
    assert not (p.parent / (p.name + ".tmp")).exists()


def test_read_json_missing_returns_none(tmp_path):
    assert read_json(snapshot_path(tmp_path)) is None


def test_read_json_directory_raises(tmp_path):
    p = snapshot_path(tmp_path)
    p.mkdir(parents=True)
    with pytest.raises(OSError):
        read_json(p)


def test_read_json_invalid_json_raises(tmp_path):
    p = snapshot_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_json(p)


def test_corpus_file_is_frozen():
    e = CorpusFile(path="a.md", data=b"A", sha256=hash_bytes(b"A"))
    assert (e.path, e.data, e.sha256) == ("a.md", b"A", hash_bytes(b"A"))
    with pytest.raises(FrozenInstanceError):
        setattr(e, "path", "b.md")


def test_manifest_entry_is_frozen():
    e = ManifestEntry(path="a.md", sha256="0" * 64, uid="u1")
    assert (e.path, e.sha256, e.uid) == ("a.md", "0" * 64, "u1")
    with pytest.raises(FrozenInstanceError):
        setattr(e, "path", "b.md")
