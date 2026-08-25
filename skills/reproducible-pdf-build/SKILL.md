---
name: reproducible-pdf-build
description: "Make LaTeX/PDF builds reproducible: metadata-stripped SHA-256 sidecars, qpdf non-determinism detection, SOURCE_DATE_EPOCH migration, and fail-closed CI gates. Use when PDF build artifacts keep changing hash between runs, when a delivery pipeline needs byte-identical rebuilds, or when auditing whether a PDF was rebuilt from known sources."
metadata:
  openclaw:
    emoji: "🔁"
    category: "research"
    subcategory: "reproducibility"
    keywords: ["PDF reproducibility", "deterministic build", "SOURCE_DATE_EPOCH", "qpdf", "metadata-stripped hash", "byte-identical repack", "tectonic", "TeXLive"]
    source: "leibniz2"
---

# Reproducible PDF Build

## Overview

Academic/engineering deliveries ship a PDF built from `.tex`. To prove the
artifact came from known sources and that a rebuild is trustworthy, you need
**build determinism**: the same inputs must produce the same bytes (or a
provable proxy of it). This skill distills a real production lesson: two
independent non-determinism sources were found and handled with a
**metadata-stripped SHA-256 sidecar** pattern plus **fail-closed gates**,
while the principled fix (`SOURCE_DATE_EPOCH`) was documented as the future
migration.

The lesson applies to any pipeline where a PDF (or other generated artifact)
enters a signed/delivered bundle:

1. **Detect** whether the build is byte-deterministic.
2. **Isolate** what exactly is non-deterministic (compiler? post-processing?).
3. **Instrument** with a hash sidecar that is itself stable.
4. **Gate** the delivery on the stable proxy (fail-closed), not on raw bytes.
5. **Document** the migration path to a deterministic toolchain.

## When to Use

- A PDF in your delivery keeps changing SHA-256 across rebuilds and you need
  to explain/contain it.
- You want a CI check that proves "the shipped PDF matches the checked-in
  sources" without recompiling in CI.
- You are migrating from a non-deterministic engine (e.g. tectonic) to
  TeXLive + `SOURCE_DATE_EPOCH` and want a verification strategy on both sides.
- You need a bundle hash that is stable across repacks even when the raw PDF
  is not reproducible.

## Background: Why PDFs Are Non-Deterministic

Two independent sources of byte drift were found in the field:

### 1. Compiler-level (tectonic 0.17.0)

`tectonic` is NOT byte-deterministic: consecutive builds of the same `.tex`
produce different byte streams (observed: 33-page manuscript, stable page
count, unstable bytes). This is a known property of the engine's internal
ordering; it does NOT affect content correctness.

### 2. Post-processing (qpdf --remove-metadata)

The `qpdf --remove-metadata` step is ALSO non-deterministic. Controlled
experiment: the **same input PDF** processed 3 times produced **3 different
outputs**:

```
run 1  b090ac01…
run 2  429984da…
run 3  509a47a6…
raw PDF  e7b0bc0b…
```

So even "strip volatile metadata then hash" is not a stable proxy if you
recompute it freely.

## The Pattern: Metadata-Stripped SHA-256 Sidecar

Instead of hashing raw PDF bytes (which drift), hash the **stripped** PDF
(`qpdf --remove-metadata` clears `/Info`, `/ID`, `/CreationDate` — the
volatile fields), and store that hash in a sidecar next to the PDF:

```
ingiliz_empirizmi_v3.pdf                  ← raw artifact
ingiliz_empirizmi_v3.pdf.metadata.sha256  ← "raw <sha256>  <filename>" (sha256sum format)
```

### Critical rule: reuse, don't recompute

Because `qpdf --remove-metadata` is itself non-deterministic, the sidecar
MUST NOT be regenerated on every repack. The rule that makes repacks
byte-identical:

> **Regenerate the sidecar ONLY when the PDF's raw SHA-256 changes.**
> If the raw hash is unchanged, reuse the existing sidecar verbatim.

Proof observed: consecutive repacks were byte-identical (zip hash stable)
once this rule was applied.

## Procedure

### Step 1 — Detect non-determinism with a rerun experiment

Write a small experiment script that runs the suspect command N times on the
SAME input and prints the distinct output hashes:

