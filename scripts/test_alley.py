"""Emulator test of the Random / Next alley loader: run the REAL Bowling stage-setup
function from main.dol (0x804c79a0) with the Riivolution patches applied, and check
which file name reaches the stage loader each game."""
import sys, os, struct
sys.path.insert(0, os.path.dirname(__file__))
from unicorn.ppc_const import *
import hook
from test_hook import Machine, check, dol
import test_hook

SETUP = 0x804c79a0          # builds the stage name, then bl LoadStage(name, -1, 0)
STOP = 0x81004000


EFFECT_FUNCS = {hook.NEW: 'new', hook.EFFECT_CTOR: 'ctor', hook.EFFECT_START: 'start', hook.EFFECT_KILL: 'kill',
                hook.EFFECT_SET_COLOR: 'color', hook.EFFECT_SET_MTX: 'mtx', hook.EFFECT_UPDATE: 'update',
                0x8023e7c4: 'FREEZE', 0x8023e75c: 'HIDE'}


class AlleyMachine(Machine):
    def __init__(self, mode=None, trail=False, style=0):
        super().__init__()
        patches = (hook.alley_patches(mode) if mode else []) + (hook.trail_patches(style) if trail else [])
        for addr, data, orig in patches:
            if orig is not None:
                cur = self.r32(addr)
                if cur != orig:                  # Riivolution skips a patch whose original doesn't match
                    assert data == cur.to_bytes(4, 'big'), hex(addr)   # (only OK if it's the same patch twice)
                    continue
            self.mu.mem_write(addr, data)
        self.mu.reg_write(UC_PPC_REG_MSR, self.mu.reg_read(UC_PPC_REG_MSR) | 0x2000)   # FP on (as in the game)
        self.seen, self.calls = [], []
        # simulated resource cache (list 0): {record address: (path, data address)}
        self.mgr = 0x81400000
        self.w32(0x806F8120 + hook.RES_MGR_SDA, self.mgr)
        self.cache, self.next_rec = {}, 0x81410000
        self.freed, self.dtors, self.evicted_data = [], [], []
        for f, n in ((hook.RES_FIND, 'find'), (hook.LIST_NEXT, 'next'), (hook.RECORD_DTOR, 'dtor'), (hook.FREE, 'free')):
            self.mu.hook_add(test_hook.UC_HOOK_CODE, self._res, begin=f, end=f, user_data=n)
        # stub every call the setup function makes; record the name given to LoadStage
        self.mu.hook_add(test_hook.UC_HOOK_CODE, self._stub, begin=0x80231000, end=0x80233000)
        for f in EFFECT_FUNCS:
            self.mu.hook_add(test_hook.UC_HOOK_CODE, self._fx, begin=f, end=f)
        self.mu.hook_add(test_hook.UC_HOOK_CODE, self._ball_orig, begin=hook.BALL_UPDATE + 4, end=hook.BALL_UPDATE + 4)
        self.mu.hook_add(test_hook.UC_HOOK_CODE, self._code, begin=hook.TRAIL_ADDR, end=hook.TRAIL_END)   # mftb
        self.mu.hook_add(test_hook.UC_HOOK_CODE, self._code, begin=hook.STAGE_ADDR, end=0x80003000)     # mftb

    def _ret(self, v=None):
        if v is not None:
            self.mu.reg_write(UC_PPC_REG_3, v)
        for r in range(4, 13):
            self.mu.reg_write(UC_PPC_REG_0 + r, 0xBAD00000 + r)
        self.mu.reg_write(UC_PPC_REG_0, 0xBAD00000)
        self.mu.reg_write(UC_PPC_REG_PC, self.mu.reg_read(UC_PPC_REG_LR))

    def _res(self, mu, addr, size, kind):
        r3, r4, r5 = (mu.reg_read(UC_PPC_REG_3), mu.reg_read(UC_PPC_REG_4), mu.reg_read(UC_PPC_REG_5))
        if kind == 'find':
            path = self.cstr(r5)
            hit = [rec for rec, (p, _) in self.cache.items() if p == path] if r4 == 0 else []
            self._ret(hit[0] if hit else 0)
        elif kind == 'next':
            assert r3 == self.mgr + 4, hex(r3)
            recs = list(self.cache)
            nxt = recs[0] if r4 == 0 and recs else (recs[recs.index(r4) + 1] if r4 in recs and recs.index(r4) + 1 < len(recs) else 0)
            self._ret(nxt)
        elif kind == 'dtor':
            assert r4 == 1 and r3 in self.cache
            path, data = self.cache.pop(r3)
            self.dtors.append(path)
            self.evicted_data.append(data)
            self._ret(r3)
        elif kind == 'free':
            self.freed.append(r3)
            self._ret()

    def _stub(self, mu, addr, size, user):
        if addr == hook.STAGE_LOAD:
            name = self.cstr(mu.reg_read(UC_PPC_REG_3))
            self.seen.append(name)
            path = 'Stage/BwlScene/' + name
            mu.mem_write(self.mgr + 0x28, path.encode() + b'\0')
            if not any(p == path for p, _ in self.cache.values()):    # loader: cache miss -> load + new record
                rec = self.next_rec
                self.next_rec += 0x100
                self.cache[rec] = (path, rec + 0x10000)
                self.w32(rec + 0x9C, rec + 0x10000)
            for r in range(4, 13):
                mu.reg_write(UC_PPC_REG_0 + r, 0xBAD00000 + r)
        if addr in (hook.STAGE_LOAD, 0x80231780, 0x80231768, 0x80232594):
            mu.reg_write(UC_PPC_REG_3, 0x81200000)
            mu.reg_write(UC_PPC_REG_PC, mu.reg_read(UC_PPC_REG_LR))

    def _fx(self, mu, addr, size, user):
        name = EFFECT_FUNCS[addr]
        r3, r4 = mu.reg_read(UC_PPC_REG_3), mu.reg_read(UC_PPC_REG_4)
        if name == 'new':
            self.calls.append(('new', r3))
            self.heap = getattr(self, 'heap', 0x81500000)
            mu.reg_write(UC_PPC_REG_3, self.heap)
            self.heap += 0x200
        elif name == 'ctor':
            self.calls.append(('ctor', r3, self.cstr(r4)))
        elif name == 'mtx':
            self.calls.append(('mtx', r3, struct.unpack('>12f', bytes(mu.mem_read(r4, 48)))))
        elif name == 'color':
            regs = [mu.reg_read(UC_PPC_REG_0 + r) & 0xFF for r in (4, 5, 6, 7)]
            self.calls.append(('color', r3, tuple(regs), mu.reg_read(UC_PPC_REG_8)))
        elif name == 'start':
            self.calls.append(('start', r3, chr(self.mu.mem_read(r3 + 4 + hook.NAME_LETTER, 1)[0])))
        else:
            self.calls.append((name, r3))
        for r in range(5, 13):                   # callee may clobber volatile registers
            mu.reg_write(UC_PPC_REG_0 + r, 0xDEAD0000 + r)
        mu.reg_write(UC_PPC_REG_0, 0xDEAD0000)
        mu.reg_write(UC_PPC_REG_PC, mu.reg_read(UC_PPC_REG_LR))

    def _ball_orig(self, mu, addr, size, user):
        # the real ball update (after its first instruction 'stwu r1,-0xd0(r1)'): just return
        self.orig_calls += 1
        mu.reg_write(UC_PPC_REG_1, mu.reg_read(UC_PPC_REG_1) + 0xD0)
        mu.reg_write(UC_PPC_REG_PC, mu.reg_read(UC_PPC_REG_LR))

    orig_calls = 0

    def ball_frame(self, obj, x, y, z, index=0):
        mu = self.mu
        self.mu.mem_write(obj + 0x44, struct.pack('>12f', 1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z))
        self.w32(obj + 0x78, index)
        sp = 0x81700000
        mu.reg_write(UC_PPC_REG_1, sp)
        mu.reg_write(UC_PPC_REG_3, obj)
        for r in range(14, 32):
            mu.reg_write(UC_PPC_REG_0 + r, 0x1111 * r)
        mu.reg_write(UC_PPC_REG_LR, STOP)
        n = len(self.calls)
        mu.emu_start(hook.BALL_UPDATE, STOP, count=3000)
        ok = mu.reg_read(UC_PPC_REG_1) == sp and all(mu.reg_read(UC_PPC_REG_0 + r) == 0x1111 * r for r in range(14, 32))
        return ok, self.calls[n:]

    def cstr(self, a):
        b = bytes(self.mu.mem_read(a, 32))
        return b[:b.index(b'\0')].decode()

    def setup(self, hundred=False):
        mu = self.mu
        obj = 0x81300000
        mu.mem_write(obj, bytes(0x40))
        self.w32(obj + 0x18, 1 if hundred else 0)
        sp = 0x81700000
        mu.reg_write(UC_PPC_REG_1, sp)
        mu.reg_write(UC_PPC_REG_2, 0x806FE080)
        mu.reg_write(UC_PPC_REG_13, 0x806F8120)
        mu.reg_write(UC_PPC_REG_3, obj)
        for r in range(14, 32):
            mu.reg_write(UC_PPC_REG_0 + r, 0x1111 * r)
        mu.reg_write(UC_PPC_REG_LR, STOP)
        n = len(self.seen)
        mu.emu_start(SETUP, STOP, count=5000)
        ok = mu.reg_read(UC_PPC_REG_1) == sp and all(mu.reg_read(UC_PPC_REG_0 + r) == 0x1111 * r for r in range(14, 32))
        assert len(self.seen) == n + 1
        return ok, self.seen[-1]


