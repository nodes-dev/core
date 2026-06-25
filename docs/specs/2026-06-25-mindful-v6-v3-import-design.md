# Mindful v6 - v3 Import Helper (Design)

**Status:** approved (brainstorming) - ready for planning
**Date:** 2026-06-25
**Repo:** `~/d/mindful/v6` (TS only, no kernel changes planned)
**Specs/plans home:** `~/d/nodes/docs/{specs,plans}/`
**Builds on:** SP1 (thought/mindmap/journal kinds), SP2 (required `visualIdentity`), SP7 (`captured` facet), SP8 (current sprite pipeline)

## 1. Overview

Mindful v6 needs a helper script to import thoughts from Mindful v3 while preserving the clean v6
abstractions. The existing v3-to-v5 path provides useful reference code:

- `~/d/mindful/v5/backend/scripts/mindful_v3_export.py`
- `~/d/mindful/v5/backend/scripts/mindful_v5_import.py`

Those scripts are not a direct fit for v6. They include CouchDB/Redis setup, v5 visual identity
layers, activity tracking, attractor handling, and journal-section expansion. v6 should import the
durable parts that match its model and leave service-era or unmodeled concerns out of this slice.

This design covers a first importer slice:

1. Add a Mindful-owned optional `alias` facet for thoughts.
2. Import v3/v5-export JSON into valid v6 thoughts.
3. Preserve v3 identity as stable v6 node IDs.
4. Preserve aliases/tags where they are valid and unique.
5. Import v3 graph edges and resolved tags as v6 global relations.
6. Fail the whole import before writing anything on malformed input, duplicate aliases, dangling
   references, bad timestamps, or collisions. This is **validation-atomic**: all domain checks pass
   before any write. It is not a filesystem transaction; an unexpected I/O/runtime failure during
   the write loop can still leave earlier nodes on disk.

## 2. Scope

### In

- Optional `alias` facet on `thought`.
- Alias-aware thought/tag/ref resolution in the Mindful API and CLI.
- `src/import-v3.ts` import module with transform, validation, and import helpers.
- `src/bin-import-v3.ts` thin executable wrapper.
- Package `bin` entry for `mindful-import-v3`.
- Dry-run mode that validates and reports without writing.
- Import report with counts and ID mappings.
- Tests for alias behavior and importer validation-atomicity.

### Out

- Direct Postgres export from v3. The existing v5 exporter remains the source for JSON payloads.
- CouchDB, Redis, index-management, and v5 service setup.
- v5 pending visual identity / visual identity layers. v6 derives and stores its own
  `visualIdentity`.
- Activity tracking, interaction counts, heat, momentum, and reviews.
- Attractor flags, visual indexes, themes, and presets.
- v3 journal-section detection and conversion. This is useful, but it deserves a separate design
  because v6 has both a captured-time journal projection and an explicit list-shaped `journal` kind.
- A CLI command for editing aliases after import.
- Compatibility layers for legacy v6 data. v6 is still pre-release.

## 3. Current State

### v6

- `Mindful.capture({ title, body?, tags?, at })` creates a `thought:<newUid()>` node, attaches
  `visualIdentity` and `captured`, resolves tags, and performs one `corpus.add`.
- `thoughtSpec` requires `visualIdentity` and `captured`.
- `Node` has no alias field. Mindful currently resolves tags by title, with duplicate-title
  ambiguity rejected.
- CLI refs resolve exact ID or unique ID prefix, not aliases.
- The kernel registry validates one node at a time. Cross-node uniqueness rules must be enforced by
  Mindful/import APIs, not by a normal kind invariant.
- Storage is Markdown/frontmatter through `Corpus.add`; the importer should use validated v6 nodes,
  not write files by hand.
- Relations are stored on the source node (`node.relations`). There is no public "append relation
  to an existing node" import primitive, and `Corpus.add` is not a merge/update API for arbitrary
  already-present nodes. This constrains imported edge sources: they must be part of the import
  batch.

### v3/v5 Export Shape

The v5 exporter produces JSON with top-level arrays such as:

- `thoughts[]`
- `edges[]`
- `activities[]`
- `structures[]`

Relevant thought fields include:

- `id`: v3 UUID-like identity.
- `title`
- `body`
- `alias`: optional human-readable handle.
- `tag`: optional older/alternate handle.
- `tags[]`: tag names used to link thoughts.
- `time_created`, `time_modified`, and/or `metadata.createdAt` / `metadata.modifiedAt`.

Relevant edge fields include:

- `source`
- `target`
- `relation`
- `weight`
- `type`

## 4. Alias Facet

Add a Mindful-owned optional facet:

```ts
export const ALIAS = "alias";

export type Alias = {
  name: string;
};
```

