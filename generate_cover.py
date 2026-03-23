#!/usr/bin/env python3
"""Generate podcast cover art: white text on black background."""

from PIL import Image, ImageDraw, ImageFont

WIDTH = 3000
HEIGHT = 3000


def generate_cover():
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)

    # Serif fonts for a newspaper feel, with fallbacks
    font_size = 460
    small_font_size = 300
    serif_fonts = [
        "/Library/Fonts/Times.ttc",
        "/System/Library/Fonts/Times.ttc",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ]
    font = small_font = None
    for path in serif_fonts:
        try:
            font = ImageFont.truetype(path, font_size)
            small_font = ImageFont.truetype(path, small_font_size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()
        small_font = font

    # Draw "NICAR" centered
    bbox1 = draw.textbbox((0, 0), "NICAR", font=font)
    w1 = bbox1[2] - bbox1[0]
    x1 = (WIDTH - w1) // 2
    y1 = HEIGHT // 2 - 380

    # Draw "Sessions" centered below
    bbox2 = draw.textbbox((0, 0), "Sessions", font=small_font)
    w2 = bbox2[2] - bbox2[0]
    x2 = (WIDTH - w2) // 2
    y2 = y1 + 480

    draw.text((x1, y1), "NICAR", fill="white", font=font)
    draw.text((x2, y2), "Sessions", fill="white", font=small_font)

    output = "docs/cover.png"
    img.save(output, "PNG")
    print(f"Cover art written to {output} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    generate_cover()
