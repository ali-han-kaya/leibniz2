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

  if (!fs.existsSync(path)) {
    console.log('config-diff.json yok — yorum atlanıyor');
    return;
  }
  const diff = JSON.parse(fs.readFileSync(path, 'utf8'));
  const diffs = diff.differences || [];
  const existing = await listComments();
  const found = existing.find(c => c.body && c.body.includes(MARKER));

  if (diffs.length === 0) {
    // Fark yok: önceki run'ın bayat uyarısını kaldır (yanıltıcı kalmasın).
    if (found) {
      await github.rest.issues.deleteComment({
        comment_id: found.id,
        owner: context.repo.owner,
        repo: context.repo.repo,
      });
      console.log('config-diff fark yok — bayat yorum kaldırıldı');
    } else {
      console.log('config-diff fark yok — yorum yok');
    }
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
