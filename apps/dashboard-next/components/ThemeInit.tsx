"use client";

import { useEffect } from "react";
import {
  DARK_MEDIA_QUERY,
  DEFAULT_THEME,
  resolveTheme,
  THEME_STORAGE_KEY,
  type ThemeResolution,
} from "@/lib/theme";

function readStored(): string | null {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    return null; // private mode / kısıtlı depolama — tercih yokmuş gibi davran
  }
}

/**
 * Tarayıcı çubuğunu paletle eşler (`<meta name="theme-color">`).
 *
 * Değer TOKEN'dan okunur (`--bg`), koda gömülü hex'ten DEĞİL: tema tek
 * kaynaktan gelir ve `check-design-tokens` uygulama kaynağında hex literalini
 * zaten bloke eder — meta için hex yazmak kapıyı kırmak olurdu. Meta yoksa
 * oluşturulur (Next `viewport.themeColor` statik değer isterdi, o da hex'tir).
 */
function applyThemeColor() {
  const bg = window
    .getComputedStyle(document.documentElement)
    .getPropertyValue("--bg")
    .trim();
  if (!bg) return; // token çözülmedi — meta yazıp yanlış renk vaat etme
  let meta = document.head.querySelector<HTMLMetaElement>(
    'meta[name="theme-color"]'
  );
  if (!meta) {
    meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.appendChild(meta);
  }
  meta.content = bg;
}

function apply(resolution: ThemeResolution) {
  document.documentElement.dataset.theme = resolution.theme;
  // Uygulanan PALET (`theme`) ile kullanıcının SEÇİMİ (`themePreference`)
  // ayrıdır: auto iken tema sistemden gelir, tercih yine "auto"dur.
  document.documentElement.dataset.themePreference = resolution.preference;
  applyThemeColor();
  try {
    if (resolution.clearStored) {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    } else if (resolution.persist) {
      window.localStorage.setItem(THEME_STORAGE_KEY, resolution.theme);
    }
  } catch {
    /* kota/hassas mod — tema yine de uygulandı */
  }
}

/**
 * `data-theme`'i istemcide uygular ve böylece KÖPRÜDEKİ açık tema bloğu
 * (`design-system/tailwind.css` → `:root[data-theme="light"]`) devreye girer.
 *
 * Neden istemci tarafı: App Router'da kök layout `searchParams` görmez
 * (yalnız sayfalar görür) ve `?theme=` override'ının KALICI OLMAMASI tam da
 * istemci sözleşmesidir (`lib/theme.ts`). Saklı tercih yoksa tema SİSTEM
 * tercihine çözülür (auto) ve `prefers-color-scheme` değişimi dinlenir; açık
 * bir palet seçiliyken OS teması değişse bile palet korunur.
 *
 * Çıktı yoktur (null) — yan etkiler: `documentElement.dataset.theme` /
 * `dataset.themePreference`, `theme-color` meta'sı (bkz. applyThemeColor) ve
 * `localStorage` (yalnız açık tercih yazımı / `?theme=auto` sıfırlaması).
 */
export function ThemeInit() {
  useEffect(() => {
    // Medya sorgusu yoksa (çok eski gömülü tarayıcı) sinyal "koyu" sayılır:
    // CSS `:root` ile aynı → ilk boyamada tema değişmez.
    const query =
      typeof window.matchMedia === "function"
        ? window.matchMedia(DARK_MEDIA_QUERY)
        : null;
    const initial = resolveTheme(
      window.location.search,
      readStored(),
      query ? query.matches : DEFAULT_THEME === "dark"
    );
    apply(initial);

    // Yalnız auto modunda dinle: açık palet (sorgu ya da saklı tercih) OS
    // temasına DÖNMEZ. Sorgu override'ı da kalıcı değildir ama ziyaret
    // boyunca kullanıcı tercihidir — OS olayı onu ezmemeli.
    if (!initial.followSystem || !query) return;
    const onChange = (event: MediaQueryListEvent) => {
      apply(resolveTheme("", null, event.matches));
    };
    // Safari < 14 yalnız `addListener` sunar.
    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    }
    query.addListener(onChange);
    return () => query.removeListener(onChange);
  }, []);

  return null;
}
