
"use strict";
// Service worker: Freebuff Electron webview'de cache'i bypass et.
// skipWaiting + clients.claim ile yeni sürüm sayfa yeniden yüklenmeden
// devralir; fetch handler'ı tüm isteklere no-cache zorlar. API endpoint'leri
// (/api/*) network-first, cache'e dokunmaz.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js', { scope: '/' })
    .then((reg) => console.log('sw registered:', reg.scope))
    .catch(() => {});  // sw.js yoksa sessizce devam (non-Electron ortam/CI)
}
const $ = (id) => document.getElementById(id);

function setTheme(theme) {
  const light = theme === "light";
  document.documentElement.dataset.theme = light ? "light" : "dark";
  const toggle = $("theme-toggle");
  if (toggle) {
    toggle.setAttribute("aria-pressed", String(light));
    toggle.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
    toggle.textContent = light ? "dark mode" : "light mode";
  }
  try { localStorage.setItem("dashboard-theme", light ? "light" : "dark"); } catch (e) {}
}

try {
  setTheme(localStorage.getItem("dashboard-theme") === "light" ? "light" : "dark");
} catch (e) {
  setTheme("dark");
}

// View Transitions API (Chromium 111+, Safari 18+): subtle cross-fade
// on each SSE snapshot-driven panel refresh. Disabled under
// prefers-reduced-motion and on browsers without support.
let useViewTransitions = false;
if (typeof document.startViewTransition === "function") {
  const reduceMotion =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  useViewTransitions = !reduceMotion;
}
let evtSource = null;
let lastTs = 0;
let reconnectDelay = 1000;
const MAX_RECONNECT_DELAY = 30000;
// Bütçe limiti ($) — TEK KAYNAK: /api/latest `budget.limit` (etkin config
// budget_usd aynası). Snapshot gelince applySnapshot senkronlar; stream'deki
// [BÜTÇE] satırı da günceller. 30.0 yalnızca snapshot ÖNCESİ fallback'tir.
let BUDGET_LIMIT = 30.0;

function fmtBytes(b) {
  if (b == null) return "—";
  if (b > 1048576) return (b/1048576).toFixed(2) + " MB";
  return Math.round(b/1024) + " KB";
}
// Bütçe limiti gösterimi: tam sayıysa "30", değilse 2 ondalık ("27.50").
function fmtLimit(v) {
  if (v == null || !isFinite(v)) return "—";
  return (v % 1 === 0) ? String(v) : v.toFixed(2);
}

function fmtTs(iso) {
  if (!iso) return "no run yet";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString() + " (" + iso.split("T")[1].slice(0,5) + " UTC)";
  } catch(e) { return iso; }
}
// Süre formatı: 65 → "1m05s", 3600 → "1h00m", 3 → "3s"
function fmtDuration(s) {
  if (s == null || !isFinite(s)) return "—";
  const sec = Math.round(s);
  if (sec < 60) return sec + "s";
  if (sec < 3600) return Math.floor(sec / 60) + "m" + String(sec % 60).padStart(2, "0") + "s";
  return Math.floor(sec / 3600) + "h" + String(Math.floor((sec % 3600) / 60)).padStart(2, "0") + "m";
}
function setLive(state) {
  const dot = $("live-dot"), txt = $("live-status");
  if (state === "ok") { dot.className = "live-dot connected"; txt.textContent = "live"; }
  else if (state === "warn") { dot.className = "live-dot warn"; txt.textContent = "stale"; }
  else if (state === "err") { dot.className = "live-dot"; txt.textContent = "disconnected"; }
  else { dot.className = "live-dot"; txt.textContent = "connecting…"; }
}

// Tek satırı vurgula: kırmızı (hata/P0 bulgu) > mor (bütçe/BÜTÇE kalkanı) > sarı (P1 bulgu + CLI override) > yeşil (K8/Z3 SAT-UNSAT + PASS) > gri (ayraç/K-header).
function renderLiveFindings() {
  const fpEl = $("findings-panel");
  if (!fpEl || !liveFindings.length) return;
  const p0s = liveFindings.filter(f => f.type === "P0");
  const p1s = liveFindings.filter(f => f.type === "P1");
  let html = "<div style=\"font-size:12px;padding:4px 0\">";
  if (p0s.length) {
    html += p0s.map(f => `<div style=\"color:var(--err);margin:2px 0\">🔴 <b>P0</b> ${escapeHTML(f.line)}</div>`).join("");
  }
  if (p1s.length) {
    html += p1s.map(f => `<div style=\"color:var(--warn);margin:2px 0\">🟡 <b>P1</b> ${escapeHTML(f.line)}</div>`).join("");
  }
  html += `</div><div class=\"ts\" style=\"font-size:10px;color:#999\">canlı akıştan ${liveFindings.length} bulgu</div>`;
  fpEl.innerHTML = html;
}

