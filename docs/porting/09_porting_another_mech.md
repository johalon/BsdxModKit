# 09 別の機体を移植するとき — 透に固有な部分と、使い回せる部分

対象: 今後 (1) BALDR FORCE EXE（BFE）の透以外の機体、(2) BALDR HEART EXE（BHE）の機体（ツクヨミは phase3a で着手済み・保留）を DiveX に移植する場合に、
今のパイプラインの「どこがそのまま使え、どこを機体ごとに用意し直すか」を、コードを読んだ結果でまとめる。
完璧な汎用化は目標にしない（作者方針）。整理案（§6）のうち **案 1・2・3・7 は実施済み**（2026-11-16、4 パックの sha256 不変）、案 4 以降は案だけ。
新しい機体を足すときに用意するファイルの一覧は §8。

表記: ファイル名は `<PROJECT>` 直下からの相対パス。§2 の行番号は 2026-11-16 朝の git HEAD（整理の前、dd04a78）のもの。整理で動いた項目には「→ 実施済み: 移った先」を付けた（今の置き場は §2.0）。
分類記号（§2 の表）:
* **(a) 機体設定** — 機体ごとに差し替える設定値（名前・番号・スロット・出力先）
* **(b) 共通規則** — BFE→DiveX で機体に関係なく効く変換規則（exe の処理に基づくもの）
* **(c) 透の武装のワークアラウンド** — 透の特定の技・弾を名指しで直す処理
* **(d) 改善版の調整** — modified/ だけに当てる、機体ごとに別物になる調整

---

## 0. 要約（先に結論）

* **BFE の変換規則（bfe2bsdx_waz / tama / line / eft / spm）は、ほぼそのまま別の BFE 機体に効く見込み。** 規則は BaldrForce.exe の共通処理
  （WAZ ローダ、フェーズの変化先、速度・ジャンプ、ヒット、Effect.spr、Tama.dat、SE 表、基本モーションの SPR スロット表）に基づいていて、
  技を番号で名指しする分岐はない（§3.3 で裏づけ）。ただし **透の技名で引く表が変換器の中に 2 つある**（`SINK_SKILLS`、COMBOV3 の表）。
* **機体ごとに用意し直すのは主に build スクリプトの先頭の定数と表**（ID・スロット・名前、BFE 技→甲テンプレの対応表 `TEMPLATE`、初期装備、mek の基本値）と、
  **ビルド後半の名指しの処理**（G1 の BU/MBU、FOLLOWCUT の判定文字列、HITLOCK の技名表）、**改善版の調整一式**（modified_tweaks / modified_behavior / balance / combo_v3）。
* **入力側の取り出しツール**（bfepac / bfe_gr2 / bfe_spr / bfe_waz）は akira.spr・akira.waz・akira.cpu でも末尾まで読めることを確認済み（docs/bfe/04_bfe_tooru_survey.md §3・§4.1、調査記録 07 §0）。
* **2 機目を同時に入れるのが一番の壁**: SpriteGroup の空き 4 枠（133〜136）は 3A・3B で使い切り（または予約）、機体 ID 10 は 1 つ、
  共通 waz（Tama02/Tama04/Laser）・SeGroup カテゴリ 37 への追記はどちらも「バニラの末尾から」番号を振るので、独立に作った 2 パックは番号が衝突する。
  統合は phase3.5 まで作らない方針（制作記録 2026-10-27、制作記録 §1）。
* **BHE 系（ツクヨミ）**は tools/port/ の汎用部品と build_phase3a.py まではできている。実機で「エフェクトを出すと落ちる」で保留（制作記録 2026-10-24）。
  BFE 系と共有できるのは PortTool（JSON⇔バイナリ）、grp/dat の登録、mek_check、nexaspac、MaterialBlock の作り方、GUI。変換本体は別系統。
* 整理案（§6）は、出力を 1 バイトも変えずに「4 パックの sha256 が変わらない」ことで検証できるものから順に並べた。最優先は
  **(1) 機体設定を 1 か所（mods/<機体>/ の設定モジュール）へ寄せる**、**(2) 変換器の中の透専用の表（SINK_SKILLS・COMBOV3・EFT_SLOT 135 の直書き）を引数化する**。
  → 2026-11-16 に (1)(2) と案 7（BFE 共通の定数を common へ）を実施した。透の設定は `mods/phase3b_tooru/mech_config.py`、変換器は透の技名を持たない（§2.0）。

---

## 1. 前提（今の構成のおさらい）

| 項目 | 透（phase3b）の値 | 出どころ |
|---|---|---|
| 機体 ID（MekaGroup） | 10（Sora2 の枠を転用） | build_phase3b.py:45、:425-426 |
| WazaGroup | [110] 空き（ツクヨミ用の置き場）、[111] Tooru（`--waz110` 版は 110 に直接） | :50-53、:419-422 |
| SpriteGroup | 135 tooru_eft.spm（BFE エフェクト）、136 tooru.spm（機体） | :48-49、:423-424 |
| SeGroup | カテゴリ 37（宇田川）の末尾に BFE_*.ogg | :54、:284 |
| 共通 waz への追記 | 弾 → Tama04、エフェクト → Tama02、ライン → Laser | :55 |
| 選択画面 | 晴嵐（ID 97）の行 27 を借りる、サムネ anim 98 | :56、:151-154、:615-617 |
| 出力 | mods/phase3b_tooru/{files,Update3.pac}、modified/、variantB_waz110/、work/tooru_port/、調査記録 15*.md | :27-35、:747-751、:795 |

ビルドの流れ（A〜I2）はノウハウ 02（docs/porting/02_build_and_pac.md）の表を参照。4 パック = 原作再現版・改善版 × 通常・waz110。
現行の sha256 先頭（2026-11-16、制作記録 末尾）: 3b `D08A1C91` / waz110 `865F18C5`、modified `70F001E7` / waz110 `6F648BFE`。

PC でのビルド: `python tools/build_packs.py`（git から見えるファイルを `<PROJECT>/_ws/proj` に重ねてビルドし、照合して配置する。02 §3）。
パスは `tools/bfe2bsdx_common.py` の `P`（tools/ の 1 つ上）と `EXT`（P の隣の ext）で決まり、直書きは無い（2026-11-16 に整理、§6 案 3 は実施済み）。

---

## 2. 機体に依存する部分の棚卸し

### 2.0 整理後の置き場（2026-11-16、§6 案 1・2・7）

| 何 | 今の置き場 | 備考 |
|---|---|---|
| 機体 ID・スロット・名前・入出力パス・`TEMPLATE`・`SKILLS`・`HIDDEN`・技名の付け直し（`RENAME`）・説明文の行（`equip_index()`）・初期装備・イニシャライザ・mek 基本値（`MEK_BASIC`）・`HITLOCK_KEEP(_TURNS)`・G1 の技名（`HITSTOP_MOVE_F1`・`NOKEZORI_ZERO`）・`SINK_SKILLS`・`COMBO_V3_MODULE`・ラベル `LABEL`・WazaGroup 名・サムネ名・自動生成表の見出し | **`mods/phase3b_tooru/mech_config.py`** | build は `import mech_config as C` で読む（同じフォルダ）。値は移す前と同じ |
| `SKILL_BASE`、共通 waz の並び `SHARED_WAZ`、追記先 `BULLET_FILE/EFFECT_FILE/LASER_FILE`（4/2/6）、BFE 基本モーションの表 `BASIC`、`BASIC_ANIM_SLOT {59: 26}` | **`tools/bfe2bsdx_common.py`** | BFE 機ならどれも同じ決まり。spm・waz・build・attack_count_check が import する |
| SINK の技名 | `Converter(sink_skills=)` で受け取る（既定は空） | 渡さなければ SINK は効かない |
| COMBOV3 の表（`bfe2bsdx_combo_v3`） | `Converter(combo_v3=<module>)`・`Fx(combo_v3=)` で受け取る（既定 None） | None なら COMBOCLS だけ。別機体の同名の技に透の値は当たらない |
| 弾の名前の印 | `Fx(label=)`（必須） | FOLLOWCUT の判定も `fx.label + '弾'` |
| 改善版の挙動の調整の対象ファイル | `bfe2bsdx_modified_behavior.apply(new, self_waz=, bullet_waz=, spm_file=, eft_file=, eft_slot=)` | build が `MEKA_NAME + '.waz'`、`SHARED[BULLET_FILE] + '.waz'`、`SPM_NAME + '.spm'`、`EFT_NAME + '.spm'`、`EFT_SLOT` を渡す |
| **まだ透の値が残っている所** | `tools/modified_tweaks.py`（調整の表）、`bfe2bsdx_combo_v3.py`（表そのもの）、`bfe2bsdx_balance.py`（`SELF_WAZ 'Tooru.waz'`・`SELF_ARMOR_*`・表題）、`bfe2bsdx_modified_behavior.py` の各関数の技名・弾名、`tools/build_packs.py`（`mods/phase3b_tooru` の場所）、build の G0 診断（`TOORU_DIAG`） | 改善版の調整は §6 案 4（未実施）。build の I2 は今のところ透の調整をそのまま当てる → 別機体では I2 を外すか、調整を機体ごとに用意する（§8） |

