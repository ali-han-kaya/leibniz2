#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""token_delivery.py — "token delivery" ozellik kontrati icin CI giris noktasi.

Sozlesme (exit-code contract — CI adimi bu kodlari bekler):

  0  PASS    — ozellik yerinde: gorevli token HICBIR gozlemlenebilir yuzeyde
               gecmiyor (log/exception/stdout/metric/status_api) VE vakluk
               korumalari yesil (asagidaki 2 kontrolleri dahili kosar).
  1  LEAK    — en az bir yuzeyde gorevli token goruldu (seed + yuzey +
               en-kisa-ozet JSON'da; stderr'e verdict satiri).
  2  VACUITY — kontrat kirik: fuzzer vakuum. Tetikler: (a) token kanalda hic
               akmedi (pozitif kontrol), (b) bes yuzeyden biri kampanyada
               hic dolmadi, (c) gizleme-KAPALI prob hic leke bulamadi
               (mutasyon probu), (d) hic token uretilmedi / tohum bos.
  3  ENV     — ortam/kullanim hatasi: modul import edilemedi, beklenmeyen
               istisna, gecerli-olmayan arguman. Fail-closed varsayilan:
               hicbir hata yolu 0 uretmez.

AIR-GAP: bu CLI calismaya baslamadan once socket katmanini KAPATIR
(socket.socket / create_connection / getaddrinfo -> RuntimeError). Test
paketi stdlib-disi hicbir sey kullanmaz; bir gun ag cagrisi sizarsa
istisna yukarida yakalanir ve rc=3 olur — "ag kullanilmadi" iddiasi
kodla zorlanir, sozle degil. Pip kurulumu YOKTUR, calisma boyunca ag
gerekmez; CI adimi da `--redact off` canary'siyle kapinin kendini
oldurerek (mutation) vakluk denetimi yapar.

Kullanim:
  python3 token_delivery.py                    # kampayna (120 tohum), rc 0/1/2/3
  python3 token_delivery.py --json --out r.json
  python3 token_delivery.py --redact off       # mutasyon kipi: rc=1 BEKLENIR

