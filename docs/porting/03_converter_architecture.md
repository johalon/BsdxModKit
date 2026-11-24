# 03 変換器 bfe2bsdx_* の構造と、変換規則の直し方

対象: BFE の透（TOORU）を DiveX の自機にする変換器一式（`tools/bfe2bsdx_*.py` ほか）と、そのビルド `mods/phase3b_tooru/build_phase3b.py`。
読み手: 変換規則を直す・足す人（開発者）。規則タグの網羅的な一覧は `docs/porting/04_conversion_rules_catalog.md`（別担当）。ここは仕組みと代表例だけを扱う。
基準: ワークスペースの写し（2026-11-16 朝）のコード。行番号は「この写しでの目安」で、ずれることがある。関数名で探すこと。

---

## 0. 要点（まずこれだけ）

* 変換の本体は `tools/bfe2bsdx_waz.py` の `Converter.convert()`（1 技 = 1 回の呼び出し）。**BFE のフェーズ 1 つを DiveX のターン 1 つ**にし、フェーズ内のイベント・速度・ジャンプ・ヒット・発射・変化先を、DiveX のスロット（slot 0 スプライト … slot 71 変更処理）のイベントに書き直す（`bfe2bsdx_waz.py` 冒頭 docstring、`調査記録 09 §3`）。
* **甲（kou）の同名技がテンプレート**。BFE に対応が無い・意味が分からない部分だけを甲から写す（`_boiler()`、`BOILER` 定数）。ヒットは甲のヒットを複製して BFE の値で上書きする（`_set_hit()`）。
* 弾・エフェクト・レーザーは `bfe2bsdx_tama.Fx` が「技が実際に撃つものだけ」を変換し、共通 waz（Tama04 / Tama02 / Laser）の末尾に足す（`調査記録 09 §0`）。
* 規則は **`rep.add('タグ', メッセージ)`** で記録され、`tools/provenance.py` の `KIND_CAT` が R/E/V/T/X/M に分類して `調査記録 15` を自動生成する。全件は `work/tooru_port/report.txt`。
* 直すときの原則: **武装名で分岐しない／原作 exe とバニラ実例の両方を根拠に／原作に無いフレーム・ターンを足さない／機械的変換を優先**（`制作記録`「変換の方針」、`制作記録 §2`）。原作再現版で再現できないものは、ワークアラウンド（監修つき）か、改善版（`tools/modified_tweaks.py`）へ回す（`調査記録 60` 冒頭、`制作記録 11/15 夜`）。

---

## 1. データの流れ

### 1.1 全体図

```
BFE 側（<BFE> の pac → tools/bfepac.py で展開済みのものを work/ に置いて使う）
  TOORU.WAZ ──bfe_waz.py（bfe_waz_fields.json で名前付け）──> work/bfe_waz/TOORU_named.json ─┐
  Tama.dat  ──bfe_waz.py──────────────────────────────> work/bfe_waz/Tama_named.json   ─┤
  tooru.spr ──bfe_spr.py──> work/bfe_spr/tooru.json ; tooru*.grp ──bfe_gr2.py──> work/bfe_png ─┤
  Bmp/Effect/Effect.spr + *.grp ──bfe2bsdx_effspr.parse / bfe2bsdx_eft.decode_sheets──────────┤
  BaldrForce.exe の表（エフェクト番号→アニメ）──bfe2bsdx_effmap──> work/tooru_full/effmap.json ─┤
  SE の wav（work/bfe_se）、EquipmentInfo.DAT（説明文）──────────────────────────────────┤
                                                                                            v
DiveX 側のバニラ（work/extracted の Kou.waz / Kou.mek / 共通 waz / grp）──PortTool b2j──> JSON
                                                                                            v
                         mods/phase3b_tooru/build_phase3b.py（A〜I2 の節）
                                                                                            v
  Tooru.waz / Tooru.mek / tooru.spm / tooru_eft.spm / Tama02・Tama04・Laser.waz（末尾追加）/ grp / dat / ogg
      ──PortTool j2b（再パース一致を確認）──> files/ ──nexaspac.py create──> Update3.pac（原作再現版）
      └─ 同じ JSON の写しに balance / modified_behavior を当てて ──> modified/Update3.pac（改善版）
```

出どころ: `build_phase3b.py` 冒頭の定数（`BFE_SPR`・`BFE_WAZ`・`BFE_TAMA`・`BFE_SE`・`BFE_EQUIP`・`BFE_EFFECT`）、`bfe2bsdx_spm.py` / `bfe2bsdx_eft.py` / `bfe2bsdx_effmap.py` の docstring。

### 1.2 BFE から読むもの（入力）
| BFE のデータ | 読むモジュール | 何に使うか |
|---|---|---|
| TOORU.WAZ（技: ヘッダ 0x6C ＋ フェーズ 0x18C ＋ スプライトイベント 48B） | `bfe_waz.py`（構造）＋ `bfe_waz_fields.json`（名前・意味） | 機体の技 87 個の変換元（`調査記録 09 §0`） |
| Tama.dat（弾・爆発。WAZ と同じ形） | 同上 | 弾技（Tama04 へ）。技が撃つ連鎖をたどって必要な分だけ |
| tooru.spr ＋ GR2 シート | `bfe_spr.py` / `bfe_gr2.py` → `bfe2bsdx_spm.py` | 機体 spm（ページ・判定矩形・合成） |
| Effect.spr ＋ シート | `bfe2bsdx_effspr.py` → `bfe2bsdx_eft.py` | `tooru_eft.spm`（SpriteGroup 135）。使うアニメだけ |
| BaldrForce.exe のハンドラ表 0x4d45ec | `bfe2bsdx_effmap.py`（objdump の bf.asm と exe から抽出） | BFE のエフェクト番号 → Effect.spr アニメ（`調査記録 09 §8.1`） |
| exe の SE 名表 | `bfe_waz_fields.json` の `enums.se` | `SeMap`（新しい SE 項目の番号） |

* BFE の「named JSON」のキー（`speed` / `jump` / `hit` / `noke_mech` / `fire` / `go_hit_mech` / `move_dir` / `lock1` …）は `bfe_waz_fields.json` の `structs` から来る。意味の確度（CONFIRMED / LIKELY / UNKNOWN）もそこにある（`gen_bfe_waz_fields.py` docstring）。
* 既知のずれ: 標的ﾀｲﾌﾟの列挙が `bfe_waz_fields.json` では 1 つずれている（「要修正、未着手」、`調査記録 60 §4`）。

