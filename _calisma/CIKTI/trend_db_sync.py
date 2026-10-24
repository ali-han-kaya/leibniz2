#!/usr/bin/env python3
"""trend_db_sync.py — history.jsonl → Neon `trend_runs` OTOMATİK senkronu.

Neden bu modül var: `apps/trend-db/scripts/load.ts` idempotent bir yükleyici
ama TETİKSİZDİ. README "Otomatik zamanlama yok: `npm run load` elle/periyodik
çağrılmalı" diyordu; daemon her yeni koşumu `history.jsonl`'e yazdığında
arşiv (kalıcı `trend_runs`) geride kalıyordu. Bu modül tetiği daemon'ın
kendisine bağlar:

  persist_history(yeni kayıt) → digest → debounce'lu tek arka plan thread'i
  → `load.ts <history>` → durum `$PREVIEW_DIR/trend_sync.json` + `/api/trend-sync`

Sözleşmeler (hepsi test edilebilir yüzeyler):

1. **Tek yazıcı:** yükleme tek bir worker thread'inde koşar; eşzamanlı istekler
   debounce penceresinde BİRLEŞİR (N append → 1 yükleme). `load.ts` zaten
   `ON CONFLICT DO NOTHING` (skipDuplicates) olduğu için mükerrer çağrı veri
   bozmaz, sadece boşa iş olur.
2. **Idempotans:** son BAŞARILI yüklemenin digest'i saklanır; dosya değişmediyse
   alt süreç hiç başlatılmaz ("up-to-date").
3. **Sessiz PASS yok:** atlama da bir sonuçtur ve `state="skipped"` + `reason`
   ile raporlanır (`loader-missing`, `node-missing`, `no-database-url`, …).
   Başarısızlık daemon'ı düşürmez ama `ok=false` olarak görünür kalır.
4. **TCC:** launchd GUI agent'ı repo dizinini okuyamaz. Yükleyici dizini sırayla
   `TREND_SYNC_DIR` → `<repo>/apps/trend-db` → `~/Library/Caches/com.freebuff/
   trend-db` (TCC-safe kopya, `--provision`) → `~/Desktop/leibniz2/apps/
   trend-db` (kabuk oturumu) aranır. Okunamayan aday sessizce atlanmaz;
   neden `reason` alanında döner.

Kullanım (elle/denetim):
  python3 trend_db_sync.py --once                 # bir kez senkronla
  python3 trend_db_sync.py --once --json          # tek satır makine raporu
  python3 trend_db_sync.py --status               # son durumu bas
  python3 trend_db_sync.py --watch                # sürekli izle (debounce'lu)
  python3 trend_db_sync.py --provision            # TCC-safe yükleyici kopyası
  python3 trend_db_sync.py --install-schedule     # launchd: WatchPaths + 15 dk
  python3 trend_db_sync.py --uninstall-schedule   # launchd agent'ını kaldır

ZAMANLANMIŞ ADIM (2026-10-18): daemon içi tetik yalnız daemon AYAKTAYKEN
çalışır. Yeniden başlatmadan önce yazılmış satırlar, bağlantı hatasıyla
düşmüş turlar ve `TREND_SYNC=0` (replay/snapshot) penceresinde büyüyen
history.jsonl arşivde geride kalırdı. `--install-schedule`, aynı `--once`
yolunu launchd'a bağlar:

  WatchPaths → history.jsonl BÜYÜDÜĞÜNDE koş
  StartInterval → append olmasa da 15 dk'da bir dene (düşen turu kurtarır)

İkisi de aynı digest kapısından geçtiği için boş tur yükleme başlatmaz;
`load.ts` ayrıca `ON CONFLICT DO NOTHING` (idempotent).
"""
import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

# Varsayılanlar. Debounce: daemon bir koşumu tek seferde yazar, ama yeniden
# denemeler/elle tetiklemeler kısa aralıkla gelebilir — 5 s pencere bunları
# tek yüklemeye indirir ve yükleme (~0.3-1 s) bitmeden yeni tur açmaz.
DEFAULT_DEBOUNCE_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 120.0
STATUS_FILE_NAME = "trend_sync.json"

ENV_ENABLE = "TREND_SYNC"           # "0" → kapalı; başka değer → açık
ENV_DIR = "TREND_SYNC_DIR"          # yükleyici dizini (apps/trend-db)
ENV_NODE = "TREND_SYNC_NODE"        # node ikilisi (launchd PATH'i kısıtlı)
ENV_DEBOUNCE = "TREND_SYNC_DEBOUNCE"
ENV_TIMEOUT = "TREND_SYNC_TIMEOUT"
ENV_LAUNCHCTL = "TREND_SYNC_LAUNCHCTL"   # launchctl ikilisi (test enjeksiyonu)

# ── Zamanlanmış senkron (launchd) sabitleri ─────────────────────────────────
SCHEDULE_LABEL = "com.freebuff.trend-db-sync"
SCHEDULE_PLIST_NAME = SCHEDULE_LABEL + ".plist"
SCHEDULE_INTERVAL_SECONDS = 900      # 15 dk emniyet kemeri (append yoksa da dene)
SCHEDULE_THROTTLE_SECONDS = 60       # append fırtınasını tek tura indir
_LOG_DIR = os.path.join(os.path.expanduser("~"), "Library", "Logs")
SCHEDULE_LOG = os.path.join(_LOG_DIR, SCHEDULE_LABEL + ".log")
SCHEDULE_ERR_LOG = os.path.join(_LOG_DIR, SCHEDULE_LABEL + ".err.log")
# launchd GUI agent'ı bu dizinleri okuyamaz (TCC): böyle bir yükleyiciyle
# kurulan zamanlama her turda `loader-unreadable` verirdi — sessiz no-op
# yerine kurulumu `loader-needs-provision` ile reddederiz.
_TCC_RISK_PREFIXES = ("~/Desktop", "~/Documents", "~/Downloads")
# TCC'li bir yerden kurulduğunda betiğin kendisi buraya kopyalanır
# (launchd python'u ~/Desktop'taki dosyayı açamaz).
STAGED_SCRIPT_DIR = os.path.join(
    os.path.expanduser("~"), "Library", "Caches", "com.freebuff", "trend-db-sync")

