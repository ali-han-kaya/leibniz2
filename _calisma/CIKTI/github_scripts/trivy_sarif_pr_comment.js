// trivy_sarif_pr_comment.js — Trivy SARIF → PR-diff yorumu (docker-security PR koşumu).
//
// Kaynak: trivy.sarif (trivy-action format: sarif, scan-type: fs).
// Sözleşme (github_scripts_battery K16 senaryolarıyla sabit):
//   • results: [] (temiz)   → temiz-yorum UPSERT, setFailed YOK
//   • CRITICAL/HIGH bulgu   → bulgu-tablosu + diff-içi/diff-dışı damgası + setFailed
//   • bozuk SARIF (runs:[]) → setFailed, yanıltıcı yorum YOK (fail-closed)
//   • seviye-yok            → default-deny (HIGH muamelesi; sessiz geçiş yok)
// Upsert marker: <!-- trivy-sarif-pr-comment --> (pr_status_comment.js deseni).
// Çağrım: github-script adımı gövdeyi fs.readFileSync + eval(async-wrap) ile
// koşar (manifest_comment.js ile aynı desen) — module.exports YOKTUR.
"use strict";

const fs = require("fs");

const MARKER = "<!-- trivy-sarif-pr-comment -->";
const SARIF_PATH = "trivy.sarif";
const CHANGED_PATH = "changed_files.txt";
const BLOCKING = new Set(["CRITICAL", "HIGH"]);

function severityOf(result) {
  // Trivy SARIF'te gerçek seviye properties.severity'de; eksikse default-deny
  // (HIGH) — 'error' seviyesi CRITICAL/HIGH'ı ayırt edemez, tahmin edilmez.
  const sev = String(
    (result.properties && result.properties.severity) || ""
  ).toUpperCase();
  return sev || "HIGH";
}

function cell(text) {
  return String(text).slice(0, 120).replace(/\|/g, "\\|").replace(/\n/g, " ");
}

try {
  const raw = fs.readFileSync(SARIF_PATH, "utf8");
  const sarif = JSON.parse(raw);
  const runs = sarif && Array.isArray(sarif.runs) ? sarif.runs : [];
  if (runs.length !== 1) {
    // Fail-closed: SARIF üretimi bozuldu — bulgu-yokluğu İSPAT edilemez;
    // yanıltıcı "temiz" yorumu düşmeden gate'i kırmızıya çevir.
    core.setFailed(
      "SARIF bozuk (runs: " + runs.length + ") — tarama kanıtı yok, fail-closed"
    );
    return;
  }

  const changed = new Set();
  try {
    for (const line of fs.readFileSync(CHANGED_PATH, "utf8").split("\n")) {
      const f = line.trim();
      if (f) changed.add(f);
    }
  } catch {} // changed listesi yoksa tüm bulgular diff-dışı sayılır

  const findings = [];
  for (const result of runs[0].results || []) {
    const uri =
      (((result.locations || [])[0] || {}).physicalLocation || {})
        .artifactLocation || {};
    const file = String(uri.uri || "bilinmeyen-dosya");
    findings.push({
      severity: severityOf(result),
      rule: String(result.ruleId || "?"),
      message: String((result.message && result.message.text) || ""),
      file,
      inDiff: changed.has(file),
    });
  }
  const blocking = findings.filter((f) => BLOCKING.has(f.severity));
  const inDiff = blocking.filter((f) => f.inDiff);

  let body = MARKER + "\n## 🛡️ Trivy tarama raporu (docker-security)\n\n";
  if (!blocking.length) {
    body +=
      "✅ **CRITICAL/HIGH bulgu yok** — Trivy temiz " +
      "(CRITICAL/HIGH, ignore-unfixed).\n";
  } else {
    body +=
      "**" +
      blocking.length +
      "** CRITICAL/HIGH bulgu " +
      "(diff-içi: " +
      inDiff.length +
      ")\n\n";
    body +=
      "| Seviye | Kural | Bulgu | Dosya | Kapsam |\n" +
      "|--------|-------|-------|-------|--------|\n";
    for (const f of blocking) {
      body +=
        "| " +
        f.severity +
        " | `" +
        cell(f.rule) +
        "` | " +
        cell(f.message) +
        " | `" +
        cell(f.file) +
        "` | " +
        (f.inDiff ? "diff-içi" : "diff-dışı") +
        " |\n";
    }
    body +=
      "\nKapı: CRITICAL/HIGH (ignore-unfixed) → gate kırmızı. " +
      "Çözüm: yamalı base-image / pkg yükseltmesi (DOCKER_SECURITY_PATCHING.md).\n";
  }

  const { data: comments } = await github.rest.issues.listComments({
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: context.issue.number,
    per_page: 100,
  });
  const existing = comments.find((c) => c.body && c.body.includes(MARKER));
  if (existing) {
    await github.rest.issues.updateComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      comment_id: existing.id,
      body,
    });
  } else {
    await github.rest.issues.createComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: context.issue.number,
      body,
    });
  }

  if (blocking.length) {
    core.setFailed(
      "Trivy: " +
        blocking.length +
        " CRITICAL/HIGH bulgu " +
        "(diff-içi: " +
        inDiff.length +
        ") — gate kırmızı"
    );
  } else {
    console.log("Trivy temiz — CRITICAL/HIGH bulgu yok");
  }
} catch (err) {
  // Okunamaz/çözümlenemez SARIF dahil her arıza fail-closed: yanlış "temiz"
  // sinyali asla üretme, yorum düşürmeden gate'i kırmızıya çevir.
  core.setFailed(
    "SARIF yorumlanamadı: " + (err && err.message ? err.message : err)
  );
}
