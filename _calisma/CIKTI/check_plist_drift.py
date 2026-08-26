#!/usr/bin/env python3
"""check_plist_drift.py — LaunchAgent plist şablon drift'ini denetler.

update_preview.sh'in yerleşik şablonunu (plist_default_template) kanonik bir
HOME ile render eder, çıktıyı commit'li golden plist'lerle karşılaştırır ve
plutil/plistlib ile yapısal geçerliliğini doğrular. Böylece şablondaki bir
değişiklik (port/path/KeepAlive/ProgramArguments) CI'da advisory bir drift
sinyali olarak yakalanır.

Kanonik HOME = /Users/ci (portable; gerçek kullanıcı yolu golden'a gömülmez).
Render, update_preview.sh --plist-force <render-home> ile YAPILIR (tek kaynak);
bu script render mantığını kopyalamaz — yalnızca çıktıyı normalize edip
golden'la karşılaştırır.

Exit kodu:
  0 = tüm profiller golden ile birebir + yapısal geçerli (drift yok)
  1 = drift (bayat/golden'dan farklı/geçersiz/eksik/fazla)
  2 = hata (script yok, render başarısız, golden dizini yok)

Drift önceliği (results[].priority + has_p0/has_p1):
  P0 = fail-closed: fazla-profil (golden'da olmayan render edilmiş profil) —
       golden seti şablonla senkron değil, build'i BLOKE eder.
  P1 = advisory: diğer drift'ler (eksik/bayat/yapısal geçersiz).

Kullanım:
  check_plist_drift.py [--script PATH] [--golden-dir DIR]
                       [--canonical-home PATH] [--render-home DIR] [--json]
"""
import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile

DEFAULT_CANONICAL_HOME = "/Users/ci"
DEFAULT_GOLDEN_DIRNAME = "plist-golden"


def normalize(content, src, dst):
    """`content` içindeki `src` önekini `dst` ile değiştir (render-home → canonical)."""
    if not content:
        return content
    return content.replace(src, dst)


def plist_is_valid(path):
    """plist dosyasını yapısal olarak doğrula (plutil varsa onu, yoksa plistlib)."""
    try:
        if shutil.which("plutil"):
            r = subprocess.run(["plutil", "-lint", path],
                               capture_output=True, text=True, timeout=30)
            return r.returncode == 0
        with open(path, "rb") as f:
            plistlib.load(f)
        return True
    except Exception:
        return False


def check(render_home, golden_dir, canonical_home):
    """Render edilmiş plist'leri golden ile karşılaştır.

    Döner: (results, drift, error)
      results = [ {label, verdict, priority, detail} ... ]  (sıralı, deterministik)
      drift   = True ise en az bir profil golden'dan farklı
      error   = True ise denetim koşulamadı (exit 2)

    priority öncelik sınıfıdır:
      P0 — fail-closed: fazla-profil drift'i (golden'da olmayan render edilmiş
           profil). Golden seti şablonla senkron DEĞİL demektir — şablon yeni
           bir profil üretiyor ama commit'li golden'ı yok. Sessiz kapsam
           kaybını önlemek için build'i BLOKE eder.
      P1 — advisory: diğer drift'ler (eksik/bayat/yapısal geçersiz).
      None — PASS.
    """
    results = []
    drift = False
    error = False

    golden_files = {}
    if os.path.isdir(golden_dir):
        for name in sorted(os.listdir(golden_dir)):
            if name.endswith(".plist"):
                golden_files[name] = os.path.join(golden_dir, name)

    if not golden_files:
        return results, drift, True  # golden yok → denetim koşulamadı

    rendered_dir = os.path.join(render_home, "Library", "LaunchAgents")
    rendered_files = {}
    if os.path.isdir(rendered_dir):
        for name in sorted(os.listdir(rendered_dir)):
            if name.endswith(".plist"):
                rendered_files[name] = os.path.join(rendered_dir, name)

    # Golden'daki her profil: render edilmiş mi, normalize edilmiş içerik aynı mı?
    for name, golden_path in golden_files.items():
        rpath = rendered_files.get(name)
        if rpath is None:
            drift = True
            results.append({"label": name, "verdict": "DRIFT", "priority": "P1",
                            "detail": "render edilmedi (eksik)"})
            continue

        with open(golden_path, "r", encoding="utf-8") as f:
            golden = f.read()
        with open(rpath, "r", encoding="utf-8") as f:
            rendered = normalize(f.read(), render_home, canonical_home)

        if rendered != golden:
            drift = True
            results.append({"label": name, "verdict": "DRIFT", "priority": "P1",
                            "detail": "şablondan üretilen içerik golden'dan farklı"})
            continue

        if not plist_is_valid(rpath):
            drift = True
            results.append({"label": name, "verdict": "DRIFT", "priority": "P1",
                            "detail": "yapısal geçersiz (plutil/plistlib)"})
            continue

        results.append({"label": name, "verdict": "PASS", "priority": None,
                        "detail": "golden ile birebir + geçerli"})

    # Golden'da olmayan fazladan render edilmiş plist var mı? (beklenmedik profil)
    # Fazla-profil drift'i P0 (fail-closed): golden seti şablonla senkron değil.
    # Diğer drift'ler (eksik/bayat/geçersiz) P1 (advisory) kalır.
    for name in rendered_files:
        if name not in golden_files:
            drift = True
            results.append({"label": name, "verdict": "DRIFT", "priority": "P0",
                            "detail": "golden'da olmayan fazla profil"})

    return results, drift, error


