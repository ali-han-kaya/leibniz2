#!/usr/bin/env node
/**
 * make_docx.js — Markdown kaynagini gercek .docx'e cevirir.
 *
 * Kullanim:
 *   node make_docx.js                                   # varsayilan kaynak/cikti
 *   node make_docx.js --in docs/X.md --out out/x.docx
 *   node make_docx.js --self-test                       # parser sozlesmesi
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

function buildDocument(blocks, meta) {
  const children = [];
  for (const blk of blocks) {
    children.push(...blockToDocx(blk));
  }
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
    sections: [{ children }],
  });
}

// ── Self-test (parser sozlesmesi; CI'da kosar) ───────────────────────────────

function selfTest() {
  const fails = [];
  const eq = (name, got, want) => {
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

  if (fails.length) {
    for (const f of fails) console.error(`self-test FAIL: ${f}`);
    console.log("self-test=FAIL");
    return 1;
  }
  console.log("self-test=PASS checks=10");
  return 0;
}

// ── Uretim ──────────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const args = { in: DEFAULT_IN, out: DEFAULT_OUT, selfTest: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--in") args.in = path.resolve(argv[++i]);
    else if (argv[i] === "--out") args.out = path.resolve(argv[++i]);
    else if (argv[i] === "--self-test") args.selfTest = true;
    else if (argv[i] === "--help" || argv[i] === "-h") {
      console.log(
        "kullanim: node make_docx.js [--in <md>] [--out <docx>] [--self-test]"
      );
      process.exit(0);
    } else {
      console.error(`bilinmeyen arguman: ${argv[i]}`);
      process.exit(2);
    }
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) process.exit(selfTest());

  if (!fs.existsSync(args.in)) {
    console.error(`HATA: kaynak bulunamadi: ${args.in}`);
    process.exit(1);
  }
  const md = fs.readFileSync(args.in, "utf8");
  const blocks = parseMarkdown(md);
  const firstHeading = blocks.find(
    (x) => x.kind === "heading" && x.level === 1
  );
  const stamp = new Date(SOURCE_DATE_EPOCH * 1000).toISOString();
  const buf = await Packer.toBuffer(
    buildDocument(blocks, {
      creator: "leibniz2 docx-export",
      title: firstHeading ? firstHeading.text : path.basename(args.in, ".md"),
      description: `${path.relative(ROOT, args.in)} — SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} (${stamp})`,
    })
  );

  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  fs.writeFileSync(args.out, buf);

  const sha = crypto.createHash("sha256").update(buf).digest("hex");
  const counts = blocks.reduce((a, x) => {
    a[x.kind] = (a[x.kind] || 0) + 1;
    return a;
  }, {});
  console.log(`source=${path.relative(ROOT, args.in)}`);
  console.log(`docx=${path.relative(ROOT, args.out)}`);
  console.log(`source_date_epoch=${SOURCE_DATE_EPOCH}`);
  console.log(`bytes=${buf.length}`);
  console.log(`sha256=${sha}`);
  console.log(
    `blocks=${blocks.length} headings=${counts.heading || 0} tables=${counts.table || 0}`
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
