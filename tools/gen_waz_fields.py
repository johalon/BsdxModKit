#!/usr/bin/env python3
"""Generate tools/waz_fields.json : BSDX .waz field-semantics dictionary (machine readable).

Hand-written semantics (from BaldrSky.exe property tables / readers / damage code and
cross-mech statistics, see notes/05_waz_field_dictionary.md) + value ranges computed
from the NeXAS_DX JSON dumps (work/nexas_rt/json/waz).

usage: python3 gen_waz_fields.py [JSON_WAZ_DIR] [OUT]
"""
import json, os, sys, glob, re, collections
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')    # この作業ツリーの根（tools/ の 1 つ上）

HERE = os.path.dirname(os.path.abspath(__file__))
JDIR = sys.argv[1] if len(sys.argv) > 1 else _ROOT + '/work/nexas_rt/json/waz'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'waz_fields.json')
FACTORY = os.path.dirname(_ROOT) + '/ext/NeXAS_DX/src/main/java/com/giga/nexas/dto/bsdx/waz/wazfactory/SkillInfoFactory.java'

C, L, U = 'CONFIRMED', 'LIKELY', 'UNKNOWN'

# ---------------------------------------------------------------- slot table (72)
SLOT_NAMES = []
SLOT_TYPES = []
for line in open(FACTORY, encoding='utf-8'):
    m = re.search(r'new SkillInfoTypeEntry\((0x[0-9A-Fa-f]+),\s*0x[0-9A-Fa-f]+,\s*"([^"]+)"\)', line)
    if m:
        SLOT_TYPES.append(int(m.group(1), 16)); SLOT_NAMES.append(m.group(2))
assert len(SLOT_NAMES) == 72, len(SLOT_NAMES)

CLASS_OF_TYPE = {0: 'CEventVal', 1: 'CEventVal', 2: 'CEventValRandom', 3: 'CEventValRandom', 4: 'CEventWazaSelect',
                 5: 'CEventTerm', 6: 'CEventTerm', 7: 'CEventMove', 8: 'CEventHeight', 9: 'CEventTerm', 10: 'CEventTerm',
                 11: 'CEventTerm', 12: 'CEventSlipHosei', 13: 'CEventSprite', 14: 'CEventSpriteYure', 15: 'CEventSpriteAttr',
                 16: 'CEventHit', 17: 'CEventEscape', 18: 'CEventCpuButton', 19: 'CEventEffect', 20: 'CEventBlink',
                 21: 'CEventCharge', 22: 'CEventTouch', 23: 'CEventSe', 24: 'CEventVoice', 25: 'CEventScreenYure',
                 26: 'CEventScreenAttr', 27: 'CEventScreenEffect', 28: 'CEventScreenLine', 29: 'CEventRadialLine',
                 30: 'CEventBlur', 31: 'CEventCamera', 32: 'CEventTerm', 33: 'CEventNokezori', 34: 'CEventChange',
                 35: 'CEventStatus'}
TERM_GROUP_OF_TYPE = {5: 20, 6: 4, 9: 18, 10: 18, 11: 23, 32: 21}  # exe factory 0x5db500 -> ctor 0x641ad0(…,group,…)

def F(key, name_ja, typ, sem, conf, editable=True, member=None, unit=None, ev=None):
    d = dict(key=key, name_ja=name_ja, type=typ, semantics=sem, confidence=conf, editable=editable)
    if member: d['exe_member'] = member
    if unit: d['unit'] = unit
    if ev: d['evidence'] = ev
    return d

COMMON = [F('startFrame', '開始フレーム', 'int32', 'ターン内でこのイベントが有効になる最初のフレーム(0始まり)。値型イベントは start→end で補間される', C,
            ev='Sprite が 0-1,2-4,5-36… と連続する。Val 表示関数が (end-start)>1 の時だけ開始値を表示'),
          F('endFrame', '終了フレーム', 'int32', 'イベントが有効な最後のフレーム。ネストされたサブオブジェクトでは意味が異なる(多くは0)', C)]

VAL = [F('int1', '開始値タイプ', 'enum', '0=直値, 1=前の値±(相対)。イベント長が1フレームなら無視', C, ev='0x5f4660 表示関数: "%4d" / "前%c%4d"'),
       F('int2', '開始値', 'int32', '開始値(タイプ1なら前の値への加算量)', C),
       F('int3', '終了値タイプ', 'enum', '0=直値, 1=前の値±, 2=開始値±', C, ev='0x5f4660: "%s%4d" / "%s前%c%4d" / "%s開始値%c%4d"'),
       F('int4', '終了値(=主値)', 'int32', '終了値。1フレームイベントや多くのスロットではこれが実効値', C)]
VALR = [F('int1', '開始値タイプ', 'enum', '0=直値, 1=前の値±', C, ev='0x5f4980'),
        F('int2', '開始値', 'int32', '', C), F('int3', '開始値ランダム幅(±)', 'int32', '"%s(±%4d)"', C),
        F('int4', '終了値タイプ', 'enum', '0=直値, 1=前±, 2=開始値±', C), F('int5', '終了値(=主値)', 'int32', '', C),
        F('int6', '終了値ランダム幅(±)', 'int32', '', C)]
