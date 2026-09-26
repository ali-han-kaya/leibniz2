/**
 * Data contract for LeibnizChain.
 *
 * Every number shown in the video is loaded from public/data/leibniz.json,
 * which was generated directly from the leibniz2 repository
 * (_calisma/CIKTI/history.jsonl + test_id_residual_acceptance_doc.py).
 * Nothing here hardcodes a claim the repo cannot produce.
 */
export type Run = {
  n: number;
  ts: string;
  day: string;
  verdict: string;
  duration_s: number | null;
  findings: number;
  /** negatif ise süreç sinyal ile kesilmiş (ör. -15 = SIGTERM) */
  exit_code: number | null;
  p0: number | null;
  p1: number | null;
  /** pattern_drift */
  drift: string;
  z3_passed: number;
  z3_total: number;
  /** cli_override_count */
  overrides: number;
  /** ham status_board metni (sahne ayrıştırılmış hâli kullanır) */
  board: string;
  /** bu koşuda dolu olan kapı telemetrisi sütun sayısı */
  telemetry_reported: number;
};

/** status_board'dan ayrıştırılan tek tahta kalemi. */
export type BoardItem = {
  label: string;
  /** UNKNOWN = tanınmayan işaret; sahne onu PASS saymaz. */
  state: "PASS" | "WARN" | "FAIL" | "UNKNOWN";
  mark: string;
};

export type Evidence = {
  label: string;
  value: string;
  sub: string;
  ok: boolean;
};

export type LeibnizData = {
  meta: {
    repo: string;
    composition: string;
    width: number;
    height: number;
    fps: number;
    frames: number;
    duration_s: number;
    reconstruction: string;
  };
  runs: Run[];
  run_span: {
    first: string | null;
    last: string | null;
    count: number;
    verdicts: Record<string, number>;
    /** çıkış kodu dağılımı; negatif kod sinyal kodudur (-15 = SIGTERM) */
    exits: { code: number | null; count: number; signal: string | null }[];
    drift: Record<string, number>;
    severity: {
      p0: number;
      p1: number;
      findings: number;
      z3_passed: number;
      z3_total: number;
      overrides: number;
    };
    max_duration_s: number | null;
    /** kapı telemetrisi doluluk denetimi — "rapor yok" kanıtı */
    telemetry: {
      columns: number;
      /** hiçbir koşuda null olmayan sütunlar (değer 0 da "dolu" sayılır) */
      reported: string[];
      /** hiçbir koşuda dolu olmayan sütunlar */
      unreported: string[];
      min_per_run: number;
      max_per_run: number;
    };
    board: BoardItem[];
    board_raw: string;
    board_agreement: { distinct: number; of_runs: number };
    /** true → history.jsonl yoktu (temiz klon/CI); zaman çizelgesi boş. */
    data_missing: boolean;
  };
  evidence: Evidence[];
  gates: {
    range: string;
    core: string[];
    all: string[];
    names: Record<string, string>;
    /** status_board sayımı — sabit "PASS" DEĞİLDİR */
    verdict: { ok: number; warn: number; other: number };
    board: BoardItem[];
    board_raw: string;
    /** tahta adı doğrudan kapı numarası olan PASS kayıtları (orn. ["K0"]) */
    ok_ids: string[];
    /** kapı numarası olmayan tahta kalemleri (grup sinyalleri) */
    group_warn: string[];
    /** koşuların sinyalle kesilme dökümü — uydurulmaz, history.jsonl'dan */
    break: {
      kind: "signal" | "none" | "no_data";
      exit_code: number | null;
      signal: string | null;
      runs: number;
      of_runs: number;
      share_pct: number;
      telemetry_reported: number;
      telemetry_columns: number;
      p0: number;
      p1: number;
      max_duration_s: number | null;
    };
  };
  seal: {
    delivery_raw: string;
    delivery_stripped: string;
    pdftex_3pass: string;
  };
};
