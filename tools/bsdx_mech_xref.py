#!/usr/bin/env python3
"""Cross-reference MekaGroup IDs against mech-related .dat tables (uses TSVs from bsdx_tables.py and .mek names).
usage: bsdx_mech_xref.py <tsvdir> <mekdir>
"""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bsdx_mekinfo import parse_mek
T, M = sys.argv[1], sys.argv[2]
def tsv(n):
    rows = []
    for line in open(os.path.join(T, n + '.tsv'), encoding='utf-8'):
        if line.startswith('#'): continue
        rows.append(line.rstrip('\n').split('\t'))
    return rows
grp = {int(r[0]): r[1] for r in tsv('MekaGroup')}
names = {}
for i, code in grp.items():
    p = os.path.join(M, code + '.mek')
    if os.path.exists(p):
        m = parse_mek(open(p, 'rb').read()); names[i] = (m['name'], m['pilot'], len(m['weapons']))
tabs = {}
def col0(n, c=1):
    return {int(r[c]): int(r[0]) for r in tsv(n)}
tabs['Meka'] = col0('Meka'); tabs['MekaPilot'] = col0('MekaPilot'); tabs['SelMenu'] = col0('SelectMekaMenu')
tabs['Tourn'] = col0('TournamentMekaData'); tabs['SvMain'] = col0('SurvivalMekaMain'); tabs['SvZako'] = col0('SurvivalMekaZako'); tabs['SvRare'] = col0('SurvivalMekaRare')
we = tsv('WeaponEquip')
print('id\tcode\tname\tpilot\tnWeap\t' + '\t'.join(tabs) + '\tWeaponEquip(row=id)')
for i in sorted(grp):
    n = names.get(i, ('?', '?', 0))
    w = we[i][1:] if i < len(we) else []
    wst = 'none' if all(x == '-1' for x in w) else 'set'
    print('%d\t%s\t%s\t%s\t%d\t' % (i, grp[i], n[0], n[1], n[2]) + '\t'.join(str(tabs[t].get(i, '-')) for t in tabs) + '\t' + wst)
