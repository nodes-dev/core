# Mindful v6 — SP4: ANSI Encoder (`spriteToAnsi`)

**Status:** Design (approved in brainstorming; pending written-spec review)
**Date:** 2026-06-24
**Repo:** `~/d/mindful/v6` (TypeScript only — **no kernel changes**)
**Builds on:** SP1 (`2026-06-23-mindful-v6-sp1-abstraction-design.md`), SP2
(`2026-06-24-mindful-v6-sp2-visual-identity-design.md`), SP3
(`2026-06-24-mindful-v6-sp3-renderer-design.md`)

**Goal:** Make SP3's abstract `Sprite` raster **visible** in a terminal: a single pure function
`spriteToAnsi(sprite) → string` that encodes an 8×8 sprite as 24-bit truecolor, half-block ANSI text
ready to `console.log`. This is the first slice of the original SP4 ("the renderer + CLI/TUI shell");
the interactive shell, colorscheme-picking UI, active-scheme storage, SVG/PNG encoders, and animation
are each their own later sub-project.

**Architecture:** A new pure module `src/encode.ts` exports `spriteToAnsi(sprite: Sprite): string`. It
is a **presentation leaf**: it consumes only SP3's `Sprite` type, performs no I/O, holds no state,
touches no `Corpus`, and adds no runtime dependency. There is **no** `Mindful` method — ANSI is a
presentation concern, so `Mindful` stays a data/raster API and the (future) shell composes
`spriteToAnsi(m.sprite(id))` itself. The encoder is **strict**: it validates the `Sprite`'s dimension
contract and pixel format and fails early (`ValidationError`) rather than emitting partial or
malformed output.

**Tech stack:** TypeScript (Node ≥20, ESM, `.js` import extensions, biome, vitest). No new runtime
dependencies — pure string/integer math over the existing `Sprite`.

---

## Global Constraints

- **No kernel changes.** All work is in `~/d/mindful/v6`. The dependency stays one-way
  (`mindful → @nodes/kernel`); the kernel never learns what ANSI is.
