#!/usr/bin/env python3
"""Dependency closure of a BHE mech waz for porting to BSDX.

Usage: bhe_deps.py <bhe mech waz name> [--bhe DIR] [--bsdx DIR]
  Follows WazaSelect refs into BHE shared waz (Effect/Tama01-05/Laser/Bomb) transitively, and reports for every
  needed shared skill whether BSDX already has a skill of the same Japanese name (-> remap index) or it must be
  appended; plus sprite groups, SE (by file name against BSDX SeGroup) and voices used by the closure.
"""
import json, os, sys, collections
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')    # この作業ツリーの根（tools/ の 1 つ上）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from waz_refs import refs_of
a = sys.argv[1:]
mech = a[0]
BH = a[a.index('--bhe') + 1] if '--bhe' in a else _ROOT + '/work/bhe_rt/json'
BS = a[a.index('--bsdx') + 1] if '--bsdx' in a else _ROOT + '/work/nexas_rt/json'
def ld(root, kind, name):
    for f in os.listdir(os.path.join(root, kind)):
        if f.lower() == (name + '.' + kind + '.json').lower():
            return json.load(open(os.path.join(root, kind, f), encoding='utf-8'))
def lst(g): return [v for k, v in g.items() if isinstance(v, list) and k != 'voiceTypeList'][0]
bwg, swg = lst(ld(BH, 'grp', 'wazagroup')), lst(ld(BS, 'grp', 'WazaGroup'))
bsg, ssg = lst(ld(BH, 'grp', 'spritegroup')), lst(ld(BS, 'grp', 'SpriteGroup'))
bse, sse = lst(ld(BH, 'grp', 'segroup')), lst(ld(BS, 'grp', 'SeGroup'))
SH = range(0, 8)
bw = {i: ld(BH, 'waz', bwg[i]['wazaDisplayName']) for i in SH}
sw = {i: ld(BS, 'waz', swg[i]['wazaDisplayName']) for i in SH}
sname = {i: {} for i in SH}
for i in SH:
    for j, s in enumerate(sw[i]['skillList']):
        if s and s.get('skillNameJapanese') is not None:
            sname[i].setdefault(s['skillNameJapanese'], j)
root = ld(BH, 'waz', mech)
need = {}  # (file, seq) -> depth
spr = collections.Counter(); se = collections.Counter(); vo = collections.Counter()
todo = [(None, s) for s in root['skillList'] if s]
seen = set()
while todo:
    src, s = todo.pop()
    for k, r in refs_of(s, 'bhe'):
        if k == 'waz' and r[0] in SH:
            if r not in seen:
                seen.add(r)
                sk = bw[r[0]]['skillList'][r[1]] if r[1] < len(bw[r[0]]['skillList']) else None
                need[r] = sk.get('skillNameJapanese') if sk else None
                if sk: todo.append((r, sk))
        elif k == 'spr': spr[r[0]] += 1
        elif k == 'se': se[r] += 1
        elif k == 'voice': vo[r] += 1
print('## shared skills needed (closure): %d' % len(need))
app = collections.Counter()
for (f, q), n in sorted(need.items()):
    j = sname[f].get(n)
    st = 'BSDX[%d]' % j if j is not None else 'APPEND'
    if j is None: app[f] += 1
    print('  %s[%d] %s -> %s' % (bwg[f]['wazaDisplayName'], q, n, st))
print('## to append per shared waz:', {bwg[f]['wazaDisplayName']: n for f, n in app.items()})
print('## sprite groups used (BHE idx: file -> BSDX idx)')
sfile = {(x.get('spriteFileName') or '').lower(): i for i, x in enumerate(ssg)}
for g, n in sorted(spr.items()):
    fn = bsg[g].get('spriteFileName') if g >= 0 else '(self)'
    print('  %d %s x%d -> %s' % (g, fn, n, sfile.get((fn or '').lower(), 'NONE' if g >= 0 else 'self')))
print('## SE used: %d distinct' % len(se))
sfn = {}
for c, cat in enumerate(sse):
    for i, it in enumerate(cat.get('seItems') or []):
        if it.get('existFlag'): sfn.setdefault((it.get('seFileName') or '').lower(), (c, i))
miss = []
for (c, i), n in sorted(se.items()):
    fn = bse[c]['seItems'][i].get('seFileName') if c < len(bse) and i < len(bse[c].get('seItems') or []) else None
    t = sfn.get((fn or '').lower())
    if t is None: miss.append(fn)
    print('  BHE(%d,%d) %s x%d -> %s' % (c, i, fn, n, t if t else 'MISSING in BSDX (needs ogg from BHE Se.pac + SeGroup entry)'))
print('## SE files missing in BSDX: %d %s' % (len(miss), miss))
print('## voices used by waz:', dict(vo))
