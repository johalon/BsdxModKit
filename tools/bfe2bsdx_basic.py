#!/usr/bin/env python3
"""透（TOORU）の基本性能（ダッシュ系）— BFE 仕様外のユーザー要望（2026-10-26 フィードバック「BFE仕様外の要望」）。

要望: ノーマルダッシュ速度 12 / サーチダッシュ = 村正と同等の性能で速度 26 / ブーストダッシュ = イムくん（ノイ）と
同じスクリプトで速度 18 前後（移動ではなくドッジ的に使う新モーション）。理由: BFE は BD が無く ND が速く SD に溜めが無い。

方式（バニラの実例をそのままコピー。調査記録 14 §B）:
* 速度は mek 基本情報の 速度：ダッシュ / サーチダッシュ / ブーストダッシュ（DTO normalDashSpeed / searchDashSpeed /
  boostDashSpeed）。exe のプロパティ表 0x85e97c..0x85e99c = {速度：歩行, 速度：ダッシュ, 速度：サーチダッシュ,
  速度：ブーストダッシュ, 浮遊高度} が DTO の並びと一致。バニラの基本技（Kou/Muramasa/Noi の SD/BD/ND 技）には
  速度イベント（slot 18）が無く、ベクトル補正率：移動（slot 24, %）で区間ごとに倍率を掛けるだけ。
* 基本技は mek の PairBlock（14 個: 0 立ち, 1-2 歩行, 3-5 ND 開始/持続/硬直, 6-8 SD, 9-11 BD, 12-13 起き上がり）で
  waz の技番号を指す。透は甲の配置（ND = -1 = エンジン既定, SD = 技 3-5, BD = 技 6-8）なので、
  技 3-5 を 村正の SD 技 6-8、技 6-8 を ノイの BD 技 9-11 で**同じ番号のまま置き換える**（技番号はずれない）。
* スプライト参照は基本 anim 0..47 が全機体共通の意味（kou/muramasa/imukun/tooru.spm で名前一致を確認）なので
  同じ番号のまま tooru.spm（spmFileSequence -1）へ。パターン番号は透の anim のパターン数に丸める。ボイス（slot 53）は削除
  （透はボイスなし）。SE・エフェクト（共通 Effect.waz）は元のまま → mek の MaterialBlock 通常エントリ 2（ダッシュ系の
  素材。甲 / 村正 / ノイの通常エントリ 2 にそれぞれの SD/BD の SE・エフェクト画像が入っていることで確認）に合流させる。
"""
import copy, collections

