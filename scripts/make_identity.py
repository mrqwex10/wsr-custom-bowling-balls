"""Storm IDENTITY: procedural teal/red/black solid coverstock + logo from the photo.

Output: designs/identity.png (equirect, 1024x512 master; the build step
downsamples it to the in-game size)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, binary_dilation, grey_dilation
from ballmap import directions, bilinear, fit_circle, to_image
from noise3d import fbm, smoothstep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1024, 512

# Palette measured from the product photo (k-means on the ball face)
RED = np.array([202, 28, 51]) / 255
RED_DK = np.array([150, 22, 40]) / 255
TEAL = np.array([16, 150, 120]) / 255
TEAL_DK = np.array([30, 100, 86]) / 255
BLACK = np.array([16, 13, 18]) / 255
SMOKE = np.array([70, 38, 46]) / 255


def coverstock(d):
    # domain-warped noise gives the stretched, swirled look of a solid reactive
    q = d * 0.95
    warp = np.stack([fbm(q * 0.9, 3, seed=s) for s in (11, 23, 37)], -1)
    w = q + 1.1 * warp
    # second, finer warp gives the streaky "poured" swirl look
    warp2 = np.stack([fbm(w * 2.2, 3, seed=s) for s in (41, 53, 67)], -1)
    w2 = w + 0.25 * warp2
    region = fbm(w2, 3, gain=0.45, seed=3)         # teal vs red, big soft blobs
    smoke = fbm(w2 * 1.6 + 5.0, 4, gain=0.5, seed=9)  # dark smoky clouds
    tone = fbm(w2 * 2.6 - 2.0, 3, seed=21)         # light/dark variation inside each colour
    s = smoothstep(-0.09, 0.09, region + 0.02)[..., None]
    tt = smoothstep(-0.35, 0.45, tone)[..., None]
    teal = TEAL * (1 - tt) + TEAL_DK * tt
    tr = smoothstep(-0.25, 0.5, tone)[..., None]
    red = RED * (1 - tr) + RED_DK * tr
    col = teal * (1 - s) + red * s
    # soft black seams where the two colours meet
    vein = np.exp(-(region / 0.13) ** 2)[..., None]
    col = col * (1 - 0.8 * vein) + BLACK * 0.8 * vein
    # large smoky black areas with soft, feathered edges
    k = smoothstep(0.02, 0.38, smoke)[..., None]
    col = col * (1 - 0.92 * k) + (BLACK * 0.75 + SMOKE * 0.25) * 0.92 * k
    return col


if __name__ == '__main__':
    main()
