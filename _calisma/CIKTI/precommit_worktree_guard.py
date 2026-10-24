#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""precommit_worktree_guard.py — pre-commit'in kayıpsız stash penceresi (kalıcı çözüm).

KÖK-NEDEN
---------
`git commit` sırasında pre-commit unstaged İZLENEN deltayı
`~/.cache/pre-commit/patch<epoch>-<pid>` dosyasına stash'ler, ağacı
`git checkout -- .` ile index'e eşitler ve geri-uygulamayı SADECE
`finally` bloğundaki `git apply`'e bırakır. Pencere içinde süreç-ölümü
(harness'ın process-group SIGKILL'i — 2026-09-18 revert-olayı) ya da
`finally`'deki `apply`'in çakışması → ağaç sessizce revert olur ve delta
yalnızca pre-commit cache'inde kalır. Cache ise bir ÖNBELLEKTİR:
`pre-commit clean`, disk-temizleyici ya da cache-evrimi tek kopyayı da
silebilir → kalıcı veri kaybı.

Mevcut savunma (check_unstaged_delta.py + check_precommit_orphans.py)
YALNIZCA tespit eder: kapılardan biri commit'i bloklar, diğeri sonradan
kalıntıyı bulur. İkisi de pencere AÇILMADAN önce tek kopyayı dayanıklı
bir yere KOYMAYZ ve kayıp olduktan sonra OTOMATİK GERİ YÜKLEMEZ.

KALICI ÇÖZÜM (bu modül — üç katman)
-----------------------------------
1. **Yedek (pencere açılmadan):** `.git/hooks/pre-commit` sarmalayıcısı
   pre-commit'i çağırmadan ÖNCE `backup` çalıştırır: `git diff --binary`
   (worktree↔index = pre-commit'in stash'lediği tam delta) dayanıklı bir
   dizine, `.git/precommit-worktree-backups/<epochms>-<pid>/`, yazılır.
   Yedek alınamazsa ve delta BOŞ DEĞİLSE sarmalayıcı commit'i BLOKLAR
   (fail-closed: kayıp riski olan pencere kanıtlanabilir yedek yoksa
   açılmaz). Deltа boşsa hiçbir şey yazılmaz ve commit engellenmez.
2. **Geri yükleme (pencere kapandıktan):** sarmalayıcı pre-commit
   döndükten sonra `post` çalıştırır: delta ağacıysa yedek "tüketilmiş"
   işaretlenir; delta KAYIPSA yedekten `git apply` ile geri yüklenir ve
   GÜRÜLTÜLÜ uyarır (bu bir pre-commit arızasıdır — sessiz geçilmez).
   Apply başarısızsa yedek SİLİNMEZ ve exit 1 ile yol gösterilir.
3. **Kurtarma (ölen koşum):** sarmalayıcının `backup` adımı ÖNCE
   önceki koşulardan kalan, henüz tüketilmemiş yedekleri tarar: delta
   ağacıda değilse (`--reverse --check` temizlenmiyorsa) otomatik geri
   yükler. Böylece process-group kill sonrası delta bir sonraki commit'te
   KENDİLİĞİNDEN geri gelir — elle patch kazısı gerekmez.

NEDEN ÖZEL DİZİN, NEDEN DEĞİL `~/.cache/pre-commit`
--------------------------------------------------
pre-commit patch'leri ÖNBELLEKTİR ve pre-commit onları ASLA silmez ama
kimse de korumaz (yetim birikimi ~170 → check_precommit_orphans.py bunu
kanıtladı). Bu yedekler `.git/` altındadır: repo ile birliktedir, `git
clean` (izlenen/.git hariç) tarafından süpürülmez, `pre-commit clean`
dokunmaz ve worktree'yi KİRLİLENDİRMEZ (izlenen bir dosya değil,
`.git/` altındaki bir artefakt — kapıların "ağaç temiz" varsayımını
bozmaz).