### 1.3 DiveX に出すもの（出力）
| 出力 | 中身 | 出どころ |
|---|---|---|
| `Tooru.waz` | 100 技: 0–10 基本動作（甲を複製、ダッシュは村正・ノイ）、11 区切り、12–98 移植 87 技、99 イニシャライザ | `調査記録 09 §0`、build の C 節 |
| `Tama04.waz` 末尾 | 変換した BFE 弾（「（透移植弾N）」） | `bfe2bsdx_tama.Fx.tama_target()` |
| `Tama02.waz` 末尾 | BFE のエフェクト技（「BFEエフェクトNN（透移植）」） | `Fx.effect_target()` |
| `Laser.waz` 末尾 | レーザー・ワイヤーのライン（根元／ライン親／ライン子／先端） | `bfe2bsdx_line.LineBuilder.build()` |
| `Tooru.mek` | 甲の mek を土台に武装 88・熱・AI・MaterialBlock | build の E 節 |
| `tooru.spm` / `tooru_eft.spm` / grp / dat / ogg | 絵・登録表・SE | build の B・C2・D・F 節 |

waz.json の形（NeXAS_DX の JSON）: `skillList[技] → phasesInfo[ターン] → skillUnitCollection[]`（`unitQuantity` = スロット番号）`→ skillInfoObjectList[]`（イベント。`startFrame` / `endFrame` とスロットごとの値）。ヒットは `ceventHitUnitList`、生成は `ceventEffectUnitList`（サブスロット）、変化は `bsdxInfoCollectionList1/2`（Term）。スロット名は `tools/waz_fields.json` の `slots`（`docs/formats/05_waz_field_dictionary.md`）。

### 1.4 甲テンプレート方式
* 対応表 `TEMPLATE`（build、BFE の WAZ 番号 → 甲の武装番号）で、各技に甲の同名技（Lv3）を割り当てる（build の `TEMPLATE` / `kou_skill_of()`）。
* テンプレートから使うもの（`Converter`）:
  * **定型スロット**: `_boiler()` が甲の **ターン 0** から `BOILER = (6, 24, 26, 27, 28, 30, 31, 33, 45, 46, 47, 54, 67, 69, 70)`（弾は `BOILER_BULLET = (26, 45, 70)`、FC は `FCSLOTS` 59–66/68 も）を、ターン長の比で伸縮して写す。写す前に規則で落とす・直すもの: slot 47 の値 3 以外（HITCANCEL）、slot 30（SDKEEP）、slot 6（SHAKE0）、slot 54（SHADOW）、slot 33 の正規化（SLIP）。
  * **ヒット**: 甲のヒットオブジェクトを順番に複製し、`_set_hit()` が BFE の値で上書き。同じ BFE ヒットの繰り返しは最初のテンプレヒットを再利用（HITREPEAT）。甲に直接ヒットが無い技は甲ボディブローLv3 のヒット（`conv.default_hit`）を土台にする（APPROX として記録）。
  * **発射イベント**: 甲の同名技の slot 48 を複製。無ければ甲ハンドガンの発射（`FALLBACK_PROJ`）。
* 弾のテンプレートは Tama01「ハンドガン：甲」、その他の「書き方の見本」（追従・接触オフ・発射位置補正など）もバニラの特定の技から取り、取り出し時に `assert` で技名を確かめている（`Fx.__init__`）。
* `Lib`（`bfe2bsdx_waz.py`）はバニラ waz から「スロット × typeId の見本オブジェクト」「条件・ジャンプの Term の見本」を集めておく辞書。新しいイベントは `lib.obj(slot, typeId, start, end, ...)`、変化は `lib.change(conds, jump, start, end)` で作る（甲を最初に渡すので甲の見本が優先）。
* 方針の現在形: 「BFE から変換不可能な値だけテンプレに残し、他は全て透から」（ユーザー 11/11、`調査記録 40`）。甲のまま残している値とその理由は `調査記録 40` の表。

### 1.5 NeXAS_DX（Java）を使う箇所
* 呼び出しは `bfe2bsdx_common.porttool(*jobs)` だけ。`java ... PortTool`（`tools/harness/PortTool.java`）に `b2j`（バイナリ → JSON）/ `j2b`（JSON → バイナリ。生成後に再パース・再生成がバイト一致することを確認）を渡す。クラスは `work/tooru_port/nexas_snap` のスナップショットから読む（並行ビルドの干渉よけ。`bfe2bsdx_common.py` docstring）。
* build での使いどころ: A 節（バニラの grp・共通 waz・Kou.waz/mek・SelectMekaMenuMeka.spm を JSON に）、C 節（`bfe2bsdx_basic.jobs()` で村正・ノイ）、G 節（生成 → 再パースして `norm()` 比較、共通 waz はバニラのバイト列が先頭にそのまま残ることも確認）、I2 節（改善版も同じ確認）。
* `VAN = work/nexas_rt/json`（バニラ全体の JSON、RoundTrip の出力）は mek_check と spm の参照に使う。

---

## 2. モジュールの地図

### 2.1 build_phase3b.py の節と呼び出し関係
| 節 | やること | 呼ぶもの |
|---|---|---|
| A | バニラを JSON に（`assert` で登録表の件数を確認） | `porttool` |
| B | 機体 SPR → spm、セレクト画面のサムネ | `bfe2bsdx_spm.convert()` |
| 先頭 | 機体の値を `mech_config`（同じフォルダ）から読む（`import mech_config as C`）。BFE 共通の定数は `bfe2bsdx_common` | `mech_config.py`（09 §2.0） |
| C | `Lib` / `SeMap` / `Fx(label=C.LABEL, combo_v3=)` / `Converter(mode='mech', sink_skills=C.SINK_SKILLS, combo_v3=)` を作り、基本動作 0–10・ダッシュ・**87 技を `conv.convert()`**・イニシャライザ。弾・エフェクト・ラインは convert の中から `Fx` 経由で変換される | `bfe2bsdx_waz`、`bfe2bsdx_tama`、`bfe2bsdx_line`、`bfe2bsdx_basic` |
| C 後半 | HITLOCK（`C.HITLOCK_KEEP` で手指定）、Effect spm（使うアニメだけ）、参照範囲の `assert`、`double_armor` | `Fx.hitlock_exempt()`、`bfe2bsdx_eft.build_effect_spm()` |
| D | SE（wav → ogg、決定的） | ffmpeg |
| E | mek（熱 HEAT、AI の武器番号の付け替え、MaterialBlock） | `bfe2bsdx_basic.apply_mek()`、`material_for()` |
| F | grp 登録 | — |
| G0 | 診断パック（`TOORU_DIAG` のときだけ） | — |
| G1 | エンジン差のパッチ（`_hitstop_move_f1`: 技名は `C.HITSTOP_MOVE_F1`・`C.NOKEZORI_ZERO` = ブーストアッパー・メガ BU。後述 §5.2） | — |
| G1b | FIRELOCK の目印を消す、FOLLOWCUT（`_followcut()`。この機体の弾 = 名前に `fx.label + '弾'`） | — |
| G | 改善版用の値 `_bal` を退避 → 生成 → 再パース一致 | `bfe2bsdx_balance.pop_bal()`、`porttool` |
| H | `mek_check.py`（違反 0）と `--full --spm`（バニラ基準外 0）を `assert` | `tools/mek_check.py` |
| I | pac 作成と展開検証 | `tools/nexaspac.py` |
| I2 | 改善版: ダメージ系 → 挙動系の調整、変わってよいキー以外が同じことを `assert` | `bfe2bsdx_balance.apply()`、`bfe2bsdx_modified_behavior.apply(bgen, self_waz=, bullet_waz=, spm_file=, eft_file=, eft_slot=)`、`modified_tweaks` |
| 末尾 | `weapons.json`・`weapons_table.md`・`調査記録 15`・`調査記録 15b`・`調査記録 15c`・`report.txt` | `provenance.write()`、`Report.dump()` |

