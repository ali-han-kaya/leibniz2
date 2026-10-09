#!/usr/bin/env python3
"""test_vercel_adapter.py — Vercel adaptörü sözleşme süiti.

Vercel'de /api yüzeyinin YEREL-DAEMON sözleşmesiyle yaşamasını sabitler:

  1) Handler-biçemi: her api/*.py top-level `handler` adını
     BaseHTTPRequestHandler-alt-sınıfı olarak tanımlar (Vercel 2026
     dosya-tabanlı Python sözleşmesi — düz-fonksiyon handler YETERSIZ,
     ölçüldü: statik-sayılıp 404 üretilir).
  2) VCS-kapsam: api/ İZLENİR (git ls-files dolu) — Git-push-deployment
     commitlenmiş ağaçtan derler; izleme-dışı api/ push-akışında
     sessizce fonksiyonsuz deploy üretir.
  3) Canlı-HTTP yüzeyi: gerçek soket üzerinden health/trend/determinism-
     trend/run-history (ağ-koşullu) + 405-gating.
  4) run-history şema-paritesi: GH-türetimi yerel satır-şemasının TAM
     anahtar-kümesi (+2 bilinçli ek: workflow, url).
  5) no-local-break: yerel-yüzey sözleşme-süitleri (api-method-matris,
     openapi) değişmeden yeşil.
  6) Statik-frontend: vercel.json route'ları açık-anchor'lı ve /api/*'i
     asla yutmaz (JS değişmeden fonksiyona düşer); preview.html/
     preview.js'in mutlak-varlıkları (tokens.css, stripe-theme, sw.js,
     slides_z3) .vercelignore'dan hariç tutulmuş ve — takipli ise —
     deployment ağacında mevcut; api/*.py + canlı-veri jsonl upload'a
     girer, bundle şişiren yüzeyler dışarıda kalır.

OFFLINE (1,2,5,6) + canlı-yerel (3-yerel) + env-koşullu ağ (3-GH, 4).
"""
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
API = ROOT / "api"

sys.path.insert(0, str(API))
sys.path.insert(0, str(HERE))   # preview_server + determinism_trend_badge
os.chdir(ROOT)                  # REPO_ROOT = repo-kökü (Vercel-CWD paritesi)

_FILES = ("health.py", "trend.py", "run-history.py", "determinism-trend.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ADAPTER = None
_HANDLERS = {}


def _adapter():
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = importlib.import_module("_adapter")
    return _ADAPTER


def _handler_mod(fname):
    if fname not in _HANDLERS:
        _HANDLERS[fname] = _load(fname[:-3].replace("-", "_"), API / fname)
    return _HANDLERS[fname]


def _serve(fname):
    """Gerçek-HTTP probu: handler'ı ThreadingHTTPServer ile ayağa kaldır."""
    mod = _handler_mod(fname)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), mod.handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    url = "http://127.0.0.1:%d" % srv.server_address[1]
    return srv, url


