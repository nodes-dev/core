# Mindful v6 — SP7: Journal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make capture-time intrinsic to every thought and add a `journal` CLI command that reads thoughts in a time-ordered, date-windowed view.

**Architecture:** A new required `captured` facet (mirroring `identity.ts`) holds a precise ISO instant; a new pure `journal.ts` module (mirroring the `encode.ts` boundary) projects thoughts into date-grouped, wall-clock-ordered `DayGroup`s. The clock is injected at the edge (`bin.ts` → `runCli`'s new `now` param); `Mindful`/`runCli`/`journalView` stay deterministic. The journal is a *view*, never a stored container.

**Tech Stack:** TypeScript (ESM, `.js` import specifiers), zod, `@nodes/kernel` (file: dep, no kernel changes), vitest, biome. Tooling via the `rtk` wrapper.

**Spec:** `~/d/nodes/docs/specs/2026-06-24-mindful-v6-sp7-journal-design.md` (committed `79477d6`).

## Global Constraints

- **No kernel changes.** All work in `~/d/mindful/v6`; `@nodes/kernel` is consumed as-is.
- **`captured` facet shape:** `{ at: string }`, strict; `at` validates as `z.string().datetime({ offset: true })` — explicit offset required (`Z` allowed), naive/date-only rejected, fractional seconds allowed.
- **`capturedSortKey` fractional precision = milliseconds (`.SSS`)**, offset stripped (wall-clock key).
- **No raw `ZodError` escapes a boundary.** `makeCaptured` → `ValidationError`; `capturedOf` → `FacetError`; `journalView` bounds → `ValidationError`; CLI date args → `CliUsageError`. Never call a bare `schema.parse` on a value that can reach `runCli`.
- **`at` is required** on `capture({ title, body?, tags?, at })`; the clock is injected, never read inside `Mindful`.
- **`metadata.created = capturedDate(at)`** — a derived coarse projection, never the source of truth; **`metadata.updated` untouched**.
- **`runCli(argv, mindful, root, env, now, out, err)`** — `now` injected between `env` and the sinks.
- **Centralized datetime contract:** `capturedDate`/`capturedTime`/`capturedSortKey` validate through `CapturedSchema` first; CLI/journal never slice a raw datetime string.
- **`journalView` is pure** (no `Corpus`, no I/O, not a `Mindful` method); the CLI composes `journalView(mindful.allThoughts(), window)`. It filters `kind === THOUGHT` internally, sorts by stored wall clock (tie-break `id`), and omits empty days.
- **Sink contract (from SP5):** sinks receive complete newline-terminated strings; usage errors → exit 2, `NodesError`/`CliError`/`ConfigError` → exit 1, success → 0.
- **Clean break (pre-release, single-user):** making `captured` required means pre-existing thoughts and `makeNode` thought fixtures without it now fail validation — fix the fixtures (enumerated in Task 3).
- **Gate (run from `~/d/mindful/v6`):** `rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`. biome is read-only in `check`; fix formatting with `rtk npx @biomejs/biome check --write <files>`.
- **Use Read/file tools, not shell `grep`/`rg`** (corrupted output under the `rtk` env).

---

### Task 1: `captured` facet module

**Files:**
- Create: `src/captured.ts`
- Test: `tests/captured.test.ts`
- Modify: `src/index.ts` (barrel exports)

**Interfaces:**
- Consumes: `@nodes/kernel` (`FacetError`, `ValidationError`, `type Node`), `zod`.
- Produces:
  - `CAPTURED = "captured"` (string const)
  - `CapturedSchema` (zod), `type Captured = { at: string }`
  - `makeCaptured(at: string): Captured` — throws `ValidationError` on malformed `at`
  - `capturedOf(node: Node): Captured` — throws `FacetError` on missing/malformed
  - `requireValidCaptured(node: Node): void`
  - `capturedDate(at: string): string` (`"YYYY-MM-DD"`)
  - `capturedTime(at: string): string` (`"HH:MM"`)
  - `capturedSortKey(at: string): string` (`"YYYY-MM-DDTHH:MM:SS.SSS"`, offset-stripped)
  - `localIso(date: Date): string`

- [ ] **Step 1: Write the failing test**

Create `tests/captured.test.ts`:

```ts
import { FacetError, ValidationError, makeNode } from "@nodes/kernel";
import { describe, expect, it } from "vitest";
import {
	CAPTURED,
	CapturedSchema,
	capturedDate,
	capturedOf,
	capturedSortKey,
	capturedTime,
	localIso,
	makeCaptured,
	requireValidCaptured,
} from "../src/captured.js";

const pad = (n: number, w = 2) => String(n).padStart(w, "0");

describe("CapturedSchema", () => {
	it("accepts an offset (±HH:MM), Z, and fractional seconds", () => {
		expect(CapturedSchema.safeParse({ at: "2026-06-24T21:02:11-04:00" }).success).toBe(true);
		expect(CapturedSchema.safeParse({ at: "2026-06-24T21:02:11Z" }).success).toBe(true);
		expect(CapturedSchema.safeParse({ at: "2026-06-24T21:02:11.5Z" }).success).toBe(true);
	});

	it("rejects date-only, naive (offset-less), garbage, and extra keys", () => {
		expect(CapturedSchema.safeParse({ at: "2026-06-24" }).success).toBe(false);
		expect(CapturedSchema.safeParse({ at: "2026-06-24T21:02:11" }).success).toBe(false);
		expect(CapturedSchema.safeParse({ at: "garbage" }).success).toBe(false);
		expect(CapturedSchema.safeParse({ at: "2026-06-24T21:02:11Z", extra: 1 }).success).toBe(false);
	});
});

describe("makeCaptured", () => {
	it("returns the validated facet", () => {
		expect(makeCaptured("2026-06-24T12:00:00Z")).toEqual({ at: "2026-06-24T12:00:00Z" });
	});
	it("throws ValidationError (not a raw ZodError) on malformed at", () => {
		expect(() => makeCaptured("nope")).toThrow(ValidationError);
	});
});

describe("capturedOf / requireValidCaptured", () => {
	it("reads a valid facet and passes the invariant", () => {
		const node = makeNode({
			id: "thought:x",
			kind: "thought",
			title: "X",
			facets: { [CAPTURED]: { at: "2026-06-24T12:00:00Z" } },
		});
		expect(capturedOf(node)).toEqual({ at: "2026-06-24T12:00:00Z" });
		expect(() => requireValidCaptured(node)).not.toThrow();
	});
	it("throws FacetError when the facet is missing", () => {
		const bare = makeNode({ id: "thought:y", kind: "thought", title: "Y" });
		expect(() => capturedOf(bare)).toThrow(FacetError);
		expect(() => requireValidCaptured(bare)).toThrow(FacetError);
	});
});

describe("capturedDate / capturedTime", () => {
	it("reads the stored wall-clock date for both offset forms", () => {
		expect(capturedDate("2026-06-24T23:30:00-04:00")).toBe("2026-06-24");
		expect(capturedDate("2026-06-24T23:30:00Z")).toBe("2026-06-24");
	});
	it("reads HH:MM, ignoring seconds and fractions", () => {
		expect(capturedTime("2026-06-24T09:05:30.250Z")).toBe("09:05");
	});
});

describe("capturedSortKey", () => {
	it("normalizes to milliseconds so fractions order after the whole second", () => {
		expect(capturedSortKey("2026-06-24T09:00:00Z") < capturedSortKey("2026-06-24T09:00:00.500Z")).toBe(true);
	});
	it("is offset-independent (same wall clock → equal key)", () => {
		expect(capturedSortKey("2026-06-24T09:00:00-04:00")).toBe(capturedSortKey("2026-06-24T09:00:00+02:00"));
	});
	it("validates first (throws ValidationError on garbage)", () => {
		expect(() => capturedSortKey("nope")).toThrow(ValidationError);
	});
});

describe("localIso", () => {
	it("formats a Date as a valid captured.at with a ±HH:MM offset, round-tripping the local parts", () => {
		const d = new Date("2026-06-24T12:00:00Z");
		const at = localIso(d);
		expect(at).toMatch(/[+-]\d{2}:\d{2}$/);
		expect(() => makeCaptured(at)).not.toThrow();
		expect(capturedDate(at)).toBe(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`);
		expect(capturedTime(at)).toBe(`${pad(d.getHours())}:${pad(d.getMinutes())}`);
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npx vitest run tests/captured.test.ts`
Expected: FAIL — cannot resolve `../src/captured.js` (module does not exist yet).

- [ ] **Step 3: Write the implementation**

Create `src/captured.ts`:

```ts
import { FacetError, type Node, ValidationError } from "@nodes/kernel";
import { z } from "zod";

