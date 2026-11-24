#!/usr/bin/env python3
"""Test tools/port/spm_append.py on the real shared spm of the ツクヨミ port (調査記録 08 §4).

For BSDX Tama.spm (has the 9098-byte tail = anim-table copy), bomb.spm, Mark.spm, Pic.spm:
  1. append the BHE anims (BHE spm converted to BSDX by PortTool) -> verify_append(): the original file is recovered
     byte for byte by removing the inserted runs and restoring the counts; header/pages/images/anims are identical
     runs; the tail keeps its original bytes (Tama: + count patch + same new anims, still == the anim table)
  2. NeXAS_DX parses the result; its JSON = original JSON + the new entries (old entries unchanged), new anim names
     equal the BHE names, every new page/image/anim index is in range
  3. control: appending nothing gives back the original file exactly
Run: python3 tools/tests/test_spm_append.py   (needs tools/build_nexas_dx.sh)
"""
import os, sys, json, tempfile
sys.path.insert(0, '/path/to/workspace/tools/port')
import spm_append as S
from bhe2bsdx import porttool, jload

DX = '/path/to/ext/NeXAS_DX/src/main/resources/game/bsdx/spm'
FX = '/path/to/workspace/work/bhe_tsukuyomi_fx'
CASES = {'Tama': ('tama', [195, 231]), 'bomb': ('bomb', [97]),
         'Mark': ('mark', [218, 225, 226, 227, 228, 229, 230, 231, 232, 237, 250, 251, 252, 253]), 'Pic': ('pic', [207, 217])}

tmp = tempfile.mkdtemp(prefix='spmapp_', dir=os.environ.get('TMPDIR'))
porttool(*[['spm', '%s/%s.spm' % (FX, b), '%s/bhe_%s.spm' % (tmp, b)] for b, _ in CASES.values()])
jobs = []
for n, (b, ids) in CASES.items():
    base = open('%s/%s.spm' % (DX, n), 'rb').read()
    donor = open('%s/bhe_%s.spm' % (tmp, b), 'rb').read()
    same, _ = S.append(base, donor, [])
    assert same == base, '%s: empty append changed bytes' % n
    out, info = S.append(base, donor, ids)
    S.verify_append(base, out, info)
    open('%s/%s.spm' % (tmp, n), 'wb').write(out)
    json.dump(info, open('%s/%s.info.json' % (tmp, n), 'w'), ensure_ascii=False)
    jobs += [['b2j', 'bsdx', '%s/%s.spm' % (DX, n), '%s/%s.orig.json' % (tmp, n)],
             ['b2j', 'bsdx', '%s/%s.spm' % (tmp, n), '%s/%s.new.json' % (tmp, n)],
             ['b2j', 'bsdx', '%s/bhe_%s.spm' % (tmp, b), '%s/%s.bhe.json' % (tmp, n)]]
    print('%-5s %7d -> %7d B  tail %s(%d B)  +%d pages +%d images +%d anims (anims %s)' % (
        n, len(base), len(out), info['tail_kind'] or 'none', info['tail_len'], info['n_pages'], len(info['images']),
        len(ids), sorted(info['anim_map'].values())))
porttool(*jobs)
for n, (b, ids) in CASES.items():
    o, w, d = (jload('%s/%s.%s.json' % (tmp, n, k)) for k in ('orig', 'new', 'bhe'))
    info = json.load(open('%s/%s.info.json' % (tmp, n)))
    for k in ('pageData', 'imageData', 'animData'):
        assert w[k][:len(o[k])] == o[k], (n, k)          # old entries unchanged (NeXAS view)
    assert w['patPageNum'] == o['patPageNum'] and w['spmVersion'] == o['spmVersion']
    for k, na in info['anim_map'].items():
        a, ab = w['animData'][na], d['animData'][int(k)]
        assert a['animName'] == ab['animName'] and a['numPat'] == ab['numPat'], (n, k)
        for pt, pb in zip(a['patData'], ab['patData']):
            assert pt['waitFrame'] == pb['waitFrame']
            for pg, pgb in zip(pt['pageNo'], pb['pageNo']):
                P, PB = w['pageData'][pg], d['pageData'][pgb]
                assert len(o['pageData']) <= pg < len(w['pageData'])
                assert [c['srcRect'] for c in P['chipData']] == [c['srcRect'] for c in PB['chipData']]
                assert [w['imageData'][c['imageNo']]['imageName'] for c in P['chipData']] == \
                       [d['imageData'][c['imageNo']]['imageName'] for c in PB['chipData']]
    assert [x['imageName'] for x in w['imageData'][len(o['imageData']):]] == info['images']
print('OK: originals preserved, results parse with NeXAS_DX, appended anims equal the BHE ones')
