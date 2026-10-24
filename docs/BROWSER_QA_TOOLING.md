# Tarayıcı QA Araç Seçimi — Orca embedded browser vs agent-browser

> **Diátaxis: Reference / scenario-matrix** — Amacı: repodaki tarayıcı-QA işleri
> için hangi araç hangi senaryoda kullanılır sorusunu cevaplamak. Öğretici değil
> (nasıl koşulur için bkz. `orca skills get orca-cli` ve
> `agent-browser skills get core`), performans kıyası da değil (o ölçüm yer:
> `_calisma/CIKTI/agent-browser_vs_playwright_bellek_kiyas.md`).

Bu belge **2026-10-07** durumunu yansıtır: `orca` CLI (app kapalıyken algılanan son yüklü sürüm `/usr/local/bin/orca`) ve `agent-browser 0.27.0`; bkz. "Doğrulama kaydı" ve "Sınırlılıklar".

## 1. İki aracın kimliği (doğrulanmış, tahmin değil)

| | **Orca built-in browser** (`orca …`) | **agent-browser** (`agent-browser …`) |
|---|---|---|
| Ne | Orca uygulamasına gömülü, **worktree-kapsamlı** sekme yüzeyi | Bağımsız Rust CLI; Chrome/Chromium'u CDP ile sürer |
| Motor | Orca'nın kendi gömülü sayfası ("not Chrome, Safari, or Orca's own app UI") | Bağımsız yüklediği **Chrome for Testing 153.0.8010.47** (`~/.agent-browser/browsers/…`) |
| Aldığı kaynak | Orca uygulaması çalışıyor olmalı — uygulama kapalıyken `tab list --json` → `runtime_unavailable: "Could not read Orca runtime metadata … Start the Orca app first."` | Kendi daemon'ı (`agent-browser-darwin-arm64`, ölçülen ~9.3 MB) + Chrome ağacı |
| A11y çıktı | `orca snapshot` — element ref'leri (`@e1` benzeri) | `agent-browser snapshot -i` — aynı kalıp, `[ref=eN]`; ölçülü: çalışma sayfasında **4,399 B / 106 satır** |
| Oturum durumu | `tab profile` ailesi: profile create/clone/switch (worktree'a bağlı) | `--session` ailesi + auth vault + video kaydı |
| Sayfa-affinity | **Orca worktree tablosuna bağlı**: içindeki sekme kendi izolasyonunda çalışır; Orca UI dışından bakan Playwright/CDP göremez | Herhangi bir URL; dış Chrome/Safari gerekirse ayrı yol |
| Kompoze kullanım | `orca exec --command "…"` (agent-browser komutlarını bu yüzeyden de çalıştırabilir) | `agent-browser exec` yok; komutlar birer-bir |
| Sınırlı-görüş | Orca dışına dokunmaz: Orca UI/settings veya dış webview **Computer Use**'a gider | Orca uygulamasının iç yüzeyine (app chrome) erişemez |

`orca exec --command …` köprüsü önemli: Orca, agent-browser'ı **alt araç**
olarak çalıştırabilir; dolayısıyla ikisi rekabet değil, bazen kompozit.

## 2. Senaryo-matrisi — hangi iş için hangi araç

Karar sütununun okunuşu: "✔ araç doğal", "⚠ araç çalışır ama pahalı/yerine düşük",
"✖ çatışır/yapamaz".

| # | Senaryo | Orca embedded | agent-browser | Not |
|---|---|---|---|---|
| S1 | **Repo-dashboard QA** (`:8000` preview gibi, Orca dışı sayfa) | ✖ Orca dışı sayfa — Playwright/CDP uygun | ✔ tek-komutlu `open/snapshot/click` | Bizim `preview_server.py` işleri bu kutuya düşer |
| S2 | **Orca worktree'ındaki agent-owned sayfa** (Orca sekmesinde açık, aynı worktree'a bağlı iş) | ✔ worktree-affinity; snapshot/ref akışı yerli | ⚠ erişebilir ama oturum/profil durumu Orca'da kalır | Orca tab listesi aside — en temizi |
| S3 | **Dış site QA** (giriş formları, 3rd-party yüzeyleri) | ⚠ gömülü tarayıcı dış sayfa açar ama bu senaryo ona bırakılmamış | ✔ auth-vault + dev-tools ölçümleri | CDP tabanlı akış |
| S4 | **Elektron/desktop uygulama DOM'u** (VS Code, Slack tarzı) | ✖ | ✔ `agent-browser skills get electron` kendisi bu senaryo için | |
| S5 | **Video/artefact kaydı** | ⚠ yok (tab show/screenshot var) | ✔ `record --output` | |
| S6 | **Multi-session paralel iş** (a/b agent'ları) | ⚠ worktree başına tab | ✔ `--session a/b` izole | |
| S7 | **Hızlı a11y depo konsolu** (repo QA'da PR öncesi smoke) | ✖ | ✔ tek-chrome + `snapshot -i` küçük-ağaç | |
| S8 | **Orca uygulaması durum-sız kullanım** (app kapalı) | ✖ runtime_unavailable (ölçüldü) | ✔ daemon bağımsız | |
| S9 | **Orca tablosu agent handoff akışları** (worktree spawn + prompt) | ✔ `orca worktree create --agent …` | ✖ | Bu, tarayıcı-değil; sadece referans |
| S10 | **Playwright/CDP hedefi gerektiren çağrı** (page.route, SSE interception) | ✖ | ⚠ | Playwright bu iş-yüzdesinde hâlâ birinci |

### Karar kuralı

> **Karar kuralı (tek satır):** İş Orca state'inin (worktree/terminal/sekmeler)
> kaynağıysa VE sayfa Orca'nın gömülü sekmesinde yaşıyorsa → **orca**. Diğer tüm
> browser-QA işleri için → **agent-browser** (dış sayfa, repo-dashboard,
> Elektron, kayıt, çoklu-oturum). Programatik interception gerektiren
> (service-worker block, CSP ölçümü) testlerde birinci → **Playwright/CDP**.

## 3. Bu repo'nun somut QA evi

Bu belge repo'da bugün tarayıcıya bakan 4 yüzeyi kapsar; hepsi S1 kutusuna düşer:

1. `_calisma/CIKTI/test_dashboard_keyboard_nav.py` — Playwright sync API +
   service-worker block + CSP sayacı (SW-geçişli istekler page.route'a
   görünmez olabildiğinden SW bloklanır — suite kendi notu, satır 128–137).
2. `test_dashboard_playwright_smoke.py` — SSE + CSP render smoke.
3. `test_a11y_gate.py` — axe (vendor snapshot; `check_security_browser.list`).
4. Gelecek: agent-browser ile hızlı **manual-repro** (snapshot-to-chat akışı).

Geri-kalan not: **CI'da (headless runner) Playwright kalır** — agent-browser
    daemon'ı CI-container'a ekstra bir bağımlılık getirir; mevcut güven
    süitesi (`check_security_browser.list`) Playwright'a sabittir.

## 4. Doğrulama kaydı (2026-10-07 koşum)

Bu belgedeki yönlü iddiaların kanıtı:

```text
$ orca status --json          → app.running=false, runtime.state=not_running
$ orca tab list --json        → error.code=runtime_unavailable
                                ("Start the Orca app first.")
$ agent-browser --version     → agent-browser 0.27.0
$ agent-browser open http://127.0.0.1:<free>/  → 5,116 ms ilk-yumu (daemon+chrome spawn)
$ agent-browser snapshot -i   → 186 ms, 4,399 B, 106 satır a11y ağaç (ref=eN)
$ agent-browser close --all   → 138 ms, rc=0
ile ölçüm rakamları: agent_browser_vs_playwright_bellek_kiyas.md
(ana süreç 224.8 MB, helper ağacı 1,263.6 MB; Playwright'ta 832.0 MB toplam).
```

Playwright sanity-parçası (senaryo S1/S10 kanıtının yarısı): aynı sayfada
`pg.aria_snapshot()` **6,739–9,009 karakter**, `domcontentloaded` goto
`26–38 ms` warm — yani programatik-interception işyüzdesinde Playwright
hâlâ yeterli; agent-browser'ın "snapshot küçük" avantajı a11y-ağaç boyutunda
kendi payını alır (ağaç ~4.4 KB vs ~9 KB: ~%51 küçük).

## 5. Sınırlılıklar (ölçülmeyen / koşulamayan)

- **Orca embedded browser'ın kendi ölçümü** bu turda alınmadı: Orca
  uygulaması çalışmıyordu (`runtime_unavailable`). S2/S9 satırlarındaki
  "worktree-affinity/not Chrome" iddiaları **CLI reference'tan** gelir
  (`orca skills get orca-cli` → "Built-In Browser" bölümü), live ölçüden değil.
  Uygulama açıkken `orca snapshot`/`orca tab list` tekrar edilmelidir.
- `orca skills get browser` diye bir konu yok (CLI bunu reddetti); browser
  ayrıntısının gerçek kaynağı `ORCA skills get orca-cli` → `references/browser.md`
  (gömülü reference-dosyası; diskte bağımsız bulamadım).
- Performans kıyası için bellek/latency rakamları **ayrı bir turda** ölçüldü
  (`agent-browser_vs_playwright_bellek_kiyas.md`) — bu belge onun
  **karar-yüzü**dür, rakamları tekrar açıklamaz.
- agent-browser sürüm skew'i: kendi Chrome'u (153.0.8010.47) vs
  Playwright'in (chromium-1243) — sürüm-bağımlı davranış farkı tablonun
  "motor" satırında işlendi.
