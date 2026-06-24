# Mindful v6 — SP2: Visual Identity (the `visualIdentity` thought facet)

**Status:** Design (approved in brainstorming; pending written-spec review)
**Date:** 2026-06-24
**Repo:** `~/d/mindful/v6` (TypeScript only — **no kernel changes**)
**Builds on:** SP1 (`2026-06-23-mindful-v6-sp1-abstraction-design.md` §3, §7)

**Goal:** Give every `thought` a deterministic, intrinsic **visual identity** — a small,
*color-free* fingerprint derived once from the thought's immutable `uid` and stored as a required
facet — plus a swappable **colorscheme** layer and a pure resolver that maps an identity to concrete
colors. This realizes SP1's promise that `thought = note + VisualIdentity`. Pixel rendering and any
UI for choosing schemes are **SP3**, not here.

**Architecture:** A `thought`'s stored identity carries only abstract, palette-independent *slots*
(`{index, variant}`) plus the `seed` they came from. Concrete colors live in separately-chosen
`Colorscheme`s; a pure `resolve(identity, scheme)` maps each slot to a `#rrggbb` color at
read/render time. Switching the colorscheme re-themes every thought with **zero** stored-data
changes. Everything lands in the mindful package: the kernel already supports **kind-level** required
facets and invariants (`Registry.validate` composes `KindSpec.requiredFacets`/`invariants`), so a
"visual identity" — a domain concept — stays entirely in mindful and never leaks into the
domain-free kernel.

**Tech stack:** TypeScript (Node ≥20, ESM, `.js` import extensions, zod, biome, vitest); `node:crypto`
for the SHA-256 seed (the same module the kernel already uses for `newUid`).

---

## Global Constraints

- **No kernel changes.** SP2 is implemented wholly in `~/d/mindful/v6`. The dependency stays one-way
  (`mindful → @nodes/kernel`); the kernel never learns what a visual identity is.
- **Identity is intrinsic and immutable.** It is a pure deterministic function of the thought's
  persistent `uid`. Editing the title or body, renaming, or retagging **never** changes it.
- **Stored facet is the source of truth.** Validation checks the facet's *structure*, never
  recomputes-and-compares against the derivation. This lets the derivation algorithm evolve later
  without invalidating thoughts already on disk.
- **Color-free identity.** The stored facet contains no colors. `slots[i].index` is a raw `0–255`
  selector, **not** a literal position in any scheme — so identities are independent of any
  colorscheme's length. `resolve` reduces it modulo the scheme size.
- **Fail early; shape errors are `FacetError`.** All structural constraints live in the zod schema,
  surfaced through a `load`-style accessor exactly like `membershipOf`/`edgesOf`. A missing or
  malformed `visualIdentity` facet throws `FacetError` before any disk write. No `InvariantError` is
  used in SP2 (no semantic rule survives zod parsing).
- **Atomic capture preserved.** `capture` keeps SP1's single-write, resolve-tags-first pattern; the
  identity is derived and attached **before** the one `corpus.add`.
- **Greenfield, no migration.** The mindful store has no persisted data (only temp-dir tests), so
  making `visualIdentity` required needs no backfill — consistent with SP1's clean-break principle.

---

## 1. Context & Motivation

SP1 made `thought` its own kind (`{ name: "thought" }`, no shape, no facets) and explicitly deferred
its visual identity (SP1 §3.2, §7): *"`thought` is its own kind now (≈ `note`); SP2 will add
`visualIdentity` as its required facet (`thought = note + VisualIdentity`)."*

SP2 delivers exactly that facet and the minimal color machinery around it. The design separates three
concerns that are easy to conflate:

1. **Identity** — *which* abstract visual slots a thought owns. Intrinsic, deterministic, stored.
2. **Colorscheme** — *what colors exist*. A swappable, user-chosen theme; not stored per-thought.
3. **Resolution** — mapping identity + scheme → concrete colors. A pure function.

Keeping colors out of the stored identity is the key decision: a user can switch colorschemes and
every thought re-themes instantly, and the classic "8-bit/chiptune" aesthetic (NES, PICO-8, …) is
exactly fixed indexed palettes, so an indexed identity is the natural fit. SP3 will render these
identities as actual art; SP2 stops at the data and its resolution.

