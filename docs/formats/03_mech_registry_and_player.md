# 03 機体レジストリとプレイヤー機体の決定ロジック (BALDR SKY DiveX)

調査日: 2026-10-21 / 担当: mech registry & player selection
信頼度表記: **[確定]** = データ/逆アセンブルで直接確認、**[高]** = 複数の状況証拠、**[推測]** = 仮説

前提の訂正: DiveX は FD 的な構成で、本編ストーリーモードのスクリプトは含まれない。戦闘があるモードは
`SelectGameMode.bin` から分岐する以下のみ (`GetFlg(15)` = SelectGameMode.dat の行番号):

| flag15 | モード | 起動 | SetBattleMode(native 481) の値 |
|---|---|---|---|
| 0 | ショートストーリー (IFシナリオ, 一部に戦闘あり) | LoadScript("01…12*.bin") | 0 (既定) |
| 1 | バルドクエスト | LoadScript("BaldrQuest.bin") | 3 [高] |
| 2 | 改造 / 亜季の部屋 (コインショップ) | native_698() | – |
| 3 | バルドアリーナ (観戦/賭け, Tournament) | LoadScript("Tournament.bin") | 5 |
| 4 | バルド地獄 (Hell) | LoadScript("hell.bin") | 4 |
| 5 | 究極サバイバル (「色んな機体を自機として操れる」) | LoadScript("Survival.bin") | 1 |

プレイヤーが機体を選べるのは **究極サバイバル と バルド地獄** (AkisRoomItem の説明文に「『究極サバイバル』『バルド地獄』で『X』を自機として選択できるようになります」と明記)。

作成ツール (/path/to/workspace/tools/):
- `bsdx_tables.py` — .dat / MekaGroup.grp / WazaGroup.grp → TSV (出力: /path/to/workspace/work/tables/)
- `bsdx_bindis.py` — .bin スクリプトの簡易逆アセンブラ (CALL を `Func(args)` 形式で出力。出力: /path/to/workspace/work/bindis/)
- `bsdx_mekinfo.py` — .mek の基本情報と武装リスト (`--weapons`)
- `bsdx_mech_xref.py` — MekaGroup ID × 各テーブルのクロスリファレンス (出力: /path/to/workspace/work/mech_xref.tsv)
- `bsdx_native_case.py` — スクリプトのネイティブ関数 ID → exe 内ハンドラ表示

注: NeXAS_DX 同梱の dat は Update.pac 版と一致 (AkisRoomItem/HellConfig/PlugIn 等は Config.pac 版と異なる)。機体系テーブル (Meka/MekaPilot/SelectMekaMenu/WeaponEquip/Tournament*/Survival*) は Config.pac にしか無い。

---

## 1. 機体レジストリ

### 1.1 MekaGroup.grp = 機体 ID の正本 [確定]
- 場所: Dat.pac `MekaGroup.grp` (Update.pac には無い)
- 形式: `int32 count; { int32 existFlag; if(flag) { cstr name; cstr codeName; } } × count`
- 現在 **103 件 (ID 0..102)**。ID = 配列インデックス。全 103 件に existFlag≠0。
- `name` = .mek ファイルのベース名 (Kou → Kou.mek)、`codeName` = 大文字ラベル (KOU)。
  exe に `Script\Battle\MekaGroup.h` / `MEKA_` 文字列 → 開発用エディタが `#define MEKA_KOU 0` 形式のヘッダを書き出していた名残 (実行時には無関係)。
- ローダ: `CMekaGroupManager::Load` @ **0x6571c0**: "MekaGroup.grp" を開き count を読み、
  件数分 `new CMekaGroup(0x200 bytes)` (ctor 0x6541a0) → std::vector に push_back → `CMekaGroup::Read` (0x6516b0)。
  **ロード自体は可変長 (データ駆動)**。マネージャのグローバルは `[0x86bb04]`、ID→CMekaGroup* 参照は `0x4380e0(id)` (on `[0x86bb04]+4`)。
- .mek → waz/spm: .mek 基本情報の `デフォルト技グループ` = WazaGroup.grp のインデックス (110件)、
  `デフォルトスプライトグループ` = SpriteGroup.grp のインデックス (138件)。例: Kou.mek waz=9 (WazaGroup[9]=甲/Kou.waz)、spm=9。

### 1.2 ただし exe には「103」がハードコードされている [確定] ← 新規 ID 追加の最大の障害
`0x67 (=103)` を境界とするループ/配列:

