#!/usr/bin/env python3
"""External references of a waz (BSDX or BHE NeXAS_DX JSON): sprite / waz(bullet,effect) / SE / voice.

Usage:
  waz_refs.py <waz.json> [--game bsdx|bhe] [--skills] [--pairs]
    --skills : per-skill table (name + counts)
    --pairs  : full histograms of (wazFileNo,seq), (SeGroup,item), (BatVoice,item)
  waz_refs.py --map <bhe waz.json> <bsdx waz.json>
    Aligns skills by index (and checks names), then derives the remap tables actually applied
    (BHE ref -> BSDX ref) for WazaSelect / SE / voice / sprite, event by event in document order.

Event typeIds: SE = BSDX 23 / BHE 29, Voice = BSDX 24 / BHE 30 (byteDataList blobs: SE {cat,item,prob,flag},
voice {char,item,prob}). WazaSelect = any object with wazFileNo/wazSequenceNo. Sprite = spmFileSequence+actionGroupNumber.
"""
import json, sys, struct, collections

def walk(o, depth=0):
    if isinstance(o, dict):
        yield depth, o
        for v in o.values():
            yield from walk(v, depth + 1)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v, depth)

def ints(raw, n):
    return struct.unpack('<%di' % n, bytes((x + 256) % 256 for x in raw[:4 * n]))

def guess_game(w):
    for _, d in walk(w):
        if 'bheInfoCollectionList' in d or 'bheInfoCollectionList1' in d:
            return 'bhe'
        if 'bsdxInfoCollectionList' in d or 'bsdxInfoCollectionList1' in d:
            return 'bsdx'
    return 'bsdx'

def refs_of(obj, game):
    se_t, vo_t = (23, 24) if game == 'bsdx' else (29, 30)
    out = []
    for depth, d in walk(obj):
        t = d.get('typeId')
        if 'wazFileNo' in d and 'wazSequenceNo' in d:
            out.append(('waz', (d['wazFileNo'], d['wazSequenceNo'])))
        elif 'spmFileSequence' in d and 'actionGroupNumber' in d:
            out.append(('spr', (d['spmFileSequence'], d['actionGroupNumber'], d['actionNumber'])))
        elif t == se_t and 'byteDataList' in d:
            for b in d['byteDataList']:
                out.append(('se', ints(b, 3)[:2]))
        elif t == vo_t and 'byteDataList' in d:
            for b in d['byteDataList']:
                out.append(('voice', ints(b, 2)))
    return out

def skills(w):
    return w['skillList']

def main():
    a = sys.argv[1:]
    if a and a[0] == '--map':
        src, dst = json.load(open(a[1], encoding='utf-8')), json.load(open(a[2], encoding='utf-8'))
        gs, gd = guess_game(src), guess_game(dst)
        S, D = skills(src), skills(dst)
        print('skills: src=%d (%s) dst=%d (%s)' % (len(S), gs, len(D), gd))
        same = diff = 0
        maps = {k: collections.defaultdict(collections.Counter) for k in ('waz', 'se', 'voice', 'spr')}
        misalign = []
        for i in range(min(len(S), len(D))):
            s, d = S[i], D[i]
            if not s or not d:
                if bool(s) != bool(d):
                    misalign.append((i, 'empty-mismatch'))
                continue
            if s.get('skillNameJapanese') == d.get('skillNameJapanese'):
                same += 1
            else:
                diff += 1
                misalign.append((i, s.get('skillNameJapanese'), d.get('skillNameJapanese')))
            rs, rd = refs_of(s, gs), refs_of(d, gd)
            for kind in maps:
                xs = [r for k, r in rs if k == kind]
                ys = [r for k, r in rd if k == kind]
                if len(xs) == len(ys):
                    for x, y in zip(xs, ys):
                        maps[kind][x][y] += 1
                else:
                    maps[kind][('COUNT_MISMATCH', i)][(len(xs), len(ys))] += 1
        print('name-aligned skills: same=%d differ=%d' % (same, diff))
        for m in misalign[:30]:
            print('  misalign', m)
        for kind, m in maps.items():
            print('## %s remap (src -> dst : count)  [%d distinct src]' % (kind, len(m)))
            for x in sorted(m, key=str):
                ys = m[x]
                print('  %s -> %s' % (x, ', '.join('%s×%d' % (y, n) for y, n in ys.most_common())))
        return
    w = json.load(open(a[0], encoding='utf-8'))
    game = a[a.index('--game') + 1] if '--game' in a else guess_game(w)
    S = skills(w)
    print('%s: game=%s skills=%d (non-empty %d)' % (a[0], game, len(S), sum(1 for s in S if s)))
    tot = collections.defaultdict(collections.Counter)
    rows = []
    for i, s in enumerate(S):
        if not s:
            continue
        r = refs_of(s, game)
        c = collections.Counter(k for k, _ in r)
        rows.append((i, s.get('skillNameJapanese'), c))
        for k, v in r:
            tot[k][v] += 1
    # summaries
    print('waz targets by file:', dict(collections.Counter({}).__class__(
        {f: sum(n for (ff, _), n in tot['waz'].items() if ff == f) for f in sorted({ff for ff, _ in tot['waz']})})))
    print('sprite spmFileSequence:', dict(collections.Counter({f: sum(n for (ff, _, _), n in tot['spr'].items() if ff == f) for f in {ff for ff, _, _ in tot['spr']}})))
    print('SE categories:', dict(sorted(collections.Counter({c: sum(n for (cc, _), n in tot['se'].items() if cc == c) for c in {cc for cc, _ in tot['se']}}).items())))
    print('voice chars:', dict(sorted(collections.Counter({c: sum(n for (cc, _), n in tot['voice'].items() if cc == c) for c in {cc for cc, _ in tot['voice']}}).items())))
    if '--pairs' in a:
        for k in ('waz', 'se', 'voice'):
            print('## %s distinct=%d' % (k, len(tot[k])))
            print('  ' + ' '.join('%s:%d' % (x, n) for x, n in sorted(tot[k].items())))
    if '--skills' in a:
        for i, n, c in rows:
            print('%4d %-30s %s' % (i, n, dict(c)))

if __name__ == '__main__':
    main()
