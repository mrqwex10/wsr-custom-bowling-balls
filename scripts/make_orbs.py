"""Animated Pro orbs. Each design is frame(d, t) -> (rgb, height) for t in [0, 1)
and loops seamlessly. Height is baked into the colours as relief: crests get a
bright edge, crevices go dark (light-direction free, so it looks right however
the ball rolls).

usage: make_orbs.py <name|all> <n_frames>   -> designs/orbs/<name>_<n>/fNN.png (+ .mmK.png)"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from ballmap import directions, to_image
from noise3d import fbm, smoothstep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RW, RH = 512, 256            # render size (2x supersampled)
W, H, N_MIPS = 256, 128, 4
TAU = 2 * np.pi
AXES = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float)


def C(*rgb):
    return np.array(rgb, float) / 255


def lerp(a, b, t):
    t = np.asarray(t, float)
    return a * (1 - t[..., None]) + b * t[..., None] if t.ndim else a * (1 - t) + b * t


def loop(t, r, seed=0):
    ph = seed * 1.618
    return r * np.array([np.cos(TAU * t + ph), np.sin(TAU * t + ph), 0.6 * np.sin(TAU * t + 2 * ph)])


def ramp(x, stops):
    """Piecewise-linear colour ramp; stops = [(pos, rgb), ...]."""
    x = np.clip(x, stops[0][0], stops[-1][0])
    out = np.zeros(x.shape + (3,))
    for (p0, c0), (p1, c1) in zip(stops[:-1], stops[1:]):
        m = (x >= p0) & (x <= p1)
        f = ((x - p0) / max(p1 - p0, 1e-6))[m][:, None]
        out[m] = c0 * (1 - f) + c1 * f
    return out


def relief(col, h, strength=1.0, sigma=5.0, crest=0.55, crest_col=(1, 1, 1)):
    """Bake a height map into the colours (cavity shading + crest highlights)."""
    hb = ndi.gaussian_filter(h, sigma, mode=('nearest', 'wrap'))
    cav = h - hb
    s = cav.std() + 1e-6
    cn = np.clip(cav / s, -3, 3)
    shade = 1 + 0.22 * strength * cn
    col = col * shade[..., None]
    hi = smoothstep(1.2, 2.6, cn) * crest * strength
    col = col + np.array(crest_col, float) * hi[..., None]
    return np.clip(col, 0, 1)


def basis(a):
    up = np.array([0, 1.0, 0]) if abs(a[1]) < 0.9 else np.array([0, 0, 1.0])
    u = np.cross(up, a); u /= np.linalg.norm(u)
    v = np.cross(a, u)
    return u, v


# ------------------------------------------------------------------ plasma globe
def plasma(d, t):
    """From every side you look into the globe: a white-hot electrode in the
    middle and flickering tendrils reaching for the glass. Each side's view
    fades to dark glass before the next, so there are no seams."""
    region = np.argmax(d @ AXES.T, axis=-1)
    glow = np.zeros(d.shape[:2])
    core = np.zeros(d.shape[:2])
    for k, a in enumerate(AXES):
        m = region == k
        if not m.any():
            continue
        u, v = basis(a)
        p = d[m]
        x, y, z = p @ u, p @ v, p @ a
        ang = np.arccos(np.clip(z, -1, 1))
        r = ang / (np.pi / 4)
        az = np.arctan2(y, x)
        sa = np.sin(ang)
        rng = np.random.default_rng(100 + k)
        g = np.zeros(len(p)); c = np.zeros(len(p))
        n_t = 7
        for j in range(n_t):
            base = TAU * (j + rng.uniform(-0.3, 0.3)) / n_t
            sway = 0.45 * np.sin(TAU * t + rng.uniform(0, TAU))
            q = np.stack([r * 2.2, np.full_like(r, j * 3.7 + k * 11.3), np.zeros_like(r)], -1)
            wander = 0.9 * fbm(q + loop(t, 0.5, j + 7 * k), 3, seed=17)
            q2 = np.stack([r * 9.0, np.full_like(r, j * 5.1 + k * 7.7), np.zeros_like(r)], -1)
            jag = 0.10 * fbm(q2 + loop(t, 1.2, j + 3 * k), 2, seed=23)
            path = base + sway + wander + jag
            dphi = np.angle(np.exp(1j * (az - path)))
            dist = np.abs(dphi) * sa
            width = 0.010 + 0.012 * r
            reach = 0.86 + 0.10 * np.sin(TAU * (t + rng.uniform()))
            along = smoothstep(0.06, 0.16, r) * smoothstep(reach, reach - 0.12, r)
            flick = 0.6 + 0.4 * (0.5 + 0.5 * np.sin(TAU * (2 * t + rng.uniform())))
            c += np.exp(-(dist / width) ** 2) * along * flick
            g += np.exp(-(dist / (width * 5)) ** 2) * along * flick
            # bright touch point on the glass at the end of the tendril
            end = np.exp(-((r - reach + 0.04) / 0.05) ** 2) * np.exp(-(dist / 0.05) ** 2)
            g += 0.8 * end * flick
        pulse = 0.9 + 0.1 * np.sin(TAU * 2 * t)
        c += np.exp(-(r / 0.13) ** 2) * 1.5 * pulse
        g += np.exp(-(r / 0.42) ** 2) * 0.45 * pulse
        fade = smoothstep(1.0, 0.80, r)
        glow[m] = g * fade
        core[m] = c * fade
    smoke = 0.5 + 0.5 * fbm(d * 1.8 + loop(t, 0.15, 3), 3, seed=31)
    col = C(10, 5, 24) + C(40, 12, 70) * smoke[..., None] * 0.6
    col = col + C(190, 60, 255) * np.clip(glow, 0, 1.5)[..., None] * 0.75
    col = col + C(255, 215, 255) * np.clip(core, 0, 1.2)[..., None]
    return np.clip(col, 0, 1), None


# ------------------------------------------------------------------ inferno
def inferno(d, t):
    def f(s):
        q = d * 0.85 + np.array([0, -0.65 * s, 0])       # flames rise
        w = np.stack([fbm(q * 0.8, 3, seed=s_) for s_ in (41, 43, 47)], -1)
        return fbm(q * 1.1 + 1.6 * w, 4, gain=0.45, seed=53)
    a, b = f(t), f(t - 1)
    n = ((1 - t) * a + t * b) / np.sqrt((1 - t) ** 2 + t ** 2)  # seamless loop crossfade
    swirl = fbm(d * 0.8 + loop(t, 0.2, 5), 3, seed=59)
    heat = np.clip(0.52 + 1.45 * n + 0.30 * swirl, 0, 1)
    col = ramp(heat, [(0.0, C(30, 6, 20)), (0.3, C(140, 10, 80)), (0.5, C(235, 40, 60)),
                      (0.68, C(255, 120, 20)), (0.85, C(255, 205, 70)), (1.0, C(255, 250, 210))])
    return col, heat


# ------------------------------------------------------------------ toxic slime
def slime(d, t):
    lat = np.arcsin(np.clip(d[..., 1], -1, 1))
    lon = np.arctan2(d[..., 2], d[..., 0])
    goo = fbm(d * 2.0 + loop(t, 0.25, 1), 4, seed=61)
    green = lerp(C(40, 170, 20), C(170, 255, 70), smoothstep(-0.4, 0.5, goo))
    green = green + C(200, 255, 120) * smoothstep(0.35, 0.7, goo)[..., None] * 0.4
    # lavender crust over the top, with holes that show the glowing goo
    edge = 0.12 + 0.18 * fbm(np.stack([d[..., 0] * 1.6, d[..., 2] * 1.6, np.zeros_like(lat)], -1), 3, seed=67)
    crust = smoothstep(edge - 0.05, edge + 0.05, lat)
    holes = smoothstep(0.16, 0.30, fbm(d * 1.5 + 9, 2, seed=71) + 0.05 * np.sin(TAU * t))
    crust = crust * (1 - holes)
    # drips oozing down from the crust edge
    rng = np.random.default_rng(73)
    drips = np.zeros_like(lat)
    for k in range(16):
        lk = rng.uniform(-np.pi, np.pi)
        ek = 0.12 + 0.18 * fbm(np.array([[np.cos(lk) * 1.6, np.sin(lk) * 1.6, 0.0]]), 3, seed=67)[0]
        length = rng.uniform(0.15, 0.55) * (0.8 + 0.2 * np.sin(TAU * (t + rng.uniform())))
        w = rng.uniform(0.035, 0.07)
        dl = np.angle(np.exp(1j * (lon - lk))) * np.cos(lat)
        y = (ek - lat) / length                       # 0 at the edge, 1 at the tip
        taper = w * (1 - 0.55 * np.clip(y, 0, 1)) + w * 0.5 * np.exp(-((y - 1) / 0.12) ** 2)
        drips = np.maximum(drips, smoothstep(taper, taper * 0.6, np.abs(dl)) * (y > -0.1) * (y < 1.12))
    shell = np.clip(crust + drips * (1 - holes), 0, 1)
    # bubbles rising through the goo (one trip per loop -> seamless)
    bub = np.zeros_like(lat)
    for k in range(26):
        lk = rng.uniform(-np.pi, np.pi)
        ph = rng.uniform()
        bl = -1.35 + ((ph + t) % 1.0) * 1.5
        rad = rng.uniform(0.04, 0.09)
        cdir = np.array([np.cos(bl) * np.cos(lk), np.sin(bl), np.cos(bl) * np.sin(lk)])
        ang = np.arccos(np.clip(d @ cdir, -1, 1))
        bub = np.maximum(bub, np.clip(1 - (ang / rad) ** 2, 0, 1))
    lav = lerp(C(150, 130, 210), C(225, 215, 250), smoothstep(-0.3, 0.6, fbm(d * 3, 3, seed=79)))
    col = lerp(green, lav, shell)
    col = col + C(210, 255, 170) * (bub * (1 - shell))[..., None] * 0.5
    h = shell * 1.0 + np.sqrt(bub) * 0.5 * (1 - shell) + 0.15 * goo
    return col, h


# ------------------------------------------------------------------ arcane void
def arcane(d, t):
    pts = np.random.default_rng(83).normal(size=(48, 3))
    pts /= np.linalg.norm(pts, axis=1, keepdims=True)
    q = d + 0.12 * np.stack([fbm(d * 2.0 + loop(t, 0.12, s), 3, seed=s) for s in (87, 89, 97)], -1)
    q /= np.linalg.norm(q, axis=-1, keepdims=True)
    dots = q.reshape(-1, 3) @ pts.T
    dist = np.sqrt(np.clip(2 - 2 * dots, 0, None))
    part = np.partition(dist, 1, axis=1)
    edge = (part[:, 1] - part[:, 0]).reshape(d.shape[:2])
    vein = np.exp(-(edge / 0.022) ** 2)
    halo = np.exp(-(edge / 0.09) ** 2)
    ang = np.arccos(np.clip(d[..., 1], -1, 1))              # 0 at the top
    pulse = 0.5 + 0.5 * np.sin(TAU * (2 * ang / np.pi - t))  # waves of light flowing down the veins
    pulse = 0.3 + 0.7 * pulse ** 2
    neb = smoothstep(-0.1, 0.6, fbm(d * 1.5 + loop(t, 0.2, 9), 4, seed=101))
    col = C(16, 4, 36) + C(90, 30, 160) * neb[..., None] * 0.55
    col = col + C(170, 70, 255) * (halo * pulse)[..., None] * 0.55
    col = col + C(240, 200, 255) * (vein * pulse)[..., None]
    return np.clip(col, 0, 1), vein * 0.8 + neb * 0.2


# ------------------------------------------------------------------ frost shards
def frost(d, t):
    rng = np.random.default_rng(107)
    pts = rng.normal(size=(60, 3)); pts /= np.linalg.norm(pts, axis=1, keepdims=True)
    tilt = rng.normal(size=(60, 3)); tilt /= np.linalg.norm(tilt, axis=1, keepdims=True)
    tint = rng.uniform(0, 1, 60)
    dots = d.reshape(-1, 3) @ pts.T
    cell = dots.argmax(1)
    dist = np.sqrt(np.clip(2 - 2 * dots, 0, None))
    part = np.partition(dist, 1, axis=1)
    edge = (part[:, 1] - part[:, 0]).reshape(d.shape[:2])
    cell = cell.reshape(d.shape[:2])
    L = np.array([np.cos(TAU * t), 0.45, np.sin(TAU * t)]); L /= np.linalg.norm(L)
    glint = np.clip(tilt[cell] @ L, 0, 1) ** 14            # light sweeping round the ball
    base = lerp(C(8, 20, 60), C(40, 110, 200), tint[cell] * 0.7 + 0.3 * smoothstep(-0.4, 0.5, fbm(d * 3, 2, seed=109)))
    col = base + C(180, 240, 255) * glint[..., None] * 0.9
    line = np.exp(-(edge / 0.012) ** 2) * (0.7 + 0.3 * np.sin(TAU * (t + tint[cell])))
    col = col + C(90, 220, 255) * line[..., None] * 0.8
    crack = (1 - np.clip(np.abs(fbm(d * 1.3 + loop(t, 0.18, 4), 2, seed=113)) * 9, 0, 1)) ** 3
    flick = 0.6 + 0.4 * np.sin(TAU * 3 * t)
    col = col + C(200, 250, 255) * (crack * flick)[..., None] * 0.6
    h = smoothstep(0.0, 0.07, edge) + 0.3 * tint[cell]
    return np.clip(col, 0, 1), h


def holo(d, t):
    import make_holo_anim
    return make_holo_anim.frame(d, t), None


DESIGNS = {
    'holo': holo, 'plasma': plasma, 'inferno': inferno,
    'slime': (slime, dict(strength=0.9, sigma=6, crest=0.55)),
    'arcane': (arcane, dict(strength=0.8, sigma=4, crest=0.35, crest_col=(0.9, 0.7, 1.0))),
    'frost': (frost, dict(strength=1.2, sigma=3, crest=0.5, crest_col=(0.8, 0.95, 1.0))),
}
DESIGNS['inferno'] = (inferno, dict(strength=1.0, sigma=5, crest=0.35, crest_col=(1.0, 0.9, 0.6)))
LABELS = {'holo': 'Holographic', 'plasma': 'Plasma Globe', 'inferno': 'Inferno',
          'slime': 'Toxic Slime', 'arcane': 'Arcane Void', 'frost': 'Frost Shards',
          'venom': 'Venom Swirl', 'blackhole': 'Black Hole', 'dragoneye': "Dragon's Eye"}


def render(name, n_frames):
    spec = DESIGNS[name]
    fn, rel = (spec if isinstance(spec, tuple) else (spec, None))
    out = os.path.join(ROOT, 'designs/orbs', f'{name}_{n_frames}')
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        os.remove(os.path.join(out, f))
    d = directions(RW, RH)
    for i in range(n_frames):
        res = fn(d, i / n_frames)
        col, h = res[0], res[1]
        if h is not None and rel:
            col = relief(col, h, **rel)
        if len(res) > 2:                       # glowing parts are not shaded by the relief
            col = np.clip(col + res[2], 0, 1)
        big = to_image(col)
        big.resize((W, H), Image.LANCZOS).save(os.path.join(out, f'f{i:02d}.png'))
        for m in range(1, N_MIPS + 1):
            big.resize((W >> m, H >> m), Image.LANCZOS).save(os.path.join(out, f'f{i:02d}.mm{m}.png'))
    return out





# ================================================================== v4 orbs
def _sphere_pts(n, seed):
    p = np.random.default_rng(seed).normal(size=(n, 3))
    return p / np.linalg.norm(p, axis=1, keepdims=True)


def _fib_pts(n, jitter, seed):
    """Evenly spread points (Fibonacci sphere) with a little jitter."""
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = np.pi * (1 + 5 ** 0.5) * i
    p = np.stack([np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)], -1)
    p = p + jitter * np.random.default_rng(seed).normal(size=p.shape) / np.sqrt(n)
    return p / np.linalg.norm(p, axis=1, keepdims=True)


def _front_polar(d):
    """Angle from the front (+Z) and azimuth around it (0 = right, pi/2 = up)."""
    th = np.arccos(np.clip(d[..., 2], -1, 1))
    ph = np.arctan2(d[..., 1], d[..., 0])
    return th, ph


def _loopx(fn, t):
    """Seamless loop for motion that doesn't naturally repeat: crossfade f(t) with f(t-1)."""
    a, b = fn(t), fn(t - 1)
    w = t
    return ((1 - w) * a + w * b) / np.sqrt((1 - w) ** 2 + w ** 2)