export const CAPTURED = "captured";

// `at`: an ISO-8601 datetime with an explicit offset (Z or ±HH:MM). Naive (offset-less) and
// date-only strings are rejected; fractional seconds are accepted.
export const CapturedSchema = z.object({ at: z.string().datetime({ offset: true }) }).strict();
export type Captured = z.infer<typeof CapturedSchema>;

/** Capture-time validating constructor: translate a zod failure into the kernel's ValidationError
 * (bad caller INPUT). capture() uses this — never a raw CapturedSchema.parse, which leaks ZodError. */
export function makeCaptured(at: string): Captured {
	const result = CapturedSchema.safeParse({ at });
	if (!result.success) {
		throw new ValidationError(`invalid captured.at: ${result.error.issues.map((i) => i.message).join("; ")}`);
	}
	return result.data;
}

/** Load + validate the stored `captured` facet. Mirrors `visualIdentityOf`: a missing or malformed
 * facet is a shape error → FacetError. */
export function capturedOf(node: Node): Captured {
	const raw = node.facets[CAPTURED];
	if (raw === undefined) throw new FacetError(`${node.id}: missing '${CAPTURED}' facet`);
	const result = CapturedSchema.safeParse(raw);
	if (!result.success) {
		throw new FacetError(
			`${node.id}: invalid '${CAPTURED}' facet: ${result.error.issues.map((i) => i.message).join("; ")}`,
		);
	}
	return result.data;
}

/** Kind-level invariant for `thought`: forces facet validation during Registry.validate. */
export function requireValidCaptured(node: Node): void {
	capturedOf(node);
}

// --- centralized wall-clock extraction (validate FIRST, then read the stored parts) ---

/** "YYYY-MM-DD" — the stored local date, regardless of offset form. */
export function capturedDate(at: string): string {
	return makeCaptured(at).at.slice(0, 10);
}

/** "HH:MM" — the stored wall clock; seconds/fractions ignored. */
export function capturedTime(at: string): string {
	return makeCaptured(at).at.slice(11, 16);
}

const OFFSET_RE = /(Z|[+-]\d{2}:\d{2})$/;

/** Offset-independent, millisecond-normalized wall-clock key for a stable chronological sort.
 * Strips the offset and canonicalizes the fraction to exactly 3 digits, so plain string compare
 * matches true wall-time order (raw compare misorders "…09:00:00.500Z" before "…09:00:00Z"). */
export function capturedSortKey(at: string): string {
	const wall = makeCaptured(at).at.replace(OFFSET_RE, ""); // YYYY-MM-DDTHH:MM:SS[.fff]
	const dot = wall.indexOf(".");
	if (dot === -1) return `${wall}.000`;
	const frac = `${wall.slice(dot + 1)}000`.slice(0, 3);
	return `${wall.slice(0, dot)}.${frac}`;
}