NEDEN ANA-PID DEĞİL, OTOMATİK KURTARMA
---------------------------------------
`check_unstaged_delta.py` ata-pid eşleşmesiyle BU koşumun patch'ini
bulup bloklar — ama o zaten pencerenin İÇİNDEDİR (ağaç eşitlenmiştir);
orada delta'yı geri yüklemek zincirin geri kalan kapılarını karışık
ağaçta koşar ve pre-commit'in kendi finally-apply'iyle çakışır. Bu yüzden
geri yükleme yalnızca sarmalayıcının pencere DIŞINDAKİ adımında yapılır;
iç kapı yalnızca kalan yedekleri RAPORLAR (uyarı), geri yüklemez.

Sözleşme / çıkış kodları (CLI seam):
* `backup`  : 0 = yedek alındı VEYA delta boş (engellenecek bir şey yok);
              1 = delta var ama yedeklenemedi (fail-closed — sarmalayıcı
              commit'i bloklamalı).
* `post`    : 0 = delta ya korundu ya da geri yüklendi; 1 = geri
              yüklenemedi (yedek korunur, elle müdahale gerekir).
* `status`  : her zaman 0 (yalnız rapor); `--json` makine-okunur.
* `recover` : elle kurtarma; 0 = kurtarıldı/zaten var, 1 = uygulanamadı.

OFFLINE, stdlib-only. Yalnız `git` çağırır; worktree'ye YAZMAZ (yalnız
`.git/` altındaki kendi yedek dizinine).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
from typing import List, Optional

MARKER = "WORKTREE-GUARD-WRAPPER"  # sarmalayıcı dosyasının kimliği
KEEP_CONSUMED = 10  # tüketilmiş yedeklerden en fazla kaç tanesi saklanır
BACKUP_DIRNAME = "precommit-worktree-backups"


# ── git yardımcıları ────────────────────────────────────────────────────────

def _git(args: List[str], root: pathlib.Path, input_bytes: Optional[bytes] = None,
         check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args], cwd=str(root), input=input_bytes,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            "git %s başarısız (rc=%d): %s"
            % (" ".join(args), proc.returncode,
               (proc.stderr or b"").decode("utf-8", "replace").strip()))
    return proc


def repo_root() -> pathlib.Path:
    out = _git(["rev-parse", "--show-toplevel"], pathlib.Path.cwd()).stdout
    return pathlib.Path(out.decode("utf-8").strip())


def backup_root(root: pathlib.Path) -> pathlib.Path:
    """`.git/` altındaki dayanıklı yedek kökü — worktree'yi kirletmez.

    `git rev-parse --git-path` worktree başına doğru dizini verir (linked
    worktree'ler kendi `.git/worktrees/<ad>/` altına yazar).
    """
    out = _git(["rev-parse", "--git-path", BACKUP_DIRNAME], root).stdout
    path = pathlib.Path(out.decode("utf-8").strip())
    if not path.is_absolute():
        path = root / path
    return path


def unstaged_delta(root: pathlib.Path) -> bytes:
    """worktree↔index farkı, binary — pre-commit'in stash'lediği tam delta."""
    return _git(["diff", "--binary"], root).stdout


def unstaged_files(root: pathlib.Path) -> List[str]:
    out = _git(["diff", "--name-only"], root).stdout
    return [ln.strip() for ln in
            out.decode("utf-8", "replace").splitlines() if ln.strip()]


# ── yedek deposu ────────────────────────────────────────────────────────────

def _now_stamp() -> str:
    return "%d-%d" % (int(datetime.datetime.now().timestamp() * 1000),
                      os.getpid())


def write_backup(root: pathlib.Path, delta: bytes, files: List[str],
                 base: Optional[pathlib.Path] = None) -> pathlib.Path:
    base = base or backup_root(root)
    base.mkdir(parents=True, exist_ok=True)
    dest = base / _now_stamp()
    dest.mkdir(parents=True, exist_ok=False)
    (dest / "delta.patch").write_bytes(delta)
    head = _git(["rev-parse", "HEAD"], root).stdout.decode("utf-8").strip()
    manifest = {
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "pid": os.getpid(),
        "head": head,
        "files": files,
        "consumed": False,
        "bytes": len(delta),
    }
    (dest / "backup.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return dest


def list_backups(base: pathlib.Path) -> List[pathlib.Path]:
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir()
                  if p.is_dir() and (p / "delta.patch").is_file())


