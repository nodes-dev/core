# Nodes Index Persistence — Design

**Status:** approved design (Python first; TypeScript port is a later spec)
**Scope:** on-disk persistence of the three derived indexes (`Index`, `SearchIndex`,
`VectorIndex`) so that constructing a `Corpus` over an unchanged corpus skips the
full parse + re-index pass. Realizes §5 ("fast I/O via a rebuildable derived index").

---

## 1. Goal & non-goals

**Goal:** startup speed at scale. A `Corpus` over a large, unchanged corpus should
load a persisted snapshot and reconcile only what changed on disk, instead of
re-parsing and re-indexing every `*.md` file on every construction.

Files remain the single source of truth; the snapshot is a **disposable, private,
per-language cache**. It is never the authority — every load reconciles the snapshot
against the current files by content hash, so a stale or absent snapshot costs only
time, never correctness.

**Non-goals:**

- No auto-flush. No `close()` / context-manager lifecycle. Writing is explicit.
- No eviction of orphaned raw-vector cache files under `.nodes-index/vectors/`.
- No cross-language snapshot reads (Python never reads a TS snapshot or vice versa).
- No approximate nearest-neighbour; cosine stays exact brute-force.
- The TypeScript port is a separate later spec; this spec is Python-only.

---

## 2. Architecture

Keep the three index classes **pure data with no file I/O**. They gain only pure
`to_dict()` / `from_dict()` (serialization is not file I/O).

A new module `python/src/nodes/kernel/snapshot.py` owns everything on-disk:

- the snapshot file location and atomic write,
- the `version` / `lang` gate and the **integrity validation**,
- the `path → (sha256, uid)` **manifest**,
- the **file-walk** (read bytes once, hash, parse-on-demand) shared by full rebuild
  and reconcile,
- the **reconcile** algorithm.

`Corpus` owns an in-memory manifest kept in sync across every write path, and exposes
`flush_index()`.

### 2.1 File layout

One JSON file per language under the already-git-ignored `.nodes-index/`:

```
<root>/.nodes-index/snapshot.py.json     # Python
<root>/.nodes-index/snapshot.ts.json     # TypeScript (later spec)
<root>/.nodes-index/vectors/<ns>/<sha>.json   # existing raw-vector cache (unchanged)
```

Distinct filenames are how the private per-language caches coexist in one repo
without clobbering each other.

### 2.2 Snapshot document

```json
{
  "version": 1,
  "lang": "py",
  "manifest": [
    {"path": "gene/PHF19.md", "sha256": "<64 hex>", "uid": "7b2c…"}
  ],
  "structural": { "entries": [ … ] },
  "search": { "postings": { … }, "lengths": { … }, "id_by_uid": { … } },
  "vectors": { "namespace": "fixture-v1", "dim": 4, "vectors": { … },
               "id_by_uid": { … }, "hash_by_uid": { … } }
}
```

- `version` equals the module constant `SNAPSHOT_SCHEMA_VERSION` (starts at `1`).
  Any mismatch makes the snapshot unusable (silent rebuild).
- `lang` is `"py"`. A snapshot whose `lang` differs is unusable.
- `manifest` paths are **root-relative POSIX** strings (portable if the repo moves).
- `vectors` is `null` when the writing corpus had no embedder.

---

## 3. The manifest

The manifest is the authoritative list of indexed files. Each entry pins one file by:

- `path` — root-relative POSIX path,
- `sha256` — hash of the file's **actual on-disk bytes**,
- `uid` — the uid the file's node produced.

**Invariant (byte-level product):** the manifest is *always* produced by a byte-level
file walk — both on reconcile and on full rebuild. The load path never hashes
`node_to_markdown(node)`; it hashes the bytes read from disk. This guarantees that the
next reconcile's "did this file change?" test compares like with like (YAML/formatting
normalization can make `node_to_markdown(parse(bytes)) != bytes`, which would otherwise
mark unchanged files as changed).

The in-memory manifest is updated on every write path so that `flush_index()` needs no
re-reads (a freshly written file's bytes are exactly `node_to_markdown(node)`, so the
write path may hash those bytes — equal to the on-disk bytes it just wrote):

- **add(node):** set `manifest[rel(node)] = (sha256(node_to_markdown(node)), node.uid)`.
- **delete(node_id):** remove the entry for that path.
- **rename(old, new):** set the renamed node's new entry; if the path moved
  (`old_path != new_path`) remove the old path's entry; **and re-hash every rewritten
  referrer** at its (unchanged) path — rename rewrites inbound referrers' files too, so
  their bytes and hashes change.