### 2.1 mods/phase3b_tooru/build_phase3b.py

| 行 | 内容 | 分類 | 別機体でどうするか |
|---|---|---|---|
| 21 | `sys.path.insert(0, '/path/to/workspace/tools')` | (a) パス | 案 3 → 実施済み: `__file__` 起点 |
| 27-43 | 入出力パス（`work/bfe_spr/tooru.json`、`work/bfe_png`、`work/bfe_waz/TOORU_named.json`、`Tama_named.json`、`work/bfe_se`、`EquipmentInfo.DAT`、`work/bfe_effect`、`work/tooru_port`、`mods/phase3b_tooru`） | (a) | 機体名で組み立てる。Tama・Effect・SE は BFE 共通（機体に依存しない） → 実施済み: mech_config（`BFE_*`、`MOD_DIR`、`WORK_DIR`、`NOTES_*`） |
| 45-58 | `NEW_ID 10`、`MEKA_NAME/CODE 'Tooru'/'TOORU'`、`SPM_NAME 'tooru'`、`SPR_SLOT 136`、`EFT_SLOT 135`、`WAZ_SLOT 111`、`SE_CAT 37`、`BULLET/EFFECT/LASER_FILE 4/2/6`、`VICTIM_ROW 27 / VICTIM_ID 97`、`COIN 150`、`MARKER_*` | (a) | すべて差し替え。スロットの空きは §5 → 実施済み: mech_config（`BULLET/EFFECT/LASER_FILE` だけは BFE 共通として common） |
| 62-64 | `OLD_CODES`（BFE 技番号 → 旧 weaponSequence 名 ARMJAB など。ない番号は `BFE%03d`） | (a) | 新機体は全部 `BFE%03d` でよい（旧名は 20 技版の互換のため） |
| 65-74 | **`TEMPLATE`**: BFE 技番号（Lv3 = 3e+2、189-212）→ 甲の武装番号（テンプレート） | (a) | **機体ごとに作り直す最大の表**。§3.2 → 実施済み: mech_config |
| 75 | `SKILLS`: `3*e+2 for e in range(63)` + 189-191 + 192-212 | (a) | 透は通常 63 種×Lv1-3 + マーカー 3 + 必殺 21 という **透の WAZ の並び**（docs/bfe/04_bfe_tooru_survey.md §4.3）。CPU 機の WAZ がこの並びかは**未確認** |
| 76-77 | `HIDDEN {189,190}`、`MARKER_DESC`（マーカーミサイルの説明文） | (a) | 透だけ |
| 79-82 | `KOU_INIT 151`（イニシャライザの複製元）、`LOADOUT_BFE`・`LOADOUT_FC 192`、`BASIC_ANIM_MAP {59: SKILL_BASE+26}` | (a) | 初期装備は機体ごと。BASIC_ANIM_MAP は BFE 共通のスロット規約（26 = 空中待機、調査記録 07 §4）なので (b) 寄り → 実施済み: 初期装備は mech_config、`BASIC_ANIM_SLOT` は common |
| 110-111 | バニラの件数の assert（WazaGroup 110・SpriteGroup 138・SeGroup 38・BatVoice 30・MekaGroup 103）と空き枠の assert | (b) | **2 機目を「1 機目の出力の上に」積むと必ず落ちる**（§5.4） |
| 128-155 | 選択画面サムネ: 立ち 2 方向のページから 1 チップ画像、`na['animName'] = '透：TOORU\r'` | (a) 名前 / (b) 方法 | 名前だけ差し替え。テンプレ anim 41・98 件の assert は共通 |
| 159-167 | Lib（甲 waz + 共通 waz）、SeMap、Fx、Converter。`default_hit` = 甲 waz 技 14（ボディブローLv3）の Hit | (b) | そのまま |
| 173-187 | 基本技 0-10 = 甲の複製、ボイス削除。ダッシュは `bfe2bsdx_basic`（村正 SD・ノイ BD） | (a)+(d) 的 | 透へのユーザー要望（調査記録 14 §B）。新機体では使うか決め直す |
| 188-191, 210-212 | `EquipmentInfo.DAT` 240B×85 から説明文、`eq = bi // 3 …` | (a) | EquipmentInfo は**透（プレイヤー）の装備表**（docs/bfe/04_bfe_tooru_survey.md §1.3）。他機体の説明文の出どころは**ない**（空欄か自作） |
| 196-200 | 技名の正規化（`(Lv3)` 除去、`■` 除去、マーカーミサイルの名前） | (b)+(a) | Lv 表記の除去は共通、マーカーは透だけ |
| 216-222 | イニシャライザ = 甲 151 の複製（anim 107 → SKILL_BASE+186） | (a) | 186 は**透の SPR のスロット番号**。機体ごとに選ぶ |
| 226-234 | **HITLOCK_KEEP**（ロックを切り替える 7 技名）、`HITLOCK_KEEP_TURNS {('モーニングスター：先端（透移植）', 0)}` | (c) | 透の技名。新機体は空から決める → 実施済み: mech_config |
| 258-270 | 装甲関連値 ×2（`bfe2bsdx_basic.double_armor`、ユーザー 10/27） | (b) 扱い | 全技一律の規則なので流用可（ただしユーザー判断の値） |
| 274-286 | SE: `BFE_<名前>.ogg`、`seItemName 'BFE:'+nm`、カテゴリ SE_CAT の末尾 | (b) | 同じ名前で 2 機目が足すと**同じ ogg が 2 回登録される**（§5.5） |
| 290-298 | mek 基本情報: `mekName '透'`・パイロット名・説明文・`mekType 15`・`baseHealth 500`・性能 5/4/3/4・速度 | (a) | BFE に機体ごとの速度の項目はない（全機体共通、調査記録 07 §2.2）。CPU 機のステータスは `.cpu` ヘッダ（c1+c2×Lv）。比率で決める手作業（調査記録 07 §2.3） → 実施済み: mech_config `MEK_BASIC` |
| 300-321 | 武装エントリ: 甲のテンプレ武装を複製し名前・説明・技番号。**熱 = 消費OH×80/130**（:307-317） | (b) | 熱の換算は exe 根拠（BFE 0x41ad50 / DiveX 0x61cd95）で共通 |
| 325-344 | AI: 甲の表の武器番号を付け替え（テンプレ → 対応武装、他は種類別に順番） | (b) | そのまま（範囲外にならないことが mek_check A1 で保証） |
| 346 | VoiceInfo 無し（透は無言、ユーザー 10/23） | (a) | 機体ごと |
| 347-413 | MaterialBlock（甲の通常 10 エントリを tooru.spm の基本 anim 画像へ、武装ごとに閉包）、レインで自己テスト | (b) | そのまま |
| 417-426 | registries: [110] プレースホルダ、`'◆透'`、SpriteGroup 2 枠、MekaGroup[10] が Sora2 であることの assert | (a) | 番号・名前 |
| 429-445 | `TOORU_DIAG == 'mbu'` 診断 | (c) | 透だけ（診断用、リリースには入らない） |
| 454-473 | **G1 `_hitstop_move_f1('ブーストアッパー', 2)` / `('メガ・ブーストアッパー', 3)`**、MBU の のけぞり停止時間 0 | (c) | コメントにも「Named per skill on purpose (not a general converter rule)」。新機体では当てない → 実施済み: 技名は mech_config `HITSTOP_MOVE_F1`・`NOKEZORI_ZERO`（新機体は空のタプルに。`NOKEZORI_ZERO` を None にする作りにはまだなっていない） |
| 488-490 | `_firelock` 印の除去 | (b) 名残 | 変換器の印を外すだけ |
| 498-554 | **FOLLOWCUT**: 追従弾を撃つ側の anim が変わるフレームで追従を止める。判定に `'透移植弾' in skillNameJapanese`（:511） | (b) 規則 + (a) 文字列 | 規則は一般的（BFE go_mech_spr）。ラベル文字列だけ機体依存 → 実施済み: `fx.label + '弾'` |
| 560-563 | `BAL_SRC = {MEKA_NAME+'.waz': …}`、`_bal` 退避 | (b) | そのまま |
| 566-602 | 生成 → 再パース一致、共通 waz の先頭バイト一致、png のコピー | (b) | そのまま |
| 604-624 | dat: WeaponEquip（103 行）、SelectMekaMenu（99 行・VICTIM）、MekaPilot（70 行・行 30）、Meka.dat（99 行に追加） | (a) 行・ID / (b) 方法 | 行番号の assert はバニラ前提（§5.4） |
| 629-645 | mek_check（違反 0）と `--full --spm --also-waz`（バニラ Sora.mek との差 0） | (b) | そのまま |
| 648-657 | `work/tooru_port/view`（waz_summary 用） | (a) パス | |
| 659-667 | pac 作成と展開検証 | (b) | そのまま |
| 674-753 | 改善版（modified/）: balance → modified_behavior。`B_SPM`（:684）、`調査記録 15b`・`調査記録 15c` を書く（:749-751） | (d) | 調整の中身は全部機体ごと（§2.4） |
| 754-786 | weapons.json / weapons_table.md | (b) | そのまま |
| 788-797 | provenance → `調査記録 15`、`'透（TOORU）'`、mek 基本値の説明文（:794） | (a) | 出力名・説明文 |

