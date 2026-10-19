/**
 * native_deck.js — PNG'siz deck renderer'ı: native şekiller + GERÇEK metin.
 *
 * Neden: PNG-embed deseninde slaytlar tek bir görseldi — metin seçilemiyor,
 * aranamıyor, düzenlenemiyordu. Bu renderer slaytı pptxgenjs şekilleriyle
 * (roundRect/rect/line) ve gerçek metin run'larıyla kurar: slayt içeriği
 * arama, kopyalama ve düzenlemeye açıktır; konuşmacı notları ek katman olarak
 * korunur.
 *
 * Renk/font/radius TEK kaynaktan gelir: `tokens.js` → `design-system/tokens.json`.
 * Rol adıyla renk seçilir (`rail: "accent"`, `color: "err"`); bilinmeyen rol
 * hata atar (fail-closed) — slayta rastgele hex sızmaz.
 *
 * Deck spesifikasyonu veridir (bkz. `*_pptx.js`):
 *   {
 *     file: "<ad>.pptx",
 *     meta: { title, subject, author, company },
 *     footer: "LEIBNIZ2  /  <DECK>",
 *     slides: [ { kicker, title, rail, notes, blocks: [ ... ] } ]
 *   }
 * Blok türleri: text · card · rows · steps · badge · comparison
 *
 * Determinizm notu: slayt İÇERİĞİ deterministiktir; .pptx baytları değildir
 * (zip zaman damgaları) — bu yüzden çıktı artefakt olarak saklanmaz, test
 * yapıyı doğrular (bkz. test_pptx_export.py).
 */
const PptxGenJS = require("pptxgenjs");
const { load } = require("./tokens");

const T = load(); // modül düzeyinde bir kez: eksik token = erken hata

// Slayt tipografisi UI'dan daha yoğundur (token line-height 1.4-1.5 panolar
// için); deck satır aralığı bu yüzden ayrıca sabitlenir.
const SLIDE_LINE = 1.12;
const FONT_SIZE_DEFAULT = T.type.body;

function role(name) {
  const value = T.colors[name];
  if (!value) {
    throw new Error(
      `bilinmeyen token rolü: ${name} (geçerli: ${Object.keys(T.colors).join(", ")})`
    );
  }
  return value;
}

// ---------------------------------------------------------------- primitifler
function text(slide, opts) {
  const size = opts.size || FONT_SIZE_DEFAULT;
  // caps: PNG deck'lerdeki CSS `text-transform: uppercase` karşılığı —
  // pptxgenjs'te transform yok, bu yüzden metni renderer büyütür.
  const lines = String(
    opts.caps ? String(opts.text).toUpperCase() : opts.text
  ).split("\n");
  const runs = lines.map((line, index) => ({
    text: line,
    options: { breakLine: index < lines.length - 1 },
  }));
  slide.addText(runs, {
    x: opts.x,
    y: opts.y,
    w: opts.w,
    h: opts.h || 0.5,
    fontFace: opts.mono ? T.font.mono : T.font.sans,
    fontSize: size,
    color: role(opts.color || "fg"),
    bold: !!opts.bold,
    align: opts.align || "left",
    valign: opts.valign || "top",
    margin: 0,
    charSpacing: opts.caps ? T.letterSpacingCaps * size : 0,
    lineSpacingMultiple: opts.lineSpacing || SLIDE_LINE,
  });
}

function panel(slide, opts) {
  slide.addShape("roundRect", {
    x: opts.x,
    y: opts.y,
    w: opts.w,
    h: opts.h,
    rectRadius: opts.radius === undefined ? T.radius.panel : opts.radius,
    fill: { color: role(opts.fill || "surface") },
    line: {
      color: role(opts.outline || "border"),
      width: opts.outlineWidth || 1,
    },
  });
}

function arrow(slide, opts) {
  slide.addShape("line", {
    x: opts.x,
    y: opts.y,
    w: opts.w,
    h: 0,
    line: {
      color: role(opts.color || "muted"),
      width: opts.width || 2,
      endArrowType: "triangle",
    },
  });
}

