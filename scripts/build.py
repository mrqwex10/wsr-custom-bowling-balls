"""Build Riivolution-ready common.carc variants with custom PRO bowling balls.

Pipeline per variant:
  original common.carc (extracted)  ->  replace pro-ball TEX0s (CMPR + mipmaps)
  -> set those materials to trilinear mip filtering -> repack brres -> repack carc (Yaz0)
Then writes the Riivolution XML.

usage: build.py            build everything into output/
       build.py --roundtrip  only check that an unmodified repack is byte-identical
"""
import os, sys, shutil, struct, subprocess, json, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
from mdl0_dump import group, u32, s32, cstr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, 'tools/bin')
WSZST, WIMGT = os.path.join(TOOLS, 'wszst'), os.path.join(TOOLS, 'wimgt')
ORIG_CARC = os.path.join(ROOT, 'work/disc/files/Common/BwlScene/common.carc')
BUILD = os.path.join(ROOT, 'work/build')
OUT = os.path.join(ROOT, 'output')
MOD_DIR = 'WSR_ball_mod'          # folder name at the SD card root
BRRES = {'pro': 'G3D/WS2_bwl_ball_pro.brres', 'normal': 'G3D/WS2_bwl_ball.brres'}
COLORS = ['blue', 'red', 'green', 'yellow']   # = player 1..4

# design name -> source image (master, any size with 2:1 ratio) ; '.mmN' files are custom mips
DESIGNS = {
    'holo': 'designs/holo.png',
    'identity': 'designs/identity.png',
}
LABELS = {'holo': 'Holographic', 'identity': 'Storm Identity', None: 'Stock'}

# Riivolution choices: (choice label, folder, size, {(ball kind, player color): design})
# ball kind: 'pro' = star ball at Pro class, 'normal' = striped ball below Pro
SLOTS_A = {('pro', 'blue'): 'holo', ('pro', 'red'): 'identity'}
SLOTS_B = {('pro', 'blue'): 'identity', ('pro', 'red'): 'holo'}
# test: same designs on the normal balls too, so they show at any skill level
TEST_A = {**SLOTS_A, ('normal', 'blue'): 'holo', ('normal', 'red'): 'identity'}
TEST_B = {**SLOTS_B, ('normal', 'blue'): 'identity', ('normal', 'red'): 'holo'}
VARIANTS = [
    ('P1 Holographic, P2 Identity', 'holo_p1', 512, SLOTS_A),
    ('P1 Identity, P2 Holographic', 'identity_p1', 512, SLOTS_B),
    ('P1 Holographic, P2 Identity (low-res safe mode)', 'holo_p1_lowres', 256, SLOTS_A),
    ('P1 Identity, P2 Holographic (low-res safe mode)', 'identity_p1_lowres', 256, SLOTS_B),
    ('TEST any rank: P1 Holographic, P2 Identity', 'test_holo_p1', 512, TEST_A),
    ('TEST any rank: P1 Identity, P2 Holographic', 'test_identity_p1', 512, TEST_B),
]
N_MIPS = 5
GX_LIN_MIP_LIN = 5


def run(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f'command failed: {" ".join(args)}\n{r.stdout}\n{r.stderr}')
    return r.stdout


def sha(path):
    return hashlib.sha1(open(path, 'rb').read()).hexdigest()[:12]


def extract(carc, dest, kinds=('pro',)):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    run(WSZST, 'extract', carc, '-d', dest, '-q')
    dirs = {}
    for k in kinds:
        brres = os.path.join(dest, BRRES[k])
        run(WSZST, 'extract', brres, '-d', brres + '.d', '-q')
        dirs[k] = brres + '.d'
    return dirs


def repack(carc_dir, out_carc, kinds=('pro',)):
    for k in kinds:
        brres = os.path.join(carc_dir, BRRES[k])
        run(WSZST, 'create', brres + '.d', '-d', brres, '-o', '-q')
        shutil.rmtree(brres + '.d')
    run(WSZST, 'create', carc_dir, '-d', out_carc, '-o', '-q')


