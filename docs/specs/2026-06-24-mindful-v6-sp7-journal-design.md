# Mindful v6 — SP7: Journal (capture-time + time-ordered view) (Design)

**Status:** approved (brainstorming) — ready for planning
**Date:** 2026-06-24
**Repo:** `~/d/mindful/v6` (TS only, no kernel changes)
**Specs/plans home:** `~/d/nodes/docs/{specs,plans}/`
**Builds on:** SP1 (thought kind, `Mindful` API), SP2 (required `visualIdentity` facet precedent), SP3/SP4 (sprite + ANSI), SP5 (CLI shell, injected `root`/`env`/sinks), SP6 (active scheme threading)

## 1. Overview

Today a thought has no time. `metadata.created` exists in the kernel but is day-granularity,
defaults to `null`, and `capture()` never sets it. There is no way to ask "what did I write today"
or to walk a corpus in time order. SP7 makes time **intrinsic** to a thought and adds a **journal**:
a low-friction "jot it now, organize later" capture surface plus a time-ordered reading view.

The user's model (locked during brainstorming): thoughts exist in one collection; *structures*
(sets, lists, graphs) relate them; **"journal" and "mindmap" are how a set of thoughts is
represented in UX**, not separate storage. The journal here is the **diary/timeline lens** — a
derived view that projects thoughts within a time window (default: today). It is a different feature
from the SP1 `journal` *kind* (a named, explicitly-ordered list); that kind is untouched by SP7.

SP7 adds three things that do not exist today:

1. A **required `captured` facet** on every thought — a precise capture instant (`{ at }`).
2. A **pure journal projection** — `journalView(thoughts, window)` grouping thoughts by date in
   stored-local-time order. No container node, no I/O.
3. **CLI surface** — `add` stamps the capture instant; a new `journal` command reads a day or range.

### Scope (locked)

- **In:** an intrinsic capture timestamp; a pure date-windowed projection; `journal` read command
  (today / single date / `--since`/`--until` range); injected clock.
- **Out (deferred):** relative date keywords (`yesterday`, `--days N`); intra-day sub-views /
  sampling granularity; the SP1 named-`journal` *kind* CLI; editing the capture time; the richer v5
  activity model (`interactionCount`, `connectedness`, momentum, etc.); mindmap CLI; sprites in the
  journal list.

### Standing boundary (still binding, honored here)

The journal is a **representation/view**, so — exactly like `encode.ts` — it lives **outside**
`Mindful` core as a pure module the CLI composes (`journalView(mindful.allThoughts(), window)`);
there is no `Mindful.journal` method. The impure clock stays at the edge (`bin.ts`); `Mindful` and
`runCli` receive time explicitly and remain deterministic. Stored identity is never mutated.

## 2. Current state (verified)

- **Kernel `metadata`** (`@nodes/kernel`): `created`/`updated` are `YYYY-MM-DD` date strings
  (regex + real-calendar refine), nullable, **default `null`**; `version` defaults to 1. There is no
  time-of-day field, and `makeNode`/`capture` set none of them.
- **`src/identity.ts`** — the facet precedent SP7 mirrors: a constant (`VISUAL_IDENTITY`), a strict
  zod schema, a `visualIdentityOf(node)` loader that throws `FacetError` on missing/malformed, and a
  `requireValidVisualIdentity(node)` kind invariant.
- **`src/kinds.ts`** — `thoughtSpec` declares `requiredFacets: new Set([VISUAL_IDENTITY])` and
  `invariants: [requireValidVisualIdentity]`.
- **`src/api.ts`** — `Mindful.capture({ title, body?, tags? })` makes the node, attaches
  `visualIdentity` (derived from `uid`), resolves tags, and does **one** `corpus.add` (atomic: a
  throwing tag persists nothing). `allThoughts()` returns `corpus.all().filter(kind === THOUGHT)`.
