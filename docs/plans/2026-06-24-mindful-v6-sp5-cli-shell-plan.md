# Mindful v6 — SP5: CLI Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `mindful` one-shot subcommand CLI (`add`/`show`/`list`/`search`/`edit`/`delete`/`tag`) — the first runnable app over the headless `Mindful` API and the first consumer of `spriteToAnsi`.

**Architecture (SP5 baseline):** A testable core `runCli(argv, mindful, out, err): number` in `src/cli.ts` holds all parsing, dispatch, formatting, and error handling, writing only through injected sinks and returning an exit code. A thin `src/bin.ts` resolves the data dir, constructs `Mindful`, and calls `runCli`. The package gains a real `tsc` build to `dist/` (mirroring `@nodes/kernel`) so `bin` points at emitted JS.

**Tech Stack:** TypeScript (Node ≥20, ESM, `.js` import extensions), `node:util` `parseArgs` for argument parsing, vitest, biome. No new runtime or dev dependencies.

## Current State Note

This plan has since been implemented and later CLI work expanded it substantially. The historical SP5 baseline below used `runCli(argv, mindful, out, err): number` and seven commands over a live `Mindful` instance. Current `~/d/mindful/v6` uses `runCli(argv, root, env, now, out, err, makeMindful, runEditor?)`, keeps list/show/search paths catalog-backed, passes `now` into `add` so `Mindful.capture` receives `at`, supports editor-driven edits, and includes later commands/features: `scheme`, `journal`, `index`, `mindmap`, `similar`, `search --semantic`, aliases/display refs, config/env scheme resolution, catalog refresh, and semantic index maintenance.

Treat the task snippets below as historical SP5 implementation steps, not as replacement code for the current CLI. When auditing or modifying current code, preserve the root/env/now/factory signature, `CAPTURED` timestamp behavior, catalog-backed reads, partial-refresh error boundary, editor runner seam, and later command set.

## Global Constraints

- **No kernel changes.** All work is in `~/d/mindful/v6`; dependency stays one-way (`mindful → @nodes/kernel`).
- **No new dependencies (runtime or dev).** `parseArgs` is built into `node:util`; the build uses the already-present `typescript`. No CLI framework, no TS runner.
- **All tooling via `rtk`.** `rtk npm test`, `rtk npm run typecheck`, `rtk npm run check`, `rtk npm run build`, `rtk git ...`, `rtk npx @biomejs/biome ...`.
- **Tooling:** use `rtk rg` for searches and read target files directly when validating exact snippets.
- **biome:** tabs, line width 120, organizes/sorts imports (flags duplicate imports from the same module). `check` is read-only; fix diffs with `rtk npx @biomejs/biome check --write <files>`.
- **Testable core, thin wrapper.** All logic in `runCli`; tests drive it directly against a temp-dir `Mindful` with array sinks — **no subprocess spawning, no dependence on build output in tests**. `bin.ts` is untested wiring.
- **Exit-code taxonomy.** Usage problems → exit `2`; any `NodesError` (the kernel base class all kernel errors extend, incl. `InvariantError`) plus CLI domain failures → `error: <msg>` to `err`, exit `1`; success → `0`. The catch tests `instanceof NodesError`, not leaf subclasses. Unexpected (non-usage, non-domain) errors are rethrown (fail-early), not masked as exit 1.
- **Sink contract.** `out`/`err` receive complete, newline-terminated strings (one call per result/error, trailing `\n` included). `spriteToAnsi` stays no-trailing-newline; the CLI appends the `\n` when embedding it. **Commands with no output make no sink call** (no empty `"\n"`).
- **Historical SP5 scheme boundary.** `show`/`add` render via `defaultColorscheme` only (`Mindful.sprite()` default) — no scheme flag, config, or persistence; identity never mutated. Current code has since added scheme config/env resolution and `scheme` commands.
- **`--tag` is the only repeatable flag** (`parseArgs` `multiple: true`); `--body`/`--title`/`--limit` are single-valued, and repeating one is a usage error (exit 2), detected by scanning `parseArgs` tokens (`{ tokens: true }`).
- **Pinned output.** `list` sorted by id ascending; `search` preserves the kernel's order (do **not** re-sort); `show` prints sprite then stable `id:`/`title:`/`body:`/`related:` fields, `body:` verbatim (multiline as-is), `related: []` when empty; `<score>` is raw `String(hit.score)`.
- **`add --tag` does not auto-create tags** — an unknown tag target fails the command (exit 1) and nothing is persisted (SP1 fail-early; `Mindful.capture` writes atomically).

