#!/usr/bin/env python3
"""Validate a BSDX mech (mek + its waz) against the registries it will run with (index-range lint).

Usage: mek_check.py <mek.json> [--json-dir DIR ...] [--waz NAME] [--quiet]
  --json-dir: one or more NeXAS_DX JSON roots searched in order (mod first, then original);
              default <作業ツリー>/work/nexas_rt/json. grp/waz are taken from the first root that has them.
Checks (each prints a count of violations + examples):
  W1 weapon.wazSequence < skills in own waz          W2 weapon.switchToMekNo in -1..MekaGroup-1
  A1 AI attack event (type 2) mekWeaponInfoMapNo < #weapons   A2 AI Term int1 < #Term groups, typeList[0] < items
  V1 VoiceInfo.version (=BatVoice idx) < #chars      V2 every table groupId < #voices of that char
  M1 MaterialBlock dims == (#SpriteGroup, #SeGroup, #BatVoice)
  M2 material se ids exist (SeGroup item existFlag)  M3 material voice ids < #voices
  M4 material sprite group referenced but SpriteGroup entry empty
  R1 waz WazaSelect (file,seq): file registered and seq < WazaGroup.param (= skills in that waz file)
  R2 waz SE (cat,item) exists   R3 waz voice (char,item) exists   R4 waz sprite spmFileSequence registered
  R5 waz Term int1 in range (BSDX has 30 groups; BHE had 34 with different order)
  R6 sprite groups used by waz but never preloaded by this mek's MaterialBlock (informational)
  R8 waz Term JUMP '技ジャンプ' (paramList = wazFileNo, skillNo) in range (same rule as R1)
  R9 (with --spm) sprite anim/pattern exist in the spm (spm JSON looked up in the json roots by SpriteGroup file name)
  --full: list every violation (one 'FULL <code> <msg>' line each)
  --also-waz A,B,..: run R1/R2/R4/R8/R9 over these whole waz files too (e.g. shared waz with appended skills)
"""
import json, os, sys, struct, collections
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')    # この作業ツリーの根（tools/ の 1 つ上）

args = sys.argv[1:]
roots = []
i = 0
mekp = None
WAZ = None
ALSO = []
while i < len(args):
    if args[i] == '--json-dir':
        i += 1
        while i < len(args) and not args[i].startswith('--'):
            roots.append(args[i]); i += 1
        continue
    if args[i] == '--waz':
        WAZ = args[i + 1]; i += 2; continue
    if args[i] == '--also-waz':
        ALSO = args[i + 1].split(','); i += 2; continue
    if args[i].startswith('--'):
        i += 1; continue
    mekp = args[i]; i += 1
roots = roots or [_ROOT + '/work/nexas_rt/json']
QUIET = '--quiet' in args
SPM = '--spm' in args
FULL = '--full' in args

def ld(kind, name):
    for r in roots:
        d = os.path.join(r, kind)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.lower() == (name + '.' + kind + '.json').lower():
                return json.load(open(os.path.join(d, f), encoding='utf-8'))
    return None

def lst(g):
    return [v for k, v in g.items() if isinstance(v, list) and k != 'voiceTypeList'][0]

MG, WG, SG = lst(ld('grp', 'MekaGroup')), lst(ld('grp', 'WazaGroup')), lst(ld('grp', 'SpriteGroup'))
SE, BV = lst(ld('grp', 'SeGroup')), ld('grp', 'BatVoice')['voiceList']
TERM = ld('grp', 'Term')['termList']
mek = json.load(open(mekp, encoding='utf-8'))
b = mek['mekBasicInfo']
W = mek['mekWeaponInfoMap']
wazname = WAZ or WG[b['wazFileSequence']]['wazaDisplayName']
waz = ld('waz', wazname)
nsk = len(waz['skillList']) if waz else -1
viol = collections.defaultdict(list)

def add(code, msg):
    viol[code].append(msg)

def ints(raw, n):
    return struct.unpack('<%di' % n, bytes((x + 256) % 256 for x in raw[:4 * n]))

def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)

def term_check(o, code, where):
    for d in walk(o):
        for k in ('bsdxInfoCollectionList', 'bsdxInfoCollectionList1', 'bsdxInfoCollectionList2'):
            for t in d.get(k) or []:
                if not isinstance(t, dict) or 'int1' not in t:
                    continue
                g = t['int1']
                if not (0 <= g < len(TERM)):
                    add(code, '%s term group %d out of range' % (where, g)); continue
                tl = t.get('typeList') or []
                if tl and not (0 <= tl[0] < len(TERM[g]['termItemList'])):
                    add(code, '%s term %s[%d] item out of range (%d items)' % (where, TERM[g]['termGroupCodeName'], tl[0], len(TERM[g]['termItemList'])))

print('== %s : %s / %s  waz=%s(%d skills) spm=%s(%s) weapons=%d AI=%s voice.version=%s' % (
    os.path.basename(mekp), b['mekName'], b['pilotNameKanji'], wazname, nsk, b['spmFileSequence'],
    SG[b['spmFileSequence']].get('spriteFileName') if 0 <= b['spmFileSequence'] < len(SG) else '?', len(W),
    [(a['aiTypeEnglish'], len(a['cpuEventList'])) for a in mek['mekAiInfoList']], mek['mekVoiceInfo'].get('version')))
