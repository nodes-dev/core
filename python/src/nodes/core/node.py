from __future__ import annotations

from datetime import date
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from nodes.core.errors import IdError, ValidationError
from nodes.core.ids import NodeId
from nodes.core.relations import Relation


def new_uid() -> str:
    return uuid4().hex


class NodeMetadata(BaseModel):
    created: date | None = None
    updated: date | None = None
    version: int = 1


class Node(BaseModel):
    id: str
    uid: str = Field(default_factory=new_uid)
    kind: str
    title: str
    body: str = ""
    metadata: NodeMetadata = Field(default_factory=NodeMetadata)
    relations: list[Relation] = Field(default_factory=list)
    facets: dict[str, dict] = Field(default_factory=dict)
    deprecated_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_id_kind(self) -> Node:
        try:
            parsed = NodeId.parse(self.id)
        except IdError as exc:
            raise ValidationError(str(exc)) from exc
        if parsed.kind != self.kind:
            raise ValidationError(f"id kind {parsed.kind!r} != kind field {self.kind!r}")
        return self
