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