CACHE_LOADER_DIR = os.path.join(
    os.path.expanduser("~"), "Library", "Caches", "com.freebuff", "trend-db")
_DESKTOP_LOADER_DIR = os.path.join(
    os.path.expanduser("~"), "Desktop", "leibniz2", "apps", "trend-db")

# Yükleme çıktısındaki tek satırlık özet: "bitti: 100 kayıt işlendi
# (3 eklendi), 97 atlandı" — eklenen sayıyı buradan okuruz.
_INSERTED_RE = re.compile(r"\((\d+)\s+eklendi\)")

_STATE_IDLE = "idle"
_STATE_SYNCED = "synced"
_STATE_UP_TO_DATE = "up-to-date"
_STATE_SKIPPED = "skipped"
_STATE_FAILED = "failed"
_OK_STATES = frozenset({_STATE_SYNCED, _STATE_UP_TO_DATE})


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tail(text, limit=2000):
    """Alt süreç çıktısının son `limit` karakteri (durum dosyası şişmesin)."""
    if not text:
        return ""
    return text[-limit:]


def history_digest(path):
    """history.jsonl baytlarının SHA-256'sı; okunamazsa None.

    `persist_history` zaten yazdığı içeriğin digest'ini hesaplıyor ve API'ye
    veriyor; worker bu değeri kullanır. Dosyadan okuyan yol (CLI `--once`)
    aynı tanımı kullanır — iki taraf ayrışırsa "değişmedi" yanlış olurdu.
    """
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def read_env_file(loader_dir):
    """`<loader>/.env` içindeki anahtarları oku (DEĞERLER dışarı verilmez).

    Yalnız varlık kontrolü için: `load.ts` `dotenv/config` ile cwd'deki .env'i
    kendisi yükler. Burada değeri okumak/taşımak gereksiz — parola süreç
    ortamına bizim tarafımızdan konmaz.
    """
    env = {}
    path = os.path.join(loader_dir or "", ".env")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return {}
    return env


def has_database_url(loader_dir, env=None):
    """DATABASE_URL ya süreç ortamında ya yükleyicinin .env'inde olmalı.

    Yoksa yükleme kesin başarısız olur (`load.ts` çıkış 1). Alt süreci
    başlatıp kırmızı görmek yerine görünür bir `skipped` üretiyoruz.
    """
    env = os.environ if env is None else env
    if env.get("DATABASE_URL"):
        return True
    return bool(read_env_file(loader_dir).get("DATABASE_URL"))


def find_node(env=None):
    """node ikilisini bul: env override → PATH → bilinen konumlar.

    launchd oturumunda PATH minimaldir (`/usr/bin:/bin:...`) ve nvm/homebrew
    görünmez; bu yüzden mutlak adaylar taranır.
    """
    env = os.environ if env is None else env
    explicit = env.get(ENV_NODE)
    if explicit and os.access(explicit, os.X_OK):
        return explicit
    found = shutil.which("node", path=env.get("PATH"))
    if found:
        return found
    candidates = ["/opt/homebrew/bin/node", "/usr/local/bin/node"]
    nvm = os.path.join(os.path.expanduser("~"), ".nvm", "versions", "node")
    try:
        versions = sorted(os.listdir(nvm), reverse=True)
    except OSError:
        versions = []
    candidates += [os.path.join(nvm, v, "bin", "node") for v in versions]
    for cand in candidates:
        if os.access(cand, os.X_OK):
            return cand
    return None


def _loadable(loader_dir):
    """Yükleyici dizini gerçekten okunabiliyor mu? (TCC kapısı)

    `os.path.isfile` TCC engelini gizleyebilir; bu yüzden dosyayı AÇMAYI
    deneriz. Okunamayan aday, "var ama erişilemez" olarak raporlanır.
    """
    script = os.path.join(loader_dir, "scripts", "load.ts")
    try:
        with open(script, "rb"):
            return True
    except OSError:
        return False


def find_loader_dir(repo_root=None, env=None):
    """(dizin, neden) — bulunamazsa (None, reason).

    `reason` ayrımı önemli: "yükleyici yok" (provision edilmemiş) ile
    "var ama TCC engelliyor" farklı eylemler gerektirir.
    """
    env = os.environ if env is None else env
    candidates = []
    explicit = env.get(ENV_DIR)
    if explicit:
        candidates.append(("env", explicit))
    if repo_root:
        candidates.append(("repo", os.path.join(repo_root, "apps", "trend-db")))
    candidates.append(("cache", CACHE_LOADER_DIR))
    candidates.append(("desktop", _DESKTOP_LOADER_DIR))
    seen = set()
    blocked = None
    for _kind, cand in candidates:
        cand = os.path.abspath(os.path.expanduser(cand))
        if cand in seen:
            continue
        seen.add(cand)
        if not os.path.isdir(cand):
            continue
        if _loadable(cand):
            return cand, None
        blocked = cand
    if blocked:
        return None, "loader-unreadable"
    return None, "loader-missing"


