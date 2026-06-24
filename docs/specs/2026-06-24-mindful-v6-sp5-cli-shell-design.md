# Mindful v6 — SP5: CLI Shell (`mindful` command)

**Status:** Design (approved in brainstorming; pending written-spec review)
**Date:** 2026-06-24
**Repo:** `~/d/mindful/v6` (TypeScript only — **no kernel changes**)
**Builds on:** SP1 (`2026-06-23-mindful-v6-sp1-abstraction-design.md`), SP2
(`2026-06-24-mindful-v6-sp2-visual-identity-design.md`), SP3
(`2026-06-24-mindful-v6-sp3-renderer-design.md`), SP4
(`2026-06-24-mindful-v6-sp4-ansi-encoder-design.md`)

**Goal:** The library→app jump. A one-shot subcommand CLI — `mindful add|show|list|search|edit|delete|tag`
— that composes the existing headless `Mindful` API with SP4's `spriteToAnsi` so a person can actually
capture thoughts and *see* their sprites in a terminal. This is the first real consumer of the entire
`uid → VisualIdentity → palette() → sprite() → spriteToAnsi()` pipeline.

**Architecture:** A testable core plus a thin executable wrapper. `src/cli.ts` exports
`runCli(argv, mindful, out, err): number` — it parses arguments, dispatches subcommands, formats output
through injected `out`/`err` sinks, and **returns an exit code**. `src/bin.ts` is a thin executable
(shebang → resolve data dir → `mkdir` → `new Mindful(root)` → `process.exit(runCli(...))`) that is pure
wiring and is not unit-tested. The package gains a real `tsc` build to `dist/` (mirroring how
`@nodes/kernel` already ships) so `bin` can point at emitted JavaScript.

**Tech stack:** TypeScript (Node ≥20, ESM, `.js` import extensions, biome, vitest). Argument parsing via
the built-in `node:util` `parseArgs`. **No new runtime or dev dependencies** — `typescript` (already a
devDependency) provides the build; everything else is Node built-ins (`node:util`, `node:fs`,
`node:path`, `node:os`) and existing mindful modules.

---

## Global Constraints

- **No kernel changes.** All work is in `~/d/mindful/v6`. The dependency stays one-way
  (`mindful → @nodes/kernel`).
- **No new dependencies (runtime or dev).** `parseArgs` is built into `node:util`; the build uses the
  already-present `typescript`. No CLI framework (commander/yargs), no TS runner.
- **Testable core, thin wrapper.** All command logic is in `runCli(argv, mindful, out, err): number`,
  driven in tests against a temp-dir `Mindful` with array buffers — **no subprocess spawning, no
  dependence on the build output in tests**. `bin.ts` is wiring only.
- **Scheme boundary holds.** `show`/`add` render via `defaultColorscheme` only. The CLI introduces **no
  scheme state** — no `--scheme` flag, no config file, no persistence. The scheme picker + active-scheme
  storage remains a separate, deferred sub-project. The standing rule is honored by construction:
  consumers are pure consumers of `sprite()` output; identity is never mutated, scheme is never
  implicitly persisted.
- **Strict, fail-early.** Usage problems and domain failures both abort cleanly with distinct exit codes
  (see §5). No silent fallbacks; no partial mutation (the `Mindful` API already writes atomically).
- **Thought lifecycle only.** This slice exposes thought CRUD + search + tag. Mindmap and journal
  commands, similarity, the interactive REPL/TUI, and the scheme UI are deferred (see §8).

---

## 1. Context & Motivation

SP1–SP4 built a complete but entirely headless pipeline: `Mindful` (capture/edit/tag/search thoughts,
mindmaps, journals), a deterministic `VisualIdentity` per thought, a swappable colorscheme + `palette()`,
a pure `sprite()` renderer, and `spriteToAnsi()`. Every piece is pure and importable, but nothing yet
turns it into something a user can *run*. SP5 is the library→app jump: the first executable that composes
these into a usable tool, and the first real consumer of `spriteToAnsi`.

The original SP4 bundle ("renderer + CLI/TUI shell") is fully decomposed. SP5 is the **one-shot
subcommand CLI** only — the smallest app jump that exercises the whole pipeline end-to-end. The
interactive REPL and full-screen TUI are deliberately *not* here: they need an input loop and (for the
TUI) a rendering framework, and they layer naturally on top of this command core later.

