#!/usr/bin/env node
/**
 * make_docx.js — Markdown kaynagini gercek .docx'e cevirir.
 *
 * Kullanim:
 *   node make_docx.js                                   # varsayilan kaynak/cikti
 *   node make_docx.js --in docs/X.md --out out/x.docx
 *   node make_docx.js --in docs/A.md --in docs/B.md     # iki raporu tek dosyada birlestir
 *   node make_docx.js --self-test                       # parser sozlesmesi
 *
 * Coklu kaynak: her kaynak yeni sayfada baslar (bolum kirilimi, NEXT_PAGE);
 * ilk kaynaktan sonraki basliklar bir seviye terfi eder (h1→h2, tavan h6) —
 * boylece ikinci raporun h1'i birinci raporun bolum basligi olur.
 * Coklu kaynakta varsayilan cikti: out/combined_report.docx.
 *
 * Varsayilanlar: kaynak docs/FINAL_RC_REPORT.md, cikti _calisma/docx/out/final_rc_report.docx.
 * Cikti, kaynak dizinine YAZILMAZ: uretilen artifact ayri bir cikti dizininde
 * kalir (teslim zincirinin hash'li dosyalarina dokunulmaz).
 *
 * Sozlesme (pptx jeneratoruyle ayni desen):
 *   - saf fonksiyonlar (parser) modul olarak disa acilir; --self-test bunlari
 *     dogrular — CI'da hem parser sozlesmesi hem uretim kosar.
 *   - cikti makine-okur key=value satirlari basar (kaynak, docx, bytes, sha256,
 *     blok/tablo/baslik sayaclari, verdict).
 *
 * Determinizm notu: docx paketi core.xml tarih alanlarini kendi zamanindan
 * uretir; SOURCE_DATE_EPOCH yalnizca jeneratorun kendi damgalarini sabitler.
 * Olculen davranis README'de (docs/PUBLISH_SCENARIO.md) yazilidir — bu yuzden
 * CI byte-identity degil, LibreOffice ile acilabilirlik dogrular.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  Table,
  TableRow,
  TableCell,
  WidthType,
  AlignmentType,
  SectionType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..", "..");
const DEFAULT_IN = path.join(ROOT, "docs", "FINAL_RC_REPORT.md");
const DEFAULT_OUT = path.join(__dirname, "out", "final_rc_report.docx");
// SDE verilmezse sabit bir epoch: uretim duvar-saatine bagli olmasin.
const SOURCE_DATE_EPOCH = Number(process.env.SOURCE_DATE_EPOCH || 1700000000);

// ── Markdown parser (saf; --self-test ile dogrulanir) ────────────────────────

/** Satir ici isaretleri (bold/code) TextRun listesine cevirir. */
function inlineRuns(text, opts = {}) {
  const runs = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      runs.push(new TextRun({ text: text.slice(last, m.index), ...opts }));
    }
    const tok = m[0];
    if (tok.startsWith("**")) {
      runs.push(new TextRun({ text: tok.slice(2, -2), bold: true, ...opts }));
    } else {
      runs.push(
        new TextRun({ text: tok.slice(1, -1), font: "Consolas", ...opts })
      );
    }
    last = m.index + tok.length;
  }
  if (last < text.length)
    runs.push(new TextRun({ text: text.slice(last), ...opts }));
  return runs.length ? runs : [new TextRun({ text: "", ...opts })];
}

function splitRow(line) {
  return line
    .replace(/^\s*\|/, "")
    .replace(/\|\s*$/, "")
    .split("|")
    .map((c) => c.trim());
}

const isTableSep = (line) =>
  /^\s*\|?[\s:-]*\|[\s:|-]*$/.test(line) && line.includes("-");

