// video_render_comment.js — LeibnizChain render ölçümünü PR yorumuna taşır.
//
// Girdi: `render_ci.sh` çıktıları (render_report.json + render_mode.txt).
// `check_render.py --json` raporu kare/süre/çözünürlük/bayt/sha256 alanlarını
// taşır; sha256 ayrı bir `sha256sum` adımından değil, ayrıştırıcının okuduğu
// TAM dosya baytlarından gelir.
//
// Fail-closed davranış: render adımı düştüyse veya rapor yoksa yorum yine
// yazılır — ama PASS/760 kare/geçerli sha256 UYDURULMAZ. Yorum marker'lıdır;
// aynı PR'da sonraki commit'ler yeni yorum açmak yerine mevcut olanı günceller.
const fs = require('fs');

const MARKER = '<!-- leibniz-chain-video-render -->';
const EXPECTED_FRAMES = 760;
const OUT = '_calisma/video/out';
const REPORT_PATH = `${OUT}/render_report.json`;
const MODE_PATH = `${OUT}/render_mode.txt`;
const CHECK_PATH = `${OUT}/render_check.txt`;
const ELAPSED_PATH = `${OUT}/render_elapsed_s.txt`;

function readText(path) {
  try {
    return fs.readFileSync(path, 'utf8').trim();
  } catch {
    return '';
  }
}

function fmtDuration(seconds) {
  const n = Number(seconds);
  return Number.isFinite(n) ? `${n.toFixed(3)} s` : 'ölçülemedi';
}

function fmtBytes(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n)) return 'ölçülemedi';
  return `${(n / 1048576).toFixed(2)} MiB (${n.toLocaleString('en-US')} B)`;
}

function shortSha(value) {
  return String(value || '').slice(0, 12);
}

const outcome = process.env.RENDER_OUTCOME || 'unknown';
const mode = readText(MODE_PATH) || 'yok';
const elapsed = readText(ELAPSED_PATH);
const runUrl = `${context.serverUrl || 'https://github.com'}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
// PR'da `context.sha` merge commit'idir; yorumun hangi HEAD commit'ine ait
// olduğunu göstermek için pull_request.head.sha tercih edilir.
const commit = shortSha(
  (context.payload &&
    context.payload.pull_request &&
    context.payload.pull_request.head &&
    context.payload.pull_request.head.sha) ||
    context.sha ||
    process.env.GITHUB_SHA
);

let report = null;
let reportError = '';
try {
  report = JSON.parse(fs.readFileSync(REPORT_PATH, 'utf8'));
} catch (err) {
  reportError = err && err.message ? err.message : String(err);
}

const track = report && report.track ? report.track : null;
const problems =
  report && Array.isArray(report.problems) ? report.problems : [];
const metricProblems = [];
if (track) {
  if (Number(track.frames) !== EXPECTED_FRAMES) {
    metricProblems.push(`kare ${track.frames}, beklenen ${EXPECTED_FRAMES}`);
  }
  if (!Number.isFinite(Number(track.duration_s))) {
    metricProblems.push('video süresi ölçülemedi');
  }
  if (!Number.isFinite(Number(track.file_bytes))) {
    metricProblems.push('dosya boyutu ölçülemedi');
  }
  if (!/^[0-9a-f]{64}$/.test(String(track.sha256 || ''))) {
    metricProblems.push('SHA-256 raporu eksik/geçersiz');
  }
}
const contractPassed =
  outcome === 'success' &&
  track !== null &&
  problems.length === 0 &&
  metricProblems.length === 0;

const lines = ['## 🎞️ LeibnizChain render', ''];
if (contractPassed) {
  lines.push('✅ **760 kare render sözleşmesi PASS**');
} else if (outcome !== 'success') {
  lines.push(`❌ **Render adımı başarısız** (\`${outcome}\`)`);
} else if (reportError) {
  lines.push('⚠️ **Render raporu okunamadı** — ölçüm yok, PASS sayılmadı');
} else {
  lines.push('❌ **Render sözleşmesi FAIL**');
}
lines.push('');

if (track) {
  lines.push('| Ölçüm | Değer |');
  lines.push('| --- | --- |');
  lines.push(`| Kare | **${track.frames}** / ${EXPECTED_FRAMES} |`);
  lines.push(`| Video süresi | ${fmtDuration(track.duration_s)} |`);
  lines.push(`| Kap süresi | ${fmtDuration(track.container_duration_s)} |`);
  lines.push(`| Çözünürlük | ${track.width}×${track.height} |`);
  lines.push(`| Boyut | ${fmtBytes(track.file_bytes)} |`);
  lines.push(`| SHA-256 | \`${track.sha256 || 'yok'}\` |`);
  if (elapsed) lines.push(`| Render duvar saati | ${elapsed} sn |`);
  lines.push(`| Veri modu | \`${mode}\` |`);
  lines.push(`| Sözleşme | ${contractPassed ? '✅ PASS' : '❌ FAIL'} |`);
  lines.push('');
  if (problems.length || metricProblems.length) {
    lines.push('**Sözleşme sorunları:**');
    for (const problem of problems.concat(metricProblems)) {
      lines.push(`- ${String(problem).replace(/\|/g, '\\|')}`);
    }
    lines.push('');
  }
} else {
  lines.push('| Ölçüm | Değer |');
  lines.push('| --- | --- |');
  lines.push('| Kare | ölçülemedi |');
  lines.push('| Video süresi | ölçülemedi |');
  lines.push('| Boyut | ölçülemedi |');
  lines.push('| SHA-256 | ölçülemedi |');
  lines.push(`| Veri modu | \`${mode}\` |`);
  lines.push('| Sözleşme | ❌ FAIL |');
  lines.push('');
  if (reportError) {
    lines.push(`Rapor nedeni: \`${reportError.replace(/`/g, "'")}\``);
    lines.push('');
  }
}

const check = readText(CHECK_PATH);
if (check) {
  lines.push('<details><summary>check-render çıktısı</summary>');
  lines.push('');
  lines.push('```');
  lines.push(check.slice(-2000));
  lines.push('```');
  lines.push('</details>');
  lines.push('');
}
if (commit) lines.push(`Commit: \`${commit}\` · [Koşu](${runUrl})`);
else lines.push(`[Koşu](${runUrl})`);

const body = `${MARKER}\n${lines.join('\n')}`;

if (!context.issue || !context.issue.number) {
  core.warning('video_render_comment: PR numarası yok — yorum atlandı');
  return;
}

const { data: comments } = await github.rest.issues.listComments({
  owner: context.repo.owner,
  repo: context.repo.repo,
  issue_number: context.issue.number,
  per_page: 100,
});
const existing = comments.find(
  (comment) => typeof comment.body === 'string' && comment.body.includes(MARKER)
);
if (existing) {
  await github.rest.issues.updateComment({
    owner: context.repo.owner,
    repo: context.repo.repo,
    comment_id: existing.id,
    body,
  });
} else {
  await github.rest.issues.createComment({
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: context.issue.number,
    body,
  });
}
