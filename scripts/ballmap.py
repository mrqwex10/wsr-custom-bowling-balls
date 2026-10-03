"""Shared helpers for building Wii Sports Resort bowling-ball textures.

Ball UV layout (measured from bwg_ball_*_pro MDL0):
    v = 0.5 - lat/180            (Y axis = poles, v=0 at +Y)
    u = (270 - lon)/360          lon = atan2(z, x)
so u=0.5 is the +Z "front" of the ball and u increases toward +X (viewer's right).
"""
import numpy as np
from PIL import Image, ImageFilter


def directions(w, h):
    """Unit direction for the centre of every texel of a w*h equirect texture."""
    u = (np.arange(w) + 0.5) / w
    v = (np.arange(h) + 0.5) / h
    uu, vv = np.meshgrid(u, v)
    lat = np.radians((0.5 - vv) * 180.0)
    lon = np.radians(270.0 - uu * 360.0)
    x = np.cos(lat) * np.cos(lon)
    y = np.sin(lat)
    z = np.cos(lat) * np.sin(lon)
    return np.stack([x, y, z], -1)


def bilinear(img, px, py):
    """Sample float image (H,W,C) at float pixel coords with edge clamping."""
    h, w = img.shape[:2]
    px = np.clip(px, 0, w - 1.001)
    py = np.clip(py, 0, h - 1.001)
    x0, y0 = np.floor(px).astype(int), np.floor(py).astype(int)
    fx, fy = (px - x0)[..., None], (py - y0)[..., None]
    a, b = img[y0, x0], img[y0, x0 + 1]
    c, d = img[y0 + 1, x0], img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fit_circle(rgba, white_thresh=235):
    """Find the ball disc in a product photo. Ignores the drop shadow below."""
    rgb, al = rgba[..., :3], rgba[..., 3]
    m = (al > 200) & (rgb.min(-1) < white_thresh)
    ys, xs = np.nonzero(m)
    top = ys.min()
    # rough radius from widest row, then least-squares fit on the upper 3/4 of the edge
    pts = []
    for y in range(top, ys.max()):
        row = np.nonzero(m[y])[0]
        if len(row) > 4:
            pts += [(row.min(), y), (row.max(), y)]
    pts = np.array(pts, float)
    r0 = (pts[:, 0].max() - pts[:, 0].min()) / 2
    pts = pts[pts[:, 1] < top + 1.6 * r0]  # skip the shadow-contaminated bottom
    A = np.c_[2 * pts[:, 0], 2 * pts[:, 1], np.ones(len(pts))]
    bvec = (pts ** 2).sum(1)
    cx, cy, c = np.linalg.lstsq(A, bvec, rcond=None)[0]
    return cx, cy, np.sqrt(c + cx * cx + cy * cy)


def flatten_lighting(img, cx, cy, R, strength=0.85, inner=0.0):
    """Remove the studio fall-off baked into a product photo.

    Measures the median brightness in thin rings around the disc centre and
    rescales each ring toward the brightness of the central region, so the
    game's own lighting is the only shading left on the ball."""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.hypot(xx - cx, yy - cy) / R
    lum = img[..., :3] @ np.array([0.299, 0.587, 0.114])
    edges = np.linspace(0, 1, 41)
    centers, meds = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        sel = (rr >= a) & (rr < b)
        if sel.sum() > 20:
            centers.append((a + b) / 2)
            meds.append(np.median(lum[sel]))
    centers, meds = np.array(centers), np.array(meds)
    ref = np.median(lum[rr < 0.5])
    # smooth the profile so it only follows lighting, not artwork
    k = np.ones(5) / 5
    sm = np.convolve(np.pad(meds, 2, mode='edge'), k, mode='valid')
    gain = (ref / np.maximum(sm, 1e-3)) ** strength
    gain = np.clip(gain, 0.6, 2.2)
    g = np.interp(rr, centers, gain)[..., None]
    out = img.copy()
    out[..., :3] = np.clip(img[..., :3] * g, 0, 1)
    return out


