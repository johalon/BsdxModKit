#!/usr/bin/env python3
"""Summarize NeXAS_DX mek JSON outputs (from RoundTrip harness). Usage: mek_summary.py <json/mek dir>"""
import json, sys, os, glob
rows = []
for p in sorted(glob.glob(os.path.join(sys.argv[1], '*.mek.json'))):
    m = json.load(open(p, encoding='utf-8'))
    b = m['mekBasicInfo']; mb = m['mekMaterialBlock']
    w = m['mekWeaponInfoMap']
    rows.append((os.path.basename(p)[:-9], b['mekName'], b['mekNameEnglish'], b['pilotNameKanji'], b['wazFileSequence'], b['spmFileSequence'],
                 b['mekType'], b['baseHealth'], len(w), len(m['mekAiInfoList']), mb['extraRegularCount'], len(mb['entries']),
                 os.path.getsize(p)))
print('| file | mekName | ruby | pilot | waz# | spm# | type | HP/10 | weapons | AI | extra | material | jsonsize |')
print('|' + '---|' * 13)
for r in rows:
    print('| ' + ' | '.join(str(x).replace('|', '/').replace('\n', ' ') for x in r) + ' |')
