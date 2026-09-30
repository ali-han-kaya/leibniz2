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
     --strict-determinism (Faz 4: determinizm referansı /ID-kanonik hash'tir
     ve kabul defterinde kayıtlı olmalıdır — defter `ID_RESIDUAL_LEDGER` env
     ile ya da repo/mirror kopyasıyla çözülür). Exit kodu korunur.
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
    # K6-DETERM /ID-kanonik çekirdeği + kabul defteri (determinizm
    # referansının TEK kaynağı). İkisi de stage edilmemişse strict kapı
    # commit edilecek sürümden FARKLI bir referansla koşardı.
    "_calisma/CIKTI/id_canonical.py",
    "docs/ID_RESIDUAL_ACCEPTANCE.md",
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
    # Asıl kapı: Faz 4'te strict determinizm AÇIK — K6-DETERM teslim PDF'inin
    # /ID-kanonik hash'ini kabul defterinde (docs/ID_RESIDUAL_ACCEPTANCE.md)
    # arar. Referans kayıtlı değilse P1 ile bloklar (defter = tek kaynak;
    # motor geçişi/yeniden paketleme bilinçli defter satırı ister).
    r = subprocess.run(
        [sys.executable, str(CIKTI / "verify_delivery.py"),
         "--dir", "_calisma/CIKTI", "--strict-determinism"])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
