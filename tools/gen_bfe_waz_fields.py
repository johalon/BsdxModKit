#!/usr/bin/env python3
"""gen_bfe_waz_fields.py - generate tools/bfe_waz_fields.json (BALDR FORCE EXE data-format dictionary).

Source of truth: unprotected BaldrForce.exe (2003-01-12 link, 983,040 B) which still contains the
in-house WAZ/CPU editor dialogs (RT_DIALOG 107..188) and their dialog procedures.  Offsets were
taken from the editor's init functions (SetDlgItemInt/CheckDlgButton/CheckRadioButton reading
[struct+off]) and EN_CHANGE handlers (helper 0x43ccb0(hDlg,id,signed,min,max,ptr,size)), and
cross-checked against runtime code where noted.  See notes/07_bfe_exe_analysis.md.

conf: CONFIRMED = offset+meaning proven by exe code (editor label bound to the offset, and/or
      runtime use), LIKELY = offset proven, meaning/units inferred, UNKNOWN = no evidence.
Usage: python3 tools/gen_bfe_waz_fields.py [exe] -> writes tools/bfe_waz_fields.json
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'work', 'bfe_disc_exe', 'x', 'BaldrForce.exe')
C, L, U = 'CONFIRMED', 'LIKELY', 'UNKNOWN'


def F(off, typ, name, ja, conf=C, **kw):
    d = dict(off=off, type=typ, name=name, ja=ja, conf=conf)
    d.update(kw)
    return d


# generic "calc" (計算) blocks: every value is a random range [a,b] (runtime picks a+rand()%(b-a+1));
# -32768 (0x8000) in the first value = "do not update".  Proven at 0x440b70 (speed) / 0x4401bc (jump).
RANGE_NOTE = 'pair = random range [min,max]; -32768 = keep current (runtime 0x440b70)'

S = {}
S['skill_header'] = dict(size=0x6C, ja='技ヘッダ (WAZA_BRAIN dlg113 / TAMA_BRAIN dlg118)', fields=[
    F(0x00, 'char[40]', 'name', '技名 (cp932, NUL 以降はゴミ)'),
    F(0x28, 'u8', 'group', '技グループ', enum='skill_group'),
    F(0x29, 'u8', 'kind', '技タイプ (0=打撃→攻撃側の打撃威力, 1=射撃→射撃威力, 2=特殊)', enum='skill_kind',
      note='damage uses attacker +0x12 if kind!=0 else +0x0e (0x4423aa)'),
    F(0x2A, 'u16', 'heat', '消費OH (ヒート増加量; ゲージ最大 130)', note='mech heat max = 0x82 (0x41b826)'),
    F(0x2C, 'u16', 'max_hits', '最大HIT数 (9999=無制限)', conf=L),
    F(0x2E, 'u16', 'action_counter', '総合行動カウンタ', conf=L),
    F(0x30, 'u16', 'exp', 'EXP (次Lvまでの経験値; Lv3=0)', conf=L),
    F(0x32, 'u8[2]', 'pad32', 'pad (0xCC)'),
    F(0x34, 'i32', 'ai_distance', '距離 (AI 用の間合い)', conf=L),
    F(0x38, 'i32', 'ai_height', '高さ (AI 用)', conf=L),
    F(0x3C, 'bits8', 'range_bits', '距離 bit0=近 bit1=中 bit2=遠', bits=['近距離', '中距離', '遠距離']),
    F(0x3D, 'bits8', 'height_bits', '高さ bit0=上 bit1=中 bit2=下', bits=['上', '中', '下']),
    F(0x3E, 'u8[32]', 'alg_list', 'アルゴリズムリスト = 実行するフェーズ番号の並び (99=終端)'),
    F(0x5E, 'struct:loop[4]', 'loops', 'ループ情報×4 {終了位置, 開始位置, ループ数} (99=未使用)', note='entry=3 bytes'),
    F(0x6A, 'u8', 'phase_count', 'フェーズ数'),
    F(0x6B, 'u8', 'pad6b', 'pad'),
])
S['loop'] = dict(size=3, ja='ループ情報 (dlg162)', fields=[
    F(0, 'u8', 'end', '終了 (alg_list 上の位置)'), F(1, 'u8', 'start', '開始'), F(2, 'u8', 'count', 'ループ数')])

S['calc_speed'] = dict(size=15, ja='計算（速度） dlg167', note=RANGE_NOTE, fields=[
    F(0, 'i16[2]', 'init', '初期値 [min,max] (<<8 して速度に)'), F(4, 'i16[2]', 'final', '最終値'),
    F(8, 'i16[2]', 'step', '増分 (符号は初期→最終の向きに自動)'),
    F(12, 'i8', 'rate_move', '移 (補正率)', conf=L), F(13, 'i8', 'rate_hit', '喰 (補正率)', conf=L),
    F(14, 'i8', 'rate_wind', '風 (補正率)', conf=L)])
S['calc_dir'] = dict(size=23, ja='計算（移動方向／チップ方向） dlg168/169/178', note=RANGE_NOTE + '; angle 0-360', fields=[
    F(0, 'u8', 'type', '移動タイプ/向きタイプ (radio)', enum='dir_type'),
    F(1, 'bits8', 'flags', 'フラグ (最短ﾙｰﾄ自動ﾁｪｯｸ, 常に方向ﾁｪｯｸ, ...)'),
    F(2, 'i16[2]', 'init', '初期値'), F(6, 'i16[2]', 'final', '最終値'), F(12, 'i32[2]', 'step', '増分'),
    F(20, 'i8', 'rate_move', '移', conf=L), F(21, 'i8', 'rate_hit', '喰', conf=L), F(22, 'i8', 'rate_wind', '風', conf=L)])
S['calc_jump'] = dict(size=23, ja='計算（ジャンプ） dlg170: 二次関数 x 方式', note=RANGE_NOTE + ' (runtime 0x440190)', fields=[
    F(0, 'bits8', 'flags', 'ﾊﾞｳﾝﾄﾞ(1/2)/最低高さを直値に/軌道をそのままに/高さ差分を強引に足す/上昇・下降ﾘﾐｯﾄ解除',
      bits=['ﾊﾞｳﾝﾄﾞ(1/2)', '最低高さを直値に', '軌道をそのままに', '高さ差分を強引に足す', '上昇下降ﾘﾐｯﾄ解除']),
    F(1, 'i8[2]', 'x_start', '二次関数の x 開始位置 = 初速 (<<8 → 縦速度 +0x304)'),
    F(4, 'i16[2]', 'dx_init', 'x の増分 初期値 (=重力)'), F(8, 'i16[2]', 'dx_final', 'x の増分 最終値'),
    F(12, 'i16[2]', 'dx_step', 'x の増分 増分'), F(16, 'i16[2]', 'min_height', '最低高さ差分'),
    F(20, 'i8', 'rate_move', '移', conf=L), F(21, 'i8', 'rate_hit', '喰', conf=L), F(22, 'i8', 'rate_wind', '風', conf=L)])
S['calc_zoom'] = dict(size=14, ja='計算（ズーム／拡大縮小） dlg172', note=RANGE_NOTE + '; 256=等倍', fields=[
    F(0, 'u8', 'type', 'タイプ 0=なし 1=処理する'), F(1, 'bits8', 'flags', 'フラグ'),
    F(2, 'i16[2]', 'init', '初期値'), F(6, 'i16[2]', 'final', '最終値'), F(10, 'i16[2]', 'step', '増分')])
S['calc_camera'] = dict(size=8, ja='計算（カメラ） dlg171', fields=[
    F(0, 'u8', 'move', 'カメラ移動 0=変化なし 1=自分と標的の間へ 2=ヒット位置へ 3=自分の位置へ 4=敵の位置へ'),
    F(1, 'bits8', 'flags', 'フラグ'), F(2, 'i16', 'init', '初期値'), F(4, 'i16', 'final', '最終値'), F(6, 'i16', 'step', '増分')])
S['calc_effect'] = dict(size=6, ja='計算（エフェクト） dlg173: Effect.spr のエフェクト生成', fields=[
    F(0, 'i16', 'effect_no', 'エフェクト番号 (Bmp\\Effect\\Effect.spr のアニメ番号, -1=なし)', conf=L),
    F(2, 'bits8', 'flags', 'フラグ'), F(3, 'u8', 'scale', '出現規模'),
    F(4, 'i8', 'rect_slot', '判定番号 (SPR の判定スロットの位置に出す)', conf=L)])
S['hit'] = dict(size=0x30, ja='技：ヒット情報 dlg107 (WAZA_HIT)', fields=[
    F(0x00, 'bits8', 'flags', 'フラグ', bits=['ﾋｯﾄ中も高さ可変', '鉄と鉄のぶつかるSE', 'ﾀﾞﾒｰｼﾞ大ﾎﾞｲｽ', '装甲へのﾀﾞﾒｰｼﾞ2倍',
                                             'HIT規模を全弾更新', 'ﾀﾞﾒｰｼﾞ処理をしない', '全ﾋｯﾄ後装甲を維持', '未定'],
      note='bit3 doubles armor damage (0x44264f)'),
    F(0x01, 'u8', 'element', '属性 0=無 1=炎 2=氷 3=雷', enum='element'),
    F(0x02, 'u8', 'damage_type', 'ﾀﾞﾒｰｼﾞﾀｲﾌﾟ 0=NORMAL (1,2=未定)'),
    F(0x04, 'i16', 'power', '威力', note='dmg = power*P/10 - combo*P/10, P=攻撃側 打撃/射撃威力(既定10); '
                                       'then +heat bonus, *(100-防御力)/100 (0x44245d-0x442504)'),
    F(0x06, 'i16', 'min_power', '最低威力 (ダメージ下限)'),
    F(0x08, 'i16', 'combo_corr', 'ｺﾝﾎﾞ補正 (被弾側の補正蓄積 +0x110 に加算; 以降のヒットを減衰)'),
    F(0x0A, 'u8', 'hit_wait', 'ﾋｯﾄｳｪｲﾄ (ヒットストップ; 振動時間の計算にも使用 0x441bb2)'),
    F(0x0B, 'u8', 'hit_scale', 'HIT規模', conf=L),
    F(0x0C, 'u8', 'hits_mech', 'HIT数(ｷｬﾗ) 254=当たらない 255=無限'),
    F(0x0D, 'u8', 'hits_weapon', 'HIT数(兵器=弾) 254=当たらない 255=無限'),
    F(0x0E, 'i16', 'shake_scale', '振動規模'),
    F(0x10, 'i16', 'timer_explode', '時限爆破', conf=L),
    F(0x12, 'i16', 'se', '効果音 (SE 表 index, -1=なし)', enum='se'),
    F(0x14, 'u8', 'ko_voice_rate', 'やられ声確率 %'),
    F(0x16, 'struct:calc_effect', 'effect_mech', 'ヒットエフェクト：メカ'),
    F(0x1C, 'struct:calc_effect', 'effect_weapon', 'ヒットエフェクト：弾'),
    F(0x22, 'struct:calc_zoom', 'zoom', '拡大縮小')])
S['noke'] = dict(size=14, ja='技：のけぞり情報 dlg164 (WAZA_NOKE)', fields=[
    F(0x00, 'bits8', 'flags', 'フラグ bit0=親速度>のけぞり速度'),
    F(0x01, 'u8', 'direction', 'のけぞり方向 0=のけぞらない 1=自分→相手 2=自分の移動方向 3=自分の親→相手 4=大元のﾒｶ→相手'),
    F(0x02, 'u8', 'launch_accum', '吹き飛び蓄積量 (被弾側 +0x30a に加算、100 以上で吹き飛び) 0x441db1'),
    F(0x03, 'i8', 'noke_count', 'のけぞり回数', conf=L),
    F(0x04, 'i8', 'move_hinder', '移動妨害率 %', conf=L),
    F(0x06, 'i16', 'speed_init', '速度 初期値'), F(0x08, 'i16', 'speed_final', '速度 最終値'), F(0x0A, 'i16', 'speed_step', '速度 増分'),
    F(0x0C, 'i8', 'launch', '規模 (吹き飛びジャンプの二次関数 x = 初速、<<8) 0x441df3'),
    F(0x0D, 'i8', 'launch_down', '規模(ダウン時) (ダウン中に当たった時の浮き)')])
S['fire'] = dict(size=0x54, ja='弾：発射情報 dlg119 (TAMA_FIRE) + 指定方向に発射 dlg174/179', fields=[
    F(0x00, 'i16', 'tama', 'Tama.dat の技番号 (-1=なし)'),
    F(0x02, 'u8', 'fire_type', '発射ﾀｲﾌﾟ 0=弾(通常) 1=ﾚｰｻﾞｰ(通常) 2=ﾚｰｻﾞｰ(ｳﾈｳﾈ)'),
    F(0x03, 'u8', 'range_type', '射程ﾀｲﾌﾟ 0=打撃 1=射撃'),
    F(0x04, 'i16', 'se', '発射効果音 (SE index, -1=なし)', enum='se'),
    F(0x06, 'bits8', 'flags', 'フラグ bit0=壁あれば撃たない bit1=効果音確率1/2'),
    F(0x07, 'bits8', 'flags2', '各ﾌﾗｸﾞ (1発単位で更新(角度補正/ﾗﾝﾀﾞﾑ角度)、角度補正往復ﾙｰﾌﾟ …)'),
    F(0x0C, 'u8', 'dir_mode', '発射方向 0=追尾 1=相対位置 2=絶対位置 3=前回の弾方向'),
    F(0x0D, 'u8', 'chip_dir', 'ﾁｯﾌﾟ向き 0=発射方向 1=標的方向 2=親方向'),
    F(0x0E, 'i16', 'loops', 'ループ数 / 最大出現数(179)'),
    F(0x10, 'i16[3]', 'count', '同時発射数 初期/最終/増分'),
    F(0x16, 'i16[3]', 'interval', '発射間隔 初期/最終/増分'),
    F(0x1C, 'i16[2]+i32', 'angle_corr', '角度補正 初期/最終/増分(i32 @0x20)'),
    F(0x24, 'i16[2]+i32', 'angle_rand', 'ﾗﾝﾀﾞﾑ角度 初期/最終/増分(i32 @0x28)'),
    F(0x2C, 'i16[2]+i32', 'pos_corr', '座標補正 初期/最終/増分(i32 @0x30)'),
    F(0x34, 'i16[2]+i32', 'height_corr', '高さ補正 初期/最終/増分(i32 @0x38)'),
    F(0x3C, 'struct:target', 'origin', '発射位置 (標的計算)'),
    F(0x4C, 'struct:calc_effect', 'muzzle_effect', '発射位置ｴﾌｪｸﾄ'),
    F(0x52, 'u8[2]', 'pad', 'pad')])
S['shake'] = dict(size=4, ja='計算（振動） dlg175', fields=[
    F(0, 'u8', 'where', '振動させる個所 0=なし 1=初回 2=着地時 3=弾発射時'),
    F(1, 'i8', 'stop', '停止時間'), F(2, 'i8', 'scale', '振動規模'), F(3, 'u8', 'pad', 'pad')])
S['blink'] = dict(size=16, ja='計算（残像） dlg186', fields=[
    F(0, 'u8', 'type', 'タイプ 0=なし 1=ノーマル残像 2=色残像'), F(1, 'bits8', 'flags', 'フラグ'),
    F(2, 'i16[2]', 'init', '初期値 (R…)', conf=L), F(6, 'i16[2]', 'final', '最終値', conf=L), F(10, 'i16[2]', 'step', '増分', conf=L)])
S['target'] = dict(size=16, ja='計算（標的） dlg176: ロック座標/発射位置', fields=[
    F(0, 'bits8', 'flags', 'ｚ軸は変更しない/判定ではなく座標差分を採用/処理しない'),
    F(1, 'u8', 'type1', '標的ﾀｲﾌﾟ① 0=判定 1=前回(更新) 2=自分 3=親 4-6=ﾛｯｸ座標1-3 7-10=弾(前/後/最初/最後) 11=大元のﾒｶ 12=現情報+相対 13=最も近いOBJ 14=ヒットした物体 15=発射目標(固定) 16=前回(非更新)', conf=L),
    F(2, 'u8', 'type2', '標的ﾀｲﾌﾟ② (なし/親/ﾛｯｸ座標…)', conf=L),
    F(4, 'i32', 'depth1', '階層の深さ①'), F(8, 'i32', 'depth2', '階層の深さ②'),
    F(12, 'u8[4]', 'judge', '判定設定 dlg177 (処理タイプ/判定スロット)', conf=U)])

S['phase'] = dict(size=0x18C, ja='フェーズ (= アルゴリズム, WAZA_ALG_BRAIN dlg165); ファイル上は 0x18C=396 バイト',
                  note='go_* (変化先): -99=なし, 99=技終了, 0..n=フェーズ番号, -1=? (LIKELY 次へ). 通常は spr_event を全部再生し終えると alg_list の次へ進む', fields=[
    F(0x000, 'bits8', 'flags', '各ﾌﾗｸﾞ', bits=['着地時煙出す', 'ﾐｻｲﾙ炎＆煙', '装甲弾き→動き停止', '浮遊状態維持',
                                           '未定', 'ｽﾍﾟｼｬﾙ技演出', '空ｷｬﾝｾﾙ', 'ｷｬﾝｾﾙﾌﾗｸﾞ初期化']),
    F(0x001, 'u8', 'touch_mech_ally', '接触: メカ(味方)', enum='touch'),
    F(0x002, 'u8', 'touch_mech_enemy', '接触: メカ(敵)', enum='touch'),
    F(0x003, 'u8', 'touch_shot_ally', '接触: 弾(味方)', enum='touch'),
    F(0x004, 'u8', 'touch_shot_enemy', '接触: 弾(敵)', enum='touch'),
    F(0x005, 'u8', 'touch_obj', '接触: OBJ', enum='touch'),
    F(0x006, 'u8', 'touch_noentry', '接触: 進禁', enum='touch'),
    F(0x007, 'u8', 'touch_screen', '接触: 画面端', enum='touch'),
    F(0x008, 'i8', 'smoke_speed', '煙出る速度'),
    F(0x00A, 'i8', 'go_air', '変化(1回): 空中時 → フェーズ番号'),
    F(0x00B, 'i8', 'go_end', '変化(1回): ｱﾙｺﾞﾘｽﾞﾑ終了時'),
    F(0x00C, 'i8', 'go_anim_end', '変化(1回): ｽﾌﾟﾗｲﾄｱﾆﾒ終了時'),
    F(0x00D, 'i8', 'go_hits_le_mech', '変化(1回): 指定ﾋｯﾄ以下(ｷｬﾗ) [param @0x1A]'),
    F(0x00E, 'i8', 'go_hits_le_weapon', '変化(1回): 指定ﾋｯﾄ以下(兵器) [param @0x1C]'),
    F(0x00F, 'i8', 'go_land', '変化(随時): 地面着地時'),
    F(0x010, 'i8', 'go_obstacle', '変化(随時): 障害物ヒット時'),
    F(0x011, 'i8', 'go_hit_mech', '変化(随時): ｷｬﾗに指定ヒット時 [param @0x1E]'),
    F(0x012, 'i8', 'go_hit_weapon', '変化(随時): 兵器に指定ヒット時 [param @0x20]'),
    F(0x013, 'i8', 'go_dist_in', '変化(随時): 指定距離内時 [param @0x22]'),
    F(0x014, 'i8', 'go_dist_out', '変化(随時): 指定距離外時 [param @0x24]'),
    F(0x015, 'i8', 'go_origin_null', '変化(随時): 原点NULL時'),
    F(0x016, 'i8', 'go_mech_spr', '変化(随時): ﾒｶｽﾌﾟﾗｲﾄNo変化時'),
    F(0x017, 'i8', 'go_mech_alg', '変化(随時): ﾒｶｱﾙｺﾞNo変化時'),
    F(0x018, 'i8', 'go_mech_skill', '変化(随時): ﾒｶ別技使用時'),
    F(0x019, 'i8', 'go_counter', '変化(随時): 総合ｶｳﾝﾀ到達時'),
    F(0x01A, 'i16', 'p_hits_le_mech', 'param 指定ﾋｯﾄ以下(ｷｬﾗ)'),
    F(0x01C, 'i16', 'p_hits_le_weapon', 'param 指定ﾋｯﾄ以下(兵器)'),
    F(0x01E, 'i16', 'p_hit_mech', 'param ｷｬﾗに指定ヒット'),
    F(0x020, 'i16', 'p_hit_weapon', 'param 兵器に指定ヒット'),
    F(0x022, 'i16', 'p_dist_in', 'param 指定距離内'),
    F(0x024, 'i16', 'p_dist_out', 'param 指定距離外'),
    F(0x026, 'struct:calc_speed', 'speed', '速度 (詳細設定ボタン 5702)'),
    F(0x038, 'struct:calc_dir', 'move_dir', '移動方向 (5703)'),
    F(0x050, 'struct:calc_dir', 'chip_dir', 'チップ向き (5704 / ﾚｰｻﾞｰ用 5714)'),
    F(0x068, 'struct:calc_jump', 'jump', 'ジャンプ (5705)'),
    F(0x080, 'struct:calc_zoom', 'screen_zoom', '画面拡縮 (5710)'),
    F(0x08E, 'struct:calc_camera', 'camera', 'カメラ (5711)'),
    F(0x096, 'struct:hit', 'hit', 'ヒット (5706)'),
    F(0x0C6, 'struct:noke', 'noke_mech', 'のけぞり(ﾒｶ) (5707) ※被弾側メカへ'),
    F(0x0D4, 'struct:noke', 'noke_shot', 'のけぞり(弾) (5708)'),
    F(0x0E2, 'struct:calc_effect', 'effect_always', '常時ｴﾌｪｸﾄ (1052)'),
    F(0x0E8, 'struct:calc_effect', 'effect_land', '着地ｴﾌｪｸﾄ (1053)'),
    F(0x0F0, 'struct:fire', 'fire', '弾発射 (5709)'),
    F(0x144, 'struct:shake', 'shake', '振動 (5712)'),
    F(0x148, 'struct:blink', 'blink', '残像 (5713)'),
    F(0x158, 'struct:target', 'lock1', 'ﾛｯｸ座標1(原点) (5700)'),
    F(0x168, 'struct:target', 'lock2', 'ﾛｯｸ座標2(移動目標) (5701)'),
    F(0x178, 'struct:target', 'lock3', 'ﾛｯｸ座標3(発射目標) (1789)'),
    F(0x188, 'u8', 'n_events', 'スプライトイベント数 (後続 48B×n)'),
    F(0x189, 'u8[3]', 'pad', 'pad (ゴミ)')])
S['spr_event'] = dict(size=48, ja='スプライト情報 dlg115 (SPR_BRAIN): フェーズ内で順番に再生', fields=[
    F(0x00, 'i16[2]', 'wait', 'WAIT [min,max]: anim_type=0 なら区間フレーム数、=1 なら再生速度%'),
    F(0x04, 'i16', 'anim', 'SPR アニメスロット (tooru.spr の 512 スロット)'),
    F(0x06, 'i16', 'anim_dash', 'ﾀﾞｯｼｭ時 に使う別アニメ (-1=なし)', conf=L),
    F(0x08, 'bits8', 'flags', '各ﾌﾗｸﾞ', bits=['影', '地面にめりこむ', '弾発射位置ﾛｯｸ', '弾発射', '高さ1/2しない影', 'どこにいてもHIT', '未定', '未定']),
    F(0x09, 'u8', 'anim_type', 'ｱﾆﾒﾀｲﾌﾟ 0=指定ｳｪｲﾄに詰める 1=指定％増減させる 2=指定ｳｪｲﾄ間ﾙｰﾌﾟ 3=地面に着地するまで 4=弾を撃ち終わるまで'),
    F(0x0A, 'u8', 'dir_fix', '方向修正 (0-99)', conf=L),
    F(0x0C, 'bits32', 'attack_rects', '攻撃判定 (この区間で有効な SPR 判定スロット)',
      bits=['下段1', '下段2', '中段1', '中段2', '中段3', '中段4', '中段5', '上段1-1', '上段1-2', '上段2', '上段3', '火器1', '火器2', '火器3', '火器4', '未定'],
      note='判定設定 dlg177 names SPR rect slots: 01下段1 02中段1 04上段1 05-08火器1-4 10下段2 11中段2 12上段2 16-18中段3-5 (bit→slot LIKELY)'),
    F(0x10, 'i8', 'armor_rate', '装甲効果率 (>0: 装甲ゲージ減少=dmg/rate, <0: =|rate|*dmg; -99=壊れない) 0x442625'),
    F(0x12, 'i16', 'attr', 'ｱﾄﾘﾋﾞｭｰﾄ (描画属性)', enum='draw_attr'),
    F(0x14, 'i16', 'attr_value', 'ｱﾄﾘﾋﾞｭｰﾄ値'),
    F(0x16, 'i16', 'se_play', '効果音 再生 (SE index, -1=なし)', enum='se'),
    F(0x18, 'i8', 'se_loop', '効果音 ﾙｰﾌﾟ'),
    F(0x1A, 'i16', 'se_stop', '効果音 停止 (SE index)', enum='se'),
    F(0x1C, 'i8', 'voice_kind', 'ボイス 種類 (BatVoice カテゴリ, -1=なし)', enum='voice_category'),
    F(0x1D, 'i8', 'voice_no', 'ボイス 指定 (カテゴリ内 0-3, -1=ランダム?)', conf=L),
    F(0x1E, 'u8', 'voice_rate', 'ボイス発生確率 %'),
    F(0x20, 'struct:calc_zoom', 'zoom', 'スプライト拡大縮小 (256=等倍)'),
    F(0x2E, 'u8[2]', 'pad', 'pad')])

# ---- CPU (AI) file ----
S['cpu_header'] = dict(size=0x32, ja='敵アルゴリズム作成 dlg138 / CPU ファイル先頭。値 = c1 + c2×CPUレベル', fields=[
    F(0x00, 'i16', 'hp_bars', '耐久力 c1 = 追加 HP ゲージ本数 (1本=2080, 最大7) 0x41b654'),
    F(0x02, 'i16', 'hp_bars_lv', '耐久力 c2 (Lvごとの増分)'),
    F(0x04, 'i16', 'armor', '装甲 c1 (装甲ゲージ; プレイヤー既定300)'), F(0x06, 'i16', 'armor_lv', '装甲 c2'),
    F(0x08, 'i16', 'defense', '防御力 c1 (被ダメージ -%)'), F(0x0A, 'i16', 'defense_lv', '防御力 c2'),
    F(0x0C, 'i16', 'melee_pow', '打撃：威力 c1 (既定10, 上限20)'), F(0x0E, 'i16', 'melee_pow_lv', '打撃：威力 c2'),
    F(0x10, 'i16', 'melee_heat', '打撃：ﾋｰﾄ率 c1 (%) (c2 は Lv ごとに減算)'), F(0x12, 'i16', 'melee_heat_lv', '打撃：ﾋｰﾄ率 c2'),
    F(0x14, 'i16', 'shot_pow', '射撃：威力 c1'), F(0x16, 'i16', 'shot_pow_lv', '射撃：威力 c2'),
    F(0x18, 'i16', 'shot_heat', '射撃：ﾋｰﾄ率 c1'), F(0x1A, 'i16', 'shot_heat_lv', '射撃：ﾋｰﾄ率 c2'),
    F(0x1C, 'i16[2]', 'money', '入手金額', conf=L),
    F(0x20, 'u8', 'mech_type', 'ﾒｶの型 0=ｽﾀﾝﾀﾞｰﾄﾞ 1=多脚型'),
    F(0x22, 'i16', 'se_walk', '歩行 SE (足音)', enum='se'), F(0x24, 'i16', 'se_dash1', 'ﾀﾞｯｼｭ1 SE (開始)', enum='se'),
    F(0x26, 'i16', 'se_dash2', 'ﾀﾞｯｼｭ2 SE (継続)', enum='se'), F(0x28, 'i16', 'se_dash3', 'ﾀﾞｯｼｭ3 SE (停止)', enum='se'),
    F(0x2A, 'i16', 'se_sdash', 'Sﾀﾞｯｼｭ SE', enum='se'), F(0x2C, 'i16', 'se_down', 'ﾀﾞｳﾝ SE', enum='se'),
    F(0x2E, 'i16', 'n_move', 'CPU移動 件数 (ファイル上は直後にもう一度 u16)'),
    F(0x30, 'u8[2]', 'pad', '(ポインタ残骸)')])
S['cpu_cond'] = dict(size=0x24, ja='発動条件 dlg180 + メカ状態による発動条件 dlg181', fields=[
    F(0x00, 'u8', 'priority', '優先順位'), F(0x01, 'u8', 'need_cpu_lv', '必要CPUﾚﾍﾞﾙ'),
    F(0x04, 'i32', 'hp_le', '指定HP以下で発動'), F(0x08, 'i32[2]', 'range', '発動範囲 min～max'),
    F(0x10, 'i32[2]', 'height', '高さ範囲 min～max'),
    F(0x18, 'bits32', 'self_state', '条件(自分) メカ状態ビット', conf=L,
      bits=['地上:停止', '地上:歩行', '地上:ﾀﾞｯｼｭ', '地上:Sﾀﾞｯｼｭ', '空中:停止', '空中:歩行', '空中:ﾀﾞｯｼｭ', '空中:Sﾀﾞｯｼｭ', 'のけぞり', '吹き飛び', 'ダウン', '起き上がり']),
    F(0x1C, 'bits32', 'enemy_state', '条件(敵)', conf=L),
    F(0x20, 'i16', 'prob', '発動確率 (‰?)', conf=L), F(0x22, 'i16', 'prob_cpu', '発動確率CPU補正')])
S['cpu_move'] = dict(size=0x60, ja='CPU移動 dlg182 (ファイル: header の後 u16 n + 96B×n)', fields=[
    F(0x00, 'bits16', 'flags', 'ﾌﾗｸﾞ ﾀﾞｯｼｭ硬直なし/標的随時ﾁｪｯｸ/位置加工随時ﾁｪｯｸ/方向±ﾗﾝﾀﾞﾑ/…/完全浮遊'),
    F(0x02, 'u8', 'type', 'ﾀｲﾌﾟ 0=停止 1=歩行 2=ﾀﾞｯｼｭ 3=ｼｮｰﾄﾀﾞｯｼｭ'),
    F(0x03, 'u8', 'target', '標的 0=ﾗﾝﾀﾞﾑ位置 1=攻撃目標 2=味方'), F(0x04, 'i32', 'target_var', '標的 変数'),
    F(0x08, 'u8', 'pos_mod', '位置加工 0=なし 1=回転'), F(0x0C, 'i32', 'pos_var', '位置加工 変数 (角度)'),
    F(0x10, 'u8', 'speed_type', '速度 0=通常 1=慣性'), F(0x14, 'i32', 'speed', '移動速度'), F(0x18, 'i32', 'inertia', '慣性規模'),
    F(0x1C, 'u8', 'rise', '上昇 0=しない 1=ジャンプ 2=浮遊'), F(0x20, 'i32[2]', 'rise_var', '上昇 変数1/2'),
    F(0x28, 'u8', 'algo', '移動ｱﾙｺﾞﾘｽﾞﾑ 0=通常 1=壁よけ'), F(0x2C, 'i32', 'algo_var', '移動ｱﾙｺﾞ 変数'),
    F(0x30, 'i16', 'pre_wait', '移動前の隙'), F(0x32, 'i16', 'time', '移動時間'), F(0x34, 'i16', 'attack_prob', '攻撃確率'),
    F(0x38, 'struct:cpu_cond', 'cond', '発動条件'), F(0x5C, 'u8[4]', 'end_cond', '終了条件', conf=U)])
S['cpu_attack'] = dict(size=0x30, ja='CPU攻撃 dlg185 (コンボ1段)', fields=[
    F(0x00, 'bits8', 'flags', 'bit?=動かなくする', conf=L), F(0x02, 'i16', 'skill', '技番号 (WAZ index)'),
    F(0x04, 'i16', 'cancel_when', 'いつｷｬﾝｾﾙさせる? 0=条件なし 1=敵着地後 2=自分着地後 3=ﾋｯﾄ後'),
    F(0x06, 'i16', 'time', '時間'), F(0x08, 'i16', 'cpu_lv_corr', 'CPUﾚﾍﾞﾙ補正値'), F(0x0A, 'i16', 'interrupt_prob', '割り込ませ確率'),
    F(0x0C, 'struct:cpu_cond', 'cond', '発動条件')])
S['cpu_combo'] = dict(size=None, ja='CPUコンボリスト dlg184: {u8 割り込み可, u8, u16 n} + u16 n + cpu_attack×n', fields=[])
S['cpu_counter'] = dict(size=0x18, ja='反撃 dlg141 (ファイル末尾: u16 n + 24B×n)', fields=[
    F(0x00, 'u8', 'type', 'ﾀｲﾌﾟ 0=何もしない 1=移動 2=技'), F(0x02, 'i16', 'action', '行動 (技番号/移動番号)'),
    F(0x04, 'u8', 'value', '技の価値（優先順位）'), F(0x05, 'u8', 'need_cpu_lv', '必要CPUﾚﾍﾞﾙ'),
    F(0x06, 'i16', 'prob', '発動確率'), F(0x08, 'i16', 'prob_lv', 'CPUﾚﾍﾞﾙ発動確率変化'),
    F(0x0A, 'i16', 'delay', '出るまでの時間差'), F(0x0C, 'i16', 'delay_lv', 'CPUﾚﾍﾞﾙ時間差変化'),
    F(0x0E, 'bits8', 'attack_bits', '攻撃: 打撃(下/中/上) 射撃(下/中/上)'),
    F(0x10, 'bits16', 'dist_bits', '距離: 近/中/遠 × 横/下方/上空', conf=L)])

ENUMS = dict(
    skill_group=['通常技', '超技', '回避技'], skill_kind=['打撃', '射撃', '特殊'],
    element=['無', '炎', '氷', '雷'], touch=['重', '通常', '滑', '無'],
    dir_type=['前回の設定', '現在の進行方向', 'ﾛｯｸｵﾝした敵方向', '壁避け', '壁避け(敵ｻｰﾁ)', '常に標的位置', '先頭ﾚｰｻﾞｰ角度'],
    draw_attr=['ノーマル', '左右反転', '上下反転', '半透明', '100%加算', '50%加算', '25%加算', '100%減算', '50%減算', '25%減算',
               'タイルパターン', 'アルファブレンド', '加算アルファ', '塗りつぶし', 'フェード'],
    voice_category=['攻撃', '回避', '迎撃', '超技使用', 'ﾀﾞﾒｰｼﾞ小', 'ﾀﾞﾒｰｼﾞ大', '復帰時', '戦闘開始時', '勝利時', 'ＫＯ時', '挑発', 'その他'],
)

MOTIONS = {
    '_note': 'BFE hard-coded mech motions → SPR anim slot (exe 0x418000-0x41c200, 0x441d40-0x441fa0). '
             'ground/air chosen by height (obj+0x64)->+0x14 > 0. d = 方向区分 0前 1/2横 3後 (0x41a9f0, 敵との相対角).',
    'move_states': {'0': '停止', '1': '歩行', '2': 'ダッシュ', '3': 'ダッシュ停止', '4': 'Sダッシュ(跳躍)', '5': '空中/落下',
                    '6': 'ダウン(寝)', '7': '起き上がり', '8': '演出(登場/退場?)', '9': '演出', '10': '演出',
                    '_src': 'task2 handlers registered at 0x41bd21..0x41bdef; speeds set in 0x41a8c0: 歩行 8, ダッシュ 16, Sダッシュ 32 (×256 固定小数)'},
    'slots': [
        dict(slot=0, motion='のけぞり(地上)', conf=C, src='0x441ef4'),
        dict(slot=1, motion='(未参照: のけぞり2?)', conf=U),
        dict(slot=2, motion='吹き飛び(打ち上げ)', conf=C, src='0x441f7c, 0x4410a9'),
        dict(slot=3, motion='(未参照)', conf=U),
        dict(slot=4, motion='ダウン(倒れ/寝)', conf=C, src='state6 0x41a096'),
        dict(slot=5, motion='起き上がり', conf=C, src='state7 0x41a15d'),
        dict(slot=6, motion='立ち(待機, 地上)', conf=C, src='state0 0x4191d8, battle init 0x41b8a4'),
        dict(slot='7-10', motion='歩行 4コマ周期 (7,8,9,10; 8 と 10 で足音)', conf=C, src='0x419766'),
        dict(slot='11+3d', motion='ダッシュ開始(地上) d=0前/1,2横/3後 → 11,14,17,20', conf=C, src='0x4199db'),
        dict(slot='12+3d', motion='ダッシュ中(地上) → 12,15,18,21', conf=C),
        dict(slot='13+3d', motion='ダッシュ停止(地上) → 13,16,19,22', conf=C, src='state3 0x419bc8'),
        dict(slot=23, motion='(未参照)', conf=U),
        dict(slot=24, motion='Sダッシュ/跳躍 踏み切り', conf=L, src='state4 0x419dcd'),
        dict(slot=25, motion='跳躍 上昇', conf=L, src='0x419ee1'),
        dict(slot=26, motion='空中待機(上昇中)/空中被弾', conf=C, src='0x419089, 0x441f98'),
        dict(slot=27, motion='空中待機(下降中)', conf=C, src='0x419264'),
        dict(slot='28-31', motion='着地バウンド (落下速度で 28..31 から開始) ', conf=C, src='0x4190a0, 0x4192a0'),
        dict(slot='32-34', motion='バウンド後の着地/ダウン移行 (速度区分)', conf=L, src='0x419349'),
        dict(slot='35+3d', motion='ダッシュ開始(空中) → 35,38,41,44', conf=C),
        dict(slot='36+3d', motion='ダッシュ中(空中) → 36,39,42,45', conf=C),
        dict(slot='37+3d', motion='ダッシュ停止(空中) → 37,40,43,46', conf=C),
        dict(slot=48, motion='練習モード(mode1)の被弾リアクション', conf=L, src='0x419605'),
        dict(slot=50, motion='ダウン中の追い打ち被弾', conf=C, src='0x441e43'),
    ],
}

PLAYER_DEFAULTS = {
    '_src': '0x41b582 (status type 0 = プレイヤー); CPU は cpu_header の c1+c2*Lv',
    'hp_per_bar': 2080, 'hp_bars_extra': 2, 'hp_total': 6240, 'armor': 300, 'defense': 0,
    'melee_power': 10, 'shot_power': 10, 'melee_heat_rate': 100, 'shot_heat_rate': 100,
    'heat_max': 130, 'walk_speed': 8, 'dash_speed': 16, 'sdash_speed': 32, 'mech_type': 0,
    'se': {'walk': 40, 'dash1': 121, 'dash2': 122, 'dash3': 123, 'sdash': 124, 'down': 41},
    'meka_table': 'exe .data 0x4c9b58 stride 0x214: char pilot[260], char file[260], u8 id, u8, u8 分類, u8, '
                  'i16 cost(Hell?) @0x20c, u16 flags, u8 halfHP(1=ゲージ半分) @0x210, u8 得意間合い(1近2遠3全) @0x211, u8 @0x212, u8',
}


def main():
    se = []
    if os.path.exists(EXE):
        d = open(EXE, 'rb').read()
        base = 0x4c7e88 - 0x400000
        for i in range(181):
            o = base + i * 0x28
            se.append([d[o:o + 16].split(b'\0')[0].decode('cp932'), d[o + 16:o + 40].split(b'\0')[0].decode('cp932')])
    ENUMS['se'] = dict(_note='Se\\<name>.wav (exe 0x4c9b24 "SE\\%s.wav"); table @0x4c7e88 stride 0x28 {char name[16], char desc[24]}; '
                             '"Ganbare" = 空き', names=se)
    out = dict(_meta=dict(source='BaldrForce.exe (unprotected, 2003-01-12 build) editor dialogs + code',
                          generator='tools/gen_bfe_waz_fields.py', notes='notes/07_bfe_exe_analysis.md',
                          file_layouts=dict(
                              waz='u16 nSkill; skill_header(0x6C); phase(0x18C)×phase_count, each followed by spr_event(48)×n_events',
                              tama='Dat\\Waza\\Tama.dat = same as WAZ (弾 453 技)',
                              cpu='cpu_header(0x32); u16 nMove; cpu_move(96)×n; u16 nCombo; {4B, u16 n, cpu_attack(48)×n}×nCombo; u16 nCounter; cpu_counter(24)×n')),
               structs=S, enums=ENUMS, motions=MOTIONS, player_defaults=PLAYER_DEFAULTS)
    p = os.path.join(HERE, 'bfe_waz_fields.json')
    json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('wrote', p, 'structs', len(S), 'se', len(se))


if __name__ == '__main__':
    main()
