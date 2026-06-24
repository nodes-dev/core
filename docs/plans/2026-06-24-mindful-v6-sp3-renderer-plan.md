# Mindful v6 SP3 — Renderer (Sprite generator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a thought's stored `VisualIdentity` into a deterministic, vertically-symmetric 8×8 8-bit "chiptune" sprite as a pure, headless function, plus a `Mindful.sprite()` convenience that does the resolve-then-render glue.

**Architecture:** A new `src/sprite.ts` module holds the cell/raster types, a pure `spriteCells(identity)` generator (parses the stored 32-byte `seed` into an 8×8 grid; left 4 columns generated one-byte-per-cell, mirrored right), and a pure `renderSprite(identity, colors)` painter (validates a resolved 4-color palette, paints `pixels[r][c] = colors[cells[r][c]]` lowercased). `sprite.ts` depends only on the identity module — never on `color.ts` or `Corpus`. `Mindful.sprite()` in `api.ts` is the only place `resolve` and `renderSprite` compose.

**Tech Stack:** TypeScript (Node ≥20, ESM, `.js` import extensions, zod, biome, vitest). No new runtime dependencies — pure integer/string math over the existing `VisualIdentity`. All git/npm/npx/node tooling runs through the `rtk` wrapper.

## Global Constraints

- **No kernel changes.** All work is in `~/d/mindful/v6`. Dependency stays one-way (`mindful → @nodes/kernel`).
- **Pure and headless.** The renderer is a pure function of its arguments: no I/O, no state, no `Corpus` access, no terminal/file output. Encoders are SP4.
- **Never mutate identity; never persist.** The renderer reads only — no facet writes, no `corpus.add`, no persisted palette/sprite.
- **Stored facet is the source of truth.** The pattern derives from the **stored** `identity.seed`; never call `deriveIdentity(uid)` in the renderer.
- **Color-independence of the pattern.** `spriteCells` is a function of the seed alone; the palette never affects which cells are filled.
- **Fail early at the public boundary.** `renderSprite` validates `colors` (exactly 4, each `#rrggbb`); `spriteCells` validates the `VisualIdentity` shape on direct calls. Both throw `ValidationError` before producing output. No silent fallbacks, no short grids.
- **Canonical lowercase output.** `Sprite.pixels` entries are lowercase `#rrggbb`, matching SP2 `resolve()`.
- **Grid is 8×8 by contract.** Fixed, not parameterized (configurable size is SP4+).
- **Byte mapping is frozen.** One seed byte per generated cell (`byteIndex = row*4 + col`); `filled = (b & 0x80) !== 0`; `ink = (((b >> 1) % 3) + 1)`. Do not "improve" density/masking in SP3.
- **`rtk` gate, all green before each commit:** `rtk npm test && rtk npm run typecheck && rtk npm run check`. biome uses tabs, line width 120, and sorts imports on `--fix` (expected reformatting).

---

## Reference: existing surfaces this plan builds on

From `src/identity.ts` (do not modify):
```ts
export const VisualIdentitySchema = z.object({
  seed: z.string().regex(/^[0-9a-f]{64}$/, "seed must be a 64-char SHA-256 hex string"),
  slots: z.array(ColorSlotSchema).length(4, "exactly 4 slots required"),
}).strict();
export type VisualIdentity = z.infer<typeof VisualIdentitySchema>;  // { seed: string; slots: ColorSlot[] }
export function visualIdentityOf(node: Node): VisualIdentity;        // throws FacetError on missing/malformed
```
From `src/color.ts` (do not modify): `resolve(identity, scheme?) → string[]` (4 lowercase `#rrggbb`), `defaultColorscheme`, `type Colorscheme`.
From `@nodes/kernel`: `ValidationError`, `RefError` are exported. `corpus.get(id)` throws `RefError` for a missing node.