function colorizeLine(line) {
  if (/^\[P0\]|^\[FAIL\]|^SONUÇ: FAIL|FAIL \(P0=|^Error|Exception|^Traceback|^HATA/.test(line))
    return '<span class="err">' + escapeHTML(line) + '</span>';
  if (/^\[BÜTÇE\]|^Bütçe:|^Budget:|^\$[0-9.]+ \/ \$[0-9.]+|aşım/.test(line))
    return '<span class="budget">' + escapeHTML(line) + '</span>';
  if (/^\[P1\]|\[CLI override\]|\[CLI-OVERRIDE\]/.test(line))
    return '<span class="warn">' + escapeHTML(line) + '</span>';
  if (/\[K8\]|\bUNSAT\b|\bSAT\b|^\[PASS\]|^SONUÇ: PASS|^SONUÇ: TÜMÜ PASS|^Verdict: PASS/.test(line))
    return '<span class="ok">' + escapeHTML(line) + '</span>';
  if (/^=== |^--- |^\[K[0-9]/.test(line))
    return '<span class="muted">' + escapeHTML(line) + '</span>';
  return escapeHTML(line);
}

function colorizeStdout(text) {
  return text.split("\n").map(colorizeLine).join("\n");
}

function escapeHTML(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ---- P0/P1 trend (son 100 run) ----
let trendCache = [];

// BÜTÇE AŞIMI şeridi: trend geçmişinde budget_usd > BUDGET_LIMIT olan run
// varsa (veya canlı akış son bütçesi limiti aştıysa) trend panelinin
// üstünde kırmızı uyarı gösterir; aşım yoksa gizli kalır. Şeride tıklanınca
// aşım yapan run'ların listesi açılır (genişletilebilir detay).
let budgetOverRuns = [];
function budgetOverDetailRows(over) {
  // ts · $budget (limit $X üstünde) — en yeni üstte; 30 ile sınırlı.
  const rows = over.slice().reverse();
  const cap = 30;
  const shown = rows.slice(0, cap).map(r => {
    const t = r.ts ? new Date(r.ts).toLocaleString() : "?";
    const amt = r.budget_usd != null ? "$" + r.budget_usd.toFixed(2) : "$?";
    return escapeHTML(t) + " · " + amt + " (limit $" + fmtLimit(BUDGET_LIMIT) + " üstünde)";
  });
  if (rows.length > cap) shown.push("… +" + (rows.length - cap) + " run daha");
  return shown.join("\n");
}
function toggleBudgetOverDetail() {
  const det = $("budget-over-detail"), caret = $("budget-over-caret");
  if (!det) return;
  const open = det.style.display !== "none";
  det.style.display = open ? "none" : "block";
  if (caret) caret.textContent = open ? "▸" : "▾";
}
function updateBudgetOverBanner() {
  const el = $("budget-over-banner");
  if (!el) return;
  const rows = trendCache || [];
  const over = rows.filter(r => r.budget_usd != null && r.budget_usd > BUDGET_LIMIT);
  const liveOver = budgetState && budgetState.est != null && budgetState.limit
    && budgetState.est > budgetState.limit;
  if (!over.length && !liveOver) {
    el.style.display = "none";
    budgetOverRuns = [];
    return;
  }
  const bits = [];
  if (over.length) {
    const worst = over.reduce((a, b) => (a.budget_usd > b.budget_usd ? a : b));
    const t = worst.ts ? new Date(worst.ts).toLocaleString() : "?";
    bits.push(`${over.length} run limiti aştı · en yüksek $${worst.budget_usd.toFixed(2)} @ ${t}`);
  }
  if (liveOver) {
    bits.push(`CANLI $${budgetState.est.toFixed(2)} > limit $${fmtLimit(budgetState.limit)}`);
  }
  el.style.display = "block";
  budgetOverRuns = over;
  const sum = $("budget-over-summary");
  if (sum) sum.textContent = "🔴 BÜTÇE AŞIMI — " + bits.join(" · ");
  const det = $("budget-over-detail");
  if (det) {
    det.style.display = "none";  // her güncellemede kapalı başla
    const liveLine = liveOver
      ? "CANLI $" + budgetState.est.toFixed(2) + " > limit $" + fmtLimit(budgetState.limit)
      : "";
    det.innerHTML = budgetOverDetailRows(over) +
      (over.length && liveLine ? "\n" : "") + escapeHTML(liveLine);
  }
  const caret = $("budget-over-caret");
  if (caret) caret.textContent = "▸";
}

function renderTrend(rows) {
  const svg = $("trend");
  const legend = $("trend-legend");
  if (!rows || rows.length === 0) {
    svg.innerHTML = "";
    legend.textContent = "henüz veri yok — ilk run bekleniyor";
    updateBudgetOverBanner();
    return;
  }
  trendCache = rows;
  // Bütçe sparkline'ı başlat: henüz canlı akıştan beslenmediyse
  // (ilk yükleme), trend verisindeki son run'lardan doldur.
  if (budgetHistory.length === 0) {
    budgetHistory = rows
      .filter(r => r.budget_usd != null && isFinite(r.budget_usd))
      .map(r => ({ est: r.budget_usd, limit: BUDGET_LIMIT }));
    renderBudgetSparkline();
  }
  const W = 1160, H = 240, PL = 44, PR = 248, PT = 12, PB = 32;
  const iw = W - PL - PR, ih = H - PT - PB;
  const plotRight = PL + iw;
  const n = rows.length;

  // Dört ayrı ölçek: sol = P0/P1 (adet), sağ-iç = duration_s, sağ-orta =
  // budget_usd, sağ-dış = K8 Z3 (PASS/FAIL sayısı, toplam 12'ye kadar)
  const maxP = Math.max(1, ...rows.map(r => Math.max(r.p0||0, r.p1||0)));
  const durs = rows.map(r => r.duration_s).filter(v => v != null && isFinite(v));
  const buds = rows.map(r => r.budget_usd).filter(v => v != null && isFinite(v));
  const lims = rows.map(r => r.budget_limit).filter(v => v != null && isFinite(v));
  // Limit DEĞİŞTİYSE (config geçmişi) bütçe ekseni limitleri de kapsar —
  // basamak (step) çizgisi değişimi görünür yapsın; sabit limitse eksen
  // gözlenen bütçeye göre kalır (limit yine üst kenara kıstırılır).
  const limsVary = lims.length > 1 && Math.min(...lims) !== Math.max(...lims);
  const ztots = rows.map(r => r.z3_total).filter(v => v != null && isFinite(v));
  const maxDur = durs.length ? Math.max(...durs, 1) : 1;
  const maxBud = buds.length
    ? Math.max(...buds, 0.01, ...(limsVary ? lims : []))
    : (limsVary ? Math.max(...lims, 0.01) : 1);
  const maxZ = ztots.length ? Math.max(...ztots, 1) : 1;

  const x = (i) => PL + (n === 1 ? iw / 2 : iw * i / (n - 1));
  const yP = (v) => PT + ih - (ih * (v||0) / maxP);
  const yD = (v) => (v == null || !isFinite(v)) ? null : PT + ih - (ih * v / maxDur);
  const yB = (v) => (v == null || !isFinite(v)) ? null : PT + ih - (ih * v / maxBud);
  const yZ = (v) => (v == null || !isFinite(v)) ? null : PT + ih - (ih * v / maxZ);

  let parts = [];
  // sol eksen grid + etiketler (P0/P1)
  for (let g = 0; g <= maxP; g++) {
    const gy = yP(g);
    parts.push(`<line x1="${PL}" y1="${gy}" x2="${plotRight}" y2="${gy}" stroke="#21262d" stroke-width="1"/>`);
    parts.push(`<text x="${PL-6}" y="${gy+4}" fill="#8b949e" font-size="10" text-anchor="end">${g}</text>`);
  }
  // P0 (kırmızı), P1 (sarı)
  if (rows.some(r => (r.p0||0) > 0)) {
    parts.push(`<polyline fill="none" stroke="#f85149" stroke-width="2" points="` +
      rows.map((r,i) => `${x(i)},${yP(r.p0||0)}`).join(" ") + `"/>`);
  }
  parts.push(`<polyline fill="none" stroke="#d29922" stroke-width="2" points="` +
    rows.map((r,i) => `${x(i)},${yP(r.p1||0)}`).join(" ") + `"/>`);
  // duration_s (mavi, kesikli) — ikinci eksen
  const durPts = rows.map((r,i) => { const y = yD(r.duration_s); return y == null ? null : `${x(i)},${y}`; }).filter(Boolean);
  if (durPts.length) {
    parts.push(`<polyline fill="none" stroke="#58a6ff" stroke-width="2" stroke-dasharray="4 3" points="${durPts.join(" ")}"/>`);
  }
  // budget_usd (mor) — üçüncü eksen (sağ-orta eksen konumu referans çizgisi
  // etiketi için burada tanımlanır — TDZ'yi önler).
  const budAxisX = plotRight + 88;
  const budPts = rows.map((r,i) => { const y = yB(r.budget_usd); return y == null ? null : `${x(i)},${y}`; }).filter(Boolean);
  if (budPts.length) {
    parts.push(`<polyline fill="none" stroke="#bc8cff" stroke-width="2" points="${budPts.join(" ")}"/>`);
  }
  // Per-run bütçe limiti — zaman serisi (step, turuncu düz): config limiti
  // run'lar arasında DEĞİŞTİYSE basamak görünür (eksen limitleri kapsar).
  // Sabit limitse step çizilmez — güncel referans çizgisi (kesikli) zaten
  // o değeri gösterir; eski run'larda budget_limit yoksa o aralık atlanır.
  if (limsVary) {
    const stepPts = [];
    for (let i = 0; i < rows.length; i++) {
      const lv = rows[i].budget_limit;
      if (lv == null || !isFinite(lv)) continue;
      const yv = yB(lv);
      if (yv == null) continue;
      stepPts.push(`${x(i)},${yv}`);
      if (i + 1 < rows.length) {
        const nv = rows[i + 1].budget_limit;
        if (nv != null && isFinite(nv)) stepPts.push(`${x(i + 1)},${yv}`);
      }
    }
    if (stepPts.length) {
      parts.push(`<polyline fill="none" stroke="#ffa657" stroke-width="2" points="${stepPts.join(" ")}"/>`);
    }
  }
  // Bütçe limiti referans çizgisi — /api/latest `budget.limit`'ten gelen
  // BUDGET_LIMIT (etkin config budget_usd aynası; snapshot yoksa 30.0
  // fallback). Bütçe eksenindeki gerçek konumunda çizilir; gözlenen bütçe
  // limitin çok altındaysa (0..maxBud ölçeği) üst kenara kıstırılıp "↑" ile
  // işaretlenir — altı güvenli bölge (yeşil), üstü aşım (kırmızı kare).
  if (buds.length) {
    const rawLimitY = yB(BUDGET_LIMIT);
    const offScale = rawLimitY < PT;          // limit ölçeğin üstünde kaldı
    const limitY = offScale ? PT + 3 : rawLimitY;
    const limitLbl = "limit $" + fmtLimit(BUDGET_LIMIT);
    parts.push(`<line x1="${PL}" y1="${limitY}" x2="${plotRight}" y2="${limitY}" stroke="#ffa657" stroke-width="1.5" stroke-dasharray="6 4"/>`);
    parts.push(`<text x="${budAxisX + 6}" y="${limitY - 3}" fill="#ffa657" font-size="9">${offScale ? limitLbl + " ↑" : limitLbl}</text>`);
    // Aşım işaretleri: limiti geçen bütçe noktaları kırmızı kare (üstü = aşım)
    rows.forEach((r, i) => {
      if (r.budget_usd != null && r.budget_usd > BUDGET_LIMIT) {
        const yy = yB(r.budget_usd);
        if (yy != null) {
          parts.push(`<rect x="${x(i) - 3}" y="${yy - 3}" width="6" height="6" fill="#f85149"/>`);
        }
      }
    });
  }
  // K8 Z3 — dördüncü eksen: PASS (yeşil, düz) + FAIL (kırmızı, kesikli)
  const zPassPts = rows.map((r,i) => { const y = yZ(r.z3_passed); return y == null ? null : `${x(i)},${y}`; }).filter(Boolean);
  if (zPassPts.length) {
    parts.push(`<polyline fill="none" stroke="#3fb950" stroke-width="2" points="${zPassPts.join(" ")}"/>`);
  }
  const zFailPts = rows.map((r,i) => { const y = yZ(r.z3_failed); return y == null ? null : `${x(i)},${y}`; }).filter(Boolean);
  if (zFailPts.length) {
    parts.push(`<polyline fill="none" stroke="#f85149" stroke-width="2" stroke-dasharray="3 3" points="${zFailPts.join(" ")}"/>`);
  }
  // K9 Lean PASS oranı (%) — beşinci eksen: lean_ok true → 100, false → 0, null → skip
  const leans = rows.map(r => r.lean_ok === true ? 100 : r.lean_ok === false ? 0 : null);
  const leanVals = leans.filter(v => v != null && isFinite(v));
  const hasLean = leanVals.length > 0;
  const maxLean = hasLean ? 100 : 1;
  const yL = (v) => (v == null || !isFinite(v)) ? null : PT + ih - (ih * v / maxLean);
  const leanPts = rows.map((r,i) => { const y = yL(leans[i]); return y == null ? null : `${x(i)},${y}`; }).filter(Boolean);
  if (leanPts.length) {
    parts.push(`<polyline fill="none" stroke="#e055d2" stroke-width="2.5" stroke-dasharray="5 2" points="${leanPts.join(" ")}"/>`);
  }
  // Lean PASS/FAIL noktaları (çizgi üstünde): yeşil daire=PASS, kırmızı kare=FAIL
  rows.forEach((r, i) => {
    const cx = x(i);
    const ly = yL(leans[i]);
    if (ly == null) return;
    if (r.lean_ok === true) {
      parts.push(`<circle cx="${cx}" cy="${ly}" r="3" fill="#3fb950"/>`);
    } else if (r.lean_ok === false) {
      parts.push(`<rect x="${cx-3}" y="${ly-3}" width="6" height="6" fill="#f85149"/>`);
    }
  });
  // sağ eksenler: duration (iç) + budget (orta) + Z3 (dış) + Lean (en dış)
  const durAxisX = plotRight + 26;
  const zAxisX = plotRight + 150;
  const leanAxisX = plotRight + 192;
  if (durs.length) {
    parts.push(`<line x1="${durAxisX}" y1="${PT}" x2="${durAxisX}" y2="${PT+ih}" stroke="#58a6ff" stroke-width="1" opacity="0.5"/>`);
    parts.push(`<text x="${durAxisX+6}" y="${PT+4}" fill="#58a6ff" font-size="9">${maxDur.toFixed(0)}s</text>`);
    parts.push(`<text x="${durAxisX+6}" y="${PT+ih+2}" fill="#58a6ff" font-size="9">0s</text>`);
  }
  if (buds.length) {
    parts.push(`<line x1="${budAxisX}" y1="${PT}" x2="${budAxisX}" y2="${PT+ih}" stroke="#bc8cff" stroke-width="1" opacity="0.5"/>`);
    parts.push(`<text x="${budAxisX+6}" y="${PT+4}" fill="#bc8cff" font-size="9">$${maxBud.toFixed(2)}</text>`);
    parts.push(`<text x="${budAxisX+6}" y="${PT+ih+2}" fill="#bc8cff" font-size="9">$0</text>`);
  }
  if (ztots.length) {
    parts.push(`<line x1="${zAxisX}" y1="${PT}" x2="${zAxisX}" y2="${PT+ih}" stroke="#3fb950" stroke-width="1" opacity="0.5"/>`);
    parts.push(`<text x="${zAxisX+6}" y="${PT+4}" fill="#3fb950" font-size="9">${maxZ} PASS</text>`);
    parts.push(`<text x="${zAxisX+6}" y="${PT+ih+2}" fill="#3fb950" font-size="9">0</text>`);
  }
  if (hasLean) {
    parts.push(`<line x1="${leanAxisX}" y1="${PT}" x2="${leanAxisX}" y2="${PT+ih}" stroke="#e055d2" stroke-width="1" opacity="0.5"/>`);
    parts.push(`<text x="${leanAxisX+6}" y="${PT+4}" fill="#e055d2" font-size="9">100%</text>`);
    parts.push(`<text x="${leanAxisX+6}" y="${PT+ih+2}" fill="#e055d2" font-size="9">0%</text>`);
  }
  // noktalar (verdict rengi)
  rows.forEach((r, i) => {
    const c = r.p0 > 0 ? "#f85149" : (r.p1 > 0 ? "#d29922" : "#3fb950");
    parts.push(`<circle cx="${x(i)}" cy="${yP(Math.max(r.p0||0, r.p1||0))}" r="2.5" fill="${c}"/>`);
  });
  // hover hit alanları (transparan sütun) — tooltip için
  const colW = n === 1 ? iw : iw / (n - 1);
  const halfW = Math.max(4, Math.min(10, colW / 2));
  rows.forEach((r, i) => {
    const cx = x(i);
    parts.push(`<rect x="${(cx - halfW).toFixed(2)}" y="${PT}" width="${(halfW * 2).toFixed(2)}" height="${ih}" fill="transparent" style="cursor:crosshair" onmousemove="showTrendTip(${i}, event)" onmouseleave="hideTrendTip()"/>`);
  });
  // x ekseni zaman etiketleri (ilk/orta/son)
  const pick = [0, Math.floor((n-1)/2), n-1].filter((v,i,a) => a.indexOf(v) === i);
  pick.forEach(i => {
    const r = rows[i];
    let lbl = "?";
    if (r.ts) { const d = new Date(r.ts); lbl = d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}); }
    parts.push(`<text x="${x(i)}" y="${H-12}" fill="#8b949e" font-size="10" text-anchor="middle">${lbl}</text>`);
  });
  svg.innerHTML = parts.join("");
  const last = rows[n-1];
  const leanPct = last.lean_ok === true ? "100%" : (last.lean_ok === false ? "0%" : "?");
  legend.textContent = "Kırmızı = P0 · Sarı = P1 · Yeşil nokta = PASS · Mavi (kesikli) = duration_s · Mor = budget_usd · " +
    "Yeşil çizgi = Z3 PASS · Kırmızı (noktalı) = Z3 FAIL · " +
    "Pembe (kesikli) = Lean PASS oranı (son: " + leanPct + ") · " +
    "Turuncu (kesikli) = güncel limit $" + fmtLimit(BUDGET_LIMIT) + " (config'ten) — altı güvenli, üstü (kırmızı kare) aşım" +
    (limsVary ? " · Turuncu (düz) = per-run limit (config değişimi)" : "") +
    " · aralık: " + (rows[0].ts ? new Date(rows[0].ts).toLocaleString() : "?") +
    " → " + (last.ts ? new Date(last.ts).toLocaleString() : "?") +
    ` · ${n} run`;
  $("trend-count").textContent = `(${n} run)`;
  updateBudgetOverBanner();
}

// ---- trend hover tooltip ----
function fmtTrendDur(v) {
  if (v == null || !isFinite(v)) return "—";
  if (v < 60) return v.toFixed(1) + " s";
  return Math.floor(v / 60) + " m " + Math.round(v % 60) + " s";
}
function fmtTrendBudget(v) {
  if (v == null || !isFinite(v)) return "—";
  return "$" + v.toFixed(2);
}
// Tooltip bütçe satırına limit altı/üstü durumu: "(limit $30 altında)"
// veya "(limit $30 üstünde — AŞIM)". lim verilmezse global BUDGET_LIMIT
// (dinamik config aynası); bütçe veya limit yoksa boş döner.
function budgetLimitNote(v, lim) {
  const l = (lim != null && isFinite(lim)) ? lim : BUDGET_LIMIT;
  if (v == null || !isFinite(v) || l == null || !isFinite(l)) return "";
  const limTxt = "$" + fmtLimit(l);
  return v > l ? " (limit " + limTxt + " üstünde — AŞIM)" : " (limit " + limTxt + " altında)";
}
// Tooltip bütçe satırı rengi: aşım kırmızı (tt-over), limit altı yeşil
// (tt-under), veri/limit yoksa renksiz. lim verilmezse global BUDGET_LIMIT.
function budgetTipColor(v, lim) {
  const l = (lim != null && isFinite(lim)) ? lim : BUDGET_LIMIT;
  if (v == null || !isFinite(v) || l == null || !isFinite(l)) return "";
  return v > l ? "tt-over" : "tt-under";
}
// Run'un KULLANDIĞI bütçe limiti: history satırında budget_limit varsa o
// (o run hangi config'le koştuysa), yoksa global BUDGET_LIMIT (eski run'lar).
function runBudgetLimit(r) {
  if (r.budget_limit != null && isFinite(r.budget_limit)) return r.budget_limit;
  return BUDGET_LIMIT;
}
// Ortak trend tooltip gövdesi — iki trend grafiği (P0/P1 + refs) aynı
// formatı kullanır: ts → duration → budget (renkli limit durumu) → config
// (hangi limit/yöntemle koştu). Verdict her grafik kendi kaynağından ekler
// (P0/P1: p0/p1; refs: r.verdict).
function trendTipHeader(r) {
  const ts = r.ts ? new Date(r.ts).toLocaleString() : "?";
  const lim = runBudgetLimit(r);
  const cfgBits = [];
  if (lim != null && isFinite(lim)) cfgBits.push("limit $" + fmtLimit(lim));
  if (r.budget_method) cfgBits.push("yöntem " + r.budget_method);
  if ((r.cli_override_count || 0) > 0) cfgBits.push("CLI override");
  return [
    ts,
    "duration: " + fmtTrendDur(r.duration_s),
    "<span class=\"" + budgetTipColor(r.budget_usd, lim) + "\">budget  : " +
      fmtTrendBudget(r.budget_usd) + budgetLimitNote(r.budget_usd, lim) + "</span>",
    "config  : " + (cfgBits.length ? cfgBits.join(" · ") : "—"),
  ];
}
function showTrendTip(i, ev) {
  const r = trendCache[i];
  if (!r) return;
  const verdict = (r.p0 || 0) > 0 ? "FAIL (P0)" : ((r.p1 || 0) > 0 ? "WARN (P1)" : "PASS");
  const tip = $("tip");
  let leanLine = "lean    : —";
  if (r.lean_ok === true) leanLine = "lean    : PASS (100%)";
  else if (r.lean_ok === false) leanLine = "lean    : FAIL (0%)" + (r.lean_detail ? " — " + escapeHTML(r.lean_detail) : "");
  const head = trendTipHeader(r);
  tip.innerHTML =
    head[0] + "\n" +
    "verdict : " + verdict + "\n" +
    head[1] + "\n" +
    head[2] + "\n" +
    head[3] + "\n" +
    "z3      : " + (r.z3_passed != null ? r.z3_passed + "/" + (r.z3_total != null ? r.z3_total : "?") +
      ((r.z3_failed || 0) > 0 ? " (" + r.z3_failed + " FAIL)" : "") : "—") + "\n" +
    leanLine;
  tip.style.display = "block";
  positionTip(ev);
}
function hideTrendTip() {
  $("tip").style.display = "none";
}
function positionTip(ev) {
  const tip = $("tip");
  const pad = 14;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  if (x + w > window.innerWidth - 8) x = ev.clientX - w - pad;
  if (y + h > window.innerHeight - 8) y = ev.clientY - h - pad;
  tip.style.left = Math.max(4, x) + "px";
  tip.style.top = Math.max(4, y) + "px";
}

// ---- Reference verification trend (verified/total zaman serisi) ----
// "Tam kapsam" rozeti mantığı (saf — test_refs_trend_badge.py ile senkron).
// rows: [{refs_verified, refs_total}] (sıralı, en yeni sonda). Döner
// {cls: "ok"|"warn"|"unknown", text}. Son run full (verified===total) ise
// yeşil rozet + kesintisiz full run serisi; değilse amber; veri yoksa gri.
function refsTrendBadge(rows) {
  const have = (rows || []).filter(r => r.refs_verified != null && r.refs_total != null);
  if (!have.length) return { cls: "unknown", text: "tam kapsam: veri yok" };
  const last = have[have.length - 1];
  const full = (r) => r.refs_verified === r.refs_total;
  let streak = 0;
  for (let i = have.length - 1; i >= 0 && full(have[i]); i--) streak++;
  if (full(last)) {
    return { cls: "ok", text: "✓ TAM KAPSAM " + last.refs_verified + "/" + last.refs_total +
      (streak > 1 ? " · " + streak + " run" : "") };
  }
  return { cls: "warn", text: "kapsam eksik " + last.refs_verified + "/" + last.refs_total };
}
let refsTrendCache = [];
// by_source kırılımı tooltip'te de gösterildiğinden SRC_NAMES modül
// kapsamında olmalı (renderRefsTrend içindeki SRC_ORDER/SRC_COLORS ile
// karışmaz — onlar yalnızca çizimde kullanılır).
const SRC_NAMES = { crossref: "CrossRef", openlibrary: "OpenLibrary", sep: "SEP",
                    archive: "Internet Archive", internetarchive: "Internet Archive",
                    perseus: "Perseus", hathitrust: "HathiTrust", url: "URL" };
function showRefsTrendTip(i, ev) {
  const r = refsTrendCache[i];
  if (!r) return;
  const verdict = r.verdict || ((r.p0 || 0) > 0 ? "FAIL (P0)"
                : ((r.p1 || 0) > 0 ? "WARN (P1)" : "PASS"));
  const tip = $("tip");
  const head = trendTipHeader(r);  // ortak format: ts → duration → budget → config
  let lines = [
    head[0],
    "verdict : " + verdict,
    head[1],
    head[2],
    head[3],
    "refs    : " + (r.refs_verified != null ? r.refs_verified : "?") + " / " +
      (r.refs_total != null ? r.refs_total : "?"),
    "mismatch: " + (r.refs_mismatch || 0),
  ];
  // by_source kırılımı — kaynak bazında hangi kaynaktan kaç doğrulama
  const bs = r.refs_by_source || {};
  const srcKeys = Object.keys(bs).filter(k => (bs[k] || 0) > 0);
  if (srcKeys.length > 0) {
    lines.push("── by_source ──");
    srcKeys.sort((a,b) => (bs[b]||0) - (bs[a]||0)).forEach(k => {
      const nm = SRC_NAMES[k] || k;
      lines.push("  " + nm + ": " + (bs[k] || 0));
    });
  }
  tip.innerHTML = lines.join("\n");
  tip.style.display = "block";
  positionTip(ev);
}
function renderRefsTrend(rows) {
  const svg = $("refs-trend");
  const legend = $("refs-trend-legend");
  const have = (rows || []).filter(r => r.refs_verified != null && r.refs_total != null);
  refsTrendCache = have;
  if (!have.length) {
    svg.innerHTML = "";
    legend.textContent = "çevrimiçi referans verisi yok — bu run'larda --check-references veri üretmedi";
    $("refs-trend-count").textContent = "";
    const b0 = refsTrendBadge([]);
    const bEl0 = $("refs-trend-badge");
    if (bEl0) { bEl0.className = "badge " + b0.cls; bEl0.textContent = b0.text; }
    return;
  }
  const W = 1160, H = 240, PL = 44, PR = 110, PT = 12, PB = 32;
  const iw = W - PL - PR, ih = H - PT - PB;
  const plotRight = PL + iw;
  const n = have.length;
  const maxT = Math.max(1, ...have.map(r => r.refs_total || 0));
  const x = (i) => PL + (n === 1 ? iw / 2 : iw * i / (n - 1));
  const y = (v) => PT + ih - (ih * (v == null || !isFinite(v) ? 0 : v) / maxT);

  let parts = [];
  // sol eksen grid (0..maxT)
  const steps = Math.min(maxT, 5);
  for (let s = 0; s <= steps; s++) {
    const g = Math.round(maxT * s / steps);
    const gy = y(g);
    parts.push(`<line x1="${PL}" y1="${gy}" x2="${plotRight}" y2="${gy}" stroke="#21262d" stroke-width="1"/>`);
    parts.push(`<text x="${PL-6}" y="${gy+4}" fill="#8b949e" font-size="10" text-anchor="end">${g}</text>`);
  }
  // by_source yığılmış alan (stacked area) — kaynak kırılımı; yığının tepesi
  // verified'a eşit olmalı (toplam = refs_verified). crossref/sep/
  // openlibrary/archive/perseus + kalanlar "diğer" olarak toplanır.
  const SRC_ORDER = ["crossref", "sep", "openlibrary", "archive", "perseus"];
  const SRC_COLORS = {
    crossref: "#58a6ff", sep: "#3fb950", openlibrary: "#bc8cff",
    archive: "#d29922", internetarchive: "#d29922",
    perseus: "#f85149", hathitrust: "#79c0ff",
    diğer: "#8b949e", url: "#8b949e",
  };
  const bySrc = have.map(r => {
    const bs = r.refs_by_source || {};
    const m = {};
    let other = 0;
    for (const k of Object.keys(bs)) {
      const v = Number(bs[k]) || 0;
      if (SRC_ORDER.includes(k)) m[k] = (m[k] || 0) + v;
      else other += v;
    }
    if (other > 0) m["diğer"] = other;
    return m;
  });
  const activeSrc = SRC_ORDER.filter(s => bySrc.some(m => (m[s] || 0) > 0));
  if (bySrc.some(m => (m["diğer"] || 0) > 0)) activeSrc.push("diğer");
  const base = new Array(n).fill(0);
  const areaPts = (vals) => vals.map((v,i) => `${x(i)},${y(v)}`).join(" ");
  activeSrc.forEach(s => {
    const top = have.map((_, i) => base[i] + (bySrc[i][s] || 0));
    const color = SRC_COLORS[s] || "#8b949e";
    // çokgen: üst kenar ileri + alt kenar (eski base) geri — yığılmış alan.
    const pts = areaPts(top) + " " +
      [...top].reverse().map((_, i) => `${x(n-1-i)},${y(base[n-1-i])}`).join(" ");
    parts.push(`<polygon fill="${color}" fill-opacity="0.30" stroke="none" points="${pts}"/>`);
    for (let i = 0; i < n; i++) base[i] = top[i];
  });
  // total (mavi, kesikli) — çevrimiçi denetlenebilir girdi sayısı
  parts.push(`<polyline fill="none" stroke="#58a6ff" stroke-width="2" stroke-dasharray="4 3" points="` +
    have.map((r,i) => `${x(i)},${y(r.refs_total)}`).join(" ") + `"/>`);
  // verified (yeşil, dolu) — doğrulanan
  parts.push(`<polyline fill="none" stroke="#3fb950" stroke-width="2.5" points="` +
    have.map((r,i) => `${x(i)},${y(r.refs_verified)}`).join(" ") + `"/>`);
  // mismatch (kırmızı) — yalnızca >0 varsa
  if (have.some(r => (r.refs_mismatch || 0) > 0)) {
    parts.push(`<polyline fill="none" stroke="#f85149" stroke-width="2" points="` +
      have.map((r,i) => `${x(i)},${y(r.refs_mismatch || 0)}`).join(" ") + `"/>`);
  }
  // noktalar: tam kapsam yeşil, eksik amber
  have.forEach((r, i) => {
    const full = r.refs_verified === r.refs_total;
    parts.push(`<circle cx="${x(i)}" cy="${y(r.refs_verified)}" r="2.5" fill="${full ? "#3fb950" : "#d29922"}"/>`);
  });
  // hover hit alanları (transparan sütun) — tooltip: run ts + verified/total + verdict
  const rColW = n === 1 ? iw : iw / (n - 1);
  const rHalfW = Math.max(4, Math.min(10, rColW / 2));
  have.forEach((r, i) => {
    parts.push(`<rect x="${(x(i) - rHalfW).toFixed(2)}" y="${PT}" width="${(rHalfW * 2).toFixed(2)}" height="${ih}" fill="transparent" style="cursor:crosshair" onmousemove="showRefsTrendTip(${i}, event)" onmouseleave="hideTrendTip()"/>`);
  });
  // x ekseni zaman etiketleri (ilk/orta/son)
  const pick = [0, Math.floor((n-1)/2), n-1].filter((v,i,a) => a.indexOf(v) === i);
  pick.forEach(i => {
    const r = have[i];
    let lbl = "?";
    if (r.ts) { const d = new Date(r.ts); lbl = d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}); }
    parts.push(`<text x="${x(i)}" y="${H-12}" fill="#8b949e" font-size="10" text-anchor="middle">${lbl}</text>`);
  });
  svg.innerHTML = parts.join("");
  const last = have[n-1];
  const pct = last.refs_total > 0 ? Math.round(100 * last.refs_verified / last.refs_total) : 0;
  // by_source seri lejantı (renkli ■ çipler, son run sayıları ile)
  const lastSrc = activeSrc.map(s => {
    const c = bySrc[n-1][s] || 0;
    return `<span style="color:${SRC_COLORS[s]||"#8b949e"}">■ ${SRC_NAMES[s]||s}:${c}</span>`;
  }).join(" ");
  legend.innerHTML = "Yeşil = verified · Mavi (kesikli) = total · Kırmızı = mismatch · Son: " +
    `${last.refs_verified}/${last.refs_total} (${pct}%) · ` +
    (have[0].ts ? new Date(have[0].ts).toLocaleString() : "?") +
    " → " + (last.ts ? new Date(last.ts).toLocaleString() : "?") + ` · ${n} run` +
    (lastSrc ? " · " + lastSrc : "");
  $("refs-trend-count").textContent = `(${n} run)`;
  // "Tam kapsam" rozeti — bugünkü 61/61 serisini yeşil rozetle vurgula.
  const b = refsTrendBadge(have);
  const bEl = $("refs-trend-badge");
  if (bEl) { bEl.className = "badge " + b.cls; bEl.textContent = b.text; }
}

