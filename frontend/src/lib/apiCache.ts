/**
 * Defense-in-depth purge for pre-v25 service-worker API caches at account
 * boundaries. The current Service Worker uses network-only for all /api/*
 * requests and deletes legacy API caches during activation. Keep this helper
 * on login and logout because a user can open the app before SW activation
 * completes, or have an older installation on a shared device.
 */
// Keep legacy cache support to prevent cross-account data leakage after upgrade.
const API_CACHE_PREFIXES = ['mytrips-api-', 'partiu-api-'];

export async function purgeApiCache(): Promise<void> {
  if (typeof caches === 'undefined') return;
  try {
    const names = await caches.keys();
    await Promise.all(
      names.filter((n) => API_CACHE_PREFIXES.some((prefix) => n.startsWith(prefix))).map((n) => caches.delete(n)),
    );
  } catch {
    // CacheStorage may be unavailable or blocked in private browsing.
    // The network-only worker never falls back to cached account data.
  }
}
