# Denklem → Görsel Pipeline'ı (tex-render-guide Method 1 ↔ ölçülmüş motor)

Bu belge, `tex-render-guide` skill'inin **Method 1** (pdflatex + dvipng /
convert) akışını bu repodaki denklem-görsel üretimiyle karşılaştırır.

**Güncelleme (2026-10-02, ölçümle):** bu metnin ilk sürümü TeXLive'nin
kurulu olmadığı bir çağı anlatıyordu ve “TeXLive'siz” akışı bu repo için
varsayılan diye sunuyordu. Artık ölçülen durum şudur:

- TeXLive **kurulu** (Homebrew TeX Live 2026) ve iki motor da ölçülmüş;
- `render_z3_slides.py` motoru `pdflatex → latex → tectonic` **sırasıyla**
  seçer. TeXLive'li bir makinede `find_tex_engine()` = **`pdflatex`**, yani
  pratikte **Method 1** çalışır; `tectonic` yalnız TeXLive yokken devreye
  giren **düşüş** yoludur;
- PNG tarafında `find_pdf_to_png()` = `convert → magick → pdftoppm → sips`
  sırası, bu makinede **`convert`** (ImageMagick) ile sonuçlanır.

Kanonik hash'ler ve iki motorun karşılaştırması §6'dadır; tam kanonik
hash'lerin tek kaynağı `docs/ID_RESIDUAL_ACCEPTANCE.md` §4 defteridir.

Kullanım amacı: `core_section.tex`'teki 12 Z3 teoremini slayt kullanımına
uygun, sayfadan bağımsız PNG görsellerine dönüştürmek (çalışan uygulama:
`_calisma/CIKTI/render_z3_slides.py`, çıktı: `_calisma/CIKTI/slides_z3/`).

---

## 1. Karşılaştırma özeti

| Boyut | tex-render-guide Method 1 (klasik) | Bu repo (bugün ölçülen) |
|---|---|---|
| **Kaynak** | tek denklemli `standalone` .tex | aynı (birebir) |
| **Derleyici** | `pdflatex` (TeXLive) veya `latex`→DVI | `pdflatex` (TeXLive) — `tectonic` yalnız TeXLive yokken **düşüş** yolu |
| **DVI yolu** | `latex` → `dvipng -D 300 -T tight -bg Transparent` | yok (tectonic PDF üretir) |
| **PDF yolu** | `pdflatex` → `convert -density 300` (ImageMagick) | `pdftoppm -r 300 -png -singlefile` (poppler) |
| **Şeffaf arka plan** | `dvipng -bg Transparent` (DVI) / convert (PDF) | pdftoppm PNG doğal şeffaf (RGBA) |
| **Tight crop** | `dvipng -T tight` / `convert -trim` | `standalone` sınıfı zaten border'ı sıkılar |
| **TeXLive bağımlılığı** | **gerekli** (~2-4 GB) | **gerekli değil** ama **mevcut**; pipeline TeXLive varsa onu kullanır, yoksa `tectonic`e düşer |
| **Kurulum** | `brew install --cask mactex/basictex` | `brew install tectonic poppler` (düşüş yol için yeterli) |
| **Süre (12 teorem)** | — (2026-08-26 kaydında ölçülmedi) | ~25 sn (tek komut, 12 PNG; 2026-08-26 ölçümü) |
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

**Sınırlama (2026-08-26 ölçümü):** `pdflatex`, `latex`, `dvipng`, `convert`
(ImageMagick) — dördü de TeXLive/mactex veya ayrı kurulum gerektirir. O
tarihte bu makinede hiçbiri yoktu. **2026-10-02 ölçümü:** artık
`pdflatex`, `latex` ve `convert` PATH'te (`/opt/homebrew/bin`), yani bu
yol artık varsayılan olarak **yürüyor** (bkz. §6).

---

## 3. TeXLive'siz ortamda seçilen düşüş yolu (tectonic)

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
python3 _calisma/CIKTI/render_z3_slides.py --out _calisma/CIKTI/slides_z3
# Araçlar: LaTeX=tectonic, PDF→PNG=pdftoppm (dpi=300, bg=transparent)
# ÖZET: 12 OK, 0 hata → _calisma/CIKTI/slides_z3
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

**Öneri (2026-10-02 ölçümüne göre güncellendi):** bu repo için **ölçülen**
pipeline Method 1'dir — `pdflatex` (TeX Live 2026/Homebrew) + `convert`
(ImageMagick), 300 DPI, `standalone` ile tight crop. `tectonic + pdftoppm`
artık **TeXLive yokken devreye giren düşüş yoludur**; ikisi de aynı görsel
kaliteyi verir (12/12 PNG, `--check-sync` ile kodla senkron), ama bugün
seçilen motor kodda sabittir: `pdflatex → latex → tectonic`. Motora göre
kanonik hash'ler **farklıdır** (çapraz-motor byte eşitliği ölçümde imkânsız —
§6), bu yüzden “hangi motor” sorusu teslim kimliğidir ve yanıt §6'daki
defterdedir.

---

## 5. Doğrulama kaydı (2026-08-26)

