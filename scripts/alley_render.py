"""Software renderer for the Bowling alley (Stage/BwlScene/Normal.carc) so alley
skins can be previewed from the game's camera without a Wii.

Approximation of the real TEV setup: first texture layer x vertex colour (baked
lighting), alpha-blended materials drawn after opaque ones, optional lane gloss
(reflected scene blended under the lane like the game's mirror models).

    render(textures: {name: PIL image}, cam=...) -> PIL image
"""
import os, sys, struct, glob
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
from mdl0_dump import parse, group, u32, s32, u16, cstr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGES = {   # stage -> (extracted brres dir, decoded png dir, models drawn)
    'normal': ('work/stage/Normal.d/G3D/bwg_field.brres.d', 'work/stage/png',
               ('bwg_field', 'bwg_field_front', 'bwg_field_pin')),
    '100pin': ('work/stage/100Pin.d/G3D/bwg_field_91.brres.d', 'work/stage/png91',
               ('WS2_bwl_field_91', 'bwg_wall_L', 'bwg_wall_R')),
}

# where the game's camera sits while you line up a throw (approximate)
CAM_THROW = dict(eye=(0.0, 15.5, 44.0), at=(0.0, 4.0, -150.0), fov=38.0)
CAM_PINS = dict(eye=(0.0, 6.0, -150.0), at=(0.0, 4.5, -186.0), fov=42.0)
CAM_THROW_100 = dict(eye=(0.0, 15.5, 44.0), at=(0.0, 4.0, -250.0), fov=38.0)
CAM_PINS_100 = dict(eye=(0.0, 9.0, -290.0), at=(0.0, 6.0, -345.0), fov=46.0)


def ensure_stage(stage='normal'):
    """Unpack the stock alley from work/disc (models + decoded textures) the first time it's needed."""
    import subprocess
    brres_d, png_d, _ = STAGES[stage]
    brres_d, png_d = os.path.join(ROOT, brres_d), os.path.join(ROOT, png_d)
    tools = os.path.join(ROOT, 'tools/bin')
    if not os.path.isdir(brres_d):
        carc = os.path.join(ROOT, 'work/disc/files/Stage/BwlScene', 'Normal.carc' if stage == 'normal' else '100Pin.carc')
        carc_d = os.path.dirname(os.path.dirname(brres_d))
        subprocess.run([os.path.join(tools, 'wszst'), 'extract', carc, '-d', carc_d, '-o', '-q'], check=True)
        subprocess.run([os.path.join(tools, 'wszst'), 'extract', brres_d[:-2], '-d', brres_d, '-o', '-q'], check=True)
    if not os.path.isdir(png_d) or not os.listdir(png_d):
        os.makedirs(png_d, exist_ok=True)
        tex = os.path.join(brres_d, 'Textures(NW4R)')
        for n in sorted(os.listdir(tex)):
            subprocess.run([os.path.join(tools, 'wimgt'), 'decode', os.path.join(tex, n), '-d',
                            os.path.join(png_d, n + '.png'), '-o', '-q'], check=True)


def materials(path):
    b = open(path, 'rb').read()
    secs = [u32(b, 0x10 + 4 * i) for i in range(14)]
    out = {}
    for name, h in group(b, secs[8]):
        n, lo = u32(b, h + 0x2c), h + s32(b, h + 0x30)
        layers = []
        for i in range(n):
            e = lo + i * 0x34
            layers.append((cstr(b, e + s32(b, e)), u32(b, e + 0x18), u32(b, e + 0x1c)))
        out[name] = dict(layers=layers, xlu=bool(u32(b, h + 0x10) & 0x80000000))
    return out


def colors(path):
    b = open(path, 'rb').read()
    secs = [u32(b, 0x10 + 4 * i) for i in range(14)]
    out = {}
    if secs[4]:
        for name, h in group(b, secs[4]):
            data, cnt = h + s32(b, h + 8), u16(b, h + 0x1e)
            assert u32(b, h + 0x18) == 5
            out[u32(b, h + 0x10)] = np.frombuffer(b, np.uint8, cnt * 4, data).reshape(cnt, 4) / 255.0
    return out


