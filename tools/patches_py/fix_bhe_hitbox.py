#!/usr/bin/env python3
"""PROJECT PATCH (applied by tools/build_nexas_dx.sh to the delomboked copy; upstream ext untouched).
BHE -> BSDX spm hit-area conversion fix (調査記録 06 §3.3, verified on misaki2 sou.spm: 38991/38991 rects):
  unk0 (hit-area kind 0..7) = BHE `id`            (upstream guessed it from shapeType -> wrong)
  rect = (trunc(cx - sx/2), trunc(cy - sy/2), trunc(cx + sx/2), trunc(cy + sy/2))   (float half, truncate toward 0)
  3D box (shapeType 10): unk1/unk2 = trunc(cz - sz/2), trunc(cz + sz/2); 2D: 0, 0
Usage: fix_bhe_hitbox.py <src-main dir>"""
import sys, os
R = sys.argv[1] + '/com/giga/nexas/dto/bhe/spm/'
def sub(path, old, new, count=1):
    s = open(path, encoding='utf-8').read()
    assert s.count(old) == count, (path, old, s.count(old))
    open(path, 'w', encoding='utf-8').write(s.replace(old, new))
sub(R + 'Spm.java', 'area.setUnk0(overrideUnk0 != null ? overrideUnk0 : mapShapeTypeForBsdx());',
    'area.setUnk0(overrideUnk0 != null ? overrideUnk0 : (id != null ? (int) id : mapShapeTypeForBsdx())); // PATCH(proj): kind = BHE id')
sub(R + 'hitbox/CRotatableRect.java', '''        int left = cx - w / 2;
        int top = cy - h / 2;
        int right = left + w;
        int bottom = top + h;
        return buildBsdxHitArea(left, top, right, bottom, null, null, null);''',
'''        // PATCH(proj): centre +- size/2 with float half truncated toward zero (matches misaki2 sou.spm)
        int left = (int) (cx - w / 2.0);
        int top = (int) (cy - h / 2.0);
        int right = (int) (cx + w / 2.0);
        int bottom = (int) (cy + h / 2.0);
        return buildBsdxHitArea(left, top, right, bottom, null, null, null);''')
sub(R + 'hitbox/CRotatableBox.java', '''        int left = cx - w / 2;
        int top = cy - h / 2;
        int right = left + w;
        int bottom = top + h;
        int zMin = cz - d / 2;
        int zMax = zMin + d;''',
'''        // PATCH(proj): centre +- size/2 with float half truncated toward zero (matches misaki2 sou.spm)
        int left = (int) (cx - w / 2.0);
        int top = (int) (cy - h / 2.0);
        int right = (int) (cx + w / 2.0);
        int bottom = (int) (cy + h / 2.0);
        int zMin = (int) (cz - d / 2.0);
        int zMax = (int) (cz + d / 2.0);''')
sub(R + 'hitbox/DefaultHitArea.java', 'return buildBsdxHitArea(left, top, right, bottom, zMin, zMax, 1);',
    'return buildBsdxHitArea(left, top, right, bottom, zMin, zMax, null); // PATCH(proj): kind = BHE id')
print('fix_bhe_hitbox: patched')
