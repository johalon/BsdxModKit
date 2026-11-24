# 01. NeXAS_DX 調査報告：BSDX データ形式とツールチェーン

調査対象: `/path/to/ext/NeXAS_DX`（Karaik 氏の Java ツール。中身は読むだけで、触っていない）
作業コピー: `/path/to/workspace/work/nexas_dx`、ビルド成果物: `/path/to/workspace/tools/nexas_build`
日付: 2026-10-21

> 表記の約束: **【確認済】** はコードかデータで裏付けたもの、**【推測】** は仮説。インデックスはすべて 0 始まり。

---

## 0. 要約

* **ラウンドトリップ（parse → JSON → generate → バイト比較）は、spm 以外は全件一致した。**
  mek 105/105、waz 112/112、grp 8/8、dat 67/67、bin 166/166（`__GLOBAL.bin` は対象外）。spm は 1832/1989 で、不一致 157 件はすべて同じ一つの原因による（§2.4）。
* 機体を構成するもの:
  `MekaGroup.grp`（機体 ID）、`WazaGroup.grp`（waz ID）、`SpriteGroup.grp`（spm ID）、`<Name>.mek`、`<Name>.waz`、`<sprite>.spm`、png 画像（staging にない pac に入っている）、そして各種 dat 表（WeaponEquip / SelectMekaMenu など）。
* **ゲーム内で機体を指す ID は MekaGroup.grp のインデックス**である【確認済】。dat 表とスクリプト（bin の `LoadMek(21,…)` など）はこの番号を使う。
* **SpriteGroup.grp に空きスロットが 4 つある（133〜136、existFlag=0）**【確認済】。ここを使えば SpriteGroup の配列長（138）を変えずに新しい spm を登録できる。配列長を変えると ProgramMaterial.grp と全 mek の MaterialBlock を作り直すことになる。
* **登録されていない「孤児」機体が見つかった**【確認済】: Akao.mek（モリビト２号／柊 赤緒）、Akao.waz、Moribito.waz、Zako003a.mek。どれも grp に登録されておらず、MaterialBlock の次元が現行版と違う（Akao は 139/38/31、Zako003a は 136/38/17）。旧版か、未公開・DLC 系のデータと見られる【推測】。Akao は staging 済みのどの pac にも入っていない。
* **BHE→BSDX 移植（月読）は、元のコードのままでは spm しか書き出せない**（waz も mek も、生成したものが読めない）。本プロジェクトで JSON 経由のコピーとバグ修正を加えた結果、**BHE の機体 waz 94 件すべてと月読の mek が、BSDX 形式で生成→再パースまで通った**。残る大きな問題は索引の付け替えで、共通 waz/spm と SE ライブラリが BHE と BSDX でまったく違う（§4）。
* **BHE のデータは月読 1 機分なら揃っている**（mek、waz、spm、grp 登録、共通依存）。足りないのは png と音声だけ。png は普通の PNG で、BSDX も同じ形式を使っている【推測・高確度】。
* **既存機体を複製して新エントリを作る作業は、コンテナ内では一通りできた**。試作 `tools/harness/CloneMech.java` で Sora を Test01 として複製し、grp・mek・waz・spm・dat を生成した。全出力が再パースしてバイト一致する（§5）。ゲーム上の動作は未検証。

---

## 1. ビルドと round-trip テスト