**Spec:** `~/d/nodes/docs/specs/2026-06-24-mindful-v6-sp5-cli-shell-design.md`.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/cli.ts` | `resolveDataDir`, `runCli`, `resolveId`, `parse`/`parseFlags`, command handlers, formatting, error model | 1–3 |
| `src/bin.ts` | Thin executable: shebang, resolve dir, mkdir, construct `Mindful`, exit with `runCli`'s code | 4 |
| `tests/cli.test.ts` | Drives `runCli` against a `mkdtemp` temp dir; pure `resolveDataDir` tests | 1–3 |
| `tsconfig.build.json` | `extends` base: `noEmit:false`, `outDir:"dist"`, `rootDir:"src"`, `include:["src"]` | 4 |
| `package.json` | Add `build` script + full dist metadata (`main`/`types`/`exports`/`files`/`bin`) | 4 |
| `biome.json` | Add `files.ignore: ["dist"]` | 4 |
| `.gitignore` | Add `dist/` | 4 |
| `src/index.ts` | Export `runCli`, `resolveDataDir` | 4 |

Current-code note: the file set still exists, but `src/cli.ts`, `tests/cli.test.ts`, and `src/bin.ts` now include later catalog, scheme, semantic, journal, mindmap, and editor code. Do not collapse them back to the SP5-only shape.

---

## Task 1: `resolveDataDir` + CLI module scaffold

**Files:**
- Create: `~/d/mindful/v6/src/cli.ts`
- Test: `~/d/mindful/v6/tests/cli.test.ts`

**Interfaces:**
- Consumes: nothing (pure function over `NodeJS.ProcessEnv`).
- Produces: `export function resolveDataDir(env: NodeJS.ProcessEnv): string` — resolves the corpus root from `MINDFUL_HOME` ?? `$XDG_DATA_HOME/mindful` ?? `$HOME/.local/share/mindful`, treating empty strings as absent, throwing a plain `Error` if none resolvable. Creates the `src/cli.ts` module that Tasks 2–3 extend.

- [ ] **Step 1: Write the failing test**

Current-code note: this pure `resolveDataDir` surface is still current, but the current test suite also asserts plain `Error` prototype behavior.

Create `~/d/mindful/v6/tests/cli.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { resolveDataDir } from "../src/cli.js";

