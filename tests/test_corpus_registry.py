from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import InvariantError, UnknownKindError
from nodes.kernel.node import Node
from nodes.kernel.registry import Registry
from nodes.vocab.kinds import register_knowledge_vocab
from nodes.vocab.source import SOURCE


def _registry() -> Registry:
    r = Registry()
    register_knowledge_vocab(r)
    return r


def test_no_registry_skips_validation(tmp_path):
    c = Corpus(tmp_path)  # no registry — today's behavior
    c.add(Node(id="zzz:a", kind="zzz", title="A"))  # unregistered kind, still allowed
    assert c.get("zzz:a").title == "A"


def test_registry_rejects_unknown_kind_no_file(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    with pytest.raises(UnknownKindError):
        c.add(Node(id="zzz:a", kind="zzz", title="A"))
    assert not (tmp_path / "zzz").exists()


def test_registry_rejects_invalid_paper_no_file(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    with pytest.raises(InvariantError):  # empty source facet
        c.add(Node(id="paper:a", kind="paper", title="A", facets={SOURCE: {}}))
    assert not (tmp_path / "paper").exists()


def test_registry_accepts_valid_node(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    c.add(Node(id="paper:a", kind="paper", title="A", facets={SOURCE: {"year": 2026}}))
    assert c.get("paper:a").title == "A"
