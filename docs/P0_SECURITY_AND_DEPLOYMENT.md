# MyTrips v0.1.0 — OCI Native Build

Repository: `lurrnet/mytrips`, fork of `thiagodsti/partiu`.
Upstream baseline: Partiu v2.6.9 (`2510371e9c61faabe2dc636aa02edbb765862dc3`).
MyTrips version: `MYTRIPS_VERSION=0.1.0`; upstream feature-version variable: `PARTIU_VERSION=2.6.9`.

## Policy

- **Build and run directly on OCI**, never publish MyTrips container images to a registry.
- Use either `deploy/oci/compose.yaml` (ARM64) or root `docker-compose.yml`. Both use `build:`, a local `mytrips:0.1.0` image tag, and bind HTTP to `127.0.0.1:8030` by default. Set `MYTRIPS_PORT` in the root `.env` to override the host port; the container always listens on port 8000.
- GitHub CI still runs tests and a local Docker build smoke check; it does not push images. Both image publishing workflows were removed.
- The Dockerfile installs pinned `uv` from Python packages instead of copying binaries from GHCR.
- `DISABLE_SMTP_SERVER=true` is enforced by the patched backend regardless of admin settings. No SMTP host port is published. Scheduler, LLM, and Photon lookups disabled in the OCI deployment.
- Keep the Cloudflare Tunnel and Access separate; do not expose the app with a public host bind.
- Base images and build dependencies are still downloaded from Docker Hub, apt repositories, npm, and PyPI; **no container registry is required to host MyTrips itself**. OCI needs outbound network for the first build.
- This is initial staging hardening, not a complete security audit. Review third-party data lookups, dependency vulnerabilities and email/PDF parser threats before real use.

## Deploy on OCI Ampere A1

Assumes Docker Engine, Compose plugin and Git are installed.

```sh
cd ~/github
git clone https://github.com/lurrnet/mytrips.git
cd mytrips
cp .env.example .env
chmod 600 .env
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
mkdir -p data && chmod 700 data

bash deploy/oci/check-config.sh
docker compose --env-file .env -f deploy/oci/compose.yaml up -d --build
docker compose --env-file .env -f deploy/oci/compose.yaml ps
curl -fsS http://127.0.0.1:8030/manifest.json
```

The setting is in the repository root `.env`, copied from `.env.example`: `MYTRIPS_PORT=8030`. If port 8030 is occupied, choose another unused host port by changing that value. `PARTIU_PORT` was an old, undocumented Compose-only variable; it is no longer supported. To update an existing `.env`, replace any `PARTIU_PORT=...` line with `MYTRIPS_PORT=8030`, or append the new line if neither exists. Docker still listens on port 8000 **inside the container**.
Cloudflare Tunnel origin `http://127.0.0.1:8030` assumes cloudflared runs **on the same host**. Protect it with Cloudflare Access.
Use synthetic data for the initial smoke test.

## Routine updates

Review upstream changes in a branch via `scripts/sync-upstream-safely.sh`.
After changes are reviewed, tested, and merged, on OCI:

```sh
cd ~/github/mytrips
git fetch origin
git switch main
git pull --ff-only origin main
bash deploy/oci/check-config.sh
docker compose --env-file .env -f deploy/oci/compose.yaml up -d --build
```

For reproducibility, note the Git commit SHA or tag deployed. Local image tag `mytrips:0.1.0` is overwritten on a rebuild; to retain rollback images tag them with a distinct name **before** rebuilding.

## SQLite database filename migration

The application and both Compose files now default to `mytrips.db`.
Existing installs with `partiu.db` must migrate while the app is stopped.
The original database is preserved. The migration uses SQLite's backup API,
including committed changes in WAL, and refuses to overwrite a target.

```sh
cd ~/github/mytrips
docker compose --env-file .env -f deploy/oci/compose.yaml stop app
python3 scripts/rename_sqlite_db.py
# Existing .env files are not changed by git pull:
sed -i 's#^DB_PATH=./data/partiu.db$#DB_PATH=./data/mytrips.db#' .env
bash deploy/oci/check-config.sh
docker compose --env-file .env -f deploy/oci/compose.yaml up -d --build
```

If `data/mytrips.db` already exists alongside `data/partiu.db`, do not
overwrite either; inspect both databases first. Never migrate while the
old app is still writing. After smoke testing, separately archive the
original `data/partiu.db` and its old auxiliary files.

## Backup and restore

`PARTIU_BACKUP_DIR=/var/backups/mytrips bash deploy/oci/backup.sh` stops the container, archives SQLite and files, validates gzip, writes a SHA256 checksum, then restarts it.
`bash deploy/oci/restore.sh --apply /var/backups/mytrips/mytrips-<timestamp>.tar.gz` verifies checksum and archive contents, stops the app, preserves old data under a renamed directory, restores and verifies SQLite integrity.
**Restore replaces live data. Test it in a separate staging checkout before real data.** The `.env` secret is not archived and must be backed up separately.
Backups contain sensitive travel records; restrict and encrypt off-host copies.

## Privacy and Cloudflare email forwarding

P1 will introduce Cloudflare Email Routing → Email Worker → authenticated MyTrips API. Until then, SMTP is deliberately disabled and manual entry / upload can be used.
The existing Partiu update checker talks to GitHub (not GHCR); if avoiding this optional outbound lookup is also desired, it requires a separate setting/change.
