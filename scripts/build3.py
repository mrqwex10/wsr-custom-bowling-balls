"""Build v3: choose your Pro orb (or a random orb each game) + random non-Pro pool.

Per variant, each ball archive gets one mode:
  ('banm', design, n)    animated, all 4 slots share frames (16 frames, with mips)
  ('bran', designs, n)   a random animated orb per player per load (8 frames each, no mips)
  ('brnd', pool)         a random static design per player per load (with mips)
  ('stock',)             untouched
"""
import os, sys, shutil, struct, glob
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
import build as v1
import build2 as b2
import hook
from make_pool import POOL
from make_orbs import ORDER, LABELS

ROOT = v1.ROOT
COLORS = b2.COLORS
NOMIP_CHAIN = 256 * 128 // 2
PERIOD = {16: 4, 8: 5}          # 1/60 s per frame: 16 frames @ 15 fps, 8 frames @ 12 fps

VARIANTS = [('Pro: random orb each game', 'pro_random', ('bran', ORDER, 8), ('brnd', POOL))]
VARIANTS += [(f'Pro: {LABELS[n]}', f'pro_{n}', ('banm', n, 16), ('brnd', POOL)) for n in ORDER]
VARIANTS += [('TEST: non-Pro balls get the random orbs', 'test_orbs', ('stock',), ('bran', ORDER, 8))]
STATIC = [('Classic (no code): P1 Holographic, P2 Identity, any rank', 'test_holo_p1'),
          ('TEST: orientation finder (no code) - send a photo', 'test_orientation')]
STATIC_BUILDS = {'test_orientation': 'orientation'}     # every ball (normal + pro) gets this design


def orb_dir(name, n):
    return os.path.join(ROOT, 'designs/orbs', f'{name}_{n}')


def encode_nomip(png, tmp):
    out = os.path.join(tmp, os.path.basename(png) + '.tex0')
    v1.run(v1.WIMGT, 'encode', png, '-x', 'TEX.CMPR', '-d', out, '-o', '-q', '--n-mm', '0', '--no-mipmaps')
    b = open(out, 'rb').read()
    size = struct.unpack_from('>I', b, 4)[0]
    assert struct.unpack_from('>I', b, 0x24)[0] == 1 and size - 0x40 == NOMIP_CHAIN, png
    return b[:0x40], b[0x40:size]


def frames(name, n, tmp, mips=True):
    src = sorted(glob.glob(os.path.join(orb_dir(name, n), 'f??.png')))
    assert len(src) == n, (name, n, len(src))
    sub = os.path.join(tmp, f'{name}_{n}_{"mm" if mips else "nm"}')
    os.makedirs(sub, exist_ok=True)
    out = []
    for f in src:
        if mips:
            out.append(b2.encode_chain(b2.graded_copy(f, sub), sub))
        else:
            g = os.path.join(sub, os.path.basename(f))
            b2.game_grade(Image.open(f)).save(g)
            out.append(encode_nomip(g, sub))
    return out[0][0], [c for _, c in out]


def fill(kind, brres_d, mode, tmp):
    prefix = 'WS2_bwl_ball_pro_' if kind == 'pro' else 'WS2_bwl_ball_'
    model = (lambda c: f'bwg_ball_{c}_pro') if kind == 'pro' else (lambda c: f'bwg_ball_{c}')
    mips = True
    if mode[0] == 'banm':
        hdr, chains = frames(mode[1], mode[2], tmp)
        mk = lambda k: b2.tag(b'BANM', len(chains), PERIOD[mode[2]], k)
    elif mode[0] == 'brnd':
        chains = []
        for n in mode[1]:
            hdr, c = b2.encode_chain(b2.pool_chain_pngs(n, tmp), tmp)
            chains.append(c)
        mk = lambda k: b2.tag(b'BRND', len(chains), 0xFFFF, k)
    elif mode[0] == 'bran':
        mips = False
        chains = []
        for n in mode[1]:
            hdr, c = frames(n, mode[2], tmp, mips=False)
            chains += c
        sets, nfr = len(mode[1]), mode[2]
        mk = lambda k: b'BRAN' + struct.pack('>BBHHHi', sets, nfr, 0xFFFF, PERIOD[nfr], NOMIP_CHAIN >> 5, k)
    else:
        raise ValueError(mode)
    for k, c in enumerate(COLORS):
        name = prefix + c
        datas = chains if k == 0 else [chains[(k * 3) % len(chains)]]
        open(os.path.join(brres_d, b2.TEXDIR, name), 'wb').write(b2.make_tex0(hdr, datas, name, mk(k)))
        if mips:
            for s in ('', '_mirror'):
                v1.set_mip_filter(os.path.join(brres_d, b2.MDLDIR, model(c) + s), name)