### 1.1 Linux でビルドできなかった点と、その回避
| 問題 | 対処 |
|---|---|
| Maven Central への接続がプロキシで 403（repo.maven.apache.org を含め全ミラー不可） | Maven は使わず javac で直接ビルドした |
| lombok jar が手に入らない（@Data 302 箇所、@NoArgs/@AllArgs など） | 自作の `tools/delombok/DelombokLite.java` を使う。javac Tree API でソースを読み、getter/setter/ctor/log をテキストとして挿入する。lombok アノテーションはスタブ（`tools/delombok/stubs`）にした |
| hutool 5.8.16 がない | GitHub から hutool 5.8.17 のソースを取り、core と json だけをビルド（`tools/libs/hutool-core-json-5.8.17-src-build.jar`、JAXBUtil は除外） |
| jackson / slf4j | `/opt/gradle-8.14.3/lib` にあった jackson 2.16.1 と slf4j-api 1.7.36 を流用 |
| JavaFX（win classifier） | GUI のクラス（MainApplication、controller/*Controller、Workspace*、support/*）はコンパイル対象から外した |
| JUnit 5 がない | テストクラスと同じ処理をする CLI `tools/harness/RoundTrip.java` を書いた |
| ファイル名に非 ASCII（UTF-8）が含まれる | `LC_ALL=C.UTF-8` が必要。これがないと spm 7 件で InvalidPathException になる |

再現手順:
```
/path/to/workspace/tools/build_nexas_dx.sh          # 作業コピー作成 → delombok → javac
/path/to/workspace/tools/run_roundtrip.sh [OUT] [ext…]   # 既定の出力先 /path/to/workspace/work/nexas_rt（json/ gen/ summary.txt）
```
JSON 化には元のテストと同じ hutool `JSONUtil.toJsonStr` を、逆変換には Jackson `readValue` を使っている。

> 注: 作業中に `/path/to/workspace/work/` の下（自分で作った nexas_dx コピーと rt 出力）が何者かに削除された。別の作業の可能性がある。スクリプト化してあるので再現はできる。

### 1.2 結果（`/path/to/workspace/work/nexas_rt/summary.txt`）
| 形式 | 件数 | 一致 | 不一致 | parse 失敗 | 備考 |
|---|---:|---:|---:|---:|---|
| .mek | 105 | **105** | 0 | 0 | |
| .waz | 112 | **112** | 0 | 0 | waz ディレクトリは空ではない（112 件） |
| .spm | 1989 | **1832** (92.1%) | 157 | 0 | 不一致はすべて「末尾の未解析データが失われる」もの |
| .grp | 8 | **8** | 0 | 0 | |
| .dat | 67 | **67** | 0 | 0 | |
| .bin | 167 | **166** | 0 | 1 | `__GLOBAL.bin` は非対応（TODO クラス）。スキップ判定が `"__GLOBAL"` と小文字化前の名前で比べているため効いていない（小さなバグ） |

spm の不一致 157 件はすべて、**生成結果が元ファイルの先頭部分と完全に一致し、末尾だけが欠ける**パターンである。Spm DTO の `SPMTailData` は空クラスで、パーサは EOF を確かめずに処理を終える。JSON を介さず parse→generate しても同じ結果になるので（`tools/harness/Direct.java`）、delombok の副作用ではなく元のツール側の制約である。
不一致には機体スプライトも含まれる: sora.spm、isao.spm、Rain_past.spm、Tama.spm、Zako_002a、zako_018a/027a/101a/109a/127a/204a/207a/208a/208a2/215a。残りは UI（BQ*、RandomMap*、nq_*、TitleBar* など）。
→ **spm は tool で再生成せず、バイトコピーで扱うのが安全**。

**BHE（resources/game/bhe）の結果**（`BheRoundTrip`）: grp は parse・generate とも 8/8 一致。mek 95/95 と waz 103/103 は parse のみ成功（generator がない）。spm は parse 748/748、再生成の一致は 560/748（BHE の SpmGenerator が hit area を書かないため、戦闘スプライトは全件不一致）。詳しくは §4.3。

---

## 2. 各形式の構造

すべてリトルエンディアン。文字列は NUL 終端で、既定の文字コードは windows-31j（mek の英名とパイロットのローマ字だけ UTF-8 で読む）。

### 2.1 .mek（機体定義）
ヘッダは int×6（seq1..seq6）で、各ブロックの先頭オフセットを表す。seq1 は常に 24。**Generator はブロックをシリアライズした後でオフセットを計算し直す**ので、中身を自由に増減できる【確認済】。

| ブロック | 範囲 | 内容 | 理解度 |
|---|---|---|---|
| ① MekBasicInfo | seq1..seq2 | 文字列 5 個（機体名、英名[UTF-8]、パイロット名、ローマ字[UTF-8]、解説）+ int 22 個: **wazFileSequence**（=WazaGroup idx）、**spmFileSequence**（=SpriteGroup idx）、mekType（図鑑の分類フラグ）、healthRecovery、forceOnKill、baseHealth(/10)、FCゲージLv1/2、ブースターLv/増分、常時装甲、コンボ感想反映率、格闘/射撃/耐久/機動(0-5)、重量、歩行/ND/SD/BD 速度、浮遊高度 | ほぼ全フィールドに日本語の内部名（RTTI/エディタ文字列由来）と挙動メモがある |
| ② MekPairBlock | seq2..seq3 | (int,int)×14 固定 | 名前はなし。データを見ると **int2 = 基本動作スロット → waz の skill index**（例: Kou は 0,1,2,-1,-1,-1,3..10。waz の 0=立ち、1/2=歩行、3..=SD/BD…）、int1 は常に -1【推測】 |
| ③ WeaponInfo | seq3..seq4 | count、続いて各エントリ {flag=1、文字列 3 個（武装名、コード名、解説）、int 19 個: switchToMekNo、**wazSequence**（自機 waz 内の skill index）、FC 量、熱量（初期/最小）、必要経験値、デモ距離、カテゴリ(0 通常/1 FC/2 イニシャライザ)、攻撃タイプ(0 格闘/1 射撃)、タグ 8 種、フラグ(0/1 HC/2 非表示)、unknown19} | ほぼ判明。unknown19 だけ不明（攻撃Lv？） |
| ④ AI | seq4..seq5 | count × {日本語名、英名、eventCount、各 event: short type（1=CCpuEventMove、2=CCpuEventAttack）+ 型ごとのフィールド} | フィールド名は RTTI 由来の 25 項目（発動確率、範囲 Min/Max など）。詳しい意味は BALDRSKYDIVEX_DAT/MEK_AI を参照 |
| ⑤ VoiceInfo | seq5..seq6 | **version**（実際は **BatVoice.grp の index**【推測・ほぼ確実】: Kou=0、Rain=1、Sora=6、Noi=15、ザコ=-1）、emotions[name,token]、voiceSlots[name,token]、table[(builtin13+emotions) 行 × slots 列]、各セルは (voiceType, groupId, weight) の三つ組の列 | 構造は判明。DTO 側の名前「version」は誤り。builtin 行数（13）は BatVoice の種別数 13 と一致 |
| ⑥ MaterialBlock | seq6..EOF | CMaterial 7 個 → int extra → CMaterial extra 個 → EOF まで CMaterial。各 CMaterial は 3 段の list-of-list(u32): **spriteGroups[SpriteGroup 数=138]、seGroups[SeGroup 数=38]、voiceGroups[BatVoice 数=30]** | 判明（IDA: reader `sub_657800`、`CMaterial::readArraysFromFile`、"AddSprite/AddSe/AddVoice"）。前の 7+extra 個は通常状態用。残りは武装ごとに 1 個か 3 個ずつ割り当てられる（フラグ次第）。**各段のインデックスは grp の番号そのもの**【確認済】。例: Kou のエントリでは spriteGroups[9]=kou.spm 内の ID、[3]/[4]=Smoke/Mark、seGroups[0]=REACTION、voiceGroups[0]=甲。プリロード表と見られる【推測】 |

> 重要: MaterialBlock の配列長は SpriteGroup/SeGroup/BatVoice の**登録数に直結している**。grp を末尾に伸ばすと、全 mek（2124 エントリ）と ProgramMaterial.grp の長さを合わせる必要が出てくる可能性がある（エンジンが境界チェックをしているかは未確認）。

### 2.2 .waz（技・行動定義）
```
繰り返し: int flag(0=空スロット)
  Skill { 文字列 jp, 文字列 en, int phaseQuantity,
          Phase[phaseQuantity] { 72 個の SkillUnit:
              int n1, CEvent×n1（スロット i ごとに型が固定、SKILL_INFO_TYPE_ENTRIES_BSDX[72]）
              int n2, SkillInfoUnknown×n2 {start,end,int×3} },
          int nSuffix, (int,int)×nSuffix }
```
* 72 スロットには名前がある（ｽﾌﾟﾗｲﾄ、位置、ﾍﾞｸﾄﾙ、攻撃：メカ、ＳＥ、ボイス、画面演出…、変更処理）。CEvent の具象クラスは 36 種（CEventHit、CEventMove、CEventSprite…）。どれも EXE の RTTI からそのまま起こしたもので、**読み書きは完全**（112/112 一致）。数値の意味はクラスによってまちまち。
* **WazaGroup の param は、その waz の skill 数**【確認済】。
* 他ファイルへの参照:
  * `CEventSprite {spmFileSequence(-1=自機 spm、または自機の SpriteGroup idx を明示), actionGroupNumber, actionNumber}`。たとえば Kou は 441 件で 9（=kou.spm）を明示している。
  * `CEventWazaSelect {wazFileNo(=WazaGroup idx: 0 Effect、1-5 Tama01-05、6 Laser、7 Bomb), wazSequenceNo}`。弾や爆風の生成に使う。
  * `CEventSe`（16 バイト不透明×n）、`CEventVoice`（int×3 + 12 バイト不透明×n）。**SE とボイスの参照先 ID は未解析のまま**【推測: SeGroup idx/item idx/確率】。
* waz ファイル名は WazaGroup の `wazaDisplayName` + ".waz"。

### 2.3 .grp（静的レジストリ。ゲーム起動前に読み込まれる）
| ファイル | 構造 | 中身 | 件数 |
|---|---|---|---|
| **MekaGroup.grp** | n × {flag, name, CODE} | 機体 ID → `<name>.mek`。0 Kou、1 Masa … 26 Muramasa、27 以降はザコ | 103（空きなし） |
| **WazaGroup.grp** | n × {flag, 日本語名, CODE, fileName, param(=skill数)} | 0 Effect、1-5 Tama01-05、6 Laser、7 Bomb、8 MapObj、9 Kou … 33 Muramasa、34 以降はザコ | 110（空きなし） |
| **SpriteGroup.grp** | n × {flag, spmファイル名, CODE, param} | 0-8 共通エフェクト（Tama/bomb/Elec/Smoke/Mark/Pic/Link/Fire/Wind）、9-108 機体 spm、109-132 マップ OBJ、**133-136 空き**、137 ComboWeaponInfo.spm(param=1) | 138 |
| **SeGroup.grp** | n × {flag, 種別, CODE, m × {flag, 名前, CODE, ファイル名}} | SE カテゴリ（REACTION、AIRPLANE …、36 PROGRAM、37 UDAGAWA）。11 番は空き | 38 |
| **BatVoice.grp** | 種別 13 × {名前, CODE} + n × {flag, キャラ名, CODE, m × {flag, 台詞, CODE, ファイル名}} | 戦闘ボイス。0 甲 … 19 村正、20-29 ナビ | 30（空きなし） |
| **ProgramMaterial.grp** | list-of-list ×3（138/38/30） | エンジン共通のプリロード表（MaterialBlock と同じ次元）【推測】 | — |
| **Term.grp** | グループ × {名前, CODE, 項目 × {名前, CODE, 解説, p1, p2}} | waz/AI エディタの条件語彙（エディタ用の定義表） | — |
| **MapGroup.grp** | マップ定義（文字列 3 個、int、item×4int、list-of-list×3） | 戦闘マップ | — |

EXE 内に `Dat\MekaGroup.grp`、`Script\Battle\MekaGroup.h`、`SAVE ERROR : CMekaGroupManager` などの文字列があり、開発版のエディタ機能が残っている。

### 2.4 .spm（スプライト・アニメ・当たり判定）
`"SPM VER-2.00"` → pages[n]{chip 数, w, h, rect, option, 回転中心, hitFlag(32bit), hitRects[ビット数]{unk0 種別, rect, unk1, unk2}, chips[n]{imageNo, dst, w, h, src, drawOption, value, option}} → images[n]{png 名} → patPageNum → anims[n]{名前("立ち\r"…), numPat, 回転/反転, pats{wait, pageNo[patPageNum]}}。
* BSDX の 1989 件はすべて VER-2.00（2.02 は BHE 用）。
* **末尾に未解析ブロックがあるファイルが 157 件**。例: BQBackup の末尾 50 バイト = `01 00 00 00 02 00 00 00 00 01 …`。何のデータかは不明。
* hitRect の unk0 は分類（2 が 94%、7 は厚み付きで unk1/unk2 を持つ）。README の推測を参照。
* **画像（png）は spm に入っておらず、ファイル名で参照される**。例: kou.spm は images 222 枚（`kou_000_0001.png` …）、pages 16333、anims 559。Zako_002a は `Zako_002a0001.png` など 8 枚。

### 2.5 .dat（CSV 相当の表）
`int 列数` → `int 型[列数]`（0=int、1=string、2=IntNew、3=byte）→ EOF まで行が続く。読み書きは完全。機体に関係する表:

| dat | 形 | 意味（【推測】を含む） |
|---|---|---|
| **WeaponEquip** | 103 行×14 | **MekaGroup と 1:1**。初期装備スロット 14 個（自機の武装 index、-1 は空） |
| **BQMekaMemory** | 103 行×1 | MekaGroup と 1:1（BaldrQuest 用の数値） |
| **SelectMekaMenu** | 99 行×3 | [MekaGroup idx、SelectMekaMenuMeka.spm の anim idx、?(85-114 または -1)]。Sora2/Neunzehn2/Chris2/Zako208a2 以外の全機体 |
| **Meka** | 99 行×2 | [MekaGroup idx、値(100,300…)]。SelectMekaMenu と同じ ID 集合で、並びは別 |
| **TournamentMekaData** | 99 行×6 | トーナメント用パラメータ |
| **MekaPilot** | 70 行×1 | MekaGroup idx の並び。MekaPilot.spm の anim 70 個と対応 |
| **Weapon** | 152 行×4 | 甲（Kou、武装 153 個）の武装成長表【推測】 |
| SurvivalMekaMain/Rare/Zako | 24/34/86 行 | サバイバルモードの出現機体 |
| Char、PersonalData、Stand、StandPos | — | ADV 用。戦闘とは無関係 |

### 2.6 .bin（NeXAS スクリプトのバイトコード）
preCount + pre(8B×n) → 命令 (opcode, operand)×n → 文字列表 → properties → properties2 → 定数表/68B 表 → tailRaw。CALL の operand は上位 16bit が引数数、下位 16bit が native ID（名前の一部は判明: SetMessage、LoadMek、InitDeployMek、MidDeployMek …）。166 件のうち 68 件に tailRaw（未解析部分。そのまま書き戻すので往復は可能）がある。
戦闘の初期化例: `LoadMek(21 /*Noi=MekaGroup idx*/, 127, 1, -1, -1)`、`InitDeployMek(陣営?, …, x, y, z, 角度)`。スクリプトも機体を MekaGroup idx で指している【確認済】。
ここにある bin は外伝・Hell・Tutorial・モード系（Survival/Tournament/System など）だけで、本編シナリオは含まれない。

---

## 3. ファイル間の参照と、リソースの出どころ

```
スクリプト(bin) / dat ──MekaGroup idx──▶ MekaGroup.grp ──name──▶ <Name>.mek
<Name>.mek  ─wazFileSequence─▶ WazaGroup.grp ─fileName─▶ <Name>.waz
            ─spmFileSequence─▶ SpriteGroup.grp ─file─▶ <sprite>.spm ─imageName─▶ *.png（未入手の pac）
            ─VoiceInfo.version─▶ BatVoice.grp（idx）─▶ ボイス ogg（Voice.pac?）
            ─MaterialBlock[sprite|se|voice][grp idx]─▶ 各 grp 内の ID リスト
            ─Weapon.wazSequence─▶ 自機 waz の skill idx