/** Markdown'u blok listesine ayirir: {kind, ...}. Saf ve deterministik. */
function parseMarkdown(md) {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*$/.test(line)) {
      i++;
      continue;
    }
    if (/^```/.test(line)) {
      const body = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) body.push(lines[i++]);
      i++; // kapanis
      blocks.push({ kind: "code", text: body.join("\n") });
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      blocks.push({ kind: "heading", level: h[1].length, text: h[2].trim() });
      i++;
      continue;
    }
    if (
      /^\s*([-*_])\s*\1\s*\1[\s-*_]*$/.test(line) ||
      /^-{3,}\s*$/.test(line)
    ) {
      blocks.push({ kind: "hr" });
      i++;
      continue;
    }
    if (/^\s*>/.test(line)) {
      const body = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        body.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      blocks.push({ kind: "quote", text: body.join(" ") });
      continue;
    }
    if (
      /^\s*\|/.test(line) &&
      i + 1 < lines.length &&
      isTableSep(lines[i + 1])
    ) {
      const header = splitRow(line);
      const rows = [];
      i += 2;
      while (i < lines.length && /^\s*\|/.test(lines[i]))
        rows.push(splitRow(lines[i++]));
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    const b = line.match(/^\s*[-*]\s+(.*)$/);
    if (b) {
      const items = [];
      while (i < lines.length) {
        const mm = lines[i].match(/^\s*[-*]\s+(.*)$/);
        if (!mm) break;
        items.push(mm[1]);
        i++;
      }
      blocks.push({ kind: "bullets", items });
      continue;
    }
    const n = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (n) {
      const items = [];
      while (i < lines.length) {
        const mm = lines[i].match(/^\s*\d+[.)]\s+(.*)$/);
        if (!mm) break;
        items.push(mm[1]);
        i++;
      }
      blocks.push({ kind: "numbers", items });
      continue;
    }
    const para = [line.trim()];
    i++;
    while (
      i < lines.length &&
      !/^\s*$/.test(lines[i]) &&
      !/^(#{1,6}\s|```|\s*[-*]\s|\s*\d+[.)]\s|\s*>|\s*\|)/.test(lines[i])
    ) {
      para.push(lines[i].trim());
      i++;
    }
    blocks.push({ kind: "paragraph", text: para.join(" ") });
  }
  return blocks;
}

const HEADING_LEVELS = [
  HeadingLevel.HEADING_1,
  HeadingLevel.HEADING_2,
  HeadingLevel.HEADING_3,
  HeadingLevel.HEADING_4,
  HeadingLevel.HEADING_5,
  HeadingLevel.HEADING_6,
];

function cell(text, bold) {
  return new TableCell({
    children: [
      new Paragraph({ children: inlineRuns(text, bold ? { bold: true } : {}) }),
    ],
  });
}

function blockToDocx(blk) {
  switch (blk.kind) {
    case "heading":
      return [
        new Paragraph({
          children: inlineRuns(blk.text),
          heading: HEADING_LEVELS[blk.level - 1],
        }),
      ];
    case "paragraph":
      return [new Paragraph({ children: inlineRuns(blk.text) })];
    case "bullets":
      return blk.items.map(
        (t) => new Paragraph({ children: inlineRuns(t), bullet: { level: 0 } })
      );
    case "numbers":
      return blk.items.map(
        (t) =>
          new Paragraph({
            children: inlineRuns(t),
            numbering: { reference: "num-list", level: 0 },
          })
      );
    case "quote":
      return [
        new Paragraph({
          children: inlineRuns(blk.text),
          indent: { left: 480 },
          alignment: AlignmentType.LEFT,
        }),
      ];
    case "code":
      return blk.text.split("\n").map(
        (t) =>
          new Paragraph({
            children: [
              new TextRun({ text: t || " ", font: "Consolas", size: 18 }),
            ],
          })
      );
    case "hr":
      return [
        new Paragraph({
          text: "",
          border: { bottom: { style: "single", size: 6, space: 1 } },
        }),
      ];
    case "table":
      return [
        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          rows: [
            new TableRow({
              tableHeader: true,
              children: blk.header.map((h) => cell(h, true)),
            }),
          ].concat(
            blk.rows.map(
              (r) => new TableRow({ children: r.map((c) => cell(c, false)) })
            )
          ),
        }),
      ];
    default:
      throw new Error(`bilinmeyen blok turu: ${blk.kind}`);
  }
}

