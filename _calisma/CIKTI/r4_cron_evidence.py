#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r4_cron_evidence.py — haftalık docker-security cron'unun İLK `schedule`
koşumunu ölçer ve R4 denetim satırına kanıt olarak yazar.

Tarihsel kök-neden (bu oturum): R4 satırı "cron PR #52 merge'i ile
tetiklenebilir hâle geldi, ancak henüz ateşlenmedi; ilk ateşleme
2026-10-05T03:43Z" diyordu. Kanıt ancak ELLE `gh run list` ölçülerek
yazılabiliyordu — yani satırın en kritik iddiası ("GitHub'ın kendi
tetiklemesi oldu mu?") ölçüm disiplinine değil, birinin hatırlamasına bağlıydı.
`schedule` tetikleyicisi hiç ateşlenmezse kırmızı bir koşum da doğmaz: yalnız
sessizlik olur ve satır "bekliyor" hâlinde sonsuza kadar bayatlar.

Bu betik o sessizliği ölçülebilir hâle getirir. Tek giriş noktasıdır
(workflow mantığı YAML'da yeniden yazılmaz):

  1) `docker-security.yml`'in koşumlarını okur (tek kaynak: `gh run list`,
     R4 satırının kendi ölçüm komutuyla aynı — `--runs-file` ile offline).
  2) `event=schedule` koşumlarını ayırır, **beklenen ilk tick'ten
     (2026-10-05T03:43Z) sonraki EN ERKEN** koşumu seçer. Push / PR /
     dispatch koşumları cron kanıtı SAYILMAZ: aynı yolu koşsalar da
     tetikleyici farklıdır (runbook'un "elle koşum ne kanıtlar" ayrımı).
  3) Üç durumdan birini hükmeder:
       pending — sert bitişten önce, schedule koşumu yok (bekleme penceresi)
       missed  — sert bitiş geçti, schedule koşumu hâlâ yok → KIRMIZI
       fired   — schedule koşumu var; conclusion=success ise PASS, değilse
                 KIRMIZI (cron ateşlendi ama kapı düştü — gerçek sinyal)
  4) `--apply`: hükmü `docs/FULL_SCOPE_AUDIT_2026-09-17.md` R4 satırındaki
     işaretli parçaya yazar. Parça MAKİNE-YÖNETİMLİDİR: elle düzenlenmez,
     önceki ölçümlerin (2026-10-02/2026-10-31: schedule 0) kaydı satırın
     gövdesinde KALIR, güncel hüküm parçadadır.

Fail-closed sözleşmesi (sessiz PASS yok):
  rc 0 = ölçüldü ve kanıt temiz (pending ya da fired/success)
  rc 1 = ölçüldü ve kanıt KÖTÜ (missed ya da fired/başarısız) — satır yine
         yazılır, çünkü "❌ ölçüldü" ile "boş = ölçülmedi" farklı iddialardır
  rc 2 = ÖLÇÜLEMEDİ (gh yok/API hatası/bozuk JSON/işaretler eksik) — satıra
         HİÇBİR ŞEY yazılmaz, workflow kırmızı olur

Idempotent: yazma kararı hükmün KİMLİĞİNE bağlıdır — (durum, run id,
conclusion). Ölçüm saati metinde görünür ama kimliğe girmez; aksi hâlde nöbet
her hafta aynı hükmü yeniden yazıp boşuna bot PR'ı açardı.

OFFLINE test edilebilir: `--runs-file` + `--now` ile ağ olmadan; stdlib-only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ROOT = HERE.parent.parent
DEFAULT_DOC = ROOT / "docs" / "FULL_SCOPE_AUDIT_2026-09-17.md"

WORKFLOW_FILE = "docker-security.yml"
WATCHDOG_WORKFLOW = ".github/workflows/docker-security-cron-evidence.yml"

# R4 satırının başı: tablo satırı "| R4 | risk | ...".
ROW_PREFIX = "| R4 "

