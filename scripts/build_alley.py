"""Build themed Bowling alleys (Stage/BwlScene/Normal.carc replacements).

    python scripts/build_alley.py [theme ...]   -> output/WSR_ball_mod/alley/<theme>.carc

Each theme = new textures (scripts/make_alley.py) packed into bwg_field.brres with the
original formats / mip counts, animated textures tagged BANM for the GXLoadTexObj hook
(frames follow the first image, each a full mip chain), and tinted scene lights
(SCN0 'RPScene' in bwg_field_rsca.brres) for mood lighting.
"""
import os, sys, shutil, struct
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
import build as v1
import build2 as b2
import make_alley as M

ROOT = v1.ROOT
ORIG = os.path.join(ROOT, 'work/disc/files/Stage/BwlScene/Normal.carc')
WORK = os.path.join(ROOT, 'work/build/alley')
OUT_DIR = os.path.join(v1.OUT, v1.MOD_DIR, 'alley')
FIELD = 'G3D/bwg_field.brres'
RSCA = 'G3D/bwg_field_rsca.brres'
SCN0 = 'AnmScn(NW4R)/RPScene'
FMT = {1: 'I8', 3: 'IA8', 5: 'RGB5A3', 6: 'RGBA32', 14: 'CMPR'}

# (theme, menu label, disc file name used by the Random/Next loader)
THEMES = [('cosmic', 'Cosmic Glow', 'Cosmic.carc'),
          ('synthwave', 'Synthwave Sunset', 'Synthwave.carc'),
          ('aurora', 'Aurora Ice', 'Aurora.carc'),
          ('lava', 'Lava Forge', 'Lava.carc'),
          ('whiteout', 'Whiteout', 'Whiteout.carc')]

# diagnostic builds (not in Random / Next): (folder, base theme, menu label)
TESTS = []   # (diagnostic builds used while finding the hang: ('cosmic_still', 'cosmic', label), ('stock_repack', 'stock', label))

# animation speed: 1/60 s per frame
PERIOD = {'bwg_screen_2': 9, 'gater': 6, 'floor': 7}
ANIM_SIZE = {'bwg_screen_2': (512, 256), 'floor': (64, 128)}   # animation frames at reduced size
# Every theme must be NO BIGGER than the stock alley (unpacked and on disc) - bigger alleys hung the game
# after 1-2 restarts. Room for the animations comes from textures that are invisible or barely visible:
SHRINK = {'mark': (128, 256),                  # lane arrows (348 KB -> 87 KB; seen from far away)
          'test_111_kan': (8, 8),              # not used by any material
          'bwg_screen_tekari_2': (128, 64),    # soft glare layer on the screens
          'ue_kan05': (8, 8),                  # ceiling overlay (the themes use a flat grey)
          'back_roof_2': (256, 256),           # wall behind the bowler
          'bwg_screen_alpha2': (256, 128),     # the screens' reflection in the lane
          'dust_table': (128, 64)}             # the tables by the seats behind the bowler

# mood lighting: (ambient rgb, main light rgb); stock is ambient 100,100,100 + white lights
LIGHT = {'cosmic': ((78, 62, 118), (215, 190, 255)),
         'synthwave': ((112, 58, 112), (255, 200, 235)),
         'aurora': ((70, 96, 124), (205, 230, 255)),
         'lava': ((118, 66, 46), (255, 205, 160)),
         'whiteout': ((112, 112, 116), (255, 255, 255))}


def tex0_info(path):
    b = open(path, 'rb').read()
    w, h = struct.unpack_from('>HH', b, 0x1C)
    fmt, imgs = struct.unpack_from('>II', b, 0x20)
    return w, h, fmt, imgs


def encode(im, fmt, n_images, tmp, key, size=None):
    """PIL image -> (64-byte TEX0 header, image data incl. mips)."""
    if size:
        im = im.resize(size, Image.LANCZOS)
    w, h = im.size
    n_mm = max(0, min(n_images - 1, (min(w, h).bit_length() - 1) - 2))
    png = os.path.join(tmp, key + '.png')
    im.save(png)
    dest = os.path.join(tmp, key + '.tex0')
    args = [v1.WIMGT, 'encode', png, '-x', 'TEX.' + FMT[fmt], '-d', dest, '-o', '-q']
    args += ['--n-mm', str(n_mm)] if n_mm else ['--n-mm', '0', '--no-mipmaps']
    v1.run(*args)
    b = open(dest, 'rb').read()
    size_ = struct.unpack_from('>I', b, 4)[0]
    assert b[:4] == b'TEX0' and struct.unpack_from('>i', b, 0x10)[0] == 0x40
    return b[:0x40], b[0x40:size_]


