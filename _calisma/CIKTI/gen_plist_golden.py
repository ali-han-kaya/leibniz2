#!/usr/bin/env python3
"""gen_plist_golden.py — plist-golden dosyalarını update_preview.sh şablonundan
otomatik yeniden üretir.

check_plist_drift.py'nin denetlediği golden plist'lerin commit'li kopyasını
günceller. Her commit'te şablon (`plist_default_template`) veya profil
tanımları (`PLIST_PROFILES`, port/interval/keepalive) değiştiğinde golden
dosyaları bayatlar — drift kapısı bunu yakalar. Bu script, şablon/profil
değişikliğinden SONRA golden'ı bir kereliğine yeniden üreterek drift'i
sıfırlar; git diff ile neyin değiştiğini gösterir.

KANONİK HOME: /Users/ci (check_plist_drift.py ile aynı; portable — gerçek
kullanıcı yolu golden'a gömülmez). Render öncesi hedef dizin temizlenir
(idempotent). Yalnızca gerçekten değişen dosyalar overwrite edilir.

Kullanım:
  python3 gen_plist_golden.py                       # üret ve diff göster
  python3 gen_plist_golden.py --dry-run             # yalnızca drift var mı kontrol et (exit kodu)
  python3 gen_plist_golden.py --force               # değişmesin bile tümünü overwrite

Exit kodu:
  0 = tüm golden'lar güncel (değişiklik yok)
  1 = drift — golden'lar güncellendi (git stage et)
  2 = hata (render başarısız)

CI'da kullanım (drift saptama, advisory):
  python3 gen_plist_golden.py --dry-run && echo "golden güncel" || echo "DRIFT — golden bayat"
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATE_PREVIEW = os.path.join(HERE, "update_preview.sh")
GOLDEN_DIR = os.path.join(HERE, "plist-golden")
CANONICAL_HOME = "/Users/ci"


def run_render(render_home):
    """update_preview.sh --plist-force <render_home> çalıştır."""
    r = subprocess.run(
        ["bash", UPDATE_PREVIEW, "--plist-force", render_home],
        capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def collect_rendered(render_home):
    """Render edilmiş plist'leri {dosya_adı: içerik} olarak topla."""
    launch_dir = os.path.join(render_home, "Library", "LaunchAgents")
    result = {}
    if os.path.isdir(launch_dir):
        for name in sorted(os.listdir(launch_dir)):
            if name.endswith(".plist"):
                p = os.path.join(launch_dir, name)
                with open(p, "r", encoding="utf-8") as f:
                    # render-home yolunu kanonik /Users/ci ile değiştir
                    content = f.read().replace(render_home, CANONICAL_HOME)
                result[name] = content
    return result


def compare(rendered):
    """Rendered içerikleri mevcut golden'larla karşılaştır.

    Döner: (drift, updated, unchanged, removed)
      drift    = True ise en az bir dosya farklı
      updated  = değişen dosya adları
      unchanged= aynı kalan dosya adları
      removed  = golden'da olup render'da olmayanlar
    """
    drift = False
    updated = []
    unchanged = []
    removed = []

    golden_names = set()
    if os.path.isdir(GOLDEN_DIR):
        for name in os.listdir(GOLDEN_DIR):
            if name.endswith(".plist"):
                golden_names.add(name)

    render_names = set(rendered.keys())

    # Render'da olup golden'da olmayan → yeni profil (ekle)
    for name in sorted(render_names - golden_names):
        drift = True
        updated.append(name)

    # Golden'da olup render'da olmayan → profil kaldırılmış (silinmeli)
    for name in sorted(golden_names - render_names):
        drift = True
        removed.append(name)

    # Her ikisinde de olanlar → içerik karşılaştır
    for name in sorted(golden_names & render_names):
        gp = os.path.join(GOLDEN_DIR, name)
        with open(gp, "r", encoding="utf-8") as f:
            current = f.read()
        if current != rendered[name]:
            drift = True
            updated.append(name)
        else:
            unchanged.append(name)

    return drift, updated, unchanged, removed


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="plist-golden dosyalarını update_preview.sh şablonundan otomatik üret")
    ap.add_argument("--dry-run", action="store_true",
                    help="yalnızca drift kontrolü — dosyaları değiştirme")
    ap.add_argument("--force", action="store_true",
                    help="değişmemiş dosyaları da overwrite et")
    args = ap.parse_args(argv)

    if not os.path.isfile(UPDATE_PREVIEW):
        print(f"HATA: update_preview.sh yok: {UPDATE_PREVIEW}", file=sys.stderr)
        return 2

    # Render
    render_home = tempfile.mkdtemp(prefix="gen-golden-render-")
    try:
        rc, output = run_render(render_home)
        if rc != 0:
            print(f"HATA: render başarısız (exit {rc})", file=sys.stderr)
            print(output, file=sys.stderr)
            return 2

        rendered = collect_rendered(render_home)
        if not rendered:
            print("HATA: render başarılı ama hiç plist üretilmedi", file=sys.stderr)
            return 2

    finally:
        shutil.rmtree(render_home, ignore_errors=True)

    # Karşılaştır
    drift, updated, unchanged, removed = compare(rendered)
    all_changed = updated + removed

    if not drift:
        print("✓ plist-golden güncel — şablon/profil değişikliği yok")
        print(f"  {len(unchanged)} profil değişmedi: {', '.join(sorted(unchanged))}")
        return 0

    # Drift var — raporla
    print("⚠ plist-golden BAYAT — şablon/profil değişikliği tespit edildi\n")

    if removed:
        print(f"  KALDIRILACAK ({len(removed)}): {', '.join(removed)}")
    if updated:
        up_labels = [n for n in updated if n not in removed]
        if up_labels:
            print(f"  GÜNCELLENECEK ({len(up_labels)}): {', '.join(up_labels)}")
    if unchanged:
        print(f"  Değişmedi ({len(unchanged)}): {', '.join(unchanged)}")

    if args.dry_run:
        print(f"\nSONUÇ: DRIFT — {len(all_changed)} golden dosya bayat (--dry-run, değiştirilmedi)")
        return 1

    # Dosyaları güncelle
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    overwritten = []

    for name in sorted(rendered):
        target = os.path.join(GOLDEN_DIR, name)
        if name in updated or args.force:
            with open(target, "w", encoding="utf-8") as f:
                f.write(rendered[name])
            overwritten.append(name)
        elif name not in unchanged:
            # Tamamen yeni profil
            with open(target, "w", encoding="utf-8") as f:
                f.write(rendered[name])
            overwritten.append(name)

    for name in removed:
        target = os.path.join(GOLDEN_DIR, name)
        if os.path.isfile(target):
            os.unlink(target)
            print(f"  Silindi: {name}")

    print(f"\n✓ {len(overwritten)} golden dosya güncellendi: {', '.join(sorted(overwritten))}")
    print("  Sonraki adım: git add plist-golden/ + commit")
    return 1


if __name__ == "__main__":
    sys.exit(main())