TERM = [F('bsdxInfoCollectionList[0].int1', '条件グループ', 'int32', 'Term.grp のグループ番号。CEvent 型ごとに固定(位置=20, 無効条件=4, 方向=18, 速度タイプ等=23, 攻撃力=21, 変更処理の条件=0, 飛び先=16)', C, editable=False,
          ev='factory 0x5db500 が ctor 0x641ad0 に渡す値とデータの int1 が一致'),
        F('bsdxInfoCollectionList[0].typeList', '項目パス', 'int32[]', 'Term.grp 項目番号の列。先頭はグループ int1 の項目、項目の param2>=0 なら次の値はそのサブグループの項目', L,
          ev='[2,7,16] = 親:オブジェクト→オブジェクト(単体):接触→接触:着地していたら'),
        F('bsdxInfoCollectionList[0].paramList', '数値パラメータ($v1,$v2…)', 'int32[]', '項目文字列の $v1/$v2 に入る値。攻撃力では paramList[0] が威力', C, ev='0x63bf50 = paramList[i] を返す。ダメージ計算 0x63ba40 が使用'),
        F('bsdxInfoCollectionList[0].intList3', '対象選択1', 'int32[]', '項目が対象オブジェクトを要求する時の選択値(オブジェクト/オブジェクト位置の番号)と推定', U),
        F('bsdxInfoCollectionList[0].intList4', '対象選択2', 'int32[]', '同上(位置補正: オブジェクト位置2 など)と推定', U),
        F('bsdxInfoCollectionList[0].int2', '末尾値', 'int32', '不明(0/1)', U)]

def sub(idx, name_ja, cls, sem='', conf=L, editable=True):
    return dict(index=idx, name_ja=name_ja, cls=cls, semantics=sem, confidence=conf, editable=editable)

CLASSES = {}
CLASSES['CEventVal'] = dict(type_ids=[0, 1], exe=dict(read='0x641da0', value_reader='0x5f45f0', display='0x5f4660'),
                            summary='値(開始→終了の補間付き)。int4 が主値', fields=COMMON + VAL)
CLASSES['CEventValRandom'] = dict(type_ids=[2, 3], exe=dict(read='0x642100', value_reader='0x5f4900', display='0x5f4980'),
                                  summary='ランダム幅付きの値。int5 が主値', fields=COMMON + VALR)
CLASSES['CEventWazaSelect'] = dict(type_ids=[4], exe=dict(read='0x643580'), summary='他の waz の技を参照(弾・爆風・ヒットエフェクトの生成)',
    fields=COMMON + [F('wazFileNo', '技ファイル番号', 'int32', 'WazaGroup.grp の番号(0 Effect, 1-5 Tama01-05, 6 Laser, 7 Bomb, 自機 waz も可)', C, ev='Tama01 の技名「ライフル：甲」等が甲の武装と一致'),
                     F('wazSequenceNo', '技番号', 'int32', '参照先 waz 内の技 index', C)])
CLASSES['CEventTerm'] = dict(type_ids=[5, 6, 9, 10, 11, 32], exe=dict(read='0x6417e0', term_reader='0x6660f0', vtable='0x7f4714'),
    summary='条件式/指定子(Term.grp の語彙で記述)。攻撃力・位置・方向などに使う', fields=COMMON + TERM)
CLASSES['CEventSprite'] = dict(type_ids=[13], exe=dict(read='0x640060'), summary='モーション(スプライトアニメ)指定',
    fields=COMMON + [F('spmFileSequence', 'スプライトファイル', 'int32', '-1=自機の spm、それ以外は SpriteGroup.grp の番号', C),
                     F('actionGroupNumber', 'アニメ番号', 'int32', 'spm の animData index(例 sora.spm 0=立ち, 34=ジャンプ着地1)', C, ev='参照される最大パターン番号 < numPat が全件成立(waz_summary で検証)'),
                     F('actionNumber', 'パターン番号', 'int32', 'そのアニメ内の pat index', C)])
