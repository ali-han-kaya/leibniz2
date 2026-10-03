#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""precommit_log.py — pre-commit log'unun tek okuyucusu.

Kavram (bkz. CONTEXT.md "Pre-commit log"): pre-commit verbose çıktısının
tek bir log'u var; iki rota üzerinden gelir (canlı subprocess stdout/stderr
ya da disksel logs/precommit.log) ve hepsinden hook kayıtları çıkarılır.

İki katman:

  1) Saf ayrıştırıcılar — verilen metinden kayıtlara:
       parse_hooks(text, source)       -> [{name, id, status, source}]
       parse_update_config(text)       -> (status|None, [satır])
       parse_findings(text, uc, out)   -> [(öncelik, mesaj)]
  2) Tek toplayıcı — kaynak önceliğini SAHİP olur:
       collect(stderr, stdout, sidecar_paths) -> kayıtlar | None
       Öncelik: stderr -> stdout -> sidecar. Hiçbiri hook üretmezse None
       (panel yerinde durur: "hook verisi bekleniyor").

NEDEN VAR (2026-10-02 ölçümü, bu modülün doğduğu hata):
pre-commit `run --all-files --show-diff-on-failure` çıktısının 52 hook
satırinin TAMAMI stdout'ta, stderr 0 bayt'tir — hook'lar başarısız olsa
bile. preview_server içinde iki çağrış sitesi farklı kural okuyordu
(biri `stderr or stdout` birleştirip tek sefer, diğeri `parse(stderr) or
parse(stdout)`), _finalize_run ise YALNIZ stderr'a bakıyordu; üç yol
aynı veriye bakıp farklı sonuç üretti ve panel "⏳ hook verisi
bekleniyor…"da takildi. Bugünün kanıtı: kaynak kurali tek yerde
(toplayıcı), ayrıştırıcı tek aile (STATUS_RE + _HOOK_ID_RE), kayıt tek
şekil ({name, id, status, source}).

Yan kaynaklar: run_summary_precommit.py sidecar'i AYRI sözleşmesiyle
(schema doğrulamali, katı) okur — bu modülün sidecar okuması TOLERANSTIR
(bozuk/eksik -> None -> panel placeholder korunur). İki bilinçli sözleşme,
tek dosya.

Kayıt `source` alanı: kayıtların hangi kaynaktan okunduğunu söyler
(stderr | stdout | sidecar | log) — takilpaneli sinifini yeniden
araştırmayı gereksiz kılar; PRECOMMIT_RAPORU.schema.json ile kilitli.