---

## 4. Load & reconcile

`Corpus.__init__` (no snapshot write ever):

```
snap = load_snapshot(snapshot_path, embedder_namespace)   # None if no file / unusable
if snap is None:
    full_rebuild()        # byte-walk: read+hash+parse every file, build all indexes
else:
    reconcile(snap)       # byte-walk: read+hash every file; parse only changed/added
```

`load_snapshot()` reads and validates **only the cache file**. It never parses corpus
files, so it cannot raise corpus errors. It returns `None` (→ silent full rebuild) when
the file is missing, is not valid JSON, has a mismatched `version`/`lang`, fails
integrity validation (§5), or — when an embedder is configured — has a missing or
mismatched `vectors` section (§6).

### 4.1 Reconcile algorithm

1. Deserialize the three sections into live `Index` / `SearchIndex` / `VectorIndex`
   objects (snapshot-time state). In no-embedder mode the `vectors` section is ignored
   without deserialization (§6).
2. Walk current `*.md` files; for each read bytes once and compute `sha256`. Diff
   against the manifest:
   - **unchanged** (path present, hash matches): keep the deserialized state; do not
     parse.
   - **changed** (path present, hash differs): drop the manifest's old uid from all
     indexes; parse the node from the already-read bytes; upsert.
   - **added** (path absent from manifest): parse from the read bytes; upsert.
   - **deleted** (manifest path absent on disk): drop its uid from all indexes.
3. Apply all **drops before upserts** (so a uid that moves files is handled cleanly).
   Upserts run the existing collision contract (`assert_addable`); a corpus that
   collides on reconcile raises `CollisionError`, exactly as `build()` does.
4. Rebuild the in-memory manifest from this walk (root-relative path, freshly computed
   hash, node uid), satisfying the §3 byte-level invariant.

**Error scoping (cache vs. corpus):** the silent fallback is strictly for snapshot-cache
unusability detected inside `load_snapshot()`. Any error raised while reading or parsing
corpus files, or from the index collision contract — during *either* `full_rebuild()` or
`reconcile()` — propagates unchanged. Cache problems silently rebuild; corpus problems
surface.

### 4.2 Cost

Unchanged files cost one read + one sha256 (no YAML parse, no pydantic `Node`
construction, no index extraction). Changed/added files are read exactly once: hashed,
then parsed from the in-memory bytes.

---

## 5. Integrity validation

`load_snapshot()` validates internal consistency before any entry is trusted. "Hashes
match" alone proves only that files are unchanged, not that the cached index state
corresponds to them — so:

- **Duplicate manifest uids** → unusable.
- **Bijection (structural & search):** the set of manifest uids equals the set of uids
  in the structural section and equals the set in the search section. Any uid in an
  index section but not the manifest, or vice versa → unusable.
- **Vector section** (only when an embedder is configured, see §6): its uid set equals
  the manifest uid set; `namespace` equals the configured embedder's
  `cache_namespace`; every stored vector has length `dim`. Any violation → unusable.
- Malformed section shapes (missing keys, wrong types) → unusable.

All of these resolve to `load_snapshot()` returning `None` → silent full rebuild.

---

## 6. Embedder / vector rules

The snapshot is usable for incremental load **iff** `version` and `lang` match **and**:

- **No embedder configured:** the `vectors` section is irrelevant. It is **not
  deserialized or validated** — a corrupt `vectors` section does not force a rebuild.
  Structural + search load and reconcile normally.
- **Embedder configured:** the snapshot must carry a `vectors` section whose
  `namespace == embedder.cache_namespace` and whose `dim`/uid-set pass §5. Otherwise the
  whole snapshot is unusable → full rebuild. Rationale: rebuilding vectors needs every
  node's `embed_text`, which means parsing every file anyway, so a model/namespace change
  cleanly forces one full rebuild (a rare event; simplest correct path). During reconcile
  with a matching embedder, vector upserts/drops ride the same diff as structural/search,
  using the corpus's embedder + raw `VectorCache`.

---

## 7. Per-index serialization

Each index owns its `to_dict()` / `from_dict()`.

- **SearchIndex** — persist `postings` (`term → uid → [title_tf, body_tf]`), `lengths`
  (`uid → [title_len, body_len]`), `id_by_uid`. Recompute `_total_title` /
  `_total_body` by summing `lengths` on load (single source of truth; no stored-total
  drift).