CLASSES['CEventHit'] = dict(type_ids=[16], exe=dict(read='0x63b580', write='0x63b3e0', init='0x63bc60', vtable='0x7f2bf8', prop_table='0x7f2ad0', damage_calc='0x63ba40', target_check='0x63b9b0'),
    summary='攻撃判定(スロット41=対メカ, 42=対弾)。威力・ヒット数・のけぞり等の中核',
    fields=COMMON + [
        F('attackTargetType', '攻撃グループ', 'int16 bitmask', '当たる相手: bit0=敵, bit1=味方, bit2=自分(1=敵のみ, 3=敵+味方, 6=味方+自分)', C, member='+0x08', ev='0x63b9b0 が陣営比較で bit 1/2/4 を判定、Karaik の実験と一致'),
        F('short2', '攻撃グループ2', 'int16 bitmask', '第2の対象マスク(既定7)。弾・OBJ 等への当たり指定と推定', L, member='+0x0a', ev='既定値 7'),
        F('int1', 'ヒットカウンタ初期化', 'bool', '1=この判定開始時にヒット済みリストをリセット', L, member='+0x0c', ev='既定1、値は0/1のみ'),
        F('int2', 'フラグ', 'bitmask', '攻撃フラグ(2,4,8,16,32,64…)。各bitの意味は未解析', L, member='+0x10'),
        F('int3', '(名称なし)', 'int32', '0-3。プロパティ名のないメンバ。攻撃Lv/強度の可能性(武装の攻撃Ｌｖと弱い相関)', U, member='+0x14'),
        F('hitCount', 'ヒット数', 'int32', '1判定で与える最大ヒット数。-1/9999=判定中は無制限', L, member='+0x18', ev='既定1, ドリル -1+間隔4'),
        F('hitInterval', 'ヒット間隔', 'int32', '多段ヒットの間隔(フレーム)', L, member='+0x1c', unit='frame'),
        F('minDamage', '攻撃力最低値', 'int32', '補正後ダメージの下限', C, member='+0x20', ev='0x63ba40: cmovl で max(dmg,[+0x20])'),
        F('chargeDamageRate', '攻撃力溜め反映率', 'int32', '>=0 なら dmg×(溜め%+値)/100。-1/-999 等の負値=溜め無効', C, member='+0x24', unit='%', ev='0x63ba40'),
        F('int11', '装甲攻撃力', 'int32', '装甲(スーパーアーマー)への攻撃力倍率%と推定(既定100)', L, member='+0x28', unit='%'),
        F('startComboCorrection', '基底コンボ補正値', 'int32', 'コンボ補正の基底加算', L, member='+0x2c'),
        F('internalCorrection', '攻撃力補正：技のみ', 'int32', '技の中だけで累積する補正(技終了で戻る)', L, member='+0x30'),
        F('midComboCorrection', '攻撃力補正', 'int32', 'コンボ中に累積する補正', L, member='+0x34'),
        F('endCorrection', '攻撃力補正：技終了時', 'int32', '技終了時に加算される補正(7が多い)', L, member='+0x38'),
        F('int13', '自分停止時間', 'int32', 'ヒット時に攻撃側が止まるフレーム', L, member='+0x3c', unit='frame'),
        F('int14', '消滅時間', 'int32', 'ヒット後に(弾が)消えるまでのフレームと推定', L, member='+0x40', unit='frame'),
        F('int15', 'ヒットストップ', 'int32', '被弾側のヒットストップ', L, member='+0x44', unit='frame', ev='int16 とほぼ同分布'),
        F('int16', 'ヒットストップ（自機）', 'int32', '攻撃側のヒットストップ', L, member='+0x48', unit='frame'),
        F('int17', 'スロー反映率', 'int32', '既定100', L, member='+0x4c', unit='%', ev='init で 100'),
        F('int18', '画面：拡大縮小時間', 'int32', 'ヒット時の画面ズーム時間', L, member='+0x50', unit='frame'),
        F('screenShakeFrame', '画面：振動時間', 'int32', 'ヒット時の画面振動時間', L, member='+0x54', unit='frame'),
        F('int20', '鉄ヒットＳＥ', 'int32', '金属ヒット音関連(0/10/20)。意味未確定', U, member='+0x58'),
        F('int21', 'ダメージ色時間', 'int32', '被弾フラッシュ時間(既定7)', L, member='+0x5c', unit='frame', ev='init で 7'),
        F('int22', 'キャンセルフラグ', 'int32', '既定2。0/1/2 が大半、弾では 30-200 も', U, member='+0x60'),
        F('selfStunFrame', '(名称なし)', 'int32', '0/1/2。既定1。Karaik は「自機硬直」と命名したが自分停止時間は +0x3c', U, member='+0x64'),
    ],
    subobjects=[sub(6, '攻撃力', 'CEventTerm(group21 ATTACK2)', '威力。typeList[0]: 0=直値 paramList[0], 1=自HPの%, 2=敵HPの%', C),
                sub(16, 'ヒットエフェクト', 'CEventWazaSelect', '通常 Effect.waz の技', C),
                sub(17, 'のけぞり（地上→地上）', 'CEventNokezori', '地上の相手に当たった時', C),
                sub(18, 'のけぞり（空中）', 'CEventNokezori', '空中の相手', C),
                sub(19, 'のけぞり（空中→地上）', 'CEventNokezori', '空中→着地', C),
                sub(20, 'のけぞり（ダウン）', 'CEventNokezori', 'ダウン中の相手', C),
                sub(25, '画面：拡大縮小', 'CEventValRandom', '', L), sub(27, '画面：振動', 'CEventScreenYure', '', L),
                sub(28, 'ヒットＳＥ', 'CEventSe', '', C), sub(32, 'メカステータス増減値', 'CEventStatus', '', U)],
    damage_formula='base = 攻撃力.paramList[0] (type0) | 自HP×p/100 (type1) | 敵HP×p/100 (type2); 条件付きで×1.5; ×(呼び出し側補正%)/100; max(base, 攻撃力最低値); if 溜め反映率>=0: ×(溜め%+溜め反映率)/100   [0x63ba40]')
CLASSES['CEventNokezori'] = dict(type_ids=[33], exe=dict(read='0x63c5d0', init='0x63c960', prop_table='0x7f2d98'),
    summary='のけぞり(被弾リアクション)。Hit のサブオブジェクト17-20',
    fields=COMMON + [
        F('int1', '処理タイプ', 'enum', '0=指定(以下の値を使う), 1=同じ：地上→地上, 2=同じ：空中, 3=同じ：空中→地上, 4=同じ：ダウン, 5=なし', C, member='+0x4c', ev='Term.grp NOKEZORITYPE と同じ6値、データも 0/1/2/4/5'),
        F('short1', 'フラグ', 'int16 bitmask', '', L, member='+0x50'),
        F('int2', '停止時間', 'int32', 'のけぞり停止(硬直)フレームと推定', L, member='+0x54', unit='frame'),
        F('int3', 'ﾋｯﾄﾊﾞｯｸ', 'int32', 'ノックバック量', L, member='+0x58'),
        F('int4', 'ﾋｯﾄﾊﾞｯｸ(のけぞり時)', 'int32', 'のけぞり中に当たった時のノックバック', L, member='+0x5c'),
        F('int5', 'ﾋｯﾄﾊﾞｯｸ:自機補正', 'int32', '攻撃側の押し戻し', L, member='+0x60'),
        F('int6', 'ﾋｯﾄﾊﾞｯｸ:自機補正(のけぞり時)', 'int32', '', L, member='+0x64'),
        F('int7', 'ダウン時間', 'int32', 'ダウン継続フレーム(既定50)', L, member='+0x68', unit='frame', ev='init で 50、データ 50 が93%'),
        F('int8', 'のけぞり速度', 'int32', '吹き飛び/のけぞりの速度(既定10)', L, member='+0x6c', ev='init で 10'),
        F('int9', '速度減速率', 'int32', '既定100', L, member='+0x70', ev='init で 100'),
        F('int10', '吹き飛び規模', 'int32', '浮かせ量(負値あり、-999=特殊)', L, member='+0x74'),
        F('int11', '吹き飛び重力', 'int32', '既定50', L, member='+0x78', ev='init で 50'),
        F('int12', 'バウンドLv', 'int32', '0-6', L, member='+0x7c'),
        F('int13', 'バウンド速度', 'int32', '', L, member='+0x80'),
    ],
    subobjects=[sub(8, 'のけぞり方向', 'CEventTerm(group18 ANGLE)', '既定 [3,…] 角度指定', L),
                sub(9, 'のけぞり速度タイプ', 'CEventTerm(group23 PARAM)', '', L), sub(12, '吹き飛び規模タイプ', 'CEventTerm(group23 PARAM)', '', L)])
