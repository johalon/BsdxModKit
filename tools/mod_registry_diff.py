#!/usr/bin/env python3
"""Diff NeXAS_DX JSON dumps of BSDX registries/tables (grp/dat) between the original game and a mod.

Usage: mod_registry_diff.py <orig json root> <mod json root> [--full]
  json roots are RoundTrip outputs (<root>/grp/*.grp.json, <root>/dat/*.dat.json).
  Original: /path/to/workspace/work/nexas_rt/json (NeXAS_DX bundled data = Update-wins).
Reports, per file: entry count orig->mod, appended entries, changed entries (field-level),
and for SeGroup/BatVoice also item-level changes inside each category/character.
"""
import json, os, sys

FULL = '--full' in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith('--')]
O, M = args[0], args[1]

def load(root, sub, name):
    for n in os.listdir(os.path.join(root, sub)) if os.path.isdir(os.path.join(root, sub)) else []:
        if n.lower() == name.lower():
            return json.load(open(os.path.join(root, sub, n), encoding='utf-8'))
    return None

def short(x, n=160):
    s = json.dumps(x, ensure_ascii=False)
    return s if FULL or len(s) <= n else s[:n] + '…'

def items_diff(tag, a, b, key_fields):
    a = a or []; b = b or []
    out = []
    if len(a) != len(b):
        out.append('    %s items %d -> %d' % (tag, len(a), len(b)))
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else None
        y = b[i] if i < len(b) else None
        if x != y:
            kind = 'ADD' if x is None else ('DEL' if y is None else 'CHG')
            fy = {k: (y or {}).get(k) for k in key_fields}
            fx = {k: (x or {}).get(k) for k in key_fields}
            out.append('    %s[%d] %s %s%s' % (tag, i, kind, short(fy, 200), '' if kind == 'ADD' else '  (was %s)' % short(fx, 120)))
    return out

def list_diff(name, la, lb, key_fields, nested=None):
    print('## %s: %d -> %d entries' % (name, len(la), len(lb)))
    for i in range(max(len(la), len(lb))):
        x = la[i] if i < len(la) else None
        y = lb[i] if i < len(lb) else None
        if x == y:
            continue
        kind = 'ADD' if x is None else ('DEL' if y is None else 'CHG')
        head = {k: (y or {}).get(k) for k in key_fields}
        line = '  [%d] %s %s' % (i, kind, short(head, 220))
        if kind == 'CHG':
            was = {k: x.get(k) for k in key_fields}
            if was != head:
                line += '  (was %s)' % short(was, 160)
        print(line)
        if nested:
            sub, sk = nested
            if kind == 'ADD':
                its = (y or {}).get(sub) or []
                print('    %d items, e.g. %s' % (len(its), short([{k: it.get(k) for k in sk} for it in its[:4]], 400)))
            elif kind == 'CHG':
                for l in items_diff(sub, x.get(sub), y.get(sub), sk)[: (10**6 if FULL else 25)]:
                    print(l)

def grp(name, listkey, fields, nested=None):
    a, b = load(O, 'grp', name + '.grp.json'), load(M, 'grp', name + '.grp.json')
    if b is None:
        return
    if name == 'BatVoice' and a['voiceTypeList'] != b['voiceTypeList']:
        print('## BatVoice voiceTypeList changed: %d -> %d' % (len(a['voiceTypeList']), len(b['voiceTypeList'])))
    list_diff(name, a[listkey], b[listkey], fields, nested)

def dat(name):
    a, b = load(O, 'dat', name + '.dat.json'), load(M, 'dat', name + '.dat.json')
    if b is None:
        return
    ra, rb = a['data'], b['data']
    print('## %s.dat: cols %s -> %s, rows %d -> %d' % (name, a['columnTypes'], b['columnTypes'] if b['columnTypes'] != a['columnTypes'] else 'same', len(ra), len(rb)))
    for i in range(max(len(ra), len(rb))):
        x = ra[i] if i < len(ra) else None
        y = rb[i] if i < len(rb) else None
        if x != y:
            print('  row %d %s %s%s' % (i, 'ADD' if x is None else ('DEL' if y is None else 'CHG'), short(y, 300), '' if x is None else '  (was %s)' % short(x, 200)))

grp('MekaGroup', 'mekaList', ['existFlag', 'mekaName', 'mekaCodeName'])
grp('WazaGroup', 'wazaList', ['existFlag', 'wazaName', 'wazaCodeName', 'wazaDisplayName', 'param'])
grp('SpriteGroup', 'spriteList', ['existFlag', 'spriteFileName', 'spriteCodeName', 'param'])
grp('SeGroup', 'seList', ['existFlag', 'seType', 'seTypeCodeName'], ('seItems', ['existFlag', 'seItemName', 'seItemCodeName', 'seFileName']))
grp('BatVoice', 'voiceList', ['existFlag', 'characterName', 'characterCodeName'], ('voices', ['existFlag', 'voice', 'voiceCodeName', 'voiceFileName']))
for d in ['MekaPilot', 'SelectMekaMenu', 'Meka', 'WeaponEquip', 'HellConfig', 'TournamentMekaData', 'BGM', 'AkisRoomItem']:
    dat(d)