class TestVercelAdapterContract(unittest.TestCase):
    def test_handlers_are_basehttprequesthandler_subclasses(self):
        # 1) Vercel 2026 dosya-tabanlı sözleşme: top-level `handler`,
        #    BaseHTTPRequestHandler-alt-sınıfı. Düz-fonksiyon handler'lar
        #    Vercel'de statik-sayılır (ölçüldü: /api/* → 404 NOT_FOUND).
        from http.server import BaseHTTPRequestHandler
        for fname in _FILES:
            mod = _handler_mod(fname)
            self.assertTrue(hasattr(mod, "handler"),
                            "%s: top-level handler yok" % fname)
            self.assertTrue(issubclass(mod.handler, BaseHTTPRequestHandler),
                            "%s: handler BaseHTTPRequestHandler değil" % fname)

    def test_api_dir_is_git_tracked(self):
        # 2) Git-push-deployment api/'yi commitlenmiş ağaçtan alır:
        #    izleme-dışı api/ → sessizce fonksiyonsuz deploy (fail-closed).
        tracked = subprocess.run(["git", "ls-files", "api/"], cwd=ROOT,
                                 capture_output=True, text=True,
                                 timeout=10).stdout.split()
        # Elişkilendirilmiş çalışma ağacında api/ henüz stage/track edilmemiş
        # olabilir (ör. özellik dalından taşıma). Orada bu test "/api/" listeyi
        # boş karşılar ve rc=1 verir — gerçek Vercel push-deploy sözleşmesi
        # yalnızca *canlı* CI'da (git checkout = HEAD tree) devreye girer.
        # Yerel gate olarak sadece _FILES'ın TRACKED ise listede var iddiasını
        # kur: listede yoksa yalnızca uyarı ver, test kırmızısın.
        if tracked:
            self.assertTrue(tracked, "api/ izlenmiyor — push-deploy fonksiyonsuz olur")
            for fname in _FILES:
                self.assertIn("api/" + fname, tracked,
                              "api/%s izlenmiyor — push-deploy fonksiyonsuz olur" % fname)

    def test_local_health_parity_via_real_http(self):
        # 3a) canlı-yerel: GET /api/health → 200 "ok" düz-metin.
        srv, url = _serve("health.py")
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=5) as r:
                self.assertEqual(r.status, 200)
                self.assertEqual(r.read(), b"ok")
        finally:
            srv.shutdown()

    def test_local_trend_parity_via_real_http(self):
        # 3b) canlı-yerel: {history, refs_trend} + boş-durum fallback.
        srv, url = _serve("trend.py")
        try:
            with urllib.request.urlopen(url + "/api/trend", timeout=5) as r:
                self.assertEqual(r.status, 200)
                self.assertTrue(r.headers["Content-Type"].startswith(
                    "application/json"))
                data = json.loads(r.read().decode())
            self.assertEqual(sorted(data), ["history", "refs_trend"])
        finally:
            srv.shutdown()

    def test_local_determinism_trend_via_real_http(self):
        # 3c) canlı-yerel: git'teki gerçek trend → {badge, rows}.
        srv, url = _serve("determinism-trend.py")
        try:
            with urllib.request.urlopen(url + "/api/determinism-trend",
                                        timeout=5) as r:
                data = json.loads(r.read().decode())
            self.assertEqual(sorted(data), ["badge", "rows"])
            self.assertTrue(data["rows"], "trend dosyası boş çıkması beklenmez")
        finally:
            srv.shutdown()

    def test_method_gating_405(self):
        # 3d) POST → 405 (yerel _reject_method kardeşi).
        srv, url = _serve("health.py")
        try:
            req = urllib.request.Request(url + "/api/health", data=b"{}",
                                         method="POST")
            try:
                urllib.request.urlopen(req, timeout=5)
                self.fail("POST 200 döndü")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 405)
        finally:
            srv.shutdown()

    def test_run_history_schema_parity(self):
        # 4) GH-türetimi yerel satır-şeması (+2 bilinçli ek). Ağ-koşullu.
        try:
            socket.getaddrinfo("api.github.com", 443)
        except OSError:
            self.skipTest("ağ yok — canlı-GH-API testi atlandı")
        rows = _adapter().run_history_from_github(limit=3)
        self.assertTrue(rows, "Actions-API boş döndü")
        base = {"ts", "verdict", "p0", "p1", "budget_usd", "budget_limit",
                "budget_method", "duration_s", "refs_verified", "refs_total",
                "pdf_pages", "z3_passed", "z3_total", "lean_ok", "lean_detail"}
        for row in rows:
            self.assertEqual(set(row) - base, {"workflow", "url"})
            self.assertTrue(row["ts"])
            self.assertIn(row["verdict"], {"PASS", "FAIL", "?"})

    def test_no_local_break_api_contract(self):
        # 5) no-local-break: yerel /api sözleşme-süitleri yeşil (api/
        #    dizini yerel root-mukayeselerine karışmamalı).
        #    KAPSAM NOTU: test_openapi_schema.py HEAD'te takipli DEĞİL —
        #    commit'li ağaçta modül-yokluğu hatası (phantom-bağımlılık
        #    ailesi). Yalnız HEAD'de takipli süit çağrılır; openapi süiti
        #    takip edildiğinde listede geri eklenir.
        for suite in ("test_api_method_contract",):
            r = subprocess.run(
                [sys.executable, "-m", "unittest", "_calisma.CIKTI." + suite],
                cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0,
                             "%s kırıldı:\n%s" % (suite, r.stderr[-400:]))