### 2.2 変換器 tools/bfe2bsdx_*.py

| ファイル:行 | 内容 | 分類 | 備考 |
|---|---|---|---|
| bfe2bsdx_common.py:7-14 | `P = '/path/to/workspace'`、`SNAP`（`work/tooru_port/nexas_snap`、環境変数 `BFE2BSDX_SNAP`）、gradle の jar の場所、`VAN`（バニラ JSON） | (a) パス | SNAP の置き場所が `tooru_port` 配下なのは歴史的な理由だけ |
| bfe2bsdx_waz.py:44 | `SKILL_BASE = 60`（機体 spm の anim = 60 + SPR スロット） | (b) | spm 側（bfe2bsdx_spm.py:36）と同じ値を別々に定義している → 実施済み: common の 1 つに |
| bfe2bsdx_waz.py:47 | `SPRITE_ATTR`（描画属性 → slot 7） | (b) | exe 0x443665 |
| bfe2bsdx_waz.py:49 | **`SINK_SKILLS = {'インペリアルストライク', 'インペリアルファイナル'}`** | (c) | 変換器の中の唯一の技名表（mech モード）。:1266 で使う → 実施済み: `Converter(sink_skills=)`、値は mech_config |
| bfe2bsdx_waz.py:50, 235-239 | `DASH_SPEED 16`、`AIR_H 160`、`BFE_LAUNCH_G 128`、`BFE_BASE_G -128` | (b) | exe の全機体共通の定数（調査記録 07 §2.2）。AIR_H・LAUNCH_G は推定 |
| bfe2bsdx_waz.py:62-66 | `COMBO_CLASS`（BFE ｺﾝﾎﾞ補正 → 甲の補正クラス） | (b)、ただし**境界は透の 40/47 技の分位から決めた値**（:53-58） | 別機体でも同じ表を使えば「透と同じ物差し」になる。分位を取り直すかは判断事項 |
| bfe2bsdx_waz.py:79 | `ROLE_C = 284.9`（**透の 80 技の平均**から）、`ROLE_G 2.0`、`ROLE_G_MOD`（modified_tweaks） | (b) 値は透由来 / (d) | 同上 |
| bfe2bsdx_waz.py:42, 2399-2419 | **COMBOV3**: `CV3.in_scope(技名)` / `shot_in_scope(技名)` で、**3b と modified の両方**の初段補正・技終了時・最低値を技名で引く | (c)+(d) | 表は bfe2bsdx_combo_v3.py。**別の BFE 機体に同名の技（例: ハンドガン）があれば透の値が黙って当たる**（§3.3） → 実施済み: `Converter(combo_v3=)`（既定 None）。表のモジュール名は mech_config `COMBO_V3_MODULE` |
| bfe2bsdx_waz.py:746 | 弾名に `'先端'` を含むか（ワイヤー先端の判定） | (b) | BFE の Tama.dat の名前（共通データ）なので機体に依存しない |
| bfe2bsdx_waz.py:2361 付近 | 表示威力 = 威力×1.5（「透 = MekaGroup 10 の自機」） | (b) | 甲以外の自機の補正（制作記録 変換の方針）。どの非甲機でも同じ |
| bfe2bsdx_waz.py:2864- | `remap_template_sprites`（甲の anim → 機体 spm の同番号 anim） | (b) | 基本 anim 0-47 は全機体共通の意味（bfe2bsdx_basic.py 冒頭） |
| bfe2bsdx_spm.py:36-47 | `SKILL_BASE 60`、`BASIC`（DiveX 基本 anim 0-47 ← BFE SPR スロット） | (b) | BFE の基本モーション表は exe ハードコードで akira.spr も同じ構成（調査記録 07 §4） → 実施済み: common へ |
| bfe2bsdx_spm.py:181 | `kou.spm.json` を `/path/to/workspace/work/nexas_rt/json/spm/` から直読み | (a) パス | 案 3 |
| bfe2bsdx_spm.py:384 | `--name` の既定 `tooru` | (a) | CLI だけ |
| bfe2bsdx_tama.py:21-23 | `Fx(..., spm_seq, bullet_file, effect_file, laser_file, kou_waz, label='透移植')` | (a) 引数化済み | スロットとラベルは引数。既定値だけ透 → 実施済み: `label` は必須（既定値なし）、build が mech_config `LABEL` を渡す |
| bfe2bsdx_tama.py:35-99 | テンプレートの弾・サンプル（Tama01[4] ハンドガン：甲、Tama02[1]、Tama04[51] グラビティボム、Tama04[27] サテライト、Tama05[10] マインナックル、甲 waz 47・167・285・318）を**番号で取り、名前で assert** | (b) | バニラの番号。共通 waz に他 MOD が追記しても先頭は変わらないので安全（追記は末尾のみ） |
| bfe2bsdx_tama.py:142, 192, 215, 239, 255 | 生成する技名 `'%s（%s弾%d）' % (名前, label, Tama番号)`、`'BFEエフェクト%02d（%s）'` | (a) 書式 | **改善版の調整・FOLLOWCUT はこの名前で弾を探す**（`'…（透移植弾303）'` など） |
| bfe2bsdx_eft.py:35 | `TAMA_NAMED = '/path/to/workspace/work/bfe_waz/Tama_named.json'` | (a) パス | |
| bfe2bsdx_effmap.py:11-14 | exe・逆アセンブル・キャッシュ `work/tooru_full/effmap.json` | (a) パス | 中身（エフェクト種類 → Effect.spr anim）は BFE 共通 |
| bfe2bsdx_line.py:31 | `EXTRA_TIP, EXTRA_TIP_PARENT = 46, 42`（バニラ Laser の番号） | (b) | ライン骨組みは「**甲の同名武装**のライン」（:15）。甲に同名武装がない BFE ワイヤーは骨組みが無い → 要確認 |
| bfe2bsdx_basic.py:22, 31, 43-71 | `SPEEDS`（ND 8・SD 26・BD 18）、`RETIME`、`SOURCES ('Muramasa','Noi')` ほか | (a)/(d) 的 | 透へのユーザー要望（BFE 仕様外）。3b にも入っている |
| bfe2bsdx_combo_v3.py:27-241 | `SCOPE`・`OPENER`・`LATE`・`PUNCH`・`MOD_MIN_SET`・`EXPECT`・`SHOT_OPENER`・`SHOT_MIN`（すべて透の技名キー） | (c)/(d) | OPENER/LATE は「透の原作データから生成した値」（:22-24）。生成スクリプト `tooru_kou_review_20261110/opener.py` は**ワークスペースに無い**（未確認） |

