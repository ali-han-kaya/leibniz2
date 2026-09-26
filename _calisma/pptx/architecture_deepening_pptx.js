/**
 * architecture_deepening_pptx.js — deck'i NATIVE pptx şekilleri + metniyle kurar.
 *
 * İçerik kaynağı: _calisma/CIKTI/architecture_deepening_deck.py (PNG deck, görsel
 * QA). PNG'ler artık pptx'e GÖMÜLMEZ: slayt gerçek metin run'ları ve vektör
 * şekillerle kurulur → aranabilir, kopyalanabilir, düzenlenebilir.
 *
 * Palet/tipografi: `design-system/tokens.json` (tokens.js). Slaytta tek bir
 * ad-hoc hex yoktur; renkler rol adıyla seçilir (accent/budget/ok/warn…).
 * Geometri 1600x900 px deck ızgarasından türetilir (T.grid, inç).
 * Karşılaştırma panosu PNG deck'teki 630 px'lik iki sütundan gelir.
 */
const path = require("path");
const { renderDeck, T } = require("./native_deck");

const G = T.grid;
const ROW_X = 110 / 160; // 0.6875
// Karşılaştırma panosu (PNG deck'teki 630 px'lik iki sütun)
const LEFT_X = 100 / 160; // 0.625
const RIGHT_X = 870 / 160; // 5.4375
const COL_W = 630 / 160; // 3.9375