describe("resolveDataDir", () => {
	it("uses MINDFUL_HOME ahead of everything", () => {
		expect(resolveDataDir({ MINDFUL_HOME: "/a", XDG_DATA_HOME: "/x", HOME: "/h" })).toBe("/a");
	});

	it("falls back to $XDG_DATA_HOME/mindful", () => {
		expect(resolveDataDir({ XDG_DATA_HOME: "/x", HOME: "/h" })).toBe("/x/mindful");
	});

	it("falls back to $HOME/.local/share/mindful", () => {
		expect(resolveDataDir({ HOME: "/h" })).toBe("/h/.local/share/mindful");
	});

	it("treats empty-string env vars as absent", () => {
		expect(resolveDataDir({ MINDFUL_HOME: "", XDG_DATA_HOME: "/x" })).toBe("/x/mindful");
	});

	it("throws when nothing is resolvable", () => {
		expect(() => resolveDataDir({})).toThrow();
		expect(() => resolveDataDir({ MINDFUL_HOME: "", XDG_DATA_HOME: "", HOME: "" })).toThrow();
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npx vitest run tests/cli.test.ts`
Expected: FAIL — cannot resolve `../src/cli.js` (module does not exist).

- [ ] **Step 3: Write the minimal implementation**

Create `~/d/mindful/v6/src/cli.ts`:

```ts
import { join } from "node:path";

/** First non-empty of the candidates, or undefined. Empty strings are treated as absent. */
function firstNonEmpty(...values: (string | undefined)[]): string | undefined {
	for (const v of values) {
		if (v !== undefined && v !== "") return v;
	}
	return undefined;
}

/** Resolve the corpus root: MINDFUL_HOME ?? $XDG_DATA_HOME/mindful ?? $HOME/.local/share/mindful.
 * Empty-string env vars count as absent. Throws (fail-early) if none yields a path — never cwd. */
export function resolveDataDir(env: NodeJS.ProcessEnv): string {
	const home = firstNonEmpty(env.MINDFUL_HOME);
	if (home !== undefined) return home;
	const xdg = firstNonEmpty(env.XDG_DATA_HOME);
	if (xdg !== undefined) return join(xdg, "mindful");
	const userHome = firstNonEmpty(env.HOME);
	if (userHome !== undefined) return join(userHome, ".local", "share", "mindful");
	throw new Error("cannot resolve mindful data dir: set MINDFUL_HOME, XDG_DATA_HOME, or HOME");
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npx vitest run tests/cli.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Gate + commit**

```bash
cd ~/d/mindful/v6
rtk npm test && rtk npm run typecheck && rtk npm run check
# if check reports diffs:
rtk npx @biomejs/biome check --write src/cli.ts tests/cli.test.ts
rtk git add src/cli.ts tests/cli.test.ts
rtk git commit -m "feat(cli): resolveDataDir — XDG-aware corpus root resolution"
```

---

## Task 2: `runCli` dispatch + error model + no-flag commands

**Files:**
- Modify: `~/d/mindful/v6/src/cli.ts`
- Test: `~/d/mindful/v6/tests/cli.test.ts`

**Interfaces:**
- Consumes: `resolveDataDir` (Task 1, unchanged); `Mindful` from `./api.js` (`get`, `delete`, `tag`, `related`, `allThoughts`, `sprite`); `spriteToAnsi` from `./encode.js`; `NodesError` from `@nodes/kernel`.
- Produces:
  - `type Sink = (s: string) => void`
  - `export function runCli(argv: string[], mindful: Mindful, out: Sink, err: Sink): number`
  - Module-private: `CliUsageError`, `CliError`, `parse(rest, options)`, `resolveId(mindful, ref)`, and handlers `cmdList`/`cmdShow`/`cmdDelete`/`cmdTag`. `argv` is `process.argv.slice(2)`. The dispatch `switch` routes `add`/`edit`/`search` to the `default` (usage, exit 2) until Task 3 adds them.

- [ ] **Step 1: Write the failing tests**

Historical SP5 snippet: current tests call `runCli(argv, root, env, now, out, err, () => mindful, runEditor?)` and all direct `Mindful.capture` setup passes `at: CAPTURE_AT`. Current ref resolution also goes through the thought catalog and supports aliases/display refs.

Append to `~/d/mindful/v6/tests/cli.test.ts`. First extend the imports at the top of the file to:

```ts
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Mindful } from "../src/api.js";
import { resolveDataDir, runCli } from "../src/cli.js";
```

Then append these suites:

```ts
describe("runCli — dispatch + no-flag commands", () => {
	let root: string;
	let out: string[];
	let err: string[];
	let m: Mindful;

	beforeEach(() => {
		root = mkdtempSync(join(tmpdir(), "mindful-cli-"));
		out = [];
		err = [];
		m = new Mindful(root);
	});
	afterEach(() => rmSync(root, { recursive: true, force: true }));

	const run = (...argv: string[]): number =>
		runCli(argv, m, (s) => out.push(s), (s) => err.push(s));
	const stdout = () => out.join("");
	const stderr = () => err.join("");

	it("list of zero thoughts: exit 0, no sink call", () => {
		expect(run("list")).toBe(0);
		expect(out).toHaveLength(0);
	});

	it("list prints id + title per thought, id-sorted", () => {
		const a = m.capture({ title: "Alpha" });
		const b = m.capture({ title: "Beta" });
		expect(run("list")).toBe(0);
		const lines = stdout().trimEnd().split("\n");
		expect(lines).toHaveLength(2);
		expect(stdout()).toContain(`${a.id}  Alpha`);
		expect(stdout()).toContain(`${b.id}  Beta`);
		// id-sorted ascending
		const sorted = [a.id, b.id].sort();
		expect(lines[0].startsWith(sorted[0])).toBe(true);
		expect(stdout().endsWith("\n")).toBe(true);
	});

	it("show prints sprite + stable fields, related: [] when none", () => {
		const t = m.capture({ title: "Solo", body: "the body" });
		expect(run("show", t.id)).toBe(0);
		const s = stdout();
		expect(s).toContain("▀"); // half-block glyph from spriteToAnsi
		expect(s).toContain("\x1b[38;2;"); // truecolor fg escape
		expect(s).toContain(`id: ${t.id}`);
		expect(s).toContain("title: Solo");
		expect(s).toContain("body: the body");
		expect(s).toContain("related: []");
	});

	it("show resolves a unique id-prefix (bare uid prefix)", () => {
		const t = m.capture({ title: "Prefixed" });
		const uid = t.id.slice("thought:".length);
		expect(run("show", uid.slice(0, 6))).toBe(0);
		expect(stdout()).toContain(`id: ${t.id}`);
	});

	it("show ambiguous prefix → exit 1", () => {
		m.capture({ title: "One" });
		m.capture({ title: "Two" });
		expect(run("show", "thought:")).toBe(1);
		expect(stderr()).toContain("error:");
	});

	it("show non-matching ref → exit 1", () => {
		expect(run("show", "nope")).toBe(1);
		expect(stderr()).toContain("error:");
	});

	it("delete removes a thought", () => {
		const t = m.capture({ title: "Doomed" });
		expect(run("delete", t.id)).toBe(0);
		expect(stdout()).toContain(`deleted ${t.id}`);
		expect(run("show", t.id)).toBe(1); // gone
	});

	it("tag links to an existing target and show lists it under related", () => {
		const target = m.capture({ title: "Target" });
		const src = m.capture({ title: "Source" });
		expect(run("tag", src.id, "Target")).toBe(0);
		expect(stdout()).toContain(`tagged ${src.id} #Target`);
		out.length = 0;
		expect(run("show", src.id)).toBe(0);
		expect(stdout()).toContain("related:");
		expect(stdout()).toContain(`- ${target.id}`);
	});

	it("tag with a non-existent target → NodesError → exit 1", () => {
		const src = m.capture({ title: "Lonely" });
		expect(run("tag", src.id, "ghost")).toBe(1);
		expect(stderr()).toContain("error:");
	});

	it("usage errors → exit 2", () => {
		expect(run()).toBe(2); // no command
		expect(run("bogus")).toBe(2); // unknown command
		expect(run("list", "extra")).toBe(2); // list takes no args
		expect(run("show")).toBe(2); // missing ref
		expect(run("show", "--nope", "x")).toBe(2); // unknown flag
		expect(stderr()).toContain("usage");
	});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npx vitest run tests/cli.test.ts`
Expected: FAIL — `runCli` is not exported from `../src/cli.js`.

- [ ] **Step 3: Implement `runCli`, error model, dispatch, and no-flag commands**

Historical SP5 snippet: the implemented CLI no longer resolves refs from `mindful.allThoughts()` on every command. Current code uses `ensureCatalog(root)`/`resolveCatalogRef`, maps `CatalogError`/`ConfigError`/`SemanticError`/`EditorError` to exit 1, and keeps construction behind `makeMindful`.

Edit `~/d/mindful/v6/src/cli.ts`. Update the top imports to:

```ts
import { join } from "node:path";
import { type ParseArgsConfig, parseArgs } from "node:util";
import { type Node, NodesError } from "@nodes/kernel";
import { type Mindful } from "./api.js";
import { spriteToAnsi } from "./encode.js";
```

(One combined `node:util` import — biome flags duplicate imports from the same module.) Keep `firstNonEmpty` and `resolveDataDir` exactly as in Task 1. Then add below them:

```ts
type Sink = (s: string) => void;
type Options = NonNullable<ParseArgsConfig["options"]>;

/** Usage problem (bad command / args / flags) → exit 2. */
class CliUsageError extends Error {}
/** CLI-level domain failure not covered by a kernel NodesError (e.g. ref resolution) → exit 1. */
class CliError extends Error {}

const USAGE = `usage: mindful <command> [args]

commands:
  add <title> [--body <text>] [--tag <name>]...
  show <ref>
  list
  search <query> [--limit <n>]
  edit <ref> [--title <text>] [--body <text>]
  delete <ref>
  tag <ref> <name>`;

/** parseArgs wrapper: strict, positionals + tokens on; its throws become usage errors. */
function parse(rest: string[], options: Options) {
	try {
		return parseArgs({ args: rest, options, allowPositionals: true, strict: true, tokens: true });
	} catch (e) {
		throw new CliUsageError(e instanceof Error ? e.message : String(e));
	}
}

/** Resolve a <ref> to exactly one thought id: full id, id-prefix, or bare uid-prefix.
 * Zero or multiple matches are CLI domain failures (exit 1). */
function resolveId(mindful: Mindful, ref: string): string {
	const matches = mindful
		.allThoughts()
		.filter((t) => t.id === ref || t.id.startsWith(ref) || t.id.startsWith(`thought:${ref}`));
	if (matches.length === 1) return matches[0].id;
	if (matches.length === 0) throw new CliError(`no thought matching ${JSON.stringify(ref)}`);
	throw new CliError(`ambiguous ref ${JSON.stringify(ref)}: matches ${matches.length} thoughts`);
}

function cmdList(mindful: Mindful, rest: string[], out: Sink): number {
	const { positionals } = parse(rest, {});
	if (positionals.length !== 0) throw new CliUsageError("list takes no arguments");
	const thoughts = mindful.allThoughts().sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
	if (thoughts.length === 0) return 0; // no sink call
	out(`${thoughts.map((t) => `${t.id}  ${t.title}`).join("\n")}\n`);
	return 0;
}

function formatShow(node: Node, ansi: string, related: Node[]): string {
	const lines = [ansi, `id: ${node.id}`, `title: ${node.title}`, `body: ${node.body}`];
	lines.push(related.length === 0 ? "related: []" : `related:\n${related.map((r) => `- ${r.id}`).join("\n")}`);
	return `${lines.join("\n")}\n`;
}

function cmdShow(mindful: Mindful, rest: string[], out: Sink): number {
	const { positionals } = parse(rest, {});
	if (positionals.length !== 1) throw new CliUsageError("show <ref>");
	const id = resolveId(mindful, positionals[0]);
	const node = mindful.get(id);
	const ansi = spriteToAnsi(mindful.sprite(id));
	out(formatShow(node, ansi, mindful.related(id)));
	return 0;
}

function cmdDelete(mindful: Mindful, rest: string[], out: Sink): number {
	const { positionals } = parse(rest, {});
	if (positionals.length !== 1) throw new CliUsageError("delete <ref>");
	const id = resolveId(mindful, positionals[0]);
	mindful.delete(id);
	out(`deleted ${id}\n`);
	return 0;
}

function cmdTag(mindful: Mindful, rest: string[], out: Sink): number {
	const { positionals } = parse(rest, {});
	if (positionals.length !== 2) throw new CliUsageError("tag <ref> <name>");
	const id = resolveId(mindful, positionals[0]);
	mindful.tag(id, positionals[1]);
	out(`tagged ${id} #${positionals[1]}\n`);
	return 0;
}

/** Parse, dispatch, format, and map errors to exit codes. Writes only via out/err. */
export function runCli(argv: string[], mindful: Mindful, out: Sink, err: Sink): number {
	try {
		const [command, ...rest] = argv;
		switch (command) {
			case "list":
				return cmdList(mindful, rest, out);
			case "show":
				return cmdShow(mindful, rest, out);
			case "delete":
				return cmdDelete(mindful, rest, out);
			case "tag":
				return cmdTag(mindful, rest, out);
			default:
				throw new CliUsageError(command === undefined ? "no command" : `unknown command ${JSON.stringify(command)}`);
		}
	} catch (e) {
		if (e instanceof CliUsageError) {
			err(`${e.message}\n\n${USAGE}\n`);
			return 2;
		}
		if (e instanceof NodesError || e instanceof CliError) {
			err(`error: ${(e as Error).message}\n`);
			return 1;
		}
		throw e; // unexpected: fail-early, do not mask
	}
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk npx vitest run tests/cli.test.ts`
Expected: PASS (all Task 1 + Task 2 suites).

- [ ] **Step 5: Gate + commit**

```bash
cd ~/d/mindful/v6
rtk npm test && rtk npm run typecheck && rtk npm run check
# if check reports diffs:
rtk npx @biomejs/biome check --write src/cli.ts tests/cli.test.ts
rtk git add src/cli.ts tests/cli.test.ts
rtk git commit -m "feat(cli): runCli dispatch + error model + list/show/delete/tag"
```

---

## Task 3: flag-bearing commands — `add`, `edit`, `search`

**Files:**
- Modify: `~/d/mindful/v6/src/cli.ts`
- Test: `~/d/mindful/v6/tests/cli.test.ts`

**Interfaces:**
- Consumes: everything from Task 2 (`parse`, `CliUsageError`, `CliError`, `resolveId`, `runCli`'s `switch`); `Mindful.capture`/`edit`/`search`/`get`/`sprite`; `spriteToAnsi`.
- Produces: module-private `parseFlags(rest, options, singleValued)` (rejects a repeated single-valued flag via token scan) and handlers `cmdAdd`/`cmdEdit`/`cmdSearch`; adds their three `case`s to `runCli`'s `switch`.

- [ ] **Step 1: Write the failing tests**

Historical SP5 snippet: current `add` output includes the captured date, current `capture` requires `at`, and current tests include additional editor, alias, catalog, semantic, and partial-refresh cases.

Append this suite to `~/d/mindful/v6/tests/cli.test.ts` (its own `describe` with the same harness):

```ts
describe("runCli — flag-bearing commands", () => {
	let root: string;
	let out: string[];
	let err: string[];
	let m: Mindful;

	beforeEach(() => {
		root = mkdtempSync(join(tmpdir(), "mindful-cli-"));
		out = [];
		err = [];
		m = new Mindful(root);
	});
	afterEach(() => rmSync(root, { recursive: true, force: true }));

	const run = (...argv: string[]): number =>
		runCli(argv, m, (s) => out.push(s), (s) => err.push(s));
	const stdout = () => out.join("");
	const stderr = () => err.join("");

	it("add captures and prints id + sprite (CLI-only round trip)", () => {
		expect(run("add", "Hello")).toBe(0);
		const s = stdout();
		expect(s).toMatch(/^added thought:[0-9a-f]{32}\n/);
		expect(s).toContain("▀");
		expect(s).toContain("\x1b[38;2;");
		out.length = 0;
		expect(run("list")).toBe(0);
		expect(stdout()).toContain("Hello");
	});

	it("add with --body and --tag (targets created first)", () => {
		expect(run("add", "TagA")).toBe(0);
		expect(run("add", "TagB")).toBe(0);
		out.length = 0;
		expect(run("add", "Tagged", "--body", "with body", "--tag", "TagA", "--tag", "TagB")).toBe(0);
		const id = stdout().match(/added (thought:[0-9a-f]{32})/)?.[1];
		expect(id).toBeDefined();
		out.length = 0;
		expect(run("show", id as string)).toBe(0);
		expect(stdout()).toContain("body: with body");
		expect(stdout()).toContain("related:");
	});

	it("add --tag with a non-existent target → exit 1, nothing persisted", () => {
		expect(run("add", "Orphan", "--tag", "ghost")).toBe(1);
		expect(stderr()).toContain("error:");
		out.length = 0;
		expect(run("list")).toBe(0);
		expect(out).toHaveLength(0); // not persisted
	});

	it("edit updates the body; show reflects it", () => {
		const t = m.capture({ title: "Editable", body: "old" });
		expect(run("edit", t.id, "--body", "new")).toBe(0);
		expect(stdout()).toContain(`updated ${t.id}`);
		out.length = 0;
		expect(run("show", t.id)).toBe(0);
		expect(stdout()).toContain("body: new");
	});

	it("edit with no flags → exit 2", () => {
		const t = m.capture({ title: "NoFlags" });
		expect(run("edit", t.id)).toBe(2);
		expect(stderr()).toContain("usage");
	});

	it("edit a multiline body is printed verbatim by show", () => {
		const t = m.capture({ title: "Multi" });
		expect(run("edit", t.id, "--body", "a\nb")).toBe(0);
		out.length = 0;
		expect(run("show", t.id)).toBe(0);
		expect(stdout()).toContain("body: a\nb");
	});

	it("search finds a match, preserves kernel order, raw score", () => {
		m.capture({ title: "needle in here" });
		m.capture({ title: "unrelated" });
		expect(run("search", "needle")).toBe(0);
		const s = stdout();
		expect(s).toContain("needle in here");
		expect(s).toMatch(/\(\d/); // "(<score>" — raw numeric, not blank
		expect(s.endsWith("\n")).toBe(true);
	});

	it("search with no hits: exit 0, no sink call", () => {
		m.capture({ title: "alpha" });
		expect(run("search", "zzzznomatch")).toBe(0);
		expect(out).toHaveLength(0);
	});

	it("invalid --limit → exit 2", () => {
		m.capture({ title: "x" });
		expect(run("search", "x", "--limit", "abc")).toBe(2);
		expect(run("search", "x", "--limit", "0")).toBe(2);
	});

	it("duplicate single-valued flag → exit 2; repeated --tag allowed", () => {
		expect(run("add", "Dup", "--body", "one", "--body", "two")).toBe(2);
		const t = m.capture({ title: "EditDup" });
		expect(run("edit", t.id, "--title", "x", "--title", "y")).toBe(2);
		m.capture({ title: "SearchDup" });
		expect(run("search", "SearchDup", "--limit", "1", "--limit", "2")).toBe(2);
		// repeated --tag is allowed (targets exist)
		m.capture({ title: "ta" });
		m.capture({ title: "tb" });
		expect(run("add", "WithTags", "--tag", "ta", "--tag", "tb")).toBe(0);
	});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npx vitest run tests/cli.test.ts`
Expected: FAIL — `add`/`edit`/`search` currently hit the `default` case (exit 2), so the success-path assertions fail.

- [ ] **Step 3: Implement `parseFlags` + the three handlers + extend the switch**

Historical SP5 snippet: current `cmdAdd` receives `now`, calls `Mindful.capture({ at: now, ... })`, refreshes the catalog after mutations, and resolves the active scheme before rendering. Current `cmdSearch` also supports `--semantic`, and `cmdEdit` supports `--editor`.

Edit `~/d/mindful/v6/src/cli.ts`. Add `parseFlags` after `parse`:

```ts
/** Like parse, but rejects any single-valued flag given more than once (parseArgs would silently
 * keep the last). --tag is multiple and exempt; only names in `singleValued` are policed. */
function parseFlags(rest: string[], options: Options, singleValued: string[]) {
	const parsed = parse(rest, options);
	const seen = new Set<string>();
	for (const tok of parsed.tokens) {
		if (tok.kind !== "option" || !singleValued.includes(tok.name)) continue;
		if (seen.has(tok.name)) throw new CliUsageError(`--${tok.name} given more than once`);
		seen.add(tok.name);
	}
	return parsed;
}
```

Add the three handlers (next to the others):

```ts
function cmdAdd(mindful: Mindful, rest: string[], out: Sink): number {
	const { values, positionals } = parseFlags(
		rest,
		{ body: { type: "string" }, tag: { type: "string", multiple: true } },
		["body"],
	);
	if (positionals.length !== 1) throw new CliUsageError("add <title> [--body <text>] [--tag <name>]...");
	const node = mindful.capture({
		title: positionals[0],
		body: values.body as string | undefined,
		tags: values.tag as string[] | undefined,
	});
	out(`added ${node.id}\n${spriteToAnsi(mindful.sprite(node.id))}\n`);
	return 0;
}

function cmdEdit(mindful: Mindful, rest: string[], out: Sink): number {
	const { values, positionals } = parseFlags(
		rest,
		{ title: { type: "string" }, body: { type: "string" } },
		["title", "body"],
	);
	if (positionals.length !== 1) throw new CliUsageError("edit <ref> [--title <text>] [--body <text>]");
	const title = values.title as string | undefined;
	const body = values.body as string | undefined;
	if (title === undefined && body === undefined) throw new CliUsageError("edit requires --title and/or --body");
	const id = resolveId(mindful, positionals[0]);
	mindful.edit(id, { title, body });
	out(`updated ${id}\n`);
	return 0;
}

function cmdSearch(mindful: Mindful, rest: string[], out: Sink): number {
	const { values, positionals } = parseFlags(rest, { limit: { type: "string" } }, ["limit"]);
	if (positionals.length !== 1) throw new CliUsageError("search <query> [--limit <n>]");
	let limit: number | undefined;
	const raw = values.limit as string | undefined;
	if (raw !== undefined) {
		const n = Number(raw);
		if (!Number.isInteger(n) || n < 1) throw new CliUsageError(`invalid --limit ${JSON.stringify(raw)}`);
		limit = n;
	}
	const hits = mindful.search(positionals[0], limit); // kernel order: score desc, id asc — do not re-sort
	if (hits.length === 0) return 0; // no sink call
	out(`${hits.map((h) => `${h.id}  ${mindful.get(h.id).title}  (${String(h.score)})`).join("\n")}\n`);
	return 0;
}
```

Replace the `switch` in `runCli` with one that includes all seven commands:

```ts
		switch (command) {
			case "add":
				return cmdAdd(mindful, rest, out);
			case "show":
				return cmdShow(mindful, rest, out);
			case "list":
				return cmdList(mindful, rest, out);
			case "search":
				return cmdSearch(mindful, rest, out);
			case "edit":
				return cmdEdit(mindful, rest, out);
			case "delete":
				return cmdDelete(mindful, rest, out);
			case "tag":
				return cmdTag(mindful, rest, out);
			default:
				throw new CliUsageError(command === undefined ? "no command" : `unknown command ${JSON.stringify(command)}`);
		}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `rtk npx vitest run tests/cli.test.ts`
Expected: PASS (all suites).

- [ ] **Step 5: Gate + commit**

```bash
cd ~/d/mindful/v6
rtk npm test && rtk npm run typecheck && rtk npm run check
# if check reports diffs:
rtk npx @biomejs/biome check --write src/cli.ts tests/cli.test.ts
rtk git add src/cli.ts tests/cli.test.ts
rtk git commit -m "feat(cli): add/edit/search commands + duplicate-flag rejection"
```

---

## Task 4: build to `dist/`, `bin.ts`, package metadata, barrel exports

**Files:**
- Create: `~/d/mindful/v6/src/bin.ts`
- Create: `~/d/mindful/v6/tsconfig.build.json`
- Modify: `~/d/mindful/v6/package.json`
- Modify: `~/d/mindful/v6/biome.json`
- Modify: `~/d/mindful/v6/.gitignore`
- Modify: `~/d/mindful/v6/src/index.ts`

**Interfaces:**
- Consumes: `runCli`, `resolveDataDir` from `./cli.js` (Tasks 1–3).
- Produces: a runnable `mindful` command (`dist/bin.js`); `runCli`/`resolveDataDir` exported from the barrel; a `build` script and full dist package metadata. This task has no vitest unit (bin is wiring); its gate is a clean build emitting `dist/bin.js` + `dist/index.js`, plus the existing suite + typecheck + check.

- [ ] **Step 1: Create the build tsconfig**

Create `~/d/mindful/v6/tsconfig.build.json` (mirrors `@nodes/kernel`):

```json
{
	"extends": "./tsconfig.json",
	"compilerOptions": {
		"noEmit": false,
		"outDir": "dist",
		"rootDir": "src",
		"declaration": true,
		"declarationMap": true,
		"sourceMap": true
	},
	"include": ["src"]
}
```

- [ ] **Step 2: Create the thin executable wrapper**

Historical SP5 snippet: current `bin.ts` passes `root`, `process.env`, `localIso(new Date())`, a lazy `Mindful` factory, and an `EditorRunner` that shells out to `VISUAL`/`EDITOR`; it sets `process.exitCode` rather than calling `process.exit`.

Create `~/d/mindful/v6/src/bin.ts` (the shebang MUST be the first line; `tsc` preserves it on emit):

```ts
#!/usr/bin/env node
import { mkdirSync } from "node:fs";
import { Mindful } from "./api.js";
import { resolveDataDir, runCli } from "./cli.js";

const root = resolveDataDir(process.env);
mkdirSync(root, { recursive: true });
const mindful = new Mindful(root);
const code = runCli(
	process.argv.slice(2),
	mindful,
	(s) => {
		process.stdout.write(s);
	},
	(s) => {
		process.stderr.write(s);
	},
);
process.exit(code);
```

- [ ] **Step 3: Add the barrel exports**

Edit `~/d/mindful/v6/src/index.ts` — append after the existing `spriteToAnsi` export:

```ts
export { runCli, resolveDataDir } from "./cli.js";
```

- [ ] **Step 4: Update `package.json`**

Edit `~/d/mindful/v6/package.json`. Replace `"main": "src/index.ts"` and the `scripts` block, and add `types`/`exports`/`files`/`bin`, so the package becomes:

```jsonc
{
	"name": "@mindful/v6",
	"version": "0.1.0",
	"description": "Mindful: a headless thought/mindmap/journal app over @nodes/kernel",
	"type": "module",
	"engines": { "node": ">=20" },
	"main": "dist/index.js",
	"types": "dist/index.d.ts",
	"exports": { ".": { "types": "./dist/index.d.ts", "default": "./dist/index.js" } },
	"files": ["dist"],
	"bin": { "mindful": "dist/bin.js" },
	"scripts": {
		"build": "tsc -p tsconfig.build.json",
		"test": "vitest run",
		"typecheck": "tsc --noEmit",
		"check": "biome check ."
	},
	"dependencies": {
		"@nodes/kernel": "file:../../nodes/ts",
		"zod": "^3.23.0"
	},
	"devDependencies": {
		"@biomejs/biome": "^1.9.0",
		"@types/node": "^20.0.0",
		"typescript": "^5.5.0",
		"vitest": "^2.0.0"
	}
}
```

- [ ] **Step 5: Ignore `dist/` for git and biome**

Edit `~/d/mindful/v6/.gitignore` to:

```
node_modules/
dist/
```

Edit `~/d/mindful/v6/biome.json` to add a `files.ignore` (so `biome check .` never lints generated JS):

```json
{
	"$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
	"files": { "ignore": ["dist"] },
	"formatter": { "enabled": true, "lineWidth": 120 },
	"linter": { "enabled": true, "rules": { "recommended": true } }
}
```

- [ ] **Step 6: Build and verify emission**

```bash
cd ~/d/mindful/v6
rtk npm run build
rtk ls dist/bin.js dist/index.js dist/cli.js
rtk sed -n '1p' dist/bin.js   # expect: #!/usr/bin/env node
```
Expected: build exits 0; all three files exist; `dist/bin.js` first line is the shebang.

- [ ] **Step 7: Smoke-test the runnable bin end-to-end**

```bash
cd ~/d/mindful/v6
D="$(mktemp -d)"                                   # one corpus dir across both calls
MINDFUL_HOME="$D" rtk node dist/bin.js add "first thought"
MINDFUL_HOME="$D" rtk node dist/bin.js list
```
Expected: `add` prints `added thought:…` then a colored sprite; `list` prints the `thought:…  first thought` line. (Manual verification only — not a committed test.)

- [ ] **Step 8: Full gate**

```bash
cd ~/d/mindful/v6
rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build
# if check reports diffs:
rtk npx @biomejs/biome check --write src/bin.ts src/index.ts
```
Expected: all four stages pass.

- [ ] **Step 9: Commit**

```bash
cd ~/d/mindful/v6
rtk git add src/bin.ts src/index.ts tsconfig.build.json package.json biome.json .gitignore
rtk git commit -m "feat(cli): runnable mindful bin + dist build + package metadata"
```

---

## Self-Review

**Spec coverage (against `2026-06-24-mindful-v6-sp5-cli-shell-design.md`):**
- §2 seven commands → Task 2 (`list`/`show`/`delete`/`tag`) + Task 3 (`add`/`edit`/`search`). ✅
- §2 `parseArgs` config (`--tag` multiple; others single) + dup-flag rejection → Task 3 `parseFlags`. ✅
- §2 `add --tag` no-auto-create / nothing persisted → Task 3 test "non-existent target". ✅
- §3 unique-prefix `<ref>` (full id / id-prefix / bare uid-prefix; zero & ambiguous → exit 1) → Task 2 `resolveId` + tests. ✅
- §4 `resolveDataDir` order + empty-as-absent + throw → Task 1. ✅
- §5 usage(2)/domain(1)/success(0), `instanceof NodesError`, `parseArgs` throws → usage, unexpected rethrown → Task 2 `runCli` catch. ✅
- §6 `add` (id + sprite), `show` (sprite + stable fields, verbatim body, `related: []`), `list` (id-sorted), `search` (kernel order, raw score), confirmations, no-output→no-sink-call → Tasks 2–3 handlers + tests. ✅
- §7 file set, `runCli`/`resolveDataDir` signatures, full dist metadata, shebang preserved, base tsconfig stays `noEmit` → Tasks 1–4. ✅
- §8 extended gate incl. `rtk npm run build` → Task 4 Step 8; test cases (round trip, ANSI real, multiline body, dup-flag with targets created first, empty search no sink) → Tasks 2–3. ✅
- §8 biome won't lint `dist/` → Task 4 `files.ignore`. ✅
- Scheme boundary: `show`/`add` use `Mindful.sprite()` default (`defaultColorscheme`); no scheme flag anywhere. ✅

**Placeholder scan:** none — every code/test step carries complete code; the only manual-only step (Task 4 Step 7 smoke test) is explicitly not a committed test.

**Type consistency:** `runCli(argv, mindful, out, err): number`, `Sink = (s: string) => void`, `resolveDataDir(env): string`, `resolveId(mindful, ref): string`, `parse`/`parseFlags` return the `parseArgs` result shape, handlers `cmd*(mindful, rest, out): number` — names and signatures match across Tasks 1–4 and the barrel export in Task 4.

Current-code note: the current type contract is `runCli(argv, root, env, now, out, err, makeMindful, runEditor?)`, with root/catalog-based helpers and additional domain errors/commands layered on top of this SP5 baseline.
