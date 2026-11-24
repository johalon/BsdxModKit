#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bfe2bsdx_modified_behavior.py — 改善版（modified/）だけの技の挙動の調整（ユーザー 2026-11-10）。

項目の一覧・切り替え・値は tools/modified_tweaks.py（kind '挙動'）。ここは on の項目だけを、改善版の Tooru.waz の写しに当てる。
どの関数も、相手のデータが想定どおりか（技名・ターン・値）を assert で確かめてから変える（変換が変わって前提が崩れたら
ビルドが止まる）。原作再現版（3b）のデータには触らない。
apply(new, self_waz=, bullet_waz=, spm_file=, eft_file=, eft_slot=) -> (log 行のリスト, 変えた技の index の集合)。build_phase3b.py の I2 が呼ぶ。
機体のファイル名・スロットは apply() の引数で受け取る（透: Tooru.waz / Tama04.waz / tooru.spm / tooru_eft.spm / 135。docs/porting/09_porting_another_mech.md §6 案 2）。
"""
import copy
import modified_tweaks as MT
import modified_ground_armor as GA      # GROUND_ARMOR（地上で出した技の装甲、調査記録 66）。取りやめるときは ORDER の行と一緒に消す

# 機体のファイル名・スロット: apply() が引数から入れる（透: 'Tooru.waz'、'Tama04.waz'、'tooru.spm'、'tooru_eft.spm'、135）
SELF_WAZ = BULLET_WAZ = SPM_FILE = EFT_FILE = EFT_SLOT = None
EFFECT_WAZ = None   # 共有のエフェクト waz（透: 'Tama02.waz'）。apply() の effect_waz。STUNROD_DOT が改善版だけの技を末尾に足す
_NEW = {}      # apply() の new（Tooru.waz 以外のファイルを触る項目用）


def _skill(w, name):
    hit = [(i, s) for i, s in enumerate(w['skillList']) if s and s.get('skillNameJapanese') == name]
    assert len(hit) == 1, 'modified behavior: skill %s found %d times' % (name, len(hit))
    return hit[0]


def _units(turn, slot):
    return [u for u in turn['skillUnitCollection'] if u['unitQuantity'] == slot]


def _objs(turn, slot):
    return [o for u in _units(turn, slot) for o in u['skillInfoObjectList']]


def _drop(turn, slot):
    n = len(_objs(turn, slot))
    turn['skillUnitCollection'] = [u for u in turn['skillUnitCollection'] if u['unitQuantity'] != slot]
    return n


def _end_jump(turn):
    """The turn's unconditional jump at its last frame (slot 71, no condition)."""
    js = [o for o in _objs(turn, 71) if o['flag'] == 1 and o['bsdxInfoCollectionList1'][0]['typeList'] == [0]]
    assert len(js) == 1, 'modified behavior: %d unconditional jumps' % len(js)
    return js[0]


def gs_recoil(w, log):
    """GS_RECOIL: ジェノサイド・ショットガンの射撃ターンの反動（slot 18 の後ろ向き初速）x mul。"""
    si, s = _skill(w, 'ジェノサイド・ショットガン')
    mul = MT.p('GS_RECOIL', 'mul')
    for t in MT.p('GS_RECOIL', 'turns'):
        turn = s['phasesInfo'][t]
        d15 = _objs(turn, 15)
        assert len(d15) == 1 and d15[0]['bsdxInfoCollectionList'][0]['paramList'][0] == 180, 'GS_RECOIL: turn %d is not the backward shot turn' % t
        assert _objs(turn, 48), 'GS_RECOIL: turn %d fires nothing' % t
        r = [o for o in _objs(turn, 18) if o['int1'] == 0 and o['startFrame'] == 0 and o['int2'] > 0]
        assert len(r) == 1, 'GS_RECOIL: turn %d recoil slot 18 not unique' % t
        a = r[0]['int2']; r[0]['int2'] = max(0, round(a * mul))
        log.append('GS_RECOIL ジェノサイド・ショットガン turn %d: 反動 slot 18 %d -> %d px/F (F%d-%d で %d へ)' % (
            t, a, r[0]['int2'], r[0]['startFrame'], r[0]['endFrame'], r[0]['int5']))
    return si


def gs_interval(w, log):
    """GS_INTERVAL: 射撃の後のターンを cut F 短くする（ターン末の無条件ジャンプを前へ、はみ出すイベントは切る）。"""
    si, s = _skill(w, 'ジェノサイド・ショットガン')
    cut = MT.p('GS_INTERVAL', 'cut')
    for t in MT.p('GS_INTERVAL', 'turns'):
        turn = s['phasesInfo'][t]
        assert _objs(turn, 48), 'GS_INTERVAL: turn %d fires nothing' % t
        j = _end_jump(turn)
        old = j['startFrame']; new = old - cut
        assert j['endFrame'] == old and new > 0
        fire_last = max(o['startFrame'] for o in _objs(turn, 48))
        assert fire_last < new, 'GS_INTERVAL: the shot itself would be cut'
        n_cut = 0
        for u in turn['skillUnitCollection']:
            keep = []
            for o in u['skillInfoObjectList']:
                if o is j:
                    o['startFrame'] = o['endFrame'] = new
                elif o['startFrame'] > new:
                    n_cut += 1
                    continue
                elif o['endFrame'] > new:
                    o['endFrame'] = new
                keep.append(o)
            u['skillInfoObjectList'] = keep
        turn['skillUnitCollection'] = [u for u in turn['skillUnitCollection'] if u['skillInfoObjectList']]
        log.append('GS_INTERVAL ジェノサイド・ショットガン turn %d: ターン末 F%d -> F%d（%d F 短縮、はみ出したイベント %d 件を削除）' % (
            t, old, new, cut, n_cut))
    return si


def _zero_resets(turn, t, tid):
    for sl in (19, 21):
        for o in _objs(turn, sl):
            assert all(o[k] == 0 for k in ('int1', 'int2', 'int3', 'int4', 'int5', 'int6')) and o['startFrame'] == 0, \
                '%s: turn %d slot %d is not the 0 reset' % (tid, t, sl)


def gs_gravity(w, log):
    """GS_GRAVITY: ジェノサイド・ショットガンの turn start_turn の slot 21（重力 0）を 重力 gravity にし、それより後のターンの slot 19 / 21 を外す。
    start_turn より前のターンと start_turn の slot 19（縦速度 0）はそのまま。"""
    si, s = _skill(w, 'ジェノサイド・ショットガン')
    g = MT.p('GS_GRAVITY', 'gravity')
    st = MT.p('GS_GRAVITY', 'start_turn')
    assert _objs(s['phasesInfo'][st], 48), 'GS_GRAVITY: start turn %d is not the first shot' % st
    n19 = n21 = 0
    for t, turn in enumerate(s['phasesInfo']):
        _zero_resets(turn, t, 'GS_GRAVITY')
        if t == st:
            o21 = _objs(turn, 21)
            assert len(o21) == 1, 'GS_GRAVITY: turn %d has no slot 21 to reuse' % t
            o21[0]['int5'] = g
        elif t > st:
            n19 += _drop(turn, 19)
            n21 += _drop(turn, 21)
    log.append('GS_GRAVITY ジェノサイド・ショットガン: turn %d F0 に重力 %d、turn %d 以降の slot 19（縦速度 0）%d 個・slot 21（重力 0）%d 個を削除' % (
        st, g, st + 1, n19, n21))
    return si


def seiryu_vinertia(w, log):
    """SEIRYU_VINERTIA: 青龍刀の各ターンの 縦速度 0（slot 19）と 重力 0（slot 21）を外し、最初のターンだけ 重力 gravity。
    甲 デュアルハーケン Lv3 と同じ組み方（turn 0 に slot 21 int5 25、slot 19 なし、以後のターンは slot 19 / 21 なし）。"""
    si, s = _skill(w, '青龍刀')
    g = MT.p('SEIRYU_VINERTIA', 'gravity')
    n19 = n21 = 0
    for t, turn in enumerate(s['phasesInfo']):
        for o in _objs(turn, 19):
            assert all(o[k] == 0 for k in ('int1', 'int2', 'int3', 'int4', 'int5', 'int6')) and o['startFrame'] == 0, \
                'SEIRYU_VINERTIA: turn %d slot 19 is not the 0 reset' % t
        for o in _objs(turn, 21):
            assert all(o[k] == 0 for k in ('int1', 'int2', 'int3', 'int4', 'int5', 'int6')) and o['startFrame'] == 0, \
                'SEIRYU_VINERTIA: turn %d slot 21 is not gravity 0' % t
        n19 += _drop(turn, 19)
        if t == 0:
            o21 = _objs(turn, 21)
            assert len(o21) == 1, 'SEIRYU_VINERTIA: turn 0 has no slot 21 to reuse'
            o21[0]['int5'] = g
        else:
            n21 += _drop(turn, 21)
    log.append('SEIRYU_VINERTIA 青龍刀: slot 19（縦速度 0）%d 件・slot 21（重力 0）%d 件を削除、turn 0 F0 に重力 %d（甲 デュアルハーケン Lv3 と同じ）' % (
        n19, n21, g))
    return si


def seiryu_nokevz(w, log):
    """SEIRYU_NOKEVZ: 青龍刀の全ヒットの のけぞり 4 欄に フラグ bit1（攻撃側の縦速度を吹き飛びに足す）。吹き飛び重力 0 は noke_gravity に。"""
    si, s = _skill(w, '青龍刀')
    gv = MT.p('SEIRYU_NOKEVZ', 'noke_gravity')
    n = ng = 0
    for turn in s['phasesInfo']:
        for h in _objs(turn, 41):
            for hu in h['ceventHitUnitList']:
                if 17 <= hu['unitSlotNum'] <= 20 and hu.get('data'):
                    d = hu['data']
                    assert d.get('int10', 0) != -999, 'SEIRYU_NOKEVZ: 吹き飛び規模 -999 (keep) would skip the vertical branch'
                    d['short1'] = d.get('short1', 0) | 2; n += 1
                    if d.get('int11', 0) == 0:
                        d['int11'] = gv; ng += 1
    assert n, 'SEIRYU_NOKEVZ: no nokezori found'
    log.append('SEIRYU_NOKEVZ 青龍刀: のけぞり %d 欄に フラグ bit1（攻撃側の縦速度、0x619179）、吹き飛び重力 0 -> %d を %d 欄' % (n, gv, ng))
    return si


SW_NAME = 'スウィングワイヤー'
SW_BULLET = ('Laser.waz', 'スウィングワイヤー：ライン親（透移植）')


def _turn_jumps(turn):
    """slot 71 objects whose destination is ターンジャンプ→指定(n) (typeList [0, 1])."""
    return [o for o in _objs(turn, 71) if o['bsdxInfoCollectionList2'][0]['typeList'] == [0, 1]]


def _land_cond(w):
    """「オブジェクト→接触→着地していたら」(typeList [2, 7, 16]) を Tooru.waz の frame-0 分岐（ギャラクティックストライク等）から取る。"""
    for s in w['skillList']:
        for turn in (s or {}).get('phasesInfo', []):
            for o in _objs(turn, 71):
                if o['bsdxInfoCollectionList2'][0]['typeList'] != [0, 1]:
                    continue
                for c in o['bsdxInfoCollectionList1']:
                    if c['typeList'] == [2, 7, 16] and not c['int2']:
                        return o
    raise AssertionError('SW_AIRLIFT: no 着地していたら dispatch sample in %s' % SELF_WAZ)


def sw_inertia(w, log):
    """SW_INERTIA: スウィングワイヤーの全ターンから slot 18（技の速度: F0 の 0 リセットと、以後の「前±0」保持）を外す。
    甲 スィングワイヤー Lv1-3 と同じく速度イベントなし = 出した時の横の勢いがエンジンの通常の動きで残る。"""
    si, s = _skill(w, SW_NAME)
    n = 0
    for t, turn in enumerate(s['phasesInfo']):
        for o in _objs(turn, 18):
            assert o['int1'] in (0, 1) and o['int5'] == 0 and o['int2'] == 0, 'SW_INERTIA: turn %d slot 18 is not 0 / 前±0' % t
        n += _drop(turn, 18)
    log.append('SW_INERTIA %s: slot 18（速度 0 リセット・保持）%d 件を削除（甲 スィングワイヤーと同じく速度イベントなし）' % (SW_NAME, n))
    return si


def sw_armor(w, log):
    """SW_ARMOR: スウィングワイヤーの turn 0 F0 に 装甲（slot 36）level、戻りの turn（最後）F0 に 0。
    甲 スィングワイヤー Lv3（Kou.waz 140: turn 0 F0 = 3、回転後の turn 2 F0 = 0）と同じ置き方。SW_AIRLIFT より前に当て、空中版にも写す。"""
    import copy
    si, s = _skill(w, SW_NAME)
    lv = MT.p('SW_ARMOR', 'level')
    ph = s['phasesInfo']
    assert len(ph) == 3 and _objs(ph[1], 41), 'SW_ARMOR: expected 構え / 回転（当たり）/ 戻り の 3 ターン'
    tpl = None
    for s2 in w['skillList']:
        for turn in (s2 or {}).get('phasesInfo', []):
            for u in _units(turn, 36):
                tpl = tpl or u
    assert tpl is not None, 'SW_ARMOR: no slot 36 sample in %s' % SELF_WAZ
    for t, val in ((0, lv), (len(ph) - 1, 0)):
        assert not _units(ph[t], 36), 'SW_ARMOR: turn %d already has 装甲' % t
        u = copy.deepcopy(tpl)
        o = copy.deepcopy(u['skillInfoObjectList'][0])
        o.update(int1=0, int2=0, int3=0, int4=val, startFrame=0, endFrame=0, offset=0)
        u['skillInfoObjectList'] = [o]
        uc = ph[t]['skillUnitCollection']
        k = next((i for i, x in enumerate(uc) if x['unitQuantity'] > 36), len(uc))
        uc.insert(k, u)
    log.append('SW_ARMOR %s: 装甲 %d を turn 0 F0 から、戻りの turn %d F0 で 0（甲 スィングワイヤーと同じ）' % (SW_NAME, lv, len(ph) - 1))
    return si


def sw_launch(w, log):
    """SW_LAUNCH: スウィングワイヤー 本体（中心部）の当たり（1 回だけ）の のけぞりの 吹き飛び規模（int10、0x6191b9: 縦速度 = int10/10 px/F）を
    launch、吹き飛び重力（int11、0x619219: 被弾側の重力補正率 % = slot 27 相当）を rate にする（int10 のある欄 = 地上・空中・空中→地上）。
    被弾側の重力 = 基準（0x6191de: 被弾数 +0x18f4 が 2 以下で 50、以後 20n+10）x rate% / 200 px/F^2。
    SW_AIRLIFT より前に当て、空中版にも写す。"""
    si, s = _skill(w, SW_NAME)
    v, r = MT.p('SW_LAUNCH', 'launch'), MT.p('SW_LAUNCH', 'rate')
    hs = MT.p('SW_LAUNCH', 'hitstop')
    ch = []
    hsl = []
    for t, turn in enumerate(s['phasesInfo']):
        for h in _objs(turn, 41):
            if hs is not None:
                # 11/13 夜: ヒットストップ（int15 被弾側 / int16 自機、推定）20F の間に 6F ごとのワイヤーが当たり、敵が動き出す前に
                # 縦速度を上書きしていた（推定）→ 短くして、打ち上げがワイヤーの次の当たりまでに効くように
                hsl.append((t, h.get('int15'), h.get('int16')))
                h['int15'], h['int16'] = hs, hs
            for hu in h['ceventHitUnitList']:
                d = hu.get('data')
                if 17 <= hu['unitSlotNum'] <= 20 and d and d.get('int10', 0) > 0:
                    ch.append((t, hu['unitSlotNum'], d['int10'], v, d.get('int11', 0), r))
                    d['int10'], d['int11'] = v, r
    assert ch, 'SW_LAUNCH: no 吹き飛び規模 found'
    log.append('SW_LAUNCH %s: 本体の当たりの 吹き飛び規模・重力: %s%s' % (
        SW_NAME, ', '.join('turn %d 欄 %d 規模 %d -> %d 重力 %d -> %d' % c for c in ch),
        ''.join('; turn %d ヒットストップ %s/%s -> %d' % (t, a, b, hs) for t, a, b in hsl)))
    return si


def sw_wirefloat(w, log):
    """SW_WIREFLOAT: ワイヤー（Laser.waz 透移植 ライン親、6F ごとに当たる）の 空中欄（18）を自前の値にし（int1 = 0、元は地上欄と同じ）、
    吹き飛び規模 -999（0x619160: 縦速度を変えない）・吹き飛び重力 rate。空中の敵にワイヤーが当たっても、本体の打ち上げの勢いを上書きしない
    （以前は毎回 縦速度 0.7 px/F・重力 44% に置き直して打ち上げを止めていた）。重力の補正率だけは毎回 rate に置き直す。"""
    import copy
    fn, name = SW_BULLET
    lw = _NEW.get(fn)
    assert lw is not None, 'SW_WIREFLOAT: %s not among the modified files' % fn
    si, s = _skill(lw, name)
    # 11/13 改: 縦速度の上書き（規模 7 = 0.7 px/F）は残す（ユーザー「上書きしないと飛びすぎる」）。重力だけ rate にしてワイヤーのヒット後もふわっと。
    r = MT.p('SW_WIREFLOAT', 'rate')
    lv = MT.p('SW_WIREFLOAT', 'launch')
    ch = []
    for turn in s['phasesInfo']:
        for h in _objs(turn, 41):
            for hu in h['ceventHitUnitList']:
                d = hu.get('data')
                if 17 <= hu['unitSlotNum'] <= 20 and d and not d.get('int1'):    # int1 = 1..4 は他の欄と同じ → 自前の欄だけ
                    ch.append((hu['unitSlotNum'], d.get('int10', 0), d.get('int11', 0))); d['int11'] = r
                    if lv is not None:
                        d['int10'] = lv
                    pl = MT.p('SW_WIREFLOAT', 'pull')
                    if pl is not None:      # 11/13 夜: のけぞり速度（負 = 引き寄せ、調査記録 43 で −1 / 減速 25）
                        assert d.get('int8', 0) < 0, 'SW_WIREFLOAT: wire nokezori speed is not a pull'
                        log.append('SW_WIREFLOAT: 欄 %d 引き寄せ（のけぞり速度）%d -> %d' % (hu['unitSlotNum'], d['int8'], pl))
                        d['int8'] = pl
    assert ch, 'SW_WIREFLOAT: no own nokezori column'
    log.append('SW_WIREFLOAT %s %s: 吹き飛び規模 -> %s・重力 -> %d（%s、他の欄はこれと同じ設定）' % (
        fn, name, lv, r, ', '.join('欄 %d 元 %d / %d' % c for c in ch)))
    return [(fn, si)]


def sw_airlift(w, log):
    """SW_AIRLIFT: 空中で出したときだけ、縦の勢いを残したまま上向きの加速（重力 gravity < 0）をかけ続ける。
    全ターン（0..n-1）を写して空中版（n..2n-1）を作り、turn 0 F0 に「NOT 着地していたら → turn n」を入れる。
    空中版は slot 19（縦速度 0）/ 21（重力 0）を外し、turn n F0 だけ slot 21 重力 gravity。地上版は今のまま（浮かない）。
    重力 G の加速度 = G*1024/200 /1024 px/F^2（0x5f4be0）。G = -1 で 148F（技全体）に 約 53px 上がる（ジャンピングニーの頂点 60px 相当）。"""
    import copy
    si, s = _skill(w, SW_NAME)
    g = MT.p('SW_AIRLIFT', 'gravity')
    ph = s['phasesInfo']; n = len(ph)
    assert s.get('phaseQuantity', n) == n and len(s.get('skillSuffixList', [])) == n, 'SW_AIRLIFT: turn count mismatch'
    for t, turn in enumerate(ph):
        _zero_resets(turn, t, 'SW_AIRLIFT')
        for o in _turn_jumps(turn):
            assert 0 < o['bsdxInfoCollectionList2'][0]['paramList'][0] < n, 'SW_AIRLIFT: turn %d jumps outside the skill' % t
    air = copy.deepcopy(ph)
    n19 = n21 = 0
    for t, turn in enumerate(air):
        for o in _turn_jumps(turn):
            o['bsdxInfoCollectionList2'][0]['paramList'][0] += n
        n19 += _drop(turn, 19)
        if t == 0:
            o21 = _objs(turn, 21)
            assert len(o21) == 1, 'SW_AIRLIFT: turn 0 has no slot 21 to reuse'
            o21[0]['int5'] = g
        else:
            n21 += _drop(turn, 21)
    # 11/12 夜（ユーザー）: 前半（技の decel_from F まで）は gravity で加速、そこから重力 decel_gravity（正 = 下向き）で上昇速度の約 7 割を失う
    dfrom, dg = MT.p('SW_AIRLIFT', 'decel_from'), MT.p('SW_AIRLIFT', 'decel_gravity')
    where = None
    if dfrom is not None:
        f0 = 0
        for t, turn in enumerate(air):
            L = _end_jump(turn)['startFrame'] + 1
            if f0 <= dfrom < f0 + L:
                where = (t, dfrom - f0)
                o = copy.deepcopy(o21[0])
                o.update(int5=dg, startFrame=dfrom - f0, endFrame=dfrom - f0, offset=0)
                u = [x for x in ph[0]['skillUnitCollection'] if x['unitQuantity'] == 21][0]
                u = copy.deepcopy(u); u['skillInfoObjectList'] = [o]
                uc = turn['skillUnitCollection']
                assert not _units(turn, 21), 'SW_AIRLIFT: decel turn already has slot 21'
                uc.insert(next((i for i, x in enumerate(uc) if x['unitQuantity'] > 21), len(uc)), u)
                break
            f0 += L
        assert where, 'SW_AIRLIFT: decel_from F%d is outside the skill' % dfrom
    ph.extend(air)
    s['phaseQuantity'] = len(ph)
    suf = s['skillSuffixList']
    for t in range(n):
        x = copy.deepcopy(suf[t]); x['int1'] = n + t; suf.append(x)
    d = copy.deepcopy(_land_cond(w))
    c = [b for b in d['bsdxInfoCollectionList1'] if b['typeList'] == [2, 7, 16]][0]
    c['int2'] = 1                                  # NOT（バニラ Akao ハンマーブロウ「NOT 着地していたら ⇒ 空中版」）
    d['bsdxInfoCollectionList1'] = [c]; d['flag'] = 1
    j = d['bsdxInfoCollectionList2'][0]
    assert j['typeList'] == [0, 1], 'SW_AIRLIFT: dispatch sample is not a turn jump'
    j['paramList'] = [n]
    d['startFrame'] = d['endFrame'] = 0; d['offset'] = 0
    u71 = _units(ph[0], 71)
    assert u71, 'SW_AIRLIFT: turn 0 has no slot 71'
    u71[0]['skillInfoObjectList'].insert(0, d)
    log.append('SW_AIRLIFT %s: 空中版 turn %d-%d を追加（turn 0 F0「NOT 着地していたら → turn %d」）。空中版は slot 19 %d 件・slot 21 %d 件を削除、'
               'turn %d F0 に重力 %d（上向きの加速、約 %.4f px/F^2）' % (SW_NAME, n, 2 * n - 1, n, n19, n21, n, g, -int(g * 1024 / 200) / 1024)
               + ('、技の F%d（turn %d F%d）から重力 %d（約 %.4f px/F^2 の減速）' % (dfrom, n + where[0], where[1], dg, int(dg * 1024 / 200) / 1024)
                  if where else ''))
    return si


