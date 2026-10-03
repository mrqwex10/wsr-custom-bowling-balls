"""Animated holographic ball: a seamless loop of frames.

Looping trick: every time-varying input moves around a closed circle (or a
whole number of palette cycles), so the last frame flows straight into the first.
Writes designs/holo_anim/fNN.png at 256x128 + fNN.mmK.png mip levels."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
from ballmap import directions, to_image
from noise3d import fbm, smoothstep
from make_holo import palette

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'designs/holo_anim')
W, H = 256, 128
SS = 3              # supersample factor for the base level
N_MIPS = 4          # 128x64 .. 16x8


def loop(theta, radius, k=1):
    return radius * np.array([np.cos(k * theta), np.sin(k * theta), 0.5 * np.sin(k * theta)])


def frame(d, t):
    th = 2 * np.pi * t
    q = d * 0.75
    warp = np.stack([fbm(q * 0.7 + loop(th, 0.055) + s * 3.1, 3, seed=s) for s in (101, 131, 151)], -1)
    w = q + 1.5 * warp
    warp2 = np.stack([fbm(w * 1.3 + loop(th + s, 0.07), 2, seed=s) for s in (171, 181, 191)], -1)
    w2 = w + 0.35 * warp2
    h = fbm(w2, 3, gain=0.45, seed=211)
    # ripples travelling across the liquid surface (one wave per loop)
    ripple = 0.09 * np.sin(2 * np.pi * (5.0 * h - t))
    phase = h * 1.6 + 0.35 * fbm(w2 * 0.6, 2, seed=223) + ripple
    n = fbm(w2 * 1.1 + 3.0 + loop(th, 0.05), 3, gain=0.5, seed=233)
    ridge = (1 - np.clip(np.abs(n + 0.06 * np.sin(2 * np.pi * (4 * h - t))) * 5.0, 0, 1)) ** 4
    deep = smoothstep(0.05, 0.4, fbm(w * 0.9 - 4.0, 3, seed=241))
    col = palette(phase)
    sheen = palette(phase + 0.33) * 0.35 + 0.65
    col = col * (1 - 0.75 * ridge[..., None]) + sheen * 0.75 * ridge[..., None]
    k = (0.6 * deep * (1 - ridge))[..., None]
    col = col * (1 - k) + np.array([52, 20, 128]) / 255 * k
    return np.clip(col, 0, 1)


def main(n_frames=20, out=OUT):
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        os.remove(os.path.join(out, f))
    d = directions(W * SS, H * SS)
    for i in range(n_frames):
        col = frame(d, i / n_frames)
        big = to_image(col)
        big.resize((W, H), Image.LANCZOS).save(os.path.join(out, f'f{i:02d}.png'))
        for m in range(1, N_MIPS + 1):
            big.resize((W >> m, H >> m), Image.LANCZOS).save(os.path.join(out, f'f{i:02d}.mm{m}.png'))
        print('frame', i)


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    main(n, os.path.join(ROOT, sys.argv[2]) if len(sys.argv) > 2 else OUT)