def read_manifest(dest: pathlib.Path) -> dict:
    try:
        return json.loads((dest / "backup.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def mark_consumed(dest: pathlib.Path) -> None:
    manifest = read_manifest(dest)
    manifest["consumed"] = True
    manifest["consumed_at"] = datetime.datetime.now().isoformat(
        timespec="seconds")
    (dest / "backup.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def prune_consumed(base: pathlib.Path) -> List[pathlib.Path]:
    """Tüketilmiş yedeklerden en eskileri sil (kanıt zaten ağaçta).

    ASLA tüketilmemiş yedek silinmez — onlar kayıp-kanıtıdır.
    """
    consumed = [p for p in list_backups(base) if read_manifest(p).get("consumed")]
    excess = consumed[:-KEEP_CONSUMED] if len(consumed) > KEEP_CONSUMED else []
    for path in excess:
        for name in ("delta.patch", "backup.json"):
            try:
                (path / name).unlink()
            except OSError:
                pass
        try:
            path.rmdir()
        except OSError:
            pass
    return excess


# ── delta var mı? kanıtı (check_precommit_orphans ile aynı yöntem) ──────────

def delta_in_tree(root: pathlib.Path, delta: bytes) -> bool:
    """Delta'nın tamamı ağaçta mı? `git apply --reverse --check` kanıtı.

    Temiz dönüş = patch'in SONRASI durum ağaçta = delta kaybolmamış.
    Boş delta asla "var" sayılmaz (boş patch her zaman reverse-uygulanır).
    """
    if not delta.strip():
        return False
    proc = _git(["apply", "--reverse", "--check", "--"], root,
                input_bytes=delta, check=False)
    return proc.returncode == 0


def applyable(root: pathlib.Path, delta: bytes) -> bool:
    proc = _git(["apply", "--check", "--"], root,
                input_bytes=delta, check=False)
    return proc.returncode == 0


def apply_delta(root: pathlib.Path, delta: bytes) -> None:
    _git(["apply", "--whitespace=nowarn", "--"], root,
         input_bytes=delta)


# ── komutlar ────────────────────────────────────────────────────────────────

def unrecovered(base: pathlib.Path, root: pathlib.Path) -> List[tuple]:
    """Tüketilmemiş yedekler → (dest, manifest, delta, kurtarılabilir-mi).

    Sıra: en yeni önce (sonraki commit en son kaybı onarsın).

    NOT: `applyable` burada TAHMİNDİR — bir yedeği uyguladıktan sonra
    ağacın durumu değiştiği için sonraki yedeklerin uygulanabilirliği
    yeniden ölçülür (bkz. cmd_backup/cmd_post'taki taze kontrol). Eski
    ölçümle karar verilseydi örtüşen deltalarda "çakışma" UYARISI
    yanlış-pozitif üretirdi.
    """
    out = []
    for dest in reversed(list_backups(base)):
        manifest = read_manifest(dest)
        if manifest.get("consumed"):
            continue
        try:
            delta = (dest / "delta.patch").read_bytes()
        except OSError:
            continue
        out.append((dest, manifest, delta, applyable(root, delta)))
    return out


def cmd_backup(root: pathlib.Path, base: pathlib.Path) -> int:
    # 1) önceki koşulardan kalan yedekleri KURTAR (pencere henüz açılmadı)
    recovered = 0
    for dest, manifest, delta, _stale_can_apply in unrecovered(base, root):
        if delta_in_tree(root, delta):
            mark_consumed(dest)  # zaten ağaçta — kanıtlandı, tüket
            continue
        # TAZE ölç: bir önceki yedeğin uygulanması ağacı değiştirmiş olabilir.
        if not applyable(root, delta):
            print("⚠️  worktree-guard: soluyan yedek KURTARILAMADI "
                  "(çakışma): %s" % dest)
            print("     dosyalar: %s" % ", ".join(manifest.get("files", [])))
            print("     elle: git apply %s" % (dest / "delta.patch"))
            continue
        apply_delta(root, delta)
        recovered += 1
        mark_consumed(dest)
        print("🔁 worktree-guard: önceki koşumun KAYIP unstaged deltasi "
              "geri yüklendi (%d dosya): %s"
              % (len(manifest.get("files", [])), dest))
        print("   %s" % ", ".join(manifest.get("files", [])))

    # 2) bu koşum için yeni yedek al
    delta = unstaged_delta(root)
    if not delta.strip():
        print("worktree-guard: unstaged delta yok — yedek gerekmedi.")
        return 0
    files = unstaged_files(root)
    try:
        dest = write_backup(root, delta, files, base=base)
    except OSError as exc:
        print("HATA: worktree-guard yedeklenemedi: %s" % exc, file=sys.stderr)
        print("  delta var (%d dosya: %s) ve pencere AÇILMADI." %
              (len(files), ", ".join(files)), file=sys.stderr)
        print("  commit ENGELLENDİ (fail-closed: kanıtlanabilir yedek yokken "
              "kayıp-penceresi açılmaz).", file=sys.stderr)
        return 1
    prune_consumed(base)
    print("worktree-guard: %d dosyalık unstaged delta yedeklendi → %s"
          % (len(files), dest))
    if recovered:
        print("worktree-guard: (%d önceki kayıp da geri yüklendi)" % recovered)
    return 0


def cmd_post(root: pathlib.Path, base: pathlib.Path) -> int:
    """Pencere kapandı: delta korundu mu? Kayıpsa geri yükle."""
    pending = [t for t in unrecovered(base, root)]
    if not pending:
        return 0
    # Bu koşumun yedeği en yenisidir; önce onu tüket, sonra eski kalanları
    # (pre-commit'in kendi patch'i onları zaten geri koymuş olabilir).
    dest, manifest, delta, _ = pending[0]
    if delta_in_tree(root, delta):
        mark_consumed(dest)
        rest = pending[1:]
    else:
        # TAZE ölç: bu koşumun yedeği en yenisi, ama yine de güncelle.
        can_apply = applyable(root, delta)
        if can_apply:
            apply_delta(root, delta)
            mark_consumed(dest)
            print("⚠️  worktree-guard: pre-commit unstaged deltayı geri "
                  "KOYMADI (finally-apply arızası?) — yedekten otomatik "
                  "geri yüklendi. Bu bir pre-commit olayıdır; kaydı için "
                  "_calisma/CIKTI/recovery_patches_<tarih>/ desenini izle.")
            print("   %s" % ", ".join(manifest.get("files", [])))
            rest = pending[1:]
        else:
            print("HATA: worktree-guard: delta KAYIP ve yedek "
                  "UYGULANAMIYOR (çakışma): %s" % dest, file=sys.stderr)
            print("  dosyalar: %s" % ", ".join(manifest.get("files", [])),
                  file=sys.stderr)
            print("  elle: git apply %s" % (dest / "delta.patch"),
                  file=sys.stderr)
            return 1
    # eski, hâlâ tüketilmemiş yedekler: delta ağaçtaysa tüket, değilse raporla
    for old_dest, old_manifest, old_delta, _ in rest:
        if delta_in_tree(root, old_delta):
            mark_consumed(old_dest)
        elif applyable(root, old_delta):
            apply_delta(root, old_delta)
            mark_consumed(old_dest)
            print("🔁 worktree-guard: eski yedek de geri yüklendi: %s"
                  % old_dest)
        else:
            print("⚠️  worktree-guard: eski yedek çözülemedi (elle incele): "
                  "%s (%s)" % (old_dest,
                               ", ".join(old_manifest.get("files", []))))
    prune_consumed(base)
    return 0


def cmd_recover(root: pathlib.Path, base: pathlib.Path) -> int:
    """Elle kurtarma: tüketilmemiş tüm yedekleri uygulamayı dene."""
    rc = 0
    for dest, manifest, delta, _ in unrecovered(base, root):
        if delta_in_tree(root, delta):
            mark_consumed(dest)
            print("zaten ağaçta: %s" % dest)
            continue
        if not applyable(root, delta):
            print("UYGULANAMADI (çakışma): %s — %s"
                  % (dest, ", ".join(manifest.get("files", []))),
                  file=sys.stderr)
            rc = 1
            continue
        apply_delta(root, delta)
        mark_consumed(dest)
        print("geri yüklendi: %s (%s)"
              % (dest, ", ".join(manifest.get("files", []))))
    return rc


def classify_backups(base: pathlib.Path, root: pathlib.Path) -> dict:
    """Yedekleri üç duruma ayır (tek ölçüm, iki kullanımda tutarlı).

    * `pending`     : tüketilmemiş VE ağaçta DEĞİL → KAYIP; kurtarma gerek.
                      (status raporunun ve delta-kapısı uyarısının tek
                      kaynağı; in-tree yedek buraya asla girmez — o ya
                      uçuş-taze (pencere açık) ya da henüz tüketilmemiş
                      bir geri-yüklemenin artığıdır.)
    * `in_flight`   : tüketilmemiş ama delta ağaçta → normal (backup/post
                      çifti arasında pencere; ya da kurtarılmış-artık).
    * `unrecoverable`: kayıp ama uygulanamıyor (çakışma) → elle müdahale.
    """
    pending, in_flight, unrecoverable = [], [], []
    for dest in reversed(list_backups(base)):
        manifest = read_manifest(dest)
        if manifest.get("consumed"):
            continue
        try:
            delta = (dest / "delta.patch").read_bytes()
        except OSError:
            continue
        row = {"path": str(dest), "created": manifest.get("created"),
               "head": manifest.get("head"),
               "files": manifest.get("files", []), "bytes": len(delta)}
        if delta_in_tree(root, delta):
            in_flight.append(row)
        elif applyable(root, delta):
            pending.append(row)
        else:
            row["reason"] = "çakışma — elle bak"
            unrecoverable.append(row)
    return {"pending": pending, "in_flight": in_flight,
            "unrecoverable": unrecoverable}


def cmd_status(root: pathlib.Path, base: pathlib.Path,
               as_json: bool = False) -> int:
    groups = classify_backups(base, root)
    if as_json:
        print(json.dumps({"ok": True, "backup_root": str(base),
                          **groups}, ensure_ascii=False, indent=2))
        return 0
    total = sum(len(v) for v in groups.values())
    if not total:
        print("worktree-guard: çözülmemiş yedek YOK (%s)" % base)
        return 0
    if groups["pending"]:
        print("worktree-guard: %d KAYIP yedek — kurtarma gerek (%s)"
              % (len(groups["pending"]), base))
        for row in groups["pending"]:
            print("  KAYIP   %s  [%s]"
                  % (row["path"], ", ".join(row["files"])))
    if groups["in_flight"]:
        print("worktree-guard: %d uçuş-taze yedek (delta ağaçta — normal)"
              % len(groups["in_flight"]))
        for row in groups["in_flight"]:
            print("  TAZE    %s  [%s]"
                  % (row["path"], ", ".join(row["files"])))
    if groups["unrecoverable"]:
        print("worktree-guard: %d ÇAKIŞMA — elle incele:"%
              len(groups["unrecoverable"]))
        for row in groups["unrecoverable"]:
            print("  ÇAKIŞMA %s  [%s]"
                  % (row["path"], ", ".join(row["files"])))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="pre-commit unstaged-delta yedekleme/geri yükleme "
                    "(kayıp-penceresi kalıcı çözümü)")
    parser.add_argument("command",
                        choices=("backup", "post", "status", "recover"))
    parser.add_argument("--root", default=None,
                        help="repo kökü (varsayılan: mevcut worktree)")
    parser.add_argument("--backup-dir", default=None,
                        help="yedek kökü (test izolasyonu; varsayılan: "
                             ".git/%s)" % BACKUP_DIRNAME)
    parser.add_argument("--json", action="store_true",
                        help="status: makine-okunur JSON")
    args = parser.parse_args(argv)

    try:
        root = (pathlib.Path(args.root).expanduser()
                if args.root else repo_root())
        root = root.resolve()
        base = (pathlib.Path(args.backup_dir).expanduser()
                if args.backup_dir else backup_root(root))
    except (RuntimeError, OSError) as exc:
        print("HATA: %s" % exc, file=sys.stderr)
        return 2

    try:
        if args.command == "backup":
            return cmd_backup(root, base)
        if args.command == "post":
            return cmd_post(root, base)
        if args.command == "recover":
            return cmd_recover(root, base)
        return cmd_status(root, base, as_json=args.json)
    except RuntimeError as exc:  # git hatası — fail-closed, sessiz yok
        print("HATA: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