renderDeck(() => ({
  file: path.resolve(__dirname, "architecture_deepening.pptx"),
  meta: {
    title: "leibniz2 — Architecture Deepening",
    subject:
      "Üç derinleştirme adayı: analitik geçmiş · temiz arayüz sınırı · drift kanıtı (native slaytlar)",
    author: "leibniz2 verification pipeline",
    company: "leibniz2",
  },
  footer: "LEIBNIZ2  /  ARCHITECTURE DEEPENING",
  slides: [
    {
      kicker: "01 / framing",
      title: "Three ways to deepen the chain",
      rail: "accent",
      blocks: [
        {
          kind: "text",
          x: ROW_X,
          y: 1.8125,
          w: 5.4,
          h: 1.1,
          text: "Keep the verification boundary stable.\nDeepen the layers around it.",
          size: T.type.lead,
        },
        {
          kind: "text",
          x: ROW_X,
          y: 3.04,
          w: 5.4,
          h: 1.1,
          text: "01  Queryable history\n02  Controlled frontend boundary\n03  Stronger delivery evidence",
          size: T.type.body,
          bold: true,
        },
        {
          kind: "text",
          x: 6.4375,
          y: 2.3125,
          w: 3.0,
          h: 0.9,
          text: "SAME\nAUTHORITY",
          size: T.type.display,
          color: "accent",
          bold: true,
        },
        {
          kind: "text",
          x: 6.4375,
          y: 3.44,
          w: 3.0,
          h: 0.7,
          text: "JSONL + SHA-256\nremain the audit source",
          size: T.type.small,
          color: "muted",
          bold: true,
        },
      ],
      notes:
        "01 / framing — Three ways to deepen the chain. " +
        "Keep the verification boundary stable and deepen the layers around it. " +
        "Candidates: 01 queryable history · 02 controlled frontend boundary · " +
        "03 stronger delivery evidence. " +
        "SAME AUTHORITY: JSONL + SHA-256 stay the audit source.",
    },
    {
      kicker: "02 / candidate one",
      title: "01  /  Make history analytical",
      rail: "budget",
      blocks: [
        {
          kind: "comparison",
          left: {
            x: LEFT_X,
            body: "JSONL\n↓\nmanual scans\n↓\nlimited trend views",
          },
          right: {
            x: RIGHT_X,
            body: "Verified JSONL\n↓\nrebuildable SQL projection\n↓\ntrends · flakiness · anomalies",
          },
          y: G.panelY,
          h: G.panelH,
          w: COL_W,
          accent: "budget",
          size: T.type.body,
          footnote: "Projection failure ≠ gate failure",
        },
      ],
      notes:
        "02 / candidate one — Make history analytical. " +
        "BEFORE: verified JSONL → manual scans → limited trend views. " +
        "AFTER: verified JSONL → rebuildable SQL projection → trends · flakiness · anomalies. " +
        "Contract: projection failure is NOT gate failure — the JSONL record plus its " +
        "SHA-256 sidecar remains the authority.",
    },
    {
      kicker: "03 / candidate two",
      title: "02  /  Put a clean boundary around the UI",
      rail: "accent",
      blocks: [
        {
          kind: "comparison",
          left: {
            x: LEFT_X,
            body: "Browser\n↓\nPython /api/*",
            sub: "Static shell + SSE works,\nbut contract is implicit",
          },
          right: {
            x: RIGHT_X,
            body: "Browser\n↓\nvalidated REST proxy\n↓\nPython dashboard",
            sub: "Allowlisted routes · rate limits\nstructured errors · timeouts",
          },
          y: G.panelY,
          h: G.panelH,
          w: COL_W,
          accent: "accent",
          size: T.type.body,
        },
      ],
      notes:
        "03 / candidate two — Put a clean boundary around the UI. " +
        "BEFORE: browser → Python /api/*; the static shell and SSE work, but the " +
        "contract is implicit. AFTER: browser → validated REST proxy → Python " +
        "dashboard, with allowlisted routes · rate limits · structured errors · timeouts.",
    },
    {
      kicker: "04 / candidate three",
      title: "03  /  Turn drift into visible evidence",
      rail: "warn",
      blocks: [
        {
          kind: "comparison",
          left: {
            x: LEFT_X,
            body: "Build PDF\n↓\nsidecar\n↓\nreview discovers drift late",
          },
          right: {
            x: RIGHT_X,
            body: "SOURCE_DATE_EPOCH build\n↓\nrebuild hash comparison\n↓\nCI blocks source/PDF drift",
            sub: "Before/after evidence in summary",
          },
          y: G.panelY,
          h: G.panelH,
          w: COL_W,
          accent: "warn",
          size: T.type.body,
        },
      ],
      notes:
        "04 / candidate three — Turn drift into visible evidence. " +
        "BEFORE: build PDF → sidecar → review discovers drift late. " +
        "AFTER: SOURCE_DATE_EPOCH build → rebuild hash comparison → CI blocks " +
        "source/PDF drift, and the before/after evidence lands in the run summary.",
    },
    {
      kicker: "05 / recommendation",
      title: "Choose depth without moving the trust boundary",
      rail: "ok",
      blocks: [
        {
          kind: "text",
          x: ROW_X,
          y: 1.8125,
          w: 6,
          h: 0.35,
          text: "Recommended order",
          size: T.type.small,
          color: "ok",
          bold: true,
        },
        {
          kind: "text",
          x: 0.875,
          y: 2.25,
          w: 5.4,
          h: 1.3,
          text: "1. Add the rebuild-and-compare gate\n2. Add a read-only history projection\n3. Add the external frontend proxy when needed",
          size: T.type.body,
          lineSpacing: 1.3,
        },
        {
          kind: "text",
          x: 5.9375,
          y: 2.4375,
          w: 3.4,
          h: 1.4,
          text: "FILES\n→\nPROJECTION\n→\nPRODUCT",
          size: T.type.display,
          color: "ok",
          bold: true,
        },
        {
          kind: "text",
          x: 5.9375,
          y: 3.85,
          w: 3.4,
          h: 0.7,
          text: "Each step remains reversible\nand independently verifiable.",
          size: T.type.small,
          color: "muted",
          bold: true,
        },
      ],
      notes:
        "05 / recommendation — Choose depth without moving the trust boundary. " +
        "Order: 1) add the rebuild-and-compare gate, 2) add a read-only history " +
        "projection, 3) add the external frontend proxy when needed. " +
        "FILES → PROJECTION → PRODUCT. Each step stays reversible and " +
        "independently verifiable.",
    },
  ],
}));
