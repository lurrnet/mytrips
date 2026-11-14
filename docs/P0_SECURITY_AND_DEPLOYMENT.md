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
curl -fsS http://127.0.0.1:8030/pwa/manifest.json
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

## Branding audit (MyTrips distribution)

The customer-facing name is **MyTrips** in the setup/login flows, English and
Portuguese translations, navigation and GitHub links, PWA manifest/HTML, default
push notifications, 2FA authenticator issuer, API docs, iCalendar producer,
integrations' User-Agent headers, frontend package metadata and release checker.

Run `python3 scripts/audit_branding.py` to identify any regressed user-visible
Partiu names. This audit runs in GitHub CI on every PR and main push.

**Intentional compatibility exceptions:** upstream provenance links and demo URLs
in README; `PARTIU_VERSION` upstream env fallback; legacy SQLite
`partiu.db` migrations; `partiu-at-rest-v1` crypto KDF salt;
`partiu.audit` internal logger; `@partiu` iCalendar UIDs (changing UIDs would
duplicate events in existing calendars); `partiu-api-*` legacy CacheStorage
purging; `partiu_push_enabled` legacy notification preference migration; and
the Python project metadata `partiu` retained to avoid modifying the locked
dependency graph. The first MyTrips rebuild invalidates PWA caches; if an
existing installed PWA title remains stale after update, reinstall the PWA.


## Android PWA installation

**Confirmed Android installation pattern (2026-11-13):** Chrome installed
MyTrips successfully when opened from an isolated public installation page,
whereas installation from authenticated SPA routes could create a fallback
white-circle WebAPK with no manifest metadata. The public installer and its
metadata now live together under `/pwa/`. This new prefix must be tested after
deployment; the original device acceptance test was performed before the move.
The app's manifest identity, start URL, and scope remain `/` so the installed
app launches the protected web UI. Users may uninstall the old WebAPK and
reinstall from the new URL; this migration does not maintain legacy PWA URLs.

### Cloudflare Access configuration

Create **one** path-prefix Cloudflare Access Bypass for
`https://mytrips.skybluestudio.net/pwa/*` (adjust hostname for other
deployments). The only contents under `frontend/public/pwa/` are installation
assets:

| Path | Purpose |
| --- | --- |
| `/pwa/install.html` | Public installation entry (no trip data) |
| `/pwa/manifest.json` | App identity and install metadata |
| `/pwa/icon-192.png` | Chrome install / fallback icon |
| `/pwa/icon-512.png` | Optional full-resolution ordinary icon |
| `/pwa/icon-maskable-512.png` | Android maskable icon |
| `/pwa/apple-touch-icon.png` | Apple touch icon |
| `/pwa/sw.js` | Service Worker (the API sends `Service-Worker-Allowed: /`) |

**Do not bypass `/`, `/api/*`, `/*`, `/assets/*`, or other private paths.**
Keep the existing Cloudflare Access policy on all application data and pages.
This strategy does not require exposing authentication cookies, the SPA, or API.

For the current deployment these exact paths are available at
`https://mytrips.skybluestudio.net`. For other installations replace the
hostname with their own Cloudflare hostname. Static assets must return their
real content (not a 302 Access login page).

### Deploy and verify

```sh
cd ~/github/mytrips
git pull --ff-only
docker compose --env-file .env -f deploy/oci/compose.yaml up -d --build --force-recreate app

# After the container becomes healthy:
python3 scripts/check_pwa_install.py --origin http://127.0.0.1:8030 --install-page
python3 scripts/check_pwa_install.py --origin https://mytrips.skybluestudio.net --install-page
```

The checks assert the live install page, manifest and icon PNGs, and service
worker response. The external check requires the exact public Bypass paths.
The application homepage itself must still redirect unauthenticated visitors
to Cloudflare Access.

### Install or reinstall on Android

1. In regular **Android Chrome**, open the `/pwa/install.html` URL from the
   site itself, or visit **Settings → Install MyTrips** and open the linked page
   in Chrome. If the installed standalone app opens the link inside itself,
   copy the URL into Chrome manually.
2. Choose **Install app** in Chrome's three-dot menu. The page may offer its
   own Install button when Chrome fires `beforeinstallprompt`.
3. Launch the app from the home screen and authenticate through Cloudflare
   Access / MyTrips as usual. Installing never grants access to private data.
4. For troubleshooting, inspect `chrome://webapks`:
   - `Manifest URL` must be nonempty and point to
     `https://mytrips.skybluestudio.net/pwa/manifest.json?v=7`.
   - `Manifest Start URL` must be the origin root `/`, not whichever
     `/#/trips` or `/#/login` screen was open.
   - Theme and background colors should be populated.

For this one-time path migration, **uninstall the existing MyTrips WebAPK**
and install again from `/pwa/install.html`. The old root-level installation
paths are intentionally removed. After reinstalling, regular app updates
continue through `/pwa/sw.js` and should not require further reinstalls.
The `id: "/"`, `start_url: "/"` and `scope: "/"` remain stable.

If the public install page fails, compare the actual responses at the edge,
check Chrome DevTools → Application → Manifest, and verify there are no
unexpected redirects. Do not weaken the site's Access policy to fix an icon.

### Verification of single-bypass migration

After the new Docker image is deployed, verify these resources anonymously:

```sh
python3 scripts/check_pwa_install.py --origin https://mytrips.skybluestudio.net --install-page
for path in /pwa/install.html /pwa/manifest.json /pwa/sw.js /pwa/icon-192.png /pwa/icon-maskable-512.png /; do
  curl -sS -o /dev/null -w "$path HTTP=%{http_code} MIME=%{content_type}\\n" "https://mytrips.skybluestudio.net$path"
done
```

Expect the five `/pwa/*` files to return HTTP 200 with correct media types,
root `/` to return Access HTTP 302, and `/pwa/sw.js` to respond with
`Service-Worker-Allowed: /`. Confirm Android Chrome's `chrome://webapks`
shows `Manifest URL: https://mytrips.skybluestudio.net/pwa/manifest.json?v=7`.
After successful verification, delete the five old **path-exact** Access Bypass
rules for `/pwa-install.html`, `/manifest.json`, `/icon-192.png`,
`/icon-maskable-512.png` and `/sw.js`; keep only the narrow `/pwa/*`
Bypass on this host.

## PWA privacy: network-only travel API (Service Worker v25)

The Service Worker at `/pwa/sw.js` does **not cache or serve any `/api` or
`/api/*` response**, regardless of method. Requests and network errors pass
through to the server/browser normally, including authentication and writes;
offline use does not fall back to another account's saved trips or stats.
Only non-sensitive `/assets/*`, `/fonts/*`, and successful root app-shell HTML
are eligible for worker caching. Other downloads and documents remain
network-only. The new worker activation deletes all old `mytrips-api-*` and
`partiu-api-*` caches as well as obsolete MyTrips shell caches before taking
control; the login/logout cache purge is kept as defense in depth.

After deploying, allow the browser to load the new worker, then confirm that
travel data requires a working network connection. This worker policy does
not clear independent browser HTTP caches, server caches, or any data that
other application code may persist outside Service Worker CacheStorage.