<Name>.waz  ─CEventSprite.spmFileSequence(-1/自 idx)─▶ SpriteGroup
            ─CEventWazaSelect.wazFileNo─▶ WazaGroup（Effect/Tama/Laser/Bomb）
            ─CEventSe / CEventVoice（不透明 blob）─▶ SeGroup / BatVoice
UI: SelectMekaMenu.dat ─anim idx─▶ SelectMekaMenuMeka.spm（98 anim）
    MekaPilot.dat ─▶ MekaPilot.spm（70 anim）
    C_<sprite名>.spm（101 件、カットイン? 例 c_kou_0001.png）… sprite ファイル名に "C_" を付けた名前（Sora2 以外はすべて存在）
    G_<pilotRoma>.spm / M_<…>.spm（各 22 件、操作できるキャラ向け）、MEKA_*_0101NO.spm（ADV の立ち絵用）
```

### 3.1 bsdx リソースの出どころ（MD5 照合。別の作業が `/path/to/workspace/work/extracted` に展開したものと比べた）
| 種別 | Dat.pac | Update.pac | Config.pac | Script.pac | Update2.pac | staging にない |
|---|---|---|---|---|---|---|
| mek 105 | 9（+Dat=Update 同一 29） | 66 | | | | **Akao.mek** |
| waz 112 | 84 | 26 | | | | **Akao.waz, Moribito.waz** |
| grp 8 | 7 | 1（MapGroup） | | | | |
| dat 67 | | 14 | 52 | | 1（System.dat） | |
| bin 167 | | 107 | | 60 | | |
| spm 1989 | | 11（sora.spm、TitleBar* など） | | | | **1978** |

→ NeXAS_DX の bsdx データは「Update.pac が Dat.pac を上書きした最新版」で揃っている。
→ **spm 1978 件と、spm が参照する png はすべて staging にない pac に入っている**。EXE の pac 名リスト（offset 0x41763C 付近）は `Voice, Stand, Face, Thumbnail, System, Script, Visual, Movie, Config, PlugIn01..PlugIn08`。機体 spm と png は **System.pac にある可能性が高い**【推測】。確認には System.pac（632MB）の**インデックス（ファイル名一覧）だけ**があれば足り、中身は要らない。
→ `PlugIn01..08.pac` を読み込む仕組みがあるらしい【推測】。差分 pac を追加する正規の手段として使えるかもしれない（要 EXE 解析）。

---

## 4. BHE→BSDX 移植実験（Tsukuyomi pipeline）の詳細と、移植の土台としての評価

> Stage 1（BHE の機体を BSDX のプレイヤー機として動かす）の土台になる部分なので、実際に動かして検証した。
> 使ったツール: `tools/harness/BheRoundTrip.java`、`RunTsukuyomiPipeline.java`、`JsonTransWaz.java`。出力は `/path/to/workspace/work/bhe_rt/` と `/path/to/workspace/work/bhe2bsdx_out/`。

### 4.1 元のパイプラインが何をしているか（`TransferTest#testPipeline` → `steps/TransMeka.process`）
1. BSDX と BHE の grp/mek/waz/spm を全部パースして Map に入れる（パスは Windows 前提の `D:\A\NeXAS_DX`）
2. 月読（tsukuyomi）の mek、waz、spm（本体と c_/s_/g_/m_）、BatVoice[1] を取り出す
3. `transBatVoice`: hutool BeanUtil で浅いコピーをし、bsdx の BatVoice の末尾（idx 30）に追加。中身の要素は BHE のクラスのままなので、BSDX の GrpGenerator に通すと失敗する
4. `transMeka`: BeanUtil でコピーし、voice version（=BatVoice idx）を 30 にする（3 で追加した位置）。それ以外の索引は直さない
5. `transWaza`: 83→72 のスロット対応表を使い、事件ごとに BeanUtil でコピーし、手書きの mapper 10 種（Hit/Effect/Height/Escape/Charge/CpuButton/RadialLine/ScreenLine/Status/Blink）を当てる
6. `transSprite`: spm を階層ごとに組み直す。hitbox は `transHitbox()` で BSDX の矩形と種別（shapeType 0→1、1→2、10→7）に写す
7. **ここで終わる**。生成、書き出し、grp 登録、メニュー用 spm の更新、pac 化は何もしていない