def build_command(loader_dir, node, history_path):
    """Yükleme komutu; hiçbir çalıştırıcı yoksa None.

    npm yerine doğrudan `node_modules/.bin/tsx` tercih edilir: npm bir katman
    daha süreç/latency ekliyor ve `--silent` olsa bile stdout'a kendi
    mesajlarını karıştırabiliyor (ölçüldü: 0.63 s tsx / 0.33 s npm — ikisi de
    kabul edilebilir, ama ayrıştırdığımız tek satır `load.ts`'in olsun).
    """
    tsx = os.path.join(loader_dir, "node_modules", ".bin", "tsx")
    script = os.path.join(loader_dir, "scripts", "load.ts")
    if os.path.exists(tsx) and node:
        return [node, os.path.realpath(tsx), script, history_path]
    if os.path.exists(tsx):
        # node bulunamadı ama betik çalıştırılabilir: deneyelim (shebang
        # /usr/bin/env node ise zaten PATH'e ihtiyaç var — hata görünür kalır).
        return [tsx, script, history_path]
    npm = shutil.which("npm")
    if npm and node:
        return [npm, "run", "load", "--silent", "--", history_path]
    return None


def parse_inserted(stdout):
    """`(N eklendi)` sayısını oku; desen yoksa None (uydurma yok)."""
    matches = _INSERTED_RE.findall(stdout or "")
    if not matches:
        return None
    return int(matches[-1])


def _subprocess_env(loader_dir, env=None, node=None):
    env = dict(os.environ if env is None else env)
    # .env sırrı alt sürece bizim tarafımızdan taşınmaz; dotenv cwd'den okur.
    if node:
        node_dir = os.path.dirname(node)
        path = env.get("PATH", "")
        if node_dir not in path.split(os.pathsep):
            env["PATH"] = node_dir + (os.pathsep + path if path else "")
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def run_sync(history_path, loader_dir=None, node=None,
             timeout=DEFAULT_TIMEOUT_SECONDS, repo_root=None, env=None):
    """Tek senkron turu. ASLA istisna fırlatmaz; sonucu durum sözlüğü döndürür.

    Durum alanları: state, ok, ts, history, history_sha256, loader_dir,
    inserted, duration_ms, reason, stdout_tail, stderr_tail.
    """
    started = time.monotonic()
    env = os.environ if env is None else env
    result = {
        "state": _STATE_FAILED,
        "ok": False,
        "ts": _now_iso(),
        "history": history_path,
        "history_sha256": None,
        "loader_dir": loader_dir,
        "inserted": None,
        "duration_ms": None,
        "reason": None,
        "stdout_tail": "",
        "stderr_tail": "",
    }

    def done():
        result["duration_ms"] = int((time.monotonic() - started) * 1000)
        return result

    if not history_path or not os.path.isfile(history_path):
        result.update(state=_STATE_SKIPPED, reason="history-missing")
        return done()
    digest = history_digest(history_path)
    if digest is None:
        result.update(state=_STATE_SKIPPED, reason="history-unreadable")
        return done()
    result["history_sha256"] = digest

    if not loader_dir:
        loader_dir, reason = find_loader_dir(repo_root=repo_root, env=env)
        result["loader_dir"] = loader_dir
        if not loader_dir:
            result.update(state=_STATE_SKIPPED, reason=reason)
            return done()

    if not has_database_url(loader_dir, env):
        result.update(state=_STATE_SKIPPED, reason="no-database-url")
        return done()

    node = node or find_node(env)
    cmd = build_command(loader_dir, node, history_path)
    if not cmd:
        result.update(state=_STATE_SKIPPED, reason="runner-missing")
        return done()

    try:
        proc = subprocess.run(
            cmd,
            cwd=loader_dir,
            env=_subprocess_env(loader_dir, env, node),
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout)),
        )
    except subprocess.TimeoutExpired as exc:
        result.update(state=_STATE_FAILED, reason="timeout",
                      stdout_tail=_tail(_maybe_text(exc.stdout)),
                      stderr_tail=_tail(_maybe_text(exc.stderr)))
        return done()
    except OSError as exc:
        result.update(state=_STATE_FAILED, reason="spawn-error",
                      stderr_tail=str(exc))
        return done()

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    inserted = parse_inserted(stdout)
    result.update(stdout_tail=_tail(stdout), stderr_tail=_tail(stderr),
                  inserted=inserted)
    if proc.returncode != 0:
        # Kısa neden: orchestrator'ın ilk bakacağı şey (no-database-url,
        # bağlantı reddi, tsx hatası) stderr'in ilk satırıdır.
        first = next((ln.strip() for ln in stderr.splitlines() if ln.strip()), "")
        result.update(state=_STATE_FAILED,
                      reason="exit-%d" % proc.returncode)
        if first:
            result["reason"] = "exit-%d: %s" % (proc.returncode, first[:200])
        return done()

    if inserted is None:
        # Yükleme koştu ama özet satırı ayrıştırılamadı: başarı iddia etmek
        # yerine uyarı bırak (veri yazılmış olabilir; sessiz "0" uydurmayız).
        result.update(state=_STATE_SYNCED, ok=True, reason="unparsed-output")
        return done()
    if inserted == 0:
        result.update(state=_STATE_UP_TO_DATE, ok=True)
        return done()
    result.update(state=_STATE_SYNCED, ok=True)
    return done()