def main():
    files = hook.ALLEY_FILES
    print('1. Random: keeps the cached alley on restarts (no reloads), new roll after Bowling was left')
    m = AlleyMachine('V')
    m.cache = {}
    names = []
    for g in range(6):
        m.tb = 0x1234567 * (g + 5)
        ok, name = m.setup()
        names.append(name)
    check(len(set(names)) == 1 and names[0] in files, f'6 games in one visit: always {names[0]}')
    check(not m.dtors and not m.freed and len(m.cache) == 1, 'nothing evicted or freed; one alley cached (like the stock game)')
    m.cache.clear()                                   # Bowling was left: the cache heap went away
    later = []
    for g in range(4):
        m.cache.clear()
        m.tb = 0x89ABC * (g + 11)
        ok, name = m.setup()
        later.append(name)
    check(all(n in files for n in later) and all(a_ != b for a_, b in zip([names[0]] + later, later)),
          f'each new visit rolls a different alley: {later}')
    m.w32(hook.ALLEY_REC, 0x12345678)
    m.cache.clear()
    ok, name = m.setup()
    check(ok and name in files and not m.dtors, 'garbage remembered pointer: rolls a new alley, touches nothing')
    import random
    rng = random.Random(3)
    picks = []
    for g in range(60):
        m.cache.clear()
        m.tb = rng.getrandbits(40)
        ok, name = m.setup()
        picks.append(name)
    check(set(picks) == set(files) and all(a_ != b for a_, b in zip(picks, picks[1:])), 'over 60 visits: every theme, never the same twice in a row')
    cur = bytes(m.mu.mem_read(hook.THEME_CUR, 3))
    check(cur[1] == hook.KEY and files[cur[0] - 1] == picks[-1] and cur[2] == 0xFF, f'live pins follow the alley; Whiteout colourway re-rolls ({cur.hex()})')

    print('3. 100-Pin and "no alley option" are untouched')
    m = AlleyMachine('V')
    ok, name = m.setup(hundred=True)
    check(ok and name == '100Pin.carc', f'100-Pin loads {name}')
    m.mu.mem_write(hook.THEME_MODE, b'\0')
    ok, name = m.setup()
    check(ok and name == 'Normal.carc', f'mode byte 0 loads {name}')
    m.mu.mem_write(hook.THEME_MODE, b'G')
    ok, name = m.setup()
    check(ok and name == 'Normal.carc', f'stray mode byte loads {name}')

    m.mu.mem_write(hook.THEME_MODE, b'V\xff\x00')
    ok, name = m.setup()
    check(ok and name == 'Normal.carc', f'Random without the key byte loads {name}')

    print('4. ball trail (particle bursts)')
    m = AlleyMachine(trail=True)
    ok, name = m.setup()
    pool = [hook.TRAIL_POOL + hook.EFFECT_SIZE * i for i in range(hook.TRAIL_N)]
    ctors = [c for c in m.calls if c[0] == 'ctor']
    check(ok and name == 'Normal.carc', f'trail on, no alley option: stage loads {name}')
    check([c[1] for c in ctors] == pool and all(c[2] == hook.TRAIL_STYLES[0][1] for c in ctors),
          f'Bowling setup creates {len(ctors)} "{hook.TRAIL_STYLES[0][1]}" effect objects')
    check([m.r32(hook.TRAIL_EFFS + 4 * i) for i in range(hook.TRAIL_N)] == pool, 'pool remembered')
    check(not any(c[0] == 'new' for c in m.calls), 'nothing is allocated from the game\'s heaps')
    m.calls.clear()
    for g in range(5):
        m.setup()
    check(not any(c[0] == 'new' for c in m.calls) and [c[1] for c in m.calls if c[0] == 'ctor'] == pool * 5,
          '5 more Bowling loads: same static objects rebuilt in place, still no allocation')
    ball, rack, refl = 0x81600000, 0x81610000, 0x81620000

    def roll(m, index=0, dup=False, mirror=False):
        """held -> released -> down the lane -> pit; rack ball idles; returns per-frame call lists"""
        log, oks = [], []
        path = [(0, 1.09, z) for z in (30, 20, 10, 4, 0.5)] + [(0.2 * i, 1.09, -1.5 - 6.0 * i) for i in range(31)] \
            + [(6, 1.0, -187.0), (6, -3.0, -190.0), (6, -3.0, -190.0)]
        for x, y, z in path:
            c = []
            if mirror:                   # the lane reflection: same ball mirrored below the lane, updated first
                ok, c1 = m.ball_frame(refl, x, -y, z, index)
                oks.append(ok)
                c += c1
            ok, c2 = m.ball_frame(ball, x, y, z, index)
            oks.append(ok)
            c += c2
            if dup:                      # the game updating the same ball twice in one frame
                ok, c3 = m.ball_frame(ball, x, y, z, index)
                oks.append(ok)
                c += c3
            log.append(((x, y, z), c))
            ok, c4 = m.ball_frame(rack, 5, 1.09, 86, 1)
            oks.append(ok and not c4)
        return log, all(oks)

    for dup, mirror in ((False, False), (True, False), (False, True), (True, True)):
        tag = (' [2 updates/frame]' if dup else '') + (' [reflection]' if mirror else '')
        m.calls.clear()
        log, ok = roll(m, dup=dup, mirror=mirror)
        allc = [k for _, c in log for k in c]
        check(ok, 'stack + saved registers intact; rack ball never touches the effects' + tag)
        check(not any(k[0] in ('FREEZE', 'HIDE') for k in allc), 'never freezes / hides an effect' + tag)
        bursts = [(i, [k for k in c if k[0] == 'start']) for i, (_, c) in enumerate(log)]
        bursts = [(i, st) for i, st in bursts if st]
        frames = [i for i, _ in bursts]
        first = log[frames[0]][0] if frames else None
        check(first is not None and first[2] < -1, f'first burst just after the foul line (z={first and first[2]})' + tag)
        check(len(frames) >= 14 and all(b - a_ == 2 for a_, b in zip(frames, frames[1:])), f'a burst every 2nd frame while rolling ({len(frames)} bursts)' + tag)
        check(all(len(st) == 1 for _, st in bursts), 'one burst per burst frame' + tag)
        used = [st[0][1] for _, st in bursts]
        idx = [pool.index(u) for u in used]
        check(all((b - a_) % hook.TRAIL_N == 1 for a_, b in zip(idx, idx[1:])), 'pool used round-robin' + tag)
        seq_ok = True
        for i, _ in bursts:
            ks = [k[0] for k in log[i][1] if k[0] in ('kill', 'start', 'color', 'mtx', 'update')]
            seq_ok &= ks == ['kill', 'start', 'color', 'mtx', 'update']
        check(seq_ok, 'each burst: stop old instance, start, tint, place, update' + tag)
        L = hook.LEAD_FRAMES
        def ahead(i, j):
            return log[i][0][j] + (log[i][0][j] - log[i - 1][0][j]) * L
        check(all(abs(k[2][3] - ahead(i, 0)) < 1e-3 and abs(k[2][7] - ahead(i, 1)) < 1e-3 and abs(k[2][11] - ahead(i, 2)) < 1e-3
                  for i, _ in bursts if i > 0 for k in log[i][1] if k[0] == 'mtx'),
              f'bursts placed {L:g} frames ahead along the real ball\'s path (not its reflection)' + tag)
        ends = [i for i, (p, c) in enumerate(log) if sum(1 for k in c if k[0] == 'kill') == hook.TRAIL_N]
        check(len(ends) == 1 and log[ends[0]][0][2] <= -186, f'all emitters stopped once, at the pit ({ends})' + tag)
        check(all(not c for p, c in log if p[2] > -1), 'nothing before the foul line' + tag)
    print('   colours / styles')
    def colours(index, tier=None, style=1):
        mm = AlleyMachine(trail=True, style=style)
        mm.setup()
        if tier:
            mm.mu.mem_write(hook.TIER_CFG + (index & 3), tier.encode())
        mm.tb = 5 << 20
        log, _ = roll(mm, index)
        return [k for _, c in log for k in c if k[0] == 'color']
    for idx, want, label in ((0, hook.TRAIL_COLORS[0], 'blue ball'), (1, hook.TRAIL_COLORS[1], 'red ball'),
                             (3, hook.TRAIL_COLORS[3], 'yellow ball'), (6, hook.TRAIL_COLORS[4], 'Pro orb = violet')):
        cols = colours(idx)
        check(cols and all(k[2] == tuple(want) + (255,) and k[3] == 3 for k in cols), f'{label} {cols[0][2] if cols else None}')
    cols = colours(5, 'G')
    check(cols and all(k[2] == tuple(hook.TRAIL_COLORS[5]) + (255,) for k in cols), 'Pro Gold = gold')
    cols = colours(2, 'D')
    check(cols and all(k[2] == tuple(hook.TRAIL_COLORS[2]) + (255,) for k in cols), 'Diamond byte on a NON-Pro ball: still the ball colour')
    for st, (label, eff, tint) in enumerate(hook.TRAIL_STYLES):
        mm = AlleyMachine(trail=True, style=st)
        mm.setup()
        names = {c[2] for c in mm.calls if c[0] == 'ctor'}
        cols = colours(0, style=st)
        want = tuple(hook.TRAIL_COLORS[0]) + (255,) if tint == 1 else (255, 255, 255, 255)
        check(names == {eff} and cols and (tint == 2 or all(k[2] == want for k in cols)), f'style "{label}": {eff}, mode {tint}')
    mm = AlleyMachine(trail=True, style=1)
    mm.setup()
    mm.mu.mem_write(hook.TIER_CFG + 0, b'D')
    seen = []
    for k in range(96):
        mm.tb = (k * 16) << hook.RAINBOW_SHIFT
        mm.ball_frame(ball, 0, 1.09, -2.0 - k, 4)
        cs = [c for c in mm.calls if c[0] == 'color']
        if cs:
            seen.append(cs[-1][2][:3])
        mm.calls.clear()
    mm.calls.clear()
    import colorsys
    hues = [colorsys.rgb_to_hsv(*[v / 255 for v in c])[0] for c in seen]
    sats = [colorsys.rgb_to_hsv(*[v / 255 for v in c])[1] for c in seen]
    check(len(seen) >= 40 and min(sats) > 0.99, f'Diamond (index 4 = blue Pro) = fully saturated colours ({len(seen)} bursts)')
    steps = [((h2 - h1) % 1.0) for h1, h2 in zip(hues, hues[1:])]
    check(all(0.0 < st < 0.05 for st in steps), f'Diamond hue sweeps round the colour wheel (max step {max(steps):.3f})')
    print('   Pro orb colours follow the ball')
    def orb_colour(slot, header_tag, value):
        mm = AlleyMachine(trail=True, style=1)
        mm.setup()
        img = 0x81700400 + 0x100 * slot
        hdr = bytearray(0x40)
        hdr[0:4] = b'TEX0'
        if header_tag == b'BRAN':
            hdr[0x30:0x40] = b'BRAN' + struct.pack('>BBHHHi', 6, 6, value, 6, 100, 0)
        else:
            hdr[0x30:0x40] = b'BANM' + struct.pack('>BBHIi', value, 16, 4, 1000, 0)
        mm.mu.mem_write(img - 0x40, bytes(hdr))
        mm.w32(hook.PRO_IMG + 4 * slot, img)
        mm.tb = 3 << 20
        log, _ = roll(mm, 4 + slot)
        return [k[2][:3] for _, c in log for k in c if k[0] == 'color']
    for k in range(6):
        cols = orb_colour(1, b'BRAN', k)
        check(cols and all(c == hook.ORB_COLORS[k] for c in cols), f'random orb set {k} -> {hook.ORB_COLORS[k]}')
    cols = orb_colour(2, b'BANM', 3)
    check(cols and all(c == hook.ORB_COLORS[2] for c in cols), 'single-orb build (orb id 3 = Inferno) -> its colour')
    cols = orb_colour(0, b'BANM', 0)
    check(cols and all(c == hook.TRAIL_COLORS[4] for c in cols), 'unknown orb -> default Pro violet')
    cols = orb_colour(0, b'BRAN', 9)
    check(cols and all(c == hook.TRAIL_COLORS[4] for c in cols), 'out-of-range set -> default Pro violet')
    print('   Match ball (Auto): effect + colour per design')
    def fake_header(addr, tag, payload):
        hdr = bytearray(0x40)
        hdr[0:4] = b'TEX0'
        hdr[0x30:0x40] = tag + payload
        return hdr
    def match(index, setup):
        mm = AlleyMachine(trail=True, style=0)
        mm.setup()
        setup(mm)
        mm.tb = 7 << 20
        log, _ = roll(mm, index)
        starts = [k for _, c in log for k in c if k[0] == 'start']
        cols = [k[2][:3] for _, c in log for k in c if k[0] == 'color']
        return list(zip([k[2] for k in starts], cols))
    def regular(slot, design):
        def f(mm):
            img = 0x81700800 + 0x100 * slot
            mm.mu.mem_write(img - 0x40, bytes(fake_header(img, b'BRND', bytes([slot + 1, 8]) + struct.pack('>HIi', design, 100, 0))))
            mm.w32(hook.NORM_IMG + 4 * slot, img)
        return f
    def want_seq(prof, n):
        out = []
        for i, (letter, part) in enumerate((('a', prof[0]), ('b', prof[1])) * n):
            pass
        return out
    import build4
    from make_pool import POOL
    from make_orbs import ORDER
    for d, name in enumerate(POOL):
        seq = match(d % 4, regular(d % 4, d))
        aura, sparks = hook.MATCH_PROFILES[d]
        letters = {l for l, _ in seq}
        ok = bool(seq)
        exp_letters = {x for x, p in (('a', aura), ('b', sparks)) if p is not None}
        ok &= letters == exp_letters
        if aura is not None and sparks is not None:
            ok &= all(l1 != l2 for (l1, _), (l2, _) in zip(seq, seq[1:]))          # alternate
        for l, c in seq:
            part = aura if l == 'a' else sparks
            ok &= (c == part) if part not in (None, 'rainbow') else (part == 'rainbow' and max(c) == 255 and min(c) == 0)
        check(ok, f'regular ball "{name}": {"aura+sparks" if len(exp_letters) == 2 else ("aura" if "a" in exp_letters else "sparks")}, colours match')
    def pro_set(slot, k):
        def f(mm):
            img = 0x81700c00 + 0x100 * slot
            mm.mu.mem_write(img - 0x40, bytes(fake_header(img, b'BRAN', struct.pack('>BBHHHi', 6, 6, k, 6, 100, 0))))
            mm.w32(hook.PRO_IMG + 4 * slot, img)
        return f
    for k, name in enumerate(ORDER):
        seq = match(4 + 1, pro_set(1, k))
        aura, sparks = hook.MATCH_PROFILES[8 + k]
        ok = bool(seq) and all(c == (aura if l == 'a' else sparks) for l, c in seq)
        check(ok, f'Pro orb "{name}": {sorted({l for l, _ in seq})} {aura} / {sparks}')
    seq = match(4 + 2, lambda mm: mm.mu.mem_write(hook.TIER_CFG + 2, b'G'))
    check(seq and all(c == hook.MATCH_PROFILES[14][0 if l == 'a' else 1] for l, c in seq) and {l for l, _ in seq} == {'a', 'b'}, 'Gold: gold aura + glitter')
    seq = match(4 + 0, lambda mm: mm.mu.mem_write(hook.TIER_CFG + 0, b'D'))
    ok = seq and {l for l, _ in seq} == {'a', 'b'}
    ok = ok and all((c == hook.WHITE) if l == 'b' else (max(c) == 255 and min(c) == 0) for l, c in seq)
    check(ok, 'Prismatic Diamond: rainbow aura + white sparkle')
    seq = match(3, lambda mm: None)
    check(seq and all(l == 'a' and c == hook.TRAIL_COLORS[3] for l, c in seq), 'unknown design: aura in the ball colour')

    print('   neighbouring lanes (CPU Miis) are ignored')
    mm = AlleyMachine(trail=True)
    mm.setup()
    cpu = 0x81630000
    oks, starts_cpu, starts_me = [], 0, 0
    for i in range(30):
        z = -2.0 - 6.0 * i
        ok, c = mm.ball_frame(cpu, 16.8, 1.09, z - 30, 0)      # a CPU ball already rolling on the next lane
        oks.append(ok)
        starts_cpu += sum(1 for k in c if k[0] == 'start')
        ok, c = mm.ball_frame(ball, 0.3, 1.09, z, 0)
        oks.append(ok)
        starts_me += sum(1 for k in c if k[0] == 'start')
    check(all(oks) and starts_cpu == 0 and starts_me >= 12, f'my ball gets the trail ({starts_me} bursts), the neighbour\'s gets none')
    print('   ball return / other balls')
    m = AlleyMachine(trail=True)
    m.setup()
    ok, c = m.ball_frame(ball, 6, 1.09, -150)
    ok2, c2 = m.ball_frame(ball, 6, 1.09, -140)
    check(ok and ok2 and not any(k[0] == 'start' for k in c + c2), 'no bursts for a ball moving toward the player')
    m2 = AlleyMachine(trail=True)
    m2.mu.mem_write(hook.TRAIL_KEY, b'\0')
    ok, name = m2.setup()
    check(ok and not any(k[0] in ('new', 'ctor') for k in m2.calls), 'no key byte: no effect objects are created')
    ok, c = m2.ball_frame(ball, 0, 1.09, -20)
    check(ok and not c, 'no key byte: ball updates untouched')
    print('   live pins follow the alley')
    m3 = AlleyMachine('V')
    for g in range(6):
        m3.cache.clear()
        m3.tb = 0x51ED * (g + 3) * 104729
        ok, name = m3.setup()
        cur, key = bytes(m3.mu.mem_read(hook.THEME_CUR, 2))
        check(ok and key == hook.KEY and files[cur - 1] == name, f'game {g}: {name} -> pin theme {cur}') if g < 3 else None

    print('5. alley Random + trail together (shared patches applied twice)')
    m = AlleyMachine('V', trail=True)
    m.tb = 123456789
    ok, name = m.setup()
    check(ok and name in files and m.r32(hook.TRAIL_EFFS) == hook.TRAIL_POOL, f'both work: {name} + trail effects')

    print('6. ball hook still works with the alley patches applied')
    m = AlleyMachine('V')
    d = m.tex0(0x80A00000, b'BANM', count=16, param=5)
    o = m.texobj(0x81003200, d)
    m.tb = 3 * 5 * 989 * 1024 + 100
    ok, img3 = m.load(o)
    check(ok and img3 == (0x94000000 | ((d + 3 * test_hook.STRIDE) & 0x3FFFFFFF) >> 5), 'animated texture -> frame 3')

    print('\nALL PASS' if test_hook.fails == 0 else f'\n{test_hook.fails} FAILED')
    sys.exit(1 if test_hook.fails else 0)


if __name__ == '__main__':
    main()
