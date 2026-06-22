from __future__ import annotations

import hashlib
import math
import re
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
