const CACHE_NAME = 'bridgeclub-v3';
const APP_SHELL = ['/', '/static/style.css', '/offline'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Only handle GET requests
  if (event.request.method !== 'GET') return;

  event.respondWith(
    fetch(event.request)
      // Ingelogde pagina's bevatten persoonlijke gegevens en worden bewust
      // niet gecachet; offline valt de app terug op de app-shell/offline-pagina.
      .catch(() =>
        caches.match(event.request).then(
          (cached) => cached || caches.match('/offline')
        )
      )
  );
});
