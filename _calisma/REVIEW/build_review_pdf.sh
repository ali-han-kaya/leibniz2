#!/bin/bash
# build_review_pdf.sh — reproducible Review Compilation + per-page PNG gallery
# Clean-checkout reproducible: tectonic (separator) + qpdf (merge) + pdftoppm (PNG), no TeXLive/exiftool required.
# Usage:
#   ./build_review_pdf.sh                          # merged PDF only (default)
#   ./build_review_pdf.sh --with-pages             # + 9 PNGs pp 4-12 + index.html under _calisma/REVIEW/pages/
#   ./build_review_pdf.sh --pages-only             # only PNG gallery (requires existing merged sources or built PDF)
#   ./build_review_pdf.sh --help
#
# Inputs (all tracked, no generation except separator.pdf from separator.tex):
#   _calisma/V5_ICERIK/.../ingiliz_empirizmi_v3.pdf   (33 pp, tectonic; now carries hypersetup Title/Author)
#   _calisma/V5_ICERIK/.../original_manuscript.pdf     (19 pp)
#   _calisma/REVIEW/separator.tex → separator.pdf     (1 p, tectonic, SOURCE_DATE_EPOCH)
# Output:
#   _calisma/REVIEW/Stoic_Hume_Review_Compilation_2026-08-17.pdf  (53 pp = 33+1+19, Title/Author via qpdf fixup)
#   _calisma/REVIEW/pages/{p004…p012}_*.png + index.html          (--with-pages only)
#
# Reproducibility: separator.pdf uses SOURCE_DATE_EPOCH (default: git log -1 --format=%ct),
# qpdf --empty --pages is deterministic, pdftoppm -r 300 -png is deterministic (RGB, no timestamps),
# and the Title/Author fixup is a single qpdf JSON-update pass. No exiftool post-processing.
set -euo pipefail

WITH_PAGES=0
PAGES_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --with-pages) WITH_PAGES=1 ;;
    --pages-only) PAGES_ONLY=1; WITH_PAGES=1 ;;
    --help|-h)
      sed -n '2,40p' "$0" | sed 's/^# //;s/^#//'
      exit 0
      ;;
    *) echo "Unknown arg: $arg (try --help)" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REVIEW_DIR="$ROOT/_calisma/REVIEW"
PKG_DIR="$ROOT/_calisma/V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17"
SRC_REVISED="$PKG_DIR/ingiliz_empirizmi_v3.pdf"
SRC_ORIGINAL="$PKG_DIR/original_manuscript.pdf"
SEP_TEX="$REVIEW_DIR/separator.tex"
SEP_PDF="$REVIEW_DIR/separator.pdf"
OUT_PDF="$REVIEW_DIR/Stoic_Hume_Review_Compilation_2026-08-17.pdf"
PAGES_DIR="$REVIEW_DIR/pages"

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not found (need: $1)" >&2; exit 2; }; }

build_separator() {
  need tectonic
  local epoch="${SOURCE_DATE_EPOCH:-$(git -C "$ROOT" log -1 --format=%ct 2>/dev/null || printf '0')}"
  echo "→ separator.pdf from separator.tex (tectonic, SOURCE_DATE_EPOCH=$epoch)"
  # tectonic writes to .build or cwd; use --outdir for determinism
  local build_dir="$REVIEW_DIR/.build/tectonic-separator"
  mkdir -p "$build_dir"
  # tectonic needs the tex in cwd; copy or run with outdir
  SOURCE_DATE_EPOCH="$epoch" tectonic --keep-logs --outdir "$build_dir" "$SEP_TEX" 2>&1 | tail -5 || true
  local built="$build_dir/separator.pdf"
  if [[ ! -f "$built" ]]; then
    # fallback: tectonic v0.17 writes to cwd when --outdir given differently
    built="$(find "$build_dir" -name "*.pdf" -type f 2>/dev/null | head -1 || true)"
  fi
  if [[ -z "$built" || ! -f "$built" ]]; then
    echo "ERROR: tectonic did not produce separator.pdf (looked in $build_dir)" >&2
    exit 1
  fi
  cp "$built" "$SEP_PDF"
  echo "  wrote $SEP_PDF ($(wc -c < "$SEP_PDF" | tr -d ' ') B)"
}

