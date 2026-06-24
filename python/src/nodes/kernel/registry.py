from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from nodes.kernel.errors import FacetError, UnknownKindError, ValidationError
from nodes.kernel.node import Node

Invariant = Callable[[Node], None]


class ShapeSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    required_facets: set[str] = Field(default_factory=set)
    optional_facets: set[str] = Field(default_factory=set)
    invariants: list[Invariant] = Field(default_factory=list)


class KindSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    shape: str | None = None
    required_facets: set[str] = Field(default_factory=set)
    optional_facets: set[str] = Field(default_factory=set)
    invariants: list[Invariant] = Field(default_factory=list)


class Registry:
    def __init__(self) -> None:
        self._specs: dict[str, KindSpec] = {}
        self._shapes: dict[str, ShapeSpec] = {}

    def register_shape(self, spec: ShapeSpec) -> None:
        if spec.name in self._shapes:
            raise ValidationError(f"shape {spec.name!r} is already registered")
        self._shapes[spec.name] = spec

    def is_shape(self, name: str) -> bool:
        return name in self._shapes

    def register(self, spec: KindSpec) -> None:
        if spec.name in self._specs:
            raise ValidationError(f"kind {spec.name!r} is already registered")
        if spec.shape is not None and spec.shape not in self._shapes:
            raise UnknownKindError(f"kind {spec.name!r} adopts unknown shape {spec.shape!r}")
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
        required = set(spec.required_facets)
        optional = set(spec.optional_facets)
        invariants: list[Invariant] = []
        if spec.shape is not None:
            shape = self._shapes[spec.shape]
            required |= shape.required_facets
            optional |= shape.optional_facets
            invariants.extend(shape.invariants)
        invariants.extend(spec.invariants)

        present = set(node.facets)
        missing = required - present
        if missing:
            raise FacetError(f"{node.id}: missing required facets {sorted(missing)}")
        allowed = required | optional
        unexpected = present - allowed
        if unexpected:
            raise FacetError(f"{node.id}: unexpected facets {sorted(unexpected)}")
        for invariant in invariants:
            invariant(node)