# ------------------------------------------------------------------ venom swirl
def venom(d, t):
    """Gunmetal ball with olive/lime bands coiling around a tilted axis; the bands
    flow along, metallic crests catch the light, lime glints ride the bands."""
    A = np.array([0.35, 1.0, 0.25]); A /= np.linalg.norm(A)
    u, v = basis(A)
    ang = np.arctan2(d @ v, d @ u)
    hgt = d @ A
    warp = fbm(d * 1.1 + loop(t, 0.12, 2), 4, seed=601)
    warp2 = fbm(d * 2.3 + loop(t, 0.10, 6), 3, seed=603)
    field = ang / TAU * 2 + hgt * 1.6 + 1.5 * warp + 0.35 * warp2
    bands = 0.5 + 0.5 * np.sin(TAU * field - TAU * t)              # one band-width of travel per loop
    fine = 0.5 + 0.5 * np.sin(TAU * 3 * field - TAU * 3 * t + 1.3)
    x = np.clip(0.8 * bands + 0.2 * fine, 0, 1)
    x = x ** 1.6                                                    # mostly gunmetal, thinner bands
    col = ramp(x, [(0.0, C(30, 32, 33)), (0.30, C(52, 55, 54)), (0.50, C(75, 72, 45)),
                   (0.68, C(100, 118, 28)), (0.84, C(136, 160, 36)), (0.94, C(185, 200, 70)),
                   (1.0, C(215, 214, 205))])
    brushed = fbm(np.stack([field * 14, hgt * 2, np.zeros_like(hgt)], -1), 2, seed=607)
    col = col * (0.92 + 0.12 * brushed)[..., None]
    glints = np.zeros(d.shape[:2])
    for k, p in enumerate(_sphere_pts(60, 611)):
        a = np.arccos(np.clip(d @ p, -1, 1))
        tw = 0.5 + 0.5 * np.sin(TAU * (t * (1 + k % 3) + k * 0.37))
        glints = np.maximum(glints, np.exp(-(a / 0.03) ** 2) * tw ** 3)
    emit = C(220, 255, 90) * (glints * smoothstep(0.35, 0.7, x))[..., None] * 0.9
    return np.clip(col, 0, 1), x, emit


