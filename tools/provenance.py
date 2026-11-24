#!/usr/bin/env python3
"""provenance.py - per-weapon record of HOW each value of a ported mech was obtained (調査記録 15).

Categories (one per Report entry kind; see notes/15_provenance.md for the reasoning):
  R 変換・確定規則   : BFE value converted by a rule backed by the exe (and/or a vanilla example)
  E 変換・推定係数   : BFE value converted by a rule whose scale / meaning is estimated (coefficients to tune in game)
  V バニラ書式の流用 : BFE behaviour expressed with an idiom copied from a vanilla DiveX skill (values still from BFE)
  T テンプレ値のまま : no BFE counterpart -> the value of 甲's template skill was kept
  X 除外・未対応     : BFE data intentionally dropped / ignored / not representable
  M 手入力（BFE 外） : value chosen by hand (user request or design decision), not derived from BFE
Nothing here changes build output; it only writes reports.
"""
import collections, json, os, re

try:
    _SLOT = {x['slot']: x['name_ja'] for x in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'waz_fields.json'),
                                                             encoding='utf-8'))['slots']}
except Exception:
    _SLOT = {}


def _slotname(m):
    return re.sub(r'slot (\d+)', lambda g: 'slot %s（%s）' % (g.group(1), _SLOT.get(int(g.group(1)), '?')) if int(g.group(1)) in _SLOT
                  else g.group(0), m)

CAT_NAME = {'R': '変換・確定規則', 'E': '変換・推定係数', 'V': 'バニラ書式の流用', 'T': 'テンプレ値のまま',
            'X': '除外・未対応', 'M': '手入力（BFE外）'}
KIND_CAT = {'AIR': 'R', 'MOVE': 'R', 'VERT': 'R', 'LANDTEST': 'R', 'VRATE': 'R', 'LAUNCH': 'E', 'BLEND': 'R', 'DIRECTION': 'R', 'INERTIA': 'R', 'SPEEDCUT': 'R', 'RESTRAMP': 'R', 'FREEFALL': 'R', 'POSTAPEX': 'R', 'LOOP': 'R', 'LOOPPOS': 'R', 'SWEEP': 'R', 'STOP': 'R', 'HITDELAY': 'R', 'SLIP': 'R', 'HITCANCEL': 'R', 'HITLOCK': 'R', 'HEAT': 'R',
            'HIT': 'E', 'NOKE': 'E', 'HEIGHT': 'E', 'COMBO': 'E', 'MINDMG': 'E', 'SELFDECAY': 'R', 'COMBOCLS': 'E', 'ROLEMIN': 'E', 'NOKEFLOAT': 'E', 'NOKERANDDIR': 'E', 'STICKHEIGHT': 'E', 'MECHDIST': 'V', 'NOKEDIRZERO': 'R', 'NOKEPULL': 'R', 'CHIPTARGET': 'R', 'STICKALPHADIR': 'R', 'STICKALPHADIR2': 'R', 'MECHSPR': 'R', 'EFFTARGET': 'E', 'AIMONCE': 'R', 'BLINK': 'E', 'STICKFLOOR': 'E', 'REPDECAY': 'R', 'FIREIV': 'R', 'BFALL': 'R',
            'STICK': 'V', 'MISSILEFX': 'V', 'NORECT': 'R', 'DISTOUT': 'R', 'STICKZ': 'E', 'MULTILAUNCH': 'R', 'NOKEVEC': 'R', 'DIR16RESET': 'R', 'STICKFOLLOW': 'E', 'STICKHOLD': 'E', 'DIVETOUCH': 'V', 'FIRELOCK': 'R', 'NOKEDOWNHIT2': 'R', 'NOKECHAIN': 'E', 'HITSTOPCHAIN': 'E', 'DIVEHOLD': 'E', 'BHOLDANY': 'R', 'STICKTARGET': 'R', 'POSCORR': 'R', 'FOLLOWCUT': 'E', 'TIPTOUCH': 'R', 'TIPDETACH': 'E', 'FLATCHIP': 'R', 'SLAMKEEP': 'E', 'STICKALPHA0': 'R', 'RANDLOW': 'R', 'TWINMUZZLE': 'V', 'FCPHASE': 'E', 'FCSTOP': 'E', 'LANDHOLDV': 'R', 'CHIPAIR': 'R', 'LOCKPARENT': 'R', 'CHIPMOVE': 'R', 'SPAWNYPCT': 'E', 'HOMING_OFFSET': 'V', 'HOMING_EITHER': 'R', 'BHOLD': 'R', 'BDECEL': 'R', 'NOKEDIR': 'V', 'NOKEPARENT': 'R', 'STICKALPHA': 'E', 'BDIVE': 'R', 'LOCKTARGET': 'E', 'RISE': 'V', 'FIREDIR': 'V', 'SPIN': 'R', 'LANDHOLD': 'V', 'LOB': 'E', 'HITSCALE': 'R', 'TOUCH': 'V', 'BTOUCH': 'V', 'BVERT': 'R', 'BSPEED': 'R', 'ANGLESIGN': 'R', 'SPAWNTYPE': 'R', 'HITIV': 'R', 'NODMG': 'R', 'PIERCE': 'R', 'LINEZOOM': 'R', 'ZOOMTYPE0': 'R', 'SEVOICE': 'R', 'LANDZOOM': 'R', 'TOUCHCARRY': 'R', 'SDKEEP': 'R', 'NOKESAME': 'R', 'NOKEDOWN': 'R', 'NOKEDOWNHIT': 'R', 'LINE': 'V', 'LASER': 'V',
            'TEMPLATE': 'T',
            'DROPPED': 'X', 'IGNORED': 'X', 'NOFIRE': 'X', 'UNKNOWN': 'X',
            'BASIC': 'M', 'BASIC_ANIM': 'M', 'MANUAL': 'M', 'ARMOR': 'M'}