# Makine-yönetimli parça işaretleri. Parça R4 satırının İÇİNDEDİR (tek satır
# tablo hücresi); işaretler eksik/çoksa betik yazmayı REDDEDER (rc 2) — sessizce
# ikinci bir parça eklemek, hangi hükmün geçerli olduğunu belirsizleştirirdi.
SEGMENT_START = "<!-- r4-cron-evidence:start -->"
SEGMENT_END = "<!-- r4-cron-evidence:end -->"

# Ölçülen armed tarih: PR #52 merge'i (2026-09-30T22:19:48Z) sonrası ilk
# Pazartesi tick'i. `test_security_cron_schedule.py` aynı değeri pin'ler.
EXPECTED_FIRST_TICK = datetime(2026, 10, 5, 3, 43, tzinfo=timezone.utc)

# Sert bitiş: tick + 20sa. Ölçülen scheduler gecikmesi 5s36d–7s37d (2026-10-05…
# 10-26 koşumları); 20sa, gecikmeyi "geç ama ateşlendi" sayarken haftanın geri
# kalanına taşmaz — nöbet Salı 05:17'de koşar, yani ölçüm bitişten SONRA olur.
DEFAULT_DEADLINE_HOURS = 20
RUN_LIMIT = 100

STATES = ("pending", "missed", "fired")


class Unmeasured(RuntimeError):
    """Ölçüm yapılamadı → rc 2, satıra hiçbir şey yazılmaz."""


class DocContractError(RuntimeError):
    """R4 satırı/parça işaretleri beklenen biçimde değil → rc 2 (elle düzeltme)."""


# ── zaman yardımcıları ────────────────────────────────────────────────────

def parse_ts(value: str) -> datetime:
    """ISO-8601 (Z dahil) → tz-aware datetime. Naif girdi reddedilir."""
    if not isinstance(value, str) or not value.strip():
        raise Unmeasured("zaman değeri boş: %r" % (value,))
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise Unmeasured("zaman ayrıştırılamadı: %r (%s)" % (value, exc)) from exc
    if dt.tzinfo is None:
        raise Unmeasured("saat dilimi olmayan zaman reddedildi: %r" % (value,))
    return dt.astimezone(timezone.utc)


def fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


# ── koşum seçimi (saf) ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Run:
    id: str
    created: datetime
    event: str
    status: str
    conclusion: str | None
    url: str = ""

    @property
    def identity(self):
        return (self.id, self.conclusion)


@dataclass
class Verdict:
    state: str
    schedule_count: int
    total_runs: int
    as_of: datetime
    expected: datetime
    deadline_hours: int
    run: Run | None = None

    @property
    def deadline(self) -> datetime:
        return self.expected + timedelta(hours=self.deadline_hours)

    @property
    def identity(self):
        return (self.state, self.run.id if self.run else None,
                self.run.conclusion if self.run else None)

    def exit_code(self) -> int:
        if self.state == "pending":
            return 0
        if self.state == "missed":
            return 1
        return 0 if self.run is not None and self.run.conclusion == "success" else 1


def normalize_runs(payload) -> list[Run]:
    """`gh run list --json …` çıktısı ya da `{"workflow_runs": [...]}` → Run[]."""
    if isinstance(payload, dict):
        raw = payload.get("workflow_runs")
        if raw is None:
            raise Unmeasured("koşum listesi bulunamadı (workflow_runs yok)")
        items = raw
    elif isinstance(payload, list):
        items = payload
    else:
        raise Unmeasured("koşum listesi beklenen biçimde değil: %s"
                         % type(payload).__name__)

    runs: list[Run] = []
    for item in items:
        if not isinstance(item, dict):
            raise Unmeasured("koşum kaydı eşlenik değil: %r" % (item,))
        rid = item.get("databaseId", item.get("id"))
        created = item.get("createdAt", item.get("created_at"))
        event = item.get("event")
        if not rid or not created or not event:
            raise Unmeasured("koşum kaydı eksik alan taşıyor: %r" % (item,))
        runs.append(Run(
            id=str(rid),
            created=parse_ts(created),
            event=str(event),
            status=str(item.get("status") or ""),
            conclusion=item.get("conclusion"),
            url=str(item.get("url") or item.get("html_url") or ""),
        ))
    return runs


