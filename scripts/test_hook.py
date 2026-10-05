"""Run the REAL GXLoadTexObj from main.dol, patched with our hook, inside a
PowerPC emulator (unicorn) and check what gets written to the GPU FIFO."""
import sys, os, struct
sys.path.insert(0, os.path.dirname(__file__))
from unicorn import Uc, UC_ARCH_PPC, UC_MODE_PPC32, UC_MODE_BIG_ENDIAN, UC_HOOK_MEM_WRITE, UC_HOOK_CODE, UcError
from unicorn.ppc_const import *
from dol import Dol
import hook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dol = Dol(os.path.join(ROOT, 'work/disc/sys/main.dol'))
STOP = 0x81004000
STRIDE = 21824
fails = 0


def check(cond, msg):
    global fails
    print(('  PASS ' if cond else '  FAIL ') + msg)
    if not cond:
        fails += 1


class Machine:
    def __init__(self):
        mu = self.mu = Uc(UC_ARCH_PPC, UC_MODE_PPC32 | UC_MODE_BIG_ENDIAN)
        mu.mem_map(0x80000000, 0x01800000)          # MEM1
        mu.mem_map(0x90000000, 0x00400000)          # part of MEM2
        mu.mem_map(0xCC000000, 0x00010000)          # hardware regs / WG pipe
        for o, a, s, _ in dol.secs:
            mu.mem_write(a, dol.b[o:o + s])
        for addr, data, orig in hook.patches():    # exactly what Riivolution writes
            if orig is not None:
                assert self.r32(addr) == orig, hex(addr)  # same check Riivolution makes
            mu.mem_write(addr, data)
        self.fifo = []
        mu.hook_add(UC_HOOK_MEM_WRITE, self._w, begin=0xCC008000, end=0xCC008003)
        self.tb = 0
        mu.hook_add(UC_HOOK_CODE, self._code, begin=0x80001A00, end=0x80001F00)
        # fake __GXData with texture-region / TLUT-region callbacks
        gxdata = 0x81000000
        self.w32(0x806FE080 - 0x79E0, gxdata)
        stub = 0x81001000
        for i, w in enumerate([0x3C608100, 0x60632000, 0x4E800020]):   # lis r3,0x8100; ori r3,r3,0x2000; blr
            self.w32(stub + 4 * i, w)
        self.w32(gxdata + 0x518, stub)
        self.w32(gxdata + 0x51C, stub)

    def _w(self, mu, access, addr, size, value, user):
        self.fifo.append((size, value & ((1 << (8 * size)) - 1)))

    def _code(self, mu, addr, size, user):
        # emulate mftb / mftbu deterministically (time base = self.tb)
        w = struct.unpack('>I', mu.mem_read(addr, 4))[0]
        if (w >> 26) == 31 and ((w >> 1) & 0x3FF) == 371:
            rd = (w >> 21) & 31
            tbr = ((w >> 16) & 31) | (((w >> 11) & 31) << 5)
            val = (self.tb >> 32) if tbr == 269 else (self.tb & 0xFFFFFFFF)
            mu.reg_write(UC_PPC_REG_0 + rd, val)
            mu.reg_write(UC_PPC_REG_PC, addr + 4)

    def w32(self, a, v): self.mu.mem_write(a, struct.pack('>I', v & 0xFFFFFFFF))
    def r32(self, a): return struct.unpack('>I', self.mu.mem_read(a, 4))[0]
    def r16(self, a): return struct.unpack('>H', self.mu.mem_read(a, 2))[0]

    def tex0(self, at, tag=None, count=0, param=0, stride=STRIDE, rel=0):
        hdr = bytearray(0x40)
        hdr[0:4] = b'TEX0'
        if tag:
            hdr[0x30:0x40] = tag + struct.pack('>HHIi', count, param, stride, rel)
        self.mu.mem_write(at, bytes(hdr))
        return at + 0x40                            # image data address

    def texobj(self, at, image_virt):
        phys = image_virt & 0x3FFFFFFF
        self.mu.mem_write(at, bytes(0x20))
        self.w32(at + 0x0C, 0x94000000 | (phys >> 5))
        return at

    def load(self, obj, mapid=0):
        mu = self.mu
        self.fifo = []
        sp = 0x81700000
        mu.reg_write(UC_PPC_REG_1, sp)
        mu.reg_write(UC_PPC_REG_2, 0x806FE080)
        mu.reg_write(UC_PPC_REG_13, 0x806F8120)
        mu.reg_write(UC_PPC_REG_3, obj)
        mu.reg_write(UC_PPC_REG_4, mapid)
        for r in range(14, 32):
            mu.reg_write(UC_PPC_REG_0 + r, 0x1111 * r)
        mu.reg_write(UC_PPC_REG_LR, STOP)
        mu.emu_start(hook.GXLOADTEXOBJ, STOP, count=2000)
        ok = mu.reg_read(UC_PPC_REG_1) == sp and all(mu.reg_read(UC_PPC_REG_0 + r) == 0x1111 * r for r in range(14, 32))
        # image3 is the 6th BP write (0x61 prefix byte + word pairs)
        words = [v for s, v in self.fifo if s == 4]
        img3 = [v for v in words if (v >> 24) in (0x94, 0x95, 0x96, 0x97, 0xB4, 0xB5, 0xB6, 0xB7)]
        return ok, (img3[0] if img3 else None)


