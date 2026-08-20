  const { data: labels } = await github.rest.issues.listLabelsOnIssue({
    issue_number: context.issue.number,
    owner: context.repo.owner,
    repo: context.repo.repo,
  });
  const hasP1 = labels.some(l => l.name === 'precommit-p1');
  if (hasP1) {
    core.setFailed('precommit-p1 etiketi var — P1 bulgusu giderilene kadar merge bloke.');
  } else {
    console.log('precommit-p1 etiketi yok — P1 label gate PASS');
  }