```python
# extract: qpdf_determinism_experiment.py (simplified)
import hashlib, subprocess, tempfile, shutil

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def rerun(pdf, qpdf, runs=5):
    raw = sha256_file(pdf)
    hashes = []
    for _ in range(runs):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
            out = t.name
        subprocess.run([qpdf, "--remove-metadata", pdf, out], check=True)
        hashes.append(sha256_file(out))
    distinct = len(set(hashes))
    verdict = "DETERMINISTIC" if distinct <= 1 else "NON-DETERMINISTIC"
    print(f"raw={raw[:8]}… distinct={distinct}/{runs} verdict={verdict}")
```

Run it, and **freeze the result** into a checked-in `output.txt`. The frozen
record is your gate input; a live rerun varies by design (that variation IS
the finding). Two modes keep it honest:

- default → prints the byte-stable frozen record (gate input)
- `--rerun N` → live experiment, output varies run to run

### Step 2 — Freeze a byte-stable record

The frozen output must be byte-for-byte stable so a CI gate can diff it
(like a golden-file test). If the artifact is ever rebuilt, the record goes
stale and the gate fails closed until the record is regenerated — which is
exactly the signal you want.

### Step 3 — Instrument the delivery pipeline

- Compute `(raw_sha256, stripped_sha256)` with qpdf at verification time;
  if qpdf is absent, return `(raw, None)` and SKIP the check (optional layer,
  not a hard failure — mirrors "pdfinfo optional" behavior).
- Ship the sidecar inside the bundle; the manifest includes it.
- In the repack/re-delivery tool, apply the **reuse rule**: regenerate the
  sidecar only when raw hash changed; otherwise copy the existing sidecar.

### Step 4 — Gate fail-closed on the proxy

- Keep strict raw-byte determinism checks OFF by default if the toolchain is
  known non-deterministic (a strict check would false-positive on every
  repack). Expose it behind an opt-in flag (e.g. `--strict-determinism`).
- Gate on: raw hash sidecar match (P0), manifest integrity, and — for
  build-specific claims — the frozen experiment record.
- Report drift as informational when it is expected (P0/P1 only when the
  *stable* proxy breaks, not when raw bytes drift).

### Step 5 — Document the migration path

The principled fix for engine-level non-determinism is a deterministic
toolchain:

```bash
# TeXLive + SOURCE_DATE_EPOCH (the documented target)
export SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)   # commit timestamp
export TEXMFOUTPUT="$PWD/.texmf-output"               # deterministic aux dir
pdflatex -interaction=nonstopmode manuscript.tex       # (run twice for refs)
```

Notes from the field:

- `SOURCE_DATE_EPOCH` makes TeXLive emit stable `/CreationDate` and
  `/ID` — removing the need for qpdf stripping in the common case.
- `tectonic` does not honor `SOURCE_DATE_EPOCH` the same way; the migration
  path is TeXLive + `SOURCE_DATE_EPOCH`, and the strict-determinism gate
  should stay OFF until that migration lands.
- Even after migration, keep the sidecar + reuse rule: it is the layer that
  makes repacks byte-identical regardless of engine behavior.

## Checklist

- [ ] Rerun experiment on the SAME input (≥3 runs) and record distinct hashes
- [ ] Frozen `output.txt` checked in, byte-stable, stale-detecting
- [ ] Sidecar `*.pdf.metadata.sha256` ships next to the PDF (sha256sum format)
- [ ] Reuse rule implemented: sidecar regenerated only on raw-hash change
- [ ] Verification: qpdf missing → skip (not fail); strict determinism opt-in
- [ ] Manifest includes the sidecar; delivery gate verifies raw hash P0
- [ ] Migration documented: TeXLive + `SOURCE_DATE_EPOCH` + `TEXMFOUTPUT`
- [ ] Repack proof: consecutive repacks byte-identical (zip hash stable)

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Sidecar hash differs after every repack | qpdf non-determinism | Apply reuse rule (regenerate only on raw change) |
| Strict determinism gate false-positives | Engine non-deterministic | Keep `--strict-determinism` OFF until SOURCE_DATE_EPOCH migration |
| Frozen record stale after rebuild | PDF recompiled | Regenerate record, review diff, commit as new frozen version |
| `qpdf` not installed in CI | Optional layer | Return `(raw, None)` and skip — never fail on absent optional tool |

## References

- qpdf: https://github.com/qpdf/qpdf
- Reproducible builds (PDFs): https://reproducible-builds.org/
- TeXLive + SOURCE_DATE_EPOCH: https://reproducible-builds.org/docs/source-date-epoch/
- Field artifacts (leibniz2): `qpdf_determinism_experiment.py`,
  `qpdf_determinism_output.txt`, MANIFEST V5i/V5k/V5l/V5m notes,
  `repack_delivery.py` sidecar-reuse logic, `verify_delivery.py` K6-DETERM
