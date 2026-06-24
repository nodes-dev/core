# Mindful v6 — SP3: Renderer (the `Sprite` generator)

**Status:** Design (approved in brainstorming; pending written-spec review)
**Date:** 2026-06-24
**Repo:** `~/d/mindful/v6` (TypeScript only — **no kernel changes**)
**Builds on:** SP1 (`2026-06-23-mindful-v6-sp1-abstraction-design.md`), SP2
(`2026-06-24-mindful-v6-sp2-visual-identity-design.md`)

**Goal:** Turn a thought's stored `VisualIdentity` into deterministic 8-bit "chiptune"-style art —
a small, vertically-symmetric **sprite** — as a pure, headless function. The pattern derives from the
identity's stored `seed`; the colors come from SP2's resolved palette. The renderer produces an
**abstract raster** (a pure data structure); turning that into terminal/SVG/PNG output, animation, and
the interactive shell are **SP4**, not here.

**Architecture:** A pure generator `spriteCells(identity)` parses the stored 32-byte `seed` into an
8×8 grid of cell values (`0` = background, `1|2|3` = ink slot), generated on the left 4 columns and
mirrored. `renderSprite(identity, colors)` validates a resolved 4-color palette and paints the cells
into a `Sprite` (an 8×8 raster of `#rrggbb`). The core generator depends only on the `VisualIdentity`
type — **not** on `color.ts`; the `resolve`-then-`render` glue lives solely in `api.ts` as
`Mindful.sprite()`, mirroring SP2's `Mindful.palette()`. Everything stays pure and headless: no
`Corpus` access in the renderer, no I/O, no mutation, no persistence.

**Tech stack:** TypeScript (Node ≥20, ESM, `.js` import extensions, zod, biome, vitest). No new runtime
dependencies — pure integer/string math over the existing `VisualIdentity`.

---

## Global Constraints

- **No kernel changes.** SP3 is implemented wholly in `~/d/mindful/v6`. The dependency stays one-way
  (`mindful → @nodes/kernel`); the kernel never learns what a sprite is.
- **Pure and headless.** The renderer is a pure function of `(VisualIdentity, colors)`. It performs no
  I/O, holds no state, touches no `Corpus`, and emits no terminal/file output. SP4 owns encoders.
- **Never mutate identity; never persist.** The renderer reads only; it never writes a facet, never
  calls `corpus.add`, and never persists a resolved palette or sprite. This is the SP2→SP3 boundary:
  the renderer is a pure consumer of identity + palette output.
- **Stored facet is the source of truth.** The pattern derives from the **stored** `identity.seed`,
  never from `deriveIdentity(uid)`. The renderer never re-derives identity from a uid.
- **Color-independence of the pattern.** `spriteCells` is a function of the seed alone; the palette
  never affects which cells are filled. Switching colorscheme re-themes a sprite (its `pixels`) with
  an identical cell grid.
- **Fail early; validate at the public boundary.** `renderSprite` validates its `colors` argument
  (exactly 4 entries, each a valid `#rrggbb`); `spriteCells` validates the `VisualIdentity` shape when
  called directly. Both throw before producing any output. No silent fallbacks, no short grids.
- **Canonical lowercase output.** `Sprite.pixels` entries are normalized to lowercase `#rrggbb`,
  matching SP2 `resolve()` output, so encoders and snapshot tests see stable, canonical colors.

---

## 1. Context & Motivation

SP1 made `thought` its own kind and deferred its visual treatment; SP2 gave every thought a stored,
color-free `VisualIdentity` (`{ seed, slots }`) plus a swappable `Colorscheme` and a pure
`resolve(identity, scheme) → string[4]`. SP1 §7 named **SP3** as "the renderer (2D '8-bit/chiptune'
art, animation) and the CLI/TUI shell."

