"""Build v4: Pro orbs + skill tiers (Gold at 1500, Prismatic Diamond at 2000).

Pro archive:  4 slot textures tagged BTIR -> redirect by the player's Bowling skill
              to one of three shared targets inside the same archive:
                 WS2_bwl_ball_pro_zbase (orb: BANM single / BRAN random)
                 WS2_bwl_ball_pro_zgold (BANM)    WS2_bwl_ball_pro_zdia (BANM)
Normal archive: per-player random pool (each slot keeps its own pick), or a test mode.
"""
import os, sys, shutil, struct, glob
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
import build as v1
import build2 as b2
import build3 as b3
import hook
from mdl0_dump import group, u32
from make_pool import POOL
from make_orbs import ORDER, LABELS

COLORS = b2.COLORS
TIER1, TIER2 = 1500, 2000
NOMIP = b3.NOMIP_CHAIN

# (label, folder, pro spec, normal spec)
#  pro spec:    ('tiers', base, frames_base, frames_tier, mips)  base = orb name or 'random'
#               ('stock',)
#  normal spec: ('brnd', pool) | ('bran', orbs, frames) | ('banm', design, frames) | ('bdbg', designs) | ('stock',)
VARIANTS = [('Pro: random orb each game', 'pro_random', ('tiers', 'random', 6, 8, False), ('brnd', POOL))]
VARIANTS += [(f'Pro: {LABELS[n]}', f'pro_{n}', ('tiers', n, 16, 10, True), ('brnd', POOL)) for n in ORDER]
VARIANTS += [('TEST: non-Pro balls get the random orbs', 'test_orbs', ('stock',), ('bran', ORDER, 8))]
TIER_OPTIONS = [('Gold', 'G'), ('Prismatic Diamond', 'D')]
STATIC = []   # the old 'Classic' build used a traced trademark logo; not part of the release
PERIOD = {16: 4, 10: 4, 8: 5, 6: 6}


def brres_textures(path):
    """{texture name: absolute offset of its TEX0} for a .brres file."""
    b = open(path, 'rb').read()
    root = struct.unpack_from('>H', b, 0x0C)[0]
    folders = group(b, root + 8)
    tex = dict(folders)['Textures(NW4R)']
    return {name: off for name, off in group(b, tex)}


def nomip_chains(paths, tmp):
    out = []
    for f in paths:
        g = os.path.join(tmp, 'nm_' + os.path.basename(os.path.dirname(f)) + '_' + os.path.basename(f))
        b2.game_grade(Image.open(f)).save(g)
        out.append(b3.encode_nomip(g, tmp))
    return out[0][0], [c for _, c in out]


def orb_frames(name, n, tmp, mips):
    if mips:
        return b3.frames(name, n, tmp, mips=True)
    return nomip_chains(sorted(glob.glob(os.path.join(b3.orb_dir(name, n), 'f??.png'))), tmp)


def pool_nomip(names, tmp):
    paths = []
    for n in names:
        src = Image.open(os.path.join(v1.ROOT, 'designs/pool', n + '.png')).convert('RGB').resize((256, 128), Image.LANCZOS)
        p = os.path.join(tmp, f'pool_{n}.png')
        src.save(p)
        paths.append(p)
    return nomip_chains(paths, tmp)


