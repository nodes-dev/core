# Mindful v6 SP6 — Scheme Picker + Active-Scheme Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `mindful` CLI a catalog of built-in colorschemes, a persisted active-scheme choice, and `scheme list/set/show` commands — so rendered sprites reflect the user's chosen palette.

**Architecture:** Two new pure-ish modules — `src/schemes.ts` (a 6-palette catalog with a defensive-copy accessor) and `src/config.ts` (reads/writes/validates `<root>/config.yaml` and resolves the active scheme with `MINDFUL_SCHEME > config.yaml > default` precedence). `runCli` grows two injected app dependencies (`root`, `env`); `add`/`show` resolve the active scheme and pass it into `mindful.sprite()`; a new `scheme` command drives the catalog and config. Scheme config lives beside the CLI, never inside `Mindful` (which stays thought/raster-domain).

**Tech Stack:** TypeScript (ESM, `.js` import specifiers), vitest, the `yaml` package (already a direct dependency), `@nodes/kernel` (consumed as built JS — **no kernel changes**), biome.

## Global Constraints

- **No kernel changes.** All work is in `~/d/mindful/v6`. `@nodes/kernel` is consumed as built JS.
- **Gate (run from `~/d/mindful/v6`):** `rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build` — all four must pass at the end of every task.
- **All tooling via `rtk`:** `rtk npm …`, `rtk node …`, `rtk npx …`. Never bare `npm`/`node`/`git` for the build/test loop.
- **grep/rg give corrupted output under rtk** — read files with the editor, not shell grep.
- **biome:** tabs, line width 120, organizes/sorts imports, flags duplicate imports from the same module. `check` is read-only; fix diffs with `rtk npx @biomejs/biome check --write <files>`.
- **Fail early / no silent fallback.** Unknown scheme names and ill-shaped config throw; reads never invent a default value silently except the documented "nothing set → built-in default" precedence.
- **Explicit > defensive; composition > inheritance.** No "legacy"/"compatibility" layers, no "Unified" prefixes.
- **Persistence is explicit:** `config.yaml` is written **only** by `scheme set`. All other paths are pure reads.
- **Identity is never mutated.** Schemes color the raster at render time only.
- **Canonical palettes are pinned (below), not improvised.** Use the exact hex listed for `gameboy`, `dawnbringer-16`, `nord`, `solarized`; `monochrome` is the one freely-authored ramp; `chiptune-16` already lives in `color.ts`.
- **Sink contract (from SP5):** sinks receive complete, newline-terminated strings; commands with no output make no sink call.
- **Use `~/d/` in any doc/code paths**, never `/home/keith/` or `/mnt/ssd/Dropbox/`.

## File Structure

- **Create `src/schemes.ts`** — catalog: the 5 new `Colorscheme` palettes + `chiptune-16` (by reference), a name→scheme registry, `DEFAULT_SCHEME_NAME`, `schemeNames()`, `getScheme(name)`.
- **Create `src/config.ts`** — `MindfulConfig`, `ConfigError`, `readConfig`, `writeConfig`, `resolveActiveScheme`.
- **Modify `src/cli.ts`** — new `runCli` signature `(argv, mindful, root, env, out, err)`; thread active scheme into `add`/`show`; add the `scheme` command + `SCHEME_USAGE`; `CliUsageError` gains an optional per-error usage string; catch `ConfigError` → exit 1.
- **Modify `src/bin.ts`** — pass `root` and `process.env` through.
- **Modify `src/index.ts`** — barrel-export the new public symbols.
- **Create `tests/schemes.test.ts`**, **`tests/config.test.ts`**; **modify `tests/cli.test.ts`** (migrate both `run` helpers; add scheme-command, render-threading, malformed-config tests).

## Task Dependency Order

Task 1 (schemes) → Task 2 (config, uses schemes) → Task 3 (cli signature + render threading + bin, uses config) → Task 4 (scheme command, uses config + new signature). Each task ends green on the full gate.

---

### Task 1: Scheme catalog (`src/schemes.ts`)

**Files:**
- Create: `src/schemes.ts`
- Modify: `src/index.ts`
- Test: `tests/schemes.test.ts`

**Interfaces:**
- Consumes: `type Colorscheme`, `defaultColorscheme` from `src/color.ts` (`Colorscheme = { name: string; colors: string[] }`; `defaultColorscheme.name === "chiptune-16"`).
- Produces:
  - `DEFAULT_SCHEME_NAME: string` (= `defaultColorscheme.name`)
  - `schemeNames(): string[]` — catalog order, default first: `["chiptune-16","gameboy","dawnbringer-16","monochrome","nord","solarized"]`
  - `getScheme(name: string): Colorscheme` — returns a **defensive copy** `{ name, colors: [...] }`; throws a plain `Error` on unknown name.

- [ ] **Step 1: Write the failing test**