### 2.3 補助ツール

| ファイル:行 | 内容 | 分類 |
|---|---|---|
| tools/provenance.py:60 | `write(path, mech, rows, header_lines)` — 機体名は引数。`KIND_CAT`（:28-33）は Report の種別 → 出どころ区分の表 | (b)（機体非依存） |
| tools/tooru_weapon_table.py:25-26 | `NAMES`（共通 waz 0..7）、`TOORU_FILE = (110, 111)` | (a) → 2026-11-16 に `tools/weapon_table.py` へ置き換え（`--mech` で mech_config を読む。WazaGroup は pac から） |
| 同 :35-39 | `<root>/_ws/proj/work/tooru_port/check…`、`mods/phase3b_tooru/…/Update3.pac` を組み立て（`__file__` 起点。**PC の `_ws` 配置前提**） | (a) |
| 同 :55-61, 123 | `back_Tooru.waz.json` / `back_Tooru.mek.json`、表題 `'# 透 …'` | (a) |
| tools/bfe2bsdx_balance.py:63-69 | `SELF_ARMOR_*`（Tooru.waz の slot 36）、`SELF_WAZ = 'Tooru.waz'` | (a) |
| 同 :25-52 | `OVERRIDES` / `RAPID` / `MKE` / `FINISH` / `DRILL` / `HITCAP` / `FC_MIN` / `FC_POWER` … を modified_tweaks から**モジュール読み込み時に**組み立てる | (d) |
| 同 :304 | 自動生成表の表題 `'# 透 改善版…'` | (a) |
| tools/modified_tweaks.py:16-404 | `TWEAKS`（約 40 項目）。対象は透の武装名と `'…（透移植弾NNN）'` の弾名、`Laser.waz` のライン名 | (d) |
| tools/bfe2bsdx_modified_behavior.py:13, 165-166, 535 | `SELF_WAZ 'Tooru.waz'`、`SW_NAME`・`SW_BULLET ('Laser.waz', 'スウィングワイヤー：ライン親（透移植）')`、`SPM_FILE, EFT_FILE = 'tooru.spm', 'tooru_eft.spm'` | (a) → 実施済み: `SELF_WAZ`・`SPM_FILE`・`EFT_FILE` は apply() の引数。`SW_*` は調整の中身（案 4 の範囲）なので残した |
| 同 :599, 607 | **`spmFileSequence == 135` の直書き**（IF_RECT。EFT_SLOT と同じ値） | (a)（定数の重複） → 実施済み: apply(eft_slot=) |
| 同 :425-1066 の各関数 | `_NEW['Tama04.waz']` で弾を名前で探し assert（GF_SIZE、IF_RECT、T150、SG_AIRGRAV、GRENADE_KOU、BULLET_NOCANCEL、SAT_HOLD） | (d)。Tama04 は `BULLET_FILE` の値の重複 → 実施済み: `_NEW[BULLET_WAZ]`（apply(bullet_waz=)）。assert の文言には Tama04 が残る |
| 同 :1069-1076 | `ORDER` と modified_tweaks の「挙動」項目が 1 対 1（assert） | (d) の枠組み（流用可） |

**「Tama04[115]」のような共通 waz の番号**（制作記録 11/15 TIPDETACH など）は、変換した順に末尾へ振られる番号で、コードの中には直書きされていない。
コードは弾を `（透移植弾<BFE Tama 番号>）` の**名前**で探す（BFE Tama 番号はビルドしても変わらない）。番号が出てくるのは notes・STATUS・report.txt だけ。
→ 別機体でも「DiveX 側の番号で指定しない、BFE 番号つきの名前で指定する」流儀はそのまま使える。

### 2.4 分類ごとのまとめ

| 分類 | 主な場所 | 別機体で |
|---|---|---|
| (a) 機体設定 | build 先頭 :21-82、mek 基本情報 :290-298、registries :417-426、dat :604-624、出力名、modified_behavior/balance/tooru_weapon_table の `Tooru` | **全部差し替え**。今は 6 ファイル以上に散っている → 案 1 |
| (b) 共通規則 | bfe2bsdx_waz（mech/bullet モード）、tama、line、eft、effspr、effmap、spm、common、basic の double_armor・merge_material、build の C〜I の枠組み、provenance | **そのまま**（§3.3 の注意つき） |
| (c) 透の武装のワークアラウンド | build G1（BU/MBU）、HITLOCK_KEEP、DIAG mbu、waz の SINK_SKILLS、combo_v3 の表 | 新機体では**当てない**。似た症状が出たら同じ手口で個別に |
| (d) 改善版の調整 | modified_tweaks、modified_behavior、balance、combo_v3 の MOD_*、waz の ROLE_G_MOD | **機体ごとに一から**。枠組み（on/params の一覧、assert してから変える、3b との差分検査）は流用 |

---

## 3. BFE の別の機体を移植する場合の見立て

### 3.1 手順（透の流れを機体名で置き換えたもの）

| 段 | やること | 使うもの | そのまま／作り直し |
|---|---|---|---|
| 1 入力の取り出し | `Bmp\Meka\<機体>.spr`・`<機体>NNN.grp`、`Dat\Waza\<機体>.waz`、`Dat\Cpu\<機体>.cpu`（ファイル名の規則は exe の文字列、調査記録 07 §1）。Tama.dat・Effect.spr・Se\*.wav は透で取り出し済み（BFE 共通） | 作者に PC から取ってもらう（ゲーム由来データ、制作記録）。pac に入っている表は `tools/bfepac.py` | ツールはそのまま |
| 2 画像・SPR → JSON | `bfe_gr2.py png`（index 255 → 透明）、`bfe_spr.py`、`bfe_waz.py <機体>.waz`（名前付き JSON、`--summary` で技一覧） | 同左 | そのまま。akira で確認済み |
| 3 BFE 技一覧と武装表 | `bfe_waz.py --summary` で技番号・名前・技グループ・技タイプ・消費OH を出し、**移植する技の番号 → 甲のテンプレ武装**の表（透の `TEMPLATE`）を作る。名前は WAZ ヘッダの技名 | build の `SKILLS`・`TEMPLATE`・`HIDDEN`・初期装備 | **作り直し**（機体ごとの手作業の中心） |
| 4 スプライト | `bfe2bsdx_spm.convert(spr, png_dir, 名前付きWAZ, out, 名前)` | 同左 | そのまま（基本 anim 0-47 は BFE 共通のスロット表から） |
| 5 技の変換 | `Converter(mode='mech')` + `Fx`（弾・エフェクト・ライン） | 同左 | そのまま。ただし §3.3 の 3 点 |
| 6 基本技・mek | 甲の基本技 0-10 を複製して絵を差し替え、mek 基本値（耐久・性能・速度）を決める、イニシャライザの絵の SPR スロットを選ぶ | build C・E 節 | 値は**機体ごと**（ステータスは `.cpu` ヘッダを比率で、調査記録 07 §2.3 の考え方） |
| 7 SE | 使う SE を BFE_*.ogg にして SeGroup に足す | build D 節 | 方法はそのまま。カテゴリと番号は §5.5 |
| 8 登録 | MekaGroup・WazaGroup・SpriteGroup・dat 4 種 | build F・G 節 | 番号は §5 |
| 9 ビルドと検証 | 再パース一致、共通 waz の先頭バイト一致、mek_check 違反 0・`--full` 基準外 0、pac 展開検証、2 回ビルドで sha256 一致 | build G〜I | そのまま |
| 10 実機 | 選択・装備・各技・敵としての動作 | 作者 | 毎回 |

### 3.2 機体ごとに用意し直すもの（一覧）

