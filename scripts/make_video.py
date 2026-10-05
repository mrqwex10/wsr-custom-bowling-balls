"""Showcase video for WSR Custom Bowling Balls - renders every frame from the mod's real
textures (same art that ships), adds a self-made synth soundtrack, encodes MP4.
usage: make_video.py [--preview]   (preview renders a few stills only)"""
import os, sys, math, wave, subprocess, shutil
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from ballmap import bilinear
from build2 import game_grade
from make_pool import POOL
from make_orbs import ORDER, LABELS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'work/video')
W, H, FPS = 1920, 1080, 30
TAU = 2 * np.pi
FB = '/System/Library/Fonts/Supplemental/Arial Black.ttf'
FR = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
_fonts = {}


def font(path, size):
    k = (path, size)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(path, size)
    return _fonts[k]


# ------------------------------------------------------------------ assets
def load_anim(name):
    return [np.asarray(game_grade(Image.open(os.path.join(ROOT, 'designs/orbs', f'{name}_16', f'f{i:02d}.png'))), float) / 255
            for i in range(16)]


def load_pool(name):
    im = Image.open(os.path.join(ROOT, 'designs/pool', name + '.png')).convert('RGB').resize((512, 256), Image.LANCZOS)
    return [np.asarray(game_grade(im), float) / 255]


POOL_NAMES = {'riptide': 'Riptide', 'galaxy': 'Galaxy', 'tiedye': 'Tie-Dye', 'hyperspin': 'Hyperspin', 'smiley': 'Smiley',
              'emerald420': 'Emerald 420', 'stainedglass': 'Stained Glass', 'synthwave': 'Synthwave'}
ORB_TAG = {'holo': 'liquid chrome that never sits still', 'venom': 'gunmetal coils of toxic green',
           'inferno': 'a fireball you can bowl with', 'blackhole': 'an accretion disk wrapped round the ball',
           'arcane': 'veins of light pulsing through the void', 'dragoneye': 'it looks back at you'}


