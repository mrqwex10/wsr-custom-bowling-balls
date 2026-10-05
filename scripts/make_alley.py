"""Alley skin concepts: procedural (original) art for the Bowling stage textures.

Each concept returns {'tex': {texture name: PIL image}, 'anim': {texture name: [frames]}}.
Texture names are the ones inside Stage/BwlScene/Normal.carc -> G3D/bwg_field.brres.

Layout facts (from the stage models):
  floor        lane + approach boards, tiles every ~35 cm across x ~74 cm along the lane
  mark         left HALF of a lane's arrows/dots/foul line (mirror wrap: right edge = lane centre)
  gater        gutter: u 0..0.5 = cross-section, v repeats every ~30 cm along the lane
  ball_return_2  the rails between lane pairs (tiny tile)
  bwg_screen_2 masking-unit screen above the pins (1024x512, ~30 px trim top & bottom)
  bwg_screen_alpha2  same art at half size (its reflection in the lane)
  ue_40        ceiling (mirror wrap)       roof_light  ceiling light strips (LA)
  inside       pit behind the pins         bwg_pin     pin (u 0..2 around, v top->bottom)
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.ndimage import gaussian_filter
sys.path.insert(0, os.path.dirname(__file__))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = os.path.join(ROOT, 'work/stage/png')
FRAMES = 8


def stock(name):
    if not os.path.exists(os.path.join(PNG, name + '.png')):
        from alley_render import ensure_stage
        ensure_stage('normal')
    return Image.open(os.path.join(PNG, name + '.png'))


def arr(im):
    return np.asarray(im.convert('RGBA'), np.float32) / 255.0


def img(a):
    a = np.clip(a, 0, 1)
    mode = 'RGBA' if a.shape[2] == 4 else 'RGB'
    return Image.fromarray((a * 255 + 0.5).astype(np.uint8), mode)


def tnoise(h, w, scale, seed, octaves=4):
    """Tileable fractal noise in [0,1] (band-limited white noise, so it wraps seamlessly)."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    fy = np.fft.fftfreq(h)[:, None] * h
    fx = np.fft.fftfreq(w)[None, :] * w
    for o in range(octaves):
        s = scale * 2 ** o
        f = np.exp(-(fx ** 2 + fy ** 2) / (2 * s ** 2))
        n = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((h, w))) * f))
        n = (n - n.mean()) / (n.std() + 1e-9)
        out += amp * n
        tot += amp
        amp *= 0.5
    out /= tot
    return np.clip(0.5 + 0.22 * out, 0, 1)


def wrap_blur(a, s):
    return gaussian_filter(a, (s, s) + (0,) * (a.ndim - 2), mode='wrap')


def stars(h, w, n, seed, size=(0.6, 1.6), colors=((1, 1, 1),), wrap=True):
    rng = np.random.default_rng(seed)
    layer = np.zeros((h, w, 3))
    for _ in range(n):
        y, x = rng.uniform(0, h), rng.uniform(0, w)
        r = rng.uniform(*size)
        c = np.array(colors[rng.integers(len(colors))]) * rng.uniform(0.5, 1.0)
        R = int(np.ceil(r * 3))
        for dy in range(-R, R + 1):
            for dx in range(-R, R + 1):
                yy, xx = int(y) + dy, int(x) + dx
                if wrap:
                    yy, xx = yy % h, xx % w
                elif not (0 <= yy < h and 0 <= xx < w):
                    continue
                d2 = (yy - y) ** 2 + (xx - x) ** 2 if not wrap else ((int(y) + dy) - y) ** 2 + ((int(x) + dx) - x) ** 2
                layer[yy, xx] += c * np.exp(-d2 / (2 * (r * 0.6) ** 2))
    return layer