---

## 2. Data Model

```ts
// Stored on every thought — intrinsic, color-free, derived once from uid.
interface VisualIdentity {
  seed: string;          // 64-char lowercase SHA-256 hex digest of the thought's uid
  slots: ColorSlot[];    // exactly 4
}

interface ColorSlot {
  index: number;         // raw 0–255 selector (NOT a literal scheme position)
  variant: number;       // 0–3: which transform the resolver applies (see §4)
}

// Separate, swappable, NOT stored per-thought.
interface Colorscheme {
  name: string;
  colors: string[];      // flat list of #rrggbb, any length ≥ 1
}
```

**Why 4 slots:** enough for an 8-bit-style sprite (e.g. background + 3 ink colors) while staying tiny
and deterministic. The renderer (SP3) decides what each slot is *for*; SP2 fixes only the count.

**Why a raw `0–255` index:** scheme-size independence. The identity must not assume a particular
number of colors. The resolver maps `scheme.colors[index % scheme.colors.length]`, so any scheme of
any length re-themes every thought.

---

## 3. Derivation — `deriveIdentity(uid)`

A pure, deterministic function (no `Date`, no randomness):

```ts
function deriveIdentity(uid: string): VisualIdentity {
  const seed = sha256hex(uid);               // 64-char lowercase hex, via node:crypto
  const bytes = bytesOf(seed);               // 32 bytes from the digest
  const slots: ColorSlot[] = [];
  for (let i = 0; i < 4; i++) {
    slots.push({ index: bytes[i * 2], variant: bytes[i * 2 + 1] % 4 });
  }
  return { seed, slots };
}
```

- `seed` is the SHA-256 hex digest of the **persistent `uid` field** (not the id slug — the id's
  suffix is a separate random value in SP1; the `uid` is the immutable, on-disk identity).
- Each slot reads **two distinct digest bytes**: `index = bytes[i*2]`, `variant = bytes[i*2+1] % 4`.
  Slots 0–3 therefore consume bytes 0–7 of the 32-byte digest; the selector and the transform come
  from independent bytes so the two visual dimensions vary independently.
- Same `uid` → byte-identical `VisualIdentity`, always.

---

## 4. Resolution — `resolve(identity, scheme)`

A pure function mapping an identity's 4 slots to 4 concrete colors against a chosen scheme:

```ts
function resolve(identity: VisualIdentity, scheme: Colorscheme = defaultColorscheme): string[] {
  return identity.slots.map((slot) => {
    const base = scheme.colors[slot.index % scheme.colors.length];  // size-independent
    return applyVariant(base, slot.variant);                        // HSL transform → #rrggbb
  });
}
```

**Variant transforms** (`applyVariant(hex, variant)`), via HSL math:

| variant | transform  | effect                                  |
|---------|------------|-----------------------------------------|
| `0`     | base       | the scheme entry unchanged              |
| `1`     | light      | lightness raised by a fixed step        |
| `2`     | dark       | lightness lowered by a fixed step       |
| `3`     | accent     | complementary hue (hue + 180°)          |

So from a single K-color scheme, each of a thought's 4 slots can be a base color, a light or dark
shade of it, or its complement — substantial deterministic range while the scheme stays a plain
color list. The exact lightness step is an implementation detail (a fixed constant, e.g. ±20% L); the
*set* of four transforms is the contract.

**Default colorscheme** (`defaultColorscheme`): one built-in chiptune-style palette (a fixed list of
`#rrggbb` colors, ~16 entries) so the decoupling is real and testable without SP3. Its exact colors
are an implementation detail; its identity (a named `Colorscheme`) is the contract. `resolve` and
`Mindful.palette` default to it when no scheme is supplied.

A small internal color module provides `hexToHsl` / `hslToHex` for the transforms; these are
module-private helpers, not part of the public surface (only `resolve`, `defaultColorscheme`, and the
types are exported).

---

## 5. Facet Wiring & Validation

**Schema + accessor** (`src/identity.ts`), mirroring the kernel's `load` pattern (`shapes.ts`):

