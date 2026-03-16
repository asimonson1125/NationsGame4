const CACHE_NAME = 'nations-engine-v2';
const CDN_ASSETS = new Set([
  'https://unpkg.com/htmx.org@1.9.12',
  'https://unpkg.com/alpinejs@3.14.1/dist/cdn.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css'
]);

function shouldCache(request) {
  const url = new URL(request.url);
  // Same-origin static/uploaded assets only
  if (url.origin === self.location.origin) {
    return url.pathname.startsWith('/static/') || url.pathname.startsWith('/uploads/');
  }
  // Explicit CDN assets
  return CDN_ASSETS.has(url.href);
}

// Install: pre-cache CDN assets and core static files
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll([
      '/static/css/style.css',
      '/static/fonts/inter-latin.woff2',
      '/static/images/logo.svg',
      ...CDN_ASSETS
    ]))
  );
});

// Activate: purge old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
});

// Fetch: cache-first for static assets, ignore everything else
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  if (!shouldCache(event.request)) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (response.ok) {
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, response.clone()));
        }
        return response;
      }).catch(() => new Response('', { status: 503, statusText: 'Service Unavailable' }));
    })
  );
});