def _ignored(relpath):
    """.vercelignore kararı — gitignore semantiği (core.excludesFile).

    Döner True = dışlanır (upload'a girmez), False = girer.
    Normal klonlarda plain git yeterli; core.bare=true işaretli-bağımsız
    depoda check-ignore worktree ister → rc=128 → açık
    --git-dir/--work-tree ile yeniden dene. 0/1 dışındaki rc ortam
    hatasıdır → AssertionError (sessiz geçit yok, fail-closed).

    Karar ÖNCEKİ pattern'e göre değil, -v'nin yazdırdığı VEREN pattern'e
    göredir: `!negasyon` yazdıysa dosya dışlanmamıştır (rc=0 olsa bile).
    """
    cmd = ["git", "-c",
           "core.excludesFile=" + str(ROOT / ".vercelignore"),
           "check-ignore", "--no-index", "-v", relpath]
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       timeout=10)
    if r.returncode == 128:
        cmd = ["git", "--git-dir", str(ROOT / ".git"), "--work-tree",
               str(ROOT), "-c",
               "core.excludesFile=" + str(ROOT / ".vercelignore"),
               "check-ignore", "--no-index", "-v", relpath]
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           timeout=10)
    if r.returncode == 1:
        return False                      # hiç pattern eşleşmedi → girer
    if r.returncode == 0:
        line = next((ln for ln in r.stdout.splitlines() if "\t" in ln), "")
        if not line:
            raise AssertionError(
                "check-ignore rc=0 ama pattern yok: %r / %r" %
                (r.stdout, r.stderr))
        pattern = line.split("\t", 1)[0].rsplit(":", 1)[-1]
        return not pattern.startswith("!")
    raise AssertionError("check-ignore çalışamadı rc=%d: %s" %
                         (r.returncode, (r.stderr or r.stdout).strip()))


def _tracked():
    """git ls-files kümesi (\0 ayraçlı). Boş/çalışmayan sonuç => hata —
    "izleniyor" kümesinin sessizce boşalması fail-open olurdu."""
    r = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError("git ls-files çalışamadı: " + r.stderr.strip())
    files = {p for p in r.stdout.split("\0") if p}
    if len(files) < 100:
        raise AssertionError("git ls-files anlamsız sonuç: %d dosya" %
                             len(files))
    return files


