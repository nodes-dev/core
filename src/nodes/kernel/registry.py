from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from nodes.kernel.errors import FacetError, UnknownKindError
from nodes.kernel.node import Node

Invariant = Callable[[Node], None]


class KindSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    required_facets: set[str] = Field(default_factory=set)
    optional_facets: set[str] = Field(default_factory=set)
    invariants: list[Invariant] = Field(default_factory=list)


class Registry:
    def __init__(self) -> None:
        self._specs: dict[str, KindSpec] = {}

    def register(self, spec: KindSpec) -> None:
        self._specs[spec.name] = spec

    def is_registered(self, kind: str) -> bool:
        return kind in self._specs

    def get(self, kind: str) -> KindSpec:
        try:
            return self._specs[kind]
        except KeyError as exc:
            raise UnknownKindError(f"kind {kind!r} is not registered") from exc

    def validate(self, node: Node) -> None:
        spec = self.get(node.kind)
        present = set(node.facets)
        missing = spec.required_facets - present
        if missing:
            raise FacetError(f"{node.id}: missing required facets {sorted(missing)}")
        allowed = spec.required_facets | spec.optional_facets
        unexpected = present - allowed
        if unexpected:
            raise FacetError(f"{node.id}: unexpected facets {sorted(unexpected)}")
        for invariant in spec.invariants:
            invariant(node)
