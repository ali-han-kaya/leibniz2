/**
 * verification_chain_pptx.js — deck'i NATIVE pptx şekilleri + metniyle kurar.
 *
 * İçerik kaynağı: _calisma/CIKTI/verification_chain_deck.py (PNG deck, görsel
 * QA). PNG'ler artık pptx'e GÖMÜLMEZ: slayt gerçek metin run'ları ve vektör
 * şekillerle kurulur → aranabilir, kopyalanabilir, düzenlenebilir.
 *
 * Palet/tipografi: `design-system/tokens.json` (tokens.js). Slaytta tek bir
 * ad-hoc hex yoktur; renkler rol adıyla seçilir (accent/budget/ok/warn/err…).
 * Geometri 1600x900 px deck ızgarasından türetilir (T.grid, inç).
 */
const path = require("path");
const { renderDeck, T } = require("./native_deck");

const G = T.grid; // inç cinsinden ızgara (10 x 5.625)
const X = G.marginX;                       // 90 px
const W = G.contentRight - G.marginX;      // 1420 px içerik genişliği
const ROW_X = 110 / 160;                   // 0.6875 — tablo/step hizası
const ROW_W = 8.25;                        // 1320 px

renderDeck(() => ({
  file: path.resolve(__dirname, "verification_chain.pptx"),
  meta: {
    title: "leibniz2 — Verification Chain",
    subject: "K0–K21 doğrulama zinciri mimarisi (native slaytlar)",
    author: "leibniz2 verification pipeline",
    company: "leibniz2",
  },
  footer: "LEIBNIZ2  /  VERIFICATION CHAIN",
  slides: [
    {
      kicker: "01 / thesis",
      title: "Integrity is a chain, not a checkbox",
      rail: "accent",
      blocks: [
        {
          kind: "text", x: ROW_X, y: 1.78, w: 5.4, h: 1.1,
          text: "Every artifact passes through independent gates.\nOne broken link blocks delivery.",
          size: T.type.lead,
        },
        {
          kind: "text", x: ROW_X, y: 3.03, w: 5.4, h: 0.4,
          text: "Fail-closed  ·  reproducible  ·  offline-capable",
          size: T.type.body, color: "accent", bold: true,
        },
        {
          kind: "badge", x: 6.25, y: 1.875, w: 2.6875, h: 1.15,
          text: "P0 / P1\n→ BLOCK", color: "budget", textColor: "fg",
          size: T.type.title,
        },
        {
          kind: "text", x: 6.56, y: 3.22, w: 2.1, h: 0.7,
          text: "INFO\n→ REPORT", size: T.type.body, color: "muted", bold: true,
        },
      ],
      notes:
        "01 / thesis — Integrity is a chain, not a checkbox. " +
        "Every artifact passes through independent gates. One broken link blocks " +
        "delivery. Fail-closed · reproducible · offline-capable. " +
        "P0/P1 → BLOCK; INFO → REPORT.",
    },
    {
      kicker: "02 / architecture",
      title: "K0 → K21: layered evidence",
      rail: "accent",
      blocks: [
        {
          kind: "text", x: ROW_X, y: 1.625, w: 6, h: 0.3,
          text: "Core integrity", size: T.type.small, color: "accent",
          bold: true, caps: true,
        },
        {
          kind: "text", x: ROW_X, y: 1.90625, w: 6, h: 0.4,
          text: "K0–K7   artifacts · manifests · hygiene", size: T.type.body,
        },
        {
          kind: "text", x: ROW_X, y: 2.53, w: 6, h: 0.3,
          text: "Proof and reproducibility", size: T.type.small, color: "budget",
          bold: true, caps: true,
        },
        {
          kind: "text", x: ROW_X, y: 2.8125, w: 6, h: 0.4,
          text: "K8–K14   Z3 · Lean · lineage · cleanup", size: T.type.body,
        },
        {
          kind: "text", x: ROW_X, y: 3.4375, w: 6, h: 0.3,
          text: "Operational mirrors", size: T.type.small, color: "warn",
          bold: true, caps: true,
        },
        {
          kind: "text", x: ROW_X, y: 3.71875, w: 6.4, h: 0.4,
          text: "K15–K21   history · CI · mirror · frozen records",
          size: T.type.body,
        },
        {
          kind: "badge", x: 6.5625, y: 2.1, w: 2.375, h: 1.35,
          text: "ONE\nENTRY\nPOINT", color: "border", textColor: "fg",
          size: T.type.display,
        },
        {
          kind: "text", x: 6.5625, y: 3.72, w: 2.375, h: 0.7,
          text: "verify_delivery.py\n--full", size: T.type.small,
          color: "accent", bold: true, mono: true,
        },
      ],
      notes:
        "02 / architecture — K0 → K21: layered evidence. " +
        "Core integrity: K0–K7 artifacts · manifests · hygiene. " +
        "Proof and reproducibility: K8–K14 Z3 · Lean · lineage · cleanup. " +
        "Operational mirrors: K15–K21 history · CI · mirror · frozen records. " +
        "ONE ENTRY POINT: verify_delivery.py --full.",
    },
    {
      kicker: "03 / flow",
      title: "The delivery path",
      rail: "accent",
      blocks: [
        {
          kind: "steps", x: ROW_X, y: 2.4375, w: 1.4375, h: 0.75, gap: 0.34,
          size: T.type.body,
          steps: [
            { label: "SOURCE", color: "accent" },
            { label: "BUILD", color: "budget" },
            { label: "HASH", color: "warn" },
            { label: "VERIFY", color: "ok" },
            { label: "DELIVER", color: "accent" },
          ],
        },
        {
          kind: "text", x: ROW_X, y: 3.8125, w: ROW_W, h: 0.4,
          text: "The sidecar is the promise: the bytes we verified are the bytes we ship.",
          size: T.type.body, color: "muted",
        },
      ],
      notes:
        "03 / flow — The delivery path: SOURCE → BUILD → HASH → VERIFY → DELIVER. " +
        "The sidecar is the promise: the bytes we verified are the bytes we ship.",
    },
    {
      kicker: "04 / operations",
      title: "Failure modes are first-class outputs",
      rail: "accent",
      blocks: [
        {
          kind: "rows", x: ROW_X, y: 1.78, w: ROW_W, h: G.rowH, gap: G.rowGap,
          size: T.type.body,
          rows: [
            { label: "Hash drift", value: "P0", color: "accent" },
            { label: "Missing expected file", value: "P1", color: "warn" },
            { label: "Optional tool absent", value: "SKIP", color: "muted" },
            { label: "Advisory hygiene note", value: "INFO", color: "ok" },
          ],
        },
        {
          kind: "text", x: ROW_X, y: 4.8125, w: ROW_W, h: 0.4,
          text: "No silent PASS. No mystery green.",
          size: T.type.body, color: "accent", bold: true,
        },
      ],
      notes:
        "04 / operations — Failure modes are first-class outputs. " +
        "Hash drift: P0. Missing expected file: P1. Optional tool absent: SKIP. " +
        "Advisory hygiene note: INFO. No silent PASS. No mystery green.",
    },
    {
      kicker: "05 / take-away",
      title: "A small surface with a large guarantee",
      rail: "accent",
      blocks: [
        {
          kind: "text", x: ROW_X, y: 1.9375, w: 6, h: 0.4,
          text: "The chain stays boring on purpose:", size: T.type.lead,
        },
        {
          kind: "text", x: 0.9375, y: 2.53, w: 5.2, h: 1.1,
          text: "• stdlib-first\n• deterministic inputs\n• explicit findings\n• clean-clone reproducibility",
          size: T.type.body,
        },
        {
          kind: "text", x: 5.9375, y: 2.625, w: 3.4, h: 0.65,
          text: "K0–K21", size: T.type.display, color: "accent", bold: true,
        },
        {
          kind: "text", x: 5.9375, y: 3.44, w: 3.4, h: 0.7,
          text: "one auditable\ndelivery decision", size: T.type.body,
          color: "muted", bold: true,
        },
      ],
      notes:
        "05 / take-away — A small surface with a large guarantee. " +
        "The chain stays boring on purpose: stdlib-first · deterministic inputs · " +
        "explicit findings · clean-clone reproducibility. K0–K21: one auditable " +
        "delivery decision.",
    },
  ],
}));
