/**
 * tokens.js — pptx jeneratörlerinin TEK renk/tipografi/geometri kaynağı.
 *
 * Kaynak: design-system/tokens.json (dashboard token katmanı; tokens.css'in
 * üretici kaynağı — orada değişirse slaytlar da değişir).
 *
 * Sözleşmeler:
 *  - Renkler pptxgenjs beklentisiyle '#'SIZ döner (skill: "hex renkler #'süz").
 *  - Fail-closed: eksik/geçersiz token sessizce varsayılana DÜŞMEZ, hata atar;
 *    yanlış token adı slayta rastgele renk sızdırmaz.
 *  - Slayt tipografisi/geometrisi token DEĞİL: deck ızgarasından türetilir
 *    (1600x900 px deck = 10x5.625 inç kanvas → 160 px/inç, 1 px = 0.45 pt;
 *    10 inç = 720 pt). Renk/font/radius token'dan, ölçek ızgaradan gelir.
 */
const fs = require("fs");
const path = require("path");

const TOKENS_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "design-system",
  "tokens.json"
);
const PX_PER_INCH = 160; // 1600 px / 10 inç
const PT_PER_PX = 0.45; // 720 pt / 1600 px

// CSS yığınında geçen ama PowerPoint'te KARŞILIĞI OLMAYAN aileler
// (-apple-system vb.) atlanır; tercih listesi iki platformda da bulunan
// adlardan seçilir (PowerPoint bulamazsa kendi eşdeğerine düşer).
const GENERIC_FACES = new Set([
  "-apple-system",
  "blinkmacsystemfont",
  "system-ui",
  "sans-serif",
  "monospace",
  "serif",
  "ui-monospace",
  "ui-sans-serif",
]);
const PORTABLE_PREFERENCE = [
  "Helvetica",
  "Arial",
  "Menlo",
  "Consolas",
  "DejaVu Sans Mono",
];

function load(pathname = TOKENS_PATH) {
  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(pathname, "utf8"));
  } catch (err) {
    throw new Error(`tokens.json okunamadı: ${pathname} (${err.message})`);
  }
  const hex = (group, key) => {
    const value = (raw[group] || {})[key];
    if (typeof value !== "string" || !value.trim()) {
      throw new Error(
        `tokens.json: ${group}.${key} eksik — palette türetilemez`
      );
    }
    const match = /^#([0-9a-fA-F]{6})$/.exec(value.trim());
    if (!match) {
      throw new Error(
        `tokens.json: ${group}.${key} 6-haneli hex değil: ${value}`
      );
    }
    return match[1].toUpperCase();
  };
  const face = (group, key) => {
    const value = (raw[group] || {})[key];
    if (typeof value !== "string" || !value.trim()) {
      throw new Error(`tokens.json: ${group}.${key} eksik`);
    }
    const stack = value
      .split(",")
      .map((part) => part.trim().replace(/^["']|["']$/g, ""))
      .filter(Boolean);
    const portable = PORTABLE_PREFERENCE.find((name) =>
      stack.some((family) => family.toLowerCase() === name.toLowerCase())
    );
    if (portable) return portable;
    const first = stack.find(
      (family) => !GENERIC_FACES.has(family.toLowerCase())
    );
    if (!first) {
      throw new Error(
        `tokens.json: ${group}.${key} taşınabilir font ailesi içermiyor: ${value}`
      );
    }
    return first;
  };
  const px = (group, key) => {
    const value = (raw[group] || {})[key];
    if (typeof value !== "string" || !/^[\d.]+px$/.test(value.trim())) {
      throw new Error(`tokens.json: ${group}.${key} px değil: ${value}`);
    }
    return parseFloat(value);
  };

  const colors = {
    bg: hex("color", "bg"),
    surface: hex("color", "surface-1"),
    surfaceRaised: hex("color", "surface-2"),
    border: hex("color", "border"),
    fg: hex("color", "fg"),
    muted: hex("color", "muted"),
    dimmed: hex("color", "fg-dimmed"),
    accent: hex("color", "accent"),
    ok: hex("color", "ok"),
    warn: hex("color", "warn"),
    err: hex("color", "err"),
    budget: hex("color", "budget"),
    onAccent: hex("color", "on-accent"),
  };

  return {
    path: pathname,
    colors,
    // Slayt içinde rol adıyla renk seçimi: roles.accent → colors.accent.
    roles: colors,
    palette: Object.values(colors),
    font: {
      sans: face("font", "sans"),
      mono: face("font", "mono"),
      verdict: face("font", "verdict"),
    },
    // Tipografi: deck piksel ölçüleri → pt (PX_TO_PT ile).
    type: {
      kicker: Math.round(22 * PT_PER_PX * 10) / 10, // 9.9
      title: Math.round(53 * PT_PER_PX * 10) / 10, // 23.9
      lead: Math.round(34 * PT_PER_PX * 10) / 10, // 15.3
      body: Math.round(30 * PT_PER_PX * 10) / 10, // 13.5
      small: Math.round(24 * PT_PER_PX * 10) / 10, // 10.8
      micro: Math.round(18 * PT_PER_PX * 10) / 10, // 8.1
      display: Math.round(64 * PT_PER_PX * 10) / 10, // 28.8
    },
    lineHeight: {
      base: (raw["line-height"] || {}).base || 1.5,
      tight: (raw["line-height"] || {}).tight || 1.4,
    },
    // letter-spacing.caps = "0.05em" → em sayısı (pt'ye çevrim: em × punto)
    letterSpacingCaps: (() => {
      const value = (raw["letter-spacing"] || {}).caps;
      if (typeof value !== "string" || !/^[\d.]+em$/.test(value.trim())) {
        throw new Error(`tokens.json: letter-spacing.caps em değil: ${value}`);
      }
      return parseFloat(value);
    })(),
    radius: {
      // token radius.* px → inç (roundRect rectRadius inç ister)
      panel: px("radius", "7") / PX_PER_INCH,
      row: px("radius", "6") / PX_PER_INCH,
      chip: px("radius", "4") / PX_PER_INCH,
    },
    // Izgara: 1600x900 px deck geometrisi → inç.
    grid: {
      width: 10,
      height: 5.625,
      rail: 16 / PX_PER_INCH,
      marginX: 90 / PX_PER_INCH,
      contentRight: 1510 / PX_PER_INCH,
      kickerY: 70 / PX_PER_INCH,
      titleY: 110 / PX_PER_INCH,
      ruleY: 205 / PX_PER_INCH,
      bodyY: 285 / PX_PER_INCH,
      footerY: 840 / PX_PER_INCH,
      panelY: 275 / PX_PER_INCH,
      panelH: 425 / PX_PER_INCH,
      rowH: 85 / PX_PER_INCH,
      rowGap: 30 / PX_PER_INCH,
    },
  };
}

module.exports = { load, TOKENS_PATH, PX_PER_INCH, PT_PER_PX };