EFFECT_SUBS = ['エフェクトタイプ1', 'エフェクトタイプ2', 'フラグ', 'エフェクト番号', '同時発射数', '最大発射数', '発射間隔', '発射位置', '発射位置補正：方向',
               '発射位置補正：方向補正', '発射位置補正：距離', '発射位置補正：高さ', '発射方向：１発ごとの補正', '発射方向：同時発射補正', '発射方向：全体補正',
               '発射ＳＥ', 'ｽﾌﾟﾗｲﾄ：拡大縮小', 'ｽﾌﾟﾗｲﾄ：拡大縮小X', 'ｽﾌﾟﾗｲﾄ：拡大縮小Y', 'ｽﾌﾟﾗｲﾄ：拡大縮小Y(ｽﾛｰ影響)', 'ｽﾌﾟﾗｲﾄ：振動', 'ｽﾌﾟﾗｲﾄ：属性',
               'ｽﾌﾟﾗｲﾄ：方向', 'ｽﾌﾟﾗｲﾄ：方向補正', 'ｽﾌﾟﾗｲﾄ：方向増分', '位置', '位置：分散率', '座標移動', 'ﾍﾞｸﾄﾙ：方向', 'ﾍﾞｸﾄﾙ：方向補正', 'ﾍﾞｸﾄﾙ：方向増分',
               'ﾍﾞｸﾄﾙ：速度', 'ﾍﾞｸﾄﾙ：高さ', 'ﾍﾞｸﾄﾙ：重力', 'ﾍﾞｸﾄﾙ：最低高度', 'ﾍﾞｸﾄﾙ：慣性', '汎用変数', '溜め攻撃力', '影の濃さ', '優先順位補正', '耐久力',
               '記憶ＯＢＪの最大数', '指定OBJ数以下なら生成', '指定画面範囲内なら生成', '指定画面範囲外なら削除']
CLASSES['CEventEffect'] = dict(type_ids=[19], exe=dict(read='0x639600', init='0x639920', prop_table='0x7f2518'),
    summary='弾・エフェクトの発射(生成)。エフェクト番号=生成する技(Tama/Laser/Bomb/Effect)。弾の威力は生成先の技の Hit にある',
    fields=COMMON + [F('int1', 'エフェクトタイプ1', 'enum', '0/1', L, member='+0xbc'), F('int2', 'エフェクトタイプ2', 'enum', '0-3', L, member='+0xc0'),
                     F('int3', 'フラグ', 'bitmask', '1,4,16…', L, member='+0xc4'), F('int4', '発射方向：１発ごとの補正', 'int32', '0-24 と推定', U, member='+0xc8'),
                     F('int5', '(記憶OBJ/画面範囲系)', 'int32', '-1/100-500。記憶ＯＢＪの最大数〜画面範囲のどれか', U, member='+0xcc'),
                     F('int6', '(同上)', 'int32', '-1/0/50-300', U, member='+0xd0'), F('int7', '(同上)', 'int32', '-1/50-300', U, member='+0xd4'),
                     F('int8', '(名称不明)', 'int32', '0/5/6', U, member='+0xd8'), F('int9', '(名称不明)', 'int32', '既定1。1以外は 2-20', U, member='+0xdc'),
                     F('int10', '(名称不明・角度?)', 'int32', '±90 程度', U, member='+0xe0'), F('int11', '(名称不明・角度幅?)', 'int32', '0-360', U, member='+0xe4')],
    subobjects=[sub(i, n, {3: 'CEventWazaSelect', 7: 'CEventTerm(位置)', 15: 'CEventSe', 25: 'CEventTerm(位置)', 20: 'CEventSpriteYure', 21: 'CEventSpriteAttr',
                         27: 'CEventMove', 8: 'CEventTerm(方向)', 22: 'CEventTerm(方向)', 28: 'CEventTerm(方向)'}.get(i, 'CEventVal/ValRandom'),
                    {3: '生成する技(弾)。弾の威力・ヒット数はこの参照先の Hit', 4: '1回に出す数', 5: '合計の最大数', 6: '発射間隔(フレーム)', 37: '溜め時の攻撃力', 40: '弾の耐久力'}.get(i, ''),
                    C if i in (3,) else L) for i, n in enumerate(EFFECT_SUBS) if i not in (0, 1, 2, 12, 41, 42, 43, 44)])
CLASSES['CEventCharge'] = dict(type_ids=[21], exe=dict(read='0x637e50', prop_table='0x7f1fe0'), summary='溜め / 熱チャージ消費',
    fields=COMMON, subobjects=[sub(0, '消費する熱チャージ量', 'CEventVal', 'int4=消費量(100,200,1000…)', L), sub(1, '蓄積する溜め', 'CEventVal', '溜め量', L)])
CLASSES['CEventSe'] = dict(type_ids=[23], exe=dict(read='0x63edf0'), summary='効果音。複数候補から確率で選ぶ',
    fields=COMMON + [F('count', '候補数', 'int32', 'byteDataList の要素数', C, editable=False),
                     F('byteDataList[i] (16B=4×int32)', '候補', 'struct', '{SeGroup.grp カテゴリ番号, カテゴリ内の項目番号, 確率%(100が通常), フラグ(1)}', C, ev='7005/7025 件が実在する SeGroup 項目に解決(残りは空き項目)')])
CLASSES['CEventVoice'] = dict(type_ids=[24], exe=dict(read='0x642d10'), summary='ボイス。複数候補から確率で選ぶ',
    fields=COMMON + [F('int1', 'タイプ', 'enum', '0/1', L), F('int2', '優先順位', 'int32', '0 または 13-29', L), F('int3', '(名称不明)', 'int32', '8 または 3', U),
                     F('result', '候補数', 'int32', '', C, editable=False),
                     F('byteDataList[i] (12B=3×int32)', '候補', 'struct', '{BatVoice.grp キャラ番号(甲=0,レイン=1,ノイ=15), そのキャラの台詞番号, 確率/重み%}', C, ev='キャラ番号が mek VoiceInfo の BatVoice 番号と一致')])