---

## 2. Scope — Commands

Seven thought-lifecycle subcommands. Each maps to an existing `Mindful` method:

| Command | Args | `Mindful` call | Success output |
|---|---|---|---|
| `add` | `<title> [--body <text>] [--tag <name>]…` | `capture({title, body, tags})` | `added <id>` + sprite |
| `show` | `<ref>` | `get(id)` + `sprite(id)` | sprite + stable fields (§6) |
| `list` | *(none)* | `allThoughts()` | one `<id>  <title>` line per thought, id-sorted |
| `search` | `<query> [--limit <n>]` | `search(query, limit)` | one `<id>  <title>  (<score>)` line per hit |
| `edit` | `<ref> [--title <t>] [--body <b>]` | `edit(id, patch)` | `updated <id>` |
| `delete` | `<ref>` | `delete(id)` | `deleted <id>` |
| `tag` | `<ref> <name>` | `tag(id, name)` | `tagged <id> #<name>` |

The CLI verb for capture is **`add`**; the underlying API method `Mindful.capture()` is unchanged.

**`add --tag` semantics (fail-early, inherited from SP1):** tags resolve against *existing* thoughts
only — `mindful add "A" --tag "B"` **fails** (exit 1) if no thought titled `B` already exists. The CLI
does **not** auto-create tag targets. This matches `Mindful.capture`/`resolveTag` behavior (a genuine
miss throws `RefError`); the thought is not persisted if a tag fails.

**`parseArgs` flag configuration.** Flags are parsed per subcommand with `node:util` `parseArgs`
(`allowPositionals: true`). Only `--tag` repeats:

- `tag` → `{ type: "string", multiple: true }` — collects every `--tag` into a `string[]` (the `tags`
  array passed to `capture`).
- `body`, `title`, `limit` → `{ type: "string" }` (single-valued).

**Duplicate single-valued flags are usage errors, not last-wins.** A repeated `--body`, `--title`, or
`--limit` → exit 2. `parseArgs` collapses a repeated single-valued flag to a single string (silently
keeping the last), so the CLI must pass `{ tokens: true }` and scan the returned tokens to detect a
single-valued option appearing more than once, rejecting it via the usage path. (`--tag` is exempt — it
is explicitly `multiple`.)

---

## 3. ID Resolution — unique-prefix `<ref>`

Thought ids are `thought:<uid>` where `uid` is a 32-character hex string, too long to retype. Commands
taking a `<ref>` (`show`, `edit`, `delete`, `tag`) accept a **unique prefix**:

A thought *matches* `ref` when any of these hold against its full id:
- `id === ref`, or
- `id.startsWith(ref)`, or
- `id.startsWith("thought:" + ref)` (so a bare uid-prefix like `9f3a` works).

`resolveId(mindful, ref): string` scans `allThoughts()` and:
- **exactly one** match → returns that id,
- **zero** matches → throws a domain error (`no thought matching <ref>`) → exit 1,
- **more than one** match → throws a domain error (`ambiguous ref <ref>: matches N thoughts`) → exit 1.

This is a CLI-level convenience over the API; it never mutates anything. Resolution by *title* is
deferred (§8).

---

## 4. Data Location — `resolveDataDir(env)`

`resolveDataDir(env: NodeJS.ProcessEnv): string` is pure and resolves the corpus root in order:

1. `MINDFUL_HOME`
2. `$XDG_DATA_HOME/mindful`
3. `$HOME/.local/share/mindful`

**Empty-string env vars are treated as absent**, not as usable paths — an empty `MINDFUL_HOME`,
`XDG_DATA_HOME`, or `HOME` is skipped as if unset (prevents `""` resolving to the process cwd). If none
yields a path (no override, no `XDG_DATA_HOME`, no `HOME`), `resolveDataDir` **throws** (fail-early) — it
never falls back to cwd.

`bin.ts` calls `resolveDataDir(process.env)`, then `mkdirSync(root, { recursive: true })` before
constructing `Mindful(root)`. Tests set `MINDFUL_HOME` to a temp dir (or pass a temp-dir `Mindful`
directly to `runCli`).

---

## 5. Error Handling & Exit Codes

