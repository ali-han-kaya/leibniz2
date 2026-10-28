#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""npm_audit_gate.py — npm audit ZORUNLU eşik kapısı (Node çalışma alanları).

Sözleşme: her kayıtlı npm çalışma alanında `npm audit` çıktısındaki
vulnerability sayıları eşiğe vurulur; eşiğe eşit/daha ağır bir bulgu varsa
kapı **exit 1** verir. Kapsam `npm_workspaces.py`'den gelir — floor/hijyen
sözleşmesini denetleyen testle AYNI küme (tek kaynak): aksi hâlde gate'in
sessizce atladığı bir çalışma alanı "denetlendi" sanılırdı.

Eşik (`--level`, varsayılan `NPM_AUDIT_GATE_LEVEL` env'i, yoksa `high`):

    critical → yalnız CRITICAL bloklar
    high     → CRITICAL + HIGH bloklar (varsayılan)
    moderate → CRITICAL + HIGH + MODERATE
    low      → hepsi

Üç durum, üç ayrı gerekçe (karıştırılmamalı):

  PASS   — ölçüm yapıldı, eşiğe eşit/ağır bulgu yok.
  FAIL   — ölçüm yapıldı, eşiğe eşit/ağır bulgu var.
  SKIP   — ölçüm YAPILAMADI (npm yok, registry/audit endpoint'ine
           ulaşılamadı). Çıktı bunu açıkça yazar; `--require-real` (CI)
           SKIP'i FAIL'e çevirir — CI'da npm kurulu olduğu için SKIP artık
           "ortam yok" değil, **kapının sessizce körleştiği** anlamına gelir.

Neden `--package-lock-only`: audit, lockfile'daki çözülmüş ağaca bakar;
node_modules gerekmez (CI'da `npm ci` maliyeti yok, yerelde de hızlı).

Kullanım:
  python3 _calisma/CIKTI/npm_audit_gate.py --require-real
  python3 _calisma/CIKTI/npm_audit_gate.py --level critical --json
  python3 _calisma/CIKTI/npm_audit_gate.py --audit-json /tmp/fixtures   # offline
  NPM_AUDIT_GATE_LEVEL=high python3 _calisma/CIKTI/npm_audit_gate.py

Çıkış kodları:
  0 — tüm çalışma alanları PASS (ya da SKIP ve `--require-real` yok)
  1 — en az bir FAIL, veya SKIP + `--require-real`
  2 — kullanım hatası (geçersiz seviye)

stdlib-only. `--audit-json` dışında ağa/npm'e bağımlıdır.
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import npm_workspaces  # noqa: E402 — kardeş modül (yol yukarıda eklendi)

LEVELS = ("low", "moderate", "high", "critical")
DEFAULT_LEVEL = "high"


def resolve_level(cli_level=None):
    """Eşiği çöz: CLI > env (`NPM_AUDIT_GATE_LEVEL`) > varsayılan.

    Workflow eşiği `env:` bloğunda TEK yerde tutar; script aynı değeri
    ortamdan okur — böylece eşik ikinci bir literal olarak sürüklenmez.
    """
    level = (cli_level or os.environ.get("NPM_AUDIT_GATE_LEVEL")
             or DEFAULT_LEVEL).strip().lower()
    if level not in LEVELS:
        sys.stderr.write("HATA: geçersiz seviye %r — biri olmalı: %s\n"
                         % (level, ", ".join(LEVELS)))
        raise SystemExit(2)
    return level


def blocking_severities(level):
    """Eşiğe eşit ya da daha ağır severity'ler (npm `--audit-level` semantiği)."""
    return tuple(LEVELS[LEVELS.index(level):])


def summarize(report, level):
    """npm audit JSON'u → eşik kararı.

    `metadata.vulnerabilities` severity başına sayı taşır (npm ≥ 7).
    Eksik anahtar 0 sayılır — "bilinmiyor" değil: npm bu alanı her raporda
    doldurur, eksikliği ancak bozuk bir rapor üretir (o yol SKIP'e düşer).
    """
    vulns = ((report or {}).get("metadata") or {}).get("vulnerabilities") or {}
    blocking = {sev: int(vulns.get(sev, 0) or 0)
                for sev in blocking_severities(level)}
    total = sum(blocking.values())
    return {
        "blocking": blocking,
        "blocking_total": total,
        "counts": {sev: int(vulns.get(sev, 0) or 0)
                   for sev in ("critical", "high", "moderate", "low")},
        "verdict": "FAIL" if total else "PASS",
    }


def _fixture_path(fixture_dir, workspace):
    slug = workspace.replace("/", "__")
    return pathlib.Path(fixture_dir) / (slug + ".json")


def run_audit(workspace, level, fixture_dir=None):
    """Tek çalışma alanı için (report, mode, detail) döndürür.

    report None ise ölçüm yapılmamıştır (mode == "SKIP").
    """
    if fixture_dir:
        path = _fixture_path(fixture_dir, workspace)
        if not path.is_file():
            return None, "SKIP", "fixture yok: %s" % path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return None, "SKIP", "fixture okunamadı: %s" % exc
        if not isinstance(data, dict) or "metadata" not in data:
            return None, "SKIP", "fixture'da metadata yok"
        return data, "fixture", ""

    npm = shutil.which("npm")
    if not npm:
        return None, "SKIP", "npm yok (PATH'te bulunamadı)"
    cmd = [npm, "audit", "--package-lock-only", "--json",
           "--audit-level=%s" % level]
    try:
        proc = subprocess.run(cmd, cwd=str(npm_workspaces.ROOT / workspace),
                              capture_output=True, text=True, timeout=240)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "SKIP", "npm audit çalıştırılamadı: %s" % exc
    try:
        data = json.loads(proc.stdout or "")
    except ValueError:
        first = (proc.stderr or proc.stdout or "").strip().splitlines()
        return None, "SKIP", "audit JSON üretmedi: %s" % (
            first[0] if first else "çıktı boş")
    if not isinstance(data, dict) or "metadata" not in data:
        err = (data or {}).get("error") if isinstance(data, dict) else None
        summary = (err or {}).get("summary") if isinstance(err, dict) else None
        return None, "SKIP", "audit raporu eksik (metadata yok): %s" % (
            summary or "registry/audit endpoint erişilemez olabilir")
    return data, "npm", ""


def gate(workspaces, level, fixture_dir=None):
    results = []
    for ws in workspaces:
        report, mode, detail = run_audit(ws, level, fixture_dir)
        if report is None:
            results.append({"workspace": ws, "verdict": "SKIP", "mode": mode,
                            "detail": detail, "blocking": {}, "counts": {}})
            continue
        verdict = summarize(report, level)
        results.append({"workspace": ws, "verdict": verdict["verdict"],
                        "mode": mode, "detail": "",
                        "blocking": verdict["blocking"],
                        "blocking_total": verdict["blocking_total"],
                        "counts": verdict["counts"]})
    skipped = [r["workspace"] for r in results if r["verdict"] == "SKIP"]
    failed = [r["workspace"] for r in results if r["verdict"] == "FAIL"]
    if failed:
        verdict, reason = "FAIL", "blocking-findings"
    elif skipped and len(skipped) == len(results):
        # Hiçbir çalışma alanı ölçülemedi: "PASS" yazmak ölçüm yokluğunu
        # kanıt gibi gösterirdi. SKIP dürüst olanı söyler.
        verdict, reason = "SKIP", "skip-only"
    elif skipped:
        verdict, reason = "PASS", "partial-skip"
    else:
        verdict, reason = "PASS", "clean"
    return {"level": level, "workspaces": results,
            "skipped": skipped, "failed": failed,
            "verdict": verdict, "verdict_reason": reason}


def apply_require_real(result):
    """SKIP'i CI'da FAIL'e çevir (kanıt satırı ile çıkış kodu aynı şeyi desin)."""
    if result.get("require_real") and result["skipped"] \
            and result["verdict_reason"] != "blocking-findings":
        result["verdict"] = "FAIL"
        result["verdict_reason"] = "skip-with-require-real"
    return result


def render_evidence(result):
    """İnsan/log kanıtı: çalışma alanı başına tek satır + son verdict satırı."""
    sevs = ",".join(blocking_severities(result["level"]))
    lines = []
    for row in result["workspaces"]:
        if row["verdict"] == "SKIP":
            lines.append("workspace=%s verdict=SKIP level=%s (%s)"
                         % (row["workspace"], result["level"], row["detail"]))
            continue
        counts = " ".join("%s=%d" % (sev, row["counts"].get(sev, 0))
                          for sev in ("critical", "high", "moderate", "low"))
        lines.append("workspace=%s verdict=%s level=%s blocking=[%s] %s "
                     "mode=%s" % (row["workspace"], row["verdict"],
                                  result["level"], sevs, counts, row["mode"]))
    lines.append("verdict=%s level=%s workspaces=%d skipped=%d failed=%d "
                 "reason=%s"
                 % (result["verdict"], result["level"],
                    len(result["workspaces"]), len(result["skipped"]),
                    len(result["failed"]), result["verdict_reason"]))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description="npm audit eşik kapısı")
    ap.add_argument("--level", choices=LEVELS, default=None,
                    help="bloklama eşiği (varsayılan: NPM_AUDIT_GATE_LEVEL "
                         "env'i, yoksa 'high')")
    ap.add_argument("--workspace", action="append", dest="workspaces",
                    default=None, metavar="DIR",
                    help="taranacak dizin (tekrarlanabilir; varsayılan: "
                         "npm_workspaces kaydındaki mevcut alanlar)")
    ap.add_argument("--require-real", action="store_true",
                    help="SKIP'i FAIL say (CI: ölçüm yapılamadıysa kapı kırmızı)")
    ap.add_argument("--report", default=None, metavar="PATH",
                    help="kanıt satırlarını bu dosyaya da yaz")
    ap.add_argument("--audit-json", default=None, metavar="DIR",
                    help="offline mod: DIR/<workspace slug>.json fixture'larını "
                         "oku (npm çalıştırılmaz — test/probe için)")
    ap.add_argument("--json", action="store_true",
                    help="stdout'a tek JSON dokümanı yaz (tanı satırları stderr)")
    ap.add_argument("--json-out", default=None, metavar="PATH",
                    help="JSON çıktısını dosyaya yaz (JSON modunu açar)")
    args = ap.parse_args(argv)

    level = resolve_level(args.level)
    workspaces = args.workspaces or npm_workspaces.present_workspaces()
    if not workspaces:
        sys.stderr.write("HATA: taranacak çalışma alanı yok\n")
        return 2

    result = gate(workspaces, level, args.audit_json)
    result["require_real"] = bool(args.require_real)
    apply_require_real(result)

    evidence = render_evidence(result)
    json_mode = bool(args.json or args.json_out)
    # JSON modu: stdout TEK doküman kalır — kanıt satırları stderr'e gider.
    stream = sys.stderr if json_mode else sys.stdout
    for line in evidence:
        stream.write(line + "\n")
    if args.report:
        path = pathlib.Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(evidence) + "\n", encoding="utf-8")

    if json_mode:
        doc = json.dumps(result, indent=2, sort_keys=True)
        if args.json_out:
            path = pathlib.Path(args.json_out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(doc + "\n", encoding="utf-8")
        if args.json:
            sys.stdout.write(doc + "\n")

    if result["failed"]:
        sys.stderr.write("FAIL: eşiğe eşit/ağır bulgu: %s\n"
                         % ", ".join(result["failed"]))
    elif result["verdict_reason"] == "skip-with-require-real":
        sys.stderr.write("FAIL: ölçüm yapılamadı (SKIP) ve --require-real "
                         "verildi: %s\n" % ", ".join(result["skipped"]))
    return 1 if result["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
