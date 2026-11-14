"""
Ensures the service worker script and SPA shell are never cached by the
browser, so a new deploy is picked up promptly instead of being served
stale (the bug this guards against: PWA users on mobile not seeing new
versions until they reinstall the app).
"""

import backend.main as main


class TestStaticCacheHeaders:
    def test_sw_js_is_not_cached_and_allows_root_scope(self):
        response = main.serve_sw()
        assert response.headers.get("cache-control") == "no-cache"
        assert response.headers.get("service-worker-allowed") == "/"

    def test_manifest_uses_canonical_pwa_file(self):
        response = main.serve_manifest()
        assert response.path.endswith("/pwa/manifest.json")
        assert response.headers.get("content-type") == "application/manifest+json"
        assert response.headers.get("cache-control") == "no-cache"

    def test_spa_shell_is_not_cached(self):
        response = main.serve_spa("some/client/route")
        assert response.headers.get("cache-control") == "no-cache"