def pick_format(orig_fmt, im):
    if orig_fmt == 14 and im.mode == 'RGBA':
        return 5
    if orig_fmt in (1, 3) and im.mode in ('RGB', 'RGBA'):   # LA/L originals we re-coloured
        return 5
    return orig_fmt


def tint_lights(rsca_path, theme):
    """Patch the light colours in place inside the ORIGINAL bwg_field_rsca.brres.
    (Never repack it: wszst rebuilds its string pool and the SCN0 light-set name
    references then point at the wrong strings - that hung the game on the Wii.)"""
    amb, light = LIGHT[theme]
    b = bytearray(open(rsca_path, 'rb').read())
    base = b.index(b'SCN0')
    assert b.count(b'SCN0') == 1
    amb_offs = [0x2ac, 0x2c8, 0x2e4]
    light_offs = [0x318, 0x374, 0x3d0]
    for o in amb_offs:
        o += base
        assert b[o:o + 4] == bytes([100, 100, 100, 0]), (hex(o), b[o:o + 4].hex())
        b[o:o + 3] = bytes(amb)
    for o in light_offs:
        o += base
        assert b[o:o + 4] == b'\xff\xff\xff\xff', (hex(o), b[o:o + 4].hex())
        b[o:o + 3] = bytes(light)
    open(rsca_path, 'wb').write(b)


def check_tags(brres_path, expect):
    b = open(brres_path, 'rb').read()
    found = {}
    i = 0
    while (i := b.find(b'TEX0', i)) >= 0:
        if b[i + 0x30:i + 0x34] == b'BANM':
            assert i % 32 == 0, f'tagged TEX0 not 32-byte aligned at {i:#x}'
            found[i] = struct.unpack_from('>HHIi', b, i + 0x34)
        i += 4
    assert len(found) == expect, (len(found), expect)
    return found


def build_theme(theme, base=None):
    """base given = diagnostic 'still' build: no animation frames, every texture at its stock size."""
    still = base is not None
    work = os.path.join(WORK, theme)
    if os.path.exists(work):
        shutil.rmtree(work)
    carc_d = os.path.join(work, 'Normal.d')
    v1.run(v1.WSZST, 'extract', ORIG, '-d', carc_d, '-q')
    p = os.path.join(carc_d, FIELD)
    v1.run(v1.WSZST, 'extract', p, '-d', p + '.d', '-q')
    tdir = os.path.join(carc_d, FIELD + '.d', b2.TEXDIR)
    tmp = os.path.join(work, 'tex')
    os.makedirs(tmp)
    c = dict(tex={}, anim={}) if base == 'stock' else M.CONCEPTS[base or theme]()
    if still:
        c['anim'] = {}
    for name, im in c['tex'].items():
        path = os.path.join(tdir, name)
        assert os.path.exists(path), name
        w, h, fmt, imgs = tex0_info(path)
        fmt = pick_format(fmt, im)
        if still:
            im = im.resize((w, h), Image.LANCZOS)
        if name in SHRINK:
            im = im.resize(SHRINK[name], Image.LANCZOS)
        frames = c['anim'].get(name)
        if name == 'bwg_pin' and c.get('pin_ways'):            # Whiteout: random colourway (hook tag BPIN)
            enc = [encode(im_, fmt, imgs, tmp, f'pin_{k}') for k, im_ in enumerate(c['pin_ways'])]
            stride = len(enc[0][1])
            tag = b'BPIN' + struct.pack('>HHIi', len(enc), 0, stride, 0)
            open(path, 'wb').write(b2.make_tex0(enc[0][0], [d for _, d in enc], name, tag))
            continue
        if frames:
            size = ANIM_SIZE.get(name)
            enc = [encode(f, fmt, imgs, tmp, f'{name}_{k:02d}', size) for k, f in enumerate(frames)]
            stride = len(enc[0][1])
            assert all(len(d) == stride for _, d in enc)
            tag = b'BANM' + struct.pack('>HHIi', len(enc), PERIOD[name], stride, 0)
            data = b2.make_tex0(enc[0][0], [d for _, d in enc], name, tag)
        else:
            hdr, d = encode(im, fmt, imgs, tmp, name)
            data = b2.make_tex0(hdr, [d], name, bytes(16))
        open(path, 'wb').write(data)
    for name, size in SHRINK.items():                  # shrink the stock ones the theme doesn't replace
        if name in c['tex']:
            continue
        path = os.path.join(tdir, name)
        w, h, fmt, imgs = tex0_info(path)
        im = M.stock(name)
        im = im.convert('RGBA' if im.mode in ('RGBA', 'LA') else 'RGB').resize(size, Image.LANCZOS)
        hdr, d = encode(im, pick_format(fmt, im), imgs, tmp, name)
        open(path, 'wb').write(b2.make_tex0(hdr, [d], name, bytes(16)))
    if base != 'stock':
        tint_lights(os.path.join(carc_d, RSCA), base or theme)
    p = os.path.join(carc_d, FIELD)
    v1.run(v1.WSZST, 'create', p + '.d', '-d', p, '-o', '-q')
    shutil.rmtree(p + '.d')
    check_tags(os.path.join(carc_d, FIELD), len(c['anim']))
    os.makedirs(OUT_DIR, exist_ok=True)
    dest = os.path.join(OUT_DIR, theme + '.carc')
    v1.run(v1.WSZST, 'create', carc_d, '-d', dest, '-o', '-q')
    u8a, u8b = os.path.join(work, 'orig.u8'), os.path.join(work, 'new.u8')
    v1.run(v1.WSZST, 'decompress', ORIG, '-d', u8a, '-o', '-q')
    v1.run(v1.WSZST, 'decompress', dest, '-d', u8b, '-o', '-q')
    extra = os.path.getsize(u8b) - os.path.getsize(u8a)
    print(f'{theme:10s} {os.path.getsize(dest) / 1024:7.0f} KB on SD   extra RAM {extra / 1024:6.0f} KB   '
          f'animated: {", ".join(c["anim"]) or "-"}')
    return dest


