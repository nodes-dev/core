# Mindful v6 SP2 — Visual Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every `thought` a deterministic, color-free `visualIdentity` facet derived from its immutable `uid`, plus a swappable `Colorscheme` and a pure resolver that maps an identity to concrete colors.

**Architecture:** Three units in `~/d/mindful/v6`, no kernel changes. `identity.ts` owns the intrinsic fingerprint (derivation + facet schema + accessor + invariant). `color.ts` owns the theme layer (`Colorscheme` + built-in default + pure `resolve` + HSL transforms). The integration task wires the facet onto `thoughtSpec` and makes `capture` attach it atomically, then adds `Mindful.palette`. The kernel already composes **kind-level** required facets + invariants in `Registry.validate`, so a "visual identity" — a domain concept — stays entirely in mindful.

**Tech Stack:** TypeScript (Node ≥20, ESM, `.js` import extensions), zod, biome (line width 120), vitest, `node:crypto` (SHA-256). Consumes `@nodes/kernel` over a `file:` dependency.

**Spec:** `~/d/nodes/docs/specs/2026-06-24-mindful-v6-sp2-visual-identity-design.md` (committed `cd87acd`).

## Global Constraints

- **No kernel changes.** All work is in `~/d/mindful/v6`. Dependency stays one-way (`mindful → @nodes/kernel`); never edit `~/d/nodes/ts`.
- **All git/npm/tooling via the `rtk` wrapper**, run from `~/d/mindful/v6`. Gate = `rtk npm test && rtk npm run typecheck && rtk npm run check`.
- **TOOLING NOTE:** `grep`/`rg` give corrupted results in this environment — use file reads, not grep, to inspect code.
- **Identity is intrinsic and immutable:** a pure deterministic function of the thought's persistent `uid`. `edit` must never change it.
- **Stored facet is the source of truth:** validation checks structure only; never recompute-and-compare against the derivation.
- **Color-free identity:** the facet holds `{ seed, slots }`; `slots[i].index` is a raw `0–255` selector, not a scheme position. `resolve` reduces it modulo scheme length.
- **Fail early; shape errors are `FacetError`:** all structural constraints live in the zod schema, surfaced via a `load`-style accessor like `membershipOf`. No `InvariantError` path in SP2.
- **`resolve` fails fast** (a thrown `Error`) on an empty scheme or a selected color that is not a valid `#rrggbb` string — no fall-through to undefined HSL behavior.
- **Atomic capture preserved:** `capture` keeps SP1's single-write, resolve-tags-first pattern; the identity is attached before the one `corpus.add`.
- **Greenfield, no migration:** the mindful store has no persisted data (only temp-dir tests).
- **biome will reformat** transcribed code (tabs, import sorting) on `--fix`; that is expected and self-corrects. Production HSL helpers (`hexToHsl`/`hslToHex`) stay module-private (not exported, not imported by tests).

---

### Task 1: Identity module — derivation, facet schema, accessor, invariant

**Files:**
- Create: `~/d/mindful/v6/src/identity.ts`
- Modify: `~/d/mindful/v6/package.json` (add `zod` direct dependency)
- Modify: `~/d/mindful/v6/src/index.ts` (export the identity surface)
- Test: `~/d/mindful/v6/tests/identity.test.ts`

**Interfaces:**
- Consumes: `FacetError`, `type Node`, `makeNode` (`@nodes/kernel`); `z` (`zod`).
- Produces:
  - `VISUAL_IDENTITY = "visualIdentity"` (string const).
  - `VisualIdentitySchema`, `ColorSlotSchema` (zod schemas); `type VisualIdentity = { seed: string; slots: ColorSlot[] }`, `type ColorSlot = { index: number; variant: number }`.
  - `deriveIdentity(uid: string): VisualIdentity` — pure, deterministic.
  - `visualIdentityOf(node: Node): VisualIdentity` — throws `FacetError` if the facet is missing or malformed.
  - `requireValidVisualIdentity(node: Node): void` — kind-level invariant (calls `visualIdentityOf`).

- [ ] **Step 1: Add zod as a direct dependency and install**

zod currently resolves only as a hoisted transitive dep of `@nodes/kernel`; depend on it explicitly. Edit `~/d/mindful/v6/package.json` so the `dependencies` block reads exactly:

