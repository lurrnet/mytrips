#!/usr/bin/env python3
"""Regression audit: ensure public-facing Partiu branding does not return.

Scan tracked application source, not historical test fixtures. Compatibility-
sensitive identifiers are explicitly allowlisted by file and exact substring.
"""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# These old values have stable semantics and must not be rebranded in place.
LEGACY = {
    "backend/auth/audit_log.py": ("partiu.audit",),
    "backend/crypto.py": ("partiu-at-rest-v1",),
    "backend/database.py": ("partiu.db", "Partiu DB"),
    "backend/routes/version.py": ("PARTIU_VERSION",),
    "backend/trips/ical_service.py": ("@partiu",),
    "frontend/src/lib/apiCache.ts": ("partiu-api-", "Partiu API"),
    "frontend/src/lib/notifications.ts": ("partiu_push_enabled", "Partiu PWA"),
}


def audit() -> None:
    failures: list[str] = []

    manifest = json.loads((ROOT / "frontend/public/manifest.json").read_text())
    if manifest.get("id") != "/" or manifest.get("scope") != "/":
        failures.append("PWA manifest must have explicit stable id and scope")
    html = (ROOT / "frontend/index.html").read_text()
    if 'href="/manifest.json?v=6"' not in html or 'crossorigin="use-credentials"' in html:
        failures.append("PWA manifest must be referenced without credentials (public Access bypass)")
    if 'rel="icon" type="image/png" sizes="192x192" href="/icon-192.png?v=5"' not in html:
        failures.append("HTML must provide a 192px PNG fallback icon for Android")
    install_page = (ROOT / "frontend/public/pwa-install.html").read_text()
    if '<link rel="manifest" href="/manifest.json?v=6"' not in install_page:
        failures.append("Public PWA install page must reference the canonical manifest")
    if 'href="/pwa-install.html"' not in (ROOT / "frontend/src/pages/SettingsPage.svelte").read_text():
        failures.append("Settings must link to the official public PWA install page")
    if '<a class="open-link" href="/">Open MyTrips</a>' not in install_page:
        failures.append("Public PWA install page must link back to the protected app")
    if 'href="/icon-192.png?v=5"' not in install_page:
        failures.append("Public PWA install page must reference approved icon")
    if "navigator.serviceWorker.register('/sw.js'" not in install_page:
        failures.append("Public PWA install page must register the existing service worker")

    if manifest.get("name") != "MyTrips" or manifest.get("short_name") != "MyTrips":
        failures.append("PWA manifest name and short_name must both be MyTrips")

    # Assert the approved app artwork reaches each public icon endpoint.
    icons = {
        "frontend/public/icon-192.png": 192,
        "frontend/public/icon-512.png": 512,
        "frontend/public/icon-maskable-512.png": 512,
        "frontend/public/apple-touch-icon.png": 180,
        "frontend/public/mytrips-brand.png": 64,
        "frontend/public/mytrips-original-A.png": 393,
    }
    for rel, expected_size in icons.items():
        raw = (ROOT / rel).read_bytes()
        if not raw.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10])):
            failures.append(f"{rel}: not a PNG")
            continue
        width, height = struct.unpack(">II", raw[16:24])
        if (width, height) != (expected_size, expected_size):
            failures.append(f"{rel}: expected {expected_size}x{expected_size}, got {width}x{height}")

    ico_path = ROOT / "frontend/public/favicon.ico"
    if ico_path.read_bytes()[:4] != bytes([0, 0, 1, 0]):
        failures.append("favicon.ico has invalid ICO header")
    # Mirror the proven Smart Meter Texas Android manifest selection: one
    # 192px ordinary icon, one 512px image usable as BOTH any and maskable.
    expected_icon_purposes = {
        ("192x192", "any", "/icon-192.png?v=5"),
        ("512x512", "any maskable", "/icon-maskable-512.png?v=5"),
    }
    actual_icon_purposes = {
        (icon.get("sizes"), icon.get("purpose", "any"), icon.get("src"))
        for icon in manifest.get("icons", [])
    }
    if actual_icon_purposes != expected_icon_purposes:
        failures.append("PWA icons must follow the Smart Meter Texas any/maskable pattern")
    for name in ("SetupPage", "LoginPage"):
        rel = f"frontend/src/pages/{name}.svelte"
        if '/mytrips-brand.png?v=3' not in (ROOT / rel).read_text():
            failures.append(f"{rel}: brand image missing")

    explicit = {
        "frontend/index.html": (
            "<title>MyTrips</title>",
            'name="apple-mobile-web-app-title" content="MyTrips"',
            '/favicon.ico?v=3',
            '/apple-touch-icon.png?v=3',
        ),
        "frontend/sw.js": ("title: 'MyTrips'", "mytrips-static-", "mytrips-api-", "const CACHE_VERSION = 'v24'"),
        "frontend/src/components/SideRail.svelte": (
            "https://github.com/lurrnet/mytrips",
            '/mytrips-brand.png?v=3',
        ),
        "frontend/src/pages/SettingsPage.svelte": (
            "https://github.com/lurrnet/mytrips/releases",
        ),
        "frontend/src/lib/apiCache.ts": ("mytrips-api-", "partiu-api-"),
        "frontend/src/lib/notifications.ts": (
            "mytrips_push_enabled",
            "partiu_push_enabled",
        ),
        "backend/main.py": ('title="MyTrips"',),
        "backend/routes/version.py": (
            'GITHUB_REPO = "lurrnet/mytrips"',
            "MYTRIPS_VERSION",
        ),
        "backend/auth/twofa_service.py": ('issuer_name="MyTrips"',),
        "backend/trips/ical_service.py": ("PRODID:-//MyTrips//Trip Export//EN",),
        "backend/integrations/photon/client.py": ("MyTrips/0.1",),
        "backend/integrations/wikipedia/client.py": ("MyTrips/0.1",),
        "frontend/package.json": ('"name": "mytrips-frontend"',),
        "frontend/package-lock.json": ('"name": "mytrips-frontend"',),
    }
    for rel, needles in explicit.items():
        value = (ROOT / rel).read_text()
        for needle in needles:
            if needle not in value:
                failures.append(f"{rel}: missing expected brand value {needle!r}")

    for lang in ("en", "pt-BR"):
        rel = f"frontend/src/locales/{lang}.json"
        translations = json.loads((ROOT / rel).read_text())
        for key, value in translations.items():
            if isinstance(value, str) and re.search(r"partiu", value, re.I):
                failures.append(f"{rel}:{key}: stale Partiu brand")
        for key in ("setup.title", "login.title", "notif.test_title", "nav.project"):
            if "MyTrips" not in translations.get(key, ""):
                failures.append(f"{rel}:{key}: missing MyTrips")

    scan = list((ROOT / "frontend/src").rglob("*")) + list(
        (ROOT / "backend").rglob("*.py")
    )
    scan.extend((ROOT / "frontend/sw.js", ROOT / "frontend/index.html"))
    for path in scan:
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if path.name.endswith((".test.ts", ".spec.ts")) or "/tests/" in rel:
            continue
        if rel.startswith("frontend/src/locales/"):
            continue
        if path.suffix not in (".py", ".svelte", ".ts", ".js", ".json", ".css", ".html"):
            continue
        for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if not re.search("partiu", line, re.I):
                continue
            cleaned = line
            for allowed in LEGACY.get(rel, ()):
                cleaned = re.sub(re.escape(allowed), "", cleaned, flags=re.I)
            if re.search("partiu", cleaned, re.I):
                failures.append(f"{rel}:{lineno}: {line.strip()[:160]}")

    if failures:
        raise SystemExit("Brand audit FAILED:\n" + "\n".join(failures))
    print("MyTrips full brand audit: PASS")


if __name__ == "__main__":
    audit()