SPEEDS = {'normalDashSpeed': 8, 'searchDashSpeed': 26, 'boostDashSpeed': 18}   # ND 12 -> 10 (user 2026-10-27) -> 8 (user 2026-11-12)
# BD retiming (user 2026-10-27: 加速前の硬直を今の 1/4〜1/3、持続を半分 = ドッジ専用化). dst skill -> (old, new) frame of
# its unconditional end change (slot 71). All events of the copied vanilla skill are rescaled by new/old (same script
# shape; point events at frame 0 such as 移動補正 0% / 100% keep their meaning); events reaching past the change
# (CPU 回避 / SE loop 0-150 = "until the skill ends") are left as they are.
#   6 BD 開始 (Noi 9): change 11 -> 3 = 12F -> 4F (1/3). 4F = vanilla precedent 村正 BD 開始 (Muramasa.waz 9, 4F);
#                      3F (1/4) would leave only 3 sprite frames of the 4-pattern 構え.
#   7 BD 持続 (Noi 10): change 20 -> 10 (half; still fixed length, independent of the button)
#   user 2026-10-30: BD 開始 +1F (4F -> 5F, change 3 -> 4); 移動距離 2/3 は速度 18 のまま持続で: 11F -> 7F (change 10 -> 6)
RETIME = {6: (11, 4), 7: (20, 10)}   # user 2026-11-12: BD 持続（最高速の区間）+4F、速度そのまま: 7F -> 11F (change 6 -> 10)
# SD (user 2026-10-31: 開始前の硬直をなくす・すぐ加速 / バーニアのエフェクトをなくす / 持続 20F / 終了後の慣性は今のまま; 調査記録 21).
#   3 SD 開始 (Muramasa 6): end change 5 -> 0 = 6F -> 1F (frame 0 only). BaldrSky.exe SD state (vtable 0x7f1888):
#     the engine sets the dash velocity to 0 in the start stages 0/1 and to the SD speed only in the 持続 stages 2/3
#     (0x62b8e0), and a start skill's end moves straight to 持続 (OnSkillEnd 0x62c430: stage 1 -> SetStage(3)).
#     PairBlock -1 is NOT a skip: it selects the engine default start (stage 0, SetStage 0x62bbd6), which waits
#     11F (update 0x62c173: counter > 10 -> SetStage(3)) = Zako022a's case. So the start stays a waz skill, cut to F0;
#     its F0 events (SE x2, 接触, effects moved F4 -> F0) still run: vanilla precedent Tama02 73/55 last phases
#     (エフェクト + unconditional end at F0).
#   4 SD 持続 (Muramasa 7): fixed 20F = unconditional end change at F19 (was: 「離したら」 F20..150 = min 21F);
#     the rest rescaled by retime(20 -> 19), events past F20 (CPU 回避 0-150, SE loop 1-150, ...) unchanged.
RETIME[3] = (5, 0)
SD_FIXED_END = (4, 20, 19)      # dst skill, old (conditional) change frame, new unconditional end frame
# バーニア = Effect.waz 139「方向煙：村正」(Mark.spm anim 157 ﾏｽﾞﾙﾌﾗｯｼｭ：02, X 拡大 1024 = 4 倍で後ろ向き（方向補正 180）に
# 機体へ追従する炎, 7F 間隔で発生) -> removed. Kept: 104 地面属性（大）総合 (ground dust / splash by terrain) and the
# start's launch burst 10 リング煙 / 72 フラッシュ / 67 リング楕円黄 (one-shot at the start, not a thruster).
SD_DROP_EFFECTS = {4: [139]}
# SDFACE (user 2026-11-22 「サーチダッシュの開始時、敵のほうに100%向くようにしてほしい」, 両版, 調査記録 96):
#   SD 開始の slot 10 方向増分 200 (20°/F) は 村正 6F / 甲 13F の開始なら 120° / 260° 回るが、開始を F0 だけにした
#   (RETIME[3]) ので 20° しか回らず、持続 F0 の 0 で止まっていた。-> 開始 F0 の 200 を 9999 (即座に敵方向) に、
#   持続 F0 の 0 を 9999・F1 に 0 (1F の向き直り、FACEPHASE と同じ書き方: 甲 ASスティンガー T2 F30 9999 / F31 0)。
#   持続側にも置くのは、F0 で終わる開始の技の slot 10 が 持続 F0 の 0 より先に効くかが未確認のため（二重に置いて確実に）。
SD_FACE_SNAP = 9999
SD_FACE = {3: (200, False), 4: (0, True)}     # dst skill -> (F0 slot 10 の元の値, F1 に 0 を足すか)
# BD 硬直 (Noi 11) ground phase slot 24 移動補正 (% of the dash speed kept while recovering): 20 -> 15
# (user 2026-10-30: 終わりの減速をほんの少し強めて、ドッジ後のリスクを増やす)
BD_RECOVER_RATE = (8, 20, 15)
ARMOR_LV_MAX = 16      # vanilla slot 36 装甲 int4 range 1..16
# user 2026-11-09 (ARMORATK1): 装甲攻撃力 (Hit int11) の x2 をやめて 甲テンプレの値そのまま。自機の装甲 (slot 36) の x2 は維持。
#   根拠: BaldrSky.exe 0x61f0c8 装甲ゲージ減少 = max(1, 最終ダメージ x int11 / 100)、0x60c74f 技の装甲段階 1 = プール 100。
#   透の威力 (BFE/4、最低値) は甲 Lv1 の約 1.5〜2 倍なので、x1 で近接はほぼ甲 Lv3 と同水準
#   (ブーストアッパー 1・2 段目 = 各 187 → 合計 約 3.7 段階)。x2 では甲 Lv3 の約 2 倍だった。
ARMOR_ATK_X2 = False
# user 2026-11-09 夕 (ARMORSELF1): 自機の装甲 (slot 36 段階・常時装甲) の x2 もやめる。原作再現版は等倍で評価する
#   (強化するなら modified 側で)。これで 10/27 の「装甲関連 x2」は 3b では何もしない。
ARMOR_SELF_X2 = False
# Tooru (= Kou layout) skill index -> (vanilla mech, its skill index); PairBlock slot in comments
COPY = {
    3: ('Muramasa', 6),   # pair 6  サーチダッシュ（開始）  6F（甲 12F）-> 1F (RETIME, user 2026-10-31)
    4: ('Muramasa', 7),   # pair 7  サーチダッシュ（持続）  D キーを離すまで -> 固定 20F (SD_FIXED_END, user 2026-10-31)
    5: ('Muramasa', 8),   # pair 8  サーチダッシュ（硬直）  10F
    6: ('Noi', 9),        # pair 9  ブーストダッシュ（開始） 12F、移動補正 0%
    7: ('Noi', 10),       # pair 10 ブーストダッシュ（持続） 固定 20F（ボタンに関係なく終わる）、移動補正 100%
    8: ('Noi', 11),       # pair 11 ブーストダッシュ（硬直） 着地 22F（移動補正 20%）／空中 20F
}
SOURCES = ('Muramasa', 'Noi')
MATERIAL_ENTRY = 2    # regular MaterialBlock entry holding the dash / SD / BD assets
VOICE_SLOT = 53


