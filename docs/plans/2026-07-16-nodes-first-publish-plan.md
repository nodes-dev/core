# Nodes First Publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the public home (`nodes-dev/core`) and publish the first lockstep release — `nodes-core` 0.1.0 on PyPI and `@nodes-dev/core` 0.1.0 on npm — from tag `core/v0.1.0` through a trusted-OIDC pipeline, per
`~/d/nodes/docs/designs/2026-07-16-nodes-first-publish-design.md`.

**Architecture:** Tasks 1–4 are repository file changes (license, manifests, lockfile tracking, verification scripts, two workflows) on an isolated branch, merged to main. Tasks 5–7 are operational: push the repo to GitHub, set up registries (with owner-interactive steps), rehearse the pipeline, and cut `core/v0.1.0`.

**Tech Stack:** GitHub Actions (SHA-pinned), uv/hatchling, npm 11, `pypa/gh-action-pypi-publish`, `gh` CLI.

## Global Constraints

- Before Task 1, the execution controller MUST use `superpowers:using-git-worktrees` to create or verify an isolated checkout on branch `feat/first-publish` off `main`. The plan never creates the branch or assumes the primary `~/d/nodes` checkout is the active workspace.
- Every local command resolves the active checkout with `ROOT="$(git rev-parse --show-toplevel)"` on the same command line. Never hardcode `cd ~/d/nodes`: execution may be inside a linked worktree, and environment variables do not persist across separate tool calls.
- All local git commands through `rtk` (`rtk git …`); npm through `rtk npm …`; uv through `rtk uv …`. Exception, on purpose: checks that capture command output use raw `git` — `rtk git status` rewrites empty output to `ok`, which breaks emptiness tests. (Workflow YAML uses plain commands; CI has no `rtk`.)
- Stage explicitly by path. Never `git add -A`. Never stage `python/dist/` (NOT gitignored — remove after every build) or `*.tgz` files.
- No AI-attribution trailers or footers on commits.
- ALL SIX gates before EVERY commit — from `ts/`: `rtk npm test`, `rtk npm run typecheck`, `rtk npm run check`; from `python/`: `rtk uv run --frozen pytest -q`, `rtk uv run --frozen ruff check .`, `rtk uv run --frozen pyright src`.
- Fixtures untouched: `FIXSTAT="$(git status --porcelain -- fixtures/)" && test -z "$FIXSTAT" && echo "fixtures clean"` must print `fixtures clean` before every commit.
- Fail-closed verification: run checks line-at-a-time; for grep no-match assertions use `test $? -eq 1` (exit 1 = no match; exit ≥ 2 = grep itself failed).
- Every workflow `uses:` is pinned to a full 40-character commit SHA with the release tag in a trailing comment (`# vX.Y.Z`). Never a tag or branch ref.
- Workflows default to `permissions: contents: read`; only the two publish jobs add `id-token: write`.
- The release version is **0.1.0** everywhere; the tag is **`core/v0.1.0`**; repo URLs are `https://github.com/nodes-dev/core`.
- Steps marked **[OWNER]** need the human project owner (browser/auth). The executor STOPS at each one, notifies the owner, and waits — never skips or simulates them.
- On any conflict, `docs/designs/2026-07-16-nodes-first-publish-design.md` governs.

## File Structure

- `LICENSE`, `python/LICENSE`, `ts/LICENSE` — identical MIT text (root is canonical; packaging tools can't reach above their package dir).
- `python/README.md` — new PyPI landing page.
- `python/pyproject.toml`, `ts/package.json` — publish metadata completion.
- `.gitignore` — stop ignoring `uv.lock`; `python/uv.lock` becomes tracked.
- `.github/scripts/verify_python_artifacts.py` — wheel + sdist content/metadata assertions.
- `.github/scripts/verify_npm_tarball.py` — npm tarball content assertions.
- `.github/scripts/pypi_upload_check.py` — hash-verified PyPI pre/post-upload check.
- `.github/scripts/smoke_install_python.sh` — installs wheel and sdist into scratch envs, runs namespace checks.
- `.github/scripts/smoke_install_npm.sh` — installs tarball into a scratch project, imports it.
- `.github/workflows/ci.yml` — six gates, matrixed (Python 3.11/3.13, Node 20/24), also `workflow_call`-able.
- `.github/workflows/release.yml` — tag-driven build/verify/publish pipeline; plain `workflow_dispatch` = rehearsal.

---

### Task 1: License and publish metadata

**Files:**
- Create: `LICENSE`, `python/LICENSE`, `ts/LICENSE`, `python/README.md`
- Modify: `python/pyproject.toml`, `ts/package.json`, `.gitignore`

**Interfaces:**
- Produces: wheel METADATA carries `License-Expression: MIT` and `.dist-info/licenses/LICENSE`; sdist and npm tarball each carry `LICENSE` and `README.md`. Task 2's verification scripts assert these exact facts. `python/uv.lock` becomes tracked (CI's `uv sync --frozen` in Task 3 requires it).

- [ ] **Step 1: Create the MIT license (three identical copies)**

Write this exact text to `LICENSE`, then copy it:

```text
MIT License

Copyright (c) 2026 Keith Hughitt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

```bash
ROOT="$(git rev-parse --show-toplevel)" && cp "$ROOT/LICENSE" "$ROOT/python/LICENSE" && cp "$ROOT/LICENSE" "$ROOT/ts/LICENSE"
ROOT="$(git rev-parse --show-toplevel)" && cmp "$ROOT/LICENSE" "$ROOT/python/LICENSE" && cmp "$ROOT/LICENSE" "$ROOT/ts/LICENSE" && echo "license copies identical"
```

Expected: `license copies identical`.

- [ ] **Step 2: Create `python/README.md`**

```markdown
# nodes-core

Nodes core: a problem-agnostic knowledge substrate.

`nodes-core` is the Python implementation of the Nodes kernel — a portable
corpus of plain-text nodes with typed relations, structural shapes, and
derived full-text-search and similarity indexes. A TypeScript implementation
([`@nodes-dev/core`](https://www.npmjs.com/package/@nodes-dev/core)) passes
the same cross-language conformance fixtures.

## Install

```
pip install nodes-core
```

## Use

```python
import nodes.core
```

The `nodes` namespace is a PEP 420 native namespace package; `nodes-core`
ships exactly the `nodes.core` subpackage.

## Documentation

The language-neutral format and behavior specification, both
implementations, and the shared conformance fixtures live at
<https://github.com/nodes-dev/core>.

## License

MIT
```

- [ ] **Step 3: Complete `python/pyproject.toml` `[project]` metadata**

Replace the `[project]` table (everything above `[build-system]`) with:

```toml
[project]
name = "nodes-core"
import-names = ["nodes.core"]
import-namespaces = ["nodes"]
version = "0.1.0"
description = "Nodes core: a problem-agnostic knowledge substrate"
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "Keith Hughitt", email = "keith.hughitt@gmail.com" }]
requires-python = ">=3.11"
classifiers = ["Typing :: Typed"]
dependencies = [
  "pydantic>=2.0",
  "pyyaml>=6.0.3",
]