* 実行: `python tools/build_packs.py`（同期 → 通常と `--waz110` を 2 回ずつビルド → sha256 照合 → 配置。02 §3）。単発なら `python mods/phase3b_tooru/build_phase3b.py [--waz110]`。
* 並行作業のときの `work/tooru_port/BUILD.lock` は build_packs.py が確認して置く（30 分以内のロックがあれば止まる）。build_phase3b.py 自身は見ない。

### 2.2 各モジュールの役割
| ファイル | 役割 | 入力 → 出力 | 主な入口 |
|---|---|---|---|
| `bfe2bsdx_waz.py`（約 2,880 行） | **技・弾の変換の本体**。mode `'mech'`（機体の技、絵は tooru.spm = spm -1、anim = 60 + SPR スロット）/ `'bullet'`（弾、絵は tooru_eft.spm）。規則の大半がここ | BFE named 技 ＋ 甲テンプレ JSON → DiveX 技 JSON | `Converter.convert()`、`_set_hit()`、`_set_noke()`、`_set_fire()`、`_boiler()`、`_post_apex()`、`ev_timing()` |
| `bfe2bsdx_tama.py` | 弾・エフェクト・ラインの**登録簿**（必要になったら変換して共通 waz に割り当て、番号を返す）。バニラの見本の収集 | Tama 番号 / エフェクト番号 → (ファイル, 技番号) | `Fx.tama_target()`、`effect_target()`、`line_chain()`、`phase_bullet()`、`tail_bullet()`、`hit_cancel()`、`hitlock_exempt()` |
| `bfe2bsdx_line.py` | レーザー・ワイヤー（線分の連鎖）→ DiveX のライン。甲の同名武装のライン一式を複製して BFE の絵・本数・伸び・拡大・ヒットを入れる | BFE 根元 Tama ＋ 甲の Laser 鎖 → Laser.waz の新しい鎖 | `LineBuilder.build()`、`_root/_parent/_child/_tip()`、`_hits()`、`stops_at_hit()`（PIERCE） |
| `bfe2bsdx_common.py` | PortTool 呼び出し、JSON 入出力、`Report`（規則の記録）。**BFE 機に共通の定数**: `SKILL_BASE`、`SHARED_WAZ`、`BULLET_FILE/EFFECT_FILE/LASER_FILE`（4/2/6）、基本モーション表 `BASIC`、`BASIC_ANIM_SLOT`（11/16 から。spm・waz はここから import） | — | `porttool()`、`Report.add/mark/since/dump` |
| `mods/phase3b_tooru/mech_config.py` | **透の機体設定**（ID・スロット・名前・パス・`TEMPLATE`・`SKILLS`・mek 基本値・`HITLOCK_KEEP`・G1 の技名・`SINK_SKILLS`・`COMBO_V3_MODULE`・`LABEL` など）。build だけが読む。変換器は機体の値を引数で受け取り、透の技名を持たない（09 §2.0） | — | — |
| `bfe2bsdx_spm.py` | 機体 SPR → spm。ページ = SPR フレーム、判定スロット → hitFlag ビット、合成の焼き込み | SPR JSON ＋ PNG → spm JSON ＋ PNG | `convert()`、`blend_of()`、`true_layout()` |
| `bfe2bsdx_eft.py` / `bfe2bsdx_effspr.py` / `bfe2bsdx_effmap.py` | Effect.spr のパース、使うアニメだけの spm、エフェクト番号 → アニメ表 | — | `build_effect_spm()`、`upright_anims()`、`parse()`、`load()` |
| `bfe2bsdx_basic.py` | 基本性能（ダッシュ速度・SD/BD 技の差し替え、BFE 外の手入力 M） | — | `apply_waz()`、`apply_mek()`、`add_sd_extras()` |
| `bfe2bsdx_combo_v3.py` | 透の格闘・射撃の通常技のコンボ補正と最低値（COMBOV3）。表 `OPENER`・`LATE` はデータからの生成値。変換器は import せず、build が `Converter(combo_v3=)` で渡す（渡さなければ COMBOCLS だけ） | 技名 → 補正 | `in_scope()`、`start_corr()`、`end_corr()` ほか |
| `bfe2bsdx_balance.py` | 改善版のダメージ系（威力・最低値・補正・装甲攻撃力・ヒット数上限）。`modified_tweaks` の値だけを見る | 原作再現版 JSON の写し → 改善版 | `pop_bal()`、`apply()`、`only_keys_changed()` |
| `bfe2bsdx_modified_behavior.py` | 改善版の挙動系（ターン・速度・判定）。各関数は相手のデータを `assert` で確かめてから変える | 同上 | `apply()`、`ORDER` |
| `modified_tweaks.py` | 改善版の調整の**一覧と on/off・params**（`TWEAKS`）。`python tools/modified_tweaks.py` で一覧 | — | `on()`、`p()`、`table()` |
| `provenance.py` | 規則タグ → 分類（`KIND_CAT`）、武装ごとの出どころ表を書く | `Report` のログ → `調査記録 15` | `category()`、`summarize()`、`write()` |
| `bfe2bsdx_render*.py` | 目視確認用の描画（spm ページ、技のスプライト列、ライン） | — | CLI |
| `bfe_waz.py` | BFE の WAZ / Tama.dat / CPU のパーサ（EOF まで読めることを確認済み） | バイナリ → named JSON | `parse()`、`decode()`、CLI |
| `bfe_waz_fields.json` / `gen_bfe_waz_fields.py` | BFE データ形式の辞書（exe に残るエディタのダイアログとコードから生成） | exe → JSON | — |
| `waz_fields.json` / `gen_waz_fields.py` | DiveX waz のスロット辞書（手書きの意味 ＋ バニラ JSON の値域） | — | `provenance._slotname()` もこれでスロット名を付ける |
| `gen_terms_ux_md.py` | `docs/game_spec/41_terms_ux.md` を `waz_terms_ux.json` と `waz_fields.json` から作る | — | — |
| `attack_count_check.py` | 全技・全弾の「攻撃回数（ヒット・発射）」を BFE と DiveX 出力で数えて比べる | build の `check/waz/*.json` | CLI（§5.5） |
| `weapon_table.py` | 武装一覧（威力・補正・属性・早期廃熱・EX キャンセル）を Markdown で。読み取りのみ | 置いてある pac（展開して PortTool で JSON に戻す。`_ws/table_cache` にキャッシュ） | CLI |

---

## 3. Converter.convert() の中身