```json
  "dependencies": {
    "@nodes/kernel": "file:../../nodes/ts",
    "zod": "^3.23.0"
  },
```

Then install:

```bash
cd ~/d/mindful/v6 && rtk npm install
```
Expected: exits 0; `zod` now resolvable directly from the package. Verify:
```bash
cd ~/d/mindful/v6 && node -e "console.log(require.resolve('zod'))"
```
Expected: prints a path under `~/d/mindful/v6/node_modules/zod` (or a hoisted location the package controls), exit 0.

- [ ] **Step 2: Write the failing test `tests/identity.test.ts`**

```ts
import { createHash } from "node:crypto";
import { FacetError, makeNode } from "@nodes/kernel";
import { describe, expect, it } from "vitest";
import { VISUAL_IDENTITY, deriveIdentity, requireValidVisualIdentity, visualIdentityOf } from "../src/identity.js";

const UID = "0123456789abcdef0123456789abcdef";

function thoughtWith(identity: unknown) {
	return makeNode({ id: "thought:t1", kind: "thought", title: "T", facets: { [VISUAL_IDENTITY]: identity } });
}

describe("deriveIdentity", () => {
	it("is deterministic: same uid → identical identity", () => {
		expect(deriveIdentity(UID)).toEqual(deriveIdentity(UID));
	});

	it("differs for different uids", () => {
		expect(deriveIdentity(UID)).not.toEqual(deriveIdentity(`${UID}f`));
	});

	it("produces a 64-char sha256 hex seed and exactly 4 in-range slots", () => {
		const id = deriveIdentity(UID);
		expect(id.seed).toMatch(/^[0-9a-f]{64}$/);
		expect(id.slots).toHaveLength(4);
		for (const slot of id.slots) {
			expect(Number.isInteger(slot.index)).toBe(true);
			expect(slot.index).toBeGreaterThanOrEqual(0);
			expect(slot.index).toBeLessThanOrEqual(255);
			expect([0, 1, 2, 3]).toContain(slot.variant);
		}
	});

	it("reads index and variant from separate digest bytes", () => {
		const buf = createHash("sha256").update(UID).digest();
		const id = deriveIdentity(UID);
		expect(id.seed).toBe(buf.toString("hex"));
		for (let i = 0; i < 4; i++) {
			expect(id.slots[i].index).toBe(buf[i * 2]);
			expect(id.slots[i].variant).toBe(buf[i * 2 + 1] % 4);
		}
	});
});

describe("visualIdentityOf / requireValidVisualIdentity", () => {
	it("reads back a valid identity facet", () => {
		const id = deriveIdentity(UID);
		const node = thoughtWith(id);
		expect(visualIdentityOf(node)).toEqual(id);
		expect(() => requireValidVisualIdentity(node)).not.toThrow();
	});

	it("throws FacetError when the facet is missing", () => {
		const node = makeNode({ id: "thought:t1", kind: "thought", title: "T" });
		expect(() => visualIdentityOf(node)).toThrow(FacetError);
		expect(() => requireValidVisualIdentity(node)).toThrow(FacetError);
	});

	it("throws FacetError on a malformed identity (bad seed, wrong slot count, out-of-range)", () => {
		const good = deriveIdentity(UID);
		expect(() => visualIdentityOf(thoughtWith({ seed: "abc", slots: good.slots }))).toThrow(FacetError);
		expect(() => visualIdentityOf(thoughtWith({ seed: good.seed, slots: good.slots.slice(0, 3) }))).toThrow(
			FacetError,
		);
		expect(() =>
			visualIdentityOf(thoughtWith({ seed: good.seed, slots: [{ index: 256, variant: 0 }, ...good.slots.slice(1)] })),
		).toThrow(FacetError);
		expect(() =>
			visualIdentityOf(thoughtWith({ seed: good.seed, slots: [{ index: 0, variant: 4 }, ...good.slots.slice(1)] })),
		).toThrow(FacetError);
	});
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/identity.test.ts`
Expected: FAIL — `../src/identity.js` does not exist.

- [ ] **Step 4: Write `src/identity.ts`**

