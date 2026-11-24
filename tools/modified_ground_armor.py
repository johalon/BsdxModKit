#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""modified_ground_armor.py — 改善版だけ: 地上で出した技に装甲を付ける（GROUND_ARMOR、ユーザー 2026-11-16、調査記録 65・66）。

「地上コンボにアーマーを付ける」変更はこのファイルと、tools/modified_tweaks.py の GROUND_ARMOR の 1 行だけにまとめてある。
  * 取りやめ（一時的）: modified_tweaks.py の GROUND_ARMOR を on=False にしてビルド（前の改善版の sha256 に戻る）。
  * 取りやめ（完全に）: 上の行、bfe2bsdx_modified_behavior.py の ORDER の ('GROUND_ARMOR', …) の 1 行と import、このファイルを消す。
  * 値の調整: modified_tweaks.py の GROUND_ARMOR の params（skills = 技 → (段階, 装甲を 0 に戻す (ターン, F) の並び)）。
原作再現版（3b）には何もしない。

やり方（技ごと）:
  1. 今の turn 0 を 2 つ写して末尾に足す（turn n = 地上版、turn n+1 = 空中版）。地上版の F0 に装甲（slot 36）= 段階。
  2. 元の turn 0 は長さ 0 の振り分けターンにする: F0「着地していたら → turn n」、ほか → turn n+1
     （タックル・ブーストキックの turn 0 と同じ形。条件 [2,7,16] は Tooru.waz の既存の分岐から写す）。
  3. 写しのジャンプは元の turn 0 と同じ行き先なので、turn 1 以降は地上・空中で共通のまま、番号も変わらない。
  4. 指定の (ターン, F) に「装甲 0」を置く。ターン 0 の指定は地上版の写し（turn n）に置く。共通のターンに置いた 0 は、
     空中版ではもともと 0 なので何も変えない。
