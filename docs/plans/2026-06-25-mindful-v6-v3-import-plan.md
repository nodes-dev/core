# Mindful v6 - v3 Import Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an alias-aware v6 thought model and a validation-atomic helper for importing Mindful v3/v5-export JSON into `~/d/mindful/v6`.

**Architecture:** Implement alias as an optional Mindful-owned thought facet, then restructure Mindful resolution so aliases win over title fallback for tags and CLI refs. The importer consumes parsed JSON, transforms it into fully valid v6 nodes in memory, validates batch/corpus collisions and relation integrity before any write, and writes through `Corpus.add` only after all domain checks pass. A thin `mindful-import-v3` executable handles argv/env/fs wiring.

**Tech Stack:** TypeScript ESM (`.js` import specifiers), zod, `@nodes/kernel`, yaml/frontmatter storage via `Corpus`, Node built-ins (`node:fs`, `node:util`, `node:path`), vitest, biome. Tooling through `rtk`.

**Spec:** `~/d/nodes/docs/specs/2026-06-25-mindful-v6-v3-import-design.md` (committed through `2d49296`).

---

## Global Constraints

- Work in `~/d/mindful/v6`; no kernel changes.
- Use `rtk` wrappers for commands.
- Preserve v3 source IDs as `thought:<normalized-id>` and `uid: <normalized-id>`, where normalization is `strip hyphens -> lowercase -> assert /^[0-9a-f]{32}$/`.
- Alias facet is optional. When present, shape is strict `{ name: string }`, and name must match `^[a-z0-9]+(?:-[a-z0-9]+)*$`.
- Direct v6 API writes are strict: `capture({ alias })` validates the supplied alias and does not normalize it.
- Legacy import normalizes `alias`/`tag` input before strict validation.
- Alias uniqueness is enforced at Mindful/import boundaries, not in the registry.
- Resolver order: alias first, then title fallback. Alias wins over same-string titles.
- Import is validation-atomic: all domain validation completes before any disk write. Do not promise rollback for unexpected I/O/runtime failures during the write loop.
- Imported explicit edge sources must be in the import batch. Targets may be in the batch or already existing.
- Tags on imported thoughts become global `relatesTo` relations and always have imported sources.
- Ignore v5 visual/activity/attractor fields; count unsupported fields in the import report.
- Gate from `~/d/mindful/v6`: `rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`.

## File Structure

- Create `src/alias.ts`: alias facet schema, loaders, normalizer.
- Modify `src/kinds.ts`: mark alias as optional and validate when present.
- Modify `src/index.ts`: export alias and importer public surfaces.
- Modify `src/api.ts`: alias-aware capture input, uniqueness checks, resolver index, tag resolution.
- Modify `src/cli.ts`: CLI ref resolution by alias.
- Create `src/import-v3.ts`: payload parsing, transformation, validation-atomic import, report generation.
- Create `src/bin-import-v3.ts`: thin executable for `mindful-import-v3`.
- Modify `package.json`: add bin entry for `mindful-import-v3`.
- Create `tests/alias.test.ts`: facet/API/CLI alias behavior.
- Create `tests/import-v3.test.ts`: importer transform, validation, relations, dry-run behavior.

---

### Task 1: Alias Facet Module and Thought Registration

**Files:**
- Create: `src/alias.ts`
- Modify: `src/kinds.ts`
- Modify: `src/index.ts`
- Test: `tests/alias.test.ts`

**Purpose:** Introduce the optional `alias` facet and make the `thought` kind accept/validate it. Do not change `Mindful.capture` yet.

- [ ] **Step 1: Write the failing alias facet tests**

Create `tests/alias.test.ts` with the facet-only tests first:

```ts
import { FacetError, ValidationError, makeNode } from "@nodes/kernel";
import { describe, expect, it } from "vitest";
import {
	ALIAS,
	AliasSchema,
	aliasOf,
	makeAlias,
	normalizeAliasInput,
	requireValidAlias,
} from "../src/alias.js";

describe("alias facet", () => {
	it("accepts a valid alias", () => {
		expect(AliasSchema.safeParse({ name: "garden-notes-2026" }).success).toBe(true);
		expect(makeAlias("garden-notes-2026")).toEqual({ name: "garden-notes-2026" });
	});

	it("rejects malformed alias names", () => {
		for (const name of ["", "Garden", "garden_notes", "garden notes", "-garden", "garden-", "garden--notes"]) {
			expect(AliasSchema.safeParse({ name }).success).toBe(false);
			expect(() => makeAlias(name)).toThrow(ValidationError);
		}
	});

	it("rejects extra keys", () => {
		expect(AliasSchema.safeParse({ name: "garden", extra: true }).success).toBe(false);
	});

	it("returns null when the optional facet is absent", () => {
		const node = makeNode({ id: "thought:a", kind: "thought", title: "A" });
		expect(aliasOf(node)).toBeNull();
		expect(() => requireValidAlias(node)).not.toThrow();
	});

	it("loads a present alias facet", () => {
		const node = makeNode({
			id: "thought:a",
			kind: "thought",
			title: "A",
			facets: { [ALIAS]: { name: "garden" } },
		});
		expect(aliasOf(node)).toEqual({ name: "garden" });
		expect(() => requireValidAlias(node)).not.toThrow();
	});

	it("throws FacetError for malformed stored alias facets", () => {
		const node = makeNode({
			id: "thought:a",
			kind: "thought",
			title: "A",
			facets: { [ALIAS]: { name: "Garden" } },
		});
		expect(() => aliasOf(node)).toThrow(FacetError);
		expect(() => requireValidAlias(node)).toThrow(FacetError);
	});

	it("normalizes legacy alias input for importer use", () => {
		expect(normalizeAliasInput("Garden Notes")).toBe("gardennotes");
		expect(normalizeAliasInput("Garden_Notes")).toBe("garden-notes");
		expect(normalizeAliasInput("Garden—Notes")).toBe("garden-notes");
		expect(normalizeAliasInput("  --Garden!!Notes--  ")).toBe("gardennotes");
	});
});
```

- [ ] **Step 2: Run the new test and verify it fails**

Run: `rtk npx vitest run tests/alias.test.ts`

Expected: FAIL with a module resolution error for `../src/alias.js`.

- [ ] **Step 3: Implement `src/alias.ts`**

Create `src/alias.ts`:

```ts
import { FacetError, type Node, ValidationError } from "@nodes/kernel";
import { z } from "zod";

export const ALIAS = "alias";

const ALIAS_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export const AliasSchema = z
	.object({
		name: z.string().regex(ALIAS_RE, "alias must be lowercase alphanumeric words separated by single hyphens"),
	})
	.strict();

export type Alias = z.infer<typeof AliasSchema>;

function zodMessages(error: z.ZodError): string {
	return error.issues.map((issue) => issue.message).join("; ");
}

/** Strict constructor for new v6 writes. Does not normalize. */
export function makeAlias(name: string): Alias {
	const result = AliasSchema.safeParse({ name });
	if (!result.success) throw new ValidationError(`invalid '${ALIAS}' facet: ${zodMessages(result.error)}`);
	return result.data;
}

/** Load the optional alias facet. Missing is valid; malformed present data is a facet error. */
export function aliasOf(node: Node): Alias | null {
	const raw = node.facets[ALIAS];
	if (raw === undefined) return null;
	const result = AliasSchema.safeParse(raw);
	if (!result.success) {
		throw new FacetError(`${node.id}: invalid '${ALIAS}' facet: ${zodMessages(result.error)}`);
	}
	return result.data;
}

/** Kind-level invariant for optional alias: short-circuits on absence, validates when present. */
export function requireValidAlias(node: Node): void {
	aliasOf(node);
}

/** Legacy importer normalizer. Mirrors the v5 strict import path: lowercase, replace underscores
 * and en/em dashes with hyphen, strip all other non-alphanumeric/hyphen chars, collapse hyphens,
 * trim hyphens. */
export function normalizeAliasInput(raw: string): string {
	return raw
		.toLowerCase()
		.trim()
		.replace(/[\u2013\u2014_]/g, "-")
		.replace(/[^a-z0-9-]/g, "")
		.replace(/-+/g, "-")
		.replace(/^-+|-+$/g, "");
}
```

