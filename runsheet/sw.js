// sw.js — self-destruct version
// Clears all caches and unregisters itself. No reload to avoid loops.

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .then(() => self.clients.claim())
      .then(() => self.registration.unregister())
  );
});

self.addEventListener('fetch', e => {
  e.respondWith(fetch(e.request));
});
