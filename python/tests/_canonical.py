from __future__ import annotations

from nodes.kernel.node import Node


def to_canonical(node: Node) -> dict:
    """Language-neutral canonical JSON of a node (docs/STANDARD.md §11.1).

    Relations are normalized (source explicit) in document order. Dates render
    as YYYY-MM-DD strings or None. Uses on-disk field name `deprecated_ids`.
    """
    return {
        "id": node.id,
        "uid": node.uid,
        "kind": node.kind,
        "title": node.title,
        "body": node.body,
        "metadata": {
            "created": node.metadata.created.isoformat() if node.metadata.created else None,
            "updated": node.metadata.updated.isoformat() if node.metadata.updated else None,
            "version": node.metadata.version,
        },
        "relations": [
            {
                "source": r.source,
                "predicate": r.predicate,
                "target": r.target,
                "directed": r.directed,
                "weight": r.weight,
                "attrs": r.attrs,
            }
            for r in node.relations
        ],
        "facets": node.facets,
        "deprecated_ids": node.deprecated_ids,
    }