```ts
import { createHash } from "node:crypto";
import { FacetError, type Node } from "@nodes/kernel";
import { z } from "zod";

export const VISUAL_IDENTITY = "visualIdentity";

export const ColorSlotSchema = z.object({
	index: z.number().int().min(0).max(255),
	variant: z.number().int().min(0).max(3),
});
export const VisualIdentitySchema = z.object({
	seed: z.string().regex(/^[0-9a-f]{64}$/, "seed must be a 64-char SHA-256 hex string"),
	slots: z.array(ColorSlotSchema).length(4, "exactly 4 slots required"),
});

export type ColorSlot = z.infer<typeof ColorSlotSchema>;
export type VisualIdentity = z.infer<typeof VisualIdentitySchema>;

/** Deterministic, color-free identity derived from a thought's immutable uid.
 * `index` and `variant` come from separate digest bytes so the two visual dimensions vary independently. */
export function deriveIdentity(uid: string): VisualIdentity {
	const buf = createHash("sha256").update(uid).digest();
	const seed = buf.toString("hex");
	const slots: ColorSlot[] = [];
	for (let i = 0; i < 4; i++) {
		slots.push({ index: buf[i * 2], variant: buf[i * 2 + 1] % 4 });
	}
	return { seed, slots };
}

/** Load + validate the visualIdentity facet. Mirrors the kernel's private `load` pattern:
 * a missing or malformed facet is a shape error → FacetError (never InvariantError). */
export function visualIdentityOf(node: Node): VisualIdentity {
	const raw = node.facets[VISUAL_IDENTITY];
	if (raw === undefined) throw new FacetError(`${node.id}: missing '${VISUAL_IDENTITY}' facet`);
	const result = VisualIdentitySchema.safeParse(raw);
	if (!result.success) {
		throw new FacetError(
			`${node.id}: invalid '${VISUAL_IDENTITY}' facet: ${result.error.issues.map((i) => i.message).join("; ")}`,
		);
	}
	return result.data;
}

/** Kind-level invariant for `thought`: forces schema validation during Registry.validate.
 * All constraints are structural, so this surfaces FacetError; no semantic (InvariantError) rule remains in SP2. */
export function requireValidVisualIdentity(node: Node): void {
	visualIdentityOf(node);
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/identity.test.ts`
Expected: PASS (all cases).

- [ ] **Step 6: Export the identity surface from the barrel `src/index.ts`**

Add this line to `~/d/mindful/v6/src/index.ts` (after the existing exports):

```ts
export {
	VISUAL_IDENTITY,
	VisualIdentitySchema,
	ColorSlotSchema,
	type VisualIdentity,
	type ColorSlot,
	deriveIdentity,
	visualIdentityOf,
	requireValidVisualIdentity,
} from "./identity.js";
```

- [ ] **Step 7: Run the full gate**

Run: `cd ~/d/mindful/v6 && rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green (existing 31 tests + the new identity tests; typecheck clean; biome clean). biome may reformat `identity.ts`/`index.ts` on a prior `--fix`; if `check` reports formatting, run `rtk npx biome check --write .` and re-run the gate.

- [ ] **Step 8: Commit**

```bash
cd ~/d/mindful/v6 && rtk git add package.json package-lock.json src/identity.ts src/index.ts tests/identity.test.ts
rtk git commit -m "feat: visualIdentity derivation + facet schema/accessor (identity.ts)"
```

---

### Task 2: Color module — Colorscheme, default scheme, pure resolver

**Files:**
- Create: `~/d/mindful/v6/src/color.ts`
- Modify: `~/d/mindful/v6/src/index.ts` (export the color surface)
- Test: `~/d/mindful/v6/tests/color.test.ts`

**Interfaces:**
- Consumes: `type VisualIdentity` (`./identity.js`).
- Produces:
  - `type Colorscheme = { name: string; colors: string[] }`.
  - `defaultColorscheme: Colorscheme` — a 16-color `chiptune-16` palette.
  - `resolve(identity: VisualIdentity, scheme?: Colorscheme): string[]` — pure; returns 4 `#rrggbb`; defaults to `defaultColorscheme`; throws on an empty scheme or a malformed selected color.
  - Module-private (NOT exported): `applyVariant`, `hexToHsl`, `hslToHex`.

- [ ] **Step 1: Write the failing test `tests/color.test.ts`**

