#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_lease_token_fuzz.py — Öznitelik-tabanlı fuzz: lease token'i HICBIR
gozlemlenebilir cikti yuzeyinde GORUNMEZ.

Konu: iki-fazli lease delivery protokolu (bu oturumun tasarimi). GRANT ile
dagitilan per-grant capability *token*, ACK'i guncel grant'a baglar; replay
korumasinin baglayicisidir. Token yalnizca C<->W dogrulanmis kanalinda
dolasabilir; asagidaki GOZLEMLENEBILIR YUZEYLERDE asla gecmemelidir:

  log        — koordinator/child hata ayiklama loglari
  exception  — ust seviye yakalanan hata metinleri
  stdout     — child yeniden baslangic/durum baskilari
  metric     — olcum etiketleri
  status_api — durum/hata raporlari (API'ye acik)

OZELLIK (kuney): her tohum icin uretilen tum olay izdizimlerinde, gorevli
(issued) token'larin HICBIRI hicbir yuzey metninde gecmez.

ANTI-VAKLUK (uc kanit; dosya mutasyonu YOK):
  1) pozitif kontrol — token kanalda GERCEKTEN akar (GRANT/ACK transcriptte);
  2) yuzey kapsami — kampanya boyunca bes yuzeyin hepsi DOLU olur;
  3) gomulu mutasyon probu — gizleme kapatildiginda (redact=False) ayni
     fuzzer sizintiyi BULUR, en kisa olay onekine (prefix shrink) indirgenir
     ve k-1 onekinde sizinti yoktur; k Same-seed tekrar ile dogrulanir.