1. 入力 JSON 一式（`<機体>.json`（SPR）、`<機体>_named.json`（WAZ）、PNG）。
2. **BFE 技 → 甲テンプレの対応表**（`TEMPLATE`）と、移植する技の選び方（`SKILLS`）。透は「通常技の Lv3 だけ」（`3e+2`）だが、これは透の WAZ が通常 63 種×3 Lv の並びだから（docs/bfe/04_bfe_tooru_survey.md §4.3）。CPU 機の WAZ の構成は**未調査**。
3. mek の基本値と表示名、パイロット名、説明文（EquipmentInfo は透の装備の説明だけなので、他機体の武装説明は無い）。
4. 初期装備（WeaponEquip の 14 枠）。イニシャライザを持たせるか。
5. 機体 ID・WazaGroup・SpriteGroup・SE カテゴリ・選択ボタンの割り当て（§5）。
6. 改善版を作るなら、その調整一式（§2.4 (d)）。
7. 透向けの要望で入れたもの（ダッシュ系 `bfe2bsdx_basic`、装甲 ×2）を新機体にも入れるかの判断（作者）。

### 3.3 「透の変換規則は BFE 共通の exe 処理に基づくのでそのまま効く」の裏づけと反例

**裏づけ（コードで確かめたこと）**
* 変換器の分岐は BFE データのフィールド（フェーズの変化先 `go_*`、`move_dir`、`anim_type`、`fire_type`、フラグ、ヒット・のけぞりの値）で決まり、
  **BFE の技番号・Tama 番号で分岐する箇所は見当たらない**（`['index']`・`ti ==`・`bi ==` を tools/bfe2bsdx_*.py で検索、該当なし。tama.py の `ti in self.tcache` などは表引き）。
* 定数は exe 由来の全機体共通値: 移動速度は全機体共通でハードコード（歩行 8・ダッシュ 16・S ダッシュ 32、調査記録 07 §2.2）→ `DASH_SPEED 16`。
  描画属性表 0x443665 → `SPRITE_ATTR`。1 コマ = wait+1 tick（0x413244）・30fps → ×2。エフェクト種類 → anim 表 0x4d45ec（bfe2bsdx_effmap）。
* 入力形式: TOORU.WAZ・akira.waz・Tama.dat・TOORU.CPU・akira.cpu が同じパーサで末尾まで読め、exe の WAZ ローダ（0x43de60）と同じ構造（調査記録 07 §0）。
  SPR も tooru・akira とも末尾まで読める（docs/bfe/04_bfe_tooru_survey.md §3）。
* 基本モーションの SPR スロット表は exe ハードコードで、akira.spr も同じ構成 → 「全機体で共通の規約」（調査記録 07 §4）。bfe2bsdx_spm の `BASIC` はこの表。
* 弾・エフェクト・SE は BFE 全体で共通のデータ（Tama.dat 453 技、Effect.spr、SE 表 181 件。docs/bfe/04_bfe_tooru_survey.md §0、調査記録 07 §1・§6）。Fx は必要な弾だけを閉包で変換する（bfe2bsdx_tama.py 冒頭）。
* 弾の変換はすでに「透の技」ではなく「Tama.dat の技」単位（キャッシュ `tcache` / `pcache` / `lcache` は Tama 番号キー）。

**反例・注意（そのままでは効かない／透の値が混ざるところ）**
1. **COMBOV3 が技名で 3b にも効く**（bfe2bsdx_waz.py:2399-2419、combo_v3 の `SCOPE` 等）。新機体に `ハンドガン` などの同名技があれば、**透向けに決めた初段補正・最低値が黙って当たる**。
   名前が無ければ従来規則（COMBOCLS 等）に落ちるので壊れはしないが、「機体ごとの判断」が透の判断で上書きされる。→ 案 2。
2. **`SINK_SKILLS`**（:49）は透の 2 技の名前。新機体に同名技が無ければ効かない（無害）、あれば効く（それが正しいかは技しだい）。
3. **規則の「目安合わせ」は透の 1〜2 技で行った**: 速度 1:1（タックル・ブーストキック）、ジャンプの係数（ブーストアッパー）、`COMBO_CLASS` の境界と `ROLE_C 284.9`（透の技の分布）（調査記録 09 §3、§4-8、bfe2bsdx_waz.py:53-79）。
   exe の式から機械的に出したものではない値は、別機体でも同じ数値が使われる（＝透と同じ物差し）。機体ごとに取り直すかは判断事項。
4. **ラインの骨組み**は「甲の同名武装の Laser のライン」（bfe2bsdx_line.py:15）。テンプレ表で甲のライン武装を割り当てられない BFE ワイヤー・レーザーは、骨組みが無い（どう落ちるかは**未確認**）。
5. **テンプレ技に無い要素の土台**: 直接ヒットが無いテンプレ → 甲ボディブロー（build :166）、発射が無いテンプレ → 甲ハンドガンの発射（:193、発射位置が甲のハンドガンの位置になる。調査記録 09 §3.1）。新機体でも同じ近似が出る。
6. **多脚（メカの型 1）**: BFE には「スタンダード／多脚」の型がある（調査記録 07 §2.1）。多脚機の基本モーションが同じスロット表かは**未確認**（akira で確かめたのはスタンダード機と思われる、未確認）。
7. **WAZ の並び**: 透の `SKILLS` は Lv 付きの並び。CPU 機の WAZ がどうなっているか、EquipmentInfo のような説明文があるかは**未確認**。

---

## 4. BHE の機体を移植する場合

### 4.1 現状（できていること・保留）

| 項目 | 状態 | 出どころ |
|---|---|---|
| 汎用部品 | `tools/port/bhe2bsdx.py`（Term の付け替え、AI フィールドのずれの補正 `ai_event()`、共通技の閉包 `shared_closure`、参照の付け替え `RefMap`、MaterialBlock）、`spm_append.py`（共通 spm への末尾追加、元のバイトを保持）、`material_images.py`（BHE の (anim,pattern) 組 → BSDX の画像番号） | 各ファイル冒頭、調査記録 08 §2・§6 |
| ビルド | `mods/phase3a_tsukuyomi/build_phase3a.py`。機体ごとの設定（`MECH`、`NEW_ID 10`、`SPR_SLOT 133`、`VOICE_CHAR 6`、`SE_CAT 11`、`VICTIM_ROW 27`、`LOADOUT`、`HIDDEN_WEAPONS`、`FX_ANIMS`）は先頭にまとまっている（:36-57） | build_phase3a.py、調査記録 08 §6 |
| 検証 | 生成 12 ファイルの再パース一致、mek_check 違反 0、共通 waz `--also-waz` はバニラ既存の 15 件だけ、`port_remap_check.py`（SE はファイル名、共通技は技名で一致）、共通 spm は `spm_append.verify_append()` | 調査記録 08 §3 |
| テスト | `tools/tests/test_bhe_hitbox.py`（BHE sou.spm の当たり判定が misaki MOD と一致）、`test_spm_append.py` | 各ファイル冒頭 |
| Java | `tools/harness/PortTool.java`（b2j/j2b/spm、BFE 系と共有）、`RunTsukuyomiPipeline.java`（NeXAS_DX の実験的 TransMeka を 1 機に走らせる。機体名は引数、既定 tsukuyomi）、`CloneMech.java`（既存 BSDX 機の複製、プロトタイプ・実機未検証） | 各ファイル冒頭 |
| NeXAS_DX の修正 | `tools/patches_py/fix_bhe_hitbox.py`（当たり判定）を `build_nexas_dx.sh` が適用。`tools/patches/com/giga/nexas/util/ProjJsonCopy.java` | 調査記録 08 §2.1 |
| **保留** | 実機で「エフェクトを出すとゲームが落ちる」（2026-10-24 ユーザー）→ 透に注力のため保留。原因未調査 | 制作記録 10/24、制作記録 §1・末尾 |
| 未確認 | HUD（C_/G_/M_ spm）の名前の決まり方、敵としての動作、追加した共通エフェクトが他機体に影響しないか | 調査記録 08 §5 |

旧: 「敵として出したときのエフェクトで落ちる」（制作記録 §1）／ 制作記録 10/24 の原文は「エフェクトを出すとゲームが落ちる」で自機か敵かは書かれていない → 自機・敵の別は**未確認**。

### 4.2 BHE と BFE の違い（部品が別系統になる理由）