- **`src/cli.ts`** — `runCli(argv, mindful, root, env, out, err): number`; `parseFlags` rejects a
  duplicate single-valued flag via a token scan; `cmdAdd` prints `added <id>` + sprite. Error model:
  `CliUsageError` (optional per-error `usage`) → exit 2; `CliError`/`NodesError`/`ConfigError` →
  exit 1. Sinks receive complete newline-terminated strings; no sink call when there is no output.
- **`src/bin.ts`** — resolves `root`, `mkdirSync`, `new Mindful(root)`, passes `root` + `process.env`
  + sinks into `runCli`.
- **`tests/profile.test.ts`** — builds a "valid thought" fixture by attaching only `visualIdentity`.
  After SP7 that fixture needs **both** facets.

## 3. Module layout

Two new modules + edits to `kinds.ts`/`api.ts`/`cli.ts`/`bin.ts`/`index.ts`. Dependency direction
is one-way (`captured → kernel`; `journal → {kernel, captured}`; `cli → {journal, captured, …}`); no
cycles. `journal.ts` has no `Corpus` and no I/O.

### `src/captured.ts` — the capture-time facet (mirrors `identity.ts`)

```ts
export const CAPTURED = "captured";

// at: an ISO-8601 datetime that carries an explicit offset (Z or ±HH:MM).
// Naive (offset-less) and date-only strings are rejected. Fractional seconds allowed.
export const CapturedSchema = z.object({ at: z.string().datetime({ offset: true }) }).strict();
export type Captured = z.infer<typeof CapturedSchema>;

export function capturedOf(node: Node): Captured;            // FacetError if missing/malformed
export function requireValidCaptured(node: Node): void;      // kind invariant → forces validation

// Centralized extraction: validate `at` through CapturedSchema FIRST, then read the stored
// wall-clock parts. CLI/journal never slice a raw datetime string themselves.
export function capturedDate(at: string): string;            // "YYYY-MM-DD" (stored local date)
export function capturedTime(at: string): string;            // "HH:MM" (stored wall clock; secs/fraction ignored)

// Side-effect-free Date formatter using the local timezone; produces an ISO string with a
// local ±HH:MM offset. bin.ts calls localIso(new Date()); tests pass a fixed Date.
export function localIso(date: Date): string;
```

- `capturedOf`/`requireValidCaptured` are exact analogues of `visualIdentityOf`/
  `requireValidVisualIdentity` — a missing or malformed `captured` facet is a shape error
  (`FacetError`), surfaced during `Registry.validate`.
- `capturedDate`/`capturedTime` are the **single** datetime contract for the rest of the app. Both
  parse `{ at }` through `CapturedSchema` before extracting, so no second implicit datetime semantics
  can grow in CLI or journal code. They return the **stored wall-clock** parts (the date/time as
  written, regardless of offset form) — never a runtime-timezone re-interpretation.
- `localIso` is the only place a wall clock is read; it is exercised by `bin.ts` with `new Date()`.

### `src/journal.ts` — the pure projection (mirrors the `encode.ts` boundary)

```ts
export interface JournalEntry { id: string; title: string; at: string; }   // the lightweight "ThoughtLight"
export interface DayGroup { date: string; entries: JournalEntry[]; }
export interface DateWindow { since: string; until: string; }              // inclusive YYYY-MM-DD bounds

// Regex + real-calendar refine for YYYY-MM-DD window bounds; exported so the CLI reuses it.
export const JournalDateSchema: z.ZodType<string>;

export function journalView(thoughts: Node[], window: DateWindow): DayGroup[];
```

`journalView`:
1. Validates `window.since` and `window.until` through `JournalDateSchema`; rejects `since > until`
   (lexicographic compare, valid for `YYYY-MM-DD`) — both **fail-early** with `ValidationError`.
2. Filters input to `kind === THOUGHT` **internally** (the signature accepts `Node[]`, so a stray
   mindmap/journal-kind node cannot leak in and throw on a missing `captured`).
3. For each remaining thought, computes `capturedDate(capturedOf(node).at)`; keeps those with
   `since <= date <= until`.
4. Sorts entries in **stored-local-timestamp order**: ascending lexicographic on the `at` string
   *as captured* (wall time as written — explicitly **not** UTC-instant order; two same-date
   thoughts written under different offsets order by their stored strings), tie-broken by `id`.
