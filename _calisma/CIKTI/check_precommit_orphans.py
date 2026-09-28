#!/usr/bin/env python3
"""check_precommit_orphans.py — pre-commit patch-kalıntısı kapısı (fail-closed).

Kök-neden (systematic-debugging turu, 2026-09-19): pre-commit unstaged
deltayı ~/.cache/pre-commit/patch<epoch>-<pid> dosyasına stash'leyup
`git checkout -- .` ile siler; geri-uygulama yalnız finally-bloğunda
yapılır. Pencere-içi süreç-ölümü → ağaç sessizce revert olur ve delta
yalnız patch-dosyasında kalır. pre-commit patch dosyalarını ASLA silmez
(kaynakta unlink yok) → yetimler birikir (~170 bulundu).

Sözleşme (tdd turu, seam = kapı CLI'si):
- PRE_COMMIT_HOME env'i varsa o dizin (pre-commit'in kendi override'ı),
  yoksa ~/.cache/pre-commit denetlenir.
- 24s+ yaşlı patch → exit 1; çıktı dosyayı adlar ve kurtarma-protokolünü
  söyler (patch = kurtarma-artefaktı: arşivle veya sil, dış-aktör-değil).
- Taze patch (<24s) → exit 0 (az-önce ölen koşumun tek kurtarma-aracı
  olabilir; cezalandırılmaz) — ama içeriği arşivle birebir eşleşiyorsa
  tekrar-olay uyarısı basılır ve yine exit 0 kalır.
- Arşiv parmak-izleri `recovery_patches_*` dizinlerinin TAMAMINDAN gelir
  (2026-09-27 düzeltmesi: eskiden tek dizin sabitti — 09-18 arşivi görünür,
  09-20 ve 09-26 arşivleri görünmezdi; aynı delta'nın sonraki kopyaları
  KNOWN-INCIDENT etiketi almıyordu). Arşivsizlik tek başına blok değildir,
  ama çıktı \"parmak-izi yok\" diyerek etiketsizliği görünür kılar.
- Dizin boş/yok → exit 0.

Otomatik karantina (2026-09-28 turu) — yetimler BİRİKİR; elle temizlik
ölçeklenmez, ama körlemesine silmek VERİ KAYBIDIR. Bu yüzden kanıtlanmış
gereksiz yetimler taşınır, geri kalanı elle incelemeye kalır:

- **Kanıt 1 — `rev-apply` (kesin):** `git apply --reverse --check` temiz
  dönüyorsa ağaç, patch'in SONRASI durumdadır → patch'in içeriği zaten
  ağaçta; kaybedilecek bir şey yok. (53 arşiv patch'inde ölçüldü: 12/53.)
- **Kanıt 2 — `+lines`:** patch'in `+` satırlarının TÜMÜ hedef dosyada
  (çokluk-farkında, dosya-başına) bulunuyorsa delta uygulanmış demektir.
  Kısa/boş/brace-only satırlar (`}`, `#`, boş…) kanıt SAYILMAZ: aksi halde
  \"satır zaten var\" tesadüfü yanlış-pozitif üretirdi. En az bir anlamlı
  eklenen satır şarttır. (Ölçüldü: 23/53; iki kanıt farklı yönlerde
  ayrışır — birlikte kullanılırlar.)
- **HUNK ŞARTI:** hiç `@@` hunk'ı olmayan patch ASLA temizlenmez. Ölçüldü:
  `git apply --check` BOŞ/yalnız-header diff'te 0 döndürür (uygulanacak
  değişiklik yok) — guard olmadan \"redundant\" sanılırdı; kapının kendi
  regresyon fixture'ı da tam olarak `diff --git a/x b/x` (hunksız).
- **ASLA temizlenmez:** KNOWN-INCIDENT ve ZAYIF-PARMAK-İZİ patch'leri.
  Etiket UYARI'dır, muafiyet değil (AGENTS.md): bu kayıtlar olayın
  TEKRARLADIĞININ kanıtıdır; otomatik taşımak tekrar-sinyalini silerdi.
- **ASLA dokunulmaz:** taze patch'ler. Kurtarma-penceresi içindedirler ve
  pre-commit'in kendi uçuş-içi stash'i olabilirler.
- **Taşıma, silme değil:** kanıtlananlar `<cache>-orphans-quarantine-<tarih>/`
  altına TAŞINIR (aynı adlı dosya `shutil.move` ile korunur) ve yanına
  sha256+md5+kanıt+yaş kaydıyla `MANIFEST.md` yazılır → taşıma geri
  alınabilir (AGENTS.md: \"silme yerine karantina\"). Özetler STDERR/STDOUT'a
  basılmaz (eşleşme yokken özet gürültüsü operatörü kırmızıyı kaçırtır) —
  yalnız MANIFEST dosyasına yazılır.
- Karantinadan sonra elle inceleme gerektiren yetim kalmadıysa exit 0
  (commit bloklanmaz: kanıt var); kaldıysa exit 1.

Exit: 0 = kurtarma-penceresi temiz VEYA yalnız kanıtlanmış yetimler vardı
(karantinaya alındı), 1 = incelenmemiş yetim var (fail-closed),
2 = kullanım hatası.
"""

