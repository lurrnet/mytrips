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


## Android PWA install: "This app cannot be installed"

MyTrips is deployed behind Cloudflare Access. Chromium may fail to load a
credential-protected manifest without `crossorigin="use-credentials"` even when
the manifest is on the same origin. The frontend now includes this attribute;
the Manifest has an explicit stable ID/scope, and its response uses
`application/manifest+json` with no-cache headers. The service worker avoids
caching installation metadata and icon URLs.

**First verify the app itself, without changing Access security settings:**

```sh
cd ~/github/mytrips
git pull --ff-only
docker compose --env-file .env -f deploy/oci/compose.yaml up -d --build
python3 scripts/check_pwa_install.py --origin http://127.0.0.1:8030
```

The script checks actual HTTP responses (not just source files): manifest link
and cookie credentials, JSON Content-Type, app identity/scope, image MIME type,
PNG dimensions and CRC integrity, and service worker JavaScript response.

If the localhost checks pass but Android Chrome still reports it cannot install:

1. Open MyTrips over **HTTPS** using the canonical Cloudflare Tunnel hostname
   in a regular Chrome tab (not Incognito, not plain `http://192.168...`).
2. Complete Cloudflare Access login on that **same origin and Chrome profile**.
3. Reload, then try the Chrome three-dot install option again. If an older
   MyTrips/Partiu PWA is installed, uninstall the existing app first.
4. In Chrome desktop DevTools → **Application → Manifest**, inspect install
   errors and inspect the `manifest.json?v=4` request under **Network**.
   It must return **200**, `application/manifest+json`, **MyTrips JSON**
   instead of Access HTML or a 302 redirect. Icon URLs must return **200
   image/png**, not `text/html`. Service worker `/sw.js` must load as JS.
5. If requests still land on the Access login/challenge page after signing in,
   investigate the Access application session, cookie scope, or WAF rules.
   Do **not** disable Cloudflare Access on the entire hostname just to install
   a PWA. Installation as a browser shortcut is a temporary fallback.

Chrome on Android can only install a full WebAPK when its installability checks
pass. A valid manifest and local CI are insufficient to prove an authenticated
Cloudflare edge request works from the real Android browser.


## Android launcher icon — Smart Meter Texas comparison

The working Smart Meter Texas PWA manifest uses 192px `purpose: any` and
512px `purpose: any maskable`. MyTrips now follows that same unambiguous
selection pattern while retaining the **approved original A artwork** and the
dark, safe-zone-padded `icon-maskable-512.png`. The Web UI favicon and login
artwork are unchanged. The previous 512px regular image remains available on
disk, but is no longer a competing 512px manifest icon.

After deploying, run `python3 scripts/check_pwa_install.py --origin http://127.0.0.1:8030`
and check the external manifest in Chrome. An authenticated Access browser may
fetch icons successfully while the **WebAPK minting service** still cannot
create an Android-installed app; a fallback home-screen shortcut may render a
small square icon in a white circle. This code change improves icon selection
but **does not guarantee a WebAPK**.

On Android Chrome open `chrome://webapks` and look for MyTrips. Also check
Android Settings → Apps. A WebAPK appears as an installed app; a browser
shortcut may only exist on the home screen. If MyTrips is not a WebAPK, diagnose
Chrome installation eligibility and Cloudflare Access/minting compatibility,
not icon colors. Keep Cloudflare Access enabled.
