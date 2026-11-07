#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
[[ -f .env ]] || { echo "Missing .env" >&2; exit 1; }
if grep -Eq "^[[:space:]]*PARTIU_PORT=" .env; then
  echo "Deprecated PARTIU_PORT in .env. Rename it to MYTRIPS_PORT (default 8030)." >&2
  exit 1
fi
docker compose --env-file .env -f deploy/oci/compose.yaml config --format json | python3 -c '
import json, pathlib, sys
root=pathlib.Path(sys.argv[1]).resolve()
app=json.load(sys.stdin)["services"]["app"]
image=app["image"]
assert image.startswith("mytrips:") and "/" not in image and "@" not in image, "expected local-only image tag"
assert pathlib.Path(app["build"]["context"]).resolve()==root, "build context must be this checkout"
assert app["build"].get("dockerfile")=="Dockerfile", "must build local Dockerfile"
ports=app.get("ports", [])
assert len(ports)==1 and ports[0].get("host_ip")=="127.0.0.1" and int(ports[0]["target"])==8000, "HTTP must be localhost-only; SMTP not published"
port=int(ports[0]["published"])
assert 1 <= port <= 65535 and port not in (25, 2525), "Host port must be a valid HTTP port, not SMTP"
print(f"MyTrips external HTTP port: 127.0.0.1:{port} -> container :8000")
env=app["environment"]
for k,v in {"DB_PATH":"/app/data/mytrips.db", "DISABLE_SMTP_SERVER":"true", "DISABLE_SCHEDULER":"true", "DEMO_MODE":"false", "PHOTON_URL":"", "OLLAMA_URL":"", "SECURE_COOKIES":"true"}.items():
    assert env.get(k)==v, f"unsafe {k}"
dockerfile=(root/"Dockerfile").read_text()
assert "ghcr.io" not in dockerfile, "Dockerfile must not fetch builder from GHCR"
print("MyTrips OCI local-build policy: PASS")
' "$root"
