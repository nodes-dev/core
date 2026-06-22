from __future__ import annotations

from nodes.vocab import predicates as p


def test_constant_values():
    assert p.ABOUT == "about"
    assert p.CITES == "cites"
    assert p.ANSWERS == "answers"
    assert p.ASKS == "asks"
    assert p.REFINES == "refines"


def test_helpers_build_relations():
    cases = [
        (p.about, p.ABOUT),
        (p.cites, p.CITES),
        (p.answers, p.ANSWERS),
        (p.asks, p.ASKS),
        (p.refines, p.REFINES),
    ]
    for fn, predicate in cases:
        rel = fn("note:a", "topic:b")
        assert rel.source == "note:a"
        assert rel.target == "topic:b"
        assert rel.predicate == predicate
        assert rel.directed is True
