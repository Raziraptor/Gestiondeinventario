/**
 * fusion.js — Fusion Design System runtime
 * animateCounters, avatarColorClass, theme helpers, chart helpers
 */

/* ── THEME ──────────────────────────────────────────────────── */
(function () {
  const KEY = 'erp_theme';
  const t = localStorage.getItem(KEY) || 'dark';
  document.documentElement.setAttribute('data-theme', t);
  document.documentElement.setAttribute('data-bs-theme', t);
})();

/* ── ANIMATED COUNTERS ──────────────────────────────────────── */
function animateCounters(root) {
  root = root || document;
  root.querySelectorAll('[data-count]').forEach(function (el) {
    var target = parseFloat(el.getAttribute('data-count'));
    var dec    = (el.getAttribute('data-dec') || '0') | 0;
    var prefix = el.getAttribute('data-prefix') || '';
    var suffix = el.getAttribute('data-suffix') || '';
    var t0 = performance.now(), dur = 1100;
    function fmt(v) {
      return prefix + v.toLocaleString('es-MX', {
        minimumFractionDigits: dec,
        maximumFractionDigits: dec
      }) + suffix;
    }
    function tick(t) {
      var p = Math.min(1, (t - t0) / dur);
      var e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(target * e);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });
}

/* ── AVATAR COLOR ────────────────────────────────────────────── */
function avatarColorClass(seed) {
  var colors = ['av-violet', 'av-sage', 'av-info', 'av-warn', 'av-danger'];
  var hash = 0;
  for (var i = 0; i < seed.length; i++) {
    hash = ((hash << 5) - hash) + seed.charCodeAt(i);
    hash |= 0;
  }
  return colors[Math.abs(hash) % colors.length];
}

/* Inject avatar styles once */
(function () {
  var s = document.createElement('style');
  s.textContent = [
    '.av{display:inline-flex;align-items:center;justify-content:center;border-radius:50%;font-family:var(--font-heading);font-weight:700;font-size:.78rem;line-height:1;flex-shrink:0;user-select:none;}',
    '.av-32{width:32px;height:32px;font-size:.7rem;}',
    '.av-40{width:40px;height:40px;}',
    '.av-48{width:48px;height:48px;font-size:.9rem;}',
    '.av-violet{background:rgba(145,132,217,.18);color:#b3a9e6;}',
    '.av-sage   {background:rgba(163,178,133,.18);color:#a3b285;}',
    '.av-info   {background:rgba(127,179,217,.18);color:#7fb3d9;}',
    '.av-warn   {background:rgba(217,169, 91,.18);color:#d9a95b;}',
    '.av-danger {background:rgba(224,113,109,.18);color:#e0716d;}',
    '[data-theme="light"] .av-violet{background:rgba(198,113, 57,.15);color:#c67139;}',
    '[data-theme="light"] .av-sage   {background:rgba(122,138, 94,.15);color:#7a8a5e;}',
    '[data-theme="light"] .av-info   {background:rgba( 74,127,165,.15);color:#4a7fa5;}',
    '[data-theme="light"] .av-warn   {background:rgba(176,125, 47,.15);color:#b07d2f;}',
    '[data-theme="light"] .av-danger {background:rgba(192, 79, 67,.15);color:#c04f43;}',
  ].join('\n');
  document.head.appendChild(s);
})();

/* ── CHART HELPERS ──────────────────────────────────────────── */
var FusionChart = {
  tokens: function () {
    var s = getComputedStyle(document.documentElement);
    return {
      accent:  s.getPropertyValue('--accent').trim()  || '#9184d9',
      sage:    s.getPropertyValue('--sage').trim()    || '#a3b285',
      danger:  s.getPropertyValue('--danger').trim()  || '#e0716d',
      warn:    s.getPropertyValue('--warn').trim()    || '#d9a95b',
      info:    s.getPropertyValue('--info').trim()    || '#7fb3d9',
      muted:   s.getPropertyValue('--muted').trim()   || '#8f93a8',
      faint:   s.getPropertyValue('--faint').trim()   || '#6a6e82',
      border:  s.getPropertyValue('--border').trim()  || 'rgba(255,255,255,.08)',
      text:    s.getPropertyValue('--text').trim()    || '#e9e9ed',
      card:    s.getPropertyValue('--card').trim()    || '#1b1e2b',
    };
  },

  baseOptions: function (tk) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: tk.muted, font: { size: 11 } } },
        tooltip: {
          backgroundColor: tk.card,
          titleColor: tk.text,
          bodyColor: tk.muted,
          borderColor: tk.border,
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
        },
      },
      scales: {
        x: {
          ticks: { color: tk.faint, font: { size: 10 } },
          grid:  { color: tk.border },
        },
        y: {
          ticks: { color: tk.faint, font: { size: 10 } },
          grid:  { color: tk.border },
        },
      },
    };
  },

  barOptions: function (tk) {
    var base = this.baseOptions(tk);
    base.animation = {
      delay: function (ctx) { return ctx.dataIndex * 80; },
    };
    return base;
  },

  donutOptions: function (tk) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '70%',
      animation: { animateRotate: true, animateScale: false },
      plugins: {
        legend: { position: 'bottom', labels: { color: tk.muted, font: { size: 11 }, padding: 16 } },
        tooltip: {
          backgroundColor: tk.card,
          titleColor: tk.text,
          bodyColor: tk.muted,
          borderColor: tk.border,
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
        },
      },
    };
  },

  lineOptions: function (tk) {
    var base = this.baseOptions(tk);
    base.elements = {
      line:  { tension: 0.35, borderWidth: 2 },
      point: { radius: 3, hoverRadius: 5 },
    };
    return base;
  },
};

/* ── THEME TOGGLE + THEMECHANGE EVENT ───────────────────────── */
window.setFusionTheme = function (t) {
  var KEY = 'erp_theme';
  localStorage.setItem(KEY, t);
  document.documentElement.setAttribute('data-theme', t);
  document.documentElement.setAttribute('data-bs-theme', t);
  window.dispatchEvent(new Event('themechange'));
};

window.toggleFusionTheme = function () {
  var KEY = 'erp_theme';
  var cur = localStorage.getItem(KEY) || 'dark';
  window.setFusionTheme(cur === 'dark' ? 'light' : 'dark');
};

/* ── DOM READY INIT ─────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  /* Run counters */
  animateCounters(document);

  /* Theme button wiring (Fusion topbar .icon-btn[data-action=theme]) */
  document.querySelectorAll('[data-action="theme"]').forEach(function (btn) {
    btn.addEventListener('click', function () { window.toggleFusionTheme(); });
  });

  /* Build avatar initials for elements with data-initials */
  document.querySelectorAll('[data-initials]').forEach(function (el) {
    var seed = el.getAttribute('data-initials') || '??';
    el.classList.add('av', avatarColorClass(seed));
    el.textContent = seed.substring(0, 2).toUpperCase();
  });
});

/* Expose globally for templates */
window.animateCounters  = animateCounters;
window.avatarColorClass = avatarColorClass;
window.FusionChart      = FusionChart;