5. Groups into `DayGroup`s by date, days ascending. **Empty days are omitted** — only days with
   thoughts are returned; "nothing on that date" is a CLI presentation concern.

Pure and deterministic in `(thoughts, window)`; no formatting (the CLI owns `HH:MM` rendering via
`capturedTime`).

### `src/kinds.ts` — `thought` gains the invariant

`requiredFacets: new Set([VISUAL_IDENTITY, CAPTURED])`, `invariants: [requireValidVisualIdentity,
requireValidCaptured]`.

### `src/api.ts` — `capture` stamps time

- New **required** field in the input object: `capture({ title, body?, tags?, at })`. `at` is an
  ISO-8601-with-offset string supplied by the caller (the CLI derives it from the injected clock);
  `Mindful` never reads a wall clock.
- `capture` attaches `facets[CAPTURED] = CapturedSchema.parse({ at })` alongside `visualIdentity`,
  and sets `metadata.created = capturedDate(at)` as a **derived coarse projection** — never a
  competing source of truth. `metadata.updated` is left untouched this slice.
- Validation of `at` happens **before** the single `corpus.add`, so it is part of the same atomic
  capture path as identity and tags: a bad `at` (or a throwing tag) persists nothing.

### `src/cli.ts` — clock injection + `journal` command

- New signature: `runCli(argv, mindful, root, env, now, out, err): number` (`now` between `env` and
  the sinks). `now` is an ISO-with-offset string — the captured instant for `add` and the source of
  "today" for `journal` (`capturedDate(now)`).
- `cmdAdd` passes `at: now` into `capture`, and prints `added <id> (<date>)` (date = `capturedDate(now)`)
  then the sprite.
- New top-level `journal` command (§5) with `JOURNAL_USAGE`; top-level `USAGE` gains a `journal` line.

### `src/bin.ts` — inject the clock

Compute `const now = localIso(new Date())` and pass it into `runCli(..., root, process.env, now,
out, err)`.

### `index.ts` — barrel

Add from `./captured.js`: `CAPTURED`, `CapturedSchema`, `type Captured`, `capturedOf`,
`requireValidCaptured`, `capturedDate`, `capturedTime`, `localIso`. Add from `./journal.js`:
`journalView`, `JournalDateSchema`, `type JournalEntry`, `type DayGroup`, `type DateWindow`.

## 4. The `captured` facet

```yaml
captured:
  at: "2026-06-24T21:02:11-04:00"
```

- **Shape:** `{ at: string }`, strict. `at` validates as `z.string().datetime({ offset: true })`:
  an explicit offset is **required** (a bare `Z` counts — it is an explicit ISO offset), a naive
  offset-less datetime and a date-only string are rejected. Fractional seconds are accepted;
  `capturedTime` returns the first `HH:MM` and ignores seconds/fractions.
- **CLI-generated values** (`localIso`) use a local `±HH:MM` offset; stored values from any source
  may use `Z`. Either way, `capturedDate`/`capturedTime` read the date/time **embedded in the
  string**, so the journal reflects the wall clock at capture, not the reader's timezone.
- **Required + intrinsic:** every thought carries it, like `visualIdentity`. The journal projection
  therefore never handles a "timeless" thought.

## 5. CLI surface

Top-level `USAGE` gains: `journal [<date>] | journal --since <date> --until <date>`.
A dedicated `JOURNAL_USAGE` backs the command's errors.

| Invocation | Window | stdout |
|------------|--------|--------|
| `journal` | today: `since = until = capturedDate(now)` | day groups, or empty message |
| `journal <date>` | single day `[date, date]` | day group, or empty message |
| `journal --since <a> --until <b>` | range `[a, b]` | day groups, or empty message |

### Argument rules (all via `JournalDateSchema`; errors → exit 2 with `JOURNAL_USAGE`)

