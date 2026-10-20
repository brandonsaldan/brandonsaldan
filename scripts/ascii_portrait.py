"""
Turns a cut-out portrait photo into the ASCII art on the left of both profile cards.

The photo needs a pure white background (like a cut-out from Photos or remove.bg),
which becomes empty space so only the subject is drawn.

    python -m pip install pillow numpy lxml
    python scripts/ascii_portrait.py path/to/photo.png

Rewrites the ascii <text> block in dark_mode.svg and light_mode.svg in place.
The light card draws dark areas densely; the dark card is its negative.
"""
import re
import sys
from PIL import Image, ImageFilter
import numpy as np

FONT_PX = 9                # art font size; line height matches it
RAMP = ' .:-=+#'           # sparse -> dense
BLUR_PX = 2                # softens the outline and skin texture
CONTRAST_PERCENT = 70      # gentle local contrast so the eyes and mouth still read
FLATTEN_LIGHTING = 0.8     # 0-1, evens out broad shadows (e.g. one side of the face) so features stand out
ART_WIDTH, ART_HEIGHT = 420, 500  # space left of the info column, in px
CARDS = ['dark_mode.svg', 'light_mode.svg']


def to_ascii(path):
    """
    Returns (dark_lines, light_lines) for the photo at path
    """
    cell_w, line_h = 0.6 * FONT_PX, FONT_PX  # monospace cells are 0.6em wide
    cols, rows = int(ART_WIDTH // cell_w), int(ART_HEIGHT // line_h)

    full = Image.open(path).convert('RGB')
    foreground_rows = (np.asarray(full).min(2) < 250).sum(1)
    top = int(np.argmax(foreground_rows > 20)) - 4  # start right at the top of the hair
    height = full.height - top
    width = int(height * cols * cell_w / (rows * line_h))
    center = full.width // 2
    im = full.crop((center - width // 2, top, center + width // 2, top + height))

    background = np.asarray(im).min(2) >= 250
    halo = (np.asarray(im.convert('L')) >= 225) & ~background  # white fringe left by the cut-out
    gray = im.convert('L').filter(ImageFilter.GaussianBlur(BLUR_PX))
    if FLATTEN_LIGHTING:
        # subtract the broad lighting, estimated with the background filled in so edges don't skew it
        g = np.asarray(gray).astype(float)
        filled = np.where(background, g[~background].mean(), g)
        lighting = np.asarray(Image.fromarray(filled.astype(np.uint8)).filter(ImageFilter.GaussianBlur(60))).astype(float)
        g = np.clip(g - FLATTEN_LIGHTING * (lighting - lighting[~background].mean()), 0, 255)
        gray = Image.fromarray(g.astype(np.uint8))
    gray = gray.filter(ImageFilter.UnsharpMask(radius=40, percent=CONTRAST_PERCENT, threshold=0))
    g = np.asarray(gray).astype(float)

    h, w = g.shape
    lum = np.full((rows, cols), 255.0)
    bg_fraction = np.ones((rows, cols))
    for r in range(rows):
        for c in range(cols):
            ys = slice(r * h // rows, (r + 1) * h // rows)
            xs = slice(c * w // cols, (c + 1) * w // cols)
            bg_fraction[r, c] = background[ys, xs].mean()
            mask = ~background[ys, xs] & ~halo[ys, xs]
            if mask.any():
                lum[r, c] = g[ys, xs][mask].mean()

    subject = bg_fraction < 0.5
    padded = np.pad(subject, 1)
    neighbours = sum(np.roll(np.roll(padded, dy, 0), dx, 1)
                     for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)[1:-1, 1:-1]
    subject &= neighbours >= 3  # drop stray single cells

    # rank-based equalization so each character covers a similar share of the subject
    values = np.sort(lum[subject])
    rank = np.clip(np.searchsorted(values, lum, side='right') / len(values) - 1e-9, 0, 1)

    def render(dense_when_bright):
        lines = []
        for r in range(rows):
            row = ''
            for c in range(cols):
                if not subject[r, c]:
                    row += ' '
                elif bg_fraction[r, c] > 0.25:
                    row += '.'  # soft outline
                else:
                    t = rank[r, c] if dense_when_bright else 1 - rank[r, c]
                    row += RAMP[min(len(RAMP) - 1, int(t * len(RAMP)))]
            lines.append(row)
        return lines

    return render(True), render(False)


def write_card(filename, lines):
    """
    Replaces the ascii <text> block in an SVG card, vertically centred in the card
    """
    with open(filename, encoding='utf-8') as f:
        svg = f.read()
    top = 15 + FONT_PX + (ART_HEIGHT - FONT_PX * len(lines)) // 2
    tspans = '\n'.join(f'<tspan x="15" y="{top + i * FONT_PX}">{line}</tspan>' for i, line in enumerate(lines))
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
    print(f'Wrote {len(dark[0])}x{len(dark)} portrait to {", ".join(CARDS)}')