/**
 * Coklu kaynak icin baslik terfisi: h1→h2 ... h5→h6, h6 ayni kalir (tavan).
 * Saf; self-test ile dogrulanir.
 */
function promoteHeadingBlocks(blocks) {
  return blocks.map((b) =>
    b.kind === "heading"
      ? { ...b, level: Math.min(b.level + 1, HEADING_LEVELS.length) }
      : b
  );
}

/**
 * Coklu kaynagi tek belgede birlestirir: her part yeni sayfada baslar
 * (SectionType.NEXT_PAGE bolum kirilimi). parts: [{ blocks }].
 */
function buildSectionsDocument(parts, meta) {
  const sections = parts.map((p, idx) => ({
    ...(idx > 0 ? { properties: { type: SectionType.NEXT_PAGE } } : {}),
    children: p.blocks.flatMap(blockToDocx),
  }));
  return new Document({
    creator: meta.creator,
    lastModifiedBy: meta.creator,
    title: meta.title,
    description: meta.description,
    numbering: {
      config: [
        {
          reference: "num-list",
          levels: [
            {
              level: 0,
              format: "decimal",
              text: "%1.",
              alignment: AlignmentType.START,
            },
          ],
        },
      ],
    },
    styles: { default: { document: { run: { font: "Calibri", size: 22 } } } },
    sections,
  });
}

/** Tek kaynak: buildSectionsDocument'in tek bolumluk kisa yolu. */
function buildDocument(blocks, meta) {
  return buildSectionsDocument([{ blocks }], meta);
}

// ── Self-test (parser sozlesmesi; CI'da kosar) ───────────────────────────────

function selfTest() {
  const fails = [];
  let checks = 0;
  const eq = (name, got, want) => {
    checks++;
    const a = JSON.stringify(got);
    const b = JSON.stringify(want);
    if (a !== b) fails.push(`${name}: got=${a} want=${b}`);
  };

  const md = [
    "# Baslik",
    "",
    "Bir **kalin** ve `kod` paragrafi.",
    "",
    "| A | B |",
    "|---|---|",
    "| 1 | 2 |",
    "",
    "- madde bir",
    "- madde iki",
    "",
    "1. birinci",
    "2. ikinci",
    "",
    "```",
    "echo x",
    "```",
    "",
    "> alinti",
  ].join("\n");

  const b = parseMarkdown(md);
  eq(
    "blok turleri",
    b.map((x) => x.kind),
    ["heading", "paragraph", "table", "bullets", "numbers", "code", "quote"]
  );
  eq("baslik seviyesi", b[0].level, 1);
  eq("tablo basligi", b[2].header, ["A", "B"]);
  eq("tablo satiri", b[2].rows, [["1", "2"]]);
  eq("madde sayisi", b[3].items.length, 2);
  eq("numarali sayisi", b[4].items.length, 2);
  eq("kod govdesi", b[5].text, "echo x");
  eq("alinti", b[6].text, "alinti");

  // Ayni girdi ayni bloklari uretmeli (parser determinizmi).
  eq("parser determinist", parseMarkdown(md), b);

  // Satir ici ayristirma: bold + code ayri TextRun'lar.
  const runs = inlineRuns("a **b** `c`");
  eq("inline run sayisi", runs.length, 4);

  // Coklu kaynak: baslik terfisi (h1→h2, h6 tavani asamaz, paragraf dokunulmaz).
  const promoted = promoteHeadingBlocks([
    { kind: "heading", level: 1, text: "A" },
    { kind: "heading", level: 6, text: "B" },
    { kind: "paragraph", text: "x" },
  ]);
  eq(
    "baslik terfisi",
    promoted.map((x) => [x.kind, x.level ?? 0]),
    [
      ["heading", 2],
      ["heading", 6],
      ["paragraph", 0],
    ]
  );

  // Coklu kaynak birlesimi: part sirasi korunur, bloklar kaybolmaz.
  const p1 = parseMarkdown("# Bir\n\nmetin");
  const p2 = parseMarkdown("# Iki\n\n| A |\n|---|\n| 1 |");
  const parts = [{ blocks: p1 }, { blocks: p2 }];
  eq(
    "coklu bolum birlesimi",
    parts.flatMap((p) => p.blocks).map((x) => x.kind),
    ["heading", "paragraph", "heading", "table"]
  );

  if (fails.length) {
    for (const f of fails) console.error(`self-test FAIL: ${f}`);
    console.log("self-test=FAIL");
    return 1;
  }
  console.log(`self-test=PASS checks=${checks}`);
  return 0;
}

