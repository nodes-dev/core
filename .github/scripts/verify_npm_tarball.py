#!/usr/bin/env python3
"""Assert npm tarball contents (first-publish design, 2.4 verify-artifacts).

dist/vocab/ is explicitly forbidden: the retired vocab compiled outputs
survived in an unclean workstation dist/ once already, and tsc never deletes
stale outputs.
"""

import sys
import tarfile
from pathlib import PurePosixPath

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
        members = t.getmembers()
    names: set[str] = set()
    for member in members:
        name = member.name
        path = PurePosixPath(name)
        if "\\" in name or path.is_absolute() or str(path) != name or any(part in {".", ".."} for part in path.parts):
            fail(f"tarball contains non-canonical path: {name!r}")
        if name in names:
            fail(f"tarball contains duplicate path: {name!r}")
        if not member.isfile():
            fail(f"tarball contains non-regular member: {name!r}")
        names.add(name)
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