# ------------------------------------------------------------------ black hole
def blackhole(d, t):
    th, ph = _front_polar(d)
    TH = 0.30                                                      # event horizon (~17 deg)

    def disk(s):
        # differential rotation: inner material whips round faster
        w = 2.2 / np.maximum(th, 0.25) ** 1.2
        rot = ph + w * s
        lg = np.log(np.maximum(th, 0.05))
        arms = 0.5 + 0.5 * np.cos(2 * rot + 3.2 * lg)
        streak = 0.5 + 0.5 * np.cos(9 * rot + 10 * lg)
        q = np.stack([np.cos(rot) * th * 3, np.sin(rot) * th * 3, th * 1.5], -1)
        turb = fbm(q, 4, seed=621)
        return 0.55 * arms + 0.35 * streak ** 3 + 0.7 * turb

    swirl = _loopx(disk, t)
    reach = smoothstep(1.9, 0.9, th)                                # disk fades into space
    inner = smoothstep(TH + 0.01, TH + 0.06, th)
    heat = np.exp(-(th - TH) / 0.55) * reach * inner                 # hotter near the hole
    dopp = 1 + 0.35 * np.cos(ph - 2.6)                              # one side beamed brighter
    I = np.clip(heat * (0.55 + 0.75 * swirl) * dopp, 0, 1.6)
    disk_col = ramp(np.clip(I, 0, 1), [(0.0, C(18, 8, 34)), (0.25, C(60, 31, 78)), (0.45, C(119, 25, 134)),
                                       (0.65, C(201, 5, 146)), (0.82, C(240, 80, 150)), (1.0, C(255, 220, 245))])
    # space behind: nebula in the same colours
    neb = smoothstep(-0.1, 0.6, fbm(d * 1.4 + loop(t, 0.06, 5), 4, seed=631))
    space = C(8, 6, 22) + C(70, 20, 90) * neb[..., None] * 0.6 + C(150, 30, 110) * (neb ** 3)[..., None] * 0.35
    col = lerp(space, disk_col, np.clip(I * 1.6, 0, 1) * reach)
    # twinkling stars
    stars = np.zeros(d.shape[:2])
    for k, p in enumerate(_sphere_pts(320, 641)):
        a = np.arccos(np.clip(d @ p, -1, 1))
        if p[2] > 0.75:
            continue
        tw = 0.35 + 0.65 * (0.5 + 0.5 * np.sin(TAU * (t * (1 + k % 3) + k * 0.61))) ** 2
        stars = np.maximum(stars, np.exp(-(a / (0.008 + 0.006 * (k % 4 == 0))) ** 2) * tw)
    col = col + C(255, 240, 255) * (stars * (1 - np.clip(I, 0, 1)))[..., None]
    # comets streaking across the back of the ball (one pass per loop -> seamless)
    rng = np.random.default_rng(651)
    for k in range(5):
        A = rng.normal(size=3); A[2] = -abs(A[2]) - 0.8; A /= np.linalg.norm(A)
        B = np.cross(A, rng.normal(size=3)); B /= np.linalg.norm(B)
        N = np.cross(A, B)
        s = (rng.uniform() + t) % 1.0
        head = -0.6 + 1.2 * s
        beta = np.arctan2(d @ B, d @ A)
        off = np.abs(d @ N)
        life = np.sin(np.pi * s) ** 0.7
        tail = np.clip((beta - (head - 0.45)) / 0.45, 0, 1) * (beta <= head)
        tail_i = np.exp(-(off / (0.012 + 0.03 * (head - beta).clip(0))) ** 2) * tail ** 1.5
        hd = np.exp(-(((beta - head) / 0.04) ** 2 + (off / 0.04) ** 2))
        col = col + (C(150, 200, 255) * tail_i[..., None] * 0.8 + C(240, 250, 255) * hd[..., None]) * life
    # photon ring + the hole itself
    ring = np.exp(-((th - TH - 0.035) / 0.012) ** 2) * (0.85 + 0.15 * np.sin(TAU * (t + ph / TAU * 2)))
    col = col + C(255, 210, 240) * ring[..., None]
    col = lerp(col, C(0, 0, 2), smoothstep(TH + 0.012, TH - 0.008, th))
    return np.clip(col, 0, 1), None


