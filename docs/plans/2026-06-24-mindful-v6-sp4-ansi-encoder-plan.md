# Mindful v6 SP4 — ANSI Encoder (`spriteToAnsi`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SP3's abstract `Sprite` raster visible in a terminal via one pure function `spriteToAnsi(sprite) → string` that encodes a sprite as 24-bit truecolor, half-block ANSI text.

**Architecture:** A new pure module `src/encode.ts` exports `spriteToAnsi(sprite: Sprite): string` — a presentation leaf that consumes only SP3's `Sprite` type, validates it strictly, and returns ready-to-`console.log` ANSI. No `Mindful` method (encoding is presentation, not data); the future shell composes `spriteToAnsi(m.sprite(id))` itself. No I/O, no state, no new runtime dependency.

**Tech Stack:** TypeScript (Node ≥20, ESM, `.js` import extensions, biome, vitest). All git/npm/npx/node tooling runs through the `rtk` wrapper.

## Global Constraints

- **No kernel changes.** All work is in `~/d/mindful/v6`. Dependency stays one-way (`mindful → @nodes/kernel`).
- **Pure presentation leaf.** `spriteToAnsi` is a pure function of its `Sprite` argument: no I/O (returns a string; printing is the caller's job), no state, no `Corpus`, no new dependency.
- **No `Mindful` method.** `Mindful`/`api.ts` is untouched. `encode.ts` imports `ValidationError` from `@nodes/kernel` and the `Sprite` type from `./sprite.js`, and no other mindful module.
- **Consumes only `Sprite`.** The encoder has no knowledge of `VisualIdentity`, slots, palettes, or schemes.
- **Strict, fail-early.** Validates the dimension contract + pixel format and throws `ValidationError` before producing any output. No silent fallbacks, no partial output.
- **Truecolor only.** 24-bit `\x1b[38;2;r;g;bm` (fg) / `\x1b[48;2;r;g;bm` (bg). No 256/16-color downgrade.
- **Size contract.** Positive-width, even-height, rectangular `#rrggbb` sprites; SP3's 8×8 is the primary caller. Odd height is rejected.
- **Frozen escape construction.** `RESET = "\x1b[0m"`, `UPPER_HALF_BLOCK = "▀"`; per cell `fg(top) + bg(bottom) + "▀"`; per text row the `width` cells concatenated then `RESET`; text rows joined with `\n`, **no trailing newline**.
- **`rtk` gate, all green before commit:** `rtk npm test && rtk npm run typecheck && rtk npm run check`. biome uses tabs, line width 120, and organizes imports; if `check` reports formatting/import-order diffs, apply them with `rtk npx @biomejs/biome check --write src/encode.ts src/index.ts tests/encode.test.ts` and re-run the gate.

---

## Reference: existing surfaces this plan builds on

From `src/sprite.ts` (SP3, do not modify):
```ts
export interface Sprite { width: number; height: number; pixels: string[][] } // pixels[row][col] = lowercase "#rrggbb"
export function renderSprite(identity: VisualIdentity, colors: string[]): Sprite; // 8×8 sprite
```
From `src/identity.ts` (do not modify): `type VisualIdentity = { seed: string; slots: ColorSlot[] }`.
From `@nodes/kernel`: `ValidationError` is exported (the project's fail-early error, already used in `api.ts`/`sprite.ts`).

The 8×8 test fixture reuses SP3's frozen byte-mapping seed `MAP_SEED = "c0808800" + "0".repeat(56)`, which has filled (non-background) cells, so the encoded sprite exercises multiple distinct colors.

---

### Task 1: `encode.ts` — strict `spriteToAnsi` + barrel export

**Files:**
- Create: `~/d/mindful/v6/src/encode.ts`
- Modify: `~/d/mindful/v6/src/index.ts` (append the barrel export)
- Test: `~/d/mindful/v6/tests/encode.test.ts`

**Interfaces:**
- Consumes: `Sprite`, `renderSprite` from `./sprite.js`; `VisualIdentity` from `./identity.js`; `ValidationError` from `@nodes/kernel`.
- Produces: `function spriteToAnsi(sprite: Sprite): string` — validates a positive-width, even-height, rectangular, `#rrggbb` sprite (throws `ValidationError` otherwise) and returns half-block truecolor ANSI (4 text rows for an 8×8 sprite; no trailing newline).

- [ ] **Step 1: Write the failing tests**

Create `~/d/mindful/v6/tests/encode.test.ts`:
```ts
import { ValidationError } from "@nodes/kernel";
import { describe, expect, it } from "vitest";
import { spriteToAnsi } from "../src/encode.js";
import type { VisualIdentity } from "../src/identity.js";
import { type Sprite, renderSprite } from "../src/sprite.js";

const RESET = "\x1b[0m";

// Test-local expected-sequence builders (do not import encode.ts internals — they are module-private).
function channels(hex: string): [number, number, number] {
	return [
		Number.parseInt(hex.slice(1, 3), 16),
		Number.parseInt(hex.slice(3, 5), 16),
		Number.parseInt(hex.slice(5, 7), 16),
	];
}
function fg(hex: string): string {
	const [r, g, b] = channels(hex);
	return `\x1b[38;2;${r};${g};${b}m`;
}
function bg(hex: string): string {
	const [r, g, b] = channels(hex);
	return `\x1b[48;2;${r};${g};${b}m`;
}

const twoByTwo: Sprite = {
	width: 2,
	height: 2,
	pixels: [
		["#ff0000", "#00ff00"],
		["#0000ff", "#ffffff"],
	],
};

function idWithSeed(seed: string): VisualIdentity {
	return {
		seed,
		slots: [
			{ index: 0, variant: 0 },
			{ index: 1, variant: 0 },
			{ index: 2, variant: 0 },
			{ index: 3, variant: 0 },
		],
	};
}
const MAP_SEED = `c0808800${"0".repeat(56)}`; // SP3 fixture: has filled cells → multiple colors
const FOUR = ["#102030", "#a1b2c3", "#ffffff", "#000000"];

describe("spriteToAnsi", () => {
	it("encodes a 2×2 sprite to one exact half-block text row", () => {
		const expected = `${fg("#ff0000")}${bg("#0000ff")}▀${fg("#00ff00")}${bg("#ffffff")}▀${RESET}`;
		expect(spriteToAnsi(twoByTwo)).toBe(expected);
	});

	it("produces no trailing newline (single row → no \\n at all)", () => {
		expect(spriteToAnsi(twoByTwo).includes("\n")).toBe(false);
	});

	it("encodes an 8×8 sprite to 4 text rows of 8 glyphs each, each ending with RESET", () => {
		const out = spriteToAnsi(renderSprite(idWithSeed(MAP_SEED), FOUR));
		const rows = out.split("\n");
		expect(rows).toHaveLength(4);
		for (const row of rows) {
			expect((row.match(/▀/g) ?? []).length).toBe(8);
			expect(row.endsWith(RESET)).toBe(true);
		}
		expect(out.endsWith("\n")).toBe(false);
	});

	it("emits fg = top pixel and bg = bottom pixel for the first cell of the first text row", () => {
		const sprite = renderSprite(idWithSeed(MAP_SEED), FOUR);
		const out = spriteToAnsi(sprite);
		const firstCell = `${fg(sprite.pixels[0][0])}${bg(sprite.pixels[1][0])}▀`;
		expect(out.split("\n")[0].startsWith(firstCell)).toBe(true);
	});

	it("uniform sprite: each cell's fg sequence equals its bg sequence", () => {
		const uniform: Sprite = {
			width: 2,
			height: 2,
			pixels: [
				["#123456", "#123456"],
				["#123456", "#123456"],
			],
		};
		expect(spriteToAnsi(uniform)).toBe(
			`${fg("#123456")}${bg("#123456")}▀${fg("#123456")}${bg("#123456")}▀${RESET}`,
		);
	});

	it("throws ValidationError when height ≠ pixels.length", () => {
		const bad: Sprite = {
			width: 2,
			height: 4,
			pixels: [
				["#000000", "#000000"],
				["#000000", "#000000"],
			],
		};
		expect(() => spriteToAnsi(bad)).toThrow(ValidationError);
	});

	it("throws ValidationError on a ragged row", () => {
		const bad: Sprite = { width: 2, height: 2, pixels: [["#000000", "#000000"], ["#000000"]] };
		expect(() => spriteToAnsi(bad)).toThrow(ValidationError);
	});

	it("throws ValidationError on a non-#rrggbb pixel", () => {
		const bad1: Sprite = {
			width: 2,
			height: 2,
			pixels: [
				["#000000", "red"],
				["#000000", "#000000"],
			],
		};
		const bad2: Sprite = {
			width: 2,
			height: 2,
			pixels: [
				["#000000", "#xyz000"],
				["#000000", "#000000"],
			],
		};
		expect(() => spriteToAnsi(bad1)).toThrow(ValidationError);
		expect(() => spriteToAnsi(bad2)).toThrow(ValidationError);
	});

	it("throws ValidationError on an odd height", () => {
		const bad: Sprite = {
			width: 2,
			height: 3,
			pixels: [
				["#000000", "#000000"],
				["#000000", "#000000"],
				["#000000", "#000000"],
			],
		};
		expect(() => spriteToAnsi(bad)).toThrow(ValidationError);
	});

	it("throws ValidationError on non-positive or non-integer dimensions", () => {
		const zeroWidth: Sprite = { width: 0, height: 2, pixels: [[], []] };
		const fracHeight: Sprite = {
			width: 2,
			height: 2.5,
			pixels: [
				["#000000", "#000000"],
				["#000000", "#000000"],
			],
		};
		expect(() => spriteToAnsi(zeroWidth)).toThrow(ValidationError);
		expect(() => spriteToAnsi(fracHeight)).toThrow(ValidationError);
	});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npm test -- encode.test.ts`
Expected: FAIL — `../src/encode.js` does not exist / `spriteToAnsi` is not exported.

- [ ] **Step 3: Implement `src/encode.ts`**

Create `~/d/mindful/v6/src/encode.ts`:
```ts
import { ValidationError } from "@nodes/kernel";
import type { Sprite } from "./sprite.js";

const RESET = "\x1b[0m";
const UPPER_HALF_BLOCK = "▀";
const HEX_RE = /^#[0-9a-fA-F]{6}$/;

function channels(hex: string): [number, number, number] {
	return [
		Number.parseInt(hex.slice(1, 3), 16),
		Number.parseInt(hex.slice(3, 5), 16),
		Number.parseInt(hex.slice(5, 7), 16),
	];
}

function fg(hex: string): string {
	const [r, g, b] = channels(hex);
	return `\x1b[38;2;${r};${g};${b}m`;
}

function bg(hex: string): string {
	const [r, g, b] = channels(hex);
	return `\x1b[48;2;${r};${g};${b}m`;
}

/** Encode a Sprite as 24-bit truecolor, half-block ANSI text (ready to console.log). Strict: validates
 * a positive-width, even-height, rectangular #rrggbb sprite and throws ValidationError on violation.
 * Each "▀" shows fg = top pixel and bg = bottom pixel, so one text row encodes two sprite rows. Pure;
 * no I/O — printing is the caller's job. */
export function spriteToAnsi(sprite: Sprite): string {
	const { width, height, pixels } = sprite;
	if (!Number.isInteger(width) || width <= 0) {
		throw new ValidationError(`sprite width must be a positive integer, got ${width}`);
	}
	if (!Number.isInteger(height) || height <= 0) {
		throw new ValidationError(`sprite height must be a positive integer, got ${height}`);
	}
	if (height % 2 !== 0) {
		throw new ValidationError(`sprite height must be even for half-block encoding, got ${height}`);
	}
	if (pixels.length !== height) {
		throw new ValidationError(`sprite has ${pixels.length} rows, expected height ${height}`);
	}
	for (const row of pixels) {
		if (row.length !== width) {
			throw new ValidationError(`sprite row has ${row.length} cells, expected width ${width}`);
		}
		for (const px of row) {
			if (!HEX_RE.test(px)) throw new ValidationError(`sprite has invalid pixel ${JSON.stringify(px)}`);
		}
	}
	const lines: string[] = [];
	for (let t = 0; t < height; t += 2) {
		const top = pixels[t];
		const bottom = pixels[t + 1]; // always defined: height is even and pixels.length === height
		let line = "";
		for (let c = 0; c < width; c++) {
			line += `${fg(top[c])}${bg(bottom[c])}${UPPER_HALF_BLOCK}`;
		}
		lines.push(line + RESET);
	}
	return lines.join("\n");
}
```

- [ ] **Step 4: Add the barrel export**

In `~/d/mindful/v6/src/index.ts`, append:
```ts
export { spriteToAnsi } from "./encode.js";
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `rtk npm test -- encode.test.ts`
Expected: PASS (10 tests).

- [ ] **Step 6: Run the full gate**

Run: `rtk npm test && rtk npm run typecheck && rtk npm run check`
Expected: all green; full suite grows by the new `encode.test.ts`. If `check` reports formatting/import-order diffs, apply them with `rtk npx @biomejs/biome check --write src/encode.ts src/index.ts tests/encode.test.ts` and re-run the gate.

- [ ] **Step 7: Commit**

```bash
rtk git add src/encode.ts src/index.ts tests/encode.test.ts
rtk git commit -m "feat(encode): spriteToAnsi — strict half-block truecolor ANSI encoder"
```

---

## Self-Review (completed by plan author)

**1. Spec coverage:**
- §2 constants (`RESET`, `UPPER_HALF_BLOCK`, `HEX_RE`) → Task 1 implementation.
- §3 algorithm (row pairing, `fg(top)+bg(bottom)+▀`, `\n`-joined, no trailing newline) → implementation + 2×2 exact / 8×8 structural / first-cell / uniform tests.
- §4 strict contract (positive-int width/height, even height, `pixels.length === height`, rectangular rows, `#rrggbb`) → implementation guard order + the five validation tests.
- §5 surface (`encode.ts` imports `ValidationError` + `type Sprite` only; barrel export; no `api.ts` change) → Task 1 files.
- §6 testing strategy → exactly the test cases listed.
- §7 out of scope (SVG/PNG, animation, shell, scheme storage, I/O, color fallbacks, odd-height/scaling) → not built. ✓

**2. Placeholder scan:** none — every code/test step is complete; the 2×2 expected string and validation cases are fully specified.

**3. Type consistency:** `spriteToAnsi(sprite: Sprite): string` matches the spec; `Sprite`/`renderSprite`/`VisualIdentity` names match `sprite.ts`/`identity.ts`; `ValidationError` matches the kernel export; the test-local `fg`/`bg`/`channels` mirror the private implementation helpers without importing them.