```ts
import { describe, expect, it } from "vitest";
import type { VisualIdentity } from "../src/identity.js";
import { type Colorscheme, defaultColorscheme, resolve } from "../src/color.js";

// Test-local hex→HSL (production helper is module-private and must not be imported).
function hsl(hex: string): { h: number; s: number; l: number } {
	const r = Number.parseInt(hex.slice(1, 3), 16) / 255;
	const g = Number.parseInt(hex.slice(3, 5), 16) / 255;
	const b = Number.parseInt(hex.slice(5, 7), 16) / 255;
	const max = Math.max(r, g, b);
	const min = Math.min(r, g, b);
	const l = (max + min) / 2;
	let h = 0;
	let s = 0;
	const d = max - min;
	if (d !== 0) {
		s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
		if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
		else if (max === g) h = (b - r) / d + 2;
		else h = (r - g) / d + 4;
		h *= 60;
	}
	return { h, s, l };
}

// identity whose 4 slots all select colors[0] (index 0) but apply variants 0..3
function variantProbe(): VisualIdentity {
	return {
		seed: "0".repeat(64),
		slots: [
			{ index: 0, variant: 0 },
			{ index: 0, variant: 1 },
			{ index: 0, variant: 2 },
			{ index: 0, variant: 3 },
		],
	};
}

describe("defaultColorscheme", () => {
	it("is a non-empty list of valid #rrggbb colors", () => {
		expect(defaultColorscheme.colors.length).toBeGreaterThan(0);
		for (const c of defaultColorscheme.colors) expect(c).toMatch(/^#[0-9a-f]{6}$/);
	});
});

describe("resolve", () => {
	it("returns exactly 4 #rrggbb colors", () => {
		const out = resolve(variantProbe());
		expect(out).toHaveLength(4);
		for (const c of out) expect(c).toMatch(/^#[0-9a-f]{6}$/);
	});

	it("variant 0 returns the base entry unchanged; 1/2 shift lightness; 3 rotates hue ~180°", () => {
		const scheme: Colorscheme = { name: "probe", colors: ["#3366cc"] };
		const [base, light, dark, accent] = resolve(variantProbe(), scheme);
		expect(base).toBe("#3366cc"); // unchanged
		expect(hsl(light).l).toBeGreaterThan(hsl(base).l); // lighter
		expect(hsl(dark).l).toBeLessThan(hsl(base).l); // darker
		// circular hue distance from 180° (complementary), tolerant of 8-bit rounding
		const raw = (((hsl(accent).h - hsl(base).h) % 360) + 360) % 360;
		expect(Math.abs(raw - 180)).toBeLessThan(2);
	});

	it("is scheme-size independent (index % length) and re-themes under a different scheme", () => {
		const id: VisualIdentity = {
			seed: "0".repeat(64),
			slots: [
				{ index: 5, variant: 0 },
				{ index: 21, variant: 0 },
				{ index: 200, variant: 0 },
				{ index: 17, variant: 0 },
			],
		};
		const small: Colorscheme = { name: "s", colors: ["#111111", "#222222", "#333333", "#444444"] };
		const outDefault = resolve(id, defaultColorscheme);
		const outSmall = resolve(id, small);
		expect(outDefault).toHaveLength(4);
		expect(outSmall).toHaveLength(4);
		expect(outSmall).not.toEqual(outDefault); // same identity, different scheme → different colors
	});

	it("uses defaultColorscheme when no scheme is passed", () => {
		expect(resolve(variantProbe())).toEqual(resolve(variantProbe(), defaultColorscheme));
	});

	it("throws on an empty scheme", () => {
		expect(() => resolve(variantProbe(), { name: "empty", colors: [] })).toThrow();
	});

	it("throws on a malformed selected color (no fall-through to HSL)", () => {
		expect(() => resolve(variantProbe(), { name: "bad", colors: ["notacolor"] })).toThrow();
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/color.test.ts`
Expected: FAIL — `../src/color.js` does not exist.

- [ ] **Step 3: Write `src/color.ts`**

