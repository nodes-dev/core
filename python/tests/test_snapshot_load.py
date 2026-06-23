from __future__ import annotations

from nodes.kernel.index import Index
from nodes.kernel.node import Node
from nodes.kernel.relations import relates_to
from nodes.kernel.search import SearchIndex
from nodes.kernel.snapshot import (
    ManifestEntry,
    Snapshot,
    load_snapshot,
    read_json,
    snapshot_path,
    write_json_atomic,
    write_snapshot,
)


def _nodes() -> list[Node]:
    return [
        Node(id="topic:a", kind="topic", title="A", relations=[relates_to("topic:a", "topic:b")]),
        Node(id="topic:b", kind="topic", title="B"),
    ]


def _manifest(nodes: list[Node]) -> list[ManifestEntry]:
    return [
        ManifestEntry(path=f"topic/{n.id.split(':', 1)[1]}.md", sha256=f"{i:064d}", uid=n.uid)
        for i, n in enumerate(nodes)
    ]


def _write(tmp_path):
    nodes = _nodes()
    manifest = _manifest(nodes)
    write_snapshot(tmp_path, manifest, Index.build(nodes), SearchIndex.build(nodes), None)
    return nodes, manifest


def _snapshot_doc(tmp_path) -> dict:
    doc = read_json(snapshot_path(tmp_path))
    assert doc is not None
    return doc


def test_write_then_load_round_trips_structural_and_search(tmp_path):
    _nodes_written, manifest = _write(tmp_path)

    snapshot = load_snapshot(tmp_path, None)

    assert isinstance(snapshot, Snapshot)
    assert {m.uid for m in snapshot.manifest} == {m.uid for m in manifest}
    assert set(snapshot.index.by_uid) == {m.uid for m in manifest}
    assert set(snapshot.search_index.lengths) == {m.uid for m in manifest}
    assert snapshot.vector_index is None


def test_missing_file_returns_none(tmp_path):
    assert load_snapshot(tmp_path, None) is None


def test_bad_version_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["version"] = 0
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_bad_lang_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["lang"] = "ts"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_corrupt_json_returns_none(tmp_path):
    _write(tmp_path)
    snapshot_path(tmp_path).write_text("{", encoding="utf-8")

    assert load_snapshot(tmp_path, None) is None


def test_duplicate_manifest_uid_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["manifest"][1]["uid"] = doc["manifest"][0]["uid"]
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_manifest_section_bijection_violation_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"].pop()
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_search_id_by_uid_mismatch_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    first_uid = doc["manifest"][0]["uid"]
    doc["search"]["id_by_uid"][first_uid] = "topic:wrong"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_no_embedder_ignores_corrupt_vectors_section(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["vectors"] = {"this": "is not a vector snapshot"}
    write_json_atomic(snapshot_path(tmp_path), doc)

    snapshot = load_snapshot(tmp_path, None)

    assert isinstance(snapshot, Snapshot)
    assert snapshot.vector_index is None


def test_embedder_required_but_vectors_missing_returns_none(tmp_path):
    _write(tmp_path)

    assert load_snapshot(tmp_path, "model-v1") is None


def test_embedder_namespace_mismatch_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    manifest = doc["manifest"]
    ids_by_uid = {entry["uid"]: f"topic:{entry['path'].removeprefix('topic/').removesuffix('.md')}" for entry in manifest}
    doc["vectors"] = {
        "namespace": "other-model",
        "dim": 2,
        "vectors": {manifest[0]["uid"]: [1.0, 0.0], manifest[1]["uid"]: [0.0, 1.0]},
        "id_by_uid": ids_by_uid,
        "hash_by_uid": {entry["uid"]: entry["sha256"] for entry in manifest},
    }
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, "model-v1") is None


def test_embedder_vector_id_by_uid_mismatch_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    manifest = doc["manifest"]
    ids_by_uid = {entry["uid"]: f"topic:{entry['path'].removeprefix('topic/').removesuffix('.md')}" for entry in manifest}
    ids_by_uid[manifest[0]["uid"]] = "topic:wrong"
    doc["vectors"] = {
        "namespace": "model-v1",
        "dim": 2,
        "vectors": {manifest[0]["uid"]: [1.0, 0.0], manifest[1]["uid"]: [0.0, 1.0]},
        "id_by_uid": ids_by_uid,
        "hash_by_uid": {entry["uid"]: entry["sha256"] for entry in manifest},
    }
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, "model-v1") is None