- Dates must be valid `YYYY-MM-DD`; a malformed date → usage error.
- `--since` and `--until` are **all-or-nothing**: either alone → usage error.
- A duplicate `--since` or `--until` → usage error (existing `parseFlags` single-value token scan).
- A positional `<date>` combined with `--since`/`--until` → usage error.
- `since > until` → usage error at the CLI (exit 2, `JOURNAL_USAGE`). `journalView` **independently**
  enforces `since <= until` as a fail-early `ValidationError` (each layer self-correct).

### Output format (exact)

No sprites — a compact day-list, like `list`; `show <ref>` remains the detail/sprite path. Each day
is a `YYYY-MM-DD` header, then one indented entry line `  <HH:MM>  <id>  <title>` per thought
(`HH:MM` from `capturedTime(at)`; full `thought:<uid>` id for copy-paste into `show`). Day groups are
separated by a single blank line. One trailing newline (sink contract).

```
2026-06-24
  09:14  thought:0a3f…  morning idea
  21:02  thought:b9e1…  evening note

2026-06-25
  08:30  thought:7c12…  next-day note
```

**Empty window** (projection returns `[]`) is a friendly message to **stdout**, exit 0 (not silence
like `list`): `no thoughts on <date>` for a single day, `no thoughts from <since> to <until>` for a
range.

## 6. Data flow

- **Capture:** `bin.ts` reads the wall clock once (`localIso(new Date())`) → `runCli` `now` →
  `cmdAdd` → `capture({ …, at: now })` → `captured` facet + `metadata.created` mirror, one atomic
  write. `Mindful` never touches a clock.
- **Read:** `cmdJournal` resolves the `DateWindow` from args (defaulting to `capturedDate(now)`),
  calls `journalView(mindful.allThoughts(), window)`, and formats day groups via `capturedTime`.
  Pure from `allThoughts()` onward.

## 7. Error handling (fail-early, no silent fallback)

- **Malformed `at` at capture** → `ValidationError` from `CapturedSchema.parse`, before any write →
  nothing persists (same atomic path as identity/tags). Surfaces as exit 1 in the CLI.
- **Missing/malformed `captured` on read** → `FacetError` via `requireValidCaptured` during
  validation (exactly like `visualIdentity`).
- **Bad `journal` arguments** (malformed date, lone `--since`/`--until`, duplicate flag, positional +
  flags, `since > until`) → `CliUsageError` → exit 2 with `JOURNAL_USAGE`.
- **`journalView` self-protection** — malformed bound or `since > until` → `ValidationError`
  (defense in depth for any non-CLI caller).
- **Empty window** is **not** an error — friendly stdout message, exit 0.

## 8. Testing

Unit-tested against temp dirs (`mkdtempSync` + direct `Mindful`); no subprocess spawning. Injected
`now`/`at` make every case deterministic regardless of the runner's timezone. `bin.ts` stays a thin
wrapper (the `localIso` logic it calls is tested directly in `captured.test.ts`).

### `tests/captured.test.ts`
- `CapturedSchema` accepts `…-04:00` and `…Z`; rejects date-only (`2026-06-24`), naive
  (`2026-06-24T21:02:11`), and garbage.
- `capturedDate` returns the stored date for both offset forms; `capturedTime` returns `HH:MM`,
  ignoring seconds/fractions.
- `capturedOf` returns the facet and throws `FacetError` on missing/malformed; `requireValidCaptured`
  passes a valid node and throws on a missing facet.
- `localIso(fixedDate)` round-trips: its output parses through `CapturedSchema`, and
  `capturedDate`/`capturedTime` read back consistent parts.

### `tests/journal.test.ts`
- Window filtering: thoughts inside `[since, until]` kept, outside dropped; single-day `since == until`.
- Ascending **stored-local** order with `id` tie-break.
- **Wall-time semantics:** two same-date thoughts whose `at` carry different offsets sort by the
  stored string, **not** by absolute UTC instant (explicit assertion).
- Non-`THOUGHT` nodes passed in are filtered out (no throw).
- Empty days omitted from the result.
- Malformed bound → throws; `since > until` → throws.

