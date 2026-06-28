# Nodes TypeScript Index Persistence - Design

**Status:** draft design, written after implementation audit
**Scope:** TypeScript parity for the Python on-disk index-persistence subsystem.

---

## 1. Goal & non-goals

**Goal:** the TypeScript `Corpus` should load a persisted snapshot of the three derived
indexes (`Index`, `SearchIndex`, `VectorIndex`) and reconcile only changed files, matching
the Python persistence behavior while preserving TypeScript API conventions.

Files remain the source of truth. The snapshot is a disposable, private, per-language
cache: deleting it only costs startup time.

**Non-goals:**

- No cross-language snapshot reads. TypeScript reads `snapshot.ts.json`; Python reads
  `snapshot.py.json`.
- No byte-identical snapshot format. TypeScript uses camelCase keys, Python uses
  snake_case keys.
- No auto-flush or lifecycle hook. Snapshot writes are explicit.
- No eviction of raw vector cache files under `.nodes-index/vectors/`.

---

## 2. Architecture

`ts/src/snapshot.ts` owns all snapshot file concerns:

- `snapshotPath(root)` and the `version` / `lang` gate,
- byte hashing and the root-relative POSIX file walk,
- atomic JSON writes,
- snapshot deserialization and integrity validation,
- the manifest shape.

The index classes stay pure data and expose only `toDict()` / `fromDict()` for
serialization. `Corpus` owns load/reconcile/full-rebuild behavior and the in-memory
manifest. `Store.allNodes()` uses the same `iterCorpusFiles()` walker as `Corpus`, so
private `.nodes-index` files never become corpus nodes.

### File layout

```text
<root>/.nodes-index/snapshot.py.json          # Python cache
<root>/.nodes-index/snapshot.ts.json          # TypeScript cache
<root>/.nodes-index/vectors/<ns>/<sha>.json   # shared raw-vector cache namespace layout
```

The snapshot document is language-private, but it represents the same semantic state as
Python:

```json
{
  "version": 1,
  "lang": "ts",
  "manifest": [
    {"path": "gene/PHF19.md", "sha256": "<64 hex>", "uid": "7b2c..."}
  ],
  "structural": {"entries": []},
  "search": {"postings": {}, "lengths": {}, "idByUid": {}},
  "vectors": {"namespace": "fixture-v1", "dim": 4, "vectors": {}, "idByUid": {}, "hashByUid": {}}
}
```

`vectors` is `null` when the corpus has no embedder.

---

## 3. Manifest & file walk

Manifest entries pin indexed files by root-relative POSIX path, sha256 of actual on-disk
bytes, and uid. The load path always hashes bytes read from disk; it never normalizes by
serializing a parsed node. This prevents formatting-only emitter differences from causing
false "unchanged" decisions.

`iterCorpusFiles(root)` is the single TypeScript corpus walk:

- sorted by root-relative POSIX path,
- reads each regular `*.md` file once,
- skips `.nodes-index`, symlinks, directories named `*.md`, and non-files.

Mutation paths keep the manifest live without re-reading:

- `add` records `sha256(nodeToMarkdown(node))` for the file just written.
- `delete` removes the path.
- `rename` removes the old path when the file moves, records the renamed node, and records
  every rewritten referrer because rename rewrites their on-disk bytes.

---

## 4. Load & reconcile

`new Corpus(root, registry?, embedder?)` tries `loadSnapshot(root, namespace)`.

- If the snapshot is absent or unusable, construction falls back to a full rebuild from
  `iterCorpusFiles()`.
- If the snapshot is usable, construction reconciles it against current file hashes.

Reconcile:

1. Deserialize structural, search, and optional vector indexes from the snapshot.
2. Walk current corpus files and hash bytes.
3. Keep unchanged files without parsing.
4. Drop changed/deleted old uids from every live index.
5. Parse changed/added files from the already-read bytes, then upsert them.
6. Rebuild the in-memory manifest from the current byte walk.

Drops happen before upserts, and changed/added nodes enforce the full build collision
contract: duplicate uids raise before insertion, then `assertAddable()` checks identity
collisions.

Construction never writes `snapshot.ts.json`. `corpus.flushIndex()` is the only snapshot
write API; it serializes current indexes plus the current manifest and writes atomically
with `<path>.tmp` followed by rename.

---

## 5. Integrity validation

`loadSnapshot()` validates the cache before returning live index objects:

- `version === 1`, `lang === "ts"`.
- Manifest rows have valid root-relative POSIX `.md` paths, 64-lowercase-hex sha256
  strings, string uids, no duplicate paths, and no duplicate uids.
- Manifest path agrees with the structural live id via `pathForNodeId(id)`.
- Structural entries have valid ids, kind/id agreement, no duplicate uid, no identity
  collisions, valid relation rows, and valid structural ref roles. Relation extraction is
  replayed so source and target `OutRef`s for one relation share the same `Relation`
  object.
- Search `lengths` keys, `idByUid` keys, and manifest uids match. `search.idByUid` must
  equal the structural `{uid -> id}` map. Every postings uid must exist in `lengths`, each
  postings bucket must be non-empty, tf pairs cannot be `[0, 0]`, and field tf cannot
  exceed the stored field length.
- With an embedder, vectors must exist, namespace must match `embedder.cacheNamespace`,
  uid sets across `vectors` / `idByUid` / `hashByUid` must match the manifest, `idByUid`
  must equal structural ids, dimensions must be valid, and stored vectors must be
  L2-normalized.
- Without an embedder, the `vectors` section is ignored and not deserialized.

Malformed cache state makes the snapshot unusable and triggers a full rebuild.

---

## 6. Error handling

The only silent fallback is snapshot-cache unusability inside `loadSnapshot()`: missing file,
invalid JSON, wrong version/lang, failed integrity validation, or embedder/vector namespace
mismatch. This is acceptable because the snapshot is disposable and every load reconciles
against current file hashes.

Corpus errors propagate:

- malformed node frontmatter/body,
- file read errors while walking corpus files,
- collision errors during rebuild or reconcile,
- `flushIndex()` write errors.

This keeps cache repair automatic while still surfacing actual corpus corruption.

---

## 7. Testing

Required coverage:

- Snapshot I/O: path, hashing, atomic write, JSON read semantics, `.nodes-index` exclusion,
  symlink and non-file behavior.
- Per-index round trips and malformed snapshot validation for structural, search, and vector
  indexes.
- `Corpus` round-trip: build -> `flushIndex()` -> reload equals a fresh rebuild.
- Reconcile direct on-disk add/edit/delete and uid-collision cases.
- Rename manifest maintenance, including rewritten referrers.
- No-embedder tolerance for corrupt vectors.
- Store-level `.nodes-index` exclusion for `allNodes()`.
- Full TS gates: `rtk npm test`, `rtk npm run typecheck`, `rtk npm run check`.