def run_render(script, render_home):
    """update_preview.sh --plist-force <render-home> çalıştır; (rc, output)."""
    r = subprocess.run(
        ["bash", script, "--plist-force", render_home],
        capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="LaunchAgent plist drift denetimi")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--script", default=os.path.join(here, "update_preview.sh"),
                    help="update_preview.sh yolu")
    ap.add_argument("--golden-dir", default=os.path.join(here, DEFAULT_GOLDEN_DIRNAME),
                    help="golden plist dizini")
    ap.add_argument("--canonical-home", default=DEFAULT_CANONICAL_HOME,
                    help="golden'da kullanılan kanonik HOME (vars. /Users/ci)")
    ap.add_argument("--render-home", default=None,
                    help="render hedef HOME (vars. geçici dizin; test için sabitlenebilir)")
    ap.add_argument("--json", action="store_true", help="JSON çıktı")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.script):
        report = {"ok": False, "error": f"update_preview.sh yok: {args.script}",
                  "results": []}
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(f"HATA: update_preview.sh yok: {args.script}")
        return 2

    if not os.path.isdir(args.golden_dir):
        report = {"ok": False, "error": f"golden dizini yok: {args.golden_dir}",
                  "results": []}
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(f"HATA: golden dizini yok: {args.golden_dir}")
        return 2

    # Render hedefi: --render-home verildiyse onu, yoksa geçici dizini kullan.
    own_tmp = False
    render_home = args.render_home
    if render_home is None:
        render_home = tempfile.mkdtemp(prefix="plist-render-")
        own_tmp = True
    elif os.path.isdir(render_home):
        shutil.rmtree(render_home, ignore_errors=True)
    os.makedirs(render_home, exist_ok=True)

    try:
        rc, output = run_render(args.script, render_home)
        if rc != 0:
            report = {"ok": False, "error": f"render başarısız (exit {rc}): {output.strip()}",
                      "results": []}
            if args.json:
                print(json.dumps(report, ensure_ascii=False))
            else:
                print(f"HATA: render başarısız (exit {rc})")
                print(output.strip())
            return 2

        results, drift, error = check(render_home, args.golden_dir, args.canonical_home)
        if error:
            report = {"ok": False, "error": "denetim koşulamadı (golden yok)", "results": results}
            if args.json:
                print(json.dumps(report, ensure_ascii=False))
            return 2

        # Fazla-profil drift'i P0 (fail-closed); diğer drift'ler P1 (advisory).
        has_p0 = any(r.get("priority") == "P0" for r in results)
        has_p1 = any(r.get("priority") == "P1" for r in results)
        report = {"ok": not drift, "drift": drift,
                  "canonical_home": args.canonical_home,
                  "has_p0": has_p0, "has_p1": has_p1,
                  "results": results}
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            for r in results:
                if r["verdict"] == "PASS":
                    mark = "PASS"
                else:
                    mark = r.get("priority") or "DRIFT"
                print(f"[{mark}] {r['label']} — {r['detail']}")
            if drift:
                print(f"SONUÇ: DRIFT TESPİT EDİLDİ (P0={int(has_p0)}, P1={int(has_p1)})")
            else:
                print("SONUÇ: TÜMÜ PASS")
        return 1 if drift else 0
    finally:
        if own_tmp:
            shutil.rmtree(render_home, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