```ts
import type { VisualIdentity } from "./identity.js";

export interface Colorscheme {
	name: string;
	colors: string[]; // #rrggbb entries
}

/** Built-in default palette: a fixed 16-color chiptune-style scheme.
 * The renderer (SP3) decides what each slot is for; SP2 only needs a real, non-empty scheme. */
export const defaultColorscheme: Colorscheme = {
	name: "chiptune-16",
	colors: [
		"#000000",
		"#1d2b53",
		"#7e2553",
		"#008751",
		"#ab5236",
		"#5f574f",
		"#c2c3c7",
		"#fff1e8",
		"#ff004d",
		"#ffa300",
		"#ffec27",
		"#00e436",
		"#29adff",
		"#83769c",
		"#ff77a8",
		"#ffccaa",
	],
};

const HEX_RE = /^#[0-9a-fA-F]{6}$/;
const LIGHT_STEP = 0.2;

function hexToHsl(hex: string): { h: number; s: number; l: number } {
	const r = Number.parseInt(hex.slice(1, 3), 16) / 255;
	const g = Number.parseInt(hex.slice(3, 5), 16) / 255;
	const b = Number.parseInt(hex.slice(5, 7), 16) / 255;
	const max = Math.max(r, g, b);
	const min = Math.min(r, g, b);
	const l = (max + min) / 2;
	let h = 0;
	let s = 0;
	const d = max - min;
	if (d !== 0) {
		s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
		if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
		else if (max === g) h = (b - r) / d + 2;
		else h = (r - g) / d + 4;
		h *= 60;
	}
	return { h, s, l };
}

function hslToHex(h: number, s: number, l: number): string {
	const hue = ((h % 360) + 360) % 360;
	const c = (1 - Math.abs(2 * l - 1)) * s;
	const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
	const m = l - c / 2;
	let r = 0;
	let g = 0;
	let b = 0;
	if (hue < 60) [r, g, b] = [c, x, 0];
	else if (hue < 120) [r, g, b] = [x, c, 0];
	else if (hue < 180) [r, g, b] = [0, c, x];
	else if (hue < 240) [r, g, b] = [0, x, c];
	else if (hue < 300) [r, g, b] = [x, 0, c];
	else [r, g, b] = [c, 0, x];
	const to = (v: number): string =>
		Math.round((v + m) * 255)
			.toString(16)
			.padStart(2, "0");
	return `#${to(r)}${to(g)}${to(b)}`;
}

/** Apply a slot's variant transform to a base color: 0 base, 1 light, 2 dark, 3 accent (hue+180°). */
function applyVariant(hex: string, variant: number): string {
	if (variant === 0) return hex.toLowerCase();
	const { h, s, l } = hexToHsl(hex);
	if (variant === 1) return hslToHex(h, s, Math.min(1, l + LIGHT_STEP));
	if (variant === 2) return hslToHex(h, s, Math.max(0, l - LIGHT_STEP));
	return hslToHex(h + 180, s, l); // variant === 3
}

/** Resolve an identity's 4 color-free slots to 4 concrete #rrggbb colors against a chosen scheme.
 * Scheme-size independent (index % length). Fails fast on an empty scheme or a malformed color. */
