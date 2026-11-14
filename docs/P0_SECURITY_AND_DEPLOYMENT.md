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

**Confirmed Android installation path (2026-11-13):** When Chrome installed
MyTrips from authenticated app routes such as `/#/login` or `/#/trips`, the
Android WebAPK's `chrome://webapks` entry showed a blank `Manifest URL`, an
incorrect start URL, and a white-circle launcher icon. Installing from the
isolated public `/pwa-install.html` page on the **same hostname** correctly
populated `Manifest URL` (`/manifest.json?v=6`) and displayed the approved
MyTrips A icon. This strongly implicates the authenticated SPA install path;
the specific root mechanism has not been isolated further.

### Cloudflare Access configuration

Create narrowly scoped **path-exact Bypass** policies for these public static
PWA resources under the *same hostname* as the private app:

| Path | Purpose |
| --- | --- |
| `/pwa-install.html` | Public installation entry page, no trip data |
| `/manifest.json` | Canonical app name, identity, colors, install icons |
| `/icon-192.png` | Chrome install / fallback icon |
| `/icon-maskable-512.png` | Android adaptive icon |
| `/sw.js` | Install-page service worker registration |

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

1. In regular **Android Chrome**, open the `/pwa-install.html` URL from the
   site itself, or visit **Settings → Install MyTrips** and open the linked page
   in Chrome. If the installed standalone app opens the link inside itself,
   copy the URL into Chrome manually.
2. Choose **Install app** in Chrome's three-dot menu. The page may offer its
   own Install button when Chrome fires `beforeinstallprompt`.
3. Launch the app from the home screen and authenticate through Cloudflare
   Access / MyTrips as usual. Installing never grants access to private data.
4. For troubleshooting, inspect `chrome://webapks`:
   - `Manifest URL` must be nonempty and point to
     `https://mytrips.skybluestudio.net/manifest.json?v=6`.
   - `Manifest Start URL` must be the origin root `/`, not whichever
     `/#/trips` or `/#/login` screen was open.
   - Theme and background colors should be populated.

Only uninstall an *old incorrectly installed* white-circle WebAPK if needed
before a clean install. **Normal application updates should not require
uninstalling MyTrips.** The existing Service Worker remains unchanged and
checks for updates when the app is brought back into focus. The manifest has a
stable `id: "/"`, `start_url: "/"`, and `scope: "/"` so future deployments
keep the installed app identity and launch URL.

If the public install page fails, compare the actual responses at the edge,
check Chrome DevTools → Application → Manifest, and verify there are no
unexpected redirects. Do not weaken the site's Access policy to fix an icon.