INFO = {'BULLET', 'EFFECT', 'LINEMAP', 'SKILL', 'SE_NEW', 'SPM', 'EFT_SPM', 'MATERIAL_SELFTEST', 'SUMMARY'}


def category(kind, msg):
    if kind == 'APPROX':
        if 'go_counter' in msg or 'anim_type' in msg:
            return 'E'
        if 'idiom' in msg or 'ボディブロー' in msg or 'fallback projectile' in msg:
            return 'V'
        if 'template' in msg:
            return 'T'
        return 'E'
    return KIND_CAT.get(kind)


def summarize(entries):
    """entries: [(kind, msg)] -> {cat: Counter(msg-with-kind)}"""
    out = collections.defaultdict(collections.Counter)
    for k, m in entries:
        if k in INFO:
            continue
        c = category(k, m) or 'R'
        out[c]['[%s] %s' % (k, _slotname(m))] += 1
    return out


def write(path, mech, rows, header_lines=()):
    """rows: [dict(no, name, bfe, kou, own=[(k,m)], bullets={ti: [(k,m)]}, extra=[(cat, text)])]"""
    L = ['# %s — 値の出どころ（自動生成・ビルドごとに更新）' % mech, '',
         '凡例: ' + ' / '.join('**%s** %s' % (c, n) for c, n in CAT_NAME.items()) + '。説明は notes/15_provenance.md。', '']
    L += list(header_lines)
    L += ['', '## 一覧', '', '| # | 武装 | BFE | 甲テンプレ | R | E | V | T | X | M |', '|---|---|---|---|---|---|---|---|---|---|']
    det = []
    for r in rows:
        own = summarize(r['own'])
        bul = summarize([e for es in r.get('bullets', {}).values() for e in es])
        for c, t in r.get('extra', ()):
            own[c][t] += 1
        cnt = {c: sum(own[c].values()) + sum(bul[c].values()) for c in CAT_NAME}
        L.append('| %s | %s | %s | %s | %s |' % (r['no'], r['name'], '-' if r['bfe'] is None else r['bfe'], r['kou'],
                                                 ' | '.join(str(cnt[c] or '') for c in CAT_NAME)))
        det += ['', '### %s %s' % (r['no'], r['name'])]
        for title, S in (('技本体', own), ('撃つ弾（共通 waz、他の武装と共有のことあり）', bul)):
            if not any(S.values()):
                continue
            det.append('* %s' % title)
            for c in CAT_NAME:
                for m, n in sorted(S[c].items()):
                    det.append('  * %s %s%s' % (c, m, '' if n == 1 else ' ×%d' % n))
    L += ['', '## 武装ごとの詳細'] + det
    open(path, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
