/**
 * verification_chain_pptx.js — PNG deck'i gerçek .pptx'e çevirir.
 *
 * Kaynak: _calisma/CIKTI/verification_chain_deck.py (PIL, 1600x900 PNG slaytlar).
 * Strateji: her PNG tam-kanvas görsel olarak yerleşir (piksel-sadakati);
 * slayt metni konuşmacı notları olarak taşınır (aranabilir/erişilebilir katman,
 * skill'in desteklediği kanal — görünmez metin-kutusu hilesi YOK).
 *
 * Skill sözleşmesi (pptxgenjs 4.x):
 *  - layout set edilmeden slayt eklenmez (LAYOUT_16x9 = 10 x 5.625 inç;
 *    1600x900 = 16:9 → tam-kanvas w:10 h:5.625 birebir oturur)
 *  - hex renkler #'süz; bu jeneratörde sadece varsayılan metin rengi var
 *  - her add* çağrısına taze options nesnesi (kütüphane EMU'ya mut eder)
 *  - writeFile sonrası skill'in validate.py'si koşulur
 */
const path = require("path");
const PptxGenJS = require("pptxgenjs");

const DECK_DIR = path.resolve(__dirname, "..", "verification_chain_deck");
const OUT = path.resolve(__dirname, "verification_chain.pptx");

const pres = new PptxGenJS();
pres.layout = "LAYOUT_16x9";
pres.title = "leibniz2 — Verification Chain";
pres.subject = "K0–K21 doğrulama zinciri mimarisi";
pres.author = "leibniz2 verification pipeline";
pres.company = "leibniz2";

const slides = [
  {
    img: "slide-01.png",
    notes:
      "01 / thesis — Integrity is a chain, not a checkbox. " +
      "Every artifact passes through independent gates. One broken link blocks delivery. " +
      "Fail-closed · reproducible · offline-capable. P0/P1 → BLOCK; INFO → REPORT.",
  },
  {
    img: "slide-02.png",
    notes:
      "02 / architecture — K0 → K21: layered evidence. " +
      "Core integrity: K0–K7 artifacts · manifests · hygiene. " +
      "Proof and reproducibility: K8–K14 Z3 · Lean · lineage · cleanup. " +
      "Operational mirrors: K15–K21 history · CI · mirror · frozen records. " +
      "ONE ENTRY POINT: verify_delivery.py --full.",
  },
  {
    img: "slide-03.png",
    notes:
      "03 / flow — The delivery path: SOURCE → BUILD → HASH → VERIFY → DELIVER. " +
      "The sidecar is the promise: the bytes we verified are the bytes we ship.",
  },
  {
    img: "slide-04.png",
    notes:
      "04 / operations — Failure modes are first-class outputs. " +
      "Hash drift: P0. Missing expected file: P1. Optional tool absent: SKIP. " +
      "Advisory hygiene note: INFO. No silent PASS. No mystery green.",
  },
  {
    img: "slide-05.png",
    notes:
      "05 / take-away — A small surface with a large guarantee. " +
      "The chain stays boring on purpose: stdlib-first · deterministic inputs · " +
      "explicit findings · clean-clone reproducibility. K0–K21: one auditable delivery decision.",
  },
];

for (const s of slides) {
  const slide = pres.addSlide();
  slide.background = { color: "0A101C" }; // BG (10,16,28) — kenar payı sıfırlanır
  slide.addImage({
    path: path.join(DECK_DIR, s.img),
    x: 0,
    y: 0,
    w: 10,
    h: 5.625,
  });
  slide.addNotes(s.notes);
}

pres.writeFile({ fileName: OUT }).then(() => {
  console.log("yazildi:", OUT, `(${slides.length} slayt)`);
});