```ts
export const VISUAL_IDENTITY = "visualIdentity";

const ColorSlotSchema = z.object({
  index: z.number().int().min(0).max(255),
  variant: z.number().int().min(0).max(3),
});
export const VisualIdentitySchema = z.object({
  seed: z.string().regex(/^[0-9a-f]{64}$/, "seed must be a 64-char SHA-256 hex string"),
  slots: z.array(ColorSlotSchema).length(4, "exactly 4 slots required"),
});

export function visualIdentityOf(node: Node): VisualIdentity {
  // throws FacetError on a missing or malformed facet (same as membershipOf/edgesOf)
}
```

All structural constraints live in the schema, so `visualIdentityOf` throws **`FacetError`** for any
malformed payload — consistent with the kernel's existing accessors.

**Kind-level invariant** (`src/identity.ts`): `requireValidVisualIdentity(node)` simply calls
`visualIdentityOf(node)`, forcing schema validation during `Registry.validate`. Because every
constraint is structural, no `InvariantError` path remains in SP2; the named invariant exists so the
registry runs the check and so future semantic rules have a home.

**`thoughtSpec`** (`src/kinds.ts`) gains the facet and invariant:

```ts
export const thoughtSpec: KindSpec = {
  name: THOUGHT,
  requiredFacets: new Set([VISUAL_IDENTITY]),
  invariants: [requireValidVisualIdentity],
};
```

The registry's "unexpected facet" check then allows a thought to carry **only** `visualIdentity`; a
thought with no facets now fails the required-facet check (`FacetError`) before any write.

---

## 6. API Changes (`src/api.ts`)

**`capture`** derives and attaches the identity before the single write, preserving SP1's atomic
pattern:

```ts
capture(input: { title: string; body?: string; tags?: string[] }): Node {
  const node = makeNode({ id: `${THOUGHT}:${newUid()}`, kind: THOUGHT, title: input.title, body: input.body ?? "" });
  node.facets[VISUAL_IDENTITY] = deriveIdentity(node.uid);   // derive from the persistent uid
  const idx = this.aliasIndex();
  for (const name of input.tags ?? []) node.relations.push(this.resolveTag(node.id, name, idx));
  this.corpus.add(node);                                     // one write; nothing persists if a tag threw
  return this.corpus.get(node.id);
}
```

- `deriveIdentity` reads `node.uid` (assigned by `makeNode` via the schema default) — the immutable,
  persisted field, **not** the id slug.
- **`edit` is unchanged.** Identity is uid-derived and immutable; retitling/editing body must not
  alter the face. (No re-derivation, no identity touch.)

**Convenience** (`Mindful.palette`):

```ts
palette(thoughtId: string, scheme: Colorscheme = defaultColorscheme): string[] {
  return resolve(visualIdentityOf(this.corpus.get(thoughtId)), scheme);  // 4 concrete #rrggbb
}
```

This is the right convenience boundary: callers get resolved colors without hand-loading the facet,
while the pure `resolve`/`deriveIdentity` remain independently usable and testable.

**New barrel exports** (`src/index.ts`): `VISUAL_IDENTITY`, `visualIdentityOf`, `deriveIdentity`,
`requireValidVisualIdentity`, `resolve`, `defaultColorscheme`, and the `VisualIdentity`,
`ColorSlot`, `Colorscheme` types.

---

## 7. File Structure

```text
~/d/mindful/v6/src/
  identity.ts   # VISUAL_IDENTITY, schema, visualIdentityOf, deriveIdentity, requireValidVisualIdentity
  color.ts      # Colorscheme type, defaultColorscheme, resolve, applyVariant, hexToHsl/hslToHex (private)
  kinds.ts      # thoughtSpec gains requiredFacets + invariant  (modified)
  api.ts        # capture derives identity; Mindful.palette added  (modified)
  index.ts      # export the new surface  (modified)
~/d/mindful/v6/tests/
  identity.test.ts   # derivation determinism/stability, facet validation
  color.test.ts      # resolve, variant transforms, scheme-size independence, re-theming
```

Split by responsibility: `identity.ts` owns the intrinsic fingerprint and its facet; `color.ts` owns
the theme layer and resolution. They share no state; `color.ts` consumes the `VisualIdentity` type
only.

---

## 8. Error Handling