def build_variant(folder, pro_mode, normal_mode):
    work = os.path.join(v1.BUILD, folder)
    kinds = [k for k, m in (('pro', pro_mode), ('normal', normal_mode)) if m[0] != 'stock']
    dirs = v1.extract(v1.ORIG_CARC, os.path.join(work, 'common.d'), kinds)
    tmp = os.path.join(work, 'tex')
    os.makedirs(tmp, exist_ok=True)
    for kind, mode in (('pro', pro_mode), ('normal', normal_mode)):
        if mode[0] != 'stock':
            fill(kind, dirs[kind], mode, tmp)
    for kind in kinds:
        brres = os.path.join(work, 'common.d', v1.BRRES[kind])
        v1.run(v1.WSZST, 'create', brres + '.d', '-d', brres, '-o', '-q')
        shutil.rmtree(brres + '.d')
        b2.finalize_tags(brres)
    dest = os.path.join(v1.OUT, v1.MOD_DIR, folder, 'common.carc')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    v1.run(v1.WSZST, 'create', os.path.join(work, 'common.d'), '-d', dest, '-o', '-q')
    return dest


def build_static(folder, design):
    work = os.path.join(v1.BUILD, folder)
    dirs = v1.extract(v1.ORIG_CARC, os.path.join(work, 'common.d'), ('normal', 'pro'))
    tmp = os.path.join(work, 'tex')
    os.makedirs(tmp, exist_ok=True)
    hdr, chain = b2.encode_chain(b2.pool_chain_pngs(design, tmp), tmp)
    for kind in ('normal', 'pro'):
        for c in COLORS:
            name = ('WS2_bwl_ball_pro_' if kind == 'pro' else 'WS2_bwl_ball_') + c
            model = f'bwg_ball_{c}_pro' if kind == 'pro' else f'bwg_ball_{c}'
            open(os.path.join(dirs[kind], b2.TEXDIR, name), 'wb').write(b2.make_tex0(hdr, [chain], name, bytes(16)))
            for s_ in ('', '_mirror'):
                v1.set_mip_filter(os.path.join(dirs[kind], b2.MDLDIR, model + s_), name)
        brres = os.path.join(work, 'common.d', v1.BRRES[kind])
        v1.run(v1.WSZST, 'create', brres + '.d', '-d', brres, '-o', '-q')
        shutil.rmtree(brres + '.d')
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
    xml = ('<wiidisc version="1">\n  <id game="RZT">\n    <region type="E" />\n  </id>\n  <options>\n'
           '    <section name="WSR Custom Bowling Balls">\n      <option name="Ball mod">\n'
           + '\n'.join(choices) + '\n      </option>\n    </section>\n  </options>\n'
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
    for label, folder, pro_mode, normal_mode in VARIANTS:
        dest = build_variant(folder, pro_mode, normal_mode)
        u8 = os.path.join(v1.BUILD, folder, 'size.u8')
        v1.run(v1.WSZST, 'decompress', dest, '-d', u8, '-o', '-q')
        extra = os.path.getsize(u8) - 1862666
        print(f'{folder:14s} carc {os.path.getsize(dest):8d}  extra RAM {extra / 1024:6.0f} KB  {label}')
    for folder, design in STATIC_BUILDS.items():
        print(folder, os.path.getsize(build_static(folder, design)), 'bytes (static)')
    print(write_xml())


if __name__ == '__main__':
    main()
