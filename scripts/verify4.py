"""End-to-end emulator check of v4 builds: tiers, random pools, test modes."""
import os, sys, struct, glob
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
from test_hook import Machine
import test_hook
import build as v1
import build2 as b2
import build4 as b4
import hook
from make_orbs import ORDER

BASE = 0x90100000
check = test_hook.check
_cache = {}


def frames_ref(name, n):
    k = (name, n)
    if k not in _cache:
        _cache[k] = [np.asarray(b2.game_grade(Image.open(f)), float)
                     for f in sorted(glob.glob(os.path.join(v1.ROOT, 'designs/orbs', f'{name}_{n}', 'f??.png')))]
    return _cache[k]


def pool_ref(names):
    k = tuple(names)
    if k not in _cache:
        _cache[k] = [np.asarray(b2.game_grade(Image.open(os.path.join(v1.ROOT, 'designs/pool', n + '.png'))
                                              .convert('RGB').resize((256, 128), Image.LANCZOS)), float) for n in names]
    return _cache[k]


def run(label, folder, pro, normal):
    print(f'=== {folder}')
    work = os.path.join(v1.ROOT, 'work/verify4', folder)
    os.makedirs(work, exist_ok=True)
    u8 = os.path.join(work, 'common.u8')
    v1.run(v1.WSZST, 'decompress', os.path.join(v1.OUT, v1.MOD_DIR, folder, 'common.carc'), '-d', u8, '-o', '-q')
    arc = open(u8, 'rb').read()
    m = Machine()
    m.mu.mem_write(BASE, arc)
    tags = {}
    i = 0
    while (i := arc.find(b'TEX0', i)) >= 0:
        mg = arc[i + 0x30:i + 0x34]
        if mg in (b'BANM', b'BRND', b'BRAN', b'BDBG', b'BTIR', b'BPAG'):
            tags.setdefault(mg, []).append(i)
        i += 4

    def decode(addr, hdr_off):
        hdr = bytearray(arc[hdr_off:hdr_off + 0x40])
        n_img = struct.unpack_from('>I', hdr, 0x24)[0]
        w_, h_ = struct.unpack_from('>HH', hdr, 0x1C)
        chain = b2.CHAIN if n_img > 1 else w_ * h_ // 2
        hdr[0x30:0x40] = bytes(16)
        struct.pack_into('>I', hdr, 4, 0x40 + chain)
        struct.pack_into('>I', hdr, 0x14, 0)
        p = os.path.join(work, 'probe.tex0')
        open(p, 'wb').write(bytes(hdr) + arc[addr - BASE:addr - BASE + chain])
        v1.run(v1.WIMGT, 'decode', p, '-d', p + '.png', '-o', '-q', '--no-mipmaps')
        return np.asarray(Image.open(p + '.png').convert('RGB'), float)

    def shown(o, hdr_off):
        ok, img3 = m.load(o)
        return ok, decode(((img3 & 0xFFFFFF) << 5) | 0x80000000, hdr_off)

    def best(img, groups):
        res = []
        for gname, refs in groups.items():
            for k, r in enumerate(refs):
                res.append((np.abs(img - r).mean(), gname, k))
        return min(res)

    if pro[0] == 'tiers':
        base, nb, nt, mips = pro[1:]
        groups = {'gold': frames_ref('gold', nt), 'diamond': frames_ref('diamond', nt)}
        if base == 'random':
            for o in ORDER:
                groups['orb:' + o] = frames_ref(o, nb)
        else:
            groups['orb:' + base] = frames_ref(base, nb)
        slots = tags.get(b'BTIR', [])
        check(len(slots) == 4, f'4 Pro slots tagged BTIR ({len(slots)})')
        for n, off in enumerate(slots):
            o = m.texobj(0x81003000 + n * 0x20, BASE + off + 0x40)
            slot = arc[off + 0x34]
            for cfg, want in [(0x00, 'orb'), (ord('G'), 'gold'), (ord('D'), 'diamond')]:
                tierb = bytearray(4); tierb[slot] = cfg
                m.mu.mem_write(hook.TIER_CFG, bytes(tierb))
                skill = chr(cfg) if cfg else '-'
                okall, seen = True, []
                for step in range(nt + 1):                            # walk through the whole animation
                    m.tb = step * b4.PERIOD[nt] * 989 * 1024 + 777 + n
                    ok, img = shown(o, off)
                    err, g, k = best(img, groups)
                    okall &= ok and g.startswith(want) and err < 8
                    seen.append(k)
                check(okall, f'Pro slot {n} (P{slot + 1}), tier byte {skill}: {want}, all frames ok')
    normals = [o for mg in (b'BRND', b'BRAN', b'BANM', b'BDBG') for o in tags.get(mg, [])
               if not (pro[0] == 'tiers' and o in sum((tags.get(x, []) for x in (b'BANM', b'BRAN')), []) and
                       arc[o + 0x34:o + 0x36] != arc[o + 0x34:o + 0x36])]
    if normal[0] == 'brnd':
        refs = {'pool': pool_ref(normal[1])}
        for n, off in enumerate(tags[b'BRND']):
            o = m.texobj(0x81003200 + n * 0x20, BASE + off + 0x40)
            m.tb = 0x99999 * (n + 3) ** 3
            ok, img = shown(o, off)
            err, g, k = best(img, refs)
            check(ok and err < 8, f'non-Pro slot {n}: random design "{normal[1][k]}" (err {err:.1f})')
    elif normal[0] == 'banm':
        refs = {normal[1]: frames_ref(normal[1], normal[2])}
        for n, off in enumerate([x for x in tags[b'BANM']]):
            o = m.texobj(0x81003200 + n * 0x20, BASE + off + 0x40)
            m.tb = 3 * PERIOD_T(normal[2]) + 100
            ok, img = shown(o, off)
            err, g, k = best(img, refs)
            check(ok and err < 8 and k == 3, f'slot {n}: animated {g} frame {k} (err {err:.1f})')
    elif normal[0] == 'bdbg':
        refs = {'det': pool_ref(normal[1])}
        for n, off in enumerate(tags[b'BDBG']):
            o = m.texobj(0x81003200 + n * 0x20, BASE + off + 0x40)
            okall = True
            for skill, want in [(0, 0), (700, 1), (1200, 2), (1700, 3), (2300, 4)]:
                m.w32(hook.LAST_SKILL, skill)
                ok, img = shown(o, off)
                err, g, k = best(img, refs)
                okall &= ok and k == want and err < 8
            check(okall, f'detector slot {n}: every skill bracket shows the right colour')
    elif normal[0] == 'bpag':
        tmp = os.path.join(work, 'diag'); os.makedirs(tmp, exist_ok=True)
        refs = {'diag': [np.asarray(b2.game_grade(Image.open(p)), float) for p in b4.diag_pngs(tmp)]}
        m.w32(hook.CALLS, 3); m.w32(hook.LAST_ANY, 1250); m.w32(hook.LAST_SKILL, 0)
        TPP = 180 * 989 * 1024
        for n, off in enumerate(tags[b'BPAG']):
            o = m.texobj(0x81003200 + n * 0x20, BASE + off + 0x40)
            got = []
            for page in range(3):
                m.tb = page * TPP + 500
                ok, img = shown(o, off)
                err, g, k = best(img, refs)
                got.append((k, round(err, 1)))
            want = [3, 26 + 12, 52 + 0]
            check([k for k, _ in got] == want and all(e < 10 for _, e in got), f'diag slot {n}: pages show C3, A12, B0 ({got})')
    elif normal[0] == 'bran':
        groups = {'orb:' + o: frames_ref(o, normal[2]) for o in normal[1]}
        for n, off in enumerate(tags[b'BRAN']):
            o = m.texobj(0x81003200 + n * 0x20, BASE + off + 0x40)
            m.tb = 0x55555 * (n + 2) ** 3
            ok, img = shown(o, off)
            err, g, k = best(img, groups)
            check(ok and err < 8, f'slot {n}: random animated {g} (err {err:.1f})')


def PERIOD_T(n):
    return b4.PERIOD[n] * 989 * 1024


for v in b4.VARIANTS:
    run(*v)
print('\nALL PASS' if not test_hook.fails else f'\n{test_hook.fails} FAILURES')