### 4.2 実際に BSDX 形式で書き出した結果（月読）
| 段階 | 元のパイプライン | 修正後（本プロジェクト） |
|---|---|---|
| spm（tsukuyomi.spm、c_tsukuyomi.spm） | **OK**: 生成でき、BSDX パーサで再パースも通る（207776→198576 B。hitbox を BSDX 形式に変換） | 同じ |
| waz | **NG**: CEventHit の startFrame が null で NPE。それを直しても、入れ子の `List<BheInfoCollection>` が BeanUtil で消え、書き出したものが読めない | **OK**: `JsonTransWaz`（JSON 経由でコピーし、キー名と入れ子 typeId を付け替える）と、build 時のパッチ（下記）。**BHE の機体 waz 94 件すべてが、生成→再パース→再生成でバイト一致した** |
| mek | **NG**: AI の CCpuEventMove/Attack が BeanUtil で基底クラスに化け、書いたものが読めない | **OK**（`-DfixAi=true`: AI を JSON で型ごとに写し直す）。ただし、下の 4.4 で挙げる索引の書き換えはまだしていない |
| grp / pac / dat | 手つかず | 手つかず（§5 の CloneMech で使った登録処理を流用できる） |

build 時に当てるパッチ（`tools/build_nexas_dx.sh` の PROJECT PATCHES と `tools/patches/`）。上流の ext は触っていない:
* `ProjJsonCopy.copy()`: 手書き mapper 9 種の中にある `BeanUtil.copyProperties` を JSON コピーに置き換える（入れ子の InfoCollection と、入れ子 SkillInfoObject の typeId を付け替える）
* `slotIndex()`: mapper 6 種（Charge/Escape/Height/RadialLine/ScreenLine/Status）が BHE の unit を**位置で**取っていたバグを直し、`unitSlotNum` で引くようにした。BHE のリーダは存在する unit しかリストに入れないので、位置で取ると型がずれる
* CEventHit で start/endFrame が写されていなかった点と、CEventEffect の FreeParam→CEventVal で frame と値が null になる点
* 上の修正をした後も BSDX 自身の round-trip は 105/105、112/112 のままで、退行はない