Create `tests/schemes.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { defaultColorscheme } from "../src/color.js";
import { DEFAULT_SCHEME_NAME, getScheme, schemeNames } from "../src/schemes.js";

const HEX = /^#[0-9a-f]{6}$/;

describe("schemes catalog", () => {
	it("DEFAULT_SCHEME_NAME derives from the default object", () => {
		expect(DEFAULT_SCHEME_NAME).toBe(defaultColorscheme.name);
	});

	it("schemeNames lists all six, default first", () => {
		expect(schemeNames()).toEqual(["chiptune-16", "gameboy", "dawnbringer-16", "monochrome", "nord", "solarized"]);
	});

	it("getScheme returns the requested palette", () => {
		expect(getScheme("gameboy").name).toBe("gameboy");
		expect(getScheme("chiptune-16").colors).toEqual(defaultColorscheme.colors);
	});

	it("getScheme returns a defensive copy (catalog stays immutable)", () => {
		const a = getScheme("gameboy");
		a.colors[0] = "#ffffff";
		a.colors.push("#000000");
		const b = getScheme("gameboy");
		expect(b.colors[0]).not.toBe("#ffffff");
		expect(b.colors).toHaveLength(4);
	});

	it("getScheme throws on an unknown name", () => {
		expect(() => getScheme("nope")).toThrow();
	});

	it("every palette is non-empty and all entries are #rrggbb", () => {
		for (const name of schemeNames()) {
			const { colors } = getScheme(name);
			expect(colors.length).toBeGreaterThan(0);
			for (const c of colors) expect(c).toMatch(HEX);
		}
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npm test -- schemes`
Expected: FAIL — cannot resolve `../src/schemes.js`.

- [ ] **Step 3: Write `src/schemes.ts`**

Create `src/schemes.ts` with the catalog. The hex values below are canonical for the named palettes — copy them verbatim, lowercase:

```ts
import { type Colorscheme, defaultColorscheme } from "./color.js";

/** Built-in colorschemes beyond the default. chiptune-16 is the default and lives in color.ts. */
const GAMEBOY: Colorscheme = {
	name: "gameboy",
	colors: ["#0f380f", "#306230", "#8bac0f", "#9bbc0f"],
};

const DAWNBRINGER_16: Colorscheme = {
	name: "dawnbringer-16",
	colors: [
		"#140c1c",
		"#442434",
		"#30346d",
		"#4e4a4e",
		"#854c30",
		"#346524",
		"#d04648",
		"#757161",
		"#597dce",
		"#d27d2c",
		"#8595a1",
		"#6daa2c",
		"#d2aa99",
		"#6dc2ca",
		"#dad45e",
		"#deeed6",
	],
};

const MONOCHROME: Colorscheme = {
	name: "monochrome",
	colors: ["#000000", "#242424", "#484848", "#6d6d6d", "#919191", "#b6b6b6", "#dadada", "#ffffff"],
};

const NORD: Colorscheme = {
	name: "nord",
	colors: [
		"#2e3440",
		"#3b4252",
		"#434c5e",
		"#4c566a",
		"#d8dee9",
		"#e5e9f0",
		"#eceff4",
		"#8fbcbb",
		"#88c0d0",
		"#81a1c1",
		"#5e81ac",
		"#bf616a",
		"#d08770",
		"#ebcb8b",
		"#a3be8c",
		"#b48ead",
	],
};

const SOLARIZED: Colorscheme = {
	name: "solarized",
	colors: [
		"#002b36",
		"#073642",
		"#586e75",
		"#657b83",
		"#839496",
		"#93a1a1",
		"#eee8d5",
		"#fdf6e3",
		"#b58900",
		"#cb4b16",
		"#dc322f",
		"#d33682",
		"#6c71c4",
		"#268bd2",
		"#2aa198",
		"#859900",
	],
};

/** Catalog order: default first, then the rest. */
const CATALOG: Colorscheme[] = [defaultColorscheme, GAMEBOY, DAWNBRINGER_16, MONOCHROME, NORD, SOLARIZED];

const BY_NAME = new Map<string, Colorscheme>(CATALOG.map((s) => [s.name, s]));

/** Name of the built-in default scheme. Derived from the object so the two never drift. */
export const DEFAULT_SCHEME_NAME = defaultColorscheme.name;

/** All built-in scheme names, in catalog order (default first). */
export function schemeNames(): string[] {
	return CATALOG.map((s) => s.name);
}

/** Look up a built-in scheme by name. Returns a defensive copy so the catalog can't be mutated.
 * Throws (fail-early) on an unknown name; callers translate this into a typed error. */
export function getScheme(name: string): Colorscheme {
	const scheme = BY_NAME.get(name);
	if (scheme === undefined) throw new Error(`unknown scheme ${JSON.stringify(name)}`);
	return { name: scheme.name, colors: [...scheme.colors] };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npm test -- schemes`
Expected: PASS (6 tests).

- [ ] **Step 5: Add barrel exports**

In `src/index.ts`, add this line after the `./sprite.js` / `./encode.js` exports:

```ts
export { DEFAULT_SCHEME_NAME, getScheme, schemeNames } from "./schemes.js";
```