def jobs(src, jdir):
    """PortTool b2j jobs for the vanilla sources (same priority as the build: Update2 > Update > Dat)"""
    out = []
    for n in SOURCES:
        out += [['b2j', 'bsdx', src(n + '.waz'), '%s/%s.waz.json' % (jdir, n)], ['b2j', 'bsdx', src(n + '.mek'), '%s/%s.mek.json' % (jdir, n)]]
    return out


def _check_source(name, waz, mek, kou_waz):
    pair = [p['int2'] for p in mek['mekPairBlock']['unkPair']]
    for dst, (sn, si) in COPY.items():
        if sn != name:
            continue
        slot = {3: 6, 4: 7, 5: 8, 6: 9, 7: 10, 8: 11}[dst]
        assert pair[slot] == si, (name, slot, pair)
        # same role as the Kou skill it replaces (SD <-> SD, BD <-> BD; stage 開始/持続/硬直)
        kn, sn_ = kou_waz['skillList'][dst]['skillNameJapanese'], waz['skillList'][si]['skillNameJapanese']
        assert kn == sn_, (name, si, sn_, kn)


def apply_waz(waz_skills, kou_waz, srcs, rep, numpat, remap):
    """replace waz_skills[3..8] (Kou layout) by the vanilla SD (Muramasa) / BD (Noi) skills.
    srcs: name -> (waz json, mek json). remap = bfe2bsdx_waz.remap_template_sprites. Returns the new skill objects."""
    for n in SOURCES:
        _check_source(n, srcs[n][0], srcs[n][1], kou_waz)
    new = []
    for dst, (sn, si) in sorted(COPY.items()):
        waz, mek = srcs[sn]
        grp = mek['mekBasicInfo']['spmFileSequence']
        s = copy.deepcopy(waz['skillList'][si])
        for o in _walk(s):          # basic anims only (0..47 = same meaning in every mech spm)
            if 'actionGroupNumber' in o and o.get('spmFileSequence') in (-1, grp):
                assert 0 <= o['actionGroupNumber'] < 48, (sn, si, o)
        remap(s, {}, (-1, grp), rep, numpat)
        for o in _walk(s):
            assert not ('actionGroupNumber' in o and o.get('spmFileSequence') == grp), (sn, si)
        nv = 0
        for ph in s['phasesInfo']:
            nv += sum(1 for u in ph['skillUnitCollection'] if u['unitQuantity'] == VOICE_SLOT)
            ph['skillUnitCollection'] = [u for u in ph['skillUnitCollection'] if u['unitQuantity'] != VOICE_SLOT]
        k = kou_waz['skillList'][dst]
        rep.add('BASIC', 'skill %d %s <- %s skill %d「%s」(%s)%s' % (dst, k['skillNameJapanese'], sn, si, s['skillNameJapanese'],
                                                                   s['skillNameEnglish'], ' voice x%d removed' % nv if nv else ''))
        s['skillNameJapanese'], s['skillNameEnglish'] = k['skillNameJapanese'], k['skillNameEnglish']
        what = 'skill %d %s' % (dst, k['skillNameJapanese'])
        if dst in RETIME:
            retime(s, *RETIME[dst], rep=rep, what=what, note='user 2026-10-31' if dst == 3 else 'user 2026-10-27')
        if dst == SD_FIXED_END[0]:
            fixed_end(s, *SD_FIXED_END[1:], rep=rep, what=what)
        for eno in SD_DROP_EFFECTS.get(dst, ()):
            drop_effect(s, eno, rep=rep, what=what)
        if dst in SD_FACE:
            sd_face(s, *SD_FACE[dst], rep=rep, what=what)
        if dst == BD_RECOVER_RATE[0]:
            hit = [o for ph in s['phasesInfo'] for u in ph['skillUnitCollection'] if u['unitQuantity'] == 24
                   for o in u['skillInfoObjectList'] if o.get('int4') == BD_RECOVER_RATE[1]]
            assert len(hit) == 1, (dst, hit)
            hit[0]['int4'] = BD_RECOVER_RATE[2]
            rep.add('BASIC', 'skill %d %s slot 24 移動補正 %d -> %d (user 2026-10-30: 終わりの減速を少し強める)' % (
                dst, k['skillNameJapanese'], BD_RECOVER_RATE[1], BD_RECOVER_RATE[2]))
        waz_skills[dst] = s
        new.append(s)
    return new


