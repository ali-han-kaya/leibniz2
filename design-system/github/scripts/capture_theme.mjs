/**
 * design-system/github/scripts/capture_theme.mjs — capture github.com in a
 * pinned color scheme.
 *
 * WHY THIS EXISTS (measured 2026-10-11): github.com serves
 * `data-color-mode="dark"` to logged-out visitors. Emulating
 * `prefers-color-scheme: light`, setting cookies (`color_mode`,
 * `preferred_color_mode`), localStorage keys (`color-mode`, `color_mode`,
 * `github-color-mode`, `preferred-color-mode`) and query parameters
 * (`?color_mode=light`, `?colorMode=light`, `?theme=light`) were all tried and
 * every one still rendered the dark theme — and the extractor CLI exposes only
 * `--dark-mode` (i.e. `page.emulateMedia({colorScheme:"dark"})`, which GitHub
 * ignores). Theme switching on GitHub is an attribute flip on <html>:
 * `data-color-mode="light"` alone turns the *same* DOM/CSS snapshot into the
 * real light theme (verified: `--bgColor-default` `#0d1117` -> `#fff`,
 * `--fgColor-default` `#f0f6fc` -> `#1f2328`, same 1990 computed custom
 * properties).
 *
 * So this script drives dembrandt's OWN extraction function
 * (`dembrandt/lib/extractors.js` `extractBranding`) — the exact code path that
 * produced raw.json — and only pins the theme attribute before/while the page
 * boots. Rule identity is checked by re-capturing the dark theme and comparing
 * against the committed raw.json: 304/304 names, 304/304 values identical
 * (2026-10-11).
 *
 * Usage (evidence tooling, not a repo runtime dependency):
 *   mkdir -p /tmp/gh-capture && cd /tmp/gh-capture
 *   npm install --no-save playwright@1.63.0 dembrandt@0.7.3  # one command: --no-save prunes
 *   ./node_modules/.bin/playwright install chromium         # Chrome Headless Shell 153
 *   cp <repo>/design-system/github/scripts/capture_theme.mjs .
 *   node capture_theme.mjs light raw.light.json
 *   node capture_theme.mjs dark  raw.redark.json            # rule-identity check
 *
 * The output keeps the extractor's own schema (colors.cssVariables is what the
 * canonical layer consumes) and adds `theme`, `captureNote` and `pageState`
 * provenance. `pageState` is read back from the captured page after extraction
 * (data-color-mode plus the two Primer canvas/ink variables), which is what
 * makes a capture self-evidencing: dark -> `#0d1117` / `#f0f6fc`, light ->
 * `#fff` / `#1f2328`.
 */
import fs from "node:fs";
import { chromium } from "playwright-core";
import { extractBranding } from "dembrandt/lib/extractors.js";

const THEME = process.argv[2] || "light";
const OUT = process.argv[3] || `raw.${THEME}.json`;
const URL = "https://github.com/";

if (THEME !== "light" && THEME !== "dark") {
  console.error("usage: node capture_theme.mjs <light|dark> [out.json]");
  process.exit(2);
}

const spinner = {
  text: "",
  start() {},
  stop() {},
  warn() {},
  fail() {},
  succeed() {},
};

const browser = await chromium.launch({
  headless: true,
  args: ["--disable-blink-features=AutomationControlled"],
});

// extractBranding() creates its own browser context, so the theme pin is
// injected by wrapping newContext(). The MutationObserver re-pins the attribute
// if GitHub's boot script writes its own (dark) value back.
let capturedPage = null;

const patched = new Proxy(browser, {
  get(target, prop, receiver) {
    if (prop === "newContext") {
      return async (options) => {
        const context = await target.newContext(options);
        const realNewPage = context.newPage.bind(context);
        context.newPage = async (...args) => {
          const page = await realNewPage(...args);
          capturedPage = page;
          return page;
        };
        await context.addInitScript((theme) => {
          const pin = () => {
            const el = document.documentElement;
            if (el && el.getAttribute("data-color-mode") !== theme) {
              el.setAttribute("data-color-mode", theme);
            }
          };
          if (document.documentElement) pin();
          new MutationObserver(pin).observe(document, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ["data-color-mode"],
          });
        }, THEME);
        return context;
      };
    }
    return Reflect.get(target, prop, receiver);
  },
});

let result;
let pageState = null;
try {
  result = await extractBranding(URL, spinner, patched, {
    navigationTimeout: 90000,
  });
  // Read the theme back from the captured page BEFORE closing the browser: this
  // is the artifact's own proof that the requested scheme was the one extracted.
  pageState = await capturedPage.evaluate(() => {
    const cs = getComputedStyle(document.documentElement);
    let total = 0;
    for (const name of cs) if (name.startsWith("--")) total += 1;
    return {
      dataColorMode: document.documentElement.getAttribute("data-color-mode"),
      bgColorDefault: cs.getPropertyValue("--bgColor-default").trim(),
      fgColorDefault: cs.getPropertyValue("--fgColor-default").trim(),
      prefersDark: matchMedia("(prefers-color-scheme: dark)").matches,
      computedCustomProperties: total,
    };
  });
} finally {
  await browser.close();
}

if (!pageState || pageState.dataColorMode !== THEME) {
  console.error(
    `theme pin failed: page reports ${pageState && pageState.dataColorMode}, wanted ${THEME}`
  );
  process.exit(3);
}

const count = Object.keys(result?.colors?.cssVariables ?? {}).length;
const raw = {
  url: URL,
  extractedAt: new Date().toISOString(),
  theme: THEME,
  siteName: result?.siteName ?? "GitHub",
  captureNote:
    "Extracted with dembrandt/lib/extractors.js extractBranding (same code path " +
    "as raw.json, playwright-core 1.63.0, Chrome Headless Shell 153, 1920x1080) " +
    "with the page's data-color-mode attribute pinned to \"" +
    THEME +
    "\" — the attribute GitHub's own theme switcher flips, because github.com " +
    "serves dark to logged-out visitors and the CLI exposes no light switch.",
  pageState,
  ...result,
};

fs.writeFileSync(OUT, JSON.stringify(raw, null, 2) + "\n");
console.log(`theme=${THEME} cssVariables=${count} -> ${OUT}`);