def load_mesh(model, stage='normal'):
    """[(material, P (n,3,3), UV (n,3,2), C (n,3,4))] for one MDL0."""
    path = os.path.join(ROOT, STAGES[stage][0], '3DModels(NW4R)', model)
    r = parse(path)
    mats = materials(path)
    cols = colors(path)
    b = open(path, 'rb').read()
    secs = [u32(b, 0x10 + 4 * i) for i in range(14)]
    clr_ids = {}
    for name, h in group(b, secs[10]):
        clr_ids[name] = struct.unpack_from('>h', b, h + 0x48 + 4)[0]
    out = []
    for o, (oname, _) in zip(r['objects'], group(b, secs[10])):
        mat = o['pos'].split('__', 1)[1]
        mat = mat if mat in mats else mat.rsplit('__', 1)[0]
        P = np.array(r['pos'][o['pos']], float)
        UV = np.array(r['uv'][o['tex'][0]], float) if o['tex'] else np.zeros((1, 2))
        C = cols.get(clr_ids[oname])
        pi = np.array([[v['pos'] for v in t] for t in o['tris']])
        ti = np.array([[v.get('tex0', 0) for v in t] for t in o['tris']])
        if C is not None and 'clr0' in o['attrs']:
            ci = np.array([[v['clr0'] for v in t] for t in o['tris']])
            CC = C[ci]
        else:
            CC = np.ones(pi.shape + (4,))
        out.append((mat, mats[mat], P[pi], UV[ti], CC))
    return out


def stock_textures(stage='normal'):
    ensure_stage(stage)
    tex = {}
    for p in glob.glob(os.path.join(ROOT, STAGES[stage][1], '*.png')):
        n = os.path.basename(p)[:-4]
        if '.mm' not in n:
            tex[n] = Image.open(p)
    return tex


def tex_array(im):
    im = im.convert('RGBA') if im.mode in ('RGBA', 'LA', 'P') else im.convert('RGB').convert('RGBA')
    return np.asarray(im, np.float32) / 255.0


def sample(T, u, v, ws, wt):
    h, w = T.shape[:2]
    x = u * w - 0.5
    y = v * h - 0.5
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = (x - x0)[:, None]; fy = (y - y0)[:, None]

    def wrap(i, n, mode):
        if mode == 1:
            return i % n
        if mode == 2:
            i = i % (2 * n)
            return np.where(i >= n, 2 * n - 1 - i, i)
        return np.clip(i, 0, n - 1)
    xa, xb = wrap(x0, w, ws), wrap(x0 + 1, w, ws)
    ya, yb = wrap(y0, h, wt), wrap(y0 + 1, h, wt)
    return ((T[ya, xa] * (1 - fx) + T[ya, xb] * fx) * (1 - fy) +
            (T[yb, xa] * (1 - fx) + T[yb, xb] * fx) * fy)


def look(eye, at, fov, W, H):
    eye, at = np.array(eye, float), np.array(at, float)
    f = at - eye; f /= np.linalg.norm(f)
    r = np.cross(f, [0, 1, 0]); r /= np.linalg.norm(r)
    u = np.cross(r, f)
    fl = 0.5 * H / np.tan(np.radians(fov) / 2)
    return eye, r, u, f, fl


