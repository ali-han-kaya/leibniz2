  const fs = require('fs');
  const path = 'reproducibility/config/config-diff.json';
  const MARKER = '<!-- stoic-hume-v5-config-diff -->';

  const listComments = async () => {
    const { data } = await github.rest.issues.listComments({
      issue_number: context.issue.number,
      owner: context.repo.owner,
      repo: context.repo.repo,
      per_page: 100,
    });
    return data;
  };
  // Yorum listesi: CI'de birleştirilmiş adım (manifest + config-diff) listeyi
  // BİR KEZ çekip EXISTING_COMMENTS olarak verir (API çağrısı 2'den 1'e iner);
  // tek başına koşulursa kendi listComments çağrısına düşer — iki yol aynı
  // create/update/delete davranışını üretir.
  const getExisting = async () => {
    if (typeof EXISTING_COMMENTS !== 'undefined' && EXISTING_COMMENTS)
      return EXISTING_COMMENTS;
    return await listComments();
  };

  // State-sync temizliği (config_drift_comment.js / tum_sapmalar_comment.js
  // ile aynı desen): bulgu YOKSA marker'lı bayat yorumu kaldır — önceki
  // run'ın uyarısı çözülen/işlenmeyen durumda yanıltıcı kalmasın.
  const cleanupStale = async (why) => {
    const existing = await getExisting();
    const found = existing.find(c => c.body && c.body.includes(MARKER));
    if (found) {
      await github.rest.issues.deleteComment({
        comment_id: found.id,
        owner: context.repo.owner,
        repo: context.repo.repo,
      });
      console.log(`${why} — bayat yorum kaldırıldı`);
    } else {
      console.log(`${why} — yorum yok`);
    }
  };

  if (!fs.existsSync(path)) {
    // config-diff.json yok — bu run'da bulgu üretilmedi; dosya yokluğu da
    // "bulgu yok" sayılır (state-sync: bayat yorumu temizle).
    await cleanupStale('config-diff.json yok');
    return;
  }
  const diff = JSON.parse(fs.readFileSync(path, 'utf8'));
  const diffs = diff.differences || [];

  if (diffs.length === 0) {
    await cleanupStale('config-diff fark yok');
    return;
  }

  const lines = diffs.map(d =>
    `- **${d.field}**: \`${JSON.stringify(d.raw)}\` → ` +
    `\`${JSON.stringify(d.effective)}\` _(${d.reason})_`
  );
  const runUrl = `${context.payload.repository.html_url}/actions/runs/${context.runId}`;
  const body = [
    '## ⚙️ Config diff (raw vs effective)',
    '',
    ...lines,
    '',
    "> Advisory: bloke etmez; bloke eden kapı config-drift job'ıdır.",
    `> Detay: [run #${context.runId}](${runUrl})`,
    '',
    MARKER,
  ].join('\n').trim();

  const existing2 = await getExisting();
  const found = existing2.find(c => c.body && c.body.includes(MARKER));
  if (found) {
    await github.rest.issues.updateComment({
      comment_id: found.id,
      owner: context.repo.owner,
      repo: context.repo.repo,
      body,
    });
    console.log(`config-diff yorumu güncellendi: comment_id=${found.id}`);
  } else {
    await github.rest.issues.createComment({
      issue_number: context.issue.number,
      owner: context.repo.owner,
      repo: context.repo.repo,
      body,
    });
    console.log('config-diff yorumu oluşturuldu');
  }