build_merged_pdf() {
  need qpdf
  if [[ ! -f "$SRC_REVISED" ]]; then echo "ERROR: missing $SRC_REVISED" >&2; exit 1; fi
  if [[ ! -f "$SRC_ORIGINAL" ]]; then echo "ERROR: missing $SRC_ORIGINAL" >&2; exit 1; fi
  if [[ ! -f "$SEP_PDF" ]]; then
    echo "separator.pdf missing — building it first"
    build_separator
  fi
  echo "→ merged Review PDF: qpdf --empty --pages (33+1+19=53)"
  local tmp_merged
  tmp_merged="$(mktemp -t review-merged.XXXXXX.pdf)"
  trap 'rm -f "$tmp_merged" "${tmp_merged}.qdf" 2>/dev/null || true' EXIT
  qpdf --empty --pages "$SRC_REVISED" "$SEP_PDF" "$SRC_ORIGINAL" -- "$tmp_merged"

  # Fix up Title/Author/Subject: qpdf --empty inherits Info from first input (ingiliz),
  # but the Review Compilation needs its own "— Review Compilation" suffix. When ingiliz
  # has empty Title (pre-hypersetup PDF on disk), the merged QDF has no /Info at all —
  # we must create it. Uses Python stdlib + qpdf --qdf text edit (no exiftool, deterministic).
  python3 - "$tmp_merged" "$OUT_PDF" << 'PY'
import re, subprocess, sys, pathlib, tempfile, shutil
src = pathlib.Path(sys.argv[1])
dst = pathlib.Path(sys.argv[2])
title = "The Limits of Formal Methods \u2014 Review Compilation"
subject = "Review copy: revised manuscript (Part I, pp. 1-33), separator (p. 34), original manuscript (Part II, pp. 35-53)"
author = "Empirisizm"
with tempfile.NamedTemporaryFile(suffix=".qdf", delete=False) as tf:
    qdf = tf.name
try:
    r = subprocess.run(["qpdf", "--qdf", str(src), qdf], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        shutil.copy2(src, dst)
        sys.exit(0)
    t = pathlib.Path(qdf).read_text(encoding="utf-8", errors="ignore")
    orig = t

    def esc_paren(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def patch_field(text, key, value):
        esc = esc_paren(value)
        pat = re.compile(r"(" + re.escape(key) + r"\s*)\([^)]*\)")
        if pat.search(text):
            return pat.sub(r"\1(" + esc + ")", text, count=1)
        pat2 = re.compile(re.escape(key) + r"\s*<[^>]*>")
        if pat2.search(text):
            return pat2.sub(key + " (" + esc + ")", text, count=1)
        return text

    if "/Title" in t or "/Author" in t:
        t = patch_field(t, "/Title", title)
        t = patch_field(t, "/Author", author)
        if "/Subject" in t:
            t = patch_field(t, "/Subject", subject)
        else:
            t = re.sub(r"(/Title\s*\([^)]*\))", r"\1\n/Subject (" + esc_paren(subject) + ")", t, count=1)
    else:
        # No Info dict at all (ingiliz had empty Title) — inject one before trailer.
        # Inject: "N 0 obj\n<< /Title (...) /Author (...) /Subject (...) >>\nendobj" before "trailer <<"
        # and add "/Info N 0 R" into trailer.
        m = re.search(r"^(\d+) 0 obj", t, re.MULTILINE)
        max_obj = max(int(x.group(1)) for x in re.finditer(r"^(\d+) 0 obj", t, re.MULTILINE)) if m else 0
        new_obj = max_obj + 1
        info_obj = f"{new_obj} 0 obj\n<< /Title ({esc_paren(title)}) /Author ({esc_paren(author)}) /Subject ({esc_paren(subject)}) /Creator (LaTeX with hyperref) >>\nendobj\n"
        t = t.replace("trailer <<", info_obj + "trailer <<", 1)
        t = t.replace("trailer <<", "trailer <<\n  /Info " + str(new_obj) + " 0 R", 1)

    if t != orig:
        pathlib.Path(qdf).write_text(t, encoding="utf-8")
        r2 = subprocess.run(["qpdf", qdf, str(dst)], capture_output=True, text=True, timeout=30)
        if r2.returncode != 0:
            # QDF patch produced invalid PDF — fall back to plain merged (no Title)
            sys.stderr.write(f"qpdf re-linearize failed: {r2.stderr[:300]}\n")
            shutil.copy2(src, dst)
    else:
        shutil.copy2(src, dst)
finally:
    try: pathlib.Path(qdf).unlink()
    except: pass
PY
  trap - EXIT
  rm -f "$tmp_merged" 2>/dev/null || true

  # Verify
  if command -v pdfinfo >/dev/null 2>&1; then
    echo "  $(pdfinfo "$OUT_PDF" 2>/dev/null | grep -E "Pages:|Title:|Author:" | tr '\n' ';' | sed 's/ *; */; /g')"
  fi
  echo "  wrote $OUT_PDF ($(wc -c < "$OUT_PDF" | tr -d ' ') B, $(pdfinfo "$OUT_PDF" 2>/dev/null | awk '/Pages:/{print $2}') pp)"

  # Sidecar: delivery-zip sidecar patterninin aynısı (repack_delivery.write_sidecar genesis).
  # OUT_PDF'in SHA-256'sını "<sha256>  <basename>\n" formatında yanına yazar —
  # check_review_freshness bu sidecar'ı byte-for-byte, hash-eşleşmesiyle doğrular.
  python3 - "$OUT_PDF" << 'PY'
import hashlib, pathlib, sys
out = pathlib.Path(sys.argv[1])
sidecar = out.with_suffix(out.suffix + ".sha256")
h = hashlib.sha256(out.read_bytes()).hexdigest()
sidecar.write_text(f"{h}  {out.name}\n", encoding="utf-8")
print(f"  sidecar: {sidecar.name} ({h[:16]}…)")
PY
}

build_pages() {
  need pdftoppm
  mkdir -p "$PAGES_DIR"
  # Formal apparatus pp 4-12 of the Review PDF? No — of the revised manuscript (ingiliz).
  # Gallery is defined against ingiliz_empirizmi_v3.pdf pp 4-12 (see docs/TEX_RENDER_PIPELINE.md §4a).
  # Use $SRC_REVISED as source so gallery tracks the current revised manuscript, not the merged Review.
  local src="$SRC_REVISED"
  if [[ ! -f "$src" ]]; then echo "ERROR: missing $src for pages gallery" >&2; exit 1; fi
  echo "→ PNG gallery: pdftoppm -r 300 -png -singlefile -f N -l N (RGB, docs/TEX_RENDER_PIPELINE.md §4a)"
  # Ordered: pdf page → slug → caption (for index.html; must match existing pages/index.html)
  local pages=(
    "4:01_intro-scope:The Limits — §1 + §2.1 Scope & preconditions"
    "5:02_L0-language:§2.2 L₀ language (sorts I/Cont/B, 9 predicates)"
    "6:03_axioms_S-M0-HI-T1:§2.2.1–2.2.2 Axioms (S), (M0a)(M0b), (H-I), (T1)"
    "7:04_prop-P1-bridge:Props 2.1–2.2 — P1 + bridge (⋆)"
    "8:05_reiification-O1-O3-G:§2.4 Enriched L⁺: (O1)(O2)(O3), G, (G)"
    "9:06_K-lemma-P2.4:§2.5–2.6 K + Lemma 2.3 + Prop 2.4"
    "10:07_props-P2.5-P2.6-beth:Props 2.5–2.6 + Defs 2.7–2.8 (Beth)"
    "11:08_enrichments:§2.7 Three enrichments"
    "12:09_humean-table-stoic-clause:§2.8–2.9 Four-level table + Stoic clause"
  )
  # Clean legacy non-pNNN names (idempotent)
  rm -f "$PAGES_DIR"/ingiliz_empirizmi_v3_page*.png 2>/dev/null || true
  local entry pnum slug
  for entry in "${pages[@]}"; do
    pnum="${entry%%:*}"
    slug="${entry#*:}"; slug="${slug%%:*}"
    local prefix="$PAGES_DIR/p$(printf '%03d' "$pnum")_${slug}"
    pdftoppm -r 300 -png -singlefile -f "$pnum" -l "$pnum" "$src" "$prefix"
    local png="${prefix}.png"
    if [[ ! -f "$png" ]]; then echo "ERROR: pdftoppm failed for p$pnum" >&2; exit 1; fi
    # Verify RGB (color_type 2 at IHDR+9), deterministic output
    python3 - "$png" "$pnum" << 'PY'
import sys
p = sys.argv[1]
data = open(p, "rb").read()
ct = data[25]
assert ct == 2, f"expected RGB color_type 2 for p{sys.argv[2]}, got {ct}"
PY
    echo "  p$(printf '%02d' "$pnum") → $(basename "$png") ($(wc -c < "$png" | tr -d ' ') B, RGB)"
  done

  # Regenerate index.html (kept in repo; build ensures it matches PNG set)
  cat > "$PAGES_DIR/index.html" << 'HTML'
<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Formal apparatus — ingiliz_empirizmi_v3.pdf pp 4–12</title>
<style>
  :root{--bg:#0e1116;--fg:#e6e8eb;--muted:#9aa3b2;--border:#222830;--accent:#7eb8ff}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 ui-sans-system,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
  header{max-width:1100px;margin:0 auto;padding:28px 20px 10px}
  h1{margin:0 0 6px;font-size:22px;letter-spacing:-.02em}
  header p{margin:0;color:var(--muted)}
  header a{color:var(--accent);text-decoration:none}
  header a:hover{text-decoration:underline}
  main{max-width:1100px;margin:0 auto;padding:10px 20px 40px}
  nav.toc{background:#151a22;border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin:14px 0 18px}
  nav.toc ol{margin:6px 0 0 18px;padding:0}
  nav.toc li{margin:4px 0}
  nav.toc a{color:var(--fg)}
  nav.toc a:hover{color:var(--accent)}
  figure{margin:18px 0;background:#11151d;border:1px solid var(--border);border-radius:10px;overflow:hidden}
  figcaption{padding:10px 14px;border-bottom:1px solid var(--border);background:#151a22}
  figcaption strong{font-weight:600}
  figcaption span{color:var(--muted)}
  img{display:block;width:100%;height:auto;background:#fff}
  footer{max-width:1100px;margin:0 auto;padding:0 20px 30px;color:var(--muted);font-size:12px}
  code{background:#151a22;border:1px solid var(--border);padding:2px 6px;border-radius:6px}
</style>
<header>
  <h1>Formal apparatus — <code>ingiliz_empirizmi_v3.pdf</code> pp 4–12</h1>
  <p>9-page PNG gallery · <code>pdftoppm -r 300 -png -singlefile -f N -l N</code> (RGB, 8-bit/color, 2550×3300) · source: <code>_calisma/V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17/ingiliz_empirizmi_v3.pdf</code> (33 pp, tectonic 0.17.0) · next to the standalone-equation pipeline in <a href="../../docs/TEX_RENDER_PIPELINE.md">docs/TEX_RENDER_PIPELINE.md §4a</a></p>
</header>
<main>
<nav class="toc">
  <strong>Contents</strong> — click to jump. Highlighted: pp 6 / 8 / 9 and their Proposition pages.
  <ol>
    <li><a href="#p004">p04 — §1 + §2.1 Scope &amp; preconditions</a></li>
    <li><a href="#p005">p05 — §2.2 L₀ language (sorts I / Cont / B, 9 predicates)</a></li>
    <li><a href="#p006">p06 — §2.2.1–2.2.2 Axioms (S), (M0a)(M0b), (H-I), (T1) ★</a></li>
    <li><a href="#p007">p07 — Props 2.1–2.2 — P1 + bridge (⋆) — Proposition page</a></li>
    <li><a href="#p008">p08 — §2.4 Enriched L⁺: (O1)(O2)(O3), G, (G) ★</a></li>
    <li><a href="#p009">p09 — §2.5–2.6 K + Lemma 2.3 + Prop 2.4 ★ — Proposition page</a></li>
    <li><a href="#p010">p10 — Props 2.5–2.6 + Defs 2.7–2.8 (Beth) — Proposition page</a></li>
    <li><a href="#p011">p11 — §2.7 Three enrichments</a></li>
    <li><a href="#p012">p12 — §2.8–2.9 Four-level table + Stoic modal clause</a></li>
  </ol>
</nav>

<figure id="p004"><figcaption><strong>p04</strong> — §1 Introduction + §2 Formalization header + §2.1 Interpretive preconditions <span>· formalization starts here; ToC + §1 remainder</span></figcaption><img src="p004_01_intro-scope.png" alt="p04 §1 + §2.1 scope and preconditions" loading="lazy"></figure>
<figure id="p005"><figcaption><strong>p05</strong> — §2.2 Minimal extensional language L₀ <span>· sorts I / Cont / B (+ Fact ⊆ Cont in L⁺), 9 predicates Kat/Rep/Grasp/Assent/Bel/Causal/Custom/Just/StoicEp</span></figcaption><img src="p005_02_L0-language.png" alt="p05 §2.2 L0 language definitions" loading="lazy"></figure>
<figure id="p006"><figcaption><strong>p06 ★</strong> — §2.2.1–2.2.2 Axioms <span>· (S) ∀b StoicEp(b)→∃i∃c…, (M0a)(M0b), (H-I), (T1) — mechanism &amp; exclusion axioms</span></figcaption><img src="p006_03_axioms_S-M0-HI-T1.png" alt="p06 axioms S M0a M0b H-I T1" loading="lazy"></figure>
<figure id="p007"><figcaption><strong>p07 — Proposition page</strong> — Prop 2.1 (P1) Strength relation &amp; Prop 2.2 Bridge collapse <span>· T₂∧M₀⊨T₁, T₁∧M₀⊭T₂; (⋆) at single pair vs global</span></figcaption><img src="p007_04_prop-P1-bridge.png" alt="p07 propositions 2.1 2.2" loading="lazy"></figure>
<figure id="p008"><figcaption><strong>p08 ★</strong> — §2.4 Controlled reiification <span>· L⁺ = L₀ ∪ {custFact, nonjustFact, Obtains, G}, (O1)(O2)(O3), target G(custFact(b), nonjustFact(b,c))</span></figcaption><img src="p008_05_reiification-O1-O3-G.png" alt="p08 reiification O1 O2 O3 G" loading="lazy"></figure>
<figure id="p009"><figcaption><strong>p09 ★ — Proposition page</strong> — §2.5 K + Lemma 2.3 + Prop 2.4 <span>· admissible K (4 constraints), Lemma 2.3 L₀-reduct invariance, Prop 2.4 implicit definability failure</span></figcaption><img src="p009_06_K-lemma-P2.4.png" alt="p09 K lemma 2.3 proposition 2.4" loading="lazy"></figure>
<figure id="p010"><figcaption><strong>p10 — Proposition page</strong> — Props 2.5–2.6 + Defs 2.7–2.8 <span>· definitional irreducibility, stability under arbitrary L₀-theories, Beth anchor</span></figcaption><img src="p010_07_props-P2.5-P2.6-beth.png" alt="p10 propositions 2.5 2.6 definitions 2.7 2.8" loading="lazy"></figure>
<figure id="p011"><figcaption><strong>p11</strong> — §2.7 What richer languages add <span>· modal □ₛ, justification t:φ, grounding — incl. disjunctive conclusion</span></figcaption><img src="p011_08_enrichments.png" alt="p11 enrichments modal justification grounding" loading="lazy"></figure>
<figure id="p012"><figcaption><strong>p12</strong> — §2.8 Historical anchoring + §2.9 Stoic modal clause <span>· four-level Humean table (genetic/epistemic/normative/grounding) + “could not arise from what is not”</span></figcaption><img src="p012_09_humean-table-stoic-clause.png" alt="p12 four-level table and Stoic modal clause" loading="lazy"></figure>
</main>
<footer>
  Generated <code>pdftoppm -r 300 -png -singlefile -f N -l N ingiliz_empirizmi_v3.pdf pNNN_…</code> (poppler 26.08.0, RGB <code>color_type=2</code>, no <code>-gray</code>) — next to the standalone-equation path in <code>docs/TEX_RENDER_PIPELINE.md §3 / §4a</code>. Open any PNG at 100% for print-faithful axioms &amp; propositions.
</footer>
</html>
HTML
  echo "  wrote $PAGES_DIR/index.html"
  echo "PNG gallery: 9 files + index.html in $PAGES_DIR"
}

# ---- main ----
if (( PAGES_ONLY )); then
  build_pages
  exit 0
fi

# Default: merged PDF. With --with-pages, also rebuild gallery.
build_merged_pdf
if (( WITH_PAGES )); then
  build_pages
fi

echo ""
echo "Done. Outputs:"
echo "  $OUT_PDF"
if (( WITH_PAGES )); then
  echo "  $PAGES_DIR/p004_*.png … p012_*.png (9 PNGs, RGB)"
  echo "  $PAGES_DIR/index.html"
fi