def sw_nokevz(w, log):
    """SW_NOKEVZ: スウィングワイヤーのワイヤー（Laser.waz の透移植 ライン親）の全ヒットの のけぞり 4 欄に フラグ bit1（攻撃側の縦速度を足す、
    0x619179）。甲 スィングワイヤー Lv1-3 の ライン親・先端も空中欄に bit1 を持つ（バニラの前例）。
    注意（未確認）: 0x619183 は「攻撃側」オブジェクトの縦速度（+0x14a4 → +0x3c）を読む。攻撃側が弾（ワイヤー）自身なら、ワイヤーは
    slot 11 で毎 F 透の位置に置き直される（0x610e70）ので縦速度は 0 のままで、効かない可能性がある。実機で確認する。"""
    fn, name = SW_BULLET
    lw = _NEW.get(fn)
    assert lw is not None, 'SW_NOKEVZ: %s not among the modified files' % fn
    si, s = _skill(lw, name)
    gv = MT.p('SW_NOKEVZ', 'noke_gravity')
    n = ng = 0
    for turn in s['phasesInfo']:
        for h in _objs(turn, 41):
            for hu in h['ceventHitUnitList']:
                if 17 <= hu['unitSlotNum'] <= 20 and hu.get('data'):
                    d = hu['data']
                    assert d.get('int10', 0) != -999, 'SW_NOKEVZ: 吹き飛び規模 -999 (keep) would skip the vertical branch'
                    d['short1'] = d.get('short1', 0) | 2; n += 1
                    if d.get('int11', 0) == 0:
                        d['int11'] = gv; ng += 1
    assert n, 'SW_NOKEVZ: no nokezori found'
    log.append('SW_NOKEVZ %s %s: のけぞり %d 欄に フラグ bit1（攻撃側の縦速度、0x619179）、吹き飛び重力 0 -> %d を %d 欄' % (fn, name, n, gv, ng))
    return [(fn, si)]


def armor_cont(w, log):
    """ARMOR_CONT: 同じフレームに「装甲 0」と「装甲 N（>0）」が並ぶところ（変換で BFE のフェーズをヒットの境目で切ったときにできる）から
    「装甲 0」を外す。エンジンが 0 を後に処理すると、そのターンの残りで装甲が切れる（ユーザー 11/12「武幻の装甲が段ごとに途切れる」）。
    装甲 N の再設定（プールの補充）はそのまま。全技が対象。"""
    out = []
    for si, s in enumerate(w['skillList']):
        if not s:
            continue
        n = 0
        for turn in s['phasesInfo']:
            for u in _units(turn, 36):
                fr = {}
                for o in u['skillInfoObjectList']:
                    fr.setdefault(o['startFrame'], []).append(o.get('int4', 0))
                both = {f for f, vs in fr.items() if 0 in vs and any(v > 0 for v in vs)}
                keep = [o for o in u['skillInfoObjectList'] if not (o['startFrame'] in both and o.get('int4', 0) == 0)]
                n += len(u['skillInfoObjectList']) - len(keep)
                u['skillInfoObjectList'] = keep
        if n:
            out.append(si)
            log.append('ARMOR_CONT %s: 同じフレームの「装甲 0」%d 件を削除（装甲が途切れないように）' % (s.get('skillNameJapanese'), n))
    assert out, 'ARMOR_CONT: nothing to fix'
    return [(SELF_WAZ, si) for si in out]


def _add_effect_sub(o, sample, idx):
    """発射（slot 48）o に、sample の発射から サブオブジェクト idx を写す（unitSlotNum の順に差し込む）。"""
    import copy
    key = [k for k, v in o.items() if isinstance(v, list) and v and isinstance(v[0], dict) and 'unitSlotNum' in v[0]][0]
    src = [x for x in sample[key] if x['unitSlotNum'] == idx]
    assert len(src) == 1 and src[0].get('data'), 'sample fire has no sub %d' % idx
    lst = o[key]
    assert not any(x['unitSlotNum'] == idx and x.get('data') for x in lst), 'fire already has sub %d' % idx
    lst[:] = [x for x in lst if x['unitSlotNum'] != idx]
    x = copy.deepcopy(src[0]); x['data']['offset'] = 0
    k = next((i for i, y in enumerate(lst) if y['unitSlotNum'] > idx), len(lst))
    lst.insert(k, x)
    return x['data']


def gf_size(w, log):
    """GF_SIZE: ギガンテックフィールドの場（Tama04 透移植弾303）の 拡大縮小（slot 1）を全部 x mul。判定（スプライトの当たり矩形 ±32px）も同じ倍率で広がる。
    発射（Tooru.waz turn 2 の slot 48）に 発射位置補正：方向（自機の向き）と 距離 dist px を足して、場の後ろの端が自機に来るようにする。"""
    mul = MT.p('GF_SIZE', 'mul'); dist = MT.p('GF_SIZE', 'dist')
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'GF_SIZE: Tama04.waz not among the modified files'
    bi, b = _skill(tw, 'ｷﾞｶﾞﾝﾃｯｸﾌｨｰﾙﾄﾞ（透移植弾303）')
    n = 0
    for turn in b['phasesInfo']:
        for o in _objs(turn, 1):
            o['int2'] = round(o['int2'] * mul); o['int5'] = round(o['int5'] * mul); n += 1
    assert n == 5, 'GF_SIZE: expected 5 scale events, got %d' % n
    # 11/17（調査記録 75 §3）: 場の turn 0 は slot 11 前指定を維持 + slot 18 の α（自機からの前方オフセット px、STICKALPHAPOS）で
    # 毎 F 位置が決まる。発射位置補正の距離は効いていなかった（実機で 300 -> 400 が変わらない）ので、α に ahead px を足す。
    ahead = MT.p('GF_SIZE', 'ahead')
    a18 = [o for o in _objs(b['phasesInfo'][0], 18) if o['int2'] or o['int5']]
    assert len(a18) == 1 and _objs(b['phasesInfo'][0], 11), 'GF_SIZE: turn 0 alpha (slot 18) / keep (slot 11) not as expected'
    a_old = (a18[0]['int2'], a18[0]['int5'])
    a18[0]['int2'] += ahead; a18[0]['int5'] += ahead
    si, s = _skill(w, 'ギガンテックフィールド')
    fires = [o for o in _objs(s['phasesInfo'][2], 48)
             if any(x['unitSlotNum'] == 3 and x.get('data') and x['data']['wazSequenceNo'] == bi
                    for x in o['ceventEffectUnitList'])]
    assert len(fires) == 1, 'GF_SIZE: field fire not found in turn 2'
    _, ef = _skill(w, 'E・フィンガー')
    sample = next(o for turn in ef['phasesInfo'] for o in _objs(turn, 48)
                  if any(x['unitSlotNum'] == 10 and x.get('data') for x in o['ceventEffectUnitList']))
    # 発射位置補正は 11/12〜11/17 の形のまま残す（int5 だけ dist。実機で効いていないと分かったが、前のパックとの違いを α だけにするため）
    _add_effect_sub(fires[0], sample, 8)
    d10 = _add_effect_sub(fires[0], sample, 10)
    d10.update(int1=0, int2=0, int3=0, int4=0, int5=dist, int6=0)
    log.append('GF_SIZE ギガンテックフィールド: 場の拡大縮小 %d 件 x%g（最大 640 -> %d、判定 ±%dpx）、発射位置補正 %dpx、場の前方オフセット α %s -> %s' % (
        n, mul, round(640 * mul), round(32 * 640 * mul / 256), dist, a_old, (a18[0]['int2'], a18[0]['int5'])))
    return [(SELF_WAZ, si), (BULLET_WAZ, bi)]


def gf_push(w, log):
    """GF_PUSH: ギガンテックフィールドの場（Tama04 透移植弾303）の全ヒット（場の多段 turn 0・爆発 turn 1）の のけぞり 4 欄の
    横の押し（のけぞり速度 int8 px/F・速度減速率 int9、毎 F int9/100 px/F 減速）を、1 回の押しの距離 v^2/(2a) が x mul になるように変える。
    速度は v x sqrt(mul) を四捨五入（整数）、減速率はその速度で距離が x mul になる値（四捨五入）。縦（吹き飛び規模・重力）・硬直・方向はそのまま。
    別の欄と同じ（int1 != 0）の欄は触らない。"""
    mul = MT.p('GF_PUSH', 'mul')
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'GF_PUSH: Tama04.waz not among the modified files'
    bi, b = _skill(tw, 'ｷﾞｶﾞﾝﾃｯｸﾌｨｰﾙﾄﾞ（透移植弾303）')
    ch = []
    for t, turn in enumerate(b['phasesInfo']):
        hs = _objs(turn, 41)
        assert len(hs) == 1, 'GF_PUSH: turn %d has %d hits' % (t, len(hs))
        for c, d in sorted(_cols(hs[0]).items()):
            if d.get('int1'):
                continue
            v, a = d.get('int8', 0), d.get('int9', 0)
            assert v > 0 and a > 0, 'GF_PUSH: turn %d column %d push %d/%d' % (t, c, v, a)
            v2 = max(1, round(v * mul ** 0.5))
            a2 = max(1, round(a * v2 * v2 / (mul * v * v)))
            d['int8'], d['int9'] = v2, a2
            ch.append('T%d 欄%d %d/%d -> %d/%d（距離 x%.2f）' % (t, c, v, a, v2, a2, (v2 * v2 / a2) / (v * v / a)))
    assert len(ch) == 6, 'GF_PUSH: expected 6 own columns, got %s' % ch
    log.append('GF_PUSH ギガンテックフィールド 横の押し（のけぞり速度/減速率）: ' + ', '.join(ch))
    return [(BULLET_WAZ, bi)]


def drill_face(w, log):
    """DRILL_FACE: ドリルの掘削ターン（攻撃判定 slot 41 のある唯一のターン）の F0 の slot 10 方向増分 0 を rate にし、
    次のターン（引き戻し）の F0 に slot 10 = 0 を置いて追尾を止める。甲 ドリル の書き方（T0 F0 100、技の間ずっと）。"""
    si, s = _skill(w, 'ドリル')
    rate = MT.p('DRILL_FACE', 'rate')
    ts = s['phasesInfo']
    hit_t = [t for t, turn in enumerate(ts) if _objs(turn, 41)]
    assert len(hit_t) == 1, 'DRILL_FACE: drilling turns %s' % hit_t
    t = hit_t[0]; turn = ts[t]
    o10 = _objs(turn, 10)
    assert len(o10) == 1 and o10[0]['startFrame'] == 0 and not o10[0].get('int5'), 'DRILL_FACE: turn %d slot 10 is not the F0 stop' % t
    assert t + 1 < len(ts) and not _objs(ts[t + 1], 10) and not _objs(ts[t + 1], 41), 'DRILL_FACE: turn %d is not the retract turn' % (t + 1)
    j = _end_jump(turn)
    o10[0]['int5'] = rate
    _put_unit(ts[t + 1], _mk_unit(_units(turn, 10)[0], [dict(startFrame=0, endFrame=0, int5=0)]))
    log.append('DRILL_FACE ドリル turn %d（掘削 F0-%d）: slot 10 方向増分 0 -> %d（%.0f°/F で敵へ向く）、turn %d F0 に 0（止める）' % (
        t, j['startFrame'], rate, rate / 10.0, t + 1))
    return si


def tko_tune(w, log):
    """TKO_TUNE: T・K・O
    * 装甲: turn 0 F0 に armor 段階、ほかの装甲イベントは外す（技の終わりまで続く。甲 キリングレイジと同じ置き方）。
    * 偶数ヒット（turn 5）の当たりの未変換は変換側（bfe2bsdx_waz HITREPEAT）で直したので、turn 3 と同じテンプレであることだけ確かめる。
    * 連打のターン（turn 2・4、各 4F）を cut F 短くする。発生（turn 0・1）とそのスローはそのまま。"""
    import copy
    si, s = _skill(w, 'T・K・O')
    ph = s['phasesInfo']
    lv = MT.p('TKO_TUNE', 'armor'); cut = MT.p('TKO_TUNE', 'cut')
    na = 0
    for turn in ph:
        na += _drop(turn, 36)
    tpl = None
    for s2 in w['skillList']:
        for turn in (s2 or {}).get('phasesInfo', []):
            for u in _units(turn, 36):
                tpl = tpl or u
    u = copy.deepcopy(tpl)
    o = copy.deepcopy(u['skillInfoObjectList'][0])
    o.update(int1=0, int2=0, int3=0, int4=lv, startFrame=0, endFrame=0, offset=0)
    u['skillInfoObjectList'] = [o]
    uc = ph[0]['skillUnitCollection']
    uc.insert(next((i for i, x in enumerate(uc) if x['unitQuantity'] > 36), len(uc)), u)
    h3, h5 = _objs(ph[3], 41), _objs(ph[5], 41)
    assert len(h3) == 1 and len(h5) == 1, 'TKO_TUNE: expected one hit in turn 3 and 5'
    a, b = h3[0], h5[0]
    for k in ('minDamage', 'startComboCorrection', 'midComboCorrection', 'endCorrection', 'startFrame', 'endFrame'):
        assert a.get(k) == b.get(k), 'TKO_TUNE: turn 3 / 5 hits differ in %s' % k
    # 偶数ヒットの未変換は変換側で直した（HITREPEAT、原作再現版も）。ここでは同じテンプレから作られていることだけ確かめる。
    assert _power(a) == _power(b) and a.get('chargeDamageRate') == b.get('chargeDamageRate') != 0, \
        'TKO_TUNE: turn 5 hit is not converted like turn 3 (HITREPEAT not applied?)'
    # 11/13: 補正 0（ユーザー）。前のコンボの補正で減らない = 最低値を表示威力（威力 x1.5 切り捨て）に、技終了時補正を end に。
    # 各ヒットの 初段・技中・内部 の補正はもともと 0（確かめる）。
    end = MT.p('TKO_TUNE', 'end')
    hits = [o_ for turn in ph for sl in (41, 42, 43, 44) for o_ in _objs(turn, sl)]
    assert len(hits) == 3, 'TKO_TUNE: expected 3 hits, got %d' % len(hits)
    mins = []
    for h in hits:
        assert h['startComboCorrection'] == h['midComboCorrection'] == h['internalCorrection'] == 0, 'TKO_TUNE: hit adds correction'
        d = int(_power(h) * 1.5)
        assert h['minDamage'] <= d
        mins.append('%d->%d' % (h['minDamage'], d))
        h['minDamage'] = d; h['endCorrection'] = end
    for t in (2, 4):
        turn = ph[t]
        j = _end_jump(turn)
        old = j['startFrame']; new = old - cut
        assert old == 3 and new > 0, 'TKO_TUNE: turn %d is not the 4F punch wind-up' % t
        for u_ in turn['skillUnitCollection']:
            for o_ in u_['skillInfoObjectList']:
                if o_ is j:
                    o_['startFrame'] = o_['endFrame'] = new
                else:
                    assert o_['startFrame'] <= new, 'TKO_TUNE: turn %d has an event after F%d' % (t, new)
                    o_['endFrame'] = min(o_['endFrame'], new)
    log.append('TKO_TUNE T・K・O: 装甲 %d を turn 0 F0 から技の終わりまで（装甲イベント %d 件を置き換え）、'
               '連打 turn 2・4 を 4F -> %dF（2 ヒット 12F -> %dF）。補正 0: 最低値 = 表示威力（%s）、技終了時補正 %d' % (
                   lv, na, 4 - cut, 12 - 2 * cut, '・'.join(mins), end))
    return si


def _power(o):
    p = 0
    for u in o.get('ceventHitUnitList') or []:
        if u.get('unitSlotNum') == 6:
            p = sum(u['data']['bsdxInfoCollectionList'][0]['paramList'])
    return p


def gekka_launch(w, log):
    """GEKKA_LAUNCH: 月華衝の締め（turn 6 の当たり）の のけぞり 4 欄の 吹き飛び規模（int10、浮かせ量）x mul、吹き飛び重力（int11）x grav。"""
    si, s = _skill(w, '月華衝')
    mul, grav = MT.p('GEKKA_LAUNCH', 'mul'), MT.p('GEKKA_LAUNCH', 'grav', 1.0)
    hs = _objs(s['phasesInfo'][6], 41)
    assert len(hs) == 1, 'GEKKA_LAUNCH: turn 6 hit not unique'
    vals = []
    for hu in hs[0]['ceventHitUnitList']:
        if 17 <= hu['unitSlotNum'] <= 20 and hu.get('data'):
            d = hu['data']
            assert d['int10'] > 0 and d['int11'] > 0, 'GEKKA_LAUNCH: 吹き飛び規模 / 重力 %s %s' % (d['int10'], d['int11'])
            v = (d['int10'], d['int11'], int(d['int10'] * mul + 0.5), int(d['int11'] * grav + 0.5))
            d['int10'], d['int11'] = v[2], v[3]
            vals.append(v)
    assert len(vals) == 4 and len(set(vals)) == 1, 'GEKKA_LAUNCH: 4 columns differ %s' % vals
    log.append('GEKKA_LAUNCH 月華衝 turn 6: 吹き飛び規模 %d -> %d、吹き飛び重力 %d -> %d（4 欄）' % (vals[0][0], vals[0][2], vals[0][1], vals[0][3]))
    return si


def tko_downlift(w, log):
    """TKO_DOWNLIFT: T・K・O の最後の一撃（turn 6 の当たり）の ダウン欄（20）を「地上欄と同じ（int1 1）」から自分の値（int1 0）にし、
    吹き飛び規模・重力・バウンド Lv・バウンド速度（int10〜13）を src（クラッシュハンマー）の src_turn の当たりの src_col 欄（地上→地上）から写す。
    停止時間・ノックバック・のけぞり速度・減速率・ダウン時間・のけぞり方向は今の T・K・O の値（地上欄と同じ）のまま。連打（turn 3・5）は触らない。"""
    si, s = _skill(w, 'T・K・O')
    hs = _objs(s['phasesInfo'][6], 41)
    assert len(hs) == 1, 'TKO_DOWNLIFT: turn 6 hit not unique'
    c = _cols(hs[0])
    assert c[20]['int1'] == 1 and c[17]['int1'] == 0, 'TKO_DOWNLIFT: down column is not "same as ground" (%s)' % c[20]['int1']
    for k in ('int2', 'int3', 'int4', 'int7', 'int8', 'int9', 'int10', 'int11', 'int12', 'int13'):
        assert c[20][k] == c[17][k], 'TKO_DOWNLIFT: down / ground columns differ in %s' % k
    _, s2 = _skill(w, MT.p('TKO_DOWNLIFT', 'src'))
    h2 = _objs(s2['phasesInfo'][MT.p('TKO_DOWNLIFT', 'src_turn')], 41)
    assert len(h2) == 1, 'TKO_DOWNLIFT: src hit not unique'
    src = _cols(h2[0])[MT.p('TKO_DOWNLIFT', 'src_col')]
    assert src['int10'] < 0 and src['int12'] > 0, 'TKO_DOWNLIFT: src is not a slam with bounce'
    d = c[20]
    old = tuple(d[k] for k in ('int10', 'int11', 'int12', 'int13'))
    d['int1'] = 0
    for k in ('int10', 'int11', 'int12', 'int13'):
        d[k] = src[k]
    new = tuple(d[k] for k in ('int10', 'int11', 'int12', 'int13'))
    log.append('TKO_DOWNLIFT T・K・O turn 6 ダウン欄: 処理タイプ 1（地上欄と同じ）-> 0、規模/重力/バウンド Lv/速度 %s -> %s（%s turn %d 欄 %d から）' % (
        old, new, MT.p('TKO_DOWNLIFT', 'src'), MT.p('TKO_DOWNLIFT', 'src_turn'), MT.p('TKO_DOWNLIFT', 'src_col')))
    return si


