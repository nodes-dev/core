from __future__ import annotations

from pathlib import Path

from nodes.kernel.frontmatter import node_from_markdown, node_to_markdown

FIXTURE = Path(__file__).parent / "fixtures" / "gene_phf19.md"


def test_golden_fixture_parses():
    n = node_from_markdown(FIXTURE.read_text(encoding="utf-8"))
    assert n.id == "gene:PHF19"
    assert n.kind == "gene"
    assert n.facets["bio-axes"]["primary_external_id"] == "HGNC:7296"
    targets = {r.target for r in n.relations}
    assert {"topic:polycomb", "gene:EZH2"} <= targets


def test_serialize_is_idempotent():
    n = node_from_markdown(FIXTURE.read_text(encoding="utf-8"))
    once = node_to_markdown(n)
    twice = node_to_markdown(node_from_markdown(once))
    assert once == twice