def fill_pro_tiers(brres_d, base, n_base, n_tier, mips, tmp):
    T = os.path.join(brres_d, b2.TEXDIR)
    if base == 'random':
        chains = []
        for o in ORDER:
            hdr, c = orb_frames(o, n_base, tmp, mips)
            chains += c
        base_tag = b'BRAN' + struct.pack('>BBHHHi', len(ORDER), n_base, 0xFFFF, PERIOD[n_base], len(chains[0]) >> 5, 0)
    else:
        hdr, chains = orb_frames(base, n_base, tmp, mips)
        base_tag = b2.tag(b'BANM', n_base, PERIOD[n_base], 0, stride=len(chains[0]))
    ghdr, gold = orb_frames('gold', n_tier, tmp, mips)
    dhdr, dia = orb_frames('diamond', n_tier, tmp, mips)
    assert len(gold[0]) == len(chains[0]) == len(dia[0])
    st = len(chains[0])
    targets = {'WS2_bwl_ball_pro_zbase': (hdr, chains, base_tag),
               'WS2_bwl_ball_pro_zgold': (ghdr, gold, b2.tag(b'BANM', n_tier, PERIOD[n_tier], 0, stride=st)),
               'WS2_bwl_ball_pro_zdia': (dhdr, dia, b2.tag(b'BANM', n_tier, PERIOD[n_tier], 0, stride=st))}
    if base == 'random':
        # each player needs their OWN roll: the roll is stamped in the target header,
        # so give every slot its own small BRAN header (frame 0 only) that points at
        # the shared frame pool in zbase. (One shared header = every Pro player got
        # the same orb - fixed in v1.2.)
        for k in range(1, len(COLORS)):
            targets[f'WS2_bwl_ball_pro_zbase{k}'] = (hdr, [chains[0]], base_tag)
    for name, (h, ch, tg) in targets.items():
        open(os.path.join(T, name), 'wb').write(b2.make_tex0(h, ch, name, tg))
    for c in COLORS:
        name = f'WS2_bwl_ball_pro_{c}'
        tg = b'BTIR' + struct.pack('>BBhii', COLORS.index(c), 0, 0, 0, 0)   # player slot; offsets patched after packing
        open(os.path.join(T, name), 'wb').write(b2.make_tex0(hdr, [chains[0]], name, tg))
        if mips:
            for s in ('', '_mirror'):
                v1.set_mip_filter(os.path.join(brres_d, b2.MDLDIR, f'bwg_ball_{c}_pro{s}'), name)


def finalize_tiers(brres_path):
    offs = brres_textures(brres_path)
    b = bytearray(open(brres_path, 'rb').read())
    hdr = {k: offs[f'WS2_bwl_ball_pro_{k}'] for k in ('zbase', 'zgold', 'zdia')}
    per_slot = {k: offs.get(f'WS2_bwl_ball_pro_zbase{k}') for k in range(1, len(COLORS))}
    pool = hdr['zbase'] + 0x40
    for k, o in per_slot.items():
        if o is not None:                              # per-player roll headers -> shared frame pool
            assert b[o + 0x30:o + 0x34] == b'BRAN' and o % 32 == 0
            struct.pack_into('>i', b, o + 0x3C, pool - (o + 0x40))
    for c in COLORS:
        o = offs[f'WS2_bwl_ball_pro_{c}']
        assert b[o:o + 4] == b'TEX0' and b[o + 0x30:o + 0x34] == b'BTIR' and o % 32 == 0
        data = o + 0x40
        k = COLORS.index(c)
        base_hdr = per_slot.get(k) if per_slot.get(k) is not None else hdr['zbase']
        base_rel = base_hdr - data
        assert base_rel % 32 == 0 and -0x8000 <= base_rel // 32 < 0x8000, base_rel
        struct.pack_into('>hii', b, o + 0x36, base_rel // 32, hdr['zgold'] - data, hdr['zdia'] - data)
    for k, o in hdr.items():
        assert o % 32 == 0 and b[o + 0x30:o + 0x34] in (b'BANM', b'BRAN')
    open(brres_path, 'wb').write(b)


DIAG_PAGES = [('C', (40, 90, 220)), ('A', (235, 130, 20)), ('B', (40, 170, 60))]
DIAG_N = 26


def diag_pngs(tmp):
    """Small readout textures: page letter + number on four sides (A/B are hundreds)."""
    import numpy as np
    from PIL import ImageDraw, ImageFont
    from ballmap import directions
    from make_pool import decal
    d = directions(512, 256)
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Black.ttf', 330)
    out = []
    for letter, rgb in DIAG_PAGES:
        for v in range(DIAG_N):
            col = np.zeros(d.shape[:2] + (3,)) + np.array(rgb, float) / 255
            im = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
            label = f'{letter}{v}' + ('+' if v == DIAG_N - 1 else '')
            ImageDraw.Draw(im).text((512, 530), label, font=font, anchor='mm', fill=(255, 255, 255, 255),
                                    stroke_width=18, stroke_fill=(0, 0, 0, 255))
            for f_ in ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0)):
                col = decal(col, d, f_, im, 44)
            p = os.path.join(tmp, f'diag_{letter}{v:02d}.png')
            Image.fromarray((np.clip(col, 0, 1) * 255).astype('uint8')).resize((128, 64), Image.LANCZOS).save(p)
            out.append(p)
    return out