That original SP3 bundled three independent subsystems: a pure renderer, an interactive shell, and a
scheme-picking UI. They are decomposed: **SP3 is the renderer only** — a pure, headless,
foundational function that everything else consumes. The shell, scheme-selection UI, and the
"where the active scheme lives" storage point move to **SP4**, where the package makes its larger jump
from library to application. Animation is deferred with them: the static sprite raster is exactly the
foundation animation would build on, and animation shows its value inside the shell.

SP3 keeps the same philosophy as SP1/SP2: small, well-bounded, deterministic, unit-testable units with
no hidden state.

---

## 2. Data Model

```ts
// A cell's palette role. 0 = background, 1|2|3 = ink slot.
type CellValue = 0 | 1 | 2 | 3;

// The uncolored sprite grid: 8 rows × 8 columns by contract.
type SpriteCells = CellValue[][];

// An abstract raster — pure data; SP4 encoders turn it into ANSI/SVG/PNG.
interface Sprite {
  width: number;        // 8
  height: number;       // 8
  pixels: string[][];   // [row][col] → lowercase "#rrggbb"
}
```

- A cell value `s` is painted with `colors[s]`, so palette slot `0` is the background and slots `1–3`
  are the three ink colors — the "background + 3 inks" framing fixed in SP2 (§2).
- `CellValue` is a union, not `number`, so `pixels[row][col] = colors[cells[row][col]]` is explicit and
  hard to misuse (the index is provably in `0..3`).
- Grid dimensions are fixed at **8×8** by contract (the canonical NES/chiptune tile size), asserted in
  tests rather than carried as parameters (YAGNI: configurable size is SP4+).

---

## 3. Generative Algorithm — `spriteCells(identity)`

A pure, deterministic function of the **stored** `identity.seed` (no `Date`, no randomness, no uid
re-derivation):

```ts
function spriteCells(identity: VisualIdentity): SpriteCells {
  // 1. Validate shape when called directly (fail early); see §6.
  // 2. Parse the 64-char hex seed into 32 bytes.
  // 3. Generate the left 4 columns × 8 rows = 32 cells, one byte per cell.
  // 4. Mirror columns 0..3 into columns 7..4.
}
```

- **Grid & symmetry:** 8×8 with a vertical (left–right) mirror. Only the **left 4 columns × 8 rows =
  32 cells** are generated; each generated column `c` is copied to column `7 - c`.
- **Byte mapping:** the `seed` is exactly 32 bytes — **one byte per generated cell**. For generated
  cell at `(row, col)` with `col ∈ 0..3`, the byte index is `row * 4 + col`. For that byte `b`:
  - **Filled?** `filled = (b & 0x80) !== 0` (top bit → ~50% density, the identicon norm).
  - **Which ink?** if `filled`, the cell value is `(((b >> 1) % 3) + 1)` → `1 | 2 | 3`; if not filled,
    the cell value is `0` (background).
- **Mirror:** `cells[row][7 - col] = cells[row][col]` for `col ∈ 0..3`.
- Same stored `seed` → byte-identical `SpriteCells`, always. The palette never enters this function.

This exact algorithm is SP3's frozen first slice. Density shaping, richer masks, and larger grids are
deferred to SP4, when generated sprites can actually be inspected.

---

## 4. Painting — `renderSprite(identity, colors)`

A pure function mapping a cell grid through a resolved 4-color palette into a `Sprite`:

```ts
function renderSprite(identity: VisualIdentity, colors: string[]): Sprite {
  // 1. Validate colors: exactly 4 entries, each matching /^#[0-9a-f]{6}$/i; else throw (fail early).
  // 2. cells = spriteCells(identity)   // also validates identity shape
  // 3. pixels[row][col] = colors[cells[row][col]].toLowerCase()
  // 4. return { width: 8, height: 8, pixels }
}
```

- **Color validation:** `colors.length === 4` and every entry is a valid `#rrggbb` (case-insensitive
  regex). The pure renderer protects its own boundary even though `Mindful.sprite()` always feeds it
  `resolve()` output (which is already valid and lowercase).
