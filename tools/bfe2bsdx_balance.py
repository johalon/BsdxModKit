#!/usr/bin/env python3
"""TOORU balanced variant (modified/Update3.pac): damage parameters only, no behaviour change.

User 2026-11-04: the build outputs both the faithful pack (Update3.pac) and a balanced one (modified/Update3.pac).
Analysis: 調査記録 B1 (最低値 by tag), B2/B3 (COMBOCLS 甲 vs 透), B4_role_preserving_20261104.md (the rule used here).

Rule (B4 §7・§8, user 11/04 / 11/05 「イニシャライザ前は原作より少し弱く、イニシャライザ込みで原作の 1.5〜2 倍」):
  * The converter (tools/bfe2bsdx_waz.py ROLEMIN) computes, for every converted vs-mech hit, the faithful 最低値 with
    HG factor ROLE_G 2 and the balanced one with ROLE_G_MOD (1.25 since 11/05, was 0.8), both never below BFE 最低威力 x3/8. The balanced value
    rides on the hit as '_bal' {'minDamage': ...}.
  * modified/: that 最低値, and 技終了時 (endCorrection) = round(faithful x END_MUL_MOD) (1.0 since 11/05 = unchanged, was 1.5) on the same hits.
  * Model result (B4 §8, FC/イニ rules of the wiki, HG measured by the user: +0.2 / +0.4 per loop): イニ前 0.96 /
    イニ込み 1.95 of the original (11/04 rule 0.8 / x1.5 under the old HG guess: 0.97 / 1.92; under the measured HG 0.86 / 1.57).
  * Then per-weapon adjustments (user 11/05: 「広範囲の変換は最低限にして、個々の武装ごとに、ユーザー体験をどうしたいかの
    意図とともに調整」): OVERRIDES (by the BFE weapon name of the technique that owns the hit) and FC_MIN (every 必殺 / FC).
    min only raises: 最低値 = max(the rule's value, round(表示威力 x ratio)). power (user 11/05): 威力 x mul on every hit of
    the weapon, the 最低値 keeps its ratio to the 表示威力 (then min / FC_MIN apply to the new 表示威力).
The build pops '_bal' before writing the faithful files (pop_bal) and applies it to copies in its section I2 (apply).
Vanilla skills never carry '_bal' (only converted hits do) and are never modified.
"""
import copy
from bfe2bsdx_waz import ROLE_G_MOD
import modified_tweaks as MT   # 2026-11-10 (user): 改善版の調整は tools/modified_tweaks.py に一覧（on / params）。ここはそれを読むだけ。

# -- per-weapon adjustments (user 11/05). Key = weapon name (mek weaponName = BFE name). min = 最低値 / 表示威力 at least,
# min_set = 最低値 / 表示威力 exactly (may lower; user 11/06), power = 威力 multiplier. Built from modified_tweaks (GENOCIDE_POWER).
# 2026-11-10 COMBOV3 (user): エア・タックル min_set 0.7 / ダブルセイバー min 0.66 / 青龍刀 min 0.5 / ドリル min 1.0 は撤廃。
# 格闘・射撃の通常技の最低値は bfe2bsdx_combo_v3（ドリル 100 %・青龍刀 30 %・ダブルセイバー 60 % は MOD_MIN_SET）。
OVERRIDES = {}
if MT.on('GENOCIDE_POWER'):
    OVERRIDES[MT.p('GENOCIDE_POWER', 'weapon')] = dict(power=MT.p('GENOCIDE_POWER', 'mul'), why=MT._BY['GENOCIDE_POWER']['why'])
if MT.on('GENOCIDE_MIN'):   # 作者 2026-11-22 (GENOCIDE_MIN, 調査記録 90 §8): 最低値 = 表示威力 x ratio ちょうど（役割式・FC_MIN の 100% から下げる）
    OVERRIDES.setdefault(MT.p('GENOCIDE_MIN', 'weapon'), {})['min_set'] = MT.p('GENOCIDE_MIN', 'ratio')
    OVERRIDES[MT.p('GENOCIDE_MIN', 'weapon')].setdefault('why', MT._BY['GENOCIDE_MIN']['why'])
RAPID = MT.p('RAPID_LATE', 'weapons', {})   # user 2026-11-14 (RAPID_LATE): weapon -> (power mul, 最低値 / 表示威力, 技のみ補正)
for _w, (_pm, _r, _ic) in RAPID.items():
    if _pm != 1:
        OVERRIDES.setdefault(_w, {})['power'] = OVERRIDES.get(_w, {}).get('power', 1) * _pm
        OVERRIDES[_w].setdefault('why', MT._BY['RAPID_LATE']['why'])
MKE = MT.p('MINEKNUCKLE_EARLY', 'weapons', {})   # user 2026-11-14 (MINEKNUCKLE_EARLY, 調査記録 54): weapon -> (power mul, 最低値 / 表示威力)
assert not set(MKE) & set(RAPID), 'MINEKNUCKLE_EARLY / RAPID_LATE overlap'
for _w, (_pm, _r) in MKE.items():
    if _pm != 1:
        OVERRIDES.setdefault(_w, {})['power'] = OVERRIDES.get(_w, {}).get('power', 1) * _pm
        OVERRIDES[_w].setdefault('why', MT._BY['MINEKNUCKLE_EARLY']['why'])