### 4.3 形式ごとの変換可否
| 形式 | BHE 側のツール | BHE→BSDX の変換 | 失われる、または対応先がないもの |
|---|---|---|---|
| grp | parse・generate とも 8/8 一致 | 構造は同じ（ProgramMaterial だけ BHE に header と pair 配列がある） | **登録内容がまるで違う**: MekaGroup 164（空き多数）、WazaGroup 171、SpriteGroup 208、SeGroup 55、BatVoice 43。**SE カテゴリは CODE が一致するものがほぼない**（BSDX と共通は 1 件だけで、W_BULLET/W_SLASH/METAL/T_ENERGY などは BHE にしかない） |
| mek | parse のみ（95/95）。generator はない | BSDX の MekGenerator で書ける | 武装ごとの `bheInt1..7`（日本語名不明。月読はすべて -1/0）と **Fei リスト**（feiFlag + int×7×n。月読は 0 件）。MaterialBlock の次元（208/55/43 と 138/38/30）が合わない。wazFileSequence と spmFileSequence が BHE の番号のまま |
| waz | parse のみ（103/103）。generator はない | 72 スロットに写せる（JsonTransWaz） | **対応先のない BHE スロット**: 23 速度XYZ、35 標的、38 技ツールパラメータ、40 ハイパーアーマー、43 死亡(自爆)、**52 CPU特殊行動**（月読 17、katou 16、motoki 13 など 13 機体）、62 属性、66〜69 マルチロック（sou だけ）。BHE にしかないクラス: CEventFreeParam（→CEventVal で近似）、CEventMultiLock*、CEventWazaToolParam、CEventAttr。sou には入れ子の FreeParam（type 15）もある。構造が違うクラス（Hit +フィールド、Blink +9 フィールド、Touch +short、Effect の slot28「標的」）は mapper で近似している。**CEventSe と CEventVoice の中身（不透明 blob）はそのままコピーするので、BHE の SeGroup/BatVoice 番号のまま残る** |
| spm | parse 748/748。**generator は hit area を書かない**（`writeHitArea` が空実装）ので、BHE→BHE の再生成は 560/748 しか一致せず、**戦闘スプライトは全滅**（0x3D でずれる） | BSDX 形式には変換できる（hitbox は shapeType 0/1/10 を rect と unk0 に写す。README によると 96.8% 一致） | 回転、円、球などの形状情報（BSDX 側に入れる場所がない）、厚み（unk1/unk2 には概算を入れる）。BSDX の spm 末尾ブロックは BHE にはない |
| dat / bin | BheBinService では未登録 | — | BHE dat 47、bin 139 は未調査 |