class Raster:
    def __init__(self, W, H, cam):
        self.W, self.H = W, H
        self.eye, self.r, self.u, self.f, self.fl = look(cam['eye'], cam['at'], cam['fov'], W, H)
        self.color = np.zeros((H, W, 3), np.float32)
        self.z = np.full((H, W), np.inf, np.float32)

    def project(self, P):
        d = P - self.eye
        x, y, z = d @ self.r, d @ self.u, d @ self.f
        return x, y, z

    def clip(self, P, UV, C, near):
        """Split triangles that cross the near plane (the lane is a few huge triangles)."""
        z = (P - self.eye) @ self.f
        inside = z > near
        ok = inside.all(1)
        part = inside.any(1) & ~ok
        outP, outU, outC = [P[ok]], [UV[ok]], [C[ok]]
        for i in np.nonzero(part)[0]:
            poly = []
            for k in range(3):
                a, b = k, (k + 1) % 3
                va = (P[i, a], UV[i, a], C[i, a])
                if inside[i, a]:
                    poly.append(va)
                if inside[i, a] != inside[i, b]:
                    t = (near - z[i, a]) / (z[i, b] - z[i, a])
                    poly.append(tuple(x + (y - x) * t for x, y in zip(va, (P[i, b], UV[i, b], C[i, b]))))
            for k in range(1, len(poly) - 1):
                tri = (poly[0], poly[k], poly[k + 1])
                outP.append(np.array([v[0] for v in tri])[None])
                outU.append(np.array([v[1] for v in tri])[None])
                outC.append(np.array([v[2] for v in tri])[None])
        return np.concatenate(outP), np.concatenate(outU), np.concatenate(outC)

    def draw(self, P, UV, C, T, ws, wt, xlu, shade, near=0.5):
        P, UV, C = self.clip(P, UV, C, near)
        x, y, z = self.project(P.reshape(-1, 3))
        x, y, z = x.reshape(-1, 3), y.reshape(-1, 3), z.reshape(-1, 3)
        keep = (z > near * 0.99).all(1)
        W, H = self.W, self.H
        for i in np.nonzero(keep)[0]:
            zi = z[i]
            sx = self.W / 2 + self.fl * x[i] / zi
            sy = self.H / 2 - self.fl * y[i] / zi
            x0, x1 = int(max(np.floor(sx.min()), 0)), int(min(np.ceil(sx.max()), W - 1))
            y0, y1 = int(max(np.floor(sy.min()), 0)), int(min(np.ceil(sy.max()), H - 1))
            if x0 > x1 or y0 > y1:
                continue
            den = (sy[1] - sy[2]) * (sx[0] - sx[2]) + (sx[2] - sx[1]) * (sy[0] - sy[2])
            if abs(den) < 1e-9:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            a = ((sy[1] - sy[2]) * (gx - sx[2]) + (sx[2] - sx[1]) * (gy - sy[2])) / den
            bb = ((sy[2] - sy[0]) * (gx - sx[2]) + (sx[0] - sx[2]) * (gy - sy[2])) / den
            c = 1 - a - bb
            m = (a >= -1e-4) & (bb >= -1e-4) & (c >= -1e-4)
            if not m.any():
                continue
            a, bb, c = a[m], bb[m], c[m]
            iz = a / zi[0] + bb / zi[1] + c / zi[2]
            depth = 1 / iz
            py, px = gy[m].astype(int), gx[m].astype(int)
            vis = depth < self.z[py, px] - (0.02 if xlu else 0)
            if not vis.any():
                continue
            a, bb, c, depth, py, px = a[vis], bb[vis], c[vis], depth[vis], py[vis], px[vis]
            wa, wb, wc = a / zi[0] * depth, bb / zi[1] * depth, c / zi[2] * depth
            uv = UV[i]
            u = wa * uv[0, 0] + wb * uv[1, 0] + wc * uv[2, 0]
            v = wa * uv[0, 1] + wb * uv[1, 1] + wc * uv[2, 1]
            col = C[i]
            vc = wa[:, None] * col[0] + wb[:, None] * col[1] + wc[:, None] * col[2]
            t = sample(T, u, v, ws, wt)
            rgb = shade(t[:, :3], vc[:, :3], np.stack([px, py], 1))
            al = t[:, 3:4] * vc[:, 3:4]
            if xlu:
                self.color[py, px] = self.color[py, px] * (1 - al) + rgb * al
            else:
                cut = al[:, 0] > 0.5
                py, px, rgb, depth = py[cut], px[cut], rgb[cut], depth[cut]
                self.color[py, px] = rgb
                self.z[py, px] = depth