def encode_small(png, tmp):
    out = os.path.join(tmp, os.path.basename(png) + '.tex0')
    g = os.path.join(tmp, 'g_' + os.path.basename(png))
    b2.game_grade(Image.open(png)).save(g)
    v1.run(v1.WIMGT, 'encode', g, '-x', 'TEX.CMPR', '-d', out, '-o', '-q', '--n-mm', '0', '--no-mipmaps')
    b = open(out, 'rb').read()
    size = struct.unpack_from('>I', b, 4)[0]
    return b[:0x40], b[0x40:size]


def fill_normal(kind, brres_d, spec, tmp):
    """Per-slot modes (each slot keeps its own random stamp); pool owned by slot 0."""
    prefix = 'WS2_bwl_ball_pro_' if kind == 'pro' else 'WS2_bwl_ball_'
    if spec[0] == 'brnd':
        hdr, chains = pool_nomip(spec[1], tmp)
        mk = lambda k: b2.tag(b'BRND', len(chains), 0xFFFF, k, stride=len(chains[0]))
    elif spec[0] == 'bdbg':
        hdr, chains = pool_nomip(spec[1], tmp)
        mk = lambda k: b'BDBG' + struct.pack('>HHIi', len(chains), 0, len(chains[0]), k)
    elif spec[0] == 'bran':
        chains = []
        for o in spec[1]:
            hdr, c = orb_frames(o, spec[2], tmp, False)
            chains += c
        sets, nfr = len(spec[1]), spec[2]
        mk = lambda k: b'BRAN' + struct.pack('>BBHHHi', sets, nfr, 0xFFFF, PERIOD[nfr], NOMIP >> 5, k)
    elif spec[0] == 'bpag':
        enc = [encode_small(p, tmp) for p in diag_pngs(tmp)]
        hdr, chains = enc[0][0], [c for _, c in enc]
        assert all(len(c) == 4096 for c in chains)
        mk = lambda k: b'BPAG' + struct.pack('>BBHIi', len(DIAG_PAGES), DIAG_N, 180, len(chains[0]), k)
    elif spec[0] == 'banm':
        hdr, chains = orb_frames(spec[1], spec[2], tmp, False)
        mk = lambda k: b2.tag(b'BANM', len(chains), PERIOD[spec[2]], k, stride=len(chains[0]))
    else:
        raise ValueError(spec)
    for k, c in enumerate(COLORS):
        name = prefix + c
        datas = chains if k == 0 else [chains[(k * 3) % len(chains)]]
        open(os.path.join(brres_d, b2.TEXDIR, name), 'wb').write(b2.make_tex0(hdr, datas, name, mk(k)))


def finalize_slots(brres_path, magics=(b'BANM', b'BRND', b'BRAN', b'BDBG', b'BPAG')):
    """rel (0x3C) of each slot -> image data of slot 0 (which holds the pool).
    BDBG keeps its stride as a u32 at 0x38 like BRND."""
    offs = brres_textures(brres_path)
    b = bytearray(open(brres_path, 'rb').read())
    names = [n for n in offs if n.rsplit('_', 1)[-1] in COLORS]
    by_color = {n.rsplit('_', 1)[-1]: offs[n] for n in names}
    pool = by_color['blue'] + 0x40
    for c, o in by_color.items():
        assert b[o + 0x30:o + 0x34] in magics and o % 32 == 0, (c, b[o + 0x30:o + 0x34])
        struct.pack_into('>i', b, o + 0x3C, pool - (o + 0x40))
    open(brres_path, 'wb').write(b)