[project.urls]
Homepage = "https://github.com/nodes-dev/core"
Repository = "https://github.com/nodes-dev/core"
Issues = "https://github.com/nodes-dev/core/issues"
```

Leave every other table (`[build-system]`, `[tool.*]`, `[dependency-groups]`) exactly as it is.

- [ ] **Step 4: Complete `ts/package.json`**

Replace the whole file with:

```json
{
  "name": "@nodes-dev/core",
  "version": "0.1.0",
  "description": "Nodes core: a problem-agnostic knowledge substrate (TypeScript)",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/nodes-dev/core.git",
    "directory": "ts"
  },
  "homepage": "https://github.com/nodes-dev/core",
  "bugs": { "url": "https://github.com/nodes-dev/core/issues" },
  "type": "module",
  "engines": { "node": ">=20" },
  "packageManager": "npm@11.11.0",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "default": "./dist/index.js"
    }
  },
  "files": ["dist"],
  "publishConfig": { "access": "public" },
  "scripts": {
    "build": "tsc -p tsconfig.build.json",
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "check": "biome check ."
  },
  "dependencies": {
    "yaml": "^2.5.0",
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

- [ ] **Step 5: Track `python/uv.lock`**

Delete the `uv.lock` line from `.gitignore` (line reads exactly `uv.lock`), then:

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/python" && rtk uv lock
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT" && git check-ignore python/uv.lock; test $? -eq 1 && echo "uv.lock no longer ignored"
```

Expected: `uv.lock no longer ignored`. (`git check-ignore` exits 1 when the path is not ignored.)

- [ ] **Step 6: Verify the wheel carries the new metadata**

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/python" && rm -rf dist && rtk uv build
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/python" && python3 - <<'EOF'
import glob
import zipfile

wheels = glob.glob("dist/nodes_core-0.1.0-py3-none-any.whl")
assert len(wheels) == 1, wheels
with zipfile.ZipFile(wheels[0]) as z:
    names = z.namelist()
    meta = z.read("nodes_core-0.1.0.dist-info/METADATA").decode()
assert "License-Expression: MIT" in meta, "License-Expression missing"
assert "nodes_core-0.1.0.dist-info/licenses/LICENSE" in names, "LICENSE missing from wheel"
print("wheel metadata ok")
EOF
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/python" && rm -rf dist && test ! -e dist && echo "dist not left behind"
```

Expected: `wheel metadata ok` then `dist not left behind`.

- [ ] **Step 7: Verify the npm tarball carries LICENSE**

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/ts" && rm -rf dist && rtk npm run build
ROOT="$(git rev-parse --show-toplevel)" && S="$(mktemp -d)" && cd "$ROOT/ts" && rtk npm pack --dry-run --json --pack-destination "$S" > "$S/pack.json"; python3 - "$S/pack.json" <<'EOF'
import json
import sys

files = {f["path"] for f in json.load(open(sys.argv[1]))[0]["files"]}
assert "LICENSE" in files, "LICENSE missing from pack"
assert "dist/index.js" in files, "dist/index.js missing from pack"
print("npm pack contents ok")
EOF
```

Expected: `npm pack contents ok`.

- [ ] **Step 8: Run all six gates + fixtures check**

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/python" && rtk uv run --frozen pytest -q && rtk uv run --frozen ruff check . && rtk uv run --frozen pyright src
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/ts" && rtk npm test && rtk npm run typecheck && rtk npm run check
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT" && FIXSTAT="$(git status --porcelain -- fixtures/)" && test -z "$FIXSTAT" && echo "fixtures clean"
```

Expected: all six gates PASS; `fixtures clean`.

- [ ] **Step 9: Commit**

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT" && rtk git add LICENSE python/LICENSE ts/LICENSE python/README.md python/pyproject.toml python/uv.lock ts/package.json .gitignore && rtk git commit -m "chore: add MIT license and publish metadata"
```

---

### Task 2: Artifact verification scripts

**Files:**
- Create: `.github/scripts/verify_python_artifacts.py`
- Create: `.github/scripts/verify_npm_tarball.py`
- Create: `.github/scripts/pypi_upload_check.py`
- Create: `.github/scripts/smoke_install_python.sh`
- Create: `.github/scripts/smoke_install_npm.sh`

**Interfaces:**
- Consumes: Task 1's metadata (`License-Expression: MIT`, LICENSE files in artifacts).
- Produces (Task 4's release workflow and Task 6's bootstrap call these exact CLIs):
  - `python3 .github/scripts/verify_python_artifacts.py <dist-dir>` — exits 0 printing `python artifacts ok`.
  - `python3 .github/scripts/verify_npm_tarball.py <tarball.tgz>` — exits 0 printing `npm tarball ok`.
  - `python3 .github/scripts/pypi_upload_check.py {pre,post} --project <name> --version <v> --dist <dir>` — exits 0 printing `pypi <mode>-check ok …`.
  - `.github/scripts/smoke_install_python.sh <dist-dir>` — exits 0 printing `python install smoke ok`.
  - `.github/scripts/smoke_install_npm.sh <tarball.tgz>` — exits 0 printing `npm import smoke ok`.

- [ ] **Step 1: Write `verify_python_artifacts.py`**

```python
#!/usr/bin/env python3
"""Assert wheel + sdist contents and metadata (first-publish design, 2.4 verify-artifacts)."""

import glob
import os
import sys
import tarfile
import zipfile


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: verify_python_artifacts.py <dist-dir>")
    dist = sys.argv[1]
    entries = sorted(os.listdir(dist))
    wheels = glob.glob(os.path.join(dist, "nodes_core-*-py3-none-any.whl"))
    sdists = glob.glob(os.path.join(dist, "nodes_core-*.tar.gz"))
    if len(entries) != 2 or len(wheels) != 1 or len(sdists) != 1:
        fail(f"expected exactly one wheel and one sdist, found {entries}")

    with zipfile.ZipFile(wheels[0]) as z:
        names = z.namelist()
        if "nodes/core/py.typed" not in names:
            fail("wheel missing nodes/core/py.typed")
        if "nodes/__init__.py" in names:
            fail("wheel contains nodes/__init__.py (breaks the namespace)")
        meta_name = next(n for n in names if n.endswith(".dist-info/METADATA"))
        meta = z.read(meta_name).decode()
        for line in (
            "Import-Name: nodes.core",
            "Import-Namespace: nodes",
            "License-Expression: MIT",
        ):
            if line not in meta:
                fail(f"wheel METADATA missing {line!r}")
        if not any(n.endswith(".dist-info/licenses/LICENSE") for n in names):
            fail("wheel missing dist-info/licenses/LICENSE")

    with tarfile.open(sdists[0]) as t:
        names = t.getnames()
        root = names[0].split("/")[0]
        for required in (
            f"{root}/pyproject.toml",
            f"{root}/README.md",
            f"{root}/LICENSE",
            f"{root}/src/nodes/core/py.typed",
        ):
            if required not in names:
                fail(f"sdist missing {required}")
        if f"{root}/src/nodes/__init__.py" in names:
            fail("sdist contains src/nodes/__init__.py (breaks the namespace)")
        member = t.extractfile(f"{root}/PKG-INFO")
        assert member is not None
        pkg_info = member.read().decode()
        for line in ("Name: nodes-core", "License-Expression: MIT"):
            if line not in pkg_info:
                fail(f"sdist PKG-INFO missing {line!r}")

    print("python artifacts ok")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `verify_npm_tarball.py`**

```python
#!/usr/bin/env python3
"""Assert npm tarball contents (first-publish design, 2.4 verify-artifacts).

dist/vocab/ is explicitly forbidden: the retired vocab compiled outputs
survived in an unclean workstation dist/ once already, and tsc never deletes
stale outputs.
"""

import sys
import tarfile

REQUIRED = {
    "package/package.json",
    "package/README.md",
    "package/LICENSE",
    "package/dist/index.js",
    "package/dist/index.d.ts",
}
ALLOWED_EXACT = {"package/package.json", "package/README.md", "package/LICENSE"}
FORBIDDEN_PREFIXES = ("package/dist/vocab/",)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: verify_npm_tarball.py <tarball.tgz>")
    with tarfile.open(sys.argv[1]) as t:
        names = set(t.getnames())
    missing = REQUIRED - names
    if missing:
        fail(f"tarball missing {sorted(missing)}")
    stray = [n for n in names if n not in ALLOWED_EXACT and not n.startswith("package/dist/")]
    if stray:
        fail(f"tarball contains paths outside the allowed set: {sorted(stray)}")
    retired = [n for n in names if n.startswith(FORBIDDEN_PREFIXES)]
    if retired:
        fail(f"tarball contains retired paths (stale dist/): {sorted(retired)}")
    print("npm tarball ok")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write `pypi_upload_check.py`**

```python
#!/usr/bin/env python3
"""Hash-verified PyPI pre/post-upload check (first-publish design, 3).

pre:  every file PyPI already has for this version must be one of ours with a
      matching SHA-256 (an absent project/version is the expected empty set on
      first publish). Unexpected filenames or digest mismatches fail closed.
post: additionally, every local file must now be present on PyPI.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def local_files(dist: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in sorted(os.listdir(dist)):
        with open(os.path.join(dist, name), "rb") as fh:
            out[name] = hashlib.sha256(fh.read()).hexdigest()
    if len(out) != 2:
        fail(f"expected exactly 2 local distribution files, found {sorted(out)}")
    return out


def remote_files(project: str, version: str) -> dict[str, str]:
    url = f"https://pypi.org/pypi/{project}/{version}/json"
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}
        raise
    return {u["filename"]: u["digests"]["sha256"] for u in data["urls"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["pre", "post"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dist", required=True)
    args = parser.parse_args()

    local = local_files(args.dist)
    remote = remote_files(args.project, args.version)

    unexpected = sorted(set(remote) - set(local))
    if unexpected:
        fail(f"PyPI has files for {args.project} {args.version} that are not ours: {unexpected}")
    mismatched = sorted(n for n in remote if remote[n] != local[n])
    if mismatched:
        fail(f"SHA-256 mismatch against PyPI for: {mismatched}")
    if args.mode == "post":
        absent = sorted(set(local) - set(remote))
        if absent:
            fail(f"files still missing on PyPI after upload: {absent}")

    print(f"pypi {args.mode}-check ok: {len(remote)}/{len(local)} files present and matching")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `smoke_install_python.sh`**

```bash
#!/usr/bin/env bash
# Install wheel and sdist independently into scratch envs; run namespace checks
# (first-publish design, 2.4: installing the sdist proves it rebuilds).
set -euo pipefail

DIST="$1"
for artifact in "$DIST"/nodes_core-*-py3-none-any.whl "$DIST"/nodes_core-*.tar.gz; do
  scratch="$(mktemp -d)"
  uv venv "$scratch/venv" >/dev/null
  uv pip install --python "$scratch/venv/bin/python" "$artifact" >/dev/null
  "$scratch/venv/bin/python" - <<'EOF'
import importlib

import nodes.core

assert nodes.core.__name__ == "nodes.core"
assert getattr(nodes, "__file__", None) is None, "nodes is not a namespace package"
legacy = ".".join(["nodes", "kernel"])
try:
    importlib.import_module(legacy)
except ModuleNotFoundError as exc:
    assert exc.name == legacy, exc.name
else:
    raise SystemExit("legacy import path still importable")
EOF
  echo "smoke ok: $(basename "$artifact")"
  rm -rf "$scratch"
done
echo "python install smoke ok"
```

- [ ] **Step 5: Write `smoke_install_npm.sh`**

```bash
#!/usr/bin/env bash
# Install the tarball into a scratch project and import it
# (first-publish design, 2.4 verify-artifacts).
set -euo pipefail

TARBALL="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
scratch="$(mktemp -d)"
cd "$scratch"
npm init -y >/dev/null
npm install --no-audit --no-fund "$TARBALL" >/dev/null
node --input-type=module -e "
const core = await import('@nodes-dev/core');
const keys = Object.keys(core);
if (keys.length === 0) throw new Error('no exports');
console.log('npm import smoke ok (' + keys.length + ' exports)');
"
cd / && rm -rf "$scratch"
```

Then make both shell scripts executable:

```bash
ROOT="$(git rev-parse --show-toplevel)" && chmod +x "$ROOT/.github/scripts/smoke_install_python.sh" "$ROOT/.github/scripts/smoke_install_npm.sh"
```

- [ ] **Step 6: Red test — the npm guard must reject a stale dist**

Fabricate the historical failure (retired vocab outputs surviving in `dist/`) deterministically:

```bash
ROOT="$(git rev-parse --show-toplevel)" && S="$(mktemp -d)" && cd "$ROOT/ts" && rm -rf dist && rtk npm run build && mkdir -p dist/vocab && echo "// stale" > dist/vocab/kinds.js && rtk npm pack --pack-destination "$S" && python3 "$ROOT/.github/scripts/verify_npm_tarball.py" "$S"/nodes-dev-core-0.1.0.tgz; echo "exit=$?"
```

Expected: `FAIL: tarball contains retired paths (stale dist/): ['package/dist/vocab/kinds.js']` and `exit=1`. Any other outcome is a STOP.

- [ ] **Step 7: Green — clean builds pass all local checks**

```bash
ROOT="$(git rev-parse --show-toplevel)" && S="$(mktemp -d)" && cd "$ROOT/ts" && rm -rf dist && rtk npm run build && rtk npm pack --pack-destination "$S" && python3 "$ROOT/.github/scripts/verify_npm_tarball.py" "$S"/nodes-dev-core-0.1.0.tgz && "$ROOT/.github/scripts/smoke_install_npm.sh" "$S"/nodes-dev-core-0.1.0.tgz
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/python" && rm -rf dist && rtk uv build && python3 "$ROOT/.github/scripts/verify_python_artifacts.py" dist && "$ROOT/.github/scripts/smoke_install_python.sh" dist
```

Expected: `npm tarball ok`, `npm import smoke ok (…)`, `python artifacts ok`, `smoke ok: …` twice, `python install smoke ok`.

- [ ] **Step 8: Red/green the PyPI check against the live index**

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/python" && python3 "$ROOT/.github/scripts/pypi_upload_check.py" pre --project nodes-core --version 0.1.0 --dist dist
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/python" && python3 "$ROOT/.github/scripts/pypi_upload_check.py" post --project nodes-core --version 0.1.0 --dist dist; echo "exit=$?"
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/python" && python3 "$ROOT/.github/scripts/pypi_upload_check.py" pre --project requests --version 2.32.3 --dist dist; echo "exit=$?"
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT/python" && rm -rf dist && test ! -e dist && echo "dist not left behind"
```

Expected, in order: `pypi pre-check ok: 0/2 files present and matching` (project not yet on PyPI = empty set); `FAIL: files still missing on PyPI…` with `exit=1` (post demands presence); `FAIL: PyPI has files … that are not ours` with `exit=1` (foreign files fail closed); `dist not left behind`.

- [ ] **Step 9: Run all six gates + fixtures check**

Same commands as Task 1 Step 8. Expected: all PASS; `fixtures clean`.

- [ ] **Step 10: Commit**

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT" && rtk git add .github/scripts && rtk git commit -m "ci: add release verification scripts"
```

---

### Task 3: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: workflow `ci.yml` with `workflow_call` trigger — Task 4's release workflow invokes it as its `gates` job. Job names `python` and `typescript`.

- [ ] **Step 1: Resolve action SHAs**

For each action, list its release tags and record the **peeled commit SHA** (`^{}` line) of the **latest stable release tag** (highest version, no pre-release suffix):

```bash
git ls-remote --tags https://github.com/actions/checkout | tail -12
git ls-remote --tags https://github.com/actions/setup-node | tail -12
git ls-remote --tags https://github.com/astral-sh/setup-uv | tail -12
```

For each: the annotated tag appears twice — `refs/tags/vX.Y.Z` and `refs/tags/vX.Y.Z^{}`; pin the `^{}` SHA (the commit itself). If a tag has no `^{}` line it is lightweight and its own SHA is the commit. Record `SHA + tag` for: `actions/checkout`, `actions/setup-node`, `astral-sh/setup-uv`. Cross-check each SHA resolves on GitHub before use:

```bash
git ls-remote https://github.com/actions/checkout <sha> | head -1
```

- [ ] **Step 2: Write `.github/workflows/ci.yml`**

Replace each `<SHA:owner/repo>` with the full 40-char SHA from Step 1 and each `# vX.Y.Z` comment with the actual tag:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
  workflow_call:

permissions:
  contents: read

jobs:
  python:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.13"]
    defaults:
      run:
        working-directory: python
    steps:
      - uses: <SHA:actions/checkout> # vX.Y.Z
      - uses: <SHA:astral-sh/setup-uv> # vX.Y.Z
        with:
          python-version: ${{ matrix.python-version }}
      - run: uv sync --frozen
      - run: uv run --frozen pytest -q
      - run: uv run --frozen ruff check .
      - run: uv run --frozen pyright src

  typescript:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        node-version: ["20", "24"]
    defaults:
      run:
        working-directory: ts
    steps:
      - uses: <SHA:actions/checkout> # vX.Y.Z
      - uses: <SHA:actions/setup-node> # vX.Y.Z
        with:
          node-version: ${{ matrix.node-version }}
          cache: npm
          cache-dependency-path: ts/package-lock.json
      - run: npm ci
      - run: npm test
      - run: npm run typecheck
      - run: npm run check
```

In the final file, `uses:` lines read like `uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0` (SHA shown here is an example — use the one you resolved).

- [ ] **Step 3: Validate — YAML parses, everything is SHA-pinned**

```bash
ROOT="$(git rev-parse --show-toplevel)" && python3 -c "import yaml; yaml.safe_load(open('$ROOT/.github/workflows/ci.yml'))" && echo "yaml ok"
ROOT="$(git rev-parse --show-toplevel)" && grep -rn "<SHA:" "$ROOT/.github"; test $? -eq 1 && echo "no unresolved sha markers"
ROOT="$(git rev-parse --show-toplevel)" && UNPINNED="$(grep -En "uses: " "$ROOT/.github/workflows/ci.yml" | grep -Ev "@[0-9a-f]{40} #" || true)" && test -z "$UNPINNED" && echo "all actions sha-pinned"
```

Expected: `yaml ok`, `no unresolved sha markers`, `all actions sha-pinned`. (If `python3 -c` lacks `yaml`, run it as `rtk uv run --frozen python -c …` from `python/` with the path adjusted to `../.github/workflows/ci.yml`.)

- [ ] **Step 4: Run all six gates + fixtures check**

Same commands as Task 1 Step 8. Expected: all PASS; `fixtures clean`.

- [ ] **Step 5: Commit**

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT" && rtk git add .github/workflows/ci.yml && rtk git commit -m "ci: add gate workflow"
```

---

### Task 4: Release workflow

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: `ci.yml` via `workflow_call` (Task 3); the five scripts from Task 2 at their exact paths.
- Produces: workflow `release.yml` with artifact names `python-dist` and `npm-tarball`; publish jobs `publish-npm` / `publish-pypi` bound to environment `release` (Task 6 configures the registries and environment against these exact names).

- [ ] **Step 1: Resolve additional action SHAs**

Same procedure as Task 3 Step 1 for: `actions/upload-artifact`, `actions/download-artifact`, `pypa/gh-action-pypi-publish` (for the last, use the latest stable `vX.Y.Z` release tag — not the mutable `release/v1` branch).

```bash
git ls-remote --tags https://github.com/actions/upload-artifact | tail -12
git ls-remote --tags https://github.com/actions/download-artifact | tail -12
git ls-remote --tags https://github.com/pypa/gh-action-pypi-publish | tail -16
```

- [ ] **Step 2: Write `.github/workflows/release.yml`**

Replace `<SHA:…>` markers as in Task 3 (reuse Task 3's SHAs for checkout/setup-node/setup-uv):

```yaml
name: Release

on:
  push:
    tags: ["core/v*"]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false

jobs:
  gates:
    uses: ./.github/workflows/ci.yml

  build:
    runs-on: ubuntu-latest
    steps:
      - uses: <SHA:actions/checkout> # vX.Y.Z
      - name: Check version consistency
        run: |
          PY_VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('python/pyproject.toml','rb'))['project']['version'])")"
          NPM_VERSION="$(node -p "require('./ts/package.json').version")"
          if [ "$PY_VERSION" != "$NPM_VERSION" ]; then
            echo "manifest version mismatch: pyproject=$PY_VERSION package.json=$NPM_VERSION"
            exit 1
          fi
          case "$GITHUB_REF" in
            refs/tags/core/v*)
              TAG_VERSION="${GITHUB_REF#refs/tags/core/v}"
              if [ "$TAG_VERSION" != "$PY_VERSION" ]; then
                echo "tag core/v$TAG_VERSION does not match manifest version $PY_VERSION"
                exit 1
              fi
              ;;
          esac
          echo "version consistency ok: $PY_VERSION"
      - uses: <SHA:astral-sh/setup-uv> # vX.Y.Z
      - name: Build Python distributions
        working-directory: python
        run: |
          rm -rf dist
          uv build
      - uses: <SHA:actions/setup-node> # vX.Y.Z
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: ts/package-lock.json
      - name: Build npm tarball
        working-directory: ts
        run: |
          npm ci
          rm -rf dist
          npm run build
          npm pack
      - uses: <SHA:actions/upload-artifact> # vX.Y.Z
        with:
          name: python-dist
          path: python/dist/*
          if-no-files-found: error
      - uses: <SHA:actions/upload-artifact> # vX.Y.Z
        with:
          name: npm-tarball
          path: ts/nodes-dev-core-*.tgz
          if-no-files-found: error

  verify-artifacts:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: <SHA:actions/checkout> # vX.Y.Z
      - uses: <SHA:actions/download-artifact> # vX.Y.Z
        with:
          name: python-dist
          path: dist-python
      - uses: <SHA:actions/download-artifact> # vX.Y.Z
        with:
          name: npm-tarball
          path: dist-npm
      - uses: <SHA:astral-sh/setup-uv> # vX.Y.Z
      - uses: <SHA:actions/setup-node> # vX.Y.Z
        with:
          node-version: "24"
      - run: python3 .github/scripts/verify_python_artifacts.py dist-python
      - run: python3 .github/scripts/verify_npm_tarball.py dist-npm/*.tgz
      - run: .github/scripts/smoke_install_python.sh dist-python
      - run: .github/scripts/smoke_install_npm.sh dist-npm/*.tgz
      - name: npm publish dry-run
        run: npm publish --dry-run "$(ls dist-npm/*.tgz)"

  publish-npm:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/core/v')
    needs: [gates, build, verify-artifacts]
    runs-on: ubuntu-latest
    environment: release
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: <SHA:actions/download-artifact> # vX.Y.Z
        with:
          name: npm-tarball
          path: dist-npm
      - uses: <SHA:actions/setup-node> # vX.Y.Z
        with:
          node-version: "24"
          registry-url: https://registry.npmjs.org
      - name: Require npm >= 11.5.1 (trusted publishing floor)
        run: |
          node -e "
            const [maj, min, pat] = require('child_process').execSync('npm --version').toString().trim().split('.').map(Number);
            const ok = maj > 11 || (maj === 11 && (min > 5 || (min === 5 && pat >= 1)));
            if (!ok) { console.error('npm too old for trusted publishing'); process.exit(1); }
          "
      - run: npm publish "$(ls dist-npm/*.tgz)"

  publish-pypi:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/core/v')
    needs: [gates, build, verify-artifacts]
    runs-on: ubuntu-latest
    environment: release
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: <SHA:actions/checkout> # vX.Y.Z
      - uses: <SHA:actions/download-artifact> # vX.Y.Z
        with:
          name: python-dist
          path: dist
      - name: PyPI pre-upload check
        run: python3 .github/scripts/pypi_upload_check.py pre --project nodes-core --version "${GITHUB_REF#refs/tags/core/v}" --dist dist
      - uses: <SHA:pypa/gh-action-pypi-publish> # vX.Y.Z
        with:
          packages-dir: dist
          skip-existing: true
      - name: PyPI post-upload check
        run: python3 .github/scripts/pypi_upload_check.py post --project nodes-core --version "${GITHUB_REF#refs/tags/core/v}" --dist dist
```

- [ ] **Step 3: Validate — YAML parses, SHA-pinned, invariants present**

```bash
ROOT="$(git rev-parse --show-toplevel)" && python3 -c "import yaml; yaml.safe_load(open('$ROOT/.github/workflows/release.yml'))" && echo "yaml ok"
ROOT="$(git rev-parse --show-toplevel)" && grep -rn "<SHA:" "$ROOT/.github"; test $? -eq 1 && echo "no unresolved sha markers"
ROOT="$(git rev-parse --show-toplevel)" && UNPINNED="$(grep -En "uses: " "$ROOT/.github/workflows/release.yml" | grep -Ev "@[0-9a-f]{40} #|uses: ./.github/workflows/ci.yml" || true)" && test -z "$UNPINNED" && echo "all actions sha-pinned"
ROOT="$(git rev-parse --show-toplevel)" && COUNT="$(grep -c "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/core/v')" "$ROOT/.github/workflows/release.yml")" && test "$COUNT" = "2" && echo "both publish jobs tag-gated"
ROOT="$(git rev-parse --show-toplevel)" && COUNT="$(grep -c "environment: release" "$ROOT/.github/workflows/release.yml")" && test "$COUNT" = "2" && echo "both publish jobs environment-bound"
ROOT="$(git rev-parse --show-toplevel)" && COUNT="$(grep -c "id-token: write" "$ROOT/.github/workflows/release.yml")" && test "$COUNT" = "2" && echo "id-token only on publish jobs"
```

Expected: all six confirmation lines.

- [ ] **Step 4: Run all six gates + fixtures check**

Same commands as Task 1 Step 8. Expected: all PASS; `fixtures clean`.

- [ ] **Step 5: Commit**

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT" && rtk git add .github/workflows/release.yml && rtk git commit -m "ci: add release workflow"
```

---

### Task 5: Merge, create `nodes-dev/core`, push, CI green

This task and the two after it are operational: run them from the **primary checkout** on `main` (not the worktree), stopping at each **[OWNER]** step.

- [ ] **Step 1: Merge the branch**

Use `superpowers:finishing-a-development-branch`, option "Merge back to main locally" (precedent: `refactor/vocab-retirement` and the layout branch merged locally). Verify all six gates on the merged result; delete `feat/first-publish`.

- [ ] **Step 2 [OWNER]: Re-authenticate `gh`**

Both stored tokens are invalid. The owner runs (`!` prefix in the prompt runs it in-session):

```bash
gh auth refresh -h github.com
```

for whichever account controls the `nodes-dev` organization. Then verify:

```bash
gh auth status
gh api orgs/nodes-dev --jq .login
```

Expected: a valid account, and `nodes-dev`. If `orgs/nodes-dev` 404s, STOP — the identity design's premise (org exists and is controlled) needs re-checking with the owner.

- [ ] **Step 3: Create the repository and push**

```bash
gh repo create nodes-dev/core --public --description "Nodes: a problem-agnostic knowledge substrate (Python + TypeScript)"
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT" && rtk git remote add origin https://github.com/nodes-dev/core.git
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT" && rtk git push -u origin main
```

- [ ] **Step 4: Watch CI go green**

```bash
RUN_ID="$(gh run list --repo nodes-dev/core --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId')" && gh run watch --repo nodes-dev/core --exit-status "$RUN_ID"
```

Expected: success with all four matrix legs (Python 3.11, 3.13; Node 20, 24). This is the first time the declared floors are actually tested — a floor-leg failure is a real compatibility bug: STOP, fix on a branch, merge, re-push; do not proceed to registry setup until CI is green.

---

### Task 6: Release environment, registry setup, npm bootstrap

- [ ] **Step 1: Create the protected `release` environment**

```bash
gh api -X PUT repos/nodes-dev/core/environments/release --input - <<'EOF'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh api -X POST repos/nodes-dev/core/environments/release/deployment-branch-policies -f name='core/v*' -f type=tag
gh api repos/nodes-dev/core/environments/release/deployment-branch-policies --jq '.branch_policies[] | "\(.name) \(.type)"'
```

Expected: final command prints exactly `core/v* tag`. No required reviewers are configured (design §2.5: single maintainer; the tag push is the approval).

- [ ] **Step 2 [OWNER]: Create the npm `nodes-dev` organization**

On npmjs.com (logged in): profile menu → **Add Organization** → name `nodes-dev` → **free / public packages plan**. This reserves the `@nodes-dev` scope. Verify from the shell:

```bash
npm org ls nodes-dev
```

Expected: a member table listing the owner (no 404).

- [ ] **Step 3 [OWNER]: npm login on the workstation**

```bash
npm login
npm whoami
```

Expected: `npm whoami` prints the owner's npm username.

- [ ] **Step 4: Bootstrap-publish `@nodes-dev/core` 0.0.0**

Built from a clean `git archive` copy so no workstation `dist/` residue can leak (design §2.5). Build, verify, and publish run in ONE command chain — shell variables do not persist across separate tool calls, and each `&&` stops the chain (including the publish) on any failure. The Task 2 guard runs immediately before the upload:

```bash
ROOT="$(git rev-parse --show-toplevel)" && S="$(mktemp -d)" && git -C "$ROOT" archive HEAD ts | tar -x -C "$S" && cd "$S/ts" && npm ci && npm run build && npm version 0.0.0 --no-git-tag-version && npm pack && python3 "$ROOT/.github/scripts/verify_npm_tarball.py" nodes-dev-core-0.0.0.tgz && npm publish nodes-dev-core-0.0.0.tgz && rm -rf "$S"
npm view @nodes-dev/core@0.0.0 version
```

Expected: `npm tarball ok` in the chain's output, then `0.0.0` from `npm view`. The `--access public` flag is unnecessary — `publishConfig.access` is inside the tarball's package.json.

- [ ] **Step 5 [OWNER]: Configure the npm trusted publisher**

On npmjs.com: package page for `@nodes-dev/core` → **Settings** → **Trusted publisher**: publisher **GitHub Actions**; organization/user `nodes-dev`; repository `core`; workflow filename `release.yml`; environment `release`; allowed action **`npm publish`** (configurations created after 2026-05-20 must select allowed actions). Save.

- [ ] **Step 6 [OWNER]: Add the PyPI pending trusted publisher**

On pypi.org (owner's account, 2FA enabled): **Account settings → Publishing** (`https://pypi.org/manage/account/publishing/`) → **Add a new pending publisher** → GitHub: PyPI project name `nodes-core`; owner `nodes-dev`; repository name `core`; workflow name `release.yml`; environment name `release`. Save. (First pipeline upload creates the project; no placeholder, no token.)

---

### Task 7: Rehearsal, release `core/v0.1.0`, post-release verification

- [ ] **Step 1: Rehearse the pipeline (no publish)**

```bash
gh workflow run release.yml --repo nodes-dev/core --ref main
sleep 5 && RUN_ID="$(gh run list --repo nodes-dev/core --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')" && gh run watch --repo nodes-dev/core --exit-status "$RUN_ID"
gh run view --repo nodes-dev/core "$RUN_ID" --json jobs --jq '.jobs[] | "\(.name): \(.conclusion)"'
```

Expected: overall success; `build`, `verify-artifacts`, and all `gates / …` legs report `success`; `publish-npm` and `publish-pypi` report `skipped` (their tag-ref condition is false on dispatch). Anything publishing on a dispatch is a critical bug: STOP.

- [ ] **Step 2: Tag and release**

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT" && rtk git tag core/v0.1.0 && rtk git push origin core/v0.1.0
sleep 5 && RUN_ID="$(gh run list --repo nodes-dev/core --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')" && gh run watch --repo nodes-dev/core --exit-status "$RUN_ID"
```

Expected: full success including both publish jobs. Recovery on partial publish (design §3): re-run only the failed job at the same version (`gh run rerun "$RUN_ID" --failed`); never retract the successful artifact; never move the tag.

- [ ] **Step 3: Verify PyPI**

```bash
S="$(mktemp -d)" && uv venv "$S/venv" && uv pip install --python "$S/venv/bin/python" nodes-core==0.1.0 && "$S/venv/bin/python" - <<'EOF'
import importlib

import nodes.core

assert nodes.core.__name__ == "nodes.core"
assert getattr(nodes, "__file__", None) is None
legacy = ".".join(["nodes", "kernel"])
try:
    importlib.import_module(legacy)
except ModuleNotFoundError as exc:
    assert exc.name == legacy
else:
    raise SystemExit("legacy import path importable")
print("pypi install smoke ok")
EOF
rm -rf "$S"
```

Expected: `pypi install smoke ok`. (If the install 404s within the first minutes, index propagation may lag; retry after ~2 minutes before treating it as a failure.)

- [ ] **Step 4: Verify npm and deprecate the bootstrap**

```bash
npm view @nodes-dev/core@0.1.0 version dist.attestations
S="$(mktemp -d)" && cd "$S" && npm init -y >/dev/null && npm install --no-audit --no-fund @nodes-dev/core@0.1.0 >/dev/null && node --input-type=module -e "const core = await import('@nodes-dev/core'); if (Object.keys(core).length === 0) throw new Error('no exports'); console.log('npm registry smoke ok');" && cd / && rm -rf "$S"
npm deprecate @nodes-dev/core@0.0.0 "Bootstrap release for trusted-publishing setup; use >=0.1.0."
npm view @nodes-dev/core versions
```

Expected: `0.1.0` with a non-empty `dist.attestations` (provenance); `npm registry smoke ok`; `versions` lists `["0.0.0","0.1.0"]` with 0.0.0 deprecated (deprecation shows on `npm view @nodes-dev/core@0.0.0`).

- [ ] **Step 5: Final repo hygiene check**

```bash
ROOT="$(git rev-parse --show-toplevel)" && cd "$ROOT" && FIXSTAT="$(git status --porcelain)" && test -z "$FIXSTAT" && echo "worktree clean"
ROOT="$(git rev-parse --show-toplevel)" && test ! -e "$ROOT/python/dist" && echo "no dist residue"
```

Expected: `worktree clean`, `no dist residue`.

---

## Final Verification

- All six gates green locally; CI green on `main`.
- `pip install nodes-core==0.1.0` and `npm install @nodes-dev/core@0.1.0` both work from clean environments (Task 7 Steps 3–4).
- `npm view @nodes-dev/core@0.1.0 dist.attestations` shows provenance; PyPI project page for `nodes-core` shows 0.1.0 with attestations.
- npm 0.0.0 bootstrap deprecated.
- Tag `core/v0.1.0` exists on `origin` and points at the released commit: `rtk git ls-remote origin refs/tags/core/v0.1.0`.
- No new local commits beyond the merge: `rtk git log --oneline origin/main..HEAD` is empty.
