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
