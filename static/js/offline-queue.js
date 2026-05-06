/**
 * offline-queue.js
 * Cola de operaciones pendientes usando IndexedDB.
 * Cargado en el page context (no en el SW).
 */
const _DB_NAME    = 'inventario-offline';
const _DB_VERSION = 1;
const _STORE      = 'pending_ops';

function _openDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(_DB_NAME, _DB_VERSION);
        req.onupgradeneeded = e => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(_STORE)) {
                db.createObjectStore(_STORE, { keyPath: 'id', autoIncrement: true });
            }
        };
        req.onsuccess  = e => resolve(e.target.result);
        req.onerror    = e => reject(e.target.error);
    });
}

async function oqEnqueue(type, payload) {
    const db = await _openDB();
    return new Promise((resolve, reject) => {
        const tx  = db.transaction(_STORE, 'readwrite');
        const req = tx.objectStore(_STORE).add({
            type, payload, created_at: Date.now(), status: 'pending',
        });
        req.onsuccess = () => resolve(req.result);
        req.onerror   = () => reject(req.error);
    });
}

async function oqGetAll() {
    const db = await _openDB();
    return new Promise((resolve, reject) => {
        const tx  = db.transaction(_STORE, 'readonly');
        const req = tx.objectStore(_STORE).getAll();
        req.onsuccess = () => resolve(req.result);
        req.onerror   = () => reject(req.error);
    });
}

async function oqRemove(id) {
    const db = await _openDB();
    return new Promise((resolve, reject) => {
        const tx  = db.transaction(_STORE, 'readwrite');
        const req = tx.objectStore(_STORE).delete(id);
        req.onsuccess = () => resolve();
        req.onerror   = () => reject(req.error);
    });
}

async function oqCount() {
    const db = await _openDB();
    return new Promise((resolve, reject) => {
        const tx  = db.transaction(_STORE, 'readonly');
        const req = tx.objectStore(_STORE).count();
        req.onsuccess = () => resolve(req.result);
        req.onerror   = () => reject(req.error);
    });
}

/** Actualiza el badge del navbar con el conteo actual */
async function oqUpdateBadge() {
    const n     = await oqCount();
    const badge = document.getElementById('offlinePendingBadge');
    const wrap  = document.getElementById('offlinePendingWrap');
    if (!badge || !wrap) return;
    if (n > 0) {
        badge.textContent  = n;
        wrap.style.display = 'inline-flex';
    } else {
        wrap.style.display = 'none';
    }
}

/**
 * Intenta sincronizar la cola con el servidor.
 * Llamado automáticamente al volver online, o manualmente.
 */
async function oqSync() {
    const ops = await oqGetAll();
    if (!ops.length) return;

    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';

    let resp;
    try {
        resp = await fetch('/api/sync', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body:    JSON.stringify({ operations: ops }),
        });
    } catch {
        // Sin red todavía
        return;
    }

    if (!resp.ok) return;

    const data = await resp.json();
    const failed = [];

    for (const result of data.results) {
        if (result.ok) {
            await oqRemove(result.id);
        } else {
            failed.push(result);
        }
    }

    await oqUpdateBadge();

    // Notificar al usuario
    const ok_count = data.results.filter(r => r.ok).length;
    if (ok_count > 0) {
        _showSyncToast(
            `${ok_count} operación(es) sincronizada(s) correctamente.`,
            'success'
        );
    }
    if (failed.length > 0) {
        const msgs = failed.map(f => f.error).join('\n');
        _showSyncToast(
            `${failed.length} operación(es) fallaron:\n${msgs}`,
            'danger'
        );
    }
}

function _showSyncToast(message, type) {
    const colors = {
        success: { bg: '#1e293b', border: '#10b981', dot: '#10b981' },
        danger:  { bg: '#1e293b', border: '#ef4444', dot: '#ef4444' },
    };
    const c = colors[type] || colors.success;

    const el = document.createElement('div');
    el.style.cssText = `
        position:fixed; bottom:5rem; left:50%; transform:translateX(-50%);
        z-index:10000; max-width:min(360px, calc(100vw - 2rem));
        background:${c.bg}; color:#f1f5f9;
        border:1px solid ${c.border}; border-radius:.75rem;
        padding:.75rem 1.1rem; font-size:.85rem; font-weight:500;
        box-shadow:0 8px 32px rgba(0,0,0,.4);
        white-space:pre-line; line-height:1.4;
        display:flex; align-items:flex-start; gap:.6rem;
    `;
    el.innerHTML = `<span style="color:${c.dot};margin-top:.15rem;">&#9679;</span><span>${message}</span>`;
    document.body.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transition = 'opacity .3s';
        setTimeout(() => el.remove(), 300);
    }, 5000);
}

// Sincronizar automáticamente al volver a tener red
window.addEventListener('online', () => {
    setTimeout(oqSync, 1000); // pequeño delay para que la red se estabilice
});

// Exponer API global
window.OfflineQueue = { enqueue: oqEnqueue, getAll: oqGetAll, remove: oqRemove, count: oqCount, sync: oqSync, updateBadge: oqUpdateBadge };
