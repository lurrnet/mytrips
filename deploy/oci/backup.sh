#!/usr/bin/env bash
# Full cold backup: SQLite + WAL + files in data directory.
set -Eeuo pipefail
umask 077
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
[[ -f .env && -d data ]] || { echo "Missing .env or data" >&2; exit 1; }
backup_dir="${PARTIU_BACKUP_DIR:-/var/backups/mytrips}"
mkdir -p -- "$backup_dir"; chmod 700 -- "$backup_dir"
backup_dir="$(cd -- "$backup_dir" && pwd -P)"
case "$backup_dir/" in "$root/"* ) echo "Backups must be outside repository" >&2; exit 1;; esac
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$backup_dir/mytrips-$stamp.tar.gz"
[[ ! -e "$archive" ]] || { echo "Archive exists" >&2; exit 1; }
tmp="$archive.tmp.$$"
compose=(docker compose --env-file .env -f deploy/oci/compose.yaml)
was_running="$("${compose[@]}" ps --status running -q app)"
cleanup() {
  status=$?
  if [[ -n "$was_running" ]]; then "${compose[@]}" up -d --no-deps app || status=1; fi
  rm -f -- "$tmp"
  exit "$status"
}
trap cleanup EXIT
if [[ -n "$was_running" ]]; then "${compose[@]}" stop app; fi
tar -czf "$tmp" -C "$root" data
gzip -t "$tmp"
mv -- "$tmp" "$archive"
(cd "$backup_dir" && sha256sum "$(basename -- "$archive")" > "$(basename -- "$archive").sha256")
echo "Backup: $archive (contains sensitive travel data; encrypt off-host)"
