from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import CollisionError
from nodes.kernel.frontmatter import node_to_markdown
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to
from nodes.kernel.snapshot import snapshot_path


def _seed(root) -> Corpus:
    c = Corpus(root)
    c.add(
        Node(
            id="topic:a",
            kind="topic",
            title="A",
            body="alpha gamma",
            relations=[relates_to("topic:a", "topic:b")],
        )
    )
    c.add(Node(id="topic:b", kind="topic", title="B", body="beta gamma"))
    return c


def _results(c: Corpus) -> dict:
    return {
        "search_gamma": [(h.id, h.uid) for h in c.search("gamma")],
        "outbound_a": [(e.relation.target, e.target_uid) for e in c.outbound("topic:a")],
        "dangling": len(c.dangling()),
    }


def test_round_trip_matches_fresh_rebuild(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    assert snapshot_path(tmp_path).is_file()
    loaded = Corpus(tmp_path)  # loads + reconciles (no on-disk changes)
    fresh = Corpus(tmp_path)  # also loads, identical
    assert _results(loaded) == _results(c)
    assert _results(loaded) == _results(fresh)


def test_construction_never_writes_snapshot(tmp_path):
    _seed(tmp_path)  # no flush
    assert not snapshot_path(tmp_path).is_file()
    Corpus(tmp_path)  # full rebuild, must not write
    assert not snapshot_path(tmp_path).is_file()


def test_reconcile_after_direct_disk_edit(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    # Edit topic/b.md directly on disk (content change, same uid/id).
    b_node = c.store.read_file("topic:b")
    b_node.body = "beta delta epsilon"
    c.store.path_for("topic:b").write_text(node_to_markdown(b_node), encoding="utf-8")
    reconciled = Corpus(tmp_path)
    assert [(h.id, h.uid) for h in reconciled.search("delta")] == [("topic:b", b_node.uid)]


def test_reconcile_added_and_deleted_files(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    # Delete a's file, add a new file, both directly on disk.
    c.store.path_for("topic:a").unlink()
    c.store.write_file(Node(id="topic:c", kind="topic", title="C", body="gamma"))
    reconciled = Corpus(tmp_path)
    ids = {h.id for h in reconciled.search("gamma")}
    assert ids == {"topic:b", "topic:c"}  # a gone, c present, b retained


def test_corrupt_snapshot_silently_rebuilds(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    snapshot_path(tmp_path).write_text("{garbage", encoding="utf-8")
    rebuilt = Corpus(tmp_path)  # must not raise
    assert _results(rebuilt) == _results(c)


def test_malformed_corpus_file_propagates(tmp_path):
    _seed(tmp_path)
    c2 = Corpus(tmp_path)
    c2.flush_index()
    # Corrupt an actual corpus file (not the cache): construction must raise.
    c2.store.path_for("topic:a").write_text("---\nnot: valid node\n---\nbody", encoding="utf-8")
    with pytest.raises(Exception):
        Corpus(tmp_path)


def test_reconcile_uid_collision_raises(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    # Rewrite b.md so it claims a's uid -> duplicate uid on reconcile.
    a = c.store.read_file("topic:a")
    b = c.store.read_file("topic:b")
    b.uid = a.uid
    c.store.path_for("topic:b").write_text(node_to_markdown(b), encoding="utf-8")
    with pytest.raises(CollisionError):
        Corpus(tmp_path)
