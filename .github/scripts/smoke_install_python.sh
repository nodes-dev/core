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