| 観点 | BHE（tools/port/） | BFE（tools/bfe2bsdx_*） |
|---|---|---|
| 技データ | BSDX とほぼ同じ形（型付きスロット）。NeXAS_DX の TransMeka で waz/spm/mek を変換し、Term・AI・参照を付け替える | 形式がまったく違う（392B 固定ブロック）。甲の同名技をテンプレにしてフィールド単位で組み立てる |
| 共通技（弾・エフェクト） | BHE の共通 waz から閉包。**BSDX に同名の技があれば BSDX 版を使う**（調査記録 08 §2.5） | Tama.dat から閉包して**全部新規**に変換 |
| 共通スプライト | BHE の anim を BSDX の同名共通 spm（Tama/bomb/Mark/Pic）の**末尾に追加**（spm_append） | 専用の spm（tooru_eft.spm）を 1 枚作り SpriteGroup に登録 |
| SE | BSDX に同名ファイルがあれば流用、無いものだけ新カテゴリ（11）に | BFE の SE を全部 BFE_*.ogg として追加（カテゴリ 37 の末尾） |
| ボイス | BatVoice の既存キャラ枠（[6]）の後ろに追加 | なし |
| 依存の大きさ | 「共有エフェクト・弾・SE が同名別物 → 付け替えが大仕事」（調査記録 00 ROADMAP） | 自前で一式作るので衝突は少ない |

### 4.3 共有できる部品と別系統の部品

| 部品 | 共有／別 | 備考 |
|---|---|---|
| PortTool（JSON ⇔ バイナリ、再パース一致） | **共有** | ただし呼び出しは 2 系統: `bhe2bsdx.porttool`（`tools/nexas_build`）と `bfe2bsdx_common.porttool`（スナップショット `work/tooru_port/nexas_snap`）。build_phase3a は自前の classpath（:65-70）も持つ |
| nexaspac.py（pac 作成・展開検証） | 共有 | |
| bsdx_dat（dat の読み書き）、grp の登録の書き方 | 共有（コードは各 build に重複） | MekaGroup[10]・WeaponEquip・SelectMekaMenu・MekaPilot・Meka.dat の処理はほぼ同じ |
| mek_check.py（W/A/V/M/R1-R9、`--full`、`--also-waz`） | 共有 | ツクヨミの作業で R8・R9・`--also-waz`・`--full` を追加（調査記録 08 §2.4） |
| MaterialBlock の規則（画像番号の昇順リスト、138/38/30） | 考え方は共有、実装は別 | BFE: build の `material_for`、BHE: `RefMap.material` + `material_images` |
| Report | 別実装が 2 つ | bfe2bsdx_common.Report は log/mark/since（provenance 用）あり、bhe2bsdx.Report は集計だけ |
| GUI（BsdxWorkshop） | 共有 | どの機体の mek/waz も開ける。書き出しは常に Update3.pac（ノウハウ 08、調査記録 13） |
| 変換本体 | 別 | BHE: TransMeka + bhe2bsdx、BFE: bfe2bsdx_waz/tama/line/eft/spm |
| 共通 spm への追記 | BHE だけ | spm_append は BFE 系でも使えるが、今の BFE 系は専用 spm 方式 |

### 4.4 BHE の別機体に進むなら

1. まずツクヨミの落ちを再現・切り分け（共通 spm 追記・Tama02 以外のヒットエフェクト・HUD 等が候補だが、どれも**推測**。調べていない）。
2. 新機体は build_phase3a.py をコピーし、先頭の設定（`MECH`、スロット、`VOICE_CHAR`、`LOADOUT`、`FX_ANIMS`）を差し替え、`bhe_deps.py <機体>` で依存の閉包を確認する。
3. スロットの空きは §5 の制約を受ける（3A は SpriteGroup 133、WazaGroup 110 を使う前提で 3B が番号を空けている）。

---

## 5. 複数の機体を同時に入れるときの制約

### 5.1 機体 ID（MekaGroup）
* exe に機体数 103 のハードコードが 6 か所（うち 1 か所は構造体内の固定配列、セーブ形式にも関係）。103 以上の ID は LoadMek で即終了（調査記録 11 §1）。
* exe を変えずに使える ID: **10（完全に未使用）**、77・76・56・65・33・39・53（敵専用でスクリプト未登場。ただし BQUnit に行がある）（調査記録 11 §0、調査記録 12 §2）。
* 実験版 exe（N=120）は作成済み・未テスト、**Phase 4 は保留**（調査記録 11 §0、制作記録 10/23、制作記録 §1）。
* 統合パック phase3c では ツクヨミ = ID 10、透 = ID 77（アイアンファイル）にした（調査記録 12 §1）。**3 機目は 76・56 などの残り候補**から選ぶことになる（どれも BQ に行がある点は同じ）。

### 5.2 選択画面のボタン
* SelectMekaMenu の先頭 70 行が上限（exe のボタン ID 697〜766 固定、調査記録 11 §2.1）。移植機 1 機ごとに既存機のボタンを 1 つ借りる。
  候補と敵 HP の表は 調査記録 12 §3。増やすには exe パッチ（ページ切替案）が要る（未作成、調査記録 11 §2.3）。

### 5.3 SpriteGroup・WazaGroup・SeGroup・BatVoice
| 表 | 制約 | 今の使用 |
|---|---|---|
| SpriteGroup（138） | 空き 4 枠 133〜136。配列長を変えると ProgramMaterial.grp と**全 mek の MaterialBlock** を作り直すことになる（docs/formats/01_formats_and_tools.md §1） | 133 ツクヨミ、134 ツクヨミ用に予約（実際は未使用、調査記録 08 §1）、135 tooru_eft、136 tooru → **新機体に回せるのは最大で 134 の 1 枠** |
| WazaGroup（110） | 末尾追加は動く（misaki 111、透 112 件で実機動作。調査記録 06、STATUS） | 110 ツクヨミ（3b ではプレースホルダ）、111 透 |
| SeGroup（38 カテゴリ） | カテゴリ数は変えない。カテゴリ内の項目追加は可 | 11 ツクヨミ、37 の末尾（97〜）透 |
| BatVoice（30 キャラ） | キャラ数を変えると全 mek の MaterialBlock が変わる。キャラ内の追加は可（調査記録 06 §3） | [6] にツクヨミ 64 枠 |

SpriteGroup が実質の上限。BFE 機をもう 1 機入れるときの選択肢（いずれも**未検証の案**）:
* (i) **BFE エフェクト spm を BFE 機で共有**する（Effect.spr は BFE 共通。今の tooru_eft.spm は「透が使う 78 anim だけ」を BFE と同じ anim 番号で入れているので、
  2 機ぶんの anim の和集合で作れば番号はそのまま。bfe2bsdx_eft.py は anim 番号 = Effect.spr 番号の規則、調査記録 09 §8.1）。これで機体 spm 1 枠（134）で足りる。
  ただし改善版の IF_RECT は「落雷の anim のページを他の弾が使っていない」ことを assert している（modified_behavior :599-612）→ 共有すると前提が変わる。
* (ii) 機体 spm を既存の枠と共有（前例: spm 38 = Aki/Zako003c。docs/formats/03_mech_registry_and_player.md §5）— 別機体の絵は共有できないので実質使えない。
* (iii) SpriteGroup を伸ばす（全 mek の MaterialBlock 作り直し、誰も試していない。調査記録 06 §1）。

### 5.4 ビルドが「バニラから」番号を振ること
* build_phase3b は vanilla の件数を assert し（:110）、共通 waz・SeGroup の追記位置をバニラの末尾から決める（:161、bfe2bsdx_tama `_alloc`）。dat も行数を assert（:609、:616、:620、:623）。
* したがって **2 機目を独立にビルドすると、Tama02/Tama04/Laser の追記番号と SeGroup 37 の項目番号が 1 機目と重なる**。grp・dat・共通 waz はファイル丸ごと置き換えなので、
  Update4.pac などに分けて重ねても**先勝ちでどちらかが消える**（pac の優先順は docs/formats/02_pac_and_loading.md §3）。
* 解決は 2 通り: (A) 統合ビルド（phase3c の build_merged.py 方式。後から足した側の WazaSelect・技ジャンプの番号をずらす処理は入っているが、3A/3B では重ならなかったので**一度も動いていない**、調査記録 12 §1・§7）、
  (B) 2 機目のビルドを 1 機目の出力の上で走らせる（今の assert を外す必要あり）。方針として統合は phase3.5 まで作らない（制作記録 10/27）。

