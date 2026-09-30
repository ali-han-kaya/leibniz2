-- CreateTable
CREATE TABLE "trend_runs" (
    "id" SERIAL NOT NULL,
    "ts" TIMESTAMPTZ(6) NOT NULL,
    "verdict" TEXT NOT NULL,
    "p0" INTEGER NOT NULL,
    "p1" INTEGER NOT NULL,
    "duration_s" DOUBLE PRECISION,
    "duration_pct_warn" BOOLEAN,
    "budget_usd" DECIMAL(10,2),
    "budget_limit" DECIMAL(10,2),
    "budget_method" TEXT,
    "ref_count" INTEGER,
    "refs_verified" INTEGER,
    "refs_total" INTEGER,
    "refs_mismatch" INTEGER,
    "refs_by_source" JSONB,
    "z3_passed" INTEGER,
    "z3_failed" INTEGER,
    "z3_total" INTEGER,
    "lean_ok" BOOLEAN,
    "lean_source" TEXT,
    "lean_override" BOOLEAN,
    "lean_detail" JSONB,
    "lineage_ok" BOOLEAN,
    "lineage_count" INTEGER,
    "lineage_summary" JSONB,
    "pattern_drift" JSONB,
    "pattern_drift_detail" JSONB,
    "cli_override_count" INTEGER,
    "cli_overrides" JSONB,
    "hook_env" JSONB,
    "precommit_hooks" JSONB,
    "status_board" JSONB,
    "findings" JSONB,
    "audit_refs_trend" TEXT,
    "flaky_count" INTEGER,
    "deterministic_count" INTEGER,
    "exit_code" INTEGER,
    "raw_sha256" TEXT,
    "stripped_sha256" TEXT,
    "history_sidecar_sha256" TEXT,
    "pdf_pages" INTEGER,
    "source_row_sha256" TEXT,

    CONSTRAINT "trend_runs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "trend_runs_ts_key" ON "trend_runs"("ts");

-- CreateIndex
CREATE UNIQUE INDEX "trend_runs_source_row_sha256_key" ON "trend_runs"("source_row_sha256");

-- CreateIndex
CREATE INDEX "trend_runs_verdict_ts_idx" ON "trend_runs"("verdict", "ts" DESC);