# ------------------------------------------------------------------ dragon's eye
def dragoneye(d, t):
    th, ph = _front_polar(d)
    TI = 0.62                                                     # iris radius (~35 deg)
    r = th / TI

    # --- iris: fibres of fire flowing outward from the pupil
    def fibres(s):
        q = np.stack([np.cos(ph) * 8, np.sin(ph) * 8, r * 3.0 - 2.4 * s], -1)
        return fbm(q, 4, seed=701)
    fib = _loopx(fibres, t)
    veins = (1 - np.clip(np.abs(fbm(np.stack([np.cos(ph) * 14, np.sin(ph) * 14, r * 5 - 2.5 * t * 0], -1)
                                    + loop(t, 0.3, 3), 3, seed=707)) * 5, 0, 1)) ** 3
    x = np.clip(1 - r + 0.35 * fib, 0, 1)
    iris = ramp(x, [(0.0, C(70, 6, 6)), (0.25, C(170, 25, 10)), (0.5, C(240, 90, 10)),
                    (0.75, C(255, 175, 30)), (1.0, C(255, 240, 150))])
    iris = iris + C(255, 210, 90) * (veins * 0.6)[..., None]
    iris = lerp(iris, C(25, 4, 4), smoothstep(0.80, 1.0, r))          # dark limbal ring
    # --- slit pupil that slowly breathes
    X, Y = th * np.cos(ph), th * np.sin(ph)
    w = TI * (0.12 + 0.07 * np.sin(TAU * t))
    slit = (X / w) ** 2 + (Y / (TI * 0.92)) ** 2
    pupil = smoothstep(1.15, 0.85, slit)
    rim = np.exp(-((slit - 1.0) / 0.35) ** 2) * (1 - pupil)
    iris = iris + C(255, 120, 20) * rim[..., None] * 0.5
    iris = lerp(iris, C(4, 0, 0), pupil)
    # --- dragon scales everywhere else
    pts = _fib_pts(420, 0.35, 711)
    keep = np.arccos(np.clip(pts[:, 2], -1, 1)) > TI + 0.12
    pts = pts[keep]
    dots = d.reshape(-1, 3) @ pts.T
    cell = dots.argmax(1).reshape(d.shape[:2])
    dist = np.sqrt(np.clip(2 - 2 * dots, 0, None))
    part = np.partition(dist, 1, axis=1)
    d1 = part[:, 0].reshape(d.shape[:2])
    edge = (part[:, 1] - part[:, 0]).reshape(d.shape[:2])
    rng = np.random.default_rng(713)
    tint = rng.uniform(0, 1, len(pts))[cell]
    dome = np.sqrt(np.clip(1 - (d1 / 0.16) ** 2, 0, 1))
    bevel = smoothstep(0.0, 0.05, edge)
    scale_h = 0.55 * bevel + 0.45 * dome
    scales = lerp(C(22, 4, 8), C(70, 12, 14), tint * 0.6 + 0.4 * dome)
    scales = scales + C(150, 60, 30) * (dome ** 4)[..., None] * 0.18    # glossy scale tops
    # embers glowing in the cracks, pulsing outward from the eye
    wave = 0.5 + 0.5 * np.sin(TAU * (2 * th / np.pi * 1.5 - t))
    ember = np.exp(-(edge / 0.014) ** 2) * (0.25 + 0.75 * wave ** 2)
    halo = np.exp(-((th - TI) / 0.12) ** 2) * (th > TI)
    m = smoothstep(TI + 0.04, TI - 0.01, th)                       # eye vs scales
    base = scales * (1 - m)[..., None]                              # shaded by the relief
    h = scale_h * (1 - m) + 0.2 * fib * m
    emit = (C(255, 110, 20) * ember[..., None] * 1.0 + C(255, 120, 30) * halo[..., None] * 0.45) * (1 - m)[..., None]
    emit = emit + iris * m[..., None]                               # the eye glows on its own
    return np.clip(base, 0, 1), h, emit


DESIGNS['venom'] = (venom, dict(strength=1.0, sigma=4, crest=0.45, crest_col=(0.95, 0.97, 0.85)))
DESIGNS['blackhole'] = blackhole
DESIGNS['dragoneye'] = (dragoneye, dict(strength=1.5, sigma=4, crest=0.4, crest_col=(1.0, 0.75, 0.5)))
ORDER = ['holo', 'venom', 'inferno', 'blackhole', 'arcane', 'dragoneye']



