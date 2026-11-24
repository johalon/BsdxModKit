#!/usr/bin/env python3
"""Dump NeXAS_DX grp JSONs as index tables. Usage: grp_dump.py <json/grp dir> [Name]"""
import json, sys, os
d = sys.argv[1]
only = sys.argv[2] if len(sys.argv) > 2 else None
def load(n): return json.load(open(os.path.join(d, n + '.grp.json'), encoding='utf-8'))
if only in (None, 'MekaGroup'):
    print('## MekaGroup'); 
    for i, e in enumerate(load('MekaGroup')['mekaList']):
        print(i, e.get('existFlag'), e.get('mekaName'), e.get('mekaCodeName'))
if only in (None, 'WazaGroup'):
    print('## WazaGroup')
    for i, e in enumerate(load('WazaGroup')['wazaList']):
        print(i, e.get('existFlag'), e.get('wazaName'), e.get('wazaCodeName'), e.get('wazaDisplayName'), e.get('param'))
if only in (None, 'SpriteGroup'):
    print('## SpriteGroup')
    for i, e in enumerate(load('SpriteGroup')['spriteList']):
        print(i, e.get('existFlag'), e.get('spriteFileName'), e.get('spriteCodeName'), e.get('param'))
if only in (None, 'SeGroup'):
    print('## SeGroup')
    for i, g in enumerate(load('SeGroup')['seList']):
        items = g.get('seItems') or []
        print(i, g.get('existFlag'), g.get('seType'), g.get('seTypeCodeName'), 'items=%d' % len(items),
              [ (it.get('seItemName'), it.get('seFileName')) for it in items[:3] ])
if only in (None, 'BatVoice'):
    print('## BatVoice')
    j = load('BatVoice')
    print('types', [(t['voiceType'], t['voiceTypeCodeName']) for t in j['voiceTypeList']][:50])
    for i, g in enumerate(j['voiceList']):
        v = g.get('voices') or []
        print(i, g.get('existFlag'), g.get('characterName'), g.get('characterCodeName'), 'voices=%d' % len(v), [(x.get('voice'), x.get('voiceFileName')) for x in v[:2]])
if only in (None, 'ProgramMaterial'):
    print('## ProgramMaterial')
    j = load('ProgramMaterial')
    for k in ('array1', 'array2', 'array3'):
        print(k, len(j[k]), [a['values'] for a in j[k]][:20])
if only in (None, 'Term'):
    print('## Term')
    for g in load('Term')['termList']:
        print(g['termGroupName'], g['termGroupCodeName'], len(g['termItemList']), [(t['termItemName'], t['param1'], t['param2']) for t in g['termItemList'][:4]])
if only in (None, 'MapGroup'):
    print('## MapGroup')
    for i, g in enumerate(load('MapGroup')['groupList']):
        print(i, g.get('existFlag'), g.get('groupName'), g.get('groupCodeName'), g.get('groupResourceName'), g.get('int1'), 'items=%d' % len(g.get('items') or []))
