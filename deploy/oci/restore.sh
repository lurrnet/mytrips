#!/usr/bin/env bash
# Restore only to staging first; preserves existing data directory.
set -Eeuo pipefail
umask 077
[[ $# -eq 2 && "$1" == "--apply" ]] || { echo "Usage: $0 --apply /path/to/archive.tar.gz" >&2; exit 2; }
archive="$(realpath -- "$2")"
[[ -f "$archive" && -f "$archive.sha256" ]] || { echo "Missing archive/checksum" >&2; exit 1; }
(cd "$(dirname -- "$archive")" && sha256sum -c -- "$(basename -- "$archive").sha256")
python3 - "$archive" <<'PY'
import pathlib,sys,tarfile
with tarfile.open(sys.argv[1],"r:gz") as tf:
 for m in tf:
  p=pathlib.PurePosixPath(m.name)
  if not p.parts or p.parts[0]!="data" or ".." in p.parts or m.name.startswith("/") or not (m.isfile() or m.isdir()):
   raise SystemExit(f"Unsafe archive member: {m.name}")
print("Archive entry safety PASS")
PY
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
[[ -f .env ]] || { echo "Missing .env" >&2; exit 1; }
compose=(docker compose --env-file .env -f deploy/oci/compose.yaml)
was_running="$("${compose[@]}" ps --status running -q app)"
if [[ -n "$was_running" ]]; then "${compose[@]}" stop app; fi
old=""
if [[ -e data ]]; then
 old="data.pre-restore.$(date -u +%Y%m%dT%H%M%SZ)"
 [[ ! -e "$old" ]] || { echo "Old backup directory exists" >&2; exit 1; }
 mv data "$old"
fi
rollback() {
 status=$?
 if [[ "$status" -ne 0 ]]; then
  echo "Restore failed; reverting data" >&2
  if [[ -e data ]]; then mv data "data.failed-restore.$(date -u +%Y%m%dT%H%M%SZ)"; fi
  if [[ -n "$old" && -e "$old" ]]; then mv "$old" data; fi
 fi
 if [[ -n "$was_running" ]]; then "${compose[@]}" up -d --no-deps app || status=1; fi
 exit "$status"
}
trap rollback EXIT
tar -xzf "$archive" --no-same-owner -C "$root"
[[ -f data/partiu.db ]] || { echo "SQLite DB missing" >&2; exit 1; }
python3 - <<'PY'
import sqlite3
conn=sqlite3.connect("file:data/partiu.db?mode=ro",uri=True)
try:
 if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise SystemExit("SQLite integrity check FAILED")
finally: conn.close()
print("SQLite integrity PASS")
PY
echo "Restore successful; previous directory: ${old:-none}"
