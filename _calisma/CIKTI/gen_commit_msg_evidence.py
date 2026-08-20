#!/usr/bin/env python3
"""gen_commit_msg_evidence.py — commit-msg hook blokaj kanıtı üretir.

commit_msg_hook.sh'i çeşitli test mesajlarıyla çalıştırır ve her birinin
bloke/izin durumunu COMMIT_MSG_BLOCK_EVIDENCE.md olarak raporlar.

Bu belge CI'da periyodik olarak yeniden üretilir; hook kuralları
değişirse kanıt da değişir — değişmezse kanıt sabit kalır (deterministik).

Kullanım:
  python3 gen_commit_msg_evidence.py [--out COMMIT_MSG_BLOCK_EVIDENCE.md]
"""
import argparse
import pathlib
import subprocess
import sys
import tempfile
import datetime

HERE = pathlib.Path(__file__).resolve().parent
HOOK = HERE / "commit_msg_hook.sh"

# (mesaj_satırı, beklenen_davranış, açıklama)
# blocked=True → hook exit 1 vermeli (bloke)
# blocked=False → hook exit 0 vermeli (izin)
TEST_CASES = [
    # ── Geçerli başlıklar (izin verilmeli) ──
    ("fix: null pointer deerference", False, "geçerli conventional commit"),
    ("docs: README güncelleme", False, "geçerli kapsam + eylem"),
    ("feat(auth): OAuth desteği ekle", False, "geçerli kapsam alt kapsam"),
    ("Merge branch 'main' into feature", False, "git merge başlığı (izinli)"),
    ("Revert \"feat: X ekle\"", False, "git revert başlığı (izinli)"),
    ("refactor: modül yeniden düzenle", False, "geçerli refactor"),
    ("chore: bağımlılık güncelle", False, "geçerli chore"),
    # ── Bloke edilmesi gereken başlıklar ──
    ("WIP", True, "WIP başlık yasak"),
    ("wip: bir şey", True, "wip: önekli yasak"),
    ("fix: WIP bir şey", True, "WIP kelimesi içeren yasak"),
    ("test marker: deneme", True, "test marker yasak"),
    ("test: deneme", True, "test: noise yasak"),
    ("test", True, "tek Kelime test yasak"),
    ("smoke test", True, "smoke başlık yasak"),
    ("fix typo", True, "fix typo noise"),
    ("minor fix", True, "minor fix noise"),
    ("temp", True, "temp noise yasak"),
    ("tmp", True, "tmp noise yasak"),
    ("foo", True, "foo noise yasak"),
    ("bar", True, "bar noise yasak"),
    ("lorem ipsum dolor sit amet", True, "lorem ipsum noise yasak"),
    ("asdf", True, "asdf noise yasak"),
    # ── Format hataları ──
    ("duzgun baslik yok", True, "iki nokta + boşluk formatı yok"),
    ("fix:single_space_yok", True, "iki nokta sonrası boşluk yok"),
    ("<type>: placeholder düzenlenmemiş", True, "şablon placeholder'ı var"),
    # ── Uzunluk ──
    ("fix: " + "a" * 67, False, "72 karakter (sınırda, izin)"),
    ("fix: " + "a" * 68, True, "73 karakter (aşım, bloke)"),
    # ── Boş mesaj ──
    ("", True, "boş mesaj bloke"),
]


def test_message(msg: str, hook_path: str) -> int:
    """Hook'u mesajla çalıştır, exit kodunu döndür."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False) as f:
        f.write(msg + "\n")
        f.flush()
        try:
            r = subprocess.run(["sh", hook_path, f.name],
                               capture_output=True, text=True, timeout=5)
            return r.returncode
        finally:
            pathlib.Path(f.name).unlink(missing_ok=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="COMMIT_MSG_BLOCK_EVIDENCE.md",
                    help="Çıktı dosyası (varsayılan: COMMIT_MSG_BLOCK_EVIDENCE.md)")
    args = ap.parse_args(argv)

    if not HOOK.exists():
        print(f"HATA: hook bulunamadı: {HOOK}", file=sys.stderr)
        return 1

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = []
    for msg, expected_block, description in TEST_CASES:
        rc = test_message(msg, str(HOOK))
        actually_blocked = (rc != 0)
        ok = (actually_blocked == expected_block)
        results.append((msg, expected_block, actually_blocked, ok, description))

    # Rapor üret
    lines = [
        "# COMMIT_MSG_BLOCK_EVIDENCE.md",
        "",
        f"Üretim zamanı: {now}",
        f"Hook: `_calisma/CIKTI/commit_msg_hook.sh`",
        f"Test sayısı: {len(results)}",
        "",
        "## Test Sonuçları",
        "",
        "| # | Mesaj | Beklenen | Gerçek | Durum | Açıklama |",
        "|---|-------|----------|--------|-------|----------|",
    ]

    pass_count = sum(1 for r in results if r[3])
    fail_count = len(results) - pass_count

    for i, (msg, exp_block, act_block, ok, desc) in enumerate(results, 1):
        status = "✅" if ok else "❌"
        exp_label = "BLOKE" if exp_block else "İZİN"
        act_label = "BLOKE" if act_block else "İZİN"
        msg_display = msg if msg else "_(boş)_"
        # Markdown tablosu için pipe karakterini escape et
        msg_display = msg_display.replace("|", "\\|")
        if len(msg_display) > 50:
            msg_display = msg_display[:47] + "..."
        lines.append(f"| {i} | `{msg_display}` | {exp_label} | {act_label} | {status} | {desc} |")

    lines += [
        "",
        "## Özet",
        "",
        f"- **Toplam test:** {len(results)}",
        f"- **Başarılı:** {pass_count}",
        f"- **Başarısız:** {fail_count}",
        "",
    ]

    if fail_count == 0:
        lines.append("**SONUÇ: PASS** — tüm testler beklenen davranışı üretiyor.")
    else:
        lines.append(f"**SONUÇ: FAIL** — {fail_count} test beklenen davranışı üretmiyor.")
        lines.append("")
        lines.append("Başarısız testler:")
        for i, (msg, exp_block, act_block, ok, desc) in enumerate(results, 1):
            if not ok:
                msg_display = msg if msg else "_(boş)_"
                lines.append(f"- #{i}: `{msg_display}` — beklenen: {'BLOKE' if exp_block else 'İZİN'}, "
                             f"gerçek: {'BLOKE' if act_block else 'İZİN'}")

    lines += [
        "",
        "---",
        "Otomatik üretilmiştir. Hook kuralları değişirse bu dosya da değişir.",
        f"Son yenileme: {now}",
        "",
    ]

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"COMMIT_MSG_BLOCK_EVIDENCE.md üretildi: {len(results)} test, "
          f"{pass_count} PASS, {fail_count} FAIL")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
