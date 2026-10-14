#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_delivery_hook.py — verify-delivery hook'unun ön-kontrolü.

verify-delivery hook'u (`language: system`, `pass_filenames: false`)
ÇALIŞMA AĞACINI test eder; `git commit` ise STAGE'LENEN içeriği alır.
Bağımlılık dosyalarının (verify_delivery.py — test edilen doğrulayıcı,
verify_delivery.config.json + şema — denetlenen config, TESLIM zipleri + .sha256
— K1/K2 girdileri) stage edilmemiş değişiklikleri varsa hook, commit edilecek
sürümden FARKLI bir sürümü test edebilir. Bu ön-kontrol o durumu NET bir
uyarıyla görünür yapar (advisory — doğrulama yine de koşar, exit kodu
doğrulama sonucunu yansıtır).

Kullanım (pre-commit entry):
    python3 _calisma/CIKTI/verify_delivery_hook.py

Davranış:
  1. Bağımlılık dosyaları için `git status --porcelain` ile stage durumu
     denetlenir: '??' (untracked) veya iş-ağacı sütununda 'M' (unstaged /
     staged+unstaged) → uyarı listesine girer; yalnızca staged ('M ') temizdir.
  2. Uyarı varsa net bir blok basılır (advisory).
  3. Asıl kapı koşulur: verify_delivery.py --dir _calisma/CIKTI
     --strict-determinism. Exit kodu korunur.

Faz 4 bağlamı — DEPS listesi neden kanonik çekirdeği ve kabul defterini de
kapsar: K6-DETERM'in strict karşılaştırması (a) `pdf_id_canonical.py` ile
`/ID`-nötr hash'i hesaplar ve (b) referansı `docs/ID_RESIDUAL_ACCEPTANCE.md`
§4 tablosundan okur. İkisi de stage'lenmemişse hook, commit'lenenden FARKLI
çekirdek ve FARKLI defter karşısında yeşil verebilir — DEPS'in var oluş
nedeni tam olarak bu sınıf kaymadir. K6-DETERM'in varsayılanı zaten strict
olsa da bayrak AÇIKÇA geçirilir: sözleşme varsayılana değil ilana
dayanmalı; varsayılan çevrildiğinde kapı sessizce kapanmasın.
"""
import pathlib
import subprocess
import sys

CIKTI = pathlib.Path(__file__).resolve().parent

sys.path.insert(0, str(CIKTI))
import hook_unstaged_deps as hud  # noqa: E402

# Hook'un test ettiği ve commit'in içeriğini belirleyen bağımlılıklar.
DEPS = [
    "_calisma/CIKTI/verify_delivery.py",                  # test edilen doğrulayıcı
    "_calisma/CIKTI/pdf_id_canonical.py",                 # K6-DETERM /ID-kanonik çekirdeği
    "docs/ID_RESIDUAL_ACCEPTANCE.md",                     # kabul defteri (§4 kanonik referans)
    "_calisma/CIKTI/verify_delivery.config.json",         # denetlenen config
    "_calisma/CIKTI/verify_delivery.config.schema.json",  # config şeması
    "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip",     # K1 girdisi
    "_calisma/CIKTI/TESLIM_KLASOR_V5_2026-08-17.zip.sha256",
    "_calisma/CIKTI/TESLIM_V5_FINAL_2026-08-17.zip",      # K2 girdisi
    "_calisma/CIKTI/TESLIM_V5_FINAL_2026-08-17.zip.sha256",
]


def unstaged_deps():
    """Bağımlılık dosyalarının stage durumu ({rel: durum})."""
    return hud.unstaged_deps(DEPS)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    strict = "--strict" in argv
    dirty = unstaged_deps()
    if dirty:
        if strict:
            # Fail-closed: stage edilen sürümle aynı içerik test edilemez.
            return hud.block_strict("verify-delivery", dirty)
        hud.print_warning("verify-delivery", dirty)
    # Asıl kapı: --strict-determinism AÇIKÇA geçer (varsayılan zaten True;
    # sözleşme ölçülebilir olsun — ilan bayrağa değil varsayılana
    # bağlanırsa bir gün çevrildiğinde kapı sessizce kapanır).
    r = subprocess.run(
        [sys.executable, str(CIKTI / "verify_delivery.py"),
         "--dir", "_calisma/CIKTI", "--strict-determinism"])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
