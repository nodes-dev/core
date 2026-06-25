# mindful v6 — SP8: Organic Generative Visuals (Design)

**Status:** Draft for review
**Date:** 2026-06-24
**Project:** mindful v6 (`~/d/mindful/v6`), built on the `nodes` kernel
**Builds on:** SP2 (visual identity), SP3 (sprite renderer), SP4 (ANSI encoder), SP6 (scheme catalog)

## 1. Goal

Replace the deterministic-but-blocky 8×8 byte-mirror sprite with **organic, generative visuals derived from real scientific models**. Each thought is rendered as a small raster produced by a *faithful* implementation of a natural-systems formula (reaction–diffusion, standing waves, a strange attractor, …), colored by the thought's semantic cluster and themed by the active colorscheme. Output stays a terminal-renderable raster via the existing SP4 ANSI half-block encoder.

The visuals must be **coarse but real** — faithful to the actual math, not decorative look-alikes — and fully **deterministic, pure, and headless** (a function of the thought's immutable `uid`, no network, no model inference, no heavy dependencies).

## 2. Background — current state

- **SP2 `identity.ts`:** every `thought` has a required `visualIdentity` facet `{ seed, slots }` derived from its immutable `uid` via SHA-256. `seed` is the 64-char hex digest; `slots` is 4× `{ index, variant }`. The stored facet is source of truth.
- **SP3 `sprite.ts`:** `spriteCells(identity)` turns `seed` bytes into an 8×8 mirrored `CellValue 0|1|2|3` grid; `renderSprite(identity, colors)` paints it through 4 colors into a `Sprite { width, height, pixels: string[][] }`.
- **SP4 `encode.ts`:** `spriteToAnsi(sprite)` packs a `Sprite` into 24-bit truecolor half-block (`▀`) text — full per-pixel color, 2 sprite rows per text row, even height required.
- **SP6 `color.ts` / `schemes.ts`:** `Colorscheme { name, colors: string[] }`; a 6-scheme catalog (chiptune-16 default, gameboy, dawnbringer-16, monochrome, nord, solarized). `resolve(identity, scheme)` maps the 4 slots to concrete colors. HSL helpers `hexToHsl` / `hslToHex` / `applyVariant` live (private) in `color.ts`. Each scheme lists its darkest color first by convention.
- `Mindful.sprite(id, scheme?)` is the glue: resolve → render. `Mindful.palette(id, scheme?)` is a separate boundary.

SP8 swaps the **generator** (byte-mirror → formula field) while reusing the **seed**, the **scheme catalog**, the **`Sprite` type**, and the **ANSI encoder** unchanged.

## 3. Scope

**In scope (SP8):**
- A *semantic cluster* concept: an integer `clusterId ∈ [0, K)`, derived deterministically from the uid (a hash bucket — a faithful stub for future content-based clustering).
- A **family registry** of `K = 6` vetted, genuinely-faithful generative models, each tied to a real natural-systems catalog slug.
- A **field pipeline**: uid → model parameters (+ a seeded noise term) → grid evaluation → a normalized scalar `Field`.
- A **colormap**: scalar `Field` value → color, hue chosen by `clusterId`, themed by the active scheme.
- Integration: `Mindful.sprite` reroutes to the pipeline; the visual size becomes a parameter (default 24×24).
- Determinism, faithfulness, and validation tests.

**Out of scope (deferred — see §13):**
- Real semantic clustering from embeddings (the cluster stays a hash bucket).
- Animation playback (generators may carry a time axis, but SP8 renders one frame).
- Empirical frequency-weighted cluster assignment (uniform for now).
- Families 7–15 (architecture grows to them later).
- Richer-glyph / WebGL / three.js renderers (the generator layer is built renderer-agnostic so these can be added later — see §12).

## 4. Architecture & data flow

```
uid
 → deriveIdentity(uid)            (SP2, existing)       → { seed, slots }
 → clusterId = familyOf(seed)     ∈ [0, K)              hash bucket (stub for real clustering)
 → family    = REGISTRY[clusterId]                       { slug, name, paramSpecs, generate }
 → params    = paramSpecs.map(spec → mapSeed(seed, spec))   + a seeded PRNG for stochastic models
 → field     = family.generate(params, size, rng)       Field { width, height, values:number[][] in [0,1] }
 → pixels    = field.values.map(v → colormap(v, clusterId, scheme))   per-pixel #rrggbb
 → sprite    = { width, height, pixels }                 (existing Sprite type)
 → spriteToAnsi(sprite)                                  (SP4, existing)
```

**New modules (all pure, headless, no heavy deps):**
- `src/families.ts` — the registry: `K = 6` family entries + their `generate` functions + parameter specs transcribed from the catalog.
- `src/field.ts` — `Field` type, parameter derivation (`mapSeed`), the seeded PRNG, grid evaluation orchestration, normalization.
- `src/colormap.ts` — scalar → color ramp.

**Modified:** `src/api.ts` (`Mindful.sprite` reroute + `size` param), `src/index.ts` (barrel). `add`/`show` CLI call sites are unchanged (they call `Mindful.sprite(id, scheme)` with the default size).

**Retired for the avatar:** the byte-mirror `spriteCells` and the 4-color `renderSprite` are no longer used to render a thought; remove them if no longer referenced. The `Sprite` type, `spriteToAnsi`, `resolve`, and `Mindful.palette` are retained.

## 5. Semantic identity (clusters)

`clusterId` is a single integer in `[0, K)`, one per thought, naming a "domain of thought." Each cluster owns **one model family + one color hue**, so all thoughts in a cluster are visually kin.

- **Derivation (now):** `familyOf(seed)` reads a fixed 2-byte slice of the SHA-256 `seed` (distinct from the bytes used for model parameters, so adding/changing parameters never shifts a thought's cluster) and reduces it modulo `K`. Pure function of the uid; no storage, no migration of existing thoughts.
- **`K` = number of registered families** (6 in SP8), so every `clusterId` maps to a real model.
- **Future seam:** real semantic clustering depends on a thought's *content* (embeddings), not its uid, so it cannot be a uid-derived function. The future SP that introduces it will add a **stored** `semanticIdentity` facet plus a compute pipeline; SP8 deliberately does *not* store the stub, to avoid a facet migration now and a reshape later. `familyOf` is the single seam that future work replaces.

**Decision (ratified):** derive `clusterId` from the seed at render time; do not store it.

## 6. Family registry (`K = 6`)

Six models chosen for **faithfulness**, **visual diversity**, and to exercise both generator shapes (closed-form `f(x,y)` and seeded `simulate → snapshot`). Each is tied to its real catalog slug. **Parameter ranges are transcribed into the registry from the natural-systems catalog (`~/d/natural-systems`, `guide-data.json`) with provenance comments — mindful v6 stays a standalone package and never reads that repo at runtime.** Several catalog *hover* animations are decorative fakes (e.g. `grayScottHover`, `waveEquationHover`); SP8 implements the genuine update rules, not those.

| # | Family | Slug | Shape | Core math (evaluated over `[0,1]²` unless noted) |
|---|--------|------|-------|---------------------------------------------------|
| 0 | Reaction–diffusion | `gray-scott` | seeded sim → snapshot | `uₜ = Dᵤ∇²u − uv² + F(1−u)`, `vₜ = Dᵥ∇²v + uv² − (F+k)v`; periodic 5-point Laplacian; seeded `v` perturbations; snapshot `v`. Catalog defaults `Dᵤ=0.16, Dᵥ=0.08`; vary `F∈[0.02,0.06]`, `k∈[0.05,0.07]`. |
| 1 | Standing waves (Chladni) | `modal-acoustics` | closed-form | `f(x,y) = cos(nπx)cos(mπy) − cos(mπx)cos(nπy)`; field `= |f|`. `n,m ∈ {1..6}` from seed. Square-plate eigenmode superposition. |
| 2 | Logistic map | `logistic-map` | iterated map → density | `xₙ₊₁ = r·xₙ(1−xₙ)`; column = `r ∈ [r₀,r₁] ⊂ [2.8,4.0]`, row = `x ∈ [0,1]`; burn-in then accumulate visited `x` into a per-column density (bifurcation diagram). |
| 3 | Gravitational potential | `n-body-problem` | closed-form | `Φ(x,y) = −Σᵢ G·mᵢ / √((x−xᵢ)²+(y−yᵢ)²+ε²)` over `M` seeded masses (softened); field `= Φ`. `M∈{2..5}`, positions/masses from seed. |
| 4 | Phyllotaxis (Vogel) | `vogel-phyllotaxis` | closed-form geometry | seed `i` at angle `i·137.507°`, radius `c·√i`; field = distance to nearest seed (Voronoi-like). `N`, `c` from seed. |
| 5 | Strange attractor (Lorenz) | `lorenz-attractor` | seeded ODE → projection density | `ẋ=σ(y−x), ẏ=x(ρ−z)−y, ż=xy−βz`; `σ=10, β=8/3`, `ρ∈[24,30]`; integrate (RK4, `dt≈0.005`) from seeded init; accumulate `(x,z)` projection into a log-scaled density grid. |

Mixing: two closed-form fields (Chladni, gravitational), one iterated map (logistic), one closed-form geometric (phyllotaxis), two simulations (Gray–Scott PDE, Lorenz ODE). Simulations may run on an internal grid larger than `size` and downsample.

## 7. Field pipeline (`field.ts`)

- **`Field` type (renderer-neutral):** `interface Field { width: number; height: number; values: number[][] }`, every value normalized to `[0,1]`, `values.length === height`, each row length `width`. This is the common currency every renderer consumes (§12).
- **Parameter derivation `mapSeed(seed, spec)`:** each `paramSpec` declares `{ name, min, max, byteOffset }` (or an integer set for `n,m,M,N`); `mapSeed` reads bytes at `byteOffset` from the `seed` hex, forms a `u ∈ [0,1)`, and returns `min + (max−min)·u` (or selects from the integer set). Distinct offsets per parameter; offsets are disjoint from the cluster slice (§5).
- **Seeded PRNG:** a small inline `mulberry32` (no dependency) seeded from a 32-bit uid-derived value, used for stochastic initial conditions / noise (Gray–Scott perturbations, Lorenz init jitter). Deterministic given the uid.
- **Normalization:** each generator returns raw values; the pipeline normalizes to `[0,1]` (min–max, or a documented log scale for density fields) before colormapping.
- **Generator signature:** `generate(params, size, rng) → Field`. Pure given its inputs.

## 8. Colormap (`colormap.ts`)

**Decision (ratified):** continuous single-hue HSL ramp keyed by cluster.

- `clusterId` picks a **base color** from the active scheme: `base = scheme.colors[clusterId % scheme.colors.length]`.
- The colormap converts `base` to HSL and ramps **lightness** across the normalized value `v ∈ [0,1]` on the base hue/saturation: roughly `L(v) = lerp(L_low, L_high, v)` with `L_low ≈ 0.06` (near-black background for `v=0`) and `L_high ≈ 0.78`. Output via `hslToHex`. (Single-hue lightness ramp avoids hue-interpolation artifacts and keeps "color = cluster".)
- `hexToHsl` / `hslToHex` are promoted from private to **exported** in `color.ts` for reuse; no behavior change.
- Color is therefore tied to **semantic identity** (the cluster's hue) and themed by the **active scheme** (which palette the hue is drawn from). Low-color schemes (e.g. gameboy's 4 greens) still produce a valid, low-contrast ramp.

## 9. Rendering & integration

- **`Mindful.sprite(id, scheme?, size = 24)`** reroutes to the pipeline: load thought → `visualIdentityOf` (existing) → `seed` → `clusterId` → `family.generate` → `colormap` → `Sprite`. `size` must be a positive **even** integer (the SP4 encoder requires even height); fail-early `ValidationError` otherwise. Default `24` → 24 wide × 12 tall in the terminal.
- **CLI `add`/`show`** keep calling `Mindful.sprite(id, scheme)` (default size); no call-site changes. Exposing `size` as a CLI flag is deferred.
- **`spriteToAnsi`** consumes the `Sprite` unchanged.

## 10. Determinism, validation, error model

- **Determinism:** the entire pipeline is a pure function of the uid (via the stored `seed`) + the chosen `size` + the active scheme. No `Date`, no `Math.random` (the inline PRNG is uid-seeded). Same inputs → byte-identical ANSI.
- **Purity / deps:** no new runtime dependencies; no reading of external files; no `~/d/natural-systems` access at runtime. Only `ValidationError` (and existing types) from `@nodes/kernel`.
- **Validation (fail-early):** invalid `size` (non-even / non-positive); any `Field` value outside `[0,1]` or `NaN`; malformed colormap output (`colormap` must return a valid `#rrggbb`); wrong `Field` dimensions — all `ValidationError`. `spriteToAnsi`'s existing strict validation remains the final gate.

## 11. Testing strategy

- **Determinism (golden):** for ≥2 fixed uids per family, snapshot the rendered ANSI; assert stability across runs.
- **Faithfulness (characterization), one per generator:**
  - `logistic-map`: orbit reproduces known behavior (fixed point for `r<3`, period-2 onset at `r=3`, chaos near `r=4`).
  - `n-body-problem`: potential is monotonic in `1/r` from a single mass; superposition adds.
  - `modal-acoustics`: nodal set (`f≈0`) lies on the predicted lines for given `n,m`; symmetry holds.
  - `gray-scott`: from a seeded perturbation the field develops non-trivial structure (variance grows; not uniform).
  - `vogel-phyllotaxis`: consecutive seeds differ by the golden angle; radius ∝ `√i`.
  - `lorenz-attractor`: trajectory stays bounded; projected density is bimodal (two lobes).
- **Pipeline / units:** `mapSeed` covers its range and is stable; PRNG is deterministic; `Field` normalized to `[0,1]` with correct dims; `colormap` returns valid lowercase `#rrggbb` and is monotonic in lightness; `size` validation rejects odd/non-positive.
- **Integration:** `Mindful.sprite(id)` returns a valid `Sprite` (24×24) and `spriteToAnsi` succeeds for every family.
- **Gate:** `rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`.

## 12. Renderer-agnostic seam (future web reuse)

The deliberate split — **generators produce a renderer-neutral `Field` (and, where natural, the underlying point sets), and renderers consume it** — is what lets the *same* model code drive multiple front-ends. SP8 ships the **ANSI** renderer (`Field → colormap → Sprite → spriteToAnsi`). A future SP can add a **web/WebGL** renderer (R3F / `@opentui/three`, as used in mindful v3–v5) that consumes the same `families.ts`/`field.ts` output: a `Field` maps to a texture or heightmap; point-based families (phyllotaxis, Lorenz, n-body) can expose their point sets for geometry. **No three.js/OpenTUI dependency is added in SP8** — doing so would pull a WebGL stack into a pure-headless, zero-heavy-dep package. The seam (pure generators, swappable renderers) is the forward-compat investment; the second renderer is deferred.

## 13. Decisions log

1. **Seed-driven only** — no embeddings / semantic-model layer in SP8.
2. **Replace, not coexist** — the formula field replaces the byte-mirror sprite as the thought avatar everywhere.
3. **Size is a parameter, default 24×24** (even/positive; encoder needs even height).
4. **`clusterId` derived from the seed, not stored** — hash bucket now; future real clustering adds a stored `semanticIdentity` facet (it depends on content, not uid).
5. **`K` = number of registered families** (6 in SP8), so every cluster maps to a real model.
6. **Strong initial set, grow to 15** — ship 6 vetted, diverse generators; architecture accepts more.
7. **Faithfulness is a vetting gate** — hand-port only verified-genuine math; the catalog's fake hover animations are not used as-is.
8. **No runtime dependency on `~/d/natural-systems`** — parameter ranges/slugs are transcribed into the registry with provenance.
9. **Continuous single-hue HSL colormap** keyed by cluster, themed by the active scheme; `hexToHsl`/`hslToHex` exported from `color.ts`.
10. **Renderer-agnostic generators** — `Field` is the common currency; ANSI now, web/three.js deferred (§12); no WebGL dep added.
11. **Generators may carry a time axis** but SP8 renders a single deterministic frame; animation playback deferred.
12. **Empirical frequency weighting deferred** — cluster assignment is uniform (hash bucket) until the arXiv catalog matures.

## 14. Deferred / future SPs

- Real semantic clustering from embeddings (stored `semanticIdentity` facet + compute pipeline).
- Families 7–15 (toward the full `K≈15` cluster space).
- Web/WebGL renderer (R3F / `@opentui/three`) reusing the SP8 generators (§12).
- Animation playback (multi-frame `t` sampling + a player).
- Empirical frequency-weighted cluster/formula sampling once the natural-systems arXiv catalog provides per-formula counts.
- Richer-glyph terminal encoders (quadrant/braille) as alternative `Field` consumers.
- The long-standing deferred SP1 duplicate-container-collision test (non-blocking).
