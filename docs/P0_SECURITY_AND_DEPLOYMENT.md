# MyTrips P0.1–P0.3 — initial implementation

**Fork:** `lurrnet/mytrips` (upstream `thiagodsti/partiu`).
**Baseline:** `v2.6.9`, commit `2510371e9c61faabe2dc636aa02edbb765862dc3`.
**Status:** v0.1.0 initial staging release candidate. CI covers basic Docker build, unit tests, security config, and synthetic cold backup/restore. Real ARM64 image build and OCI end-to-end smoke still require verification.

## P0.1 — Upstream sync and isolation
Keep changes in feature branches, merge after PR checks; `scripts/sync-upstream-safely.sh` creates an isolated upstream-merge branch from clean local `main`.
Do not rewrite upstream history. Keep `data/` and `.env` ignored.

## P0.2 — Security and release controls
Use `deploy/oci/compose.yaml` on OCI, **not** upstream root `docker-compose.yml`, which publishes SMTP port 25 and HTTP on all interfaces.
The OCI deployment binds only `127.0.0.1:8000`; config forces `DISABLE_SMTP_SERVER=true` even if SQLite settings say enabled.
The SMTP kill switch requires **our custom built image**. Do not use unpatched `ghcr.io/thiagodsti/partiu`.
No public SMTP, no default outbound Photon queries, no Ollama LLM forwarding, no demo mode. Cloudflare Tunnel + Access required before access over internet.
`PARTIU_IMAGE` must have an actual `@sha256:<64 hex>` digest. Never use `latest` for OCI.
Production hardening still needs review of base-image pins, dependency advisories, outbound enrichment APIs, admin setup, CSRF/rate limits, sensitive email parsing, and CI/e2e results.
The supplied PR workflow checks static deployment guardrails; upstream CI contains non-blocking browser E2E tests.

## P0.3 — OCI ARM64 staging
After reviewed PR merges, **P0 ARM64 pinned image** automatically builds on `main`. Copy `PARTIU_IMAGE=...@sha256:...` from its log, job summary, or uploaded `mytrips-arm64-image-ref` artifact. If the package is private, authenticate with GHCR using a least-privilege read:packages token, or mark the package public.
On an OCI Ampere A1 host with Docker Compose and a **local** Cloudflare Tunnel:

```sh
git clone https://github.com/lurrnet/mytrips.git
cd mytrips
cp .env.example .env
chmod 600 .env
# Edit .env: SECRET_KEY=<openssl rand -hex 32 output>, PARTIU_VERSION=0.1.0
# Append: PARTIU_IMAGE=ghcr.io/lurrnet/mytrips@sha256:<real digest>
mkdir -p data
chmod 700 data
bash deploy/oci/check-config.sh
docker compose --env-file .env -f deploy/oci/compose.yaml up -d
docker compose --env-file .env -f deploy/oci/compose.yaml ps
curl -fsS http://127.0.0.1:8000/manifest.json
```

The Compose config uses relative `../../.env` and `../../data` from `deploy/oci/`, resolved to the repository root.
Cloudflare Tunnel origin should target `http://127.0.0.1:8000` **only if cloudflared runs on the same host**.
Protect hostname with Cloudflare Access, verify HTTPS secure cookies.
Use synthetic emails/trips/hotel confirmations during smoke tests. Do not enter real reservation data before the audit is finished. The source code still uses Partiu identifiers; MyTrips is the fork/distribution name.

## Backup and restore acceptance
`PARTIU_BACKUP_DIR=/var/backups/mytrips bash deploy/oci/backup.sh` produces archive + SHA256; stopping the container ensures consistent SQLite/WAL + attachments.
`bash deploy/oci/restore.sh --apply /var/backups/mytrips/<archive>.tar.gz` validates checksums, archive types, and SQLite integrity. **Destructive** to live `data/`; old data is renamed, never auto-deleted. Test against a separate staging checkout first. Secrets in `.env` are not backed up.
Archive contains personal travel history and documents: restrict access and encrypt when off-host. Add Dockback integration only after a restore drill.

## Release guardrails
- The image is built natively for Linux ARM64 by the main-branch GitHub workflow; no `latest` in the OCI Compose.
- Inspect Actions workflow, digest, and published package visibility before deploying. A successful build is **not** evidence an OCI VM has run the image.
- Container-side startup settings force the scheduler and SMTP listener off. This first version supports manual entry and import, but forwarding automation is deferred to P1.
- Bind the service to localhost; Cloudflare Tunnel and Access must be configured separately on the host.
