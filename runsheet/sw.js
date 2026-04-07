// sw.js — self-destruct version
// Clears all caches and unregisters itself so the browser fetches everything fresh.

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .then(() => self.clients.claim())
      .then(() => self.registration.unregister())
      .then(() => {
        return self.clients.matchAll({ type: 'window' }).then(clients => {
          clients.forEach(client => client.navigate(client.url));
        });
      })
  );
});

self.addEventListener('fetch', e => {
  e.respondWith(fetch(e.request));
});
