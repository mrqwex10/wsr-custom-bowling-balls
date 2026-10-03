"""Build v2: animated Pro balls + random non-Pro balls (needs the GXLoadTexObj hook).

  Pro balls (all 4 player slots)  -> animated holographic (frames live in pro_blue's TEX0)
  Normal balls (all 4 slots)      -> random pick from a design pool (pool lives in blue's TEX0)

Every texture is 256x128 CMPR with 4 mip levels (21,824 bytes per image chain), so
every frame / design has the same stride and the hook can swap between them.
"""
import os, sys, shutil, struct, glob
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
import build as v1
import hook
from make_pool import POOL

ROOT = v1.ROOT
TEXDIR = 'Textures(NW4R)'
MDLDIR = '3DModels(NW4R)'
COLORS = ['blue', 'red', 'green', 'yellow']
W, H, N_MIPS = 256, 128, 4
CHAIN = sum((W >> m) * (H >> m) // 2 for m in range(N_MIPS + 1))   # CMPR = 4 bits/texel
assert CHAIN == 21824
ANIM_PERIOD_60THS = 4        # 15 fps
LITE_FRAMES = ('designs/holo_anim_lite', 10)

# (label, folder, anim dir, n_frames, pool designs or 'anim' = normal balls animated too)
VARIANTS = [
    ('Animated Pro + random balls', 'anim_random', 'designs/holo_anim', 20, POOL),
    ('Animated Pro + random balls (Lite)', 'anim_random_lite', 'designs/holo_anim_lite', 10, POOL[:5]),
    ('TEST: everyone animated (no Pro needed)', 'anim_everyone', 'designs/holo_anim', 20, 'anim'),
]


# In-game the ball is held turned 90 degrees about its vertical axis compared with
# our design 'front' (+Z). Rolling every image a quarter turn puts the designed
# front (+Z) onto +X, the side the camera actually sees (verified on hardware).
QUARTER_TURN = True


def game_grade(img):
    """The game's lighting darkens ball textures; lift shadows/mids to compensate.
    Also applies the quarter-turn so features face the camera in-game."""
    import numpy as np
    a = np.asarray(img.convert('RGB'), float) / 255
    a = np.clip(a ** 0.8 * 1.08, 0, 1)
    if QUARTER_TURN:
        a = np.roll(a, a.shape[1] // 4, axis=1)
    return Image.fromarray((a * 255 + 0.5).astype('uint8'), 'RGB')


def graded_copy(src_png, tmp):
    """Copy a PNG and its .mmK.png levels into tmp with the game grade applied."""
    out = os.path.join(tmp, os.path.basename(src_png))
    for g in [src_png] + sorted(glob.glob(src_png.replace('.png', '.mm*.png'))):
        game_grade(Image.open(g)).save(os.path.join(tmp, os.path.basename(g)))
    return out


def name_tail(name):
    n = name.encode()
    t = struct.pack('>I', len(n)) + n
    return t + b'\0' * (-len(t) % 4 + 4)


def encode_chain(png, tmp):
    """PNG (+ .mmK.png) -> raw CMPR bytes of the full mip chain + a TEX0 header template."""
    out = os.path.join(tmp, os.path.basename(png) + '.tex0')
    v1.run(v1.WIMGT, 'encode', png, '-x', 'TEX.CMPR', '-d', out, '-o', '-q')
    b = open(out, 'rb').read()
    size = struct.unpack_from('>I', b, 4)[0]
    assert struct.unpack_from('>HH', b, 0x1C) == (W, H), png
    assert struct.unpack_from('>I', b, 0x24)[0] == N_MIPS + 1, png
    assert size - 0x40 == CHAIN, (png, size)
    return b[:0x40], b[0x40:size]


def pool_chain_pngs(name, tmp):
    """Master equirect -> 256x128 + mips (LANCZOS)."""
    src = Image.open(os.path.join(ROOT, 'designs/pool', name + '.png')).convert('RGB')
    base = os.path.join(tmp, f'pool_{name}.png')
    game_grade(src.resize((W, H), Image.LANCZOS)).save(base)
    for m in range(1, N_MIPS + 1):
        game_grade(src.resize((W >> m, H >> m), Image.LANCZOS)).save(base.replace('.png', f'.mm{m}.png'))
    return base


def make_tex0(header, datas, name, tag):
    """One TEX0 file whose image data is datas[0] followed by datas[1:] (the pool)."""
    hdr = bytearray(header)
    data = b''.join(datas)
    size = 0x40 + len(data)
    struct.pack_into('>I', hdr, 0x04, size)
    struct.pack_into('>I', hdr, 0x14, size + 4)   # name offset -> string in the tail
    hdr[0x30:0x40] = tag
    return bytes(hdr) + data + name_tail(name)


def tag(magic, count, param, slot_id, stride=CHAIN):
    # rel is finalised after the brres is laid out; it temporarily holds a slot id
    return magic + struct.pack('>HHIi', count, param, stride, slot_id)


def finalize_tags(brres_path):
    """Patch real 'rel' offsets: each slot -> image data of the pool owner (slot id 0)."""
    b = bytearray(open(brres_path, 'rb').read())
    found = {}
    i = 0
    while (i := b.find(b'TEX0', i)) >= 0:
        if b[i + 0x30:i + 0x34] in (b'BANM', b'BRND', b'BRAN'):
            slot = struct.unpack_from('>i', b, i + 0x3C)[0]
            found[slot] = i
        i += 4
    assert sorted(found) == [0, 1, 2, 3], found
    pool = found[0] + 0x40
    for slot, off in found.items():
        assert off % 32 == 0, f'TEX0 not 32-byte aligned at {off:#x}'
        struct.pack_into('>i', b, off + 0x3C, pool - (off + 0x40))
    open(brres_path, 'wb').write(b)
    return found


def set_filters(brres_d, models):
    for mdl, tex in models:
        v1.set_mip_filter(os.path.join(brres_d, MDLDIR, mdl), tex)


def build_variant(folder, anim_dir, n_frames, pool):
    work = os.path.join(v1.BUILD, folder)
    dirs = v1.extract(v1.ORIG_CARC, os.path.join(work, 'common.d'), ('normal', 'pro'))
    tmp = os.path.join(work, 'tex')
    os.makedirs(tmp, exist_ok=True)

    # ---- Pro: animated frames, all owned by pro_blue -----------------------
    def frame_chains(adir, n):
        frames = sorted(glob.glob(os.path.join(ROOT, adir, 'f??.png')))
        assert len(frames) == n, (adir, len(frames))
        sub = os.path.join(tmp, os.path.basename(adir))
        os.makedirs(sub, exist_ok=True)
        out = []
        for f in frames:
            out.append(encode_chain(graded_copy(f, sub), sub))
        return out[0][0], [c for _, c in out]

    hdr, chains = frame_chains(anim_dir, n_frames)
    for k, color in enumerate(COLORS):
        name = f'WS2_bwl_ball_pro_{color}'
        datas = chains if k == 0 else [chains[0]]
        t = tag(b'BANM', n_frames, ANIM_PERIOD_60THS, k)
        open(os.path.join(dirs['pro'], TEXDIR, name), 'wb').write(make_tex0(hdr, datas, name, t))
    set_filters(dirs['pro'], [(f'bwg_ball_{c}_pro{s}', f'WS2_bwl_ball_pro_{c}') for c in COLORS for s in ('', '_mirror')])

    # ---- Normal: random pool (or animated for the test build), owned by blue
    if pool == 'anim':
        hdr, pchains = frame_chains(*LITE_FRAMES)
        mk_tag = lambda k: tag(b'BANM', len(pchains), ANIM_PERIOD_60THS, k)
    else:
        pchains = []
        for n in pool:
            hdr, data = encode_chain(pool_chain_pngs(n, tmp), tmp)
            pchains.append(data)
        mk_tag = lambda k: tag(b'BRND', len(pchains), 0xFFFF, k)
    for k, color in enumerate(COLORS):
        name = f'WS2_bwl_ball_{color}'
        datas = pchains if k == 0 else [pchains[k % len(pchains)]]
        t = mk_tag(k)
        open(os.path.join(dirs['normal'], TEXDIR, name), 'wb').write(make_tex0(hdr, datas, name, t))
    set_filters(dirs['normal'], [(f'bwg_ball_{c}{s}', f'WS2_bwl_ball_{c}') for c in COLORS for s in ('', '_mirror')])

    # ---- pack brres, fix up rel offsets, pack carc ---------------------------
    layout = {}
    for kind in ('pro', 'normal'):
        brres = os.path.join(work, 'common.d', v1.BRRES[kind])
        v1.run(v1.WSZST, 'create', brres + '.d', '-d', brres, '-o', '-q')
        shutil.rmtree(brres + '.d')
        layout[kind] = finalize_tags(brres)
    dest = os.path.join(v1.OUT, v1.MOD_DIR, folder, 'common.carc')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    v1.run(v1.WSZST, 'create', os.path.join(work, 'common.d'), '-d', dest, '-o', '-q')
    return dest, layout


def memory_patches_xml():
    lines = []
    for addr, data, orig in hook.patches():
        extra = f' original="{orig:08X}"' if orig is not None else ''
        lines.append(f'    <memory offset="0x{addr:08X}" value="{data.hex().upper()}"{extra} />')
    return '\n'.join(lines)


def write_xml():
    # v2 (code) choices first, then the v1 static fallback
    choices, patches = [], []
    for label, folder, *_ in VARIANTS:
        choices.append(f'        <choice name="{label}"><patch id="{folder}" /></choice>')
        patches.append(f'  <patch id="{folder}">\n'
                       f'    <file disc="/Common/BwlScene/common.carc" external="/{v1.MOD_DIR}/{folder}/common.carc" />\n'
                       f'{memory_patches_xml()}\n  </patch>')
    static = [('Classic (no code): P1 Holographic, P2 Identity, any rank', 'test_holo_p1'),
              ('Classic (no code): P1 Identity, P2 Holographic, any rank', 'test_identity_p1')]
    for label, folder in static:
        choices.append(f'        <choice name="{label}"><patch id="{folder}" /></choice>')
        patches.append(f'  <patch id="{folder}">\n'
                       f'    <file disc="/Common/BwlScene/common.carc" external="/{v1.MOD_DIR}/{folder}/common.carc" />\n  </patch>')
    xml = ('<wiidisc version="1">\n  <id game="RZT">\n    <region type="E" />\n  </id>\n  <options>\n'
           '    <section name="WSR Custom Bowling Balls">\n      <option name="Ball mod">\n'
           + '\n'.join(choices) + '\n      </option>\n    </section>\n  </options>\n'
           + '\n'.join(patches) + '\n</wiidisc>\n')
    p = os.path.join(v1.OUT, 'riivolution', f'{v1.MOD_DIR}.xml')
    open(p, 'w').write(xml)
    return p


def main():
    for label, folder, anim_dir, n, pool in VARIANTS:
        dest, layout = build_variant(folder, anim_dir, n, pool)
        print(f'{folder:18s} {os.path.getsize(dest):8d} bytes  {label}')
    print(write_xml())


if __name__ == '__main__':
    main()