def photo_to_equirect(photo, cx, cy, R, w, h, shrink=0.92, eq_mix=0.45, back='mirror', back_blend=(0.35, 0.75)):
    """Wrap a front-view photo of a ball around the whole sphere.

    Front hemisphere: radial projection of the disc, using a mix of orthographic
    (true look from the front) and equidistant (less stretching near the rim).
    `shrink` keeps us away from the photo's dark/glossy outer edge, which is
    where ugly outlines come from.
    back='mirror'   -> back hemisphere is the reflection through the limb plane
                       (perfectly seamless, fine for abstract/marbled balls)
    back='readable' -> back centre shows a right-reading copy so text/pictures
                       aren't mirrored, blended into the mirror near the limb."""
    d = directions(w, h)
    x, y, z = d[..., 0], d[..., 1], d[..., 2]
    Rs = shrink * R

    def project(xs, ys, zs):
        th = np.arccos(np.clip(np.abs(zs), -1, 1))  # angle from view axis (0..pi/2)
        s = np.hypot(xs, ys)
        s = np.where(s < 1e-9, 1e-9, s)
        r_ortho = np.sin(th)
        r_eq = th / (np.pi / 2)
        r = (1 - eq_mix) * r_ortho + eq_mix * r_eq
        return cx + Rs * r * xs / s, cy - Rs * r * ys / s

    px, py = project(x, y, z)
    out = bilinear(photo, px, py)
    if back == 'readable':
        # viewed from behind the ball, screen-right is -X
        qx, qy = project(-x, y, z)
        alt = bilinear(photo, qx, qy)
        depth = np.clip(-z, 0, 1)  # 0 at limb, 1 at back centre
        a, b = back_blend
        t = np.clip((depth - a) / (b - a), 0, 1)
        t = (t * t * (3 - 2 * t))[..., None]
        out = out * (1 - t) + alt * t
    return out


def to_image(arr):
    return Image.fromarray((np.clip(arr[..., :3], 0, 1) * 255 + 0.5).astype(np.uint8), 'RGB')


def render_preview(tex, size=256, rot_y=0.0, rot_x=0.0, env=None, bg=(0.16, 0.16, 0.16)):
    """Very small software renderer: textured, lit sphere for eyeballing seams."""
    t = np.asarray(tex.convert('RGB'), float) / 255
    th, tw = t.shape[:2]
    yy, xx = np.mgrid[0:size, 0:size]
    sx = (xx + 0.5) / size * 2 - 1
    sy = 1 - (yy + 0.5) / size * 2
    rr = sx * sx + sy * sy
    inside = rr < 1
    sz = np.sqrt(np.clip(1 - rr, 0, 1))
    n = np.stack([sx, sy, sz], -1)  # view-space normal, camera on +Z
    # rotate normal into object space
    cyr, syr = np.cos(rot_y), np.sin(rot_y)
    cxr, sxr = np.cos(rot_x), np.sin(rot_x)
    Ry = np.array([[cyr, 0, syr], [0, 1, 0], [-syr, 0, cyr]])
    Rx = np.array([[1, 0, 0], [0, cxr, -sxr], [0, sxr, cxr]])
    o = n @ (Rx @ Ry)
    lat = np.degrees(np.arcsin(np.clip(o[..., 1], -1, 1)))
    lon = np.degrees(np.arctan2(o[..., 2], o[..., 0]))
    u = ((270 - lon) / 360) % 1.0
    v = 0.5 - lat / 180
    col = bilinear(np.concatenate([t, t[:, :1]], 1), u * tw - 0.5 + 0.0, v * th - 0.5)
    L = np.array([-0.4, 0.6, 0.7]); L /= np.linalg.norm(L)
    ndl = np.clip(n @ L, 0, 1)[..., None]
    H = L + np.array([0, 0, 1.0]); H /= np.linalg.norm(H)
    spec = (np.clip(n @ H, 0, 1) ** 60)[..., None] * 0.55
    shade = col * (0.35 + 0.75 * ndl) + spec
    bg = np.zeros_like(shade) + np.array(bg, float)
    a = np.clip((1 - np.sqrt(rr)) * size * 0.5, 0, 1)[..., None]  # AA edge
    img = shade * a + bg * (1 - a)
    return to_image(img)
