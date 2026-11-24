#!/usr/bin/env python3
"""waz_summary.py — BSDX 機体の技(waz)を人が読める表にする。

  python3 waz_summary.py Kou                 # 武装一覧(mek の武装 → waz の技)
  python3 waz_summary.py Kou --skills        # waz の全技
  python3 waz_summary.py Kou --skill 12      # 技 12 の詳細(ターン別タイムライン)
  python3 waz_summary.py Tama01 --skills     # 共通 waz(弾など)も可
  オプション: --json-dir DIR (既定 <作業ツリー>/work/nexas_rt/json), --csv

入力は NeXAS_DX の JSON (tools/run_roundtrip.sh の出力)。フィールドの意味は tools/waz_fields.json /
notes/05_waz_field_dictionary.md を参照。【推定】の項目は表示も推定である点に注意。
"""
import json, os, sys, argparse, functools, collections, signal
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')    # この作業ツリーの根（tools/ の 1 つ上）
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

P = argparse.ArgumentParser()
P.add_argument('name', help='MekaGroup 名 / mek ファイル名(Kou, Sora…) または waz 名(Tama01…)')
P.add_argument('--json-dir', default=_ROOT + '/work/nexas_rt/json')
P.add_argument('--skills', action='store_true')
P.add_argument('--skill', type=int)
P.add_argument('--csv', action='store_true')
A = P.parse_args()
J = A.json_dir

def load(kind, name):
    p = os.path.join(J, kind, name + '.' + kind + '.json')
    if not os.path.exists(p):
        low = {f.lower(): f for f in os.listdir(os.path.join(J, kind))}
        f = low.get((name + '.' + kind + '.json').lower())
        if not f: return None
        p = os.path.join(J, kind, f)
    return json.load(open(p, encoding='utf-8'))

WG = load('grp', 'WazaGroup')['wazaList']
SG = load('grp', 'SpriteGroup')
SG = [v for v in SG.values() if isinstance(v, list)][0]
SE = load('grp', 'SeGroup')['seList']
BV = load('grp', 'BatVoice')['voiceList']
TERM = load('grp', 'Term')['termList']

@functools.lru_cache(None)
def waz_by_idx(i):
    if i is None or i < 0 or i >= len(WG) or not WG[i].get('existFlag'): return None
    return load('waz', WG[i]['wazaDisplayName'])

def waz_name(i):
    return WG[i]['wazaDisplayName'] if 0 <= i < len(WG) and WG[i].get('existFlag') else '?%d' % i

def skill_name(w, i):
    try:
        s = w['skillList'][i]
        return (s.get('skillNameJapanese') or '(無名)') if s else '(空)'
    except Exception:
        return '(範囲外)'

# ------------------------------------------------------------------ helpers
def events(skill, typeId=None, slot=None):
    for t, ph in enumerate(skill.get('phasesInfo') or []):
        for u in ph['skillUnitCollection']:
            if slot is not None and u['unitQuantity'] != slot: continue
            for o in u['skillInfoObjectList']:
                if typeId is None or o['typeId'] == typeId:
                    yield t, u['unitQuantity'], o

def subobj(o, idx):
    for k, v in o.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and 'unitSlotNum' in v[0]:
            for u in v:
                if u.get('unitSlotNum') == idx and u.get('buffer') and u.get('data'):
                    return u['data']
    return None

def val(o):
    """CEventVal / ValRandom の主値(終了値)"""
    if o is None: return None
    return o['int5'] if 'int5' in o else o.get('int4')

