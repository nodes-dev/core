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


def local_files(dist: str, *, require_attestations: bool) -> dict[str, str]:
    names = sorted(os.listdir(dist))
    wheels = [name for name in names if name.endswith(".whl")]
    sdists = [name for name in names if name.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1:
        fail(f"expected exactly 1 wheel and 1 sdist, found wheels={wheels}, sdists={sdists}")

    distributions = wheels + sdists
    expected_attestations = {f"{name}.publish.attestation" for name in distributions}
    present_attestations = {name for name in names if name.endswith(".publish.attestation")}
    unexpected = sorted(set(names) - set(distributions) - expected_attestations)
    if unexpected:
        fail(f"unexpected files in distribution directory: {unexpected}")
    if require_attestations:
        missing = sorted(expected_attestations - present_attestations)
        if missing:
            fail(f"missing distribution attestations: {missing}")

    out: dict[str, str] = {}
    for name in distributions:
        with open(os.path.join(dist, name), "rb") as fh:
            out[name] = hashlib.sha256(fh.read()).hexdigest()
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

    local = local_files(args.dist, require_attestations=args.mode == "post")
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
