"""
Turns a cut-out portrait photo into the ASCII art on the left of both profile cards.

The photo needs a pure white background (like a cut-out from Photos or remove.bg),
which becomes empty space so only the subject is drawn.

    python -m pip install pillow numpy
    python scripts/ascii_portrait.py path/to/photo.png

Rewrites the ascii <text> block in dark_mode.svg and light_mode.svg in place.

Works like Andrew6rant's card: the photo is pushed to near black-and-white, then each
cell gets the character whose glyph shape best matches that patch of the photo, from the
same character sets his cards use. The light card draws dark areas; the dark card is its negative.
"""
import html
import re
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import numpy as np

FONT_PX, LINE_PX = 16, 20  # same glyph size as the info text, on 20px rows
COLS, ROWS = 43, 25        # 413 x 500 px, from the card's left edge to just before the info column
LEFT, TOP = 15, 15
CROP_BOTTOM = 820          # photo row (px) to end the crop at, just below the collar
CONTRAST = 16              # steepness of the curve that pushes the photo toward black and white
FLATTEN_LIGHTING = 0.9     # 0-1, evens out broad shadows (e.g. one side of the face)
DARK_CHARS = '!"#%\'*,./:;=@HLMNW[\\]^`bdghijklmnprwxy{|}~'
LIGHT_CHARS = '!"#$%&\'*+,-.;=@BFLMTW]`gklrwy|}~'
GLYPH_FONT = '/System/Library/Fonts/Menlo.ttc'  # any monospace .ttf/.ttc works; only used to measure glyph shapes
CARDS = ['dark_mode.svg', 'light_mode.svg']

GW, GH = 12, 25            # glyph bitmap size, same 0.48 aspect as a 16px glyph on a 20px row


def blur(a, radius):
    return np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius))).astype(float)


def glyph_bank(charset):
    """
    Returns the characters (space first), their blurred glyph bitmaps flattened, and the densest glyph's ink
    """
    font = ImageFont.truetype(GLYPH_FONT, 20)
    ascent, descent = font.getmetrics()
    chars = [' '] + sorted(set(charset))
    bitmaps = []
    for ch in chars:
        im = Image.new('L', (GW, GH), 0)
        if ch != ' ':
            ImageDraw.Draw(im).text((0, (GH - ascent - descent) // 2 + 1), ch, fill=255, font=font)
        bitmaps.append(np.asarray(im).astype(float))
    top_ink = max(b.mean() for b in bitmaps) / 255
    bank = np.stack([blur(b, 1) / 255 for b in bitmaps]).reshape(len(chars), -1)
    return chars, bank, top_ink


def to_ascii(path):
    """
    Returns (dark_lines, light_lines) for the photo at path
    """
    full = Image.open(path).convert('RGB')
    top = int(np.argmax((np.asarray(full).min(2) < 250).sum(1) > 20)) - 4  # start right at the top of the hair
    height = CROP_BOTTOM - top
    width = int(height * COLS * 0.6 * FONT_PX / (ROWS * LINE_PX))
    center = full.width // 2 + 10
    im = full.crop((center - width // 2, top, center + width // 2, top + height))

    # white background, plus the white fringe a cut-out leaves behind
    background = (np.asarray(im).min(2) >= 250) | (np.asarray(im.convert('L')) >= 225)
    g = np.asarray(im.convert('L')).astype(float)
    lighting = blur(np.where(background, g[~background].mean(), g), 60)
    g = np.clip(g - FLATTEN_LIGHTING * (lighting - lighting[~background].mean()), 0, 255)
    lo, hi = np.percentile(g[~background], 3), np.percentile(g[~background], 97)
    bright = np.where(background, 1.0, np.clip((g - lo) / (hi - lo), 0, 1))

    # near black-and-white, split at the subject's median brightness
    mid = np.median(bright[~background])
    curve = lambda x: 1 / (1 + np.exp(-CONTRAST * (x - mid)))
    contrast = np.clip((curve(bright) - curve(0)) / (curve(1) - curve(0)), 0, 1)

    def render(ink, charset):
        chars, bank, top_ink = glyph_bank(charset)
        ink = blur(np.where(background, 0, ink) * 255, 1) / 255
        cells = np.asarray(Image.fromarray((np.clip(ink, 0, 1) * 255).astype(np.uint8))
                           .resize((COLS * GW, ROWS * GH), Image.BOX)).astype(float) / 255
        cells = cells.reshape(ROWS, GH, COLS, GW).transpose(0, 2, 1, 3).reshape(ROWS, COLS, -1)
        cells *= top_ink * 1.3  # a fully inked cell should match the densest glyph
        return [''.join(chars[int(np.argmin(((bank - cells[r, c]) ** 2).sum(1)))] for c in range(COLS))
                for r in range(ROWS)]

    return render(contrast, DARK_CHARS), render(1 - contrast, LIGHT_CHARS)


def write_card(filename, lines):
    """
    Replaces the ascii <text> block in an SVG card
    """
    with open(filename, encoding='utf-8') as f:
        svg = f.read()
    tspans = '\n'.join(f'<tspan x="{LEFT}" y="{TOP + FONT_PX - 2 + i * LINE_PX}">{html.escape(line, quote=False)}</tspan>'
                       for i, line in enumerate(lines))
    svg, count = re.subn(
        r'<text x="15" y="30" (fill="[^"]+") class="ascii"( font-size="[^"]+")?>\n.*?\n</text>',
        lambda m: f'<text x="15" y="30" {m.group(1)} class="ascii" font-size="{FONT_PX}px">\n{tspans}\n</text>',
        svg, flags=re.S)
    if count != 1:
        raise Exception('Could not find the ascii <text> block in ' + filename)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(svg)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    dark, light = to_ascii(sys.argv[1])
    write_card(CARDS[0], dark)
    write_card(CARDS[1], light)
    print(f'Wrote {COLS}x{ROWS} portrait to {", ".join(CARDS)}')
