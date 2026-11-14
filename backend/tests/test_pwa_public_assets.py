"""Public PWA endpoints must fail closed under the Cloudflare /pwa/* Bypass."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.main as main
from backend.main import app


def test_public_pwa_directory_allows_only_reviewed_static_files():
    with TestClient(app) as client:
        for name, mime in (
            ("install.html", "text/html"),
            ("install.js", "text/javascript"),
            ("manifest.json", "application/manifest+json"),
            ("sw.js", "text/javascript"),
            ("icon-192.png", "image/png"),
            ("icon-maskable-512.png", "image/png"),
            ("apple-touch-icon.png", "image/png"),
        ):
            response = client.get(f"/pwa/{name}")
            assert response.status_code == 200, (name, response.text[:150])
            assert response.headers["content-type"].startswith(mime)
        assert client.get("/pwa/sw.js").headers["service-worker-allowed"] == "/"
        installer = client.get("/pwa/install.html")
        assert installer.headers["cache-control"] == "no-store, no-transform"
        assert "script-src 'self'" in installer.headers["content-security-policy"]
        assert "unsafe-inline" not in installer.headers["content-security-policy"]
        assert "no-transform" not in client.get("/pwa/manifest.json").headers["cache-control"]


def test_public_pwa_directory_unknown_paths_return_real_404_not_spa_html():
    with TestClient(app) as client:
        for path in (
            "/pwa/not-found.js", "/pwa/private.json", "/pwa/foo/bar.js",
            "/pwa/.env", "/pwa/install.html/extra", "/pwa/",
            "/pwa/no-such-file.png",
        ):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 404, (path, response.status_code)
            assert not response.headers.get("content-type", "").startswith("text/html")


def test_public_pwa_allowlist_is_explicit_and_contains_no_secrets():
    from backend.main import _PUBLIC_PWA_FILES

    assert _PUBLIC_PWA_FILES == {
        "install.html", "install.js", "manifest.json", "sw.js",
        "icon-192.png", "icon-512.png", "icon-maskable-512.png",
        "apple-touch-icon.png",
    }
    for name in _PUBLIC_PWA_FILES:
        assert (Path(__file__).resolve().parents[2] / "frontend" / "public" / "pwa" / name).is_file()



def test_public_pwa_symlink_is_rejected_even_for_an_allowlisted_file(tmp_path, monkeypatch):
    public = tmp_path / "pwa"
    public.mkdir()
    (public / "icon-192.png").symlink_to(Path(__file__).resolve())
    monkeypatch.setattr(main, "_FRONTEND_DIR", tmp_path)
    with pytest.raises(HTTPException) as exc:
        main._pwa_asset("icon-192.png")
    assert exc.value.status_code == 404
