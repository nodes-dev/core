from __future__ import annotations

import hashlib
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


def test_write_json_atomic_round_trip_and_no_tmp_left(tmp_path):
    p = snapshot_path(tmp_path)
    write_json_atomic(p, {"version": 1, "x": [1, 2]})
    assert read_json(p) == {"version": 1, "x": [1, 2]}
    assert not (p.parent / (p.name + ".tmp")).exists()


def test_read_json_missing_returns_none(tmp_path):
    assert read_json(snapshot_path(tmp_path)) is None


def test_manifest_entry_is_frozen():
    e = ManifestEntry(path="a.md", sha256="0" * 64, uid="u1")
    assert (e.path, e.sha256, e.uid) == ("a.md", "0" * 64, "u1")
    with pytest.raises(FrozenInstanceError):
        setattr(e, "path", "b.md")
