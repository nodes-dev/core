# Mindful v6 — SP6: Scheme Picker + Active-Scheme Storage (Design)

**Status:** approved (brainstorming) — ready for planning
**Date:** 2026-06-24
**Repo:** `~/d/mindful/v6` (TS only, no kernel changes)
**Specs/plans home:** `~/d/nodes/docs/{specs,plans}/`
**Builds on:** SP2 (visual identity + `Colorscheme`/`resolve`), SP3 (sprite), SP4 (ANSI encoder), SP5 (CLI shell)

## 1. Overview

SP5 shipped a runnable `mindful` CLI, but every sprite renders with the single built-in
`defaultColorscheme` — there is nothing to pick and no place to record a choice. SP6 closes that
gap and, in doing so, settles the storage decision deferred since SP2: **where the active-scheme
choice physically lives.**

SP6 adds three things that do not exist today:

1. A **catalog** of more than one built-in colorscheme (6 curated palettes).
2. A **persisted active-scheme choice**, written to a config file at the data-dir root.
3. **CLI surface** to drive it (`scheme list` / `scheme set` / `scheme show`), plus threading the
   resolved active scheme into `add`/`show` so rendered rasters reflect the user's choice.

### Scope (locked)

- **In:** selecting among built-in schemes; persisting the choice; an env override for one-off use.
- **Out (deferred):** user-authored / loaded custom schemes (no scheme-authoring surface, no user
  palette files); mindmap/journal rendering; animation; non-ANSI encoders.

### Standing boundary (still binding, honored here)

Consumers are pure consumers of `VisualIdentity` / `palette()` / `sprite()` output plus the chosen
scheme. SP6 **never mutates a thought's stored identity**, and **never persists the scheme
implicitly** — `config.yaml` is written *only* when the user explicitly runs `scheme set`. All read
paths are pure. Active-scheme selection is **app configuration** and lives beside the CLI, not
inside `Mindful` (which stays thought/raster-domain).

## 2. Current state (verified)

- `src/color.ts` — `interface Colorscheme { name: string; colors: string[] }`; one built-in
  `defaultColorscheme` (`name: "chiptune-16"`, the 16-color PICO-8 palette); `resolve(identity,
  scheme = defaultColorscheme): string[]`.
- `src/api.ts` — `Mindful.sprite(id, scheme = defaultColorscheme): Sprite` and
  `palette(id, scheme = defaultColorscheme): string[]` already accept an optional scheme. `Mindful`
  holds its corpus at `corpus.store.root` (not surfaced as a first-class property).
- `src/cli.ts` — `runCli(argv, mindful, out, err): number`; `add`/`show` call `mindful.sprite(id)`
  with **no** scheme, so everything renders default. Error model: `CliUsageError` (exit 2),
  `CliError` (exit 1), `NodesError` (exit 1), success 0. Sinks receive complete newline-terminated
  strings; commands with no output make no sink call.
- `src/bin.ts` — `root = resolveDataDir(process.env)`, `mkdirSync(root, {recursive})`,
  `new Mindful(root)`, `runCli(process.argv.slice(2), mindful, out, err)`.
- `index.ts` already exports `type Colorscheme`, `defaultColorscheme`, `resolve` (line 16).
- `yaml` is already a direct runtime dependency (added in SP5 for packed installs).

## 3. Module layout

Three concerns, two new modules + edits to `cli.ts`/`bin.ts`/`index.ts`. Dependency direction is
one-way (`schemes → color`, `config → schemes`, `cli → {config, schemes}`); no cycles.

### `src/schemes.ts` — the catalog

```ts
import { type Colorscheme, defaultColorscheme } from "./color.js";

// derived from the actual default object — no name drift
export const DEFAULT_SCHEME_NAME = defaultColorscheme.name;

// catalog order, default first; the 5 new palettes are defined here
// registry: Record<string, Colorscheme> keyed by scheme name

export function schemeNames(): string[];      // catalog order, default first
export function getScheme(name: string): Colorscheme;  // throws on unknown; returns a DEFENSIVE COPY
```