def tko_stage(w, log):
    """TKO_STAGE: T・K・O の最後の一撃（turn 6 = 溜め F0-35 + 当たり F36-37）と、その後の硬直だけに演出を足す（調査記録 76、ユーザー 11/18）。連打（turn 0-5）は触らない。
    * 当たりのヒットエフェクト（サブ 16）を fx_src の fx_turn の当たりから写す（今の最後の一撃はヒットエフェクトなし。連打は Tama02 99 のまま）。
    * 硬直の turn 7 は連打を外したときにも通るので、写しを新ターン（末尾）に作り、turn 6 の終わりだけそこへ飛ばす。新ターンの後は turn 7 と同じく技の終わり。
    * turn 6 と新ターンの全フレーム: 暗転（slot 61、256 -> shade を最初の fade F、最後の fade F で 256 に戻す）、スロー効果（slot 69）= slow、
      透のスロー反映率（slot 70）= self_rate。新ターンの最後の F でスロー 0・反映率 100（IF_STAGE と同じ戻し方）。
      値の前例は 武幻剛乱舞 turn 0（暗転 + スロー 1000・反映率 50）。"""
    si, s = _skill(w, MT.p('TKO_STAGE', 'skill'))
    ph = s['phasesInfo']
    n = len(ph)
    assert n == 8 and s.get('phaseQuantity') == 8 and len(s['skillSuffixList']) == 8, 'TKO_STAGE: expected 8 turns (%d)' % n
    t6, t7 = ph[6], ph[7]
    for t_ in (6, 7):
        assert not any(_objs(ph[t_], k) for k in (61, 68, 69, 70)), 'TKO_STAGE: turn %d already has a screen effect' % t_
    # --- ヒットエフェクト
    hs = _objs(t6, 41)
    assert len(hs) == 1 and hs[0]['startFrame'] == 36, 'TKO_STAGE: turn 6 hit not as expected'
    hl = hs[0]['ceventHitUnitList']
    assert not any(hu['unitSlotNum'] == 16 and hu.get('data') for hu in hl), 'TKO_STAGE: final hit already has a hit effect'
    _, src = _skill(w, MT.p('TKO_STAGE', 'fx_src'))
    sh = _objs(src['phasesInfo'][MT.p('TKO_STAGE', 'fx_turn')], 41)
    assert len(sh) == 1, 'TKO_STAGE: fx source hit not unique'
    fx = [hu for hu in sh[0]['ceventHitUnitList'] if hu['unitSlotNum'] == 16 and hu.get('data')]
    assert len(fx) == 1 and fx[0]['data']['wazFileNo'] == 2, 'TKO_STAGE: fx source has no hit effect'
    fx = copy.deepcopy(fx[0]); fx['data']['offset'] = 0
    hl[:] = [hu for hu in hl if hu['unitSlotNum'] != 16]
    hl.insert(next((i for i, hu in enumerate(hl) if hu['unitSlotNum'] > 16), len(hl)), fx)
    # --- 硬直の写し（新ターン n）
    e6 = _end_jump(t6)
    assert e6['bsdxInfoCollectionList2'][0]['typeList'] == [0, 1] and e6['bsdxInfoCollectionList2'][0]['paramList'] == [7], 'TKO_STAGE: turn 6 does not end into turn 7'
    e7 = _end_jump(t7)
    assert e7['bsdxInfoCollectionList2'][0]['typeList'] == [0, 2], 'TKO_STAGE: turn 7 does not end the skill'
    t8 = copy.deepcopy(t7)
    for u in t8['skillUnitCollection']:
        u['skillInfoUnknownList'] = []
        for o in u['skillInfoObjectList']:
            o['offset'] = 0
    ph.append(t8)
    s['phaseQuantity'] = len(ph)
    x = copy.deepcopy(s['skillSuffixList'][-1]); x['int1'] = n; s['skillSuffixList'].append(x)
    e6['bsdxInfoCollectionList2'][0]['paramList'] = [n]
    # --- 暗転・スロー
    slow, rate, shade, fade = (MT.p('TKO_STAGE', k) for k in ('slow', 'self_rate', 'shade', 'fade'))
    tpl = {k: _unit_tpl([w], k) for k in (61, 69, 70)}
    L6 = _end_jump(t6)['startFrame'] + 1
    L8 = _end_jump(t8)['startFrame'] + 1
    assert L6 > fade and L8 > fade + 1, 'TKO_STAGE: turns too short'

    def dark(a, b_, f0, f1):
        return dict(int1=0x10000000, int2=a, int3=0, int4=0, int5=0, int6=b_, int7=0, int8=0, int9=0, startFrame=f0, endFrame=f1)

    def val(v0, v1, f0, f1, mode=0):
        return dict(int1=mode, int2=v0, int3=0, int4=v1, startFrame=f0, endFrame=f1)

    _put_unit(t6, _mk_unit(tpl[61], [dark(256, shade, 0, fade - 1), dark(shade, shade, fade, L6 - 1)]))
    _put_unit(t6, _mk_unit(tpl[69], [val(slow, slow, 0, L6 - 1)]))
    rate_f = MT.p('TKO_STAGE', 'rate_f', 0)    # 11/19（ユーザー）: 反映率を turn 6 の F0 ではなく rate_f で設定（それまでは反映率を変えない）
    assert 0 <= rate_f < L6, 'TKO_STAGE: rate_f %s outside turn 6' % rate_f
    _put_unit(t6, _mk_unit(tpl[70], [val(rate, rate, rate_f, rate_f)]))
    _put_unit(t8, _mk_unit(tpl[61], [dark(shade, shade, 0, L8 - fade - 1), dark(shade, 256, L8 - fade, L8 - 1)]))
    _put_unit(t8, _mk_unit(tpl[69], [val(slow, slow, 0, L8 - 2), val(0, 0, L8 - 1, L8 - 1)]))
    _put_unit(t8, _mk_unit(tpl[70], [val(rate, rate, 0, 0), val(100, 100, L8 - 1, L8 - 1)]))
    log.append('TKO_STAGE %s: 最後の一撃（turn 6 F36）にヒットエフェクト（%s turn %d と同じ Tama02 %d）、turn 6（%dF）-> 新 turn %d（turn 7 の写し %dF）-> 技の終わり。'
               'turn 6・%d に暗転 256 -> %d（%dF で暗く、最後 %dF で戻す）、スロー %d・透の反映率 %d（新 turn %d の最後 F で 0 / 100）。外したときの turn 7 は今のまま'
               % (s['skillNameJapanese'], MT.p('TKO_STAGE', 'fx_src'), MT.p('TKO_STAGE', 'fx_turn'), fx['data']['wazSequenceNo'], L6, n, L8,
                  n, shade, fade, fade, slow, rate, n))
    return si


# SPM_FILE, EFT_FILE: the mech's spm / effect spm (set by apply())


def _bits(pg):
    """page hitRects in hitFlag bit order -> {bit: hitRect dict}"""
    bs = [b for b in range(32) if pg['hitFlag'] >> b & 1]
    assert len(bs) == len(pg['hitRects']), 'IF_RECT: hitFlag / hitRects mismatch'
    return {b: h for b, h in zip(bs, pg['hitRects'])}


def _to_column(h, pg, log_, low=0):
    """hitRect h -> 床面の矩形はそのまま、高さを unk0 7（高さ範囲付き）で low から絵の上端（-pageRect.top）まで。"""
    r = h['hitRect']; old = (h['unk0'], r['left'], r['top'], r['right'], r['bottom'], h['unk1'], h['unk2'])
    assert h['unk0'] in (1, 2, 3) and h['unk1'] == h['unk2'] == 0 and r['right'] - r['left'] <= 32, 'IF_RECT: rect %s' % (old,)
    top = -pg['pageRect']['top']; assert 100 <= top <= 400 and 0 <= low < top - 10, 'IF_RECT: page top %d / low %d' % (top, low)
    h['unk0'], h['unk1'], h['unk2'] = 7, low, top
    log_.append('区分 %d -> 区分 7 高さ %d..%d（床面 %d,%d-%d,%d はそのまま）' % (old[0], low, top, r['left'], r['top'], r['right'], r['bottom']))


def if_rect(w, log):
    """IF_RECT: インペリアルファイナルの攻撃判定を絵の大きさに（spm のページの判定矩形）。
    判定矩形は床面（横 x 奥行き）で、高さは unk0 の区分（1 下段 / 2 中段 / 3 上段）か、unk0 7 のときの unk1..unk2（高さの範囲）で決まる
    （甲 kou.spm: どの区分も矩形の縦の中心がほぼ 0、胴体の箱は {2, 0..72}）。
    * 本体の当たり（turn 2、威力 1800）: 原作 SPR slot 19/20 の 28x28、区分 3（上段）。この anim はインペリアルストライクの当たりと
      共用で、絵も同じなので両方まとめて、攻撃ビット（0-10）の高さを剣の根元（params.sword_low）から絵の上端（剣の先）まで（区分 7）
      にする。床面はそのまま（ユーザー 11/12: 平面は広げず高さだけ。ストライクとファイナルで同じ判定に。11/13: 剣の根元から先端まで、
      背の低い敵・ダウン中の敵に当たらなくてよい）。
    * 落雷の弾（Tama04 ｲﾝﾍﾟﾘｱﾙﾌｧｲﾅﾙ用落雷、この技だけが使う）: Effect の当たり矩形（SPR 2 -> bit 0、区分 2）の高さを雷の柱の高さに。
      弾の拡大縮小（slot 1）が高さにも掛かるかは未確認。"""
    si, s = _skill(w, 'インペリアルファイナル')
    spm, eft = _NEW.get(SPM_FILE), _NEW.get(EFT_FILE)
    assert spm and eft, 'IF_RECT: spm files not given to apply()'
    R = lambda q: (q['left'], q['top'], q['right'], q['bottom'])
    hits = _objs(s['phasesInfo'][2], 41)
    assert len(hits) == 1 and hits[0]['endFrame'] == 13, 'IF_RECT: turn 2 hit'
    ags = {o['actionGroupNumber'] for o in _objs(s['phasesInfo'][2], 0) if o['spmFileSequence'] == -1}
    assert len(ags) == 1, 'IF_RECT: turn 2 sprite anims %s' % ags
    ag = ags.pop()
    an = spm['animData'][ag]
    assert an['numPat'] == 1, 'IF_RECT: mech anim %d has %d pats' % (ag, an['numPat'])
    base = an['patData'][0]['pageNo'][0]
    # 同じ anim（BFE 226）をインペリアルストライクの当たり（turn 1）も使う。絵が同じなので判定も同じにする（ユーザー 11/12）。
    users = sorted({(x['skillNameJapanese'], ti) for x in w['skillList'] for ti, t in enumerate((x or {}).get('phasesInfo', []))
                    for o in _objs(t, 0) if o.get('spmFileSequence') == -1 and o['actionGroupNumber'] == ag})
    assert users == [('インペリアルストライク', 1), ('インペリアルファイナル', 2)], 'IF_RECT: anim %d users %s' % (ag, users)
    for i, a_ in enumerate(spm['animData']):
        for p_ in a_['patData']:
            assert i == ag or not (base <= p_['pageNo'][0] < base + 8), 'IF_RECT: pages %d.. shared with anim %d' % (base, i)
    pages, done = [], []
    for d in range(8):
        pg = spm['pageData'][base + d]
        if not pg['hitFlag']:
            continue
        bm = _bits(pg); atk = [b for b in bm if b <= 10]
        assert atk and len({R(bm[b]['hitRect']) for b in atk}) == 1, 'IF_RECT: page %d attack rects %s' % (base + d, atk)
        l_ = []
        for b in atk:
            _to_column(bm[b], pg, l_, MT.p('IF_RECT', 'sword_low'))
        pages.append(base + d); done.append(l_[0])
    assert len(pages) == 5, 'IF_RECT: mech pages with rects %s' % pages
    t4 = _NEW[BULLET_WAZ]
    bi = [i for i, x in enumerate(t4['skillList']) if x and x.get('skillNameJapanese') == 'ｲﾝﾍﾟﾘｱﾙﾌｧｲﾅﾙ用落雷（透移植弾392）']
    assert len(bi) == 1, 'IF_RECT: bolt bullet %s' % bi
    bi = bi[0]
    bas = {o['actionGroupNumber'] for t in t4['skillList'][bi]['phasesInfo'] for o in _objs(t, 0) if o['spmFileSequence'] == EFT_SLOT}
    assert len(bas) == 1, 'IF_RECT: bolt anims %s' % bas
    ba = bas.pop()
    for f_, w_ in _NEW.items():
        if f_.endswith('.waz'):
            for j, x in enumerate(w_['skillList']):
                for t in (x or {}).get('phasesInfo', []):
                    for o in _objs(t, 0):
                        assert (f_, j) == (BULLET_WAZ, bi) or not (o.get('spmFileSequence') == EFT_SLOT and o.get('actionGroupNumber') == ba), \
                            'IF_RECT: bolt anim %d also used by %s %d' % (ba, f_, j)
    epages, edone = [], []
    bpg = [p_['pageNo'][0] for p_ in eft['animData'][ba]['patData']]
    for i, a_ in enumerate(eft['animData']):
        assert i == ba or not set(p_['pageNo'][0] for p_ in a_['patData']) & set(bpg), 'IF_RECT: bolt pages shared with eft anim %d' % i
    for pn in bpg:
        pg = eft['pageData'][pn]
        bm = _bits(pg) if pg['hitFlag'] else {}
        if 0 not in bm:
            continue
        l_ = []
        _to_column(bm[0], pg, l_, MT.p('IF_RECT', 'sword_low')); epages.append(pn); edone.append(l_[0])   # 11/13: 落雷も同じ下端
    assert len(epages) == 8, 'IF_RECT: bolt pages with a hit rect %s' % epages
    log.append('IF_RECT インペリアルファイナル・ストライク: 本体の当たり（共用の anim %d、ページ %s）の攻撃判定の高さを剣の根元から先まで（例 %s）。'
               '落雷（eft anim %d、ページ %d-%d）の判定を雷の柱の高さに（例 %s）' % (
        ag, '・'.join(map(str, pages)), done[2] if len(done) > 2 else done[0], ba, epages[0], epages[-1], edone[4]))
    # spm の touched: ('a', anim) / ('p', page)（build_phase3b I2 がそれ以外の一致を確かめる）
    return [(SPM_FILE, ('p', p_)) for p_ in pages] + [(EFT_FILE, ('p', p_)) for p_ in epages]


def _zero_offsets(o):
    if isinstance(o, dict):
        if 'offset' in o:
            o['offset'] = 0
        for v in o.values():
            _zero_offsets(v)
    elif isinstance(o, list):
        for v in o:
            _zero_offsets(v)


