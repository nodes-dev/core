from __future__ import annotations

import pytest

from nodes.kernel.errors import FacetError, InvariantError, UnknownKindError
from nodes.kernel.node import Node
from nodes.kernel.registry import Registry
from nodes.vocab.kinds import PROSE_KINDS, SOURCE_KINDS, register_knowledge_vocab
from nodes.vocab.source import SOURCE


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    register_knowledge_vocab(r)
    return r


def test_all_kinds_registered(reg):
    for name in PROSE_KINDS + SOURCE_KINDS:
        assert reg.is_registered(name)


def test_bare_note_validates(reg):
    reg.validate(Node(id="note:a", kind="note", title="A"))  # no raise


def test_note_with_stray_facet_raises(reg):
    with pytest.raises(FacetError):
        reg.validate(Node(id="note:a", kind="note", title="A", facets={SOURCE: {"year": 2026}}))


def test_paper_missing_source_raises(reg):
    with pytest.raises(FacetError):
        reg.validate(Node(id="paper:a", kind="paper", title="A"))


def test_paper_empty_source_raises(reg):
    with pytest.raises(InvariantError):
        reg.validate(Node(id="paper:a", kind="paper", title="A", facets={SOURCE: {}}))


def test_paper_valid_source_passes(reg):
    reg.validate(Node(id="paper:a", kind="paper", title="A", facets={SOURCE: {"year": 2026}}))


def test_book_and_dataset_share_source_invariant(reg):
    for kind in ("book", "dataset"):
        with pytest.raises(InvariantError):
            reg.validate(Node(id=f"{kind}:a", kind=kind, title="A", facets={SOURCE: {}}))
        reg.validate(Node(id=f"{kind}:b", kind=kind, title="B", facets={SOURCE: {"identifier": "x"}}))


def test_unregistered_kind_raises():
    reg = Registry()  # empty
    with pytest.raises(UnknownKindError):
        reg.validate(Node(id="note:a", kind="note", title="A"))