OFFLINE, stdlib-only. Ayrıştırıcılar safdır; toplayıcı dosya okur.
"""
import json
import re

STATUS_RE = re.compile(r"^(.*?)\.{4,}(Passed|Failed)\s*$", re.M)
# Hook durum satırını izleyen öznitelik bloğu: "- hook id: check-python3-shell"
_HOOK_ID_RE = re.compile(r"^-\s*hook\s+id:\s*(\S+)\s*$", re.M)

# schema enum ile kilitli (PRECOMMIT_RAPORU.schema.json -> hooks.items.source)
SOURCES = ("stderr", "stdout", "sidecar", "log")


def parse_hooks(log_text, source):
    """pre-commit verbose çıktısından hook sonuçlarını ayrıştır.

    Her hook satırı 'Hook adı………Passed|Failed' biçimindedir; durum satırını
    izleyen öznitelik bloğundaki `- hook id:` değeri de kaydedilir (örn.
    display adı 'Block shell commands under shell: python3 {0}' iken id
    'check-python3-shell' — makine-okur kimlik). id bulunamazsa None.
    `source` kayıtların okunduğu kaynağı taşır (SOURCES sözleşmesi).
    Boş/None metin -> [] (kaynak yok = kayıt yok; toplayıcı karar verir).
    """
    if not log_text:
        return []
    hooks = []
    for m in STATUS_RE.finditer(log_text):
        nxt = STATUS_RE.search(log_text, m.end())
        seg = log_text[m.end(): nxt.start() if nxt else len(log_text)]
        idm = _HOOK_ID_RE.search(seg)
        hooks.append({
            "name": m.group(1).strip(),
            "id": idm.group(1) if idm else None,
            "status": m.group(2),
            "source": source,
        })
    return hooks


def parse_update_config(log_text):
    """update-config hook'unun durumu + kendi çıktısı (denetim izi).

    Hook satırı ('Sync config …Passed/Failed') ile bir SONRAKİ hook satırı
    arasındaki satırlar o hook'un stdout/stderr çıktısıdır (verbose: true).
    """
    if not log_text:
        return None, []
    uc_status = None
    uc_output = []
    for m in STATUS_RE.finditer(log_text):
        if "Sync config" in m.group(1) or "gen_config" in m.group(1):
            uc_status = m.group(2)
            nxt = STATUS_RE.search(log_text, m.end())
            end = nxt.start() if nxt else len(log_text)
            for line in log_text[m.end():end].splitlines():
                s = line.strip()
                if not s or s.startswith("- hook id:") or s.startswith("- duration:"):
                    continue
                uc_output.append(s)
            break
    return uc_status, uc_output


def parse_findings(log_text, uc_status, uc_output):
    """P0/P1 bulgularını ayrıştır; update-config FAIL'i ayrı P1 bulgusu yapar."""
    findings = []
    if not log_text:
        return findings
    for pri in ("P0", "P1"):
        for m in re.finditer(rf"^\[{pri}\] (.+)$", log_text, re.M):
            findings.append((pri, m.group(1).strip()))

    # update-config FAIL → ayrı bir bulgu (CI'da drift/modifikasyon işareti).
    if uc_status == "Failed":
        detail = " | ".join(uc_output) if uc_output else "çıktı yok"
        findings.append(("P1",
                         f"update-config FAIL — config paket içeriğiyle "
                         f"senkronlanamadı (CI'da drift/modifikasyon). "
                         f"Çıktı: {detail}"))
    return findings


def _read_sidecar(path):
    """PRECOMMIT_RAPORU.json toleranslı okuma -> kayıtlar | None.

    Bozuk/eksik/boş -> None (panel placeholder'ı korunur; katı doğrulama
    run_summary_precommit.py'nin işi). Kayıtlar bu noktada YENİDEN
    `sidecar` kaynağıyla damgalanır: kaynağı, toplayıcının hangi adayı
    kullandığını söyler — sonraki teşhis için kanıt zinciri kırılmaz.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("hooks") or []
    except (OSError, ValueError, AttributeError):
        return None
    hooks = []
    for h in raw:
        if isinstance(h, dict) and h.get("name"):
            hooks.append({
                "name": h.get("name", "?"),
                "id": h.get("id"),
                "status": h.get("status", "Unknown"),
                "source": "sidecar",
            })
    return hooks or None


def collect(stderr=None, stdout=None, sidecar_paths=()):
    """Kaynak önceliğiyle hook kayıtlarını topla: stderr -> stdout -> sidecar.

    Öncelik KURALI burada yaşar (2026-10-02 asimetrisi bu yüzden tek yere
    indi): her kaynak PARSE edilir, boş metin değil — stderr dolu ama
    hooksuz ise stdout denenir. sidecar yalnız çağıran isterse denenir
    (arka plan yolu taze çıktı üretir, eski sidecar göstermez).

    Hook üreten ilk kaynak kazanır; hiçbirı üretmezse None.
    """
    for text, source in ((stderr, "stderr"), (stdout, "stdout")):
        hooks = parse_hooks(text, source)
        if hooks:
            return hooks
    for path in sidecar_paths:
        hooks = _read_sidecar(path)
        if hooks:
            return hooks
    return None