### `tests/cli.test.ts` (migrate `run` helpers to the 7-arg `now` form)
- `add` writes the `captured` facet and prints `added <id> (<date>)` with the date from injected `now`.
- `journal` with no args lists **today** (uses `now`); `journal <date>` lists that single day;
  `journal --since <a> --until <b>` lists the range with multiple day groups (blank-line separated).
- Exact `HH:MM` lines come from the captured offset, **not** the runner's TZ (capture with an `at`
  whose wall clock is known, assert the rendered time).
- Errors → exit 2 with `JOURNAL_USAGE`: malformed date, `--since` alone, `--until` alone, duplicate
  `--since`, positional + `--since`/`--until`, `since > until`.
- Empty window → friendly stdout message, exit 0 (single-day and range wording).
- `show <ref>` still renders the sprite (detail path unaffected).

### `tests/api` + `tests/profile.test.ts`
- `capture` requires `at`, writes `captured`, sets `metadata.created = capturedDate(at)`, leaves
  `metadata.updated` untouched.
- **Atomic capture:** `capture` with a **bad `at`** but an otherwise-valid tag target persists
  nothing (proves `captured` validation joins identity + tags on the single atomic path).
- `profile.test.ts`'s valid-thought fixture is updated to attach **both** `visualIdentity` and
  `captured`.

### Gate (unchanged)
`rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`

## 9. Out of scope / deferred

- Relative date keywords (`yesterday`, `today` literal, `--days N`), intra-day sub-views, and
  sampling granularity (the user's "later").
- The SP1 named-`journal` *kind* CLI (create/append/reorder/remove); mindmap CLI; similarity commands.
- Editing or backdating the capture time; `metadata.updated` maintenance on `edit`.
- The richer v5 activity/interaction model (`interactionCount`, `lastInteractionAt`,
  `connectedness`, momentum/heat).
- Sprites inside the journal list; non-ANSI encoders; animation.
- The long-standing deferred SP1 duplicate-container-collision test.

## 10. Decisions log

1. **Journal model** — a derived **date-windowed view** over thoughts, not a container node; "journal"
   is a UX representation of a set of thoughts (same conceptual family as "mindmap"). Distinct from
   the SP1 `journal` *kind*, which is untouched.
2. **Time resolution** — a **precise instant** in a new facet (not the kernel's day-only
   `metadata.created`), so same-day thoughts order by true write time.
3. **`captured` is a required intrinsic facet** — every thought is located in time, like
   `visualIdentity`; clean break (pre-existing thoughts without it fail validation on read), accepted
   pre-release/single-user.
4. **`at` shape** — `z.string().datetime({ offset: true })`: explicit offset required (`Z` allowed),
   naive/date-only rejected, fractional seconds allowed.
5. **`at` in the input object** — `capture({ title, body, tags, at })`, `at` required; the clock is
   injected, never read inside `Mindful`.
6. **`runCli(argv, mindful, root, env, now, out, err)`** — `now` injected between `env` and sinks;
   tests deterministic.
7. **`metadata.created` mirror** — set to `capturedDate(at)` as a derived coarse projection, **never**
   the source of truth; `metadata.updated` untouched this slice.
8. **Centralized datetime contract** — `capturedDate`/`capturedTime` validate through `CapturedSchema`
   first; CLI/journal never slice a raw string, so no second timestamp semantics grows.
9. **Stored-local sort** — `journalView` orders by the `at` string as captured (wall time), not UTC
   instant; tie-break by `id`.
10. **Journal is a pure module, not a `Mindful` method** — same boundary as `encode.ts`; the CLI
    composes `journalView(mindful.allThoughts(), window)`.
11. **`journalView` filters `kind === THOUGHT` internally** and rejects bad windows / `since > until`
    fail-early (defense in depth).
12. **Empty window is presentation** — projection omits empty days; the CLI prints a friendly message,
    exit 0.
13. **CLI date contract** — `YYYY-MM-DD` only (no relative keywords this slice); `--since`/`--until`
    all-or-nothing; `since > until` is a usage error (exit 2) at the CLI and a `ValidationError` in
    `journalView`.