def _maybe_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def write_status(path, status):
    """Durum dosyasını atomik yaz (tmp + os.replace). Hata yutulur: telemetri
    yazımı daemon'ı düşürmemeli — ama durum bellekte kalır ve rota okur."""
    if not path:
        return False
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = "%s.tmp.%d" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def read_status(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


class HistorySync:
    """Debounce'lu, tek-thread'li history → DB senkron işçisi.

    `request()` asla bloklamaz ve istisna fırlatmaz — `persist_history` LOCK
    altındayken çağrılır. İş yalnız arka plan thread'inde yapılır.
    """

    def __init__(self, history_path, preview_dir=None, loader_dir=None,
                 debounce=DEFAULT_DEBOUNCE_SECONDS,
                 timeout=DEFAULT_TIMEOUT_SECONDS,
                 runner=run_sync, repo_root=None, env=None, enabled=True):
        self.history_path = history_path
        self.preview_dir = preview_dir
        self.loader_dir = loader_dir
        self.debounce = max(0.0, float(debounce))
        self.timeout = float(timeout)
        self.repo_root = repo_root
        self.env = env
        self.enabled = bool(enabled)
        self.status_path = (os.path.join(preview_dir, STATUS_FILE_NAME)
                            if preview_dir else None)
        self._runner = runner
        self._cond = threading.Condition()
        self._thread = None
        self._stopped = False
        self._wanted = None          # yüklenecek digest
        self._notify_seq = 0
        # Yeniden başlatmada gereksiz yükleme olmasın: son BAŞARILI digest
        # diskteki durum dosyasından devralınır.
        persisted = read_status(self.status_path) or {}
        self._last_synced = persisted.get("last_synced_sha256")
        # Denenen son digest: aynı içerik için başarısız/atlanmış turu
        # sonsuz döngüde TEKRARLAMAMAK için (watch modu her saniye sorar;
        # kalıcı bağlantı hatasında her debounce'ta bir alt süreç açmak
        # istenmez). Yeni digest → yeniden dener. Kasten SÜREÇ-YEREL:
        # yeniden başlatma, kalıcı bir hatayı bir kez yeniden dener.
        self._last_attempt = None
        self._last_success_ts = persisted.get("last_success_ts")
        self._runs = int(persisted.get("runs") or 0)
        self._status = persisted if persisted else {
            "state": _STATE_IDLE if self.enabled else "disabled",
            "ok": False,
            "ts": None,
            "history": history_path,
            "loader_dir": loader_dir,
            "last_synced_sha256": None,
            "last_success_ts": None,
            "runs": 0,
        }
        if not self.enabled:
            self._status = dict(self._status, state="disabled", ok=False)

    # ── dış yüzey ──────────────────────────────────────────────────────────
    def request(self, digest=None):
        """Yeni bir digest bildir; kısa süre içinde tek yükleme tetikler."""
        if not self.enabled:
            return False
        if digest is None:
            digest = history_digest(self.history_path)
        if not digest:
            return False
        with self._cond:
            if digest == self._last_synced and self._status.get("ok"):
                return False
            if digest == self._last_attempt and not self._status.get("ok"):
                # Aynı içerik zaten denendi ve başarısız/atlandı: tekrar
                # denemek durumu değiştirmez, yükü boşa çoğaltır.
                return False
            self._wanted = digest
            self._notify_seq += 1
            self._cond.notify_all()
            return True

    def start(self):
        if not self.enabled or self._thread is not None:
            return False
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="trend-db-sync")
        self._thread.start()
        return True

    def stop(self, timeout=2.0):
        with self._cond:
            self._stopped = True
            self._cond.notify_all()
        t = self._thread
        if t is not None:
            t.join(timeout=timeout)
        return t is None or not t.is_alive()

    def status(self):
        with self._cond:
            return dict(self._status)

    # ── işçi ──────────────────────────────────────────────────────────────
    def _loop(self):
        while True:
            with self._cond:
                while not self._stopped and self._wanted is None:
                    self._cond.wait()
                if self._stopped:
                    return
                # Debounce: pencere İÇİNDE gelen her istek süreyi sıfırlar →
                # seri append'ler tek yüklemeye birleşir.
                deadline = time.monotonic() + self.debounce
                seq = self._notify_seq
                while not self._stopped:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._cond.wait(remaining)
                    if self._notify_seq != seq:
                        seq = self._notify_seq
                        deadline = time.monotonic() + self.debounce
                if self._stopped:
                    return
                digest = self._wanted
                self._wanted = None
            if digest == self._last_synced and self._status.get("ok"):
                continue
            self._run_once(digest)

    def _run_once(self, digest):
        self._last_attempt = digest
        result = self._runner(
            history_path=self.history_path,
            loader_dir=self.loader_dir,
            timeout=self.timeout,
            repo_root=self.repo_root,
            env=self.env,
        )
        if not isinstance(result, dict):
            result = {"state": _STATE_FAILED, "ok": False,
                      "reason": "runner-contract"}
        self._runs += 1
        status = dict(result)
        status["runs"] = self._runs
        status["last_synced_sha256"] = self._last_synced
        status["last_attempt_sha256"] = self._last_attempt
        status["last_success_ts"] = self._last_success_ts
        if status.get("ok") and digest:
            self._last_synced = digest
            self._last_success_ts = status.get("ts")
            status["last_synced_sha256"] = digest
            status["last_success_ts"] = self._last_success_ts
        elif status.get("ok"):
            # digest bilinmiyordu (CLI/elle): dosyanın şu anki halini mühürle.
            current = history_digest(self.history_path)
            if current:
                self._last_synced = current
                status["last_synced_sha256"] = current
                self._last_success_ts = status.get("ts")
                status["last_success_ts"] = self._last_success_ts
        with self._cond:
            self._status = status
        write_status(self.status_path, status)