`runCli` separates **usage errors** from **domain errors** with a tiny internal marker class:

```ts
class CliUsageError extends Error {}   // module-private to cli.ts
```

Dispatch is wrapped in try/catch with three outcomes:

- **Usage error → exit `2`.** Unknown/missing subcommand, missing required positional, an unknown or
  malformed flag, an invalid `--limit` (non-integer / `< 1`), or `edit` with neither `--title` nor
  `--body`. These throw (or are caught as) `CliUsageError`; `runCli` writes a usage message to `err` and
  returns `2`. **`parseArgs` throws its own errors** for unknown options / bad option values — these are
  caught and funneled into the usage path (exit 2).
- **Domain error → exit `1`.** Any `NodesError` — the kernel's base error class, which **all** kernel
  errors extend (`RefError`, `ValidationError`, `FacetError`, `CollisionError`, **and `InvariantError`**,
  the last able to surface from validation paths over malformed on-disk data) — plus CLI domain failures
  (no-match or ambiguous `<ref>` from §3). The catch tests `instanceof NodesError` (not the individual
  subclasses) so a new kernel error subtype is covered automatically. `runCli` writes `error: <message>`
  to `err` and returns `1`.
- **Success → exit `0`.** Output written to `out`.

No partial state on a domain error: the `Mindful` API persists atomically (a thought whose tag fails is
never written), and the CLI performs no multi-step mutations.

---

## 6. Output Formats

All commands write through the injected `out` sink. Formats are pinned for scriptability and
deterministic tests.

**`add`** — captures, then prints the new id followed by the sprite (immediate visual feedback):
```
added thought:<uid>
<ansi sprite>
```

**`show <ref>`** — sprite first (visual payoff), then stable labeled fields:
```
<ansi sprite>
id: thought:<uid>
title: <title>
body: <body>
related: []
```
- `body:` prints the thought's body **verbatim** for human readability (may be empty after the colon).
  A multiline body is printed as-is — its newlines flow onto the following lines after `body:`; the body
  is **not** JSON-encoded or escaped. (Field order is still stable: `related:` always follows the body.)
- **`related:`** lists the global-graph neighbors (`Mindful.related(id)`), one `- <id>` bullet per
  neighbor on following lines. **When there are no neighbors, the line is exactly `related: []`** (no
  bullets). This is the chosen empty-collection convention.

