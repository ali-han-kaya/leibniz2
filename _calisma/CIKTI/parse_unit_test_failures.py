#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_unit_test_failures.py — unit_tests.log'dan düşen testleri ayrıştırır.

unittest -v çıktısındaki FAIL/ERROR/satırlarını bulur ve markdown tablosu üretir.
Hiç düşen test yoksa boş string döndürür.

Kullanım:
  python3 parse_unit_test_failures.py unit_tests.log
  python3 parse_unit_tests_failures.py unit_tests.log --json
"""
import json
import re
import sys


def parse_failures(log_text):
    """unittest -v log'undan FAIL/ERROR satırlarını ayrıştır.

    Döndürür: [{"test": str, "status": "FAIL"|"ERROR", "detail": str}]
    """
    failures = []
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        # FAIL pattern: "test_foo (module.Class) ... FAIL"
        m_fail = re.match(r"^(\S+) \(\S+\) \.\.\. (FAIL|ERROR)$", line)
        if m_fail:
            test_name = m_fail.group(1)
            status = m_fail.group(2)
            # Detail lines follow until next test or separator
            detail_lines = []
            i += 1
            while i < len(lines):
                if lines[i].startswith("=" * 70):
                    break
                if re.match(r"^\S+ \(\S+\) \.\.\. (FAIL|ERROR|ok|OK)$", lines[i]):
                    break
                detail_lines.append(lines[i])
                i += 1
            failures.append({
                "test": test_name,
                "status": status,
                "detail": "\n".join(detail_lines).strip()[:500],
            })
        else:
            i += 1
    return failures


def to_markdown(failures, total_lines):
    """Failure listesinden markdown tablosu üret."""
    if not failures:
        return ""
    p0 = [f for f in failures if f["status"] == "ERROR"]
    p1 = [f for f in failures if f["status"] == "FAIL"]
    parts = [
        "## 🧪 Unit Test Düşenler",
        "",
        f"**{len(failures)}** düşen test (ERROR: {len(p0)}, FAIL: {len(p1)})",
        "",
        "| Durum | Test | Detay |",
        "|-------|------|-------|",
    ]
    for f in failures:
        icon = "🔴" if f["status"] == "ERROR" else "🟡"
        detail = f["detail"].split("\n")[0][:80] if f["detail"] else "—"
        # Markdown tablo karakterlerini temizle
        detail = detail.replace("|", "\\|")
        parts.append(f"| {icon} {f['status']} | `{f['test']}` | {detail} |")
    return "\n".join(parts)


def main():
    if len(sys.argv) < 2:
        print("Kullanım: parse_unit_test_failures.py <unit_tests.log>", file=sys.stderr)
        return 1

    log_path = sys.argv[1]
    use_json = "--json" in sys.argv

    try:
        with open(log_path, encoding="utf-8") as f:
            log_text = f.read()
    except FileNotFoundError:
        print(f"Dosya bulunamadı: {log_path}", file=sys.stderr)
        return 1

    failures = parse_failures(log_text)
    total_lines = len(log_text.splitlines())

    if use_json:
        print(json.dumps({
            "total_lines": total_lines,
            "failure_count": len(failures),
            "failures": failures,
        }, indent=2, ensure_ascii=False))
    else:
        md = to_markdown(failures, total_lines)
        if md:
            print(md)
        else:
            print(f"✅ Tüm testler yeşil ({total_lines} satır log)")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
