// GENERATED — elle düzenlemeyin. Kaynak: _calisma/CIKTI/preview_contract.schema.json
// Yeniden üretim: python3 _calisma/CIKTI/gen_preview_contract.py --write
// Elle değişiklik `--check` ve test_preview_contract.py'yi kırmızıya düşürür.

/** GET /api/latest: son koşumun özeti (LATEST'in panonun okuduğu alt kümesi). */
export type Latest = {
  verdict?: string | null;
  ts?: string | null;
  p0?: number | null;
  p1?: number | null;
  stripped_sha256?: string | null;
  z3_passed?: number | null;
  z3_total?: number | null;
  z3_failed?: number | null;
  /** Koşumun kullandığı bütçe (USD). */
  budget_usd?: number | null;
  /** Koşumun etkin bütçe limiti (USD). */
  budget_limit?: number | null;
};

/** history.jsonl satırının panoya projeksiyonu (preview_server HISTORY_DASHBOARD_KEYS). Her iki yolda (preview + DB) aynı şekil. */
export type HistoryRow = {
  ts?: string | null;
  verdict?: string | null;
  p0?: number | null;
  p1?: number | null;
  duration_s?: number | null;
  budget_usd?: number | null;
  budget_limit?: number | null;
  budget_method?: string | null;
  refs_verified?: number | null;
  refs_total?: number | null;
  refs_mismatch?: number | null;
  refs_by_source?: { [key: string]: unknown } | null;
  hook_env?: { [key: string]: unknown } | null;
  z3_passed?: number | null;
  z3_failed?: number | null;
  z3_total?: number | null;
  lean_ok?: boolean | null;
  lean_detail?: string | null;
  cli_override_count?: number | null;
};

/** GET /api/trend?limit=N: pencerelenmiş geçmiş + refs-trend gövdesi. */
export type TrendResponse = {
  history: HistoryRow[];
  /** Uygulanan pencere; penceresiz çağrıda yok. */
  limit?: number | null;
  refs_trend?: { [key: string]: unknown } | null;
};
