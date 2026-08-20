  const fs = require('fs');
  if (!fs.existsSync('drift_rc.txt')) {
    console.log('drift_rc.txt yok — yorum durumu bilinemiyor, atlanıyor');
    return;
  }
  const rc = fs.readFileSync('drift_rc.txt', 'utf8').trim();
  // diff-on-drift kapısı (diff_config_artifacts.py --fail-on-drift): dosya
  // yoksa kapı çalışmamış demektir — fail-closed gate ile aynı varsayılan
  // ("cat 2>/dev/null || echo 0"): yoksa 0.
  const diffrc = fs.existsSync('diffdrift_rc.txt')
    ? fs.readFileSync('diffdrift_rc.txt', 'utf8').trim() : '0';

  const MARKER = '<!-- stoic-hume-v5-config-drift -->';
  const existing = await github.rest.issues.listComments({
    issue_number: context.issue.number,
    owner: context.repo.owner,
    repo: context.repo.repo,
    per_page: 100,
  });
  const found = existing.data.find(c => c.body && c.body.includes(MARKER));

  // State-sync (config_diff_comment.js ile aynı desen): drift ÇÖZÜLDÜYSE
  // (HER İKİ kapı da exit 0 — gen_config + diff-on-drift) bayat uyarı
  // yorumunu KALDIR — önceki run'ın "Config drift tespit edildi" uyarısı
  // çözülen drift'te yanıltıcı kalmasın. Yorum yoksa sessizce geç.
  if (rc === '0' && diffrc === '0') {
    if (found) {
      await github.rest.issues.deleteComment({
        comment_id: found.id,
        owner: context.repo.owner,
        repo: context.repo.repo,
      });
      console.log('config-drift fark yok — bayat yorum kaldırıldı');
    } else {
      console.log('config-drift fark yok — yorum yok');
    }
    return;
  }

  // Her kapının kendi bulguları: yalnızca o kapı FAIL ise bölüm eklenir.
  const genFindings = (rc !== '0' && fs.existsSync('drift_stderr.txt'))
    ? fs.readFileSync('drift_stderr.txt', 'utf8').trim() : '';
  const diffFindings = (diffrc !== '0' && fs.existsSync('diffdrift_stderr.txt'))
    ? fs.readFileSync('diffdrift_stderr.txt', 'utf8').trim() : '';

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

  // Tek yorumda iki kapının bulguları (yalnızca FAIL olan kapıların bölümü):
  //  📄 gen_config.py --dry-run      — exit rc   (drift_stderr.txt)
  //  🔎 diff-on-drift --fail-on-drift — exit diffrc (diffdrift_stderr.txt)
  const sections = [];
  if (rc !== '0') {
    sections.push(
      '### 📄 gen_config.py --dry-run (exit `' + rc + '`)',
      '',
      genFindings ? '```text\n' + genFindings + '\n```' : '_bulgu boş_');
  }
  if (diffrc !== '0') {
    sections.push(
      '### 🔎 diff-on-drift --fail-on-drift (exit `' + diffrc + '`)',
      '',
      diffFindings ? '```text\n' + diffFindings + '\n```' : '_bulgu boş_');
  }

  const body = [
    '## ⚠️ Config drift tespit edildi',
    '',
    'Config ile paket içeriği arasında fark bulundu (kapılar: ' +
      'gen_config.py --dry-run + diff-on-drift):',
    '',
    ...sections,
    '',
    overrideLine,
    '',
    "Düzeltme: `python3 _calisma/CIKTI/gen_config.py` çalıştırıp config'i paket içeriğinden yeniden üret.",
    '',
    MARKER,
  ].join('\n').trim();

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
