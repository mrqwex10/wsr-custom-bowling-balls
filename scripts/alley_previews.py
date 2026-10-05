"""Animated GIF previews of alley concepts (throw view + pin view)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
import alley_render as R
import make_alley as M

OUT = os.path.join(M.ROOT, 'work/stage/concepts')


def main(names):
    for n in names:
        c = M.CONCEPTS[n]()
        for cam_name, cam in (('throw', R.CAM_THROW), ('pins', R.CAM_PINS)):
            frames = []
            for k in range(M.FRAMES):
                tex = dict(c['tex'])
                for name, fr in c['anim'].items():
                    tex[name] = fr[k]
                frames.append(R.render(tex, cam=cam, W=1440, H=810).resize((720, 405), Image.LANCZOS))
            p = os.path.join(OUT, f'{n}_{cam_name}.gif')
            frames[0].save(p, save_all=True, append_images=frames[1:], duration=140, loop=0, optimize=False)
            print(p)


if __name__ == '__main__':
    main(sys.argv[1:] or list(M.CONCEPTS))
