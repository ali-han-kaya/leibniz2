  const fs = require('fs');
  const path = 'reproducibility/manifest.txt';
  if (!fs.existsSync(path)) {
    console.log('manifest.txt yok — yorum atlanıyor');
    return;
  }
  const manifest = fs.readFileSync(path, 'utf8');

  // run_id/sha/ref üst bilgilerini ayrıştır (manifest başlığı)
  const meta = {};
  for (const line of manifest.split('\n')) {
    const m = line.match(/^(github_\w+):\s+(.+)$/);
    if (m) meta[m[1]] = m[2];
  }

  const MARKER = '<!-- stoic-hume-v5-reproducibility-manifest -->';

  // K10 bundle bütünlüğü rozeti (önceki adım k10_verdict.txt yazdı)
  const k10 = fs.existsSync('k10_verdict.txt')
    ? fs.readFileSync('k10_verdict.txt', 'utf8').trim()
    : 'N/A';
  const k10Badge = k10 === 'PASS'
    ? '✅ **K10 manifest digest: PASS**'
    : (k10 === 'FAIL'
        ? '❌ **K10 manifest digest: FAIL**'
        : `⚠️ **K10 manifest digest: ${k10}**`);

  // CLI override uyarısı — budget artifact'ındaki cli_overrides_version.json
  // (reproducibility bundle'a merge olur). override varsa yoruma uyarı satırı
  // eklenir; dosya yoksa (advisory) sessizce atlanır.
  const cliPath = 'reproducibility/cli_overrides_version.json';
  let cliLines = [];
  if (fs.existsSync(cliPath)) {
    try {
      const cli = JSON.parse(fs.readFileSync(cliPath, 'utf8'));
      if (cli.warning && Array.isArray(cli.overrides) && cli.overrides.length) {
        cliLines = [
          '⚠️ **CLI override TESPİT EDİLDİ** — bütçe kalkanı dosya config',
          'değeriyle DEĞİL CLI değeriyle koştu (tekrarlanabilirlik sapması):',
          '',
          ...cli.overrides.map(o =>
            `- \`${o.key}\`: ${JSON.stringify(o.file_value)} → ` +
            `${JSON.stringify(o.effective)} (CLI verildi)`),
        ];
      }
    } catch (e) {
      console.log(`cli_overrides_version.json okunamadı: ${e.message}`);
    }
  }

  const code = '```text\n' + manifest + '\n```';
  const body = [
    '## 📦 Reproducibility manifest (SHA-256)',
    '',
    k10Badge,
    '',
    'Bu run için üretilen tüm artifact dosyalarının bütünlük özeti:',
    '',
    code,
    '',
    ...(cliLines.length ? [...cliLines, ''] : []),
    meta.github_run_id
      ? `> Run: [${meta.github_run_id}](${context.payload.repository.html_url}/actions/runs/${meta.github_run_id})`
      : '',
    '',
    MARKER,
  ].join('\n').trim();

  // Tek yorum güncelle (upsert): marker'lı mevcut yorumu bul, varsa
  // güncelle; yoksa oluştur. Her run'da yeni yorum birikmez.
  //
  // Yorum listesi: CI'da birleştirilmiş adım (manifest + config-diff) yorum
  // listesini BİR KEZ çekip EXISTING_COMMENTS olarak verir — API çağrısı
  // 2'den 1'e iner. Script tek başına koşarsa (selftest harness'ı / bağımsız
  // kullanım) kendi listComments çağrısına düşer; iki yol da aynı upsert
  // davranışını üretir (mock'lar ve gerçek CI aynı sözleşmeyi doğrular).
  const existing = (typeof EXISTING_COMMENTS !== 'undefined' && EXISTING_COMMENTS)
    ? { data: EXISTING_COMMENTS }
    : await github.rest.issues.listComments({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        per_page: 100,
      });
  const found = existing.data.find(c => c.body && c.body.includes(MARKER));

  if (found) {
    await github.rest.issues.updateComment({
      comment_id: found.id,
      owner: context.repo.owner,
      repo: context.repo.repo,
      body,
    });
    console.log(`Mevcut yorum güncellendi: comment_id=${found.id}`);
  } else {
    await github.rest.issues.createComment({
      issue_number: context.issue.number,
      owner: context.repo.owner,
      repo: context.repo.repo,
      body,
    });
    console.log('Yeni yorum oluşturuldu (marker bulunamadı)');
  }
