  // commit_msg_gate.js — commit-msg ihlali varsa PR'ı bloke eder.
  //
  // logs/commit_msg_findings.json'u okur; violations dizisi boş değilse
  // core.setFailed() ile FAIL verir. Branch protection'da bu check adı
  // required listesine eklenince tüm commit-msg ihlalleri giderilene dek
  // merge bloke olur.
  //
  // Yalnızca pull_request'te anlamlı; push'ta sidecar üretilmiş olsa bile
  // gate atlanabilir (branch protection zaten push'ta uygulanmaz).

  const fs = require('fs');
  const FINDINGS_PATH = 'logs/commit_msg_findings.json';

  if (!fs.existsSync(FINDINGS_PATH)) {
    console.log('commit_msg_findings.json bulunamadı — commit-msg gate PASS (sidecar üretilmemiş)');
    return;
  }

  let data;
  try {
    data = JSON.parse(fs.readFileSync(FINDINGS_PATH, 'utf8'));
  } catch (e) {
    const errMsg = `commit_msg_findings.json ayrıştırma hatası: ${e.message}`;
    console.log(errMsg);
    core.setFailed(errMsg);
    return;
  }

  const violations = data.violations || [];
  const checked = data.checked || 0;

  if (violations.length === 0) {
    console.log(`commit-msg gate: PASS — ${checked} commit denetlendi, ihlal yok`);
    return;
  }

  // İhlal var — detaylı hata mesajı
  const lines = [
    `commit-msg gate: FAIL — ${violations.length} ihlal (${checked} commit denetlendi)`,
    '',
  ];
  for (const v of violations) {
    lines.push(`  ${v.commit}  ${v.subject}`);
    if (v.detail) lines.push(`    → ${v.detail}`);
  }
  const msg = lines.join('\n');
  console.log(msg);
  const failMsg = `${violations.length} commit-msg ihlali — PR'ı düzeltin`;
  console.log(failMsg);
  core.setFailed(failMsg);