`VisualIdentitySchema` is `.strict()` and requires `slots` (4 entries) even though `spriteCells` ignores them — all test fixtures that call `spriteCells`/`renderSprite` directly must include 4 valid slots.

---

### Task 1: `sprite.ts` — types + pure `spriteCells` generator

**Files:**
- Create: `~/d/mindful/v6/src/sprite.ts`
- Test: `~/d/mindful/v6/tests/sprite.test.ts`

**Interfaces:**
- Consumes: `VisualIdentity`, `VisualIdentitySchema` from `./identity.js`; `ValidationError` from `@nodes/kernel`.
- Produces:
  - `type CellValue = 0 | 1 | 2 | 3`
  - `type SpriteCells = CellValue[][]`
  - `interface Sprite { width: number; height: number; pixels: string[][] }`
  - `function spriteCells(identity: VisualIdentity): SpriteCells` — pure 8×8 grid from the stored seed; throws `ValidationError` on a malformed identity.

**Byte-mapping fixture (used by the test below — values are pre-computed, do not change them):**
Seed `"c0808800" + "0".repeat(56)` (64 hex chars). Bytes 0–3 are `0xc0, 0x80, 0x88, 0x00`; bytes 4–31 are `0x00`.
- byte `0xc0`: filled (`0xc0 & 0x80` ≠ 0); ink `(((0xc0>>1)%3)+1) = ((96%3)+1) = 1` → cell `1`
- byte `0x80`: filled; ink `(((0x80>>1)%3)+1) = ((64%3)+1) = 2` → cell `2`
- byte `0x88`: filled; ink `(((0x88>>1)%3)+1) = ((68%3)+1) = 3` → cell `3`
- byte `0x00`: not filled → cell `0`
So row 0 generated cells `[1,2,3,0]`, mirrored → `[1,2,3,0,0,3,2,1]`. Rows 1–7 are all `0` (`[0,0,0,0,0,0,0,0]`).

- [ ] **Step 1: Write the failing tests**

Create `~/d/mindful/v6/tests/sprite.test.ts`:
```ts
import { ValidationError } from "@nodes/kernel";
import { describe, expect, it } from "vitest";
import type { VisualIdentity } from "../src/identity.js";
import { type CellValue, type SpriteCells, spriteCells } from "../src/sprite.js";

// Valid identity with a controllable seed. slots are required by the schema but unused by spriteCells.
function idWithSeed(seed: string): VisualIdentity {
	return {
		seed,
		slots: [
			{ index: 0, variant: 0 },
			{ index: 0, variant: 0 },
			{ index: 0, variant: 0 },
			{ index: 0, variant: 0 },
		],
	};
}

const ZERO_SEED = "0".repeat(64); // all bytes 0x00 → every cell background (0)
const MAP_SEED = `c0808800${"0".repeat(56)}`; // see plan: row 0 = [1,2,3,0,0,3,2,1], rows 1-7 all 0

describe("spriteCells", () => {
	it("is 8×8 with every value in {0,1,2,3}", () => {
		const cells = spriteCells(idWithSeed(MAP_SEED));
		expect(cells).toHaveLength(8);
		for (const row of cells) {
			expect(row).toHaveLength(8);
			for (const v of row) expect([0, 1, 2, 3]).toContain(v);
		}
	});

	it("is deterministic: same seed → equal grids; different seed → different grids", () => {
		expect(spriteCells(idWithSeed(MAP_SEED))).toEqual(spriteCells(idWithSeed(MAP_SEED)));
		expect(spriteCells(idWithSeed(ZERO_SEED))).not.toEqual(spriteCells(idWithSeed(MAP_SEED)));
	});

	it("is vertically mirrored: cells[r][c] === cells[r][7-c]", () => {
		const cells = spriteCells(idWithSeed(MAP_SEED));
		for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) expect(cells[r][c]).toBe(cells[r][7 - c]);
	});

	it("maps seed bytes per the frozen rule (fill = b&0x80, ink = ((b>>1)%3)+1)", () => {
		const cells = spriteCells(idWithSeed(MAP_SEED));
		const expected: SpriteCells = [
			[1, 2, 3, 0, 0, 3, 2, 1],
			[0, 0, 0, 0, 0, 0, 0, 0],
			[0, 0, 0, 0, 0, 0, 0, 0],
			[0, 0, 0, 0, 0, 0, 0, 0],
			[0, 0, 0, 0, 0, 0, 0, 0],
			[0, 0, 0, 0, 0, 0, 0, 0],
			[0, 0, 0, 0, 0, 0, 0, 0],
			[0, 0, 0, 0, 0, 0, 0, 0],
		];
		expect(cells).toEqual(expected);
	});

	it("all-zero seed → all-background grid", () => {
		const cells = spriteCells(idWithSeed(ZERO_SEED));
		for (const row of cells) for (const v of row) expect(v).toBe(0);
	});

	it("throws ValidationError on a malformed identity (short/non-hex seed)", () => {
		expect(() => spriteCells(idWithSeed("abc"))).toThrow(ValidationError);
		expect(() => spriteCells(idWithSeed("g".repeat(64)))).toThrow(ValidationError);
	});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npm test -- sprite.test.ts`
