"""Spinning-in-place GIF of the animated frames at true speed."""
import sys, os, glob
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
from ballmap import render_preview
src, out, period = sys.argv[1], sys.argv[2], int(sys.argv[3])
frames = sorted(f for f in glob.glob(os.path.join(src, 'f??.png')))
imgs = []
for loopn in range(2):
    for i, f in enumerate(frames):
        imgs.append(render_preview(Image.open(f), 260, 0.25, 0.15))
imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=int(period * 1000 / 60), loop=0)
print(out, len(imgs), 'frames')