- [ ] **Step 4: Register alias as an optional thought facet**

Modify `src/kinds.ts`:

```ts
import type { KindSpec } from "@nodes/kernel";
import { ALIAS, requireValidAlias } from "./alias.js";
import { CAPTURED, requireValidCaptured } from "./captured.js";
import { VISUAL_IDENTITY, requireValidVisualIdentity } from "./identity.js";

export const THOUGHT = "thought";
export const MINDMAP = "mindmap";
export const JOURNAL = "journal";

// thought (≈ note) requires intrinsic visual identity and capture timestamp facets.
// Alias is optional, but if present it is strictly validated.
export const thoughtSpec: KindSpec = {
	name: THOUGHT,
	requiredFacets: new Set([VISUAL_IDENTITY, CAPTURED]),
	optionalFacets: new Set([ALIAS]),
	invariants: [requireValidVisualIdentity, requireValidCaptured, requireValidAlias],
};

// mindmap/journal: first-class kinds adopting the kernel's graph/list shapes.
export const mindmapSpec: KindSpec = { name: MINDMAP, shape: "graph" };
export const journalSpec: KindSpec = { name: JOURNAL, shape: "list" };
```

- [ ] **Step 5: Export the alias surface**

Modify `src/index.ts` to add:

```ts
export {
	ALIAS,
	AliasSchema,
	type Alias,
	aliasOf,
	makeAlias,
	normalizeAliasInput,
	requireValidAlias,
} from "./alias.js";
```

- [ ] **Step 6: Run the alias facet test**

Run: `rtk npx vitest run tests/alias.test.ts`

Expected: PASS.

- [ ] **Step 7: Run focused profile tests**

Run: `rtk npx vitest run tests/profile.test.ts tests/mindful-thoughts.test.ts`

Expected: PASS. Existing thoughts without alias remain valid because alias is optional.

- [ ] **Step 8: Commit Task 1**

```bash
rtk git add src/alias.ts src/kinds.ts src/index.ts tests/alias.test.ts
rtk git commit -m "feat: add optional alias facet"
```

---

### Task 2: Alias-Aware Mindful API and CLI Resolution

**Files:**
- Modify: `src/api.ts`
- Modify: `src/cli.ts`
- Test: `tests/alias.test.ts`
- Test: `tests/cli.test.ts`

**Purpose:** Add `capture({ alias? })`, enforce alias uniqueness, resolve tags by alias before title, and resolve CLI refs by alias.

- [ ] **Step 1: Append API alias behavior tests**

First update the import block at the top of `tests/alias.test.ts` so it includes every symbol used by both the Task 1 facet tests and the new API tests:

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { FacetError, RefError, ValidationError, makeNode } from "@nodes/kernel";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Mindful } from "../src/api.js";
import { CAPTURE_AT } from "./fixtures.js";
import {
	ALIAS,
	AliasSchema,
	aliasOf,
	makeAlias,
	normalizeAliasInput,
	requireValidAlias,
} from "../src/alias.js";
```

Then append these tests to `tests/alias.test.ts`:

```ts
describe("Mindful alias API", () => {
	let root: string;
	let mindful: Mindful;

	beforeEach(() => {
		root = mkdtempSync(join(tmpdir(), "mindful-alias-"));
		mindful = new Mindful(root);
	});

	afterEach(() => rmSync(root, { recursive: true, force: true }));

	it("capture stores a strict alias facet", () => {
		const node = mindful.capture({ at: CAPTURE_AT, title: "Garden", alias: "garden" });
		expect(aliasOf(mindful.get(node.id))).toEqual({ name: "garden" });
	});

	it("capture rejects invalid aliases instead of normalizing them", () => {
		expect(() => mindful.capture({ at: CAPTURE_AT, title: "Garden", alias: "Garden Notes" })).toThrow(
			ValidationError,
		);
		expect(mindful.allThoughts()).toEqual([]);
	});

	it("capture rejects duplicate aliases before writing", () => {
		const first = mindful.capture({ at: CAPTURE_AT, title: "First", alias: "garden" });
		expect(() => mindful.capture({ at: CAPTURE_AT, title: "Second", alias: "garden" })).toThrow(ValidationError);
		expect(mindful.allThoughts().map((n) => n.id)).toEqual([first.id]);
	});

	it("tag resolves by alias first", () => {
		const target = mindful.capture({ at: CAPTURE_AT, title: "Long Human Title", alias: "garden" });
		const note = mindful.capture({ at: CAPTURE_AT, title: "Note" });
		mindful.tag(note.id, "garden");
		expect(mindful.related(note.id).map((n) => n.id)).toEqual([target.id]);
	});

	it("alias wins over a same-string title", () => {
		const aliasTarget = mindful.capture({ at: CAPTURE_AT, title: "Alias Target", alias: "garden" });
		mindful.capture({ at: CAPTURE_AT, title: "garden" });
		const note = mindful.capture({ at: CAPTURE_AT, title: "Note" });
		mindful.tag(note.id, "garden");
		expect(mindful.related(note.id).map((n) => n.id)).toEqual([aliasTarget.id]);
	});

	it("title fallback still fails when ambiguous", () => {
		mindful.capture({ at: CAPTURE_AT, title: "Recipes" });
		mindful.capture({ at: CAPTURE_AT, title: "Recipes" });
		const note = mindful.capture({ at: CAPTURE_AT, title: "Note" });
		expect(() => mindful.tag(note.id, "Recipes")).toThrow(ValidationError);
	});

	it("missing alias/title target still throws RefError", () => {
		const note = mindful.capture({ at: CAPTURE_AT, title: "Note" });
		expect(() => mindful.tag(note.id, "missing")).toThrow(RefError);
	});
});
```

- [ ] **Step 2: Append CLI alias resolution tests**

Append this test inside the existing `describe("runCli — dispatch + no-flag commands", ...)` block in `tests/cli.test.ts`:

```ts
	it("show resolves an alias ref", () => {
		const t = m.capture({ at: CAPTURE_AT, title: "Garden", alias: "garden" });
		expect(run("show", "garden")).toBe(0);
		expect(stdout()).toContain(`id: ${t.id}`);
	});
```

- [ ] **Step 3: Run tests and verify failure**

Run: `rtk npx vitest run tests/alias.test.ts tests/cli.test.ts`

Expected: FAIL. TypeScript/test failure should show `alias` is not accepted by `capture`, duplicate aliases are not enforced, or CLI alias refs do not resolve.

- [ ] **Step 4: Replace the resolver index in `src/api.ts`**

Modify imports and helper types in `src/api.ts`:

```ts
import { ALIAS, aliasOf, makeAlias } from "./alias.js";
```

Replace the current `AliasIndex` interface and `aliasIndex()` / `resolveTag()` methods with:

```ts
interface ResolverIndex {
	aliases: Map<string, string>;
	titles: Map<string, string>;
	ambiguousTitles: Set<string>;
}