CLASSES['CEventChange'] = dict(type_ids=[34], exe=dict(read='0x637b20', list_reader='0x667100'), summary='変更処理: 条件が成立したら飛び先へ(ターン送り・技移行・終了)。キャンセル/派生/ループの実体',
    fields=COMMON + [F('flag', '条件数', 'int32', 'bsdxInfoCollectionList1 の要素数', C, editable=False),
                     F('bsdxInfoCollectionList1[]', '条件', 'Term(group0 PARENT)', '各条件。[0]=無条件, [2,…]=オブジェクト条件(接触/入力/攻撃/ゲージ…)。複数ある時の結合(AND/OR)は未確認', L),
                     F('bsdxInfoCollectionList2[0]', '飛び先', 'Term(group16 JUMP)', '[0,0]=次のターン, [0,1]+$v1=指定ターン, [0,2]=終了, [1]+$v1,$v2=技ジャンプ, [4]=終了', L),
                     F('int1', '(末尾値)', 'int32', '', U)])
CLASSES['CEventMove'] = dict(type_ids=[7], exe=dict(read='0x63c020'), summary='座標移動', fields=COMMON + [
    F('bsdxInfoCollectionList1[0]', '開始位置', 'Term', '', L), F('bsdxInfoCollectionList2[0]', '終了位置', 'Term', '', L), F('int1', '移動タイプ', 'enum', '', L)])
CLASSES['CEventHeight'] = dict(type_ids=[8], exe=dict(read='0x63af60'), summary='追尾ジャンプ力(高さ合わせ)', fields=COMMON + [F('int1', 'タイプ', 'enum', '', L)],
    subobjects=[sub(1, '最大増分(1=0.01)', 'CEventValRandom'), sub(2, '標的高度補正', 'CEventVal')])
CLASSES['CEventSlipHosei'] = dict(type_ids=[12], exe=dict(read='0x63fdc0', init='0x63fee0'), summary='技後の慣性補正', fields=COMMON + [
    F('long1', '最低速度', 'double', '', L), F('long2', '最高速度', 'double', '', L), F('int1', '最低上昇量', 'int32', '', L), F('int2', '最高上昇量', 'int32', '既定6', L),
    F('int3', '最低重力増分', 'int32', '', L), F('int4', '最高重力増分', 'int32', '既定99999', L)])
CLASSES['CEventSpriteYure'] = dict(type_ids=[14], exe=dict(read='0x6409d0'), summary='スプライト振動', fields=COMMON + [
    F('bsdxInfoCollectionList[0]', '(Term)', 'Term', '角度系の指定と推定', U), F('vibrationAreaType', '振動タイプ', 'enum', '角度指定/左回転/右回転/下/上/左/右/ランダム', L),
    F('vibrationAmplitudeOutToIn', '振幅(開始)', 'int32', '"%s : %4d (周期 : %4d)"', U), F('vibrationAmplitudeInToOut', '振幅(終了)/周期', 'int32', '', U), F('vibrationDampingFactor', '周期/減衰', 'int32', '', U)])
CLASSES['CEventSpriteAttr'] = dict(type_ids=[15], exe=dict(read='0x6404d0'), summary='スプライト描画属性(加算/フェード/色指定…)', fields=COMMON + [
    F('int1', '描画タイプ', 'enum', '0通常 1塗りつぶし 3フィルム 5フェード 6フラッシュ 7半透明 8αブレンド 9加算 10減算 11フェード色 12フラッシュ色 14加算色 18マスク', L)] +
    [F('int%d' % i, '描画パラメータ%d' % (i - 1), 'int32', '値(開始/終了)・色RGB(開始/終了)と推定', U) for i in range(2, 12)])
CLASSES['CEventBlink'] = dict(type_ids=[20], exe=dict(read='0x636d80', init='0x636dd0', prop_table='0x7f1dd8'), summary='残像', fields=COMMON + [
    F('int1', '残像タイプ', 'enum', '', L), F('int2', '発射間隔', 'int32', '既定5', L, unit='frame'), F('int3', 'アニメ時間', 'int32', '既定20', L, unit='frame'),
    F('short1', 'フラグ', 'int16 bitmask', '加算属性/ノーマル/親オブジェクトの拡大率反映/親オブジェクトの属性反映', L)])
CLASSES['CEventTouch'] = dict(type_ids=[22], exe=dict(read='0x641b90', prop_table='0x7f4828'), summary='接触時の挙動(14カテゴリ)', fields=COMMON + [
    F('byteData1 (56B=14×int32)', 'カテゴリ別設定', 'int32[14]', '水平：メカ(敵/味方)・弾(敵/味方)・マップOBJ, 進禁(メカ/弾/穴), 画面端, 垂直：メカ(敵/味方)・弾(敵/味方)・障害物 の順で1つずつ', L)])
CLASSES['CEventEscape'] = dict(type_ids=[17], exe=dict(read='0x639e80', init='0x63a730', prop_table='0x7f2778'), summary='CPU回避(AI用ヒント)', fields=COMMON + [
    F('int1', 'タイプ', 'bitmask', '短打撃/突進/単射撃/連射撃', L), F('int2', '優先順位', 'int32', '', L), F('int3', 'チェック方向補正', 'int32', '', L), F('int4', 'チェック範囲', 'int32', '既定200', L),
    F('int5', 'チェック範囲（高さ）', 'int32', '既定100', L), F('int6', 'チェック高度補正', 'int32', '', L), F('int7', 'チェック回数', 'int32', '', L), F('int8', '回避方向補正', 'int32', '既定90', L)],
    subobjects=[sub(2, 'チェック方向', 'CEventTerm(ANGLE)'), sub(8, '回避方向', 'CEventTerm(ANGLE)')])
