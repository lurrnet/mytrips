#!/usr/bin/env python3
"""Regression audit: ensure public-facing Partiu branding does not return.

Scan tracked application source, not historical test fixtures. Compatibility-
sensitive identifiers are explicitly allowlisted by file and exact substring.
"""
from __future__ import annotations

import json
import re
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
    if manifest.get("name") != "MyTrips" or manifest.get("short_name") != "MyTrips":
        failures.append("PWA manifest name and short_name must both be MyTrips")

    explicit = {
        "frontend/index.html": (
            "<title>MyTrips</title>",
            'name="apple-mobile-web-app-title" content="MyTrips"',
        ),
        "frontend/sw.js": ("title: 'MyTrips'", "mytrips-static-", "mytrips-api-"),
        "frontend/src/components/SideRail.svelte": (
            "https://github.com/lurrnet/mytrips",
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