### 5.5 弾・エフェクト・SE の番号と名前
* 共通 waz の番号（例 Tama04[115]）は変換順で決まるので、2 機目が入ると変わり得る。コードは名前（`（透移植弾N）`）で探すので、**ラベルを機体ごとに変えれば名前は衝突しない**（`Fx(label=…)`）。
* BFE の弾を 2 機で共有して重複を減らす案は、**改善版の調整が弾を名前で書き換える**（BULLET_NOCANCEL、GF_SIZE など）ため、共有すると透の調整が他機体の弾にも効く。機体ごとに別の複製にしておくのが安全。
* SE: 同じ BFE の SE を 2 機目も `BFE_<名前>.ogg` で足すと、ファイル名が同じ（pac 内で上書き・同一内容）で、SeGroup の項目だけ 2 つになる。
  BFE の SE は共通の 181 件の表（調査記録 07 §1）なので、**「BFE SE カテゴリ」を 1 つ決めて和集合で登録**する方が筋が良い（未実施の案）。

---

## 6. 拡張しやすくするための整理案（案 1・2・3・7 は実施済み、ほかは案のみ）

並びは「小さく安全で、4 パックの sha256 が変わらないことで検証できる」順。検証の共通手順:
`work/tooru_port/BUILD.lock` を作ってから 4 パックをビルド（`build_phase3b.py` と `--waz110`）→ 3b `D08A1C91`・waz110 `865F18C5`・modified `70F001E7`・waz110 `6F648BFE`（2026-11-16 時点、最新値は 制作記録 末尾）と一致、
さらに自動生成の `調査記録 15`・`15b`・`15c` と `work/tooru_port/report.txt`・`weapons_table.md` が変わらないこと（git diff が空）。
**検証は `python tools/build_packs.py`（表示がすべて `same` なら出力は不変）。**

