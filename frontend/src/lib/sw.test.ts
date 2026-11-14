/**
 * Privacy regression tests for the MyTrips PWA Service Worker.
 *
 * The SW must never read or write cached API responses. Earlier versions
 * cached trips and authentication responses under cache names shared across
 * accounts; upgrading must remove these caches before claiming clients.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import swSource from '../../public/pwa/sw.js?raw';

type FetchHandler = (event: FakeFetchEvent) => void;
type ActivateHandler = (event: FakeLifecycleEvent) => void;

interface FakeFetchEvent {
  request: Request;
  respondWith: (r: Response | Promise<Response>) => void;
  waitUntil: (p: Promise<unknown>) => void;
}
interface FakeLifecycleEvent {
  waitUntil: (p: Promise<unknown>) => void;
}

let fetchHandler: FetchHandler;
let activateHandler: ActivateHandler;
let cacheEntries: Map<string, Map<string, Response>>;
let cachedNames: Set<string>;
let timeline: string[];

function loadServiceWorker() {
  timeline = [];
  cachedNames = new Set([
    'mytrips-api-v24',
    'partiu-api-v6',
    'mytrips-static-v24',
    'mytrips-static-v25',
    'other-app-data',
  ]);
  cacheEntries = new Map();
  const openCache = (name: string) => {
    if (!cacheEntries.has(name)) cacheEntries.set(name, new Map());
    cachedNames.add(name);
    const entries = cacheEntries.get(name)!;
    return {
      keys: async () => [...entries.keys()].map((url) => new Request(url)),
      delete: async (req: Request | string) => entries.delete(typeof req === 'string' ? req : req.url),
      match: async (req: Request) => {
        timeline.push('cache-match');
        return entries.get(req.url);
      },
      put: async (req: Request, res: Response) => {
        timeline.push('cache-put');
        entries.set(req.url, res);
      },
    };
  };

  const listeners: Record<string, (event: any) => void> = {};
  const self = {
    addEventListener: (type: string, fn: (event: any) => void) => { listeners[type] = fn; },
    location: { origin: 'https://mytrips.test' },
    clients: { claim: async () => { timeline.push('claim'); } },
    skipWaiting: () => {},
  };
  const caches = {
    open: async (name: string) => openCache(name),
    keys: async () => [...cachedNames],
    delete: async (name: string) => {
      timeline.push('delete:' + name);
      cacheEntries.delete(name);
      return cachedNames.delete(name);
    },
    match: async (req: Request) => {
      timeline.push('global-cache-match');
      for (const map of cacheEntries.values()) {
        const hit = map.get(req.url);
        if (hit) return hit;
      }
      return undefined;
    },
  };

  new Function('self', 'caches', 'fetch', swSource)(
    self,
    caches,
    (...args: [RequestInfo, RequestInit?]) => globalThis.fetch(...args),
  );
  fetchHandler = listeners.fetch as FetchHandler;
  activateHandler = listeners.activate as ActivateHandler;
  return { openCache };
}

function dispatch(request: Request): Promise<Response> {
  let response: Promise<Response> | undefined;
  fetchHandler({
    request,
    respondWith: (value) => { response = Promise.resolve(value); },
    waitUntil: () => {},
  });
  if (!response) throw new Error('The worker did not respond to this request');
  return response;
}

describe('privacy-first service worker', () => {
  beforeEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it.each([
    ['GET', '/api/trips', undefined],
    ['GET', '/api/auth/me', undefined],
    ['GET', '/api', undefined],
    ['POST', '/api/auth/login', '{}'],
    ['PUT', '/api/trips/t1/budget', '{}'],
    ['DELETE', '/api/trips/t1', undefined],
  ])('uses network only for %s %s', async (method, path, body) => {
    const { openCache } = loadServiceWorker();
    openCache('mytrips-api-v24').put(
      new Request('https://mytrips.test' + path),
      new Response('{"private":"OLD ACCOUNT"}'),
    );
    timeline = [];
    vi.stubGlobal('fetch', vi.fn(async () => {
      timeline.push('network');
      return new Response('{"private":"CURRENT ACCOUNT"}', { status: 200 });
    }));

    const init: RequestInit = { method };
    if (body !== undefined) init.body = body;
    const response = await dispatch(new Request('https://mytrips.test' + path, init));
    expect(await response.json()).toEqual({ private: 'CURRENT ACCOUNT' });
    expect(timeline).toEqual(['network']);
  });

  it('fails a disconnected API fetch instead of falling back to stale private data', async () => {
    loadServiceWorker();
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline'); }));
    await expect(dispatch(new Request('https://mytrips.test/api/trips'))).rejects.toThrow('offline');
    expect(timeline).not.toContain('cache-match');
  });

  it('deletes legacy API caches before claiming clients', async () => {
    loadServiceWorker();
    const work: Promise<unknown>[] = [];
    activateHandler({ waitUntil: (promise) => { work.push(promise); } });
    await Promise.all(work);
    expect(cachedNames.has('mytrips-api-v24')).toBe(false);
    expect(cachedNames.has('partiu-api-v6')).toBe(false);
    expect(cachedNames.has('mytrips-static-v24')).toBe(false);
    expect(cachedNames.has('mytrips-static-v25')).toBe(true);
    expect(cachedNames.has('other-app-data')).toBe(true);
    expect(timeline.at(-1)).toBe('claim');
  });

  it('never intercepts cross-origin requests', () => {
    loadServiceWorker();
    let responded = false;
    fetchHandler({
      request: new Request('https://basemaps.cartocdn.com/tile.png'),
      respondWith: () => { responded = true; },
      waitUntil: () => {},
    });
    expect(responded).toBe(false);
  });

  it('does not intercept same-origin document downloads or installation resources', () => {
    loadServiceWorker();
    for (const path of ['/api/health', '/pwa/manifest.json', '/pwa/icon-192.png', '/documents/trip.pdf']) {
      let intercepted = false;
      fetchHandler({
        request: new Request('https://mytrips.test' + path),
        respondWith: () => { intercepted = true; },
        waitUntil: () => {},
      });
      expect(intercepted).toBe(path === '/api/health');
    }
  });

  it('caches fingerprinted static assets but not dynamic responses', async () => {
    loadServiceWorker();
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response('const x=1', {
        status: 200,
        headers: { 'content-type': 'application/javascript' },
      }),
    ));
    const req = new Request('https://mytrips.test/assets/index-hash.js');
    await dispatch(req);
    expect(timeline).toContain('cache-put');
    timeline = [];
    await dispatch(req);
    expect(timeline).toContain('cache-match');
    expect(timeline).not.toContain('cache-put');
  });

  it('caches only root app-shell HTML on navigation, never other HTML routes', async () => {
    loadServiceWorker();
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response('<html>SPA</html>', { status: 200, headers: { 'content-type': 'text/html' } }),
    ));
    // Mode cannot be set in RequestInit; create an actual document navigation request.
    const navigation = (url: string) => ({ url, method: 'GET', mode: 'navigate' }) as Request;
    const rootResponse = await dispatch(navigation('https://mytrips.test/'));
    expect(rootResponse.ok).toBe(true);
    expect(timeline).toContain('cache-put');
    timeline = [];
    await dispatch(navigation('https://mytrips.test/private-document'));
    expect(timeline).not.toContain('cache-put');
  });
});
