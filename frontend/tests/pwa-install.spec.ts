import { test, expect } from '@playwright/test';

/**
 * Runtime gate: HTTP 200 and Manifest parsing alone cannot detect an inline
 * installer script blocked by script-src 'self', or an invisible broken logo.
 * This is required in CI even when unrelated full E2E tests remain advisory.
 */
test('public installer executes under CSP with real visible artwork', async ({ page }) => {
  const cspErrors: string[] = [];
  page.on('console', (msg) => {
    if (/content security policy|refused to execute|refused to load/i.test(msg.text())) {
      cspErrors.push(msg.text());
    }
  });
  page.on('pageerror', (error) => cspErrors.push(error.message));

  const response = await page.goto('/pwa/install.html');
  expect(response?.status()).toBe(200);
  await expect(page.locator('#manifest-status')).toContainText('PASS', { timeout: 15000 });
  await expect(page.locator('#icon-status')).toContainText('PASS', { timeout: 15000 });
  await expect(page.locator('#worker-status')).toContainText('PASS', { timeout: 15000 });
  await expect(page.locator('img.logo')).toBeVisible();
  const image = await page.locator('img.logo').evaluate((img) => ({
    width: (img as HTMLImageElement).naturalWidth,
    source: new URL((img as HTMLImageElement).currentSrc).pathname,
  }));
  expect(image.width).toBe(192);
  expect(image.source).toBe('/pwa/icon-192.png');

  const registration = await page.evaluate(async () => {
    const worker = await navigator.serviceWorker.ready;
    return { scope: worker.scope, scriptURL: worker.active?.scriptURL };
  });
  expect(registration.scope).toBe('http://localhost:8000/');
  expect(registration.scriptURL).toBe('http://localhost:8000/pwa/sw.js');
  expect(cspErrors).toEqual([]);
});

test('unknown public assets return real 404, never SPA shell HTML', async ({ request }) => {
  for (const path of ['/pwa/not-found.js', '/pwa/private.json', '/pwa/.env', '/pwa/nested/secret.js']) {
    const res = await request.get(path, { maxRedirects: 0 });
    expect(res.status(), path).toBe(404);
    expect(res.headers()['content-type']).not.toContain('text/html');
  }
});