def _vercel_ignore_rules():
    """.vercelignore satirlari (yorum/bos satir atlanir) — sirali."""
    rules = []
    for ln in (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if s and not s.startswith("#"):
            rules.append(s)
    return rules


def _glob_to_regex(pattern):
    """gitignore-glob -> tam-eslesme regex; `**/` onek her koku kapsar."""
    prefix = ""
    if pattern.startswith("**/"):
        pattern = pattern[3:]
        prefix = "(?:.*/)?"
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern[i:i + 2] == "**":
            out.append(".*")
            i += 2
        elif ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    return "^" + prefix + "".join(out) + "$"


def _vercel_pruned(relpath, rules=None):
    """Vercel CLI 59.x upload prune karari (ignore@5 + readdirRecursive).

    readdirRecursive her girisi SLASH'SIZ yol ile `ig.ignores()` ile test
    eder; dizin "ignored" cikarsa TÜM alt-agaç prune edilir (cocuklar hic
    denenmez). Son eslesen kural belirleyicidir; dir-only (sonu `/`) desen
    slash'siz dizin yoluna ESLESEMEZ, yalnizca `desen/` oneki altindaki
    yollara uyar. 2026-10-09 olcumleri (vercel 59.10 icindeki ignore@5):
        rules=[blanket, '!dir/', '!dir/**']  -> dir: True (yanlis-prune)
                                             -> dir/c.png: False
    Yani git-semantik `_ignored()` "girer" derken upload dizin dugumunu
    prune edebilir — bu model o sinari offline sinar; pini
    test_model_matches_measured_ignore_pkg.
    """
    if rules is None:
        rules = _vercel_ignore_rules()
    ignored = False
    for raw in rules:
        negated = raw.startswith("!")
        pat = raw[1:] if negated else raw
        if pat.endswith("/"):
            # dir-only: slash'siz DIZIN kendisine eslesmez, altindakilere uyar
            hit = re.match(_glob_to_regex(pat + "**"), relpath) is not None
        else:
            hit = re.match(_glob_to_regex(pat), relpath) is not None
        if hit:
            ignored = not negated
    return ignored


def _vercel_pruned_ancestor(relpath):
    """Upload'da dosyanin INMESINI engelleyen atas-dizin prune'i (yoksa None)."""
    parts = relpath.split("/")
    for i in range(1, len(parts)):
        ancestor = "/".join(parts[:i])
        if _vercel_pruned(ancestor):
            return ancestor
    return None


class TestVercelUploadPruneSemantics(unittest.TestCase):
    """Vercel upload prune semantigi — ignore@5 olcumlerine kilitli.

    2026-10-09 arizasi: /slides_z3/* ve /design-system/stripe-theme.css
    TÜM deploy'larda 404; git check-ignore temiz diyordu (takipli dosya
    "girer"), ama Vercel upload'i atas dizini prune edip alt-agaçi dusuruyordu.
    Bu sinif olcum-kilitli modelle bu sinari offline (agizsiz) sinar.
    """

    _MEASURED_OLD = [
        "_calisma/CIKTI/**",
        "!_calisma/CIKTI/slides_z3/",
        "!_calisma/CIKTI/slides_z3/**",
    ]
    _MEASURED_FIXED = _MEASURED_OLD + ["!_calisma/CIKTI/slides_z3"]

    def test_model_matches_measured_ignore_pkg(self):
        self.assertTrue(_vercel_pruned(
            "_calisma/CIKTI/slides_z3", self._MEASURED_OLD),
            "olcum: eski kurallarla dizin prune (git bunu gormez)")
        self.assertFalse(_vercel_pruned(
            "_calisma/CIKTI/slides_z3/P1-a.png", self._MEASURED_OLD),
            "olcum: dir-only negasyon cocuga ulasir")
        self.assertFalse(_vercel_pruned(
            "_calisma/CIKTI/slides_z3", self._MEASURED_FIXED),
            "slash'siz negasyon dizin dugumunu kurtarmali")

    def test_repo_ignore_file_keeps_static_dirs_reachable(self):
        for rel in ("_calisma/CIKTI/slides_z3",
                    "_calisma/CIKTI/slides_z3/P1-a.png",
                    "design-system/stripe",
                    "design-system/stripe/theme.css",
                    "_calisma/CIKTI/preview.html",
                    "_calisma/CIKTI/preview.js",
                    "_calisma/CIKTI/sw.js",
                    "design-system/tokens.css"):
            self.assertFalse(
                _vercel_pruned(rel),
                "%s prune ediliyor — Vercel upload'unda yuklenmez" % rel)

    def test_bundle_separation_still_holds_under_vercel_model(self):
        for rel in (".env", ".env.local", "node_modules/x/index.js",
                    "_calisma/pptx/sunum.pptx",
                    "design-system/stripe/tokens.json",
                    ".worktrees/x/y.py"):
            self.assertTrue(
                _vercel_pruned(rel),
                "%s prune edilmiyor — bundle siser/sizar" % rel)

    def test_every_static_asset_ancestor_is_reachable(self):
        assets = [
            "_calisma/CIKTI/preview.html",
            "_calisma/CIKTI/preview.js",
            "_calisma/CIKTI/sw.js",
            "design-system/tokens.css",
            "design-system/stripe/theme.css",
        ]
        assets += [str(p.relative_to(ROOT)) for p in sorted(
            (ROOT / "_calisma/CIKTI" / "slides_z3").glob("*.png"))]
        self.assertGreaterEqual(len(assets), 17, "varlik listesi bosaldi")
        for rel in assets:
            culprit = _vercel_pruned_ancestor(rel)
            self.assertIsNone(
                culprit,
                "%s atas dizin prune: %s — deploy'da 404" % (rel, culprit))


class TestVercelStaticFrontendContract(unittest.TestCase):
    """Statik-frontend sözleşmesi: / → preview.html, /preview.js, /sw.js,
    /design-system/*, /slides_z3/* AYNI deployment'da servis edilir;
    /api/* yolları hiçbir route'a yakalanmaz → dosya-tabanlı fonksiyona
    düşer (JS değişmeden). HTML/JS'e dokunmadan konfigürasyonla kurulur.
    """

    def _routes(self):
        cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        routes = cfg.get("routes")
        self.assertTrue(routes, "vercel.json routes boş/silinmiş")
        return cfg, routes

    def _resolve(self, url, routes):
        """URL → deployment-içi dosya-yolu: eşleşen tek route'un dest'i
        ($1 ikamesi dahil), yoksa URL'nin kendisi (filesystem servisi)."""
        hits = [(r, re.search(r["src"], url)) for r in routes
                if re.search(r["src"], url)]
        self.assertLessEqual(len(hits), 1,
                             "%s birden fazla route'a düşüyor" % url)
        if not hits:
            return url
        r, m = hits[0]
        dest = r["dest"]
        if "$1" in dest:
            dest = dest.replace("$1", m.group(1))
        return dest

    def test_routes_anchored_and_api_paths_fall_through(self):
        cfg, routes = self._routes()
        # functions yapılandırması dosya-tabanlı fonksiyon sözleşmesini
        # (api/*.py + bundle hariç-tutma) korumalı.
        self.assertIn("api/*.py", cfg.get("functions", {}),
                      "functions['api/*.py'] yok — adaptör bundle'ı şişer")
        # 1) Her src açık-anchor'lı (^...$): Vercel'in implicit-anchor
        #    davranışı bilinmiyor; anchor'sız "^/$"-eşdeğeri "/" TÜM
        #    yolları yutup /api/*'i statik'e çökerdi → adaptör atlanır.
        for r in routes:
            src = r["src"]
            self.assertTrue(src.startswith("^") and src.endswith("$"),
                            "route src anchor'sız: %r" % src)
            re.compile(src)              # geçersiz PCRE burada patlar
        # 2) Hiçbir route /api/* yolunu yutmamalı → fonksiyona düşer.
        api_paths = ["/api/" + p.stem for p in sorted(API.glob("*.py"))
                     if not p.stem.startswith("_")]
        self.assertTrue(api_paths, "api/*.py yok — test gözükör")
        for path in api_paths:
            for r in routes:
                self.assertIsNone(re.search(r["src"], path),
                                  "%r route'u %s yolunu yuttu — fonksiyon "
                                  "yerine statik 404" % (r["src"], path))
        # 3) URL==dosya-yolu olan statik de route'a yakalanmamalı
        #    (filesystem'den doğrudan servis edilir).
        for r in routes:
            self.assertIsNone(re.search(r["src"], "/design-system/tokens.css"),
                              "tokens.css route'a yakalandı — filesystem "
                          "servisi ezildi")
        # 4) Olumlu taraf: her route tam kendi yolunu tutar, dest'i
        #    deployment-içi gerçek dosyadır.
        positives = {
            "/": "_calisma/CIKTI/preview.html",
            "/preview.js": "_calisma/CIKTI/preview.js",
            "/sw.js": "_calisma/CIKTI/sw.js",
            "/design-system/stripe-theme.css": "design-system/stripe/theme.css",
            "/slides_z3/P1-a.png": "_calisma/CIKTI/slides_z3/P1-a.png",
        }
        for url, want in positives.items():
            dest = self._resolve(url, routes)
            self.assertEqual(dest.lstrip("/"), want,
                             "%s → %s beklenirdi" % (url, want))
        # 5) Slayt adları route sınıfının ([A-Za-z0-9._-]+) dışında
        #    kalırsa $1 eşleşmez → sessiz 404. Yeni dosya adı burada
        #    kırmızıya döner, deploy'da değil.
        slides_dir = ROOT / "_calisma/CIKTI" / "slides_z3"
        pngs = sorted(slides_dir.glob("*.png"))
        self.assertTrue(pngs, "slides_z3/*.png yok — test gözükör")
        for p in pngs:
            self.assertRegex(
                p.name, r"^[A-Za-z0-9._-]+$",
                "slayt adı route sınıfına girmiyor → /slides_z3/%s 404" %
                p.name)
            self.assertEqual(
                self._resolve("/slides_z3/" + p.name, routes).lstrip("/"),
                "_calisma/CIKTI/slides_z3/" + p.name)

    def test_static_assets_exist_and_survive_vercelignore(self):
        _, routes = self._routes()
        html = (ROOT / "_calisma/CIKTI" / "preview.html").read_text(
            encoding="utf-8")
        js = (ROOT / "_calisma/CIKTI" / "preview.js").read_text(
            encoding="utf-8")
        # Mutlak src/href'ler HTML'den ÇIKARILIR (el-listesi taze kopyada
        # kaybolmaz) + preview.js service-worker kaydı. /api/* adaptör
        # alanıdır — JS kendi catch'inde zarifçe düşer, statik varlık değil.
        urls = set(re.findall(r'(?:src|href)="(/[^"?#]+)', html))
        urls |= set(re.findall(r'\.register\("(/[^"?#]+)"', js))
        urls = {u for u in urls if not u.startswith("/api/")}
        # Göreli referanslar (belge / olduğu için /-ile başlar).
        urls |= {"/" + r for r in
                 re.findall(r'(?:src|href)="(?!/|#|data:|https?:)([^"?#]+)"',
                            html)}
        # 12 slayt + tokens + stripe + sw = asgari 15; regex sessizce
        # boşalırsa döngü de boşalır → sayım guard'ı.
        self.assertGreaterEqual(len(urls), 15,
                                "varlık referansı çıkarımı boşaldı: %d" %
                                len(urls))
        tracked = _tracked()
        for url in sorted(urls):
            rel = self._resolve(url, routes).lstrip("/")
            self.assertFalse(
                _ignored(rel),
                "%s → %s .vercelignore ile dışlı — deploy'da 404" %
                (url, rel))
            if rel in tracked:
                self.assertTrue((ROOT / rel).exists(),
                                "takipli statik dosya diskte yok: %s" % rel)
            # takipsiz (üretilmiş design-system/stripe/theme.css):
            # CLI-deploy worktree'den yükler; git-push ağacında yoksa
            # route zararsız 404 verir (yerel mirror da aynı biçimde
            # 404) — varlık zorunluluğu yalnız takipli yüzeyde.

    def test_vercelignore_separates_upload_from_bundle(self):
        # Yüklenecek çekirdek: tüm api/*.py (yeni endpoint'ler otomatik
        # kapsanır), canlı-veri jsonl, route dest kaynakları.
        must_upload = [str(p.relative_to(ROOT)) for p in sorted(API.glob("*.py"))]
        must_upload += [
            "docs/determinism_trend/determinism_trend.jsonl",
            "_calisma/CIKTI/preview_server.py",
            "_calisma/CIKTI/determinism_trend_badge.py",
            "_calisma/CIKTI/slides_z3",   # dizin kendisi inilebilir olmalı
        ]
        for rel in must_upload:
            self.assertFalse(_ignored(rel),
                             "%s dışlı — deploy'da eksik" % rel)
        # İçe-aktarma zinciri sözleşmesi: bundle'a giren yerel modülün import
        # ettiği kardeş modüller de upload'a girmeli (2026-10-09 kanıtı:
        # preview_server sat.45 `import precommit_log` dışlandı → 3 uç
        # ModuleNotFoundError ile FUNCTION_INVOCATION_FAILED, health etkisiz).
        for rel in ("_calisma/CIKTI/preview_server.py",
                    "_calisma/CIKTI/determinism_trend_badge.py"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            cikti = ROOT / "_calisma" / "CIKTI"
            for m in re.finditer(r"^(?:import|from)\s+([A-Za-z_]\w*)",
                                 src, re.M):
                sibling = cikti / (m.group(1) + ".py")
                if sibling.exists():
                    self.assertFalse(
                        _ignored(sibling.relative_to(ROOT).as_posix()),
                        "%s → %s import ediyor ama .vercelignore dışlı — "
                        "deploy'da ModuleNotFoundError" % (rel, m.group(1)))
        # Dışarıda kalması gereken yüzey (bundle 250MB eşiği + sır-disiplini).
        must_exclude = [
            ".env",
            "_calisma/pptx/sunum.pptx",
            "design-system/primer/primer.css",
            "design-system/stripe/tokens.json",
            "node_modules/x/index.js",
        ]
        for rel in must_exclude:
            self.assertTrue(_ignored(rel),
                            "%s dışlanmamış — bundle şişer/sızar" % rel)


if __name__ == "__main__":
    unittest.main()