| アドレス | 内容 |
|---|---|
| 0x461fba | オブジェクト内の固定配列 `[esi+0x84]` と `[esi+0x220]` (各 int×103) をゼロ初期化 |
| 0x461160–0x461193 | `[edi+0x220+id*4]` (状態 1/2/3) を id=0..102 で走査し集計 (図鑑「撃破/閲覧」系統計と推測) |
| 0x5e0780–0x5e08a0 | `[0x874d8c]` (int 配列) を id=0..102 でクリア |
| 0x5f83ca | `rand() % 103` で機体 ID を乱択 (その後 id-10 を 0..0x27 のテーブルで分類) |
| 0x671dc2–0x671dfb | `for id<103: MekaGroup(id)->0x64f130(...)` (セーブ/ロード系の機体ごと処理と推測) |
| 0x6736c0–0x6736f9 | `for id<103: MekaGroup(id)->0x652370(...)` |
| 0x673780–0x673835 | `for id<103: MekaGroup(id)->0x651540(3)` |
| (参考) 0x466d45, 0x4e0c14, 0x5ca627 | `mov …,0x67` (配列サイズ初期化と推測、未確認) |

→ **ID 103 以降を足すと、これらのループに含まれない/固定長配列 (特に構造体内の int[103]) を越えて書き込む恐れ**。
新機体は「既存 ID の差し替え」で入れるのが現実的 (§4)。

### 1.3 ハードコードされた機体 ID (変形・分離ペア) [確定]
`LoadMek` 実装 0x672240 / `ReleaseMek` 0x6722b0 / `CMekaGroup` ロード 0x5df030 / 0x5df10b / 0x59a3e1 で:
- ID 19 (Neunzehn) を読むと ID 20 (Neunzehn2) も読む
- ID 22 (Chris) → ID 23 (Chris2)
- ID 48 (Zako208a ハーミット) → ID 49 (Zako208a2 ハーミット(殻))
（.mek の武装 `switchToMek` フィールドでも Chris↔Chris2、208a↔208a2 が相互参照）。
新機体に変形を持たせる場合はこの比較列の追加 (exe パッチ) が必要。

### 1.4 機体関連 .dat テーブル (全て Config.pac) [行=データ駆動, exe は vector サイズで件数を算出]

`.dat` 形式: `int32 nCol; int32 colType[nCol] (0/2=int, 1=cp932文字列); 行…EOF`

| ファイル | 行数 | 列 | 意味 | 信頼度 |
|---|---|---|---|---|
| Meka.dat | 99 | c0=機体ID, c1=数値 | 「ゲームに登場する機体」マスタ順 (Kou..Zako215a, Sora2/Neunzehn2/Chris2/Zako208a2 を除く99機)。exe グローバル vector `0xbe74c4..c8` (8バイト行)。c1 は 0x5fcf8c でスコア/報酬計算に使用 (`c1*x*7/100`) | 構造[確定] c1意味[推測: 撃破報酬係数] |
| MekaPilot.dat | 70 | c0=機体ID | **プレイヤーが使用可能な機体の一覧** (Kou + 購入解禁 69機)。MekaPilot.spm (パイロット絵, System.pac側) と対 | [高] |
| SelectMekaMenu.dat | 99 | c0=機体ID, c1=サムネ番号, c2=亜季の部屋アイテムID | 選択画面/アリーナ表示用の行。c1 は SelectMekaMenuMeka.spm のフレーム番号 [高]、c2 は AkisRoomItem.dat の行 (購入で解禁)。c2=-1 は Kou(行0) と雑魚29機(行70–98, 非プレイアブル) | c0/c2 [確定], c1 [高] |
| WeaponEquip.dat | 103 | 14 列 | **行番号 = 機体ID**。プレイヤー操作時のボタン/スロット→その機体の .mek 武装インデックス。スロット0–11 = 通常武装、12–13 = FC (フォースクラッシュ) / イニシャライザ。-1=空き。Kou 行は 153 武装中のデフォルト装備 | 行=ID [確定], スロット意味 [高] |
| Weapon.dat | 153 | c0=武装idx, c1(1..5), c2, c3(-1 or 武装idx) | **甲(Kou)専用** のカスタマイズ用武装表 (Kou.mek の武装数 153 と一致)。c1/c2/c3 の意味は未確定 (コスト/最大Lv/上位版リンク?) | 対応[確定] 列[推測] |
| AkisRoomItem.dat | 232 | c0=種別(2=見出し,1=商品), c1=価格(コイン), c2, c5=名前, c6=説明 … | 行84=見出し「使用機体」, 行85–153 = 機体解禁アイテム (69件) | [確定] |
| TournamentMekaData.dat | 99 | c0=機体ID, c1..c5 | アリーナ出場機の強さ/オッズ等 [推測] | – |
| SurvivalMekaMain/Zako/Rare.dat | 24/86/34 | c0=機体ID … | サバイバルの出現機体 (敵側) | [高] |
| HellConfig.dat | 100 | c0=ステージ名, c1=ID, c2=マップ, c3..c10=敵機ID(-999終端), …, c22=説明 | 地獄モードのステージ選択画面用 (プレビュー表示)。実際の配置は Hell###.bin | [高] |
| BQUnit.dat / BQMekaMemory.dat / nq_*.dat | | | バルドクエスト/ニラクエスト側 (自機は Kou 固定) | – |

