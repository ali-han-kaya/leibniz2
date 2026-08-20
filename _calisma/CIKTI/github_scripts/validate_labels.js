  // validate_labels.js — label tanım doğrulama (dry-run, değişiklik yapmaz).
  //
  // label_definitions.json'daki her etiketin repo'da mevcut olduğunu,
  // renk ve açıklamanın eşleştiğini doğrular. Eksik/yanlış → core.setFailed().
  // sync_labels.js ile karıştırılmamalı: bu script SADECE doğrular, oluşturmaz/güncellemez.

  const fs = require('fs');
  const DEFINITIONS_PATH = '_calisma/CIKTI/label_definitions.json';

  if (!fs.existsSync(DEFINITIONS_PATH)) {
    core.setFailed('label_definitions.json bulunamadı');
    return;
  }

  const defs = JSON.parse(fs.readFileSync(DEFINITIONS_PATH, 'utf8'));
  const expected = defs.labels || [];

  if (!expected.length) {
    console.log('label_definitions.json boş — doğrulama atlandı');
    return;
  }

  // Repo'daki mevcut etiketleri çek
  const { data: existingLabels } = await github.rest.issues.listLabelsForRepo({
    owner: context.repo.owner,
    repo: context.repo.repo,
    per_page: 100,
  });

  const errors = [];
  const ok = [];

  for (const def of expected) {
    const existing = existingLabels.find(l => l.name === def.name);

    if (!existing) {
      errors.push(`❌ ${def.name}: etiket repo'da tanımlı değil`);
      continue;
    }

    const colorMatch = existing.color === def.color;
    const descMatch = (existing.description || '') === (def.description || '');

    if (!colorMatch) {
      errors.push(
        `❌ ${def.name}: renk uyuşmuyor (beklenen: #${def.color}, ` +
        `gerçek: #${existing.color})`
      );
    }
    if (!descMatch) {
      errors.push(
        `❌ ${def.name}: açıklama uyuşmuyor (beklenen: "${def.description}", ` +
        `gerçek: "${existing.description || ''}")`
      );
    }

    if (colorMatch && descMatch) {
      ok.push(`✅ ${def.name}: tanım eşleşiyor (#${def.color})`);
    }
  }

  // Sonuç
  console.log(`\n─── Label tanım doğrulama (${expected.length} etiket) ───`);
  for (const line of ok) console.log(line);
  for (const line of errors) console.log(line);

  if (errors.length) {
    console.log(`\nSONUÇ: FAIL — ${errors.length} uyuşmazlık`);
    core.setFailed(`${errors.length} label tanım uyuşmazlığı`);
  } else {
    console.log(`\nSONUÇ: PASS — ${ok.length} etiket tanımlı ve eşleşiyor`);
  }
