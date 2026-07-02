const CACHE_NAME = 'akash-hrm-cache-v1';
const urlsToCache = [
  '/',
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/img/favicon.svg'
];

// Install a service worker
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
  );
});

// Network-First with Cache Fallback for navigation requests, Cache-First for static assets
self.addEventListener('fetch', event => {
  // Only intercept HTTP/S GET requests
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  // Cache-First for static assets (images, css, js files)
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request)
        .then(cachedResponse => {
          if (cachedResponse) {
            return cachedResponse;
          }
          return fetch(event.request).then(networkResponse => {
            if (!networkResponse || networkResponse.status !== 200) {
              return networkResponse;
            }
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then(cache => {
              cache.put(event.request, responseToCache);
            });
            return networkResponse;
          });
        })
    );
  } else {
    // Network-First with Cache Fallback for HTML routing pages to ensure real-time data access
    event.respondWith(
      fetch(event.request)
        .then(networkResponse => {
          // If online, return response immediately
          return networkResponse;
        })
        .catch(() => {
          // If offline, try serving the index/root cached response
          return caches.match(event.request);
        })
    );
  }
});

// Update a service worker
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});