def t150_volleys(w, log):
    """T150_VOLLEYS: ガトリング T-150 の射撃ターン（turn 2、4F ごとに 3 発 x 30 回）を volleys 回まで延ばす。
    発射（slot 48、Tama04 透移植弾10）とスプライト（slot 0、2 コマの交互）を同じ 4F 刻みで足し、速度（slot 18）の終わりと
    ターン末の無条件ジャンプを後ろへずらす。"""
    import copy
    si, s = _skill(w, 'ガトリング T-150')
    vol = MT.p('T150_VOLLEYS', 'volleys')
    turn = s['phasesInfo'][2]
    assert _NEW.get(BULLET_WAZ) is not None, 'T150_VOLLEYS: Tama04.waz not among the modified files'
    bi, _ = _skill(_NEW[BULLET_WAZ], 'ガトリングガン Lv2（透移植弾10）')

    def _tama(o):
        d = [x['data'] for x in o['ceventEffectUnitList'] if x['unitSlotNum'] == 3 and x.get('data')]
        return (d[0]['wazFileNo'], d[0]['wazSequenceNo']) if d else None

    fu = _units(turn, 48); su = _units(turn, 0)
    assert len(fu) == 1 and len(su) == 1, 'T150_VOLLEYS: slot 0 / 48 units %d / %d' % (len(su), len(fu))
    fires = [o for o in fu[0]['skillInfoObjectList'] if _tama(o) == (4, bi)]
    step, n0 = 4, len(fires)
    assert n0 == 30 and [o['startFrame'] for o in fires] == list(range(0, 120, step)), 'T150_VOLLEYS: fires %s' % [o['startFrame'] for o in fires]
    per = MT.p('T150_VOLLEYS', 'per_volley')
    for o in fires:
        c = [x['data'] for x in o['ceventEffectUnitList'] if x['unitSlotNum'] == 4 and x.get('data')]
        assert len(c) == 1 and c[0]['int2'] == 3 and c[0]['int5'] == 3, 'T150_VOLLEYS: not 3 bullets per volley'
        c[0]['int2'] = c[0]['int5'] = per          # 11/13: 同時発射数 3 -> per（効果音が F0 の 1 回なのでターンは延ばさない）
    spr = su[0]['skillInfoObjectList']
    assert [(o['startFrame'], o['endFrame'], o['actionNumber']) for o in spr] == [(f, f + 3, f // step % 2) for f in range(0, 120, step)], \
        'T150_VOLLEYS: sprite frames'
    j = _end_jump(turn)
    end0 = j['startFrame']
    assert end0 == 119, 'T150_VOLLEYS: turn end F%d' % end0
    v18 = [o for o in _objs(turn, 18) if o['endFrame'] == end0]
    assert len(v18) == 1 and v18[0]['startFrame'] == 1, 'T150_VOLLEYS: slot 18 hold'
    assert vol >= n0
    end1 = end0 + (vol - n0) * step
    for o in _objs(turn, 18) + _objs(turn, 15) + _objs(turn, 19) + _objs(turn, 21) + _objs(turn, 47) + _objs(turn, 52):
        assert o is v18[0] or o['endFrame'] == 0, 'T150_VOLLEYS: other event runs to F%d' % o['endFrame']
    for k in range(n0, vol):
        f = k * step
        a = copy.deepcopy(fires[-1]); _zero_offsets(a)
        a['startFrame'] = a['endFrame'] = f
        fu[0]['skillInfoObjectList'].append(a)
        b = copy.deepcopy(spr[k % 2]); _zero_offsets(b)      # 2 コマ（action 0 / 1）の交互を続ける
        b['startFrame'], b['endFrame'] = f, f + 3
        spr.append(b)
    v18[0]['endFrame'] = end1
    j['startFrame'] = j['endFrame'] = end1
    log.append('T150_VOLLEYS ガトリング T-150 turn 2: 発射 %d 回 x3 発（%d 発）-> %d 回 x%d 発（%d 発）、ターン末 F%d -> F%d' % (
        n0, n0 * 3, vol, per, vol * per, end0, end1))
    return si


def _fire_users(name_by_file):
    """{(file, bullet index)} -> 発射している (file, 技名) の集合（Tooru.waz と変更対象の弾ファイル）。"""
    out = {}
    for f_, w_ in _NEW.items():
        if not f_.endswith('.waz'):
            continue
        for x in w_['skillList']:
            for t in (x or {}).get('phasesInfo', []):
                for o in _objs(t, 48):
                    for e in o['ceventEffectUnitList']:
                        d = e.get('data')
                        if e['unitSlotNum'] == 3 and d:
                            out.setdefault((d['wazFileNo'], d['wazSequenceNo']), set()).add((f_, x['skillNameJapanese']))
    return out


def _cols(h):
    """当たり h の のけぞり 4 欄 {欄: data}"""
    return {hu['unitSlotNum']: hu['data'] for hu in h['ceventHitUnitList'] if 17 <= hu['unitSlotNum'] <= 20 and hu.get('data')}


def sg_airgrav(w, log):
    """SG_AIRGRAV: ショットガン・ジェノサイド・ショットガンの弾の対メカの当たり（slot 41）の 空中欄 18 の 吹き飛び重力（int11）を rate に。"""
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'SG_AIRGRAV: Tama04.waz not among the modified files'
    r = MT.p('SG_AIRGRAV', 'rate')
    users = _fire_users(None)
    out, ch = [], []
    for name in MT.p('SG_AIRGRAV', 'bullets'):
        bi, b = _skill(tw, name)
        u = {n for _, n in users.get((4, bi), ())}
        assert u and u <= {'ショットガン', 'ジェノサイド・ショットガン'}, 'SG_AIRGRAV: %s fired by %s' % (name, u)
        for t, turn in enumerate(b['phasesInfo']):
            for h in _objs(turn, 41):
                c = _cols(h)
                assert 18 in c and not c[18].get('int1'), 'SG_AIRGRAV: %s turn %d air column is not its own' % (name, t)
                ch.append('%s turn %d 欄 18 %d -> %d' % (name, t, c[18].get('int11', 0), r))
                c[18]['int11'] = r
        out.append((BULLET_WAZ, bi))
    assert len(ch) == 2, 'SG_AIRGRAV: expected one mech hit per bullet, got %s' % ch
    log.append('SG_AIRGRAV 吹き飛び重力（空中欄）: ' + ', '.join(ch))
    return out


def bu_fall(w, log):
    """BU_FALL: ブーストアッパーの turn 2（上昇、ターン末で技終了）の後に、src（メガ・ブーストアッパー）turn src_turn の落下ターンを写して turn 3 に。
    turn 2 のターン末を「技終了」から「turn 3 へ」に変える。落下ターンは 着地していたら → 技終了（F6 から）、ターン末も技終了。
    armor_off: 落下ターンの F0 に 装甲 0（slot 36）。原作の各段の「装甲 0」は段の切り替わりの後のフレームで実行されず、装甲 3 が落下まで残っていた（11/19）。"""
    si, s = _skill(w, 'ブーストアッパー')
    _add_fall(w, log, 'BU_FALL', 'ブーストアッパー', si, s, [2], 2, MT.p('BU_FALL', 'armor_off', False))
    return si


def jk_fall(w, log):
    """JK_FALL: ジャンピングニーの turn 2（外れたときの終わり）・turn 3（当たったときの終わり、長さ 0）の後に BU_FALL と同じ落下ターンを turn 4 として足す。"""
    si, s = _skill(w, 'ジャンピングニー')
    ph = s['phasesInfo']
    assert len(ph) == 4 and not _objs(ph[3], 41) and not _objs(ph[2], 41), 'JK_FALL: expected 4 turns, no hits in turn 2 / 3'
    assert not any(_objs(t, 36) for t in ph), 'JK_FALL: ジャンピングニー has armor events now (check armor in the fall turn)'
    _add_fall(w, log, 'JK_FALL', 'ジャンピングニー', si, s, MT.p('JK_FALL', 'from_turns'), 2, False)
    return si


def _add_fall(w, log, tid, name, si, s, from_turns, slot24_turn, armor_off):
    """from_turns の各ターン末の「技終了」を、末尾に足す落下ターン（MT.p(tid, 'src') の src_turn の写し）へのジャンプに変える。
    落下ターンの slot 24 は slot24_turn の値、slot 30 は 0。armor_off なら落下ターンの F0 に 装甲 0。"""
    ph = s['phasesInfo']; n = len(ph)
    assert s.get('phaseQuantity', n) == n and len(s['skillSuffixList']) == n, '%s: unexpected turn count' % tid
    ends = []
    for t in from_turns:
        j = _end_jump(ph[t])
        assert j['bsdxInfoCollectionList2'][0]['typeList'] == [0, 2], '%s: turn %d does not end the skill' % (tid, t)
        ends.append((t, j))
    _, m = _skill(w, MT.p(tid, 'src'))
    src = m['phasesInfo'][MT.p(tid, 'src_turn')]
    # 11/18 DASHRATE: 変換器が全ターンの F0 に slot 24 / 30（ﾍﾞｸﾄﾙ補正率：移動 / ｻｰﾁﾀﾞｯｼｭ）を置くようになった
    assert {u['unitQuantity'] for u in src['skillUnitCollection']} == {0, 18, 19, 21, 24, 30, 71}, 'BU_FALL: source turn slots'
    j71 = _objs(src, 71)
    assert len(j71) == 2 and all(o['bsdxInfoCollectionList2'][0]['typeList'] == [0, 2] for o in j71) and \
        any(c['typeList'] == [2, 7, 16] and not c['int2'] for o in j71 for c in o['bsdxInfoCollectionList1']), \
        'BU_FALL: source turn is not 着地していたら -> 技終了'
    assert min(o.get('int5', 0) for o in _objs(src, 19)) < 0, 'BU_FALL: source turn does not fall'
    fall = copy.deepcopy(src); _zero_offsets(fall)
    # 落下ターンの slot 24 / 30 は写し元（メガ・ブーストアッパー）の段の値ではなく、ブーストアッパー turn 2 の続き:
    # 24 = turn 2 と同じ（原作 BU 最終段の「移」）、30 = 0（原作の S ダッシュの勢いは BU の 3 段の間に止まっている、調査記録 77）
    for u in fall['skillUnitCollection']:
        if u['unitQuantity'] == 24:
            u['skillInfoObjectList'] = copy.deepcopy(_objs(ph[slot24_turn], 24)); _zero_offsets(u['skillInfoObjectList'])
            assert u['skillInfoObjectList'], '%s: turn %d has no slot 24' % (tid, slot24_turn)
        elif u['unitQuantity'] == 30:
            o30 = _objs(fall, 30)
            assert len(o30) == 1, 'BU_FALL: source slot 30 %d events' % len(o30)
            o30[0].update(int1=0, int2=0, int3=0, int4=0, startFrame=0, endFrame=0)
            u['skillInfoObjectList'] = o30
    note = ''
    if armor_off:
        # 装甲 0 のイベント: この技の装甲（slot 36）の単位を写して F0 に 装甲 0 を 1 つ
        tpl = [u for t in ph for u in _units(t, 36)]
        assert tpl, '%s: no slot 36 in %s to copy for armor_off' % (tid, name)
        assert any(o.get('int4', 0) > 0 for t in ph for o in _objs(t, 36)), '%s: %s has no armor to switch off' % (tid, name)
        u36 = copy.deepcopy(tpl[0]); o = copy.deepcopy(u36['skillInfoObjectList'][0])
        o.update(int1=0, int2=0, int3=0, int4=0, startFrame=0, endFrame=0, offset=0)
        u36['skillInfoObjectList'] = [o]
        uc = fall['skillUnitCollection']
        k = next((i for i, x_ in enumerate(uc) if x_['unitQuantity'] > 36), len(uc))
        uc.insert(k, u36)
        note = '、F0 に 装甲 0'
    ph.append(fall)
    s['phaseQuantity'] = n + 1
    x = copy.deepcopy(s['skillSuffixList'][-1]); x['int1'] = n; s['skillSuffixList'].append(x)
    tgt = copy.deepcopy(_end_jump(ph[1])['bsdxInfoCollectionList2'][0])     # turn 1 -> turn 2 の「ターンジャンプ→指定」
    assert tgt['typeList'] == [0, 1]
    tgt['paramList'] = [n]
    for _t, j in ends:
        j['bsdxInfoCollectionList2'] = [copy.deepcopy(tgt)]
    land = [o['startFrame'] for o in j71 if o['bsdxInfoCollectionList1'][0]['typeList'] == [2, 7, 16]][0]
    log.append('%s %s: %s を 技終了 -> turn %d（%s turn %d の落下を写した %dF のターン、F%d から 着地していたら -> 技終了%s）' % (
        tid, name, '・'.join('turn %d の終わり F%d' % (t, j['startFrame']) for t, j in ends), n,
        MT.p(tid, 'src'), MT.p(tid, 'src_turn'), _end_jump(fall)['startFrame'] + 1, land, note))


def dsaber_airgrav(w, log):
    """DSABER_AIRGRAV: ダブルセイバー 1 段目（turn）の当たりの 空中欄（18、もともと自分の値）の 吹き飛び重力 int11 を rate に。"""
    si, s = _skill(w, 'ダブルセイバー')
    t = MT.p('DSABER_AIRGRAV', 'turn'); r = MT.p('DSABER_AIRGRAV', 'rate')
    hs = _objs(s['phasesInfo'][t], 41)
    assert len(hs) == 1, 'DSABER_AIRGRAV: turn %d hit not unique' % t
    assert not any(_objs(x, 41) for x in s['phasesInfo'][1:t]), 'DSABER_AIRGRAV: turn %d is not the first hit' % t
    c = _cols(hs[0])
    assert c[18]['int1'] == 0, 'DSABER_AIRGRAV: air column is not its own'
    old = c[18]['int11']
    c[18]['int11'] = r
    log.append('DSABER_AIRGRAV ダブルセイバー turn %d 空中欄: 吹き飛び重力 %d -> %d' % (t, old, r))
    return si


def galaxy_airrise(w, log):
    """GALAXY_AIRRISE: ギャラクティックストライクの turn 0 の分岐（着地していたら -> turn 6 = BFE ph0 の地上版、ほか -> turn 3 急降下）をやめ、
    無条件で turn 6 へ（turn 6 -> 1 飛び上がり -> 2 -> 3 急降下、地上版と同じ）。"""
    si, s = _skill(w, 'ギャラクティックストライク')
    ph = s['phasesInfo']
    t0 = ph[0]
    d = _end_jump(t0)
    assert d['startFrame'] == 0 and d['bsdxInfoCollectionList2'][0]['paramList'] == [3], 'GALAXY_AIRRISE: turn 0 default is not -> 3'
    land = [o for o in _objs(t0, 71) if o is not d]
    assert len(land) == 1 and land[0]['bsdxInfoCollectionList1'][0]['typeList'] == [2, 7, 16] and \
        land[0]['bsdxInfoCollectionList2'][0]['paramList'] == [6], 'GALAXY_AIRRISE: turn 0 ground dispatch'
    assert _end_jump(ph[6])['bsdxInfoCollectionList2'][0]['paramList'] == [1], 'GALAXY_AIRRISE: turn 6 does not go to the rise'
    assert _objs(ph[1], 19)[0]['int5'] > 0, 'GALAXY_AIRRISE: turn 1 is not the rise'
    for u in _units(t0, 71):
        u['skillInfoObjectList'] = [o for o in u['skillInfoObjectList'] if o is not land[0]]
    d['bsdxInfoCollectionList2'][0]['paramList'] = [6]
    log.append('GALAXY_AIRRISE ギャラクティックストライク: turn 0 の「着地していたら -> turn 6、ほか -> turn 3」を 無条件 -> turn 6 に（空中でも 6 -> 1 飛び上がり -> 2 -> 3）')
    return si


def galaxy_release(w, log):
    """GALAXY_RELEASE: ギャラクティックストライク turn 1（飛び上がり）に「攻撃キーが離されていたら -> turn 2」を足す。
    条件は Term 入力 [2,4,3]（攻撃キーが離されていたら、ATTACKKEY_OFF2）。村正 臥竜 turn 1 と同じ形（flag 1、[0,1] ターンジャンプ→指定）。
    turn 1 の既存の 2 つ（F1- 標的との距離 10 以下 -> 2、ターン末 -> 2）はそのまま。turn 1 へは turn 6 から入る（GALAXY_AIRRISE なら空中でも）。"""
    import copy
    si, s = _skill(w, 'ギャラクティックストライク')
    t1 = s['phasesInfo'][1]
    assert _objs(t1, 19)[0]['int5'] > 0, 'GALAXY_RELEASE: turn 1 is not the rise'
    end = _end_jump(t1)
    assert end['bsdxInfoCollectionList2'][0]['typeList'] == [0, 1] and end['bsdxInfoCollectionList2'][0]['paramList'] == [2],         'GALAXY_RELEASE: turn 1 does not end into turn 2'
    j71 = _objs(t1, 71)
    assert len(j71) == 2 and not any(c['typeList'][:2] == [2, 4] for o in j71 for c in o['bsdxInfoCollectionList1']),         'GALAXY_RELEASE: turn 1 jumps changed'
    st = MT.p('GALAXY_RELEASE', 'start')
    assert 0 <= st < end['startFrame']
    rel = copy.deepcopy(end)
    rel['bsdxInfoCollectionList1'] = [dict(int1=0, typeList=[2, 4, 3], paramList=[], intList3=[], intList4=[], int2=0)]
    rel['startFrame'], rel['endFrame'] = st, end['startFrame']
    rel['offset'] = 0
    u = _units(t1, 71)[0]
    u['skillInfoObjectList'].insert(u['skillInfoObjectList'].index(end), rel)
    log.append('GALAXY_RELEASE ギャラクティックストライク turn 1: F%d-%d に「攻撃キーが離されていたら -> turn 2」を追加（ターン末 F%d -> turn 2 はそのまま）' % (
        st, end['startFrame'], end['startFrame']))
    return si


def galaxy_divespeed(w, log):
    """GALAXY_DIVESPEED: ギャラクティックストライク turn 3（急降下）の from_frame 以降の slot 19（一定の下降速度、LANDHOLDV で着地まで保持）を speed に。"""
    si, s = _skill(w, 'ギャラクティックストライク')
    t3 = s['phasesInfo'][3]
    assert _objs(t3, 41), 'GALAXY_DIVESPEED: turn 3 is not the dive'
    j = _objs(t3, 71)
    assert any(c['typeList'] == [2, 7, 16] for o in j for c in o['bsdxInfoCollectionList1']), 'GALAXY_DIVESPEED: turn 3 has no landing jump'
    f0, sp = MT.p('GALAXY_DIVESPEED', 'from_frame'), MT.p('GALAXY_DIVESPEED', 'speed')
    tail = [o for o in _objs(t3, 19) if o['startFrame'] >= f0]
    assert tail and all(o['int2'] == o['int5'] == -10 and o['int1'] == 0 for o in tail), 'GALAXY_DIVESPEED: turn 3 tail is not -10'
    assert all(o['startFrame'] < f0 and o['int5'] < 0 for o in _objs(t3, 19) if o not in tail)
    for o in tail:
        o['int2'] = o['int5'] = sp
    log.append('GALAXY_DIVESPEED ギャラクティックストライク turn 3: %s の下降速度 -10 -> %d px/F（F0-%d の加速はそのまま）' % (
        ', '.join('F%d-%d' % (o['startFrame'], o['endFrame']) for o in tail), sp, f0 - 1))
    return si


def _rise_px(objs, n):
    """turn の slot 19（重力 0）の F0..n-1 の上昇量 px。イベントは int2 -> int5 を startFrame..endFrame で直線に、次のイベントまでは最後の値を保持。"""
    v = [None] * n
    for o in sorted(objs, key=lambda o: o['startFrame']):
        s, e = o['startFrame'], max(o['startFrame'], o['endFrame'])
        for f in range(s, n):
            v[f] = o['int2'] + (o['int5'] - o['int2']) * (min(f, e) - s) / max(1, e - s)
    return sum(x or 0 for x in v)


def galaxy_rise(w, log):
    """GALAXY_RISE: ギャラクティックストライク turn 1（飛び上がり）の slot 19 の速度を一律 k 倍（四捨五入）にして、押しっぱなしの上昇量を apex px に（apex None なら高さはそのまま）。slot 18 の前進は h_scale 倍。
    フレーム数・横速度・ターン構成・GALAXY_RELEASE の「離したら turn 2」はそのまま。"""
    si, s = _skill(w, 'ギャラクティックストライク')
    t1 = s['phasesInfo'][1]
    ev = _objs(t1, 19)
    g = _objs(t1, 21)
    assert ev and all(o['int5'] > 0 and o['int1'] == 0 for o in ev), 'GALAXY_RISE: turn 1 is not the rise'
    assert len(g) == 1 and not g[0].get('int5'), 'GALAXY_RISE: turn 1 gravity is not 0'
    n = _end_jump(t1)['startFrame'] + 1
    old = _rise_px(ev, n)
    assert abs(old - 272) < 1, 'GALAXY_RISE: turn 1 rise %.1f px (expected 272)' % old
    ap = MT.p('GALAXY_RISE', 'apex')
    if ap is not None:     # None = 高さは原作再現版のまま（11/22 ユーザー）
        k = ap / old
        before = ['%d->%d' % (o['int2'], o['int5']) for o in ev]
        for o in ev:
            o['int2'], o['int5'] = int(o['int2'] * k + 0.5), int(o['int5'] * k + 0.5)
        new = _rise_px(ev, n)
        log.append('GALAXY_RISE ギャラクティックストライク turn 1（%dF）: slot 19 x%.3f %s -> %s、上昇量 %.0f -> %.0f px' % (
            n, k, ', '.join(before), ', '.join('%d->%d' % (o['int2'], o['int5']) for o in ev), old, new))
    hs = MT.p('GALAXY_RISE', 'h_scale')
    if hs is not None:
        h = _objs(t1, 18)
        assert len(h) == 1 and (h[0]['int2'], h[0]['int5'], h[0]['int1']) == (12, 7, 0) and h[0]['startFrame'] == 0 and h[0]['endFrame'] == n - 1,             'GALAXY_RISE: turn 1 forward speed is not 12 -> 7 over the turn'
        o = h[0]; d0 = _rise_px(h, n)
        o['int2'], o['int5'] = int(o['int2'] * hs + 0.5), int(o['int5'] * hs + 0.5)
        log.append('GALAXY_RISE ギャラクティックストライク turn 1: slot 18 前進 x%.2f 12->7 -> %d->%d px/F、前進 %.0f -> %.0f px' % (
            hs, o['int2'], o['int5'], d0, _rise_px(h, n)))
    return si


def dsaber_launch(w, log):
    """DSABER_LAUNCH: ダブルセイバー 2 段目（turn 4）の当たりの のけぞり 4 欄を 3 段目（turn 6）の欄の写しにする（ヒットストップ等の当たりの値はそのまま）。"""
    import copy
    si, s = _skill(w, 'ダブルセイバー')
    ph = s['phasesInfo']
    a, b = _objs(ph[MT.p('DSABER_LAUNCH', 'turn')], 41), _objs(ph[MT.p('DSABER_LAUNCH', 'src_turn')], 41)
    assert len(a) == 1 and len(b) == 1, 'DSABER_LAUNCH: hits'
    ca, cb = _cols(a[0]), _cols(b[0])
    assert set(ca) == set(cb) == {17, 18, 19, 20} and cb[17].get('int10', 0) > 0 and not ca[17].get('int10'), 'DSABER_LAUNCH: columns'
    old = (ca[17].get('int3', 0), ca[17].get('int4', 0), ca[17].get('int8', 0), ca[17].get('int9', 0), ca[17].get('int10', 0), ca[17].get('int11', 0))
    for hu in a[0]['ceventHitUnitList']:
        if hu['unitSlotNum'] in cb:
            off = hu['data'].get('offset', 0)
            hu['data'] = copy.deepcopy(cb[hu['unitSlotNum']]); _zero_offsets(hu['data']); hu['data']['offset'] = off
    # 11/14（ユーザー）: 横方向（ノックバック int3・int4、のけぞり速度 int8、減速率 int9）は 1 段目（h_turn）と同じ、
    # 高さは 3 段目の height 倍（吹き飛び規模 int10 = 縦の初速、重力はそのままなので 高さ ∝ int10^2 → int10 x sqrt(height)）
    ht, hgt = MT.p('DSABER_LAUNCH', 'h_turn'), MT.p('DSABER_LAUNCH', 'height')
    if ht is not None:
        c1 = _cols(_objs(ph[ht], 41)[0])
        for hu in a[0]['ceventHitUnitList']:
            c = hu['unitSlotNum']
            if c in c1 and not hu['data'].get('int1'):
                assert not c1[c].get('int1'), 'DSABER_LAUNCH: turn %d column %d is a reference' % (ht, c)
                for x in ('int3', 'int4', 'int8', 'int9'):
                    hu['data'][x] = c1[c].get(x, 0)
                if hgt is not None:
                    hu['data']['int10'] = round(hu['data'].get('int10', 0) * hgt ** 0.5)
    ca = _cols(a[0])
    new = (ca[17].get('int3', 0), ca[17].get('int4', 0), ca[17].get('int8', 0), ca[17].get('int9', 0), ca[17].get('int10', 0), ca[17].get('int11', 0))
    log.append('DSABER_LAUNCH ダブルセイバー turn %d: のけぞり 4 欄を turn %d と同じに（地上欄 ノックバック/のけぞり速度/減速率/吹き飛び規模/重力 %s -> %s）、'
               'ヒットストップ %s/%s はそのまま' % (MT.p('DSABER_LAUNCH', 'turn'), MT.p('DSABER_LAUNCH', 'src_turn'), old, new, a[0].get('int15'), a[0].get('int16')))
    return si


def grenade_kou(w, log):
    """GRENADE_KOU: 手榴弾の弾の対メカの当たりの ヒットストップ を甲と同じ、吹き飛ばし（int3・int4・int8・int10）を甲 x scale、減速率・吹き飛び重力は甲と同じ。
    自前の欄（int1 = 0）だけ変える（ほかの欄はそれを参照）。停止時間（int2・int7）・のけぞり方向・SE は今のまま。"""
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'GRENADE_KOU: Tama04.waz not among the modified files'
    name = MT.p('GRENADE_KOU', 'bullet'); k = MT.p('GRENADE_KOU', 'scale')
    bi, b = _skill(tw, name)
    u = {n for _, n in _fire_users(None).get((4, bi), ())}
    assert u == {'手榴弾'}, 'GRENADE_KOU: %s fired by %s' % (name, u)
    ph = b['phasesInfo']
    done = []
    if k is None:
        # 11/14（ユーザー: 吹き飛んでいない。SE 以外はほぼ甲ベースで、そこから吹き飛びの高さを下げる）:
        # のけぞり 4 欄のスカラ（停止時間・ノックバック・のけぞり速度・減速率・吹き飛び規模・重力・バウンド・参照 int1）を甲の欄の値に丸ごと。
        # 当たりの ヒットストップ・自分停止・スロー反映率（int13・int15・int16・int17）も甲。吹き飛び規模だけ x sqrt(height)（重力が同じなので高さ x height）。
        # 威力・最低値・補正・装甲攻撃力（バランス側）、ヒットエフェクト・SE・のけぞり方向は今のまま。
        hgt = MT.p('GRENADE_KOU', 'height')
        KEYS = ('int1', 'short1', 'int2', 'int3', 'int4', 'int5', 'int6', 'int7', 'int8', 'int9', 'int10', 'int11', 'int12', 'int13')
        for part in ('direct', 'blast'):
            ref = MT.p('GRENADE_KOU', part)
            for t in ref['turns']:
                hs = _objs(ph[t], 41)
                assert len(hs) == 1, 'GRENADE_KOU: turn %d mech hits %d' % (t, len(hs))
                h = hs[0]
                for x in ('int13', 'int15', 'int16', 'int17'):
                    h[x] = ref['hit'][x]
                cols = _cols(h)
                assert set(cols) == {17, 18, 19, 20}
                for c, d in cols.items():
                    kc = dict(ref['cols'][17]); kc.update(ref['cols'].get(c, {'int1': 1}))
                    for x in KEYS:
                        d[x] = kc.get(x, 0)
                    if d.get('int10', 0) > 0:
                        d['int10'] = round(d['int10'] * hgt ** 0.5)
                c17 = cols[17]
                done.append('turn %d（%s）ヒットストップ %d、地上欄 停止 %d ノックバック %d/%d のけぞり速度 %d 減速率 %d 吹き飛び規模 %d 重力 %d（空中欄は %s）' % (
                    t, '直撃' if part == 'direct' else '爆発', h['int15'], c17['int2'], c17['int3'], c17['int4'], c17['int8'], c17['int9'], c17['int10'], c17['int11'],
                    '地上欄と同じ' if cols[18]['int1'] else '自前'))
        log.append('GRENADE_KOU %s: のけぞりを甲の手榴弾と同じに、吹き飛びの高さ x%g: %s' % (name, hgt, ' / '.join(done)))
        return [(BULLET_WAZ, bi)]
    for part in ('direct', 'blast'):
        ref = MT.p('GRENADE_KOU', part)
        for t in ref['turns']:
            hs = _objs(ph[t], 41)
            assert len(hs) == 1, 'GRENADE_KOU: turn %d mech hits %d' % (t, len(hs))
            h = hs[0]
            old_hs = (h.get('int15', 0), h.get('int16', 0))
            h['int15'] = h['int16'] = ref['hitstop']
            cols = []
            for c, d in sorted(_cols(h).items()):
                if d.get('int1'):
                    continue
                before = tuple(d.get(x, 0) for x in ('int3', 'int4', 'int8', 'int9', 'int10', 'int11'))
                for x in ('int3', 'int4', 'int8', 'int10'):
                    d[x] = round(ref[x] * k)
                for x in ('int9', 'int11'):
                    d[x] = ref[x]
                cols.append('欄 %d %s -> %s' % (c, before, tuple(d[x] for x in ('int3', 'int4', 'int8', 'int9', 'int10', 'int11'))))
            assert cols, 'GRENADE_KOU: turn %d has no own column' % t
            done.append('turn %d（%s）ヒットストップ %d/%d -> %d、%s' % (t, '直撃' if part == 'direct' else '爆発', old_hs[0], old_hs[1], ref['hitstop'], '; '.join(cols)))
    log.append('GRENADE_KOU %s（ノックバック/のけぞり速度/減速率/吹き飛び規模/重力）: %s' % (name, ' / '.join(done)))
    return [(BULLET_WAZ, bi)]


def ex_cancel(w, log):
    """EXCANCEL: EX キャンセル（キャンセル操作、exe 0x617130）の区間 = ｷｬﾝｾﾙﾌﾗｸﾞ（slot 47）の値 3 を、表のとおりに置き直す。
    まず全技の値 3 のイベント（甲テンプレの名残）を消し、表の (ターン, 開始, 終了) に置く。同じターンの slot 47 の 0/1/2 の
    イベントがあるフレームは抜く（甲 ケイジブレイドLv3 T1: F0-10 = 3、F11 = 1、F12-63 = 3）。slot 33 は触らない。
    他の挙動の調整（ターンの追加など）の後に当てる。"""
    import copy
    win = MT.p('EXCANCEL', 'windows')
    tpl_u = tpl_o = None
    removed = []; touched = set()
    for si, s in enumerate(w['skillList']):
        for t, turn in enumerate((s or {}).get('phasesInfo', [])):
            for u in _units(turn, 47):
                tpl_u = tpl_u or u
                keep = []
                for o in u['skillInfoObjectList']:
                    if o.get('int4') == 3:
                        assert o.get('int2') == 3 and o.get('int1') == 0 and o.get('int3') == 0, 'EXCANCEL: unexpected value-3 event'
                        tpl_o = tpl_o or o
                        removed.append('%s T%d F%d-%d' % (s['skillNameJapanese'], t, o['startFrame'], o['endFrame'])); touched.add(si)
                    else:
                        keep.append(o)
                u['skillInfoObjectList'] = keep
            turn['skillUnitCollection'] = [u for u in turn['skillUnitCollection']
                                           if not (u['unitQuantity'] == 47 and not u['skillInfoObjectList'])]
    assert tpl_u is not None and tpl_o is not None, 'EXCANCEL: no slot 47 value-3 sample in %s' % SELF_WAZ
    log.append('EXCANCEL: 甲テンプレから写っていた値 3 の区間 %d 個を削除（%s）' % (len(removed), '、'.join(removed)))
    for name, ws in win.items():
        si, s = _skill(w, name)
        ph = s['phasesInfo']; done = []
        assert len({t for t, _a, _b in ws}) == len(ws), 'EXCANCEL %s: a turn is listed twice' % name
        for t, a, b in ws:
            assert 0 <= t < len(ph), 'EXCANCEL %s: no turn %d' % (name, t)
            turn = ph[t]
            last = max(o['endFrame'] for o in _objs(turn, 71))      # このターンを出る一番遅いフレーム
            assert 0 <= a <= b <= last, 'EXCANCEL %s T%d: F%d-%d is outside the turn (last frame F%d)' % (name, t, a, b, last)
            other = _objs(turn, 47)
            assert all(o['startFrame'] == o['endFrame'] and o.get('int4') in (0, 1, 2) for o in other), \
                'EXCANCEL %s T%d: unexpected slot 47 events' % (name, t)
            cut = sorted({o['startFrame'] for o in other if a <= o['startFrame'] <= b})
            segs = []; x = a
            for c in cut + [b + 1]:
                if x <= c - 1:
                    segs.append((x, c - 1))
                x = c + 1
            assert segs, 'EXCANCEL %s T%d: empty window' % (name, t)
            objs = []
            for x, y in segs:
                o = copy.deepcopy(tpl_o); o.update(int1=0, int2=3, int3=0, int4=3, startFrame=x, endFrame=y, offset=0)
                objs.append(o)
            us = _units(turn, 47)
            if us:
                assert len(us) == 1
                us[0]['skillInfoObjectList'] = sorted(us[0]['skillInfoObjectList'] + objs, key=lambda o: o['startFrame'])
            else:
                u = copy.deepcopy(tpl_u); u['skillInfoObjectList'] = objs; u['skillInfoUnknownList'] = []
                uc = turn['skillUnitCollection']
                k = next((i for i, x_ in enumerate(uc) if x_['unitQuantity'] > 47), len(uc))
                uc.insert(k, u)
            done.append('T%d %s' % (t, '・'.join('F%d-%d' % sg for sg in segs)))
        touched.add(si)
        log.append('EXCANCEL %s: %s' % (name, ' / '.join(done)))
    return [(SELF_WAZ, si) for si in sorted(touched)]


def bullet_nocancel(w, log):
    """BULLET_NOCANCEL: 表の近接技が撃つ弾（Tama04）の対メカの当たり（slot 41）の selfStunFrame（+0x64、キャンセルフラグ）を 1 -> 0。
    弾を撃っているのがその技だけで（ほかの弾経由も含む）、今の値が全部 1 であることを確かめてから変える（調査記録 56）。"""
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'BULLET_NOCANCEL: Tama04.waz not among the modified files'
    users = _fire_users(None)
    names = {(4, i): s['skillNameJapanese'] for i, s in enumerate(tw['skillList']) if s}

    def roots(k, seen=()):
        """弾 k を（弾経由も含めて）撃っている Tooru.waz の技名の集合"""
        out = set()
        for f_, n in users.get(k, ()):
            if f_ == SELF_WAZ:
                out.add(n)
            elif f_ == BULLET_WAZ:
                k2 = (4, _skill(tw, n)[0])
                if k2 not in seen:
                    out |= roots(k2, seen + (k,))
        return out
    out, ch = [], []
    for weapon, bl in MT.p('BULLET_NOCANCEL', 'bullets').items():
        for name in bl:
            bi, b = _skill(tw, name)
            r = roots((4, bi))
            assert r == {weapon}, 'BULLET_NOCANCEL: %s fired by %s (expected %s)' % (name, r, weapon)
            n = 0
            for t, turn in enumerate(b['phasesInfo']):
                for h in _objs(turn, 41):
                    assert h.get('selfStunFrame') == 1, 'BULLET_NOCANCEL: %s turn %d hit flag %s' % (name, t, h.get('selfStunFrame'))
                    h['selfStunFrame'] = 0
                    n += 1
            assert n, 'BULLET_NOCANCEL: %s has no mech hit' % name
            ch.append('%s %s %d 件' % (weapon, name, n))
            out.append((BULLET_WAZ, bi))
    log.append('BULLET_NOCANCEL 弾の当たりのキャンセルフラグ 1 -> 0: ' + ', '.join(ch))
    return out


def sat_hold(w, log):
    """SAT_HOLD: サテライトレーザーの落下ビームに「落ちないターン」を足す（原作再現版では使わない回避策、調査記録 59・60）。"""
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'SAT_HOLD: Tama04.waz not among the modified files'
    bi, b = _skill(tw, MT.p('SAT_HOLD', 'bullet'))
    ph0 = b['phasesInfo'][0]
    hits = _objs(ph0, 41)
    assert len(hits) == 1 and hits[0]['hitCount'] > 1, 'SAT_HOLD: turn 0 hit %s' % [h.get('hitCount') for h in hits]
    n = hits[0]['hitCount']
    for turn in b['phasesInfo']:                      # every absolute turn jump >= 1 moves one turn down
        for o in _objs(turn, 71):
            j = o['bsdxInfoCollectionList2'][0]
            if j['typeList'] == [0, 1] and j['paramList'] and j['paramList'][0] >= 1:
                j['paramList'] = [j['paramList'][0] + 1]
    hold = copy.deepcopy(ph0)
    for u in _units(hold, 19):
        u['skillInfoObjectList'] = [dict(copy.deepcopy(u['skillInfoObjectList'][0]), int1=0, int2=0, int3=0, int4=0, int5=0, int6=0,
                                         startFrame=0, endFrame=0, offset=0)]
    _objs(hold, 41)[0]['hitCount'] = n - 1
    hits[0]['hitCount'] = 1
    k = 0
    for o in _objs(ph0, 71):
        if o['bsdxInfoCollectionList1'][0]['typeList'][:3] == [2, 6, 0]:
            o['bsdxInfoCollectionList2'][0]['paramList'] = [1]; k += 1
    assert k == 1, 'SAT_HOLD: %d hit-count jumps in turn 0' % k
    # user 11/15 night: when the hold time is used up, go on to the piercing turn (not the explosion): the turn-end jump of
    # the hold turn fires after (hits - 1) x ヒット間隔 frames and leads to turn 2.
    hold_f = (n - 1) * (hits[0].get('hitInterval') or 10)
    k2 = 0
    for o in _objs(hold, 71):
        if o['bsdxInfoCollectionList1'][0]['typeList'] == [0]:
            o['startFrame'] = o['endFrame'] = min(o['endFrame'], hold_f)
            o['bsdxInfoCollectionList2'][0]['typeList'] = [0, 1]; o['bsdxInfoCollectionList2'][0]['paramList'] = [2]; k2 += 1
    assert k2 == 1, 'SAT_HOLD: %d turn-end jumps in the hold turn' % k2
    b['phasesInfo'].insert(1, hold)
    b['phaseQuantity'] = len(b['phasesInfo'])
    log.append('SAT_HOLD %s: ターン 0 は 1 ヒット -> 新ターン 1（落下なし、%d ヒット）-> ターン 2（貫通）' % (b['skillNameJapanese'], n - 1))
    return [(BULLET_WAZ, bi)]


def sat_ride(w, log):
    """SAT_RIDE: サテライトレーザーの落下ビームを甲 Lv3 T0 と同じ「敵の上に乗って一緒に落ちる」形にする（調査記録 69）。"""
    assert not MT.on('SAT_HOLD'), 'SAT_RIDE: SAT_HOLD must be off (both rewrite turn 0)'
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'SAT_RIDE: Tama04.waz not among the modified files'
    bi, b = _skill(tw, MT.p('SAT_RIDE', 'bullet'))
    _, kou = _skill(tw, MT.p('SAT_RIDE', 'kou'))
    ph0 = b['phasesInfo'][0]
    assert not _units(ph0, 51), 'SAT_RIDE: turn 0 already has slot 51'
    k51 = _units(kou['phasesInfo'][0], 51)
    assert len(k51) == 1 and len(k51[0]['skillInfoObjectList']) == 1, 'SAT_RIDE: 甲 T0 slot 51'
    bd = k51[0]['skillInfoObjectList'][0]['byteData1']
    assert [i for i, v in enumerate(bd) if v] == [36] and bd[36] == 1, 'SAT_RIDE: 甲 T0 slot 51 is not 垂直メカ敵 only (%s)' % bd
    u51 = copy.deepcopy(k51[0])
    for o in u51['skillInfoObjectList']:
        o['startFrame'] = o['endFrame'] = 0; o['offset'] = 0
    uc = ph0['skillUnitCollection']
    at = next((i for i, u in enumerate(uc) if u['unitQuantity'] > 51), len(uc))
    uc.insert(at, u51)
    # (2) 空中のけぞり: 下向きに押す
    hits = _objs(ph0, 41)
    assert len(hits) == 1 and hits[0]['hitCount'] > 1, 'SAT_RIDE: turn 0 hit %s' % [h.get('hitCount') for h in hits]
    air = [hu for hu in hits[0]['ceventHitUnitList'] if hu['ceventHitUnitQuantity'] == 18]
    assert len(air) == 1, 'SAT_RIDE: %d 空中 のけぞり units' % len(air)
    d = air[0]['data']
    was = (d.get('int10'), d.get('int11'))
    assert (d.get('int10') or 0) >= 0, 'SAT_RIDE: 空中 のけぞり already downward (%s)' % (was,)
    d['int10'], d['int11'] = MT.p('SAT_RIDE', 'air_down'), MT.p('SAT_RIDE', 'air_grav')
    calm = []
    if MT.p('SAT_RIDE', 'calm', False):
        # 11/16 23:10 実験（ユーザー「当たっている間はほぼ押さない形」）: 4 つののけぞりの ﾋｯﾄﾊﾞｯｸ・のけぞり速度・吹き飛び規模を 0 に
        for hu in hits[0]['ceventHitUnitList']:
            if hu['ceventHitUnitQuantity'] in (17, 18, 19, 20):
                dd = hu['data']
                calm.append('%d:%s/%s/%s' % (hu['ceventHitUnitQuantity'], dd.get('int3'), dd.get('int8'), dd.get('int10')))
                dd['int3'] = dd['int8'] = 0
                if hu['ceventHitUnitQuantity'] != 18:   # 空中の吹き飛び規模は air_down（11/16 23:40 Dive2 の -10）
                    dd['int10'] = 0
        assert len(calm) == 4, 'SAT_RIDE: のけぞり units %s' % calm
    # (5) 11/16 23:35: 敵がいなくなっても空中で止まる（ユーザー）。T0 の落下は slot 19 で F0-4 に速さを付けるだけ（重力 0）なので、
    #     敵の上で縦の速さが 0 になると戻らない。甲は -50 を T0 の全フレーム（F0-179）に置いている → 最後の速さをターンの終わりまで延ばす
    j19 = _objs(ph0, 19)
    last = max(j19, key=lambda o: o['startFrame'])
    t_end = max(o['endFrame'] for o in _objs(ph0, 71))
    assert last['endFrame'] < t_end and (last.get('int2') or 0) < 0, 'SAT_RIDE: slot 19 last %s' % last
    f19 = (last['startFrame'], last['endFrame'], t_end)
    last['endFrame'] = t_end
    # (3) 着地 -> 高さ <= land_h（甲 T0 の「高さ□以下なら」を写す） / (4) 時間切れ -> 貫通ターン (1)
    # 11/16 23:30: 「地面に着地」(2,7,17) は敵の上に乗っただけで成り立ち、空中で爆風が出て敵を打ち上げていた（ユーザーの動画 23-04-01・23-16-13）
    kh = [o for o in _objs(kou['phasesInfo'][0], 71) if o['bsdxInfoCollectionList1'][0]['typeList'] == [2, 3, 3, 2]]
    assert len(kh) == 1, 'SAT_RIDE: 甲 T0 height condition %d' % len(kh)
    land_h = MT.p('SAT_RIDE', 'land_h')
    k_land = k_end = 0
    for o in _objs(ph0, 71):
        c, j = o['bsdxInfoCollectionList1'][0], o['bsdxInfoCollectionList2'][0]
        if c['typeList'] == [2, 7, 16]:
            o['bsdxInfoCollectionList1'] = [dict(copy.deepcopy(kh[0]['bsdxInfoCollectionList1'][0]), paramList=[land_h])]
            # int1 = 条件の対象オブジェクト（Term G1: 0 自分 / 1 標的）。甲は 1（標的の高さ ≤ 155 = 敵が低くなったら貫通）。
            # 11/16 23:50: 1 のままだと外れたビームが地面で止まったまま時間切れまで残った（ビームの標的が取れていないと推定）→ 0（ビーム自身の高さ）
            assert kh[0].get('int1') == 1, 'SAT_RIDE: 甲 T0 height condition object %s' % kh[0].get('int1')
            o['int1'] = 0
            k_land += 1
        elif c['typeList'] == [0]:
            assert j['typeList'] == [0, 1] and j['paramList'] != [1], 'SAT_RIDE: turn 0 end jump %s/%s' % (j['typeList'], j['paramList'])
            j['paramList'] = [1]; k_end += 1
        elif c['typeList'][:3] == [2, 6, 0]:
            assert j['typeList'] == [0, 1] and j['paramList'] == [1], 'SAT_RIDE: hit-count jump %s/%s' % (j['typeList'], j['paramList'])
    assert (k_land, k_end) == (1, 1), 'SAT_RIDE: turn 0 land %d / end %d jumps' % (k_land, k_end)
    # (6) 11/17 07:59（ユーザー「当たってる間、敵が仰け反らないから、すぐに敵の自由移動で抜けられる。仰け反りを甲のレーザーくらいに」）:
    #     calm で ﾋｯﾄﾊﾞｯｸ（int3 = 最初のヒットの被弾硬直）を 0 にしていたので、毎ヒットが「最初のヒット」のまま硬直 0 だった（推定）。
    #     4 つののけぞりの int3 / int4（のけぞり中に当たったときの硬直）を甲 Lv3 T0 の値に。押す量（のけぞり速度・吹き飛び）はそのまま
    stun = []
    if MT.p('SAT_RIDE', 'kou_stun', False):
        kh41 = _objs(kou['phasesInfo'][0], 41)
        assert len(kh41) == 1, 'SAT_RIDE: 甲 T0 hits %d' % len(kh41)
        kn = {hu['ceventHitUnitQuantity']: hu['data'] for hu in kh41[0]['ceventHitUnitList'] if hu['ceventHitUnitQuantity'] in (17, 18, 19, 20)}
        assert len(kn) == 4, 'SAT_RIDE: 甲 T0 のけぞり units %s' % sorted(kn)
        for hu in hits[0]['ceventHitUnitList']:
            q = hu['ceventHitUnitQuantity']
            if q in kn:
                dd = hu['data']
                stun.append('%d:%s/%s->%s/%s' % (q, dd.get('int3'), dd.get('int4'), kn[q].get('int3'), kn[q].get('int4')))
                dd['int3'], dd['int4'] = kn[q].get('int3'), kn[q].get('int4')
        assert len(stun) == 4, 'SAT_RIDE: のけぞり units %s' % stun
    # (7) 11/17 07:59（ユーザー「空中で当たっている間はずっと貫通せずに当たり続け、敵が地面についてから今と同じ時間ヒットさせたい。外れたときは今と同じ」）:
    #     今の T0 をそのまま写して最後に新しいターン（地上の段）を足す（20 ヒット、使い切る / 時間切れ -> 貫通、高さ <= land_h -> 爆発）。
    #     T0 はヒット数の制限なし（-1、甲 T0 と同じ）・ヒット数の条件を外し、「最近ヒットした OBJ が地面に着地していたら -> 地上の段」を足す。
    #     対象オブジェクトは条件の intList3[0]（Term G1: 8 最近ヒットしたOBJ。対空バルカンビット：真 が (2,7,17) を 標的 [1,0] で使う）。
    #     末尾に足すので既存のターン番号（1 貫通 / 2 爆発）は変わらない
    g_turn = None
    if MT.p('SAT_RIDE', 'air_hold', False):
        g_turn = len(b['phasesInfo'])
        assert g_turn == 3, 'SAT_RIDE: bullet has %d turns' % g_turn
        g = copy.deepcopy(ph0)
        # 11/17 19:55（ユーザー「20 ヒットの段で即座にレーザーが消えてる」）: 地上の敵に乗ったビームでも 高さ <= land_h が成り立ち
        # （9488C83B でも「地面についたら即爆発」していた）、段に入った瞬間に爆発へ飛んでいた（推定）→ 地上の段からは高さの条件を外す。
        # 段の途中で敵が抜けたときに地面に長く残らないよう、時間切れ（-> 貫通）を ヒット数 × 間隔 + g_margin に縮める
        gu = _units(g, 71)
        assert len(gu) == 1, 'SAT_RIDE: ground turn slot 71 units %d' % len(gu)
        gl = gu[0]['skillInfoObjectList']
        gh = [o for o in gl if o['bsdxInfoCollectionList1'][0]['typeList'] == [2, 3, 3, 2]]
        ge = [o for o in gl if o['bsdxInfoCollectionList1'][0]['typeList'] == [0]]
        assert len(gh) == 1 and len(ge) == 1, 'SAT_RIDE: ground turn height %d / end %d' % (len(gh), len(ge))
        gl.remove(gh[0])
        g_end = _objs(g, 41)[0]['hitCount'] * (_objs(g, 41)[0].get('hitInterval') or 10) + MT.p('SAT_RIDE', 'g_margin', 10)
        assert g_end < ge[0]['endFrame'], 'SAT_RIDE: ground turn end %d >= %d' % (g_end, ge[0]['endFrame'])
        ge[0]['startFrame'] = ge[0]['endFrame'] = g_end
        hits[0]['hitCount'] = -1
        u71 = _units(ph0, 71)
        assert len(u71) == 1, 'SAT_RIDE: turn 0 slot 71 units %d' % len(u71)
        ol = u71[0]['skillInfoObjectList']
        hc = [o for o in ol if o['bsdxInfoCollectionList1'][0]['typeList'][:3] == [2, 6, 0]]
        assert len(hc) == 1, 'SAT_RIDE: hit-count jumps %d' % len(hc)
        ol.remove(hc[0])
        ih = next(i for i, o in enumerate(ol) if o['bsdxInfoCollectionList1'][0]['typeList'] == [2, 3, 3, 2])
        gc = copy.deepcopy(ol[ih])
        gc['int1'] = 0
        gc['bsdxInfoCollectionList1'] = [dict(int1=0, typeList=[2, 7, 17], paramList=[], intList3=[8, 0], intList4=[], int2=0)]
        gc['bsdxInfoCollectionList2'][0]['typeList'] = [0, 1]
        gc['bsdxInfoCollectionList2'][0]['paramList'] = [g_turn]
        ol.insert(ih + 1, gc)                 # 高さ <= land_h（外れて地面 -> 爆発）を先に見る
        # 11/17 20:15（ユーザー「修正後も触った瞬間に、爆発すらせず文字通り即座に消えてる」）: skillSuffixList（ターンごとに 1 件）を
        # 足していなかったので、ゲームはターン 3 を知らず、ジャンプした瞬間に弾が終わっていた → BU_FALL と同じく 1 件足す
        assert len(b['skillSuffixList']) == g_turn, 'SAT_RIDE: skillSuffixList %d' % len(b['skillSuffixList'])
        _zero_offsets(g)
        b['phasesInfo'].append(g)
        b['phaseQuantity'] = len(b['phasesInfo'])
        x = copy.deepcopy(b['skillSuffixList'][-1]); x['int1'] = g_turn; b['skillSuffixList'].append(x)
    log.append('SAT_RIDE %s: ターン 0 に接触 垂直メカ敵 1（甲 T0 から）、空中のけぞり 吹き飛び %s/%s -> %d/%d、着地 -> 自分の高さ %d 以下（甲 T0 の条件の形、対象は自分）、'
               '時間切れ -> ターン 1（貫通）、落下の速さ %s を F%d-%d -> F%d-%d（甲と同じく掛け続ける）'
               % (b['skillNameJapanese'], was[0], was[1], d['int10'], d['int11'], land_h, last.get('int2'), f19[0], f19[1], f19[0], f19[2])
               + ('。押さない（ﾋｯﾄﾊﾞｯｸ/のけぞり速度/吹き飛び規模 -> 0: %s）' % ', '.join(calm) if calm else '')
               + ('。被弾硬直 int3/int4 を甲 T0 に（%s）' % ', '.join(stun) if stun else '')
               + ('。空中の間はヒット数無制限、最近ヒットした OBJ が地面に着地 -> 新ターン %d（今までの T0 = 20 ヒット -> 貫通、高さの条件なし、時間切れ F%d -> 貫通）' % (g_turn, g_end) if g_turn else ''))
    return [(BULLET_WAZ, bi)]


def sat_aim(w, log):
    """SAT_AIM: サテライトレーザーの本体が出す 1 本目のビームを標的の真上に（2 本目以降はランダムのまま、調査記録 69）。"""
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'SAT_AIM: Tama04.waz not among the modified files'
    bi, body = _skill(tw, MT.p('SAT_AIM', 'body'))
    _, sk = _skill(w, MT.p('SAT_AIM', 'skill'))
    # 透の技の、本体を出す発射（Tama04 の本体を指す 1 件）から 発射位置（標的）と 高さ を取る
    src = [o for t in sk['phasesInfo'] for o in _objs(t, 48)
           if any(e['ceventEffectUnitQuantity'] == 3 and e['data'].get('wazFileNo') == 4 and e['data'].get('wazSequenceNo') == bi
                  for e in o['ceventEffectUnitList'])]
    assert len(src) == 1, 'SAT_AIM: %d body spawns in %s' % (len(src), sk['skillNameJapanese'])
    se = {e['ceventEffectUnitQuantity']: e for e in src[0]['ceventEffectUnitList']}
    assert se[7]['data']['bsdxInfoCollectionList'][0]['intList3'] == [1, 0], 'SAT_AIM: body spawn is not at the target'
    assert 11 in se, 'SAT_AIM: body spawn has no 発射位置補正：高さ'
    ph1 = body['phasesInfo'][1]
    beams = [o for o in _objs(ph1, 48) if any(e['ceventEffectUnitQuantity'] == 3 and e['data'].get('wazSequenceNo') == bi + 1
                                              for e in o['ceventEffectUnitList'])]
    assert len(beams) == 8 and sorted(o['startFrame'] for o in beams)[0] == 0, 'SAT_AIM: beams %s' % [o['startFrame'] for o in beams]
    first = min(beams, key=lambda o: o['startFrame'])
    assert [o['startFrame'] for o in beams].count(0) == 1, 'SAT_AIM: two beams at F0'
    el = first['ceventEffectUnitList']
    q = [e['ceventEffectUnitQuantity'] for e in el]
    assert 7 in q and 11 not in q and all(k in q for k in (8, 9, 10)), 'SAT_AIM: first beam units %s' % q
    el[:] = [e for e in el if e['ceventEffectUnitQuantity'] not in (8, 9, 10)]
    i7 = next(i for i, e in enumerate(el) if e['ceventEffectUnitQuantity'] == 7)
    el[i7] = copy.deepcopy(se[7])
    el.insert(i7 + 1, copy.deepcopy(se[11]))
    log.append('SAT_AIM %s: 1 本目（T1 F0）の発射位置 本体の周り 100px ランダム -> 標的、高さ %s（本体の発射と同じ）。2〜8 本目はそのまま'
               % (body['skillNameJapanese'], se[11]['data'].get('int2')))
    return [(BULLET_WAZ, bi)]


def _unit_tpl(ws, slot):
    """slot の unit（説明・typeId の雛形）を ws のどれかの技から 1 つ取る（中身は呼び出し側で入れ替える）。"""
    for w_ in ws:
        for s_ in w_['skillList']:
            for t_ in (s_ or {}).get('phasesInfo', ()):
                for u in _units(t_, slot):
                    if u['skillInfoObjectList']:
                        return u
    raise AssertionError('IF_STAGE: no slot %d unit to copy' % slot)


def _put_unit(turn, unit):
    """unit を slot 番号の順を保って turn に入れる（同じ slot があれば置き換える）。"""
    uc = turn['skillUnitCollection']
    uc[:] = [u for u in uc if u['unitQuantity'] != unit['unitQuantity']]
    at = next((i for i, u in enumerate(uc) if u['unitQuantity'] > unit['unitQuantity']), len(uc))
    uc.insert(at, unit)


def _mk_unit(tpl, objs):
    u = copy.deepcopy(tpl)
    o0 = u['skillInfoObjectList'][0]
    u['skillInfoObjectList'] = [dict(copy.deepcopy(o0), offset=0, **o) for o in objs]
    u['skillInfoUnknownList'] = []
    return u


def if_stage(w, log):
    """IF_STAGE: インペリアルファイナルの本体が当たったときだけ演出 → 落雷 → 吹き飛び（調査記録 72、ユーザー 11/17）。
    * turn 2（本体の当たり F0-13）: 落雷の発射（slot 48）を外す。「当たったら → 新ターン 4」を足す（透の打撃と同じ条件 (2,6,0,0)）。
      外れたら今までどおり turn 2 の終わり → turn 3（落雷なし）。本体の自機ヒットストップ int16 は 0（演出の長さを決まった値にする）。
    * 新ターン 4（停止の段、stop_f F）: 黒背景（slot 61、甲 死閃・鉄山靠と同じ 256 -> 128 で暗くして保つ）＋ 画面停止（slot 68 = 自分以外の時間が止まる）。
    * 新ターン 5（落雷の段、落雷の長さ + slow_f F）: F0 に落雷（turn 2 から移す）、黒背景のまま、スロー効果（slot 69）= slow、透のスロー反映率（slot 70）= 0。
      最後の fade F で黒背景を戻し、最後の F でスロー 0・反映率 100 → turn 3（硬直、今までと同じ）。
    * 新ターン 4・5 はキャンセル不可（slot 47 = 0 を全フレーム。turn 3 の EX キャンセルはそのまま）。
    * 落雷（Tama04）: 対メカの当たりのヒットストップ（被弾側 int15）= bolt_stop、のけぞり 4 欄を本体の当たりと同じに（上へ吹き飛ぶ）、
      落雷自身のスロー反映率（slot 70）を 0 に（スロー中も今の速さで落ちる）。落雷を撃つのはこの技だけ（BULLET_NOCANCEL の表で確認済み）。"""
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'IF_STAGE: Tama04.waz not among the modified files'
    si, s = _skill(w, MT.p('IF_STAGE', 'skill'))
    bi, b = _skill(tw, MT.p('IF_STAGE', 'bolt'))
    ph = s['phasesInfo']
    n = len(ph)
    assert n == 4 and s.get('phaseQuantity') == 4 and len(s['skillSuffixList']) == 4, 'IF_STAGE: expected 4 turns (%d)' % n
    t2 = ph[2]
    # --- turn 2: 本体の当たりと落雷の発射
    hits = _objs(t2, 41)
    assert len(hits) == 1 and hits[0]['hitCount'] == 1, 'IF_STAGE: turn 2 hits %s' % [h.get('hitCount') for h in hits]
    body = hits[0]
    hf = (body['startFrame'], body['endFrame'])
    u48 = _units(t2, 48)
    assert len(u48) == 1 and len(u48[0]['skillInfoObjectList']) == 1, 'IF_STAGE: turn 2 fires %d' % len(_objs(t2, 48))
    fire = u48[0]['skillInfoObjectList'][0]
    eno = [e['data'] for e in fire['ceventEffectUnitList'] if e['ceventEffectUnitQuantity'] == 3]
    assert len(eno) == 1 and (eno[0].get('wazFileNo'), eno[0].get('wazSequenceNo')) == (4, bi) and fire['startFrame'] == 0, \
        'IF_STAGE: turn 2 fires %s, not the bolt %d' % (eno, bi)
    for t_ in (0, 1, 3):
        assert not _objs(ph[t_], 48), 'IF_STAGE: turn %d also fires' % t_
    _drop(t2, 48)
    # 11/18（ユーザー「空振りすると電撃が出ないのに電撃の SE がする。当たったときは落雷時に鳴ってほしい」）:
    # 落雷の発射 SE（BFE ph2 fire.se = elec03、変換器が発射のフレームに slot 52 で置く。スプライトイベントの SE pikiiin より後ろ）を
    # turn 2 から外し、新 turn 5 の落雷の発射（F0）へ移す。pikiiin（振りの SE）は turn 2 に残す。
    u52 = _units(t2, 52)
    assert len(u52) == 1, 'IF_STAGE: turn 2 SE units %d' % len(u52)
    se_at = [o for o in u52[0]['skillInfoObjectList'] if o['startFrame'] == fire['startFrame']]
    assert len(se_at) == 2 and se_at[-1]['byteDataList'][0][:4] == [37, 0, 0, 0] \
        and se_at[-1]['byteDataList'][0][4] & 0xff == MT.p('IF_STAGE', 'fire_se') \
        and se_at[0]['byteDataList'][0][4] != se_at[-1]['byteDataList'][0][4], \
        'IF_STAGE: turn 2 SEs at the fire frame %s' % [o['byteDataList'] for o in se_at]
    fire_se = se_at[-1]
    u52[0]['skillInfoObjectList'].remove(fire_se)
    end2 = _end_jump(t2)
    assert end2['bsdxInfoCollectionList2'][0]['typeList'] == [0, 1] and end2['bsdxInfoCollectionList2'][0]['paramList'] == [3], \
        'IF_STAGE: turn 2 does not end into turn 3'
    assert not [o for o in _objs(t2, 71) if o is not end2], 'IF_STAGE: turn 2 already has conditional jumps'
    # 当たったら -> turn 4（透の打撃の「命中したら」と同じ条件。ブーストアッパー turn 0 から写す）
    _, bu = _skill(w, 'ブーストアッパー')
    hj = [o for o in _objs(bu['phasesInfo'][0], 71) if o['bsdxInfoCollectionList1'][0]['typeList'] == [2, 6, 0, 0]]
    assert len(hj) == 1 and hj[0]['bsdxInfoCollectionList1'][0]['paramList'] == [0], 'IF_STAGE: hit condition template'
    j = copy.deepcopy(hj[0])
    j.update(startFrame=hf[0], endFrame=hf[1], offset=0)
    j['bsdxInfoCollectionList2'] = [dict(copy.deepcopy(end2['bsdxInfoCollectionList2'][0]), paramList=[n])]
    _units(t2, 71)[0]['skillInfoObjectList'].insert(0, j)
    self_stop = body['int16']
    body['int16'] = 0
    # 11/17 夜（ユーザー「電撃が出る 0.2 秒前くらいにズームを解除」）: 本体ヒットの画面ズーム時間（int18、+0x50）を短く
    zoom0 = body['int18']
    assert zoom0 > MT.p('IF_STAGE', 'zoom_f'), 'IF_STAGE: body zoom time %s' % zoom0
    body['int18'] = MT.p('IF_STAGE', 'zoom_f')
    # --- 新ターン 4・5（turn 2 から、絵・移動・接触だけを写す）
    stop_f, slow_f, fade = MT.p('IF_STAGE', 'stop_f'), MT.p('IF_STAGE', 'slow_f'), MT.p('IF_STAGE', 'fade')
    shade = MT.p('IF_STAGE', 'shade')     # 背景の明るさ（256 = そのまま、0 = 真っ暗。甲 死閃の命中 T2 F0-3 は 0）。11/17 夜: 128 -> 0（ユーザー）
    bolt_f = max(o['endFrame'] for o in _objs(b['phasesInfo'][0], 71)) + 1
    tpl = {k: _unit_tpl([w], k) for k in (61, 68, 69, 70)}
    c47 = _units(ph[1], 47)
    assert len(c47) == 1 and [(o['startFrame'], o['int2'], o['int4']) for o in c47[0]['skillInfoObjectList']] == [(0, 0, 0)], 'IF_STAGE: turn 1 slot 47'
    c47 = c47[0]
    pose = [o for o in _objs(t2, 0) if o['endFrame'] == max(p['endFrame'] for p in _objs(t2, 0))]
    assert len(pose) == 1, 'IF_STAGE: turn 2 last pose'

    def base(L):
        t = copy.deepcopy(t2)
        t['skillUnitCollection'] = [u for u in t['skillUnitCollection'] if u['unitQuantity'] in (0, 10, 18, 19, 21, 51)]
        for u in t['skillUnitCollection']:
            if u['unitQuantity'] == 0:
                u['skillInfoObjectList'] = [dict(copy.deepcopy(pose[0]), startFrame=0, endFrame=L - 1, offset=0)]
            for o in u['skillInfoObjectList']:
                o['endFrame'] = min(o['endFrame'], L - 1); o['offset'] = 0
            u['skillInfoObjectList'] = [o for o in u['skillInfoObjectList'] if o['startFrame'] <= L - 1]
            u['skillInfoUnknownList'] = []
        e = copy.deepcopy(end2)
        e.update(startFrame=L - 1, endFrame=L - 1, offset=0)
        _put_unit(t, _mk_unit(_unit_tpl([w], 71), []))
        _units(t, 71)[0]['skillInfoObjectList'] = [e]
        # 演出の間はキャンセル不可（本体の命中で立つキャンセル可・EX キャンセルとも 0 に。turn 1 の F0 と同じ値を全フレームに）
        _put_unit(t, _mk_unit(c47, [dict(int1=0, int2=0, int3=0, int4=0, startFrame=0, endFrame=L - 1)]))
        return t, e

    def dark(a, b_, f0, f1):
        return dict(int1=0x10000000, int2=a, int3=0, int4=0, int5=0, int6=b_, int7=0, int8=0, int9=0, startFrame=f0, endFrame=f1)

    def val(v0, v1, f0, f1, mode=0):
        return dict(int1=mode, int2=v0, int3=0, int4=v1, startFrame=f0, endFrame=f1)

    ta, ea = base(stop_f)
    ea['bsdxInfoCollectionList2'][0]['paramList'] = [n + 1]
    _put_unit(ta, _mk_unit(tpl[61], [dark(shade, shade, 0, stop_f - 1)]))     # 死閃と同じく当たった瞬間から暗く
    _put_unit(ta, _mk_unit(tpl[68], [val(0, 0, 0, stop_f - 1)]))
    LB = bolt_f + slow_f
    hold = MT.p('IF_STAGE', 'hold_f', 0)   # 11/17 夜: 落雷の後に腕を突き上げたポーズを hold_f F 保つ（ユーザー、技の全体がそのぶん伸びる）
    tb, eb = base(LB + hold)
    eb['bsdxInfoCollectionList2'][0]['paramList'] = [3]
    u48b = copy.deepcopy(u48[0]); u48b['skillInfoUnknownList'] = []
    _put_unit(tb, u48b)
    _put_unit(tb, _mk_unit(u52[0], [{k: v for k, v in copy.deepcopy(fire_se).items() if k not in ('offset', 'startFrame', 'endFrame')}]))   # 11/18: 発射 SE は落雷と同時
    slow = MT.p('IF_STAGE', 'slow')
    _put_unit(tb, _mk_unit(tpl[61], [dark(shade, shade, 0, LB - fade - 1), dark(shade, 256, LB - fade, LB - 1)]))
    if slow and slow_f:     # 11/17 夜: 落雷後のスローは無し（slow_f 0、ユーザー「エンジンのズームアウト中にスローを解除すると汚い」）
        _put_unit(tb, _mk_unit(tpl[69], [val(slow, slow, 0, LB - 2), val(0, 0, LB - 1, LB - 1)]))
        _put_unit(tb, _mk_unit(tpl[70], [val(0, 0, 0, 0), val(100, 100, LB - 1, LB - 1)]))
    ph.extend([ta, tb])
    s['phaseQuantity'] = len(ph)
    for t_ in (n, n + 1):
        x = copy.deepcopy(s['skillSuffixList'][-1]); x['int1'] = t_; s['skillSuffixList'].append(x)
    # --- 落雷: ヒットストップ・のけぞり・スロー反映率
    bt = b['phasesInfo']
    assert len(bt) == 1, 'IF_STAGE: bolt turns %d' % len(bt)
    bh = _objs(bt[0], 41)
    assert len(bh) == 1, 'IF_STAGE: bolt hits %d' % len(bh)
    stop0 = bh[0]['int15']
    bh[0]['int15'] = MT.p('IF_STAGE', 'bolt_stop')
    nk = {hu['ceventHitUnitQuantity']: hu for hu in body['ceventHitUnitList'] if hu['ceventHitUnitQuantity'] in (17, 18, 19, 20)}
    assert len(nk) == 4, 'IF_STAGE: body のけぞり units %s' % sorted(nk)
    k = 0
    for i, hu in enumerate(bh[0]['ceventHitUnitList']):
        q = hu['ceventHitUnitQuantity']
        if q in nk:
            bh[0]['ceventHitUnitList'][i] = copy.deepcopy(nk[q]); k += 1
    assert k == 4, 'IF_STAGE: bolt のけぞり units %d' % k
    s70 = _objs(bt[0], 70)
    assert s70, 'IF_STAGE: bolt has no slot 70'
    r70 = [o['int4'] for o in s70]
    for o in s70:
        o['int2'] = o['int4'] = 0
    log.append('IF_STAGE %s: turn 2 の落雷を外し、当たったら（F%d-%d）-> 新 turn %d（黒背景 %d + 画面停止 %dF）-> 新 turn %d（落雷 + 黒背景 + スロー %d、%dF = 落雷 %dF + %dF、'
               '最後 %dF で黒背景を戻す、その後ポーズ保持 %dF）-> turn 3。外れたら turn 2 -> turn 3（落雷なし）。落雷の発射 SE（SeGroup[37][%d]）を turn 2 F0 -> 新 turn 5 F0。本体の自機ヒットストップ %s -> 0、画面ズーム時間 %s -> %s。'
               '落雷 %s: 被弾側ヒットストップ %s -> %d、のけぞり 4 欄を本体と同じに、スロー反映率 %s -> 0'
               % (s['skillNameJapanese'], hf[0], hf[1], n, shade, stop_f, n + 1, slow if slow_f else 0, LB, bolt_f, slow_f, fade, hold, fire_se['byteDataList'][0][4] & 0xff, self_stop, zoom0, body['int18'],
                  b['skillNameJapanese'], stop0, bh[0]['int15'], r70))
    return [(SELF_WAZ, si), (BULLET_WAZ, bi)]


def antibullet_power(w, log):
    """ANTIBULLET_POWER: 透の弾とラインの対弾の当たり（slot 42）の威力（slot 6）を表の値に。回数・間隔は触らない。下げない。"""
    out, ch = [], []
    for fn_, key in ((BULLET_WAZ, 'tama'), ('Laser.waz', 'laser')):
        tw = _NEW.get(fn_)
        assert tw is not None, 'ANTIBULLET_POWER: %s not among the modified files' % fn_
        for name, v in MT.p('ANTIBULLET_POWER', key).items():
            bi, b = _skill(tw, name)
            hs = [h for turn in b['phasesInfo'] for h in _objs(turn, 42)]
            assert hs, 'ANTIBULLET_POWER: %s has no 対弾 hit' % name
            vs = v if isinstance(v, list) else [v] * len(hs)
            assert len(vs) == len(hs), 'ANTIBULLET_POWER: %s has %d 対弾 hits, table %d' % (name, len(hs), len(vs))
            olds = []
            for h, p_ in zip(hs, vs):
                us = [u for u in h['ceventHitUnitList'] if u.get('unitSlotNum') == 6]
                assert len(us) == 1 and len(us[0]['data']['bsdxInfoCollectionList'][0]['paramList']) >= 1, name
                pl = us[0]['data']['bsdxInfoCollectionList'][0]['paramList']
                old = sum(pl)
                assert p_ >= old, 'ANTIBULLET_POWER: %s %d -> %d は下げる値' % (name, old, p_)
                pl[:] = [p_] + [0] * (len(pl) - 1)
                olds.append(old)
            ch.append('%s %s -> %s' % (name, '/'.join(map(str, olds)), '/'.join(map(str, vs))))
            out.append((fn_, bi))
    log.append('ANTIBULLET_POWER 対弾の威力: ' + ', '.join(ch))
    return out


def photon_nowall(w, log):
    """PHOTON_NOWALL: フォトンブラスターの弾の小さい段階から、壁・床の遷移（WALLHIT 接触 typeList [2,7,7]・重なり [2,7,15]、WALLLAND
    着地 [2,7,16]）を外し、slot 51 の壁の欄を 甲 フォトンブラスター：甲Lv3 T0 と同じにする。"""
    import struct
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'PHOTON_NOWALL: Tama04.waz not among the modified files'
    pr = MT.p('PHOTON_NOWALL', 'bullet'), MT.p('PHOTON_NOWALL', 'turns'), MT.p('PHOTON_NOWALL', 'touch')
    bi, b = _skill(tw, pr[0])
    wall = ([2, 7, 7], [2, 7, 15], [2, 7, 16])
    msg = []
    for t in pr[1]:
        turn = b['phasesInfo'][t]
        nd = 0
        for u in _units(turn, 71):
            keep = []
            for o in u['skillInfoObjectList']:
                cs = [c.get('typeList')[:3] for c in o['bsdxInfoCollectionList1']]
                if len(cs) == 1 and cs[0] in wall:
                    nd += 1
                else:
                    keep.append(o)
            u['skillInfoObjectList'] = keep
        assert nd == 3, 'PHOTON_NOWALL: %s turn %d removed %d wall changes (expected 3)' % (pr[0], t, nd)
        t51 = [o for o in _objs(turn, 51) if o['startFrame'] == 0]
        assert len(t51) == 1, 'PHOTON_NOWALL: %s turn %d F0 slot 51 x%d' % (pr[0], t, len(t51))
        v = list(struct.unpack('<14i', bytes(t51[0]['byteData1'])))
        old = tuple(v[4:9])
        v[4], v[5], v[6], v[8] = pr[2]['obj'], pr[2]['nomech'], pr[2]['nobullet'], pr[2]['screen']
        t51[0]['byteData1'] = list(struct.pack('<14i', *v))
        msg.append('turn %d: 壁・床の遷移 %d 件を外す、slot 51 OBJ..画面端 %s -> %s' % (t, nd, old, tuple(v[4:9])))
    log.append('PHOTON_NOWALL %s: %s' % (pr[0], '; '.join(msg)))
    return [(BULLET_WAZ, bi)]


def stunrod_dot(w, log):
    """STUNROD_DOT: スタンロッドの感電（見えない弾、敵に追従）を、麻痺の間 一定間隔でダメージを出す弾にする（ユーザー 11/19）。
    * 弾の対メカの当たり: 「ﾀﾞﾒｰｼﾞ処理をしない」(0x20) を外し、威力（内部）・最低値（表示威力 x 比）・ヒット毎補正を入れ、間隔を interval F に。
      早期廃熱は EARLYHEAT のスタンロッドの値（on のとき）。属性（感電）は付けない（付けると麻痺が延び続ける）。
    * 弾の寿命: 技本体の当たりの電撃の時間（int22、麻痺の長さ）に合わせる（ターン 0 の終わりと、スプライト・位置・当たりの区間）。
    * ヒット SE: 技 T2 の生成 SE（elec07）を当たりに戻す（SEVOICE で外したもの。重なってよい: ユーザー 11/19「多重に鳴るのはいったん発生してもいい」）。
    * ヒットエフェクト: BFE エフェクト 21 の写しを共有のエフェクト waz の末尾に足し（改善版だけ）、F0 で向き（slot 9）と大きさ（slot 1）を乱数に。
      元のエフェクトはほかの技（GF・EF・スプレッドパンチなど）も使うので触らない。
    * 画面の振動（当たりのサブ 27）の揺れ方を shake_type（3 = 縦。ブーストアッパー・インペリアルストライクと同じ）に。
    エフェクト・SE・振動はすべて当たりに付くので、敵が爆散して当たらなくなれば止まる。"""
    P_ = lambda k: MT.p('STUNROD_DOT', k)
    tw, ew = _NEW.get(BULLET_WAZ), _NEW.get(EFFECT_WAZ)
    assert tw is not None and ew is not None, 'STUNROD_DOT: %s / %s not among the modified files' % (BULLET_WAZ, EFFECT_WAZ)
    si, s = _skill(w, P_('skill'))
    bi, b = _skill(tw, P_('bullet'))
    users = _fire_users(None).get((4, bi), set())
    assert users == {(SELF_WAZ, P_('skill'))}, 'STUNROD_DOT: bullet fired by %s' % users
    # 麻痺の長さ = 技本体の当たり（1 つ）の電撃の時間
    mh = [h for t in s['phasesInfo'] for h in _objs(t, 41)]
    assert len(mh) == 1 and mh[0]['int2'] & 0x02 and mh[0]['int22'] > 0, 'STUNROD_DOT: skill hits %s' % [(h['int2'], h['int22']) for h in mh]
    life = mh[0]['int22']
    # 生成 SE（弾を出すターンの slot 52）
    se = [o['byteDataList'][0] for t in s['phasesInfo'] if any(e['unitSlotNum'] == 3 and e.get('data', {}).get('wazSequenceNo') == bi
          and e['data'].get('wazFileNo') == 4 for o in _objs(t, 48) for e in o['ceventEffectUnitList']) for o in _objs(t, 52)]
    assert len(se) == 1 and se[0][:4] == [37, 0, 0, 0] and se[0][4] == P_('se'), 'STUNROD_DOT: fire SE %s' % se
    assert len(b['phasesInfo']) == 1, 'STUNROD_DOT: bullet turns %d' % len(b['phasesInfo'])
    t0 = b['phasesInfo'][0]
    hs = _objs(t0, 41)
    assert len(hs) == 1, 'STUNROD_DOT: bullet hits %d' % len(hs)
    h = hs[0]
    sub = {u['unitSlotNum']: u for u in h['ceventHitUnitList']}
    pw = sub[6]['data']['bsdxInfoCollectionList'][0]
    assert (h['int2'], h['hitCount'], h['hitInterval'], h['minDamage'], h['midComboCorrection'], pw['typeList'], pw['paramList'], 28 in sub,
            h['int22']) == (0x20, -1, 2, 0, 0, [0], [0], False, 0), 'STUNROD_DOT: bullet hit is not the no-damage 2F hit'
    # 寿命: ターン 0 の終わり（slot 71）と、区間がそこまでのイベント
    end = _end_jump(t0)
    assert end['bsdxInfoCollectionList2'][0]['typeList'] == [0, 2], 'STUNROD_DOT: bullet turn 0 does not end the bullet'
    f0 = end['startFrame']
    span = sorted({u['unitQuantity'] for u in t0['skillUnitCollection'] for o in u['skillInfoObjectList'] if o['endFrame'] == f0})
    assert span == [0, 1, 11, 41, 71] and not [o for u in t0['skillUnitCollection'] for o in u['skillInfoObjectList'] if o['endFrame'] > f0], \
        'STUNROD_DOT: bullet events ending at F%d: %s' % (f0, span)
    for u in t0['skillUnitCollection']:
        for o in u['skillInfoObjectList']:
            if o['endFrame'] == f0:
                o['endFrame'] = life - 1
                if u['unitQuantity'] == 71:
                    o['startFrame'] = life - 1
    # ダメージ
    power = P_('power')
    disp = int(power * 1.5)
    early = (MT.p('EARLYHEAT', 'weapons') or {}).get(P_('weapon'), 0)
    h['int2'] = early
    h['hitInterval'] = P_('interval')
    pw['paramList'] = [power]
    h['minDamage'] = P_('min_dmg')      # 表示の単位（x1.5 しない）。ユーザー 11/19: 1
    h['midComboCorrection'] = P_('mid_corr')
    # 振動
    sh = sub[27]['data']
    assert (sh['int1'], sh['int2'], sh['int3']) == (0, 3, 1), 'STUNROD_DOT: shake %s' % [sh['int1'], sh['int2'], sh['int3']]
    sh['int1'] = P_('shake_type')
    sh['int3'] = P_('shake_amp')      # 振幅（作者の実機実験 11/19: int3 が振幅、int2 は 3 と 9 で体感の差なし）。1 -> 5
    # ヒット SE（当たりのサブ 28。雛形はほかの弾の当たりから）
    tpl = next(u for x in tw['skillList'] for t in (x or {}).get('phasesInfo', ()) for o in _objs(t, 41)
               for u in o['ceventHitUnitList'] if u['unitSlotNum'] == 28)
    u28 = copy.deepcopy(tpl)
    u28['data'] = dict(u28['data'], offset=0, count=1, byteDataList=[list(se[0])])
    lst = h['ceventHitUnitList']
    lst.insert(next((i for i, u in enumerate(lst) if u['unitSlotNum'] > 28), len(lst)), u28)
    # ヒットエフェクト: 写しを末尾に足して乱数の向き・大きさ
    he = sub[16]['data']
    ei = he['wazSequenceNo']
    assert he['wazFileNo'] == 2 and ew['skillList'][ei]['skillNameJapanese'] == P_('effect'), 'STUNROD_DOT: hit effect %s' % he
    fx = copy.deepcopy(ew['skillList'][ei])
    fx['skillNameJapanese'] = fx['skillNameJapanese'] + P_('effect_suffix')
    ft = fx['phasesInfo'][0]
    assert not _objs(ft, 1) and not _objs(ft, 9), 'STUNROD_DOT: effect already has scale/direction'
    lo, wd = P_('scale')
    a0, aw = P_('angle')
    _put_unit(ft, _mk_unit(_unit_tpl([tw], 1), [dict(int1=0, int2=lo, int3=wd, int4=0, int5=lo, int6=wd, startFrame=0, endFrame=0)]))
    _put_unit(ft, _mk_unit(_unit_tpl([tw, w], 9), [dict(int1=0, int2=a0, int3=aw, int4=0, int5=a0, int6=aw, startFrame=0, endFrame=0)]))
    ew['skillList'].append(fx)
    ni = len(ew['skillList']) - 1
    he['wazSequenceNo'] = ni
    log.append('STUNROD_DOT %s: 寿命 F%d -> %dF（麻痺の長さ）、%dF ごと %d ヒット、威力 内部 %d（表示 %d）最低 %d、ヒット毎補正 %d、早期廃熱 %d、'
               'ヒット SE %d、振動 %d 振幅 %d、ヒットエフェクト %s[%d] -> 写し [%d]（大きさ %d+0..%d、向き %d+0..%d）' % (
                   P_('bullet'), f0, life, P_('interval'), (life - 1) // P_('interval') + 1, power, disp, h['minDamage'], P_('mid_corr'),
                   early, se[0][4], P_('shake_type'), P_('shake_amp'), EFFECT_WAZ, ei, ni, lo, wd, a0, aw))
    return [(BULLET_WAZ, bi), (EFFECT_WAZ, ni)]


def nd_speed(w, log):
    """ND_SPEED（11/21）: 改善版だけ mek の 速度：ダッシュ（normalDashSpeed）を + add。mek は build の I2 が _NEW に入れて渡す。"""
    mf = SELF_WAZ[:-len('.waz')] + '.mek'
    m = _NEW.get(mf)
    assert m is not None, 'ND_SPEED: %s not among the modified files' % mf
    bi = m['mekBasicInfo']
    old = bi['normalDashSpeed']
    add = MT.p('ND_SPEED', 'add')
    assert isinstance(add, int) and add != 0, add
    bi['normalDashSpeed'] = old + add
    log.append('ND_SPEED %s: 速度：ダッシュ（normalDashSpeed）%d -> %d' % (mf, old, old + add))
    return []      # 技は触らない（mek の確認は build の I2）


def hammer_notimeout(w, log):
    """HAMMER_NOTIMEOUT（11/21）: クラッシュハンマーの落下（turn 1）が時間切れで攻撃（turn 2）に移らないように。
    turn 1 の終わりの無条件ジャンプを新ターン（末尾）へ。新ターン = turn 1 の最後の tail F の slot 0・18・19 の写し（F0 起点）
    + slot 36（turn 1 F0 の装甲）+「着地 -> attack_turn」（turn 1 と同じ条件）+ 終わりで自分自身へ。"""
    si, s = _skill(w, MT.p('HAMMER_NOTIMEOUT', 'skill'))
    t1, at, tail = (MT.p('HAMMER_NOTIMEOUT', k) for k in ('turn', 'attack_turn', 'tail'))
    ph = s['phasesInfo']
    n = len(ph)
    assert n == 5 and s.get('phaseQuantity') == n and len(s['skillSuffixList']) == n, 'HAMMER_NOTIMEOUT: expected 5 turns (%d)' % n
    tr = ph[t1]
    e = _end_jump(tr)
    assert e['bsdxInfoCollectionList2'][0]['typeList'] == [0, 1] and e['bsdxInfoCollectionList2'][0]['paramList'] == [at],         'HAMMER_NOTIMEOUT: turn %d does not time out into turn %d' % (t1, at)
    L = e['startFrame'] + 1
    land = [o for o in _objs(tr, 71) if o is not e]
    assert len(land) == 1 and land[0]['bsdxInfoCollectionList1'][0]['typeList'] == [2, 7, 16]         and land[0]['bsdxInfoCollectionList2'][0]['paramList'] == [at] and land[0]['endFrame'] == L - 1, 'HAMMER_NOTIMEOUT: landing jump not as expected'
    f0 = L - tail
    nt = {'skillUnitCollection': []}
    for k in tr:
        if k != 'skillUnitCollection':
            nt[k] = copy.deepcopy(tr[k])
    v19 = None
    for u in tr['skillUnitCollection']:
        q = u['unitQuantity']
        if q in (0, 18, 19):
            objs = [o for o in u['skillInfoObjectList'] if o['endFrame'] >= f0]
            assert objs and all(o['startFrame'] <= f0 for o in objs[:1]), 'HAMMER_NOTIMEOUT: slot %d does not cover F%d-%d' % (q, f0, L - 1)
            assert max(o['endFrame'] for o in objs) == L - 1, 'HAMMER_NOTIMEOUT: slot %d does not reach the turn end' % q
            if q == 19:
                assert len(objs) == 1 and objs[0]['int2'] == objs[0]['int5'] < 0, 'HAMMER_NOTIMEOUT: fall speed not held'
                v19 = objs[0]['int5']
        elif q == 36:
            objs = [o for o in u['skillInfoObjectList'] if o['startFrame'] == 0]
            assert len(objs) == 1 and objs[0]['int4'] > 0, 'HAMMER_NOTIMEOUT: turn %d F0 armor not found' % t1
        elif q == 71:
            objs = [land[0], e]
        else:
            continue
        nu = copy.deepcopy(u)
        nu['skillInfoUnknownList'] = []
        nu['skillInfoObjectList'] = []
        for o in objs:
            o = copy.deepcopy(o)
            o['offset'] = 0
            if q == 36:
                o['startFrame'] = o['endFrame'] = 0
            elif q == 71 and o['bsdxInfoCollectionList1'][0]['typeList'] == [0]:
                o['startFrame'] = o['endFrame'] = tail - 1
                o['bsdxInfoCollectionList2'][0]['paramList'] = [n]      # 自分自身へ
            elif q == 71:
                o['startFrame'], o['endFrame'] = 0, tail - 1
            else:
                o['startFrame'] = max(0, o['startFrame'] - f0)
                o['endFrame'] = o['endFrame'] - f0
            nu['skillInfoObjectList'].append(o)
        nt['skillUnitCollection'].append(nu)
    ph.append(nt)
    s['phaseQuantity'] = len(ph)
    x = copy.deepcopy(s['skillSuffixList'][-1]); x['int1'] = n; s['skillSuffixList'].append(x)
    e['bsdxInfoCollectionList2'][0]['paramList'] = [n]
    log.append('HAMMER_NOTIMEOUT %s: turn %d の終わり（F%d）-> turn %d をやめ、新 turn %d（turn %d F%d-%d の写し %dF、下降 %d px/F 保持・装甲・着地 -> turn %d）へ。'
               '新 turn %d の終わりは自分自身へ（着地するまで落ち続ける）' % (s['skillNameJapanese'], t1, L - 1, at, n, t1, f0, L - 1, tail, v19, at, n))
    return si


def shield_inertia(w, log):
    """SHIELD_INERTIA（11/21）: シールドのダッシュ慣性を受けやすく。slot 24（移動の補正率）は nd_rate 未満を nd_rate に、
    slot 30（SD の補正率、DASHRATE の直線の減り）は 100 からの減り幅 x sd_loss。最後のターンの 0 への戻しはターン全体で。"""
    si, s = _skill(w, MT.p('SHIELD_INERTIA', 'skill'))
    nd, k = MT.p('SHIELD_INERTIA', 'nd_rate'), MT.p('SHIELD_INERTIA', 'sd_loss')
    ph = s['phasesInfo']
    assert len(ph) == 3, 'SHIELD_INERTIA: expected 3 turns (%d)' % len(ph)
    ch = []
    for t, turn in enumerate(ph):
        o24 = _objs(turn, 24)
        assert len(o24) == 1 and o24[0]['startFrame'] == 0 and o24[0]['int1'] == 0, 'SHIELD_INERTIA: turn %d slot 24 not a single F0 value' % t
        a24 = o24[0]['int4']
        if a24 < nd:
            o24[0]['int4'] = nd
        o30 = _objs(turn, 30)
        assert len(o30) == 1 and o30[0]['startFrame'] == 0, 'SHIELD_INERTIA: turn %d slot 30 not a single F0 ramp' % t
        o = o30[0]
        a30 = (o['int2'], o['int4'], o['endFrame'])
        assert o['int1'] == (0 if t == 0 else 1), 'SHIELD_INERTIA: turn %d slot 30 mode %d' % (t, o['int1'])
        if t == 0:
            assert o['int2'] == 100
        if t == len(ph) - 1:
            assert o['int4'] == 0, 'SHIELD_INERTIA: last turn does not end at 0'
            o['endFrame'] = _end_jump(turn)['startFrame']
        else:
            o['int4'] = int(100 - (100 - o['int4']) * k + 0.5)
        ch.append('T%d 移動 %d->%d / SD %s%d->%d@F%d -> %s%d->%d@F%d' % (t, a24, o24[0]['int4'], 'prev' if o['int1'] else '', a30[0], a30[1], a30[2],
                                                                     'prev' if o['int1'] else '', o['int2'], o['int4'], o['endFrame']))
    log.append('SHIELD_INERTIA %s: %s' % (s['skillNameJapanese'], ', '.join(ch)))
    return si


def sink_mod(w, log):
    """SINK_MOD（11/21）: 表の技・ターンの F0 に機体どうしの接触オフ（slot 51）を置く（変換規則 SINK と同じ物を src から写す）。
    on_end の技は最後のターンの最後の F に接触オン。"""
    _, src = _skill(w, MT.p('SINK_MOD', 'src'))
    (t_off, f_off), (t_on, f_on) = MT.p('SINK_MOD', 'src_off'), MT.p('SINK_MOD', 'src_on')
    off = [o for o in _objs(src['phasesInfo'][t_off], 51) if o['startFrame'] == f_off]
    on_ = [o for o in _objs(src['phasesInfo'][t_on], 51) if o['startFrame'] == f_on]
    assert len(off) == 1 and len(on_) == 1, 'SINK_MOD: src slot 51 objects not found'
    off, on_ = off[0], on_[0]
    assert off['byteData1'][0] == 0 and on_['byteData1'][0] == 1 and off['byteData1'][1:] == on_['byteData1'][1:], 'SINK_MOD: src off / on not as expected'
    tpl = _units(src['phasesInfo'][t_off], 51)[0]
    sis, ch = [], []
    for name, cfg in MT.p('SINK_MOD', 'skills').items():
        si, s = _skill(w, name)
        ph = s['phasesInfo']
        last = None
        for t in cfg['turns']:
            turn = ph[t]
            assert not _units(turn, 51), 'SINK_MOD: %s turn %d already has slot 51' % (name, t)
            objs = [dict(off, offset=0, startFrame=0, endFrame=0)]
            if cfg['on_end'] and t == cfg['turns'][-1]:
                e = _end_jump(turn)
                assert e['bsdxInfoCollectionList2'][0]['typeList'] == [0, 2], 'SINK_MOD: %s turn %d does not end the skill' % (name, t)
                last = e['startFrame']
                objs.append(dict(on_, offset=0, startFrame=last, endFrame=last))
            u = copy.deepcopy(tpl)
            u['skillInfoObjectList'] = copy.deepcopy(objs)
            u['skillInfoUnknownList'] = []
            _put_unit(turn, u)
        if not cfg['on_end']:
            nxt = max(cfg['turns']) + 1
            assert _end_jump(ph[max(cfg['turns'])])['bsdxInfoCollectionList2'][0]['paramList'] == [nxt] and                 any(o['byteData1'][0] == 0 for o in _objs(ph[nxt], 51) if o['startFrame'] == 0),                 'SINK_MOD: %s turn %d is not followed by a touch-off turn' % (name, nxt)
        ch.append('%s turn %s F0 接触オフ%s' % (name, cfg['turns'], '、turn %d F%d で戻す' % (cfg['turns'][-1], last) if cfg['on_end'] else '（次のターンから変換の接触オフ）'))
        sis.append(si)
    log.append('SINK_MOD（%s turn %d の slot 51 の写し）: %s' % (MT.p('SINK_MOD', 'src'), t_off, '; '.join(ch)))
    return [(SELF_WAZ, si) for si in sis]


def gekka_camera(w, log):
    """GEKKA_CAMERA（11/22）: 月華衝の締め（turn 6）に 甲 月華衝 turn 5 の当たり以後の 拡大縮小（slot 59）とカメラ（slot 66）を写す（当たり = F0）。"""
    P = {k: MT.p('GEKKA_CAMERA', k) for k in ('skill', 'turn', 'zoom', 'zoom_ramp', 'zoom_until', 'h0', 'h1', 'hold')}
    f0 = MT.p('GEKKA_CAMERA', 'start', 0)   # 11/22 作者: アッパーのダメージ判定が出たとき（turn 6 の当たり矩形 bit 0 が初めて出る F12）から
    si, s = _skill(w, P['skill'])
    turn = s['phasesInfo'][P['turn']]
    hs = _objs(turn, 41)
    assert len(hs) == 1 and hs[0]['startFrame'] == 0, 'GEKKA_CAMERA: turn %d hit is not at F0' % P['turn']
    assert not _units(turn, 59) and not _units(turn, 66), 'GEKKA_CAMERA: turn %d already has zoom / camera' % P['turn']
    e = _end_jump(turn)
    assert e['bsdxInfoCollectionList2'][0]['typeList'] == [0, 2], 'GEKKA_CAMERA: turn %d does not end the skill' % P['turn']
    L = e['startFrame'] + 1
    assert L > f0 + P['hold'] + 1 and L > f0 + P['zoom_until'], 'GEKKA_CAMERA: turn too short'
    z = P['zoom']
    _put_unit(turn, _mk_unit(_unit_tpl([w], 59), [
        dict(int1=1, int2=0, int3=0, int4=0, int5=z, int6=0, startFrame=f0, endFrame=f0 + P['zoom_ramp'] - 1),
        dict(int1=0, int2=z, int3=0, int4=0, int5=z, int6=0, startFrame=f0 + P['zoom_ramp'], endFrame=f0 + P['zoom_until'])]))
    tpl = copy.deepcopy(_unit_tpl([w], 66))
    pos = [cu for o in tpl['skillInfoObjectList'] for cu in o['ceventCameraUnitList'] if cu['unitSlotNum'] == 0]
    assert pos and pos[0]['data']['bsdxInfoCollectionList'][0]['typeList'] == [1], 'GEKKA_CAMERA: no camera position template'
    pos = pos[0]

    def cam(f0, f1, a, b):
        p_ = copy.deepcopy(pos); p_['data']['offset'] = 0
        h = dict(ceventCameraUnitQuantity=3, description='高さ', buffer=1, unitSlotNum=3,
                 data=dict(int1=0, int2=a, int3=0, int4=b, offset=0, typeId=0, startFrame=0, endFrame=f1 - f0))
        o = copy.deepcopy(tpl['skillInfoObjectList'][0])
        o.update(ceventCameraUnitList=[p_, h], offset=0, startFrame=f0, endFrame=f1)
        return o

    u = copy.deepcopy(tpl)
    u['skillInfoObjectList'] = [cam(f0, f0 + P['hold'] - 1, 0, P['h0']), cam(f0 + P['hold'], L - 1, P['h0'], P['h1'])]
    u['skillInfoUnknownList'] = []
    _put_unit(turn, u)
    log.append('GEKKA_CAMERA %s turn %d（%dF）: 拡大縮小 F%d-%d 前 -> %d、F%d-%d %d / カメラ 自分基準 高さ F%d-%d 0 -> %d、F%d-%d %d -> %d（甲 月華衝 turn 5 F17 以後の写し、F%d から）' % (
        P['skill'], P['turn'], L, f0, f0 + P['zoom_ramp'] - 1, z, f0 + P['zoom_ramp'], f0 + P['zoom_until'], z, f0, f0 + P['hold'] - 1, P['h0'], f0 + P['hold'], L - 1, P['h0'], P['h1'], f0))
    return si


def slide_airfall(w, log):
    """SLIDE_AIRFALL（作者 11/22、調査記録 90 §3）: スライディングキックの蹴り（turn 1）の F from_frame に 縦速度 fall px/F（slot 19）を足し、
    当たった後・蹴り終わり（turn 2）の F0 の 縦速度 0 も fall に。重力 0（slot 21）はそのままなので、技の間 一定の速さで斜め下へ落ちる
    （甲 スライディングキックLv3 turn 0: F11 から前進、F14 に 縦速度 -5・重力 0、当たった後の硬直も落ち続ける）。地上では下に動かない。"""
    P = {k: MT.p('SLIDE_AIRFALL', k) for k in ('skill', 'kick_turn', 'after_turns', 'from_frame', 'fall')}
    si, s = _skill(w, P['skill'])
    ph = s['phasesInfo']
    kt = ph[P['kick_turn']]
    assert _objs(kt, 41) and _objs(kt, 18), 'SLIDE_AIRFALL: turn %d is not the kick' % P['kick_turn']
    for t in [P['kick_turn']] + list(P['after_turns']):
        o19, o21 = _objs(ph[t], 19), _objs(ph[t], 21)
        assert len(o19) == 1 and o19[0]['startFrame'] == 0 and o19[0]['int5'] == 0 and not any(o19[0].get('int%d' % k) for k in range(1, 7)), \
            'SLIDE_AIRFALL: turn %d slot 19 is not a single 縦速度 0 at F0' % t
        assert len(o21) == 1 and not any(o21[0].get('int%d' % k) for k in range(1, 7)), 'SLIDE_AIRFALL: turn %d gravity is not 0' % t
    e = _end_jump(kt)
    assert P['from_frame'] < e['startFrame'], 'SLIDE_AIRFALL: from_frame after the kick ends'
    o = copy.deepcopy(_objs(kt, 19)[0])
    o.update(int5=P['fall'], startFrame=P['from_frame'], endFrame=P['from_frame'], offset=0)
    _units(kt, 19)[0]['skillInfoObjectList'].append(o)
    for t in P['after_turns']:
        _objs(ph[t], 19)[0]['int5'] = P['fall']
    log.append('SLIDE_AIRFALL %s: turn %d F%d 縦速度 0 -> %d px/F（重力 0 のまま）、%s F0 縦速度 0 -> %d（甲 スライディングキックLv3 と同じ角度 約 28°。甲は前進が遅く F14 から縦 -5）' % (
        P['skill'], P['kick_turn'], P['from_frame'], P['fall'], '・'.join('turn %d' % t for t in P['after_turns']), P['fall']))
    return si


def cb_hitback(w, log):
    """CB_HITBACK（作者 11/22、調査記録 91）: キャノンブレイカーの 1 撃目（turn の対メカの当たり、1 つだけ）ののけぞり 4 欄の
    被弾硬直 int3 / int4 を hitback に。欄 18-20 は処理タイプ 1（地上欄と同じ）だが、値もそろえておく。"""
    P = {k: MT.p('CB_HITBACK', k) for k in ('skill', 'turn', 'hitback')}
    si, s = _skill(w, P['skill'])
    t = s['phasesInfo'][P['turn']]
    hs = _objs(t, 41)
    assert len(hs) == 1 and hs[0]['hitCount'] == 1, 'CB_HITBACK: turn %d hits %d' % (P['turn'], len(hs))
    h = hs[0]
    nk = [hu for hu in h['ceventHitUnitList'] if hu['ceventHitUnitQuantity'] in (17, 18, 19, 20)]
    assert len(nk) == 4, 'CB_HITBACK: のけぞり units %d' % len(nk)
    old = sorted({(hu['data']['int3'], hu['data']['int4']) for hu in nk})
    assert all(a < P['hitback'] and b < P['hitback'] for a, b in old), 'CB_HITBACK: already %s' % old
    for hu in nk:
        hu['data']['int3'] = hu['data']['int4'] = P['hitback']
    log.append('CB_HITBACK %s: turn %d F%d-%d の当たり のけぞり 4 欄の被弾硬直 %s -> %d/%d（被弾側ヒットストップ %d・停止 %d はそのまま）' % (
        P['skill'], P['turn'], h['startFrame'], h['endFrame'], old, P['hitback'], P['hitback'], h['int15'], nk[0]['data']['int2']))
    return si


def cb_stop(w, log):
    """CB_STOP（作者 11/22、調査記録 91）: キャノンブレイカーの 1 撃目が当たった後のターン（turn 1 の「当たったら」の行き先）の全フレームに
    画面停止（slot 68）。値はターン 0（FC 演出）の画面停止と同じ。外したときのターン・連打のターンは触らない。"""
    P = {k: MT.p('CB_STOP', k) for k in ('skill', 'turn')}
    si, s = _skill(w, P['skill'])
    ph = s['phasesInfo']
    hj = [o for o in _objs(ph[1], 71) if o['bsdxInfoCollectionList1'][0]['typeList'] == [2, 6, 0, 0]]
    assert hj and all(o['bsdxInfoCollectionList2'][0]['paramList'] == [P['turn']] for o in hj[:1]), \
        'CB_STOP: turn 1 hit does not jump to turn %d' % P['turn']
    t = ph[P['turn']]
    assert not _objs(t, 41) and not _objs(t, 48), 'CB_STOP: turn %d attacks or fires' % P['turn']
    assert not any(_objs(t, k) for k in (61, 68, 69, 70)), 'CB_STOP: turn %d already has a screen effect' % P['turn']
    for i, t_ in enumerate(ph):
        if i not in (0, P['turn']):
            assert not _objs(t_, 68), 'CB_STOP: turn %d already stops the screen' % i
    u0 = _units(ph[0], 68)
    assert len(u0) == 1 and len(u0[0]['skillInfoObjectList']) == 1, 'CB_STOP: turn 0 screen stop'
    L = max(o['endFrame'] for o in _objs(t, 0)) + 1
    e = _end_jump(t)
    assert e['startFrame'] == L - 1, 'CB_STOP: turn %d ends at F%d, sprite %dF' % (P['turn'], e['startFrame'], L)
    v = {k: x for k, x in u0[0]['skillInfoObjectList'][0].items() if k not in ('offset', 'startFrame', 'endFrame')}
    _put_unit(t, _mk_unit(u0[0], [dict(copy.deepcopy(v), startFrame=0, endFrame=L - 1)]))
    log.append('CB_STOP %s: turn %d（当たったとき、%dF）の F0-%d に画面停止（turn 0 と同じ値）' % (P['skill'], P['turn'], L, L - 1))
    return si


def msweeper_air(w, log):
    """MSWEEPER_AIR（作者 11/22、調査記録 90 §4）: マインスイーパの弾（Tama04）の対メカの当たりの 空中欄（欄 18、自前の値）のスカラ
    （停止時間・ノックバック・のけぞり速度・減速率・吹き飛び規模・重力など）を、ターンごとに甲の値（params の cols）に丸ごと置き換える。
    turn 0（直撃）= 甲 Tama05「マインスイーパ：甲」turn 0 の当たり（空中欄は地上欄と同じ）、turn 1（爆発）= 甲が着弾で出す Bomb「マインナックル：甲」の空中欄。
    のけぞり方向（欄の中の ceventNokezoriUnitList）・地上欄・空中→地上欄・ダウン欄・威力・ヒットストップ・SE はそのまま。"""
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'MSWEEPER_AIR: Tama04.waz not among the modified files'
    name = MT.p('MSWEEPER_AIR', 'bullet')
    bi, b = _skill(tw, name)
    u = {n for _, n in _fire_users(None).get((4, bi), ())}
    assert u == {MT.p('MSWEEPER_AIR', 'skill')}, 'MSWEEPER_AIR: %s fired by %s' % (name, u)
    KEYS = ('int1', 'short1', 'int2', 'int3', 'int4', 'int5', 'int6', 'int7', 'int8', 'int9', 'int10', 'int11', 'int12', 'int13')
    done = []
    for t, ref in sorted(MT.p('MSWEEPER_AIR', 'turns').items()):
        hs = _objs(b['phasesInfo'][t], 41)
        assert len(hs) == 1, 'MSWEEPER_AIR: turn %d mech hits %d' % (t, len(hs))
        c = _cols(hs[0])
        assert set(c) == {17, 18, 19, 20} and c[18].get('int1') == 0, 'MSWEEPER_AIR: turn %d air column is not its own' % t
        before = {x: c[18].get(x, 0) for x in KEYS if c[18].get(x, 0)}
        for x in KEYS:
            c[18][x] = ref['col'].get(x, 0)
        after = {x: c[18][x] for x in KEYS if c[18][x]}
        done.append('turn %d（%s、甲 %s）%s -> %s' % (t, ref['part'], ref['src'], before, after))
    log.append('MSWEEPER_AIR %s 空中欄（欄 18）: %s' % (name, ' / '.join(done)))
    return [(BULLET_WAZ, bi)]


def msweeper_cancel(w, log):
    """MSWEEPER_CANCEL（作者 11/22、調査記録 100）: マインスイーパの撃ち終わりの硬直（params の turn）の F0 にある ｷｬﾝｾﾙﾌﾗｸﾞ（slot 47）
    = 0（原作 ph2 の flags bit7 ｷｬﾝｾﾙﾌﾗｸﾞ初期化、HITCANCEL）を 1 にする。撃った時点（turn 1 F0 = 1）から技の終わりまで武装キャンセル可
    = 甲 マインスイーパLv3（発射フレームに slot 47 = 1、以後 0 に戻さない）と同じ。EX キャンセルの区間（値 3）は触らない（EXCANCEL が後で置く）。"""
    P = {k: MT.p('MSWEEPER_CANCEL', k) for k in ('skill', 'turn')}
    si, s = _skill(w, P['skill'])
    ph = s['phasesInfo']
    assert P['turn'] == len(ph) - 1, 'MSWEEPER_CANCEL: turn %d is not the last of %d' % (P['turn'], len(ph))
    prev = _objs(ph[P['turn'] - 1], 47)
    assert [(o['startFrame'], o.get('int4')) for o in prev if o.get('int4') != 3] == [(0, 1)], 'MSWEEPER_CANCEL: fire turn slot 47 %s' % prev
    c = [o for o in _objs(ph[P['turn']], 47) if o.get('int4') != 3]
    assert [(o['startFrame'], o['endFrame'], o.get('int4')) for o in c] == [(0, 0, 0)], 'MSWEEPER_CANCEL: turn %d slot 47 %s' % (P['turn'], c)
    c[0]['int4'] = 1
    log.append('MSWEEPER_CANCEL %s: turn %d（撃ち終わりの硬直）F0 の ｷｬﾝｾﾙﾌﾗｸﾞ 0 -> 1（撃った時点から技の終わりまで武装キャンセル可、甲と同じ）' % (P['skill'], P['turn']))
    return si


def megamine_hold(w, log):
    """MEGAMINE_HOLD（作者 11/22、調査記録 98）: メガマインの弾（Tama04「地雷 Lv4（透移植弾359）」）の爆発のターン（params の turns）に
    縦速度 0（slot 19、F0 からターンの終わりまで毎フレーム）と 重力 0（slot 21、F0）を置く。発射の重力 60（slot 48 sub 33）が弾に残り、
    空中で爆発すると爆風が落ちていくため。毎フレーム縦速度を書くと重力に影響されない（06 §2、0x60c206）。
    設置・落下中（turn 0）はそのまま（地雷は今までどおり地面へ落ちる）。横の動き・当たり・絵はそのまま。"""
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'MEGAMINE_HOLD: Tama04.waz not among the modified files'
    name = MT.p('MEGAMINE_HOLD', 'bullet')
    bi, b = _skill(tw, name)
    u = {n for _, n in _fire_users(None).get((4, bi), ())}
    assert u == {MT.p('MEGAMINE_HOLD', 'skill')}, 'MEGAMINE_HOLD: %s fired by %s' % (name, u)
    t19, t21 = _unit_tpl([tw], 19), _unit_tpl([tw], 21)
    Z = dict(int1=0, int2=0, int3=0, int4=0, int5=0, int6=0)
    done = []
    for t in MT.p('MEGAMINE_HOLD', 'turns'):
        turn = b['phasesInfo'][t]
        assert not _objs(turn, 19) and not _objs(turn, 21), 'MEGAMINE_HOLD: turn %d already has slot 19 / 21' % t
        assert _objs(turn, 41), 'MEGAMINE_HOLD: turn %d has no hit (not the explosion)' % t
        L = _end_jump(turn)['startFrame'] + 1
        _put_unit(turn, _mk_unit(t19, [dict(Z, startFrame=0, endFrame=L - 1)]))
        _put_unit(turn, _mk_unit(t21, [dict(Z, startFrame=0, endFrame=0)]))
        done.append('turn %d（%dF）' % (t, L))
    log.append('MEGAMINE_HOLD %s: %s に 縦速度 0（毎フレーム）・重力 0 を追加（爆風が落ちない）' % (name, '・'.join(done)))
    return [(BULLET_WAZ, bi)]


def spread_kou(w, log):
    """SPREAD_KOU（作者 11/22、調査記録 99）: 対空スプレッドボムの弾（Tama04）の対メカの当たりの のけぞり 4 欄（17-20）のスカラと のけぞり方向を、
    ターンごとに甲 Tama04「対空スプレッドボム：甲Lv3」の同じターンの値（params の turns）に丸ごと置き換える。'same' の欄は処理タイプ 1（地上欄と同じ）・値も地上欄。
    威力・最低値・補正・ヒット間隔（SPREAD_EVERYF）・ヒットストップ・SE・エフェクトはそのまま。"""
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, 'SPREAD_KOU: Tama04.waz not among the modified files'
    name = MT.p('SPREAD_KOU', 'bullet')
    bi, b = _skill(tw, name)
    u = {n for _, n in _fire_users(None).get((4, bi), ())}
    assert u == {MT.p('SPREAD_KOU', 'skill')}, 'SPREAD_KOU: %s fired by %s' % (name, u)
    KEYS = ('int1', 'short1', 'int2', 'int3', 'int4', 'int5', 'int6', 'int7', 'int8', 'int9', 'int10', 'int11', 'int12', 'int13')
    DIRK = ('typeList', 'paramList', 'intList4')
    done = []
    for t, ref in sorted(MT.p('SPREAD_KOU', 'turns').items()):
        hs = _objs(b['phasesInfo'][t], 41)
        assert len(hs) == 1, 'SPREAD_KOU: turn %d mech hits %d' % (t, len(hs))
        c = _cols(hs[0])
        assert set(c) == {17, 18, 19, 20} and set(ref) == {17, 18, 19, 20}, 'SPREAD_KOU: turn %d columns %s' % (t, sorted(c))
        ch = []
        for k in (17, 18, 19, 20):
            r = ref[k]
            if r == 'same':
                r = dict(ref[17], int1=1)
            nk = c[k].get('ceventNokezoriUnitList') or []
            assert len(nk) == 1 and len(nk[0]['data']['bsdxInfoCollectionList']) == 1, 'SPREAD_KOU: turn %d col %d direction units' % (t, k)
            d = nk[0]['data']['bsdxInfoCollectionList'][0]
            before = {x: c[k].get(x, 0) for x in KEYS if c[k].get(x, 0)}
            bdir = d['typeList']
            for x in KEYS:
                c[k][x] = r.get(x, 0)
            for x in DIRK:
                d[x] = list(r['dir'][x])
            after = {x: c[k][x] for x in KEYS if c[k][x]}
            ch.append('欄 %d %s%s -> %s%s' % (k, before, bdir, after, d['typeList']))
        done.append('turn %d: %s' % (t, ' / '.join(ch)))
    log.append('SPREAD_KOU %s のけぞり 4 欄を甲（%s）と同じに: %s' % (name, MT.p('SPREAD_KOU', 'kou'), ' | '.join(done)))
    return [(BULLET_WAZ, bi)]


def spread_self(w, log):
    """SPREAD_SELF（作者 11/23、調査記録 107）: 対空スプレッドボム（透の技、1 ターン）で自機が受ける慣性を甲と同じ形に。
    drop のスロット（技の速度 18・方向 15・縦速度 19・重力 21・SD 補正率 30）を外し、移動補正率 slot 24 を move の直線（mode 1 = 前の値から）に置き換える。"""
    si, s = _skill(w, MT.p('SPREAD_SELF', 'skill'))
    ph = s['phasesInfo']
    assert len(ph) == 1, 'SPREAD_SELF: expected 1 turn (%d)' % len(ph)
    turn = ph[0]
    L = _end_jump(turn)['startFrame'] + 1
    assert L == 68, 'SPREAD_SELF: turn length %d (expected 68)' % L
    o24 = _objs(turn, 24)
    assert len(o24) == 1 and o24[0]['startFrame'] == 0 and o24[0]['int1'] == 0 and o24[0]['int4'] == 50, 'SPREAD_SELF: slot 24 not a single F0 50'
    o30 = _objs(turn, 30)
    assert len(o30) == 1 and o30[0]['int4'] == 0, 'SPREAD_SELF: slot 30 not a single F0 0'
    dropped = []
    for q in MT.p('SPREAD_SELF', 'drop'):
        n = _drop(turn, q)
        assert n, 'SPREAD_SELF: slot %d not present' % q
        dropped.append('slot %d x%d' % (q, n))
    u24 = _units(turn, 24)[0]
    tpl = o24[0]
    objs = []
    for a, b, v in MT.p('SPREAD_SELF', 'move'):
        assert 0 <= a <= b < L
        objs.append(dict(tpl, int1=1, int4=v, offset=0, startFrame=a, endFrame=b))
    u24['skillInfoObjectList'] = objs
    log.append('SPREAD_SELF %s: %s を外す（甲と同じく前の勢い・重力・SD 慣性が残る）、移動補正率 F0 50 -> %s' % (
        s['skillNameJapanese'], '・'.join(dropped), ' / '.join('F%d-%d -> %d' % m for m in MT.p('SPREAD_SELF', 'move'))))
    return si


def _bit(tid, name, skill):
    tw = _NEW.get(BULLET_WAZ)
    assert tw is not None, '%s: Tama04.waz not among the modified files' % tid
    bi, b = _skill(tw, name)
    u = {n for _, n in _fire_users(None).get((4, bi), ())}
    assert u == {skill}, '%s: %s fired by %s' % (tid, name, u)
    return bi, b


def gbit_orbit(w, log):
    """GBIT_ORBIT（作者 11/22、調査記録 102）: ガトリングビット本体の周回の距離。turn 0（近づく）の「距離→□以下なら（2,3,6,2）→ 周回」と、
    周回のターンの「距離→□以上なら（2,3,6,3、DISTOUT）→ turn 0」の距離を params の dist（前 -> 後）で置き換える。
    周回は敵の方向 ±90° に進むので距離は少しずつ広がり、dist_out で敵へ戻る（= 200〜300 の帯を回る）。両方 2/3 にして帯ごと 133〜200 に。"""
    bi, b = _bit('GBIT_ORBIT', MT.p('GBIT_ORBIT', 'bullet'), MT.p('GBIT_ORBIT', 'skill'))
    dist = dict(MT.p('GBIT_ORBIT', 'dist'))
    ch = []
    for t, turn in enumerate(b['phasesInfo']):
        for o in _objs(turn, 71):
            for c in o['bsdxInfoCollectionList1']:
                if c['typeList'][:3] == [2, 3, 6]:
                    v = c['paramList'][0]
                    assert v in dist, 'GBIT_ORBIT: turn %d distance %s not in %s' % (t, v, dist)
                    c['paramList'][0] = dist[v]
                    ch.append('turn %d 距離→%d%s -> %d' % (t, v, '以下' if c['typeList'][3] == 2 else '以上', dist[v]))
    assert len(ch) == 3, 'GBIT_ORBIT: expected 3 distance terms (turn 0 以下・turn 1 / 3 以上), got %s' % ch
    log.append('GBIT_ORBIT %s: %s' % (MT.p('GBIT_ORBIT', 'bullet'), ', '.join(ch)))
    return [(BULLET_WAZ, bi)]


def bit_alttrack(w, log):
    """BIT_ALTTRACK（作者 11/22、調査記録 102）: ガトリングビット・レーザービットのビット本体の指定ターンに、高度の追尾（slot 20 追尾ジャンプ力、
    「最大増分(1=0.01)」の 1 項目 int1 / int2〜int5）を F0 からターンの終わりまで置く。水無月真のファイアビット（Tama03「ファイアビット：真」
    turn 0・1、int1 0、10〜10、F0-183）と同じ値。雛形は Tama04 の slot 20（最大増分 1 項目だけのもの）を写して値を入れ替える。"""
    tw = _NEW.get(BULLET_WAZ)
    tpl = None
    for s_ in tw['skillList']:
        for t_ in (s_ or {}).get('phasesInfo', ()):
            for u_ in _units(t_, 20):
                os_ = u_['skillInfoObjectList']
                if tpl is None and os_ and len(os_[0].get('ceventHeightUnitList') or []) == 1 and os_[0]['ceventHeightUnitList'][0]['unitSlotNum'] == 1:
                    tpl = u_
    assert tpl is not None, 'BIT_ALTTRACK: no slot 20 template (one 最大増分 item) in Tama04'
    i1, (lo, hi) = MT.p('BIT_ALTTRACK', 'int1'), MT.p('BIT_ALTTRACK', 'max_inc')
    out, done = [], []
    for name, v in MT.p('BIT_ALTTRACK', 'bits').items():
        bi, b = _bit('BIT_ALTTRACK', name, v['skill'])
        ts = []
        for t in v['turns']:
            turn = b['phasesInfo'][t]
            assert not _objs(turn, 20), 'BIT_ALTTRACK: %s turn %d already has slot 20' % (name, t)
            assert _objs(turn, 15), 'BIT_ALTTRACK: %s turn %d has no direction (not a moving turn)' % (name, t)
            L = _end_jump(turn)['startFrame'] + 1
            u = copy.deepcopy(tpl)
            o = u['skillInfoObjectList'][0]
            u['skillInfoObjectList'] = [o]
            u['skillInfoUnknownList'] = []
            o.update(offset=0, int1=i1, startFrame=0, endFrame=L - 1)
            hu = o['ceventHeightUnitList'][0]['data']
            hu.update(offset=0, int1=0, int2=lo, int3=0, int4=0, int5=hi, int6=0, startFrame=0, endFrame=L - 1)
            _put_unit(turn, u)
            ts.append('turn %d（%dF）' % (t, L))
        done.append('%s %s' % (v['skill'], '・'.join(ts)))
        out.append((BULLET_WAZ, bi))
    log.append('BIT_ALTTRACK 高度追尾（slot 20 最大増分 %d〜%d）: %s' % (lo, hi, ', '.join(done)))
    return out


def gbit_airgrav(w, log):
    """GBIT_AIRGRAV（作者 11/22、調査記録 102）: ガトリングビットの弾の対メカの当たりの 空中欄 18 の 吹き飛び重力（int11）を rate に（SG_AIRGRAV と同じ）。"""
    bi, b = _bit('GBIT_AIRGRAV', MT.p('GBIT_AIRGRAV', 'bullet'), MT.p('GBIT_AIRGRAV', 'skill'))
    r = MT.p('GBIT_AIRGRAV', 'rate')
    ch = []
    for t, turn in enumerate(b['phasesInfo']):
        for h in _objs(turn, 41):
            c = _cols(h)
            assert 18 in c and not c[18].get('int1'), 'GBIT_AIRGRAV: turn %d air column is not its own' % t
            ch.append('turn %d 欄 18 %d -> %d' % (t, c[18].get('int11', 0), r))
            c[18]['int11'] = r
    assert len(ch) == 1, 'GBIT_AIRGRAV: expected one mech hit, got %s' % ch
    log.append('GBIT_AIRGRAV 吹き飛び重力（空中欄）%s: %s' % (MT.p('GBIT_AIRGRAV', 'bullet'), ', '.join(ch)))
    return [(BULLET_WAZ, bi)]


def gbit_airpush(w, log):
    """GBIT_AIRPUSH（作者 11/23、調査記録 105）: ガトリングビットの弾の対メカの当たりの 空中欄 18 の 横の押し
    （のけぞり速度 int8 px/F・速度減速率 int9、毎 F int9/100 px/F 減速）を v / decel に。重力（int11）・吹き飛び規模（int10）はそのまま。"""
    bi, b = _bit('GBIT_AIRPUSH', MT.p('GBIT_AIRPUSH', 'bullet'), MT.p('GBIT_AIRPUSH', 'skill'))
    v, a = MT.p('GBIT_AIRPUSH', 'v'), MT.p('GBIT_AIRPUSH', 'decel')
    assert v > 0 and a > 0, 'GBIT_AIRPUSH: v / decel must be positive'
    ch = []
    for t, turn in enumerate(b['phasesInfo']):
        for h in _objs(turn, 41):
            c = _cols(h)
            assert 18 in c and not c[18].get('int1'), 'GBIT_AIRPUSH: turn %d air column is not its own' % t
            v0, a0 = c[18].get('int8', 0), c[18].get('int9', 0)
            assert v0 > 0 and a0 > 0, 'GBIT_AIRPUSH: turn %d push %d/%d' % (t, v0, a0)
            ch.append('turn %d 欄 18 %d/%d -> %d/%d' % (t, v0, a0, v, a))
            c[18]['int8'], c[18]['int9'] = v, a
    assert len(ch) == 1, 'GBIT_AIRPUSH: expected one mech hit, got %s' % ch
    log.append('GBIT_AIRPUSH 横の押し（空中欄、のけぞり速度/減速率）%s: %s' % (MT.p('GBIT_AIRPUSH', 'bullet'), ', '.join(ch)))
    return [(BULLET_WAZ, bi)]


ORDER = [('ARMOR_CONT', armor_cont), ('IF_RECT', if_rect), ('T150_VOLLEYS', t150_volleys), ('GF_SIZE', gf_size), ('GF_PUSH', gf_push), ('DRILL_FACE', drill_face), ('TKO_TUNE', tko_tune), ('TKO_DOWNLIFT', tko_downlift), ('TKO_STAGE', tko_stage), ('GEKKA_LAUNCH', gekka_launch),
         ('GS_RECOIL', gs_recoil), ('GS_INTERVAL', gs_interval), ('GS_GRAVITY', gs_gravity), ('SEIRYU_VINERTIA', seiryu_vinertia), ('SEIRYU_NOKEVZ', seiryu_nokevz),
         ('SW_INERTIA', sw_inertia), ('SW_ARMOR', sw_armor), ('SW_LAUNCH', sw_launch), ('SW_WIREFLOAT', sw_wirefloat), ('SW_AIRLIFT', sw_airlift), ('SW_NOKEVZ', sw_nokevz),
         ('SG_AIRGRAV', sg_airgrav), ('BU_FALL', bu_fall), ('JK_FALL', jk_fall), ('GALAXY_AIRRISE', galaxy_airrise), ('GALAXY_RELEASE', galaxy_release), ('GALAXY_DIVESPEED', galaxy_divespeed), ('GALAXY_RISE', galaxy_rise), ('DSABER_LAUNCH', dsaber_launch), ('DSABER_AIRGRAV', dsaber_airgrav), ('GRENADE_KOU', grenade_kou),
         ('BULLET_NOCANCEL', bullet_nocancel), ('ANTIBULLET_POWER', antibullet_power), ('PHOTON_NOWALL', photon_nowall), ('STUNROD_DOT', stunrod_dot), ('SAT_HOLD', sat_hold), ('SAT_RIDE', sat_ride), ('SAT_AIM', sat_aim), ('IF_STAGE', if_stage), ('ND_SPEED', nd_speed), ('HAMMER_NOTIMEOUT', hammer_notimeout), ('SHIELD_INERTIA', shield_inertia), ('SINK_MOD', sink_mod), ('GEKKA_CAMERA', gekka_camera), ('SLIDE_AIRFALL', slide_airfall), ('MSWEEPER_AIR', msweeper_air), ('MSWEEPER_CANCEL', msweeper_cancel), ('MEGAMINE_HOLD', megamine_hold), ('SPREAD_KOU', spread_kou), ('SPREAD_SELF', spread_self), ('GBIT_ORBIT', gbit_orbit), ('BIT_ALTTRACK', bit_alttrack), ('GBIT_AIRGRAV', gbit_airgrav), ('GBIT_AIRPUSH', gbit_airpush), ('CB_HITBACK', cb_hitback), ('CB_STOP', cb_stop), ('EXCANCEL', ex_cancel),   # EXCANCEL はターン番号で指定する項目の最後
         ('GROUND_ARMOR', lambda w, log: GA.ground_armor(w, log, MT.p('GROUND_ARMOR', 'skills'), SELF_WAZ))]   # EXCANCEL の後（turn 0 を当てた後の形で写す）
_known = {t['id'] for t in MT.TWEAKS if t['kind'] == '挙動'}
assert _known == {k for k, _ in ORDER}, 'modified_tweaks 挙動 items without an implementation (or vice versa): %s' % (
    _known ^ {k for k, _ in ORDER})


def apply(new, self_waz, bullet_waz, spm_file, eft_file, eft_slot, effect_waz=None):
    """new: {file name: modified json}（bfe2bsdx_balance.apply の結果、in place で変える）。
    戻り値の touched は {file name: 変えた技の index の集合}（11/12 から Tooru.waz 以外も入る）。"""
    global _NEW, SELF_WAZ, BULLET_WAZ, SPM_FILE, EFT_FILE, EFT_SLOT, EFFECT_WAZ
    _NEW = new
    SELF_WAZ, BULLET_WAZ, SPM_FILE, EFT_FILE, EFT_SLOT, EFFECT_WAZ = self_waz, bullet_waz, spm_file, eft_file, eft_slot, effect_waz
    log, touched = [], {}
    w = new.get(SELF_WAZ)
    assert w is not None, 'modified behavior: %s not among the modified files' % SELF_WAZ
    for tid, fn in ORDER:
        if MT.on(tid):
            r = fn(w, log)
            for f_, si in (r if isinstance(r, list) else [(SELF_WAZ, r)]):
                touched.setdefault(f_, set()).add(si)
        else:
            log.append('%s: off' % tid)
    return log, touched
