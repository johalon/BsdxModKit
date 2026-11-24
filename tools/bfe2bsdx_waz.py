#!/usr/bin/env python3
"""bfe2bsdx_waz.py - field-level conversion of BALDR FORCE EXE WAZ skills (mech moves) AND Tama.dat entries (bullets,
explosions) into BALDR SKY DiveX waz skills (NeXAS_DX JSON). A BSDX "template" skill (the same-named move of 甲/Kou for
mech moves, a vanilla bullet for Tama) is used only for the parts whose BFE semantics are unknown or have no BFE
counterpart (AI hints, inertia, slow-motion, screen effects, nokezori details, CPU escape...).
Library used by mods/phase3b_tooru/build_phase3b.py; rules in 調査記録 09 §3 / §8.

BFE (tools/bfe_waz.py named JSON, 調査記録 07 §3) -> BSDX (docs/formats/05_waz_field_dictionary.md):
  phase -> turn (1:1 index; an alg_list that repeats a phase gets extra cloned turns appended)
  sprite event -> slot 0 CEventSprite, one event per SPR pattern
       mech: anim = 60 + SPR slot of tooru.spm (spm -1) ; bullet/effect: anim = Effect.spr slot of tooru_eft.spm (spm 135)
       BFE pattern time = (wait+1) ticks (exe 0x413244: counter = wait+1) ; x2 frames (30 -> 60 fps)
       WAIT/anim_type 0..4 -> frame lengths ; se_play -> slot 52 ; armor_rate >= 3 -> slot 36 (mech)
       zoom type 1 -> slot 1 スプライト：拡大縮小 (256 = 1.0)
  speed init/final/step -> slot 18 (+ slot 15 角度指定→スプライト方向(BFE move_dir angle, deg) for mech); init 変更しない
       (-32768) = keep momentum: slot 18 start type 1 (前±0) -> 最終 at 増分/tick (assumed dash speed 16).
  sprite event 描画属性 3..9 -> slot 7 SpriteAttr (半透明 / 加算 / 減算, 100/50/25 %).  mech: value 1:1 (calibrated on Kou, 調査記録 09);
       bullet: value /2 (same pixel scale, 30 -> 60 fps; Kou ハンドガン 40->24 vs BFE 64)
  bullet move_dir 2 (ﾛｯｸｵﾝ敵方向) / 5 (常に標的位置) -> slot 15 target direction (Kou homing missile idiom) +
       slot 17 方向増分 = step/51.2 (BFE step 2048 = 8 deg/tick -> 40 = 4.0 deg/frame) ; init angle -> slot 16 (±range)
       moving bullets get slot 8 スプライト方向 = 移動方向 (BFE rotates bullet sprites the same way)
  jump x0>0 / dive -> slot 19 + 21 (mech calibration, 調査記録 09 §3)
  hit -> slot 41 (vs mech) / 42 (vs bullets) = template hit (deep copy) with 威力 = BFE/4, 最低 = /4, ヒット数, ヒットストップ,
       ヒットSE = BFE SE, ヒットエフェクト = converted BFE effect (fx.effect_target), 吹き飛び規模 = launch*20
       window: frames whose sprite event has attack bits (bullets without any: the whole turn)
  fire (Tama) -> slot 48 CEventEffect: target = converted BFE bullet (fx.tama_target); 同時発射数 = count, 発射方向補正 =
       angle_corr ± angle_rand, 速度 = bullet init speed /2 ; loops -> one spawn event every interval*2 F while the
       phase runs (max MAXSPAWN=64) ;
       fire_type 1/2 (laser / うねうね wire) and laser roots -> fx.line_chain (bfe2bsdx_line: the template's BSDX line
       chain with the BFE segment sprite / count / zoom / hits; a wire tip fired by the mech moves into the chain)
  muzzle / 常時 effect -> slot 48 spawn of the converted effect at fire time / turn start
  transitions (changes, slot 71):  value -1 = "next phase of the alg list" [guess, see 調査記録 09], 99 = end
       go_hit_mech  -> 残りメカＨＩＴ数→□なら(0)      go_hit_weapon -> 残り弾ＨＩＴ数→□なら(0)
       go_obstacle  -> 接触(18) / 重なり(18) (WALLHIT) go_land / anim_type 3 -> 着地していたら
       go_dist_in p -> 距離→□以下なら(p)              go_origin_null -> NULLなら (parent gone)
       go_air       -> frame-0 dispatch: 着地していたら => ground clone turn, else => air turn (甲 ブーストキック idiom)
       go_mech_alg / go_mech_spr (parent mech's phase / sprite changed) -> 親状態：ターン ; go_mech_skill -> 親状態：技
       go_hits_le_mech -> Kou T.K.O idiom ; go_end/go_anim_end -> turn end ; loops -> 汎用カウンタ
       go_counter -> 技カウンタ→□以上なら(action_counter x2) [guess] ; go_dist_out / go_hits_le_weapon -> ignored (reported)
"""
import copy, json, math, os, collections, itertools, struct
# COMBOV3 (user 2026-11-10): the per-technique tables (透: tools/bfe2bsdx_combo_v3.py) are passed by the mech's build as
# Converter(combo_v3=<module>) -- no table -> the COMBOCLS rule only (a same-named technique of another mech does not
# silently get 透's values; docs/porting/09_porting_another_mech.md §6 案 2, 2026-11-16).

from bfe2bsdx_common import SKILL_BASE   # mech anim = SKILL_BASE + BFE SPR slot (shared with bfe2bsdx_spm; 09 §6 案 7)
# BFE sprite event 描画属性 (0x443665: index -> object draw flags 0,1,2,4,8,0x400,0x800,0x10,0x1000,0x2000) ->
# BSDX slot 7 CEventSpriteAttr (int1 type: 7 半透明 / 9 加算描画 / 10 減算描画 ; int3 -> int8 value, 256 = 100 %)
SPRITE_ATTR = {3: (7, 128), 4: (9, 256), 5: (9, 128), 6: (9, 64), 7: (10, 256), 8: (10, 128), 9: (10, 64)}
# G 2026-11-11 (SINK): techniques that slide into the enemy in BFE (dash momentum + hit box on the own body, no push-out):
# names passed by the mech's build as Converter(sink_skills=...) (透: mods/phase3b_tooru/mech_config.SINK_SKILLS).
FACE_TYPES = (1, 3, 4)  # R 2026-11-18 FACEPHASE: BFE チップ向き 1 ﾛｯｸｵﾝした敵方向 / 3 敵座標（１回） / 4 敵座標（常時）
FACE_RATE = 300         # FACEPHASE 常に方向ﾁｪｯｸ: slot 10 方向増分 (0.1 deg/F) kept on, 甲 ダブルサブマシンガン T0 / the pre-hit window
FACE_SNAP = 9999        # FACEPHASE 段の開始時: 1F で向き直る (甲 ASスティンガー T2 F30 9999 -> F31 0, ◆青龍刀 T0 9999)
DASH_SPEED = 16        # BFE dash speed (exe 0x41a8c0): assumed current speed when a phase only decelerates (init 変更しない)
MAXSPAWN = 64          # max spawn events emitted for one BFE fire block (loops)
NOSE = {'Menu_Open', 'None', 'Ganbare', None}
# N 2026-11-01 (COMBOCLS, 調査記録 24 §N, user 11/01 23:29): combo correction by CLASS, not by proportion. Per technique, the
# size = max BFE ｺﾝﾎﾞ補正 over its hits (mech + bullets it fires); 近接/射撃 = BFE 技タイプ of the mech technique (header
# +0x29, the field 0x442340 uses to pick 打撃/射撃威力) <-> 甲 mek weaponType 0 / 1-2. 甲 classes: Lv3 techniques of
# Kou.mek (82 近接 / 69 射撃), size = max(基底+攻撃力補正+技終了時); BFE class bounds = the same rank shares (quantiles of
# the 40 / 47 透 techniques). Value = the 甲 class's most frequent (基底, 攻撃力補正, 技終了時) with 攻撃力補正 0 and with
# 初段の総補正 (基底+技終了時) and 途中の補正 (技終了時) not decreasing by class. Rows: (BFE max ｺﾝﾎﾞ補正 <= bound, (基底, mid, 終了時)).
# B 2026-11-04 (COMBOZERO, user 11/04, 調査記録 B3・B4): 透 had no technique in a 0 class (BFE ｺﾝﾎﾞ補正 0 is rare) while 28 %
# of 甲's 近接 / 29 % of its 射撃 Lv3 techniques carry 0/0/0 -> the lowest positive class (index 2: 近接 <= 50, 射撃 <= 2)
# gets 0/0/0 (was 0/0/7 and 0/0/5). Class bounds and indices unchanged.
COMBO_CLASS = {
    True: [(-1, (-12, 0, 7)), (0, (0, 0, 0)), (50, (0, 0, 0)), (100, (10, 0, 7)), (125, (0, 0, 20)), (200, (0, 0, 30)),
           (10 ** 9, (0, 0, 50))],                                   # 近接
    False: [(-1, (-10, 0, 0)), (0, (0, 0, 0)), (2, (0, 0, 0)), (5, (0, 0, 10)), (30, (0, 0, 20)), (10 ** 9, (0, 0, 30))],  # 射撃
}

# B 2026-11-04 (ROLEMIN, user 11/04, notes/B4_role_preserving_20261104.md): keep each technique's role in a combo (opener /
# finisher). BFE 0x442340 floors 威力 - combo at 最低威力 and the HG bonus (up to x2, rising while the victim is airborne)
# makes a big hit placed late worth more; DiveX has a percent-of-威力 combo rate and no such bonus by default. Rule per
# vs-mech hit: 表示 = floor(威力 x1.5); rho = min(1, max(BFE 威力 - ROLE_C, BFE 最低威力) x ROLE_G / BFE 威力);
# 最低値 = max(BFE 最低威力 x3/8, round(表示 x rho)). ROLE_C = 284.9 = the BFE ｺﾝﾎﾞ補正 x3/4 typically accumulated after 3
# techniques (3 x mean over 透's 80 techniques of the per-technique sum, 284.9); ROLE_G 2 = HG x2 at the end of the combo.
# The balanced pack (modified/) uses ROLE_G_MOD (tools/bfe2bsdx_balance.py): stored on the hit as '_bal' (popped by the
# build before writing; applied in its section I2). 11/05 (user: DiveX HG = +0.5 per gauge, a combo gains 0.4 gauge per
# loop -> +0.2 / +0.4, 調査記録 B4 §8): 0.8 -> 1.25 (原作比 イニ前 0.96 / イニ込み 1.95).
# Per-weapon adjustments on top of this: bfe2bsdx_balance.OVERRIDES (user 11/05).
import modified_tweaks as _MT        # 2026-11-10: 改善版の値は tools/modified_tweaks.py（ROLEMIN role_g）。off なら改善版でも 3b の最低値。
ROLE_C, ROLE_G, ROLE_G_MOD = 284.9, 2.0, _MT._BY['ROLEMIN']['params']['role_g']


def role_min(bfe_power, bfe_min, g):
    """ROLEMIN: 最低値 for a vs-mech hit of BFE 威力 / 最低威力 with HG factor g (never below BFE 最低威力 x3/8)."""
    base = max(1, round(bfe_min * 3 / 8))
    if bfe_power <= 0:
        return base
    disp = int(max(1, round(bfe_power / 4)) * 1.5)
    rho = min(1.0, max(bfe_power - ROLE_C, bfe_min) * g / bfe_power)
    return max(base, max(1, round(disp * rho)))


# ELEMENT (user 2026-11-14 「移植版で原作の属性に合わせてリアクションする。氷は除く。スタンロッドなど特別な事情を除き、
# 甲の一般的な F にする」「早期廃熱は移植版に含まれない」, 調査記録 53): BFE hit 属性 (hit +0x01: 0 無 1 炎 2 氷 3 雷; BFE only
# tints the victim, 0x44ea00) -> DiveX Hit +0x10 フラグ bit4 燃焼 / bit2 電撃 (state 6 / 5, 続く時間 = int22 F,
# 0x61fff7-0x620054, 調査記録 42). F = the most common value on the vanilla 甲 + shared waz hits (電撃 50: 55 hits,
# 燃焼 30: 15 hits); a hit without either keeps int22 1 (915 of 1167 hits). The template's bits 2/4/8/16 (甲's own
# reactions and 早期廃熱) are dropped on every converted vs-mech hit; 8/16 come back in modified/ only (EARLYHEAT).
ELEM_BITS = {1: (0x04, 30, '炎→燃焼'), 3: (0x02, 50, '雷→電撃')}
ELEM_MASK = 0x02 | 0x04 | 0x08 | 0x10
ELEM_I22_NONE = 1


def combo_class(melee, c):
    for i, (b, v) in enumerate(COMBO_CLASS[bool(melee)]):
        if c <= b:
            return i, v
    return len(COMBO_CLASS[bool(melee)]) - 1, COMBO_CLASS[bool(melee)][-1][1]


# ------------------------------------------------------------------------------------------- Term rendering / lookup
class TermText:
    def __init__(self, term_list):
        self.T = term_list

    def text(self, b):
        g = b['int1']; out = []; vals = list(b['paramList']); vi = 0
        for tok in b['typeList']:
            if g is None or g < 0 or g >= len(self.T):
                out.append('#%d' % tok); g = None; continue
            items = self.T[g]['termItemList'] or []
            if tok < 0 or tok >= len(items):
                out.append('#%d' % tok); g = None; continue
            it = items[tok]; s = it['termItemName']; code = it['termItemCodeName'] or ''
            n = s.count('$v') + code.count('$v')
            if it['param2'] in (-1, -2):
                n = max(n, -it['param2'])
            if n:
                s += '(' + ','.join(map(str, vals[vi:vi + n])) + ')'; vi += n
            out.append(s); g = it['param2'] if it['param2'] >= 0 else None
        return '→'.join(out)


class Lib:
    """event-object templates harvested from vanilla waz files (first file wins: pass Kou first)"""

    def __init__(self, waz, term_list, extra=()):
        self.tt = TermText(term_list)
        self.desc = {}
        self.conds = {}      # rendered condition text (params blanked) -> condition Term dict
        self.jumps = {}
        self.ev = {}         # (slot, typeId) -> sample object
        for w in (waz,) + tuple(extra):
            for s in w['skillList']:
                if not s:
                    continue
                for ph in s['phasesInfo']:
                    for u in ph['skillUnitCollection']:
                        self.desc.setdefault(u['unitQuantity'], u['unitDescription'])
                        for o in u['skillInfoObjectList']:
                            self.ev.setdefault((u['unitQuantity'], o['typeId']), o)
                            if o['typeId'] == 34:
                                for b in o['bsdxInfoCollectionList1']:
                                    # Term int2 = NOT (vanilla: Aki 立ち 「NOT 地面に着地していたら ⇒ 落下」, Akao
                                    # ハンマーブロウ 「NOT 着地していたら ⇒ 空中版」). The rendered key ignores int2, so keep a
                                    # positive sample: the first 「着地していたら」 seen (Kou) was negated, which inverted every
                                    # landing condition of the port (調査記録 14 §W0).
                                    k = self._key(b)
                                    if k not in self.conds or (self.conds[k]['int2'] and not b['int2']):
                                        self.conds[k] = b
                                b = o['bsdxInfoCollectionList2'][0]
                                self.jumps.setdefault(self._key(b), b)
        self.change_tpl = self.ev[(71, 34)]

    def _key(self, b):
        b2 = dict(b); b2['paramList'] = [0] * len(b['paramList'])
        return self.tt.text(b2)

    def cond(self, key, params=(), obj=None, neg=False):
        """obj: intList3 object selector (0 = self, 2 = parent, ...; vanilla usage counts in 調査記録 09);
        neg: Term int2 = 1 (NOT)"""
        b = copy.deepcopy(self.conds[key]); b['paramList'] = list(params) + b['paramList'][len(params):]
        if obj is not None:
            b['intList3'] = [obj, 0]
        b['int2'] = 1 if neg else 0
        return b

    def change(self, conds, jump, start, end):
        """conds: list of (key, params); jump: 'next' | 'end' | int turn"""
        o = copy.deepcopy(self.change_tpl)
        o['bsdxInfoCollectionList1'] = [self.cond(*c) for c in conds] if conds else [self.cond('無条件')]
        o['flag'] = len(o['bsdxInfoCollectionList1'])
        if jump == 'next':
            j = copy.deepcopy(self.jumps['ターンジャンプ→１つ先'])
        elif jump == 'end':
            j = copy.deepcopy(self.jumps['ターンジャンプ→終了'])
        else:
            j = copy.deepcopy(self.jumps['ターンジャンプ→指定(0)']); j['paramList'] = [int(jump)]
        o['bsdxInfoCollectionList2'] = [j]
        o['startFrame'], o['endFrame'] = start, end
        o['offset'] = 0
        return o

    def obj(self, slot, typeId, start, end, **kw):
        o = copy.deepcopy(self.ev[(slot, typeId)])
        for k in list(o):
            if k.startswith('int') or k.startswith('long'):
                o[k] = 0
        o.update(kw); o['startFrame'], o['endFrame'], o['offset'] = start, end, 0
        return o


def zoom_identity(z):
    """G 2026-11-03: the event leaves the sprite at 1.0 (init keep/256 and final keep/256, or no step) -> no slot 1."""
    one = lambda p: p[0] == -32768 or (p[0] == 256 and p[1] in (256, -32768))
    still = z['step'][0] in (0, -32768) and (z['step'][1] in (0, -32768))
    return one(z['init']) and (one(z['final']) or still)


def zoom_events(lib, z, t, n):
    """BFE sprite-event zoom (calc_zoom) -> slot 1 スプライト：拡大縮小 events. [確定: BaldrForce.exe, V 2026-10-27]
    Init 0x440dd0: each pair is a RANDOM RANGE [min, max]: cur = init, target = final, rate = step (sign toward target);
    -32768 = keep. Per tick 0x440ec0: cur += rate, clamped at target; sprite zoom (+0x20/+0x22) = cur (256 = 1.0), i.e.
    step is in zoom units PER TICK. (Old rule used init[0] = the range MINIMUM and stretched the change over the whole
    event: e.g. ★火花：青 (Tama 206, フォトンブラスター) 96..256 -> 0 at 8..16/tick became 96 -> 0 over 42F = much smaller.)
    -> start = mid ± half (int3), end = final mid reached after |d|/step ticks (x2 F), then held."""
    mid = lambda p: (p[0] + p[1]) / 2.0 if p[1] != -32768 else p[0]
    i0, f0, st = z['init'], z['final'], z['step']
    keep = i0[0] == -32768
    z0 = 256.0 if keep else mid(i0)
    z1 = z0 if f0[0] == -32768 else mid(f0)
    step = abs(mid(st)) if st[0] != -32768 else 0
    if step <= 0:
        z1 = z0        # G 2026-11-03: rate 0 never moves (0x440ec0: cur += 0, no clamp) -> the init holds (ｼｮｯﾄｶﾞﾝ 64..128 -> 0 step 0)
    d = n if (step <= 0 or z1 == z0) else max(1, int(round(abs(z1 - z0) / step * 2)))
    zend = z1 if d <= n else z0 + (z1 - z0) * n / float(d)
    # RANDLOW (2026-11-08): ValRandom width is one-sided (主値 + 0..幅) -> the start range [min, max] is min + 0..(max - min)
    start = dict(int1=1, int2=0, int3=0) if keep else (dict(int1=0, int2=int(i0[0]), int3=int(i0[1] - i0[0])) if i0[1] > i0[0]
                                                       else dict(int1=0, int2=int(round(z0)), int3=0))
    out = [lib.obj(1, 2, t, t + min(d, n) - 1, int4=0, int5=int(round(zend)), **start)]
    if d < n:
        out.append(lib.obj(1, 2, t + d, t + n - 1, int1=0, int2=int(round(z1)), int4=0, int5=int(round(z1))))
    return out


AIR_H = 160            # M 2026-10-28: assumed height (px) when a phase is entered in the air (go_air target)
BFE_LAUNCH_G = 128     # M 2026-10-28: BFE gravity of a launched (吹き飛び) mech, 1/256 px^.5 per tick [推定: 通常武装.mp4 /
                       # ｱｰﾑｱｯﾊﾟｰ→ｴｱ･ﾀｯｸﾙ.mp4: L5 rises ~10 ticks, L7 airborne ~26 ticks; the same value as JK's own jump]
                       # M 2026-10-29: = the base gravity block below (a launched mech has no skill block) [確定: exe]
BFE_BASE_G = -128      # M 2026-10-29: BaldrForce.exe 0x420be0 gives every object (mech 0x41c01a, objects 0x426945 /
                       # 0x44a6f6) a permanent movement block 1 whose only component is vertical -128; 0x448c70 averages
                       # the vertical component of later blocks into it ((L + g) >> 1, 0x448e31) -> skill block 3:
                       # g_eff = (x増分 - 128) >> 1. work/tooru_port/SIGN_DECISION_20261029.md


def bfe_free_fall(h, v, limit=300):
    """M 2026-10-30 (FREEFALL): BFE vertical motion of a mech that is no longer in a skill, from height h (px) and
    velocity v (1/256 px^.5 units, up = +). With no skill block only the permanent block 1 of 0x420be0 is valid, so the
    composite 0x448c70 takes its -128 as it is (no averaging): v += -128 per tick (0x4402e0), dh = sign(v)*(v>>8)^2
    clamped to +-48. Same physics as the launched victim (bfe_launch). Returns the per-tick height changes until the
    landing tick (included); [] when already grounded."""
    out = []
    if h <= 0 and v <= 0:
        return out
    for _ in range(limit):
        v += BFE_BASE_G
        q = v >> 8
        d = max(-48, min(48, q * q * (1 if v >= 0 else -1)))
        h1 = max(0, h + d)
        out.append(h1 - h); h = h1
        if h <= 0:
            break
    return out


def bfe_vert_sim(jp, ticks, st, trace=None):
    """M 2026-10-28: BFE skill vertical motion for one phase, BaldrForce.exe 0x440150 (phase start) + 0x4402e0 (tick).
    Phase start: v = x開始*256 unless jump flag 4 「軌道をそのままに」; gravity g = x増分 (init -> final by step/tick, step 0 =
    final at once, -32768 = keep). Tick: if height <= 0 and v <= 0 -> grounded, nothing (checked BEFORE v += g, so a
    positive x増分 never lifts a grounded mech); else v += g_eff, dh = sign(v)*(v>>8)^2 clamped to +-48 px unless flag
    0x10; height floored at 最低高さ (flag 2: absolute, else relative to the phase start). Positive v = up.
    M 2026-10-29: g_eff = (x増分 + BFE_BASE_G) >> 1 (movement-block composite 0x448c70 with the permanent block 1 = -128,
    0x420be0): x増分 +128 = no gravity, 0 = -64, +123 (爆撃ﾐｻｲﾙ firing) = -3. The literal v += x増分 made every positive
    x増分 phase in the air rise for ever (爆撃ﾐｻｲﾙ 'infinite climb', reported). Verified on 原作8 (ｻｲﾄﾞｽﾃｯﾌﾟｷｯｸ miss: no
    rise), 原作9 (爆撃ﾐｻｲﾙ: 173 px in 9 ticks, then -1 px/tick while firing), 原作10 (JK apex ~60 px), S: DD (+64 -> -32).
    st: dict(h, v, g) carried from the previous phase (mutated). Returns the per-tick height changes (px/tick).
    trace: optional list receiving (h, v) after each tick (M 2026-10-30, FREEFALL: the state at a hit / turn end)."""
    mid = lambda r: (r[0] + r[1]) // 2
    f = jp['flags']
    if not f & 4:
        st['v'] = mid(jp['x_start']) * 256
    gt = st['g']; gs = 0
    if jp['dx_init'][0] != -32768:
        st['g'] = mid(jp['dx_init'])
        gt = mid(jp['dx_final']) if jp['dx_final'][0] != -32768 else st['g']
        gs = abs(mid(jp['dx_step']))
    mh = jp['min_height'][0] if jp['min_height'][0] != -32768 else 0
    floor_ = mh if f & 2 else st['h'] + mh
    out = []
    for _ in range(ticks):
        g = st['g']
        st['g'] = gt if gs == 0 else (min(gt, g + gs) if gt > g else max(gt, g - gs))
        h0 = st['h']
        if h0 <= 0 and st['v'] <= 0:
            st['v'] = 0; out.append(0)
            if trace is not None:
                trace.append((0, 0))
            continue
        st['v'] += (st['g'] + BFE_BASE_G) >> 1      # M 2026-10-29: composite with the base block (0x448c70)
        q = st['v'] >> 8
        d = q * q * (1 if st['v'] >= 0 else -1)
        if not f & 0x10:
            d = max(-48, min(48, d))
        h = max(h0 + d, floor_, 0)
        if h <= 0 < h0:
            h = 0
        st['h'] = h
        out.append(h - h0)
        if trace is not None:
            trace.append((h, st['v']))
    return out


def bfe_bullet_vert(jp, ticks):
    """S 2026-10-29: BFE bullet vertical motion for one phase: the bfe_vert_sim tick (0x4402e0, v = x開始*256 at the phase
    start 0x440150, g_eff = (x増分 + BFE_BASE_G) >> 1 - bullets get the base block too, 0x426945 / 0x44a6f6) but without
    the ground stop: the DiveX bullet spawns at the muzzle height and its own 着地 test ends the phase, so the descent
    goes on. Returns the per-tick height changes (px/tick)."""
    mid = lambda r: (r[0] + r[1]) // 2
    f = jp['flags']; v = mid(jp['x_start']) * 256
    g = mid(jp['dx_init']); gt = mid(jp['dx_final']) if jp['dx_final'][0] != -32768 else g; gs = abs(mid(jp['dx_step']))
    out = []
    for _ in range(ticks):
        g = gt if gs == 0 else (min(gt, g + gs) if gt > g else max(gt, g - gs))
        v += (g + BFE_BASE_G) >> 1
        q = v >> 8
        d = q * q * (1 if v >= 0 else -1)
        out.append(d if f & 0x10 else max(-48, min(48, d)))
    return out


def bfe_bullet_land(jp, limit=3000):
    """S 2026-10-29: tick at which a bullet launched from the ground by this phase (x開始 > 0) is back at height 0 under
    bfe_bullet_vert (None = not within limit ticks)"""
    h = 0
    for k, d in enumerate(bfe_bullet_vert(jp, limit)):
        h += d
        if h <= 0 and k > 0:
            return k + 1
    return None


def bfe_fire_offsets(fire, n):
    """G 2026-11-03 (FIREIV, 調査記録 26 §G3): BFE tick offsets of the first n shots of a fire block, from the first shot.
    BaldrForce.exe 0x44a1c0 (every tick): v = timer +0x290 (0 at the fire start, 0x44a398); timer = v - 1; v > 0 -> no
    shot. A shot sets timer = T (0x4a7db0: acc +0x2a8 (= 間隔 初期 << 8, 0x44a3d7) += 増分, T = acc >> 8, clamped at
    最終 on the side of the step's sign, no clamp for step 0) -> the next shot is T+1 ticks later (T <= 0: next tick).
    The old rule took 2 x 間隔 F (= 間隔 ticks), one tick short (原作 7.mp4 火炎放射器 2.30 s vs 移植 6.mp4 1.13 s)."""
    ini, fin, stp = (list(fire['interval']) + [0, 0, 0])[:3]
    acc = ini << 8; t = 0; out = [0]
    for _ in range(1, max(1, n)):
        acc += stp; T = acc >> 8
        if stp > 0 and T > fin:
            T = fin
        elif stp < 0 and T < fin:
            T = fin
        t += max(0, T) + 1; out.append(t)
    return out


def bfe_launch(L, g=BFE_LAUNCH_G):
    """M 2026-10-28: BFE launch L (victim v = L*256, 0x441f50) under the same tick physics as bfe_vert_sim with gravity g
    -> (apex px, airtime ticks from the ground)"""
    v = L * 256; h = 0; H = 0; t = 0; up = None
    while t < 400:
        v -= g; t += 1
        q = v >> 8; h += max(-48, min(48, q * q * (1 if v >= 0 else -1)))
        if v <= 0 and up is None:
            up = t; H = h
        if up is not None and h <= 0:
            break
    return H, t


def bfe_launch_multi(L, n, iv, g=BFE_LAUNCH_G):
    """bfe_launch with v reset to L*256 every iv ticks for n hits -> (apex px, airtime ticks)"""
    v = L * 256; h = 0; H = 0; t = 0; k = 1
    while t < 600:
        if k < n and t and t % iv == 0:
            v = L * 256; k += 1
        v -= g; t += 1
        q = v >> 8; h += max(-48, min(48, q * q * (1 if v >= 0 else -1)))
        H = max(H, h)
        if k >= n and v <= 0 and h <= 0:
            break
    return H, t


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def i32list(*vals):
    out = []
    for v in vals:
        b = (v & 0xffffffff).to_bytes(4, 'little')
        out += [x - 256 if x > 127 else x for x in b]
    return out


def struct_unpack_i32(b):
    """inverse of i32list: signed byte list -> int32 values"""
    return [int.from_bytes(bytes((x & 0xff) for x in b[i:i + 4]), 'little', signed=True) for i in range(0, len(b), 4)]


# ------------------------------------------------------------------------------------------- SE map
class SeMap:
    """BFE SE table index -> new BSDX SeGroup item (appended to an existing category; files converted to ogg)"""

    def __init__(self, bfe_se_names, cat, base_index, prefix='BFE_'):
        self.names = bfe_se_names; self.cat = cat; self.base = base_index; self.prefix = prefix
        self.items = collections.OrderedDict()   # bfe name -> item index

    def name(self, idx):
        if idx is None or idx < 0 or idx >= len(self.names):
            return None
        return self.names[idx][0]

    WAV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'bfe_se')

    def frames(self, idx):
        """G 2026-11-03 (SEVOICE): length of the BFE SE wav in DiveX frames (60/s), None if unknown."""
        n = self.name(idx)
        if not n or not os.path.isdir(self.WAV_DIR):
            return None
        c = [x for x in os.listdir(self.WAV_DIR) if x.lower() == (n + '.wav').lower()]
        if not c:
            return None
        import wave
        w = wave.open(os.path.join(self.WAV_DIR, c[0]))
        return w.getnframes() * 60.0 / w.getframerate()

    def get(self, idx):
        n = self.name(idx)
        if n in NOSE:
            return None
        if n not in self.items:
            self.items[n] = self.base + len(self.items)
        return (self.cat, self.items[n])


# ------------------------------------------------------------------------------------------- CEventEffect helpers
def effect_target(o):
    for u in o.get('ceventEffectUnitList') or []:
        if u['unitSlotNum'] == 3 and u.get('data') and 'wazFileNo' in u['data']:
            return (u['data']['wazFileNo'], u['data']['wazSequenceNo'])
    return None


def set_effect_target(o, tgt):
    for u in o['ceventEffectUnitList']:
        if u['unitSlotNum'] == 3:
            u['data']['wazFileNo'], u['data']['wazSequenceNo'] = tgt


def effect_sub(o, slot, sample=None):
    """the data dict of sub <slot> of a CEventEffect; created from <sample> (a unit dict) when missing"""
    for u in o['ceventEffectUnitList']:
        if u['unitSlotNum'] == slot:
            return u['data']
    if sample is None:
        return None
    u = copy.deepcopy(sample); u['data']['offset'] = 0
    L = o['ceventEffectUnitList']; L.append(u); L.sort(key=lambda x: x['unitSlotNum'])
    return u['data']


def drop_effect_sub(o, slot):
    o['ceventEffectUnitList'] = [u for u in o['ceventEffectUnitList'] if u['unitSlotNum'] != slot]


