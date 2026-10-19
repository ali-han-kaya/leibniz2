#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_render.py — render edilen mp4'ün SÖZLEŞMESİNİ ölçer (fail-closed).

Bir render "başarılı" sayılmaz; beklenen sözleşmeye uyması gerekir:
  kare sayısı = make_data.FRAMES, süre = FRAMES/FPS, çözünürlük = WxH.

Neden kendi ayrıştırıcımız: paketlenmiş ffprobe
(`node_modules/@remotion/compositor-darwin-arm64/ffprobe`) macOS'ta
`libavdevice.dylib` bulamadığı için Abort trap 6 ile ölüyor (ölçüldü
2026-09-26). mp4 kutu (box) ağacı stdlib ile ayrıştırılabilir; `struct` +
sabit alan ofsetleri yerine KUTU BOYLUTLARI kullanılır (aşağıdaki
`_walk`), çünkü sabit ofsetler farklı muxer'larda kayar.

  python3 check_render.py                       # out/leibniz-chain.mp4
  python3 check_render.py <mp4>                 # başka dosya
  python3 check_render.py <mp4> --json          # makine-okunur çıktı

Çıkış kodu: 0 = sözleşme tuttu, 1 = sapma (fail-closed), 2 = dosya okunamadı.

stdlib-only, cevrimdisi.
"""

import argparse
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import make_data  # noqa: E402  (kare bütçesinin tek kaynağı)

DEFAULT_MP4 = os.path.join(HERE, "out", "leibniz-chain.mp4")

# Tolerans: süre için ±0.1 sn. mp4 süresi kare süresine yuvarlanır (760 ×
# 1/30 = 25.3333 sn; kap mvhd'de 25.387 sn ölçüldü — ffmpeg'in container
# kenar yastığı). Kare SAYISI ve çözünürlük toleranssızdır.
DURATION_TOLERANCE_S = 0.1

_CONTAINERS = (b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf")


class ProbeError(Exception):
    """Dosya okunamadı / beklenen kutu bulunamadı."""


def _boxes(buf, start, end):
    """[start, end) aralığındaki üst düzey kutuları (offset, boyut, tip)."""
    off = start
    while off + 8 <= end:
        size, typ = struct.unpack(">I4s", buf[off:off + 8])
        header = 8
        if size == 1:
            if off + 16 > end:
                raise ProbeError("64-bit boyut alanı kesilmiş (offset %d)" % off)
            size = struct.unpack(">Q", buf[off + 8:off + 16])[0]
            header = 16
        elif size == 0:
            size = end - off
        if size < header or off + size > end:
            raise ProbeError("kutu boyutu geçersiz: %s @ %d (boyut %d)" % (typ, off, size))
        yield off, size, typ
        off += size


def _find(buf, path):
    """İç içe kutu yolunu bulur → (kutu gövdesinin başlangıcı, kutunun bitişi).

    `_find(b, [b'moov', b'trak'])` moov → trak yolunu verir; dönen çift
    `_boxes(buf, start, end)` içine doğrudan verilir (başlangıç + bitiş).
    """
    want = list(path)
    current = [(0, len(buf))]
    while want:
        nxt = []
        for base, limit in current:
            for off, size, typ in _boxes(buf, base, limit):
                if typ == want[0]:
                    nxt.append((off + 8, off + size))
        if not nxt:
            raise ProbeError("kutu bulunamadi: %s" % b"/".join(want).decode())
        current = nxt
        want.pop(0)
    return current[0]


def _find_in(buf, start, end, path):
    """Göreli kutu yolu: (start, end) aralığından `path` ile devam eder.

    Birden çok kutu (örn. birden çok trak) aynı yolda ise TÜMÜ döner; çağıran
    hangisini istiyorsa seçer. `trak` üst düzeyde değildir — bu yüzden
    `_find` (dosya kökünden yürür) tek başına yetmez.
    """
    current = [(start, end)]
    for want in path:
        nxt = []
        for base, limit in current:
            for off, size, typ in _boxes(buf, base, limit):
                if typ == want:
                    nxt.append((off + 8, off + size))
        if not nxt:
            raise ProbeError("kutu bulunamadi: %s" % want.decode())
        current = nxt
    return current


def read_duration(buf):
    """Kap süresi (saniye) — mvhd. Video izinin süresi mdhd'den ayrıca okunur."""
    # _find TEK sonuc dondurur (cift); _find_in liste dondurur (ilk eleman
    # secilir) — ikisinin kullanimi karistirilirsa burada tip hatasi olur.
    off, _end = _find(buf, [b"moov", b"mvhd"])
    timescale, duration = _time_fields(buf, off)
    if not timescale:
        raise ProbeError("mvhd timescale = 0")
    return duration / timescale


def _time_fields(buf, body):
    """mvhd/mdhd'nin (timescale, duration) alanlari.

    FullBox basligi: version(1)+flags(3)=4 bayt.
      v0: creation(4) modification(4) → timescale govde+12, duration govde+16
      v1: creation(8) modification(8) → timescale govde+20, duration govde+24
    """
    version = buf[body]
    if version == 0:
        return struct.unpack(">II", buf[body + 12:body + 20])
    if version == 1:
        timescale = struct.unpack(">I", buf[body + 20:body + 24])[0]
        duration = struct.unpack(">Q", buf[body + 24:body + 32])[0]
        return timescale, duration
    raise ProbeError("desteklenmeyen mvhd/mdhd surumu: %d" % version)


