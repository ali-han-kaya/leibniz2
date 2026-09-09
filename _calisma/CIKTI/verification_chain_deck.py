#!/usr/bin/env python3
"""Generate a minimal premium dark-theme K-layer architecture deck."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "verification_chain_deck"
W, H = 1600, 900
BG = (10, 16, 28)
PANEL = (20, 30, 48)
TEXT = (235, 242, 252)
MUTED = (155, 172, 196)
CYAN = (72, 211, 218)
PURPLE = (164, 125, 255)
GREEN = (94, 218, 151)
AMBER = (255, 190, 91)


def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def slide(title, kicker, draw_body):
    image = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(image)
    d.rectangle((0, 0, 16, H), fill=CYAN)
    d.text((90, 70), kicker.upper(), fill=CYAN, font=font(22, True))
    d.text((90, 110), title, fill=TEXT, font=font(56, True))
    d.line((90, 205, 1510, 205), fill=(45, 62, 88), width=2)
    draw_body(d)
    d.text((90, 840), "LEIBNIZ2  /  VERIFICATION CHAIN", fill=MUTED, font=font(18, True))
    return image


def text(d, xy, value, size=28, fill=TEXT, bold=False):
    d.multiline_text(xy, value, fill=fill, font=font(size, bold), spacing=10)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    slides = []
    slides.append(slide("Integrity is a chain, not a checkbox", "01  /  thesis", lambda d: (
        text(d, (110, 285), "Every artifact passes through independent gates.\nOne broken link blocks delivery.", 40),
        text(d, (110, 485), "Fail-closed  ·  reproducible  ·  offline-capable", 26, CYAN, True),
        d.rounded_rectangle((1000, 300, 1430, 650), 28, fill=PANEL, outline=PURPLE, width=3),
        text(d, (1060, 370), "P0 / P1\n→ BLOCK", 52, TEXT, True),
        text(d, (1060, 545), "INFO\n→ REPORT", 30, MUTED, True),
    )))
    slides.append(slide("K0 → K21: layered evidence", "02  /  architecture", lambda d: (
        text(d, (110, 260), "Core integrity", 26, CYAN, True),
        text(d, (110, 305), "K0–K7   artifacts · manifests · hygiene", 30),
        text(d, (110, 405), "Proof and reproducibility", 26, PURPLE, True),
        text(d, (110, 450), "K8–K14   Z3 · Lean · lineage · cleanup", 30),
        text(d, (110, 550), "Operational mirrors", 26, AMBER, True),
        text(d, (110, 595), "K15–K21   history · CI · mirror · frozen records", 30),
        d.rounded_rectangle((1050, 270, 1430, 650), 24, fill=PANEL),
        text(d, (1110, 350), "ONE\nENTRY\nPOINT", 44, TEXT, True),
        text(d, (1110, 555), "verify_delivery.py\n--full", 24, CYAN, True),
    )))
    def flow_body(d):
        steps = [("SOURCE", CYAN), ("BUILD", PURPLE), ("HASH", AMBER), ("VERIFY", GREEN), ("DELIVER", CYAN)]
        x = 110
        for i, (label, color) in enumerate(steps):
            d.rounded_rectangle((x, 390, x + 230, 510), 20, fill=PANEL, outline=color, width=3)
            text(d, (x + 35, 425), label, 26, TEXT, True)
            if i < len(steps) - 1:
                d.line((x + 245, 450, x + 285, 450), fill=MUTED, width=4)
            x += 285
        text(d, (110, 610), "The sidecar is the promise: the bytes we verified are the bytes we ship.", 30, MUTED)
    slides.append(slide("The delivery path", "03  /  flow", flow_body))
    def failure_body(d):
        rows = [("Hash drift", "P0", CYAN), ("Missing expected file", "P1", AMBER), ("Optional tool absent", "SKIP", MUTED), ("Advisory hygiene note", "INFO", GREEN)]
        y = 285
        for label, status, color in rows:
            d.rounded_rectangle((110, y, 1430, y + 85), 16, fill=PANEL)
            text(d, (150, y + 24), label, 27)
            text(d, (1240, y + 24), status, 27, color, True)
            y += 115
        text(d, (110, 770), "No silent PASS. No mystery green.", 32, CYAN, True)
    slides.append(slide("Failure modes are first-class outputs", "04  /  operations", failure_body))
    def takeaway_body(d):
        text(d, (110, 310), "The chain stays boring on purpose:", 34)
        text(d, (150, 405), "• stdlib-first\n• deterministic inputs\n• explicit findings\n• clean-clone reproducibility", 32, TEXT)
        text(d, (950, 420), "K0–K21", 68, CYAN, True)
        text(d, (950, 520), "one auditable\ndelivery decision", 30, MUTED, True)
    slides.append(slide("A small surface with a large guarantee", "05  /  take-away", takeaway_body))
    for index, image in enumerate(slides, 1):
        image.save(OUT / f"slide-{index:02d}.png")
    (OUT / "README.md").write_text("# Verification Chain deck\n\nGenerated PNG slides for visual QA. Source: `_calisma/CIKTI/verification_chain_deck.py`.\n", encoding="utf-8")
    print(f"generated {len(slides)} slides in {OUT}")


if __name__ == "__main__":
    build()
