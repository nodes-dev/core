from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nodes.kernel.errors import CollisionError
from nodes.kernel.node import Node
from nodes.kernel.ranking import score_key

Vector = tuple[float, ...]

_NAMESPACE_RE = re.compile(r"[A-Za-z0-9._-]+")


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
    if not namespace or namespace in (".", "..") or _NAMESPACE_RE.fullmatch(namespace) is None:
        raise ValueError(f"invalid cache_namespace {namespace!r}")


_TEXT_HASH_RE = re.compile(r"[0-9a-f]{64}")


def validate_text_hash(text_hash: str) -> None:
    """A cache key must be exactly 64 lowercase hex chars (a SHA-256 hexdigest)."""
    if _TEXT_HASH_RE.fullmatch(text_hash) is None:
        raise ValueError(f"invalid text_hash {text_hash!r}")


def _validate_finite(vec: tuple[object, ...]) -> None:
    if len(vec) < 1:
        raise ValueError("vector must have length >= 1")
    for x in vec:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise ValueError(f"vector contains non-finite or non-numeric value {x!r}")
        try:
            finite = math.isfinite(x)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError(f"vector contains non-finite or non-numeric value {x!r}")


def _normalize(vec: Vector) -> Vector:
    """Return the L2-normalized vector; reject zero-norm and invalid numeric input."""
    _validate_finite(vec)
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        raise ValueError("cannot normalize a zero-norm vector")
    return tuple(x / norm for x in vec)


@dataclass
class SimilarHit:
    id: str
    uid: str
    score: float


def _validate_k(k: int | None) -> None:
    if k is not None and (isinstance(k, bool) or not isinstance(k, int) or k <= 0):
        raise ValueError(f"k must be a positive int or None, got {k!r}")


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


@dataclass(frozen=True)
class _PreparedVector:
    text_hash: str
    namespace: str
    vector: Vector | None  # None => content unchanged (id-only refresh)


class VectorIndex:
    """In-memory uid -> L2-normalized vector store with exact cosine ranking.

    Bound to exactly one embedder namespace and one dimension (cosine across
    vectors from different models or dimensions is meaningless).
    """

    def __init__(self) -> None:
        self.vectors: dict[str, Vector] = {}
        self.id_by_uid: dict[str, str] = {}
        self.hash_by_uid: dict[str, str] = {}
        self.dim: int | None = None
        self.namespace: str | None = None

    @classmethod
    def build(cls, nodes: Iterable[Node], embedder: Embedder, cache: VectorCache) -> "VectorIndex":
        idx = cls()
        validate_namespace(embedder.cache_namespace)
        idx.namespace = embedder.cache_namespace  # bind even for an empty corpus
        for node in nodes:
            if node.uid in idx.hash_by_uid:
                raise CollisionError(f"duplicate uid {node.uid!r} in corpus")
            idx.upsert(node, embedder, cache)
        return idx

    def prepare(self, node: Node, embedder: Embedder, cache: VectorCache) -> _PreparedVector:
        """Resolve + validate the vector WITHOUT mutating index state (cache writes ok)."""
        namespace = embedder.cache_namespace
        validate_namespace(namespace)
        if self.namespace is not None and namespace != self.namespace:
            raise ValueError(f"embedder namespace {namespace!r} != index namespace {self.namespace!r}")
        text = embed_text(node)
        h = text_hash(text)
        if self.hash_by_uid.get(node.uid) == h:
            return _PreparedVector(text_hash=h, namespace=namespace, vector=None)
        cached = cache.get(namespace, h)
        if cached is None:
            embedded = embedder.embed([text])
            if len(embedded) != 1:
                raise ValueError(f"embedder returned {len(embedded)} vectors for 1 input")
            raw_values = tuple(embedded[0])
            _validate_finite(raw_values)
            raw: Vector = tuple(float(x) for x in raw_values)
            cache.put(namespace, h, raw)
        else:
            raw = cached
        if self.dim is not None and len(raw) != self.dim:
            raise ValueError(f"vector dim {len(raw)} != index dim {self.dim}")
        return _PreparedVector(text_hash=h, namespace=namespace, vector=_normalize(raw))

    def commit(self, node: Node, prepared: _PreparedVector) -> None:
        """Apply a prepared vector. Infallible: never raises on valid prepared input."""
        if self.namespace is None:
            self.namespace = prepared.namespace
        if prepared.vector is None:
            self.id_by_uid[node.uid] = node.id  # rename / id-only refresh
            return
        if self.dim is None:
            self.dim = len(prepared.vector)
        self.vectors[node.uid] = prepared.vector
        self.id_by_uid[node.uid] = node.id
        self.hash_by_uid[node.uid] = prepared.text_hash

    def upsert(self, node: Node, embedder: Embedder, cache: VectorCache) -> None:
        self.commit(node, self.prepare(node, embedder, cache))

    def remove(self, uid: str) -> None:
        self.vectors.pop(uid, None)
        self.id_by_uid.pop(uid, None)
        self.hash_by_uid.pop(uid, None)

    def query_vector(self, vec: Vector, k: int | None = None) -> list[SimilarHit]:
        _validate_k(k)
        return self._rank(self._prepare_query(vec), k, exclude_uid=None)

    def similar(self, uid: str, k: int | None = None) -> list[SimilarHit]:
        _validate_k(k)
        if uid not in self.vectors:
            raise KeyError(uid)
        return self._rank(self.vectors[uid], k, exclude_uid=uid)

    def similar_text(self, text: str, embedder: Embedder, k: int | None = None) -> list[SimilarHit]:
        _validate_k(k)
        if self.namespace is not None and embedder.cache_namespace != self.namespace:
            raise ValueError(
                f"embedder namespace {embedder.cache_namespace!r} != index namespace {self.namespace!r}"
            )
        embedded = embedder.embed([text])
        if len(embedded) != 1:
            raise ValueError(f"embedder returned {len(embedded)} vectors for 1 input")
        return self.query_vector(tuple(embedded[0]), k)

    def _prepare_query(self, vec: Vector) -> Vector:
        raw_values = tuple(vec)
        _validate_finite(raw_values)
        if self.dim is not None and len(raw_values) != self.dim:
            raise ValueError(f"query dim {len(raw_values)} != index dim {self.dim}")
        return _normalize(tuple(float(x) for x in raw_values))

    def _rank(self, query_vec: Vector, k: int | None, *, exclude_uid: str | None) -> list[SimilarHit]:
        hits = [
            SimilarHit(
                id=self.id_by_uid[uid],
                uid=uid,
                score=sum(a * b for a, b in zip(query_vec, vec)),
            )
            for uid, vec in self.vectors.items()
            if uid != exclude_uid
        ]
        hits.sort(key=lambda h: (-score_key(h.score), h.id))
        return hits if k is None else hits[:k]