### 4.4 月読を BSDX のプレイヤー機にするために必要な索引の付け替え（未実装・設計）
1. **SpriteGroup**: 自機 13→BSDX の新スロット。共通スプライト（BHE: 0 Tama, 1 bomb, 3 Smoke, 4 Mark, 5 Pic, 7 Link, 9 Wind）は**同名でも中身が別物**（例: BHE Tama.spm 279085B、BSDX Tama.spm 177672B）。アニメ番号もずれるので、**BHE 版の共通 spm も別の SpriteGroup として持ち込む必要がある**。BHE にしかない MekaEffect.spm（月読の png にも mekaeffect*.png が入っている）、Ice.spm も同様
2. **WazaGroup**: 自機 11→新番号。月読は共通 waz を参照している: Effect 17 skill、Tama05 5、Tama03 1（Kou は Effect/Tama01/02/04/05/Laser）。共通 waz 自体の中身が別物で（Effect は BHE 291 skill、BSDX 146 skill で、同じ位置に同じ名前が来るのは 30 件だけ）、**参照されている skill を推移的に辿って抜き出し、新しい waz（例: `Tsukuyomi_Ext.waz`）にまとめて登録し、参照を張り替える**仕組みが必要
3. **SeGroup / CEventSe**: BHE の SE ライブラリは BSDX と互換性がない。BHE の SE ファイル（Se.pac 相当）を取り込んで SeGroup にカテゴリを追加するか、似た BSDX の SE に置き換える対応表を作る。どちらにしても、16 バイト blob の意味を解析する必要がある
4. **BatVoice**: 月読のボイス群（64 本）を追加する（idx 30）。CEventVoice の 12B blob と MekVoiceInfo の参照を合わせる。ボイスの ogg も必要
5. **MaterialBlock**: 208/55/43 を 138(+α)/38(+α)/30(+1) に作り直す（上の 1〜4 の対応表から自動で生成できる）
6. **grp の配列長が伸びる問題**: 共通スプライトを持ち込むと、空きスロット 4 つ（133〜136）では足りない。**grp を末尾に伸ばしてもエンジンが受け付けるか**（全 mek の MaterialBlock を伸ばす必要があるか）が最優先の未確認事項になる
7. 画面と dat: §5.2 の #7〜#10 と同じ（WeaponEquip、SelectMekaMenu、C_/G_/M_ spm など。BHE 側には c_/g_/m_/s_tsukuyomi.spm がある）

### 4.5 BHE リソースは揃っているか（月読）
| 要素 | 状況 |
|---|---|
| tsukuyomi.mek（18 武装、AI 2 種、Material 27 エントリ、Fei なし） | あり |
| tsukuyomi.waz（31 skill） | あり |
| spm: tsukuyomi / c_ / g_ / m_ / s_ と、tsuku_*（ADV 用） | あり |
| grp への登録: MekaGroup[2]、WazaGroup[11]、SpriteGroup[13]、BatVoice[1] | あり |
| 共通の依存: Effect/Tama03/Tama05 waz、Tama/bomb/Smoke/Mark/Pic/Link/Wind/MekaEffect spm | あり（resources/game/bhe に含まれる） |
| **png 画像**（tsukuyomi.spm は 22 枚: tsukuyomi_0xx_0001.png と mekaeffect0xx_0001.png） | **なし**。BHE の pac から取り出す必要がある（ユーザー PC の <BHE>） |
| SE / ボイスの音声ファイル | なし |
| BHE の dat（武装表やメニュー相当） | dat 47 件はあるが未解析 |

→ **データ構造の面では、月読 1 機分は揃っている**。足りないのは画像と音声だけ。
→ **テクスチャの形式**: BHE の spm も VER-2.00 で、画像は `.png` のファイル名で参照している。BSDX 側の Update.pac にある png（5 件）は**ヘッダ `89 50 4E 47` の普通の PNG**だった（ヘッダとサイズだけ確認し、画像は見ていない）。BHE も同じ NeXAS の pac なので、取り出せば普通の PNG になり、BSDX でそのまま読めるはず【推測・高確度】。画像の寸法やチップ座標は spm 側に入っているので、png は名前を変えずに同梱すればよい。