# ── TCC-safe yükleyici kopyası ───────────────────────────────────────────────

def _is_under(path, parent):
    path = os.path.realpath(os.path.abspath(path))
    parent = os.path.realpath(os.path.abspath(parent))
    return path == parent or path.startswith(parent + os.sep)


def provision_loader(src_dir, dst_dir=CACHE_LOADER_DIR, allow_outside=False):
    """Yükleyici projesini TCC-safe kopyaya çoğalt.

    launchd GUI agent'ı `~/Desktop`ı okuyamadığı için daemon'un gerçekten
    yükleme yapabilmesi bunu gerektirir. Hedef VARSAYILAN olarak yalnız
    `~/Library/Caches/com.freebuff/` altında olabilir — rastgele bir yola
    `--delete`/kopyalama yapılmasın (fail-closed).
    """
    src_dir = os.path.abspath(os.path.expanduser(src_dir))
    dst_dir = os.path.abspath(os.path.expanduser(dst_dir))
    result = {"ok": False, "src": src_dir, "dst": dst_dir, "method": None,
              "reason": None}
    if not os.path.isfile(os.path.join(src_dir, "scripts", "load.ts")):
        result["reason"] = "source-not-loader"
        return result
    cache_root = os.path.join(os.path.expanduser("~"), "Library", "Caches")
    if not allow_outside and not _is_under(dst_dir, cache_root):
        result["reason"] = "destination-outside-cache"
        return result
    if _is_under(dst_dir, src_dir) or _is_under(src_dir, dst_dir):
        result["reason"] = "overlapping-paths"
        return result
    try:
        os.makedirs(dst_dir, exist_ok=True)
        rsync = shutil.which("rsync")
        if rsync:
            proc = subprocess.run(
                [rsync, "-a", "--delete", src_dir + "/", dst_dir + "/"],
                capture_output=True, text=True, timeout=300)
            if proc.returncode != 0:
                result["reason"] = "rsync-failed: " + _tail(proc.stderr, 400)
                return result
            result["method"] = "rsync"
        else:
            # rsync yok: node_modules dahil tam kopya (hedef zaten cache).
            for name in os.listdir(src_dir):
                s, d = os.path.join(src_dir, name), os.path.join(dst_dir, name)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
            result["method"] = "copytree"
        # .env TCC-safe kopyada yaşayacaksa yalnız sahibi okuyabilsin.
        env_path = os.path.join(dst_dir, ".env")
        if os.path.isfile(env_path):
            try:
                os.chmod(env_path, 0o600)
            except OSError:
                pass
    except (OSError, subprocess.SubprocessError) as exc:
        result["reason"] = "copy-failed: %s" % exc
        return result
    result["ok"] = _loadable(dst_dir)
    if not result["ok"]:
        result["reason"] = "destination-unreadable"
    return result


# ── Zamanlanmış senkron (launchd agent) ────────────────────────────────────

def default_launch_agents_dir():
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")


def schedule_plist_path(agents_dir=None):
    return os.path.join(agents_dir or default_launch_agents_dir(),
                        SCHEDULE_PLIST_NAME)


def _tcc_risk(path):
    """launchd GUI agent'ının okuyamayacağı (TCC korumalı) bir yol mu?"""
    real = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    for prefix in _TCC_RISK_PREFIXES:
        root = os.path.realpath(os.path.expanduser(prefix))
        if real == root or real.startswith(root + os.sep):
            return True
    return False


def build_schedule_plist(history_path, loader_dir, *, script=None,
                         log_path=SCHEDULE_LOG, err_log_path=SCHEDULE_ERR_LOG,
                         interval=SCHEDULE_INTERVAL_SECONDS,
                         throttle=SCHEDULE_THROTTLE_SECONDS):
    """launchd agent tanımı — TEK kaynak: dosya da test de buradan geçer.

    `--dir` açıkça yazılır: launchd'ın keşfi (repo → cache → Desktop) minimal
    PATH'te TCC'ye takılan bir adaya düşüp doğru kopyayı gölgelemesin.
    `interval=0` → `StartInterval` hiç yazılmaz (yalnız WatchPaths tetiği).
    """
    script = os.path.abspath(script or __file__)
    history_path = os.path.abspath(os.path.expanduser(history_path))
    loader_dir = os.path.abspath(os.path.expanduser(loader_dir))
    data = {
        "Label": SCHEDULE_LABEL,
        "ProgramArguments": [sys.executable, script, "--once", "--json",
                             "--history", history_path, "--dir", loader_dir],
        # Oturum açılışında bir tur: daemon kapalıyken büyüyen dosya
        # ilk fırsatta yakalanır.
        "RunAtLoad": True,
        # ASIL tetik: history.jsonl değiştiğinde (append) koş.
        "WatchPaths": [history_path],
        "ThrottleInterval": int(throttle),
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": log_path,
        "StandardErrorPath": err_log_path,
    }
    if int(interval) > 0:
        data["StartInterval"] = int(interval)
    return data


def render_schedule_plist(history_path, loader_dir, **kwargs):
    """`build_schedule_plist` çıktısının XML baytları (plistlib tek yol)."""
    return plistlib.dumps(build_schedule_plist(history_path, loader_dir, **kwargs),
                          fmt=plistlib.FMT_XML, sort_keys=False)