stdout: insan-okunur ozet (veya --json ile TEK JSON belgesi);
stderr: verdict satiri (summary_pattern_drift deseni). --out: JSON raporu
dosyaya da yazar (CI ozet/ek icin).
"""
import argparse
import json
import pathlib
import socket
import sys
import traceback

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

RC_PASS, RC_LEAK, RC_VACUITY, RC_ENV = 0, 1, 2, 3
SURFACES = ("log", "exception", "stdout", "metric", "status_api")


def install_airgap_guard():
    """Socket katmanini kapat (air-gap, kodla zorlanmis)."""
    def _blocked(*_a, **_k):
        raise RuntimeError("token_delivery: ag erisimi engellendi (air-gap)")
    socket.socket = _blocked          # type: ignore[assignment]
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked


def evaluate(campaign):
    """Saf degerlendirme: kampanya ozeti -> (rc, report).

    campaign: {"seeds", "total_leaks", "first_leak", "token_on_channel",
               "surfaces_seen", "issued_any", "probe_found_leak"}
    Test edilebilir saf cekirdek: CI disinda unit test rc haritasini pin'ler.
    """
    report = dict(campaign)
    if not campaign.get("seeds"):
        return RC_VACUITY, _with(report, verdict="VACUITY",
                                 reason="bos tohum kumesi")
    if not campaign.get("issued_any"):
        return RC_VACUITY, _with(report, verdict="VACUITY",
                                 reason="hic token uretilmedi")
    if not campaign.get("token_on_channel"):
        return RC_VACUITY, _with(report, verdict="VACUITY",
                                 reason="token kanalda hic akmedi (pozitif "
                                        "kontrol kirik)")
    missing = [s for s in SURFACES if s not in (campaign.get("surfaces_seen") or ())]
    if missing:
        return RC_VACUITY, _with(report, verdict="VACUITY",
                                 reason=f"yuzeyler kapali: {missing}")
    if campaign.get("redact") and not campaign.get("probe_found_leak"):
        return RC_VACUITY, _with(report, verdict="VACUITY",
                                 reason="gizleme-kapali prob leke bulamadi "
                                        "(mutasyon probu kirik)")
    if campaign.get("total_leaks"):
        return RC_LEAK, _with(report, verdict="LEAK")
    return RC_PASS, _with(report, verdict="PASS")


def _with(report, verdict, reason=None):
    report = dict(report)
    report["verdict"] = verdict
    if reason:
        report["reason"] = reason
    return report


def run_campaign(redact, seeds_count, ops_count, probe_seeds):
    """Fuzzer'i kostur; kampanya ozeti + ilk leke detayi dondur.

    probe (yalniz redact=True): gizleme-KAPALI kisa prob — fuzzer'in
    leke yakalayabildigini kanitlar (vakluk korumasi c).
    """
    try:
        import test_lease_token_fuzz as fuzz
    except Exception as exc:  # import hatasi = ortam hatasi (fail-closed)
        raise RuntimeError(f"fuzzer modulu import edilemedi: {exc}") from exc

    seeds = list(range(seeds_count))
    total_leaks = 0
    first_leak = None
    token_on_channel = False
    surfaces_seen = set()
    issued_any = False

    for seed in seeds:
        run = fuzz.execute(seed, redact=redact, max_ops=ops_count)
        if run.issued:
            issued_any = True
        leaks = fuzz.surfaces_leaking(run)
        total_leaks += len(leaks)
        if leaks and first_leak is None:
            tok, surface, text = leaks[0]
            k, _ = fuzz.first_leak_prefix(seed, redact=False,
                                          limit=ops_count)
            first_leak = {"seed": seed, "surface": surface,
                          "token_prefix": tok[:12],
                          "text_head": text[:160],
                          "minimal_prefix_ops": k}
        for surface, _text in run.surfaces:
            surfaces_seen.add(surface)
        for msg in run.transcript:
            if msg.get("token") in run.issued:
                token_on_channel = True

    probe_found_leak = None
    if redact:
        probe_found_leak = False
        for seed in probe_seeds:
            k, probe_run = fuzz.first_leak_prefix(seed, redact=False,
                                                  limit=ops_count)
            if k is not None and fuzz.surfaces_leaking(probe_run):
                probe_found_leak = True
                break

    return {
        "redact": redact,
        "seeds": len(seeds),
        "ops_per_seed": ops_count,
        "total_leaks": total_leaks,
        "first_leak": first_leak,
        "token_on_channel": token_on_channel,
        "surfaces_seen": sorted(surfaces_seen),
        "issued_any": issued_any,
        "probe_found_leak": probe_found_leak,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="lease token delivery ozellik kontrati (air-gap, fail-closed)")
    ap.add_argument("--json", action="store_true",
                    help="stdout TEK JSON belgesi")
    ap.add_argument("--out", metavar="PATH", help="JSON raporu dosyaya yaz")
    ap.add_argument("--seeds", type=int, default=120,
                    help="kampanya tohum sayisi (varsayilan 120)")
    ap.add_argument("--ops", type=int, default=45,
                    help="tohum basina olay sayisi (varsayilan 45)")
    ap.add_argument("--probe-seeds", type=int, default=20,
                    help="vakluk probu tohum limiti (varsayilan 20)")
    ap.add_argument("--redact", choices=("on", "off"), default="on",
                    help="gizleme; 'off' mutasyon kipidir (rc=1 beklenir)")
    args = ap.parse_args(argv)

    if args.seeds < 1 or args.ops < 1 or args.probe_seeds < 1:
        print("token_delivery: --seeds/--ops/--probe-seeds >= 1 olmali",
              file=sys.stderr)
        return RC_ENV

    install_airgap_guard()
    try:
        campaign = run_campaign(redact=(args.redact == "on"),
                                seeds_count=args.seeds,
                                ops_count=args.ops,
                                probe_seeds=range(args.probe_seeds))
        rc, report = evaluate(campaign)
    except SystemExit:
        raise
    except Exception as exc:  # beklenmeyen hata = ortam hatasi (fail-closed)
        rc, report = RC_ENV, {
            "verdict": "ENV",
            "error": f"{type(exc).__name__}: {exc}",
            "trace_tail": traceback.format_exc().splitlines()[-3:],
        }

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    if args.json:
        print(payload)
    else:
        print(f"token_delivery: verdict={report.get('verdict')} "
              f"rc={rc} seeds={report.get('seeds')} "
              f"leaks={report.get('total_leaks')}")
        if report.get("first_leak"):
            fl = report["first_leak"]
            print(f"  ilk leke: seed={fl['seed']} yuzey={fl['surface']} "
                  f"onek={fl['minimal_prefix_ops']}")
        if report.get("reason"):
            print(f"  sebep: {report['reason']}")
    print(f"Sonuc: {report.get('verdict')} (rc={rc})", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