- **Pure presentation leaf.** `spriteToAnsi` is a pure function of its `Sprite` argument: no I/O
  (it returns a string; printing is the caller's job), no state, no `Corpus`, no new dependency.
- **No `Mindful` method.** Encoding is presentation, not data. `Mindful` is untouched. `encode.ts`
  imports `ValidationError` from `@nodes/kernel` and the `Sprite` type from `./sprite.js`, and no
  other mindful module (nothing from `api.ts`).
- **Consumes only `Sprite`.** The encoder has no knowledge of `VisualIdentity`, slots, palettes, or
  colorschemes. It cannot mutate identity or persist anything — the SP2/SP3 boundary holds by
  construction.
- **Strict, fail-early.** The encoder validates its argument (dimension contract + pixel format) and
  throws `ValidationError` before producing any output. No silent fallbacks, no partial output.
- **Truecolor only.** 24-bit `\x1b[38;2;r;g;bm` / `\x1b[48;2;r;g;bm` sequences. No 256-color or
  16-color downgrade path (YAGNI; modern terminals support truecolor).
- **Size contract.** SP4 supports **positive-width, even-height rectangular** sprites; SP3's 8×8
  output is the primary caller. Odd-height support, scaling/zoom, and richer terminal layout are
  deferred — future additive changes, not accidental Hyrum's-Law contracts.

---

## 1. Context & Motivation

SP3 delivered a pure renderer producing an abstract `Sprite` (`{ width, height, pixels: string[][] }`,
an 8×8 grid of lowercase `#rrggbb`). It deliberately stopped at the data structure — "encoders are
SP4." Nothing yet turns that raster into something a human can see.

The original SP4 bundled four independent subsystems (encoders, the interactive shell, scheme-picking
UI + active-scheme storage, animation). They are decomposed; **this sub-project is the ANSI encoder
only** — the single piece with a concrete near-term consumer (the future TUI shell) and the one that
makes every downstream visual feature demonstrable. It is pure, headless, and dependency-free, so it
fits the SP1–SP3 philosophy exactly. SVG was considered and **deferred** alongside PNG: it is also a
pure no-dep string function, but it has no planned consumer (no web/doc-embedding feature on the
roadmap), so building it now would be speculative surface.

---

## 2. Data Model

No new persisted or public types. The encoder consumes SP3's existing `Sprite`:

```ts
// from src/sprite.ts (SP3) — unchanged
interface Sprite {
  width: number;
  height: number;
  pixels: string[][];   // [row][col] → lowercase "#rrggbb"
}
```

Module-private frozen constants:

```ts
const RESET = "\x1b[0m";
const UPPER_HALF_BLOCK = "▀";
const HEX_RE = /^#[0-9a-fA-F]{6}$/;
```

---

## 3. Encoding Algorithm — `spriteToAnsi(sprite)`

24-bit truecolor, half-block packing. The upper-half-block glyph `▀` shows its **foreground** in the
top half of the character cell and its **background** in the bottom half, so each text row encodes two
sprite rows.

```ts
function spriteToAnsi(sprite: Sprite): string {
  // 1. Validate the dimension contract + pixel format (see §4); throw ValidationError on violation.
  // 2. For each text row t in 0 .. height/2 - 1:
  //      top    = pixels[2t]
  //      bottom = pixels[2t + 1]
  //      for each column c in 0 .. width - 1:
  //        cell = fg(top[c]) + bg(bottom[c]) + UPPER_HALF_BLOCK
  //      line = cells.join("") + RESET
  // 3. return lines.join("\n")            // no trailing newline
}
```

- **Row pairing:** text row `t` renders sprite rows `2t` (foreground / top) and `2t+1` (background /
  bottom). An 8-row sprite → **4 text rows**.
- **Per cell:** `fg(top[c]) + bg(bottom[c]) + UPPER_HALF_BLOCK`, where:
  - `fg("#rrggbb")` → `\x1b[38;2;{r};{g};{b}m`
  - `bg("#rrggbb")` → `\x1b[48;2;{r};{g};{b}m`
  - `r`/`g`/`b` are the decimal values of the three hex byte-pairs.
- **Per text row:** the `width` cells concatenated, then `RESET`.
- **Whole sprite:** text rows joined with `\n`, **no trailing newline**.

The escape construction is frozen so tests can assert it character-for-character.

---

## 4. Error Handling — strict dimension + pixel contract

`spriteToAnsi` validates before emitting anything; any violation throws `ValidationError`
(from `@nodes/kernel`, the project's fail-early error). The dimension contract:

- `width` and `height` must be **positive integers** (`Number.isInteger`, `> 0`) — rejects zero-width,
  zero-height, negative, and fractional dimensions.
- `height` must be **even** — the half-block pairing needs two sprite rows per text row.
- `pixels.length === height`.
- every row's length is exactly `width` (rectangular; rejects ragged rows).
- every pixel matches `HEX_RE` (`/^#[0-9a-fA-F]{6}$/`).

No silent fallbacks, no partial output. Because the encoder is pure, there is nothing to clean up on
throw.

---

## 5. Public Surface & Files

```text
~/d/mindful/v6/src/
  encode.ts     # spriteToAnsi(sprite): string; private RESET/UPPER_HALF_BLOCK/HEX_RE/fg/bg   (new)
  index.ts      # export { spriteToAnsi }                                                      (modified)
~/d/mindful/v6/tests/
  encode.test.ts   # pure unit tests                                                           (new)
```

`encode.ts` imports `ValidationError` from `@nodes/kernel` and the `Sprite` type from `./sprite.js` —
no other mindful module. The barrel adds `spriteToAnsi`. No other file changes — `api.ts`, `sprite.ts`,
`color.ts`, `identity.ts`, `kinds.ts` are untouched.

---

## 6. Testing Strategy (`encode.test.ts`)

**Exact output (2×2 fixture)** — small enough to assert the full string:
- `{ width: 2, height: 2, pixels: [["#ff0000","#00ff00"],["#0000ff","#ffffff"]] }` encodes to exactly
  one text row:
  `\x1b[38;2;255;0;0m\x1b[48;2;0;0;255m▀\x1b[38;2;0;255;0m\x1b[48;2;255;255;255m▀\x1b[0m`
  (no trailing `\n`).

**Structure (8×8 fixture from a real `renderSprite` output)** — proves SP3-sized sprites encode
correctly:
- splitting the result on `\n` yields exactly **4** text rows.
- each text row contains exactly **8** `▀` glyphs and ends with `RESET`.
- the whole string has no trailing newline.
- for a chosen column, the emitted `fg` substring encodes the top pixel and the `bg` substring encodes
  the bottom pixel (assert the exact `\x1b[38;2;…m` / `\x1b[48;2;…m` sequences).

**Uniform sprite:** every pixel one color → each cell's `fg` sequence equals its `bg` sequence.

**Validation (each throws `ValidationError`):**
- `height` ≠ `pixels.length` (dimension mismatch).
- a ragged row (one row's length ≠ `width`).
- a non-`#rrggbb` pixel (`"red"`, `"#xyz"`).
- an odd height (e.g. a `2×3` sprite).
- a non-positive or non-integer dimension (e.g. `width: 0`, `height: 2.5`).

---

## 7. Out of Scope / Deferred (SP5+)

- **SVG and PNG encoders** (PNG needs a binary-image dependency; SVG deferred until a consumer exists).
- **Animation:** frame sequences, palette cycling, idle motion.
- **The interactive CLI/TUI shell:** the library→app jump, input handling, navigation,
  capture/search/show.
- **Active-scheme storage & scheme-picking UI:** where the chosen colorscheme lives (the deliberate
  storage point) and the UI to choose it.
- **Any I/O:** `spriteToAnsi` returns a string; printing/streaming to a terminal is the caller's job.
- **Color-depth fallbacks:** no 256-color / 16-color downgrade; truecolor only.
- **Odd-height sprites, scaling/zoom, and richer terminal layout:** additive future work. (Positive-width,
  even-height rectangular sprites of any width ARE supported now — only odd height is rejected.)

---

## 8. Decisions Log

1. **SP4 = the ANSI encoder only.** The original SP4 (encoders + shell + scheme UI + animation) is
   decomposed; shell, scheme storage/UI, SVG/PNG, and animation move to later sub-projects.
2. **Half-block `▀` packing, 24-bit truecolor.** Text row `t` = sprite rows `2t` (fg) + `2t+1` (bg);
   8×8 → 4 text rows × 8 glyphs. Square aspect, compact, the standard terminal-image technique.
3. **Pure presentation leaf, no `Mindful` method.** Encoding is presentation; `Mindful` stays a
   data/raster API. The shell composes `spriteToAnsi(m.sprite(id))`. `encode.ts` imports only the
   `Sprite` type.
4. **Strict encoder, not forgiving.** Validates a positive-integer, even-height, rectangular dimension
   contract and `#rrggbb` pixels; throws `ValidationError` and emits nothing on violation.
5. **Positive-width, even-height rectangular sprites of any width.** SP3's 8×8 is the primary caller.
   Only odd height is rejected; odd-height support, scaling/zoom, and richer layout are deferred (avoid
   accidental Hyrum's-Law contracts).
6. **Frozen escape construction:** `RESET = "\x1b[0m"`, `UPPER_HALF_BLOCK = "▀"`, `fg`/`bg` emit exact
   `\x1b[38;2;r;g;bm` / `\x1b[48;2;r;g;bm`; rows joined with `\n`, no trailing newline.
7. **Truecolor only**, no color-depth fallback (YAGNI).
8. **SVG deferred** alongside PNG: pure and no-dep, but no planned consumer yet.
9. **No I/O:** the function returns a string; printing is the caller's responsibility.
10. **No kernel changes; no new runtime dependency.**
