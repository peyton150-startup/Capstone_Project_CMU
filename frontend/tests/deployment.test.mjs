import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';

const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'));
const vite = readFileSync(new URL('../vite.config.ts', import.meta.url), 'utf8');

test('Vercel proxies the versioned API to the existing Render backend before the SPA fallback', () => {
  assert.deepEqual(config.rewrites, [
    {
      source: '/api/:path*',
      destination: 'https://capstone-project-cmu.onrender.com/api/:path*',
    },
    { source: '/(.*)', destination: '/index.html' },
  ]);
});

test('proxied operator responses cannot be cached at the browser or Vercel edge', () => {
  const apiHeaders = config.headers.find(rule => rule.source === '/api/:path*');
  assert.ok(apiHeaders, 'expected API-specific cache headers');
  const headers = Object.fromEntries(apiHeaders.headers.map(({ key, value }) => [key.toLowerCase(), value]));
  assert.match(headers['cache-control'], /no-store/);
  assert.equal(headers['vercel-cdn-cache-control'], 'no-store');
  assert.equal(headers['x-vercel-enable-rewrite-caching'], '0');
});

test('Vite has independent localhost and Render proxy routes', () => {
  assert.match(vite, /'\/api': \{ target: 'http:\/\/127\.0\.0\.1:8000'/);
  assert.match(vite, /'\/render-api': \{/);
  assert.match(vite, /https:\/\/capstone-project-cmu\.onrender\.com/);
  assert.match(vite, /rewrite: path => path\.replace/);
});