export function resolve(identity: VisualIdentity, scheme: Colorscheme = defaultColorscheme): string[] {
	if (scheme.colors.length === 0) throw new Error(`colorscheme ${JSON.stringify(scheme.name)} has no colors`);
	return identity.slots.map((slot) => {
		const base = scheme.colors[slot.index % scheme.colors.length];
		if (!HEX_RE.test(base)) {
			throw new Error(`colorscheme ${JSON.stringify(scheme.name)} has invalid color ${JSON.stringify(base)}`);
		}
		return applyVariant(base, slot.variant);
	});
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/color.test.ts`
Expected: PASS (all cases).

- [ ] **Step 5: Export the color surface from the barrel `src/index.ts`**

Add this line to `~/d/mindful/v6/src/index.ts`:

```ts
export { type Colorscheme, defaultColorscheme, resolve } from "./color.js";
```

- [ ] **Step 6: Run the full gate**

Run: `cd ~/d/mindful/v6 && rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green. If biome reports formatting in `color.ts`/`index.ts`, run `rtk npx biome check --write .` and re-run the gate.

- [ ] **Step 7: Commit**

```bash
cd ~/d/mindful/v6 && rtk git add src/color.ts src/index.ts tests/color.test.ts
rtk git commit -m "feat: Colorscheme + default chiptune-16 scheme + pure resolve (color.ts)"
```

---

### Task 3: Integration — require the facet on `thought`, attach it in `capture`, add `Mindful.palette`

**Files:**
- Modify: `~/d/mindful/v6/src/kinds.ts` (thoughtSpec gains required facet + invariant)
- Modify: `~/d/mindful/v6/src/api.ts` (capture attaches identity; add `palette`)
- Test: `~/d/mindful/v6/tests/identity-integration.test.ts`

**Interfaces:**
- Consumes: `VISUAL_IDENTITY`, `deriveIdentity`, `visualIdentityOf` (`./identity.js`); `type Colorscheme`, `defaultColorscheme`, `resolve` (`./color.js`); `requireValidVisualIdentity` (`./identity.js`, used in `kinds.ts`).
- Produces: `thoughtSpec` with `requiredFacets: new Set([VISUAL_IDENTITY])` + `invariants: [requireValidVisualIdentity]`; `capture` that persists a valid identity; `Mindful.palette(thoughtId: string, scheme?: Colorscheme): string[]`.

> **Why this is one task:** the moment `thoughtSpec` requires `visualIdentity`, every `capture` in the existing suite would fail validation unless `capture` also attaches the facet. Both edits must land in the same commit so the suite stays green.

- [ ] **Step 1: Write the failing test `tests/identity-integration.test.ts`**

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { FacetError, makeNode } from "@nodes/kernel";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Mindful } from "../src/api.js";
import { VISUAL_IDENTITY, deriveIdentity, visualIdentityOf } from "../src/identity.js";
import { defaultColorscheme, resolve } from "../src/color.js";