def term_text(b):
    """Term (bsdxInfoCollection) を Term.grp の語彙で表示(推定ルール: param2>=0 はサブグループへ)"""
    if not b: return ''
    g = b['int1']; out = []; vals = list(b['paramList']); vi = 0
    for tok in b['typeList']:
        if g is None or g < 0 or g >= len(TERM):
            out.append('#%d' % tok); g = None; continue
        items = TERM[g]['termItemList'] or []
        if tok < 0 or tok >= len(items):
            out.append('%s#%d' % (TERM[g]['termGroupCodeName'], tok)); g = None; continue
        it = items[tok]; s = it['termItemName']
        code = it['termItemCodeName'] or ''
        n = s.count('$v') + code.count('$v')
        if it['param2'] in (-1, -2):
            n = max(n, -it['param2'])
        if n:
            vs = vals[vi:vi + n]; vi += n
            s += '(' + ','.join(map(str, vs)) + ')'
        out.append(s)
        g = it['param2'] if it['param2'] >= 0 else None
    if vi < len(vals): out.append('v=' + ','.join(map(str, vals[vi:])))
    if any(b.get('intList3') or []) or any(b.get('intList4') or []):
        out.append('[obj %s/%s]' % (b.get('intList3'), b.get('intList4')))
    return '→'.join(out)

def attack_text(term):
    if not term: return '-'
    b = term['bsdxInfoCollectionList'][0]
    t = b['typeList'][0] if b['typeList'] else 0
    v = b['paramList'][0] if b['paramList'] else 0
    return {0: str(v), 1: '自HP%d%%' % v, 2: '敵HP%d%%' % v}.get(t, term_text(b))

def attack_value(term):
    if not term: return 0
    b = term['bsdxInfoCollectionList'][0]
    return b['paramList'][0] if (b['paramList'] and (not b['typeList'] or b['typeList'][0] == 0)) else 0

def se_name(b):
    a, i, p, f = b
    try:
        it = SE[a]['seItems'][i]
        n = it.get('seItemName') or '(空)'
    except Exception:
        n = '?'
    return '%s/%s%s' % (SE[a]['seTypeCodeName'] if 0 <= a < len(SE) else a, n, '' if p == 100 else '(%d%%)' % p)

def voice_name(b):
    c, i, p = b
    try:
        ch = BV[c]; v = ch['voices'][i]
        return '%s「%s」%s' % (ch['characterName'], v.get('voice', '?'), '' if p == 100 else '(%d%%)' % p)
    except Exception:
        return 'voice?%d/%d' % (c, i)

def ints(raw, n):
    import struct
    return struct.unpack('<%di' % n, bytes((x + 256) % 256 for x in raw))

NOKE = {17: '地', 18: '空', 19: '空→地', 20: 'ダウン'}
def noke_text(hit):
    n = subobj(hit, 17)
    if not n: return '-'
    if n['int1'] != 0:
        return ['指定', '同:地→地', '同:空', '同:空→地', '同:ダウン', 'なし'][n['int1']] if n['int1'] < 6 else '?'
    return '停%d HB%d/%d ダ%d 吹%d' % (n['int2'], n['int3'], n['int4'], n['int7'], n['int10'])

# ------------------------------------------------------------------ skill analysis
def hits_of(w, si, depth=0, seen=None, mult=1, tag=''):
    """技 si の Hit 一覧(弾を生成していれば参照先の Hit も辿る)"""
    seen = seen or set()
    if (id(w), si) in seen or depth > 3: return []
    seen = seen | {(id(w), si)}
    try: s = w['skillList'][si]
    except Exception: return []
    if not s: return []
    res = []
    for t, slot, o in events(s):
        if o['typeId'] == 16:
            res.append(dict(turn=t, slot=slot, src=tag or '本体', dmg=attack_text(subobj(o, 6)), dmgv=attack_value(subobj(o, 6)),
                            cnt=o['hitCount'], iv=o['hitInterval'], mn=o['minDamage'], armor=o['int11'], hs=o['int15'], noke=noke_text(o),
                            frames='%d-%d' % (o['startFrame'], o['endFrame']), mult=mult))
        elif o['typeId'] == 19:
            ws = subobj(o, 3)
            if not ws: continue
            n1 = val(subobj(o, 4)) or 1; nmax = val(subobj(o, 5)); iv = val(subobj(o, 6))
            w2 = waz_by_idx(ws['wazFileNo'])
            if w2 is None: continue
            nm = '%s:%s' % (waz_name(ws['wazFileNo']), skill_name(w2, ws['wazSequenceNo']))
            res += hits_of(w2, ws['wazSequenceNo'], depth + 1, seen, n1, nm + ('×%d' % n1 if n1 != 1 else '') + ('(max%d,間隔%s)' % (nmax, iv) if nmax else ''))
    return res

