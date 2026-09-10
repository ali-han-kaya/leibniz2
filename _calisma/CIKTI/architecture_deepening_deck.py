#!/usr/bin/env python3
"""Generate a concise before/after deck for three architecture candidates."""
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:  # PIL yoksa modül import edilebilir kalır; testler SKIP
    HAS_PIL = False

OUT = Path(__file__).resolve().parent.parent / "architecture_deepening_deck"
W, H = 1600, 900
BG = (10, 16, 28); PANEL = (20, 30, 48); TEXT = (235, 242, 252)
MUTED = (155, 172, 196); CYAN = (72, 211, 218); PURPLE = (164, 125, 255)
GREEN = (94, 218, 151); AMBER = (255, 190, 91)


def font(size, bold=False):
    names = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf"]
    for name in names:
        if Path(name).is_file(): return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def txt(d, xy, value, size=28, fill=TEXT, bold=False):
    d.multiline_text(xy, value, fill=fill, font=font(size, bold), spacing=10)


def base(title, kicker, accent=CYAN):
    image = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(image)
    d.rectangle((0, 0, 16, H), fill=accent)
    txt(d, (90, 70), kicker.upper(), 21, accent, True)
    txt(d, (90, 110), title, 52, TEXT, True)
    d.line((90, 205, 1510, 205), fill=(45, 62, 88), width=2)
    txt(d, (90, 840), "LEIBNIZ2  /  ARCHITECTURE DEEPENING", 18, MUTED, True)
    return image, d


def comparison(title, kicker, before, after, accent):
    image, d = base(title, kicker, accent)
    d.rounded_rectangle((100, 275, 730, 700), 24, fill=PANEL, outline=(75, 88, 112), width=2)
    d.rounded_rectangle((870, 275, 1500, 700), 24, fill=PANEL, outline=accent, width=3)
    txt(d, (145, 320), "BEFORE", 23, MUTED, True); txt(d, (915, 320), "AFTER", 23, accent, True)
    txt(d, (145, 385), before, 31); txt(d, (915, 385), after, 31)
    d.line((765, 480, 835, 480), fill=accent, width=5)
    d.polygon([(835, 480), (810, 465), (810, 495)], fill=accent)
    return image


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    slides = []
    image, d = base("Three ways to deepen the chain", "01 / framing", CYAN)
    txt(d, (110, 290), "Keep the verification boundary stable.\nDeepen the layers around it.", 42)
    txt(d, (110, 485), "01  Queryable history\n02  Controlled frontend boundary\n03  Stronger delivery evidence", 32, TEXT, True)
    txt(d, (1030, 370), "SAME\nAUTHORITY", 48, CYAN, True)
    txt(d, (1030, 545), "JSONL + SHA-256\nremain the audit source", 25, MUTED, True)
    slides.append(image)

    slides.append(comparison("01  /  Make history analytical", "02 / candidate one",
        "JSONL\n↓\nmanual scans\n↓\nlimited trend views",
        "Verified JSONL\n↓\nrebuildable SQL projection\n↓\ntrends · flakiness · anomalies\n\nProjection failure ≠ gate failure", PURPLE))

    slides.append(comparison("02  /  Put a clean boundary around the UI", "03 / candidate two",
        "Browser\n↓\nPython /api/*\n\nStatic shell + SSE\nworks, but contract is implicit",
        "Browser\n↓\nvalidated REST proxy\n↓\nPython dashboard\n\nAllowlisted routes · rate limits\nstructured errors · timeouts", CYAN))

    slides.append(comparison("03  /  Turn drift into visible evidence", "04 / candidate three",
        "Build PDF\n↓\nsidecar\n↓\nreview discovers drift late",
        "SOURCE_DATE_EPOCH build\n↓\nrebuild hash comparison\n↓\nCI blocks source/PDF drift\n\nBefore/after evidence in summary", AMBER))

    image, d = base("Choose depth without moving the trust boundary", "05 / recommendation", GREEN)
    txt(d, (110, 290), "Recommended order", 28, GREEN, True)
    txt(d, (140, 350), "1. Add the rebuild-and-compare gate\n2. Add a read-only history projection\n3. Add the external frontend proxy when needed", 34)
    txt(d, (950, 390), "FILES\n→\nPROJECTION\n→\nPRODUCT", 45, GREEN, True)
    txt(d, (950, 615), "Each step remains reversible\nand independently verifiable.", 25, MUTED, True)
    slides.append(image)

    for i, image in enumerate(slides, 1): image.save(OUT / f"slide-{i:02d}.png")
    (OUT / "README.md").write_text("# Architecture deepening deck\n\nThree candidates shown with before/after architecture visuals.\n", encoding="utf-8")
    print(f"generated {len(slides)} slides in {OUT}")


if __name__ == "__main__": build()