Expected: FAIL — `../src/sprite.js` does not exist / `spriteCells` is not exported.

- [ ] **Step 3: Implement `sprite.ts` (types + `spriteCells`)**

Create `~/d/mindful/v6/src/sprite.ts`:
```ts
import { ValidationError } from "@nodes/kernel";
import { type VisualIdentity, VisualIdentitySchema } from "./identity.js";

/** A cell's palette role: 0 = background, 1|2|3 = ink slot. */
export type CellValue = 0 | 1 | 2 | 3;

/** The uncolored sprite grid: 8 rows × 8 columns by contract. */
export type SpriteCells = CellValue[][];

/** An abstract raster — pure data. SP4 encoders turn it into ANSI/SVG/PNG. */
export interface Sprite {
	width: number;
	height: number;
	pixels: string[][]; // [row][col] → lowercase "#rrggbb"
}

const SIZE = 8;
const HALF = SIZE / 2; // 4 generated columns, mirrored into the right 4

/** Pure, color-free 8×8 cell grid derived from the STORED identity.seed.
 * Left 4 columns generated (one seed byte per cell, byteIndex = row*4 + col), mirrored into the
 * right 4. The palette never enters this function — switching colorscheme cannot change the grid. */
export function spriteCells(identity: VisualIdentity): SpriteCells {
	const parsed = VisualIdentitySchema.safeParse(identity);
	if (!parsed.success) {
		throw new ValidationError(`invalid visual identity: ${parsed.error.issues.map((i) => i.message).join("; ")}`);
	}
	const { seed } = parsed.data; // 64-char hex → 32 bytes
	const cells: SpriteCells = [];
	for (let row = 0; row < SIZE; row++) {
		const r = new Array<CellValue>(SIZE);
		for (let col = 0; col < HALF; col++) {
			const byteIndex = row * HALF + col;
			const b = Number.parseInt(seed.slice(byteIndex * 2, byteIndex * 2 + 2), 16);
			const value: CellValue = (b & 0x80) !== 0 ? (((b >> 1) % 3) + 1) as CellValue : 0;
			r[col] = value;
			r[SIZE - 1 - col] = value; // vertical mirror
		}
		cells.push(r);
	}
	return cells;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk npm test -- sprite.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full gate**

Run: `rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green (biome may reformat `sprite.ts`/imports — accept it).

- [ ] **Step 6: Commit**

```bash
rtk git add src/sprite.ts tests/sprite.test.ts
rtk git commit -m "feat(sprite): SpriteCells/Sprite types + pure spriteCells generator"
```

---

### Task 2: `renderSprite` — paint cells through a resolved palette