- [ ] **Step 6: Run the full gate**

Run: `rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`
Expected: all pass. If `check` reports formatting/import-order diffs, run `rtk npx @biomejs/biome check --write src/schemes.ts src/index.ts tests/schemes.test.ts` and re-run the gate.

- [ ] **Step 7: Commit**

```bash
rtk git add src/schemes.ts src/index.ts tests/schemes.test.ts
rtk git commit -m "feat(scheme): built-in colorscheme catalog (6 palettes)"
```

---

### Task 2: Config persistence + active-scheme resolution (`src/config.ts`)

**Files:**
- Create: `src/config.ts`
- Modify: `src/index.ts`
- Test: `tests/config.test.ts`

**Interfaces:**
- Consumes: `DEFAULT_SCHEME_NAME`, `getScheme` from `src/schemes.ts`; `type Colorscheme` from `src/color.ts`; `parse`/`stringify` from `yaml`.
- Produces:
  - `interface MindfulConfig { scheme?: string }`
  - `class ConfigError extends Error {}`
  - `readConfig(root: string): MindfulConfig`
  - `writeConfig(root: string, config: MindfulConfig): void`
  - `resolveActiveScheme(root: string, env: NodeJS.ProcessEnv): { name: string; scheme: Colorscheme; source: "env" | "config" | "default" }`

- [ ] **Step 1: Write the failing test**

Create `tests/config.test.ts`:

```ts
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ConfigError, readConfig, resolveActiveScheme, writeConfig } from "../src/config.js";

describe("readConfig / writeConfig", () => {
	let root: string;
	beforeEach(() => {
		root = mkdtempSync(join(tmpdir(), "mindful-cfg-"));
	});
	afterEach(() => rmSync(root, { recursive: true, force: true }));

	const writeRaw = (text: string) => writeFileSync(join(root, "config.yaml"), text);

	it("missing file → {}", () => expect(readConfig(root)).toEqual({}));
	it("empty file → {}", () => {
		writeRaw("");
		expect(readConfig(root)).toEqual({});
	});
	it("a scheme value parses", () => {
		writeRaw("scheme: gameboy\n");
		expect(readConfig(root)).toEqual({ scheme: "gameboy" });
	});

	it("rejects malformed YAML", () => {
		writeRaw("{a: 1");
		expect(() => readConfig(root)).toThrow(ConfigError);
	});
	it("rejects a top-level array", () => {
		writeRaw("- a\n- b\n");
		expect(() => readConfig(root)).toThrow(ConfigError);
	});
	it("rejects a top-level scalar", () => {
		writeRaw("hello\n");
		expect(() => readConfig(root)).toThrow(ConfigError);
	});
	it("rejects unknown keys", () => {
		writeRaw("color: blue\n");
		expect(() => readConfig(root)).toThrow(ConfigError);
	});
	it("rejects a non-string scheme", () => {
		writeRaw("scheme: 42\n");
		expect(() => readConfig(root)).toThrow(ConfigError);
	});
	it("wraps a non-file config path as ConfigError", () => {
		mkdirSync(join(root, "config.yaml"));
		expect(() => readConfig(root)).toThrow(ConfigError);
	});

	it("writeConfig round-trips a scheme", () => {
		writeConfig(root, { scheme: "nord" });
		expect(readConfig(root)).toEqual({ scheme: "nord" });
	});
	it("writeConfig({}) writes an empty mapping with no scheme key", () => {
		writeConfig(root, {});
		expect(readConfig(root)).toEqual({});
	});
});

describe("resolveActiveScheme", () => {
	let root: string;
	beforeEach(() => {
		root = mkdtempSync(join(tmpdir(), "mindful-cfg-"));
	});
	afterEach(() => rmSync(root, { recursive: true, force: true }));

	it("defaults when nothing is set", () => {
		const r = resolveActiveScheme(root, {});
		expect(r.name).toBe("chiptune-16");
		expect(r.source).toBe("default");
	});
	it("config wins over default", () => {
		writeConfig(root, { scheme: "nord" });
		const r = resolveActiveScheme(root, {});
		expect(r.name).toBe("nord");
		expect(r.source).toBe("config");
	});
	it("env wins over config", () => {
		writeConfig(root, { scheme: "nord" });
		const r = resolveActiveScheme(root, { MINDFUL_SCHEME: "gameboy" });
		expect(r.name).toBe("gameboy");
		expect(r.source).toBe("env");
		expect(r.scheme.name).toBe("gameboy");
	});
	it("an empty MINDFUL_SCHEME is treated as absent", () => {
		writeConfig(root, { scheme: "nord" });
		expect(resolveActiveScheme(root, { MINDFUL_SCHEME: "" }).source).toBe("config");
	});
	it("unknown scheme from config → ConfigError", () => {
		writeConfig(root, { scheme: "bogus" });
		expect(() => resolveActiveScheme(root, {})).toThrow(ConfigError);
	});
	it("unknown scheme from env → ConfigError", () => {
		expect(() => resolveActiveScheme(root, { MINDFUL_SCHEME: "bogus" })).toThrow(ConfigError);
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk npm test -- config`
Expected: FAIL — cannot resolve `../src/config.js`.