- **Lowercase normalization:** each painted color is lowercased, so `Sprite.pixels` is canonical
  regardless of caller casing — matching SP2 `resolve()`.
- **No scheme dependency:** `renderSprite` takes 4 resolved color strings, not a `Colorscheme`. The
  module never imports `color.ts`.

---

## 5. API Changes (`src/api.ts`)

A convenience boundary mirroring SP2's `palette()`:

```ts
sprite(thoughtId: string, scheme: Colorscheme = defaultColorscheme): Sprite {
  const node = this.corpus.get(thoughtId);          // RefError if no such thought
  const identity = visualIdentityOf(node);          // FacetError if missing/malformed; load once
  return renderSprite(identity, resolve(identity, scheme));
}
```

- `visualIdentityOf(node)` is loaded **once** into a local and reused for both `resolve` and
  `renderSprite` (no double load).
- `resolve(identity, scheme)` is SP2's pure resolver; `sprite()` is the only place `resolve` and
  `renderSprite` are composed.
- `capture`/`edit` are **unchanged**: the renderer adds no stored data and no write path.

**New barrel exports** (`src/index.ts`): `renderSprite`, `spriteCells`, and the `Sprite`,
`SpriteCells`, `CellValue` types.

---

## 6. File Structure

```text
~/d/mindful/v6/src/
  sprite.ts        # CellValue, SpriteCells, Sprite types; spriteCells; renderSprite   (new)
  api.ts           # Mindful.sprite() added                                            (modified)
  index.ts         # export the renderer surface                                       (modified)
~/d/mindful/v6/tests/
  sprite.test.ts               # spriteCells + renderSprite (pure unit tests)           (new)
  sprite-integration.test.ts   # Mindful.sprite() end-to-end + re-theme                 (new)
```

`sprite.ts` imports only the `VisualIdentity` type (and `VisualIdentitySchema` for direct-call
validation) from `identity.ts`; it does **not** import `color.ts`. The `resolve`-then-`render` glue
lives solely in `api.ts`. Split by responsibility: `identity.ts` owns the fingerprint, `color.ts` owns
the theme/resolution, `sprite.ts` owns the pattern/raster. They share only types.

---

## 7. Error Handling

Fail early, no silent fallbacks:

- **`renderSprite`** throws `ValidationError` (the project's existing fail-early error, from
  `@nodes/kernel`) if `colors.length !== 4` or any entry is not a valid `#rrggbb`, before producing any
  pixels.
- **`spriteCells`** validates the `VisualIdentity` shape when called directly: it runs
  `VisualIdentitySchema.safeParse(identity)` and throws `ValidationError` on a malformed shape (e.g. a
  seed that is not 64 hex chars), rather than parsing a short byte array and silently emitting an
  under-sized grid. This is symmetric with `renderSprite`'s color validation.
- **`Mindful.sprite()`** surfaces the existing accessor errors unchanged: `RefError` (no such thought),
  `FacetError` (missing/malformed `visualIdentity` facet, via `visualIdentityOf`). The
  `FacetError`-on-`Node`-load path stays in `visualIdentityOf`; direct `spriteCells`/`renderSprite`
  calls (no `Node`) raise `ValidationError`.

---

## 8. Testing Strategy

**Pure (`sprite.test.ts`):**
- **Determinism:** `spriteCells(id)` equals itself across calls; two different seeds produce different
  grids.
- **Dimensions & type:** exactly 8 rows × 8 columns; every value ∈ `{0, 1, 2, 3}`.
- **Vertical symmetry:** `cells[r][c] === cells[r][7 - c]` for all `r ∈ 0..7`, `c ∈ 0..7`.
- **Byte mapping:** against a hand-chosen seed, assert specific cells match the `(b & 0x80)` fill rule
  and the `(((b >> 1) % 3) + 1)` ink rule for known bytes.