/** Side-effect-free Date formatter using the LOCAL timezone; produces an ISO string with a local
 * ±HH:MM offset and millisecond precision. bin.ts calls localIso(new Date()). */
export function localIso(date: Date): string {
	const p = (n: number, w = 2) => String(n).padStart(w, "0");
	const off = -date.getTimezoneOffset(); // minutes east of UTC
	const sign = off >= 0 ? "+" : "-";
	const oh = p(Math.floor(Math.abs(off) / 60));
	const om = p(Math.abs(off) % 60);
	return (
		`${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}` +
		`T${p(date.getHours())}:${p(date.getMinutes())}:${p(date.getSeconds())}.${p(date.getMilliseconds(), 3)}` +
		`${sign}${oh}:${om}`
	);
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npx vitest run tests/captured.test.ts`
Expected: PASS (all cases).

- [ ] **Step 5: Add barrel exports**

In `src/index.ts`, add after the `sprite` export line (keep grouping by module):

```ts
export {
	CAPTURED,
	CapturedSchema,
	type Captured,
	capturedDate,
	capturedOf,
	capturedSortKey,
	capturedTime,
	localIso,
	makeCaptured,
	requireValidCaptured,
} from "./captured.js";
```

- [ ] **Step 6: Format + typecheck**

Run: `rtk npx @biomejs/biome check --write src/captured.ts src/index.ts tests/captured.test.ts && rtk npm run typecheck`
Expected: biome writes/normalizes (import sorting), typecheck clean.

- [ ] **Step 7: Commit**

```bash
git add src/captured.ts src/index.ts tests/captured.test.ts
git commit -m "feat(captured): captured facet — schema, validated helpers, sort key, localIso"
```

---

### Task 2: `journal.ts` pure projection

**Files:**
- Create: `src/journal.ts`
- Test: `tests/journal.test.ts`
- Modify: `src/index.ts` (barrel exports)

**Interfaces:**
- Consumes: `@nodes/kernel` (`type Node`, `ValidationError`), `zod`, `./captured.js` (`capturedDate`, `capturedOf`, `capturedSortKey`), `./kinds.js` (`THOUGHT`).
- Produces:
  - `interface JournalEntry { id: string; title: string; at: string }`
  - `interface DayGroup { date: string; entries: JournalEntry[] }`
  - `interface DateWindow { since: string; until: string }`
  - `JournalDateSchema` (zod `YYYY-MM-DD`, calendar-valid)
  - `journalView(thoughts: Node[], window: DateWindow): DayGroup[]`

- [ ] **Step 1: Write the failing test**

Create `tests/journal.test.ts`:

```ts
import { ValidationError, makeNode } from "@nodes/kernel";
import { describe, expect, it } from "vitest";
import { CAPTURED } from "../src/captured.js";
import { type DateWindow, journalView } from "../src/journal.js";

function thought(slug: string, at: string, title = slug): ReturnType<typeof makeNode> {
	return makeNode({ id: `thought:${slug}`, kind: "thought", title, facets: { [CAPTURED]: { at } } });
}
const W = (since: string, until: string): DateWindow => ({ since, until });

describe("journalView", () => {
	it("filters to the window and groups by date", () => {
		const ts = [
			thought("a", "2026-06-20T10:00:00Z"),
			thought("b", "2026-06-24T09:00:00Z"),
			thought("c", "2026-06-24T21:00:00Z"),
			thought("d", "2026-06-30T10:00:00Z"),
		];
		const g = journalView(ts, W("2026-06-24", "2026-06-24"));
		expect(g.map((x) => x.date)).toEqual(["2026-06-24"]);
		expect(g[0].entries.map((e) => e.id)).toEqual(["thought:b", "thought:c"]);
	});

	it("spans a multi-day range, each date its own group, days ascending", () => {
		const ts = [thought("a", "2026-06-25T08:00:00Z"), thought("b", "2026-06-24T10:00:00Z")];
		const g = journalView(ts, W("2026-06-24", "2026-06-25"));
		expect(g.map((x) => x.date)).toEqual(["2026-06-24", "2026-06-25"]);
	});

	it("sorts within a day by wall clock, ties broken by id", () => {
		const ts = [
			thought("z", "2026-06-24T09:00:00Z"),
			thought("a", "2026-06-24T08:00:00Z"),
			thought("m", "2026-06-24T09:00:00Z"),
		];
		const g = journalView(ts, W("2026-06-24", "2026-06-24"));
		expect(g[0].entries.map((e) => e.id)).toEqual(["thought:a", "thought:m", "thought:z"]);
	});

	it("orders fractional seconds after the whole second (not raw-lexicographic)", () => {
		const ts = [thought("late", "2026-06-24T09:00:00.500Z"), thought("early", "2026-06-24T09:00:00Z")];
		const g = journalView(ts, W("2026-06-24", "2026-06-24"));
		expect(g[0].entries.map((e) => e.id)).toEqual(["thought:early", "thought:late"]);
	});

	it("orders by stored wall clock, not absolute UTC instant", () => {
		// west 09:00-04:00 = 13:00Z; east 10:00+02:00 = 08:00Z. UTC order would be [east, west];
		// wall-clock order is [west(09:00), east(10:00)].
		const ts = [thought("east", "2026-06-24T10:00:00+02:00"), thought("west", "2026-06-24T09:00:00-04:00")];
		const g = journalView(ts, W("2026-06-24", "2026-06-24"));
		expect(g[0].entries.map((e) => e.id)).toEqual(["thought:west", "thought:east"]);
	});

	it("filters out non-thought nodes", () => {
		const j = makeNode({
			id: "journal:log",
			kind: "journal",
			title: "log",
			facets: { membership: { members: [] }, order: { order: [] } },
		});
		const ts = [thought("a", "2026-06-24T10:00:00Z"), j];
		const g = journalView(ts, W("2026-06-24", "2026-06-24"));
		expect(g[0].entries.map((e) => e.id)).toEqual(["thought:a"]);
	});

	it("omits empty days (returns [] when nothing matches)", () => {
		expect(journalView([thought("a", "2026-06-20T10:00:00Z")], W("2026-06-24", "2026-06-24"))).toEqual([]);
	});

	it("rejects a malformed bound with ValidationError (not ZodError)", () => {
		expect(() => journalView([], W("2026-13-01", "2026-06-24"))).toThrow(ValidationError);
		expect(() => journalView([], W("nope", "2026-06-24"))).toThrow(ValidationError);
	});

	it("rejects since > until with ValidationError", () => {
		expect(() => journalView([], W("2026-06-25", "2026-06-24"))).toThrow(ValidationError);
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npx vitest run tests/journal.test.ts`
Expected: FAIL — cannot resolve `../src/journal.js`.

- [ ] **Step 3: Write the implementation**

Create `src/journal.ts`:

```ts
import { type Node, ValidationError } from "@nodes/kernel";
import { z } from "zod";
import { capturedDate, capturedOf, capturedSortKey } from "./captured.js";
import { THOUGHT } from "./kinds.js";

export interface JournalEntry {
	id: string;
	title: string;
	at: string;
}
export interface DayGroup {
	date: string;
	entries: JournalEntry[];
}
export interface DateWindow {
	since: string;
	until: string;
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/** YYYY-MM-DD with real-calendar validity (rejects 2026-13-01, 2026-02-30, non-leap 02-29).
 * Exported so the CLI reuses it (the CLI translates a failure to CliUsageError; journalView to
 * ValidationError — same schema, boundary-specific typed error). */
export const JournalDateSchema = z
	.string()
	.regex(DATE_RE, "expected a YYYY-MM-DD date")
	.refine((s) => {
		const [y, m, d] = s.split("-").map(Number);
		if (y < 1 || m < 1 || m > 12 || d < 1) return false;
		const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
		const maxDay = m === 2 && leap ? 29 : DAYS_IN_MONTH[m - 1];
		return d <= maxDay;
	}, "not a valid calendar date");

function bound(label: string, value: string): string {
	const r = JournalDateSchema.safeParse(value);
	if (!r.success) {
		throw new ValidationError(`journal ${label}: ${r.error.issues.map((i) => i.message).join("; ")}`);
	}
	return r.data;
}

export function journalView(thoughts: Node[], window: DateWindow): DayGroup[] {
	const since = bound("since", window.since);
	const until = bound("until", window.until);
	if (since > until) throw new ValidationError(`journal window: since ${since} is after until ${until}`);

	const rows = thoughts
		.filter((n) => n.kind === THOUGHT)
		.map((n) => {
			const at = capturedOf(n).at;
			return { id: n.id, title: n.title, at, date: capturedDate(at), key: capturedSortKey(at) };
		})
		.filter((r) => r.date >= since && r.date <= until)
		.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

	const groups: DayGroup[] = [];
	for (const r of rows) {
		let g = groups[groups.length - 1];
		if (g === undefined || g.date !== r.date) {
			g = { date: r.date, entries: [] };
			groups.push(g);
		}
		g.entries.push({ id: r.id, title: r.title, at: r.at });
	}
	return groups;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npx vitest run tests/journal.test.ts`
Expected: PASS.

- [ ] **Step 5: Add barrel exports**

In `src/index.ts`, add:

```ts
export { type DateWindow, type DayGroup, type JournalEntry, JournalDateSchema, journalView } from "./journal.js";
```

- [ ] **Step 6: Format + typecheck**

Run: `rtk npx @biomejs/biome check --write src/journal.ts src/index.ts tests/journal.test.ts && rtk npm run typecheck`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/journal.ts src/index.ts tests/journal.test.ts
git commit -m "feat(journal): pure journalView projection + JournalDateSchema"
```

---

### Task 3: Make time intrinsic + thread the clock

This task makes `captured` a required `thought` facet, makes `capture()` stamp it from a required `at`, threads an injected `now` through `runCli`, and updates every existing call site and fixture so the gate stays green. Splitting it would leave the build red between steps (a required `at` forces `cmdAdd` to have `now`, which forces the `runCli` signature change), so it lands as one atomic change.

**Files:**
- Modify: `src/kinds.ts` (thought `requiredFacets` + invariant)
- Modify: `src/api.ts` (`capture` stamps `captured` + `metadata.created` mirror)
- Modify: `src/cli.ts` (`runCli` gains `now`; `cmdAdd` stamps + `(date)` output)
- Modify: `src/bin.ts` (inject `localIso(new Date())`)
- Create: `tests/fixtures.ts` (shared `CAPTURE_AT` / `NOW`)
- Modify (test call sites): `tests/mindful-thoughts.test.ts`, `tests/mindful-journals.test.ts`, `tests/mindful-mindmaps.test.ts`, `tests/identity-integration.test.ts`, `tests/sprite-integration.test.ts`, `tests/cli.test.ts`, `tests/profile.test.ts`

**Interfaces:**
- Consumes: `./captured.js` (`CAPTURED`, `makeCaptured`, `capturedDate`, `localIso`, `requireValidCaptured`).
- Produces (relied on by Task 4):
  - `Mindful.capture(input: { title: string; body?: string; tags?: string[]; at: string }): Node`
  - `runCli(argv: string[], mindful: Mindful, root: string, env: NodeJS.ProcessEnv, now: string, out: Sink, err: Sink): number`
  - `tests/fixtures.ts`: `export const CAPTURE_AT = "2026-06-24T12:00:00Z"`, `export const NOW = "2026-06-24T12:00:00Z"`

- [ ] **Step 1: Add the required facet + invariant to `kinds.ts`**

In `src/kinds.ts`, add the import and extend `thoughtSpec`:

```ts
import type { KindSpec } from "@nodes/kernel";
import { CAPTURED, requireValidCaptured } from "./captured.js";
import { VISUAL_IDENTITY, requireValidVisualIdentity } from "./identity.js";

export const THOUGHT = "thought";
export const MINDMAP = "mindmap";
export const JOURNAL = "journal";

// thought (≈ note) requires its intrinsic visual identity (SP2) and capture time (SP7).
export const thoughtSpec: KindSpec = {
	name: THOUGHT,
	requiredFacets: new Set([VISUAL_IDENTITY, CAPTURED]),
	invariants: [requireValidVisualIdentity, requireValidCaptured],
};
export const mindmapSpec: KindSpec = { name: MINDMAP, shape: "graph" };
export const journalSpec: KindSpec = { name: JOURNAL, shape: "list" };
```

- [ ] **Step 2: Stamp `captured` in `capture()`**

In `src/api.ts`, add to the existing local imports:

```ts
import { CAPTURED, capturedDate, makeCaptured } from "./captured.js";
```

Replace the `capture` method body so it takes a required `at`, attaches the facet, and mirrors `metadata.created` (the rest of the method — tag resolution, single `corpus.add` — is unchanged):

```ts
	capture(input: { title: string; body?: string; tags?: string[]; at: string }): Node {
		const node = makeNode({ id: `${THOUGHT}:${newUid()}`, kind: THOUGHT, title: input.title, body: input.body ?? "" });
		// Intrinsic facets, attached before any tag resolution so the single write below persists a
		// complete, valid thought. makeCaptured validates `at` (ValidationError, not a raw ZodError)
		// before the write, joining identity + tags on the one atomic capture path.
		node.facets[VISUAL_IDENTITY] = deriveIdentity(node.uid);
		node.facets[CAPTURED] = makeCaptured(input.at);
		node.metadata.created = capturedDate(input.at); // derived coarse projection; `updated` untouched
		const idx = this.aliasIndex();
		for (const name of input.tags ?? []) node.relations.push(this.resolveTag(node.id, name, idx));
		this.corpus.add(node); // one write; nothing persists if `at` or a tag above threw
		return this.corpus.get(node.id);
	}
```

- [ ] **Step 3: Thread `now` through `runCli` + stamp in `cmdAdd`**

In `src/cli.ts`:

(a) Add to imports:

```ts
import { capturedDate } from "./captured.js";
```

(b) Change `cmdAdd` to take `now` and stamp + print `(date)`:

```ts
function cmdAdd(mindful: Mindful, rest: string[], out: Sink, root: string, env: NodeJS.ProcessEnv, now: string): number {
	const { values, positionals } = parseFlags(rest, {
		body: { type: "string" },
		tag: { type: "string", multiple: true },
	});
	if (positionals.length !== 1) throw new CliUsageError("add <title> [--body <text>] [--tag <name>]...");
	const { scheme } = resolveActiveScheme(root, env);
	const node = mindful.capture({
		title: positionals[0],
		body: values.body as string | undefined,
		tags: values.tag as string[] | undefined,
		at: now,
	});
	out(`added ${node.id} (${capturedDate(now)})\n${spriteToAnsi(mindful.sprite(node.id, scheme))}\n`);
	return 0;
}
```

(c) Change the `runCli` signature to add `now` between `env` and `out`, and pass it to `cmdAdd`:

```ts
export function runCli(
	argv: string[],
	mindful: Mindful,
	root: string,
	env: NodeJS.ProcessEnv,
	now: string,
	out: Sink,
	err: Sink,
): number {
	try {
		const [command, ...rest] = argv;
		switch (command) {
			case "add":
				return cmdAdd(mindful, rest, out, root, env, now);
			case "list":
				return cmdList(mindful, rest, out);
			case "show":
				return cmdShow(mindful, rest, out, root, env);
			case "search":
				return cmdSearch(mindful, rest, out);
			case "edit":
				return cmdEdit(mindful, rest, out);
			case "delete":
				return cmdDelete(mindful, rest, out);
			case "tag":
				return cmdTag(mindful, rest, out);
			case "scheme":
				return cmdScheme(rest, out, root, env);
			default:
				throw new CliUsageError(command === undefined ? "no command" : `unknown command ${JSON.stringify(command)}`);
		}
	} catch (e) {
		if (e instanceof CliUsageError) {
			err(`${e.message}\n\n${e.usage ?? USAGE}\n`);
			return 2;
		}
		if (e instanceof NodesError || e instanceof CliError || e instanceof ConfigError) {
			err(`error: ${(e as Error).message}\n`);
			return 1;
		}
		throw e;
	}
}
```

(The `journal` case is added in Task 4; leave the switch otherwise as-is.)

- [ ] **Step 4: Inject the clock in `bin.ts`**

In `src/bin.ts`, import `localIso` and compute `now`:

```ts
#!/usr/bin/env node
import { mkdirSync } from "node:fs";
import { Mindful } from "./api.js";
import { localIso } from "./captured.js";
import { resolveDataDir, runCli } from "./cli.js";

const root = resolveDataDir(process.env);
mkdirSync(root, { recursive: true });
const mindful = new Mindful(root);
const code = runCli(
	process.argv.slice(2),
	mindful,
	root,
	process.env,
	localIso(new Date()),
	(s) => {
		process.stdout.write(s);
	},
	(s) => {
		process.stderr.write(s);
	},
);
process.exitCode = code;
```

- [ ] **Step 5: Create the shared test fixture**

Create `tests/fixtures.ts`:

```ts
// Fixed capture instant for tests that don't care about time (Z is a valid explicit offset).
// capturedDate(CAPTURE_AT) === "2026-06-24"; capturedTime(CAPTURE_AT) === "12:00".
export const CAPTURE_AT = "2026-06-24T12:00:00Z";
// Injected clock for runCli in tests.
export const NOW = "2026-06-24T12:00:00Z";
```

- [ ] **Step 6: Add `at` to every `capture()` call (TypeScript enumerates them)**

Run `rtk npm run typecheck`. TypeScript reports every `.capture({ ... })` missing the now-required `at` (error TS2345/TS2741) across `src/` and `tests/`. For each reported call, add `at: CAPTURE_AT` (importing `CAPTURE_AT` from `./fixtures.js` at the top of each test file that needs it). Pattern:

```ts
// before
const t = m.capture({ title: "First", body: "hello" });
// after
const t = m.capture({ title: "First", body: "hello", at: CAPTURE_AT });
```

Files with `capture()` call sites to fix (all TS-caught — re-run typecheck until clean): `tests/mindful-thoughts.test.ts`, `tests/mindful-journals.test.ts`, `tests/mindful-mindmaps.test.ts`, `tests/identity-integration.test.ts`, `tests/sprite-integration.test.ts`, `tests/cli.test.ts`. (`src/cli.ts`'s `cmdAdd` already passes `at: now` from Step 3.)

- [ ] **Step 7: Add the `captured` facet to direct `makeNode` thought fixtures (NOT TS-caught)**

These build thought nodes by hand and expect `corpus.add`/`validate` to **succeed**; once `captured` is required they fail at runtime with `FacetError`. `node.facets` is a loose record, so TypeScript does **not** flag these — fix each explicitly by adding `[CAPTURED]: { at: CAPTURE_AT }` to its `facets`. Import `CAPTURED` from `../src/captured.js` and `CAPTURE_AT` from `./fixtures.js` in each file.

- `tests/sprite-integration.test.ts` — the `thought:fixture` node (currently `facets: { [VISUAL_IDENTITY]: {...} }`): add `[CAPTURED]: { at: CAPTURE_AT }` alongside `[VISUAL_IDENTITY]`.
- `tests/cli.test.ts` — the three hand-built thought nodes: `thought:abc`, `thought:abcdef` (the exact-vs-prefix test) and `thought:scheme-probe` (the scheme-rendering test): add `[CAPTURED]: { at: CAPTURE_AT }` to each `facets`.

Do **not** touch the deliberately-invalid fixtures that assert rejection — they must still throw: `tests/identity-integration.test.ts` `thought:bare` (no facets) and `thought:bad` (malformed identity), and `tests/profile.test.ts`'s "without visualIdentity" node. They still throw `FacetError` (now for a missing facet either way), so their assertions hold.

- [ ] **Step 8: Update `profile.test.ts` for the two required facets**

In `tests/profile.test.ts`, the SP2 "valid thought" test attaches only `visualIdentity` and expects validation to pass — it now needs `captured` too. Add imports and update that test, and add a `captured`-missing test:

```ts
import { CAPTURED } from "../src/captured.js";
import { CAPTURE_AT } from "./fixtures.js";
// ...
	it("a thought validates with valid visualIdentity + captured facets (SP2/SP7)", () => {
		const uid = "t1";
		const node = makeNode({ id: `${THOUGHT}:t1`, kind: THOUGHT, title: "T" });
		node.facets[VISUAL_IDENTITY] = deriveIdentity(uid);
		node.facets[CAPTURED] = { at: CAPTURE_AT };
		expect(() => reg().validate(node)).not.toThrow();
	});

	it("a thought without the captured facet fails validation (FacetError)", () => {
		const node = makeNode({ id: `${THOUGHT}:t1`, kind: THOUGHT, title: "T" });
		node.facets[VISUAL_IDENTITY] = deriveIdentity("t1");
		expect(() => reg().validate(node)).toThrow(FacetError);
	});
```

- [ ] **Step 9: Migrate the `cli.test.ts` `runCli` helpers + the `add` output assertion**

In `tests/cli.test.ts`:

(a) Import the fixture: `import { CAPTURE_AT, NOW } from "./fixtures.js";` (add `CAPTURE_AT` here too if Step 6 needs it in this file).

(b) Each `run`/`runEnv` helper closure (there are several, one per `describe` block) calls `runCli(argv, m, root, {}|env, (s) => out.push(s), (s) => err.push(s))`. Insert `NOW` between the env argument and the first sink. Example:

```ts
	const run = (...argv: string[]): number =>
		runCli(
			argv,
			m,
			root,
			{},
			NOW,
			(s) => out.push(s),
			(s) => err.push(s),
		);
	const runEnv = (env: NodeJS.ProcessEnv, ...argv: string[]): number =>
		runCli(
			argv,
			m,
			root,
			env,
			NOW,
			(s) => out.push(s),
			(s) => err.push(s),
		);
```

(c) The "add captures and prints id + sprite" test asserts `expect(s).toMatch(/^added thought:[0-9a-f]{32}\n/)`. The output now includes the date — update that one assertion to:

```ts
		expect(s).toMatch(/^added thought:[0-9a-f]{32} \(2026-06-24\)\n/);
```

(The line-222 `match(/added (thought:[0-9a-f]{32})/)` is a substring match and still works.)

- [ ] **Step 10: Add the capture-time API tests**

Append to `tests/mindful-thoughts.test.ts` (it already imports `ValidationError`; add `CAPTURE_AT` from `./fixtures.js` and `capturedDate` from `../src/captured.js`):

```ts
	it("capture stamps the captured facet and mirrors metadata.created (updated left null)", () => {
		const m = new Mindful(root);
		const t = m.capture({ title: "Dated", at: "2026-03-09T08:30:00-05:00" });
		expect(m.get(t.id).facets.captured).toEqual({ at: "2026-03-09T08:30:00-05:00" });
		expect(m.get(t.id).metadata.created).toBe("2026-03-09");
		expect(m.get(t.id).metadata.updated).toBeNull();
	});

	it("capture with a malformed at throws ValidationError and persists nothing (atomic)", () => {
		const m = new Mindful(root);
		const target = m.capture({ title: "Target", at: CAPTURE_AT });
		expect(() => m.capture({ title: "Bad", tags: ["Target"], at: "not-a-date" })).toThrow(ValidationError);
		expect(m.allThoughts().map((x) => x.title)).toEqual(["Target"]); // only the valid one survived
	});
```

- [ ] **Step 11: Run the full gate**

Run: `rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`
Expected: all tests pass; typecheck clean; biome `check` reports no fixes needed (run `rtk npx @biomejs/biome check --write src tests` first if it flags formatting); build emits `dist/`.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat(capture): captured is a required thought facet; inject the clock via runCli now"
```

---

### Task 4: `journal` CLI command

**Files:**
- Modify: `src/cli.ts` (`JOURNAL_USAGE`, `cmdJournal`, `USAGE` line, dispatch case)
- Modify: `tests/cli.test.ts` (new `journal` describe block)

**Interfaces:**
- Consumes: `./journal.js` (`type DateWindow`, `JournalDateSchema`, `journalView`), `./captured.js` (`capturedDate`, `capturedTime`), `Mindful.allThoughts()`, the Task 3 `runCli(now)` signature.
- Produces: a top-level `journal` command.

- [ ] **Step 1: Write the failing tests**

Append a new `describe` block to `tests/cli.test.ts` (uses the Task 3 fixture import):

```ts
describe("runCli — journal command", () => {
	let root: string;
	let out: string[];
	let err: string[];
	let m: Mindful;

	beforeEach(() => {
		root = mkdtempSync(join(tmpdir(), "mindful-cli-"));
		out = [];
		err = [];
		m = new Mindful(root);
	});
	afterEach(() => rmSync(root, { recursive: true, force: true }));

	const runNow = (now: string, ...argv: string[]): number =>
		runCli(
			argv,
			m,
			root,
			{},
			now,
			(s) => out.push(s),
			(s) => err.push(s),
		);
	const run = (...argv: string[]): number => runNow(NOW, ...argv);
	const stdout = () => out.join("");
	const stderr = () => err.join("");

	it("with no args lists today, oldest-first, HH:MM + id + title", () => {
		const a = m.capture({ title: "morning idea", at: "2026-06-24T09:14:00Z" });
		const b = m.capture({ title: "evening note", at: "2026-06-24T21:02:00Z" });
		expect(runNow("2026-06-24T23:00:00Z", "journal")).toBe(0);
		expect(stdout()).toBe(`2026-06-24\n  09:14  ${a.id}  morning idea\n  21:02  ${b.id}  evening note\n`);
	});

	it("a single <date> lists only that day", () => {
		m.capture({ title: "old", at: "2026-06-20T10:00:00Z" });
		const t = m.capture({ title: "target day", at: "2026-06-24T08:00:00Z" });
		expect(run("journal", "2026-06-24")).toBe(0);
		expect(stdout()).toBe(`2026-06-24\n  08:00  ${t.id}  target day\n`);
	});

	it("a --since/--until range groups each day, blank-line separated", () => {
		const a = m.capture({ title: "day one", at: "2026-06-24T10:00:00Z" });
		const b = m.capture({ title: "day two", at: "2026-06-25T08:30:00Z" });
		expect(run("journal", "--since", "2026-06-24", "--until", "2026-06-25")).toBe(0);
		expect(stdout()).toBe(
			`2026-06-24\n  10:00  ${a.id}  day one\n\n2026-06-25\n  08:30  ${b.id}  day two\n`,
		);
	});

	it("renders HH:MM from the captured offset, not the runtime TZ", () => {
		const a = m.capture({ title: "tz", at: "2026-06-24T09:14:00-04:00" });
		expect(runNow("2026-06-24T12:00:00Z", "journal", "2026-06-24")).toBe(0);
		expect(stdout()).toContain(`  09:14  ${a.id}  tz`);
	});

	it("empty single day → friendly stdout message, exit 0", () => {
		expect(runNow("2026-06-24T12:00:00Z", "journal", "2026-06-20")).toBe(0);
		expect(stdout()).toBe("no thoughts on 2026-06-20\n");
	});

	it("empty range → friendly stdout message, exit 0", () => {
		expect(run("journal", "--since", "2026-06-01", "--until", "2026-06-05")).toBe(0);
		expect(stdout()).toBe("no thoughts from 2026-06-01 to 2026-06-05\n");
	});

	it("bad arguments → exit 2 with journal usage", () => {
		expect(run("journal", "2026-13-99")).toBe(2); // malformed date
		expect(run("journal", "--since", "2026-06-01")).toBe(2); // until missing
		expect(run("journal", "--until", "2026-06-05")).toBe(2); // since missing
		expect(run("journal", "--since", "2026-06-01", "--since", "2026-06-02", "--until", "2026-06-05")).toBe(2); // dup
		expect(run("journal", "2026-06-01", "--since", "2026-06-01", "--until", "2026-06-05")).toBe(2); // positional + flags
		expect(run("journal", "--since", "2026-06-05", "--until", "2026-06-01")).toBe(2); // since > until
		expect(run("journal", "a", "b")).toBe(2); // too many positionals
		expect(stderr()).toContain("mindful journal");
		expect(stdout()).toBe("");
	});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npx vitest run tests/cli.test.ts -t "journal command"`
Expected: FAIL — `journal` is an unknown command (exit 2 for the happy-path cases, which expect 0).

- [ ] **Step 3: Implement the command**

In `src/cli.ts`:

(a) Add imports:

```ts
import { capturedDate, capturedTime } from "./captured.js";
import { type DateWindow, JournalDateSchema, journalView } from "./journal.js";
```

(Merge with the existing `./captured.js` import added in Task 3 — a single import line: `import { capturedDate, capturedTime } from "./captured.js";`. biome flags duplicate imports from the same module.)

(b) Add the `JOURNAL_USAGE` constant next to `SCHEME_USAGE`:

```ts
const JOURNAL_USAGE = `usage: mindful journal [<date>] | mindful journal --since <date> --until <date>

  journal                            thoughts captured today
  journal <date>                     thoughts captured on <date> (YYYY-MM-DD)
  journal --since <a> --until <b>    thoughts captured from <a> through <b>`;
```

(c) Add the `journal` line to the top-level `USAGE` (after the `tag` line, before `scheme`):

```ts
const USAGE = `usage: mindful <command> [args]

commands:
  add <title> [--body <text>] [--tag <name>]...
  show <ref>
  list
  search <query> [--limit <n>]
  edit <ref> [--title <text>] [--body <text>]
  delete <ref>
  tag <ref> <name>
  journal [<date>] | journal --since <date> --until <date>
  scheme <list|set|show>`;
```

(d) Add a `journalDate` helper (CLI-boundary translation → `CliUsageError`) and `cmdJournal`, near the other `cmd*` functions:

```ts
function journalDate(s: string): string {
	const r = JournalDateSchema.safeParse(s);
	if (!r.success) throw new CliUsageError(`journal: invalid date ${JSON.stringify(s)}`, JOURNAL_USAGE);
	return r.data;
}

function cmdJournal(mindful: Mindful, rest: string[], out: Sink, now: string): number {
	const { values, positionals } = parseFlags(rest, { since: { type: "string" }, until: { type: "string" } });
	const since = values.since as string | undefined;
	const until = values.until as string | undefined;
	let window: DateWindow;
	if (since !== undefined || until !== undefined) {
		if (positionals.length !== 0) throw new CliUsageError("journal: <date> cannot combine with --since/--until", JOURNAL_USAGE);
		if (since === undefined || until === undefined) {
			throw new CliUsageError("journal: --since and --until are required together", JOURNAL_USAGE);
		}
		window = { since: journalDate(since), until: journalDate(until) };
		if (window.since > window.until) {
			throw new CliUsageError(`journal: --since ${window.since} is after --until ${window.until}`, JOURNAL_USAGE);
		}
	} else {
		if (positionals.length > 1) throw new CliUsageError("journal takes at most one <date>", JOURNAL_USAGE);
		const date = positionals.length === 1 ? journalDate(positionals[0]) : capturedDate(now);
		window = { since: date, until: date };
	}
	const groups = journalView(mindful.allThoughts(), window);
	if (groups.length === 0) {
		out(
			window.since === window.until
				? `no thoughts on ${window.since}\n`
				: `no thoughts from ${window.since} to ${window.until}\n`,
		);
		return 0;
	}
	const blocks = groups.map(
		(g) => `${g.date}\n${g.entries.map((e) => `  ${capturedTime(e.at)}  ${e.id}  ${e.title}`).join("\n")}`,
	);
	out(`${blocks.join("\n\n")}\n`);
	return 0;
}
```

(e) Add the dispatch case in `runCli`'s switch (after `tag`, before `scheme`):

```ts
			case "journal":
				return cmdJournal(mindful, rest, out, now);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk npx vitest run tests/cli.test.ts -t "journal command"`
Expected: PASS.

- [ ] **Step 5: Run the full gate**

Run: `rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`
Expected: all green (run `rtk npx @biomejs/biome check --write src/cli.ts tests/cli.test.ts` first if formatting is flagged).

- [ ] **Step 6: Commit**

```bash
git add src/cli.ts tests/cli.test.ts
git commit -m "feat(cli): journal command — today / <date> / --since..--until, friendly empty message"
```

---

## Self-Review

**Spec coverage:**
- §3 `captured.ts` (facet, `makeCaptured`, `capturedOf`, `requireValidCaptured`, `capturedDate`/`capturedTime`/`capturedSortKey`, `localIso`) → Task 1.
- §3 `journal.ts` (`journalView`, types, `JournalDateSchema`) → Task 2.
- §3 `kinds.ts` invariant, `api.ts` capture stamping + `metadata.created` mirror, `cli.ts` `runCli(now)`/`cmdAdd`, `bin.ts` injection, barrel → Task 3 (barrel split into Tasks 1/2).
- §5 `journal` command (today / date / range, arg rules, output, empty message) → Task 4.
- §7 zod→typed-error translation: `makeCaptured`→ValidationError (T1), `capturedOf`→FacetError (T1), `journalView` bounds→ValidationError (T2), CLI dates→CliUsageError (T4).
- §8 tests: captured schema/helpers/sort-key/localIso (T1), journal projection incl. fractional + wall-time-not-UTC (T2), capture API + atomic + metadata mirror (T3), profile two-facet + missing-captured (T3), journal CLI incl. TZ-independent HH:MM + all exit-2 cases + empty messages (T4).

**Placeholder scan:** none — every code step shows complete code. Step 6/7 of Task 3 are a TS-guided/enumerated mechanical transform with the exact value (`CAPTURE_AT`) and an explicit file/fixture list, not a vague "fix the rest."

**Type consistency:** `capture({…, at})` (T3) matches the `at: now` call in `cmdAdd` (T3) and `at: CAPTURE_AT` in tests; `runCli(argv, mindful, root, env, now, out, err)` is identical across `bin.ts` (T3), the migrated helpers (T3), and `cmdJournal`'s `now` (T4); `journalView(thoughts, window)` / `DateWindow` / `capturedTime` / `capturedDate` names match between T2, T4, and the spec.

## Execution Handoff

Plan complete. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, spec+quality review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Which approach?