### 3.1 流れ（`bfe2bsdx_waz.py` の `convert()`、約 L654–1982）
1. **技全体の準備**: 技タイプ（ヘッダ +0x29: 0 打撃 / 1 射撃）から HITCANCEL の可否、`_combo_setup()`（COMBOCLS）、`_rep_setup()`（REPDECAY）。
2. **技順（alg_list）→ ターン**: 初出のフェーズはそのフェーズ番号のターン、繰り返し出るフェーズは末尾に複製ターンを足す。ループは「技順の位置」として解釈（LOOPPOS）。
3. **フェーズごと**（`for ti_, pi in enumerate(turn_phase)`）に、`ev = defaultdict(list)`（スロット → イベント）を埋める。コメントの区切りは `# ---- movement` / `# ---- body collision` / `# ---- hit` / `# ---- projectile` / `# ---- transitions`。
4. **技全体の後処理**: 最初の攻撃フレームまでの向き追尾（slot 10 方向増分 300 → 0、甲の書き方）、`_boiler()`、FC 演出の位置（`_fc_at()`、FCPHASE）、slot 47 の値 3 区間の分割（HITCANCEL）、HOMING_EITHER、TWINMUZZLE、DIR16RESET、空中時の振り分け（AIR、甲ブーストキックの書き方）、着地分岐、技後の上昇（`_post_apex()`、POSTAPEX）、命中で終わる動く技の 1F 停止ターン（STOP）。
5. 最後に `phasesInfo` を組み立てて返す（イベントは開始フレーム順、slot 71 だけは並び順を保つ）。

### 3.2 BFE の項目 → DiveX のスロット（主なもの）
| BFE | DiveX | 主な規則（タグ） | 場所 |
|---|---|---|---|
| スプライトイベント（アニメ・ウェイト・ｱﾆﾒﾀｲﾌﾟ 0–4） | slot 0（パターンごと）。1 コマ = (wait+1) tick、1 tick = 2F | FIREIV（撃ち終わるまで型）、LANDHOLD | `ev_timing()`、`ev_len()`、`patterns()` |
| 拡大縮小 | slot 1 | ZOOMTYPE0（type バイトは exe が読まない） | `zoom_events()` |
| 描画属性 3–9 | slot 7 SpriteAttr | BLEND | `SPRITE_ATTR` |
| 装甲効果率 ≥3 | slot 36 | — | convert のイベント処理 |
| 速度 初期/最終/増分 | slot 18（機体は /2 px/F）＋ slot 15 方向 | MOVE、INERTIA、SPEEDCUT、RESTRAMP、BSPEED（弾は slot 25 50% ＋ 生の値）、BDECEL | `# ---- movement` |
| ジャンプ（縦） | slot 19 速度イベント ＋ 重力 0（BFE の縦の軌跡をそのまま写す） | VERT、TOUCHCARRY、BHOLD・BHOLDANY（弾）、BFALL | `bfe_vert_sim()`、`_vert_events()`、`bfe_bullet_vert()` |
| 接触処理 メカ敵 0 | slot 51（甲 Ｉ・Ａ・Ｉ の接触オフ） | TOUCH、BTOUCH、SINK | `# ---- body collision` |
| ヒット（HIT 数 > 0 かつ攻撃判定のある区間） | slot 41（対メカ）/ 42（対弾） | HIT、MINDMG、COMBOCLS/COMBOV3、SELFDECAY、HITIV、HITDELAY、NODMG、NORECT、HITFX0、ELEMENT | `_set_hit()`、`_element()`、`_nodmg_hit()` |
| のけぞり | Hit サブ 17/18（地上/空中）ほか | NOKE、LAUNCH、NOKEDOWN、NOKEFLOAT、SLAMKEEP、NOKEPARENT、NOKECHAIN | `_set_noke()`、`bfe_launch()` |
| 弾発射（「弾発射」フラグのイベントだけ） | slot 48 生成（生成先 = 変換した弾） | FIREIV、SWEEP、POSCORR、LOCKTARGET、STICKTARGET、FIRELOCK（目印）、NOFIRE | `# ---- projectile`、`_set_fire()`、`spawn()` |
| レーザー・ワイヤーの発射 | slot 48 → ライン親 | LINE、PIERCE | `Fx.line_chain()` → `LineBuilder.build()` |
| 常時・発射位置エフェクト | slot 48（エフェクト技） | EFFTARGET | `effect_spawn()` |
| SE | slot 52、Hit サブ 28 | SEVOICE | `se_obj()`、`_se_voice()`、`SeMap` |
| 変化先 go_*（-1 = 技順の次、99 = 終了） | slot 71 変更処理（Term の条件 ⇒ ジャンプ） | AIR、LOOP/LOOPPOS、MECHDIST、DISTOUT、IGNORED | `# ---- transitions`、`lib.change()` |
| フェーズ flags bit6 空ｷｬﾝｾﾙ / bit7 初期化、射撃の発射 | slot 47 ｷｬﾝｾﾙﾌﾗｸﾞ | HITCANCEL | convert の HITCANCEL ブロック |
| 残像 | slot 49 | BLINK | convert |
| ﾐｻｲﾙ炎＆煙 | slot 48（Laser[67] 煙 ＋ エフェクト 23） | MISSILEFX | convert |

単位換算の柱（どれも exe とバニラで裏付け、詳細は `調査記録 09 §3`・`調査記録 15 §3`・コメント）:
* 時間: BFE 30fps → ×2F。1 コマは (wait+1) tick（BaldrForce.exe 0x413244）。
* 速度: 機体 BFE px/tick → /2 px/F（M 10-28）。弾は slot 25 ﾍﾞｸﾄﾙ補正率：技 50% ＋ 生の値で v/2 を正確に（BSPEED）。
* 威力: BFE ÷4（確定、`制作記録`）。DiveX は「甲以外の自機」の威力表示に ×1.5 を掛け（BaldrSky.exe 0x63ba40）、最低値には掛けないので、最低値 = BFE ×3/8（MINDMG、`_set_hit()`）。
* 吹き飛び: 規模 = 40H/T、重力 = 3200H/T²（H・T は BFE の打ち上げの頂点と滞空、DiveX 重力は /200。LAUNCH、`_set_noke()`）。旧: 規模 = 2·L²（上限 150）→ 現: 2·L² は叩きつけ（負の打ち上げ）だけ。
* のけぞり水平: 速度 = v/2、減速率 = 増分 ×100/1024（同じ距離、`_set_noke()`）。
* ヒットストップ: max(6, BFE ﾋｯﾄｳｪｲﾄ ×2)（機体）。

---

## 4. 変換規則はコード上どう表現されているか