- **Palette independence:** the same identity yields identical `spriteCells` and differing `pixels`
  under two different 4-color palettes.
- **`renderSprite` validation:** throws on 3-color and 5-color arrays and on a malformed entry (e.g.
  `"#xyz"`, `"red"`); a valid call satisfies `pixels[r][c] === colors[cells[r][c]]` (lowercased).
- **`spriteCells` validation:** a malformed `VisualIdentity` (short seed, non-hex seed) throws
  `ValidationError` on a direct call.
- **Lowercase normalization:** `renderSprite` with an upper-case palette (e.g. `"#ABCDEF"`) yields
  lowercase `pixels`.

**Integration (`sprite-integration.test.ts`):**
- `capture` then `Mindful.sprite(id)` returns an 8×8 sprite; reloading the corpus yields a
  byte-identical sprite (stored-seed determinism, no re-derivation).
- The same thought rendered against two schemes yields identical `cells` (verified via `spriteCells`)
  but different `pixels` (re-theming through the `sprite()` path).
- `Mindful.sprite()` on a missing id throws `RefError`.

---

## 9. Out of Scope / Deferred (SP4+)

- **Animation:** frame sequences, palette cycling, idle motion.
- **Encoders:** ANSI/terminal, SVG, PNG, or any concrete output format. SP3 stops at the abstract
  raster.
- **The CLI/TUI shell:** the interactive application; the library→app jump.
- **Scheme-picking UI & active-scheme storage:** choosing/managing schemes and where the active choice
  lives (the deliberate storage point).
- **Algorithm enrichment:** density shaping, richer masks, multi-tile or larger grids, configurable
  sprite size — deferred until sprites are visually inspectable in SP4.

---

## 10. Decisions Log

1. **SP3 = the renderer only.** The original SP3 (renderer + shell + scheme UI) is decomposed; shell,
   scheme-picking UI, active-scheme storage, and animation move to **SP4**.
2. **Output is an abstract raster** (`Sprite` = 8×8 grid of `#rrggbb`), a pure data structure. Encoders
   are SP4.
3. **Symmetric sprite** (identicon-style), **8×8** grid with **vertical mirror**: left 4 columns
   generated, mirrored to the right.
4. **Silhouette + 3 inks** color mapping: cell value `0` = background, `1|2|3` = ink; `pixels[r][c] =
   colors[cells[r][c]]`. Uses all 4 palette colors and yields a clear figure/ground.
5. **Byte mapping:** the 32-byte `seed` gives one byte per generated cell (`row*4 + col`); fill =
   `(b & 0x80)`, ink = `(((b >> 1) % 3) + 1)`. Frozen as SP3's first slice.
6. **Pattern derives from the stored `seed`,** never `deriveIdentity(uid)` — stored facet is the
   source of truth.
7. **`spriteCells` is color-free and exported** — the canonical test surface for determinism,
   symmetry, byte mapping, and palette independence.
8. **`renderSprite(identity, colors)` takes resolved colors,** not a `Colorscheme`; `sprite.ts` never
   imports `color.ts`. The `resolve`-then-`render` glue lives only in `Mindful.sprite()`.
9. **Typed cells** (`CellValue = 0|1|2|3`, `SpriteCells = CellValue[][]`) make the paint mapping
   explicit and misuse-resistant.
10. **Fail early at both public boundaries:** `renderSprite` validates colors (4× `#rrggbb`);
    `spriteCells` validates identity shape (`VisualIdentitySchema`) on direct calls. Both raise
    `ValidationError`. `FacetError` only on the `Node`-load path (`visualIdentityOf`).
11. **Canonical lowercase `pixels`,** matching SP2 `resolve()`, for stable encoders/snapshots.
12. **No kernel changes; pure and headless;** no mutation, no persistence — the renderer is a pure
    consumer of identity + palette output.
