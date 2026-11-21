#!/usr/bin/env python3
"""Generate the 512x512 app icon used by software directories (AlternativeTo, etc.).

The OG image is 1200x630 with text; center-cropping it cuts words in half. This
draws a purpose-built square mark instead: receipt + QR + coin, store palette.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 512
BG_TOP = (16, 26, 46)
BG_BOT = (7, 10, 18)
INK = (15, 23, 42)
PAPER = (248, 250, 252)
MUTED = (203, 213, 225)
TEAL = (45, 212, 191)
TEAL_DARK = (5, 46, 43)
TEAL_DEEP = (15, 118, 110)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rounded(draw, box, r, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)


def main(out="site/og/crypto-invoice-icon.png"):
    img = Image.new("RGB", (S, S), BG_BOT)
    d = ImageDraw.Draw(img)

    # vertical gradient
    for y in range(S):
        d.line([(0, y), (S, y)], fill=lerp(BG_TOP, BG_BOT, y / (S - 1)))

    # soft teal glow behind the mark
    glow = Image.new("RGB", (S, S), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((96, 40, 416, 360), fill=(16, 78, 74))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.blend(img, Image.blend(img, glow, 0.55), 0.55)
    d = ImageDraw.Draw(img)

    # shadow under the sheet
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((134, 100, 378, 372), radius=30, fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    img.paste(Image.alpha_composite(img.convert("RGBA"), sh).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)

    # receipt: rounded top, zig-zag torn bottom
    sheet = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheet)
    sd.rounded_rectangle((128, 84, 384, 356), radius=30, fill=PAPER)
    left, right, base, peak, teeth = 128, 384, 382, 362, 6
    pts = [(left, 340)]
    step = (right - left) / teeth
    pts.append((left, base))
    for i in range(teeth):
        pts.append((round(left + step * (i + 0.5)), peak))
        pts.append((round(left + step * (i + 1)), base))
    pts.append((right, 340))
    sd.polygon(pts, fill=PAPER)
    img.paste(Image.alpha_composite(img.convert("RGBA"), sheet).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)

    # header rule
    rounded(d, (156, 118, 300, 136), 9, INK)
    rounded(d, (312, 118, 356, 136), 9, TEAL_DEEP)

    # copy lines (left)
    for i, w in enumerate((96, 76, 60)):
        rounded(d, (156, 166 + i * 30, 156 + w, 180 + i * 30), 7, MUTED)

    # QR block (right)
    qx, qy, qs = 268, 158, 88
    rounded(d, (qx - 8, qy - 8, qx + qs + 8, qy + qs + 8), 10, (226, 232, 240))
    rounded(d, (qx, qy, qx + qs, qy + qs), 6, PAPER)
    cell = qs / 9
    # three finder squares + noise modules
    for fx, fy in ((0, 0), (6, 0), (0, 6)):
        x0, y0 = qx + fx * cell, qy + fy * cell
        d.rectangle((x0, y0, x0 + 3 * cell, y0 + 3 * cell), fill=INK)
        d.rectangle((x0 + cell, y0 + cell, x0 + 2 * cell, y0 + 2 * cell), fill=PAPER)
        d.rectangle((x0 + 2 * cell, y0 + 2 * cell, x0 + 2.6 * cell, y0 + 2.6 * cell), fill=INK)
    for cx, cy in ((4, 1), (5, 3), (4, 4), (6, 4), (8, 2), (7, 6), (4, 7), (5, 8), (8, 8), (6, 7)):
        d.rectangle((qx + cx * cell, qy + cy * cell, qx + (cx + 1) * cell, qy + (cy + 1) * cell), fill=INK)

    # divider + total row
    d.line((156, 268, 356, 268), fill=(203, 213, 225), width=4)
    rounded(d, (156, 288, 244, 304), 8, MUTED)
    rounded(d, (276, 284, 356, 308), 12, TEAL_DEEP)

    # coin: bold B plus the two strokes that turn it into the bitcoin mark
    # (DejaVu's U+20BF glyph renders as tofu, so build it from a B instead)
    cx, cy, r = 388, 388, 74
    d.ellipse((cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6), fill=BG_BOT)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=TEAL)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 112)
    bb = d.textbbox((0, 0), "B", font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    tx, ty = cx - tw / 2 - bb[0], cy - th / 2 - bb[1] - 2
    d.text((tx, ty), "B", font=font, fill=TEAL_DARK)
    stroke = max(7, round(th * 0.075))
    off = round(tw * 0.20)
    top, bot = ty + bb[1] - 12, ty + bb[3] + 12
    for sx in (tx + bb[0] + tw / 2 - off, tx + bb[0] + tw / 2 + off):
        d.rounded_rectangle((sx - stroke / 2, top, sx + stroke / 2, bot), radius=stroke / 2, fill=TEAL_DARK)

    img.save(out, optimize=True)
    print("wrote", out, img.size)


if __name__ == "__main__":
    import sys

    main(*sys.argv[1:])