CLASSES['CEventCpuButton'] = dict(type_ids=[18], exe=dict(read='0x6386a0', init='0x638810', prop_table='0x7f2180'), summary='CPUボタン入力(AI用)', fields=COMMON + [
    F('int1', 'チェック方向補正', 'int32', '', L), F('int2', 'チェック範囲', 'int32', '既定200', L), F('int3', 'チェック範囲（高さ）', 'int32', '既定100', L),
    F('int4', 'チェック高度補正', 'int32', '', L), F('int5', 'チェック回数', 'int32', '既定1', L), F('short1', 'ボタン入力（範囲内）', 'int16', '', L), F('short2', 'ボタン入力（範囲外）', 'int16', '', L)],
    subobjects=[sub(0, 'チェック方向', 'CEventTerm(ANGLE)')])
CLASSES['CEventScreenYure'] = dict(type_ids=[25], exe=dict(read='0x63e1b0'), summary='画面振動', fields=COMMON + [F('bsdxInfoCollectionList[0]', '(Term)', 'Term', '', U)] + [F('int%d' % i, '(振動パラメータ)', 'int32', 'タイプ(角度指定/回転/上下左右/ランダム)・振幅・周期と推定', U) for i in range(1, 5)])
CLASSES['CEventScreenAttr'] = dict(type_ids=[26], exe=dict(read='0x63d1e0'), summary='画面描画属性(フェード/フラッシュ/ネガ…)', fields=COMMON + [F('int1', '描画タイプ', 'enum', '0フェード 1フラッシュ 2フェード色 3フラッシュ色 4ネガ 5α塗り 6加算塗り 7減算塗り', L)] + [F('int%d' % i, '(パラメータ)', 'int32', '値・色', U) for i in range(2, 10)])
CLASSES['CEventScreenEffect'] = dict(type_ids=[27], exe=dict(read='0x63d6e0'), summary='画面エフェクト', fields=COMMON + [F('int1', '持続カウンタ', 'int32', '', L), F('int2', 'タイプ', 'enum', '', L), F('int3', '速度1', 'int32', '', L), F('int4', '速度2', 'int32', '', L)], subobjects=[sub(4, '方向', 'CEventTerm(ANGLE)')])
CLASSES['CEventScreenLine'] = dict(type_ids=[28], exe=dict(read='0x63dd00'), summary='効果線', fields=COMMON + [F('int%d' % (i + 1), n, 'int32', '', L) for i, n in enumerate(['持続カウンタ', '変化フレーム数', '数', '速度', '長さ', '太さ', '輝度', '色R', '色G', '色B'])], subobjects=[sub(3, '角度', 'CEventTerm(ANGLE)')])
CLASSES['CEventRadialLine'] = dict(type_ids=[29], exe=dict(read='0x63ccf0'), summary='集中線', fields=COMMON + [F('int%d' % (i + 1), n, 'int32', '', L) for i, n in enumerate(['持続カウンタ', 'フレーム数', 'フレーム速度', '数', '距離', '長さ', '太さ', '輝度', 'フェード時間', '色R', '色G', '色B'])], subobjects=[sub(4, '座標', 'CEventTerm(POS)')])
CLASSES['CEventBlur'] = dict(type_ids=[30], exe=dict(read='0x637100'), summary='ブラー', fields=COMMON + [F('bsdxInfoCollectionList[0]', '(Term)', 'Term', '', U)] + [F('int%d' % i, '(パラメータ)', 'int32', '"%3d(%3d,%3d) ⇒ %3d(%3d,%3d)" 開始/終了の(強さ,x,y)と推定', U) for i in range(1, 7)])
CLASSES['CEventCamera'] = dict(type_ids=[31], exe=dict(read='0x6375e0', prop_table='0x7f1f14'), summary='カメラ', fields=COMMON + [F('short1', 'フラグ', 'int16', '', L)],
    subobjects=[sub(0, '位置', 'CEventTerm(POS)'), sub(1, '方向', 'CEventTerm(ANGLE)'), sub(2, '距離', 'CEventVal'), sub(3, '高さ', 'CEventVal')])
CLASSES['CEventStatus'] = dict(type_ids=[35], exe=dict(read='0x640fe0', prop_table='0x7f4530'), summary='パラメータ変動(一時ステータス変化: 最大HP/攻撃力/防御力/速度/冷却…)。使用2件のみ',
    fields=COMMON + [F('byteData1/byteData2/byte1/int1..int9', '(構造未解析)', 'raw', '名前: 追加タイプ, 対象タイプ, 最大HP, ブースター数, FCゲージ数, 打撃/射撃攻撃力, 打撃/射撃防御力, 移動速度×4, 攻撃速度×2, 熱冷却速度, 根性値, データタイプ, 終了タイプ, 終了カウント, 開始時間, 実行間隔, 優先順位, 重複タイプ', U, editable=False)],
    subobjects=[sub(24, 'エフェクト', 'CEventWazaSelect')])
CLASSES['SkillInfoUnknown'] = dict(type_ids=[255], exe={}, summary='スロットごとの付属リスト skillInfoUnknownList {start,end,int1,int2,int3}。(-1,1,-2) が99%。ループ/ブロック範囲の指定と推定',
    fields=COMMON + [F('int1', '(回数?)', 'int32', '-1 が大半(2,3,10…も)', U, editable=False), F('int2', '(?)', 'int32', 'ほぼ1', U, editable=False), F('int3', '(?)', 'int32', '-2 が大半', U, editable=False)])

