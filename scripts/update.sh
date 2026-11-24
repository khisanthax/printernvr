#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

if [[ $# -gt 1 || ($# -eq 1 && ${1:-} != --with-go2rtc) ]]; then
  printf 'Usage: bash scripts/update.sh [--with-go2rtc]\n' >&2
  exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  printf 'Commit or stash tracked changes before updating.\n' >&2
  exit 1
fi
backup=$(bash scripts/backup.sh)
printf 'Configuration and metadata backed up to %s (media not included)\n' "$backup"
git pull --ff-only
bash scripts/install.sh "$@"
