#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""klayers_contract.py — klayers.json sözleşmesinin TEK sahibi.

verify_delivery.py --klayers-out şunu yazar:

    {"run_status": "PASS"|"FAIL",
     "layers": {"K<n>": {"label": str, "status": "PASS|FAIL|SKIP",
                          "ran": bool, "findings": [...]}}}

Bunu üreten (verify_delivery) ile okuyan (run_summary_klayers,
preview_server, preview.js, github_scripts/*.js) modüller aynı sözlüğü
paylaşır. Katman kümesi, anahtar adları ve bloklayan öncelikler burada
tanımlıdır — tüketiciler kendi listesini tutmaz.

SORUMLULUK: verify_delivery ÜRETİR (args'a bakar, bulguları böler),
run_summary_klayers GÖSTERİR, burası yalnızca sözlüğü tanımlar (I/O,
args, render yok). Verdict'in sahibi üreticidir: run_verdict() çalıştırılıp
`run_status` olarak yazılır, tüketiciler onu OKUR.

Yeni katman ekleme ve yüzeylerin neden ayrışabildiği:
docs/KLAYERS_PIPELINE.md. KATMAN EKLEME adımları:
skills/verify-chain/gen_k_layer.py.
"""


# ---- Sözleşmenin sabitleri -------------------------------------------------

# Kayıt dışı (hiçbir K katmanına düşmeyen) P0/P1'lerin toplandığı kova.
# Bu anahtar sidecar'ın KATMAN OLMAYAN tek girdisidir: status'u her zaman
# FAIL'tir, `ran` her zaman True'dur — katman koşmadıysa bile bulgu vardır.
OTHER_KEY = "UNREGISTERED"
OTHER_LABEL = "Unregistered findings"

# Katmanı FAIL yapan öncelikler. INFO görünür ama katmanı düşürmez
# (ör. --k0-toolkit-tolerant ile TOOLKIT zip'leri INFO olur) — bu yüzden
# "her bulgu bloklar" değil, "yalnız bunlar bloklar".
BLOCKING_PRIORITIES = ("P0", "P1")


# ---- Katman kayıtları -------------------------------------------------------

# TEK KAYNAK: katman kümesi + etiketleri. verify_delivery.py'nin docstring
# tablosu bu sözlüğü YANSITIR (insan-okunur kopya); gen_k_layer.py ikisini
# birlikte günceller, test_m0_k_table_sync.py / test_skill_layer_sync.py
# çapraz denetler.
LAYER_LABELS = {
    "K0": "Bayat zip taraması",
    "K1": "Dış zip sidecar",
    "K2": "Klasör checksum",
    "K3": "İç zip sidecar",
    "K4": "Manifest 19/19",
    "K5": "Script byte-for-byte",
    "K6": "İçerik (PDF + referans + skill reuse)",
    "K7": "Hijyen (secret/artefakt)",
    "K8": "Z3 sembolik ispat",
    "K9": "Lean reduct-invariance + 8 teorem çekirdek",
    "K10": "Manifest digest",
    "K11": "Config drift",
    "K12": "Plist şablon",
    "K13": "Repro self-test",
    "K14": "Cleanup kaydı",
    "K15": "History sidecar",
    "K16": "GScripts self-test",
    "K17": "Mirror sync",
    "K18": "Daemon HTTP smoke",
    "K19": "Coq reduct-invariance (8 teorem)",
    "K20": "Launchctl durum",
    "K21": "SDE determinism guard",
}

# K0-K7 çekirdek katmanlar: --full olsun olmasın her run'da koşar.
CORE_LAYERS = frozenset({"K0", "K1", "K2", "K3", "K4", "K5", "K6", "K7"})

# İsteğe bağlı katman → onu aktifleştiren bayrağın args üzerindeki getter'ı.
# args'ı ÜRETİCİ sahiplenir; bu yalnızca "hangi bayrak hangi katmanı açar"
# eşlemesidir, dolayısıyla sözleşmenin parçasıdır.
OPTIONAL_LAYERS = {
    "K8": lambda a: a.symbolic_proof,
    "K9": lambda a: a.lean_proof,
    "K10": lambda a: bool(a.verify_manifest),
    "K11": lambda a: a.check_config_drift,
    "K12": lambda a: a.check_plist,
    "K13": lambda a: a.check_repro_manifest,
    "K14": lambda a: a.check_cleanup,
    "K15": lambda a: bool(a.check_history),
    "K16": lambda a: a.check_github_scripts,
    "K17": lambda a: a.check_mirror,
    "K18": lambda a: a.check_daemon,
    "K19": lambda a: a.coq_proof,
    "K20": lambda a: a.check_launchd,
    "K21": lambda a: getattr(a, "check_sde", False),
}


# ---- Tüketici yüzeyleri ----------------------------------------------------

# Run summary'nin "K katmanları" bölümünde gösterilen katmanlar (sıralı).
# LAYER_LABELS'ın bir ALT KÜMESİDİR — üreticinin ürettiği her katmanı
# göstermez. Farklı yüzeyler (preview.js rozetleri, PR yorumu) kendi
# alt kümesini seçebilir; bu liste YALNIZCA run summary yüzeyinin seçimidir.
# Kapsam dışı: K0 (kendi modülü run_summary_k0.py'de) ve K15/K18-K21
# (bu yüzeye henüz eklenmedi).
RENDER_LAYERS = [
    "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9", "K10",
    "K11", "K12", "K13", "K14", "K16", "K17",
]


# ---- Sözleşme üzerinde saf fonksiyonlar --------------------------------------

def presentation_order(layers):
    """Gösterilecek (anahtar, katman) çiftleri — Other önce, sonra K sırası.

    Tüketicilerin TEK gezinti yolu: "hangi katmanlar önemli" sorusu bir
    yerde durur. Boş kova (yok ya da {}) hiç üretilmez — Other bölümü
    görünmez. Eksik K katmanı ATLANMAZ, None döner: render() onun için
    "sidecar'da yok" basabilmeli.
    """
    other = layers.get(OTHER_KEY)
    # Bozuk kova tüm raporu düşürmemeli: consolidate_summary bölüm
    # status()'larını try/except'siz çağırır. Yalnız sözlük olan kova kabul.
    if not isinstance(other, dict):
        other = None
    rows = ([(OTHER_KEY, other)] if other else [])
    return rows + [(key, layers.get(key)) for key in RENDER_LAYERS]


def run_verdict(layers):
    """'PASS' | 'FAIL' — bu run ne kadar bloklanır?

    Gösterilen katmanlardan biri FAIL ise kapı kapanır. Üretici bunu
    sidecar'a `run_status` olarak yazar; tüketiciler okur.
    """
    for _key, lyr in presentation_order(layers):
        if lyr and lyr.get("status") == "FAIL":
            return "FAIL"
    return "PASS"