def summarize(w, si):
    s = w['skillList'][si]
    turns = len(s.get('phasesInfo') or [])
    flen = []
    for ph in s.get('phasesInfo') or []:
        m = 0
        for u in ph['skillUnitCollection']:
            for o in u['skillInfoObjectList']:
                m = max(m, o['endFrame'] + 1)
        flen.append(m)
    hs = hits_of(w, si)
    heat = [val(o) for t, sl, o in events(s, slot=40)]
    chg = [val(subobj(o, 0)) for t, sl, o in events(s, typeId=21)]
    inv = [(o['startFrame'], o['endFrame']) for t, sl, o in events(s, slot=38) if o['int4']]
    arm = sorted({o['int4'] for t, sl, o in events(s, slot=36) if o['int4']})
    nse = sum(1 for _ in events(s, typeId=23)); nvo = sum(1 for _ in events(s, typeId=24))
    return dict(turns=turns, flen=flen, hits=hs, heat=heat, charge=chg, inv=inv, armor=arm, nse=nse, nvo=nvo)

def hits_short(hs, maxn=4):
    out = []
    agg = collections.OrderedDict()
    for h in hs:
        if h['slot'] == 42: continue  # 対弾判定は除外
        cnt = '∞' if h['cnt'] in (-1, 9999) else str(h['cnt'])
        key = (h['src'], h['dmg'], cnt, h['iv'])
        agg[key] = agg.get(key, 0) + 1
    for (src, dmg, cnt, iv), k in list(agg.items())[:maxn]:
        s = '%s×%s' % (dmg, cnt) + ('/%df' % iv if iv and cnt != '1' else '')
        if k > 1: s = '[%s]×%d' % (s, k)
        if src != '本体': s = '%s{%s}' % (s, src)
        out.append(s)
    if len(agg) > maxn: out.append('…+%d' % (len(agg) - maxn))
    return ' '.join(out) or '-'

def est_total(hs):
    tot = 0; inf = False
    for h in hs:
        if h['slot'] == 42: continue
        c = h['cnt']
        if c in (-1, 9999): inf = True; c = 1
        tot += h['dmgv'] * max(c, 0) * (h['mult'] or 1)
    return ('%d+' % tot) if inf else str(tot)

# ------------------------------------------------------------------ output
def out_rows(header, rows):
    if A.csv:
        import csv
        wr = csv.writer(sys.stdout); wr.writerow(header); wr.writerows(rows); return
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)] if rows else [len(h) for h in header]
    def fmt(r): return ' | '.join(str(x).ljust(min(wd, 60)) if i < len(r) - 1 else str(x) for i, (x, wd) in enumerate(zip(r, widths)))
    print(fmt(header)); print('-' * min(200, sum(min(w, 60) + 3 for w in widths)))
    for r in rows: print(fmt(r))

def resolve(name):
    mek = load('mek', name)
    if mek:
        wi = mek['mekBasicInfo']['wazFileSequence']
        return mek, wi, waz_by_idx(wi)
    for i, g in enumerate(WG):
        if g.get('existFlag') and g['wazaDisplayName'].lower() == name.lower():
            return None, i, waz_by_idx(i)
    w = load('waz', name)
    return None, None, w

mek, widx, waz = resolve(A.name)
if waz is None:
    sys.exit('waz not found for %s' % A.name)