def apply_mek(basic_info, rep):
    for k, v in SPEEDS.items():
        rep.add('BASIC', 'mek %s %s -> %s' % (k, basic_info.get(k), v))
        basic_info[k] = v
    pa = basic_info.get('permanentArmor') or 0      # 常時装甲: armor x2 rule (user 2026-10-27) - 0 stays 0
    basic_info['permanentArmor'] = pa * 2 if ARMOR_SELF_X2 else pa
    rep.add('BASIC', 'mek permanentArmor（常時装甲）%s -> %s (装甲関連 x2)' % (pa, pa * 2))


def fixed_end(skill, old_end, new_end, rep=None, what=''):
    """make a 'until the button is released' 1-turn skill fixed length (user 2026-10-31, SD 持続 20F): its single
    conditional end change at old_end becomes unconditional at new_end (= F0..new_end), the timeline rescaled by
    retime(old_end -> new_end) (events past old_end = 'until the skill ends' unchanged). Same 終了 target as before."""
    ph = skill['phasesInfo'][0]
    ch = [o for u in ph['skillUnitCollection'] if u['unitQuantity'] == 71 for o in u['skillInfoObjectList']]
    assert len(ch) == 1 and ch[0]['startFrame'] == old_end and ch[0]['flag'] == 1, (what, ch)
    cond = ch[0]['bsdxInfoCollectionList1'][0]
    old_cond = list(cond['typeList'])
    assert old_cond != [0] and ch[0]['bsdxInfoCollectionList2'][0]['typeList'] == [0, 2], (what, ch)
    retime(skill, old_end, new_end, rep=rep, what=what, note='user 2026-10-31')
    cond.update(typeList=[0], paramList=[], intList3=[], intList4=[])      # 無条件 (as the start / 硬直 end changes)
    ch[0]['startFrame'] = ch[0]['endFrame'] = new_end
    if rep is not None:
        rep.add('BASIC', '%s end change: condition %s at F%d..150 -> unconditional at F%d = fixed %dF regardless of the '
                         'button (user 2026-10-31)' % (what, old_cond, old_end, new_end, new_end + 1))


def sd_face(skill, old, add_stop, rep=None, what=''):
    """SDFACE (user 2026-11-22): the skill's single F0 slot 10 方向増分 (old) -> SD_FACE_SNAP (snap to the locked enemy),
    plus a 0 at F1 when add_stop (1F の向き直り)."""
    ph = skill['phasesInfo'][0]
    u10 = [u for u in ph['skillUnitCollection'] if u['unitQuantity'] == 10]
    assert len(u10) == 1, (what, len(u10))
    L = u10[0]['skillInfoObjectList']
    assert len(L) == 1 and L[0]['startFrame'] == 0 and L[0]['endFrame'] == 0 and (L[0].get('int5') or 0) == old, (what, L)
    L[0]['int5'] = SD_FACE_SNAP
    if add_stop:
        o = copy.deepcopy(L[0]); o['offset'] = 0; o['startFrame'] = o['endFrame'] = 1; o['int5'] = 0
        L.append(o)
    if rep is not None:
        rep.add('SDFACE', '%s slot 10 方向増分 F0 %d -> %d%s (開始時に敵へ 100%% 向く; user 2026-11-22)' % (
            what, old, SD_FACE_SNAP, ', F1 0' if add_stop else ''))


