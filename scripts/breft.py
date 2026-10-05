"""Minimal BREFT (effect texture) reader/writer: list, decode to PNG, replace images."""
import os, sys, struct, subprocess, tempfile
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
import build as v1

FMT_NAMES = {0: 'I4', 1: 'I8', 2: 'IA4', 3: 'IA8', 4: 'RGB565', 5: 'RGB5A3', 6: 'RGBA32', 14: 'CMPR'}
TEX0_TEMPLATE = os.path.join(v1.ROOT, 'work/stage/Normal.d/G3D/bwg_field.brres.d/Textures(NW4R)/ball_return_2')


def entries(b):
    """[(name, header_offset, data_size, w, h, fmt)]"""
    assert b[:4] == b'REFT'
    tab = 0x60
    n = struct.unpack_from('>H', b, tab + 4)[0]
    o = tab + 8
    out = []
    for _ in range(n):
        ln = struct.unpack_from('>H', b, o)[0]
        name = b[o + 2:o + 2 + ln].split(b'\0')[0].decode()
        off, size = struct.unpack_from('>II', b, o + 2 + ln)
        o += 2 + ln + 8
        h = tab + off
        w, hh = struct.unpack_from('>HH', b, h + 4)
        fmt = b[h + 0xC]
        out.append((name, h, size, w, hh, fmt))
    return out


def to_tex0(b, e):
    name, h, size, w, hh, fmt = e
    t = bytearray(open(TEX0_TEMPLATE, 'rb').read()[:0x40])
    struct.pack_into('>I', t, 4, 0x40 + size)
    struct.pack_into('>I', t, 0x14, 0)
    struct.pack_into('>HH', t, 0x1C, w, hh)
    struct.pack_into('>II', t, 0x20, fmt, 1)
    struct.pack_into('>ff', t, 0x28, 0.0, 0.0)
    return bytes(t) + b[h + 0x20:h + 0x20 + size]


def decode(b, e, tmp):
    p = os.path.join(tmp, e[0] + '.tex0')
    open(p, 'wb').write(to_tex0(b, e))
    png = os.path.join(tmp, e[0] + '.png')
    v1.run(v1.WIMGT, 'decode', p, '-d', png, '-o', '-q')
    return Image.open(png).copy()


if __name__ == '__main__':
    path, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    b = open(path, 'rb').read()
    for e in entries(b):
        print(f'{e[0]:24s} {e[3]}x{e[4]} {FMT_NAMES.get(e[5], e[5]):7s} {e[2]} bytes')
        decode(b, e, out).save(os.path.join(out, e[0] + '.png'))