// ---- Schema Sync rozeti (config_sync: verify.yml ↔ CONFIG_BASENAMES ↔ config.json) ----
function configSyncBadge(s) {
  if (!s || s.available !== true) {
    return {cls: "unknown", text: "Schema Sync: veri yok"};
  }
  const vt = (s.verified || 0) + "/" + (s.total || 0);
  if (s.has_drift) {
    return {cls: "err", text: "✗ Schema Sync: " + vt + " (" + (s.error_count || 0) + " drift)"};
  }
  return {cls: "ok", text: "✓ Schema Sync: " + vt};
}

function renderConfigSync(s) {
  const el = $("config-sync-badge");
  const body = $("config-sync-body");
  const ts = $("cs-ts");
  if (!el) return;
  const b = configSyncBadge(s);
  el.textContent = b.text;
  el.className = "badge " + b.cls;
  if (body) {
    if (!s || s.available !== true) {
      body.textContent = "Schema Sync: veri yok (config-sync job'u henüz koşmadı)";
    } else if (s.has_drift) {
      body.innerHTML = (s.details || []).map(d =>
        `<div style="color:var(--err)">✗ ${d.replace(/</g, '&lt;')}</div>`).join("")
        || `<div style="color:var(--err)">✗ Schema Sync: ${(s.verified||0)}/${(s.total||0)} (${(s.error_count||0)} drift)</div>`;
    } else {
      body.textContent = "✓ Schema Sync: tüm config dosyaları senkron";
    }
  }
  if (ts) ts.textContent = s && s.ts ? fmtTs(s.ts) : "";
}

