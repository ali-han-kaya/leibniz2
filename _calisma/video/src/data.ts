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
    /** true → history.jsonl yoktu (temiz klon/CI); zaman çizelgesi boş. */
    data_missing: boolean;
  };
  evidence: Evidence[];
  gates: {
    range: string;
    core: string[];
    all: string[];
    names: Record<string, string>;
    verdict: string;
  };
  seal: {
    delivery_raw: string;
    delivery_stripped: string;
    pdftex_3pass: string;
  };
};
