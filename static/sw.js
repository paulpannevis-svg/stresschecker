// Geen fetch-handler: deze service worker cachet NIETS (alle requests gaan rechtstreeks naar
// het netwerk). Een eerdere versie cachete wel HTML, waardoor oude tabbladen na een deploy
// verouderde UI toonden (o.a. het 'ingeklemde' /view-rapport). Bij activatie wist deze worker
// daarom ALLE bestaande cache-opslag, zodat zo'n stale cache op elk apparaat wordt opgeruimd
// zodra de browser deze (gewijzigde) sw.js oppikt.
self.addEventListener('install', function (e) { self.skipWaiting(); });
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys()
      .then(function (keys) { return Promise.all(keys.map(function (k) { return caches.delete(k); })); })
      .then(function () { return clients.claim(); })
  );
});