EXCANCEL などターン番号で指定する項目の後に当てる（写しは当てた後の turn 0 をそのまま写す）。
"""
import copy

ARMOR_SLOT = 36
JUMP_SLOT = 71


def _units(turn, slot):
    return [u for u in turn['skillUnitCollection'] if u['unitQuantity'] == slot]


def _objs(turn, slot):
    return [o for u in _units(turn, slot) for o in u['skillInfoObjectList']]


def _put(turn, tpl_u, objs):
    """slot 36 のユニットを番号順の位置に足す（このターンに slot 36 が無いことは呼ぶ側で確認済み）。"""
    u = copy.deepcopy(tpl_u)
    u['skillInfoObjectList'] = objs
    uc = turn['skillUnitCollection']
    k = next((i for i, x in enumerate(uc) if x['unitQuantity'] > ARMOR_SLOT), len(uc))
    uc.insert(k, u)


def _armor_obj(tpl_o, level, frame):
    o = copy.deepcopy(tpl_o)
    o.update(int1=0, int2=0, int3=0, int4=level, startFrame=frame, endFrame=frame, offset=0)
    return o


def _samples(w):
    """slot 36 のユニットと、「着地していたら → turn N」（[2,7,16]、NOT なし）の分岐を Tooru.waz の既存の技から取る。"""
    tpl_u = land = None
    for s in w['skillList']:
        for turn in (s or {}).get('phasesInfo', []):
            for u in _units(turn, ARMOR_SLOT):
                tpl_u = tpl_u or u
            for o in _objs(turn, JUMP_SLOT):
                c = o['bsdxInfoCollectionList1']
                if land is None and len(c) == 1 and c[0]['typeList'] == [2, 7, 16] and not c[0]['int2'] and \
                        o['bsdxInfoCollectionList2'][0]['typeList'] == [0, 1]:
                    land = o
    assert tpl_u is not None and land is not None, 'GROUND_ARMOR: no slot 36 / 着地していたら sample'
    return tpl_u, land


def _last_frame(turn):
    return max(o['endFrame'] for o in _objs(turn, JUMP_SLOT))


def ground_armor(w, log, skills, self_waz):
    """skills: {技名: (段階, [(ターン, F), …])}（装甲を 0 に戻す場所。ターン番号は元の番号、0 は地上版の写し）。
    戻り値: [(self_waz, 技 index), …]。"""
    tpl_u, land = _samples(w)
    tpl_o = tpl_u['skillInfoObjectList'][0]
    out = []
    for name, (level, offs) in skills.items():
        hit = [(i, s) for i, s in enumerate(w['skillList']) if s and s.get('skillNameJapanese') == name]
        assert len(hit) == 1, 'GROUND_ARMOR: skill %s found %d times' % (name, len(hit))
        si, s = hit[0]
        ph = s['phasesInfo']; n = len(ph)
        assert 1 <= level <= 3 and offs, 'GROUND_ARMOR %s: level %s / off points %s' % (name, level, offs)
        assert s.get('phaseQuantity', n) == n and len(s.get('skillSuffixList', [])) == n, 'GROUND_ARMOR %s: turn count mismatch' % name
        # 前提: 装甲がまだ無い・turn 0 に地上/空中の分岐が無い・ジャンプは絶対番号か技の終わりで、turn 0 へ戻るものが無い
        for t, turn in enumerate(ph):
            assert not _units(turn, ARMOR_SLOT), 'GROUND_ARMOR %s: turn %d already has 装甲' % (name, t)
            for o in _objs(turn, JUMP_SLOT):
                j = o['bsdxInfoCollectionList2'][0]
                assert j['typeList'] in ([0, 1], [0, 2]), 'GROUND_ARMOR %s: turn %d jump type %s' % (name, t, j['typeList'])
                assert j['typeList'] == [0, 2] or 0 < j['paramList'][0] < n, 'GROUND_ARMOR %s: turn %d jumps to %s' % (name, t, j['paramList'])
                assert not (t == 0 and o['bsdxInfoCollectionList1'][0]['typeList'] == [2, 7, 16]), 'GROUND_ARMOR %s: turn 0 already dispatches' % name
        ends = [o for o in _objs(ph[0], JUMP_SLOT) if o['bsdxInfoCollectionList1'][0]['typeList'] == [0]]
        assert len(ends) == 1, 'GROUND_ARMOR %s: turn 0 has %d unconditional jumps' % (name, len(ends))
        for t, f in offs:
            assert 0 <= t < n and 0 <= f <= _last_frame(ph[t]), 'GROUND_ARMOR %s: off point T%d F%d is outside the turn' % (name, t, f)
        # 1. 地上版・空中版の写し
        ground, air = copy.deepcopy(ph[0]), copy.deepcopy(ph[0])
        # 2. 元の turn 0 を振り分けにする
        cond = copy.deepcopy(land); cond.update(startFrame=0, endFrame=0, offset=0)
        cond['bsdxInfoCollectionList2'][0]['paramList'] = [n]
        dflt = copy.deepcopy(ends[0]); dflt.update(startFrame=0, endFrame=0, offset=0)
        dflt['bsdxInfoCollectionList2'][0]['typeList'] = [0, 1]; dflt['bsdxInfoCollectionList2'][0]['paramList'] = [n + 1]
        u71 = copy.deepcopy(_units(ph[0], JUMP_SLOT)[0]); u71['skillInfoObjectList'] = [cond, dflt]
        ph[0] = {k: v for k, v in ph[0].items() if k != 'skillUnitCollection'}
        ph[0]['skillUnitCollection'] = [u71]
        ph.extend([ground, air])
        s['phaseQuantity'] = len(ph)
        suf = s['skillSuffixList']
        for t in (n, n + 1):
            x = copy.deepcopy(suf[0]); x['int1'] = t; suf.append(x)
        # 3. 装甲: 地上版の F0 に段階、指定の場所で 0
        put = {n: [_armor_obj(tpl_o, level, 0)]}
        for t, f in offs:
            put.setdefault(n if t == 0 else t, []).append(_armor_obj(tpl_o, 0, f))
        for t, objs in sorted(put.items()):
            _put(ph[t], tpl_u, sorted(objs, key=lambda o: o['startFrame']))
        out.append((self_waz, si))
        log.append('GROUND_ARMOR %s: 装甲 %d（地上で出したときだけ）。turn 0 を振り分け（着地していたら → turn %d 地上版、ほか → turn %d 空中版）、'
                   '装甲 0 は %s' % (name, level, n, n + 1, '・'.join('T%d F%d' % (n if t == 0 else t, f) for t, f in offs)))
    return out