`src/alias.ts` owns:

- `ALIAS`
- `AliasSchema`
- `Alias` type
- `makeAlias(name): Alias`
- `aliasOf(node): Alias | null`
- `requireValidAlias(node): void`
- `normalizeAliasInput(raw): string`

`makeAlias` is strict: it validates the name it is handed and does not normalize direct v6 API
input. The legacy importer uses `normalizeAliasInput` first, then passes the result into
`makeAlias`. This keeps new v6 writes explicit while still preserving old v3 handles that used
minor formatting variants.

`requireValidAlias` must short-circuit when the facet is absent. It validates only a present alias
facet, matching the optional-facet contract.

### Shape

The stored facet is:

```yaml
facets:
  alias:
    name: garden
```

No leading `#` is stored.

### Validation

If present, the alias facet must be exactly `{ name: string }`. The `name` must match:

```text
^[a-z0-9]+(?:-[a-z0-9]+)*$
```

That is the v5 strict-alias style: lowercase alphanumeric words separated by single hyphens, no
leading/trailing hyphen.

The facet is optional on `thought`. `thoughtSpec` adds `ALIAS` to `optionalFacets` and adds
`requireValidAlias` to invariants. Missing alias is valid.

### Uniqueness

Alias uniqueness is enforced at Mindful boundaries, not by the registry:

- `capture({ ..., alias? })` rejects an alias already used by an existing thought before writing.
- The v3 importer validates aliases against the existing corpus and the incoming batch before any
  write.
- Future alias edit commands should use the same uniqueness helper.

Duplicate aliases fail; the importer never auto-deduplicates or appends suffixes. Aliases are
user-facing identifiers and may back old URLs and tag references.

### Resolution

Alias becomes a first-class resolver input:

- `tag()` and capture tags resolve by alias first.
- If no alias matches, fall back to current title lookup.
- If title fallback is ambiguous, fail early as today.
- CLI refs resolve exact ID, unique ID prefix, then alias.
- Alias match wins over a title match. This gives aliases stable URL/tag semantics even when titles
  duplicate.

Implementation requires replacing the current title-only `aliasIndex()` with an explicit resolver
index:

- `aliases: Map<string, string>` for unique aliases.
- `titles: Map<string, string>` plus `ambiguousTitles: Set<string>` for exact/lowercase title
  fallback.
- Resolution checks `aliases` first, then title maps. This is necessary so an alias can win
  deterministically over a same-string title.

## 5. Importer Architecture

Add a package-local import module and thin executable:

```text
src/import-v3.ts        # transform, validation, importV3(...)
src/bin-import-v3.ts    # executable wrapper: args/env/fs wiring only
tests/import-v3.test.ts
tests/alias.test.ts
```

The import module consumes parsed JSON. It does not connect to Postgres, CouchDB, or Redis. The v5
export script remains the tool for extracting v3 data into JSON.

### Public Module Surface

```ts
export interface ImportV3Options {
  dryRun?: boolean;
  fallbackAt?: string;
}

export interface ImportReport {
  thoughts: number;
  aliases: number;
  relations: number;
  duplicateRelations: number;
  droppedUnsupportedFields: Record<string, number>;
  idMappings: Array<{ sourceId: string; nodeId: string; uid: string }>;
  dryRun: boolean;
}

export function importV3(payload: unknown, mindful: Mindful, options?: ImportV3Options): ImportReport;
```

Additional transform/validation helpers may be exported for tests if useful, but `importV3` is the
main embedding API.

### Validation-Atomic Flow

The importer validates all domain constraints before writing:

1. Parse and validate the input payload shape.
2. Transform all incoming thoughts into complete v6 `Node` objects in memory.
3. Validate alias structure.
4. Validate alias uniqueness within the batch and against existing thoughts.
5. Validate ID/UID uniqueness within the batch.
6. Validate ID/UID collisions against the existing corpus.
7. Build all relations in memory.
8. Validate relation sources and endpoints.
9. Validate every node with the same registry/corpus rules used by normal v6 writes.
10. If `dryRun` is true, return the report and write nothing.
11. Otherwise, write nodes.

A bad thought, alias, timestamp, tag, edge, or collision stops the import before the first disk
write. The implementation does not provide rollback for unexpected filesystem/runtime failures
during the write loop; that residual partial-write risk is accepted for this slice.

## 6. Identity Mapping

Preserve v3 identity.

The default mapping is:

```text
source thought id: 550e8400-e29b-41d4-a716-446655440000
v6 node id:       thought:550e8400e29b41d4a716446655440000
v6 uid:           550e8400e29b41d4a716446655440000
```

If a v3 ID is already a 32-character hex string, it is lowercased and maps directly to
`thought:<id>` and `uid: <id>`.