**Files:**
- Modify: `~/d/mindful/v6/src/sprite.ts` (append `renderSprite`)
- Test: `~/d/mindful/v6/tests/sprite.test.ts` (append a `renderSprite` describe block)

**Interfaces:**
- Consumes: `spriteCells`, `Sprite`, `VisualIdentity` (from Task 1 / `./identity.js`); `ValidationError` from `@nodes/kernel`.
- Produces: `function renderSprite(identity: VisualIdentity, colors: string[]): Sprite` — validates `colors` (exactly 4, each `#rrggbb`), paints `pixels[r][c] = colors[cells[r][c]]` lowercased, returns `{ width: 8, height: 8, pixels }`. Throws `ValidationError` on a bad `colors` argument and (via `spriteCells`) on a malformed identity.

- [ ] **Step 1: Write the failing tests**

First, **merge `renderSprite` into the existing `../src/sprite.js` import** at the top of the file (do not add a second import statement from the same module — biome's import organizer flags duplicates). The line becomes:
```ts
import { type CellValue, type SpriteCells, renderSprite, spriteCells } from "../src/sprite.js";
```

Then append the new describe block to `~/d/mindful/v6/tests/sprite.test.ts`:
```ts
// (idWithSeed, ZERO_SEED, MAP_SEED are defined above in this file)
const FOUR = ["#102030", "#a1b2c3", "#ffffff", "#000000"]; // bg, ink1, ink2, ink3

describe("renderSprite", () => {
	it("returns an 8×8 sprite of #rrggbb pixels", () => {
		const s = renderSprite(idWithSeed(MAP_SEED), FOUR);
		expect(s.width).toBe(8);
		expect(s.height).toBe(8);
		expect(s.pixels).toHaveLength(8);
		for (const row of s.pixels) {
			expect(row).toHaveLength(8);
			for (const c of row) expect(c).toMatch(/^#[0-9a-f]{6}$/);
		}
	});

	it("paints pixels[r][c] = colors[cells[r][c]]", () => {
		const id = idWithSeed(MAP_SEED);
		const cells = spriteCells(id);
		const s = renderSprite(id, FOUR);
		for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) expect(s.pixels[r][c]).toBe(FOUR[cells[r][c]]);
	});

	it("all-zero seed → every pixel is the background color (colors[0])", () => {
		const s = renderSprite(idWithSeed(ZERO_SEED), FOUR);
		for (const row of s.pixels) for (const px of row) expect(px).toBe("#102030");
	});

	it("normalizes upper-case colors to lowercase", () => {
		const s = renderSprite(idWithSeed(ZERO_SEED), ["#ABCDEF", "#111111", "#222222", "#333333"]);
		expect(s.pixels[0][0]).toBe("#abcdef");
	});

	it("is palette-independent in its cell grid: same identity, two palettes → same cells, different pixels", () => {
		const id = idWithSeed(MAP_SEED);
		const a = renderSprite(id, FOUR);
		const b = renderSprite(id, ["#000000", "#111111", "#222222", "#333333"]);
		// cells identical (proxy: structure same), pixels differ
		expect(a.pixels).not.toEqual(b.pixels);
		expect(spriteCells(id)).toEqual(spriteCells(id));
	});

	it("throws ValidationError when colors is not exactly length 4", () => {
		expect(() => renderSprite(idWithSeed(ZERO_SEED), ["#000000", "#111111", "#222222"])).toThrow(ValidationError);
		expect(() =>
			renderSprite(idWithSeed(ZERO_SEED), ["#000000", "#111111", "#222222", "#333333", "#444444"]),
		).toThrow(ValidationError);
	});

	it("throws ValidationError on a malformed color entry", () => {
		expect(() => renderSprite(idWithSeed(ZERO_SEED), ["#000000", "#111111", "#222222", "red"])).toThrow(
			ValidationError,
		);
		expect(() => renderSprite(idWithSeed(ZERO_SEED), ["#000000", "#111111", "#222222", "#xyz"])).toThrow(
			ValidationError,
		);
	});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npm test -- sprite.test.ts`
Expected: FAIL — `renderSprite` is not exported.

- [ ] **Step 3: Implement `renderSprite`**

Append to `~/d/mindful/v6/src/sprite.ts`:
```ts
const HEX_RE = /^#[0-9a-fA-F]{6}$/;

/** Paint a cell grid through a resolved 4-color palette into a Sprite. Validates colors (exactly 4
 * valid #rrggbb) and lowercases the output. Pure — no Colorscheme and no Corpus dependency. */
export function renderSprite(identity: VisualIdentity, colors: string[]): Sprite {
	if (colors.length !== 4) {
		throw new ValidationError(`renderSprite expects exactly 4 colors, got ${colors.length}`);
	}
	for (const c of colors) {
		if (!HEX_RE.test(c)) throw new ValidationError(`renderSprite: invalid color ${JSON.stringify(c)}`);
	}
	const palette = colors.map((c) => c.toLowerCase());
	const cells = spriteCells(identity); // also validates identity shape
	const pixels = cells.map((row) => row.map((s) => palette[s]));
	return { width: SIZE, height: SIZE, pixels };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk npm test -- sprite.test.ts`
Expected: PASS (13 tests total in the file).

- [ ] **Step 5: Run the full gate**

Run: `rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
rtk git add src/sprite.ts tests/sprite.test.ts
rtk git commit -m "feat(sprite): renderSprite — validated, lowercase-normalized painter"
```

---

### Task 3: `Mindful.sprite()` + barrel exports + integration tests

**Files:**
- Modify: `~/d/mindful/v6/src/api.ts` (add import + `sprite()` method)
- Modify: `~/d/mindful/v6/src/index.ts` (export the renderer surface)
- Test: `~/d/mindful/v6/tests/sprite-integration.test.ts`

**Interfaces:**
- Consumes: `renderSprite`, `Sprite` from `./sprite.js`; existing `resolve`, `defaultColorscheme`, `Colorscheme` (`./color.js`), `visualIdentityOf` (`./identity.js`), and `this.corpus` in `api.ts`.
- Produces: `Mindful.sprite(thoughtId: string, scheme?: Colorscheme): Sprite` — loads the thought (`RefError` if absent), loads its identity once (`FacetError` if missing/malformed), returns `renderSprite(identity, resolve(identity, scheme))`.

- [ ] **Step 1: Write the failing integration tests**

Create `~/d/mindful/v6/tests/sprite-integration.test.ts`:
```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { RefError } from "@nodes/kernel";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Mindful } from "../src/api.js";
import type { Colorscheme } from "../src/color.js";
import { visualIdentityOf } from "../src/identity.js";
import { renderSprite, spriteCells } from "../src/sprite.js";

let root: string;
beforeEach(() => {
	root = mkdtempSync(join(tmpdir(), "mindful-sprite-"));
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("Mindful.sprite", () => {
	it("returns an 8×8 sprite for a captured thought using the default scheme", () => {
		const m = new Mindful(root);
		const t = m.capture({ title: "Render me" });
		const s = m.sprite(t.id);
		expect(s.width).toBe(8);
		expect(s.height).toBe(8);
		expect(s.pixels).toHaveLength(8);
		for (const row of s.pixels) expect(row).toHaveLength(8);
		// matches the pure path
		expect(s.pixels).toEqual(renderSprite(visualIdentityOf(t), m.palette(t.id)).pixels);
	});

	it("round-trips byte-identically through a fresh Mindful instance (stored-seed determinism)", () => {
		const m1 = new Mindful(root);
		const t = m1.capture({ title: "Persisted sprite" });
		const expected = m1.sprite(t.id);
		const m2 = new Mindful(root); // reads from disk
		expect(m2.sprite(t.id)).toEqual(expected);
	});

	it("re-themes: same thought, two schemes → identical cells, different pixels", () => {
		const m = new Mindful(root);
		const t = m.capture({ title: "Re-theme me" });
		const mono: Colorscheme = { name: "mono", colors: ["#000000", "#555555", "#aaaaaa", "#ffffff"] };
		const a = m.sprite(t.id); // default scheme
		const b = m.sprite(t.id, mono);
		expect(spriteCells(visualIdentityOf(t))).toEqual(spriteCells(visualIdentityOf(t))); // cells stable
		expect(b.pixels).not.toEqual(a.pixels); // colors differ
	});

	it("throws RefError for an unknown thought id", () => {
		const m = new Mindful(root);
		expect(() => m.sprite("thought:does-not-exist")).toThrow(RefError);
	});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npm test -- sprite-integration.test.ts`
Expected: FAIL — `m.sprite` is not a function.

- [ ] **Step 3: Add the `sprite()` method to `api.ts`**

In `~/d/mindful/v6/src/api.ts`, add to the existing import from `./sprite.js` (create the import line near the other local imports):
```ts
import { type Sprite, renderSprite } from "./sprite.js";
```
Then add the method to the `Mindful` class, immediately after the existing `palette(...)` method:
```ts
	/** Render a thought's stored visual identity to an 8×8 sprite, themed by a colorscheme (defaults to
	 * the built-in scheme). Pure resolve-then-render glue; never mutates or persists. */
	sprite(thoughtId: string, scheme: Colorscheme = defaultColorscheme): Sprite {
		const node = this.corpus.get(thoughtId); // RefError if no such thought
		const identity = visualIdentityOf(node); // FacetError if missing/malformed; loaded once
		return renderSprite(identity, resolve(identity, scheme));
	}
```

- [ ] **Step 4: Export the renderer surface from the barrel**

In `~/d/mindful/v6/src/index.ts`, append:
```ts
export { type CellValue, type Sprite, type SpriteCells, renderSprite, spriteCells } from "./sprite.js";
```

- [ ] **Step 5: Run the integration tests to verify they pass**

Run: `rtk npm test -- sprite-integration.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the full gate**

Run: `rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green. Full suite grows by the new sprite test files.

- [ ] **Step 7: Commit**

```bash
rtk git add src/api.ts src/index.ts tests/sprite-integration.test.ts
rtk git commit -m "feat(api): Mindful.sprite() + barrel exports for the renderer"
```

---

## Self-Review (completed by plan author)

**1. Spec coverage:**
- §2 data model (`CellValue`, `SpriteCells`, `Sprite`) → Task 1.
- §3 algorithm (8×8, vertical mirror, byte mapping, stored seed) → Task 1 + byte-mapping/symmetry/zero-seed tests.
- §4 painting (`renderSprite`, 4×`#rrggbb` validation, lowercase) → Task 2.
- §5 API (`Mindful.sprite()` loads identity once; barrel exports) → Task 3.
- §6 file structure (`sprite.ts` imports only identity, not color; glue in api) → Tasks 1–3.
- §7 error handling (`ValidationError` on direct calls; `RefError`/`FacetError` on the Node path) → Task 1 (identity validation), Task 2 (color validation), Task 3 (`RefError` test).
- §8 testing strategy → all three test blocks; palette-independence covered in Tasks 2 & 3.
- §9 out of scope (animation, encoders, shell, scheme UI) → not built. ✓

**2. Placeholder scan:** none — every code/test step contains complete code; byte-mapping expected values are pre-computed.

**3. Type consistency:** `CellValue`/`SpriteCells`/`Sprite`/`spriteCells`/`renderSprite` used identically across tasks; `Mindful.sprite(thoughtId, scheme?)` matches the spec signature; `resolve`/`visualIdentityOf`/`defaultColorscheme`/`Colorscheme` names match `color.ts`/`identity.ts`.