- [ ] **Step 3: Write `src/config.ts`**

```ts
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { parse, stringify } from "yaml";
import type { Colorscheme } from "./color.js";
import { DEFAULT_SCHEME_NAME, getScheme } from "./schemes.js";

/** App-level configuration, persisted at <root>/config.yaml. Intentionally tiny. */
export interface MindfulConfig {
	scheme?: string;
}

/** Raised for an unreadable, malformed, or ill-shaped config, or an unknown configured/env scheme. */
export class ConfigError extends Error {}

type SchemeSource = "env" | "config" | "default";

function configPath(root: string): string {
	return join(root, "config.yaml");
}

/** Read and validate <root>/config.yaml. Missing or empty file → {}. Fails early (ConfigError) on
 * malformed YAML, a non-mapping document, unknown keys, or a non-string scheme. Pure (no writes). */
export function readConfig(root: string): MindfulConfig {
	let text: string;
	try {
		text = readFileSync(configPath(root), "utf8");
	} catch (e) {
		if ((e as NodeJS.ErrnoException).code === "ENOENT") return {};
		throw new ConfigError(`cannot read config.yaml: ${e instanceof Error ? e.message : String(e)}`);
	}
	let parsed: unknown;
	try {
		parsed = parse(text);
	} catch (e) {
		throw new ConfigError(`config.yaml is not valid YAML: ${e instanceof Error ? e.message : String(e)}`);
	}
	if (parsed === null || parsed === undefined) return {};
	if (typeof parsed !== "object" || Array.isArray(parsed)) {
		throw new ConfigError("config.yaml must be a mapping");
	}
	const obj = parsed as Record<string, unknown>;
	for (const key of Object.keys(obj)) {
		if (key !== "scheme") throw new ConfigError(`config.yaml has unknown key ${JSON.stringify(key)}`);
	}
	if ("scheme" in obj && typeof obj.scheme !== "string") {
		throw new ConfigError("config.yaml: scheme must be a string");
	}
	return "scheme" in obj ? { scheme: obj.scheme as string } : {};
}

/** Serialize the known config fields to <root>/config.yaml. Only the schema shape is written;
 * writeConfig(root, {}) yields an empty-mapping document. Called only by `scheme set`. */
export function writeConfig(root: string, config: MindfulConfig): void {
	const out: Record<string, string> = {};
	if (config.scheme !== undefined) out.scheme = config.scheme;
	writeFileSync(configPath(root), stringify(out));
}

function lookup(name: string, source: string): Colorscheme {
	try {
		return getScheme(name);
	} catch {
		throw new ConfigError(`unknown scheme ${JSON.stringify(name)} from ${source}`);
	}
}

/** Resolve the active scheme: MINDFUL_SCHEME (non-empty) > config.yaml > built-in default.
 * An unknown name in the env or config path fails early (ConfigError). */
export function resolveActiveScheme(
	root: string,
	env: NodeJS.ProcessEnv,
): { name: string; scheme: Colorscheme; source: SchemeSource } {
	const envName = env.MINDFUL_SCHEME;
	if (envName !== undefined && envName !== "") {
		return { name: envName, scheme: lookup(envName, "MINDFUL_SCHEME"), source: "env" };
	}
	const cfg = readConfig(root);
	if (cfg.scheme !== undefined) {
		return { name: cfg.scheme, scheme: lookup(cfg.scheme, "config.yaml"), source: "config" };
	}
	return { name: DEFAULT_SCHEME_NAME, scheme: getScheme(DEFAULT_SCHEME_NAME), source: "default" };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk npm test -- config`
Expected: PASS (all `readConfig`/`writeConfig`/`resolveActiveScheme` tests).

- [ ] **Step 5: Add barrel exports**

In `src/index.ts`, add after the `./schemes.js` export line:

```ts
export { ConfigError, type MindfulConfig, readConfig, resolveActiveScheme, writeConfig } from "./config.js";
```

- [ ] **Step 6: Run the full gate**

Run: `rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`
Expected: all pass. Fix any biome diffs with `rtk npx @biomejs/biome check --write src/config.ts src/index.ts tests/config.test.ts` and re-run.

- [ ] **Step 7: Commit**

```bash
rtk git add src/config.ts src/index.ts tests/config.test.ts
rtk git commit -m "feat(config): config.yaml read/write + active-scheme resolution"
```

---

### Task 3: Thread active scheme into rendering (`runCli` signature + `add`/`show` + `bin.ts`)

**Files:**
- Modify: `src/cli.ts`
- Modify: `src/bin.ts`
- Test: `tests/cli.test.ts`

