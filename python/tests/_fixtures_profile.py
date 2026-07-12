"""Test-support profile for the shared conformance fixtures (design §3.2).

Registers the kinds the fixture corpora use; not shipped API. `zzz` stays
unregistered on purpose — the check oracle pins `unknown-kind` for it.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from nodes.kernel.errors import FacetError, InvariantError
from nodes.kernel.node import Node
from nodes.kernel.registry import KindSpec, Registry

SOURCE = "source"
NOTE = "note"
TOPIC = "topic"
PAPER = "paper"


class Source(BaseModel):
    """Bibliographic facet the fixture `paper` nodes carry."""

    model_config = ConfigDict(extra="forbid")  # unknown keys (typos) fail, never silently dropped

    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    container: str | None = None
    identifier: str | None = None
    url: str | None = None


def source_of(node: Node) -> Source:
    raw = node.facets.get(SOURCE)
    if raw is None:
        raise FacetError(f"{node.id}: missing '{SOURCE}' facet")
    try:
        return Source.model_validate(raw)
    except PydanticValidationError as exc:  # malformed payload / unknown key / wrong type
        raise FacetError(f"{node.id}: invalid '{SOURCE}' facet: {exc}") from exc


def require_identifiable_source(node: Node) -> None:
    s = source_of(node)
    if not (s.authors or s.year or s.identifier or s.url):
        raise InvariantError(
            f"{node.id}: source facet needs at least one of authors/year/identifier/url"
        )


def register_fixtures_profile(reg: Registry) -> None:
    reg.register(KindSpec(name=NOTE))
    reg.register(KindSpec(name=TOPIC))
    reg.register(
        KindSpec(
            name=PAPER,
            required_facets={SOURCE},
            invariants=[require_identifiable_source],
        )
    )
