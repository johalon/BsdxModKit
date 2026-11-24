#!/usr/bin/env python3
"""透（TOORU）の機体設定 — build_phase3b.py が読む、機体ごとに差し替える値の置き場（docs/porting/09_porting_another_mech.md §6 案 1、2026-11-16）。

別の機体を移植するときは、このファイルを複製して値を差し替える（一覧は docs/porting/09_porting_another_mech.md §8）。
ここにあるのは「機体ごとに違う値」だけ。BFE 共通の決まり（SKILL_BASE、共通 waz の番号、基本モーションの表）は tools/bfe2bsdx_common.py。
BFE→DiveX の変換規則（tools/bfe2bsdx_*.py）と、ビルドの手順（build_phase3b.py）は機体に依存しない。
改善版の調整（tools/modified_tweaks.py ほか）はまだ tools/ 側にある（09 §6 案 4、未実施）。

値は 2026-11-16 に build_phase3b.py の先頭などから 1 文字も変えずに移した（4 パックの sha256 不変で確認）。
"""

# ------------------------------------------------------------------ 入力（<P> からの相対パス）
BFE_SPR = 'work/bfe_spr/tooru.json'            # BFE SPR（bfe_spr.py の出力）
BFE_PNG = 'work/bfe_png'                       # BFE の機体画像（bfe_gr2.py png）
BFE_WAZ = 'work/bfe_waz/TOORU_named.json'      # BFE WAZ（bfe_waz.py の名前付き JSON）
BFE_EQUIP = 'work/bfe_extracted/Update/EquipmentInfo.DAT'   # 武装の説明文（透＝プレイヤーの装備表、240B x 85）
# BFE 共通（機体に依存しない）: Tama.dat・SE・Effect.spr
BFE_TAMA = 'work/bfe_waz/Tama_named.json'
BFE_SE = 'work/bfe_se'
BFE_EFFECT = 'work/bfe_effect'                 # Effect.spr + *.grp (Bmp/Effect)

# ------------------------------------------------------------------ 出力
MOD_DIR = 'mods/phase3b_tooru'                 # パックの置き場（<P> から）
WORK_DIR = 'work/tooru_port'                   # 中間結果と report.txt
NOTES_PROVENANCE = 'notes/15_provenance_tooru_table.md'    # 自動生成（手で触らない）
NOTES_BALANCE = 'notes/15b_balance_tooru_table.md'
NOTES_TWEAKS = 'notes/15c_modified_tweaks.md'

# ------------------------------------------------------------------ ID・スロット・名前
NEW_ID = 10                                    # MekaGroup（Sora2 の枠を転用）
MEKA_NAME, MEKA_CODE = 'Tooru', 'TOORU'
SPM_NAME = 'tooru'
SPR_SLOT = 136
EFT_NAME, EFT_SLOT = 'tooru_eft', 135   # BFE Effect.spr subset (134 = Tsukuyomi effects, 133 = Tsukuyomi)
WAZ_SLOT = 111                 # 110 is left for Tsukuyomi (phase 3A) -> placeholder entry (existFlag 0) here
WAZ_SLOT_WAZ110 = 110          # --waz110: TOORU directly at WazaGroup 110 (no placeholder entry)
SE_CAT = 37                    # 宇田川 UDAGAWA: BFE SE appended after its 97 items (category 11 is Tsukuyomi's)
VICTIM_ROW, VICTIM_ID = 27, 97 # 晴嵐's select button (same as phase 1 / 3A)
COIN = 150
MARKER_OLD, MARKER_NEW = '【MODテスト】', '【MODテストTOORU】'   # phase 0 の名残（今は使っていない）
LABEL = '透移植'               # 変換した弾・エフェクト・ラインの技名に付く印（'…（透移植弾303）'）。bfe2bsdx_tama.Fx(label=)
WAZA_NAME = '◆透'              # WazaGroup の wazaName
THUMB_ANIM_NAME = '透：TOORU\r'  # 選択画面サムネの anim 名（SelectMekaMenuMeka.spm）

