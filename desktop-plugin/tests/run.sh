#!/usr/bin/env bash
# Build a throwaway harness dir and run the harness-story desktop plugin tests.
# Cleans up desktop-plugin/.harness on exit so no external symlinks remain.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/.." && pwd)"
scratch="$root/.harness"
skill="${HERMES_SKILLS:-$HOME/.hermes/skills}/hermes-desktop-plugins"
mods="${HERMES_NODE_MODULES:-$HOME/.hermes/hermes-agent/node_modules}"

if ! command -v node >/dev/null 2>&1; then
  for ndir in "$HOME"/.hermes/tools/node-*/bin; do
    [ -d "$ndir" ] && PATH="$ndir:$PATH"
  done
  export PATH
fi

trap 'rm -rf "$scratch"' EXIT

for p in "$skill/scripts/stub-desktop-sdk.sh" "$mods/react" "$mods/react-dom" "$mods/jsdom" "$mods/scheduler"; do
  [ -e "$p" ] || { echo "missing: $p" >&2; exit 1; }
done

rm -rf "$scratch"
mkdir -p "$scratch"
bash "$skill/scripts/stub-desktop-sdk.sh" "$scratch" >/dev/null
cp "$root/harness-story/plugin.js" "$scratch/plugin.js"

# node --check on an .mjs copy
cp "$scratch/plugin.js" "$scratch/check.mjs"
node --check "$scratch/check.mjs"
rm "$scratch/check.mjs"
echo "syntax ok (node --check)"

# Swap stubbed react for real React 19 + jsdom
rm -rf "$scratch/node_modules/react"
for p in react react-dom jsdom scheduler; do
  ln -s "$mods/$p" "$scratch/node_modules/$p"
done

cp "$here/harness.mjs" "$scratch/harness.mjs"
cd "$scratch"
node harness.mjs
