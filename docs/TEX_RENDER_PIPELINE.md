# Denklem → Görsel Pipeline'ı (tex-render-guide Method 1 ↔ tectonic)

Bu belge, `tex-render-guide` skill'inin **Method 1** (pdflatex + dvipng /
convert) akışını bu repoda kullanılan **tectonic + pdftoppm** akışıyla
karşılaştırır ve skill'e uygun, TeXLive bağımlılığı olmayan denklem-görsel
pipeline'ını belgeler.

Kullanım amacı: `core_section.tex`'teki 12 Z3 teoremini slayt kullanımına
uygun, sayfadan bağımsız PNG görsellerine dönüştürmek (çalışan uygulama:
`_calisma/CIKTI/render_z3_slides.py`, çıktı: `_calisma/slides_z3/`).

---

## 1. Karşılaştırma özeti

| Boyut | tex-render-guide Method 1 (klasik) | Bu repo (tectonic varyantı) |
|---|---|---|
| **Kaynak** | tek denklemli `standalone` .tex | aynı (birebir) |
| **Derleyici** | `pdflatex` (TeXLive) veya `latex`→DVI | `tectonic` (bağımsız binary, TeXLive'siz) |
| **DVI yolu** | `latex` → `dvipng -D 300 -T tight -bg Transparent` | yok (tectonic PDF üretir) |
| **PDF yolu** | `pdflatex` → `convert -density 300` (ImageMagick) | `pdftoppm -r 300 -png -singlefile` (poppler) |
| **Şeffaf arka plan** | `dvipng -bg Transparent` (DVI) / convert (PDF) | pdftoppm PNG doğal şeffaf (RGBA) |
| **Tight crop** | `dvipng -T tight` / `convert -trim` | `standalone` sınıfı zaten border'ı sıkılar |
| **TeXLive bağımlılığı** | **gerekli** (~2-4 GB) | **yok** (tectonic tek Homebrew paketi) |
| **Kurulum** | `brew install --cask mactex/basictex` | `brew install tectonic poppler` |
| **Süre (12 teorem)** | — (ölçülmedi, TeXLive yok) | ~25 sn (tek komut, 12 PNG) |
| **Çözünürlük** | 300 DPI (dvipng `-D` / convert `-density`) | 300 DPI (`pdftoppm -r`) |

**Sonuç:** Aynı görsel kalite (300 DPI, şeffaf bg, tight crop), ancak tectonic
varyantı TeXLive kurulumunu gerektirmez ve CI'da tek paketle
tekrarlanabilir. `dvipng`'in `-bg`/`-T tight` kolaylıkları, `standalone`
sınıfı (border + tight) ve pdftoppm'nin doğal RGBA çıktısıyla karşılanır.

---

## 2. tex-render-guide Method 1 (klasik akış — TeXLive gerekir)

Skill'in önerdiği orijinal akış:

```bash
# Tek denklem
cat > eq.tex << 'EOF'
\documentclass[border=2pt]{standalone}
\usepackage{amsmath,amssymb}
\begin{document}
$\displaystyle \int_{-\infty}^{\infty} e^{-x^2} \, dx = \sqrt{\pi}$
\end{document}
EOF

# Yol A — DVI + dvipng (şeffaf bg, tight crop)
latex eq.tex
dvipng -D 300 -T tight -bg Transparent eq.dvi -o eq.png

# Yol B — PDF + convert (ImageMagick)
pdflatex eq.tex
convert -density 300 eq.pdf -quality 100 -trim eq.png
```

Önemli bayraklar (skill'den):
- `dvipng -D 300` — DPI (300 baskı, 150 ekran, 600 yüksek kalite)
- `dvipng -T tight` — denkleme sıkı crop, minimum kenar boşluğu
- `dvipng -bg Transparent` — şeffaf arka plan (slayt/web için şart)
- `dvipng -fg "rgb 1.0 1.0 1.0"` — koyu arka plan için beyaz yazı
- `convert -density 300 ... -trim` — PDF'ten yüksek DPI PNG + sıkı crop

**Sınırlama:** `pdflatex`, `latex`, `dvipng`, `convert` (ImageMagick) — dördü
de TeXLive/mactex veya ayrı kurulum gerektirir. Bu makinede hiçbiri yok.

---

## 3. Bu reponun tectonic akışı (TeXLive'siz, doğrulanmış)

`render_z3_slides.py`'nin kullandığı akış — aynı girdi, farklı araçlar:

```bash
# 1) standalone .tex (birebir aynı — Method 1 girdisi)
cat > eq.tex << 'EOF'
\documentclass[border=4pt]{standalone}
\usepackage{amsmath,amssymb}
\begin{document}
$\displaystyle (T_2 \land M_0) \vDash T_1$
\end{document}
EOF

# 2) tectonic ile PDF (pdflatex yerine)
tectonic eq.tex

# 3) PDF → PNG, 300 DPI, şeffaf bg (convert yerine pdftoppm)
pdftoppm -r 300 -png -singlefile eq.pdf eq
```

Tek komutluk üretim (12 teorem):

```bash
python3 _calisma/CIKTI/render_z3_slides.py --out _calisma/slides_z3
# Araçlar: LaTeX=tectonic, PDF→PNG=pdftoppm (dpi=300, bg=transparent)
# ÖZET: 12 OK, 0 hata → _calisma/slides_z3
```

### Neden eşdeğer

| Method 1 davranışı | tectonic varyantı karşılığı |
|---|---|
| `pdflatex eq.tex` | `tectonic eq.tex` (standalone destekler) |
| `dvipng -D 300` | `pdftoppm -r 300` |
| `dvipng -T tight` | `standalone` sınıfının `border=4pt`'i (sıkı kutu) |
| `dvipng -bg Transparent` | pdftoppm PNG **RGBA** — arka plan doğal şeffaf |
| `convert -density 300 -trim` | `pdftoppm -singlefile` (standalone zaten trim'li) |
| `-fg "rgb 1 1 1"` (koyu bg) | `.tex` içinde `\color{white}` ile (xcolor) |

### Seçenekler (render_z3_slides.py)

```bash
--dpi 300        # çözünürlük (varsayılan 300; 600 yüksek kalite)
--border 4       # standalone border (pt)
--with-label     # ID + Z3 sonucu etiketi (slayt başlığı için)
--only P4-b      # tek teorem
--check-sync     # THEOREMS tablosu ↔ symbolic_proof_z3.py (fail-closed)
```

### İstenen PNG formatı — arka plan

- **Slayt (koyu tema):** varsayılan şeffaf PNG (pdftoppm RGBA) — yeterli.
- **Beyaz arka plan:** koyu temada çizgiler görünür diye beyaz kutu istenirse
  `--bg white` eklenir (şu an yalnızca varsayılan şeffaf; beyaz gerekiyorsa
  `.tex`'e `\colorbox{white}{...}` eklenir).
- **Koyu arka plan yazısı:** `\usepackage{xcolor}` + `\color{white}` denklem
  gövdesinde (dvipng `-fg` karşılığı).

---

## 4. Ne zaman hangisi?

| Durum | Pipeline |
|---|---|
| Bu repoda / CI'da (TeXLive yok, tectonic var) | **tectonic + pdftoppm** (render_z3_slides.py) |
| TeXLive zaten kurulu, tek seferlik denklem | Method 1 — `latex`+`dvipng` (DVI) veya `pdflatex`+`convert` |
| SVG gerekli (ölçeklenebilir web) | Method 1: `dvisvgm --no-fonts eq.dvi` (TeXLive) |
| Çok sayıda denklem, web (hızlı) | Method 2: KaTeX (`katex --display-mode`) |
| PDF'ten SVG | `pdf2svg eq.pdf eq.svg` (yoksa `mutool draw -F svg`) |

**Öneri:** Bu repo için kanonik pipeline **tectonic + pdftoppm**'dır —
tek Homebrew bağımlılığı (`tectonic poppler`), TeXLive'siz, doğrulanmış
(12/12 PNG), `render_z3_slides.py --check-sync` ile kodla senkron.

---

## 5. Doğrulama kaydı (2026-08-26)

- `render_z3_slides.py` → 12/12 PNG üretildi (`_calisma/slides_z3/`), 300 DPI,
  şeffaf bg, tight crop (standalone).
- PNG boyutları 2-10 KB; P1-a örneğinde 3792 opak piksel (içerik doğrulandı).
- `--check-sync` PASS: THEOREMS tablosu `symbolic_proof_z3.py` record()
  ID'leriyle birebir (12/12); drift (fazla/eksik/verdict uyuşmazlığı) → exit 1.
- Araç zinciri: `tectonic` (0.17.0) + `pdftoppm` (poppler) — TeXLive yok,
  makinede kanıtlanmış çalışma.
- DVI/dvipng yolu TeXLive gerektirdiğinden bu makinede ölçülmedi (belge
  sınırlaması; karşılaştırma skill'in belirttiği bayraklar üzerinden).
