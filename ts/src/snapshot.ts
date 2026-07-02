import { createHash } from "node:crypto";
import {
  type Dirent,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative } from "node:path";
import { NodeId } from "./ids.js";
import { SearchIndex } from "./search.js";
import { VectorIndex } from "./similarity.js";
import { Index } from "./structural-index.js";

export const SNAPSHOT_SCHEMA_VERSION = 1;
export const SNAPSHOT_LANG = "ts";

const SHA256_RE = /^[0-9a-f]{64}$/;
const SNAPSHOT_KEYS = ["version", "lang", "manifest", "structural", "search", "vectors"];
const MANIFEST_ROW_KEYS = ["path", "sha256", "uid"];

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

export interface CorpusFileStat {
  readonly path: string;
  readonly mtimeMs: number;
  readonly size: number;
}

export interface CorpusFingerprint {
  readonly files: readonly CorpusFileStat[];
}

interface WalkedCorpusPath {
  readonly path: string;
  readonly fullPath: string;
}

/** Root-relative POSIX path (forward slashes on every platform), the cross-language form. */
function relPosix(root: string, full: string): string {
  return relative(root, full).split(/[\\/]/).join("/");
}

function listCorpusMarkdownPaths(root: string): WalkedCorpusPath[] {
  const files: WalkedCorpusPath[] = [];
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
        files.push({ path: relPosix(root, full), fullPath: full });
      }
    }
  };
  walk(root);
  files.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  return files;
}

/** Byte-level walk: read each .md file's bytes once and hash them. Skips the private
 * `.nodes-index` tree, symlinks, and non-files. Sorted by root-relative POSIX path so the
 * order matches Python's `sorted(root.rglob("*.md"))`. */
export function iterCorpusFiles(root: string): CorpusFile[] {
  return listCorpusMarkdownPaths(root).map(({ path, fullPath }) => {
    const data = readFileSync(fullPath);
    return { path, data, sha256: hashBytes(data) };
  });
}

/** Stat-level walk over the same corpus file set as `iterCorpusFiles`. Does not read file bodies. */
export function listCorpusFileStats(root: string): CorpusFileStat[] {
  return listCorpusMarkdownPaths(root).map(({ path, fullPath }) => {
    const stat = statSync(fullPath);
    return { path, mtimeMs: stat.mtimeMs, size: stat.size };
  });
}

/** Cheap external-change fingerprint for resident consumers. Not a content-identity hash. */
export function readCorpusFingerprint(root: string): CorpusFingerprint {
  return { files: listCorpusFileStats(root) };
}