**`list`** — every thought, **sorted by id ascending** (matches the kernel's natural path order), one per
line:
```
<id>  <title>
```

**`search <query>`** — hits in the **kernel's order**, which is deterministic: score descending, then id
ascending. The kernel already sorts `SearchHit`s this way (verified in `search.ts`), so the CLI **must
not re-sort** — it iterates `search()`'s result as returned. `SearchHit` carries no title, so each hit
triggers one `get(hit.id)` for display:
```
<id>  <title>  (<score>)
```
An empty result set prints nothing (exit 0).

**`edit` / `delete` / `tag`** — single confirmation lines: `updated <id>`, `deleted <id>`,
`tagged <id> #<name>`.

---

## 7. Public Surface & Files

```text
~/d/mindful/v6/
  src/
    cli.ts            # runCli(argv, mindful, out, err): number; resolveDataDir(env); resolveId(); formatting  (new)
    bin.ts            # #!/usr/bin/env node — thin executable wrapper, not unit-tested                          (new)
    index.ts          # add exports: runCli, resolveDataDir                                                     (modified)
  tests/
    cli.test.ts       # drives runCli against a mkdtemp temp dir; pure resolveDataDir tests                     (new)
  tsconfig.build.json # extends base: noEmit:false, outDir:"dist", rootDir:"src", declaration, include:["src"]  (new)
  package.json        # add build script + full dist package metadata (see below)                               (modified)
  .gitignore          # add dist/                                                                               (modified)
```

**`runCli` signature (the contract later tasks/tests rely on):**
```ts
type Sink = (s: string) => void;
export function runCli(argv: string[], mindful: Mindful, out: Sink, err: Sink): number;
export function resolveDataDir(env: NodeJS.ProcessEnv): string;
```
`argv` is the post-`node bin.ts` argument list (i.e. `process.argv.slice(2)`).

**Sink contract (pinned).** `runCli` calls `out`/`err` with **complete, newline-terminated strings** —
each user-facing result or error message is one call ending in `\n` (a multi-line result is a single
string containing its internal newlines and one trailing `\n`). The sinks are *not* given newline-free
chunks that callers must reassemble. `bin.ts` wires `out = (s) => process.stdout.write(s)` and
`err = (s) => process.stderr.write(s)` — no extra newline added at the wiring layer. **`spriteToAnsi`
itself stays no-trailing-newline** (its SP4 contract is unchanged); the CLI appends the `\n` when it
embeds the sprite in a command's output, so terminal output ends cleanly on its own line. Tests
concatenate the captured sink calls and assert against the joined string (including trailing newlines).

**`package.json` build metadata** — adopt the kernel's full dist-package shape (not just `bin`), so the
package is a coherent dist-package rather than half-source/half-dist:
```jsonc
{
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": { ".": { "types": "./dist/index.d.ts", "default": "./dist/index.js" } },
  "files": ["dist"],
  "bin": { "mindful": "dist/bin.js" },
  "scripts": { "build": "tsc -p tsconfig.build.json", /* test/typecheck/check unchanged */ }
}
```
Tests import mindful modules from `../src/*.js` (source) as today — they do **not** depend on `main` or
the build. The base `tsconfig.json` keeps `noEmit: true` and continues to typecheck `src` + `tests`; only
`tsconfig.build.json` emits, and only `src` → `dist/`. `bin.ts`'s `#!/usr/bin/env node` shebang is the
file's first line; `tsc` preserves it on emit, and `npm` marks the `bin` executable on install.

`@nodes/kernel` is already a built dist-package (`main: dist/index.js`), so the emitted mindful `dist/`
imports it cleanly under plain `node` — no runner needed.

---

## 8. Testing Strategy (`cli.test.ts`)

Mirrors the existing integration-test pattern: `root = mkdtempSync(join(tmpdir(), "mindful-cli-"))` in
`beforeEach`, `rmSync(root, { recursive: true, force: true })` in `afterEach`, `new Mindful(root)`.
Each test calls `runCli(argv, m, out, err)` with `out`/`err` pushing into string arrays, then asserts the
returned exit code and the captured output.

**`runCli` behavior:**
- **Round-trip:** `add "First"` → exit 0, output `added thought:…`; then `list` → exit 0, line contains
  that id + `First`; then `show <id-prefix>` → exit 0, output contains the id, `title: First`, and the
  sprite.
- **`add --tag`:** add a thought `B`, then `add "A" --tag B` → exit 0; and `add "C" --tag nope` (no such
  thought) → exit 1, `err` contains `error:`.
- **Sprite is real ANSI:** `show` output contains the half-block glyph `▀` and an ESC sequence
  (`\x1b[38;2;`), proving the `spriteToAnsi` path runs.
- **`search`:** add two thoughts, search a term in one → exit 0, the matching id appears; an empty query
  result → exit 0, no hit lines.
- **`edit`:** `edit <ref> --body "new"` → exit 0, `updated …`; a subsequent `show` reflects the new body.
  `edit <ref>` with no flags → exit 2 (usage).
- **Multiline body:** `add` then `edit <ref> --body $'a\nb'`; `show` output contains `body:` followed by
  the verbatim two-line body (newline preserved, not escaped).
- **Duplicate single-valued flag:** `add "X" --body one --body two` → exit 2 (usage), not last-wins;
  likewise a repeated `--title`/`--limit`. `add "X" --tag a --tag b` → exit 0 (repeated `--tag` allowed).
- **`delete`:** `delete <ref>` → exit 0; subsequent `show <ref>` → exit 1.
- **`tag`:** `tag <ref> <name>` against an existing target → exit 0, `tagged … #name`; `show` then lists
  it under `related:`.
- **`show` empty related:** a freshly added thought → `show` output contains exactly `related: []`.
- **ID resolution:** a unique prefix resolves (exit 0); a prefix matching ≥2 thoughts → exit 1
  (`ambiguous`); a prefix matching none → exit 1.
- **Usage paths:** unknown command → exit 2; no command → exit 2; unknown flag (`--nope`) → exit 2
  (caught from `parseArgs`); `search --limit abc` → exit 2; `add` with no title → exit 2.

**Pure `resolveDataDir`:**
- `MINDFUL_HOME=/a` wins over everything → `/a`.
- no `MINDFUL_HOME`, `XDG_DATA_HOME=/x` → `/x/mindful`.
- only `HOME=/h` → `/h/.local/share/mindful`.
- **empty strings treated as absent:** `MINDFUL_HOME=""` with `XDG_DATA_HOME=/x` → `/x/mindful`.
- nothing set (or all empty) → **throws**.

---

## 9. Out of Scope / Deferred (SP6+)

- **Mindmap & journal commands** (`createMindmap`/`addThought`/`link`…, `createJournal`/`append`/
  `reorder`…). This slice proves the thought lifecycle + ANSI path first.
- **Similarity commands** (`similar`/`similarText`) — require an embedder; no CLI surface yet.
- **Interactive REPL & full-screen TUI** — input loop / rendering framework; layer on top of this command
  core later.
- **Scheme picker + active-scheme storage** — the deliberate storage point and its UI; SP5 renders with
  `defaultColorscheme` only and persists no scheme state.
- **SVG/PNG encoders and animation** — separate encoder/animation sub-projects.
- **ID resolution by title** — only id / id-prefix resolution now.

---

## 10. Decisions Log

1. **SP5 = the one-shot subcommand CLI only.** REPL, full-screen TUI, scheme UI, mindmap/journal
   commands, and other encoders are each later sub-projects.
2. **Testable core + thin bin wrapper.** `runCli(argv, mindful, out, err): number` holds all logic and is
   tested directly with injected sinks against a temp-dir `Mindful`; `bin.ts` is untested wiring. Rejected:
   subprocess-spawning tests (slow/flaky, couples tests to the build) and an arg-parsing framework (new
   dep; `node:util.parseArgs` suffices).
3. **Seven thought-lifecycle commands:** `add`, `show`, `list`, `search`, `edit`, `delete`, `tag`. CLI
   verb `add` maps to `Mindful.capture()`.
4. **Real `tsc` build to `dist/`, full dist-package metadata.** `main`/`types`/`exports`/`files`/`bin`
   all point at `dist/` (mirroring `@nodes/kernel`); a new `tsconfig.build.json` emits only `src`. The
   base config stays `noEmit` for typechecking. **Zero new dependencies.**
5. **Unique-prefix `<ref>` resolution.** `show`/`edit`/`delete`/`tag` accept a unique id-prefix (incl.
   bare uid-prefix); zero/ambiguous matches are domain errors (exit 1). Title resolution deferred.
6. **Usage vs domain errors are distinct.** Internal `CliUsageError`; usage problems (incl. `parseArgs`
   throws, bad `--limit`, duplicate single-valued flag, `edit` with no flags) → exit 2; domain failures —
   any `NodesError` (the kernel base class all kernel errors extend, incl. `InvariantError`) plus CLI
   domain failures — → `error: <msg>`, exit 1; success → 0. The catch tests `instanceof NodesError`, not
   the leaf subclasses.
7. **Empty env vars treated as absent** in `resolveDataDir`; no fallback to cwd; throws if nothing
   resolvable.
8. **Default scheme only.** `show`/`add` render via `defaultColorscheme`; no scheme flag, config, or
   persistence — the scheme boundary holds by construction.
9. **Pinned, deterministic output.** `list` sorted by id ascending; `search` preserves the kernel's
   score-desc/id-asc order; `show` prints sprite then stable `id:`/`title:`/`body:`/`related:` fields,
   with `related: []` as the explicit empty-collection form.
10. **`add --tag` does not auto-create tags** (SP1 fail-early): an unknown tag target fails the command
    (exit 1) and nothing is persisted.
11. **`--tag` is the only repeatable flag** (`parseArgs` `multiple: true`); `--body`/`--title`/`--limit`
    are single-valued, and repeating one is a usage error (exit 2), not last-wins — detected by scanning
    `parseArgs` tokens (`{ tokens: true }`).
12. **Sink contract:** `out`/`err` receive complete, newline-terminated strings (one call per
    result/error, trailing `\n` included); `spriteToAnsi` stays no-trailing-newline and the CLI appends
    the `\n` when embedding it. `body:` is printed verbatim (multiline bodies flow as-is, not escaped).
13. **No kernel changes; no new runtime or dev dependency.**
