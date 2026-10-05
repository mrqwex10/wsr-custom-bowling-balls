"""v2.0 banner: title, alley thumbnails (from work/verify_alley) and the ball row of the v1 banner."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import build_alley as BA

ROOT = BA.ROOT
BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
W, H = 1280, 600
BG = (16, 13, 24)


def rounded(im, r):
    m = Image.new('L', im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), r, fill=255)
    out = Image.new('RGBA', im.size)
    out.paste(im.convert('RGB'), (0, 0), m)
    return out


def main(out):
    c = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(c)
    f = lambda s: ImageFont.truetype(BOLD, s)
    d.text((W / 2, 62), 'WSR Custom Bowling Balls', font=f(62), anchor='mm', fill=(255, 241, 214))
    d.text((W / 2, 122), 'New balls, animated alleys and a ball trail for Wii Sports Resort', font=f(28), anchor='mm', fill=(225, 220, 255))
    d.text((W / 2, 158), '5 alley themes  •  6 animated Pro orbs  •  Gold & Prismatic Diamond  •  8 random designs',
           font=f(19), anchor='mm', fill=(170, 165, 195))
    tw, th, gap = 232, 131, 14
    x0 = (W - (5 * tw + 4 * gap)) // 2
    for i, (t, label, _) in enumerate(BA.THEMES):
        im = Image.open(os.path.join(ROOT, 'work/verify_alley', f'{t}_pins.png')).convert('RGB')
        im = im.crop((60, 0, 660, 338)).resize((tw, th), Image.LANCZOS)
        x = x0 + i * (tw + gap)
        c.paste(rounded(im, 10), (x, 190), rounded(im, 10))
        d.text((x + tw / 2, 190 + th + 18), label, font=f(16), anchor='mm', fill=(205, 200, 225))
    old = Image.open(os.path.join(ROOT, 'release/previews/banner_v1.png')).convert('RGB')
    row = old.crop((40, 185, 1250, 425))
    row = row.resize((int(row.width * 0.66), int(row.height * 0.66)), Image.LANCZOS)
    c.paste(row, ((W - row.width) // 2, 372))
    d.text((W / 2, 568), 'Wii Sports Resort (USA)  •  Riivolution / Friivolution', font=f(22), anchor='mm', fill=(150, 145, 175))
    c.save(out)
    print(out)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'release/previews/banner.png'))