# ------------------------------------------------------------------ ball renderer (RGBA, anti-aliased)
def render_ball(tex, size, yaw, pitch=0.12, light=(-0.45, 0.6, 0.65)):
    S = size
    yy, xx = np.mgrid[0:S, 0:S]
    sx = (xx + 0.5) / S * 2 - 1
    sy = 1 - (yy + 0.5) / S * 2
    rr = sx * sx + sy * sy
    sz = np.sqrt(np.clip(1 - rr, 0, 1))
    n = np.stack([sx, sy, sz], -1)
    cy, syw = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)
    Ry = np.array([[cy, 0, syw], [0, 1, 0], [-syw, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    o = n @ (Rx @ Ry)
    lat = np.arcsin(np.clip(o[..., 1], -1, 1))
    lon = np.arctan2(o[..., 2], o[..., 0])
    th, tw = tex.shape[:2]
    u = ((np.radians(270) - lon) / TAU) % 1.0
    v = 0.5 - lat / np.pi
    t2 = np.concatenate([tex, tex[:, :1]], 1)
    col = bilinear(t2, u * tw - 0.5, v * th - 0.5)
    L = np.array(light); L /= np.linalg.norm(L)
    ndl = np.clip(n @ L, 0, 1)[..., None]
    Hh = L + np.array([0, 0, 1.0]); Hh /= np.linalg.norm(Hh)
    spec = (np.clip(n @ Hh, 0, 1) ** 80)[..., None] * 0.65 + (np.clip(n @ Hh, 0, 1) ** 12)[..., None] * 0.08
    fres = ((1 - sz) ** 3)[..., None] * 0.25
    img = col * (0.42 + 0.68 * ndl) + spec + fres * np.array([0.7, 0.75, 1.0])
    a = np.clip((1 - np.sqrt(rr)) * S * 0.5, 0, 1)
    rgba = np.dstack([np.clip(img, 0, 1), a])
    return Image.fromarray((rgba * 255).astype(np.uint8), 'RGBA')


def frame_of(anim, t, fps=15):
    return anim[int(t * fps) % len(anim)]


# ------------------------------------------------------------------ backgrounds / compositing
def background(t, hue=(0.10, 0.06, 0.20)):
    yy, xx = np.mgrid[0:H, 0:W]
    cx, cy = W / 2, H * 0.55
    r = np.hypot((xx - cx) / W, (yy - cy) / H)
    base = np.array(hue)[None, None, :] * (1.15 - 1.1 * r)[..., None]
    glow = np.exp(-(r / 0.35) ** 2)[..., None] * np.array(hue) * 0.9
    img = np.clip(base + glow, 0, 1)
    return Image.fromarray((img * 255).astype(np.uint8), 'RGB').convert('RGBA')


_bg_cache = {}


def bg(hue):
    if hue not in _bg_cache:
        _bg_cache[hue] = background(0, hue)
    return _bg_cache[hue].copy()


def place_ball(canvas, ball, cx, cy, shadow=True, glow=None):
    s = ball.width
    if glow is not None:
        g = Image.new('RGBA', (int(s * 1.8), int(s * 1.8)), (0, 0, 0, 0))
        dg = ImageDraw.Draw(g)
        dg.ellipse([s * 0.2, s * 0.2, s * 1.6, s * 1.6], fill=glow + (110,))
        g = g.filter(ImageFilter.GaussianBlur(s * 0.18))
        canvas.alpha_composite(g, (int(cx - g.width / 2), int(cy - g.height / 2)))
    if shadow:
        sh = Image.new('RGBA', (int(s * 1.4), int(s * 0.35)), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([s * 0.15, s * 0.05, s * 1.25, s * 0.3], fill=(0, 0, 0, 150))
        sh = sh.filter(ImageFilter.GaussianBlur(s * 0.05))
        canvas.alpha_composite(sh, (int(cx - sh.width / 2), int(cy + s * 0.42)))
    canvas.alpha_composite(ball, (int(cx - s / 2), int(cy - s / 2)))


def text(canvas, xy, s, size, fill=(255, 255, 255), bold=True, alpha=1.0, anchor='mm', shadow=True):
    if alpha <= 0.01:
        return
    f = font(FB if bold else FR, size)
    x0, y0, x1, y1 = (int(math.floor(v)) for v in ImageDraw.Draw(canvas).textbbox(xy, s, font=f, anchor=anchor))
    x1, y1 = x1 + 1, y1 + 1
    pad = 10
    layer = Image.new('RGBA', (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    o = (xy[0] - x0 + pad, xy[1] - y0 + pad)
    if shadow:
        d.text((o[0] + 3, o[1] + 4), s, font=f, anchor=anchor, fill=(0, 0, 0, int(160 * alpha)))
    d.text(o, s, font=f, anchor=anchor, fill=tuple(fill) + (int(255 * alpha),))
    canvas.alpha_composite(layer, (int(x0 - pad), int(y0 - pad)))


def ease(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def fade_in_out(t, dur, fi=0.4, fo=0.4):
    return min(ease(t / fi) if fi else 1, ease((dur - t) / fo) if fo else 1)


# ------------------------------------------------------------------ scenes
class Assets:
    def __init__(self):
        self.orbs = {n: load_anim(n) for n in ORDER}
        self.gold = load_anim('gold')
        self.dia = load_anim('diamond')
        self.pool = {n: load_pool(n) for n in POOL}
        self.alleys = load_alleys()


def scene_title(A, t, dur):
    c = bg((0.10, 0.06, 0.22))
    heroes = [('blackhole', A.orbs['blackhole']), ('holo', A.orbs['holo']), ('gold', A.gold),
              ('diamond', A.dia), ('dragoneye', A.orbs['dragoneye'])]
    appear = ease((t - 0.3) / 1.2)
    for k, (n, anim) in enumerate(heroes):
        sz = 300 if n in ('gold', 'diamond') else 250
        x = W / 2 + (k - 2) * 330
        y = H * 0.62 + 30 * (1 - appear) + 12 * math.sin(TAU * (t * 0.4 + k * 0.2))
        ball = render_ball(frame_of(anim, t), sz, math.pi / 2 + 0.5 * math.sin(TAU * t / 6 + k))
        ball.putalpha(ball.getchannel('A').point(lambda a: int(a * appear)))
        place_ball(c, ball, x, y)
    a = ease((t - 0.8) / 1.0) * fade_in_out(t, dur, 0, 0.5)
    text(c, (W / 2, 190), 'WSR CUSTOM BOWLING BALLS', 104, (255, 236, 200), alpha=a)
    text(c, (W / 2, 300), 'New balls, animated alleys and a ball trail for Wii Sports Resort', 48, (225, 220, 255), bold=False, alpha=a)
    a2 = ease((t - 2.0) / 0.8) * fade_in_out(t, dur, 0, 0.5)
    text(c, (W / 2, H - 90), 'animated alleys  •  Pro orbs  •  Gold & Prismatic Diamond  •  random balls', 38, (190, 190, 215), bold=False, alpha=a2)
    return c


def scene_card(title, sub, hue):
    def f(A, t, dur):
        c = bg(hue)
        a = fade_in_out(t, dur, 0.3, 0.3)
        s = 1 + 0.04 * ease(t / dur)
        text(c, (W / 2, H / 2 - 30), title, int(110 * s), (255, 245, 225), alpha=a)
        text(c, (W / 2, H / 2 + 75), sub, 44, (210, 210, 235), bold=False, alpha=a)
        return c
    return f


def scene_spotlight(name, anim, label, tag, hue, glow, big=560):
    def f(A, t, dur):
        c = bg(hue)
        a = fade_in_out(t, dur, 0.35, 0.35)
        yaw = math.pi / 2 + 0.5 * math.sin(TAU * t / 5.0)              # feature side stays toward the camera
        ball = render_ball(frame_of(anim, t), big, yaw, pitch=0.15 + 0.08 * math.sin(t))
        ball.putalpha(ball.getchannel('A').point(lambda v: int(v * a)))
        place_ball(c, ball, W / 2, H * 0.47, glow=glow)
        text(c, (W / 2, H - 175), label, 72, (255, 255, 255), alpha=a)
        text(c, (W / 2, H - 100), tag, 38, (205, 205, 230), bold=False, alpha=a)
        return c
    return f


def scene_pool(A, t, dur):
    c = bg((0.06, 0.10, 0.20))
    a = fade_in_out(t, dur, 0.4, 0.4)
    text(c, (W / 2, 95), 'A random ball for every non-Pro player', 54, (240, 240, 255), alpha=a)
    for k, n in enumerate(POOL):
        col, row = k % 4, k // 4
        x = W / 2 + (col - 1.5) * 420
        y = 340 + row * 400
        app = ease((t - 0.15 * k) / 0.6) * a
        ball = render_ball(A.pool[n][0], 260, math.pi / 2 + t * 0.9 + k, pitch=0.2)
        ball.putalpha(ball.getchannel('A').point(lambda v: int(v * app)))
        place_ball(c, ball, x, y)
        text(c, (x, y + 185), POOL_NAMES[n], 34, (230, 230, 245), alpha=app)
    return c


def scene_orb_grid(A, t, dur):
    c = bg((0.12, 0.05, 0.20))
    a = fade_in_out(t, dur, 0.4, 0.5)
    text(c, (W / 2, 95), 'Pro rank: random orb each game  -  or pick your favourite', 46, (240, 235, 255), alpha=a)
    for k, n in enumerate(ORDER):
        col, row = k % 3, k // 3
        x = W / 2 + (col - 1) * 520
        y = 360 + row * 400
        ball = render_ball(frame_of(A.orbs[n], t), 270, math.pi / 2 + 0.6 * math.sin(TAU * t / 5 + k), pitch=0.15)
        ball.putalpha(ball.getchannel('A').point(lambda v: int(v * a)))
        place_ball(c, ball, x, y)
        text(c, (x, y + 190), LABELS[n], 34, (230, 230, 245), alpha=a)
    return c


def scene_install(A, t, dur):
    c = bg((0.07, 0.07, 0.14))
    a = fade_in_out(t, dur, 0.4, 0.4)
    text(c, (W / 2, 170), 'Easy install', 90, (255, 240, 215), alpha=a)
    lines = ['1.  Copy two folders to your SD card',
             '2.  Open Wii Sports Resort in Riivolution / Friivolution',
             '3.  Ball mod:  "Pro: random orb each game"',
             '4.  Alley:  "Random"   Ball trail:  "Match ball (Auto)"',
             '5.  Earned it?  Set your Pro ball tier to Gold or Diamond']
    for i, l in enumerate(lines):
        ai = ease((t - 0.4 - 0.45 * i) / 0.5) * a
        text(c, (300, 330 + i * 105), l, 48, (225, 225, 245), bold=False, alpha=ai, anchor='lm')
    text(c, (W / 2, H - 90), 'Wii Sports Resort (USA)  •  no save data touched', 34, (160, 160, 190), bold=False, alpha=a)
    return c


def scene_end(A, t, dur):
    c = bg((0.10, 0.06, 0.22))
    a = ease(t / 0.6)
    for k, (anim, x) in enumerate([(A.gold, W / 2 - 330), (A.dia, W / 2 + 330)]):
        ball = render_ball(frame_of(anim, t), 300, math.pi / 2 + 0.5 * math.sin(TAU * t / 6 + k * 2), pitch=0.15)
        ball.putalpha(ball.getchannel('A').point(lambda v: int(v * a)))
        place_ball(c, ball, x, H * 0.48, glow=(255, 210, 120) if k == 0 else (190, 170, 255))
    text(c, (W / 2, 150), 'WSR CUSTOM BOWLING BALLS', 96, (255, 236, 200), alpha=a)
    text(c, (W / 2, H * 0.48), 'v2.0', 44, (210, 210, 235), bold=False, alpha=a)
    text(c, (W / 2, H - 230), 'github.com/mrqwex10/wsr-custom-bowling-balls', 46, (225, 225, 255), bold=False, alpha=a)
    text(c, (W / 2, H - 150), 'made by qwex10', 40, (180, 180, 210), bold=False, alpha=a)
    return c


ALLEY_TAG = {'cosmic': 'blacklight bowling in deep space', 'synthwave': 'an 80s neon grid at sunset',
             'aurora': 'frozen lanes under the northern lights', 'lava': 'lava flows down the lane',
             'whiteout': 'a bright alley with dark pins'}
ALLEY_SRC = (2304, 1296)


def load_alleys():
    """{theme: {'throw': [frames], 'pins': [frames]}} rendered from the decoded release alley files (cached)."""
    import alley_render as R
    import build_alley as BA
    import verify_alley as VA
    out = {}
    cache = os.path.join(OUT, 'alley')
    os.makedirs(cache, exist_ok=True)
    for theme, _, _ in BA.THEMES:
        out[theme] = {}
        tex = None
        for cam_name, cam in (('throw', R.CAM_THROW), ('pins', R.CAM_PINS)):
            frames = []
            for k in range(8):
                p = os.path.join(cache, f'{theme}_{cam_name}_{k}.png')
                if not os.path.exists(p):
                    if tex is None:
                        tmp = os.path.join(OUT, 'alley_tex', theme)
                        shutil.rmtree(tmp, ignore_errors=True)
                        os.makedirs(tmp)
                        tex = VA.textures(os.path.join(BA.OUT_DIR, theme + '.carc'), tmp)
                    cur = {n: v[k % len(v)] for n, v in tex.items()}
                    R.render(cur, cam=cam, W=3072, H=1728).resize(ALLEY_SRC, Image.LANCZOS).save(p)
                frames.append(Image.open(p).convert('RGB'))
            out[theme][cam_name] = frames
    return out


def scene_alley(theme, label):
    def f(A, t, dur):
        half = dur / 2
        cam = 'throw' if t < half else 'pins'
        tt = t if t < half else t - half
        fr = A.alleys[theme][cam][int(t * 7) % 8]
        z = 1.0 + 0.07 * ease(tt / half)                     # slow push-in
        sw, sh = ALLEY_SRC[0] / z / 1.2, ALLEY_SRC[1] / z / 1.2
        cx, cy = ALLEY_SRC[0] / 2, ALLEY_SRC[1] / 2
        c = fr.crop((int(cx - sw / 2), int(cy - sh / 2), int(cx + sw / 2), int(cy + sh / 2))).resize((W, H), Image.LANCZOS)
        a = fade_in_out(t, dur, 0.3, 0.3)
        if a < 1:
            c = Image.blend(Image.new('RGB', (W, H), (0, 0, 0)), c, a)
        shade = Image.new('RGBA', (W, 230), (0, 0, 0, 0))
        g = np.linspace(0, 170, 230).astype(np.uint8)
        shade.putalpha(Image.fromarray(np.repeat(g[:, None], W, 1)))
        c = c.convert('RGBA')
        c.alpha_composite(shade, (0, H - 230))
        text(c, (90, H - 120), label.upper(), 76, (255, 255, 255), alpha=a, anchor='lm')
        text(c, (92, H - 55), ALLEY_TAG[theme], 38, (215, 215, 235), bold=False, alpha=a, anchor='lm')
        return c
    return f


def timeline(A):
    import build_alley as BA
    T = [(scene_title, 6.0),
         (scene_card('NEW: ALLEY THEMES', 'five animated alleys  -  or let Random pick one', (0.10, 0.04, 0.16)), 2.6)]
    for theme, label, _ in BA.THEMES:
        T.append((scene_alley(theme, label), 4.2))
    T += [(scene_card('PLUS: BALL TRAIL', 'a particle trail made for every ball', (0.05, 0.06, 0.14)), 2.6),
          (scene_card('ANIMATED PRO ORBS', 'for players at Pro rank (1000+ skill)', (0.12, 0.05, 0.20)), 2.4)]
    hues = {'holo': ((0.10, 0.06, 0.22), (200, 150, 255)), 'venom': ((0.06, 0.08, 0.05), (170, 210, 60)),
            'inferno': ((0.16, 0.05, 0.04), (255, 120, 40)), 'blackhole': ((0.06, 0.03, 0.12), (220, 60, 200)),
            'arcane': ((0.08, 0.03, 0.16), (170, 80, 255)), 'dragoneye': ((0.14, 0.04, 0.03), (255, 110, 30))}
    for n in ORDER:
        T.append((scene_spotlight(n, A.orbs[n], LABELS[n], ORB_TAG[n], *hues[n]), 3.2))
    T += [(scene_orb_grid, 4.5),
          (scene_card('EVERYONE ELSE', '8 designs, a new one every time Bowling loads', (0.06, 0.10, 0.20)), 2.4),
          (scene_pool, 6.5),
          (scene_card('PRESTIGE TIERS', 'unlock them as your skill climbs', (0.12, 0.09, 0.03)), 2.6),
          (scene_spotlight('gold', A.gold, 'GOLD', '1500 skill  -  molten gold, crowned', (0.12, 0.08, 0.02), (255, 200, 90), 600), 5.0),
          (scene_card('...AND AT 2000', 'the rarest ball in the game', (0.06, 0.06, 0.14)), 2.2),
          (scene_spotlight('diamond', A.dia, 'PRISMATIC DIAMOND', '2000 skill  -  rainbow fire and comet trails', (0.06, 0.05, 0.14), (190, 170, 255), 640), 6.5),
          (scene_install, 6.0),
          (scene_end, 6.0)]
    return T


# ------------------------------------------------------------------ soundtrack (synthesised here, royalty free)
def soundtrack(seconds, path, sr=44100):
    t = np.arange(int(seconds * sr)) / sr
    bpm = 100
    beat = 60 / bpm
    bar = beat * 4
    def note(n):
        return 440.0 * 2 ** ((n - 69) / 12)
    prog = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]       # Am F C G
    out = np.zeros_like(t)
    # warm pad
    for i, chord in enumerate(prog * 20):
        t0 = i * bar
        if t0 > seconds:
            break
        m = (t >= t0) & (t < t0 + bar + 0.4)
        tt = t[m] - t0
        env = np.clip(tt / 0.35, 0, 1) * np.clip((bar + 0.4 - tt) / 0.4, 0, 1)
        for nn in chord:
            for det in (-0.12, 0.12):
                f = note(nn) * 2 ** (det / 12)
                out[m] += 0.05 * env * (np.sin(TAU * f * tt) + 0.3 * np.sin(TAU * 2 * f * tt))
    # sparkly arpeggio (starts after the title)
    rng = np.random.default_rng(3)
    step = beat / 2
    for k in range(int(seconds / step)):
        t0 = k * step
        if t0 < 5.5 or t0 > seconds - 3:
            continue
        chord = prog[int(t0 / bar) % 4]
        nn = chord[[0, 1, 2, 1][k % 4]] + 12 + (12 if k % 8 >= 6 else 0)
        m = (t >= t0) & (t < t0 + 0.6)
        tt = t[m] - t0
        out[m] += 0.07 * np.exp(-tt * 7) * np.sin(TAU * note(nn) * tt) * (1 + 0.3 * np.sin(TAU * 3 * note(nn) * tt))
    # soft kick + hat once the orbs start
    for k in range(int(seconds / beat)):
        t0 = k * beat
        if t0 < 8.4 or t0 > seconds - 4:
            continue
        m = (t >= t0) & (t < t0 + 0.25)
        tt = t[m] - t0
        out[m] += 0.22 * np.exp(-tt * 18) * np.sin(TAU * (50 + 90 * np.exp(-tt * 30)) * tt)
        mh = (t >= t0 + beat / 2) & (t < t0 + beat / 2 + 0.05)
        out[mh] += 0.03 * np.exp(-(t[mh] - t0 - beat / 2) * 90) * rng.normal(size=mh.sum())
    out *= np.clip(t / 1.5, 0, 1) * np.clip((seconds - t) / 3.0, 0, 1)
    out = out / (np.abs(out).max() + 1e-9) * 0.8
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main():
    preview = '--preview' in sys.argv
    os.makedirs(OUT, exist_ok=True)
    fdir = os.path.join(OUT, 'frames')
    if not preview:
        shutil.rmtree(fdir, ignore_errors=True)
    os.makedirs(fdir, exist_ok=True)
    A = Assets()
    T = timeline(A)
    total = sum(d for _, d in T)
    if preview:
        stills = []
        acc = 0
        for fn, dur in T:
            stills.append(fn(A, dur * 0.55, dur).convert('RGB').resize((640, 360), Image.LANCZOS))
            acc += dur
        sheet = Image.new('RGB', (640 * 4, 360 * ((len(stills) + 3) // 4)))
        for i, s in enumerate(stills):
            sheet.paste(s, ((i % 4) * 640, (i // 4) * 360))
        sheet.save(os.path.join(OUT, 'storyboard.jpg'), quality=85)
        print('storyboard', total, 's')
        return
    idx = 0
    for fn, dur in T:
        n = int(round(dur * FPS))
        for i in range(n):
            fn(A, i / FPS, dur).convert('RGB').save(os.path.join(fdir, f'{idx:05d}.png'), compress_level=1)
            idx += 1
    wav = os.path.join(OUT, 'music.wav')
    soundtrack(idx / FPS, wav)
    mp4 = os.path.join(ROOT, 'previews', 'WSR_Custom_Bowling_Balls_showcase.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(fdir, '%05d.png'),
                    '-i', wav, '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', mp4], check=True)
    print(mp4, idx, 'frames', round(idx / FPS, 1), 's')


if __name__ == '__main__':
    main()