def select_first_scheduled(runs: list[Run], expected: datetime):
    """(ilk uygun schedule koşumu | None, toplam schedule sayısı).

    Kriter iki katmanlı:
      * `event == "schedule"` — push/PR/dispatch koşumu cron kanıtı DEĞİLDİR
        (aynı işi koşar, farklı tetikleyici; runbook bu ayrımı pin'ler).
      * `created >= expected` — armed tarihten (PR #52 merge'i sonrası ilk
        Pazartesi) ÖNCEKİ bir schedule koşumu bu tick'in kanıtı sayılmaz.
    """
    scheduled = [r for r in runs if r.event == "schedule"]
    after = [r for r in scheduled if r.created >= expected]
    after.sort(key=lambda r: (r.created, r.id))
    return (after[0] if after else None), len(scheduled)


def measure(runs: list[Run], now: datetime,
            expected: datetime = EXPECTED_FIRST_TICK,
            deadline_hours: int = DEFAULT_DEADLINE_HOURS) -> Verdict:
    if deadline_hours <= 0:
        raise Unmeasured("deadline-hours pozitif olmalı: %r" % (deadline_hours,))
    run, scheduled_count = select_first_scheduled(runs, expected)
    if run is not None:
        state = "fired"
    elif now < expected + timedelta(hours=deadline_hours):
        state = "pending"
    else:
        state = "missed"
    return Verdict(state=state, schedule_count=scheduled_count,
                   total_runs=len(runs), as_of=now, expected=expected,
                   deadline_hours=deadline_hours, run=run)


# ── hükmü metne çevirme ───────────────────────────────────────────────────

def render_segment(v: Verdict) -> str:
    """R4 satırına gömülecek MAKİNE-YÖNETİMLİ parça (işaretler hariç).

    Kısıt: tablo hücresi — parça `|` İÇERMEZ (hücreyi bölerdi).
    """
    head = ("**Son hüküm (makine-yönetimli — `%s`, ölçüm %s):** "
            % (WATCHDOG_WORKFLOW, fmt(v.as_of)))
    tick = fmt(v.expected)
    if v.state == "pending":
        body = ("beklenen ilk `schedule` tick'i (`%s`) ve +%dh sert bitişi henüz "
                "GEÇMEDİ; `event=schedule` koşum sayısı **0** → nöbet bekleme "
                "penceresinde, kanıt bekleniyor."
                % (tick, v.deadline_hours))
    elif v.state == "missed":
        body = ("beklenen ilk `schedule` tick'i (`%s`) ve +%dh sert bitişi "
                "**GEÇTİ**, `event=schedule` koşum sayısı hâlâ **0** (son %d "
                "koşumun tamamı push / pull_request / workflow_dispatch) → "
                "GitHub'ın kendi tetiklemesi kanıtlanmadı; R4 bu yüzden açık "
                "ve nöbet bu durumu KIRMIZI raporlar."
                % (tick, v.deadline_hours, v.total_runs))
    else:
        run = v.run
        assert run is not None  # state=fired ⇒ run var
        ref = ("run [`%s`](%s)" % (run.id, run.url)) if run.url else ("run `%s`" % run.id)
        body = ("zamanlanmış tetikleme **KANITLANDI** — ilk `schedule` koşumu %s, "
                "`created_at=%s` (tick `%s`), status `%s`, conclusion `%s`; "
                "`event=schedule` koşum sayısı **%d**. Yukarıdaki \"henüz "
                "ateşlenmedi / schedule 0\" ifadeleri kanıttan ÖNCEKİ ölçümün "
                "kaydıdır; güncel hüküm bu parçadır."
                % (ref, fmt(run.created), tick, run.status or "-",
                   run.conclusion or "-", v.schedule_count))
    tail = (" Bu parça nöbet akışı tarafından ölçümden yeniden yazılır — elle "
            "düzenlenmez.")
    segment = head + body + tail
    if "|" in segment:  # savunma: hücre sınırını bozan bir değer girmesin
        raise DocContractError("parça `|` içeriyor (tablo hücresi bölünür)")
    return segment


# ── satır okuma/yazma ─────────────────────────────────────────────────────