export function sameCorpusFingerprint(a: CorpusFingerprint, b: CorpusFingerprint): boolean {
  if (a.files.length !== b.files.length) return false;
  for (let i = 0; i < a.files.length; i++) {
    const left = a.files[i];
    const right = b.files[i];
    if (left.path !== right.path || left.mtimeMs !== right.mtimeMs || left.size !== right.size) return false;
  }
  return true;
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

export interface Snapshot {
  manifest: ManifestEntry[];
  index: Index;
  searchIndex: SearchIndex;
  vectorIndex: VectorIndex | null;
}

export function pathForNodeId(nodeId: string): string {
  const nid = NodeId.parse(nodeId);
  return `${nid.kind}/${nid.slug.replace(/:/g, "__")}.md`;
}

export function writeSnapshot(
  root: string,
  manifest: ManifestEntry[],
  index: Index,
  searchIndex: SearchIndex,
  vectorIndex: VectorIndex | undefined,
): void {
  const doc = {
    version: SNAPSHOT_SCHEMA_VERSION,
    lang: SNAPSHOT_LANG,
    manifest: manifest.map((m) => ({ path: m.path, sha256: m.sha256, uid: m.uid })),
    structural: index.toDict(),
    search: searchIndex.toDict(),
    vectors: vectorIndex !== undefined ? vectorIndex.toDict() : null,
  };
  writeJsonAtomic(snapshotPath(root), doc);
}

function validateManifestPath(path: string): void {
  const parts = path.split("/");
  if (
    !path ||
    path.startsWith("/") ||
    path.includes("\\") ||
    path.endsWith("/") ||
    !path.endsWith(".md") ||
    parts[0] === ".nodes-index" ||
    parts.some((part) => part === "" || part === "." || part === "..")
  ) {
    throw new Error("snapshot manifest row path must be a root-relative POSIX .md path");
  }
}

function parseManifest(raw: unknown): ManifestEntry[] {
  if (!Array.isArray(raw)) throw new Error("snapshot manifest is not an array");
  const entries: ManifestEntry[] = [];
  for (const e of raw) {
    if (typeof e !== "object" || e === null) throw new Error("snapshot manifest row is not an object");
    const row = e as Record<string, unknown>;
    for (const key of MANIFEST_ROW_KEYS) {
      if (!(key in row)) throw new Error(`snapshot manifest row missing ${key}`);
    }
    const { path, sha256, uid } = row;
    if (typeof path !== "string") throw new Error("snapshot manifest row path must be a string");
    validateManifestPath(path);
    if (typeof sha256 !== "string") throw new Error("snapshot manifest row sha256 must be a string");
    if (!SHA256_RE.test(sha256)) throw new Error("snapshot manifest row sha256 must be 64 lowercase hex chars");
    if (typeof uid !== "string") throw new Error("snapshot manifest row uid must be a string");
    entries.push({ path, sha256, uid });
  }
  if (new Set(entries.map((m) => m.uid)).size !== entries.length) throw new Error("snapshot manifest: duplicate uid");
  if (new Set(entries.map((m) => m.path)).size !== entries.length) throw new Error("snapshot manifest: duplicate path");
  return entries;
}

function setsEqual(a: Set<string>, b: Set<string>): boolean {
  return a.size === b.size && [...a].every((x) => b.has(x));
}

function mapsEqual(a: Map<string, string>, b: Map<string, string>): boolean {
  if (a.size !== b.size) return false;
  for (const [k, v] of a) if (b.get(k) !== v) return false;
  return true;
}

/** Reads and validates ONLY the cache file. Returns null for any cache problem (missing file,
 * invalid JSON, version/lang mismatch, integrity failure, embedder-configured vector mismatch).
 * Never parses corpus files, so it can never raise a corpus error — any throw here is a cache
 * problem and resolves to a silent full rebuild upstream. */
export function loadSnapshot(root: string, embedderNamespace: string | null): Snapshot | null {
  try {
    const doc = readJson(snapshotPath(root));
    if (doc === null) return null;
    if (typeof doc !== "object") return null;
    const d = doc as Record<string, unknown>;
    for (const key of SNAPSHOT_KEYS) {
      if (!(key in d)) throw new Error(`snapshot document missing ${key}`);
    }
    if (d.version !== SNAPSHOT_SCHEMA_VERSION || d.lang !== SNAPSHOT_LANG) return null;

    const manifest = parseManifest(d.manifest);
    const manifestUids = new Set(manifest.map((m) => m.uid));

    const index = Index.fromDict(d.structural);
    if (!setsEqual(new Set(index.byUid.keys()), manifestUids)) return null;
    const expectedIds = new Map<string, string>();
    for (const [uid, entry] of index.byUid) expectedIds.set(uid, entry.id);
    for (const m of manifest) {
      if (m.path !== pathForNodeId(expectedIds.get(m.uid) as string)) {
        throw new Error("snapshot manifest path does not match structural id");
      }
    }

    const searchIndex = SearchIndex.fromDict(d.search);
    if (!setsEqual(new Set(searchIndex.lengths.keys()), manifestUids)) return null;
    if (!mapsEqual(searchIndex.idByUid, expectedIds)) return null;

    let vectorIndex: VectorIndex | null = null;
    if (embedderNamespace !== null) {
      const vec = d.vectors;
      if (typeof vec !== "object" || vec === null) return null;
      if ((vec as Record<string, unknown>).namespace !== embedderNamespace) return null;
      vectorIndex = VectorIndex.fromDict(vec);
      if (!setsEqual(new Set(vectorIndex.vectors.keys()), manifestUids)) return null;
      if (!mapsEqual(vectorIndex.idByUid, expectedIds)) return null;
    }

    return { manifest, index, searchIndex, vectorIndex };
  } catch (e) {
    // loadSnapshot only ever reads the cache file, so any thrown Error is a cache problem
    // (absent/locked file, malformed JSON, failed integrity check) -> rebuild. This is the
    // closest faithful mirror of Python's `except (OSError, ValueError)`: every cache-unusable
    // signal here surfaces as an Error subclass, while JS's error taxonomy gives no class-based
    // way to separate them further. A non-Error throw is not a cache signal — rethrow it.
    if (!(e instanceof Error)) throw e;
    return null;
  }
}