### 4.6 汎用「外部機体インポート」パイプラインの設計案（Stage 2 の BALDR FORCE EXE も想定）
```
[外部ゲーム → 中間表現]  BHE: NeXAS_DX の bhe パーサ / BFE: 未知（要調査）
        ↓  依存の推移閉包を作る（自機 waz → 共通 waz の skill → spm/anim → png、SE、Voice）
[BSDX 側の割り当て]  MekaGroup/WazaGroup/SpriteGroup/SeGroup/BatVoice に追加（できれば空きスロットを優先）
        ↓  索引の付け替え表（old idx → new idx）を全参照に適用（mek basic/Material、waz Sprite/WazaSelect/Se/Voice）
[生成と検証]  BSDX generator → 再パースして一致確認 → dat 表（WeaponEquip/SelectMekaMenu…）→ pac 化
```
今あるもの: 外部側パーサ（BHE）、JsonTransWaz、CloneMech（登録と dat）。ないもの: 依存閉包の抽出、SE/Voice blob の解読、grp 拡張の可否、pac 化。

---

## 5. 判定: 既存機体を複製して新機体を追加できるか

**結論: データ形式の面では十分にできる**（mek/waz/grp/dat は完全に往復でき、spm はバイトコピーで済む）。足りないのは (a) ゲームへの組み込み（pac 化／上書き読み込み）、(b) 画像 png、(c) EXE 側の上限やハードコード、という実機側の未知数である。

### 5.1 試作の実行結果（`tools/harness/CloneMech.java`、出力 `/path/to/workspace/work/clone_test/`）
`CloneMech <game/bsdx> <out> Sora Test01` を実行した:
```
src=Sora mekId=9 waz=26(Sora.waz) spm=24(sora.spm)
new=Test01 mekId=103 waz=110 spmSlot=133(test01.spm)
material entries remapped: 24/26
waz remap: CEventSprite=14 CEventWazaSelect(self)=0
selfcheck OK ×8（grp3, mek, waz, dat3）
```

### 5.2 必要な編集の一覧（新 ID: mek=103、waz=110、sprite=133 の場合）
| # | 対象 | 編集 | 状態 |
|---|---|---|---|
| 1 | MekaGroup.grp | 末尾に {1,"Test01","TEST01"} を追加 → ID 103 | 自動化済 |
| 2 | WazaGroup.grp | 末尾に {1,名前,CODE,"Test01",skill数} を追加 → 110 | 自動化済 |
| 3 | SpriteGroup.grp | 空きスロット 133 を {1,"test01.spm",CODE,0} に書き換え（配列長は変えない） | 自動化済 |
| 4 | Test01.mek | wazFileSequence=110、spmFileSequence=133、名前変更、**MaterialBlock の spriteGroups[24]→[133] へ移動** | 自動化済 |
| 5 | Test01.waz | CEventSprite.spmFileSequence 24→133（-1 はそのまま）、WazaSelect の自己参照があれば付け替え | 自動化済 |
| 6 | test01.spm | sora.spm をバイトコピー（png 名はそのまま。最初は元機体の画像を共有させる） | 自動化済 |
| 7 | WeaponEquip.dat / BQMekaMemory.dat | 103 行目に元機体の行をコピー（MekaGroup と 1:1 なので**必須**と見る） | 自動化済 |
| 8 | SelectMekaMenu.dat | [103, 元機体の anim idx, -1] を追加（SelectMekaMenuMeka のアイコンを流用） | 自動化済（第 3 列の意味は推測） |
| 9 | Meka.dat / TournamentMekaData.dat | 99 行の表。SelectMekaMenu と同じ ID 集合なので行を足す必要がある可能性が高い | **未実装** |
| 10 | MekaPilot.dat/.spm、SelectMekaMenuMeka.spm、C_test01.spm | 専用のアイコンやカットインを作るなら anim/page/png を追加（C_ は sprite 名から引いている可能性あり → `C_test01.spm` をコピー） | 未実装 |
| 11 | BatVoice | 既存の index を使い回す（Sora=6）か、-1（無音）にする。追加すると全 mek の voiceGroups 長が変わる | 流用で回避 |
| 12 | pac 化 | `Update.pac` の差し替えか、`PlugInNN.pac` を追加。NexasPack.exe（Windows）か、別の作業の tools/nexaspac.py を使う | 未着手 |
| 13 | **プレイヤー機として使うには** | 本編の自機は Kou（ID 0）に固定されている。自由選択モード（SelectMekaMenu 経由の対戦/トーナメント/サバイバル）で選べるようにするか、スクリプト（bin）の `LoadMek(0,…)` を書き換える | 要調査 |

### 5.3 未解決の論点（優先度順）
1. **EXE の上限**: MekaGroup 104 件、WazaGroup 111 件で配列があふれないか。セーブデータ（BQMekaMemory など機体ごとの記録）との互換性はどうか。
2. **grp の空きスロット（SpriteGroup 133〜136）**は安全に使えるか。末尾に追加した場合、MaterialBlock や ProgramMaterial の長さの違い（138 と 139）をエンジンが許すか（Akao が 139 であることが参考になる）。
3. **CEventSe/CEventVoice の不透明 blob の意味**（SE やボイスを独自に差し替えたくなったら必要になる）。
4. **spm の末尾ブロックの意味**（spm を新しく作る、または編集するなら必要になる）。
5. **png の置き場所と形式**: System.pac のインデックス（ファイル名一覧）が欲しい。必要なのは名前だけ。
6. SelectMekaMenu の第 3 列、Meka.dat の第 2 列、MekPairBlock の int1、Weapon の unknown19 の意味。
7. Akao（モリビト２号）の由来。DLC/PlugIn 用データなら、「未登録機体を有効化する」という既存の手順がどこかにあるかもしれない。