クロスチェック結果 (mech_xref.tsv): `{SelectMekaMenu で c2≠-1 の機体} ∪ {Kou} == {MekaPilot の機体}` (70機, 完全一致)。
WeaponEquip が設定済み (全-1 でない) の機体は 88。プレイアブル70機は全て設定済み。追加で Chris2(23), Zako208a2(49) 等の変形先も設定済み → **変形先にもスロット定義が要る**。
完全未使用の ID: **10 (Sora2)** — どのテーブル (Meka/MekaPilot/SelectMekaMenu) にも、どのスクリプトの LoadMek/InitDeployMek にも出現せず、WeaponEquip 行10も全-1 → **新機体の差し替え先として最適**。

---

## 2. 「どれがプレイヤー機か」の決定

### 2.1 戦闘のスクリプト起動 [確定]
ネイティブ関数ディスパッチ: 汎用 0..705 は switch @0x78047c (表 0x7836f4)、ゲーム固有は default → `0x449d70` で `id-410` の switch (@0x449d87, 表 0x44bea4, 0..0x124)。
戦闘系は全てグローバル `CBattle* [0x86bae8]` のメソッド呼び出し。

| native | 名前 (NeXAS_DX命名 / 推定) | exe 実体 | 引数 |
|---|---|---|---|
| 481 | (SetBattleMode) | 0x6740d0 | (mode, flag) → `[0x86ba5c]=mode`、プレイヤー機 `[0x86ba54]` を確定 (§2.2) |
| 506 | LoadMap | 0x66f740 | (mapId, ?, bool) |
| 541 | LoadMek | 0x672240 → 0x5df030 → CMekaGroup::Load 0x6551f0 | (mekId, 127, motionFlag?, ?) — **mekId=-1 は `[0x86ba54]`(プレイヤー機) に置換**。127 は 7 素材ブロック全部のビットマスクと推測 |
| 542 | (ReleaseMek) | 0x6722b0 | LoadMek と同じ引数、参照カウント減算 |
| 553 | InitDeployMek | 0x672310 | (unitNo, team, mekId, lv?, x, y, z, angle) — **mekId=-1 は同様にプレイヤー機に置換**。unitNo=0 がプレイヤー操作ユニット |
| 668 | MidDeployMek | | 途中参戦 |
| 530 | (DeployPlayer?) | | Survival で `(0,1,-1,16)` |

典型 (Hell100：ノイ.bin, bank 構成):
```
START 1000:  LoadMek(21, 127, -1, -1)            ; 敵 Noi の素材ロード
START 1003:  native_542(21, 127, -1, -1)          ; 解放
START 1002:  LoadMap(45, 0, 1)
             InitDeployMek(0, 1, -1, 16, 1110, 1100, 0, 180)   ; ユニット0=自機(選択中の機体)
             InitDeployMek(1, 2, 21, 10, 1110, 570, 0, 180)    ; 敵 ID21 イムくん
```
全スクリプト集計 (InitDeployMek, unitNo=0): `mekId=-1` が 174 回 (Hell/Survival)、`mekId=0`(Kou固定) が 44 回 (ショートストーリー内戦闘・チュートリアル)。unitNo=0 に Kou/-1 以外を置く例は無し。
team: 1=味方, 2=敵, 0=中立? 第4引数は 10/16 が大半 (CPUレベル/機体Lv と推測)。

