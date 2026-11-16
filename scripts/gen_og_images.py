#!/usr/bin/env python3
"""Generate 1200x630 OG images (solid dark bg, big tool name, cryptopay tagline)
into site/og/. Uses Pillow + Space Grotesk variable font (OFL, in scripts/fonts/)
to match the design language; falls back to DejaVu if the TTF is missing.
Idempotent."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "og"
OUT.mkdir(parents=True, exist_ok=True)
SG_VF = ROOT / "scripts" / "fonts" / "SpaceGrotesk-VF.ttf"
DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEJAVU_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

W, H = 1200, 630
BG = (11, 18, 32)        # #0b1220
INK = (226, 232, 240)    # #e2e8f0
MUTED = (159, 176, 208)  # #9fb0d0
ACCENT = (138, 180, 255) # #8ab4ff
MINT = (126, 224, 192)   # #7ee0c0


def sg_font(size, weight):
    """Space Grotesk at a named weight instance, or DejaVu fallback."""
    if SG_VF.is_file():
        f = ImageFont.truetype(str(SG_VF), size)
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
        return f
    return ImageFont.truetype(DEJAVU_BOLD if weight == "Bold" else DEJAVU_REG, size)


IMAGES = {
    "home": {
        "title": "Xion's Micro Tools",
        "subtitle": "Tiny paid tools · crypto checkout",
    },
    "bundle": {
        "title": "Lifetime bundle — all 3 tools",
        "subtitle": "$49 · one payment · lifetime updates",
    },
    "crypto-invoice-generator": {
        "title": "Crypto Invoice Generator",
        "subtitle": "Printable invoices with BTC / ETH / SOL payment QR",
    },
    "cron-ping-monitor": {
        "title": "Cron Ping Monitor",
        "subtitle": "Uptime pinger + static status page, $0 hosting",
    },
    "telegram-broadcaster": {
        "title": "Telegram Broadcast Bot",
        "subtitle": "Broadcast + schedule posts with the raw Bot API",
    },
    "citation-monitor-weekly-digest": {
        "title": "Citation Monitor — Weekly Digest",
        "subtitle": "Where AI engines cite you vs competitors, every Monday",
    },
    "citation-monitor-agency": {
        "title": "Citation Monitor — Agency",
        "subtitle": "3 brands tracked in one weekly AI-visibility report",
    },
}


def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        cand = (cur + " " + w_).strip()
        if draw.textlength(cand, font=font) <= max_w:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def gen(name, title, subtitle):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # subtle top rule in the accent gradient pair
    d.rectangle([0, 0, W // 2, 6], fill=ACCENT)
    d.rectangle([W // 2, 0, W, 6], fill=MINT)

    f_brand = sg_font(32, "Medium")
    f_title = sg_font(84, "Bold")
    f_sub = sg_font(38, "Medium")
    f_tag = sg_font(30, "Bold")
    f_small = sg_font(24, "Regular")

    d.text((80, 64), "XION'S MICRO TOOLS", font=f_brand, fill=MUTED)

    y = 200
    for ln in wrap(d, title, f_title, W - 160):
        d.text((80, y), ln, font=f_title, fill=INK)
        y += 96
    y += 14
    for ln in wrap(d, subtitle, f_sub, W - 160):
        d.text((80, y), ln, font=f_sub, fill=MUTED)
        y += 50

    # bottom tagline
    d.rectangle([80, H - 120, 220, H - 117], fill=ACCENT)
    d.text((80, H - 96), "cryptopay · BTC / ETH / SOL", font=f_tag, fill=ACCENT)
    d.text((80, H - 52), "coins no company can freeze", font=f_small, fill=MUTED)

    out = OUT / f"{name}.png"
    img.save(out, "PNG", optimize=True)
    print(f"ok {out.relative_to(ROOT)} ({out.stat().st_size} bytes)")


for name, spec in IMAGES.items():
    gen(name, spec["title"], spec["subtitle"])
print("all OG images generated")