EFFECT_ORIG = os.path.join(ROOT, 'work/disc/files/Effect/BwlScene/effect.carc')
TRAIL_DIR = os.path.join(v1.OUT, v1.MOD_DIR, 'trail')
BREFF = 'WS2_effect_bwl.breff'
# WS2_bwl_balltail particle colours (colour 1 primary / secondary): stock light blue -> white,
# so the colour the trail code sets each frame comes through as-is; a little more opaque
TRAIL_COLOR_FROM = bytes.fromhex('01a0ff64' '00ffff00')
TRAIL_COLOR_TO = bytes.fromhex('ffffffb4' 'ffffff00')


def breff_effect(b, name):
    """(absolute offset, size) of one effect's data in a .breff."""
    o = 0x38
    n = struct.unpack_from('>H', b, o + 4)[0]
    p = o + 8
    for _ in range(n):
        ln = struct.unpack_from('>H', b, p)[0]
        nm = b[p + 2:p + 2 + ln].split(b'\0')[0].decode()
        off, size = struct.unpack_from('>II', b, p + 2 + ln)
        p += 2 + ln + 8
        if nm == name:
            return o + off, size
    raise KeyError(name)


def build_trail_effect():
    """Effect/BwlScene/effect.carc with the ball-trail colours patched in place (no breff repack)."""
    work = os.path.join(WORK, 'trail')
    if os.path.exists(work):
        shutil.rmtree(work)
    d = os.path.join(work, 'effect.d')
    v1.run(v1.WSZST, 'extract', EFFECT_ORIG, '-d', d, '-q')
    p = os.path.join(d, BREFF)
    b = bytearray(open(p, 'rb').read())
    st, size = breff_effect(b, 'WS2_bwl_balltail')
    o = st + 0x158
    assert b[o:o + 8] == TRAIL_COLOR_FROM, b[o:o + 8].hex()
    b[o:o + 8] = TRAIL_COLOR_TO
    open(p, 'wb').write(b)
    os.makedirs(TRAIL_DIR, exist_ok=True)
    dest = os.path.join(TRAIL_DIR, 'effect.carc')
    v1.run(v1.WSZST, 'create', d, '-d', dest, '-o', '-q')
    a, n = os.path.join(work, 'orig.u8'), os.path.join(work, 'new.u8')
    v1.run(v1.WSZST, 'decompress', EFFECT_ORIG, '-d', a, '-o', '-q')
    v1.run(v1.WSZST, 'decompress', dest, '-d', n, '-o', '-q')
    ba, bn = open(a, 'rb').read(), open(n, 'rb').read()
    diff = [i for i in range(len(ba)) if i < len(bn) and ba[i] != bn[i]]
    assert len(ba) == len(bn), (len(ba), len(bn))
    assert all(0x10 <= i < 0x20 for i in diff[:16]) and len([i for i in diff if not 0x10 <= i < 0x20]) <= 8, diff[:20]
    print(f'trail      effect.carc: {len([i for i in diff if not 0x10 <= i < 0x20])} colour bytes changed, size unchanged')
    return dest