# ---------------------------------------------------------------- slot semantics
SLOT_SEM = {
    0: ('モーション(アニメ)。フレーム区間ごとに spm アニメ/パターンを指定', C, True),
    1: ('スプライト拡大率(256=等倍と推定)', L, True), 2: ('X方向拡大率', L, True), 3: ('Y方向拡大率', L, True), 4: ('Y拡大率(スロー影響)', L, True), 5: ('拡大率(ベース)', L, True),
    6: ('スプライト振動', L, True), 7: ('スプライト描画属性', L, True), 8: ('スプライトの向き指定(Term ANGLE)', L, True), 9: ('向き補正(度)', L, True), 10: ('向き増分(回転速度)', L, True),
    11: ('位置指定(Term POS)', L, True), 12: ('位置指定の無効条件', L, True), 13: ('位置分散率', L, True), 14: ('座標移動', L, True),
    15: ('移動ベクトルの方向(Term)', L, True), 16: ('移動方向補正(度)', L, True), 17: ('移動方向増分', L, True), 18: ('移動速度(突進速度など)', L, True),
    19: ('ジャンプ力(上昇速度)', L, True), 20: ('追尾ジャンプ力(標的の高さに合わせる)', L, True), 21: ('重力', L, True), 22: ('最低高度', L, True), 23: ('慣性', L, True),
    24: ('ベクトル補正率：移動(%)。入力移動の反映率', L, True), 25: ('ベクトル補正率：技(%)', L, True), 26: ('ベクトル補正率：のけぞり(%)', L, True), 27: ('ベクトル補正率：重力(%)', L, True),
    28: ('ベクトル補正率：ジャンプ力(%)', L, True), 29: ('ベクトル補正率：浮遊(%)', L, True), 30: ('ベクトル補正率：サーチダッシュ(%)', L, True), 31: ('ベクトル補正率：慣性(%)', L, True), 32: ('ベクトル補正率：押し戻し(%)', L, True),
    33: ('技後の慣性補正', L, True), 34: ('耐久力(弾・設置物のHP。int4=400-9000)', L, True), 35: ('汎用変数(技内カウンタ等)', L, True),
    36: ('装甲(スーパーアーマー段階。int4=1-16)', L, True), 37: ('装甲ヒットストップ補正率', L, True), 38: ('無敵(区間内 int4=0/1)', L, True), 39: ('弱点', L, True),
    40: ('熱量: 技の途中で追加される熱(連射系のループターンに多い。int4=50-2000、int3=1 は相対加算)。基本の消費熱は mek 武装の蓄積熱量', L, True),
    41: ('攻撃判定：対メカ', C, True), 42: ('攻撃判定：対弾(弾消し/相殺)', L, True), 43: ('攻撃判定拡大縮小反映率(512 等)', L, True),
    44: ('パラメータ変動(一時ステータス変化)', U, False), 45: ('CPU回避(AI)', L, True), 46: ('CPUボタン入力(AI)', L, True),
    47: ('キャンセルフラグ(int2/int4=0-3。キャンセル可能段階と推定)', L, True), 48: ('エフェクト/弾の発射', C, True), 49: ('残像', L, True), 50: ('溜め・熱チャージ消費', L, True),
    51: ('接触時の挙動', L, True), 52: ('効果音', C, True), 53: ('ボイス', C, True), 54: ('影の濃さ(256/255)', L, True), 55: ('描画優先順位補正', L, True),
    56: ('フォースフィードバック', L, True), 57: ('レーザー：振幅', L, True), 58: ('レーザー：周期', L, True),
    59: ('画面ズーム', L, True), 60: ('画面振動', L, True), 61: ('画面描画属性', L, True), 62: ('画面エフェクト', L, True), 63: ('効果線', L, True), 64: ('集中線', L, True), 65: ('ブラー', L, True), 66: ('カメラ', L, True),
    67: ('攻撃方向(0/180/90 度)', L, True), 68: ('画面停止(区間の長さ=停止フレーム。超技演出)', L, True), 69: ('スロー効果', L, True), 70: ('スロー反映率(%)', L, True),
    71: ('変更処理(条件→飛び先)。キャンセル・派生・ループ・終了', L, True),
}

# ---------------------------------------------------------------- data ranges
def walk_obj(o, prefix, acc):
    for k, v in o.items():
        if k in ('offset', 'typeId', 'slotNum', 'unitSlotNum', 'buffer', 'description') or k.endswith('UnitQuantity'):
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            acc[prefix + k].append(v)
        elif k == 'bsdxInfoCollectionList' and v:
            b = v[0]
            acc['bsdxInfoCollectionList[0].int1'].append(b['int1'])
            if b['typeList']: acc['bsdxInfoCollectionList[0].typeList[0]'].append(b['typeList'][0])
            if b['paramList']: acc['bsdxInfoCollectionList[0].paramList[0]'].append(b['paramList'][0])

def collect():
    top = collections.defaultdict(lambda: collections.defaultdict(list))
    subr = collections.defaultdict(lambda: collections.defaultdict(list))
    slotcount = collections.Counter(); files = collections.Counter()
    for f in sorted(glob.glob(os.path.join(JDIR, '*.waz.json'))):
        d = json.load(open(f, encoding='utf-8'))
        for s in d['skillList']:
            if not s: continue
            for p in s.get('phasesInfo') or []:
                for u in p['skillUnitCollection']:
                    for o in u['skillInfoObjectList']:
                        slotcount[u['unitQuantity']] += 1
                        walk_obj(o, '', top[CLASS_OF_TYPE[o['typeId']]])
                        for lk, lv in o.items():
                            if isinstance(lv, list) and lv and isinstance(lv[0], dict) and 'data' in lv[0]:
                                for su in lv:
                                    if su.get('data'):
                                        walk_obj(su['data'], '', subr[(CLASS_OF_TYPE[o['typeId']], su.get('unitSlotNum'))])
                    for k in u.get('skillInfoUnknownList') or []:
                        walk_obj(k, '', top['SkillInfoUnknown'])
    return top, subr, slotcount

def rng(vals):
    if not vals: return None
    c = collections.Counter(vals)
    return dict(n=len(vals), min=min(vals), max=max(vals), top=[[k, v] for k, v in c.most_common(6)])