def find_row_line(lines: list[str]) -> int:
    hits = [i for i, ln in enumerate(lines) if ln.startswith(ROW_PREFIX)]
    if not hits:
        raise DocContractError("R4 satırı bulunamadı (beklenen önek: %r)"
                               % ROW_PREFIX)
    if len(hits) > 1:
        raise DocContractError("R4 satırı %d kez geçiyor — hüküm belirsiz, "
                               "elle düzeltilmeli" % len(hits))
    return hits[0]


def read_segment(row: str) -> str:
    """R4 satırındaki parçanın gövdesi; işaretler tekil değilse DocContractError."""
    if row.count(SEGMENT_START) != 1 or row.count(SEGMENT_END) != 1:
        raise DocContractError(
            "R4 satırında parça işaretleri tekil değil (start=%d, end=%d) — "
            "betik ikinci bir parça eklemez; elle düzeltin"
            % (row.count(SEGMENT_START), row.count(SEGMENT_END)))
    start = row.index(SEGMENT_START) + len(SEGMENT_START)
    end = row.index(SEGMENT_END)
    if end < start:
        raise DocContractError("R4 parçasının bitiş işareti başlangıçtan önce")
    return row[start:end]


def write_segment(text: str, segment: str) -> str:
    """Parçayı değiştirir (işaretler korunur); R4 dışına dokunmaz."""
    lines = text.splitlines()
    idx = find_row_line(lines)
    row = lines[idx]
    read_segment(row)  # sözleşme denetimi
    start = row.index(SEGMENT_START) + len(SEGMENT_START)
    end = row.index(SEGMENT_END)
    lines[idx] = row[:start] + segment + row[end:]
    out = "\n".join(lines)
    if text.endswith("\n"):
        out += "\n"
    return out


def segment_identity(segment: str):
    """Mevcut parçanın kimliği (durum, run id, conclusion) — idempotan için.

    Kimlik metinden değil hükümden türetilir; burada yalnızca "bu parça HANGİ
    durumu iddia ediyor" sorusuna cevap verilir. Okunamayan parça → None, yani
    "yaz" (fail-closed: bozuk parça sessizce korunmaz, ölçümle değiştirilir).
    """
    if "**KANITLANDI**" in segment:
        import re
        m = re.search(r"run \[?`([^`]+)`\]?(?:\([^)]*\))?, `created_at=([^`]+)`"
                      r".*conclusion `([^`]+)`", segment)
        if m:
            return ("fired", m.group(1), None if m.group(3) == "-" else m.group(3))
        return None
    if "**GEÇTİ**" in segment:
        return ("missed", None, None)
    if "henüz GEÇMEDİ" in segment:
        return ("pending", None, None)
    return None


def apply_verdict(text: str, v: Verdict) -> tuple[str, bool]:
    """(yeni metin, değişti mi). Kimlik aynıysa metin AYNEN döner."""
    segment = render_segment(v)
    lines = text.splitlines()
    idx = find_row_line(lines)
    current = read_segment(lines[idx])
    if segment_identity(current) == v.identity:
        return text, False
    if current.strip() == segment.strip():
        return text, False
    return write_segment(text, segment), True


# ── canlı ölçüm ───────────────────────────────────────────────────────────

def fetch_runs(repo: str) -> list[Run]:
    """`gh run list` ile koşumları oku; gh yok/API hatası → Unmeasured (rc 2)."""
    try:
        import audit_live_ci_sync as alcs
    except ImportError as exc:  # pragma: no cover — kurulum hatası
        raise Unmeasured("audit_live_ci_sync import edilemedi: %s" % exc) from exc
    argv = [
        "run", "list",
        "--workflow", WORKFLOW_FILE,
        "--limit", str(RUN_LIMIT),
        "--json", "databaseId,createdAt,event,status,conclusion,url",
    ]
    if repo:
        argv += ["--repo", repo]
    try:
        out = alcs.run_gh(argv)
    except RuntimeError as exc:
        raise Unmeasured("gh koşum listesi alınamadı: %s" % exc) from exc
    try:
        payload = json.loads(out)
    except (TypeError, ValueError) as exc:
        raise Unmeasured("gh çıktısı JSON değil: %s" % exc) from exc
    return normalize_runs(payload)


