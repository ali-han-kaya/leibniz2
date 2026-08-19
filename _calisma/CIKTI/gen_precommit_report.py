#!/usr/bin/env python3
"""gen_precommit_report.py — pre-commit çıktısını rapora çevir (MD + JSON).

verify.yml'deki 'Generate pre-commit findings report' adımının inline Python
mantığının standalone hali (gen_repro_manifest.py deseni): aynı kod hem CI'da
hem yerelde çalışır → CI ile yerel arasında drift olmaz.

Girdi : logs/precommit.log   (pre-commit run --all-files çıktısı)
        logs/precommit.exit  (exit kodu)
        logs/commit_msg_findings.json  (check_commit_messages.py sidecar'ı —
                                        varsa "Commit-msg (CI advisory)" bölümü)
Çıktı : logs/PRECOMMIT_RAPORU.md  (hook sonuçları + P0/P1 bulguları + commit-msg
                                     + ham log notu)
        logs/PRECOMMIT_RAPORU.json (aynı içeriğin makine-okunur hali: hook
                                     durumları Passed/Failed + bulgular + sayımlar)
        → her ikisi de `logs/` altında olduğundan precommit-logs artifact'ına
          otomatik girer ve reproducibility manifest'inde SHA-256 ile sabitlenir.

Kullanım (CI çalışma dizininden — logs/ altı hazır olmalı):
  python3 gen_precommit_report.py
"""
import datetime
import json
import pathlib
import re

STATUS_RE = re.compile(r"^(.*?)\.{4,}(Passed|Failed)\s*$", re.M)


def parse_hooks(log_text):
    """pre-commit verbose çıktısından hook sonuçlarını ayrıştır.

    Her hook satırı 'Hook adı.....Passed|Failed' biçimindedir.
    """
    return [
        {"name": m.group(1).strip(), "status": m.group(2)}
        for m in STATUS_RE.finditer(log_text)
    ]


def parse_update_config(log_text):
    """update-config hook'unun durumu + kendi çıktısı (denetim izi).

    Hook satırı ('Sync config …Passed/Failed') ile bir SONRAKİ hook satırı
    arasındaki satırlar o hook'un stdout/stderr çıktısıdır (verbose: true).
    """
    uc_status = None
    uc_output = []
    for m in STATUS_RE.finditer(log_text):
        if "Sync config" in m.group(1) or "gen_config" in m.group(1):
            uc_status = m.group(2)
            nxt = STATUS_RE.search(log_text, m.end())
            end = nxt.start() if nxt else len(log_text)
            for line in log_text[m.end():end].splitlines():
                s = line.strip()
                if not s or s.startswith("- hook id:") or s.startswith("- duration:"):
                    continue
                uc_output.append(s)
            break
    return uc_status, uc_output


def load_commit_msg(path="logs/commit_msg_findings.json"):
    """check_commit_messages.py sidecar'ı — yoksa/bozuksa None."""
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def parse_findings(log_text, uc_status, uc_output):
    """P0/P1 bulgularını ayrıştır; update-config FAIL'i ayrı P1 bulgusu yapar."""
    findings = []
    for pri in ("P0", "P1"):
        for m in re.finditer(rf"^\[{pri}\] (.+)$", log_text, re.M):
            findings.append((pri, m.group(1).strip()))

    # update-config FAIL → ayrı bir bulgu (CI'da drift/modifikasyon işareti).
    if uc_status == "Failed":
        detail = " | ".join(uc_output) if uc_output else "çıktı yok"
        findings.append(("P1",
                         f"update-config FAIL — config paket içeriğiyle "
                         f"senkronlanamadı (CI'da drift/modifikasyon). "
                         f"Çıktı: {detail}"))
    return findings


