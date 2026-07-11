from __future__ import annotations

import pytest

from nodes.kernel.corpus import Corpus
from nodes.kernel.errors import CollisionError
from nodes.kernel.frontmatter import node_to_markdown
from nodes.kernel.structural_index import Index
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to
from nodes.kernel.search import SearchIndex
from nodes.kernel.snapshot import ManifestEntry, hash_bytes, load_snapshot, snapshot_path, write_snapshot


class TermEmbedder:
    cache_namespace = "term-v1"

    def embed(self, texts: list[str]) -> list[tuple[float, float]]:
        return [(1.0, 0.0) if "omega" in text else (0.0, 1.0) for text in texts]


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


def _fresh_rebuild(root, embedder=None) -> Corpus:
    snapshot_path(root).unlink()
    return Corpus(root, embedder=embedder)


def _loaded_manifest(root) -> dict[str, ManifestEntry]:
    snap = load_snapshot(root, None)
    assert snap is not None
    return {m.path: m for m in snap.manifest}


def test_round_trip_matches_fresh_rebuild(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    assert snapshot_path(tmp_path).is_file()
    loaded = Corpus(tmp_path)  # loads + reconciles (no on-disk changes)
    fresh = _fresh_rebuild(tmp_path)
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


def test_flush_index_uses_live_manifest_not_disk_rebuild(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    # Edit topic/b.md directly on disk, then flush the stale in-memory corpus.
    b_node = c.store.read_file("topic:b")
    b_node.body = "beta zeta"
    c.store.path_for("topic:b").write_text(node_to_markdown(b_node), encoding="utf-8")
    c.flush_index()
    reloaded = Corpus(tmp_path)
    assert [(h.id, h.uid) for h in reloaded.search("zeta")] == [("topic:b", b_node.uid)]


def test_delete_flush_writes_usable_manifest_matching_fresh_rebuild(tmp_path):
    c = _seed(tmp_path)
    c.delete("topic:a")
    c.flush_index()
    manifest = _loaded_manifest(tmp_path)
    assert set(manifest) == {"topic/b.md"}
    loaded = Corpus(tmp_path)
    fresh = _fresh_rebuild(tmp_path)
    assert [(h.id, h.uid) for h in loaded.search("gamma")] == [(h.id, h.uid) for h in fresh.search("gamma")]
    assert len(loaded.dangling()) == len(fresh.dangling()) == 0


def test_rename_flush_writes_updated_manifest_matching_fresh_rebuild(tmp_path):
    c = _seed(tmp_path)
    renamed = c.rename("topic:b", "topic:c")
    c.flush_index()
    manifest = _loaded_manifest(tmp_path)
    assert set(manifest) == {"topic/a.md", "topic/c.md"}
    assert manifest["topic/a.md"].sha256 == hash_bytes(c.store.path_for("topic:a").read_bytes())
    assert manifest["topic/c.md"].sha256 == hash_bytes(c.store.path_for("topic:c").read_bytes())
    loaded = Corpus(tmp_path)
    assert [(e.relation.target, e.target_uid) for e in loaded.outbound("topic:a")] == [
        ("topic:c", renamed.uid)
    ]
    fresh = _fresh_rebuild(tmp_path)
    assert _results(loaded) == _results(fresh)


def test_rename_refreshes_search_for_externally_edited_referrer_before_manifest_record(tmp_path):
    c = _seed(tmp_path)
    c.flush_index()
    loaded = Corpus(tmp_path)
    referrer = loaded.store.read_file("topic:a")
    referrer.body = "alpha gamma omega"
    loaded.store.path_for("topic:a").write_text(node_to_markdown(referrer), encoding="utf-8")
    loaded.rename("topic:b", "topic:c")
    loaded.flush_index()
    reloaded = Corpus(tmp_path)
    fresh = _fresh_rebuild(tmp_path)
    assert [(h.id, h.uid) for h in reloaded.search("omega")] == [
        (h.id, h.uid) for h in fresh.search("omega")
    ] == [("topic:a", referrer.uid)]


def test_rename_refreshes_vectors_for_externally_edited_referrer_before_manifest_record(tmp_path):
    embedder = TermEmbedder()
    c = Corpus(tmp_path, embedder=embedder)
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
    c.flush_index()
    loaded = Corpus(tmp_path, embedder=embedder)
    referrer = loaded.store.read_file("topic:a")
    referrer.body = "alpha gamma omega"
    loaded.store.path_for("topic:a").write_text(node_to_markdown(referrer), encoding="utf-8")
    loaded.rename("topic:b", "topic:c")
    loaded.flush_index()
    reloaded = Corpus(tmp_path, embedder=embedder)
    fresh = _fresh_rebuild(tmp_path, embedder=embedder)
    reloaded_hit = reloaded.query_vector((1.0, 0.0), k=1)[0]
    fresh_hit = fresh.query_vector((1.0, 0.0), k=1)[0]
    assert (reloaded_hit.id, reloaded_hit.uid) == (fresh_hit.id, fresh_hit.uid) == ("topic:a", referrer.uid)
    assert reloaded_hit.score == pytest.approx(fresh_hit.score)
    assert reloaded_hit.score == pytest.approx(1.0)


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


def test_manifest_path_identity_mismatch_silently_rebuilds(tmp_path):
    c = Corpus(tmp_path)
    node = c.add(Node(id="topic:a", kind="topic", title="A", body="alpha"))
    ghost = Node(id="topic:b", kind="topic", uid="b" * 32, title="B", body="beta")
    write_snapshot(
        tmp_path,
        [
            ManifestEntry(
                path="topic/a.md",
                sha256=hash_bytes(c.store.path_for("topic:a").read_bytes()),
                uid=ghost.uid,
            )
        ],
        Index.build([ghost]),
        SearchIndex.build([ghost]),
        None,
    )

    rebuilt = Corpus(tmp_path)

    assert [(h.id, h.uid) for h in rebuilt.search("alpha")] == [("topic:a", node.uid)]
    assert rebuilt.search("beta") == []
    assert [n.id for n in rebuilt.all()] == ["topic:a"]


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
