#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

mkdir -p config recordings logs
copy_example() {
  if [[ ! -e "$2" ]]; then
    (set -o noclobber; cat "$1" > "$2")
  fi
}
copy_example .env.example .env
copy_example config/app.example.json config/app.json
if [[ ! -e config/cameras.json ]]; then
  (set -o noclobber; printf '{"printers": []}\n' > config/cameras.json)
fi

compose=(docker compose)
if [[ "${1:-}" == "--with-go2rtc" ]]; then
  copy_example config/go2rtc.example.yaml config/go2rtc.yaml
  compose+=(-f docker-compose.yml -f docker-compose.go2rtc.yml --profile go2rtc)
elif [[ $# -ne 0 ]]; then
  printf 'Usage: bash scripts/install.sh [--with-go2rtc]\n' >&2
  exit 2
fi
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build --wait --wait-timeout 120
printf 'Printer NVR is ready. Configure and probe cameras on /cameras.\n'