def phys5(v): return (v & 0x3FFFFFFF) >> 5


def main():
    global fails
    m = Machine()
    print('1. untagged texture passes through untouched')
    d = m.tex0(0x80900000)
    o = m.texobj(0x81003000, d)
    ok, img3 = m.load(o)
    check(ok, 'stack + callee-saved registers preserved')
    check(img3 == (0x94000000 | phys5(d)), f'GPU got original address ({img3 and hex(img3)})')
    check(m.r32(o + 0x0C) & 0xFFFFFF == phys5(d), 'texobj unchanged')

    print('2. non-texture garbage / null address')
    o2 = m.texobj(0x81003100, 0x80000000)
    ok, img3 = m.load(o2)
    check(ok and img3 == 0x94000000, 'null image pointer passes through without reading low memory')

    print('3. animated texture follows the time base')
    d = m.tex0(0x80A00000, b'BANM', count=16, param=5)       # 5/60 s per frame = 12 fps
    o = m.texobj(0x81003200, d)
    TICKS_PER_FRAME = 5 * 989 * 1024
    for frame in [0, 1, 7, 15, 16, 37]:
        m.tb = frame * TICKS_PER_FRAME + 1000
        ok, img3 = m.load(o)
        want = d + (frame % 16) * STRIDE
        check(ok and img3 == (0x94000000 | phys5(want)), f't=frame {frame:2d} -> GPU image = frame {frame % 16}')
        check(m.r32(o + 0x0C) & 0xFFFFFF == phys5(d), '   texobj restored to frame 0 afterwards')
    m.tb = (1 << 40) + 12345                                  # large time base: upper word in use
    ok, img3 = m.load(o)
    check(ok and img3 is not None and (phys5(img3 << 5) - phys5(d)) * 32 % STRIDE == 0, 'huge time base still yields a valid frame')

    print('4. random texture picks once and remembers; pool via rel offset; MEM2')
    pool = 0x90100000
    slots = []
    for i, base in enumerate([0x90000100, 0x90004100, 0x90008100, 0x9000C100]):
        dd = m.tex0(base, b'BRND', count=8, param=0xFFFF, rel=pool - (base + 0x40))
        slots.append((dd, m.texobj(0x81003300 + 0x20 * i, dd)))
    picks = []
    for k, (dd, oo) in enumerate(slots):
        m.tb = 0x123456789 + k * 37
        ok, img3 = m.load(oo, mapid=0)
        idx = ((img3 & 0xFFFFFF) * 32 + 0x80000000 - (pool | 0x80000000)) // STRIDE if img3 else None
        stamp = m.r16(dd - 0x40 + 0x36)
        check(ok and stamp == idx and 0 <= idx < 8, f'slot {k}: picked design {idx}, stamped')
        m.tb += 999999
        ok, img3b = m.load(oo)
        check(img3b == img3, f'slot {k}: same design on the next draw')
        picks.append(idx)
    print('   picks:', picks)
    # reload (fresh header) gives a new roll
    dd, oo = slots[0]
    rolls = set()
    for t in range(20):
        m.tex0(dd - 0x40, b'BRND', count=8, param=0xFFFF, rel=pool - dd)
        m.tb = 1000003 * (t + 1) ** 3
        ok, img3 = m.load(oo)
        rolls.add(img3)
    check(len(rolls) >= 5, f'fresh loads re-roll ({len(rolls)} different designs over 20 loads)')

    print('5. other GX map ids work (register id byte kept)')
    m.tb = 0
    d = m.tex0(0x80B00000, b'BANM', count=4, param=6)
    o = m.texobj(0x81003400, d)
    ok, img3 = m.load(o, mapid=2)
    check(ok and img3 is not None, 'map id 2 load goes through')
    words = [v for s, v in m.fifo if s == 4]
    check(any((v >> 24) == 0x96 and (v & 0xFFFFFF) == phys5(d) for v in words), 'GPU got TX_SETIMAGE3 for map 2 with frame 0')

    print('6. random animated set (BRAN): one set per load, animates inside it')
    pool = 0x90200000
    sets, nfr, period, stride = 6, 8, 5, 16384
    TPF = period * 989 * 1024
    for trial in range(6):
        base = 0x90180000 + trial * 0x8000
        hdr = bytearray(0x40); hdr[0:4] = b'TEX0'
        hdr[0x30:0x40] = b'BRAN' + struct.pack('>BBHHHi', sets, nfr, 0xFFFF, period, stride >> 5, pool - (base + 0x40))
        m.mu.mem_write(base, bytes(hdr))
        dd = base + 0x40
        oo = m.texobj(0x81003500 + trial * 0x20, dd)
        m.tb = 0xABCDEF * (trial + 3) ** 2
        chosen = None
        okall = True
        for fr in range(0, 2 * nfr + 3):
            t0 = (m.tb // TPF + 1) * TPF + 100        # next frame boundary
            m.tb = t0
            ok, img3 = m.load(oo)
            addr = ((img3 & 0xFFFFFF) << 5) | 0x80000000
            idx = (addr - (pool | 0x80000000)) // stride
            sset, sfr = divmod(idx, nfr)
            want_fr = (t0 >> 10) // (period * 989) % nfr
            chosen = sset if chosen is None else chosen
            okall &= ok and (addr - pool) % stride == 0 and sset == chosen and sfr == want_fr and 0 <= sset < sets
        stamp = m.r16(dd - 0x40 + 0x36)
        check(okall and stamp == chosen, f'trial {trial}: set {chosen} kept for every frame, frames advance in order')
    print('8. per-player tier (BTIR + Riivolution tier bytes)')
    def pool_tex(at, n):
        return m.tex0(at, b'BANM', count=n, param=4, rel=0)
    base_d = pool_tex(0x90300000, 3); gold_d = pool_tex(0x90310000, 3); dia_d = pool_tex(0x90320000, 3)
    objs = []
    for sl in range(4):
        slot = 0x902F0000 + sl * 0x1000
        sd = slot + 0x40
        hdr = bytearray(0x40); hdr[0:4] = b'TEX0'
        hdr[0x30:0x40] = b'BTIR' + struct.pack('>BBhii', sl, 0, ((base_d - 0x40) - sd) // 32, (gold_d - 0x40) - sd, (dia_d - 0x40) - sd)
        m.mu.mem_write(slot, bytes(hdr))
        objs.append((sd, m.texobj(0x81003600 + sl * 0x20, sd)))
    m.tb = 0
    def shows(sl):
        ok, img3 = m.load(objs[sl][1])
        for name, dd in (('orb', base_d), ('gold', gold_d), ('diamond', dia_d)):
            if img3 == (0x94000000 | phys5(dd)):
                return ok, name
        return ok, None
    m.mu.mem_write(hook.TIER_CFG, bytes([0x13, 0xA7, 0xFF, 0x00]))      # unset / random garbage
    check(all(shows(sl) == (True, 'orb') for sl in range(4)), 'no tier chosen (any leftover byte): every Pro ball stays an orb')
    m.mu.mem_write(hook.TIER_CFG, b'D')                                # P1 Diamond only
    check(shows(0) == (True, 'diamond') and all(shows(sl)[1] == 'orb' for sl in (1, 2, 3)), 'P1 Diamond: only player 1 changes')
    m.mu.mem_write(hook.TIER_CFG, b'DG\x00G')
    got = [shows(sl)[1] for sl in range(4)]
    check(got == ['diamond', 'gold', 'orb', 'gold'], f'P1 Diamond, P2 Gold, P4 Gold: {got}')
    check(m.r32(objs[0][1] + 0x0C) & 0xFFFFFF == phys5(objs[0][0]), 'texobj restored to the slot texture')
    for a_, dsz in ((t, b) for t, b in [(p_[0], len(p_[1])) for p_ in hook.patches()]):
        check(not (a_ <= hook.TIER_CFG < a_ + dsz), f'boot patch at {a_:#x} does not overwrite the tier bytes')

    print('7b. random design remembers the image per colour slot (byte 0x34 = slot + 1)')
    m.mu.mem_write(hook.NORM_IMG, bytes(16))
    for sl in range(4):
        base = 0x90200100 + 0x4000 * sl
        hdr = bytearray(0x40); hdr[0:4] = b'TEX0'
        hdr[0x30:0x40] = b'BRND' + bytes([sl + 1, 8]) + struct.pack('>HIi', 0xFFFF, STRIDE, 0)
        m.mu.mem_write(base, bytes(hdr))
        ok, _ = m.load(m.texobj(0x81003900 + 0x20 * sl, base + 0x40))
        check(ok and m.r32(hook.NORM_IMG + 4 * sl) == base + 0x40 and m.r16(base + 0x36) < 8, f'slot {sl}: remembered, rolled design {m.r16(base + 0x36)}')
    print('8b. tier redirect remembers the resolved Pro image per slot (ball trail colour)')
    imgs = [m.r32(hook.PRO_IMG + 4 * sl) for sl in range(4)]
    tags = [bytes(m.mu.mem_read(i - 0x10, 4)) if i else None for i in imgs]
    check(all(i != 0 for i in imgs) and all(t in (b'BANM', b'BRAN', b'BRND') for t in tags), f'PRO_IMG per slot -> tagged images {tags}')
    print('9. alley theme (BTHM): pool index = current theme, 0 when unknown; Whiteout -> colourway')
    dd = m.tex0(0x90330000, b'BTHM', count=9, param=0, rel=0)
    o = m.texobj(0x81003700, dd)
    for cur, key, want in [(0, 0xA5, 0), (1, 0xA5, 1), (4, 0xA5, 4), (9, 0xA5, 0), (200, 0xA5, 0), (3, 0x00, 0), (3, 0xA5, 3)]:
        m.mu.mem_write(hook.THEME_CUR, bytes([cur, key, 0xFF]))
        ok, img3 = m.load(o)
        check(ok and img3 == (0x94000000 | phys5(dd + want * STRIDE)), f'theme byte {cur:3d} key {key:02X} -> image {want}')
    seen = set()
    for k in range(24):
        m.mu.mem_write(hook.THEME_CUR, bytes([5, 0xA5, 0xFF]))       # a new visit: colourway re-rolls
        m.tb = 0x9E3779B97F4A * (k + 3) + 12345 * k
        ok, img3 = m.load(o)
        var = m.mu.mem_read(hook.PIN_VAR, 1)[0]
        ok2, img3b = m.load(o)                                       # ...and then stays
        seen.add(var)
        check(ok and ok2 and var < 4 and img3 == img3b == (0x94000000 | phys5(dd + (5 + var) * STRIDE)), f'Whiteout -> colourway {var} (image {5 + var}), kept') if k < 3 else None
    check(seen == {0, 1, 2, 3}, f'all 4 colourways come up ({sorted(seen)})')
    print('10. Whiteout far-lane pins (BPIN) use the same colourway')
    pp = m.tex0(0x90340000, b'BPIN', count=4, param=0, rel=0)
    o2 = m.texobj(0x81003800, pp)
    for var in range(4):
        m.mu.mem_write(hook.PIN_VAR, bytes([var]))
        ok, img3 = m.load(o2)
        check(ok and img3 == (0x94000000 | phys5(pp + var * STRIDE)), f'colourway {var} -> far-lane pin image {var}')
    print('\nALL PASS' if not fails else f'\n{fails} FAILURES')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
