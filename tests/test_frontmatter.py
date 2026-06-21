from __future__ import annotations

from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown, split_frontmatter
from nodes.kernel.node import Node
from nodes.kernel.relations import Relation, relates_to


def test_split_no_frontmatter():
    fm, body = split_frontmatter("just text")
    assert fm == {} and body == "just text"


def test_parse_related_and_relations():
    text = (
        "---\n"
        "id: gene:PHF19\n"
        "uid: deadbeefdeadbeefdeadbeefdeadbeef\n"
        "kind: gene\n"
        "title: PHF19\n"
        "related: [topic:polycomb]\n"
        "relations:\n"
        "  - { predicate: interacts_with, target: gene:EZH2 }\n"
        "---\n"
        "PHF19 body.\n"
    )
    n = node_from_markdown(text)
    assert n.id == "gene:PHF19" and n.uid == "deadbeefdeadbeefdeadbeefdeadbeef"
    assert relates_to("gene:PHF19", "topic:polycomb") in n.relations
    assert Relation(source="gene:PHF19", predicate="interacts_with", target="gene:EZH2") in n.relations
    assert n.body == "PHF19 body.\n"


def test_body_preserves_whitespace_below_frontmatter():
    text = (
        "---\n"
        "id: topic:a\n"
        "uid: deadbeefdeadbeefdeadbeefdeadbeef\n"
        "kind: topic\n"
        "title: A\n"
        "---\n"
        "\n"
        "First paragraph.\n"
        "\n"
    )
    n = node_from_markdown(text)
    assert n.body == "\nFirst paragraph.\n\n"
    assert node_from_markdown(node_to_markdown(n)).body == n.body


def test_roundtrip_preserves_relations_and_facets():
    n = Node(
        id="gene:PHF19", kind="gene", title="PHF19",
        uid="deadbeefdeadbeefdeadbeefdeadbeef",
        relations=[
            relates_to("gene:PHF19", "topic:polycomb"),
            Relation(source="gene:PHF19", predicate="interacts_with", target="gene:EZH2"),
        ],
        facets={"bio-axes": {"primary_external_id": "HGNC:7296"}},
        body="PHF19 body.",
    )
    reparsed = node_from_markdown(node_to_markdown(n))
    assert reparsed.id == n.id
    assert reparsed.facets == n.facets
    assert set((r.predicate, r.target) for r in reparsed.relations) == \
        set((r.predicate, r.target) for r in n.relations)


def test_plain_relatesto_serializes_into_related_only():
    n = Node(id="topic:a", kind="topic", title="A",
             relations=[relates_to("topic:a", "topic:b")])
    md = node_to_markdown(n)
    assert "related:" in md
    assert "relations:" not in md