- **VectorIndex** — persist `vectors` (uid → normalized vector), `id_by_uid`,
  `hash_by_uid`, `dim`, `namespace`. Avoids re-reading N raw-cache files and
  re-normalizing on every startup.
- **Index (structural)** — persist per entry `{uid, id, kind, deprecated_ids,
  relations, membership_refs}` (the inputs `_extract_out_refs` consumes). On load,
  rebuild `id_to_uid`, `deprecated_to_uid`, `out_refs`, and `in_refs` by **replaying the
  same extraction**.

  **Parity-critical invariant:** the source and target `OutRef`s of one relation must
  share a single `Relation` instance, because `in_refs` dedup keys on `id(relation)`.
  Serialize each relation once per entry and replay extraction on load; never serialize
  the two `OutRef`s independently (that would create two `Relation` objects and break
  inbound/dangling dedup).

---

## 8. Corpus API

- `Corpus.flush_index() -> None` (new): serialize the three live indexes + the current
  in-memory manifest into the snapshot document and write it atomically (`<path>.tmp`
  then `os.replace`, the established pattern). Pure with respect to reads; raises on I/O
  failure (explicit — atomic write means no partial snapshot). When the corpus has no
  embedder, the `vectors` section is written as `null`.
- `Corpus.__init__` gains the load/reconcile behaviour of §4. It still **never writes the
  snapshot**. (The raw `VectorCache` may still write under `.nodes-index/vectors/` during
  `VectorIndex.build`, as today — hence "never writes *the snapshot*".)

---

## 9. Error handling summary

- **Silent → full rebuild** (cache problem, never a correctness risk; every load
  reconciles against current file hashes): snapshot file missing; not valid JSON;
  `version`/`lang` mismatch; integrity failure (§5); embedder-configured vector
  mismatch (§6).
- **Propagates** (corpus problem, not a cache problem): file read errors; frontmatter /
  `ValidationError` on a parsed node; `CollisionError` from the collision contract during
  rebuild or reconcile; `flush_index()` write/I/O errors.

This is the single deliberate exception to the project's "avoid silent fallbacks" rule,
justified by the disposable-cache contract (the same philosophy as the raw `VectorCache`,
whose deletion merely forces re-embedding).

---

## 10. Testing

- **Round-trip equivalence:** build → `flush_index()` → new `Corpus` (loads snapshot) →
  assert every query API (`resolve`, `outbound` / `inbound` / `dangling`, `search`,
  `similar`) is identical to a fresh full-rebuild corpus. Extends the existing
  `test_index_rebuild_equivalence.py` pattern.
- **Reconcile against on-disk mutation:** flush, then mutate files directly on disk —
  add a file, edit a file (content change), edit a file (uid change), delete a file —
  construct a new `Corpus`, assert results equal a from-scratch rebuild and the
  rewritten manifest is correct.
- **rename manifest:** after a `rename()` that moves a node and rewrites referrers,
  `flush_index()` + reload yields results equal to a fresh rebuild (guards §3's referrer
  re-hash and old-path removal).
- **Invalidation → silent rebuild, correct results:** corrupt/truncated JSON; wrong
  `version`; wrong `lang`; embedder-configured vector-namespace mismatch; vector
  dim mismatch.
- **No-embedder tolerance:** a corrupt `vectors` section does not prevent a no-embedder
  `Corpus` from loading structural + search (§6).
- **Error propagation:** a malformed corpus file raises on construction (not swallowed);
  a reconcile that introduces a uid collision raises `CollisionError`.
- **Relation identity:** inbound / dangling dedup is correct after a load (guards §7's
  shared-`Relation` invariant).
- **Integrity guards:** a snapshot with a manifest uid missing from a required section,
  an extra index uid absent from the manifest, or duplicate manifest uids → silent
  rebuild.
- All existing parity tests and frozen fixtures continue to pass unchanged.

---

## 11. Module / file map

- **Create:** `python/src/nodes/kernel/snapshot.py` — `SNAPSHOT_SCHEMA_VERSION`,
  the manifest type, `load_snapshot()`, the file-walk, `reconcile()`/`full_rebuild()`
  helpers, atomic write.
- **Modify:** `python/src/nodes/kernel/index.py`, `search.py`, `similarity.py` — add
  `to_dict()` / `from_dict()`; expose the extraction replay needed by structural
  `from_dict`.
- **Modify:** `python/src/nodes/kernel/corpus.py` — load/reconcile in `__init__`,
  `flush_index()`, in-memory manifest maintenance across `add` / `delete` / `rename`.
- **Docs:** extend `docs/format.md` with an index-persistence subsection.