def read_video_track(buf):
    """Video izinin timescale/duration/kare/çözünürlüğü.

    Çoklu trak varsa ilk video trakı seçilir (trak'lar arasında kodlayıcı
    ayrımı yerine 'mdia/hdlr' handler_type == 'vide' aranır; handler bulunamazsa
    ilk trak kabul edilir — Remotion tek video trakı yazar).
    """
    # _find() (govde_baslangici, kutu_sonu) dondurur — ikisini de ACIKCA
    # isimlendir: `start + end` yazimi moov'un 40 bayt disina tasar ve
    # free/mdat kutularina yanlis bakilir (olculdu 2026-09-26).
    moov_start, moov_end = _find(buf, [b"moov"])
    for off, size, typ in _boxes(buf, moov_start, moov_end):
        if typ != b"trak":
            continue
        trak_start, trak_end = off + 8, off + size
        try:
            hoff, _ = _find_in(buf, trak_start, trak_end, [b"mdia", b"hdlr"])[0]
        except ProbeError:
            continue
        # hdlr: version/flags(4) + pre_defined(4) + handler_type(4)
        if buf[hoff + 8:hoff + 12] != b"vide":
            continue

        moff, mend = _find_in(buf, trak_start, trak_end, [b"mdia", b"mdhd"])[0]
        ts, dur = _time_fields(buf, moff)

        stbl_off, stbl_end = _find_in(buf, trak_start, trak_end, [b"mdia", b"minf", b"stbl"])[0]
        width = height = None
        for soff, ssize, styp in _boxes(buf, stbl_off, stbl_end):
            if styp != b"stsd":
                continue
            # stsd gövdesi: version/flags(4) + entry_count(4), sonra örnek
            # girdisi (kutu başlığı 8 + ardından 78 baytlık VisualSampleEntry
            # başlığı). width/height bu sabit başlığın son 4 baytıdır.
            # `_boxes` KUTU BASI dondurur (govde = bas + 8). Govde icinde:
            #   +0  version/flags (4)      +4  entry_count (4)
            #   +8  ornek girdi basligi (size 4 + tip 4)
            #   +16 reserved (6) + data_ref (2)
            #   +24 pre_defined (2) + reserved (2) + pre_defined[3] (12)
            #   +40 width (2)   +42 height (2)
            body = soff + 8
            width, height = struct.unpack(">HH", buf[body + 40:body + 44])
            break

        soff, _ = _find_in(buf, stbl_off, stbl_end, [b"stsz"])[0]
        # stsz FullBox: ver/flags(4) + sample_size(4) + sample_count(4)
        samples = struct.unpack(">I", buf[soff + 8:soff + 12])[0]
        return {
            "timescale": ts,
            "duration_s": (dur / ts) if ts else 0.0,
            "frames": samples,
            "width": width,
            "height": height,
        }
    raise ProbeError("video trak bulunamadi (hdlr != 'vide')")


def probe(path):
    with open(path, "rb") as fh:
        buf = fh.read()
    if b"ftyp" not in buf[:64]:
        raise ProbeError("mp4 imzasi yok (ftyp bulunamadi)")
    track = read_video_track(buf)
    track["file_bytes"] = len(buf)
    track["container_duration_s"] = read_duration(buf)
    return track


def check(track):
    """Sözleşme sapmalarını liste hâlinde döndürür (boş = PASS)."""
    expect_frames = make_data.FRAMES
    expect_duration = make_data.FRAMES / make_data.FPS
    problems = []
    if track["frames"] != expect_frames:
        problems.append(
            "kare %d, beklenen %d" % (track["frames"], expect_frames)
        )
    if abs(track["duration_s"] - expect_duration) > DURATION_TOLERANCE_S:
        problems.append(
            "video suresi %.4f sn, beklenen %.4f sn (±%.2f)"
            % (track["duration_s"], expect_duration, DURATION_TOLERANCE_S)
        )
    want = (make_data.WIDTH, make_data.HEIGHT)
    if (track["width"], track["height"]) != want:
        problems.append(
            "cozunurluk %sx%s, beklenen %dx%d"
            % (track["width"], track["height"], want[0], want[1])
        )
    return problems


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mp4", nargs="?", default=DEFAULT_MP4, help="olculecek mp4")
    ap.add_argument("--json", action="store_true", help="makine-okunur cikti")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.mp4):
        print("check-render: FAIL — dosya yok: %s" % args.mp4, file=sys.stderr)
        return 2
    try:
        track = probe(args.mp4)
    except (ProbeError, struct.error) as exc:
        print("check-render: FAIL — ayristirilamadi: %s" % exc, file=sys.stderr)
        return 2

    problems = check(track)
    # --json stdout'u SADECE JSON olmalidir: ozet satiri stderr'e yazilir,
    # aksi halde `json.loads(stdout)` kirilir (olculdu 2026-09-26).
    if args.json:
        print(json.dumps({"track": track, "problems": problems}, ensure_ascii=False))
    else:
        print(
            "kare=%d sure=%.4fs kap=%.4fs cozunurluk=%dx%d bayt=%d"
            % (
                track["frames"],
                track["duration_s"],
                track["container_duration_s"],
                track["width"],
                track["height"],
                track["file_bytes"],
            )
        )
    if problems:
        for p in problems:
            print("FAIL: %s" % p, file=sys.stderr)
        return 1
    print(
        "check-render: PASS — sozlesme tuttu (%d kare / %.2f sn)"
        % (track["frames"], track["duration_s"]),
        file=sys.stderr if args.json else sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