def mip_chain(design, size, tmp):
    """Write <name>.png + <name>.mmN.png at the target size. Uses the design's own
    custom mips (e.g. the holo colour shift) when present, else high-quality downsamples."""
    src = os.path.join(ROOT, DESIGNS[design])
    base, ext = os.path.splitext(src)
    w, h = size, size // 2
    img = Image.open(src).convert('RGB')
    os.makedirs(tmp, exist_ok=True)
    out = os.path.join(tmp, f'{design}_{size}.png')
    levels = [img]
    for m in range(1, N_MIPS + 1):
        custom = f'{base}.mm{m}{ext}'
        levels.append(Image.open(custom).convert('RGB') if os.path.exists(custom) else None)
    # pick each level by its pixel size so 256-wide builds reuse the right custom mips
    by_width = {}
    for lv in levels:
        if lv is not None:
            by_width.setdefault(lv.width, lv)
    for m in range(N_MIPS + 1):
        lw, lh = w >> m, h >> m
        if lw < 8 or lh < 4:
            break
        src_lv = by_width.get(lw)
        if src_lv is None:
            # a custom chain whose base is bigger than this build: shift by the level offset
            src_lv = img
            if levels[1] is not None and img.width > w:
                k = (img.width // w).bit_length() - 1 + m
                src_lv = levels[k] if k < len(levels) and levels[k] is not None else img
        lv = src_lv if src_lv.size == (lw, lh) else src_lv.resize((lw, lh), Image.LANCZOS)
        lv.save(out if m == 0 else out.replace('.png', f'.mm{m}.png'))
    return out


def encode(png, dest):
    run(WIMGT, 'encode', png, '-x', 'TEX.CMPR', '-d', dest, '-o', '-q')


def set_mip_filter(mdl0_path, tex_name):
    """Layer using `tex_name` (the design texture): min filter -> LIN_MIP_LIN."""
    b = bytearray(open(mdl0_path, 'rb').read())
    secs = [u32(b, 0x10 + 4 * i) for i in range(14)]
    n_patched = 0
    for name, m in group(b, secs[8]):
        n = u32(b, m + 0x2C)
        lo = m + s32(b, m + 0x30)
        for i in range(n):
            L = lo + i * 0x34
            if cstr(b, L + s32(b, L)) == tex_name:
                struct.pack_into('>I', b, L + 0x20, GX_LIN_MIP_LIN)
                n_patched += 1
    assert n_patched, mdl0_path
    open(mdl0_path, 'wb').write(b)


def build_variant(folder, size, slots):
    work = os.path.join(BUILD, folder)
    kinds = sorted({k for k, _ in slots})
    dirs = extract(ORIG_CARC, os.path.join(work, 'common.d'), kinds)
    tmp = os.path.join(work, 'tex')
    for (kind, color), design in slots.items():
        png = mip_chain(design, size, tmp)
        tex = f'WS2_bwl_ball_pro_{color}' if kind == 'pro' else f'WS2_bwl_ball_{color}'
        model = f'bwg_ball_{color}_pro' if kind == 'pro' else f'bwg_ball_{color}'
        encode(png, os.path.join(dirs[kind], 'Textures(NW4R)', tex))
        for suffix in ('', '_mirror'):
            set_mip_filter(os.path.join(dirs[kind], '3DModels(NW4R)', model + suffix), tex)
    dest = os.path.join(OUT, MOD_DIR, folder, 'common.carc')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    repack(os.path.join(work, 'common.d'), dest, kinds)
    return dest


def roundtrip():
    work = os.path.join(BUILD, '_roundtrip')
    extract(ORIG_CARC, os.path.join(work, 'common.d'))
    out = os.path.join(work, 'common.carc')
    repack(os.path.join(work, 'common.d'), out)
    a = os.path.join(work, 'a.u8'); b = os.path.join(work, 'b.u8')
    run(WSZST, 'decompress', ORIG_CARC, '-d', a, '-o', '-q')
    run(WSZST, 'decompress', out, '-d', b, '-o', '-q')
    same = open(a, 'rb').read() == open(b, 'rb').read()
    print('roundtrip U8 identical:', same, '| sizes', os.path.getsize(a), os.path.getsize(b))
    return same


def write_xml():
    choices = '\n'.join(
        f'        <choice name="{label}"><patch id="{folder}" /></choice>' for label, folder, _, _ in VARIANTS)
    patches = '\n'.join(
        f'  <patch id="{folder}">\n'
        f'    <file disc="/Common/BwlScene/common.carc" external="/{MOD_DIR}/{folder}/common.carc" />\n'
        f'  </patch>' for _, folder, _, _ in VARIANTS)
    xml = f'''<wiidisc version="1">
  <id game="RZT">
    <region type="E" />
  </id>
  <options>
    <section name="WSR Custom Bowling Balls">
      <option name="Pro balls">
{choices}
      </option>
    </section>
  </options>
{patches}
</wiidisc>
'''
    os.makedirs(os.path.join(OUT, 'riivolution'), exist_ok=True)
    p = os.path.join(OUT, 'riivolution', f'{MOD_DIR}.xml')
    open(p, 'w').write(xml)
    return p


def main():
    if '--roundtrip' in sys.argv:
        sys.exit(0 if roundtrip() else 1)
    if os.path.exists(os.path.join(OUT, MOD_DIR)):
        shutil.rmtree(os.path.join(OUT, MOD_DIR))
    for label, folder, size, slots in VARIANTS:
        p = build_variant(folder, size, slots)
        print(f'{folder:22s} {os.path.getsize(p):8d} bytes  {label}')
    print(write_xml())


if __name__ == '__main__':
    main()