function badge(slide, opts) {
  panel(slide, {
    x: opts.x,
    y: opts.y,
    w: opts.w,
    h: opts.h,
    fill: opts.fill || "surface",
    outline: opts.color || "border",
    outlineWidth: opts.outlineWidth || 1.5,
    radius: T.radius.chip,
  });
  text(slide, {
    x: opts.x,
    y: opts.y + 0.05,
    w: opts.w,
    h: opts.h - 0.1,
    text: opts.text,
    size: opts.size || T.type.lead,
    bold: true,
    color: opts.textColor || opts.color || "fg",
    align: "center",
    valign: "middle",
  });
}

// -------------------------------------------------------------------- bloklar
function drawBlock(slide, block) {
  switch (block.kind) {
    case "text":
      text(slide, block);
      break;
    case "card": {
      panel(slide, block);
      if (block.label) {
        text(slide, {
          x: block.x + 0.31,
          y: block.y + 0.28,
          w: block.w - 0.62,
          h: 0.3,
          text: block.label,
          size: block.labelSize || T.type.small,
          color: block.labelColor || block.outline || "muted",
          bold: true,
          caps: true,
        });
      }
      if (block.body) {
        text(slide, {
          x: block.x + 0.31,
          y: block.y + (block.label ? 0.72 : 0.4),
          w: block.w - 0.62,
          h: block.h - (block.label ? 0.9 : 0.6),
          text: block.body,
          size: block.bodySize || T.type.lead,
          color: block.bodyColor || "fg",
          bold: !!block.bodyBold,
          mono: !!block.bodyMono,
        });
      }
      break;
    }
    case "rows": {
      let y = block.y;
      for (const row of block.rows) {
        panel(slide, {
          x: block.x,
          y,
          w: block.w,
          h: block.h,
          radius: T.radius.row,
          outlineWidth: 0,
          outline: "surface",
        });
        text(slide, {
          x: block.x + 0.25,
          y: y + 0.14,
          w: block.w * 0.6,
          h: block.h - 0.28,
          text: row.label,
          size: block.size || T.type.body,
          color: "fg",
          valign: "middle",
        });
        text(slide, {
          x: block.x + block.w * 0.62,
          y: y + 0.14,
          w: block.w * 0.35,
          h: block.h - 0.28,
          text: row.value,
          size: block.size || T.type.body,
          color: row.color || "fg",
          bold: true,
          align: "right",
          valign: "middle",
          mono: !!row.mono,
        });
        y += block.h + block.gap;
      }
      break;
    }
    case "steps": {
      let x = block.x;
      for (let index = 0; index < block.steps.length; index += 1) {
        const step = block.steps[index];
        panel(slide, {
          x,
          y: block.y,
          w: block.w,
          h: block.h,
          outline: step.color || "border",
          outlineWidth: 1.5,
          radius: T.radius.row,
        });
        text(slide, {
          x,
          y: block.y,
          w: block.w,
          h: block.h,
          text: step.label,
          size: block.size || T.type.body,
          bold: true,
          color: "fg",
          align: "center",
          valign: "middle",
        });
        if (index < block.steps.length - 1) {
          arrow(slide, {
            x: x + block.w + 0.03,
            y: block.y + block.h / 2,
            w: block.gap - 0.06,
            color: "muted",
            width: 2,
          });
        }
        x += block.w + block.gap;
      }
      break;
    }
    case "badge":
      badge(slide, block);
      break;
    case "comparison": {
      panel(slide, {
        x: block.left.x,
        y: block.y,
        w: block.w,
        h: block.h,
        outline: "border",
      });
      panel(slide, {
        x: block.right.x,
        y: block.y,
        w: block.w,
        h: block.h,
        outline: block.accent,
        outlineWidth: 1.5,
      });
      text(slide, {
        x: block.left.x + 0.31,
        y: block.y + 0.28,
        w: 1.5,
        h: 0.3,
        text: "BEFORE",
        size: T.type.small,
        color: "muted",
        bold: true,
        caps: true,
      });
      text(slide, {
        x: block.right.x + 0.31,
        y: block.y + 0.28,
        w: 1.5,
        h: 0.3,
        text: "AFTER",
        size: T.type.small,
        color: block.accent,
        bold: true,
        caps: true,
      });
      text(slide, {
        x: block.left.x + 0.31,
        y: block.y + 0.72,
        w: block.w - 0.62,
        h: block.h - 0.9,
        text: block.left.body,
        size: block.size || T.type.body,
        color: "muted",
      });
      text(slide, {
        x: block.right.x + 0.31,
        y: block.y + 0.72,
        w: block.w - 0.62,
        h: block.h - 0.9,
        text: block.right.body,
        size: block.size || T.type.body,
        color: "fg",
      });
      // İkinci (alt) paragraf: PNG deck'lerdeki küçük muted satır.
      for (const side of [block.left, block.right]) {
        if (!side.sub) continue;
        text(slide, {
          x: side.x + 0.31,
          y: block.y + block.h - 0.78,
          w: block.w - 0.62,
          h: 0.6,
          text: side.sub,
          size: T.type.small,
          color: "muted",
          bold: true,
        });
      }
      arrow(slide, {
        x: block.left.x + block.w + 0.09,
        y: block.y + block.h / 2,
        w: block.arrowWidth || 0.44,
        color: block.accent,
        width: 3,
      });
      if (block.footnote) {
        text(slide, {
          x: block.left.x,
          y: block.footnoteY || block.y + block.h + 0.16,
          w: T.grid.contentRight - block.left.x,
          h: 0.4,
          text: block.footnote,
          size: block.footnoteSize || T.type.body,
          color: block.footnoteColor || "fg",
          bold: true,
        });
      }
      break;
    }
    default:
      throw new Error(`bilinmeyen blok türü: ${block.kind}`);
  }
}

