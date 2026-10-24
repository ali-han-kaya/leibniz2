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

/** klayers.json'daki gerçek K katmanı durumu. MISSING = rapor yok. */
export type GateStatus = "PASS" | "FAIL" | "SKIP" | "MISSING";

export type GateLayer = {
  id: string;
  label: string;
  status: GateStatus;
  ran: boolean;
  findings: number;
};

export type GateRun = {
  run_id: string | null;
  created_at: string | null;
  verdict: string | null;
  layers: GateLayer[];
  counts: { pass: number; fail: number; skip: number; missing: number };
};

/** GateChainRuns kapısının durumu. MISSING = bu koşunun kaydı yok — PASS DEĞİL. */
export type GateHistoryStatus = "PASS" | "FAIL" | "SKIP" | "WARN" | "MISSING";

export type GateHistoryGate = {
  id: string;
  label: string;
  status: GateHistoryStatus;
  /** kanıt kaynağı: koşu-başına `layers` haritası | status_board | yok */
  from: "layers" | "board" | null;
};

/** Tek bir history.jsonl koşusunun 16 kapılık gerçek durumu. */
export type GateHistoryRun = {
  n: number;
  ts: string;
  day: string;
  verdict: string;
  exit_code: number | null;
  duration_s: number | null;
  gates: GateHistoryGate[];
  /** MISSING olmayan kapı sayısı (0..16) */
  reported: number;
  missing: number;
  /** koşu satırı koşu-başına `layers` haritası taşıyor mu */
  layers_reported: boolean;
  board_raw: string;
  /** "K katmanları ⚠️" gibi grup sinyali; kapı kimliği değildir */
  board_group_state: "PASS" | "WARN" | "FAIL" | "UNKNOWN" | null;
};

export type GateHistory = {
  source: string;
  composition: string;
  frames: number;
  fps: number;
  width: number;
  height: number;
  intro_frames: number;
  per_run_frames: number;
  outro_frames: number;
  run_capacity: number;
  gate_count: number;
  runs: GateHistoryRun[];
  run_count: number;
  data_missing: boolean;
  totals: { reported: number; missing: number; cells: number };
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
  gate_chain: {
    source: string;
    runs: GateRun[];
    run_count: number;
    data_missing: boolean;
    complete: boolean;
  };
  /** İkinci kompozisyonun (GateChainRuns) verisi — yalnız history.jsonl. */
  gate_history: GateHistory;
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
    /**
     * Son koşunun KENDİ 16 kapılık dökümü (history satırındaki `layers`).
     * `from` alanı kanıtı söyler: "layers" (tam harita) | "board" (tahtada
     * adı geçen kapı) | null (kayıt yok).
     */
    statuses: GateHistoryGate[];
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
      /** kapı başına koşu sayıları (PASS/FAIL/SKIP/WARN/MISSING) */
      by_gate: Record<
        string,
        {
          pass: number;
          fail: number;
          skip: number;
          warn: number;
          missing: number;
        }
      >;
      /**
       * Kapı kanıtı OLAN en yeni kırılma (sıfır olmayan çıkış). Sinyalle
       * kesilen bir koşu rapor üretemediği için animasyon kanıtlı koşuyu
       * çizer; "en yeni kırılma" ayrıca `newest`'te dürüstçe adlandırılır.
       * Yoksa null.
       */
      latest: {
        n: number;
        ts: string;
        exit_code: number | null;
        signal: string | null;
        gates: GateHistoryGate[];
        /** GERÇEK FAIL kapı kimlikleri (K0–K15; uydurulmaz) */
        failed: string[];
        /** K0–K15 dışındaki gerçek kayıtlar (K16+; silinmez) */
        outside: { id: string; status: string }[];
        /** kapsam dışı GERÇEK FAIL kapıları (ör. K16/K17) */
        outside_failed: string[];
        reported: number;
        layers_reported: boolean;
      } | null;
      /** en yeni kırılma — kanıtı olmasa da (#98 SIGTERM gibi) */
      newest: {
        n: number;
        ts: string;
        exit_code: number | null;
        signal: string | null;
        reported: number;
      } | null;
      /** latest en yeni kırılmanın kendisi mi (kanıtlı mı)? */
      latest_is_newest: boolean;
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