**Interfaces:**
- Consumes: `resolveActiveScheme`, `ConfigError` from `src/config.ts`.
- Produces: new exported signature `runCli(argv: string[], mindful: Mindful, root: string, env: NodeJS.ProcessEnv, out: Sink, err: Sink): number`. `add`/`show` now render with the resolved active scheme. (The `scheme` command arrives in Task 4.)

> **Note:** this task changes `runCli`'s arity, so **`bin.ts` and every `runCli` call-site in `tests/cli.test.ts` must be updated in this same task** or the build breaks. There are two `run` helpers in `tests/cli.test.ts` (one per `describe` block) — both call `runCli(argv, m, out, err)` today.

- [ ] **Step 1: Migrate existing call-sites to the new signature (keep tests green-able)**

In `tests/cli.test.ts`:

1. Change the top `node:fs` import to include `writeFileSync`:
   ```ts
   import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
   ```
2. In **both** `describe` blocks, replace the `run` helper with a `root`-and-`env`-aware version (the variadic `argv` stays, so existing `run("show", id)` call-sites are unchanged):
   ```ts
   const run = (...argv: string[]): number =>
   	runCli(
   		argv,
   		m,
   		root,
   		{},
   		(s) => out.push(s),
   		(s) => err.push(s),
   	);
   ```

- [ ] **Step 2: Write the failing tests (new behavior)**

Append a new `describe` block to `tests/cli.test.ts`:

```ts
describe("runCli — active scheme affects rendering", () => {
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

	const runEnv = (env: NodeJS.ProcessEnv, ...argv: string[]): number =>
		runCli(
			argv,
			m,
			root,
			env,
			(s) => out.push(s),
			(s) => err.push(s),
		);
	const stdout = () => out.join("");
	const stderr = () => err.join("");

	it("show renders with the env-selected scheme (monochrome differs from default)", () => {
		m.corpus.add(
			makeNode({
				id: "thought:scheme-probe",
				kind: "thought",
				title: "Probe",
				facets: { [VISUAL_IDENTITY]: deriveIdentity("scheme-probe-seed") },
			}),
		);
		expect(runEnv({}, "show", "thought:scheme-probe")).toBe(0);
		const def = stdout();
		out.length = 0;
		expect(runEnv({ MINDFUL_SCHEME: "monochrome" }, "show", "thought:scheme-probe")).toBe(0);
		const mono = stdout();
		expect(mono).not.toBe(def);
		expect(mono).toContain("id: thought:scheme-probe");
	});

	it("malformed config.yaml makes show exit 1", () => {
		const t = m.capture({ title: "X" });
		writeFileSync(join(root, "config.yaml"), "{ bad");
		expect(runEnv({}, "show", t.id)).toBe(1);
		expect(stderr()).toContain("error:");
	});

	it("malformed config.yaml makes add exit 1 without persisting the thought", () => {
		writeFileSync(join(root, "config.yaml"), "{ bad");
		expect(runEnv({}, "add", "Blocked")).toBe(1);
		expect(stderr()).toContain("error:");
		expect(m.allThoughts()).toEqual([]);
	});
});
```

> If the fixed seed `"scheme-probe-seed"` happens to render identically under both palettes (it should not — monochrome is grayscale, chiptune-16 is saturated), pick another fixed seed; the test is deterministic, so verify once.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `rtk npm test -- cli`
Expected: FAIL — `runCli` is called with 6 args but currently takes 4 (type error / wrong rendering); the new `describe` block fails.

- [ ] **Step 4: Update `runCli` and the rendering commands in `src/cli.ts`**

1. Add to the imports (keep them sorted; biome will enforce order):
   ```ts
   import { ConfigError, resolveActiveScheme } from "./config.js";
   ```
2. Change the `cmdAdd` signature and body to resolve the active scheme **before** capture and render with it:
   ```ts
   function cmdAdd(mindful: Mindful, rest: string[], out: Sink, root: string, env: NodeJS.ProcessEnv): number {
   	const { values, positionals } = parseFlags(rest, {
   		body: { type: "string" },
   		tag: { type: "string", multiple: true },
   	});
   	if (positionals.length !== 1) throw new CliUsageError("add <title> [--body <text>] [--tag <name>]...");
   	const { scheme } = resolveActiveScheme(root, env);
   	const node = mindful.capture({
   		title: positionals[0],
   		body: values.body as string | undefined,
   		tags: values.tag as string[] | undefined,
   	});
   	out(`added ${node.id}\n${spriteToAnsi(mindful.sprite(node.id, scheme))}\n`);
   	return 0;
   }
   ```
3. Change `cmdShow` to render with the active scheme:
   ```ts
   function cmdShow(mindful: Mindful, rest: string[], out: Sink, root: string, env: NodeJS.ProcessEnv): number {
   	const { positionals } = parse(rest, {});
   	if (positionals.length !== 1) throw new CliUsageError("show <ref>");
   	const id = resolveId(mindful, positionals[0]);
   	const { scheme } = resolveActiveScheme(root, env);
   	const node = mindful.get(id);
   	const ansi = spriteToAnsi(mindful.sprite(id, scheme));
   	out(formatShow(node, ansi, mindful.related(id)));
   	return 0;
   }
   ```