def load_runs_file(path: str) -> list[Run]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise Unmeasured("koşum dosyası okunamadı: %s" % exc) from exc
    except ValueError as exc:
        raise Unmeasured("koşum dosyası bozuk JSON: %s" % exc) from exc
    return normalize_runs(payload)


# ── CLI ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="docker-security cron kanıtı → R4 satırı (fail-closed)")
    ap.add_argument("--doc", default=str(DEFAULT_DOC),
                    help="denetim belgesi (varsayılan: %s)" % DEFAULT_DOC)
    ap.add_argument("--runs-file", default=None,
                    help="offline: koşum listesi JSON (gh çağrılmaz)")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""),
                    help="owner/repo (varsayılan: GITHUB_REPOSITORY)")
    ap.add_argument("--now", default=None,
                    help="ölçüm anı (ISO-8601; varsayılan: şimdi, UTC)")
    ap.add_argument("--expected-first-tick", default=None,
                    help="beklenen ilk tick (varsayılan: 2026-10-05T03:43Z)")
    ap.add_argument("--deadline-hours", type=int, default=DEFAULT_DEADLINE_HOURS,
                    help="tick + N saat = sert bitiş (varsayılan: %d)"
                         % DEFAULT_DEADLINE_HOURS)
    ap.add_argument("--apply", action="store_true",
                    help="hükmü R4 parçasına yaz (varsayılan: yalnız ölç)")
    ap.add_argument("--json", action="store_true",
                    help="tek JSON dokümanı bas (stdout)")
    ap.add_argument("--print-segment", action="store_true",
                    help="üretilen parçayı stdout'a bas (teşhis)")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        now = parse_ts(args.now) if args.now else datetime.now(timezone.utc)
        expected = (parse_ts(args.expected_first_tick) if args.expected_first_tick
                    else EXPECTED_FIRST_TICK)
        runs = (load_runs_file(args.runs_file) if args.runs_file
                else fetch_runs(args.repo))
        verdict = measure(runs, now, expected, args.deadline_hours)
        doc = Path(args.doc)
        try:
            text = doc.read_text(encoding="utf-8")
        except OSError as exc:
            raise DocContractError("belge okunamadı: %s" % exc) from exc

        if args.print_segment:
            print(render_segment(verdict))

        changed = False
        if args.apply:
            new_text, changed = apply_verdict(text, verdict)
            if changed:
                doc.write_text(new_text, encoding="utf-8")
    except (Unmeasured, DocContractError) as exc:
        print("FAIL: %s" % exc, file=sys.stderr)
        if args.json:
            print(json.dumps({
                "verdict": "UNMEASURED", "state": None, "changed": False,
                "exit": 2, "error": str(exc), "doc": str(args.doc),
            }, ensure_ascii=False))
        return 2

    rc = verdict.exit_code()
    run = verdict.run
    payload = {
        "verdict": "PASS" if rc == 0 else "FAIL",
        "state": verdict.state,
        "changed": changed,
        "applied": bool(args.apply),
        "schedule_count": verdict.schedule_count,
        "total_runs": verdict.total_runs,
        "expected_first_tick": fmt(verdict.expected),
        "deadline": fmt(verdict.deadline),
        "as_of": fmt(verdict.as_of),
        "run_id": run.id if run else None,
        "run_created_at": fmt(run.created) if run else None,
        "run_status": run.status if run else None,
        "run_conclusion": run.conclusion if run else None,
        "doc": str(args.doc),
        "exit": rc,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print("%s: state=%s schedule=%d/%d run=%s changed=%s"
              % (payload["verdict"], verdict.state, verdict.schedule_count,
                 verdict.total_runs, payload["run_id"] or "-", changed))
        if verdict.state == "missed":
            print("  beklenen tick (%s) + %dh sert bitiş geçti; schedule "
                  "koşumu yok → cron'un GitHub tetiklemesi KANITLANMADI"
                  % (fmt(verdict.expected), verdict.deadline_hours))
        elif verdict.state == "fired":
            print("  ilk schedule koşumu: %s (conclusion=%s)"
                  % (payload["run_created_at"], payload["run_conclusion"]))
    return rc


if __name__ == "__main__":
    sys.exit(main())