### 4.1 規則タグ = `rep.add()` の kind
* 規則が値を書き込むたびに `self.rep.add('TAG', 'メッセージ')`（`bfe2bsdx_common.Report`）。タグは大文字の英字（例 `HITCANCEL`、`POSTAPEX`、`BSPEED`、`LOOPPOS`、`TOUCHCARRY`）。
* `Report` は 2 つを持つ: タグ別の件数（`items`、`report.txt` に出る）と順番どおりのログ（`log`、武装別の出どころ表に使う）。
* 定数・フラグとして出てくるタグもある: `SINK_SKILLS`（技名の集合。11/16 から mech_config にあり `Converter(sink_skills=)` で渡す）、`DASH_SPEED`、`MAXSPAWN`、`COMBO_CLASS`、`ELEM_BITS`、`POST_G` など。
* 一時的な目印をオブジェクトに付けて後で処理する書き方がある: `o['_c47']`（HITCANCEL の分割用）、`ch['_apex']`（POSTAPEX）、`tp['_bal']`（改善版の最低値。build G 節で外す）、`o['_firelock']`（build G1b で外す）、`u['_drop']`（HITFX0）。**目印を足したら、出力前に必ず消す**（消し忘れは再パース比較で気づくとは限らない。`_bal` は `pop_bal()`、`_firelock` は build で pop）。

### 4.2 規則のコメントの書式
規則ごとに次の形のコメントが付いている（例は `bfe2bsdx_waz.py` の TOUCHCARRY、L1142 付近）:

```
# G 2026-11-04 (TOUCHCARRY, 調査記録 30): BFE 0x444560 - an object whose contact flags ... does NOT move that tick ...
#   DiveX has no such freeze -> 透 flew 169 px past short enemies (1 hit, user 20261103_4).
#   -> 透's height = his own curve, never passing the victim launched by this phase's hit ...
```

* 先頭の 1 文字: 書いた担当（M = 動き、S = 弾、N = 数値、B = バランス、ほか G / W / L / T）か、provenance の分類（R / E / V）。統一されていないので、分類は必ず `KIND_CAT` で見る（`調査記録 16` 冒頭の §M/§S/§N、`制作記録 §2`）。
* 中身の順番: **ユーザーの指摘（原文の引用）→ BFE の exe の処理（アドレス）→ DiveX の exe の処理 → バニラの実例 → 規則**。旧規則を置き換えたときは「was …」「superseded …」「replaces the 10-30 …」と残す。
* 一部の規則はコメントにだけ名前があり、report には別のタグで出る（例: `CHIPAIR`・`NORECT`・`RANDLOW`・`SPAWNYPCT`・`STICKFLOOR`・`MECHSPR` は `KIND_CAT` に載っているが、この写しのコードで同名の `rep.add` は無い）。

### 4.3 provenance（値の出どころ）への記録
* 分類（`tools/provenance.py`、説明は `調査記録 15 §2`）:

| 記号 | 名前 | 意味 |
|---|---|---|
| R | 変換・確定規則 | exe（かバニラ実例）で裏付けた規則で BFE の値を変換 |
| E | 変換・推定係数 | 変換しているが係数・意味が推定。**ワークアラウンドもここに入れている**（FOLLOWCUT・TIPDETACH・DIVETOUCH は E、`制作記録 11/15`） |
| V | バニラ書式の流用 | BFE の挙動を DiveX の同じ挙動の技の書き方で表現 |
| T | テンプレ値のまま | BFE に対応が無く甲の値 |
| X | 除外・未対応 | 使っていない BFE データ |
| M | 手入力（BFE 外） | 設計判断・ユーザー要望の値 |

* 仕組み:
  * `KIND_CAT` = タグ → 分類の辞書。`APPROX` だけはメッセージの文言で振り分け（`category()`）。`INFO`（BULLET・SKILL・SPM など）は表に出さない。
  * build は技ごとに `m0 = rep.mark()` → `conv.convert()` → `rep.since(m0)` で、その技の記録を `prov_own` に入れる。弾の記録は `Fx.tama_log`（`log_for()`）で、撃った武装の「撃つ弾」欄に出る。HEAT・ARMOR は build が武装に足す。
  * `provenance.write()` が `調査記録 15` を作る（原作再現版の通常ビルドだけ。waz110 では作らない）。**手で編集しない**（`制作記録`）。
* 落とし穴（この写しのコードで確認）:
  * **`KIND_CAT` に無いタグは黙って R に数えられる**（`summarize()` の `or 'R'`）。この写しで未登録: `COMBOV3`、`ELEMENT`、`HITFX0`、`HITREPEAT`、`LINEIV`、`LINEWIN`、`SHADOW`、`SHAKE0`、`SINK`、`TPLHIT0`、`HITSTOPMOVE`（ほか INFO 扱いの `BALANCE`・`BEHAVIOR`）。新しいタグを足したら `KIND_CAT` にも足す。
  * ライン（`bfe2bsdx_line.py`）の個々の規則は `notes` に溜めて最後に **`LINE` タグ（V）でまとめて**出す。そのため TIPDETACH（`KIND_CAT` では E）も表では「V [LINE] … (TIPDETACH)」になる。
  * build の後処理（G1 の HITSTOPMOVE、G1b の FOLLOWCUT）は `rep.add` だけで武装の `prov_own` に入らないので、**武装別の出どころ表には出ない**（report.txt にだけ出る）。

### 4.4 代表例（どこに・どう書かれているか）
| タグ | 分類 | 場所 | 中身（要約） | 資料 |
|---|---|---|---|---|
| HITCANCEL | R | `convert()` 冒頭（技タイプ）、フェーズ末の slot 47 ブロック（約 L1587）、`_boiler()`（甲の slot 47 の 0/1/2 を落とす）、後処理（値 3 の区間を BFE の 1F イベントの前後で分割、約 L1818）、`_set_hit()`（Hit +0x64 `selfStunFrame` = 打撃なら 1）、`Fx.hit_cancel()` / `melee_tamas`（打撃技が撃った打撃の弾だけ 1）、`line._hits()` | BFE: 打撃のヒットで +0x3e = 1、射撃は発射で 1、フェーズ flags bit6/bit7。DiveX: Hit +0x64 == 1 → [+0x1900] = 1、slot 47 の値 0/1 → [+0x1900]、値 3 → キャンセル操作の窓 | `調査記録 20` |
| POSTAPEX | R（コメントは M） | 変化処理で終了する slot 71 に `_apex` の目印 → `_post_apex()`、`dx_rise()`、`POST_G` | 空中で終わる技の「技後の上昇の頂点」を BFE と一致させる。技後に BFE に無いターンを足していた FREEFALL を置き換え | `調査記録 19`、`制作記録` |
| BSPEED | R | `# ---- movement`（弾は slot 25 50% を各ターン F0 に）、`Fx.tama_speed()`（生成の初速） | BFE の弾速（整数 px/tick）を v/2 px/F に正確に（奇数の丸めで 2 倍速になっていた） | `制作記録 §3` |
| LOOPPOS | R | `convert()` のループ準備（約 L714）と遷移（約 L1771）、ターン 0 へ戻るループの初期化を省く（約 L1800） | ループの開始・終了は**技順の位置**。DiveX の汎用変数は 1 つなので、しきい値 = 前のループの回数の合計 + 回数 − 1 | `調査記録 25` |
| TOUCHCARRY | R（コメントは G） | 機体の縦（`bfe_vert_sim()` の後、約 L1142） | 打ち上げた相手に接触している間は BFE では自分が動かない → 透の高さを「自分の軌跡」と「打ち上げた相手の最高点」の小さい方に | `調査記録 30` |
| FIRELOCK | R | `convert()` の発射（約 L1526）で `_firelock` の目印 → build G1b | 「弾発射位置ﾛｯｸ」付きの発射。11/15 夜に build 側の処理は撤去され、目印を消すだけが残る（追従弾は slot 11 の STICK 系で表す） | `調査記録 57 §3`、`調査記録 59`、`調査記録 60 §7`、build G1b のコメント |
| FOLLOWCUT | E（ワークアラウンド） | build G1b `_followcut()` | 撃った側のアニメが発射ターン内で変わるフレームで、追従弾の slot 11 と付随の 15/18/19 を止める（EF 42F・ギガンテック 52F） | `調査記録 60 §8`、`制作記録 11/15 夜` |
| TIPDETACH | E（ワークアラウンド） | `line._tip()`、`Fx.tail_bullet()` | 技の終了で入る先端の段は、BFE のその段以降を独立した弾として出し、先端は F1 で終わる（DiveX のライン先端の制約を避ける組み替え） | `調査記録 61` |

