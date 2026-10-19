// Tema çözümlemesi — tarayıcıda uygulayan `components/ThemeInit.tsx` ile
// smoke kapısının PAYLAŞTIĞI tek kaynak. Sözleşme
// `_calisma/CIKTI/preview.js`'in aynısıdır:
//
//   * geçerli `?theme=<dark|light>` sorgusu saklı tercihi EZER ve KALICI
//     OLMAZ — CI/Lighthouse deterministik tema taraması yapabilsin, ama
//     kullanıcının kayıtlı tercihi bozulmasın,
//   * sorgu yoksa `localStorage[dashboard-theme]` (yalnız geçerliyse),
//   * o da yoksa varsayılan `dark` (CSS `:root` ile aynı → ilk boyamada
//     tema değişmediği için layout kayması üretmez).
//
// Neden yalnız `dark | light`: dashboard-next yalnız repo köprüsünü
// (`design-system/tailwind.css`) import eder; `stripe` varyantı ayrı bir
// sheet'tir ve burada tüketilmez (bkz. app/globals.css preset-bağımsızlık
// notu). Kümeye varyant eklemek önce köprü importunu gerektirir.
export const THEMES = ["dark", "light"] as const;

export type Theme = (typeof THEMES)[number];

export const DEFAULT_THEME: Theme = "dark";

/** preview.js ile aynı anahtar — iki yüzey aynı tercihi paylaşır. */
export const THEME_STORAGE_KEY = "dashboard-theme";

export const THEME_QUERY_PARAM = "theme";

export function isTheme(value: string | null | undefined): value is Theme {
  return (
    typeof value === "string" && (THEMES as readonly string[]).includes(value)
  );
}

export interface ThemeResolution {
  theme: Theme;
  /** true → tema kullanıcı tercihi olarak saklanmalı (sorgu override'ı DEĞİL). */
  persist: boolean;
}

/**
 * Saf çözümleyici: `window`'a dokunmaz, dolayısıyla tip kapısında ve
 * (tarayıcısız) sözleşme testinde doğrudan koşar.
 *
 * `search` ham sorgu dizesidir (`""`, `"?theme=light"`, `"theme=light"`).
 */
export function resolveTheme(
  search: string,
  stored: string | null
): ThemeResolution {
  const requested = new URLSearchParams(search).get(THEME_QUERY_PARAM);
  if (isTheme(requested)) {
    return { theme: requested, persist: false };
  }
  return { theme: isTheme(stored) ? stored : DEFAULT_THEME, persist: true };
}