4. Change `runCli`'s signature and the two affected `case` calls, and add `ConfigError` to the domain-error catch:
   ```ts
   export function runCli(
   	argv: string[],
   	mindful: Mindful,
   	root: string,
   	env: NodeJS.ProcessEnv,
   	out: Sink,
   	err: Sink,
   ): number {
   	try {
   		const [command, ...rest] = argv;
   		switch (command) {
   			case "add":
   				return cmdAdd(mindful, rest, out, root, env);
   			case "list":
   				return cmdList(mindful, rest, out);
   			case "show":
   				return cmdShow(mindful, rest, out, root, env);
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
   	} catch (e) {
   		if (e instanceof CliUsageError) {
   			err(`${e.message}\n\n${USAGE}\n`);
   			return 2;
   		}
   		if (e instanceof NodesError || e instanceof CliError || e instanceof ConfigError) {
   			err(`error: ${(e as Error).message}\n`);
   			return 1;
   		}
   		throw e;
   	}
   }
   ```

- [ ] **Step 5: Update `src/bin.ts`**

Pass the already-computed `root` and `process.env` into `runCli`:

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
	root,
	process.env,
	(s) => {
		process.stdout.write(s);
	},
	(s) => {
		process.stderr.write(s);
	},
);
process.exitCode = code;
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `rtk npm test -- cli`
Expected: PASS — migrated existing tests plus the two new rendering tests.

- [ ] **Step 7: Run the full gate**

Run: `rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`
Expected: all pass. Fix any biome diffs with `rtk npx @biomejs/biome check --write src/cli.ts src/bin.ts tests/cli.test.ts` and re-run.

- [ ] **Step 8: Commit**

```bash
rtk git add src/cli.ts src/bin.ts tests/cli.test.ts
rtk git commit -m "feat(cli): thread active scheme into add/show; runCli takes root+env"
```

---

### Task 4: The `scheme` command (`list` / `set` / `show`)

**Files:**
- Modify: `src/cli.ts`
- Test: `tests/cli.test.ts`

**Interfaces:**
- Consumes: `resolveActiveScheme`, `writeConfig`, `readConfig` from `src/config.ts`; `getScheme`, `schemeNames`, `DEFAULT_SCHEME_NAME` from `src/schemes.ts`; the existing `CliError`/`CliUsageError`/`parse` helpers and the `runCli` signature from Task 3.
- Produces: a top-level `scheme` command dispatching `list`/`set`/`show`; `CliUsageError` carries an optional per-error usage string so scheme errors print `SCHEME_USAGE`.

- [ ] **Step 1: Write the failing tests**

Add the `node:fs`/config imports needed by the new tests to the top of `tests/cli.test.ts` (merge into existing import lines; biome will sort):
```ts
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { readConfig } from "../src/config.js";
```

Append a new `describe` block:

```ts
describe("runCli — scheme command", () => {
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
		runCli(
			argv,
			m,
			root,
			{},
			(s) => out.push(s),
			(s) => err.push(s),
		);
	const runEnv = (env: NodeJS.ProcessEnv, ...argv: string[]): number =>
		runCli(
			argv,
			m,
			root,
			env,
			(s) => out.push(s),
			(s) => err.push(s),
		);
	const stdout = () => out.join("");
	const stderr = () => err.join("");

	it("scheme list marks active+default with no config (exact lines)", () => {
		expect(run("scheme", "list")).toBe(0);
		expect(stdout()).toBe(
			"chiptune-16  (active, default)\ngameboy\ndawnbringer-16\nmonochrome\nnord\nsolarized\n",
		);
	});

	it("after set, list moves the active marker and keeps default tagged", () => {
		expect(run("scheme", "set", "gameboy")).toBe(0);
		out.length = 0;
		expect(run("scheme", "list")).toBe(0);
		const s = stdout();
		expect(s).toContain("chiptune-16  (default)\n");
		expect(s).toContain("gameboy  (active)\n");
	});

	it("scheme set persists to config.yaml and prints 'configured'", () => {
		expect(run("scheme", "set", "nord")).toBe(0);
		expect(stdout()).toBe("configured scheme: nord\n");
		expect(readConfig(root)).toEqual({ scheme: "nord" });
	});

	it("scheme set notes an active MINDFUL_SCHEME override", () => {
		expect(runEnv({ MINDFUL_SCHEME: "gameboy" }, "scheme", "set", "nord")).toBe(0);
		expect(stdout()).toBe("configured scheme: nord\nnote: MINDFUL_SCHEME=gameboy currently overrides config.yaml\n");
	});

	it("scheme set <bogus> → exit 1 and no file written", () => {
		expect(run("scheme", "set", "bogus")).toBe(1);
		expect(stderr()).toContain("error:");
		expect(existsSync(join(root, "config.yaml"))).toBe(false);
	});

	it("scheme show reports name + source for each precedence", () => {
		expect(run("scheme", "show")).toBe(0);
		expect(stdout()).toBe("chiptune-16  (source: default)\n");
		expect(run("scheme", "set", "nord")).toBe(0);
		out.length = 0;
		expect(run("scheme", "show")).toBe(0);
		expect(stdout()).toBe("nord  (source: config.yaml)\n");
		out.length = 0;
		expect(runEnv({ MINDFUL_SCHEME: "gameboy" }, "scheme", "show")).toBe(0);
		expect(stdout()).toBe("gameboy  (source: MINDFUL_SCHEME)\n");
	});

	it("scheme list fails (exit 1) when MINDFUL_SCHEME names an unknown scheme", () => {
		expect(runEnv({ MINDFUL_SCHEME: "bogus" }, "scheme", "list")).toBe(1);
		expect(stderr()).toContain("error:");
	});

	it("bare scheme and unknown subcommand → exit 2 with scheme usage", () => {
		expect(run("scheme")).toBe(2);
		expect(run("scheme", "bogus")).toBe(2);
		expect(stderr()).toContain("mindful scheme <list|set|show>");
	});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk npm test -- cli`