If a v3 ID is UUID-like, hyphens are stripped, the result is lowercased, and the result must be 32
hex characters.

If a source ID cannot be normalized into a valid 32-character lowercase hex value, the import fails.
This keeps import deterministic and avoids inventing hidden fallback IDs.

`visualIdentity` is derived from the preserved `uid` via `deriveIdentity(uid)`, matching normal v6
semantics. Legacy v5 visual identity fields are ignored.

The import report records every `{ sourceId, nodeId, uid }` mapping.

## 7. Thought Field Mapping

For each imported thought:

| v3/v5 field | v6 mapping |
| --- | --- |
| `id` | `thought:<normalized-id>` and `uid: <normalized-id>` |
| `title` | `node.title`; missing/blank becomes `"Untitled"` |
| `body` | `node.body`; missing becomes `""` |
| `alias` | `facets.alias.name` if present and valid |
| `tag` | fallback alias source if `alias` is absent |
| `time_created` | preferred source for `captured.at` |
| `metadata.createdAt` | fallback source for `captured.at` |
| `time_modified`, `metadata.modifiedAt` | not imported in this slice |
| visual identity fields | ignored; v6 derives its own |
| activity / attractor fields | ignored |

### Alias Source

Alias source order:

1. `alias`
2. `tag`
3. none

The importer normalizes an input alias the same way v5 strict import did for user-facing handles:

- lowercase
- replace underscores and Unicode en/em dashes with hyphen
- strip non-alphanumeric/hyphen characters
- collapse repeated hyphens
- trim leading/trailing hyphens

If the resulting alias is empty, the import fails. If normalization changes the source alias, the
report records that as an imported alias count but the spec does not require a per-alias warning
unless the plan chooses to add one.

### Timestamp Source

`captured.at` comes from the first usable source:

1. `time_created`
2. `metadata.createdAt`
3. `fallbackAt` option

`fallbackAt` is required only if any thought lacks a usable creation timestamp.

Accepted timestamp inputs:

- ISO datetimes with explicit offset, including `Z`.
- ISO datetimes without offset: interpreted as UTC and serialized with `Z`.
- `YYYY-MM-DD`: interpreted as `YYYY-MM-DDT00:00:00Z`.

The stored output must pass `CapturedSchema`, including seconds and an explicit offset.

`metadata.created` is set to `capturedDate(captured.at)`. `metadata.updated` stays `null` in this
slice.

Data-fidelity caveat: offset-less v3 datetimes may have represented local wall time. This importer
does not infer historical local timezone; it treats naive datetimes as UTC to keep the transform
deterministic and explicit.

## 8. Relations and Tags

### Edges

Import `edges[]` as global `Node.relations` attached to the source thought.

Mapping:

| v3/v5 edge field | v6 relation field |
| --- | --- |
| `source` | relation source, normalized to v6 thought ID |
| `target` | relation target, normalized to v6 thought ID |
| `relation` | `predicate`; missing defaults to `relatesTo` |
| `weight` | preserved if finite; otherwise `null` |
| `type` | ignored |

Only relations whose endpoints resolve to imported or already-existing thoughts are valid. A
dangling endpoint fails the import before writing.

The relation source must be part of the import batch. Targets may be imported thoughts or existing
corpus thoughts. If an edge's source resolves only to an already-existing corpus thought, the import
fails before writing because this slice does not introduce a merge/update path for existing source
nodes.

Duplicate `(source, predicate, target)` relations are collapsed in memory. The report increments
`duplicateRelations` for duplicates skipped.

`type` is ignored for relation semantics. Unsupported edge `type` values are counted in
`droppedUnsupportedFields` so the loss is visible in dry-run and import reports.

Imported edges are global semantic relations. They never become mindmap `edges` form facets. This
preserves the v6 distinction between the global relation graph and structure-local form edges.

### Tags

If an imported thought has `tags[]`, each tag string is resolved through the same alias/title
resolver used by `Mindful.tag`:

1. Alias match.
2. Title match.
3. Ambiguous title: fail.
4. No match: fail.

Resolved tags become global `relatesTo` relations from the tagged thought to the resolved target
thought.

Generated tag relations and explicit edge relations are deduplicated together.

Tag relation sources are always imported thoughts, because the tag list lives on an imported
thought record.

## 9. CLI Wrapper

Add a second package binary:

```json
{
  "bin": {
    "mindful": "dist/bin.js",
    "mindful-import-v3": "dist/bin-import-v3.js"
  }
}
```

Command:

```text
mindful-import-v3 <export.json> [--dry-run] [--fallback-at <iso-offset>]
```

Behavior:

