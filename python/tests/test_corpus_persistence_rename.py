from __future__ import annotations

from nodes.kernel.corpus import Corpus
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to
from nodes.kernel.snapshot import iter_corpus_files, load_snapshot, read_json, snapshot_path


class FixedEmbedder:
    cache_namespace = "test-ns"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, 0.0) for _ in texts]


def _manifest_matches_disk(c: Corpus) -> bool:
    """Every in-memory manifest entry equals the actual on-disk file bytes + walk."""
    on_disk = {f.path: f.sha256 for f in iter_corpus_files(c.store.root)}
    mem = {p: e.sha256 for p, e in c.manifest.items()}
    return on_disk == mem


def _results(c: Corpus):
    return (
        sorted((h.id, h.uid) for h in c.search("gamma")),
        sorted((e.relation.source, e.relation.target) for e in c.dangling()),
        sorted(c.index.id_to_uid),
    )


def test_add_keeps_manifest_in_sync(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", body="gamma"))
    c.add(Node(id="topic:b", kind="topic", title="B", body="gamma"))
    assert _manifest_matches_disk(c)


def test_delete_removes_manifest_entry(tmp_path):
    c = Corpus(tmp_path)
    c.add(Node(id="topic:a", kind="topic", title="A", body="gamma"))
    c.add(Node(id="topic:b", kind="topic", title="B", body="gamma"))
    c.delete("topic:a")
    assert "topic/a.md" not in c.manifest
    assert _manifest_matches_disk(c)


def test_rename_updates_referrers_and_old_path(tmp_path):
    c = Corpus(tmp_path)
    c.add(
        Node(
            id="topic:a",
            kind="topic",
            title="A",
            body="gamma",
            relations=[relates_to("topic:a", "topic:b")],
        )
    )
    c.add(Node(id="topic:b", kind="topic", title="B", body="gamma"))
    c.rename("topic:b", "topic:b2")  # rewrites a.md (referrer) and moves b.md -> b2.md
    assert "topic/b.md" not in c.manifest  # old path removed
    assert "topic/b2.md" in c.manifest
    assert _manifest_matches_disk(c)  # referrer a.md re-hashed too


def test_flush_after_mutations_reloads_equivalently(tmp_path):
    c = Corpus(tmp_path)
    c.add(
        Node(
            id="topic:a",
            kind="topic",
            title="A",
            body="gamma",
            relations=[relates_to("topic:a", "topic:b")],
        )
    )
    c.add(Node(id="topic:b", kind="topic", title="B", body="gamma"))
    c.rename("topic:b", "topic:b2")
    c.add(Node(id="topic:c", kind="topic", title="C", body="gamma"))
    c.delete("topic:a")
    c.flush_index()
    reloaded = Corpus(tmp_path)
    assert load_snapshot(tmp_path, None) is not None
    assert _results(reloaded) == _results(c)
    # And a from-scratch rebuild (no snapshot) agrees:
    snapshot_path(tmp_path).unlink()
    assert _results(Corpus(tmp_path)) == _results(c)


def test_rename_rewrites_structure_form_facet_refs_without_registry(tmp_path):
    from nodes.kernel.corpus import Corpus
    from nodes.kernel.node import Node
    from nodes.kernel.shapes import EDGES, KEYS, MEMBERSHIP, ORDER

    c = Corpus(tmp_path)  # no registry attached
    c.store.write_file(Node(id="topic:a", kind="topic", title="A"))
    c.store.write_file(Node(id="topic:b", kind="topic", title="B"))
    c.store.write_file(Node(
        id="graph:g", kind="graph", title="G",
        facets={MEMBERSHIP: {"members": ["topic:a", "topic:b"]},
                EDGES: {"edges": [{"source": "topic:a", "predicate": "to", "target": "topic:b"}]}},
    ))
    c.store.write_file(Node(
        id="list:l", kind="list", title="L",
        facets={MEMBERSHIP: {"members": ["topic:a"]}, ORDER: {"order": ["topic:a"]}},
    ))
    c.store.write_file(Node(
        id="dict:d", kind="dict", title="D",
        facets={MEMBERSHIP: {"members": ["topic:a"]}, KEYS: {"keys": {"k": "topic:a"}}},
    ))
    c = Corpus(tmp_path)  # reload: index sees every structural ref, with no registry

    c.rename("topic:a", "topic:c")

    g = c.store.read_file("graph:g")
    assert g.facets[MEMBERSHIP]["members"] == ["topic:c", "topic:b"]
    assert g.facets[EDGES]["edges"][0]["source"] == "topic:c"
    assert c.store.read_file("list:l").facets[ORDER]["order"] == ["topic:c"]
    assert c.store.read_file("dict:d").facets[KEYS]["keys"] == {"k": "topic:c"}


def test_delete_last_embedder_node_flushes_self_usable_snapshot(tmp_path):
    c = Corpus(tmp_path, embedder=FixedEmbedder())
    c.add(Node(id="topic:a", kind="topic", title="A", body="gamma"))
    c.delete("topic:a")
    c.flush_index()
    doc = read_json(snapshot_path(tmp_path))
    assert doc["vectors"]["vectors"] == {}
    assert doc["vectors"]["dim"] is None

    reloaded = Corpus(tmp_path, embedder=FixedEmbedder())
    assert reloaded.vector_index is not None
    assert reloaded.vector_index.dim is None
    assert reloaded.similar_text("query") == []
