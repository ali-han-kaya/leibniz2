  const fs = require('fs');
  const rc = fs.readFileSync('drift_rc.txt', 'utf8').trim();
  const findings = fs.existsSync('drift_stderr.txt')
    ? fs.readFileSync('drift_stderr.txt', 'utf8').trim() : '';

  // cli_overrides tutarlılık denetimi (config-drift job'ının CLI overrides
  // adımı): effective_config.json'daki CLI override sapması drift raporunda
  // AYRI bir satır olarak görünür. Advisory — yorumu patlatmaz.
  const overridePath = 'config-drift/cli_overrides_version.json';
  let overrideLine = '';
  if (fs.existsSync(overridePath)) {
    try {
      const cov = JSON.parse(fs.readFileSync(overridePath, 'utf8'));
      if (cov.warning) {
        const rows = (cov.overrides || [])
          .map(o => '- `' + o.key + '`: ' + o.file_value + ' → ' + o.effective + ' (CLI verildi)')
          .join('\n');
        overrideLine = [
          '### 🔧 CLI override tespit edildi (tekrarlanabilirlik sapması)',
          '',
          'Bütçe kalkanı dosya config değeriyle DEĞİL CLI değeriyle koştu:',
          '',
          rows || '- _(override listesi boş)_',
        ].join('\n');
      } else {
        overrideLine = 'CLI override: yok (config değerleriyle tutarlı ✓)';
      }
    } catch (e) {
      console.log('cli_overrides_version.json okunamadı (atlanıyor): ' + e.message);
    }
  }

  const MARKER = '<!-- stoic-hume-v5-config-drift -->';
  const body = [
    '## ⚠️ Config drift tespit edildi',
    '',
    '`gen_config.py --dry-run` config ile paket içeriği arasında fark buldu (exit `' + rc + '`):',
    '',
    findings ? '```text\n' + findings + '\n```' : '_bulgu boş_',
    '',
    overrideLine,
    '',
    "Düzeltme: `python3 _calisma/CIKTI/gen_config.py` çalıştırıp config'i paket içeriğinden yeniden üret.",
    '',
    MARKER,
  ].join('\n').trim();

  const existing = await github.rest.issues.listComments({
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
    console.log(`Config drift yorumu güncellendi: comment_id=${found.id}`);
  } else {
    await github.rest.issues.createComment({
      issue_number: context.issue.number,
      owner: context.repo.owner,
      repo: context.repo.repo,
      body,
    });
    console.log('Config drift yorumu oluşturuldu');
  }