Fail early, no silent fallbacks. `visualIdentity` missing → `FacetError` (registry required-facet
check). `visualIdentity` malformed (bad seed, wrong slot count, out-of-range `index`/`variant`) →
`FacetError` (schema, via the accessor invoked by the invariant). All before any disk write. `resolve`
on an empty-`colors` scheme is a programming error, not user data — `defaultColorscheme` is non-empty
and a caller-supplied scheme with no colors fails fast (modulo-by-zero guarded with a thrown error).

---

## 9. Testing Strategy

**Derivation (`identity.test.ts`):**
- Determinism: `deriveIdentity(uid)` equals itself across calls; two different uids differ.
- Structure: returns `seed` matching `^[0-9a-f]{64}$` and exactly 4 slots with `index ∈ 0–255`,
  `variant ∈ 0–3`.
- Separate-byte independence: `index` and `variant` of a slot come from distinct digest bytes
  (verified against a known uid's digest).
- Stability across edits: `capture` then `edit` (title and body) leaves `visualIdentityOf` unchanged.
- Facet validation: a thought built with no `visualIdentity` facet fails validation (`FacetError`);
  a thought with a malformed identity (short seed; 3 slots; `variant: 4`; `index: 256`) fails with
  `FacetError`; a valid one passes.

**Resolution (`color.test.ts`):**
- `resolve` returns exactly 4 `#rrggbb` strings.
- Variant transforms: `0` returns the base unchanged; `1`/`2` shift lightness up/down; `3` rotates hue
  ~180° (asserted on known inputs through `hexToHsl`).
- Scheme-size independence: the same identity resolves against schemes of different lengths without
  error (`index % K`), and re-theming (same identity, different scheme) yields different colors but
  the same 4-length structure.
- Empty-scheme guard: `resolve` against a `colors: []` scheme throws.

**Integration:**
- `capture` persists a valid identity; on-disk round-trip (reload corpus) preserves it byte-for-byte.
- `Mindful.palette(thoughtId)` returns 4 colors using the default scheme; with an explicit scheme it
  re-themes.

---

## 10. Out of Scope / Deferred (SP3+)

- **Rendering:** turning an identity into actual 2D "8-bit/chiptune" art, sprites, animation.
- **Scheme-choosing UI / persistence of the active scheme:** SP2 ships the resolver and one built-in
  scheme; choosing/managing schemes (and where the active choice lives) is SP3.
- **Richer identity dimensions:** shape/glyph/creature parameters beyond color slots (the "structured
  visual parameters" option set aside in brainstorming).
- **Per-corpus configurable slot count or palette size:** fixed at 4 slots / 4 transforms in SP2
  (YAGNI).

---

## 11. Decisions Log

1. `VisualIdentity = { seed, slots }`; **color-free** and stored as a required `thought` facet —
   realizes SP1's `thought = note + VisualIdentity`.
2. Derived from the thought's **immutable `uid`** (SHA-256), so identity is intrinsic and **stable
   across edits/renames**.
3. **Materialized**, not computed-on-read: `capture` derives and persists it; the stored facet is the
   **source of truth** (no recompute-and-compare on validate).
4. Colors are **decoupled** from identity: slots hold abstract `{index, variant}`; concrete colors
   live in swappable `Colorscheme`s; a pure `resolve` maps them. Switching schemes re-themes with no
   stored-data change.
5. `index` is a raw **0–255** selector reduced modulo scheme length → **scheme-size independence**.
6. **4 slots**, each `{ index, variant }`; `variant ∈ {base, light, dark, accent(+180° hue)}`.
7. `index` and `variant` derive from **separate digest bytes** (`bytes[i*2]`, `bytes[i*2+1] % 4`).
8. `seed` validated as exactly a **64-char SHA-256 hex** string (structural, not recomputation).
9. Malformed facet payloads surface as **`FacetError`** (schema via accessor), matching the kernel's
   existing facet loaders; **no `InvariantError`** path remains in SP2.
10. **No kernel changes**; SP2 lives entirely in `~/d/mindful/v6`; kind-level required facets +
    invariants already exist in the kernel registry.
11. SP2 scope = identity facet + `Colorscheme` type + built-in default scheme + pure `resolve` +
    `Mindful.palette`. **Rendering and scheme-picking UI are SP3.**