---

## 5. 規則を足す・直すときの手順とお作法

### 5.1 原則（今も有効）
1. **武装名で分岐しない（値の個別上書きをしない）**。変換規則を直して全武装に効かせる。直すときの根拠は **(a) 原作 exe の処理 (b) バニラ BSDX 機体の実例の両方**（`制作記録 §2`、`調査記録 15 §1・§5`）。
2. **原作の技に無いフレーム・ターンを足さない**。技は原作どおりのフレームで終わらせ、技後の動きは DiveX の技後処理で表す。技後の上昇は頂点の高さを一致させる（着地までのフレーム数は不要）（`制作記録`「変換の方針」）。
3. **機械的な変換を優先**。目合わせ・推定値は exe の式から求めた値に置き換える。近似が残るなら「何が近似で、DiveX のどの制約のためか」を明記する（同上）。
4. 判断の優先順位: コンボの再現性（キャンセルの可否・タイミング・キャンセル時の慣性）＞ 単発の見た目（`制作記録`「大目的」）。
5. 原作再現版では**ワークアラウンドをできるだけ避け、原作パラメーターの移植を優先**。再現できないものだけワークアラウンド可（事後に手法の監修を通す）。**案件は 1 つずつ**（ユーザー 11/15、`調査記録 60` 冒頭、`制作記録 11/15 夜`）。
6. 甲テンプレは「BFE から変換不可能な値」だけに残す（ユーザー 11/11、`調査記録 40`）。

### 5.2 現にある「名前での分岐」（例外として把握しておく）
旧: 「武装名で分岐するコードは変換器に 1 か所も無い」（`調査記録 15 §1`、10/27 時点）→ 現: 次の例外がある。どれもユーザーの指示か、理由がコメントに書いてある。新しく足すときは同じ扱い（理由・ユーザー指示をコメントと STATUS に残す）にする。
| 場所 | 中身 | 理由 |
|---|---|---|
| `mech_config.SINK_SKILLS`（インペリアルストライク・インペリアルファイナル）→ `Converter(sink_skills=)` | 技全体で接触オフ（SINK） | ユーザー 11/11。BFE は機体の押し出しが無い（コメントに exe の根拠） |
| build G1 `_hitstop_move_f1`（技名は `mech_config.HITSTOP_MOVE_F1` = ブーストアッパー 2 / メガ・ブーストアッパー 3、`NOKEZORI_ZERO`） | ヒットで入るターンの F0 の移動を F1 へ（HITSTOPMOVE）、メガ BU の停止時間 0 | 「Named per skill on purpose (not a general converter rule)」= ユーザーの手修正を採用（11/10、メガ BU は暫定） |
| `mech_config.HITLOCK_KEEP` / `HITLOCK_KEEP_TURNS`（build C 後半） | ヒットロックに反応させる弾を手指定 | 甲も混在なのでユーザーが手で分類（11/09、`調査記録 36`） |
| `bfe2bsdx_combo_v3.py` の `SCOPE`・`PUNCH`・`OPENER`・`LATE`・`MOD_MIN_SET`（`Converter(combo_v3=)` で渡したときだけ効く） | 技名ごとの補正 | 表はデータからの生成値（`OPENER`/`LATE`）。`MOD_MIN_SET` は改善版のユーザー指定 |
| `bfe2bsdx_modified_behavior.py`・`bfe2bsdx_balance.py` | 改善版の技ごとの調整 | 改善版はもともと技ごとの調整の場所（§5.3） |

### 5.3 ワークアラウンドと改善版への振り分け
* **原作再現版（3b）に入れてよいもの**:
  * R / V の規則（exe で原作の処理が分かり、DiveX で同じ結果になる書き方がある）。
  * 係数が推定の規則（E）。実機で合わなければ係数を疑い、直すなら規則ごと（`調査記録 15 §2`）。
  * ワークアラウンド（E）は「原作のパラメーターでは再現できず、DiveX の部品の制約を避けるもの」に限る。コメントと notes に「ワークアラウンド」と書き、ユーザーの監修を待つ（例: TIPDETACH「ユーザーの監修が要る」`調査記録 61`、FOLLOWCUT は了承済み `制作記録 11/15 夜`）。
* **改善版（modified）へ回すもの**:
  * 原作に無いターン・フレームを足す必要があるもの（例: サテライトレーザーのターン追加 DIVEHOLD → 原作再現版から外し、改善版 `SAT_HOLD` へ。`調査記録 60 §5`）。
  * 遊びやすさのための値の変更（威力・最低値・EX キャンセル区間・速度など）。
* 改善版に足す手順（`制作記録 §2` 11/10〜、`tools/modified_tweaks.py` docstring）:
  1. `tools/modified_tweaks.py` の `TWEAKS` に 1 件（`id`・`kind`（ダメージ / 挙動）・`on`・`since`・`target`・`what`・`why`・`params`・`impl`）。
  2. 実装: ダメージ系は `bfe2bsdx_balance.py`（`MT.p(id, key)` で params を読む）、挙動系は `bfe2bsdx_modified_behavior.py` に関数を書き、`ORDER` に足す（`TWEAKS` の挙動項目と `ORDER` が一致しないとモジュール読み込みで `assert` が落ちる）。
  3. 挙動系の関数は、技名・ターン・元の値を `assert` で確かめてから変える（例 `galaxy_divespeed()`）。変換が変わって前提が崩れたらビルドが止まる。
  4. build I2 が「改善版で変わってよいキー（`bfe2bsdx_balance.KEYS`）以外は原作再現版と同じ」「触った技・spm ページ以外は同じ」を `assert` する。キーを増やすときは `KEYS` も直す。
  5. on=False で前のパックの sha256 が再現することを確かめると安全（`制作記録 11/15 12:50` の BULLET_NOCANCEL）。