# ================================================================== v5 orbs
def blackhole2(d, t):
    """Interstellar-style: a black hole on each side wrapped in a glowing lensed
    halo, and a white-hot accretion disk band circling the whole ball (so it's
    visible from every angle) with streaks racing along it."""
    x, y, z = d[..., 0], d[..., 1], d[..., 2]
    th = np.arccos(np.clip(np.abs(z), -1, 1))                   # angle from the nearer hole
    sgn = np.where(z >= 0, 1.0, -1.0)
    ph = np.arctan2(y, x * sgn)                                 # around the hole
    lon = np.arctan2(x, z)                                      # along the disk band
    HR = 0.38

    def halo_tex(s_):
        rot = ph + 3.0 * s_ / np.maximum(th, 0.3)
        q = np.stack([np.cos(rot) * 3, np.sin(rot) * 3, th * 6], -1)
        return 0.5 * (0.5 + 0.5 * np.cos(10 * rot + 6 * th)) + 0.7 * fbm(q, 3, seed=811)

    def band_tex(s_):
        a = lon + 1.6 * s_
        q = np.stack([np.cos(a) * 4, np.sin(a) * 4, y * 22], -1)
        return 0.45 * (0.5 + 0.5 * np.cos(14 * a + 40 * y)) + 0.8 * fbm(q, 4, seed=813)

    halo_n = _loopx(halo_tex, t)
    band_n = _loopx(band_tex, t)
    # background: deep, mostly empty space with sparse twinkling stars
    col = np.zeros(d.shape[:2] + (3,)) + C(4, 2, 12)
    col = col + C(40, 10, 60) * smoothstep(0.2, 0.7, fbm(d * 1.2, 3, seed=815))[..., None] * 0.35
    stars = np.zeros(d.shape[:2])
    for k, p in enumerate(_sphere_pts(220, 817)):
        a = np.arccos(np.clip(d @ p, -1, 1))
        tw = 0.3 + 0.7 * (0.5 + 0.5 * np.sin(TAU * (t * (1 + k % 3) + k * 0.41))) ** 2
        stars = np.maximum(stars, np.exp(-(a / 0.008) ** 2) * tw)
    col = col + C(255, 235, 255) * stars[..., None]
    # lensed halo: the far side of the disk bent up and over the hole
    halo = (np.exp(-((th - HR - 0.07) / 0.05) ** 2) + 0.6 * np.exp(-((th - HR - 0.18) / 0.10) ** 2))
    halo = 1.4 * halo * (0.6 + 0.7 * halo_n) * (1 + 0.35 * np.cos(ph))  # beamed brighter on one side
    halo_c = ramp(np.clip(halo, 0, 1.2) / 1.2, [(0.0, C(30, 8, 50)), (0.3, C(119, 25, 134)), (0.55, C(201, 5, 146)),
                                                (0.75, C(255, 110, 120)), (0.9, C(255, 190, 150)), (1.0, C(255, 245, 235))])
    col = col + halo_c * np.clip(halo, 0, 1)[..., None]
    # event horizon + photon ring
    col = lerp(col, C(0, 0, 0), smoothstep(HR + 0.01, HR - 0.01, th))
    ring = np.exp(-((th - HR - 0.012) / 0.010) ** 2)
    col = col + C(255, 235, 245) * ring[..., None] * 0.9
    # accretion disk band round the equator, passing in front of both holes
    near = np.clip(1 - th / 1.2, 0, 1)                          # hotter / thinner near the holes
    w = 0.075 + 0.075 * (1 - near)
    band = np.exp(-(y / w) ** 2)
    heat = band * (0.75 + 0.8 * band_n) * (0.8 + 0.7 * near) * (1 + 0.3 * np.sin(lon))
    band_c = ramp(np.clip(heat, 0, 1.3) / 1.3, [(0.0, C(30, 8, 50)), (0.25, C(119, 25, 134)), (0.45, C(201, 5, 146)),
                                                 (0.65, C(255, 90, 110)), (0.82, C(255, 170, 120)), (1.0, C(255, 248, 240))])
    a_band = np.clip(heat * 1.4, 0, 1)
    col = lerp(col, band_c, a_band)
    # comets crossing the empty space above and below the disk
    rng = np.random.default_rng(819)
    for k in range(6):
        A = rng.normal(size=3); A[1] = (0.6 + 0.3 * rng.uniform()) * (1 if k % 2 else -1); A /= np.linalg.norm(A)
        B = np.cross(A, rng.normal(size=3)); B /= np.linalg.norm(B)
        N = np.cross(A, B)
        s_ = (rng.uniform() + t) % 1.0
        head = -0.6 + 1.2 * s_
        beta = np.arctan2(d @ B, d @ A)
        off = np.abs(d @ N)
        life = np.sin(np.pi * s_) ** 0.7
        tail = np.clip((beta - (head - 0.45)) / 0.45, 0, 1) * (beta <= head)
        tail_i = np.exp(-(off / (0.012 + 0.03 * (head - beta).clip(0))) ** 2) * tail ** 1.5
        hd = np.exp(-(((beta - head) / 0.04) ** 2 + (off / 0.04) ** 2))
        vis = (1 - a_band) * smoothstep(0.30, 0.45, th)
        col = col + (C(150, 200, 255) * tail_i[..., None] * 0.8 + C(240, 250, 255) * hd[..., None]) * (life * vis)[..., None]
    return np.clip(col, 0, 1), None


