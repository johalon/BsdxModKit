#!/usr/bin/env python3
"""Summarize NeXAS_DX dat JSONs: name, cols, rows, types, first rows. Usage: dat_summary.py <json/dat dir> [name] [nrows]"""
import json, sys, os, glob
d = sys.argv[1]; only = (sys.argv[2] or None) if len(sys.argv) > 2 else None; n = int(sys.argv[3]) if len(sys.argv) > 3 else 2
for p in sorted(glob.glob(os.path.join(d, '*.dat.json'))):
    name = os.path.basename(p)[:-9]
    if only and name != only: continue
    j = json.load(open(p, encoding='utf-8'))
    t = ''.join({'String': 'S', 'Integer': 'i', 'IntegerNew': 'I', 'Byte': 'b'}.get(x, '?') for x in j['columnTypes'])
    print(f"{name}: cols={j['columnCount']} rows={len(j['data'])} types={t}")
    for r in j['data'][:n]:
        print('    ', [str(x)[:40] for x in r][:16])
