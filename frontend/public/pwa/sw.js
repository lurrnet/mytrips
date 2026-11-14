/**
 * Service Worker for MyTrips PWA.
 *
 * Privacy-first strategies:
 *   - /api and /api/* (ALL methods) → network only; no CacheStorage reads/writes
 *   - /assets/* and /fonts/*       → cache-first (non-sensitive static assets)
 *   - HTML navigation             → network-first; cache only successful app-shell HTML
 *   - everything else             → browser network (not cached by this worker)
 *
 * On activation, erase old MyTrips/Partiu API caches, which may contain
 * private trip data from previous accounts. Cross-origin traffic is untouched.
 */

const CACHE_VERSION = 'v25';
const STATIC_CACHE = `mytrips-static-${CACHE_VERSION}`;
const STATIC_CACHE_MAX = 80; // cap cached app-shell and static files

const trimInProgress = new Set();

// ---- Install: skip waiting immediately ----
self.addEventListener('install', () => {
  self.skipWaiting();
});

// ---- Activate: erase legacy private API caches and old shell versions ----
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names
      .filter((name) =>
        name.startsWith('mytrips-api-') ||
        name.startsWith('partiu-api-') ||
        name.startsWith('partiu-static-') ||
        (name.startsWith('mytrips-static-') && name !== STATIC_CACHE)
      )
      .map((name) => caches.delete(name)));
    // Claim clients only after old private caches are removed.
    await self.clients.claim();
  })());
});

// ---- Fetch: only shell/static files are eligible for caching ----
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Leave cross-origin requests entirely to the browser.
  if (url.origin !== self.location.origin) return;

  // Every API request, including login/authentication and mutations, goes
  // straight to the network. Never fall back to stale account data on failure.
  if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }

  // No non-GET response is ever stored in CacheStorage.
  if (request.method !== 'GET') return;

  // Installation resources must always be fetched fresh. In particular, do
  // not accidentally cache a Cloudflare Access challenge under a PWA URL.
  if (url.pathname.startsWith('/pwa/')) return;

  // Fingerprinted JS/CSS and self-hosted fonts contain no user records.
  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/fonts/')) {
    event.respondWith(cacheFirstStatic(request));
    return;
  }

  // App navigation is network-first; only the static HTML shell is cached.
  // Other same-origin resources (e.g. private documents) stay network-only.
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstShell(request));
  }
});

// ---- Limited, non-sensitive cache strategies ----

async function cacheFirstStatic(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  // Never store a redirect (for example, Cloudflare Access sign-in HTML).
  if (response.ok && !response.redirected) {
    await cache.put(request, response.clone());
    try { await trimCache(cache, STATIC_CACHE_MAX); } catch (e) { console.warn('[SW] trimCache error', e); }
  }
  return response;
}

async function networkFirstShell(request) {
  const cache = await caches.open(STATIC_CACHE);
  try {
    const response = await fetch(request);
    const url = new URL(request.url);
    const isShellPath = url.pathname === '/' || url.pathname === '/index.html';
    const isHtml = response.headers.get('content-type')?.toLowerCase().includes('text/html');
    if (isShellPath && isHtml && response.ok && !response.redirected) {
      await cache.put(request, response.clone());
      try { await trimCache(cache, STATIC_CACHE_MAX); } catch (e) { console.warn('[SW] trimCache error', e); }
    }
    return response;
  } catch {
    // Old CacheStorage versions are not consulted (they may contain private data).
    const cached = await cache.match(request);
    if (cached) return cached;
    return new Response('<h1>Offline</h1>', {
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
      status: 503,
    });
  }
}

// ---- Cache size management ----

async function trimCache(cache, maxEntries) {
  if (trimInProgress.has(cache)) return;
  trimInProgress.add(cache);
  try {
    const keys = await cache.keys();
    if (keys.length > maxEntries) {
      // Cache API returns keys in insertion order; delete the oldest excess
      const toDelete = keys.slice(0, keys.length - maxEntries);
      await Promise.all(toDelete.map((k) => cache.delete(k)));
    }
  } catch (e) {
    console.warn('[SW] trimCache failed', e);
  } finally {
    trimInProgress.delete(cache);
  }
}

// ---- Push notifications ----
self.addEventListener('push', (event) => {
  console.log('[SW] push event received', event.data ? 'with data' : 'no data');
  if (!event.data) return;

  let payload = { title: 'MyTrips', body: '', url: '/' };
  try {
    payload = { ...payload, ...event.data.json() };
  } catch {
    payload.body = event.data.text();
  }

  console.log('[SW] showing notification:', payload.title);
  const badgeCount = typeof payload.badge === 'number' ? payload.badge : undefined;
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/pwa/icon-192.png',
      data: { url: payload.url },
    }).then(() => {
      console.log('[SW] notification shown OK');
      if (badgeCount !== undefined && 'setAppBadge' in self.registration) {
        return self.registration.setAppBadge(badgeCount);
      }
    }).catch((err) => {
      console.error('[SW] showNotification failed:', err);
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data?.url || '/';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.postMessage({ type: 'navigate', url });
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