import argparse
import collections
import datetime
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import NamedTuple

WINDOW_HOURS = 24
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
# Arşiv dizinleri tarih damgalıdır (recovery_patches_20260918, …_20260920,
# …_20260926, …_20260927): desen GLOB'dur, tek dizin sabitlenmez — yeni arşiv
# eklendiğinde parmak-izi kaynağı kendiliğinden genişler.
ARCHIVE_GLOB = "recovery_patches_*"

# Tanı etiketleri. Sıra sözleşmedir: KNOWN yalnız sha256 birebir eşleşmesi
# üretir; WEAK yalnız md5 eşleşip sha256 düştüğünde (etiket DEĞİLDİR).
KNOWN = "known-incident"
WEAK = "weak-md5-only"
NONE = None

# ── otomatik karantina sözleşmesi (modül başlığında gerekçesi) ─────────────
QUARANTINE_SUFFIX = "-orphans-quarantine-"
# Kanıt eşiği: bundan kısa/normalize-edilince boşalan satır kanıt sayılmaz.
MIN_SUBSTANTIVE_CHARS = 4
EVIDENCE_REVERSE = "rev-apply"
EVIDENCE_LINES = "+lines"
_FILE_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$")
_HUNK_RE = re.compile(r"^@@ .* @@")
# Etiketli kayıtlar taşınmaz: olayın tekrar ettiğinin kanıtıdırlar.
PROTECTED_LABELS = (KNOWN, WEAK)


class Fingerprints(NamedTuple):
    """Olay-arşivinin çift parmak-izi haritası (TEK okuma, iki hesap).

    İki ayrı okuma yapılsa dosya arada değişirse haritalar birbirini
    tutmazdı — "birebir aynı" yargısı sessizce yanlışlaşırdı.
    """

    sha256: dict
    md5: dict
    archives: list
    patch_count: int


def cache_dir() -> pathlib.Path:
    home = os.environ.get("PRE_COMMIT_HOME")
    return pathlib.Path(home) if home else pathlib.Path.home() / ".cache" / "pre-commit"


def digests(data: bytes) -> tuple:
    """(sha256, md5) — ikisi de aynı baytlardan.

    md5 kasıtlı olarak güvenlik-dışı işaretlenir (FIPS çekirdeklerde
    `hashlib.md5()` reddedilebilir): burada kimlik etiketi üretir,
    bütünlük güvencesi sağlamaz — o rol sha256'nindir.
    """
    return (
        hashlib.sha256(data).hexdigest(),
        hashlib.md5(data, usedforsecurity=False).hexdigest(),
    )


def archive_fingerprints() -> Fingerprints:
    """Tüm arşiv dizinlerinden çift parmak-izi.

    Aynı içerik birden çok arşivde olabilir (tekrar eden olay): hepsi
    listelenir, böylece kurtarma yolu tek bir dizine bağlı kalmaz.
    """
    by_sha: dict = {}
    by_md5: dict = {}
    archives = []
    count = 0
    for directory in sorted(HERE.glob(ARCHIVE_GLOB)):
        if not directory.is_dir():
            continue
        archives.append(directory.name)
        for patch in sorted(directory.glob("patch*")):
            if not patch.is_file():
                continue
            try:
                sha, md5 = digests(patch.read_bytes())
            except OSError as exc:  # arşiv okunamazsa etiketleme eksilir → görünür olsun
                print(f"UYARI: arşiv patch'i okunamadı: {patch} ({exc})")
                continue
            loc = f"{directory.name}/{patch.name}"
            by_sha.setdefault(sha, []).append(loc)
            by_md5.setdefault(md5, []).append(loc)
            count += 1
    return Fingerprints(sha256=by_sha, md5=by_md5, archives=archives,
                        patch_count=count)