def build_data(log_text, exit_code, commit_msg=None):
    """Ayrıştırma sonucunu tek kaynak bir sözlüğe topla (MD + JSON ortak).

    commit_msg (check_commit_messages.py sidecar'ı) verilirse 'commit_msg'
    alanı olarak eklenir; None ise alan hiç yazılmaz (rapor geriye uyumlu).
    """
    hooks = parse_hooks(log_text)
    uc_status, uc_output = parse_update_config(log_text)
    findings = parse_findings(log_text, uc_status, uc_output)

    now = datetime.datetime.utcnow().isoformat() + "Z"
    verdict = "PASS" if exit_code == 0 else "FAIL"
    passed = sum(1 for h in hooks if h["status"] == "Passed")
    failed = len(hooks) - passed
    p0 = sum(1 for pri, _ in findings if pri == "P0")
    p1 = sum(1 for pri, _ in findings if pri == "P1")

    data = {
        "generated_at": now,
        "command": "pre-commit run --all-files --show-diff-on-failure",
        "exit_code": exit_code,
        "verdict": verdict,
        "role": "advisory",
        "hooks": hooks,
        "update_config": {
            "status": uc_status,
            "output": uc_output,
        },
        "findings": [
            {"priority": pri, "message": text} for pri, text in findings
        ],
        "counts": {
            "hooks": len(hooks),
            "passed": passed,
            "failed": failed,
            "p0": p0,
            "p1": p1,
        },
    }
    if commit_msg is not None:
        data["commit_msg"] = commit_msg
    return data


def render_markdown(data):
    """Veri sözlüğünden PRECOMMIT_RAPORU.md metnini üret."""
    hooks = data["hooks"]
    uc_status = data["update_config"]["status"]
    uc_output = data["update_config"]["output"]
    findings = data["findings"]

    lines = [
        "# PRECOMMIT DENETİM RAPORU (CI advisory)",
        "",
        f"- **Tarih (UTC):** {data['generated_at']}",
        f"- **Komut:** `{data['command']}`",
        f"- **Sonuç:** {data['verdict']} (exit {data['exit_code']})",
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

    # update-config'e özel bölüm: PASS/FAIL + kendi çıktısı (denetim izi).
    lines += ["", "## update-config (config senkronu)", ""]
    if uc_status:
        out_txt = "; ".join(uc_output) if uc_output else "çıktı yok (drift yok)"
        escaped_out = out_txt.replace("|", "\\|")
        lines.append("| Adım | Durum | Çıktı |")
        lines.append("|---|---|---|")
        lines.append(f"| Sync config (gen_config.py) | {uc_status} | {escaped_out} |")
    else:
        lines.append("(update-config hook satırı çıktıda bulunamadı)")

    lines += ["", "## Bulgular (P0/P1)", ""]
    if findings:
        lines += ["| Öncelik | Bulgu |", "|---|---|"]
        for f in findings:
            escaped = f["message"].replace('|', '\\|')
            lines.append(f"| {f['priority']} | {escaped} |")
    else:
        lines.append("Bulgu yok — tüm hook'lar geçti.")

    # Commit-msg (CI advisory): check_commit_messages.py sidecar'ı varsa.
    cm = data.get("commit_msg")
    if cm is not None:
        checked = cm.get("checked", 0)
        violations = cm.get("violations", [])
        lines += ["", "## Commit-msg (CI advisory)", ""]
        if violations:
            lines.append(f"- ⚠️ {len(violations)} ihlal ({checked} commit denetlendi):")
            for v in violations:
                subject = (v.get("subject") or "").replace("|", "\\|")
                detail = (v.get("detail") or "").replace("|", "\\|")
                lines.append(f"  - `{v.get('commit', '?')}` — \"{subject}\": {detail}")
        else:
            lines.append(f"- ✅ İhlal yok ({checked} commit denetlendi).")
    lines += [
        "",
        "## Ham log",
        "",
        "Tam çıktı `precommit.log` dosyasında (bu artifact içinde) saklanır.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    log = pathlib.Path("logs/precommit.log")
    log_text = (log.read_text(encoding="utf-8", errors="replace")
                if log.exists() else "")
    try:
        exit_code = int(pathlib.Path("logs/precommit.exit").read_text().strip())
    except Exception:
        exit_code = 1

    data = build_data(log_text, exit_code, load_commit_msg())

    pathlib.Path("logs").mkdir(parents=True, exist_ok=True)
    pathlib.Path("logs/PRECOMMIT_RAPORU.md").write_text(
        render_markdown(data), encoding="utf-8"
    )
    pathlib.Path("logs/PRECOMMIT_RAPORU.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"PRECOMMIT_RAPORU.md yazıldı: {len(data['hooks'])} hook, "
          f"{len(data['findings'])} bulgu")
    print(f"PRECOMMIT_RAPORU.json yazıldı: {len(data['hooks'])} hook, "
          f"{data['counts']['p0']} P0, {data['counts']['p1']} P1")


if __name__ == "__main__":
    main()
