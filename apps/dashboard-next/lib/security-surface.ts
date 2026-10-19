// Pano güvenlik yüzeyi — TEK KAYNAK.
//
// Neden ayrı modül: "hangi savunma aktif" sorusunun cevabı üç yerde
// yaşayabilirdi (health ucu, panel kartı, test) ve üçü ayrıştığında pano
// yalan söyler. Karar burada bir kez verilir: `/api/health` yalnız
// `securitySurface()`in çıktısını yayınlar, panel yalnız yayını okur.
//
// Durum KODA GÖMÜLMEZ: kapıların durumu `process.env`den türetilir. Sabit
// "aktif" yazsaydık panel süs olurdu — operatör token'ı kaldırdığında da
// yeşil kalırdı.
//
// Değerler `preview_server.py` ile hizalıdır (ALLOWED_HOSTS,
// DEFAULT_STOP_ALLOWLIST, `load_stop_allowlist`, run-now token kapısı). Pano
// bu kapıları KENDİSİ uygulamaz; preview_server'ın ortam sözleşmesini
// aynalar — `api/_adapter.py`nin "yerel birebir" aynası gibi. Tek bilinçli
// sapma: buradaki allowlist ayrıştırması IP DOĞRULAMAZ, yani tanınmayan bir
// değeri de "genişletme" sayar. Şüpheli yapılandırma sessizce yere
// düşmesin diye fazla uyaran yön seçildi (fail-closed).

/** Kapının panoda gösterilebilen durumu — KAPALI küme. */
export type DefenseState = "active" | "fail-closed" | "widened" | "unknown";

/** Durum kümesinin tek kaynağı: ayrıştırıcı ve rozet tablosu bunu okur. */
export const DEFENSE_STATES = [
  "active",
  "fail-closed",
  "widened",
  "unknown",
] as const satisfies readonly DefenseState[];

/** Panodaki tek satır: hangi kapı, hangi durumda, neden. */
export type Defense = {
  id: string;
  label: string;
  state: DefenseState;
  detail: string;
};

export type SecuritySurface = Defense[];

/** Ortam haritası; `process.env` de bu şekli taşır. */
export type SecurityEnv = Readonly<Record<string, string | undefined>>;

export const RUN_NOW_TOKEN_ENV = "PREVIEW_RUN_NOW_TOKEN";
export const STOP_ALLOWLIST_ENV = "PREVIEW_STOP_ALLOWLIST";

/** `preview_server.ALLOWED_HOSTS` ile birebir. */
export const TRUSTED_HOSTS = ["127.0.0.1", "localhost", "::1"] as const;

/** `preview_server.DEFAULT_STOP_ALLOWLIST` ile birebir. */
export const DEFAULT_STOP_PEERS = ["127.0.0.1", "::1"] as const;

// Durum → görünen etiket. Etiketler de tek kaynakta: panel kendi metnini
// yazsaydı iki yerde iki farklı kelime olurdu.
const STATE_LABELS: Record<DefenseState, string> = {
  active: "AKTİF",
  "fail-closed": "FAIL-CLOSED",
  widened: "GENİŞ",
  unknown: "BİLİNMİYOR",
};

export function isDefenseState(value: unknown): value is DefenseState {
  return (
    typeof value === "string" &&
    (DEFENSE_STATES as readonly string[]).includes(value)
  );
}

export function defenseStateLabel(state: DefenseState): string {
  return STATE_LABELS[state];
}

/**
 * `PREVIEW_STOP_ALLOWLIST`i peer listesine çevirir.
 *
 * Python tarafı (`load_stop_allowlist`) geçersiz IP'leri düşürür; buradaki
 * ayna doğrulama yapmaz — tanınmayan bir değer "genişletme" sayılır ve
 * panelde görünür. Ayrışma tek yönlüdür: pano gerçekte olduğundan DAHA
 * GENİŞ raporlar, dar değil.
 */
export function stopPeers(env: SecurityEnv): string[] {
  const peers = new Set<string>(DEFAULT_STOP_PEERS);
  for (const token of (env[STOP_ALLOWLIST_ENV] ?? "").split(",")) {
    const value = token.trim();
    if (value) peers.add(value);
  }
  return [...peers];
}

/** Default'un DIŞINDA kalan peer'lar — kapı genişletilmiş mi? */
export function extraStopPeers(env: SecurityEnv): string[] {
  return stopPeers(env).filter(
    (peer) => !(DEFAULT_STOP_PEERS as readonly string[]).includes(peer)
  );
}

/**
 * Panonun gösterdiği yüzey. Sıra sabittir (değişmez kapılar önce), çünkü
 * kart satırlarını çevirmiyor — Next'in SSR çıktısı ile istemci arasında
 * sıra farkı olmamalı.
 */
export function securitySurface(env: SecurityEnv = process.env): Defense[] {
  const extraPeers = extraStopPeers(env);
  const token = (env[RUN_NOW_TOKEN_ENV] ?? "").trim();
  return [
    {
      id: "trusted-host",
      label: "DNS-rebinding kapısı",
      state: "active",
      detail: `Host/Origin yalnız ${TRUSTED_HOSTS.join(", ")}`,
    },
    {
      id: "csp-nonce",
      label: "CSP + nonce",
      state: "active",
      detail: "script-src nonce'lu, 'unsafe-inline' yok",
    },
    {
      id: "static-root",
      label: "Statik kök hapsetme",
      state: "active",
      detail: "kök dışına çıkan yol reddedilir",
    },
    {
      id: "stop-peer",
      label: "/api/stop peer kapısı",
      state: extraPeers.length ? "widened" : "active",
      detail: extraPeers.length
        ? `izin genişletildi: +${extraPeers.join(", ")}`
        : `yalnız ${DEFAULT_STOP_PEERS.join(", ")}`,
    },
    {
      id: "run-now-token",
      label: "/api/run-now token kapısı",
      state: token ? "active" : "fail-closed",
      detail: token
        ? "Bearer token zorunlu"
        : "token yok → uç hiç açılmaz (401)",
    },
  ];
}

/**
 * `/api/health` gövdesini kapı listesine çevirir — TELİ DOĞRULAYARAK.
 *
 * Gövde başka bir süreçten/istemciden gelebilir: eksik, bozuk ya da
 * tanınmayan bir durum taşıyabilir. Tanınmayan durum `unknown`a düşer
 * (`active`e DEĞİL) — güvenlik panelinde yanlış-pozitif yeşil en pahalı
 * hatadır. Okunamayan gövde boş listeyle temsil edilir; panel onu
 * "bilinmiyor" olarak basar, "hepsi aktif" diye değil.
 */
export function parseSecuritySurface(payload: unknown): SecuritySurface {
  const raw = (payload as { security?: unknown } | null | undefined)?.security;
  if (!Array.isArray(raw)) return [];
  const defenses: Defense[] = [];
  for (const item of raw) {
    if (typeof item !== "object" || item === null) continue;
    const row = item as Record<string, unknown>;
    if (typeof row.id !== "string" || !row.id) continue;
    if (typeof row.label !== "string") continue;
    defenses.push({
      id: row.id,
      label: row.label,
      state: isDefenseState(row.state) ? row.state : "unknown",
      detail: typeof row.detail === "string" ? row.detail : "",
    });
  }
  return defenses;
}
