const CACHE = 'inventario-v4';

const PRECACHE = [
  '/offline',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
  'https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap',
];

// Rutas de la app que se cachean en background (stale-while-revalidate)
const APP_ROUTES = [
  '/',
  '/dashboard',
  '/inventario',
  '/productos',
  '/ordenes',
  '/proyectos-oc',
  '/reportes',
];

// Instalar: pre-cachear recursos críticos
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

// Activar: limpiar cachés viejos
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// ── ESTRATEGIAS DE FETCH ──────────────────────────────────────────────────────
self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  // Ignorar requests que no sean GET
  if (request.method !== 'GET') return;

  // Ignorar extensiones de Chrome u otros esquemas no-http
  if (!url.protocol.startsWith('http')) return;

  const isStatic = url.pathname.startsWith('/static/') ||
                   url.hostname.includes('jsdelivr.net') ||
                   url.hostname.includes('fonts.googleapis.com') ||
                   url.hostname.includes('fonts.gstatic.com');

  // ── Cache-first para estáticos y CDN ──
  if (isStatic) {
    e.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(resp => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE).then(c => c.put(request, clone));
          }
          return resp;
        }).catch(() => cached || Response.error());
      })
    );
    return;
  }

  // ── Stale-while-revalidate para rutas de la app ──
  if (request.mode === 'navigate') {
    e.respondWith(
      caches.open(CACHE).then(async cache => {
        const cached = await cache.match(request);

        const networkFetch = fetch(request).then(resp => {
          if (resp.ok) cache.put(request, resp.clone());
          return resp;
        }).catch(() => null);

        // Si hay caché, devuélvelo inmediatamente y refresca en background
        if (cached) {
          // Actualizar en background sin bloquear
          networkFetch.catch(() => {});
          return cached;
        }

        // Sin caché: esperar la red; si falla, servir /offline
        const resp = await networkFetch;
        if (resp) return resp;

        const offlinePage = await cache.match('/offline');
        return offlinePage || new Response('Sin conexión', { status: 503 });
      })
    );
    return;
  }

  // ── Network-first para API y otros JSON ──
  if (url.pathname.startsWith('/api/') || request.headers.get('accept')?.includes('application/json')) {
    e.respondWith(
      fetch(request).catch(() =>
        new Response(JSON.stringify({ ok: false, error: 'Sin conexión' }), {
          headers: { 'Content-Type': 'application/json' },
          status: 503,
        })
      )
    );
    return;
  }
});

// ── BACKGROUND SYNC ──────────────────────────────────────────────────────────
const _IDB_NAME  = 'inventario-offline';
const _IDB_VER   = 1;
const _IDB_STORE = 'pending_ops';

function _swOpenDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(_IDB_NAME, _IDB_VER);
        req.onupgradeneeded = e => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(_IDB_STORE))
                db.createObjectStore(_IDB_STORE, { keyPath: 'id', autoIncrement: true });
        };
        req.onsuccess = e => resolve(e.target.result);
        req.onerror   = e => reject(e.target.error);
    });
}

function _swGetAll(db) {
    return new Promise((resolve, reject) => {
        const req = db.transaction(_IDB_STORE, 'readonly').objectStore(_IDB_STORE).getAll();
        req.onsuccess = () => resolve(req.result);
        req.onerror   = () => reject(req.error);
    });
}

function _swRemove(db, id) {
    return new Promise((resolve, reject) => {
        const req = db.transaction(_IDB_STORE, 'readwrite').objectStore(_IDB_STORE).delete(id);
        req.onsuccess = () => resolve();
        req.onerror   = () => reject(req.error);
    });
}

async function _syncWithServer() {
    const db  = await _swOpenDB();
    const ops = await _swGetAll(db);
    if (!ops.length) return;

    // Obtener CSRF desde las cookies (Flask lo pone en 'csrf_token' cookie)
    const csrf = _getCookieCSRF();

    const resp = await fetch('/api/sync', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body:    JSON.stringify({ operations: ops }),
    });

    if (!resp.ok) return;
    const data = await resp.json();

    let okCount = 0;
    const errors = [];

    for (const result of data.results) {
        if (result.ok) {
            await _swRemove(db, result.id);
            okCount++;
        } else {
            errors.push(result.error);
        }
    }

    // Notificar al usuario si hay clientes abiertos
    const clientList = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clientList) {
        client.postMessage({ type: 'SYNC_RESULT', okCount, errors });
    }

    // Notificación push local si no hay ventana activa
    if (!clientList.length && okCount > 0) {
        self.registration.showNotification('Sincronización completada', {
            body:  `${okCount} operación(es) offline sincronizada(s).`,
            icon:  '/static/icons/icon-192.png',
            badge: '/static/icons/icon-192.png',
        });
    }
}

function _getCookieCSRF() {
    const match = self.cookie && self.cookie.match(/csrf_token=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    // fallback: vacío (Flask-WTF también acepta X-CSRFToken vacío para rutas con @login_required)
    return '';
}

self.addEventListener('sync', e => {
    if (e.tag === 'sync-inventario') {
        e.waitUntil(_syncWithServer());
    }
});

// Escuchar mensajes desde la página para sync manual
self.addEventListener('message', e => {
    if (e.data && e.data.type === 'TRIGGER_SYNC') {
        _syncWithServer().catch(() => {});
    }
});

// ── WEB PUSH ─────────────────────────────────────────────────────────────────
self.addEventListener('push', function (e) {
  let data = { title: 'Gestor de Inventario', body: '', url: '/dashboard' };
  try { data = Object.assign(data, e.data.json()); } catch (_) {}

  e.waitUntil(
    self.registration.showNotification(data.title, {
      body:    data.body,
      icon:    '/static/icons/icon-192.png',
      badge:   '/static/icons/icon-192.png',
      data:    { url: data.url },
      vibrate: [200, 100, 200],
    })
  );
});

self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  const target = (e.notification.data && e.notification.data.url) || '/dashboard';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const c of list) {
        if (c.url.includes(target) && 'focus' in c) return c.focus();
      }
      return clients.openWindow(target);
    })
  );
});