function addTitleKey(byTitle: Map<string, Set<string>>, key: string, id: string): void {
	const ids = byTitle.get(key) ?? new Set<string>();
	ids.add(id);
	byTitle.set(key, ids);
}

private resolverIndex(extra?: Node): ResolverIndex {
	const aliases = new Map<string, string>();
	const byTitle = new Map<string, Set<string>>();
	for (const n of [...this.corpus.all(), ...(extra === undefined ? [] : [extra])]) {
		if (n.kind !== THOUGHT) continue;
		const alias = aliasOf(n);
		if (alias !== null) aliases.set(alias.name, n.id);
		addTitleKey(byTitle, n.title, n.id);
		addTitleKey(byTitle, n.title.toLowerCase(), n.id);
	}
	const titles = new Map<string, string>();
	const ambiguousTitles = new Set<string>();
	for (const [key, ids] of byTitle) {
		if (ids.size === 1) titles.set(key, [...ids][0]);
		else ambiguousTitles.add(key);
	}
	return { aliases, titles, ambiguousTitles };
}

private resolveThoughtName(name: string, idx: ResolverIndex): string {
	const aliasTarget = idx.aliases.get(name) ?? idx.aliases.get(name.toLowerCase());
	if (aliasTarget !== undefined) return aliasTarget;

	const titleTarget = idx.titles.get(name) ?? idx.titles.get(name.toLowerCase());
	if (titleTarget !== undefined) return titleTarget;

	const lower = name.toLowerCase();
	if (idx.ambiguousTitles.has(name) || idx.ambiguousTitles.has(lower)) {
		throw new ValidationError(`ambiguous tag ${JSON.stringify(name)}: multiple thoughts share that title`);
	}
	throw new RefError(`tag ${JSON.stringify(name)} does not resolve to a known node`);
}