def drop_effect(skill, eno, rep=None, what=''):
    """remove the slot 48 エフェクト events spawning Effect.waz skill eno (user 2026-10-31: バーニアのエフェクトをなくす)"""
    n = 0
    for ph in skill['phasesInfo']:
        for u in ph['skillUnitCollection']:
            if u['unitQuantity'] != 48:
                continue
            keep = []
            for o in u['skillInfoObjectList']:
                no = [e['data'] for e in o['ceventEffectUnitList'] if e['ceventEffectUnitQuantity'] == 3]
                if len(no) == 1 and no[0].get('wazFileNo') == 0 and no[0].get('wazSequenceNo') == eno:
                    n += 1
                else:
                    keep.append(o)
            u['skillInfoObjectList'] = keep
        ph['skillUnitCollection'] = [u for u in ph['skillUnitCollection'] if u['unitQuantity'] != 48 or u['skillInfoObjectList']]
    assert n == 1, (what, eno, n)
    if rep is not None:
        rep.add('BASIC', '%s slot 48 エフェクト Effect.waz %d removed (バーニア; user 2026-10-31)' % (what, eno))


def retime(skill, old_end, new_end, rep=None, what='', note='user 2026-10-27'):
    """rescale the 1-turn skill's timeline by new_end/old_end (old_end = frame of its unconditional end change).
    Range events: start' = round(start*k), end' = round(end*k) (>= start'). Sprite events (slot 0) stay a gap-free
    sequence: each ends where the next starts; a middle pattern whose span rounds to 0 frames is dropped, the last pose
    is always kept. Frames beyond old_end (= 'until the skill ends', e.g. CPU回避 0-150) are not changed."""
    assert len(skill['phasesInfo']) == 1, what
    k = new_end / float(old_end)
    f = lambda x: x if x > old_end else int(round(x * k))
    ph = skill['phasesInfo'][0]
    ends = [o['startFrame'] for u in ph['skillUnitCollection'] if u['unitQuantity'] == 71 for o in u['skillInfoObjectList']]
    assert ends == [old_end], (what, ends)
    before = {}
    for u in ph['skillUnitCollection']:
        L = u['skillInfoObjectList']
        before[u['unitQuantity']] = [(o['startFrame'], o['endFrame']) for o in L]
        if u['unitQuantity'] == 0:
            L.sort(key=lambda o: o['startFrame'])
            st = [f(o['startFrame']) for o in L]
            keep = []
            for i, o in enumerate(L):
                last = i == len(L) - 1
                if not last and st[i + 1] <= st[i]:
                    continue
                o['startFrame'], o['endFrame'] = st[i], (st[i + 1] - 1 if not last else max(st[i], f(o['endFrame'])))
                keep.append(o)
            u['skillInfoObjectList'] = keep
        else:
            for o in L:
                o['startFrame'], o['endFrame'] = f(o['startFrame']), max(f(o['startFrame']), f(o['endFrame']))
    if rep is not None:
        after = {u['unitQuantity']: [(o['startFrame'], o['endFrame']) for o in u['skillInfoObjectList']] for u in ph['skillUnitCollection']}
        rep.add('BASIC', '%s retimed %dF -> %dF (end change %d -> %d; %s): %s' % (
            what, old_end + 1, new_end + 1, old_end, new_end, note,
            '; '.join('slot %d %s -> %s' % (s, before[s], after[s]) for s in sorted(before) if before[s] != after[s])))