def dragoneye2(d, t):
    """Two big dragon eyes on opposite sides, scales and ember-light between."""
    x, y, z = d[..., 0], d[..., 1], d[..., 2]
    th = np.arccos(np.clip(np.abs(z), -1, 1))
    ph = np.arctan2(y, x * np.where(z >= 0, 1.0, -1.0))
    TI = 0.80                                                   # iris radius (~46 deg)
    r = th / TI

    def fibres(s_):
        q = np.stack([np.cos(ph) * 8, np.sin(ph) * 8, r * 3.0 - 2.4 * s_], -1)
        return fbm(q, 4, seed=701)
    fib = _loopx(fibres, t)
    veins = (1 - np.clip(np.abs(fbm(np.stack([np.cos(ph) * 14, np.sin(ph) * 14, r * 5], -1)
                                    + loop(t, 0.3, 3), 3, seed=707)) * 5, 0, 1)) ** 3
    xx = np.clip(1 - r + 0.35 * fib, 0, 1)
    iris = ramp(xx, [(0.0, C(70, 6, 6)), (0.25, C(170, 25, 10)), (0.5, C(240, 90, 10)),
                     (0.75, C(255, 175, 30)), (1.0, C(255, 240, 150))])
    iris = iris + C(255, 210, 90) * (veins * 0.6)[..., None]
    iris = lerp(iris, C(25, 4, 4), smoothstep(0.82, 1.0, r))
    X, Y = th * np.cos(ph), th * np.sin(ph)
    w = TI * (0.12 + 0.07 * np.sin(TAU * t))
    slit = (X / w) ** 2 + (Y / (TI * 0.92)) ** 2
    pupil = smoothstep(1.15, 0.85, slit)
    rim = np.exp(-((slit - 1.0) / 0.35) ** 2) * (1 - pupil)
    iris = iris + C(255, 120, 20) * rim[..., None] * 0.5
    iris = lerp(iris, C(4, 0, 0), pupil)
    pts = _fib_pts(300, 0.35, 711)
    pts = pts[np.arccos(np.clip(np.abs(pts[:, 2]), -1, 1)) > TI + 0.10]
    dots = d.reshape(-1, 3) @ pts.T
    cell = dots.argmax(1).reshape(d.shape[:2])
    dist = np.sqrt(np.clip(2 - 2 * dots, 0, None))
    part = np.partition(dist, 1, axis=1)
    d1 = part[:, 0].reshape(d.shape[:2])
    edge = (part[:, 1] - part[:, 0]).reshape(d.shape[:2])
    tint = np.random.default_rng(713).uniform(0, 1, len(pts))[cell]
    dome = np.sqrt(np.clip(1 - (d1 / 0.17) ** 2, 0, 1))
    scale_h = 0.55 * smoothstep(0.0, 0.05, edge) + 0.45 * dome
    scales = lerp(C(22, 4, 8), C(70, 12, 14), tint * 0.6 + 0.4 * dome)
    scales = scales + C(150, 60, 30) * (dome ** 4)[..., None] * 0.18
    wave = 0.5 + 0.5 * np.sin(TAU * (2 * th / np.pi * 1.5 - t))
    ember = np.exp(-(edge / 0.014) ** 2) * (0.25 + 0.75 * wave ** 2)
    halo = np.exp(-((th - TI) / 0.12) ** 2) * (th > TI)
    m = smoothstep(TI + 0.04, TI - 0.01, th)
    base = scales * (1 - m)[..., None]
    h = scale_h * (1 - m) + 0.2 * fib * m
    emit = (C(255, 110, 20) * ember[..., None] + C(255, 120, 30) * halo[..., None] * 0.45) * (1 - m)[..., None]
    emit = emit + iris * m[..., None]
    return np.clip(base, 0, 1), h, emit


DESIGNS['blackhole'] = blackhole2
DESIGNS['dragoneye'] = (dragoneye2, dict(strength=1.5, sigma=4, crest=0.4, crest_col=(1.0, 0.75, 0.5)))



# ================================================================== tier balls
def _grad(h):
    """Gradient of an equirect height map in tangent space (east, north)."""
    H_, W_ = h.shape
    lat = (0.5 - (np.arange(H_) + 0.5) / H_) * np.pi
    hx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * TAU / W_) / np.maximum(np.cos(lat), 0.05)[:, None]
    hy = np.zeros_like(h)
    hy[1:-1] = (h[:-2] - h[2:]) / (2 * np.pi / H_)
    return hx, hy


def _perturb(d, h, k):
    """Bend the sphere normal by the height map (for metal / gem shading)."""
    hx, hy = _grad(h)
    y = np.array([0, 1.0, 0])
    east = np.cross(y, d); east /= np.maximum(np.linalg.norm(east, axis=-1, keepdims=True), 1e-6)
    north = np.cross(d, east)
    n = d - k * (hx[..., None] * east + hy[..., None] * north)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def _emblem(kind, size=512):
    """Crown emblem as an RGBA height/mask image."""
    from PIL import Image, ImageDraw
    im = Image.new('L', (size, size), 0)
    dr = ImageDraw.Draw(im)
    s = size
    if kind == 'crown':
        pts = [(0.18, 0.70), (0.14, 0.32), (0.33, 0.50), (0.50, 0.22), (0.67, 0.50), (0.86, 0.32), (0.82, 0.70)]
        dr.polygon([(x * s, y * s) for x, y in pts], fill=255)
        dr.rectangle([0.18 * s, 0.72 * s, 0.82 * s, 0.82 * s], fill=255)
        for cx, cy in [(0.14, 0.30), (0.50, 0.20), (0.86, 0.30)]:
            dr.ellipse([(cx - 0.05) * s, (cy - 0.05) * s, (cx + 0.05) * s, (cy + 0.05) * s], fill=255)
    if kind == 'jewels':
        for cx in (0.32, 0.5, 0.68):
            dr.ellipse([(cx - 0.045) * s, 0.575 * s, (cx + 0.045) * s, 0.665 * s], fill=255)
    from PIL import ImageFilter
    im = im.filter(ImageFilter.GaussianBlur(s * 0.006))
    return np.asarray(im, float) / 255


def _decal_mask(d, front, img, ang_deg):
    f = np.array(front, float); f /= np.linalg.norm(f)
    up = np.array([0, 1.0, 0])
    r = np.cross(up, f); r /= np.linalg.norm(r)
    u = np.cross(f, r)
    x, y, z = d @ r, d @ u, d @ f
    ang = np.arccos(np.clip(z, -1, 1))
    s_ = np.hypot(x, y) + 1e-9
    rad = ang / np.radians(ang_deg)
    hgt, wid = img.shape
    from ballmap import bilinear
    v = bilinear(img[..., None], (0.5 + 0.5 * rad * x / s_) * wid - 0.5, (0.5 - 0.5 * rad * y / s_) * hgt - 0.5)[..., 0]
    return v * (rad < 1)


def _flares(d, pts, sizes, bright):
    """Four-point star glints (bright cores with cross-shaped rays)."""
    out = np.zeros(d.shape[:2])
    for p, sz, b in zip(pts, sizes, bright):
        if b <= 0.01:
            continue
        u, v = basis(p)
        x, y, z = d @ u, d @ v, d @ p
        front = z > 0.9
        core = np.exp(-((x * x + y * y) / (sz * 0.35) ** 2))
        rays = np.exp(-(np.abs(x) / (sz * 0.06))) * np.exp(-(np.abs(y) / (sz * 1.6))) + \
               np.exp(-(np.abs(y) / (sz * 0.06))) * np.exp(-(np.abs(x) / (sz * 1.6)))
        out = np.maximum(out, (core + 0.8 * rays) * b * front)
    return np.clip(out, 0, 1.5)


