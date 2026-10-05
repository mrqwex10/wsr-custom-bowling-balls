"""End-to-end check of built alley carcs: unpack what goes on the SD card, decode
every texture (and every animation frame exactly the way the BANM hook addresses it),
and render the alley from those decoded images.

    python scripts/verify_alley.py [theme ...]   -> work/verify_alley/<theme>_{throw,pins}.gif
"""
import os, sys, shutil, struct
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
import build as v1
import build_alley as BA
import alley_render as R

OUT = os.path.join(v1.ROOT, 'work/verify_alley')


def decode_tex0(raw, tmp, key):
    p = os.path.join(tmp, key + '.tex0')
    open(p, 'wb').write(raw)
    png = os.path.join(tmp, key + '.png')
    v1.run(v1.WIMGT, 'decode', p, '-d', png, '-o', '-q')
    return Image.open(png).copy()


def textures(carc, tmp):
    """{name: [frame images]} as the GPU will see them."""
    d = os.path.join(tmp, 'carc.d')
    v1.run(v1.WSZST, 'extract', carc, '-d', d, '-o', '-q')
    br = os.path.join(d, BA.FIELD)
    b = open(br, 'rb').read()
    from build4 import brres_textures
    out = {}
    for name, o in brres_textures(br).items():
        size = struct.unpack_from('>I', b, o + 4)[0]
        hdr = bytearray(b[o:o + 0x40])
        tag = b[o + 0x30:o + 0x34]
        if tag == b'BANM':
            count, period, stride, rel = struct.unpack_from('>HHIi', b, o + 0x34)
            frames = []
            for k in range(count):
                start = o + 0x40 + rel + k * stride
                raw = bytes(hdr[:0x30]) + bytes(16) + b[start:start + stride]
                raw = bytearray(raw)
                struct.pack_into('>I', raw, 4, 0x40 + stride)
                struct.pack_into('>I', raw, 0x14, 0)
                frames.append(decode_tex0(bytes(raw), tmp, f'{name}_{k}'))
            out[name] = frames
        else:
            raw = bytearray(b[o:o + size])
            struct.pack_into('>I', raw, 0x14, 0)
            out[name] = [decode_tex0(bytes(raw), tmp, name)]
    return out


def main(themes):
    os.makedirs(OUT, exist_ok=True)
    for t in themes:
        tmp = os.path.join(v1.BUILD, 'verify_alley', t)
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        os.makedirs(tmp)
        tex = textures(os.path.join(BA.OUT_DIR, t + '.carc'), tmp)
        n = max(len(v) for v in tex.values())
        anim = [k for k, v in tex.items() if len(v) > 1]
        for cam_name, cam in (('throw', R.CAM_THROW), ('pins', R.CAM_PINS)):
            frames = []
            for k in range(n):
                cur = {name: v[k % len(v)] for name, v in tex.items()}
                frames.append(R.render(cur, cam=cam, W=1440, H=810).resize((720, 405), Image.LANCZOS))
            p = os.path.join(OUT, f'{t}_{cam_name}.gif')
            frames[0].save(p, save_all=True, append_images=frames[1:], duration=140, loop=0)
            frames[0].save(p[:-4] + '.png')
        print(t, 'decoded', len(tex), 'textures; animated:', anim, '->', OUT)


if __name__ == '__main__':
    main(sys.argv[1:] or [t for t, _, _ in BA.THEMES])
