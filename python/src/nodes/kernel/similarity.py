from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Protocol

from nodes.kernel.node import Node

Vector = tuple[float, ...]

_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class Embedder(Protocol):
    """The seam: turns text into vectors. The kernel ships no concrete embedder."""

    @property
    def cache_namespace(self) -> str: ...

    def embed(self, texts: list[str]) -> list[Vector]: ...


def embed_text(node: Node) -> str:
    """The frozen per-node embedding input: title and body joined by one blank line."""
    return f"{node.title}\n\n{node.body}"


def text_hash(text: str) -> str:
    """Content-address key for the vector cache."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_namespace(namespace: str) -> None:
    """A cache_namespace must be a safe single path segment."""
    if not namespace or namespace in (".", "..") or _NAMESPACE_RE.match(namespace) is None:
        raise ValueError(f"invalid cache_namespace {namespace!r}")


_TEXT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_text_hash(text_hash: str) -> None:
    """A cache key must be exactly 64 lowercase hex chars (a SHA-256 hexdigest)."""
    if _TEXT_HASH_RE.match(text_hash) is None:
        raise ValueError(f"invalid text_hash {text_hash!r}")


def _validate_finite(vec: tuple[object, ...]) -> None:
    if len(vec) < 1:
        raise ValueError("vector must have length >= 1")
    for x in vec:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            raise ValueError(f"vector contains non-finite or non-numeric value {x!r}")


def _normalize(vec: Vector) -> Vector:
    """Return the L2-normalized vector; reject zero-norm and invalid numeric input."""
    _validate_finite(vec)
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        raise ValueError("cannot normalize a zero-norm vector")
    return tuple(x / norm for x in vec)


class VectorCache:
    """Content-addressed on-disk cache of RAW embedder output, namespaced per embedder.

    Disposable: deleting the directory just forces re-embedding. All ranking math
    lives in VectorIndex; this is purely a model-output cache.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, namespace: str, text_hash: str) -> Path:
        validate_namespace(namespace)
        validate_text_hash(text_hash)
        return self.root / ".nodes-index" / "vectors" / namespace / f"{text_hash}.json"

    def get(self, namespace: str, text_hash: str) -> Vector | None:
        path = self._path(namespace, text_hash)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"corrupt cache file {path}: {exc}") from exc
        if not isinstance(data, dict) or "dim" not in data or "vector" not in data:
            raise ValueError(f"corrupt cache file {path}: missing dim/vector")
        raw = data["vector"]
        if not isinstance(raw, list) or len(raw) != data["dim"]:
            raise ValueError(f"corrupt cache file {path}: dim/vector length mismatch")
        raw_tuple = tuple(raw)
        _validate_finite(raw_tuple)
        return tuple(float(x) for x in raw_tuple)

    def put(self, namespace: str, text_hash: str, vector: Vector) -> None:
        _validate_finite(vector)
        path = self._path(namespace, text_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"dim": len(vector), "vector": list(vector)}, allow_nan=False)
        tmp = path.parent / f"{text_hash}.json.tmp"
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
