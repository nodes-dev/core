from __future__ import annotations

import pytest

from nodes.core.corpus import Corpus
from nodes.core.errors import InvariantError, UnknownKindError
from nodes.core.node import Node
from nodes.core.registry import Registry
from tests._fixtures_profile import SOURCE, register_fixtures_profile


def _registry() -> Registry:
    r = Registry()
    register_fixtures_profile(r)
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


from nodes.core.errors import FacetError, RefError  # noqa: E402
from nodes.core.relations import Relation  # noqa: E402


def test_rename_validates_renamed_node_no_write(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    c.add(Node(id="paper:a", kind="paper", title="A", facets={SOURCE: {"year": 2026}}))
    # paper -> note keeps the source facet, which a bare note may not carry
    with pytest.raises(FacetError):
        c.rename("paper:a", "note:a")
    assert (tmp_path / "paper" / "a.md").exists()
    assert not (tmp_path / "note").exists()
    assert c.get("paper:a").title == "A"


def test_rename_valid_rewrites_referrer(tmp_path):
    c = Corpus(tmp_path, registry=_registry())
    c.add(Node(id="paper:b", kind="paper", title="B", facets={SOURCE: {"year": 2020}}))
    c.add(Node(id="note:a", kind="note", title="A",
               relations=[Relation(source="note:a", predicate="cites", target="paper:b")]))
    c.rename("paper:b", "paper:c")
    assert c.get("paper:c").title == "B"
    assert c.get("note:a").relations[0].target == "paper:c"
    assert c.resolve("paper:b").id == "paper:c"  # deprecated alias still resolves


def test_rename_blocked_by_invalid_referrer_no_writes(tmp_path):
    seed = Corpus(tmp_path)  # no registry — lets us write an invalid referrer
    seed.add(Node(id="topic:t", kind="topic", title="T"))
    seed.add(Node(id="paper:bad", kind="paper", title="Bad", facets={SOURCE: {}},
                  relations=[Relation(source="paper:bad", predicate="about", target="topic:t")]))
    c = Corpus(tmp_path, registry=_registry())
    with pytest.raises(InvariantError):  # the invalid referrer fails validation
        c.rename("topic:t", "topic:t2")
    # nothing was written: old id still live, new id absent, referrer untouched
    fresh = Corpus(tmp_path)
    assert fresh.get("topic:t").title == "T"
    with pytest.raises(RefError):
        fresh.get("topic:t2")
    assert fresh.get("paper:bad").relations[0].target == "topic:t"
