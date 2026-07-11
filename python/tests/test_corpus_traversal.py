from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import RefError
from nodes.kernel.node import Node
from nodes.kernel.shapes import MEMBERSHIP


def _set_node(node_id: str, members: list[str]) -> Node:
    return Node(id=node_id, kind="set", title=node_id, facets={MEMBERSHIP: {"members": members}})


def _seeded(tmp_path) -> Corpus:
    """Registry-free corpus mirroring the fixture cluster: crate ⊃ box ⊃ {tidy, renamed};
    box lists renamed under its deprecated id; crate lists a dangling note:ghost."""
    c = Corpus(tmp_path)
    c.add(Node(id="note:renamed", kind="note", title="R", deprecated_ids=["note:old-name"]))
    c.add(Node(id="note:tidy", kind="note", title="T"))
    c.add(_set_node("set:box", ["note:tidy", "note:old-name"]))
    c.add(_set_node("set:crate", ["set:box", "note:ghost"]))
    return c


def test_members_skips_dangling(tmp_path):
    assert _seeded(tmp_path).members("set:crate") == ["set:box"]


def test_members_resolves_deprecated_refs_to_sorted_live_ids(tmp_path):
    assert _seeded(tmp_path).members("set:box") == ["note:renamed", "note:tidy"]


def test_members_of_facetless_node_is_empty(tmp_path):
    assert _seeded(tmp_path).members("note:tidy") == []


def test_containers_resolves_deprecated_input_ref(tmp_path):
    assert _seeded(tmp_path).containers("note:old-name") == ["set:box"]


def test_containers_reports_direct_containers_only(tmp_path):
    assert _seeded(tmp_path).containers("set:box") == ["set:crate"]


def test_descendants_walks_nesting_and_skips_dangling(tmp_path):
    assert _seeded(tmp_path).descendants("set:crate") == ["note:renamed", "note:tidy", "set:box"]


def test_ancestors_walks_containers_transitively(tmp_path):
    assert _seeded(tmp_path).ancestors("note:renamed") == ["set:box", "set:crate"]


def test_cycles_terminate_and_exclude_start(tmp_path):
    c = Corpus(tmp_path)
    c.add(_set_node("set:loop-a", ["set:loop-b"]))
    c.add(_set_node("set:loop-b", ["set:loop-a"]))
    c.add(_set_node("set:selfie", ["set:selfie"]))
    assert c.descendants("set:loop-a") == ["set:loop-b"]
    assert c.ancestors("set:loop-b") == ["set:loop-a"]
    assert c.members("set:selfie") == ["set:selfie"]
    assert c.descendants("set:selfie") == []
    assert c.ancestors("set:selfie") == []


def test_all_four_reject_unresolvable_input_ref(tmp_path):
    c = _seeded(tmp_path)
    for fn in (c.members, c.containers, c.descendants, c.ancestors):
        with pytest.raises(RefError):
            fn("note:ghost")