SATP = MT.p('SAT_POWER', 'weapons', {})   # user 2026-11-16 (SAT_POWER, 調査記録 69): weapon -> (power mul, 最低値 / 表示威力), MKE と同じ形
assert not set(SATP) & (set(RAPID) | set(MKE)), 'SAT_POWER / RAPID_LATE / MINEKNUCKLE_EARLY overlap'
for _w, (_pm, _r) in SATP.items():
    if _pm != 1:
        OVERRIDES.setdefault(_w, {})['power'] = OVERRIDES.get(_w, {}).get('power', 1) * _pm
        OVERRIDES[_w].setdefault('why', MT._BY['SAT_POWER']['why'])
SHOTP = MT.p('SHOT_POWER', 'weapons', {})   # 作者 2026-11-22 (SHOT_POWER, 調査記録 90 §6): weapon -> 威力の倍率 か (倍率, 最低値 / 表示威力)（調査記録 95）
SHOTP = {_w: (_v if isinstance(_v, tuple) else (_v, None)) for _w, _v in SHOTP.items()}
assert not set(SHOTP) & (set(RAPID) | set(MKE) | set(SATP)), 'SHOT_POWER / RAPID_LATE / MINEKNUCKLE_EARLY / SAT_POWER overlap'
for _w, (_pm, _r) in SHOTP.items():
    if _pm != 1:
        OVERRIDES.setdefault(_w, {})['power'] = OVERRIDES.get(_w, {}).get('power', 1) * _pm
        OVERRIDES[_w].setdefault('why', MT._BY['SHOT_POWER']['why'])