- The catalog includes `defaultColorscheme` under its own name plus 5 new palettes (§4).
- `getScheme(name)` returns `{ name: s.name, colors: [...s.colors] }` so callers cannot mutate the
  catalog through the returned object. Unknown name throws (fail-early); the thrown error is a plain
  `Error` here — callers (`config.ts`, `cli.ts`) translate it to the appropriate typed error.

### `src/config.ts` — persistence + active-scheme resolution

```ts
export interface MindfulConfig {
  scheme?: string;
}

export class ConfigError extends Error {}

export function readConfig(root: string): MindfulConfig;
export function writeConfig(root: string, config: MindfulConfig): void;
export function resolveActiveScheme(
  root: string,
  env: NodeJS.ProcessEnv,
): { name: string; scheme: Colorscheme; source: SchemeSource };

type SchemeSource = "env" | "config" | "default";
```

- Config file path: `<root>/config.yaml`.
- `readConfig`: missing file → `{}`; empty file → `{}`; otherwise parse YAML and **validate shape**.
  Reject (→ `ConfigError`): malformed YAML, top-level array, top-level scalar, unknown keys, or a
  non-string `scheme`. The accepted schema is intentionally tiny: `{ scheme?: string }`.
- `writeConfig`: serializes exactly the schema fields present via `yaml.stringify`. Called **only**
  by `scheme set`. `writeConfig(root, {})` deterministically writes an empty-mapping document
  (`{}`) with no `scheme` key.
- `resolveActiveScheme`: applies precedence **`MINDFUL_SCHEME` (non-empty) > `config.yaml` >
  built-in default**, resolves the chosen name through `getScheme`, and reports the winning
  `source`. An unknown name from `config.yaml` or `MINDFUL_SCHEME` → `ConfigError` (message names
  the source). `ConfigError` is owned here so `config.ts` has no dependency on the CLI.

### `src/cli.ts` — wiring

- New signature: `runCli(argv, mindful, root, env, out, err): number` (`root` before `env`:
  "this app instance plus its app environment"). The positional form is retained for this slice;
  an object form is deferred until a future SP adds more injected services.
- `add` / `show` call `resolveActiveScheme(root, env)` once and pass `.scheme` into
  `mindful.sprite(id, scheme)`.
- New top-level `scheme` command with a `list` / `set` / `show` sub-switch (§5).
- `runCli`'s catch chain adds `ConfigError` → `error: <message>` / exit 1 (alongside `NodesError`
  and `CliError`).

### `src/bin.ts` — passthrough

Pass the already-computed `root` and `process.env` into `runCli`:
`runCli(process.argv.slice(2), mindful, root, process.env, out, err)`.

### `index.ts` — barrel

Add: `schemeNames`, `getScheme`, `DEFAULT_SCHEME_NAME` (from `./schemes.js`) and `readConfig`,
`writeConfig`, `resolveActiveScheme`, `ConfigError`, `type MindfulConfig` (from `./config.js`).
`Colorscheme` is already exported.

## 4. The catalog (6 schemes)

Catalog order (default first):

| name | size | character |
|------|------|-----------|
| `chiptune-16` | 16 | existing default (PICO-8) — unchanged |
| `gameboy` | 4 | DMG olive-green ramp |
| `dawnbringer-16` | 16 | DB16 classic |
| `monochrome` | 8 | grayscale ramp (high-contrast vs default — used as the rendering-contrast probe in tests) |
| `nord` | 16 | Nord palette |
| `solarized` | 16 | Solarized (dark base) |

The implementer authors the actual hex values. Every palette must be non-empty and every entry must
match `#rrggbb`. `resolve` is scheme-size independent (`index % length`), so a 4-entry `gameboy`
works without special-casing.

## 5. CLI surface

Top-level `USAGE` gains a line: `scheme <list|set|show>`. A dedicated `SCHEME_USAGE` backs the
sub-switch.