spm_anims = None
if mek:
    b = mek['mekBasicInfo']
    sp = b['spmFileSequence']
    spmname = SG[sp]['spriteName'] if 0 <= sp < len(SG) and 'spriteName' in SG[sp] else None
    if spmname is None and 0 <= sp < len(SG):
        spmname = next((v for k, v in SG[sp].items() if isinstance(v, str) and v.lower().endswith('.spm')), None)
    spm = load('spm', spmname[:-4]) if spmname else None
    spm_anims = spm['animData'] if spm else None
    print('# %s 「%s」(%s) pilot=%s  waz=%s[%s] spm=%s[%s]%s  HP=%s' % (A.name, b['mekName'], b['mekNameEnglish'], b['pilotNameKanji'], widx, waz_name(widx) if widx is not None else '?',
          sp, spmname, '' if spm_anims else '(spm JSONなし)', b['baseHealth']))
else:
    print('# waz %s (WazaGroup %s)' % (A.name, widx))

def anim_name(spmseq, g, n):
    if spmseq != -1 or not spm_anims:
        return 'spm%s:%d/%d' % (spmseq, g, n)
    if 0 <= g < len(spm_anims):
        a = spm_anims[g]; nm = a['animName'].strip()
        bad = '' if n < a['numPat'] else '!pat範囲外'
        return '%s#%d%s' % (nm, n, bad)
    return 'anim?%d' % g

if A.skill is not None:
    si = A.skill; s = waz['skillList'][si]
    if not s: sys.exit('empty skill')
    print('## 技 %d 「%s」 %s  ターン数=%d' % (si, s.get('skillNameJapanese'), s.get('skillNameEnglish'), len(s['phasesInfo'])))
    SLOTN = {}
    try:
        F = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'waz_fields.json'), encoding='utf-8'))
        SLOTN = {e['slot']: e['name_ja'] for e in F['slots']}
    except Exception:
        pass
    for t, ph in enumerate(s['phasesInfo']):
        print('### ターン %d' % t)
        for u in ph['skillUnitCollection']:
            sl = u['unitQuantity']
            for o in u['skillInfoObjectList']:
                ty = o['typeId']; fr = '%3d-%3d' % (o['startFrame'], o['endFrame'])
                if ty == 13: d = anim_name(o['spmFileSequence'], o['actionGroupNumber'], o['actionNumber'])
                elif ty == 16:
                    d = '威力=%s ヒット数=%s 間隔=%s 最低=%s 装甲攻撃=%s%% HS=%s/%s 溜め反映=%s 補正(基底/技のみ/中/終)=%s/%s/%s/%s 対象=%s のけぞり[%s]' % (
                        attack_text(subobj(o, 6)), o['hitCount'], o['hitInterval'], o['minDamage'], o['int11'], o['int15'], o['int16'], o['chargeDamageRate'],
                        o['startComboCorrection'], o['internalCorrection'], o['midComboCorrection'], o['endCorrection'], o['attackTargetType'], noke_text(o))
                    he = subobj(o, 16)
                    if he: d += ' ヒットEF=%s:%d' % (waz_name(he['wazFileNo']), he['wazSequenceNo'])
                    hse = subobj(o, 28)
                    if hse: d += ' ヒットSE=' + ','.join(se_name(ints(x, 4)) for x in hse['byteDataList'])
                elif ty == 19:
                    ws = subobj(o, 3)
                    d = '発射 %s 同時=%s 最大=%s 間隔=%s' % (('%s:%s「%s」' % (waz_name(ws['wazFileNo']), ws['wazSequenceNo'], skill_name(waz_by_idx(ws['wazFileNo']) or {'skillList': []}, ws['wazSequenceNo']))) if ws else '?',
                                                       val(subobj(o, 4)), val(subobj(o, 5)), val(subobj(o, 6)))
                elif ty == 4: d = '%s:%d「%s」' % (waz_name(o['wazFileNo']), o['wazSequenceNo'], skill_name(waz_by_idx(o['wazFileNo']) or {'skillList': []}, o['wazSequenceNo']))
                elif ty == 23: d = ' / '.join(se_name(ints(x, 4)) for x in o['byteDataList'])
                elif ty == 24: d = ' / '.join(voice_name(ints(x, 3)) for x in o['byteDataList'])
                elif ty in (0, 1): d = ('%d⇒' % o['int2'] if o['int1'] or o['int2'] else '') + ('%s%d' % (['', '前+', '開始+'][o['int3']] if o['int3'] in (0, 1, 2) else '?', o['int4']))
                elif ty in (2, 3): d = '%s%d±%d' % (['', '前+', '開始+'][o['int4']] if o['int4'] in (0, 1, 2) else '?', o['int5'], o['int6'])
                elif ty == 34:
                    d = ' & '.join(term_text(b) for b in o['bsdxInfoCollectionList1']) + '  ⇒  ' + term_text(o['bsdxInfoCollectionList2'][0])
                elif 'bsdxInfoCollectionList' in o: d = term_text(o['bsdxInfoCollectionList'][0])
                elif ty == 21: d = '熱チャージ消費=%s 溜め=%s' % (val(subobj(o, 0)), val(subobj(o, 1)))
                else:
                    d = ' '.join('%s=%s' % (k, v) for k, v in o.items() if isinstance(v, (int, float)) and k not in ('offset', 'slotNum', 'typeId', 'startFrame', 'endFrame'))[:150]
                print('  [%2d %s] %s  %s' % (sl, SLOTN.get(sl, ''), fr, d))
    sys.exit(0)

