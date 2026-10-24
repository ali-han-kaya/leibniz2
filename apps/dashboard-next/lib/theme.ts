// Tema çözümlemesi — tarayıcıda uygulayan `components/ThemeInit.tsx` ile
// smoke kapısının PAYLAŞTIĞI tek kaynak. Sözleşme
// `_calisma/CIKTI/preview.js`'in aynısıdır:
//
//   * `auto` bir PALET DEĞİL, tercihin YOKLUĞUDUR: sistem tercihine
//     (`prefers-color-scheme`) çözülür ve sistem değişince canlı güncellenir,
//   * açık bir palet (`dark | light`) auto'yu EZER,
//   * geçerli `?theme=<dark|light>` sorgusu saklı tercihi EZER ve KALICI
//     OLMAZ — CI/Lighthouse deterministik tema taraması yapabilsin, ama
//     kullanıcının kayıtlı tercihi bozulmasın,
//   * `?theme=auto` tek istisnadır: açık bir SIFIRLAMA isteğidir, saklı
//     tercihi siler (`clearStored`) — "auto" hiçbir zaman depolanmaz,
//     yokluk auto demektir,
//   * sorgu yoksa `localStorage[dashboard-theme]` (yalnız geçerliyse),
//   * o da yoksa auto → sistem tercihi (`prefers-color-scheme`); sinyal
//     okunamazsa varsayılan `dark` (CSS `:root` ile aynı → ilk boyamada
//     tema değişmediği için layout kayması üretmez).
//
// Neden yalnız `dark | light`: dashboard-next yalnız repo köprüsünü
// (`design-system/tailwind.css`) import eder; `stripe` varyantı ayrı bir
// sheet'tir ve burada tüketilmez (bkz. app/globals.css preset-bağımsızlık
// notu). Kümeye varyant eklemek önce köprü importunu gerektirir.
export const THEMES = ["dark", "light"] as const;

export type Theme = (typeof THEMES)[number];

/** Tercih yokluğu: sistem temasını izle. Depolanan bir değer DEĞİLDİR. */
export const AUTO_THEME = "auto";

export type ThemePreference = Theme | typeof AUTO_THEME;

/** Yalnız `matchMedia` okunamazsa kullanılan palet (CSS `:root` ile aynı). */
export const DEFAULT_THEME: Theme = "dark";

/** preview.js ile aynı anahtar — iki yüzey aynı tercihi paylaşır. */
export const THEME_STORAGE_KEY = "dashboard-theme";

export const THEME_QUERY_PARAM = "theme";

/** Sistem tercihi medya sorgusu — preview.js'teki `DARK_QUERY` ile aynı. */
export const DARK_MEDIA_QUERY = "(prefers-color-scheme: dark)";

export function isTheme(value: string | null | undefined): value is Theme {
  return (
    typeof value === "string" && (THEMES as readonly string[]).includes(value)
  );
}

export function isThemePreference(
  value: string | null | undefined
): value is ThemePreference {
  return value === AUTO_THEME || isTheme(value);
}

export interface ThemeResolution {
  /** Uygulanacak PALET (`data-theme`). */
  theme: Theme;
  /** Kullanıcının SEÇİMİ: palet ya da auto (uygulanan palet değil). */
  preference: ThemePreference;
  /** true → tema kullanıcı tercihi olarak saklanmalı (sorgu override'ı DEĞİL). */
  persist: boolean;
  /** true → saklı tercih silinmeli (`?theme=auto` sıfırlaması). */
  clearStored: boolean;
  /** true → sistem tercihi değişimini dinle (`prefers-color-scheme`). */
  followSystem: boolean;
}

/**
 * Saf çözümleyici: `window`'a dokunmaz, dolayısıyla tip kapısında ve
 * (tarayıcısız) sözleşme testinde doğrudan koşar.
 *
 * `search` ham sorgu dizesidir (`""`, `"?theme=light"`, `"theme=light"`).
 * `prefersDark` sistem tercihidir (`matchMedia(DARK_MEDIA_QUERY).matches`).
 */
export function resolveTheme(
  search: string,
  stored: string | null,
  prefersDark: boolean
): ThemeResolution {
  const system: Theme = prefersDark ? "dark" : "light";
  const requested = new URLSearchParams(search).get(THEME_QUERY_PARAM);
  if (requested === AUTO_THEME) {
    return {
      theme: system,
      preference: AUTO_THEME,
      persist: false,
      clearStored: true,
      followSystem: true,
    };
  }
  if (isTheme(requested)) {
    return {
      theme: requested,
      preference: requested,
      persist: false,
      clearStored: false,
      followSystem: false,
    };
  }
  if (isTheme(stored)) {
    return {
      theme: stored,
      preference: stored,
      persist: true,
      clearStored: false,
      followSystem: false,
    };
  }
  return {
    theme: system,
    preference: AUTO_THEME,
    persist: false,
    clearStored: false,
    followSystem: true,
  };
}