// ---- refs-trend duration/bought overlay (refs-trend.json'dan bağımsız trend) ----
function renderRefsTrendDurationBudget(rows) {
  // refs-trend grafiğine sağ eksen olarak duration_s + budget_usd ekler.
  // rows: [{date, duration_s, budget_usd, verdict, ...}]
  const svg = $("refs-trend");
  if (!svg || !rows.length) return;
  const durs = rows.map(r => r.duration_s).filter(v => v != null && isFinite(v));
  const buds = rows.map(r => r.budget_usd).filter(v => v != null && isFinite(v));
  if (!durs.length && !buds.length) return;
  const maxDur = durs.length ? Math.max(...durs, 1) : 1;
  const maxBud = buds.length ? Math.max(...buds, 0.01) : 1;
  // SVG viewBox ile aynı koordinat sistemi (1160x240, PL=44, PR=110)
  const W = 1160, H = 240, PL = 44, PR = 110, PT = 12, PB = 32;
  const iw = W - PL - PR, ih = H - PT - PB;
  const plotRight = PL + iw;
  // duration (mavi, kesikli) + budget (mor) eksenleri
  const durAxisX = plotRight + 26;
  const budAxisX = plotRight + 68;
  const parts = [];
  if (durs.length) {
    parts.push(`<line x1="${durAxisX}" y1="${PT}" x2="${durAxisX}" y2="${PT+ih}" stroke="#58a6ff" stroke-width="1" opacity="0.5"/>`);
    parts.push(`<text x="${durAxisX+6}" y="${PT+4}" fill="#58a6ff" font-size="9">${maxDur.toFixed(0)}s</text>`);
    parts.push(`<text x="${durAxisX+6}" y="${PT+ih+2}" fill="#58a6ff" font-size="9">0s</text>`);
  }
  if (buds.length) {
    parts.push(`<line x1="${budAxisX}" y1="${PT}" x2="${budAxisX}" y2="${PT+ih}" stroke="#bc8cff" stroke-width="1" opacity="0.5"/>`);
    parts.push(`<text x="${budAxisX+6}" y="${PT+4}" fill="#bc8cff" font-size="9">$${maxBud.toFixed(2)}</text>`);
    parts.push(`<text x="${budAxisX+6}" y="${PT+ih+2}" fill="#bc8cff" font-size="9">$0</text>`);
  }
  // timestamp ekseninde hizala: refs-trend rows[] ile duration_budget rows[]
  // farklı uzunlukta olabilir; her birini kendi ekseninde bağımsız çiz.
  const n = rows.length;
  const x = (i) => PL + (n === 1 ? iw / 2 : iw * i / (n - 1));
  const yD = (v) => (v == null || !isFinite(v)) ? null : PT + ih - (ih * v / maxDur);
  const yB = (v) => (v == null || !isFinite(v)) ? null : PT + ih - (ih * v / maxBud);
  if (durs.length) {
    const pts = rows.map((r,i) => { const y = yD(r.duration_s); return y == null ? null : `${x(i)},${y}`; }).filter(Boolean);
    if (pts.length) parts.push(`<polyline fill="none" stroke="#58a6ff" stroke-width="2" stroke-dasharray="4 3" points="${pts.join(" ")}"/>`);
  }
  if (buds.length) {
    const pts = rows.map((r,i) => { const y = yB(r.budget_usd); return y == null ? null : `${x(i)},${y}`; }).filter(Boolean);
    if (pts.length) parts.push(`<polyline fill="none" stroke="#bc8cff" stroke-width="2" points="${pts.join(" ")}"/>`);
  }
  // budget limit referans çizgisi (BUDGET_LIMIT — /api/latest budget.limit)
  if (buds.length) {
    const limitY = yB(BUDGET_LIMIT);
    const offScale = limitY < PT;
    const ly = offScale ? PT + 3 : limitY;
    parts.push(`<line x1="${PL}" y1="${ly}" x2="${plotRight}" y2="${ly}" stroke="#ffa657" stroke-width="1" stroke-dasharray="6 4" opacity="0.6"/>`);
  }
  // varsa SVG içine ekle (mevcut graphic'in ÜZERİNE bindir)
  if (parts.length) {
    svg.insertAdjacentHTML("beforeend", parts.join(""));
    // legend'a duration/budget notu ekle
    const legend = $("refs-trend-legend");
    if (legend) {
      const extra = [];
      if (durs.length) extra.push(`Mavi (kesikli) = duration_s (max ${maxDur.toFixed(0)}s)`);
      if (buds.length) extra.push(`Mor = budget_usd (max $${maxBud.toFixed(2)})`);
      if (extra.length) legend.textContent += " · " + extra.join(" · ");
    }
  }
}

let runStreamES = null;
// ---- Bütçe ilerleme çubuğu (stream'deki [BÜTÇE] satırlarından) ----
let budgetState = null;   // {est, limit} — son bilinen bütçe kalkanı değeri
let budgetHistory = [];   // [{est, limit}] — son N run'ın bütçe değerleri (sparkline)

function updateBudgetBar() {
  const bar = $("budget-fill"), cnt = $("budget-count");
  const limitLine = $("budget-limit-line");
  if (!bar || !cnt) return;
  if (!budgetState || !budgetState.limit || !budgetState.est) {
    bar.style.width = "0%";
    bar.className = "z3fill budget";
    cnt.className = "z3count";
    cnt.textContent = "—";
    if (limitLine) limitLine.style.display = "none";
    return;
  }
  const { est, limit } = budgetState;
  const pct = Math.min(100, Math.round(est / limit * 100));
  bar.style.width = pct + "%";
  const over = est > limit;
  bar.className = over ? "z3fill err" : "z3fill budget";
  cnt.className = over ? "z3count" : "z3count ok";
  cnt.textContent = "$" + est.toFixed(2) + " / $" + limit.toFixed(2)
    + " (" + pct + "%)" + (over ? " · AŞIM" : "");
  // Limit çizgisi: bar'ın %100'üne turuncu dikey işaret (over: kırmızı)
  if (limitLine) {
    limitLine.style.display = "block";
    limitLine.style.left = "100%";
    limitLine.style.background = over ? "#f85149" : "#d29922";
    limitLine.title = "Limit: $" + fmtLimit(limit) + (over ? " (AŞIM!)" : "");
  }
}

// Bütçe sparkline (canvas): son N run'ın bütçe değerlerini mini grafik olarak çizer.
// Yeşil = limit altı, kırmızı = aşım, turuncu kesikli = limit çizgisi.
function renderBudgetSparkline() {
  const cv = $("budget-spark");
  if (!cv) return;
  const ctx = cv.getContext("2d");
  const W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);

  const MAX_BARS = 30;
  const hist = budgetHistory.slice(-MAX_BARS);
  if (hist.length < 1) {
    ctx.fillStyle = "#8b949e";
    ctx.font = "9px monospace";
    ctx.fillText("—", 4, 14);
    return;
  }

  const M = Math.max(...hist.map(h => h.est), 0.01);
  // limit: her kayıtta aynı limit varsa onu kullan, yoksa $30 varsay
  const limits = hist.filter(h => h.limit != null && isFinite(h.limit));
  const limit = limits.length ? limits[limits.length - 1].limit : 30.0;
  const yMax = Math.max(M, limit) * 1.15;  // %15 boşluk

  const bw = 2;  // bar genişliği
  const gap = Math.floor((W - 8) / MAX_BARS);  // bar aralığı
  const padL = 2, padT = 1, padB = 2;
  const h = H - padT - padB;

  // limit çizgisi (turuncu, kesikli/yatay)
  const limitY = padT + h - (h * limit / yMax);
  ctx.strokeStyle = "#d29922";
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 2]);
  ctx.beginPath();
  ctx.moveTo(0, limitY);
  ctx.lineTo(W, limitY);
  ctx.stroke();
  ctx.setLineDash([]);

  for (let i = 0; i < hist.length; i++) {
    const x = padL + i * gap;
    const barH = Math.max(1, h * hist[i].est / yMax);
    const y = padT + h - barH;
    const over = hist[i].est > (hist[i].limit || limit);
    ctx.fillStyle = over ? "#f85149" : "#3fb950";
    ctx.fillRect(x, y, bw, barH);
  }
}