if A.skills or not mek:
    rows = []
    for si, s in enumerate(waz['skillList']):
        if not s: continue
        r = summarize(waz, si)
        rows.append([si, s.get('skillNameJapanese') or '', len(r['flen']), '/'.join(map(str, r['flen'])), hits_short(r['hits']), est_total(r['hits']),
                     ','.join(map(str, r['heat'])) or '-', ','.join('%d-%d' % x for x in r['inv']) or '-', ','.join(map(str, r['armor'])) or '-', r['nse'], r['nvo']])
    out_rows(['#', '技名', 'T', 'F/ターン', '攻撃(威力×ヒット数{弾})', '威力計(推定)', '熱(waz)', '無敵', '装甲', 'SE', 'Vo'], rows)
    sys.exit(0)

rows = []
CAT = {0: '通常', 1: 'FC', 2: 'INIT'}; TYP = {0: '格', 1: '射'}
for k in sorted(mek['mekWeaponInfoMap'], key=int):
    wp = mek['mekWeaponInfoMap'][k]
    si = wp['wazSequence']
    s = waz['skillList'][si] if 0 <= si < len(waz['skillList']) else None
    if not s:
        rows.append([k, wp['weaponName'], si, '(技なし)'] + [''] * 7); continue
    r = summarize(waz, si)
    rows.append([k, wp['weaponName'], '%s%s' % (CAT.get(wp['weaponCategory'], wp['weaponCategory']), TYP.get(wp['weaponType'], wp['weaponType'])), wp['forceCrashAmount'],
                 '%d/%d' % (wp['heatMaxConsumption'], wp['heatMinConsumption']), '%d「%s」' % (si, s.get('skillNameJapanese')), '/'.join(map(str, r['flen'])),
                 hits_short(r['hits']), est_total(r['hits']), (r['hits'][0]['noke'] if r['hits'] else '-'),
                 ','.join('%d-%d' % x for x in r['inv']) or '-'])
out_rows(['#', '武装名', '種', 'Lv', '熱 初/最小', '技', 'F/ターン', '攻撃(威力×ヒット数{弾})', '威力計(推定)', 'のけぞり(地上)', '無敵'], rows)
