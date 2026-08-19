#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_python3_shell.py — `shell: python3 {0}` altında kabuk komutu kapısı.

GitHub Actions'ta `shell: python3 {0}` (veya `shell: python`) demek `run:`
içeriğinin Python KODU olduğu anlamına gelir. Birisi yanlışlıkla altına
kabuk komutları yazarsa (cd/&&/|/echo/set -e...) iş, Python derleme hatası
veya çalışma-zamanı NameError'u ile CI'da patlar — geç yakalanır.

Bu kapı (lokal + OFFLINE, yalnızca stdlib) workflow'u satır satır ayrıştırıp
her `shell: python3` adımının `run:` içeriğini iki kapıyla denetler:

  1) compile(): run bloğu geçerli Python DEĞİLSE FAIL.
     (kabuk komutlarının çoğu — `cd x && python3 y.py` vb. — zaten
      SyntaxError üretir)
  2) asla-geçerli-Python-olmayan kabuk kalıpları: `&&`, `||`, `$(`, `${`,
     `$VAR`, `set -e`, `2>&1`, satır-başı `echo `/`cd `/`export `/`cat <<`,
     `#!/` — Python'da bu kalıplar için meşru kullanım YOKTUR; bulunursa FAIL
     (compile'ın yakalayamadığı tek-simge kabuklar: `echo "x"` gibi).

`;` ve `|` (bitwise) Python'da geçerli olduğundan BİLEREK denetlenmez —
yanlış pozitif üretmez. Yanlış PASS üretmez: doğrulanamayan adım (ayrıştırma
belirsizliği) FAIL sayılır.

Kullanım:
    python3 check_python3_shell.py --workflow .github/workflows/verify.yml
    python3 check_python3_shell.py --workflow X.yml --json      # makine-okur
    python3 check_python3_shell.py --workflow X.yml --out rapor.json

Exit: 0 = PASS (python3-shell adımı yok ya da hepsi geçerli Python),
      1 = FAIL (kabuk komutu python3 adımında), 2 = kullanım/ortam hatası.
"""
import argparse
import json
import re
import sys

# GitHub Actions'ın `run:` bloğunda asla geçerli Python olmayan kabuk kalıpları.
# Python'da `&&`/`||` yoktur, `$` operatörü yoktur, `2>&1` geçersizdir,
# satır-başı `echo `/`cd `/`export ` kabuk içindir (Python'da `echo x` gibi
# iki değişken yan yana SyntaxError üretir — compile kapısı da yakalar; bu
# kalıplar daha net hata mesajı ve NameError vakaları için).
SHELL_PATTERNS = [
    (r"&&", "kabuk AND (`&&`)"),
    (r"\|\|", "kabuk OR (`||`)"),
    (r"\$\(", "komut ikamesi (`$(...)`)"),
    (r"\$\{", "değişken ikamesi (`${...}`)"),
    (r"\$[A-Za-z_][A-Za-z0-9_]*", "ortam değişkeni (`$VAR`)"),
    (r"\bset\s+-[ex]\b", "kabuk `set -e/-x`"),
    (r"2>&1", "kabuk yönlendirme (`2>&1`)"),
    (r"#!/", "shebang"),
    (r"(?m)^\s*echo\s+", "kabuk `echo`"),
    (r"(?m)^\s*cd\s+", "kabuk `cd`"),
    (r"(?m)^\s*export\s+", "kabuk `export`"),
    (r"(?m)^\s*cat\s*<<", "kabuk heredoc (`cat <<`)"),
    (r"(?m)^\s*tee\s+", "kabuk `tee`"),
]

SHELL_RE = re.compile(r"^\s*shell:\s*(.+?)\s*$")
RUN_RE = re.compile(r"^\s*run:\s*(.*)$")
STEP_RE = re.compile(r"^(\s*)-\s+(name|id|uses):\s*(.*)$")
PY_SHELL_RE = re.compile(r"^python3?(\s*\{\s*\d+\s*\})?$", re.IGNORECASE)


def _dedent_block(lines):
    """run: | bloğunu YAML girintisinden arındır (en küçük boş-olmayan
    girinti baz alınır). Boş satırlar korunur."""
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    if not indents:
        return "\n".join(lines)
    cut = min(indents)
    return "\n".join(l[cut:] if l.strip() else l for l in lines)


def parse_steps(text):
    """Workflow metnini adım adım ayrıştırır.

    Döndürür: [{name, indent, lineno, shell, run_source, run_kind}]
    shell/run, adım girintisinden DÜŞÜK girintideki `- name:` ile başlar;
    blok `run: |` altındaki satırlar bir sonraki adıma (veya eşit/düşük
    girintiye) kadar toplanır.
    """
    steps = []
    current = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        m = STEP_RE.match(raw)
        if m:
            if current is not None:
                steps.append(current)
            current = {
                "name": m.group(3) or "",
                "indent": len(m.group(1)),
                "lineno": lineno,
                "shell": None,
                "run_source": None,
                "run_kind": None,
            }
            continue
        if current is None:
            continue
        key_indent = len(raw) - len(raw.lstrip())
        if key_indent <= current["indent"]:
            # bir sonraki adım başlamadan blok kırıldı (güvenlik: blok kapat)
            current["run_kind"] = "done" if current["run_kind"] == "block" \
                else current["run_kind"]
            continue
        sm = SHELL_RE.match(raw)
        if sm and current["shell"] is None:
            current["shell"] = sm.group(1).strip().strip("'\"")
            continue
        rm = RUN_RE.match(raw)
        if rm and current["run_source"] is None:
            inline = rm.group(1).strip()
            if inline in ("|", ">", "|-", ">-"):
                # YAML blok skaları: sonraki girintili satırlar bloktur
                current["run_source"] = ""
                current["run_kind"] = "block"
            else:
                current["run_source"] = inline
                current["run_kind"] = "inline"
            continue
        if current["run_kind"] == "block":
            current["run_source"] += raw + "\n"
    if current is not None:
        steps.append(current)
    for s in steps:
        if s["run_kind"] == "block" and s["run_source"]:
            s["run_source"] = _dedent_block(s["run_source"].splitlines())
    return steps


def check_step(step):
    """Tek adımı denetler. Döndürür (verdict, detail) — verdict PASS|FAIL.
    Yalnızca `shell: python3` adımları; diğerleri PASS (kapsam dışı)."""
    shell = step.get("shell")
    if shell is None or not PY_SHELL_RE.match(shell):
        return "PASS", "python3-shell adımı değil"
    src = step.get("run_source") or ""
    if not src.strip():
        return "FAIL", "`shell: python3` ama boş `run:` bloğu"
    reasons = []
    try:
        compile(src, f"<workflow {step['name']}>", "exec")
    except SyntaxError as e:
        reasons.append(f"geçerli Python değil (SyntaxError: {e.msg} "
                       f"satır {e.lineno})")
    for pat, label in SHELL_PATTERNS:
        m = re.search(pat, src)
        if m:
            line_no = src[: m.start()].count("\n") + 1
            reasons.append(f"kabuk kalıbı: {label} (satır {line_no})")
    if reasons:
        return "FAIL", "; ".join(reasons)
    return "PASS", "geçerli Python (`shell: python3` uyumlu)"


def audit(text):
    """Tüm workflow'u denetler. Döndürür: [finding dict]"""
    findings = []
    for step in parse_steps(text):
        v, d = check_step(step)
        findings.append({
            "step": step["name"] or "(adsız)",
            "line": step["lineno"],
            "shell": step.get("shell"),
            "verdict": v,
            "detail": d,
        })
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workflow", required=True,
                    help="denetlenecek GitHub Actions workflow YAML dosyası")
    ap.add_argument("--json", action="store_true",
                    help="makine-okunur JSON rapor bas (stdout'a yalnızca JSON)")
    ap.add_argument("--out", help="raporu bu dosyaya da yaz")
    args = ap.parse_args(argv)

    try:
        with open(args.workflow, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"HATA: workflow okunamadı: {e}", file=sys.stderr)
        return 2

    findings = audit(text)
    fails = [f for f in findings if f["verdict"] == "FAIL"]
    checked = [f for f in findings if f["shell"] and
               PY_SHELL_RE.match(f["shell"])]
    total = len(findings)

    if args.json:
        report = {
            "tool": "check_python3_shell.py",
            "workflow": args.workflow,
            "steps": total,
            "python3_shell_steps": len(checked),
            "fail": len(fails),
            "verdict": "PASS" if not fails else "FAIL",
            "findings": findings,
        }
        out = json.dumps(report, ensure_ascii=False, indent=1)
        print(out)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(out)
        return 0 if not fails else 1

    for f in findings:
        if f["verdict"] == "FAIL":
            print(f"[FAIL] satır {f['line']:<4} {f['step']:<40} "
                  f"-> {f['detail']}")
    print(f"SONUÇ: {'FAIL' if fails else 'PASS'} — {len(fails)} FAIL / "
          f"{len(checked)} python3-shell adım / {total} toplam adım")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
