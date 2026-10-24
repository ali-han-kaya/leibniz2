#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview_inline_audit.py — preview yüzeyi inline event-handler sayacı.

CSP `script-src 'self' + nonce` altında **nitelik** handler'lar
(`onclick="…"`, `onmousemove="…"`) nonce kapsamına girmez; tarayıcı
bunları sessizce bloklar. VERIFY-001 tam olarak bu sessiz kayıptı.

Sayaç TEK kaynakta yaşar: `test_preview_server.py` (eski kopya) ve
`test_preview_inline_handler_gate.py` (güvenlik kapısı) aynı fonksiyonu
kullanır; iki regex kopyası sürüklenemez.

Yüzey kümesi sabit bir dosya listesi değil, dizindeki gerçek `.html`
dosyalarıdır + `preview.js` + üreticiden gelen `design_preview.html`.
Yeni bir sayfa eklenirse kapıya kendiliğinden girer.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent

# Nitelik adı, '=', sonra alıntı. `data-*` tutmaz (`-` lookbehind'da yasak);
# `connection=` gibi kelimeler eşleşmez (önek `on` değil). Metnin BAŞINDAKİ
# `onload="…"` parçası da sayılır (`(?<![\\w-])`).
# ÖNEMLİ: HTML yorumları (<!-- ... -->) öncesinden kaldırılır; bu yorumlardaki
# onmousemove/onclick metinleri yalan pozitif (false positive) oluşturur.
COMMENT_FREE_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Inline handler: `on*` öneki, `=` ataması, değer içinde alıntı.
# `data-*` tutmaz; `connection=` gibi kelimeler eşleşmez (önek `on` değil).
# Metnin BAŞINDAKİ `onload="…"` parçası da sayılır (`(?<![\\w-])`).
INLINE_HANDLER_RE = re.compile(
    r"""(?<![\\w-])on[a-z]+\s*=\s*["']""",
    re.IGNORECASE,
)


def _strip_html_comments(text: str) -> str:
    """HTML yorumlarını (<!-- ... -->) metinden kaldır."""
    return COMMENT_FREE_RE.sub("", text)


def count_inline_handlers(text):
    """Metindeki inline event-handler niteliği eşleşmelerini döndür.

    Önce HTML yorumları temizlenir, bu yorumlardaki onmousemove/onclick
    metinlerinden yararlanılan yalan pozitif'ler giderilir.
    """
    clean = _strip_html_comments(text)
    return INLINE_HANDLER_RE.findall(clean)


def generate_design_preview(dest):
    """`design_preview.html`'i geçici yola üret ve içeriğini döndür.

    Commit dışı kopya bayat olabilir; bu yüzden her koşuda üretici çağrılır.
    Üretim başarısızsa RuntimeError — testte SKIP değil, kırmızı.
    """
    proc = subprocess.run(
        [sys.executable, str(HERE / "build_design_preview.py"), str(dest)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(HERE),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "build_design_preview.py başarısız: %s"
            % (proc.stderr or proc.stdout or "")[-400:]
        )
    return pathlib.Path(dest).read_text(encoding="utf-8")


def served_surfaces(preview_dir=None):
    """Servis edilebilen yüzeyler: gerçek `.html` kümesi + preview.js + artifact."""
    root = pathlib.Path(preview_dir or HERE)
    surfaces = {}
    for path in sorted(root.glob("*.html")):
        surfaces[path.name] = path.read_text(encoding="utf-8")
    js = root / "preview.js"
    if js.is_file():
        surfaces["preview.js"] = js.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        surfaces["üretilen design_preview.html"] = generate_design_preview(
            pathlib.Path(tmp) / "design_preview.html"
        )
    return surfaces