FINISH = MT.p('FINISHER_POWER', 'weapons', {})   # user 2026-11-15 (FINISHER_POWER): weapon -> dict(disp=最終の表示威力, min=最低値 / 表示威力)
DRILL = MT.p('DRILL_POWER', 'weapons', {})       # user 2026-11-15 (DRILL_POWER): weapon -> 威力・最低値の倍率（最終値に、切り捨て）
assert not set(FINISH) & set(DRILL) and not (set(FINISH) | set(DRILL)) & (set(RAPID) | set(MKE) | set(OVERRIDES)), 'FINISHER_POWER / DRILL_POWER overlap'
HITCAP = MT.p('HITCAP', 'weapons', {})     # user 2026-11-16 (HITCAP, 調査記録 64): weapon -> 対メカの当たりの最大ヒット数 (Hit hitCount)
assert all(isinstance(v, int) and v >= 1 for v in HITCAP.values()), 'HITCAP: 1 以上の整数'
HITCAP_LOG = {}              # weapon -> [(hitCount before, after)] (filled by apply)
EVERYF = MT.p('SPREAD_EVERYF', 'weapons', {})   # 作者 2026-11-22 (SPREAD_EVERYF, 調査記録 93): weapon -> dict(file, turns, interval, power, min, ic)
EVERYF_LOG = {}              # weapon -> [(turn, hitInterval before, after, 威力 before, after, 最低 before, after, 技のみ before, after)]
BOMBBIT = MT.p('BOMBBIT_BODY', 'weapons', {})   # 作者 2026-11-22 (BOMBBIT_BODY, 調査記録 102): weapon -> dict(file, skill, turns, power=内部値, min=最低値 / 表示威力)
assert all(isinstance(v.get('power'), int) and v['power'] > 0 for v in BOMBBIT.values()), 'BOMBBIT_BODY: power は正の整数'
BOMBBIT_LOG = {}             # weapon -> [(turn, 表示 before, after, 最低 before, after)]
GBMIN = MT.p('GBIT_BULLET_MIN', 'weapons', {})   # 作者 2026-11-22 (GBIT_BULLET_MIN, 調査記録 104): weapon -> dict(file, skill=弾の名前, min=最低値 / 表示威力)
GBMIN_LOG = {}               # weapon -> [(表示, 最低 before, after)]
FC_SHAPE = MT.p('FC_SHAPE', 'weapons', {})   # user 2026-11-16 夜 (FC_SHAPE, 調査記録 67): FC weapon -> dict(disp=表示威力, file=?, min=最低値の比?, ic=技のみ補正?)
assert all(isinstance(v.get('disp'), int) and int(v['disp'] * 2 // 3 * 1.5) == v['disp'] for v in FC_SHAPE.values()), 'FC_SHAPE: disp は 威力 x1.5 で出せる整数'
FC_SHAPE_LOG = {}            # weapon -> number of hits rewritten (filled by apply)
FC_MIN = MT.p('FC_MIN', 'ratio', 0)          # 必殺 / FC (mek weaponCategory 1): 最低値 >= 表示威力 x0.8 (user 11/05); off -> 0 (no raise)
FC_MIN_EXACT = MT.p('FC_MIN', 'exact', False)   # 作者 2026-11-22 (調査記録 97): True -> 最低値 = 表示威力 x 比 ちょうど（上げ下げとも）
FC_MIN_EXCEPT = MT.p('FC_MIN', 'except_', {})    # weapon -> 比、または {file: 比}
FC_WHY = MT._BY['FC_MIN']['why']
FC_POWER = MT.p('FC_POWER', 'mul', {})       # user 2026-11-12 (FC_POWER): FC weapon name -> 威力 x mul on every hit (bullets too); 装甲攻撃力は打ち消して維持
assert all(v >= 1 for v in FC_POWER.values()), 'FC_POWER: 弱体化しない（ユーザー 11/12）'
END_SET = {MT.p('STUNROD_DOT', 'weapon'): MT.p('STUNROD_DOT', 'end_corr')} if MT.p('STUNROD_DOT', 'end_corr') is not None else {}
# user 2026-11-19 (STUNROD_DOT, 調査記録 84): weapon -> 技終了時（endCorrection）を指定（初段補正はそのまま）。継続ダメージの分、本体の補正を 0 に
END_SET_LOG = {}
ROLEMIN_ON = MT.on('ROLEMIN')                # off: COMBOV3 対象外のヒットの 最低値 / 技終了時 は 3b のまま
END_MUL_MOD = MT.p('ROLEMIN', 'end_mul', 1.0)   # 11/05 (調査記録 B4 §8): x1.5 -> x1.0 with ROLE_G_MOD 1.25
COMBOV3_MOD_ON = MT.on('COMBOV3_MOD')        # off: 格闘・射撃の通常技の 初段 / 技終了時 / 最低値 は 3b のまま
ARMOR_ATK_MOD = MT.p('ARMORATK_MOD', 'mul', 1.0)   # user 2026-11-09 (ARMORATK_MOD): 装甲攻撃力 (Hit int11, %) x1.1 on every converted hit
#   (1.25 は少し強く 1.0 は弱かった -> 1.1, user 11/09 夜). 3b は甲テンプレの等倍 = ARMORATK1/ARMORSELF1, 調査記録 35.
#   四捨五入 (10 -> 11, 25 -> 28, 50 -> 55, 100 -> 110); 0 / 負の特殊値はそのまま.
NONFC_POWER_MOD = MT.p('NONFC08', 'mul', 1.0)   # user 2026-11-10 (NONFC08): 威力 x0.8 on every hit of a non-FC weapon (mek weaponCategory != 1).
#   最低値 は表示威力との比を保つ (OVERRIDES power と同じ扱い)。装甲への攻撃力は維持: int11 = 3b x ARMOR_ATK_MOD / NONFC_POWER_MOD
#   (装甲ゲージ減少 = 最終ダメージ x int11 / 100, exe 0x61f0c8 -> 威力 x0.8 を int11 / 0.8 で打ち消す。100 -> 138, 10 -> 14)。
SELF_ARMOR_ON = MT.on('SELFARMOR15')
SELF_ARMOR_MOD = MT.p('SELFARMOR15', 'mul', 1)   # user 2026-11-10 (SELFARMOR15): 自機の装甲 (Tooru.waz slot 36 CEventVal int4 = 段階, 1 段階 = 装甲 100)
#   x1.5 切り捨て (1 -> 1, 2 -> 3, 3 -> 4), modified only. 3b は等倍 (ARMORSELF1)。SELF_ARMOR_SET は技全体の段階をその値に。
SELF_ARMOR_SET = MT.p('SELFARMOR15', 'set', {})   # skill name (= mek weaponName) -> 段階 (user 11/10)
EARLYHEAT = MT.p('EARLYHEAT', 'weapons', {})   # user 2026-11-14 (EARLYHEAT, 調査記録 53): weapon -> 早期廃熱 bit (8 / 16), modified only
assert all(v in (8, 16) for v in EARLYHEAT.values()), 'EARLYHEAT: 8 か 16'
EARLYHEAT_TURNS = MT.p('EARLYHEAT', 'turns', {})   # 11/21 (調査記録 88 §5): weapon -> only the hits in these turns of its skill (フォトンブラスター: blast T1/T2)
assert set(EARLYHEAT_TURNS) <= set(EARLYHEAT), 'EARLYHEAT turns: weapon not in weapons'
EARLYHEAT_LOG = {}           # weapon -> number of hits given the bit (filled by apply)
BURN = MT.p('BURN_ADD', 'weapons', {})   # 作者 2026-11-22 (BURN_ADD, 調査記録 90 §1): weapon -> dict(file=?, frames=燃焼の F)。Hit int2 0x04 + int22
assert all(isinstance(v.get('frames'), int) and v['frames'] > 0 for v in BURN.values()), 'BURN_ADD: frames は正の整数'
BURN_LOG = {}                # weapon -> number of hits given 燃焼 (filled by apply)
SELF_WAZ = 'Tooru.waz'
ARMOR_LOG = []               # (skill index, skill name, before, after) filled by apply(); table_md lists it
KEYS = ('minDamage', 'endCorrection', 'paramList', 'int11', 'startComboCorrection', 'internalCorrection', 'int2', 'hitCount', 'int22', 'hitInterval')   # hitInterval: SPREAD_EVERYF   # int22: BURN_ADD（燃焼の F）   # hitCount: HITCAP   # int2: EARLYHEAT (Hit フラグ)   # internalCorrection: RAPID_LATE   # paramList: OVERRIDES power (slot 6 威力 of a hit only); int11: ARMOR_ATK_MOD; startComboCorrection: COMBOV3


def pop_bal(objs):
    """objs: {file name: json}. Removes every '_bal' in place; returns [(file name, path tuple, bal dict)].
    A hit object reachable by two paths is listed under both."""
    found, hit_objs = [], []

    def walk(o, name, path):
        if isinstance(o, dict):
            if '_bal' in o:
                found.append((name, path, o['_bal'])); hit_objs.append(o)
            for k, v in o.items():
                if k != '_bal':
                    walk(v, name, path + (k,))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, name, path + (i,))
    for n, o in objs.items():
        walk(o, n, ())
    for o in hit_objs:
        o.pop('_bal', None)
    return found


def _get(o, path):
    for k in path:
        o = o[k]
    return o


def _power(o):
    p = 0
    for u in o.get('ceventHitUnitList') or []:
        if u.get('unitSlotNum') == 6:
            p = sum(u['data']['bsdxInfoCollectionList'][0]['paramList'])
    return p


def _set_power(src, dst, mul):
    """dst's slot 6 威力 = src's x mul (absolute, so a hit reached by two paths is not scaled twice)."""
    for us, ud in zip(src.get('ceventHitUnitList') or [], dst.get('ceventHitUnitList') or []):
        if us.get('unitSlotNum') == 6:
            for bs, bd in zip(us['data']['bsdxInfoCollectionList'], ud['data']['bsdxInfoCollectionList']):
                bd['paramList'] = [max(1, round(x * mul)) for x in bs['paramList']]


def fc_min_ratio(tech, n):
    """FC_MIN の比（FC_MIN_EXCEPT を見る）。{file: 比} で n が無ければ ratio。"""
    r = FC_MIN_EXCEPT.get(tech, FC_MIN)
    if isinstance(r, dict):
        r = r.get(n, FC_MIN)
    return r


def target_min(bal, disp, cat, n=None):
    """The modified/ 最低値 of one hit: the rule's value, raised by OVERRIDES / FC_MIN. Returns (value, reason).
    FC_MIN_EXACT (作者 11/22): FC の最低値 = 表示威力 x 比 ちょうど（役割式の値より下げてもよい）。"""
    m, why = bal['minDamage'], ''
    tech = bal.get('tech')
    rs = []
    if cat.get(tech) == 1:
        r_ = fc_min_ratio(tech, n)
        if FC_MIN_EXACT and r_:
            m, why = max(1, round(disp * r_)), 'FC_MIN %d%%' % round(r_ * 100)
        else:
            rs.append((r_, 'FC_MIN'))
    if 'min' in OVERRIDES.get(tech, {}):
        rs.append((OVERRIDES[tech]['min'], 'OVERRIDES'))
    for ratio, src_ in rs:
        v = round(disp * ratio)
        if v > m:
            m, why = v, src_
    if 'min_set' in OVERRIDES.get(tech, {}):
        m, why = max(1, round(disp * OVERRIDES[tech]['min_set'])), 'OVERRIDES set'
    return m, why


def apply(objs, recs, cat=None):
    """objs: {file name: faithful json (after pop_bal)}; recs: pop_bal's list; cat: {weapon name: mek weaponCategory}.
    Returns ({file name: new json}, rows). Inputs are not modified.
    rows: [(file, skill index, skill name, 表示威力, min faithful, min new, end faithful, end new, owner weapon, reason)]."""
    cat = cat or {}
    unknown = sorted(set(OVERRIDES) - set(cat)) if cat else []
    assert not unknown, 'OVERRIDES: unknown weapon name(s) %s' % unknown
    bad_fc = sorted(k for k in FC_POWER if cat.get(k) != 1) if cat else []
    assert not bad_fc, 'FC_POWER: not an FC weapon name %s' % bad_fc
    bad_eh = sorted(set(EARLYHEAT) - set(cat)) if cat else []
    assert not bad_eh, 'EARLYHEAT: unknown weapon name(s) %s' % bad_eh
    EARLYHEAT_LOG.clear()
    BURN_LOG.clear()
    bad_bn = sorted(set(BURN) - set(cat)) if cat else []
    assert not bad_bn, 'BURN_ADD: unknown weapon name(s) %s' % bad_bn
    HITCAP_LOG.clear()
    EVERYF_LOG.clear()
    BOMBBIT_LOG.clear()
    GBMIN_LOG.clear()
    assert not cat or not set(GBMIN) - set(cat), 'GBIT_BULLET_MIN: unknown weapon name(s) %s' % (set(GBMIN) - set(cat))
    bad_bb = sorted(set(BOMBBIT) - set(cat)) if cat else []
    assert not bad_bb, 'BOMBBIT_BODY: unknown weapon name(s) %s' % bad_bb
    bad_ef = sorted(set(EVERYF) - set(cat)) if cat else []
    assert not bad_ef, 'SPREAD_EVERYF: unknown weapon name(s) %s' % bad_ef
    END_SET_LOG.clear()
    FC_SHAPE_LOG.clear()
    bad_fs = sorted(k for k in FC_SHAPE if cat.get(k) != 1) if cat else []
    assert not bad_fs, 'FC_SHAPE: not an FC weapon name %s' % bad_fs
    bad_fm = sorted(k for k in FC_MIN_EXCEPT if cat.get(k) != 1) if cat else []
    assert not bad_fm, 'FC_MIN except: not an FC weapon name %s' % bad_fm
    bad_hc = sorted(set(HITCAP) - set(cat)) if cat else []
    assert not bad_hc, 'HITCAP: unknown weapon name(s) %s' % bad_hc
    new = {n: copy.deepcopy(o) for n, o in objs.items() if any(r[0] == n for r in recs)}
    rows, done = [], set()
    for n, path, bal in recs:
        src, dst = _get(objs[n], path), _get(new[n], path)
        disp = int(_power(src) * 1.5)
        v3_on = bool(bal.get('v3')) and COMBOV3_MOD_ON
        if bal.get('v3') and not v3_on:
            bal = {k: v for k, v in bal.items() if k not in ('v3', 'endCorrection', 'startComboCorrection', 'min_ratio')}
            bal['minDamage'] = src['minDamage']          # COMBOV3_MOD off: 3b の値（下の FC_MIN / OVERRIDES はかかる）
        elif not bal.get('v3') and not ROLEMIN_ON:
            bal = dict(bal, minDamage=src['minDamage'])   # ROLEMIN off: 3b の最低値
        end_new = bal['endCorrection'] if 'endCorrection' in bal else round(src['endCorrection'] * END_MUL_MOD)
        st_new = bal.get('startComboCorrection', src.get('startComboCorrection'))
        mul = OVERRIDES.get(bal.get('tech'), {}).get('power')
        nonfc = cat.get(bal.get('tech')) != 1
        if nonfc:
            mul = (mul or 1) * NONFC_POWER_MOD
        fc_mul = 1 if nonfc else FC_POWER.get(bal.get('tech'), 1)
        fs_ = None if nonfc or src.get('attackTargetType') != 1 else FC_SHAPE.get(bal.get('tech'))
        if fs_ and fs_.get('file', n) != n:
            fs_ = None
        if fs_:
            # FC_SHAPE (user 11/16 夜, 調査記録 67): FC_POWER の代わりに表示威力を disp ちょうどに（src からの絶対倍率）
            p_src, p_tgt = _power(src), fs_['disp'] * 2 // 3
            assert p_src > 0 and mul is None, 'FC_SHAPE: %s 威力 %s / 他の倍率 %s' % (bal.get('tech'), p_src, mul)
            fc_mul = p_tgt / p_src
            assert fc_mul >= 1, 'FC_SHAPE: 弱体化しない（%s %d -> %d）' % (bal.get('tech'), p_src, p_tgt)
        if fc_mul != 1:
            mul = (mul or 1) * fc_mul
        if mul:
            _set_power(src, dst, mul)
            disp_new = int(_power(dst) * 1.5)
            bal = dict(bal, minDamage=round(bal['minDamage'] * disp_new / disp) if disp else bal['minDamage'])
            disp = disp_new
        if bal.get('v3'):
            # COMBOV3 (user 11/10): 最低値 = the modified 表示威力 (after x0.8) x the technique's ratio; replaces ROLEMIN /
            # OVERRIDES min for 格闘・射撃の通常技 (they are non-FC, so FC_MIN does not apply)
            m, why = max(1, round(disp * bal['min_ratio'])), 'COMBOV3 %s %d%%' % (bal['v3'], round(bal['min_ratio'] * 100))
            if bal.get('tech') in RAPID:
                # RAPID_LATE (user 11/14): 連射系の最低値の比と技のみ補正（同じ技の全弾で共有）を個別に
                _pm, _r, _ic = RAPID[bal['tech']]
                m, why = max(1, round(disp * _r)), 'RAPID_LATE %d%% ic %d' % (round(_r * 100), _ic)
                if 'internalCorrection' in dst:
                    dst['internalCorrection'] = _ic
            if bal.get('tech') in MKE:
                # MINEKNUCKLE_EARLY (user 11/14, 調査記録 54): 威力半分に合わせて最低値の比を上げ、後半の値を今と同じに
                _r = MKE[bal['tech']][1]
                m, why = max(1, round(disp * _r)), 'MINEKNUCKLE_EARLY %d%%' % round(_r * 100)
            if bal.get('tech') in SATP:
                # SAT_POWER (user 11/16, 調査記録 69): SAT_RIDE で 20 ヒット当たり切るぶん 1 本 約 170 に
                _r = SATP[bal['tech']][1]
                m, why = max(1, round(disp * _r)), 'SAT_POWER %d%%' % round(_r * 100)
            if bal.get('tech') in SHOTP and SHOTP[bal['tech']][1] is not None:
                # SHOT_POWER min (作者 11/22, 調査記録 95): 鷹落としの最低補正率を 50% に（威力 60% の上に重ねる）
                _r = SHOTP[bal['tech']][1]
                m, why = max(1, round(disp * _r)), 'SHOT_POWER %d%%' % round(_r * 100)
        else:
            m, why = target_min(bal, disp, cat, n)
        if fs_:
            assert _power(dst) == fs_['disp'] * 2 // 3 and disp == fs_['disp'], ('FC_SHAPE', bal.get('tech'), _power(dst), disp)
            why = (why + '+' if why else '') + 'FC_SHAPE 表示 %d' % disp
            if 'min' in fs_:
                m = max(1, round(disp * fs_['min']))
                why += ' 最低 %d%%' % round(fs_['min'] * 100)
            if 'ic' in fs_:
                assert 'internalCorrection' in dst, 'FC_SHAPE: %s has no internalCorrection' % bal.get('tech')
                dst['internalCorrection'] = fs_['ic']
                why += ' 技のみ %d' % fs_['ic']
            if id(src) not in done:
                FC_SHAPE_LOG[bal['tech']] = FC_SHAPE_LOG.get(bal['tech'], 0) + 1
        tech_ = bal.get('tech')
        if tech_ in FINISH or tech_ in DRILL:
            # FINISHER_POWER / DRILL_POWER (user 11/15): 最終値（NONFC08 などの倍率の後）で指定。威力は src からの絶対倍率で書く
            # （二つの経路で届くヒットを二重に掛けない）。装甲攻撃力は下の nonfc の打ち消し（p0 / p1）で維持。
            assert v3_on and nonfc, 'FINISHER_POWER / DRILL_POWER: %s is not a COMBOV3 non-FC hit' % tech_
            pw_ = [x for u in dst['ceventHitUnitList'] if u.get('unitSlotNum') == 6 for b in u['data']['bsdxInfoCollectionList'] for x in b['paramList']]
            assert len(pw_) == 1, 'FINISHER_POWER / DRILL_POWER: %s 威力 %s' % (tech_, pw_)
            p_src = _power(src)
            if tech_ in FINISH:
                fp_ = FINISH[tech_]
                p_tgt = -(-fp_['disp'] * 2 // 3)   # 切り上げ: 表示 = 威力 x1.5 の切り捨てなので 400 は 267（400.5 -> 400）。割り切れる値（330・420）は今までと同じ
                assert int(p_tgt * 1.5) == fp_['disp'], 'FINISHER_POWER: 表示威力 %d は 威力 x1.5 で出せない' % fp_['disp']
                r_min = fp_.get('min', bal['min_ratio'])
            else:
                p_tgt = int(_power(dst) * DRILL[tech_])
            mul = p_tgt / p_src
            _set_power(src, dst, mul)
            assert _power(dst) == p_tgt, (tech_, _power(dst), p_tgt)
            disp = int(p_tgt * 1.5)
            if tech_ in FINISH:
                m, why = max(1, round(disp * r_min)), 'FINISHER_POWER 表示 %d 最低 %d%%' % (disp, round(r_min * 100))
            else:
                m, why = int(m * DRILL[tech_]), 'DRILL_POWER x%g' % DRILL[tech_]
        bb_ = BOMBBIT.get(tech_)
        if (bb_ and bb_['file'] == n and src.get('attackTargetType') == 1 and src.get('slotNum', 41) == 41
                and 'phasesInfo' in path and path[list(path).index('phasesInfo') + 1] in bb_['turns']
                and objs[n]['skillList'][path[1]].get('skillNameJapanese') == bb_['skill']):
            # BOMBBIT_BODY (作者 11/22, 調査記録 102): ボミングビットの本体の当たり（指定ターンの対メカ）を 威力 power・最低値 表示 x min に。
            # 威力は src からの絶対倍率で書く（二つの経路で届くヒットを二重に掛けない）。装甲攻撃力は下の nonfc の打ち消し（p0 / p1）で維持
            assert nonfc, 'BOMBBIT_BODY: %s is an FC' % tech_
            t_ = path[list(path).index('phasesInfo') + 1]
            p_src = _power(src)
            pw_ = [x for u in dst['ceventHitUnitList'] if u.get('unitSlotNum') == 6 for b in u['data']['bsdxInfoCollectionList'] for x in b['paramList']]
            assert p_src > 0 and len(pw_) == 1, 'BOMBBIT_BODY: %s turn %d 威力 %s' % (tech_, t_, pw_)
            d0, m0 = disp, m
            mul = bb_['power'] / p_src
            _set_power(src, dst, mul)
            assert _power(dst) == bb_['power'], (tech_, _power(dst), bb_['power'])
            disp = int(bb_['power'] * 1.5)
            m, why = max(1, round(disp * bb_['min'])), 'BOMBBIT_BODY 表示 %d 最低 %d%%' % (disp, round(bb_['min'] * 100))
            if id(src) not in done:
                BOMBBIT_LOG.setdefault(tech_, []).append((t_, d0, disp, m0, m))
        gm_ = GBMIN.get(tech_)
        if (gm_ and gm_['file'] == n and src.get('attackTargetType') == 1 and src.get('slotNum', 41) == 41
                and len(path) > 1 and path[0] == 'skillList' and objs[n]['skillList'][path[1]].get('skillNameJapanese') == gm_['skill']):
            # GBIT_BULLET_MIN (作者 11/22, 調査記録 104): ガトリングビットの弾だけ最低値の比を min に（威力・補正はそのまま）
            m0 = m
            m, why = max(1, round(disp * gm_['min'])), (why + '+' if why else '') + 'GBIT_BULLET_MIN %d%%' % round(gm_['min'] * 100)
            if id(src) not in done:
                GBMIN_LOG.setdefault(tech_, []).append((disp, m0, m))
        if mul:
            why = ('power x%g' % mul) + ('+' + why if why else '')
        if tech_ in END_SET and src.get('attackTargetType') == 1:
            if end_new != END_SET[tech_]:
                why = (why + '+' if why else '') + 'STUNROD_DOT 技終了時 %d' % END_SET[tech_]
            end_new = END_SET[tech_]
            if id(src) not in done:
                END_SET_LOG[tech_] = END_SET_LOG.get(tech_, 0) + 1
        dst['minDamage'], dst['endCorrection'] = m, end_new
        if st_new is not None and 'startComboCorrection' in dst:
            dst['startComboCorrection'] = st_new
        if src.get('int11', 0) > 0:
            # NONFC08: undo the power change by the ratio actually written (rounded 表示威力 before / after), so small
            # bullets (威力 2 -> 2, 12 -> 10) keep their armor damage too; non-FC only (FC power OVERRIDES stay as before)
            p0, p1 = int(_power(src) * 1.5), int(_power(dst) * 1.5)
            r_ = p0 / p1 if nonfc and p0 > 0 and p1 > 0 else 1
            if fc_mul != 1 and p0 > 0 and p1 > 0:
                # FC_POWER (11/12): undo only the FC_POWER part (GENOCIDE_POWER x1.5 keeps its armor damage as before)
                r_ = p0 * (mul / fc_mul) / p1
            dst['int11'] = int(src['int11'] * ARMOR_ATK_MOD * r_ + 0.5)
        eh_ = EARLYHEAT.get(bal.get('tech'))
        if eh_ and bal.get('tech') in EARLYHEAT_TURNS:
            assert 'phasesInfo' in path, 'EARLYHEAT turns: %s path %s has no turn' % (bal.get('tech'), path)
            if path[list(path).index('phasesInfo') + 1] not in EARLYHEAT_TURNS[bal['tech']]:
                eh_ = None
        if eh_:
            # EARLYHEAT (user 11/14, 調査記録 53): 早期廃熱 bit on every hit of the weapon (3b carries none, ELEMENT drops 8/16)
            assert not src.get('int2', 0) & 0x18, 'EARLYHEAT: 3b already has 8/16 (%s)' % bal.get('tech')
            dst['int2'] = src.get('int2', 0) | eh_
            if id(src) not in done:
                EARLYHEAT_LOG[bal['tech']] = EARLYHEAT_LOG.get(bal['tech'], 0) + 1
            why = (why + '+' if why else '') + 'EARLYHEAT %d' % eh_
        bn_ = BURN.get(bal.get('tech'))
        if bn_ and bn_.get('file', n) == n and src.get('attackTargetType') == 1:
            # BURN_ADD (作者 11/22, 調査記録 90 §1): 燃焼 (Hit フラグ 0x04、時間 int22 F)。3b に属性 (2 / 4) が無いことを確かめる
            assert not src.get('int2', 0) & 0x06, 'BURN_ADD: 3b already has an element (%s int2 %s)' % (bal.get('tech'), src.get('int2'))
            dst['int2'] = dst.get('int2', 0) | 0x04
            dst['int22'] = bn_['frames']
            if id(src) not in done:
                BURN_LOG[bal['tech']] = BURN_LOG.get(bal['tech'], 0) + 1
            why = (why + '+' if why else '') + 'BURN_ADD 燃焼 %dF' % bn_['frames']
        hc_ = HITCAP.get(bal.get('tech'))
        if hc_ and src.get('attackTargetType') == 1 and src.get('slotNum', 41) == 41:
            # HITCAP (user 11/16, 調査記録 64): 対メカの当たりの最大ヒット数だけ。対弾 (slot 42) は触らない
            h0 = src.get('hitCount')
            assert h0 is not None and (h0 < 0 or h0 > hc_), 'HITCAP: %s hitCount %s' % (bal.get('tech'), h0)
            dst['hitCount'] = hc_
            if id(src) not in done:
                HITCAP_LOG.setdefault(bal['tech'], []).append((h0, hc_))
            why = (why + '+' if why else '') + 'HITCAP %d' % hc_
        ef_ = EVERYF.get(bal.get('tech'))
        if (ef_ and ef_['file'] == n and src.get('attackTargetType') == 1 and src.get('slotNum', 41) == 41
                and 'phasesInfo' in path and path[list(path).index('phasesInfo') + 1] in ef_['turns']):
            # SPREAD_EVERYF (作者 11/22, 調査記録 93): 爆発の対メカの当たりのヒット間隔を短く（params interval）。威力・最低値・技のみ補正は
            # ヒット数の比で換算した整数（全ヒットの合計がおおむね今と同じ）。装甲攻撃力（int11）は上で決めた値のまま
            # （1 ヒットのダメージが小さくても装甲ゲージは max(1, …) で 1 ずつ減る）。int11 の後に書くので p0/p1 の打ち消しは掛からない
            t_ = path[list(path).index('phasesInfo') + 1]
            pw0 = _power(dst)
            assert pw0 > 0 and src.get('hitInterval', 0) > ef_['interval'], ('SPREAD_EVERYF', bal.get('tech'), t_, pw0, src.get('hitInterval'))
            for u in dst['ceventHitUnitList']:
                if u.get('unitSlotNum') == 6:
                    for b in u['data']['bsdxInfoCollectionList']:
                        assert len(b['paramList']) == 1, ('SPREAD_EVERYF', b['paramList'])
                        b['paramList'] = [ef_['power']]
            assert _power(dst) == ef_['power']
            ic0 = dst.get('internalCorrection')
            dst['hitInterval'] = ef_['interval']
            if 'ic' in ef_:
                dst['internalCorrection'] = ef_['ic']
            if id(src) not in done:
                EVERYF_LOG.setdefault(bal['tech'], []).append((t_, src['hitInterval'], ef_['interval'], int(pw0 * 1.5),
                                                              int(ef_['power'] * 1.5), m, ef_['min'], ic0, dst.get('internalCorrection')))
            disp, m = int(ef_['power'] * 1.5), ef_['min']
            dst['minDamage'] = m
            why = (why + '+' if why else '') + 'SPREAD_EVERYF 間隔 %dF 表示 %d 最低 %d' % (ef_['interval'], disp, m)
        if id(src) in done:
            continue
        done.add(id(src))
        si = path[1] if len(path) > 1 and path[0] == 'skillList' else -1
        sk = objs[n]['skillList'][si] if si >= 0 else {}
        rows.append((n, si, (sk or {}).get('skillNameJapanese', '?'), disp, src['minDamage'], m,
                     src['endCorrection'], end_new, bal.get('tech', '?'), why,
                     src.get('startComboCorrection'), st_new))
    missing_fs = sorted(set(FC_SHAPE) - set(FC_SHAPE_LOG))
    assert not missing_fs or not cat, 'FC_SHAPE: no hit rewritten for %s' % missing_fs
    assert not cat or set(BURN) == set(BURN_LOG), 'BURN_ADD: no hit for %s' % (set(BURN) - set(BURN_LOG))
    assert not cat or set(EVERYF) == set(EVERYF_LOG), 'SPREAD_EVERYF: no hit for %s' % (set(EVERYF) - set(EVERYF_LOG))
    assert not cat or all(sorted({t for t, *_ in BOMBBIT_LOG.get(k, ())}) == sorted(v['turns']) for k, v in BOMBBIT.items()), \
        'BOMBBIT_BODY: hits per turn %s' % BOMBBIT_LOG
    assert not cat or set(GBMIN) == set(GBMIN_LOG), 'GBIT_BULLET_MIN: no hit for %s' % (set(GBMIN) - set(GBMIN_LOG))
    assert not cat or set(END_SET) == set(END_SET_LOG), 'STUNROD_DOT end_corr: no hit for %s' % (set(END_SET) - set(END_SET_LOG))
    if SELF_ARMOR_ON:
        _self_armor(new)
    else:
        del ARMOR_LOG[:]
    return new, rows


def _self_armor(new):
    """SELFARMOR15: slot 36 段階 of the mech's own skills in the modified copy (x SELF_ARMOR_MOD floor, SELF_ARMOR_SET)."""
    del ARMOR_LOG[:]
    w = new.get(SELF_WAZ)
    assert w is not None, 'SELFARMOR15: %s not among the modified files %s' % (SELF_WAZ, sorted(new))
    seen = set()
    for si, s in enumerate(w['skillList']):
        if not s:
            continue
        nm = s.get('skillNameJapanese') or ''
        ch = []
        for ph in s['phasesInfo']:
            for u in ph['skillUnitCollection']:
                if u['unitQuantity'] != 36:
                    continue
                for o in u['skillInfoObjectList']:
                    v = o.get('int4', 0)
                    if v > 0:
                        o['int4'] = SELF_ARMOR_SET[nm] if nm in SELF_ARMOR_SET else int(v * SELF_ARMOR_MOD)
                        ch.append((v, o['int4']))
        if ch:
            seen.add(nm)
            ARMOR_LOG.append((si, nm, sorted({a for a, b in ch}), sorted({b for a, b in ch})))
    missing = sorted(set(SELF_ARMOR_SET) - seen)
    assert not missing, 'SELFARMOR15: no armored skill named %s' % missing


def only_keys_changed(a, b, keys=KEYS):
    """Structural diff: True if a and b differ only in the values of <keys>."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if set(a) != set(b):
            return False
        if a.get('unitQuantity') == 36 and 'int4' not in keys:      # SELFARMOR15: 装甲 段階 inside slot 36 units only
            keys = tuple(keys) + ('int4',)
        return all(k in keys or only_keys_changed(a[k], b[k], keys) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(only_keys_changed(x, y, keys) for x, y in zip(a, b))
    return a == b


def table_md(rows):
    L = ['# 透 改善版（modified/Update3.pac）の最低値と技終了時（自動生成）', '',
         '規則: 格闘・射撃の通常技は COMBOV3（tools/bfe2bsdx_combo_v3.py, 調査記録 38。最低値 = 表示威力 x 技ごとの比、初段補正・技終了時も）。'
         'それ以外（FC など）は 最低値 = 係数 %g の役割を保つ式、技終了時 = 原作再現 x%g（調査記録 B4 §7・§8）。原作再現版の最低値は BFE 最低威力 x3/8。'
         '表示威力 = 威力 x1.5（改善版は x0.8 後）。同じ値のヒットはまとめています。' % (ROLE_G_MOD, END_MUL_MOD), '',
         '| ファイル | 技 | 表示威力: 最低値 原作再現 → 改善版 / 技終了時 原作再現 → 改善版 |', '|---|---|---|']
    by = {}
    for n, si, nm, d, m0, m1, e0, e1, tech, why, s0, s1 in rows:
        k_ = (n, si, '%s（%s）' % (nm, tech) if tech not in nm else nm)
        c = '%d: %d → **%d** / %d → **%d**%s%s' % (d, m0, m1, e0, e1, ' / 初段 %s → **%s**' % (s0, s1) if s0 != s1 else '',
                                                 '（%s）' % why if why else '')
        if c not in by.setdefault(k_, []):
            by[k_].append(c)
    for (n, si, nm), cells in by.items():
        L.append('| %s | [%d] %s | %s |' % (n.split('.')[0], si, nm, '<br>'.join(cells)))
    L += ['', '## 武装ごとの調整（OVERRIDES / FC_MIN）', '', '| 武装 | 調整（最低値 / 表示威力、威力の倍率） | 意図 |', '|---|---|---|',
          '| FC（必殺）すべて | %g %s%s | %s |' % (FC_MIN, 'ちょうど' if FC_MIN_EXACT else '以上',
                                                 ''.join('<br>%s %s' % (k, ' / '.join('%s %g' % (f, x) for f, x in v.items()) if isinstance(v, dict) else '%g' % v)
                                                         for k, v in FC_MIN_EXCEPT.items()), FC_WHY)]
    L += ['| %s | %s | %s |' % (k, ' / '.join(x for x in ('%g 以上' % v['min'] if 'min' in v else '', '%g ちょうど' % v['min_set'] if 'min_set' in v else '',
                                                         '威力 x%g' % v['power'] if 'power' in v else '') if x), v['why'])
          for k, v in OVERRIDES.items()]
    if EARLYHEAT:
        L += ['', '## 早期廃熱（EARLYHEAT、攻撃判定のフラグ 8 / 16）', '', '| 武装 | 値 | 付けたヒット数 |', '|---|---|---|']
        L += ['| %s | %d | %d |' % (k, v, EARLYHEAT_LOG.get(k, 0)) for k, v in EARLYHEAT.items()]
    if ARMOR_LOG:
        L += ['', '## 自機の装甲（slot 36 段階、x%g 切り捨て＋上書き SELF_ARMOR_SET）' % SELF_ARMOR_MOD, '',
              '| 技 | 原作再現 → 改善版 |', '|---|---|']
        L += ['| [%d] %s | %s → **%s**%s |' % (si, nm, '/'.join(map(str, a)), '/'.join(map(str, b)), '（上書き）' if nm in SELF_ARMOR_SET else '')
              for si, nm, a, b in ARMOR_LOG]
    return '\n'.join(L) + '\n'