def build_variant(folder, pro, normal):
    work = os.path.join(v1.BUILD, folder)
    kinds = [k for k, s in (('pro', pro), ('normal', normal)) if s[0] != 'stock']
    dirs = v1.extract(v1.ORIG_CARC, os.path.join(work, 'common.d'), kinds)
    tmp = os.path.join(work, 'tex')
    os.makedirs(tmp, exist_ok=True)
    if pro[0] == 'tiers':
        fill_pro_tiers(dirs['pro'], *pro[1:], tmp)
    elif pro[0] != 'stock':
        fill_normal('pro', dirs['pro'], pro, tmp)
    if normal[0] != 'stock':
        fill_normal('normal', dirs['normal'], normal, tmp)
    for kind in kinds:
        brres = os.path.join(work, 'common.d', v1.BRRES[kind])
        v1.run(v1.WSZST, 'create', brres + '.d', '-d', brres, '-o', '-q')
        shutil.rmtree(brres + '.d')
        if kind == 'pro' and pro[0] == 'tiers':
            finalize_tiers(brres)
        else:
            finalize_slots(brres)
    dest = os.path.join(v1.OUT, v1.MOD_DIR, folder, 'common.carc')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    v1.run(v1.WSZST, 'create', os.path.join(work, 'common.d'), '-d', dest, '-o', '-q')
    return dest


def write_xml():
    choices, patches = [], []
    mem = b2.memory_patches_xml()
    for label, folder, *_ in VARIANTS:
        choices.append(f'        <choice name="{label}"><patch id="{folder}" /></choice>')
        patches.append(f'  <patch id="{folder}">\n'
                       f'    <file disc="/Common/BwlScene/common.carc" external="/{v1.MOD_DIR}/{folder}/common.carc" />\n'
                       f'{mem}\n  </patch>')
    for label, folder in STATIC:
        choices.append(f'        <choice name="{label}"><patch id="{folder}" /></choice>')
        patches.append(f'  <patch id="{folder}">\n'
                       f'    <file disc="/Common/BwlScene/common.carc" external="/{v1.MOD_DIR}/{folder}/common.carc" />\n  </patch>')
    tier_opts = []
    for slot in range(4):
        ch = []
        for label, code in TIER_OPTIONS:
            pid = f'p{slot + 1}_{code.lower()}'
            ch.append(f'        <choice name="{label}"><patch id="{pid}" /></choice>')
            addr, val, _ = hook.tier_patch(slot, code)
            patches.append(f'  <patch id="{pid}">\n    <memory offset="0x{addr:08X}" value="{val.hex().upper()}" />\n  </patch>')
        tier_opts.append(f'      <option name="P{slot + 1} Pro ball tier">\n' + '\n'.join(ch) + '\n      </option>')
    xml = ('<wiidisc version="1">\n  <id game="RZT">\n    <region type="E" />\n  </id>\n  <options>\n'
           '    <section name="WSR Custom Bowling Balls">\n      <option name="Ball mod">\n'
           + '\n'.join(choices) + '\n      </option>\n' + '\n'.join(tier_opts) + '\n    </section>\n  </options>\n'
           + '\n'.join(patches) + '\n</wiidisc>\n')
    p = os.path.join(v1.OUT, 'riivolution', f'{v1.MOD_DIR}.xml')
    open(p, 'w').write(xml)
    return p


def main():
    keep = {f for _, f, *_ in VARIANTS} | {f for _, f in STATIC}
    od = os.path.join(v1.OUT, v1.MOD_DIR)
    for f in os.listdir(od):
        if os.path.isdir(os.path.join(od, f)) and f not in keep:
            shutil.rmtree(os.path.join(od, f))
    only = sys.argv[1:]
    for label, folder, pro, normal in VARIANTS:
        if only and folder not in only:
            continue
        dest = build_variant(folder, pro, normal)
        u8 = os.path.join(v1.BUILD, folder, 'size.u8')
        v1.run(v1.WSZST, 'decompress', dest, '-d', u8, '-o', '-q')
        extra = os.path.getsize(u8) - 1862666
        print(f'{folder:14s} extra RAM {extra / 1024:6.0f} KB  {label}')
    print(write_xml())


if __name__ == '__main__':
    main()