def classify(prints: Fingerprints, sha: str, md5: str):
    """(sha256, md5) → (etiket, arşiv konumları).

    Sıra sözleşmedir. sha256 birebir eşleşmesi tek otoritedir: aynı
    içerik demektir, "bilinen olay" etiketi doğar. sha256 düştüyse md5'e
    bakılır, ama o eşleşme WEAK'tır — md5 çakışabildiği için etiket
    üretmez, yalnız "içerik farklı ama özet aynı" ayrımını görünür kılar.
    """
    exact = prints.sha256.get(sha)
    if exact:
        return KNOWN, exact
    weak = prints.md5.get(md5)
    if weak:
        return WEAK, weak
    return NONE, []


# ── otomatik karantina: kanıt toplama ──────────────────────────────────────

def substantive(line: str) -> bool:
    """Satır KANIT olabilir mi? Kısa/boş/brace-only (`}`, `#`, `)`) sayılmaz.

    Bu eşik olmadan "+satır zaten dosyada var" tesadüfü yanlış-pozitif
    üretirdi: her dosyada boş satır ve `}` bulunur.
    """
    return len(line.strip()) >= MIN_SUBSTANTIVE_CHARS


def has_hunks(text: str) -> bool:
    """`@@` hunk header'ı var mı — yoksa patch ASLA otomatik temizlenmez.

    Ölçüldü: `git apply --check` BOŞ veya yalnız-`diff --git`-header
    patch'te 0 döndürür (uygulanacak değişiklik yok) → guard olmadan
    \"kanıtlanmış gereksiz\" sanılırdı. Kapının kendi regresyon fixture'ı da
    tam olarak `diff --git a/x b/x` (hunksız) biçimindedir.
    """
    return any(_HUNK_RE.match(line) for line in text.splitlines())


def added_lines(text: str) -> dict:
    """{yol: [eklenen satır…]} — yalnız `+` satırları.

    `+++`/`---` (dosya başlığı) ve `@@` (hunk başlığı) elenir; `-` satırları
    içerik taşımaz (silinen metin patch'in bilgisidir, ağaçta aranacak şey
    değildir) — kanıt yalnız EKLENENLER üzerinden kurulur.
    """
    files: dict = {}
    current = None
    for line in text.split("\n"):
        match = _FILE_RE.match(line)
        if match:
            current = match.group(2)
            files.setdefault(current, [])
            continue
        if current is None or line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            files[current].append(line[1:])
    return files


