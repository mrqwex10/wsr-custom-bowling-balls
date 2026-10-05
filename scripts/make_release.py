"""Package a release zip from the built output (run build4.py + build_alley.py first).

    python scripts/make_release.py 2.0   -> dist/WSR_Custom_Bowling_Balls_v2.0.zip

Leaves out the diagnostic TEST alleys; everything else in output/ goes in as built.
"""
import os, sys, shutil, zipfile, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import build as v1
import build4
import build_alley as BA

DIST = os.path.join(v1.ROOT, 'dist')


def main(version):
    name = f'WSR_Custom_Bowling_Balls_v{version}'
    stage = os.path.join(v1.BUILD, 'release', name)
    if os.path.exists(stage):
        shutil.rmtree(stage)
    os.makedirs(os.path.join(stage, 'riivolution'))
    build4.write_xml(dev=False, path=os.path.join(stage, 'riivolution', f'{v1.MOD_DIR}.xml'))
    src = os.path.join(v1.OUT, v1.MOD_DIR)
    dst = os.path.join(stage, v1.MOD_DIR)
    os.makedirs(dst)
    for _, folder, *_ in build4.VARIANTS:
        os.makedirs(os.path.join(dst, folder))
        shutil.copy2(os.path.join(src, folder, 'common.carc'), os.path.join(dst, folder, 'common.carc'))
    os.makedirs(os.path.join(dst, 'alley'))
    for theme, _, _ in BA.THEMES:
        shutil.copy2(os.path.join(src, 'alley', theme + '.carc'), os.path.join(dst, 'alley', theme + '.carc'))
    shutil.copy2(os.path.join(v1.OUT, 'README.txt'), os.path.join(dst, 'README.txt'))
    # every external file the XML points at must be in the zip
    xml = open(os.path.join(stage, 'riivolution', f'{v1.MOD_DIR}.xml')).read()
    import re
    for ext in re.findall(r'external="([^"]+)"', xml):
        assert os.path.isfile(stage + ext), f'missing {ext}'
    assert 'TEST: stock' not in xml and 'cosmic_still' not in xml
    out = os.path.join(DIST, name + '.zip')
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for top in ('riivolution', v1.MOD_DIR):
            for root, dirs, files in os.walk(os.path.join(stage, top)):
                dirs.sort()
                rel = os.path.relpath(root, stage)
                z.write(root, rel + '/')
                for f in sorted(files):
                    z.write(os.path.join(root, f), os.path.join(rel, f))
    total = sum(i.file_size for i in zipfile.ZipFile(out).infolist())
    print(out, f'{os.path.getsize(out) / 1e6:.1f} MB zipped, {total / 1e6:.1f} MB unpacked')
    return out


if __name__ == '__main__':
    main(sys.argv[1])
