#!/usr/bin/env bash
set -euo pipefail

workspace_dir="$(cd "$(dirname "$0")" && pwd)"
python3 "$workspace_dir/run_reproductions.py" "$@"