let root: string;
beforeEach(() => {
	root = mkdtempSync(join(tmpdir(), "mindful-identity-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("Mindful — visual identity integration", () => {
	it("capture attaches the uid-derived identity", () => {
		const m = new Mindful(root);
		const t = m.capture({ title: "First" });
		expect(visualIdentityOf(t)).toEqual(deriveIdentity(t.uid));
	});

	it("identity is stable across edits (title and body)", () => {
		const m = new Mindful(root);
		const t = m.capture({ title: "Draft" });
		const before = visualIdentityOf(t);
		m.edit(t.id, { title: "Renamed", body: "new body" });
		expect(visualIdentityOf(m.get(t.id))).toEqual(before);
	});

	it("identity round-trips on disk through a fresh Mindful instance", () => {
		const m1 = new Mindful(root);
		const t = m1.capture({ title: "Persisted" });
		const expected = visualIdentityOf(t);
		const m2 = new Mindful(root); // reads from disk
		expect(visualIdentityOf(m2.get(t.id))).toEqual(expected);
	});

	it("a thought without the visualIdentity facet fails validation (FacetError)", () => {
		const m = new Mindful(root);
		const bare = makeNode({ id: "thought:bare", kind: "thought", title: "Bare" });
		expect(() => m.corpus.add(bare)).toThrow(FacetError);
	});

	it("a thought with a malformed identity fails validation (FacetError)", () => {
		const m = new Mindful(root);
		const bad = makeNode({
			id: "thought:bad",
			kind: "thought",
			title: "Bad",
			facets: { [VISUAL_IDENTITY]: { seed: "abc", slots: [] } },
		});
		expect(() => m.corpus.add(bad)).toThrow(FacetError);
	});

	it("palette() returns 4 colors and re-themes under a different scheme", () => {
		const m = new Mindful(root);
		const t = m.capture({ title: "Color me" });
		const withDefault = m.palette(t.id);
		expect(withDefault).toEqual(resolve(visualIdentityOf(t), defaultColorscheme));
		expect(withDefault).toHaveLength(4);
		const other = { name: "mono", colors: ["#101010", "#f0f0f0"] };
		expect(m.palette(t.id, other)).not.toEqual(withDefault);
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/identity-integration.test.ts`
Expected: FAIL — `m.palette` is not a function (and capture does not yet attach the facet).

- [ ] **Step 3: Wire the facet onto `thoughtSpec` in `src/kinds.ts`**

Replace the entire contents of `~/d/mindful/v6/src/kinds.ts` with:

```ts
import type { KindSpec } from "@nodes/kernel";
import { VISUAL_IDENTITY, requireValidVisualIdentity } from "./identity.js";

export const THOUGHT = "thought";
export const MINDMAP = "mindmap";
export const JOURNAL = "journal";

// thought (≈ note) now requires its intrinsic visual identity facet (SP2).
export const thoughtSpec: KindSpec = {
	name: THOUGHT,
	requiredFacets: new Set([VISUAL_IDENTITY]),
	invariants: [requireValidVisualIdentity],
};
// mindmap/journal: first-class kinds adopting the kernel's graph/list shapes.
export const mindmapSpec: KindSpec = { name: MINDMAP, shape: "graph" };
export const journalSpec: KindSpec = { name: JOURNAL, shape: "list" };
```

- [ ] **Step 4: Attach the identity in `capture` and add `palette` in `src/api.ts`**

In `~/d/mindful/v6/src/api.ts`, add to the imports from local modules (after the existing `./kinds.js` / `./profile.js` imports):

```ts
import { VISUAL_IDENTITY, deriveIdentity, visualIdentityOf } from "./identity.js";
import { type Colorscheme, defaultColorscheme, resolve } from "./color.js";
```

Replace the `capture` method body so it attaches the uid-derived identity before the single write:

```ts
	capture(input: { title: string; body?: string; tags?: string[] }): Node {
		const node = makeNode({ id: `${THOUGHT}:${newUid()}`, kind: THOUGHT, title: input.title, body: input.body ?? "" });
		// Intrinsic visual identity, derived from the immutable uid (NOT the id slug). Attached before
		// any tag resolution so the single write below persists a complete, valid thought.
		node.facets[VISUAL_IDENTITY] = deriveIdentity(node.uid);
		const idx = this.aliasIndex();
		for (const name of input.tags ?? []) node.relations.push(this.resolveTag(node.id, name, idx));
		this.corpus.add(node); // one write; nothing persists if a tag above threw
		return this.corpus.get(node.id);
	}
```

Add a `palette` method to the `Mindful` class (place it among the query methods, e.g. directly after `allThoughts`):

```ts
	/** Resolve a thought's stored visual identity to 4 concrete #rrggbb colors against a colorscheme
	 * (defaults to the built-in scheme). The right convenience boundary: callers never hand-load the facet. */
	palette(thoughtId: string, scheme: Colorscheme = defaultColorscheme): string[] {
		return resolve(visualIdentityOf(this.corpus.get(thoughtId)), scheme);
	}
```

- [ ] **Step 5: Run the integration test to verify it passes**

Run: `cd ~/d/mindful/v6 && rtk npx vitest run tests/identity-integration.test.ts`
Expected: PASS (all cases).

- [ ] **Step 6: Run the full gate (all suites must stay green)**

Run: `cd ~/d/mindful/v6 && rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green. The existing `mindful-thoughts`/`mindful-mindmaps`/`mindful-journals` suites still pass because `capture` now attaches the required facet. If biome reports formatting, run `rtk npx biome check --write .` and re-run.

- [ ] **Step 7: Commit**

```bash
cd ~/d/mindful/v6 && rtk git add src/kinds.ts src/api.ts tests/identity-integration.test.ts
rtk git commit -m "feat: require visualIdentity on thought, attach in capture, add Mindful.palette"
```

---

## Final Verification

After all three tasks, from `~/d/mindful/v6`:

- [ ] `rtk npm test` — all suites pass (the 31 SP1 tests + identity + color + integration).
- [ ] `rtk npm run typecheck` — clean.
- [ ] `rtk npm run check` — biome clean.
- [ ] **SP2 invariants hold:**
  - Identity is derived from the immutable `uid` and is byte-stable across `edit` (title/body) and across an on-disk reload.
  - The stored facet is the source of truth: validation is structural only (`FacetError` on missing/malformed), never recompute-and-compare.
  - Identity is color-free; `resolve` is scheme-size independent (`index % length`) and re-themes under any scheme; it fails fast on an empty scheme or a malformed selected color.
  - `thought` now requires exactly the `visualIdentity` facet; a thought built without it fails validation.
  - No kernel changes were made (`~/d/nodes/ts` untouched); dependency stays one-way.
