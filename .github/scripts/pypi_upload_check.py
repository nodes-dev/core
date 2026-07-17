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
