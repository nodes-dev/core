from __future__ import annotations

from nodes.kernel.corpus import Corpus
from nodes.kernel.node import Node
from nodes.kernel.registry import Registry
from nodes.kernel.relations import Relation
from nodes.kernel.shapes import MEMBERSHIP, register_builtin_shapes
from nodes.vocab.kinds import register_knowledge_vocab
from nodes.vocab.source import SOURCE


def _registry() -> Registry:
    r = Registry()
    register_builtin_shapes(r)
    register_knowledge_vocab(r)
    return r


def _tuples(findings) -> list[tuple[str, str, str, str]]:
    return [(f.severity, f.code, f.ref, f.detail) for f in findings]


def test_clean_corpus_no_findings(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    c.add(Node(id="topic:t", kind="topic", title="T"))
    c.add(Node(id="note:n", kind="note", title="N",
               relations=[Relation(source="note:n", predicate="about", target="topic:t")]))
    assert c.check() == []


def test_hand_edited_violations_reported(tmp_path):
    seed = Corpus(tmp_path)  # registry-free: simulates hand-edited files
    seed.add(Node(id="zzz:m", kind="zzz", title="M"))
    seed.add(Node(id="note:s", kind="note", title="S", facets={SOURCE: {"year": 2026}}))
    seed.add(Node(id="paper:b", kind="paper", title="B",
                  relations=[Relation(source="paper:b", predicate="cites", target="paper:ghost")]))
    c = Corpus(tmp_path, registry=_registry())
    assert _tuples(c.check()) == [
        ("error", "facet-unexpected", "note:s", "source"),
        ("warning", "dangling-ref", "paper:b", "paper:ghost"),
        ("error", "facet-missing", "paper:b", "source"),
        ("error", "unknown-kind", "zzz:m", "zzz"),
    ]


def test_no_registry_reports_only_dangling(tmp_path):
    seed = Corpus(tmp_path)
    seed.add(Node(id="zzz:m", kind="zzz", title="M",
                  relations=[Relation(source="zzz:m", predicate="cites", target="note:gone")]))
    c = Corpus(tmp_path)
    assert _tuples(c.check()) == [("warning", "dangling-ref", "zzz:m", "note:gone")]


def test_passed_registry_overrides_corpus_registry(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    c.add(Node(id="note:n", kind="note", title="N"))
    empty = Registry()
    assert _tuples(c.check(registry=empty)) == [("error", "unknown-kind", "note:n", "note")]


def test_details_order_by_code_point(tmp_path):
    seed = Corpus(tmp_path)  # registry-free: simulates hand-edited files
    # U+FF61 < U+1F600 by code point; UTF-16 code-unit order would reverse them.
    seed.add(Node(id="note:x", kind="note", title="X", facets={"｡": {}, "\U0001f600": {}}))
    c = Corpus(tmp_path, registry=_registry())
    assert [f.detail for f in c.check()] == ["｡", "\U0001f600"]


def test_check_does_not_mutate_corpus(tmp_path):
    seed = Corpus(tmp_path)
    seed.add(Node(id="zzz:m", kind="zzz", title="M"))
    c = Corpus(tmp_path, registry=_registry())
    c.check()
    assert c.get("zzz:m").title == "M"  # still readable, file untouched


def test_dangling_member_reported_after_delete_and_deduped(tmp_path):
    seed = Corpus(tmp_path)  # registry-free: dangling-member is registry-independent
    seed.add(Node(id="note:gone", kind="note", title="G"))
    seed.add(Node(id="set:box", kind="set", title="Box",
                  facets={MEMBERSHIP: {"members": ["note:gone", "note:gone"]}}))
    seed.delete("note:gone")
    assert _tuples(seed.check()) == [("warning", "dangling-member", "set:box", "note:gone")]


def test_dangling_member_orders_with_other_findings(tmp_path):
    seed = Corpus(tmp_path)
    seed.add(Node(id="set:box", kind="set", title="Box",
                  relations=[Relation(source="set:box", predicate="about", target="topic:gone")],
                  facets={MEMBERSHIP: {"members": ["note:ghost"]}}))
    assert _tuples(seed.check()) == [
        ("warning", "dangling-member", "set:box", "note:ghost"),
        ("warning", "dangling-ref", "set:box", "topic:gone"),
    ]
