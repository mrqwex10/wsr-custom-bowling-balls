"""Random-pool designs for non-Pro players. Each writes designs/pool/<name>.png
(1024x512 equirect master). All patterns are evaluated on 3D sphere
directions, so nothing has a seam or pinched poles."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ballmap import directions, bilinear, to_image
from noise3d import fbm, smoothstep, perlin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'designs/pool')
W, H = 1024, 512
C = lambda *rgb: np.array(rgb, float) / 255


def mix(a, b, t):
    t = np.asarray(t)[..., None] if np.ndim(t) else t
    return a * (1 - t) + b * t


def sphere_points(n, seed):
    r = np.random.default_rng(seed)
    p = r.normal(size=(n, 3))
    return p / np.linalg.norm(p, axis=1, keepdims=True)


def voronoi(d, pts, warp=0.0, seed=0):
    """Distance to nearest and 2nd-nearest feature point (great-circle-ish)."""
    q = d
    if warp:
        q = d + warp * np.stack([fbm(d * 2.0, 3, seed=seed + s) for s in (1, 2, 3)], -1)
        q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    dots = q.reshape(-1, 3) @ pts.T
    dist = np.sqrt(np.clip(2 - 2 * dots, 0, None))
    part = np.partition(dist, 1, axis=1)
    return part[:, 0].reshape(d.shape[:2]), part[:, 1].reshape(d.shape[:2])


def decal(col, d, front, img_rgba, ang_radius_deg, up=(0, 1, 0)):
    """Paste an RGBA image as a round-ish decal centred on `front`."""
    f = np.array(front, float); f /= np.linalg.norm(f)
    u = np.array(up, float)
    r = np.cross(u, f); r /= np.linalg.norm(r)
    u = np.cross(f, r)
    x, y, z = d @ r, d @ u, d @ f
    ang = np.arccos(np.clip(z, -1, 1))
    s = np.hypot(x, y) + 1e-9
    rad = ang / np.radians(ang_radius_deg)          # 0..1 inside the decal
    im = np.asarray(img_rgba, float) / 255
    h, w = im.shape[:2]
    px = (0.5 + 0.5 * rad * x / s) * w - 0.5
    py = (0.5 - 0.5 * rad * y / s) * h - 0.5
    smp = bilinear(im, px, py)
    a = smp[..., 3:4] * (rad < 1.0)[..., None]
    return col * (1 - a) + smp[..., :3] * a


def stars(d, density, seed, size=0.004):
    """Sharp little stars of varying brightness."""
    pts = sphere_points(density, seed)
    dots = d.reshape(-1, 3) @ pts.T
    best = dots.max(1).reshape(d.shape[:2])
    which = dots.argmax(1).reshape(d.shape[:2])
    ang = np.arccos(np.clip(best, -1, 1))
    bright = np.random.default_rng(seed + 1).uniform(0.35, 1.0, density)[which]
    return np.exp(-(ang / size) ** 2) * bright


# ---------------------------------------------------------------- designs
def galaxy(d):
    base = mix(C(8, 6, 24), C(22, 12, 58), smoothstep(-0.4, 0.5, fbm(d * 1.2, 4, seed=5)))
    w = d + 0.6 * np.stack([fbm(d * 1.5, 3, seed=s) for s in (61, 62, 63)], -1)
    neb1 = smoothstep(0.0, 0.55, fbm(w * 1.4, 5, seed=71))
    neb2 = smoothstep(0.05, 0.6, fbm(w * 1.7 + 4, 5, seed=73))
    col = base
    col = col + C(230, 70, 190) * (neb1 ** 1.1)[..., None] * 1.25
    col = col + C(70, 150, 255) * (neb2 ** 1.1)[..., None] * 1.15
    core = smoothstep(0.25, 0.7, fbm(w * 1.4, 5, seed=71)) * smoothstep(0.2, 0.7, fbm(w * 1.7 + 4, 5, seed=73))
    col = col + C(255, 220, 255) * core[..., None] * 0.6
    dust = smoothstep(0.2, 0.55, fbm(w * 3.0 + 9, 4, seed=79))
    col = col * (1 - 0.45 * dust[..., None])
    s = stars(d, 260, 7, 0.011) + 0.7 * stars(d, 700, 9, 0.0075)
    col = col + s[..., None] * C(255, 250, 235)
    return np.clip(col, 0, 1)


def lava(d):
    pts = sphere_points(70, 11)
    d1, d2 = voronoi(d, pts, warp=0.12, seed=31)
    edge = d2 - d1
    crack = np.exp(-(edge / 0.035) ** 2)
    glow = np.exp(-(edge / 0.11) ** 2)
    rock_t = fbm(d * 6.0, 4, seed=37)
    rock = mix(C(22, 14, 12), C(58, 34, 26), smoothstep(-0.4, 0.5, rock_t))
    heat = smoothstep(-0.2, 0.6, fbm(d * 1.5, 3, seed=41))          # some cracks hotter
    col = rock + C(170, 30, 0) * (glow * (0.35 + 0.65 * heat))[..., None] * 0.7
    hot = mix(C(255, 90, 0), C(255, 225, 120), (crack * heat))
    col = mix(col, hot, np.clip(crack * (0.6 + 0.6 * heat), 0, 1))
    return np.clip(col, 0, 1)


def hsv2rgb(h, s, v):
    h = np.mod(h, 1.0) * 6
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r = np.choose(i, [v, q, p, p, t, v]); g = np.choose(i, [t, v, v, q, p, p]); b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], -1)


def tiedye(d):
    # spiral around the front axis, crumpled with noise like real tie-dye folds
    z = d[..., 2]
    ang = np.arctan2(d[..., 1], d[..., 0]) / (2 * np.pi)
    rad = np.arccos(np.clip(z, -1, 1)) / np.pi
    crumple = 0.10 * fbm(d * 3.5, 4, seed=111) + 0.05 * fbm(d * 9, 2, seed=113)
    h = ang * 2 + rad * 3.2 + crumple * 3
    stripe = 0.5 + 0.5 * np.cos(2 * np.pi * (h * 3))
    col = hsv2rgb(h, 0.78 + 0.15 * stripe, 0.92)
    white = smoothstep(0.85, 1.0, stripe) * 0.35
    col = mix(col, C(255, 255, 255), white)
    return np.clip(col, 0, 1)


def main(names=None):
    os.makedirs(OUT, exist_ok=True)
    d = directions(W, H)
    for n in names or POOL:
        col = globals()[n](d)
        to_image(col).save(os.path.join(OUT, f'{n}.png'))
        print('wrote', n)


# ---------------------------------------------------------------- v2 designs


def hyperspin(d):
    """Neon rainbow spiral arms. Spinning blurs each latitude into a glowing
    rainbow ring; slow rolls show hypnotic spirals."""
    lat = np.arcsin(np.clip(d[..., 1], -1, 1))
    lon = np.arctan2(d[..., 2], d[..., 0])
    arms = 0.5 + 0.5 * np.cos(5 * (lon + 2.4 * lat))
    core = arms ** 10
    glow = arms ** 3
    hue = 0.5 + lat / np.pi * 1.35 + 0.08 * np.sin(5 * (lon + 2.4 * lat))
    neon = hsv2rgb(hue, 0.85, 1.0)
    col = np.zeros(d.shape[:2] + (3,)) + np.array([0.03, 0.02, 0.06])
    col = col + neon * glow[..., None] * 0.85
    col = col + (neon * 0.4 + 0.6) * core[..., None] * 0.6
    rings = np.exp(-((np.mod(lat / np.pi * 9 + 0.5, 1) - 0.5) / 0.03) ** 2)
    col = col + hsv2rgb(hue + 0.5, 0.6, 1.0) * rings[..., None] * 0.25
    return np.clip(col, 0, 1)


# ---------------------------------------------------------------- v4 pool designs


def _leaf_decal(size=1024):
    """Gold glitter outline of a cannabis leaf with a 3D extrusion, plus '420'."""
    from PIL import ImageFilter
    im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    cx, cy = size * 0.5, size * 0.56
    leaves = [(0, 0.44, 0.040), (30, 0.39, 0.036), (-30, 0.39, 0.036), (60, 0.30, 0.031),
              (-60, 0.30, 0.031), (92, 0.19, 0.025), (-92, 0.19, 0.025)]

    def leaflet(angle_deg, L, Wd, ox=0.0, oy=0.0):
        a = np.radians(90 - angle_deg)
        pts_l, pts_r = [], []
        n = 23
        for i in range(n + 1):
            f = i / n
            width = Wd * np.sin(np.pi * f ** 0.85) ** 0.9 * size
            serr = (0.45 if i % 2 else 0.0) * width * (0.15 < f < 0.92)
            along = f * L * size
            px, py = np.cos(a) * along, -np.sin(a) * along
            nx, ny = np.sin(a), np.cos(a)
            pts_l.append((cx + ox + px + nx * (width + serr), cy + oy + py + ny * (width + serr)))
            pts_r.append((cx + ox + px - nx * (width + serr), cy + oy + py - ny * (width + serr)))
        return pts_l + pts_r[::-1]

    ext = (size * 0.022, size * 0.016)
    gold_dk, gold = (190, 125, 30, 255), (255, 210, 80, 255)
    lw = max(4, size // 95)
    for ang, L, Wd in leaves:                                  # extrusion: back outline + depth lines
        dr.line(leaflet(ang, L, Wd, *ext) + [leaflet(ang, L, Wd, *ext)[0]], fill=gold_dk, width=lw)
    for ang, L, Wd in leaves:
        P = leaflet(ang, L, Wd)
        Q = leaflet(ang, L, Wd, *ext)
        tip = len(P) // 2 - 0
        for k in (tip - 1, 0):
            dr.line([P[k], Q[k]], fill=gold_dk, width=lw)
    for ang, L, Wd in leaves:
        P = leaflet(ang, L, Wd)
        dr.polygon(P, fill=(0, 0, 0, 0))
        dr.line(P + [P[0]], fill=gold, width=lw)
    dr.line([(cx, cy), (cx, cy + size * 0.14)], fill=gold, width=lw)
    font = None
    for f in ['/System/Library/Fonts/Supplemental/Arial Black.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
              '/System/Library/Fonts/Helvetica.ttc']:
        if os.path.exists(f):
            font = ImageFont.truetype(f, int(size * 0.17))
            break
    tx, ty = cx, cy + size * 0.25
    dr.text((tx + ext[0], ty + ext[1]), '420', font=font, anchor='mm', fill=(0, 0, 0, 0), stroke_width=lw, stroke_fill=gold_dk)
    dr.text((tx, ty), '420', font=font, anchor='mm', fill=(0, 0, 0, 0), stroke_width=lw, stroke_fill=gold)
    a = np.asarray(im, float) / 255
    # glitter: speckle the gold
    rng = np.random.default_rng(5)
    sp = rng.uniform(0.7, 1.25, a.shape[:2])
    a[..., :3] = np.clip(a[..., :3] * sp[..., None], 0, 1)
    return Image.fromarray((a * 255).astype(np.uint8), 'RGBA')


# ---------------------------------------------------------------- v5 pool designs


def iq420(d):
    """Storm !Q-style dark emerald pearl with green sparkle, gold 3D leaf + 420 logo on both sides."""
    w = d + 0.7 * np.stack([fbm(d * 1.2, 3, seed=s) for s in (501, 503, 505)], -1)
    cloud = smoothstep(0.0, 0.5, fbm(w * 1.4, 5, seed=507))
    streak = smoothstep(0.25, 0.6, fbm(w * 2.8 + 3, 4, seed=509))
    col = mix(C(8, 18, 12), C(22, 96, 44), cloud)
    col = col + C(50, 175, 70) * (streak * cloud)[..., None] * 0.7
    glit = (perlin(d * 140, seed=511) > 0.42) * (0.3 + 0.7 * cloud)
    glit2 = (perlin(d * 210, seed=513) > 0.5) * 0.6
    col = col + C(120, 230, 90) * glit[..., None] * 0.55 + C(230, 200, 90) * (glit2 * cloud)[..., None] * 0.35
    col = col * (0.85 + 0.15 * smoothstep(-1, 0.4, d[..., 1]))[..., None]
    leaf = _leaf_decal()
    col = decal(col, d, (0, 0, 1), leaf, 48)
    col = decal(col, d, (0, 0, -1), leaf, 48)
    return np.clip(col, 0, 1)


def synthwave(d):
    """Retro synthwave: neon striped sun over wireframe mountains, gradient sky,
    glowing grid ground. Sunsets on both sides of the ball."""
    lat = np.arcsin(np.clip(d[..., 1], -1, 1))
    lon = np.arctan2(d[..., 2], d[..., 0])
    sky_t = np.clip(lat / (np.pi / 2), 0, 1)
    sky = np.where((sky_t < 0.25)[..., None], mix(C(255, 120, 60), C(230, 40, 140), sky_t / 0.25),
                   mix(C(230, 40, 140), C(25, 8, 60), np.clip((sky_t - 0.25) / 0.6, 0, 1)))
    # stars up high
    from make_orbs import _sphere_pts
    st = np.zeros(d.shape[:2])
    for p in _sphere_pts(160, 901):
        if p[1] < 0.35:
            continue
        st = np.maximum(st, np.exp(-(np.arccos(np.clip(d @ p, -1, 1)) / 0.009) ** 2))
    sky = sky + st[..., None] * 0.9
    col = sky.copy()
    # two suns (front and back), striped toward the bottom
    for zs in (1, -1):
        ang = np.arccos(np.clip(d @ np.array([0, 0.28, zs]) / np.linalg.norm([0, 0.28, 1]), -1, 1))
        sun = smoothstep(0.43, 0.41, ang)
        rel = (lat - 0.02) / 0.62
        stripes = (np.sin(rel * 46) > -0.2 + 1.4 * (1 - np.clip(rel / 0.55, 0, 1))) | (rel > 0.45)
        sun = sun * stripes * (lat > 0.0)
        sc = mix(C(255, 60, 140), C(255, 230, 80), np.clip(rel * 1.6, 0, 1))
        glow = np.exp(-((ang - 0.42) / 0.12) ** 2) * (ang > 0.42) * (lat > -0.02)
        col = col + C(255, 90, 150) * glow[..., None] * 0.35
        col = mix(col, sc, sun)
    # wireframe mountains along the horizon
    ridge = 0.06 + 0.16 * np.clip(fbm(np.stack([np.cos(lon) * 2.2, np.sin(lon) * 2.2, np.zeros_like(lon)], -1), 4, seed=903) + 0.25, 0, 1)
    mnt = (lat > 0) & (lat < ridge)
    edge = np.exp(-((lat - ridge) / 0.008) ** 2)
    col = np.where(mnt[..., None], C(30, 8, 50), col)
    col = col + C(0, 230, 255) * edge[..., None] * 0.9
    # glowing grid ground
    g = lat < 0
    depth = np.clip(-lat / (np.pi / 2), 1e-3, 1)
    rows = np.abs(np.sin(np.pi * 1.4 / np.maximum(depth, 0.03)))
    cols_ = np.abs(np.sin(lon * 18))
    line = np.maximum(smoothstep(0.12, 0.0, rows), smoothstep(0.10, 0.0, cols_) * (depth > 0.02))
    ground = C(18, 4, 40) + C(255, 40, 200) * line[..., None] * (0.35 + 0.65 * (1 - depth))[..., None]
    col = np.where(g[..., None], ground, col)
    col = col + C(255, 80, 180) * np.exp(-(lat / 0.02) ** 2)[..., None] * 0.6     # horizon glow
    return np.clip(col, 0, 1)


# ---------------------------------------------------------------- skill detector test balls


# ---------------------------------------------------------------- v6: fully original replacements
def _font(size, bold=True):
    for f in ['/System/Library/Fonts/Supplemental/Arial Black.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
              '/System/Library/Fonts/Helvetica.ttc']:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)


def _riptide_logo(size=1024):
    """Original logo: outlined lettering in a dashed frame (yellow, like a real ball logo)."""
    im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    gold = (250, 228, 50, 255)
    f = _font(int(size * 0.19))
    dr.text((size / 2, size / 2), 'RIPTIDE', font=f, anchor='mm', fill=(0, 0, 0, 0), stroke_width=13, stroke_fill=gold)
    x0, y0, x1, y1 = size * 0.05, size * 0.35, size * 0.95, size * 0.65
    seg, gap = size * 0.06, size * 0.025
    lw = 13
    x = x0
    while x < x1:
        dr.line([(x, y0), (min(x + seg, x1), y0)], fill=gold, width=lw)
        dr.line([(x, y1), (min(x + seg, x1), y1)], fill=gold, width=lw)
        x += seg + gap
    y = y0
    while y < y1:
        dr.line([(x0, y), (x0, min(y + seg, y1))], fill=gold, width=lw)
        dr.line([(x1, y), (x1, min(y + seg, y1))], fill=gold, width=lw)
        y += seg + gap
    return im


def riptide(d):
    """Teal / crimson / black solid reactive (procedural coverstock) with an original logo."""
    import make_identity
    col = make_identity.coverstock(d)
    logo = _riptide_logo()
    col = decal(col, d, (0, 0, 1), logo, 40)
    col = decal(col, d, (0, 0, -1), logo, 40)
    return np.clip(col, 0, 1)


def emerald420(d):
    return iq420(d)


def _smiley_face(kind, size=1024):
    """Hand-built faces (no outside artwork). kind: 'classic' or 'goofy'."""
    im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    S = size
    ink = (40, 22, 8, 255)
    if kind == 'classic':
        for cx in (0.36, 0.64):
            dr.ellipse([(cx - 0.055) * S, 0.24 * S, (cx + 0.055) * S, 0.46 * S], fill=ink)
            dr.ellipse([(cx - 0.035) * S, 0.27 * S, (cx - 0.005) * S, 0.31 * S], fill=(255, 255, 255, 150))
        dr.arc([0.22 * S, 0.22 * S, 0.78 * S, 0.80 * S], start=20, end=160, fill=ink, width=int(S * 0.045))
        for cx, ang in ((0.255, 160), (0.745, 20)):                      # dimples at the smile ends
            a = np.radians(ang)
            px, py = 0.5 + 0.28 * np.cos(a), 0.51 + 0.29 * np.sin(a)
            dr.arc([(px - 0.05) * S, (py - 0.05) * S, (px + 0.05) * S, (py + 0.05) * S],
                   start=ang - 70 if cx < 0.5 else ang - 110, end=ang + 70 if cx < 0.5 else ang + 110, fill=ink, width=int(S * 0.02))
    else:
        # big googly eyes looking different ways
        for cx, (px, py) in ((0.35, (0.03, -0.01)), (0.65, (-0.02, 0.03))):
            dr.ellipse([(cx - 0.12) * S, 0.18 * S, (cx + 0.12) * S, 0.46 * S], fill=(250, 250, 250, 255), outline=ink, width=int(S * 0.012))
            dr.ellipse([(cx + px - 0.05) * S, (0.33 + py - 0.06) * S, (cx + px + 0.05) * S, (0.33 + py + 0.06) * S], fill=ink)
            dr.ellipse([(cx + px - 0.02) * S, (0.33 + py - 0.04) * S, (cx + px + 0.005) * S, (0.33 + py - 0.015) * S], fill=(255, 255, 255, 255))
        # raised eyebrows
        dr.line([(0.24 * S, 0.14 * S), (0.42 * S, 0.11 * S)], fill=ink, width=int(S * 0.03))
        dr.line([(0.58 * S, 0.10 * S), (0.76 * S, 0.15 * S)], fill=ink, width=int(S * 0.03))
        # lopsided grin with the tongue sticking out
        dr.chord([0.24 * S, 0.40 * S, 0.80 * S, 0.80 * S], start=8, end=172, fill=(120, 20, 25, 255), outline=ink, width=int(S * 0.02))
        dr.rectangle([0.30 * S, 0.585 * S, 0.74 * S, 0.62 * S], fill=(250, 250, 245, 255))      # top teeth
        dr.ellipse([0.46 * S, 0.62 * S, 0.70 * S, 0.92 * S], fill=(235, 70, 90, 255), outline=ink, width=int(S * 0.012))
        dr.line([(0.58 * S, 0.66 * S), (0.585 * S, 0.84 * S)], fill=(180, 40, 60, 255), width=int(S * 0.012))
    return im


def smiley(d):
    """Glossy yellow ball: classic smiley on one side, goofy tongue-out face on the other."""
    yellow = C(255, 205, 40)
    col = np.zeros(d.shape[:2] + (3,)) + yellow
    col = col * (0.9 + 0.12 * smoothstep(-1, 0.6, d[..., 1]))[..., None]
    col = mix(col, C(240, 150, 30), smoothstep(-0.2, -1.0, d[..., 1]) * 0.35)       # warmer underside
    col = decal(col, d, (0, 0, 1), _smiley_face('classic'), 62)
    col = decal(col, d, (0, 0, -1), _smiley_face('goofy'), 62)
    return np.clip(col, 0, 1)


def stainedglass(d):
    """Cathedral rose windows on both sides, jewel-toned panes and lead came
    between them, random panes round the middle."""
    PAL = [C(190, 20, 40), C(20, 120, 60), C(30, 70, 190), C(240, 180, 30), C(130, 40, 160), C(20, 150, 170)]
    z = d[..., 2]
    th = np.arccos(np.clip(np.abs(z), -1, 1))
    ph = np.arctan2(d[..., 1], d[..., 0] * np.where(z >= 0, 1, -1))
    rings = [0.0, 0.16, 0.42, 0.72, 1.02]
    ring = np.digitize(th, rings) - 1
    petals = np.array([1, 8, 12, 16, 24])
    rose = th < rings[-1]
    n_p = petals[np.clip(ring, 0, 4)]
    off = np.where(ring % 2 == 1, 0.5, 0.0)
    pos = ph / (2 * np.pi) * n_p + off + 0.12 * np.sin(th * 9)                      # gently curved mullions
    petal = np.floor(pos)
    frac = pos - petal
    pane = ((petal.astype(int) * (1 + ring % 2) + ring * 2) % len(PAL))
    col = np.stack(PAL)[pane]
    col = np.where((ring == 0)[..., None], C(250, 220, 90), col)                    # golden centre
    lead_r = np.min([np.abs(th - r) for r in rings[1:]], axis=0) < 0.012
    lead_p = (np.minimum(frac, 1 - frac) * 2 * np.pi * np.sin(np.maximum(th, 0.02)) / n_p < 0.011) & (ring > 0)
    # random panes around the middle band
    i = np.arange(260) + 0.5
    phi = np.arccos(1 - 2 * i / 260); tp = np.pi * (1 + 5 ** 0.5) * i
    pts = np.stack([np.cos(tp) * np.sin(phi), np.cos(phi), np.sin(tp) * np.sin(phi)], -1)
    dots = d.reshape(-1, 3) @ pts.T
    cell = dots.argmax(1).reshape(d.shape[:2])
    dist = np.sqrt(np.clip(2 - 2 * dots, 0, None))
    part = np.partition(dist, 1, axis=1)
    edge = (part[:, 1] - part[:, 0]).reshape(d.shape[:2])
    band = np.stack(PAL)[cell % len(PAL)] * (0.75 + 0.25 * ((cell * 7) % 5) / 4)[..., None]
    col = np.where(rose[..., None], col, band)
    lead = np.where(rose, lead_r | lead_p, edge < 0.014)
    glass = 0.82 + 0.18 * fbm(d * 14, 3, seed=951) + 0.12 * fbm(d * 3, 2, seed=953)
    col = col * glass[..., None]
    col = mix(col, C(25, 22, 20), lead.astype(float))
    return np.clip(col, 0, 1)


POOL = ['riptide', 'galaxy', 'tiedye', 'hyperspin', 'smiley', 'emerald420', 'stainedglass', 'synthwave']

if __name__ == '__main__':
    main(sys.argv[1:] or None)