# ------------------------------------------------------------------ 技の対応表
# BFE WAZ index (Lv3 = 3*EQ+2 / marker / special) -> Kou weapon index used as template (boilerplate, hit objects,
# mek weapon entry, AI slot). Order = weapon order in the mek (equip screen): 63 normal, 3 markers, 21 specials.
OLD_CODES = {2: 'ARMJAB', 5: 'ARMSTRAIGHT', 8: 'ARMUPPER', 11: 'BOOSTUPPER', 14: 'LOWKICK', 26: 'BOOSTKICK', 32: 'TACKLE',
             38: 'IMPERIALSTRIKE', 44: 'DRILL', 56: 'PILEBUNKER', 59: 'BEAMSWORD', 65: 'LANCE', 98: 'HANDGUN', 110: 'SHOTGUN',
             119: 'HOMINGMISSILE', 80: 'QUOTEWIRE', 192: 'CANNONBREAKER', 195: 'MEGABOOSTUPPER', 193: 'TKO', 197: 'IMPERIALFINAL'}
TEMPLATE = {
    2: 0, 5: 1, 8: 2, 11: 47, 14: 3, 17: 5, 20: 43, 23: 27, 26: 52, 29: 26, 32: 28, 35: 28, 38: 17, 41: 56, 44: 6, 47: 19,
    50: 20, 53: 8, 56: 9, 59: 10, 62: 13, 65: 15, 68: 18, 71: 34, 74: 35, 77: 33, 80: 38, 83: 40, 86: 41, 89: 107, 92: 45,
    95: 21, 98: 60, 101: 75, 104: 62, 107: 63, 110: 65, 113: 73, 116: 87, 119: 88, 122: 89, 125: 91, 128: 87, 131: 108,
    134: 97, 137: 105, 140: 109, 143: 67, 146: 94, 149: 86, 152: 84, 155: 85, 158: 95, 161: 96, 164: 99, 167: 71, 170: 110,
    173: 112, 176: 100, 179: 101, 182: 103, 185: 104, 188: 22,
    189: 88, 190: 88, 191: 88,
    192: 113, 193: 115, 194: 120, 195: 113, 196: 114, 197: 124, 198: 121, 199: 129, 200: 125, 201: 130, 202: 117,
    203: 135, 204: 135, 205: 139, 206: 137, 207: 137, 208: 140, 209: 146, 210: 144, 211: 141, 212: 137,
}
SKILLS = [(bi, TEMPLATE[bi], OLD_CODES.get(bi, 'BFE%03d' % bi)) for bi in [3 * e + 2 for e in range(63)] + [189, 190, 191] + list(range(192, 213))]
HIDDEN = {189, 190}            # ■マーカーミサイル Lv1/Lv2 copies: ported but weaponIdentifier 2 (not on the equip screen); 191 visible
# 技名の付け直し（BFE の技名から Lv 表記を外した後に、この表にある技だけ名前を差し替える）
RENAME = {189: 'マーカーミサイルLv1', 190: 'マーカーミサイルLv2', 191: 'マーカーミサイル'}
MARKER_DESC = ('『BALDR FORCE EXE』のデータに残っていた未使用の隠し武装（開発用と思われる）。ホーミングするミサイルを撃ち、'
               '命中・着弾すると周囲に小型弾をばらまきます。（MOD テスト版）')


def equip_index(bi):
    """BFE 技番号 -> EquipmentInfo.DAT の行（None なら説明文は MARKER_DESC）。通常技 = bi // 3、必殺技 192- = 64-"""
    return bi // 3 if bi < 189 else (None if bi < 192 else 64 + (bi - 192))