def reverse_applies(data: bytes, root) -> bool:
    """`git apply --reverse --check`: ağaç patch'in SONRASI durumda mı?

    Temiz dönüş = patch'in tüm değişiklikleri ağaçta zaten var → kesin
    kanıt (satır-sezgisinden güçlü). git yoksa/hata verirse kanıt YOK
    sayılır (fail-closed: kanıtlanamayan taşınmaz).
    """
    try:
        completed = subprocess.run(
            ["git", "apply", "--reverse", "--check", "--"],
            input=data, cwd=str(root), capture_output=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def redundancy_evidence(patch: pathlib.Path, root) -> str:
    """Kanıt türü (`rev-apply` | `+lines`) ya da None (kanıtlanamadı).

    İki bağımsız sinyal; farklı yönlerde ayrışırlar (ölçüldü: 53 arşiv
    patch'inde rev-apply 12, +satır 23 — ağaç sürüklendiğinde +satır daha
    bağışlayıcı, satır-eklemeyen bir patch'te rev-apply daha güçlü).
    """
    try:
        data = patch.read_bytes()
    except OSError:
        return None
    text = data.decode("utf-8", errors="replace")
    if not has_hunks(text):
        return None
    if reverse_applies(data, root):
        return EVIDENCE_REVERSE
    files = added_lines(text)
    if not any(substantive(line) for lines in files.values() for line in lines):
        return None  # yalnız önemsiz eklenen satırlar → kanıt kurulamaz
    for relative, lines in files.items():
        target = pathlib.Path(root) / relative
        try:
            have = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None  # hedef dosya yok → delta ağaçta değil
        needed = collections.Counter(line for line in lines if substantive(line))
        available = collections.Counter(line for line in have if substantive(line))
        if needed - available:
            return None  # eksik satır var → kanıtlanamadı
    return EVIDENCE_LINES


def quarantine_dir(cache: pathlib.Path) -> pathlib.Path:
    """`<cache>-orphans-quarantine-<YYYYMMDD>` — cache'in KARDEŞİ.

    Öntanımlı cache'te `~/.cache/pre-commit-orphans-quarantine-<tarih>`
    üretir (AGENTS.md'nin adlandırdığı dizin); testler PRE_COMMIT_HOME
    verdikleri için aynı kural geçici dizinde de birebir işler.
    """
    stamp = datetime.date.today().strftime("%Y%m%d")
    return cache.parent / (cache.name + QUARANTINE_SUFFIX + stamp)


def quarantine(cache: pathlib.Path, entries, prints: Fingerprints) -> list:
    """Kanıtlanmış yetimleri taşır ve MANIFEST.md'ye kaydını yazar.

    `entries`: [(patch, age_h, evidence)]. Özetler YALNIZ dosyaya yazılır —
    stdout'a basılan özet, eşleşme gürültüsüyle operatörü yanıltırdı.
    Döner: taşınan hedef yollar.
    """
    destination = quarantine_dir(cache)
    destination.mkdir(parents=True, exist_ok=True)
    moved = []
    records = []
    for patch, age_h, evidence in entries:
        data = patch.read_bytes()
        sha, md5 = digests(data)
        _, locations = classify(prints, sha, md5)
        target = destination / patch.name
        if target.exists():  # aynı adlı eski karantina kaydı → çakışmayı çöz
            target = destination / f"{patch.name}.{int(time.time())}"
        shutil.move(str(patch), str(target))
        moved.append(target)
        records.append(
            f"- `{patch.name}` → `{target.name}`\n"
            f"  - kanıt: {evidence}\n"
            f"  - yaş: {age_h:.1f}h\n"
            f"  - sha256: {sha}\n"
            f"  - md5: {md5}\n"
            f"  - arşiv eşleşmesi: {', '.join(locations) if locations else '—'}"
        )
    manifest = destination / "MANIFEST.md"
    block = (f"\n## {datetime.datetime.now().isoformat(timespec='seconds')} — "
             f"{len(moved)} patch\n\n- kaynak: `{cache}`\n\n"
             + "\n".join(records) + "\n")
    if manifest.exists():
        manifest.write_text(manifest.read_text(encoding="utf-8") + block,
                            encoding="utf-8")
    else:
        manifest.write_text(
            "# Pre-commit yetim patch karantinası (geri alınabilir)\n\n"
            "`check_precommit_orphans.py` yalnız KANITLANMIŞ gereksiz yetimleri "
            "buraya taşır; hiçbir kayıt silinmez.\n\n"
            "- geri alma: dosyaları `..` altındaki cache köküne geri taşı.\n"
            "- `rev-apply`: `git apply --reverse --check` temiz → ağaç patch'in "
            "sonrası durumda.\n"
            "- `+lines`: patch'in anlamlı `+` satırlarının tümü hedef dosyada var.\n"
            + block, encoding="utf-8")
    return moved


def select_cleanable(orphans, prints: Fingerprints, root, no_clean: bool):
    """(cleanable, kept) — yetimleri kanıt durumuna göre ayırır.

    Sıra sözleşmedir: etiket koruması KANITTAN ÖNCE gelir, çünkü KNOWN/WEAK
    kayıtları olayın tekrar ettiğinin kanıtıdır — kanıtlanmış olsalar bile
    taşınmazlar (etiket UYARI'dır, muafiyet değil; AGENTS.md).
    """
    cleanable, kept = [], []
    for patch, age_h in orphans:
        evidence = None
        if not no_clean:
            try:  # TEK okuma: iki okuma arasında dosya değişirse etiket kayardı
                sha, md5 = digests(patch.read_bytes())
            except OSError:
                sha = md5 = ""
            label, _ = classify(prints, sha, md5)
            if label not in PROTECTED_LABELS:
                evidence = redundancy_evidence(patch, root)
        if evidence:
            cleanable.append((patch, age_h, evidence))
        else:
            kept.append((patch, age_h))
    return cleanable, kept


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="pre-commit yetim patch kapısı (kanıtlanmış gereksizleri "
                    "karantinaya alır, kalanını fail-closed bloklar)")
    parser.add_argument("--no-clean", action="store_true",
                        help="otomatik karantinayı kapat (yalnız raporla/getir)")
    parser.add_argument("--root", default=str(ROOT),
                        help="kanıt ölçümünün kök dizini (test izolasyonu)")
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root)

    base = cache_dir()
    now = time.time()
    prints = archive_fingerprints()
    orphans = []
    incidents = []
    weak = []

    if base.is_dir():
        for patch in sorted(base.glob("patch*")):
            if not patch.is_file():
                continue
            try:
                age_h = (now - patch.stat().st_mtime) / 3600.0
                sha, md5 = digests(patch.read_bytes())
            except OSError as exc:
                print(f"UYARI: cache patch'i okunamadı: {patch} ({exc})")
                continue
            label, locs = classify(prints, sha, md5)
            is_orphan = age_h > WINDOW_HOURS
            if is_orphan:
                orphans.append((patch, age_h))
            if label == KNOWN:
                incidents.append((patch, age_h, sha, md5, locs, is_orphan))
            elif label == WEAK:
                weak.append((patch, age_h, md5, locs))

    # --- özel uyarı blokları: çıktının EN ÜSTÜNDE, yetim listesinden ÖNCE ---
    if incidents:
        print(f"⚠️  BİLİNEN OLAY PARMAK-İZİ (KNOWN-INCIDENT) — {len(incidents)} "
              "patch, içerik olay-arşiviyle BİREBİR aynı")
        for patch, age_h, sha, md5, locs, is_orphan in sorted(
                incidents, key=lambda x: -x[1]):
            durum = "yetim, kurtarma-penceresi dışı" if is_orphan else "taze"
            print(f"   {patch.name}: {age_h:.1f}h eski ({durum})")
            print(f"     arşiv: {', '.join(locs)}")
            print(f"     sha256: {sha}")
            print(f"     md5:    {md5}")
        fresh_n = sum(1 for x in incidents if not x[5])
        if fresh_n:
            # Taze eşleşme BLOKLANMAZ: az önce ölen koşumun tek kurtarma
            # aracı olabilir. Ama aynı delta daha önce de yetim kalmıştır →
            # sessiz geçmemeli.
            print(f"   ↳ {fresh_n} tanesi kurtarma-penceresi içinde "
                  "(<24h) — bloklamaz, tekrar sinyali")
        print("   ↳ aynı içerik arşivde duruyor: yeni veri kaybı değil; "
              "kaynağı doğrulamak için `git apply` ile denetle")

    if weak:
        print(f"⚠️  ZAYIF-PARMAK-İZİ ÇAKIŞMASI (md5 eşleşti, sha256 eşleşmedi) "
              f"— {len(weak)} patch")
        for patch, age_h, md5, locs in sorted(weak, key=lambda x: -x[1]):
            print(f"   {patch.name}: {age_h:.1f}h eski")
            print(f"     arşiv: {', '.join(locs)} (içerik FARKLI)")
            print(f"     md5:    {md5}")
        print("   ↳ md5 çakışabildiği için bu eşleşme bilinen-olay etiketi "
              "DEĞİLDİR ve tek başına kanıt sayılmaz; yalnız göz atmaya değer")

    if not orphans:
        return 0

    # --- kanıtlanmış gereksizleri TAŞI (silme değil), kalanı blokla ---
    cleanable, kept = select_cleanable(orphans, prints, root, args.no_clean)
    if cleanable:
        print("OTOMATİK KARANTİNA — kanıtlanmış gereksiz yetim (içerik ağaçta):")
        for patch, age_h, evidence in sorted(cleanable, key=lambda x: -x[1]):
            print(f"  {patch.name}: {age_h:.1f}h eski — kanıt={evidence}")
        try:
            moved = quarantine(base, cleanable, prints)
        except OSError as exc:
            print(f"  UYARI: karantina başarısız ({exc}) — yetimler yerinde kaldı, "
                  "blok sürüyor")
            kept = orphans
        else:
            print(f"  → {len(moved)} patch taşındı: {quarantine_dir(base)}")
            print("  → MANIFEST.md: sha256 + md5 + kanıt + yaş kaydı "
                  "(silme yok — geri taşınabilir)")
            print("  → bilinen-olay / zayıf-eşleşme kayıtları ve kanıtlanamayanlar "
                  "TAŞINMADI (elle inceleme)")

    if not kept:
        print("PRE-COMMIT PATCH ORPHANS: elle inceleme gerektiren yetim KALMADI "
              "(yalnız kanıtlanmış gereksizler vardı — karantinaya alındı).")
        return 0

    print("PRE-COMMIT PATCH ORPHANS (kurtarma-penceresi dışı kalıntı):")
    for patch, age_h in sorted(kept, key=lambda x: -x[1]):
        print(f"  {patch.name}: {age_h:.1f}h eski")
    print(f"arşiv parmak-izleri: {len(prints.archives)} dizin / "
          f"{prints.patch_count} patch (sha256 + md5)"
          + ("" if prints.patch_count else
             " — UYARI: arşiv yok/boş, parmak-izi üretilemedi (kontrol körleşti)"))
    print(
        "recovery: her patch, bir koşumun unstaged deltasidir (revert-olayi "
        "kanitidir, dis-aktor degil). Gerekmiyorsa sil; olay-arsivi icin "
        "_calisma/CIKTI/recovery_patches_<tarih>/ desenini izle."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