| 優先 | 案 | 触るファイル | 影響範囲 | sha256 で検証できるか | リスク |
|---|---|---|---|---|---|
| **1（実施済み 2026-11-16）** | **機体固有の値を 1 つの設定モジュールへ**（→ `mods/phase3b_tooru/mech_config.py`。§2.0）: `mods/phase3b_tooru/mech_config.py`（仮）に build 先頭 :27-82 の定数・表（ID・スロット・名前・`TEMPLATE`・`SKILLS`・`HIDDEN`・初期装備・mek 基本値 :293-297・HITLOCK_KEEP・ラベル `'透移植'`）を移し、build はそれを import する。値は 1 文字も変えない | build_phase3b.py、新規 1 ファイル | 透のビルドだけ | **できる**（純粋な移動） | 低。sync.sh は build_phase3b.py の `['python3', `・ffmpeg ブロック・`os.symlink(` を文字列で探して書き換える → これらを build 側に残せば影響なし |
| **2（実施済み 2026-11-16）** | **変換器の中の透専用の値を引数・設定へ**（→ §2.0。balance の `SELF_WAZ` は案 4 と一緒に）: `SINK_SKILLS` を Converter の引数に、COMBOV3 を「機体ごとの表を渡したときだけ効く」形に（既定 = 透の表で今と同じ）、modified_behavior の `135` を `EFT_SLOT` の値に、`'Tama04.waz'`・`'Tooru.waz'`・`'tooru.spm'` を apply() の引数に、FOLLOWCUT の `'透移植弾'` を `fx.label + '弾'` に | bfe2bsdx_waz.py、bfe2bsdx_combo_v3.py、bfe2bsdx_modified_behavior.py、bfe2bsdx_balance.py、build | 変換器（透以外の利用者はいない） | **できる**（既定値が今の値なら出力は同じ） | 低〜中。COMBOV3 は 3b にも効くので、引数の渡し忘れで 3b が変わる → sha で検出できる |
| **3（実施済み 2026-11-16）** | **パスのハードコードを `__file__` 起点に**: `bfe2bsdx_common.P`、build :21、bfe2bsdx_spm:181、bfe2bsdx_eft:35、bfe2bsdx_effmap:11-14、bhe2bsdx:15、build_phase3a、build_merged、tests、porttool.sh 等の `/path/to/workspace`・`/path/to/ext`・`/opt/gradle-8.14.3/lib` | tools/*.py、mods/*/build*.py、tools/*.sh、**tools/win_build/sync.sh** | 全ビルド、PC ビルド | **できる**（パスだけ） | 中。**sync.sh の sed（`/path/to/workspace` → `_ws/proj`）が不要になるので sync.sh も同時に直す**。`/path/to/ext`（NeXAS_DX の位置）は `_ws/ext` と相対関係が違う（クラウドは `proj` の兄弟 `ext`、PC は `_ws/ext`）→ 環境変数（例 `NEXAS_DX`）で渡すのが安全。tooru_weapon_table.py はすでに `_ws/proj` 前提（:35）でクラウドでは動かない点も合わせて揃える |
| **4** | **改善版の調整を機体ごとの置き場へ**: `tools/modified_tweaks.py` の `TWEAKS` を `mods/phase3b_tooru/tweaks.py`（仮）へ移し、balance・combo_v3・modified_behavior はモジュール読み込み時ではなく `apply(tweaks)` で受け取る。tools/modified_tweaks.py は互換のため残すか、透の表を読む薄い入口に | modified_tweaks.py、bfe2bsdx_balance.py（:23-68 の組み立て）、bfe2bsdx_combo_v3.py（:126-127）、bfe2bsdx_waz.py（:78-79 `ROLE_G_MOD`）、modified_behavior | 改善版（と、ROLE/COMBOV3 経由で 3b） | **できる** | 中。今は import 時に値が決まる作りなので、読み込み順の変化で値が変わらないか注意。作者が触る「一覧と切り替え」の場所が変わる → ノウハウ・HUMAN 向け説明の更新が要る |
| **5** | **ビルドの共通部分の切り出し**: `tools/bsdx_build_common.py`（仮）に、grp/dat の登録（:604-624 と build_phase3a の同等部分）、生成→再パース一致（:566-594）、mek_check と `--full` 基準比較（:629-645）、pac 作成・展開検証（:659-667）、view 作成を関数化。Report・porttool も 1 つに | build_phase3b.py、build_phase3a.py、build_merged.py、bfe2bsdx_common.py、bhe2bsdx.py | 全ビルド | 3b は**できる**。3A・merged は今の pac の sha が記録されておらず、入力（work/bhe_tsukuyomi* など）がワークスペースに無い → 検証できるのは 3b だけ | 中。sync.sh が `capture_output=True, text=True, env=env)` を書き換えている（bfe2bsdx_common の porttool）→ 移す先でも同じ文字列か、sync.sh を直す |
| **6** | **バニラ前提の assert を「前の状態」前提に**: build の :110・:609・:616・:620・:623 と共通 waz・SeGroup の追記位置を「入力の grp/dat の今の件数」から決め、**入力を 1 機目の出力に差し替えられる**ようにする（2 機目を積むため） | build_phase3b.py、bfe2bsdx_tama（`_alloc` は既に `len(SH[f])` 起点）、SeMap | 透のビルド（入力がバニラなら同じ） | **できる**（入力がバニラなら同じ番号） | 中。assert は「想定外の入力で黙って壊さない」ための保険なので、件数の検査は残して「期待値を入力から取る」形に |
| **7（実施済み 2026-11-16）** | **SKILL_BASE と BFE 共通の定数を 1 か所に**（→ `bfe2bsdx_common`。§2.0）: bfe2bsdx_spm:36 と bfe2bsdx_waz:44 の `SKILL_BASE`、`BULLET_FILE` などの共通 waz 番号、BFE の基本モーション表（spm `BASIC` と build `BASIC_ANIM_MAP`）を `bfe2bsdx_common` に | bfe2bsdx_common.py、spm.py、waz.py、build | 変換器 | **できる** | 低 |
| **8** | **BFE エフェクト spm・BFE SE カテゴリを機体共通の資源として扱う設計メモ**（コードは 2 機目のときに）: §5.3 (i)・§5.5 の和集合方式。ラベルは機体ごと、弾は機体ごとの複製 | 文書のみ（notes 新規） | なし | — | なし（設計だけ）。実装するときは改善版の IF_RECT の前提（:599-612）を見直す |

### TODO（将来）: 案 4 をやるとき（2026-11-16 作者「今はやらないでおこう」）

**やる時期**: 2 機目の移植に実際に入るとき、または改善版の調整（modified_tweaks への追加）がしばらく止まっているとき。

**中身**: `tools/modified_tweaks.py` の `TWEAKS`（約 40 項目、透の武装名・`…（透移植弾NNN）` の弾名）を `mods/phase3b_tooru/tweaks.py`（仮）へ移す。
今は次の 4 モジュールが **import した時点で**表を読んでいるので、build が `apply(tweaks)` などで渡した表を使う形に直す（5 ファイル・約 70 か所）:
`bfe2bsdx_balance`（`OVERRIDES`・`RAPID`・`MKE`・`FINISH`・`DRILL`・`HITCAP`・`FC_MIN`・`FC_POWER`・`SELF_ARMOR_*`… をモジュール読み込み時に組み立て）、
`bfe2bsdx_combo_v3`（`MOD_OPENER_START_CAP`）、`bfe2bsdx_waz`（`ROLE_G_MOD`）、`bfe2bsdx_modified_behavior`（`MT.on()`）。
balance の `SELF_WAZ 'Tooru.waz'` も同時に引数にする。

**やると起きること**: 別の機体が自分の調整表を持つ・空にできる（今は別機体で build の I2 を通すと透の技名の assert で落ちる）。
作者が調整を見る・切り替える場所が機体のフォルダに移る → `python tools/modified_tweaks.py` の一覧、ノウハウ 05・HANDOFF・制作記録 の説明を直す。

**想定されるまずいこと（対策）**
1. 読み込み時に決まる値の取りこぼし。on の項目は modified の sha256 で気づけるが、**off の項目は出力が同じなので sha では見つからない** → off の項目を 1 つずつ一時的に on にしてビルドし、値が届いているかを確かめる手順を入れる。
2. `FC_MIN`・`ROLEMIN`・`COMBOV3_MOD` は表に行があることを前提に `_BY[...]` を直接参照している（05 の落とし穴）→ 空の表で KeyError。既定値を決める。
3. フィードバック対応で別の作業が `modified_tweaks.py` に足していると、移した先に入らない・ぶつかる → 調整の作業が止まっているときにやる。
4. 移すのは表だけで、`bfe2bsdx_modified_behavior` の各関数（約 1,000 行、透の技名・弾名で assert）は tools/ に残る。on のときだけ動くので害はないが、別機体の改善版はその機体用の関数を書いてから。
5. notes・STATUS の `tools/modified_tweaks.py` の記述は古いパスのまま残る → ノウハウに読み替えを 1 行書く。

検証は §6 の共通手順（4 パック same、調査記録 15*・report.txt の差分なし）。特に 調査記録 15c（調整の一覧）が同じであること。

**やらない方がよいこと（今は）**
* 変換器（bfe2bsdx_waz の 2877 行）を機体抽象化のために分割・書き直すこと。規則はすでに機体非依存で、得るものに対して sha の一致を保つ手間が大きい。
* 弾を BFE 機どうしで共有すること（§5.5。改善版の名前指定の調整が他機体に漏れる）。

---

## 7. 確認できなかったこと・資料の食い違い

* ツクヨミの落ちが自機・敵のどちらで起きるか（制作記録 10/24 は区別なし、制作記録 §1 は「敵として出したとき」）。
* CPU 機（akira など）の WAZ の構成（Lv の並びがあるか）、多脚機の基本モーションのスロット、BFE ワイヤーで甲に同名武装が無い場合のライン変換の挙動。
* COMBOV3 の OPENER/LATE を作ったスクリプト（`tooru_kou_review_20261110/opener.py`）の所在（ワークスペースに無い）。
* SpriteGroup 134 の扱い: 調査記録 08 §1 は「使わずに済んだ＝空き」、制作記録 10/23 は「SpriteGroup 134 予約」。現行の build_phase3a.py は 133 だけを使う（:39）。
* SE の数: 調査記録 09 §0 は 70 種（97〜166）、制作記録 10/23 は 69 個、PC の OGG キャッシュは 71 個（コーディネーター補足）。ビルドの `semap.items` が正（後から増えたと思われるが経緯は未確認）。
* build_phase3a.py・build_merged.py が現在の環境でそのまま再現できるか（入力の work/bhe_tsukuyomi* と tools/nexas_build はワークスペースに無い）。

---

## 8. 新しい機体を足すときに用意するファイル（2026-11-16、§6 案 1・2・7 の後）

BFE の別の機体（仮に `<mech>`）を 1 機、透と同じ作りで足す場合。透のファイルを複製して差し替えるのが早い。

| # | ファイル | 中身 | 透での例 |
|---|---|---|---|
| 1 | `work/bfe_spr/<mech>.json`、`work/bfe_png/`（その機体の画像）、`work/bfe_waz/<MECH>_named.json` | 入力。BFE の pac から取り出す（§3.1 の 1・2。ゲーム由来なので git に入れない） | `tooru.json`、`TOORU_named.json` |
| 2 | **`mods/<mech>/mech_config.py`** | 機体ごとの値の全部（ID・スロット・名前・入出力パス・`TEMPLATE`・`SKILLS`・`HIDDEN`・`RENAME`・`equip_index()`・初期装備・`MEK_BASIC`・`LABEL`・`HITLOCK_KEEP`・G1 の技名・`SINK_SKILLS`・`COMBO_V3_MODULE`・表の見出し） | `mods/phase3b_tooru/mech_config.py` |
| 3 | `mods/<mech>/build_<mech>.py` | `build_phase3b.py` の複製。同じフォルダの `mech_config` を読むので、中身はほぼそのまま。G0（`TOORU_DIAG`）は消してよい | `build_phase3b.py` |
| 4 | （任意）COMBOV3 のような技名の表 | 作らないなら `COMBO_V3_MODULE = None`（COMBOCLS だけになる） | `tools/bfe2bsdx_combo_v3.py` |
| 5 | （任意）改善版の調整 | **今は機体ごとに分かれていない**（§6 案 4 未実施）。`tools/modified_tweaks.py` の表と `bfe2bsdx_modified_behavior`・`bfe2bsdx_balance` は透の技名で assert するので、別機体で build の I2（改善版）を通すと落ちる。改善版を作らないなら I2 を外す、作るなら案 4 を先にやる | `modified_tweaks.py` |
| 6 | `tools/build_packs.py` の対象 | 今は `mods/phase3b_tooru` 固定（pac の置き場と `SHA256SUMS.txt`）。別機体を回すなら対象のフォルダを引数にする改修が要る | — |
| 6b | 武装表 | `python tools/weapon_table.py --mech <MEKA_NAME> [--pac <pac>]`。mech_config の `MEKA_NAME`・`MOD_DIR`・`MEK_BASIC['mekName']` だけを使う。パックが `MOD_DIR/Update3.pac`・`MOD_DIR/modified/Update3.pac` 以外なら `--pac` | — |
| 7 | ドキュメント | `notes/NN` に移植の記録、制作記録 に 1 行 | — |

注意:
* mech_config の `NEW_ID`・`SPR_SLOT`・`EFT_SLOT`・`WAZ_SLOT`・`SE_CAT`・`VICTIM_*` は §5 の空き枠から選ぶ。**透と同時に入れる**なら番号の衝突（§5.4・§5.5）を先に解決すること（統合は phase3.5 まで作らない方針）。
* `LABEL` は機体ごとに変える（弾の名前の衝突を避ける。§5.5）。
* `HITSTOP_MOVE_F1` を空にした場合、build の G1 は `_g1[C.NOKEZORI_ZERO[0]]` で落ちる（`NOKEZORI_ZERO` を「無し」にする作りになっていない）。新機体で使わないなら G1 の 2 行を条件付きにする。
* `RENAME`・`equip_index()`・`MARKER_DESC` は透の WAZ の並び（通常 63 種×Lv1-3、マーカー 3、必殺 21）が前提。別機体の WAZ の構成は未調査（§3.3 の 7）。
* 共通の決まり（`SKILL_BASE`、共通 waz 4/2/6、基本モーション表）は `tools/bfe2bsdx_common.py`。機体ごとに変える物ではない。
