// sw.js — Service worker for Stoic-Hume V5 CI Dashboard
// Freebuff Electron webview cache bypass + offline resilience.
//
// Her fetch isteginde Cache-Control: no-cache uygular; eski caches
// varsa activate'te temizler. Skip-waiting yaparak yeni sürümün
// sayfa yeniden yüklenmeden devralmasini saglar (clients.claim).
const CACHE_NAME = 'stoic-hume-v5-v1';

// Install: yeni worker hemen devralsin — beklemesin.
self.addEventListener('install', (event) => {
  self.skipWaiting();
});

// Activate: tum eski cache'leri temizle + tum client'lari claim et.
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: her istege cache-busting header'lar ekle.
// navigate isteklerinde (sayfa yukleme) html dahi olsa
// no-cache zorla.
self.addEventListener('fetch', (event) => {
  // API endpoint'leri: network-first, cache'e dokunma.
  if (event.request.url.includes('/api/')) {
    event.respondWith(fetch(event.request, { cache: 'no-cache' }));
    return;
  }

  // Statik dosyalar (html, js, css): network-first, cache'i atla.
  event.respondWith(
    fetch(event.request, { cache: 'no-cache' }).catch(() => {
      // Network yoksa (offline) — bos yanit; dashboard SSE ile zaten
      // baglanamayacagi icin anlamli bir fallback yok.
      return new Response('', { status: 503, statusText: 'Offline' });
    })
  );
});