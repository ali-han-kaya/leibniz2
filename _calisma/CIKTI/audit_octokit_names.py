#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_octokit_names.py — Octokit metod adı denetimi (fail-closed).

github_scripts/*.js dosyalarındaki Octokit REST API çağrılarını tarar;
izin verilen metod adları ↔ resmi rota eşlemesiyle eşleşmeyen
çağrıları yakalar. pre-commit + CI'da fail-closed çalışır.

Kullanım:
  python audit_octokit_names.py                  # tüm js dosyalarını tara
  python audit_octokit_names.py --scripts-dir DIZIN  # özel dizin
  python audit_octokit_names.py --json           # JSON çıktı
  python audit_octokit_names.py --check-only     # yalnızca kontrol, çıktı yok

Çıkış: 0 = PASS (tüm çağrılar izinli), 1 = FAIL (izin dışı metod)
"""

import argparse
import json
import os
import re
import sys

# ── İzın verilen Octokit metod adları ↔ resmi GitHub API rotası ──────────
# Her entry: (method_name, http_method, route_pattern)
# method_name: github.rest.<namespace>.<method> biçiminde
# route_pattern: GitHub REST API resmi yolu (https://docs.github.com/en/rest)
ALLOWED_METHODS = [
    # ── Issues: Comments ──────────────────────────────────────────────────
    ("issues.listComments",        "GET",
     "/repos/{owner}/{repo}/issues/{issue_number}/comments"),
    ("issues.createComment",       "POST",
     "/repos/{owner}/{repo}/issues/{issue_number}/comments"),
    ("issues.updateComment",       "PATCH",
     "/repos/{owner}/{repo}/issues/{issue_number}/comments/{comment_id}"),
    ("issues.deleteComment",       "DELETE",
     "/repos/{owner}/{repo}/issues/{issue_number}/comments/{comment_id}"),
    # ── Issues: Labels ────────────────────────────────────────────────────
    ("issues.listLabelsOnIssue",   "GET",
     "/repos/{owner}/{repo}/issues/{issue_number}/labels"),
    ("issues.addLabels",           "POST",
     "/repos/{owner}/{repo}/issues/{issue_number}/labels"),
    ("issues.removeLabel",         "DELETE",
     "/repos/{owner}/{repo}/issues/{issue_number}/labels/{name}"),
    # ── Issues: Label definitions (repo-level) ────────────────────────────
    ("issues.listLabelsForRepo",   "GET",
     "/repos/{owner}/{repo}/labels"),
    ("issues.createLabel",         "POST",
     "/repos/{owner}/{repo}/labels"),
    ("issues.updateLabel",         "PATCH",
     "/repos/{owner}/{repo}/labels/{name}"),
]

# Hızlı arama sözlüğü: method_name → (http_method, route)
_ALLOWED_MAP = {name: (method, route) for name, method, route in ALLOWED_METHODS}

# Octokit REST çağrısı kalıbı:
#   github.rest.<namespace>.<method>(  veya  github.rest.<namespace>.<method>({
_CALL_RE = re.compile(
    r"github\.rest\.(\w+)\.(\w+)\s*\(")

# ScriptPath injection kalıbı (bonus — node gerektirmez)
_SCRIPTPATH_RE = re.compile(
    r"scriptPath\s*:", re.M)


def _find_js_files(scripts_dir):
    """Dizindeki tüm .js dosyalarını listele (recursive)."""
    files = []
    for root, _dirs, fnames in os.walk(scripts_dir):
        for fn in sorted(fnames):
            if fn.endswith(".js"):
                files.append(os.path.join(root, fn))
    return files


def audit_file(path):
    """Tek bir .js dosyasını denetle.

    Dönüş: [(method_name, namespace, method, line_no, file_path), ...]
    Bulgu = izin dışı Octokit çağrısı.
    """
    findings = []
    try:
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                for m in _CALL_RE.finditer(line):
                    namespace, method = m.group(1), m.group(2)
                    full_name = f"{namespace}.{method}"
                    if full_name not in _ALLOWED_MAP:
                        findings.append((full_name, namespace, method,
                                         lineno, path))
    except (OSError, UnicodeDecodeError) as e:
        findings.append((f"READ_ERROR: {e}", "", "", 0, path))
    return findings


def audit_directory(scripts_dir):
    """Tüm .js dosyalarını denetle.

    Dönüş: {ok: bool, findings: [...], files_scanned: int, total_calls: int}
    """
    js_files = _find_js_files(scripts_dir)
    all_findings = []
    total_calls = 0
    for path in js_files:
        # Her dosyadaki toplam Octokit çağrısını say (izinli + izinsiz)
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            total_calls += len(_CALL_RE.findall(content))
        except (OSError, UnicodeDecodeError):
            pass
        all_findings.extend(audit_file(path))
    return {
        "ok": len(all_findings) == 0,
        "findings": [
            {"method": f[0], "namespace": f[1], "method_name": f[2],
             "line": f[3], "file": os.path.basename(f[4])}
            for f in all_findings
        ],
        "files_scanned": len(js_files),
        "total_calls": total_calls,
        "allowed_count": len(_ALLOWED_MAP),
    }


def format_text(result):
    """İnsan-okunur çıktı."""
    lines = []
    lines.append(f"── Octokit metod adı denetimi ──")
    lines.append(f"Dosya sayısı: {result['files_scanned']}")
    lines.append(f"Toplam Octokit çağrısı: {result['total_calls']}")
    lines.append(f"İzin verilen metod: {result['allowed_count']}")
    if result["ok"]:
        lines.append(f"Durum: PASS — tüm çağrılar izinli")
    else:
        lines.append(f"Durum: FAIL — {len(result['findings'])} izin dışı metod")
        for f in result["findings"]:
            loc = f"satır {f['line']}" if f["line"] else "?"
            lines.append(f"  ✗ {f['method']} ({f['file']}:{loc})")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scripts-dir",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "github_scripts"),
                    help="github_scripts dizini (varsayılan: ../github_scripts)")
    ap.add_argument("--json", action="store_true",
                    help="JSON çıktı")
    ap.add_argument("--check-only", action="store_true",
                    help="Yalnızca kontrol, çıktı bastırma")
    args = ap.parse_args(argv)

    result = audit_directory(args.scripts_dir)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif not args.check_only:
        print(format_text(result))

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
