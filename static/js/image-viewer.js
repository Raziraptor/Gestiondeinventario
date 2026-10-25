/* Visor de imágenes a pantalla completa (Pointer Events, sin librerías).
 * Cualquier img[data-zoomable] abre el visor; data-zoom-src opcional.
 * API: window.ImageViewer.open(src, alt) / .close()
 * DOM siempre con createElement/textContent (CSP + XSS). */
(function () {
  'use strict';

  var MIN = 1, MAX = 5, DOUBLE_TAP_SCALE = 2.5, TAP_MS = 300, TAP_SLOP = 10;
  var SEL = 'img[data-zoomable]';

  var overlay, img, closeBtn;
  var source = null, prevOverflow = '';
  var s = 1, tx = 0, ty = 0;
  var pointers = new Map();
  var pinch = null;       // { dist, scale, mid:{x,y}, t:{x,y} }
  var pan = null;         // { x, y }
  var tapStart = null, lastTap = null, closeOnClick = false;
  var animTimer = 0;

  function reducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
  function isOpen() { return !!overlay && !overlay.hidden; }

  function build() {
    overlay = document.createElement('div');
    overlay.className = 'iv-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Visor de imagen');
    overlay.hidden = true;

    img = document.createElement('img');
    img.className = 'iv-img';
    img.alt = '';
    img.draggable = false;

    closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'iv-close';
    closeBtn.setAttribute('aria-label', 'Cerrar imagen');
    var ic = document.createElement('i');
    ic.className = 'ph ph-x';
    ic.setAttribute('aria-hidden', 'true');
    closeBtn.appendChild(ic);

    overlay.appendChild(img);
    overlay.appendChild(closeBtn);
    document.body.appendChild(overlay);

    closeBtn.addEventListener('click', function (e) { e.stopPropagation(); close(); });
    // Bootstrap (modal abierto) devuelve el foco al modal en document focusin: se corta aquí.
    overlay.addEventListener('focusin', function (e) { e.stopPropagation(); });
    overlay.addEventListener('pointerdown', onDown);
    overlay.addEventListener('pointermove', onMove);
    overlay.addEventListener('pointerup', onUp);
    overlay.addEventListener('pointercancel', onUp);
    overlay.addEventListener('lostpointercapture', onUp);
    overlay.addEventListener('click', onOverlayClick);
    overlay.addEventListener('wheel', onWheel, { passive: false });
    overlay.addEventListener('contextmenu', function (e) { e.preventDefault(); });
    window.addEventListener('resize', function () { if (isOpen()) { clampT(); apply(); } });
  }

  function apply() {
    img.style.transform = 'translate3d(' + tx + 'px,' + ty + 'px,0) scale(' + s + ')';
  }

  function clampT() {
    var vw = overlay.clientWidth, vh = overlay.clientHeight;
    var mx = Math.max(0, (img.offsetWidth * s - vw) / 2);
    var my = Math.max(0, (img.offsetHeight * s - vh) / 2);
    tx = clamp(tx, -mx, mx);
    ty = clamp(ty, -my, my);
  }

  function reset() {
    s = 1; tx = 0; ty = 0;
    pointers.clear(); pinch = null; pan = null; tapStart = null; lastTap = null; closeOnClick = false;
    img.style.willChange = '';
    apply();
  }

  // Coordenadas relativas al centro de la pantalla (origen del transform).
  function rel(x, y) { return { x: x - overlay.clientWidth / 2, y: y - overlay.clientHeight / 2 }; }

  function zoomAt(p, next, animate) {
    next = clamp(next, MIN, MAX);
    if (animate && !reducedMotion()) {
      img.classList.add('iv-anim');
      clearTimeout(animTimer);
      animTimer = setTimeout(function () { img.classList.remove('iv-anim'); }, 260);
    }
    tx = p.x - (p.x - tx) / s * next;
    ty = p.y - (p.y - ty) / s * next;
    s = next;
    if (s < 1.02) { s = 1; tx = 0; ty = 0; }
    clampT();
    apply();
  }

  function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
  function two() {
    var it = pointers.values();
    return [it.next().value, it.next().value];
  }

  function startPinch() {
    var pr = two();
    var mid = rel((pr[0].x + pr[1].x) / 2, (pr[0].y + pr[1].y) / 2);
    pinch = { dist: Math.max(1, dist(pr[0], pr[1])), scale: s, mid: mid, t: { x: tx, y: ty } };
  }

  function onDown(e) {
    if (closeBtn.contains(e.target)) return;
    e.preventDefault();
    closeOnClick = false;
    try { overlay.setPointerCapture(e.pointerId); } catch (err) { /* puntero ya liberado */ }
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    img.style.willChange = 'transform';
    if (pointers.size === 1) {
      tapStart = { x: e.clientX, y: e.clientY, t: e.timeStamp, onImg: e.target === img };
      pan = { x: e.clientX, y: e.clientY };
    } else if (pointers.size === 2) {
      tapStart = null; lastTap = null; pan = null;
      startPinch();
    }
  }

  function onMove(e) {
    var p = pointers.get(e.pointerId);
    if (!p) return;
    p.x = e.clientX; p.y = e.clientY;
    if (tapStart && Math.hypot(e.clientX - tapStart.x, e.clientY - tapStart.y) > TAP_SLOP) tapStart = null;
    if (pinch && pointers.size >= 2) {
      var pr = two();
      var next = clamp(pinch.scale * dist(pr[0], pr[1]) / pinch.dist, MIN, MAX);
      var mid = rel((pr[0].x + pr[1].x) / 2, (pr[0].y + pr[1].y) / 2);
      // El punto de la imagen bajo el punto medio inicial sigue bajo el punto medio actual.
      tx = mid.x - (pinch.mid.x - pinch.t.x) / pinch.scale * next;
      ty = mid.y - (pinch.mid.y - pinch.t.y) / pinch.scale * next;
      s = next;
      clampT();
      apply();
    } else if (pan && pointers.size === 1 && s > 1) {
      tx += e.clientX - pan.x;
      ty += e.clientY - pan.y;
      pan.x = e.clientX; pan.y = e.clientY;
      clampT();
      apply();
    }
  }

  function onUp(e) {
    if (!pointers.has(e.pointerId)) return;
    pointers.delete(e.pointerId);
    var tap = e.type === 'pointerup' && tapStart && (e.timeStamp - tapStart.t) < TAP_MS ? tapStart : null;
    tapStart = null;
    if (pointers.size < 2) pinch = null;
    else startPinch();
    if (pointers.size === 1) {
      var rest = pointers.values().next().value;
      pan = { x: rest.x, y: rest.y };
    } else {
      pan = null;
    }
    if (pointers.size === 0) {
      img.style.willChange = '';
      if (s < 1.02) { s = 1; tx = 0; ty = 0; apply(); }
    }
    if (tap) handleTap(tap, e);
  }

  function handleTap(tap, e) {
    if (!tap.onImg) {
      // El cierre espera al clic sintético: si se cerrara aquí, ese clic caería en lo que hay debajo.
      if (s === 1) closeOnClick = true;
      return;
    }
    if (lastTap && (e.timeStamp - lastTap.t) < TAP_MS && Math.hypot(tap.x - lastTap.x, tap.y - lastTap.y) < 30) {
      lastTap = null;
      zoomAt(rel(tap.x, tap.y), s > 1 ? 1 : DOUBLE_TAP_SCALE, true);
    } else {
      lastTap = { t: e.timeStamp, x: tap.x, y: tap.y };
    }
  }

  function onOverlayClick(e) {
    var go = closeOnClick;
    closeOnClick = false;
    if (go && s === 1 && e.target !== img && !closeBtn.contains(e.target)) close();
  }

  function onWheel(e) {
    e.preventDefault();
    zoomAt(rel(e.clientX, e.clientY), s * (e.deltaY < 0 ? 1.1 : 1 / 1.1), false);
  }

  function open(src, alt, from) {
    if (!src) return;
    if (!overlay) build();
    if (!isOpen()) source = from || (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    reset();
    img.src = src;
    img.alt = alt || '';
    if (!isOpen()) {
      prevOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    overlay.hidden = false;
    closeBtn.focus({ preventScroll: true });
  }

  function close() {
    if (!isOpen()) return;
    overlay.hidden = true;
    img.removeAttribute('src');
    reset();
    document.body.style.overflow = prevOverflow;
    var back = source;
    source = null;
    if (back && document.contains(back)) back.focus({ preventScroll: true });
  }

  function openFrom(el) {
    open(el.getAttribute('data-zoom-src') || el.currentSrc || el.getAttribute('src'), el.getAttribute('alt') || '', el);
  }

  // Captura: corre antes que los handlers de filas clicables (role="link") o enlaces contenedores.
  document.addEventListener('click', function (e) {
    var el = e.target instanceof Element ? e.target.closest(SEL) : null;
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
    openFrom(el);
  }, true);

  document.addEventListener('keydown', function (e) {
    if (isOpen()) {
      if (e.key === 'Escape') {
        e.preventDefault(); e.stopPropagation();
        close();
      } else if (e.key === 'Tab') {
        e.preventDefault();
        closeBtn.focus({ preventScroll: true });
      }
      return;
    }
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var el = e.target instanceof Element && e.target.matches(SEL) ? e.target : null;
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
    openFrom(el);
  }, true);

  function enhance(el) {
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
    if (!el.hasAttribute('role')) el.setAttribute('role', 'button');
    if (!el.hasAttribute('aria-label')) {
      var alt = (el.getAttribute('alt') || '').trim();
      el.setAttribute('aria-label', alt ? 'Ampliar imagen: ' + alt : 'Ampliar imagen');
    }
  }

  function enhanceTree(root) {
    if (root.nodeType !== 1) return;
    if (root.matches(SEL)) enhance(root);
    var list = root.querySelectorAll(SEL);
    for (var i = 0; i < list.length; i++) enhance(list[i]);
  }

  function init() {
    enhanceTree(document.body);
    new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var added = muts[i].addedNodes;
        for (var j = 0; j < added.length; j++) enhanceTree(added[j]);
      }
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.ImageViewer = { open: function (src, alt) { open(src, alt); }, close: close };
})();
