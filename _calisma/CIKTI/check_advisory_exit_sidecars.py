#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_advisory_exit_sidecars.py — advisory adımların exit sidecar'ı ZORUNLU.

Kök neden (bu depoda ölçülmüş gerçek olay): `shell: bash` altında adım
`bash -eo pipefail` ile koşar. `continue-on-error: true` olan bir advisory
adımında gate komutu düştüğünde errexit bir SONRAKİ satırı çalıştırmaz;
yani `status=$?` hiç koşmaz, `echo "$status" > logs/X.exit` YAZILMAZ ve
rapora düşen "exit code: N" bloğu hiç oluşmaz. Job `continue-on-error`
sayesinde YEŞİL kalır — karar sessizce kaybolur. Aynı sınıf hata, adım
çökerse/atlanırsa da oluşur (verdict dosyası yok, kimse fark etmez).

Bu kapı iki modda çalışır ve ikisi de fail-closed'dır:

  1) ÇALIŞMA-ZAMANI (varsayılan, `--dir logs`): kayıtlı her sidecar
     (`logs/*.exit`) dosyada VAR mı, içeriği geçerli bir exit kodu mu
     (0..255 tamsayı) diye bakar. Eksik/boş/ayrıştırılamaz dosya = FAIL
     ("gate kararı kayboldu"). Dosya DEĞERİ (0 veya ≠0) bu kapının
     konusu değildir — o gate'in kendi verdict'idir; burada yalnız
     verdict'in *kanıtı* aranır.

  2) STATİK (`--workflow .github/workflows/verify.yml`): kayıtlı her
     sidecar'ın workflow'da TAM OLARAK BİR yazıcı adımı olmalı; adım
     advisory (`continue-on-error` + `if: always()`) olmalı ve yazıcı
     errexit-güvenli olmalı (`set +e` … `status=$?` ya da K12/K13
     deseni: `if …; then status=0; else status=$?; fi`). Ayrıca
     workflow'da yazılan her `*.exit` sidecar'ı kayıtlı olmalıdır —
     yeni bir sidecar sessizce izlenmeden eklenemez.

Kullanım:
    python3 check_advisory_exit_sidecars.py                 # logs/ runtime
    python3 check_advisory_exit_sidecars.py --dir logs --json
    python3 check_advisory_exit_sidecars.py --workflow .github/workflows/verify.yml
    python3 check_advisory_exit_sidecars.py --dir logs \
        --workflow .github/workflows/verify.yml --json-out logs/advisory_sidecars.json
    python3 check_advisory_exit_sidecars.py --expect precommit   # kısmi koşum

Exit: 0 = PASS, 1 = FAIL (eksik/geçersiz sidecar veya workflow sözleşmesi
ihlali), 2 = kullanım/ortam hatası (workflow dosyası yok, PyYAML yok, ...).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Kayıt TEK KAYNAK: sidecar adı → dosya + onu üreten adımın kimliği.
# Yeni bir advisory `.exit` sidecar'ı ekleyen herkes buraya da eklemek
# zorundadır; statik mod kayıtsız yazıcıyı FAIL eder (fail-closed).
SIDECARS = (
    {
        "name": "precommit",
        "path": "logs/precommit.exit",
        "step": "Run pre-commit (advisory, all files, show diff on failure)",
    },
    {
        "name": "k13_repro_manifest",
        "path": "logs/k13_repro_manifest.exit",
        "step": "Run verify-delivery-repro-manifest (K13, separate)",
    },
    {
        "name": "k12_repro_manifest",
        "path": "logs/k12_repro_manifest.exit",
        "step": "Run K12 scenarios (K13 pattern)",
    },
    {
        "name": "check_unit_tests",
        "path": "logs/check_unit_tests.exit",
        "step": "Run check-unit-tests hook (separate)",
    },
)

# `... > logs/x.exit` / `> "logs/x.exit"` biçimindeki yazımlar.
WRITE_RE = re.compile(r">\s*\"?([A-Za-z0-9_./-]+\.exit)\"?")
# Geçerli kabuk exit kodu aralığı.
EXIT_CODE_RE = re.compile(r"^-?\d+$")
MAX_EXIT_CODE = 255