for k, w in W.items():
    if not (0 <= w['wazSequence'] < nsk):
        add('W1', 'weapon %s %s wazSequence %d' % (k, w['weaponName'], w['wazSequence']))
    if not (-1 <= w['switchToMekNo'] < len(MG)):
        add('W2', 'weapon %s switchToMekNo %d' % (k, w['switchToMekNo']))
for a in mek['mekAiInfoList']:
    for j, e in enumerate(a['cpuEventList']):
        if e['type'] == 2 and not (0 <= e.get('mekWeaponInfoMapNo', -1) < len(W)):
            add('A1', 'AI %s ev%d attack weapon #%s (have %d)' % (a['aiTypeEnglish'], j, e.get('mekWeaponInfoMapNo'), len(W)))
        term_check(e, 'A2', 'AI %s ev%d' % (a['aiTypeEnglish'], j))
v = mek['mekVoiceInfo']
ver = v.get('version')
if ver is not None and ver >= 0:
    if ver >= len(BV):
        add('V1', 'version %d >= %d chars' % (ver, len(BV)))
    else:
        nv = len(BV[ver].get('voices') or [])
        mx = max([c['groupId'] for row in v['table'] for col in row for c in col] or [-1])
        bad = sorted({c['groupId'] for row in v['table'] for col in row for c in col if not (0 <= c['groupId'] < nv)})
        if bad:
            add('V2', 'BatVoice[%d]=%s has %d voices but table uses groupId up to %d (bad: %d ids, e.g. %s)' % (
                ver, BV[ver].get('characterCodeName'), nv, mx, len(bad), bad[:8]))
mb = mek['mekMaterialBlock']
loaded_spr = set()
for n, e in enumerate(mb['entries']):
    dims = (len(e['spriteGroups']), len(e['seGroups']), len(e['voiceGroups']))
    if dims != (len(SG), len(SE), len(BV)):
        add('M1', 'entry %d dims %s != %s' % (n, dims, (len(SG), len(SE), len(BV)))); continue
    for g, ids in enumerate(e['spriteGroups']):
        if ids:
            loaded_spr.add(g)
            if not SG[g].get('existFlag'):
                add('M4', 'entry %d sprite group %d empty' % (n, g))
    for c, ids in enumerate(e['seGroups']):
        items = SE[c].get('seItems') or []
        for it in ids:
            if not (0 <= it < len(items)) or not items[it].get('existFlag'):
                add('M2', 'entry %d se (%d,%d)' % (n, c, it))
    for c, ids in enumerate(e['voiceGroups']):
        nv = len(BV[c].get('voices') or [])
        for it in ids:
            if not (0 <= it < nv):
                add('M3', 'entry %d voice (%d,%d) >= %d' % (n, c, it, nv))
used_spr = collections.Counter()
_spm_cache = {}
def spm_json(g):
    if g not in _spm_cache:
        fn = SG[g].get('spriteFileName') or ''
        _spm_cache[g] = ld('spm', fn[:-4]) if fn.lower().endswith('.spm') else None
    return _spm_cache[g]
def jumps(o):
    for d in walk(o):
        for k, v in d.items():
            if 'InfoCollectionList' in k and isinstance(v, list):
                for t in v:
                    if isinstance(t, dict) and t.get('int1') == 16 and (t.get('typeList') or [None])[0] == 1 and len(t.get('paramList') or []) >= 2:
                        yield t['paramList'][0], t['paramList'][1]
def ref_checks(wz, label, selfwaz, selfspm):
    for si, s in enumerate(wz['skillList']):
        if not s:
            continue
        for f, q in jumps(s):
            f = selfwaz if f == -1 else f
            if not (0 <= f < len(WG)) or not WG[f].get('existFlag') or not (0 <= q < WG[f]['param']):
                add('R8', '%s skill %d JUMP (%d,%d) out of range' % (label, si, f, q))
        if SPM:
            for d in walk(s):
                if 'spmFileSequence' in d and 'actionGroupNumber' in d:
                    g = selfspm if d['spmFileSequence'] == -1 else d['spmFileSequence']
                    if g is None or g < 0 or g >= len(SG):
                        continue
                    sp = spm_json(g)
                    if sp is None:
                        add('R9', '%s spm for group %d not found (skip)' % (label, g)); continue
                    a, p_ = d['actionGroupNumber'], d['actionNumber']
                    if not (0 <= a < len(sp['animData'])) or not (0 <= p_ < max(1, sp['animData'][a]['numPat'])):
                        add('R9', '%s skill %d sprite g%d anim %d pat %d out of range' % (label, si, g, a, p_))
