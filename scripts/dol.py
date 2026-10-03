"""DOL loader + capstone helpers for poking at main.dol."""
import struct
import capstone

class Dol:
    def __init__(self, path):
        b = self.b = open(path, 'rb').read()
        offs = struct.unpack('>18I', b[0:0x48])
        addrs = struct.unpack('>18I', b[0x48:0x90])
        sizes = struct.unpack('>18I', b[0x90:0xD8])
        self.secs = [(o, a, s, i < 7) for i, (o, a, s) in enumerate(zip(offs, addrs, sizes)) if s]
        self.md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_32 | capstone.CS_MODE_BIG_ENDIAN)
        self.md.detail = False
        self.md.skipdata = True

    def text(self):
        for o, a, s, is_text in self.secs:
            if is_text:
                yield a, self.b[o:o + s]

    def read(self, addr, n):
        for o, a, s, _ in self.secs:
            if a <= addr < a + s:
                return self.b[o + addr - a:o + addr - a + n]
        return None

    def u32(self, addr):
        return struct.unpack('>I', self.read(addr, 4))[0]

    def dis(self, addr, n):
        out = []
        for i in self.md.disasm(self.read(addr, n * 4), addr):
            out.append(f'{i.address:08x}: {i.mnemonic:8s} {i.op_str}')
        return out

    def words(self):
        for a, data in self.text():
            for i in range(0, len(data), 4):
                yield a + i, struct.unpack_from('>I', data, i)[0]


def bl_target(addr, w):
    """Target of a 'bl' (or 'b') instruction word, else None."""
    if (w >> 26) == 18:
        li = w & 0x03FFFFFC
        if li & 0x02000000:
            li -= 0x04000000
        return (addr + li) if not (w & 2) else li
    return None