### 5.4 規則を直す・足す手順（チェックリスト）
1. **症状を原作と比べる**: ユーザーの動画・指摘から、どの技のどのフェーズかを特定（`waz_summary.py Tooru --json-dir work/tooru_port/view --skill N` でタイムラインを見る。`調査記録 09 §6`）。
2. **原作の処理を exe で確かめる**: BaldrForce.exe のどの関数がその値をどう使うか（アドレスを控える）。BFE データの値は named JSON で見る。
3. **DiveX の処理とバニラの実例を確かめる**: BaldrSky.exe の該当処理と、同じ挙動のバニラ技（甲が多い）の書き方。どちらかが欠けたら「推定」と明記する。
4. **規則として書く**: 技名ではなく BFE の値・フラグを条件にする。影響範囲が広すぎないか、同じ条件に当たる他の技を先に洗い出す。
5. **記録**: `rep.add('新タグ', …)`、`provenance.KIND_CAT` に分類、コメント（§4.2 の書式）、`work/tooru_port/制作記録` に 1 行（日時・タグ・ファイルと関数・パックの sha256）、notes に節、`制作記録` に 1 行。
6. **ビルド 2 回**（原作再現版と `--waz110`、改善版は同じビルドで出る）して sha256 が一致すること（決定的）。
7. **差分を確かめる**（§5.5）。意図した技以外が変わっていないか。
8. 実機確認を 制作記録 で依頼（動画は挙動を見たいときだけ、`制作記録`「撮影依頼のルール」）。

### 5.5 変更後に確かめること
* **build が自動で止めるもの**（通ればよい）: 12 ファイルの再パース一致、共通 waz のバニラ部分のバイト一致、spm 参照・WazaSelect の範囲、`mek_check`（違反 0）と `--full --spm`（バニラ基準外 0）、pac の展開一致、改善版の「変わってよいキー以外は同じ」（`build_phase3b.py` H・I・I2 節）。
* **全武装の前後差分**: 専用スクリプトはこの写しに無い。notes では「offset を除く JSON 比較」で前後を比べている（`調査記録 24`・`調査記録 25` の「影響」節）。やり方:
  * build は開始時に `work/tooru_port/check` を消して作り直す（build L85）。**変更前に `work/tooru_port/check/`（と `check_modified/`）を別名で写しておく**。
  * 前後の `check/waz/*.json` を `bfe2bsdx_common.norm()`（offset 等を除く）で技ごとに比べ、変わった技・ターン・スロットを表にする。`tools/waz_struct_diff.py a.json b.json --align name` はスロット単位の差を集計できる（本来は BHE 移植比較用。docstring）。
  * 改善版の前版は `work/behavior_mod_20261110/prev_modified_*` のように残している例がある（`制作記録 11/10 夜`）。
* **report.txt**（`work/tooru_port/report.txt`）: タグごとの件数と全メッセージ。新しいタグの件数が想定どおりか、既存タグの件数が意図せず増減していないかを見る。
* **出どころ表**（`調査記録 15`）: 武装ごとの R/E/V/T/X/M の件数と内訳。T（テンプレのまま）や X が増えていないか。§4.3 の落とし穴（未登録タグは R、ラインは V、build 後処理は出ない）に注意。
* **攻撃回数**: `python3 tools/attack_count_check.py [--dx DIR] [--out FILE]`（BFE のフェーズ遷移と DiveX の slot 71 を両方シミュレートしてヒット数・発射数を比べる。機体は「当たる」前提、弾は「当たらない」前提。`調査記録 25 §3`）。ループ・遷移・発射間隔を触ったら必ず回す。差が残る既知のもの（ワイヤーの先端、NODMG、上限 64 など）は `調査記録 25 §3` の表。
* **武装表**: `work/tooru_port/weapons_table.md`（状態: 変換 / 変換（推定あり）/ 近似）、`python tools/weapon_table.py`（威力・補正・属性・早期廃熱・EX キャンセル）。
* **目視**: `bfe2bsdx_render_skill.py`（技のスプライト列と判定・生成の時刻）、`bfe2bsdx_render_line.py`（ライン）、`bfe2bsdx_render.py`（spm ページ）。

---

## 6. コードを読むときの入口（この種の修正はこの関数）