# ------------------------------------------------------------------------------------------- converter
class Converter:
    """mode 'mech': TOORU.WAZ skill -> mech skill (sprites of tooru.spm, spm -1)
       mode 'bullet': Tama.dat entry -> shared-waz bullet skill (sprites of the effect spm <spm_seq>)
       fx: object with effect_target(effect_no) / tama_target(tama) / line_chain(name, ti, proj, mech_tip) /
           spawn_sample(kind) ('bullet' | 'effect' | 'effect_from_mech') / sub_samples (slot -> unit dict)"""

    def __init__(self, lib, spr_anims, semap, rep, spm_numpat, fx=None, mode='mech', spm_seq=-1, anim_base=SKILL_BASE,
                 sink_skills=(), combo_v3=None):
        self.lib = lib; self.A = spr_anims; self.se = semap; self.rep = rep; self.numpat = spm_numpat
        self.sink_skills = frozenset(sink_skills)   # SINK: technique names (mech's own list)
        self.cv3 = combo_v3                          # COMBOV3 tables of the mech (module), or None
        self.fx = fx; self.mode = mode; self.spm_seq = spm_seq; self.anim_base = anim_base
        self.default_hit = None      # hit object used when the template move has none (set by the caller)

    # ---------------- timing
    def nat(self, a):
        return sum(p['wait'] + 1 for p in self.A[a]) if a >= 0 and self.A[a] else 0

    def ev_len(self, e, ph):
        w = (e['wait'][0] + e['wait'][1]) // 2
        t = e['anim_type']; nat = self.nat(e['anim'])
        if t == 0:
            n = w if w > 0 else nat
        elif t == 1:
            n = round(nat * w / 100.0)
        elif t == 2:
            n = w
        elif t == 3 and self.mode != 'mech':
            # bullet 着地まで: BFE has no timeout (0x4433b4 loops while airborne). The 80F hold made a lob explode in
            # the air / right after launch (DDﾐｻｲﾙ 'falls too early', S 2026-10-28). Vanilla 「DDミサイル：甲Lv3」 waits
            # up to 177F for 着地 (T0/T1 F0-177) -> 89 ticks = 178F hold + 着地 jump.
            # S 2026-10-29: the hold must not end before the BFE landing (DD Lv3: ~88 ticks from the ground, later from
            # the muzzle -> it exploded in the air at 178F, user report) -> predicted landing (bfe_bullet_land) + 8 ticks,
            # at least the vanilla 178F.
            n = 89; jp = ph['jump']; land = None
            if jp['x_start'][0] > 0 and jp['dx_init'][0] != -32768:
                land = bfe_bullet_land(jp)
                if land:
                    n = max(n, land + 8)
            hi_ = ph['hit']
            if jp['x_start'][0] == 0 and jp['dx_init'][0] != -32768 and jp['dx_init'][0] <= -200 and \
                    ph['touch_mech_enemy'] == 1 and 0 < hi_['hits_mech'] < 255:
                # E 2026-11-15 (DIVETOUCH): a falling beam that stands on the enemy (ｻﾃﾗｲﾄﾚｰｻﾞｰ ph0) leaves the phase when its
                # hits run out (BFE has no timeout while airborne) -> hold long enough for all of them: 89 ticks + hits x
                # (HIT規模 + 1) ticks (20 x 5 = 100). The hold end is only a fallback; the 残りＨＩＴ数 / ground tests end it.
                n = max(n, 89 + hi_['hits_mech'] * (hi_['hit_scale'] + 1))
            self.rep.add('LANDHOLD', 'bullet anim_type 3 (着地まで): %dF hold + 着地 jump (vanilla DDミサイル：甲 177F%s)' % (
                2 * n, '; BFE landing %d ticks + 8' % land if land else ''))
        elif t == 3:
            n = 40; self.rep.add('APPROX', 'anim_type 3 (着地まで): 80F hold + 着地 jump')
        elif t == 4:
            f = ph['fire']
            # G 2026-11-03 (FIREIV): BFE 0x443330 at each end of the anim (table 0x4433f4[4] = 0x4433c5): shots left
            # (+0x288) > 0 -> the anim loops, else the event ends -> length = whole anim cycles covering the last shot
            # (bfe_fire_offsets, shots counted from the event start). Was loops x 間隔 + 4 ticks (one tick per shot short).
            last = bfe_fire_offsets(f, min(MAXSPAWN, max(1, f['loops'])))[-1]
            cyc = max(1, nat)
            n = max(nat, cyc * ((last + 1 + cyc - 1) // cyc))
            self.rep.add('FIREIV', 'anim_type 4 (弾を撃ち終わるまで): last shot at tick %d (BFE 間隔 %s, x%d) -> %d ticks (anim cycle %d)' % (
                last, f['interval'], min(MAXSPAWN, max(1, f['loops'])), n, cyc))
        else:
            n = nat; self.rep.add('UNKNOWN', 'anim_type %d' % t)
        return max(1, n) * 2

    MAXLOOPF = 4000      # cap (BSDX frames) for anim_type 2 events with huge loop counts

    def ev_timing(self, e, ph):
        """exact BFE timing of one sprite event -> (BSDX frames, [(pat, start, end)] or None when the anim is empty).
        BaldrForce.exe 0x443820 (event start, jump table 0x443aa0) + 0x443330 (anim end, table 0x4433f4); a pattern
        whose stored time is v lasts v+1 ticks (0x413244); 1 tick = 2 BSDX frames.
          0 ウェイトに詰める: 1 pattern -> WAIT; else pattern i = (w_i+1)*WAIT // Σ(w_j+1)   (0x4438b8)
          1 %増減        : 100 -> natural (w_i); else (w_i+1)*WAIT // 100                (0x443930)
          2 ウェイト間ループ: natural patterns cycled for WAIT+1 ticks (counter +0x124 = WAIT set at 0x4439db,
                            decremented every tick by 0x443382 via the per-tick check 0x4442f0; ends when < 0)
          3 着地まで      : natural, looped while airborne; skipped when it starts on the ground (0x4439f6 / 0x4433b4)
          4 撃ち終わるまで: natural, looped while shots remain (0x4433c5)"""
        w = (e['wait'][0] + e['wait'][1]) // 2
        t = e['anim_type']; a = e['anim']
        pats = self.A[a] if 0 <= a < len(self.A) and self.A[a] else []
        nat = [p['wait'] + 1 for p in pats]
        if t in (3, 4):
            n = self.ev_len(e, ph)
            return n, (self.patterns(a, n, True) if pats else None)
        if t == 0:
            ticks = [w + 1] if len(pats) <= 1 else [(x * w) // sum(nat) + 1 for x in nat]
        elif t == 1:
            ticks = nat if (w == 100 or not pats) else [(x * w) // 100 + 1 for x in nat]
            if not pats:
                ticks = [max(1, round(w / 100.0))]
        elif t == 2:
            ticks, tot = [], 0
            while tot < w + 1:
                for x in (nat or [1]):
                    if tot >= w + 1:
                        break
                    k = min(x, w + 1 - tot); ticks.append(k); tot += k
        else:
            self.rep.add('UNKNOWN', 'anim_type %d' % t); ticks = nat or [1]
        out, f = [], 0
        for i, k in enumerate(ticks):
            if f >= self.MAXLOOPF:
                self.rep.add('APPROX', 'anim_type %d event capped at %dF' % (t, self.MAXLOOPF)); break
            out.append((i % max(1, len(pats)), f, f + 2 * k - 1)); f += 2 * k
        return f, (out if pats else None)

    def patterns(self, a, n, loop):
        """split n BSDX frames over the patterns of anim a -> [(pat, start, end)]"""
        pats = self.A[a]; k = len(pats)
        waits = [(p['wait'] + 1) * 2 for p in pats]
        out = []
        if loop:      # play at natural speed, cycling, for n frames
            f, i = 0, 0
            while f < n:
                d = min(waits[i % k], n - f); out.append((i % k, f, f + d - 1)); f += d; i += 1
            return out
        tot = sum(waits); cum = 0; prev = 0
        for i, w in enumerate(waits):
            cum += w; b = round(n * cum / tot)
            if b > prev:
                out.append((i, prev, b - 1)); prev = b
        return out

    def sprite(self, a, p, s, e):
        if self.mode == 'mech':
            return self.lib.obj(0, 13, s, e, spmFileSequence=-1, actionGroupNumber=self.anim_base + a, actionNumber=p)
        return self.lib.obj(0, 13, s, e, spmFileSequence=self.spm_seq, actionGroupNumber=a, actionNumber=p)

    def se_obj(self, se, f):
        return self.lib.obj(52, 23, f, f, count=1, byteDataList=[i32list(se[0], se[1], 100, 1)])

    # ---------------- spawns
    def spawn(self, kind, tgt, at, L, proj=None):
        o = copy.deepcopy(proj if proj is not None else self.fx.spawn_sample(kind))
        o['offset'] = 0
        set_effect_target(o, tgt)
        if tgt[0] != getattr(self.fx, 'LF', None) and (o.get('int2') or o.get('int3', 0) & 2):
            # S 2026-10-30 (SPAWNTYPE): CEventEffect header int2 エフェクトタイプ2 (1 line / 2 line parent / 3 smoke
            # line) and int3 flag bit 1 occur in vanilla only on spawns that target Laser (≈4,700 others all 0 / bit
            # clear). A template spawn copied from a line skill (甲 火炎放射 (1,1,2,0)) kept them on a Tama04 bullet:
            # 火炎放射器 flames passed through the enemy with 0 HIT (移植版5). Non-Laser target -> plain bullet header.
            self.rep.add('SPAWNTYPE', 'spawn -> file %d: header int2 %s int3 %s -> 0 / bit1 clear (vanilla: line types only for Laser)' % (
                tgt[0], o.get('int2'), o.get('int3')))
            o['int2'] = 0; o['int3'] = o.get('int3', 0) & ~2
            # S 2026-11-01 (SPAWNTYPE, int1): the sample was a line spawn (甲 スタンロッド/エネルギー/グラビティフィールド
            # 稲妻 (0,1,0) -> Laser) and its int1 エフェクトタイプ1 = 0 stayed: BaldrSky.exe 0x645254 int1 == 0 (int2 != 1)
            # -> object type 3 = 0x6111e0(..,3), the visual-only object of the hit effects (0x6482a6) -> the Tama04 field
            # never hit (グラビティフィールド「一切当たらない」). Vanilla bullet-file targets (1-5, 7) carry int1 = 1 (type 1),
            # 甲's own field spawns (4,17)/(4,21) = (1,0,0); only Effect (file 0) spawns are 0.
            if tgt[0] != 0 and not o.get('int1'):
                o['int1'] = 1
                self.rep.add('SPAWNTYPE', 'spawn -> file %d: header int1 0 -> 1 (bullet object; 0 = exe 0x645254 visual-only type 3)' % tgt[0])
        o['startFrame'] = o['endFrame'] = max(0, min(L - 1, at))
        for d in walk(o):
            if 'offset' in d:
                d['offset'] = 0
        return o

    def effect_spawn(self, eff, at, L, ev, what, at_target=False, name_ja=''):
        if not self.fx or eff is None or eff['effect_no'] < 0:
            return
        tgt = self.fx.effect_target(eff['effect_no'])
        if tgt is None:
            self.rep.add('DROPPED', 'effect type %d (%s): no Effect.spr anim (procedural effect)' % (eff['effect_no'], what)); return
        o = self.spawn('effect' if self.mode != 'mech' else 'effect_from_mech', tgt, at, L)
        if at_target:
            # E 2026-11-06 (EFFTARGET, user 11/06 「スタンロッドはヒット時にごく小さいエフェクトが自機から発生している。敵の位置が
            # 正しい」): BFE 常時ｴﾌｪｸﾄ with 判定番号 (SPR 判定スロット, ｽﾀﾝﾛｯﾄﾞ ph1 slot 6) in a phase that hits a mech = the
            # spark where the attack touches the enemy. DiveX has no SPR-rect spawn position -> オブジェクト位置指定 標的
            # (intList3 [1,0], vanilla サテライトレーザーLv1, same as LOCKTARGET).
            d7_ = effect_sub(o, 7)
            if d7_ is not None and d7_.get('bsdxInfoCollectionList'):
                b7_ = d7_['bsdxInfoCollectionList'][0]
                if b7_['typeList'] == [1]:
                    b7_['intList3'] = [1, 0]
                    self.rep.add('EFFTARGET', '%s: 常時ｴﾌｪｸﾄ %d at 判定番号 %d on a hitting phase -> spawn sub 7 オブジェクト位置指定 標的' % (
                        name_ja, eff['effect_no'], eff['rect_slot']))
        ev[48].append(o)

    # ---------------- one skill
    def convert(self, bs, tpl, name_ja, name_en, fc=False, fallback_proj=None):
        """bs: BFE named skill / Tama; tpl: BSDX template skill (JSON)"""
        lib = self.lib; rep = self.rep; bullet = self.mode != 'mech'
        stick_follow_ = None
        h = bs['header']; phases = bs['phases']; nph = len(phases)
        # 2026-10-30 (HITCANCEL, 調査記録 20): BFE 技タイプ (header +0x29: 0 打撃 / 1 射撃) decides the cancel flag (mech
        # +0x38 -> +0x3e): a hit on a mech by an object whose OWN skill is 打撃 sets it (0x441856-0x441878, also bullets of
        # the weapon in use: +0x284 = weapon slot, copied to bullets at 0x44a5c3); a 射撃 mech sets it when it fires
        # (0x44a812-0x44a81b). DiveX: hit +0x64 キャンセルフラグ == 1 -> owner [+0x1900] = 1 (0x646edc-0x646eed, owner =
        # [+0x14c4], also for bullets); slot 47 value 0/1 -> [+0x1900] (0x60c91b-0x60c959). Bullets: only the 打撃 Tama
        # fired by a 打撃 mech skill (= the striking part of a melee move; vanilla 門倉コレダー：甲 / ケイジブレイド：甲 c1).
        kind = h.get('kind', 0)
        self._combo_setup(bs, kind, bullet, name_ja)     # N COMBOCLS (technique size / 近接・射撃 for _set_hit)
        if not bullet:
            # ELEMENT (調査記録 53): a BFE ﾀﾞﾒｰｼﾞ処理をしない hit (NODMG, 感電（見えない） of ｽﾀﾝﾛｯﾄﾞ) carries the element, but
            # it is a 威力 0 hit every 2F in DiveX (no state is put on it, see _element) -> its element goes to the
            # technique's own strikes (the 「特別な事情」 of the user's rule), keeping the template's time if it has that bit.
            self._elem_child = 0
            if self.fx is not None and hasattr(self.fx, 'chain'):
                for ph_ in phases:
                    for t_ in sorted(self.fx.chain(ph_['fire']['tama'])):
                        for p_ in self.fx.tama[t_]['phases']:
                            if p_['hit']['flags'] & 0x20 and p_['hit']['element'] in ELEM_BITS and not self._elem_child:
                                self._elem_child = p_['hit']['element']
                                rep.add('ELEMENT', '%s: 撃つ弾 %d の ﾀﾞﾒｰｼﾞ処理をしない ヒットの属性 %d -> 技本体の打撃へ' % (
                                    name_ja, t_, p_['hit']['element']))
        self._rep_setup(bs, bullet)                      # G REPDECAY (repeated bullets of one technique, _set_hit)
        if bullet:
            hc_ = bool(self.fx is not None and hasattr(self.fx, 'hit_cancel') and self.fx.hit_cancel(bs.get('index')))
        else:
            hc_ = kind == 0
            if kind == 0 and self.fx is not None and hasattr(self.fx, 'melee_tamas'):
                for ph_ in phases:
                    new_ = self.fx.chain(ph_['fire']['tama']) - self.fx.melee_tamas
                    late_ = [t_ for t_ in new_ if t_ in self.fx.tcache and self.fx.tama[t_]['header'].get('kind') == 0 and
                             any(p_['hit']['hits_mech'] not in (0, 254) and p_['hit']['power'] > 0 for p_ in self.fx.tama[t_]['phases'])]
                    if late_:
                        rep.add('APPROX', '%s: 打撃 bullets %s were converted before (by a 射撃 skill): hit cancel flag kept 0' % (name_ja, late_))
                    self.fx.melee_tamas |= new_
        alg = [a for a in h['alg_list'] if a != 99 and 0 <= a < nph]
        if not alg:
            alg = [0]
        # turn of each alg position: first occurrence -> the phase's own index, repeats -> cloned turns appended
        pos_turn, seen, extra = [], set(), []
        for a in alg:
            if a in seen:
                pos_turn.append(nph + len(extra)); extra.append(a)
            else:
                pos_turn.append(a); seen.add(a)
        if extra:
            rep.add('APPROX', '%s: alg_list repeats phases %s -> cloned turns' % (name_ja, extra))
        turn_phase = list(range(nph)) + extra
        nxt = {}
        for i, t in enumerate(pos_turn):
            nxt[t] = pos_turn[i + 1] if i + 1 < len(pos_turn) else 'end'
        for p in range(nph):        # phases outside the alg list (jump-only): continue after their first alg successor
            if p not in nxt:
                later = [t for t in pos_turn if t > p]
                nxt[p] = later[0] if later else 'end'
        loops = [l for l in h['loops'] if l['end'] != 99 and l['count'] > 0]
        # R 2026-11-03 (LOOPPOS, 調査記録 25): BaldrForce.exe 0x443491-0x4434d3 (next alg position, reached only when the phase
        # ends without its own go_*): for each of the 4 loops, if obj+0x1b (current ALG POSITION) == loop end and count > 0:
        # its own counter obj+0x1d+i += 1; < count -> return loop start (alg position); else counter i = 0 and fall through;
        # then position + 1. So start/end are alg-list positions (not phase numbers: ｼﾞｪﾉｻｲﾄﾞ･ｼｮｯﾄｶﾞﾝ alg [0,1,2,3,0,2,3]
        # loop 4..6 x2 was never matched -> 2 shots instead of 3) and every loop has its own counter, reset when it exits.
        # DiveX has one 汎用変数 per object (slot 35 -> +0x17b0, 0x60c5f0; relative add via the getter table 0x635b40),
        # reset to 0 at skill start; the second loop of 武幻剛乱舞 / ｸﾞﾘｶﾞﾝﾄ･ﾗﾝｽ saw the first loop's final count and ran
        # once (13 -> 11 hits). Each loop's threshold is offset by the counts of the loops before it in the alg list
        # (the counter is not reset in between; exact for a straight alg flow, reported otherwise).
        lp_ok, bias = [], 0
        for l in sorted(loops, key=lambda l: (l['end'], l['start'])):
            if not (0 <= l['start'] <= l['end'] < len(pos_turn)):
                rep.add('IGNORED', '%s: loop alg positions %d..%d x%d outside the alg list (%d)' % (name_ja, l['start'], l['end'], l['count'], len(pos_turn)))
                continue
            l = dict(l, t_start=pos_turn[l['start']], t_end=pos_turn[l['end']], bias=bias)
            if bias or alg[l['start']] != l['start'] or alg[l['end']] != l['end'] or pos_turn[l['start']] == 0:
                rep.add('LOOPPOS', '%s: loop alg %d..%d x%d -> turns %d..%d, 汎用カウンタ threshold %d (+%d of the earlier loops; BFE 0x443491 per-loop counters)' % (
                    name_ja, l['start'], l['end'], l['count'], l['t_start'], l['t_end'], bias + l['count'] - 1, bias))
                if bias and any(p_.get(k_, -99) != -99 for p_ in phases for k_ in ('go_hit_mech', 'go_land', 'go_hits_le_mech', 'go_end', 'go_anim_end', 'go_dist_in', 'go_air')):
                    rep.add('APPROX', '%s: shared 汎用カウンタ offset assumes the earlier loops ran fully (conditional transitions present)' % name_ja)
            lp_ok.append(l); bias += l['count']
        loops = lp_ok
        tpl_hits = {s: [o for ph in tpl['phasesInfo'] for u in ph['skillUnitCollection'] if u['unitQuantity'] == s
                        for o in u['skillInfoObjectList']] for s in (41, 42)}
        tpl_proj = [o for ph in tpl['phasesInfo'] for u in ph['skillUnitCollection'] if u['unitQuantity'] == 48
                    for o in u['skillInfoObjectList'] if effect_target(o) and effect_target(o)[0] != 0]
        # wire tip fired separately by the mech (BFE ﾓｰﾆﾝｸﾞｽﾀｰ / ｽｳｨﾝｸﾞﾜｲﾔｰ 先端): in BSDX the line parent spawns the tip
        mech_tip = None
        if not bullet and self.fx:
            lasers = [ph['fire'] for ph in phases if ph['fire']['tama'] >= 0 and
                      (ph['fire']['fire_type'] != 0 or self.fx.chain_has_laser(ph['fire']['tama']))]
            tips = [ph['fire']['tama'] for ph in phases if ph['fire']['tama'] >= 0 and ph['fire']['fire_type'] == 0
                    and not self.fx.chain_has_laser(ph['fire']['tama']) and '先端' in self.fx.tama[ph['fire']['tama']]['header']['name']]
            if lasers and tips:
                mech_tip = tips[0]
        turns = []
        air_dispatch = []
        last_sprite = None
        hit_no = 0
        hit_tpl_of = {}        # R 2026-11-12 HITREPEAT: BFE hit -> template hit index of its first occurrence
        first_attack = None
        moving_any = False
        cur_sp = None          # BFE speed reached at the end of the previous turn (for 初期値 変更しない)
        sp_assumed = True      # M 2026-11-01 (RESTRAMP): cur_sp still rests on the DASH_SPEED guess (no turn with 初期値 yet)
        touch_off_seen = False
        flat_seen = False      # FLATCHIP applied in an earlier turn of this bullet
        stop_fix = []          # mech: 「hit -> end」 changes of moving turns, redirected to a 1-frame stop turn
        # M 2026-10-29 (HITDELAY): phases entered by a mech hit (go_hit_mech) of a phase with a hitstop. BFE freezes the
        # attacker during the hitstop (0x444560) and processes no hit, so the next phase hits after it (原作11: BU hit 1
        # F152, freeze ~10 ticks, hit 2 F164 in the air). BaldrSky jumps to the destination turn and runs its F0 inside the
        # freeze (移植版2-2: T2 pose at once, 2nd hit F138 on the ground, 透 rose alone after the freeze) -> the destination
        # turn's hit window starts at F1 (vanilla 甲 ブーストアッパーLv3: 2nd hit F16 = 1F after the 1st hit F14-15).
        hit_entry = set()
        if not bullet:
            for p_, ph_ in enumerate(phases):
                g_ = ph_['go_hit_mech']; hi_ = ph_['hit']
                if g_ == -99 or hi_['hit_wait'] <= 0 or hi_['hits_mech'] in (0, 254) or hi_['power'] <= 0:
                    continue
                d_ = nxt.get(p_) if g_ == -1 else (g_ if 0 <= g_ < nph else None)
                if isinstance(d_, int):
                    hit_entry.add(d_)
        rising = False         # a previous turn rose without gravity (hover in later zero-jump turns)
        vst = {'h': 0, 'v': 0, 'g': 0}; vknown = False   # mech: BFE vertical state carried along the turns (M 2026-10-28)
        ground_vert = {}       # mech: turn -> (slot 19, slot 21) of the same phase entered on the ground (land dispatch)
        land_dispatch = []     # mech: (turn, 着地 change) of go_land turns that never take off from the ground
        chip_off = 0           # bullet: BFE チップ向き offset reached at the end of the previous turn (SPIN)
        spun_prev = False      # bullet: the previous turn ended while spinning (SPIN)
        # G 2026-11-03 (ZOOMTYPE0): BFE sets the sprite zoom at EVERY event start (0x443727, init 256 = back to 1.0) while a
        # DiveX slot 1 value stays until the next slot 1 event -> once any event of the skill zooms, every sprite event
        # gets its slot 1 (identity ones as 256 / keep). BaldrSky.exe 0x60b9e2..0x60b9ef: a slot 1 object active at the
        # frame writes the base zoom X AND Y (+0x16a8/+0x16ac); with none the last value (or the spawn's) stays. Bullets
        # always get it: their spawn carries the 甲 template's sprite zoom (sub 16..19, e.g. ｶﾞﾄﾘﾝｸﾞ砲 -> Tama04 sub 19,
        # ﾌﾞﾛｯｸﾊﾞﾘｱ sub 18 160) while a BFE bullet's zoom comes only from its own events (TAMA_FIRE has no zoom).
        zoom_any = bullet or any(not zoom_identity(e['zoom']) for p_ in phases for e in p_['events'])
        for ti_, pi in enumerate(turn_phase):
            ph = phases[pi]
            ev = collections.defaultdict(list)
            t = 0; atk = []; fire_at = None; land_from = None; fire_ev_end = None
            for e in ph['events']:
                n, pts = self.ev_timing(e, ph)
                if pts:
                    for (p, s0, s1) in pts:
                        ev[0].append(self.sprite(e['anim'], p, t + s0, t + s1))
                        last_sprite = (e['anim'], p)
                    if zoom_any:
                        # V 2026-10-27 (exe 0x440dd0 / 0x440ec0). G 2026-11-03 (ZOOMTYPE0): the zoom 'type' byte is not
                        # read by BaldrForce.exe (event start 0x443727 -> 0x440dd0 reads event+0x22.. only; per tick
                        # 0x444263 -> 0x440ec0 is unconditional), so type 0 zooms (ﾊﾞｽﾞｰｶ砲 Lv3 768, ﾊﾝﾄﾞｶﾞﾝ Lv1 128 ..)
                        # apply too; was type == 1 only.
                        ev[1] += zoom_events(lib, e['zoom'], t, n)
                        if e['zoom']['type'] != 1 and not zoom_identity(e['zoom']):
                            rep.add('ZOOMTYPE0', 'sprite event zoom type %d applied (init %s final %s step %s; BFE ignores the '
                                    'type byte, 0x440dd0 / 0x440ec0)' % (e['zoom']['type'], e['zoom']['init'],
                                                                         e['zoom']['final'], e['zoom']['step']))
                elif last_sprite:
                    ev[0].append(self.sprite(last_sprite[0], last_sprite[1], t, t + n - 1))
                se = self.se.get(e['se_play']) if e['se_play'] >= 0 else None
                if se:
                    ev[52].append(self.se_obj(se, t))
                if e['attack_rects']:
                    atk.append((t, t + n - 1))
                if e['attr'] in SPRITE_ATTR and (7, 15) in lib.ev:
                    ty, val = SPRITE_ATTR[e['attr']]
                    ev[7].append(lib.obj(7, 15, t, t + n - 1, int1=ty, int2=0, int3=val, int8=val))
                    rep.add('BLEND', 'sprite event 描画属性 %d -> slot 7 SpriteAttr type %d value %d' % (e['attr'], ty, val))
                if not bullet and e['armor_rate'] >= 3:
                    lv = 1 if e['armor_rate'] < 4 else 2 if e['armor_rate'] < 16 else 3
                    ev[36].append(lib.obj(36, 0, t, t, int4=lv)); ev[36].append(lib.obj(36, 0, t + n, t + n, int4=0))
                if e['flags'] & 8 and fire_at is None:
                    fire_at = t; fire_ev_end = t + n
                if e['anim_type'] == 3 and land_from is None:
                    land_from = t
                t += n
            L = max(t, 2)
            # ---- movement
            # M 2026-10-28: mech speed /2 too (was 1:1 'calibrated' on 甲 values). BFE speed = px/tick (0x440b70 v<<8, the
            # same entry as the dash 16, 0x4196a0; 通常武装.mp4 dash ~15 px/tick); BSDX slot 18 = px/F (0x60c129 x1024 ->
            # CMove vector 0x5f59b0 -> position 0x5f5604), 1 tick = 2 F. 1:1 moved every mech skill twice as far
            # (E・フィンガー 'moves too much', ジャンピングニー 32 px/F).
            sp = ph['speed']; div = 2.0
            if bullet:
                # S 2026-10-30 (BSPEED): BFE bullet speed is an integer px/tick (0x449100 pos += cos/sin * (composite
                # 0x448c70 >> 8)) = v/2 px/F; slot 18 /2 rounded odd speeds up (DDﾐｻｲﾙ Lv4 1 -> 1 px/F = 2x: グラルパトン
                # flew twice as far, 原作9-2 / 移植版6). Slot 25 ﾍﾞｸﾄﾙ補正率：技 50% (CMove 0x5f5258 / 0x5f53ca: skill
                # vector * %/100, the jump is not scaled; vanilla bullet 鉄扇 Tama05[68]) + the raw BFE value in slot 18
                # and spawn sub 31 (Fx.tama_speed) = exactly v/2 px/F for every speed. F0 of every turn (0x60c469 keeps
                # the value while no event is active).
                div = 1.0
                ev[25].append(lib.obj(25, 0, 0, 0, int1=0, int2=50, int3=0, int4=50))
                if ti_ == 0:
                    rep.add('BSPEED', 'bullet slot 25 ﾍﾞｸﾄﾙ補正率：技 50% + raw BFE px/tick in slot 18 / spawn speed (= v/2 px/F, vanilla 鉄扇)')
            if not bullet and (sp['init'][0] != -32768 or sp['final'][0] != 0):
                rep.add('MOVE', 'mech speed BFE %s -> %s px/tick -> slot 18 /2 px/F' % (sp['init'][0], sp['final'][0]))
            moving = False
            # R 2026-11-04 (BDECEL): bullets too. ﾋﾞｯﾄ：真上ﾊﾞﾙｶﾝ ph1 (初期 -32768 = keep, 最終 0, 増分 1024 = 4 px/tick):
            # BFE brakes to a stop under the enemy (0x4489d2); the bullet turn had no slot 18 and the bit flew on at 10
            # (user 4.mp4 「対空バルカンビットが敵の下で止まらない」).
            keep_decel = (sp['init'][0] == -32768 and sp['final'][0] == 0 and sp['step'][0] > 0 and (not bullet or ti_ > 0))
            if keep_decel and bullet:
                rep.add('BDECEL', 'bullet speed 変更しない -> 0 at %d/256 px/tick -> slot 18 前±0 -> 0' % sp['step'][0])
            if sp['init'][0] != -32768 or sp['final'][0] != 0 or keep_decel:
                # random ranges [min,max] -> ValRandom. R 2026-11-08 (RANDLOW, user 多弾頭ミサイルポッド 「ランダムに偏り」): the
                # ValRandom width field is one-sided, value = 主値 + rand(0..幅) (vanilla 方向補正 pairs -40/80, -15/30, -60/120,
                # -30/60 ... = symmetric only that way; the editor prints 「±」). mid ± half gave mid..max -> min, max - min.
                mid = lambda r: r[0]
                half = lambda r: r[1] - r[0]
                v0 = mid(sp['init']) if sp['init'][0] != -32768 else None
                v1 = mid(sp['final'])
                # 増分 0 = reach the final value at once (BaldrForce.exe 0x4489d2 / 0x448a11: step 0 -> cur = target).
                # The old max(1, step) stretched e.g. ショットガン's 0 -> 24..48 over 9000 ticks (pellets crawled)
                step = sp['step'][0] if sp['step'][0] > 0 else 1 << 20
                c = lambda v: int(math.copysign(math.floor(abs(v) / div + 0.5), v)) if v else 0   # 1 -> 1 (was round(0.5) = 0)
                if v0 is None:
                    # BFE 初期値 -32768 = keep the current speed (dash momentum) and move it to 最終 by 増分 per tick:
                    # start type 1 (前±0) -> end value; length from the speed reached in the previous turn (bullets,
                    # e.g. 手榴弾 12 -> bounce turn keeps decelerating to 1) or an assumed dash speed (mech)
                    # M 2026-10-30: mech too uses the speed reached at the end of the previous turn when known
                    # (DASH_SPEED only at the skill start, where the BFE speed is the unknown dash momentum)
                    cur = cur_sp if cur_sp is not None else DASH_SPEED
                    nn = max(1, math.ceil(abs(cur - v1) * 256 / step)) * 2
                    ve = v1
                    if not bullet and nn > L and not sp_assumed:
                        # M 2026-10-30 (SPEEDCUT): the BFE interpolator (0x4489d2) moves the speed by 増分/256 px/tick per
                        # tick for as long as the phase runs; a slot 18 ramp interpolates start -> end over its own frames,
                        # so a ramp cut at the turn end reached 最終 too early (ｴｱ･ﾀｯｸﾙ ph2 16 -> 0 at 64/tick = 128F in
                        # a 32F turn: 透 stopped dead after the tackle, BFE drifts on; 移植版ex / 原作ex). End value =
                        # the BFE speed after L/2 ticks.
                        ve = cur + math.copysign(step / 256.0 * (L / 2), v1 - cur)
                        rep.add('SPEEDCUT', 'mech speed 前±0 (%s) -> %s at %d/tick: %dF > turn %dF -> slot 18 ends at %s (BFE value at the turn end)' % (
                            cur, v1, step, nn, L, c(ve)))
                    if not bullet and nn > L and sp_assumed:
                        # M 2026-11-01 (RESTRAMP): while the start speed is only the DASH_SPEED guess, SPEEDCUT's absolute
                        # end value (e.g. ハンドガン T0 16 -> 0 cut at 7 px/F) made DiveX accelerate a mech at rest
                        # (前 = 0, 0x635c51 reads +0x1758) to that value along the stale +0x1744 direction (0 = down after
                        # the battle start; right-facing 透 slid ~100 px down, facing_drift.mp4 F346-375 / F450-482).
                        # Keep the ramp relative instead: 前±0 -> 最終 over the full BFE length nn, cut by the turn's
                        # unconditional slot 71 jump at L-1 (vanilla 甲 ◆モズ落としLv3 T3 前±0->4 F0-21, jump F15;
                        # ﾗｲｻﾞｰﾋﾞｰﾑ T1 F17-96, jump F30). Rest stays 0 (BFE: no momentum -> no move); a cancel keeps
                        # the previous skill's momentum and direction and loses it at cur/nn per frame.
                        rep.add('RESTRAMP', 'mech speed 前±0 (assumed %s) -> %s at %d/tick: slot 18 前±0 -> %s over %dF (> turn %dF, cut by the turn jump)' % (
                            cur, v1, step, c(v1), nn, L))
                    o = lib.obj(18, 3, 0, nn - 1 if (not bullet and sp_assumed) else min(L - 1, nn - 1), int1=1, int2=0, int4=0, int5=c(ve), int6=c(half(sp['final'])) if ve == v1 else 0)
                    if not bullet:
                        rep.add('INERTIA', 'speed 変更しない -> keep momentum, %s %d in %dF' % ('stop' if v1 == 0 else 'to', v1, nn))
                elif math.ceil(abs(v0 - v1) * 256 / step) <= 1:      # instant (増分 0 or one tick): final ± range on frame 0
                    nn = 1
                    o = lib.obj(18, 3, 0, 0, int1=0, int2=c(v1), int4=0, int5=c(v1), int6=c(half(sp['final'])))
                else:
                    nn = max(1, math.ceil(abs(v0 - v1) * 256 / step)) * 2
                    ve = v1
                    if not bullet and nn > L:
                        ve = v0 + math.copysign(step / 256.0 * (L / 2), v1 - v0)      # M 2026-10-30 SPEEDCUT (above)
                        rep.add('SPEEDCUT', 'mech speed %s -> %s at %d/tick: %dF > turn %dF -> slot 18 ends at %s (BFE value at the turn end)' % (
                            v0, v1, step, nn, L, c(ve)))
                    o = lib.obj(18, 3, 0, min(L - 1, nn - 1), int1=0, int2=c(v0), int3=c(half(sp['init'])), int4=0,
                                int5=c(ve), int6=c(half(sp['final'])) if ve == v1 else 0)
                ev[18].append(o)
                hs_ = o['endFrame'] + 1
                if hs_ < L:     # keep the reached speed until the turn ends (前±0 -> 前±0, vanilla 毒針：クリス / 突進 types)
                    ev[18].append(lib.obj(18, 3, hs_, L - 1, int1=1, int2=0, int4=1, int5=0))
                moving = bool((v0 or 0) or v1)
                vs = v0 if v0 is not None else (cur_sp if cur_sp is not None else DASH_SPEED)
                dv = step / 256.0 * (L / 2)
                cur_sp = v1 if abs(vs - v1) <= dv else vs + math.copysign(dv, v1 - vs)
                if v0 is not None:
                    sp_assumed = False
                if not bullet and not (v0 is None):
                    md = ph['move_dir']
                    ang = rnd = 0
                    if md['init'][0] != -32768:
                        lo, hi_ = md['init']; ang, rnd = (lo + hi_) // 2, (hi_ - lo) // 2
                        rep.add('DIRECTION', 'mech move_dir type %d angle %d -> slot 15 角度指定→スプライト方向(%d,%d)' % (md['type'], lo, ang, rnd))
                    ev[15].append(self._dir_event(0, ang, rnd))
            elif bullet and sp['init'][0] == -32768:
                moving = turns[-1][2] if turns else True     # speed kept from the spawner / previous turn
            stick_z = None
            if bullet and ph['move_dir']['type'] == 5 and getattr(self.fx, 'keep_pos', None):
                ev[18] = []; moving = False
                o = copy.deepcopy(self.fx.keep_pos); o['startFrame'], o['endFrame'], o['offset'] = 0, L - 1, 0
                ev[11].append(o)
                rep.add('STICK', 'bullet move_dir 5 (常に標的位置) -> slot 11 前指定を維持 (vanilla マインナックル：甲 / シールド：甲)')
                jh_ = ph['jump']
                if jh_['flags'] & 2 and jh_['min_height'][0] > 0 and jh_['x_start'][0] <= 0:
                    # E 2026-11-07 (STICKZ, replaces STICKFLOOR; user 「貫壁のエフェクトが自機を覆わない」「付着マインが徐々に上昇」): with slot 11
                    # the position is 親 + this frame's vector (0x610e70, 0x610f85), so a held slot 19 is the height ABOVE the
                    # parent; slot 22 was an absolute floor (0x610f6b), under an airborne 透 it did nothing. 超ﾀｯｸﾙ用 44,
                    # ｸﾞﾗﾋﾞﾃｨﾌｨｰﾙﾄﾞ 40, ｼｰﾙﾄﾞ 44. 吸着ﾏｲﾝ 16..32 -> 32 (= the 甲 height), held so it no longer drifts.
                    stick_z = int(max(jh_['min_height']))
                md_ = ph['move_dir']
                if md_['flags'] & 4 and md_['init'][0] != -32768 and md_['final'][0] != -32768 and \
                        md_['final'][0] >= md_['init'][0] and md_['final'][0] > 0:
                    # R 2026-11-08 (STICKALPHA0, user ギガンテックフィールド 「前に滑り出さない」): also a slow / zero 増分
                    # (ギガンテックフィールド 80 -> 128 at 8/256 px/tick: about 80 px ahead for the whole phase); with slot 11 the
                    # offset is the slot 18 value itself (STICKALPHAPOS), so a constant α is just a held value.
                    # R 2026-11-04 (STICKALPHA, user 20261103_4 #6 「弾が前進しない」): BFE flag 0x04 「常に標的位置＋α」
                    # (dlg168 4002) puts the object at the target + α, α running 初期値 -> 最終値 by 増分/256 px per tick
                    # (ｴﾈﾙｷﾞｰﾌｨｰﾙﾄﾞ ph0: 24 -> 128 at 6 px/tick: the field slides ~104 px ahead of 透 and stays there, 原作
                    # orig6.mp4). Vanilla Ｅフィールド：甲Lv3 T0 does the same with slot 11 前指定 + slot 15 + slot 18 30 -> 0
                    # (the kept offset moves with the object's own velocity). -> slot 15 角度指定→スプライト方向 + slot 18 the
                    # α step in raw BFE px/tick (BSPEED 50 %) until α reaches 最終値, then 0.
                    a0_, a1_ = (md_['init'][0] + md_['init'][1]) / 2.0, (md_['final'][0] + md_['final'][1]) / 2.0
                    st_ = md_['step'][0] / 256.0
                    n_ = min(L, 2 * int(math.ceil((a1_ - a0_) / st_))) if st_ > 0 else 0
                    a1_ = min(a1_, a0_ + st_ * n_ / 2.0)
                    # R 2026-11-06 (STICKALPHADIR2, user EF.mp4 / 原作_EF.mp4 11/06: still on 透): vanilla Ｅフィールド：甲Lv3 T0
                    # keeps slot 15 over the whole slide (F0-100) with the term's intList3 [2, 0] (the bullet idiom of
                    # パラレルミサイル：甲 / 波動砲：甲, 77 uses); ours was F0 only with [0, 0] -> same span and mode as vanilla.
                    # E 2026-11-07 (STICKALPHAPOS, user エネルギーフィールド.mp4 11/07: still on 透): with slot 11 active BaldrSky.exe
                    # 0x610e70 rewrites the position every frame to 親 + 固定オフセット (0x610ed0-0x610f25) and then adds only THIS
                    # frame's move vector (0x610f85), so the slot 18 speed is the offset itself and never accumulates (the 甲 EF
                    # 30 = 30 px ahead). Ours was 6 px/tick (3 px/F, then 0) = the field stayed on 透 -> slot 18 = α: 2×α raw
                    # (BSPEED 50 %) ramped a0 -> a1 and held for the rest of the turn, slot 15 over the whole turn.
                    d15_ = self._dir_event(0, 0, 0); d15_['endFrame'] = L - 1
                    d15_['bsdxInfoCollectionList'][0]['intList3'] = [2, 0]
                    ev[15].append(d15_)
                    r0_, r1_ = int(round(2 * a0_)), int(round(2 * a1_))
                    if n_ > 0:
                        ev[18].append(lib.obj(18, 3, 0, max(0, n_ - 1), int1=0, int2=r0_, int4=0, int5=r1_))
                    stick_follow_ = (d15_, r1_)
                    if n_ < L:
                        ev[18].append(lib.obj(18, 3, n_, L - 1, int1=0, int2=r1_, int4=0, int5=r1_))
                    moving = True
                    rep.add('STICKALPHA', 'bullet 常に標的位置＋α %d -> %d at %.1f px/tick -> slot 15 スプライト方向 + slot 18 %d for %dF (vanilla Ｅフィールド：甲)' % (
                        a0_, a1_, st_, int(round(st_)), n_))
                if getattr(self.fx, 'keep_touch', None) and not ev[51]:
                    o = copy.deepcopy(self.fx.keep_touch); o['startFrame'] = o['endFrame'] = 0; o['offset'] = 0
                    ev[51].append(o)
                    rep.add('STICK', 'bullet move_dir 5 -> slot 51 接触 all off at F0 (vanilla マインナックル：甲 / シールド：甲)')
            elif bullet and stick_follow_ and ph['move_dir']['type'] in (0, 1) and getattr(self.fx, 'keep_pos', None) and                     ph['speed']['init'][0] in (0, -32768) and ph['speed']['final'][0] == 0:
                # E 2026-11-08 (STICKFOLLOW, user エネルギーフィールド / ギガンテックフィールド 「後半、爆風が自機の近くへ瞬間移動」): when the
                # slot 11 turn ends, BaldrSky.exe puts the object back at anchor + offset (0x607880 via 0x60cbb2: the spawn
                # point at 透) instead of where it was drawn (親 + α). The still later phases of an α field (move_dir 0/1,
                # speed 0) keep slot 11 + the last α so the burst stays in front of 透 (it follows 透 instead of staying
                # in place: approximation).
                # E 2026-11-09 (STICKHOLD, replaces the 11/08 follow; user 「手を引っ込めるポーズで射出位置の指定が変わるのに、なお追従
                # しているのが問題では」): BFE ph1/ph2 have 移動方向 0/1 and speed 0 = the field stays where the pose change left it
                # (ph0 ends on go_mech_spr). -> slot 11 「オブジェクト位置を直値に」 自分 (Term g20 [3], intList3 [0, 0]; vanilla
                # ICBM / 高速電撃 use [3]) over the turn with speed 0: the position is taken once from where it is drawn and held,
                # instead of 前指定を維持 + α (which followed 透) or nothing (which snapped back to 透).
                # R 2026-11-15 night (user: 「原作は構えの間だけ透に付く作り」を甲と同じ組み方で): vanilla Ｅフィールド：甲Lv3 has slot 11
                # in T0 only and nothing in T1 / T2; the 直値 自分 slot 11 placed here on 11/09 was never confirmed in game.
                # -> no slot 11 after the follow turn, speed 0 (the bullet stays where the follow turn left it).
                ev[18] = [lib.obj(18, 3, 0, L - 1, int1=0, int2=0, int4=0, int5=0)]
                moving = False
                rep.add('STICKHOLD', '%s ph%d: after a 常に標的位置＋α phase (still, speed 0) -> no slot 11, speed 0 (vanilla Ｅフィールド：甲Lv3 T1)' % (name_ja, pi))
            elif bullet:
                md = ph['move_dir']
                once_ = md['type'] == 2 and not md['flags'] & 2
                if md['type'] in (2, 5):
                    # R 2026-11-06 (AIMONCE, user 11/06 ボミングビット「敵の上で 1F ごとに向きが変わって停滞」, 原作 Original 通常武装
                    # 3:30 = passes over the enemy's head): dlg168 flag 0x02 「常に方向ﾁｪｯｸ」 off -> the heading toward the
                    # lock-on enemy is taken once at the phase start (ﾋﾞｯﾄ（爆弾投下） Lv3 ph1: type 2, flags 0, 増分 0).
                    # Without the flag the converted slot 15 re-aimed every frame -> slot 15 at F0 only (vanilla F0-0 aims).
                    o = copy.deepcopy(self.fx.homing_dir); o['startFrame'], o['endFrame'], o['offset'] = 0, 0 if once_ else L - 1, 0
                    l2_ = ph.get('lock2') or {}
                    if l2_.get('type1') == 2 and o.get('bsdxInfoCollectionList'):
                        # R 2026-11-08 (LOCKPARENT, user 集束波動砲 「溜めが銃口ではなく自機と敵の間に出る」, 原作 FC 2:17): BFE ﾛｯｸ座標2
                        # (移動目標, phase +0x168) type 2 = the parent (★吸い込まれる火花 ph1, at its 判定 rect = the muzzle)
                        # -> slot 15 オブジェクト位置指定 親 (Term g1 [2]) instead of 標的: the sparks converge on 透.
                        o['bsdxInfoCollectionList'][0]['intList4'] = [2, 0]
                        rep.add('LOCKPARENT', 'bullet ﾛｯｸ座標2 (移動目標) type 2 = 親 -> slot 15 toward the parent')
                    ev[15].append(o)
                    if once_:
                        rep.add('AIMONCE', 'bullet move_dir 2 without 常に方向ﾁｪｯｸ -> slot 15 オブジェクト位置指定 at F0 only')
                    rate = abs(md['step'][0]) / 51.2 if md['step'][0] else (999 if md['type'] == 5 else 0)
                    if rate and not once_:
                        ev[17].append(lib.obj(17, 3, 0, L - 1, int1=0, int2=int(round(rate)), int4=0, int5=int(round(rate))))
                if md['type'] in (2, 5) and md['final'][0] != -32768 and (md['final'][0] or md['final'][1]):
                    # homing toward target ± random offset (多弾頭ﾐｻｲﾙﾎﾟｯﾄﾞ final -85..85: each missile turns to a random
                    # heading around the target -> wide random spread). Vanilla 「小型ミサイル：メタルカーゴ」: slot 15 target +
                    # slot 16 方向補正 -30±60 at frame 0 + slot 17 rate.
                    lo, hi_ = -md['final'][1], -md['final'][0]          # ANGLESIGN (see _set_fire)
                    if md['flags'] & 16 and lo != hi_:
                        # R 2026-11-04 (HOMING_EITHER): BFE flag 0x10 「最終値：ﾗﾝﾀﾞﾑ間なし」 (dlg168 4004) = the offset is
                        # either end, never in between. ｶﾞﾄﾘﾝｸﾞﾋﾞｯﾄ ph1 (type 2, flags 0x13 = 最短ﾙｰﾄ + 常に方向ﾁｪｯｸ,
                        # final -90/90, step 0): heading = target bearing ±90 every tick = circles the enemy while
                        # firing. DiveX keeps slot 16 方向補正 (+0x174c) and adds it to the slot 15 target every frame
                        # (0x606d34, 0x60c02b), but ValRandom ±90 is uniform, so most rolls point inward and the bit
                        # rammed the enemy (user 4.mp4). -> lo here, hi in a clone turn picked by 汎用→確率 5000
                        # (rand%10000 < v, 0x667c10; vanilla ミサイルランチャー：甲 uses the same condition).
                        o16 = lib.obj(16, 3, 0, 0, int1=0, int2=lo, int3=0, int4=0, int5=lo, int6=0); o16['_alt16'] = hi_
                        ev[16].append(o16)
                        rep.add('HOMING_EITHER', 'bullet homing with target offset %d or %d (最終値：ﾗﾝﾀﾞﾑ間なし) -> slot 16 %d / clone turn %d, 50%%' % (lo, hi_, lo, hi_))
                    else:
                        ev[16].append(lib.obj(16, 3, 0, 0, int1=0, int2=lo, int3=0, int4=0, int5=lo, int6=hi_ - lo))
                        rep.add('HOMING_OFFSET', 'bullet homing with target offset %d..%d -> slot 16 (vanilla メタルカーゴ)' % (lo, hi_))
                elif md['init'][0] != -32768 and (md['init'][0] or md['init'][1]):
                    lo, hi_ = -md['init'][1], -md['init'][0]            # ANGLESIGN (see _set_fire)
                    rep.add('ANGLESIGN', 'bullet move_dir %d..%d -> slot 16 %d..%d (DiveX angle = -BFE angle)' % (md['init'][0], md['init'][1], lo, hi_))
                    ev[16].append(lib.obj(16, 3, 0, 0, int1=0, int2=lo, int3=hi_ - lo, int4=0,
                                          int5=lo, int6=hi_ - lo))
                spin_end = 0
                cd = ph['chip_dir']
                if cd['init'][0] != -32768:
                    chip_off = (cd['init'][0] + cd['init'][1]) / 2.0
                elif cd['type'] in (0, 1) and cd['final'][0] != -32768 and cd['step'][0] > 0:
                    # BFE チップ向き offset moves from its current value to 最終 at 増分/256 deg per tick (calc_dir, same
                    # interpolator as speed): ﾘｻｰﾁﾐｻｲﾙ ph0 0 -> 360 at 15..30 deg/tick, ph1 360 -> 0 = the missile sprite
                    # spins while it flies out (reported 2026-10-27: 'BFE rotates while launched, BSX goes straight'; the
                    # old rule always pointed the sprite along the movement). Vanilla spinning bullets 「スプレッドパンチ：甲」
                    # / 「グラビティボム：甲」: slot 9 方向補正 -9999 + slot 10 方向増分 (0.1 deg/F, same unit as slot 17).
                    c1 = (cd['final'][0] + cd['final'][1]) / 2.0
                    st = (cd['step'][0] + cd['step'][1]) / 2.0
                    dd = c1 - chip_off
                    if abs(dd) >= 1:
                        full = int(math.ceil(abs(dd) * 256 / st)) * 2
                        spin_end = min(L, full)
                        # S 2026-10-30: BaldrSky.exe 0x60bbe9 / 0x606b00: slot 9 -9999 = RANDOM spin sense per object
                        # (rand & 1 -> mode -9998 / -9999), -9998 -> +90 deg ahead (angle increases), -9997 -> -90 deg
                        # (decreases); slot 10 = |rate| (0.1 deg/F; a NEGATIVE rate = 360 deg/F, i.e. snap). 10/28 移植版6:
                        # missiles spun both ways; 原作10: all clockwise (BFE +). DiveX angle = -BFE angle (ANGLESIGN) ->
                        # BFE + (CW) = DiveX decreasing = -9997. The spin end resets slot 9 to 0 (else the sprite stays 90
                        # deg off its base direction).
                        r = int(round(st / 51.2)); rr = int(round((cd['step'][1] - cd['step'][0]) / 2.0 / 51.2))
                        mode = -9997 if dd > 0 else -9998
                        ev[9].append(lib.obj(9, 3, 0, 0, int5=mode))
                        ev[10].append(lib.obj(10, 3, 0, 0, int5=r, int6=rr))
                        if spin_end < L:
                            ev[9].append(lib.obj(9, 3, spin_end, spin_end, int5=0))
                            ev[10].append(lib.obj(10, 3, spin_end, spin_end, int5=9999))
                        chip_off = c1 if full <= L else chip_off + dd * L / float(full)
                        rep.add('SPIN', 'bullet チップ向き %+.0f deg at %.1f deg/tick -> slot 9 %d (%s) / 10 rate %d (±%d) for %dF (exe 0x606b00)' % (
                            dd, st / 256.0, mode, 'CW' if dd > 0 else 'CCW', r, rr, spin_end))
                # R 2026-11-08 (CHIPAIR, user 鳳凰落とし / 鷹落とし 「三角形が上空ではなく敵の方を向く」, 原作 FC 2:08): チップ向き 2
                # 移動方向(空中用) on a shot that only rises (真上ｼｮｯﾄ: 速度 0 -> ±4, x開始 4..5) also needs slot 8
                # 移動方向（高さ含む）; with no horizontal speed the sprite kept the spawn facing (toward the enemy).
                if (moving or (cd['type'] == 2 and ph['jump']['x_start'][0] > 0)) and spin_end < L:
                    face_t = cd['type'] in (1, 3, 4) and getattr(self.fx, 'sprite_target', None) is not None and                         not (cd['step'][0] and ph['move_dir']['type'] == 2 and cd['step'][0] == ph['move_dir']['step'][0])
                    # R 2026-11-07 (CHIPMOVE, user ホーミングミサイル 向き; 原作 通常武装 2:05 は進行方向): チップ 敵方向 turning at the same 増分 as
                    # the 移動方向 敵方向 from the same start = the sprite stays on the heading (ﾎｰﾐﾝｸﾞﾐｻｲﾙ 2048 / 2048); slot 8
                    # オブジェクト位置指定 snaps to the enemy at once -> keep スプライト方向＝移動方向 (vanilla ホーミングミサイル：甲).
                    # R 2026-11-05 (CHIPTARGET, user 11/05 「ﾚｰｻﾞｰﾋﾞｯﾄとﾊﾞﾙｶﾝﾋﾞｯﾄは敵に背を向けている」): dlg169 計算（チップ方向）
                    # 向きﾀｲﾌﾟ 0 向き修正なし / 1 ﾛｯｸｵﾝした敵方向 / 2 移動方向(空中用) / 3 敵座標（１回） / 4 敵座標（常時）
                    # (the 移動方向 radio of dlg168 differs). ﾚｰｻﾞｰﾋﾞｯﾄ ph2 moves to target +180 (away) with chip type 1, and its
                    # laser is fired 相対位置 (dir_mode 1) = along the chip -> the sprite must face the enemy, not the movement.
                    # Vanilla レーザービット：甲Lv3 slot 8 「オブジェクト位置指定」 (sprite toward the target) + laser spawned at スプライト方向.
                    o = copy.deepcopy(self.fx.sprite_target if face_t else self.fx.sprite_dir); o['startFrame'], o['endFrame'], o['offset'] = spin_end, L - 1, 0
                    ev[8].append(o); moving_any = True
                    if face_t:
                        rep.add('CHIPTARGET', 'bullet チップ向き type %d (敵方向) -> slot 8 オブジェクト位置指定 (vanilla レーザービット：甲)' % cd['type'])
                    if spin_end == 0 and spun_prev:      # the previous turn ended mid-spin: face the movement again
                        ev[9].append(lib.obj(9, 3, 0, 0, int5=0))
                        ev[10].append(lib.obj(10, 3, 0, 0, int5=9999))
                spun_prev = spin_end >= L > 0 and bool(ev[10])
            nk_ml = ph['noke_mech']; hi_ml = ph['hit']
            if bullet and 1 < hi_ml['hits_mech'] < 254 and nk_ml['launch_accum'] >= 100 and nk_ml['launch'] > 0 and                     ph['touch_mech_enemy'] == 1 and not hi_ml['flags'] & 1:
                # R 2026-11-07 (MULTILAUNCH, user 対空スプレッドボム 原作 2:35: 敵がボムと一緒に上昇): BFE resets v = launch at each of the
                # hits while the bomb stays in contact (0x441f50, 0x444560); the DiveX bomb passes the victim and later hits
                # raise the gravity (0x6191de). -> one hit carries the whole BFE rise: (n-1) intervals of launch + the free flight.
                # 2026-11-08 (user 「少しだけ高く浮きすぎ」): the last of the n hits ends the phase (残りメカHIT数 0 -> ph1), so the
                # victim flies on n-1 launches (apex 158 -> 132 px for 対空ｽﾌﾟﾚｯﾄﾞﾎﾞﾑ)
                ph['noke_mech'] = dict(nk_ml, _ht=bfe_launch_multi(nk_ml['launch'], hi_ml['hits_mech'] - 1, hi_ml.get('hit_scale', 0) + 1))
                rep.add('MULTILAUNCH', '%s ph%d: launch %d x %d hits -> apex %d px, %d ticks' % (name_ja, pi, nk_ml['launch'], hi_ml['hits_mech'], ph['noke_mech']['_ht'][0], ph['noke_mech']['_ht'][1]))
            if bullet and ph['noke_mech']['direction'] == 2 and ph['jump']['x_start'][0] != 0:
                ph['noke_mech'] = dict(ph['noke_mech'], _vert=True)
            jp = ph['jump']; x0 = jp['x_start'][0]; dx = jp['dx_init'][0]
            dive_ = divetouch_ = False
            if jp['dx_step'][0] == 0 and jp['dx_final'][0] != -32768:
                dx = jp['dx_final'][0]       # 増分 0 = final at once (same interpolator, 0x4489d2): 手榴弾 0 -> -96
            expects_land = ph['go_land'] != -99 or any(e['anim_type'] == 3 for e in ph['events'])
            lift = None            # mech: first frame at which the phase, entered on the ground, is airborne (None = never)
            vtr = None             # mech: BFE (h, v) after each tick of this turn (None = unknown state), M 2026-10-30
            vh0 = 0                # mech: BFE height at the start of this turn (POSTAPEX), M 2026-10-31
            if not bullet:
                # M 2026-10-28: the BFE vertical curve of the phase (bfe_vert_sim, exe 0x440150 / 0x4402e0) -> slot 19
                # velocity events + gravity 0 (_vert_events). Replaces 「4*x0 -> x0/2 for 3F + gravity |dx|*50/256」 and the
                # dive idiom, and adds the cases they dropped: x0 0 / dx 0 = hold the height (爆撃ﾐｻｲﾙ firing, ﾀｯｸﾙ
                # recovery; vanilla 甲 タックル T0 ジャンプ力 0 + 重力 0). M 2026-10-29: x増分 is averaged with the base block
                # (g_eff = (x増分 - 128) >> 1, see BFE_BASE_G): +128 = hold, below falls (爆撃ﾐｻｲﾙ ph2 +123 = slow descent).
                # A phase that keeps the trajectory (flag 4) at an unknown state (skill start) emits nothing.
                if jp['flags'] & 4 and jp['dx_init'][0] == -32768 and not vknown:
                    pass
                else:
                    if any(t_ == ti_ for _s, t_ in air_dispatch):
                        vst['h'] = max(vst['h'], AIR_H)
                    gst = dict(vst, h=0)
                    gd = bfe_vert_sim(jp, (L + 1) // 2, gst)            # same phase entered on the ground
                    hh = 0
                    for k_, d_ in enumerate(gd):
                        hh += d_
                        if hh > 0:
                            lift = 2 * k_; break
                    vtr = []; vh0 = vst['h']
                    st0 = dict(vst)
                    dts = bfe_vert_sim(jp, (L + 1) // 2, vst, trace=vtr); vknown = True
                    nk_ = ph['noke_mech']
                    if ti_ in hit_entry and ph['touch_mech_enemy'] == 1 and not ph['hit']['flags'] & 1 and \
                            ph['hit']['hits_mech'] not in (0, 254) and sum(dts) > 0 and nk_['launch_accum'] >= 100 and nk_['launch'] > 0:
                        # G 2026-11-04 (TOUCHCARRY, 調査記録 30): BFE 0x444560 - an object whose contact flags (+0x301 & 0xa,
                        # set by 0x4422e0 when it touches an enemy mech with 接触 メカ敵 1 通常) are on does NOT move that
                        # tick; only hit flag bit0 「ﾋｯﾄ中も高さ可変」 keeps the vertical update (0x4402e0), and the velocity
                        # stays frozen. ﾌﾞｰｽﾄｱｯﾊﾟｰ ph2 (the only Tooru phase without bit0) is entered by the ph0 hit, so 透 starts
                        # in contact and rises only as far as the launched enemy lets him (原作1: 透 and the enemy go up
                        # together, 2nd hit connects). DiveX has no such freeze -> 透 flew 169 px past short enemies (1 hit,
                        # user 20261103_4). -> 透's height = his own curve, never passing the victim launched by this
                        # phase's hit (bfe_launch physics from the ground); a blocked tick keeps his velocity.
                        vv = nk_['launch'] * 256; hv = 0; ht = st0['h']; i_ = 0; own_c_ = 0; hmax_ = 0; v_own = vtr[0][1] if vtr else 0
                        own_v = [mid_v for _h, mid_v in vtr]
                        new = []; ntr = []; v_cur = (jp['x_start'][0] + jp['x_start'][1]) // 2 * 256 if not jp['flags'] & 4 else st0['v']
                        for k_ in range(len(dts)):
                            vv -= BFE_LAUNCH_G; q_ = vv >> 8
                            hv = max(0, hv + max(-48, min(48, q_ * q_ * (1 if vv >= 0 else -1))))
                            # G 2026-11-04 (TOUCHCARRY smooth, user: 「自機の上昇がガクガク」): the all-or-nothing own step gave
                            # 24 px / 0 / 18 px ticks. -> 透's height = min(his free curve, the enemy's highest point so far):
                            # he rides the enemy's parabola tick by tick and never drops with it.
                            own_c_ += dts[k_]; hmax_ = max(hmax_, hv)
                            nh_ = st0['h'] + min(own_c_, hmax_) if dts[k_] >= 0 else ht + dts[k_]
                            new.append(nh_ - ht); ht = nh_; v_cur = own_v[k_]
                            ntr.append((ht, v_cur))
                        rep.add('TOUCHCARRY', '%s turn %d: 接触 メカ敵 1 without ﾋｯﾄ中も高さ可変, entered by a hit -> rises with the '
                                'launched enemy (L%d): BFE %+d -> %+d px (0x444560 contact freeze)' % (
                                    name_ja, ti_, nk_['launch'], sum(dts), sum(new)))
                        dts = new; vtr[:] = ntr; vst['h'] = ht; vst['v'] = v_cur
                    e19, e21 = self._vert_events(dts, L)
                    ev[19] += e19; ev[21] += e21
                    ground_vert[ti_] = self._vert_events(gd, L)
                    rep.add('VERT', 'mech jump x開始 %s / x増分 %s%s -> BFE height %+d px in %dF -> slot 19 x%d, 重力 0' % (
                        jp['x_start'][0], jp['dx_init'][0], ' (keep)' if jp['flags'] & 4 else '', sum(dts), L, len(e19)))
            elif bullet and x0 > 0 and jp['dx_init'][0] != -32768:
                # S 2026-10-29: launched bullet (x開始 > 0) -> the exact BFE curve (bfe_bullet_vert: g_eff = (x増分 - 128)
                # >> 1, M SIGN_DECISION_20261029) as slot 19 velocity events + 重力 0 (_vert_events, the mech rule), the
                # descent continuing until the DiveX 着地 test. Replaces RISE (held x0..8 px/F), LOB (apex fit to a
                # literal x増分 deceleration + slot 21 as /100: DD rose 306 px and landed at ~1.6 s, BFE: 440 px apex at
                # ~45 ticks, ground at ~88 ticks = 2.9 s, 通常武装.mp4) and the mech calibration 4*x0 / gravity 50 (手榴弾).
                # dx +128 (真上ｼｮｯﾄ, 対空ｽﾌﾟﾚｯﾄﾞﾎﾞﾑ, ﾋﾞｯﾄ爆弾投下) = no gravity: x0^2 px/tick for ever.
                dts = bfe_bullet_vert(jp, (L + 1) // 2)
                e19, e21 = self._vert_events(dts, L)
                ev[19] += e19; ev[21] += e21
                rising = dx > 0 and not expects_land
                hs_ = list(itertools.accumulate(dts)) or [0]
                k_ = hs_.index(max(hs_))
                land_ = next((2 * (j_ + 1) for j_, h_ in enumerate(hs_) if h_ <= 0 and j_ > 0), None)
                rep.add('BVERT', 'bullet x開始 %s / x増分 %s->%s -> BFE g_eff %+d: apex %dpx at %dF, ground %s in %dF -> slot 19 x%d, 重力 0' % (
                    jp['x_start'][0], jp['dx_init'][0], jp['dx_final'][0], (dx + BFE_BASE_G) >> 1, max(hs_), 2 * (k_ + 1),
                    'at %dF' % land_ if land_ else 'not reached', L, len(e19)))
                nk_r = ph['noke_mech']
                if nk_r.get('_ht') and len(e19) == 1 and (e19[0].get('int5') or 0) > 0 and len(set(dts)) == 1:
                    # R 2026-11-17 (RIDELAUNCH, tester report 対空スプレッドボム 「敵を打ち上げる高度が弾の進行よりもほんの若干高く、
                    # 弾が敵の足先に当たるとヒット中に外れる。敵が弾より低い位置で当たると爆発までヒットする」): MULTILAUNCH gave
                    # one hit the whole BFE rise (規模 75 = 7.5 px/F), but DiveX re-launches on every hit (0x6191b9 assigns
                    # vz = 規模/10) -> each 8F interval the victim gained ~20 px on the bomb (4 px/F) and a victim touched at
                    # its feet left the hit rect. BFE: the bomb stops while it touches the victim (touch 1, 0x444560), so
                    # bomb and victim rise together (原作 2:35). -> 規模 so that the victim's mean rise per hit interval
                    # equals the bomb's: vz_bomb + a*T/2, a = 0.25 * 重力/100 * victim base gravity/50 (base 50 for hits
                    # 1-2, then 20n+10, 0x6191de) averaged over hits 1..n-1. 重力 stays the MULTILAUNCH fit.
                    H_r, t_r = nk_r['_ht']; T_r = 2 * t_r
                    g_r = max(1, int(round(3200.0 * H_r / (T_r * T_r))))
                    n_r = ph['hit']['hits_mech']; iv_r = 2 * (ph['hit'].get('hit_scale', 0) + 1)
                    base_r = [50 if k_r <= 2 else 20 * k_r + 10 for k_r in range(1, n_r)]
                    a_r = 0.25 * g_r / 100.0 * sum(base_r) / len(base_r) / 50.0
                    vz_r = e19[0]['int5']
                    s_r = int(round(10 * (vz_r + a_r * iv_r / 2.0)))
                    ph['noke_mech'] = dict(nk_r, _ride=s_r)
                    rep.add('RIDELAUNCH', '%s ph%d: bomb rises %d px/F, %d hits / %dF -> 吹き飛び規模 %d (victim keeps pace; 重力 %d, mean victim gravity %.3f px/F^2)' % (
                        name_ja, pi, vz_r, n_r, iv_r, s_r, g_r, a_r))
            elif bullet and x0 <= 0 and dx != -32768 and not jp['flags'] & 4 and jp['flags'] & 2 and \
                    jp['min_height'][0] == 0 and expects_land and ((dx + BFE_BASE_G) >> 1 < 0 or x0 < 0):
                # R 2026-11-04: expects_land (go_land or an anim 「地面に着地するまで」) instead of go_land alone: ﾋﾞｯﾄ
                # （爆弾投下）の爆弾 ph0 (x開始 0, x増分 64 -> g_eff -32, flag 2, 最低高さ 0) ends by its landing anim, no
                # go_land -> no vertical event, the bomb hung at the bit's height (user 4.mp4 「ボムが落下しない」).
                # G 2026-11-03 (BFALL, 調査記録 26 §G1): a bullet fired level (x開始 <= 0) whose phase ends on landing falls in
                # BFE: the same tick physics as BVERT (0x4402e0, v = x開始<<8 at the phase start 0x440150, g_eff = (x増分
                # - 128) >> 1) down to the absolute floor 0 (flag 2 「最低高さを直値に」, 最低高さ 0; without flag 2 the floor
                # is the start height and nothing falls, 0x4403a1), then 着地時 -> the go_land phase. ガトリングガン Lv1/2
                # (x増分 -64 -> g_eff -96): 1,1,4,4,4,9,9,9,16 px per tick -> lands within one 9-tick pass from the muzzle
                # (原作 通常武装.mp4 101.6-102.4 s: landing smoke ~250-370 px from the muzzle). The converter emitted no
                # vertical motion here (BVERT needs x開始 > 0), so the DiveX bullet never met its 着地 test and flew 10 x
                # 18F (LOOPPOS) = ~4300 px. Each pass of a looping phase restarts v (BFE 0x440150 / DiveX turn F0 events).
                dts = bfe_bullet_vert(jp, (L + 1) // 2)
                e19, e21 = self._vert_events(dts, L)
                ev[19] += e19; ev[21] += e21
                rising = False
                rep.add('BFALL', 'bullet x開始 %s / x増分 %s, 最低高さ 0 (直値), go_land %s (or 着地アニメ) -> BFE g_eff %+d: falls %dpx in %dF -> slot 19 x%d, 重力 0, DiveX 着地 test' % (
                    jp['x_start'][0], jp['dx_init'][0], ph['go_land'], (dx + BFE_BASE_G) >> 1, -sum(dts), L, len(e19)))
            elif bullet and x0 == 0 and (dx == 0 or dx == -32768 or (dx + BFE_BASE_G) >> 1 == 0) and                     (rising or (ti_ > 0 and phases[turn_phase[ti_ - 1]]['move_dir']['type'] == 5 and ph['move_dir']['type'] != 5) or
                     (ti_ > 0 and dx != -32768 and any((o_.get('int2') or 0) or (o_.get('int5') or 0) for t_ in turns for o_ in t_[0][19]))):
                # R 2026-11-15 (BHOLDANY, user DD.mp4 11/15 「爆風が当たっていない」: the hit blast flew up off the screen): BFE
                # sets v = x開始 << 8 at EVERY phase start (0x440150), so a zero jump block stops the bullet wherever the
                # previous phase's flight had brought it. `rising` only covered a rise that never lands; DDﾐｻｲﾙ ph0 (x開始 6,
                # 着地まで) hit on its way up and ph2 (zero block) kept the DiveX ジャンプ力 13 of turn 0 -> the 5-hit blast
                # left the enemy at 13 px/F. -> any earlier turn of the bullet with vertical movement.
                # R 2026-11-07 (BHOLDSTUCK, user マインナックル.mp4: 爆発が真上へ飛んでいく): a stuck bullet's height is the 甲 spawn's
                # ジャンプ力 (sub 32, an offset while slot 11 holds it, 0x610f98). The next turn has no slot 11, so that speed
                # moved it for real and 吸着ﾏｲﾝ's explosion flew off the top of the screen -> v 0 like the rising case.
                # BFE zero jump block = v 0 / g 0 -> the bullet stays at its height (鷹落とし explosion in the air;
                # vanilla 対空スプレッドボム：甲Lv3 T1: ジャンプ力 0 at frame 0).
                # R 2026-11-04 (BHOLD): also x増分 +128 (g_eff 0, v = x開始<<8 = 0 at the phase start, 0x440150):
                # ﾋﾞｯﾄ（爆弾投下） ph1 after the rising ph0 kept the 4 px/F of turn 0 and climbed off-screen (user 4.mp4).
                ev[19].append(lib.obj(19, 3, 0, 0, int1=0, int2=0, int4=0, int5=0)); ev[21].append(lib.obj(21, 2, 0, 0, int5=0))
                if dx not in (0, -32768):
                    rep.add('BHOLD', 'bullet x開始 0 / x増分 %d (g_eff 0) after a rise -> slot 19 0, 重力 0 (BFE v = 0 at the phase start)' % dx)
                if not rising and ti_ > 0 and phases[turn_phase[ti_ - 1]]['move_dir']['type'] != 5:
                    rep.add('BHOLDANY', '%s ph%d: zero jump block after a flight -> slot 19 0, 重力 0 at F0 (BFE v = x開始 at the phase start)' % (name_ja, pi))
            elif bullet and ti_ == 0 and x0 == 0 and dx != -32768 and not jp['flags'] & 12 and \
                    ((dx + BFE_BASE_G) >> 1 >= 0 or (jp['flags'] & 2 and jp['min_height'][0] > 0)):
                # (2026-11-06: the 11/05 extension to flag 8 + move_dir 5 was reverted: it zeroed the 甲 template's spawn
                # ジャンプ力 (sub 32) of 吸着ﾏｲﾝ, which then sat at the enemy's feet - user 11/06 吸着マイン.mp4.)
                # R 2026-11-04 (BHOLD): first turn of a bullet that BFE starts with v = x開始<<8 = 0 (0x440150) and that
                # never falls below its spawn height (g_eff >= 0, or a floor 最低高さ > 0 as an absolute height, flag 2,
                # 0x4403a1). With no slot 19 / 21 the DiveX bullet kept the spawn's ジャンプ力 from the 甲 template
                # (sub 32: 甲 レーザービット 50, no 重力) and 透用ﾚｰｻﾞｰﾋﾞｯﾄ rose off-screen (user 4.mp4). The floor case is
                # held at the spawn height (透用ﾚｰｻﾞｰﾋﾞｯﾄ: floor 48 px, muzzle height about the same).
                ev[19].append(lib.obj(19, 3, 0, 0, int1=0, int2=0, int4=0, int5=0)); ev[21].append(lib.obj(21, 2, 0, 0, int5=0))
                rep.add('BHOLD', 'bullet turn 0 x開始 0 / x増分 %d / flags %d / 最低高さ %d -> slot 19 0, 重力 0 (no spawn ジャンプ力 carry-over)' % (
                    dx, jp['flags'], jp['min_height'][0]))
            elif bullet and x0 > 0:
                rising = False
                ev[19].append(lib.obj(19, 3, 0, 2, int2=4 * x0, int5=max(1, x0 // 2)))
                g = round(abs(dx) * 50 / 256) if dx < 0 else 50
                ev[21].append(lib.obj(21, 2, 0, 0, int5=g))
            elif bullet and x0 == 0 and dx != -32768 and dx <= -200:
                # R 2026-11-04 (BDIVE): was a flat jump -20 / gravity 0 (Kou ブーストキック idiom). The only user is
                # ｻﾃﾗｲﾄﾚｰｻﾞｰ's beam (x増分 -1024, 最低高さ -9999 relative = no floor, 0x4403a1): BFE falls 1,9,25,48,48..
                # px per tick (bfe_bullet_vert) -> ~24 px/F; the flat -20 did not reach the ground within the 178F turn from
                # the spawn height, so the beam and its ground blast stayed above the screen (user: radar shows the hit,
                # no effect on screen). Same tick physics as BVERT / BFALL.
                dts = bfe_bullet_vert(jp, (L + 1) // 2)
                e19, e21 = self._vert_events(dts, L)
                ev[19] += e19; ev[21] += e21
                dive_ = True
                rep.add('BDIVE', 'bullet x開始 0 / x増分 %d (g_eff %+d), no floor -> BFE fall %dpx in %dF -> slot 19 x%d, 重力 0' % (
                    dx, (dx + BFE_BASE_G) >> 1, -sum(dts), L, len(e19)))
            # ---- body collision (BFE 接触処理 メカ敵 0 = pass through: ｷｬﾉﾝﾌﾞﾚｲｶｰ ph3, ｷﾞｬﾗｸﾃｨｯｸｽﾄﾗｲｸ ph3 - the same phases
            # where 甲 GS / Ｉ・Ａ・Ｉ switch 接触 水平：メカ(敵) to 0) -> copy 甲 Ｉ・Ａ・Ｉ's slot 51 objects
            # G 2026-11-11 (SINK, user 「原作はインペリアルをダッシュしながら撃つと敵にめり込みつつ攻撃できたが、移植版はめり込めない」):
            # BFE has no push-out between mechs: the move step (0x4447a0 -> 0x4451e0 / 0x4458c0) only refuses to ENTER
            # another mech's box and ignores a box it already overlaps, and a hit only freezes the mover for that tick
            # (0x4422e0 sets +0x301 & 2, 0x444560). ｲﾝﾍﾟﾘｱﾙ ph0 keeps the dash momentum (速度 初期値 変更しない) and its
            # hit box sits on 透's own body (SPR slot 4/19/20 = -12..16 px), so in BFE 透 slides into the enemy and hits
            # it there. DiveX pushes the bodies apart (水平：メカ（敵） 1) and stopped 透 at the enemy's edge. -> the whole
            # technique gets the 甲 Ｉ・Ａ・Ｉ touch-off object at F0 of every turn; contact comes back on the last frame
            # of the final turn (as ｷﾞｬﾗｸﾃｨｯｸｽﾄﾗｲｸ's touch_on after ph4), so 透 does not stay overlapped after the move.
            sink_ = not bullet and name_ja in self.sink_skills
            if not bullet and self.fx is not None and hasattr(self.fx, 'touch_off'):
                if ph['touch_mech_enemy'] == 0 or sink_:
                    o = copy.deepcopy(self.fx.touch_off); o['startFrame'] = o['endFrame'] = 0; o['offset'] = 0
                    ev[51].append(o); touch_off_seen = True
                    if sink_:
                        rep.add('SINK', '%s ph%d: BFE 接触 メカ敵 %d (no push-out, dash momentum kept) -> slot 51 (甲 Ｉ・Ａ・Ｉ) body collision off' % (
                            name_ja, pi, ph['touch_mech_enemy']))
                        if pi == len(phases) - 1:
                            o = copy.deepcopy(self.fx.touch_on); o['startFrame'] = o['endFrame'] = L - 1; o['offset'] = 0
                            ev[51].append(o)
                            rep.add('SINK', '%s ph%d: last turn F%d -> slot 51 body collision back on' % (name_ja, pi, L - 1))
                    else:
                        rep.add('TOUCH', '%s ph%d: 接触 メカ敵 0 -> slot 51 (甲 Ｉ・Ａ・Ｉ) body collision off' % (name_ja, pi))
                elif touch_off_seen:
                    o = copy.deepcopy(self.fx.touch_on); o['startFrame'] = o['endFrame'] = 0; o['offset'] = 0
                    ev[51].append(o)
            # S 2026-10-29: a moving multi-hit bullet with BFE 接触 メカ敵 0 (火炎放射器, ﾌｫﾄﾝﾌﾞﾗｽﾀｰ) flies through the enemy and
            # hits it on the way. DiveX's default CEventTouch (0x641c50: 水平：メカ（敵） 1) stopped the flames at the enemy's
            # body edge, so they piled up in front of it and their small hit rect never reached it (no damage, short
            # range; 移植版7). Vanilla 「火炎放射器の炎：甲」 / 蜘蛛弾 / 暗黒弾 set 水平：メカ（敵） 0 at F0 -> the same slot 51
            # object as the mech rule (甲 Ｉ・Ａ・Ｉ, = 蜘蛛弾's bytes), restored by touch_on when a later phase has 接触 1.
            elif bullet and self.fx is not None and hasattr(self.fx, 'touch_off') and not ev[51]:
                hm_ = ph['hit']['hits_mech']
                # G 2026-11-04 (BTOUCH widened, user 20261103_4 #2 「EPX手榴弾・DDミサイルの爆風で敵が上でなく横に飛ぶ」):
                # the blast phases (接触 メカ敵 0, not moving) kept DiveX's default 水平：メカ（敵） 1, so the blast body
                # spawned beside the enemy shoved it sideways (its のけぞり速度 is 0: BFE v 0, launch only). Vanilla blasts
                # (Bomb.waz 爆風*, きのこ雲*: 117 of 125 slot 51 objects) turn every contact off. -> any bullet phase with
                # BFE 接触 メカ敵 0 gets the touch-off object, moving or not, hits or not.
                if ph['touch_mech_enemy'] == 0:
                    # R 2026-11-16 (BTOUCHFALL, user 「modified 版でサテライトレーザーが落下後に爆発しない、外すとレーザーが消滅する」,
                    # 調査記録 68): the 甲 Ｉ・Ａ・Ｉ touch-off object also carries マップOBJ / 進禁（メカ・弾）/ 画面端 = 2 (vanilla
                    # rifle-type bullets: vanish on contact). A bullet phase that keeps moving DOWN (converted slot 19
                    # ジャンプ力 < 0 in this turn; BFE x開始 -99 / -128 are not falls) pushed itself into the no-entry area under
                    # the floor and vanished there before 着地していたら (ｻﾃﾗｲﾄﾚｰｻﾞｰ pierce + blast phases). -> all 56 bytes 0,
                    # as vanilla 「サテライトレーザー：甲Lv3」 T1.
                    jp_ = ph['jump']
                    falls_ = any((o_.get('int5') or 0) < 0 or (o_.get('int2') or 0) < 0 for o_ in ev[19])
                    o = copy.deepcopy(self.fx.keep_touch if falls_ else self.fx.touch_off); o['startFrame'] = o['endFrame'] = 0; o['offset'] = 0
                    ev[51].append(o); touch_off_seen = True
                    if falls_:
                        rep.add('BTOUCHFALL', 'bullet ph%d: 接触 メカ敵 0 + 下向きの縦 (x開始 %s / x増分 %s) -> slot 51 all 0 '
                                '(進禁 2 = 床下で消える を外す, vanilla サテライトレーザー：甲Lv3 T1)' % (pi, jp_['x_start'], jp_['dx_init']))
                    rep.add('BTOUCH', 'bullet ph%d: 接触 メカ敵 0 (%s hits, %s) -> slot 51 水平：メカ（敵） 0 (vanilla 爆風 / 火炎放射器の炎：甲 / 蜘蛛弾)' % (
                        pi, 'unlimited' if hm_ == 255 else hm_, 'moving' if max(ph['speed']['init'] + ph['speed']['final']) > 0 else 'still'))
                elif touch_off_seen and ph['touch_mech_enemy'] == 1:
                    o = copy.deepcopy(self.fx.touch_on); o['startFrame'] = o['endFrame'] = 0; o['offset'] = 0
                    ev[51].append(o); touch_off_seen = False
            # G 2026-11-19 (WALLHIT, user 「ホーミング、リサーチ、フォトンブラスター（小さい段階）、多弾頭は原作では壁に接触すると
            # 次の段階（爆発）に進む。ただ消えてはまずい」, 調査記録 82): a bullet phase with BFE go_obstacle (壁 -> 次の段) must
            # register the wall. The 甲 Ｉ・Ａ・Ｉ touch-off / touch-on objects carry マップOBJ / 進禁（メカ）/ 進禁（弾） = 2
            # (vanilla rifle-type: the bullet vanishes on contact; 調査記録 68), so the missile vanished at the wall before the
            # change to the blast phase; phases without slot 51 kept the spawn value (unknown, 0 = no contact/overlap is
            # recorded, 0x60f6c3). -> in such a phase the F0 slot 51 has those three = 1 (blocked: contact recorded,
            # 0x60f6c3 / vf150 0x609de0; 進禁メカ -> 0, see below); a phase without its own slot 51 gets touch_on (DiveX default 0x641c50, as the
            # mech-enemy-1 phases after BTOUCH) with the same change. BTOUCHFALL's all-0 object is left alone.
            if bullet and ph['go_obstacle'] != -99 and self.fx is not None and hasattr(self.fx, 'touch_on'):
                f0_ = [o_ for o_ in ev[51] if o_['startFrame'] == 0]
                added_ = not f0_
                if added_:
                    o = copy.deepcopy(self.fx.touch_on); o['startFrame'] = o['endFrame'] = 0; o['offset'] = 0
                    ev[51].append(o); f0_ = [o]
                for o_ in f0_:
                    v_ = list(struct.unpack('<14i', bytes(o_['byteData1'])))
                    if any(v_):
                        old_ = tuple(v_[4:7])
                        # R 2026-11-19 (作者「ホーミングが壁をすり抜けないが、爆発せずぬるっと滑りながら進み続ける」): the
                        # map collision loop 0x60eb43 (table 0x85f244: 進禁メカ col 5 -> flag 2, 進禁弾 col 6 -> 4, 進禁穴 col 7
                        # -> 8) blocks on mode 1 and sets +0x1664 |= flag, but the wall test mask 18 has no flag 2: a mech-only
                        # wall stopped the missile without firing the change. Vanilla bullets ignore mech walls (ライフル：甲
                        # (0,0,0,0,2,0,2,0,0)) -> 進禁メカ 0; OBJ / 進禁弾 1.
                        v_[4] = 1 if v_[4] == 2 else v_[4]; v_[5] = 0; v_[6] = 1 if v_[6] == 2 else v_[6]
                        o_['byteData1'] = list(struct.pack('<14i', *v_))
                        rep.add('WALLHIT', '%s ph%d: go_obstacle -> slot 51 F0 OBJ/進禁メカ/進禁弾 %s -> %s%s' % (
                            name_ja, pi, old_, tuple(v_[4:7]), ' (added touch_on)' if added_ else ''))
            # ---- hit
            hi = ph['hit']; hits = hi['hits_mech']
            hit_window = None
            # S 2026-11-01 (NODMG): BFE hit flags bit5 ﾀﾞﾒｰｼﾞ処理をしない: 0x441566 -> 0x4418d6, on a mech only the
            # element tint 0x44ea00 (victim sprite colour, 感電 = 雷) - no damage, のけぞり, hitstop or hit count -> no slot 41
            # (感電（見えない） of ｽﾀﾝﾛｯﾄﾞ; it became a real 255-hit bullet once its spawn is a bullet object, SPAWNTYPE int1).
            # W 2026-11-03 (NODMG, superseded the 'no slot 41' rule, user 11/03 02:34): the bit5 path rejoins at 0x4418c7,
            # so BFE still plays the hit SE (0x417ce0) and the hit effect (0x426e00) on every hit; it skips only the damage
            # (0x442330 / 0x4425c0), のけぞり, the cancel flag (0x4416cc) and the hitstop -> a 威力 0 slot 41 (_nodmg_hit).
            nodmg_ = bool(hi['flags'] & 0x20)
            # R 2026-11-07 (NORECT, user 波動砲 「原作は 1 ヒット」): 攻撃判定ビット 0 = no active SPR rect. The whole-turn fallback is
            # for bullets with no bits anywhere (落雷); a bits-less phase of a bullet that has bits elsewhere never hits
            # (波動砲 ph1: the explosion, power 50 / HIT 255 are unused data).
            if hits not in (0, 254) and hi['power'] > 0 and (atk or (bullet and not any(e_['attack_rects'] for p_ in phases for e_ in p_['events']))):
                hs, he = (atk[0][0], max(b for a_, b in atk)) if atk else (0, L - 1)
                if ti_ in hit_entry and hs == 0 and he >= 1:
                    hs = 1                     # M 2026-10-29 HITDELAY (see hit_entry)
                    rep.add('HITDELAY', '%s turn %d: entered by a hit with hitstop -> hit window F0 -> F1 (BFE no hit during the freeze)' % (name_ja, ti_))
                hit_window = (hs, he)
                if first_attack is None:
                    first_attack = (ti_, hs)
                if not tpl_hits[41]:
                    if not self.default_hit:
                        raise ValueError('template has no hit: ' + name_ja)
                    tpl_hits[41] = [self.default_hit]
                    rep.add('APPROX', '%s: template move has no direct hit -> default hit object (Kou ボディブロー)' % name_ja)
                # R 2026-11-12 (HITREPEAT, user 「TKO 偶数ヒット目でカス当たり」): the template hit is taken by order, so a
                # BFE hit that repeats an earlier one (T・K・O: left / right jab, same 攻撃情報 except コンボ補正 1 / 2 and のけぞり
                # 打ち上げ +2 / -2) got the template's next hit (甲 T.K.O hit 2: no hit effect / SE, 溜め反映 0, 装甲攻撃 0,
                # hitback 1000). A repeat of the same BFE hit (攻撃情報 apart from コンボ補正; のけぞり not compared) re-uses
                # the template hit of its first occurrence. The BFE values themselves are still set per hit by _set_hit.
                key_ = repr(sorted((k_, v_) for k_, v_ in hi.items() if k_ != 'combo_corr'))
                idx_ = min(hit_no, len(tpl_hits[41]) - 1)
                if key_ in hit_tpl_of and hit_tpl_of[key_] != idx_:
                    rep.add('HITREPEAT', '%s turn %d: same BFE hit as an earlier turn -> template hit %d (not %d)' % (
                        name_ja, ti_, hit_tpl_of[key_], idx_))
                    idx_ = hit_tpl_of[key_]
                hit_tpl_of.setdefault(key_, idx_)
                tp = copy.deepcopy(tpl_hits[41][idx_])
                hit_no += 1
                self._rep_ti = bs.get('index') if bullet else None      # G REPDECAY (local: bullets convert nested)
                self._set_hit(tp, hi, ph['noke_mech'], hs, he, hits, cancel=hc_ and not nodmg_, bfe_iv=True)   # HITCANCEL (local: bullets convert nested); HITIV
                md_ = ph['move_dir']; nkm_ = ph['noke_mech']
                if bullet and nkm_['direction'] == 2 and md_['type'] == 0 and md_['init'][0] != -32768 and \
                        md_['init'][1] - md_['init'][0] >= 359 and nkm_['speed_init']:
                    # E 2026-11-05 (NOKERANDDIR, user 11/05 「キャノンブレイカー: 敵が真上に飛ぶはずが、斜め前に飛ぶ」): BFE
                    # のけぞり方向 2 「自分の移動方向」 = the hitter's direction angle +0x51c (0x441fb0, jump table 0x4421f8
                    # case 2 -> 0x44201b), whatever its speed. 雷神魔破拳用 (ｷｬﾉﾝﾌﾞﾚｲｶｰ ph4 x10) has 方向 初期値 0..359 (a random
                    # angle per bullet) and speed 0 -> each hit pushes 16 px/tick in a random direction, the 10 hits cancel
                    # out and the enemy goes up with the launch. The 甲 template's 角度指定→スプライト方向(0, 0) pushed every
                    # hit forward. -> the same Term with (0, ±180) (full circle only).
                    r_ = (md_['init'][1] - md_['init'][0] + 1) // 2
                    n_ = 0
                    for u_ in tp['ceventHitUnitList']:
                        if u_['unitSlotNum'] in (17, 18, 19, 20) and u_.get('data'):
                            # R 2026-11-05 (user: still diagonal with the random ±180): the 10 random pushes cancel out
                            # in BFE -> no horizontal push at all (int8 / int9 0), the launch alone remains.
                            u_['data']['int8'] = 0; u_['data']['int9'] = 0
                            for x_ in u_['data'].get('ceventNokezoriUnitList') or []:
                                if x_['unitSlotNum'] == 8 and x_.get('data') and x_['data'].get('bsdxInfoCollectionList'):
                                    b_ = x_['data']['bsdxInfoCollectionList'][0]
                                    if b_['typeList'] == [3, 0] and len(b_['paramList']) == 2:
                                        b_['paramList'] = [0, int(min(180, r_))]   # full circle: the centre does not matter
                                        n_ += 1
                    if n_:
                        rep.add('NOKERANDDIR', '%s ph%d: bullet のけぞり方向 2 移動方向, BFE 方向 初期値 %d..%d (random) -> 角度指定→スプライト方向(0, ±%d) x%d' % (
                            name_ja, pi, md_['init'][0], md_['init'][1], min(180, r_), n_))
                if nodmg_:
                    self._nodmg_hit(tp, hi, pi)
                self._se_voice(tp, hi, hits, name_ja, ti_)
                nk_ = ph['noke_mech']; sp_ = ph['speed']
                if bullet and not nodmg_ and nk_['flags'] & 1 and nk_['direction'] == 2 and hits != 1 and sp_['init'][0] != -32768:
                    # R 2026-11-04 (NOKEPARENT, user 20261103_4 #5 「弾が小さい状態のとき、敵と一緒に弾が移動するはずが、その
                    # 量が小さい」): BFE のけぞり flag bit0 「親速度>のけぞり速度」 starts the victim at the hitting object's own
                    # speed + 速度 初期値 (0x441fb0: [obj+0x64]+0x520 + noke +6, <<8 -> 0x448870), along its move direction
                    # (方向 2, +0x51c). ﾌｫﾄﾝﾌﾞﾗｽﾀｰ ph0: the ball slows 32 -> 2 px/tick (増分 512) and re-hits every 3 ticks,
                    # so the enemy rides along with it. The converter gave 2/2 = 1 px/F. -> the hit window is cut where the
                    # BFE ball speed changes; each piece gets のけぞり速度 (ball + 初期値)/2 px/F and the ball's deceleration.
                    # R 2026-11-15 (NOKEPARENTDECEL, user 「弾が小さい状態のとき、相手を過剰に吹き飛ばしてしまって、攻撃が繋がり
                    # づらい。弾の進行速度と同じくらいの吹き飛びが望ましい」): the victim slows by its own のけぞり 増分 (BFE
                    # 0x441fb0: noke +0xa -> the victim's speed step; ﾌｫﾄﾝﾌﾞﾗｽﾀｰ ph0 1024 = 4 px/tick per tick = 1 px/F per F),
                    # not by the ball's 増分 (512 = 0.5 px/F per F). With the ball's step the enemy kept ball + 1 px/F, slid out
                    # ahead of the small ball, was no longer re-hit and coasted twice as far. With its own step it falls back
                    # to the ball between re-hits (6F: enemy 17 -> 11, ball 16 -> 13) and is carried at the ball's speed, as
                    # BFE (re-hit every 3 ticks resets it to ball + 初期値). -> int9 = noke 増分 x100/1024 for every piece.
                    mid_ = lambda r: (r[0] + r[1]) / 2.0
                    v_, vt_ = mid_(sp_['init']), mid_(sp_['final']); st_ = sp_['step'][0] / 256.0 if sp_['step'][0] > 0 else 1e9
                    vb_ = []
                    for t_ in range(L // 2 + 2):
                        vb_.append(v_)
                        v_ = max(vt_, v_ - st_) if v_ > vt_ else min(vt_, v_ + st_)
                    pieces_ = []
                    for f_ in range(tp['startFrame'], tp['endFrame'] + 1):
                        tk_ = f_ // 2
                        k8_ = int(round((vb_[tk_] + nk_['speed_init']) / 2.0))
                        k9_ = int(round(max(0, nk_['speed_step']) * 100 / 1024.0))
                        if pieces_ and pieces_[-1][2:] == [k8_, k9_]:
                            pieces_[-1][1] = f_
                        else:
                            pieces_.append([f_, f_, k8_, k9_])
                    # merge pieces shorter than the hit interval into the next one (one re-hit per piece at least)
                    iv_ = max(2, tp.get('hitInterval') or 2)
                    mg_ = []
                    for pc_ in pieces_:
                        if mg_ and mg_[-1][1] - mg_[-1][0] + 1 < iv_:
                            mg_[-1][1] = pc_[1]; mg_[-1][2:] = pc_[2:] if mg_[-1][2] < pc_[2] else mg_[-1][2:]
                        else:
                            mg_.append(list(pc_))
                    for a_, b_, k8_, k9_ in mg_:
                        o_ = copy.deepcopy(tp); o_['startFrame'], o_['endFrame'] = a_, b_
                        for u_ in o_['ceventHitUnitList']:
                            if u_['unitSlotNum'] in (17, 18, 19, 20) and u_.get('data'):
                                u_['data']['int8'] = max(u_['data'].get('int8') or 0, k8_); u_['data']['int9'] = k9_
                        ev[41].append(o_)
                    rep.add('NOKEPARENT', 'bullet のけぞり 親速度>のけぞり速度 (BFE flag 0x01, 方向 2): ball %s -> %s px/tick -> %d hit pieces, のけぞり速度 %s px/F' % (
                        sp_['init'][0], sp_['final'][0], len(mg_), '/'.join(str(m_[2]) for m_ in mg_)))
                else:
                    gh_ = ph['go_hit_mech']
                    nj_ = pi + 1 if gh_ == -1 else gh_
                    if bullet and not nodmg_ and 0 <= nj_ < nph and nj_ != pi and nk_['noke_count'] > 0 and \
                            not (nk_['launch_accum'] >= 100 and nk_['launch'] > 0):
                        nh_ = phases[nj_]['noke_mech']
                        if nh_['launch_accum'] >= 100 and nh_['launch'] > 0:
                            # E 2026-11-15 (NOKECHAIN, user 「DDの1ヒット目で敵がのけぞるはずが、のけ反っていない。そのため後段の
                            # 爆風で吹き飛ばなくなっている」): a bullet hit that turns the bullet into a launching blast (BFE
                            # go_hit_mech -> a phase with 打ち上げ; DDﾐｻｲﾙ ph0 -> ph2) had the default template's ﾋｯﾄﾊﾞｯｸ 0 for a
                            # fresh victim: no hitstun, and DiveX applies a launch only to a victim in hitstun (0x619230 /
                            # 0x61914a). BFE のけぞり回数 100; vanilla DDミサイル：甲Lv3 T0 100/200. -> ﾋｯﾄﾊﾞｯｸ 0 -> 2 x のけぞり回数 F.
                            for u_ in tp['ceventHitUnitList']:
                                if u_['unitSlotNum'] in (17, 18, 19, 20) and u_.get('data') and not u_['data'].get('int3'):
                                    u_['data']['int3'] = 2 * nk_['noke_count']
                                    u_['data']['int4'] = max(u_['data'].get('int4') or 0, 2 * nk_['noke_count'])
                            rep.add('NOKECHAIN', '%s ph%d: hit -> ph%d (打ち上げ %d): ﾋｯﾄﾊﾞｯｸ 0 -> %dF (BFE のけぞり回数 %d, vanilla DDミサイル：甲)' % (
                                name_ja, pi, nj_, nh_['launch'], 2 * nk_['noke_count'], nk_['noke_count']))
                    ev[41].append(tp)
            hw = hi['hits_weapon']
            if bullet and hw not in (0, 254) and tpl_hits[42] and hi['power'] > 0:
                tp = copy.deepcopy(tpl_hits[42][0])
                hs, he = hit_window or ((atk[0][0], max(b for a_, b in atk)) if atk else (0, L - 1))
                self._set_hit(tp, hi, ph['noke_shot'], hs, he, hw, weapon=True, cancel=False, bfe_iv=True)
                ev[42].append(tp)
            # ---- projectile
            fire = ph['fire']
            if fire['tama'] >= 0 and fire_at is None:
                # BFE fires only from a sprite event whose flags have bit 3 弾発射 (0x4437e7 -> fire table 0x4d92a0).
                # ﾗｲﾝﾚｰｻﾞｰ ph0 carries a Lv1 root that is never fired; the old rule (fire at frame 0 anyway) added a second,
                # earlier laser ('hit starts earlier than the original', reported)
                rep.add('NOFIRE', '%s ph%d: Tama %d has no 弾発射 event -> not fired' % (name_ja, pi, fire['tama']))
            if fire['tama'] >= 0 and fire_at is not None:
                at = fire_at
                laser = self.fx and (fire['fire_type'] != 0 or self.fx.chain_has_laser(fire['tama']))
                if laser and bullet and fire['fire_type'] != 0:
                    rep.add('APPROX', 'laser/wire segment Tama %d (fire_type %d) fired by a bullet without a laser root: plain bullet'
                            % (fire['tama'], fire['fire_type']))
                    laser = False
                if not bullet and mech_tip is not None and fire['tama'] == mech_tip:
                    rep.add('LINE', '%s ph%d: wire tip Tama %d is spawned by the line chain (BSDX 先端), not by the mech' % (name_ja, pi, mech_tip))
                elif laser:
                    if bullet:
                        proj = self.fx.bullet_laser_proj
                    else:
                        proj = next((p for p in tpl_proj if effect_target(p)[0] == self.fx.LF), None)
                    life = None
                    if not bullet and fire_ev_end is not None and fire_ev_end < L and \
                            any(p_['go_mech_spr'] != -99 for p_ in self.fx.tama[fire['tama']]['phases']):
                        life = fire_ev_end - at          # root ends with the firing sprite event (go_mech_spr)
                    tgt = self.fx.line_chain(name_ja, fire['tama'], proj, mech_tip, life) if proj else None
                    if tgt:
                        o = self.spawn(None, tgt, at, L, proj=proj); ev[48].append(o)
                        self.fx.lines.set_pierce(o, tgt)    # L 2026-10-30 PIERCE (bfe2bsdx_line._pierce_hdr)
                    else:
                        rep.add('DROPPED', '%s ph%d: laser Tama %d (no template line chain)' % (name_ja, pi, fire['tama']))
                else:
                    tgt = self.fx.tama_target(fire['tama']) if self.fx else None
                    if tgt:
                        if bullet:
                            proj = self.fx.spawn_sample('bullet')
                        else:
                            proj = tpl_proj[0] if tpl_proj else fallback_proj
                            if not tpl_proj:
                                rep.add('APPROX', '%s: spawn event cloned from the fallback projectile (template has none)' % name_ja)
                        # G 2026-11-03 (FIREIV): shot k at at + 2 x bfe_fire_offsets (BFE (T+1) ticks per shot, 0x44a1c0 /
                        # 0x4a7db0; was 2 x 間隔 F = one tick short), as many as fit in the phase (BFE keeps firing while
                        # the phase runs), at most MAXSPAWN.
                        offs_ = [at + 2 * o_ for o_ in bfe_fire_offsets(fire, min(MAXSPAWN, max(1, fire['loops'])))]
                        nsp = max(1, sum(1 for o_ in offs_ if o_ <= L - 1))
                        if fire['interval'][0] != 0 or (fire['interval'][2] if len(fire['interval']) > 2 else 0):
                            rep.add('FIREIV', '%s ph%d: BFE 間隔 %s -> shots at F%s (old gap %dF)' % (
                                name_ja, pi, fire['interval'], ','.join(str(o_) for o_ in offs_[:nsp][:6]) + (',..' if nsp > 6 else ''),
                                max(2, fire['interval'][0] * 2)))
                        a0, a1, astep = fire['angle_corr']
                        cnt = max(1, fire['count'][0])
                        sweep = astep != 0 and a1 != a0
                        if sweep:
                            # 角度補正 {init, final, step}: each shot advances by step/256 deg inside [init, final]
                            # (ﾘｻｰﾁﾐｻｲﾙ -30/+30 step 60 = alternating fan, 吸着ﾏｲﾝ 0..359 step 22.5 x16 = ring). The old rule
                            # gave every shot the init angle (ﾘｻｰﾁﾐｻｲﾙ all at -30: 'diagonal, clustered', reported).
                            # A multi-shot event becomes one spawn per shot (count 1) with its own angle.
                            rep.add('SWEEP', '%s ph%d: fire angle %d..%d step %.1f x %d (%s, %s)' % (
                                name_ja, pi, a0, a1, astep / 256.0, cnt, 'per shot' if fire['flags2'] & 1 else 'per volley',
                                'ping-pong' if fire['flags2'] & 4 else 'clamp'))
                        # exact BFE advance (BaldrForce.exe 0x449bc0, state set at 0x44a360): angle = acc>>8, acc += step after
                        # each shot (flags2 bit0 「1発単位で更新」) or after each volley (bit0 off); reaching 最終 clamps
                        # there, and with flags2 bit2 「角度補正往復ﾙｰﾌﾟ」 init/final swap and the step reverses (ping-pong).
                        # The old modulo wrap went past 最終 (火炎放射器 -30..+42 sawtooth instead of -30..30..-30).
                        sw = {'acc': a0 << 8, 'ini': a0, 'fin': a1, 'stp': astep}
                        def sweep_adv(sw=sw, pp=bool(fire['flags2'] & 4)):
                            sw['acc'] += sw['stp']; a_ = sw['acc'] >> 8
                            if (sw['stp'] > 0 and a_ >= sw['fin']) or (sw['stp'] < 0 and a_ <= sw['fin']):
                                sw['acc'] = sw['fin'] << 8
                                if pp:
                                    sw['ini'], sw['fin'], sw['stp'] = sw['fin'], sw['ini'], -sw['stp']
                        per_shot = bool(fire['flags2'] & 1)
                        for k in range(nsp):
                            for c_ in (range(cnt) if sweep else (0,)):
                                o = self.spawn(None, tgt, offs_[k], L, proj=proj)
                                ang = None
                                if sweep:
                                    ang = sw['acc'] >> 8
                                    if per_shot:
                                        sweep_adv()
                                self._set_fire(o, fire, self.fx.tama_speed(fire['tama']), angle=ang, count=1 if sweep else None)
                                # R 2026-11-20 (POSCORR0, 作者「エクスカリバーの一発目が少し離れた位置に出て綺麗につながらない」, 原作
                                # BFE_Original/フォースクラッシュ.mp4 0:38 vs 移植 11/21 動画): BFE 位置補正 0 = the bullet starts on the fire
                                # point (透's hand, SPR 14). The 甲 template spawn kept its own 発射位置補正：距離 (sub 10: 甲 エクスカリバー
                                # 100, ケイジブレイド 50, Ｅ・フィンガー 20) -> the swords stood that far ahead of the hand (video: 1st sword
                                # ~150 px ahead of 透, 2nd sword +130 px from the 1st = BFE spacing). Melee (技タイプ 打撃) spawns placed on
                                # 透 only (not the ロック座標 spawns that LOCKTARGET below moves onto the enemy); the guns keep the
                                # template muzzle offset (10 px).
                                if not bullet and kind == 0 and fire['pos_corr'][0] == 0 and fire['origin']['type1'] not in (4, 5, 6):
                                    d10_ = effect_sub(o, 10); d7_ = effect_sub(o, 7)
                                    b7_ = ((d7_ or {}).get('bsdxInfoCollectionList') or [None])[0]
                                    if d10_ is not None and (d10_.get('int2') or d10_.get('int5')) and b7_ and \
                                            b7_['typeList'] == [1] and b7_['intList3'][:1] == [0]:
                                        rep.add('POSCORR0', '%s ph%d -> Tama %d: BFE 位置補正 0 -> template spawn sub 10 発射位置補正：距離 %d/%d -> 0' % (
                                            name_ja, pi, fire['tama'], d10_.get('int2', 0), d10_.get('int5', 0)))
                                        d10_['int2'] = d10_['int5'] = 0
                                if not bullet and any(e_['flags'] & 0x0c == 0x0c for e_ in ph['events']):
                                    # R 2026-11-15 (FIRELOCK): BFE sprite event 「弾発射位置ﾛｯｸ」+「弾発射」 (BaldrForce.exe
                                    # 0x4437a8: the fire position is computed once at the event start, 0x4406c0 / 0x440a50).
                                    # Marker for the build's FIRELOCK pass (needs the final sprite pages); popped there.
                                    o['_firelock'] = True
                                og_ = fire['origin']
                                if og_['type1'] in (4, 5, 6) and ph['lock%d' % (og_['type1'] - 3)]['type1'] == 0:
                                    # E 2026-11-04 (LOCKTARGET, user 20261103_4 #9 「キャノンブレイカーの打撃が発生しない」): BFE
                                    # 発射位置 = ロック座標 1-3 whose 標的ﾀｲﾌﾟ is 0 「判定」: the coordinate of the object the
                                    # technique hit (原作 orig9.mp4: the 10 雷神魔破拳用 blasts burst on the enemy after 透 has
                                    # dashed ~300 px away). The spawn kept the fallback's 「オブジェクト位置指定 自分」 -> the blasts
                                    # went off at 透 and hit nothing (9.mp4). -> spawn sub 7 = オブジェクト位置指定 標的
                                    # (intList3 [1,0], vanilla サテライトレーザーLv1). Exact BFE lock semantics not traced.
                                    d7_ = effect_sub(o, 7)
                                    if d7_ is not None and d7_.get('bsdxInfoCollectionList'):
                                        b7_ = d7_['bsdxInfoCollectionList'][0]
                                        if b7_['typeList'] == [1] and b7_['intList3'] != [1, 0]:
                                            b7_['intList3'] = [1, 0]
                                            rep.add('LOCKTARGET', '%s ph%d: 発射位置 ロック座標%d (標的ﾀｲﾌﾟ 判定) -> spawn sub 7 オブジェクト位置指定 標的 (vanilla サテライトレーザー)' % (
                                                name_ja, pi, og_['type1'] - 3))
                                # R 2026-11-15 (STICKTARGET, user 「スプレッドパンチは発生まで自機の拳に追従、スタンロッドは敵の位置に
                                # 追従、グラビティフィールドは自機の身体の中心から発生」): BFE 移動方向 5 puts the bullet on its ﾛｯｸ座標1
                                # every tick (BaldrForce.exe 0x4467d0: 0x4406c0 resolves the target object, 0x440a50 its
                                # point). The 標的ﾀｲﾌﾟ table (0x440a04) is 0 = the target it already has (for a fired bullet:
                                # the shooter), 1 = itself, 2 = parent, 3/4/5 = the object of ﾛｯｸ座標 1/2/3. With type 0 and
                                # 判定 処理タイプ 1 the point is the shooter's active attack rect of the current sprite event
                                # (ｽﾌﾟﾚｯﾄﾞﾊﾟﾝﾁ: the fist), and the body centre when that event has no attack rect
                                # (ｸﾞﾗﾋﾞﾃｨﾌｨｰﾙﾄﾞ anim 366: 攻撃判定 0). Types 3-5 with a 標的 spawn = the enemy (感電).
                                # DiveX: the follow bullet (slot 11 前指定を維持) re-reads spawn sub 25 -> sub 7 / 25 = 自分 NONE
                                # for the centre case, sub 25 = 標的 for the enemy case; the fist case keeps FIRERECT1.
                                tb_ = self.fx.tama[fire['tama']]['phases'][0] if not bullet and 0 <= fire['tama'] < len(self.fx.tama) else None
                                if tb_ is not None and tb_['move_dir']['type'] == 5:
                                    l1_ = tb_['lock1']
                                    d7_ = effect_sub(o, 7); d25_ = effect_sub(o, 25)
                                    b7_ = d7_['bsdxInfoCollectionList'][0] if d7_ and d7_.get('bsdxInfoCollectionList') else None
                                    b25_ = d25_['bsdxInfoCollectionList'][0] if d25_ and d25_.get('bsdxInfoCollectionList') else None
                                    fev_ = [e_ for e_ in ph['events'] if e_['flags'] & 8]
                                    if b7_ and b25_ and l1_['type1'] == 0 and l1_['judge'][0] == 1 and fev_ and                                             not any(e_['attack_rects'] for e_ in fev_) and b25_['typeList'] == [1] and b25_['intList3'][:1] == [0]:
                                        if b7_['typeList'] == [1] and b7_['intList3'][:1] == [0]:
                                            b7_['intList3'] = [0, 0]
                                        b25_['intList3'] = [0, 0]
                                        rep.add('STICKTARGET', '%s ph%d -> Tama %d: ﾛｯｸ座標1 = shooter, no attack rect on the firing event -> spawn sub 7 / 25 自分 NONE (body centre)' % (
                                            name_ja, pi, fire['tama']))
                                    elif b7_ and b25_ and l1_['type1'] in (3, 4, 5) and b7_['typeList'] == [1] and b7_['intList3'] == [1, 0] and                                             b25_['typeList'] == [1] and b25_['intList3'] != [1, 0]:
                                        b25_['intList3'] = [1, 0]
                                        rep.add('STICKTARGET', '%s ph%d -> Tama %d: ﾛｯｸ座標1 type %d (lock object), spawned at 標的 -> spawn sub 25 標的 (follows the enemy)' % (
                                            name_ja, pi, fire['tama'], l1_['type1']))
                                ev[48].append(o)
                            if sweep and not per_shot:
                                sweep_adv()
                        if getattr(self, 'firedir_added', False):
                            self.firedir_added = False
                            rep.add('FIREDIR', 'fire spawn without ﾍﾞｸﾄﾙ：方向 -> sub 28 角度指定→スプライト方向(0,0) (vanilla 甲 ハンドガン / 炸裂弾)')
                        if fire['loops'] > MAXSPAWN and nsp == MAXSPAWN:
                            rep.add('APPROX', '%s: BFE fire loops %d -> %d spawn events (cap)' % (name_ja, fire['loops'], MAXSPAWN))
                        self.effect_spawn(fire['muzzle_effect'], at, L, ev, 'muzzle')
                    else:
                        rep.add('DROPPED', '%s ph%d: projectile Tama %d not ported' % (name_ja, pi, fire['tama']))
                se = self.se.get(fire['se'])
                if se:
                    ev[52].append(self.se_obj(se, at))
            if not bullet:
                # HITCANCEL (調査記録 20): BFE mech phase entry (0x443d2d-0x443d41): flags bit6 空ｷｬﾝｾﾙ -> flag 1, else bit7
                # ｷｬﾝｾﾙﾌﾗｸﾞ初期化 -> 0; a 射撃 skill sets 1 when it fires (0x44a81b) -> slot 47 at F0 / the fire frame (vanilla
                # 甲 射撃: slot 47 (0 -> 1) on the fire frame, ハンドガンLv3 T1 F4; エネルギーフィールド T1 F0). Turn 0 needs no 0:
                # DiveX clears [+0x1900] when a skill starts (0x61cafe; every TOORU phase 0 has bit7).
                fired_ = fire['tama'] >= 0 and fire_at is not None
                c47 = {}
                if ph['flags'] & 0x40:
                    c47[0] = 1
                elif ph['flags'] & 0x80 and ti_ > 0:
                    c47[0] = 0
                if kind == 1 and fired_:
                    c47[min(fire_at, L - 1)] = 1
                for f_, v_ in sorted(c47.items()):
                    o = lib.obj(47, 0, f_, f_, int1=0, int2=0, int3=0, int4=v_); o['_c47'] = True
                    ev[47].append(o)
                    rep.add('HITCANCEL', '%s ph%d: slot 47 F%d = %d (%s)' % (name_ja, pi, f_, v_, 'fire, 射撃' if (kind == 1 and fired_ and f_ == min(fire_at, L - 1))
                                                                            else 'phase flags %02x %s' % (ph['flags'], '空ｷｬﾝｾﾙ' if v_ else 'ｷｬﾝｾﾙﾌﾗｸﾞ初期化')))
            bl_ = ph.get('blink') or {}
            if not bullet and bl_.get('type') in (1, 2) and (49, 20) in lib.ev:
                # E 2026-11-06 (BLINK, user 11/06 「原作は自機に残像が出る（ｷｬﾉﾝﾌﾞﾚｲｶｰ）。甲の FC（ﾒｶﾞﾌﾞｰｽﾄｷｯｸ）にも残像がある」):
                # BFE 計算（残像） dlg186 type 1 ノーマル残像 / 2 色残像, 初期値 -> 最終値 0 at 増分 per tick (the image
                # fades: ﾌﾞｰｽﾄｷｯｸ 24 at 6, ｷｬﾉﾝﾌﾞﾚｲｶｰ color 0x1818/32 at 4). -> slot 49 残像 (CEventBlink int2 発生間隔,
                # int3 表示時間; vanilla 甲 ﾒｶﾞﾌﾞｰｽﾄｷｯｸ 3/40) for the whole phase: one image per BFE tick (2F), shown for
                # the fade time max(init)/step ticks x2 F. 色残像 is drawn as a normal one (DiveX int1 color mode unknown).
                vals_ = [v_ & 0xff for v_ in bl_['init'] if v_ > 0] + [v_ >> 8 for v_ in bl_['init'] if v_ > 255]
                st_ = max(1, abs(bl_['step'][0]))
                life_ = max(4, int(math.ceil(max(vals_ or [24]) / float(st_))) * 2)
                ev[49].append(lib.obj(49, 20, 0, L - 1, int1=0, int2=2, int3=life_))
                rep.add('BLINK', '%s ph%d: BFE 残像 type %d init %s step %d -> slot 49 残像 every 2F, %dF' % (
                    name_ja, pi, bl_['type'], bl_['init'], bl_['step'][0], life_))
            if stick_z is not None:
                ev[19] = [lib.obj(19, 3, 0, L - 1, int1=0, int2=stick_z, int4=0, int5=stick_z)]; ev[21] = [lib.obj(21, 2, 0, 0, int5=0)]
                rep.add('STICKZ', 'bullet move_dir 5: height %d above the parent -> slot 19 held, 重力 0' % stick_z)
            if bullet and ph['flags'] & 2 and self.fx and hasattr(self.fx, 'SH'):
                # E/V 2026-11-07 (MISSILEFX, user ホーミングミサイル.mp4 / 多弾頭ミサイルポッド.mp4 vs 原作 通常武装 1:55 / 2:05: 炎と煙が無い):
                # BFE ﾌｪｰｽﾞ flag bit1 「ﾐｻｲﾙ炎＆煙」 (0x443ec7) spawns effect 23 (anim 111, the flame) + effect 4 (procedural
                # white trail, no Effect.spr anim) and renews them while the phase runs; it was not converted at all.
                # Trail: vanilla missile idiom Laser[67] 煙（ライン親） (ホーミングミサイル：甲 T0 F0), once per run of flagged
                # phases. Flame: effect 23 every 4F (DiveX effects do not follow the bullet).
                if not (ti_ > 0 and phases[turn_phase[ti_ - 1]]['flags'] & 2):
                    for e_ in next(u_ for u_ in self.fx.SH[2]['skillList'][1]['phasesInfo'][0]['skillUnitCollection'] if u_['unitQuantity'] == 48)['skillInfoObjectList']:
                        d3_ = effect_sub(e_, 3)
                        if d3_ is not None and d3_.get('wazFileNo') == 6 and d3_.get('wazSequenceNo') == 67:
                            o_ = copy.deepcopy(e_); o_['startFrame'] = o_['endFrame'] = 0; o_['offset'] = 0
                            for d_ in walk(o_):
                                if 'offset' in d_:
                                    d_['offset'] = 0
                            ev[48].append(o_)
                for f_ in range(0, L, 4):
                    self.effect_spawn({'effect_no': 23}, f_, L, ev, 'missile flame')
                rep.add('MISSILEFX', '%s ph%d: ﾐｻｲﾙ炎＆煙 -> Laser[67] 煙 + effect 23 every 4F' % (name_ja, pi))
            self.effect_spawn(ph['effect_always'], 0, L, ev, 'always',
                              at_target=(not bullet and ph['effect_always']['rect_slot'] >= 0 and ph['hit']['power'] > 0
                                         and ph['hit']['hits_mech'] not in (0, 254)), name_ja='%s ph%d' % (name_ja, pi))
            if ph['effect_land']['effect_no'] >= 0:
                rep.add('IGNORED', 'effect_land (着地エフェクト) %d' % ph['effect_land']['effect_no'])
            # ---- transitions
            ch = []
            def dest(v):
                if v == 99:
                    return 'end'
                if v == -1:
                    return nxt.get(ti_, 'end')
                return v if 0 <= v < nph else None
            if ph['go_air'] not in (-99,) and dest(ph['go_air']) is not None and dest(ph['go_air']) != ti_:
                air_dispatch.append((ti_, dest(ph['go_air'])))
                rep.add('AIR', '%s ph%d: 空中時 -> %s' % (name_ja, pi, dest(ph['go_air'])))
            gh = ph['go_hit_mech']
            if hit_window and gh != -99 and dest(gh) is not None:
                if not bullet and dest(gh) == 'end':
                    # M 2026-10-31 (POSTAPEX; replaces the 10-30 FREEFALL fall turns, user 10/29: no frames the BFE
                    # skill does not have): BFE ends the skill at the hit and the free mech rises on from its state at
                    # the hit tick -> one 「hit -> end」 change, marked with the BFE states of the turn; the post-skill
                    # gravity per exit frame is set after the dispatch clones (_post_apex).
                    o = lib.change([('オブジェクト→攻撃→残りメカＨＩＴ数→□なら(0)', [0])], 'end', hit_window[0], L - 1)
                    o['_apex'] = {'why': 'hit', 'moving': moving, 'h0': vh0, 'vtr': vtr}
                    ch.append(o)
                else:
                    ch.append(lib.change([('オブジェクト→攻撃→残りメカＨＩＴ数→□なら(0)', [0])], dest(gh), hit_window[0], L - 1))
            if bullet and ph['go_dist_out'] != -99 and dest(ph['go_dist_out']) is not None and ph['p_dist_out'] > 0:
                # R 2026-11-07 (DISTOUT, user ガトリングビット 「徐々に敵から離れて射撃が届かない」): ﾋﾞｯﾄ ph1 orbits tangentially and BFE
                # returns to the approach phase beyond 距離 300 (go_dist_out); it was dropped. Same term as 距離→□以下 with
                # the compare 3 = 以上 (typeList tail, as 技カウンタ→□以上なら; vanilla (2,3,6,3)).
                o_ = lib.change([('オブジェクト→パラメータ→距離→□以下なら(0)', [ph['p_dist_out']])], dest(ph['go_dist_out']), 1, L - 1)
                o_['bsdxInfoCollectionList1'][0]['typeList'][3] = 3
                ch.append(o_)
                rep.add('DISTOUT', '%s ph%d: BFE 距離 %d 以上 -> %s' % (name_ja, pi, ph['p_dist_out'], dest(ph['go_dist_out'])))
            if bullet:
                for k, cond in (('go_hit_weapon', ('オブジェクト→攻撃→残り弾ＨＩＴ数→□なら(0)', [0])),
                                ('go_obstacle', ('オブジェクト→接触→マップOBJ＋進禁に接触していたら(0)', [18])),   # WALLHIT: 2 -> 18 (vanilla missiles)
                                ('go_origin_null', ('オブジェクト→オブジェクト→NULLなら', [], 2)),
                                ('go_dist_in', ('オブジェクト→パラメータ→距離→□以下なら(0)', [max(1, ph['p_dist_in'])])),
                                ('go_mech_alg', ('オブジェクト→変化→親状態：ターン', [])),
                                # R 2026-11-06 (MECHSPR, user EF.mp4 11/06 「大きなヒットが原作 3 回、移植版 4 回」): BFE
                                # go_mech_spr = the parent's sprite (anim) changed. ｴﾈﾙｷﾞｰﾌｨｰﾙﾄﾞ ph0 ends when 透 goes from
                                # anim 250 (20 ticks) to 251 inside the same phase; 親状態：ターン waited for the turn end
                                # (54F -> 4 hits at 14F). DiveX 親状態：グループ = the parent's sprite group changed (vanilla
                                # laser roots 甲レーザー（根元） etc., 47 uses) -> 310 -> 311 at F42 -> 3 hits.
                                ('go_mech_spr', ('オブジェクト→変化→親状態：グループ', [])),
                                ('go_mech_skill', ('オブジェクト→変化→親状態：技', [])),
                                ('go_counter', ('オブジェクト→汎用→技カウンタ→□以上なら(0)', [max(1, h['action_counter']) * 2]))):
                    v = ph[k]
                    if v != -99 and dest(v) is not None:
                        if k == 'go_hit_weapon' and not ev[42]:
                            continue
                        if k == 'go_counter':
                            if not (0 < h['action_counter'] < 9999):
                                continue
                            rep.add('APPROX', 'go_counter (総合ｶｳﾝﾀ到達) -> 技カウンタ >= action_counter x2 [guess: counter = ticks]')
                        ch.append(lib.change([cond], dest(v), 1 if k in ('go_origin_null', 'go_mech_alg', 'go_mech_spr', 'go_mech_skill') else 0, L - 1))
                        if k == 'go_obstacle':
                            # WALLHIT: vanilla 甲 missiles end on 弾終了チェック（＋障害物接触）(18) = contact OR overlap with the
                            # map (0x66b1a2); the HP / remaining-HIT parts stay separate BFE transitions -> a second change
                            # on the overlap (ハンドガン：しずか：爆裂 / ライフル：甲 use this term), both with mask 18.
                            ch.append(lib.change([('オブジェクト→接触→マップOBJ+進禁に重なっていたら(0)', [18])], dest(v), 0, L - 1))
                            # R 2026-11-19 (WALLLAND, 作者動画 11/19 20:56 「ホーミングは壁をすり抜けないが、爆発せずぬるっと滑り
                            # ながら進み続ける」): the missiles hit the top of the black block and slid along it = DiveX floor
                            # (着地), which sets neither the 進禁 flags nor the OBJ contact list. BFE has one map obstacle test
                            # for walls and floor (go_obstacle), so a phase without its own landing transition (go_land /
                            # anim_type 3) also takes 着地していたら to the same phase (vanilla ハンドガン：甲 pairs 弾終了チェック
                            # （＋障害物接触）(18) with 着地していたら). From F1 so a bullet spawned on the floor is not ended at once.
                            if ph['go_land'] == -99 and land_from is None:
                                ch.append(lib.change([('オブジェクト→接触→着地していたら', [])], dest(v), min(1, L - 1), L - 1))
                                rep.add('WALLLAND', '%s ph%d: go_obstacle -> also 着地していたら -> %s' % (name_ja, pi, dest(v)))
            elif ph['go_dist_in'] != -99 and dest(ph['go_dist_in']) is not None and ph['p_dist_in'] > 0:
                # V 2026-11-05 (MECHDIST, user 11/05 「マインナックル: 敵に近づいたらすぐ攻撃に移るはずが、前進モーションが
                # 終わりまで出ている」): BFE 距離内 on a mech phase (ﾏｲﾝﾅｯｸﾙ ph0: 距離 50 -> next, the lunge) was dropped for
                # mechs. Vanilla mechs use the same condition on self (甲 青龍刀 / スウェーバックナイフ / キリングレイジ
                # 「距離→□以下なら(N) -> ターンジャンプ→１つ先」 over the approach frames, 15 uses).
                ch.append(lib.change([('オブジェクト→パラメータ→距離→□以下なら(0)', [ph['p_dist_in']])], dest(ph['go_dist_in']), 1, L - 1))
                rep.add('MECHDIST', '%s ph%d: BFE 距離 %d 以内 -> %s (vanilla 甲 青龍刀 idiom, F1..)' % (name_ja, pi, ph['p_dist_in'], dest(ph['go_dist_in'])))
            gl = ph['go_hits_le_mech']
            miss_target = None
            if gl != -99 and dest(gl) is not None:
                miss_target = dest(gl)
            gland = ph['go_land']
            if land_from is not None or gland != -99:
                tgt = dest(gland) if gland != -99 else nxt.get(ti_, 'end')
                if bullet and gland == -99 and land_from is not None and ph['go_anim_end'] != -99 and dest(ph['go_anim_end']) is not None:
                    # R 2026-11-16 (LANDANIMEND, 調査記録 68): an anim_type 3 (着地まで) bullet animation ends at the landing, so
                    # BFE goes to 絵の終わり go_anim_end there, not to the next phase (ｻﾃﾗｲﾄﾚｰｻﾞｰ ph0: a missed beam lands ->
                    # ph2 爆発; the port went through the 30-hit pierce phase first).
                    if dest(ph['go_anim_end']) != tgt:
                        rep.add('LANDANIMEND', '%s ph%d: 着地まで の絵の終わり -> go_anim_end %d (was next %s)' % (name_ja, pi, ph['go_anim_end'], tgt))
                    tgt = dest(ph['go_anim_end'])
                if tgt is not None:
                    # a turn that takes off itself (ジャンプ力 at frame 0) must not test landing before it is airborne:
                    # vanilla 甲 moves start the test well after the jump (ジャンピングニー jump 13 / test 23,
                    # ギャラクティックストライク 17 / 23, ブーストキック 5 / 6+). 6F margin.
                    if bullet:
                        ls_ = max(1, land_from or 1, 6 if any(o['startFrame'] == 0 and (o.get('int5') or 0) > 0 for o in ev[19]) else 1)
                    else:
                        # M 2026-10-28: BFE 着地時 (0x44433d) = previous height > 0 and height <= 0, i.e. a landing; DiveX
                        # 「着地していたら」 is a state and fired on frame 1 on the ground (ﾀｯｸﾙ lunge ph2 -> recovery at once =
                        # 'タックルで進まない'). Test from 2F after the phase's own take-off (min 6F as before); a go_land
                        # phase that never leaves the ground gets the frame-0 ground/air dispatch below (ground clone
                        # without the test).
                        ls_ = max(1, land_from or 1, max(6, lift + 2) if lift is not None else 1)
                    lo_ = lib.change([('オブジェクト→接触→着地していたら', [])], tgt, min(ls_, L - 1), L - 1)
                    ch.append(lo_)
                    if not bullet and ev[19]:
                        # M 2026-11-08 (LANDHOLDV, user メガブーストキック / ギャラクティックストライク 「空振りのとき着地で終わらない」):
                        # the BFE fall path ends with ジャンプ力 0 where BFE reaches the floor, but the DiveX mech is not exactly
                        # there (its height before the dive differs) and stops in the air / never gets a landing contact,
                        # so 着地していたら never fired (a hit ends the turn earlier). -> keep the last downward ジャンプ力
                        # until the turn ends: the mech keeps falling until it lands.
                        e19_ = sorted(ev[19], key=lambda o_: o_['startFrame'])
                        neg_ = [o_ for o_ in e19_ if (o_.get('int5') or 0) < 0]
                        if neg_:
                            last_ = neg_[-1]
                            tail_ = [o_ for o_ in e19_ if o_['startFrame'] > last_['startFrame']]
                            if all((o_.get('int2') or 0) == 0 and (o_.get('int5') or 0) == 0 for o_ in tail_):
                                for o_ in tail_:
                                    ev[19].remove(o_)
                                v_ = last_['int5']
                                if last_['endFrame'] < L - 1:
                                    ev[19].append(lib.obj(19, 3, last_['endFrame'] + 1, L - 1, int1=0, int2=v_, int4=0, int5=v_))
                                    rep.add('LANDHOLDV', '%s turn %d: fall path ends at F%d -> ジャンプ力 %d held to the landing test' % (name_ja, ti_, last_['endFrame'], v_))
                    if bullet:
                        # G 2026-11-03 (LANDZOOM, 調査記録 29): DiveX's foot offset (+0x1608, 0x608d60: rect 13 via
                        # 0x608970/0x6089e0, or the sprite bounds 0x765800) is scaled by the sprite zoom unless slot 43
                        # (+0x17d8) >= 0; BFE lands on the height alone (0x44433d). A zoom > 1.0 thus lowers the foot and
                        # fires 着地していたら early (ガトリングガン Lv2: 512 at F6-7 -> landed ~150px from the muzzle,
                        # user video 20261103_3). -> slot 43 = 256 over the enlarged frames, -1 (= follow the zoom,
                        # vanilla Muramasa F12) after them.
                        big = sorted(f_ for o_ in ev[1] if max(o_['int2'], o_['int5']) > 256
                                     for f_ in range(o_['startFrame'], o_['endFrame'] + 1) if f_ >= lo_['startFrame'] - 1)
                        spans = []
                        for f_ in big:
                            if spans and f_ <= spans[-1][1] + 1:
                                spans[-1][1] = max(spans[-1][1], f_)
                            else:
                                spans.append([f_, f_])
                        # only a pulse (the zoom returns to <= 1.0 inside the turn): the foot drops mid-flight. A
                        # zoom held for the whole turn (DD Lv3/4, 手榴弾 Lv4, ﾊﾝﾄﾞｶﾞﾝ Lv3 ...) keeps the hit rect
                        # following it (HITSCALE) - no early landing reported for those.
                        for a_, b_ in [sp_ for sp_ in spans if sp_[1] + 1 < L]:
                            ev[43].append(lib.obj(43, 0, a_, a_, int4=256))
                            ev[43].append(lib.obj(43, 0, b_ + 1, b_ + 1, int4=-1))
                            rep.add('LANDZOOM', '%s turn %d: zoom > 1.0 at F%d-%d with 着地 test from F%d -> slot 43 = 256 there '
                                    '(foot offset not zoomed, BFE lands on height)' % (name_ja, ti_, a_, b_, lo_['startFrame']))
                    if not bullet and lift is None and land_from is None and ti_ in ground_vert:
                        land_dispatch.append((ti_, lo_))
            HIT = ('オブジェクト→攻撃→残りメカＨＩＴ数→□なら(0)', [0])
            hitc = [HIT] if (miss_target is not None and hit_window) else []
            for lp in loops:
                if ti_ == lp['t_end']:     # LOOPPOS: turn of the alg position, threshold offset by the earlier loops
                    ev[35].append(lib.obj(35, 0, 0, 0, int1=1, int2=0, int3=1, int4=1))
                    ch.append(lib.change(hitc + [('オブジェクト→汎用→汎用カウンタ→□以下なら(0)', [lp['bias'] + lp['count'] - 1])], lp['t_start'], L - 1, L - 1))
                    rep.add('LOOP', '%s: phases %d..%d x%d via 汎用カウンタ' % (name_ja, lp['start'], lp['end'], lp['count']))
            ge = ph['go_end'] if ph['go_end'] != -99 else ph['go_anim_end']
            normal = dest(ge) if (ge != -99 and dest(ge) is not None) else nxt.get(ti_, 'end')
            # M 2026-10-31 (POSTAPEX): a turn that ends the skill at its last frame -> marked (post-skill gravity, _post_apex)
            end_mk = {'why': 'end', 'moving': False, 'h0': vh0, 'vtr': vtr}
            if miss_target is not None:
                if hit_window:
                    ch.append(lib.change(hitc, normal, L - 1, L - 1))
                    if not bullet and normal == 'end':
                        ch[-1]['_apex'] = dict(end_mk)
                fin = miss_target
            else:
                fin = normal
            ch.append(lib.change([], fin, L - 1, L - 1))
            if not bullet and fin == 'end':
                ch[-1]['_apex'] = dict(end_mk)
            ev[71] += ch
            for k in ('go_dist_out', 'go_hits_le_weapon') + (() if bullet else ('go_counter',)) + \
                    (() if bullet else ('go_obstacle', 'go_hit_weapon', 'go_origin_null', 'go_mech_spr', 'go_mech_alg', 'go_mech_skill')):
                if ph[k] != -99:
                    rep.add('IGNORED', '%s %s=%d' % ('bullet' if bullet else 'mech', k, ph[k]))
            turns.append((ev, L, moving))
        if loops and not any(l['t_start'] == 0 for l in loops):   # counter reset at skill start
            turns[0][0][35].insert(0, lib.obj(35, 0, 0, 0, int1=0, int2=0, int3=0, int4=0))
        elif loops:
            # R 2026-11-03 (LOOPPOS): a loop back to turn 0 re-ran this F0 reset on every pass (ガトリングガン弾 0..0 x10:
            # counter 0 -> +1 each pass, never past 9 -> the bullet looped until it hit). The engine already starts at 0:
            # skill start 0x61c980 calls vt+0x190 = 0x6075d0 (+0x17b0 = 0) for the mech, a new object copies the spawn's
            # 汎用変数 (sub 36, absent = 0) at 0x611eb7 (0x6111e0); vanilla フォトンブラスター：甲 bullets add to it with no reset.
            rep.add('LOOPPOS', '%s: loop back to turn 0 -> no F0 counter reset (engine starts at 0: 0x6075d0 / 0x611eb7)' % name_ja)
        # ---- facing tracking until the first active frame (Kou idiom: 方向増分 300 -> 0)
        if first_attack and not bullet:
            fp, fs = first_attack
            turns[0][0][10].append(lib.obj(10, 3, 0, 0, int5=300))
            fs = max(fs, 4) if fp == 0 else fs
            cd_fp = phases[turn_phase[fp]]['chip_dir']
            keep_fp = cd_fp['type'] in FACE_TYPES and bool(cd_fp['flags'] & 2)
            if keep_fp:     # FACEPHASE: the first striking phase itself keeps facing the enemy (ｽｳｨﾝｸﾞﾜｲﾔｰ ph1)
                rep.add('FACEPHASE', '%s turn %d: first strike phase has チップ向き 敵方向 + 常に方向ﾁｪｯｸ -> slot 10 tracking not stopped at F%d' % (name_ja, fp, fs))
            else:
                turns[fp][0][10].append(lib.obj(10, 3, fs, fs, int5=0))
            self._face_phases(turns, turn_phase, pos_turn, phases, fp, keep_fp, name_ja)
        elif not bullet and phases:
            # R 2026-11-18 (FACEALWAYS, user 「原作で常に敵を向く技は、移植版でも改善版でもそうしてほしい」, 調査記録 79 §6): a technique
            # with no mech strike (射撃・設置など) never got the Kou 300 -> 0 window; its 常に方向ﾁｪｯｸ phases track the
            # enemy from their F0 (甲 ダブルサブマシンガン T0 300), a later phase without it stops at its F0.
            self._face_phases(turns, turn_phase, pos_turn, phases, None, False, name_ja)
        # ---- boilerplate from the template's first turn (retimed)
        fc_ti_ = next((ti_ for ti_, pi_ in enumerate(turn_phase) if phases[pi_]['flags'] & 32 and ti_ < len(turns)), None) if fc else None
        self._boiler(tpl, turns, fc and fc_ti_ is None, keep0=bool(phases) and phases[turn_phase[0]]['speed']['init'][0] == -32768, name_ja=name_ja,
                     ph0=phases[turn_phase[0]] if phases else None)
        if fc and fc_ti_ is not None:
            self._fc_at(tpl, turns, fc_ti_, name_ja)
        if not bullet and phases:
            self._dash_rates(turns, turn_phase, pos_turn, phases, loops, name_ja)
        if not bullet:
            # HITCANCEL: a template slot 47 value-3 range (キャンセル操作 window, [+0x1904], DiveX only) is split around the
            # single-frame BFE events like vanilla 甲 ケイジブレイドLv3 T1 (F0-10 = 3, F11 = 1, F12-63 = 3)
            for ev_, _L, _m in turns:
                mine = [o for o in ev_[47] if o.pop('_c47', False)]
                fs_ = set(o['startFrame'] for o in mine); ids_ = set(map(id, mine))
                rest = []
                for o in ev_[47]:
                    if id(o) in ids_:
                        continue
                    segs = [(o['startFrame'], o['endFrame'])]
                    for f_ in sorted(fs_):
                        segs = [x for s_, e_ in segs for x in (((s_, f_ - 1), (f_ + 1, e_)) if s_ <= f_ <= e_ else ((s_, e_),)) if x[0] <= x[1]]
                    for s_, e_ in segs:
                        o2 = copy.deepcopy(o); o2['startFrame'], o2['endFrame'] = s_, e_; rest.append(o2)
                ev_[47] = rest + mine
        # ---- HOMING_EITHER: clone turn with the other end of the 方向補正 (see the slot 16 code above)
        nxt_ = lib._key(lib.jumps['ターンジャンプ→１つ先'])
        for ti_ in range(len(turns)):
            ev_, L_, m_ = turns[ti_]
            alt_ = [o for o in ev_[16] if '_alt16' in o]
            if not alt_:
                continue
            hi_ = alt_[0].pop('_alt16')
            k = len(turns)
            cev = copy.deepcopy(ev_)
            for o in cev[16]:
                if o['startFrame'] == 0:
                    o['int2'] = o['int5'] = hi_
            for o in cev[71]:
                j = o['bsdxInfoCollectionList2'][0]
                if lib._key(j) == nxt_:
                    j2 = copy.deepcopy(lib.jumps['ターンジャンプ→指定(0)']); j2['paramList'] = [ti_ + 1]
                    o['bsdxInfoCollectionList2'] = [j2]
            turns.append((cev, L_, m_))
            ev_[71].insert(0, lib.change([('汎用→確率(0)', [5000])], k, 0, 0))
        # R 2026-11-08 (TWINMUZZLE, user ダブルサブマシンガン 「片方の銃からしか出ない」, 原作 通常 1:43): BFE 発射位置 判定 with two
        # rect bits (ﾀﾞﾌﾞﾙｻﾌﾞﾏｼﾝｶﾞﾝ judge 96 = the two 4x4 muzzle rects of anim 303-305) shoots from the muzzles in turn;
        # the 甲 template spawn kept 発射位置 (0, 2) only. Vanilla ダブルサブマシンガン：甲 alternates (0, 1) / (0, 2) -> same,
        # by fire frame (the muzzle flash of the same frame follows its shot).
        if not bullet:
            for ti_, pi_ in enumerate(turn_phase):
                if ti_ >= len(turns):
                    break
                og_ = phases[pi_]['fire'].get('origin') or {}
                jb_ = (og_.get('judge') or [0, 0, 0, 0])[2]
                # judge 7 (bits 0-2) is the common default of most fire origins (single muzzle in BFE) -> two or more bits
                # above it only (ﾀﾞﾌﾞﾙｻﾌﾞﾏｼﾝｶﾞﾝ 96)
                if not (og_.get('flags', 0) & 1 and bin(jb_ & 0xfff8).count('1') >= 2):
                    continue
                frames_ = []
                for o_ in turns[ti_][0][48]:
                    d7_ = effect_sub(o_, 7)
                    b7_ = (d7_ or {}).get('bsdxInfoCollectionList') or []
                    if b7_ and b7_[0]['typeList'] == [1] and b7_[0]['intList3'][:1] == [0] and b7_[0]['intList3'][1] in (1, 2):
                        frames_.append((o_['startFrame'], b7_[0]))
                order_ = sorted(set(f_ for f_, b_ in frames_))
                for f_, b_ in frames_:
                    b_['intList3'] = [0, 1 + order_.index(f_) % 2]
                if frames_:
                    rep.add('TWINMUZZLE', '%s ph%d: 発射位置 判定 %d (two rects) -> spawn sub 7 (0,1)/(0,2) alternating, %d shots' % (name_ja, pi_, jb_, len(order_)))
        # R 2026-11-08 (DIR16RESET, user ガトリングビット 「離れすぎる問題が継続」): slot 16 方向補正 is kept on the object (+0x174c)
        # and added to every later slot 15 target heading (0x606d34, 0x60c02b). ﾋﾞｯﾄ ph1 orbits with ±90; back in the
        # approach turn (DISTOUT) the ±90 stayed -> it kept circling outward instead of closing in. BFE recomputes the
        # heading per phase (no carried offset) -> a bullet turn that aims (slot 15) without its own slot 16 gets 0 at F0
        # when another turn of the skill sets one.
        if bullet and any(t_[0][16] for t_ in turns):
            for ev_, L_, m_ in turns:
                if ev_[15] and not ev_[16] and (16, 3) in lib.ev:
                    ev_[16].append(lib.obj(16, 3, 0, 0, int2=0, int5=0))
                    rep.add('DIR16RESET', '%s: aiming turn without 方向補正 -> slot 16 0 at F0 (the ±offset of another turn carried over)' % name_ja)
        # ---- BFE 空中時 (exe 0x443c9a: on phase entry, height obj+0x64->+0x14 > 0 -> go_air). Vanilla DiveX idiom
        # (甲 ブーストキック turn 0): frame 0 「接触→着地していたら」 => ground turn, else (無条件) => air turn. The
        # ground path continues in a clone of this turn appended at the end (the original turn becomes the 1-frame
        # dispatcher). The former 「高さ→□超過なら(4)」 at frame 0 also fired on the ground when the same frame applied
        # the ground version's take-off jump (ブーストキック / ギャラクティックストライク ...), so the air version played.
        for ti_, air in air_dispatch:
            k = len(turns)
            ev, L, m = turns[ti_]
            turns.append((copy.deepcopy(ev), L, m))
            # the dispatcher is a bare 1-frame turn like 甲 ブーストキック T0 (gravity 50 + the two changes): the
            # ground version's frame-0 events (take-off jump, speed) must not run before the landing test
            dv = collections.defaultdict(list)
            dv[35] = [o for o in ev[35] if o['startFrame'] == 0]          # loop counter reset
            dv[21] = [lib.obj(21, 2, 0, 0, int5=50)]
            dv[71] = [lib.change([('オブジェクト→接触→着地していたら', [])], k, 0, 0), lib.change([], air, 0, 0)]
            turns[ti_] = (dv, 1, m)
            rep.add('AIR', '%s turn %d: frame-0 dispatch 着地していたら -> turn %d (ground clone), else -> %s' % (name_ja, ti_, k, air))
            # R 2026-11-17 AIRMOVERATE (template slot 24 / 30 onto the air turn) retired 11/18: every turn now carries its own
            # BFE-derived slot 24 / 30 at F0 (DASHRATE, _dash_rates).
        air_src = set(t_ for t_, _a in air_dispatch)
        land_dispatch = [x for x in land_dispatch if x[0] not in air_src]
        if not bullet:
            # M 2026-10-28: the template's ﾍﾞｸﾄﾙ補正率：重力 / ジャンプ力 (slot 27 / 28, copied from 甲 turn 0 and retimed:
            # e.g. 28 = 10 % at F0) scaled or froze the converted vertical curve and persisted after the skill (甲 restores
            # them in its own later frames, which the port does not have) -> 100 % at frame 0 of turn 0.
            for ev_, _L, _m in turns:
                ev_[27] = []; ev_[28] = []
            turns[0][0][27] = [lib.obj(27, 0, 0, 0, int1=0, int4=100)]
            turns[0][0][28] = [lib.obj(28, 0, 0, 0, int1=0, int4=100)]
            rep.add('VRATE', 'mech slot 27/28 (重力/ジャンプ力 補正率) template values dropped -> 100 at turn 0 F0')
        for ti_, lo_ in land_dispatch:
            # M 2026-10-28: go_land phase that never takes off from the ground (BFE: no landing -> runs to its end).
            # Same frame-0 dispatch as 空中時 above: on the ground -> clone without the landing test and with the
            # ground-entry vertical curve; in the air -> clone of the original turn.
            ev, L, m = turns[ti_]
            kg, ka = len(turns), len(turns) + 1
            gev = copy.deepcopy(ev)
            gev[71] = [o for o, o0 in zip(gev[71], ev[71]) if o0 is not lo_]
            for o in gev[71]:
                if '_apex' in o:       # M 2026-10-30: the ground version never takes off -> it ends grounded
                    o['_apex']['vtr'] = None
            gev[19], gev[21] = [copy.deepcopy(o) for o in ground_vert[ti_][0]], [copy.deepcopy(o) for o in ground_vert[ti_][1]]
            turns.append((gev, L, m)); turns.append((copy.deepcopy(ev), L, m))
            dv = collections.defaultdict(list)
            dv[35] = [o for o in ev[35] if o['startFrame'] == 0]
            dv[21] = [lib.obj(21, 2, 0, 0, int5=0)]
            dv[71] = [lib.change([('オブジェクト→接触→着地していたら', [])], kg, 0, 0), lib.change([], ka, 0, 0)]
            turns[ti_] = (dv, 1, m)
            rep.add('LANDTEST', '%s turn %d: go_land without take-off -> frame-0 dispatch 着地していたら -> turn %d (no test), else -> turn %d' % (
                name_ja, ti_, kg, ka))
        stop_fix = []
        for ti_, (ev_, L_, _m) in enumerate(turns):
            marks = [(o, o.pop('_apex')) for o in ev_[71] if '_apex' in o]
            if marks and not bullet:
                self._post_apex(ev_, L_, marks, name_ja, ti_)
            # hit -> end of a moving turn -> the 1F stop turn below (speed 0; vertically it is one free-fall frame:
            # no slot 19 / 21 event, so the vz and the post-skill gravity of the hit frame go on)
            stop_fix += [o for o, mk in marks if mk['why'] == 'hit' and mk['moving']]
        if stop_fix:
            # BFE ends the move on hit (go_hit_mech 99) and the mech drops back into its plain movement state; in DiveX
            # the skill end keeps the current momentum (ジャンピングニー: 透 kept flying with speed 32 + jump after the
            # hit, reported). Vanilla 甲 moves zero the speed before they end -> speed 0.
            # M 2026-10-28: ending in the air also handed the template's 技後の慣性補正 (slot 33, 甲 JK F13: 上昇量 3..4 /
            # 重力増分 0..0) to the free-flying mech = 透 rose off-screen after the JK hit (BSX問題の近接技.mp4 F530-578).
            # M 2026-10-29: the 10-28 「wait for landing」 stop turn (重力 50, 80F) made the hit locked and floaty (user
            # 10/28: 「命中後は攻撃が終わり、いい感じの慣性が残る技なので微悪化」). BFE ends the skill on the hit (go_hit_mech 99) and
            # the free mech keeps its vertical velocity under the base gravity block (-128, 0x420be0; 原作10: JK hit F139,
            # rises ~50px more, lands ~17 ticks after the hitstop, horizontal drift ~14px). -> 1F stop turn again: speed 0,
            # slot 33 = the vanilla end-of-skill value (0,8,0,6,0,99999) (甲 JK T1; min 上昇量 0 = no forced rise; the
            # vanilla hit -> recovery turns use the same 上昇量 0..6 / 重力増分 0..99999), then end at F0.
            k = len(turns)
            sv = collections.defaultdict(list)
            sv[18] = [lib.obj(18, 3, 0, 0, int1=0, int2=0, int4=0, int5=0)]
            if (33, 12) in lib.ev:
                o = copy.deepcopy(lib.ev[(33, 12)]); o['startFrame'] = o['endFrame'] = 0; o['offset'] = 0
                o.update(long1=0, long2=8, int1=0, int2=6, int3=0, int4=99999); sv[33] = [o]
            sv[71] = [lib.change([], 'end', 0, 0)]
            turns.append((sv, 1, False))
            for o in stop_fix:
                j = copy.deepcopy(lib.jumps['ターンジャンプ→指定(0)']); j['paramList'] = [k]
                o['bsdxInfoCollectionList2'] = [j]
            rep.add('STOP', '%s: hit -> end redirected to 1F stop turn %d (speed 0, slot 33 0,8,0,6,0,99999, end)' % (name_ja, k))
        out = {'phaseQuantity': len(turns), 'skillNameJapanese': name_ja, 'skillNameEnglish': name_en, 'phasesInfo': [],
               'skillSuffixList': [{'int1': i, 'int2': 0} for i in range(len(turns))]}
        for ev, L, _m in turns:
            units = []
            for slot in sorted(ev):
                if not ev[slot]:
                    continue
                for o in ev[slot]:
                    o['slotNum'] = slot
                    o['startFrame'] = max(0, min(o['startFrame'], 9999)); o['endFrame'] = max(o['startFrame'], min(o['endFrame'], 9999))
                units.append({'unitQuantity': slot, 'unitDescription': self.lib.desc[slot],
                              'skillInfoObjectList': sorted(ev[slot], key=lambda o: o['startFrame']) if slot not in (71,) else ev[slot],
                              'skillInfoUnknownList': []})
            out['phasesInfo'].append({'skillUnitCollection': units})
        return out

    POST_G = (50, 5000)    # M 2026-10-31 (POSTAPEX): DiveX floor of the post-skill gravity (0x6299d0 / 0x61cab8) .. vanilla max 重力

    @staticmethod
    def dx_rise(vz, a):
        """M 2026-10-31 (POSTAPEX): DiveX rise (px) after the frame a skill ends with vertical velocity vz (px/F) under the
        gravity a px/F^2. Per frame BaldrSky.exe runs the skill events (0x60d3da -> 0x60bfd0: slot 19 writes vz, 0x60c206),
        then the movement update 0x5f5120: the position integrates vz (0x5f5604) and only then the six sub-moves update
        (0x5f56a8 loop -> gravity move vtbl+4 = 0x5f4be0: vz -= 重力*1024/200 * 補正率/100) -> later frames move vz-a,
        vz-2a, ..."""
        r = 0.0; v = vz - a
        while v > 0:
            r += v; v -= a
        return r

    def _post_apex(self, ev, L, marks, name_ja, ti):
        """M 2026-10-31 (POSTAPEX): post-skill rise of a mech skill that ends in the air = the BFE one (apex height), for
        every frame at which the turn can end the skill (「hit -> end」 window, last frame). Replaces the 10-30 FREEFALL
        fall turns (frames the BFE skill does not have; user 10/29).
        BFE: after the skill (go_hit_mech 99 / last phase) only the base block 1 (-128, 0x420be0) is left -> v += -128
        per tick (bfe_free_fall) from the state (h, v) of the exit tick: apex = h + rise.
        DiveX, natural end (turn jump 終了): the mech enters its free state; every state's enter (0x629cf0 / 0x62e1e0 /
        0x62eae0 -> 0x6299d0, 0x62c500 / 0x62d190 / ... call it too) only FLOORS the gravity of the vertical move to 50
        ((g + 0x200) & ~0x3ff < 0xc800 -> 0xc800) and keeps vz. 技後の慣性補正 (slot 33 -> +0x1798..+0x17ac, 0x618150:
        vz clamp [int1, int2], gravity rate clamp [int3, int4]) is applied only when a NEW skill starts while one is
        running (0x61c980 -> 0x61ca8a) or by the cancel input (0x61c790 -> 0x61c893), not on the natural end: 移植版2
        (10/29 build, JK hit -> 1F stop turn with slot 33 (0,8,0,6,..) -> end) rose at ~8 px/F, above int2 = 6.
        So the free rise = dx_rise(vz at the exit frame, G/200) with G = max(50, slot 21 重力 in effect). Vanilla skills
        end with 重力 > 50 in effect (Akao 空中ファントム 100, Muramasa 臥竜 200, Zako030a ジャンプ殴り 500 ...) and change
        重力 inside a turn (Zako104a 突き上げ 0 -> 50 -> 100 -> 300).
        Rule: per exit frame f (BFE tick f//2): G(f) = the integer in [50, 5000] whose dx_rise(vz(f), G/200) is closest
        to (BFE apex - DiveX height after f); slot 21 events from the first exit frame on. The vz curve (slot 19) is not
        changed: every frame from there on is covered by a slot 19 event (single-frame events -> spans of the same value)
        so the in-skill motion stays exact although 重力 is no longer 0 (vz is rewritten before it moves, see dx_rise)."""
        lib = self.lib
        e19 = sorted(ev[19], key=lambda o: o['startFrame'])
        vz = []; cur = 0.0
        for f in range(L):
            for o in e19:
                s_, e_ = o['startFrame'], o['endFrame']
                if s_ <= f <= e_:
                    a_, b_ = o.get('int2') or 0, o.get('int5') or 0
                    cur = a_ + (b_ - a_) * (f - s_) / float(e_ - s_) if e_ > s_ else float(b_)
            vz.append(cur)
        exits = {}
        for o, mk in marks:
            if mk['vtr']:
                for f in range(max(0, o['startFrame']), min(o['endFrame'], L - 1) + 1):
                    exits.setdefault(f, mk)
        if not exits:
            return
        G0, G1 = self.POST_G
        gf = {}; info = collections.OrderedDict(); fall = collections.OrderedDict()
        for f in sorted(exits):
            mk = exits[f]; vtr = mk['vtr']
            k = min(f // 2, len(vtr) - 1)
            h, v = vtr[k]
            rise = max([0] + list(itertools.accumulate(bfe_free_fall(h, v)))) if (h > 0 or v > 0) else 0
            H = mk['h0'] + sum(vz[:f + 1])
            T = h + rise - H
            if vz[f] <= 0:                     # falling / grounded at the exit: no rise either way (G kept)
                if h > 0 or round(H) > 0:
                    fall.setdefault(mk['why'], []).append((k, h, round(H), h + rise))
                continue
            if T <= 0:
                g = min(G1, int(math.ceil(200 * vz[f])))
            elif self.dx_rise(vz[f], G0 / 200.0) <= T:
                g = G0                         # DiveX cannot rise as high from this vz (shortfall, logged)
            else:
                lo, hi = G0, G1                # dx_rise decreases with G: last G with rise >= T, then the closer one
                while hi - lo > 1:
                    m_ = (lo + hi) // 2
                    if self.dx_rise(vz[f], m_ / 200.0) >= T:
                        lo = m_
                    else:
                        hi = m_
                g = min((lo, hi), key=lambda x: abs(self.dx_rise(vz[f], x / 200.0) - T))
            gf[f] = g
            info.setdefault((mk['why'], k), (f, h, v, rise, H, vz[f], g))
        for why, xs in fall.items():
            ks = sorted(set(x[0] for x in xs))
            self.rep.add('POSTAPEX', '%s T%d %s ticks %d-%d: airborne but not rising at the exit (BFE v <= 0 or < 1 px/tick, '
                         'DiveX vz <= 0): no rise either way, apex = exit height (BFE %d..%d / DiveX %d..%d px), 重力 kept' % (
                             name_ja, ti, 'hit -> end' if why == 'hit' else 'end', ks[0], ks[-1],
                             min(x[3] for x in xs), max(x[3] for x in xs), min(x[2] for x in xs), max(x[2] for x in xs)))
        if not gf:
            return
        # slot 19: cover every frame from the first G on (vz must be rewritten each frame once 重力 != 0)
        f0 = min(gf)
        cov = []
        for i, o in enumerate(e19):
            nxt_s = e19[i + 1]['startFrame'] if i + 1 < len(e19) else L
            if o['endFrame'] < nxt_s - 1 and nxt_s - 1 >= f0:
                if o['startFrame'] == o['endFrame']:
                    o['endFrame'] = nxt_s - 1
                else:
                    c_ = o.get('int5') or 0
                    cov.append(lib.obj(19, 3, o['endFrame'] + 1, nxt_s - 1, int1=0, int2=c_, int3=0, int4=0, int5=c_, int6=0))
        ev[19] = sorted(e19 + cov, key=lambda o: o['startFrame'])
        prev = None
        for f in sorted(gf):
            if gf[f] != prev:            # one 重力 event per frame (replaces the F0 重力 0 of _vert_events)
                ev[21] = [o for o in ev[21] if o['startFrame'] != f] + [lib.obj(21, 2, f, f, int5=gf[f])]; prev = gf[f]
        for (why, k), (f, h, v, rise, H, vzf, g) in info.items():
            self.rep.add('POSTAPEX', '%s T%d %s tick %d (F%d): BFE h %d v %d -> free fall apex %d (+%d); DiveX h %d vz %.1f: '
                         'apex %d at 重力 50 -> %d at 重力 %d (slot 21 from F%d, 0x6299d0 keeps >= 50)' % (
                             name_ja, ti, 'hit -> end' if why == 'hit' else 'end', k, f, h, v, h + rise, rise, round(H), vzf,
                             round(H + self.dx_rise(vzf, 0.25)), round(H + self.dx_rise(vzf, g / 200.0)), g, f))

    def _vert_events(self, d_ticks, L):
        """M 2026-10-28: BFE per-tick height changes (px/tick, from bfe_vert_sim) -> slot 19 ジャンプ力 events (px/F) with
        slot 21 重力 0, so the DiveX height follows the BFE curve exactly. BaldrSky.exe: slot 19 writes the vertical
        velocity (x1024 px/F, 0x60c1f7 -> CMove+0x14 +0x10), gravity subtracts 重力/200 px/F each frame (0x5f4be0: x1024 * 0x51eb851f >> 38; M 2026-10-29, was /100), the
        position integrates px/F (0x5f5604). One BFE tick = 2 frames: d even -> vz d/2 from the run's first frame (it
        persists with gravity 0); d odd -> ramp (d+1)/2 -> (d-1)/2 over the run (average d/2)."""
        lib = self.lib
        e19 = []; cur = None; k = 0; n = len(d_ticks)
        while k < n:
            j = k
            while j + 1 < n and d_ticks[j + 1] == d_ticks[k]:
                j += 1
            d = d_ticks[k]; s, e = 2 * k, min(L - 1, 2 * j + 1)
            if s > L - 1:
                break
            if d % 2 == 0:
                if cur != d // 2:
                    e19.append(lib.obj(19, 3, s, s, int1=0, int2=d // 2, int3=0, int4=0, int5=d // 2, int6=0)); cur = d // 2
            else:
                a, b = (d + 1) // 2, (d - 1) // 2
                e19.append(lib.obj(19, 3, s, e, int1=0, int2=a, int3=0, int4=0, int5=b, int6=0)); cur = b
            k = j + 1
        return e19, [lib.obj(21, 2, 0, 0, int5=0)]

    def _dir_event(self, f, angle=0, rnd=0):
        """slot 15 角度指定→スプライト方向(angle, ±rnd) in degrees (vanilla Zako011b ショルダータックル uses (180,0) to move
        backwards; BFE move_dir 初期値 is in degrees too, e.g. 波動砲 recoil 180)"""
        o = copy.deepcopy(self.lib.ev[(15, 10)]); o['startFrame'] = o['endFrame'] = f; o['offset'] = 0
        b = o['bsdxInfoCollectionList'][0]
        assert b['typeList'] == [3, 0] and len(b['paramList']) == 2, b
        b['paramList'] = [int(angle), int(rnd)]
        return o

    BOILER = (6, 24, 26, 27, 28, 30, 31, 33, 45, 46, 47, 54, 67, 69, 70)
    # slot 43 攻撃判定拡大縮小反映率 is NOT copied (S 2026-10-28): BaldrSky.exe 0x635e2b maps it to obj+0x17d8 and the
    # hit-rect code 0x607e88..0x607ecc uses it as an absolute rect scale (256 = 1.0) for both axes when >= 0, else (the
    # default -1, 0x607612) the sprite zoom X/Y (+0x16a0/+0x16a4). The 甲 ハンドガン template's 512 (its spawn stretches
    # the sprite X 512) doubled every converted bullet's hit rect (ｼｰﾙﾄﾞ 256x256 -> 512x512: 'hit area too wide',
    # reported). BFE scales attack rects with the sprite zoom (0x414a10) = the DiveX default.
    BOILER_BULLET = (26, 45, 70)
    FCSLOTS = (59, 60, 61, 62, 63, 64, 65, 66, 68)

    # R 2026-11-18 (DASHRATE, 調査記録 77, user 11/18 「ノーマルダッシュやサーチダッシュの慣性が乗りすぎている」 -> 案 A'):
    # BFE (BaldrForce.exe) during a mech skill:
    #  * walk / dash = movement block 0, scaled per phase by 「移」 (calc_speed +0x0C rate_move, phase +0x32) in the composite
    #    0x448c70 via 0x449050 (0 x1, 1 x0.9, 2 x0.75, 3 x0.5, 4 x0.25, 5 x0.125, 6 x2, 7 x1.5, 8 x1.25, 9 x0).
    #    -> slot 24 ﾍﾞｸﾄﾙ補正率：移動 (CMove 0x5f51c6 +0x1770) = that rate at F0 of every turn.
    #  * S dash = block 5 (enter 0x419cb0: 32 px/tick once), NOT scaled by 移; its tick 0x419e40 during a skill on the ground
    #    sets target 0 and step ±(phase +0x34 「風」 <<8): the momentum falls by 風 px/tick per tick (風/4 px/F per F, 風 0 =
    #    stop at once). 風 2 (517 of 716 透 phases) stops a 16 px/F dash in 32F.
    #    DiveX keeps the search / boost dash in the dash-inertia vector (skill start 0x61c980 -> vt+0x24 0x62b990 / 0x62aa70)
    #    which only loses 4/1000 of the base speed per frame, scaled by slot 30 ｻｰﾁﾀﾞｯｼｭ補正率 (0x5f5445 +0x1788).
    #    -> slot 30 follows the BFE decay scaled to 透's faster dash (user 11/18: 「原作より速くしたぶん、技中に移動する距離も
    #    ほとんど同じくらいの倍率で大きいと良い」): rate(f) = BFE speed(f) / (SD_PORT - decel*f) * SD_PORT/16 = 100 * vb / (16 -
    #    16*SD_DECEL*f), so the slide = (26/16) x BFE's. BD shares the vector and slot 30 -> same frames, x18/26 distance.
    # Turn values follow the first pass of the alg list (each turn: start = previous, end = the rate where the BFE momentum
    # ends or the turn ends). Approximations (reported): a jump that skips turns enters the next one with a higher rate
    # (ramps down from it); a jump-only turn ramps from the previous rate to 0 over the full BFE stop time of its 風; a turn
    # re-entered by a loop / backward jump with a non-zero end rate ramps back up to it.
    SD_PORT = 26           # 透 mek サーチダッシュ速度 (Tooru.mek, user 調査記録 21)
    SD_DECEL = 0.004       # DiveX 0x62b990: decel = base speed x 4 / 1000 per frame
    MOVE_RATE = {0: 100, 1: 90, 2: 75, 3: 50, 4: 25, 5: 12.5, 6: 200, 7: 150, 8: 125, 9: 0}

    def _face_phases(self, turns, turn_phase, pos_turn, phases, fp, keep_fp, name_ja):
        """R 2026-11-18 (FACEPHASE, user 「青龍刀とダブルセイバーの多段攻撃中、敵が横に回り込んでも正面を攻撃し続ける」, 調査記録 79).
        BFE の機体の段の チップ向き（段 +0x50、calc_dir）が 機体の向き。段の開始時 BaldrForce.exe 0x43fe00 が、向きﾀｲﾌﾟ 1
        （ﾛｯｸｵﾝした敵方向）なら 自分→ﾛｯｸ座標 の角度（0x40d410）を基準に置き、初期値・最終値・増分（0 = 即座に最終値）で向きを
        決める = 段に入るたびに敵へ向き直る。フラグ 0x02「常に方向ﾁｪｯｸ」は毎 tick 向き直す（AIMONCE と同じフラグ）。
        変換は今まで最初の攻撃フレームまでしか向きを追わなかった（甲の書き方 300 -> 0）ので、それより後の段の向き直りが落ちていた。
        最初の攻撃の段より後（alg の順）の段ごとに:
          * 敵方向 + 常に方向ﾁｪｯｸ -> F0 に slot 10 = FACE_RATE（甲 ダブルサブマシンガン T0 300 のまま止めない書き方）
          * 敵方向（1 回）       -> F0 に slot 10 = FACE_SNAP、F1 に 0（甲 ASスティンガー T2 F30 9999 / F31 0 の 1F 向き直り）
          * 向き修正なし         -> 前の段が追い続けていたら F0 に 0（止める）
        """
        lib = self.lib
        order = []
        for t in pos_turn:
            if t not in order:
                order.append(t)
        # fp None (FACEALWAYS): no mech strike -> only the 常に方向ﾁｪｯｸ phases, from the first turn
        if fp is not None and fp not in order:
            return
        cont = keep_fp; pend0 = False; log_ = []
        for t in (order[order.index(fp) + 1:] if fp is not None else order):
            if t >= len(turns):
                continue
            ev, L, _m = turns[t]
            cd = phases[turn_phase[t]]['chip_dir']
            face = cd['type'] in FACE_TYPES
            always = face and (cd['flags'] & 2 or cd['type'] == 4)    # type 4 敵座標（常時）
            if fp is None and not always:
                if cont:
                    ev[10].append(lib.obj(10, 3, 0, 0, int5=0)); log_.append('T%d 停止' % t); cont = False
                continue
            if always:
                ev[10].append(lib.obj(10, 3, 0, 0, int5=FACE_RATE)); log_.append('T%d 常時' % t)
                cont, pend0 = True, False
            elif face:
                ev[10].append(lib.obj(10, 3, 0, 0, int5=FACE_SNAP))
                if L > 1:
                    ev[10].append(lib.obj(10, 3, 1, 1, int5=0)); pend0 = False
                else:
                    pend0 = True
                log_.append('T%d 開始時' % t); cont = False
            elif cont or pend0:
                ev[10].append(lib.obj(10, 3, 0, 0, int5=0)); log_.append('T%d 停止' % t)
                cont = pend0 = False
        if log_:
            if fp is None:
                self.rep.add('FACEALWAYS', '%s: 打撃なし、チップ向き 敵方向 + 常に方向ﾁｪｯｸ の段 -> slot 10 %s (BFE 0x43fe00)' % (name_ja, ', '.join(log_)))
            else:
                self.rep.add('FACEPHASE', '%s: 最初の攻撃（turn %d）より後の段の チップ向き 敵方向 -> slot 10 %s (BFE 0x43fe00)' % (name_ja, fp, ', '.join(log_)))

    def _dash_rates(self, turns, turn_phase, pos_turn, phases, loops, name_ja):
        lib = self.lib; rep = self.rep
        for t, (ev, L, _m) in enumerate(turns):
            ev[24] = [lib.obj(24, 0, 0, 0, int1=0, int2=0, int3=0, int4=int(round(self.MOVE_RATE[phases[turn_phase[t]]['speed']['rate_move']])))]
        order = []
        for t in pos_turn:
            if t not in order:
                order.append(t)
        vb, f, done = 16.0, 0, {}
        for t in order:
            ev, L, _m = turns[t]
            w = phases[turn_phase[t]]['speed']['rate_wind']
            if vb <= 0 or w == 0:
                done[t] = (0, 0, 0, 0); vb = 0.0
            else:
                e = min(L, int(math.ceil(vb / (w / 4.0))))
                vb_e = max(0.0, vb - w / 4.0 * e)
                r1 = int(round(100 * vb_e / (16 - 16 * self.SD_DECEL * (f + e)))) if vb_e > 0 else 0
                done[t] = (1 if t != order[0] else 0, 0 if t != order[0] else 100, max(0, e - 1), r1)
                vb = vb_e
            f += L
        back = set(l['t_start'] for l in loops)
        pos_of = {t: i for i, t in enumerate(order)}
        for t, pi in enumerate(turn_phase[:len(turns)]):
            for k, v in phases[pi].items():
                if k.startswith('go_') and isinstance(v, int) and 0 <= v < len(phases) and v in pos_of and t in pos_of and pos_of[v] <= pos_of[t]:
                    back.add(v)
        for t, (ev, L, _m) in enumerate(turns[:len(turn_phase)]):
            w = phases[turn_phase[t]]['speed']['rate_wind']
            if t in done:
                i1, i2, ef, r1 = done[t]
                if t in back and r1 > 0:
                    rep.add('APPROX', 'DASHRATE %s: turn %d re-entered (loop / backward jump) with slot 30 end %d -> may ramp up again' % (name_ja, t, r1))
            elif w == 0:
                i1, i2, ef, r1 = 0, 0, 0, 0
            else:
                i1, i2, ef, r1 = 1, 0, min(L - 1, int(math.ceil(16 / (w / 4.0))) - 1), 0
                rep.add('APPROX', 'DASHRATE %s: jump-only turn %d: slot 30 previous -> 0 over F0-%d (風 %d)' % (name_ja, t, ef, w))
            ev[30] = [lib.obj(30, 0, 0, ef, int1=i1, int2=i2, int3=0, int4=r1)]
        rep.add('DASHRATE', '%s: slot 24 = BFE 移 %s; slot 30 %s' % (
            name_ja, [self.MOVE_RATE[phases[pi]['speed']['rate_move']] for pi in turn_phase[:len(turns)]],
            ' '.join('T%d:%s%d->%d@F%d' % (t, 'prev' if o['int1'] else '', o['int2'], o['int4'], o['endFrame'])
                     for t, (ev, _L, _m) in enumerate(turns) for o in ev[30])))

    def _boiler(self, tpl, turns, fc, keep0=False, name_ja='', ph0=None):
        if not tpl['phasesInfo']:
            return
        t0 = tpl['phasesInfo'][0]
        tl = max([o['endFrame'] for u in t0['skillUnitCollection'] for o in u['skillInfoObjectList']] + [1]) + 1
        ev, L, _m = turns[0]
        f = L / tl
        slots = self.BOILER_BULLET if self.mode != 'mech' else self.BOILER
        if self.mode != 'mech' and any(u['unitQuantity'] == 43 for u in t0['skillUnitCollection']):
            self.rep.add('HITSCALE', 'bullet slot 43 (template %s) not copied: hit rect follows the sprite zoom (BFE 0x414a10, '
                         'BaldrSky 0x607e88)' % [o.get('int4') for u in t0['skillUnitCollection'] if u['unitQuantity'] == 43
                                                  for o in u['skillInfoObjectList']])
        for u in t0['skillUnitCollection']:
            s = u['unitQuantity']
            if s in slots or (fc and s in self.FCSLOTS):
                # T 2026-11-11 (MOVERATE, examined and NOT converted): slot 24 / 30 移動 / ｻｰﾁﾀﾞｯｼｭ補正率 scale the walk and
                # search-dash vectors (BaldrSky.exe CMove 0x5f51c6 +0x1770 / 0x5f5445 +0x1788; reset to 100 at every skill
                # start 0x61c980 -> vt+0x17c 0x606900). Whether the walk vector still follows the stick during a skill is not
                # established, and BFE's per-calc 「移」 rate (calc_speed +12, values 0..9) is not decoded -> 甲 template kept.
                if self.mode == 'mech' and s in (24, 30):
                    # R 2026-11-18 (DASHRATE, 調査記録 77): ﾍﾞｸﾄﾙ補正率：移動 / ｻｰﾁﾀﾞｯｼｭ come from the BFE phases (_dash_rates),
                    # not from 甲's turn 0. Replaces MOVERATE (not converted, 11/11), SDKEEP (11/04) and AIRMOVERATE (11/17).
                    self.rep.add('DASHRATE', '%s: template slot %d dropped (BFE 移 / 風 instead)' % (name_ja, s))
                    continue
                if self.mode == 'mech' and s == 6 and ph0 is not None and ph0['shake']['where'] == 0:
                    # T 2026-11-11 (SHAKE0): ｽﾌﾟﾗｲﾄ：振動 is 甲's own wobble; the BFE phase has 振動させる個所 0 (なし,
                    # phase +0x144) -> no vibration. With a BFE 振動 (初回 / 着地時 / 弾発射時) the template's is kept
                    # (the BFE scale / stop units are not mapped).
                    self.rep.add('SHAKE0', '%s: template slot 6 ｽﾌﾟﾗｲﾄ：振動 dropped (BFE 振動させる個所 0)' % name_ja)
                    continue
                if self.mode == 'mech' and s == 54 and ph0 is not None and ph0['events'] and \
                        all(e['flags'] & 1 for e in ph0['events']):
                    # T 2026-11-11 (SHADOW): 影の濃さ from 甲; every BFE event of the phase draws the shadow (spr flag 影)
                    # -> the DiveX default shadow, template value dropped.
                    self.rep.add('SHADOW', '%s: template slot 54 影の濃さ dropped (BFE 影 on every event)' % name_ja)
                    continue
                for o in u['skillInfoObjectList']:
                    if self.mode == 'mech' and s == 47 and not (o.get('int2') == 3 and o.get('int4') == 3):
                        # HITCANCEL (調査記録 20): 甲's own cancel timing (0/1/2 = [+0x1900], at 甲's fire / hit frames) is
                        # replaced by the BFE rule (hit +0x64, phase flags, fire); only the value-3 キャンセル操作 window stays
                        self.rep.add('HITCANCEL', 'template slot 47 F%d-%d (%s -> %s) dropped (甲 timing; BFE rule instead)' % (
                            o['startFrame'], o['endFrame'], o.get('int2'), o.get('int4')))
                        continue
                    o = copy.deepcopy(o); o['offset'] = 0
                    o['startFrame'] = min(L - 1, round(o['startFrame'] * f)); o['endFrame'] = min(max(L - 1, o['startFrame']), round(o['endFrame'] * f))
                    if self.mode == 'mech' and s == 33 and o.get('int1', 0) > 0:
                        # M 2026-10-29 (SLIP): 技後の慣性補正 with a minimum 上昇量 > 0 forces the mech upward after the
                        # skill (甲 JK F13 (2,8,3,4,0,0): 透 rose off-screen after the JK hit, BSX問題の近接技.mp4; 甲 BU
                        # (3,4,2,2,20,20): 透 hovered ~30F after ブーストアッパー, 移植版2-2 F146-173). 甲 only lets them act
                        # inside a landing wait (BU T0 F36-159, JK F23-43); BFE's free mech has no upward term (only
                        # the base gravity block, 0x420be0) -> the vanilla end-of-skill value (0,8,0,6,0,99999).
                        # M 2026-10-31: slot 33 acts only when a skill starts while this one runs (0x61c980 ->
                        # 0x618150) or on the cancel input (0x61c790), never on the natural end (see _post_apex), so
                        # SLIP only concerns cancels; the post-skill rise is POSTAPEX.
                        self.rep.add('SLIP', 'mech slot 33 F%d (%s,%s,%s,%s,%s,%s) -> (0,8,0,6,0,99999)' % (
                            o['startFrame'], o.get('long1'), o.get('long2'), o.get('int1'), o.get('int2'), o.get('int3'), o.get('int4')))
                        o.update(long1=0, long2=8, int1=0, int2=6, int3=0, int4=99999)
                    if o['endFrame'] < o['startFrame']:
                        o['endFrame'] = o['startFrame']
                    ev[s].append(o)
                self.rep.add('TEMPLATE', '%s slot %d copied from template turn 0' % (self.mode, s))

    def _fc_at(self, tpl, turns, ti, name_ja=''):
        # E 2026-11-08 (FCPHASE, user メガブーストキック 「必殺演出は飛び上がった後、技の開始時に出ている（他の FC も）」, 原作 FC 0:26):
        # BFE フェーズ flag bit5 「スペシャル技演出」 (ﾒｶﾞ･ﾌﾞｰｽﾄｷｯｸ / 貫壁 ph1 164, ﾒｶﾞﾏｲﾝ ph1 160) is where the FC presentation
        # starts. The 甲 template's screen slots (59-68) were copied from its turn 0 onto our turn 0 (the skill start), or
        # dropped when the template keeps them later (甲 メガブーストキック T3). -> the first template turn that has them,
        # time-scaled, at the BFE flagged phase's turn.
        src = None
        for tt in tpl['phasesInfo']:
            if any(u['unitQuantity'] in self.FCSLOTS and u['skillInfoObjectList'] for u in tt['skillUnitCollection']):
                src = tt; break
        if src is None:
            return
        tl = max([o['endFrame'] for u in src['skillUnitCollection'] for o in u['skillInfoObjectList']] + [1]) + 1
        ev, L, _m = turns[ti]
        f = L / float(tl)
        for u in src['skillUnitCollection']:
            if u['unitQuantity'] in self.FCSLOTS:
                for o in u['skillInfoObjectList']:
                    o = copy.deepcopy(o); o['offset'] = 0
                    o['startFrame'] = min(L - 1, int(round(o['startFrame'] * f)))
                    o['endFrame'] = max(o['startFrame'], min(L - 1, int(round(o['endFrame'] * f))))
                    ev[u['unitQuantity']].append(o)
        self.rep.add('FCPHASE', '%s: FC screen slots from the template turn with them -> turn %d (BFE スペシャル技演出 phase)' % (name_ja, ti))
        # E 2026-11-09 (FCSTOP, user 「BSX の FC は演出中にスロー・時間停止、移植版の多くはそうなっていない」): BaldrForce.exe
        # 0x443d45 -> 0x443fd0: on a スペシャル技演出 phase the mech gets +0x1c4 = 1 and the global 0x4e0626 is raised;
        # 0x420a00 then returns 0 ticks for the world (everything but the FC user stops) until the phase ends (0x443d66
        # clears it). DiveX 画面停止 (slot 68, vanilla 甲 メガブーストキック T3 F0-102 / ギガンテックフィールド T0 F0-45) does the
        # same; ours kept only the template's partial span (or none when its first presentation turn has no 68)
        # -> slot 68 over the whole flagged turn.
        smp = None
        for tt in tpl['phasesInfo']:
            for u in tt['skillUnitCollection']:
                if u['unitQuantity'] == 68 and u['skillInfoObjectList']:
                    smp = u['skillInfoObjectList'][0]; break
            if smp is not None:
                break
        if smp is None and (68, 0) in self.lib.ev:
            smp = self.lib.ev[(68, 0)]
        if smp is not None:
            o = copy.deepcopy(smp); o['offset'] = 0; o['startFrame'], o['endFrame'] = 0, L - 1
            ev[68] = [o]
            self.rep.add('FCSTOP', '%s: 画面停止 (slot 68) over the スペシャル技演出 turn %d (F0-%d, BFE world stop 0x420a00)' % (name_ja, ti, L - 1))

    @staticmethod
    def _hit_valid(h):
        return h['hits_mech'] not in (0, 254) and h['power'] > 0 and not h['flags'] & 0x20

    def _rep_setup(self, bs, bullet):
        """G 2026-11-03 (REPDECAY): how many bullets of each Tama one firing (technique or bullet) shoots: fire loops x
        同時発射数 summed over its phases -> fx.fire_reps[t] (max over the firings converted so far; a technique / bullet
        registers before its bullets are converted, nested). _set_hit gives a 1-hit bullet the per-hit decay (技のみ) when one firing shoots it twice or more."""
        fx = self.fx
        if fx is None:
            return
        reg = getattr(fx, 'fire_reps', None)
        if reg is None:
            reg = {}
            try:
                fx.fire_reps = reg
            except AttributeError:
                return
        cnt = collections.Counter()
        for ph_ in bs['phases']:
            f_ = ph_['fire']
            if f_['tama'] >= 0:
                cnt[f_['tama']] += max(1, f_['loops']) * max(1, f_['count'][0])
        for t_, n_ in cnt.items():
            reg[t_] = max(reg.get(t_, 0), n_)

    def _combo_setup(self, bs, kind, bullet, name_ja):
        """N COMBOCLS: technique-level (近接?, max BFE ｺﾝﾎﾞ補正) for the hits converted from <bs>. A mech technique
        registers itself for every Tama it fires (fx.chain); a bullet uses the registration of the first technique that
        fired it, else its own Tama chain / 技タイプ (reported)."""
        fx = self.fx
        reg = getattr(fx, 'combo_owner', None) if fx is not None else None
        if fx is not None and reg is None:
            reg = {}
            try:
                fx.combo_owner = reg
            except AttributeError:
                reg = None
        tamas = set()
        if fx is not None and hasattr(fx, 'chain'):
            for ph_ in bs['phases']:
                tamas |= fx.chain(ph_['fire']['tama'])
        def size(own):
            cs = [p_['hit']['combo_corr'] for p_ in own['phases'] if self._hit_valid(p_['hit'])]
            for t_ in tamas:
                cs += [p_['hit']['combo_corr'] for p_ in fx.tama[t_]['phases'] if self._hit_valid(p_['hit'])]
            return max(cs) if cs else 0

        def size_sum(own):
            # COMBOV3 (user 2026-11-10, tools/bfe2bsdx_combo_v3.py): sum of BFE ｺﾝﾎﾞ補正 over the technique's distinct
            # (威力, 最低威力, ｺﾝﾎﾞ補正) vs-mech hits, its own phases and the Tama it fires (BU 125 + 75 = 200)
            hs_ = [p_['hit'] for p_ in own['phases'] if self._hit_valid(p_['hit'])]
            for t_ in tamas:
                hs_ += [p_['hit'] for p_ in fx.tama[t_]['phases'] if self._hit_valid(p_['hit'])]
            set_ = sorted({(h_['power'], h_['min_power'], h_['combo_corr']) for h_ in hs_})
            self.rep.add('COMBOV3', '%s: BFE ヒット (威力, 最低, ｺﾝﾎﾞ補正) %s -> 合計 %d' % (
                name_ja, ' '.join('(%d,%d,%d)' % t_ for t_ in set_), sum(c_ for _, _, c_ in set_)))
            return sum(c_ for _, _, c_ in set_)
        if not bullet:
            self._combo_tech = (kind == 0, size(bs), name_ja, size_sum(bs))
            if reg is not None:
                for t_ in tamas:
                    reg.setdefault(t_, self._combo_tech)
        else:
            ti = bs.get('index')
            got = reg.get(ti) if reg is not None else None
            if got is None:
                got = (kind == 0, size(bs), name_ja, size_sum(bs))
                self.rep.add('COMBOCLS', 'bullet %s: no firing technique registered -> own 技タイプ %d / chain max ｺﾝﾎﾞ補正 %d' % (
                    name_ja, kind, got[1]))
            self._combo_tech = got

    def _set_hit(self, tp, hi, nk, hs, he, hits, weapon=False, cancel=False, bfe_iv=False, src_ti=None):
        tp['startFrame'], tp['endFrame'], tp['offset'] = hs, he, 0
        tp.pop('_bal', None)                  # ROLEMIN: a copied hit must not keep another hit's balanced value
        if not weapon:
            self._element(tp, hi)             # ELEMENT (調査記録 53)
        # HITCANCEL (調査記録 20): CEventHit +0x64 (JSON selfStunFrame; exe property 「キャンセルフラグ」, read 0x63b6cc) == 1 ->
        # the owner's cancel state [+0x1900] = 1 at the hit (0x646edc), else 2 (no cancel). 1 for a 打撃 hit on mechs (BFE
        # sets its flag only when a mech is hit, 0x4416cc); slot 42 (vs bullets) -> 0. cancel: explicit (line chains) or
        # convert() (from the BFE 技タイプ).
        cancel = bool(cancel)
        c64_old = tp.get('selfStunFrame')
        tp['selfStunFrame'] = 1 if (cancel and not weapon) else 0
        self.rep.add('HITCANCEL', '%s hit F%d-%d: キャンセルフラグ(+0x64) tpl %s -> %d (%s)' % (
            'bullet' if self.mode != 'mech' else 'mech', hs, he, c64_old, tp['selfStunFrame'],
            '対弾' if weapon else ('打撃: ヒットでキャンセル可' if cancel else '射撃/打撃以外: ヒットでは不可')))
        tp['hitCount'] = -1 if hits >= 255 else hits
        iv_old = tp.get('hitInterval')
        if bfe_iv and self.mode != 'mech' and hits != 1:
            # S 2026-11-01 (HITIV): BFE re-hit wait of an object = HIT規模 (hit +0xB): after a tick with a hit the
            # attacker's +0x2d2 = HIT規模 (0x441482-0x441497), decremented each tick without a hit (0x44148b-0x441495);
            # while > 0 an overlap does not hit (0x442cec-0x442d10) -> one hit per (HIT規模+1) ticks = 2*(HIT規模+1) F.
            # DiveX: per attacker x target record, timer = hitInterval (+0x1c) at the hit (0x648a90 / 0x648fe7 /
            # 0x64941a), -1 per frame (0x609af3 from 0x60d55d), > 0 = skip (0x6486ca). The old 6F (or the template
            # value) let each 火炎放射器 flame (HIT規模 5 = 12F) hit twice as often (6.mp4: 115/118 HIT vs 原作 12.mp4 36-54).
            # Bullets only: a mech hit also freezes the attacker for its hitstop (BFE 0x444560), DiveX's interplay of
            # hitstop and the record timer is not checked (mech multi-hits: ﾄﾞﾘﾙ / ﾒｶﾞ･ﾌﾞｰｽﾄｱｯﾊﾟｰ keep the old rule).
            # Not modelled: flag bit4 HIT規模を全弾更新 (0x4497e5: the wait is copied to the sibling bullets).
            # Only mech hits arm the wait (0x441465 tests the tick's mech-hit count; bullet hits count in byte +1, 0x44132f)
            # -> vs bullets (slot 42) one hit per tick = 2F. Line chains (bfe2bsdx_line._hits, bfe_iv False) keep their rule.
            tp['hitInterval'] = 2 if weapon else 2 * (hi['hit_scale'] + 1)
            self.rep.add('HITIV', 'bullet hit (%s, hits %s): hitInterval tpl %s -> %d (BFE HIT規模 %d: 1 hit / %d ticks)%s' % (
                '対弾' if weapon else '対メカ', 'unlimited' if hits >= 255 else hits, iv_old, tp['hitInterval'], hi['hit_scale'],
                1 if weapon else hi['hit_scale'] + 1, ' [HIT規模を全弾更新 not modelled]' if hi['flags'] & 0x10 else ''))
        elif hits >= 255 and not tp.get('hitInterval'):
            tp['hitInterval'] = 6
        elif hits == 1:
            tp['hitInterval'] = 0
        elif 1 < hits < 255 and not tp.get('hitInterval'):
            tp['hitInterval'] = max(2, (he - hs + 1) // hits)
        min_old = tp.get('minDamage')
        tp['minDamage'] = max(1, hi['min_power'] // 4)
        if not weapon:
            # N 2026-10-30 (調査記録 18 §N, MINDMG): BaldrSky.exe 0x63ba40 (typeList 0 = 直値): base x150/100 when the
            # attacker's owner mech ([hit src +0x14c4], the one whose +0x154 holds the combo state) is player-controlled
            # (vf 0x158 = spawn flags bit 2, set at 0x629398 with the player index) and its MekaGroup id (+0x18a4, from
            # spawn +0x2c at 0x61bc71) != 0 (甲); then x rate/100; THEN max(d, 最低値 +0x20) -- the floor is not x1.5.
            # 透 = MekaGroup 10 as the player -> display = floor(威力 x1.5) (移植版3 BU 187 = 125x1.5, DD 262 = 175x1.5)
            # but floor = raw (移植版4 DD 2nd hit 50 = BFE 200/4). BFE 0x442340 floors in the same unit as 威力, so the
            # floor gets the same x1.5: 最低値 = BFE x3/8. (Player use assumed, like the combo x3/4.)
            tp['minDamage'] = max(1, round(hi['min_power'] * 3 / 8))
            self.rep.add('MINDMG', '最低値 tpl %s -> %d (BFE %d x3/8 = /4 x1.5: DiveX は非甲の自機の威力だけ x1.5、最低値は素のまま 0x63bb1a/0x63bb51)' % (
                min_old, tp['minDamage'], hi['min_power']))
            # B 2026-11-04 (ROLEMIN): see role_min / ROLE_C above; modified/ value kept aside in '_bal'.
            # COMBOV3 (user 2026-11-10「最低威力：単純変換を移植版」): the faithful pack keeps the x3/8 above on every hit
            # (ROLEMIN with ROLE_G is no longer applied to 3b). modified/ starts from ROLEMIN ROLE_G_MOD (kept for hits
            # outside the COMBOV3 scopes: FC etc.); in-scope techniques get their own rule below.
            tp['_bal'] = {'minDamage': role_min(hi['power'], hi['min_power'], ROLE_G_MOD)}
            self.rep.add('ROLEMIN', '最低値 %d (3b: BFE 最低 %d x3/8, ROLEMIN 不使用 COMBOV3); 改善版 ROLEMIN x%g -> %d (BFE 威力 %d, 表示 %d)' % (
                tp['minDamage'], hi['min_power'], ROLE_G_MOD, tp['_bal']['minDamage'], hi['power'],
                int(max(1, round(hi['power'] / 4)) * 1.5)))
        # ヒットカウンタ初期化 = 1: BFE counts hits per phase (obj+0x2ce / phase +0xa2, 0x44435f); the vanilla turn that
        # follows a 「残りメカＨＩＴ数」 jump resets it in 60 of 67 cases. Kou's 2nd/3rd hit objects carry 0, so a
        # converted hit in a later turn (ブーストアッパー 2段目) could not hit the already-hit target.
        int1_old, combo_old, mid_old = tp.get('int1'), tp.get('startComboCorrection'), tp.get('midComboCorrection')
        tp['int1'] = 1
        if not weapon:
            # N 2026-10-29 (調査記録 17 §N, COMBO): BFE has ONE accumulator. 0x442340: dmg = max(威力 - combo*P/10, 最低威力),
            # then combo += ｺﾝﾎﾞ補正 on every hit (x3/4 branch 0x442440; 原作11/11-2 player -> CPU fit exactly with x3/4,
            # display = dmg / 20.8 = % of a 2080 gauge). BaldrSky.exe: 攻撃力補正 (mid, +0x34) is added on every hit
            # (0x6061e5) = BFE's accumulator; 基底 (+0x2c) is stored for the combo's first hit only (0x6061fb) and merged
            # with 技終了時 (+0x38) when that technique ends (0x604dc0/0x604e2b) -> the 10/28 rule (基底 = mid = /10)
            # counted the first hit twice (移植版1: ジャブ after BU at 100-39 % = 12+12+8+7). Vanilla sets both on 7 of
            # 1276 hits. Rule: 基底 0; mid = BFE absolute loss (x3/4, BSDX power = BFE/4) as % of a 100-power BSDX hit
            # = ｺﾝﾎﾞ補正 x3/16, vanilla mid range 0..50.
            # (superseded 2026-11-01 by COMBOCLS below; kept as history)
            # N 2026-11-01 (COMBOCLS, user 11/01 23:29): the proportional rule (基底 0, mid = ｺﾝﾎﾞ補正 x3/16, 終了時 0) is
            # replaced by the 甲 class of the technique (COMBO_CLASS): 基底 (+0x2c, combo's first hit only 0x6061fb),
            # 攻撃力補正 (+0x34, every hit 0x6061e5), 技終了時 (+0x38, once when the technique ends 0x604460/0x604e2b).
            melee_, tsize_, tname_, ssum_ = getattr(self, '_combo_tech', None) or (True, hi['combo_corr'], '?', hi['combo_corr'])
            if src_ti is not None and getattr(self.fx, 'combo_owner', None) and src_ti in self.fx.combo_owner:
                melee_, tsize_, tname_, ssum_ = self.fx.combo_owner[src_ti]
            if '_bal' in tp:                  # B 11/05: per-weapon overrides of modified/ (bfe2bsdx_balance.OVERRIDES) need the owner
                tp['_bal'].update(tech=tname_, bfe=[hi['power'], hi['min_power']])
            cls_, (st_, md_, en_) = combo_class(melee_, tsize_)
            # COMBOV3 (user 2026-11-10, tools/bfe2bsdx_combo_v3.py, 調査記録 38): 格闘・武器の通常技 (mek No 0-31) in both packs:
            # 初段 = min(40, BFE ｺﾝﾎﾞ補正の合計 / 10), 攻撃力 0, 技終了時 0 (パンチ / 原作で初段向き) or 7; never negative.
            # modified/ only: 初段 cap 10 for 原作で初段向き (BU 20 -> 10); 最低値 by B4 Δ (60/30/10 %) or MOD_MIN_SET.
            # 射撃の通常技 (No 32-65): 3b keeps COMBOCLS; modified/ gets 初段 (same rule) / 技終了時 0 or 20 / 最低値 SHOT_MIN.
            CV3 = self.cv3
            if CV3 is not None and CV3.in_scope(tname_):
                st0_ = st_
                st_, md_, en_ = CV3.start_corr(ssum_), 0, CV3.end_corr(tname_)
                if '_bal' in tp:
                    tp['_bal'].update(v3='melee', startComboCorrection=CV3.start_corr_mod(tname_, st_),
                                      min_ratio=CV3.min_ratio_mod(tname_, hi['power'], hi['min_power']))
                self.rep.add('COMBOV3', '格闘 %s: BFE ｺﾝﾎﾞ補正合計 %d -> 初段/攻撃力/終了時 %d/%d/%d (COMBOCLS %d/%d/%d); OPENER %s LATE %s; '
                             '改善版 初段 %s 最低値比 %s (BFE 威力 %d / 最低 %d)' % (
                    tname_, ssum_, st_, md_, en_, st0_, combo_class(melee_, tsize_)[1][1], combo_class(melee_, tsize_)[1][2],
                    CV3.OPENER.get(tname_), CV3.LATE.get(tname_), tp.get('_bal', {}).get('startComboCorrection'),
                    tp.get('_bal', {}).get('min_ratio'), hi['power'], hi['min_power']))
            elif CV3 is not None and CV3.shot_in_scope(tname_) and '_bal' in tp:
                st_m_ = st_ if CV3.SHOT_EXPECT[tname_][0] is None else CV3.shot_start_corr_mod(tname_, ssum_)
                tp['_bal'].update(v3='shot', startComboCorrection=st_m_, endCorrection=CV3.shot_end_corr_mod(tname_),
                                  min_ratio=CV3.SHOT_MIN[tname_])
                self.rep.add('COMBOV3', '射撃 %s (改善版のみ): BFE ｺﾝﾎﾞ補正合計 %d -> 初段 %d -> %d, 終了時 %d -> %d, 最低値比 %g; OPENER %s' % (
                    tname_, ssum_, st_, st_m_, en_, tp['_bal']['endCorrection'], CV3.SHOT_MIN[tname_], CV3.SHOT_OPENER.get(tname_)))
            tp['startComboCorrection'], tp['midComboCorrection'] = st_, md_
            int_old, end_old = tp.get('internalCorrection'), tp.get('endCorrection')
            tp['internalCorrection'], tp['endCorrection'] = 0, en_
            # N 2026-11-01 (SELFDECAY): a hit that re-hits the same target (hits != 1) loses c*3//4 per hit against ITS
            # OWN 威力 in BFE (0x442340; 原作12 火炎放射器 45-k per hit fits all 12 readings). BaldrSky.exe: 技のみ
            # (+0x30) is added per hit to the record of the technique (key = src +0x1680 = parent technique id, inherited by
            # bullets 0x614a2a/0x61574a; 0x604531), counted in the rate (0x61ec39-0x61ec60) and cleared at the owner's
            # technique change (0x618270 -> 0x6059f0 -> 0x6040d0) -> per-hit decay inside the technique = mid + 技のみ.
            if hits != 1 and hi['power'] > 0:
                s_ = round(100 * (hi['combo_corr'] * 3 // 4) / hi['power'])
                tp['internalCorrection'] = max(0, min(50, s_ - tp['midComboCorrection']))
                if tp['internalCorrection']:
                    self.rep.add('SELFDECAY', '多段ヒット (hits %s): 技のみ 0 -> %d (BFE 威力 %d, ｺﾝﾎﾞ補正 %d: 1 ヒット %d = %d %% of 威力, - mid %d)' % (
                        'unlimited' if hits >= 255 else hits, tp['internalCorrection'], hi['power'], hi['combo_corr'],
                        hi['combo_corr'] * 3 // 4, s_, tp['midComboCorrection']))
            # G 2026-11-03 (REPDECAY, 調査記録 26 §G2): BFE 0x442340 keeps ONE accumulator per victim, combo += c*3//4 after
            # every hit whatever object made it -> a 1-hit bullet shot N times by one technique (ガトリング砲 x40x3: 威力
            # 50, c 3 -> 50, 48, 46 ... 最低 1) decays like a multi-hit one. DiveX keeps 技のみ per technique record (key =
            # parent technique id, inherited by every bullet: 0x614a2a/0x61574a -> 0x604531), so the same SELFDECAY value
            # on the repeated bullet gives the same per-hit slope. Data decides who decays: c*3//4 = 0 for c <= 1
            # (ガトリング T-150 の Lv2 弾 15/c1, ショットガン, ジェノサイド: no decay, 原作 7.mp4 T-150 84 HIT 60 DAM = 84 x 15
            # / 20.8 exactly); ダブルSMG 40/c2 -> 1 per hit (2.5 %).
            elif hits == 1 and hi['power'] > 0 and self.mode != 'mech' and src_ti is None and \
                    (getattr(self.fx, 'fire_reps', None) or {}).get(getattr(self, '_rep_ti', None), 0) >= 2:
                s_ = round(100 * (hi['combo_corr'] * 3 // 4) / hi['power'])
                tp['internalCorrection'] = max(0, min(50, s_ - tp['midComboCorrection']))
                if tp['internalCorrection']:
                    self.rep.add('REPDECAY', '連射弾 (1 ヒット x %d 発/技): 技のみ 0 -> %d (BFE 威力 %d, ｺﾝﾎﾞ補正 %d: 1 ヒット %d = %d %% of 威力, - mid %d)' % (
                        self.fx.fire_reps[self._rep_ti], tp['internalCorrection'], hi['power'], hi['combo_corr'],
                        hi['combo_corr'] * 3 // 4, s_, tp['midComboCorrection']))
            self.rep.add('COMBOCLS', '%s %s: 技の最大ｺﾝﾎﾞ補正 %d -> 甲%sクラス %d = 基底/攻撃力/終了時 %d/%d/%d' % (
                '近接' if melee_ else '射撃', tname_, tsize_, '近接' if melee_ else '射撃', cls_, st_, md_, en_))
            self.rep.add('COMBO', 'コンボ補正 基底/攻撃力/技のみ/技終了時 tpl %s/%s/%s/%s -> %d/%d/%d/%d (甲クラス、ヒットのｺﾝﾎﾞ補正 %d)' % (
                combo_old, mid_old, int_old, end_old, st_, md_, tp['internalCorrection'], en_, hi['combo_corr']))
        if not weapon:
            tp['int15'] = tp['int16'] = max(6 if self.mode == 'mech' else 0, hi['hit_wait'] * 2)
        # provenance only (調査記録 15): what the hit rules produced vs the 甲 template value
        self.rep.add('HIT', '%s hit F%d-%d: 威力 BFE %d -> %d (/4), 最低値 BFE %d -> %d (%s), hits %s, ヒットカウンタ初期化 tpl %s -> 1%s' % (
            'bullet' if weapon else 'mech', hs, he, hi['power'], max(1, round(hi['power'] / 4)), hi['min_power'], tp['minDamage'],
            '/4' if weapon else 'x3/8',
            tp['hitCount'], int1_old, '' if weapon else ', 初撃コンボ補正 tpl %s -> %s (甲クラス), 通常コンボ補正 tpl %s -> %s (甲クラス, BFE %d)' % (
                combo_old, tp['startComboCorrection'], mid_old, tp['midComboCorrection'], hi['combo_corr'])))
        for u in tp['ceventHitUnitList']:
            if u['unitSlotNum'] == 6:
                b = u['data']['bsdxInfoCollectionList'][0]; b['typeList'] = [0]; b['paramList'] = [max(1, round(hi['power'] / 4))]
                u['data']['startFrame'] = u['data']['endFrame'] = 0
            elif u['unitSlotNum'] == 28 and not weapon:
                se = self.se.get(hi['se'])
                if se:
                    u['data']['byteDataList'] = [i32list(se[0], se[1], 100, 1)]; u['data']['count'] = 1
            elif u['unitSlotNum'] == 16 and u.get('data') and self.fx:
                eff = hi['effect_weapon' if weapon else 'effect_mech']['effect_no']
                tgt = self.fx.effect_target(eff) if eff >= 0 else None
                for d in walk(u['data']):
                    if 'wazFileNo' in d and tgt:
                        d['wazFileNo'], d['wazSequenceNo'] = tgt
                if eff >= 0 and not tgt:
                    self.rep.add('APPROX', 'hit effect type %d has no anim -> template hit effect kept' % eff)
                if eff < 0:
                    u['_drop'] = True
            elif u['unitSlotNum'] in (17, 18) and not weapon and u.get('data') and \
                    (u['unitSlotNum'] == 17 or u['data'].get('int1') == 0):
                b4 = {k: u['data'].get(k) for k in ('int8', 'int9', 'int10')}
                b4h = {k: u['data'].get(k) for k in ('int3', 'int4')}
                self._set_noke(u['data'], dict(nk, _multi=hi['hits_mech'] > 1))      # 17 地上, 18 空中 (only when it is an explicit 指定 entry)
                af = {k: u['data'].get(k) for k in ('int8', 'int9', 'int10')}
                self.rep.add('NOKE', '%s のけぞり 速度/減速/吹き飛び規模 tpl %s/%s/%s -> %s/%s/%s (BFE v %d step %d launch %d accum %d)' % (
                    '地上' if u['unitSlotNum'] == 17 else '空中', b4['int8'], b4['int9'], b4['int10'], af['int8'], af['int9'], af['int10'],
                    nk['speed_init'], nk['speed_step'], nk['launch'], nk['launch_accum']))
                sk_ = u['data'].pop('_slamkeep', None)
                if sk_:
                    self.rep.add('SLAMKEEP', '%s のけぞり: BFE 規模 %d (小さい浮き) -> 甲テンプレの叩きつけ 規模/重力 %s/%s を維持' % (
                        '地上' if u['unitSlotNum'] == 17 else '空中', nk['launch'], sk_[0], sk_[1]))
                nf_ = u['data'].pop('_nokefloat', None)
                if nf_:
                    self.rep.add('NOKEFLOAT', '%s のけぞり ﾋｯﾄﾊﾞｯｸ tpl %s/%s -> %s/%s (BFE のけぞり回数 0 = ダウンしない浮き: 滞空 %dF の半分, 規模/重力 %s/%s)' % (
                        '地上' if u['unitSlotNum'] == 17 else '空中', nf_[0][0], nf_[0][1], nf_[1][0], nf_[1][1],
                        int(80.0 * nf_[2] / nf_[3]), nf_[2], nf_[3]))
                elif nk['launch_accum'] >= 100 and nk['launch'] > 0:
                    self.rep.add('NOKEDOWN', '%s のけぞり ﾋｯﾄﾊﾞｯｸ tpl %s/%s -> %s/%s (2 x 滞空 80*規模/重力, 着地でダウン)' % (
                        '地上' if u['unitSlotNum'] == 17 else '空中', b4h['int3'], b4h['int4'], u['data'].get('int3'), u['data'].get('int4')))
                    self.rep.add('LAUNCH', '%s 吹き飛び 規模/重力 -> %s/%s (BFE launch %d, BFE g %d: apex/airtime fit, DiveX g /200 0x5f4be0)' % (
                        '地上' if u['unitSlotNum'] == 17 else '空中', u['data'].get('int10'), u['data'].get('int11'),
                        nk['launch'], BFE_LAUNCH_G))
        # T 2026-11-11 (HITFX0, user 「ヒットエフェクトの-1」→ 進めて): BFE ヒットエフェクト -1 = no hit spark. 原作動画
        # (通常武装.mp4 1:55, 多弾頭ミサイルポッド ~10 hits at 20 fps) shows only the missile's own blast, never the star spark
        # of melee hits. Before, the 甲 template's slot 16 stayed (甲 spark on top of every explosion / flame). DiveX has
        # no -1 value; vanilla expresses 「none」 by leaving slot 16 out (Bomb 爆風 / 機体爆発, Tama05 火炎放射器の炎：甲,
        # 手榴弾, Tama03 レーザービット: 517 of 2020 hits in the 8 waz) -> drop the sub.
        if any(u.get('_drop') for u in tp['ceventHitUnitList']):
            tp['ceventHitUnitList'] = [u for u in tp['ceventHitUnitList'] if not u.pop('_drop', False)]
            self.rep.add('HITFX0', '%s hit F%d-%d: BFE ヒットエフェクト -1 -> 甲 template hit effect dropped' % (
                'bullet' if weapon else 'mech', hs, he))
        # G 2026-11-04 (NOKESAME, user: BU 「敵の吹き飛びが低すぎる」): のけぞり 処理タイプ 1-4 「同じ:…」 does NOT redirect at
        # run time - BaldrSky.exe 0x616690 picks the sub of the victim's state (+0x54/+0x58/+0x5c/+0x60) and reads its own
        # 規模/重力 (+0x74/+0x78). Vanilla keeps every 「同じ」 sub a copy of its target (3675 of 3675 in the 11 waz). Only 17 was
        # rewritten here, so a hit on an airborne enemy used the 甲 template's 空中 40/100 (BU 2nd hit: 32 px / 32F seen).
        subs_ = {u['unitSlotNum']: u['data'] for u in tp['ceventHitUnitList'] if u['unitSlotNum'] in (17, 18, 19, 20) and u.get('data')}
        for sn_, d_ in sorted(subs_.items()):
            ref_ = subs_.get(16 + d_.get('int1', 0)) if d_.get('int1') in (1, 2, 3, 4) else None
            if ref_ is not None and ref_ is not d_ and ref_.get('int1') in (0, None):
                ch_ = [k for k in ref_ if k.startswith('int') and k != 'int1' and d_.get(k) != ref_[k]]
                for k in ch_:
                    d_[k] = ref_[k]
                if ch_:
                    self.rep.add('NOKESAME', 'のけぞり %d 処理タイプ %d -> %d の値をコピー (%s)' % (sn_, d_['int1'], 16 + d_['int1'], ','.join(ch_)))
        # G 2026-11-04 (NOKEDOWNHIT): BFE 規模(ダウン時) (noke +0x0D) is the launch used on a victim that is down; the
        # ダウン sub 20 is a copy of 17 after NOKESAME. When it differs (対空ｽﾌﾟﾚｯﾄﾞﾎﾞﾑ 0: a downed enemy stays down), sub 20
        # becomes an explicit entry (処理タイプ 0) with the launch from 規模(ダウン時).
        if not weapon and nk.get('launch_down') is not None and nk['launch_accum'] >= 100 and nk['launch_down'] != nk['launch']:
            s20_ = subs_.get(20); s17_ = subs_.get(17)
            if s20_ is not None and s17_ is not None and s20_.get('int1') in (1, 2, 3, 4) and s17_.get('int1') in (0, None):
                b20_ = (s20_.get('int10'), s20_.get('int11'))
                s20_['int1'] = 0
                self._set_noke(s20_, dict(nk, launch=nk['launch_down']))
                s20_.pop('_nokefloat', None); s20_.pop('_slamkeep', None)
                if nk['launch_down'] <= 0:
                    s20_['int10'] = 0
                self.rep.add('NOKEDOWNHIT', 'のけぞり 20 ダウン: 処理タイプ 同じ -> 指定, 規模/重力 %s/%s -> %s/%s (BFE 規模(ダウン時) %d, 通常 %d)' % (
                    b20_[0], b20_[1], s20_.get('int10'), s20_.get('int11'), nk['launch_down'], nk['launch']))
        # R 2026-11-15 (NOKEDOWNHIT2, user 「ケイジブレイドの剣の部分・サテライトレーザーの爆風は、相手がダウン状態でも上に吹き
        # 飛ぶはずが、吹き飛ばない」): when the template's ダウン sub 20 is an explicit entry (処理タイプ 0, the 甲 bullet
        # templates: 20/40, 規模 0 = a downed enemy is not lifted), neither NOKESAME nor the rule above touched it, so BFE
        # 規模(ダウン時) was lost (地面から突き出る剣 5, ｻﾃﾗｲﾄﾚｰｻﾞｰ 爆発 5). -> the same conversion as sub 17 with launch =
        # 規模(ダウン時) (0 or less: no lift).
        if not weapon and nk.get('launch_down') is not None and nk['launch_accum'] >= 100:
            s20_ = subs_.get(20)
            if s20_ is not None and s20_.get('int1') in (0, None) and not s20_.get('_downhit'):
                b20_ = (s20_.get('int10'), s20_.get('int11'))
                self._set_noke(s20_, dict(nk, launch=nk['launch_down'], _multi=hi['hits_mech'] > 1))
                s20_.pop('_nokefloat', None); s20_.pop('_slamkeep', None)
                if nk['launch_down'] <= 0:
                    s20_['int10'] = 0
                if (s20_.get('int10'), s20_.get('int11')) != b20_:
                    self.rep.add('NOKEDOWNHIT2', 'のけぞり 20 ダウン (指定): 規模/重力 %s/%s -> %s/%s (BFE 規模(ダウン時) %d)' % (
                        b20_[0], b20_[1], s20_.get('int10'), s20_.get('int11'), nk['launch_down']))
        # G 2026-11-04 (NOKEDIR, user 20261103_4 #5 「拡散後、敵はほぼ真上にのけぞり続けるはずが横に吹き飛ばしすぎる」): BFE
        # のけぞり方向 1 「自分→相手」 pushes the victim away from the hitting object (0x441fb0 case 1: 0x40d410 angle from the
        # attacker's position to the victim). The converter kept the 甲 template's 角度指定→スプライト方向, so a still blast
        # pushed along its sprite facing (sideways). Vanilla uses 「オブジェクト位置」 (Term g18 [1], intList4 [9,0] = 最近攻撃
        # してきたOBJ) for that: 707 subs, Bomb.waz 爆風 79 of 131, 真 フォトンブラスター ph1/ph2. Bullets only.
        # A negative BFE speed pulls toward the object (ﾌｫﾄﾝﾌﾞﾗｽﾀｰ ph1 -8 = suction); vanilla 真 フォトンブラスター ph1 has
        # のけぞり速度 -2 / 減速 -20 with the same direction -> keep the sign on int8 and int9.
        # T 2026-11-11 (PULLDECEL, user 「速度減衰率がマイナスなせいで敵がすごい速度で吹き飛ぶ: クォウトワイヤー、リバースフィールド」):
        # the sign goes on int8 only. BaldrSky.exe 0x618e7b / 0x619135: int9 -> victim CMove +0x18 = int9*1024/100;
        # 0x5f5a40 each frame: speed (+0x14) > 0 -> speed -= [+0x18], stop at <= 0; speed < 0 -> speed += [+0x18], stop
        # at >= 0. A negative speed with a negative int9 therefore grows every frame and never stops (-12 px/F -0.25/F:
        # the pulled victim shoots past 透 and away). BFE decelerates the pull to 0 (speed_step = |deceleration|, the
        # converter's v^2/2a rule) -> int9 = +|step*100/1024|. Vanilla 真 フォトンブラスター (-2/-20) is left untouched.
        # R 2026-11-05 (user 対空スプレッド.mp4 「吹き飛ばし方向は進行方向固定なのに、外に弾き飛ばすせいで繋がらない」):
        # only when the hit pushes at all. With BFE speed 0 / -1 (対空ｽﾌﾟﾚｯﾄﾞﾎﾞﾑ ph1/ph2 -> int8 0) there is no horizontal
        # push in BFE and the direction only steered the DiveX 吹き飛び outward -> keep the template's sprite direction
        # (the bullet's travel direction).
        push_ = any((d_.get('int8') or 0) != 0 for sn_, d_ in subs_.items() if sn_ in (17, 18) and d_.get('int1') in (0, None))
        if self.mode != 'mech' and not weapon and nk['direction'] == 1 and not push_:
            self.rep.add('NOKEDIRZERO', 'bullet のけぞり方向 1 自分→相手, のけぞり速度 %d -> int8 0: sprite direction kept (no push in BFE)' % nk['speed_init'])
        elif self.mode != 'mech' and not weapon and nk['direction'] in (2, 3) and nk['speed_init'] < 0 and push_:
            # R 2026-11-05 (NOKEPULL, user 「クウォウトワイヤーで敵が飛ぶ方向も逆」): BFE のけぞり方向 3 「親→相手」 / 2
            # 「自分の移動方向」 with a negative speed pushes against that direction (0x441fb0: angle, speed_init < 0 ->
            # 0x448870 with a negative velocity): ｸｫｳﾄﾜｲﾔｰ：ﾗｲﾝ -24 pulls the victim toward 透. _set_noke took abs(); the
            # wire's sprite direction points from the parent outward (= 親→相手) -> keep the sign on int8 / int9 (vanilla
            # 真 フォトンブラスター ph1 -2 / -20).
            ch_ = []
            for sn_, d_ in sorted(subs_.items()):
                if (d_.get('int8') or 0) > 0:
                    d_['int8'] = -d_['int8']; d_['int9'] = abs(d_.get('int9') or 0); ch_.append(sn_)   # PULLDECEL
            if ch_:
                self.rep.add('NOKEPULL', 'bullet のけぞり方向 %d, 速度 %d < 0 -> int8 負 (引き寄せ), int9 正 (減速, PULLDECEL) on %s' % (nk['direction'], nk['speed_init'], ch_))
        elif self.mode != 'mech' and not weapon and nk['direction'] == 2 and nk.get('_vert') and push_:
            # R 2026-11-08 (NOKEVEC, user 「対空スプレッドボムはどう当てても XZ 平面の上方向に敵がずれる」): BFE のけぞり方向 2 = the
            # bullet's horizontal angle (+0x51c, 0x44201b). The template pushes along the SPRITE direction, and a rising
            # bullet's sprite follows 移動方向 incl. the climb (slot 8 [3,2] = 移動方向（高さ含む）, Term.grp g18) -> tilted toward screen-up = depth on the ground.
            # -> Term g18 [3, 1] 角度指定→移動方向 (no height; vanilla 炸裂弾の弾, 105 uses).
            ch_ = []
            for sn_, d_ in sorted(subs_.items()):
                for x in d_.get('ceventNokezoriUnitList') or []:
                    if x['unitSlotNum'] == 8 and x.get('data') and x['data'].get('bsdxInfoCollectionList'):
                        b = x['data']['bsdxInfoCollectionList'][0]
                        if b['typeList'] == [3, 0] and b['paramList'] == [0, 0]:
                            b['typeList'] = [3, 1]; ch_.append(sn_)
            if ch_:
                self.rep.add('NOKEVEC', 'bullet のけぞり方向 2 on a rising/falling phase -> Term [3,1] on %s' % ch_)
        elif self.mode != 'mech' and not weapon and nk['direction'] == 1:
            ch_ = []
            for sn_, d_ in sorted(subs_.items()):
                for x in d_.get('ceventNokezoriUnitList') or []:
                    if x['unitSlotNum'] == 8 and x.get('data') and x['data'].get('bsdxInfoCollectionList'):
                        b = x['data']['bsdxInfoCollectionList'][0]
                        if b['typeList'] != [1]:
                            b['typeList'] = [1]; b['paramList'] = []; b['intList3'] = [0, 0]; b['intList4'] = [9, 0]
                            ch_.append(sn_)
                if nk['speed_init'] < 0 and d_.get('int8', 0) > 0:
                    d_['int8'] = -d_['int8']; d_['int9'] = abs(d_.get('int9') or 0)   # PULLDECEL
                    ch_.append('%d-' % sn_)
            if ch_:
                self.rep.add('NOKEDIR', 'bullet のけぞり方向 1 自分→相手 -> オブジェクト位置 (vanilla 爆風)%s' % (
                    ', 速度 %d < 0 -> 引き寄せ (int8 負・int9 正 = 減速, PULLDECEL)' % nk['speed_init'] if nk['speed_init'] < 0 else ''))
        for d in walk(tp):
            if 'offset' in d:
                d['offset'] = 0

    SEVOICE_MAX = 10   # overlapping voices of one hit SE from which the per-hit SE is thinned

    def _se_voice(self, tp, hi, hits, name_ja, ti):
        """G 2026-11-03 (SEVOICE, 「スタンロッドの SE が発生後すぐに多重で出る」): BaldrForce.exe plays an SE on ONE sound
        buffer per SE (0x417ce0 -> 0x417c10: buffer [0x534238 + SE*4], SetCurrentPosition 0 (0x40cd90) then Play
        (0x40cdf0)) -> a hit that repeats faster than its SE restarts the same voice, never stacks it. BaldrSky starts a
        new voice for every hit's ヒットＳＥ (Hit sub 28), so 感電 Lv3 (elec07 1.13 s = 68F, a hit every 2F) piled up ~34
        copies. Where length / hitInterval >= SEVOICE_MAX, the sub 28 確率% (CEventSe {SeGroup, 項目, 確率%, 1}, docs/formats/05_waz_field_dictionary.md)
        becomes 200 * interval / length -> about 2 voices on average while the hits continue, still only on hits.
        Scope: bullets with a hit every tick (2F) only."""
        # only bullets hitting every BFE tick (HIT規模 0 -> hitInterval 2F, continuous contact): the worst stacking and no
        # first-impact sound to lose (mech hits and slower multi-hits keep 100%).
        if self.mode == 'mech' or not (hits >= 255 or hits > 1) or tp.get('hitInterval') != 2:
            return
        n = self.se.frames(hi['se']) if hasattr(self.se, 'frames') else None
        iv = tp['hitInterval']
        if not n or n / iv < self.SEVOICE_MAX:
            return
        # 2026-11-17 (user, 調査記録 71): the 確率% thinning (200*iv/n) made the sound random, which BFE never does
        # (it restarts one voice every tick). DiveX cannot restart a voice, so the per-hit SE is dropped instead
        # (user: 「明滅も音の連続も、移植版・modified では無しが最終形」). The bullet's spawn SE (slot 52) still plays once.
        units = tp.get('ceventHitUnitList', [])
        drop = [u for u in units if u['unitSlotNum'] == 28]
        if drop:
            tp['ceventHitUnitList'] = [u for u in units if u['unitSlotNum'] != 28]
            self.rep.add('SEVOICE', '%s turn %d: hit SE %s %.0fF every %dF -> ~%d voices stacked (BFE: 1 voice restarted, 0x417c10) -> hit SE removed (random thinning dropped 11/17)' % (
                name_ja, ti, self.se.name(hi['se']), n, iv, round(n / iv)))

    def _element(self, tp, hi):
        """ELEMENT (user 2026-11-14, 調査記録 53): vs-mech hit フラグ bits 2/4 from the BFE 属性, template 2/4/8/16 dropped."""
        f0, t0 = tp.get('int2', 0), tp.get('int22')
        f = f0 & ~ELEM_MASK
        el = hi['element']
        why = '無'
        if hi['flags'] & 0x20:
            el, why = 0, 'ﾀﾞﾒｰｼﾞ処理をしない（威力 0 で 2F ごと。状態は付けず、技本体の打撃へ）'
        elif el not in ELEM_BITS and self.mode == 'mech' and getattr(self, '_elem_child', 0):
            el, why = self._elem_child, '技が撃つ ﾀﾞﾒｰｼﾞ処理をしない 弾の属性'
        if el in ELEM_BITS:
            b, t, why0 = ELEM_BITS[el]
            f |= b
            if f0 & b and t0:
                t, why = t0, why if why != '無' else why0
                why += '（テンプレの時間 %dF を維持）' % t0
            else:
                why = why0 if why == '無' else why + ' ' + why0
            tp['int22'] = t
        elif el == 2:
            why = '氷（対応なし、ユーザー 11/14）'
            if f0 & 0x06:
                tp['int22'] = ELEM_I22_NONE
        elif f0 & 0x06:
            tp['int22'] = ELEM_I22_NONE
        tp['int2'] = f
        if (f0, t0) != (tp['int2'], tp.get('int22')):
            self.rep.add('ELEMENT', 'BFE 属性 %d: フラグ tpl %d -> %d, int22 tpl %s -> %s (%s)' % (
                hi['element'], f0, f, t0, tp.get('int22'), why))

    def _nodmg_hit(self, tp, hi, pi):
        # W 2026-11-03 (NODMG): a BFE hit with flags bit5 ﾀﾞﾒｰｼﾞ処理をしない (see convert) -> DiveX hit with 威力 0.
        # BaldrSky.exe: the hit effect is spawned whatever the victim's receive result (0x64872c table 0x648b00, all to
        # 0x64877e -> 0x6487c2 -> 0x648170); damage = max(威力 calc, 最低値 +0x20) (0x63bb4f) = 0 -> HP is not touched
        # (0x616de3 jle) and the combo function 0x606120 adds the hit to the combo count / total only when the damage
        # is > 0 (0x606154 jle) - but 攻撃力補正 (+0x34) is added unconditionally (0x6061e5) and 基底 (+0x2c) is stored
        # on the combo's first hit (0x6061fb) -> all four corrections 0. のけぞり 処理タイプ 5 = なし on 17-20 (vanilla
        # 電磁フィールド / 炸裂弾の弾: 5/5/5/5, ヒットストップ 0); ヒットストップ (int15/16) 0; SE / effect stay the BFE ones.
        old = (tp.get('minDamage'), tp.get('startComboCorrection'), tp.get('midComboCorrection'), tp.get('internalCorrection'),
               tp.get('endCorrection'), tp.get('int15'))
        tp['minDamage'] = 0
        tp.pop('_bal', None)                  # ROLEMIN: no balanced value for a 威力 0 hit
        tp['startComboCorrection'] = tp['midComboCorrection'] = tp['internalCorrection'] = tp['endCorrection'] = 0
        tp['int15'] = tp['int16'] = 0
        nk = []
        for u in tp['ceventHitUnitList']:
            if u['unitSlotNum'] == 6:
                u['data']['bsdxInfoCollectionList'][0]['paramList'] = [0]
            elif u['unitSlotNum'] in (17, 18, 19, 20) and u.get('data'):
                u['data']['int1'] = 5; nk.append(u['unitSlotNum'])
        self.rep.add('NODMG', 'ph%d: BFE hit flag ﾀﾞﾒｰｼﾞ処理をしない (element %d, 0x4418d6 -> SE/effect 0x4418c7) -> slot 41 威力 0 / 最低値 0 '
                     '(tpl %s), コンボ補正 4 欄 0 (tpl %s/%s/%s/%s), ヒットストップ 0 (tpl %s), のけぞり %s 処理タイプ 5 なし; '
                     'BSDX damage 0 = no HP / combo count (0x616de3, 0x606154)' % (
                         pi, hi['element'], old[0], old[1], old[2], old[3], old[4], old[5], nk or 'none'))

    @staticmethod
    def _set_noke(d, nk):
        # BFE のけぞり (0x441d40) -> BSDX CEventNokezori 地上 (Hit sub 17).
        # horizontal: BFE pushes the victim with speed_init px/tick, decelerated by speed_step/256 px/tick each tick
        #   -> int8 のけぞり速度 = v/2 px/F, int9 速度減速率 = step*100/1024 (1/100 px/F per F): same distance v^2/2a.
        #   Vanilla 甲 タックル 15/50 vs BFE ﾀｯｸﾙ 32/512 -> 16/50. The old rule kept 甲's values (青龍刀 10/20 ~ 250px vs
        #   BFE 64px, パイルバンカー 12/200 ~ 36px vs BFE 256px: both reported).
        # vertical: launch only when launch_accum >= 100 (0x441ed3); victim velocity = launch*256 (0x441f50) with
        #   displacement (v/256)^2 per tick -> height grows faster than L; 吹き飛び規模 = 2*L^2 fits 甲 (アームアッパー 40
        #   / BFE 5, ジャンピングニー 50 / 5, ブーストアッパー 100 / 6) better than the old 20*L (100 for 5: 'flies too far').
        #   Negative launch (slam, ギャラクティックストライク -4) keeps a negative template value (甲 GS -150).
        if nk['speed_init'] or nk['speed_step'] != 256 or nk['direction']:
            d['int8'] = int(round(abs(nk['speed_init']) / 2.0))
            d['int9'] = int(round(max(0, nk['speed_step']) * 100 / 1024.0))
        #   M 2026-10-28: 吹き飛び重力 (int11) stayed the 甲 template value (エアタックル 20 = 20 % gravity: 98 -> 480px /
        #   196F, 'enemy flies too far'). BaldrSky.exe 0x61676a: victim vz = 規模/10 px/F, gravity 50 x 吹き飛び重力 %
        #   (0x6167a5 / 0x5f4be0) -> apex H = 規模^2/重力, airtime T = 40*規模/重力 F. Both from the BFE launch
        #   (bfe_launch, gravity BFE_LAUNCH_G): 規模 = 40H/T, 重力 = 1600H/T^2 (L5 67/74, L6 100/91, L7 140/108).
        #   M 2026-10-30 (LAUNCH, /200): the 10-28 fit took the gravity as 重力/100 per frame. BaldrSky.exe 0x616795 writes
        #   0xc800 (50<<10) to the victim's CMove gravity and 0x5f4be0 subtracts [+0x20] * 0x51eb851f >> 38 = /200 (x rate
        #   %/100, sar 5 = /100) -> a = 0.25 * 吹き飛び重力/100 px/F^2: H = 2*規模^2/重力, T = 80*規模/重力 -> the victims flew
        #   twice as high and twice as long as BFE (移植版1 BU 100/91: launch F202 -> down F246 = 88F = 80*100/91; 移植版ex
        #   ｴｱ･ﾀｯｸﾙ 140/108: 118F from mid-air; BFE L6 44F / L7 52F). Fit with the exe constant: 規模 = 40H/T (unchanged),
        #   重力 = 3200H/T^2 (L2 7/44, L3 20/80, L4 40/114, L5 67/148, L6 100/182, L7 140/215, L8 185/247).
        L = nk['launch']
        if nk['launch_accum'] >= 100 and 0 < L <= 2 and (d.get('int10') or 0) < 0 and d['int10'] != -999 and (d.get('int12') or 0) > 0:
            # E 2026-11-15 (SLAMKEEP, user 「クラッシュハンマーは、ヒット後に相手が即座に地面にたたきつけられるはずが、ふわっと
            # 浮くような吹き飛びをする」): a BFE 規模 1-2 hop is a few px under BFE's constant gravity, so a victim hit in the
            # air drops at once. The DiveX fit (規模 = 40H/T, 重力 = 3200H/T^2) gives such a hop a very low gravity
            # (L2 7/44 = 0.11 px/F^2), and the victim floated down. When the 甲 template slams (吹き飛び規模 < 0: 甲
            # クラッシュハンマー -300 / int12 3 = 叩きつけ後のバウンド), keep the template's slam. Only with int12 > 0: with the
            # fitted positive launch that bounce setting made the victim bob up and down slowly (the reported float).
            d['_slamkeep'] = (d['int10'], d.get('int11'))
            return
        if nk['launch_accum'] >= 100 and L > 0:
            H_, t_ = nk.get('_ht') or bfe_launch(L); T_ = 2 * t_
            if H_ > 0:
                d['int10'] = min(400, max(1, int(round(40.0 * H_ / T_))))
                d['int11'] = max(1, int(round(3200.0 * H_ / (T_ * T_))))
                if nk.get('_ride'):
                    d['int10'] = nk['_ride']        # RIDELAUNCH (convert, BVERT): re-launched every hit, keeps pace with the bomb
                # G 2026-11-04 (NOKEDOWN, user 20261103_4 #3 「DDミサイル・対空スプレッドボムで敵がダウンしない」): BFE puts
                # every launched victim down on landing (原作1 BU / 原作2 DD: lands in dust and lies). BaldrSky.exe stores
                # the ダウン時間 (int7 -> [+0x1880]+0x1c, 0x619246) and the launch of 0x618e00 only while the victim is in
                # hitstun (ﾋｯﾄﾊﾞｯｸ +0x18ec > 0, 0x619230 / 0x61914a); ﾋｯﾄﾊﾞｯｸ = int3 (first hit) / int4 (already in
                # hitstun, 0x618f8b). The 甲 templates of the bullets have 0/30 -> no down. Vanilla launch hits keep the
                # victim in hitstun past the landing (DDミサイル：甲Lv3 100/200 for an 80F flight) -> int3/int4 >= 2x the
                # DiveX airtime T = 80*規模/重力.
                hs_ = int(math.ceil(2 * 80.0 * d['int10'] / d['int11']))
                if nk.get('noke_count', 1) > 0:
                    d['int3'] = max(d.get('int3') or 0, hs_); d['int4'] = max(d.get('int4') or 0, hs_)
                else:
                    # E 2026-11-05 (NOKEFLOAT, user 11/05 「シールドのヒットで敵がダウンしないはずが、ダウンする」): BFE
                    # 0x441d5a..0x441d83 picks the down launch (mode 4 -> 0x441f50 -> 0x41aa70 action 2) for a victim not
                    # in hitstun only when noke +0x03 (named のけぞり回数) > 0; with 0 it is mode 0 (action 0x1a, a hop
                    # without down) unless the victim is already down-launched (+0x30c). Every TOORU melee launch has
                    # +0x03 > 0; the 0 ones are barriers / small bombs (ｼｰﾙﾄﾞ, ﾌﾞﾛｯｸﾊﾞﾘｱ, ﾘﾊﾞｰｽﾌｨｰﾙﾄﾞ ...). DiveX downs a
                    # victim that lands while still in hitstun (NOKEDOWN) -> keep the hop but end the hitstun at half the
                    # airtime (T/2 = 40*規模/重力; hitstun 0 would drop the launch, 0x61914a). 甲 シールド: 0/40, 規模 1.
                    t2_ = max(1, int(40.0 * d['int10'] / d['int11']))
                    b_ = (d.get('int3'), d.get('int4'))
                    d['int3'] = max(1, min(d.get('int3') or t2_, t2_)); d['int4'] = max(1, min(d.get('int4') or t2_, t2_))
                    # R 2026-11-05 (user シールド.mp4: still down): ダウン時間 (int7, stored at the hit while in hitstun,
                    # 0x619246) 0 as well -> no down state is recorded at all.
                    d['int7'] = 0
                    # E 2026-11-06 (NOKEFLOAT, user シールド.mp4 11/06: still down): a multi-hit barrier (ｼｰﾙﾄﾞ 255 hits / 8F)
                    # relaunches the victim every hit; BaldrSky.exe 0x6191de raises the victim gravity with its air-hit
                    # count [+0x18f4] (50 -> 20n+10), so the hop shrinks below the hitstun and it lands in hitstun = down.
                    # Vanilla 甲 シールド：甲 0/40: no hitstun for a fresh victim -> no launch (0x61914a), push only.
                    if nk.get('_multi'):
                        d['int3'] = 0
                    d['_nokefloat'] = (b_, (d['int3'], d['int4']), d['int10'], d['int11'])
            else:
                d['int10'] = 0
        elif nk['launch_accum'] >= 100 and L < 0:
            if not (d.get('int10', 0) < 0 and d['int10'] != -999):
                d['int10'] = -min(150, 2 * L * L)
        elif d.get('int1') == 0:
            d['int10'] = 0

    def _set_fire(self, o, fire, speed, angle=None, count=None):
        S = self.fx.sub_samples
        d = effect_sub(o, 4, S.get(4))
        if d is not None:
            d['int2'] = d['int5'] = count or max(1, fire['count'][0])
        ac, ar = (fire['angle_corr'][0] if angle is None else angle), fire['angle_rand'][0]
        if ac or ar or effect_sub(o, 14) is not None:
            # S 2026-10-30 (ANGLESIGN): DiveX angles turn the other way on screen from BFE ones: ﾘｻｰﾁﾐｻｲﾙ fires -30 first
            # (0x449bc0 ping-pong); 原作10 the 1st missile goes up-right and the 2nd down-right, 10/28 移植版6 the 1st
            # down-right and the 2nd up-right; BFE + = clockwise (チップ向き +360 spins clockwise, 原作10).
            d = effect_sub(o, 14, S.get(14))
            # (2026-11-08: RANDLOW was also applied here and reverted the same day - user 「ランダムが絡む武装の向きがおかしい」.
            # The spawn sub 14 width IS ± (vanilla 180±90 / 0±10 / 0±360 pairs; BFE ﾗﾝﾀﾞﾑ角度 ±r, 0x449fe8), unlike the
            # slot 16 方向補正 one-sided width (-40/80 pairs) -> -ac, r as before.)
            d['int1'] = d['int2'] = d['int3'] = d['int4'] = 0; d['int5'] = -ac; d['int6'] = ar
            if ac:
                self.rep.add('ANGLESIGN', 'fire 角度補正 -> spawn sub 14 = -BFE angle (DiveX angles turn the other way)')
        d = effect_sub(o, 31, S.get(31))
        d['int1'] = d['int3'] = d['int4'] = 0; d['int2'] = d['int5'] = speed; d['int6'] = 0
        # R 2026-11-15 (POSCORR, user 「サテライトがある程度散らばるのが原作、今は正確に敵の頭上に落ちている」): BFE fire 位置補正
        # = the spawn point is moved that many px along the fire angle (角度補正 ± ﾗﾝﾀﾞﾑ角度): ｻﾃﾗｲﾄﾚｰｻﾞｰ：本体 ph1 drops each beam
        # 100 px from itself in a random direction (ﾗﾝﾀﾞﾑ角度 359). It was not converted at all. DiveX spawn sub 8 発射位置補正：
        # 方向 / 9 方向補正 / 10 距離 (vanilla 爆風: 9 = 0 ± 360, アームガン: 10 = 10). The offset angle is a separate random draw
        # from sub 14, so only where that cannot show: no random angle, or a bullet that does not move in its first phase;
        # and only spawns placed on the shooter itself.
        pc = fire['pos_corr'][0]
        if pc > 0 and self.fx is not None and 0 <= fire['tama'] < len(self.fx.tama) and all(S.get(k) is not None for k in (8, 9, 10)):
            t0 = self.fx.tama[fire['tama']]['phases'][0]
            still = t0['speed']['init'][0] == 0 and t0['speed']['final'][0] == 0
            d7 = effect_sub(o, 7)
            on_self = bool(d7 and d7.get('bsdxInfoCollectionList') and d7['bsdxInfoCollectionList'][0]['typeList'] == [1] and
                           d7['bsdxInfoCollectionList'][0]['intList3'][:1] == [0])
            if (ar == 0 or still) and on_self:
                d8 = effect_sub(o, 8, S.get(8)); d28 = effect_sub(o, 28)
                if d28 is not None and d28.get('bsdxInfoCollectionList'):
                    d8['bsdxInfoCollectionList'] = copy.deepcopy(d28['bsdxInfoCollectionList'])
                d9 = effect_sub(o, 9, S.get(9))
                d9['int1'] = d9['int2'] = d9['int3'] = d9['int4'] = 0; d9['int5'] = -ac; d9['int6'] = ar
                d10 = effect_sub(o, 10, S.get(10))
                d10['int1'] = d10['int3'] = d10['int4'] = d10['int6'] = 0; d10['int2'] = d10['int5'] = pc
                for d_ in (d8, d9, d10):
                    d_['startFrame'] = d_['endFrame'] = 0
                self.rep.add('POSCORR', 'fire Tama %d: BFE 位置補正 %d px, 角度 %d ± %d -> spawn sub 8 / 9 / 10 (発射位置補正 方向 / 方向補正 / 距離)' % (
                    fire['tama'], pc, ac, ar))
            else:
                self.rep.add('APPROX', 'fire Tama %d: BFE 位置補正 %d px not converted (random angle on a moving bullet, or not spawned on the shooter)' % (
                    fire['tama'], pc))
        if effect_sub(o, 28) is None and S.get(28) is not None:
            # every BFE bullet starts moving along its fire direction (0x449eb0 -> obj+0x51c and the velocity) = vanilla
            # spawn sub 28 ﾍﾞｸﾄﾙ：方向 「角度指定→スプライト方向(0,0)」 (甲 ハンドガン / ホーミングミサイル / 炸裂弾 shards). A
            # template spawn without it (甲 火炎放射 = a line parent that never moves) left the direction at the engine
            # default and sub 14 turned the flames down / backwards (reported '火炎放射器の射出方向').
            effect_sub(o, 28, S.get(28))
            self.firedir_added = True     # reported once per fire block by the caller (FIREDIR)
        hc = fire['height_corr'][0]
        if hc not in (0, -999) and S.get(11) is not None:
            # 高さ補正 (BFE px) -> 発射位置補正 sub 11. Without it the beam spawned at height 0 and never visibly fell (V/W
            # report). R 2026-11-04 (provisional): x1, was x8 (from 甲 サテライトレーザー's 5000..6000). Every vertical rule
            # here takes BFE px = DiveX px (BVERT / BFALL / BDIVE), and at x8 (6000 px) the beam needed ~250F to fall and
            # never reached the screen (user: radar shows the hit, no effect). 750 px falls in ~35F as in BFE.
            d = effect_sub(o, 11, S.get(11))
            d['int1'] = d['int3'] = d['int4'] = d['int6'] = 0; d['int2'] = d['int5'] = int(hc)
            self.rep.add('HEIGHT', 'fire 高さ補正 BFE %d -> 発射位置補正 %d (x1 暫定, BFE px = DiveX px)' % (hc, int(hc)))
        if 0 <= fire.get('tama', -1) < len(self.fx.tama) and effect_sub(o, 23) is not None:
            md0_ = self.fx.tama[fire['tama']]['phases'][0]['move_dir']
            if md0_['type'] == 5 and md0_['flags'] & 4 and md0_['init'][0] != -32768 and md0_['final'][0] > md0_['init'][0] \
                    and md0_['step'][0] >= 256 and not (fire['angle_rand'][0] or fire['angle_rand'][1]):
                # R 2026-11-06 (STICKALPHADIR, user ｴﾈﾙｷﾞｰﾌｨｰﾙﾄﾞ.mp4: the field stays on 透): the STICKALPHA bullet slides
                # along its sprite direction, but the template spawn's sub 23 ｽﾌﾟﾗｲﾄ：方向補正 ±360 gave it a random
                # heading. BFE ﾗﾝﾀﾞﾑ角度 is 0 and 発射方向 相対 = 透's facing; vanilla Ｅフィールド：甲 spawns have no sub 23.
                drop_effect_sub(o, 23)
                self.rep.add('STICKALPHADIR', 'fire Tama %d (常に標的位置＋α): spawn sub 23 方向補正 ±360 dropped (vanilla Ｅフィールド：甲)' % fire['tama'])
        drop_effect_sub(o, 17)
        # E 2026-11-07 (SPAWNYPCT, user 20261103_4 #7 / 鷹落とし.mp4 「縦長・判定が広い」): sub 19 is not a zoom: it fills +0x16b0, a Y
        # percentage that slot 1 never resets (BaldrSky.exe 0x611978, 0x60bad8: Y = Y × 値 / 100, also the hit rects). The 甲 template's
        # 512 made 鷹落とし ×5.12 tall; ｶﾞﾄﾘﾝｸﾞ砲 5, T-150 / ｼﾞｪﾉｻｲﾄﾞ 256, ﾀﾞﾌﾞﾙSMG 96 likewise. BFE fire has no zoom -> drop it.
        drop_effect_sub(o, 19)
        drop_effect_sub(o, 15)          # the fire SE is played by the skill itself (slot 52)
        d = effect_sub(o, 16)
        if d is not None:
            d['int5'] = 256; d['int6'] = 0


def remap_template_sprites(skill, anim_map, self_groups, rep, numpat):
    """clone helper for the basic skills: sprite refs of a Kou skill -> tooru anims (same index 0..47, others via
    anim_map); pattern clamped to the target anim's pattern count"""
    for d in walk(skill):
        if 'actionGroupNumber' in d and d.get('spmFileSequence') in self_groups:
            a = anim_map.get(d['actionGroupNumber'], d['actionGroupNumber'])
            if a != d['actionGroupNumber']:
                rep.add('BASIC_ANIM', 'Kou anim %d -> tooru anim %d' % (d['actionGroupNumber'], a))
            n = numpat[a]
            if n <= 0:
                raise ValueError('empty anim %d' % a)
            if d['actionNumber'] >= n:
                rep.add('BASIC_ANIM', 'pattern clamp anim %d #%d -> #%d' % (a, d['actionNumber'], n - 1))
            d['actionGroupNumber'] = a; d['actionNumber'] = min(d['actionNumber'], n - 1); d['spmFileSequence'] = -1
