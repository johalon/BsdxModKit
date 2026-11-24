#!/usr/bin/env python3
"""Test for the BHE->BSDX spm hit-area fix (tools/patches_py/fix_bhe_hitbox.py).
Converts BHE sou.spm with our build (PortTool spm) and compares every page's hit rects (kind, rect, z range)
with the misaki2 MOD's independently converted sou.spm (known to work in-game). Also checks tsukuyomi kinds = BHE ids.
Usage: test_bhe_hitbox.py [workdir]"""
import json, os, subprocess, sys, collections, tempfile
T = '/path/to/workspace/tools'
BHE = '/path/to/ext/NeXAS_DX/src/main/resources/game/bhe/spm'
MOD = '/tmp/claude-0/dxmod/misaki2/sou.spm'  # reference (only used for this test; not redistributed)
W = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
def pt(*a):
    r = subprocess.run([T + '/porttool.sh', *a], capture_output=True, text=True)
    assert 'FAIL' not in r.stdout, r.stdout
ok = True
if os.path.exists(MOD):
    pt('spm', BHE + '/sou.spm', W + '/sou.spm', ';', 'b2j', 'bsdx', W + '/sou.spm', W + '/ours.json', ';', 'b2j', 'bsdx', MOD, W + '/mod.json')
    a, b = json.load(open(W + '/ours.json')), json.load(open(W + '/mod.json'))
    n = bad = 0
    for pa, pb in zip(a['pageData'], b['pageData']):
        for ha, hb in zip(pa['hitRects'], pb['hitRects']):
            n += 1
            if (ha['unk0'], ha['hitRect'], ha['unk1'], ha['unk2']) != (hb['unk0'], hb['hitRect'], hb['unk1'], hb['unk2']):
                bad += 1
    print('sou.spm hit rects compared with MOD:', n, 'mismatch:', bad)
    ok &= bad == 0 and n > 30000
else:
    print('SKIP MOD comparison (reference file not present)')
pt('spm', BHE + '/tsukuyomi.spm', W + '/tsukuyomi.spm', ';', 'b2j', 'bsdx', W + '/tsukuyomi.spm', W + '/t.json', ';', 'b2j', 'bhe', BHE + '/tsukuyomi.spm', W + '/tb.json')
a, b = json.load(open(W + '/t.json')), json.load(open(W + '/tb.json'))
c = collections.Counter()
for pa, pb in zip(a['pageData'], b['pageData']):
    for ha, hb in zip(pa['hitRects'], pb['hitRects']):
        c['same' if ha['unk0'] == hb['id'] else 'diff'] += 1
        if hb['shapeType'] == 1:
            exp = (int(hb['centerX'] - hb['width'] / 2), int(hb['centerY'] - hb['height'] / 2), int(hb['centerX'] + hb['width'] / 2), int(hb['centerY'] + hb['height'] / 2))
            r = ha['hitRect']; c['rect_ok' if (r['left'], r['top'], r['right'], r['bottom']) == exp and ha['unk1'] == ha['unk2'] == 0 else 'rect_bad'] += 1
print('tsukuyomi.spm kinds:', dict(c))
ok &= c['diff'] == 0 and c['rect_bad'] == 0
print('PASS' if ok else 'FAIL'); sys.exit(0 if ok else 1)