ファイル名の `bfe2bsdx_` は省略。L は `bfe2bsdx_waz.py` の目安の行。
| 直したいこと | 見る場所 | 関係する主なタグ |
|---|---|---|
| 機体の横の動き・速度・慣性・向き | `waz.convert()` の `# ---- movement`（L828〜）、`_dir_event()`、`DASH_SPEED` | MOVE、INERTIA、SPEEDCUT、RESTRAMP、DIRECTION、SDKEEP（`_boiler()`） |
| 機体の縦（ジャンプ・落下・技後の上昇） | `bfe_vert_sim()`、`_vert_events()`、`_post_apex()`、`dx_rise()`、空中時の振り分け（L1888〜）、STOP ターン（L1944〜） | VERT、TOUCHCARRY、POSTAPEX、AIR、LANDTEST、VRATE、SLIP、STOP |
| ヒット判定の区間・ヒット数・間隔 | `convert()` の `# ---- hit`（L1303〜）、`_set_hit()`、spm の攻撃矩形は `spm.convert()` | HIT、HITDELAY、HITIV、HITREPEAT、NORECT、NODMG |
| のけぞり・吹き飛び・ダウン | `_set_noke()`、`bfe_launch()` / `bfe_launch_multi()`、`_set_hit()` 内のサブ 17/18 処理、NOKEPARENT/NOKECHAIN（`# ---- hit` 内） | NOKE、LAUNCH、NOKEDOWN、NOKEFLOAT、SLAMKEEP、MULTILAUNCH、NOKERANDDIR |
| 機体どうしの接触・めり込み | `# ---- body collision`（L1256〜）、`Fx.touch_off/touch_on` | TOUCH、BTOUCH、SINK |
| キャンセル（slot 47） | `convert()` の HITCANCEL ブロック（L1587〜）、`_boiler()` の slot 47、後処理の値 3 の分割（L1818〜）、`_set_hit()` の `selfStunFrame`、`Fx.hit_cancel()`。改善版の EX キャンセル区間は `modified_behavior.ex_cancel()`、弾ヒットでのキャンセル不可は `bullet_nocancel()` | HITCANCEL、EXCANCEL、BULLET_NOCANCEL |
| キャンセル時の慣性（slot 33） | `_boiler()` の SLIP（甲の値を (0,8,0,6,0,99999) に）。slot 33 は新しい技の開始・キャンセル操作のときだけ効き、自然終了では効かない（`_post_apex()` docstring） | SLIP |
| 弾の生成（いつ・何発・角度・位置） | `# ---- projectile`（L1444〜）、`_set_fire()`、`spawn()`、`bfe_fire_offsets()`、`Fx.tama_target()` | FIREIV、SWEEP、TWINMUZZLE、POSCORR、LOCKTARGET、SPAWNTYPE |
| 弾の速度・追尾・回転 | `# ---- movement` の弾の部分（BSPEED）、slot 15/16/17（L1030 付近 HOMING_*）、`Fx.tama_speed()` | BSPEED、BDECEL、HOMING_OFFSET、HOMING_EITHER、DIR16RESET、SPIN、ANGLESIGN |
| 弾の追従（体・拳・敵に付く） | movement の STICK 系（L930〜990）、STICKTARGET（L1545〜）、build G1b `_followcut()` | STICK、STICKALPHA、STICKHOLD、STICKZ、STICKTARGET、FOLLOWCUT |
| 弾の縦（放物線・着地・滞留） | `bfe_bullet_vert()`、`bfe_bullet_land()`、BHOLD 系（L1194〜1250）、`ev_len()` の着地まで（L502〜） | BVERT、BFALL、BHOLD、BHOLDANY、BDIVE、LANDHOLD |
| ライン（レーザー・ワイヤー） | `line.LineBuilder`: `build()`・`_parent()`（本数・伸び・引き戻し）・`_child()`（絵・拡大）・`_tip()`（先端、TIPDETACH/TIPTOUCH）・`_root()`・`_hits()`（ヒット数・間隔・窓）・`stops_at_hit()`/`_pierce_hdr()`（貫通） | LINE、PIERCE、LINEZOOM、LINEIV、LINEWIN、TPLHIT0、HITSCALE |
| 絵（パターンの長さ・拡大・合成・判定矩形） | `ev_timing()`、`ev_len()`、`patterns()`、`zoom_events()`、`SPRITE_ATTR`、`spm.convert()`／`blend_of()`、`eft.build_effect_spm()`／`upright_anims()` | ZOOMTYPE0、BLEND、FIREIV |
| エフェクト | `effect_spawn()`、`Fx.effect_target()`、`effmap`、ヒットエフェクトは `_set_hit()` のサブ 16 | EFFECT、EFFTARGET、HITFX0、MISSILEFX、BLINK |
| SE | `SeMap`、`se_obj()`、`_se_voice()`、build D 節 | SEVOICE、SE_NEW |
| 変化先・ループ・分岐 | `# ---- transitions`（L1643〜）、`Lib.change()` / `Lib.cond()`、LOOPPOS（L714〜） | AIR、LOOP、LOOPPOS、MECHDIST、DISTOUT、IGNORED |
| 威力（÷4）・最低値（×3/8）・コンボ補正 | `_set_hit()`（MINDMG・COMBOCLS・COMBOV3・SELFDECAY・REPDECAY）、`COMBO_CLASS`、`role_min()`、`combo_v3.py` | HIT、MINDMG、COMBO、COMBOCLS、COMBOV3、SELFDECAY、REPDECAY、ROLEMIN |
| 属性（燃焼・電撃） | `_element()`、`ELEM_BITS` | ELEMENT |
| 熱 | build E 節（`heatMin` / `heatMax`） | HEAT |
| FC の演出 | `_fc_at()`、`FCSLOTS` | FCPHASE、FCSTOP |
| 改善版だけの値・挙動 | `modified_tweaks.TWEAKS` → `balance.apply()` / `modified_behavior.apply()` | BALANCE、BEHAVIOR |
| ダッシュ・基本性能 | `basic.py`（`SPEEDS`・`apply_waz()`・`add_sd_extras()`） | BASIC |

---

## 7. 落とし穴・古くなった記述

* `bfe2bsdx_waz.py` 冒頭の docstring は全武装版の初期のまま。旧: 「吹き飛び規模 = launch*20」「威力 = BFE/4, 最低 = /4」→ 現: LAUNCH（40H/T・3200H/T²）、最低値 ×3/8（MINDMG）。docstring ではなく各規則のコメントを読む。
* `調査記録 15 §3` の規則表も一部古い。旧: 吹き飛び 2·L²（上限 150）、初撃コンボ補正 ÷10 → 現: LAUNCH の式、COMBOCLS（射撃・FC）/ COMBOV3（格闘・武器の通常技）。`調査記録 15` は「phase の最後にだけ更新」の決まり（`制作記録`）なので、現状はコードと `調査記録 38` 以降を見る。
* `調査記録 09 §3` の「速度 1:1」「ジャンプ 4·x0…」も旧規則（M 10-28 で /2、VERT で BFE の縦の軌跡）。
* 写しの `work/tooru_port/report.txt` は古い（BHOLDANY・STICKTARGET の節が無いが、出どころ表には有る）。work/ のレポートはビルドし直して見る。
* `KIND_CAT` に無いタグは R として数えられる（§4.3）。
* `Lib.conds` の条件の見本は「NOT（int2）付きを避けて肯定形を取る」ように直してある（甲の最初の「着地していたら」が否定形で、全部の着地条件が反転した事故。`Lib.__init__` のコメント、`調査記録 14 §W0`）。条件を新しく使うときは `neg` を明示する。
* 弾の変換は `Fx` のキャッシュ（`tcache` / `pcache` / `lcache`）で 1 度だけ。**最初に撃った技の文脈で変換される**（例: 打撃の弾を射撃技が先に撃つと、キャンセルフラグ 0 のまま。APPROX「were converted before」）。
* 共通 waz の追加位置（Tama04 109 以降など）は変換の順番で決まる。変換の順番や必要な弾の集合が変わると番号がずれる（参照は build が `assert` で検査）。
* `bfe_waz_fields.json` の標的ﾀｲﾌﾟの並びは 1 つずれている（`調査記録 60 §4`、未修正）。
* 1F 停止ターン（STOP、命中で終わる動く技）は変換器が足すターン。BFE の「命中で終了 → 自由落下」を DiveX で表すためのもの（`convert()` 後処理のコメント）。

---

## 8. 参照
* 方針: `制作記録`（大目的・変換の方針）、`制作記録 §2`（武装名で分岐しない、改善版は modified_tweaks に登録）、`調査記録 60` 冒頭（原作再現版のワークアラウンドの扱い）、`調査記録 40`（甲テンプレの残し方）。
* 仕組み: `調査記録 09`（全体・§3 規則・§8 弾・§10 ライン）、`調査記録 15`（出どころの分類）、`docs/formats/05_waz_field_dictionary.md`（DiveX のスロット）、`調査記録 07`（BFE exe）。
* 規則の実例: `調査記録 20`（HITCANCEL、全武装の前後表）、`調査記録 25`（LOOPPOS と `attack_count_check.py`）、`調査記録 30`（TOUCHCARRY・SDKEEP）、`調査記録 57`〜`61`（FIRELOCK・NOKECHAIN・BHOLDANY・STICKTARGET・FOLLOWCUT・TIPTOUCH・TIPDETACH）。
* 変更ログ: `work/tooru_port/制作記録`（1 行ずつ）、`制作記録`（末尾が最新）。
* 規則タグの一覧: `docs/porting/04_conversion_rules_catalog.md`。
