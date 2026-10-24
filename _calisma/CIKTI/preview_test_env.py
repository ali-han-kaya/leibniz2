#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview_test_env.py — testlerde preview_server yazımlarını geçici dizine taşır.

Neden var: preview_server çalışırken ÜRETİR — `history.jsonl` (+ `.sha256`
sidecar), `runs/run-*.json`, `logs/server_events.jsonl`, `klayers.json`,
`trend_sync.json`. Hepsi `--preview-dir`'in altına yazılıyordu ve birçok kapı
testi sunucuyu `--preview-dir <repo>` ile başlatıyor (gerçek `preview.html`
gerekiyor). Sonuç: test koşusu repoda gitignore'lu ama **gerçek** çalışma
zamanı dosyaları bırakıyordu; `_calisma/CIKTI/history.jsonl`, `runs/`,
`logs/server_events.jsonl` zamanla MB'lara çıktı ve "ağaçta ne değişti?"
sorusu testin kendi çıktısıyla karıştı.

Sunucu artık yazım kökünü ayrı tutabiliyor (`--runtime-dir`, varsayılan
`--preview-dir` — üretim davranışı değişmez). Bu modül o bayrağı testlerin
tek satırda, geçici bir dizinle kullanmasını sağlar:

    from preview_test_env import runtime_args, RuntimeProbe

    proc = subprocess.Popen([sys.executable, SERVER_SCRIPT,
                             "--dir", HERE, "--preview-dir", HERE,
                             *runtime_args("tooltip"), ...])

`runtime_args()` her çağrıda YENİ bir dizin üretir (paralel/ardışık sunucular
birbirinin history dosyasını ezmesin) ve süreç çıkışında siler. Dizin her
zaman `tempfile.gettempdir()` altındadır — repo içine, önbelleğe veya HOME'a
yazmaz.

`RuntimeProbe` repo kökündeki çalışma zamanı yollarının (var olanlarla yok
olanların ayrımıyla) anlık görüntüsünü alır; `changed()` iki görüntü arasında
OLUŞAN/DEĞİŞEN yolları döndürür. Kapı testi "ağaç temiz kaldı" iddiasını bu
araçla, sayısal olarak (mtime_ns + boyut) kurar.

Yalnız stdlib; sunucuyu import etmez (alt-süreç olarak koşan testler de kullanır).
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# Sunucunun repo/önbellek dizinine bıraktığı çalışma zamanı izleri. Repo
# içinde bunlar gitignore'ludur; yine de "test ağacı kirletmesin" sözleşmesi
# bu yolların DEĞİŞMEMESİNİ ister.
REPO_RUNTIME_RELPATHS = (
    "history.jsonl",
    "history.jsonl.sha256",
    "runs",
    "logs/server_events.jsonl",
    "klayers.json",
    "trend_sync.json",
)

_REGISTERED = []


def runtime_dir(label="gate"):
    """Geçici bir çalışma zamanı dizini üret; süreç çıkışında silinir.

    Her çağrı benzersizdir: iki sunucu aynı dizini paylaşırsa `history.jsonl`
    son-yazan-kazanır yarışına girer ve izolasyon kanıtı kırılganlaşırdı.
    """
    prefix = "preview-runtime-%s-" % (label or "gate")
    path = tempfile.mkdtemp(prefix=prefix)
    _REGISTERED.append(path)
    return path


@atexit.register
def _cleanup():
    """Süreç sonunda üretilen tüm dizinleri kaldır (hata sessizce yutulur)."""
    while _REGISTERED:
        shutil.rmtree(_REGISTERED.pop(), ignore_errors=True)


def runtime_args(label="gate"):
    """Popen listesine eklenecek `--runtime-dir <geçici>` çifti."""
    return ["--runtime-dir", runtime_dir(label)]


def in_process_runtime(module, label="inproc"):
    """In-process testler için sunucu globallerini geçici dizine yönlendir.

    `module` preview_server'dır. Döndürülen `RuntimeHandle` eski değerleri
    tutar; `handle.restore(module)` çağrısı (tearDown) bunları geri koyar.
    `preview.html`/`preview.js` okumaları PREVIEW_DIR'de kalır — yalnız yazım
    globalleri taşınır.
    """
    runtime = runtime_dir(label)
    handle = RuntimeHandle(runtime=runtime, saved=(
        module.RUNTIME_DIR,
        module.HISTORY_PATH,
        module.RUNS_DIR,
        module.SERVER_EVENTS_PATH,
    ))
    module.RUNTIME_DIR = runtime
    module.HISTORY_PATH = os.path.join(runtime, "history.jsonl")
    module.RUNS_DIR = os.path.join(runtime, "runs")
    module.SERVER_EVENTS_PATH = os.path.join(runtime, "logs",
                                            "server_events.jsonl")
    return handle


class RuntimeHandle(object):
    """`in_process_runtime` çıktısı: geri alma için eski globalleri taşır."""

    def __init__(self, runtime, saved):
        self.runtime = runtime
        self.saved = saved

    def restore(self, module):
        (module.RUNTIME_DIR, module.HISTORY_PATH, module.RUNS_DIR,
         module.SERVER_EVENTS_PATH) = self.saved


def _stat(path):
    """Dosya/dizin için (mtime_ns, size) ya da None (yok)."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


class RuntimeProbe(object):
    """Repo kökündeki çalışma zamanı yollarının anlık görüntüsü.

    Dizinlerin de izlenmesi bilinçli: `runs/` boş kalsa bile oluşması bir
    yazımdır (mtime değişir).
    """

    def __init__(self, root=None):
        self.root = os.path.abspath(root or HERE)
        self.before = self.snapshot()

    def paths(self):
        return [os.path.join(self.root, rel) for rel in REPO_RUNTIME_RELPATHS]

    def snapshot(self):
        return {rel: _stat(os.path.join(self.root, rel))
                for rel in REPO_RUNTIME_RELPATHS}

    def changed(self):
        """`before`'a göre oluşan/değişen göreli yollar (sıralı)."""
        after = self.snapshot()
        return sorted(rel for rel, value in after.items()
                      if value != self.before.get(rel))
