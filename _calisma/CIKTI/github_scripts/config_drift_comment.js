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

  // cli_overrides tek kaynak kontrolü — summary.txt'den okunur (VERSION JSON
  // ile aynı karar, çift okuma drift'i yok). drift_rc + diffdrift_rc 0 olsa
  // bile override varsa state-sync silme yapmaz.
  const summaryPath = 'config-drift/summary.txt';
  let overrideWarnActive = false;
  if (fs.existsSync(summaryPath)) {
    const summary = fs.readFileSync(summaryPath, 'utf8');
    overrideWarnActive = /^cli_overrides=WARNING/m.test(summary);
  }

  // State-sync (config_diff_comment.js ile aynı desen): drift ÇÖZÜLDÜYSE
  // (HER İKİ kapı da exit 0 — gen_config + diff-on-drift) VE override yoksa
  // bayat uyarı yorumunu KALDIR — önceki run'ın "Config drift tespit edildi"
  // uyarısı çözülen drift'te yanıltıcı kalmasın. Yorum yoksa sessizce geç.
  if (rc === '0' && diffrc === '0' && !overrideWarnActive) {
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

  // cli_overrides tutarlılık denetimi — TEK KAYNAK: summary.txt
  // (VERSION JSON sidecar'ı da aynı kaynaktan türer — çift okuma drift'i
  // önlenir). summary.txt'deki 'cli_overrides=' satırı WARNING ise detay
  // cli_overrides_version.json'dan okunur (satır yalnızca karar verir).
  // not: summaryPath zaten yukarıda tanımlandı (overrideWarnActive için).
  const overridePath = 'config-drift/cli_overrides_version.json';
  let overrideLine = '';
  if (fs.existsSync(summaryPath)) {
    const summary = fs.readFileSync(summaryPath, 'utf8');
    const ovMatch = summary.match(/^cli_overrides=(.+)$/m);
    if (ovMatch) {
      const ovStatus = ovMatch[1].trim();
      // Format: "WARNING 1 (override_count=1)" ya da "OK 0 (override_count=0)"
      // ya da "N/A (denetim yok)"
      if (ovStatus.startsWith('WARNING') && fs.existsSync(overridePath)) {
        try {
          const cov = JSON.parse(fs.readFileSync(overridePath, 'utf8'));
          const rows = (cov.overrides || [])
            .map(o => '- `' + o.key + '`: ' + JSON.stringify(o.file_value) + ' → ' +
                      JSON.stringify(o.effective) + ' (CLI verildi)')
            .join('\n');
          overrideLine = [
            '### 🔧 CLI override tespit edildi (tekrarlanabilirlik sapması)',
            '',
            'Bütçe kalkanı dosya config değeriyle DEĞİL CLI değeriyle koştu',
            `(kaynak: summary.txt → ${ovStatus}):`,
            '',
            rows || '- _(override listesi boş)_',
          ].join('\n');
        } catch (e) {
          overrideLine = `### 🔧 CLI override: ${ovStatus} (JSON okunamadı: ${e.message})`;
        }
      } else if (ovStatus.startsWith('OK')) {
        overrideLine = 'CLI override: yok (config değerleriyle tutarlı ✓, summary.txt → OK)';
      } else {
        overrideLine = `CLI override: ${ovStatus} (summary.txt → denetim kararı)`;
      }
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

  // overrideWarnActive zaten yukarıda belirlendi (summary.txt'den).
  // Yalnızca override varsa → başlık drift değil override odaklı olur.
  //
  // overrideLine her zaman tam bloktur (başlık + açıklama + row'lar).
  // Drift VARSA: overrideLine alt bölüm olarak sections'tan sonra eklenir.
  // Drift YOKSA: overrideLine başlığı ATLANIR (titleLine zaten verir),
  //   yalnızca açıklama + row listesi gösterilir — çift başlık önlenir.
  const hasDrift = sections.length > 0;
  const titleLine = hasDrift
    ? '## ⚠️ Config drift tespit edildi'
    : '## 🔧 CLI override tespit edildi (tekrarlanabilirlik sapması)';
  const explainLine = hasDrift
    ? 'Config ile paket içeriği arasında fark bulundu (kapılar: ' +
        'gen_config.py --dry-run + diff-on-drift):'
    : null;  // override-only: açıklama overrideLine'dan gelir

  // overrideLine'dan başlıksız gövdeyi çıkar (override-only durum için)
  let overrideBodyOnly = overrideLine;
  if (overrideLine.includes('\n')) {
    overrideBodyOnly = overrideLine.substring(overrideLine.indexOf('\n') + 1).trim();
  }

  const body = [
    titleLine,
    '',
    explainLine,
    ...sections,
    hasDrift ? overrideLine : overrideBodyOnly,
    '',
    hasDrift
      ? "Düzeltme: `python3 _calisma/CIKTI/gen_config.py` çalıştırıp config'i paket içeriğinden yeniden üret."
      : "Düzeltme: CLI override'ı kaldırıp dosya config'i ile koş (ya da override'ı bilinçliyse config dosyasına işle).",
    '',
    MARKER,
  ].filter(line => line !== null && line !== '').join('\n').trim();

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