def boards(h, w, nboards, seed, base, grain, seam=0.55, jitter=0.06):
    """Lane boards running along v (the lane length), tileable."""
    rng = np.random.default_rng(seed)
    x = np.arange(w)
    bw = w / nboards
    idx = (x // bw).astype(int)
    tone = rng.uniform(1 - jitter, 1 + jitter, nboards)[idx]
    g = tnoise(h, w, 1.5, seed)
    streak = tnoise(h, w, 3, seed + 1)
    streak = gaussian_filter(streak, (6, 0.3), mode='wrap')
    col = np.array(base)[None, None] * tone[None, :, None]
    col = col * (1 - grain * 0.5 + grain * (0.6 * streak + 0.4 * g))[..., None]
    edge = np.minimum((x % bw), bw - (x % bw))
    col *= (1 - (1 - seam) * np.exp(-edge ** 2 / 0.6))[None, :, None]
    return col


def recolor_mark(fill, glow_col, glow=6, glow_amt=0.9, inner=None):
    """Original lane markings re-coloured with a neon halo (keeps the real arrow/dot positions)."""
    m = arr(stock('mark'))[..., 3]
    halo = gaussian_filter(m, glow, mode='nearest')
    halo = np.clip(halo * 2.2, 0, 1) * glow_amt
    a = np.clip(m + halo * (1 - m), 0, 1)
    col = (np.array(fill)[None, None] * m[..., None] + np.array(glow_col)[None, None] * (halo * (1 - m))[..., None])
    col = col / np.maximum(a[..., None], 1e-6)
    if inner is not None:                      # hot core
        core = gaussian_filter(m, 1.2) ** 3
        col = col * (1 - core[..., None]) + np.array(inner)[None, None] * core[..., None]
    return img(np.dstack([col, a]))


def screen_frame(content, trim_col, edge_col, trim=30):
    """Put content (1024x(512-2*trim)) into the screen texture with a top/bottom trim."""
    H, W = 512, 1024
    out = np.zeros((H, W, 3))
    out[trim:H - trim] = content
    yy = np.arange(trim)[:, None, None] / trim
    band = np.array(trim_col)[None, None] * (0.75 + 0.25 * np.sin(yy * np.pi))
    out[:trim] = band
    out[H - trim:] = band[::-1]
    for y0 in (trim - 3, H - trim):
        out[y0:y0 + 3] = edge_col
    return out


def finish_screen(a):
    im = img(a)
    return im, im.resize((512, 256), Image.LANCZOS)


def pin_tex(band_cols, body=(0.96, 0.96, 0.98), glow=None):
    """bwg_pin: 64x128, v runs top->bottom of the pin; the stock texture has a chevron at the neck."""
    p = arr(stock('bwg_pin'))[..., :3]
    red = (p[..., 0] - p[..., 2]) > 0.25
    out = np.ones_like(p) * np.array(body)
    shade = p.mean(2, keepdims=True) / np.maximum(p[~red].mean(), 1e-3)
    out = out * np.clip(shade, 0.85, 1.05)
    c1, c2 = band_cols
    v = np.linspace(0, 1, p.shape[0])[:, None, None]
    out[red] = (np.array(c1) * (1 - v) + np.array(c2) * v)[np.nonzero(red)[0], 0]
    return img(out)


# ----------------------------------------------------------------------------------
# Concept 1: COSMIC GLOW - blacklight night bowling in deep space
# ----------------------------------------------------------------------------------
def cosmic():
    T, A = {}, {}
    # lane: midnight boards with glitter specks
    fl = boards(256, 128, 13, 11, (0.10, 0.08, 0.20), 0.6, seam=0.6)
    fl += stars(256, 128, 70, 12, (0.4, 1.0), ((0.3, 1, 1), (1, 0.3, 0.9), (1, 0.9, 0.3), (1, 1, 1))) * 0.9
    T['floor'] = img(fl)
    T['mark'] = recolor_mark((0.55, 1.0, 1.0), (0.1, 0.8, 1.0), glow=5, inner=(0.95, 1, 1))
    # gutters: dark channel with a neon stripe; chase-light dashes run toward the pins
    def gut(phase):
        h, w = 128, 128
        u = np.arange(w)[None, :] / w
        v = np.arange(h)[:, None] / h
        base = np.zeros((h, w, 3)) + np.array([0.06, 0.05, 0.12])
        stripe = np.exp(-((u - 0.25) / 0.035) ** 2)
        dash = (0.35 + 0.65 * (((v + phase) % 0.5) < 0.18))
        base += stripe[..., None] * dash[..., None] * np.array([1.0, 0.25, 0.95])
        base += (np.exp(-((u - 0.05) / 0.02) ** 2) + np.exp(-((u - 0.45) / 0.02) ** 2))[..., None] * np.array([0.1, 0.6, 1.0]) * 0.8
        return img(base)
    A['gater'] = [gut(i / FRAMES / 2) for i in range(FRAMES)]
    T['gater'] = A['gater'][0]
    T['ball_return_2'] = img(np.zeros((16, 16, 3)) + np.array([0.22, 0.2, 0.6]) * np.linspace(0.7, 1, 16)[:, None, None])
    # ceiling: night sky
    ce = np.zeros((256, 512, 3)) + np.array([0.025, 0.02, 0.07])
    neb = tnoise(256, 512, 1.0, 21, octaves=2)
    ce += ((neb - 0.5).clip(0) * 0.8)[..., None] * np.array([0.3, 0.1, 0.45])
    ce += stars(256, 512, 200, 22, (0.35, 0.8), ((1, 1, 1), (0.6, 0.8, 1), (1, 0.8, 0.9)))
    T['ue_40'] = img(ce)
    T['ue_kan05'] = img(np.zeros((256, 512, 3)) + 0.25)
    # ceiling strips: neon tubes (RGBA instead of LA so they can be coloured)
    rl = arr(stock('roof_light'))
    tube = np.zeros(rl.shape[:2] + (3,)) + np.array([0.75, 0.3, 1.0])
    T['roof_light'] = img(np.dstack([tube, rl[..., 3] * 0.9]))
    T['inside'] = img(arr(stock('inside'))[..., :3] * np.array([0.35, 0.3, 0.6]))
    T['bwg_pin'] = pin_tex(((1.0, 0.2, 0.9), (0.2, 0.9, 1.0)))
    # screen: animated deep-space scene
    A['bwg_screen_2'] = [cosmic_screen(i) for i in range(FRAMES)]
    T['bwg_screen_2'], T['bwg_screen_alpha2'] = finish_screen(A['bwg_screen_2'][0])
    A['bwg_screen_2'] = [img(a) for a in A['bwg_screen_2']]
    darken(T, ('carpet_2', 'back_roof_2', 'counter', 'chair', 'ball_stand_2', 'back_floor', 'jihanki', 'dust_table'), (0.35, 0.3, 0.55))
    pin_spots(T, (0.3, 0.9, 1.0))
    return dict(tex=T, anim=A)


def pin_spots(T, col):
    """pin_spot: the pin-position dots on each lane's pin deck (RGBA, alpha = dot shape)."""
    a = arr(stock('pin_spot'))
    a[..., :3] = np.array(col)
    T['pin_spot'] = img(a)


def darken(T, names, tint):
    for n in names:
        a = arr(stock(n))
        a[..., :3] *= np.array(tint)
        T[n] = img(a if stock(n).mode in ('RGBA', 'LA') else a[..., :3])


def cosmic_screen(f):
    H, W = 452, 1024
    t = f / FRAMES
    y, x = np.mgrid[0:H, 0:W].astype(float)
    sky = np.zeros((H, W, 3)) + np.array([0.02, 0.01, 0.06])
    n1 = tnoise(H, W, 2.0, 31)
    n2 = tnoise(H, W, 4.0, 32)
    drift = np.roll(n1, int(t * W / 4), axis=1)
    neb = np.clip((drift * 0.7 + n2 * 0.5 - 0.48) * 2.4, 0, 1)
    sky += neb[..., None] * (np.array([0.55, 0.1, 0.65]) * (1 - x / W)[..., None] + np.array([0.1, 0.35, 0.8]) * (x / W)[..., None])
    st = stars(H, W, 420, 33, (0.5, 1.3), ((1, 1, 1), (0.7, 0.85, 1), (1, 0.85, 0.7)), wrap=False)
    rng = np.random.default_rng(34)
    tw = 0.6 + 0.4 * np.sin(2 * np.pi * (t + rng.uniform(0, 1, (H // 8 + 1, W // 8 + 1))))
    tw = np.kron(tw, np.ones((8, 8)))[:H, :W]
    sky += st * tw[..., None]
    # ringed planet that is a bowling ball (finger holes), centre
    cx, cy, R = W / 2, H * 0.5, 120
    d = np.hypot(x - cx, y - cy)
    ball = d < R
    lx, ly = (x - cx + 45) / R, (y - cy + 50) / R
    lit = np.clip(1.15 - 0.85 * np.hypot(lx, ly), 0.15, 1)
    swirl = tnoise(H, W, 6, 35)
    bcol = (np.array([0.15, 0.5, 1.0]) * (1 - swirl[..., None]) + np.array([0.75, 0.2, 1.0]) * swirl[..., None])
    bcol = bcol * lit[..., None]
    rim = np.exp(-((d - R) / 4) ** 2)
    # finger holes rotate slowly around the planet
    ang = 2 * np.pi * t
    holes = np.zeros((H, W))
    for hx, hy, hr in ((-28, -40, 14), (22, -42, 14), (-2, 8, 17)):
        px = cx + hx * np.cos(ang * 0.25) * 1.0 + 30 * np.sin(ang) * 0
        holes = np.maximum(holes, (np.hypot(x - (cx + hx), y - (cy + hy)) < hr).astype(float))
    bcol = bcol * (1 - 0.85 * holes[..., None])
    # ring (behind + in front)
    rx, ry = (x - cx) / 230, (y - cy) / 46
    rr = np.hypot(rx, ry)
    ringm = np.clip(1 - np.abs(rr - 1) / 0.12, 0, 1) * (0.6 + 0.4 * np.sin(rr * 60))
    ringc = np.array([1.0, 0.75, 0.35])
    behind = (y < cy) & ball
    sky = sky * (1 - ringm[..., None] * 0.9) + ringc * ringm[..., None]
    sky[ball] = bcol[ball]
    sky += rim[..., None] * np.array([0.4, 0.8, 1.0]) * 0.8
    front = ringm * ((y > cy - 2) | ~ball)
    sky = np.where(((y > cy - 2) & ball)[..., None], sky * (1 - front[..., None] * 0.9) + ringc * front[..., None], sky)
    # comet streaking across, one pass per loop
    hx = -100 + (W + 200) * t
    hy = 70 + 60 * t
    for k in range(40):
        px, py = hx - k * 6, hy - k * 0.4
        a = np.exp(-((x - px) ** 2 + (y - py) ** 2) / (2 * (3 - k * 0.05) ** 2)) * (1 - k / 40)
        sky += a[..., None] * np.array([0.8, 0.95, 1.0])
    # neon pin constellations either side
    for side in (-1, 1):
        ox = W / 2 + side * 360
        pts = [(0, -60), (0, 60), (-30, 0), (30, 0), (0, -110), (0, 110)]
        for (px, py) in [(ox + -20, H / 2 - 80), (ox + 20, H / 2 - 80), (ox, H / 2 - 40), (ox - 40, H / 2 - 40), (ox + 40, H / 2 - 40)][:0]:
            pass
        # 10 pin triangle as stars joined by lines
        tri = [(0, 0), (-1, 1), (1, 1), (-2, 2), (0, 2), (2, 2), (-3, 3), (-1, 3), (1, 3), (3, 3)]
        pp = [(ox + a * 26, H / 2 - 100 + b * 50) for a, b in tri]
        lay = Image.new('L', (W, H), 0)
        dr = ImageDraw.Draw(lay)
        for i, (ax, ay) in enumerate(pp):
            for bx, by in pp[i + 1:]:
                if abs(np.hypot(ax - bx, ay - by) - np.hypot(26, 50)) < 2:
                    dr.line((ax, ay, bx, by), fill=90, width=2)
        for ax, ay in pp:
            dr.ellipse((ax - 4, ay - 4, ax + 4, ay + 4), fill=255)
        L = np.asarray(lay, float) / 255
        L = L + gaussian_filter(L, 5) * 2.5
        pulse = 0.75 + 0.25 * np.sin(2 * np.pi * (t + (0.5 if side > 0 else 0)))
        sky += L[..., None] * np.array([0.3, 0.9, 1.0] if side < 0 else [1.0, 0.35, 0.9]) * pulse
    return screen_frame(np.clip(sky, 0, 1), (0.08, 0.06, 0.16), (0.2, 0.95, 1.0))


def line_mask(lay_fn, W, H, width=2):
    lay = Image.new('L', (W, H), 0)
    lay_fn(ImageDraw.Draw(lay))
    return np.asarray(lay, float) / 255


def glow_of(m, r, amt=1.0):
    return m + gaussian_filter(m, r) * amt * 2.5 + gaussian_filter(m, r * 3) * amt * 1.5


def chrome(u, top, mid, bot):
    """Vertical-profile chrome gradient for rails/gutters, u in 0..1."""
    u = u[..., None]
    c = np.where(u < 0.5, np.array(top) * (1 - u * 2) + np.array(mid) * (u * 2),
                 np.array(mid) * (2 - u * 2) + np.array(bot) * (u * 2 - 1))
    return c


# ----------------------------------------------------------------------------------
# Concept 2: SYNTHWAVE SUNSET - 80s neon grid
# ----------------------------------------------------------------------------------
def synthwave():
    T, A = {}, {}
    h, w = 256, 128
    fl = boards(h, w, 13, 41, (0.13, 0.05, 0.17), 0.35, seam=0.7)
    gx = np.zeros((h, w)); gx[:, :2] = 1; gx[:, -1:] = 1
    gy = np.zeros((h, w)); gy[:2] = 1; gy[h // 2:h // 2 + 2] = 1
    grid = np.clip(gx + gy, 0, 1)
    grid = grid + wrap_blur(grid, 2.5) * 1.5
    fl += grid[..., None] * np.array([1.0, 0.15, 0.75]) * 0.32
    T['floor'] = img(fl)
    T['mark'] = recolor_mark((1.0, 0.85, 0.35), (1.0, 0.2, 0.6), glow=6, inner=(1, 1, 0.8))

    def gut(phase):
        u = np.arange(128)[None, :] / 64.0          # only 0..0.5 of the texture is used
        v = np.arange(128)[:, None] / 128
        c = chrome(np.clip(u, 0, 1) * np.ones((128, 1)), (0.25, 0.9, 1.0), (0.25, 0.05, 0.35), (1.0, 0.3, 0.8))
        pulse = np.exp(-(((v - phase) % 1.0 - 0.5) / 0.06) ** 2)
        c = c + pulse[..., None] * np.array([1.0, 0.9, 1.0]) * 0.6 * np.exp(-((u - 0.5) / 0.15) ** 2)[..., None]
        return img(c)
    A['gater'] = [gut(i / FRAMES) for i in range(FRAMES)]
    T['gater'] = A['gater'][0]
    T['ball_return_2'] = img(chrome(np.linspace(0, 1, 16)[:, None] * np.ones((1, 16)), (1.0, 0.5, 0.9), (0.35, 0.1, 0.5), (0.2, 0.8, 1.0)))
    ce = np.zeros((256, 512, 3)) + np.array([0.08, 0.02, 0.12])
    ce += stars(256, 512, 120, 42, (0.35, 0.7), ((1, 0.8, 1), (0.7, 0.9, 1)))
    T['ue_40'] = img(ce)
    T['ue_kan05'] = img(np.zeros((256, 512, 3)) + 0.25)
    rl = arr(stock('roof_light'))
    T['roof_light'] = img(np.dstack([np.zeros(rl.shape[:2] + (3,)) + np.array([0.2, 0.9, 1.0]), rl[..., 3] * 0.9]))
    T['inside'] = img(arr(stock('inside'))[..., :3] * np.array([0.5, 0.25, 0.6]))
    T['bwg_pin'] = pin_tex(((1.0, 0.25, 0.7), (0.25, 0.85, 1.0)))
    fr = [synth_screen(i) for i in range(FRAMES)]
    T['bwg_screen_2'], T['bwg_screen_alpha2'] = finish_screen(fr[0])
    A['bwg_screen_2'] = [img(a) for a in fr]
    darken(T, ('carpet_2', 'back_roof_2', 'counter', 'chair', 'ball_stand_2', 'back_floor', 'jihanki', 'dust_table'), (0.55, 0.3, 0.6))
    pin_spots(T, (1.0, 0.35, 0.8))
    return dict(tex=T, anim=A)


def synth_screen(f):
    H, W = 452, 1024
    t = f / FRAMES
    y, x = np.mgrid[0:H, 0:W].astype(float)
    hz = H * 0.62                                   # horizon
    s = np.clip(y / hz, 0, 1)[..., None]
    sky = np.array([0.08, 0.02, 0.2]) * (1 - s) ** 1.5 + np.array([0.75, 0.1, 0.55]) * s ** 2.2 + np.array([0.3, 0.05, 0.4]) * s * (1 - s)
    sky += stars(H, W, 160, 51, (0.4, 0.9), ((1, 0.9, 1),), wrap=False) * (1 - s) ** 2
    # sun with sliding slits
    cx, cy, R = W / 2, hz - 10, 150
    d = np.hypot(x - cx, (y - cy) * 1.0)
    sunm = d < R
    sg = np.clip((y - (cy - R)) / (2 * R), 0, 1)[..., None]
    sunc = np.array([1.0, 0.95, 0.35]) * (1 - sg) + np.array([1.0, 0.2, 0.55]) * sg
    rel = (y - (cy - R * 0.1)) / (R * 1.1)
    gap_w = np.clip(rel, 0, 1) * 9
    band = ((y - cy + t * 22) % 22)
    slit = (rel > 0) & (band < gap_w)
    sm = sunm & ~slit
    sky += gaussian_filter(sunm.astype(float), 25)[..., None] * np.array([1.0, 0.3, 0.6]) * 0.7
    sky = np.where(sm[..., None], sunc, sky)
    # mountains (wireframe silhouettes)
    rng = np.random.default_rng(52)
    xs = np.arange(W)
    ridge = hz - (40 + 70 * np.abs(np.sin(xs / 140 + 1.3)) * (0.6 + 0.4 * np.sin(xs / 53)) * (np.abs(xs - W / 2) / (W / 2)) ** 0.6)
    mnt = (y > ridge[None, :]) & (y < hz)
    sky = np.where(mnt[..., None], np.array([0.12, 0.02, 0.2]) + (hz - y)[..., None] / 120 * np.array([0.2, 0.0, 0.25]), sky)
    edge = np.exp(-((y - ridge[None, :]) / 1.5) ** 2) * (y < hz)
    sky += glow_of(edge, 2, 0.5)[..., None] * np.array([0.3, 0.9, 1.0]) * 0.8
    # floor grid scrolling toward the viewer (drawn as real lines, 3x supersampled)
    flo = y > hz
    sky = np.where(flo[..., None], np.array([0.08, 0.0, 0.15]), sky)
    S = 3
    lay = Image.new('L', (W * S, H * S), 0)
    dr = ImageDraw.Draw(lay)
    vx, vy = W / 2 * S, hz * S
    for k in range(-40, 41):                         # lines running to the vanishing point
        dr.line((vx + k * 3 * S, vy, vx + k * 120 * S, (H + 300) * S), fill=255, width=2 * S)
    for k in range(0, 40):                           # cross lines, spaced by perspective
        zz = k + 1 - t
        if zz <= 0.05:
            continue
        yy = hz + 260 / zz
        if yy < H:
            dr.line((0, yy * S, W * S, yy * S), fill=255, width=2 * S)
    gm = np.asarray(lay.resize((W, H), Image.LANCZOS), float) / 255 * flo
    fade = np.clip((y - hz) / 70, 0, 1) ** 1.2
    sky += (glow_of(gm, 1.5, 0.35) * fade)[..., None] * np.array([1.0, 0.2, 0.8])
    sky += np.exp(-((y - hz) / 2) ** 2)[..., None] * np.array([1.0, 0.5, 0.9])
    # palm silhouettes
    lay = Image.new('L', (W, H), 0)
    dr = ImageDraw.Draw(lay)
    for px, base_y, hgt, lean in ((110, H, 300, 30), (190, H, 220, -20), (W - 120, H, 290, -30), (W - 200, H, 200, 25)):
        pts = [(px + lean * (i / 20) ** 2, base_y - hgt * i / 20) for i in range(21)]
        for i in range(20):
            dr.line(pts[i] + pts[i + 1], fill=255, width=int(12 - i * 0.35))
        tx, ty = pts[-1]
        for a in range(-160, 180, 40):
            r = np.radians(a)
            fr = [(tx + k * 9 * np.cos(r), ty + k * 9 * np.sin(r) * 0.5 + (k / 9) ** 2 * 26) for k in range(10)]
            dr.line([c for p_ in fr for c in p_], fill=255, width=5)
    palm = np.asarray(lay, float) / 255
    sky = sky * (1 - palm[..., None]) + np.array([0.05, 0.0, 0.08]) * palm[..., None]
    rim = gaussian_filter(palm, 2) * (1 - palm)
    sky += rim[..., None] * np.array([1.0, 0.3, 0.7]) * 0.9
    return screen_frame(np.clip(sky, 0, 1), (0.12, 0.04, 0.18), (1.0, 0.25, 0.75))


# ----------------------------------------------------------------------------------
# Concept 3: AURORA ICE - frozen lanes under the northern lights
# ----------------------------------------------------------------------------------
def aurora():
    T, A = {}, {}
    h, w = 256, 128
    fl = boards(h, w, 13, 61, (0.70, 0.84, 0.95), 0.25, seam=0.85, jitter=0.03)
    cr = tnoise(h, w, 6, 62, octaves=3)
    cracks = np.exp(-((cr - 0.5) / 0.012) ** 2) * (tnoise(h, w, 2, 63) > 0.5)
    fl = fl * (1 - 0.15 * wrap_blur(cracks, 1.5)[..., None]) + cracks[..., None] * 0.25
    fl += stars(h, w, 40, 64, (0.3, 0.7), ((1, 1, 1),)) * 0.6
    T['floor'] = img(fl)
    T['mark'] = recolor_mark((0.08, 0.3, 0.75), (0.5, 0.85, 1.0), glow=4, glow_amt=0.6)

    def gut():
        u = np.arange(128)[None, :] / 64.0
        c = chrome(np.clip(u, 0, 1) * np.ones((128, 1)), (0.85, 0.95, 1.0), (0.45, 0.65, 0.85), (0.9, 0.97, 1.0))
        c = c * (0.9 + 0.1 * tnoise(128, 128, 4, 65)[..., None]) + stars(128, 128, 25, 66, (0.3, 0.6)) * 0.5
        return img(c)
    T['gater'] = gut()
    T['ball_return_2'] = img(chrome(np.linspace(0, 1, 16)[:, None] * np.ones((1, 16)), (1, 1, 1), (0.6, 0.8, 0.95), (0.9, 0.95, 1)))
    ce = np.zeros((256, 512, 3)) + np.array([0.03, 0.06, 0.14])
    ce += stars(256, 512, 180, 68, (0.35, 0.8), ((1, 1, 1), (0.8, 0.95, 1)))
    T['ue_40'] = img(ce)
    T['ue_kan05'] = img(np.zeros((256, 512, 3)) + 0.3)
    rl = arr(stock('roof_light'))
    T['roof_light'] = img(np.dstack([np.zeros(rl.shape[:2] + (3,)) + np.array([0.6, 1.0, 0.85]), rl[..., 3] * 0.8]))
    T['inside'] = img(arr(stock('inside'))[..., :3] * np.array([0.5, 0.65, 0.85]))
    T['bwg_pin'] = pin_tex(((0.2, 0.55, 1.0), (0.3, 0.95, 0.75)))
    fr = [aurora_screen(i) for i in range(FRAMES)]
    T['bwg_screen_2'], T['bwg_screen_alpha2'] = finish_screen(fr[0])
    A['bwg_screen_2'] = [img(a) for a in fr]
    darken(T, ('carpet_2', 'back_roof_2', 'counter', 'chair', 'ball_stand_2', 'back_floor', 'jihanki', 'dust_table'), (0.6, 0.75, 0.95))
    pin_spots(T, (0.15, 0.4, 0.85))
    return dict(tex=T, anim=A)


def aurora_screen(f):
    H, W = 452, 1024
    t = f / FRAMES
    y, x = np.mgrid[0:H, 0:W].astype(float)
    s = (y / H)[..., None]
    sky = np.array([0.01, 0.02, 0.08]) * (1 - s) + np.array([0.04, 0.12, 0.22]) * s
    st = stars(H, W, 300, 71, (0.4, 1.0), ((1, 1, 1), (0.8, 0.9, 1)), wrap=False)
    rng = np.random.default_rng(72)
    tw = 0.55 + 0.45 * np.sin(2 * np.pi * (t + rng.uniform(0, 1, (H // 6 + 1, W // 6 + 1))))
    sky += st * np.kron(tw, np.ones((6, 6)))[:H, :W][..., None]
    # aurora curtains: wavy ribbons with vertical rays
    ph = 2 * np.pi * t
    for k, (yc, amp, col, sp) in enumerate(((140, 40, (0.2, 1.0, 0.55), 1), (110, 30, (0.25, 0.7, 1.0), -1), (170, 25, (0.7, 0.3, 1.0), 1))):
        cy = yc + amp * np.sin(x / 170 + ph * sp + k) + 15 * np.sin(x / 53 - ph * sp * 2 + k * 2)
        dy = y - cy
        curtain = np.where(dy < 0, np.exp(-(dy / 70) ** 2), np.exp(-(dy / 10) ** 2))
        rays = 0.55 + 0.45 * np.sin(x / 7 + 3 * np.sin(x / 40 + ph * sp + k) + ph * 2 * sp)
        sky += (curtain * rays * 0.75)[..., None] * np.array(col)
    # mountains with snow
    xs = np.arange(W)
    r1 = H * 0.72 - 90 * np.abs(np.sin(xs / 160 + 0.4)) - 30 * np.abs(np.sin(xs / 61 + 2))
    r2 = H * 0.85 - 50 * np.abs(np.sin(xs / 110 + 2.2)) - 15 * np.abs(np.sin(xs / 37))
    m1 = y > r1[None, :]
    snow = np.clip(1 - (y - r1[None, :]) / 45, 0, 1) * (0.6 + 0.4 * (tnoise(H, W, 8, 73) > 0.45))
    mc = np.array([0.12, 0.18, 0.3]) * (1 - snow[..., None]) + np.array([0.75, 0.85, 1.0]) * snow[..., None]
    sky = np.where(m1[..., None], mc, sky)
    m2 = y > r2[None, :]
    sky = np.where(m2[..., None], np.array([0.05, 0.08, 0.15]) + 0.5 * np.clip(1 - (y - r2[None, :]) / 20, 0, 1)[..., None] * np.array([0.6, 0.7, 0.9]), sky)
    # pine silhouettes
    lay = Image.new('L', (W, H), 0)
    dr = ImageDraw.Draw(lay)
    rng = np.random.default_rng(74)
    for px in list(range(10, 300, 34)) + list(range(W - 300, W, 34)):
        hh = rng.uniform(70, 130)
        by = H
        dr.polygon([(px, by - hh), (px - hh * 0.28, by), (px + hh * 0.28, by)], fill=255)
    tr = np.asarray(lay, float) / 255
    sky = sky * (1 - tr[..., None]) + np.array([0.02, 0.04, 0.08]) * tr[..., None]
    # ice-crystal pin emblem in the middle
    lay = Image.new('L', (W, H), 0)
    dr = ImageDraw.Draw(lay)
    cx, cy = W / 2, H * 0.5
    for a in range(0, 360, 60):
        r = np.radians(a)
        ex, ey = cx + 90 * np.cos(r), cy + 90 * np.sin(r)
        dr.line((cx, cy, ex, ey), fill=255, width=6)
        for k in (0.45, 0.7):
            bx, by = cx + 90 * k * np.cos(r), cy + 90 * k * np.sin(r)
            for b in (-1, 1):
                r2_ = r + b * np.radians(45)
                dr.line((bx, by, bx + 28 * np.cos(r2_), by + 28 * np.sin(r2_)), fill=255, width=5)
    cr = np.asarray(lay, float) / 255
    pulse = 0.85 + 0.15 * np.sin(2 * np.pi * t)
    sky += glow_of(cr, 4, 0.6)[..., None] * np.array([0.6, 0.9, 1.0]) * pulse
    return screen_frame(np.clip(sky, 0, 1), (0.75, 0.88, 1.0), (1.0, 1.0, 1.0))


# ----------------------------------------------------------------------------------
# Concept 4: LAVA FORGE - obsidian lanes with molten cracks
# ----------------------------------------------------------------------------------
def lava():
    T, A = {}, {}
    h, w = 256, 128
    base = boards(h, w, 13, 81, (0.11, 0.09, 0.09), 0.5, seam=0.6)
    base += stars(h, w, 25, 82, (0.3, 0.6), ((1, 0.5, 0.1),)) * 0.5
    xx = np.arange(w)[None, :]
    seams = np.zeros((h, w))
    for sx in (w * 3 / 13, w * 9 / 13):          # two glowing seams per tile, along the lane
        seams += np.exp(-((xx - sx) / 0.9) ** 2)
    vv = np.arange(h)[:, None] / h

    def floor_frame(k):
        heat = 0.55 + 0.45 * np.sin(2 * np.pi * (vv * 2 - k / FRAMES))   # flows toward the pins
        core = seams * heat
        halo = wrap_blur(core, 3.0)
        c = base + core[..., None] * np.array([1.0, 0.6, 0.15]) + (halo * 2.2)[..., None] * np.array([0.7, 0.15, 0.0])
        return img(c)
    A['floor'] = [floor_frame(k) for k in range(FRAMES)]
    T['floor'] = A['floor'][0]
    T['mark'] = recolor_mark((1.0, 0.75, 0.2), (1.0, 0.3, 0.0), glow=6, inner=(1, 1, 0.7))
    lv = tnoise(128, 128, 3, 85)
    lv2 = tnoise(128, 128, 6, 86)

    def gut(k):
        u = np.arange(128)[None, :] / 64.0
        shift = int(round(k * 128 / FRAMES))
        n = np.roll(lv, shift, axis=0) * 0.6 + np.roll(lv2, shift * 2, axis=0) * 0.4
        hot = np.clip((n - 0.35) * 2.2, 0, 1)
        prof = np.exp(-((u - 0.5) / 0.28) ** 2)
        c = np.array([0.5, 0.05, 0.0]) + hot[..., None] * np.array([0.5, 0.75, 0.25])
        c = c * prof[..., None] + np.array([0.12, 0.08, 0.07]) * (1 - prof[..., None])
        return img(c)
    A['gater'] = [gut(k) for k in range(FRAMES)]
    T['gater'] = A['gater'][0]
    T['ball_return_2'] = img(chrome(np.linspace(0, 1, 16)[:, None] * np.ones((1, 16)), (0.35, 0.3, 0.3), (0.12, 0.1, 0.1), (0.9, 0.35, 0.05)))
    ce = np.zeros((256, 512, 3)) + np.array([0.06, 0.04, 0.04])
    rk = tnoise(256, 512, 12, 87, octaves=2)
    ce *= (0.75 + 0.5 * rk)[..., None]
    ce += stars(256, 512, 90, 88, (0.3, 0.7), ((1, 0.45, 0.1),)) * 0.8
    T['ue_40'] = img(ce)
    T['ue_kan05'] = img(np.zeros((256, 512, 3)) + 0.25)
    rl = arr(stock('roof_light'))
    T['roof_light'] = img(np.dstack([np.zeros(rl.shape[:2] + (3,)) + np.array([1.0, 0.45, 0.1]), rl[..., 3] * 0.8]))
    T['inside'] = img(arr(stock('inside'))[..., :3] * np.array([0.7, 0.35, 0.25]))
    T['bwg_pin'] = pin_tex(((1.0, 0.75, 0.1), (1.0, 0.2, 0.0)))
    fr = [lava_screen(i) for i in range(FRAMES)]
    T['bwg_screen_2'], T['bwg_screen_alpha2'] = finish_screen(fr[0])
    A['bwg_screen_2'] = [img(a) for a in fr]
    darken(T, ('carpet_2', 'back_roof_2', 'counter', 'chair', 'ball_stand_2', 'back_floor', 'jihanki', 'dust_table'), (0.5, 0.35, 0.3))
    pin_spots(T, (1.0, 0.55, 0.1))
    return dict(tex=T, anim=A)


def lava_screen(f):
    H, W = 452, 1024
    t = f / FRAMES
    y, x = np.mgrid[0:H, 0:W].astype(float)
    s = (y / H)[..., None]
    sky = np.array([0.05, 0.02, 0.03]) * (1 - s) + np.array([0.45, 0.08, 0.02]) * s ** 1.5
    smoke = tnoise(H, W, 2.5, 91)
    smoke = np.roll(smoke, -int(t * H / 2), axis=0)
    sky = sky * (0.7 + 0.6 * smoke[..., None])
    cx = W / 2
    # volcano cone
    top = H * 0.38
    halfw = 60 + (y - top) * 1.25
    cone = (y > top) & (np.abs(x - cx) < halfw)
    rock = tnoise(H, W, 5, 92)
    sky = np.where(cone[..., None], np.array([0.12, 0.07, 0.06]) * (0.6 + 0.8 * rock[..., None]), sky)
    # lava rivers down the slopes (flowing)
    for side, ph0 in ((-1, 0.0), (1, 0.4), (-0.4, 0.7)):
        path = cx + side * (y - top) * 0.75 + 18 * np.sin((y - top) / 25 + side)
        rv = np.exp(-((x - path) / (5 + (y - top) * 0.04)) ** 2) * cone
        flow = 0.6 + 0.4 * np.sin((y - top) / 12 - 2 * np.pi * (t * 2 + ph0))
        sky += (rv * flow)[..., None] * np.array([1.0, 0.55, 0.1])
        sky += gaussian_filter(rv, 6)[..., None] * np.array([0.8, 0.2, 0.0]) * 1.5
    # eruption: fountain + glow pulse
    pulse = 0.7 + 0.3 * np.sin(2 * np.pi * t)
    crater = np.exp(-(((x - cx) / 70) ** 2 + ((y - top) / 18) ** 2))
    sky += crater[..., None] * np.array([1.0, 0.6, 0.15]) * 1.2 * pulse
    rng = np.random.default_rng(93)
    lay = np.zeros((H, W))
    for i in range(70):
        ang = rng.uniform(-1.0, 1.0)
        spd = rng.uniform(0.5, 1.0)
        ph = (t + rng.uniform(0, 1)) % 1.0
        px = cx + ang * 260 * ph * spd
        py = top - (300 * spd * ph - 330 * ph ** 2)
        if 0 <= px < W and 0 <= py < H:
            lay[int(py), int(px)] = 1.0
    lay = gaussian_filter(lay, 2.2) * 40
    sky += np.clip(lay, 0, 1.5)[..., None] * np.array([1.0, 0.6, 0.15])
    # ember sparks rising everywhere
    em = np.zeros((H, W))
    for i in range(140):
        ex = rng.uniform(0, W)
        ph = (t + rng.uniform(0, 1)) % 1.0
        ey = H - ph * H * rng.uniform(0.6, 1.2)
        ex += 15 * np.sin(ph * 6 + i)
        if 0 <= ey < H:
            em[int(ey), int(ex) % W] = rng.uniform(0.5, 1)
    sky += np.clip(gaussian_filter(em, 1.3) * 18, 0, 1)[..., None] * np.array([1.0, 0.5, 0.1])
    # foreground lava lake
    lake = y > H * 0.86
    lk = tnoise(H, W, 4, 94)
    lk = np.roll(lk, int(t * W / 8), axis=1)
    sky = np.where(lake[..., None], np.array([0.7, 0.15, 0.0]) + np.clip((lk - 0.45) * 2.5, 0, 1)[..., None] * np.array([0.3, 0.7, 0.3]), sky)
    return screen_frame(np.clip(sky, 0, 1), (0.1, 0.07, 0.06), (1.0, 0.45, 0.05))


# ----------------------------------------------------------------------------------
# Concept 5: WHITEOUT - bright gallery alley, dark pins (colour-balance experiment)
# ----------------------------------------------------------------------------------
PIN_WAYS = {                       # body, band top, band bottom
    'onyx': ((0.025, 0.025, 0.03), (1.0, 1.0, 1.0), (0.85, 0.85, 0.88)),
    'navy': ((0.06, 0.09, 0.22), (1.0, 0.78, 0.25), (1.0, 0.65, 0.15)),
    'garnet': ((0.32, 0.03, 0.07), (1.0, 1.0, 1.0), (0.95, 0.9, 0.9)),
    'forest': ((0.04, 0.17, 0.11), (0.95, 0.85, 0.55), (0.9, 0.75, 0.4)),
}


def lighten(T, names, amt, tint=(1, 1, 1)):
    for n in names:
        a = arr(stock(n))
        g = a[..., :3].mean(2, keepdims=True)
        a[..., :3] = (a[..., :3] * 0.25 + g * 0.75) * (1 - amt) + np.array(tint) * amt
        T[n] = img(a if stock(n).mode in ('RGBA', 'LA') else a[..., :3])


def whiteout(pins='onyx'):
    T, A = {}, {}
    h, w = 256, 128
    T['floor'] = img(boards(h, w, 13, 101, (0.80, 0.78, 0.74), 0.18, seam=0.88, jitter=0.02))
    T['mark'] = recolor_mark((0.08, 0.08, 0.1), (0.4, 0.4, 0.45), glow=2, glow_amt=0.25)
    u = np.arange(128)[None, :] / 64.0
    T['gater'] = img(chrome(np.clip(u, 0, 1) * np.ones((128, 1)), (0.85, 0.86, 0.88), (0.55, 0.57, 0.62), (0.85, 0.86, 0.88)))
    T['ball_return_2'] = img(chrome(np.linspace(0, 1, 16)[:, None] * np.ones((1, 16)), (0.85, 0.85, 0.87), (0.6, 0.61, 0.65), (0.8, 0.8, 0.83)))
    ce = np.zeros((256, 512, 3)) + np.array([0.70, 0.70, 0.72])
    xx = np.arange(512)[None, :]
    ce -= (np.minimum(xx % 64, 64 - xx % 64) < 1.5)[..., None] * 0.08     # panel seams

    T['ue_40'] = img(ce)
    T['ue_kan05'] = img(np.zeros((256, 512, 3)) + 0.9)
    rl = arr(stock('roof_light'))
    T['roof_light'] = img(np.dstack([np.ones(rl.shape[:2] + (3,)), rl[..., 3] * 0.9]))
    T['inside'] = img(np.zeros((128, 256, 3)) + 0.78 * (0.85 + 0.15 * arr(stock('inside'))[..., :3]))
    body, b1, b2 = PIN_WAYS[pins]
    T['bwg_pin'] = pin_tex((b1, b2), body=body)
    pin_ways = [pin_tex((w[1], w[2]), body=w[0]) for w in PIN_WAYS.values()]   # far lanes: random colourway
    fr = [white_screen(i, body, b1 if pins != 'onyx' else (1.0, 0.45, 0.3)) for i in range(FRAMES)]
    T['bwg_screen_2'], T['bwg_screen_alpha2'] = finish_screen(fr[0])
    A['bwg_screen_2'] = [img(a) for a in fr]
    lighten(T, ('carpet_2', 'back_roof_2', 'counter', 'chair', 'ball_stand_2', 'back_floor', 'jihanki', 'dust_table'), 0.45, (0.8, 0.8, 0.8))
    pin_spots(T, (0.12, 0.12, 0.14))
    return dict(tex=T, anim=A, pin_ways=pin_ways)


def white_screen(f, ink, band=(1.0, 0.78, 0.25)):
    H, W = 452, 1024
    t = f / FRAMES
    y, x = np.mgrid[0:H, 0:W].astype(float)
    out = np.zeros((H, W, 3)) + 0.68
    out -= (((x % 64) < 1.2) | ((y % 64) < 1.2))[..., None] * 0.04
    ink = np.array(ink)
    floor_y = H * 0.74
    out[int(floor_y):int(floor_y) + 3, 60:W - 60] = ink * 0.5 + 0.4
    # ten pins seen from the front: back row of 4 is smallest/highest
    S = 3
    lay = Image.new('L', (W * S, H * S), 0)
    dr = ImageDraw.Draw(lay)
    rows = [(4, 0.78, -14), (3, 0.86, -8), (2, 0.93, -3), (1, 1.0, 0)]
    cx = 760
    for n, sc, dy in rows:
        for i in range(n):
            px = cx + (i - (n - 1) / 2) * 44 * sc
            base = floor_y + dy
            hgt, rad = 118 * sc, 17 * sc
            dr.ellipse(((px - rad) * S, (base - hgt * 0.48) * S, (px + rad) * S, (base) * S), fill=255)
            dr.rectangle(((px - rad * 0.42) * S, (base - hgt * 0.82) * S, (px + rad * 0.42) * S, (base - hgt * 0.35) * S), fill=255)
            dr.ellipse(((px - rad * 0.62) * S, (base - hgt) * S, (px + rad * 0.62) * S, (base - hgt * 0.72) * S), fill=255)
    pinm = np.asarray(lay.resize((W, H), Image.LANCZOS), float) / 255
    out -= np.exp(-(((x - cx) / 120) ** 2 + ((y - floor_y) / 7) ** 2))[..., None] * 0.15
    out = out * (1 - pinm[..., None]) + ink * pinm[..., None]
    # neck bands in the accent colour
    bandm = pinm * (np.abs(((y - floor_y) % 1000)) > 0)
    # ball rolls in from the left once per loop
    br = 58
    bx = 120 + (cx - 260 - 120) * t
    by = floor_y - br
    ball = np.clip(br - np.hypot(x - bx, y - by), 0, 1.5) / 1.5
    out -= (np.exp(-(((x - bx) / 75) ** 2 + ((y - floor_y) / 6) ** 2)) * 0.2)[..., None]
    ang = (bx - 120) / br
    holes = np.zeros((H, W))
    for hx, hy in ((-16, -20), (14, -22), (0, 14)):
        rx = bx + hx * np.cos(ang) - hy * np.sin(ang)
        ry = by + hx * np.sin(ang) + hy * np.cos(ang)
        holes = np.maximum(holes, np.clip(9 - np.hypot(x - rx, y - ry), 0, 1))
    shine = np.exp(-(((x - bx + 20) / 16) ** 2 + ((y - by + 24) / 12) ** 2)) * 0.3
    bc = ink + shine[..., None]
    bc = bc * (1 - holes[..., None]) + 0.45 * holes[..., None]
    out = out * (1 - ball[..., None]) + bc * ball[..., None]
    # motion streaks behind the ball, in the accent colour
    for k, off in enumerate((-30, 0, 30)):
        streak = np.exp(-((y - (by + off * 0.8)) / 2.2) ** 2) * np.clip((bx - br - 10 - x) / 200 + 1, 0, 1) * (x < bx - br - 10) * (x > bx - br - 210)
        out = out * (1 - streak[..., None] * 0.9) + np.array(band) * streak[..., None] * 0.9
    return screen_frame(np.clip(out, 0, 1), (0.72, 0.72, 0.75), ink)


# live pins (Common/BwlScene/common.carc WS2_bwl_pin.brres 'bwg_pin', 64x256): (body, blue parts, red parts)
PIN_STYLE = {'cosmic': ((0.97, 0.96, 1.0), (0.2, 0.9, 1.0), (1.0, 0.2, 0.9)),
             'synthwave': ((0.98, 0.95, 0.99), (0.25, 0.85, 1.0), (1.0, 0.25, 0.7)),
             'aurora': ((0.96, 0.98, 1.0), (0.3, 0.95, 0.75), (0.2, 0.55, 1.0)),
             'lava': ((0.98, 0.95, 0.92), (1.0, 0.75, 0.1), (1.0, 0.2, 0.0)),
             'whiteout': ((0.022, 0.022, 0.026), (1.0, 1.0, 1.0), (0.80, 0.80, 0.83))}
# Whiteout colourways (random per Bowling visit): (body, blue parts, red parts), in PIN_WAYS order
WHITEOUT_LIVE = {'onyx': PIN_STYLE['whiteout'],
                 'navy': ((0.05, 0.08, 0.22), (1.0, 0.80, 0.28), (0.95, 0.68, 0.18)),
                 'garnet': ((0.30, 0.025, 0.06), (1.0, 1.0, 1.0), (0.85, 0.82, 0.82)),
                 'forest': ((0.035, 0.16, 0.10), (0.96, 0.86, 0.56), (0.88, 0.74, 0.40))}
LIVE_PIN = os.path.join(ROOT, 'work/stage/common_bwg_pin.png')


def live_pin(theme, way=None):
    """Re-coloured live pin for an alley theme (keeps the shading of the stock texture);
    way = a Whiteout colourway name (WHITEOUT_LIVE)."""
    if not os.path.exists(LIVE_PIN):
        import subprocess
        src = os.path.join(ROOT, 'work/stage/common.d/G3D/WS2_bwl_pin.brres.d/Textures(NW4R)/bwg_pin')
        if not os.path.exists(src):
            tools = os.path.join(ROOT, 'tools/bin')
            d = os.path.join(ROOT, 'work/stage/common.d')
            subprocess.run([os.path.join(tools, 'wszst'), 'extract', os.path.join(ROOT, 'work/disc/files/Common/BwlScene/common.carc'),
                            '-d', d, '-o', '-q'], check=True)
            subprocess.run([os.path.join(tools, 'wszst'), 'extract', os.path.join(d, 'G3D/WS2_bwl_pin.brres'),
                            '-d', os.path.join(d, 'G3D/WS2_bwl_pin.brres.d'), '-o', '-q'], check=True)
        subprocess.run([os.path.join(ROOT, 'tools/bin/wimgt'), 'decode', src, '-d', LIVE_PIN, '-o', '-q'], check=True)
    p = arr(Image.open(LIVE_PIN))[..., :3]
    r, g, b = p[..., 0], p[..., 1], p[..., 2]
    lum = p.mean(2)
    blue = np.clip((b - r) / 0.35, 0, 1)
    red = np.clip((r - b) / 0.35, 0, 1) * np.clip((r - g) / 0.25, 0, 1)
    body = np.clip(1 - blue - red, 0, 1)
    body_c, blue_c, red_c = (np.array(c) for c in (WHITEOUT_LIVE[way] if way else PIN_STYLE[theme]))
    def shade(mask):
        m = mask > 0.5
        ref = lum[m].mean() if m.any() else 1.0
        return np.clip(lum / max(ref, 1e-3), 0.6, 1.25)[..., None]
    out = body[..., None] * body_c * shade(body) + blue[..., None] * blue_c * shade(blue) + red[..., None] * red_c * shade(red)
    if theme == 'whiteout':                       # dark pins: keep a soft highlight down the middle
        x = np.linspace(-1, 1, p.shape[1])[None, :, None]
        out = out + body[..., None] * 0.05 * np.exp(-(x / 0.3) ** 2)
        h = p.shape[0]
        star = np.zeros(lum.shape)
        star[int(h * 0.58):int(h * 0.86)] = 1        # the star sits in the band
        star *= body * np.clip((lum - 0.82) / 0.1, 0, 1)
        out = out * (1 - star[..., None]) + np.array(blue_c if way not in (None, 'onyx') else [0.97, 0.97, 0.99]) * star[..., None]
    return img(out)


CONCEPTS = {'cosmic': cosmic, 'synthwave': synthwave, 'aurora': aurora, 'lava': lava, 'whiteout': whiteout}

if __name__ == '__main__':
    import alley_render as R
    names = sys.argv[1:] or list(CONCEPTS)
    out = os.path.join(ROOT, 'work/stage/concepts')
    os.makedirs(out, exist_ok=True)
    for n in names:
        c = CONCEPTS[n]()
        for k, im in c['tex'].items():
            im.save(os.path.join(out, f'{n}_{k}.png'))
        for cam_name, cam in (('throw', R.CAM_THROW), ('pins', R.CAM_PINS)):
            R.render(c['tex'], cam=cam, W=1920, H=1080).resize((960, 540), Image.LANCZOS).save(
                os.path.join(out, f'{n}_{cam_name}.png'))
        print(n, 'done')