PAD_NAME = 'pad.bin'


def u8_size(carc, tmp):
    out = os.path.join(tmp, 'size.u8')
    v1.run(v1.WSZST, 'decompress', carc, '-d', out, '-o', '-q')
    return os.path.getsize(out)


def pad_themes():
    """Make every theme exactly the size of the STOCK alley, unpacked AND on the SD card.

    On a restart the game frees the alley and loads the next one into the same memory, which is
    planned around the stock alley: bigger alleys hung the game after 1-2 restarts (padding them all
    to the biggest theme made it hang sooner). So each theme is built smaller than stock (SHRINK), then
    an unused 'pad.bin' brings the unpacked size up to exactly stock, and zeros after the Yaz0 data
    (the decoder stops at the unpacked size) bring the file size up to exactly stock."""
    tmp = os.path.join(WORK, 'pad')
    os.makedirs(tmp, exist_ok=True)
    themes = [t for t, _, _ in THEMES]
    carcs = {t: os.path.join(OUT_DIR, t + '.carc') for t in themes}
    dirs = {t: os.path.join(WORK, t, 'Normal.d') for t in themes}
    for t in themes:                                     # start from unpadded archives
        pad = os.path.join(dirs[t], PAD_NAME)
        if os.path.exists(pad):
            os.remove(pad)
            v1.run(v1.WSZST, 'create', dirs[t], '-d', carcs[t], '-o', '-q')
    target_u8 = u8_size(ORIG, tmp)                       # exactly the stock alley's sizes
    sizes = {t: (u8_size(carcs[t], tmp), os.path.getsize(carcs[t])) for t in themes}
    for t, (u, c) in sizes.items():
        print(f'  {t:10s} unpacked {u:9,} (stock {target_u8:,})   file {c:9,} (stock {os.path.getsize(ORIG):,})')
        assert u + 0x100 <= target_u8, f'{t} is bigger than the stock alley unpacked'
    for t in themes:
        pad = os.path.join(dirs[t], PAD_NAME)
        n = max(0, target_u8 - u8_size(carcs[t], tmp) - 0x40)
        for _ in range(8):                               # adjust until the archive is exactly target_u8
            open(pad, 'wb').write(bytes(n))
            v1.run(v1.WSZST, 'create', dirs[t], '-d', carcs[t], '-o', '-q')
            got = u8_size(carcs[t], tmp)
            if got == target_u8:
                break
            n += target_u8 - got
            assert n >= 0, (t, n)
        assert u8_size(carcs[t], tmp) == target_u8, (t, got, target_u8)
    target_c = os.path.getsize(ORIG)
    for t in themes:
        assert os.path.getsize(carcs[t]) + 0x800 <= target_c, f'{t} file is not safely smaller than the stock alley file'
    for t in themes:
        b = open(carcs[t], 'rb').read()
        assert b[:4] == b'Yaz0' and struct.unpack_from('>I', b, 4)[0] == target_u8
        open(carcs[t], 'wb').write(b + bytes(target_c - len(b)))
    print(f'padded {len(themes)} themes: {target_u8:,} bytes unpacked, {target_c:,} bytes on SD each')
    return target_u8, target_c


def main():
    names = sys.argv[1:] or [t for t, _, _ in THEMES] + [f for f, _, _ in TESTS]
    tests = {f: b for f, b, _ in TESTS}
    for t in names:
        if t == 'trail':
            build_trail_effect()
            continue
        if t == 'pad':
            continue
        build_theme(t, tests.get(t))
    pad_themes()



if __name__ == '__main__':
    main()
