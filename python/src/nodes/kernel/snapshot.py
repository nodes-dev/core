from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_LANG = "py"


def snapshot_path(root: Path | str) -> Path:
    return Path(root) / ".nodes-index" / "snapshot.py.json"


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class CorpusFile:
    path: str  # root-relative POSIX
    data: bytes
    sha256: str


def iter_corpus_files(root: Path | str) -> list[CorpusFile]:
    root = Path(root)
    files: list[CorpusFile] = []
    for p in sorted(root.rglob("*.md")):
        if p.is_symlink() or not p.is_file():
            continue
        data = p.read_bytes()
        files.append(CorpusFile(path=p.relative_to(root).as_posix(), data=data, sha256=hash_bytes(data)))
    return files


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    sha256: str
    uid: str


def write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, allow_nan=False)
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