function drawFrame(slide, deck, spec) {
  // Rol ADI ile çalışılır: metin ve şekil aynı token'dan beslenir; hex
  // yalnız şekil fill'inde gerekir (role() adı doğrular).
  const railRole = spec.rail || "accent";
  const railColor = role(railRole);
  slide.background = { color: T.colors.bg };
  slide.addShape("rect", {
    x: 0,
    y: 0,
    w: T.grid.rail,
    h: T.grid.height,
    fill: { color: railColor },
    line: { color: railColor, width: 0 },
  });
  text(slide, {
    x: T.grid.marginX,
    y: T.grid.kickerY,
    w: 6,
    h: 0.3,
    text: spec.kicker,
    size: T.type.kicker,
    color: railRole,
    bold: true,
    caps: true,
  });
  // (kicker ve footer caps: PNG deck'lerdeki CSS uppercase karşılığı)
  text(slide, {
    x: T.grid.marginX,
    y: T.grid.titleY,
    w: T.grid.contentRight - T.grid.marginX,
    h: 0.6,
    text: spec.title,
    size: T.type.title,
    color: "fg",
    bold: true,
  });
  slide.addShape("line", {
    x: T.grid.marginX,
    y: T.grid.ruleY,
    w: T.grid.contentRight - T.grid.marginX,
    h: 0,
    line: { color: T.colors.border, width: 1.25 },
  });
  text(slide, {
    x: T.grid.marginX,
    y: T.grid.footerY,
    w: 7,
    h: 0.25,
    text: deck.footer,
    size: T.type.micro,
    color: "muted",
    bold: true,
    caps: true,
  });
}

// ------------------------------------------------------------------- giriş
function build(spec) {
  if (!spec || !Array.isArray(spec.slides) || spec.slides.length === 0) {
    throw new Error("deck spesifikasyonu: slides boş olamaz");
  }
  for (const key of ["file", "meta", "footer"]) {
    if (!spec[key]) throw new Error(`deck spesifikasyonu: ${key} zorunlu`);
  }
  const pres = new PptxGenJS();
  pres.layout = "LAYOUT_16x9";
  pres.title = spec.meta.title;
  pres.subject = spec.meta.subject;
  pres.author = spec.meta.author;
  pres.company = spec.meta.company;
  for (const slideSpec of spec.slides) {
    const slide = pres.addSlide();
    drawFrame(slide, spec, slideSpec);
    for (const block of slideSpec.blocks || []) drawBlock(slide, block);
    if (slideSpec.notes) slide.addNotes(slideSpec.notes);
  }
  return pres.writeFile({ fileName: spec.file }).then(() => spec.slides.length);
}

// Deck spesifikasyonları bu yardımcıyla yazılır: token'ları ve ızgarayı
// enjekte eder, jeneratör dosyaları yalnız İÇERİK taşır.
function renderDeck(specFactory) {
  const spec = specFactory(T);
  return build(spec).then((count) => {
    console.log("yazildi:", spec.file, `(${count} slayt, native şekil)`);
  });
}

module.exports = { renderDeck, build, drawBlock, drawFrame, T };
