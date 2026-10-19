"use client";

import { useEffect } from "react";
import { resolveTheme, THEME_STORAGE_KEY } from "@/lib/theme";

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

/**
 * `data-theme`'i istemcide uygular ve böylece KÖPRÜDEKİ açık tema bloğu
 * (`design-system/tailwind.css` → `:root[data-theme="light"]`) devreye girer.
 *
 * Neden istemci tarafı: App Router'da kök layout `searchParams` görmez
 * (yalnız sayfalar görür) ve `?theme=` override'ının KALICI OLMAMASI tam da
 * istemci sözleşmesidir (`lib/theme.ts`). Varsayılan `dark` CSS `:root` ile
 * aynı olduğu için sorgusuz ziyarette görünür değişiklik yoktur.
 *
 * Çıktı yoktur (null) — yan etkiler: `documentElement.dataset.theme` ve
 * `theme-color` meta'sı (bkz. applyThemeColor).
 */
export function ThemeInit() {
  useEffect(() => {
    const { theme, persist } = resolveTheme(
      window.location.search,
      readStored()
    );
    document.documentElement.dataset.theme = theme;
    applyThemeColor();
    if (!persist) return; // sorgu override'ı kullanıcı tercihini YAZMAZ
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      /* kota/hassas mod — tema yine de uygulandı */
    }
  }, []);

  return null;
}