モードスクリプト側:
- `hell.bin`: SetBattleMode(4) → `LoadMek(-1,127,-3,-1)` でプレイヤー機を先読み → CallBank(9,1000/1002/1003) でステージスクリプトの bank を呼ぶ。
- `Survival.bin`: SetBattleMode(1) → `LoadMek(-1,127,-3,-1)` → `native_530(0,1,-1,16)`。
- `Tournament.bin`: SetBattleMode(5) (観戦なのでプレイヤー機なし)。

### 2.2 プレイヤー機 ID の保持場所 [確定]
- 現在のプレイヤー機: **`[0x86ba54]`** (int, MekaGroup ID)。参照 141 箇所。
- SetBattleMode (0x674147–0x674180): `[0x86ba54] = (mode != 0) ? [0x873bd0] : [0x87452c]`
  → `[0x873bd0]` = 選択モード(サバイバル/地獄)用に保存された選択機体、`[0x87452c]` = mode0 用 (セーブデータ領域と推測)。
- バルドクエスト (mode 3) 初期化 0x452a94–0x452abd: `[0x86ba54] = 0` (Kou 固定) + BQPlugInList.dat。それ以外 PlugInList.dat。
- 機体変更関数 **0x5de160 (ChangePlayerMeka(id))**:
  - mode==4 (地獄): `[0x86ba54]=id` かつ `[0x873bd0]=id` (mode0 なら `[0x87452c]`)
  - mode==1 (サバイバル) 等: 戦闘中差し替え経路 → 旧機体解放 0x66f8b0 → 0x5dd9b0(id) → 新機体ロード 0x66f890 (exe 文字列「サバイバルメカバトル中解放/ロード」と対応)
  - 呼び出し元: 0x532556 (選択メニュー確定), 0x446141/0x44615b/0x44831b (スクリプトネイティブ側)。
- 選択 UI クラス:
  - 地獄: ステージ選択 (HellConfig.dat, MekaPilot.dat, SelectMekaMenu.dat, SelectHellStage.spm, MekaPilot.spm, SelectMekaMenuMeka.spm) @0x53a9xx
  - サバイバル: `CSelectMekaMenu` (SelectMekaMenu.dat/.spm, MekaPilot.dat/.spm) @0x54c0xx
  - アリーナ: TournamentMekaData.dat + SelectMekaMenu.dat (サムネのみ利用) @0x546bxx
  - SelectMekaMenu は 12 バイト行 vector、件数は vector サイズから算出 (0x487b0c ほか) → **行数はデータ駆動**。
- ロック判定: 0x54bd20 (ボタンID-0x2b9 = SelectMekaMenu 行) → `c2==-1` なら何もしない、
  それ以外 `ItemStatus(c2)` (0x450970, `[0x874c88]` のアイテムフラグ配列) が 1 なら「アイテムを購入するには %dコインが必要です」、2 なら「ロックされています」。
  `ItemStatus(-1)=0`(=使用可) なので、c2=-1 は「常時使用可」として扱われる可能性あり [推測]。ただし雑魚29機 (行70–98) は MekaPilot に無く、選択画面には出ない (アリーナ用の行) と推測 [高]。

### 2.3 甲 (Kou) だけの特別扱い [確定]
- SetBattleMode 0x674185–0x67420a: プレイヤー機が ID0 なら Kou 武装状態配列 `[0x874ca0]` (0x60 バイト × **153 固定**, `cmp esi,0x3960`) の各 `+4` を 2、それ以外なら 0 に設定。
- Kou 用の装備プリセット (14 スロット × 複数セット, 0x10f0 構造体) をセーブから `[esi+0x4b1c]` (int[14]) へコピー (0x452920–0x4529b1)。
- Weapon.dat (153行) は Kou 専用。Kou.mek の武装 153 件のうち 113 件に `必要経験値`>0 (=経験値で解禁するカスタマイズ武装)。

---

## 3. プレイヤー機に必要なデータ (ロードアウト)

