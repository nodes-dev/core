from __future__ import annotations

import json

from nodes.kernel.corpus import Corpus
from nodes.kernel.index import Index
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to


def _relation_signature(out_ref) -> tuple | None:
    rel = out_ref.relation
    if rel is None:
        return None
    return (
        rel.source,
        rel.predicate,
        rel.target,
        rel.directed,
        rel.weight,
        json.dumps(rel.attrs, sort_keys=True, default=repr),
    )


def _out_ref_signature(out_ref) -> tuple:
    return (out_ref.ref, out_ref.role, _relation_signature(out_ref))


def _normalize(index: Index) -> dict:
    return {
        "by_uid": {
            uid: (
                e.id,
                e.kind,
                tuple(sorted(e.deprecated_ids)),
                tuple(sorted(_out_ref_signature(o) for o in e.out_refs)),
            )
            for uid, e in index.by_uid.items()
        },
        "id_to_uid": dict(index.id_to_uid),
        "deprecated_to_uid": dict(index.deprecated_to_uid),
        "in_refs": {
            ref: sorted((r.source_uid, *_out_ref_signature(r.out_ref)) for r in rows)
            for ref, rows in index.in_refs.items()
        },
    }


def _assert_equivalent(corpus: Corpus) -> None:
    fresh = Index.build(corpus.store.all_nodes())
    assert _normalize(corpus.index) == _normalize(fresh)


def test_rebuild_equivalence_through_mutation_sequence(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")]))
    c.add(Node(id="topic:b", kind="topic", title="B"))
    c.add(Node(id="graph:g", kind="graph", title="G", facets={"membership": {
        "shape": "graph",
        "members": ["topic:a", "topic:b"],
        "edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}],
    }}))
    _assert_equivalent(c)

    c.rename("topic:b", "topic:b2")  # creates deprecated id, rewrites referrers (A's relation, graph members/edges)
    _assert_equivalent(c)

    c.add(Node(id="topic:c", kind="topic", title="C", relations=[relates_to("topic:c", "topic:a")]))
    _assert_equivalent(c)

    c.delete("topic:a")  # strands inbound refs from topic:c and graph:g → must stay as dangling
    _assert_equivalent(c)
    assert len(c.dangling()) >= 1  # topic:c still points at the deleted topic:a


def test_rebuild_equivalence_after_overwrite(tmp_path):
    c = Corpus(tmp_path)
    n = Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:x")])
    c.add(n)
    n.relations = [relates_to("topic:a", "topic:y")]  # change outbound refs
    c.add(n)  # same uid+id overwrite
    _assert_equivalent(c)
