"""README / GameBanana preview images for the alleys, made from work/verify_alley
(renders of the decoded release files)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image, ImageDraw, ImageFont
import alley_render as R
import build_alley as BA

ROOT = R.ROOT
V = os.path.join(ROOT, 'work/verify_alley')
FONT = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'


def label(im, text, size=26):
    im = im.convert('RGB')
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, size)
    d.text((18, im.height - 18), text, font=f, anchor='ls', fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
    return im


def frames(gif):
    g = Image.open(gif)
    out = []
    for k in range(g.n_frames):
        g.seek(k)
        out.append(g.convert('RGB'))
    return out


def main(out_dirs):
    names = {t: l for t, l, _ in BA.THEMES}
    reel = []
    for t in names:
        fr = frames(os.path.join(V, f'{t}_throw.gif'))
        reel += [label(f.resize((560, 315), Image.LANCZOS), names[t], 21) for f in fr]
    stock = R.render({}, cam=R.CAM_PINS, W=1440, H=810).resize((720, 405), Image.LANCZOS)
    tiles = [label(Image.open(os.path.join(V, f'{t}_pins.png')), names[t]) for t in names] + [label(stock, 'Stock (for comparison)')]
    grid = Image.new('RGB', (720 * 3 + 16, 405 * 2 + 8), (18, 16, 24))
    for i, im in enumerate(tiles):
        grid.paste(im, ((i % 3) * 728, (i // 3) * 413))
    for d in out_dirs:
        os.makedirs(d, exist_ok=True)
        pal = [f.quantize(colors=160, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in reel]
        pal[0].save(os.path.join(d, 'alleys.gif'), save_all=True, append_images=pal[1:], duration=190, loop=0, optimize=True)
        grid.convert('RGB').save(os.path.join(d, 'alleys_grid.jpg'), quality=88)
        print(d, 'alleys.gif', len(reel), 'frames;', 'alleys_grid.jpg')


if __name__ == '__main__':
    main(sys.argv[1:] or [os.path.join(ROOT, 'release/previews')])
