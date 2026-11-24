#!/usr/bin/env python3
"""Structural diff of two BSDX waz JSONs (e.g. our BHE->BSDX conversion vs a third-party port).

Usage: waz_struct_diff.py <a.waz.json> <b.waz.json> [--align name] [--ignore-refs] [--max N]
  --align name : pair skills by Japanese name (first occurrence in a) instead of by index
  --ignore-refs: blank wazFileNo/wazSequenceNo/spmFileSequence and SE/voice blobs before comparing
Reports per slot: events only in a / only in b / differing fields (aggregated by (slot, typeId, field)).
"""
import json, sys, collections

a_path, b_path = [x for x in sys.argv[1:] if not x.startswith('--')][:2]
ALIGN = '--align' in sys.argv
IGN = '--ignore-refs' in sys.argv
MAXN = int(sys.argv[sys.argv.index('--max') + 1]) if '--max' in sys.argv else 40
REFKEYS = {'wazFileNo', 'wazSequenceNo', 'spmFileSequence'}

def norm(o):
    if isinstance(o, dict):
        r = {}
        for k, v in o.items():
            if k == 'offset':
                continue
            if IGN and (k in REFKEYS or (k == 'byteDataList' and o.get('typeId') in (23, 24))):
                continue
            r[k] = norm(v)
        return r
    if isinstance(o, list):
        return [norm(v) for v in o]
    return o

def flat(o, p=''):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from flat(v, p + '.' + k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from flat(v, p + '[%d]' % i)
    else:
        yield p, o

A = json.load(open(a_path, encoding='utf-8'))['skillList']
B = json.load(open(b_path, encoding='utf-8'))['skillList']
pairs = []
if ALIGN:
    idx = {}
    for i, s in enumerate(A):
        if s:
            idx.setdefault(s.get('skillNameJapanese'), i)
    for j, s in enumerate(B):
        if s and s.get('skillNameJapanese') in idx:
            pairs.append((idx[s.get('skillNameJapanese')], j))
else:
    pairs = [(i, i) for i in range(min(len(A), len(B)))]

agg = collections.Counter()
examples = {}
identical = 0
for i, j in pairs:
    sa, sb = norm(A[i]), norm(B[j])
    if sa == sb:
        identical += 1
        continue
    if sa.get('phaseQuantity') != sb.get('phaseQuantity'):
        agg[('phaseQuantity',)] += 1
        continue
    if sa.get('skillSuffixList') != sb.get('skillSuffixList'):
        agg[('skillSuffixList',)] += 1
    for t, (pa, pb) in enumerate(zip(sa['phasesInfo'], sb['phasesInfo'])):
        ua = {u['unitQuantity']: u for u in pa['skillUnitCollection']}
        ub = {u['unitQuantity']: u for u in pb['skillUnitCollection']}
        for sl in sorted(set(ua) | set(ub)):
            la = (ua.get(sl) or {}).get('skillInfoObjectList', [])
            lb = (ub.get(sl) or {}).get('skillInfoObjectList', [])
            if len(la) != len(lb):
                agg[('slot', sl, 'count', len(la), len(lb))] += 1
                examples.setdefault(('slot', sl, 'count', len(la), len(lb)), (i, j, t))
                continue
            for ea, eb in zip(la, lb):
                if ea == eb:
                    continue
                fa, fb = dict(flat(ea)), dict(flat(eb))
                for k in sorted(set(fa) | set(fb)):
                    if fa.get(k) != fb.get(k):
                        key = ('slot', sl, 'type', ea.get('typeId'), k)
                        agg[key] += 1
                        examples.setdefault(key, (i, j, t, fa.get(k), fb.get(k)))
            xa = (ua.get(sl) or {}).get('skillInfoUnknownList', [])
            xb = (ub.get(sl) or {}).get('skillInfoUnknownList', [])
            if xa != xb:
                agg[('slot', sl, 'unknownList')] += 1
print('pairs=%d identical=%d differing=%d' % (len(pairs), identical, len(pairs) - identical))
for k, n in agg.most_common(MAXN):
    print('  %-60s x%-5d e.g. %s' % (k, n, examples.get(k)))
