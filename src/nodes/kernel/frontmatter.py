from __future__ import annotations

from typing import Any

import yaml

from nodes.kernel.node import Node, NodeMetadata
from nodes.kernel.relations import RELATES_TO, Relation, relates_to


def split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---\r\n"):
        nl = "\r\n"
    elif text.startswith("---\n"):
        nl = "\n"
    else:
        return {}, text
    rest = text[len("---") + len(nl):]
    sep = f"{nl}---{nl}"
    idx = rest.find(sep)
    if idx == -1:
        return {}, text
    fm = yaml.safe_load(rest[:idx]) or {}
    body = rest[idx + len(sep):]
    return fm, body


def node_from_markdown(text: str) -> Node:
    fm, body = split_frontmatter(text)
    node_id = fm["id"]
    relations: list[Relation] = []
    for ref in fm.get("related", []) or []:
        relations.append(relates_to(node_id, ref))
    for raw in fm.get("relations", []) or []:
        relations.append(Relation.from_serialized(raw, container_id=node_id))
    meta = NodeMetadata.model_validate({k: fm[k] for k in ("created", "updated", "version") if k in fm})
    return Node(
        id=node_id,
        uid=fm["uid"],
        kind=fm["kind"],
        title=fm["title"],
        body=body,
        metadata=meta,
        relations=relations,
        facets=fm.get("facets", {}) or {},
        deprecated_ids=fm.get("deprecated_ids", []) or [],
    )


def _is_plain_relatesto(rel: Relation, node_id: str) -> bool:
    return (
        rel.predicate == RELATES_TO
        and rel.source == node_id
        and rel.directed is True
        and rel.weight is None
        and not rel.attrs
    )


def node_to_markdown(node: Node) -> str:
    fm: dict[str, Any] = {"id": node.id, "uid": node.uid, "kind": node.kind, "title": node.title}
    if node.metadata.created is not None:
        fm["created"] = node.metadata.created
    if node.metadata.updated is not None:
        fm["updated"] = node.metadata.updated
    if node.metadata.version != 1:
        fm["version"] = node.metadata.version
    related = [r.target for r in node.relations if _is_plain_relatesto(r, node.id)]
    typed = [r.to_serialized(node.id) for r in node.relations if not _is_plain_relatesto(r, node.id)]
    if related:
        fm["related"] = related
    if typed:
        fm["relations"] = typed
    if node.facets:
        fm["facets"] = node.facets
    if node.deprecated_ids:
        fm["deprecated_ids"] = node.deprecated_ids
    yaml_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{yaml_text}\n---\n{node.body}"