- **Kou 以外の機体: ロードアウトは固定**。WeaponEquip.dat の行 (= 機体ID) の 14 スロットが、その機体の .mek 武装ブロックのインデックスを指す。カスタマイズ UI は無い。
- **Kou: カスタマイズ可能**。武装プール = Kou.mek 武装 153 件、解禁/装備条件 = Weapon.dat (153行) + 武装の `必要経験値`、プリセット/状態はセーブデータ (exe 内に 153 固定)。
- .mek の武装エントリ (NeXAS_DX MekParser): `name, code, desc, switchToMek, wazSeq(=waz内技番号), FC量, 熱(最大/最小), 必要経験値, デモ距離, category(0=通常,1=FC,2=イニシャライザ), atkType(0=打撃,1=射撃,2=…), 各タイプフラグ×8, weaponId, unk`。
- プレイヤーとして使うのに必要なもの (現状の理解):
  1. MekaGroup.grp にエントリ (ID)
  2. .mek (+ WazaGroup/SpriteGroup に waz/spm) — 敵用と同一ファイルでよい (実例: 雑魚もプレイアブル)
  3. WeaponEquip.dat 行 ID に 14 スロット (これが無い/全-1 だと攻撃ボタンが空になるはず [推測])
  4. 選択画面に出すなら SelectMekaMenu.dat 行 + MekaPilot.dat 行 (+ SelectMekaMenuMeka.spm/MekaPilot.spm のフレーム) + 解禁用 AkisRoomItem 行 (c2)
  5. 変形するなら exe のペア比較 (§1.3)

---

## 4. 最小編集案

### 4(a) 実験1: プレイヤー機を既存の敵機体にすり替える

**案A (データのみ・最小, 推奨)**: 「選択画面で X を選ぶと別機体 Y が出る」ようにする。
1. Dat.pac `MekaGroup.grp`: プレイアブル機 X のエントリの name/codeName を Y の .mek 名に書き換え
   (例: ID 28 `Zako021b` → `Zako213a`)。※同じ ID を使う敵 (他ステージの X) も Y になる点に注意。
2. Config.pac `WeaponEquip.dat` 行 X: Y の .mek 武装インデックスで 14 スロットを埋め直す
   (`bsdx_mekinfo.py --weapons` で Y の武装一覧を確認。Y の waz/spm は .mek 内の参照で自動的に正しく読まれる)。
3. 地獄/サバイバルで X を購入・選択して確認 (または既に解禁済みセーブで)。
→ スクリプト・exe は無変更。必要なのは Dat.pac と Config.pac の再パック (nexaspac.py)。

**案B (スクリプト)**: Hell###.bin の bank 1002 `InitDeployMek(0,1,-1,…)` の第3引数を Y に、bank 1000/1003 に `LoadMek(Y,127,-1,-1)` / `native_542(Y,…)` を追加。
NeXAS_DX の BinParser/BinGenerator (JSON 往復) で再生成。Y の WeaponEquip 行が設定済みであること (WeaponEquip 全-1 の機体: 10,20,27,29,30,31,33,42,56,65,76,77,78,88,93 は不可)。

### 4(b) 新機体の登録

**推奨: 新 ID を作らず未使用 ID 10 (Sora2) を差し替える** (exe の 103 固定を回避)。
1. Dat.pac: `MekaGroup.grp` 10 番を `NewMech/NEWMECH` に、`NewMech.mek` を追加 (Sora2.mek は残しても可)。
   新 .mek の waz/spm は WazaGroup.grp (現110) / SpriteGroup.grp (現138) に**末尾追加**してそのインデックスを .mek に書く
   (これらのグループ数に exe 側の固定上限があるかは**未調査**)。
2. Config.pac:
   - `WeaponEquip.dat` 行10 に 14 スロット
   - `MekaPilot.dat` に 10 を追加
   - `SelectMekaMenu.dat` に `(10, サムネ番号, アイテムID)` を追加 (サムネは既存番号を流用可。アイテムは既存の機体解禁アイテムを流用するか、c2=-1 で常時解禁を試す)
   - (任意) `Meka.dat` に `(10, 報酬係数)`、`AkisRoomItem.dat` に解禁アイテム行、`SurvivalMekaMain/Zako/Rare.dat`・`TournamentMekaData.dat` に敵として出したい場合の行
   - (任意) `PersonalData.dat`/図鑑系は未調査
3. exe パッチ不要 (変形しない場合)。

**どうしても ID 103 を新設する場合に必要な exe パッチ (未検証・高リスク)**:
§1.2 の `0x67` 比較/定数を `0x68` に変更 (0x461193, 0x461fba, 0x5e08a0, 0x5f83ca, 0x671dfb, 0x6736f9, 0x673835, 0x466d45/0x4e0c14/0x5ca627 を要確認)。
ただし 0x461fba の配列は構造体 (`[esi+0x84]`, `[esi+0x220]`, 間隔 0x19c=103*4) に埋め込まれており、要素追加で後続フィールドとずれる → セーブ形式の変更を伴う可能性大。現段階では非推奨。

