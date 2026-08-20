  const fs = require('fs');
  const DEFINITIONS_PATH = '_calisma/CIKTI/label_definitions.json';

  if (!fs.existsSync(DEFINITIONS_PATH)) {
    console.log('label_definitions.json bulunamadı — label sync atlandı');
    return;
  }

  const defs = JSON.parse(fs.readFileSync(DEFINITIONS_PATH, 'utf8'));
  const expected = defs.labels || [];

  // Repo'daki mevcut etiketleri çek
  const { data: existingLabels } = await github.rest.issues.listLabels({
    owner: context.repo.owner,
    repo: context.repo.repo,
    per_page: 100,
  });

  let created = 0, updated = 0, unchanged = 0;

  for (const def of expected) {
    const existing = existingLabels.find(l => l.name === def.name);

    if (!existing) {
      // Etiket yok → oluştur
      await github.rest.issues.createLabel({
        owner: context.repo.owner,
        repo: context.repo.repo,
        name: def.name,
        color: def.color,
        description: def.description || '',
      });
      console.log(`Etiket oluşturuldu: ${def.name} (#${def.color})`);
      created++;
    } else {
      // Etiket var → renk/açıklama eşleşiyor mu?
      const colorMatch = existing.color === def.color;
      const descMatch = (existing.description || '') === (def.description || '');

      if (!colorMatch || !descMatch) {
        await github.rest.issues.updateLabel({
          owner: context.repo.owner,
          repo: context.repo.repo,
          name: def.name,
          color: def.color,
          description: def.description || '',
        });
        console.log(`Etiket güncellendi: ${def.name} ` +
          `(renk: ${existing.color}→${def.color}, ` +
          `açıklama: ${descMatch ? 'aynı' : 'güncellendi'})`);
        updated++;
      } else {
        console.log(`Etiket güncel: ${def.name}`);
        unchanged++;
      }
    }
  }

  console.log(`\nLabel sync: ${created} oluşturuldu, ${updated} güncellendi, ${unchanged} unchanged`);
