#!/usr/bin/env python3
"""build_design_preview.py — frontend-design derleme + denetim paketi.

preview.html + preview.js'i tek statik demo dosyasına derler (API hattı mock
snapshot'la beslenir; CSS/kurallar/bağımlılık ağacı üretim HTML'iyle birebir).
renderVerdictSeal'in durum geçişlerini gerçek applySnapshotInner üzerinden
sınar (mock sunucu değil, gerçek kaynak fonksiyon + gerçek DOM).

Çıktı: _calisma/CIKTI/design_preview.html (üretilmiş — commit dışı).
"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "design_preview.html"

html = (HERE / "preview.html").read_text(encoding="utf-8")
js = (HERE / "preview.js").read_text(encoding="utf-8")
tokens = (ROOT / "design-system" / "tokens.css").read_text(encoding="utf-8")

# 1) token sheet'i inline et (link rotası demo'da sunucusuz çalışmaz)
html = html.replace('<link rel="stylesheet" href="/design-system/tokens.css?v=1">',
                    "<style>\n" + tokens + "\n</style>")

# 2) sw.js kaydını nötrle (sunucu yok)
js = js.replace("navigator.serviceWorker.register('/sw.js', { scope: '/' })",
                "Promise.reject(new Error('demo: no sw'))")

# 3) ağ hattını mock'a çevir: connect() + diğer fetch'ler başlatılmasın.
#    Demoya özel: EventSource/fetch/loadRunHistory ucu boş stub'larla tanımlanır,
#    böylece preview.js'in kendi init çağrıları (connect() vb.) zararsız olur.
bootstrap = """
// ── demo mock katmanı (build_design_preview.py ekler) ──
const MOCK_SNAPSHOT = __MOCK_SNAPSHOT__;
const _RealEventSource = window.EventSource;
window.EventSource = class {
  constructor() { this.listeners = {}; }
  addEventListener(name, fn) { (this.listeners[name] = this.listeners[name] || []).push(fn); }
  emit(name, data) { (this.listeners[name] || []).forEach(fn => fn({ data: JSON.stringify(data) })); }
  close() {}
};
const _RealFetch = window.fetch;
window.fetch = function(url) {
  const path = String(url).split("?")[0];
  if (path === "/api/trend") {
    return Promise.resolve({ json: () => Promise.resolve({ history: [], refs_trend: { rows: [], duration_budget: { rows: [] } } }) });
  }
  return Promise.resolve({ json: () => Promise.resolve({ rows: [] }) });
};
window.__demoApplySnapshot = (d) => applySnapshot(d);
// Canlı-durum rozeti de gerçek akış gibi yesile dönsün (snapshot gelir):
setTimeout(() => window.__demoApplySnapshot(MOCK_SNAPSHOT), 50);
"""
# const MOCK_SNAPSHOT'u literal ile göm (hash gövdesi json.dumps ile güvenli)
mock = {
    "ts": "2026-09-18T09:15:00+00:00",
    "verdict": "PASS",
    "status_board": "🟢 🟢 🟢 🟢 🟢 — zincir sağlam",
    "p0": 0, "p1": 0,
    "pdf_hash": {"stripped": "314578497c9d2a41be3f0c6d1e5f8a7b2c4d6e9f0a1b3c5d7e9f1a2b4c6d8e0f"},
}
bootstrap = bootstrap.replace("__MOCK_SNAPSHOT__", json.dumps(mock))
js = bootstrap + "\n" + js

# 4) inline script: preview.js'i göm ve snapshot'ı uygulamadan ÖNCE gerçek
#    applySnapshotInner'la üç durumu sına (PASS/FAIL/hash yok) — sonra canlı
#    demo snapshot'ı kalsın.
inline = """
<script data-build-ts></script>
<script>
__PREVIEW_JS__
(async () => {
  try {
    // s1: hash yok -> seal hidden
    window.__demoApplySnapshot({ verdict: "PASS", status_board: "\\u2705 tamam" });
    const s1 = document.getElementById("verdict-seal").hidden === true;
    // s2: FAIL + hash -> seal-fail + halka metni
    window.__demoApplySnapshot(Object.assign({}, MOCK_SNAPSHOT, { verdict: "FAIL" }));
    const sealEl = document.getElementById("verdict-seal");
    const s2 = sealEl.hidden === false && sealEl.classList.contains("seal-fail") &&
               sealEl.querySelector("textPath").textContent.indexOf("VERIFIED") === 0;
    // s3: PASS + hash -> seal-pass + hash metni
    window.__demoApplySnapshot(MOCK_SNAPSHOT);
    const s3 = sealEl.classList.contains("seal-pass") &&
               sealEl.querySelector(".seal-hash").textContent.indexOf("314578") === 0;
    window.__DESIGN_AUDIT__ = { s1_hidden_without_hash: s1, s2_fail_state: s2, s3_pass_state: s3 };
  } catch (e) {
    window.__DESIGN_AUDIT__ = { error: String(e) };
  }
})();
</script>
"""
inline = inline.replace("__PREVIEW_JS__", js)
html = html.replace('<script data-build-ts></script>\n<script src="preview.js"></script>', inline)

# 5) güvenlik: önceki deneme kalıntısını da kaldır
html = html.replace('<script src="preview.js"></script>', "")

OUT.write_text(html, encoding="utf-8")
print(f"OK {OUT.name} {OUT.stat().st_size} bytes")