for wn in ALSO:
    wz = ld('waz', wn)
    wi = [i for i, x in enumerate(WG) if (x.get('wazaDisplayName') or '').lower() == wn.lower()]
    if wz is None or not wi:
        add('R8', 'also-waz %s not found' % wn); continue
    if len(wz['skillList']) != WG[wi[0]]['param']:
        add('R1', 'also-waz %s has %d skills but WazaGroup.param %d' % (wn, len(wz['skillList']), WG[wi[0]]['param']))
    ref_checks(wz, wn, wi[0], None)
    for si, s in enumerate(wz['skillList']):
        if not s:
            continue
        for d in walk(s):
            if 'wazFileNo' in d and 'wazSequenceNo' in d:
                f, q = d['wazFileNo'], d['wazSequenceNo']
                f = wi[0] if f == -1 else f
                if not (0 <= f < len(WG)) or not WG[f].get('existFlag') or not (0 <= q < WG[f]['param']):
                    add('R1', '%s skill %d WazaSelect (%d,%d) out of range' % (wn, si, f, q))
            elif d.get('typeId') == 23 and 'byteDataList' in d:
                for x in d['byteDataList']:
                    c, it = ints(x, 2)
                    if not (0 <= c < len(SE) and 0 <= it < len(SE[c].get('seItems') or []) and SE[c]['seItems'][it].get('existFlag')):
                        add('R2', '%s skill %d SE (%d,%d)' % (wn, si, c, it))
            elif 'spmFileSequence' in d and 'actionGroupNumber' in d and d['spmFileSequence'] >= 0:
                g = d['spmFileSequence']
                if g >= len(SG) or not SG[g].get('existFlag'):
                    add('R4', '%s skill %d sprite group %d unregistered' % (wn, si, g))
if waz:
    ref_checks(waz, wazname, b['wazFileSequence'], b['spmFileSequence'])
    for si, s in enumerate(waz['skillList']):
        if not s:
            continue
        for d in walk(s):
            t = d.get('typeId')
            if 'wazFileNo' in d and 'wazSequenceNo' in d:
                f, q = d['wazFileNo'], d['wazSequenceNo']
                if f == -1:
                    f = b['wazFileSequence']
                if not (0 <= f < len(WG)) or not WG[f].get('existFlag'):
                    add('R1', 'skill %d WazaSelect file %d unregistered' % (si, f))
                elif not (0 <= q < WG[f]['param']):
                    add('R1', 'skill %d WazaSelect %s[%d] >= %d' % (si, WG[f]['wazaDisplayName'], q, WG[f]['param']))
            elif 'spmFileSequence' in d and 'actionGroupNumber' in d:
                g = d['spmFileSequence']
                g = b['spmFileSequence'] if g == -1 else g
                if g >= 0:
                    used_spr[g] += 1
                    if g >= len(SG) or not SG[g].get('existFlag'):
                        add('R4', 'skill %d sprite group %d unregistered' % (si, g))
            elif t == 23 and 'byteDataList' in d:
                for x in d['byteDataList']:
                    c, it = ints(x, 2)
                    ok = 0 <= c < len(SE) and 0 <= it < len(SE[c].get('seItems') or []) and SE[c]['seItems'][it].get('existFlag')
                    if not ok:
                        add('R2', 'skill %d SE (%d,%d)' % (si, c, it))
            elif t == 24 and 'byteDataList' in d:
                for x in d['byteDataList']:
                    c, it = ints(x, 2)
                    if not (0 <= c < len(BV) and 0 <= it < len(BV[c].get('voices') or [])):
                        add('R3', 'skill %d voice (%d,%d)' % (si, c, it))
        term_check(s, 'R5', 'skill %d' % si)
        # R7: BSDX convention (all 2792 original hit attack terms use group 21 ATTACK2, nokezori terms use 23 PARAM);
        # BHE uses 22 for the hit attack term -> must be remapped 22->21 when porting.
        for d in walk(s):
            for hu in d.get('ceventHitUnitList') or []:
                dd = hu.get('data') or {}
                for t in dd.get('bsdxInfoCollectionList') or []:
                    if hu.get('unitSlotNum') == 6 and t.get('int1') != 21:
                        add('R7', 'skill %d hit attack term group %s (BSDX expects 21)' % (si, t.get('int1')))
                for nu in dd.get('ceventNokezoriUnitList') or []:
                    for t in (nu.get('data') or {}).get('bsdxInfoCollectionList') or []:
                        if t.get('int1') in (21, 22):   # among groups 21-23 BSDX only ever uses 23 here
                            add('R7', 'skill %d nokezori term group %s (BSDX expects 23)' % (si, t.get('int1')))
    for g, n in sorted(used_spr.items()):
        if g not in loaded_spr and g > 8:
            add('R6', 'sprite group %d (%s) used %d times by waz but not in MaterialBlock' % (g, SG[g].get('spriteFileName') if g < len(SG) else '?', n))
for code in sorted(viol):
    L = viol[code]
    ex = collections.Counter(L)
    print('  %s: %d  e.g. %s' % (code, len(L), '; '.join(list(dict.fromkeys(L))[: (3 if QUIET else 6)])))
    if FULL:
        for m in dict.fromkeys(L):
            print('    FULL %s %s' % (code, m))
if not viol:
    print('  OK (no violations)')
