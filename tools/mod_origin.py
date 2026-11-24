#!/usr/bin/env python3
"""Classify every file of an extracted mod pac by where the same file name exists in the original games.

Usage: mod_origin.py <mod dir> [--list] [--ext png,ogg]
Sources: <作業ツリー>/work/pac_lists/{BALDRHEARTEXE,BALDRSKY_DIVEX}/*.list.txt (name, size)
         + <作業ツリー>/work/extracted/<Pac>/ (BSDX staged pacs, real files -> size compare)
Output: counts per (ext, in BSDX?, in BHE?, same size as BHE?) and optionally per-file lines.
Names compared case-insensitively.
"""
import os, sys, collections
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')    # この作業ツリーの根（tools/ の 1 つ上）

L = _ROOT + '/work/pac_lists'
X = _ROOT + '/work/extracted'
args = [a for a in sys.argv[1:] if not a.startswith('--')]
LIST = '--list' in sys.argv
exts = None
for a in sys.argv:
    if a.startswith('--ext'):
        exts = set(sys.argv[sys.argv.index(a) + 1].split(','))

idx = collections.defaultdict(list)  # lower name -> [(game, pac, size)]
for game in ('BALDRHEARTEXE', 'BALDRSKY_DIVEX'):
    for fn in sorted(os.listdir(os.path.join(L, game))):
        pac = fn.replace('.list.txt', '')
        for line in open(os.path.join(L, game, fn), encoding='utf-8'):
            if line.startswith('#'):
                continue
            p = line.rstrip('\r\n').split('\t')
            if len(p) >= 4:
                idx[p[3].lower()].append((game, pac, int(p[1])))
for pac in os.listdir(X):
    d = os.path.join(X, pac)
    if os.path.isdir(d):
        for f in os.listdir(d):
            idx[f.lower()].append(('BALDRSKY_DIVEX', pac + '.pac', os.path.getsize(os.path.join(d, f))))

def classify(path):
    f = os.path.basename(path)
    sz = os.path.getsize(path)
    locs = idx.get(f.lower(), [])
    bsdx = [l for l in locs if l[0] == 'BALDRSKY_DIVEX']
    bhe = [l for l in locs if l[0] == 'BALDRHEARTEXE']
    tag = ('BSDX' if bsdx else '-', 'BHE' if bhe else '-',
           ('BHE=' if any(l[2] == sz for l in bhe) else 'BHE!=') if bhe else '',
           ('BSDX=' if any(l[2] == sz for l in bsdx) else 'BSDX!=') if bsdx else '')
    return tag, locs, sz

if __name__ == '__main__':
    d = args[0]
    c = collections.Counter()
    rows = []
    for f in sorted(os.listdir(d)):
        e = f.rsplit('.', 1)[-1].lower()
        if exts and e not in exts:
            continue
        tag, locs, sz = classify(os.path.join(d, f))
        c[(e,) + tag] += 1
        rows.append((f, sz, tag, locs))
    for k, v in sorted(c.items()):
        print('%-5s %-5s %-4s %-6s %-7s %5d' % (k + (v,)))
    if LIST:
        for f, sz, tag, locs in rows:
            print('\t'.join([f, str(sz), ' '.join(t for t in tag if t), ';'.join('%s/%s:%d' % l for l in locs)]))