---

## 付録 A. mek ファイル一覧（105 件。※が grp 未登録）
Akao※(モリビト２号) Aki(シルファ) Chinatsu1(カゲロウ・凛) Chinatsu2(クリムゾンロータス) Chris/Chris2(グリムバフォメット) Eizi(ニーズヘッグ) Gilberto(ノーブルヴァーチュ) Gregory(バプティゼイン) Isao(タイラントギガース) Kou(カゲロウ) Makoto(ネージュ・エール) Masa(カゲロウ・鎧) Mohawk(メギンギョルド) Muramasa(村正) Nanoha(ニランナー) Naoki(震機狼) Neunzehn(ノインツェーン) Neunzehn2(偽ノインツェーン) Noi(イムくん) Rain(アイギスガード) Rain_Past(アイギス) Sidsel(フレスベルグ) Sizuka(和泉しずか) Sora/Sora2(カゲロウ・冴) Tranquilizer Yukie(黛由紀江)
Zako001a メッサー, 001b ヴァイパー, 002a エグゼター, 002b エクエス, 003a※ ファウスト, 003b クロノス, 003c シルファ, 004a サークリス, 005a シュレイク・テトラ, 009a/b/c ピドー/コマンダー/キャノン, 010a ストレイガ, 011a/b/c α・ダイン/β・ダイン/シャドーラン, 012a/b タルタル/キャノン, 014a ディアマンテ, 015a/b ハノマーグ/Ⅱ, 017a/b ヤクト/ラピッド・ヴァイス, 018a フィーア・グスタフ, 020a ゲド, 021a/b アイランナー/M, 022a モラモラ, 023a/b バグ/ガード・バグ, 024a スコーピオン, 026a メタルカーゴ, 027a スプレイダー, 028a 晴嵐, 029a 颪, 030a ノスリ, 031a シーアネモネ, 101a コパー, 102a クラウン, 103a カーレント, 104a ブル, 105a オールター, 106a ナーシサス, 107a ルース, 108a スナイパー, 109a タッドポール, 111a〜113a アイアンシックル/ハマー/ファイル, 114a センテンス, 116a アドヴェント, 117a シャドーゲイル, 118a アイアンローラー, 119a アイアンギムレット, 120a アイアンシェル, 122a トレス, 124a ブラックルース, 126a ケルビム, 127a ミラージュ, 128a/b 鉄/鋼, 201a アイビーム, 202a ゴールドシザー, 203a アーチャン, 204a シャドーギグ, 205a 風魔, 206a アイゼン＝ヴォルフ, 207a イール, 208a/208a2 ハーミット/（殻）, 209a ヴォーゲル, 210a サイクロプス, 211a フェニックス, 212a アイロニー, 213a クワトロ, 214a ドス, 215a フドゥルー・ホルス

詳しい表（waz#/spm#/type/HP/武装数/AI 数/Material 数）: `python3 /path/to/workspace/tools/py/mek_summary.py /path/to/workspace/work/nexas_rt/json/mek`
主人公機 Kou は武装 153、Material 391（7+3 通常 + 381）と突出している。他の自機系は武装 15〜29、ザコは 2〜15。

## 付録 B. その他の件数
* spm 1989 件: 機体本体 100 件前後、C_ 101、G_ 22、M_ 22、MEKA_* 34、KOU_* などの ADV 立ち絵用、UI（BQ*/RandomMap*/nq_*/Title*）
* waz 112 件 = WazaGroup 110 件 + 未登録（Akao、Moribito）。Akao.waz と Moribito.waz は同じサイズ（211461B）だが内容は別、どちらも 33 skill
* dat 67 件（機体関連は §2.5）。bin 167 件（外伝 26、Hell 約 95、Tutorial 23、モード系）

## 付録 C. 作成したツール
| パス | 用途 |
|---|---|
| `/path/to/workspace/tools/build_nexas_dx.sh` | Linux 用のビルド（delombok + javac、GUI は除外） |
| `/path/to/workspace/tools/run_roundtrip.sh` | round-trip を全形式で実行し、JSON も出力する |
| `/path/to/workspace/tools/delombok/` | DelombokLite と lombok スタブ |
| `/path/to/workspace/tools/libs/hutool-core-json-5.8.17-src-build.jar` | hutool をソースからビルドしたもの |
| `/path/to/workspace/tools/harness/RoundTrip.java`, `Direct.java` | テストハーネス |
| `/path/to/workspace/tools/harness/CloneMech.java` | 機体複製の試作 |
| `/path/to/workspace/tools/harness/BheRoundTrip.java` | BHE の全件パース。spm/grp は再生成して比較 |
| `/path/to/workspace/tools/harness/RunTsukuyomiPipeline.java` | 元の TransMeka を実行し、BSDX 形式で書き出して検証（`-DfixAi=true`） |
| `/path/to/workspace/tools/harness/JsonTransWaz.java` | BHE waz→BSDX waz 変換の試作（JSON 経由、スロット対応表、対応先なしの報告、事件ごとの整合検査） |
| `/path/to/workspace/tools/patches/` + build スクリプトの PROJECT PATCHES | 上流の BHE→BSDX mapper のバグ修正（ext には手を入れていない） |
| `/path/to/workspace/tools/py/mek_summary.py`, `grp_dump.py`, `dat_summary.py` | JSON の要約 |
