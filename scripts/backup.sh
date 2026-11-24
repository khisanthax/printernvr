#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

if [[ $# -gt 1 || ($# -eq 1 && ${1:-} != --full) ]]; then
  printf 'Usage: bash scripts/backup.sh [--full]\n' >&2
  exit 2
fi

revision=$(git rev-parse --verify HEAD)
paths=(config)
if [[ ${1:-} == --full ]]; then
  paths+=(recordings)
else
  for path in recordings/.clip_metadata.json recordings/.timelapse-auto.json recordings/.timeline; do
    if [[ -e "$path" || -L "$path" ]]; then paths+=("$path"); fi
  done
fi
if [[ -e .env || -L .env ]]; then paths+=(.env); fi

for path in "${paths[@]}"; do
  # Reject links and special files; never traverse outside the intended source tree.
  unexpected=$(find "$path" ! -type d ! -type f -print -quit)
  if [[ -n "$unexpected" ]]; then
    printf 'Backup refused a link or special file under %s. Use a verified volume snapshot instead.\n' "$path" >&2
    exit 1
  fi
done
if [[ -L recordings || -L backups ]]; then
  printf 'Backup refused a linked recordings or backups directory.\n' >&2
  exit 1
fi

umask 077
mkdir -p backups
backup=$(mktemp -d backups/printernvr.XXXXXXXX)
printf '%s\n' "$revision" > "$backup/revision"
tar -cf "$backup/state.tar.part" -- "${paths[@]}"
mv -- "$backup/state.tar.part" "$backup/state.tar"
(
  cd -- "$backup"
  sha256sum state.tar revision > SHA256SUMS
  sha256sum -c SHA256SUMS >/dev/null
  tar -tf state.tar >/dev/null
)
printf '%s\n' "$backup"