| Invocation | Behavior | stdout | Errors |
|------------|----------|--------|--------|
| `scheme list` | `resolveActiveScheme(root, env)` for the active name, then list `schemeNames()` in catalog order | one line per scheme: `<name>` + parenthetical tags from {`active`, `default`} | unknown active (bad env/config) → exit 1 |
| `scheme set <name>` | `getScheme(name)` to validate, then `writeConfig(root, { scheme: name })` | `configured scheme: <name>` (+ override note, see below) | unknown name → exit 1, **no file written** |
| `scheme show` | `resolveActiveScheme(root, env)` | `<name>  (source: <label>)` | unknown active → exit 1 |
| `scheme` (bare) / unknown sub | usage error | — | `CliUsageError` → exit 2, `SCHEME_USAGE` to stderr |

### Output formats (exact)

- **`scheme list`** — each line is `<name>` followed, when applicable, by a single parenthetical of
  comma-joined tags in fixed order `active`, `default`. With no config (default active):

  ```
  chiptune-16  (active, default)
  gameboy
  dawnbringer-16
  monochrome
  nord
  solarized
  ```

  After `scheme set gameboy` (no env override): `chiptune-16  (default)`, `gameboy  (active)`, rest
  bare. The two-space separator between name and parenthetical matches the `list`/`search` column
  style already used in the CLI.

- **`scheme set <name>`** — prints `configured scheme: <name>` (wording is "configured", not
  "active", because writing config does not necessarily make the scheme active under an env
  override). When `MINDFUL_SCHEME` is present and non-empty, append a second line:

  ```
  configured scheme: gameboy
  note: MINDFUL_SCHEME=<name> currently overrides config.yaml
  ```

- **`scheme show`** — `<name>  (source: <label>)` where the label maps the resolved source:
  `env` → `MINDFUL_SCHEME`, `config` → `config.yaml`, `default` → `default`. e.g.
  `gameboy  (source: config.yaml)`.

All command output is a single complete newline-terminated string per the SP5 sink contract.

## 6. Data flow: rendering with the active scheme

`add` and `show` each call `resolveActiveScheme(root, env)` exactly once and pass the resolved
`.scheme` into `mindful.sprite(id, scheme)`. The thought's stored visual identity is read, never
written; the scheme only colors the raster at render time. A thought captured under one scheme and
shown under another therefore renders differently with no change to its stored data.

## 7. Error handling (fail-early, no silent fallback)

- **Unknown scheme name** — from `set <name>`, `config.yaml`, or `MINDFUL_SCHEME` — is exit **1**,
  not a usage error. Rationale: like a bad `<ref>` it is valid syntax with no match, not a malformed
  invocation. `set`'s validation and `scheme show` raise `CliError`; the config/env resolution path
  raises `ConfigError`; all are caught into `error: <message>` / exit 1.
- **Malformed or ill-shaped `config.yaml`** → `ConfigError` → exit 1. A hand-corrupted config
  therefore also fails `add`/`show` (rendering cannot pick a palette). This is intended: configs
  written by `scheme set` are always valid, so only manual corruption triggers it, and failing
  loudly beats silently reverting to default.
- **`scheme list` depends on active resolution**, so it can fail with exit 1 when env/config names
  an unknown scheme — consistent with fail-early.
- **Bare `scheme` / unknown subcommand** → `CliUsageError` → exit 2.

## 8. Testing

Unit-tested against temp dirs (existing pattern: `mkdtempSync` + direct `Mindful`), no subprocess
spawning. `bin.ts` stays a thin untested wrapper, covered by one manual smoke test.

### `tests/schemes.test.ts`
- `DEFAULT_SCHEME_NAME === defaultColorscheme.name`.
- `schemeNames()` returns all 6 in catalog order, default first.
- `getScheme(known)` returns the right palette; mutating the returned `.colors` does **not** affect
  a second `getScheme` call (defensive-copy proof).
- `getScheme(unknown)` throws.
- Every catalog palette is non-empty and all entries match `#rrggbb`.