SKIP = {'alpha_z_mat', 'shadow_a_mat', 'shadow_b_mat', 'shadow_b_mat_1'}
_MESH = {}


def meshes(stage='normal'):
    if stage not in _MESH:
        ensure_stage(stage)
        M = _MESH[stage] = {m: load_mesh(m, stage) for m in STAGES[stage][2]}
        if stage == 'normal':
            # the player's own pins are spawned by the game, not part of the stage: copy a set
            mat, info, P, UV, C = M['bwg_field_pin'][0]
            cx = P[:, :, 0].mean(1)
            m = (cx > 60) & (cx < 75)
            Q = P[m].copy()
            Q[..., 0] -= (Q[..., 0].min() + Q[..., 0].max()) / 2
            M['bwg_field_pin'].append((mat, info, Q, UV[m], C[m]))
        else:
            # the 100-pin side walls are placed by the game at the gutters' outer edges
            for k, dx in (('bwg_wall_L', -25.2), ('bwg_wall_R', 25.2)):
                M[k] = [(mat, info, P + np.array([dx, 0, 0]), UV, C) for mat, info, P, UV, C in M[k]]
    return _MESH[stage]


def default_shade(t, vc, pix):
    return np.clip(t * vc * 1.3, 0, 1)


def render(textures, cam=CAM_THROW, W=960, H=540, shade=None, gloss=0.22, ambient=1.0,
           emissive=(), skip=SKIP, sky=(0.05, 0.05, 0.06), stage='normal'):
    """textures: {texture name: PIL image} (missing ones fall back to stock).
    emissive: texture names drawn full-bright (ignore baked lighting)."""
    shade = shade or default_shade
    stock = stock_textures(stage)
    tx = {n: tex_array(textures.get(n, stock.get(n))) for n in set(stock) | set(textures)}

    base = Raster(W, H, cam)
    base.color[:] = sky
    # opaque first, then translucent
    def ordered(rast, mirror):
        for xlu in (False, True):
            for model, parts in meshes(stage).items():
                for mat, info, P, UV, C in parts:
                    if info['xlu'] != xlu or mat in skip:
                        continue
                    if P[..., 1].max() < -0.5:
                        continue
                    lane = mat in ('lane_mat', 'lane_stand_mat', 'mark_mat', 'gater_mat')
                    if mirror and (lane or P[..., 1].min() > 30):
                        continue
                    name, ws, wt = info['layers'][0]
                    if name not in tx:
                        continue
                    PP = P.copy()
                    if mirror:
                        PP[..., 1] *= -1
                    if name in emissive:
                        sh = lambda t, vc, pix: np.clip(t * 1.1, 0, 1)
                    else:
                        sh = lambda t, vc, pix: np.clip(shade(t, vc, pix) * ambient, 0, 1)
                    rast.draw(PP, UV, C, tx[name], ws, wt, info['xlu'], sh)
    ordered(base, False)
    img = base.color
    if gloss > 0:
        refl = Raster(W, H, cam)
        refl.color[:] = sky
        ordered(refl, True)
        # where the lane is visible in the base pass, blend the reflection in
        lane_mask = _lane_mask(cam, W, H, stage)
        k = gloss * lane_mask[..., None]
        img = img * (1 - k) + refl.color * k
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))


def _lane_mask(cam, W, H, stage='normal'):
    r = Raster(W, H, cam)
    for model, parts in meshes(stage).items():
        for mat, info, P, UV, C in parts:
            if info['xlu'] or P[..., 1].max() < -0.5 or mat in SKIP:
                continue
            val = 1.0 if mat == 'lane_mat' else 0.0
            T = np.ones((1, 1, 4), np.float32)
            r.draw(P, UV, C, T, 0, 0, False, lambda t, vc, pix, v=val: np.full_like(t, v))
    return r.color[..., 0]


if __name__ == '__main__':
    import time
    t = time.time()
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'work/stage/render_stock.png')
    render({}).save(out)
    print(out, round(time.time() - t, 1), 's')