def strip_comments(text: str) -> str:
    """Yorum satırlarını at (statik analiz yalnız çalışan satırları görsün)."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def errexit_safe(run: str) -> bool:
    """Yazıcı adım errexit'e rağmen `status`'ü yakalıyor mu?

    İki meşru desen var (ikisi de bu depoda kullanılıyor):
      A) `set +e` → komut → `status=$?` → `set -e`
      B) `if komut; then status=0; else status=$?; fi`
    Başka her şey (çıplak komut + `status=$?`) errexit altında sidecar'ı
    yazmadan ölür — tam olarak bu kapının engellediği hata.
    """
    body = strip_comments(run)
    if "status=$?" not in body:
        return False
    plus_e = re.search(r"(?m)^\s*set\s+\+e\b", body)
    if plus_e:
        return plus_e.start() < body.index("status=$?")
    has_if = re.search(r"(?m)^\s*if\b", body)
    has_else = re.search(r"(?m)^\s*else\s*$", body)
    if has_if and has_else:
        return has_if.start() < body.index("status=$?")
    return False


def is_advisory(step: dict) -> bool:
    cont = step.get("continue-on-error")
    truthy = cont is True or (isinstance(cont, str)
                              and cont.strip().lower() in ("true", "${{ true }}"))
    cond = step.get("if")
    always = isinstance(cond, str) and "always()" in cond
    return truthy and always


def load_workflow(path: Path):
    try:
        import yaml  # noqa: WPS433 (opsiyonel bağımlılık, açık hata mesajı)
    except ImportError as exc:  # pragma: no cover - ortam hatası
        raise SystemExit(f"PyYAML gerekli (statik mod): {exc}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: workflow YAML sözlüğü değil")
    return data


def workflow_steps(data: dict):
    """(job_id, index, step) üçlüleri — tüm işler, sıralı."""
    for job_id, job in (data.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for idx, step in enumerate(job.get("steps") or []):
            if isinstance(step, dict):
                yield job_id, idx, step


def check_static(path: Path, registry, findings, known_paths=None):
    """Statik sözleşme: `registry` denetlenir, `known_paths` kayıtlı sayılır.

    `--expect` ile kısmi koşumda yalnız seçilen sidecar'lar denetlenir; ama
    workflow'daki DİĞER bilinen `.exit` yazıcıları "kayıtsız" sayılmamalı.
    """
    data = load_workflow(path)
    writers: dict[str, list] = {}
    for job_id, idx, step in workflow_steps(data):
        run = step.get("run")
        if not isinstance(run, str):
            continue
        # Yorum satırlarındaki örnekler yazıcı sayılmasın (yalnız çalışan satır).
        for match in WRITE_RE.finditer(strip_comments(run)):
            writers.setdefault(match.group(1), []).append((job_id, idx, step))

    if known_paths is None:
        known_paths = {entry["path"] for entry in SIDECARS}
    details = []

    for entry in registry:
        sidecar_path = entry["path"]
        found = writers.get(sidecar_path, [])
        label = entry["name"]
        if not found:
            findings.append({
                "kind": "no-writer", "sidecar": label, "path": sidecar_path,
                "workflow": path.name,
                "detail": f"{sidecar_path} hiçbir adımda yazılmıyor — kayıt bayat",
            })
            details.append({"name": label, "path": sidecar_path,
                            "status": "no-writer"})
            continue
        if len(found) > 1:
            findings.append({
                "kind": "ambiguous-writer", "sidecar": label,
                "path": sidecar_path, "workflow": path.name,
                "detail": (f"{sidecar_path} {len(found)} adımda yazılıyor "
                           f"({', '.join(str(s.get('name')) for _, _, s in found)})"),
            })
            details.append({"name": label, "path": sidecar_path,
                            "status": "ambiguous-writer"})
            continue

        job_id, idx, step = found[0]
        step_name = step.get("name") or f"{job_id}#{idx}"
        run = step.get("run") or ""
        problems = []
        if not errexit_safe(run):
            problems.append(
                "errexit-güvensiz yazıcı (set +e/if-else yok) — komut düşerse "
                "sidecar yazılmadan adım ölür"
            )
        if not is_advisory(step):
            problems.append("adım advisory değil (continue-on-error + if: always())")
        if entry["step"] != step_name:
            problems.append(
                f"kayıtlı adım adı uyuşmuyor (kayıt: {entry['step']!r}, "
                f"workflow: {step_name!r})"
            )
        if problems:
            findings.append({
                "kind": "unsafe-writer", "sidecar": label, "path": sidecar_path,
                "workflow": path.name, "step": step_name,
                "detail": "; ".join(problems),
            })
            details.append({"name": label, "path": sidecar_path,
                            "status": "unsafe-writer", "step": step_name})
        else:
            details.append({"name": label, "path": sidecar_path,
                            "status": "ok", "step": step_name})

    for written in sorted(writers):
        if written not in known_paths:
            findings.append({
                "kind": "unregistered-writer", "sidecar": None, "path": written,
                "workflow": path.name,
                "detail": (f"{written} yazılıyor ama SIDECARS kaydında yok — "
                           "izlenmeyen verdict kabul edilmez"),
            })
            details.append({"name": None, "path": written,
                            "status": "unregistered", "workflow": path.name})

    return details


def check_runtime(directory: Path, registry):
    details = []
    for entry in registry:
        target = directory / Path(entry["path"]).name
        label = entry["name"]
        if not target.exists():
            details.append({
                "name": label, "path": str(target), "status": "missing",
                "detail": ("gate kararı kayboldu: dosya yok (errexit/çökme/"
                           "adım atlandı). Verdict ÜRETİLMEDİ — PASS sayılmaz."),
            })
            continue
        try:
            raw = target.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            details.append({"name": label, "path": str(target),
                            "status": "invalid",
                            "detail": f"okunamadı: {exc}"})
            continue
        if not raw:
            details.append({"name": label, "path": str(target),
                            "status": "invalid",
                            "detail": "dosya boş — exit kodu yazılmadı"})
            continue
        if not EXIT_CODE_RE.match(raw):
            details.append({"name": label, "path": str(target),
                            "status": "invalid",
                            "detail": f"exit kodu değil: {raw[:40]!r}"})
            continue
        code = int(raw)
        if code < 0 or code > MAX_EXIT_CODE:
            details.append({"name": label, "path": str(target),
                            "status": "invalid",
                            "detail": f"exit kodu aralık dışı (0..{MAX_EXIT_CODE}): {code}"})
            continue
        details.append({"name": label, "path": str(target), "status": "ok",
                        "code": code})
    return details


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def build_report(args, registry):
    findings: list[dict] = []
    modes: dict[str, list] = {}

    if args.dir:
        directory = Path(args.dir)
        if not directory.is_dir():
            raise SystemExit(f"--dir dizin değil: {args.dir}")
        modes["runtime"] = check_runtime(directory, registry)

    for wf in args.workflow or []:
        path = Path(wf)
        if not path.is_file():
            raise SystemExit(f"--workflow dosyası yok: {wf}")
        modes.setdefault("static", []).extend(
            check_static(path, registry, findings))

    for mode, details in modes.items():
        for item in details:
            if item["status"] == "ok":
                continue
            if item["status"] == "invalid" or item["status"] == "missing":
                findings.append({
                    "kind": "missing-sidecar" if item["status"] == "missing"
                            else "invalid-sidecar",
                    "sidecar": item["name"], "path": item["path"],
                    "detail": item.get("detail", ""),
                })

    verdict = "PASS" if not findings else "FAIL"
    return {
        "verdict": verdict,
        "modes": sorted(modes),
        "expected": [entry["name"] for entry in registry],
        "details": modes,
        "findings": findings,
        "missing": sorted({f["sidecar"] for f in findings
                           if f["kind"] == "missing-sidecar"
                           and f["sidecar"] is not None}),
        "invalid": sorted({f["sidecar"] for f in findings
                           if f["kind"] == "invalid-sidecar"
                           and f["sidecar"] is not None}),
    }


def render_text(report) -> str:
    lines = [f"ADVISORY EXIT SIDECAR DENETİMİ — {report['verdict']} "
             f"(modlar: {', '.join(report['modes'])})"]
    for mode in report["modes"]:
        lines.append(f"\n[{mode}]")
        for item in report["details"][mode]:
            mark = "✅" if item["status"] == "ok" else "❌"
            code = f" exit={item['code']}" if "code" in item else ""
            step = f" ← {item['step']}" if "step" in item else ""
            lines.append(f"  {mark} {item['name'] or '-'}: {item['path']}"
                         f" [{item['status']}{code}]{step}")
    if report["findings"]:
        lines.append("\nSORUNLAR:")
        for finding in report["findings"]:
            lines.append(f"  - [{finding['kind']}] {finding['detail']}")
    if report["missing"]:
        lines.append("\nKAYBOLAN VERDICT'LER: " + ", ".join(report["missing"]))
        lines.append("  → errexit yutmuş olabilir: yazıcı adımda `set +e`/`if-else` "
                     "kalıbına geç ve adımın gerçekten koştuğunu doğrula.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Advisory adımların exit sidecar'larını denetle (fail-closed)")
    parser.add_argument("--dir", default="logs",
                        help="runtime modu: exit dosyalarının dizini (varsayılan: logs)")
    parser.add_argument("--workflow", action="append", default=[],
                        help="statik modu: workflow dosyası (birden çok kez verilebilir)")
    parser.add_argument("--expect", default=None,
                        help="kısmi koşum: yalnız bu virgülle ayrılmış sidecar adları")
    parser.add_argument("--json", action="store_true", help="stdout: tek JSON belgesi")
    parser.add_argument("--json-out", default=None,
                        help="JSON raporunu bu yola yaz (stdout insan-okur kalır)")
    args = parser.parse_args(argv)

    registry = SIDECARS
    if args.expect:
        wanted = [name.strip() for name in args.expect.split(",") if name.strip()]
        known = {entry["name"] for entry in SIDECARS}
        unknown = [name for name in wanted if name not in known]
        if unknown:
            print(f"Bilinmeyen sidecar adı: {', '.join(unknown)}", file=sys.stderr)
            return 2
        registry = tuple(entry for entry in SIDECARS if entry["name"] in wanted)

    report = build_report(args, registry)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"

    if args.json_out:
        atomic_write(Path(args.json_out), payload)
    if args.json:
        sys.stdout.write(payload)
    else:
        print(render_text(report))
        if args.json_out:
            print(f"\nJSON: {args.json_out}")

    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