---

## 未解決事項 / 次の確認
1. MekaPilot.spm / SelectMekaMenuMeka.spm のフレームが行番号とどう対応するか (spm は System.pac 側の可能性。System.pac は未ステージ)。新行追加時に画像が無いとクラッシュするか。
2. SelectMekaMenu c2=-1 の機体が選択可能か (ItemStatus(-1)=0 なので可能性あり) — 実機テストで確認。
3. 選択画面の一覧が MekaPilot 由来か SelectMekaMenu 由来か (CSelectMekaMenu init 0x54c0xx の詳細解析が未了)。
4. WazaGroup/SpriteGroup/SeGroup/BatVoice 側にもハードコード件数があるか。
5. Weapon.dat c1–c3、TournamentMekaData/SurvivalMeka* 各列の意味。
6. `[0x873bd0]`/`[0x87452c]` のセーブ内オフセット (既存セーブで新 ID を選んだ状態の保存可否)。

---

## 5. 追記 (2026-10-22, Phase 1 パック作成時の解析) [確定 = 逆アセンブルで確認]
- **CSelectMekaMenu のボタンは 70 個にハードコード**: 生成ループ 0x54c666–0x54c7f7 (`[esp+0x14]` を 0xc ずつ 0x33c まで = SelectMekaMenu 行 0..69)、
  更新ループ 0x54b8b0–0x54b930 / 0x54bb07– (`ebp` 0x20ac→0x23e8 step 0xc = 70)。ボタン ID = 0x2b9+行、座標は Button.dat (0xcb5a5c, 72B 行) の 697..766 行。
  → 行を追加しても 71 個目は出ない。**新機体を選択画面に出すには既存 0..69 行のどれかと入れ替える** (exe パッチ無しの場合)。
- アイテム ctor 0x54f970 / setup 0x54f470: SelectMekaMenu 行 (ボタン番号) の c1 → SelectMekaMenuMeka.spm の anim 番号 (確定)、c2 → ItemStatus(0x450970)。c2=-1 は甲と同じく常時選択可。
- 詳細欄 0x54d4cb: MekaPilot.dat を **機体 ID で線形検索** し、見つかった行番号 = MekaPilot.spm の anim 番号 (無ければ -1)。
- 選択画面/地獄ステージ選択/その他メニューは ctor で **Meka.dat の全機体を CMekaGroup::0x64f2e0 (mek 読み込み・参照カウント+1) で事前ロード**、dtor で 0x64f660 解放
  (0x54c2e1, 0x53aa53, 0x5324d9, 0x4d3927, 0x512d36, 0x5ce71b)。→ 自機にする機体は Meka.dat に必要。
- Meka.dat c1 = **自機の**コイン倍率 (0x5fcf52: `idx = FindMekaRow([0x86ba54])`, `c1 * score * 7 / 100`)。0x513025/0x5132b1 は Meka.dat 全機の「既知フラグ」(0x86f9a8, 0x4504c0) を数える (図鑑/達成率系と推測)。
- 0x5f83ca `rand()%103` の再抽選表 (0x5f8598): ID 10, 20, 23, 49 を除外 (変形先/未使用)。ID 10 はランダム出現しない。
- waz/spm を複数 ID で共有する前例: waz 26 = Sora(9)/Sora2(10)、waz 27 + spm 26 = Neunzehn(19)/Neunzehn2(20) (同時ロード)、spm 38 = Aki(7)/Zako003c(93)。
- 敵専用機で WeaponEquip 行が設定済み (開発元の割当が残存): 34,36,37,38,39,40,44,46,47,53,59,71,75,79,86,98。
- Phase 1 パック: /path/to/workspace/mods/phase1_test/ (颪 Zako029a → ID 10、晴嵐のボタン枠 27 を貸与)。

## 追記（2026-10-22 ユーザー情報）
WeaponEquip.dat は初期配置にすぎず、インゲームの「装備」画面で武装配置を自由に組み替えられる（通常 12 枠 + FC/イニシャライザ 2 枠）。
本文 §3 の「甲以外は固定装備」という推定は要修正。甲以外の機体で装備可能な候補がどこで決まるか（mek の武器リスト全体か）を動画・実機で確認すること。