def _launchctl_binary(env=None):
    env = os.environ if env is None else env
    return env.get(ENV_LAUNCHCTL) or "launchctl"


def _run_launchctl(args, env=None, timeout=30):
    """launchctl çağrısı → (rc, stdout+stderr). İkili yoksa rc=127."""
    binary = _launchctl_binary(env)
    if not shutil.which(binary) and not os.path.exists(binary):
        return 127, "launchctl bulunamadı: %s" % binary
    try:
        proc = subprocess.run([binary] + list(args), capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _launchd_target():
    """GUI oturum hedefi (`gui/<uid>`) — agent'ın bağlanacağı alan."""
    return "gui/%d" % os.getuid()


def stage_script(script, dst_dir=None):
    """Modülü launchd'ın okuyabildiği cache'e kopyala (TCC-safe çalıştırma).

    launchd GUI agent'ı `~/Desktop`ı okuyamaz: plist doğrudan repo'daki
    betiği gösterseydi iş hiç başlamazdı (python dosyayı açamaz). Kopya
    atomik yazılır; içerik aynıysa yeniden yazılmaz (`changed=False`).
    """
    src = os.path.abspath(os.path.expanduser(script))
    result = {"ok": False, "src": src, "dst": None, "changed": False,
              "reason": None}
    try:
        with open(src, "rb") as f:
            data = f.read()
    except OSError as exc:
        result["reason"] = "source-unreadable: %s" % exc
        return result
    dst = os.path.join(os.path.abspath(os.path.expanduser(dst_dir or
                                                          STAGED_SCRIPT_DIR)),
                       os.path.basename(src))
    result["dst"] = dst
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        same = False
        if os.path.exists(dst):
            with open(dst, "rb") as f:
                same = f.read() == data
        if not same:
            tmp = dst + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.chmod(tmp, 0o644)
            os.replace(tmp, dst)
        result.update(ok=True, changed=not same)
    except OSError as exc:
        result["reason"] = "stage-failed: %s" % exc
    return result


def install_schedule(history_path, loader_dir=None, agents_dir=None, *,
                     interval=SCHEDULE_INTERVAL_SECONDS,
                     throttle=SCHEDULE_THROTTLE_SECONDS, load=True,
                     env=None, script=None, log_path=SCHEDULE_LOG,
                     err_log_path=SCHEDULE_ERR_LOG, staged_dir=None):
    """launchd agent'ını kur. SONUÇ SÖZLÜĞÜ döner; istisna fırlatmaz.

    Fail-closed noktalar (hepsi `reason` ile görünür kalır):
      - yükleyici yok           → `loader-missing` / `loader-unreadable`
      - yükleyici TCC'de         → `loader-needs-provision` (plist YAZILMAZ)
      - plist başkasının/bozuk   → `plist-foreign` / `plist-unreadable`
      - bootstrap başarısız      → `bootstrap-failed` (plist DİSKTE kalır)
      - yükleme sonrası görünmüyor → `not-loaded`
    """
    env = os.environ if env is None else env
    history_path = os.path.abspath(os.path.expanduser(history_path))
    result = {
        "ok": False,
        "label": SCHEDULE_LABEL,
        "plist": schedule_plist_path(agents_dir),
        "history": history_path,
        "loader_dir": loader_dir,
        "interval": int(interval),
        "throttle": int(throttle),
        "watch": [history_path],
        "script": None,
        "script_staged": False,
        "installed": False,
        "changed": False,
        "loaded": False,
        "reason": None,
        "warnings": [],
        "launchctl": [],
    }

    explicit_loader = loader_dir is not None
    if not loader_dir:
        loader_dir, reason = find_loader_dir(env=env)
        if not loader_dir:
            result["reason"] = reason or "loader-missing"
            return result
    loader_dir = os.path.abspath(os.path.expanduser(loader_dir))
    if _tcc_risk(loader_dir):
        # Keşif repo'yu (~/Desktop) ilk sırada bulur; launchd için kullanışsız.
        # Cache kopyası zaten varsa SESSİZ no-op kurmak yerine ona geç.
        fallback = os.path.abspath(os.path.expanduser(CACHE_LOADER_DIR))
        if not explicit_loader and fallback != loader_dir and _loadable(fallback):
            result["warnings"].append(
                "%s TCC korumalı — cache kopyası kullanılıyor: %s"
                % (loader_dir, fallback))
            result["loader_source"] = loader_dir
            loader_dir = fallback
        else:
            result["reason"] = "loader-needs-provision"
            result["warnings"].append(
                "%s launchd GUI agent'ı için TCC korumalı — `--provision` ile "
                "cache kopyasına geç, sonra kur" % loader_dir)
            return result
    result["loader_dir"] = loader_dir
    if not os.path.isfile(history_path):
        # WatchPaths dosya oluşunca tetikler; StartInterval yine dener.
        result["warnings"].append("history-missing: %s" % history_path)

    # Betiğin KENDİSİ de TCC'li olabilir (repo ~/Desktop altında): o zaman
    # launchd python'u dosyayı açamaz ve iş sessizce hiç başlamaz.
    script_path = os.path.abspath(os.path.expanduser(script or __file__))
    if _tcc_risk(script_path):
        staged = stage_script(script_path, staged_dir)
        result["script_source"] = script_path
        if not staged["ok"]:
            result["reason"] = "script-staging-failed"
            result["warnings"].append(staged.get("reason") or "")
            return result
        script_path = staged["dst"]
        result["script_staged"] = True
    result["script"] = script_path

    payload = render_schedule_plist(history_path, loader_dir,
                                    script=script_path, log_path=log_path,
                                    err_log_path=err_log_path,
                                    interval=interval, throttle=throttle)
    path = result["plist"]

    # Yabancı ya da ayrıştırılamayan plist'in üzerine YAZMA (fail-closed):
    # aynı etiketi taşımayan bir dosyayı ezmek başka bir aracın kurulumunu
    # sessizce bozardı.
    previous = None
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                previous = plistlib.load(f)
        except (OSError, ValueError) as exc:
            # InvalidFileException ValueError'ın alt sınıfı: bozuk plist de
            # buraya düşer (`plist-unreadable`) — üzerine yazılmaz.
            result["reason"] = "plist-unreadable: %s" % exc
            return result
        if not isinstance(previous, dict) or previous.get("Label") != SCHEDULE_LABEL:
            result["reason"] = "plist-foreign"
            return result

    target = "%s/%s" % (_launchd_target(), SCHEDULE_LABEL)
    if load:
        # Yüklüyse önce indir: bootstrap "already bootstrapped" ile düşerdi
        # ve dosya değişmişse launchd ESKİ tanımı çalıştırmaya devam ederdi.
        rc_print, _ = _run_launchctl(["print", target], env)
        if rc_print == 0:
            rc_out, out = _run_launchctl(["bootout", target], env)
            result["launchctl"].append(
                {"args": ["bootout", target], "rc": rc_out,
                 "output": _tail(out, 400)})

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        already_same = False
        if previous is not None:
            try:
                already_same = plistlib.dumps(previous, fmt=plistlib.FMT_XML,
                                              sort_keys=False) == payload
            except (TypeError, ValueError):
                already_same = False
        if not already_same:
            with open(path, "wb") as f:
                f.write(payload)
            os.chmod(path, 0o644)
        result["changed"] = not already_same
        result["installed"] = True
    except OSError as exc:
        result["reason"] = "write-failed: %s" % exc
        return result

    if not load:
        result.update(ok=True, loaded=False)
        return result

    rc, out = _run_launchctl(["bootstrap", _launchd_target(), path], env)
    result["launchctl"].append(
        {"args": ["bootstrap", _launchd_target(), path], "rc": rc,
         "output": _tail(out, 400)})
    if rc == 127:
        # İkili yok: "bootstrap başarısız" demek yanlış eylem önerirdi.
        result["reason"] = "launchctl-missing"
        return result
    if rc != 0:
        result["reason"] = "bootstrap-failed"
        return result

    rc, out = _run_launchctl(["print", target], env)
    result["launchctl"].append(
        {"args": ["print", target], "rc": rc, "output": _tail(out, 400)})
    result["loaded"] = rc == 0
    if not result["loaded"]:
        result["reason"] = "not-loaded"
        return result
    result["ok"] = True
    return result


def uninstall_schedule(agents_dir=None, env=None):
    """Agent'ı indir + plist'i sil. Plist yoksa da `ok` (idempotent)."""
    env = os.environ if env is None else env
    path = schedule_plist_path(agents_dir)
    result = {"ok": True, "label": SCHEDULE_LABEL, "plist": path,
              "present_before": os.path.exists(path), "removed": False,
              "booted_out": False, "reason": None, "launchctl": []}
    target = "%s/%s" % (_launchd_target(), SCHEDULE_LABEL)
    rc, out = _run_launchctl(["bootout", target], env)
    result["booted_out"] = rc == 0
    result["launchctl"].append(
        {"args": ["bootout", target], "rc": rc, "output": _tail(out, 400)})
    try:
        os.remove(path)
        result["removed"] = True
    except FileNotFoundError:
        pass
    except OSError as exc:
        result["ok"] = False
        result["reason"] = "remove-failed: %s" % exc
    return result


def _print_schedule(result, json_mode):
    if json_mode:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return
    if "removed" in result:
        print("kaldırma   : %s (%s)" % ("ok" if result["ok"] else "HATA",
                                        result["plist"]))
        print("bootout    : %s" % ("ok" if result["booted_out"] else "yüklü değildi"))
        print("plist      : %s" % ("silindi" if result["removed"] else "yoktu"))
        if result.get("reason"):
            print("neden      : %s" % result["reason"])
        return
    print("zamanlama  : %s (%s)" % ("ok" if result["ok"] else "HATA",
                                    result["plist"]))
    print("etiketi    : %s" % result["label"])
    print("izlenen    : %s" % ", ".join(result.get("watch") or []))
    print("aralık     : %s s" % result.get("interval"))
    print("yükleyici  : %s" % result.get("loader_dir"))
    print("yüklü      : %s" % ("evet" if result.get("loaded") else "hayır"))
    if result.get("changed"):
        print("plist      : yazıldı")
    for warning in result.get("warnings") or []:
        print("uyarı      : %s" % warning)
    if result.get("reason"):
        print("neden      : %s" % result["reason"])


# ── CLI ─────────────────────────────────────────────────────────────────────

def _default_history():
    return os.path.join(os.path.expanduser("~"), "Library", "Caches",
                        "com.freebuff", "preview", "history.jsonl")


def _print_status(status, json_mode):
    if json_mode:
        print(json.dumps(status, ensure_ascii=False, sort_keys=True))
        return
    print("durum      : %s (%s)" % (status.get("state"),
                                    "ok" if status.get("ok") else "ok-değil"))
    for key in ("reason", "history", "history_sha256", "loader_dir",
                "inserted", "duration_ms", "last_synced_sha256"):
        if status.get(key) is not None:
            print("%-11s: %s" % (key, status[key]))
    if status.get("stderr_tail"):
        print("stderr     : %s" % _tail(status["stderr_tail"], 600))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="history.jsonl → Neon trend_runs otomatik senkronu")
    ap.add_argument("--history", default=_default_history(),
                    help="kaynak JSONL (varsayılan: TCC-mirror history.jsonl)")
    ap.add_argument("--dir", dest="loader_dir", default=None,
                    help="yükleyici dizini (apps/trend-db); verilmezse aranır")
    ap.add_argument("--once", action="store_true", help="tek senkron turu")
    ap.add_argument("--watch", action="store_true", help="sürekli izle")
    ap.add_argument("--status", action="store_true", help="son durumu bas")
    ap.add_argument("--status-file", default=None,
                    help="durum JSON yolu (varsayılan: <history dizini>/trend_sync.json)")
    ap.add_argument("--provision", action="store_true",
                    help="yükleyiciyi TCC-safe cache kopyasına çoğalt")
    ap.add_argument("--provision-src", default=None,
                    help="--provision kaynağı (varsayılan: bu repo'nun apps/trend-db)")
    ap.add_argument("--debounce", type=float, default=None)
    ap.add_argument("--timeout", type=float, default=None)
    ap.add_argument("--install-schedule", action="store_true",
                    help="launchd agent'ı kur (WatchPaths + StartInterval)")
    ap.add_argument("--uninstall-schedule", action="store_true",
                    help="launchd agent'ını indir ve plist'i sil")
    ap.add_argument("--launch-agents-dir", default=None,
                    help="LaunchAgents dizini (varsayılan: ~/Library/LaunchAgents)")
    ap.add_argument("--schedule-interval", type=int,
                    default=SCHEDULE_INTERVAL_SECONDS,
                    help="StartInterval saniye; 0 → yalnız WatchPaths")
    ap.add_argument("--schedule-throttle", type=int,
                    default=SCHEDULE_THROTTLE_SECONDS,
                    help="ThrottleInterval saniye (append fırtınası)")
    ap.add_argument("--schedule-no-load", action="store_true",
                    help="plist'i yaz ama launchctl bootstrap etme")
    ap.add_argument("--json", action="store_true", help="tek satır JSON")
    args = ap.parse_args(argv)

    env = os.environ
    status_path = args.status_file or os.path.join(
        os.path.dirname(os.path.abspath(args.history)), STATUS_FILE_NAME)

    if args.install_schedule or args.uninstall_schedule:
        if args.install_schedule and args.uninstall_schedule:
            print("kur ve kaldır aynı çağrıda olamaz", file=sys.stderr)
            return 2
        if args.uninstall_schedule:
            result = uninstall_schedule(args.launch_agents_dir, env=env)
        else:
            result = install_schedule(
                args.history, loader_dir=args.loader_dir,
                agents_dir=args.launch_agents_dir,
                interval=args.schedule_interval,
                throttle=args.schedule_throttle,
                load=not args.schedule_no_load, env=env)
        _print_schedule(result, args.json)
        return 0 if result.get("ok") else 1

    if args.provision:
        src = args.provision_src or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "apps", "trend-db")
        result = provision_loader(src)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        else:
            print("provision  : %s (%s → %s)" % (
                "ok" if result["ok"] else "HATA", result["src"], result["dst"]))
            if result.get("reason"):
                print("neden      : %s" % result["reason"])
            if result["ok"]:
                print("not        : daemon bu kopyayı TREND_SYNC_DIR olmadan da bulur")
        return 0 if result["ok"] else 1

    if args.status:
        status = read_status(status_path) or {
            "state": _STATE_IDLE, "ok": False, "reason": "no-status-yet"}
        _print_status(status, args.json)
        return 0

    debounce = args.debounce if args.debounce is not None else float(
        env.get(ENV_DEBOUNCE) or DEFAULT_DEBOUNCE_SECONDS)
    timeout = args.timeout if args.timeout is not None else float(
        env.get(ENV_TIMEOUT) or DEFAULT_TIMEOUT_SECONDS)
    preview_dir = os.path.dirname(os.path.abspath(args.history))

    if args.watch:
        sync = HistorySync(args.history, preview_dir=preview_dir,
                           loader_dir=args.loader_dir, debounce=debounce,
                           timeout=timeout, env=env)
        sync.start()
        sync.request()
        print("izleniyor : %s (debounce %.1fs, durum %s)" % (
            args.history, debounce, status_path), file=sys.stderr)
        try:
            while True:
                time.sleep(1.0)
                # append-only dosyada mtime/digest değişimi yeterli tetik.
                digest = history_digest(args.history)
                if digest and digest != sync.status().get("last_synced_sha256"):
                    sync.request(digest)
        except KeyboardInterrupt:
            sync.stop()
        return 0

    status = run_sync(args.history, loader_dir=args.loader_dir,
                      timeout=timeout, env=env)
    # Worker ile aynı sözleşme: başarılı tur digest'i mühürler, böylece
    # `--status` ve yeniden başlatma "ne yüklendi?" sorusunu yanıtlar.
    if status.get("ok") and status.get("history_sha256"):
        status["last_synced_sha256"] = status["history_sha256"]
        status["last_success_ts"] = status.get("ts")
    write_status(status_path, status)
    _print_status(status, args.json)
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
