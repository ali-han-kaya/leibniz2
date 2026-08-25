const fs = require('fs');

  // Tek marker — tüm sapmalar (manifest + K10 + CLI override + config diff)
  // bu yorumda toplanır. Eski MARKER_MANIFEST ve MARKER_CFGDIFF marker'ları
  // bu yorumla DEĞİŞTİRİLMİŞTİR — state-sync onları da temizler.
  const MARKER = '<!-- stoic-hume-v5-tum-sapmalar -->';
  const OLD_MARKERS = [
    '<!-- stoic-hume-v5-reproducibility-manifest -->',
    '<!-- stoic-hume-v5-config-diff -->',
  ];

  // Şablon değişkenleri (bölümler yoksa '' kalır).
  let k10BadgeVal = '';

  // ── Yardımcı: yorum listesini çek ──
  const getComments = async () => {
    if (typeof EXISTING_COMMENTS !== 'undefined' && EXISTING_COMMENTS)
      return EXISTING_COMMENTS;
    const { data } = await github.rest.issues.listComments({
      issue_number: context.issue.number,
      owner: context.repo.owner,
      repo: context.repo.repo,
      per_page: 100,
    });
    return data;
  };

  // ── Bölüm 1: Reproducibility manifest + K10 digest ──
  let manifestBlock = '';
  const manifestPath = 'reproducibility/manifest.txt';
  if (fs.existsSync(manifestPath)) {
    const manifest = fs.readFileSync(manifestPath, 'utf8');
    // run_id/sha/ref üst bilgilerini ayrıştır
    const meta = {};
    for (const line of manifest.split('\n')) {
      const m = line.match(/^(github_\w+):\s+(.+)$/);
      if (m) meta[m[1]] = m[2];
    }
    const k10 = fs.existsSync('k10_verdict.txt')
      ? fs.readFileSync('k10_verdict.txt', 'utf8').trim() : 'N/A';
    k10BadgeVal = k10 === 'PASS'
      ? '✅ **K10 manifest digest: PASS**'
      : (k10 === 'FAIL'
          ? '❌ **K10 manifest digest: FAIL**'
          : `⚠️ **K10 manifest digest: ${k10}**`);
    const code = '```text\n' + manifest + '\n```';
    const runRef = meta.github_run_id
      ? `> Run: [${meta.github_run_id}](${context.payload.repository.html_url}/actions/runs/${meta.github_run_id})`
      : '';
    manifestBlock = [
      '### 📦 Reproducibility manifest (SHA-256)',
      '',
      k10BadgeVal,
      '',
      'Bu run için üretilen tüm artifact dosyalarının bütünlük özeti:',
      '',
      code,
      runRef,
    ].filter(Boolean).join('\n');
  }

  // ── Bölüm 2: CLI override (iki kaynaktan da okur) ──
  let overrideBlock = '';
  const cliPath1 = 'reproducibility/cli_overrides_version.json';
  const cliPath2 = 'budget/index.json';
  let cliOverrideRows = [];
  let hasCliOverride = false;

  for (const cliPath of [cliPath1, cliPath2]) {
    if (!fs.existsSync(cliPath)) continue;
    try {
      const data = JSON.parse(fs.readFileSync(cliPath, 'utf8'));
      // cli_overrides_version.json: üst düzeyde warning/overrides
      // budget/index.json: cli_overrides.warning / cli_overrides.overrides
      const cov = data.cli_overrides || data;
      const ovs = cov.overrides || [];
      const warn = cov.warning && ovs.length > 0;
      if (!warn) continue;
      hasCliOverride = true;
      // Aynı override'ları iki kaynaktan da çeker — birleştirip tekilleştir.
      for (const o of ovs) {
        const row = `- \`${o.key}\`: ${JSON.stringify(o.file_value)} → ` +
                    `${JSON.stringify(o.effective)} (CLI verildi)`;
        if (!cliOverrideRows.includes(row)) cliOverrideRows.push(row);
      }
    } catch (e) {
      console.log(`CLI override kaynağı okunamadı (${cliPath}): ${e.message}`);
    }
  }
  if (hasCliOverride) {
    const k10Fail = k10BadgeVal.includes('FAIL');
    overrideBlock = k10Fail
      ? [
          '### ⚠️ K10 FAIL + CLI override — olası neden',
          '',
          'Bütçe kalkanı dosya config değeriyle DEĞİL CLI değeriyle koştu',
          '(tekrarlanabilirlik sapması, K10 manifest uyuşmazlığının olası nedeni):',
          '',
          ...cliOverrideRows,
        ].join('\n')
      : [
          '### 🔧 CLI override aktif (tekrarlanabilirlik sapması)',
          '',
          ...cliOverrideRows,
        ].join('\n');
  }

  // ── Bölüm 3: Config diff (raw vs effective) ──
  let configDiffBlock = '';
  const diffPath = 'reproducibility/config/config-diff.json';
  if (fs.existsSync(diffPath)) {
    try {
      const diff = JSON.parse(fs.readFileSync(diffPath, 'utf8'));
      const diffs = diff.differences || [];
      if (diffs.length > 0) {
        const lines = diffs.map(d =>
          `- **${d.field}**: \`${JSON.stringify(d.raw)}\` → ` +
          `\`${JSON.stringify(d.effective)}\` _(${d.reason})_`
        );
        configDiffBlock = [
          '### ⚙️ Config diff (raw vs effective)',
          '',
          ...lines,
          '',
          `> Advisory: bloke etmez; bloke eden kapı config-drift job'ıdır.`,
          `> Detay: [run #${context.runId}](${context.payload.repository.html_url}/actions/runs/${context.runId})`,
        ].join('\n');
      }
    } catch (e) {
      console.log(`config-diff.json okunamadı: ${e.message}`);
    }
  }

  // ── Birleşik body ──
  const sections = [manifestBlock, overrideBlock, configDiffBlock]
    .filter(Boolean);
  if (sections.length === 0) {
    // Hiçbir sapma yok → mevcut bayat yorumları temizle (state-sync).
    const all = await getComments();
    let deleted = 0;
    for (const c of all) {
      if (c.body && (c.body.includes(MARKER) ||
          OLD_MARKERS.some(m => c.body && c.body.includes(m)))) {
        await github.rest.issues.deleteComment({
          comment_id: c.id, owner: context.repo.owner, repo: context.repo.repo,
        });
        deleted++;
      }
    }
    console.log(`Tüm sapmalar temiz — ${deleted} bayat yorum kaldırıldı`);
    return;
  }

  const body = [
    '## 📊 Tüm Sapmalar — Reproducibility + Config',
    '',
    ...sections.map(s => s + '\n'),
    MARKER,
  ].join('\n').trim();

  // Upsert (tek yorum): marker'lı mevcut yorumu bul → güncelle; yok → oluştur.
  const existing = (await getComments()).find(
    c => c.body && c.body.includes(MARKER));
  // Eski marker'lı yorumları da temizle (geçiş dönemi).
  const all = await getComments();
  for (const c of all) {
    if (c.body && OLD_MARKERS.some(m => c.body && c.body.includes(m))) {
      await github.rest.issues.deleteComment({
        comment_id: c.id, owner: context.repo.owner, repo: context.repo.repo,
      });
      console.log(`Eski marker yorumu kaldırıldı: comment_id=${c.id}`);
    }
  }

  if (existing) {
    await github.rest.issues.updateComment({
      comment_id: existing.id, owner: context.repo.owner, repo: context.repo.repo,
      body,
    });
    console.log(`Tüm sapmalar yorumu güncellendi: comment_id=${existing.id}`);
  } else {
    await github.rest.issues.createComment({
      issue_number: context.issue.number,
      owner: context.repo.owner, repo: context.repo.repo, body,
    });
    console.log('Tüm sapmalar yorumu oluşturuldu');
  }