const CACHE = 'inventario-v1';

const PRECACHE = [
  '/',
  '/dashboard',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
  'https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap',
];

// Instalar: pre-cachear recursos estáticos
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

// Activar: limpiar cachés viejos
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch: network-first para páginas HTML, cache-first para estáticos
self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  // Solo interceptar requests del mismo origen o CDNs conocidas
  const isStatic = url.pathname.startsWith('/static/') ||
                   url.hostname.includes('jsdelivr.net') ||
                   url.hostname.includes('fonts.googleapis.com') ||
                   url.hostname.includes('fonts.gstatic.com');

  if (isStatic) {
    // Cache-first: devuelve caché si existe, si no va a red y cachea
    e.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(resp => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE).then(c => c.put(request, clone));
          }
          return resp;
        });
      })
    );
    return;
  }

  // Para rutas de la app (HTML/JSON): network-first con fallback offline
  if (request.mode === 'navigate') {
    e.respondWith(
      fetch(request).catch(() =>
        caches.match('/dashboard') || caches.match('/')
      )
    );
  }
});