def double_armor(skills, rep, what, log=None):
    """user 2026-10-27 「すべての装甲に関する値（武装の装甲値と、装甲への攻撃値など）は、今の倍で」: x2 of what the build
    produced (converted from BFE or kept from the 甲 / vanilla template alike), applied once at the end of the build to
    every skill the port writes:
      * slot 36 装甲 (CEventVal int4 = super-armor level, vanilla 1..16) -> x2 (cap 16)
      * slot 41 / 42 Hit int11 装甲攻撃力 (%): BaldrSky.exe 0x61f0c8: armor gauge damage = max(1, dmg * int11 / 100),
        taken from the victim's armor pools (+0x1940 / +0x193c / +0x1944) -> x2 (0 stays 0, negative = special, kept)
    returns the number of changed values; one report line per skill (log: list receiving (kind, msg) as well)"""
    n = 0
    for si, s in skills:
        if not s:
            continue
        ch = collections.Counter()
        for ph in s['phasesInfo']:
            for u in ph['skillUnitCollection']:
                q = u['unitQuantity']
                for o in u['skillInfoObjectList']:
                    if q == 36 and o.get('int4', 0) > 0 and ARMOR_SELF_X2:
                        v = min(ARMOR_LV_MAX, o['int4'] * 2); ch['装甲 slot36 %d->%d' % (o['int4'], v)] += 1; o['int4'] = v
                    elif q in (41, 42) and o.get('int11', 0) > 0 and ARMOR_ATK_X2:
                        v = o['int11'] * 2; ch['装甲攻撃力 slot%d %d->%d' % (q, o['int11'], v)] += 1; o['int11'] = v
        if ch:
            n += sum(ch.values())
            m = '%s%s: 装甲関連 x2 (user 2026-10-27): %s' % (what, si if si is not None else '', ', '.join(
                '%s%s' % (k_, ' x%d' % c if c > 1 else '') for k_, c in sorted(ch.items())))
            rep.add('ARMOR', m)
            if log is not None:
                log.append(('ARMOR', m))
    return n


def merge_material(entries, extra, self_group):
    """union the SE / sprite lists of `extra` (material_for() of the new skills) into regular entry MATERIAL_ENTRY;
    the mech's own sprite group already lists every basic-anim image"""
    e = entries[MATERIAL_ENTRY]
    for key in ('spriteGroups', 'seGroups'):
        for g, L in enumerate(extra[key]):
            if key == 'spriteGroups' and g == self_group:
                continue
            if L:
                e[key][g] = sorted(set(e[key][g]) | set(L))


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


# SD 残像 / SE (user 2026-11-06):
#  2 「サーチダッシュ中も残像を出してほしい。残像同士の距離の間隔が甲の SD と同じくらい」: 甲 サーチダッシュ（持続）slot 49
#    残像 int2 3 (発生間隔 F) / int3 20 (表示 F) at SD speed 16 = 48 px between images. 透 SD speed 26 (SPEEDS) ->
#    interval round(48 / 26) = 2F (52 px). 表示 20F as 甲.
#  3 「原作（ショートダッシュ）では SE が鳴っている。今の SE に加えて鳴らしてほしい」: BFE mech SE table sdash = 124
#    「dash04」 (BaldrForce.exe motion handlers, tools/gen_bfe_waz_fields MOTIONS 'se') -> SD 開始 F0, next to the two
#    vanilla SEs (slot 52 holds several objects per frame: 甲 メガブーストキック T3 F10).
SD_BLINK = (4, 3, 20)            # dst skill (持続), 甲's interval, 甲's 表示時間
KOU_SD_SPEED = 16
SD_SE = (3, 124)                 # dst skill (開始), BFE SE index


def add_sd_extras(waz_skills, kou_waz, se_obj, se_ref, rep, sd_speed):
    dst, kint, klife = SD_BLINK
    k49 = [o for ph in kou_waz['skillList'][dst]['phasesInfo'] for u in ph['skillUnitCollection'] if u['unitQuantity'] == 49
           for o in u['skillInfoObjectList']]
    assert len(k49) == 1 and k49[0]['int2'] == kint and k49[0]['int3'] == klife, k49
    s = waz_skills[dst]; ph = s['phasesInfo'][0]
    end = max(o['endFrame'] for u in ph['skillUnitCollection'] if u['unitQuantity'] == 71 for o in u['skillInfoObjectList'])
    o = copy.deepcopy(k49[0]); o['offset'] = 0; o['startFrame'] = 0; o['endFrame'] = end
    o['int2'] = max(1, int(round(KOU_SD_SPEED * kint / float(sd_speed))))
    u49 = [u for u in ph['skillUnitCollection'] if u['unitQuantity'] == 49]
    assert not u49, 'SD 持続 already has 残像'
    u = copy.deepcopy([u for p_ in kou_waz['skillList'][dst]['phasesInfo'] for u in p_['skillUnitCollection'] if u['unitQuantity'] == 49][0])
    u['skillInfoObjectList'] = [o]
    ph['skillUnitCollection'].append(u); ph['skillUnitCollection'].sort(key=lambda x: x['unitQuantity'])
    rep.add('BASIC', 'skill %d SD 持続 slot 49 残像 F0-%d: 間隔 %dF (甲 %dF x SD 速度 %d/%d), 表示 %dF (user 2026-11-06)' % (
        dst, end, o['int2'], kint, KOU_SD_SPEED, sd_speed, klife))
    kou_dash_fx(waz_skills, kou_waz, se_obj, se_ref, rep)