// ── Uretim ──────────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const args = { in: [], out: null, selfTest: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--in") args.in.push(path.resolve(argv[++i]));
    else if (argv[i] === "--out") args.out = path.resolve(argv[++i]);
    else if (argv[i] === "--self-test") args.selfTest = true;
    else if (argv[i] === "--help" || argv[i] === "-h") {
      console.log(
        "kullanim: node make_docx.js [--in <md>]... [--out <docx>] [--self-test]"
      );
      process.exit(0);
    } else {
      console.error(`bilinmeyen arguman: ${argv[i]}`);
      process.exit(2);
    }
  }
  if (args.in.length === 0) args.in = [DEFAULT_IN];
  if (!args.out) {
    args.out =
      args.in.length > 1
        ? path.join(__dirname, "out", "combined_report.docx")
        : DEFAULT_OUT;
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) process.exit(selfTest());

  const parts = [];
  for (const src of args.in) {
    if (!fs.existsSync(src)) {
      console.error(`HATA: kaynak bulunamadi: ${src}`);
      process.exit(1);
    }
    parts.push({ path: src, md: fs.readFileSync(src, "utf8") });
  }

  const allBlocks = [];
  parts.forEach((p, idx) => {
    p.blocks = parseMarkdown(p.md);
    if (idx > 0) p.blocks = promoteHeadingBlocks(p.blocks);
    allBlocks.push(...p.blocks);
  });

  const firstHeading = parts[0].blocks.find(
    (x) => x.kind === "heading" && x.level === 1
  );
  const stamp = new Date(SOURCE_DATE_EPOCH * 1000).toISOString();
  const relSources = parts.map((p) => path.relative(ROOT, p.path)).join(",");
  const buf = await Packer.toBuffer(
    buildSectionsDocument(parts, {
      creator: "leibniz2 docx-export",
      title: firstHeading
        ? firstHeading.text
        : path.basename(parts[0].path, ".md"),
      description: `${relSources} — SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} (${stamp})`,
    })
  );

  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  fs.writeFileSync(args.out, buf);

  const sha = crypto.createHash("sha256").update(buf).digest("hex");
  const counts = allBlocks.reduce((a, x) => {
    a[x.kind] = (a[x.kind] || 0) + 1;
    return a;
  }, {});
  console.log(`source=${relSources}`);
  console.log(`sections=${parts.length}`);
  console.log(`docx=${path.relative(ROOT, args.out)}`);
  console.log(`source_date_epoch=${SOURCE_DATE_EPOCH}`);
  console.log(`bytes=${buf.length}`);
  console.log(`sha256=${sha}`);
  console.log(
    `blocks=${allBlocks.length} headings=${counts.heading || 0} tables=${counts.table || 0}`
  );
  console.log("verdict=OK");
  return 0;
}

if (require.main === module) {
  main()
    .then((rc) => process.exit(rc))
    .catch((e) => {
      console.error(`HATA: ${e && e.message ? e.message : e}`);
      process.exit(1);
    });
}

module.exports = { parseMarkdown, inlineRuns, buildDocument };