Expected: FAIL — `scheme` is an unknown command (exit 2 with the generic usage), so the scheme-specific assertions fail.

- [ ] **Step 3: Give `CliUsageError` an optional per-error usage string**

In `src/cli.ts`, replace the `CliUsageError` class declaration and the usage-error branch of the `runCli` catch so scheme errors can carry `SCHEME_USAGE`:

```ts
class CliUsageError extends Error {
	readonly usage?: string;
	constructor(message: string, usage?: string) {
		super(message);
		this.usage = usage;
	}
}
```

In the `runCli` catch, change the `CliUsageError` branch to prefer the per-error usage:

```ts
		if (e instanceof CliUsageError) {
			err(`${e.message}\n\n${e.usage ?? USAGE}\n`);
			return 2;
		}
```

- [ ] **Step 4: Add the scheme command implementation**

In `src/cli.ts`:

1. Extend the imports (this adds `writeConfig` to Task 3's `./config.js` import line and adds the `./schemes.js` line; biome will sort):
   ```ts
   import { ConfigError, resolveActiveScheme, writeConfig } from "./config.js";
   import { DEFAULT_SCHEME_NAME, getScheme, schemeNames } from "./schemes.js";
   ```

2. Add the top-level usage line. Change the `USAGE` constant's command list to include `scheme`:
   ```ts
   const USAGE = `usage: mindful <command> [args]

   commands:
     add <title> [--body <text>] [--tag <name>]...
     show <ref>
     list
     search <query> [--limit <n>]
     edit <ref> [--title <text>] [--body <text>]
     delete <ref>
     tag <ref> <name>
     scheme <list|set|show>`;
   ```

3. Add the `SCHEME_USAGE` constant near `USAGE`:
   ```ts
   const SCHEME_USAGE = `usage: mindful scheme <list|set|show>

     scheme list            list built-in colorschemes (active marked)
     scheme set <name>      persist <name> as the configured scheme
     scheme show            print the active scheme and its source`;
   ```

4. Add the command functions (place them with the other `cmd*` functions):
   ```ts
   function cmdSchemeList(rest: string[], out: Sink, root: string, env: NodeJS.ProcessEnv): number {
   	const { positionals } = parse(rest, {});
   	if (positionals.length !== 0) throw new CliUsageError("scheme list takes no arguments", SCHEME_USAGE);
   	const active = resolveActiveScheme(root, env).name;
   	const lines = schemeNames().map((name) => {
   		const tags: string[] = [];
   		if (name === active) tags.push("active");
   		if (name === DEFAULT_SCHEME_NAME) tags.push("default");
   		return tags.length === 0 ? name : `${name}  (${tags.join(", ")})`;
   	});
   	out(`${lines.join("\n")}\n`);
   	return 0;
   }

   function cmdSchemeSet(rest: string[], out: Sink, root: string, env: NodeJS.ProcessEnv): number {
   	const { positionals } = parse(rest, {});
   	if (positionals.length !== 1) throw new CliUsageError("scheme set <name>", SCHEME_USAGE);
   	const name = positionals[0];
   	try {
   		getScheme(name);
   	} catch {
   		throw new CliError(`unknown scheme ${JSON.stringify(name)}`);
   	}
   	writeConfig(root, { scheme: name });
   	let msg = `configured scheme: ${name}\n`;
   	const envName = env.MINDFUL_SCHEME;
   	if (envName !== undefined && envName !== "") {
   		msg += `note: MINDFUL_SCHEME=${envName} currently overrides config.yaml\n`;
   	}
   	out(msg);
   	return 0;
   }

   function cmdSchemeShow(rest: string[], out: Sink, root: string, env: NodeJS.ProcessEnv): number {
   	const { positionals } = parse(rest, {});
   	if (positionals.length !== 0) throw new CliUsageError("scheme show takes no arguments", SCHEME_USAGE);
   	const { name, source } = resolveActiveScheme(root, env);
   	const label = source === "env" ? "MINDFUL_SCHEME" : source === "config" ? "config.yaml" : "default";
   	out(`${name}  (source: ${label})\n`);
   	return 0;
   }

   function cmdScheme(rest: string[], out: Sink, root: string, env: NodeJS.ProcessEnv): number {
   	const [sub, ...subRest] = rest;
   	switch (sub) {
   		case "list":
   			return cmdSchemeList(subRest, out, root, env);
   		case "set":
   			return cmdSchemeSet(subRest, out, root, env);
   		case "show":
   			return cmdSchemeShow(subRest, out, root, env);
   		default:
   			throw new CliUsageError(
   				sub === undefined ? "scheme requires a subcommand" : `unknown scheme subcommand ${JSON.stringify(sub)}`,
   				SCHEME_USAGE,
   			);
   	}
   }
   ```

5. Add the dispatch case in `runCli`'s switch (alongside the others):
   ```ts
   			case "scheme":
   				return cmdScheme(rest, out, root, env);
   ```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `rtk npm test -- cli`
Expected: PASS — all scheme-command tests plus the previously-green suite.

- [ ] **Step 6: Run the full gate**

Run: `rtk npm test && rtk npm run typecheck && rtk npm run check && rtk npm run build`
Expected: all pass. Fix any biome diffs with `rtk npx @biomejs/biome check --write src/cli.ts tests/cli.test.ts` and re-run.

- [ ] **Step 7: Manual smoke test against the built binary**

```bash
D="$(mktemp -d)"
MINDFUL_HOME="$D" rtk node dist/bin.js add "first thought"
MINDFUL_HOME="$D" rtk node dist/bin.js scheme list
MINDFUL_HOME="$D" rtk node dist/bin.js scheme set gameboy
MINDFUL_HOME="$D" rtk node dist/bin.js scheme show
MINDFUL_SCHEME=monochrome MINDFUL_HOME="$D" rtk node dist/bin.js scheme show
```
Expected: `add` prints `added thought:…` + a sprite; `scheme list` shows six rows with `chiptune-16  (active, default)`; `scheme set gameboy` prints `configured scheme: gameboy`; `scheme show` prints `gameboy  (source: config.yaml)`; the env-prefixed `scheme show` prints `monochrome  (source: MINDFUL_SCHEME)`.

- [ ] **Step 8: Commit**

```bash
rtk git add src/cli.ts tests/cli.test.ts
rtk git commit -m "feat(cli): scheme list/set/show command"
```

---

## Self-Review

**1. Spec coverage** (against `2026-06-24-mindful-v6-sp6-scheme-storage-design.md`):
- §3 `schemes.ts` (catalog, `DEFAULT_SCHEME_NAME`, `schemeNames`, `getScheme` defensive copy) → Task 1.
- §3 `config.ts` (`MindfulConfig`, `ConfigError`, `readConfig` strict validation, `writeConfig`, `resolveActiveScheme` precedence) → Task 2.
- §3 `runCli(argv, mindful, root, env, out, err)` + `add`/`show` threading + `ConfigError` catch → Task 3.
- §3 `bin.ts` passthrough → Task 3 Step 5.
- §3 barrel exports → Task 1 Step 5 + Task 2 Step 5 (`Colorscheme` already exported, no change).
- §4 six canonical palettes (hex pinned) → Task 1 Step 3.
- §5 command surface + exact output formats (`list` lines, `configured scheme:` + override note, `show` source labels, `SCHEME_USAGE`) → Task 4.
- §6 render with active scheme → Task 3 Step 4 (resolve before capture) + render-threading test.
- §7 error model (unknown scheme exit 1; malformed config exit 1 and fails `add`/`show`; unreadable config becomes `ConfigError`; bare/unknown sub exit 2) → Tasks 2–4 + tests.
- §8 full test plan (schemes/config/cli, exact `list` lines, unknown-env `list` exit 1, no-file-on-bogus-set, render-differs probe, malformed-config `show`, malformed-config `add` atomicity) → Tasks 1, 2, 4, 3 respectively.
- Gate unchanged → every task Step 6/7.

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to" placeholders; every code and test step carries complete code; all hex values are literal.

**3. Type consistency:** `runCli(argv, mindful, root, env, out, err)` is used identically in `bin.ts`, both migrated `run` helpers, and both new `runEnv`/`run` helpers. `resolveActiveScheme` returns `{ name, scheme, source }` consistently in Task 2 (definition), Task 3 (`{ scheme }` destructure), and Task 4 (`{ name, source }` and `.name`). `getScheme`/`schemeNames`/`DEFAULT_SCHEME_NAME`, `ConfigError`/`writeConfig`/`readConfig`/`MindfulConfig` names match across definition, barrel, and call-sites. Source labels (`env`/`config`/`default`) map to `MINDFUL_SCHEME`/`config.yaml`/`default` in exactly one place (`cmdSchemeShow`).