// "[BÜTÇE] ~175990 token → $1.08 (limit $30.0, …)" → {est:1.08, limit:30}
// Stream satırındaki limit etkin config'ten geldiği için BUDGET_LIMIT'i de
// senkronlar — config değişince grafik çizgisi canlı akışta otomatik uyar.
function scanBudget(line) {
  const m = line.match(/\[BÜTÇE\][^→]*→\s*\$([0-9.]+)\s*\(limit\s*\$([0-9.]+)/);
  if (m) {
    budgetState = { est: parseFloat(m[1]), limit: parseFloat(m[2]) };
    BUDGET_LIMIT = parseFloat(m[2]);
    // Sparkline: her yeni run başında önceki est/limit'i history'e push'la
    // (scanBudget her run'un ilk [BÜTÇE] satırında bir kere çağrılır)
    if (budgetHistory.length === 0 ||
        budgetHistory[budgetHistory.length - 1].est !== budgetState.est) {
      budgetHistory.push({ ...budgetState });
      if (budgetHistory.length > 60) budgetHistory = budgetHistory.slice(-60);
    }
    updateBudgetBar();
    renderBudgetSparkline();
    updateBudgetOverBanner();  // canlı aşım varsa şerit anında görünsün
  }
}

// ---- K8 Z3 ilerleme çubuğu (stream'deki PASS satırlarından) ----
const Z3_TOTAL = 12;
let z3Seen = new Set();    // tamamlanan kontroller (bireysel [P1-a] satırları)
let z3Passed = new Set();  // PASS veren kontroller (özet [PASS] P1-a satırları)
let z3Failed = new Set();  // FAIL veren kontroller (özet [FAIL] P1-a satırları)

function updateZ3Bar() {
  const bar = $("z3-fill"), cnt = $("z3-count");
  if (!bar || !cnt) return;
  const done = z3Seen.size, passed = z3Passed.size, failed = z3Failed.size;
  bar.style.width = Math.round(done / Z3_TOTAL * 100) + "%";
  if (failed > 0) { bar.className = "z3fill err"; cnt.className = "z3count"; }
  else if (passed === Z3_TOTAL) { bar.className = "z3fill ok"; cnt.className = "z3count ok"; }
  else { bar.className = "z3fill"; cnt.className = "z3count"; }
  cnt.textContent = passed + "/" + Z3_TOTAL + (failed > 0 ? " · " + failed + " FAIL" : "");
}

function scanZ3(line) {
  // Yeni bir K8 Z3 koşusu başlarsa sayaçları sıfırla (bayat kalmayı önler).
  if (/SEMBOLİK İSPAT/.test(line)) {
    z3Seen.clear(); z3Passed.clear(); z3Failed.clear();
    updateZ3Bar();
    return;
  }
  // Özet tablo: "  [PASS] P1-a ..." / "  [FAIL] P4-b ..."
  let m = line.match(/\[\s*(PASS|FAIL)\s*\]\s*(P[1-5](?:-(?:[a-e]|note))?)\b/);
  if (m) {
    (m[1] === "PASS" ? z3Passed : z3Failed).add(m[2]);
    z3Seen.add(m[2]);
    updateZ3Bar();
    return;
  }
  // Bireysel kontrol satırı: "[P1-a] ... : UNSAT ..." (canlı ilerleme)
  m = line.match(/^\[(P[1-5](?:-(?:[a-e]|note))?)\]/);
  if (m) {
    z3Seen.add(m[1]);
    updateZ3Bar();
  }
}

let streamLines = [];  // renklendirilmiş HTML satırları (son STREAM_MAX)
let liveFindings = []; // canlı akıştan toplanan P0/P1 satırları [{type, line}]
const STREAM_MAX = 600;  // son N run replay edilirken yeterli bağlam kalsın
function connectStream() {
  const el = $("runstream"), st = $("stream-state");
  if (runStreamES) runStreamES.close();
  runStreamES = new EventSource("/api/run-stream?v=" + (window.BUILD_TS||Date.now()));
  runStreamES.addEventListener("info", (e) => {
    try { const d = JSON.parse(e.data); st.textContent = "bağlı"; } catch(_) {}
  });
  const push = (tag, line, replay) => {
    scanZ3(line);
    scanBudget(line);
    const arrow = tag === "stderr" ? '<span class="muted">⟶ </span>' : "";
    const mark = replay ? '<span class="muted">⏪ </span>' : "";
    streamLines.push(mark + arrow + colorizeLine(line));
    if (streamLines.length > STREAM_MAX) streamLines = streamLines.slice(-STREAM_MAX);
    el.innerHTML = streamLines.join("\n");
    el.scrollTop = el.scrollHeight;
    // P0/P1 satırlarını canlı findings paneline ekle
    if (/^\[P0\]/.test(line) || /\[FAIL\]/.test(line) || /SONUÇ: FAIL/.test(line)) {
      liveFindings.push({type: "P0", line: line});
      renderLiveFindings();
    } else if (/^\[P1\]/.test(line) || /\[CLI override\]/.test(line)) {
      liveFindings.push({type: "P1", line: line});
      renderLiveFindings();
    } else if (/^SONUÇ: PASS|^SONUÇ: TÜMÜ PASS|^Verdict: PASS/.test(line)) {
      // PASS satırı geldiyse findings panelini temizle (yeni run)
    }
  };
  runStreamES.addEventListener("replay-start", (e) => {
    let sum = null;
    try { sum = JSON.parse(e.data); } catch(_) {}
    if (sum && sum.first) {
      // İlk run'un başında (yeniden bağlantıda) eski satırları temizle ki
      // replay + canlı satırlar çift görünmesin; K8 sayacını ve bütçe
      // çubuğunu sıfırla (replay son run'u baştan sayar).
      streamLines = [];
      liveFindings = [];
      renderLiveFindings();
      z3Seen.clear(); z3Passed.clear(); z3Failed.clear();
      updateZ3Bar();
      budgetState = null;
      updateBudgetBar();
      st.textContent = "geçmiş runlar yükleniyor…";
    }
    // Her run'un özeti (verdict/P0/P1/bütçe) — geçmiş run sınırında
    // görünür bir özet satırı olarak yazılır.
    const sv = sum && sum.verdict ? sum.verdict : "UNKNOWN";
    const scls = sv === "PASS" ? "ok" : (sv === "FAIL" || sv === "ERROR" ? "err" : "warn");
    const p0 = sum && sum.p0 != null ? sum.p0 : 0;
    const p1 = sum && sum.p1 != null ? sum.p1 : 0;
    const bud = sum && sum.budget_usd != null ? "$" + sum.budget_usd.toFixed(2) : "—";
    const dur = sum && sum.duration_s != null
      ? " · " + fmtDuration(sum.duration_s) : "";
    const refV = sum && sum.refs_verified != null ? sum.refs_verified : null;
    const refT = sum && sum.refs_total != null ? sum.refs_total : null;
    const refs = refV != null && refT != null ? " · refs " + refV + "/" + refT : "";
    const pg = sum && sum.pdf_pages != null ? " · " + sum.pdf_pages + " sayfa" : "";
    const tlabel = sum && sum.ts && sum.ts.indexOf("T") >= 0
      ? sum.ts.split("T")[1].slice(0, 8) : "";
    const label = tlabel ? "geçmiş run " + tlabel : "geçmiş run";
    streamLines.push(
      '<span class="muted">── ' + label + ' ── </span>' +
      '<span class="' + scls + '">' + sv + '</span>' +
      '<span class="muted"> · P0=' + p0 + ' · P1=' + p1 + refs + pg + ' · bütçe ' + bud + dur + '</span>');
    el.innerHTML = streamLines.join("\n");
    el.scrollTop = el.scrollHeight;
  });
  runStreamES.addEventListener("stdout", (e) => {
    try { const d = JSON.parse(e.data); push("stdout", d.line, d.replay); } catch(_) {}
  });
  runStreamES.addEventListener("stderr", (e) => {
    try { const d = JSON.parse(e.data); push("stderr", d.line, d.replay); } catch(_) {}
  });
  runStreamES.addEventListener("replay-end", (e) => {
    let d = null;
    try { d = JSON.parse(e.data); } catch(_) {}
    if (!d || d.last) {
      // Son run'un sonunda canlı akış sınırını çiz (ara runlarda değil).
      st.textContent = "bağlı";
      streamLines.push('<span class="muted">── canlı akış ──</span>');
    }
    if (streamLines.length > STREAM_MAX) streamLines = streamLines.slice(-STREAM_MAX);
    el.innerHTML = streamLines.join("\n");
    el.scrollTop = el.scrollHeight;
  });
  runStreamES.addEventListener("end", (e) => {
    st.textContent = "run bitti";
    streamLines.push('<span class="muted">── run sonu ──</span>');
    if (streamLines.length > STREAM_MAX) streamLines = streamLines.slice(-STREAM_MAX);
    el.innerHTML = streamLines.join("\n");
    el.scrollTop = el.scrollHeight;
  });
  runStreamES.onerror = () => { st.textContent = "bağlantı koptu"; };
}

let _trendCache = null;       // {rows, dbRows} en son yüklenen trend verisi
let _trendFetchAt = 0;          // Date.now() of last fetch (0 = never)
const TREND_CACHE_MS = 30000;   // 30s coarse cadence

// ─── CLI override trend ──────────────────────────────────────────────────
// Son run warning=true ise amber "⚠️ override VAR (N · keys)", değilse
// yeşil "✓ override YOK"; veri yoksa gri. Python test karşılığı
// (test_override_trend_badge.override_trend_badge) ile birebir senkron.
const OVERRIDE_COLOR_RULES = {
  warning: { color: "#d29922", label: "⚠️ override VAR" },
  clean:   { color: "#3fb950", label: "✓ override YOK" },
};

function overrideTrendBadge(rows) {
  const have = (rows || []).filter(r => r && typeof r.warning === "boolean");
  if (!have.length) return { cls: "unknown", text: "override: veri yok" };
  const last = have[have.length - 1];
  if (last.warning) {
    const keys = (last.override_keys || []).filter(k => k);
    let text = "⚠️ override VAR (" + (last.override_count || 0);
    if (keys.length) text += " · " + keys.join(",");
    text += ")";
    return { cls: "warn", text: text };
  }
  return { cls: "ok", text: "✓ override YOK" };
}

function renderOverrideTrend(rows) {
  const badgeEl = $("ovr-trend-badge");
  const svg = $("ovr-trend");
  const legend = $("ovr-trend-legend");
  if (!badgeEl && !svg) return;
  const have = (rows || []).filter(r => r && typeof r.warning === "boolean");
  const b = overrideTrendBadge(have);
  if (badgeEl) {
    badgeEl.textContent = b.text;
    badgeEl.className = "badge " + b.cls;
  }
  if (legend) {
    legend.textContent =
      OVERRIDE_COLOR_RULES.warning.label + " · " + OVERRIDE_COLOR_RULES.clean.label;
  }
  if (svg) {
    const W = 1160, H = 120, n = have.length;
    let parts = [];
    have.forEach((r, i) => {
      const x = n === 1 ? W / 2 : 20 + (W - 40) * i / (n - 1);
      const color = r.warning ? OVERRIDE_COLOR_RULES.warning.color
                              : OVERRIDE_COLOR_RULES.clean.color;
      parts.push(`<circle cx="${x.toFixed(1)}" cy="${H / 2}" r="5" fill="${color}">` +
        `<title>${r.ts || ""} ${r.warning ? "override VAR" : "override YOK"}</title></circle>`);
    });
    svg.innerHTML = parts.join("");
  }
}

function loadOverrideTrend() {
  fetch("/api/override-trend").then(r => r.json()).then(data => {
    const rows = Array.isArray(data) ? data : ((data && data.rows) || []);
    renderOverrideTrend(rows);
  }).catch(() => renderOverrideTrend([]));
}

function loadTrend(force) {
  const now = Date.now();
  if (!force && _trendCache && now - _trendFetchAt < TREND_CACHE_MS) {
    // cache hâlâ taze — yeniden render et ama tekrar fetch etme
    const {rows, dbRows} = _trendCache;
    renderTrend(rows);
    renderRefsTrend(rows);
    renderHookEnv(rows);
    renderHookEnvTrend(rows);
    if (dbRows && dbRows.length) renderRefsTrendDurationBudget(dbRows);
    return;
  }
  _trendFetchAt = now;
  fetch("/api/trend").then(r => r.json()).then(data => {
    const rows = Array.isArray(data.history) ? data.history : [];
    renderTrend(rows);
    renderRefsTrend(rows);
    renderHookEnv(rows);
    renderHookEnvTrend(rows);
    const dbRows = (data.refs_trend && data.refs_trend.duration_budget && data.refs_trend.duration_budget.rows) || [];
    _trendCache = {rows, dbRows};
    if (dbRows.length) renderRefsTrendDurationBudget(dbRows);
  }).catch(err => {
    $("trend-legend").textContent = "trend yüklenemedi: " + err;
  });
}

// ---- Budget breakdown (ratios + type_bytes) ----
function renderBudget(b) {
  const brEl = $("m-br"), tbEl = $("m-tb"), tbSub = $("m-tb-sub");
  const w = b && b.comparison && b.comparison.weighted;
  const ratios = w && w.ratios;
  const byType = w && w.by_type;
  if (!ratios || !byType) {
    brEl.textContent = "—";
    tbEl.textContent = "—";
    tbSub.textContent = "iç zip kırılımı";
    return;
  }
  const order = ["text", "pdf", "archive", "binary"];
  brEl.textContent = order.map(k => k + "=" + (ratios[k] != null ? ratios[k] : "?")).join(" · ");
  tbEl.textContent = order.map(k => fmtBytes(byType[k])).join(" · ");
  tbSub.textContent = "toplam " + fmtBytes(b.total_bytes);
}

// ---- Online reference stats (verified/total, by_source) ----
function renderRefsOnline(d) {
  const tsEl = $("ro-ts"), sourcesEl = $("ro-sources");
  const total   = d.refs_total   != null ? d.refs_total   : d.total_online;
  const verified = d.refs_verified != null ? d.refs_verified : d.verified;
  const mismatch = d.refs_mismatch != null ? d.refs_mismatch : d.mismatch;
  const unverified = d.refs_unverified != null ? d.refs_unverified
                 : (total != null && verified != null ? Math.max(0, total - verified) : null);
  const bySource = d.refs_by_source || d.by_source;
  const ts = d.ts || d.date;

  if (total == null) {
    $("ro-vt").textContent = "—";
    $("ro-unv").textContent = "—";
    $("ro-mis").textContent = "—";
    $("ro-cov").textContent = "—";
    $("ro-vt").className = "value"; $("ro-cov").className = "value";
    sourcesEl.innerHTML = '<div class="muted">çevrimiçi referans denetimi bu run\'da veri üretmedi (ağ/denetim çalışmadı veya 0 kayıt)</div>';
    if (tsEl) tsEl.textContent = "";
    return;
  }

  const v = verified || 0;
  $("ro-vt").textContent = v + " / " + total;
  $("ro-vt").className = "value " + (v === total ? "ok" : "warn");
  $("ro-unv").textContent = unverified != null ? unverified : "?";
  $("ro-mis").textContent = mismatch || 0;
  const pct = total > 0 ? Math.round(100 * v / total) : 0;
  $("ro-cov").textContent = pct + "%";
  $("ro-cov").className = "value " + (pct === 100 ? "ok" : "warn");
  if (tsEl) tsEl.textContent = fmtTs(ts);

  // ---- Shared source maps (source cards + table'da kullanılır) ----
  const srcColors = { crossref: "#58a6ff", openlibrary: "#bc8cff", sep: "#3fb950",
                      archive: "#d29922", internetarchive: "#d29922", perseus: "#f85149",
                      hathitrust: "#79c0ff", url: "#8b949e", handle: "#8b949e",
                      fallback_openlibrary: "#bc8cff", fallback_loc: "#79c0ff",
                      fallback_hathitrust: "#79c0ff", "diğer": "#8b949e" };
  const srcNames = { crossref: "CrossRef", openlibrary: "OpenLibrary", sep: "SEP",
                     archive: "Internet Archive", internetarchive: "Internet Archive",
                     perseus: "Perseus", hathitrust: "HathiTrust", url: "URL",
                     handle: "Handle" };
  const srcIcons = { crossref: "\ud83d\udd17", openlibrary: "\ud83d\udcda", sep: "\ud83d\udcd6",
                     archive: "\ud83c\udfdb\ufe0f", internetarchive: "\ud83c\udfdb\ufe0f",
                     perseus: "\ud83c\udfdb\ufe0f", hathitrust: "\ud83d\udcd8",
                     url: "\ud83c\udf10", handle: "\ud83d\udcce" };
  const order = ["crossref", "openlibrary", "sep", "archive", "internetarchive", "perseus"];
  const rows = order.filter(k => bySource && bySource[k] != null);
  if (!rows.length) {
    sourcesEl.innerHTML = '<div class="muted">kaynak kırılımı yok (by_source boş)</div>';
    // Hide cards too
    const scEl = $("ro-source-cards");
    if (scEl) scEl.innerHTML = '';
    return;
  }
  const max = Math.max(...rows.map(k => bySource[k]));

  // ---- Source summary cards (colored left border) ----
  const scEl = $("ro-source-cards");
  if (scEl) {
    let cardsHtml = '';
    for (const k of rows) {
      const c = bySource[k];
      const clr = srcColors[k] || "var(--accent)";
      const icon = srcIcons[k] || "";
      cardsHtml += '<div class="card source-card" style="border-left:3px solid ' + clr + '">' +
        '<div class="label">' + icon + ' ' + (srcNames[k] || k) + '</div>' +
        '<div class="value">' + c + '</div></div>';
    }
    scEl.innerHTML = cardsHtml;
  }

  // ---- Colored table (renk kodlu satırlar + yatay çubuk grafiği) ----
  const archiveGroup = d.archive_group;
  let html = '';
  if (archiveGroup != null && archiveGroup > 0) {
    html += `<div style="margin-bottom:6px;font-size:0.85em;color:var(--accent)">` +
      `📚 Archive group: <b>${archiveGroup}</b>` +
      ` <span class="ts">(archive + loc + hathitrust)</span></div>`;
  }
  html += '<table style="border-collapse:collapse;width:100%">' +
    '<thead><tr><th style="width:24%">Source</th><th style="width:10%">Cnt</th>' +
    '<th style="width:8%">%</th><th>Bar</th></tr></thead><tbody>';
  for (const k of rows) {
    const c = bySource[k];
    const w = max > 0 ? Math.round(100 * c / max) : 0;
    const clr = srcColors[k] || "var(--accent)";
    const icon = srcIcons[k] || "";
    const nm = srcNames[k] || k;
    html += '<tr style="border-left:3px solid ' + clr + '">' +
      '<td style="padding-left:12px">' + icon + ' <b>' + nm + '</b></td>' +
      '<td style="font-family:monospace;font-weight:600">' + c + '</td>' +
      '<td style="font-family:monospace" class="ts">' + w + '%</td>' +
      '<td style="padding:4px 10px 4px 16px">' +
        '<div style="height:14px;background:#21262d;border-radius:7px;overflow:hidden">' +
          '<div style="width:' + w + '%;height:100%;background:' + clr +
            ';border-radius:7px;transition:width 0.4s"></div></div></td></tr>';
  }
  html += '</tbody></table>';
  sourcesEl.innerHTML = html;
}

// ---- Config diff (raw vs effective) ----
function renderConfigDiff(cd, ts) {
  const bodyEl = $("cd-body"), tsEl = $("cd-ts");
  if (!bodyEl) return;
  if (tsEl) tsEl.textContent = ts ? fmtTs(ts) : "";
  if (cd == null) {
    bodyEl.innerHTML = '<div class="muted">veri bekleniyor…</div>';
    return;
  }
  const diffs = cd.differences;
  if (!diffs || !diffs.length) {
    bodyEl.innerHTML = '<span class="badge ok">fark yok</span> ' +
      '<span class="muted">raw config ile effective config aynı (CLI override / drift yok)</span>';
    return;
  }
  const reasonLabel = { cli_override: "CLI override", default: "default", drift: "DRIFT" };
  const reasonCls = { cli_override: "info", default: "warn", drift: "err" };
  let h = '<table><thead><tr><th>Field</th><th>Raw</th><th>Effective</th><th>Neden</th></tr></thead><tbody>';
  for (const r of diffs) {
    const cls = reasonCls[r.reason] || "unknown";
    const lbl = reasonLabel[r.reason] || r.reason;
    h += '<tr><td><code>' + escapeHTML(r.field) + '</code></td>' +
      '<td><code>' + escapeHTML(fmtVal(r.raw)) + '</code></td>' +
      '<td><code>' + escapeHTML(fmtVal(r.effective)) + '</code></td>' +
      '<td><span class="badge ' + cls + '">' + lbl + '</span></td></tr>';
  }
  h += '</tbody></table>';
  bodyEl.innerHTML = h;
}

// ---- CLI override panel (son run'un override durumu) ----
function renderCliOverride(data) {
  const bodyEl = $("cov-body"), tsEl = $("cov-ts");
  if (!bodyEl) return;
  const cov = data && data.cli_overrides;
  const ts = data && data.ts;
  if (tsEl) tsEl.textContent = ts ? fmtTs(ts) : "";
  if (cov == null) {
    bodyEl.innerHTML = '<div class="muted">veri bekleniyor…</div>';
    return;
  }
  // cov: { budget: {override, file_value, effective}, ... }
  const items = Object.entries(cov).filter(
    ([, v]) => v && typeof v === "object");
  if (!items.length) {
    bodyEl.innerHTML = '<span class="badge ok">CLI override YOK</span> ' +
      '<span class="muted">bütçe kalkanı dosya config değerleriyle koştu</span>';
    return;
  }
  const overrides = items.filter(([, v]) => v.override);
  if (!overrides.length) {
    // keys var ama override=false (cli_given ama değer aynı)
    bodyEl.innerHTML = '<span class="badge ok">CLI override YOK</span> ' +
      '<span class="muted">' + items.length + ' anahtar CLI verildi ama dosya değeriyle aynı</span>';
    return;
  }
  let h = '<span class="badge warn">CLI override VAR ('
    + overrides.length + ')</span>';
  h += '<table style="margin-top:8px"><thead><tr><th>Anahtar</th>' +
    '<th>Dosya değeri</th><th>CLI değeri</th></tr></thead><tbody>';
  for (const [key, v] of overrides) {
    h += '<tr><td><code>' + escapeHTML(key) + '</code></td>' +
      '<td><code>' + escapeHTML(fmtVal(v.file_value)) + '</code></td>' +
      '<td><code style="color:var(--warn)">' +
      escapeHTML(fmtVal(v.effective)) + '</code></td></tr>';
  }
  h += '</tbody></table>';
  bodyEl.innerHTML = h;
}

// ---- Mirror sync panel (K17) — son run'un mirror durumu ----
// Kaynak: /api/latest `mirror_sync` (verify --json 'mirror' raporu).
// Gösterir: K17 exit kodu + GÜNCEL/BAYAT rozeti + BAYAT/EKSİK dosya listesi
// (sync_verify_mirror.sh --check çıktısındaki satırlardan).
function renderMirrorSync(data) {
  const bodyEl = $("mirror-body"), tsEl = $("mirror-ts");
  if (!bodyEl) return;
  const m = data && data.mirror_sync;
  const ts = data && data.ts;
  if (tsEl) tsEl.textContent = ts ? fmtTs(ts) : "";
  if (m == null) {
    bodyEl.innerHTML = '<span class="muted">K17 mirror check bu run\u0027da koşmadı (--check-mirror gerekli)</span>';
    return;
  }
  const exit = m.exit;
  const ok = m.ok === true;
  const stale = (m.stale_files || []).slice();
  const auto = m.auto_synced === true;
  // TCC rotası (exit null + ok): launchd agent ~/Desktop'ı okuyamadığı için
  // K17 denetimi atlandı — sahte GÜNCEL gösterme, açık "denetlenemedi" rozeti.
  const skipTcc = ok && exit == null;
  const badgeCls = skipTcc ? "warn" : (ok ? "ok" : "err");
  const badgeTxt = skipTcc
    ? "denetlenemedi (TCC)"
    : (ok ? (auto ? "GÜNCEL (otomatik sync)" : "GÜNCEL")
          : (exit === 1 ? "BAYAT" : "hata"));
  let h = '<span class="badge ' + badgeCls + '">' + badgeTxt + '</span> ' +
    '<span class="muted">K17 exit=' + (exit != null ? exit : "—") +
    (auto ? ' · auto_synced ✓ (before=' + m.before_exit + ')' : '') + '</span>';
  h += '<div style="margin-top:6px;font-size:12px">' +
    escapeHTML(m.detail || "") + '</div>';
  if (stale.length) {
    h += '<div style="margin-top:8px;font-size:12px;font-weight:600;color:var(--warn)">' +
      'BAYAT/EKSİK dosyalar (' + stale.length + '):</div>' +
      '<ul style="margin:4px 0 0 0;padding-left:18px;font-size:12px;color:var(--warn)">' +
      stale.map(f => '<li><code>' + escapeHTML(f) + '</code></li>').join("") +
      '</ul>';
  } else if (ok) {
    h += '<div style="margin-top:6px;font-size:12px;color:var(--ok)">' +
      '✓ repo ↔ mirror birebir — bayat dosya yok</div>';
  }
  bodyEl.innerHTML = h;
}

// ---- Pattern drift panel — merge pattern ↔ ARTIFACT_JOBS tutarlılığı ----
// Kaynak: /api/latest `pattern_drift` (PASS/DRIFT) + `pattern_drift_detail`.
function renderPatternDrift(data) {
  const bodyEl = $("pattern-drift-body"), tsEl = $("pattern-drift-ts");
  if (!bodyEl) return;
  const ts = data && data.ts;
  if (tsEl) tsEl.textContent = ts ? fmtTs(ts) : "";
  const drift = data && data.pattern_drift;
  const detail = data && data.pattern_drift_detail;
  if (drift == null) {
    bodyEl.innerHTML = '<span class="muted">pattern drift kontrolü bu run\u0027da çalışmadı</span>';
    return;
  }
  if (drift === "PASS") {
    bodyEl.innerHTML = '<span class="badge ok">PASS</span> ' +
      '<span style="margin-left:8px;font-size:13px">merge pattern ↔ ARTIFACT_JOBS tutarlı — eksik/fazla artifact yok</span>';
  } else {
    bodyEl.innerHTML = '<span class="badge err">DRIFT</span> ' +
      '<span style="margin-left:8px;font-size:13px;font-weight:600;color:var(--err)">pattern tutarsızlığı tespit edildi</span>' +
      '<div style="margin-top:8px;font-size:12px;color:var(--warn)">' + escapeHTML(detail || "") + '</div>';
  }
}

// ---- K-layers panel (tek kaynak: d.layers → K0-K17) ----
// K8/K9 enriched by z3_passed/lean_ok detail; others purely from layers.
const K_ALL = ["K0","K1","K2","K3","K4","K5","K6","K7","K8","K9",
               "K10","K11","K12","K13","K14","K16","K17","K18","K20"];

function _cls(st) { return st === "PASS" ? "ok" : st === "FAIL" ? "err" : "warn"; }
function _ico(st) { return st === "PASS" ? "✓" : st === "FAIL" ? "✗" : "·"; }

function renderKLayers(ls, z3p, z3t, z3f, leanOk, leanDetail) {
  const panel = $("klayers-panel");
  if (!panel) return;
  if (!ls || Object.keys(ls).length === 0) {
    panel.innerHTML = '<span class="muted">K-layers: bekleniyor…</span>';
    return;
  }
  let html = '';
  for (const k of K_ALL) {
    const l = ls[k];
    if (!l) continue;
    let st = l.status;
    let title = l.label || '';
    if (k === "K8" && z3p != null) {
      const tot = z3t != null ? z3t : 12;
      const failed = z3f || 0;
      title += " (" + z3p + "/" + tot + (failed > 0 ? " FAIL:" + failed : "") + ")";
    }
    if (k === "K9") {
      if (leanOk === true) title += " PASS";
      else if (leanOk === false) title += " FAIL" + (leanDetail ? " — " + leanDetail : "");
    }
    let kcls = _cls(st);
    if (k === "K9" && leanOk === false) kcls += " fail-pulse";
    html += '<span class="badge ' + kcls + '" title="' + title + '">'
      + _ico(st) + ' ' + k + '</span>';
  }
  panel.innerHTML = html || '<span class="muted">K-layers: veri yok</span>';
}

// ---- Hook env sürümleri (zaman serisi: python/z3/lean/…) ----
const HOOK_TOOLS = ["python", "z3", "lean", "pre_commit", "pdfinfo", "qpdf"];
const HOOK_LABELS = { python: "Python", z3: "Z3", lean: "Lean",
                      pre_commit: "pre-commit", pdfinfo: "pdfinfo", qpdf: "qpdf" };

function shortVer(v) {
  if (v == null) return "—";
  const s = String(v);
  return s.length > 44 ? s.slice(0, 44) + "…" : s;
}

function renderHookEnv(rows) {
  const body = $("he-body"), tsEl = $("he-ts");
  if (!body) return;
  if (!rows || !rows.length) {
    body.innerHTML = '<div class="muted">henüz run yok</div>';
    if (tsEl) tsEl.textContent = "";
    return;
  }
  const lastSeen = {};
  const transitions = [];
  for (const r of rows) {
    const env = r.hook_env;
    if (!env || typeof env !== "object") continue;
    for (const tool of HOOK_TOOLS) {
      const v = env[tool];
      if (v == null) continue;
      if (lastSeen[tool] === undefined) {
        lastSeen[tool] = { v, ts: r.ts };
      } else if (lastSeen[tool].v !== v) {
        transitions.push({ tool, from: lastSeen[tool].v, to: v, ts: r.ts });
        lastSeen[tool] = { v, ts: r.ts };
      } else {
        lastSeen[tool].ts = r.ts;
      }
    }
  }
  let html = '<table><thead><tr><th>Tool</th><th>Current version</th>' +
    '<th>Değişiklik</th><th>Son görülme</th></tr></thead><tbody>';
  for (const tool of HOOK_TOOLS) {
    const s = lastSeen[tool];
    const n = transitions.filter(t => t.tool === tool).length;
    html += '<tr><td><code>' + (HOOK_LABELS[tool] || tool) + '</code></td>' +
      '<td><code>' + (s ? escapeHTML(shortVer(s.v)) : "—") + '</code></td>' +
      '<td>' + (n ? '<span class="badge warn">' + n + '</span>' : '<span class="badge ok">0</span>') + '</td>' +
      '<td class="ts">' + (s ? fmtTs(s.ts) : "—") + '</td></tr>';
  }
  html += '</tbody></table>';
  if (transitions.length) {
    html += '<div class="ts" style="margin-top:8px">Sürüm değişiklikleri (yeni → eski):</div>';
    const rev = transitions.slice().reverse().slice(0, 20);
    for (const t of rev) {
      html += '<div style="margin:3px 0"><span class="badge info">' + (HOOK_LABELS[t.tool] || t.tool) + '</span> ' +
        '<code>' + escapeHTML(shortVer(t.from)) + '</code> → <code>' + escapeHTML(shortVer(t.to)) + '</code> ' +
        '<span class="ts">' + fmtTs(t.ts) + '</span></div>';
    }
  } else {
    html += '<div class="muted" style="margin-top:8px">henüz sürüm değişikliği yok</div>';
  }
  body.innerHTML = html;
  if (tsEl) tsEl.textContent = fmtTs(rows[rows.length - 1].ts);
}

// Deterministik sürüm → renk haritası (aynı sürüm aynı renk, panel sıralı).
const ENV_TREND_CACHE = { svg: [], legend: [] };
function envVersionColor(v) {
  if (v == null) return "#21262d";  // yok/None → koyu boş kutucuk
  const pal = ["#58a6ff", "#3fb950", "#d29922", "#bc8cff", "#f85149",
               "#79c0ff", "#ff7b72", "#a5d6ff", "#aff5b4", "#f0b429",
               "#d2a8ff", "#e3b341"];
  let h = 0;
  const s = String(v);
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return pal[h % pal.length];
}
let heTrendCache = [];
function showHookEnvTrendTip(i, ev) {
  const r = heTrendCache[i];
  if (!r) return;
  const env = r.hook_env || {};
  const tip = $("tip");
  const lines = [
    "run : " + fmtTs(r.ts),
    "verdict : " + (r.verdict || "—"),
    "── araç sürümleri ──",
  ];
  for (const t of HOOK_TOOLS) {
    lines.push("  " + (HOOK_LABELS[t] || t) + ": " +
      (env[t] != null ? String(env[t]) : "—"));
  }
  tip.innerHTML = lines.join("\n");
  tip.style.display = "block";
  positionTip(ev);
}
// Hook env araç sürümleri zaman serisi (refs-trend deseni): her araç bir satır,
// her hücre o run'daki sürümün rengi. Sürüm değişimi = yatay renk bandı kırılması.
function renderHookEnvTrend(rows) {
  const svg = $("he-trend"), legend = $("he-trend-legend");
  if (!svg) return;
  const have = (rows || []).filter(r => r.hook_env && typeof r.hook_env === "object");
  heTrendCache = have;
  const tools = HOOK_TOOLS.slice();
  if (!have.length) {
    svg.innerHTML = "";
    if (legend) legend.textContent = "hook env sürüm verisi yok — probe edilmedi";
    return;
  }
  const W = 1160, H = 240, PL = 96, PT = 14, PB = 30;
  const iw = W - PL - 20, ih = H - PT - PB;
  const n = have.length;
  const rowsT = tools.length;
  const x = (i) => PL + (n === 1 ? iw / 2 : iw * i / (n - 1));
  const y = (t) => PT + (t + 0.5) * ih / rowsT;
  const bandH = Math.max(6, ih / rowsT);

  let parts = [];
  // araç etiketleri (sol eksen)
  tools.forEach((t, ti) => {
    parts.push(`<text x="${PL - 8}" y="${y(ti) + 4}" fill="#8b949e" font-size="11" text-anchor="end">${HOOK_LABELS[t] || t}</text>`);
  });
  // hücre başına yatay bant: run index üzerinden renk = sürüm
  have.forEach((r, i) => {
    const env = r.hook_env || {};
    const w0 = n === 1 ? iw : (i === 0 ? (iw / (n - 1)) : (iw / (n - 1)));
    tools.forEach((t, ti) => {
      const v = env[t];
      const color = envVersionColor(v);
      const cx0 = (i === 0 ? PL : (PL + iw * (i - 0.5) / (n - 1)));
      const cx1 = (i === n - 1 ? PL + iw : (PL + iw * (i + 0.5) / (n - 1)));
      const wCell = cx1 - cx0;
      const hc = v == null ? bandH * 0.55 : bandH * 0.78;
      parts.push(`<rect x="${cx0.toFixed(2)}" y="${(y(ti) - hc / 2).toFixed(2)}" width="${wCell.toFixed(2)}" height="${hc.toFixed(2)}" fill="${color}" fill-opacity="0.85" stroke="#0d1117" stroke-width="0.5"/>`);
    });
  });
  // hover hit sütunları (tüm araçları kapsar) — tooltip: run ts + araç sürümleri
  const rColW = n === 1 ? iw : iw / (n - 1);
  const rHalfW = Math.max(6, Math.min(16, rColW / 2));
  have.forEach((r, i) => {
    parts.push(`<rect x="${(x(i) - rHalfW).toFixed(2)}" y="${PT}" width="${(rHalfW * 2).toFixed(2)}" height="${ih}" fill="transparent" style="cursor:crosshair" onmousemove="showHookEnvTrendTip(${i}, event)" onmouseleave="hideTrendTip()"/>`);
  });
  svg.innerHTML = parts.join("\n");
  if (legend) {
    // lejant: hangi sürüm hangi renkte (son gözlem + değişim sayısı)
    const seen = {};
    const changes = {};
    (have.map(r => r.hook_env)).forEach((env, i) => {
      for (const t of tools) {
        const v = env[t];
        if (v == null) continue;
        if (!seen[t]) seen[t] = { first: v, ts: have[i].ts };
        if (seen[t].last !== undefined && seen[t].last !== v) changes[t] = (changes[t] || 0) + 1;
        seen[t] = { ...seen[t], last: v };
      }
    });
    const partsL = ["Sürüm değişimleri:"];
    for (const t of tools) {
      const c = changes[t] || 0;
      partsL.push((HOOK_LABELS[t] || t) + ": " +
        (c ? `${c} değişim` : "sabit"));
    }
    legend.textContent = partsL.join("  ·  ");
  }
}

function renderHookEnvDrift(matrix) {
  // Kaynak: /api/latest `hook_env_matrix` (~/LATEST hook_env ↔ HOOK_ENV_MATRIX.md).
  const el = $("he-matrix");
  if (!el) return;
  const tools = (matrix && matrix.tools) || [];
  const verdict = (matrix && matrix.verdict) || (tools.length ? "OK" : "—");
  if (!tools.length) {
    el.innerHTML = '<div class="muted">matris verisi yok (hook_env prob edilmedi)</div>';
    return;
  }
  const badge = verdict === "DRIFT" ?
    '<span class="badge err">DRIFT</span>' :
    '<span class="badge ok">OK · matrix ile uyumlu</span>';
  let html = '<div style="margin-bottom:8px">Son run araçları ↔ ' +
    '<code>docs/HOOK_ENV_MATRIX.md</code> beklenen pin: ' + badge + '</div>';
  html += '<table><thead><tr><th>Tool</th><th>Beklenen pin (matris)</th>' +
    '<th>Gözlenen (son run)</th><th>Durum</th></tr></thead><tbody>';
  for (const t of tools) {
    const label = HOOK_LABELS[t.tool] || t.tool;
    const exp = t.expected ? '<code>' + escapeHTML(shortVer(t.expected)) + '</code>' : '—';
    const obs = t.observed ? '<code>' + escapeHTML(shortVer(t.observed)) + '</code>' : '<span class="muted">yok</span>';
    let status;
    if (t.status === "ok") status = '<span class="badge ok">✓</span>';
    else if (t.status === "missing")
      status = '<span class="badge warn">eksik — matris bekleniyor</span>';
    else status = '<span class="badge err">doc dışı — HOOK_ENV_MATRIX.md\'de yok</span>';
    html += '<tr><td><code>' + label + '</code></td><td>' + exp + '</td>' +
      '<td>' + obs + '</td><td>' + status + '</td></tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
  const tsEl = $("he-matrix-ts");
  if (tsEl && matrix && matrix.observed_ts) tsEl.textContent = fmtTs(matrix.observed_ts);
}

function fmtVal(v) {
  if (v == null) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function applySnapshotInner(d) {
  // Schema Sync rozeti: config_sync özeti (verify.yml ↔ CONFIG_BASENAMES)
  renderConfigSync(d.config_sync);

  // Env drift paneli: son run hook_env ↔ matris beklenen pin (ödeme/SSE).
  if (d.hook_env_matrix) renderHookEnvDrift(d.hook_env_matrix);

  // Bütçe limiti TEK KAYNAK: /api/latest `budget.limit` (etkin config
  // budget_usd aynası). Config değişince grafik referans çizgisi + kart
  // otomatik uyum sağlar; snapshot yoksa 30.0 fallback kalır.
  if (d.budget && d.budget.limit > 0 && d.budget.limit !== BUDGET_LIMIT) {
    BUDGET_LIMIT = d.budget.limit;
    // Trend grafiği cache'liyse yeni limitle yeniden çiz (config değişikliği)
    if (trendCache.length) renderTrend(trendCache);
  }

  // Status board: CI consolidate_summary.py ile aynı 5 ikonlu tek satır
  if (d.status_board) {
    $("status-board").textContent = d.status_board;
    $("status-board").style.color = d.status_board.includes("🔴") ? "#c0392b" : "#27ae60";
  }

  // Pre-commit hooks panel: PRECOMMIT_RAPORU.json'dan okunan hook durumları
  const hooksEl = $("precommit-hooks");
  if (hooksEl && d.precommit_hooks && d.precommit_hooks.length > 0) {
    hooksEl.innerHTML = d.precommit_hooks.map(h => {
      const icon = h.status === "Passed" ? "✅" : "❌";
      const color = h.status === "Passed" ? "var(--ok)" : "var(--err)";
      return `<span style="margin-right:10px;color:${color}">${icon} <span style="color:var(--fg)">${h.name}</span></span>`;
    }).join("");
  } else if (hooksEl) {
    hooksEl.innerHTML = "<span style='color:var(--muted)'>⏳ hook verisi bekleniyor…</span>";
  }

  // K15 history sidecar: history.jsonl.sha256 hash'i (persist_history atomik yazar)
  const k15El = $("k15-sidecar");
  if (k15El) {
    if (d.history_sidecar_sha256) {
      const h = d.history_sidecar_sha256;
      k15El.innerHTML = `<span style="color:var(--ok)">🔒</span> K15 sidecar: <code style="font-size:10px;color:#666">${h.substring(0, 16)}…</code>`;
    } else {
      k15El.innerHTML = "<span style='color:var(--muted)'>⏳ K15 sidecar bekleniyor…</span>";
    }
  }

  // Findings panel: P0/P1 bulgu satırları (snapshot veya canlı akış)
  const fpEl = $("findings-panel");
  if (fpEl) {
    const findings = d.findings || [];
    // Canlı akışta liveFindings varsa onu kullan (daha taze)
    if (liveFindings.length > 0 && findings.length === 0) {
      renderLiveFindings();
    } else if (findings.length === 0 && liveFindings.length === 0) {
      fpEl.innerHTML = "";
    } else if (findings.length > 0) {
      const p0s = findings.filter(f => f.priority === "P0");
      const p1s = findings.filter(f => f.priority === "P1");
      let html = "<div style=\"font-size:12px;padding:4px 0\">";
      if (p0s.length) {
        html += p0s.map(f => `<div style=\"color:var(--err);margin:2px 0\">🔴 <b>P0</b> <span style=\"color:#999\">${f.id || f.label || ''}</span> ${f.message || ''}</div>`).join("");
      }
      if (p1s.length) {
        html += p1s.map(f => `<div style=\"color:var(--warn);margin:2px 0\">🟡 <b>P1</b> <span style=\"color:#999\">${f.id || f.label || ''}</span> ${f.message || ''}</div>`).join("");
      }
      html += "</div>";
      fpEl.innerHTML = html;
    }
  }

  // Verdict badge + value
  const verdict = d.verdict || "UNKNOWN";
  $("m-verdict").textContent = verdict;
  $("m-verdict").className = "value " + (
    verdict === "PASS" ? "ok" :
    verdict === "FAIL" ? "err" : "");
  $("m-ts").textContent = fmtTs(d.ts);

  // P0/P1
  const p0 = d.p0 ?? "?", p1 = d.p1 ?? "?";
  $("m-p0p1").textContent = p0 + " / " + p1;
  $("m-p0p1").className = "value " + (
    p0 === 0 && p1 === 0 ? "ok" :
    p0 > 0 ? "err" : "warn");

  // Duration; duration_pct_warn is the server-side relative-duration guard.
  $("m-dur").textContent = d.duration_s != null ? d.duration_s + " s" : "—";
  const durationWarnEl = $("duration-pct-warn");
  if (durationWarnEl) {
    durationWarnEl.innerHTML = d.duration_pct_warn
      ? '<span class="badge warn" title="Göreli süre eşiği aşıldı">⚠ süre normalin üzerinde</span>'
      : '';
  }

  // Bütçe sparkline: snapshot'ta budgetState varsa history'e ekle
  if (d.budget_usd != null && d.budget_limit != null) {
    if (budgetHistory.length === 0 ||
        budgetHistory[budgetHistory.length - 1].est !== d.budget_usd) {
      budgetHistory.push({ est: d.budget_usd, limit: d.budget_limit });
      if (budgetHistory.length > 60) budgetHistory = budgetHistory.slice(-60);
    }
    renderBudgetSparkline();
  }

  // Budget — limit /api/latest `budget.limit`'ten (applySnapshot başında senkronlanır)
  $("m-budget").textContent = d.budget_usd != null ? "$" + d.budget_usd.toFixed(2) : "—";
  const limTxt = "$" + fmtLimit(BUDGET_LIMIT);
  $("m-budget-sub").textContent = (d.budget_usd != null && d.budget_usd < BUDGET_LIMIT)
    ? "✓ under " + limTxt + " limit"
    : (d.budget_usd != null ? "⚠ over " + limTxt : "limit " + limTxt);

  // PDF pages + refs (ayrı kartlar)
  $("m-pages").textContent = d.pdf_pages || "—";
  $("m-refs").textContent = d.ref_count || "—";

  // Metadata-stripped
  if (d.stripped_sha256) {
    $("m-meta").textContent = d.stripped_sha256.slice(0, 16) + "…";
    $("m-meta-sub").textContent = "drift: " + (d.stripped_sha256 !== (d.expected_stripped || "").slice(0,16) ? "yes" : "no");
    $("pdf-hash").textContent = d.stripped_sha256.slice(0, 16) + "…";
  }

  // Top-level badges
  const badges = $("badges");
  badges.innerHTML = "";
  const addBadge = (cls, text) => {
    const s = document.createElement("span");
    s.className = "badge " + cls;
    s.textContent = text;
    badges.appendChild(s);
  };
  // K-layer panel — tek kaynak: d.layers (K0-K17)
  // K8/K9 enriched by z3_passed/lean_ok from server.
  const ls = d.layers || {};
  renderKLayers(ls, d.z3_passed, d.z3_total, d.z3_failed, d.lean_ok, d.lean_detail);
  // K8 Z3 rozeti — son run'ın GERÇEK sonucundan (sunucu stderr'deki
  // [PASS]/[FAIL] P1-5 özet tablosunu sayar; veri yoksa '?' gösterir).
  if (d.z3_passed != null) {
    const ztot = d.z3_total != null ? d.z3_total : 12;
    const zcls = (d.z3_failed || 0) > 0 ? "err" : (d.z3_passed >= ztot ? "ok" : "warn");
    addBadge(zcls, "K8 Z3: " + d.z3_passed + "/" + ztot +
      ((d.z3_failed || 0) > 0 ? " (" + d.z3_failed + " FAIL)" : "") +
      " (son çalıştırma)");
  } else {
    addBadge("warn", "K8 Z3: ? (son çalıştırma yok)");
  }
  // K9 Lean rozeti — son run'ın GERÇEK sonucundan (sunucu stderr'deki
  // '[K9] Lean 4 reduct-invariance: PASS/FAIL — detail' satırını ayrıştırır;
  // K9 satırı yoksa '?' gösterir — koşulmamış run'ları FAIL gibi göstermez).
  // Lean FAIL animasyonlu uyarıcı (badge + status board altında alert)
  const la = $("lean-alert");
  if (d.lean_ok === true) {
    addBadge("ok", "K9 Lean: PASS (son çalıştırma)");
    if (la) la.classList.add("hidden");
  } else if (d.lean_ok === false) {
    addBadge("err", "K9 Lean: FAIL" +
      (d.lean_detail ? " — " + d.lean_detail : "") + " (son çalıştırma)");
    if (la) {
      la.classList.remove("hidden");
      la.textContent = "⚠ K9 Lean: FAIL — " + (d.lean_detail || "ispat zinciri kırık");
    }
  } else {
    addBadge("warn", "K9 Lean: ? (koşulmadı)");
    if (la) la.classList.add("hidden");
  }
  addBadge(p1 === 0 ? "ok" : "warn", "Beth 1953: " + (p1 === 0 ? "düzeltildi" : p1 + " P1"));
  // Soy hattı rozeti — son run'ın lineage_summary durumundan (sunucu
  // verify_delivery.py --json lineage.generations'dan çıkarılan son nesil
  // bilgisi; akış satırını beklemeden anında görünür).
  const lin = d.lineage_summary;
  if (lin) {
    const lcls = lin.ok ? "ok" : "err";
    addBadge(lcls, "Soy hattı: " + lin.current_note +
      " (" + lin.current_hash + "…) · " + lin.count + " nesil");
  }
  // Budget override rozeti — son run'ın cli_overrides durumundan (sunucu
  // verify_delivery.py --json config.cli_overrides'ını LATEST'e taşır; akış
  // satırını beklemeden anında görünür). override=true varsa sarı (sapma),
  // yoksa gri/sessiz geçer (rozet gürültü yapmaz).
  const cov = d.cli_overrides || {};
  const ovKeys = Object.keys(cov).filter(k => (cov[k] || {}).override);
  if (ovKeys.length) {
    const ovDetail = ovKeys.map(k =>
      "`" + k + "`: " + (cov[k].file_value != null ? cov[k].file_value : "?") +
      " → " + cov[k].effective).join(" · ");
    addBadge("warn", "Budget override: " + ovKeys.length + " (" + ovDetail + ")");
  }
  // refs rozeti — son run'ın GERÇEK references_online sonucundan, Z3 rozetiyle
  // aynı stilde: uyuşmazlık/doğrulanamayan sayısını ayrı gösterir.
  if (d.refs_total != null && d.refs_verified != null) {
    const full = d.refs_verified === d.refs_total;
    const mism = d.refs_mismatch || 0;
    const unv = Math.max(0, d.refs_total - d.refs_verified - mism);
    const cls = mism > 0 ? "err" : (full ? "ok" : "warn");
    let txt = "refs: " + d.refs_verified + "/" + d.refs_total + " online";
    const parts = [];
    if (mism > 0) parts.push(mism + " MISMATCH");
    if (unv > 0) parts.push(unv + " UNVERIFIED");
    if (parts.length) txt += " (" + parts.join(", ") + ")";
    addBadge(cls, txt);
  } else {
    addBadge(d.ref_count === 64 ? "ok" : "warn", "refs: " + (d.ref_count || "?"));
  }

  // Fields formerly refreshed through /api/latest now arrive in the SSE
  // snapshot projection from preview_server.py.
  loadTrend();
  renderRefsOnline(d);
  renderConfigDiff(d.config_diff, d.ts);
  renderCliOverride(d);
  if (d.budget) renderBudget(d.budget);
  renderMirrorSync(d);
  renderPatternDrift(d);
  if (d.stdout_short) applyStdout(d.stdout_short);
  if (d.stderr_short && d.exit_code !== 0) applyStdout(d.stderr_short);

  if (d.stdout_short) {
    const refItems = [];
    const lines = d.stdout_short.split("\n");
    for (const line of lines) {
      const m = line.match(/^\s*\[(OK|FAIL|SKIP)\]\s+(CrossRef|SEP|OpenLib)\s+(\S.*?)\s+->\s+(.*)$/);
      if (m) refItems.push({tag: m[1], src: m[2], name: m[3], detail: m[4].trim()});
    }
    if (refItems.length) {
      const list = $("refs");
      list.innerHTML = "";
      for (const r of refItems.slice(0, 50)) {
        const li = document.createElement("li");
        const tag = r.tag === "OK" ? "ok" : r.tag === "FAIL" ? "err" : "warn";
        li.innerHTML = `<span class="badge ${tag}" style="min-width:42px;text-align:center">${r.tag}</span>` +
          `<span style="min-width:60px;color:var(--muted)">${r.src}</span>` +
          `<span style="flex:1">${escapeHTML(r.name)}</span>`;
        list.appendChild(li);
      }
    }
  }
}

function applySnapshot(d) {
  if (!d) return;  // no snapshot to apply — SSE/stream only calls with real data
  if (useViewTransitions) {
    document.startViewTransition(() => applySnapshotInner(d));
  } else {
    applySnapshotInner(d);
  }
}

function applyStdout(text) {
  const el = $("stdout");
  el.innerHTML = colorizeStdout(text);
  el.scrollTop = el.scrollHeight;
}

let rhFilter = "all";  // all | PASS | FAIL | P0
const RUN_HISTORY_CACHE_MS = 30000;
let runHistoryCache = null;
let runHistoryFetchedAt = null;
let runHistoryRequest = null;

function setRhFilter(f) {
  rhFilter = f;
  // Buton stilleri
  document.querySelectorAll(".rh-filter button").forEach(b => {
    b.classList.toggle("active", b.dataset.f === f);
  });
  loadRunHistory();
}

function loadRunHistory(fromSSE = false) {
  if (runHistoryRequest) return runHistoryRequest;
  if (fromSSE && runHistoryCache !== null && runHistoryFetchedAt !== null &&
      Date.now() - runHistoryFetchedAt < RUN_HISTORY_CACHE_MS) {
    return Promise.resolve(runHistoryCache);
  }
  runHistoryRequest = fetch("/api/run-history?_t=" + Date.now()).then(r => r.json()).then(rows => {
    runHistoryCache = rows;
    runHistoryFetchedAt = Date.now();
    const el = $("run-history");
    if (!rows.length) {
      el.innerHTML = "<span class=\"muted\">henüz run yok</span>";
      return rows;
    }
    const cnt = $("run-history-count");
    // Filtreleme: all → hepsi, PASS → verdict=ok, FAIL → fail/error, P0 → p0>0
    let filtered = rows;
    if (rhFilter === "PASS") {
      filtered = rows.filter(r => r.verdict === "PASS" && (r.p0||0) === 0);
    } else if (rhFilter === "FAIL") {
      filtered = rows.filter(r => r.verdict === "FAIL" || r.verdict === "ERROR");
    } else if (rhFilter === "P0") {
      filtered = rows.filter(r => (r.p0||0) > 0);
    }
    const fSuffix = rhFilter !== "all" ? " / " + rows.length : "";
    if (cnt) cnt.textContent = "(" + filtered.length + fSuffix + ")";
    if (!filtered.length) {
      el.innerHTML = "<span class=\"muted\">filtreyle eşleşen run yok</span>";
      return;
    }
    const lines = filtered.slice().reverse().map(r => {
      const sv = r.verdict || "?";
      const cls = sv === "PASS" ? "ok" : (sv === "FAIL" || sv === "ERROR" ? "err" : "warn");
      const t = r.ts && r.ts.indexOf("T") >= 0 ? r.ts.split("T")[1].slice(0, 8) : "?";
      const dur = r.duration_s != null ? r.duration_s.toFixed(0) + "s" : "—";
      const bud = r.budget_usd != null ? "$" + r.budget_usd.toFixed(2) : "—";
      const refs = r.refs_verified != null ? r.refs_verified + "/" + r.refs_total : "?/?";
      const pg = r.pdf_pages != null ? r.pdf_pages : "?";
      // K9 Lean renkli gösterge: PASS=● yeşil, FAIL=● kırmızı, koşulmadı=gri tire
      let lean = "";
      if (r.lean_ok === true) {
        lean = `<span style="color:var(--ok)" title="Lean PASS">●</span>`;
      } else if (r.lean_ok === false) {
        const ld = r.lean_detail ? " — " + r.lean_detail : "";
        lean = `<span style="color:var(--err)" title="Lean FAIL${ld}">●</span>`;
      } else {
        lean = `<span class="muted" title="Lean: koşulmadı">·</span>`;
      }
      // Bütçe aşımı: run budget_usd > BUDGET_LIMIT ise kırmızı AŞIM rozeti
      // (şerit + trend ile aynı kural — tek kaynak BUDGET_LIMIT).
      const over = r.budget_usd != null && BUDGET_LIMIT != null
        && isFinite(BUDGET_LIMIT) && r.budget_usd > BUDGET_LIMIT;
      const overBadge = over
        ? `<span class="rh-over" title="BÜTÇE AŞIMI: $${r.budget_usd.toFixed(2)} > limit $${fmtLimit(BUDGET_LIMIT)}">AŞIM</span>`
        : "";
      // Kaynak rozeti: run'un geldiği yol (smoke/daemon/verify). source
      // alanı olmayan eski kayıtlar daemon varsayılır (server persist).
      const srcBadge = r.source || "daemon";
      const srcEl = `<span class="source-badge ${srcBadge}">${srcBadge}</span>`;
      const text = `<span class=\"muted\">${t}</span> <span class=\"${cls}\">${sv}</span> ` +
        `<span class=\"muted\">P0=${r.p0||0} P1=${r.p1||0} refs=${refs} ${pg}p ${bud} ${dur}</span>` +
        ` ${lean}${overBadge}${srcEl}`;
      const tsAttr = r.ts ? r.ts.replace(/'/g, "\'").replace(/"/g, "&quot;") : "";
      return `<div class="rh-row" data-ts="${tsAttr}" onclick="loadRunStdout('${tsAttr}')" ` +
        `title="Tıklayınca bu run'un stdout'u yüklenir">${text}</div>`;
    });
    el.innerHTML = lines.join("\n");
    return rows;
  }).catch(() => null).finally(() => { runHistoryRequest = null; });
  return runHistoryRequest;
}

function loadRunStdout(ts) {
  if (!ts) return;
  const el = $("stdout");
  if (el) el.textContent = "Yükleniyor…";
  fetch("/api/run-stdout?ts=" + encodeURIComponent(ts)).then(r => r.json()).then(d => {
    if (d.stdout != null) applyStdout(d.stdout + (d.stderr ? "\n--- STDERR ---\n" + d.stderr : ""));
    else if (d.error) applyStdout("Hata: " + d.error);
  }).catch(err => {
    if (el) el.textContent = "Yüklenemedi: " + err;
  });
}

function connect() {
  if (evtSource) evtSource.close();
  setLive("connecting");
  evtSource = new EventSource("/api/run?v=" + (window.BUILD_TS||Date.now()));
  evtSource.addEventListener("snapshot", (e) => {
    try {
      const d = JSON.parse(e.data);
      applySnapshot(d);
      setLive("ok");
      lastTs = Date.now();
      reconnectDelay = 1000; // reset backoff on success
      // Run history'yi de güncelle (yeni run snapshot'ı gelince)
      loadRunHistory(true);
    } catch(err) { console.error("snapshot parse", err); }
  });
  evtSource.addEventListener("update", (e) => {
    try {
      const d = JSON.parse(e.data);
      applySnapshot(d);
      setLive("ok");
      lastTs = Date.now();
      // Run history'yi de güncelle (yeni run update'i gelince)
      loadRunHistory(true);
    } catch(err) { console.error("update parse", err); }
  });
  evtSource.onerror = () => {
    setLive("err");
    // Exponential backoff: 1s → 2s → 4s → ... → 30s max
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
  };
}

$("reconnect").addEventListener("click", connect);
$("theme-toggle").addEventListener("click", () => {
  setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
});

// staleness watchdog: 90s boyunca güncelleme yoksa "stale" göster
setInterval(() => {
  if (Date.now() - lastTs > 90000) setLive("warn");
}, 30000);

loadTrend();
loadOverrideTrend();
connectStream();
// Run history filtresini başlat (all varsayılan)
setRhFilter("all");
connect();

(() => {
  const names = ['P1-a','P1-b','P2','P3-a','P3-b','P4-a','P4-b','P4-c','P4-d','P4-e','P5','P5-note'];
  const root = document.getElementById('z3-slides');
  const box = document.getElementById('z3-lightbox');
  const image = document.getElementById('z3-lightbox-image');
  let index = 0;
  function src(i) { return '/slides_z3/' + names[i] + '.png'; }
  function show(i) {
    index = (i + names.length) % names.length;
    image.src = src(index);
    image.alt = names[index] + ' Z3 slaytı';
  }
  function open(i) {
    show(i); box.hidden = false; document.getElementById('z3-close').focus();
  }
  function close() { box.hidden = true; root.querySelector('button')?.focus(); }
  root.querySelectorAll('.z3-slide').forEach((button, i) => {
    button.addEventListener('click', () => open(i));
  });
  document.getElementById('z3-prev').addEventListener('click', () => show(index - 1));
  document.getElementById('z3-next').addEventListener('click', () => show(index + 1));
  document.getElementById('z3-close').addEventListener('click', close);
  box.addEventListener('click', e => { if (e.target === box) close(); });
  document.addEventListener('keydown', e => {
    if (box.hidden) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowLeft') show(index - 1);
    else if (e.key === 'ArrowRight') show(index + 1);
  });
})();
