import { createHash } from "node:crypto";
import {
  type Dirent,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative } from "node:path";

export const SNAPSHOT_SCHEMA_VERSION = 1;
export const SNAPSHOT_LANG = "ts";

export function snapshotPath(root: string): string {
  return join(root, ".nodes-index", "snapshot.ts.json");
}

export function hashBytes(data: Buffer | Uint8Array): string {
  return createHash("sha256").update(data).digest("hex");
}

export interface CorpusFile {
  readonly path: string; // root-relative POSIX
  readonly data: Buffer;
  readonly sha256: string;
}

/** Root-relative POSIX path (forward slashes on every platform), the cross-language form. */
function relPosix(root: string, full: string): string {
  return relative(root, full).split(/[\\/]/).join("/");
}

/** Byte-level walk: read each .md file's bytes once and hash them. Skips the private
 * `.nodes-index` tree, symlinks, and non-files. Sorted by root-relative POSIX path so the
 * order matches Python's `sorted(root.rglob("*.md"))`. */
export function iterCorpusFiles(root: string): CorpusFile[] {
  const files: CorpusFile[] = [];
  const walk = (dir: string): void => {
    if (!existsSync(dir)) return;
    let entries: Dirent[];
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = join(dir, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) {
        if (relPosix(root, full) === ".nodes-index") continue;
        walk(full);
      } else if (entry.isFile() && entry.name.endsWith(".md")) {
        const data = readFileSync(full);
        files.push({ path: relPosix(root, full), data, sha256: hashBytes(data) });
      }
    }
  };
  walk(root);
  files.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  return files;
}

export interface ManifestEntry {
  readonly path: string;
  readonly sha256: string;
  readonly uid: string;
}

/** Write JSON atomically (tmp + rename). Rejects any non-finite number — JS `JSON.stringify`
 * silently emits `null` for NaN/Infinity, so a replacer enforces the rejection (parity with
 * Python's `json.dumps(..., allow_nan=False)`). Throws before any write, so no partial file. */
export function writeJsonAtomic(path: string, obj: unknown): void {
  const payload = JSON.stringify(obj, (_key, value) => {
    if (typeof value === "number" && !Number.isFinite(value)) {
      throw new RangeError("cannot serialize non-finite number to JSON");
    }
    return value;
  });
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, payload, "utf-8");
  renameSync(tmp, path);
}

/** Read + parse JSON. Returns `null` only for a genuinely-absent path. A directory, a broken
 * symlink, or invalid JSON throws (JS `JSON.parse` already rejects the `NaN`/`Infinity`
 * constants, so Python's explicit `parse_constant` guard is free here). */
export function readJson(path: string): unknown {
  let raw: string;
  try {
    raw = readFileSync(path, "utf-8");
  } catch (e) {
    const err = e as NodeJS.ErrnoException;
    if (err.code === "ENOENT") {
      try {
        lstatSync(path); // a broken symlink reads ENOENT but lstats fine
      } catch {
        return null; // genuinely absent
      }
      throw err; // path exists as a (broken) symlink
    }
    throw err; // EISDIR and anything else
  }
  return JSON.parse(raw);
}
