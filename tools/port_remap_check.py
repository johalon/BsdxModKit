#!/usr/bin/env python3
"""Check how a BHE->BSDX mech port remapped its references, using the port's own registries.

Usage: port_remap_check.py <bhe json root> <ported bsdx json root> <bhe waz name> <ported waz name> [--orig <bsdx json root>]
  e.g. port_remap_check.py <作業ツリー>/work/bhe_rt/json <mod>/json misaki misaki
For SE and voice remaps derived by waz_refs.map-style alignment, prints whether the file names match
(BHE SeGroup item seFileName vs BSDX SeGroup item seFileName; BatVoice voiceFileName).
For shared waz (Effect/Tama01-05/Laser/Bomb) prints whether each WazaSelect target skill name matches
(BHE <shared>[seq] vs ported <shared>[seq']), and whether the target is in the original BSDX range or appended.
"""
import json, os, sys, collections
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')    # この作業ツリーの根（tools/ の 1 つ上）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from waz_refs import refs_of, guess_game

a = [x for x in sys.argv[1:] if not x.startswith('--')]
BH, PT, wb, wp = a[0], a[1], a[2], a[3]
ORIG = sys.argv[sys.argv.index('--orig') + 1] if '--orig' in sys.argv else _ROOT + '/work/nexas_rt/json'

def ld(root, kind, name):
    d = os.path.join(root, kind)
    for f in os.listdir(d):
        if f.lower() == (name + '.' + kind + '.json').lower():
            return json.load(open(os.path.join(d, f), encoding='utf-8'))
    return None

def lst(g):
    return [v for k, v in g.items() if isinstance(v, list) and k != 'voiceTypeList'][0]

bse, pse = lst(ld(BH, 'grp', 'segroup')), lst(ld(PT, 'grp', 'SeGroup') or ld(ORIG, 'grp', 'SeGroup'))
bbv, pbv = ld(BH, 'grp', 'batvoice')['voiceList'], (ld(PT, 'grp', 'BatVoice') or ld(ORIG, 'grp', 'BatVoice'))['voiceList']
bwg = lst(ld(BH, 'grp', 'wazagroup'))
pwg = lst(ld(PT, 'grp', 'WazaGroup') or ld(ORIG, 'grp', 'WazaGroup'))
owg = lst(ld(ORIG, 'grp', 'WazaGroup'))

def se_file(tab, c, i):
    try:
        return tab[c]['seItems'][i].get('seFileName')
    except Exception:
        return None

def vo_file(tab, c, i):
    try:
        return tab[c]['voices'][i].get('voiceFileName')
    except Exception:
        return None

src, dst = ld(BH, 'waz', wb), ld(PT, 'waz', wp)
S, D = src['skillList'], dst['skillList']
pairs = collections.Counter()
for i in range(min(len(S), len(D))):
    if not S[i] or not D[i]:
        continue
    rs, rd = refs_of(S[i], 'bhe'), refs_of(D[i], 'bsdx')
    for kind in ('waz', 'se', 'voice', 'spr'):
        xs = [r for k, r in rs if k == kind]
        ys = [r for k, r in rd if k == kind]
        if len(xs) == len(ys):
            for x, y in zip(xs, ys):
                pairs[(kind, x, y)] += 1
        else:
            pairs[(kind, 'COUNT', (i, len(xs), len(ys)))] += 1

shared_cache = {}
def shared(root, idx, grp):
    key = (root, idx)
    if key not in shared_cache:
        shared_cache[key] = ld(root, 'waz', grp[idx]['wazaDisplayName']) if 0 <= idx < len(grp) else None
    return shared_cache[key]

stat = collections.Counter()
print('## SE remap: BHE(cat,item) file -> BSDX(cat,item) file')
for (kind, x, y), n in sorted(pairs.items(), key=str):
    if kind == 'se' and x != 'COUNT':
        fx, fy = se_file(bse, *x), se_file(pse, *y)
        ok = (fx or '').lower() == (fy or '').lower()
        stat['se_same_file' if ok else 'se_diff_file'] += n
        stat['se_into_cat%d' % y[0]] += n
        print('  %s %-28s -> %s %-28s %s x%d' % (x, fx, y, fy, 'SAME' if ok else 'DIFF', n))
print('## voice remap')
for (kind, x, y), n in sorted(pairs.items(), key=str):
    if kind == 'voice' and x != 'COUNT':
        fx, fy = vo_file(bbv, *x), vo_file(pbv, *y)
        ok = (fx or '').lower() == (fy or '').lower()
        stat['voice_same_file' if ok else 'voice_diff_file'] += n
        if not ok:
            print('  %s %s -> %s %s DIFF x%d' % (x, fx, y, fy, n))
print('## WazaSelect remap (shared waz skill names)')
for (kind, x, y), n in sorted(pairs.items(), key=str):
    if kind == 'waz' and x != 'COUNT':
        if x[0] >= 9:  # self / other mech
            print('  self/other ref %s -> %s x%d' % (x, y, n)); continue
        bw, pw = shared(BH, x[0], bwg), shared(PT, y[0], pwg)
        bn = (bw['skillList'][x[1]] or {}).get('skillNameJapanese') if bw and x[1] < len(bw['skillList']) else None
        pn = (pw['skillList'][y[1]] or {}).get('skillNameJapanese') if pw and y[1] < len(pw['skillList']) else None
        orig_n = owg[y[0]]['param']
        region = 'orig' if y[1] < orig_n else 'APPENDED'
        stat['waz_%s' % region] += n
        stat['waz_name_%s' % ('same' if bn == pn else 'diff')] += n
        print('  %s「%s」 -> %s「%s」 %s %s x%d' % (x, bn, y, pn, region, '' if bn == pn else 'NAME-DIFF', n))
print('## sprite group remap (non -1)')
sc = collections.Counter()
for (kind, x, y), n in pairs.items():
    if kind == 'spr' and x != 'COUNT' and x[0] != -1:
        sc[(x[0], y[0], x[1:] == y[1:])] += n
for k, n in sorted(sc.items()):
    print('  spmSeq %s -> %s  anim-same=%s x%d' % (k[0], k[1], k[2], n))
print('## COUNT mismatches:', [k for k in pairs if k[1] == 'COUNT'][:20])
print('## stats', dict(stat))