KOU_INIT = 151                 # イニシャライザ (cloned, its anim 107 -> tooru SPR slot 186 pose)
INIT_SPR_SLOT = 186            # イニシャライザの絵に使う BFE SPR のスロット（anim = SKILL_BASE + これ）
LOADOUT_BFE = [2, 5, 8, 11, 14, 26, 32, 38, 56, 59, 98, 119]   # 12 normal (same set as before) + FC + initializer
LOADOUT_FC = 192               # キャノンブレイカー (BFE initial super move)

# ------------------------------------------------------------------ mek の基本値（wazFileSequence / spmFileSequence は build が入れる）
MEK_BASIC = dict(mekName='透', mekNameEnglish='TOORU', pilotNameKanji='相馬　透', pilotNameRoma='TOORU SOUMA',
                 mekDescription='『BALDR FORCE EXE』より移植した相馬透のシュミクラム。素手格闘を主体に射撃・必殺技をひととおり備えた全能型です。（MOD テスト版）',
                 mekType=15, baseHealth=500, permanentArmor=0, comboImpactFactor=200,
                 fightingAbility=5, shootingAbility=4, durability=3, mobility=4, physicsWeight=0,
                 walkingSpeed=4, normalDashSpeed=8, searchDashSpeed=16, boostDashSpeed=14, autoHoverHeight=0)

# ------------------------------------------------------------------ 透の武装を名指しする処理（新しい機体では空から決める）
# HITLOCK (調査記録 36): bullets / lines do not switch the lock-on (BSX plugin ヒットロック), except those of these
# weapons (user 2026-11-09, hand-picked; マインナックル / 月華衝 removed 11/10: their mines are exempt: Eフィンガーの爆発・ワイヤー 2 種・地面の剣 2 種・貫壁・キャノンブレイカー still lock)
HITLOCK_KEEP = ('E・フィンガー', 'クォウトワイヤー', 'スウィングワイヤー', 'ケイジ・ブレイド', 'エクスカリバー', '貫壁', 'キャノンブレイカー')
# モーニングスター = 甲 (user 2026-11-09): only the tip's first turn (flying out; 甲 モーニングスターLv3（先端） ph0 int2 0, ph1 32,
# 爆風 32) locks; wire / later turns / BFE ph2 tip are exempt
HITLOCK_KEEP_TURNS = {('モーニングスター：先端（透移植）', 0)}
# G1 (build_phase3b.py): BU hitstop patch, (技名, ターン) の順に当てる。最後の要素は「ヒットの のけぞり 停止時間 -> 0」をするターン
HITSTOP_MOVE_F1 = (('ブーストアッパー', 2), ('メガ・ブーストアッパー', 3))
NOKEZORI_ZERO = ('メガ・ブーストアッパー', 2)
# SINK (bfe2bsdx_waz Converter(sink_skills=)): BFE で敵にめり込みながら当てる技（G 2026-11-11）
SINK_SKILLS = {'インペリアルストライク', 'インペリアルファイナル'}
# COMBOV3 (Converter(combo_v3=)): 技名で引く初段補正・技終了時・最低値の表のモジュール（tools/ の中）。None なら COMBOCLS だけ
COMBO_V3_MODULE = 'bfe2bsdx_combo_v3'

# ------------------------------------------------------------------ 自動生成の表の見出し
PROV_TITLE = '透（TOORU）'
PROV_BASIC_KOU = '甲 / 村正 / ノイ'
PROV_BASIC_EXTRA = [('M', 'mek 基本値 耐久 500・フラグ 15・常時装甲 0・性能 5/4/3/4・歩行 4: BFE と単位体系が違うため甲を基準に比率で決めた設計値（調査記録 07 §2.3）'),
                    ('T', 'コンボ感想反映率 200・FC ゲージ／ブースター: BFE に該当なし → 甲の値')]
PROV_HEADER = ['ビルド: mods/phase3b_tooru/build_phase3b.py（統合パック phase3c_merged も同じ内容を使う）。']
