from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from nodes.core.ids import NodeId
from nodes.core.structural_index import Index
from nodes.core.search import SearchIndex
from nodes.core.similarity import VectorIndex

SNAPSHOT_SCHEMA_VERSION = 2
SNAPSHOT_LANG = "py"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SNAPSHOT_KEYS = frozenset({"version", "lang", "manifest", "structural", "search", "vectors"})
_MANIFEST_ROW_KEYS = frozenset({"path", "sha256", "uid"})


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
        rel = p.relative_to(root)
        if rel.parts[0] == ".nodes-index" or p.is_symlink() or not p.is_file():
            continue
        data = p.read_bytes()
        files.append(CorpusFile(path=rel.as_posix(), data=data, sha256=hash_bytes(data)))
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


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant)
    except FileNotFoundError:
        if path.is_symlink():
            raise
        return None


@dataclass
class Snapshot:
    manifest: list[ManifestEntry]
    index: Index
    search_index: SearchIndex
    vector_index: VectorIndex | None


def write_snapshot(
    root: Path | str,
    manifest: list[ManifestEntry],
    index: Index,
    search_index: SearchIndex,
    vector_index: VectorIndex | None,
) -> None:
    doc = {
        "version": SNAPSHOT_SCHEMA_VERSION,
        "lang": SNAPSHOT_LANG,
        "manifest": [{"path": m.path, "sha256": m.sha256, "uid": m.uid} for m in manifest],
        "structural": index.to_dict(),
        "search": search_index.to_dict(),
        "vectors": vector_index.to_dict() if vector_index is not None else None,
    }
    write_json_atomic(snapshot_path(root), doc)


def _parse_manifest(raw: object) -> list[ManifestEntry]:
    if not isinstance(raw, list):
        raise ValueError("snapshot manifest is not a list")
    entries = []
    for e in raw:
        if not isinstance(e, dict):
            raise ValueError("snapshot manifest row is not a dict")
        missing = _MANIFEST_ROW_KEYS - e.keys()
        if missing:
            raise ValueError(f"snapshot manifest row missing {sorted(missing)[0]}")
        path = e["path"]
        sha256 = e["sha256"]
        uid = e["uid"]
        if not isinstance(path, str):
            raise ValueError("snapshot manifest row path must be a string")
        _validate_manifest_path(path)
        if not isinstance(sha256, str):
            raise ValueError("snapshot manifest row sha256 must be a string")
        if _SHA256_RE.fullmatch(sha256) is None:
            raise ValueError("snapshot manifest row sha256 must be 64 lowercase hex chars")
        if not isinstance(uid, str):
            raise ValueError("snapshot manifest row uid must be a string")
        entries.append(ManifestEntry(path=path, sha256=sha256, uid=uid))
    uids = [e.uid for e in entries]
    paths = [e.path for e in entries]
    if len(set(uids)) != len(uids):
        raise ValueError("snapshot manifest: duplicate uid")
    if len(set(paths)) != len(paths):
        raise ValueError("snapshot manifest: duplicate path")
    return entries


def _validate_manifest_path(path: str) -> None:
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or path.endswith("/")
        or not path.endswith(".md")
        or path.split("/", 1)[0] == ".nodes-index"
        or any(part in ("", ".", "..") for part in path.split("/"))
    ):
        raise ValueError("snapshot manifest row path must be a root-relative POSIX .md path")


def _path_for_node_id(node_id: str) -> str:
    parsed = NodeId.parse(node_id)
    return f"{parsed.kind}/{parsed.slug.replace(':', '__')}.md"


def load_snapshot(root: Path | str, embedder_namespace: str | None) -> Snapshot | None:
    try:
        doc = read_json(snapshot_path(root))
        if doc is None:
            return None
        if not isinstance(doc, dict):
            return None
        missing = _SNAPSHOT_KEYS - doc.keys()
        if missing:
            raise ValueError(f"snapshot document missing {sorted(missing)[0]}")
        if doc.get("version") != SNAPSHOT_SCHEMA_VERSION or doc.get("lang") != SNAPSHOT_LANG:
            return None

        manifest = _parse_manifest(doc["manifest"])
        manifest_uids = {m.uid for m in manifest}

        index = Index.from_dict(doc["structural"])
        if set(index.by_uid) != manifest_uids:
            return None
        expected_ids = {uid: entry.id for uid, entry in index.by_uid.items()}
        for m in manifest:
            if m.path != _path_for_node_id(expected_ids[m.uid]):
                raise ValueError("snapshot manifest path does not match structural id")

        search_index = SearchIndex.from_dict(doc["search"])
        if set(search_index.lengths) != manifest_uids:
            return None
        if search_index.id_by_uid != expected_ids:
            return None

        vector_index: VectorIndex | None = None
        if embedder_namespace is not None:
            vec = doc.get("vectors")
            if not isinstance(vec, dict):
                return None
            if vec.get("namespace") != embedder_namespace:
                return None
            vector_index = VectorIndex.from_dict(vec)
            if set(vector_index.vectors) != manifest_uids:
                return None
            if vector_index.id_by_uid != expected_ids:
                return None

        return Snapshot(
            manifest=manifest,
            index=index,
            search_index=search_index,
            vector_index=vector_index,
        )
    except (OSError, ValueError):
        return None
