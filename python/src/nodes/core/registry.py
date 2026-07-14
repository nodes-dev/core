from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from nodes.core.errors import FacetError, InvariantError, UnknownKindError, ValidationError
from nodes.core.node import Node

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


class Violation(BaseModel):
    """One structured validation finding from `Registry.check` (never raised)."""

    code: str
    detail: str
    message: str


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

    def _compose(self, spec: KindSpec) -> tuple[set[str], set[str], list[Invariant]]:
        required = set(spec.required_facets)
        optional = set(spec.optional_facets)
        invariants: list[Invariant] = []
        if spec.shape is not None:
            shape = self._shapes[spec.shape]
            required |= shape.required_facets
            optional |= shape.optional_facets
            invariants.extend(shape.invariants)
        invariants.extend(spec.invariants)
        return required, optional, invariants

    def validate(self, node: Node) -> None:
        required, optional, invariants = self._compose(self.get(node.kind))
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

    def check(self, node: Node) -> list[Violation]:
        """Collect ALL violations of `node` with machine-stable codes; never raises on
        content. Non-kernel exceptions from invariants are programmer bugs and propagate."""
        spec = self._specs.get(node.kind)
        if spec is None:
            return [
                Violation(
                    code="unknown-kind",
                    detail=node.kind,
                    message=f"{node.id}: kind {node.kind!r} is not registered",
                )
            ]
        required, optional, invariants = self._compose(spec)
        present = set(node.facets)
        violations: list[Violation] = []
        for name in sorted(required - present):
            violations.append(
                Violation(code="facet-missing", detail=name, message=f"{node.id}: missing required facet {name!r}")
            )
        for name in sorted(present - (required | optional)):
            violations.append(
                Violation(code="facet-unexpected", detail=name, message=f"{node.id}: unexpected facet {name!r}")
            )
        if violations:
            return violations  # invariants presuppose their facets; running them would duplicate reports
        for invariant in invariants:
            try:
                invariant(node)
            except FacetError as exc:
                violations.append(Violation(code="facet-invalid", detail="", message=str(exc)))
            except InvariantError as exc:
                violations.append(Violation(code="invariant-violated", detail="", message=str(exc)))
        return violations