- `render_z3_slides.py` → 12/12 PNG üretildi (`_calisma/CIKTI/slides_z3/`), 300 DPI,
  şeffaf bg, tight crop (standalone).
- PNG boyutları 2-10 KB; P1-a örneğinde 3792 opak piksel (içerik doğrulandı).
- `--check-sync` PASS: THEOREMS tablosu `symbolic_proof_z3.py` record()
  ID'leriyle birebir (12/12); drift (fazla/eksik/verdict uyuşmazlığı) → exit 1.
- Araç zinciri: `tectonic` (0.17.0) + `pdftoppm` (poppler) — TeXLive yok,
  makinede kanıtlanmış çalışma.
- DVI/dvipng yolu TeXLive gerektirdiğinden bu makinede ölçülmedi (belge
  sınırlaması; karşılaştırma skill'in belirttiği bayraklar üzerinden).

---

## 6. Motor karşılaştırması — ölçülmüş (2026-10-02)

Bu bölüm tahmin değil **ölçüm**dür. Kanonik hash = trailer `/ID` çifti
nötrlenmiş SHA-256 (tek uygulama: `_calisma/CIKTI/pdf_id_canonical.py`).
Ham hash'ler koşumdan koşuma değişir; aynı bağlamda kanonik hash'ler
**değişmez** — bu, determinizmin kanıtıdır.

### 6.1 Slayt pipeline'ının bugün seçtiği motor

| Adım | Çözümleme sırası (kod) | Bu makinede ölçülen (darwin) |
|---|---|---|
| TeX motoru | `pdflatex` → `latex` → `tectonic` | **`pdflatex`** — `find_tex_engine()` |
| PDF → PNG | `convert` → `magick` → `pdftoppm` → `sips` | **`convert`** — `find_pdf_to_png()` |

Yani TeXLive kurulu bir makinede bu repo **Method 1**'i yürütür; `tectonic`
yolu yalnız TeXLive yokken seçilir. Slaytlar `_calisma/CIKTI/slides_z3/`
altında üretilir ve `check-z3-slide-sync` kapısı PNG hash'lerini iki bağımsız
koşumda karşılaştırarak fail-closed denetler.

### 6.2 İki motorun kanonik hash'leri

| Bağlam | SDE | Kanonik hash | Ölçüm |
|---|---|---|---|
| tectonic 0.17.0, 1 geçiş | 0 | `ad8fca69d4e4a2e1d67e497c8a7449f22c8564f5e9b3790d0b6f85d90d318e1b` | bağlamlar arası **kararlı**; darwin **ve** CI-linux aynı |
| pdfTeX 1 geçiş (darwin, Homebrew TeX Live 2026) | 0 | `a75c340911801273b38be6ffb51a34820764b8f812d528dd2705d64117f1aa00` | 2 bağımsız koşum birebir aynı |
| pdfTeX 1 geçiş (**CI**, ubuntu-latest apt TeXLive) | 0 | `092154a0473e33c2c4d869e2123e36138612ff44f63f689437eeb8450b00fc06` | **5** bağımsız CI koşumu birebir aynı |
| pdfTeX 3 geçiş (darwin) | 0 | `544516b0d9d2f4c12b05b512b79b31ad238e82d3ca3aff81166a6bac1914f597` | `make -f docs/Makefile.texlive check` ×2 birebir aynı |
| teslim artefaktı (tectonic-era, donmuş) | SDE kaydı yok | `d4f67e39fd0ef77e8f294ca2195bb1fc784716234d0675ab88a4fd8695263a6a` | kabul defteri §4 satır 5 — K6-DETERM strict'in okuduğu referans |

**Çapraz-platform asimetri (ölçüldü):** ayrışan bacak **pdfTeX**'tir,
tectonic değil. `tectonic` her iki platformda da aynı kanonik hash'i verir;
pdfTeX'in CI-linux kanonik hash'i Homebrew darwin'den farklıdır (font/TeXLive
paket seti). Bu yüzden kabul defterinde **iki** pdfTeX satırı (darwin + CI)
ve **tek** tectonic satırı vardır.

### 6.3 Bu ne anlama geliyor?

- **Teslim** hâlâ tectonic-era: teslim PDF'inin kanonik hash'i `d4f67e39…`
  ve defterde **kendi satırında** durur. TeXLive-era yeniden derleme yapılmadı;
  yapılırsa kanonik hash değişir ve protokol gereği **bilinçli yeni satır** +
  sidecar yenilemesi olur.
- **CI/trend** pdfTeX ile ölçüyor (`determinism-trend` işi, `ubuntu-latest`).
- **Slaytlar** TeXLive varsa pdfTeX ile üretilir.
- Yani “kanonik motor” tek bir satır değil, **yüzeye göre** bir seçimdir ve
  her yüzeyin kendi defter satırı vardır. Tam listesi ve kanıtları:
  `docs/ID_RESIDUAL_ACCEPTANCE.md` §4.
- Çapraz-motor byte eşitliği ölçümde **imkânsızdır** (font/ligatür/hinting
  farkları); **içerik** eşitliği ise sağlandı — hizalama (3 geçiş) sonrası
  33 = 33 sayfa, metin farkı yalnız satır sonu heceleme kırılımları.
