/**
 * report.ts — dry-run counting and reporting utilities for load.ts consumers.
 *
 * Provides reusable functions for:
 * - Dry-run mode detection and reporting
 * - Source line count reporting
 * - Final summary reporting (records processed, inserted, skipped)
 *
 * Convention: all functions are pure where possible; I/O (console.log) is
 * intentional for reporting use-cases. Consumers may call these directly or
 * compose them into their own output format.
 */

export interface DryRunInfo {
  isDryRun: boolean;
  reason?: string;
}

/**
 * Detect whether the process is running in dry-run mode.
 * Checks for --dry-run flag in process.argv.
 */
export function isDryRun(): boolean {
  return process.argv.includes('--dry-run');
}

/**
 * Return dry-run metadata including a human-readable reason.
 */
export function dryRunInfo(): DryRunInfo {
  const isDR = isDryRun();
  return {
    isDryRun: isDR,
    reason: isDR ? 'dry-run mod -- veritabanı yazma yapılmayacak' : undefined,
  };
}

/**
 * Report the source file line count.
 * @param sourcePath - path to the source file
 * @param lineCount - number of non-empty lines
 */
export function reportSourceLineCount(sourcePath: string, lineCount: number): void {
  console.log(`kaynak: ${sourcePath} (${lineCount} satır)`);
}

/**
 * Report the final load summary.
 * @param totalRecords - total records processed
 * @param insertedCount - number of records inserted
 * @param skippedCount - number of records skipped (bad rows, etc.)
 */
export function reportLoadSummary(
  totalRecords: number,
  insertedCount: number,
  skippedCount: number
): void {
  console.log(
    `bitti: ${totalRecords} kayıt işlendi (${insertedCount} eklendi), ${skippedCount} atlandı`
  );
}