def gold(d, t):
    """Tier 1 (1500): molten gold. Ripples roll out from embossed crowns, a light
    sweeps across the liquid metal, glitter flares twinkle all over."""
    crown = np.maximum(_decal_mask(d, (0, 0, 1), _emblem('crown'), 30), _decal_mask(d, (0, 0, -1), _emblem('crown'), 30))
    jewels = np.maximum(_decal_mask(d, (0, 0, 1), _emblem('jewels'), 30), _decal_mask(d, (0, 0, -1), _emblem('jewels'), 30))
    th = np.arccos(np.clip(np.abs(d[..., 2]), -1, 1))
    flow = fbm(d * 1.6 + 0.6 * np.stack([fbm(d * 1.2 + loop(t, 0.10, s), 2, seed=900 + s) for s in range(3)], -1)
               + loop(t, 0.12, 4), 4, seed=911)
    ripple = 0.5 + 0.5 * np.sin(TAU * (th * 7.0 - 2 * t))           # rings rolling away from the crowns
    ripple = ripple * smoothstep(0.55, 0.62, th)                    # calm around the emblem
    h = 0.55 * flow + 0.22 * ripple + 1.6 * crown - 0.8 * jewels
    n = _perturb(d, h, 0.12)
    # fake studio environment reflected in the metal (soft top light, horizon band)
    env = 0.35 + 0.65 * smoothstep(-0.2, 0.9, n[..., 1]) + 0.45 * np.exp(-((n[..., 1] - 0.05) / 0.12) ** 2)
    ramp_g = ramp(np.clip(env / 1.2, 0, 1), [(0.0, C(60, 30, 5)), (0.35, C(150, 95, 20)), (0.6, C(220, 160, 40)),
                                             (0.8, C(250, 205, 90)), (1.0, C(255, 245, 200))])
    L = np.array([np.cos(TAU * t), 0.35, np.sin(TAU * t)]); L /= np.linalg.norm(L)
    sweep = np.clip((n * L).sum(-1), 0, 1) ** 28                    # moving highlight on the ripples
    col = ramp_g + C(255, 240, 200) * sweep[..., None] * 0.9
    # the crown is polished brighter; set rubies glow
    col = lerp(col, np.clip(col * 1.25 + 0.06, 0, 1), np.clip(crown, 0, 1) * 0.8)
    ruby = C(190, 10, 40) + C(255, 140, 170) * (0.4 + 0.6 * sweep)[..., None]
    col = lerp(col, ruby, np.clip(jewels * 1.3, 0, 1))
    rng = np.random.default_rng(921)
    pts = _sphere_pts(70, 923)
    tw = np.clip(np.sin(TAU * (t * rng.integers(1, 3, 70) + rng.uniform(0, 1, 70))), 0, 1) ** 4
    fl = _flares(d, pts, rng.uniform(0.03, 0.07, 70), tw)
    emit = C(255, 250, 220) * fl[..., None]
    return np.clip(col, 0, 1), None, emit


def diamond(d, t):
    """Tier 2 (2000): prismatic diamond. Big gem facets flash rainbow fire as the
    light circles the ball, brilliant-cut arrows sparkle, star flares burst."""
    rng = np.random.default_rng(941)
    pts = _fib_pts(90, 0.25, 943)
    tilt = pts + 0.55 * rng.normal(size=pts.shape)
    tilt /= np.linalg.norm(tilt, axis=1, keepdims=True)
    rnd = rng.uniform(0, 1, len(pts))
    dots = d.reshape(-1, 3) @ pts.T
    cell = dots.argmax(1).reshape(d.shape[:2])
    dist = np.sqrt(np.clip(2 - 2 * dots, 0, None))
    part = np.partition(dist, 1, axis=1)
    edge = (part[:, 1] - part[:, 0]).reshape(d.shape[:2])
    L = np.array([np.cos(TAU * t), 0.5 * np.sin(TAU * t) + 0.2, np.sin(TAU * t)]); L /= np.linalg.norm(L)
    facing = (tilt[cell] * L).sum(-1)
    gdir = rng.normal(size=pts.shape)
    grad_in = ((d - pts[cell]) * gdir[cell]).sum(-1) * 6           # light gradient across each facet
    bright = np.clip(0.62 + 0.38 * np.abs(facing) + 0.12 * grad_in, 0.3, 1.15)
    # dispersion: every facet throws a different slice of the rainbow, shifting with the light
    hue = np.mod(facing * 1.6 + rnd[cell] + 0.3 * grad_in + t, 1.0)
    fire = np.stack([0.5 + 0.5 * np.cos(TAU * (hue + o)) for o in (0.0, 0.33, 0.67)], -1)
    fire = np.clip(fire * 1.1, 0, 1)
    fire_amt = 0.08 + 0.92 * smoothstep(0.35, 0.85, facing) * (0.5 + 0.5 * rnd[cell])   # fire only where the light hits
    ice = lerp(C(175, 190, 222), C(252, 253, 255), np.clip(bright - 0.35, 0, 1) ** 0.8)
    col = lerp(ice, 0.25 + 0.85 * fire, fire_amt) * bright[..., None]
    # crisp bright facet edges
    col = col + C(255, 255, 255) * np.exp(-(edge / 0.007) ** 2)[..., None] * 0.6
    # brilliant-cut arrows radiating from both 'tables'
    th = np.arccos(np.clip(np.abs(d[..., 2]), -1, 1))
    ph = np.arctan2(d[..., 1], d[..., 0] * np.where(d[..., 2] >= 0, 1, -1))
    arrows = (0.5 + 0.5 * np.cos(8 * ph)) ** 6 * smoothstep(0.75, 0.15, th) * (0.5 + 0.5 * np.sin(TAU * (2 * t - th)))
    col = col + C(200, 230, 255) * arrows[..., None] * 0.45
    h = smoothstep(0.0, 0.03, edge)
    fp = _sphere_pts(40, 947)
    tw = np.clip(np.sin(TAU * (t * rng.integers(1, 4, 40) + rng.uniform(0, 1, 40))), 0, 1) ** 6
    fl = _flares(d, fp, rng.uniform(0.06, 0.14, 40), tw)
    emit = C(255, 255, 255) * fl[..., None]
    return np.clip(col, 0, 1), h, emit


DESIGNS['gold'] = (gold, None)
DESIGNS['diamond'] = (diamond, dict(strength=0.35, sigma=2, crest=0.6, crest_col=(1, 1, 1)))
LABELS.update({'gold': 'Gold (1500)', 'diamond': 'Prismatic Diamond (2000)'})



# ================================================================== Prismatic Diamond v2
def _spectrum(x):
    """0..1 -> red, orange, yellow, green, cyan, blue, violet (vivid)."""
    return np.clip(np.stack([0.5 + 0.5 * np.cos(TAU * (x * 0.85 + o)) for o in (0.0, 0.67, 0.33)], -1) * 1.25 - 0.1, 0, 1)


def _gem_icon(size=512):
    """Brilliant-cut diamond icon: outline + facet lines (mask image)."""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.new('L', (size, size), 0)
    dr = ImageDraw.Draw(im)
    s_ = size
    P = lambda x, y: (x * s_, y * s_)
    crown_top, girdle, culet = 0.24, 0.42, 0.86
    pts = [P(0.30, crown_top), P(0.70, crown_top), P(0.88, girdle), P(0.50, culet), P(0.12, girdle)]
    w = int(s_ * 0.028)
    dr.line(pts + [pts[0]], fill=255, width=w, joint='curve')
    dr.line([P(0.12, girdle), P(0.88, girdle)], fill=255, width=w)
    for x0, x1 in ((0.30, 0.22), (0.43, 0.38), (0.57, 0.62), (0.70, 0.78)):
        dr.line([P(x0, crown_top), P(x1, girdle)], fill=200, width=int(w * 0.7))
    for x in (0.22, 0.38, 0.62, 0.78):
        dr.line([P(x, girdle), P(0.50, culet)], fill=200, width=int(w * 0.7))
    im = im.filter(ImageFilter.GaussianBlur(s_ * 0.004))
    return np.asarray(im, float) / 255