- Resolves the corpus root using the existing `resolveDataDir(env)` helper.
- Constructs `new Mindful(root)`.
- Reads and parses the JSON file.
- Calls `importV3(payload, mindful, { dryRun, fallbackAt })`.
- Prints a compact report.
- Exits `0` on success.
- Exits `1` on validation/domain errors.
- Exits `2` on usage errors.

The wrapper is intentionally thin and mirrors the existing `bin.ts` / `runCli` separation. Tests
drive the import module directly, not through subprocesses.

## 10. Error Model

Fail early, no silent repair:

- Malformed payload: fail.
- Invalid source ID: fail.
- ID/UID collision within the batch or with existing corpus: fail.
- Invalid alias: fail.
- Duplicate alias in batch or existing corpus: fail.
- Bad timestamp with no usable fallback: fail.
- Dangling edge endpoint: fail.
- Edge source resolves only to an existing, non-batch thought: fail.
- Dangling tag target: fail.
- Ambiguous title fallback for a tag: fail.
- Registry validation failure: fail.

No write occurs until all checks pass. Dry-run performs the same checks and writes nothing.

## 11. Testing Strategy

### `alias.test.ts`

- Missing alias facet is valid on a thought.
- Valid alias facet passes.
- Malformed alias facet throws.
- Invalid names reject: uppercase, underscores, spaces, leading/trailing hyphen, repeated hyphen,
  empty string.
- `Mindful.capture({ alias })` stores the facet.
- `Mindful.capture({ alias })` rejects invalid aliases instead of normalizing them.
- Duplicate alias through `capture` fails before writing.
- `tag()` resolves by alias.
- Alias wins over title.
- CLI `show <alias>` resolves a thought.

### `import-v3.test.ts`

- Dry-run validates a payload and writes nothing.
- Import preserves v3 UUID identity as `thought:<uuid-without-hyphens>` and `uid`.
- Import stores `captured`, `visualIdentity`, optional alias, title, body, and `metadata.created`.
- Import maps explicit edges to global relations.
- Import maps `tags[]` through alias/title resolution.
- Duplicate explicit/tag relations are collapsed and counted.
- Duplicate aliases fail before any write.
- Invalid aliases fail before any write.
- Within-batch ID/UID collisions fail before any write.
- Uppercase UUID/hex source IDs normalize to lowercase.
- Dangling edge endpoint fails before any write.
- Edge whose source is existing-only fails before any write.
- Dangling tag target fails before any write.
- Missing timestamp requires `fallbackAt`.
- Date-only and naive timestamps normalize to explicit UTC.
- Existing ID/UID collision fails before writing.
- Existing alias collision fails before writing.
- Unsupported v5 fields are ignored and counted in the report.

### Gate

Same package gate as recent SPs:

```text
rtk npm test
rtk npm run typecheck
rtk npm run check
rtk npm run build
```

## 12. Alternatives Considered

### Core import + alias facet + relations (chosen)

This imports the durable identity, handle, text, time, and graph information while keeping v6 free
of v5 infrastructure. It is the smallest slice that preserves the useful semantic graph.

### Full v3 semantic lift

This would also port journal-section expansion, activity fields, and possibly attractor state.
Rejected for this slice because it mixes import mechanics with new v6 domain modeling. Journal
section expansion may still be valuable, but it should be designed separately against v6's current
journal projection and list-shaped `journal` kind.

### Minimal thoughts-only importer

This would skip edges and tags. Rejected because v3's relation graph is core Mindful data, and v6
already has a clean global relation primitive.

### Auto-deduplicate aliases

Rejected. Aliases are user-facing identifiers and may back old URLs and tags. Silent suffixing would
make imported references surprising.

## 13. Decisions Log

1. Preserve v3 IDs as v6 thought IDs where possible.
2. Normalize UUID source IDs by stripping hyphens.
3. Lowercase normalized UUID/hex source IDs.
4. Use the normalized v3 ID as both v6 `uid` and the id suffix.
5. Add alias as an optional Mindful-owned thought facet, not a kernel field.
6. Alias is unique when present.
7. Alias uniqueness is enforced at Mindful/import boundaries.
8. Duplicate aliases fail the whole import before writing.
9. Alias/tag source precedence is `alias` then `tag` then none.
10. Tags resolve by alias first, then title.
11. Imported v3 edges become global relations, not mindmap form edges.
12. Imported edge sources must be in the import batch; targets may be existing thoughts.
13. v5 visual/activity/attractor fields are ignored in this slice.
14. Journal-section expansion is deferred to a separate design.
15. The importer consumes JSON exports only; it does not connect to v3 Postgres or v5 CouchDB.
16. Dry-run performs full validation and writes nothing.
17. The import is validation-atomic: domain failures produce no disk writes, while unexpected
    I/O/runtime failures during the write loop remain a residual partial-write risk.
