#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
target="$script_dir/official-source"
commit="8b44e971756e421ade723442dafd17513fd70e1a"

if [[ ! -d "$target/.git" ]]; then
  git clone https://github.com/MrBlankness/SchemaCompression.git "$target"
fi

git -C "$target" fetch origin "$commit"
git -C "$target" checkout --detach "$commit"
actual="$(git -C "$target" rev-parse HEAD)"

if [[ "$actual" != "$commit" ]]; then
  echo "unexpected source commit: $actual" >&2
  exit 1
fi

echo "official source ready at commit $actual"
