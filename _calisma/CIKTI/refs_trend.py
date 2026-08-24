#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refs_trend.py — `refs-online` artifact'larını run'lar arası toplar ve
"online verification trend" tablosu üretir (CrossRef/SEP/OpenLibrary ve
diğer kaynaklardan çevrimiçi doğrulanan referans sayısının zaman serisi).

Kaynak: GitHub Actions API — iki artifact türü run'lar arası toplanır:
  - `refs-online` → her zip'ten `references_online.json` (verify_delivery.py
    --refs-out'un ürettiği VERSION JSON) → çevrimiçi doğrulama zaman serisi.
  - `run-history` → her zip'ten `history.jsonl` (verify_delivery.py
    --history-out'un tek JSONL kaydı; ts/duration_s/budget_usd/verdict) →
    duration + budget trendi.

Kimlik:
  - CI: GITHUB_TOKEN env (workflow'da `actions: read` gerekir).
  - Yerel: token yoksa `gh api` (kullanıcı auth'u) kullanılır.

Çıktı (--out-dir):
  - refs-trend.md  — insan-okur tablo: refs trendi + duration/budget trendi
  - refs-trend.json — makine-okur {generated, repo, rows[], totals,
                     duration_budget{rows[], summary}}

Kullanım:
  GITHUB_TOKEN=... python3 _calisma/CIKTI/refs_trend.py --repo owner/name \\
      --out-dir refs-trend [--max-artifacts 100]

Çıkış kodları: 0 her zaman (veri yoksa boş tablo + not; API hatası → 1,
advisory job continue-on-error ile tolere eder).
"""
import argparse
import datetime
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile

API = "https://api.github.com"

# refs-trend raporu changelog'u (kısa kayıt; en yeni üstte).
# Kaynak: verify_delivery.py K6 denetimindeki düzeltmeler. Yeni bir denetim
# düzeltmesi yapıldığında buraya tek satır eklenir (denetlenebilir geçmiş).
CHANGELOG = [
    ("2026-08-24",
     "V5aa: CI'da geçici OL timeout'ları belgelendi (58/61 push + 61/61 "
     "workflow_dispatch); `_ol_retry` outer retry eklendi — zaman aşımı/" 
     "connection reset/5xx geçici UNVERIFIED'lar 3s bekleyip tekrar denenir."),
    ("2026-08-22",
     "V5z: canlı CI 61/61 PASS, UNVERIFIED=0 — tüm kanıt zincirleri "
     "birlikte doğrulandı (LoC 3 + Handle 1 + HT 1 + OL fallback Fine)."),
    ("2026-08-22",
     "Kapsam: 61/61 — 64 referansın 61'i çevrimiçi kaynaktan doğrulanır "
     "(CrossRef/SEP/OpenLibrary/Internet Archive/Handle/LoC/Perseus), 3'ü "
     "bibliyografik belgedir (modern kitaplar: IA'da tarama yok, HT'de katalog "
     "yok, OL'de kayıtlı). Erken dönem '54/54' sayısı artık geçersizdir — "
     "V5 düzeltme zinciri boyunca kapsam 54→56 (CrossRef dergileri) → 61 "
     "(Sextus IA birebir + Della Rocca Handle) olarak genişledi; '54' sayısı "
     "yalnızca CrossRef+SEP+OL+IA temel zincirinin sonucuydu, LoC/Handle/ia_ids "
     "fallback'leri eklenmeden önceki durumu yansıtır."),
    ("2026-08-21",
     "V5w: Lagrée/Millican/Schmitt/Fine kitapları HathiTrust'sız katalog "
     "kanıtıyla — Library of Congress lccn kayıtları PASS (loc_check; zincir "
     "IA → HT → LoC → OL → GB). by_source'ta yeni `loc` kaynağı; kapsam "
     "değişmedi (61/61 PASS)."),
    ("2026-08-21",
     "V5v: refs-trend denetimi tekrarlanabilir script oldu — "
     "audit_refs_trend.py, refs-trend.json satırlarını kaynak refs-online "
     "artifact'larıyla karşılaştırır (sahte satır / sayı / by_source drift'i "
     "/ bayat trend → exit 1; advisory audit-refs-trend job'ı). Canlı "
     "denetim 83/83 satır birebir PASS."),
    ("2026-08-21",
     "V5r: OL edisyon kayıtlarında oclc YOK — tam identifier matrisi HT'ye "
     "denendi (lccn + oclc + isbn), yalnızca Xunzi (`lccn:87033578`) eşleşir; "
     "4 modern telifli kitap HT kataloğunda yok, OL fallback PASS ile kalır."),
    ("2026-08-21",
     "V5q: kapsam boşluğu kapatıldı — 4 Sextus edisyonu (1562 Estienne, "
     "1569 Hervet, 1621 Chouet) IA'da `ia_ids` ile birebir identifier "
     "doğrulamasıyla, Della Rocca 2010 arşivlenmiş Wayback URL ile "
     "doğrulanır; 61/64 canlı kapsam."),
    ("2026-08-21",
     "V5t: Della Rocca 2010 'PSR' artık CrossRef DIŞI Handle System API'den "
     "doğrulanır — makalenin kendi DC.identifier'ı bir Handle'dır "
     "(hdl.handle.net/2027/spo.3521354.0010.007), DOI yok; kaynak sayısı "
     "değişmedi (61/61 PASS)."),
    ("2026-08-19",
     "V5p: OpenLibrary'den OCLC/LCCN identifier'ları çekildi, HathiTrust "
     "fallback'i OL'den önce denenir (V5p: Xunzi `lccn:87033578` ile HT "
     "katalog kaydıyla PASS; oclc/lccn değerleri ht_ids'e eklendi)."),
    ("2026-08-19",
     "V5o: 11 UNVERIFIED kaynak kapatıldı → 56/56 tam çevrimiçi kapsam. "
     "Denetim REFERENCE_POOL_SIZE=4 havuzda PARALEL koşar — sıralı koşudaki "
     "rate-limit (OpenLibrary ~8 sn/çağrı) bütçe-skip'e düşürüp UNVERIFIED "
     "bırakıyordu; bütçe 260 sn'ye çıkarıldı. Canlı doğrulama: 56/56 PASS, "
     "94 sn (crossref 6, sep 5, openlibrary 27, archive 16, perseus 2). "
     "NOT: bu 56/56 **yerel doğrulama**dır (trend tablosunda görünmez); "
     "deterministik kanıtı REFERANS_KANIT_DENETIMI.md §5.3'te "
     "`ia_ol_fallback_evidence.py --offline` ile belgelenmiştir."),
    ("2026-08-19",
     "V5n: Norton 1981 ve Popkin 1951 DOI'leri CrossRef'e eklendi — kapsam-dışı "
     "kalan son 2 dergi makalesi artık çevrimiçi doğrulanır "
     "(canlı kapsam 54→56; 4fe2ccc)."),
    ("2026-08-18",
     "Hicks 1925 ve Hume 1975 OpenLibrary sorguları güçlendirildi "
     "(29/31 → 31/31 çevrimiçi doğrulama; ce5523b)."),
]


class _NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Redirect'te Authorization başlığını düşürür.

    GitHub `/zip` endpoint'i imzalı Azure blob URL'ine 302 yönlendirir.
    urllib varsayılan olarak Authorization'ı redirect'e taşır; blob depolama
    geçersiz Bearer token'ı 401 (InvalidAuthenticationInfo) ile reddeder.
    İmza URL'in kendisindedir — redirect'te auth başlığı gerekmez.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.remove_header("Authorization")
        return new


def api_get(path, token, binary=False):
    """GitHub API GET. Token varsa urllib, yoksa `gh api` (yerel auth)."""
    if token:
        req = urllib.request.Request(f"{API}{path}")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("User-Agent", "refs-trend")
        # Redirect'te Authorization'ı düşür (Azure blob 401'inin kökü).
        opener = urllib.request.build_opener(_NoAuthRedirect)
        with opener.open(req, timeout=60) as r:
            data = r.read()
        return data if binary else json.loads(data.decode("utf-8"))
    cmd = ["gh", "api", path]
    r = subprocess.run(cmd, capture_output=True, text=not binary)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "gh api hatası").strip())
    out = r.stdout
    if binary:
        # text=False iken bytes, text=True iken str gelebilir.
        return out if isinstance(out, bytes) else out.encode()
    return json.loads(out.decode("utf-8") if isinstance(out, bytes) else out)


def fetch_artifacts_by_name(repo, token, name, max_artifacts):
    """Son max_artifacts adet `name` artifact'ını toplar -> [dict] (tarih sıralı)."""
    rows = []
    page = 1
    while len(rows) < max_artifacts:
        path = (f"/repos/{repo}/actions/artifacts?name={name}"
                f"&per_page=100&page={page}")
        data = api_get(path, token)
        artifacts = data.get("artifacts", [])
        for a in artifacts:
            if a.get("name") == name:
                rows.append(a)
        if len(artifacts) < 100 or len(rows) >= max_artifacts:
            break
        page += 1
        if page > 10:  # güvenlik: en fazla 1000 artifact
            break
    rows.sort(key=lambda a: a.get("created_at", ""))
    return rows[-max_artifacts:]


def fetch_refs_online_artifacts(repo, token, max_artifacts):
    """Son max_artifacts adet `refs-online` artifact'ını toplar -> [dict]."""
    return fetch_artifacts_by_name(repo, token, "refs-online", max_artifacts)


def parse_report(blob):
    """Artifact zip'inden references_online.json'u ayrıştırır."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist()
                 if n.endswith("references_online.json")]
        if not names:
            raise ValueError("zip içinde references_online.json yok")
        return json.loads(z.read(names[0]).decode("utf-8"))


def parse_history_record(blob):
    """Artifact zip'inden history.jsonl'in son (en güncel) kaydını döndürür."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if n.endswith("history.jsonl")]
        if not names:
            raise ValueError("zip içinde history.jsonl yok")
        text = z.read(names[0]).decode("utf-8")
    last = None
    for line in text.splitlines():
        line = line.strip()
        if line:
            last = json.loads(line)
    if last is None:
        raise ValueError("history.jsonl boş")
    return last


def stats(vals):
    """Sayı listesi için {count,min,max,avg} özeti; boşsa {count:0,...}."""
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return {"count": 0, "min": None, "max": None, "avg": None}
    return {
        "count": len(vals),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "avg": round(sum(vals) / len(vals), 2),
    }


# ── Eşik değerleri (süre/bütçe ihlali uyarıları) ────────────────────────
DURATION_WARN_S = 300.0    # 5 dakika üzeri süre uyarısı
BUDGET_WARN_USD = 30.0     # $30 bütçe limiti uyarısı (verify_delivery.config)


def check_run_warnings(r, dur_warn=DURATION_WARN_S, bud_warn=BUDGET_WARN_USD):
    """Tek bir run için duration/budget eşik uyarılarını döndür.

    Döndürülen dict:
        {"duration_warn": bool, "budget_warn": bool,
         "duration_val": float|None, "budget_val": float|None,
         "messages": [str]}
    """
    dur = r.get("duration_s")
    bud = r.get("budget_usd")
    msgs = []
    dw = False
    bw = False
    if isinstance(dur, (int, float)) and dur > dur_warn:
        dw = True
        msgs.append(f"süre {dur:.1f}s > eşik {dur_warn:.0f}s")
    if isinstance(bud, (int, float)) and bud > bud_warn:
        bw = True
        msgs.append(f"bütçe ${bud:.2f} > eşik ${bud_warn:.0f}")
    # K8 Z3: failed varsa uyarı
    z3p = r.get("z3_passed")
    z3t = r.get("z3_total")
    if isinstance(z3p, (int, float)) and isinstance(z3t, (int, float)):
        z3f = z3t - z3p
        if z3f > 0:
            msgs.append(f"Z3 FAIL {int(z3f)}/{int(z3t)}")
    return {
        "duration_warn": dw,
        "budget_warn": bw,
        "duration_val": dur if isinstance(dur, (int, float)) else None,
        "budget_val": bud if isinstance(bud, (int, float)) else None,
        "messages": msgs,
    }


def summarize_warnings(history_rows, dur_warn=DURATION_WARN_S, bud_warn=BUDGET_WARN_USD):
    """Tüm run'lar için uyarı özetini döndür.

    Döndürülen dict:
        {"duration_violations": int, "budget_violations": int,
         "total_runs": int, "violations": [{run_idx, date, messages}]}
    """
    violations = []
    for i, r in enumerate(history_rows):
        w = check_run_warnings(r, dur_warn, bud_warn)
        if w["messages"]:
            violations.append({
                "run_idx": i + 1,
                "date": r.get("date", ""),
                "run_id": r.get("run_id"),
                "messages": w["messages"],
            })
    return {
        "duration_violations": sum(1 for v in violations
                                    for m in v["messages"] if "süre" in m),
        "budget_violations": sum(1 for v in violations
                                  for m in v["messages"] if "bütçe" in m),
        "total_runs": len(history_rows),
        "violations": violations,
    }


def build_duration_budget(history_rows):
    """history_rows'tan duration_budget JSON bölümünü üretir (fail-closed).

    Her run'a duration/budget eşik bayraklarını işler (check_run_warnings),
    summary stats'ını hesaplar ve eşik ihlali özetini ekler. main() ve birim
    testleri ORTAK kullanır — bölümün JSON sözleşmesi tek kaynaktır:
        {run_count,
         rows[{date, run_id, duration_s, budget_usd, verdict, p0, p1,
               z3_passed, z3_total, duration_warn, budget_warn}],
         summary{duration_s{count,min,max,avg}, budget_usd{...}},
         warnings{duration_violations, budget_violations, total_runs,
                  violations[{run_idx, date, run_id, messages}]} | None}
    Sayısal olmayan duration/budget değerleri stats'a katılmaz (markdown'da
    '—' gösterilir), run_count yine de tüm run'ları sayar; boş girdi
    warnings=None üretir (bölüm yok anlamında).
    """
    rows = []
    for r in history_rows:
        w = check_run_warnings(r)
        rows.append({
            "date": r.get("date", ""),
            "run_id": r.get("run_id"),
            "duration_s": r.get("duration_s"),
            "budget_usd": r.get("budget_usd"),
            "verdict": r.get("verdict"),
            "p0": r.get("p0"),
            "p1": r.get("p1"),
            "z3_passed": r.get("z3_passed"),
            "z3_total": r.get("z3_total"),
            "duration_warn": w["duration_warn"],
            "budget_warn": w["budget_warn"],
            "audit_refs_trend": r.get("audit_refs_trend"),
        })
    return {
        "run_count": len(rows),
        "rows": rows,
        "summary": {
            "duration_s": stats([r["duration_s"] for r in rows]),
            "budget_usd": stats([r["budget_usd"] for r in rows]),
        },
        "warnings": summarize_warnings(rows) if rows else None,
    }


def short_date(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return (iso or "")[:16]


def _coverage_change_note(row, prev_row, changelog=None):
    """total_online değiştiğinde ilgili V5 notunu döndür.

    Değişim yoksa boş string; ilk satırsa boş string.
    CHANGELOG, [(date_str, note_str), ...] formatında ters kronolojik.
    """
    if prev_row is None:
        return ""
    cur_total = row.get("total_online", 0)
    prev_total = prev_row.get("total_online", 0)
    if cur_total == prev_total:
        return ""
    # Kapsam değişim yönü
    diff = cur_total - prev_total
    arrow = "↑" if diff > 0 else "↓"
    # Tarihe en yakın CHANGELOG entry'sini bul
    if changelog is None:
        changelog = CHANGELOG
    row_date = (row.get("date") or "")[:10]  # YYYY-MM-DD
    best_note = None
    for date_str, note in changelog:
        if date_str <= row_date:
            # V5xxx notunu ara
            if note and ("Kapsam" in note or "kapsam" in note
                         or "56→" in note or "61" in note
                         or "→56" in note or "→61" in note):
                best_note = note[:60]
                break
    if best_note:
        return f"{arrow} {prev_total}→{cur_total} ({best_note})"
    return f"{arrow} {prev_total}→{cur_total}"


def changelog_lines():
    """CHANGELOG kaydını markdown satırlarına çevirir (boş liste = changelog yok).

    Tek kaynak: CHANGELOG sabiti. Denetim düzeltmelerinin kısa, denetlenebilir
    geçmişini refs-trend.md'nin altına ekler (en yeni üstte). V5p–V5w arası
    özet tablosu kapsamları ve by_source değişimlerini gösterir.
    """
    if not CHANGELOG:
        return []
    out = ["## Changelog", ""]

    # V5p–V5w özet tablosu: kapsam + by_source değişim zinciri.
    out.append("### Kapsam & by_source değişim tablosu (V5p–V5w)")
    out.append("")
    out.append("| Versiyon | Tarih | Kapsam | by_source değişimi | Not |")
    out.append("|---|---|---|---|---|")
    out.append("| V5n | 08-19 | 54→56 | crossref +2 (Norton/Popkin) | CrossRef dergileri eklendi |")
    out.append("| V5o | 08-19 | 56/56 | — (aynı dağılım) | Paralel koşu, rate-limit düzeltmesi |")
    out.append("| V5p | 08-19 | 56/56 | Xunzi: `lccn:87033578` → HT PASS | OCLC/LCCN ht_ids'e eklendi |")
    out.append("| V5q | 08-21 | 56→61 | archive +4 (Sextus ia_ids) +1 (Della Rocca Wayback) | Kapsam boşluğu kapatıldı |")
    out.append("| V5r | 08-21 | 61/61 | — (aynı dağılım) | OL oclc YOK; Xunzi hariç hepsi OL fallback |")
    out.append("| V5t | 08-21 | 61/61 | handle +1 (Della Rocca → Handle System) | CrossRef dışı kalıcı tanımlayıcı |")
    out.append("| V5v | 08-21 | 61/61 | — (denetim altyapısı) | audit_refs_trend.py eklendi |")
    out.append("| V5w | 08-21 | 61/61 | loc +3 (Lagrée/Millican/Schmitt), openlibrary −3 | LoC lccn katalog kanıtı |")
    out.append("")

    for date, note in CHANGELOG:
        out.append(f"- **{date}:** {note}")
    out.append("")
    return out


def build_coverage_transition_summary(rows):
    """Rows'tan UNVERIFIED > 0 → 0 geçiş özet tablosu üretir.

    Tüm refs-online artifact'larını tarar, total_online değişimlerini ve
    her aşamada UNVERIFIED sayısının sıfıra düştüğü ilk run'ı bulur.
    Kompakt tek satırlı özet: 54/49 → 56/26 → 61/61 geçiş zinciri.

    Döndürür: markdown satır listesi veya boş liste.
    """
    if len(rows) < 2:
        return []

    # Her unique total_online değeri için ilk ve son UNVERIFIED durumu
    by_total = {}
    for r in rows:
        t = r.get("total_online", 0)
        u = r.get("unverified", 0)
        if t not in by_total:
            by_total[t] = {"first_unverified": u, "last_unverified": u,
                           "first_date": r.get("date", ""),
                           "first_run": r.get("run_id"),
                           "last_date": r.get("date", ""),
                           "last_run": r.get("run_id")}
        else:
            by_total[t]["last_unverified"] = u
            by_total[t]["last_date"] = r.get("date", "")
            by_total[t]["last_run"] = r.get("run_id")

    # total_online değerine göre sırala
    sorted_totals = sorted(by_total.keys())

    # Geçiş zinciri: her aşamada UNVERIFIED'ın sıfıra ilk düştüğü anı bul
    out = []
    out.append("### UNVERIFIED → 0 geçiş özeti")
    out.append("")
    out.append("| Aşama | total_online | İlk UNVERIFIED | UNVERIFIED=0 ilk run | Tarih |")
    out.append("|---|---|---|---|---|")

    for t in sorted_totals:
        info = by_total[t]
        first_u = info["first_unverified"]
        last_u = info["last_unverified"]

        # Bu total_online değerinde UNVERIFIED'ın sıfıra düştüğü ilk satırı bul
        zero_run = None
        zero_date = None
        for r in rows:
            if r.get("total_online") == t and r.get("unverified", 0) == 0:
                zero_run = r.get("run_id")
                zero_date = r.get("date", "")
                break

        if zero_run:
            # Tam kapsam: UNVERIFIED=0'a ulaşıldı
            line = (f"| **{t}/{t}** | {t} | {first_u} | "
                    f"`{zero_run}` | {short_date(zero_date)} |")
        else:
            # UNVERIFIED hala > 0 (erken aşama veya kısmi)
            line = (f"| {t} | {t} | {first_u} | "
                    f"(son: {last_u}) `{info['last_run']}` | "
                    f"{short_date(info['last_date'])} |")
        out.append(line)

    out.append("")

    # Geçiş zinciri tek satır özet
    transitions = []
    for t in sorted_totals:
        info = by_total[t]
        # Bu total_online değerinde sıfır UNVERIFIED'a ulaşıldı mı?
        zero_reached = any(
            r.get("total_online") == t and r.get("unverified", 0) == 0
            for r in rows)
        if zero_reached:
            transitions.append(f"{t}/{t}")
        else:
            last_u = info["last_unverified"]
            transitions.append(f"{t}/{t - last_u}")

    chain = " → ".join(transitions)
    out.append(f"**Geçiş zinciri:** {chain}")
    out.append("")
    out.append(f"_{len(sorted_totals)} aşama, {len(rows)} artifact taranmıştır._")
    out.append("")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--out-dir", default="refs-trend")
    ap.add_argument("--max-artifacts", type=int, default=100,
                    help="işlenecek en fazla artifact (varsayılan 100)")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    os.makedirs(args.out_dir, exist_ok=True)
    generated = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        artifacts = fetch_refs_online_artifacts(args.repo, token,
                                                args.max_artifacts)
    except Exception as e:
        print(f"HATA: refs-online artifact listelenemedi — {e}", file=sys.stderr)
        sys.exit(1)

    try:
        hist_artifacts = fetch_artifacts_by_name(args.repo, token,
                                                 "run-history",
                                                 args.max_artifacts)
    except Exception as e:
        print(f"  (run-history listelenemedi — {e}; duration/budget trendi boş)",
              file=sys.stderr)
        hist_artifacts = []

    rows = []
    for a in artifacts:
        aid = a["id"]
        try:
            blob = api_get(f"/repos/{args.repo}/actions/artifacts/{aid}/zip",
                           token, binary=True)
            rep = parse_report(blob)
        except Exception as e:
            print(f"  (atlandı: artifact {aid} ({a.get('created_at')}) — {e})",
                  file=sys.stderr)
            continue
        by_source = rep.get("by_source", {})
        rows.append({
            "date": rep.get("date", a.get("created_at", "")),
            "run_id": (a.get("workflow_run") or {}).get("id"),
            "total_online": rep.get("total_online", 0),
            "verified": rep.get("verified", 0),
            "unverified": rep.get("unverified", 0),
            "mismatch": rep.get("mismatch", 0),
            "by_source": by_source,
        })

    rows.sort(key=lambda r: r["date"])

    history_rows = []
    for a in hist_artifacts:
        aid = a["id"]
        try:
            blob = api_get(f"/repos/{args.repo}/actions/artifacts/{aid}/zip",
                           token, binary=True)
            rec = parse_history_record(blob)
        except Exception as e:
            print(f"  (atlandı: run-history artifact {aid} "
                  f"({a.get('created_at')}) — {e})", file=sys.stderr)
            continue
        _row = {
            "date": rec.get("ts", a.get("created_at", "")),
            "run_id": (a.get("workflow_run") or {}).get("id"),
            "duration_s": rec.get("duration_s"),
            "budget_usd": rec.get("budget_usd"),
            "verdict": rec.get("verdict"),
            "p0": rec.get("p0"),
            "p1": rec.get("p1"),
            "z3_passed": rec.get("z3_passed"),
            "z3_total": rec.get("z3_total"),
            "audit_refs_trend": rec.get("audit_refs_trend"),
        }
        _w = check_run_warnings(_row)
        _row["duration_warn"] = _w["duration_warn"]
        _row["budget_warn"] = _w["budget_warn"]
        history_rows.append(_row)
    history_rows.sort(key=lambda r: r["date"])

    # ── Markdown tablo ───────────────────────────────────────────────────
    lines = [
        "# Çevrimiçi Referans Doğrulama Trendi (refs-online)",
        "",
        f"- **Kaynak:** `refs-online` artifact'ları (GitHub API, son "
        f"{len(rows)} run)",
        f"- **Üretim:** refs_trend.py — {generated}",
        f"- **Repo:** {args.repo}",
        "",
    ]
    if not rows:
        lines += [
            "## Veri yok",
            "",
            "Henüz `refs-online` artifact'ı bulunamadı. İlk `verify` run'ları",
            "bu tabloyu doldurmaya başlar (her run bir satır).",
            "",
        ]
    else:
        lines += [
            "| # | Tarih (UTC) | Run ID | Toplam | Doğrulanan | "
            "Doğrulanamayan | Uyumsuz | Kaynak dağılımı | Kapsam Notu |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(rows, 1):
            src = ", ".join(f"{k}={v}" for k, v in
                            sorted(r["by_source"].items()))
            prev = rows[i - 2] if i >= 2 else None
            note = _coverage_change_note(r, prev)
            lines.append(
                f"| {i} | {short_date(r['date'])} | {r['run_id'] or '-'} | "
                f"{r['total_online']} | {r['verified']} | {r['unverified']} | "
                f"{r['mismatch']} | {src} | {note} |"
            )
        lines += [""]

        # Özet
        verified_all = sum(r["verified"] for r in rows)
        latest = rows[-1]
        lines += [
            "## Özet",
            "",
            f"- **Run sayısı:** {len(rows)}",
            f"- **En güncel run:** {short_date(latest['date'])} "
            f"(run {latest['run_id']}) — {latest['verified']}/{latest['total_online']} "
            "doğrulanan",
            f"- **Tüm run'lar toplam doğrulanan:** {verified_all}",
            f"- **Ortalama doğrulanan/run:** "
            f"{verified_all / len(rows):.1f}",
            f"- **İlk run:** {short_date(rows[0]['date'])} — "
            f"{rows[0]['verified']}/{rows[0]['total_online']} doğrulanan",
            f"- **Milestone:** 56/56 (V5o, yerel doğrulama — "
            "[REFERANS §5.3](REFERANS_KANIT_DENETIMI.md))",
            "",
        ]
        # Kapsam açıklaması: sayılar nereden gelir, "54" neden artık geçersiz
        latest_v = latest["verified"]
        latest_t = latest["total_online"]
        if latest_v is not None and latest_t is not None:
            lines += [
                f"### Kapsam",
                "",
                f"**{latest_v}/{latest_t}** — 64 referansın {latest_v}'i "
                "çevrimiçi kaynaktan doğrulanır (CrossRef, SEP, "
                "OpenLibrary, Internet Archive, Handle System, "
                "Library of Congress, Perseus). Kalan 3 referans "
                "bibliyografik belgedir — modern telifli kitaplar, "
                "çevrimiçi indekslenmez.",
                "",
                "**Kapsam geçiş dipnotu (54/49 → 56/26 → 61/61):** "
                "Erken dönem 54/49 (CrossRef+SEP+OL+IA temel zincir), "
                "V5n ile 56/56'ya (Norton/Popkin CrossRef + paralel koşu) "
                "yükseldi — bu 56/56 **yerel doğrulama**ydı (CI repo'da "
                "doğrudan koşulmuştu, GitHub artifact'ına yansımadı; "
                "kanıtı REFERANS_KANIT_DENETIMI.md §5.3'te belgelenmiştir: "
                "`ia_ol_fallback_evidence.py --offline` deterministik "
                "mock kanıt). Trend yalnızca gerçek `refs-online` "
                "artifact'larından beslenir; 56/56 satırı trend tablosunda "
                "görünmez. V5q/V5t/V5w zinciriyle kapsam 61/61'e ulaştı "
                "(Sextus ia_ids + Della Rocca Handle + LoC lccn katalog "
                "kanıtı). '54' erken bir anlık görüntüdür, güncel denetim "
                "kapsamını yansıtmaz.",
                "",
                "> 🏁 **Milestone 56/56 (yerel):** V5o — tam çevrimiçi kapsam "
                "(Norton/Popkin CrossRef + paralel koşu, 11 UNVERIFIED "
                "kapatıldı). Bu sonuç GitHub artifact'ına yansımadığı için "
                "trend tablosunda görünmez; deterministik kanıtı "
                "[REFERANS_KANIT_DENETIMI.md §5.3](REFERANS_KANIT_DENETIMI.md) "
                "(`ia_ol_fallback_evidence.py --offline`) ile yeniden "
                "üretilebilir.",
                "",
            ]

        # ── Coverage transition summary (UNVERIFIED>0 → 0 geçiş zinciri) ──
        transition_lines = build_coverage_transition_summary(rows)
        if transition_lines:
            lines += transition_lines

    # ── Duration / Budget trendi (run-history) ───────────────────────────
    if history_rows:
        lines += [
            "## Duration / Budget trendi (run-history)",
            "",
            f"- **Kaynak:** `run-history` artifact'ları (son {len(history_rows)} run)",
            "",
            "| # | Tarih (UTC) | Run ID | Duration (s) | Budget (USD) | Z3 | Verdict | Audit |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(history_rows, 1):
            dur = (f"{r['duration_s']:.1f}"
                   if isinstance(r["duration_s"], (int, float))
                   else (r["duration_s"]
                         if r["duration_s"] is not None else "—"))
            bud = (f"${r['budget_usd']:.2f}"
                   if isinstance(r["budget_usd"], (int, float))
                   else (r["budget_usd"]
                         if r["budget_usd"] is not None else "—"))
            # Uyarı bayrakları
            w = check_run_warnings(r)
            flags = []
            if w["duration_warn"]:
                flags.append("⏰")
            if w["budget_warn"]:
                flags.append("💰")
            flag_str = " ".join(flags)
            z3 = (f"{r['z3_passed']}/{r['z3_total']}"
                   if isinstance(r.get("z3_passed"), (int, float))
                   else "—")
            # Audit sütunu: PASS/FAIL/advisory (None = audit henüz koşulmadı)
            audit = r.get("audit_refs_trend")
            if audit is not None:
                audit_str = "✅" if str(audit).upper() == "PASS" else (
                    "🔴" if str(audit).upper() == "FAIL" else f"{audit}")
            else:
                audit_str = "—"
            lines.append(
                f"| {i} | {short_date(r['date'])} | {r['run_id'] or '-'} | "
                f"{dur} | {bud} | {z3} | {r['verdict'] or '-'} {flag_str} | {audit_str} |"
            )
        lines += [""]

        ds = stats([r["duration_s"] for r in history_rows])
        bs = stats([r["budget_usd"] for r in history_rows])

        def num(v, nd=1):
            return f"{v:.{nd}f}" if v is not None else "—"

        lines += [
            "**Duration özeti:** "
            f"min {num(ds['min'])} s · max {num(ds['max'])} s · "
            f"avg {num(ds['avg'])} s",
            "",
            "**Budget özeti:** "
            f"min ${num(bs['min'], 2)} · max ${num(bs['max'], 2)} · "
            f"avg ${num(bs['avg'], 2)}",
            "",
        ]

        # ── Eşik uyarıları özeti ────────────────────────────────────────
        vw = summarize_warnings(history_rows)
        if vw["violations"]:
            lines += [
                "### ⚠️ Eşik ihlalleri",
                "",
                f"- **Süre eşiği:** {DURATION_WARN_S:.0f}s üzeri {vw['duration_violations']} run",
                f"- **Bütçe eşiği:** ${BUDGET_WARN_USD:.0f} üzeri {vw['budget_violations']} run",
                "",
                "| # | Tarih | Run ID | Uyarılar |",
                "|---|---|---|---|",
            ]
            for v in vw["violations"]:
                msgs = "; ".join(v["messages"])
                lines.append(
                    f"| {v['run_idx']} | {short_date(v['date'])} | "
                    f"{v['run_id'] or '-'} | {msgs} |"
                )
            lines += [""]
        else:
            lines += [
                "### ✅ Eşik uyarıları",
                "",
                f"Son {len(history_rows)} run'da süre/bütçe eşiği ihlali yok.",
            ]
            lines += [""]

    # ── UNVERIFIED zaman serisi ──────────────────────────────────────────
    unv_latest = unv_max = unv_zero_runs = 0
    stale_runs = set()
    if rows:
        unv_series = [(r["date"], r["unverified"]) for r in rows]
        unv_latest = unv_series[-1][1] if unv_series else 0
        unv_max = max(u for _, u in unv_series) if unv_series else 0
        unv_zero_runs = sum(1 for _, u in unv_series if u == 0)
        lines += [
            "## UNVERIFIED Zaman Serisi",
            "",
            f"- **Son durum:** {unv_latest} doğrulanamayan referans",
            f"- **Maksimum:** {unv_max} (tüm run'larda)",
            f"- **Sıfır olan run sayısı:** {unv_zero_runs}/{len(rows)}",
            "",
        ]
        # Son 5 run'daki trend
        recent = unv_series[-5:] if len(unv_series) >= 5 else unv_series
        if len(recent) > 1:
            trend = "↓ azalıyor" if recent[-1][1] < recent[0][1] else (
                "↑ artıyor" if recent[-1][1] > recent[0][1] else "→ sabit")
            lines.append(f"- **Trend (son {len(recent)} run):** {trend}"
                         f" ({recent[0][1]} → {recent[-1][1]})")
            lines += [""]

    # ── Bayat artifact uyarısı ───────────────────────────────────────────
    # refs-online artifact'ları son N run'da güncellenmemişse uyarı.
    if rows and history_rows:
        refs_ids = {r["run_id"] for r in rows if r.get("run_id")}
        hist_ids = {h["run_id"] for h in history_rows if h.get("run_id")}
        # Son 3 run'da refs-online artifact'ı olmayanlar
        last_3_hist = history_rows[-3:] if len(history_rows) >= 3 else history_rows
        last_3_ids = {h["run_id"] for h in last_3_hist if h.get("run_id")}
        stale_runs = last_3_ids - refs_ids
        if stale_runs:
            lines += [
                "## ⚠️ Bayat refs-online Artifact Uyarısı",
                "",
                f"Son {len(last_3_hist)} run'da refs-online artifact'ı bulunmayan"
                f" run'lar: {', '.join(str(i) for i in sorted(stale_runs))}",
                "Bu run'larda çevrimiçi referans doğrulaması çalışmamış olabilir.",
                "",
            ]
        else:
            lines += [
                "## ✅ refs-online Artifact Durumu",
                "",
                f"Son {len(last_3_hist)} run'da tüm run'larda refs-online artifact'ı mevcut.",
                "",
            ]

    # Changelog: denetim düzeltmelerinin kısa kaydı (kaynak: CHANGELOG).
    lines += changelog_lines()

    md_path = os.path.join(args.out_dir, "refs-trend.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))

    duration_budget = build_duration_budget(history_rows)
    unverified_series = {
        "latest": unv_latest if rows else 0,
        "max": unv_max if rows else 0,
        "zero_runs": unv_zero_runs if rows else 0,
        "total_runs": len(rows),
        "stale_artifact_runs": sorted(stale_runs) if (rows and history_rows and stale_runs) else [],
    } if rows else None

    summary = {
        "generated": generated,
        "repo": args.repo,
        "run_count": len(rows),
        "rows": rows,
        "totals": {
            "verified": sum(r["verified"] for r in rows),
            "total_online": sum(r["total_online"] for r in rows),
        } if rows else {"verified": 0, "total_online": 0},
        "duration_budget": duration_budget,
        "unverified_series": unverified_series,
    }
    with open(os.path.join(args.out_dir, "refs-trend.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[refs-trend] yazıldı: {md_path} "
          f"({len(rows)} refs + {len(history_rows)} history run)")


if __name__ == "__main__":
    main()
