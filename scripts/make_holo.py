"""Holographic liquid-chrome ball with a mipmap colour-shift "animation".

The Wii GPU picks a smaller mipmap the further away / more edge-on the ball is.
Each mip level here is the same swirl with the colours slid further along a
cyclic holographic palette, so as the ball rolls down the lane (and at its
curved rim) the colours keep flowing. No code patch needed.

Writes designs/holo.png (+ holo.mm1.png ... for wimgt) at the in-game size."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
from ballmap import directions, to_image
from noise3d import fbm, smoothstep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 512, 256
N_MIPS = 5          # extra levels: 256x128 ... 16x8
SHIFT_PER_MIP = 0.22  # palette slide per level (1.0 = full cycle)

# cyclic palette sampled from the reference: violet -> pink -> lilac -> cyan -> mint -> lilac -> violet
STOPS = np.array([
    [88, 34, 196],
    [178, 70, 230],
    [246, 118, 214],
    [214, 168, 255],
    [124, 226, 255],
    [158, 255, 214],
    [196, 186, 255],
    [120, 60, 220],
], float) / 255


def palette(t):
    t = np.mod(t, 1.0) * len(STOPS)
    i = np.floor(t).astype(int) % len(STOPS)
    f = t - np.floor(t)
    f = f * f * (3 - 2 * f)
    a, b = STOPS[i], STOPS[(i + 1) % len(STOPS)]
    return a * (1 - f[..., None]) + b * f[..., None]


def fields(d):
    """Shared swirl geometry: phase (which colour), ridge (bright streaks), deep (dark violet)."""
    q = d * 0.75
    warp = np.stack([fbm(q * 0.7, 3, seed=s) for s in (101, 131, 151)], -1)
    w = q + 1.5 * warp
    warp2 = np.stack([fbm(w * 1.3, 2, seed=s) for s in (171, 181, 191)], -1)
    w2 = w + 0.35 * warp2
    h = fbm(w2, 3, gain=0.45, seed=211)
    phase = h * 1.6 + 0.35 * fbm(w2 * 0.6, 2, seed=223)
    # liquid-chrome ridges: thin bright lines where the warped field folds
    n = fbm(w2 * 1.1 + 3.0, 3, gain=0.5, seed=233)
    ridge = (1 - np.clip(np.abs(n) * 5.0, 0, 1)) ** 4
    deep = smoothstep(0.05, 0.4, fbm(w * 0.9 - 4.0, 3, seed=241))
    return phase, ridge, deep


def shade(phase, ridge, deep, shift):
    col = palette(phase + shift)
    # pastel sheen on the ridges, like light catching folds in foil
    sheen = palette(phase + shift + 0.33) * 0.35 + 0.65
    col = col * (1 - 0.75 * ridge[..., None]) + sheen * 0.75 * ridge[..., None]
    # deep violet pools give it depth (kept off the ridges)
    k = (0.6 * deep * (1 - ridge))[..., None]
    col = col * (1 - k) + np.array([52, 20, 128]) / 255 * k
    return np.clip(col, 0, 1)


def render_level(w, h, shift, ss=4):
    """Supersampled so each mip is a true filtered image (no aliasing)."""
    d = directions(w * ss, h * ss)
    col = shade(*fields(d), shift)
    col = col.reshape(h, ss, w, ss, 3).mean((1, 3))
    # small mips average toward grey-lilac; push contrast/saturation back up so
    # the far-away ball stays vivid
    level = int(round(np.log2(W / w)))
    if level:
        k = 1 + 0.22 * level
        mean = col.mean((0, 1), keepdims=True)
        lum = col.mean(-1, keepdims=True)
        col = mean + (col - mean) * k
        col = lum + (col - lum) * (1 + 0.15 * level)
    return np.clip(col, 0, 1)


def main():
    out = os.path.join(ROOT, 'designs')
    os.makedirs(out, exist_ok=True)
    # remove stale mip files
    for f in os.listdir(out):
        if f.startswith('holo.mm'):
            os.remove(os.path.join(out, f))
    to_image(render_level(W, H, 0.0, ss=3)).save(os.path.join(out, 'holo.png'))
    for m in range(1, N_MIPS + 1):
        w, h = W >> m, H >> m
        ss = min(16, 3 << m)
        to_image(render_level(w, h, SHIFT_PER_MIP * m, ss)).save(os.path.join(out, f'holo.mm{m}.png'))


if __name__ == '__main__':
    main()