### `tests/config.test.ts`
- `readConfig`: missing file → `{}`; empty file → `{}`; `scheme: gameboy` → `{ scheme: "gameboy" }`.
- `readConfig` rejects with `ConfigError`: malformed YAML, top-level array, top-level scalar,
  unknown key, non-string `scheme`.
- `writeConfig` then `readConfig` round-trips `{ scheme: "gameboy" }`.
- `writeConfig(root, {})` writes a deterministic empty-mapping document with no `scheme` key.
- `resolveActiveScheme` precedence: env beats config beats default; correct `source`
  (`env`/`config`/`default`) in each case.
- Unknown name via config → `ConfigError`; via env → `ConfigError`.

### `tests/cli.test.ts` (additions)
- `scheme list` with no config: assert the **exact** six lines (locks catalog order and tag
  formatting, including `chiptune-16  (active, default)`).
- After `scheme set gameboy`: `scheme list` shows `gameboy  (active)` and `chiptune-16  (default)`.
- `scheme set gameboy` writes `config.yaml` and prints `configured scheme: gameboy`; with
  `MINDFUL_SCHEME` set, also prints the override note.
- `scheme set bogus` → exit 1, `error: …`, and `config.yaml` **does not exist** afterward.
- `MINDFUL_SCHEME=<unknown>` + `scheme list` → exit 1 (active resolution path covered).
- `scheme show` reports the right name+source label under each of the three precedence cases.
- `scheme` bare and `scheme bogus` → exit 2 with `SCHEME_USAGE`.
- **Active scheme reaches the raster:** `show <ref>` output **differs** when `MINDFUL_SCHEME` names
  a visibly different built-in (`monochrome` vs default). Assert "output differs", not exact ANSI.
- Malformed `config.yaml` makes `show <ref>` exit 1.

### Gate (unchanged from SP5)
`rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`

## 9. Out of scope / deferred

- User-authored or file-loaded custom schemes (scheme-authoring + validation surface, user palette
  files).
- Mindmap/journal CLI commands, similarity commands, REPL/full-screen TUI.
- Animation; SVG/PNG encoders.
- The long-standing deferred SP1 duplicate-container-collision test.
- Object-form `runCli` signature (revisit if a future SP injects more app services).

## 10. Decisions log

1. **Scope** — select among built-in schemes only; custom-scheme authoring deferred.
2. **Storage** — `<root>/config.yaml` (YAML, matching the corpus frontmatter style; `yaml` already a
   dep); written only on `scheme set`; reads pure.
3. **Precedence** — `MINDFUL_SCHEME` (non-empty) > `config.yaml` > built-in default; unknown name
   fails early in any path.
4. **Commands** — `scheme list` / `scheme set <name>` / `scheme show`; no `clear` (revert by setting
   the default name).
5. **Catalog** — 6 schemes: `chiptune-16` (default), `gameboy`, `dawnbringer-16`, `monochrome`,
   `nord`, `solarized`.
6. **Boundary** — scheme config lives in `config.ts` beside the CLI, not in `Mindful`; identity never
   mutated; persistence never implicit.
7. **`DEFAULT_SCHEME_NAME = defaultColorscheme.name`** — derived, no drift.
8. **`ConfigError` owned by `config.ts`** — no `config → cli` dependency; `runCli` catches it → exit 1.
9. **Strict config shape validation** — `{ scheme?: string }`; non-object/array/unknown-key/non-string
   → `ConfigError`.
10. **`getScheme` returns a defensive copy** — catalog immutable through the accessor.
11. **`runCli(argv, mindful, root, env, out, err)`** — positional, `root` before `env`.
12. **`scheme set` wording** — `configured scheme: <name>` (+ override note when `MINDFUL_SCHEME`
    set), not "active scheme", since config write ≠ active under env shadow.
13. **Unknown scheme is exit 1**, not usage (exit 2); malformed config is exit 1 and also fails
    `add`/`show`.
