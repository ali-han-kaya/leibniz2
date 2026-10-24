# Stoic-Hume V5 — doğrulama süpürmesi (tek komut, tek verdict).
#
#   make verify         # cache-clean + token kapısı + build + batarya → SWEEP: PASS/FAIL
#   make verify-list    # adımların sözlüğü (komutlar dahil)
#   make verify DRY=1   # planı göster, hiçbir adımı koşma
#   make verify ONLY=tokens,build
#
#   make local-verify           # EN GENİŞ: ortam + taze dashboard-next derlemesi
#                                # + süpürme + commit zinciri + ağaç envanteri
#   make local-verify FAST=1     # commit zincirini (hooks) atla
#   make local-verify REBUILD=1  # derleme taze olsa da yeniden derle
#   make local-verify ONLY=build,tree
#
# Mantık `_calisma/CIKTI/verify_sweep.py`'de (stdlib-only, test edilebilir):
# bu Makefile yalnız ince giriş noktasıdır — kabuk mantığı taşımaz, bu yüzden
# adım eklemek/çıkarmak Makefile'a dokunmayı gerektirmez.
#
# Tek yetkili verdict EKRANDAKİ `SWEEP: PASS/FAIL` satırıdır. Çıkış kodu: make
# PASS'te 0, kırık recipe'de KENDİ koduyla 2 döndürür (make sözleşmesi) —
# yani fail-closed korunur ama 2, koşucunun "kullanım hatası" 2'siyle
# karıştırılmasın; betiği doğrudan koşarsan kırık adım 1 döner.
PY ?= python3
SWEEP := $(PY) _calisma/CIKTI/verify_sweep.py
LOCAL := $(PY) _calisma/CIKTI/local_verify.py

.PHONY: verify verify-list local-verify

verify:
	@$(SWEEP) $(if $(DRY),--dry-run,) $(if $(ONLY),--only $(ONLY),)

verify-list:
	@$(SWEEP) --list

# Yerel tek komut: adımlar `local_verify.py`'de (stdlib-only, test edilebilir;
# `test_verify_sweep.py` sözleşmeyi pinler). Bu hedef yalnız bayrak geçirir.
local-verify:
	@$(LOCAL) $(if $(FAST),--fast,) $(if $(REBUILD),--rebuild,) $(if $(ONLY),--only $(ONLY),)
