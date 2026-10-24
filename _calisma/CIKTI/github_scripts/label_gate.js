// P0 label gate (REQUIRED check) — API kotasına dayanıklı okuma.
//
// Etiket kaynağı ÖNCE olay yüküdür: `pull_request` olayında GitHub,
// etiketleri `context.payload.pull_request.labels` içinde bedava taşır.
// Önceki sürüm her koşuda REST'e gidiyordu; kurulum kotası tükendiğinde
// (403 "API rate limit exceeded for installation") REQUIRED kapı, P0
// etiketi OLMASA BİLE kırmızıya düşüyordu — yanlış-blokaj.
//
// Yük etiket taşımıyorsa (push, eksik payload) REST'e düşülür. REST de
// başarısız olursa FAIL-CLOSED: etiket durumu BİLİNMİYOR, gate PASS
// veremez (sessiz fail-open yasak).
function labelsFromPayload() {
  const pr = context.payload && context.payload.pull_request;
  if (pr && Array.isArray(pr.labels)) {
    return pr.labels.map((l) => (typeof l === 'string' ? { name: l } : l));
  }
  return null;
}

let labels = labelsFromPayload();
if (labels === null) {
  try {
    const res = await github.rest.issues.listLabelsOnIssue({
      issue_number: context.issue.number,
      owner: context.repo.owner,
      repo: context.repo.repo,
    });
    labels = res.data || [];
  } catch (e) {
    core.setFailed(
      'precommit-p0 etiketleri okunamadı (' +
        (e && e.message ? e.message : e) +
        ') — P0 label gate FAIL-CLOSED: etiket durumu bilinmiyor, PASS verilemez.'
    );
    return;
  }
}

const hasP0 = labels.some((l) => l.name === 'precommit-p0');
if (hasP0) {
  core.setFailed(
    'precommit-p0 etiketi var — P0 bulgusu giderilene kadar merge bloke.'
  );
} else {
  console.log('precommit-p0 etiketi yok — P0 label gate PASS');
}