def diamond2(d, t):
    """Tier 2 (2000): bold, high-contrast prismatic diamond with rainbow comet
    trails orbiting the ball, shimmering rainbow fire and a glowing gem emblem."""
    rng = np.random.default_rng(961)
    pts = _fib_pts(72, 0.55, 963)
    tilt = pts + 0.7 * rng.normal(size=pts.shape)
    tilt /= np.linalg.norm(tilt, axis=1, keepdims=True)
    rnd = rng.uniform(0, 1, len(pts))
    dots = d.reshape(-1, 3) @ pts.T
    cell = dots.argmax(1).reshape(d.shape[:2])
    dist = np.sqrt(np.clip(2 - 2 * dots, 0, None))
    part = np.partition(dist, 1, axis=1)
    edge = (part[:, 1] - part[:, 0]).reshape(d.shape[:2])
    L = np.array([np.cos(TAU * t), 0.45, np.sin(TAU * t)]); L /= np.linalg.norm(L)
    facing = (tilt[cell] * L).sum(-1)
    gdir = rng.normal(size=pts.shape)
    grad_in = ((d - pts[cell]) * gdir[cell]).sum(-1) * 6
    v = np.clip(0.5 + 0.55 * facing + 0.2 * grad_in, 0, 1)            # strong light/dark swing
    col = lerp(C(8, 12, 40), C(245, 250, 255), v ** 1.4)
    # dispersion: the rainbow slides across every facet and races with the light
    hue = np.mod(facing * 0.9 + rnd[cell] + 0.45 * grad_in + 2 * t, 1.0)
    fire_amt = np.clip(0.30 + 0.70 * smoothstep(0.15, 0.7, facing), 0, 1) * (0.55 + 0.45 * rnd[cell])
    col = lerp(col, _spectrum(hue) * (0.45 + 0.6 * v[..., None]), fire_amt * 0.8)
    edge_glow = np.exp(-(edge / 0.007) ** 2)
    h = smoothstep(0.0, 0.03, edge)
    emit = C(220, 235, 255) * edge_glow[..., None] * 0.3
    # emblem on both sides: bold glowing brilliant-cut icon, rainbow light inside, spinning rainbow halo
    icon = _gem_icon_bold()
    em_line = np.maximum(_decal_mask(d, (0, 0, 1), icon[0], 34), _decal_mask(d, (0, 0, -1), icon[0], 34))
    em_fill = np.maximum(_decal_mask(d, (0, 0, 1), icon[1], 34), _decal_mask(d, (0, 0, -1), icon[1], 34))
    th = np.arccos(np.clip(np.abs(d[..., 2]), -1, 1))
    ph = np.arctan2(d[..., 1], d[..., 0] * np.where(d[..., 2] >= 0, 1, -1))
    col = col * (1 - 0.65 * np.exp(-(th / 0.55) ** 2))[..., None]     # darker field behind the emblem
    inside = _spectrum(np.mod(d[..., 1] * 1.5 + t, 1.0))
    emit = emit + inside * em_fill[..., None] * 0.55 + C(255, 255, 255) * em_line[..., None]
    halo = np.exp(-((th - 0.68) / 0.045) ** 2)
    emit = emit + _spectrum(np.mod(ph / TAU + t, 1.0)) * halo[..., None] * 0.7
    # prismatic comet trails: wide rainbow ribbons orbiting the ball
    for axis, speed, ph0 in [((0.35, 1.0, 0.2), 1, 0.0), ((1.0, -0.3, 0.6), 1, 0.33), ((-0.4, 0.5, 1.0), 2, 0.7)]:
        N = np.array(axis, float); N /= np.linalg.norm(N)
        A = np.cross(N, [0.3, 0.1, 1.0]); A /= np.linalg.norm(A)
        B = np.cross(N, A)
        off = d @ N
        beta = np.arctan2(d @ B, d @ A)
        behind = np.mod(TAU * (ph0 + speed * t) - beta, TAU)          # 0 at the head
        tail = np.exp(-behind / 2.6) * (behind < TAU * 0.92)
        width = 0.09 + 0.05 * np.clip(behind / 3, 0, 1)
        across = np.clip(off / width * 0.5 + 0.5, 0, 1)
        band = np.exp(-(off / width) ** 4)
        glow = np.exp(-(off / (width * 2.2)) ** 2) * 0.35
        emit = emit + _spectrum(across) * (band * tail * 1.4)[..., None] + C(200, 180, 255) * (glow * tail)[..., None]
        core = np.exp(-((behind / 0.12) ** 2 + (off / 0.05) ** 2))
        emit = emit + C(255, 255, 255) * core[..., None] * 1.4
    fp = _sphere_pts(36, 967)
    tw = np.clip(np.sin(TAU * (t * rng.integers(1, 4, 36) + rng.uniform(0, 1, 36))), 0, 1) ** 5
    fl = _flares(d, fp, rng.uniform(0.07, 0.15, 36), tw)
    emit = emit + C(255, 255, 255) * fl[..., None]
    return np.clip(col, 0, 1), h, emit


def _gem_icon_bold(size=512):
    """(outline mask, fill mask) of a brilliant-cut gem icon."""
    from PIL import Image, ImageDraw, ImageFilter
    s_ = size
    P = lambda x, y: (x * s_, y * s_)
    top, gird, cul = 0.22, 0.42, 0.88
    outline = [P(0.29, top), P(0.71, top), P(0.90, gird), P(0.50, cul), P(0.10, gird)]
    fill = Image.new('L', (s_, s_), 0)
    ImageDraw.Draw(fill).polygon(outline, fill=255)
    line = Image.new('L', (s_, s_), 0)
    dr = ImageDraw.Draw(line)
    w = int(s_ * 0.045)
    dr.line(outline + [outline[0]], fill=255, width=w, joint='curve')
    dr.line([P(0.10, gird), P(0.90, gird)], fill=255, width=w)
    for x0, x1 in ((0.29, 0.21), (0.43, 0.37), (0.57, 0.63), (0.71, 0.79)):
        dr.line([P(x0, top), P(x1, gird)], fill=230, width=int(w * 0.6))
    for x in (0.21, 0.37, 0.63, 0.79):
        dr.line([P(x, gird), P(0.50, cul)], fill=230, width=int(w * 0.6))
    blur = ImageFilter.GaussianBlur(s_ * 0.004)
    return np.asarray(line.filter(blur), float) / 255, np.asarray(fill.filter(blur), float) / 255


DESIGNS['diamond'] = (diamond2, dict(strength=0.6, sigma=2, crest=0.5, crest_col=(1, 1, 1)))


if __name__ == '__main__':
    names = ORDER if sys.argv[1] == 'all' else sys.argv[1].split(',')
    n = int(sys.argv[2])
    for nm in names:
        print('rendered', render(nm, n))
