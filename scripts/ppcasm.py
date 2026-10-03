"""Tiny PowerPC assembler for the handful of instructions the hook needs.
Two-pass, label-aware. Every encoding is cross-checked with capstone in tests."""
import struct

def _r(x):
    return int(str(x).lower().lstrip('r'))

def _s16(v):
    assert -0x8000 <= v <= 0x7FFF, v
    return v & 0xFFFF

def _u16(v):
    assert 0 <= v <= 0xFFFF, v
    return v

def _spr(n):
    return ((n & 31) << 5) | (n >> 5)


class Asm:
    def __init__(self, base):
        self.base = base
        self.items = []   # (kind, args)
        self.labels = {}

    # --- program building -------------------------------------------------
    def label(self, name):
        self.items.append(('label', name))

    def __getattr__(self, op):
        def emit(*args):
            self.items.append((op, args))
        return emit

    def word(self, w):
        self.items.append(('word', (w,)))

    # --- assembly ---------------------------------------------------------
    def assemble(self):
        pc = self.base
        for kind, a in self.items:
            if kind == 'label':
                self.labels[a] = pc
            else:
                pc += 4
        out = []
        pc = self.base
        for kind, a in self.items:
            if kind == 'label':
                continue
            out.append(self._enc(kind, a, pc))
            pc += 4
        return b''.join(struct.pack('>I', w) for w in out)

    def addr(self, name):
        return self.labels[name]

    def _target(self, t):
        return self.labels[t] if isinstance(t, str) else t

    def _enc(self, op, a, pc):
        D = lambda opc, rd, ra, imm: (opc << 26) | (_r(rd) << 21) | (_r(ra) << 16) | imm
        X = lambda rs, ra, rb, xo, rc=0: (31 << 26) | (_r(rs) << 21) | (_r(ra) << 16) | (_r(rb) << 11) | (xo << 1) | rc
        if op == 'word': return a[0]
        # loads/stores: op rD, d(rA)  -> args (rD, d, rA)
        mem = {'lwz': 32, 'stw': 36, 'lhz': 40, 'lha': 42, 'sth': 44, 'stwu': 37, 'lbz': 34, 'stb': 38}
        if op in mem: return D(mem[op], a[0], a[2], _s16(a[1]))
        if op == 'addi': return D(14, a[0], a[1], _s16(a[2]))
        if op == 'li': return D(14, a[0], 0, _s16(a[1]))
        if op == 'lis': return D(15, a[0], 0, _u16(a[1]) if a[1] >= 0 else _s16(a[1]))
        if op == 'addis': return D(15, a[0], a[1], _s16(a[2]))
        if op == 'mulli': return D(7, a[0], a[1], _s16(a[2]))
        if op == 'ori': return D(24, a[1], a[0], _u16(a[2]))
        if op == 'oris': return D(25, a[1], a[0], _u16(a[2]))
        if op == 'cmplwi': return (10 << 26) | (_r(a[0]) << 16) | _u16(a[1])          # cr0
        if op == 'cmpwi': return (11 << 26) | (_r(a[0]) << 16) | _s16(a[1])
        if op == 'cmpw': return X(0, a[0], a[1], 0)
        if op == 'cmplw': return X(0, a[0], a[1], 32)
        if op == 'rlwinm': return (21 << 26) | (_r(a[1]) << 21) | (_r(a[0]) << 16) | (a[2] << 11) | (a[3] << 6) | (a[4] << 1)
        if op == 'rlwimi': return (20 << 26) | (_r(a[1]) << 21) | (_r(a[0]) << 16) | (a[2] << 11) | (a[3] << 6) | (a[4] << 1)
        if op == 'slwi': n = a[2]; return self._enc('rlwinm', (a[0], a[1], n, 0, 31 - n), pc)
        if op == 'srwi': n = a[2]; return self._enc('rlwinm', (a[0], a[1], 32 - n, n, 31), pc)
        if op == 'mr': return X(a[1], a[0], a[1], 444)
        if op in ('or', 'orr'): return X(a[1], a[0], a[2], 444)
        if op == 'xor': return X(a[1], a[0], a[2], 316)
        if op == 'add': return X(a[0], a[1], a[2], 266)
        if op == 'subf': return X(a[0], a[1], a[2], 40)
        if op == 'mullw': return X(a[0], a[1], a[2], 235)
        if op == 'divwu': return X(a[0], a[1], a[2], 459)
        if op == 'mflr': return (31 << 26) | (_r(a[0]) << 21) | (_spr(8) << 11) | (339 << 1)
        if op == 'mtlr': return (31 << 26) | (_r(a[0]) << 21) | (_spr(8) << 11) | (467 << 1)
        if op == 'mftb': return (31 << 26) | (_r(a[0]) << 21) | (_spr(268) << 11) | (371 << 1)
        if op == 'mftbu': return (31 << 26) | (_r(a[0]) << 21) | (_spr(269) << 11) | (371 << 1)
        if op == 'blr': return 0x4E800020
        if op in ('b', 'bl'):
            disp = self._target(a[0]) - pc
            assert -0x2000000 <= disp < 0x2000000 and disp % 4 == 0, hex(disp)
            return (18 << 26) | (disp & 0x03FFFFFC) | (1 if op == 'bl' else 0)
        conds = {'blt': (12, 0), 'bge': (4, 0), 'bgt': (12, 1), 'ble': (4, 1), 'beq': (12, 2), 'bne': (4, 2)}
        if op in conds:
            bo, bi = conds[op]
            disp = self._target(a[0]) - pc
            assert -0x8000 <= disp < 0x8000, hex(disp)
            return (16 << 26) | (bo << 21) | (bi << 16) | (disp & 0xFFFC)
        raise ValueError(op)


def branch(frm, to):
    disp = to - frm
    return (18 << 26) | (disp & 0x03FFFFFC)
