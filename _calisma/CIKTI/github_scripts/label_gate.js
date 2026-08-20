  const { data: labels } = await github.rest.issues.listLabelsOnIssue({
    issue_number: context.issue.number,
    owner: context.repo.owner,
    repo: context.repo.repo,
  });
  const hasP0 = labels.some(l => l.name === 'precommit-p0');
  if (hasP0) {
    core.setFailed('precommit-p0 etiketi var — P0 bulgusu giderilene kadar merge bloke.');
  } else {
    console.log('precommit-p0 etiketi yok — P0 label gate PASS');
  }
