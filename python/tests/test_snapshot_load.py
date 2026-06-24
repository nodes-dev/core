from __future__ import annotations

import json

import pytest

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


def _ids_by_uid(manifest: list[dict]) -> dict[str, str]:
    return {
        entry["uid"]: f"topic:{entry['path'].removeprefix('topic/').removesuffix('.md')}"
        for entry in manifest
    }


def _vector_section(manifest: list[dict], namespace: str) -> dict:
    return {
        "namespace": namespace,
        "dim": 2,
        "vectors": {manifest[0]["uid"]: [1.0, 0.0], manifest[1]["uid"]: [0.0, 1.0]},
        "id_by_uid": _ids_by_uid(manifest),
        "hash_by_uid": {entry["uid"]: entry["sha256"] for entry in manifest},
    }


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


def test_duplicate_manifest_path_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["manifest"][1]["path"] = doc["manifest"][0]["path"]
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


@pytest.mark.parametrize("key", ("manifest", "structural", "search", "vectors"))
def test_missing_required_top_level_key_returns_none(tmp_path, key):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    del doc[key]
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_non_dict_manifest_row_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["manifest"][0] = "not a manifest row"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_manifest_row_missing_uid_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    del doc["manifest"][0]["uid"]
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


@pytest.mark.parametrize("field", ("path", "sha256", "uid"))
def test_non_string_manifest_row_field_returns_none(tmp_path, field):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["manifest"][0][field] = 123
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_manifest_sha_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["manifest"][0]["sha256"] = "not-a-sha"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


@pytest.mark.parametrize("path", ("/abs.md", "../x.md", "topic\\a.md", "", "topic/a.txt"))
def test_malformed_manifest_path_returns_none(tmp_path, path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["manifest"][0]["path"] = path
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_manifest_path_under_nodes_index_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["manifest"][0]["path"] = ".nodes-index/foo.md"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_manifest_section_bijection_violation_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"].pop()
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_manifest_path_must_match_structural_id_for_uid(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["manifest"][0]["path"] = "topic/wrong.md"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_structural_entries_container_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"] = {}
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_structural_entry_id_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    first_uid = doc["manifest"][0]["uid"]
    doc["structural"]["entries"][0]["id"] = 123
    doc["search"]["id_by_uid"][first_uid] = 123
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_structural_entry_invalid_id_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    first_uid = doc["manifest"][0]["uid"]
    doc["structural"]["entries"][0]["id"] = "not-a-node-id"
    doc["search"]["id_by_uid"][first_uid] = "not-a-node-id"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_structural_entry_id_kind_mismatch_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    first_uid = doc["manifest"][0]["uid"]
    doc["structural"]["entries"][0]["id"] = "note:a"
    doc["structural"]["entries"][0]["kind"] = "topic"
    doc["search"]["id_by_uid"][first_uid] = "note:a"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


@pytest.mark.parametrize("weight", [True, float("nan"), float("inf"), "1.0"])
def test_malformed_structural_relation_weight_returns_none(tmp_path, weight):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"][0]["relations"][0]["weight"] = weight
    snapshot_path(tmp_path).write_text(json.dumps(doc), encoding="utf-8")

    assert load_snapshot(tmp_path, None) is None


def test_malformed_structural_relation_directed_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"][0]["relations"][0]["directed"] = "false"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_structural_refs_not_a_list_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"][0]["structural_refs"] = {}
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_structural_ref_missing_ref_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"][0]["structural_refs"] = [{"role": "membership_member"}]
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_structural_ref_invalid_role_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["structural"]["entries"][0]["structural_refs"] = [{"ref": "topic:a", "role": "bogus"}]
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_search_id_by_uid_mismatch_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    first_uid = doc["manifest"][0]["uid"]
    doc["search"]["id_by_uid"][first_uid] = "topic:wrong"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_search_lengths_container_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["search"]["lengths"] = []
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_search_postings_container_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["search"]["postings"] = []
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_search_empty_posting_bucket_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    doc["search"]["postings"]["ghost"] = {}
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, None) is None


def test_malformed_search_tf_greater_than_length_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    first_uid = doc["manifest"][0]["uid"]
    doc["search"]["postings"]["ghost"] = {first_uid: [2, 0]}
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
    doc["vectors"] = _vector_section(manifest, "other-model")
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, "model-v1") is None


def test_embedder_loads_valid_vector_section(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    manifest = doc["manifest"]
    doc["vectors"] = _vector_section(manifest, "expected-ns")
    write_json_atomic(snapshot_path(tmp_path), doc)

    snapshot = load_snapshot(tmp_path, "expected-ns")

    assert isinstance(snapshot, Snapshot)
    assert snapshot.vector_index is not None
    assert snapshot.vector_index.namespace == "expected-ns"
    assert set(snapshot.vector_index.vectors) == {entry["uid"] for entry in manifest}


def test_embedder_malformed_vectors_container_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    manifest = doc["manifest"]
    doc["vectors"] = _vector_section(manifest, "model-v1")
    doc["vectors"]["dim"] = None
    doc["vectors"]["vectors"] = []
    doc["vectors"]["id_by_uid"] = {}
    doc["vectors"]["hash_by_uid"] = {}
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, "model-v1") is None


@pytest.mark.parametrize("vector", ([2.0, 0.0], [0.0, 0.0]))
def test_embedder_non_unit_vector_returns_none(tmp_path, vector):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    manifest = doc["manifest"]
    doc["vectors"] = _vector_section(manifest, "expected-ns")
    doc["vectors"]["vectors"][manifest[0]["uid"]] = vector
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, "expected-ns") is None


@pytest.mark.parametrize("hash_value", (123, "not-a-sha"))
def test_embedder_malformed_vector_hash_returns_none(tmp_path, hash_value):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    manifest = doc["manifest"]
    doc["vectors"] = _vector_section(manifest, "expected-ns")
    doc["vectors"]["hash_by_uid"][manifest[0]["uid"]] = hash_value
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, "expected-ns") is None


def test_embedder_vector_id_by_uid_mismatch_returns_none(tmp_path):
    _write(tmp_path)
    doc = _snapshot_doc(tmp_path)
    manifest = doc["manifest"]
    doc["vectors"] = _vector_section(manifest, "model-v1")
    doc["vectors"]["id_by_uid"][manifest[0]["uid"]] = "topic:wrong"
    write_json_atomic(snapshot_path(tmp_path), doc)

    assert load_snapshot(tmp_path, "model-v1") is None
