#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
[[ -f .env ]] || { echo "Missing .env" >&2; exit 1; }
docker compose --env-file .env -f deploy/oci/compose.yaml config --format json | python3 -c '
import json,re,sys
app=json.load(sys.stdin)["services"]["app"]
assert re.search(r"@sha256:[0-9a-f]{64}$", app["image"]), "image must use immutable digest"
ports=app.get("ports", [])
assert len(ports)==1 and ports[0].get("host_ip")=="127.0.0.1" and int(ports[0]["target"])==8000, "HTTP must be loopback-only; no SMTP published"
env=app["environment"]
assert env.get("DISABLE_SMTP_SERVER")=="true"
assert env.get("DEMO_MODE")=="false"
assert env.get("PHOTON_URL")==""
assert env.get("OLLAMA_URL")==""
assert env.get("SECURE_COOKIES")=="true"
print("P0 OCI policy: PASS")
'