private resolveTag(source: string, name: string, idx: ResolverIndex): Relation {
	return { source, predicate: RELATES_TO, target: this.resolveThoughtName(name.replace(/^#+/, ""), idx), directed: true, weight: null, attrs: {} };
}

private requireUniqueAlias(aliasName: string): void {
	const idx = this.resolverIndex();
	if (idx.aliases.has(aliasName)) {
		throw new ValidationError(`alias ${JSON.stringify(aliasName)} is already in use`);
	}
}
```

Also import `RefError` from `@nodes/kernel` in the top import list:

```ts
	RefError,
```

Remove the no-longer-used `tagToRelation` import.

- [ ] **Step 5: Update `capture` signature and implementation**

Replace the `capture` method in `src/api.ts` with:

```ts
	capture(input: { title: string; body?: string; tags?: string[]; at: string; alias?: string }): Node {
		const node = makeNode({ id: `${THOUGHT}:${newUid()}`, kind: THOUGHT, title: input.title, body: input.body ?? "" });
		// Intrinsic visual identity, derived from the immutable uid (NOT the id slug). Attached before
		// any tag resolution so the single write below persists a complete, valid thought.
		node.facets[VISUAL_IDENTITY] = deriveIdentity(node.uid);
		node.facets[CAPTURED] = makeCaptured(input.at);
		if (input.alias !== undefined) {
			const alias = makeAlias(input.alias); // strict: direct v6 writes are not normalized
			this.requireUniqueAlias(alias.name);
			node.facets[ALIAS] = alias;
		}
		node.metadata.created = capturedDate(input.at);
		const idx = this.resolverIndex(node);
		for (const name of input.tags ?? []) node.relations.push(this.resolveTag(node.id, name, idx));
		this.corpus.add(node); // one write; nothing persists if alias/tag validation above threw
		return this.corpus.get(node.id);
	}
```

- [ ] **Step 6: Update `tag` to use the new resolver**

Ensure `tag()` still calls `this.resolveTag(node.id, name, this.resolverIndex())`:

```ts
	tag(thoughtId: string, name: string): Node {
		const node = this.corpus.get(thoughtId);
		node.relations.push(this.resolveTag(node.id, name, this.resolverIndex()));
		this.corpus.add(node);
		return this.corpus.get(thoughtId);
	}
```

- [ ] **Step 7: Make CLI `resolveId` alias-aware**

Modify imports in `src/cli.ts`:

```ts
import { aliasOf } from "./alias.js";
```

Replace `resolveId` in `src/cli.ts` with:

```ts
function resolveId(mindful: Mindful, ref: string): string {
	const thoughts = mindful.allThoughts();
	const exact = thoughts.find((t) => t.id === ref);
	if (exact !== undefined) return exact.id;

	const prefixMatches = thoughts.filter((t) => t.id.startsWith(ref) || t.id.startsWith(`thought:${ref}`));
	if (prefixMatches.length === 1) return prefixMatches[0].id;
	if (prefixMatches.length > 1) throw new CliError(`ambiguous ref ${JSON.stringify(ref)}: matches ${prefixMatches.length} thoughts`);

	const aliasMatches = thoughts.filter((t) => aliasOf(t)?.name === ref);
	if (aliasMatches.length === 1) return aliasMatches[0].id;
	if (aliasMatches.length > 1) throw new CliError(`ambiguous alias ${JSON.stringify(ref)}: matches ${aliasMatches.length} thoughts`);

	throw new CliError(`no thought matching ${JSON.stringify(ref)}`);
}
```

The ambiguous-alias branch should be unreachable through normal APIs, but it keeps CLI behavior explicit for manually corrupted data.

- [ ] **Step 8: Run focused tests**

Run: `rtk npx vitest run tests/alias.test.ts tests/cli.test.ts tests/mindful-thoughts.test.ts`

Expected: PASS.

- [ ] **Step 9: Typecheck**

Run: `rtk npm run typecheck`

Expected: PASS. If TypeScript complains about imports or optional chaining, fix the exact files from this task.

- [ ] **Step 10: Commit Task 2**

```bash
rtk git add src/api.ts src/cli.ts tests/alias.test.ts tests/cli.test.ts
rtk git commit -m "feat: resolve thoughts by alias"
```

---

### Task 3: Import Core - Payload, IDs, Timestamps, Aliases, Dry-Run

**Files:**
- Create: `src/import-v3.ts`
- Modify: `src/index.ts`
- Test: `tests/import-v3.test.ts`

**Purpose:** Add the importer module with validation-atomic thought import, ID preservation, timestamp normalization, alias normalization/uniqueness, unsupported-field counting, and dry-run behavior. Explicit edges/tags are added in Task 4.

- [ ] **Step 1: Write core importer tests**

Create `tests/import-v3.test.ts`:

```ts
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CollisionError, ValidationError } from "@nodes/kernel";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { aliasOf } from "../src/alias.js";
import { Mindful } from "../src/api.js";
import { CAPTURED } from "../src/captured.js";
import { VISUAL_IDENTITY } from "../src/identity.js";
import { importV3, normalizeV3Id, normalizeV3Timestamp } from "../src/import-v3.js";

const UUID_A = "550e8400-e29b-41d4-a716-446655440000";
const UUID_B = "550e8400-e29b-41d4-a716-446655440001";
const ID_A = "550e8400e29b41d4a716446655440000";
const ID_B = "550e8400e29b41d4a716446655440001";

function payload(thoughts: unknown[], extra: Record<string, unknown> = {}) {
	return { generated_at: "2026-06-25T00:00:00Z", thoughts, edges: [], activities: [], structures: [], ...extra };
}

describe("v3 import helpers", () => {
	it("normalizes UUID and hex ids by stripping hyphens and lowercasing", () => {
		expect(normalizeV3Id("550E8400-E29B-41D4-A716-446655440000")).toBe(ID_A);
		expect(normalizeV3Id("550E8400E29B41D4A716446655440000")).toBe(ID_A);
	});

	it("rejects source ids that cannot normalize to 32 hex chars", () => {
		expect(() => normalizeV3Id("not-a-uuid")).toThrow(ValidationError);
	});

	it("normalizes timestamps to captured-compatible explicit UTC when needed", () => {
		expect(normalizeV3Timestamp("2026-06-24T12:30:00Z")).toBe("2026-06-24T12:30:00Z");
		expect(normalizeV3Timestamp("2026-06-24T12:30:00")).toBe("2026-06-24T12:30:00Z");
		expect(normalizeV3Timestamp("2026-06-24")).toBe("2026-06-24T00:00:00Z");
	});
});

describe("importV3 core thoughts", () => {
	let root: string;
	let mindful: Mindful;

	beforeEach(() => {
		root = mkdtempSync(join(tmpdir(), "mindful-import-v3-"));
		mindful = new Mindful(root);
	});

	afterEach(() => rmSync(root, { recursive: true, force: true }));

	it("dry-run validates and writes nothing", () => {
		const report = importV3(
			payload([{ id: UUID_A, title: "Garden", body: "body", alias: "garden", time_created: "2026-06-24T12:00:00Z" }]),
			mindful,
			{ dryRun: true },
		);
		expect(report).toMatchObject({ thoughts: 1, aliases: 1, relations: 0, duplicateRelations: 0, dryRun: true });
		expect(report.idMappings).toEqual([{ sourceId: UUID_A, nodeId: `thought:${ID_A}`, uid: ID_A }]);
		expect(mindful.allThoughts()).toEqual([]);
	});

	it("imports a thought with preserved id/uid, captured, visualIdentity, alias, title, body, and metadata.created", () => {
		const report = importV3(
			payload([{ id: UUID_A, title: "Garden", body: "body", alias: "Garden_Notes", time_created: "2026-06-24T12:00:00Z" }]),
			mindful,
		);
		expect(report).toMatchObject({ thoughts: 1, aliases: 1, relations: 0, dryRun: false });
		const node = mindful.get(`thought:${ID_A}`);
		expect(node.uid).toBe(ID_A);
		expect(node.title).toBe("Garden");
		expect(node.body).toBe("body");
		expect(node.metadata.created).toBe("2026-06-24");
		expect(node.metadata.updated).toBeNull();
		expect(node.facets[CAPTURED]).toEqual({ at: "2026-06-24T12:00:00Z" });
		expect(node.facets[VISUAL_IDENTITY]).toBeDefined();
		expect(aliasOf(node)).toEqual({ name: "garden-notes" });
	});

	it("uses tag as alias source when alias is absent", () => {
		importV3(payload([{ id: UUID_A, title: "Garden", tag: "garden", time_created: "2026-06-24" }]), mindful);
		expect(aliasOf(mindful.get(`thought:${ID_A}`))).toEqual({ name: "garden" });
	});

	it("uses fallbackAt when creation timestamp is missing", () => {
		importV3(payload([{ id: UUID_A, title: "Garden" }]), mindful, { fallbackAt: "2026-06-24T08:00:00Z" });
		expect(mindful.get(`thought:${ID_A}`).facets[CAPTURED]).toEqual({ at: "2026-06-24T08:00:00Z" });
	});

	it("fails when timestamp is missing and fallbackAt is absent", () => {
		expect(() => importV3(payload([{ id: UUID_A, title: "Garden" }]), mindful)).toThrow(ValidationError);
		expect(mindful.allThoughts()).toEqual([]);
	});

	it("fails on duplicate aliases before writing", () => {
		expect(() =>
			importV3(
				payload([
					{ id: UUID_A, title: "A", alias: "dup", time_created: "2026-06-24T12:00:00Z" },
					{ id: UUID_B, title: "B", alias: "dup", time_created: "2026-06-24T12:00:00Z" },
				]),
				mindful,
			),
		).toThrow(ValidationError);
		expect(mindful.allThoughts()).toEqual([]);
	});

	it("fails on existing alias collision before writing", () => {
		mindful.capture({ at: "2026-06-24T12:00:00Z", title: "Existing", alias: "garden" });
		expect(() =>
			importV3(payload([{ id: UUID_A, title: "Garden", alias: "garden", time_created: "2026-06-24T12:00:00Z" }]), mindful),
		).toThrow(ValidationError);
		expect(mindful.allThoughts().map((n) => n.title)).toEqual(["Existing"]);
	});

	it("fails on within-batch id/uid collision before writing", () => {
		expect(() =>
			importV3(
				payload([
					{ id: UUID_A, title: "A", time_created: "2026-06-24T12:00:00Z" },
					{ id: ID_A, title: "B", time_created: "2026-06-24T12:00:00Z" },
				]),
				mindful,
			),
		).toThrow(ValidationError);
		expect(mindful.allThoughts()).toEqual([]);
	});

	it("fails on existing id/uid collision before writing", () => {
		importV3(payload([{ id: UUID_A, title: "A", time_created: "2026-06-24T12:00:00Z" }]), mindful);
		expect(() => importV3(payload([{ id: UUID_A, title: "A again", time_created: "2026-06-24T12:00:00Z" }]), mindful)).toThrow(
			CollisionError,
		);
		expect(mindful.get(`thought:${ID_A}`).title).toBe("A");
	});

	it("counts unsupported v5 fields in the report", () => {
		const report = importV3(
			payload([
				{
					id: UUID_A,
					title: "A",
					time_created: "2026-06-24T12:00:00Z",
					visualIdentityLayers: {},
					interactionCount: 7,
					isAttractor: true,
				},
			]),
			mindful,
			{ dryRun: true },
		);
		expect(report.droppedUnsupportedFields).toMatchObject({
			visualIdentityLayers: 1,
			interactionCount: 1,
			isAttractor: 1,
		});
	});

	it("writes through corpus storage on real import", () => {
		importV3(payload([{ id: UUID_A, title: "A", time_created: "2026-06-24T12:00:00Z" }]), mindful);
		expect(existsSync(join(root, "thought", `${ID_A}.md`))).toBe(true);
	});
});
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `rtk npx vitest run tests/import-v3.test.ts`

Expected: FAIL with a module resolution error for `../src/import-v3.js`.

- [ ] **Step 3: Implement `src/import-v3.ts` core helpers**

Create `src/import-v3.ts`:

```ts
import {
	CollisionError,
	ValidationError,
	makeNode,
	type Node,
} from "@nodes/kernel";
import { z } from "zod";
import { ALIAS, aliasOf, makeAlias, normalizeAliasInput } from "./alias.js";
import { type Mindful } from "./api.js";
import { CAPTURED, makeCaptured } from "./captured.js";
import { VISUAL_IDENTITY, deriveIdentity } from "./identity.js";
import { THOUGHT } from "./kinds.js";

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

const V3ThoughtSchema = z
	.object({
		id: z.string(),
		title: z.unknown().optional(),
		body: z.unknown().optional(),
		alias: z.unknown().optional(),
		tag: z.unknown().optional(),
		tags: z.unknown().optional(),
		time_created: z.unknown().optional(),
		time_modified: z.unknown().optional(),
		metadata: z.unknown().optional(),
	})
	.passthrough();

const V3PayloadSchema = z
	.object({
		thoughts: z.array(V3ThoughtSchema),
		edges: z.array(z.unknown()).optional().default([]),
		activities: z.array(z.unknown()).optional().default([]),
		structures: z.array(z.unknown()).optional().default([]),
	})
	.passthrough();

type V3Thought = z.infer<typeof V3ThoughtSchema>;

const UNSUPPORTED_THOUGHT_FIELDS = [
	"visualIdentity",
	"visualIdentityLayers",
	"visual_identity",
	"activityTracking",
	"activity_tracking",
	"interactionCount",
	"interaction_count",
	"lastInteractionAt",
	"last_interaction_at",
	"isAttractor",
	"is_attractor",
	"visualIndex",
	"visual_index",
	"attractor",
] as const;

function zodMessages(error: z.ZodError): string {
	return error.issues.map((issue) => issue.message).join("; ");
}

export function normalizeV3Id(sourceId: string): string {
	const normalized = sourceId.replace(/-/g, "").toLowerCase();
	if (!/^[0-9a-f]{32}$/.test(normalized)) {
		throw new ValidationError(`v3 thought id ${JSON.stringify(sourceId)} does not normalize to 32 hex chars`);
	}
	return normalized;
}

export function normalizeV3Timestamp(value: unknown): string {
	if (typeof value !== "string") throw new ValidationError(`timestamp ${JSON.stringify(value)} is not a string`);
	const raw = value.trim();
	if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return `${raw}T00:00:00Z`;
	if (/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(raw)) {
		return makeCaptured(raw).at;
	}
	if (/^\d{4}-\d{2}-\d{2}T/.test(raw)) {
		return makeCaptured(`${raw}Z`).at;
	}
	throw new ValidationError(`timestamp ${JSON.stringify(value)} is not a supported v3 timestamp`);
}

function metadataCreatedAt(thought: V3Thought): unknown {
	const metadata = thought.metadata;
	if (metadata !== null && typeof metadata === "object" && !Array.isArray(metadata)) {
		return (metadata as Record<string, unknown>).createdAt;
	}
	return undefined;
}

function sourceTimestamp(thought: V3Thought, fallbackAt: string | undefined): string {
	const raw = thought.time_created ?? metadataCreatedAt(thought) ?? fallbackAt;
	if (raw === undefined) {
		throw new ValidationError(`thought ${JSON.stringify(thought.id)} is missing a creation timestamp`);
	}
	return normalizeV3Timestamp(raw);
}

function textField(value: unknown, fallback: string): string {
	if (typeof value !== "string") return fallback;
	const trimmed = value.trim();
	return trimmed === "" ? fallback : value;
}

function bodyField(value: unknown): string {
	return typeof value === "string" ? value : "";
}

function aliasSource(thought: V3Thought): string | undefined {
	for (const raw of [thought.alias, thought.tag]) {
		if (typeof raw !== "string") continue;
		const normalized = normalizeAliasInput(raw);
		if (normalized === "") throw new ValidationError(`thought ${JSON.stringify(thought.id)} has an empty alias after normalization`);
		return normalized;
	}
	return undefined;
}

function increment(map: Record<string, number>, key: string): void {
	map[key] = (map[key] ?? 0) + 1;
}

function unsupportedFieldCounts(thoughts: V3Thought[]): Record<string, number> {
	const counts: Record<string, number> = {};
	for (const thought of thoughts) {
		for (const key of UNSUPPORTED_THOUGHT_FIELDS) {
			if (Object.prototype.hasOwnProperty.call(thought, key)) increment(counts, key);
		}
	}
	return counts;
}

function existingAliases(mindful: Mindful): Set<string> {
	const aliases = new Set<string>();
	for (const node of mindful.allThoughts()) {
		const alias = aliasOf(node);
		if (alias !== null) aliases.add(alias.name);
	}
	return aliases;
}

function existingIdsAndUids(mindful: Mindful): { ids: Set<string>; uids: Set<string> } {
	const ids = new Set<string>();
	const uids = new Set<string>();
	for (const node of mindful.corpus.all()) {
		ids.add(node.id);
		uids.add(node.uid);
	}
	return { ids, uids };
}

interface BuildResult {
	nodes: Node[];
	report: ImportReport;
	sourceToNodeId: Map<string, string>;
}

function buildCore(payload: unknown, mindful: Mindful, options: ImportV3Options): BuildResult {
	const parsed = V3PayloadSchema.safeParse(payload);
	if (!parsed.success) throw new ValidationError(`invalid v3 import payload: ${zodMessages(parsed.error)}`);

	const dryRun = options.dryRun ?? false;
	const fallbackAt = options.fallbackAt;
	if (fallbackAt !== undefined) makeCaptured(normalizeV3Timestamp(fallbackAt));

	const existingIdentity = existingIdsAndUids(mindful);
	const seenIds = new Set<string>();
	const seenUids = new Set<string>();
	const seenAliases = existingAliases(mindful);
	const nodes: Node[] = [];
	const sourceToNodeId = new Map<string, string>();
	const idMappings: ImportReport["idMappings"] = [];
	let aliases = 0;

	for (const thought of parsed.data.thoughts) {
		const uid = normalizeV3Id(thought.id);
		const nodeId = `${THOUGHT}:${uid}`;
		if (seenIds.has(nodeId) || seenUids.has(uid)) throw new ValidationError(`duplicate imported id/uid for ${JSON.stringify(thought.id)}`);
		if (existingIdentity.ids.has(nodeId) || existingIdentity.uids.has(uid)) {
			throw new CollisionError(`imported identity ${JSON.stringify(nodeId)} already exists`);
		}
		seenIds.add(nodeId);
		seenUids.add(uid);
		sourceToNodeId.set(thought.id, nodeId);

		const at = sourceTimestamp(thought, fallbackAt);
		const node = makeNode({
			id: nodeId,
			uid,
			kind: THOUGHT,
			title: textField(thought.title, "Untitled"),
			body: bodyField(thought.body),
			metadata: { created: makeCaptured(at).at.slice(0, 10) },
		});
		node.facets[VISUAL_IDENTITY] = deriveIdentity(uid);
		node.facets[CAPTURED] = makeCaptured(at);

		const aliasName = aliasSource(thought);
		if (aliasName !== undefined) {
			const alias = makeAlias(aliasName);
			if (seenAliases.has(alias.name)) throw new ValidationError(`alias ${JSON.stringify(alias.name)} is already in use`);
			seenAliases.add(alias.name);
			node.facets[ALIAS] = alias;
			aliases += 1;
		}

		nodes.push(node);
		idMappings.push({ sourceId: thought.id, nodeId, uid });
	}

	return {
		nodes,
		sourceToNodeId,
		report: {
			thoughts: nodes.length,
			aliases,
			relations: 0,
			duplicateRelations: 0,
			droppedUnsupportedFields: unsupportedFieldCounts(parsed.data.thoughts),
			idMappings,
			dryRun,
		},
	};
}

export function importV3(payload: unknown, mindful: Mindful, options: ImportV3Options = {}): ImportReport {
	const built = buildCore(payload, mindful, options);
	for (const node of built.nodes) {
		if (mindful.corpus.registry !== undefined) mindful.corpus.registry.validate(node);
	}
	if (built.report.dryRun) return built.report;
	for (const node of built.nodes) mindful.corpus.add(node);
	return built.report;
}
```

- [ ] **Step 4: Export importer helpers**

Modify `src/index.ts`:

```ts
export {
	importV3,
	normalizeV3Id,
	normalizeV3Timestamp,
	type ImportReport,
	type ImportV3Options,
} from "./import-v3.js";
```

- [ ] **Step 5: Run focused importer tests**

Run: `rtk npx vitest run tests/import-v3.test.ts`

Expected: PASS for core importer tests.

- [ ] **Step 6: Run typecheck**

Run: `rtk npm run typecheck`

Expected: PASS. Remove any imports in `src/import-v3.ts` that are not used until Task 4.

- [ ] **Step 7: Commit Task 3**

```bash
rtk git add src/import-v3.ts src/index.ts tests/import-v3.test.ts
rtk git commit -m "feat: import v3 thoughts"
```

---

### Task 4: Import Relations and Tags

**Files:**
- Modify: `src/import-v3.ts`
- Test: `tests/import-v3.test.ts`

**Purpose:** Import explicit v3 edges and thought `tags[]` as global relations, with source restrictions, alias/title resolution, endpoint validation, dedupe, and unsupported edge type reporting.

- [ ] **Step 1: Append relation importer tests**

Append to `tests/import-v3.test.ts`:

```ts
describe("importV3 relations and tags", () => {
	let root: string;
	let mindful: Mindful;

	beforeEach(() => {
		root = mkdtempSync(join(tmpdir(), "mindful-import-v3-rel-"));
		mindful = new Mindful(root);
	});

	afterEach(() => rmSync(root, { recursive: true, force: true }));

	it("imports explicit edges as global relations on imported source thoughts", () => {
		const report = importV3(
			payload(
				[
					{ id: UUID_A, title: "A", time_created: "2026-06-24T12:00:00Z" },
					{ id: UUID_B, title: "B", time_created: "2026-06-24T12:00:00Z" },
				],
				{ edges: [{ source: UUID_A, target: UUID_B, relation: "relatesTo", weight: 0.75, type: "explicit" }] },
			),
			mindful,
		);
		expect(report.relations).toBe(1);
		const related = mindful.related(`thought:${ID_A}`).map((n) => n.id);
		expect(related).toEqual([`thought:${ID_B}`]);
		const source = mindful.get(`thought:${ID_A}`);
		expect(source.relations).toEqual([
			{
				source: `thought:${ID_A}`,
				predicate: "relatesTo",
				target: `thought:${ID_B}`,
				directed: true,
				weight: 0.75,
				attrs: {},
			},
		]);
	});

	it("imports tag strings through alias/title resolution", () => {
		importV3(
			payload([
				{ id: UUID_A, title: "Tag Target", alias: "target", time_created: "2026-06-24T12:00:00Z" },
				{ id: UUID_B, title: "Tagged", tags: ["target"], time_created: "2026-06-24T12:00:00Z" },
			]),
			mindful,
		);
		expect(mindful.related(`thought:${ID_B}`).map((n) => n.id)).toEqual([`thought:${ID_A}`]);
	});

	it("deduplicates explicit and tag relations together", () => {
		const report = importV3(
			payload(
				[
					{ id: UUID_A, title: "Target", alias: "target", time_created: "2026-06-24T12:00:00Z" },
					{ id: UUID_B, title: "Tagged", tags: ["target"], time_created: "2026-06-24T12:00:00Z" },
				],
				{ edges: [{ source: UUID_B, target: UUID_A, relation: "relatesTo", type: "tag_based" }] },
			),
			mindful,
		);
		expect(report.relations).toBe(1);
		expect(report.duplicateRelations).toBe(1);
		expect(mindful.get(`thought:${ID_B}`).relations).toHaveLength(1);
	});

	it("allows existing targets but requires imported sources", () => {
		const existing = mindful.capture({ at: "2026-06-24T12:00:00Z", title: "Existing", alias: "existing" });
		const report = importV3(
			payload([{ id: UUID_A, title: "A", time_created: "2026-06-24T12:00:00Z" }], {
				edges: [{ source: UUID_A, target: existing.id, relation: "relatesTo", type: "explicit" }],
			}),
			mindful,
		);
		expect(report.relations).toBe(1);
		expect(mindful.related(`thought:${ID_A}`).map((n) => n.id)).toEqual([existing.id]);
	});

	it("fails when an explicit edge source is existing-only", () => {
		const existing = mindful.capture({ at: "2026-06-24T12:00:00Z", title: "Existing", alias: "existing" });
		expect(() =>
			importV3(
				payload([{ id: UUID_A, title: "A", time_created: "2026-06-24T12:00:00Z" }], {
					edges: [{ source: existing.id, target: UUID_A, relation: "relatesTo" }],
				}),
				mindful,
			),
		).toThrow(ValidationError);
		expect(mindful.allThoughts().map((n) => n.id)).toEqual([existing.id]);
	});

	it("fails on dangling edge endpoints before writing", () => {
		expect(() =>
			importV3(
				payload([{ id: UUID_A, title: "A", time_created: "2026-06-24T12:00:00Z" }], {
					edges: [{ source: UUID_A, target: UUID_B, relation: "relatesTo" }],
				}),
				mindful,
			),
		).toThrow(ValidationError);
		expect(mindful.allThoughts()).toEqual([]);
	});

	it("fails on dangling tag targets before writing", () => {
		expect(() =>
			importV3(payload([{ id: UUID_A, title: "A", tags: ["missing"], time_created: "2026-06-24T12:00:00Z" }]), mindful),
		).toThrow(ValidationError);
		expect(mindful.allThoughts()).toEqual([]);
	});

	it("fails on ambiguous title fallback before writing", () => {
		expect(() =>
			importV3(
				payload([
					{ id: UUID_A, title: "Target", time_created: "2026-06-24T12:00:00Z" },
					{ id: UUID_B, title: "Target", time_created: "2026-06-24T12:00:00Z" },
					{
						id: "550e8400-e29b-41d4-a716-446655440002",
						title: "Tagged",
						tags: ["Target"],
						time_created: "2026-06-24T12:00:00Z",
					},
				]),
				mindful,
			),
		).toThrow(ValidationError);
		expect(mindful.allThoughts()).toEqual([]);
	});

	it("counts ignored edge type values in droppedUnsupportedFields", () => {
		const report = importV3(
			payload(
				[
					{ id: UUID_A, title: "A", time_created: "2026-06-24T12:00:00Z" },
					{ id: UUID_B, title: "B", time_created: "2026-06-24T12:00:00Z" },
				],
				{ edges: [{ source: UUID_A, target: UUID_B, relation: "relatesTo", type: "v3-special" }] },
			),
			mindful,
			{ dryRun: true },
		);
		expect(report.droppedUnsupportedFields).toMatchObject({ "edge.type": 1 });
	});
});
```

- [ ] **Step 2: Run relation tests and verify failure**

Run: `rtk npx vitest run tests/import-v3.test.ts`

Expected: FAIL because `relations` remains `0`, relations are not imported, and dangling validations do not exist.

- [ ] **Step 3: Extend `src/import-v3.ts` schemas and helper indexes**

Add/replace imports:

```ts
import {
	CollisionError,
	RELATES_TO,
	ValidationError,
	makeNode,
	type Node,
	type Relation,
} from "@nodes/kernel";
```

Add edge schema near `V3ThoughtSchema`:

```ts
const V3EdgeSchema = z
	.object({
		source: z.string(),
		target: z.string(),
		relation: z.unknown().optional(),
		weight: z.unknown().optional(),
		type: z.unknown().optional(),
	})
	.passthrough();
```

Update `V3PayloadSchema`:

```ts
const V3PayloadSchema = z
	.object({
		thoughts: z.array(V3ThoughtSchema),
		edges: z.array(V3EdgeSchema).optional().default([]),
		activities: z.array(z.unknown()).optional().default([]),
		structures: z.array(z.unknown()).optional().default([]),
	})
	.passthrough();
```

Add helper types/functions:

```ts
type V3Edge = z.infer<typeof V3EdgeSchema>;

interface ResolverIndex {
	aliases: Map<string, string>;
	titles: Map<string, string>;
	ambiguousTitles: Set<string>;
}

function addTitleKey(byTitle: Map<string, Set<string>>, key: string, id: string): void {
	const ids = byTitle.get(key) ?? new Set<string>();
	ids.add(id);
	byTitle.set(key, ids);
}

function buildResolverIndex(nodes: Node[], existing: Node[]): ResolverIndex {
	const aliases = new Map<string, string>();
	const byTitle = new Map<string, Set<string>>();
	for (const node of [...existing, ...nodes]) {
		if (node.kind !== THOUGHT) continue;
		const alias = aliasOf(node);
		if (alias !== null) aliases.set(alias.name, node.id);
		addTitleKey(byTitle, node.title, node.id);
		addTitleKey(byTitle, node.title.toLowerCase(), node.id);
	}
	const titles = new Map<string, string>();
	const ambiguousTitles = new Set<string>();
	for (const [key, ids] of byTitle) {
		if (ids.size === 1) titles.set(key, [...ids][0]);
		else ambiguousTitles.add(key);
	}
	return { aliases, titles, ambiguousTitles };
}

function resolveName(name: string, idx: ResolverIndex): string {
	const cleaned = name.replace(/^#+/, "");
	const aliasTarget = idx.aliases.get(cleaned) ?? idx.aliases.get(cleaned.toLowerCase());
	if (aliasTarget !== undefined) return aliasTarget;
	const titleTarget = idx.titles.get(cleaned) ?? idx.titles.get(cleaned.toLowerCase());
	if (titleTarget !== undefined) return titleTarget;
	if (idx.ambiguousTitles.has(cleaned) || idx.ambiguousTitles.has(cleaned.toLowerCase())) {
		throw new ValidationError(`ambiguous tag ${JSON.stringify(name)}: multiple thoughts share that title`);
	}
	throw new ValidationError(`tag ${JSON.stringify(name)} does not resolve to a known node`);
}

function finiteWeight(raw: unknown): number | null {
	return typeof raw === "number" && Number.isFinite(raw) ? raw : null;
}

function predicate(raw: unknown): string {
	return typeof raw === "string" && raw !== "" ? raw : RELATES_TO;
}
```

- [ ] **Step 4: Add source/target resolution helpers**

Add these functions to `src/import-v3.ts`:

```ts
function resolveImportedSource(raw: string, sourceToNodeId: Map<string, string>): string {
	const direct = sourceToNodeId.get(raw);
	if (direct !== undefined) return direct;
	let normalized: string;
	try {
		normalized = normalizeV3Id(raw);
	} catch {
		throw new ValidationError(`edge source ${JSON.stringify(raw)} is not in the import batch`);
	}
	const nodeId = `${THOUGHT}:${normalized}`;
	if (!sourceToNodeId.has(raw) && ![...sourceToNodeId.values()].includes(nodeId)) {
		throw new ValidationError(`edge source ${JSON.stringify(raw)} is not in the import batch`);
	}
	return nodeId;
}

function resolveTarget(raw: string, sourceToNodeId: Map<string, string>, existingIds: Set<string>): string {
	const direct = sourceToNodeId.get(raw);
	if (direct !== undefined) return direct;
	if (existingIds.has(raw)) return raw;
	try {
		const nodeId = `${THOUGHT}:${normalizeV3Id(raw)}`;
		if ([...sourceToNodeId.values()].includes(nodeId) || existingIds.has(nodeId)) return nodeId;
	} catch {
		// fall through to the typed error below
	}
	throw new ValidationError(`edge target ${JSON.stringify(raw)} does not resolve to an imported or existing thought`);
}

function relationKey(rel: Relation): string {
	return `${rel.source}\u0000${rel.predicate}\u0000${rel.target}`;
}
```

- [ ] **Step 5: Build relations before validation/write**

In `buildCore`, after `nodes` are built and before returning, add relation construction. The final part of `buildCore` should look like:

```ts
	const nodeById = new Map(nodes.map((node) => [node.id, node]));
	const existingThoughts = mindful.allThoughts();
	const existingIdSet = new Set(existingThoughts.map((node) => node.id));
	const resolver = buildResolverIndex(nodes, existingThoughts);
	const relationKeys = new Set<string>();
	let relations = 0;
	let duplicateRelations = 0;

	function addRelation(rel: Relation): void {
		const key = relationKey(rel);
		if (relationKeys.has(key)) {
			duplicateRelations += 1;
			return;
		}
		relationKeys.add(key);
		const source = nodeById.get(rel.source);
		if (source === undefined) throw new ValidationError(`relation source ${JSON.stringify(rel.source)} is not imported`);
		source.relations.push(rel);
		relations += 1;
	}

	for (const edge of parsed.data.edges) {
		if (edge.type !== undefined) increment(droppedUnsupportedFields, "edge.type");
		const source = resolveImportedSource(edge.source, sourceToNodeId);
		const target = resolveTarget(edge.target, sourceToNodeId, existingIdSet);
		addRelation({
			source,
			predicate: predicate(edge.relation),
			target,
			directed: true,
			weight: finiteWeight(edge.weight),
			attrs: {},
		});
	}

	for (const thought of parsed.data.thoughts) {
		const source = sourceToNodeId.get(thought.id);
		if (source === undefined) throw new ValidationError(`missing imported source for ${JSON.stringify(thought.id)}`);
		const tags = thought.tags;
		if (tags === undefined) continue;
		if (!Array.isArray(tags)) throw new ValidationError(`thought ${JSON.stringify(thought.id)} tags must be an array`);
		for (const tag of tags) {
			if (typeof tag !== "string") throw new ValidationError(`thought ${JSON.stringify(thought.id)} tag must be a string`);
			addRelation({ source, predicate: RELATES_TO, target: resolveName(tag, resolver), directed: true, weight: null, attrs: {} });
		}
	}

	return {
		nodes,
		sourceToNodeId,
		report: {
			thoughts: nodes.length,
			aliases,
			relations,
			duplicateRelations,
			droppedUnsupportedFields,
			idMappings,
			dryRun,
		},
	};
```

To support this, change `unsupportedFieldCounts` usage in `buildCore`:

```ts
const droppedUnsupportedFields = unsupportedFieldCounts(parsed.data.thoughts);
```

and remove the older inline `droppedUnsupportedFields: unsupportedFieldCounts(...)` in the return.

- [ ] **Step 6: Run relation importer tests**

Run: `rtk npx vitest run tests/import-v3.test.ts`

Expected: PASS.

- [ ] **Step 7: Run alias/API regression tests**

Run: `rtk npx vitest run tests/alias.test.ts tests/mindful-thoughts.test.ts`

Expected: PASS. Imported relation logic must not change normal `Mindful.tag` behavior.

- [ ] **Step 8: Commit Task 4**

```bash
rtk git add src/import-v3.ts tests/import-v3.test.ts
rtk git commit -m "feat: import v3 relations"
```

---

### Task 5: `mindful-import-v3` Binary and Package Wiring

**Files:**
- Create: `src/bin-import-v3.ts`
- Modify: `package.json`
- Test: `tests/import-v3.test.ts`

**Purpose:** Add the thin executable wrapper and package bin entry. Keep subprocess testing out; verify by build and a direct helper test where useful.

- [ ] **Step 1: Add a small report formatter export and test**

Append this test to `tests/import-v3.test.ts`:

```ts
describe("formatImportReport", () => {
	it("formats a compact newline-terminated report", () => {
		expect(
			formatImportReport({
				thoughts: 2,
				aliases: 1,
				relations: 3,
				duplicateRelations: 1,
				droppedUnsupportedFields: { "edge.type": 1 },
				idMappings: [
					{ sourceId: UUID_A, nodeId: `thought:${ID_A}`, uid: ID_A },
					{ sourceId: UUID_B, nodeId: `thought:${ID_B}`, uid: ID_B },
				],
				dryRun: true,
			}),
		).toBe(
			[
				"mindful-import-v3 dry-run complete",
				"thoughts: 2",
				"aliases: 1",
				"relations: 3",
				"duplicate relations: 1",
				"dropped unsupported fields:",
				"  edge.type: 1",
				"id mappings: 2",
				"",
			].join("\n"),
		);
	});
});
```

Also add `formatImportReport` to the import list at the top of `tests/import-v3.test.ts`:

```ts
import { formatImportReport, importV3, normalizeV3Id, normalizeV3Timestamp } from "../src/import-v3.js";
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `rtk npx vitest run tests/import-v3.test.ts`

Expected: FAIL because `formatImportReport` is not exported.

- [ ] **Step 3: Implement report formatting**

Add to `src/import-v3.ts`:

```ts
export function formatImportReport(report: ImportReport): string {
	const lines = [
		`mindful-import-v3 ${report.dryRun ? "dry-run" : "import"} complete`,
		`thoughts: ${report.thoughts}`,
		`aliases: ${report.aliases}`,
		`relations: ${report.relations}`,
		`duplicate relations: ${report.duplicateRelations}`,
	];
	const dropped = Object.entries(report.droppedUnsupportedFields).sort(([a], [b]) => a.localeCompare(b));
	if (dropped.length > 0) {
		lines.push("dropped unsupported fields:");
		for (const [key, count] of dropped) lines.push(`  ${key}: ${count}`);
	}
	lines.push(`id mappings: ${report.idMappings.length}`);
	return `${lines.join("\n")}\n`;
}
```

Update `src/index.ts` importer export:

```ts
export {
	formatImportReport,
	importV3,
	normalizeV3Id,
	normalizeV3Timestamp,
	type ImportReport,
	type ImportV3Options,
} from "./import-v3.js";
```

- [ ] **Step 4: Create `src/bin-import-v3.ts`**

Create `src/bin-import-v3.ts`:

```ts
#!/usr/bin/env node
import { mkdirSync, readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { NodesError } from "@nodes/kernel";
import { Mindful } from "./api.js";
import { resolveDataDir } from "./cli.js";
import { formatImportReport, importV3 } from "./import-v3.js";

const USAGE = `usage: mindful-import-v3 <export.json> [--dry-run] [--fallback-at <iso-offset>]
`;

function main(argv: string[], env: NodeJS.ProcessEnv): number {
	let parsed: ReturnType<typeof parseArgs>;
	try {
		parsed = parseArgs({
			args: argv,
			allowPositionals: true,
			strict: true,
			options: {
				"dry-run": { type: "boolean" },
				"fallback-at": { type: "string" },
			},
		});
	} catch (e) {
		process.stderr.write(`${e instanceof Error ? e.message : String(e)}\n\n${USAGE}`);
		return 2;
	}

	if (parsed.positionals.length !== 1) {
		process.stderr.write(`mindful-import-v3 requires exactly one export.json path\n\n${USAGE}`);
		return 2;
	}

	try {
		const root = resolveDataDir(env);
		mkdirSync(root, { recursive: true });
		const payload = JSON.parse(readFileSync(parsed.positionals[0], "utf8")) as unknown;
		const mindful = new Mindful(root);
		const report = importV3(payload, mindful, {
			dryRun: parsed.values["dry-run"] === true,
			fallbackAt: parsed.values["fallback-at"] as string | undefined,
		});
		process.stdout.write(formatImportReport(report));
		return 0;
	} catch (e) {
		if (e instanceof NodesError || e instanceof Error) {
			process.stderr.write(`error: ${e.message}\n`);
			return 1;
		}
		throw e;
	}
}

process.exitCode = main(process.argv.slice(2), process.env);
```

- [ ] **Step 5: Add package bin entry**

Modify `package.json`:

```json
"bin": { "mindful": "dist/bin.js", "mindful-import-v3": "dist/bin-import-v3.js" },
```

Do not add dependencies.

- [ ] **Step 6: Run focused tests**

Run: `rtk npx vitest run tests/import-v3.test.ts`

Expected: PASS.

- [ ] **Step 7: Run typecheck and build**

Run: `rtk npm run typecheck`

Expected: PASS.

Run: `rtk npm run build`

Expected: PASS and `dist/bin-import-v3.js` exists.

- [ ] **Step 8: Commit Task 5**

```bash
rtk git add src/bin-import-v3.ts src/import-v3.ts src/index.ts package.json tests/import-v3.test.ts
rtk git commit -m "feat: add v3 import CLI"
```

---

### Task 6: Final Verification and Plan Closeout

**Files:**
- No source changes expected.
- If formatting fails, modify only the files reported by biome.

**Purpose:** Run the full project gate, fix any formatting/type/test issues, and leave the repo clean.

- [ ] **Step 1: Run full test suite**

Run: `rtk npm test`

Expected: PASS. All vitest suites pass.

- [ ] **Step 2: Run typecheck**

Run: `rtk npm run typecheck`

Expected: PASS.

- [ ] **Step 3: Run biome check**

Run: `rtk npm run check`

Expected: PASS. If it fails with formatting-only issues, run:

```bash
rtk npx @biomejs/biome check --write src/alias.ts src/api.ts src/cli.ts src/import-v3.ts src/bin-import-v3.ts tests/alias.test.ts tests/import-v3.test.ts
```

Then re-run `rtk npm run check`.

- [ ] **Step 4: Run build**

Run: `rtk npm run build`

Expected: PASS.

- [ ] **Step 5: Check git status**

Run: `rtk git status --short --branch`

Expected: clean branch after any final formatting commit.

- [ ] **Step 6: Commit final formatting fixes if needed**

If Step 3 changed files:

```bash
rtk git add src/alias.ts src/api.ts src/cli.ts src/import-v3.ts src/bin-import-v3.ts tests/alias.test.ts tests/import-v3.test.ts
rtk git commit -m "style: format v3 import helper"
```

If no files changed, skip this commit.
