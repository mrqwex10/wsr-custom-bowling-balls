"""Minimal MDL0 (v11) reader: dumps vertices, UV sets, and per-object triangles
so we can learn how the ball texture is wrapped onto the sphere."""
import struct, sys, json

def u8(b, o): return b[o]
def u16(b, o): return struct.unpack_from('>H', b, o)[0]
def s16(b, o): return struct.unpack_from('>h', b, o)[0]
def u32(b, o): return struct.unpack_from('>I', b, o)[0]
def s32(b, o): return struct.unpack_from('>i', b, o)[0]
def f32(b, o): return struct.unpack_from('>f', b, o)[0]

def cstr(b, o):
    e = b.index(b'\0', o)
    return b[o:e].decode('latin1')

def group(b, off):
    """Return list of (name, data_abs_offset) from an index group."""
    n = u32(b, off + 4)
    out = []
    for i in range(1, n + 1):
        e = off + 8 + i * 16
        nameoff, dataoff = s32(b, e + 8), s32(b, e + 12)
        out.append((cstr(b, off + nameoff), off + dataoff))
    return out

FMT = {0: ('B', 1), 1: ('b', 1), 2: ('H', 2), 3: ('h', 2), 4: ('f', 4)}

def read_array(b, h, ncomp_fn):
    data = h + s32(b, h + 8)
    comp = u32(b, h + 0x14)
    fmt = u32(b, h + 0x18)
    div = u8(b, h + 0x1C)
    stride = u8(b, h + 0x1D)
    count = u16(b, h + 0x1E)
    nc = ncomp_fn(comp)
    c, sz = FMT[fmt]
    out = []
    for i in range(count):
        v = struct.unpack_from('>' + c * nc, b, data + i * stride)
        if fmt != 4:
            v = tuple(x / (1 << div) for x in v)
        out.append(v)
    return out

def parse(path):
    b = open(path, 'rb').read()
    assert b[:4] == b'MDL0' and u32(b, 8) == 11
    secs = [u32(b, 0x10 + 4 * i) for i in range(14)]
    res = {}
    res['pos'] = {n: read_array(b, h, lambda c: 3 if c else 2) for n, h in group(b, secs[2])} if secs[2] else {}
    res['nrm'] = {n: read_array(b, h, lambda c: 3) for n, h in group(b, secs[3])} if secs[3] else {}
    res['uv'] = {n: read_array(b, h, lambda c: 2 if c else 1) for n, h in group(b, secs[5])} if secs[5] else {}
    # positions / normals / uvs keyed by array index too
    def idx_map(sec):
        m = {}
        if not sec: return m
        for n, h in group(b, sec):
            m[u32(b, h + 0x10)] = n
        return m
    pos_by_i, nrm_by_i, uv_by_i = idx_map(secs[2]), idx_map(secs[3]), idx_map(secs[5])
    res['materials'] = [n for n, _ in group(b, secs[8])] if secs[8] else []
    objs = []
    for name, h in group(b, secs[10]):
        vcd_lo, vcd_hi = u32(b, h + 0x0C), u32(b, h + 0x10)
        dl_size = u32(b, h + 0x24 + 4)
        dl_off = h + 0x24 + s32(b, h + 0x24 + 8)
        ids = struct.unpack_from('>hhhh' + 'h' * 8, b, h + 0x48)
        pos_id, nrm_id, c0, c1 = ids[:4]
        tex_ids = ids[4:]
        # attribute order: PNMTX, TEXMTX0..7, POS, NRM, CLR0, CLR1, TEX0..7
        attrs = []
        if vcd_lo & 1: attrs.append(('pnmtx', 1))
        for i in range(8):
            if vcd_lo >> (1 + i) & 1: attrs.append((f'texmtx{i}', 1))
        for nm, sh in (('pos', 9), ('nrm', 11), ('clr0', 13), ('clr1', 15)):
            t = vcd_lo >> sh & 3
            if t: attrs.append((nm, t))
        for i in range(8):
            t = vcd_hi >> (2 * i) & 3
            if t: attrs.append((f'tex{i}', t))
        o, end = dl_off, dl_off + dl_size
        tris = []
        while o < end:
            cmd = b[o]; o += 1
            if cmd == 0: continue
            if cmd in (0x20, 0x28, 0x30, 0x38):  # load indexed XF (matrix) cmds
                o += 4; continue
            prim = cmd & 0xF8
            if prim not in (0x80, 0x90, 0x98, 0xA0):
                break
            cnt = u16(b, o); o += 2
            verts = []
            for _ in range(cnt):
                v = {}
                for nm, t in attrs:
                    if t == 1:  # direct (only matrix indices expected)
                        v[nm] = b[o]; o += 1
                    elif t == 2:
                        v[nm] = b[o]; o += 1
                    else:
                        v[nm] = u16(b, o); o += 2
                verts.append(v)
            if prim == 0x90:
                tris += [verts[i:i + 3] for i in range(0, cnt - 2, 3)]
            elif prim == 0x98:
                for i in range(cnt - 2):
                    t = verts[i:i + 3]
                    tris.append(t if i % 2 == 0 else [t[1], t[0], t[2]])
            elif prim == 0xA0:
                tris += [[verts[0], verts[i], verts[i + 1]] for i in range(1, cnt - 1)]
            elif prim == 0x80:
                for i in range(0, cnt, 4):
                    q = verts[i:i + 4]
                    tris += [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
        objs.append(dict(name=name, pos=pos_by_i.get(pos_id), nrm=nrm_by_i.get(nrm_id),
                         tex=[uv_by_i.get(t) for t in tex_ids if t >= 0],
                         attrs=[a for a, _ in attrs], tris=tris))
    res['objects'] = objs
    return res

if __name__ == '__main__':
    r = parse(sys.argv[1])
    print('materials:', r['materials'])
    for k in ('pos', 'nrm', 'uv'):
        for n, a in r[k].items():
            print(k, n, len(a), 'min', [round(min(x[i] for x in a), 3) for i in range(len(a[0]))],
                  'max', [round(max(x[i] for x in a), 3) for i in range(len(a[0]))])
    for o in r['objects']:
        print('obj', o['name'], 'pos', o['pos'], 'tex', o['tex'], 'attrs', o['attrs'], 'tris', len(o['tris']))