# SD / BD エフェクト・SE (user 2026-11-06 「サーチダッシュ・ブーストダッシュともに、エフェクトとSEから村正とノイのものを消して、
# エフェクトは甲のもの、SEは開始時は甲のもの、持続では透の原作音を使う」):
#  * slot 48 / 52 of the copied 村正 SD (3-5) / ノイ BD (6-8) are removed.
#  * effects: 甲's own slot 48 of the same skill (甲 SD/BD 持続 F0: Effect.waz 72 x2 + 104; 開始 / 硬直 have none).
#  * SE 開始: 甲's slot 52 of the same skill (SE 0/266 at 甲 F3 of 13F / F5 of 10F) at the same relative time.
#  * SE 持続: BFE mech SE table (tools/gen_bfe_waz_fields MOTIONS): SD = sdash 124 「dash04」 (ｼｮｰﾄﾀﾞｯｼｭ, 11/06 put on
#    開始), BD = dash1 121 「dash01」 (BFE has no BD; ダッシュ開始 = the moment the dash moves off, like SD 持続 F0). F0, once.
#  * 硬直: no effect / SE (甲 has none; 村正・ノイの SE removed).
DASH_SE_HOLD = {4: 124, 7: 121}


def _turn_len(ph):
    return max([o['endFrame'] for u in ph['skillUnitCollection'] for o in u['skillInfoObjectList']] + [0]) + 1


def kou_dash_fx(waz_skills, kou_waz, se_obj, se_ref, rep):
    for dst in range(3, 9):
        s = waz_skills[dst]; k = kou_waz['skillList'][dst]
        assert len(s['phasesInfo']) >= 1
        nrm = sum(len(u['skillInfoObjectList']) for ph in s['phasesInfo'] for u in ph['skillUnitCollection'] if u['unitQuantity'] in (48, 52))
        for ph in s['phasesInfo']:
            ph['skillUnitCollection'] = [u for u in ph['skillUnitCollection'] if u['unitQuantity'] not in (48, 52)]
        ph = s['phasesInfo'][0]; L = _turn_len(ph)
        kph = k['phasesInfo'][0]; kL = _turn_len(kph)
        added = []
        for u in kph['skillUnitCollection']:
            q = u['unitQuantity']
            if q == 48 or (q == 52 and dst not in DASH_SE_HOLD):
                u2 = copy.deepcopy(u)
                for o in u2['skillInfoObjectList']:
                    f0 = min(L - 1, int(round(o['startFrame'] * L / float(kL))))
                    f1 = max(f0, min(L - 1, int(round(o['endFrame'] * L / float(kL)))))
                    o['startFrame'], o['endFrame'] = f0, f1
                ph['skillUnitCollection'].append(u2)
                added.append('%d x%d' % (q, len(u2['skillInfoObjectList'])))
        if dst in DASH_SE_HOLD:
            ref = se_ref(DASH_SE_HOLD[dst])
            assert ref is not None, DASH_SE_HOLD[dst]
            u52 = [u for p_ in kou_waz['skillList'][4]['phasesInfo'] for u in p_['skillUnitCollection'] if u['unitQuantity'] == 52][0]
            u2 = copy.deepcopy(u52); u2['skillInfoObjectList'] = [se_obj(ref, 0)]
            ph['skillUnitCollection'].append(u2)
            added.append('52 BFE SE %d -> SeGroup %s' % (DASH_SE_HOLD[dst], ref))
        ph['skillUnitCollection'].sort(key=lambda x: x['unitQuantity'])
        rep.add('BASIC', 'skill %d %s: 村正/ノイ slot 48/52 x%d removed -> 甲 %s (user 2026-11-06)' % (
            dst, k['skillNameJapanese'], nrm, ', '.join(added) or 'none'))