TEKRAR: her kosum random.Random(seed) ile deterministiktir (ayni tohum ayni
transcript). Hypotype bu ortamda KURULU DEGIL (py3.9, sistem + .venv_z3) —
tohumlu oz-el yazim property fuzzer kullanilir; daraltma, lekelerin yuzey
birikimine monoton olmasindan dolayi gecerli olan en-uzun-kisa-onek aramasi.
Kapsam notu: ozellik token'in YAZIMINI (verbatim) kapsar; encode edilmis
(base64/buyuk-harf) varyantlar model disidir.
"""

import random
import unittest

SURFACES = ("log", "exception", "stdout", "metric", "status_api")
SEEDS = tuple(range(120))
OPS_PER_RUN = 45
PROBE_SEEDS = tuple(range(20))

# Agirliklar: teslimat/retry yolu (kayip ACK kurtarma) sik; veri yuzeyleri
# kampanya boyunca hepsinin dolmasini garanti edecek agirlikta.
OPS = (
    ("grant", 1),
    ("deliver", 7),
    ("drop", 1),
    ("retry", 2),
    ("ack", 3),
    ("ack_retry", 2),
    ("forge_ack", 2),
    ("giveup", 1),
    ("forge_grant", 2),
    ("stale_grant", 2),
    ("child_crash_resume", 2),
    ("child_disk_lost", 1),
    ("report_missing", 1),
    ("coord_crash_resume", 2),
    ("dump", 2),
    ("metrics", 2),
)


class AuthError(Exception):
    """Cocuk reddederken uretilen hata (exception yuzeyine duser)."""


class Run:
    """Tek bir fuzz kosumu: durum, kanal, gozlemlenebilir yuzeyler.

    observe() TEK BOYNAZ cikti kapisiDIR; modelde hicbir yer dogrudan
    print/log yazmaz. Gizleme (redact) burada uygulanir ve yuzeylere
    ISLENMIS metin kaydedilir — yani yuzeyler gozlemcinin gordugu son
    halidir.
    """

    def __init__(self, seed, redact=True):
        self.seed = seed
        self.redact = redact
        self.rng = random.Random(seed)
        self.issued = []          # gorevli tokenlar (sizinti tanimi bunlara gore)
        self.surfaces = []        # (surface_name, final_text)
        self.transcript = []      # guvenilir kanala giren TUM mesajlar
        self.channel = []         # henuz teslim edilmemis mesajlar (kuyruk)

    def new_token(self):
        tok = "lt-" + format(self.rng.getrandbits(96), "024x")
        self.issued.append(tok)
        return tok

    def put(self, msg):
        self.transcript.append(dict(msg))
        self.channel.append(dict(msg))

    def observe(self, surface, text):
        if self.redact:
            for tok in self.issued:
                text = text.replace(tok, "[REDACTED]")
        self.surfaces.append((surface, text))


class Coordinator:
    def __init__(self, run):
        self.run = run
        self.state = "IDLE"
        self.epoch = 0
        self.current_token = None
        self.last_grant = None
        self.grant_history = []

    def _send_grant(self):
        self.epoch += 1
        msg = {
            "to": "child",
            "lease": "L",
            "epoch": self.epoch,
            "token": self.run.new_token(),
        }
        self.current_token = msg["token"]
        self.last_grant = msg
        self.grant_history.append(msg)
        self.run.put(msg)

    def grant(self):
        if self.state == "COMMITTED":
            return
        self.state = "PREPARED"
        self._send_grant()

    def giveup(self):
        """Timeout/NOT_FOUND: epoch++ ile yeniden teslim (tasarim madde 4)."""
        if self.state != "PREPARED":
            return
        self._send_grant()

    def on_ack(self, msg):
        ok = (
            self.state == "PREPARED"
            and msg.get("token") == self.current_token
            and msg.get("epoch") == self.epoch
        )
        if ok:
            self.state = "COMMITTED"
            self.run.observe("log", f"ack ok {msg}")
        else:
            # eski/gizli ACK yolu: mesaj yuzeylere tam haliyle doker (leak yolu)
            self.run.observe("status_api", f"ack rejected {msg}")

    def on_not_found(self, msg):
        self.run.observe("log", f"not_found {msg}")
        if self.state == "PREPARED":
            self.giveup()


class Child:
    def __init__(self, run):
        self.run = run
        self.watermark = 0
        self.record = None  # {"epoch", "token", "state"}

    def on_grant(self, msg):
        if (
            self.record
            and msg["epoch"] == self.record["epoch"]
            and msg["token"] != self.record["token"]
        ):
            raise AuthError(f"token mismatch {msg}")
        if msg["epoch"] < self.watermark:
            self.run.observe("log", f"stale grant rejected {msg}")
            raise AuthError(f"stale grant {msg}")
        if self.record and msg["epoch"] == self.record["epoch"]:
            # ayni grant'in tekrari: yeniden calistirma, cached ACK (kayip-ACK)
            self._send_ack()
            return
        self.watermark = max(self.watermark, msg["epoch"])
        self.record = {
            "epoch": msg["epoch"],
            "token": msg["token"],
            "state": "ACCEPTED",
        }
        self.run.observe("log", f"grant accepted {msg}")  # normal yol da leak yolu

    def ack(self):
        if not self.record:
            return
        if self.record["state"] == "ACCEPTED":
            self.record["state"] = "DONE"
        self._send_ack()

    def ack_retry(self):
        if self.record and self.record["state"] == "DONE":
            self._send_ack()

    def _send_ack(self):
        self.run.put(
            {
                "to": "coord",
                "type": "ack",
                "lease": "L",
                "epoch": self.record["epoch"],
                "token": self.record["token"],
            }
        )

    def crash_resume(self):
        self.run.observe("stdout", f"child resume record={self.record!r}")
        if self.record and self.record["state"] == "DONE":
            self._send_ack()

    def disk_lost(self):
        self.record = None
        self.watermark = 0

    def report_missing(self):
        if not self.record:
            self.run.put(
                {
                    "to": "coord",
                    "type": "not_found",
                    "lease": "L",
                    "epoch": self.run.coord.epoch,
                }
            )


def _deliver(run, msg):
    """Tek mesaj teslimi; AuthError yuzeylere yazilir (exception)."""
    try:
        if msg["to"] == "child":
            run.child.on_grant(msg)
        elif msg.get("type") == "not_found":
            run.coord.on_not_found(msg)
        else:
            run.coord.on_ack(msg)
    except AuthError as exc:
        run.observe("exception", str(exc))


def op_grant(run, rng):
    run.coord.grant()


def op_deliver(run, rng):
    if not run.channel:
        return
    n = rng.randint(1, len(run.channel))
    for _ in range(n):
        msg = run.channel.pop(rng.randrange(len(run.channel)))
        _deliver(run, msg)


def op_drop(run, rng):
    run.channel.clear()


def op_retry(run, rng):
    if run.coord.last_grant:
        run.put(run.coord.last_grant)


def op_ack(run, rng):
    run.child.ack()


def op_ack_retry(run, rng):
    run.child.ack_retry()


def op_forge_ack(run, rng):
    if not run.issued:
        return
    old = [t for t in run.issued if t != run.coord.current_token]
    if old and rng.random() < 0.7:
        tok = rng.choice(old)
    else:
        tok = "forged-" + format(rng.getrandbits(48), "012x")
    run.coord.on_ack(
        {"to": "coord", "type": "ack", "lease": "L",
         "epoch": run.coord.epoch, "token": tok}
    )


def op_giveup(run, rng):
    run.coord.giveup()


def op_forge_grant(run, rng):
    if not run.issued:
        return
    current = (run.child.record or {}).get("token")
    old = [t for t in run.issued if t != current]
    tok = rng.choice(old) if old else "forged-" + format(rng.getrandbits(48), "012x")
    msg = {
        "to": "child",
        "lease": "L",
        "epoch": run.child.watermark,
        "token": tok,
    }
    _deliver(run, msg)


def op_stale_grant(run, rng):
    hist = run.coord.grant_history
    if len(hist) < 2:
        return
    msg = hist[rng.randrange(len(hist) - 1)]
    _deliver(run, msg)


def op_child_crash_resume(run, rng):
    run.child.crash_resume()


def op_child_disk_lost(run, rng):
    run.child.disk_lost()


def op_report_missing(run, rng):
    run.child.report_missing()


def op_coord_crash_resume(run, rng):
    run.observe("log", "coordinator resumed from WAL")
    if run.coord.state == "PREPARED" and run.coord.last_grant:
        run.put(run.coord.last_grant)


def op_dump(run, rng):
    # durum raporu bekleyen GRANT'i oldugu gibi yazar (leak yolu)
    run.observe("status_api", f"state={run.coord.state} pending={run.coord.last_grant!r}")


def op_metrics(run, rng):
    if not run.issued:
        return
    tok = rng.choice(run.issued)
    run.observe("metric", f'lease_ack_total{{lease="L", token="{tok}"}}')


OPS_TABLE = {
    "grant": op_grant,
    "deliver": op_deliver,
    "drop": op_drop,
    "retry": op_retry,
    "ack": op_ack,
    "ack_retry": op_ack_retry,
    "forge_ack": op_forge_ack,
    "giveup": op_giveup,
    "forge_grant": op_forge_grant,
    "stale_grant": op_stale_grant,
    "child_crash_resume": op_child_crash_resume,
    "child_disk_lost": op_child_disk_lost,
    "report_missing": op_report_missing,
    "coord_crash_resume": op_coord_crash_resume,
    "dump": op_dump,
    "metrics": op_metrics,
}


def execute(seed, redact=True, max_ops=OPS_PER_RUN):
    run = Run(seed, redact)
    run.coord = Coordinator(run)
    run.child = Child(run)
    run.child.run = run
    names = [op for op, _ in OPS]
    weights = [w for _, w in OPS]
    for _ in range(max_ops):
        name = run.rng.choices(names, weights=weights, k=1)[0]
        OPS_TABLE[name](run, run.rng)
    return run


def surfaces_leaking(run):
    """(token, surface, text) — gorevli token yuzey metninde geciyorsa."""
    hits = []
    for tok in run.issued:
        for surface, text in run.surfaces:
            if tok in text:
                hits.append((tok, surface, text))
    return hits


def first_leak_prefix(seed, redact=False, limit=OPS_PER_RUN):
    """En kisa onek: k. onekte ilk leke; onerki boyunca leke yok (shrink)."""
    for k in range(1, limit + 1):
        run = execute(seed, redact, k)
        if surfaces_leaking(run):
            return k, run
    return None, None


class TestTokenLeakProperty(unittest.TestCase):
    """Ana ozellik: gizleme ACIKKEN gorevli token hicbir yuzeyde gecmez."""

    def test_property_token_absent_from_all_surfaces(self):
        seen_surfaces = set()
        token_on_channel = False
        for seed in SEEDS:
            run = execute(seed, redact=True)
            leaks = surfaces_leaking(run)
            self.assertEqual(
                leaks, [],
                f"token sizintisi! seed={seed} ilk={leaks[0] if leaks else None}",
            )
            seen_surfaces.update(surface for surface, _ in run.surfaces)
            for msg in run.transcript:
                if msg.get("token") in run.issued:
                    token_on_channel = True
        # anti-vakluk 1+2: token gercekten akar, yuzeylerin hepsi doludur
        self.assertTrue(token_on_channel, "token kanalda hic akmedi — ozellik vakuum")
        self.assertEqual(
            seen_surfaces, set(SURFACES),
            f"kapsanmayan yuzeyler: {set(SURFACES) - seen_surfaces}",
        )

    def test_same_seed_is_reproducible(self):
        a = execute(7, redact=True)
        b = execute(7, redact=True)
        self.assertEqual(a.surfaces, b.surfaces)
        self.assertEqual(a.transcript, b.transcript)
        self.assertEqual(a.issued, b.issued)


class TestFuzzerNonVacuity(unittest.TestCase):
    """Mutasyon probu: gizleme KAPALIYKEN fuzzer sizintiyi bulmalidir."""

    def test_probe_finds_leak_when_redaction_disabled(self):
        found = None
        for seed in PROBE_SEEDS:
            k, run = first_leak_prefix(seed, redact=False)
            if k is not None:
                found = (seed, k, run)
                break
        self.assertIsNotNone(
            found,
            "gizleme kapaliyken hic leke bulunamadi — fuzzer/probe vakuum",
        )
        seed, k, run = found
        leaks = surfaces_leaking(run)
        self.assertTrue(leaks)
        tok, surface, text = leaks[0]
        self.assertIn(tok, text)

        # shrink dogrulamasi: k deterministik tekrarlanir ve minimaldir
        k2, _ = first_leak_prefix(seed, redact=False)
        self.assertEqual(k2, k, "leke oneki tekrar uretilmedi (determinizm kirildi)")
        if k > 1:
            short = execute(seed, redact=False, max_ops=k - 1)
            self.assertEqual(
                surfaces_leaking(short), [],
                f"k-1={k - 1} onekte leke var — shrink minimal degil",
            )

        # ayni onek, gizleme ACIKKEN sizintisiz olmalidir (eslesme kaniti)
        paired = execute(seed, redact=True, max_ops=k)
        self.assertEqual(surfaces_leaking(paired), [])


if __name__ == "__main__":
    unittest.main()
