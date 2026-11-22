#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  printf 'Commit or stash tracked changes before updating.\n' >&2
  exit 1
fi
umask 077
mkdir -p backups
backup=$(mktemp -d backups/printernvr.XXXXXXXX)
cp -a config "$backup/"
for path in .env recordings/.clip_metadata.json recordings/.timelapse-auto.json; do
  if [[ -f "$path" ]]; then cp -p "$path" "$backup/"; fi
done
git rev-parse HEAD > "$backup/revision"
printf 'Configuration and review metadata backed up to %s\n' "$backup"
git pull --ff-only
bash scripts/install.sh "$@"
