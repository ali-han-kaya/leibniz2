#!/usr/bin/env python3
"""gen_precommit_report.py — pre-commit çıktısını PRECOMMIT_RAPORU.md'ye çevir.

verify.yml'deki 'Generate pre-commit findings report' adımının inline Python
mantığının standalone hali (gen_repro_manifest.py deseni): aynı kod hem CI'da
hem yerelde çalışır → CI ile yerel arasında drift olmaz.

Girdi : logs/precommit.log   (pre-commit run --all-files çıktısı)
        logs/precommit.exit  (exit kodu)
Çıktı : logs/PRECOMMIT_RAPORU.md (hook sonuçları + P0/P1 bulguları + ham log notu)

Kullanım (CI çalışma dizininden — logs/ altı hazır olmalı):
  python3 gen_precommit_report.py
"""
import datetime
import pathlib
import re


def main() -> None:
    log = pathlib.Path("logs/precommit.log")
    log_text = (log.read_text(encoding="utf-8", errors="replace")
                if log.exists() else "")
    try:
        exit_code = int(pathlib.Path("logs/precommit.exit").read_text().strip())
    except Exception:
        exit_code = 1

    hooks = [
        {"name": m.group(1).strip(), "status": m.group(2)}
        for m in re.finditer(r"^(.*?)\.{4,}(Passed|Failed)\s*$", log_text, re.M)
    ]
    findings = []
    for pri in ("P0", "P1"):
        for m in re.finditer(rf"^\[{pri}\] (.+)$", log_text, re.M):
            findings.append((pri, m.group(1).strip()))

    now = datetime.datetime.utcnow().isoformat() + "Z"
    verdict = "PASS" if exit_code == 0 else "FAIL"
    lines = [
        "# PRECOMMIT DENETİM RAPORU (CI advisory)",
        "",
        f"- **Tarih (UTC):** {now}",
        "- **Komut:** `pre-commit run --all-files --show-diff-on-failure`",
        f"- **Sonuç:** {verdict} (exit {exit_code})",
        "- **Rol:** advisory — build'i bloke etmez; bulgular denetim içindir.",
        "",
        "## Hook sonuçları",
        "",
        "| Hook | Durum |",
        "|---|---|",
    ]
    if hooks:
        for h in hooks:
            lines.append(f"| {h['name']} | {h['status']} |")
    else:
        lines.append("| (hook sonucu ayrıştırılamadı) | — |")

    lines += ["", "## Bulgular (P0/P1)", ""]
    if findings:
        lines += ["| Öncelik | Bulgu |", "|---|---|"]
        for pri, text in findings:
            escaped = text.replace('|', '\\|')
            lines.append(f"| {pri} | {escaped} |")
    else:
        lines.append("Bulgu yok — tüm hook'lar geçti.")
    lines += [
        "",
        "## Ham log",
        "",
        "Tam çıktı `precommit.log` dosyasında (bu artifact içinde) saklanır.",
        "",
    ]

    pathlib.Path("logs").mkdir(parents=True, exist_ok=True)
    pathlib.Path("logs/PRECOMMIT_RAPORU.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(f"PRECOMMIT_RAPORU.md yazıldı: {len(hooks)} hook, {len(findings)} bulgu")


if __name__ == "__main__":
    main()
