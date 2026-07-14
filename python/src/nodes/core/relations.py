from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nodes.core.errors import RefError

RELATES_TO = "relatesTo"


class Relation(BaseModel):
    """The single edge primitive (normalized form: source always explicit)."""

    source: str
    predicate: str
    target: str
    directed: bool = True
    weight: float | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_serialized(cls, data: dict, container_id: str) -> "Relation":
        return cls(
            source=data.get("source", container_id),
            predicate=data["predicate"],
            target=data["target"],
            directed=data.get("directed", True),
            weight=data.get("weight"),
            attrs=data.get("attrs", {}),
        )

    def to_serialized(self, container_id: str) -> dict:
        out: dict[str, Any] = {}
        if self.source != container_id:
            out["source"] = self.source
        out["predicate"] = self.predicate
        out["target"] = self.target
        if self.directed is not True:
            out["directed"] = self.directed
        if self.weight is not None:
            out["weight"] = self.weight
        if self.attrs:
            out["attrs"] = self.attrs
        return out


def relates_to(source: str, target: str) -> Relation:
    return Relation(source=source, predicate=RELATES_TO, target=target)


def tag_to_relation(source: str, tag: str, alias_map: dict[str, str]) -> Relation:
    name = tag.lstrip("#")
    target = alias_map.get(name) or alias_map.get(name.lower())
    if target is None:
        raise RefError(f"tag {tag!r} does not resolve to a known node")
    return relates_to(source, target)
