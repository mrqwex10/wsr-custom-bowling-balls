"""Render a design from several angles so seams / outlines are easy to spot.
usage: preview.py designs/foo.png [out.png]"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image
from ballmap import render_preview

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + '_preview.png'
tex = Image.open(src)
S = 240
angles = [(0, 0), (np.pi / 2, 0), (np.pi, 0), (-np.pi / 2, 0), (0, np.pi / 2), (0, -np.pi / 2)]
sheet = Image.new('RGB', (S * 6, S + 300), (30, 30, 30))
for i, (ry, rx) in enumerate(angles):
    sheet.paste(render_preview(tex, S, ry, rx), (i * S, 0))
sheet.paste(tex.convert('RGB').resize((600, 300), Image.LANCZOS), (0, S))
sheet.save(out)
print(out)
