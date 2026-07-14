from __future__ import annotations

import re

from pydantic import BaseModel

from nodes.core.errors import IdError

Ref = str

KIND_RE = re.compile(r"^[a-z][a-z0-9-]*$")
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_.-]*$")


class NodeId(BaseModel):
    """Canonical typed identifier: `kind:slug`."""

    kind: str
    slug: str

    @staticmethod
    def is_valid_kind(kind: str) -> bool:
        return bool(KIND_RE.match(kind))

    @staticmethod
    def is_valid_slug(slug: str) -> bool:
        return bool(SLUG_RE.match(slug))

    @classmethod
    def parse(cls, raw: str) -> "NodeId":
        if ":" not in raw:
            raise IdError(f"id must be 'kind:slug', got {raw!r}")
        kind, slug = raw.split(":", 1)
        if not cls.is_valid_kind(kind):
            raise IdError(f"invalid kind {kind!r} in id {raw!r}")
        if not cls.is_valid_slug(slug):
            raise IdError(f"invalid slug {slug!r} in id {raw!r}")
        return cls(kind=kind, slug=slug)

    def __str__(self) -> str:
        return f"{self.kind}:{self.slug}"