def main():
    top, subr, slotcount = collect()
    classes = {}
    for cn, cd in CLASSES.items():
        cd = json.loads(json.dumps(cd))
        for fd in cd['fields']:
            r = rng(top[cn].get(fd['key'].split(' ')[0], []))
            if r: fd['range_seen'] = r
        for sd in cd.get('subobjects', []):
            vals = subr.get((cn, sd['index']))
            if vals:
                sd['range_seen'] = {k: rng(v) for k, v in vals.items() if k not in ('startFrame', 'endFrame')}
            sd['json_path'] = '%s[unitSlotNum==%d].data' % ({'CEventHit': 'ceventHitUnitList', 'CEventNokezori': 'ceventNokezoriUnitList', 'CEventEffect': 'ceventEffectUnitList',
                                                              'CEventCharge': 'ceventChargeUnitList', 'CEventHeight': 'ceventHeightUnitList', 'CEventEscape': 'ceventEscapeUnitList',
                                                              'CEventCpuButton': 'ceventCpuButtonUnitList', 'CEventScreenEffect': 'ceventScreenEffectUnitList',
                                                              'CEventScreenLine': 'ceventScreenLineUnitList', 'CEventRadialLine': 'ceventRadialLineUnitList',
                                                              'CEventCamera': 'ceventCameraUnitList', 'CEventStatus': 'ceventStatusUnitList'}.get(cn, '?'), sd['index'])
        classes[cn] = cd
    slots = []
    for i in range(72):
        sem, conf, ed = SLOT_SEM.get(i, ('', U, False))
        t = SLOT_TYPES[i]
        e = dict(slot=i, name_ja=SLOT_NAMES[i], typeId=t, cls=CLASS_OF_TYPE[t], semantics=sem, confidence=conf, editable=ed, count_seen=slotcount.get(i, 0),
                 json_path='skillList[s].phasesInfo[turn].skillUnitCollection[unitQuantity==%d].skillInfoObjectList[]' % i)
        if t in TERM_GROUP_OF_TYPE: e['term_group'] = TERM_GROUP_OF_TYPE[t]
        if t in (0, 1): e['main_value'] = 'int4'
        if t in (2, 3): e['main_value'] = 'int5'
        slots.append(e)
    out = dict(
        format='BSDX waz field dictionary v1 (2026-10-22)',
        source_json='NeXAS_DX JSON (hutool JSONUtil) — tools/run_roundtrip.sh → work/nexas_rt/json/waz/*.waz.json',
        exe='BaldrSky.exe (BALDR SKY DiveX) — addresses are VAs',
        confidence_levels={C: 'exe コード/表 または全件データ検証で裏付け', L: 'プロパティ名の並び・既定値・統計から高確度で推定', U: '不明/仮説のみ'},
        structure=dict(
            skill='skillList[i] = null(空き) | {skillNameJapanese, skillNameEnglish, phaseQuantity, phasesInfo[], skillSuffixList[]}',
            turn='phasesInfo[t] = 「ターン」(Term.grp の TURN/ターンジャンプ の単位。NeXAS_DX の "phase")。skillUnitCollection = 存在するスロットだけ並ぶ',
            slot='skillUnitCollection[k] = {unitQuantity=スロット番号(0-71), unitDescription, skillInfoObjectList[]=そのスロットのイベント列, skillInfoUnknownList[]}',
            event='各イベントは startFrame/endFrame を持つタイムライン要素。値型は開始→終了で補間',
            suffix='skillSuffixList[k] = {int1=ターン番号(0,1,2…), int2=0 が通常}。要素数≒ターン数。エディタのツリー表示用と推定 (LIKELY, editable=false)',
            weapon='mek.mekWeaponInfoMap[n].wazSequence = 自機 waz の技 index(甲は Lv1 の技。Lv2/Lv3 は名前上 +1/+2)',
            term='CEventTerm/Change/Move 等の bsdxInfoCollection は Term.grp(30グループ)の語彙による式。int1=グループ, typeList=項目パス, paramList=$v 値'),
        slots=slots, classes=classes,
        mek_weapon=[F('weaponName', 'ヘッダ名(武装名)', 'string', '', C), F('weaponSequence', 'コード名', 'string', '', C), F('weaponDescription', '解説', 'string', '', C),
                    F('switchToMekNo', 'メカグループ番号', 'int32', '使用時に切り替わる機体(-1=なし)', L), F('wazSequence', '技番号', 'int32', '自機 waz の技 index', C),
                    F('forceCrashAmount', '攻撃Ｌｖ', 'int32', '技を出したときの FC ゲージ増加量。(値+1)×100（1 本 = 10000）= 0→+1%、3→+4%。WeaponInfo +0x64。FC・イニも消費の前に加算。ヒット時・被弾時の増加には関係しない（調査記録 70）', C, ev='技の開始 0x61ce33-0x61ce43 → 加算関数 0x6173d0。+0x68/+0x6c = 熱（0x65bdb0）との並びで +0x64 = この欄。バニラ 0-3'),
                    F('heatMaxConsumption', '蓄積熱量：初期値', 'int32', '使用時に溜まる熱(熟練前)', C), F('heatMinConsumption', '蓄積熱量：最小値', 'int32', '熟練後の熱', C),
                    F('upgradeExp', '必要経験値', 'int32', '', C), F('startPointWhenDemonstrate', 'デモ時の距離', 'int32', '', C),
                    F('weaponCategory', 'カテゴリ', 'enum', '0通常 1FC 2イニシャライザ', C), F('weaponType', '攻撃タイプ', 'enum', '0格闘 1射撃', C),
                    F('meleeSkillFlag..defensiveWeaponSkillFlag', 'タイプ：格闘技/武器/ミサイル/実弾/光学兵器/ビット/爆発物/防御兵器', 'int32×8', '>0 でタグ表示', C),
                    F('weaponIdentifier', 'フラグ', 'enum', '0通常 1HC 2非表示', L), F('weaponUnknownProperty19', '(名称なし)', 'int32', '全件1', U, editable=False)],
    )
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('wrote', OUT, 'slots', len(slots), 'classes', len(classes))

if __name__ == '__main__':
    main()
